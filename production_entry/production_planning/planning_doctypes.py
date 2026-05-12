# -*- coding: utf-8 -*-
"""
Canonical Planning DocType names — must match planning_sheet*.json and live DB (`tabPlanning sheet`).

Use these constants anywhere code references the doctype string (no literals like "Planning Sheet").
``unit`` is a Link to Workstation — stored values MUST match ``tabWorkstation.name`` exactly.
"""

PLANNING_SHEET = "Planning sheet"
PLANNING_SHEET_ITEM = "Planning sheet Item"

# When True: Planning sheet finalize only links Work Orders from existing Production Plans (no auto PP insert).
# Set False for legacy behaviour that created one Production Plan per line on sheet submit.
PLANNING_SHEET_SUBMIT_LINKS_WORK_ORDERS_ONLY = True

# Workstation names (`tabWorkstation.name`) — aligned with ERPNext master data.
LAMINATION_UNIT = "TNSPL - LAMINATION UNIT"
SLITTING_UNIT = "JVE - SLITTING MACHINE"
REWINDING_UNIT_L3 = "TSNPL - L3 REWINDING MACHINE"
REWINDING_UNIT_L4 = "JSB - L4 REWINDING MACHINE"
REWINDING_UNIT_L5 = "JSB - L5 REWINDING MACHINE"
REWINDING_UNASSIGNED_UNIT = "UNASSIGNED REWINDING UNIT"
SHEET_CUTTING_UNIT = "JVE - SHEET CUTTING MACHINE"
PRINTED_BOPP_FILM_UNIT = "VR - 1200MM BOPP PRINTING MACHINE"
PRINTING_UNASSIGNED_UNIT = "UNASSIGNED PRINTING MACHINE"
PRINTING_UNIT_2_COLOUR = "JVE - PRINTING MACHINE 2 COLOUR 1600MM"
PRINTING_UNIT_4_COLOUR = "JVE - PRINTING MACHINE 4 COLOUR 1600MM"
PRINTING_UNIT_TT = "TT - PRINTING MACHINE 4 COLOUR 1200MM"

# Old Select / spreadsheet labels → current Workstation name (for normalize + migrations).
LEGACY_PLANNING_UNIT_ALIASES = {
    "Lamination Unit": LAMINATION_UNIT,
    "Slitting Unit": SLITTING_UNIT,
    "Unassigned rewinding machine": REWINDING_UNASSIGNED_UNIT,
    "Unassigned printing machine": PRINTING_UNASSIGNED_UNIT,
    "TT - PRINTING MACHINE COLOUR 1200MM": PRINTING_UNIT_TT,
    # Title-case laminations typo / paste variants
    "TNSPL - LAMINATION UNIT": LAMINATION_UNIT,
}

# Unit number / alpha code embedded in batch/order codes at position 2.
# Example order code "051263" → digit at index 2 = "1" = Unit 1
UNIT_NUMBER_MAP = {
    "Unit 1": "1",
    "Unit 2": "2",
    "Unit 3": "3",
    "Unit 4": "4",
    LAMINATION_UNIT: "5",
    SLITTING_UNIT: "6",
    REWINDING_UNIT_L3: "7",
    REWINDING_UNIT_L4: "8",
    REWINDING_UNIT_L5: "9",
    SHEET_CUTTING_UNIT: "S",
    PRINTED_BOPP_FILM_UNIT: "V",
}


def normalize_planning_unit_for_select(raw, _depth=0):
    """Resolve ``unit`` to exact Workstation name (or UNASSIGNED / Unit N). Accepts legacy Select labels."""
    if raw is None:
        return "UNASSIGNED"
    s = str(raw).strip()
    if not s:
        return "UNASSIGNED"
    if s in LEGACY_PLANNING_UNIT_ALIASES:
        return LEGACY_PLANNING_UNIT_ALIASES[s]
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
        LAMINATION_UNIT,
        SLITTING_UNIT,
        REWINDING_UNIT_L3,
        REWINDING_UNIT_L4,
        REWINDING_UNIT_L5,
        REWINDING_UNASSIGNED_UNIT,
        SHEET_CUTTING_UNIT,
        PRINTED_BOPP_FILM_UNIT,
        PRINTING_UNASSIGNED_UNIT,
        PRINTING_UNIT_2_COLOUR,
        PRINTING_UNIT_4_COLOUR,
        PRINTING_UNIT_TT,
    )
    if s in allowed:
        return s
    u = s.upper().replace(" ", "").replace("_", "")
    if u in ("UNASSIGNED", "NONE", "NA", ""):
        return "UNASSIGNED"
    if u == "MIXED":
        return "UNASSIGNED"
    if u == "LAMINATIONUNIT" or s.strip().lower() == "lamination unit":
        return LAMINATION_UNIT
    if u == "SLITTINGUNIT" or s.strip().lower() == "slitting unit":
        return SLITTING_UNIT
    if "REWINDING" in u:
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
    if "JVESLITTINGMACHINE" in u or ("SLITTING" in u and "JVE" in u and "MACHINE" in u):
        return SLITTING_UNIT
    if "TNSPL" in u and "LAMINATION" in u:
        return LAMINATION_UNIT
    if "PRINTINGMACHINE2COLOUR" in u and "1600" in u:
        return PRINTING_UNIT_2_COLOUR
    if "PRINTINGMACHINE2COLOUR" in u or ("PRINTING" in u and "2COLOUR" in u):
        return PRINTING_UNIT_2_COLOUR
    if "PRINTINGMACHINE4COLOUR" in u and "1600" in u:
        return PRINTING_UNIT_4_COLOUR
    if "PRINTINGMACHINE4COLOUR" in u or ("PRINTING" in u and "4COLOUR" in u):
        return PRINTING_UNIT_4_COLOUR
    if "TT" in u and "PRINTING" in u and "1200" in u:
        return PRINTING_UNIT_TT
    if u.startswith("TT") and "PRINTING" in u:
        return PRINTING_UNIT_TT
    if "PRINTING" in u and "UNASSIGNED" in u:
        return PRINTING_UNASSIGNED_UNIT
    if "VR1200MMBOPPPRINTINGMACHINE" in u or "1200MMBOPP" in u:
        return PRINTED_BOPP_FILM_UNIT
    for i in (1, 2, 3, 4):
        if f"UNIT{i}" in u or s == f"Unit {i}":
            return f"Unit {i}"
    return "UNASSIGNED"


def planning_line_unit_option_lines():
    """Distinct ``unit`` values we use for planning rows (documentation / optional validation)."""
    return sorted(
        {
            "UNASSIGNED",
            "Unit 1",
            "Unit 2",
            "Unit 3",
            "Unit 4",
            LAMINATION_UNIT,
            SLITTING_UNIT,
            REWINDING_UNIT_L3,
            REWINDING_UNIT_L4,
            REWINDING_UNIT_L5,
            REWINDING_UNASSIGNED_UNIT,
            SHEET_CUTTING_UNIT,
            PRINTED_BOPP_FILM_UNIT,
        }
    )


# Deprecated: was Select newline options; retained for migrations / logging only (not synced to DocField when Link).
CANONICAL_PLANNING_LINE_UNIT_OPTIONS = "\n".join(planning_line_unit_option_lines())


def _canonical_planning_unit_option_line_set():
	return frozenset(line.strip() for line in planning_line_unit_option_lines())


def _stored_unit_select_outdated(opts):
	"""
	Legacy helper: compares old Select lists. Unused when ``unit`` is Link (``ensure`` skips non-Select).
	"""
	got = frozenset(line.strip() for line in str(opts or "").split("\n") if line.strip())
	return got != _canonical_planning_unit_option_line_set()


def ensure_planning_line_unit_docfield_options():
	"""
	Legacy Select sync — no-op when ``unit`` is Link to Workstation.

	Older sites synced ``tabDocField.options`` here; Links use ``options``='Workstation' from DocType JSON.
	"""
	import frappe

	for dt in ("Planning Table", PLANNING_SHEET_ITEM):
		try:
			fieldtype = frappe.db.get_value(
				"DocField",
				{"parent": dt, "fieldname": "unit"},
				"fieldtype",
			)
		except Exception:
			continue
		if (fieldtype or "") != "Select":
			continue
		opts = frappe.db.get_value(
			"DocField",
			{"parent": dt, "fieldname": "unit", "fieldtype": "Select"},
			"options",
		)
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


# Old names from earlier app JSON / deploys (for migration helpers only).
LEGACY_PLANNING_SHEET = "Planning Sheet"
LEGACY_PLANNING_SHEET_ITEM = "Planning Sheet Item"
