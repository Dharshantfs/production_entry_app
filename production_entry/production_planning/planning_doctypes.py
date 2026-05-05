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
SHEET_CUTTING_UNIT = "JVE - SHEET CUTTING MACHINE"

# Unit number / alpha code embedded in batch/order codes at position 2.
# Example order code "051263" → digit at index 2 = "1" = Unit 1
UNIT_NUMBER_MAP = {
    "Unit 1":                         "1",
    "Unit 2":                         "2",
    "Unit 3":                         "3",
    "Unit 4":                         "4",
    "Lamination Unit":                "5",
    "Slitting Unit":                  "6",
    "TSNPL - L3 REWINDING MACHINE":   "7",
    "JSB - L4 REWINDING MACHINE":     "8",
    "JSB - L5 REWINDING MACHINE":     "9",
    "JVE - SHEET CUTTING MACHINE":    "S",
    "VR - 1200MM BOPP PRINTING MACHINE": "V",
}


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
        SHEET_CUTTING_UNIT,
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
    if "JVESHEETCUTTINGMACHINE" in u or ("SHEETCUTTING" in u and "JVE" in u):
        return SHEET_CUTTING_UNIT
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
		SHEET_CUTTING_UNIT,
		"VR - 1200MM BOPP PRINTING MACHINE",
	)
)


def _canonical_planning_unit_option_line_set():
	"""Set of canonical ``unit`` option lines for strict DB sync checks."""
	return frozenset(
		line.strip()
		for line in (CANONICAL_PLANNING_LINE_UNIT_OPTIONS or "").split("\n")
		if line.strip()
	)


def _stored_unit_select_outdated(opts):
	"""
	Some sites have Planning sheet Item stuck at e.g. UNASSIGNED…VR BOPP **without**
	L3/L4/L5/Unassigned rewinding rows; substring checks on ``Unassigned rewinding machine`` wrongly skip.
	Use full line-set equality with canonical.
	"""
	got = frozenset(line.strip() for line in str(opts or "").split("\n") if line.strip())
	return got != _canonical_planning_unit_option_line_set()


def ensure_planning_line_unit_docfield_options():
	"""
	Sync ``tabDocField.options`` for both child line DocTypes so Desk + validate accept rewinding / VR BOPP units.

	Sites can have Planning sheet Item (legacy grid) missing rewinding machines while Planning Table (board) is fine.
	Idempotent when ``tabDocField`` already matches canonical.
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
		if not _stored_unit_select_outdated(opts):
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
