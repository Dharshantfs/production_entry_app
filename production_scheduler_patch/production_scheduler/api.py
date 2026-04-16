import frappe
from frappe import _
from frappe.utils import getdate, flt, cint
import json
import re
import datetime

from production_entry.production_planning.planning_doctypes import normalize_planning_unit_for_select

# Party / order code auto-generation (MonthLetter+YY+NNN + SO writeback).
# Set True to enable; False disables all calls (no codes generated, no SO writeback from this path).
PARTY_CODE_GENERATION_ENABLED = False

# Lamination: SO lines with item 104 (laminated FG) get a paired fabric (100*) row from BOM on the same Planning sheet.
# Board filter only applies when callers pass board_process_scope (see get_color_chart_data).
LAMINATION_FLOW_ENABLED = True


def _item_process_prefix(item_code):
	ic = (item_code or "").strip()
	return ic[:3] if len(ic) >= 3 else ""


@frappe.whitelist()
def get_fabric_item_from_laminated_item(lam_item_code):
	"""
	Resolve the single fabric FG (item code prefix 100) from the laminated item's active BOM.
	Returns {"fabric_item_code", "bom_no"}. Raises with a clear message if invalid.
	"""
	lam_item_code = (lam_item_code or "").strip()
	if len(lam_item_code) < 3:
		frappe.throw(_("Item code is too short to read process prefix (need at least 3 characters)."))
	if _item_process_prefix(lam_item_code) != "104":
		frappe.throw(
			_("Lamination item must have process code 104 in item code (first 3 digits). Got: {0}").format(
				_item_process_prefix(lam_item_code) or "—"
			)
		)
	if not frappe.db.exists("Item", lam_item_code):
		frappe.throw(_("Item {0} does not exist.").format(lam_item_code))

	bom_name = frappe.db.get_value(
		"BOM",
		{"item": lam_item_code, "docstatus": 1, "is_active": 1, "is_default": 1},
		"name",
		order_by="modified desc",
	)
	if not bom_name:
		bom_name = frappe.db.get_value(
			"BOM",
			{"item": lam_item_code, "docstatus": 1, "is_active": 1},
			"name",
			order_by="is_default desc, modified desc",
		)
	if not bom_name:
		frappe.throw(_("No active submitted BOM for laminated item {0}.").format(lam_item_code))

	bom = frappe.get_doc("BOM", bom_name)
	fabric_rows = []
	for row in bom.items or []:
		ic = (row.item_code or "").strip()
		if len(ic) >= 3 and ic[:3] == "100":
			fabric_rows.append((ic, row))

	if len(fabric_rows) == 0:
		frappe.throw(
			_("BOM {0} has no fabric FG row (item code must start with 100). Fix BOM for {1}.").format(
				bom_name, lam_item_code
			)
		)
	if len(fabric_rows) > 1:
		codes = ", ".join([f[0] for f in fabric_rows])
		frappe.throw(
			_("BOM {0} has multiple fabric components (100): {1}. Keep exactly one fabric FG.").format(bom_name, codes)
		)

	fabric_item_code = fabric_rows[0][0]
	if not frappe.db.exists("Item", fabric_item_code):
		frappe.throw(_("Fabric item {0} from BOM does not exist.").format(fabric_item_code))

	return {"fabric_item_code": fabric_item_code, "bom_no": bom_name}


def _fabric_qty_from_bom(bom_name, fabric_item_code, lamination_so_qty):
	"""Lamination SO qty (FG) -> required fabric qty using BOM line qty / BOM quantity."""
	bom = frappe.get_doc("BOM", bom_name)
	fg_qty = flt(bom.quantity) or 1.0
	if fg_qty <= 0:
		fg_qty = 1.0
	lamination_so_qty = flt(lamination_so_qty) or 0
	for row in bom.items or []:
		if (row.item_code or "").strip() == fabric_item_code:
			return flt(lamination_so_qty) * flt(row.qty) / fg_qty
	return lamination_so_qty


def _sync_lamination_fabric_planning_rows(planning_sheet_name):
	"""For each SO line with item 104, append one fabric (100) row to legacy items + board table. Idempotent."""
	if not LAMINATION_FLOW_ENABLED or not planning_sheet_name:
		return
	if not frappe.db.exists("Planning sheet", planning_sheet_name):
		return
	ps = frappe.get_doc("Planning sheet", planning_sheet_name)
	if not ps.get("sales_order"):
		return
	so = frappe.get_doc("Sales Order", ps.sales_order)
	parent_field = _get_pt_parentfield()
	changed = False
	for so_it in so.items or []:
		lam_ic = (so_it.item_code or "").strip()
		if _item_process_prefix(lam_ic) != "104":
			continue
		try:
			res = get_fabric_item_from_laminated_item(lam_ic)
		except Exception as e:
			frappe.log_error(
				title="Lamination fabric BOM",
				message=f"SO {so.name} line {so_it.name}: {e}\n{frappe.get_traceback()}",
			)
			frappe.msgprint(
				_("Lamination fabric row skipped for {0}: {1}").format(lam_ic, str(e)),
				indicator="orange",
			)
			continue
		fabric_ic = res["fabric_item_code"]
		bom_no = res["bom_no"]
		fabric_qty = _fabric_qty_from_bom(bom_no, fabric_ic, flt(so_it.qty))

		existing = frappe.get_all(
			"Planning Table",
			filters={"parent": ps.name, "item_code": fabric_ic, "so_item": so_it.name},
			pluck="name",
			limit=1,
		)
		if existing:
			continue

		lam_match = frappe.get_all(
			"Planning Table",
			filters={"parent": ps.name, "sales_order_item": so_it.name, "item_code": lam_ic},
			fields=["name"],
			limit=1,
		)
		lam_pt_name = lam_match[0].get("name") if lam_match else None
		lam_row = frappe.get_doc("Planning Table", lam_pt_name) if lam_pt_name else None

		fabric_item_name = frappe.db.get_value("Item", fabric_ic, "item_name") or ""
		specs = _fabric_row_specs_from_fabric_item(fabric_ic, so_it, lam_row)
		row = {
			"sales_order_item": "",
			"item_code": fabric_ic,
			"item_name": fabric_item_name,
			"qty": fabric_qty,
			"uom": so_it.uom,
			"gsm": specs["gsm"],
			"width_inch": specs["width_inch"],
			"color": specs["color"],
			"quality": specs["quality"],
			"custom_quality": specs["custom_quality"],
			"unit": "Lamination Unit",
			"meter": specs["meter"],
			"meter_per_roll": specs["meter_per_roll"],
			"no_of_rolls": specs["no_of_rolls"],
			"weight_per_roll": specs["weight_per_roll"],
			"planned_date": lam_row.get("planned_date") if lam_row else None,
			"plan_name": lam_row.get("plan_name") if lam_row else ps.get("custom_plan_name"),
			"party_code": ps.party_code,
			"planning_sheet": ps.name,
			"so_item": so_it.name,
		}
		if lam_pt_name and frappe.db.has_column("Planning Table", "split_from"):
			row["split_from"] = lam_pt_name

		row_b = dict(row)
		if hasattr(ps, "items") or ps.meta.has_field("items"):
			ps.append("items", row_b)
		ps.append(parent_field, dict(row))
		changed = True

	if changed:
		ps.flags.ignore_permissions = True
		ps.save()
		frappe.db.commit()


def _link_board_planned_rows_to_legacy_items(planning_sheet_name):
	"""Set Planning Table `source_item` from legacy Planning sheet Item rows (1:1 by idx)."""
	if not planning_sheet_name or not frappe.db.exists("Planning sheet", planning_sheet_name):
		return
	final_doc = frappe.get_doc("Planning sheet", planning_sheet_name)
	legacy_rows = sorted((final_doc.get("items") or []), key=lambda x: x.idx)
	board_rows = []
	for field in (
		"planned_items",
		"planning_table",
		"custom_planned_items",
		"custom_planning_table",
		"table",
	):
		br = final_doc.get(field) or []
		if br:
			board_rows = sorted(br, key=lambda x: x.idx)
			break
	if legacy_rows and board_rows and len(legacy_rows) == len(board_rows):
		for i in range(len(legacy_rows)):
			board_rows[i].source_item = legacy_rows[i].name
			board_rows[i].db_update()


def _resolve_customer_link(raw_customer, party_code=None):
    """Return a valid Customer docname for link-field assignments."""
    if not raw_customer:
        if party_code and frappe.db.exists("Customer", party_code):
            return party_code
        return ""

    raw_customer = str(raw_customer).strip()
    if not raw_customer:
        return ""

    if frappe.db.exists("Customer", raw_customer):
        return raw_customer

    by_name = frappe.db.get_value("Customer", {"customer_name": raw_customer}, "name")
    if by_name:
        return by_name

    if party_code and frappe.db.exists("Customer", party_code):
        return party_code

    return ""


def _get_pt_parentfield():
    """Return the correct parentfield for Planning Table rows on Planning Sheet.
    The form field linking to Planning Table is NOT 'items' (that's the old table).
    """
    meta = frappe.get_meta("Planning sheet")
    for field in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
        if meta.has_field(field):
            df = meta.get_field(field)
            if df and getattr(df, "options", "") == "Planning Table":
                return field
    return "planned_items"


def _repair_child_table_schema(target_doctypes=None):
    """Ensure required child-table columns exist for istable DocTypes."""
    required = {
        "parent": "VARCHAR(140)",
        "parenttype": "VARCHAR(140)",
        "parentfield": "VARCHAR(140)",
        "idx": "INT NOT NULL DEFAULT 0",
    }
    repaired = []

    if target_doctypes:
        doctypes = [d for d in target_doctypes if d and frappe.db.exists("DocType", d)]
    else:
        doctypes = frappe.get_all(
            "DocType",
            filters={"istable": 1},
            pluck="name",
        ) or []

    for dt in doctypes:
        try:
            table_cols = set(frappe.db.get_table_columns(dt) or [])
        except Exception:
            # Table may be missing or not synced yet; skip safely.
            continue
        missing = [c for c in required if c not in table_cols]
        if not missing:
            continue
        for col in missing:
            frappe.db.sql(f"ALTER TABLE `tab{dt}` ADD COLUMN `{col}` {required[col]}")
        repaired.append({"doctype": dt, "added": missing})

    if repaired:
        frappe.db.commit()
    return repaired


def ensure_child_table_schema_for_planning_cancel(doc=None, method=None):
    """
    Defensive repair before Planning Sheet cancel flow.
    Prevents 'Unknown column parenttype' from linked_with traversal.
    """
    try:
        _repair_child_table_schema()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ensure_child_table_schema_for_planning_cancel failed")


@frappe.whitelist()
def repair_child_table_schema_now():
    """Manual schema repair utility for child-table metadata drift."""
    frappe.only_for("System Manager")
    return _repair_child_table_schema()


def _sync_generated_order_code_to_sales_order(so_name, party_code):
    """Write planning-sheet party code (order code) back to Sales Order."""
    if not so_name or not party_code:
        return
    if frappe.db.has_column("Sales Order", "custom_party_code"):
        frappe.db.set_value("Sales Order", so_name, "custom_party_code", party_code, update_modified=True)
    elif frappe.db.has_column("Sales Order", "party_code"):
        frappe.db.set_value("Sales Order", so_name, "party_code", party_code, update_modified=True)
    if frappe.db.has_column("Sales Order", "custom_order_code"):
        cur_oc = frappe.db.get_value("Sales Order", so_name, "custom_order_code")
        if not (cur_oc or "").strip():
            frappe.db.set_value("Sales Order", so_name, "custom_order_code", party_code, update_modified=True)


def generate_party_code(doc):
    """
    Generate or reuse party_code (order code) for Planning sheet / Sales Order.
    Format: {MonthLetter}{YY}{NNN} e.g. C26 means March (C) + year 26 + 3-digit series.
    Reuses existing code from SO or another Planning sheet for the same SO when present.
    """
    if not PARTY_CODE_GENERATION_ENABLED:
        return

    # Identify Sales Order reference correctly
    so_ref = doc.name if doc.doctype == "Sales Order" else doc.get('sales_order')
    
    # Try to reuse existing party_code from Sales Order itself or another Planning Sheet
    existing_party_code = None
    if so_ref:
        # 1. Look in Sales Order database
        existing_party_code = frappe.db.get_value("Sales Order", so_ref, "custom_party_code") if frappe.db.has_column("Sales Order", "custom_party_code") else frappe.db.get_value("Sales Order", so_ref, "party_code") if frappe.db.has_column("Sales Order", "party_code") else None
        
        # 2. Look in other Planning Sheets for the same SO
        if not existing_party_code:
            existing_party_code = frappe.db.get_value(
                "Planning sheet",
                {"sales_order": so_ref, "party_code": ["!=" , ""], "docstatus": ["<", 2]},
                "party_code",
            )
            
    if existing_party_code:
        doc.party_code = existing_party_code
    else:
        # Generate new code based on year and month
        row = frappe.db.sql("""
            SELECT DATE_FORMAT(NOW(), '%y') AS yy,
                   MONTH(NOW()) AS mm
        """, as_dict=1)[0]
        yy = row["yy"]
        mm = int(row["mm"])
        month_map = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H", 9: "I", 10: "J", 11: "K", 12: "L"}
        mcode = month_map.get(mm, "A")
        prefix = mcode + yy
        last_code = frappe.db.sql("""
            SELECT party_code
            FROM `tabPlanning sheet`
            WHERE party_code LIKE %(prefix)s
            ORDER BY CAST(SUBSTRING(party_code, %(offset)s) AS UNSIGNED) DESC
            LIMIT 1
        """, {"prefix": prefix + "%", "offset": len(prefix) + 1}, as_dict=1)
        series = 1
        if last_code:
            try:
                series = int(last_code[0]["party_code"][len(prefix):]) + 1
            except Exception:
                series = 1
        s = str(series).zfill(3)
        doc.party_code = prefix + s

    # Persist back to Sales Order if generated from SO doc
    if doc.doctype == "Sales Order" and doc.name and doc.party_code:
        _sync_generated_order_code_to_sales_order(doc.name, doc.party_code)
    # Copy to child items if any
    if doc.get("items"):
        for item_row in doc.items:
            item_row.party_code = doc.party_code
    # Planning sheet: write order code back to linked Sales Order after party_code is set
    if doc.doctype == "Planning sheet" and doc.get("sales_order") and doc.get("party_code"):
        _sync_generated_order_code_to_sales_order(doc.sales_order, doc.party_code)


@frappe.whitelist()
def reset_party_code_series(clear_sales_order_mirror_fields=0):
    """
    System Manager only: clear stored party_code on active Planning sheets so the numeric
    series restarts at 001 for the current month prefix when PARTY_CODE_GENERATION_ENABLED is True again.

    Does not enable generation — set PARTY_CODE_GENERATION_ENABLED = True in code after reset.

    If clear_sales_order_mirror_fields=1, also clears custom_party_code / party_code / custom_order_code
    on Sales Order (destructive — use only if mirrors were filled by auto-generation).
    """
    frappe.only_for("System Manager")
    clear_sales_order_mirror_fields = cint(clear_sales_order_mirror_fields)

    cleared_ps = frappe.db.count(
        "Planning sheet",
        {"docstatus": ["<", 2], "party_code": ["!=", ""]},
    )
    frappe.db.sql(
        """
        UPDATE `tabPlanning sheet`
        SET party_code = NULL
        WHERE docstatus < 2
          AND IFNULL(party_code, '') != ''
        """
    )

    cleared_so = 0
    if clear_sales_order_mirror_fields:
        if frappe.db.has_column("Sales Order", "custom_party_code"):
            cleared_so += frappe.db.count(
                "Sales Order",
                {"docstatus": ["<", 2], "custom_party_code": ["!=", ""]},
            )
            frappe.db.sql(
                "UPDATE `tabSales Order` SET custom_party_code = NULL WHERE docstatus < 2 AND IFNULL(custom_party_code, '') != ''"
            )
        if frappe.db.has_column("Sales Order", "party_code"):
            frappe.db.sql(
                "UPDATE `tabSales Order` SET party_code = NULL WHERE docstatus < 2 AND IFNULL(party_code, '') != ''"
            )
        if frappe.db.has_column("Sales Order", "custom_order_code"):
            frappe.db.sql(
                "UPDATE `tabSales Order` SET custom_order_code = NULL WHERE docstatus < 2 AND IFNULL(custom_order_code, '') != ''"
            )

    frappe.db.commit()
    return {
        "status": "success",
        "party_code_generation_enabled": PARTY_CODE_GENERATION_ENABLED,
        "planning_sheets_updated": cleared_ps,
        "sales_orders_cleared": bool(clear_sales_order_mirror_fields),
        "message": "Series baseline cleared on Planning sheets. Set PARTY_CODE_GENERATION_ENABLED = True in api.py to start fresh from 001.",
    }


@frappe.whitelist()
def get_color_chart_data(
    date=None,
    start_date=None,
    end_date=None,
    plan_name=None,
    mode=None,
    planned_only=0,
    board_process_scope=None,
):
    """Safe wrapper to avoid UI 502s; logs root cause."""
    try:
        return _get_color_chart_data_impl(
            date=date,
            start_date=start_date,
            end_date=end_date,
            plan_name=plan_name,
            mode=mode,
            planned_only=planned_only,
            board_process_scope=board_process_scope,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_color_chart_data_error")
        return []


def _find_existing_sheet_for_sales_order(sales_order, exclude_name=None):
    """Return the oldest existing Planning Sheet for a Sales Order, or None."""
    so = str(sales_order or "").strip()
    if not so:
        return None

    filters = {"sales_order": so}
    if exclude_name:
        filters["name"] = ["!=", exclude_name]

    existing = frappe.get_all(
        "Planning sheet",
        filters=filters,
        fields=["name", "docstatus", "creation"],
        order_by="creation asc",
        limit=1,
    )
    return existing[0] if existing else None


def _production_plan_usable(pp_name):
    """Return pp_name if document exists and is not cancelled; else None."""
    if not pp_name or not str(pp_name).strip():
        return None
    pp_name = str(pp_name).strip()
    if not frappe.db.exists("Production Plan", pp_name):
        return None
    if frappe.db.get_value("Production Plan", pp_name, "docstatus") == 2:
        return None
    return pp_name


def _resolve_existing_production_plan_for_planning_sheet(sheet_name):
    """
    If this Planning sheet already has a Production Plan, return its name so callers
    do not create duplicate PP rows for the same sheet (repeated "Create Plan" clicks).
    Order: header link → first item-level link → PP.custom_planning_sheet / planning_sheet.
    """
    if not sheet_name or not frappe.db.exists("Planning sheet", sheet_name):
        return None

    for col in ("custom_production_plan", "production_plan", "production_plan_id", "pp_id"):
        if frappe.db.has_column("Planning sheet", col):
            pp = _production_plan_usable(frappe.db.get_value("Planning sheet", sheet_name, col))
            if pp:
                return pp

    for fieldname in _psi_production_plan_fields():
        rows = frappe.get_all(
            "Planning Table",
            filters={"parent": sheet_name},
            fields=[fieldname],
            limit=50,
        )
        for r in rows:
            pp = _production_plan_usable(r.get(fieldname))
            if pp:
                return pp

    for col in ("custom_planning_sheet", "planning_sheet"):
        if not frappe.db.has_column("Production Plan", col):
            continue
        rows = frappe.get_all(
            "Production Plan",
            filters={col: sheet_name, "docstatus": ["!=", 2]},
            fields=["name"],
            order_by="creation desc",
            limit_page_length=1,
        )
        if rows:
            return rows[0].name

    # Last resort: exactly one submitted PP for this sheet's Sales Order (e.g. PP created/submitted
    # from Manufacturing before Planning sheet stored custom_production_plan — avoids a second PP on finalize).
    so = frappe.db.get_value("Planning sheet", sheet_name, "sales_order")
    if so:
        pp_so = _single_submitted_production_plan_for_sales_order_when_unique(so)
        if pp_so:
            return _production_plan_usable(pp_so)

    return None


def _single_submitted_production_plan_for_sales_order_when_unique(sales_order):
    """If exactly one submitted Production Plan has po_items for this Sales Order, return its name."""
    if not sales_order:
        return None
    if not frappe.db.has_column("Production Plan Item", "sales_order"):
        return None
    rows = frappe.db.sql(
        """
        SELECT DISTINCT pp.name
        FROM `tabProduction Plan` pp
        INNER JOIN `tabProduction Plan Item` ppi ON ppi.parent = pp.name
        WHERE pp.docstatus = 1 AND IFNULL(ppi.sales_order, '') = %s
        """,
        (sales_order,),
        as_dict=True,
    )
    names = [r["name"] for r in rows]
    if len(names) == 1:
        return names[0]
    return None


def _psi_production_plan_fields():
    """Return available Planning Table fields that may store item-level Production Plan links."""
    candidates = [
        "custom_production_plan",
        "production_plan",
        "custom_production_plan_id",
        "custom_order_sheet",
        "order_sheet",
        "custom_order_plan",
    ]
    return [f for f in candidates if frappe.db.has_column("Planning Table", f)]


def _psi_production_plan_field():
    """Return the primary Planning Sheet Item field used for writing item-level Production Plan links."""
    fields = _psi_production_plan_fields()
    return fields[0] if fields else None


def _psi_order_sheet_field():
    """Return optional Planning Sheet Item field used to store row-level order-sheet/PP reference."""
    for f in ["custom_order_sheet", "order_sheet", "custom_order_plan"]:
        if frappe.db.has_column("Planning Table", f):
            return f
    return None


def _get_item_level_production_plan(item_name):
    """Read item-level Production Plan link using all known candidate fields."""
    if not item_name:
        return None

    for fieldname in _psi_production_plan_fields():
        pp = frappe.db.get_value("Planning Table", item_name, fieldname)
        if not pp and frappe.db.has_column("Planning sheet Item", fieldname):
            pp = frappe.db.get_value("Planning sheet Item", item_name, fieldname)
        if pp:
            return pp
    return None


def _collect_all_production_plans_for_planning_sheet(sheet_name):
    """Return distinct Production Plan names linked to this Planning sheet (header, lines, reverse link)."""
    if not sheet_name:
        return []
    names = set()
    for col in ("custom_production_plan", "production_plan", "production_plan_id", "pp_id"):
        if frappe.db.has_column("Planning sheet", col):
            v = frappe.db.get_value("Planning sheet", sheet_name, col)
            if v:
                names.add(v)
    for row in frappe.get_all("Planning sheet Item", filters={"parent": sheet_name}, fields=["name"]):
        pp = _get_item_level_production_plan(row.name)
        if pp:
            names.add(pp)
    for col in ("custom_planning_sheet", "planning_sheet"):
        if not frappe.db.has_column("Production Plan", col):
            continue
        for r in frappe.get_all("Production Plan", filters={col: sheet_name}, fields=["name"]):
            names.add(r.name)
    return [n for n in names if _production_plan_usable(n)]


def _planning_sheets_referencing_production_plan(pp_name):
    """Planning sheet document names that reference this Production Plan (header, board row, or reverse)."""
    sheets = set()
    pp_name = (pp_name or "").strip()
    if not pp_name:
        return []
    for col in ("custom_planning_sheet", "planning_sheet"):
        if not frappe.db.has_column("Production Plan", col):
            continue
        v = frappe.db.get_value("Production Plan", pp_name, col)
        if v:
            sheets.add(v)
    for col in ("custom_production_plan", "production_plan", "production_plan_id", "pp_id"):
        if frappe.db.has_column("Planning sheet", col):
            for r in frappe.get_all("Planning sheet", filters={col: pp_name}, fields=["name"]):
                sheets.add(r.name)
    for fieldname in _psi_production_plan_fields():
        for r in frappe.get_all("Planning Table", filters={fieldname: pp_name}, fields=["parent"]):
            if r.parent:
                sheets.add(r.parent)
        if frappe.db.has_column("Planning sheet Item", fieldname):
            for r in frappe.get_all("Planning sheet Item", filters={fieldname: pp_name}, fields=["parent"]):
                if r.parent:
                    sheets.add(r.parent)
    return list(sheets)


def _planning_sheet_all_linked_production_plans_submitted(sheet_name):
    """True if every Production Plan linked to the sheet exists and is submitted (docstatus 1)."""
    pps = _collect_all_production_plans_for_planning_sheet(sheet_name)
    if not pps:
        return False
    for pp in pps:
        if cint(frappe.db.get_value("Production Plan", pp, "docstatus")) != 1:
            return False
    return True


def on_production_plan_submitted(doc, method=None):
    """Link Work Orders onto Planning sheet items when a PP is submitted; auto-submit Planning sheet when all PPs are."""
    pp_name = doc.name if doc else None
    if not pp_name:
        return
    try:
        for sheet_name in _planning_sheets_referencing_production_plan(pp_name):
            if not frappe.db.exists("Planning sheet", sheet_name):
                continue
            ps = frappe.get_doc("Planning sheet", sheet_name)
            ps.link_work_orders_for_production_plan(pp_name)
            if cint(frappe.db.get_value("Planning sheet", sheet_name, "docstatus")) != 0:
                continue
            if _planning_sheet_all_linked_production_plans_submitted(sheet_name):
                frappe.flags.ignore_permissions = True
                try:
                    frappe.get_doc("Planning sheet", sheet_name).submit()
                finally:
                    frappe.flags.ignore_permissions = False
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"on_production_plan_submitted: {pp_name}")


def _resolve_pp_by_sales_order_item(sales_order_item):
    """Find latest submitted Production Plan linked to a Sales Order Item."""
    so_item = str(sales_order_item or "").strip()
    if not so_item:
        return None

    so_item_col = None
    if frappe.db.has_column("Production Plan Item", "sales_order_item"):
        so_item_col = "sales_order_item"
    elif frappe.db.has_column("Production Plan Item", "custom_sales_order_item"):
        so_item_col = "custom_sales_order_item"

    if not so_item_col:
        return None

    rows = frappe.db.sql(
        f"""
        SELECT DISTINCT pp.name
        FROM `tabProduction Plan` pp
        INNER JOIN `tabProduction Plan Item` ppi ON ppi.parent = pp.name
        WHERE pp.docstatus = 1
          AND COALESCE(ppi.{so_item_col}, '') = %s
        ORDER BY pp.creation DESC
        LIMIT 1
        """,
        (so_item,),
        as_dict=True,
    )
    return rows[0]["name"] if rows else None



# --- DEFINITIONS ---
PREMIUM_SPECIAL_QUALITIES = [
    "PREMIUM - HYDROPHOBIC",
    "PREMIUM - FR BS5867II PART 2 TYPE B",
    "PREMIUM - FR + ANTI MICROBIAL",
    "PREMIUM - FR FMV SS 302",
    "PREMIUM - HYDROPHILIC",
    "PREMIUM - UV",
]

UNIT_1 = ["PREMIUM", "PLATINUM", "SUPER PLATINUM", "GOLD", "SILVER"] + PREMIUM_SPECIAL_QUALITIES
UNIT_2 = ["GOLD", "SILVER", "BRONZE", "CLASSIC", "SUPER CLASSIC", "LIFE STYLE", "ECO SPECIAL", "ECO GREEN", "SUPER ECO", "ULTRA", "DELUXE"] + PREMIUM_SPECIAL_QUALITIES
UNIT_3 = ["PREMIUM", "PLATINUM", "SUPER PLATINUM", "GOLD", "SILVER", "BRONZE"] + PREMIUM_SPECIAL_QUALITIES
UNIT_4 = ["PREMIUM", "PLATINUM", "GOLD", "SILVER", "BRONZE", "CLASSIC", "CRT"] + PREMIUM_SPECIAL_QUALITIES

QUAL_LIST = ["SUPER PLATINUM", "SUPER CLASSIC", "SUPER ECO", "ECO SPECIAL", "ECO GREEN",
             "ECO SPL", "LIFE STYLE", "LIFESTYLE", "PREMIUM", "PLATINUM", "CLASSIC", "CRT",
             "DELUXE", "BRONZE", "SILVER", "ULTRA", "GOLD", "UV"] + PREMIUM_SPECIAL_QUALITIES
QUAL_LIST.sort(key=len, reverse=True)

def _normalize_quality_key(text):
    return re.sub(r"[^A-Z0-9]+", "", str(text or "").upper())

COL_LIST = ["BRIGHT WHITE", "SUPER WHITE", "MILKY WHITE", "SUNSHINE WHITE", "BLEACH WHITE", "BLEACH WHITE 1.0", "BLEACH WHITE 2.0", "WHITE MIX", "WHITE","BRIGHT IVORY","CREAM 2.0", "CREAM 3.0", "CREAM 4.0", "CREAM 5.0", "GOLDEN YELLOW 4.0 SPL", "GOLDEN YELLOW 1.0", "GOLDEN YELLOW 2.0", "GOLDEN YELLOW 3.0", "GOLDEN YELLOW", "LEMON YELLOW 1.0", "LEMON YELLOW 3.0", "LEMON YELLOW", "BRIGHT ORANGE", "DARK ORANGE", "ORANGE 2.0", "PINK 7.0 DARK", "PINK 6.0 DARK", "DARK PINK", "BABY PINK", "PINK 1.0", "PINK 2.0", "PINK 3.0", "PINK 5.0", "CRIMSON RED", "RED", "LIGHT MAROON", "DARK MAROON", "MAROON 1.0", "MAROON 2.0", "BLUE 13.0 INK BLUE", "BLUE 12.0 SPL NAVY BLUE", "BLUE 11.0 NAVY BLUE", "BLUE 8.0 DARK ROYAL BLUE", "BLUE 7.0 DARK BLUE", "BLUE 6.0 ROYAL BLUE", "LIGHT PEACOCK BLUE", "PEACOCK BLUE", "LIGHT MEDICAL BLUE", "MEDICAL BLUE", "ROYAL BLUE", "NAVY BLUE", "SKY BLUE", "LIGHT BLUE", "BLUE 9.0", "BLUE 4.0", "BLUE 2.0", "BLUE 1.0", "BLUE", "PURPLE 4.0 BLACKBERRY", "PURPLE 1.0", "PURPLE 2.0", "PURPLE 3.0", "VIOLET", "VOILET", "GREEN 13.0 ARMY GREEN", "GREEN 12.0 OLIVE GREEN", "GREEN 11.0 DARK GREEN", "GREEN 10.0", "GREEN 9.0 BOTTLE GREEN", "GREEN 8.0 APPLE GREEN", "GREEN 7.0", "GREEN 6.0", "GREEN 5.0 GRASS GREEN", "GREEN 4.0", "GREEN 3.0 RELIANCE GREEN", "GREEN 2.0 TORQUISE GREEN", "GREEN 1.0 MINT", "MEDICAL GREEN", "RELIANCE GREEN", "PARROT GREEN", "GREEN", "SILVER 1.0", "SILVER 2.0", "LIGHT GREY", "DARK GREY", "GREY 1.0", "CHOCOLATE BROWN 2.0", "CHOCOLATE BROWN", "CHOCOLATE BLACK", "BROWN 3.0 DARK COFFEE", "BROWN 2.0 DARK", "BROWN 1.0", "CHIKOO 1.0", "CHIKOO 2.0", "BEIGE 1.0", "BEIGE 2.0", "BEIGE 3.0", "BEIGE 4.0", "BEIGE 5.0", "LIGHT BEIGE", "DARK BEIGE", "BEIGE MIX", "BLACK MIX", "COLOR MIX", "BLACK"]
COL_LIST.sort(key=len, reverse=True)


def _parse_gsm_width_from_item_text(raw_text):
	"""Parse GSM and width (inch) from item code + item name (same token rules as SO line populate)."""
	if not raw_text:
		return 0, 0.0
	clean_txt = raw_text.upper().replace("-", " ").replace("_", " ").replace("(", " ").replace(")", " ")
	clean_txt = clean_txt.replace("''", " INCH ").replace('"', " INCH ")
	words = clean_txt.split()
	gsm = 0
	for i, w in enumerate(words):
		if w == "GSM" and i > 0 and words[i - 1].isdigit():
			gsm = int(words[i - 1])
			break
		elif w.endswith("GSM") and len(w) > 3 and w[:-3].isdigit():
			gsm = int(w[:-3])
			break
	width = 0.0
	for i, w in enumerate(words):
		if w == "W" and i < len(words) - 1 and words[i + 1].replace(".", "", 1).isdigit():
			width = float(words[i + 1])
			break
		elif w.startswith("W") and len(w) > 1 and w[1:].replace(".", "", 1).isdigit():
			width = float(w[1:])
			break
		elif w == "INCH" and i > 0 and words[i - 1].replace(".", "", 1).isdigit():
			width = float(words[i - 1])
			break
		elif w.endswith("INCH") and len(w) > 4 and w[:-4].replace(".", "", 1).isdigit():
			width = float(w[:-4])
			break
	return gsm, width


def _fabric_row_specs_from_fabric_item(fabric_ic, so_it, lam_row):
	"""
	GSM, width, colour, quality for the fabric line — from fabric Item only (never lamination row).
	Reuses the same extraction rules as _populate_planning_sheet_items for 100* items.
	"""
	quality_lookup = list(QUAL_LIST)
	try:
		qm_names = frappe.get_all("Quality Master", pluck="name") or []
		for qn in qm_names:
			qn_up = str(qn or "").upper().strip()
			if qn_up and qn_up not in quality_lookup:
				quality_lookup.append(qn_up)
	except Exception:
		pass
	quality_lookup.sort(key=len, reverse=True)

	item_name = frappe.db.get_value("Item", fabric_ic, "item_name") or ""
	raw_txt = f"{fabric_ic} {item_name}"
	gsm, width = _parse_gsm_width_from_item_text(raw_txt)
	for col in ("custom_gsm", "gsm"):
		if frappe.db.has_column("Item", col):
			try:
				v = frappe.db.get_value("Item", fabric_ic, col)
				if v is not None and flt(v) > 0:
					gsm = cint(v)
					break
			except Exception:
				pass
	for col in ("custom_width_inch", "width_inch", "custom_width"):
		if frappe.db.has_column("Item", col):
			try:
				v = frappe.db.get_value("Item", fabric_ic, col)
				if v is not None and flt(v) > 0:
					width = flt(v)
					break
			except Exception:
				pass
	if gsm <= 0:
		gsm, _ = _parse_gsm_width_from_item_text(raw_txt)
	if width <= 0:
		_, width = _parse_gsm_width_from_item_text(raw_txt)

	clean_txt = raw_txt.upper().replace("-", " ").replace("_", " ").replace("(", " ").replace(")", " ")
	clean_txt = clean_txt.replace("''", " INCH ").replace('"', " INCH ")
	words = clean_txt.split()
	qual = ""
	col = ""
	item_code_str = str(fabric_ic).strip()
	if len(item_code_str) >= 9 and item_code_str.startswith("100"):
		q_code = item_code_str[3:6]
		c_code = item_code_str[6:9]
		try:
			qual_name = (
				frappe.db.get_value("Quality Master", {"short_code": q_code}, "name")
				or frappe.db.get_value("Quality Master", {"code": q_code}, "name")
				or frappe.db.get_value("Quality Master", {"quality_code": q_code}, "name")
			)
			if qual_name:
				qual = qual_name
		except Exception:
			pass
		try:
			color_result = _get_color_by_code(c_code)
			if color_result:
				col = color_result
		except Exception:
			pass

	search_text = " " + " ".join(words) + " "
	search_norm = _normalize_quality_key(search_text)
	if not qual:
		for q in quality_lookup:
			if _normalize_quality_key(q) and _normalize_quality_key(q) in search_norm:
				qual = q
				break
	if not col:
		for c in COL_LIST:
			if (" " + c + " ") in search_text:
				col = c
				break
	if not col:
		su = search_text.upper()
		for c in COL_LIST:
			if c in su:
				col = c
				break

	line_quality = (qual or "").strip()
	if not line_quality:
		line_quality = (
			str(frappe.db.get_value("Item", fabric_ic, "custom_quality") or frappe.db.get_value("Item", fabric_ic, "quality") or "")
		).strip()
	if not line_quality:
		line_quality = "GENERIC"

	m_roll = flt(getattr(so_it, "custom_meter_per_roll", 0) or 0)
	wt = 0.0
	if gsm > 0 and width > 0 and m_roll > 0:
		wt = flt(gsm * width * m_roll * 0.0254) / 1000

	meter = cint(lam_row.meter) if lam_row else 0
	meter_per_roll = cint(lam_row.meter_per_roll) if lam_row else cint(m_roll)
	no_of_rolls = cint(lam_row.no_of_rolls) if lam_row else cint(getattr(so_it, "custom_no_of_rolls", 0) or 0)

	return {
		"gsm": cint(gsm) if gsm else 0,
		"width_inch": flt(width),
		"color": (col or "").strip() or "Unknown Color",
		"quality": line_quality,
		"custom_quality": (qual or line_quality),
		"weight_per_roll": wt,
		"meter": meter,
		"meter_per_roll": meter_per_roll,
		"no_of_rolls": no_of_rolls,
	}


# ... Limits ...
# --------------------------------------------------------------------------------
# SHARED HELPERS
# --------------------------------------------------------------------------------

def _populate_planning_sheet_items(ps, doc):
    """
    Populates items from a Sales Order into a Planning Sheet.
    Includes strict de-duplication based on sales_order_item.
    For existing items: UPDATE unit if changed (e.g., unassigned white order now assigned to a unit).
    For new items: CREATE new PSI record.
    """
    # Use confirmed field name
    target_field = "planned_items"
    for field in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
        if hasattr(ps, field) or ps.meta.has_field(field):
            target_field = field
            break

    # Fix: Use a list-based map (1:N) instead of a single mapping (1:1) to support split rows
    from collections import defaultdict
    existing_items_map = defaultdict(list)
    raw_list = getattr(ps, target_field, ps.get("items", []))
    for it in raw_list:
        if it.sales_order_item:
            existing_items_map[it.sales_order_item].append(it)

    # ... [Quality Lookup Logic] ...
    quality_lookup = list(QUAL_LIST)
    try:
        qm_names = frappe.get_all("Quality Master", pluck="name") or []
        for qn in qm_names:
            qn_up = str(qn or "").upper().strip()
            if qn_up and qn_up not in quality_lookup:
                quality_lookup.append(qn_up)
    except Exception:
        pass
    quality_lookup.sort(key=len, reverse=True)
    
    for it in doc.items:
        # Match all rows belonging to this SO item
        existing_psi_list = existing_items_map.get(it.name, [])
        is_existing = len(existing_psi_list) > 0
            
        raw_txt = (it.item_code or "") + " " + (it.item_name or "")
        clean_txt = raw_txt.upper().replace("-", " ").replace("_", " ").replace("(", " ").replace(")", " ")
        clean_txt = clean_txt.replace("''", " INCH ").replace('"', " INCH ")
        words = clean_txt.split()

        # ... [Extraction Logic] ... (omitted for brevity, keeping existing logic)
        # GSM extraction
        gsm = 0
        for i, w in enumerate(words):
            if w == "GSM" and i > 0 and words[i-1].isdigit():
                gsm = int(words[i-1])
                break
            elif w.endswith("GSM") and w[:-3].isdigit():
                gsm = int(w[:-3])
                break

        width = 0.0
        for i, w in enumerate(words):
            if w == "W" and i < len(words)-1 and words[i+1].replace('.','',1).isdigit():
                width = float(words[i+1])
                break
            elif w.startswith("W") and len(w) > 1 and w[1:].replace('.','',1).isdigit():
                width = float(w[1:])
                break
            elif w == "INCH" and i > 0 and words[i-1].replace('.','',1).isdigit():
                width = float(words[i-1])
                break
            elif w.endswith("INCH") and w[:-4].replace('.','',1).isdigit():
                width = float(w[:-4])
                break

        qual = ""
        col = ""
        item_code_str = str(it.item_code or "").strip()
        if len(item_code_str) >= 9 and item_code_str.startswith("100"):
            q_code = item_code_str[3:6]
            c_code = item_code_str[6:9]
            try:
                qual_name = frappe.db.get_value("Quality Master", {"short_code": q_code}, "name") or \
                           frappe.db.get_value("Quality Master", {"code": q_code}, "name") or \
                           frappe.db.get_value("Quality Master", {"quality_code": q_code}, "name")
                if qual_name: qual = qual_name
            except Exception: pass
            try:
                color_result = _get_color_by_code(c_code)
                if color_result: col = color_result
            except Exception: pass

        search_text = " " + " ".join(words) + " "
        search_norm = _normalize_quality_key(search_text)
        if not qual:
            for q in quality_lookup:
                if _normalize_quality_key(q) and _normalize_quality_key(q) in search_norm:
                    qual = q
                    break
        if not col:
            for c in COL_LIST:
                if (" " + c + " ") in search_text:
                    col = c
                    break
        # Fallback: substring match (longest-first COL_LIST) when spacing breaks " GOLDEN YELLOW " style match
        if not col:
            su = search_text.upper()
            for c in COL_LIST:
                if c in su:
                    col = c
                    break

        # Mandatory `quality` on Planning sheet Item / Planning Table (DocType requires it)
        line_quality = (qual or "").strip()
        if not line_quality:
            line_quality = (
                str(getattr(it, "custom_quality", None) or getattr(it, "quality", None) or "").strip()
            )
        if not line_quality and it.item_code:
            try:
                line_quality = str(
                    frappe.db.get_value("Item", it.item_code, "custom_quality")
                    or frappe.db.get_value("Item", it.item_code, "quality")
                    or ""
                ).strip()
            except Exception:
                line_quality = ""
        if not line_quality:
            line_quality = "GENERIC"

        m_roll = flt(it.custom_meter_per_roll)
        wt = 0.0
        if gsm > 0 and width > 0 and m_roll > 0:
            wt = flt(gsm * width * m_roll * 0.0254) / 1000

        unit = compute_default_production_unit(col, width)
        if LAMINATION_FLOW_ENABLED and _item_process_prefix(str(it.item_code or "")) == "104":
            unit = "Lamination Unit"

        p_date = getdate(ps.ordered_date) if _is_white_color(col) else None

        # Prepare PSI record data for syncing/creation
        psi_data = {
            "sales_order_item": it.name,
            "item_code": it.item_code,
            "item_name": it.item_name,
            "qty": it.qty,
            "uom": it.uom,
            "meter": flt(it.custom_meter),
            "meter_per_roll": m_roll,
            "no_of_rolls": flt(it.custom_no_of_rolls),
            "gsm": gsm,
            "width_inch": width,
            "quality": line_quality,
            "custom_quality": (qual or line_quality),
            "color": col,
            "weight_per_roll": wt,
            "unit": unit,
            "party_code": ps.party_code,
            "planned_date": p_date,
            "planning_sheet": ps.name # Explicitly link for grid visibility
        }

        # Fix: Sync logic must be split-aware. Update existing rows without wiping extras.
        if is_existing:
            # Update all split pieces with latest metadata from SO (Qual/Color/etc if changed)
            for existing_psi in existing_psi_list:
                # Update base info but PRESERVE unit and qty (don't overwrite board splits)
                existing_psi.uom = it.uom
                existing_psi.quality = line_quality
                existing_psi.custom_quality = qual or line_quality
                existing_psi.color = col
                # Ensure the link to parent is set
                existing_psi.planning_sheet = ps.name
                # Only update unit if it was not already assigned (Board assignment takes precedence)
                if not existing_psi.unit or existing_psi.unit == "UNASSIGNED":
                    existing_psi.unit = unit
                    existing_psi.planned_date = p_date
        else:
            pt_data = psi_data.copy()
            pt_data["planned_date"] = p_date
            pt_data["plan_name"] = ps.get("custom_plan_name")
            pt_data["planning_sheet"] = ps.name # For redundancy
            
            # Plan 1: Always fill the legacy 'items' table if it exists
            if hasattr(ps, "items") or ps.meta.has_field("items"):
                ps.append("items", pt_data)
                
            # Plan 2: Also fill the new custom table field if it exists and is NOT the legacy 'items'
            target_fields = ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]
            for field in target_fields:
                if (hasattr(ps, field) or ps.meta.has_field(field)) and field != "items":
                    ps.append(field, pt_data)
                    # Once appended to a new-table row, stop checking other fields for this psi.
                    # This ensures 1:1 row order mapping for synchronisation logic.
                    break 
    return ps


def _is_white_color(color):
    """Return True if color string matches a white-family color."""
    if not color:
        return False
    c = color.upper().strip()
    return any(w == c for w in WHITE_COLORS)


def compute_default_production_unit(color, width_inch):
    """
    Only white-family colors use UNASSIGNED (pool for that order date).
    All other colors: pick one of Unit 1–4 by minimum width waste (same rule as SO populate).
    """
    w = flt(width_inch)
    if _is_white_color(color):
        return "UNASSIGNED"
    UNIT_WIDTHS = {"Unit 1": 63, "Unit 2": 126, "Unit 3": 126, "Unit 4": 90}
    viable_units = []
    for u in ["Unit 1", "Unit 2", "Unit 3", "Unit 4"]:
        uw = UNIT_WIDTHS[u]
        if uw >= w:
            viable_units.append({"name": u, "width_waste": uw - w})
    if viable_units:
        return min(viable_units, key=lambda x: x["width_waste"])["name"]
    return "Unit 2"


def resolve_color_name_for_planning_row(item_code, item_name, existing_color=None):
    """Resolve color for width/unit rules when `color` was blank (item text / code parsing)."""
    if (existing_color or "").strip():
        return (existing_color or "").strip()
    raw_txt = ((item_code or "") + " " + (item_name or "")).strip()
    if not raw_txt:
        return ""
    clean_txt = raw_txt.upper().replace("-", " ").replace("_", " ").replace("(", " ").replace(")", " ")
    words = clean_txt.split()
    search_text = " " + " ".join(words) + " "
    col = ""
    item_code_str = str(item_code or "").strip()
    if len(item_code_str) >= 9 and item_code_str.startswith("100"):
        c_code = item_code_str[6:9]
        try:
            color_result = _get_color_by_code(c_code)
            if color_result:
                return color_result.upper().strip()
        except Exception:
            pass
    for c in COL_LIST:
        if (" " + c + " ") in search_text:
            return c
    su = search_text.upper()
    for c in COL_LIST:
        if c in su:
            return c
    return ""


def _get_color_by_code(color_code):
    """
    Look up color in Colour Master by color code.
    Returns the color name if found, None otherwise.
    """
    if not color_code:
        return None
    
    color_code = str(color_code).strip()
    
    # Try multiple field names  in order of preference
    fields_to_try = ["custom_color_code", "colour_code", "color_code", "short_code", "code"]
    
    for field in fields_to_try:
        try:
            result = frappe.db.get_value(
                "Colour Master",
                {field: color_code},
                ["name", "colour_name", "color_name"],
                as_dict=True
            )
            if result:
                color_name = result.get("name") or result.get("colour_name") or result.get("color_name")
                if color_name:
                    return color_name.upper().strip()
        except Exception:
            pass
    
    return None


def _normalize_color_text(v) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    su = s.upper()
    if su in {"UNKNOWN", "UNKNOWN COLOR", "NO COLOR", "N/A", "NA", "-"}:
        return ""
    return s


def _extract_color_from_sales_order_item(so_item_name: str) -> str:
    if not so_item_name or not frappe.db.exists("Sales Order Item", so_item_name):
        return ""
    cols = set(frappe.db.get_table_columns("Sales Order Item") or [])
    candidates = []
    for c in ("color", "custom_color", "colour", "custom_colour"):
        if c in cols:
            candidates.append(c)
    if not candidates:
        return ""
    row = frappe.db.get_value("Sales Order Item", so_item_name, candidates, as_dict=True) or {}
    for c in candidates:
        v = _normalize_color_text(row.get(c))
        if v:
            return v.upper().strip()
    return ""


@frappe.whitelist()
def refresh_planning_sheet_colors(planning_sheet: str):
    """Re-sync Planning sheet item colors from Sales Order Item / Item code parsing even after submit."""
    if not planning_sheet or not frappe.db.exists("Planning sheet", planning_sheet):
        return {"status": "error", "message": "Planning sheet not found", "updated": 0}

    rows = frappe.get_all(
        "Planning Table",
        filters={"parent": planning_sheet, "parenttype": "Planning sheet"},
        fields=["name", "sales_order_item", "item_code", "item_name", "color"],
        order_by="idx asc",
    ) or []

    updated = 0
    for r in rows:
        existing = _normalize_color_text(r.get("color"))
        from_so = _extract_color_from_sales_order_item(r.get("sales_order_item"))
        parsed = resolve_color_name_for_planning_row(
            r.get("item_code"), r.get("item_name"), existing_color=""
        )
        parsed = _normalize_color_text(parsed)
        next_color = (from_so or parsed or "").upper().strip()
        if next_color and next_color != str(r.get("color") or "").strip().upper():
            frappe.db.set_value("Planning Table", r["name"], "color", next_color, update_modified=False)
            updated += 1

    if updated:
        frappe.db.set_value("Planning sheet", planning_sheet, "modified", frappe.utils.now(), update_modified=False)

    return {"status": "ok", "updated": updated, "message": f"Updated color on {updated} row(s)."}


@frappe.whitelist()
def refresh_planning_sheet_spr_and_order_sheet(planning_sheet: str):
    """Backfill Planning Table `order_sheet` and `spr_name` for a sheet even after submit."""
    if not planning_sheet or not frappe.db.exists("Planning sheet", planning_sheet):
        return {"status": "error", "message": "Planning sheet not found", "updated_order_sheet": 0, "updated_spr": 0}

    def _pick_valid_pp(raw) -> str:
        txt = str(raw or "").strip()
        if not txt:
            return ""
        for token in [x.strip() for x in txt.split(",") if x and x.strip()]:
            if frappe.db.exists("Production Plan", token):
                return token
        return ""

    sheet_pp = (
        frappe.db.get_value("Planning sheet", planning_sheet, "custom_production_plan")
        if frappe.db.has_column("Planning sheet", "custom_production_plan")
        else ""
    ) or (
        frappe.db.get_value("Planning sheet", planning_sheet, "production_plan")
        if frappe.db.has_column("Planning sheet", "production_plan")
        else ""
    ) or (frappe.db.get_value("Planning sheet", planning_sheet, "order_sheet") or "")
    sheet_pp = _pick_valid_pp(sheet_pp)

    rows = frappe.get_all(
        "Planning Table",
        filters={"parent": planning_sheet, "parenttype": "Planning sheet"},
        fields=["name", "spr_name", "order_sheet", "item_code"],
        order_by="idx asc",
    ) or []

    pp_to_spr = {}
    updated_order_sheet = 0
    updated_spr = 0

    candidate_pps = set()
    if sheet_pp:
        candidate_pps.add(sheet_pp)
    for col in ("custom_planning_sheet", "planning_sheet"):
        if frappe.db.has_column("Production Plan", col):
            for ppn in frappe.db.get_all("Production Plan", filters={col: planning_sheet, "docstatus": ["<", 2]}, pluck="name"):
                if ppn:
                    candidate_pps.add(ppn)
    for row in rows:
        item_pp = _pick_valid_pp(_get_item_level_production_plan(row.get("name")))
        if item_pp:
            candidate_pps.add(item_pp)

    pp_by_item_code = {}
    if candidate_pps:
        fmt = ", ".join(["%s"] * len(candidate_pps))
        q = frappe.db.sql(
            f"""
            SELECT ppi.item_code, ppi.parent as production_plan
            FROM `tabProduction Plan Item` ppi
            WHERE ppi.parent IN ({fmt})
              AND IFNULL(ppi.item_code, '') != ''
            """,
            tuple(candidate_pps),
            as_dict=True,
        ) or []
        for r in q:
            it = (r.get("item_code") or "").strip()
            ppn = (r.get("production_plan") or "").strip()
            if it and ppn:
                pp_by_item_code.setdefault(it, [])
                if ppn not in pp_by_item_code[it]:
                    pp_by_item_code[it].append(ppn)

    def _pick_spr_for_pp(pp_id: str) -> str:
        pp_id = (pp_id or "").strip()
        if not pp_id:
            return ""
        if pp_id in pp_to_spr:
            return pp_to_spr[pp_id]

        spr_name = ""
        raw = str(frappe.db.get_value("Production Plan", pp_id, "custom_shaft_production_run_id") or "").strip()
        if raw:
            for p in [x.strip() for x in raw.split(",") if x and x.strip()]:
                if frappe.db.exists("Shaft Production Run", p):
                    spr_name = p
                    break
        if not spr_name:
            spr_name = (
                frappe.db.get_value(
                    "Shaft Production Run",
                    {"production_plan": pp_id, "docstatus": ["<", 2]},
                    "name",
                    order_by="modified desc",
                )
                or ""
            )
        pp_to_spr[pp_id] = spr_name
        return spr_name

    for r in rows:
        row_pp = _pick_valid_pp(_get_item_level_production_plan(r.name))
        if not row_pp:
            item_code = (r.get("item_code") or "").strip()
            choices = pp_by_item_code.get(item_code) or []
            if len(choices) == 1:
                row_pp = choices[0]
            elif len(choices) > 1:
                existing = _pick_valid_pp(r.get("order_sheet"))
                row_pp = existing if existing in choices else choices[0]
        if not row_pp:
            row_pp = _pick_valid_pp(r.get("order_sheet"))
        if not row_pp:
            row_pp = sheet_pp
        if row_pp and (r.get("order_sheet") or "").strip() != row_pp:
            frappe.db.set_value("Planning Table", r["name"], "order_sheet", row_pp, update_modified=False)
            updated_order_sheet += 1

        row_spr = _pick_spr_for_pp(row_pp) if row_pp else ""
        if row_spr and (r.get("spr_name") or "").strip() != row_spr:
            frappe.db.set_value("Planning Table", r["name"], "spr_name", row_spr, update_modified=False)
            updated_spr += 1

    return {
        "status": "ok",
        "updated_order_sheet": updated_order_sheet,
        "updated_spr": updated_spr,
        "message": f"Updated Order Sheet on {updated_order_sheet} row(s), SPR on {updated_spr} row(s).",
    }


@frappe.whitelist()
def manual_update_planning_sheet_links(planning_sheet: str, mappings):
    """
    Manual safe updater for Planning Table links.
    mappings: JSON array of objects -> {row_name?, item_code?, order_sheet, spr_name}
    """
    if not planning_sheet or not frappe.db.exists("Planning sheet", planning_sheet):
        return {"status": "error", "message": "Planning sheet not found", "updated": 0, "errors": []}

    if isinstance(mappings, str):
        try:
            mappings = json.loads(mappings)
        except Exception:
            return {"status": "error", "message": "Invalid mappings JSON", "updated": 0, "errors": ["Invalid JSON"]}
    mappings = mappings or []
    if not isinstance(mappings, list):
        return {"status": "error", "message": "Mappings must be a list", "updated": 0, "errors": ["Mappings must be list"]}

    rows = frappe.get_all(
        "Planning Table",
        filters={"parent": planning_sheet, "parenttype": "Planning sheet"},
        fields=["name", "item_code"],
    ) or []
    valid_rows = {r.get("name") for r in rows}
    rows_by_item_code = {}
    for r in rows:
        ic = (r.get("item_code") or "").strip()
        if ic:
            rows_by_item_code.setdefault(ic, [])
            rows_by_item_code[ic].append(r.get("name"))
    updated = 0
    errors = []

    for i, m in enumerate(mappings, start=1):
        row_name = (m.get("row_name") or "").strip()
        item_code = (m.get("item_code") or "").strip()
        pp = (m.get("order_sheet") or "").strip()
        spr = (m.get("spr_name") or "").strip()
        if not row_name and item_code:
            candidates = rows_by_item_code.get(item_code) or []
            if len(candidates) == 1:
                row_name = candidates[0]
            elif len(candidates) > 1:
                errors.append(f"Line {i}: item_code {item_code} matches multiple rows; use row_name")
                continue
            else:
                errors.append(f"Line {i}: item_code {item_code} not found in this sheet")
                continue
        if not row_name:
            errors.append(f"Line {i}: row_name or item_code is required")
            continue
        if row_name not in valid_rows:
            errors.append(f"Line {i}: row {row_name} is not part of {planning_sheet}")
            continue
        if pp and not frappe.db.exists("Production Plan", pp):
            errors.append(f"Line {i}: Production Plan {pp} not found")
            continue
        if spr and not frappe.db.exists("Shaft Production Run", spr):
            errors.append(f"Line {i}: SPR {spr} not found")
            continue
        if pp and spr:
            spr_pp = (frappe.db.get_value("Shaft Production Run", spr, "production_plan") or "").strip()
            if spr_pp and spr_pp != pp:
                errors.append(f"Line {i}: SPR {spr} belongs to {spr_pp}, not {pp}")
                continue

        if pp:
            frappe.db.set_value("Planning Table", row_name, "order_sheet", pp, update_modified=False)
        if spr:
            frappe.db.set_value("Planning Table", row_name, "spr_name", spr, update_modified=False)
        updated += 1

    return {
        "status": "ok",
        "updated": updated,
        "errors": errors,
        "message": f"Updated {updated} row(s)." + (f" Errors: {len(errors)}" if errors else ""),
    }

# White colors that are auto-planned on the Production Board and excluded from Color Chart sequencing
WHITE_COLORS = {
    "WHITE", "BRIGHT WHITE", "SUNSHINE WHITE", "MILKY WHITE", 
    "SUPER WHITE", "BLEACH WHITE", "BLEACH WHITE 1.0", "BLEACH WHITE 2.0"
}

def _normalize_unit(raw):
    """Returns title-case unit names like 'Unit 1', … or UNASSIGNED for unassigned / legacy Mixed."""
    r = (raw or "").strip().upper().replace(" ", "")
    if "UNIT1" in r:
        return "Unit 1"
    if "UNIT2" in r:
        return "Unit 2"
    if "UNIT3" in r:
        return "Unit 3"
    if "UNIT4" in r:
        return "Unit 4"
    return "UNASSIGNED"

def _get_standard_month_name(month_index):
    # month_index 1-12
    month_names = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"]
    if 1 <= month_index <= 12:
        return month_names[month_index - 1]
    return "UNKNOWN"

def _get_contextual_plan_name(base_name, date_val):
    """
    Returns the full contextual plan name with month/week prefix, matching the
    frontend display logic in ColorChart.vue: currentMonthPrefix + ' ' + p.name
    e.g. base_name='PLAN 1', date_val='2026-03-19' -> 'MARCH W12 26 PLAN 1'

    If base_name already contains a month prefix (legacy), returns it as-is.
    If base_name is 'Default', returns 'Default'.
    """
    if not base_name or base_name == "Default":
        return base_name

    clean = base_name.strip()

    # If already prefixed (contains month name), return as-is
    month_names = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE",
                   "JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"]
    upper = clean.upper()
    if any(upper.startswith(m) for m in month_names):
        return clean

    # Build prefix from date_val (mirrors frontend currentMonthPrefix computed for weekly scope)
    try:
        import datetime as _dt
        if date_val:
            d = frappe.utils.getdate(date_val)
            # ISO week number
            iso = d.isocalendar()  # (year, week, weekday)
            week_num = iso[1]
            year_2 = str(d.year)[2:]
            month_prefix = month_names[d.month - 1]
            prefix = f"{month_prefix} W{week_num} {year_2}"
            return f"{prefix} {clean}"
    except Exception:
        pass

    return clean

def _find_best_unlocked_plan(parsed_plans, doc_date):
    """
    Returns the first unlocked plan name.
    Matches primarily by 'base name' to avoid prefix issues.
    """
    if not parsed_plans:
        return None
        
    first_unlocked = None
    default_plan = None
    
    for plan in parsed_plans:
        is_locked = str(plan.get("locked", "0")) in ["1", 1, "true", True]
        if is_locked:
            continue
            
        p_name = str(plan.get("name", "")).strip()
        # Get base name for matching (e.g. MARCH W10 26 PLAN 1 -> PLAN 1)
        base = _strip_legacy_prefixes(p_name)
        
        if base.upper() == "DEFAULT":
            default_plan = p_name
            continue
            
        if not first_unlocked:
            first_unlocked = p_name
                
    return first_unlocked or default_plan

def _strip_legacy_prefixes(name):
    """
    Strips various month/week prefixes to get the base plan name.
    Example: 'MAR-26 PLAN 1' -> 'PLAN 1'
             'MARCH W10 26 PLAN 1' -> 'PLAN 1'
    """
    if not name or name == "Default":
        return name
        
    # Pattern 1: [MONTH] W[XX] [YY] [NAME] -> (e.g. MARCH W10 26 PLAN 1)
    p1 = re.sub(r'^[A-Z]+\s+W\d+\s+\d{2}\s+', '', name, flags=re.IGNORECASE)
    if p1 != name:
        return p1.strip()
        
    # Pattern 2: [MON]-[YY] [NAME] -> (e.g. MAR-26 PLAN 1)
    p2 = re.sub(r'^[A-Z]{3}-\d{2}\s+', '', name, flags=re.IGNORECASE)
    if p2 != name:
        return p2.strip()
        
    # Pattern 3: [MONTH] [YY] [NAME] -> (e.g. MARCH 26 PLAN 1)
    p3 = re.sub(r'^[A-Z]+\s+\d{2}\s+', '', name, flags=re.IGNORECASE)
    if p3 != name:
        return p3.strip()
        
    return name.strip()

HARD_LIMITS = {
    "Unit 1": 4.4,
    "Unit 2": 12.0,
    "Unit 3": 9.0,
    "Unit 4": 5.5
}
SOFT_LIMITS = {
    "Unit 1": 4.0,
    "Unit 2": 9.0,
    "Unit 3": 7.8,
    "Unit 4": 4.0
}

UNIT_QUALITY_MAP = {
    "Unit 1": UNIT_1,
    "Unit 2": UNIT_2,
    "Unit 3": UNIT_3,
    "Unit 4": UNIT_4
}

def is_quality_allowed(unit, quality):
    """All Quality Master values are allowed in all units."""
    return True

def is_sheet_locked(sheet_name):
    """Checks if a sheet is locked (either submitted or belongs to a locked plan)."""
    try:
        sheet = frappe.get_doc("Planning sheet", sheet_name)
        if sheet.docstatus != 0:
            return True
        
        # Check if its plans are locked
        cc_plan = sheet.get("custom_plan_name") or "Default"
        
        # We need to fetch persisted plans to check lock status
        from production_entry.production_planning.scheduler_api import get_persisted_plans
        
        cc_plans = get_persisted_plans("color_chart")
        if any(p["name"] == cc_plan and p.get("locked") for p in cc_plans):
            return True
            
        return False
                
        return False
    except Exception:
        return False

# Cache for column existence check
_planned_date_col_exists = None
def _has_planned_date_column():
    """Check if custom_planned_date column exists on Planning sheet table."""
    global _planned_date_col_exists
    if _planned_date_col_exists is None:
        try:
            frappe.db.sql("SELECT custom_planned_date FROM `tabPlanning sheet` LIMIT 1")
            _planned_date_col_exists = True
        except Exception:
            _planned_date_col_exists = False
    return _planned_date_col_exists

_approval_status_col_exists = None
def _has_approval_status_column():
    """Check if custom_approval_status column exists on Planning sheet table."""
    global _approval_status_col_exists
    if _approval_status_col_exists is None:
        try:
            frappe.db.sql("SELECT custom_approval_status FROM `tabPlanning sheet` LIMIT 1")
            _approval_status_col_exists = True
        except Exception:
            _approval_status_col_exists = False
    return _approval_status_col_exists

_draft_fields_exist = None
def _has_draft_fields():
    """Check if custom_draft_planned_date/idx columns exist."""
    global _draft_fields_exist
    if _draft_fields_exist is None:
        try:
            frappe.db.sql("SELECT custom_draft_planned_date FROM `tabPlanning sheet` LIMIT 1")
            _draft_fields_exist = True
        except Exception:
            _draft_fields_exist = False
    return _draft_fields_exist

def _effective_date_expr(alias="p"):
    """Returns SQL expression for effective date."""
    if _has_planned_date_column():
        return f"COALESCE({alias}.custom_planned_date, {alias}.ordered_date)"
    return f"{alias}.ordered_date"

def get_unit_load(date, unit, plan_name=None, pb_only=0):
    """Calculates current load (in Tons) for a unit on a given date.
    Filtered per-plan so each plan has its own independent capacity.
    Uses planned_date if set, otherwise falls back to parent.
    """
    # Priority: Item Date -> Sheet Date -> Sheet Ordered Date
    eff = "COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)"
    pb_only = cint(pb_only)
    # Build plan filter ΓÇö each plan is treated independently
    if plan_name and plan_name != "__all__":
        if plan_name == "Default":
            plan_cond = "AND (p.custom_plan_name IS NULL OR p.custom_plan_name = '' OR p.custom_plan_name = 'Default')"
            params = (date, unit)
        else:
            plan_cond = "AND p.custom_plan_name = %s"
            params = (date, unit, plan_name)
    else:
        # No plan filter ΓÇö sum all (used internally for global capacity checks)
        plan_cond = ""
        params = (date, unit)

    # Optional Production Board-only mode:
    # Only count items/sheets explicitly pushed/planned to PB.
    pb_cond = ""
    if pb_only and _has_planned_date_column():
        pb_cond = "AND p.custom_planned_date IS NOT NULL AND p.custom_planned_date != ''"
    
    # MIX WASTE EXCLUSION:
    # Matches frontend logic (is_mix_roll || itemName.startsWith('MIX'))
    mix_cond = "AND i.item_name NOT LIKE 'MIX%%'"
    
    sql = f"""
        SELECT SUM(i.qty) as total_qty
        FROM `tabPlanning Table` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        WHERE {eff} = %s
          AND i.unit = %s
          AND p.docstatus < 2
          AND i.docstatus < 2
          {plan_cond}
          {pb_cond}
          {mix_cond}
    """
    result = frappe.db.sql(sql, params)
    return flt(result[0][0]) / 1000.0 if result and result[0][0] else 0.0

# ===========================
# EQUIPMENT MAINTENANCE HELPERS
# ===========================

NON_BLOCKING_MAINTENANCE_TYPES = {"MESH CHANGE", "DIE CHANGE"}


def _is_non_blocking_maintenance_type(maintenance_type):
    return str(maintenance_type or "").strip().upper() in NON_BLOCKING_MAINTENANCE_TYPES

@frappe.whitelist()
def get_maintenance_windows(unit, start_date, end_date):
    """
    Query all maintenance periods for a unit within a date range.
    Returns: dict {date: [list of maintenance records]}
    """
    from frappe.utils import getdate, add_days
    
    start_dt = getdate(start_date)
    end_dt = getdate(end_date)
    
    if not frappe.db.exists("DocType", "Equipment Maintenance"):
        return {}
    
    records = frappe.db.sql("""
        SELECT name, unit, maintenance_type, start_date, end_date, status
        FROM `tabEquipment Maintenance`
        WHERE unit = %s
          AND start_date <= %s
          AND end_date >= %s
          AND docstatus < 2
    """, (unit, end_dt, start_dt), as_dict=True)
    
    # Build date map
    result = {}
    for rec in records:
        current = getdate(rec.start_date)
        end = getdate(rec.end_date)
        while current <= end:
            date_str = str(current)
            if date_str not in result:
                result[date_str] = []
            result[date_str].append({
                "type": rec.maintenance_type,
                "start_date": str(rec.start_date),
                "end_date": str(rec.end_date),
                "status": rec.status
            })
            current = add_days(current, 1)
    
    return result

def is_date_under_maintenance(unit, date_string):
    """Check if date has BLOCKING maintenance scheduled for unit."""
    from frappe.utils import getdate
    
    if not frappe.db.exists("DocType", "Equipment Maintenance"):
        return False
    
    check_date = getdate(date_string)

    count = frappe.db.sql("""
        SELECT COUNT(*) as cnt
        FROM `tabEquipment Maintenance`
        WHERE unit = %s
          AND start_date <= %s
          AND end_date >= %s
          AND docstatus < 2
          AND UPPER(TRIM(COALESCE(maintenance_type, ''))) NOT IN ('MESH CHANGE', 'DIE CHANGE')
        """, (unit, check_date, check_date))
    
    return count[0][0] > 0 if count else False

def get_maintenance_info_on_date(unit, date_string):
    """Get BLOCKING maintenance details if date is under maintenance."""
    from frappe.utils import getdate
    
    if not frappe.db.exists("DocType", "Equipment Maintenance"):
        return None
    
    check_date = getdate(date_string)
    
    rec = frappe.db.sql("""
        SELECT name, maintenance_type, start_date, end_date, status
        FROM `tabEquipment Maintenance`
        WHERE unit = %s
          AND start_date <= %s
          AND end_date >= %s
          AND docstatus < 2
          AND UPPER(TRIM(COALESCE(maintenance_type, ''))) NOT IN ('MESH CHANGE', 'DIE CHANGE')
        LIMIT 1
    """, (unit, check_date, check_date), as_dict=True)
    
    if rec:
        return {
            "type": rec[0].maintenance_type,
            "start_date": str(rec[0].start_date),
            "end_date": str(rec[0].end_date),
            "status": rec[0].status
        }
    return None

def get_next_available_date_skipping_maintenance(unit, start_date, required_tons=0, days_ahead=30):
    """Find next date where unit has capacity and is NOT under maintenance."""
    from frappe.utils import getdate, add_days
    
    if not unit or not start_date:
        return {"date": None}
    
    start_dt = getdate(start_date)
    required = flt(required_tons)
    days_ahead = cint(days_ahead) or 30
    limit = HARD_LIMITS.get(unit, 999.0)
    
    for i in range(days_ahead + 1):
        candidate = add_days(start_dt, i)
        candidate_str = str(candidate)
        
        # Skip if under maintenance
        if is_date_under_maintenance(unit, candidate_str):
            continue
        
        load = get_unit_load(candidate_str, unit, "__all__", pb_only=0)
        if load + required <= (limit * 1.05):
            return {
                "date": candidate_str,
                "current_load": load,
                "limit": limit,
                "reason": "available"
            }
    
    # Fallback suggestion
    fallback = add_days(start_dt, 1)
    return {
        "date": str(fallback),
        "current_load": get_unit_load(str(fallback), unit, "__all__", pb_only=0),
        "limit": limit,
        "reason": "no_clean_slot_found"
    }

@frappe.whitelist()
def add_equipment_maintenance(unit, maintenance_type, start_date, end_date, notes=None):
    """Create new Equipment Maintenance record."""
    import json

    if not frappe.db.exists("DocType", "Equipment Maintenance"):
        return {"status": "error", "message": "Equipment Maintenance module not found"}
    
    doc = frappe.get_doc({
        "doctype": "Equipment Maintenance",
        "unit": unit,
        "maintenance_type": maintenance_type,
        "start_date": start_date,
        "end_date": end_date,
        "notes": notes or "",
        "status": "Planned"
    })
    doc.insert(ignore_permissions=False)

    cascade_result = {"cascaded_count": 0}
    if not _is_non_blocking_maintenance_type(maintenance_type):
        # Blocking maintenance types move affected orders forward.
        cascade_result = cascade_orders_after_maintenance_removal(unit, start_date, end_date)
        movement_log = cascade_result.get("movement_log") or []

        # Persist original->new date movements on the maintenance record so delete can restore backward.
        if movement_log:
            marker = "MAINTENANCE_CASCADE_LOG::"
            user_notes = (notes or "").strip()
            log_line = marker + json.dumps(movement_log, separators=(",", ":"))
            stored_notes = f"{user_notes}\n\n{log_line}" if user_notes else log_line
            frappe.db.set_value("Equipment Maintenance", doc.name, "notes", stored_notes, update_modified=False)
            frappe.cache().set_value(f"maintenance_cascade_log::{doc.name}", movement_log)

    frappe.db.commit()

    if _is_non_blocking_maintenance_type(maintenance_type):
        return {
            "status": "success",
            "message": f"{maintenance_type} scheduled for {unit} from {start_date} to {end_date}. Orders remain on the same day.",
            "cascaded_count": 0,
            "name": doc.name
        }
    
    return {
        "status": "success",
        "message": f"Maintenance scheduled for {unit} from {start_date} to {end_date}. Moved {cascade_result.get('cascaded_count', 0)} items forward.",
        "cascaded_count": cascade_result.get("cascaded_count", 0),
        "name": doc.name
    }

@frappe.whitelist()
def cascade_orders_after_maintenance_removal(unit, maint_start_date, maint_end_date):
    """
    Move items planned inside a maintenance window forward to next available dates.
    (Used at maintenance creation time.)
    """
    from frappe.utils import getdate, add_days
    
    if not unit or not maint_start_date or not maint_end_date:
        return {"status": "error", "message": "Missing parameters"}
    
    start_dt = getdate(maint_start_date)
    end_dt = getdate(maint_end_date)
    
    # Find all items planned between maintenance start and end dates
    items = frappe.db.sql("""
        SELECT i.name, i.qty, i.unit, COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date) as effective_planned_date
        FROM `tabPlanning Table` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        WHERE i.unit = %s
          AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) >= %s
          AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) <= %s
          AND p.docstatus < 2
          AND i.docstatus < 2
    """, (unit, start_dt, end_dt), as_dict=True)
    
    if not items:
        return {"status": "success", "message": "No items to cascade", "cascaded_count": 0}
    
    has_item_planned_col = frappe.db.has_column("Planning Table", "planned_date")
    cascaded_count = 0
    local_loads = {}
    movement_log = []
    
    for item in items:
        if not has_item_planned_col:
            continue
        
        item_name = item.get("name")
        qty_tons = flt(item.get("qty")) / 1000.0
        unit_limit = HARD_LIMITS.get(unit, 999.0)
        current_date = getdate(item.get("effective_planned_date"))
        original_date_str = current_date.strftime("%Y-%m-%d")
        
        # Find next available date (skipping maintenance)
        candidate = add_days(current_date, 1)
        found_slot = False
        
        for i in range(30):  # Look ahead 30 days
            candidate_str = candidate if isinstance(candidate, str) else candidate.strftime("%Y-%m-%d")
            
            # Skip if under maintenance
            if is_date_under_maintenance(unit, candidate_str):
                candidate = add_days(candidate, 1)
                continue
            
            load_key = (candidate_str, unit)
            if load_key not in local_loads:
                local_loads[load_key] = get_unit_load(candidate_str, unit, "__all__", pb_only=1)
            
            current_load = local_loads[load_key]
            
            if (current_load + qty_tons <= unit_limit * 1.05) or (current_load == 0 and qty_tons >= unit_limit):
                local_loads[load_key] = current_load + qty_tons
                # Update item's planned date
                frappe.db.sql("""
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s
                    WHERE name = %s
                """, (candidate_str, item_name))
                movement_log.append({
                    "item_name": item_name,
                    "from_date": original_date_str,
                    "to_date": candidate_str
                })
                cascaded_count += 1
                found_slot = True
                break
            
            candidate = add_days(candidate, 1)
    
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": f"Cascaded {cascaded_count} items to next available dates",
        "cascaded_count": cascaded_count,
        "movement_log": movement_log
    }

@frappe.whitelist()
def forward_orders_from_date_range(cascade_start_date, cascade_end_date, plan_name=None):
    """
    Forward ALL orders queued on cascade_start_date to cascade_end_date
    to next available dates (after the cascade ends).
    
    Used when pushing colors - automatically clears the cascade range.
    
    Args:
        cascade_start_date: Start of cascade range (e.g. '2026-03-08')
        cascade_end_date: End of cascade range (e.g. '2026-03-16')
        plan_name: Plan name to filter by (optional)
    
    Returns:
        {
            "status": "success|error",
            "forwarded_count": number of items moved,
            "dates_cleared": list of dates that were cleared,
            "movement_log": [{"item_name": "...", "from_date": "...", "to_date": "...", "unit": "..."}, ...]
        }
    """
    from frappe.utils import getdate, add_days
    import datetime
    
    if not cascade_start_date or not cascade_end_date:
        return {"status": "error", "message": "Missing cascade date range"}
    
    start_dt = getdate(cascade_start_date)
    end_dt = getdate(cascade_end_date)
    
    if not frappe.db.has_column("Planning Table", "planned_date"):
        return {"status": "error", "message": "Required column planned_date not found"}
    
    # Find ALL items (any type) queued on dates in the cascade range
    items = frappe.db.sql("""
        SELECT 
            i.name, 
            i.qty, 
            i.unit, 
            i.color,
            COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date) as effective_planned_date
        FROM `tabPlanning Table` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        WHERE p.docstatus < 2
          AND i.docstatus < 2
          AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) >= %s
          AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) <= %s
    """, (start_dt, end_dt), as_dict=True)
    
    if not items:
        # Generate date list for cleared dates
        dates_cleared = []
        current = start_dt
        while current <= end_dt:
            dates_cleared.append(str(current))
            current = add_days(current, 1)
        
        return {
            "status": "success",
            "message": "No items to forward",
            "forwarded_count": 0,
            "dates_cleared": dates_cleared,
            "movement_log": []
        }
    
    # Group items by unit for independent cascading
    items_by_unit = {}
    for item in items:
        unit = item.get("unit") or "Unit 1"
        if unit not in items_by_unit:
            items_by_unit[unit] = []
        items_by_unit[unit].append(item)
    
    forwarded_count = 0
    movement_log = []
    local_loads = {}  # (date, unit) -> current load in tons
    
    # Generate date list for cleared dates
    dates_cleared = []
    current = start_dt
    while current <= end_dt:
        dates_cleared.append(str(current))
        current = add_days(current, 1)
    
    # Process each unit independently
    for unit, unit_items in items_by_unit.items():
        unit_limit = HARD_LIMITS.get(unit, 999.0)
        
        for item in unit_items:
            item_name = item.get("name")
            qty_tons = flt(item.get("qty")) / 1000.0
            original_date = getdate(item.get("effective_planned_date"))
            original_date_str = str(original_date)
            color = item.get("color") or ""
            
            # Start looking from the day AFTER cascade_end_date
            candidate = add_days(end_dt, 1)
            forward_found = False
            
            # Search up to 60 days ahead for available slot
            for search_days in range(60):
                candidate_str = str(candidate) if isinstance(candidate, str) else candidate.strftime("%Y-%m-%d")
                
                # Skip if under maintenance
                if is_date_under_maintenance(unit, candidate_str):
                    candidate = add_days(candidate, 1)
                    continue
                
                # Check current load for this date/unit
                load_key = (candidate_str, unit)
                if load_key not in local_loads:
                    local_loads[load_key] = get_unit_load(candidate_str, unit, "__all__", pb_only=1)
                
                current_load = local_loads[load_key]
                
                # Check if item fits (with 5% buffer) or if day is empty but item is oversized
                if (current_load + qty_tons <= unit_limit * 1.05) or (current_load == 0 and qty_tons >= unit_limit):
                    local_loads[load_key] = current_load + qty_tons
                    
                    # Update the item's planned date
                    frappe.db.sql("""
                        UPDATE `tabPlanning Table`
                        SET planned_date = %s
                        WHERE name = %s
                    """, (candidate_str, item_name))
                    
                    movement_log.append({
                        "item_name": item_name,
                        "color": color,
                        "from_date": original_date_str,
                        "to_date": candidate_str,
                        "unit": unit,
                        "qty_tons": round(qty_tons, 2)
                    })
                    
                    forwarded_count += 1
                    forward_found = True
                    break
                
                candidate = add_days(candidate, 1)
            
            if not forward_found:
                frappe.log_error(f"Could not forward item {item_name} from {original_date_str} - no available slot found in 60 days", "Forward Orders Error")
    
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": f"Forwarded {forwarded_count} items from cascade range {cascade_start_date} to {cascade_end_date}",
        "forwarded_count": forwarded_count,
        "dates_cleared": dates_cleared,
        "movement_log": movement_log
    }

def _extract_maintenance_cascade_log(notes_text):
    """Read embedded movement log from maintenance notes."""
    import json

    marker = "MAINTENANCE_CASCADE_LOG::"
    if not notes_text or marker not in notes_text:
        return []

    raw = notes_text.split(marker, 1)[1].strip()
    if "\n" in raw:
        raw = raw.split("\n", 1)[0].strip()

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

def _restore_orders_to_original_dates(unit, movement_log):
    """Restore moved items back to their original dates after maintenance is deleted."""
    from frappe.utils import getdate

    if not movement_log:
        return {"restored_count": 0, "skipped_count": 0}

    if not frappe.db.has_column("Planning Table", "planned_date"):
        return {"restored_count": 0, "skipped_count": len(movement_log)}

    restored_count = 0
    skipped_count = 0

    for move in movement_log:
        item_name = move.get("item_name")
        from_date = move.get("from_date")
        to_date = move.get("to_date")

        if not item_name or not from_date or not to_date:
            skipped_count += 1
            continue

        row = frappe.db.sql("""
            SELECT i.unit, COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date) AS effective_planned_date
            FROM `tabPlanning Table` i
            JOIN `tabPlanning sheet` p ON p.name = i.parent
            WHERE i.name = %s
              AND p.docstatus < 2
              AND i.docstatus < 2
            LIMIT 1
        """, (item_name,), as_dict=True)

        if not row:
            skipped_count += 1
            continue

        current_unit = row[0].get("unit")
        current_effective = str(getdate(row[0].get("effective_planned_date")))

        # Restore if item is still on or after the maintenance-shifted date.
        # This allows rollback even when later logic pushed it further forward.
        if current_unit != unit or current_effective < str(getdate(to_date)):
            skipped_count += 1
            continue

        # Avoid restoring into another active maintenance window.
        if is_date_under_maintenance(unit, from_date):
            skipped_count += 1
            continue

        frappe.db.sql("""
            UPDATE `tabPlanning Table`
            SET planned_date = %s
            WHERE name = %s
        """, (from_date, item_name))
        restored_count += 1

    frappe.db.commit()
    return {"restored_count": restored_count, "skipped_count": skipped_count}

def _fallback_restore_by_range(unit, maint_start_date, maint_end_date):
    """Fallback restore when movement log is missing/corrupted: pull next-day shifted items back into the maintenance window dates."""
    from frappe.utils import getdate, add_days

    if not frappe.db.has_column("Planning Table", "planned_date"):
        return {"restored_count": 0, "skipped_count": 0}

    start_dt = getdate(maint_start_date)
    end_dt = getdate(maint_end_date)
    window_days = (end_dt - start_dt).days + 1
    search_end = add_days(end_dt, max(3, window_days + 2))

    rows = frappe.db.sql("""
        SELECT i.name, i.unit, i.qty,
               DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) AS effective_planned_date
        FROM `tabPlanning Table` i
        JOIN `tabPlanning sheet` p ON p.name = i.parent
        WHERE i.unit = %s
          AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) > %s
          AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) <= %s
          AND p.docstatus < 2
          AND i.docstatus < 2
        ORDER BY DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) ASC, i.idx ASC
    """, (unit, end_dt, search_end), as_dict=True)

    if not rows:
        return {"restored_count": 0, "skipped_count": 0}

    local_loads = {}
    restored = 0
    skipped = 0
    unit_limit = HARD_LIMITS.get(unit, 999.0)

    for r in rows:
        item_name = r.get("name")
        qty_tons = flt(r.get("qty")) / 1000.0

        placed = False
        for day_offset in range(window_days):
            candidate = add_days(start_dt, day_offset)
            candidate_str = candidate if isinstance(candidate, str) else candidate.strftime("%Y-%m-%d")

            if is_date_under_maintenance(unit, candidate_str):
                continue

            load_key = (candidate_str, unit)
            if load_key not in local_loads:
                local_loads[load_key] = get_unit_load(candidate_str, unit, "__all__", pb_only=1)

            current_load = local_loads[load_key]
            if (current_load + qty_tons <= unit_limit * 1.05) or (current_load == 0 and qty_tons >= unit_limit):
                frappe.db.sql("""
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s
                    WHERE name = %s
                """, (candidate_str, item_name))
                local_loads[load_key] = current_load + qty_tons
                restored += 1
                placed = True
                break

        if not placed:
            skipped += 1

    frappe.db.commit()
    return {"restored_count": restored, "skipped_count": skipped}

@frappe.whitelist()
def delete_maintenance_and_cascade(maintenance_record_name):
    """
    Delete a maintenance record and restore previously moved orders backward.
    This is called from the frontend when user clicks "Remove" on maintenance.
    """
    if not maintenance_record_name:
        return {"status": "error", "message": "No maintenance record specified"}
    
    # Fetch maintenance record details before deletion
    maint_doc = frappe.db.get_value(
        "Equipment Maintenance",
        maintenance_record_name,
        ["unit", "start_date", "end_date", "notes", "maintenance_type"],
        as_dict=True
    )
    
    if not maint_doc:
        return {"status": "error", "message": "Maintenance record not found"}
    
    unit = maint_doc.get("unit")
    start_date = maint_doc.get("start_date")
    end_date = maint_doc.get("end_date")
    notes = maint_doc.get("notes")
    maintenance_type = maint_doc.get("maintenance_type")
    movement_log = frappe.cache().get_value(f"maintenance_cascade_log::{maintenance_record_name}") or _extract_maintenance_cascade_log(notes)
    
    # Delete the maintenance record
    frappe.delete_doc("Equipment Maintenance", maintenance_record_name)

    if _is_non_blocking_maintenance_type(maintenance_type):
        try:
            frappe.cache().delete_value(f"maintenance_cascade_log::{maintenance_record_name}")
        except Exception:
            pass
        return {
            "status": "success",
            "message": "Maintenance removed.",
            "restored_count": 0,
            "skipped_count": 0
        }

    restore_result = _restore_orders_to_original_dates(unit, movement_log)
    if restore_result.get("restored_count", 0) == 0:
        fallback = _fallback_restore_by_range(unit, start_date, end_date)
        restore_result["restored_count"] = restore_result.get("restored_count", 0) + fallback.get("restored_count", 0)
        restore_result["skipped_count"] = restore_result.get("skipped_count", 0) + fallback.get("skipped_count", 0)

    try:
        frappe.cache().delete_value(f"maintenance_cascade_log::{maintenance_record_name}")
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Maintenance removed. Restored {restore_result.get('restored_count', 0)} items to original dates.",
        "restored_count": restore_result.get("restored_count", 0),
        "skipped_count": restore_result.get("skipped_count", 0)
    }

@frappe.whitelist()
def get_all_equipment_maintenance(start_date=None, end_date=None):
    """Get all maintenance records, optionally filtered by date range."""
    if not frappe.db.exists("DocType", "Equipment Maintenance"):
        return []
    
    if start_date and end_date:
        # Find records that overlap with the date range
        records = frappe.db.sql("""
            SELECT name, unit, maintenance_type, start_date, end_date, status, notes
            FROM `tabEquipment Maintenance`
            WHERE start_date <= %s
              AND end_date >= %s
              AND docstatus < 2
            ORDER BY unit, start_date
        """, (end_date, start_date), as_dict=True)
        return records
    else:
        records = frappe.get_all("Equipment Maintenance",
            filters={"docstatus": ["<", 2]},
            fields=["name", "unit", "maintenance_type", "start_date", "end_date", "status", "notes"],
            order_by="unit, start_date"
        )
        return records

def find_best_slot(item_qty_tons, quality, preferred_unit, start_date, recursion_depth=0):
    """
    Recursive function to find the best available slot (Date/Unit).
    Order:
    1. Preferred Unit (on Date)
    2. Neighbor Units (on Date) - Must support Quality
    3. Next Day (Recurse)
    """
    if recursion_depth > 30: # Look ahead max 30 days
        return None # No slot found

    check_date = getdate(start_date)
    
    # 1. Check Preferred Unit
    if preferred_unit and preferred_unit in HARD_LIMITS:
        current_load = get_unit_load(check_date, preferred_unit)
        if current_load + item_qty_tons <= HARD_LIMITS[preferred_unit]:
            return {"date": check_date, "unit": preferred_unit}

    # 2. Check Neighbor Units (on same date)
    compatible_units = []
    for unit, valid_qualities in UNIT_QUALITY_MAP.items():
        if unit == preferred_unit: continue
        if quality in valid_qualities:
            compatible_units.append(unit)
    
    # Check Neighbors
    for unit in ["Unit 1", "Unit 2", "Unit 3", "Unit 4"]:
        if unit in compatible_units and unit in HARD_LIMITS:
            load = get_unit_load(check_date, unit)
            if load + item_qty_tons <= HARD_LIMITS[unit]:
                return {"date": check_date, "unit": unit}

    # 3. Next Day (Recurse)
    next_date = frappe.utils.add_days(check_date, 1)
    return find_best_slot(item_qty_tons, quality, preferred_unit, next_date, recursion_depth + 1)


def get_preferred_unit(quality):
    """
    Determines the best unit for an item when width info is not available.
    Since ANY quality can run on ANY unit now, just return Unit 1 as default.
    Width-based assignment is handled in _populate_planning_sheet_items and frontend autoAllocate.
    """
    return "Unit 1"


def generate_plan_code(date_str, unit, plan_name):
    """
    Generates a readable plan code: {YY}{MonthLetter}{Unit}-{PlanName}
    e.g. 26CU1-PLAN 1
    UNASSIGNED uses segment UA. Legacy Mixed normalizes to UNASSIGNED before this runs.
    """
    if not str(date_str) or not plan_name or not unit:
        return ""
    
    try:
        # Robust unit normalization for code generation
        u_clean = str(unit).upper().replace(" ", "")
        if "UNIT1" in u_clean:
            u_code = "U1"
        elif "UNIT2" in u_clean:
            u_code = "U2"
        elif "UNIT3" in u_clean:
            u_code = "U3"
        elif "UNIT4" in u_clean:
            u_code = "U4"
        elif u_clean in ("UNASSIGNED", "NONE", "NA") or "MIXED" in u_clean:
            u_code = "UA"
        else:
            return ""

        d = frappe.utils.getdate(str(date_str))
        yy = str(d.year)[-2:]
        # Month letters mapping (A-L)
        month_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
        month_char = month_letters[d.month - 1]
        
        # Strip Month/Week prefix (e.g., "MARCH W10 26 PLAN 1" -> "PLAN 1")
        clean_plan = _strip_legacy_prefixes(plan_name)
        
        return f"{yy}{month_char}{u_code}-{clean_plan}"
    except Exception:
        return ""

def update_sheet_plan_codes(sheet_doc, include_legacy=False):
    """
    Sets plan codes on board rows (`plan_name` + `custom_plan_code`) and on legacy `items`
    (`custom_plan_code` — the field shown as Plan Code on Planning sheet Item).
    Aligns with color chart / active plan name + date + unit segment.
    """
    sheet_date = sheet_doc.get("custom_planned_date") or sheet_doc.get("ordered_date")
    active_plan = sheet_doc.get("custom_plan_name") or "Default"

    unique_codes = set()

    def _row_unit(raw):
        item_unit = raw
        if item_unit:
            iu_upper = str(item_unit).upper().replace(" ", "")
            if "UNIT1" in iu_upper:
                item_unit = "Unit 1"
            elif "UNIT2" in iu_upper:
                item_unit = "Unit 2"
            elif "UNIT3" in iu_upper:
                item_unit = "Unit 3"
            elif "UNIT4" in iu_upper:
                item_unit = "Unit 4"
        return normalize_planning_unit_for_select(item_unit)

    def _row_planned_date(item):
        if isinstance(item, dict):
            return (
                item.get("planned_date")
                or item.get("custom_item_planned_date")
                or sheet_date
            )
        return (
            getattr(item, "planned_date", None)
            or getattr(item, "custom_item_planned_date", None)
            or sheet_date
        )

    def _item_unit_raw(item):
        if isinstance(item, dict):
            return item.get("unit")
        return getattr(item, "unit", None)

    def _calc_code_for_item(item):
        item_unit = _row_unit(_item_unit_raw(item))
        item_date = _row_planned_date(item)
        return generate_plan_code(item_date, item_unit, active_plan)

    def _apply_code_to_row(item, code):
        """Set only fields that exist on the child DocType (Planning sheet Item vs Planning Table)."""
        dt = getattr(item, "doctype", None)
        if not dt:
            return
        meta = frappe.get_meta(dt)
        if meta.has_field("custom_plan_code"):
            item.custom_plan_code = code
        if meta.has_field("plan_name"):
            item.plan_name = code

    if include_legacy:
        for item in sheet_doc.get("items", []):
            code = _calc_code_for_item(item)
            _apply_code_to_row(item, code)
            if code:
                unique_codes.add(code)

    # New table (Planning Table) -- check all possible fieldnames
    for tf in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
        new_items = sheet_doc.get(tf)
        if new_items:
            for item in new_items:
                code = _calc_code_for_item(item)
                _apply_code_to_row(item, code)
                if code:
                    unique_codes.add(code)
            break

    if unique_codes:
        sheet_doc.custom_plan_code = ", ".join(sorted(unique_codes))
    elif getattr(sheet_doc, "custom_plan_code", None) is None:
        sheet_doc.custom_plan_code = ""


@frappe.whitelist()
def update_sequence(items):
    """
    Updates the 'idx' of items based on the provided list.
    items: [{"name": "item_name", "idx": 1}, ...]
    """
    import json
    if isinstance(items, str):
        items = json.loads(items)
        
    for item in items:
        if item.get("name") and item.get("idx") is not None:
            # Use SQL to bypass DocStatus immutability for reordering
            frappe.db.sql("""
                UPDATE `tabPlanning Table`
                SET idx = %s
                WHERE name = %s
            """, (item.get("idx"), item.get("name")))
            
    frappe.db.commit()
    return {"status": "success"}


@frappe.whitelist()
def update_schedule(item_name, unit, date, index=0, force_move=0, perform_split=0, plan_name=None, strict_next_day=0):
    """
    Moves a specific Planning Sheet Item to a new unit/date.
    If date changes, the item is re-parented to a suitable Planning Sheet for that date.
    """
    target_date = getdate(date)
    force_move = flt(force_move)
    perform_split = flt(perform_split)
    strict_next_day = flt(strict_next_day)
    unit = normalize_planning_unit_for_select(unit)

    # 1. Get Item and Parent Details
    item = frappe.get_doc("Planning Table", item_name)
    parent_sheet = frappe.get_doc("Planning sheet", item.parent)
    
    # 2. Docstatus check ΓÇö allow movement even from submitted sheets
    # (user requested free movement; we use raw SQL to bypass Frappe immutability)

    item_wt_tons = flt(item.qty) / 1000.0
    quality = item.custom_quality or ""
    
    # QUALITY ENFORCEMENT
    if not is_quality_allowed(unit, quality):
        frappe.throw(_("Quality <b>{}</b> is not allowed in <b>{}</b>.").format(quality, unit))

    # 3. Check Capacity of Target Slot (scoped to this item's plan)
    current_load = get_unit_load(target_date, unit, plan_name=plan_name or parent_sheet.get("custom_plan_name") or "Default")
    limit = HARD_LIMITS.get(unit, 999.0)
    
    # Moving within same date (even to different unit): subtract item's own weight
    # to avoid double-counting it and causing false overflow / duplicate creation
    current_effective_date = getdate(item.get("planned_date") or parent_sheet.get("custom_planned_date") or parent_sheet.ordered_date)
    is_same_date = (str(current_effective_date) == str(target_date))
    if is_same_date and item.unit == unit:
        # Same date + same unit: pure reorder, load stays same
        load_for_check = current_load
    elif is_same_date:
        # Same date, different unit: item moves FROM old unit TO new unit.
        # Don't count the item's own weight in the old unit's load ΓÇö only the new unit's load matters
        load_for_check = current_load + item_wt_tons
    else:
        # Different date: full new load
        load_for_check = current_load + item_wt_tons

    if load_for_check > limit:
        # Exceeds Capacity
        available_space = max(0, limit - current_load)
        
        # Scenario A: SMART MOVE (find best slot - checks neighbor units first, then next day)
        if force_move:
            best_slot = find_best_slot(item_wt_tons, quality, unit, target_date)
            if not best_slot:
                frappe.throw(_("Could not find a valid slot on future dates."))
            final_unit = best_slot["unit"]
            final_date = getdate(best_slot["date"])
            
        # Scenario A2: STRICT NEXT DAY (same unit, next day - re-check capacity)
        elif strict_next_day:
            next_day = frappe.utils.add_days(target_date, 1)
            next_load = get_unit_load(next_day, unit)
            next_limit = HARD_LIMITS.get(unit, 999.0)
            
            if next_load + item_wt_tons > next_limit:
                # Next day also full ΓÇö ask user again
                return {
                    "status": "overflow",
                    "available": max(0, next_limit - next_load),
                    "limit": next_limit,
                    "current_load": next_load,
                    "order_weight": item_wt_tons,
                    "target_date": str(next_day),
                    "target_unit": unit,
                    "message": f"Next day ({next_day}) is also full for {unit}"
                }
            else:
                final_unit = unit
                final_date = next_day
            
        # Scenario B: SMART SPLIT
        elif perform_split:
            if available_space < 0.1:
                frappe.throw(_("Available space ({:.3f}T) is too small to split (Min 0.1T).").format(available_space))
            
            # Split qty stays on the target slot; remainder goes to find_best_slot — decide *that* before legacy logic.
            original_board_qty = flt(item.qty)
            remainder_qty = original_board_qty - (available_space * 1000.0)
            split_qty = available_space * 1000.0

            best_slot_rem = find_best_slot(remainder_qty / 1000.0, quality, unit, target_date)
            if not best_slot_rem:
                frappe.throw(_("Could not find slot for remaining quantity."))

            nu_rem = normalize_planning_unit_for_select(best_slot_rem.get("unit"))
            nu_split = normalize_planning_unit_for_select(unit)
            # Only add a second Planning sheet Item row when remainder and split piece land on different units.
            units_differ = nu_rem != nu_split

            # Update Original Item -> remainder; will be moved to best_slot_rem below
            item.qty = remainder_qty
            item.is_split = 1
            item.save()

            parent_name = item.parent
            legacy_table = "Planning sheet Item"
            new_legacy_name = None
            src_psi = _resolve_planning_table_source_item_link(item.get("source_item"), item.name)
            if src_psi and frappe.db.exists(legacy_table, src_psi):
                if units_differ:
                    frappe.db.set_value(legacy_table, src_psi, "qty", flt(remainder_qty))
                    old_legacy_doc = frappe.get_doc(legacy_table, src_psi)
                    new_legacy_doc = frappe.copy_doc(old_legacy_doc)
                    new_legacy_doc.name = None
                    new_legacy_doc.qty = flt(split_qty)
                    new_legacy_doc.unit = nu_split
                    new_legacy_doc.insert(ignore_permissions=True)
                    new_legacy_name = new_legacy_doc.name
                else:
                    frappe.db.set_value(
                        legacy_table,
                        src_psi,
                        {"unit": nu_rem, "qty": original_board_qty},
                    )

            max_idx = frappe.db.sql(
                "SELECT MAX(idx) FROM `tabPlanning Table` WHERE parent = %s", (parent_name,)
            )
            new_idx = int(max_idx[0][0] or 0) + 1 if max_idx and max_idx[0][0] else 1

            new_row_doc = frappe.new_doc("Planning Table")
            for field in item.meta.fields:
                if field.fieldtype not in ("Section Break", "Column Break", "Table") and field.fieldname not in ("name", "idx", "parent", "parentfield", "parenttype"):
                    new_row_doc.set(field.fieldname, item.get(field.fieldname))
            new_row_doc.parent = parent_name
            new_row_doc.parentfield = _get_pt_parentfield()
            new_row_doc.parenttype = "Planning sheet"
            new_row_doc.idx = new_idx
            new_row_doc.qty = flt(split_qty)
            new_row_doc.unit = unit
            new_row_doc.is_split = 1
            new_row_doc.split_from = item.name
            split_code = generate_plan_code(
                target_date,
                normalize_planning_unit_for_select(unit),
                (parent_sheet.get("custom_plan_name") or "Default"),
            )
            if frappe.db.has_column("Planning Table", "plan_name"):
                new_row_doc.plan_name = split_code
            if frappe.db.has_column("Planning Table", "custom_plan_code"):
                new_row_doc.custom_plan_code = split_code
            # New split line represents remaining/new queue work; never carry old SPR link.
            if frappe.db.has_column("Planning Table", "spr_name"):
                new_row_doc.spr_name = ""
            if new_legacy_name and src_psi and units_differ:
                new_row_doc.source_item = new_legacy_name
            else:
                new_row_doc.source_item = src_psi or _resolve_planning_table_source_item_link(
                    item.get("source_item"), item.name
                )
            new_row_doc.insert(ignore_permissions=True)

            frappe.db.commit()

            _move_item_to_slot(item, best_slot_rem["unit"], best_slot_rem["date"], None, plan_name)

            frappe.db.commit()
            try:
                frappe.publish_realtime("production_board_update", {"date": str(best_slot_rem["date"])})
            except Exception:
                pass
            return {"status": "success", "message": "Split successful"}
            
        else:
            # Scenario C: OVERFLOW (Ask User)
            return {
                "status": "overflow",
                "available": available_space,
                "limit": limit,
                "current_load": current_load,
                "order_weight": item_wt_tons
            }
    else:
        final_unit = unit
        final_date = target_date

    # 4. Perform Move
    # Convert index to int if provided
    idx_val = int(index) if index else None
    # If index is 0/None, maybe append? 
    # User drags to specific position. index is the new index in the list.
    # We should respect it.
    
    _move_item_to_slot(item, final_unit, final_date, idx_val, plan_name)
    
    frappe.db.commit()
    try:
        frappe.publish_realtime("production_board_update", {"date": str(final_date)})
    except Exception:
        pass
    return {
        "status": "success", 
        "moved_to": {"date": final_date, "unit": final_unit}
    }

def _planning_sheet_item_so_line_column():
    """Column on Planning sheet Item that links to the Sales Order line (for merge logic)."""
    if frappe.db.has_column("Planning sheet Item", "sales_order_item"):
        return "sales_order_item"
    if frappe.db.has_column("Planning sheet Item", "so_item"):
        return "so_item"
    return None


def _sync_legacy_planning_sheet_item_unit(source_item, unit):
    """After a board move, mirror only `unit` onto Planning sheet Item (SO snapshot grid)."""
    name = (source_item or "").strip()
    if not name or not frappe.db.exists("Planning sheet Item", name):
        return
    if not frappe.db.has_column("Planning sheet Item", "unit"):
        return
    unit = normalize_planning_unit_for_select(unit)
    frappe.db.sql(
        "UPDATE `tabPlanning sheet Item` SET unit = %s WHERE name = %s",
        (unit, name),
    )


def _legacy_psi_has_board_on_unit(sheet_parent, psi_name, target_unit):
    """True if any Planning Table row on this sheet links to this PSI with the given normalized unit."""
    if not sheet_parent or not psi_name:
        return False
    nu_t = normalize_planning_unit_for_select(target_unit)
    rows = frappe.get_all(
        "Planning Table",
        filters={"parent": sheet_parent, "source_item": psi_name},
        fields=["unit"],
    )
    for r in rows:
        if normalize_planning_unit_for_select(r.unit) == nu_t:
            return True
    return False


def _merge_reunited_legacy_psi_rows(sheet_parent):
    """Merge duplicate Planning sheet Item rows when all board rows for that group are on one unit again.

    Groups by sales-order line when `so_item` / `sales_order_item` is set; otherwise by `item_code` on the
    same sheet (splits often lose the SO line link on cloned PSI rows).
    """
    legacy_table = "Planning sheet Item"
    if not sheet_parent:
        return

    so_col = _planning_sheet_item_so_line_column()
    fields = ["name", "qty", "item_code"]
    if so_col:
        fields.append(so_col)

    all_rows = frappe.get_all(
        legacy_table,
        filters={"parent": sheet_parent},
        fields=fields,
    )
    from collections import defaultdict

    def _try_merge_group(lst):
        if len(lst) < 2:
            return
        names_with_pts = []
        for row in lst:
            pts = frappe.get_all(
                "Planning Table",
                filters={"parent": sheet_parent, "source_item": row.name},
                fields=["unit"],
            )
            if not pts:
                continue
            names_with_pts.append((row.name, pts))
        if len(names_with_pts) < 2:
            return

        union_units = set()
        for _n, pts in names_with_pts:
            for p in pts:
                union_units.add(normalize_planning_unit_for_select(p.unit))
        if len(union_units) != 1:
            return

        u_only = list(union_units)[0]
        psi_names = [n for n, _pts in names_with_pts]
        keeper = min(psi_names)
        others = [n for n in psi_names if n != keeper]

        merged_qty = flt(frappe.db.get_value(legacy_table, keeper, "qty"))
        for o in others:
            merged_qty += flt(frappe.db.get_value(legacy_table, o, "qty"))
            frappe.db.sql(
                """
                UPDATE `tabPlanning Table`
                SET source_item=%s
                WHERE parent=%s AND source_item=%s
                """,
                (keeper, sheet_parent, o),
            )
            frappe.db.sql(f"DELETE FROM `tab{legacy_table}` WHERE name=%s", (o,))
        frappe.db.set_value(
            legacy_table,
            keeper,
            {"qty": merged_qty, "unit": u_only},
        )

    # 1) Same SO line (preferred)
    if so_col:
        by_so = defaultdict(list)
        for r in all_rows:
            key = str(r.get(so_col) or "").strip()
            if key:
                by_so[key].append(r)
        for lst in by_so.values():
            _try_merge_group(lst)

    # 2) Same item_code on this sheet when SO line is blank (common after split / clone)
    by_item = defaultdict(list)
    for r in all_rows:
        if so_col and str(r.get(so_col) or "").strip():
            continue
        ic = str(r.get("item_code") or "").strip()
        if ic:
            by_item[ic].append(r)
    for lst in by_item.values():
        _try_merge_group(lst)


def _resolve_planning_table_source_item_link(source_item_value, board_row_name=None):
    """Planning Table.source_item must link to Planning sheet Item. Board row ids often get stored by mistake.

    Walk Planning Table.source_item chains until a valid Planning sheet Item is found.
    """
    def _walk(cur):
        cur = (cur or "").strip()
        for _ in range(8):
            if not cur:
                return None
            if frappe.db.exists("Planning sheet Item", cur):
                return cur
            if frappe.db.exists("Planning Table", cur):
                cur = frappe.db.get_value("Planning Table", cur, "source_item") or ""
                continue
            return None
        return None

    out = _walk(source_item_value)
    if out:
        return out
    if board_row_name:
        return _walk(board_row_name)
    return None


def _move_item_to_slot(item_doc, unit, date, new_idx=None, plan_name=None):
    """Internal helper to move a Planning Sheet Item to a specific slot.
    Re-parents item if date changes, avoiding moving the entire order."""
    unit = normalize_planning_unit_for_select(unit)
    target_date = getdate(date)
    source_parent = frappe.get_doc("Planning sheet", item_doc.parent)
    
    source_effective_date = getdate(source_parent.get("custom_planned_date") or source_parent.ordered_date)
    
    # 1. Date Reparenting (Disabled Per User Request)
    # The user explicitly requested "NEVER ALLOW NEW PLANNING SHEET" and "ALWASY USE EXISTING PLANNING SHEET".
    # Therefore, we do not reparent items to new sheets when their date changes.
    # We rely solely on updating the `planned_date` at the item level below.

    # 2. DUAL TABLE SYNC: Planning Table <-> Planning sheet Item (legacy grid)
    # When split rows share one legacy PSI and move to different units, clone the legacy row.
    # When two legacy rows for the same SO line end up on the same unit again, merge them.
    legacy_table = "Planning sheet Item"
    if item_doc.get("source_item") and frappe.db.exists(legacy_table, item_doc.source_item):
        siblings = frappe.get_all(
            "Planning Table",
            filters={"source_item": item_doc.source_item, "name": ["!=", item_doc.name]},
            fields=["name", "unit"],
        )
        # No other Planning Table rows share this legacy PSI (e.g. sole split leaving Unassigned): only sync legacy unit.
        if siblings:
            s0 = normalize_planning_unit_for_select(siblings[0].unit or "")
            if normalize_planning_unit_for_select(unit) != s0:
                old_legacy_doc = frappe.get_doc(legacy_table, item_doc.source_item)
                new_legacy_doc = frappe.copy_doc(old_legacy_doc)
                new_legacy_doc.name = None
                new_legacy_doc.qty = flt(item_doc.qty)
                new_legacy_doc.unit = unit
                new_legacy_doc.insert(ignore_permissions=True)
                new_orig_qty = max(0, flt(old_legacy_doc.qty) - flt(item_doc.qty))
                frappe.db.set_value(legacy_table, old_legacy_doc.name, "qty", new_orig_qty)
                item_doc.source_item = new_legacy_doc.name
            else:
                _sync_legacy_planning_sheet_item_unit(item_doc.get("source_item"), unit)
        else:
            _sync_legacy_planning_sheet_item_unit(item_doc.get("source_item"), unit)

        try:
            cur_legacy = frappe.get_doc(legacy_table, item_doc.source_item)
            so_col = _planning_sheet_item_so_line_column()
            so_item = (cur_legacy.get(so_col) if so_col else None) or ""
            so_item = str(so_item or "").strip()
            legacy_parent = cur_legacy.parent
            if so_col and so_item and legacy_parent:
                # Same SO line can have multiple Planning sheet Item rows after splits. Merge when they
                # represent the same unit again. Do not rely only on legacy `unit` — it often lags the board.
                dupes_all = frappe.db.sql(
                    f"""
                    SELECT name, qty, unit FROM `tab{legacy_table}`
                    WHERE parent = %s AND `{so_col}` = %s AND name != %s
                    """,
                    (legacy_parent, so_item, cur_legacy.name),
                    as_dict=True,
                )
                dupes = []
                for d in dupes_all or []:
                    nu_row = normalize_planning_unit_for_select(d.get("unit"))
                    if nu_row == unit:
                        dupes.append(d)
                    elif _legacy_psi_has_board_on_unit(legacy_parent, d.name, unit):
                        dupes.append(d)
                if dupes:
                    merged_qty = flt(cur_legacy.qty)
                    for d in dupes:
                        merged_qty += flt(d.qty)
                        frappe.db.sql(
                            "UPDATE `tabPlanning Table` SET source_item = %s WHERE source_item = %s",
                            (cur_legacy.name, d.name),
                        )
                        frappe.db.sql(f"DELETE FROM `tab{legacy_table}` WHERE name = %s", (d.name,))
                    frappe.db.set_value(
                        legacy_table,
                        cur_legacy.name,
                        {"qty": merged_qty, "unit": unit},
                    )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Legacy merge error")

        frappe.db.commit()

    # 3. Handle IDX Shifting if inserting at specific position
    # Update Item unit and parent first — use raw SQL to bypass docstatus immutability

    update_fields = {"unit": unit, "source_item": item_doc.source_item}
    if frappe.db.has_column("Planning Table", "planned_date"):
        update_fields["planned_date"] = target_date
    move_code = generate_plan_code(
        target_date,
        normalize_planning_unit_for_select(unit),
        (source_parent.get("custom_plan_name") or "Default"),
    )
    if frappe.db.has_column("Planning Table", "plan_name"):
        update_fields["plan_name"] = move_code
    if frappe.db.has_column("Planning Table", "custom_plan_code"):
        update_fields["custom_plan_code"] = move_code
    # Moving to a different production date starts a new run context; old SPR must not flow forward.
    if frappe.db.has_column("Planning Table", "spr_name"):
        date_changed = str(source_effective_date) != str(target_date)
        if date_changed:
            update_fields["spr_name"] = ""
    set_clause = ", ".join([f"`{k}` = %s" for k in update_fields.keys()])
    frappe.db.sql(
        f"UPDATE `tabPlanning Table` SET {set_clause} WHERE name = %s",
        list(update_fields.values()) + [item_doc.name]
    )
    frappe.db.commit() # FORCE SAVE FOR BOARD
    item_doc.unit = unit

    try:
        _merge_reunited_legacy_psi_rows(item_doc.parent)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "merge reunited legacy PSI")

    if new_idx is not None:
        try:
            eff = _effective_date_expr("sheet")
            
            # Re-load the current parent to ensure we use the TARGET sheet's plan
            target_parent = frappe.get_doc("Planning sheet", item_doc.parent)
            pb_plan = target_parent.get("custom_pb_plan_name") or ""
            if pb_plan:
                pb_cond = "AND sheet.custom_pb_plan_name = %(pb_plan)s"
            else:
                pb_cond = "AND (sheet.custom_pb_plan_name IS NULL OR sheet.custom_pb_plan_name = '')"

            sql_fetch = f"""
                SELECT item.name 
                FROM `tabPlanning Table` item
                JOIN `tabPlanning sheet` sheet ON item.parent = sheet.name
                WHERE {eff} = %(target_date)s AND item.unit = %(unit)s AND item.name != %(item_name)s
                {pb_cond}
                ORDER BY item.idx ASC, item.creation ASC
            """
            params = {
                "target_date": target_date,
                "unit": unit,
                "item_name": item_doc.name,
            }
            if pb_plan:
                params["pb_plan"] = pb_plan

            other_items = frappe.db.sql(sql_fetch, params)
            others = [r[0] for r in other_items]
            
            insert_pos = max(0, new_idx - 1)
            others.insert(insert_pos, item_doc.name)
            
            for i, name in enumerate(others):
                frappe.db.sql(
                    "UPDATE `tabPlanning Table` SET idx = %s WHERE name = %s",
                    (i + 1, name),
                )
        except Exception as e:
            frappe.log_error(f"Global Sequence Fix Error: {str(e)}")

    # 3. Update Plan Codes for Affected Sheets (Planning Table only)
    for sheet_name in set([source_parent.name, item_doc.parent]):
        if frappe.db.exists("Planning sheet", sheet_name):
            doc_sheet = frappe.get_doc("Planning sheet", sheet_name, ignore_cache=True)
            update_sheet_plan_codes(doc_sheet)
            frappe.db.sql("UPDATE `tabPlanning sheet` SET custom_plan_code = %s WHERE name = %s", (doc_sheet.custom_plan_code, doc_sheet.name))

            for tf in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
                new_items = doc_sheet.get(tf)
                if new_items:
                    for d in new_items:
                        if d.get("plan_name"):
                            frappe.db.sql("UPDATE `tabPlanning Table` SET plan_name = %s WHERE name = %s", (d.plan_name, d.name))
                    break

@frappe.whitelist()
def get_kanban_board(start_date, end_date):
    start_date = getdate(start_date)
    end_date = getdate(end_date)
    
    sheets = frappe.get_all(
        "Planning sheet",
        filters={
            "ordered_date": ["between", [start_date, end_date]],
            "docstatus": ["<", 2]
        },
        fields=["name", "customer", "party_code", "ordered_date", "dod", "planning_status", "docstatus"],
        order_by="ordered_date asc"
    )
    
    data = []
    for sheet in sheets:
        items = frappe.get_all(
            "Planning Table",
            filters={"parent": sheet.name},
            fields=["qty", "unit", "custom_quality", "color", "gsm"],
            order_by="idx"
        )
        
        # Map custom_quality to quality for frontend consistency
        for item in items:
            item["quality"] = item.get("custom_quality")

        total_weight = sum([flt(d.qty) for d in items])
        
        # Determine Major Unit
        unit = "Unit 1" # Default
        if items:
            # Get most frequent unit
            units = [d.unit for d in items if d.unit]
            if units:
                unit = max(set(units), key=units.count)
        
        data.append({
            "name": sheet.name,
            "customer": sheet.customer,
            "party_code": sheet.party_code,
            "ordered_date": sheet.ordered_date,
            "dod": sheet.dod,
            "planning_status": sheet.planning_status,
            "docstatus": sheet.docstatus,
            "unit": unit,
            "total_weight": total_weight,
            "items": items
        })
        
    return data

# ... (Existing get_color_chart_data, update_item_unit, update_items_bulk, etc. - UNCHANGED) ...
# I will retain them in the file content if I am replacing strict block, but if I am replacing a range I need to be careful.
# The previous `update_schedule` ended at line 165. `get_color_chart_data` followed.
# I am targeting `HARD_LIMITS` definition (line 6) down to `update_schedule` end?
# Wait, `HARD_LIMITS` is at the top. I should probably insert the helper functions and replace `update_schedule`.
# `create_planning_sheet_from_so` is further down (line 636).
# I will make TWO edits.
# 1. Replace `update_schedule` and add helpers. (This step)
# 2. Update `create_planning_sheet_from_so`.

# Actually, I can do `create_planning_sheet_from_so` implementation now if I include it in the replacement chunk
# But it's far away. I'll stick to `update_schedule` and helpers first.
# Wait, I need `UNIT_QUALITY_MAP` for `create_planning_sheet_from_so` too.
# I'll define it globally.

# The `update_schedule` function in original file is lines 95-164.
# `HARD_LIMITS` is 6-11.
# I will replace from `HARD_LIMITS` (line 6) to the end of `update_schedule` (line 164).
# And keep `get_kanban_board` (lines 33-91) ??
# Ah, `get_kanban_board` is in between `get_unit_load` and `update_schedule`.
# Ref:
# 6-18: Limits
# 21-30: get_unit_load
# 33-91: get_kanban_board
# 94-164: update_schedule

# So I should:
# 1. Update Limits and Add Helpers at top? Or just replace `update_schedule` and add helpers there?
# Python allows defining helpers anywhere ensuring usage is after def? No, order matters if running script but inside module it's fine.
# But `find_best_slot` needs `UNIT_QUALITY_MAP`.
# I'll put `UNIT_QUALITY_MAP` near `HARD_LIMITS`.

# Strategy:
# Replace Lines 6-30 (Limits + get_unit_load) with New Limits + Map + Helpers.
# Replace Lines 94-164 (update_schedule) with New `update_schedule`.

# Let's do it in one go if possible? No, `get_kanban_board` is in the middle.
# I will use `multi_replace_file_content`.

# ... (get_color_chart_data etc are below 164)
# Sequence Management Functions for Color Chart Approval

@frappe.whitelist()
def get_color_sequence(date, unit, plan_name="Default"):
    """Retrieves the saved sequence and status for a unit/plan on a given date."""
    name = f"CSA-{plan_name}-{unit}-{date}"
    if frappe.db.exists("Color Sequence Approval", name):
        doc = frappe.get_doc("Color Sequence Approval", name)
        return {
            "sequence": json.loads(doc.sequence_data) if doc.sequence_data else [],
            "status": doc.status,
            "modified": doc.modified,
            "modified_by": doc.modified_by
        }
    return {"sequence": [], "status": "Draft", "modified": None, "modified_by": None}

@frappe.whitelist()
def get_color_sequences_range(start_date, end_date, unit=None, plan_name="__all__"):
    """Fetches all color sequences for a range of dates and units."""
    try:
        filters = {
            "date": ["between", [start_date, end_date]]
        }
        if unit and unit != "All Units":
            filters["unit"] = _normalize_unit(unit)
        if plan_name and plan_name != "__all__":
            filters["plan_name"] = plan_name
            
        sequences = frappe.get_all("Color Sequence Approval", 
            filters=filters, 
            fields=["name", "date", "unit", "plan_name", "sequence_data", "status"],
            order_by="modified desc"
        )
        
        result = {}
        for s in sequences:
            # Key by unit-date for easy frontend lookup
            key = f"{s.unit}-{s.date}"
            # Keep first seen entry (latest modified due to order_by).
            if key in result:
                continue
            try:
                seq = json.loads(s.sequence_data) if s.sequence_data else []
            except Exception:
                seq = []
            result[key] = {
                "sequence": seq,
                "status": s.status
            }
        return result
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_color_sequences_range_error")
        return {}

@frappe.whitelist()
def save_color_sequence(date, unit, sequence_data, plan_name="Default", new_date=None):
    """Saves the color arrangement. Handles date changes by renaming the document."""
    unit = _normalize_unit(unit)
    name = f"CSA-{plan_name}-{unit}-{date}"
    
    # Handle date change (renaming)
    if new_date and new_date != date:
        if frappe.db.exists("Color Sequence Approval", name):
            new_name = f"CSA-{plan_name}-{unit}-{new_date}"
            if frappe.db.exists("Color Sequence Approval", new_name):
                frappe.throw(_("An arrangement already exists for {0} on {1} ({2}).").format(unit, new_date, plan_name))
            
            # Rename the document to maintain the name pattern
            frappe.rename_doc("Color Sequence Approval", name, new_name)
            name = new_name
            date = new_date

    if not frappe.db.exists("Color Sequence Approval", name):
        doc = frappe.new_doc("Color Sequence Approval")
        doc.date = date
        doc.unit = unit
        doc.plan_name = plan_name
        doc.status = "Draft"
    else:
        doc = frappe.get_doc("Color Sequence Approval", name)
        # Keep a rollback snapshot of previous sequence before overwrite.
        try:
            _append_sequence_history(date, unit, plan_name, doc.sequence_data, doc.status)
        except Exception:
            pass
        # Update the internal date field just in case
        doc.date = date
    
    if isinstance(sequence_data, str):
        doc.sequence_data = sequence_data
    else:
        doc.sequence_data = json.dumps(sequence_data)
        
    doc.save()
    frappe.db.commit()
    return {"status": "success", "name": name, "date": date}


def _sequence_history_key(date, unit, plan_name):
    return f"production_sequence_history::{plan_name}::{_normalize_unit(unit)}::{date}"


def _append_sequence_history(date, unit, plan_name, sequence_data, status=None):
    """
    Store compact sequence history in defaults for rollback.
    Keeps most recent 20 snapshots per date/unit/plan.
    """
    if not sequence_data:
        return
    key = _sequence_history_key(date, unit, plan_name or "Default")
    raw = frappe.defaults.get_global_default(key) or "[]"
    try:
        arr = json.loads(raw) if raw else []
    except Exception:
        arr = []
    arr.append({
        "ts": frappe.utils.now(),
        "by": frappe.session.user,
        "status": status or "Draft",
        "sequence_data": sequence_data if isinstance(sequence_data, str) else json.dumps(sequence_data),
    })
    if len(arr) > 20:
        arr = arr[-20:]
    frappe.defaults.set_global_default(key, json.dumps(arr))


@frappe.whitelist()
def restore_last_color_sequence(date, unit, plan_name="Default"):
    """
    Restore previous saved sequence snapshot for a specific unit/date/plan.
    """
    unit = _normalize_unit(unit)
    key = _sequence_history_key(date, unit, plan_name)
    raw = frappe.defaults.get_global_default(key) or "[]"
    try:
        arr = json.loads(raw) if raw else []
    except Exception:
        arr = []
    if not arr:
        return {"status": "error", "message": f"No saved history for {unit} on {date}"}

    last = arr.pop()
    frappe.defaults.set_global_default(key, json.dumps(arr))
    return save_color_sequence(
        date=date,
        unit=unit,
        sequence_data=last.get("sequence_data") or "[]",
        plan_name=plan_name,
    )

@frappe.whitelist()
def request_sequence_approval(date, unit, plan_name="Default"):
    """Users call this to move sequence to 'Pending Approval'."""
    unit = _normalize_unit(unit)
    name = f"CSA-{plan_name}-{unit}-{date}"
    if not frappe.db.exists("Color Sequence Approval", name):
        frappe.throw(_("Please save the sequence before requesting approval."))
    
    frappe.db.set_value("Color Sequence Approval", name, "status", "Pending Approval", update_modified=True)
    frappe.db.commit()
    return {"status": "success"}

@frappe.whitelist()
def approve_sequence(date, unit, plan_name="Default"):
    """Managers call this to approve the sequence."""
    unit = _normalize_unit(unit)
    name = f"CSA-{plan_name}-{unit}-{date}"
    if not frappe.db.exists("Color Sequence Approval", name):
        frappe.throw(_("Sequence record not found."))
    
    frappe.db.set_value("Color Sequence Approval", name, "status", "Approved", update_modified=True)
    frappe.db.commit()
    return {"status": "success"}

@frappe.whitelist()
def reject_sequence(date, unit, plan_name="Default"):
    """Managers call this to reject the sequence."""
    unit = _normalize_unit(unit)
    name = f"CSA-{plan_name}-{unit}-{date}"
    if not frappe.db.exists("Color Sequence Approval", name):
        frappe.throw(_("Sequence record not found."))
    
    frappe.db.set_value("Color Sequence Approval", name, "status", "Rejected", update_modified=True)
    frappe.db.commit()
    return {"status": "success"}

@frappe.whitelist()
def get_pending_approvals():
    """Returns color sequence arrangements for history and approval dashboard."""
    return frappe.get_all("Color Sequence Approval", 
        filters={"status": ["!=", "Approved"]},
        fields=["name", "date", "unit", "status", "plan_name", "sequence_data", "modified", "owner"],
        order_by="modified desc",
        limit=100
    )

@frappe.whitelist()
def get_items_by_name(names):
    """Returns item details for a list of Planning Sheet Item names."""
    if isinstance(names, str):
        names = json.loads(names)
    if not names:
        return []
    
    return frappe.db.sql(f"""
        SELECT 
            i.name, i.color, i.custom_quality as quality, i.qty, p.party_code,
            p.customer, COALESCE(c.customer_name, p.customer) as customer_name,
            p.sales_order, i.planned_date, i.plan_name,
            p.custom_pb_plan_name as pbPlanName
        FROM `tabPlanning Table` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        LEFT JOIN `tabCustomer` c ON p.customer = c.name
        WHERE i.name IN %s
    """, (names,), as_dict=True)

def _get_color_chart_data_impl(
    date=None,
    start_date=None,
    end_date=None,
    plan_name=None,
    mode=None,
    planned_only=0,
    board_process_scope=None,
):
    from frappe.utils import getdate
    # When unset, no process-prefix filtering (preserves existing callers).
    # When set: exclude_104 = main production board; lamination_only = 104 rows only.
    bps = (board_process_scope or "").strip() or None

    # PULL MODE: Return raw items by ordered_date, exclude items with Work Orders
    if mode == "pull" and date:
        target_date = getdate(date)
        
        # Pull Orders dialog: shows ALL items currently ON the board for source_date.
        # This includes color items (explicitly pushed, have planned_date = target_date)
        # AND white items (auto-planned, use ordered_date = target_date with no item-level date).
        has_col = frappe.db.has_column("Planning Table", "planned_date")
        clean_white_sql_pull = ", ".join([f"'{c.upper().replace(' ', '')}'" for c in WHITE_COLORS])
        
        # Dynamically detect Sales Order Item column
        so_item_real_col = "sales_order_item"
        if not frappe.db.has_column("Planning Table", so_item_real_col):
            so_item_real_col = "custom_sales_order_item"
        
        # Only use the column if it's found in the physical table
        columns = frappe.db.get_table_columns("Planning Table")
        if so_item_real_col not in columns:
            so_item_col = "'' as salesOrderItem,"
        else:
            so_item_col = f"i.{so_item_real_col} as salesOrderItem,"

        split_col = ""
        if frappe.db.has_column("Planning Table", "is_split"):
            split_col = "i.is_split as isSplit,"
        else:
            split_col = "0 as isSplit,"

        if has_col:
            # All items on board for target_date:
            # 1. Items with explicit planned_date = target_date (colors + manually-moved whites)
            # 2. White items with ordered_date = target_date and no item-level override
            items = frappe.db.sql(f"""
                SELECT 
                    i.name as itemName, i.item_code, i.item_name, i.qty, i.uom, i.unit,
                    i.color, i.custom_quality as quality, i.gsm, i.idx, i.plan_name,
                    {so_item_col} {split_col}
                    p.name as planningSheet, p.party_code as partyCode, p.customer,
                    COALESCE(c.customer_name, p.customer) as customer_name,
                    p.ordered_date, p.dod, p.sales_order as salesOrder
                FROM `tabPlanning Table` i
                JOIN `tabPlanning sheet` p ON i.parent = p.name
                LEFT JOIN `tabCustomer` c ON p.customer = c.name
                WHERE i.color IS NOT NULL AND i.color != ''
                  AND p.docstatus < 2
                  AND DATE(COALESCE(NULLIF(i.planned_date, ''), NULLIF(p.custom_planned_date, ''), p.ordered_date)) = DATE(%s)
                  AND (
                        REPLACE(UPPER(COALESCE(i.color, '')), ' ', '') IN ({clean_white_sql_pull})
                        OR COALESCE(NULLIF(i.planned_date, ''), '') != ''
                        OR COALESCE(NULLIF(p.custom_planned_date, ''), '') != ''
                        OR COALESCE(NULLIF(p.custom_pb_plan_name, ''), '') != ''
                  )
                ORDER BY i.unit, i.idx
            """, (target_date,), as_dict=True)
        else:
            # Fallback: use sheet-level date
            sheet_date_col = "COALESCE(p.custom_planned_date, p.ordered_date)" if frappe.db.has_column("Planning sheet", "custom_planned_date") else "p.ordered_date"
            items = frappe.db.sql(f"""
                SELECT 
                    i.name as itemName, i.item_code, i.item_name, i.qty, i.uom, i.unit,
                    i.color, i.custom_quality as quality, i.gsm, i.idx, i.plan_name,
                    {so_item_col} {split_col}
                    p.name as planningSheet, p.party_code as partyCode, p.customer,
                    COALESCE(c.customer_name, p.customer) as customer_name,
                    p.ordered_date, p.dod, p.sales_order as salesOrder
                FROM `tabPlanning Table` i
                JOIN `tabPlanning sheet` p ON i.parent = p.name
                LEFT JOIN `tabCustomer` c ON p.customer = c.name
                WHERE i.color IS NOT NULL AND i.color != ''
                  AND p.docstatus < 2
                  AND DATE({sheet_date_col}) = DATE(%s)
                ORDER BY i.unit, i.idx
            """, (target_date,), as_dict=True)
        
        # Check which planning sheets have Work Orders (those can't be moved)
        if items:
            sheet_names = list(set(it.planningSheet for it in items))
            so_names = list(set(it.salesOrder for it in items if it.salesOrder))
            
            wo_sheets = set()
            # Check WO via Sales Order
            if so_names:
                fmt = ','.join(['%s'] * len(so_names))
                wo_data = frappe.db.sql(f"""
                    SELECT DISTINCT sales_order FROM `tabWork Order`
                    WHERE sales_order IN ({fmt}) AND docstatus < 2
                """, tuple(so_names))
                wo_sos = set(r[0] for r in wo_data)
                for it in items:
                    if it.salesOrder and it.salesOrder in wo_sos:
                        wo_sheets.add(it.planningSheet)
            
            # Check WO via Planning Sheet custom field
            if sheet_names:
                fmt2 = ','.join(['%s'] * len(sheet_names))
                try:
                    wo_ps = frappe.db.sql(f"""
                        SELECT DISTINCT custom_planning_sheet FROM `tabWork Order`
                        WHERE custom_planning_sheet IN ({fmt2}) AND docstatus < 2
                    """, tuple(sheet_names))
                    for r in wo_ps:
                        wo_sheets.add(r[0])
                except Exception:
                    pass
            
            # Filter out items that have WO
            items = [it for it in items if it.planningSheet not in wo_sheets]
        
        # Deduplicate if mode is pull or board
        return _deduplicate_items(items)

    # PULL_BOARD MODE (Production Board only): items already ON the board for this date
    # Use item-level planned_date when set, else sheet custom_planned_date
    if mode == "pull_board" and date:
        target_date = getdate(date)
        has_item_planned = frappe.db.has_column("Planning Table", "planned_date")
        has_sheet_planned = frappe.db.has_column("Planning sheet", "custom_planned_date")
        # Effective date: prefer item level, then sheet level, fallback to ordered_date (for auto-whites)
        item_date_expr = (
            "COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date) = %s"
            if (has_item_planned and has_sheet_planned)
            else "COALESCE(p.custom_planned_date, p.ordered_date) = %s" if has_sheet_planned else "p.ordered_date = %s"
        )
        sheet_pushed = "" # No longer require sheet-level push check

        # Dynamically detect Sales Order Item column
        so_item_real_col = "sales_order_item"
        columns = frappe.db.get_table_columns("Planning Table")
        if "sales_order_item" not in columns and "custom_sales_order_item" in columns:
            so_item_real_col = "custom_sales_order_item"
        
        if so_item_real_col not in columns:
            so_item_col = "'' as salesOrderItem,"
        else:
            so_item_col = f"i.{so_item_real_col} as salesOrderItem,"
        split_col = "i.is_split as isSplit," if frappe.db.has_column("Planning Table", "is_split") else "0 as isSplit,"

        items = frappe.db.sql(f"""
            SELECT
                i.name as itemName, i.item_code, i.item_name, i.qty, i.uom, i.unit,
                i.color, i.custom_quality as quality, i.gsm, i.idx, i.plan_name,
                i.planned_date,
                {so_item_col} {split_col}
                p.name as planningSheet, p.party_code as partyCode, p.customer,
                COALESCE(c.customer_name, p.customer) as customer_name,
                p.ordered_date, p.dod, p.sales_order as salesOrder,
                COALESCE(p.custom_planned_date, '') as sheet_planned_date,
                COALESCE(p.custom_pb_plan_name, '') as pbPlanName,
                COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date) as planned_date
            FROM `tabPlanning Table` i
            JOIN `tabPlanning sheet` p ON i.parent = p.name
            LEFT JOIN `tabCustomer` c ON p.customer = c.name
            WHERE {item_date_expr}
              AND i.color IS NOT NULL AND i.color != ''
              {sheet_pushed}
              AND p.docstatus < 2
            ORDER BY i.unit, i.idx
        """, (target_date,), as_dict=True)

        # Visibility check:
        # - White items: always visible if they match the date
        # - Color items: visible if item OR sheet is planned on board
        #   (item-level planned date, sheet-level planned date, or PB plan marker)
        items = [
            it for it in (items or [])
            if _is_white_color(it.get("color"))
            or it.get("planned_date")
            or it.get("sheet_planned_date")
            or it.get("pbPlanName")
        ]

        if items:
            sheet_names = list(set(it.planningSheet for it in items))
            so_names = list(set(it.salesOrder for it in items if it.salesOrder))
            wo_sheets = set()
            if so_names:
                fmt = ','.join(['%s'] * len(so_names))
                for r in frappe.db.sql(f"SELECT DISTINCT sales_order FROM `tabWork Order` WHERE sales_order IN ({fmt}) AND docstatus < 2", tuple(so_names)):
                    wo_sheets.add(r[0])
            if sheet_names:
                fmt2 = ','.join(['%s'] * len(sheet_names))
                try:
                    for r in frappe.db.sql(f"SELECT DISTINCT custom_planning_sheet FROM `tabWork Order` WHERE custom_planning_sheet IN ({fmt2}) AND docstatus < 2", tuple(sheet_names)):
                        wo_sheets.add(r[0])
                except Exception:
                    pass
            items = [it for it in items if it.planningSheet not in wo_sheets]
        return _deduplicate_items(items) if items else []

    # Support both single date and range
    if start_date and end_date:
        query_start = getdate(start_date)
        query_end = getdate(end_date)
    elif date:
        # Check if multiple dates are provided (comma separated)
        if "," in str(date):
            target_dates = [getdate(d.strip()) for d in str(date).split(",") if d.strip()]
        else:
            target_dates = [getdate(date)]
    else:
        return []

    # Build SQL for date filtering ΓÇö support split dates (pushed vs unpushed)
    # IMPORTANT: For sheet fetching, we must use sheet-level fields. Item-level overrides
    # are handled via EXISTS later in planned_only mode.
    eff_pushed = "COALESCE(p.custom_planned_date, p.ordered_date)"
    eff_ordered = "p.ordered_date"
    
    plan_condition = ""
    params = []
    has_item_planned_col = frappe.db.has_column("Planning Table", "planned_date")
    
    if start_date and end_date:
        date_condition = f"({eff_ordered} BETWEEN %s AND %s OR {eff_pushed} BETWEEN %s AND %s)"
        params.extend([query_start, query_end, query_start, query_end])
        if has_item_planned_col:
            date_condition = f"({date_condition} OR EXISTS (SELECT 1 FROM `tabPlanning Table` psi WHERE psi.parent = p.name AND psi.planned_date BETWEEN %s AND %s))"
            params.extend([query_start, query_end])
    else:
        if len(target_dates) > 1:
            fmt = ','.join(['%s'] * len(target_dates))
            date_condition = f"({eff_ordered} IN ({fmt}) OR {eff_pushed} IN ({fmt}))"
            params.extend(target_dates)
            params.extend(target_dates)
            if has_item_planned_col:
                date_condition = f"({date_condition} OR EXISTS (SELECT 1 FROM `tabPlanning Table` psi WHERE psi.parent = p.name AND psi.planned_date IN ({fmt})))"
                params.extend(target_dates)
        else:
            date_condition = f"({eff_ordered} = %s OR {eff_pushed} = %s)"
            params.append(target_dates[0])
            params.append(target_dates[0])
            if has_item_planned_col:
                date_condition = f"({date_condition} OR EXISTS (SELECT 1 FROM `tabPlanning Table` psi WHERE psi.parent = p.name AND DATE(psi.planned_date) = DATE(%s)))"
                params.append(target_dates[0])
    
    if plan_name == "__all__":
        plan_condition = ""  # No plan filter ΓÇö return all items
    elif plan_name and plan_name != "Default":
        # Search for BOTH the base name, contextual name, and any legacy variations
        valid_names = [plan_name]
        for d in target_dates:
            ctx_name = _get_contextual_plan_name(plan_name, d)
            if ctx_name not in valid_names:
                valid_names.append(ctx_name)
        
        # Proactively find legacy candidates in the DB that match this base name when stripped
        db_names = frappe.db.sql("SELECT DISTINCT custom_plan_name FROM `tabPlanning sheet` WHERE custom_plan_name IS NOT NULL AND custom_plan_name != ''", as_list=1)
        for row in db_names:
            full_db_name = row[0]
            if _strip_legacy_prefixes(full_db_name) == plan_name:
                if full_db_name not in valid_names:
                    valid_names.append(full_db_name)
        
        fmt = ','.join(['%s'] * len(valid_names))
        plan_condition = f"AND p.custom_plan_name IN ({fmt})"
        params.extend(valid_names)
    else:
        plan_condition = "AND (p.custom_plan_name IS NULL OR p.custom_plan_name = '' OR p.custom_plan_name = 'Default')"

    # Production Board only: require custom_planned_date to be set (scheduled).
    # IMPORTANT: We do NOT require custom_pb_plan_name here because "white" orders
    # are allowed to appear directly on the Production Board without being pushed.
    # Non-white items are filtered per-item later unless they belong to a PB plan.
    if cint(planned_only) and _has_planned_date_column():
        # Allow sheets where EITHER the sheet has custom_planned_date OR items have planned_date
        has_item_planned = frappe.db.has_column("Planning Table", "planned_date")
        if has_item_planned:
            plan_condition += """ AND (
                (p.custom_planned_date IS NOT NULL AND p.custom_planned_date != '')
                OR EXISTS (SELECT 1 FROM `tabPlanning Table` psi 
                           WHERE psi.parent = p.name 
                           AND psi.planned_date IS NOT NULL 
                           AND psi.planned_date != '')
            )"""
        else:
            plan_condition += " AND p.custom_planned_date IS NOT NULL AND p.custom_planned_date != ''"
    
    # Build SELECT fields ΓÇö include columns only if they exist
    fields = ["p.name", "p.customer", "p.party_code", "c.customer_name as party_name", "p.dod", "p.ordered_date", 
              "p.planning_status", "p.docstatus", "p.sales_order", "p.custom_plan_name", "p.custom_pb_plan_name",
              "COALESCE(p.custom_plan_name, 'Default') as planName"]
    
    if _has_planned_date_column():
        fields.append("p.custom_planned_date")
    
    if _has_approval_status_column():
        fields.append("p.custom_approval_status")
        
    if _has_draft_fields():
        fields.append("p.custom_draft_planned_date")
        fields.append("p.custom_draft_idx")
        
    fields_str = ", ".join(fields)
    
    has_item_planned_col = frappe.db.has_column("Planning Table", "planned_date")
    eff = _effective_date_expr("p")

    if cint(planned_only) and has_item_planned_col and not (start_date and end_date):
        # For planned_only mode: also include sheets that have items with planned_date
        # matching target date (even if sheet's ordered_date is different).
        # This handles items whose dates were manually overridden at item level.
        if len(target_dates) == 1:
            item_date_param = target_dates[0]
        else:
            item_date_param = None  # Only handle single target date case here
        
        if item_date_param:
            planning_sheets = frappe.db.sql(f"""
                SELECT {fields_str}, {eff} as effective_date
                FROM `tabPlanning sheet` p
                LEFT JOIN `tabCustomer` c ON p.customer = c.name
                WHERE (
                    {date_condition}
                    OR EXISTS (
                        SELECT 1 FROM `tabPlanning Table` psi
                        WHERE psi.parent = p.name
                        AND DATE(psi.planned_date) = DATE(%s)
                    )
                )
                AND p.docstatus < 2
                {plan_condition}
                ORDER BY {eff} ASC, p.creation ASC
            """, tuple(params) + (item_date_param,), as_dict=True)
        else:
            planning_sheets = frappe.db.sql(f"""
                SELECT {fields_str}, {eff} as effective_date
                FROM `tabPlanning sheet` p
                LEFT JOIN `tabCustomer` c ON p.customer = c.name
                WHERE {date_condition} AND p.docstatus < 2
                {plan_condition}
                ORDER BY {eff} ASC, p.creation ASC
            """, tuple(params), as_dict=True)
    else:
        planning_sheets = frappe.db.sql(f"""
            SELECT {fields_str}, {eff} as effective_date
            FROM `tabPlanning sheet` p
            LEFT JOIN `tabCustomer` c ON p.customer = c.name
            WHERE {date_condition} AND p.docstatus < 2
            {plan_condition}
            ORDER BY {eff} ASC, p.creation ASC
        """, tuple(params), as_dict=True)

    # Fetch delivery statuses for referenced Sales Orders
    so_names = [d.sales_order for d in planning_sheets if d.sales_order]
    sheet_names = [d.name for d in planning_sheets]
    
    so_status_map = {}
    so_pp_map = {}
    so_wo_map = {}
    so_produced_map = {}
    so_wo_count_map = {}
    sheet_pp_map = {}
    pp_wo_map = {}
    so_item_produced_map = {}
    so_item_wo_count_map = {}
    item_pp_map = {}
    pp_produced_map = {}
    pp_wo_count_map = {}
    pp_has_open_wo_map = {}
    pp_has_wo_map = {}
    pp_wo_target_qty_map = {}
    pp_wo_produced_qty_map = {}
    spr_pp_produced_map = {}
    spr_pp_count_map = {}
    spr_psi_produced_map = {}
    spr_psi_count_map = {}
    spr_so_item_produced_map = {}
    spr_so_item_count_map = {}
    spr_so_produced_map = {}
    spr_so_count_map = {}
    spr_order_code_produced_map = {}
    spr_order_code_count_map = {}
    
    # Name mapping for SPR links
    spr_pp_name_map = {}
    spr_psi_name_map = {}
    spr_so_item_name_map = {}
    spr_so_name_map = {}
    spr_order_code_name_map = {}
    
    so_item_pp_cache = {}
    psi_pp_field = _psi_production_plan_field()
    so_item_code_produced_map = {}
    so_item_code_wo_count_map = {}
    so_item_code_order_produced_map = {}
    so_item_code_order_wo_count_map = {}
    order_code_item_produced_map = {}
    order_code_item_wo_count_map = {}
    so_item_delivered_qty_map = {}
    order_item_delivered_qty_map = {}
    
    valid_pps = set()
    
    if so_names:
        sos = frappe.get_all("Sales Order", filters={"name": ["in", so_names]}, fields=["name", "delivery_status"])
        for s in sos:
            so_status_map[s.name] = s.delivery_status

        so_order_code_col = None
        for c in ["order_code", "custom_order_code", "po_no", "customer_order_no"]:
            if frappe.db.has_column("Sales Order", c):
                so_order_code_col = c
                break
            
        format_string_so = ','.join(['%s'] * len(so_names))
        
        # Check Production Plan via Sales Order
        pp_data = frappe.db.sql(f"""
            SELECT sales_order, parent 
            FROM `tabProduction Plan Sales Order` 
            WHERE sales_order IN ({format_string_so}) AND docstatus < 2
        """, tuple(so_names), as_dict=True)
        for row in pp_data:
            so_pp_map[row.sales_order] = row.parent
            valid_pps.add(row.parent)
            
        # Check Work Order via Sales Order
        wo_data_so = frappe.db.sql(f"""
            SELECT sales_order, name 
            FROM `tabWork Order` 
            WHERE sales_order IN ({format_string_so}) AND docstatus < 2
        """, tuple(so_names), as_dict=True)
        for row in wo_data_so:
            so_wo_map[row.sales_order] = row.name

        # Delivery qty by Sales Order + Item Code from submitted Delivery Notes.
        dn_rows = frappe.db.sql(f"""
            SELECT dni.against_sales_order as sales_order, dni.item_code, IFNULL(SUM(dni.qty), 0) as delivered_qty
            FROM `tabDelivery Note Item` dni
            INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
            WHERE dn.docstatus = 1
              AND dni.against_sales_order IN ({format_string_so})
            GROUP BY dni.against_sales_order, dni.item_code
        """, tuple(so_names), as_dict=True) or []
        for r in dn_rows:
            k = ((r.get("sales_order") or "").strip(), (r.get("item_code") or "").strip())
            if k[0] and k[1]:
                so_item_delivered_qty_map[k] = flt(r.get("delivered_qty") or 0)
        # Delivery qty by Sales Order order-code + Item Code from submitted Delivery Notes.
        # This covers non-batch DN flows where Planning rows are linked by party/order code.
        if so_order_code_col:
            dn_order_from_so_rows = frappe.db.sql(f"""
                SELECT IFNULL(so.{so_order_code_col}, '') as order_code,
                       dni.item_code,
                       IFNULL(SUM(dni.qty), 0) as delivered_qty
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
                INNER JOIN `tabSales Order` so ON so.name = dni.against_sales_order
                WHERE dn.docstatus = 1
                  AND dni.against_sales_order IN ({format_string_so})
                  AND IFNULL(so.{so_order_code_col}, '') != ''
                GROUP BY IFNULL(so.{so_order_code_col}, ''), dni.item_code
            """, tuple(so_names), as_dict=True) or []
            for r in dn_order_from_so_rows:
                k = ((r.get("order_code") or "").strip(), (r.get("item_code") or "").strip())
                if k[0] and k[1]:
                    order_item_delivered_qty_map[k] = max(
                        flt(order_item_delivered_qty_map.get(k, 0)),
                        flt(r.get("delivered_qty") or 0),
                    )

    # Delivery qty by Order Code + Item Code from Batch link (for scanner-driven DN flows).
    party_codes = list({str(s.party_code).strip() for s in planning_sheets if s.get("party_code")})
    if party_codes and frappe.db.exists("DocType", "Batch"):
        batch_order_col = None
        for c in ["custom_party_code_text", "custom_order_code", "order_code", "party_code"]:
            if frappe.db.has_column("Batch", c):
                batch_order_col = c
                break
        if batch_order_col:
            fmt_party = ",".join(["%s"] * len(party_codes))
            dn_order_rows = frappe.db.sql(f"""
                SELECT b.{batch_order_col} as order_code, dni.item_code, IFNULL(SUM(dni.qty), 0) as delivered_qty
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
                INNER JOIN `tabBatch` b ON b.name = dni.batch_no
                WHERE dn.docstatus = 1
                  AND IFNULL(b.{batch_order_col}, '') IN ({fmt_party})
                GROUP BY b.{batch_order_col}, dni.item_code
            """, tuple(party_codes), as_dict=True) or []
            for r in dn_order_rows:
                k = ((r.get("order_code") or "").strip(), (r.get("item_code") or "").strip())
                if k[0] and k[1]:
                    order_item_delivered_qty_map[k] = max(
                        flt(order_item_delivered_qty_map.get(k, 0)),
                        flt(r.get("delivered_qty") or 0),
                    )

        # Effective produced qty by Sales Order (WO produced_qty + submitted FG Stock Entry)
        so_prod_rows = frappe.db.sql(f"""
            SELECT wo.sales_order,
                   SUM(GREATEST(IFNULL(wo.produced_qty, 0), IFNULL(se_map.se_produced_qty, 0))) as produced_qty,
                   COUNT(wo.name) as wo_count
            FROM `tabWork Order` wo
            LEFT JOIN (
                SELECT se.work_order, SUM(IFNULL(sed.qty, 0)) as se_produced_qty
                FROM `tabStock Entry` se
                INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                WHERE se.docstatus = 1
                  AND IFNULL(se.work_order, '') != ''
                  AND IFNULL(sed.is_finished_item, 0) = 1
                GROUP BY se.work_order
            ) se_map ON se_map.work_order = wo.name
            WHERE wo.sales_order IN ({format_string_so})
              AND wo.docstatus < 2
            GROUP BY wo.sales_order
        """, tuple(so_names), as_dict=True)
        for row in so_prod_rows:
            if row.get("sales_order"):
                so_produced_map[row.sales_order] = flt(row.get("produced_qty"))
                so_wo_count_map[row.sales_order] = cint(row.get("wo_count"))

        # Strict chain fallback: SO -> PP -> WO -> production_item.
        # Order code flows through PP and WO, not SO. Match against Planning Sheet party_code.
        pp_order_code_col = None
        wo_order_code_col = None
        for c in ["order_code", "custom_order_code"]:
            if frappe.db.has_column("Production Plan", c) and not pp_order_code_col:
                pp_order_code_col = c
            if frappe.db.has_column("Work Order", c) and not wo_order_code_col:
                wo_order_code_col = c

        # Build order_code select safely - handle missing columns
        if pp_order_code_col and wo_order_code_col:
            order_code_select = f"IFNULL(pp.{pp_order_code_col}, IFNULL(wo.{wo_order_code_col}, '')) as order_code"
        elif pp_order_code_col:
            order_code_select = f"IFNULL(pp.{pp_order_code_col}, '') as order_code"
        elif wo_order_code_col:
            order_code_select = f"IFNULL(wo.{wo_order_code_col}, '') as order_code"
        else:
            order_code_select = "'' as order_code"

        so_item_prod_rows = frappe.db.sql(f"""
            SELECT COALESCE(NULLIF(wo.sales_order, ''), pps.sales_order) as sales_order,
                   wo.production_item as item_code,
                   {order_code_select},
                   SUM(GREATEST(IFNULL(wo.produced_qty, 0), IFNULL(se_map.se_produced_qty, 0))) as produced_qty,
                   COUNT(DISTINCT wo.name) as wo_count
            FROM `tabWork Order` wo
            LEFT JOIN `tabProduction Plan Sales Order` pps
              ON pps.parent = wo.production_plan
             AND pps.docstatus < 2
             AND (IFNULL(wo.sales_order, '') = '' OR pps.sales_order = wo.sales_order)
            LEFT JOIN `tabProduction Plan` pp ON pp.name = wo.production_plan
            LEFT JOIN (
                SELECT se.work_order, SUM(IFNULL(sed.qty, 0)) as se_produced_qty
                FROM `tabStock Entry` se
                INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                WHERE se.docstatus = 1
                  AND IFNULL(se.work_order, '') != ''
                  AND IFNULL(sed.is_finished_item, 0) = 1
                GROUP BY se.work_order
            ) se_map ON se_map.work_order = wo.name
            WHERE COALESCE(NULLIF(wo.sales_order, ''), pps.sales_order) IN ({format_string_so})
              AND wo.docstatus < 2
              AND IFNULL(wo.production_item, '') != ''
            GROUP BY COALESCE(NULLIF(wo.sales_order, ''), pps.sales_order), wo.production_item, order_code
        """, tuple(so_names), as_dict=True)
        for row in so_item_prod_rows:
            so_key = (row.get("sales_order") or "").strip()
            item_key = (row.get("item_code") or "").strip()
            order_key = (row.get("order_code") or "").strip()
            if so_key and item_key:
                map_key = f"{so_key}::{item_key}"
                so_item_code_produced_map[map_key] = flt(row.get("produced_qty"))
                so_item_code_wo_count_map[map_key] = cint(row.get("wo_count"))
                if order_key:
                    map_order_key = f"{so_key}::{item_key}::{order_key}"
                    so_item_code_order_produced_map[map_order_key] = flt(row.get("produced_qty"))
                    so_item_code_order_wo_count_map[map_order_key] = cint(row.get("wo_count"))

    if sheet_names:
        format_string_sheet = ','.join(['%s'] * len(sheet_names))
        # Check Production Plan via Planning Sheet custom field
        # Wrap in try-except in case custom field doesn't exist
        try:
            pp_sheet_data = frappe.db.sql(f"""
                SELECT custom_planning_sheet as planning_sheet, name 
                FROM `tabProduction Plan` 
                WHERE custom_planning_sheet IN ({format_string_sheet}) AND docstatus < 2
            """, tuple(sheet_names), as_dict=True)
            for row in pp_sheet_data:
                sheet_pp_map[row.planning_sheet] = row.name
                valid_pps.add(row.name)
        except Exception:
            pass

    # SO-independent fallback for legacy/live rows:
    # match by order_code (party_code) + item_code from WO/PP chain.
    party_codes = list({str(s.party_code).strip() for s in planning_sheets if s.get("party_code")})
    if party_codes:
        pp_order_code_col = None
        wo_order_code_col = None
        for c in ["order_code", "custom_order_code"]:
            if frappe.db.has_column("Production Plan", c) and not pp_order_code_col:
                pp_order_code_col = c
            if frappe.db.has_column("Work Order", c) and not wo_order_code_col:
                wo_order_code_col = c

        if pp_order_code_col and wo_order_code_col:
            fallback_order_code_select = f"IFNULL(pp.{pp_order_code_col}, IFNULL(wo.{wo_order_code_col}, ''))"
        elif pp_order_code_col:
            fallback_order_code_select = f"IFNULL(pp.{pp_order_code_col}, '')"
        elif wo_order_code_col:
            fallback_order_code_select = f"IFNULL(wo.{wo_order_code_col}, '')"
        else:
            fallback_order_code_select = "''"

        format_string_party = ','.join(['%s'] * len(party_codes))
        order_item_rows = frappe.db.sql(f"""
            SELECT {fallback_order_code_select} as order_code,
                   wo.production_item as item_code,
                   SUM(GREATEST(IFNULL(wo.produced_qty, 0), IFNULL(se_map.se_produced_qty, 0))) as produced_qty,
                   COUNT(DISTINCT wo.name) as wo_count
            FROM `tabWork Order` wo
            LEFT JOIN `tabProduction Plan` pp ON pp.name = wo.production_plan
            LEFT JOIN (
                SELECT se.work_order, SUM(IFNULL(sed.qty, 0)) as se_produced_qty
                FROM `tabStock Entry` se
                INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                WHERE se.docstatus = 1
                  AND IFNULL(se.work_order, '') != ''
                  AND IFNULL(sed.is_finished_item, 0) = 1
                GROUP BY se.work_order
            ) se_map ON se_map.work_order = wo.name
            WHERE {fallback_order_code_select} IN ({format_string_party})
              AND wo.docstatus < 2
              AND IFNULL(wo.production_item, '') != ''
            GROUP BY order_code, wo.production_item
        """, tuple(party_codes), as_dict=True)

        for row in order_item_rows:
            order_key = (row.get("order_code") or "").strip()
            item_key = (row.get("item_code") or "").strip()
            if order_key and item_key:
                map_key = f"{order_key}::{item_key}"
                order_code_item_produced_map[map_key] = flt(row.get("produced_qty"))
                order_code_item_wo_count_map[map_key] = cint(row.get("wo_count"))

        
    if valid_pps:
        format_string_pp = ','.join(['%s'] * len(valid_pps))
        # Check Work Order via Production Plan
        wo_data_pp = frappe.db.sql(f"""
            SELECT wo.production_plan,
                   wo.name,
                   GREATEST(IFNULL(wo.produced_qty, 0), IFNULL(se_map.se_produced_qty, 0)) as produced_qty,
                 wo.qty,
                 IFNULL(wo.status, '') as status
            FROM `tabWork Order` wo
            LEFT JOIN (
                SELECT se.work_order, SUM(IFNULL(sed.qty, 0)) as se_produced_qty
                FROM `tabStock Entry` se
                INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                WHERE se.docstatus = 1
                  AND IFNULL(se.work_order, '') != ''
                  AND IFNULL(sed.is_finished_item, 0) = 1
                GROUP BY se.work_order
            ) se_map ON se_map.work_order = wo.name
            WHERE wo.production_plan IN ({format_string_pp}) AND wo.docstatus < 2
        """, tuple(valid_pps), as_dict=True)
        for row in wo_data_pp:
            if row.production_plan not in pp_wo_map:
                pp_wo_map[row.production_plan] = []
            pp_has_wo_map[row.production_plan] = True

            wo_status = str(row.get("status") or "").strip().lower()
            terminal_statuses = {"completed", "stopped", "cancelled", "closed"}
            if wo_status and wo_status not in terminal_statuses:
                pp_has_open_wo_map[row.production_plan] = True

            pp_wo_map[row.production_plan].append({
                "name": row.name,
                "produced_qty": flt(row.produced_qty),
                "qty": flt(row.qty),
                "status": row.get("status")
            })

            pp_wo_target_qty_map[row.production_plan] = pp_wo_target_qty_map.get(row.production_plan, 0) + flt(row.qty)
            pp_wo_produced_qty_map[row.production_plan] = pp_wo_produced_qty_map.get(row.production_plan, 0) + flt(row.produced_qty)

    # Shaft Production Run aggregation (submitted docs) for production flows
    try:
        if frappe.db.exists("DocType", "Shaft Production Run"):
            spr_cols = frappe.db.get_table_columns("Shaft Production Run") or []
            spr_produced_col = None
            for c in ["total_produced_weight", "custom_total_produced_weight", "produced_qty"]:
                if c in spr_cols:
                    spr_produced_col = c
                    break

            if spr_produced_col:
                spr_pp_col = next((c for c in ["production_plan", "custom_production_plan"] if c in spr_cols), None)
                spr_so_item_col = next((c for c in ["sales_order_item", "custom_sales_order_item"] if c in spr_cols), None)
                spr_psi_col = next((c for c in ["planning_sheet_item", "custom_planning_sheet_item", "planning_sheet_item_name"] if c in spr_cols), None)
                spr_so_col = next((c for c in ["sales_order", "custom_sales_order"] if c in spr_cols), None)
                spr_order_code_col = next((c for c in ["order_code", "custom_order_code", "party_code"] if c in spr_cols), None)

                party_codes = list({str(s.party_code).strip() for s in planning_sheets if s.get("party_code")})
                where_clauses = []
                params = []

                if spr_pp_col and valid_pps:
                    fmt = ",".join(["%s"] * len(valid_pps))
                    where_clauses.append(f"IFNULL({spr_pp_col}, '') IN ({fmt})")
                    params.extend(list(valid_pps))
                if spr_so_col and so_names:
                    fmt = ",".join(["%s"] * len(so_names))
                    where_clauses.append(f"IFNULL({spr_so_col}, '') IN ({fmt})")
                    params.extend(so_names)
                if spr_order_code_col and party_codes:
                    fmt = ",".join(["%s"] * len(party_codes))
                    where_clauses.append(f"IFNULL({spr_order_code_col}, '') IN ({fmt})")
                    params.extend(party_codes)

                if where_clauses:
                    select_cols = ["name", f"IFNULL({spr_produced_col}, 0) as produced_qty"]
                    if spr_pp_col:
                        select_cols.append(f"{spr_pp_col} as pp_key")
                    if spr_so_item_col:
                        select_cols.append(f"{spr_so_item_col} as so_item_key")
                    if spr_psi_col:
                        select_cols.append(f"{spr_psi_col} as psi_key")
                    if spr_so_col:
                        select_cols.append(f"{spr_so_col} as so_key")
                    if spr_order_code_col:
                        select_cols.append(f"{spr_order_code_col} as order_code_key")

                    spr_rows = frappe.db.sql(
                        f"""
                        SELECT {', '.join(select_cols)}, docstatus
                        FROM `tabShaft Production Run`
                        WHERE docstatus < 2
                          AND ({' OR '.join(where_clauses)})
                        ORDER BY creation DESC
                        """,
                        tuple(params),
                        as_dict=True,
                    )

                    for r in spr_rows:
                        spr_name = r.get("name")
                        qty = flt(r.get("produced_qty"))
                        is_submitted = (r.get("docstatus") == 1)

                        pp_key = (r.get("pp_key") or "").strip()
                        if pp_key:
                            # Always take newest name (since ordered DESC)
                            if pp_key not in spr_pp_name_map:
                                spr_pp_name_map[pp_key] = spr_name
                            if is_submitted:
                                spr_pp_produced_map[pp_key] = spr_pp_produced_map.get(pp_key, 0) + qty
                                spr_pp_count_map[pp_key] = spr_pp_count_map.get(pp_key, 0) + 1

                        so_item_key = (r.get("so_item_key") or "").strip()
                        if so_item_key:
                            if so_item_key not in spr_so_item_name_map:
                                spr_so_item_name_map[so_item_key] = spr_name
                            if is_submitted:
                                spr_so_item_produced_map[so_item_key] = spr_so_item_produced_map.get(so_item_key, 0) + qty
                                spr_so_item_count_map[so_item_key] = spr_so_item_count_map.get(so_item_key, 0) + 1

                        psi_key = (r.get("psi_key") or "").strip()
                        if psi_key:
                            # Do not infer Planning row -> SPR name from SPR.planning_sheet_item.
                            # Only explicit Planning Table `spr_name` should bind a row to SPR.
                            if is_submitted:
                                spr_psi_produced_map[psi_key] = spr_psi_produced_map.get(psi_key, 0) + qty
                                spr_psi_count_map[psi_key] = spr_psi_count_map.get(psi_key, 0) + 1

                        so_key = (r.get("so_key") or "").strip()
                        if so_key:
                            if so_key not in spr_so_name_map:
                                spr_so_name_map[so_key] = spr_name
                            if is_submitted:
                                spr_so_produced_map[so_key] = spr_so_produced_map.get(so_key, 0) + qty
                                spr_so_count_map[so_key] = spr_so_count_map.get(so_key, 0) + 1

                        order_code_key = (r.get("order_code_key") or "").strip()
                        if order_code_key:
                            if order_code_key not in spr_order_code_name_map:
                                spr_order_code_name_map[order_code_key] = spr_name
                            if is_submitted:
                                spr_order_code_produced_map[order_code_key] = spr_order_code_produced_map.get(order_code_key, 0) + qty
                                spr_order_code_count_map[order_code_key] = spr_order_code_count_map.get(order_code_key, 0) + 1
    except Exception:
        pass

    # Fetch SPR achieved weights by Production Plan (primary method)
    # Use latest submitted SPR achieved-weight column available on this site.
    spr_pp_achieved_weight_map = {}  # Map PP to SPR achieved weight
    try:
        if valid_pps and frappe.db.exists("DocType", "Shaft Production Run"):
            spr_cols_local = frappe.db.get_table_columns("Shaft Production Run") or []
            spr_pp_link_col = next((c for c in ["production_plan", "custom_production_plan"] if c in spr_cols_local), None)
            spr_achieved_col = next(
                (
                    c
                    for c in [
                        "custom_total_achieved_weight",
                        "total_achieved_weight",
                        "total_achieved_weight_kgs",
                        "achieved_weight",
                        "total_achieved",
                    ]
                    if c in spr_cols_local
                ),
                None,
            )
            if not spr_pp_link_col:
                raise Exception("SPR production-plan link column missing")

            fmt_pps = ",".join(["%s"] * len(valid_pps))
            spr_achieved_rows = []
            if spr_achieved_col:
                # Pick latest submitted SPR with non-zero achieved weight per PP (parent-level field).
                spr_achieved_rows = frappe.db.sql(f"""
                    SELECT 
                        spr.name,
                        spr.{spr_pp_link_col} as production_plan,
                        COALESCE(spr.{spr_achieved_col}, 0) as achieved_weight
                    FROM `tabShaft Production Run` spr
                    WHERE spr.{spr_pp_link_col} IN ({fmt_pps})
                      AND spr.docstatus = 1
                      AND COALESCE(spr.{spr_achieved_col}, 0) > 0
                    ORDER BY spr.creation DESC
                """, tuple(valid_pps), as_dict=True)
            else:
                # Fallback: achieved weight is stored in SPR child table rows (for example, shaft_jobs).
                child_table_field = next(
                    (
                        df.fieldname
                        for df in (frappe.get_meta("Shaft Production Run").fields or [])
                        if df.fieldtype == "Table" and (df.options or "").strip()
                    ),
                    None,
                )
                child_dt = None
                child_ach_col = None
                if child_table_field:
                    child_options = (
                        frappe.get_meta("Shaft Production Run").get_field(child_table_field).options
                        if frappe.get_meta("Shaft Production Run").get_field(child_table_field)
                        else None
                    )
                    child_dt = (child_options or "").strip()
                if child_dt and frappe.db.exists("DocType", child_dt):
                    child_cols = frappe.db.get_table_columns(child_dt) or []
                    child_ach_col = next(
                        (
                            c
                            for c in [
                                "custom_total_achieved_weight",
                                "total_achieved_weight",
                                "total_achieved_weight_kgs",
                                "achieved_weight",
                                "total_achieved",
                            ]
                            if c in child_cols
                        ),
                        None,
                    )
                if child_dt and child_ach_col:
                    spr_achieved_rows = frappe.db.sql(f"""
                        SELECT
                            spr.name,
                            spr.{spr_pp_link_col} as production_plan,
                            SUM(COALESCE(ch.{child_ach_col}, 0)) as achieved_weight
                        FROM `tabShaft Production Run` spr
                        LEFT JOIN `tab{child_dt}` ch ON ch.parent = spr.name
                        WHERE spr.{spr_pp_link_col} IN ({fmt_pps})
                          AND spr.docstatus = 1
                        GROUP BY spr.name, spr.{spr_pp_link_col}
                        HAVING SUM(COALESCE(ch.{child_ach_col}, 0)) > 0
                        ORDER BY spr.creation DESC
                    """, tuple(valid_pps), as_dict=True)
            
            for row in spr_achieved_rows:
                pp_id = row.get('production_plan')
                achieved = flt(row.get('achieved_weight', 0))
                if pp_id and pp_id not in spr_pp_achieved_weight_map:
                    spr_pp_achieved_weight_map[pp_id] = achieved
    except Exception as e:
        frappe.log_error(f"Error fetching SPR achieved weights: {str(e)}")

    # Fetch SPR production via spr_name field on Planning Table (board rows)
    spr_psi_achieved_weight_map = {}  # Map PSI to SPR achieved weight
    try:
        if frappe.db.has_column("Planning Table", "spr_name") and frappe.db.exists("DocType", "Shaft Production Run"):
            spr_cols_pt = frappe.db.get_table_columns("Shaft Production Run") or []
            spr_produced_col_pt = None
            for c in ["total_produced_weight", "custom_total_produced_weight", "produced_qty"]:
                if c in spr_cols_pt:
                    spr_produced_col_pt = c
                    break
            # Parent SPR fields are often 0 until submit; always include sum of roll line net weights.
            items_net_sql = (
                "(SELECT IFNULL(SUM(IFNULL(spi.net_weight, 0)), 0) FROM `tabShaft Production Run Item` spi "
                "WHERE spi.parent = spr.name)"
            )
            base_prod = f"COALESCE(spr.{spr_produced_col_pt}, 0)" if spr_produced_col_pt else "0"
            produced_col_sql = f"GREATEST({base_prod}, {items_net_sql})"
            base_ach = "0"
            for _ach_col in ["custom_total_achieved_weight", "total_achieved_weight", "total_achieved_weight_kgs", "achieved_weight", "total_achieved"]:
                if _ach_col in spr_cols_pt:
                    base_ach = f"COALESCE(spr.{_ach_col}, 0)"
                    break
            achieved_col_sql = f"GREATEST({base_ach}, {items_net_sql})"

            psi_spr_data = frappe.db.sql(f"""
                SELECT 
                    psi.name as psi_name,
                    psi.spr_name as spr_name,
                    spr.docstatus as spr_docstatus,
                    {produced_col_sql} as total_produced,
                    {achieved_col_sql} as total_achieved
                FROM `tabPlanning Table` psi
                LEFT JOIN `tabShaft Production Run` spr ON psi.spr_name = spr.name
                WHERE psi.parent IN ({{}})
                  AND psi.spr_name IS NOT NULL 
                  AND psi.spr_name != ''
                  AND spr.docstatus < 2
            """.format(','.join(['%s'] * len(sheet_names))), tuple(sheet_names), as_dict=True)
            
            for row in psi_spr_data:
                psi_name = row.get('psi_name')
                spr_name = row.get('spr_name')
                produced = flt(row.get('total_produced', 0))
                achieved = flt(row.get('total_achieved', 0))
                eff_kg = max(achieved, produced)
                if psi_name and spr_name:
                    if eff_kg > 0:
                        spr_psi_achieved_weight_map[psi_name] = max(
                            flt(spr_psi_achieved_weight_map.get(psi_name, 0)), eff_kg
                        )
                    if produced > 0:
                        spr_psi_produced_map[psi_name] = spr_psi_produced_map.get(psi_name, 0) + produced
                        spr_psi_count_map[psi_name] = spr_psi_count_map.get(psi_name, 0) + 1
    except Exception:
        pass

    # Item-level produced quantity map via sales_order_item/custom_sales_order_item
    if sheet_names:
        # 1) Strongest link: Planning Sheet Item -> Production Plan -> Work Order
        if psi_pp_field and frappe.db.has_column("Planning Table", psi_pp_field):
            fmt_sheet = ','.join(['%s'] * len(sheet_names))
            psi_pp_rows = frappe.db.sql(f"""
                SELECT name as psi_name, {psi_pp_field} as production_plan
                FROM `tabPlanning Table`
                WHERE parent IN ({fmt_sheet})
                  AND IFNULL({psi_pp_field}, '') != ''
            """, tuple(sheet_names), as_dict=True)

            pp_names = []
            for r in psi_pp_rows:
                psi_name = r.get("psi_name")
                pp_name = r.get("production_plan")
                if psi_name and pp_name:
                    item_pp_map[psi_name] = pp_name
                    pp_names.append(pp_name)

            if pp_names:
                pp_names = list(set(pp_names))
                fmt_pp = ','.join(['%s'] * len(pp_names))
                pp_wo_rows = frappe.db.sql(f"""
                    SELECT wo.production_plan,
                           SUM(GREATEST(IFNULL(wo.produced_qty, 0), IFNULL(se_map.se_produced_qty, 0))) as produced_qty,
                           COUNT(wo.name) as wo_count
                    FROM `tabWork Order` wo
                    LEFT JOIN (
                        SELECT se.work_order, SUM(IFNULL(sed.qty, 0)) as se_produced_qty
                        FROM `tabStock Entry` se
                        INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                        WHERE se.docstatus = 1
                          AND IFNULL(se.work_order, '') != ''
                          AND IFNULL(sed.is_finished_item, 0) = 1
                        GROUP BY se.work_order
                    ) se_map ON se_map.work_order = wo.name
                    WHERE wo.production_plan IN ({fmt_pp})
                      AND wo.docstatus < 2
                    GROUP BY wo.production_plan
                """, tuple(pp_names), as_dict=True)

                for row in pp_wo_rows:
                    pp = row.get("production_plan")
                    if pp:
                        pp_produced_map[pp] = flt(row.get("produced_qty"))
                        pp_wo_count_map[pp] = cint(row.get("wo_count"))

        # 2) Fallback link: Planning Sheet Item sales_order_item -> Work Order
        psi_so_item_col = "sales_order_item" if frappe.db.has_column("Planning Table", "sales_order_item") else "custom_sales_order_item"
        wo_so_item_col = "sales_order_item" if frappe.db.has_column("Work Order", "sales_order_item") else "custom_sales_order_item"

        if psi_so_item_col and wo_so_item_col and frappe.db.has_column("Planning Table", psi_so_item_col) and frappe.db.has_column("Work Order", wo_so_item_col):
            fmt_sheet = ','.join(['%s'] * len(sheet_names))
            so_item_rows = frappe.db.sql(f"""
                SELECT DISTINCT {psi_so_item_col} as so_item
                FROM `tabPlanning Table`
                WHERE parent IN ({fmt_sheet})
                  AND IFNULL({psi_so_item_col}, '') != ''
            """, tuple(sheet_names), as_dict=True)

            so_item_names = [r.so_item for r in so_item_rows if r.get("so_item")]
            if so_item_names:
                fmt_so_item = ','.join(['%s'] * len(so_item_names))
                wo_item_rows = frappe.db.sql(f"""
                    SELECT wo.{wo_so_item_col} as so_item,
                           SUM(GREATEST(IFNULL(wo.produced_qty, 0), IFNULL(se_map.se_produced_qty, 0))) as produced_qty,
                           COUNT(wo.name) as wo_count
                    FROM `tabWork Order` wo
                    LEFT JOIN (
                        SELECT se.work_order, SUM(IFNULL(sed.qty, 0)) as se_produced_qty
                        FROM `tabStock Entry` se
                        INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                        WHERE se.docstatus = 1
                          AND IFNULL(se.work_order, '') != ''
                          AND IFNULL(sed.is_finished_item, 0) = 1
                        GROUP BY se.work_order
                    ) se_map ON se_map.work_order = wo.name
                    WHERE wo.{wo_so_item_col} IN ({fmt_so_item})
                      AND wo.docstatus < 2
                    GROUP BY wo.{wo_so_item_col}
                """, tuple(so_item_names), as_dict=True)

                for row in wo_item_rows:
                    if row.get("so_item"):
                        so_item_produced_map[row.so_item] = flt(row.produced_qty)
                        so_item_wo_count_map[row.so_item] = cint(row.wo_count)

    data = []
    spr_meta_cache = {}
    pp_docstatus_cache = {}
    spr_pp_gsm_weights_cache = {}
    spr_pp_gsm_index_cache = {}
    spr_pp_gsm_achieved_cache = {}
    spr_pp_gsm_achieved_index_cache = {}
    pp_header_achieved_index_cache = {}
    pp_header_achieved_remaining_cache = {}
    split_so_item_produced_alloc_map = {}
    spr_has_unit_col = False
    try:
        spr_has_unit_col = frappe.db.has_column("Shaft Production Run", "unit")
    except Exception:
        spr_has_unit_col = False

    def _normalize_gsm_key(value):
        txt = str(value or "").strip()
        if not txt:
            return ""
        try:
            num = float(txt)
            if num.is_integer():
                return str(int(num))
            return str(num)
        except Exception:
            return txt

    def _load_spr_gsm_weights_for_pp(pp_id, preferred_spr=None):
        if not pp_id:
            return {}
        cache_key = f"{pp_id}::{preferred_spr or ''}"
        if cache_key in spr_pp_gsm_weights_cache:
            return spr_pp_gsm_weights_cache[cache_key]

        spr_id = str(preferred_spr or "").strip()
        if not spr_id:
            spr_id = str(spr_pp_name_map.get(pp_id) or "").strip()
        if not spr_id:
            raw_link = str(frappe.db.get_value("Production Plan", pp_id, "custom_shaft_production_run_id") or "").strip()
            spr_id = raw_link.split(",")[0].strip() if raw_link else ""

        weights_by_gsm = {}
        if spr_id and frappe.db.exists("Shaft Production Run", spr_id):
            try:
                spr_doc = frappe.get_doc("Shaft Production Run", spr_id)
                for r in (spr_doc.get("shaft_jobs") or []):
                    gsm_key = _normalize_gsm_key(r.get("gsm"))
                    total_weight = flt(r.get("total_weight") or r.get("total_weight_kgs") or 0)
                    if total_weight <= 0:
                        continue
                    if gsm_key not in weights_by_gsm:
                        weights_by_gsm[gsm_key] = []
                    weights_by_gsm[gsm_key].append(total_weight)
            except Exception:
                pass

        spr_pp_gsm_weights_cache[cache_key] = weights_by_gsm
        return weights_by_gsm

    def _load_spr_gsm_achieved_for_pp(pp_id, preferred_spr=None):
        if not pp_id:
            return {}
        cache_key = f"{pp_id}::{preferred_spr or ''}"
        if cache_key in spr_pp_gsm_achieved_cache:
            return spr_pp_gsm_achieved_cache[cache_key]

        spr_id = str(preferred_spr or "").strip()
        if not spr_id:
            spr_id = str(spr_pp_name_map.get(pp_id) or "").strip()
        if not spr_id:
            raw_link = str(frappe.db.get_value("Production Plan", pp_id, "custom_shaft_production_run_id") or "").strip()
            spr_id = raw_link.split(",")[0].strip() if raw_link else ""

        achieved_by_gsm = {}
        if spr_id and frappe.db.exists("Shaft Production Run", spr_id):
            try:
                spr_doc = frappe.get_doc("Shaft Production Run", spr_id)
                for r in (spr_doc.get("shaft_jobs") or []):
                    gsm_key = _normalize_gsm_key(r.get("gsm"))
                    achieved_weight = flt(
                        r.get("custom_total_achieved_weight")
                        or r.get("total_achieved_weight")
                        or r.get("total_achieved_weight_kgs")
                        or r.get("achieved_weight")
                        or r.get("total_achieved")
                        or 0
                    )
                    if achieved_weight <= 0:
                        continue
                    if gsm_key not in achieved_by_gsm:
                        achieved_by_gsm[gsm_key] = []
                    achieved_by_gsm[gsm_key].append(achieved_weight)
            except Exception:
                pass

        spr_pp_gsm_achieved_cache[cache_key] = achieved_by_gsm
        return achieved_by_gsm

    def _take_next_spr_weight(pp_id, gsm_value, preferred_spr=None):
        gsm_key = _normalize_gsm_key(gsm_value)
        if not pp_id or not gsm_key:
            return None

        weights_by_gsm = _load_spr_gsm_weights_for_pp(pp_id, preferred_spr=preferred_spr)
        bucket = weights_by_gsm.get(gsm_key) or []
        if not bucket:
            return None

        idx_key = f"{pp_id}::{gsm_key}"
        idx = spr_pp_gsm_index_cache.get(idx_key, 0)
        if idx >= len(bucket):
            return None

        spr_pp_gsm_index_cache[idx_key] = idx + 1
        return bucket[idx]

    def _take_next_spr_achieved(pp_id, gsm_value, preferred_spr=None):
        gsm_key = _normalize_gsm_key(gsm_value)
        if not pp_id or not gsm_key:
            return 0

        achieved_by_gsm = _load_spr_gsm_achieved_for_pp(pp_id, preferred_spr=preferred_spr)
        bucket = achieved_by_gsm.get(gsm_key) or []
        if not bucket:
            return 0

        idx_key = f"{pp_id}::{preferred_spr or ''}::{gsm_key}"
        idx = spr_pp_gsm_achieved_index_cache.get(idx_key, 0)
        if idx >= len(bucket):
            return 0

        spr_pp_gsm_achieved_index_cache[idx_key] = idx + 1
        return flt(bucket[idx])

    def _take_next_pp_header_achieved(pp_id, row_qty=0):
        if not pp_id:
            return 0
        if pp_id not in pp_header_achieved_remaining_cache:
            pp_header_achieved_remaining_cache[pp_id] = flt(spr_pp_achieved_weight_map.get(pp_id) or 0)
            pp_header_achieved_index_cache[pp_id] = 0

        remaining = flt(pp_header_achieved_remaining_cache.get(pp_id) or 0)
        if remaining <= 0:
            return 0

        qty_cap = flt(row_qty or 0)
        alloc = min(remaining, qty_cap) if qty_cap > 0 else remaining
        if alloc <= 0:
            return 0

        pp_header_achieved_remaining_cache[pp_id] = max(remaining - alloc, 0)
        pp_header_achieved_index_cache[pp_id] = cint(pp_header_achieved_index_cache.get(pp_id) or 0) + 1
        return flt(alloc)
    for sheet in planning_sheets:
        items = frappe.get_all(
            "Planning Table",
            filters={"parent": sheet.name},
            fields=["*"],
            order_by="idx"
        )
        so_item_row_counts = {}
        for _it in items:
            _k = (_it.get("sales_order_item") or _it.get("custom_sales_order_item") or "").strip()
            if _k:
                so_item_row_counts[_k] = so_item_row_counts.get(_k, 0) + 1
        pt_by_name = {it.get("name"): it for it in items if it.get("name")}

        def _pt_root_ancestor(nm):
            """Oldest Planning Table row in a split chain (split_from / custom_split_from)."""
            seen = set()
            cur = nm
            while cur in pt_by_name:
                it = pt_by_name[cur]
                sf = (it.get("split_from") or it.get("custom_split_from") or "").strip()
                if not sf or sf not in pt_by_name or cur in seen:
                    return cur
                seen.add(cur)
                cur = sf
            return cur

        pt_split_root = {nm: _pt_root_ancestor(nm) for nm in pt_by_name}
        from collections import Counter

        _root_tally = Counter(pt_split_root.values())
        pt_in_multi_split = {nm: _root_tally[pt_split_root[nm]] > 1 for nm in pt_split_root}
        # Sum SPR-produced weight per allocation bucket (SO line or split family without SO link).
        spr_claimed_by_bucket = {}
        for _it in items:
            _pn = _it.get("name")
            if not _pn or _pn not in spr_psi_produced_map:
                continue
            amt = flt(spr_psi_produced_map.get(_pn, 0))
            _k = (_it.get("sales_order_item") or _it.get("custom_sales_order_item") or "").strip()
            if _k and so_item_row_counts.get(_k, 0) > 1:
                bucket = f"so::{_k}"
            elif pt_in_multi_split.get(_pn, False):
                bucket = f"ptroot::{pt_split_root.get(_pn, _pn)}"
            else:
                continue
            spr_claimed_by_bucket[bucket] = spr_claimed_by_bucket.get(bucket, 0) + amt

        # Determine PP and WO boolean states for this sheet
        sheet_has_pp = False
        sheet_has_wo = False
        
        my_pp_name = sheet_pp_map.get(sheet.name)
        if not my_pp_name and sheet.sales_order:
            my_pp_name = so_pp_map.get(sheet.sales_order)
            
        if my_pp_name:
            sheet_has_pp = True
            
        # Calculate Produced Qty
        produced_weight = 0
        if my_pp_name and my_pp_name in pp_wo_map:
            sheet_has_wo = True
            # Sum produced_qty from all WOs for this PP (heuristic)
            produced_weight = sum([w["produced_qty"] for w in pp_wo_map[my_pp_name]])
        elif sheet.sales_order and sheet.sales_order in so_wo_map:
            sheet_has_wo = True
            # Fallback if we only have one WO link
            wo_name = so_wo_map.get(sheet.sales_order)
            produced_weight = frappe.db.get_value("Work Order", wo_name, "produced_qty") or 0

        for item in items:
            if LAMINATION_FLOW_ENABLED and bps:
                icp = _item_process_prefix(item.get("item_code") or "")
                if bps == "exclude_104" and icp == "104":
                    continue
                if bps == "lamination_only" and icp != "104":
                    continue

            color = (item.get("color") or item.get("colour") or "").strip()
            quality = (item.get("custom_quality") or "").strip()
            
            # Fallback for missing data instead of skipping (prevents "hidden" orders)
            if not color: color = "Unknown Color"
            if not quality: quality = "Unknown Quality"
            if color.upper() == "NO COLOR":
                continue

            # ΓöÇΓöÇ KEY FIX: Restore missing item details from sheet data ΓöÇΓöÇ
            unit = (item.get("unit") or sheet.get("unit") or "Unit 1").strip()
            if unit.upper() in ["UNIT 1", "UNIT 2", "UNIT 3", "UNIT 4"]:
                unit = unit.title()
            
            effective_date_str = str(item.get("ordered_date") or sheet.get("ordered_date") or "")
            
            # ΓöÇΓöÇ Granular filtering: determine if item belongs to the current date view ΓöÇΓöÇ
            item_pdate = item.get("planned_date")
            is_white = _is_white_color(color)
            
            # Effective item date for filtering: 
            # Unpushed non-white items stick to ordered_date.
            # Pushed items (or auto-pushed whites) stick to their planned/pushed date.
            i_eff_pdate = item_pdate or (sheet.get("custom_planned_date") if is_white else None) or sheet.get("ordered_date")
            
            if date or (start_date and end_date):
                try:
                    it_pdt_norm = getdate(str(i_eff_pdate)) if i_eff_pdate else None
                except Exception:
                    it_pdt_norm = None
                
                if it_pdt_norm:
                    if start_date and end_date:
                        if not (it_pdt_norm >= query_start and it_pdt_norm <= query_end):
                            continue
                    elif target_dates:
                        if it_pdt_norm not in target_dates:
                            continue

            # Production Board special filtering: only show scheduled items if planned_only is requested
            if cint(planned_only):
                # NON-WHITE items MUST be explicitly pushed (have a planned date)
                if not is_white and not item_pdate:
                    continue

            psi_name = item.get("name")
            so_item_key = (item.get("sales_order_item") or item.get("custom_sales_order_item") or "").strip()
            split_group = bool(so_item_key and so_item_row_counts.get(so_item_key, 0) > 1) or pt_in_multi_split.get(
                psi_name, False
            )
            item_pp = item_pp_map.get(item.get("name"))
            if not item_pp:
                item_pp = _get_item_level_production_plan(item.get("name"))
                if item_pp:
                    item_pp_map[item.get("name")] = item_pp

            # Legacy sheets may not have item-level PP populated; resolve via SO item and persist.
            if not item_pp and so_item_key:
                if so_item_key not in so_item_pp_cache:
                    so_item_pp_cache[so_item_key] = _resolve_pp_by_sales_order_item(so_item_key)
                item_pp = so_item_pp_cache.get(so_item_key)
                if item_pp:
                    item_pp_map[item.get("name")] = item_pp
                    if psi_pp_field and frappe.db.has_column("Planning Table", psi_pp_field):
                        try:
                            current_pp = frappe.db.get_value("Planning Table", item.get("name"), psi_pp_field)
                            if not current_pp:
                                frappe.db.set_value("Planning Table", item.get("name"), psi_pp_field, item_pp)
                        except Exception:
                            pass

            # Strict per-item production mapping (no header/plan total fallback).
            item_level_produced = None
            item_level_wo_count = 0

            if psi_name and psi_name in spr_psi_produced_map:
                item_level_produced = spr_psi_produced_map.get(psi_name, 0)
                item_level_wo_count = max(item_level_wo_count, spr_psi_count_map.get(psi_name, 0))

            if item_level_produced is None and so_item_key:
                if so_item_key in so_item_produced_map:
                    item_level_produced = so_item_produced_map.get(so_item_key, 0)
                    item_level_wo_count = max(item_level_wo_count, so_item_wo_count_map.get(so_item_key, 0))
                elif so_item_key in spr_so_item_produced_map:
                    item_level_produced = spr_so_item_produced_map.get(so_item_key, 0)
                    item_level_wo_count = max(item_level_wo_count, spr_so_item_count_map.get(so_item_key, 0))

            # Do not use SPR shaft_jobs target weight as produced fallback.
            # Produced quantity must come from produced sources only (WO/SE/SPR produced fields).

            if item_level_produced is None and item_pp and not so_item_key and not cint(item.get("is_split")):
                item_level_produced = pp_produced_map.get(item_pp)
                item_level_wo_count = max(item_level_wo_count, pp_wo_count_map.get(item_pp, 0))
                if item_level_produced is None:
                    item_level_produced = spr_pp_produced_map.get(item_pp)
                    item_level_wo_count = max(item_level_wo_count, spr_pp_count_map.get(item_pp, 0))

            # Strict fallback for legacy rows with missing SO-item/PP links:
            # derive via Sales Order -> Production Plan -> Work Order -> production_item.
            if item_level_produced is None:
                item_code_key = (item.get("item_code") or "").strip()
                sales_order_key = (sheet.sales_order or "").strip()
                if sales_order_key and item_code_key:
                    sheet_order_code = (sheet.get("party_code") or "").strip()
                    if sheet_order_code:
                        so_item_order_map_key = f"{sales_order_key}::{item_code_key}::{sheet_order_code}"
                        if so_item_order_map_key in so_item_code_order_produced_map:
                            item_level_produced = so_item_code_order_produced_map.get(so_item_order_map_key, 0)
                            item_level_wo_count = max(item_level_wo_count, so_item_code_order_wo_count_map.get(so_item_order_map_key, 0))

            if item_level_produced is None:
                item_code_key = (item.get("item_code") or "").strip()
                sales_order_key = (sheet.sales_order or "").strip()
                if sales_order_key and item_code_key:
                    so_item_map_key = f"{sales_order_key}::{item_code_key}"
                    if so_item_map_key in so_item_code_produced_map:
                        item_level_produced = so_item_code_produced_map.get(so_item_map_key, 0)
                        item_level_wo_count = max(item_level_wo_count, so_item_code_wo_count_map.get(so_item_map_key, 0))

            # Final strict fallback without Sales Order: party_code(order_code) + item_code.
            if item_level_produced is None:
                item_code_key = (item.get("item_code") or "").strip()
                order_code_key = (sheet.get("party_code") or "").strip()
                if order_code_key and item_code_key:
                    order_item_key = f"{order_code_key}::{item_code_key}"
                    if order_item_key in order_code_item_produced_map:
                        item_level_produced = order_code_item_produced_map.get(order_item_key, 0)
                        item_level_wo_count = max(item_level_wo_count, order_code_item_wo_count_map.get(order_item_key, 0))

            # Safe fallback: only rows with no item key can use SO aggregate.
            if item_level_produced is None and not so_item_key and sheet.sales_order:
                item_level_produced = so_produced_map.get(sheet.sales_order)
                item_level_wo_count = max(item_level_wo_count, so_wo_count_map.get(sheet.sales_order, 0))

            if item_level_produced is None:
                item_level_produced = 0

            # Split-safe produced allocation: distribute produced total once across split rows.
            # Skip allocation when per-item SPR data is available — each row shows its own SPR weight.
            # split_group: first row may not have is_split=1; spr_claimed subtracts weight already on SPR-linked rows.
            # alloc_bucket: same SO line, or split_from family when sales_order_item is missing on child rows.
            has_own_spr_produced = psi_name and psi_name in spr_psi_produced_map
            alloc_bucket = ""
            if so_item_key and so_item_row_counts.get(so_item_key, 0) > 1:
                alloc_bucket = f"so::{so_item_key}"
            elif pt_in_multi_split.get(psi_name, False):
                alloc_bucket = f"ptroot::{pt_split_root.get(psi_name, psi_name)}"
            if alloc_bucket and (cint(item.get("is_split")) or split_group) and not has_own_spr_produced:
                produced_total = flt(item_level_produced)
                already_alloc = flt(split_so_item_produced_alloc_map.get(alloc_bucket, 0))
                spr_claimed = flt(spr_claimed_by_bucket.get(alloc_bucket, 0))
                row_qty = flt(item.get("qty", 0))
                pool = max(produced_total - spr_claimed, 0)
                row_alloc = min(max(pool - already_alloc, 0), row_qty)
                split_so_item_produced_alloc_map[alloc_bucket] = already_alloc + row_alloc
                item_level_produced = row_alloc

            # Only Planning Table `spr_name` ties this row to an SPR (never SO/PP/SPR field alone).
            spr_name = (item.get("spr_name") or "").strip()

            spr_docstatus = None
            spr_unit = ""
            if spr_name:
                if spr_name in spr_meta_cache:
                    spr_docstatus = spr_meta_cache[spr_name].get("docstatus")
                    spr_unit = spr_meta_cache[spr_name].get("unit") or ""
                else:
                    spr_fields = ["docstatus"] + (["unit"] if spr_has_unit_col else [])
                    spr_meta = frappe.db.get_value("Shaft Production Run", spr_name, spr_fields, as_dict=True) or {}
                    spr_docstatus = spr_meta.get("docstatus")
                    spr_unit = spr_meta.get("unit") or ""
                    spr_meta_cache[spr_name] = {"docstatus": spr_docstatus, "unit": spr_unit}

            item_pending_qty = max(flt(item.get("qty", 0)) - flt(item_level_produced), 0)

            pp_docstatus = None
            if item_pp:
                if item_pp in pp_docstatus_cache:
                    pp_docstatus = pp_docstatus_cache[item_pp]
                else:
                    pp_docstatus = cint(frappe.db.get_value("Production Plan", item_pp, "docstatus") or 0)
                    pp_docstatus_cache[item_pp] = pp_docstatus

            pp_target_qty = flt(pp_wo_target_qty_map.get(item_pp, 0)) if item_pp else 0
            pp_produced_qty = flt(pp_wo_produced_qty_map.get(item_pp, 0)) if item_pp else 0
            pp_pending_qty = max(pp_target_qty - pp_produced_qty, 0) if item_pp else 0

            # Strict remaining rule for stock-entry actions should follow WO pending for the PP.
            pending_qty = min(item_pending_qty, pp_pending_qty) if item_pp else item_pending_qty
            wo_open = bool(item_pp and pp_has_open_wo_map.get(item_pp))
            wo_terminal = bool(item_pp and pp_has_wo_map.get(item_pp) and not wo_open)

            # Actual kg: only when this Planning row has `spr_name` (maps are keyed by PT name from join).
            row_spr = (item.get("spr_name") or "").strip()
            total_achieved_weight_kgs = 0
            if row_spr and psi_name and psi_name in spr_psi_achieved_weight_map:
                total_achieved_weight_kgs = spr_psi_achieved_weight_map[psi_name]
            elif row_spr and psi_name and psi_name in spr_psi_produced_map:
                total_achieved_weight_kgs = spr_psi_produced_map[psi_name]
            elif item_pp and row_spr:
                spr_row_achieved = _take_next_spr_achieved(item_pp, item.get("gsm"), preferred_spr=row_spr)
                if spr_row_achieved > 0:
                    total_achieved_weight_kgs = spr_row_achieved
                else:
                    total_achieved_weight_kgs = _take_next_pp_header_achieved(item_pp, item.get("qty"))

            # Production Table shows actual_production_weight_kgs from this field.
            # Split rows: keep per-row SPR weight when this Planning Table row is linked to an SPR
            # (spr_psi_* maps); only use allocated item_level_produced when no SPR weight exists.
            if cint(item.get("is_split")) or split_group:
                has_psi_spr_weight = row_spr and psi_name and (
                    (psi_name in spr_psi_achieved_weight_map and flt(spr_psi_achieved_weight_map.get(psi_name)) > 0)
                    or (psi_name in spr_psi_produced_map and flt(spr_psi_produced_map.get(psi_name)) > 0)
                )
                if not has_psi_spr_weight:
                    if row_spr:
                        total_achieved_weight_kgs = flt(item_level_produced)
                    else:
                        total_achieved_weight_kgs = 0
            
            delivered_qty = max(
                flt(so_item_delivered_qty_map.get(((sheet.sales_order or "").strip(), (item.get("item_code") or "").strip()), 0)),
                flt(order_item_delivered_qty_map.get(((sheet.party_code or "").strip(), (item.get("item_code") or "").strip()), 0)),
            )
            if delivered_qty > 0:
                if delivered_qty + 1e-9 >= flt(item.get("qty", 0)):
                    row_delivery_status = "Fully Delivered"
                else:
                    row_delivery_status = "Partly Delivered"
            else:
                row_delivery_status = so_status_map.get(sheet.sales_order) or "Not Delivered"

            data.append({
                "name": "{}-{}".format(sheet.name, item.get("idx", 0)),
                "itemName": item.name,
                "itemCode": (item.get("item_code") or "").strip(),
                "description": item.item_name or "",
                "planningSheet": sheet.name,
                "customer": sheet.customer,
                "customer_name": (sheet.get("party_name") or sheet.customer or sheet.party_code or ""),
                "partyCode": sheet.party_code,
                "salesOrder": (sheet.sales_order or "").strip(),
                "planningStatus": sheet.planning_status or "Draft",
                "docstatus": sheet.docstatus,
                "orderDate": effective_date_str,
                "color": color.upper().strip(),
                "quality": item.get("custom_quality") or item.get("quality") or "",
                "gsm": item.get("gsm") or "",
                "qty": flt(item.get("qty", 0)),
                "idx": item.get("idx", 0),
                "width": flt(item.get("width") or item.get("custom_width") or item.get("width_inches") or item.get("width_inch") or item.get("width_in") or 0),
                "unit": unit,
                "planName": sheet.get("planName") or sheet.get("custom_plan_name") or "Default",
                "pbPlanName": sheet.get("custom_pb_plan_name") or "",
                "planCode": (item.get("custom_plan_code") or item.get("plan_name") or ""),
                "ordered_date": str(sheet.ordered_date) if sheet.ordered_date else "",
                "planned_date": str(item_pdate or (sheet.get("custom_planned_date") if is_white else "")),
                "plannedDate": str(item_pdate or (sheet.get("custom_planned_date") if is_white else "")),
                "dod": str(sheet.dod) if sheet.dod else "",
                "delivery_status": row_delivery_status,
                "has_pp": bool(item_pp or sheet_has_pp),
                "has_wo": bool(item_level_wo_count),
                "produced_qty": flt(item_level_produced),
                "salesOrderItem": so_item_key,
                "actual_produced_qty": flt(item_level_produced),
                "actual_production_weight_kgs": flt(total_achieved_weight_kgs),
                # Legacy key kept for compatibility with cached/older frontend bundles.
                "total_achieved_weight_kgs": flt(total_achieved_weight_kgs),
                "pending_qty": flt(pending_qty),
                "item_pending_qty": flt(item_pending_qty),
                "pp_target_qty": flt(pp_target_qty),
                "pp_produced_qty": flt(pp_produced_qty),
                "pp_pending_qty": flt(pp_pending_qty),
                "wo_open": wo_open,
                "wo_terminal": wo_terminal,
                "isSplit": item.get("is_split"),
                "pp_id": item_pp or "",  # Item-level production plan ID for direct PP view routing
                "pp_docstatus": pp_docstatus,
                "spr_name": spr_name,  # SPR linked to PP (validated)
                "spr_docstatus": spr_docstatus,
                "spr_unit": spr_unit,
            })

    if cint(planned_only) and plan_name == "__all__":
        return _deduplicate_items(data)

    return data

def _deduplicate_items(items):
    """
    Helper to prevent duplicate orders appearing in board/list views.
    Groups by sales_order_item and prioritizes:
    1. Scheduled items (in custom plans) over Draft items (in Default).
    2. Newer items (higher idx or recent creation) over older ones.
    Legitimate splits (is_split=1) are PRESERVED.
    """
    seen = {}
    result = []
    for item in items:
        # Support both dict keys (camelCase vs snake_case) 
        so_item = item.get("salesOrderItem") or item.get("sales_order_item")
        is_split = item.get("isSplit") or item.get("is_split")
        
        if is_split or not so_item:
            result.append(item)
            continue
            
        if so_item not in seen:
            seen[so_item] = item
            result.append(item)
        else:
            existing = seen[so_item]
            e_plan_raw = existing.get("planName") or existing.get("custom_plan_name") or "Default"
            i_plan_raw = item.get("planName") or item.get("custom_plan_name") or "Default"
            
            # Strip legacy prefixes for logic consistency (e.g. 'MARCH W12 26 PLAN 1' -> 'PLAN 1')
            e_plan = _strip_legacy_prefixes(e_plan_raw)
            i_plan = _strip_legacy_prefixes(i_plan_raw)
            
            replace = False
            # Priority 1: Specific Plan > Default
            if e_plan == "Default" and i_plan != "Default":
                replace = True
            # Priority 2: Newer Sheet wins if both are specific plans or both are Default
            # Since items is ordered by creation, 'item' is newer than 'existing'
            elif e_plan == i_plan or (e_plan != "Default" and i_plan != "Default"):
                replace = True
                
            if replace:
                if existing in result:
                    result.remove(existing)
                seen[so_item] = item
                result.append(item)
    return result

    return data


@frappe.whitelist()
def get_orders_for_date(date):
    """Returns all Planning Sheet Items for a specific date (used by Pull Orders dialog)."""
    if not date:
        return []
    target_date = getdate(date)
    eff = _effective_date_expr("p")
    extra_fields = ", p.custom_planned_date" if _has_planned_date_column() else ""
    
    items = frappe.db.sql(f"""
        SELECT 
            i.name, i.item_code, i.item_name, i.qty, i.uom, i.unit,
            i.color, i.custom_quality as quality, i.gsm, i.width,
            p.name as planning_sheet, p.party_code, p.customer,
            COALESCE(c.customer_name, p.customer) as customer_name,
            p.ordered_date{extra_fields},
            {eff} as effective_date
        FROM `tabPlanning Table` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        LEFT JOIN `tabCustomer` c ON p.customer = c.name
        WHERE {eff} = %s
          AND p.docstatus < 2
        ORDER BY i.unit, i.idx
    """, (target_date,), as_dict=True)
    
    return items



@frappe.whitelist()
def update_item_unit(item_name, unit):
    if not item_name or not unit:
        frappe.throw(_("Item Name and Unit are required"))

    frappe.db.set_value(
        "Planning Table", item_name, "unit", normalize_planning_unit_for_select(unit)
    )
    return {"status": "success"}


@frappe.whitelist()
def update_items_bulk(items, plan_name=None):
    """Bulk move/update Planning Sheet Items.

    Each entry in ``items`` can optionally specify:
    - name: Planning Sheet Item name (required)
    - unit: target unit (optional, falls back to current)
    - date: target date as string (optional, falls back to current effective date)
    - index: desired 1-based position within the (unit, date, plan) slot (optional)
    - force_move / perform_split / strict_next_day: forwarded to update_schedule

    We intentionally route through ``update_schedule`` so that capacity rules,
    quality rules, and idx-based re-sequencing remain consistent with
    single-item drag-and-drop behaviour on the board.
    """
    import json

    if isinstance(items, str):
        items = json.loads(items)
    
    if not items:
        return {"status": "success", "count": 0}

    moved_dates = set()
    count = 0

    for row in items:
        name = row.get("name")
        if not name:
            continue

        # Fetch current state to provide sensible fallbacks
        current = frappe.db.get_value(
            "Planning Table",
            name,
            ["unit", "parent", "planned_date"],
            as_dict=True,
        )
        if not current:
            continue

        target_unit = row.get("unit") or current.unit

        # Resolve effective date using item-level date first; fallback to parent dates.
        target_date = row.get("date")
        if not target_date:
            target_date = current.get("planned_date")
        if not target_date:
            parent_sheet = frappe.db.get_value(
                "Planning sheet",
                current.parent,
                ["custom_planned_date", "ordered_date"],
                as_dict=True,
            )
            if parent_sheet:
                target_date = parent_sheet.custom_planned_date or parent_sheet.ordered_date

        if not target_date:
            # If we still don't have a date, skip this item
            continue

        index = row.get("index") or 0
        force_move = row.get("force_move", 0)
        perform_split = row.get("perform_split", 0)
        strict_next_day = row.get("strict_next_day", 0)

        res = update_schedule(
            name,
            target_unit,
            target_date,
            index=index,
            force_move=force_move,
            perform_split=perform_split,
            plan_name=plan_name,
            strict_next_day=strict_next_day,
        )

        if isinstance(res, dict) and res.get("status") == "success":
            moved_dates.add(str(target_date))
            count += 1

    # Fire a coarse realtime update for all affected dates
    for d in moved_dates:
        try:
            frappe.publish_realtime("production_board_update", {"date": d})
        except Exception:
            pass

    return {
        "status": "success",
        "count": count,
        "skipped": 0,
        "dates": sorted(list(moved_dates))
    }


@frappe.whitelist()
def bulk_confirm_orders(items):
    """
    Confirms multiple orders from the Production Board.
    Updates custom_production_status on the linked Sales Order to 'Confirmed'.
    """
    import json
    if isinstance(items, str):
        items = json.loads(items)
    
    if not items:
        return {"status": "error", "message": "No items selected"}

    count = 0
    for item_name in items:
        # Planning Sheet -> Sales Order
        parent_sheet = frappe.db.get_value("Planning Table", item_name, "parent")
        if parent_sheet:
            so_name = frappe.db.get_value("Planning sheet", parent_sheet, "sales_order")
            if so_name:
                # Set Sales Order status to Confirmed
                frappe.db.set_value("Sales Order", so_name, "custom_production_status", "Confirmed")
                # Update Planning Sheet status to Finalized
                frappe.db.set_value("Planning sheet", parent_sheet, "planning_status", "Finalized")
                count += 1
    
    frappe.db.commit()
    # Trigger realtime update
    frappe.publish_realtime("production_board_update", {"type": "confirmation"})
    
    return {"status": "success", "message": f"Successfully confirmed {count} orders.", "count": count}


@frappe.whitelist()
def get_plans(date=None, start_date=None, end_date=None, **kwargs):
    """Get unique plan names for a date or date range."""
    eff = _effective_date_expr("p")
    
    if start_date and end_date:
        query_start = getdate(start_date)
        query_end = getdate(end_date)
        date_condition = f"{eff} BETWEEN %s AND %s"
        params = [query_start, query_end]
    elif date:
        if "," in str(date):
            target_dates = [getdate(d.strip()) for d in str(date).split(",") if d.strip()]
            fmt = ','.join(['%s'] * len(target_dates))
            date_condition = f"{eff} IN ({fmt})"
            params = target_dates
        else:
            target_date = getdate(date)
            date_condition = f"{eff} = %s"
            params = [target_date]
    else:
        return ["Default"]
    
    plans = frappe.db.sql(f"""
        SELECT DISTINCT IFNULL(p.custom_plan_name, 'Default') as plan_name
        FROM `tabPlanning sheet` p
        WHERE {date_condition} AND p.docstatus < 2
        ORDER BY plan_name ASC
    """, tuple(params), as_dict=True)
    
    unique_plans = [p.plan_name or "Default" for p in plans]
    if "Default" not in unique_plans:
        unique_plans.insert(0, "Default")
    # Ensure Default is first
    if unique_plans[0] != "Default":
        unique_plans.remove("Default")
        unique_plans.insert(0, "Default")
    
    return unique_plans

# --------------------------------------------------------------------------------
# Persistent Plans System
# --------------------------------------------------------------------------------

def get_persisted_plans(plan_type):
    """Returns list of dicts: [{'name': '...', 'locked': 0}] from frappe.defaults"""
    key = f"production_scheduler_{plan_type}_plans"
    val = frappe.defaults.get_global_default(key)
    if val:
        import json
        try:
            return json.loads(val)
        except:
            pass
    if plan_type == "color_chart":
        return [{"name": "Default", "locked": 0}]
    return []

@frappe.whitelist()
def add_persistent_plan(plan_type, name):
    plans = get_persisted_plans(plan_type)
    if not any(p.get("name") == name for p in plans):
        plans.append({"name": name, "locked": 0})
        import json
        frappe.defaults.set_global_default(f"production_scheduler_{plan_type}_plans", json.dumps(plans))
    return plans

@frappe.whitelist()
def toggle_plan_lock(plan_type, name, locked):
    plans = get_persisted_plans(plan_type)
    for p in plans:
        if p.get("name") == name:
            p["locked"] = int(locked)
    import json
    frappe.defaults.set_global_default(f"production_scheduler_{plan_type}_plans", json.dumps(plans))
    return plans

@frappe.whitelist()
def get_active_plans():
    cc_plans = get_persisted_plans("color_chart")
    pb_plans = get_persisted_plans("production_board")
    active_cc = next((p["name"] for p in cc_plans if not p.get("locked")), "Default")
    active_pb = next((p["name"] for p in pb_plans if not p.get("locked")), "")
    return {"color_chart": active_cc, "production_board": active_pb}

# --------------------------------------------------------------------------------
# Persistent Plans System
# --------------------------------------------------------------------------------

def get_persisted_plans(plan_type):
    """Returns list of dicts: [{'name': '...', 'locked': 0}] from frappe.defaults"""
    key = f"production_scheduler_{plan_type}_plans"
    val = frappe.defaults.get_global_default(key)
    if val:
        import json
        try:
            plans = json.loads(val)
            if isinstance(plans, str):
                plans = json.loads(plans)
            if not isinstance(plans, list):
                plans = []
            if not any(isinstance(p, dict) and p.get("name") == "Default" for p in plans):
                plans.insert(0, {"name": "Default", "locked": 0})
            return plans
        except:
            pass
    if plan_type == "color_chart":
        return [{"name": "Default", "locked": 0}]
    return []

@frappe.whitelist()
def add_persistent_plan(plan_type, name):
    plans = get_persisted_plans(plan_type)
    if not any(p.get("name") == name for p in plans):
        plans.append({"name": name, "locked": 0})
        import json
        frappe.defaults.set_global_default(f"production_scheduler_{plan_type}_plans", json.dumps(plans))
    return plans

@frappe.whitelist()
def toggle_plan_lock(plan_type, name, locked):
    plans = get_persisted_plans(plan_type)
    for p in plans:
        if p.get("name") == name:
            p["locked"] = int(locked)
    import json
    frappe.defaults.set_global_default(f"production_scheduler_{plan_type}_plans", json.dumps(plans))
    return plans

@frappe.whitelist()
def get_active_plans():
    cc_plans = get_persisted_plans("color_chart")
    pb_plans = get_persisted_plans("production_board")
    active_cc = next((p["name"] for p in cc_plans if not p.get("locked")), "Default")
    active_pb = next((p["name"] for p in pb_plans if not p.get("locked")), "")
    return {"color_chart": active_cc, "production_board": active_pb}


@frappe.whitelist()
def get_monthly_plans(start_date, end_date):
    query_start = getdate(start_date)
    query_end = getdate(end_date)
    
    plans = frappe.db.get_all(
        "Planning sheet", 
        filters={
            "ordered_date": ["between", [query_start, query_end]],
            "docstatus": ["<", 2]
        }, 
        fields=["custom_plan_name"]
    )
    
    # Extract base names and merge duplicates
    db_raw = set([p.custom_plan_name or "Default" for p in plans])
    persisted_raw = get_persisted_plans("color_chart")

    merged_plans = {} # base_name -> {locked: bool}

    # Process DB plans
    for name in db_raw:
        base = _strip_legacy_prefixes(name)
        if base not in merged_plans:
            merged_plans[base] = {"locked": 0}

    # Process Persisted plans (global defaults)
    for p in persisted_raw:
        base = _strip_legacy_prefixes(p["name"])
        # If both are present, we prefer the lock status of the "cleaner" or explicit one
        is_locked = p.get("locked", 0)
        if base not in merged_plans or is_locked:
            merged_plans[base] = {"locked": is_locked}

    sorted_names = sorted(merged_plans.keys())
    if "Default" in sorted_names:
        sorted_names.remove("Default")
        sorted_names.insert(0, "Default")
        
    return [{"name": n, "locked": merged_plans[n]["locked"]} for n in sorted_names]

@frappe.whitelist()
def migrate_to_full_plan_names():
    """
    Migration Script (One-time):
    Converts all existing 'custom_plan_name' (e.g. 'PLAN 1') to the full 
    prefixed format (e.g. 'MARCH W12 26 PLAN 1') based on the sheet's 
    ordered_date / custom_planned_date.
    
    Also updates the Global Defaults for persisted plans.
    """
    sheets = frappe.db.get_all("Planning sheet", filters={"docstatus": ["<", 2]}, fields=["name", "custom_plan_name", "ordered_date", "custom_planned_date"])
    
    updated_sheets = 0
    new_global_plans = set()
    
    for s in sheets:
        if not s.custom_plan_name or s.custom_plan_name == "Default":
            continue
            
        full_name = _get_contextual_plan_name(s.custom_plan_name, s.custom_planned_date or s.ordered_date)
        
        if full_name != s.custom_plan_name:
            frappe.db.set_value("Planning sheet", s.name, "custom_plan_name", full_name, update_modified=False)
            updated_sheets += 1
        
        new_global_plans.add(full_name)
    
    # Update Persisted Plans in Global Defaults
    # We merge existing persisted plans but using their full names if possible
    old_persisted = get_persisted_plans("color_chart")
    # For each persisted plan, if it's a base name, we might not know the date.
    # But we can at least ensure if any sheet uses it, it's kept.
    
    current_full_list = [{"name": p["name"], "locked": p.get("locked", 0)} for p in old_persisted]
    # (Note: we don't automatically know which month to prefix a generic "PLAN 1" in defaults,
    # but the sheets update above will capture all actually used ones.)
    
    for full in new_global_plans:
        if not any(p["name"] == full for p in current_full_list):
            current_full_list.append({"name": full, "locked": 0})
            
    import json
    frappe.defaults.set_global_default("production_scheduler_color_chart_plans", json.dumps(current_full_list))
    
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": f"Updated {updated_sheets} sheets. Refined persisted plans list.",
        "total_plans": len(current_full_list)
    }

@frappe.whitelist()
def cleanup_legacy_plans():
    pass

@frappe.whitelist()
def create_plan_name_field():
    if not frappe.db.exists('Custom Field', 'Planning sheet-custom_plan_name'):
        custom_field = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning sheet",
            "fieldname": "custom_plan_name",
            "label": "Plan Name",
            "fieldtype": "Data",
            "insert_after": "planning_status"
        })
        custom_field.insert(ignore_permissions=True)
    
    # Create Planned Date custom field
    if not frappe.db.exists('Custom Field', 'Planning sheet-custom_planned_date'):
        custom_field2 = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning sheet",
            "fieldname": "custom_planned_date",
            "label": "Planned Date",
            "fieldtype": "Date",
            "insert_after": "ordered_date",
            "description": "Actual planned production date. If empty, ordered_date is used."
        })
        custom_field2.insert(ignore_permissions=True)
    
    
    # Fix: Set NULL custom_plan_name to 'Default' so plan filtering works correctly
    if frappe.db.has_column("Planning sheet", "custom_plan_name"):
        frappe.db.sql("""
            UPDATE `tabPlanning sheet` 
            SET custom_plan_name = 'Default' 
            WHERE custom_plan_name IS NULL OR custom_plan_name = ''
        """)
        frappe.db.commit()
        
    # Cleanup: Remove Production Board Plan field as requested
    if frappe.db.exists('Custom Field', 'Planning sheet-custom_pb_plan_name'):
        frappe.db.sql("DELETE FROM `tabCustom Field` WHERE name = 'Planning sheet-custom_pb_plan_name'")
        frappe.db.commit()

    # Create Plan Code custom fields for Tracking Code logic
    sheet_meta = frappe.get_meta("Planning sheet")
    pt_meta = frappe.get_meta("Planning Table")
    psi_meta = frappe.get_meta("Planning sheet Item")

    if (not sheet_meta.has_field("plan_name")) and (not frappe.db.exists('Custom Field', 'Planning sheet-plan_name')):
        cf4 = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning sheet",
            "fieldname": "plan_name",
            "label": "Plan Code",
            "fieldtype": "Data",
            "read_only": 0,
            "insert_after": "custom_plan_name"
        })
        cf4.insert(ignore_permissions=True)
    else:
        if frappe.db.exists('Custom Field', 'Planning sheet-plan_name'):
            frappe.db.set_value('Custom Field', 'Planning sheet-plan_name', 'read_only', 0)
        
    if (not pt_meta.has_field("plan_name")) and (not frappe.db.exists('Custom Field', {'dt': 'Planning Table', 'fieldname': 'plan_name'})):
        cf5 = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning Table",
            "fieldname": "plan_name",
            "label": "Plan Code",
            "fieldtype": "Data",
            "read_only": 0,
            "insert_after": "color",
            "in_list_view": 1
        })
        cf5.insert(ignore_permissions=True)
    else:
        cf_name = frappe.db.get_value('Custom Field', {'dt': 'Planning Table', 'fieldname': 'plan_name'}, 'name')
        if cf_name:
            frappe.db.set_value('Custom Field', cf_name, 'read_only', 0)

    if (not psi_meta.has_field("plan_name")) and (not frappe.db.exists('Custom Field', {'dt': 'Planning sheet Item', 'fieldname': 'plan_name'})):
        cf5b = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning sheet Item",
            "fieldname": "plan_name",
            "label": "Plan Code",
            "fieldtype": "Data",
            "read_only": 0,
            "insert_after": "color",
            "in_list_view": 1
        })
        cf5b.insert(ignore_permissions=True)

    # Create Approval Status custom field on Planning Sheet
    if not frappe.db.exists('Custom Field', 'Planning sheet-custom_approval_status'):
        cf6 = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning sheet",
            "fieldname": "custom_approval_status",
            "label": "Approval Status",
            "fieldtype": "Select",
            "options": "Draft\nPending Approval\nApproved",
            "default": "Draft",
            "insert_after": "planning_status"
        })
        cf6.insert(ignore_permissions=True)
    
    frappe.db.commit()
    
    # Automatically kick off a background job to populate old sheets if they are missing codes
    frappe.enqueue("production_entry.production_planning.scheduler_api.backfill_plan_codes", queue="short", timeout=300)

    return {"status": "success"}

@frappe.whitelist()
def backfill_plan_codes():
    """Updates existing Planning Sheets and Items that are missing a plan code."""
    sheets = frappe.get_all("Planning sheet", filters={"docstatus": ["<", 2]}, fields=["name"])
    count = 0
    for s in sheets:
        try:
            doc = frappe.get_doc("Planning sheet", s.name)
            update_sheet_plan_codes(doc)
            for tf in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
                new_items = doc.get(tf)
                if new_items:
                    for i in new_items:
                        if i.get("plan_name"):
                            frappe.db.sql(
                                "UPDATE `tabPlanning Table` SET plan_name = %s WHERE name = %s",
                                (i.plan_name, i.name),
                            )
                    break
            count += 1
        except Exception:
            pass
    frappe.db.commit()
    return {"status": "success", "updated_count": count}

@frappe.whitelist()
def get_previous_production_date(date):
    prev_date = frappe.db.get_value(
        "Planning sheet",
        {"ordered_date": ["<", date], "docstatus": ["<", 2]},
        "ordered_date",
        order_by="ordered_date desc"
    )
    return prev_date

@frappe.whitelist()
def split_order(item_name, split_qty, target_unit):
    """
    Splits an order: Keeps 'remaining_qty' in original item, creates new item with 'split_qty' in target_unit.
    """
    if not item_name or not split_qty or not target_unit:
        frappe.throw("Missing required parameters: item_name, split_qty, target_unit")

    doc = frappe.get_doc("Planning Table", item_name)
    original_qty = float(doc.qty or 0)
    split_qty_val = float(split_qty)

    if split_qty_val >= original_qty:
        frappe.throw(f"Split quantity ({split_qty_val}) must be less than original quantity ({original_qty})")

    if split_qty_val <= 0:
        frappe.throw("Split quantity must be positive")

    target_unit = normalize_planning_unit_for_select(target_unit)

    # 1. Update Board qty
    remaining_qty = original_qty - split_qty_val
    doc.db_set("qty", remaining_qty)

    parent_name = doc.parent

    max_idx = frappe.db.sql(
        "SELECT MAX(idx) FROM `tabPlanning Table` WHERE parent = %s", (parent_name,)
    )
    new_idx = int(max_idx[0][0] or 0) + 1 if max_idx and max_idx[0][0] else 1

    new_row_doc = frappe.new_doc("Planning Table")
    for field in doc.meta.fields:
        if field.fieldtype not in ("Section Break", "Column Break", "Table") and field.fieldname not in ("name", "idx", "parent", "parentfield", "parenttype"):
            new_row_doc.set(field.fieldname, doc.get(field.fieldname))
    new_row_doc.parent = parent_name
    new_row_doc.parentfield = _get_pt_parentfield()
    new_row_doc.parenttype = "Planning sheet"
    new_row_doc.idx = new_idx
    new_row_doc.qty = flt(split_qty_val)
    new_row_doc.unit = target_unit
    new_row_doc.is_split = 1
    new_row_doc.split_from = doc.name
    new_row_doc.planning_sheet = parent_name
    new_row_doc.source_ps = parent_name
    new_row_doc.source_item = _resolve_planning_table_source_item_link(doc.get("source_item"), doc.name)
    new_row_doc.insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "success",
        "original_item": doc.name,
        "remaining_qty": remaining_qty,
        "new_item": new_row_doc.name,
        "split_qty": split_qty_val,
        "target_unit": target_unit
    }

@frappe.whitelist()
def duplicate_unprocessed_orders_to_plan(old_plan, new_plan, date=None, start_date=None, end_date=None):
    """
    Moves unprocessed Planning Sheets from `old_plan` to `new_plan` by updating custom_plan_name.
    Does NOT create new sheets ΓÇö just updates the plan name on existing ones.
    Only moves sheets that do NOT have BOTH a Production Plan AND a Work Order.
    """
    if start_date and end_date:
        query_start = getdate(start_date)
        query_end = getdate(end_date)
        sheets = frappe.get_all("Planning sheet", filters={
            "custom_plan_name": old_plan,
            "ordered_date": ["between", [query_start, query_end]],
            "docstatus": ["<", 1] # Only move drafts
        })
    elif date:
        target_date = getdate(date)
        sheets = frappe.get_all("Planning sheet", filters={
            "custom_plan_name": old_plan,
            "ordered_date": target_date,
            "docstatus": ["<", 1]
        })
    else:
        return {"status": "error", "message": "Date filter required"}
    
    count = 0
    for sheet in sheets:
        frappe.db.set_value("Planning sheet", sheet.name, "custom_plan_name", new_plan)
        count += 1

    frappe.db.commit()
    return {"status": "success", "moved_count": count}

@frappe.whitelist()
def delete_plan(plan_name, date=None, start_date=None, end_date=None):
    """
    Deletes a plan by moving all its sheets to 'Default'.
    """
    if not plan_name or plan_name == "Default":
        return {"status": "error", "message": "Cannot delete Default plan"}

    if start_date and end_date:
        query_start = getdate(start_date)
        query_end = getdate(end_date)
        sheets = frappe.get_all("Planning sheet", filters={
            "custom_plan_name": plan_name,
            "ordered_date": ["between", [query_start, query_end]],
            "docstatus": ["<", 2]
        })
    elif date:
        target_date = getdate(date)
        sheets = frappe.get_all("Planning sheet", filters={
            "custom_plan_name": plan_name,
            "ordered_date": target_date,
            "docstatus": ["<", 2]
        })
    else:
        return {"status": "error", "message": "Date filter required"}

    count = 0
    for sheet in sheets:
        frappe.db.set_value("Planning sheet", sheet.name, "custom_plan_name", "Default")
        count += 1

    # Remove from persistent plans
    persisted = get_persisted_plans("color_chart")
    persisted = [p for p in persisted if p["name"] != plan_name]
    import json
    frappe.defaults.set_global_default("production_scheduler_color_chart_plans", json.dumps(persisted))

    frappe.db.commit()
    return {"status": "success", "deleted_count": count}

# ΓöÇΓöÇ Beige / buffer colors placed at very end of color sequence ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
BEIGE_COLORS = {
    "BEIGE 1.0","BEIGE 2.0","BEIGE 3.0","BEIGE 4.0","BEIGE 5.0",
    "LIGHT BEIGE","DARK BEIGE","BEIGE MIX",
}

# ΓöÇΓöÇ Very dark colors that should be followed by beige buffers when possible ΓöÇΓöÇ
VERY_DARK_COLORS = {
    "BLACK","BLACK MIX","CHOCOLATE BLACK",
    "CRIMSON RED","RED","DARK MAROON","MAROON 2.0","MAROON 1.0",
    "BROWN 3.0 DARK COFFEE","BROWN 2.0 DARK",
}

# ΓöÇΓöÇ Color lightΓåÆdark order ΓÇö FINAL USER DEFINED SEQUENCE ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
COLOR_ORDER_LIST = [
    # 0. White (Universal Starting Point)
    "BRIGHT WHITE", "SUPER WHITE", "MILKY WHITE", "SUNSHINE WHITE",
    "BLEACH WHITE 1.0", "BLEACH WHITE 2.0", "BLEACH WHITE", "WHITE MIX", "WHITE",
    
    # 1. BABY PINK
    "BABY PINK",

    # 2. MEDICAL BLUE
    "LIGHT MEDICAL BLUE", "MEDICAL BLUE",

    # 3. MEDICAL GREEN
    "MEDICAL GREEN",

    # 4. IVORY
    "BRIGHT IVORY", "IVORY", "OFF WHITE",

    # 5. CREAM
    "CREAM 1.0", "CREAM 2.0", "CREAM 3.0", "CREAM 4.0", "CREAM 5.0", "CREAM",

    # 6. LEMON YELLOW
    "LEMON YELLOW 1.0", "LEMON YELLOW 3.0", "LEMON YELLOW",

    # 7. GOLDEN YELLOW
    "GOLDEN YELLOW 4.0 SPL", "GOLDEN YELLOW 1.0", "GOLDEN YELLOW 2.0", "GOLDEN YELLOW 3.0", "GOLDEN YELLOW",

    # 8. ORANGE
    "BRIGHT ORANGE", "ORANGE 2.0", "DARK ORANGE", "ORANGE",

    # 9. PINK
    "PINK 1.0", "PINK 2.0", "PINK 3.0", "PINK 5.0", "DARK PINK", "PINK 6.0 DARK", "PINK 7.0 DARK", "PINK",

    # 10. RED
    "RED", "CRIMSON RED",

    # 11. LIGHT MAROON
    "LIGHT MAROON", "MAROON 1.0",

    # 12. DARK MAROON
    "DARK MAROON", "MAROON 2.0",

    # 13. PEACOCK BLUE
    "LIGHT PEACOCK BLUE", "PEACOCK BLUE",

    # 14. ROYAL BLUE
    "BLUE 1.0", "BLUE 2.0", "BLUE 4.0", "BLUE 9.0", "BLUE",
    "ROYAL BLUE", "BLUE 6.0 ROYAL BLUE", 
    "BLUE 7.0 DARK BLUE", "BLUE 8.0 DARK ROYAL BLUE",

    # 15. NAVY BLUE
    "NAVY BLUE", "BLUE 11.0 NAVY BLUE", "BLUE 12.0 SPL NAVY BLUE", "BLUE 13.0 INK BLUE",

    # 16. VOILET
    "VIOLET", "VOILET",

    # 17. RELIANCE GREEN
    "GREEN 3.0 RELIANCE GREEN", "RELIANCE GREEN",

    # 18. PARROT GREEN
    "GREEN 1.0 MINT", "GREEN 2.0 TORQUISE GREEN", "PARROT GREEN",

    # 19. SEA GREEN
    "SEA GREEN",

    # 20. ARMY GREEN
    "GREEN 4.0", "GREEN 5.0 GRASS GREEN", "GREEN 6.0", "GREEN 7.0", "GREEN 8.0 APPLE GREEN",
    "GREEN 9.0 BOTTLE GREEN", "GREEN 10.0", "PEACOCK GREEN",
    "GREEN 11.0 DARK GREEN", "GREEN 12.0 OLIVE GREEN", "GREEN 13.0 ARMY GREEN",
    "GREEN",

    # 21. LIGHT GREY
    "LIGHT GREY", "SILVER 1.0", "SILVER 2.0", "GREY 1.0",

    # 22. DARK GREY
    "DARK GREY", "GREY",

    # 23. BROWN
    "CHOCOLATE BROWN", "CHOCOLATE BROWN 2.0", "BROWN 1.0", "BROWN 2.0 DARK", "BROWN 3.0 DARK COFFEE",
    "CHIKOO 1.0", "CHIKOO 2.0", "CHOCOLATE BLACK", "BROWN",

    # 24. BLACK
    "BLACK MIX", "COLOR MIX", "BLACK",

    # 25. DARK BEIGE
    "DARK BEIGE", "BEIGE MIX",

    # 26. LIGHT BEIGE
    "BEIGE 1.0", "BEIGE 2.0", "BEIGE 3.0", "BEIGE 4.0", "BEIGE 5.0", "LIGHT BEIGE", "BEIGE",
]
COLOR_PRIORITY = {c: i for i, c in enumerate(COLOR_ORDER_LIST)}

# ΓöÇΓöÇ Quality run order per unit ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
UNIT_QUALITY_ORDER = {
    "Unit 1": ["PREMIUM","PLATINUM","SUPER PLATINUM","GOLD","SILVER"],
    "Unit 2": ["GOLD","SILVER","BRONZE","CLASSIC","SUPER CLASSIC","LIFE STYLE",
               "ECO SPECIAL","ECO GREEN","SUPER ECO","ULTRA","DELUXE"],
    "Unit 3": ["PREMIUM","PLATINUM","SUPER PLATINUM","GOLD","SILVER","BRONZE"],
    "Unit 4": ["PREMIUM","GOLD","SILVER","BRONZE","CLASSIC","CRT"],
}

@frappe.whitelist()
def get_board_seeds(target_date, plan_name=None, exclude_items=None):
    """API to fetch seeds for all 4 units for the frontend."""
    seeds = {}
    for u in ["Unit 1", "Unit 2", "Unit 3", "Unit 4"]:
        s = get_last_unit_order(u, target_date, plan_name, exclude_items)
        if s: seeds[u] = s
    return seeds

@frappe.whitelist()
def get_last_unit_order(unit, date=None, plan_name=None, exclude_items=None):
    """
    Returns the last pushed order on the Production Board for a given unit.
    Visual board sequence (idx DESC) is the absolute priority.
    exclude_items: list of names (Planning Sheet Item) to ignore.
    """
    from frappe.utils import getdate
    target_date = getdate(date) if date else getdate(frappe.utils.today())
    clean_unit = unit.strip().replace(" ", "").upper()
    
    exclude_sql = ""
    if exclude_items:
        if isinstance(exclude_items, str):
            import json
            exclude_items = json.loads(exclude_items)
        if exclude_items:
            # Format for SQL IN clause. Psuedo-safe because these are system DocIDs (PSI-XXXXX)
            # But we'll use a safer approach.
            names = ", ".join([f"'{n}'" for n in exclude_items if n])
            if names:
                exclude_sql = f"AND i.name NOT IN ({names})"

    clean_white_sql = ", ".join([f"'{c.upper().replace(' ', '')}'" for c in WHITE_COLORS])
    
    # --- Combined Search Part 1: Items on Target Date (Color or White) ---
    rows = frappe.db.sql(f"""
        SELECT 
            i.color, i.custom_quality as quality, i.gsm, i.item_name, i.idx, 
            p.name as sheet, p.modified, p.docstatus
        FROM `tabPlanning Table` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        WHERE REPLACE(UPPER(i.unit), ' ', '') = %s
          AND p.docstatus < 2
          AND (i.color IS NOT NULL AND i.color != '' AND i.color != '0' AND i.color != '0.0')
          AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) = DATE(%s)
          {exclude_sql}
        ORDER BY 
          -- Prioritize color items over white if they share the same date
          (CASE WHEN REPLACE(UPPER(i.color), ' ', '') NOT IN ({clean_white_sql}) THEN 0 ELSE 1 END) ASC,
          p.docstatus DESC,
          i.idx DESC,
          p.modified DESC
        LIMIT 1
    """, (clean_unit, target_date), as_dict=True)

    if not rows:
        return None

    r = rows[0]
    return {
        "color": (r.color or "").upper().strip(),
        "quality": (r.quality or "").upper().strip(),
        "gsm": r.gsm,
        "is_white": (r.color or "").upper().strip() in WHITE_COLORS,
        "date": target_date
    }

@frappe.whitelist()
def get_smart_push_sequence(item_names, target_date=None, seed_quality=None, seed_color=None, plan_name=None):
    """
    Returns items in smart push order:
    1. Perfect Match: Same color AND same quality as board seed
    2. Color Match: Same color as board seed
    3. Hierarchy Continuation: Next colors in the user light-dark sequence (Wrap-around)
    4. Quality Priority: Unit-specific quality order
    5. GSM: High to Low
    """
    import json
    if isinstance(item_names, str):
        item_names = json.loads(item_names)
    
    items = frappe.get_all("Planning Table", 
        filters={"name": ["in", item_names]},
        fields=["name", "item_code", "item_name", "qty", "unit", "color", "custom_quality", "gsm", "parent", "planned_date"]
    )
    
    if not items:
        return {"sequence": [], "seeds": {}}

    target_date = getdate(target_date) if target_date else getdate(frappe.utils.today())
    
    # Always fetch seeds for all 4 units for UI visibility (Board End display)
    unit_seeds = get_board_seeds(target_date, plan_name, item_names)

    # Enrichment bucket for UI
    parent_cache = {}
    
    # Group by unit for specialized sorting
    result_sequence = []
    for u in ["Unit 1", "Unit 2", "Unit 3", "Unit 4", "UNASSIGNED"]:
        unit_items = [it for it in items if _normalize_unit(it.get("unit")) == u]
        if not unit_items: continue
        
        seed = unit_seeds.get(u)
        s_col = (seed.get("color") if seed else seed_color or "").upper().strip()
        s_qual = (seed.get("quality") if seed else seed_quality or "").upper().strip()

        # Separate into Perfect Match, Color Match, and Others
        perfect = []
        same_col = []
        remaining = []
        
        for it in unit_items:
            c = (it.get("color") or "").upper().strip()
            q = (it.get("custom_quality") or "").upper().strip()
            if c == s_col and q == s_qual: perfect.append(it)
            elif c == s_col: same_col.append(it)
            else: remaining.append(it)

        def color_sort_key_fn(it):
            col = (it.get("color") or "").upper().strip()
            qual = (it.get("custom_quality") or "").upper().strip()
            
            # Priority 1: COLOR lightΓåÆdark order with WRAP-AROUND
            c_idx = COLOR_PRIORITY.get(col, 999)
            s_idx = COLOR_PRIORITY.get(s_col, -1)
            
            if s_idx != -1 and c_idx != 999:
                # Continuous Flow: index relative to the seed
                total_colors = len(COLOR_ORDER_LIST)
                color_score = (c_idx - s_idx + total_colors) % total_colors
            else:
                # Fallback to absolute rank if seed or color not found in hierarchy
                color_score = c_idx
            
            # Priority 2: Quality order
            q_order = UNIT_QUALITY_ORDER.get(u, [])
            q_idx = q_order.index(qual) if qual in q_order else 999
            
            # Priority 3: GSM (High to Low -> negative)
            gsm_val = -float(it.get("gsm") or 0)
            
            return (color_score, q_idx, gsm_val)

        # Final Sort within buckets
        perfect.sort(key=color_sort_key_fn)
        same_col.sort(key=color_sort_key_fn)
        remaining.sort(key=color_sort_key_fn)
        
        # Merge buckets for this unit
        unit_sorted = perfect + same_col + remaining
        
        # Enrich items for the frontend as we add them
        for it in unit_sorted:
            if it.parent not in parent_cache:
                parent_cache[it.parent] = frappe.db.get_value("Planning sheet", it.parent, ["customer","party_code"], as_dict=1) or {}
            p = parent_cache[it.parent]
            
            it["customer"] = p.get("customer","")
            it["partyCode"] = p.get("party_code","")
            it["pbPlanName"] = ""
            it["quality"] = (it.get("custom_quality") or "").upper().strip()
            it["colorKey"] = (it.get("color") or "").upper().strip()
            it["unit"] = _normalize_unit(it.get("unit"))
            it["unitKey"] = it["unit"]
            it["gsmVal"] = float(it.get("gsm") or 0)
            it["plannedDate"] = str(it.get("planned_date") or "")
            it["description"] = it.get("item_name") or ""
            
            result_sequence.append(it)

    # Safety: add sequence_no
    for i, it in enumerate(result_sequence):
        it["sequence_no"] = i + 1
        it["phase"] = "color" if it["colorKey"] not in WHITE_COLORS else "white"
        it["is_seed_bridge"] = False # Default

    return {
        "sequence": result_sequence,
        "seeds": unit_seeds
    }

@frappe.whitelist()
def move_items_to_plan(item_names, target_plan, date=None, start_date=None, end_date=None, days_in_view=1, force_move=0):
    """
    Copies specific Planning Sheet Items to a target Color Chart plan.
    - days_in_view: scale capacity limit (e.g. 28 for monthly February, 7 for weekly).
    - force_move=1: skip capacity check entirely (used in monthly/weekly views).
    - Items linked to cancelled Sales Orders are silently skipped with a warning.
    """
    import json
    if isinstance(item_names, str):
        item_names = json.loads(item_names)
    days_in_view = int(days_in_view) if days_in_view else 1
    force_move = int(force_move) if force_move else 0

    if not item_names or not target_plan:
        return {"status": "error", "message": "Missing item names or target plan"}

    moved = 0
    skipped = []
    errors = []
    new_sheet_cache = {}  # (party_code, effective_date) -> sheet_name

    UNIT_LIMITS = {"Unit 1": 4.4, "Unit 2": 12.0, "Unit 3": 9.0, "Unit 4": 5.5}

    # Clear doctype meta cache so custom fields (custom_plan_name) are recognized
    frappe.clear_cache(doctype="Planning sheet")

    for name in item_names:
        try:
            item_doc = frappe.get_doc("Planning Table", name)
            parent_sheet = frappe.get_doc("Planning sheet", item_doc.parent)

            target_unit = item_doc.unit or "UNASSIGNED"
            effective_date = parent_sheet.get("custom_planned_date") or parent_sheet.ordered_date
            party_code = parent_sheet.party_code or ""

            # --- Guard: skip items on cancelled Sales Orders ---
            if parent_sheet.sales_order:
                so_status = frappe.db.get_value("Sales Order", parent_sheet.sales_order, "docstatus")
                if so_status == 2:  # Cancelled
                    skipped.append(f"{name}: linked Sales Order {parent_sheet.sales_order} is cancelled ΓÇö skipped")
                    continue

            # --- Find or create a Planning Sheet in the target plan ---
            cache_key = (party_code, str(effective_date))
            if cache_key in new_sheet_cache:
                target_sheet_name = new_sheet_cache[cache_key]
            else:
                filters = {
                    "custom_plan_name": target_plan,
                    "docstatus": ["<", 1]
                }
                # Prefer matching by Sales Order to keep items together
                if parent_sheet.sales_order:
                    filters["sales_order"] = parent_sheet.sales_order
                elif party_code:
                    filters["party_code"] = party_code

                existing = frappe.get_all("Planning sheet", filters=filters, fields=["name"], limit=1)

                if existing:
                    target_sheet_name = existing[0].name
                else:
                    so_existing = _find_existing_sheet_for_sales_order(parent_sheet.sales_order) if parent_sheet.sales_order else None
                    if so_existing:
                        target_sheet_name = so_existing["name"]
                    else:
                        new_sheet = frappe.new_doc("Planning sheet")
                        new_sheet.custom_plan_name = target_plan
                        new_sheet.ordered_date = effective_date
                        new_sheet.party_code = party_code
                        new_sheet.customer = _resolve_customer_link(parent_sheet.customer, parent_sheet.party_code)
                        new_sheet.sales_order = parent_sheet.sales_order or ""
                        new_sheet.insert(ignore_permissions=True)
                        target_sheet_name = new_sheet.name
                    # Force custom_plan_name via raw SQL to ensure persistence
                    if frappe.db.has_column("Planning sheet", "custom_plan_name"):
                        frappe.db.sql(
                            "UPDATE `tabPlanning sheet` SET custom_plan_name = %s WHERE name = %s",
                            (target_plan, target_sheet_name)
                        )
                        frappe.logger().info(f"[MoveItems] Set custom_plan_name='{target_plan}' on sheet {target_sheet_name}")
                    else:
                        frappe.logger().error("[MoveItems] custom_plan_name column DOES NOT EXIST!")

                new_sheet_cache[cache_key] = target_sheet_name

            # --- Capacity check (scaled by days_in_view, skipped if force_move) ---
            if not force_move:
                daily_limit = UNIT_LIMITS.get(target_unit, 9999)
                scaled_limit = daily_limit * days_in_view
                target_items = frappe.get_all(
                    "Planning Table",
                    filters={"parent": target_sheet_name, "unit": target_unit},
                    fields=["qty"]
                )
                current_kg = sum(float(i.qty or 0) for i in target_items)
                item_kg = float(item_doc.qty or 0)
                if (current_kg + item_kg) / 1000 > scaled_limit:
                    errors.append(
                        f"{item_doc.item_name}: Would exceed {target_unit} capacity "
                        f"({(current_kg/1000):.2f}+{(item_kg/1000):.2f} > {scaled_limit:.1f}T)"
                    )
                    continue

            # --- RE-PARENT the item to target sheet via raw SQL ---
            # (frappe.db.set_value fails on children of submitted docs)
            frappe.db.sql("""
                UPDATE `tabPlanning Table`
                SET parent = %s, parenttype = 'Planning sheet', parentfield = %s
                WHERE name = %s
            """, (target_sheet_name, _get_pt_parentfield(), name))
            moved += 1

        except Exception as e:
            errors.append(f"{name}: {str(e)}")

    frappe.db.commit()
    result = {"status": "success", "moved": moved}
    if skipped:
        result["skipped"] = skipped
    if errors:
        result["errors"] = errors
    return result


def get_orders_for_date(date):
    """
    Fetch all Planning Sheet Items for a specific date that are NOT Cancelled/Completed (optional filter).
    Returns basic info needed for the Pull Dialog.
    """
    if not date:
        return []

    # Get parent sheets for this date (if structure is Parent Date -> Child Item)
    # Actually, your structure seems to be Planning Sheet (Header) has Date? 
    # Or Items have Date?
    # Based on `update_items_bulk`, items update `ordered_date` on Parent. 
    # So we query Planning Sheet by `ordered_date` and get items.
    
    # Wait, `get_color_chart_data` uses `ordered_date` on `Planning sheet`.
    # Let's check `get_color_chart_data` logic again to be consistent.
    # It joins Planning Sheet and Planning Sheet Item.
    
    sql = """
        SELECT 
            i.name, i.item_code, i.item_name, i.qty, i.unit, i.color, 
            i.gsm, i.custom_quality as quality,
            p.name as planning_sheet, p.party_code, p.customer
        FROM
            `tabPlanning Table` i
        LEFT JOIN
            `tabPlanning sheet` p ON i.parent = p.name
        WHERE
            p.ordered_date = %s
            AND p.docstatus < 2
            AND i.docstatus < 2
        ORDER BY
            i.unit, i.custom_quality
    """
    data = frappe.db.sql(sql, (date,), as_dict=True)
    return data

@frappe.whitelist()
def move_orders_to_date(item_names, target_date, target_unit=None, plan_name=None, pb_plan_name=None, force_move=0):
    """
    Moves list of Planning Sheet Items to a new Date.
    Supports item-level granularity by re-parenting items if necessary.
    Optionally updates the Unit of the moved items.
    """
    import json
    if isinstance(item_names, str):
        item_names = json.loads(item_names)
        
    if not item_names:
        return {"status": "failed", "message": "No items selected"}

    target_date = getdate(target_date)
    if target_unit:
        target_unit = normalize_planning_unit_for_select(target_unit)
    
    # --- CAPACITY VALIDATION & SPLITTING PREPARATION ---
    # 1. Calculate weight to add per unit and prepare docs
    weights_to_add = {} # unit -> tons
    docs_to_move = [] 

    def _get_item_wo_produced_qty(item_doc):
        """Return produced qty for this specific Planning Table row.

        We must scope by planning row / explicit SPR link, not by PP+item aggregate,
        otherwise same-order rows from other dates wrongly block movement.
        """
        try:
            row = frappe.db.sql(
                """
                SELECT SUM(IFNULL(spri.net_weight, 0)) AS produced_qty
                FROM `tabShaft Production Run Item` spri
                INNER JOIN `tabShaft Production Run` spr ON spr.name = spri.parent
                WHERE spr.docstatus < 2
                  AND IFNULL(spri.planning_sheet_item, '') = %s
                """,
                (item_doc.name,),
                as_dict=True,
            )
            produced_qty = flt((row[0] or {}).get("produced_qty") if row else 0)
            # Do not fallback to doc.spr_name-level totals here.
            # A stale/borrowed spr_name can incorrectly block moves for repeated same-order rows.
            return produced_qty
        except Exception:
            return 0.0

    for entry in item_names:
        # Support both simple list of names and list of {itemName, qty}
        name = entry.get("itemName") if isinstance(entry, dict) else entry
        req_qty = flt(entry.get("qty")) if isinstance(entry, dict) else None
        
        try:
            doc = frappe.get_doc("Planning Table", name)

            produced_qty = _get_item_wo_produced_qty(doc)
            available_qty = max(flt(doc.qty) - produced_qty, 0)

            # If pull qty not explicitly given, move only available (remaining) qty.
            if req_qty is None:
                req_qty = available_qty

            if req_qty <= 0:
                continue

            if req_qty > available_qty:
                frappe.throw(
                    _(
                        "Item {0}: Requested move qty {1} exceeds available qty {2}. "
                        "Produced/WO qty {3} is already consumed."
                    ).format(doc.item_name or doc.name, flt(req_qty), flt(available_qty), flt(produced_qty))
                )
            
            # If partial quantity requested, perform split
            if req_qty and 0 < req_qty < flt(doc.qty):
                parent_name = doc.parent
                max_idx = frappe.db.sql(
                    "SELECT MAX(idx) FROM `tabPlanning Table` WHERE parent = %s", (parent_name,)
                )
                new_idx = int(max_idx[0][0] or 0) + 1 if max_idx and max_idx[0][0] else 1

                new_row_doc = frappe.new_doc("Planning Table")
                for field in doc.meta.fields:
                    if field.fieldtype not in ("Section Break", "Column Break", "Table") and field.fieldname not in ("name", "idx", "parent", "parentfield", "parenttype"):
                        new_row_doc.set(field.fieldname, doc.get(field.fieldname))
                new_row_doc.parent = parent_name
                new_row_doc.parentfield = _get_pt_parentfield()
                new_row_doc.parenttype = "Planning sheet"
                new_row_doc.idx = new_idx
                new_row_doc.qty = flt(req_qty)
                new_row_doc.is_split = 1
                new_row_doc.split_from = doc.name
                if frappe.db.has_column("Planning Table", "spr_name"):
                    new_row_doc.spr_name = ""
                new_row_doc.source_item = _resolve_planning_table_source_item_link(
                    new_row_doc.get("source_item"), doc.name
                )
                new_row_doc.insert(ignore_permissions=True)

                # Reduce original item quantity
                new_qty = flt(doc.qty) - req_qty
                frappe.db.sql(
                    "UPDATE `tabPlanning Table` SET qty = %s, is_split = 1 WHERE name = %s",
                    (new_qty, doc.name),
                )

                move_doc = new_row_doc
            else:
                # Move the entire original item
                move_doc = doc

            docs_to_move.append(move_doc)
            
            # For capacity check
            final_unit = target_unit if target_unit else (move_doc.unit or "")
            if final_unit:
                wt_tons = flt(move_doc.qty) / 1000.0
                weights_to_add[final_unit] = weights_to_add.get(final_unit, 0.0) + wt_tons
        except frappe.DoesNotExistError:
            continue
            
    # 2. Check Limits (skip if force_move ΓÇö e.g. monthly/weekly aggregate view)
    if not force_move:
        for unit, added_weight in weights_to_add.items():
            if unit in HARD_LIMITS:
                current_load = get_unit_load(target_date, unit)
                limit = HARD_LIMITS[unit]
                
                if current_load + added_weight > limit:
                    frappe.throw(
                        f"Capacity Exceeded! Unit {unit} allows max {limit}T. Current: {current_load:.2f}T. Adding: {added_weight:.2f}T. New Total: {current_load + added_weight:.2f}T"
                    )

    count = 0
    
    # 1. Group items by Current Parent
    items_by_parent = {}
    
    for doc in docs_to_move:
        p_name = str(doc.parent)
        if p_name not in items_by_parent:
            items_by_parent[p_name] = []
        items_by_parent[p_name].append(doc)

    # 2. Process each Parent Group
    for parent_name, items in items_by_parent.items():
        parent_doc = frappe.get_doc("Planning sheet", parent_name)
        moving_docs = items  # items is already a list
        
        # Determine Target Sheet
        # Fix: Stay in the SAME sheet unless moving to a DIFFERENT plan
        target_sheet_name = parent_name
        
        # Only look for a different sheet if a plan change is actually requested
        is_plan_change = (plan_name and plan_name != "Default" and plan_name != parent_doc.get("custom_plan_name")) or \
                         (pb_plan_name and pb_plan_name != "Default" and pb_plan_name != parent_doc.get("custom_pb_plan_name"))
        
        if is_plan_change:
            find_filters = {
                "party_code": parent_doc.party_code,
                "sales_order": parent_doc.sales_order,
                "docstatus": ["<", 2]
            }
            
            # Target Plan checks
            if plan_name and plan_name != "Default":
                find_filters["custom_plan_name"] = plan_name
            elif plan_name == "Default":
                find_filters["custom_plan_name"] = ["in", ["", None, "Default"]]
            
            if pb_plan_name and pb_plan_name != "Default":
                find_filters["custom_pb_plan_name"] = pb_plan_name
            elif pb_plan_name == "Default":
                find_filters["custom_pb_plan_name"] = ["in", ["", None, "Default"]]

            found_name = frappe.db.get_value("Planning sheet", find_filters, "name")
            if found_name:
                target_sheet_name = found_name
            else:
                so_existing = _find_existing_sheet_for_sales_order(parent_doc.sales_order) if parent_doc.sales_order else None
                if so_existing:
                    target_sheet_name = so_existing["name"]
                else:
                    # Create NEW sheet only if SO has no sheet at all
                    target_sheet = frappe.new_doc("Planning sheet")
                    target_sheet.ordered_date = target_date
                    if frappe.db.has_column("Planning sheet", "custom_planned_date"):
                        target_sheet.custom_planned_date = target_date
                    target_sheet.party_code = parent_doc.party_code
                    target_sheet.customer = _resolve_customer_link(parent_doc.customer, parent_doc.party_code)
                    target_sheet.sales_order = parent_doc.sales_order
                    if plan_name and plan_name != "Default":
                        target_sheet.custom_plan_name = plan_name
                    if pb_plan_name and pb_plan_name != "Default":
                        target_sheet.custom_pb_plan_name = pb_plan_name
                    target_sheet.save(ignore_permissions=True)
                    target_sheet_name = target_sheet.name

        target_sheet = frappe.get_doc("Planning sheet", target_sheet_name)
        
        # IMPORTANT:
        # Do not auto-write sheet-level custom_planned_date when reusing an existing sheet.
        # Pull/move is item-level; forcing parent header date can make unrelated items
        # appear on a single date (for example 03-01-2026) unexpectedly.
        
        # Get starting idx for target
        target_sheet.reload()
        current_max_idx = 0
        if target_sheet.get("items"):
            current_max_idx = int(max([int(d.idx or 0) for d in target_sheet.items] or [0]))
        
        # Move Every Item in the group
        for i, item_doc in enumerate(moving_docs):
            new_idx = int(current_max_idx) + int(i) + 1
            new_unit = target_unit if target_unit else item_doc.unit

            # QUALITY ENFORCEMENT
            if new_unit and not is_quality_allowed(new_unit, item_doc.custom_quality):
                frappe.throw(_("Quality <b>{}</b> is not allowed in <b>{}</b> (Item: {}).").format(
                    item_doc.custom_quality or "Generic", new_unit, item_doc.item_name
                ))

            # Keep explicit Unassigned/Mixed moves in pool.
            # Auto-heal only when unit is genuinely missing.
            if not new_unit:
                qual = item_doc.custom_quality or ""
                new_unit = get_preferred_unit(qual)
            
            # Use SQL for direct re-parenting (Robust for rescue)
            # Make sure we also update planned_date so pulled items don't vanish from the board
            pt_pf = _get_pt_parentfield()
            set_date = f", planned_date = '{target_date}'" if frappe.db.has_column("Planning Table", "planned_date") else ""
            frappe.db.sql(f"""
                UPDATE `tabPlanning Table`
                SET parent = %s, idx = %s, unit = %s, parenttype='Planning sheet', parentfield=%s{set_date}
                WHERE name = %s
            """, (target_sheet.name, new_idx, new_unit, pt_pf, item_doc.name))

            _sync_legacy_planning_sheet_item_unit(item_doc.get("source_item"), new_unit)

            count = int(count) + 1
        
        frappe.db.commit() # Save SQL updates
        
        # 3. Handle Parent Cleanup
        if target_sheet.name != parent_doc.name:
            parent_doc.reload()
            if not parent_doc.get("items"):
                # Source is empty -> DELETE (cancel first if submitted)
                try:
                    src_ds = int(parent_doc.docstatus or 0)
                    if src_ds == 1:
                        frappe.db.sql("UPDATE `tabPlanning sheet` SET docstatus = 2 WHERE name = %s", parent_doc.name)
                    frappe.delete_doc("Planning sheet", parent_doc.name, force=1, ignore_permissions=True)
                except Exception as e:
                    # If it's linked to a Production Plan, Frappe prevents deletion. 
                    # We catch it so the move doesn't crash since the items were already moved via SQL.
                    frappe.logger().error(f"Could not delete empty planning sheet {parent_doc.name}: {e}")
        
    frappe.db.commit()


@frappe.whitelist()
def rescue_orphaned_items(target_date=None, colour=None, party_code=None):
    """Find Planning Sheet Items whose parent sheets are deleted/missing,
       and re-home them to a valid sheet on target_date (default: today)."""
    target_date = getdate(target_date or frappe.utils.today())
    
    # 1. Find orphaned items: parent sheet does not exist
    conds = []
    params = {"target": target_date}
    if colour:
        conds.append("AND item.colour LIKE %(colour)s")
        params["colour"] = f"%{colour}%"
    if party_code:
        conds.append("AND item.party_code LIKE %(party_code)s")
        params["party_code"] = f"%{party_code}%"
    
    extra = " ".join(conds)
    orphans = frappe.db.sql(f"""
        SELECT item.name, item.parent, item.unit, item.colour, item.qty,
               item.party_code, item.customer, item.custom_quality, item.item_name,
               item.sales_order
        FROM `tabPlanning Table` item
        LEFT JOIN `tabPlanning sheet` sheet ON item.parent = sheet.name
        WHERE sheet.name IS NULL
        {extra}
    """, params, as_dict=True)
    
    if not orphans:
        return {"status": "success", "count": 0, "message": "No orphaned items found"}
    
    # 2. Group by party_code and re-home
    by_party = {}
    for o in orphans:
        key = o.party_code or "UNKNOWN"
        if key not in by_party:
            by_party[key] = []
        by_party[key].append(o)
    
    rescued = 0
    for party, items in by_party.items():
        # Find or create a draft sheet for this party on target_date
        existing = frappe.db.get_value("Planning sheet", {
            "party_code": party,
            "ordered_date": target_date,
            "docstatus": ["<", 2]
        }, "name")
        
        if existing:
            sheet_name = existing
        else:
            first = items[0]
            so_existing = _find_existing_sheet_for_sales_order(first.get("sales_order")) if first.get("sales_order") else None
            if so_existing:
                sheet_name = so_existing["name"]
            else:
                new_sheet = frappe.new_doc("Planning sheet")
                new_sheet.ordered_date = target_date
                if frappe.db.has_column("Planning sheet", "custom_planned_date"):
                    new_sheet.custom_planned_date = target_date
                new_sheet.party_code = party
                new_sheet.customer = _resolve_customer_link(first.get("customer"), first.get("party_code") or party)
                new_sheet.sales_order = first.get("sales_order") or ""
                new_sheet.save(ignore_permissions=True)
                sheet_name = new_sheet.name
        
        # Reparent all orphaned items to this sheet
        for item in items:
            frappe.db.sql("""
                UPDATE `tabPlanning Table`
                SET parent = %s, parenttype='Planning sheet', parentfield=%s
                WHERE name = %s
            """, (sheet_name, _get_pt_parentfield(), item.name))
            rescued += 1
    
    frappe.db.commit()
    return {"status": "success", "count": rescued, "message": f"Rescued {rescued} orphaned items to {target_date}"}


@frappe.whitelist()
def fix_planning_table_parentfield():
    """One-time fix: update all Planning Table rows that have the wrong parentfield."""
    correct_pf = _get_pt_parentfield()
    updated = frappe.db.sql(
        "UPDATE `tabPlanning Table` SET parentfield = %s WHERE parentfield != %s AND parenttype = 'Planning sheet'",
        (correct_pf, correct_pf),
    )
    count = frappe.db.sql(
        "SELECT ROW_COUNT() as cnt"
    )[0][0]
    frappe.db.commit()
    return {"status": "success", "fixed": count, "parentfield": correct_pf}


@frappe.whitelist()
def get_items_by_sheet(sheet_name):
    """
    Fetches all items for a given Planning Sheet.
    Used for Admin Rescue to recover items.
    """
    if not sheet_name:
        return []
        
    sql = """
        SELECT name, item_name, qty, unit, docstatus, parent, idx
        FROM `tabPlanning Table`
        WHERE parent = %s
        ORDER BY idx ASC
    """
    return frappe.db.sql(sql, (sheet_name,), as_dict=True)


# --------------------------------------------------------------------------------
# Confirmed Order Workflow & Automation
# --------------------------------------------------------------------------------

@frappe.whitelist()
def get_unscheduled_planning_sheets():
    """
    Fetches Planning Sheets that are 'Confirmed' (docstatus=0 or 1) but have NO ordered_date.
    These display in the 'Confirmed Order' view.
    """
    sql = """
        SELECT 
            p.name, p.customer, COALESCE(c.customer_name, p.customer) as customer_name,
            p.party_code, p.docstatus, p.ordered_date,
            SUM(i.qty) as total_qty
        FROM `tabPlanning sheet` p
        LEFT JOIN `tabPlanning Table` i ON i.parent = p.name
        LEFT JOIN `tabCustomer` c ON p.customer = c.name
        WHERE 
            (p.ordered_date IS NULL OR p.ordered_date = '')
            AND p.docstatus < 2
        GROUP BY p.name
    """
    sheets = frappe.db.sql(sql, as_dict=True)
    
    return sheets

def _get_confirmed_orders_kanban_impl(order_date=None, delivery_date=None, party_code=None, start_date=None, end_date=None):
    """
    Fetches Planning Sheet Items where the linked Sales Order is 'Confirmed'.
    Supports date, start_date/end_date range, delivery_date, and party_code filters.
    """
    # Effective date for Confirmed Orders grouping:
    # Prefer item-level `planned_date` so the queue date matches what users see on the Board.
    # Fallback to sheet-level `custom_planned_date`, then `ordered_date`.
    if frappe.db.has_column("Planning Table", "planned_date"):
        if frappe.db.has_column("Planning sheet", "custom_planned_date"):
            # Some sites store dates as empty string '' instead of NULL.
            # NULLIF(...,'') lets COALESCE correctly fall back.
            eff = "COALESCE(NULLIF(i.planned_date, ''), NULLIF(p.custom_planned_date, ''), NULLIF(p.ordered_date, ''))"
        else:
            eff = "COALESCE(NULLIF(i.planned_date, ''), NULLIF(p.ordered_date, ''))"
    else:
        eff = _effective_date_expr("p")
    conditions = ["p.docstatus < 2"]
    values = []

    if frappe.db.has_column("Sales Order", "custom_production_status"):
        so_confirmed_sql = "so.custom_production_status = 'Confirmed'"
    else:
        frappe.log_error(
            "Sales Order missing custom_production_status; confirmed orders list cannot filter. Add field or restore column.",
            "get_confirmed_orders_kanban",
        )
        return []

    conditions.append(so_confirmed_sql)

    # Date range support (weekly/monthly)
    if start_date and end_date:
        conditions.append(f"{eff} BETWEEN %s AND %s")
        values.extend([start_date, end_date])
    elif order_date:
        conditions.append(f"{eff} = %s")
        values.append(order_date)

    # Filter by Delivery Date (DOD)
    if delivery_date and frappe.db.has_column("Planning sheet", "dod"):
        conditions.append("p.dod = %s")
        values.append(delivery_date)

    if party_code:
        conditions.append("(p.party_code LIKE %s OR p.customer LIKE %s)")
        values.extend([f"%{party_code}%", f"%{party_code}%"])

    where_clause = " AND ".join(conditions)

    so_status_sel = "so.delivery_status" if frappe.db.has_column("Sales Order", "delivery_status") else "NULL"
    so_cps_sel = "so.custom_production_status" if frappe.db.has_column("Sales Order", "custom_production_status") else "NULL"

    qual_expr = "i.custom_quality" if frappe.db.has_column("Planning Table", "custom_quality") else "NULL"
    width_expr = "i.width_inch" if frappe.db.has_column("Planning Table", "width_inch") else "0"
    dod_expr = "p.dod" if frappe.db.has_column("Planning sheet", "dod") else "NULL"

    sql = f"""
        SELECT 
            i.name, i.item_code, i.item_name, i.qty, i.unit, i.color,
            i.gsm, {qual_expr} as quality, {width_expr} as width_inch, i.idx,
            p.name as planning_sheet, p.party_code, p.customer,
            COALESCE(c.customer_name, p.customer) as customer_name,
            {dod_expr} as dod, p.planning_status, p.creation,
            so.transaction_date as so_date, {so_cps_sel} as custom_production_status, {so_status_sel} as delivery_status,
            {eff} as effective_date
        FROM
            `tabPlanning Table` i
        JOIN
            `tabPlanning sheet` p ON i.parent = p.name
        LEFT JOIN
            `tabCustomer` c ON p.customer = c.name
        LEFT JOIN
            `tabSales Order` so ON p.sales_order = so.name
        WHERE
            {where_clause}
        ORDER BY
            {eff} ASC, p.creation DESC, i.idx ASC
    """

    items = frappe.db.sql(sql, tuple(values), as_dict=True)

    data = []
    for item in items:
        data.append({
            "name": "{}-{}".format(item.planning_sheet, item.idx),
            "itemName": item.name,
            "planningSheet": item.planning_sheet,
            "customer": item.customer,
            "partyCode": item.party_code,
            "planningStatus": item.planning_status or "Draft",
            "color": (item.color or "").upper().strip(),
            "quality": item.quality or "",
            "gsm": item.gsm or "",
            "qty": flt(item.qty),
            "width": flt(item.width_inch or 0),
            "unit": item.unit or "",
            "dod": str(item.dod) if item.dod else "",
            "order_date": str(item.effective_date),
            "delivery_status": item.delivery_status or "Not Delivered",
        })

    return _deduplicate_items(data)


@frappe.whitelist()
def get_confirmed_orders_kanban(order_date=None, delivery_date=None, party_code=None, start_date=None, end_date=None):
    """Safe wrapper so Confirmed Order page never 502s on schema drift."""
    try:
        return _get_confirmed_orders_kanban_impl(
            order_date=order_date,
            delivery_date=delivery_date,
            party_code=party_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_confirmed_orders_kanban_error")
        return []



def create_planning_sheet_from_so(doc):
    """
    AUTO-CREATE PLANNING SHEET (QUALITY + GSM LOGIC)
    """
    try:
        existing_sheet = _find_existing_sheet_for_sales_order(doc.name)
        if existing_sheet:
            return
            
        # --- GET ACTIVE UNLOCKED PLANS ---
        try:
            active_plans = get_active_plans()
            cc_plan = active_plans.get("color_chart", "Default")
            pb_plan = active_plans.get("production_board", "")
        except Exception:
            cc_plan = "Default"
            pb_plan = ""

        # --- QUALITIES PER UNIT ---
        UNIT_1_MAP = ["PREMIUM", "PLATINUM", "SUPER PLATINUM", "GOLD", "SILVER"]
        UNIT_2_MAP = ["GOLD", "SILVER", "BRONZE", "CLASSIC", "SUPER CLASSIC", "LIFE STYLE",
                      "ECO SPECIAL", "ECO GREEN", "SUPER ECO", "ULTRA", "DELUXE"]
        UNIT_3_MAP = ["PREMIUM", "PLATINUM", "SUPER PLATINUM", "GOLD", "SILVER", "BRONZE"]
        UNIT_4_MAP = ["PREMIUM", "GOLD", "SILVER", "BRONZE", "CLASSIC", "CRT"]

        ps = frappe.new_doc("Planning sheet")
        ps.sales_order = doc.name
        ps.customer = _resolve_customer_link(doc.customer, doc.get("party_code"))
        ps.party_code = doc.get("party_code") or doc.customer
        ps.ordered_date = doc.transaction_date 
        ps.custom_planned_date = doc.delivery_date
        ps.dod = doc.delivery_date
        ps.planning_status = "Draft"
        ps.custom_plan_name = _get_contextual_plan_name(cc_plan, doc.transaction_date)
        ps.custom_pb_plan_name = pb_plan

        _populate_planning_sheet_items(ps, doc)
        update_sheet_plan_codes(ps, include_legacy=True)
        if not ps.get("quality"):
            ps.quality = "Standard"
        ps.flags.ignore_permissions = True
        ps.insert()
        frappe.db.commit()
        _link_board_planned_rows_to_legacy_items(ps.name)
        _sync_lamination_fabric_planning_rows(ps.name)
        final_doc = frappe.get_doc("Planning sheet", ps.name)
        update_sheet_plan_codes(final_doc, include_legacy=True)
        frappe.msgprint(f"Γ£à Planning Sheet <b>{ps.name}</b> Created!")

    except Exception as e:
        frappe.log_error("Planning Sheet Creation Failed: " + str(e))
        frappe.msgprint("ΓÜá∩╕Å Planning Sheet failed. Check 'Error Log' for details.")

@frappe.whitelist()
def create_production_plan_from_sheet(sheet_name):
    """
    Creates a Production Plan from a Planning Sheet.
    If the sheet already has a linked Production Plan (header or row), returns it — no duplicate PP.
    """
    if not sheet_name:
        return
    sheet = frappe.get_doc("Planning sheet", sheet_name)

    existing = _resolve_existing_production_plan_for_planning_sheet(sheet_name)
    if existing:
        return existing

    pp = frappe.new_doc("Production Plan")
    pp.company = frappe.defaults.get_user_default("Company")
    pp.customer = sheet.customer
    pp.get_items_from = "Material Request" 
    
    for item in sheet.items:
        row = pp.append("po_items", {})
        row.item_code = item.item_code
        row.qty = item.qty
        row.warehouse = item.warehouse if hasattr(item, 'warehouse') else ""
        if hasattr(item, 'sales_order_item'):
             row.sales_order_item = item.sales_order_item
             
    pp.insert()

    if frappe.db.has_column("Production Plan", "custom_planning_sheet"):
        frappe.db.set_value("Production Plan", pp.name, "custom_planning_sheet", sheet.name)
    elif frappe.db.has_column("Production Plan", "planning_sheet"):
        frappe.db.set_value("Production Plan", pp.name, "planning_sheet", sheet.name)

    # Persist PP link at sheet header (legacy) and item-level (source of truth for row actions)
    if frappe.db.has_column("Planning sheet", "custom_production_plan"):
        frappe.db.set_value("Planning sheet", sheet.name, "custom_production_plan", pp.name)
    elif frappe.db.has_column("Planning sheet", "production_plan"):
        frappe.db.set_value("Planning sheet", sheet.name, "production_plan", pp.name)

    psi_pp_field = _psi_production_plan_field()
    psi_order_sheet_field = _psi_order_sheet_field()
    if psi_pp_field or psi_order_sheet_field:
        for item in sheet.items:
            if psi_pp_field:
                frappe.db.set_value("Planning Table", item.name, psi_pp_field, pp.name)
            if psi_order_sheet_field and psi_order_sheet_field != psi_pp_field:
                frappe.db.set_value("Planning Table", item.name, psi_order_sheet_field, pp.name)
    
    # Update Status to Planned
    if sheet.sales_order:
        frappe.db.set_value("Sales Order", sheet.sales_order, "custom_production_status", "Planned")
        
    return pp.name

@frappe.whitelist()
def create_production_plan_bulk(sheets):
    """
    Creates Production Plans for multiple Planning Sheets at once.
    """
    import json
    if isinstance(sheets, str):
        sheets = json.loads(sheets)
    
    if not sheets: return
    
    created_plans = []
    
    # Optional: Group by Customer? 
    # Usually Production Plans are per Customer or Per SO.
    # If we select multiple sheets from different customers, we probably want separate Production Plans?
    # Or one big Production Plan?
    # Standard ERPNext Production Plan can take multiple Sales Orders / Material Requests.
    # But here we are mapping from Planning Sheet -> Production Plan.
    # Let's create ONE Production Plan per Planning Sheet for simplicity and traceability (1:1 mapping),
    # unless user requested merging.
    # The prompt doesn't specify merging.
    # "Create Plan: Button to convert selected/viewed confirmed orders into a production plan."
    # If 10 orders are visible, and I click "Create Plan", maybe I want 10 plans?
    # OR 1 plan with 10 items?
    # 1 Plan with 10 items is better for "Batching".
    # BUT if customers are different, we can't make 1 Plan (usually).
    # ERPNext Production Plan has `customer` field. If filled, restricts to that customer.
    # If empty, can handle multiple?
    # Let's try to group by Customer.
    
    # 1. Fetch all sheets
    sheet_docs = [frappe.get_doc("Planning sheet", s) for s in sheets]
    
    # 2. Group by Customer
    sheets_by_customer = {}
    for s in sheet_docs:
        cust = s.customer or "No Customer"
        if cust not in sheets_by_customer:
            sheets_by_customer[cust] = []
        sheets_by_customer[cust].append(s)
        
    # 3. Create Plans
    for cust, cust_sheets in sheets_by_customer.items():
        existing_pps = [
            _resolve_existing_production_plan_for_planning_sheet(s.name) for s in cust_sheets
        ]
        non_null = [p for p in existing_pps if p]
        if non_null:
            unique = set(non_null)
            if len(unique) > 1:
                frappe.throw(
                    _(
                        "These planning sheets are already linked to different Production Plans ({0}). "
                        "Cancel duplicate plans in Manufacturing or unlink sheets before creating a new merged plan."
                    ).format(", ".join(sorted(unique)))
                )
            only_pp = list(unique)[0]
            if len(non_null) == len(cust_sheets):
                # Every sheet in this batch already points at the same PP — do not create another.
                created_plans.append(only_pp)
                continue
            frappe.throw(
                _(
                    "Some planning sheets already have Production Plan {0}; others do not. "
                    "Link all rows first or create plans one sheet at a time."
                ).format(only_pp)
            )

        pp = frappe.new_doc("Production Plan")
        pp.company = frappe.defaults.get_user_default("Company")
        pp.customer = cust if cust != "No Customer" else None
        pp.get_items_from = "Material Request" # Dummy, we fill manually
        
        # Add Reference Sales Orders?
        # Production Plan has table `sales_orders`.
        seen_so = set()
        for s in cust_sheets:
            if s.sales_order and s.sales_order not in seen_so:
                pp.append("sales_orders", {
                    "sales_order": s.sales_order,
                    "sales_order_date": s.creation # approximation
                })
                seen_so.add(s.sales_order)
        
        # Add Items
        for s in cust_sheets:
            for item in s.items:
                row = pp.append("po_items", {})
                row.item_code = item.item_code
                row.qty = item.qty
                # row.warehouse = ... default?
                if hasattr(item, 'sales_order_item'):
                     row.sales_order_item = item.sales_order_item
            
            # Update Status of Schema
            if s.sales_order:
                frappe.db.set_value("Sales Order", s.sales_order, "custom_production_status", "Planned")
        
        pp.insert()

        if len(cust_sheets) == 1:
            s0 = cust_sheets[0]
            if frappe.db.has_column("Production Plan", "custom_planning_sheet"):
                frappe.db.set_value("Production Plan", pp.name, "custom_planning_sheet", s0.name)
            elif frappe.db.has_column("Production Plan", "planning_sheet"):
                frappe.db.set_value("Production Plan", pp.name, "planning_sheet", s0.name)

        # Persist PP link at item-level for exact row-to-PP mapping
        psi_pp_field = _psi_production_plan_field()
        psi_order_sheet_field = _psi_order_sheet_field()
        for s in cust_sheets:
            if frappe.db.has_column("Planning sheet", "custom_production_plan"):
                frappe.db.set_value("Planning sheet", s.name, "custom_production_plan", pp.name)
            elif frappe.db.has_column("Planning sheet", "production_plan"):
                frappe.db.set_value("Planning sheet", s.name, "production_plan", pp.name)

            if psi_pp_field or psi_order_sheet_field:
                for item in s.items:
                    if psi_pp_field:
                        frappe.db.set_value("Planning Table", item.name, psi_pp_field, pp.name)
                    if psi_order_sheet_field and psi_order_sheet_field != psi_pp_field:
                        frappe.db.set_value("Planning Table", item.name, psi_order_sheet_field, pp.name)

        created_plans.append(pp.name)
        
    return created_plans


@frappe.whitelist()
def audit_production_plans_for_planning_sheet(planning_sheet_name):
    """
    Read-only helper: list Production Plan documents tied to a Planning sheet.
    Use after repeated "Create Plan" clicks to see duplicates before cancelling extras in Manufacturing.
    """
    if not planning_sheet_name:
        return {"ok": False, "message": "planning_sheet_name required"}
    if not frappe.db.exists("Planning sheet", planning_sheet_name):
        return {"ok": False, "message": "Planning sheet not found"}

    resolved = _resolve_existing_production_plan_for_planning_sheet(planning_sheet_name)
    by_link = []
    for col in ("custom_planning_sheet", "planning_sheet"):
        if frappe.db.has_column("Production Plan", col):
            by_link.extend(
                frappe.get_all(
                    "Production Plan",
                    filters={col: planning_sheet_name},
                    fields=["name", "docstatus", "status", "creation"],
                    order_by="creation asc",
                )
            )

    header_pp = None
    for col in ("custom_production_plan", "production_plan"):
        if frappe.db.has_column("Planning sheet", col):
            header_pp = frappe.db.get_value("Planning sheet", planning_sheet_name, col)
            break

    return {
        "ok": True,
        "planning_sheet": planning_sheet_name,
        "reuse_would_return": resolved,
        "header_production_plan": header_pp,
        "production_plans_with_reverse_link": by_link,
    }


@frappe.whitelist()
def create_planning_sheets_bulk(sales_orders):
    """
    Creates Planning Sheets for selected Sales Orders.
    Uses GSM usage logic (Unit 1>50, etc) to auto-allocate items.
    """
    import json
    if isinstance(sales_orders, str):
        sales_orders = json.loads(sales_orders)
        
    created = []
    errors = []
    
    # GSM/Quality Maps (Helper)
    # Re-defining here or using global
    
    for so_name in sales_orders:
        try:
            # Strict singleton: never create another sheet unless existing one is deleted.
            if _find_existing_sheet_for_sales_order(so_name):
                continue
                
            doc = frappe.get_doc("Sales Order", so_name)
            
            ps = frappe.new_doc("Planning sheet")
            ps.sales_order = doc.name
            ps.party_code = doc.get("party_code") or doc.customer
            ps.customer = _resolve_customer_link(doc.customer, doc.get("party_code"))
            ps.dod = doc.delivery_date
            ps.ordered_date = doc.transaction_date
            ps.planning_status = "Draft"
            
            _populate_planning_sheet_items(ps, doc)
            update_sheet_plan_codes(ps, include_legacy=True)
            if not ps.get("quality"):
                ps.quality = "Standard"
            ps.insert(ignore_permissions=True)
            frappe.db.commit()
            _link_board_planned_rows_to_legacy_items(ps.name)
            _sync_lamination_fabric_planning_rows(ps.name)
            final_doc = frappe.get_doc("Planning sheet", ps.name)
            update_sheet_plan_codes(final_doc, include_legacy=True)
            created.append(ps.name)
            
        except Exception as e:
            frappe.log_error(f"Failed to create plan for {so_name}: {str(e)}")
            errors.append(so_name)
            
            
    return {"created": created, "errors": errors}


@frappe.whitelist()
def save_color_order(order):
    """Save custom color order global default."""
    if isinstance(order, str):
        try:
            import json
            order = json.loads(order)
        except:
            pass
    if not isinstance(order, list):
        return
    frappe.defaults.set_global_default("production_color_order", frappe.as_json(order))
    return "saved"

@frappe.whitelist()
def get_color_order():
    """Get custom color order global default."""
    try:
        order_str = frappe.defaults.get_global_default("production_color_order")
        if order_str:
            try:
                import json
                return json.loads(order_str)
            except Exception:
                return []
        return []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_color_order_error")
        return []

@frappe.whitelist()
def update_sequence(items):
    """
    Updates the idx of items for manual reordering.
    Expects items = [{name: 'ITEM-ID', idx: 1}, ...]
    Uses SQL to bypass potential Framework overhead/re-indexing logic.
    """
    import json
    if isinstance(items, str):
        items = json.loads(items)
        
    # Batch update? No, simple loop is fine for < 50 items usually.
    for i in items:
        frappe.db.sql("UPDATE `tabPlanning Table` SET idx=%s WHERE name=%s", (i["idx"], i["name"]))
        
    frappe.db.commit() # Ensure committed immediately 
    return "ok"


# --------------------------------------------------------------------------------
# Production Board Plan System (Separate from Color Chart)
# --------------------------------------------------------------------------------

@frappe.whitelist()
def get_pb_plans(date=None, start_date=None, end_date=None):
    """Get unique Production Board plan names for a date or range."""
    eff = _effective_date_expr("p")
    
    if start_date and end_date:
        query_start = frappe.utils.getdate(start_date)
        query_end = frappe.utils.getdate(end_date)
        date_condition = f"{eff} BETWEEN %s AND %s"
        params = [query_start, query_end]
    elif date:
        if "," in str(date):
            target_dates = [frappe.utils.getdate(d.strip()) for d in str(date).split(",") if d.strip()]
            fmt = ','.join(['%s'] * len(target_dates))
            date_condition = f"{eff} IN ({fmt})"
            params = target_dates
        else:
            target_date = frappe.utils.getdate(date)
            date_condition = f"{eff} = %s"
            params = [target_date]
    else:
        return []
    
    plans = frappe.db.sql(f"""
        SELECT DISTINCT IFNULL(p.custom_pb_plan_name, '') as pb_plan_name
        FROM `tabPlanning sheet` p
        WHERE {date_condition} AND p.docstatus < 2
            AND p.custom_pb_plan_name IS NOT NULL 
            AND p.custom_pb_plan_name != ''
    """, tuple(params), as_dict=True)
    
    db_plans = set([p.pb_plan_name for p in plans if p.pb_plan_name])
    persisted = {p["name"]: p.get("locked", 0) for p in get_persisted_plans("production_board")}
    
    all_names = db_plans.union(set(persisted.keys()))
    sorted_plans = sorted(list(all_names))
    
    return [{"name": n, "locked": persisted.get(n, 0)} for n in sorted_plans]

@frappe.whitelist()
def get_multiple_dates_capacity(dates, plan_name=None, pb_only=0):
    """
    Calculates the total aggregate capacity and load for multiple dates.
    Returns: {
        "Unit 1": {"total_limit": X, "total_load": Y},
        ...
    }
    """
    import json
    pb_only = cint(pb_only)
    if isinstance(dates, str):
        dates = [d.strip() for d in dates.split(",") if d.strip()]
        
    result = {}
    for unit in ["Unit 1", "Unit 2", "Unit 3", "Unit 4"]:
        total_limit = HARD_LIMITS.get(unit, 999.0) * len(dates)
        total_load = sum(get_unit_load(d, unit, plan_name, pb_only=pb_only) for d in dates)
        result[unit] = {
            "total_limit": total_limit,
            "total_load": total_load
        }
    return result

@frappe.whitelist()
def find_next_available_date(unit, start_date, required_tons=0, pb_only=1, days_ahead=30):
    """Find next date where unit has enough available capacity."""
    if not unit or not start_date:
        return {"date": None}

    start_dt = getdate(start_date)
    required = flt(required_tons)
    pb_only = cint(pb_only)
    days_ahead = cint(days_ahead) or 30
    limit = HARD_LIMITS.get(unit, 999.0)

    for i in range(1, days_ahead + 1):
        candidate = frappe.utils.add_days(start_dt, i)
        load = get_unit_load(candidate, unit, "__all__", pb_only=pb_only)
        if load + required <= (limit * 1.05):
            return {"date": str(candidate), "current_load": load, "limit": limit}

    # Fallback suggestion if no clean slot found in lookahead window
    fallback = frappe.utils.add_days(start_dt, 1)
    return {"date": str(fallback), "current_load": get_unit_load(fallback, unit, "__all__", pb_only=pb_only), "limit": limit}

@frappe.whitelist()
def push_to_pb(item_names, pb_plan_name, target_dates=None, target_date=None, fetch_dates=None):
    """
    Pushes ONLY the selected Planning Sheet items to a Production Board plan.
    target_dates can be a comma-separated list of dates (legacy).
    target_date is the explicit single start date (preferred).
    Items will be sequentially load-balanced into the dates honoring their HARD_LIMITS daily limits.
    """
    import json
    if isinstance(item_names, str):
        item_names = json.loads(item_names)

    if not item_names or not pb_plan_name:
        return {"status": "error", "message": "Missing item names or plan name"}
        
    dates = []
    if target_date:
        dates = [str(target_date).strip()]
    elif target_dates:
        dates = [d.strip() for d in str(target_dates).split(",") if d.strip()]

    updated_count = 0
    skipped_already_pushed = []
    pb_sheet_cache = {}  # (party_code, effective_date) -> pb sheet name
    local_loads = {} # (date, unit) -> current load

    for name in item_names:
        try:
            item = frappe.get_doc("Planning Table", name)
            parent = frappe.get_doc("Planning sheet", item.parent)
            # Prevent re-pushing the same order again until it is reverted
            already_pushed = False
            if parent.get("custom_pb_plan_name"):
                already_pushed = True
            if not already_pushed and frappe.db.has_column("Planning Table", "planned_date"):
                if item.get("planned_date"):
                    already_pushed = True
            if already_pushed:
                skipped_already_pushed.append(name)
                continue
            item_wt = float(item.qty or 0) / 1000.0

            # Default to the single original date if no dates provided
            effective_date = dates[0] if dates else str(parent.get("custom_planned_date") or parent.ordered_date)

            # --- FIND CAPACITY SLOT ACROSS MULTIPLE DATES ---
            if len(dates) > 0:
                unit = item.unit or get_preferred_unit(item.custom_quality)
                limit = HARD_LIMITS.get(unit, 999.0)
                for check_date in dates:
                    load_key = (check_date, unit)
                    if load_key not in local_loads:
                        local_loads[load_key] = get_unit_load(check_date, unit, "__all__", pb_only=1)
                    
                    load = local_loads[load_key]
                    # Allow the item to slot here if we are under the limit, OR if it's the very last date fallback 
                    if (load + item_wt <= limit * 1.05) or (check_date == dates[-1]):
                        effective_date = check_date
                        local_loads[load_key] = load + item_wt
                        break
            # ------------------------------------------------

            party_code = parent.party_code or ""
            # IMPORTANT: Keep original ordered_date, only change planned_date
            original_ordered_date = str(parent.ordered_date)

            # Find or create a dedicated PB Planning Sheet for this date+party
            cache_key = (party_code, effective_date, pb_plan_name)
            if cache_key in pb_sheet_cache:
                pb_sheet_name = pb_sheet_cache[cache_key]
            else:
                created_pb_sheet = False
                existing = frappe.get_all("Planning sheet", filters={
                    "custom_pb_plan_name": pb_plan_name,
                    "custom_planned_date": effective_date,
                    "party_code": party_code,
                    "docstatus": ["<", 2]
                }, fields=["name"], limit=1)

                if existing:
                    pb_sheet_name = existing[0].name
                else:
                    so_existing = _find_existing_sheet_for_sales_order(parent.sales_order) if parent.sales_order else None
                    if so_existing:
                        pb_sheet_name = so_existing["name"]
                    else:
                        pb_sheet = frappe.new_doc("Planning sheet")
                        pb_sheet.custom_plan_name = parent.get("custom_plan_name") or "Default"
                        pb_sheet.custom_pb_plan_name = pb_plan_name
                        # CRITICAL: ordered_date stays as the ORIGINAL order date
                        pb_sheet.ordered_date = original_ordered_date
                        # planned_date is the actual production date (may be overflow)
                        pb_sheet.custom_planned_date = effective_date
                        pb_sheet.party_code = party_code
                        pb_sheet.customer = _resolve_customer_link(parent.customer, parent.party_code)
                        pb_sheet.sales_order = parent.sales_order or ""
                        pb_sheet.insert(ignore_permissions=True)
                        pb_sheet_name = pb_sheet.name
                        created_pb_sheet = True
                    # Force custom fields via SQL
                    # IMPORTANT: only write sheet-level planned date when a new sheet is created.
                    # Reused sheets must not have their header date overwritten.
                    if created_pb_sheet and frappe.db.has_column("Planning sheet", "custom_pb_plan_name"):
                        frappe.db.sql("""
                            UPDATE `tabPlanning sheet`
                            SET custom_pb_plan_name = %s, custom_plan_name = %s,
                                custom_planned_date = %s
                            WHERE name = %s
                        """, (pb_plan_name, parent.get("custom_plan_name") or "Default",
                              effective_date, pb_sheet_name))

                pb_sheet_cache[cache_key] = pb_sheet_name

            # Find the current max idx on this PB sheet to append correctly
            max_idx = frappe.db.sql("""
                SELECT COALESCE(MAX(idx), 0) FROM `tabPlanning Table` WHERE parent = %s
            """, (pb_sheet_name,))[0][0]

            # Move item to the PB sheet via raw SQL (works on submitted docs)
            frappe.db.sql("""
                UPDATE `tabPlanning Table`
                SET parent = %s, parenttype = 'Planning sheet', parentfield = %s, idx = %s
                WHERE name = %s
            """, (pb_sheet_name, _get_pt_parentfield(), max_idx + 1, name))

            # Also set item-level planned date for consistency
            if frappe.db.has_column("Planning Table", "planned_date"):
                frappe.db.sql("""
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s
                    WHERE name = %s
                """, (effective_date, name))

            updated_count += 1

        except Exception as e:
            frappe.log_error(f"push_to_pb error for item {name}: {e}", "Push to PB")

    # Persist this PB plan name so it appears in the plan dropdown
    persisted = get_persisted_plans("production_board")
    if not any(p["name"] == pb_plan_name for p in persisted):
        persisted.append({"name": pb_plan_name, "locked": 0})
        import json as _json
        frappe.defaults.set_global_default(
            "production_scheduler_production_board_plans",
            _json.dumps(persisted)
        )

    frappe.db.commit()
    if updated_count == 0 and skipped_already_pushed:
        return {
            "status": "success",
            "message": "All selected orders are already pushed to the Production Board.",
            "skipped_already_pushed": len(skipped_already_pushed),
            "plan_name": pb_plan_name,
        }
    return {
        "status": "success",
        "updated_count": updated_count,
        "skipped_already_pushed": len(skipped_already_pushed),
        "plan_name": pb_plan_name,
    }


@frappe.whitelist()
def push_items_to_pb(
    items_data,
    pb_plan_name=None,
    fetch_dates=None,
    target_date=None,
    strict_target_date=0,
    allow_month_cascade=0,
    approve_cross_month=0,
    approve_maintenance_move=0,
):
    """
    Pushes Planning Sheet Items to a Production Board plan.
    Re-parents each item to a PB Planning Sheet (with custom_planned_date set)
    so the Production Board can find them via the sheet-level filter.
    items_data: list of dicts [{"name": "...", "target_date": "...", "target_unit": "...", "strict_target_date": 1}]
    strict_target_date: when true, keep item exactly on selected target date (no auto-cascade).
    allow_month_cascade: when 0, prevents cascading beyond target month end date.
    Note: automatic pre-shifting of queued white orders is intentionally disabled.
    """
    import json
    from frappe.utils import getdate, add_days
    if isinstance(items_data, str):
        items_data = json.loads(items_data)

    if not items_data:
        return {"status": "error", "message": "Missing item data"}

    def _cascade_white_queue_for_unit(target_date_val, unit_val, active_pb_plan=None, shared_loads=None):
        """
        Shift queued white items forward day-by-day for a given unit/date slot.
        This frees the target slot for incoming color push while preserving white order.
        Updates only item-level planned_date (and plan code when available).
        """
        from frappe.utils import getdate, add_days

        target_dt = getdate(target_date_val)
        unit_limit = HARD_LIMITS.get(unit_val, 999.0)
        shared_loads = shared_loads if isinstance(shared_loads, dict) else {}

        white_sql = ", ".join([f"'{c.upper().replace(' ', '')}'" for c in WHITE_COLORS])
        plan_cond = ""
        params = [target_dt, unit_val]
        if active_pb_plan:
            plan_cond = "AND COALESCE(p.custom_pb_plan_name, '') = %s"
            params.append(active_pb_plan)

        rows = frappe.db.sql(f"""
            SELECT
                i.name,
                i.qty,
                i.unit,
                COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date) AS effective_date
            FROM `tabPlanning Table` i
            JOIN `tabPlanning sheet` p ON i.parent = p.name
            WHERE p.docstatus < 2
              AND i.docstatus < 2
              AND i.unit = %s
              AND DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) >= DATE(%s)
              AND REPLACE(UPPER(COALESCE(i.color, '')), ' ', '') IN ({white_sql})
              {plan_cond}
            ORDER BY DATE(COALESCE(i.planned_date, p.custom_planned_date, p.ordered_date)) ASC, i.idx ASC
        """, tuple([params[1], params[0]] + params[2:]), as_dict=True)

        if not rows:
            return {"moved": 0, "dates": set()}

        has_item_planned_col = frappe.db.has_column("Planning Table", "planned_date")
        has_plan_code_col = frappe.db.has_column("Planning Table", "plan_name")

        moved_count = 0
        moved_dates = set()

        for r in rows:
            item_name = r.get("name")
            qty_tons = flt(r.get("qty")) / 1000.0
            source_date = str(getdate(r.get("effective_date")))

            # Remove this item's load from its current source day in the shared cache.
            src_key = (source_date, unit_val)
            if src_key not in shared_loads:
                shared_loads[src_key] = get_unit_load(source_date, unit_val, "__all__", pb_only=1)
            shared_loads[src_key] = max(0.0, shared_loads[src_key] - qty_tons)

            # Queue shift rule: each white item moves to at least the next day, skipping maintenance dates.
            candidate = add_days(getdate(source_date), 1)
            maintenance_encountered = None
            
            while True:
                candidate_str = candidate if isinstance(candidate, str) else candidate.strftime("%Y-%m-%d")
                
                # CHECK MAINTENANCE: Skip if date is under maintenance
                if is_date_under_maintenance(unit_val, candidate_str):
                    maint_info = get_maintenance_info_on_date(unit_val, candidate_str)
                    if not maintenance_encountered:
                        maintenance_encountered = maint_info
                    candidate = add_days(candidate, 1)
                    continue  # Skip this date, try next day
                
                load_key = (candidate_str, unit_val)
                if load_key not in shared_loads:
                    shared_loads[load_key] = get_unit_load(candidate_str, unit_val, "__all__", pb_only=1)

                current_load = shared_loads[load_key]
                if (current_load + qty_tons <= unit_limit * 1.05) or (current_load == 0 and qty_tons >= unit_limit):
                    shared_loads[load_key] = current_load + qty_tons
                    break

                candidate = add_days(candidate, 1)

            if not has_item_planned_col:
                continue

            if has_plan_code_col:
                new_code = generate_plan_code(candidate_str, unit_val, active_pb_plan)
                frappe.db.sql("""
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s,
                        plan_name = %s
                    WHERE name = %s
                """, (candidate_str, new_code, item_name))
            else:
                frappe.db.sql("""
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s
                    WHERE name = %s
                """, (candidate_str, item_name))

            moved_count += 1
            moved_dates.add(candidate_str)

        return {"moved": moved_count, "dates": moved_dates, "maintenance_skipped": maintenance_encountered is not None, "maintenance_info": maintenance_encountered}

    approve_cross_month = cint(approve_cross_month)
    approve_maintenance_move = cint(approve_maintenance_move)
    count = 0
    skipped_already_pushed = []
    push_errors = []
    updated_sheets = set()
    pb_sheet_cache = {}  # (party_code, target_date) -> pb sheet name
    local_loads = {} # (date, unit) -> current load
    unit_date_idx_offsets = {} # (unit, date) -> max_idx
    effective_dates_used = set()
    white_shifted_count = 0
    white_shifted_dates = set()
    cross_month_candidates = []
    maintenance_move_candidates = []

    # Disabled by request: do not pre-shift queued white orders when pushing colors.
    # Keep counters for response compatibility.

    for item in items_data:
        name = item.get("name") if isinstance(item, dict) else item
        target_date_raw = item.get("target_dates") or item.get("target_date") if isinstance(item, dict) else None
        target_unit = item.get("target_unit") if isinstance(item, dict) else None
        sequence_no = item.get("sequence_no") if isinstance(item, dict) else None
        item_strict_target = cint(item.get("strict_target_date")) if isinstance(item, dict) else 0

        try:
            # Get item + parent sheet info
            item_doc = frappe.get_doc("Planning Table", name)
            parent_doc = frappe.get_doc("Planning sheet", item_doc.parent)
            # Prevent re-pushing ΓÇö check ITEM-LEVEL only (not parent-level!)
            # Parent-level check was blocking ALL items from a sheet once one was pushed
            already_pushed = False
            if frappe.db.has_column("Planning Table", "planned_date"):
                if item_doc.get("planned_date"):
                    already_pushed = True
            if already_pushed:
                skipped_already_pushed.append(name)
                continue
            item_wt = float(item_doc.qty or 0) / 1000.0

            target_dates = [d.strip() for d in str(target_date_raw).split(",")] if target_date_raw else []

            effective_date = target_dates[0] if target_dates else str(parent_doc.get("custom_planned_date") or parent_doc.ordered_date)

            # --- FIND CAPACITY SLOT ACROSS MULTIPLE DATES (LIMITED CASCADE) ---
            unit = target_unit or item_doc.unit or get_preferred_unit(item_doc.custom_quality)
            unit = normalize_planning_unit_for_select(unit)
            limit = HARD_LIMITS.get(unit, 999.0)
            
            current_check_date = target_dates[0] if target_dates else str(parent_doc.get("custom_planned_date") or parent_doc.ordered_date)

            # Individual push can force exact selected date, skipping auto-next-day cascade.
            strict_keep_date = cint(strict_target_date) or cint(item_strict_target)
            if strict_keep_date:
                # STRICT MODE:
                # - capacity overflow: do not auto-cascade (user must change date)
                # - maintenance block: auto-propose next available day, but require user approval
                if is_date_under_maintenance(unit, current_check_date):
                    proposed = current_check_date
                    for _ in range(31):
                        next_d = add_days(proposed, 1)
                        proposed = next_d if isinstance(next_d, str) else next_d.strftime("%Y-%m-%d")
                        if is_date_under_maintenance(unit, proposed):
                            continue
                        load_key_next = (proposed, unit)
                        if load_key_next not in local_loads:
                            local_loads[load_key_next] = get_unit_load(proposed, unit, "__all__", pb_only=1)
                        next_load = local_loads[load_key_next]
                        if ((next_load + item_wt <= limit * 1.05) or (next_load == 0 and item_wt >= limit)):
                            break
                    if proposed == current_check_date:
                        frappe.msgprint(
                            f"⚠️ Item {item_doc.item_code}: no available date found after maintenance. Please change date.",
                            indicator='orange'
                        )
                        continue

                    maintenance_move_candidates.append({
                        "item_name": name,
                        "item_code": item_doc.get("item_code"),
                        "party_code": parent_doc.get("party_code") or "",
                        "unit": unit,
                        "from_date": str(current_check_date),
                        "to_date": str(proposed),
                        "qty": flt(item_doc.qty or 0),
                    })
                    if not approve_maintenance_move:
                        continue
                    current_check_date = proposed

                load_key = (current_check_date, unit)
                if load_key not in local_loads:
                    local_loads[load_key] = get_unit_load(current_check_date, unit, "__all__", pb_only=1)
                load = local_loads[load_key]
                if not ((load + item_wt <= limit * 1.05) or (load == 0 and item_wt >= limit)):
                    frappe.msgprint(
                        f"⚠️ Item {item_doc.item_code}: target date {current_check_date} is at capacity for {unit}. Please change date.",
                        indicator='orange'
                    )
                    continue

                effective_date = current_check_date
                local_loads[load_key] = load + item_wt
            else:
                # FLEX MODE: User confirmed cascading - allow flexible dates but WITH LIMITS
                maintenance_block = None
                max_cascade_days = 30  # Maximum 30 days cascade (prevents wrapping to next month)
                cascade_days = 0
                
                while cascade_days < max_cascade_days:
                    # CHECK MAINTENANCE: Skip if under maintenance
                    if is_date_under_maintenance(unit, current_check_date):
                        maint_info = get_maintenance_info_on_date(unit, current_check_date)
                        if not maintenance_block:
                            maintenance_block = {
                                "date": current_check_date,
                                "type": maint_info["type"],
                                "start": maint_info["start_date"],
                                "end": maint_info["end_date"]
                            }
                        next_d = add_days(current_check_date, 1)
                        current_check_date = next_d if isinstance(next_d, str) else next_d.strftime("%Y-%m-%d")
                        cascade_days += 1
                        continue
                    
                    load_key = (current_check_date, unit)
                    if load_key not in local_loads:
                        local_loads[load_key] = get_unit_load(current_check_date, unit, "__all__", pb_only=1)
                    
                    load = local_loads[load_key]
                    
                    # Allow placement if it fits within the limit (with 5% buffer)
                    # OR if the day is completely empty but the item itself is larger than the limit (prevents infinite loop)
                    if (load + item_wt <= limit * 1.05) or (load == 0 and item_wt >= limit):
                        effective_date = current_check_date
                        local_loads[load_key] = load + item_wt
                        # Track if maintenance was encountered
                        if maintenance_block and "maintenance_conflicts" not in locals():
                            maintenance_conflicts = []
                        if maintenance_block:
                            if "maintenance_conflicts" not in locals():
                                maintenance_conflicts = []
                            maintenance_conflicts.append(maintenance_block)
                        break
                    
                    # Otherwise, capacity is full for this date -> Cascade to the next day
                    next_d = add_days(current_check_date, 1)
                    current_check_date = next_d if isinstance(next_d, str) else next_d.strftime("%Y-%m-%d")
                    cascade_days += 1
                
                # If we hit max cascade limit, reject the item
                if cascade_days >= max_cascade_days and effective_date != current_check_date:
                    frappe.msgprint(
                        f"⚠️ Item {item_doc.item_code}: Cannot place within 30-day window. Skipped.",
                        indicator='orange'
                    )
                    continue
            
            # Safety check: if effective_date is None or empty, skip this item
            if not effective_date:
                continue

            # Strict month-boundary guard: require explicit approval before moving any item
            # from selected/source month to a different month.
            source_ref_date = target_dates[0] if target_dates else str(parent_doc.get("custom_planned_date") or parent_doc.ordered_date)
            try:
                src_dt = getdate(source_ref_date)
                dst_dt = getdate(effective_date)
                if src_dt and dst_dt and (src_dt.month != dst_dt.month or src_dt.year != dst_dt.year):
                    cross_month_candidates.append({
                        "item_name": name,
                        "item_code": item_doc.get("item_code"),
                        "party_code": parent_doc.get("party_code") or "",
                        "unit": unit,
                        "from_date": str(src_dt),
                        "to_date": str(dst_dt),
                        "qty": flt(item_doc.qty or 0),
                    })
                    if not approve_cross_month:
                        continue
            except Exception:
                pass
            
            # ------------------------------------------------

            party_code = parent_doc.party_code or ""
            # IMPORTANT: Keep original ordered_date, only change planned_date
            original_ordered_date = str(parent_doc.ordered_date)

            # ΓöÇΓöÇ Set item-level unit if user picked a different unit ΓöÇΓöÇ
            if target_unit:
                frappe.db.sql("""
                    UPDATE `tabPlanning Table` SET unit = %s WHERE name = %s
                """, (unit, name))

            # ΓöÇΓöÇ Find or create a dedicated PB Planning Sheet ΓöÇΓöÇ
            # BUG FIX: Prefer keeping items in original sheet if possible to prevent "Multiple Sheets per SO" issue.
            # If the original sheet already matches the target date, we don't need to re-parent.
            
            can_reuse_original = False
            original_effective_date = str(parent_doc.get("custom_planned_date") or parent_doc.ordered_date)
            if original_effective_date == effective_date:
                can_reuse_original = True
                pb_sheet_name = parent_doc.name
            
            if not can_reuse_original:
                cache_key = (party_code, effective_date)
                if cache_key in pb_sheet_cache:
                    pb_sheet_name = pb_sheet_cache[cache_key]
                else:
                    created_pb_sheet = False
                    # ALWAYS Reuse ANY unlocked sheet for the same SO if it exists (regardless of its header date)
                    existing = frappe.get_all("Planning sheet", filters={
                        "sales_order": parent_doc.sales_order or "",
                        "docstatus": 0
                    }, fields=["name"], limit=1)

                    if existing:
                        pb_sheet_name = existing[0].name
                    else:
                        so_existing = _find_existing_sheet_for_sales_order(parent_doc.sales_order) if parent_doc.sales_order else None
                        if so_existing:
                            pb_sheet_name = so_existing["name"]
                        else:
                            pb_sheet = frappe.new_doc("Planning sheet")
                            # CRITICAL: ordered_date stays as ORIGINAL
                            pb_sheet.ordered_date = original_ordered_date
                            pb_sheet.custom_planned_date = effective_date
                            pb_sheet.party_code = party_code
                            pb_sheet.customer = _resolve_customer_link(parent_doc.customer, parent_doc.party_code)
                            pb_sheet.sales_order = parent_doc.sales_order or ""
                            pb_sheet.insert(ignore_permissions=True)
                            pb_sheet_name = pb_sheet.name
                            created_pb_sheet = True

                    # Force custom fields via SQL to ensure consistency (New OR Existing)
                    # IMPORTANT: do not overwrite custom_planned_date on reused sheets.
                    if created_pb_sheet:
                        frappe.db.sql("""
                            UPDATE `tabPlanning sheet`
                            SET custom_plan_name = %s, custom_planned_date = %s
                            WHERE name = %s
                        """, (pb_plan_name or parent_doc.get("custom_plan_name") or "Default", effective_date, pb_sheet_name))

                    pb_sheet_cache[cache_key] = pb_sheet_name

            # ΓöÇΓöÇ Find the current max idx on this PB sheet ΓöÇΓöÇ
            max_idx = frappe.db.sql("""
                SELECT COALESCE(MAX(idx), 0) FROM `tabPlanning Table` WHERE parent = %s
            """, (pb_sheet_name,))[0][0]

            # ΓöÇΓöÇ Move item to the PB sheet via raw SQL ΓöÇΓöÇ
            # 1. Update parent link AND explicitly save the target unit to the DB
            frappe.db.sql("""
                UPDATE `tabPlanning Table`
                SET parent = %s, parenttype = 'Planning sheet', parentfield = %s, unit = %s
                WHERE name = %s
            """, (pb_sheet_name, _get_pt_parentfield(), unit, name))

            # 2. Set item-level planned date + plan code for consistency
            # This ensures ONLY the pushed item moves, staying granular.
            if frappe.db.has_column("Planning Table", "planned_date"):
                new_plan_code = generate_plan_code(effective_date, unit, pb_plan_name)
                
                frappe.db.sql("""
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s, plan_name = %s
                    WHERE name = %s
                """, (effective_date, new_plan_code, name))
            effective_dates_used.add(effective_date)

            # ΓöÇΓöÇ Update idx for sequence ordering on board ΓöÇΓöÇ
            # Use a global offset for the unit/date to ensure monotonic sequence
            # AND prevent triangular growth bug (max_idx + sequence_no inside loop)
            idx_key = (unit, effective_date)
            if idx_key not in unit_date_idx_offsets:
                # Find current max idx for this unit/date across ALL sheets
                # (Not just the new pb_sheet_name, to avoid collisions with items already on board)
                res = frappe.db.sql("""
                    SELECT COALESCE(MAX(i.idx), 0)
                    FROM `tabPlanning Table` i
                    JOIN `tabPlanning sheet` p ON i.parent = p.name
                    WHERE i.unit = %s AND p.custom_planned_date = %s
                      AND p.docstatus < 2
                """, (unit, effective_date))
                unit_date_idx_offsets[idx_key] = res[0][0] if res else 0

            if sequence_no is not None:
                new_idx = unit_date_idx_offsets[idx_key] + int(sequence_no)
            else:
                unit_date_idx_offsets[idx_key] += 1
                new_idx = unit_date_idx_offsets[idx_key]
            
            frappe.db.set_value("Planning Table", name, "idx", new_idx)

            # ΓöÇΓöÇ Track which original sheets were touched ΓöÇΓöÇ
            updated_sheets.add(item_doc.parent)  # original parent

            # ΓöÇΓöÇ Clean up original sheet if now empty ΓöÇΓöÇ
            if item_doc.parent != pb_sheet_name:
                remaining = frappe.db.count("Planning Table", {"parent": item_doc.parent})
                if remaining == 0:
                    try:
                        frappe.delete_doc("Planning sheet", item_doc.parent, ignore_permissions=True, force=True)
                    except Exception:
                        pass

            count += 1

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Push to Board Error")
            push_errors.append({"item": name, "error": str(e)})

    if maintenance_move_candidates and not approve_maintenance_move:
        frappe.db.rollback()
        return {
            "status": "maintenance_move_approval_required",
            "message": "Some orders are on maintenance dates and need next-day movement. User approval required.",
            "candidates": maintenance_move_candidates[:200],
            "count": len(maintenance_move_candidates),
        }

    if cross_month_candidates and not approve_cross_month:
        frappe.db.rollback()
        return {
            "status": "cross_month_approval_required",
            "message": "Some orders would move to next month. User approval required.",
            "candidates": cross_month_candidates[:200],
            "count": len(cross_month_candidates),
        }

    # Persist this PB plan name
    persisted = get_persisted_plans("production_board")
    if not any(p["name"] == pb_plan_name for p in persisted):
        persisted.append({"name": pb_plan_name, "locked": 0})
        import json as _json
        frappe.defaults.set_global_default(
            "production_scheduler_production_board_plans",
            _json.dumps(persisted)
        )

    frappe.db.commit()
    
    # Return detailed results to the frontend
    response = {
        "status": "success",
        "count": count, # moved items
        "moved_items": count, # legacy alias
        "dates": sorted(list(effective_dates_used)),
        "white_shifted_count": white_shifted_count,
        "white_shifted_dates": sorted(list(white_shifted_dates)),
        "skipped_already_pushed": len(skipped_already_pushed),
        "updated_sheets": len(updated_sheets),
        "plan_name": pb_plan_name,
        "errors": push_errors[:50],
    }
    if push_errors and not count:
        response["status"] = "error"
        response["message"] = push_errors[0].get("error") or "Push failed"

    # Add maintenance conflicts if any were encountered
    if "maintenance_conflicts" in locals() and maintenance_conflicts:
        response["maintenance_conflicts"] = maintenance_conflicts
    
    return response




@frappe.whitelist()
def backfill_production_plan_links(sales_order=None):
    """
    Backfill custom_production_plan field on Planning Sheet Items.
    Links items to their Production Plans based on Sales Order.
    """
    import json
    
    result = {
        "updated": 0,
        "skipped": 0,
        "errors": []
    }
    
    try:
        # Find Planning Sheets for this SO
        if sales_order:
            sheets = frappe.get_all("Planning sheet", filters={"sales_order": sales_order}, fields=["name"])
        else:
            sheets = frappe.get_all("Planning sheet", fields=["name"])
        
        if not sheets:
            return {"status": "error", "message": f"No Planning Sheets found for SO: {sales_order}"}
        
        sheet_names = [s["name"] for s in sheets]
        
        for sheet_name in sheet_names:
            try:
                sheet_doc = frappe.get_doc("Planning sheet", sheet_name)
                so = sheet_doc.sales_order
                
                if not so:
                    continue
                
                # Find Production Plans for this Sales Order
                pps = frappe.get_all("Production Plan", 
                    filters={"sales_order": so, "docstatus": ["<", 2]},
                    fields=["name"],
                    limit=1
                )
                
                if not pps:
                    result["skipped"] += 1
                    continue
                
                pp_name = pps[0]["name"]
                
                # Update all items in this sheet
                items = frappe.get_all("Planning Table", 
                    filters={"parent": sheet_name},
                    fields=["name"]
                )
                
                for item in items:
                    try:
                        frappe.db.set_value(
                            "Planning Table",
                            item["name"],
                            "custom_production_plan",
                            pp_name
                        )
                        result["updated"] += 1
                    except Exception as e:
                        result["errors"].append(f"Item {item['name']}: {str(e)}")
                        result["skipped"] += 1
            
            except Exception as e:
                result["errors"].append(f"Sheet {sheet_name}: {str(e)}")
        
        frappe.db.commit()
        result["status"] = "success"
    
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


@frappe.whitelist()
def backfill_sales_order_item_links(sales_order=None):
    """
    Backfill sales_order_item field on Planning Sheet Items.
    Links items to their Sales Order Items based on item_code matching.
    """
    import json
    
    result = {
        "updated": 0,
        "skipped": 0,
        "errors": []
    }
    
    try:
        # Find Planning Sheets
        if sales_order:
            sheets = frappe.get_all("Planning sheet", filters={"sales_order": sales_order}, fields=["name", "sales_order"])
        else:
            sheets = frappe.get_all("Planning sheet", fields=["name", "sales_order"])
        
        if not sheets:
            return {"status": "error", "message": f"No Planning Sheets found"}
        
        for sheet in sheets:
            try:
                sheet_name = sheet["name"]
                so = sheet["sales_order"]
                
                if not so:
                    continue
                
                # Get all items in this Planning Sheet
                psi_items = frappe.get_all("Planning Table",
                    filters={"parent": sheet_name},
                    fields=["name", "item_code"]
                )
                
                # Get all Sales Order Items for this SO
                so_items = frappe.get_all("Sales Order Item",
                    filters={"parent": so},
                    fields=["name", "item_code"]
                )
                
                # Create mapping: item_code -> SO Item name
                so_item_map = {soi["item_code"]: soi["name"] for soi in so_items}
                
                # Link Planning Sheet Items to Sales Order Items
                for psi in psi_items:
                    item_code = psi["item_code"]
                    if item_code in so_item_map:
                        so_item_name = so_item_map[item_code]
                        try:
                            frappe.db.set_value(
                                "Planning Table",
                                psi["name"],
                                "sales_order_item",
                                so_item_name
                            )
                            result["updated"] += 1
                        except Exception as e:
                            result["errors"].append(f"PSI {psi['name']}: {str(e)}")
                            result["skipped"] += 1
                    else:
                        result["skipped"] += 1
            
            except Exception as e:
                result["errors"].append(f"Sheet {sheet_name}: {str(e)}")
        
        frappe.db.commit()
        result["status"] = "success"
    
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


@frappe.whitelist()
def backfill_wo_production_plan_links(sales_order=None, item_code=None):
    """
    Backfill custom_production_plan on Planning Sheet Items by finding Work Orders.
    Links WO -> Production Plan -> Planning Sheet Item.
    Works even if Work Orders don't have sales_order field set.
    """
    result = {
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "linked_items": []
    }
    psi_pp_field = _psi_production_plan_field()
    psi_order_sheet_field = _psi_order_sheet_field()
    
    try:
        # Find Planning Sheets
        if sales_order:
            sheets = frappe.get_all("Planning sheet", filters={"sales_order": sales_order}, fields=["name", "sales_order"])
        else:
            sheets = frappe.get_all("Planning sheet", fields=["name", "sales_order"])
        
        if not sheets:
            return {"status": "error", "message": f"No Planning Sheets found"}
        
        for sheet in sheets:
            try:
                sheet_name = sheet["name"]
                
                # Get all items in this Planning Sheet
                psi_items = frappe.get_all("Planning Table",
                    filters={"parent": sheet_name},
                    fields=["name", "item_code"]
                )
                
                for psi in psi_items:
                    psi_item_code = psi["item_code"]
                    
                    try:
                        # Find Work Orders with matching item code
                        wos = frappe.db.sql("""
                            SELECT name, production_plan
                            FROM `tabWork Order`
                            WHERE production_item = %s
                              AND docstatus < 2
                            ORDER BY creation DESC
                            LIMIT 1
                        """, (psi_item_code,), as_dict=True)
                        
                        if wos and wos[0].get("production_plan"):
                            pp = wos[0]["production_plan"]
                            if psi_pp_field:
                                frappe.db.set_value(
                                    "Planning Table",
                                    psi["name"],
                                    psi_pp_field,
                                    pp
                                )
                            if psi_order_sheet_field and psi_order_sheet_field != psi_pp_field:
                                frappe.db.set_value(
                                    "Planning Table",
                                    psi["name"],
                                    psi_order_sheet_field,
                                    pp
                                )
                            result["updated"] += 1
                            result["linked_items"].append({
                                "psi": psi["name"],
                                "item_code": psi_item_code,
                                "wo": wos[0]["name"],
                                "pp": pp
                            })
                        else:
                            result["skipped"] += 1
                    
                    except Exception as e:
                        result["errors"].append(f"PSI {psi['name']}: {str(e)}")
                        result["skipped"] += 1
            
            except Exception as e:
                result["errors"].append(f"Sheet {sheet_name}: {str(e)}")
        
        frappe.db.commit()
        result["status"] = "success"
    
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


@frappe.whitelist()
def get_work_orders_for_sales_order(sales_order):
    """
    Get all Work Orders for a given Sales Order with production details.
    Safe server-side query bypassing Frappe security restrictions.
    """
    if not sales_order:
        return []
    
    try:
        wos = frappe.db.sql("""
            SELECT 
                name,
                item_code,
                production_item,
                qty,
                produced_qty,
                status,
                docstatus
            FROM `tabWork Order`
            WHERE sales_order = %s
              AND docstatus < 2
            ORDER BY creation DESC
        """, (sales_order,), as_dict=True)
        
        return {
            "status": "success",
            "count": len(wos),
            "work_orders": wos
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def get_work_orders_by_item_code(item_code):
    """
    Get all Work Orders for a given item code (bypasses sales_order requirement).
    Safe server-side query to find WOs regardless of sales_order linkage.
    """
    if not item_code:
        return {"status": "error", "message": "item_code required"}
    
    try:
        wos = frappe.db.sql("""
            SELECT 
                name,
                production_item,
                qty,
                produced_qty,
                status,
                sales_order,
                production_plan,
                docstatus
            FROM `tabWork Order`
            WHERE production_item = %s
            ORDER BY creation DESC
        """, (item_code,), as_dict=True)
        
        return {
            "status": "success",
            "count": len(wos),
            "item_code": item_code,
            "work_orders": wos
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def debug_production_qty_mapping(planning_sheet=None, item_name=None):
    """
    Diagnostic API to debug why production_qty shows 0 for specific items.
    Returns detailed information about Work Orders, Production Plans, and linkages.
    """
    import json
    result = {
        "planning_sheet": planning_sheet,
        "item_name": item_name,
        "diagnosis": []
    }
    
    if not planning_sheet or not item_name:
        return result
    
    try:
        item_doc = frappe.get_doc("Planning Table", item_name)
        sheet_doc = frappe.get_doc("Planning sheet", planning_sheet)
        
        result["item"] = {
            "name": item_doc.name,
            "item_code": item_doc.item_code,
            "qty": item_doc.qty,
            "custom_production_plan": item_doc.get("custom_production_plan"),
            "sales_order_item": item_doc.get("sales_order_item") or item_doc.get("custom_sales_order_item"),
        }
        result["sheet"] = {
            "name": sheet_doc.name,
            "sales_order": sheet_doc.sales_order,
        }
        
        # Check for Production Plan via item
        item_pp = item_doc.get("custom_production_plan")
        if item_pp:
            result["diagnosis"].append(f"✓ Item has custom_production_plan: {item_pp}")
            pps = frappe.get_all("Production Plan", filters={"name": item_pp}, fields=["name", "status", "docstatus"])
            if pps:
                result["diagnosis"].append(f"  → Production Plan exists: {pps[0]}")
        else:
            result["diagnosis"].append("✗ Item has NO custom_production_plan set")
        
        # Check for Work Orders via Sales Order
        so_item = item_doc.get("sales_order_item") or item_doc.get("custom_sales_order_item")
        if so_item:
            result["diagnosis"].append(f"✓ Item has sales_order_item: {so_item}")
            wos = frappe.get_all("Work Order", filters={"sales_order_item": so_item, "docstatus": ["<", 2]}, fields=["name", "produced_qty", "status", "docstatus"])
            result["diagnosis"].append(f"  → Found {len(wos)} Work Orders matching this SO item")
            for wo in wos[:3]:  # Show first 3
                result["diagnosis"].append(f"    - {wo.name}: produced_qty={wo.produced_qty}, status={wo.status}")
        else:
            result["diagnosis"].append("✗ Item has NO sales_order_item set")
        
        # Check for Work Orders via Sales Order
        if sheet_doc.sales_order:
            result["diagnosis"].append(f"✓ Sheet has sales_order: {sheet_doc.sales_order}")
            wos = frappe.get_all("Work Order", filters={"sales_order": sheet_doc.sales_order, "docstatus": ["<", 2]}, fields=["name", "produced_qty", "status", "docstatus"])
            result["diagnosis"].append(f"  → Found {len(wos)} Work Orders for this SO")
            for wo in wos[:3]:  # Show first 3
                result["diagnosis"].append(f"    - {wo.name}: produced_qty={wo.produced_qty}, status={wo.status}")
        else:
            result["diagnosis"].append("✗ Sheet has NO sales_order")

        # Check Work Orders via production_item (legacy fallback when SO linkage is missing)
        if item_doc.item_code:
            wo_item_rows = frappe.db.sql("""
                SELECT name, produced_qty, status, sales_order, production_plan
                FROM `tabWork Order`
                WHERE production_item = %s
                  AND docstatus < 2
                ORDER BY creation DESC
            """, (item_doc.item_code,), as_dict=True)
            result["diagnosis"].append(f"  → Found {len(wo_item_rows)} Work Orders by production_item={item_doc.item_code}")
            for wo in wo_item_rows[:3]:
                result["diagnosis"].append(
                    f"    - {wo.name}: produced_qty={wo.produced_qty}, status={wo.status}, sales_order={wo.sales_order or 'NULL'}, production_plan={wo.production_plan or 'NULL'}"
                )
        
        # Check Shaft Production Run
        spr_count = frappe.db.count("Shaft Production Run", {"docstatus": 1})
        result["diagnosis"].append(f"Shaft Production Run docs: {spr_count} submitted")
        
        result["status"] = "success"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result

@frappe.whitelist()
def debug_production_qty_fallback_map(planning_sheet=None, item_name=None):
    """
    Debug API to trace exact fallback map state and lookup keys for produced qty.
    Shows what's in SO->PP->WO maps and why production qty resolves to specific value.
    """
    import json
    result = {
        "planning_sheet": planning_sheet,
        "item_name": item_name,
        "maps": {},
        "lookup_keys": {},
        "resolved_qty": 0,
        "debug": []
    }
    
    try:
        if not planning_sheet or not item_name:
            return {"status": "error", "message": "planning_sheet and item_name required"}
        
        item_doc = frappe.get_doc("Planning Table", item_name)
        sheet_doc = frappe.get_doc("Planning sheet", planning_sheet)
        
        # Get SO
        so = sheet_doc.sales_order or ""
        item_code = (item_doc.item_code or "").strip()
        order_code = (sheet_doc.get("party_code") or "").strip()
        
        result["lookup_keys"] = {
            "sales_order": so,
            "item_code": item_code,
            "party_code": order_code
        }
        
        # Query strict maps directly
        so_names = [so] if so else []
        
        if so_names:
            so_order_code_col = None
            for c in ["order_code", "custom_order_code", "po_no", "customer_order_no"]:
                if frappe.db.has_column("Sales Order", c):
                    so_order_code_col = c
                    break
            
            format_string_so = ','.join(['%s'] * len(so_names))
            
            # Strict aggregation query
            so_order_select = "'' as so_order_code"
            so_order_join = ""
            so_order_group = ""
            if so_order_code_col:
                so_order_select = f"IFNULL(so.{so_order_code_col}, '') as so_order_code"
                so_order_join = "LEFT JOIN `tabSales Order` so ON so.name = pps.sales_order"
                so_order_group = ", so_order_code"
            
            so_item_prod_rows = frappe.db.sql(f"""
                SELECT pps.sales_order,
                       wo.production_item as item_code,
                       {so_order_select},
                       SUM(GREATEST(IFNULL(wo.produced_qty, 0), IFNULL(se_map.se_produced_qty, 0))) as produced_qty,
                       wo.name as sample_wo
                FROM `tabWork Order` wo
                INNER JOIN `tabProduction Plan Sales Order` pps ON pps.parent = wo.production_plan
                {so_order_join}
                LEFT JOIN (
                    SELECT se.work_order, SUM(IFNULL(sed.qty, 0)) as se_produced_qty
                    FROM `tabStock Entry` se
                    INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                    WHERE se.docstatus = 1
                      AND IFNULL(se.work_order, '') != ''
                      AND IFNULL(sed.is_finished_item, 0) = 1
                    GROUP BY se.work_order
                ) se_map ON se_map.work_order = wo.name
                WHERE pps.sales_order IN ({format_string_so})
                  AND wo.docstatus < 2
                  AND pps.docstatus < 2
                  AND IFNULL(wo.production_item, '') != ''
                GROUP BY pps.sales_order, wo.production_item{so_order_group}
            """, tuple(so_names), as_dict=True)
            
            result["maps"]["so_item_code_wos"] = so_item_prod_rows
            
            # Try exact lookups
            for row in so_item_prod_rows:
                so_key = (row.get("sales_order") or "").strip()
                item_key = (row.get("item_code") or "").strip()
                order_key = (row.get("so_order_code") or "").strip()
                
                if so_key == so and item_key == item_code:
                    result["debug"].append(f"✓ Found SO+item match: {so_key}::{item_key}")
                    if order_key == order_code:
                        result["debug"].append(f"✓ Order code matches: {order_code}")
                        result["resolved_qty"] = flt(row.get("produced_qty"))
                    elif order_key:
                        result["debug"].append(f"✗ Order code mismatch: expected='{order_code}', got='{order_key}'")
                    else:
                        result["debug"].append(f"✓ No SO order_code, using SO+item fallback")
                        result["resolved_qty"] = flt(row.get("produced_qty"))
        
        result["status"] = "success"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()
    
    return result

@frappe.whitelist()
def revert_items_from_pb(item_names):
    """
    Reverts Planning Sheet Items from the Production Board.
    Moves items back from PB sheets to original Color Chart sheets,
    and cleans up empty PB sheets afterward.
    """
    import json
    if isinstance(item_names, str):
        item_names = json.loads(item_names)
    
    if not item_names:
        return {"status": "error", "message": "No items provided"}

    count = 0

    for name in item_names:
        try:
            parent = frappe.db.get_value("Planning Table", name, "parent")
            if not parent:
                continue
            
            parent_doc = frappe.get_doc("Planning sheet", parent)
            
            # Clear Item-level Planned Date
            if frappe.db.has_column("Planning Table", "planned_date"):
                frappe.db.set_value("Planning Table", name, "planned_date", None)
            
            # If the parent has custom_pb_plan_name (it's a PB sheet), move item back
            # to an original CC sheet (one without custom_pb_plan_name)
            if parent_doc.get("custom_pb_plan_name"):
                eff_date = str(parent_doc.get("custom_planned_date") or parent_doc.ordered_date)
                party = parent_doc.party_code or ""
                
                # Find the original CC sheet for this party+date (no pb_plan_name)
                orig_sheets = frappe.get_all("Planning sheet", filters={
                    "ordered_date": eff_date,
                    "party_code": party,
                    "custom_pb_plan_name": ["in", ["", None]],
                    "docstatus": ["<", 2]
                }, fields=["name"], limit=1)
                
                if orig_sheets:
                    orig_name = orig_sheets[0].name
                else:
                    so_existing = _find_existing_sheet_for_sales_order(parent_doc.sales_order) if parent_doc.sales_order else None
                    if so_existing:
                        orig_name = so_existing["name"]
                    else:
                        # Create new CC sheet only when no sheet exists for this SO
                        orig = frappe.new_doc("Planning sheet")
                        orig.custom_plan_name = parent_doc.get("custom_plan_name") or "Default"
                        orig.ordered_date = eff_date
                        orig.party_code = party
                        orig.customer = _resolve_customer_link(parent_doc.customer, parent_doc.party_code)
                        orig.sales_order = parent_doc.sales_order or ""
                        orig.insert(ignore_permissions=True)
                        orig_name = orig.name
                
                # Move item back to original sheet
                frappe.db.set_value("Planning Table", name, "parent", orig_name)
                frappe.db.set_value("Planning Table", name, "parenttype", "Planning sheet")
                frappe.db.set_value("Planning Table", name, "parentfield", _get_pt_parentfield())
                
                # Delete PB sheet if now empty
                remaining = frappe.db.count("Planning Table", {"parent": parent})
                if remaining == 0:
                    try:
                        frappe.delete_doc("Planning sheet", parent, ignore_permissions=True, force=True)
                    except Exception:
                        pass
            else:
                # Not on a PB sheet - just clear the planned fields
                frappe.db.set_value("Planning sheet", parent, "custom_pb_plan_name", "")
                if _has_planned_date_column():
                    frappe.db.set_value("Planning sheet", parent, "custom_planned_date", None)
            
            count += 1
        except Exception as e:
            frappe.log_error(f"revert_items_from_pb error for {name}: {e}", "Revert from PB")

    frappe.db.commit()
    return {"status": "success", "reverted_items": count}


@frappe.whitelist()
def sync_custom_fields():
    """
    Creates the planned_date field on Planning Sheet Item and other key fields.
    Run this once from the browser console.
    """
    create_plan_name_field()

    # Check if custom field exists
    if not frappe.db.exists("Custom Field", {"dt": "Planning Table", "fieldname": "planned_date"}):
        doc = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning Table",
            "fieldname": "planned_date",
            "label": "Planned Date",
            "fieldtype": "Date",
            "insert_after": "unit"
        })
        doc.insert(ignore_permissions=True)

    # Item-level Production Plan link for exact View Plan routing
    if not frappe.db.exists("Custom Field", {"dt": "Planning Table", "fieldname": "custom_production_plan"}):
        pp_cf = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning Table",
            "fieldname": "custom_production_plan",
            "label": "Production Plan",
            "fieldtype": "Link",
            "options": "Production Plan",
            "insert_after": "plan_name",
            "read_only": 1,
            "in_list_view": 1,
            "columns": 2,
        })
        pp_cf.insert(ignore_permissions=True)

    # Ensure the field is visible for legacy setups where it may exist but be hidden/misplaced.
    try:
        cf_name = frappe.db.get_value("Custom Field", {"dt": "Planning Table", "fieldname": "custom_production_plan"}, "name")
        if cf_name:
            frappe.db.set_value("Custom Field", cf_name, "hidden", 0)
            frappe.db.set_value("Custom Field", cf_name, "insert_after", "plan_name")
            frappe.db.set_value("Custom Field", cf_name, "in_list_view", 1)
            frappe.db.set_value("Custom Field", cf_name, "columns", 2)
            frappe.db.set_value("Custom Field", cf_name, "read_only", 1)
    except Exception:
        pass

    frappe.db.commit()
    return "Custom fields synced successfully."


@frappe.whitelist()
def backfill_item_level_production_plan_links(planning_sheet_name=None):
    """Backfill Planning Sheet Item -> Production Plan links for legacy data."""
    frappe.only_for("System Manager")

    psi_pp_field = _psi_production_plan_field()
    psi_order_sheet_field = _psi_order_sheet_field()
    if not psi_pp_field and not psi_order_sheet_field:
        return {"status": "error", "message": "Planning Sheet Item production plan field not found. Run sync_custom_fields first."}

    filters = {}
    if planning_sheet_name:
        filters["parent"] = planning_sheet_name

    rows = frappe.get_all(
        "Planning Table",
        filters=filters,
        fields=["name", "parent", "sales_order_item", "custom_sales_order_item"],
        limit_page_length=0,
    )

    linked = 0
    unresolved = 0

    for r in rows:
        existing_pp = _get_item_level_production_plan(r.name)
        if existing_pp:
            continue

        so_item = r.get("sales_order_item") or r.get("custom_sales_order_item")
        pp_id = _resolve_pp_by_sales_order_item(so_item) if so_item else None

        if not pp_id:
            # Fallback to header-level PP field
            pp_id = frappe.db.get_value("Planning sheet", r.parent, "custom_production_plan") if frappe.db.has_column("Planning sheet", "custom_production_plan") else None
            if (not pp_id) and frappe.db.has_column("Planning sheet", "production_plan"):
                pp_id = frappe.db.get_value("Planning sheet", r.parent, "production_plan")

        if pp_id:
            if psi_pp_field:
                frappe.db.set_value("Planning Table", r.name, psi_pp_field, pp_id)
            if psi_order_sheet_field and psi_order_sheet_field != psi_pp_field:
                frappe.db.set_value("Planning Table", r.name, psi_order_sheet_field, pp_id)
            linked += 1
        else:
            unresolved += 1

    frappe.db.commit()
    return {
        "status": "success",
        "linked": linked,
        "unresolved": unresolved,
        "scanned": len(rows),
        "fields": [f for f in [psi_pp_field, psi_order_sheet_field] if f],
    }


@frappe.whitelist()
def diagnose_sales_order_planning_sheets(sales_order):
    """Diagnostic helper for singleton enforcement and legacy duplicates."""
    if not sales_order:
        return {"status": "error", "message": "sales_order is required"}

    sheets = frappe.get_all(
        "Planning sheet",
        filters={"sales_order": sales_order},
        fields=["name", "docstatus", "creation", "custom_plan_name", "custom_pb_plan_name"],
        order_by="creation asc",
        limit_page_length=0,
    )
    return {
        "status": "success",
        "sales_order": sales_order,
        "count": len(sheets),
        "sheets": sheets,
    }


@frappe.whitelist()
def revert_items_to_last_sheet_planned_date(
    from_months=None,
    to_month=None,
    unit=None,
    dry_run=1,
):
    """
    Revert item-level planned dates (planned_date) back to the best
    recoverable prior date when items were accidentally shifted across months.

    Default use-case:
    - Source (original) months: Feb + Mar
    - Wrong target month: Apr

    Args:
        from_months: list/int/str month numbers considered original (default: [2, 3])
        to_month: wrong month number to revert from (default: 4)
        unit: optional unit filter (e.g., "Unit 2")
        dry_run: 1 to preview, 0 to apply
    """
    try:
        frappe.only_for("System Manager")

        if not frappe.db.has_column("Planning Table", "planned_date"):
            return {"status": "error", "message": "planned_date column not found"}

        src_months = from_months
        if src_months in (None, "", []):
            src_months = [2, 3]
        elif isinstance(src_months, str):
            # Accept "2,3" or "[2,3]"
            s = src_months.strip().strip("[]")
            src_months = [int(x.strip()) for x in s.split(",") if x.strip()]
        elif isinstance(src_months, int):
            src_months = [src_months]
        else:
            src_months = [int(x) for x in src_months]

        bad_month = int(to_month or 4)
        dry = cint(dry_run) == 1

        placeholders = ",".join(["%s"] * len(src_months))

        unit_sql = ""
        query_params = [bad_month] + src_months + src_months
        if unit:
            unit_sql = " AND COALESCE(i.unit, '') = %s"
            query_params.append(unit)

        # Candidate rows:
        # - item currently in bad month (e.g., April)
        # - parent indicates original month either through ordered_date OR custom_planned_date
        #   (ordered_date branch catches cases where header custom_planned_date got overwritten)
        candidates = frappe.db.sql(
            f"""
            SELECT
                i.name,
                i.parent,
                i.unit,
                i.planned_date AS current_item_date,
                p.custom_planned_date AS sheet_planned_date,
                p.ordered_date,
                p.custom_pb_plan_name,
                p.custom_plan_name
            FROM `tabPlanning Table` i
            INNER JOIN `tabPlanning sheet` p ON p.name = i.parent
            WHERE p.docstatus < 2
              AND i.docstatus < 2
              AND i.planned_date IS NOT NULL
              AND MONTH(i.planned_date) = %s
              AND (
                    MONTH(COALESCE(p.ordered_date, p.custom_planned_date)) IN ({placeholders})
                    OR MONTH(COALESCE(p.custom_planned_date, p.ordered_date)) IN ({placeholders})
                  )
              {unit_sql}
            ORDER BY p.name, i.idx
            """,
            tuple(query_params),
            as_dict=True,
        )

        if not candidates:
            return {
                "status": "success",
                "dry_run": dry,
                "message": "No matching shifted items found.",
                "count": 0,
                "samples": [],
            }

        has_plan_code_col = frappe.db.has_column("Planning Table", "plan_name")
        updated = 0
        skipped = 0
        samples = []

        for r in candidates:
            # Prefer sheet_planned_date, but if it is also in the bad month,
            # fall back to ordered_date to restore pre-shift month position.
            restore_date = r.get("sheet_planned_date")
            if restore_date and getdate(restore_date).month == bad_month:
                restore_date = r.get("ordered_date")
            elif not restore_date:
                restore_date = r.get("ordered_date")

            if not restore_date:
                skipped += 1
                continue

            if getdate(restore_date).month == bad_month:
                skipped += 1
                continue

            row_preview = {
                "item": r.get("name"),
                "sheet": r.get("parent"),
                "unit": r.get("unit"),
                "from": str(r.get("current_item_date")),
                "to": str(restore_date),
            }
            if len(samples) < 100:
                samples.append(row_preview)

            if dry:
                continue

            if has_plan_code_col:
                plan_name_for_code = r.get("custom_pb_plan_name") or r.get("custom_plan_name") or "Default"
                new_code = generate_plan_code(str(restore_date), r.get("unit") or "Unit 1", plan_name_for_code)
                frappe.db.sql(
                    """
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s,
                        plan_name = %s
                    WHERE name = %s
                    """,
                    (restore_date, new_code, r.get("name")),
                )
            else:
                frappe.db.sql(
                    """
                    UPDATE `tabPlanning Table`
                    SET planned_date = %s
                    WHERE name = %s
                    """,
                    (restore_date, r.get("name")),
                )
            updated += 1

        if not dry:
            frappe.db.commit()

        return {
            "status": "success",
            "dry_run": dry,
            "count": len(candidates),
            "updated": updated,
            "skipped": skipped,
            "samples": samples,
            "message": "Preview generated" if dry else f"Reverted {updated} items to previous sheet planned date",
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "revert_items_to_last_sheet_planned_date")
        return {"status": "error", "message": "Rollback failed. See Error Log."}


@frappe.whitelist()
def delete_pb_plan(pb_plan_name, date=None, start_date=None, end_date=None):
    """
    Removes Production Board plan assignment from Planning Sheets.
    Does NOT delete the sheets ΓÇö just clears custom_pb_plan_name.
    """
    if not pb_plan_name:
        return {"status": "error", "message": "Plan name required"}
    
    eff = _effective_date_expr("p")
    
    if start_date and end_date:
        query_start = frappe.utils.getdate(start_date)
        query_end = frappe.utils.getdate(end_date)
        date_condition = f"{eff} BETWEEN %s AND %s"
        params = [query_start, query_end]
    elif date:
        target_date = frappe.utils.getdate(date)
        date_condition = f"{eff} = %s"
        params = [target_date]
    else:
        return {"status": "error", "message": "Date filter required"}
    
    params.append(pb_plan_name)
    
    result = frappe.db.sql(f"""
        UPDATE `tabPlanning sheet` p
        SET p.custom_pb_plan_name = ''
        WHERE {date_condition} AND p.docstatus < 2 AND p.custom_pb_plan_name = %s
    """, tuple(params))
    
    affected = frappe.db.sql("SELECT ROW_COUNT() as cnt")[0][0]

    # Remove from persistent plans
    persisted = get_persisted_plans("production_board")
    persisted = [p for p in persisted if p["name"] != pb_plan_name]
    import json
    frappe.defaults.set_global_default("production_scheduler_production_board_plans", json.dumps(persisted))

    frappe.db.commit()
    return {"status": "success", "cleared_count": affected}


@frappe.whitelist()
def emergency_cleanup_all_pushed_status():
    """
    ONE-CLICK CLEANUP: 
    Finds every Planning Sheet and Item that is marked as 'Pushed' 
    and strips the flags so they appear back in the Color Chart.
    """
    # 1. Clear Sheet-level flags
    frappe.db.sql("""
        UPDATE `tabPlanning sheet` 
        SET custom_pb_plan_name = NULL, custom_planned_date = NULL 
        WHERE custom_pb_plan_name IS NOT NULL AND custom_pb_plan_name != ''
    """)
    
    # 2. Clear Item-level flags
    # We exclude items with WHITE colors to avoid erasing auto-planned white orders
    clean_white_sql = ", ".join([f"'{c.upper()}'" for c in WHITE_COLORS])
    frappe.db.sql(f"""
        UPDATE `tabPlanning Table` 
        SET planned_date = NULL, plan_name = NULL
        WHERE (planned_date IS NOT NULL OR plan_name IS NOT NULL)
          AND UPPER(color) NOT IN ({clean_white_sql})
    """)
    
    frappe.db.commit()
    return {"status": "success", "message": "All color orders unlocked and returned to Color Chart. White orders preserved."}

@frappe.whitelist()
def fix_recently_cleared_whites():
    """
    TEMPORARY: Restores white orders that were accidentally cleared.
    Sets custom_planned_date = ordered_date for sheets with AT LEAST ONE white item
    that was recently modified.
    """
    from frappe.utils import getdate
    sheets = frappe.db.sql("""
        SELECT name, ordered_date, custom_planned_date, custom_pb_plan_name FROM `tabPlanning sheet`
        WHERE modified > DATE_SUB(NOW(), INTERVAL 4 HOUR)
    """, as_dict=True)
    
    count = 0
    for s in sheets:
        items = frappe.get_all("Planning Table", 
                               filters={"parent": s.name}, 
                               fields=["name", "color", "planned_date"])
        
        has_white = False
        restored_item_count = 0
        
        for it in items:
            if _is_white_color(it.color):
                has_white = True
                # Bring back the item date if it was cleared
                if not it.planned_date:
                    frappe.db.set_value("Planning Table", it.name, "planned_date", s.ordered_date)
                    restored_item_count += 1
        
        if has_white:
            updates = {}
            # Restore sheet date if missing
            if not s.custom_planned_date:
                updates["custom_planned_date"] = s.ordered_date
            
            # Ensure plan name is canonical for the month
            if not s.custom_pb_plan_name or s.custom_pb_plan_name == "Default":
                month_names = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"]
                d = getdate(s.ordered_date)
                prefix = f"{month_names[d.month-1]} {str(d.year)[2:]}"
                best_plan = f"{prefix} PLAN 1"
                
                # Use "Default" only if PLAN 1 doesn't exist anywhere
                if not frappe.db.exists("Planning sheet", {"custom_pb_plan_name": best_plan}):
                    best_plan = "Default"
                
                updates["custom_pb_plan_name"] = best_plan
            
            if updates:
                frappe.db.set_value("Planning sheet", s.name, updates)
                count += 1
            elif restored_item_count > 0:
                # Even if sheet header was okay, we restored item dates
                count += 1
                
    frappe.db.commit()
    return {"status": "success", "restored_count": count}

@frappe.whitelist()
def revert_items_to_color_chart(item_names):
    """
    Reverts items back to the Color Chart by clearing their Planning Sheet's custom_planned_date.
    Note: This affects the entire Planning Sheet containing the item.
    White orders generally re-evaluate to have a planned date implicitly, 
    but this clears the explicit field.
    """
    import json
    if isinstance(item_names, str):
        item_names = json.loads(item_names)

    if not item_names:
        return {"status": "error", "message": "No items provided"}

    updated_sheets = set()
    for name in item_names:
        try:
            # 1. Clean item-level tracking explicitly
            if frappe.db.has_column("Planning Table", "planned_date"):
                frappe.db.sql("""
                    UPDATE `tabPlanning Table`
                    SET planned_date = NULL, plan_name = NULL
                    WHERE name = %s
                """, (name,))

            # 2. Check if parent sheet should be unlinked from PB
            parent = frappe.db.get_value("Planning Table", name, "parent")
            if parent and parent not in updated_sheets:
                # Only clear parent-level tracking if NO OTHER items in this sheet are still pushed
                still_pushed = frappe.db.sql("""
                    SELECT COUNT(*) FROM `tabPlanning Table`
                    WHERE parent = %s AND planned_date IS NOT NULL
                """, (parent,))[0][0]
                
                if still_pushed == 0:
                    frappe.db.sql("""
                        UPDATE `tabPlanning sheet`
                        SET custom_planned_date = NULL, custom_pb_plan_name = NULL
                        WHERE name = %s
                    """, (parent,))
                
                updated_sheets.add(parent)
        except Exception as e:
            frappe.log_error(f"revert error for {name}: {e}", "Revert to Color Chart")

    frappe.db.commit()
    return {"status": "success", "reverted_items": len(item_names), "sheets_checked": len(updated_sheets)}


@frappe.whitelist()
def revert_pb_push(pb_plan_name, date=None):
    """
    Reverts a Production Board push for a specific date.
    Moves all items from PB Planning Sheets back to their original Color Chart sheets,
    then deletes the (now empty) PB sheets.
    """
    if not pb_plan_name:
        return {"status": "error", "message": "Plan name required"}

    target_date = frappe.utils.getdate(date) if date else None

    filters = {
        "custom_pb_plan_name": pb_plan_name,
        "docstatus": ["<", 2]
    }
    if target_date:
        # Search by the date it was PUSHED to, not the original SO date
        filters["custom_planned_date"] = target_date

    pb_sheets = frappe.get_all("Planning sheet", filters=filters, fields=["name", "ordered_date", "party_code", "custom_plan_name", "sales_order"])

    reverted = 0
    for pb_sheet in pb_sheets:
        # Find the original Color Chart sheet for same date + party_code (no pb_plan_name)
        original_filters = {
            "ordered_date": pb_sheet.ordered_date,
            "custom_pb_plan_name": ["in", ["", None]],
            "docstatus": ["<", 2]
        }
        if pb_sheet.party_code:
            original_filters["party_code"] = pb_sheet.party_code
        if pb_sheet.custom_plan_name:
            original_filters["custom_plan_name"] = pb_sheet.custom_plan_name

        originals = frappe.get_all("Planning sheet", filters=original_filters, fields=["name"], limit=1)

        if originals:
            original_sheet_name = originals[0].name
        else:
            so_existing = _find_existing_sheet_for_sales_order(pb_sheet.sales_order) if pb_sheet.sales_order else None
            if so_existing:
                original_sheet_name = so_existing["name"]
            else:
                # Create a blank original sheet only when no SO-linked sheet exists
                orig_sheet = frappe.new_doc("Planning sheet")
                orig_sheet.custom_plan_name = pb_sheet.custom_plan_name or "Default"
                orig_sheet.ordered_date = pb_sheet.ordered_date
                orig_sheet.party_code = pb_sheet.party_code or ""
                orig_sheet.sales_order = pb_sheet.sales_order or ""
                orig_sheet.insert(ignore_permissions=True)
                original_sheet_name = orig_sheet.name

        # Move all items from PB sheet back to original sheet
        items = frappe.get_all("Planning Table", filters={"parent": pb_sheet.name}, fields=["name"])
        for item in items:
            frappe.db.set_value("Planning Table", item.name, "parent", original_sheet_name)
            frappe.db.set_value("Planning Table", item.name, "parenttype", "Planning sheet")
            frappe.db.set_value("Planning Table", item.name, "parentfield", _get_pt_parentfield())
            reverted += 1

        # Delete the now-empty PB sheet
        frappe.delete_doc("Planning sheet", pb_sheet.name, ignore_permissions=True, force=True)

    frappe.db.commit()
    return {"status": "success", "reverted": reverted, "sheets_removed": len(pb_sheets)}

# ------------------------------------------------------------
# AUTO-CREATE PLANNING SHEET (BACKGROUND EXECUTION)
# ------------------------------------------------------------

def auto_create_planning_sheet(doc, method=None):
    """Create a Planning Sheet for a Sales Order.
    - Uses the first unlocked Color Chart plan.
    - If *all* plans are locked, aborts creation (no default fallback).
    - Does NOT set `custom_planned_date`; it will be filled when the sheet is pushed to the Production Board.
    """
    # 1. FETCH UNLOCKED PLAN
    parsed = get_persisted_plans("color_chart")
    cc_plan = _find_best_unlocked_plan(parsed, doc.transaction_date)

    if not cc_plan:
        # All plans are locked - do not create a sheet
        plan_summary = ", ".join([f"{p.get('name')}(L:{p.get('locked')})" for p in parsed if isinstance(p, dict)])
        frappe.msgprint(f"⚠️ All Color Chart plans are locked - Planning Sheet not created. Plans found: {plan_summary}", indicator="orange", alert=True)
        return None

    # 2. STRICT SINGLETON RULE:
    # Once a sheet exists for an SO, never create another unless the sheet is deleted.
    existing = _find_existing_sheet_for_sales_order(doc.name)

    if existing:
        sheet = frappe.get_doc("Planning sheet", existing["name"])
        new_ctx_name = _get_contextual_plan_name(cc_plan, doc.transaction_date)
        
        # Reuse existing draft only; submitted/cancelled sheets are never duplicated.
        if int(sheet.docstatus or 0) == 0:
            if sheet.custom_plan_name != new_ctx_name:
                sheet.custom_plan_name = new_ctx_name
                sheet.db_set("custom_plan_name", new_ctx_name)

            if not (sheet.get("party_code") or "").strip():
                generate_party_code(sheet)

            _populate_planning_sheet_items(sheet, doc)
            update_sheet_plan_codes(sheet, include_legacy=True)
            sheet.save(ignore_permissions=True)
            frappe.db.commit()
            _sync_lamination_fabric_planning_rows(sheet.name)

        frappe.msgprint(f"Planning Sheet <b>{sheet.name}</b> already exists for Sales Order <b>{doc.name}</b>. Reusing existing sheet.")
        return sheet

    # 3. CREATE PLANNING SHEET (party_code / order code: MonthLetter+YY+NNN, writeback to SO)
    ps = frappe.new_doc("Planning sheet")
    ps.sales_order = doc.name
    ps.customer = _resolve_customer_link(doc.customer, doc.get("party_code"))
    generate_party_code(ps)
    ps.ordered_date = doc.transaction_date
    ps.dod = doc.delivery_date
    ps.planning_status = "Draft"
    # Use contextual name for the custom_plan_name
    ps.custom_plan_name = _get_contextual_plan_name(cc_plan, doc.transaction_date)
    ps.custom_pb_plan_name = ""
    # NOTE: Do NOT set custom_planned_date here — it would make Color Chart show
    # color orders as "pushed". White items have planned_date set by
    # _populate_planning_sheet_items, and the SQL filter finds them via EXISTS.

    _populate_planning_sheet_items(ps, doc)
    
    update_sheet_plan_codes(ps, include_legacy=True)

    if not ps.get("quality"):
        ps.quality = "Standard"

    ps.flags.ignore_permissions = True
    ps.insert()
    frappe.db.commit()

    # 4. Link board rows to legacy rows (source_item), then lamination fabric rows
    _link_board_planned_rows_to_legacy_items(ps.name)
    _sync_lamination_fabric_planning_rows(ps.name)
            
    frappe.msgprint(f"✅ Planning Sheet <b>{ps.name}</b> created in unlocked plan <b>{ps.custom_plan_name}</b> and synchronized.")
    
    # RE-FETCH TO UPDATE HEADER PLAN CODES ΓÇö ONLY ITEMS ENABLED, HEADER DISABLED PER USER REQUEST
    final_doc = frappe.get_doc("Planning sheet", ps.name)
    update_sheet_plan_codes(final_doc, include_legacy=True)
    # frappe.db.set_value("Planning sheet", ps.name, "custom_plan_code", final_doc.custom_plan_code)
    
    return final_doc

# ------------------------------------------------------------
# REGENERATE PLANNING SHEET (MANUAL RE-CREATION)
# ------------------------------------------------------------

@frappe.whitelist()
def regenerate_planning_sheet(so_name):
    """Regenerate a Planning Sheet for a Sales Order.
    - Fails if an active sheet already exists.
    - Uses the first unlocked Color Chart plan; aborts if all locked.
    - Does NOT set `custom_planned_date` on creation.
    """
    if not so_name:
        frappe.throw("Sales Order Name is required")

    existing_sheet = _find_existing_sheet_for_sales_order(so_name)
    if existing_sheet:
        frappe.throw(
            f"Planning Sheet <b>{existing_sheet['name']}</b> already exists for Sales Order <b>{so_name}</b>. "
            "Delete it first, then regenerate."
        )

    doc = frappe.get_doc("Sales Order", so_name)

    # 1. FETCH UNLOCKED PLAN (same logic as auto_create)
    parsed = get_persisted_plans("color_chart")
    cc_plan = _find_best_unlocked_plan(parsed, doc.transaction_date)

    if not cc_plan:
        plan_summary = ", ".join([f"{p.get('name')}(L:{p.get('locked')})" for p in parsed if isinstance(p, dict)])
        frappe.msgprint(f"⚠️ All Color Chart plans are locked - cannot regenerate Planning Sheet. Plans found: {plan_summary}", indicator="orange", alert=True)
        return None

    # 2. CREATE PLANNING SHEET (order code generation + SO writeback)
    ps = frappe.new_doc("Planning sheet")
    ps.sales_order = doc.name
    ps.customer = _resolve_customer_link(doc.customer, doc.get("party_code"))
    generate_party_code(ps)
    ps.ordered_date = doc.transaction_date
    ps.dod = doc.delivery_date
    ps.planning_status = "Draft"
    ps.custom_plan_name = _get_contextual_plan_name(cc_plan, doc.transaction_date)
    ps.custom_pb_plan_name = ""

    _populate_planning_sheet_items(ps, doc)
    
    update_sheet_plan_codes(ps, include_legacy=True)

    if not ps.get("quality"):
        ps.quality = "Standard"

    ps.flags.ignore_permissions = True
    ps.insert()
    frappe.db.commit()

    _link_board_planned_rows_to_legacy_items(ps.name)
    _sync_lamination_fabric_planning_rows(ps.name)

    frappe.msgprint(f"✅ Regenerated Planning Sheet <b>{ps.name}</b> and synchronized.")
    return ps


@frappe.whitelist()
def run_global_cleanup():
    """
    Two-phase global cleanup:
    Phase 1 — Remove duplicate Planning Sheet headers per Sales Order (keeps OLDEST).
    Phase 2 — Remove duplicate Planning Sheet Items (if field exists).
    """
    frappe.only_for("System Manager")

    removed_sheets = 0
    removed_items = 0
    sheet_details = []

    # —— PHASE 1: Deduplicate Planning Sheet HEADERS per Sales Order —————
    all_sheets = frappe.get_all(
        "Planning sheet",
        filters={"sales_order": ["is", "set"], "docstatus": ["<", 2]},
        fields=["name", "sales_order", "creation"],
        order_by="creation asc",
        ignore_permissions=True,
        page_length=99999
    )

    so_sheet_map = {}
    for sh in all_sheets:
        so = sh.get("sales_order") or ""
        if not so:
            continue
        so_sheet_map.setdefault(so, []).append(sh)

    for so, sheets in so_sheet_map.items():
        if len(sheets) <= 1:
            continue

        keep_sheet = sheets[0].name
        dup_sheet_names = [s.name for s in sheets[1:]]

        for dup_name in dup_sheet_names:
            # Move items from duplicate to kept sheet using raw SQL
            frappe.db.sql(
                "UPDATE `tabPlanning Table` SET parent = %s WHERE parent = %s",
                (keep_sheet, dup_name)
            )
            # PROPER DELETE: Use frappe.delete_doc to clean up child table records
            frappe.delete_doc("Planning sheet", dup_name, force=1, ignore_permissions=True)
            removed_sheets += 1

        sheet_details.append({
            "sales_order": so,
            "kept_sheet": keep_sheet,
            "removed_sheets": dup_sheet_names
        })

    # —— PHASE 2: Deduplicate Planning Sheet ITEMS by name within same parent ——
    dup_items_in_sheet = frappe.db.sql("""
        SELECT parent, item_name, COUNT(*) AS cnt
        FROM `tabPlanning Table`
        GROUP BY parent, item_name, qty
        HAVING COUNT(*) > 1
    """, as_dict=True)

    for row in dup_items_in_sheet:
        items = frappe.db.sql("""
            SELECT name FROM `tabPlanning Table`
            WHERE parent = %s AND item_name = %s AND qty = 0
            ORDER BY creation ASC
        """, (row.parent, row.item_name), as_dict=True)

        if not items:
            items = frappe.db.sql("""
                SELECT name FROM `tabPlanning Table`
                WHERE parent = %s AND item_name = %s
                ORDER BY creation ASC
            """, (row.parent, row.item_name), as_dict=True)

        if len(items) > 1:
            for it in items[1:]:
                frappe.db.sql("DELETE FROM `tabPlanning Table` WHERE name = %s", (it.name,))
                removed_items += 1

    frappe.db.commit()
    return {
        "status": "success",
        "removed_sheets_count": removed_sheets,
        "removed_items_count": removed_items,
        "sheet_details": sheet_details
    }


@frappe.whitelist()
def normalize_planning_sheet_customer_link(doc, method=None):
    """Normalize customer link on Planning sheet docs to valid Customer name."""
    if not doc:
        return

    current_customer = (doc.get("customer") or "").strip()
    party_code = (doc.get("party_code") or "").strip()
    resolved = _resolve_customer_link(current_customer, party_code)

    if resolved != current_customer:
        doc.customer = resolved


@frappe.whitelist()
def repair_planning_sheet_customer_links(limit_page_length=0, dry_run=0):
    """One-time repair: convert invalid Planning sheet.customer values to valid Customer IDs."""
    limit_page_length = cint(limit_page_length or 0)
    dry_run = cint(dry_run or 0)

    rows = frappe.get_all(
        "Planning sheet",
        filters={"docstatus": ["<", 2]},
        fields=["name", "customer", "party_code"],
        limit_page_length=limit_page_length,
    )

    scanned = 0
    updated = 0
    cleared = 0
    skipped = 0
    samples = []

    for r in rows:
        scanned += 1
        current_customer = (r.get("customer") or "").strip()
        party_code = (r.get("party_code") or "").strip()

        if not current_customer:
            skipped += 1
            continue

        resolved = _resolve_customer_link(current_customer, party_code)

        if resolved == current_customer:
            skipped += 1
            continue

        if dry_run:
            samples.append({"name": r.get("name"), "from": current_customer, "to": resolved})
            if resolved:
                updated += 1
            else:
                cleared += 1
            continue

        frappe.db.set_value("Planning sheet", r.get("name"), "customer", resolved or "")
        if resolved:
            updated += 1
        else:
            cleared += 1

    if not dry_run:
        frappe.db.commit()

    return {
        "status": "success",
        "scanned": scanned,
        "updated": updated,
        "cleared": cleared,
        "skipped": skipped,
        "dry_run": bool(dry_run),
        "samples": samples[:50],
    }


@frappe.whitelist()
def validate_planning_sheet_duplicates(doc, method=None):
    """
    Prevents saving a Planning Sheet if another UNLOCKED sheet 
    already exists for the same Sales Order.
    """
    normalize_planning_sheet_customer_link(doc)

    if not doc.sales_order:
        return
        
    # Recalculate plan codes whenever saved
    update_sheet_plan_codes(doc)

    # Strict singleton: block any second sheet for the same Sales Order.
    filters = {
        "sales_order": doc.sales_order,
        "name": ["!=", doc.name],
    }
    existing = frappe.get_all("Planning sheet", filters=filters, fields=["name"], limit=1)
    if existing:
        frappe.throw(
            _(
                f"A Planning Sheet <b>{existing[0].name}</b> already exists for Sales Order <b>{doc.sales_order}</b>. "
                "Delete the existing sheet first before creating a new one."
            )
        )


def sync_work_order_custom_production_plan(doc, method=None):
    """Keep Work Order.custom_production_plan in sync with production_plan when the custom field exists.

    Many sites filter list views by custom_production_plan; ERPNext only fills production_plan.
    Without mirroring, filters show no rows even when WOs exist.
    """
    try:
        if not frappe.db.has_column("tabWork Order", "custom_production_plan"):
            return
        pp = (doc.get("production_plan") or "").strip()
        if not pp:
            return
        if not (doc.get("custom_production_plan") or "").strip():
            doc.custom_production_plan = pp
    except Exception:
        pass


def normalize_work_order_pending_status(doc, method=None):
    """
    Defensive normalization: ERPNext Work Order does not allow status "Pending".
    Some custom flows submit linked docs while status is still "Pending", which
    triggers a validation error. Coerce to a valid baseline status.
    """
    try:
        current_status = (doc.get("status") or "").strip()
        if current_status and current_status.lower() == "pending":
            doc.status = "Not Started"
    except Exception:
        pass


def normalize_linked_work_orders_for_spr(doc, method=None):
    """
    Prevent intermittent submit popups on SPR when linked Work Orders carry an
    invalid transient status value "Pending". Normalize to ERP-valid value.
    """
    try:
        pp_id = (doc.get("production_plan") or "").strip()
        if not pp_id or not frappe.db.exists("DocType", "Work Order"):
            return

        wo_names = frappe.get_all(
            "Work Order",
            filters={"production_plan": pp_id, "docstatus": ["<", 2]},
            pluck="name",
        ) or []
        if not wo_names:
            return

        for wo_name in wo_names:
            wo_status = (frappe.db.get_value("Work Order", wo_name, "status") or "").strip().lower()
            if wo_status == "pending":
                frappe.db.set_value("Work Order", wo_name, "status", "Not Started", update_modified=True)
    except Exception:
        # Keep SPR flow safe; this is a defensive normalization only.
        pass


@frappe.whitelist()
def force_merge_order_sheets(sales_order):
    """
    Administrative tool to merge all Planning Sheets for a specific Sales Order into the newest one.
    """
    frappe.only_for("System Manager")
    
    sheets = frappe.get_all("Planning sheet", 
        filters={"sales_order": sales_order, "docstatus": ["<", 2]},
        fields=["name", "creation"],
        order_by="creation desc"
    )
    
    if len(sheets) <= 1:
        return {"status": "success", "message": "No duplicates found."}
    
    target_sheet = sheets[0].name
    source_sheets = [s.name for s in sheets[1:]]
    
    moved_count = 0
    for src in source_sheets:
        # Move items via SQL
        frappe.db.sql("UPDATE `tabPlanning Table` SET parent = %s WHERE parent = %s", (target_sheet, src))
        # Delete source sheet
        frappe.delete_doc("Planning sheet", src, force=1, ignore_permissions=True)
        moved_count += 1
        
    frappe.db.commit()
    return {"status": "success", "message": f"Merged {moved_count} sheets into {target_sheet}"}


@frappe.whitelist()
def fix_white_orders_planned_date():
    """
    One-time migration: For every Planning Sheet that:
      1. Has custom_planned_date NULL or empty
      2. Has at least one item ΓÇö and ALL items are white-family colors
    Set custom_planned_date = ordered_date.

    Returns a summary of how many sheets were updated.
    """
    # Get all sheets without custom_planned_date
    sheets_without_date = frappe.db.sql("""
        SELECT name, ordered_date
        FROM `tabPlanning sheet`
        WHERE (custom_planned_date IS NULL OR custom_planned_date = '')
          AND docstatus < 2
          AND ordered_date IS NOT NULL
    """, as_dict=True)

    updated = 0
    skipped = 0

    for sheet in sheets_without_date:
        items = frappe.get_all(
            "Planning Table",
            filters={"parent": sheet.name},
            fields=["color"]
        )

        if not items:
            skipped += 1
            continue

        # Check if ALL items are white-family colors
        if all(_is_white_color(i.color) for i in items):
            frappe.db.set_value(
                "Planning sheet",
                sheet.name,
                "custom_planned_date",
                sheet.ordered_date
            )
            updated += 1
        else:
            skipped += 1

    frappe.db.commit()
    return {
        "status": "success",
        "updated": updated,
        "skipped": skipped,
        "message": f"Γ£à Updated {updated} white Planning Sheet(s). Skipped {skipped} (color or no items)."
    }
@frappe.whitelist()
def revert_split_item(item_name):
    """
    Merges a split planning sheet item back into its original row within the same sheet.
    Useful for undoing partial pulls.
    Now also synchronizes the legacy 'Items' table if needed.
    """
    try:
        it = frappe.get_doc("Planning Table", item_name)
        
        # Find the 'original' or 'primary' item for this SO row in the same sheet
        candidates = frappe.get_all("Planning Table", 
            filters={
                "parent": it.parent,
                "sales_order_item": it.sales_order_item,
                "name": ["!=", it.name]
            },
            fields=["name", "qty", "is_split", "unit"],
            order_by="is_split asc, creation asc"
        )
        
        if not candidates:
            return {"status": "failed", "message": "No original item found to merge with."}
            
        target = candidates[0]
        new_qty = flt(target.qty) + flt(it.qty)

        # Update target and remove current in Planning Table
        frappe.db.sql("UPDATE `tabPlanning Table` SET qty = %s WHERE name = %s", (new_qty, target.name))
        frappe.db.sql("DELETE FROM `tabPlanning Table` WHERE name = %s", (it.name,))
        
        frappe.db.commit() # Ensure revert persists
        
        frappe.logger().info(f"[RevertSplit] Merged {it.name} ({it.qty}) into {target.name} ({target.qty} -> {new_qty})")
        
        return {"status": "success", "message": f"Merged {it.qty} back into original row."}
    except Exception as e:
        frappe.logger().error(f"[RevertSplit] Error: {str(e)}")
        return {"status": "failed", "message": str(e)}
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# MIX ROLL DATA PERSISTENCE
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

@frappe.whitelist()
def save_mix_roll_data(date_key, entries):
    """Save mix roll entries to a simple key-value store.
    date_key: string like '2026-03-03' or '2026-W10' or '2026-03'
    entries: JSON array of mix roll objects
    """
    if isinstance(entries, str):
        entries = json.loads(entries)

    # Use a simple SQL table to store mix roll data
    # Create table if not exists
    frappe.db.sql("""
        CREATE TABLE IF NOT EXISTS `mix_roll_store_data` (
            `name` VARCHAR(140) PRIMARY KEY,
            `date_key` VARCHAR(50) NOT NULL,
            `data` LONGTEXT,
            `modified` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY `idx_date_key` (`date_key`)
        )
    """)

    existing = frappe.db.sql(
        "SELECT name FROM `mix_roll_store_data` WHERE date_key = %s", date_key
    )

    data_json = json.dumps(entries, ensure_ascii=False)

    if existing:
        frappe.db.sql(
            "UPDATE `mix_roll_store_data` SET data = %s, modified = NOW() WHERE date_key = %s",
            (data_json, date_key)
        )
    else:
        import hashlib
        name = hashlib.md5(date_key.encode()).hexdigest()[:10]
        frappe.db.sql(
            "INSERT INTO `mix_roll_store_data` (name, date_key, data, modified) VALUES (%s, %s, %s, NOW())",
            (name, date_key, data_json)
        )

    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def get_mix_roll_data(date_key):
    """Load saved mix roll entries and sync weight/status from linked Stock Entries."""
    try:
        frappe.db.sql("SELECT 1 FROM `mix_roll_store_data` LIMIT 1")
    except Exception:
        return []

    rows = frappe.db.sql(
        "SELECT data FROM `mix_roll_store_data` WHERE date_key = %s", date_key
    )
    if not (rows and rows[0][0]):
        return []

    entries = json.loads(rows[0][0])
    updated = False
    
    # Sync weight from Stock Entries or SPRs if we have a reference
    for m in entries:
        se_name = m.get("stock_entry")
        spr_name = m.get("spr_name")
        
        # 1. Sync from Stock Entry (legacy/direct SE flow)
        if se_name:
            # 0=Draft, 1=Submitted, 2=Cancelled
            se_status = frappe.db.get_value("Stock Entry", se_name, "docstatus")
            
            # Sum of FG items in this Stock Entry
            se_qty = frappe.db.sql("""
                select sum(qty) from `tabStock Entry Detail` 
                where parent = %s and is_finished_item = 1
            """, se_name)[0][0] or 0.0
            
            # If submitted and weight matches, update Kg in Color Chart
            if se_status == 1 and flt(m.get("kg")) != flt(se_qty):
                m["kg"] = flt(se_qty)
                updated = True
            
            if se_status == 1 and not m.get("_submitted"):
                m["_submitted"] = True
                updated = True

        # 2. Sync from Shaft Production Run (New flow)
        if spr_name:
            res = frappe.db.get_value("Shaft Production Run", spr_name, ["docstatus", "total_produced_weight"], as_dict=True)
            if res:
                if res.docstatus == 1:
                    if not m.get("_submitted"):
                        m["_submitted"] = True
                        updated = True
                    # Sync weight if submitted
                    if flt(m.get("kg")) != flt(res.total_produced_weight):
                        m["kg"] = flt(res.total_produced_weight)
                        updated = True
                elif res.docstatus == 0:
                     # Even if not submitted, sync the current draft weight to the chart
                     if flt(m.get("kg")) != flt(res.total_produced_weight):
                        m["kg"] = flt(res.total_produced_weight)
                        updated = True
                elif res.docstatus == 2:
                    # If cancelled, unlock the row
                    if m.get("_submitted"):
                        m["_submitted"] = False
                        updated = True
            else:
                # SPR was DELETED. Clear the link so the Color Chart row unlocks and is available again.
                m["spr_name"] = None
                m["_submitted"] = False
                m["kg"] = 0.0
                updated = True

    if updated:
        save_mix_roll_data(date_key, json.dumps(entries))

    return entries


@frappe.whitelist()
def debug_plan_check():
    """Diagnostic: Check custom_plan_name field and data."""
    result = {}
    
    # 1. Check if column exists
    result["column_exists"] = frappe.db.has_column("Planning sheet", "custom_plan_name")
    
    # 2. Check Custom Field record
    result["custom_field_exists"] = frappe.db.exists("Custom Field", "Planning sheet-custom_plan_name")
    
    # 3. Show plan name distribution
    if result["column_exists"]:
        dist = frappe.db.sql("""
            SELECT COALESCE(custom_plan_name, '(NULL)') as plan_name, COUNT(*) as cnt
            FROM `tabPlanning sheet`
            GROUP BY custom_plan_name
            ORDER BY cnt DESC
        """, as_dict=True)
        result["plan_distribution"] = dist
    else:
        result["plan_distribution"] = "Column does not exist!"
    
    # 4. Show sheets in March 2026
    if result["column_exists"]:
        march_sheets = frappe.db.sql("""
            SELECT name, ordered_date, custom_plan_name, custom_planned_date, docstatus
            FROM `tabPlanning sheet`
            WHERE ordered_date BETWEEN '2026-03-01' AND '2026-03-31'
            ORDER BY ordered_date, custom_plan_name
            LIMIT 30
        """, as_dict=True)
        result["march_sheets"] = march_sheets
    
    return result


@frappe.whitelist()
def recalculate_all_plan_codes():
    """
    Bulk-recalculates and persists plan_name on Planning Table rows and header plan code.
    Does not write legacy Planning sheet Item rows (board is source of truth for plan codes).
    """
    create_plan_name_field()
    sheets = frappe.db.sql("""
        SELECT name FROM `tabPlanning sheet`
        WHERE docstatus < 2
        ORDER BY creation DESC
    """, as_dict=True)
    
    updated = 0
    failed = 0
    
    for row in sheets:
        try:
            doc = frappe.get_doc("Planning sheet", row.name)
            update_sheet_plan_codes(doc)
            if getattr(doc, "custom_plan_code", None):
                frappe.db.sql(
                    "UPDATE `tabPlanning sheet` SET custom_plan_code = %s WHERE name = %s",
                    (doc.custom_plan_code, doc.name),
                )
            for tf in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
                new_items = doc.get(tf)
                if new_items:
                    for i in new_items:
                        if i.get("plan_name"):
                            frappe.db.sql(
                                "UPDATE `tabPlanning Table` SET plan_name = %s WHERE name = %s",
                                (i.plan_name, i.name),
                            )
                    break
            updated += 1
        except Exception as e:
            frappe.log_error(f"Failed to recalculate plan code for {row.name}: {e}")
            failed += 1
    
    frappe.db.commit()
    return {"updated": updated, "failed": failed, "total": len(sheets)}

@frappe.whitelist()
def get_master_code(doctype, name, possible_fields):
    """Checks metadata and fetches the first existing code field."""
    if not name: return "000"
    try:
        if not frappe.db.exists("DocType", doctype):
            return "000"
        # Use get_meta to safely check field existence before querying
        meta = frappe.get_meta(doctype)
        valid_fields = [f.fieldname for f in meta.fields]
        for f in possible_fields:
            if f in valid_fields:
                val = frappe.db.get_value(doctype, name, f)
                if val: return str(val)
        return "000"
    except Exception:
        return "000"

def get_mix_item_details(quality, cl_type, gsm, shaft):
    """
    Parses 'shaft' for widths (e.g. '32+30') and generates details for EACH width.
    Returns a list of dicts.
    """
    # Extract all numbers from shaft string (e.g. "32+30" -> ["32", "30"])
    widths = re.findall(r'\d+', str(shaft))
    if not widths:
        frappe.throw(f"No valid width found in Shaft Details: '{shaft}'")

    results = []
    
    # 1. Fetch Codes from Masters with safety fallback
    qual_code = get_master_code("Quality Master", quality, 
                               ["custom_quality_code", "quality_code", "short_code", "code"])
    
    color_code = get_master_code("Colour Master", cl_type, 
                                ["custom_color_code", "color_code", "short_code", "colour_code", "code"])

    qual_code = str(qual_code).zfill(3)[:3]
    color_code = str(color_code).zfill(3)[:3]
    gsm_str = str(int(flt(gsm))).zfill(3)[:3]

    for w_inch in widths:
        # Width Logic
        mm_raw = flt(w_inch) * 25.4
        mm_int = int(mm_raw)
        mm_final = round(mm_int / 5.0) * 5
        width_mm_str = str(int(mm_final)).zfill(4)[:4]
        
        item_code = f"100{qual_code}{color_code}{gsm_str}{width_mm_str}"
        item_name = f"NON WOVEN FABRIC {quality.upper()} {cl_type.upper()} {gsm_str.lstrip('0')} GSM W - {w_inch}\" ( {mm_final} MM )"
        
        results.append({
            "item_code": item_code,
            "item_name": item_name,
            "width_inch": w_inch,
            "width_mm": mm_final
        })
    
    return results

def get_mix_batch_roll(item_code, unit_code):
    """
    Calculates the next Series and Roll for a Mix Item based on the / format.
    Format: MMUYYSeries/Roll (e.g. 032261/1)
    """
    today_str = frappe.utils.today()
    month_str = today_str[5:7]
    year_str = today_str[2:4]
    
    prefix = f"{month_str}{unit_code}{year_str}"
    
    # Search for the latest batch for this item/unit/today
    # We look for ANY batch that starts with prefix and has the / separator
    latest_batch = frappe.db.sql("""
        select batch_id from `tabBatch`
        where item = %s and batch_id like %s
        order by creation desc limit 1
    """, (item_code, f"{prefix}%"))
    
    if latest_batch:
        full_id = latest_batch[0][0]
        if "/" in full_id:
            try:
                series_part, roll_part = full_id.split("/")
                return f"{series_part}/{int(roll_part) + 1}"
            except:
                return f"{full_id}/1"
        else:
            # Found a batch but no / (maybe legacy or from another system)
            # We treat the entire thing as the series and start roll 1
            return f"{full_id}/1"
    else:
        # No batch found today? Start at Series 1, Roll 1
        return f"{prefix}1/1"

@frappe.whitelist()
def create_mix_item(quality, cl_type, gsm, shaft):
    """Creates/Gets Items for all widths in shaft."""
    items_details = get_mix_item_details(quality, cl_type, gsm, shaft)
    
    for details in items_details:
        item_code = details["item_code"]
        if not frappe.db.exists("Item", item_code):
            item = frappe.new_doc("Item")
            item.item_code = item_code
            item.item_name = details["item_name"]
            item.item_group = "Products"
            item.stock_uom = "Kg"
            item.sales_uom = "Kg"
            item.weight_uom = "Kg"
            item.is_stock_item = 1
            item.valuation_method = "FIFO"
            item.valuation_rate = 100
            item.has_batch_no = 1
            item.default_material_request_type = "Material Transfer"
            
            # Set Default Warehouse in Item Defaults table
            item.append("item_defaults", {
                "company": frappe.defaults.get_global_default("company") or "Jayashree Spun Bond",
                "default_warehouse": "Finished Goods - JSB-1ZT"
            })
            
            tax_template = frappe.db.get_value("Item Tax Template", {"name": ["like", "%GST 5%"]}, "name")
            if tax_template:
                item.append("taxes", {"item_tax_template": tax_template, "tax_category": ""})
            
            meta = frappe.get_meta("Item")
            fields = [f.fieldname for f in meta.fields]
            if "custom_quality" in fields: item.custom_quality = quality
            if "custom_color" in fields: item.custom_color = cl_type
            if "custom_gsm" in fields: item.custom_gsm = gsm
            if "custom_width_inch" in fields: item.custom_width_inch = details["width_inch"]
            
            # HSN Logic based on GSM (CORRECTED)
            hsn_code = None
            gsm_val = flt(gsm)
            if 15 <= gsm_val <= 24: hsn_code = "56031100"
            elif 25 <= gsm_val <= 70: hsn_code = "56031200"
            elif 71 <= gsm_val <= 150: hsn_code = "56031300"
            
            if hsn_code:
                if "gst_hsn_code" in fields: item.gst_hsn_code = hsn_code
                elif "hsn_code" in fields: item.hsn_code = hsn_code
            
            item.insert(ignore_permissions=True)
            frappe.db.commit()
    
    return items_details

@frappe.whitelist()
def create_mix_spr(date_key, mix_data):
    """Create a Shaft Production Run for mix rolls and return its name."""
    if isinstance(mix_data, str):
        mix_data = json.loads(mix_data)

    doc = frappe.new_doc("Shaft Production Run")
    doc.run_date = frappe.utils.today()
    doc.shift = get_current_shift()
    doc.is_mix_roll = 1
    doc.status = "Draft"

    # Sync mix name to order code header if available
    if mix_data and len(mix_data) > 0:
        doc.custom_order_code = mix_data[0].get("mixName")

    # Map mix data to shaft jobs
    for i, mix in enumerate(mix_data):
        # Require item code
        if not mix.get("item_code"):
            continue

        row = doc.append("shaft_jobs", {})
        row.job_id = str(i + 1)
        row.gsm = mix.get("gsm")
        row.quality = mix.get("quality")
        row.color = mix.get("cl_type") or mix.get("clType")
        row.party_code = mix.get("mixName")

        widths = re.findall(r"\d+", str(mix.get("shaft")))
        row.combination = " + ".join(widths)

        row.total_width = sum(flt(w) for w in widths)

        # Prefer meter length coming from production table; fallback to legacy default
        raw_meter = (
            mix.get("meter_roll_mtrs")
            or mix.get("meter_roll")
            or mix.get("meter")
            or mix.get("length_mtrs")
            or mix.get("length")
            or mix.get("meters_per_roll")
        )
        row.meter_roll_mtrs = flt(raw_meter) if raw_meter else 800
        row.no_of_shafts = len(widths)

        # Allow manual weight sync if needed; SPR has its own items grid
        row.is_manual = 1

        item_codes = [x.strip() for x in str(mix.get("item_code")).split(",") if x.strip()]
        row.manual_items = json.dumps(item_codes)

    doc.insert(ignore_permissions=True)

    # Sync the spr_name back to the Mix Roll Store so the Color Chart knows it's linked
    try:
        rows = frappe.db.sql("SELECT data FROM `mix_roll_store_data` WHERE date_key = %s", date_key)
        if rows and rows[0][0]:
            entries = json.loads(rows[0][0])
            updated = False
            for mix in mix_data:
                for entry in entries:
                    if mix.get("mix_id") and entry.get("mix_id"):
                        match_condition = entry.get("mix_id") == mix.get("mix_id")
                    else:
                        match_condition = (
                            entry.get("item_code") == mix.get("item_code")
                            and entry.get("shaft") == mix.get("shaft")
                        )

                    if match_condition and not entry.get("spr_name"):
                        entry["spr_name"] = doc.name
                        updated = True

            if updated:
                frappe.db.sql(
                    "UPDATE `mix_roll_store_data` SET data = %s WHERE date_key = %s",
                    (json.dumps(entries), date_key),
                )
                frappe.db.commit()
    except Exception:
        pass

    return doc.name

def get_current_shift():
    """Returns 'Day Shift' (08-20) or 'Night Shift' (20-08)."""
    current_hour = frappe.utils.now_datetime().hour
    if 8 <= current_hour < 20:
        return "Day Shift"
    else:
        return "Night Shift"

@frappe.whitelist()
def create_mix_stock_entry(item_codes, qty, unit, date_key):
    """Creates a Material Receipt. If qty is empty/0, created as DRAFT."""
    if isinstance(item_codes, str):
        item_codes = [c.strip() for c in item_codes.split(",") if c.strip()]
    
    if not item_codes:
        frappe.throw("No Item Codes provided for Stock Entry.")

    qty = flt(qty)
    is_draft = (qty <= 0)

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    
    target_warehouse = "Finished Goods - JSB-1ZT"
    if not frappe.db.exists("Warehouse", target_warehouse):
        target_warehouse = "Finished Goods - IZT" 
    if not frappe.db.exists("Warehouse", target_warehouse):
        target_warehouse = frappe.db.get_value("Stock Settings", None, "default_fg_warehouse") or "Finished Goods - P"

    # Unit Code (Last digit)
    try:
        u_code = str(unit).strip()[-1]
        if not u_code.isdigit(): u_code = "1"
    except: u_code = "1"

    split_qty = qty / len(item_codes) if len(item_codes) > 0 else 0

    for code in item_codes:
        item_name = frappe.db.get_value("Item", code, "item_name")
        if not item_name:
            frappe.throw(f"Item {code} does not exist.")
            
        # Generate Batch Number with \ separator
        batch_no = get_mix_batch_roll(code, u_code)
            
        se.append("items", {
            "item_code": code,
            "qty": split_qty,
            "t_warehouse": target_warehouse,
            "uom": "Kg",
            "stock_uom": "Kg",
            "conversion_factor": 1,
            "batch_no": batch_no
        })
    
    meta = frappe.get_meta("Stock Entry")
    fields = [f.fieldname for f in meta.fields]
    if "custom_unit" in fields: se.custom_unit = unit
    if "custom_is_mix_roll" in fields: se.custom_is_mix_roll = 1
    if "custom_mix_roll_date" in fields: se.custom_mix_roll_date = date_key
    
    se.insert(ignore_permissions=True)
    
    if not is_draft:
        se.submit()
    
    frappe.db.commit()
    
    # Store SE reference in Mix Roll Store to allow weight sync later
    _sync_mix_roll_se_reference(date_key, item_codes, se.name)
    
    return se.name

def _sync_mix_roll_se_reference(date_key, item_codes, se_name):
    try:
        rows = frappe.db.sql("SELECT data FROM `mix_roll_store_data` WHERE date_key = %s", date_key)
        if not (rows and rows[0][0]): return
        
        entries = json.loads(rows[0][0])
        codes_str = ", ".join(item_codes)
        found = False
        for m in entries:
            # Match by item code string
            if m.get("item_code") == codes_str:
                m["stock_entry"] = se_name
                found = True
        
        if found:
            frappe.db.sql(
                "UPDATE `mix_roll_store_data` SET data = %s WHERE date_key = %s",
                (json.dumps(entries), date_key)
            )
            frappe.db.commit()
    except Exception:
        pass
    
    return se_name

@frappe.whitelist()
def create_mix_wo(unit, mix_name, quality, cl_type, gsm, shaft, kg, date_key):
    """LEGACY: Re-routed to Stock Entry in new flow, but kept for compatibility."""
    # The new flow uses create_mix_item then create_mix_stock_entry.
    # We'll just leave this as is for now or point it to a warning.
    return create_mix_wo_old(unit, mix_name, quality, cl_type, gsm, shaft, kg, date_key)

def create_mix_wo_old(unit, mix_name, quality, gsm, shaft, kg, date_key):
    """
    Old Logic: Creates a Work Order for a Mix Roll manually entered in Color Chart.
    """
    # 1. Determine Production Item
    possible_names = [f"{quality} {gsm} GSM", f"{quality} {gsm}", f"MIX-{quality}-{gsm}".replace(" ", "-").upper(), mix_name]
    item_code = None
    for name in possible_names:
        item_code = frappe.db.get_value("Item", {"item_name": name}, "name") or frappe.db.get_value("Item", {"name": name}, "name")
        if item_code: break
    if not item_code: item_code = frappe.db.get_value("Item", {"item_name": "MIX ROLL"}, "name")
    if not item_code: frappe.throw(f"Mix Item not found.")

    # 2. Create the Work Order
    wo = frappe.new_doc("Work Order")
    wo.production_item = item_code
    wo.qty = flt(kg)
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    if not company: company = frappe.get_all("Company", limit=1)[0].name
    wo.company = company
    wo.wip_warehouse = frappe.db.get_value("Stock Settings", None, "default_wip_warehouse")
    wo.fg_warehouse = frappe.db.get_value("Stock Settings", None, "default_fg_warehouse")
    
    meta = frappe.get_meta("Work Order")
    fields = [f.fieldname for f in meta.fields]
    if "custom_unit" in fields: wo.custom_unit = unit
    if "custom_shaft_details" in fields: wo.custom_shaft_details = shaft
    if "custom_mix_roll_date" in fields: wo.custom_mix_roll_date = date_key
    if "custom_is_mix_roll" in fields: wo.custom_is_mix_roll = 1

    wo.insert()
    frappe.db.commit()
    return wo.name

@frappe.whitelist()
def send_to_approval(planning_sheet_name):
    if not _has_approval_status_column():
        frappe.throw(_("Approval status column is missing. Please run 'bench migrate' to update the database schema."))
    frappe.db.set_value("Planning sheet", planning_sheet_name, "custom_approval_status", "Pending Approval")
    frappe.db.commit()
    return {"status": "success", "message": f"Planning Sheet {planning_sheet_name} sent for approval."}

@frappe.whitelist()
def approve_planning_sheet(planning_sheet_name):
    if not _has_approval_status_column():
        frappe.throw(_("Approval status column is missing. Please run 'bench migrate' to update the database schema."))
    frappe.db.set_value("Planning sheet", planning_sheet_name, "custom_approval_status", "Approved")
    frappe.db.commit()
    return {"status": "success", "message": f"Planning Sheet {planning_sheet_name} approved."}


@frappe.whitelist()
def run_orphan_cleanup():
    """
    Ultra-resilient backend cleanup to purge orphaned items and deduplicate.
    Dynamically inspects database columns to avoid 'Unknown column' errors.
    """
    frappe.only_for("System Manager")
    
    # 1. Clean up orphaned items (linked to deleted sheets)
    # Using get_all + delete_doc is slower but safer than raw SQL DELETE in Console
    all_items = frappe.get_all("Planning Table", fields=["name", "parent"])
    orphans_count = 0
    for it in all_items:
        if not it.parent or not frappe.db.exists("Planning sheet", it.parent):
            frappe.delete_doc("Planning Table", it.name, force=1, ignore_permissions=True)
            orphans_count += 1
            
    # 2. Deduplicate items within sheets (handle dynamic schema)
    # Get actual table columns to avoid 1054 errors - USE DOCTYPE NAME
    columns = frappe.db.get_table_columns("Planning Table")
    
    so_item_col = None
    if "sales_order_item" in columns:
        so_item_col = "sales_order_item"
    elif "custom_sales_order_item" in columns:
        so_item_col = "custom_sales_order_item"
        
    dup_count = 0
    if so_item_col:
        dups = frappe.db.sql(f"""
            SELECT parent, {so_item_col}, COUNT(*) as cnt
            FROM `tabPlanning Table`
            GROUP BY parent, {so_item_col}
            HAVING COUNT(*) > 1
        """, as_dict=True)

        for d in dups:
            items = frappe.get_all("Planning Table", 
                filters={"parent": d.parent, so_item_col: d.get(so_item_col)},
                fields=["name"],
                order_by="creation asc"
            )
            for it in items[1:]:
                frappe.delete_doc("Planning Table", it.name, force=1, ignore_permissions=True)
                dup_count += 1
                
    # 3. Specific ghost sheet cleanup
    sheet_to_fix = "PLAN-2026-00786"
    if frappe.db.exists("Planning sheet", sheet_to_fix):
        frappe.delete_doc("Planning sheet", sheet_to_fix, force=1, ignore_permissions=True)
    
    frappe.db.commit()
    return {
        "status": "success", 
        "message": f"Cleaned up {orphans_count} orphans and {dup_count} duplicates.",
        "columns_checked": columns
    }


@frappe.whitelist()
def get_planning_sheet_pp_id(planning_sheet_name, sales_order_item=None, planning_sheet_item=None):
    """
    Fetch the Production Plan ID linked to a Planning Sheet.
    Returns the PP ID so it can be viewed in a new tab.
    """
    no_pp_message = "No Production Plan created for this order"

    if not planning_sheet_name:
        return {"status": "not_found", "message": no_pp_message}

    try:
        if not frappe.db.exists("Planning sheet", planning_sheet_name):
            return {"status": "not_found", "message": no_pp_message}

        sheet = frappe.get_doc("Planning sheet", planning_sheet_name)
        pp_id = None

        # Strategy 0: exact item-level linkage from clicked row item
        if not planning_sheet_item and sales_order_item:
            planning_sheet_item = frappe.db.get_value(
                "Planning Table",
                {"parent": planning_sheet_name, "sales_order_item": sales_order_item},
                "name",
            ) or frappe.db.get_value(
                "Planning Table",
                {"parent": planning_sheet_name, "custom_sales_order_item": sales_order_item},
                "name",
            )

        if planning_sheet_item and frappe.db.exists("Planning Table", planning_sheet_item):
            pp_id = _get_item_level_production_plan(planning_sheet_item)

        # Strategy 0.5: resolve by Production Plan Item + sales_order_item
        if (not pp_id) and sales_order_item:
            pp_id = _resolve_pp_by_sales_order_item(sales_order_item)

        # Strategy 1: direct link fields on Planning sheet
        if (not pp_id) and frappe.db.has_column("Planning sheet", "custom_production_plan"):
            pp_id = frappe.db.get_value("Planning sheet", planning_sheet_name, "custom_production_plan")

        if (not pp_id) and frappe.db.has_column("Planning sheet", "production_plan"):
            pp_id = frappe.db.get_value("Planning sheet", planning_sheet_name, "production_plan")

        if not pp_id:
            for field_name in ["custom_production_plan", "production_plan", "production_plan_id", "pp_id"]:
                if hasattr(sheet, field_name):
                    pp_id = getattr(sheet, field_name, None)
                    if pp_id:
                        break

        # Strategy 2: fallback by Sales Order
        if not pp_id and sheet.sales_order:
            if frappe.db.has_column("Production Plan", "sales_order"):
                pps = frappe.db.sql("""
                    SELECT name FROM `tabProduction Plan`
                    WHERE sales_order = %s AND docstatus = 1
                    ORDER BY creation DESC
                    LIMIT 1
                """, (sheet.sales_order,), as_dict=True)
                if pps:
                    pp_id = pps[0]["name"]
            else:
                try:
                    pps = frappe.db.sql("""
                        SELECT DISTINCT pp.name
                        FROM `tabProduction Plan` pp
                        LEFT JOIN `tabProduction Plan Item` ppi ON pp.name = ppi.parent
                        WHERE (ppi.sales_order = %s OR pp.name LIKE CONCAT('%%', %s, '%%'))
                        AND pp.docstatus = 1
                        ORDER BY pp.creation DESC
                        LIMIT 1
                    """, (sheet.sales_order, sheet.sales_order), as_dict=True)
                    if pps:
                        pp_id = pps[0]["name"]
                except Exception as e:
                    frappe.log_error(f"Error searching PP by items: {str(e)}", "get_planning_sheet_pp_id")

        # Strategy 3: fallback by planning sheet link fields on PP
        if not pp_id:
            conditions = []
            params = []

            if frappe.db.has_column("Production Plan", "custom_planning_sheet"):
                conditions.append("custom_planning_sheet = %s")
                params.append(planning_sheet_name)
            if frappe.db.has_column("Production Plan", "planning_sheet"):
                conditions.append("planning_sheet = %s")
                params.append(planning_sheet_name)

            if conditions:
                where_clause = " OR ".join(conditions)
                pps = frappe.db.sql(f"""
                    SELECT name FROM `tabProduction Plan`
                    WHERE ({where_clause})
                    AND docstatus = 1
                    ORDER BY creation DESC
                    LIMIT 1
                """, tuple(params), as_dict=True)
                if pps:
                    pp_id = pps[0]["name"]

        if not pp_id:
            return {"status": "not_found", "message": no_pp_message}

        if not frappe.db.exists("Production Plan", pp_id):
            return {"status": "error", "message": "Linked Production Plan not found in system"}

        return {"status": "ok", "pp_id": pp_id}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_planning_sheet_pp_id")
        return {"status": "error", "message": "Unable to fetch Production Plan"}


@frappe.whitelist()
def debug_psi_fields():
    """
    DEBUG: Check what fields exist on Planning Sheet Item.
    Used to understand the actual column structure.
    """
    try:
        # Get all columns for Planning Sheet Item
        cols = frappe.db.sql("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME='tabPlanning Table' 
            ORDER BY COLUMN_NAME
        """, as_dict=True)
        
        column_names = [c['COLUMN_NAME'] for c in cols]
        
        # Filter for relevant fields
        spr_related = [c for c in column_names if 'spr' in c.lower() or 'shaft' in c.lower()]
        production_related = [c for c in column_names if 'production' in c.lower()]
        
        return {
            "status": "ok",
            "all_columns_count": len(column_names),
            "spr_related_fields": spr_related,
            "production_related_fields": production_related,
            "sample_fields": column_names[:20] if len(column_names) > 20 else column_names
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "debug_psi_fields")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def debug_item_pp_id(item_name):
    """
    DEBUG: Check what pp_id is resolved for a specific Planning Sheet Item.
    Used to diagnose missing PP links.
    """
    if not item_name:
        return {"status": "error", "message": "item_name required"}
    
    if not frappe.db.exists("Planning Table", item_name):
        return {"status": "error", "message": f"Item {item_name} not found"}
    
    try:
        item = frappe.get_doc("Planning Table", item_name)
        parent_sheet = frappe.get_doc("Planning sheet", item.parent)
        
        # Check each PP resolution strategy
        result = {
            "item_name": item_name,
            "strategies": {}
        }
        
        # Strategy 1: direct fields
        for field in _psi_production_plan_fields():
            value = frappe.db.get_value("Planning Table", item_name, field)
            result["strategies"][f"Direct: {field}"] = value or "empty"
        
        # Strategy 2: via sales_order_item
        so_item = item.get("sales_order_item") or item.get("custom_sales_order_item")
        if so_item:
            pp_via_so = _resolve_pp_by_sales_order_item(so_item)
            result["strategies"]["Via SO Item"] = pp_via_so or "not found"
        else:
            result["strategies"]["Via SO Item"] = "no SO item"
        
        # Strategy 3: via sheet
        sheet_pp_fields = ["custom_production_plan", "production_plan"]
        for field in sheet_pp_fields:
            if frappe.db.has_column("Planning sheet", field):
                value = frappe.db.get_value("Planning sheet", item.parent, field)
                result["strategies"][f"Sheet: {field}"] = value or "empty"
        
        # Final resolved PP
        resolved_pp = _get_item_level_production_plan(item_name)
        result["final_resolved_pp"] = resolved_pp or "NONE"
        result["has_wo"] = bool(frappe.db.count("Work Order", 
            filters={"production_plan": resolved_pp, "docstatus": ["<", 2]})) if resolved_pp else False
        
        return result
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "debug_item_pp_id")
        return {"status": "error", "message": str(e)}



@frappe.whitelist()
def backfill_pp_id_to_sheet_items(planning_sheet_name=None, dry_run=1):
    """
    Backfill order_sheet (PP ID) to each Planning Sheet Item row.

    Matching: each item has item_code. The parent Planning Sheet has order_sheet
    (comma-separated PP IDs). We find which PP contains that item_code.

    Args:
        planning_sheet_name: Optional. Limit to one sheet. If blank, all sheets.
        dry_run: 1 = preview only, 0 = actually write.
    """
    dry_run = cint(dry_run)

    # Fetch items - only confirmed fields: name, parent, item_code, order_sheet
    parent_filter = "WHERE 1=1"
    params = []
    if planning_sheet_name:
        parent_filter = "WHERE parent = %s"
        params.append(planning_sheet_name)

    items = frappe.db.sql(
        f"SELECT `name`, `parent`, `item_code`, `order_sheet` "
        f"FROM `tabPlanning Table` {parent_filter} ORDER BY parent ASC, idx ASC",
        params, as_dict=True
    )

    results = {"updated": [], "already_set": [], "not_found": [], "errors": []}

    # Cache parent sheet PP lists to avoid repeated DB calls
    sheet_pp_cache = {}

    for psi in items:
        try:
            # Skip if already filled
            existing_pp = psi.get("order_sheet") or ""
            if existing_pp.strip() and frappe.db.exists("Production Plan", existing_pp.strip()):
                results["already_set"].append({
                    "item": psi.name, "sheet": psi.parent, "pp_id": existing_pp.strip()
                })
                continue

            item_code = psi.get("item_code") or ""
            if not item_code:
                results["not_found"].append({"item": psi.name, "sheet": psi.parent, "reason": "no item_code"})
                continue

            # Get PP list from parent sheet (cached)
            if psi.parent not in sheet_pp_cache:
                sheet_order = frappe.db.get_value("Planning sheet", psi.parent, "order_sheet") or ""
                sheet_pp_cache[psi.parent] = [p.strip() for p in sheet_order.split(",") if p.strip()]

            pp_list = sheet_pp_cache[psi.parent]

            if not pp_list:
                results["not_found"].append({"item": psi.name, "sheet": psi.parent, "reason": "parent sheet has no order_sheet PPs"})
                continue

            # Find which PP in the list has this item_code
            # (Loop through PPs to find which one has this item_code)
            found_pp = None
            for pp_id in pp_list:
                pp_items = frappe.db.get_all("Production Plan Item", 
                    filters={"parent": pp_id, "item_code": item_code},
                    fields=["name"])
                if pp_items:
                    found_pp = pp_id
                    break
            
            if found_pp:
                if not dry_run:
                    frappe.db.set_value("Planning Table", psi["name"], "order_sheet", found_pp)
                results["updated"].append({
                    "item": psi["name"],
                    "sheet": psi["parent"],
                    "pp_id": found_pp,
                    "dry_run": bool(dry_run)
                })
            else:
                results["not_found"].append({
                    "item": psi["name"],
                    "sheet": psi["parent"],
                    "reason": f"item_code not found in any PP: {pp_list}"
                })
        
        except Exception as e:
            results["errors"].append({
                "item": psi.get("name", "unknown"),
                "error": str(e)
            })
    
    return results


# ============================================================================
# TEST & VERIFICATION FUNCTIONS
# ============================================================================

@frappe.whitelist()
def test_quality_extraction():
    """
    Test and verify that quality code extraction is working correctly.
    Can be called from console: frappe.call({method: 'production_entry.production_planning.scheduler_api.test_quality_extraction'})
    
    Tests:
    1. Quality Master structure and available fields
    2. Quality code extraction from 16-digit item codes
    3. Existing Planning Sheet items for quality population
    4. Manual extraction logic verification
    """
    import json
    
    results = {
        "status": "pending",
        "timestamp": frappe.utils.now(),
        "tests": [],
        "warnings": [],
        "errors": []
    }
    
    try:
        # TEST 1: Quality Master Count & Structure
        qm_count = frappe.db.count("Quality Master")
        results["tests"].append({
            "name": "Quality Master Count",
            "value": qm_count,
            "status": "PASS" if qm_count > 0 else "FAIL"
        })
        
        if qm_count == 0:
            results["warnings"].append("No Quality Masters found - quality extraction will have nothing to lookup")
        
        # TEST 2: Sample Quality Masters with codes
        qm_sample = frappe.db.sql("""
            SELECT name, short_code, code, quality_code
            FROM `tabQuality Master`
            LIMIT 3
        """, as_dict=True)
        
        results["tests"].append({
            "name": "Quality Master Samples",
            "samples": qm_sample,
            "status": "PASS"
        })
        
        # TEST 3: Manual extraction test (simulate _populate_planning_sheet_items logic)
        test_cases = [
            {"code": "1001165421501865", "q_code": "116", "c_code": "542", "desc": "Standard 16-digit format"},
            {"code": "1001035041001600", "q_code": "103", "c_code": "504", "desc": "Another standard format"},
        ]
        
        extraction_tests = []
        for tc in test_cases:
            item_code_str = str(tc["code"]).strip()
            if len(item_code_str) >= 9 and item_code_str.startswith("100"):
                q_code = item_code_str[3:6]
                c_code = item_code_str[6:9]
                
                # Lookup quality
                qual_name = None
                lookup_field = None
                for field in ["short_code", "code", "quality_code"]:
                    try:
                        result = frappe.db.get_value("Quality Master", {field: q_code}, "name")
                        if result:
                            qual_name = result
                            lookup_field = field
                            break
                    except:
                        pass
                
                extraction_tests.append({
                    "item_code": tc["code"],
                    "expected_q_code": tc["q_code"],
                    "extracted_q_code": q_code,
                    "q_code_match": q_code == tc["q_code"],
                    "expected_c_code": tc["c_code"],
                    "extracted_c_code": c_code,
                    "c_code_match": c_code == tc["c_code"],
                    "quality_found": qual_name or "NOT FOUND",
                    "lookup_field": lookup_field,
                    "status": "PASS" if (q_code == tc["q_code"] and c_code == tc["c_code"]) else "FAIL"
                })
        
        results["tests"].append({
            "name": "Quality Code Extraction Logic",
            "test_cases": extraction_tests,
            "status": "PASS" if all(t["status"] == "PASS" for t in extraction_tests) else "PARTIAL"
        })
        
        # TEST 4: Planning Sheet Item Population Status
        psi_total = frappe.db.count("Planning Table", {"docstatus": ["<", 2]})
        psi_with_qual = frappe.db.count("Planning Table", {"docstatus": ["<", 2], "custom_quality": ["!=", ""]})
        psi_without_qual = psi_total - psi_with_qual
        
        pct_populated = round((psi_with_qual / psi_total * 100) if psi_total > 0 else 0, 2)
        
        results["tests"].append({
            "name": "Planning Sheet Item Quality Population",
            "total_items": psi_total,
            "with_quality": psi_with_qual,
            "without_quality": psi_without_qual,
            "percentage_populated": pct_populated,
            "status": "PASS" if pct_populated > 0 or psi_total == 0 else "INFO"
        })
        
        # TEST 5: Sample PSI items with quality populated
        if psi_with_qual > 0:
            psi_samples = frappe.db.sql("""
                SELECT name, item_code, custom_quality, parent, unit, qty
                FROM `tabPlanning Table`
                WHERE docstatus < 2 AND custom_quality IS NOT NULL AND custom_quality != ''
                ORDER BY creation DESC
                LIMIT 5
            """, as_dict=True)
            
            results["tests"].append({
                "name": "Sample PSI Items with Populated Quality",
                "samples": psi_samples,
                "status": "PASS"
            })
        
        # TEST 6: Verify implementation function exists
        try:
            from production_entry.production_planning.scheduler_api import _populate_planning_sheet_items, _get_color_by_code
            results["tests"].append({
                "name": "Implementation Functions",
                "functions": ["_populate_planning_sheet_items", "_get_color_by_code"],
                "status": "PASS"
            })
        except Exception as e:
            results["tests"].append({
                "name": "Implementation Functions",
                "error": str(e),
                "status": "FAIL"
            })
            results["errors"].append(f"Could not import functions: {e}")
        
        # Overall status
        failed_tests = [t for t in results["tests"] if t.get("status") == "FAIL"]
        results["status"] = "FAIL" if failed_tests else "PASS"
        
        frappe.msgprint(f"<pre>{json.dumps(results, indent=2, default=str)}</pre>", 
                       title="Quality Extraction Test Results",
                       indicator="red" if failed_tests else "green")
        
        return results
        
    except Exception as e:
        results["status"] = "ERROR"
        results["errors"].append(str(e))
        import traceback as tb
        results["traceback"] = tb.format_exc()
        return results


@frappe.whitelist()
def create_item_spr(pp_id, planning_sheet_item_names):

    """
    Create a Shaft Production Run (SPR) for a Production Plan.
    Fetches shaft details from the Production Plan's shaft_details table.
    
    Args:
        pp_id: Production Plan ID
        planning_sheet_item_names: JSON list of Planning Sheet Item names to include
    
    Returns: SPR name or error message
    """
    if isinstance(planning_sheet_item_names, str):
        planning_sheet_item_names = json.loads(planning_sheet_item_names)
    
    if not pp_id or not planning_sheet_item_names:
        return {"status": "error", "message": "PP ID and item names required"}
    
    if not frappe.db.exists("Production Plan", pp_id):
        return {"status": "error", "message": f"Production Plan {pp_id} not found"}
    
    try:
        def _link_items_to_spr(spr_name_to_link):
            """Persist per-item SPR link so split rows remain independent across dates/units."""
            try:
                if not spr_name_to_link or not planning_sheet_item_names:
                    return
                if not frappe.db.has_column("Planning Table", "spr_name"):
                    return
                for psi_name in planning_sheet_item_names:
                    if frappe.db.exists("Planning Table", psi_name):
                        frappe.db.set_value("Planning Table", psi_name, "spr_name", spr_name_to_link)
            except Exception:
                pass

        def _hydrate_existing_spr(existing_spr_name, current_pp_id):
            """Fill missing shaft job fields on reused draft SPR from PP shaft mapping."""
            if not existing_spr_name or not frappe.db.exists("Shaft Production Run", existing_spr_name):
                return

            payload = get_spr_shaft_jobs_from_pp(current_pp_id)
            if not payload or payload.get("status") != "ok":
                return

            jobs = payload.get("jobs") or []
            if not jobs:
                return

            spr_doc = frappe.get_doc("Shaft Production Run", existing_spr_name)
            rows = list(spr_doc.get("shaft_jobs") or [])
            changed = False

            def _set_if_blank(row, keys, value):
                nonlocal changed
                if value in (None, ""):
                    return
                for k in keys:
                    if hasattr(row, k):
                        cur = row.get(k)
                        if cur in (None, "", 0, 0.0):
                            row.set(k, value)
                            changed = True

            # If no rows exist yet, create rows directly from jobs.
            if not rows:
                for i, job in enumerate(jobs, start=1):
                    row = spr_doc.append("shaft_jobs", {})
                    row.job_id = job.get("job_id") or str(i)
                    row.gsm = job.get("gsm") or ""
                    row.combination = job.get("combination") or ""
                    row.total_width = flt(job.get("total_width") or 0)
                    row.meter_roll_mtrs = flt(job.get("meter_roll_mtrs") or 0)
                    row.no_of_shafts = cint(job.get("no_of_shafts") or 0)
                    row.net_weight = job.get("net_weight") or job.get("net_weight_shaft_kgs") or ""
                    row.net_weight_shaft_kgs = row.net_weight
                    row.total_weight = flt(job.get("total_weight") or job.get("total_weight_kgs") or 0)
                    row.total_weight_kgs = row.total_weight
                    row.order_code = job.get("order_code") or ""
                    row.work_orders = job.get("work_orders") or ""
                    row.custom_label = job.get("custom_label") or ""
                changed = True
            else:
                for idx, row in enumerate(rows):
                    job = jobs[idx] if idx < len(jobs) else jobs[-1]
                    _set_if_blank(row, ["net_weight", "net_weight_shaft_kgs", "net_weight_shaft", "custom_net_weight_shaft_kgs"], job.get("net_weight") or job.get("net_weight_shaft_kgs"))
                    _set_if_blank(row, ["total_weight", "total_weight_kgs", "custom_total_weight_kgs"], flt(job.get("total_weight") or job.get("total_weight_kgs") or 0))
                    _set_if_blank(row, ["order_code", "custom_order_code"], job.get("order_code") or "")
                    _set_if_blank(row, ["work_orders", "work_order", "wo_no"], job.get("work_orders") or "")
                    _set_if_blank(row, ["combination", "shaft", "shaft_details"], job.get("combination") or "")
                    _set_if_blank(row, ["meter_roll_mtrs", "roll_mtrs", "meter_roll", "roll"], flt(job.get("meter_roll_mtrs") or 0))
                    _set_if_blank(row, ["no_of_shafts", "no_of_shaft", "no_of_sh", "no_of_sf"], cint(job.get("no_of_shafts") or 0))
                    _set_if_blank(row, ["custom_label", "label"], job.get("custom_label") or "")
                    _set_if_blank(row, ["custom_label", "label"], job.get("custom_label") or "")

            if changed:
                spr_doc.save(ignore_permissions=True)

        pp = frappe.get_doc("Production Plan", pp_id)

        # If any provided PSI already has an SPR link, reuse that specific SPR only for those PSI rows.
        psi_list = []
        existing_links = set()
        for psi_name in planning_sheet_item_names:
            if frappe.db.exists("Planning Table", psi_name):
                psi = frappe.get_doc("Planning Table", psi_name)
                psi_list.append(psi)
                link_name = (psi.get("spr_name") or "").strip()
                if link_name:
                    existing_links.add(link_name)

        if not psi_list:
            return {"status": "error", "message": "No valid Planning Sheet Items found"}

        if len(existing_links) > 1:
            return {
                "status": "error",
                "message": f"Multiple SPR links found for selected rows: {', '.join(sorted(existing_links))}. Please select rows with a single SPR or create separately.",
            }

        if len(existing_links) == 1:
            reuse_spr = existing_links.pop()
            if frappe.db.exists("Shaft Production Run", reuse_spr):
                _hydrate_existing_spr(reuse_spr, pp_id)
                _link_items_to_spr(reuse_spr)
                return {
                    "status": "ok",
                    "spr_id": reuse_spr,
                    "message": f"SPR Reused for PSI: {reuse_spr}",
                    "reused": 1,
                }
        
        # Create SPR
        spr = frappe.new_doc("Shaft Production Run")
        spr.run_date = frappe.utils.today()
        spr.shift = get_current_shift()
        spr.is_mix_roll = 0
        spr.status = "Draft"
        spr.production_plan = pp_id
        
        # Extract order code and customer from first item's parent sheet and PP
        first_psi = psi_list[0]
        parent_sheet = frappe.get_doc("Planning sheet", first_psi.parent)
        
        spr.custom_order_code = parent_sheet.party_code or ""
        spr.customer = pp.customer or parent_sheet.customer or ""

        from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
            _production_plan_total_planned_qty,
            resolve_label_from_planning_sheet_doc,
            resolve_label_from_pp_doc,
        )

        label_value = resolve_label_from_pp_doc(pp) or resolve_label_from_planning_sheet_doc(parent_sheet)
        if label_value:
            spr.custom_label = label_value

        frappe.logger().info(f"[create_item_spr] Set custom_label={label_value or ''} for PP {pp_id}")
        
        def pick_value(source, keys, default=None):
            for k in keys:
                v = source.get(k)
                if v not in (None, ""):
                    return v
            return default

        # Fetch shaft details from Production Plan (not from Planning Sheet Items)
        # Copy shaft details from PP to SPR
        pp_shafts = pp.get("custom_shaft_details") or pp.get("shaft_details") or []

        # Fetch linked Work Orders for this PP
        pp_work_orders = frappe.get_all("Work Order",
            filters={"production_plan": pp_id, "docstatus": ["<", 2]},
            fields=["name", "production_item", "qty", "produced_qty", "status"],
            order_by="creation asc"
        )
        wo_names_str = ", ".join([wo.name for wo in pp_work_orders]) if pp_work_orders else ""
        wo_total_qty = sum(flt(wo.qty) for wo in pp_work_orders)

        # Set custom_total_planned_qty from Work Orders; if WOs are missing/zero, use PP / PP-items (same as desk).
        if wo_total_qty > 0:
            spr.custom_total_planned_qty = wo_total_qty
            frappe.logger().info(f"[create_item_spr] Set custom_total_planned_qty={wo_total_qty} from WO sum for PP {pp_id}")
        else:
            pq = _production_plan_total_planned_qty(pp_id)
            if pq > 0:
                spr.custom_total_planned_qty = pq
                frappe.logger().info(f"[create_item_spr] Set custom_total_planned_qty={pq} from PP fallback for {pp_id}")

        # PP-level fallback values - try all possible field name variations
        # Standard PP fields + custom_ prefix variants
        pp_net_weight = (
            pp.get("custom_net_weight") or pp.get("net_weight") or
            pp.get("custom_net_weight_kgs") or pp.get("net_weight_kgs") or
            pp.get("custom_weight_per_roll") or pp.get("weight_per_roll") or ""
        )
        pp_total_weight = flt(
            pp.get("custom_total_weight_kgs") or pp.get("total_weight_kgs") or
            pp.get("custom_total_weight") or pp.get("total_weight") or
            pp.get("total_planned_qty") or pp.get("custom_total_planned_qty") or 0
        )
        pp_no_of_shaft = cint(
            pp.get("custom_no_of_shaft") or pp.get("no_of_shaft") or
            pp.get("custom_no_of_shafts") or pp.get("no_of_shafts") or 0
        )
        pp_combined_width = (
            pp.get("custom_combined_width") or pp.get("combined_width") or
            pp.get("custom_total_width") or pp.get("total_width") or ""
        )

        # Log PP-level values for debugging
        frappe.log_error(
            f"PP {pp_id} level values: net_weight={pp_net_weight}, total_weight={pp_total_weight}, "
            f"no_of_shaft={pp_no_of_shaft}, combined_width={pp_combined_width}",
            "SPR_DEBUG_PP_LEVEL"
        )

        if pp_shafts:
            for pp_shaft in pp_shafts:
                row = spr.append("shaft_jobs", {})
                row.job_id = pick_value(pp_shaft, ["job_id", "job", "job_no"], str(len(spr.shaft_jobs)))
                row.gsm = pick_value(pp_shaft, ["gsm"], "")
                row.combination = pick_value(pp_shaft, ["combination", "combined_width", "shaft", "shaft_details"], "") or pp_combined_width
                row.total_width = flt(pick_value(pp_shaft, ["total_width", "combined_width", "width", "total_width_inches"], 0) or 0) or flt(pp_combined_width or 0)
                # Prefer PP shaft meter__roll; fall back to PP-level fields before defaulting
                row.meter_roll_mtrs = flt(
                    pick_value(
                        pp_shaft,
                        [
                            "meter__roll",
                            "meter_roll_mtrs",
                            "meter_per_roll",
                            "meter_roll",
                            "roll_mtrs",
                            "custom_meter_roll_mtrs",
                            "custom_meter_per_roll",
                            "meter_per_roll_mtrs",
                            "roll",
                            "meter",
                        ],
                        0,
                    )
                    or flt(
                        pp.get("meter__roll")
                        or pp.get("custom_meter_roll_mtrs")
                        or pp.get("meter_roll_mtrs")
                        or pp.get("custom_meter_per_roll")
                        or pp.get("meter_per_roll")
                        or pp.get("custom_meter")
                        or pp.get("meter")
                        or 500
                    )
                )
                row.no_of_shafts = cint(pick_value(pp_shaft, ["no_of_shafts", "no_of_shaft", "no_of_sh", "no_of_sf"], 0) or 0) or pp_no_of_shaft or 1
                
                # Field names confirmed by user: net_weight, total_width (SPR)
                _nw = pick_value(pp_shaft, ["net_weight_shaft_kgs", "net_weight_shaft", "net_weight"], "") or pp_net_weight
                row.net_weight = _nw
                row.net_weight_shaft_kgs = _nw # keep legacy for safety
                row.net_weight_shaft = _nw
                row.custom_net_weight_shaft_kgs = _nw
                
                _tw = flt(pick_value(pp_shaft, ["total_weight_kgs", "total_weight", "weight"], 0) or 0) or pp_total_weight
                row.total_weight_kgs = _tw
                row.total_weight = _tw # try without _kgs variant too
                row.custom_total_weight_kgs = _tw
                row.order_code = pick_value(pp_shaft, ["order_code", "party_code", "custom_order_code"], parent_sheet.party_code or "")
                row.custom_order_code = row.order_code
                row.work_orders = pick_value(pp_shaft, ["work_orders", "work_order", "wo", "wo_no"], "") or wo_names_str
                row.work_order = row.work_orders
                # Compute total_weight from WO qty if still zero
                if not flt(row.total_weight_kgs) and wo_total_qty:
                    row.total_weight_kgs = flt(wo_total_qty)
                    row.total_weight = row.total_weight_kgs
                    row.custom_total_weight_kgs = row.total_weight_kgs
                row.quality = first_psi.custom_quality or first_psi.get("quality") or ""
                row.color = first_psi.color or ""
                row.party_code = parent_sheet.party_code or ""
                row.custom_label = pick_value(pp_shaft, ["custom_label", "label"], label_value or "")
        elif not pp_shafts:
            # Fallback: create one shaft job from PSI data if PP has no shaft_details
            for i, psi in enumerate(psi_list):
                row = spr.append("shaft_jobs", {})
                row.job_id = str(i + 1)
                row.quality = psi.custom_quality or psi.get("quality") or ""
                row.color = psi.color or ""
                row.party_code = parent_sheet.party_code or ""
                row.gsm = psi.gsm or ""
                row.custom_label = label_value or ""
                
                # Get width info from PSI
                width = flt(psi.get("width") or psi.get("custom_width") or psi.get("width_inch") or 0)
                if width:
                    row.combination = str(int(width))
                    row.total_width = width
                else:
                    row.combination = "Standard"
                    row.total_width = 0
                
                row.no_of_shafts = 1
                row.meter_roll_mtrs = flt(
                    pp.get("meter__roll")
                    or pp.get("custom_meter_roll_mtrs")
                    or pp.get("meter_roll_mtrs")
                    or pp.get("custom_meter_per_roll")
                    or pp.get("meter_per_roll")
                    or pp.get("custom_meter")
                    or pp.get("meter")
                    or 500
                )
        
        # Store selected Planning Sheet Item names for reference
        if psi_list:
            psi_names_str = ", ".join([psi.name for psi in psi_list])
            if spr.shaft_jobs:
                spr.shaft_jobs[0].manual_items = psi_names_str
        
        # Debug log before insert
        frappe.log_error(f"""
        About to insert SPR:
        - Name will be auto-generated
        - production_plan: {spr.production_plan}
        - customer: {spr.customer}
        - custom_order_code: {spr.custom_order_code}
        - shaft_jobs count: {len(spr.shaft_jobs or [])}
        - status: {spr.status}
        """, "create_item_spr_pre_insert")
        
        try:
            spr.insert(ignore_permissions=True)
        except Exception as insert_error:
            error_msg = str(insert_error)
            # Try to extract validation message
            if "Production Plan is required" in error_msg:
                return {
                    "status": "error", 
                    "message": f"SPR validation error: {error_msg}. Check that Production Plan {pp_id} exists."
                }
            frappe.log_error(frappe.get_traceback(), "create_item_spr_insert")
            return {"status": "error", "message": f"Failed to create SPR: {error_msg}"}
        
        # Link SPR back to Production Plan — append to existing value instead of overwriting
        existing_spr_link = str(frappe.db.get_value("Production Plan", pp_id, "custom_shaft_production_run_id") or "").strip()
        if spr.name not in existing_spr_link:
            new_link = f"{existing_spr_link}, {spr.name}".strip(", ") if existing_spr_link else spr.name
            frappe.db.set_value("Production Plan", pp_id, "custom_shaft_production_run_id", new_link)
        _link_items_to_spr(spr.name)
        
        frappe.db.commit()
        
        return {
            "status": "ok",
            "spr_id": spr.name,
            "message": f"SPR Created: {spr.name}"
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_item_spr")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


@frappe.whitelist()
def get_spr_shaft_jobs_from_pp(pp_id):
    """Return normalized shaft jobs from a Production Plan for SPR form auto-fill."""
    pp_id = str(pp_id or "").strip()
    if not pp_id:
        return {"status": "error", "message": "Production Plan is required", "jobs": []}

    if not frappe.db.exists("Production Plan", pp_id):
        return {
            "status": "error",
            "message": f"Production Plan {pp_id} not found",
            "jobs": [],
        }

    try:
        pp = frappe.get_doc("Production Plan", pp_id)
        jobs = []
        shafts = pp.get("custom_shaft_details") or pp.get("shaft_details") or []

        # Fetch linked Work Orders for WO name enrichment
        pp_work_orders = frappe.get_all("Work Order",
            filters={"production_plan": pp_id, "docstatus": ["<", 2]},
            fields=["name", "qty"],
            order_by="creation asc"
        )
        wo_names_str = ", ".join([wo.name for wo in pp_work_orders]) if pp_work_orders else ""
        wo_total_qty = sum(flt(wo.qty) for wo in pp_work_orders)

        def pick_value(source, keys, default=None):
            for k in keys:
                v = source.get(k)
                if v not in (None, ""):
                    return v
            return default

        # PP-level fallback values
        pp_net_weight = (
            pp.get("custom_net_weight") or pp.get("net_weight") or
            pp.get("custom_net_weight_kgs") or pp.get("net_weight_kgs") or
            pp.get("custom_weight_per_roll") or pp.get("weight_per_roll") or ""
        )
        pp_total_weight = flt(
            pp.get("custom_total_weight_kgs") or pp.get("total_weight_kgs") or
            pp.get("custom_total_weight") or pp.get("total_weight") or
            pp.get("total_planned_qty") or pp.get("custom_total_planned_qty") or 0
        )
        pp_no_of_shaft = cint(
            pp.get("custom_no_of_shaft") or pp.get("no_of_shaft") or
            pp.get("custom_no_of_shafts") or pp.get("no_of_shafts") or 0
        )
        pp_combined_width = (
            pp.get("custom_combined_width") or pp.get("combined_width") or
            pp.get("custom_total_width") or pp.get("total_width") or ""
        )

        # Log actual fields for debugging
        if shafts:
            first = shafts[0]
            raw_data = {}
            if hasattr(first, 'as_dict'):
                for k, v in first.as_dict().items():
                    if v not in (None, "", 0, 0.0) and k not in ("name", "owner", "creation", "modified", "modified_by", "doctype", "parent", "parentfield", "parenttype", "docstatus", "idx"):
                        raw_data[k] = str(v)[:200]
            frappe.log_error(f"PP {pp_id} shaft row fields: {json.dumps(raw_data, indent=2)}", "SPR_DEBUG_SHAFT_FIELDS")

        # Also try standard PP FINISHED GOODS table (po_items) for enrichment
        pp_po_items = pp.get("po_items") or []
        po_item_data = {}
        for poi in pp_po_items:
            # Build a lookup by index for width/weight enrichment
            idx = cint(poi.get("idx") or 0)
            po_item_data[idx] = poi

        for idx, pp_shaft in enumerate(shafts, start=1):
            # Get matching po_item for additional data
            matching_poi = po_item_data.get(idx, {})
            
            # For net_weight: try shaft row first, then po_item weight_per_unit/planned_qty
            raw_net_weight = pick_value(pp_shaft, ["net_weight_shaft_kgs", "net_weight_shaft", "net_weight", "weight_per_roll", "weight_roll", "weight"], "") or pp_net_weight
            if not raw_net_weight and matching_poi:
                raw_net_weight = pick_value(matching_poi, ["net_weight", "weight_per_roll", "weight_roll", "stock_qty"], "")

            # For total_weight: try shaft row, then matching po_item planned_qty
            raw_total_weight = flt(pick_value(pp_shaft, ["total_weight_kgs", "total_weight", "weight", "planned_qty"], 0) or 0) or pp_total_weight
            if not flt(raw_total_weight) and matching_poi:
                raw_total_weight = flt(pick_value(matching_poi, ["total_weight_kgs", "planned_qty", "qty", "stock_qty"], 0) or 0)

            # For total_width
            raw_width = flt(pick_value(pp_shaft, ["total_width", "combined_width", "width", "total_width_inches"], 0) or 0)
            if not flt(raw_width) and matching_poi:
                raw_width = flt(pick_value(matching_poi, ["total_width", "width", "width_inches"], 0) or 0)

            jobs.append(
                {
                    "job_id": pick_value(pp_shaft, ["job_id", "job", "job_no"], str(idx)),
                    "gsm": pick_value(pp_shaft, ["gsm"], ""),
                    "combination": pick_value(pp_shaft, ["combination", "combined_width", "shaft", "shaft_details"], "") or pp_combined_width,
                    "total_width": raw_width,
                    "meter_roll_mtrs": flt(pick_value(pp_shaft, ["meter__roll", "meter_roll_mtrs", "meter_per_roll", "meter_roll", "roll_mtrs", "custom_meter_roll_mtrs", "custom_meter_per_roll", "meter_per_roll_mtrs", "roll", "meter"], 0) or flt(pp.get("meter__roll") or pp.get("custom_meter_roll_mtrs") or pp.get("meter_roll_mtrs") or pp.get("custom_meter_per_roll") or pp.get("meter_per_roll") or pp.get("custom_meter") or pp.get("meter") or 500)),
                    "no_of_shafts": cint(pick_value(pp_shaft, ["no_of_shafts", "no_of_shaft", "no_of_sh", "no_of_sf"], 0) or 0) or pp_no_of_shaft or 1,
                    "net_weight": raw_net_weight,
                    "net_weight_shaft_kgs": raw_net_weight,
                    "total_weight_kgs": raw_total_weight,
                    "total_weight": raw_total_weight,
                    "order_code": pick_value(pp_shaft, ["order_code", "party_code", "custom_order_code"], pp.get("order_code") or pp.get("custom_order_code") or ""),
                    "work_orders": pick_value(pp_shaft, ["work_orders", "work_order", "wo", "wo_no"], "") or wo_names_str,
                    "custom_label": pick_value(pp_shaft, ["custom_label", "label"], ""),
                }
            )

            # Enrich total_weight from WO qty if shaft row has zero weight
            if not flt(jobs[-1]["total_weight_kgs"]) and wo_total_qty:
                jobs[-1]["total_weight_kgs"] = flt(wo_total_qty)

            # Resolve work_orders from combination + GSM (e.g. 46"+42"+38" → three WOs on the PP)
            try:
                from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
                    _resolve_wos_for_pp_job_row,
                )

                jrow = jobs[-1]
                jid = jrow.get("job_id")
                comb = jrow.get("combination") or ""
                ppi = pick_value(pp_shaft, ["production_plan_item", "pp_item"], None) or jid
                job_gsm = None
                gsm_raw = jrow.get("gsm")
                if gsm_raw not in (None, ""):
                    try:
                        job_gsm = int(flt(str(gsm_raw).strip().split()[0]))
                    except Exception:
                        try:
                            job_gsm = int(flt(gsm_raw))
                        except Exception:
                            pass
                ppi_s = str(ppi).strip() if ppi not in (None, "") else None
                jid_s = str(jid).strip() if jid not in (None, "") else None
                ww = _resolve_wos_for_pp_job_row(
                    pp_id,
                    ppi=ppi_s,
                    job_id=jid_s,
                    row_index=idx - 1,
                    combination=comb if comb else None,
                    job_gsm=job_gsm,
                )
                if ww:
                    jrow["work_orders"] = ", ".join(w["name"] for w in ww)
            except Exception:
                pass

        # Build debug info to discover actual field names
        _debug = {
            "shaft_count": len(shafts),
            "pp_level_fields": {},
            "first_shaft_row_all_fields": {},
        }
        # PP-level fields related to weight/shaft
        for attr in dir(pp):
            if any(kw in attr.lower() for kw in ["weight", "shaft", "width", "net", "total", "combined"]):
                val = pp.get(attr)
                if val not in (None, "", 0, 0.0, []):
                    _debug["pp_level_fields"][attr] = str(val)[:100]
        # First shaft child row: dump ALL non-empty fields
        if shafts:
            first = shafts[0]
            for attr in (first.as_dict() if hasattr(first, 'as_dict') else {}):
                val = first.get(attr)
                if val not in (None, "", 0, 0.0) and attr not in ("name", "owner", "creation", "modified", "modified_by", "doctype", "parent", "parentfield", "parenttype", "docstatus"):
                    _debug["first_shaft_row_all_fields"][attr] = str(val)[:100]

        return {
            "status": "ok",
            "pp_id": pp_id,
            "jobs": jobs,
            "customer": pp.get("customer") or "",
            "order_code": pp.get("order_code") or pp.get("custom_order_code") or "",
            "_debug": _debug,
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_spr_shaft_jobs_from_pp")
        return {
            "status": "error",
            "message": "Unable to fetch shaft details from Production Plan",
            "jobs": [],
        }


@frappe.whitelist()
def debug_pp_columns(pp_id):
    """Dump ALL non-empty columns of a PP doc via SQL - to discover actual field names."""
    if not frappe.db.exists("Production Plan", pp_id):
        return {"error": f"PP {pp_id} not found"}

    # Get all column names from tabProduction Plan
    cols = frappe.db.sql("SHOW COLUMNS FROM `tabProduction Plan`", as_dict=True)
    col_names = [c["Field"] for c in cols]

    # Fetch the PP row
    pp_row = frappe.db.sql(
        "SELECT * FROM `tabProduction Plan` WHERE name = %s", pp_id, as_dict=True
    )
    if not pp_row:
        return {"error": "Not found"}

    pp_data = pp_row[0]
    # Return only non-empty values, filter weight/shaft/net/total/width related
    relevant = {}
    all_non_empty = {}
    for k, v in pp_data.items():
        if v not in (None, "", 0, 0.0):
            all_non_empty[k] = str(v)[:100]
            if any(kw in k.lower() for kw in ["weight", "shaft", "net", "total", "width", "combined"]):
                relevant[k] = str(v)[:100]

    # Also check child table
    child_table_info = {}
    try:
        child_cols = frappe.db.sql("SHOW COLUMNS FROM `tabProduction Plan Item`", as_dict=True)
        child_col_names = [c["Field"] for c in child_cols if any(kw in c["Field"].lower() for kw in ["weight", "shaft", "net", "total", "width", "combined", "qty"])]
        child_table_info["columns"] = child_col_names
    except Exception:
        pass

    # PP custom_shaft_details child table
    shaft_child = frappe.db.sql(
        """SELECT * FROM `tabProduction Plan Item`
           WHERE parent = %s ORDER BY idx LIMIT 1""",
        pp_id, as_dict=True
    )
    shaft_row_data = {}
    if shaft_child:
        for k, v in shaft_child[0].items():
            if v not in (None, "", 0, 0.0) and k not in ("name", "owner", "creation", "modified", "modified_by", "parent", "parentfield", "parenttype", "docstatus"):
                shaft_row_data[k] = str(v)[:100]

    return {
        "pp_relevant_fields": relevant,
        "po_item_first_row_non_empty": shaft_row_data,
        "child_table_weight_cols": child_table_info,
    }


# ============================================================================
# PRODUCTION MERGE APIs
# ============================================================================

def _get_item_merge_key(item_name):
    """Get order_code + quality + color key for merge validation."""
    try:
        item = frappe.db.get_value(
            "Planning Table",
            item_name,
            ["custom_quality", "color", "parent"],
            as_dict=True
        )
        if not item:
            return None
        
        ps = frappe.db.get_value("Planning sheet", item.get("parent"), "party_code")
        quality = (item.get("custom_quality") or "").strip()
        color = (item.get("color") or "").strip()
        
        return f"{ps}||{quality}||{color}"
    except Exception:
        return None


def _validate_merge_items(item_names):
    """Validate that all items have same order_code + quality + color."""
    if not item_names or len(item_names) < 2:
        return True, "At least 2 items required to merge"
    
    keys = []
    for item_name in item_names:
        key = _get_item_merge_key(item_name)
        if not key:
            return False, f"Item {item_name} not found or invalid"
        keys.append(key)
    
    # All keys must be identical
    if len(set(keys)) != 1:
        return False, "All items must have same Order Code + Quality + Color to merge"
    
    return True, "Valid"


def _get_merge_row_name(merged_items):
    """Generate a safe row name from merged items."""
    import hashlib
    items_str = ",".join(sorted(merged_items))
    hash_suffix = hashlib.md5(items_str.encode()).hexdigest()[:6]
    return f"MERGE_{hash_suffix}"


@frappe.whitelist()
def create_merge(date, unit, plan_name, item_names, merge_label=None):
    """Create a new Production Merge record."""
    if isinstance(item_names, str):
        import json
        item_names = json.loads(item_names)
    
    if not isinstance(item_names, list):
        frappe.throw("item_names must be a list or JSON array")
    
    # Validate merge constraints
    valid, msg = _validate_merge_items(item_names)
    if not valid:
        frappe.throw(msg)

    # Capacity check: merged target weight must not exceed unit hard limit
    hard_limit_tons = HARD_LIMITS.get(unit)
    if hard_limit_tons:
        fmt = ','.join(['%s'] * len(item_names))
        total_kg = frappe.db.sql(f"""
            SELECT SUM(IFNULL(qty, 0))
            FROM `tabPlanning Table`
            WHERE name IN ({fmt})
        """, tuple(item_names))[0][0] or 0
        if flt(total_kg) > flt(hard_limit_tons) * 1000:
            frappe.throw("Selected merge weight {0} Kg exceeds {1} capacity {2} Kg".format(
                flt(total_kg),
                unit,
                flt(hard_limit_tons) * 1000
            ))
    
    # Check for overlap with existing merges
    existing_merges = frappe.db.sql("""
        SELECT name, merged_items
        FROM `tabProduction Merge`
        WHERE date = %s AND unit = %s AND plan_name = %s AND status = 'Active'
    """, (date, unit, plan_name), as_dict=True)
    
    for merge in existing_merges:
        import json
        existing_items = json.loads(merge.get("merged_items") or "[]")
        overlap = set(item_names) & set(existing_items)
        if overlap:
            frappe.throw("Items already in another merge: {}".format(", ".join(overlap)))
    
    # Create new merge record.
    # NOTE: The DocType autoname expression can collide for same unit/date,
    # so we provide our own unique name and retry safely.
    import json
    from frappe.exceptions import DuplicateEntryError

    base_name = f"PMRG-{str(unit).replace(' ', '')}-{str(date)}"
    last_error = None
    for attempt_idx in range(5):
        unique_name = f"{base_name}-{frappe.generate_hash(length=6)}"
        merge_doc = frappe.new_doc("Production Merge")
        merge_doc.name = unique_name
        merge_doc.flags.name_set = True
        merge_doc.plan_name = plan_name
        merge_doc.date = date
        merge_doc.unit = unit
        merge_doc.merge_label = merge_label or _get_merge_row_name(item_names)
        merge_doc.status = "Active"
        merge_doc.merged_items = json.dumps(item_names)
        try:
            merge_doc.insert(ignore_permissions=True, set_name=unique_name)
            return {"status": "success", "merge_id": merge_doc.name}
        except DuplicateEntryError as e:
            last_error = e
            continue

    if last_error:
        frappe.throw("Unable to create merge due to repeated duplicate name collision. Please try again.")

    frappe.throw("Unable to create merge")


@frappe.whitelist()
def update_merge(merge_id, merge_label=None, status=None):
    """Update merge label or status."""
    if not frappe.db.exists("Production Merge", merge_id):
        frappe.throw(_("Merge record not found"))
    
    merge_doc = frappe.get_doc("Production Merge", merge_id)
    
    if merge_label:
        merge_doc.merge_label = merge_label
    
    if status and status in ["Active", "Inactive"]:
        merge_doc.status = status
    
    merge_doc.save()
    return {"status": "success"}


@frappe.whitelist()
def delete_merge(merge_id):
    """Delete a merge record and revert items to original positions."""
    if not frappe.db.exists("Production Merge", merge_id):
        frappe.throw(_("Merge record not found"))

    merge_doc = frappe.get_doc("Production Merge", merge_id)
    import json
    merged_items = json.loads(merge_doc.merged_items or "[]")

    if merged_items:
        fmt = ','.join(['%s'] * len(merged_items))
        dispatched = frappe.db.sql(f"""
            SELECT DISTINCT COALESCE(so.delivery_status, 'Not Delivered') as delivery_status
            FROM `tabPlanning Table` i
            JOIN `tabPlanning sheet` p ON i.parent = p.name
            LEFT JOIN `tabSales Order` so ON p.sales_order = so.name
            WHERE i.name IN ({fmt})
        """, tuple(merged_items), as_dict=True)

        locked = any((r.get("delivery_status") or "") in ["Partly Delivered", "Fully Delivered"] for r in dispatched)
        if locked:
            frappe.throw("Cannot unmerge: one or more merged items are already dispatched.")
    
    frappe.delete_doc("Production Merge", merge_id)
    return {"status": "success"}


@frappe.whitelist()
def get_merges_for_date(date, unit=None, plan_name=None):
    """Fetch all active merges for a specific date/unit/plan."""
    filters = ["date = %s", "status = 'Active'"]
    params = [date]
    
    if unit:
        filters.append("unit = %s")
        params.append(unit)
    
    if plan_name:
        filters.append("plan_name = %s")
        params.append(plan_name)
    
    where_clause = " AND ".join(filters)
    
    merges = frappe.db.sql(f"""
        SELECT name, unit, plan_name, date, merge_label, status, merged_items
        FROM `tabProduction Merge`
        WHERE {where_clause}
        ORDER BY creation ASC
    """, tuple(params), as_dict=True)
    
    # Parse merged_items JSON for each merge
    import json
    for merge in merges:
        try:
            merge["merged_items"] = json.loads(merge.get("merged_items") or "[]")
        except:
            merge["merged_items"] = []
    
    return merges


@frappe.whitelist()
def sync_merge_planned_date(merge_id, new_date):
    """Sync planned_date change from merged row back to all items in merge."""
    if not frappe.db.exists("Production Merge", merge_id):
        frappe.throw(_("Merge record not found"))
    
    merge_doc = frappe.get_doc("Production Merge", merge_id)
    
    import json
    merged_items = json.loads(merge_doc.merged_items or "[]")
    
    if not merged_items:
        return {"status": "success", "updated": 0}
    
    # Update each item's planned_date if the column exists
    updated_count = 0
    if frappe.db.has_column("Planning Table", "custom_planned_date"):
        for item_name in merged_items:
            frappe.db.set_value("Planning Table", item_name, "custom_planned_date", new_date)
            updated_count += 1
    
    return {"status": "success", "updated": updated_count}
