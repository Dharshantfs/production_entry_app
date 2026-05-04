# =============================================================================
# Frappe Server Script — DocType Event
# Reference DocType: Work Order
# Event: After Insert
#
# Paste entire body into Server Script (no "import" lines; safe_exec).
# Do NOT call frappe.utils.get_traceback() in Server Scripts (stub may lack it).
#
# Behaviour:
#   - Still sets warehouses from Material Request Plan Item (when PP exists).
#   - Skips auto-submit + material transfer when:
#       (a) Production Plan custom_unit is Lamination Unit, OR
#       (b) FG production_item contains 102, 103, 104, or 107 anywhere in the string.
#   - If Production Plan is not submitted yet, shows message and stops (no auto-start).
# =============================================================================


def fg_skip_auto_start_and_transfer(production_item):
    if not production_item:
        return False
    pi = str(production_item)
    for code in ("102", "103", "104", "107"):
        if code in pi:
            return True
    return False


if doc.production_plan:
    try:
        pp_unit = (frappe.db.get_value("Production Plan", doc.production_plan, "custom_unit") or "").strip().lower()
        skip_auto_start = pp_unit == "lamination unit"
        skip_process_fg = fg_skip_auto_start_and_transfer(doc.production_item)

        item_wh_map = {}
        mr_items = frappe.get_all(
            "Material Request Plan Item",
            filters={"parent": doc.production_plan},
            fields=["item_code", "warehouse"],
        )
        for mr in mr_items or []:
            if mr.get("warehouse") and mr.get("item_code"):
                item_wh_map[mr.item_code] = mr.warehouse

        correct_source_wh = "Raw Materials - JSB-1ZT"
        for wh in item_wh_map.values():
            if wh:
                correct_source_wh = wh
                break

        correct_wip_wh = "Work In Progress - JSB-1ZT"
        correct_fg_wh = "Finished Goods - JSB-1ZT"

        doc.source_warehouse = correct_source_wh
        doc.wip_warehouse = correct_wip_wh
        doc.fg_warehouse = correct_fg_wh

        frappe.db.set_value("Work Order", doc.name, "source_warehouse", doc.source_warehouse, update_modified=False)
        frappe.db.set_value("Work Order", doc.name, "wip_warehouse", doc.wip_warehouse, update_modified=False)
        frappe.db.set_value("Work Order", doc.name, "fg_warehouse", doc.fg_warehouse, update_modified=False)

        for item in doc.get("required_items") or []:
            mapped_wh = item_wh_map.get(item.item_code) or correct_source_wh
            if item.source_warehouse != mapped_wh:
                item.source_warehouse = mapped_wh
                frappe.db.set_value(
                    "Work Order Item",
                    item.name,
                    "source_warehouse",
                    mapped_wh,
                    update_modified=False,
                )

        pp_docstatus = frappe.db.get_value("Production Plan", doc.production_plan, "docstatus")
        if pp_docstatus is None or int(pp_docstatus) != 1:
            frappe.msgprint(
                "Auto-start skipped for Work Order <b>"
                + str(doc.name)
                + "</b> because Production Plan <b>"
                + str(doc.production_plan)
                + "</b> is not submitted yet."
            )
        elif skip_auto_start:
            frappe.msgprint(
                "Auto-start skipped for Work Order <b>"
                + str(doc.name)
                + "</b> because Production Plan Unit is <b>Lamination Unit</b>."
            )
        elif skip_process_fg:
            frappe.msgprint(
                "Auto-start skipped for Work Order <b>"
                + str(doc.name)
                + "</b>: FG item contains process <b>102 / 103 / 104 / 107</b> — submit and start production manually when ready."
            )
        else:
            source_wh = doc.source_warehouse or "Raw Materials - JSB-1ZT"
            shortages = []
            for item in doc.get("required_items") or []:
                required_qty = item.required_qty or 0
                item_wh = item.source_warehouse or source_wh
                actual_qty = frappe.db.get_value(
                    "Bin",
                    {"item_code": item.item_code, "warehouse": item_wh},
                    "actual_qty",
                ) or 0
                if actual_qty < required_qty:
                    shortages.append(
                        "<li><b>"
                        + str(item.item_code)
                        + "</b> — Required: "
                        + str(required_qty)
                        + " "
                        + str(item.stock_uom)
                        + ", Available: "
                        + str(actual_qty)
                        + " "
                        + str(item.stock_uom)
                        + "</li>"
                    )

            if shortages:
                shortage_list = "".join(shortages)
                frappe.msgprint(
                    "Stock shortage for Work Order "
                    + str(doc.name)
                    + ":<br><ul>"
                    + shortage_list
                    + "</ul>",
                    title="Raw Material Warning",
                    indicator="orange",
                )

            if doc.docstatus == 0:
                try:
                    doc.flags.ignore_permissions = True
                    doc.submit()
                    doc.reload()
                except Exception as e:
                    frappe.log_error(title="Doc Submit Error for WO " + str(doc.name), message=str(e))

            if doc.docstatus == 1:
                exists = frappe.db.exists(
                    "Stock Entry",
                    {"work_order": doc.name, "purpose": "Material Transfer for Manufacture"},
                )
                if not exists:
                    se = frappe.new_doc("Stock Entry")
                    se.purpose = "Material Transfer for Manufacture"
                    se.stock_entry_type = "Material Transfer for Manufacture"
                    se.work_order = doc.name
                    se.company = doc.company
                    se.from_warehouse = doc.source_warehouse
                    se.to_warehouse = doc.wip_warehouse
                    se.fg_completed_qty = doc.qty
                    se.use_serial_batch_fields = 1
                    try:
                        se.get_items()
                    except Exception as e:
                        frappe.log_error(title="Stock Entry Pull Error for " + str(doc.name), message=str(e))

                    for sed in se.items or []:
                        if not sed.work_order:
                            sed.work_order = doc.name
                        if not sed.s_warehouse:
                            sed.s_warehouse = item_wh_map.get(sed.item_code) or doc.source_warehouse
                        if not sed.t_warehouse:
                            sed.t_warehouse = doc.wip_warehouse
                        sed.use_serial_batch_fields = 1
                        if not sed.batch_no:
                            has_batch = frappe.db.get_value("Item", sed.item_code, "has_batch_no")
                            if has_batch:
                                batch_rows = frappe.db.sql(
                                    """
                                    SELECT sle.batch_no, SUM(sle.actual_qty) AS qty
                                    FROM `tabStock Ledger Entry` sle
                                    WHERE sle.item_code = %s
                                      AND sle.warehouse = %s
                                      AND sle.is_cancelled = 0
                                      AND sle.batch_no IS NOT NULL
                                      AND sle.batch_no != ''
                                    GROUP BY sle.batch_no
                                    HAVING SUM(sle.actual_qty) > 0
                                    ORDER BY MIN(sle.creation) ASC
                                    LIMIT 1
                                    """,
                                    (sed.item_code, sed.s_warehouse),
                                    as_dict=True,
                                )
                                if batch_rows:
                                    sed.batch_no = batch_rows[0].batch_no
                                else:
                                    fallback = frappe.db.get_value(
                                        "Batch",
                                        {"item": sed.item_code, "disabled": 0},
                                        "name",
                                        order_by="creation asc",
                                    )
                                    if fallback:
                                        sed.batch_no = fallback

                    if not se.items:
                        for row in doc.get("required_items") or []:
                            se.append(
                                "items",
                                {
                                    "item_code": row.item_code,
                                    "qty": row.required_qty,
                                    "transfer_qty": row.required_qty,
                                    "uom": row.stock_uom,
                                    "stock_uom": row.stock_uom,
                                    "s_warehouse": row.source_warehouse or doc.source_warehouse,
                                    "t_warehouse": doc.wip_warehouse,
                                    "conversion_factor": 1,
                                    "work_order": doc.name,
                                },
                            )

                    if se.items:
                        se.flags.ignore_permissions = True
                        try:
                            se.insert()
                            se.submit()
                            doc.reload()
                            frappe.db.set_value(
                                "Work Order",
                                doc.name,
                                {
                                    "material_transferred_for_manufacturing": doc.qty,
                                    "status": "In Process",
                                },
                                update_modified=True,
                            )
                            try:
                                frappe.db.set_value(
                                    "Work Order",
                                    doc.name,
                                    "actual_start_date",
                                    frappe.utils.now_datetime(),
                                    update_modified=True,
                                )
                            except Exception:
                                pass
                            frappe.msgprint("Auto-Started! Stock Entry: <b>" + str(se.name) + "</b>")
                        except Exception as e:
                            frappe.log_error(title="Stock Entry Create Error for " + str(doc.name), message=str(e))
                            frappe.msgprint(
                                "Stock Entry failed for Work Order <b>" + str(doc.name) + "</b>. Check Error Log.",
                                indicator="orange",
                            )
                    else:
                        frappe.msgprint("Warning: No items found to transfer for " + str(doc.name) + ".")
    except Exception as e:
        frappe.log_error(title="Auto Start Error for WO " + str(doc.name), message=str(e))
        frappe.msgprint(
            "Auto-start encountered an error for <b>" + str(doc.name) + "</b>. Verify manually.",
            indicator="orange",
        )
