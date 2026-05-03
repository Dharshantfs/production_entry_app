# -*- coding: utf-8 -*-
"""
Canonical Planning DocType names — must match planning_sheet*.json and live DB (`tabPlanning sheet`).

Use these constants anywhere code references the doctype string (no literals like "Planning Sheet").
"""

PLANNING_SHEET = "Planning sheet"
PLANNING_SHEET_ITEM = "Planning sheet Item"

# When True: Planning sheet finalize only links Work Orders from existing Production Plans (no auto PP insert).
# Set False for legacy behaviour that created one Production Plan per line on sheet submit.
PLANNING_SHEET_SUBMIT_LINKS_WORK_ORDERS_ONLY = True

# Must match `Planning Table` child `unit` Select options (planning_table.json).
REWINDING_UNIT_L3 = "TSNPL - L3 REWINDING MACHINE"
REWINDING_UNIT_L4 = "JSB - L4 REWINDING MACHINE"
REWINDING_UNIT_L5 = "JSB - L5 REWINDING MACHINE"
REWINDING_UNASSIGNED_UNIT = "Unassigned rewinding machine"


def normalize_planning_unit_for_select(raw, _depth=0):
    """Map free-text to exact options on Planning Table / Planning sheet Item `unit` (Select)."""
    if raw is None:
        return "UNASSIGNED"
    s = str(raw).strip()
    if not s:
        return "UNASSIGNED"
    # Color Chart matrix column id: sheetCode|unit|planCode|gsm|quality — normalize only the unit segment.
    if _depth == 0 and "|" in s:
        parts = [p.strip() for p in s.split("|")]
        if len(parts) >= 2 and parts[1]:
            return normalize_planning_unit_for_select(parts[1], _depth + 1)
    allowed = (
        "UNASSIGNED",
        "Unit 1",
        "Unit 2",
        "Unit 3",
        "Unit 4",
        "Lamination Unit",
        "Slitting Unit",
        REWINDING_UNIT_L3,
        REWINDING_UNIT_L4,
        REWINDING_UNIT_L5,
        REWINDING_UNASSIGNED_UNIT,
        "VR - 1200MM BOPP PRINTING MACHINE",
    )
    if s in allowed:
        return s
    u = s.upper().replace(" ", "").replace("_", "")
    if u in ("UNASSIGNED", "NONE", "NA", ""):
        return "UNASSIGNED"
    if u == "MIXED":
        return "UNASSIGNED"
    if u == "LAMINATIONUNIT" or s.strip().lower() == "lamination unit":
        return "Lamination Unit"
    if u == "SLITTINGUNIT" or s.strip().lower() == "slitting unit":
        return "Slitting Unit"
    if "REWINDING" in u or "REWINDINGMACHINE" in u.replace(" ", ""):
        if "L3" in u and "TSNPL" in u:
            return REWINDING_UNIT_L3
        if "L4" in u and "JSB" in u:
            return REWINDING_UNIT_L4
        if "L5" in u and "JSB" in u:
            return REWINDING_UNIT_L5
        if "UNASSIGNED" in u:
            return REWINDING_UNASSIGNED_UNIT
    if "VR1200MMBOPPPRINTINGMACHINE" in u or "1200MMBOPP" in u:
        return "VR - 1200MM BOPP PRINTING MACHINE"
    for i in (1, 2, 3, 4):
        if f"UNIT{i}" in u or s == f"Unit {i}":
            return f"Unit {i}"
    return "UNASSIGNED"


# Old names from earlier app JSON / deploys (for migration helpers only).
LEGACY_PLANNING_SHEET = "Planning Sheet"
LEGACY_PLANNING_SHEET_ITEM = "Planning Sheet Item"

# Exact ``unit`` Select options for Planning Table + Planning sheet Item (must match planning_table.json / planning_sheet_item.json).
CANONICAL_PLANNING_LINE_UNIT_OPTIONS = "\n".join(
	(
		"UNASSIGNED",
		"Unit 1",
		"Unit 2",
		"Unit 3",
		"Unit 4",
		"Lamination Unit",
		"Slitting Unit",
		REWINDING_UNIT_L3,
		REWINDING_UNIT_L4,
		REWINDING_UNIT_L5,
		REWINDING_UNASSIGNED_UNIT,
		"VR - 1200MM BOPP PRINTING MACHINE",
	)
)


def ensure_planning_line_unit_docfield_options():
	"""
	Sync ``tabDocField.options`` for both child line DocTypes so Desk + validate accept rewinding / VR BOPP units.

	Sites that ran an older ``resync_planning_unit_field_options`` patch can have Planning sheet Item (legacy grid)
	stuck on a shortened list while Planning Table (board) was updated — inserts then fail on ``Unassigned rewinding machine``.
	Idempotent: no-op when options already include ``REWINDING_UNASSIGNED_UNIT``.
	"""
	import frappe

	for dt in ("Planning Table", PLANNING_SHEET_ITEM):
		try:
			opts = frappe.db.get_value(
				"DocField",
				{"parent": dt, "fieldname": "unit", "fieldtype": "Select"},
				"options",
			)
		except Exception:
			continue
		if opts and REWINDING_UNASSIGNED_UNIT in (opts or ""):
			continue
		try:
			frappe.db.sql(
				"""
				UPDATE `tabDocField`
				SET `options`=%s
				WHERE `parent`=%s AND `fieldname`=%s AND `fieldtype`='Select'
				""",
				(CANONICAL_PLANNING_LINE_UNIT_OPTIONS, dt, "unit"),
			)
			for ps in frappe.get_all(
				"Property Setter",
				filters={"doc_type": dt, "field_name": "unit", "property": "options"},
				pluck="name",
			) or []:
				try:
					frappe.delete_doc("Property Setter", ps, force=True, ignore_missing=True)
				except Exception:
					pass
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"ensure_planning_line_unit_docfield_options:{dt}")
	try:
		frappe.clear_cache(doctype="Planning Table")
		frappe.clear_cache(doctype=PLANNING_SHEET_ITEM)
	except Exception:
		pass
