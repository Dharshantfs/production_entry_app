# SCRIPT: SYNC PRODUCTION PLAN - ITEM LEVEL MAPPING (one po_item per Planning sheet Item row)
# TYPE: API (Server Script)
# METHOD NAME: create_production_plan_from_planning_sheet
#
# Paste into Frappe Server Script (API). Fixes: rows with same item_code/quality/color/unit
# were merged via item_agg — now each ps.items row becomes its own Production Plan Item line.

planning_sheet = frappe.form_dict.get("planning_sheet")
if not planning_sheet:
    frappe.throw("Planning Sheet not provided")

ps = frappe.get_doc("Planning sheet", planning_sheet)

party_code = str(ps.party_code).strip() if ps.party_code else ""
sales_order = str(ps.sales_order).strip() if ps.sales_order else ""
company = frappe.db.get_default("company") or frappe.db.get_value("Global Defaults", None, "default_company")
today = frappe.utils.nowdate()


def _norm_num(v, places=4):
    try:
        return round(float(v or 0), places)
    except Exception:
        return 0.0


def row_pp_group_key(unit, r):
    """Widen key with GSM + width so different physical lines do not share one PP unless you want one PP with many lines."""
    quality = (r.custom_quality or "").strip().upper() or "NO_QUALITY"
    color = (r.color or "").strip().upper() or "NO_COLOR"
    gsm = _norm_num(r.gsm)
    width = _norm_num(r.width_inch)
    return f"{unit}||{quality}||{color}||{gsm}||{width}"


def existing_pp_key_from_doc(pp):
    """Build same shape key as row_pp_group_key for draft PP reuse."""
    ex_unit = (pp.custom_unit or "").strip()
    ex_quality = (pp.custom_quality or "").strip().upper() or "NO_QUALITY"
    ex_color = (pp.custom_color or "").strip().upper() or "NO_COLOR"
    gsm = _norm_num(getattr(pp, "custom_gsm", None))
    width = _norm_num(getattr(pp, "custom_width_", None) or getattr(pp, "custom_width", None))
    return f"{ex_unit}||{ex_quality}||{ex_color}||{gsm}||{width}"


# ========== GROUP FROM OLD TABLE ONLY (ps.items) ==========
group_map = {}
row_to_pp_map = {}

for r in ps.items:
    if not r.unit:
        continue
    units_list = [u.strip() for u in str(r.unit).split(",") if u.strip()]
    for unit in units_list:
        key = row_pp_group_key(unit, r)
        group_map.setdefault(key, []).append((unit, r))  # keep unit with row for header

# ========== FETCH EXISTING PLANS ==========
pp_fields = ["name", "custom_unit", "custom_quality", "custom_color"]
for col in ("custom_gsm", "custom_width_", "custom_width"):
    if frappe.db.has_column("Production Plan", col):
        pp_fields.append(col)

existing_pp = frappe.get_all(
    "Production Plan",
    filters={"custom_planning_sheet": ps.name, "docstatus": 0},
    fields=pp_fields,
)

existing_map = {}
for row in existing_pp:
    pp = frappe.get_doc("Production Plan", row.name)
    existing_map[existing_pp_key_from_doc(pp)] = pp.name

created = []
updated = []
all_pp_list = []

# ========== CREATE / UPDATE PPs ==========
for key, unit_rows in group_map.items():
    # All rows in this group share same unit/quality/color/gsm/width per key — take header from first
    unit_val, first_r = unit_rows[0][0], unit_rows[0][1]
    quality_val = (first_r.custom_quality or "").strip() or ""
    color_val = (first_r.color or "").strip() or ""
    gsm_val = _norm_num(first_r.gsm)
    width_val = _norm_num(first_r.width_inch)

    plan_codes = []
    for _u, r in unit_rows:
        if r.custom_plan_code:
            code = str(r.custom_plan_code).strip()
            if code and code not in plan_codes:
                plan_codes.append(code)

    if key in existing_map:
        pp = frappe.get_doc("Production Plan", existing_map[key])
        pp.flags.ignore_mandatory = True
        pp.set("po_items", [])
        pp.custom_plan_code = ", ".join(plan_codes)
        if frappe.db.has_column("Production Plan", "custom_gsm"):
            pp.custom_gsm = gsm_val
        if frappe.db.has_column("Production Plan", "custom_width_"):
            pp.custom_width_ = width_val
        elif frappe.db.has_column("Production Plan", "custom_width"):
            pp.custom_width = width_val
        updated.append(pp.name)
        all_pp_list.append(pp.name)
    else:
        pp = frappe.new_doc("Production Plan")
        pp.flags.ignore_mandatory = True
        pp.company = company
        pp.posting_date = today
        pp.sales_order = sales_order
        pp.custom_planning_sheet = ps.name
        pp.custom_party_code = party_code
        pp.custom_unit = unit_val
        pp.custom_quality = quality_val
        pp.custom_color = color_val
        if frappe.db.has_column("Production Plan", "custom_gsm"):
            pp.custom_gsm = gsm_val
        if frappe.db.has_column("Production Plan", "custom_width_"):
            pp.custom_width_ = width_val
        elif frappe.db.has_column("Production Plan", "custom_width"):
            pp.custom_width = width_val
        pp.custom_plan_code = ", ".join(plan_codes)
        pp.insert(ignore_permissions=True)
        created.append(pp.name)
        all_pp_list.append(pp.name)

    # ✅ One po_items line per Planning sheet Item row — NO aggregation by item_code
    for _u, r in unit_rows:
        planned_qty = float(r.qty or 0)
        if planned_qty <= 0:
            continue

        row_to_pp_map[r.name] = pp.name
        r.order_sheet = pp.name

        item_code = r.item_code
        bom = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")
        if not bom:
            bom = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1}, "name")
        item_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Kg"

        pp.append(
            "po_items",
            {
                "item_code": item_code,
                "bom_no": bom,
                "planned_qty": planned_qty,
                "uom": item_uom,
                "stock_uom": item_uom,
                "sales_order": sales_order,
                "sales_order_item": str(r.sales_order_item or "").strip(),
                "description": r.description or r.item_name,
                "custom_party_code": party_code,
                "custom_unit": unit_val,
                "custom_quality": quality_val,
                "custom_color": r.color or "",
                "custom_planning_sheet": ps.name,
                "custom_gsm": float(r.gsm or 0),
                "custom_width_": float(r.width_inch or 0),
                "custom_meterperroll": float(r.meter_per_roll or 0),
                "custom_weight_per_roll": float(r.weight_per_roll or 0),
                "custom_no_of_rolls": int(r.no_of_rolls or 0),
            },
        )

    pp.save(ignore_permissions=True)

# ========== SET order_sheet ON NEW TABLE IN MEMORY ==========
pt_items = ps.get("planned_items") or []
for pt in pt_items:
    src = str(pt.source_item or "").strip()
    if src and src in row_to_pp_map:
        pt.order_sheet = row_to_pp_map[src]

# ========== SAVE EVERYTHING ==========
ps.planning_status = "Finalized"
ps.order_sheet = ", ".join(all_pp_list)
ps.save(ignore_permissions=True)

frappe.db.commit()

frappe.response["message"] = {"success": True, "created": created, "updated": updated}
