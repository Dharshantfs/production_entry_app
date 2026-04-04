# SCRIPT: SYNC PRODUCTION PLAN - ITEM LEVEL MAPPING (one po_item per Planning sheet Item row)
# TYPE: API (Server Script)
# METHOD NAME: create_production_plan_from_planning_sheet
#
# Paste into Frappe Server Script (API). safe_exec limitations:
# - NO frappe.db.has_column — use frappe.get_meta(...).has_field(...)
# - NO leading _ on names
# - NO tuple unpacking in for-loops (for a, b in x) — use index access (NameError _unpack_sequence_)
#
# ---------- DO YOU NEED TO "DISABLE" ANYTHING? ----------
# • Do NOT disable the Planning sheet DocType or the form — keep using it normally.
# • Replace the OLD Server Script body with this script (same API method name). Do not keep two
#   different scripts both creating Production Plans for the same sheet, or you risk duplicates.
# • In the app code, PLANNING_SHEET_SUBMIT_LINKS_WORK_ORDERS_ONLY should stay True (default):
#   then Submit on Planning sheet only LINKS Work Orders from existing PPs — it does NOT insert
#   new Production Plans. Flow: run this API first (creates/updates draft PPs) → link PPs on lines
#   if needed → Submit Production Plans → Submit Planning sheet.
# • If that flag were False (legacy), Submit would also try to create PPs — avoid that double path.

planning_sheet = frappe.form_dict.get("planning_sheet")
if not planning_sheet:
    frappe.throw("Planning Sheet not provided")

ps = frappe.get_doc("Planning sheet", planning_sheet)

party_code = str(ps.party_code).strip() if ps.party_code else ""
sales_order = str(ps.sales_order).strip() if ps.sales_order else ""
company = frappe.db.get_default("company") or frappe.db.get_value("Global Defaults", None, "default_company")
today = frappe.utils.nowdate()

# safe_exec: use Meta.has_field — not frappe.db.has_column
pp_meta = frappe.get_meta("Production Plan")


def norm_num(v, places=4):
    try:
        return round(float(v or 0), places)
    except Exception:
        return 0.0


def row_pp_group_key(unit, r):
    """Widen key with GSM + width so different physical lines do not share one PP unless you want one PP with many lines."""
    quality = (r.custom_quality or "").strip().upper() or "NO_QUALITY"
    color = (r.color or "").strip().upper() or "NO_COLOR"
    gsm = norm_num(r.gsm)
    width = norm_num(r.width_inch)
    return f"{unit}||{quality}||{color}||{gsm}||{width}"


def existing_pp_key_from_doc(pp):
    """Build same shape key as row_pp_group_key for draft PP reuse."""
    ex_unit = (pp.custom_unit or "").strip()
    ex_quality = (pp.custom_quality or "").strip().upper() or "NO_QUALITY"
    ex_color = (pp.custom_color or "").strip().upper() or "NO_COLOR"
    gsm = norm_num(getattr(pp, "custom_gsm", None))
    width = norm_num(getattr(pp, "custom_width_", None) or getattr(pp, "custom_width", None))
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
    if pp_meta.has_field(col):
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
for key in group_map:
    unit_rows = group_map[key]
    # All rows in this group share same unit/quality/color/gsm/width per key — take header from first
    first_pair = unit_rows[0]
    unit_val = first_pair[0]
    first_r = first_pair[1]
    quality_val = (first_r.custom_quality or "").strip() or ""
    color_val = (first_r.color or "").strip() or ""
    gsm_val = norm_num(first_r.gsm)
    width_val = norm_num(first_r.width_inch)

    plan_codes = []
    for ri in range(len(unit_rows)):
        pair = unit_rows[ri]
        unit_token = pair[0]
        r = pair[1]
        if r.custom_plan_code:
            code = str(r.custom_plan_code).strip()
            if code and code not in plan_codes:
                plan_codes.append(code)

    if key in existing_map:
        pp = frappe.get_doc("Production Plan", existing_map[key])
        pp.flags.ignore_mandatory = True
        pp.set("po_items", [])
        pp.custom_plan_code = ", ".join(plan_codes)
        if pp_meta.has_field("custom_gsm"):
            pp.custom_gsm = gsm_val
        if pp_meta.has_field("custom_width_"):
            pp.custom_width_ = width_val
        elif pp_meta.has_field("custom_width"):
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
        if pp_meta.has_field("custom_gsm"):
            pp.custom_gsm = gsm_val
        if pp_meta.has_field("custom_width_"):
            pp.custom_width_ = width_val
        elif pp_meta.has_field("custom_width"):
            pp.custom_width = width_val
        pp.custom_plan_code = ", ".join(plan_codes)
        pp.insert(ignore_permissions=True)
        created.append(pp.name)
        all_pp_list.append(pp.name)

    # ✅ One po_items line per Planning sheet Item row — NO aggregation by item_code
    for ri in range(len(unit_rows)):
        pair = unit_rows[ri]
        unit_token = pair[0]
        r = pair[1]
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
ps.order_sheet = ", ".join(sorted(set(all_pp_list)))
ps.save(ignore_permissions=True)

frappe.db.commit()

frappe.response["message"] = {"success": True, "created": created, "updated": updated}
