# =============================================================================
# Frappe Server Script — API
# Method name: set in Server Script (e.g. auto_material_transfer_on_start)
# Paste entire file into Server Script body. Do NOT add "import" lines.
#
# Fixes:
#   1) No imports — use frappe.parse_json only (safe_exec).
#   2) ERPNext v16 batch stock — merge classic SLE.batch_no + Serial and Batch
#      Entry (same idea as production_entry SPR). Prevents BatchNegativeStockError
#      when picks/qty exceed bundle-visible balance.
#   3) Auto path — only allocates batches with positive merged qty in source_wh.
#   4) FG 102/103/104/107: skip only when batch-tracked 100* fabric exists on the WO
#      and no fabric_batch_picks were sent; otherwise run (picks path or auto FIFO).
#   5) parse_fabric_batch_picks accepts list/dict or JSON strings.
#   6) Client sends fabric_picks_json + wo_transfer_payload (strings) — Server Script form_dict
#      often drops nested list args from frappe.call; strings survive.
#   7) Do not use frappe.db.has_column in Server Script safe_exec — it is not exposed; use Meta.has_field.
# =============================================================================


def sle_has_serial_batch_bundle_link():
    """True if Stock Ledger Entry links Serial and Batch Bundle (v15+). Safe in Server Script."""
    try:
        return bool(frappe.get_meta("Stock Ledger Entry").has_field("serial_and_batch_bundle"))
    except Exception:
        return False


def wo_has_100_batch_fabric_rm(wo):
    """True if this WO needs fabric batch picks (100* RM with has_batch_no)."""
    for row in wo.required_items or []:
        ic = str(row.item_code or "").strip()
        if not ic.startswith("100"):
            continue
        if frappe.utils.flt(row.required_qty or 0) <= 0:
            continue
        try:
            if frappe.db.get_value("Item", ic, "has_batch_no"):
                return True
        except Exception:
            pass
    return False


def fg_needs_manual_fabric_picks(production_item):
    """True when FG item code contains 102 / 103 / 104 / 107 anywhere.

    For these FGs we do not auto FIFO fabric batches. If the client POSTs
    ``fabric_batch_picks``, transfer still runs using those picks for 100* RM lines.
    """
    if not production_item:
        return False
    pi = str(production_item)
    for code in ("102", "103", "104", "107"):
        if code in pi:
            return True
    return False


def get_total_qty(item_code, warehouse):
    qty = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        "actual_qty",
    )
    return frappe.utils.flt(qty or 0)


def batch_qty_classic_sle(item_code, batch_no, warehouse):
    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(actual_qty), 0)
        FROM `tabStock Ledger Entry`
        WHERE IFNULL(is_cancelled, 0) = 0
          AND item_code = %s
          AND warehouse = %s
          AND IFNULL(batch_no, '') = %s
        """,
        (item_code, warehouse, batch_no),
    )
    return frappe.utils.flt((row and row[0] and row[0][0]) or 0)


def batch_qty_bundle_sle(item_code, batch_no, warehouse):
    """Positive outward-safe batch qty from Serial and Batch Bundle child rows."""
    if not sle_has_serial_batch_bundle_link():
        return 0.0
    sb_dt = "Serial and Batch Entry"
    if not frappe.db.exists("DocType", sb_dt):
        return 0.0
    try:
        meta = frappe.get_meta(sb_dt)
        batch_field = next(
            (fn for fn in ("batch_no", "batch", "batch_id") if meta.has_field(fn)),
            "",
        )
        qty_field = next(
            (fn for fn in ("qty", "quantity") if meta.has_field(fn)),
            "",
        )
        if not batch_field or not qty_field:
            return 0.0
        rows = frappe.db.sql(
            f"""
            SELECT
                SUM(
                    CASE
                        WHEN IFNULL(sle.actual_qty, 0) < 0
                            THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
                        ELSE ABS(IFNULL(sbe.`{qty_field}`, 0))
                    END
                ) AS q
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabSerial and Batch Entry` sbe
                ON sbe.parent = sle.serial_and_batch_bundle
            WHERE IFNULL(sle.is_cancelled, 0) = 0
              AND IFNULL(sle.item_code, '') = %s
              AND IFNULL(sle.warehouse, '') = %s
              AND IFNULL(sle.serial_and_batch_bundle, '') != ''
              AND IFNULL(sbe.`{batch_field}`, '') = %s
            """,
            (item_code, warehouse, batch_no),
        )
        return frappe.utils.flt((rows and rows[0] and rows[0][0]) or 0)
    except Exception:
        return 0.0


def get_batch_qty_in_warehouse(item_code, batch_no, warehouse):
    """Use max(classic, bundle) so we do not double-count the same stock twice."""
    if not item_code or not batch_no or not warehouse:
        return 0.0
    c = batch_qty_classic_sle(item_code, batch_no, warehouse)
    b = batch_qty_bundle_sle(item_code, batch_no, warehouse)
    return max(c, b)


def get_batches_from_ledger(item_code, warehouse):
    """Batches with positive merged balance in one warehouse (for auto path)."""
    acc = {}
    for r in frappe.db.sql(
        """
        SELECT batch_no, SUM(actual_qty) AS qty
        FROM `tabStock Ledger Entry`
        WHERE IFNULL(is_cancelled, 0) = 0
          AND item_code = %s
          AND warehouse = %s
          AND IFNULL(batch_no, '') != ''
        GROUP BY batch_no
        HAVING SUM(actual_qty) > 0
        """,
        (item_code, warehouse),
        as_dict=True,
    ):
        bn = (r.get("batch_no") or "").strip()
        q = frappe.utils.flt(r.get("qty") or 0)
        if bn and q > 0:
            acc[bn] = acc.get(bn, 0.0) + q

    if sle_has_serial_batch_bundle_link():
        try:
            sb_dt = "Serial and Batch Entry"
            if frappe.db.exists("DocType", sb_dt):
                meta = frappe.get_meta(sb_dt)
                batch_field = next(
                    (fn for fn in ("batch_no", "batch", "batch_id") if meta.has_field(fn)),
                    "",
                )
                qty_field = next(
                    (fn for fn in ("qty", "quantity") if meta.has_field(fn)),
                    "",
                )
                if batch_field and qty_field:
                    rows = frappe.db.sql(
                        f"""
                        SELECT
                            sbe.`{batch_field}` AS batch_no,
                            SUM(
                                CASE
                                    WHEN IFNULL(sle.actual_qty, 0) < 0
                                        THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
                                    ELSE ABS(IFNULL(sbe.`{qty_field}`, 0))
                                END
                            ) AS qty
                        FROM `tabStock Ledger Entry` sle
                        INNER JOIN `tabSerial and Batch Entry` sbe
                            ON sbe.parent = sle.serial_and_batch_bundle
                        WHERE IFNULL(sle.is_cancelled, 0) = 0
                          AND IFNULL(sle.item_code, '') = %s
                          AND IFNULL(sle.warehouse, '') = %s
                          AND IFNULL(sle.serial_and_batch_bundle, '') != ''
                          AND IFNULL(sbe.`{batch_field}`, '') != ''
                        GROUP BY sbe.`{batch_field}`
                        HAVING SUM(
                            CASE
                                WHEN IFNULL(sle.actual_qty, 0) < 0
                                    THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
                                ELSE ABS(IFNULL(sbe.`{qty_field}`, 0))
                            END
                        ) > 0
                        """,
                        (item_code, warehouse),
                        as_dict=True,
                    )
                    for r in rows or []:
                        bn = (r.get("batch_no") or "").strip()
                        q = frappe.utils.flt(r.get("qty") or 0)
                        if bn and q > 0:
                            acc[bn] = max(acc.get(bn, 0.0), q)
        except Exception:
            pass

    out = [{"batch_no": k, "qty": frappe.utils.flt(v)} for k, v in acc.items()]
    out.sort(key=lambda x: frappe.utils.flt(x.get("qty") or 0), reverse=True)
    return out


def parse_fabric_batch_picks(form_dict):
    """Read picks from form_dict (JSON string, or list/dict from frappe.call)."""
    raw = form_dict.get("fabric_batch_picks")
    if raw is None:
        raw = form_dict.get("fbp")
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [p for p in raw if p]
    if isinstance(raw, dict):
        return [raw] if raw else []
    s = str(raw).strip()
    if not s:
        return []
    try:
        data = frappe.parse_json(s)
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def extract_fabric_picks_from_request():
    """Resolve picks from form_dict. Server Scripts often drop nested list args — prefer JSON strings."""
    fd = frappe.form_dict
    if fd is None:
        fd = {}
    env = fd.get("wo_transfer_payload")
    if env:
        try:
            ed = frappe.parse_json(str(env).strip())
            if isinstance(ed, dict):
                pl = ed.get("fabric_batch_picks")
                if isinstance(pl, list) and pl:
                    return pl
                if isinstance(pl, str) and str(pl).strip():
                    out = parse_fabric_batch_picks({"fabric_batch_picks": str(pl).strip()})
                    if out:
                        return out
        except Exception:
            pass
    for key in ("fabric_picks_json", "fabric_batch_picks", "fbp"):
        blob = fd.get(key)
        if blob is None:
            continue
        if isinstance(blob, (list, tuple)) and blob:
            out = parse_fabric_batch_picks({"fabric_batch_picks": blob})
            if out:
                return out
        s = str(blob).strip()
        if len(s) > 1 and s[0] in "[{":
            out = parse_fabric_batch_picks({"fabric_batch_picks": s})
            if out:
                return out
    out = parse_fabric_batch_picks(fd)
    if out:
        return out
    args_blob = fd.get("args") if fd else None
    if args_blob:
        try:
            ad = frappe.parse_json(args_blob) if isinstance(args_blob, str) else args_blob
            if isinstance(ad, dict):
                out = parse_fabric_batch_picks(ad)
                if out:
                    return out
        except Exception:
            pass
    if fd:
        for key, val in fd.items():
            if val is None or key in ("cmd", "method"):
                continue
            sv = str(val).strip()
            if len(sv) > 2 and sv[0] == "[" and "batch_no" in sv:
                out = parse_fabric_batch_picks({"fabric_batch_picks": sv})
                if out:
                    return out
    try:
        req = getattr(frappe.local, "request", None)
        if req is not None:
            getd = getattr(req, "get_data", None)
            if callable(getd):
                rawb = getd(as_text=True)
                if rawb and str(rawb).strip().startswith("{"):
                    jd = frappe.parse_json(rawb)
                    if isinstance(jd, dict):
                        out = parse_fabric_batch_picks(jd)
                        if out:
                            return out
                        inner = jd.get("args")
                        if inner:
                            if isinstance(inner, str):
                                inner = frappe.parse_json(inner)
                            if isinstance(inner, dict):
                                out = parse_fabric_batch_picks(inner)
                                if out:
                                    return out
    except Exception:
        pass
    return []


def picks_pool_for_item(picks_list, item_code):
    """Match picks for one item_code. Uses only try/except — no blocked builtins."""
    out = []
    target = str(item_code or "").strip()
    for p in (picks_list or []):
        if not p:
            continue
        try:
            ic = str(p.get("item_code") or "").strip()
        except Exception:
            try:
                p = frappe.parse_json(str(p))
                ic = str(p.get("item_code") or "").strip()
            except Exception:
                continue
        if ic != target:
            continue
        try:
            bn = str(p.get("batch_no") or "").strip()
            q = frappe.utils.flt(p.get("qty"))
            if bn and q > 0:
                out.append({"batch_no": bn, "qty": q})
        except Exception:
            pass
    return out


def auto_material_transfer():
    try:
        wo_id = frappe.form_dict.get("work_order") or frappe.form_dict.get("wo_id")
        if not wo_id:
            env = (frappe.form_dict or {}).get("wo_transfer_payload")
            if env:
                try:
                    ed = frappe.parse_json(str(env).strip())
                    if isinstance(ed, dict):
                        wo_id = ed.get("work_order") or ed.get("wo_id")
                except Exception:
                    pass
        if not wo_id:
            frappe.throw("Work Order Missing")

        wo = frappe.get_doc("Work Order", wo_id)
        if wo.docstatus != 1:
            frappe.throw("Submit Work Order First")

        if frappe.utils.flt(wo.material_transferred_for_manufacturing) >= frappe.utils.flt(
            wo.qty
        ):
            wo.db_set("status", "In Process")
            frappe.response["message"] = {"success": True, "message": "Already Started"}
            return

        fabric_picks = extract_fabric_picks_from_request()
        fg_manual = fg_needs_manual_fabric_picks(wo.production_item)
        manual_pick_fallback = False
        # Never hard-stop WO start here. If picks did not arrive, continue with auto FIFO
        # for this run so production is not blocked.
        if fg_manual and not fabric_picks:
            manual_pick_fallback = wo_has_100_batch_fabric_rm(wo)
            fg_manual = False

        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Transfer for Manufacture"
        se.purpose = "Material Transfer for Manufacture"
        se.company = wo.company
        se.work_order = wo.name
        se.to_warehouse = wo.wip_warehouse
        se.use_serial_batch_fields = 1

        items_added = False
        # (item_code, source_wh, batch_no) -> qty already allocated on this SE
        batch_reserved = {}

        for row in wo.required_items:
            item_code = str(row.item_code or "").strip()
            if not item_code:
                continue
            req_qty = frappe.utils.flt(row.required_qty)
            if req_qty <= 0:
                continue

            source_wh = row.source_warehouse or wo.source_warehouse
            has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")

            if not has_batch:
                avail = get_total_qty(item_code, source_wh)
                if avail < req_qty:
                    frappe.throw(
                        str(item_code)
                        + " need "
                        + str(req_qty)
                        + " available "
                        + str(avail)
                        + " in "
                        + str(source_wh)
                    )
                se.append(
                    "items",
                    {
                        "item_code": item_code,
                        "s_warehouse": source_wh,
                        "t_warehouse": wo.wip_warehouse,
                        "qty": req_qty,
                        "transfer_qty": req_qty,
                        "uom": row.stock_uom,
                        "stock_uom": row.stock_uom,
                        "conversion_factor": 1,
                    },
                )
                items_added = True
                continue

            total = get_total_qty(item_code, source_wh)
            if total < req_qty:
                frappe.throw(
                    str(item_code)
                    + " need "
                    + str(req_qty)
                    + " available "
                    + str(total)
                    + " in "
                    + str(source_wh)
                )

            use_manual_fabric = fg_manual and str(item_code).startswith("100")

            if use_manual_fabric:
                pool = picks_pool_for_item(fabric_picks, item_code)
                if not pool:
                    frappe.throw(
                        "fabric_batch_picks required for fabric item "
                        + str(item_code)
                        + " (FG 104/107/102/103). POST fabric_batch_picks as JSON string, e.g. "
                        + '[{"item_code":"100...","batch_no":"B1","qty":10}]'
                    )
                pending = req_qty
                for pick in pool:
                    if pending <= 0:
                        break
                    bn = pick["batch_no"]
                    max_from_pick = frappe.utils.flt(pick["qty"])
                    rk = (item_code, source_wh, bn)
                    ledger_bal = get_batch_qty_in_warehouse(item_code, bn, source_wh)
                    used_here = frappe.utils.flt(batch_reserved.get(rk) or 0)
                    wh_avail = max(0.0, ledger_bal - used_here)
                    if wh_avail <= 0:
                        continue
                    use_qty = min(max_from_pick, wh_avail, pending)
                    if use_qty <= 0:
                        continue
                    se.append(
                        "items",
                        {
                            "item_code": item_code,
                            "s_warehouse": source_wh,
                            "t_warehouse": wo.wip_warehouse,
                            "qty": use_qty,
                            "transfer_qty": use_qty,
                            "uom": row.stock_uom,
                            "stock_uom": row.stock_uom,
                            "conversion_factor": 1,
                            "batch_no": bn,
                            "use_serial_batch_fields": 1,
                        },
                    )
                    pending -= use_qty
                    batch_reserved[rk] = used_here + use_qty
                    items_added = True
                if pending > 0.0001:
                    frappe.throw(
                        str(item_code)
                        + ": picks do not cover required "
                        + str(req_qty)
                        + " in "
                        + str(source_wh)
                        + " (short "
                        + str(frappe.utils.flt(pending, 3))
                        + "). Check batch balances in this warehouse or add picks."
                    )
            else:
                pending = req_qty
                batches = get_batches_from_ledger(item_code, source_wh)
                for b in batches:
                    if pending <= 0:
                        break
                    bn = b.get("batch_no")
                    wh_avail = get_batch_qty_in_warehouse(item_code, bn, source_wh)
                    if wh_avail <= 0:
                        continue
                    use_qty = min(wh_avail, pending)
                    se.append(
                        "items",
                        {
                            "item_code": item_code,
                            "s_warehouse": source_wh,
                            "t_warehouse": wo.wip_warehouse,
                            "qty": use_qty,
                            "transfer_qty": use_qty,
                            "uom": row.stock_uom,
                            "stock_uom": row.stock_uom,
                            "conversion_factor": 1,
                            "batch_no": bn,
                            "use_serial_batch_fields": 1,
                        },
                    )
                    pending -= use_qty
                    items_added = True
                if pending > 0:
                    frappe.throw(
                        str(item_code)
                        + " pending batch qty "
                        + str(pending)
                        + " in "
                        + str(source_wh)
                    )

        if not items_added:
            frappe.throw("No Items To Transfer")

        se.insert(ignore_permissions=True)
        se.submit()
        frappe.db.commit()

        wo.reload()
        wo.db_set("material_transferred_for_manufacturing", wo.qty)
        wo.db_set("status", "In Process")
        wo.db_set("actual_start_date", frappe.utils.now_datetime())
        wo.reload()

        done_msg = "Production Started : " + str(se.name)
        if manual_pick_fallback:
            done_msg += " (batch picks not received; used auto FIFO allocation)"
        frappe.response["message"] = {"success": True, "message": done_msg}

    except Exception as e:
        frappe.log_error(str(e), "WO Start Error")
        frappe.throw(str(e))


auto_material_transfer()
