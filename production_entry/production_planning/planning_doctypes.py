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
SLITTING_UNIT_VTP = "VTP - SLITTING MACHINE"
SLITTING_UNASSIGNED_UNIT = "UNASSIGNED SLITTING MACHINE"
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
BOX_BAG_UNIT_L1 = "VTP-L1 LEADER OYANG MACHINE"
BOX_BAG_UNIT_L2 = "VTP-L2 LEADER ZX MACHINE"
BOX_BAG_UNIT_L4_SCREEN = "VTP-L4 SCREEN PRINTING MACHINE"
# Legacy names (pre-rename) — map to VTP workstations on read/migrate.
LEGACY_BOX_BAG_UNIT_L1 = "L1 LEADER OYANG MACHINE"
LEGACY_BOX_BAG_UNIT_L2 = "L2 LEADER ZX MACHINE"
BOX_BAG_UNASSIGNED_UNIT = "UNASSIGNED BOX BAG MACHINE"
W_CUT_D_CUT_UNIT_JVE_L1 = "JVE-L1  B700 BAG MAKING MACHINE"
W_CUT_D_CUT_UNIT_JVE_L2 = "JVE-L2  B700 BAG MAKING MACHINE"
W_CUT_D_CUT_UNIT_JVE_L3 = "JVE-L3  B700 BAG MAKING MACHINE"
W_CUT_D_CUT_UNIT_L1 = "TTT- L1 - OYANG C700 BAG MAKING LINE"
W_CUT_D_CUT_UNIT_L2 = "TTT- L2 - OYANG C700 BAG MAKING LINE"
W_CUT_D_CUT_UNIT_L3 = "TTT- L3 - OYANG C900 BAG MAKING LINE"
W_CUT_UNASSIGNED_UNIT = "UNASSIGNED W CUT BAG MACHINE"
D_CUT_UNASSIGNED_UNIT = "UNASSIGNED D CUT BAG MACHINE"

W_CUT_D_CUT_JVE_UNITS = (
	W_CUT_D_CUT_UNIT_JVE_L1,
	W_CUT_D_CUT_UNIT_JVE_L2,
	W_CUT_D_CUT_UNIT_JVE_L3,
	W_CUT_UNASSIGNED_UNIT,
	D_CUT_UNASSIGNED_UNIT,
)
W_CUT_D_CUT_VTP_UNITS = (
	W_CUT_D_CUT_UNIT_L1,
	W_CUT_D_CUT_UNIT_L2,
	W_CUT_D_CUT_UNIT_L3,
	W_CUT_UNASSIGNED_UNIT,
	D_CUT_UNASSIGNED_UNIT,
)
W_CUT_D_CUT_MACHINE_UNITS = (
	W_CUT_D_CUT_UNIT_JVE_L1,
	W_CUT_D_CUT_UNIT_JVE_L2,
	W_CUT_D_CUT_UNIT_JVE_L3,
	W_CUT_D_CUT_UNIT_L1,
	W_CUT_D_CUT_UNIT_L2,
	W_CUT_D_CUT_UNIT_L3,
)
W_CUT_D_CUT_ALL_UNITS = W_CUT_D_CUT_MACHINE_UNITS + (
	W_CUT_UNASSIGNED_UNIT,
	D_CUT_UNASSIGNED_UNIT,
)

# Old Select / spreadsheet labels → current Workstation name (for normalize + migrations).
LEGACY_PLANNING_UNIT_ALIASES = {
    "Lamination Unit": LAMINATION_UNIT,
    "Slitting Unit": SLITTING_UNIT,
    "Unassigned slitting machine": SLITTING_UNASSIGNED_UNIT,
    "Unassigned rewinding machine": REWINDING_UNASSIGNED_UNIT,
    "Unassigned printing machine": PRINTING_UNASSIGNED_UNIT,
    "TT - PRINTING MACHINE COLOUR 1200MM": PRINTING_UNIT_TT,
    # Title-case laminations typo / paste variants
    "TNSPL - LAMINATION UNIT": LAMINATION_UNIT,
    LEGACY_BOX_BAG_UNIT_L1: BOX_BAG_UNIT_L1,
    LEGACY_BOX_BAG_UNIT_L2: BOX_BAG_UNIT_L2,
    "L1 LEADER OYANG": BOX_BAG_UNIT_L1,
    "L2 LEADER ZX": BOX_BAG_UNIT_L2,
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
    SLITTING_UNIT_VTP: "23",
    SLITTING_UNASSIGNED_UNIT: "U",
    REWINDING_UNIT_L3: "7",
    REWINDING_UNIT_L4: "8",
    REWINDING_UNIT_L5: "9",
    SHEET_CUTTING_UNIT: "S",
    PRINTED_BOPP_FILM_UNIT: "V",
    BOX_BAG_UNIT_L1: "B",
    BOX_BAG_UNIT_L2: "C",
    BOX_BAG_UNIT_L4_SCREEN: "F",
    BOX_BAG_UNASSIGNED_UNIT: "D",
    W_CUT_D_CUT_UNIT_JVE_L1: "P",
    W_CUT_D_CUT_UNIT_JVE_L2: "Q",
    W_CUT_D_CUT_UNIT_JVE_L3: "R",
    W_CUT_D_CUT_UNIT_L1: "W",
    W_CUT_D_CUT_UNIT_L2: "X",
    W_CUT_D_CUT_UNIT_L3: "Y",
    W_CUT_UNASSIGNED_UNIT: "Z",
    D_CUT_UNASSIGNED_UNIT: "E",
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
        SLITTING_UNIT_VTP,
        SLITTING_UNASSIGNED_UNIT,
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
        BOX_BAG_UNIT_L1,
        BOX_BAG_UNIT_L2,
        BOX_BAG_UNIT_L4_SCREEN,
        BOX_BAG_UNASSIGNED_UNIT,
        W_CUT_D_CUT_UNIT_JVE_L1,
        W_CUT_D_CUT_UNIT_JVE_L2,
        W_CUT_D_CUT_UNIT_JVE_L3,
        W_CUT_D_CUT_UNIT_L1,
        W_CUT_D_CUT_UNIT_L2,
        W_CUT_D_CUT_UNIT_L3,
        W_CUT_UNASSIGNED_UNIT,
        D_CUT_UNASSIGNED_UNIT,
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
    if "UNASSIGNED" in u and "SLITTING" in u:
        return SLITTING_UNASSIGNED_UNIT
    if "VTP" in u and "SLITTING" in u:
        return SLITTING_UNIT_VTP
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
    if "VTPSLITTINGMACHINE" in u or ("SLITTING" in u and "VTP" in u and "MACHINE" in u):
        return SLITTING_UNIT_VTP
    if "TNSPL" in u and "LAMINATION" in u:
        return LAMINATION_UNIT
    if "TT" in u and "PRINTING" in u and "1200" in u:
        return PRINTING_UNIT_TT
    if u.startswith("TT") and "PRINTING" in u:
        return PRINTING_UNIT_TT
    if "PRINTINGMACHINE2COLOUR" in u and "1600" in u:
        return PRINTING_UNIT_2_COLOUR
    if "PRINTINGMACHINE2COLOUR" in u or ("PRINTING" in u and "2COLOUR" in u):
        return PRINTING_UNIT_2_COLOUR
    if "PRINTINGMACHINE4COLOUR" in u and "1600" in u:
        return PRINTING_UNIT_4_COLOUR
    if "PRINTINGMACHINE4COLOUR" in u or ("PRINTING" in u and "4COLOUR" in u):
        return PRINTING_UNIT_4_COLOUR
    if "PRINTING" in u and "UNASSIGNED" in u:
        return PRINTING_UNASSIGNED_UNIT
    if "VR1200MMBOPPPRINTINGMACHINE" in u or "1200MMBOPP" in u:
        return PRINTED_BOPP_FILM_UNIT
    if "BOXBAG" in u and "UNASSIGNED" in u:
        return BOX_BAG_UNASSIGNED_UNIT
    if "VTP" in u and "L1" in u and ("LEADER" in u or "OYANG" in u):
        return BOX_BAG_UNIT_L1
    if "VTP" in u and "L2" in u and ("LEADER" in u or "ZX" in u):
        return BOX_BAG_UNIT_L2
    if "VTP" in u and "L4" in u and "SCREEN" in u:
        return BOX_BAG_UNIT_L4_SCREEN
    if "L1" in u and "LEADER" in u and "OYANG" in u:
        return BOX_BAG_UNIT_L1
    if "L2" in u and "LEADER" in u and "ZX" in u:
        return BOX_BAG_UNIT_L2
    if "WCUT" in u and "UNASSIGNED" in u:
        return W_CUT_UNASSIGNED_UNIT
    if "DCUT" in u and "UNASSIGNED" in u:
        return D_CUT_UNASSIGNED_UNIT
    if "B700BAGMAKINGMACHINE" in u and "JVE" in u:
        if "L3" in u:
            return W_CUT_D_CUT_UNIT_JVE_L3
        if "L2" in u:
            return W_CUT_D_CUT_UNIT_JVE_L2
        if "L1" in u:
            return W_CUT_D_CUT_UNIT_JVE_L1
    if "OYANGC700BAGMAKINGLINE" in u and "L1" in u and "TTT" in u:
        return W_CUT_D_CUT_UNIT_L1
    if "OYANGC700BAGMAKINGLINE" in u and "L2" in u:
        return W_CUT_D_CUT_UNIT_L2
    if "OYANGC900BAGMAKINGLINE" in u and "L3" in u:
        return W_CUT_D_CUT_UNIT_L3
    for i in (1, 2, 3, 4):
        if f"UNIT{i}" in u or s == f"Unit {i}":
            return f"Unit {i}"
    return "UNASSIGNED"


FABRIC_BOARD_ALLOCATED_UNITS = ("Unit 1", "Unit 2", "Unit 3", "Unit 4")


def normalize_allocated_to_unit_for_select(raw) -> str:
    """Map board ``unit`` to Planning sheet Item ``allocated_to_unit`` Select (Unit 1–4 or blank).

    The board uses UNASSIGNED / Mixed for the Unassigned column; ``allocated_to_unit`` only allows
    Unit 1–4 or empty — never the literal UNASSIGNED label.
    """
    norm = normalize_planning_unit_for_select(raw)
    if norm in FABRIC_BOARD_ALLOCATED_UNITS:
        return norm
    return ""


def resolve_planning_workstation_name(raw):
	"""Map planning row ``unit`` to an existing ``Workstation.name`` (exact match)."""
	import frappe

	if raw is None:
		return ""
	s = str(raw).strip()
	if not s:
		return ""
	if frappe.db.exists("Workstation", s):
		return s
	norm = normalize_planning_unit_for_select(s)
	if norm and frappe.db.exists("Workstation", norm):
		return norm
	su = s.upper().replace(" ", "")
	for ws_name in frappe.get_all("Workstation", pluck="name", limit_page_length=0) or []:
		ws = str(ws_name or "").strip()
		if not ws:
			continue
		wu = ws.upper().replace(" ", "")
		if ws == s or wu == su:
			return ws
	if norm:
		ensure_planning_workstation_record(norm)
		if frappe.db.exists("Workstation", norm):
			return norm
	return norm or s


def maintenance_units_equal(a, b):
	"""True when two unit strings refer to the same planning workstation."""
	return normalize_planning_unit_for_select(a) == normalize_planning_unit_for_select(b)


def maintenance_unit_match_values(raw_unit):
	"""All ``Planning Table.unit`` / ``Equipment Maintenance.unit`` values equivalent to *raw_unit*."""
	import frappe

	s = str(raw_unit or "").strip()
	if not s:
		return []
	out = set()
	out.add(s)
	canon = normalize_planning_unit_for_select(s)
	if canon:
		out.add(canon)
	resolved = resolve_planning_workstation_name(s)
	if resolved:
		out.add(resolved)
	canon_resolved = normalize_planning_unit_for_select(resolved or s)
	if canon_resolved:
		out.add(canon_resolved)
	su = s.upper().replace(" ", "")
	for ws in frappe.get_all("Workstation", pluck="name", limit_page_length=0) or []:
		w = str(ws or "").strip()
		if not w:
			continue
		wu = w.upper().replace(" ", "")
		if wu == su or normalize_planning_unit_for_select(w) == canon_resolved:
			out.add(w)
	return sorted(out)


def _workstation_type_for_new_record(name):
	"""Pick an existing Workstation Type only (never invent types like 'Bag Making')."""
	import frappe

	name = str(name or "").strip()
	candidates = []
	if name in ("Unit 1", "Unit 2", "Unit 3", "Unit 4", "UNASSIGNED"):
		candidates.extend(("Fabric", "Production", "Manufacturing"))
	else:
		candidates.extend(("Bag Making", "Bag", "Production", "Manufacturing"))
	candidates.append(None)
	for wt in candidates:
		if wt and frappe.db.exists("Workstation Type", wt):
			return wt
	existing = frappe.db.get_value("Workstation Type", {}, "name", order_by="modified desc")
	return existing or None


def ensure_planning_workstation_record(name):
	"""Create a Workstation row when missing; skips if no Workstation Type exists on site."""
	import frappe

	name = str(name or "").strip()
	if not name or frappe.db.exists("Workstation", name):
		return name
	payload = {"doctype": "Workstation", "workstation_name": name}
	ws_type = _workstation_type_for_new_record(name)
	if ws_type:
		payload["workstation_type"] = ws_type
	try:
		doc = frappe.get_doc(payload)
		doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"ensure_planning_workstation_record:{name}")
	return name


def ensure_planning_unit_field_links_workstation():
	"""Force planning ``unit`` child fields to Link → Workstation (fixes 'Could not find Unit')."""
	import frappe

	targets = (
		("Planning Table", "unit"),
		(PLANNING_SHEET_ITEM, "unit"),
	)
	for dt, fieldname in targets:
		try:
			frappe.db.sql(
				"""
				UPDATE `tabDocField`
				SET `fieldtype`='Link', `options`='Workstation'
				WHERE `parent`=%s AND `fieldname`=%s
				""",
				(dt, fieldname),
			)
			frappe.db.sql(
				"""
				UPDATE `tabCustom Field`
				SET `fieldtype`='Link', `options`='Workstation'
				WHERE `dt`=%s AND `fieldname`=%s
				""",
				(dt, fieldname),
			)
			for ps in frappe.get_all(
				"Property Setter",
				filters={
					"doc_type": dt,
					"field_name": fieldname,
					"property": ["in", ["fieldtype", "options"]],
				},
				pluck="name",
			) or []:
				try:
					frappe.delete_doc("Property Setter", ps, force=True, ignore_missing=True)
				except Exception:
					pass
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"ensure_planning_unit_link:{dt}")
	for ws_name in (
		BOX_BAG_UNIT_L1,
		BOX_BAG_UNIT_L2,
		BOX_BAG_UNIT_L4_SCREEN,
		BOX_BAG_UNASSIGNED_UNIT,
		"Unit 1",
		"Unit 2",
		"Unit 3",
		"Unit 4",
		"UNASSIGNED",
	):
		ensure_planning_workstation_record(ws_name)
	try:
		frappe.clear_cache(doctype="Planning Table")
		frappe.clear_cache(doctype=PLANNING_SHEET_ITEM)
	except Exception:
		pass


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
            SLITTING_UNIT_VTP,
            SLITTING_UNASSIGNED_UNIT,
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
            BOX_BAG_UNIT_L1,
            BOX_BAG_UNIT_L2,
            BOX_BAG_UNASSIGNED_UNIT,
            W_CUT_D_CUT_UNIT_JVE_L1,
            W_CUT_D_CUT_UNIT_JVE_L2,
            W_CUT_D_CUT_UNIT_JVE_L3,
            W_CUT_D_CUT_UNIT_L1,
            W_CUT_D_CUT_UNIT_L2,
            W_CUT_D_CUT_UNIT_L3,
            W_CUT_UNASSIGNED_UNIT,
            D_CUT_UNASSIGNED_UNIT,
            # Legacy labels still seen on older sites / custom Select fields.
            "JVE - PRINTING MACHINE 2 COLOUR",
            "JVE - PRINTING MACHINE 4 COLOUR",
            "TT - PRINTING MACHINE COLOUR 1200MM",
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
	Legacy Select sync for all known planning/manufacturing unit fields.
	No-op for Link fields.

	Older sites synced ``tabDocField.options`` here; Links use ``options``='Workstation' from DocType JSON.
	"""
	import frappe

	target_fields = (
		("Planning Table", "unit"),
		(PLANNING_SHEET_ITEM, "unit"),
		("Shaft Production Run", "custom_unit"),
		("Production Plan", "custom_unit"),
		("Work Order", "custom_unit"),
		("Stock Entry", "custom_unit"),
	)
	for dt, fieldname in target_fields:
		try:
			fieldtype = frappe.db.get_value(
				"DocField",
				{"parent": dt, "fieldname": fieldname},
				"fieldtype",
			)
		except Exception:
			continue
		if (fieldtype or "") != "Select":
			continue
		opts = frappe.db.get_value(
			"DocField",
			{"parent": dt, "fieldname": fieldname, "fieldtype": "Select"},
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
				(CANONICAL_PLANNING_LINE_UNIT_OPTIONS, dt, fieldname),
			)
			for ps in frappe.get_all(
				"Property Setter",
				filters={"doc_type": dt, "field_name": fieldname, "property": "options"},
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
		for dt in ("Shaft Production Run", "Production Plan", "Work Order", "Stock Entry"):
			frappe.clear_cache(doctype=dt)
	except Exception:
		pass


# Old names from earlier app JSON / deploys (for migration helpers only).
LEGACY_PLANNING_SHEET = "Planning Sheet"
LEGACY_PLANNING_SHEET_ITEM = "Planning Sheet Item"

# Fabric mix roll — max total shaft width (inches) per Color Chart unit.
MIX_ROLL_UNIT_MAX_SHAFT_INCHES = {
	"Unit 1": 63,
	"Unit 2": 126,
	"Unit 3": 126,
	"Unit 4": 90,
}

# Mix roll Material Receipt: company + finished-goods warehouse per fabric unit.
MIX_ROLL_COMPANY_FG_BY_UNIT = {
	"Unit 1": ("Jayashree Spun Bond - 1ZT", "Finished Goods - JSB-1ZT"),
	"Unit 2": ("Jayashree Spun Bond - 1ZT", "Finished Goods - JSB-1ZT"),
	"Unit 3": ("Jayashree Spun Bond - 1ZT", "Finished Goods - JSB-1ZT"),
	"Unit 4": (
		"Thusma SMS Nonwovens Private Limited - 1Z0",
		"Finished Goods Warehouse  - TSNPL",
	),
}

MIX_ROLL_FG_WAREHOUSE_FALLBACKS = (
	"Finished Goods - JSB-1ZT",
	"Finished Goods Warehouse  - TSNPL",
	"Finished Goods - IZT",
)


def parse_mix_shaft_total_inches(shaft) -> float:
	"""Sum inch widths from a shaft string like '32+30' or '40 + 40'."""
	import re

	from frappe.utils import flt

	widths = re.findall(r"\d+(?:\.\d+)?", str(shaft or ""))
	if not widths:
		return 0.0
	return sum(flt(w) for w in widths)


def get_mix_roll_unit_max_shaft_inches(unit) -> float:
	"""Return max allowed total shaft inches for a fabric unit (0 if unknown)."""
	u = normalize_planning_unit_for_select(unit)
	return float(MIX_ROLL_UNIT_MAX_SHAFT_INCHES.get(u, 0) or 0)


def validate_mix_shaft_width(unit, shaft):
	"""Raise if shaft combination total exceeds the unit's inch capacity."""
	import frappe
	from frappe import _

	max_in = get_mix_roll_unit_max_shaft_inches(unit)
	if max_in <= 0:
		return
	total = parse_mix_shaft_total_inches(shaft)
	if total <= 0:
		return
	if total > max_in + 1e-6:
		u = normalize_planning_unit_for_select(unit) or str(unit or "").strip() or "Unit"
		frappe.throw(
			_(
				"{0} maximum shaft width is {1}\". Combination {2} = {3}\" is not allowed. "
				"Enter a combination within {1}\"."
			).format(u, int(max_in) if max_in == int(max_in) else max_in, shaft, total)
		)


def resolve_mix_roll_company_and_fg_warehouse(unit):
	"""Return (company, fg_warehouse) for mix roll stock posting."""
	import frappe

	u = normalize_planning_unit_for_select(unit)
	company, fg_wh = MIX_ROLL_COMPANY_FG_BY_UNIT.get(u, MIX_ROLL_COMPANY_FG_BY_UNIT.get("Unit 1", ("", "")))
	company = str(company or "").strip()
	fg_wh = str(fg_wh or "").strip()
	if fg_wh and not frappe.db.exists("Warehouse", fg_wh):
		for alt in MIX_ROLL_FG_WAREHOUSE_FALLBACKS:
			if frappe.db.exists("Warehouse", alt):
				fg_wh = alt
				break
	if company and not frappe.db.exists("Company", company):
		company = (
			frappe.defaults.get_user_default("Company")
			or frappe.db.get_single_value("Global Defaults", "default_company")
			or ""
		)
	if fg_wh and company:
		wh_co = frappe.db.get_value("Warehouse", fg_wh, "company")
		if wh_co and wh_co != company:
			alt = frappe.db.get_value(
				"Warehouse",
				{"company": company, "is_group": 0, "name": ["like", "%Finished%"]},
				"name",
				order_by="modified desc",
			)
			if alt:
				fg_wh = alt
	if not fg_wh:
		fg_wh = frappe.db.get_value("Stock Settings", None, "default_fg_warehouse") or "Finished Goods - P"
	return company, fg_wh
