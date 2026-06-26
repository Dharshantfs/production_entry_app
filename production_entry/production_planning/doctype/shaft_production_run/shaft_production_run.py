import json
import math
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowtime, today

from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
	extract_quality_and_color,
)
from production_entry.production_planning.scheduler_api import (
	_bom_rm_stock_qty_map_for_fg,
)
from production_entry.production_planning.planning_doctypes import (
	BOX_BAG_UNIT_L1,
	BOX_BAG_UNIT_L2,
	BOX_BAG_UNIT_L4_SCREEN,
	BOX_BAG_UNASSIGNED_UNIT,
	LAMINATION_UNIT,
	PRINTED_BOPP_FILM_UNIT,
	PRINTING_UNASSIGNED_UNIT,
	PRINTING_UNIT_2_COLOUR,
	PRINTING_UNIT_4_COLOUR,
	PRINTING_UNIT_TT,
	REWINDING_UNASSIGNED_UNIT,
	REWINDING_UNIT_L3,
	REWINDING_UNIT_L4,
	REWINDING_UNIT_L5,
	SHEET_CUTTING_UNIT,
	SLITTING_UNIT,
	SLITTING_UNIT_VTP,
	SLITTING_UNASSIGNED_UNIT,
	W_CUT_D_CUT_UNIT_JVE_L1,
	W_CUT_D_CUT_UNIT_JVE_L2,
	W_CUT_D_CUT_UNIT_JVE_L3,
	W_CUT_D_CUT_UNIT_L1,
	W_CUT_D_CUT_UNIT_L2,
	W_CUT_D_CUT_UNIT_L3,
	W_CUT_D_CUT_ALL_UNITS,
	normalize_planning_unit_for_select,
	get_mix_roll_unit_max_shaft_inches,
	validate_mix_shaft_width,
	resolve_mix_roll_company_and_fg_warehouse,
)

# Unique (company_id, 2-digit unit_no) per workstation — never reuse across units.
SPR_BATCH_UNIT_MAP = {
	"Unit 1": ("JS", "01"),
	"Unit 2": ("JS", "02"),
	"Unit 3": ("JS", "03"),
	"Unit 4": ("TS", "04"),
	LAMINATION_UNIT: ("TS", "05"),
	SLITTING_UNIT: ("JV", "06"),
	SLITTING_UNIT_VTP: ("VTP", "23"),
	REWINDING_UNIT_L3: ("TS", "07"),
	REWINDING_UNIT_L4: ("JS", "08"),
	REWINDING_UNIT_L5: ("JS", "09"),
	SHEET_CUTTING_UNIT: ("JV", "10"),
	PRINTING_UNIT_2_COLOUR: ("JV", "11"),
	PRINTING_UNIT_TT: ("TT", "12"),
	PRINTING_UNIT_4_COLOUR: ("JV", "13"),
	PRINTED_BOPP_FILM_UNIT: ("VR", "14"),
	BOX_BAG_UNIT_L2: ("VTP", "15"),
	BOX_BAG_UNIT_L1: ("VTP", "16"),
	BOX_BAG_UNIT_L4_SCREEN: ("VTP", "24"),
	W_CUT_D_CUT_UNIT_JVE_L1: ("JVE", "17"),
	W_CUT_D_CUT_UNIT_JVE_L2: ("JVE", "18"),
	W_CUT_D_CUT_UNIT_JVE_L3: ("JVE", "19"),
	W_CUT_D_CUT_UNIT_L1: ("TTT", "20"),
	W_CUT_D_CUT_UNIT_L2: ("TTT", "21"),
	W_CUT_D_CUT_UNIT_L3: ("TTT", "22"),
}


def spr_batch_prefix_for_unit(unit_value: str):
	"""Resolve batch company + unit digits for a workstation name. Returns None if not configured."""
	u = normalize_planning_unit_for_select(_cstr(unit_value))
	if not u or u == "UNASSIGNED":
		return None
	if u in SPR_BATCH_UNIT_MAP:
		return SPR_BATCH_UNIT_MAP[u]
	m = re.search(r"(?i)\bunit\s*(\d+)\b", _cstr(unit_value))
	if m:
		num = int(m.group(1))
		if num == 4:
			return ("TS", "04")
		if 1 <= num <= 3:
			return ("JS", f"{num:02d}")
	return None


# FG Work Order processes that require manual batch-tracked RM lines in SPR batch picker.
SPR_FG_FABRIC_PICK_PROCESSES = ("102", "103", "104", "105", "106", "107", "108", "109", "251", "252", "253", "254", "255")


def spr_fg_item_process_code(item_code: str) -> str:
	"""3-digit process code from FG item_code.

	- Design-first printing / sheet: ``002-105…``, ``DES-252…`` (process after first hyphen).
	- Legacy width suffix: ``102…-1600`` (short numeric tail → process from head digit stream).
	"""
	raw = (item_code or "").strip().upper()
	if not raw:
		return ""
	if " - " in raw:
		raw = raw.split(" - ")[-1].strip()
	if "-" in raw:
		parts = raw.split("-", 1)
		head = parts[0].strip()
		tail = parts[1].strip() if len(parts) > 1 else ""
		if raw.count("-") == 1 and tail.isdigit() and len(tail) <= 4:
			head_digits = "".join([ch for ch in head if ch.isdigit()])
			if len(head_digits) >= 3:
				return head_digits[:3]
		tail_digits = "".join([ch for ch in tail if ch.isdigit()])
		if len(tail_digits) >= 3:
			return tail_digits[:3]
	digits = "".join([ch for ch in raw if ch.isdigit()])
	return digits[:3] if len(digits) >= 3 else ""


def spr_fg_parent_needs_fabric_batch_pick(production_item: str) -> bool:
	"""True when WO FG needs manual batch-tracked RM allocation for this SPR (102–109 incl. 108, 251–255 incl. 254, design-first)."""
	proc = spr_fg_item_process_code(production_item)
	return bool(proc) and proc in SPR_FG_FABRIC_PICK_PROCESSES


# FG process → (immediate BOM child process, fabric process) for desk batch-pick dialog.
_SPR_BOM_STACK_BY_FG_PROCESS = {
	"102": (None, "100"),
	"103": (None, "100"),
	"104": (None, "100"),
	"105": (None, "100"),
	"106": (None, "100"),
	"107": (None, "100"),
	"108": (None, "100"),
	"109": (None, "100"),
	"110": (None, "100"),
	"251": (None, "100"),
	"252": ("105", "100"),
	"253": ("104", "100"),
	"254": ("106", "100"),
	"255": (None, "100"),
	"200": (None, "100"),
	"201": ("105", "100"),
	"202": ("104", "100"),
	"211": (None, "100"),
	"212": ("105", "100"),
	"213": ("104", "100"),
	"216": ("107", "100"),
	"217": ("107", "100"),
	"225": ("106", "104"),
	"226": ("106", "104"),
	"221": ("103", "100"),
	"222": ("107", "100"),
	"223": ("107", "100"),
	"224": ("104", "103"),
	"231": ("107", "104"),
	"232": ("231", "107"),
	"233": ("107", "104"),
	"241": ("106", "104"),
	"242": ("106", "104"),
}

# Box bag + W-CUT + D-CUT finished-goods process codes (221/224, 211–217, 200–203, BOPP bag, etc.).
ALL_BAG_FG_PROCESS_CODES = frozenset({
	"200", "201", "202", "203",
	"211", "212", "213", "214", "216", "217",
	"221", "222", "223", "224", "231", "232", "233", "241", "242", "225", "226",
})


def _spr_resolve_bag_fg_process_code(item_code: str) -> str:
	"""Resolve FG process for bag items (design-first 6000-511-221…, W/D-CUT, BOPP bag)."""
	ic = _cstr(item_code).strip()
	if not ic:
		return ""
	try:
		from production_entry.production_planning.scheduler_api import (
			W_CUT_D_CUT_FG_PROCESS_CODES,
			_item_process_prefix,
		)

		try:
			from production_entry.production_planning.box_bag_api import (
				_parse_box_bag_item_code,
				_parse_dcut_bag_item_code,
			)

			p_dc = _parse_dcut_bag_item_code(ic) or {}
			proc_dc = _cstr(p_dc.get("process") or "").strip()
			if proc_dc in W_CUT_D_CUT_FG_PROCESS_CODES:
				return proc_dc
			p_bb = _parse_box_bag_item_code(ic) or {}
			proc_bb = _cstr(p_bb.get("process") or "").strip()
			if proc_bb in ALL_BAG_FG_PROCESS_CODES:
				return proc_bb
		except Exception:
			pass
		try:
			from production_entry.production_planning.bopp_bag_api import _parse_bopp_bag_item_code

			p_bopp = _parse_bopp_bag_item_code(ic) or {}
			proc_bopp = _cstr(p_bopp.get("process") or "").strip()
			if proc_bopp in ALL_BAG_FG_PROCESS_CODES:
				return proc_bopp
		except Exception:
			pass
		proc = _cstr(_item_process_prefix(ic)).strip()
		if proc in ALL_BAG_FG_PROCESS_CODES:
			return proc
	except Exception:
		pass
	proc = spr_fg_item_process_code(ic)
	return proc if proc in ALL_BAG_FG_PROCESS_CODES else ""


def spr_bag_fg_needs_rm_batch_pick(production_item: str) -> bool:
	"""Bag FG SPR (box bag, W-CUT, D-CUT, BOPP bag) needs Select RM batches dialog."""
	return bool(_spr_resolve_bag_fg_process_code(production_item))


def spr_fg_needs_rm_batch_pick(production_item: str, is_bag_spr: bool = False) -> bool:
	if is_bag_spr:
		return spr_bag_fg_needs_rm_batch_pick(production_item)
	return spr_fg_parent_needs_fabric_batch_pick(production_item)


def _spr_item_has_batch_no(item_code: str) -> bool:
	try:
		return bool(cint(frappe.db.get_value("Item", item_code, "has_batch_no") or 0))
	except Exception:
		return False


def _spr_rm_needs_manual_batch_pick(item_code: str) -> bool:
	"""True for any batch-tracked BOM RM on eligible FG WO (105 on 252 WO, not only 100*)."""
	ic = _cstr(item_code)
	if not ic:
		return False
	return _spr_item_has_batch_no(ic)


def _spr_bom_stack_for_fg_item(production_item: str) -> list[dict]:
	"""BOM chain rows for the fabric-batch dialog (FG → child → fabric)."""
	proc = _spr_resolve_bag_fg_process_code(production_item) or spr_fg_item_process_code(production_item)
	if not proc:
		return []
	child_proc, fabric_proc = _SPR_BOM_STACK_BY_FG_PROCESS.get(proc, (None, "100"))
	out = [{"process": proc, "label": _("FG ({0})").format(proc), "role": "fg", "item_code": _cstr(production_item)}]
	if child_proc:
		out.append(
			{
				"process": child_proc,
				"label": _("BOM child ({0})").format(child_proc),
				"role": "child",
				"item_code": "",
			}
		)
	if fabric_proc:
		out.append(
			{
				"process": fabric_proc,
				"label": _("Fabric ({0})").format(fabric_proc),
				"role": "fabric",
				"item_code": "",
			}
		)
	return out


def batch_shift_value(shift: str | None) -> str:
	if not shift:
		return ""
	s = shift.lower()
	if "night" in s:
		return "Night"
	if "day" in s:
		return "Day"
	return shift


def _cstr(v) -> str:
	return str(v).strip() if v is not None else ""


def _compact_unit_key(value) -> str:
	return re.sub(r"[^A-Z0-9]", "", _cstr(value).upper())


def _unit_value_for_doctype_field(unit_value, doctype: str, fieldname: str, meta=None) -> str:
	"""Return a unit value that validates against the current DocType field."""
	raw = _cstr(unit_value)
	if not raw:
		return ""
	normalized = normalize_planning_unit_for_select(raw)
	if not normalized or normalized == "UNASSIGNED":
		return ""

	try:
		field_meta = meta or frappe.get_meta(doctype)
		df = field_meta.get_field(fieldname)
	except Exception:
		df = None
	if not df or df.fieldtype != "Select":
		return normalized

	options = [_cstr(opt) for opt in _cstr(df.options).splitlines() if _cstr(opt)]
	if not options:
		return normalized

	alias_map = {
		"Unit 1": ["UNIT 1", "Unit 1"],
		"Unit 2": ["UNIT 2", "Unit 2"],
		"Unit 3": ["UNIT 3", "Unit 3"],
		"Unit 4": ["UNIT 4", "Unit 4"],
		LAMINATION_UNIT: ["Lamination Unit", LAMINATION_UNIT],
		SLITTING_UNIT: ["Slitting Unit", SLITTING_UNIT],
		REWINDING_UNASSIGNED_UNIT: ["Unassigned rewinding machine", REWINDING_UNASSIGNED_UNIT],
		PRINTING_UNASSIGNED_UNIT: ["Unassigned printing machine", PRINTING_UNASSIGNED_UNIT],
		SHEET_CUTTING_UNIT: [SHEET_CUTTING_UNIT],
		REWINDING_UNIT_L3: [REWINDING_UNIT_L3],
		REWINDING_UNIT_L4: [REWINDING_UNIT_L4],
		REWINDING_UNIT_L5: [REWINDING_UNIT_L5],
		PRINTED_BOPP_FILM_UNIT: [PRINTED_BOPP_FILM_UNIT],
		PRINTING_UNIT_2_COLOUR: [PRINTING_UNIT_2_COLOUR, "JVE - PRINTING MACHINE 2 COLOUR"],
		PRINTING_UNIT_4_COLOUR: [PRINTING_UNIT_4_COLOUR, "JVE - PRINTING MACHINE 4 COLOUR"],
		PRINTING_UNIT_TT: [PRINTING_UNIT_TT, "TT - PRINTING MACHINE COLOUR 1200MM"],
	}
	candidates = [raw, normalized] + alias_map.get(normalized, [])
	option_by_key = {_compact_unit_key(opt): opt for opt in options}
	for candidate in candidates:
		candidate_key = _compact_unit_key(candidate)
		if candidate_key in option_by_key:
			return option_by_key[candidate_key]

	# Older live sites can still have stale Select options. Widen the in-memory
	# meta so validation accepts the canonical Workstation name during migration.
	if normalized not in options:
		df.options = (_cstr(df.options) + "\n" + normalized).strip()
	return normalized


def _spr_unit_value_for_current_field(unit_value) -> str:
	"""Return a unit value that validates against the site's current SPR custom_unit field."""
	return _unit_value_for_doctype_field(unit_value, "Shaft Production Run", "custom_unit")


def _spr_bundle_source_batch_prefix(batch_no) -> str:
	raw = _cstr(batch_no)
	if not raw:
		return ""
	m = re.match(r"^(?P<prefix>.+)-B\d+(?:-\d+-\d+)?$", raw)
	return _cstr(m.group("prefix")) if m else raw


def _spr_next_bundle_batch_no(spr, source_prefix: str) -> str:
	source_prefix = _cstr(source_prefix)
	if not source_prefix:
		return ""
	max_no = 0
	for row in spr.bundle_stickers or []:
		bn = _cstr(getattr(row, "batch_no", ""))
		m = re.match(rf"^{re.escape(source_prefix)}-B(\d+)(?:-\d+-\d+)?$", bn)
		if m:
			max_no = max(max_no, cint(m.group(1)))
	return f"{source_prefix}-B{max_no + 1}"


def _spr_row_get(spr_row, key: str):
	if spr_row is None:
		return None
	if isinstance(spr_row, dict):
		return spr_row.get(key)
	return spr_row.get(key)


def _batch_field_net_weight_kgs(batch_meta) -> str | None:
	for df in batch_meta.fields:
		lab = (df.label or "").lower()
		if "net" in lab and "weight" in lab:
			return df.fieldname
	for fn in ("custom_net_weight_kgs", "custom_net_weight", "net_weight_kgs"):
		if batch_meta.has_field(fn):
			return fn
	return None


def _batch_field_gross_weight_kgs(batch_meta) -> str | None:
	for df in batch_meta.fields:
		lab = (df.label or "").lower()
		if "gross" in lab and "weight" in lab:
			return df.fieldname
	for fn in ("custom_gross_weight_kgs", "custom_gross_weight", "gross_weight_kgs"):
		if batch_meta.has_field(fn):
			return fn
	return None


def _batch_field_length_mtrs(batch_meta) -> str | None:
	for df in batch_meta.fields:
		lab = (df.label or "").lower()
		if "planned qty" in lab:
			continue
		if "length" in lab and ("mtr" in lab or "meter" in lab or "mtrs" in lab):
			return df.fieldname
		if "ordered" in lab and "length" in lab:
			return df.fieldname
	for fn in ("custom_length_mtrs", "length_mtrs", "custom_meter_roll", "meter_roll"):
		if batch_meta.has_field(fn):
			return fn
	return None


def _spr_length_meters(spr_row) -> float | None:
	"""Length in m for Batch + reporting: prefers Produced Length (Mtrs), then Meter/Roll."""
	if spr_row is None:
		return None
	for key in ("produced_length_mtrs", "custom_produced_length_mtrs"):
		v = _spr_row_get(spr_row, key)
		if v is not None and flt(v) > 0:
			return flt(v)
	try:
		spi_meta = frappe.get_meta("Shaft Production Run Item")
		for df in spi_meta.fields:
			if df.fieldtype not in ("Float", "Int", "Currency"):
				continue
			lab = (df.label or "").lower()
			if "produced" in lab and "length" in lab:
				v = _spr_row_get(spr_row, df.fieldname)
				if v is not None and flt(v) > 0:
					return flt(v)
	except Exception:
		pass
	for key in ("meter_roll", "ordered_length", "custom_ordered_length"):
		v = _spr_row_get(spr_row, key)
		if v is not None and flt(v) > 0:
			return flt(v)
	return None


def _spr_produced_length_meters(spr_row) -> float:
	"""Produced-only length in meters (no ordered/meter_roll fallback)."""
	if spr_row is None:
		return 0.0
	for key in (
		"produced_length_mtrs",
		"custom_produced_length_mtrs",
		"produced_length",
		"custom_produced_length",
	):
		v = _spr_row_get(spr_row, key)
		if v is not None and flt(v) > 0:
			return flt(v)
	return 0.0


def _spr_first_roll_item_code(doc) -> str:
	for it in doc.get("items") or []:
		ic = _cstr(getattr(it, "item_code", None) or "")
		if ic:
			return ic
	return ""


def _pp_has_lamination_work_order(pp_name: str) -> bool:
	"""True when the production plan has FG work orders for process 104 or 107 lamination."""
	if not pp_name or not frappe.db.exists("Production Plan", pp_name):
		return False
	try:
		for w in frappe.get_all(
			"Work Order",
			filters={"production_plan": pp_name, "docstatus": ["!=", 2]},
			fields=["production_item"],
			limit=50,
		):
			pi = _cstr((w or {}).get("production_item") or "")
			if spr_fg_item_process_code(pi) in ("104", "107"):
				return True
	except Exception:
		pass
	return False


def spr_doc_is_mix_roll(doc) -> bool:
	"""Mix roll SPR from Color Chart — no Production Plan / Work Order."""
	return bool(doc and cint(getattr(doc, "is_mix_roll", 0) or 0))


def spr_doc_is_lamination(doc) -> bool:
	"""Lamination SPR: Is Lamination ticked and plan / roll lines are process 104 or 107."""
	if not doc or not cint(getattr(doc, "custom_is_lamination", 0) or 0):
		return False
	ic = _spr_first_roll_item_code(doc)
	if ic and spr_fg_item_process_code(ic) in ("104", "107"):
		return True
	pp = _cstr(getattr(doc, "production_plan", None) or "")
	return _pp_has_lamination_work_order(pp)


def _fabric_gsm_from_item_name(item_name: str) -> int:
	"""Parse Fabric GSM from item name by finding the F-<number> pattern (e.g. 'F-60' or 'F - 60' ΓåÆ 60)."""
	if not item_name:
		return 0
	m = re.search(r'\bF\s*-\s*(\d+)\b', item_name, re.IGNORECASE)
	if m:
		try:
			return int(m.group(1))
		except Exception:
			pass
	return 0


# Lamination GSM suffix map (same as scheduler_api._LAM_GSM_SUFFIX_MAP): A=10 … F=13; B1 legacy 13.
_LAM_GSM_SUFFIX_MAP: dict[str, int] = {
	"A": 10,
	"B": 12,
	"B1": 13,
	"C": 15,
	"D": 20,
	"E": 30,
	"F": 13,
}


def _lam_gsm_from_item(item_name: str, item_code: str) -> int:
	"""Parse Lamination GSM from item name 'L-15 GSM' pattern, with -C suffix fallback.

	Item name pattern: 'L- 15 GSM' or 'L-15GSM'  ΓåÆ 15
	Item code suffix:  '1041030010750890-C' ΓåÆ suffix 'C' ΓåÆ 15 via _LAM_GSM_SUFFIX_MAP
	"""
	# Primary: parse 'L-<N> GSM' or 'L- <N> GSM' from item name
	if item_name:
		m = re.search(r'\bL-\s*(\d+)\s*GSM\b', item_name, re.IGNORECASE)
		if m:
			try:
				return int(m.group(1))
			except Exception:
				pass
	# Fallback: suffix after last '-' in item code (e.g. '-C' ΓåÆ 'C' ΓåÆ 15)
	if item_code:
		parts = str(item_code).strip().upper().split('-')
		if len(parts) >= 2:
			suffix = parts[-1].strip()
			if suffix in _LAM_GSM_SUFFIX_MAP:
				return _LAM_GSM_SUFFIX_MAP[suffix]
	return 0


def _bopp_gsm_from_item(item_code: str, item_name: str = "") -> int:
	"""Parse BOPP GSM from lamination / slitting item codes (107, 108, 109, encoded tails)."""
	ic = _cstr(item_code)
	if not ic:
		return 0
	try:
		from production_entry.production_planning.scheduler_api import (
			_item_process_prefix,
			_parse_107_item_code,
			_parse_108_item_code,
			_parse_110_item_code,
		)

		proc = _item_process_prefix(ic)
		if proc == "107":
			return cint((_parse_107_item_code(ic) or {}).get("bopp_gsm") or 0)
		if proc in ("108", "109"):
			return cint((_parse_108_item_code(ic) or {}).get("bopp_gsm") or 0)
		if proc == "110":
			return cint((_parse_110_item_code(ic) or {}).get("bopp_gsm") or 0)
		if proc in ("104", "107"):
			parsed = _parse_107_item_code(ic) or {}
			if cint(parsed.get("bopp_gsm") or 0) > 0:
				return cint(parsed.get("bopp_gsm") or 0)
	except Exception:
		pass
	try:
		from production_entry.production_planning.box_bag_api import _parse_dcut_bag_item_code

		parsed = _parse_dcut_bag_item_code(ic) or {}
		if cint(parsed.get("bopp_gsm") or 0) > 0:
			return cint(parsed.get("bopp_gsm") or 0)
	except Exception:
		pass
	return 0


def _fabric_gsm_from_planning_for_pp(pp_name: str) -> int:
	"""Fabric (100ΓÇª) GSM from Planning Table child row on same sheet as 104 lamination line."""
	if not pp_name or not frappe.db.exists("DocType", "Planning Table"):
		return 0
	pt_cols = set(frappe.db.get_table_columns("Planning Table") or [])
	if "custom_production_plan" not in pt_cols:
		return 0
	so_l = "sales_order_item" if "sales_order_item" in pt_cols else None
	so_cust = "custom_sales_order_item" if "custom_sales_order_item" in pt_cols else None
	fab_so = "so_item" if "so_item" in pt_cols else None
	if not fab_so:
		return 0
	params: list = [pp_name]
	if so_l and so_cust:
		join_sql = (
			f"(IFNULL(fab.{fab_so},'') = IFNULL(lam.{so_l},'') OR IFNULL(fab.{fab_so},'') = IFNULL(lam.{so_cust},''))"
		)
	elif so_l:
		join_sql = f"IFNULL(fab.{fab_so},'') = IFNULL(lam.{so_l},'')"
	elif so_cust:
		join_sql = f"IFNULL(fab.{fab_so},'') = IFNULL(lam.{so_cust},'')"
	else:
		return 0
	gcol = "gsm" if "gsm" in pt_cols else None
	if not gcol:
		return 0
	row = frappe.db.sql(
		f"""
		SELECT IFNULL(fab.{gcol}, 0) AS g
		FROM `tabPlanning Table` lam
		INNER JOIN `tabPlanning sheet` ps ON ps.name = lam.parent
		LEFT JOIN `tabPlanning Table` fab ON fab.parent = lam.parent
			AND fab.item_code LIKE '100%%'
			AND ({join_sql})
		WHERE IFNULL(lam.custom_production_plan, '') = %s
		  AND lam.item_code LIKE '104%%'
		ORDER BY lam.idx ASC, fab.idx ASC
		LIMIT 1
		""",
		tuple(params),
		as_dict=True,
	)
	if row and row[0].get("g") is not None:
		return int(flt(row[0].get("g")))
	return 0


def _spr_company_rm_warehouse(company: str, wip_wh: str = "") -> str:
	"""Best-effort raw-material warehouse for a company (lamination PP/LD, etc.)."""
	company = _cstr(company).strip()
	wip_wh = _cstr(wip_wh).strip()
	if not company:
		return ""
	patterns = (
		"%Raw Material%",
		"%Raw Materials%",
		"%RM Warehouse%",
		"%Stores%",
		"%Store%",
		"%Material%",
	)
	for pattern in patterns:
		for is_group in (0, 1):
			wh = frappe.db.get_value(
				"Warehouse",
				{"company": company, "name": ["like", pattern], "is_group": is_group},
				"name",
				order_by="modified desc",
			)
			wh = _cstr(wh).strip()
			if wh and wh != wip_wh and "work in progress" not in wh.lower():
				if is_group:
					leaf = frappe.db.get_value(
						"Warehouse",
						{"company": company, "parent_warehouse": wh, "is_group": 0},
						"name",
						order_by="modified desc",
					)
					leaf = _cstr(leaf).strip()
					if leaf and leaf != wip_wh:
						return leaf
				else:
					return wh
	rows = frappe.db.sql(
		"""
		SELECT name
		FROM `tabWarehouse`
		WHERE company = %s
		  AND IFNULL(is_group, 0) = 0
		  AND IFNULL(name, '') != ''
		  AND IFNULL(name, '') != %s
		  AND LOWER(IFNULL(name, '')) NOT LIKE %s
		ORDER BY modified DESC
		LIMIT 20
		""",
		(company, wip_wh, "%work in progress%"),
		as_dict=True,
	)
	for row in rows or []:
		wh = _cstr(row.get("name")).strip()
		if wh and wh != wip_wh:
			return wh
	return ""


def _spr_wo_rm_source_warehouse(wo_doc, item_code: str, wip_wh: str = "") -> str:
	"""Per-item RM source warehouse from WO required_items, BOM, prior MTFM, or company RM store."""
	item_code = _cstr(item_code).strip()
	wip_wh = _cstr(wip_wh).strip()
	wo_name = _cstr(getattr(wo_doc, "name", None)).strip()
	company = _cstr(getattr(wo_doc, "company", None)).strip()

	for req in getattr(wo_doc, "required_items", None) or []:
		if _cstr(getattr(req, "item_code", None)).strip() == item_code:
			src = _cstr(getattr(req, "source_warehouse", None)).strip()
			if src and src != wip_wh:
				return src
	header_src = _cstr(getattr(wo_doc, "source_warehouse", None)).strip()
	if header_src and header_src != wip_wh:
		return header_src

	if wo_name and item_code:
		prev = frappe.db.sql(
			"""
			SELECT sed.s_warehouse
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE IFNULL(se.docstatus, 0) < 2
			  AND IFNULL(se.work_order, '') = %s
			  AND IFNULL(se.purpose, '') = 'Material Transfer for Manufacture'
			  AND IFNULL(sed.item_code, '') = %s
			  AND IFNULL(sed.s_warehouse, '') != ''
			ORDER BY se.modified DESC
			LIMIT 1
			""",
			(wo_name, item_code),
			as_dict=True,
		)
		if prev:
			src = _cstr(prev[0].get("s_warehouse")).strip()
			if src and src != wip_wh:
				return src

	bom_no = _cstr(getattr(wo_doc, "bom_no", None)).strip()
	if bom_no and item_code:
		bom_wh = frappe.db.get_value(
			"BOM Item",
			{"parent": bom_no, "item_code": item_code},
			"source_warehouse",
		)
		bom_wh = _cstr(bom_wh).strip()
		if bom_wh and bom_wh != wip_wh:
			return bom_wh

	if company and item_code:
		item_wh = frappe.db.get_value(
			"Item Default",
			{"parent": item_code, "company": company},
			"default_warehouse",
		)
		item_wh = _cstr(item_wh).strip()
		if item_wh and item_wh != wip_wh:
			return item_wh

	co_rm = _spr_company_rm_warehouse(company, wip_wh)
	if co_rm:
		return co_rm

	try:
		default_wh = _cstr(frappe.db.get_single_value("Stock Settings", "default_warehouse")).strip()
		if default_wh and default_wh != wip_wh:
			return default_wh
	except Exception:
		pass
	return header_src or ""


def _spr_wo_rm_still_needed_map(wo_doc) -> dict[str, float]:
	"""RM qty still to transfer to WIP from WO required_items (stock UOM, typically Kg)."""
	out = defaultdict(float)
	for req in getattr(wo_doc, "required_items", None) or []:
		ic = _cstr(getattr(req, "item_code", None)).strip()
		if not ic:
			continue
		need = flt(getattr(req, "required_qty", 0)) - flt(getattr(req, "transferred_qty", 0))
		if need > 1e-9:
			out[ic] += need
	return dict(out)


def _spr_rm_stock_qty_precision() -> int:
	"""Decimal places for BOM RM Kg on Stock Entry lines (matches MTFM / site ledger)."""
	try:
		p = int(frappe.conf.get("spr_rm_stock_qty_precision") or 3)
	except (TypeError, ValueError):
		p = 3
	return max(0, min(p, 6))


def _spr_rm_wip_shortage_tolerance(required_qty: float) -> float:
	"""Ignore float/rounding gaps when comparing WIP Bin vs BOM RM need (Kg)."""
	try:
		base = flt(frappe.conf.get("spr_rm_wip_shortage_tolerance_kg") or 0.05)
	except (TypeError, ValueError):
		base = 0.05
	req = flt(required_qty)
	if req <= 0:
		return base
	return max(base, req * 0.002)


def _spr_wip_topup_bump_qty(shortage_qty: float) -> float:
	"""Round micro WIP gaps up so auto RM->WIP transfer still posts (e.g. 0.009 -> 0.01 Kg)."""
	qty = flt(shortage_qty)
	if qty <= 0:
		return 0.0
	tol = _spr_rm_wip_shortage_tolerance(qty)
	if qty <= tol:
		qty = tol
	return _spr_round_rm_stock_qty(qty)


def _spr_wo_rm_transfer_remaining(wo_doc, item_code: str) -> float:
	"""Qty still to transfer to WIP for one RM item on the WO."""
	item_code = _cstr(item_code).strip()
	if not wo_doc or not item_code:
		return 0.0
	for req in getattr(wo_doc, "required_items", None) or []:
		if _cstr(getattr(req, "item_code", None)).strip() != item_code:
			continue
		return flt(getattr(req, "required_qty", 0)) - flt(getattr(req, "transferred_qty", 0))
	return 0.0


def _spr_round_rm_stock_qty(qty: float) -> float:
	return flt(qty, _spr_rm_stock_qty_precision())


def _spr_floor_rm_stock_qty(qty: float) -> float:
	"""Floor to site RM precision so transfer qty never exceeds bin actual."""
	prec = _spr_rm_stock_qty_precision()
	factor = 10**prec
	return math.floor(flt(qty) * factor + 1e-12) / factor


def _spr_rm_available_qty(item_code: str, warehouse: str) -> float:
	"""Actual qty in warehouse Bin for MTFM transfers.

	Use actual_qty (not actual - reserved) because reserved_qty includes the
	same Work Order we are transferring for.  ERPNext validates the real SLE
	balance on submit, so capping to actual_qty is safe and prevents the
	'Maximum transferable quantity is 0.0 Kg' false-block.
	"""
	item_code = _cstr(item_code).strip()
	warehouse = _cstr(warehouse).strip()
	if not item_code or not warehouse:
		return 0.0
	actual = flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
	)
	if actual > 0:
		return actual
	try:
		from erpnext.stock.utils import get_stock_balance

		bal = flt(get_stock_balance(item_code, warehouse))
		if bal > 0:
			return bal
	except Exception:
		pass
	return max(actual, 0.0)


def _spr_batches_in_warehouse(item_code: str, warehouse: str) -> list[dict]:
	"""Batches with positive qty in one warehouse (classic SLE.batch_no + v15 bundles)."""
	item_code = _cstr(item_code).strip()
	warehouse = _cstr(warehouse).strip()
	if not item_code or not warehouse:
		return []
	acc: dict[str, float] = {}
	for r in frappe.db.sql(
		"""
		SELECT batch_no, SUM(actual_qty) AS qty
		FROM `tabStock Ledger Entry`
		WHERE IFNULL(is_cancelled, 0) = 0
		  AND IFNULL(item_code, '') = %s
		  AND IFNULL(warehouse, '') = %s
		  AND IFNULL(batch_no, '') != ''
		GROUP BY batch_no
		HAVING SUM(actual_qty) > 0
		""",
		(item_code, warehouse),
		as_dict=True,
	):
		bn = _cstr(r.get("batch_no"))
		q = flt(r.get("qty") or 0)
		if bn and q > 0:
			acc[bn] = acc.get(bn, 0.0) + q
	if frappe.db.has_column("Stock Ledger Entry", "serial_and_batch_bundle"):
		try:
			sb_entry_dt = "Serial and Batch Entry"
			if frappe.db.exists("DocType", sb_entry_dt):
				sb_meta = frappe.get_meta(sb_entry_dt)
				batch_field = next(
					(fn for fn in ("batch_no", "batch", "batch_id") if sb_meta.has_field(fn)), ""
				)
				qty_field = next((fn for fn in ("qty", "quantity") if sb_meta.has_field(fn)), "")
				if batch_field and qty_field:
					for r in frappe.db.sql(
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
					) or []:
						bn = _cstr(r.get("batch_no"))
						q = flt(r.get("qty") or 0)
						if bn and q > 0:
							acc[bn] = max(acc.get(bn, 0.0), q)
		except Exception:
			pass
	out = [{"batch_no": bn, "qty": flt(q)} for bn, q in acc.items() if bn and flt(q) > 0]
	out.sort(key=lambda x: flt(x.get("qty") or 0), reverse=True)
	return out


def _spr_enable_serial_batch_fields_on_se(se) -> None:
	"""ERPNext v15: batched items need use_serial_batch_fields on Stock Entry lines."""
	if not se:
		return
	se_meta = frappe.get_meta("Stock Entry")
	if se_meta.has_field("use_serial_batch_fields"):
		se.use_serial_batch_fields = 1
	line_meta = frappe.get_meta("Stock Entry Detail")
	if not line_meta.has_field("use_serial_batch_fields"):
		return
	for d in se.items or []:
		if d.item_code:
			d.use_serial_batch_fields = 1


def _spr_expand_outbound_lines_by_batch(se) -> None:
	"""Split outbound STE lines across batches when one batch cannot cover the full qty."""
	if not se or not se.items:
		return
	new_lines: list = []
	for d in list(se.items or []):
		if not d.item_code or not d.get("s_warehouse"):
			new_lines.append(d)
			continue
		has_batch = cint(frappe.db.get_value("Item", d.item_code, "has_batch_no") or 0)
		need = flt(d.get("transfer_qty") or d.get("qty"))
		if not has_batch or need <= 0:
			new_lines.append(d)
			continue
		batches = _spr_batches_in_warehouse(d.item_code, d.s_warehouse)
		if not batches:
			d.batch_no = ""
			new_lines.append(d)
			continue
		remaining = need
		first = True
		for br in batches:
			if remaining <= 0:
				break
			bn = _cstr(br.get("batch_no"))
			bq = flt(br.get("qty") or 0)
			if not bn or bq <= 0:
				continue
			take = min(remaining, bq)
			take = _spr_floor_rm_stock_qty(take)
			if take <= 0:
				continue
			if first:
				d.batch_no = bn
				d.qty = take
				d.transfer_qty = take
				new_lines.append(d)
				first = False
			else:
				new_lines.append(
					{
						"item_code": d.item_code,
						"s_warehouse": d.s_warehouse,
						"t_warehouse": d.t_warehouse,
						"uom": d.uom,
						"stock_uom": d.stock_uom,
						"conversion_factor": flt(d.conversion_factor) or 1.0,
						"batch_no": bn,
						"qty": take,
						"transfer_qty": take,
						"work_order": d.get("work_order"),
						"expense_account": d.get("expense_account"),
						"cost_center": d.get("cost_center"),
					}
				)
			remaining -= take
		if first:
			d.batch_no = ""
			new_lines.append(d)
	se.items = []
	for row in new_lines:
		if isinstance(row, dict):
			se.append("items", row)
		else:
			se.items.append(row)


def _spr_batch_available_qty(item_code: str, warehouse: str, batch_no: str) -> float:
	"""Batch qty in warehouse (SLE sum / ERPNext helper)."""
	item_code = _cstr(item_code).strip()
	warehouse = _cstr(warehouse).strip()
	batch_no = _cstr(batch_no).strip()
	if not item_code or not warehouse or not batch_no:
		return 0.0
	try:
		from erpnext.stock.utils import get_batch_qty

		return flt(get_batch_qty(batch_no, warehouse, item_code))
	except Exception:
		pass
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(actual_qty), 0)
		FROM `tabStock Ledger Entry`
		WHERE item_code = %s AND warehouse = %s AND batch_no = %s AND is_cancelled = 0
		""",
		(item_code, warehouse, batch_no),
	)
	return flt(row[0][0] if row else 0)


def _spr_parse_max_transferable_kg(exc_msg: str) -> float:
	"""Parse ERPNext 'Maximum transferable quantity is X Kg' from submit validation."""
	msg = _cstr(exc_msg)
	m = re.search(
		r"Maximum transferable quantity is\s+([\d.]+)",
		msg,
		flags=re.IGNORECASE,
	)
	return flt(m.group(1)) if m else 0.0


def _spr_cap_qty_to_rm_available(
	qty: float, item_code: str, warehouse: str, batch_no: str | None = None
) -> float:
	"""Cap MTFM qty to RM/bin or batch stock — never round above available (7.554 vs 7.553997)."""
	qty = flt(qty)
	if qty <= 0:
		return 0.0
	batch_no = _cstr(batch_no).strip() if batch_no else ""
	if batch_no:
		avl = _spr_batch_available_qty(item_code, warehouse, batch_no)
	else:
		avl = _spr_rm_available_qty(item_code, warehouse)
	if avl <= 0:
		return 0.0
	capped = min(qty, avl)
	floored = _spr_floor_rm_stock_qty(capped)
	if floored > avl + 1e-9:
		floored = _spr_floor_rm_stock_qty(avl)
	if floored > avl + 1e-9:
		floored = avl
	return max(floored, 0.0)


def _spr_wo_rm_fully_transferred(wo_doc) -> bool:
	"""True when every WO required_item shows RM fully moved to WIP (within tolerance)."""
	if not wo_doc:
		return False
	for req in getattr(wo_doc, "required_items", None) or []:
		ic = _cstr(getattr(req, "item_code", None)).strip()
		if not ic:
			continue
		req_qty = flt(getattr(req, "required_qty", 0))
		still = _spr_wo_rm_transfer_remaining(wo_doc, ic)
		if still > _spr_rm_wip_shortage_tolerance(req_qty):
			return False
	return True


def _spr_find_rm_warehouse_with_stock(
	company: str,
	item_code: str,
	wip_wh: str,
	preferred_wh: str = "",
	need_qty: float = 0,
) -> tuple[str, float]:
	"""Pick a non-WIP warehouse with stock for item; prefer preferred_wh then company RM."""
	item_code = _cstr(item_code).strip()
	wip_wh = _cstr(wip_wh).strip()
	company = _cstr(company).strip()
	need_qty = flt(need_qty)
	if not item_code:
		return "", 0.0
	candidates: list[str] = []
	for wh in (_cstr(preferred_wh).strip(),):
		if wh and wh != wip_wh and wh not in candidates:
			candidates.append(wh)
	if company:
		co_rm = _spr_company_rm_warehouse(company, wip_wh)
		if co_rm and co_rm not in candidates:
			candidates.append(co_rm)
	if company:
		for row in frappe.db.sql(
			"""
			SELECT b.warehouse, b.actual_qty
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
			WHERE b.item_code = %s
			  AND w.company = %s
			  AND IFNULL(w.is_group, 0) = 0
			  AND IFNULL(b.actual_qty, 0) > 0.0001
			  AND b.warehouse != %s
			ORDER BY b.actual_qty DESC
			""",
			(item_code, company, wip_wh),
			as_dict=True,
		):
			wh = _cstr(row.get("warehouse")).strip()
			if wh and wh not in candidates:
				candidates.append(wh)
	best_wh, best_qty = "", 0.0
	for wh in candidates:
		avl = _spr_rm_available_qty(item_code, wh)
		if avl > best_qty:
			best_wh, best_qty = wh, avl
		if need_qty > 0 and avl + _spr_rm_wip_shortage_tolerance(need_qty) >= need_qty:
			return wh, avl
	return best_wh, best_qty


def _spr_finalize_mtfm_line_qty(sed, source_wh: str, requested_qty: float) -> float:
	"""Assign batch (if item is batched) then cap line qty to true transferable stock."""
	if not sed or not sed.item_code or not source_wh:
		return 0.0
	_spr_assign_batch_for_mtfm_line(sed, source_wh, flt(requested_qty))
	qty = _spr_cap_qty_to_rm_available(
		flt(requested_qty),
		sed.item_code,
		source_wh,
		sed.get("batch_no"),
	)
	if qty > 0:
		sed.qty = qty
		sed.transfer_qty = qty
	return qty


def _spr_prepare_mtfm_stock_entry_for_submit(se) -> None:
	"""Batch split + serial/batch fields + cap lines before MTFM insert/submit."""
	if not se:
		return
	_spr_enable_serial_batch_fields_on_se(se)
	_spr_expand_outbound_lines_by_batch(se)
	_spr_enable_serial_batch_fields_on_se(se)
	_spr_cap_stock_entry_lines_to_max_transferable(se)


def _spr_cap_stock_entry_lines_to_max_transferable(se) -> None:
	"""Cap each outbound line on a Stock Entry to available source-warehouse / batch qty."""
	if not se:
		return
	for d in se.items or []:
		if not d.item_code or not d.get("s_warehouse"):
			continue
		_spr_finalize_mtfm_line_qty(
			d,
			d.s_warehouse,
			flt(d.get("transfer_qty") or d.get("qty")),
		)


class _SprWipTopupRetry(Exception):
	"""Signal manufacture chunk should rebuild after auto WIP top-up transfer."""


def _spr_resolve_expense_account(item_code: str, company: str, warehouse: str | None = None) -> str:
	"""Resolve expense_account for Stock Entry lines (perpetual inventory sites)."""
	item_code = _cstr(item_code).strip()
	company = _cstr(company).strip()
	if not item_code or not company:
		return ""
	acc = frappe.db.get_value(
		"Item Default",
		{"parent": item_code, "company": company},
		"expense_account",
	)
	if acc:
		return _cstr(acc)
	try:
		from erpnext.stock.get_item_details import get_item_details

		row = get_item_details(
			{
				"item_code": item_code,
				"company": company,
				"warehouse": warehouse or "",
				"qty": 1,
				"doctype": "Stock Entry",
			}
		)
		acc = (row or {}).get("expense_account")
		if acc:
			return _cstr(acc)
	except Exception:
		pass
	item_meta = frappe.get_meta("Item")
	if item_meta.has_field("expense_account"):
		acc = frappe.db.get_value("Item", item_code, "expense_account")
		if acc:
			return _cstr(acc)
	company_meta = frappe.get_meta("Company")
	for fld in ("stock_adjustment_account", "default_expense_account"):
		if company_meta.has_field(fld):
			acc = frappe.db.get_value("Company", company, fld)
			if acc:
				return _cstr(acc)
	return ""


def _spr_apply_stock_entry_item_accounts(se) -> None:
	"""Fill expense_account / cost_center on Stock Entry item lines before insert/submit."""
	company = _cstr(getattr(se, "company", None)).strip()
	if not company or not se:
		return
	line_meta = frappe.get_meta("Stock Entry Detail")
	has_expense = line_meta.has_field("expense_account")
	has_cc = line_meta.has_field("cost_center")
	if not has_expense and not has_cc:
		return
	default_cc = frappe.db.get_value("Company", company, "cost_center") if has_cc else None
	for d in se.items or []:
		if not d.item_code:
			continue
		wh = _cstr(d.get("s_warehouse") or d.get("t_warehouse") or getattr(se, "wip_warehouse", None))
		if has_expense and not _cstr(d.get("expense_account")):
			acc = _spr_resolve_expense_account(d.item_code, company, wh)
			if acc:
				d.expense_account = acc
		if has_cc and not _cstr(d.get("cost_center")) and default_cc:
			d.cost_center = default_cc


def _spr_apply_bag_rm_qty_from_bom(se, bom_no: str, fg_qty: float) -> None:
	"""Replace RM line qty on Stock Entry with BOM×FG using Meter→Kg divide (matches WO/PP)."""
	fg_qty = flt(fg_qty)
	if fg_qty <= 0 or not se:
		return
	rm_map, _multi = _bom_rm_stock_qty_map_for_fg(_cstr(bom_no), fg_qty)
	if not rm_map:
		return
	for d in se.items or []:
		if not d.item_code or d.get("t_warehouse"):
			continue
		needed = _spr_round_rm_stock_qty(rm_map.get(_cstr(d.item_code)))
		if needed <= 0:
			continue
		stock_uom = frappe.db.get_value("Item", d.item_code, "stock_uom") or d.stock_uom or "Kg"
		d.uom = stock_uom
		d.stock_uom = stock_uom
		d.conversion_factor = 1.0
		d.transfer_qty = needed
		d.qty = needed


def _batch_fields_from_spr_row(batch_meta, spr_row, is_bag_spr: bool = False) -> dict:
	"""Map Roll Production Result line to Batch fields (Net/Gross Weight Kgs, Length Mtrs, CBM)."""
	if not spr_row:
		return {}
	out = {}
	fn_n = _batch_field_net_weight_kgs(batch_meta)
	fn_g = _batch_field_gross_weight_kgs(batch_meta)
	fn_l = _batch_field_length_mtrs(batch_meta)
	if fn_n is not None and _spr_row_get(spr_row, "net_weight") is not None:
		out[fn_n] = flt(_spr_row_get(spr_row, "net_weight"))
	if fn_g is not None and _spr_row_get(spr_row, "gross_weight") is not None:
		out[fn_g] = flt(_spr_row_get(spr_row, "gross_weight"))
	ln = _spr_length_meters(spr_row)
	if fn_l is not None and ln is not None:
		out[fn_l] = flt(ln)
	# Explicit mapping required: SPR produced_length_mtrs -> Batch custom_meter.
	meter_from_spr = _spr_row_get(spr_row, "produced_length_mtrs")
	if batch_meta.has_field("custom_meter") and meter_from_spr not in (None, ""):
		out["custom_meter"] = flt(meter_from_spr)
	if batch_meta.has_field("custom_cbm") and _spr_row_get(spr_row, "custom_cbm") is not None:
		out["custom_cbm"] = flt(_spr_row_get(spr_row, "custom_cbm"))

	def _set_first_batch_field(candidates: tuple[str, ...], value, label_tokens: tuple[str, ...] = ()):
		if value in (None, ""):
			return
		for fn in candidates:
			if batch_meta.has_field(fn):
				out[fn] = value
				return
		if label_tokens:
			for df in (batch_meta.fields or []):
				lab = (df.label or "").lower()
				if all(t in lab for t in label_tokens):
					out[df.fieldname] = value
					return

	# Batch.custom_party_code_text ΓåÉ Roll Production line.party_code (explicit; fallback legacy line text)
	party_for_batch_party_field = _cstr(_spr_row_get(spr_row, "party_code")) or _cstr(
		_spr_row_get(spr_row, "custom_party_code_text")
	)
	_set_first_batch_field(("custom_party_code_text",), party_for_batch_party_field, ("party", "code"))

	order_code = (
		_cstr(_spr_row_get(spr_row, "custom_order_code"))
		or _cstr(_spr_row_get(spr_row, "order_code"))
		or _cstr(_spr_row_get(spr_row, "custom_party_code_text"))
		or _cstr(_spr_row_get(spr_row, "party_code"))
	)
	work_order = _cstr(_spr_row_get(spr_row, "work_order") or _spr_row_get(spr_row, "wo_id"))
	roll_numbers = _spr_row_get(spr_row, "roll_numbers")
	roll_no = _spr_row_get(spr_row, "roll_no") or roll_numbers

	_set_first_batch_field(
		("custom_order_code", "order_code", "party_code"),
		order_code,
		("order", "code"),
	)
	_set_first_batch_field(
		("work_order", "custom_work_order", "wo_no", "custom_wo_no"),
		work_order,
		("work", "order"),
	)
	_set_first_batch_field(
		("roll_no", "custom_roll_no", "roll_number", "custom_roll_number"),
		roll_no,
		("roll",),
	)
	_set_first_batch_field(
		("custom_roll_numbers", "roll_numbers", "custom_source_roll_numbers", "source_roll_numbers"),
		roll_numbers,
	)
	if is_bag_spr:
		pcs = flt(_spr_row_get(spr_row, "custom_achieved_bag_pcs"))
		if pcs > 0:
			_set_first_batch_field(("custom_produced_bagpcs",), pcs, ("produced", "bag"))
			if batch_meta.has_field("custom_produced_bagpcs"):
				ft = batch_meta.get_field("custom_produced_bagpcs").fieldtype
				out["custom_produced_bagpcs"] = _cstr(int(pcs)) if ft == "Data" else pcs
		bag_sz = _cstr(_spr_row_get(spr_row, "custom_bag_size"))
		if bag_sz:
			_set_first_batch_field(("custom_bag_size", "bag_size"), bag_sz, ("bag", "size"))
		for val, cands, tokens in (
			(_spr_row_get(spr_row, "quality"), ("custom_quality", "quality"), ("quality",)),
			(_spr_row_get(spr_row, "color"), ("custom_color", "color"), ("color",)),
			(_spr_row_get(spr_row, "gsm"), ("custom_gsm", "gsm"), ("gsm",)),
			(flt(_spr_row_get(spr_row, "width_inch") or 0), ("custom_width_inch", "width_inch"), ("width",)),
		):
			if val not in (None, "", 0):
				_set_first_batch_field(cands, val, tokens)
	return out


def _production_plan_custom_shaft_child_doctype() -> str | None:
	"""Child table Doctype behind Production Plan.custom_shaft_details (e.g. Shaft Plan Detail)."""
	try:
		pp_meta = frappe.get_meta("Production Plan")
	except Exception:
		return None
	for fname in ("custom_shaft_details", "custom_shaft_detail"):
		if not pp_meta.has_field(fname):
			continue
		f = pp_meta.get_field(fname)
		if f.fieldtype == "Table" and f.options:
			return f.options
	return None


def _looks_like_frappe_row_name(s: str) -> bool:
	"""Heuristic: autogenerated child row names are often long alphanumeric strings."""
	t = _cstr(s)
	if len(t) < 9:
		return False
	return t.isalnum()


def resolve_label_from_pp_doc(pp_doc) -> str:
	"""Label / label type from Production Plan header or first shaft detail row (sites use different field names)."""
	if not pp_doc:
		return ""
	try:
		meta = frappe.get_meta("Production Plan")
		for fn in (
			"custom_label",
			"label",
			"label_type",
			"custom_label_type",
			"type_of_label",
			"custom_type_of_label",
			"custom_print_type",
			"print_type",
		):
			if meta.has_field(fn):
				v = _cstr(pp_doc.get(fn))
				if v:
					return v
		for tbl in ("custom_shaft_details", "shaft_details"):
			if not meta.has_field(tbl):
				continue
			rows = pp_doc.get(tbl) or []
			if not rows:
				continue
			r0 = rows[0]
			for fn in ("custom_label", "label", "label_type", "type_of_label", "custom_label_type"):
				try:
					raw = r0.get(fn) if isinstance(r0, dict) else getattr(r0, fn, None)
				except Exception:
					raw = None
				v = _cstr(raw)
				if v:
					return v
	except Exception:
		pass
	return ""


def resolve_label_from_planning_sheet_doc(sheet_doc) -> str:
	"""Fallback label when PP header has no label field populated."""
	if not sheet_doc:
		return ""
	try:
		meta = frappe.get_meta("Planning sheet")
		for fn in (
			"custom_label",
			"label",
			"label_type",
			"custom_label_type",
			"type_of_label",
			"custom_type_of_label",
		):
			if meta.has_field(fn):
				v = _cstr(sheet_doc.get(fn))
				if v:
					return v
	except Exception:
		pass
	return ""


def _production_plan_total_planned_qty(production_plan: str) -> float:
	"""Resolve planned KG from Production Plan fields, then fall back to linked Work Orders sum."""
	if not production_plan or not frappe.db.exists("Production Plan", production_plan):
		return 0.0

	try:
		wo_qty = flt(
			frappe.db.sql(
				"""
				SELECT IFNULL(SUM(wo.qty), 0)
				FROM `tabWork Order` wo
				WHERE wo.production_plan = %(pp)s
				  AND wo.docstatus < 2
				""",
				{"pp": production_plan},
			)[0][0]
		)
		frappe.logger().info(f"[_production_plan_total_planned_qty] {production_plan}: WO qty sum = {wo_qty}")
		if wo_qty > 0:
			return wo_qty
	except Exception as e:
		frappe.logger().error(f"[_production_plan_total_planned_qty] Error fetching WO sum for {production_plan}: {e}")
		pass

	# Sum Production Plan Item rows (ERPNext / custom PPs)
	try:
		pp = frappe.get_doc("Production Plan", production_plan)
		pp_meta = frappe.get_meta("Production Plan")
		for tbl in ("po_items", "prod_order_items", "items", "production_plan_item", "custom_production_plan_items"):
			if not pp_meta.has_field(tbl):
				continue
			s = 0.0
			for row in pp.get(tbl) or []:
				if isinstance(row, dict):
					pq = row.get("planned_qty") or row.get("qty")
				else:
					pq = getattr(row, "planned_qty", None) or getattr(row, "qty", None)
				s += flt(pq)
			if s > 0:
				frappe.logger().info(f"[_production_plan_total_planned_qty] {production_plan}: sum {tbl} = {s}")
				return s
	except Exception as e:
		frappe.logger().error(f"[_production_plan_total_planned_qty] PP item sum error {production_plan}: {e}")

	# Final fallback to direct PP scalar fields
	try:
		pp = frappe.get_doc("Production Plan", production_plan)
		pp_meta = frappe.get_meta("Production Plan")
		for fn in (
			"custom_total_planned_qty",
			"total_planned_qty",
			"custom_total_weight_kgs",
			"total_weight_kgs",
			"planned_qty",
			"qty",
		):
			if pp_meta.has_field(fn):
				v = flt(pp.get(fn))
				if v > 0:
					return v
	except Exception:
		pass

	return 0.0


def _production_plan_total_planned_pcs(production_plan: str) -> float:
	"""Sum planned bag/sheet PCS from PP bundle rows (box-bag / bundle calc)."""
	pp_doc = _get_pp_doc(production_plan)
	if not pp_doc:
		return 0.0
	total = 0.0
	for src in _read_pp_bundle_calculation_rows(production_plan):
		tpb = flt(src.get("total_pcs_per_bundle") or 0)
		if tpb <= 0:
			n_boxes = flt(src.get("no_of_boxes") or 0)
			pcs = cint(src.get("pcs_per_packet") or 0)
			pkts = cint(src.get("pkts_per_bundle") or 0)
			if n_boxes > 0 and pcs > 0:
				tpb = flt(n_boxes * pcs)
			elif pkts > 0 and pcs > 0:
				tpb = flt(pkts * pcs)
		if tpb > 0:
			total += tpb
	if total > 0:
		return flt(total, 0)
	try:
		wo_qty = flt(
			frappe.db.sql(
				"""
				SELECT IFNULL(SUM(wo.qty), 0)
				FROM `tabWork Order` wo
				WHERE wo.production_plan = %(pp)s
				  AND wo.docstatus < 2
				""",
				{"pp": production_plan},
			)[0][0]
		)
		if wo_qty > 0:
			return flt(wo_qty, 0)
	except Exception:
		pass
	return 0.0


def _effective_weight_kg_for_produced_gsm(row) -> float:
	"""Prefer net weight; if not entered yet, use gross (same rule as desk JS spr_update_produced_gsm)."""
	nw = flt(getattr(row, "net_weight", None))
	if nw > 0:
		return nw
	return flt(getattr(row, "gross_weight", None))


def compute_produced_gsm(weight_kg, width_inch, length_m) -> float:
	"""Roll line GSM from actuals: (weight_kg * 10000) / (width_inch * length_m * 0.254)."""
	wgt = flt(weight_kg)
	w = flt(width_inch)
	ln = flt(length_m)
	den = w * ln * 0.254
	if den <= 0:
		return 0.0
	return round((wgt * 10000.0) / den, 2)


def compute_mix_roll_planned_qty_kg(gsm, width_inch, length_m) -> float:
	"""Mix-roll line planned qty (kg): gsm * width_inch * length_m * 0.0254 / 1000."""
	g, w, ln = flt(gsm), flt(width_inch), flt(length_m)
	if g <= 0 or w <= 0 or ln <= 0:
		return 0.0
	return round(g * w * ln * 0.0254 / 1000, 2)


def _spr_mix_roll_planned_length_m(row) -> float:
	"""Length for mix-roll planned qty: meter_roll / ordered length only (not produced)."""
	for key in (
		"meter_roll",
		"meter_roll_mtrs",
		"custom_meter_roll_mtrs",
		"ordered_length",
		"ordered_length_mtrs",
		"custom_ordered_length",
	):
		v = _spr_row_get(row, key)
		if v is not None and flt(v) > 0:
			return flt(v)
	return 0.0


def _work_order_names_for_pp_job(production_plan: str, m: dict, idx: int) -> str:
	"""Comma-separated WO names for this shaft row (same rules as _get_work_orders_for_spr_job)."""
	
	# Extract GSM if available in job row
	job_gsm = None
	try:
		if m.get("gsm"):
			job_gsm = int(flt(m.get("gsm")))
	except Exception:
		pass

	wos = _resolve_wos_for_pp_job_row(
		production_plan,
		ppi=m.get("production_plan_item"),
		job_id=m.get("job_id"),
		row_index=idx,
		combination=m.get("combination"),
		job_gsm=job_gsm,
	)
	return ", ".join(w["name"] for w in wos) if wos else ""


def _build_shaft_jobs_from_custom_shaft_details(production_plan: str) -> list[dict] | None:
	"""
	Load Available Jobs from Production Plan.custom_shaft_details (Table field on PP).
	Maps rows to Shaft Production Run Job; prefers human-readable Job column for job_id.
	"""
	child_dt = _production_plan_custom_shaft_child_doctype()
	if not child_dt or not frappe.db.exists("DocType", child_dt):
		return None
	if not production_plan or not frappe.db.exists("Production Plan", production_plan):
		return None
	pp_rows = frappe.db.sql(
		f"""
		SELECT * FROM `tab{child_dt}`
		WHERE parent = %(p)s
		ORDER BY idx ASC
		""",
		{"p": production_plan},
		as_dict=True,
	)
	if not pp_rows:
		return None
	job_meta = frappe.get_meta("Shaft Production Run Job")
	out: list[dict] = []
	for idx, r in enumerate(pp_rows):
		m: dict = {}
		# Shaft Plan Detail: Job is field s_no (Int); also accept job / job_no / job_id
		readable = None
		if r.get("s_no") is not None and _cstr(r.get("s_no")) != "":
			try:
				readable = str(int(flt(r["s_no"])))
			except (TypeError, ValueError):
				readable = _cstr(r.get("s_no"))
		if not readable:
			readable = (
				_cstr(r.get("job"))
				if r.get("job") is not None and _cstr(r.get("job")) != ""
				else None
			)
		if not readable:
			readable = r.get("job_no") or r.get("job_id")
		if not readable or _cstr(readable) == "":
			readable = str(idx + 1)
		m["job_id"] = _cstr(readable)

		ppi = r.get("production_plan_item") or r.get("against_production_plan_item")
		if not ppi and _looks_like_frappe_row_name(_cstr(r.get("name", ""))):
			ppi = r.get("name")
		if ppi and job_meta.has_field("production_plan_item"):
			m["production_plan_item"] = _cstr(ppi)

		comb = r.get("shaft_combination") or r.get("combination")
		if comb is not None and job_meta.has_field("combination"):
			m["combination"] = comb

		# Map Shaft Plan Detail fieldnames: combined_width, meter__roll, no_of_shaft, total_weight_kgs
		field_aliases = {
			"gsm": ("gsm", "custom_gsm"),
			"quality": ("quality", "custom_quality"),
			"notes": ("notes", "custom_notes"),
			"total_width": (
				"combined_width",
				"total_width",
				"total_width_inches",
				"custom_total_width",
			),
			"meter_roll_mtrs": (
				"meter__roll",
				"meter_roll_mtrs",
				"meter_per_roll",
				"custom_meter_roll_mtrs",
			),
			"no_of_shafts": ("no_of_shafts", "no_of_shaft", "custom_no_of_shafts"),
			"no_of_rolls": ("no_of_rolls", "roll_count_per_shaft", "custom_no_of_rolls"),
			"net_weight": ("net_weight", "net_weight_per_shaft", "custom_net_weight_per_shaft"),
			"total_weight": ("total_weight_kgs", "total_weight", "custom_total_weight"),
			"custom_total_achieved_weight": ("custom_total_achieved_weight",),
			"party_code": ("party_code", "order_code", "custom_party_code"),
			"work_orders": ("work_orders", "custom_work_orders"),
		}
		for target, aliases in field_aliases.items():
			if not job_meta.has_field(target):
				continue
			for a in aliases:
				if a in r and r[a] is not None and _cstr(r[a]) != "":
					val = r[a]
					if target == "net_weight" and not isinstance(val, str):
						val = str(val)
					m[target] = val
					break

		if m.get("gsm") is not None and m.get("gsm") != "":
			try:
				m["gsm"] = int(flt(str(m["gsm"]).strip().split()[0]))
			except Exception:
				pass

		skip_copy = {
			"name",
			"owner",
			"creation",
			"modified",
			"modified_by",
			"docstatus",
			"idx",
			"parent",
			"parentfield",
			"parenttype",
			"doctype",
		}
		skip_alias = {
			"job",
			"job_no",
			"job_id",
			"s_no",
			"name",
			"production_plan_item",
			"against_production_plan_item",
			"shaft_combination",
			"combination",
			"combined_width",
			"meter__roll",
			"no_of_shaft",
			"total_weight_kgs",
		}
		for fn, v in r.items():
			if fn in skip_copy or fn in skip_alias or v is None:
				continue
			if not job_meta.has_field(fn):
				continue
			if fn not in m:
				if fn == "net_weight" and not isinstance(v, str):
					m[fn] = str(v)
				else:
					m[fn] = v

		jn = m.get("job_id")
		job_gsm = None
		if m.get("gsm") is not None and m.get("gsm") != "":
			try:
				job_gsm = int(flt(str(m.get("gsm")).strip().split()[0]))
			except Exception:
				try:
					job_gsm = int(flt(m.get("gsm")))
				except Exception:
					pass
		wos_res = _resolve_wos_for_pp_job_row(
			production_plan,
			ppi=m.get("production_plan_item"),
			job_id=_cstr(jn) if jn else None,
			row_index=idx,
			combination=m.get("combination"),
			job_gsm=job_gsm,
		)
		if jn and (not m.get("total_weight")) and wos_res:
			tw = sum(flt(w.get("planned_qty")) for w in wos_res)
			if flt(tw) > 0:
				m["total_weight"] = flt(tw)
		if job_meta.has_field("work_orders"):
			m["work_orders"] = ", ".join(w["name"] for w in wos_res) if wos_res else ""
		_fill_party_code_from_resolved_wos(m, job_meta, wos_res)

		out.append(m)
	return out or None


def _ordered_production_plan_items(production_plan: str) -> list[str]:
	"""Distinct Work Order production_plan_item values in stable order (for ordinal WO fallback)."""
	rows = frappe.db.sql(
		"""
		SELECT wo.production_plan_item AS ppi, MIN(wo.creation) AS mc
		FROM `tabWork Order` wo
		WHERE wo.production_plan = %(pp)s
		  AND wo.docstatus < 2
		  AND IFNULL(wo.production_plan_item, '') != ''
		GROUP BY wo.production_plan_item
		ORDER BY mc ASC, ppi ASC
		""",
		{"pp": production_plan},
		as_dict=True,
	)
	return [_cstr(r.ppi) for r in rows]


def _spr_job_row_index(spr_doc, job_row) -> int | None:
	rows = list(_spr_job_rows(spr_doc))
	for i, r in enumerate(rows):
		if getattr(r, "name", None) and getattr(job_row, "name", None) and r.name == job_row.name:
			return i
	jid = _cstr(_spr_job_id(job_row))
	for i, r in enumerate(rows):
		if _cstr(_spr_job_id(r)) == jid:
			return i
	return None


def _get_all_work_orders_for_production_plan(pp_name: str) -> list:
	"""All Work Orders for a Production Plan (fallback when job id does not match production_plan_item)."""
	if not pp_name:
		return []
	return frappe.db.sql(
		"""
		SELECT wo.name, wo.production_item, wo.qty as planned_qty, wo.produced_qty, wo.status
		FROM `tabWork Order` wo
		WHERE wo.production_plan = %(pp)s
		  AND wo.docstatus != 2
		ORDER BY wo.creation ASC, wo.name ASC
		""",
		{"pp": pp_name},
		as_dict=True,
	)


def _parse_combination_widths_inches(combination) -> list[float]:
	"""Numeric widths per '+' segment, aligned with _count_combination_segments (e.g. 39\" + 24\" ΓåÆ [39, 24])."""
	if not combination:
		return []
	parts = [p.strip() for p in re.split(r"\+", str(combination)) if p.strip()]
	out: list[float] = []
	for part in parts:
		m = re.search(r"(\d+(?:\.\d+)?)", part.replace(",", ""))
		if m:
			out.append(flt(m.group(1)))
	return out


def _match_work_orders_to_combination_segments(
	pp_name: str,
	combination: str,
	ppi: str | None = None,
	job_gsm: int | None = None,
	job_id: str | None = None,
) -> list | None:
	"""
	For multi-width combinations (e.g. ``46\"+42\"+38\"`` or ``63\"+63\"``),
	match each segment to a Work Order using ``(GSM, width)`` from the WO's item code.

	PPI-scoped queries often return only **one** WO per ``production_plan_item``, while a
	single shaft job row lists **several different widths** — each width is usually its own
	WO on the plan. When ``distinct_widths >= 2`` and we have fewer WOs than combination
	segments, we load **all** work orders on the Production Plan so each width can match.

	Same-width repeats (e.g. ``42+42+42``) deduplicate to one WO.
	"""
	comb = _cstr(combination)
	if not comb:
		return None
	segs = _count_combination_segments(comb)
	if segs < 2:
		return None
	widths = _parse_combination_widths_inches(comb)
	if len(widths) < segs:
		return None
	widths = widths[:segs]
	all_wos: list = []
	if ppi:
		all_wos = list(get_work_orders_for_job(pp_name, _cstr(ppi)) or [])
	if not all_wos and job_id:
		all_wos = list(get_work_orders_for_job(pp_name, _cstr(job_id)) or [])

	# If we have fewer WOs than segments, expand to PP-wide candidates for width matching.
	if len(all_wos) < segs:
		all_wos = list(_get_all_work_orders_for_production_plan(pp_name) or [])
	elif not all_wos:
		all_wos = list(_get_all_work_orders_for_production_plan(pp_name) or [])

	if not all_wos:
		return None
	
	# Γ£à Build (GSM, WIDTH) ΓåÆ WO map using ITEM CODE parsing
	gsm_width_to_wo_map = {}
	for wo in all_wos:
		wo_name = _cstr(wo.get("name"))
		try:
			production_item = wo.get("production_item")
			if not production_item:
				continue
			# Parse item code to extract GSM and WIDTH
			parsed_gsm, parsed_width = parse_item_code(_cstr(production_item))
			if parsed_gsm > 0 and parsed_width > 0:
				key = (parsed_gsm, parsed_width)
				gsm_width_to_wo_map[key] = wo
				frappe.logger().info(f"[COMBO] WO {wo_name} = ({parsed_gsm}, {parsed_width}\") (PPI {ppi})")
		except Exception as e:
			frappe.logger().warning(f"[COMBO ERROR] Could not parse WO {wo_name}: {str(e)}")
	
	if not job_gsm:
		frappe.logger().warning(f"[COMBO] No job_gsm provided, cannot match")
		return None
	
	out: list = []
	tol = 1.25
	for target_w in widths:
		# Match by (GSM, WIDTH) tuple
		key = (job_gsm, target_w)
		if key in gsm_width_to_wo_map:
			best = gsm_width_to_wo_map[key]
			out.append(best)
			frappe.logger().info(f"[COMBO] Segment ({job_gsm}, {target_w}\") ΓåÆ WO {best.get('name')}")
		else:
			# Fallback: find by width closest to target
			best = None
			best_d = 999.0
			for (w_gsm, w_width), wo in gsm_width_to_wo_map.items():
				if abs(w_width - target_w) < best_d:
					best_d = abs(w_width - target_w)
					best = wo
			
			if best and best_d <= tol:
				out.append(best)
				frappe.logger().warning(f"[COMBO] No exact match for ({job_gsm}, {target_w}\"), fallback")
			else:
				frappe.logger().warning(f"[COMBO] No WO found for ({job_gsm}, {target_w}\")")
				return None
	
	# Γ£à DEDUPLICATE: For "63+63", return only UNIQUE WOs
	seen = set()
	unique_out = []
	for wo in out:
		wo_name = _cstr(wo.get("name"))
		if wo_name not in seen:
			seen.add(wo_name)
			unique_out.append(wo)
			frappe.logger().info(f"[COMBO DEDUP] Keep WO {wo_name}")
		else:
			frappe.logger().info(f"[COMBO DEDUP] Skip duplicate WO {wo_name}")
	
	return unique_out if len(unique_out) > 0 else None


def _wo_has_gsm(wo: dict, target_gsm: int) -> bool:
	"""Check if a WO's item has matching GSM."""
	try:
		prod_item = wo.get("production_item")
		if prod_item:
			gsm, width = parse_item_code(_cstr(prod_item))
			return gsm == target_gsm
	except Exception:
		pass
	return False


def _pick_one_wo_by_gsm(wos: list, job_gsm: int | None) -> list:
	"""Narrow a WO list to one row; prefer GSM match on production_item when several WOs share a PPI."""
	if not wos:
		return []
	if len(wos) == 1:
		return wos
	if job_gsm and job_gsm > 0:
		for wo in wos:
			try:
				prod_item = wo.get("production_item")
				if prod_item:
					gsm, _width = parse_item_code(_cstr(prod_item))
					if gsm == job_gsm:
						return [wo]
			except Exception:
				pass
	return [wos[0]]


def _pick_wos_by_gsm_and_width(wos: list, job_gsm: int | None, combination: str | None = None) -> list:
	"""Pick WO(s) by width (+ GSM when available). Supports single-width and multi-width combinations."""
	if not wos:
		return []
	widths = _parse_combination_widths_inches(combination) if combination else []
	if widths:
		tol = 0.75
		out: list = []
		seen = set()
		for tw in widths:
			best = None
			# 1) Prefer exact GSM + width
			if job_gsm and job_gsm > 0:
				for wo in wos:
					try:
						prod_item = wo.get("production_item")
						if not prod_item:
							continue
						gsm, ww = parse_item_code(_cstr(prod_item))
						if gsm == int(job_gsm) and abs(flt(ww) - flt(tw)) <= tol:
							best = wo
							break
					except Exception:
						pass
			# 2) Width-only fallback (if no GSM or no exact GSM+width)
			if best is None:
				for wo in wos:
					try:
						prod_item = wo.get("production_item")
						if not prod_item:
							continue
						_gsm, ww = parse_item_code(_cstr(prod_item))
						if abs(flt(ww) - flt(tw)) <= tol:
							best = wo
							break
					except Exception:
						pass
			if best:
				nm = _cstr(best.get("name"))
				if nm and nm not in seen:
					seen.add(nm)
					out.append(best)
		if out:
			return out
	return _pick_one_wo_by_gsm(wos, job_gsm)


def _resolve_wos_for_pp_job_row(
	pp_name: str,
	*,
	ppi: str | None = None,
	job_id: str | None = None,
	row_index: int | None = None,
	combination: str | None = None,
	job_gsm: int | None = None,
) -> list:
	"""Resolve Work Orders for one Available Jobs row.

	Multi-segment combinations (e.g. ``46\"+42\"+38\"``) return one WO per segment via
	``(GSM, width)`` on the WO item code when possible. Same-width segments share one WO.

	If ``production_plan_item`` does not match any Work Order link, we fall back to ``job_id``,
	then row order, then any WO on the plan (so the grid does not stay blank when PPI is stale).
	"""
	comb = _cstr(combination).strip() if combination else ""
	widths = _parse_combination_widths_inches(comb) if comb else []
	# Width-aware resolver for both single-width and multi-width rows.
	# This prevents picking same WO for different widths (e.g. 120" vs 63"+63").
	if comb and widths and job_gsm:
		candidates = _get_all_work_orders_for_production_plan(pp_name)
		if candidates:
			picked = _pick_wos_by_gsm_and_width(candidates, job_gsm, comb)
			if picked:
				return picked

	if comb and _count_combination_segments(comb) >= 2:
		jg = job_gsm
		if not jg:
			for ref in (ppi, job_id):
				if not ref:
					continue
				wl = get_work_orders_for_job(pp_name, _cstr(ref))
				if wl and wl[0].get("production_item"):
					try:
						g, _w = parse_item_code(_cstr(wl[0].get("production_item")))
						if g > 0:
							jg = int(g)
							break
					except Exception:
						pass
		if jg:
			matched = _match_work_orders_to_combination_segments(
				pp_name,
				comb,
				ppi=_cstr(ppi) if ppi else None,
				job_gsm=int(jg),
				job_id=_cstr(job_id) if job_id else None,
			)
			if matched:
				return matched

	if ppi:
		wos = get_work_orders_for_job(pp_name, _cstr(ppi))
		if wos:
			return _pick_wos_by_gsm_and_width(wos, job_gsm, comb)

	if job_id:
		wos = get_work_orders_for_job(pp_name, _cstr(job_id))
		if wos:
			return _pick_wos_by_gsm_and_width(wos, job_gsm, comb)

	if row_index is not None:
		ord_ppi = _ordered_production_plan_items(pp_name)
		if ord_ppi and 0 <= row_index < len(ord_ppi):
			wos = get_work_orders_for_job(pp_name, ord_ppi[row_index])
			if wos:
				return _pick_wos_by_gsm_and_width(wos, job_gsm, comb)

	all_wos = _get_all_work_orders_for_production_plan(pp_name)
	return _pick_wos_by_gsm_and_width(all_wos, job_gsm, comb) if all_wos else []


def _get_work_orders_for_spr_job(pp_name: str, spr_doc, job_row):
	"""Resolve Work Orders for a job row.

	Priority:
	1) Explicit Available Jobs.work_orders (manual jobs must stay pinned to these WOs)
	2) production_plan_item / job_id / row index heuristics for auto jobs
	"""
	# Manual jobs can coexist with auto jobs on same PP/WO dimensions; never re-resolve away
	# from explicitly selected WO(s) in the row.
	explicit_wos = _cstr(getattr(job_row, "work_orders", None) or "")
	if explicit_wos:
		names: list[str] = []
		seen = set()
		for raw in explicit_wos.replace("\n", ",").split(","):
			wo_name = _cstr(raw).strip()
			if not wo_name or wo_name in seen:
				continue
			if frappe.db.exists("Work Order", wo_name):
				names.append(wo_name)
				seen.add(wo_name)
		if names:
			wo_rows = (
				frappe.get_all(
					"Work Order",
					filters={"name": ["in", names], "docstatus": ["!=", 2]},
					fields=["name", "production_item", "qty", "produced_qty", "status"],
				)
				or []
			)
			by_name = {_cstr(r.get("name")): r for r in wo_rows}
			ordered = []
			for nm in names:
				row = by_name.get(nm)
				if not row:
					continue
				ordered.append(
					{
						"name": row.get("name"),
						"production_item": row.get("production_item"),
						"planned_qty": flt(row.get("qty")),
						"produced_qty": flt(row.get("produced_qty")),
						"status": row.get("status"),
					}
				)
			if ordered:
				return ordered
	meta = frappe.get_meta("Shaft Production Run Job")
	ppi = None
	if meta.has_field("production_plan_item"):
		ppi = getattr(job_row, "production_plan_item", None)
	jid = _spr_job_id(job_row)
	idx = _spr_job_row_index(spr_doc, job_row)
	comb = getattr(job_row, "combination", None) if meta.has_field("combination") else None
	# Γ£à Extract GSM from job_row for (GSM, WIDTH) matching
	job_gsm = None
	if meta.has_field("gsm"):
		try:
			gsm_val = getattr(job_row, "gsm", None)
			if gsm_val:
				job_gsm = int(flt(gsm_val))
		except Exception:
			pass
	return _resolve_wos_for_pp_job_row(pp_name, ppi=ppi, job_id=jid, row_index=idx, combination=comb, job_gsm=job_gsm)


def _build_shaft_jobs_from_pp_details(production_plan: str) -> list[dict] | None:
	"""One row per Production Plan Shaft Detail line, field-aligned with Shaft Production Run Job."""
	if not production_plan or not frappe.db.exists("DocType", "Production Plan Shaft Detail"):
		return None
	if not frappe.db.exists("Production Plan", production_plan):
		return None
	pp_rows = frappe.db.sql(
		"""
		SELECT * FROM `tabProduction Plan Shaft Detail`
		WHERE parent = %(p)s
		ORDER BY idx ASC
		""",
		{"p": production_plan},
		as_dict=True,
	)
	if not pp_rows:
		return None
	job_meta = frappe.get_meta("Shaft Production Run Job")
	out: list[dict] = []
	for idx, r in enumerate(pp_rows):
		m: dict = {}
		jn = r.get("job_no") or r.get("job_id")
		if not jn:
			continue
		m["job_id"] = _cstr(jn)
		if job_meta.has_field("production_plan_item"):
			# Use explicit PP-item link only when row already carries a real child-row name.
			ppi = _cstr(r.get("production_plan_item") or r.get("against_production_plan_item"))
			if ppi and frappe.db.exists("Production Plan Item", ppi):
				m["production_plan_item"] = ppi
		if r.get("shaft_combination") is not None and job_meta.has_field("combination"):
			m["combination"] = r.get("shaft_combination")
		for fn in (
			"gsm",
			"quality",
			"combination",
			"notes",
			"total_width",
			"meter_roll_mtrs",
			"net_weight",
			"total_weight",
			"custom_total_achieved_weight",
			"no_of_shafts",
			"party_code",
			"work_orders",
		):
			if fn in r and r[fn] is not None and job_meta.has_field(fn):
				m[fn] = r[fn]
		job_gsm = None
		if m.get("gsm"):
			try:
				job_gsm = int(flt(m.get("gsm")))
			except Exception:
				pass
		wos_res = _resolve_wos_for_pp_job_row(
			production_plan,
			ppi=m.get("production_plan_item"),
			job_id=_cstr(jn),
			row_index=idx,
			combination=m.get("combination"),
			job_gsm=job_gsm,
		)
		if (not m.get("total_weight")) and jn and wos_res:
			tw = sum(flt(w.get("planned_qty")) for w in wos_res)
			if flt(tw) > 0:
				m["total_weight"] = flt(tw)
		if job_meta.has_field("work_orders") and not m.get("work_orders"):
			m["work_orders"] = ", ".join(w["name"] for w in wos_res) if wos_res else ""
		_fill_party_code_from_resolved_wos(m, job_meta, wos_res)
		out.append(m)
	return out or None


def _spr_net_weight_tolerance_percent() -> float:
	"""Allowed deviation of roll net (or gross) vs planned_qty (%). Set `spr_net_weight_tolerance_percent` in site_config."""
	pc = frappe.conf.get("spr_net_weight_tolerance_percent")
	if pc is not None:
		return max(flt(pc), 0.0)
	return 5.0


def _spr_effective_roll_weight_kg_for_tolerance(row) -> float:
	nw = flt(_spr_row_get(row, "net_weight"))
	if nw > 0:
		return nw
	return flt(_spr_row_get(row, "gross_weight"))


def _spr_collect_roll_planned_tolerance_violations(doc) -> list[tuple]:
	spi = frappe.get_meta("Shaft Production Run Item")
	if not spi.has_field("planned_qty"):
		return []
	tol = _spr_net_weight_tolerance_percent()
	if tol <= 0:
		return []
	out: list[tuple] = []
	for row in doc.items or []:
		pq = flt(_spr_row_get(row, "planned_qty"))
		if pq <= 0:
			continue
		act = _spr_effective_roll_weight_kg_for_tolerance(row)
		if act <= 0:
			continue
		dev_pct = abs(act - pq) / pq * 100.0
		if dev_pct > tol + 1e-9:
			jb = _cstr(_spr_row_get(row, "job"))
			rn = _spr_row_get(row, "roll_no")
			out.append((jb, rn, pq, act, dev_pct))
	return out


def _spr_unique_text_values(values: list) -> list[str]:
	seen_upper = set()
	out = []
	for v in values:
		s = _cstr(v).strip()
		if not s:
			continue
		key = s.upper()
		if key in seen_upper:
			continue
		seen_upper.add(key)
		out.append(key)
	return out


def _spr_unique_gsm_display_values(gsms: list) -> list[str]:
	seen = set()
	ordered = []
	for g in gsms:
		val = flt(g)
		if val <= 0:
			continue
		key = round(val, 2)
		if key in seen:
			continue
		seen.add(key)
		if abs(key - int(key)) < 0.001:
			disp = str(int(key))
		else:
			disp = f"{key:.2f}".rstrip("0").rstrip(".")
		ordered.append((key, disp))
	ordered.sort(key=lambda x: x[0])
	return [disp for _, disp in ordered]


def _spr_format_gsm_summary(gsms: list) -> str:
	parts = _spr_unique_gsm_display_values(gsms)
	if not parts:
		return ""
	return ", ".join(parts) + " gsm"


def _spr_collect_gsm_from_row(row) -> float:
	for key in ("gsm", "produced_gsm", "custom_fabric_gsm", "custom_lam_gsm", "custom_bopp_gsm"):
		g = flt(_spr_row_get(row, key) or 0)
		if g > 0:
			return g
	return 0.0


def compute_spr_attribute_summaries(spr_doc) -> dict:
	"""Build list-view Color / Quality / GSM text from shaft jobs and roll lines."""
	colors, qualities, gsms = [], [], []

	for row in spr_doc.get("shaft_jobs") or []:
		q = _cstr(_spr_row_get(row, "quality")).strip()
		if q:
			qualities.append(q)
		g = flt(_spr_row_get(row, "gsm") or 0)
		if g > 0:
			gsms.append(g)

	for row in spr_doc.get("items") or []:
		c = _cstr(_spr_row_get(row, "color")).strip()
		q = _cstr(_spr_row_get(row, "quality")).strip()
		g = _spr_collect_gsm_from_row(row)
		if not c or not q or g <= 0:
			ic = _cstr(_spr_row_get(row, "item_code")).strip()
			if ic:
				specs = _spr_resolve_roll_line_specs_from_item_code(
					ic, _cstr(_spr_row_get(row, "item_name"))
				)
				if not c:
					c = _cstr(specs.get("color")).strip()
				if not q:
					q = _cstr(specs.get("quality")).strip()
				if g <= 0:
					g = flt(specs.get("gsm") or 0)
		if c:
			colors.append(c)
		if q:
			qualities.append(q)
		if g > 0:
			gsms.append(g)

	return {
		"custom_color_summary": ", ".join(_spr_unique_text_values(colors)),
		"custom_quality_summary": ", ".join(_spr_unique_text_values(qualities)),
		"custom_gsm_summary": _spr_format_gsm_summary(gsms),
	}


def sync_spr_attribute_summaries_to_doc(spr_doc) -> None:
	if not spr_doc.meta.has_field("custom_color_summary"):
		return
	for fn, val in compute_spr_attribute_summaries(spr_doc).items():
		if spr_doc.meta.has_field(fn):
			spr_doc.set(fn, val)


class ShaftProductionRun(Document):
	def before_validate(self):
		self.sync_company_from_source()
		self.normalize_custom_unit()

	def validate(self):
		self.sync_company_from_source()
		self.normalize_custom_unit()
		self.sync_shaft_job_work_orders_from_plan()
		self._spr_round_item_net_weights()
		self._spr_stamp_bag_sizes_on_roll_lines()
		self._spr_stamp_sheet_sizes_on_roll_lines()
		self._spr_recalc_mix_roll_planned_qty()
		self.calculate_produced_gsm()
		self.recalculate_job_achieved_weights()
		self.recalculate_job_achieved_meters()
		self.generate_batch_numbers()
		if cint(getattr(self, "custom_is_sheet_cutting", 0)) or cint(getattr(self, "custom_is_box_bag", 0)):
			self._spr_stamp_bag_sizes_on_bundle_rows()
			sync_bundle_total_produced_sheets_for_doc(self)
			sync_bundle_total_produced_bag_pcs_for_doc(self)
			sync_bundle_total_achieved_weight_for_doc(self)
			sync_bundle_consumed_meter_header(self)
		self._spr_recalc_total_produced_weight_header()
		self._spr_recalc_bag_pcs_headers()
		self.sync_roll_attribute_summaries()

	def sync_roll_attribute_summaries(self):
		sync_spr_attribute_summaries_to_doc(self)

	def sync_company_from_source(self):
		"""Show the manufacturing company on SPR from PP first, then linked WO."""
		if not self.meta.has_field("company"):
			return
		company = ""
		pp = _cstr(self.get("production_plan"))
		if pp and frappe.db.exists("Production Plan", pp):
			company = _cstr(frappe.db.get_value("Production Plan", pp, "company"))
		if not company:
			for table_name in ("items", "shaft_jobs"):
				for row in self.get(table_name) or []:
					wo_name = _cstr(_spr_row_get(row, "work_order") or _spr_row_get(row, "wo_id"))
					if not wo_name:
						wo_name = _cstr(getattr(row, "work_orders", None) or "").split(",")[0].strip()
					if wo_name and frappe.db.exists("Work Order", wo_name):
						company = _cstr(frappe.db.get_value("Work Order", wo_name, "company"))
						if company:
							break
				if company:
					break
		if company:
			self.company = company

	def normalize_custom_unit(self):
		unit_value = _cstr(self.get("custom_unit"))
		if not unit_value:
			return
		resolved = _spr_unit_value_for_current_field(unit_value)
		if resolved:
			try:
				df = self.meta.get_field("custom_unit")
				options = [_cstr(opt) for opt in _cstr(getattr(df, "options", "")).splitlines() if _cstr(opt)]
				if df and df.fieldtype == "Select" and resolved not in options:
					df.options = (_cstr(df.options) + "\n" + resolved).strip()
			except Exception:
				pass
			self.custom_unit = resolved

	def on_update(self):
		try:
			frappe.publish_realtime("shaft_production_run_updated", {"name": self.name})
		except Exception:
			pass

	def _spr_stamp_bag_sizes_on_roll_lines(self):
		"""Fill custom_bag_size from FG item code when missing on bag SPR roll lines."""
		if not spr_doc_is_bag_spr(self):
			return
		spi_meta = frappe.get_meta("Shaft Production Run Item")
		if not spi_meta.has_field("custom_bag_size"):
			return
		for row in self.items or []:
			if _cstr(getattr(row, "custom_bag_size", None)).strip():
				continue
			ic = _cstr(getattr(row, "item_code", None)).strip()
			if not ic or not _is_bag_bundle_fg_code(ic):
				continue
			sz = _spr_bag_size_from_item_code(ic)
			if sz:
				row.custom_bag_size = sz

	def _spr_stamp_sheet_sizes_on_roll_lines(self):
		"""Fill custom_sheet_size from FG item code when missing on sheet-cutting SPR roll lines."""
		if spr_doc_is_bag_spr(self):
			return
		if not cint(getattr(self, "custom_is_sheet_cutting", 0)):
			return
		spi_meta = frappe.get_meta("Shaft Production Run Item")
		if not spi_meta.has_field("custom_sheet_size"):
			return
		for row in self.items or []:
			if _cstr(getattr(row, "custom_sheet_size", None)).strip():
				continue
			ic = _cstr(getattr(row, "item_code", None)).strip()
			if not ic:
				continue
			sz = _spr_sheet_size_from_item_code(ic)
			if not sz:
				specs = _spr_resolve_roll_line_specs_from_item_code(ic)
				sz = _cstr(specs.get("sheet_size") or "").strip()
			if sz:
				row.custom_sheet_size = sz

	def _spr_stamp_bag_sizes_on_bundle_rows(self):
		"""Fill bundle_calculation.bag_size from FG item code when missing on bag SPR."""
		if not cint(getattr(self, "custom_is_box_bag", 0)):
			return
		for row in self.bundle_calculation or []:
			if _cstr(getattr(row, "bag_size", None) or getattr(row, "sheet_cutting_size", None)).strip():
				continue
			ic = _cstr(getattr(row, "item_code", None)).strip()
			if not ic:
				continue
			sz = _bundle_row_bag_size(row, ic, for_bag_fg=True)
			if sz:
				row.bag_size = sz
				if hasattr(row, "sheet_cutting_size"):
					row.sheet_cutting_size = sz

	def _spr_recalc_bag_pcs_headers(self):
		"""Bag SPR header: planned PCS from PP, achieved PCS = sum of bundle Total Produced Bag PCS."""
		if not cint(getattr(self, "custom_is_box_bag", 0)):
			return
		meta = frappe.get_meta("Shaft Production Run")
		pp = _cstr(self.get("production_plan"))
		if meta.has_field("custom_total_planned_pcs"):
			planned = 0.0
			if pp:
				planned = _production_plan_total_planned_pcs(pp)
			if planned <= 0 and getattr(self, "bundle_calculation", None):
				planned = sum(flt(getattr(br, "total_pcs_per_bundle", 0) or 0) for br in (self.bundle_calculation or []))
			self.custom_total_planned_pcs = flt(planned, 0)
		if meta.has_field("custom_total_achieved_pcs") and getattr(self, "bundle_calculation", None):
			self.custom_total_achieved_pcs = flt(
				sum(flt(getattr(br, "total_produced_bag_pcs", 0) or 0) for br in (self.bundle_calculation or [])),
				0,
			)

	def _spr_round_item_net_weights(self):
		"""Keep roll net weight at 2 decimal kg (matches child DocType precision and manual totals)."""
		item_meta = frappe.get_meta("Shaft Production Run Item")
		if not item_meta.has_field("net_weight"):
			return
		for row in self.items or []:
			raw = getattr(row, "net_weight", None)
			if raw in (None, ""):
				continue
			cur = flt(raw)
			rnd = flt(cur, 2)
			if abs(cur - rnd) > 1e-9:
				row.net_weight = rnd

	def _spr_recalc_total_produced_weight_header(self):
		"""Header totals: bag = sum bundle bag PCS; sheet cutting = bundle achieved kg; else roll net_weight."""
		meta = frappe.get_meta("Shaft Production Run")
		if not meta.has_field("total_produced_weight"):
			return
		if cint(getattr(self, "custom_is_box_bag", 0)) and getattr(self, "bundle_calculation", None):
			total = sum(flt(getattr(br, "total_produced_bag_pcs", 0) or 0) for br in (self.bundle_calculation or []))
			self.total_produced_weight = flt(total, 0)
		elif cint(getattr(self, "custom_is_sheet_cutting", 0)) and getattr(self, "bundle_calculation", None):
			total = sum(flt(getattr(br, "total_achieved_weight", None), 2) for br in (self.bundle_calculation or []))
			self.total_produced_weight = flt(total, 2)
		else:
			total = sum(flt(getattr(r, "net_weight", None), 2) for r in (self.items or []))
			self.total_produced_weight = flt(total, 2)
		if meta.has_field("custom_total_produced_weight"):
			self.custom_total_produced_weight = flt(self.total_produced_weight, 2 if not cint(getattr(self, "custom_is_box_bag", 0)) else 0)

	def _spr_needs_job_work_order_resync(self) -> bool:
		"""True when PP-driven WO list on jobs should be recomputed (saves DB work on routine saves)."""
		if self.is_new():
			return True
		try:
			if self.has_value_changed("production_plan"):
				return True
		except Exception:
			pass
		meta = frappe.get_meta("Shaft Production Run Job")
		if not meta.has_field("work_orders"):
			return False
		for row in self.shaft_jobs or []:
			if cint(getattr(row, "is_manual", 0)):
				continue
			if not (getattr(row, "work_orders", None) or "").strip():
				return True
		return False

	def before_submit(self):
		if spr_doc_is_mix_roll(self):
			self.create_mix_roll_material_receipts()
			return
		if (
			not spr_doc_is_lamination(self)
			and not cint(getattr(self, "custom_is_box_bag", 0))
			and not cint(getattr(self, "custom_is_sheet_cutting", 0))
		):
			self._validate_roll_weight_tolerance()
		# Create/submit Manufacture entries before final submit so shortage handling can block
		# submission and still persist a draft transfer link for operators.
		self.flags._spr_allow_manufacture_posting = True
		try:
			self.create_manufacturing_stock_entries()
		finally:
			self.flags._spr_allow_manufacture_posting = False

	def _fg_rows_missing_work_order(self) -> list[dict]:
		"""Produced rows that still do not have WO mapping (causes partial submit)."""
		out = []
		for row in self.items or []:
			qty = flt(row.get("net_weight") or row.get("gross_weight") or 0)
			if qty <= 0:
				continue
			wo = _cstr(row.get("work_order") or row.get("wo_id"))
			if wo:
				continue
			out.append(
				{
					"roll_no": row.get("roll_no"),
					"item_code": _cstr(row.get("item_code")),
					"width_inch": flt(row.get("width_inch") or 0),
					"qty": qty,
				}
			)
		return out

	def _validate_no_pending_wo_width_rows(self):
		"""Block submit with a clear list when produced widths are pending WO mapping."""
		missing = self._fg_rows_missing_work_order()
		if not missing:
			return
		by_width = defaultdict(list)
		for r in missing:
			w = flt(r.get("width_inch") or 0)
			key = f'{w:.1f}"' if w > 0 else "Unknown width"
			by_width[key].append(r)
		lines = []
		for w in sorted(by_width.keys()):
			rows = by_width[w]
			rolls = [str(x.get("roll_no")) for x in rows if x.get("roll_no") not in (None, "")]
			roll_txt = f" | rolls: {', '.join(rolls[:8])}" if rolls else ""
			lines.append(_("{0}: {1} row(s){2}").format(w, len(rows), roll_txt))
		frappe.throw(
			_(
				"Pending WO mapping found for produced widths. Fix Work Order on these roll lines before submit:\n\n{0}"
			).format("\n".join(lines)),
			title=_("Pending WO widths"),
		)

	def sync_shaft_job_work_orders_from_plan(self):
		"""Fill Available Jobs.work_orders from Production Plan (comma-separated; multi-width combos get one WO per width)."""
		meta = frappe.get_meta("Shaft Production Run Job")
		if not meta.has_field("work_orders"):
			return
		pp = self.get("production_plan")
		if not pp:
			return
		if not self._spr_needs_job_work_order_resync():
			return
		for row in self.shaft_jobs or []:
			if cint(getattr(row, "is_manual", 0)):
				continue
			idx = _spr_job_row_index(self, row)
			if idx is None:
				idx = 0
			# Γ£à Extract GSM from row for (GSM, WIDTH) matching
			job_gsm = None
			if meta.has_field("gsm"):
				try:
					gsm_val = getattr(row, "gsm", None)
					if gsm_val:
						job_gsm = int(flt(gsm_val))
				except Exception:
					pass
			m = {
				"job_id": _spr_job_id(row),
				"production_plan_item": getattr(row, "production_plan_item", None),
				"combination": getattr(row, "combination", None),
			}
			wos = _resolve_wos_for_pp_job_row(
				pp,
				ppi=m.get("production_plan_item"),
				job_id=_cstr(m.get("job_id")),
				row_index=idx,
				combination=m.get("combination"),
				job_gsm=job_gsm,
			)
			if wos:
				row.work_orders = ", ".join(w["name"] for w in wos)
				if meta.has_field("party_code"):
					pc_existing = getattr(row, "party_code", None)
					if pc_existing is None or not str(pc_existing).strip():
						try:
							wo_doc = frappe.get_doc("Work Order", wos[0]["name"])
							pc = get_order_code(wo_doc)
							if pc:
								row.party_code = pc
						except Exception:
							pass

	def sync_roll_line_net_weights_from_planned(self):
		"""No longer used on save: net weight must come from operators or site scripts, not planned qty."""
		pass

	def _validate_roll_weight_tolerance(self):
		meta = frappe.get_meta("Shaft Production Run")
		if not meta.has_field("tolerance_override_approved") or not meta.has_field("tolerance_override_reason"):
			return
		violations = _spr_collect_roll_planned_tolerance_violations(self)
		if not violations:
			if cint(self.get("tolerance_override_approved")):
				self.tolerance_override_approved = 0
				self.tolerance_override_reason = ""
			return
		reason = (self.get("tolerance_override_reason") or "").strip()
		if cint(self.get("tolerance_override_approved")) and reason:
			return
		tol = _spr_net_weight_tolerance_percent()
		parts = []
		for jb, rn, pq, act, dp in violations[:8]:
			parts.append(
				_("job {0} roll {1}: planned {2} vs {3} kg ({4:.2f}%)").format(
					jb or "—", rn if rn is not None else "—", flt(pq, 3), flt(act, 3), dp
				)
			)
		detail = "; ".join(parts)
		frappe.throw(
			_(
				"Net/gross weight differs from planned qty by more than {0}%. {1} "
				"Use Submit from desk to open the approval dialog, or set Tolerance override with a reason."
			).format(tol, detail),
			title=_("Tolerance approval required"),
		)

	def recalculate_job_achieved_weights(self):
		"""Per job: sum net_weight on roll lines (kg only — never ordered/planned meters)."""
		meta = frappe.get_meta("Shaft Production Run Job")
		if not meta.has_field("custom_total_achieved_weight"):
			return
		sums: dict[str, float] = {}
		for it in self.items or []:
			jid = _cstr(getattr(it, "job", None))
			if not jid:
				continue
			sums[jid] = sums.get(jid, 0.0) + flt(it.net_weight, 2)
		for row in self.shaft_jobs or []:
			jid = _cstr(_spr_job_id(row))
			row.custom_total_achieved_weight = flt(sums.get(jid, 0.0), 2)

	def recalculate_job_achieved_meters(self):
		"""Per job + SPR header: sum produced_length_mtrs only (no meter_roll / ordered length)."""
		if cint(getattr(self, "custom_is_sheet_cutting", 0)) or cint(getattr(self, "custom_is_box_bag", 0)):
			return
		meta_job = frappe.get_meta("Shaft Production Run Job")
		meta_spr = frappe.get_meta("Shaft Production Run")
		has_job_m = meta_job.has_field("custom_total_achieved_meter")
		has_hdr_m = meta_spr.has_field("custom_total_achieved_meter")
		if not has_job_m and not has_hdr_m:
			return
		per_job: dict[str, float] = {}
		total_all = 0.0
		for it in self.items or []:
			m = _spr_produced_length_meters(it)
			total_all += m
			jid = _cstr(getattr(it, "job", None))
			if jid and has_job_m:
				per_job[jid] = per_job.get(jid, 0.0) + m
		if has_job_m:
			for row in self.shaft_jobs or []:
				jid = _cstr(_spr_job_id(row))
				row.custom_total_achieved_meter = flt(per_job.get(jid, 0.0), 2)
		if has_hdr_m:
			self.custom_total_achieved_meter = flt(total_all, 2)

	def _spr_recalc_mix_roll_planned_qty(self):
		"""Mix-roll line planned qty from gsm × width × meter/roll (not color-chart split)."""
		if not spr_doc_is_mix_roll(self):
			return
		for row in self.items or []:
			ic = _cstr(getattr(row, "item_code", None))
			gsm_val = flt(getattr(row, "gsm", None) or 0)
			if gsm_val <= 0 and ic:
				parsed_gsm, _pw = parse_item_code(ic)
				gsm_val = flt(parsed_gsm)
			w_in = flt(getattr(row, "width_inch", None) or 0)
			if w_in <= 0 and ic:
				_pg, parsed_w = parse_item_code(ic)
				w_in = flt(parsed_w)
			length_m = _spr_mix_roll_planned_length_m(row)
			pq = compute_mix_roll_planned_qty_kg(gsm_val, w_in, length_m)
			if pq > 0:
				row.planned_qty = pq

	def calculate_produced_gsm(self):
		"""Set produced_gsm on each roll line from effective weight (net, else gross), width, length (m)."""
		meta = frappe.get_meta("Shaft Production Run Item")
		if not meta.has_field("produced_gsm"):
			return
		unit_lam = _cstr(getattr(self, "custom_unit", None)).strip() == LAMINATION_UNIT
		lam = spr_doc_is_lamination(self) or unit_lam
		is_mix = spr_doc_is_mix_roll(self)
		is_bb = cint(getattr(self, "custom_is_box_bag", 0))
		for row in self.items or []:
			if lam or is_mix:
				ln = 0.0
				for key in ("produced_length_mtrs", "custom_produced_length_mtrs"):
					v = _spr_row_get(row, key)
					if v is not None and flt(v) > 0:
						ln = flt(v)
						break
				if is_mix and ln <= 0:
					row.produced_gsm = 0
					continue
			else:
				ln_m = _spr_length_meters(row)
				if ln_m is None or flt(ln_m) <= 0:
					ln = flt(getattr(row, "meter_roll", None))
				else:
					ln = flt(ln_m)
			wgt = _effective_weight_kg_for_produced_gsm(row)
			w_in = flt(getattr(row, "width_inch", None))
			if is_bb and w_in <= 0:
				ic = _cstr(getattr(row, "item_code", None))
				if ic:
					w_in = flt(_spr_resolve_roll_line_specs_from_item_code(ic).get("width_inch") or 0)
			row.produced_gsm = compute_produced_gsm(wgt, w_in, flt(ln))

	def on_submit(self):
		self.sync_batch_custom_fields()
		self.update_work_order_statuses()

	def on_cancel(self):
		self.cancel_manufacturing_stock_entries()

	def on_trash(self):
		"""Remove stale row links so deleted SPR is not shown as Continue Entry on Production Table."""
		try:
			if frappe.db.exists("DocType", "Planning Table") and frappe.db.has_column("Planning Table", "spr_name"):
				# spr_name is stored as CSV of SPR ids; remove this id from any row that references it.
				rows = frappe.get_all(
					"Planning Table",
					filters={"spr_name": ["like", f"%{self.name}%"]},
					fields=["name", "spr_name"],
					limit_page_length=0,
				) or []
				for r in rows:
					raw = str(r.get("spr_name") or "").strip()
					if not raw:
						continue
					parts = [p.strip() for p in raw.replace(";", ",").split(",") if p and p.strip()]
					filtered = [p for p in parts if p != self.name]
					new_val = ", ".join(filtered)
					if new_val != raw:
						frappe.db.set_value("Planning Table", r["name"], "spr_name", new_val, update_modified=False)
				# Back-compat: rows that stored a single id only.
				frappe.db.sql(
					"""
					UPDATE `tabPlanning Table`
					SET spr_name = ''
					WHERE IFNULL(spr_name, '') = %s
					""",
					(self.name,),
				)
				frappe.db.commit()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SPR on_trash cleanup: Planning Table spr_name")

		# Also remove this SPR from Production Plan link list to avoid stale PP-level references elsewhere.
		try:
			if not frappe.db.has_column("Production Plan", "custom_shaft_production_run_id"):
				return
			rows = frappe.db.sql(
				"""
				SELECT name, custom_shaft_production_run_id
				FROM `tabProduction Plan`
				WHERE IFNULL(custom_shaft_production_run_id, '') != ''
				""",
				as_dict=True,
			)
			for r in rows or []:
				raw = str(r.get("custom_shaft_production_run_id") or "")
				parts = [p.strip() for p in raw.split(",") if p and p.strip()]
				filtered = [p for p in parts if p != self.name]
				if filtered != parts:
					frappe.db.set_value("Production Plan", r["name"], "custom_shaft_production_run_id", ", ".join(filtered))
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SPR on_trash cleanup: Production Plan links")

	def _batch_prefix_parts(self):
		"""Return (company_identifier, unit_number_2digit) for the batch format — one unique pair per workstation."""
		u_raw = (self.get("custom_unit") or "").strip()
		if not u_raw:
			frappe.throw(
				_("Set Unit on this Shaft Production Run before roll batch numbers can be assigned."),
				title=_("Unit required"),
			)
		parts = spr_batch_prefix_for_unit(u_raw)
		if not parts:
			frappe.throw(
				_("No batch number format is configured for unit «{0}». Choose a supported workstation or contact admin.").format(
					u_raw
				),
				title=_("Unsupported unit"),
			)
		return parts

	def _unit_digit(self) -> str:
		"""Legacy single-character unit code — kept for backward compatibility."""
		_, unit_num = self._batch_prefix_parts()
		return str(int(unit_num))  # '01' → '1', '10' → '10'

	def generate_batch_numbers(self):
		"""Assign batch_no on each roll line when draft is saved.

		New format: ``{ID}-{UU}{MM}{YY}{S}/{N}``
		  ID = company identifier (JS / TS / JV / PY)
		  UU = 2-digit unit number
		  MM = month, YY = year, S = shift series, N = roll number
		Example: JS-01052601/1
		``tabBatch`` rows are created/updated on **submit** via ``sync_batch_custom_fields``, not on every save.
		"""
		if not self.run_date or not self.get("custom_unit") or not self.shift:
			return
		rows = [r for r in (self.items or []) if r.item_code]
		if not rows:
			return
		# Heavy series queries only when at least one line still needs batch_no (routine saves with full grid skip this).
		if not any(not getattr(r, "batch_no", None) for r in rows):
			return
		parts = spr_batch_prefix_for_unit(self.get("custom_unit"))
		if not parts:
			# Unsupported / unassigned unit — skip roll batch assignment on save (submit may still require Shift + unit).
			return
		rd = getdate(self.run_date)
		comp_id, unit_num = parts
		root_5 = f"{comp_id}-{unit_num}{rd.month:02d}{rd.year % 100:02d}"
		series_prefix = self._resolve_series_prefix(root_5)
		next_roll = self._next_roll_starting(series_prefix)
		item_meta = frappe.get_meta("Shaft Production Run Item")
		for row in rows:
			if row.batch_no:
				continue
			row.batch_no = f"{series_prefix}/{next_roll}"
			if item_meta.has_field("roll_no"):
				rf = item_meta.get_field("roll_no")
				row.roll_no = int(next_roll) if rf and rf.fieldtype == "Int" else str(next_roll)
			if item_meta.has_field("custom_shift"):
				row.custom_shift = batch_shift_value(self.shift)
			next_roll += 1

	def _spr_series_prefix_from_batches(self, root_5: str, batch_nos) -> str | None:
		"""First batch prefix on this root (part before ``/``), if any."""
		for bn in batch_nos or []:
			bn = _cstr(bn)
			if not bn or "/" not in bn:
				continue
			pref = bn.split("/", 1)[0].strip()
			if pref.startswith(root_5) and len(pref) >= len(root_5):
				return pref
		return None

	def _resolve_series_prefix(self, root_5: str) -> str:
		"""Reuse series for same run_date + shift + unit when batches already exist.

		Within one SPR + shift: keep the same prefix (e.g. JS-01062674) and only
		increment the roll suffix (/1, /2, …).  A new shift digit (…74 → …75) is
		allocated only when no batch exists yet for this shift on this date/unit.
		"""
		# 1) Rows already on this document (in-memory during save / preview)
		on_doc = self._spr_series_prefix_from_batches(
			root_5, [getattr(r, "batch_no", None) for r in (self.items or [])]
		)
		if on_doc:
			return on_doc

		# 2) Rows saved on this SPR in DB (was excluded before — caused new S per row)
		if self.name:
			own_rows = frappe.db.sql(
				"""
				SELECT spi.batch_no
				FROM `tabShaft Production Run Item` spi
				WHERE spi.parent = %(cur)s
				  AND IFNULL(spi.batch_no, '') != ''
				  AND spi.batch_no LIKE CONCAT(%(root)s, '%%')
				ORDER BY spi.idx ASC
				LIMIT 50
				""",
				{"cur": self.name, "root": root_5},
			)
			on_doc = self._spr_series_prefix_from_batches(root_5, [r[0] for r in own_rows or []])
			if on_doc:
				return on_doc

		# 3) Other SPRs on same run_date + shift + unit
		existing = frappe.db.sql(
			"""
			SELECT spi.batch_no
			FROM `tabShaft Production Run Item` spi
			INNER JOIN `tabShaft Production Run` spr ON spr.name = spi.parent
			WHERE spr.run_date = %(rd)s
			  AND spr.shift = %(sh)s
			  AND spr.custom_unit = %(un)s
			  AND spr.name != %(cur)s
			  AND IFNULL(spi.batch_no, '') != ''
			  AND spi.batch_no LIKE CONCAT(%(root)s, '%%')
			ORDER BY spr.modified DESC
			LIMIT 20
			""",
			{
				"rd": self.run_date,
				"sh": self.shift,
				"un": self.custom_unit,
				"cur": self.name or "",
				"root": root_5,
			},
		)
		for (bn,) in existing or []:
			if bn and "/" in bn:
				pref = bn.split("/")[0].strip()
				if pref.startswith(root_5) and len(pref) >= len(root_5):
					return pref

		next_s = self._next_shift_suffix_num(root_5)
		return f"{root_5}{next_s}"

	def _next_shift_suffix_num(self, root_5: str) -> int:
		"""Pick next S digit(s) after scanning Batch + SPR items for this month/unit/year root."""
		max_s = 0
		rows = frappe.db.sql(
			"""
			SELECT batch_id FROM `tabBatch`
			WHERE batch_id LIKE CONCAT(%(root)s, '%%')
			""",
			{"root": root_5},
		)
		for (bid,) in rows or []:
			max_s = max(max_s, self._suffix_after_root(bid, root_5))
		rows2 = frappe.db.sql(
			"""
			SELECT spi.batch_no FROM `tabShaft Production Run Item` spi
			WHERE IFNULL(spi.batch_no,'') != ''
			  AND spi.batch_no LIKE CONCAT(%(root)s, '%%')
			""",
			{"root": root_5},
		)
		for (bn,) in rows2 or []:
			max_s = max(max_s, self._suffix_after_root(bn, root_5))
		return max_s + 1 if max_s >= 0 else 1

	def _suffix_after_root(self, batch_id: str, root_5: str) -> int:
		if not batch_id or "/" not in batch_id:
			return 0
		pref = batch_id.split("/", 1)[0].strip()
		if not pref.startswith(root_5):
			return 0
		s_part = pref[len(root_5) :]
		try:
			return int(s_part) if s_part else 0
		except ValueError:
			return 0

	def _next_roll_starting(self, series_prefix: str) -> int:
		mx = 0
		rows = frappe.db.sql(
			"""
			SELECT batch_id FROM `tabBatch`
			WHERE batch_id LIKE %(pat)s
			""",
			{"pat": f"{series_prefix}/%"},
		)
		for (bid,) in rows or []:
			mx = max(mx, self._roll_no_from_batch(bid, series_prefix))
		rows2 = frappe.db.sql(
			"""
			SELECT batch_no FROM `tabShaft Production Run Item`
			WHERE IFNULL(batch_no,'') != '' AND batch_no LIKE %(pat)s
			""",
			{"pat": f"{series_prefix}/%"},
		)
		for (bn,) in rows2 or []:
			mx = max(mx, self._roll_no_from_batch(bn, series_prefix))
		return mx + 1

	def _roll_no_from_batch(self, batch_id: str, series_prefix: str) -> int:
		if not batch_id or "/" not in batch_id:
			return 0
		pref, roll = batch_id.split("/", 1)
		if pref.strip() != series_prefix:
			return 0
		try:
			return int(roll.strip())
		except ValueError:
			return 0

	def sync_batch_custom_fields(self):
		batch_meta = frappe.get_meta("Batch")
		is_bag = spr_doc_is_bag_spr(self)
		company = _spr_company_from_doc(self)
		for row in self.items or []:
			if not row.batch_no:
				continue
			bn = _cstr(row.batch_no)
			ic = _cstr(row.get("item_code")).strip()
			batch_name = bn
			if not frappe.db.exists("Batch", batch_name) and ic:
				batch_name = (
					frappe.db.get_value(
						"Batch",
						{"item": ic, "batch_id": bn},
						"name",
					)
					or batch_name
				)
			if not batch_name or not frappe.db.exists("Batch", batch_name):
				if ic:
					try:
						batch_name = self._get_batch_link_name_for_stock_entry(bn, ic, company, row)
					except Exception:
						frappe.log_error(frappe.get_traceback(), f"SPR Batch auto-create:{self.name}")
						continue
				if not batch_name or not frappe.db.exists("Batch", batch_name):
					continue
			data = dict(_batch_fields_from_spr_row(batch_meta, row, is_bag_spr=is_bag))
			if batch_meta.has_field("custom_gross_weight") and row.get("gross_weight") is not None:
				data["custom_gross_weight"] = flt(row.gross_weight)
			if batch_meta.has_field("custom_cbm") and row.get("custom_cbm") is not None:
				data["custom_cbm"] = flt(row.custom_cbm)
			if batch_meta.has_field("custom_diameter") and row.get("custom_diameter") is not None:
				data["custom_diameter"] = flt(row.custom_diameter)
			if batch_meta.has_field("custom_shift") and row.get("custom_shift"):
				data["custom_shift"] = row.custom_shift
			if batch_meta.has_field("custom_party_code_text") and row.get("custom_party_code_text"):
				data["custom_party_code_text"] = row.custom_party_code_text
			if not data:
				continue
			try:
				frappe.db.set_value("Batch", batch_name, data)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "SPR Batch sync skipped")

	def _row_fg_qty(self, row) -> float:
		if spr_doc_is_bag_spr(self):
			pcs = flt(_spr_row_get(row, "custom_achieved_bag_pcs"))
			if pcs > 0:
				return pcs
		qty = flt(_spr_row_get(row, "net_weight"))
		if qty <= 0:
			qty = flt(_spr_row_get(row, "gross_weight"))
		if qty <= 0 and cint(getattr(self, "custom_is_box_bag", 0)):
			qty = flt(_spr_row_get(row, "custom_achieved_bag_pcs"))
		if qty <= 0 and cint(getattr(self, "custom_is_sheet_cutting", 0)):
			qty = flt(_spr_row_get(row, "custom_total_produced_sheets"))
		return qty

	def _spr_bag_fg_posting_qty_for_wo(self, wo_doc, spr_rows: list | None = None) -> float:
		"""Is Bag: FG qty in PCS from bundle/header — never meters or roll weight."""
		if not spr_doc_is_bag_spr(self) or not wo_doc:
			return 0.0
		wo_id = _cstr(getattr(wo_doc, "name", None))
		total = 0.0
		for br in self.bundle_calculation or []:
			if _cstr(getattr(br, "work_order", None)) == wo_id:
				total += flt(getattr(br, "total_produced_bag_pcs", 0) or 0)
		if total > 1e-9:
			return flt(total, 0)
		meta = frappe.get_meta("Shaft Production Run")
		if meta.has_field("custom_total_achieved_pcs"):
			hdr = flt(getattr(self, "custom_total_achieved_pcs", 0) or 0)
			if hdr > 1e-9:
				return flt(hdr, 0)
		rows = spr_rows if spr_rows is not None else [
			r for r in (self.items or [])
			if _cstr(r.get("work_order") or r.get("wo_id")) == wo_id
		]
		return flt(sum(flt(_spr_row_get(r, "custom_achieved_bag_pcs")) for r in rows), 0)

	def _spr_validate_bag_fg_qty_for_wo(self, wo_doc, fg_pcs: float) -> None:
		"""Is Bag: ensure posting PCS does not exceed WO remaining qty."""
		if not spr_doc_is_bag_spr(self) or fg_pcs <= 0:
			return
		remaining, allowed, already, _over = self._wo_allowed_remaining_qty(wo_doc)
		if fg_pcs > remaining + 1e-9:
			frappe.throw(
				_(
					"Bag SPR produced {0} PCS for WO {1}, but WO allows only {2} PCS remaining "
					"(WO qty {3}, already produced {4}). Adjust Achieved Bag PCS before submit."
				).format(
					flt(fg_pcs, 0),
					wo_doc.name,
					flt(remaining, 0),
					flt(getattr(wo_doc, "qty", 0), 0),
					flt(already, 0),
				),
				title=_("Bag PCS exceeds WO qty"),
			)

	def _set_stock_entry_spr_link(self, se):
		"""Link Manufacture / transfer entries back to this SPR for traceability and recovery tools."""
		meta = frappe.get_meta("Stock Entry")
		if meta.has_field("shaft_production_run"):
			se.shaft_production_run = self.name
		if frappe.db.has_column("Stock Entry", "custom_spr_reference") and meta.has_field("custom_spr_reference"):
			se.set("custom_spr_reference", self.name)

	def _persist_stock_entry_spr_reference_db(self, se_name: str | None):
		"""If DB has custom_spr_reference column, persist link even when not on in-memory doc meta."""
		if not se_name or not frappe.db.has_column("Stock Entry", "custom_spr_reference"):
			return
		try:
			frappe.db.set_value("Stock Entry", se_name, "custom_spr_reference", self.name, update_modified=False)
		except Exception:
			pass

	def _apply_order_code_to_submitted_stock_entry(self, se_name: str):
		"""Copy SPR header order code onto Stock Entry when the site has a matching custom field."""
		if not se_name:
			return
		oc = self._resolve_spr_order_code()
		if not oc:
			return
		meta = frappe.get_meta("Stock Entry")
		for fn in ("order_code", "custom_order_code", "custom_party_code", "party_code"):
			if meta.has_field(fn):
				try:
					frappe.db.set_value("Stock Entry", se_name, fn, oc, update_modified=False)
				except Exception:
					pass

	def _resolve_spr_order_code(self) -> str:
		for key in ("custom_order_code", "order_code", "custom_party_code", "party_code"):
			s = _cstr(self.get(key))
			if s:
				return s
		for row in self.items or []:
			for key in ("custom_order_code", "order_code", "custom_party_code_text", "party_code"):
				s = _cstr(row.get(key))
				if s:
					return s
		return ""

	def _resolve_spr_unit_value(self, wo_doc=None) -> str:
		"""Pick unit for Stock Entry: SPR header first, then WO."""
		for v in (
			self.get("custom_unit"),
			self.get("unit"),
			getattr(wo_doc, "custom_unit", None) if wo_doc else None,
			getattr(wo_doc, "unit", None) if wo_doc else None,
		):
			s = _cstr(v)
			if s:
				return s
		return ""

	def _set_stock_entry_unit(self, se, wo_doc=None):
		meta = frappe.get_meta("Stock Entry")
		unit_value = self._resolve_spr_unit_value(wo_doc)
		if not unit_value:
			return
		for fn in ("unit", "custom_unit", "workstation", "custom_workstation"):
			if meta.has_field(fn):
				resolved = _unit_value_for_doctype_field(unit_value, "Stock Entry", fn, meta=meta)
				if resolved:
					se.set(fn, resolved)

	def _apply_unit_to_submitted_stock_entry(self, se_name: str, wo_doc=None):
		if not se_name:
			return
		unit_value = self._resolve_spr_unit_value(wo_doc)
		if not unit_value:
			return
		meta = frappe.get_meta("Stock Entry")
		for fn in ("unit", "custom_unit", "workstation", "custom_workstation"):
			if meta.has_field(fn):
				resolved = _unit_value_for_doctype_field(unit_value, "Stock Entry", fn, meta=meta)
				if not resolved:
					continue
				try:
					frappe.db.set_value("Stock Entry", se_name, fn, resolved, update_modified=False)
				except Exception:
					pass

	def _refresh_batch_qty_for_codes(self, batch_codes: list[str]):
		"""Force-refresh Batch.batch_qty for given batch ids from stock ledger."""
		for bn in {_cstr(x).strip() for x in (batch_codes or []) if _cstr(x).strip()}:
			if not frappe.db.exists("Batch", bn):
				continue
			try:
				qty = flt(
					frappe.db.sql(
						"""
						SELECT IFNULL(SUM(actual_qty), 0)
						FROM `tabStock Ledger Entry`
						WHERE IFNULL(is_cancelled, 0) = 0
						  AND IFNULL(batch_no, '') = %s
						""",
						(bn,),
					)[0][0]
					or 0
				)
				if abs(qty) <= 1e-9 and frappe.db.has_column("Stock Ledger Entry", "serial_and_batch_bundle"):
					try:
						sb_bundle_dt = "Serial and Batch Bundle"
						sb_entry_dt = "Serial and Batch Entry"
						if frappe.db.exists("DocType", sb_bundle_dt) and frappe.db.exists("DocType", sb_entry_dt):
							sb_entry_meta = frappe.get_meta(sb_entry_dt)
							batch_field = next(
								(
									fn
									for fn in ("batch_no", "batch", "batch_id")
									if sb_entry_meta.has_field(fn)
								),
								"",
							)
							qty_field = next(
								(
									fn
									for fn in ("qty", "quantity")
									if sb_entry_meta.has_field(fn)
								),
								"",
							)
							if batch_field and qty_field:
								qty = flt(
									frappe.db.sql(
										f"""
										SELECT IFNULL(SUM(
											CASE
												WHEN IFNULL(sle.actual_qty, 0) < 0 THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
												ELSE ABS(IFNULL(sbe.`{qty_field}`, 0))
											END
										), 0)
										FROM `tabStock Ledger Entry` sle
										INNER JOIN `tabSerial and Batch Entry` sbe
											ON sbe.parent = sle.serial_and_batch_bundle
										WHERE IFNULL(sle.is_cancelled, 0) = 0
										  AND IFNULL(sle.serial_and_batch_bundle, '') != ''
										  AND IFNULL(sbe.`{batch_field}`, '') = %s
										""",
										(bn,),
									)[0][0]
									or 0
								)
					except Exception:
						pass
				if frappe.db.has_column("Batch", "batch_qty"):
					frappe.db.set_value("Batch", bn, "batch_qty", qty, update_modified=False)
				if frappe.db.has_column("Batch", "status"):
					status = "Empty" if abs(qty) <= 1e-9 else "Active"
					frappe.db.set_value("Batch", bn, "status", status, update_modified=False)
			except Exception:
				pass

	def _get_existing_submitted_manufacture_entries_for_spr(self) -> list[str]:
		"""Submitted Manufacture entries already linked to this SPR."""
		names = [x.strip() for x in _cstr(self.get("manufacturing_entries")).split(",") if x and x.strip()]
		meta_se = frappe.get_meta("Stock Entry")
		if not names and meta_se.has_field("shaft_production_run"):
			names = frappe.db.sql_list(
				"""
				SELECT name
				FROM `tabStock Entry`
				WHERE IFNULL(shaft_production_run, '') = %s
				  AND IFNULL(purpose, '') = 'Manufacture'
				  AND docstatus = 1
				""",
				(self.name,),
			)
		if not names and frappe.db.has_column("Stock Entry", "custom_spr_reference"):
			names = frappe.db.sql_list(
				"""
				SELECT name
				FROM `tabStock Entry`
				WHERE IFNULL(custom_spr_reference, '') = %s
				  AND IFNULL(purpose, '') = 'Manufacture'
				  AND docstatus = 1
				""",
				(self.name,),
			)
		return sorted({_cstr(x).strip() for x in (names or []) if _cstr(x).strip()})

	def _filter_shortages_by_wo_transfer_remaining(
		self, wo_doc, shortages: list[tuple[str, str, float, float, float]]
	) -> list[tuple[str, str, float, float, float]]:
		"""Drop/cap RM shortages when Work Order required_items already show full transfer."""
		if not wo_doc or not shortages:
			return []
		wo_doc = self._reload_work_order_doc(wo_doc)
		out = []
		for item_code, wh, req, avl, short_qty in shortages:
			ic = _cstr(item_code).strip()
			if not ic:
				continue
			still = _spr_wo_rm_transfer_remaining(wo_doc, ic)
			tol = _spr_rm_wip_shortage_tolerance(flt(short_qty))
			if still <= tol:
				continue
			capped = min(_spr_round_rm_stock_qty(flt(short_qty)), _spr_round_rm_stock_qty(still))
			if capped > tol:
				out.append((ic, wh, flt(req), flt(avl), capped))
		return out

	def _filter_shortage_events_by_wo_transfer(self, shortage_events) -> list:
		"""Remove shortage lines that WO already transferred — prevents duplicate MTFM per item."""
		filtered = []
		for event in shortage_events or []:
			if event.get("wip_topup"):
				filtered.append(event)
				continue
			wo_doc = self._reload_work_order_doc(event.get("wo_doc"))
			shortages = self._filter_shortages_by_wo_transfer_remaining(
				wo_doc, event.get("shortages") or []
			)
			if not shortages:
				continue
			filtered.append(
				{
					"wo_id": _cstr(event.get("wo_id")),
					"wo_doc": wo_doc,
					"chunk_total_qty": flt(event.get("chunk_total_qty")),
					"shortages": shortages,
				}
			)
		return filtered

	def _spr_cap_manufacture_rm_lines_to_wip_available(self, se, wo_doc) -> bool:
		"""Nudge consume lines only for sub-tolerance WIP/bin float drift — never cap meaningful shortages."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None))
		if not se or not wip_wh or not _spr_wo_rm_fully_transferred(wo_doc):
			return False
		changed = False
		for d in se.items or []:
			if not d.item_code or d.get("t_warehouse"):
				continue
			if _cstr(d.get("s_warehouse")) != wip_wh:
				continue
			ic = _cstr(d.item_code).strip()
			req = flt(d.get("transfer_qty") or d.get("qty"))
			if req <= 0:
				continue
			tol = _spr_rm_wip_shortage_tolerance(req)
			batch_no = _cstr(d.get("batch_no")).strip()
			if batch_no:
				avl = _spr_batch_available_qty(ic, wip_wh, batch_no)
			else:
				avl = _spr_rm_available_qty(ic, wip_wh)
			avl = _spr_floor_rm_stock_qty(avl)
			if req <= avl:
				continue
			gap = req - avl
			if gap > tol:
				# Meaningful WIP shortage — preflight auto-transfer must top up RM store -> WIP.
				continue
			cap = _spr_floor_rm_stock_qty(avl)
			if cap <= 0:
				continue
			cf = flt(d.get("conversion_factor") or 1) or 1
			d.transfer_qty = cap
			d.qty = flt(cap / cf, 6)
			changed = True
		return changed

	def _spr_wip_topup_max_kg(self) -> float:
		"""Optional per-item cap for WIP top-up (0 = unlimited)."""
		try:
			val = frappe.conf.get("spr_wip_topup_max_kg")
			if val is None:
				return 0.0
			return max(0.0, flt(val))
		except (TypeError, ValueError):
			return 0.0

	def _spr_wip_topup_short_by_item_from_exception(self, wo_doc, exc) -> dict:
		"""Parse manufacture NegativeStockError into RM->WIP top-up qty when WO transfer is already complete."""
		parsed = self._rm_shortages_from_exception(exc)
		if not parsed:
			return {}
		wo_doc = self._reload_work_order_doc(wo_doc)
		max_topup = self._spr_wip_topup_max_kg()
		out: dict[str, float] = {}
		for ic, _wh, _req, _avl, sq in parsed:
			code = _cstr(ic).strip()
			qty = _spr_wip_topup_bump_qty(sq)
			if not code or qty <= 0:
				continue
			tol = _spr_rm_wip_shortage_tolerance(qty)
			if _spr_wo_rm_transfer_remaining(wo_doc, code) > tol:
				# Normal RM->WIP shortage path should handle items still to transfer on the WO.
				continue
			if max_topup > 0 and qty > max_topup:
				qty = max_topup
			out[code] = out.get(code, 0.0) + qty
		return out

	def _spr_wip_topup_from_manufacture_se(self, se, wo_doc) -> dict:
		"""Derive WIP top-up qty from failed Manufacture STE when WO RM transfer is already complete."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		if not se or not wo_doc:
			return {}
		out: dict[str, float] = {}
		for d in se.items or []:
			if not d.item_code or d.get("t_warehouse"):
				continue
			ic = _cstr(d.item_code).strip()
			required = _spr_round_rm_stock_qty(d.get("qty") or d.get("transfer_qty"))
			wh = _cstr(d.get("s_warehouse"))
			if not ic or required <= 0 or not wh:
				continue
			tol = _spr_rm_wip_shortage_tolerance(required)
			if _spr_wo_rm_transfer_remaining(wo_doc, ic) > tol:
				continue
			available = _spr_round_rm_stock_qty(
				frappe.db.get_value("Bin", {"item_code": ic, "warehouse": wh}, "actual_qty") or 0
			)
			gap = _spr_wip_topup_bump_qty(required - available)
			if gap > 0:
				out[ic] = out.get(ic, 0.0) + gap
		return out

	def _spr_try_wip_topup_transfer_and_retry_manufacture(
		self, wo_doc, exc, allow_wip_topup_retry: bool, mfg_submit_savepoint: str, mfg_se=None
	) -> None:
		"""Create one RM->WIP MTFM for parsed WIP shortage, auto-submit, then retry Manufacture."""
		if not allow_wip_topup_retry:
			return
		topup = self._spr_wip_topup_short_by_item_from_exception(wo_doc, exc)
		if not topup and mfg_se:
			topup = self._spr_wip_topup_from_manufacture_se(mfg_se, wo_doc)
		if not topup:
			return
		transfer = self._create_wip_topup_mtfm_for_manufacture(wo_doc, topup)
		if not transfer:
			return
		if cint(frappe.db.get_value("Stock Entry", transfer, "docstatus")) == 1:
			# Force stock ledger sync: recompute bin actual_qty for transferred items
			self._force_sync_stock_bins_after_transfer(transfer, wo_doc)
			frappe.db.savepoint(mfg_submit_savepoint)
			raise _SprWipTopupRetry()

	def _force_sync_stock_bins_after_transfer(self, se_name: str, wo_doc) -> None:
		"""Force immediate stock bin synchronization after MTFM submit to avoid stale reads."""
		try:
			wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None))
			if not wip_wh:
				return
			# Get items from the submitted Stock Entry
			items = frappe.get_all(
				"Stock Entry Detail",
				filters={"parent": se_name, "t_warehouse": wip_wh},
				fields=["item_code"],
			)
			if not items:
				return
			# Force recompute bin actual_qty from stock ledger for each item
			from erpnext.stock.utils import update_bin_qty
			for row in items:
				ic = _cstr(row.get("item_code"))
				if not ic:
					continue
				# update_bin_qty recalculates actual_qty from Stock Ledger Entry
				update_bin_qty(ic, wip_wh)
			# Clear any query cache
			frappe.clear_cache(doctype="Bin")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SPR force bin sync")

	def _force_sync_bins_for_stock_entry(self, se_name: str) -> None:
		"""Force immediate bin sync for all items in a Stock Entry (source and target warehouses)."""
		try:
			from erpnext.stock.utils import update_bin_qty
			items = frappe.get_all(
				"Stock Entry Detail",
				filters={"parent": se_name},
				fields=["item_code", "s_warehouse", "t_warehouse"],
			)
			seen = set()
			for row in items:
				ic = _cstr(row.get("item_code"))
				if not ic:
					continue
				for wh in (row.get("s_warehouse"), row.get("t_warehouse")):
					wh = _cstr(wh)
					if wh and (ic, wh) not in seen:
						seen.add((ic, wh))
						update_bin_qty(ic, wh)
			frappe.clear_cache(doctype="Bin")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SPR force bin sync (SE)")

	def _create_wip_topup_mtfm_for_manufacture(self, wo_doc, short_by_item: dict) -> str:
		"""One RM->WIP transfer when Manufacture cannot consume WIP (batch/ledger gap after WO transfer)."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		if not wo_doc or not short_by_item:
			return ""
		wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None)) or ""
		if not wip_wh:
			return ""
		short_by_item = {
			_cstr(k).strip(): _spr_wip_topup_bump_qty(v)
			for k, v in (short_by_item or {}).items()
			if _cstr(k).strip() and flt(v) > 0
		}
		if not short_by_item:
			return ""
		se, _wip_b = self._new_mtfm_stock_entry_shell(
			wo_doc,
			0.001,
			today(),
			nowtime(),
			short_by_item=short_by_item,
		)
		se.from_bom = 0
		if not self._append_mtfm_shortage_lines(
			se, wo_doc, short_by_item, wip_wh, ignore_wo_transfer=True
		):
			return ""
		return self._spr_insert_shortage_transfer_draft(se)

	def _spr_apply_stock_entry_item_accounts(self, se) -> None:
		_spr_apply_stock_entry_item_accounts(se)

	def _throw_wip_stock_wo_transfer_mismatch(self, wo_doc, original_exc=None):
		"""WO shows RM transferred but WIP bin cannot satisfy Manufacture — do not create more MTFM."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		wo_id = _cstr(getattr(wo_doc, "name", None))
		wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None))
		prec = _spr_rm_stock_qty_precision()
		lines = []
		for req in getattr(wo_doc, "required_items", None) or []:
			ic = _cstr(getattr(req, "item_code", None)).strip()
			if not ic:
				continue
			transferred = flt(getattr(req, "transferred_qty", 0))
			required = flt(getattr(req, "required_qty", 0))
			wip_qty = flt(
				frappe.db.get_value("Bin", {"item_code": ic, "warehouse": wip_wh}, "actual_qty") or 0
			)
			lines.append(
				_("{0}: WO transferred {1} / required {2} Kg; WIP bin {3} Kg").format(
					ic, flt(transferred, prec), flt(required, prec), flt(wip_qty, prec)
				)
			)
		err_tail = ""
		if original_exc:
			err_tail = _("\n\nERPNext error:\n{0}").format(_cstr(original_exc))
		frappe.throw(
			_(
				"Work Order {0} already shows raw materials transferred, but Work In Progress "
				"warehouse does not have enough stock to complete Manufacture.\n\n"
				"{1}\n\n"
				"An automatic RM → WIP transfer could not be created or submitted. "
				"Check RM store stock for the shortage item(s), cancel duplicate MTFM entries "
				"if any, then submit SPR again."
			).format(wo_id, "\n".join(lines[:15]), err_tail),
			title=_("WIP stock mismatch"),
		)

	def _rm_shortages_for_se(self, se, wo_doc=None) -> list[tuple[str, str, float, float, float]]:
		"""Return RM shortages as (item_code, s_warehouse, required, available, shortage)."""
		out = []
		for d in se.items or []:
			if not d.item_code or d.get("t_warehouse"):
				continue
			required = _spr_round_rm_stock_qty(d.get("transfer_qty") or d.get("qty"))
			if required <= 0:
				continue
			wh = _cstr(d.get("s_warehouse"))
			available = _spr_round_rm_stock_qty(
				frappe.db.get_value("Bin", {"item_code": d.item_code, "warehouse": wh}, "actual_qty") or 0
			)
			tol = _spr_rm_wip_shortage_tolerance(required)
			shortage = required - available
			if shortage <= tol:
				continue
			if wo_doc and _spr_wo_rm_transfer_remaining(wo_doc, d.item_code) <= tol:
				# MTFM already submitted — WIP Bin may differ from BOM preview by fractions of a gram.
				continue
			out.append((_cstr(d.item_code), wh, required, available, shortage))
		if wo_doc:
			return self._filter_shortages_by_wo_transfer_remaining(wo_doc, out)
		return out

	def _spr_wip_topup_shortages_for_se(self, se, wo_doc) -> list[tuple[str, str, float, float, float]]:
		"""WIP bin shortfall when WO already shows RM transferred — needs company RM -> WIP top-up."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None))
		if not se or not wip_wh:
			return []
		company = _cstr(getattr(wo_doc, "company", None))
		out = []
		for d in se.items or []:
			if not d.item_code or d.get("t_warehouse"):
				continue
			if _cstr(d.get("s_warehouse")) != wip_wh:
				continue
			ic = _cstr(d.item_code).strip()
			required = _spr_round_rm_stock_qty(d.get("transfer_qty") or d.get("qty"))
			if required <= 0:
				continue
			tol = _spr_rm_wip_shortage_tolerance(required)
			if _spr_wo_rm_transfer_remaining(wo_doc, ic) > tol:
				continue
			available = _spr_round_rm_stock_qty(_spr_rm_available_qty(ic, wip_wh))
			shortage = required - available
			if shortage <= tol:
				continue
			bump = _spr_wip_topup_bump_qty(shortage)
			item_src = self._resolve_rm_source_warehouse_for_transfer(wo_doc, ic, wip_wh)
			rm_wh, _rm_avl = _spr_find_rm_warehouse_with_stock(company, ic, wip_wh, item_src, bump)
			if not rm_wh:
				rm_wh = item_src or _spr_company_rm_warehouse(company, wip_wh) or _("RM warehouse")
			out.append((ic, rm_wh, required, available, bump))
		return out

	def _best_available_batch_for_rm(self, item_code: str, warehouse: str, required_qty: float) -> str:
		"""Pick a batch with available qty in source warehouse for RM consumption.

		Covers both classic SLE.batch_no and v15 Serial-and-Batch-Bundle based entries.
		"""
		if not item_code or not warehouse:
			return ""
		rows = frappe.db.sql(
			"""
			SELECT batch_no, SUM(actual_qty) as qty
			FROM `tabStock Ledger Entry`
			WHERE IFNULL(is_cancelled, 0) = 0
			  AND IFNULL(item_code, '') = %s
			  AND IFNULL(warehouse, '') = %s
			  AND IFNULL(batch_no, '') != ''
			GROUP BY batch_no
			HAVING SUM(actual_qty) > 0
			ORDER BY SUM(actual_qty) DESC, MAX(posting_date) DESC, MAX(posting_time) DESC
			""",
			(item_code, warehouse),
			as_dict=True,
		)
		# v15 path: batch may live in Serial and Batch Entry (bundle), with empty SLE.batch_no.
		if (not rows) and frappe.db.has_column("Stock Ledger Entry", "serial_and_batch_bundle"):
			try:
				sb_entry_dt = "Serial and Batch Entry"
				if frappe.db.exists("DocType", sb_entry_dt):
					sb_entry_meta = frappe.get_meta(sb_entry_dt)
					batch_field = next(
						(fn for fn in ("batch_no", "batch", "batch_id") if sb_entry_meta.has_field(fn)),
						"",
					)
					qty_field = next(
						(fn for fn in ("qty", "quantity") if sb_entry_meta.has_field(fn)),
						"",
					)
					if batch_field and qty_field:
						rows = frappe.db.sql(
							f"""
							SELECT
								sbe.`{batch_field}` AS batch_no,
								SUM(
									CASE
										WHEN IFNULL(sle.actual_qty, 0) < 0 THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
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
									WHEN IFNULL(sle.actual_qty, 0) < 0 THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
									ELSE ABS(IFNULL(sbe.`{qty_field}`, 0))
								END
							) > 0
							ORDER BY qty DESC
							""",
							(item_code, warehouse),
							as_dict=True,
						)
			except Exception:
				rows = rows or []
		if not rows:
			return ""
		need = flt(required_qty or 0)
		for r in rows:
			if flt(r.get("qty") or 0) + 1e-9 >= need:
				return _cstr(r.get("batch_no"))
		# Important: do NOT pick a partial batch for a full-consumption row.
		# Picking an under-qty batch causes negative stock on submit.
		return ""

	def _available_batches_for_rm(self, item_code: str, warehouse: str) -> list[dict]:
		"""Return available batches with qty for RM consumption, sorted by qty desc.

		Covers both classic SLE.batch_no and bundle-based batch entries.
		"""
		if not item_code or not warehouse:
			return []
		acc: dict[str, float] = {}
		# Path 1: classic batch_no on SLE
		for r in frappe.db.sql(
			"""
			SELECT batch_no, SUM(actual_qty) as qty
			FROM `tabStock Ledger Entry`
			WHERE IFNULL(is_cancelled, 0) = 0
			  AND IFNULL(item_code, '') = %s
			  AND IFNULL(warehouse, '') = %s
			  AND IFNULL(batch_no, '') != ''
			GROUP BY batch_no
			HAVING SUM(actual_qty) > 0
			""",
			(item_code, warehouse),
			as_dict=True,
		):
			bn = _cstr(r.get("batch_no"))
			q = flt(r.get("qty") or 0)
			if bn and q > 0:
				acc[bn] = acc.get(bn, 0.0) + q

		# Path 2: serial-and-batch bundle (v15)
		if frappe.db.has_column("Stock Ledger Entry", "serial_and_batch_bundle"):
			try:
				sb_entry_dt = "Serial and Batch Entry"
				if frappe.db.exists("DocType", sb_entry_dt):
					sb_entry_meta = frappe.get_meta(sb_entry_dt)
					batch_field = next(
						(fn for fn in ("batch_no", "batch", "batch_id") if sb_entry_meta.has_field(fn)),
						"",
					)
					qty_field = next(
						(fn for fn in ("qty", "quantity") if sb_entry_meta.has_field(fn)),
						"",
					)
					if batch_field and qty_field:
						rows = frappe.db.sql(
							f"""
							SELECT
								sbe.`{batch_field}` AS batch_no,
								SUM(
									CASE
										WHEN IFNULL(sle.actual_qty, 0) < 0 THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
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
									WHEN IFNULL(sle.actual_qty, 0) < 0 THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
									ELSE ABS(IFNULL(sbe.`{qty_field}`, 0))
								END
							) > 0
							""",
							(item_code, warehouse),
							as_dict=True,
						)
						for r in rows or []:
							bn = _cstr(r.get("batch_no"))
							q = flt(r.get("qty") or 0)
							if bn and q > 0:
								acc[bn] = max(acc.get(bn, 0.0), q)
			except Exception:
				pass

		out = [{"batch_no": bn, "qty": flt(q)} for bn, q in acc.items() if bn and flt(q) > 0]
		out.sort(key=lambda x: flt(x.get("qty") or 0), reverse=True)
		return out

	def _available_batches_for_rm_all_wh(self, item_code: str) -> list[dict]:
		"""Like _available_batches_for_rm but queries ALL warehouses.

		Returns list of dicts with keys: batch_no, qty, warehouse.
		Used for the fabric-batch pick dialog so the user can see every
		available batch regardless of whether it is already in WIP.
		"""
		if not item_code:
			return []
		acc: dict[tuple, float] = {}

		for r in frappe.db.sql(
			"""
			SELECT batch_no, warehouse, SUM(actual_qty) AS qty
			FROM `tabStock Ledger Entry`
			WHERE IFNULL(is_cancelled, 0) = 0
			  AND IFNULL(item_code, '') = %s
			  AND IFNULL(batch_no, '') != ''
			GROUP BY batch_no, warehouse
			HAVING SUM(actual_qty) > 0
			""",
			(item_code,),
			as_dict=True,
		):
			bn = _cstr(r.get("batch_no"))
			wh = _cstr(r.get("warehouse"))
			q = flt(r.get("qty") or 0)
			if bn and wh and q > 0:
				key = (bn, wh)
				acc[key] = acc.get(key, 0.0) + q

		if frappe.db.has_column("Stock Ledger Entry", "serial_and_batch_bundle"):
			try:
				sb_entry_dt = "Serial and Batch Entry"
				if frappe.db.exists("DocType", sb_entry_dt):
					sb_meta = frappe.get_meta(sb_entry_dt)
					batch_field = next(
						(fn for fn in ("batch_no", "batch", "batch_id") if sb_meta.has_field(fn)), ""
					)
					qty_field = next(
						(fn for fn in ("qty", "quantity") if sb_meta.has_field(fn)), ""
					)
					if batch_field and qty_field:
						rows = frappe.db.sql(
							f"""
							SELECT
								sbe.`{batch_field}` AS batch_no,
								sle.warehouse,
								SUM(
									CASE
										WHEN IFNULL(sle.actual_qty,0) < 0
											THEN -ABS(IFNULL(sbe.`{qty_field}`,0))
										ELSE ABS(IFNULL(sbe.`{qty_field}`,0))
									END
								) AS qty
							FROM `tabStock Ledger Entry` sle
							INNER JOIN `tabSerial and Batch Entry` sbe
								ON sbe.parent = sle.serial_and_batch_bundle
							WHERE IFNULL(sle.is_cancelled, 0) = 0
							  AND IFNULL(sle.item_code, '') = %s
							  AND IFNULL(sle.serial_and_batch_bundle, '') != ''
							  AND IFNULL(sbe.`{batch_field}`, '') != ''
							GROUP BY sbe.`{batch_field}`, sle.warehouse
							HAVING SUM(
								CASE
									WHEN IFNULL(sle.actual_qty,0) < 0
										THEN -ABS(IFNULL(sbe.`{qty_field}`,0))
									ELSE ABS(IFNULL(sbe.`{qty_field}`,0))
								END
							) > 0
							""",
							(item_code,),
							as_dict=True,
						)
						for r in rows or []:
							bn = _cstr(r.get("batch_no"))
							wh = _cstr(r.get("warehouse"))
							q = flt(r.get("qty") or 0)
							if bn and wh and q > 0:
								key = (bn, wh)
								acc[key] = max(acc.get(key, 0.0), q)
			except Exception:
				pass

		out = [{"batch_no": bn, "qty": flt(q), "warehouse": wh} for (bn, wh), q in acc.items() if bn and flt(q) > 0]
		out.sort(key=lambda x: flt(x.get("qty") or 0), reverse=True)
		return out

	def _mtfm_batch_nos_for_wo_item(self, wo_name: str, item_code: str) -> set[str]:
		"""Batch numbers transferred to WIP for this WO via submitted Material Transfer for Manufacture."""
		wo_name = _cstr(wo_name).strip()
		item_code = _cstr(item_code).strip()
		out: set[str] = set()
		if not wo_name or not item_code:
			return out
		for r in frappe.db.sql(
			"""
			SELECT DISTINCT IFNULL(sed.batch_no, '') AS batch_no
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE se.docstatus = 1
			  AND IFNULL(se.work_order, '') = %s
			  AND IFNULL(se.purpose, '') = 'Material Transfer for Manufacture'
			  AND IFNULL(sed.item_code, '') = %s
			  AND IFNULL(sed.batch_no, '') != ''
			""",
			(wo_name, item_code),
			as_dict=True,
		):
			bn = _cstr(r.get("batch_no")).strip()
			if bn:
				out.add(bn)
		return out

	def _available_batches_for_wo_transfer(self, wo_doc, item_code: str) -> list[dict]:
		"""Only batches already transferred for this WO (MTFM), with current stock qty."""
		wo_name = _cstr(getattr(wo_doc, "name", None)).strip()
		allowed = self._mtfm_batch_nos_for_wo_item(wo_name, item_code)
		if not allowed:
			return []
		all_batches = self._available_batches_for_rm_all_wh(item_code)
		return [b for b in all_batches if _cstr(b.get("batch_no")).strip() in allowed]

	def _spr_fabric_picks_field_exists(self) -> bool:
		try:
			return bool(frappe.get_meta("Shaft Production Run").has_field("fabric_batch_picks"))
		except Exception:
			return False

	def _spr_init_manual_fabric_batch_pools(self, planned_wo_posts) -> None:
		"""Validate `fabric_batch_picks` vs BOM batch-tracked RM need and build mutable pools for Manufacture SE."""
		self.flags._spr_manual_batch_pools = {}
		if not self._spr_fabric_picks_field_exists():
			return
		pools: dict[str, dict[str, list]] = {}
		for plan in planned_wo_posts or []:
			wo_id = _cstr(plan.get("wo_id"))
			wo_doc = plan.get("wo_doc")
			total_qty = flt(plan.get("total_qty") or 0)
			if not wo_id or not wo_doc or total_qty <= 0:
				continue
			pi = _cstr(getattr(wo_doc, "production_item", None) or "")
			if not spr_fg_needs_rm_batch_pick(pi, spr_doc_is_bag_spr(self)):
				continue
			expected = self._build_expected_rm_map_for_qty(wo_doc, total_qty)
			batch_rm = {
				ic: q
				for ic, q in (expected or {}).items()
				if _spr_rm_needs_manual_batch_pick(ic) and flt(q) > 1e-9
			}
			if not batch_rm:
				continue
			picks = [
				r
				for r in (self.get("fabric_batch_picks") or [])
				if _cstr(getattr(r, "work_order", None) or "") == wo_id
			]
			if not picks:
				if spr_doc_is_bag_spr(self):
					frappe.throw(
						_(
							"Bag SPR — Work Order {0} (item {1}) needs raw-material batches before Submit. "
							"Open **Tools → SPR — Select RM batches**, allocate fabric/BOM batches, Save picks, then Submit again."
						).format(wo_id, pi or "—"),
						title=_("RM batches required"),
					)
				frappe.throw(
					_(
						"This SPR manufactures Work Order {0} (parent item {1}). "
						"Use **Select RM batches** on the toolbar and allocate each batch-tracked BOM item before Submit."
					).format(wo_id, pi or "—"),
					title=_("RM batches required"),
				)
			by_item: dict[str, list] = defaultdict(list)
			for p in picks:
				ic = _cstr(getattr(p, "item_code", None))
				bn = _cstr(getattr(p, "batch_no", None))
				q = flt(getattr(p, "qty", None))
				if not ic or not bn or q <= 0:
					continue
				if not _spr_rm_needs_manual_batch_pick(ic):
					frappe.throw(
						_("Batch pick lines must be for batch-tracked BOM items (got {0}).").format(ic)
					)
				if frappe.db.exists("Batch", bn):
					batch_item = frappe.db.get_value("Batch", bn, "item")
					if batch_item and _cstr(batch_item) != ic:
						frappe.throw(
							_("Batch {0} belongs to item {1}, not {2}. Fix SPR {3}.").format(bn, batch_item, ic, self.name)
						)
				by_item[ic].append({"batch_no": bn, "qty": q})
			for ic, req in batch_rm.items():
				got = sum(flt(x["qty"]) for x in by_item.get(ic, []))
				if got + 1e-6 < flt(req):
					frappe.throw(
						_(
							"Work Order {0}: RM {1} needs {2} Kg in batch picks but only {3} Kg is set. "
							"Open **Select RM batches** and increase quantities."
						).format(wo_id, ic, flt(req, 3), flt(got, 3)),
						title=_("Insufficient RM batch quantity"),
					)
			pools[wo_id] = {
				k: [{"batch_no": x["batch_no"], "qty": flt(x["qty"])} for x in v] for k, v in by_item.items()
			}
		self.flags._spr_manual_batch_pools = pools

	def _spr_rm_row_uses_manual_pool(self, wo_id: str | None, item_code: str) -> bool:
		if not wo_id:
			return False
		pools = getattr(self.flags, "_spr_manual_batch_pools", None) or {}
		if wo_id not in pools:
			return False
		ic = _cstr(item_code)
		if not _spr_rm_needs_manual_batch_pick(ic):
			return False
		return ic in (pools.get(wo_id) or {})

	def _spr_take_from_manual_pool(self, wo_id: str, item_code: str, required: float):
		ch = list((getattr(self.flags, "_spr_manual_batch_pools", None) or {}).get(wo_id, {}).get(item_code, []) or [])
		remaining = flt(required)
		allocs: list[tuple[str, float]] = []
		idx = 0
		while idx < len(ch) and remaining > 1e-9:
			entry = ch[idx]
			av = flt(entry.get("qty"))
			if av <= 1e-9:
				idx += 1
				continue
			take = min(av, remaining)
			allocs.append((_cstr(entry.get("batch_no")), flt(take)))
			entry["qty"] = flt(av - take)
			remaining = flt(remaining - take)
			if entry["qty"] <= 1e-9:
				idx += 1
		return allocs, remaining

	def _spr_apply_manual_rm_batch_splits(self, se, rm_row, allocs: list[tuple[str, float]], source_wh: str):
		if not allocs:
			return
		cf = flt(rm_row.get("conversion_factor") or 1) or 1
		first_bn, first_qty = allocs[0]
		rm_row.batch_no = first_bn
		rm_row.s_warehouse = source_wh
		rm_row.transfer_qty = flt(first_qty, 6)
		rm_row.qty = flt(first_qty / cf, 6)
		for bn, tq in allocs[1:]:
			new_row = se.append("items", {})
			base = rm_row.as_dict()
			for k, v in base.items():
				if k in {"name", "parent", "parenttype", "parentfield", "idx", "owner", "creation", "modified", "modified_by", "docstatus"}:
					continue
				new_row.set(k, v)
			new_row.batch_no = bn
			new_row.s_warehouse = source_wh
			new_row.transfer_qty = flt(tq, 6)
			new_row.qty = flt(tq / cf, 6)

	def _assign_rm_batches_for_stock_entry(self, se, wo_id: str | None = None):
		"""Assign batch_no for batch-tracked RM lines before submit.

		For Work Orders on FG processes 102–109, 251, 252 (incl. design-first codes), 100* fabric lines consume
		batches from operator picks (`fabric_batch_picks`) in order instead of auto FIFO by quantity.
		"""
		for d in list(se.items or []):
			if not d.item_code or d.get("t_warehouse"):
				continue
			if _cstr(d.get("batch_no")):
				continue
			if not cint(frappe.db.get_value("Item", d.item_code, "has_batch_no") or 0):
				continue
			wh = _cstr(d.get("s_warehouse"))
			required = flt(d.get("transfer_qty") or d.get("qty") or 0)
			if self._spr_rm_row_uses_manual_pool(wo_id, d.item_code):
				allocs, leftover = self._spr_take_from_manual_pool(_cstr(wo_id), _cstr(d.item_code), required)
				if leftover > 1e-6 or not allocs:
					frappe.throw(
						_(
							"Manual RM batch pool for WO {0}, item {1}, is exhausted or short by {2} Kg "
							"(required for this Manufacture line: {3} Kg). Re-open **Select RM batches**."
						).format(wo_id or "—", _cstr(d.item_code), flt(leftover, 3), flt(required, 3)),
						title=_("Fabric batch pool exhausted"),
					)
				self._spr_apply_manual_rm_batch_splits(se, d, allocs, wh)
				continue

			candidates = self._available_batches_for_rm(_cstr(d.item_code), wh)
			source_wh = wh
			if not candidates:
				# Fallback: if WIP has no batches yet, consume directly from from_warehouse with valid batches.
				fallback_wh = _cstr(se.get("from_warehouse"))
				if fallback_wh and fallback_wh != wh:
					candidates = self._available_batches_for_rm(_cstr(d.item_code), fallback_wh)
					if candidates:
						source_wh = fallback_wh

			remaining = flt(required)
			allocs: list[tuple[str, float]] = []
			for c in candidates:
				if remaining <= 1e-9:
					break
				q = flt(c.get("qty") or 0)
				if q <= 1e-9:
					continue
				take = min(q, remaining)
				if take > 1e-9:
					allocs.append((_cstr(c.get("batch_no")), flt(take)))
					remaining = flt(remaining - take)

			if allocs and remaining <= 1e-6:
				# Split one RM row across many batches when needed.
				cf = flt(d.get("conversion_factor") or 1) or 1
				first_bn, first_qty = allocs[0]
				d.batch_no = first_bn
				d.s_warehouse = source_wh
				d.transfer_qty = flt(first_qty, 6)
				d.qty = flt(first_qty / cf, 6)
				for bn, tq in allocs[1:]:
					new_row = se.append("items", {})
					base = d.as_dict()
					for k, v in base.items():
						if k in {"name", "parent", "parenttype", "parentfield", "idx", "owner", "creation", "modified", "modified_by", "docstatus"}:
							continue
						new_row.set(k, v)
					new_row.batch_no = bn
					new_row.s_warehouse = source_wh
					new_row.transfer_qty = flt(tq, 6)
					new_row.qty = flt(tq / cf, 6)
				continue

			avail_wh = flt(
				frappe.db.sql(
					"""
					SELECT IFNULL(SUM(actual_qty), 0)
					FROM `tabStock Ledger Entry`
					WHERE IFNULL(is_cancelled, 0) = 0
					  AND IFNULL(item_code, '') = %s
					  AND IFNULL(warehouse, '') = %s
					  AND IFNULL(batch_no, '') != ''
					""",
					(_cstr(d.item_code), wh),
				)[0][0]
				or 0
			)
			frappe.throw(
				_(
					"Batch is mandatory for raw material {0} in {1}, but no batch has enough quantity "
					"(required: {2}, available in batches: {3}). Transfer more stock or split issue batches."
				).format(
					_cstr(d.item_code), wh or "—", flt(required, 3), flt(avail_wh, 3)
				),
				title=_("Missing RM Batch"),
			)

	def _spr_merge_wos_from_shaft_jobs(self, wo_groups: dict[str, list]) -> None:
		"""Include WOs from Available Jobs so fabric can be picked before roll rows are linked or weighed."""
		for job in self.get("shaft_jobs") or []:
			raw = _cstr(getattr(job, "work_orders", None) or "")
			if not raw:
				continue
			for part in raw.replace("\n", ",").split(","):
				wo = part.strip()
				if not wo or not frappe.db.exists("Work Order", wo):
					continue
				wo_groups.setdefault(_cstr(wo), [])

	def _spr_fabric_pick_preview_fg_qty(self, rows: list, wo_doc) -> float:
		"""FG kg for BOM preview: actual roll weights, else planned_qty, else WO remaining / qty (min 1)."""
		qty = sum(self._row_fg_qty(r) for r in rows)
		if qty > 1e-9:
			return qty
		wo_id = _cstr(getattr(wo_doc, "name", None))
		if spr_doc_is_bag_spr(self) and wo_id:
			for br in self.bundle_calculation or []:
				if _cstr(getattr(br, "work_order", None)) != wo_id:
					continue
				planned = flt(getattr(br, "total_pcs_per_bundle", 0) or 0)
				if planned > 1e-9:
					return planned
				n_boxes = cint(getattr(br, "no_of_boxes", 0) or 0)
				pcs = cint(getattr(br, "pcs_per_packet", 0) or 0)
				if n_boxes > 0 and pcs > 0:
					return flt(n_boxes * pcs)
			achieved = sum(
				flt(_spr_row_get(r, "custom_achieved_bag_pcs"))
				for r in (self.items or [])
				if _cstr(r.get("work_order") or r.get("wo_id")) == wo_id
			)
			if achieved > 1e-9:
				return achieved
		if cint(getattr(self, "custom_is_box_bag", 0)):
			planned_bags = sum(flt(_spr_row_get(r, "custom_planned_bag_pcs")) for r in rows)
			if planned_bags > 1e-9:
				return planned_bags
		if cint(getattr(self, "custom_is_sheet_cutting", 0)):
			planned_sheets = sum(flt(_spr_row_get(r, "custom_planned_sheets_pcs")) for r in rows)
			if planned_sheets > 1e-9:
				return planned_sheets
		planned = sum(flt(_spr_row_get(r, "planned_qty")) for r in rows)
		if planned > 1e-9:
			return planned
		remaining, _, _, _ = self._wo_allowed_remaining_qty(wo_doc)
		if remaining > 1e-9:
			return remaining
		base = flt(getattr(wo_doc, "qty", 0))
		if base > 1e-9:
			return base
		return 1.0

	def _spr_wo_groups_for_batch_pick(self) -> dict[str, list]:
		"""Work Orders → roll lines for RM batch dialog (items + bundle_calculation + shaft jobs)."""
		wo_groups: dict[str, list] = {}
		for row in self.items or []:
			wo_name = _cstr(row.get("work_order") or row.get("wo_id"))
			if wo_name:
				wo_groups.setdefault(wo_name, []).append(row)
		for br in self.bundle_calculation or []:
			wo_name = _cstr(getattr(br, "work_order", None))
			if not wo_name or wo_name in wo_groups:
				continue
			linked = [
				r
				for r in (self.items or [])
				if _cstr(r.get("work_order") or r.get("wo_id")) == wo_name
			]
			wo_groups[wo_name] = linked or [{"work_order": wo_name, "wo_id": wo_name}]
		self._spr_merge_wos_from_shaft_jobs(wo_groups)
		if spr_doc_is_bag_spr(self):
			for br in self.bundle_calculation or []:
				wo_name = _cstr(getattr(br, "work_order", None))
				if not wo_name or wo_name in wo_groups:
					continue
				wo_groups[wo_name] = [{"work_order": wo_name, "wo_id": wo_name}]
			pp = _cstr(self.get("production_plan"))
			if pp:
				for wo in frappe.get_all(
					"Work Order",
					filters={"production_plan": pp, "docstatus": ["<", 2]},
					fields=["name", "production_item"],
				):
					wo_name = _cstr(wo.get("name"))
					pi = _cstr(wo.get("production_item"))
					if not wo_name or wo_name in wo_groups:
						continue
					if spr_bag_fg_needs_rm_batch_pick(pi):
						wo_groups[wo_name] = wo_groups.get(wo_name) or [{"work_order": wo_name, "wo_id": wo_name}]
		return wo_groups

	def _spr_build_fabric_batch_pick_context_dict(self) -> dict:
		"""API payload for the desk RM-batch dialog (102–109, 251–255 WOs + batch-tracked BOM RM + WIP batches)."""
		is_bag_spr = spr_doc_is_bag_spr(self)
		out: dict = {
			"needs_picks": False,
			"lines": [],
			"current_picks": [],
			"spr": self.name,
			"is_bag_spr": bool(is_bag_spr),
		}
		if cint(self.docstatus) != 0:
			return out
		if not self._spr_fabric_picks_field_exists():
			return out
		wo_groups = self._spr_wo_groups_for_batch_pick()
		lines = []
		for wo_id, rows in wo_groups.items():
			if not frappe.db.exists("Work Order", wo_id):
				continue
			wo_doc = frappe.get_doc("Work Order", wo_id)
			pi = _cstr(getattr(wo_doc, "production_item", None) or "")
			if not spr_fg_needs_rm_batch_pick(pi, is_bag_spr):
				continue
			total_qty = self._spr_fabric_pick_preview_fg_qty(rows, wo_doc)
			if total_qty <= 0:
				continue
			expected = self._build_expected_rm_map_for_qty(wo_doc, total_qty)
			wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None) or "")
			fg_process = _spr_resolve_bag_fg_process_code(pi) or spr_fg_item_process_code(pi)
			bom_stack = _spr_bom_stack_for_fg_item(pi)
			raw_list = []
			for ic, req in sorted((expected or {}).items()):
				ic_s = _cstr(ic)
				if not _spr_rm_needs_manual_batch_pick(ic_s):
					continue
				if flt(req) <= 1e-9:
					continue
				batches = self._available_batches_for_wo_transfer(wo_doc, ic_s)
				item_name = frappe.db.get_value("Item", ic_s, "item_name") or ""
				rm_proc = spr_fg_item_process_code(ic_s)
				qual, col = extract_quality_and_color(item_name, ic_s)
				try:
					gsm, width_inch = parse_item_code(ic_s)
				except Exception:
					gsm, width_inch = 0.0, 0.0
				if flt(gsm) <= 0:
					gsm = float(_fabric_gsm_from_item_name(item_name))
				raw_list.append(
					{
						"item_code": ic_s,
						"item_name": item_name,
						"process_code": rm_proc,
						"required_qty": flt(req, 3),
						"quality": qual or "",
						"colour": col or "",
						"gsm": flt(gsm, 2),
						"width_inch": flt(width_inch, 2),
						"batches": batches,
					}
				)
			if raw_list:
				lines.append(
					{
						"work_order": wo_id,
						"fg_item": pi,
						"fg_process": fg_process,
						"bom_stack": bom_stack,
						"wip_warehouse": wip_wh,
						"total_fg_kg": flt(total_qty, 3),
						"raw_materials": raw_list,
					}
				)
		cur = []
		for r in self.get("fabric_batch_picks") or []:
			cur.append(
				{
					"work_order": _cstr(getattr(r, "work_order", None)),
					"item_code": _cstr(getattr(r, "item_code", None)),
					"batch_no": _cstr(getattr(r, "batch_no", None)),
					"qty": flt(getattr(r, "qty", None)),
				}
			)
		out["current_picks"] = cur
		out["needs_picks"] = bool(lines)
		out["lines"] = lines
		return out

	def _rm_shortages_from_exception(self, exc) -> list[tuple[str, str, float, float, float]]:
		"""Best-effort parse of ERPNext insufficient-stock message into shortage tuples."""
		msg = _cstr(exc)
		if not msg:
			return []
		# Example:
		# "0.994 units of Item MB - 1001222: ... needed in Warehouse Work In Progress - ... to complete this transaction."
		# or HTML-rich equivalent with <strong> / links.
		msg_plain = re.sub(r"<[^>]+>", " ", msg)
		msg_plain = re.sub(r"\s+", " ", msg_plain).strip()
		m = re.search(
			r"([0-9]+(?:\.[0-9]+)?)\s+units?\s+of\s+Item\s+([^:]+):.*?Warehouse\s+(.+?)\s+to\s+complete",
			msg_plain,
			flags=re.IGNORECASE,
		)
		if not m:
			return []
		short_qty = flt(m.group(1))
		item_code = _cstr(m.group(2)).strip()
		wh = _cstr(m.group(3)).strip()
		if not item_code or not wh or short_qty <= 0:
			return []
		# required/available unknown from exception text; provide safe fallback for draft transfer creation path.
		return [(item_code, wh, short_qty, 0.0, short_qty)]

	def _spr_insert_shortage_transfer_draft(self, se) -> str:
		"""Insert MTFM for shortages; auto-submit when stock is available."""
		self._spr_last_mtfm_error = ""
		try:
			_spr_prepare_mtfm_stock_entry_for_submit(se)
			self._spr_apply_stock_entry_item_accounts(se)
			se.flags.ignore_mandatory = True
			se.flags.ignore_permissions = True
			se.insert()
			name = _cstr(se.name)
			self._persist_stock_entry_spr_reference_db(name)
			try:
				se.flags.ignore_permissions = True
				se.submit()
			except Exception as submit_exc:
				submit_msg = _cstr(submit_exc)
				# Retry once after filling accounts (expense_account is mandatory on some sites).
				if "Expense Account" in submit_msg:
					se.reload()
					self._spr_apply_stock_entry_item_accounts(se)
					se.flags.ignore_permissions = True
					se.save()
					se.submit()
				elif "Maximum transferable" in submit_msg or "Cannot transfer" in submit_msg:
					se.reload()
					plain_msg = re.sub(r"<[^>]+>", "", submit_msg)
					max_kg = _spr_parse_max_transferable_kg(plain_msg)
					if max_kg <= 0:
						for d in se.items or []:
							if d.get("s_warehouse"):
								d.batch_no = ""
						_spr_prepare_mtfm_stock_entry_for_submit(se)
						self._spr_apply_stock_entry_item_accounts(se)
						se.flags.ignore_permissions = True
						se.save()
						kept = [
							d
							for d in (se.items or [])
							if flt(d.get("transfer_qty") or d.get("qty"))
							> _spr_rm_wip_shortage_tolerance(flt(d.get("transfer_qty") or d.get("qty")))
						]
						se.items = kept
						if not kept:
							try:
								frappe.delete_doc("Stock Entry", se.name, force=1)
							except Exception:
								pass
							self._spr_last_mtfm_error = plain_msg
							return ""
						se.submit()
					else:
						row_m = re.search(r"Row #(\d+)", plain_msg, flags=re.IGNORECASE)
						row_idx = int(row_m.group(1)) - 1 if row_m else 0
						for i, d in enumerate(se.items or []):
							if not d.item_code or not d.get("s_warehouse"):
								continue
							req = flt(d.get("transfer_qty") or d.get("qty"))
							if i == row_idx:
								req = min(req, max_kg)
							_spr_finalize_mtfm_line_qty(d, d.s_warehouse, req)
						# Drop zero-qty lines — submit partial transfer when RM has some stock.
						kept = []
						for d in se.items or []:
							tol = _spr_rm_wip_shortage_tolerance(
								flt(d.get("transfer_qty") or d.get("qty"))
							)
							if flt(d.get("transfer_qty") or d.get("qty")) > tol:
								kept.append(d)
						se.items = kept
						if not kept:
							try:
								frappe.delete_doc("Stock Entry", se.name, force=1)
							except Exception:
								pass
							self._spr_last_mtfm_error = plain_msg
							return ""
						self._spr_apply_stock_entry_item_accounts(se)
						se.flags.ignore_permissions = True
						se.save()
						se.submit()
				else:
					raise
			# Commit immediately so draft/submitted entry survives frappe.throw rollback during SPR before_submit.
			try:
				frappe.db.commit()
			except Exception:
				pass
			# Force bin sync after commit to ensure stock is immediately queryable
			if name and frappe.db.exists("Stock Entry", name):
				try:
					self._force_sync_bins_for_stock_entry(name)
				except Exception:
					pass
				return name
		except Exception as exc:
			self._spr_last_mtfm_error = _cstr(exc)
			if "Expense Account" in _cstr(exc):
				frappe.throw(
					_(
						"Material Transfer could not be submitted: expense account is missing on one or more "
						"raw materials. Open each Item → Defaults and set Expense Account for company {0}, "
						"or set Company → Stock Adjustment Account, then submit SPR again."
					).format(_cstr(getattr(se, "company", None))),
					title=_("Expense Account required"),
				)
			frappe.log_error(
				frappe.get_traceback(),
				f"SPR shortage draft insert failed:{self.name}",
			)
		return ""

	def _transfer_for_manufacture_type_name(self) -> str:
		"""Resolve a valid Stock Entry Type for 'Material Transfer for Manufacture' purpose."""
		if frappe.db.exists("Stock Entry Type", "Material Transfer for Manufacture"):
			p = _cstr(frappe.db.get_value("Stock Entry Type", "Material Transfer for Manufacture", "purpose"))
			if p == "Material Transfer for Manufacture":
				return "Material Transfer for Manufacture"
		name = frappe.db.get_value("Stock Entry Type", {"purpose": "Material Transfer for Manufacture"}, "name")
		return _cstr(name) if name else "Material Transfer for Manufacture"

	def _reload_work_order_doc(self, wo_doc):
		wo_name = _cstr(getattr(wo_doc, "name", None)).strip()
		if not wo_name:
			return wo_doc
		try:
			return frappe.get_doc("Work Order", wo_name)
		except Exception:
			return wo_doc

	def _spr_company_warehouse_ctx(self) -> dict:
		"""Strict company RM (source) and WIP (target) warehouses for this SPR."""
		from production_entry.production_planning.spr_unit_warehouses import (
			_company_rm_warehouse,
			_company_wip_warehouse,
			resolve_spr_unit_manufacturing_warehouses,
		)

		company = _spr_company_from_doc(self)
		unit = _cstr(getattr(self, "custom_unit", None) or getattr(self, "unit", None))
		wh_ctx: dict = {}
		if unit:
			try:
				wh_ctx = resolve_spr_unit_manufacturing_warehouses(unit) or {}
			except Exception:
				wh_ctx = {}
		if not company:
			company = _cstr(wh_ctx.get("company"))
		wip_wh = _cstr(wh_ctx.get("wip_warehouse"))
		source_wh = _cstr(wh_ctx.get("source_warehouse"))
		if company:
			if not wip_wh:
				wip_wh = _company_wip_warehouse(company)
			if not source_wh:
				source_wh = _company_rm_warehouse(company, wip_wh=wip_wh)
		return {
			"company": company,
			"wip_warehouse": wip_wh,
			"source_warehouse": source_wh,
		}

	def _resolve_rm_source_warehouse_for_transfer(self, wo_doc, item_code: str, wip_wh: str) -> str:
		"""RM store for MTFM lines (never WIP) — prefer SPR company RM warehouse."""
		item_code = _cstr(item_code).strip()
		wip_wh = _cstr(wip_wh).strip()
		ctx = self._spr_company_warehouse_ctx()
		strict_rm = _cstr(ctx.get("source_warehouse")).strip()
		if strict_rm and strict_rm != wip_wh:
			return strict_rm
		wo_doc = self._reload_work_order_doc(wo_doc)
		raw_source_wh = _cstr(getattr(wo_doc, "source_warehouse", None)).strip()
		company = _cstr(getattr(wo_doc, "company", None)).strip() or _cstr(ctx.get("company"))
		src = _spr_wo_rm_source_warehouse(wo_doc, item_code, wip_wh)
		if src and src != wip_wh:
			return src
		if raw_source_wh and raw_source_wh != wip_wh:
			return raw_source_wh
		co_rm = _spr_company_rm_warehouse(company, wip_wh)
		if co_rm:
			return co_rm
		return ""

	def _append_mtfm_shortage_lines(
		self, se, wo_doc, short_by_item: dict, wip_wh: str, ignore_wo_transfer: bool = False
	) -> int:
		"""Append RM->WIP lines for shortage qty; returns count of lines added."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		ctx = self._spr_company_warehouse_ctx()
		wip_wh = _cstr(ctx.get("wip_warehouse")).strip() or _cstr(wip_wh).strip()
		is_bag = spr_doc_is_bag_spr(self)
		added = 0
		for item_code, short_qty in sorted((short_by_item or {}).items()):
			ic = _cstr(item_code).strip()
			if ignore_wo_transfer:
				qty = _spr_wip_topup_bump_qty(short_qty)
			else:
				qty = _spr_round_rm_stock_qty(short_qty)
				tol = _spr_rm_wip_shortage_tolerance(qty)
				if not ic or qty <= tol:
					continue
			if not ic or qty <= 0:
				continue
			if not ignore_wo_transfer:
				tol = _spr_rm_wip_shortage_tolerance(qty)
				still = _spr_wo_rm_transfer_remaining(wo_doc, ic)
				if still > tol:
					qty = min(qty, _spr_round_rm_stock_qty(still))
				elif is_bag and still <= tol:
					continue
			item_src = self._resolve_rm_source_warehouse_for_transfer(wo_doc, ic, wip_wh)
			company = _cstr(getattr(se, "company", None)).strip() or _cstr(ctx.get("company"))
			alt_wh, alt_avl = _spr_find_rm_warehouse_with_stock(company, ic, wip_wh, item_src, qty)
			if alt_wh and alt_avl > 0:
				item_src = alt_wh
			if not item_src:
				frappe.log_error(
					_("No RM source warehouse for {0} on WO {1}").format(ic, getattr(wo_doc, "name", "")),
					f"SPR MTFM draft no source:{self.name}",
				)
				continue
			stock_uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
			line = {
				"item_code": ic,
				"s_warehouse": item_src,
				"t_warehouse": wip_wh,
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1.0,
				"qty": qty,
				"transfer_qty": qty,
				"work_order": wo_doc.name,
			}
			company = _cstr(getattr(se, "company", None)).strip()
			exp_acc = _spr_resolve_expense_account(ic, company, item_src) if company else ""
			if exp_acc:
				line["expense_account"] = exp_acc
			cc = frappe.db.get_value("Company", company, "cost_center") if company else None
			if cc:
				line["cost_center"] = cc
			se.append("items", line)
			if se.items:
				qty = _spr_finalize_mtfm_line_qty(se.items[-1], item_src, qty)
			tol = _spr_rm_wip_shortage_tolerance(qty)
			if qty <= tol:
				se.items.pop()
				frappe.log_error(
					_(
						"No RM stock for {0} in {1} (need {2} Kg for WIP transfer). "
						"Transfer raw material to RM warehouse first."
					).format(ic, item_src, _spr_round_rm_stock_qty(short_qty)),
					f"SPR MTFM RM shortage:{self.name}",
				)
				continue
			added += 1
		return added

	def _mtfm_fg_qty_for_shortage_transfer(
		self, wo_doc, short_by_item: dict, chunk_total_qty: float
	) -> float:
		"""Cap MTFM fg_completed_qty so over-produced SPR runs do not exceed WO transfer allowance."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		chunk_total_qty = flt(chunk_total_qty)
		remaining_fg, _allowed_total, _already, _over_pct = self._wo_allowed_remaining_qty(wo_doc)
		wo_base = flt(getattr(wo_doc, "qty", 0))
		cap = remaining_fg if remaining_fg > 0 else wo_base
		if cap <= 0:
			cap = chunk_total_qty or 1.0

		fg_from_short = 0.0
		bom_no = _cstr(getattr(wo_doc, "bom_no", None))
		if bom_no and short_by_item and wo_base > 0:
			full_rm_map, _multi = _bom_rm_stock_qty_map_for_fg(bom_no, wo_base)
			for ic, short_qty in (short_by_item or {}).items():
				full_need = flt(full_rm_map.get(_cstr(ic)))
				if full_need > 0 and flt(short_qty) > 0:
					fg_from_short = max(fg_from_short, (flt(short_qty) / full_need) * wo_base)

		target = chunk_total_qty if chunk_total_qty > 0 else cap
		if fg_from_short > 0:
			target = min(target, flt(fg_from_short) * 1.02)
		target = min(target, cap)
		if target <= 0:
			target = min(chunk_total_qty, cap) if cap > 0 else (chunk_total_qty or 1.0)
		return max(flt(target), 0.001)

	def _prune_short_by_item_to_wo_transfer_remaining(self, wo_doc, short_by_item: dict) -> dict:
		"""Keep only RM lines that still need transfer on the WO (prevents duplicate MTFM per item)."""
		wo_doc = self._reload_work_order_doc(wo_doc)
		out: dict[str, float] = {}
		for ic, qty in (short_by_item or {}).items():
			code = _cstr(ic).strip()
			if not code:
				continue
			still = _spr_wo_rm_transfer_remaining(wo_doc, code)
			tol = _spr_rm_wip_shortage_tolerance(flt(qty))
			if still <= tol:
				continue
			need = min(_spr_round_rm_stock_qty(flt(qty)), _spr_round_rm_stock_qty(still))
			if need > tol:
				out[code] = need
		return out

	def _spr_mtfm_stock_entry_filters(self) -> dict:
		filters = {"purpose": "Material Transfer for Manufacture"}
		meta = frappe.get_meta("Stock Entry")
		if meta.has_field("shaft_production_run"):
			filters["shaft_production_run"] = self.name
		elif frappe.db.has_column("Stock Entry", "custom_spr_reference"):
			filters["custom_spr_reference"] = self.name
		else:
			return {}
		return filters

	def _find_recent_spr_wo_mtfm_transfer(self, wo_name: str, docstatus=None) -> str:
		"""Latest MTFM for this SPR + WO (draft or submitted) — avoids duplicate transfers on retry."""
		wo_name = _cstr(wo_name).strip()
		base = self._spr_mtfm_stock_entry_filters()
		if not wo_name or not base:
			return ""
		filters = dict(base)
		filters["work_order"] = wo_name
		if docstatus is not None:
			filters["docstatus"] = docstatus
		names = frappe.get_all(
			"Stock Entry",
			filters=filters,
			pluck="name",
			order_by="modified desc",
			limit=1,
		)
		return _cstr(names[0]) if names else ""

	def _shortage_events_still_blocking(self, shortage_events) -> list:
		"""Re-check WIP RM availability after MTFM — skip throw when transfers already satisfied need."""
		blocking = []
		for event in shortage_events or []:
			wo_doc = self._reload_work_order_doc(event.get("wo_doc"))
			if not wo_doc:
				continue
			chunk_total_qty = flt(event.get("chunk_total_qty"))
			if chunk_total_qty <= 0:
				continue
			preview_se = self._build_shortage_preview_for_chunk(wo_doc, chunk_total_qty)
			shortages = self._rm_shortages_for_se(preview_se, wo_doc)
			wip_topup = self._spr_wip_topup_shortages_for_se(preview_se, wo_doc)
			if shortages:
				blocking.append(
					{
						"wo_id": _cstr(event.get("wo_id")),
						"wo_doc": wo_doc,
						"chunk_total_qty": chunk_total_qty,
						"shortages": shortages,
					}
				)
			if wip_topup:
				blocking.append(
					{
						"wo_id": _cstr(event.get("wo_id")),
						"wo_doc": wo_doc,
						"chunk_total_qty": chunk_total_qty,
						"shortages": wip_topup,
						"wip_topup": True,
					}
				)
		return blocking

	def _new_mtfm_stock_entry_shell(
		self,
		wo_doc,
		chunk_total_qty: float,
		transfer_posting_date=None,
		transfer_posting_time=None,
		short_by_item=None,
	):
		wo_doc = self._reload_work_order_doc(wo_doc)
		ctx = self._spr_company_warehouse_ctx()
		company = _cstr(ctx.get("company")) or _cstr(getattr(wo_doc, "company", None))
		raw_source_wh = _cstr(ctx.get("source_warehouse")) or _cstr(getattr(wo_doc, "source_warehouse", None)) or ""
		wip_wh = _cstr(ctx.get("wip_warehouse")) or _cstr(getattr(wo_doc, "wip_warehouse", None)) or ""
		is_bag = spr_doc_is_bag_spr(self)
		se = frappe.new_doc("Stock Entry")
		se.company = company or wo_doc.company
		se.posting_date = transfer_posting_date or today()
		se.posting_time = transfer_posting_time or nowtime()
		se.set_posting_time = 1
		se.purpose = "Material Transfer for Manufacture"
		se.stock_entry_type = self._transfer_for_manufacture_type_name()
		se.work_order = wo_doc.name
		se.production_item = wo_doc.production_item
		if short_by_item:
			se.fg_completed_qty = self._mtfm_fg_qty_for_shortage_transfer(
				wo_doc, short_by_item, chunk_total_qty
			)
		else:
			se.fg_completed_qty = flt(chunk_total_qty) if flt(chunk_total_qty) > 0 else 1.0
		se.from_warehouse = None if is_bag else (raw_source_wh or None)
		se.wip_warehouse = wip_wh
		se.to_warehouse = wip_wh
		self._set_stock_entry_spr_link(se)
		_spr_enable_serial_batch_fields_on_se(se)
		return se, wip_wh

	def _create_wip_shortage_transfer_draft(self, wo_doc, chunk_total_qty: float, shortages: list[tuple[str, str, float, float, float]]) -> str:
		"""Create a draft Material Transfer for Manufacture for shortage items only."""
		if not wo_doc or not shortages:
			return ""
		wo_doc = self._reload_work_order_doc(wo_doc)
		# Use current day/time for shortage transfers to avoid backdated ledger insufficiency on old run dates.
		transfer_posting_date = today()
		transfer_posting_time = nowtime()
		wo_id = _cstr(getattr(wo_doc, "name", None))
		# Reuse existing draft for same WO + SPR to avoid duplicate drafts on retry.
		existing = self._find_open_wip_shortage_transfer_draft(wo_id)
		if existing:
			return existing
		wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None)) or ""
		if not wip_wh:
			return ""
		short_by_item = defaultdict(float)
		for item_code, _wh, _req, _avl, short_qty in shortages:
			if item_code and flt(short_qty) > 0:
				short_by_item[_cstr(item_code)] += flt(short_qty)
		if not short_by_item:
			return ""

		for ic in list(short_by_item.keys()):
			qty = _spr_round_rm_stock_qty(short_by_item.get(ic))
			tol = _spr_rm_wip_shortage_tolerance(qty)
			if qty <= tol:
				short_by_item.pop(ic, None)
				continue
			short_by_item[ic] = qty
		short_by_item = self._prune_short_by_item_to_wo_transfer_remaining(wo_doc, dict(short_by_item))
		if not short_by_item:
			return self._find_recent_spr_wo_mtfm_transfer(wo_id) or ""

		# One manual MTFM with all shortage RM lines (never BOM-driven — avoids per-item STE loops).
		se, _wip_b = self._new_mtfm_stock_entry_shell(
			wo_doc,
			chunk_total_qty,
			transfer_posting_date,
			transfer_posting_time,
			short_by_item=short_by_item,
		)
		se.from_bom = 0
		if not self._append_mtfm_shortage_lines(se, wo_doc, dict(short_by_item), wip_wh):
			return self._find_recent_spr_wo_mtfm_transfer(wo_id) or ""
		return self._spr_insert_shortage_transfer_draft(se)

	def _find_open_spr_shortage_transfer_draft(self) -> str:
		"""Find latest combined draft MTFM for this SPR."""
		filters = {
			"docstatus": 0,
			"purpose": "Material Transfer for Manufacture",
		}
		meta = frappe.get_meta("Stock Entry")
		if meta.has_field("shaft_production_run"):
			filters["shaft_production_run"] = self.name
		elif frappe.db.has_column("Stock Entry", "custom_spr_reference"):
			filters["custom_spr_reference"] = self.name
		else:
			return ""
		names = frappe.get_all("Stock Entry", filters=filters, pluck="name", order_by="modified desc", limit=1)
		return _cstr(names[0]) if names else ""

	def _create_combined_spr_shortage_transfer_draft(
		self, shortage_events, ignore_wo_transfer_prune: bool = False
	) -> str:
		"""One draft Material Transfer for Manufacture with all RM shortages (PP, LD, fabric, etc.)."""
		if not shortage_events:
			return ""
		existing = self._find_open_spr_shortage_transfer_draft()
		if existing:
			return existing

		short_map: dict[str, float] = defaultdict(float)
		item_meta: dict[str, tuple] = {}
		item_wo: dict[str, object] = {}
		item_wip_topup: dict[str, bool] = {}
		primary_wo_doc = None
		chunk_max = 0.0

		for event in shortage_events or []:
			wo_doc = event.get("wo_doc")
			is_wip_topup = bool(event.get("wip_topup"))
			if wo_doc and not primary_wo_doc:
				primary_wo_doc = self._reload_work_order_doc(wo_doc)
			chunk_max = max(chunk_max, flt(event.get("chunk_total_qty")))
			for item_code, wh, req, avl, short_qty in event.get("shortages") or []:
				ic = _cstr(item_code).strip()
				if not ic or not wo_doc or flt(short_qty) <= 0:
					continue
				short_map[ic] += flt(short_qty)
				item_wo[ic] = self._reload_work_order_doc(wo_doc)
				item_wip_topup[ic] = item_wip_topup.get(ic) or is_wip_topup
				if ic not in item_meta:
					item_meta[ic] = (_cstr(wh), flt(req), flt(avl))

		if not short_map or not primary_wo_doc:
			return ""

		if ignore_wo_transfer_prune:
			pruned_map = {_cstr(ic): _spr_round_rm_stock_qty(qty) for ic, qty in short_map.items()}
		else:
			pruned_map: dict[str, float] = {}
			item_wo_pruned: dict[str, object] = {}
			for ic, qty in short_map.items():
				wo_for_ic = item_wo.get(ic) or primary_wo_doc
				wo_ref = self._reload_work_order_doc(wo_for_ic)
				if item_wip_topup.get(ic):
					bumped = _spr_wip_topup_bump_qty(flt(qty))
					if bumped > _spr_rm_wip_shortage_tolerance(bumped):
						pruned_map[ic] = bumped
						item_wo_pruned[ic] = wo_ref
					continue
				pruned = self._prune_short_by_item_to_wo_transfer_remaining(wo_ref, {ic: flt(qty)})
				if pruned.get(ic):
					pruned_map[ic] = pruned[ic]
					item_wo_pruned[ic] = wo_ref
			if not pruned_map:
				wo_ids = sorted(
					{
						_cstr(getattr(item_wo.get(ic) or primary_wo_doc, "name", None))
						for ic in short_map.keys()
					}
				)
				for wo_id in wo_ids:
					if wo_id:
						found = self._find_recent_spr_wo_mtfm_transfer(wo_id)
						if found:
							return found
				return ""
			item_wo = item_wo_pruned

		short_map = pruned_map

		# Combined manual STE: all shortage RM lines in one entry (PP + LD + fabric, etc.).
		try:
			se, wip_wh = self._new_mtfm_stock_entry_shell(
				primary_wo_doc,
				chunk_max if chunk_max > 0 else 1.0,
				short_by_item=short_map,
			)
			se.from_bom = 0
			per_wo_short: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
			for ic, qty in short_map.items():
				wo_for_ic = item_wo.get(ic) or primary_wo_doc
				wo_key = _cstr(getattr(wo_for_ic, "name", None)).strip() or "__primary__"
				per_wo_short[wo_key][ic] += flt(qty)
			added_total = 0
			for _wo_key, ic_map in per_wo_short.items():
				sample_ic = next(iter(ic_map.keys()), "")
				wo_ref = item_wo.get(sample_ic) or primary_wo_doc
				added_total += self._append_mtfm_shortage_lines(
					se,
					wo_ref,
					dict(ic_map),
					wip_wh,
					ignore_wo_transfer=bool(
						ignore_wo_transfer_prune or item_wip_topup.get(sample_ic)
					),
				)
			if added_total > 0:
				name = self._spr_insert_shortage_transfer_draft(se)
				if name:
					return name
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"SPR combined MTFM draft:{self.name}")

		agg_shortages = [
			(ic, item_meta[ic][0], item_meta[ic][1], item_meta[ic][2], short_map[ic])
			for ic in sorted(short_map.keys())
		]
		return self._create_wip_shortage_transfer_draft(
			primary_wo_doc,
			chunk_max if chunk_max > 0 else 1.0,
			agg_shortages,
		)

	def _find_open_wip_shortage_transfer_draft(self, wo_name: str) -> str:
		"""Find latest draft transfer-for-manufacture for this WO and SPR."""
		wo_name = _cstr(wo_name)
		if not wo_name:
			return ""
		filters = {
			"docstatus": 0,
			"work_order": wo_name,
			"purpose": "Material Transfer for Manufacture",
		}
		meta = frappe.get_meta("Stock Entry")
		if meta.has_field("shaft_production_run"):
			filters["shaft_production_run"] = self.name
		elif frappe.db.has_column("Stock Entry", "custom_spr_reference"):
			filters["custom_spr_reference"] = self.name
		names = frappe.get_all("Stock Entry", filters=filters, pluck="name", order_by="modified desc", limit=1)
		return _cstr(names[0]) if names else ""

	def _build_shortage_preview_for_chunk(self, wo_doc, chunk_total_qty: float):
		"""Build a transient Manufacture entry for shortage pre-check without insert/submit."""
		posting_date = today()
		posting_time = nowtime()
		se = frappe.new_doc("Stock Entry")
		se.flags.ignore_duplicate_for_work_order = True
		se.company = wo_doc.company
		se.posting_date = posting_date
		se.posting_time = posting_time
		se.set_posting_time = 1
		se.stock_entry_type = self._manufacture_stock_entry_type_name()
		se.purpose = "Manufacture"
		se.work_order = None
		se.production_item = wo_doc.production_item
		se.fg_completed_qty = flt(chunk_total_qty)
		se.from_bom = 1
		se.bom_no = wo_doc.bom_no
		se.use_multi_level_bom = wo_doc.use_multi_level_bom
		se.wip_warehouse = wo_doc.wip_warehouse
		se.to_warehouse = wo_doc.fg_warehouse
		self._set_stock_entry_spr_link(se)
		self._set_stock_entry_unit(se, wo_doc)
		se.get_items()
		if spr_doc_is_bag_spr(self):
			_spr_apply_bag_rm_qty_from_bom(se, wo_doc.bom_no, se.fg_completed_qty)
		wip_warehouse = _cstr(getattr(wo_doc, "wip_warehouse", None))
		for item in se.items or []:
			if item.item_code and not item.get("t_warehouse"):
				item.s_warehouse = wip_warehouse
		return se

	def _raise_shortage_with_transfer(self, wo_id: str, wo_doc, chunk_total_qty: float, shortages):
		"""Create draft transfer, then throw a clear actionable shortage message."""
		transfer_name = ""
		transfer_err = ""
		try:
			transfer_name = self._create_wip_shortage_transfer_draft(wo_doc, chunk_total_qty, shortages)
			# Keep draft + submit atomic inside one request transaction.
		except Exception:
			transfer_err = _cstr(frappe.get_traceback())
			transfer_name = ""
		prec = _spr_rm_stock_qty_precision()
		lines = "\n".join(
			[
				_("{0} @ {1}: required {2}, available {3}, shortage {4}").format(
					it, wh or "—", flt(req, prec), flt(avl, prec), flt(sh, prec)
				)
				for it, wh, req, avl, sh in shortages[:20]
			]
		)
		next_steps = _(
			"1) Submit shortage transfer (each RM source warehouse -> WIP).\n"
			"2) Return to SPR and submit again."
		)
		if transfer_name:
			verify_line = (
				"2) Verify each line: source = item WO Required Items warehouse, target = WIP, qty in Kg matches WO.\n"
				if spr_doc_is_bag_spr(self)
				else "2) Verify source warehouse = Raw Materials and target warehouse = WIP, then submit.\n"
			)
			next_steps = _(
				'1) Open draft transfer: <a href="/app/stock-entry/{0}" target="_blank">{0}</a> '
				'(/app/stock-entry/{0})\n'
				"{1}"
				'3) Return to SPR: <a href="/app/shaft-production-run/{2}" target="_blank">{2}</a> and submit again.'
			).format(transfer_name, verify_line, self.name)
		elif transfer_err:
			next_steps = _(
				"Could not auto-create draft transfer on this site. "
				"Create 'Material Transfer for Manufacture' manually (Raw Materials -> WIP), submit it, then submit SPR again."
			)
		frappe.throw(
			_("Insufficient WIP stock for WO {0}.\n\n{1}\n\n{2}").format(wo_id, lines, next_steps),
			title=_("Insufficient stock"),
		)

	def _consolidated_shortage_lines(self, shortage_events) -> str:
		"""One line per item across all WOs (RM -> WIP)."""
		ctx = self._spr_company_warehouse_ctx()
		rm_wh = _cstr(ctx.get("source_warehouse")) or _("RM warehouse")
		wip_wh = _cstr(ctx.get("wip_warehouse")) or _("WIP warehouse")
		prec = _spr_rm_stock_qty_precision()
		merged: dict[str, dict] = {}
		for event in shortage_events or []:
			for item_code, _wh, req, avl, short_qty in event.get("shortages") or []:
				ic = _cstr(item_code).strip()
				if not ic:
					continue
				row = merged.setdefault(ic, {"req": 0.0, "avl": 0.0, "short": 0.0})
				row["req"] += flt(req)
				row["avl"] += flt(avl)
				row["short"] += flt(short_qty)
		if not merged:
			return ""
		lines = []
		for ic, row in sorted(merged.items()):
			lines.append(
				_(
					"{0}: move {1} from {2} to {3} (required {4}, available {5}, shortage {6})"
				).format(
					ic,
					flt(row["short"], prec),
					rm_wh,
					wip_wh,
					flt(row["req"], prec),
					flt(row["avl"], prec),
					flt(row["short"], prec),
				)
			)
		return "\n".join(lines)

	def _spr_no_rm_stock_lines_for_shortage_events(self, shortage_events) -> str:
		"""Items with WIP shortage but zero RM warehouse stock — operator must receive RM first."""
		prec = _spr_rm_stock_qty_precision()
		lines = []
		seen: set[str] = set()
		for event in shortage_events or []:
			wo_doc = self._reload_work_order_doc(event.get("wo_doc"))
			if not wo_doc:
				continue
			company = _cstr(getattr(wo_doc, "company", None))
			wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None))
			for item_code, wh, _req, _avl, short_qty in event.get("shortages") or []:
				ic = _cstr(item_code).strip()
				if not ic or ic in seen:
					continue
				need = _spr_wip_topup_bump_qty(short_qty)
				tol = _spr_rm_wip_shortage_tolerance(need)
				item_src = self._resolve_rm_source_warehouse_for_transfer(wo_doc, ic, wip_wh)
				rm_wh, rm_avl = _spr_find_rm_warehouse_with_stock(company, ic, wip_wh, item_src, need)
				if rm_avl + tol >= need:
					continue
				seen.add(ic)
				lines.append(
					_("{0}: need {1} Kg in RM store ({2}) — available {3} Kg").format(
						ic,
						flt(need, prec),
						rm_wh or wh or _("RM warehouse"),
						flt(rm_avl, prec),
					)
				)
		return "\n".join(lines[:20])

	def _raise_shortage_with_transfer_batch(
		self, shortage_events, ignore_wo_transfer_prune: bool = False
	):
		"""Create one combined transfer for all shortages, then raise actionable message."""
		if not shortage_events:
			return
		if not ignore_wo_transfer_prune:
			shortage_events = self._filter_shortage_events_by_wo_transfer(shortage_events)
			if not shortage_events:
				return
		consolidated = self._consolidated_shortage_lines(shortage_events)

		transfer_name = ""
		try:
			# Clear rolled-back Manufacture state so draft insert can commit cleanly.
			frappe.db.commit()
		except Exception:
			pass
		try:
			transfer_name = self._create_combined_spr_shortage_transfer_draft(
				shortage_events, ignore_wo_transfer_prune=ignore_wo_transfer_prune
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"SPR combined shortage draft:{self.name}")
			transfer_name = ""
		if not transfer_name:
			transfer_name = self._find_open_spr_shortage_transfer_draft()
		if not transfer_name:
			wo_ids = sorted({_cstr(e.get("wo_id")) for e in shortage_events if _cstr(e.get("wo_id"))})
			for wo_id in wo_ids:
				transfer_name = self._find_recent_spr_wo_mtfm_transfer(wo_id)
				if transfer_name:
					break

		try:
			frappe.db.commit()
		except Exception:
			pass

		# After MTFM insert/submit, reload WO + WIP bins — do not block if shortage is already resolved.
		still_blocking = self._shortage_events_still_blocking(shortage_events)
		if not still_blocking:
			return

		transfer_submitted = False
		if transfer_name:
			transfer_submitted = cint(frappe.db.get_value("Stock Entry", transfer_name, "docstatus")) == 1

		if transfer_name and transfer_submitted:
			next_steps = _(
				'Material Transfer for Manufacture <a href="/app/stock-entry/{0}" target="_blank">{0}</a> '
				"was created and submitted (RM -> WIP).\n"
				'Return to SPR <a href="/app/shaft-production-run/{1}" target="_blank">{1}</a> and submit again.'
			).format(transfer_name, self.name)
		elif transfer_name:
			next_steps = _(
				'1) Open Material Transfer for Manufacture: '
				'<a href="/app/stock-entry/{0}" target="_blank">{0}</a>\n'
				"2) Verify each line: source = company RM warehouse, target = company WIP warehouse.\n"
				"3) Submit the Stock Entry (auto-submit failed — likely insufficient RM stock), then submit SPR again."
			).format(transfer_name)
		else:
			last_err = _cstr(getattr(self, "_spr_last_mtfm_error", None)).strip()
			if last_err:
				next_steps = _(
					"Auto-transfer failed: {0}\n\n"
					"Create one 'Material Transfer for Manufacture' (company RM -> company WIP) "
					"with all shortage items, submit it, then submit SPR again."
				).format(last_err[:800])
			else:
				next_steps = _(
					"Could not auto-create transfer on this site. "
					"Create one 'Material Transfer for Manufacture' (company RM -> company WIP) with all shortage items, submit it, then submit SPR again."
				)

		body = consolidated or _("No shortage detail available.")
		no_stock_lines = self._spr_no_rm_stock_lines_for_shortage_events(shortage_events)
		if no_stock_lines and not transfer_submitted:
			body = _("{0}\n\nNo stock in RM warehouse until you transfer:\n{1}").format(
				body, no_stock_lines
			)
		frappe.throw(
			_(
				"Insufficient stock for {0} work order(s).\n\n{1}\n\n{2}"
			).format(len(still_blocking), body, next_steps),
			title=_("Insufficient stock"),
		)

	def _manufacture_stock_entry_type_name(self) -> str:
		"""Resolve a valid Stock Entry Type name for Manufacture purpose."""
		# Prefer exact standard type label only when its mapped purpose is truly Manufacture.
		if frappe.db.exists("Stock Entry Type", "Manufacture"):
			p = _cstr(frappe.db.get_value("Stock Entry Type", "Manufacture", "purpose"))
			if p == "Manufacture":
				return "Manufacture"
		name = frappe.db.get_value("Stock Entry Type", {"purpose": "Manufacture"}, "name")
		if name:
			return _cstr(name)
		# Mandatory field on this site: fail fast with explicit setup message.
		frappe.throw(
			_(
				"Cannot create SPR Manufacture entry because no Stock Entry Type is mapped to purpose "
				"'Manufacture'. Please configure one in Stock Entry Type master."
			),
			title=_("Missing Manufacture Stock Entry Type"),
		)
		return ""

	def _stock_entry_type_name_for_purpose(self, purpose: str) -> str:
		"""Resolve a valid Stock Entry Type name for the given purpose."""
		purpose = _cstr(purpose)
		if not purpose:
			return ""
		if frappe.db.exists("Stock Entry Type", purpose):
			p = _cstr(frappe.db.get_value("Stock Entry Type", purpose, "purpose"))
			if p == purpose:
				return purpose
		name = frappe.db.get_value("Stock Entry Type", {"purpose": purpose}, "name")
		if name:
			return _cstr(name)
		frappe.throw(
			_(
				"Cannot create Stock Entry because no Stock Entry Type is mapped to purpose '{0}'. "
				"Please configure one in Stock Entry Type master."
			).format(purpose),
			title=_("Missing Stock Entry Type"),
		)
		return ""

	def _strip_finished_goods_from_stock_entry(self, se):
		"""Remove FG rows from BOM-generated Stock Entry and return them as templates."""
		items = se.get("items") or []
		fg_templates = []
		for i in range(len(items) - 1, -1, -1):
			if getattr(items[i], "is_finished_item", 0):
				try:
					fg_templates.append(items[i].as_dict(no_default_fields=False))
				except Exception:
					fg_templates.append(dict(items[i].as_dict()))
				se.items.pop(i)
		fg_templates.reverse()
		return fg_templates

	def _get_batch_link_name_for_stock_entry(
		self,
		batch_id: str,
		item_code: str,
		company: str | None,
		spr_row=None,
	) -> str:
		"""
		Return tabBatch.name for Stock Entry Detail `batch_no` (Link).
		Frappe's savedocs validates every Link: the value must exist as Batch.name before insert().
		ERPNext Batch.autoname sets name = batch_id when batch_id is provided; use ERPNext make_batch when available.
		``spr_row`` fills Batch mandatory custom fields (net/gross weight, length) from the roll line.
		"""
		bid = _cstr(batch_id)
		if not bid:
			return ""

		batch_meta = frappe.get_meta("Batch")
		is_bag = spr_doc_is_bag_spr(self)
		roll_batch_data = _batch_fields_from_spr_row(batch_meta, spr_row, is_bag_spr=is_bag)

		def _existing_name() -> str | None:
			if frappe.db.exists("Batch", bid):
				it = frappe.db.get_value("Batch", bid, "item")
				if it == item_code:
					return bid
			nm = frappe.db.get_value(
				"Batch",
				{"item": item_code, "batch_id": bid},
				"name",
			)
			if nm:
				return nm
			return frappe.db.get_value("Batch", {"batch_id": bid, "item": item_code}, "name")

		found = _existing_name()
		if found:
			if roll_batch_data:
				try:
					frappe.db.set_value("Batch", found, roll_batch_data)
				except Exception:
					frappe.log_error(frappe.get_traceback(), "SPR Batch roll fields on existing Batch")
			return found

		try:
			from erpnext.stock.doctype.batch.batch import make_batch

			kw = frappe._dict(
				item=item_code,
				batch_id=bid,
				manufacturing_date=self.run_date or today(),
			)
			if company:
				if batch_meta.has_field("company"):
					kw.company = company
			for fk, fv in roll_batch_data.items():
				kw[fk] = fv
			mb = make_batch(kw)
			if mb:
				return mb
		except ImportError:
			pass
		except Exception:
			found = _existing_name()
			if found:
				return found

		b = frappe.new_doc("Batch")
		b.batch_id = bid
		b.item = item_code
		if batch_meta.has_field("company") and company:
			b.company = company
		if batch_meta.has_field("manufacturing_date"):
			b.manufacturing_date = self.run_date or today()
		for fk, fv in roll_batch_data.items():
			b.set(fk, fv)
		try:
			b.insert(ignore_permissions=True)
			return b.name
		except Exception:
			found = _existing_name()
			if found:
				return found
			raise

	def _bundle_roll_numbers_from_text(self, raw_value) -> list[str]:
		"""Parse Bundle Stickers.roll_numbers into stable roll number strings."""
		out = []
		seen = set()
		for part in re.split(r"[,;\s]+", _cstr(raw_value)):
			val = part.strip()
			if not val:
				continue
			try:
				val = str(cint(val)) if str(cint(val)) == val or val.isdigit() else val
			except Exception:
				pass
			if val not in seen:
				seen.add(val)
				out.append(val)
		return out

	def _roll_batch_prefix_and_no(self, row) -> tuple[str, str]:
		bn = _cstr(row.get("batch_no"))
		rn = _cstr(row.get("roll_no"))
		prefix = ""
		batch_roll = ""
		if "/" in bn:
			prefix, batch_roll = [x.strip() for x in bn.rsplit("/", 1)]
		elif bn:
			prefix = bn
		return prefix, rn or batch_roll

	def _bundle_batch_id(self, sticker_row, roll_numbers: list[str]) -> str:
		raw_batch_no = _cstr(sticker_row.get("batch_no"))
		if re.match(r"^.+-B\d+(?:-\d+-\d+)?$", raw_batch_no):
			return raw_batch_no
		prefix = _spr_bundle_source_batch_prefix(raw_batch_no)
		if not prefix:
			return ""
		return f"{prefix}-B{cint(sticker_row.get('idx') or 0) or 1}"

	def _spr_submit_uses_bundle_packaging(self) -> bool:
		"""When True, Manufacture FG uses Bundle Stickers (combined) then unpacked rolls; when False, one FG per roll."""
		if frappe.db.has_column("Shaft Production Run", "custom_use_bundle_packaging_on_submit"):
			return cint(self.get("custom_use_bundle_packaging_on_submit") or 0) == 1
		return False

	def _bundle_fg_plans(self) -> list[dict]:
		"""Build bundle FG rows from Bundle Stickers and map them to source roll rows."""
		if not self._spr_submit_uses_bundle_packaging():
			return []
		plans = []
		used_roll_names = {}
		rows = list(self.items or [])
		row_by_key = {}
		for row in rows:
			prefix, roll_no = self._roll_batch_prefix_and_no(row)
			if prefix and roll_no:
				row_by_key[(prefix, roll_no)] = row

		for sticker in self.bundle_stickers or []:
			prefix = _spr_bundle_source_batch_prefix(sticker.get("batch_no"))
			roll_numbers = self._bundle_roll_numbers_from_text(sticker.get("roll_numbers"))
			if not prefix or not roll_numbers:
				continue

			source_rows = []
			missing = []
			for rn in roll_numbers:
				row = row_by_key.get((prefix, rn))
				if not row:
					missing.append(rn)
					continue
				source_rows.append(row)
			if missing:
				frappe.throw(
					_("Bundle Sticker row {0}: roll number(s) {1} not found for batch {2}.").format(
						cint(sticker.get("idx") or 0) or "?", ", ".join(missing), prefix
					),
					title=_("Bundle roll mismatch"),
				)

			for row in source_rows:
				row_name = _cstr(row.get("name"))
				if row_name in used_roll_names:
					frappe.throw(
						_("Roll {0} is included in more than one bundle sticker row ({1} and {2}).").format(
							row.get("roll_no") or row.get("batch_no"),
							used_roll_names[row_name],
							sticker.get("idx"),
						),
						title=_("Duplicate bundled roll"),
					)
				used_roll_names[row_name] = sticker.get("idx")

			work_orders = {_cstr(r.get("work_order") or r.get("wo_id")) for r in source_rows}
			work_orders.discard("")
			item_codes = {_cstr(r.get("item_code")) for r in source_rows}
			item_codes.discard("")
			if len(work_orders) > 1 or len(item_codes) > 1:
				frappe.throw(
					_("Bundle Sticker row {0} mixes Work Orders or items. Pack one Work Order/item per bundle.").format(
						cint(sticker.get("idx") or 0) or "?"
					),
					title=_("Invalid bundle"),
				)

			source_net = flt(sum(self._row_fg_qty(r) for r in source_rows), 2)
			source_gross = flt(sum(flt(r.get("gross_weight")) for r in source_rows), 2)
			bundle_net = flt(sticker.get("sticker_bundle_weight") or source_net, 2)
			source_order_code = ""
			for r in source_rows:
				source_order_code = (
					_cstr(r.get("custom_order_code"))
					or _cstr(r.get("order_code"))
					or _cstr(r.get("custom_party_code_text"))
					or _cstr(r.get("party_code"))
				)
				if source_order_code:
					break
			if abs(bundle_net - source_net) > 0.05:
				frappe.throw(
					_("Bundle Sticker row {0}: bundle net {1} Kg does not match selected roll net {2} Kg.").format(
						cint(sticker.get("idx") or 0) or "?", bundle_net, source_net
					),
					title=_("Bundle weight mismatch"),
				)

			plans.append(
				{
					"source_rows": source_rows,
					"source_names": {_cstr(r.get("name")) for r in source_rows},
					"first_idx": min([cint(r.get("idx") or 0) for r in source_rows] or [0]),
					"work_order": next(iter(work_orders), ""),
					"item_code": next(iter(item_codes), ""),
					"batch_no": self._bundle_batch_id(sticker, roll_numbers),
					"net_weight": bundle_net,
					"gross_weight": flt(sticker.get("sticker_bundle_gross_weight_kg") or source_gross, 2),
					"produced_length_mtrs": flt(
						sticker.get("produced_length_mtrs")
						or sticker.get("custom_produced_length_mtrs")
						or 0
					),
					"roll_numbers": ", ".join(roll_numbers),
					"order_code": source_order_code,
					"party_code": source_order_code,
					"custom_party_code_text": source_order_code,
					"bundle_sticker_idx": sticker.get("idx"),
				}
			)
		return plans

	def _fg_posting_units_for_rows(self, spr_rows: list, wo_doc) -> list:
		"""Return FG posting units: bundles first (when enabled), then individual roll lines."""
		chunk_names = {_cstr(r.get("name")) for r in spr_rows or []}
		units = []
		covered = set()
		use_bundles = self._spr_submit_uses_bundle_packaging()
		for plan in self._bundle_fg_plans() if use_bundles else []:
			if _cstr(plan.get("work_order")) != _cstr(getattr(wo_doc, "name", "")):
				continue
			src = set(plan.get("source_names") or set())
			overlap = src & chunk_names
			if not overlap:
				continue
			if overlap != src:
				frappe.throw(
					_("Bundle Sticker row {0} was split across Stock Entry chunks. Reduce bundle size or increase WO overproduction allowance.").format(
						plan.get("bundle_sticker_idx") or "?"
					),
					title=_("Bundle split blocked"),
				)
			covered.update(src)
			units.append({"sort_idx": plan.get("first_idx") or 0, "row": plan, "is_bundle": True})

		for row in spr_rows or []:
			if _cstr(row.get("name")) in covered:
				continue
			units.append({"sort_idx": cint(row.get("idx") or 0), "row": row, "is_bundle": False})
		# Bundle FG lines first, then unpacked rolls (same sort_idx group).
		units.sort(key=lambda x: (cint(x.get("sort_idx") or 0), 0 if x.get("is_bundle") else 1))
		return [u["row"] for u in units]

	def _fg_posting_qty_for_rows(self, spr_rows: list, wo_doc) -> float:
		if spr_doc_is_bag_spr(self):
			bag_total = self._spr_bag_fg_posting_qty_for_wo(wo_doc, spr_rows)
			if bag_total > 0:
				return bag_total
		return sum(flt(self._row_fg_qty(unit)) for unit in self._fg_posting_units_for_rows(spr_rows, wo_doc))

	def _append_manufacture_fg_from_spr_rolls(self, se, wo_doc, spr_rows: list, fg_templates=None):
		"""Append FG rows: normal rolls individually, packed rolls as one Bundle Stickers row."""
		item_code = wo_doc.production_item
		has_batch = cint(frappe.db.get_value("Item", item_code, "has_batch_no"))
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Kg"
		item_name = frappe.db.get_value("Item", item_code, "item_name")
		fg_templates = list(fg_templates or [])
		base_template = None
		for tpl in fg_templates:
			if _cstr(tpl.get("item_code")) == _cstr(item_code):
				base_template = tpl
				break
		if base_template is None and fg_templates:
			base_template = fg_templates[0]

		for spr in self._fg_posting_units_for_rows(spr_rows, wo_doc):
			qty = self._row_fg_qty(spr)
			if qty <= 0:
				continue
			bn_raw = spr.get("batch_no")
			bn = _cstr(bn_raw) if bn_raw is not None else ""
			if has_batch:
				if not bn:
					frappe.throw(
						_("Batch No is required on each roll line for batch-tracked item {0}").format(
							item_code
						),
						title=_("Missing Batch"),
					)
				se_batch = self._get_batch_link_name_for_stock_entry(
					bn, item_code, wo_doc.company, spr
				)
				if not se_batch:
					frappe.throw(
						_("Could not resolve Batch master for batch id {0}").format(bn),
						title=_("Batch"),
					)
			else:
				se_batch = ""

			row = {}
			if base_template:
				row.update(
					{
						k: v
						for k, v in base_template.items()
						if k
						not in {
							"name",
							"parent",
							"parenttype",
							"parentfield",
							"idx",
							"owner",
							"creation",
							"modified",
							"modified_by",
							"docstatus",
						}
					}
				)
			row.update(
				{
					"item_code": item_code,
					"item_name": item_name,
					"qty": qty,
					"transfer_qty": qty,
					"uom": row.get("uom") or stock_uom,
					"stock_uom": row.get("stock_uom") or stock_uom,
					"conversion_factor": flt(row.get("conversion_factor") or 1),
					"t_warehouse": wo_doc.fg_warehouse,
					"s_warehouse": "",
					"is_finished_item": 1,
				}
			)
			if has_batch and se_batch:
				row["batch_no"] = se_batch
			elif "batch_no" in row:
				row["batch_no"] = ""
			se.append("items", row)

	def _wo_submitted_manufacture_fg_qty(self, wo_id: str) -> float:
		"""Submitted Manufacture FG qty already posted against this WO."""
		if not wo_id:
			return 0.0
		return flt(
			frappe.db.sql(
				"""
				SELECT IFNULL(SUM(fg_completed_qty), 0)
				FROM `tabStock Entry`
				WHERE work_order = %s
				  AND IFNULL(purpose, '') = 'Manufacture'
				  AND docstatus = 1
				""",
				wo_id,
			)[0][0]
		)

	def _wo_overproduction_percent(self) -> float:
		"""Work Order overproduction allowance from Manufacturing Settings (safe fallback = 0)."""
		try:
			p = frappe.db.get_single_value("Manufacturing Settings", "overproduction_percentage_for_work_order")
			return max(flt(p), 0.0)
		except Exception:
			return 0.0

	def _wo_allowed_remaining_qty(self, wo_doc) -> tuple[float, float, float, float]:
		"""Return remaining allowed qty, allowed total, produced so far, overproduction %."""
		base_qty = flt(getattr(wo_doc, "qty", 0))
		over_pct = self._wo_overproduction_percent()
		allowed_total = base_qty * (1.0 + (over_pct / 100.0))
		already = max(flt(getattr(wo_doc, "produced_qty", 0)), self._wo_submitted_manufacture_fg_qty(wo_doc.name))
		remaining = max(allowed_total - already, 0.0)
		return remaining, allowed_total, already, over_pct

	def _wo_allowed_entry_qty(self, wo_doc) -> tuple[float, float]:
		"""Per-entry allowed FG qty from WO qty + Manufacturing Settings overproduction %."""
		base_qty = flt(getattr(wo_doc, "qty", 0))
		over_pct = self._wo_overproduction_percent()
		allowed = base_qty * (1.0 + (over_pct / 100.0))
		return flt(allowed), flt(over_pct)

	def _split_rows_by_qty_limit(self, rows: list, qty_limit: float) -> list[list]:
		"""Split SPR rows into chunks where sum(_row_fg_qty) <= qty_limit."""
		if qty_limit <= 0:
			return [rows]
		chunks: list[list] = []
		cur: list = []
		cur_total = 0.0
		for r in rows:
			q = flt(self._row_fg_qty(r))
			if q <= 0:
				continue
			# Single row bigger than per-entry limit cannot be split safely.
			if q > qty_limit + 1e-9:
				wo_id = _cstr(r.get("work_order") or r.get("wo_id"))
				frappe.throw(
					_(
						"Single roll row for WO {0} has qty {1} Kg, above per-entry allowed {2} Kg. "
						"Adjust roll qty/WO qty or overproduction %."
					).format(wo_id or "—", flt(q, 3), flt(qty_limit, 3)),
					title=_("WO quantity exceeded"),
				)
			if cur and (cur_total + q) > qty_limit + 1e-9:
				chunks.append(cur)
				cur = []
				cur_total = 0.0
			cur.append(r)
			cur_total += q
		if cur:
			chunks.append(cur)
		return chunks

	def _build_expected_rm_map_for_qty(self, wo_doc, fg_qty: float) -> dict[str, float]:
		"""Expected RM consumption map for a WO at given FG qty (item_code -> transfer_qty).

		Must use the **same** Stock Entry inputs as ``create_manufacturing_stock_entries`` before
		``get_items()``: ``work_order`` is left blank so ERPNext builds RM from BOM × ``fg_completed_qty``
		identically to submitted Manufacture entries. Setting ``work_order`` here would use a different
		validation/backflush path and skew split-entry variance checks. This doc is never inserted.
		"""
		fg_qty = flt(fg_qty)
		if fg_qty <= 0:
			return {}
		se = frappe.new_doc("Stock Entry")
		se.company = wo_doc.company
		se.posting_date = today()
		se.posting_time = nowtime()
		se.set_posting_time = 1
		se.stock_entry_type = self._manufacture_stock_entry_type_name()
		se.purpose = "Manufacture"
		# Match submitted SPR Manufacture entries: WO linked only after submit, not during get_items().
		se.work_order = None
		se.production_item = wo_doc.production_item
		se.fg_completed_qty = fg_qty
		se.from_bom = 1
		se.bom_no = wo_doc.bom_no
		se.use_multi_level_bom = wo_doc.use_multi_level_bom
		se.wip_warehouse = wo_doc.wip_warehouse
		se.to_warehouse = wo_doc.fg_warehouse
		se.get_items()
		if spr_doc_is_bag_spr(self):
			_spr_apply_bag_rm_qty_from_bom(se, wo_doc.bom_no, fg_qty)
		rm = defaultdict(float)
		for d in se.items or []:
			if d.item_code and not d.get("t_warehouse"):
				rm[d.item_code] += flt(d.get("transfer_qty") or d.get("qty"))
		return dict(rm)

	def _collect_rm_map_from_se(self, se) -> dict[str, float]:
		"""Actual RM map from generated Stock Entry items (item_code -> transfer_qty)."""
		rm = defaultdict(float)
		for d in se.items or []:
			if d.item_code and not d.get("t_warehouse"):
				rm[d.item_code] += flt(d.get("transfer_qty") or d.get("qty"))
		return dict(rm)

	def _merge_rm_maps(self, target: dict[str, float], delta: dict[str, float]) -> dict[str, float]:
		for item_code, qty in (delta or {}).items():
			target[item_code] = flt(target.get(item_code)) + flt(qty)
		return target

	def _validate_rm_split_variance(
		self,
		wo_id: str,
		fg_total_qty: float,
		expected_rm: dict[str, float],
		actual_rm: dict[str, float],
		wo_doc=None,
	):
		"""Ensure split-entry RM consumption matches BOM-expected RM for this FG qty (same path as phantom SE)."""
		under_consume: dict[str, float] = {}
		issues = []
		for item_code in sorted(set(expected_rm or {}) | set(actual_rm or {})):
			exp = flt((expected_rm or {}).get(item_code))
			act = flt((actual_rm or {}).get(item_code))
			diff = abs(act - exp)
			threshold = max(0.01, abs(exp) * 0.001)  # 0.1% or 0.01 qty floor
			if diff <= threshold + 1e-9:
				continue
			if act < exp - threshold:
				under_consume[_cstr(item_code).strip()] = _spr_wip_topup_bump_qty(exp - act)
			else:
				issues.append((item_code, exp, act, act - exp, threshold))
		if under_consume and wo_doc:
			shortage_events = [
				{
					"wo_id": wo_id,
					"wo_doc": wo_doc,
					"chunk_total_qty": fg_total_qty,
					"shortages": [
						(
							ic,
							self._resolve_rm_source_warehouse_for_transfer(
								wo_doc, ic, _cstr(getattr(wo_doc, "wip_warehouse", None))
							)
							or _spr_company_rm_warehouse(
								_cstr(getattr(wo_doc, "company", None)),
								_cstr(getattr(wo_doc, "wip_warehouse", None)),
							)
							or _("RM warehouse"),
							flt((expected_rm or {}).get(ic)),
							flt((actual_rm or {}).get(ic)),
							qty,
						)
						for ic, qty in under_consume.items()
						if ic and qty > 0
					],
					"wip_topup": True,
				}
			]
			self._raise_shortage_with_transfer_batch(shortage_events, ignore_wo_transfer_prune=True)
		if not issues:
			return
		details = "\n".join(
			[
				_("{0}: expected {1}, actual {2}, delta {3}, tolerance {4}").format(
					it, flt(exp, 6), flt(act, 6), flt(delta, 6), flt(tol, 6)
				)
				for it, exp, act, delta, tol in issues[:20]
			]
		)
		frappe.throw(
			_(
				"RM consumption mismatch for WO {0} (FG qty {1}) after split Manufacture entries. "
				"Submission aborted for safety.\n\n{2}"
			).format(wo_id, flt(fg_total_qty, 3), details),
			title=_("RM split variance"),
		)

	def _validate_fg_roll_coverage_for_wo(self, wo_doc, spr_rows: list, se_names: list[str]):
		"""Hard guard: every produced SPR FG roll must be represented in submitted Manufacture entries."""
		if not wo_doc or not se_names:
			return
		item_code = _cstr(getattr(wo_doc, "production_item", None))
		if not item_code:
			return
		has_batch = cint(frappe.db.get_value("Item", item_code, "has_batch_no"))
		expected_total = 0.0
		expected_by_batch = defaultdict(float)
		for spr in self._fg_posting_units_for_rows(spr_rows, wo_doc):
			qty = flt(self._row_fg_qty(spr))
			if qty <= 0:
				continue
			expected_total += qty
			if has_batch:
				bn_raw = _cstr(spr.get("batch_no"))
				if not bn_raw:
					continue
				se_batch = self._get_batch_link_name_for_stock_entry(bn_raw, item_code, wo_doc.company, spr)
				if se_batch:
					expected_by_batch[_cstr(se_batch)] += qty
		rows = frappe.db.sql(
			"""
			SELECT IFNULL(sed.batch_no, '') AS batch_no, IFNULL(sed.qty, 0) AS qty
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE sed.parent IN %(parents)s
			  AND IFNULL(se.docstatus, 0) = 1
			  AND IFNULL(se.purpose, '') = 'Manufacture'
			  AND IFNULL(sed.is_finished_item, 0) = 1
			  AND sed.item_code = %(item_code)s
			""",
			{"parents": tuple(se_names), "item_code": item_code},
			as_dict=True,
		) or []
		actual_total = 0.0
		actual_by_batch = defaultdict(float)
		for r in rows:
			q = flt(r.get("qty"))
			actual_total += q
			b = _cstr(r.get("batch_no"))
			if b:
				actual_by_batch[b] += q
		if abs(expected_total - actual_total) > 1e-6:
			frappe.throw(
				_(
					"WO {0}: SPR roll total {1} Kg but submitted Manufacture entries total {2} Kg. "
					"Rollback to prevent missed roll posting."
				).format(wo_doc.name, flt(expected_total, 3), flt(actual_total, 3)),
				title=_("FG roll coverage mismatch"),
			)
		if has_batch:
			missing_batches = []
			for b, exp in expected_by_batch.items():
				act = flt(actual_by_batch.get(b))
				if abs(exp - act) > 1e-6:
					missing_batches.append((b, exp, act))
			if missing_batches:
				details = "\n".join(
					[_("Batch {0}: expected {1} Kg, posted {2} Kg").format(b, flt(e, 3), flt(a, 3)) for b, e, a in missing_batches[:20]]
				)
				frappe.throw(
					_(
						"WO {0}: some produced roll batches were not fully posted to Manufacture entries.\n\n{1}"
					).format(wo_doc.name, details),
					title=_("Missing FG roll batches"),
				)

	def _sync_work_order_produced_qty_from_submitted_manufacture(self, wo_id: str):
		"""Recompute WO produced_qty from submitted Manufacture entries."""
		if not wo_id:
			return
		total = flt(
			frappe.db.sql(
				"""
				SELECT IFNULL(SUM(fg_completed_qty), 0)
				FROM `tabStock Entry`
				WHERE work_order = %s
				  AND IFNULL(purpose, '') = 'Manufacture'
				  AND docstatus = 1
				""",
				wo_id,
			)[0][0]
		)
		frappe.db.set_value("Work Order", wo_id, "produced_qty", total, update_modified=False)

	def _sync_work_order_required_item_progress(self, wo_id: str):
		"""Recompute WO required-items consumed/transferred qty from submitted Stock Entries."""
		if not wo_id or not frappe.db.exists("Work Order", wo_id):
			return
		wo_meta = frappe.get_meta("Work Order")
		if not wo_meta.has_field("required_items"):
			return
		req_df = wo_meta.get_field("required_items")
		req_dt = _cstr(getattr(req_df, "options", None))
		if not req_dt:
			return
		req_meta = frappe.get_meta(req_dt)
		if not req_meta.has_field("item_code"):
			return

		consumed_map = {}
		try:
			rows = frappe.db.sql(
				"""
				SELECT sed.item_code, IFNULL(SUM(IFNULL(sed.transfer_qty, sed.qty)), 0) AS qty
				FROM `tabStock Entry` se
				INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
				WHERE se.work_order = %(wo)s
				  AND se.docstatus = 1
				  AND IFNULL(se.purpose, '') IN ('Manufacture', 'Material Consumption for Manufacture')
				  AND IFNULL(sed.s_warehouse, '') != ''
				  AND IFNULL(sed.t_warehouse, '') = ''
				GROUP BY sed.item_code
				""",
				{"wo": wo_id},
				as_dict=True,
			) or []
			consumed_map = {_cstr(r.item_code): flt(r.qty) for r in rows if _cstr(r.item_code)}
		except Exception:
			consumed_map = {}

		transferred_map = {}
		try:
			rows = frappe.db.sql(
				"""
				SELECT sed.item_code, IFNULL(SUM(IFNULL(sed.transfer_qty, sed.qty)), 0) AS qty
				FROM `tabStock Entry` se
				INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
				WHERE se.work_order = %(wo)s
				  AND se.docstatus = 1
				  AND IFNULL(se.purpose, '') = 'Material Transfer for Manufacture'
				  AND IFNULL(sed.s_warehouse, '') != ''
				  AND IFNULL(sed.t_warehouse, '') != ''
				GROUP BY sed.item_code
				""",
				{"wo": wo_id},
				as_dict=True,
			) or []
			transferred_map = {_cstr(r.item_code): flt(r.qty) for r in rows if _cstr(r.item_code)}
		except Exception:
			transferred_map = {}

		wo_doc = frappe.get_doc("Work Order", wo_id)
		for row in wo_doc.get("required_items") or []:
			item_code = _cstr(getattr(row, "item_code", None))
			if not item_code:
				continue
			if req_meta.has_field("consumed_qty"):
				next_consumed = flt(consumed_map.get(item_code, 0))
				if abs(flt(getattr(row, "consumed_qty", 0)) - next_consumed) > 1e-9:
					frappe.db.set_value(req_dt, row.name, "consumed_qty", next_consumed, update_modified=False)
			if req_meta.has_field("transferred_qty"):
				next_transferred = flt(transferred_map.get(item_code, 0))
				if abs(flt(getattr(row, "transferred_qty", 0)) - next_transferred) > 1e-9:
					frappe.db.set_value(req_dt, row.name, "transferred_qty", next_transferred, update_modified=False)

	def _sync_production_plan_progress_from_work_orders(self, production_plan: str):
		"""Sync Production Plan item/header produced qty from Work Order produced_qty."""
		pp = _cstr(production_plan)
		if not pp or not frappe.db.exists("Production Plan", pp):
			return
		pp_meta = frappe.get_meta("Production Plan")
		ppi_meta = frappe.get_meta("Production Plan Item")
		ppi_has_produced = ppi_meta.has_field("produced_qty")
		pp_rows = frappe.get_all(
			"Production Plan Item",
			filters={"parent": pp, "parenttype": "Production Plan", "parentfield": "po_items"},
			fields=["name", "item_code", "produced_qty"] if ppi_has_produced else ["name", "item_code"],
		) or []
		if not pp_rows:
			return
		wo_rows = frappe.get_all(
			"Work Order",
			filters={"production_plan": pp, "docstatus": ["<", 2]},
			fields=["name", "production_plan_item", "production_item", "produced_qty"],
		) or []
		produced_by_ppi = defaultdict(float)
		produced_by_item = defaultdict(float)
		for wo in wo_rows:
			produced = flt(wo.get("produced_qty"))
			ppi = _cstr(wo.get("production_plan_item"))
			item_code = _cstr(wo.get("production_item"))
			if ppi:
				produced_by_ppi[ppi] += produced
			elif item_code:
				produced_by_item[item_code] += produced
		pp_item_code_count = defaultdict(int)
		for pr in pp_rows:
			pp_item_code_count[_cstr(pr.get("item_code"))] += 1
		total_produced = 0.0
		for pr in pp_rows:
			row_name = _cstr(pr.get("name"))
			item_code = _cstr(pr.get("item_code"))
			next_val = produced_by_ppi.get(row_name)
			if next_val is None and item_code and pp_item_code_count.get(item_code) == 1:
				next_val = produced_by_item.get(item_code, 0.0)
			if next_val is None:
				next_val = 0.0
			next_val = flt(next_val, 3)
			total_produced += next_val
			if ppi_has_produced:
				cur_val = flt(pr.get("produced_qty"))
				if abs(cur_val - next_val) > 1e-9:
					frappe.db.set_value("Production Plan Item", row_name, "produced_qty", next_val, update_modified=False)
		for f in ("produced_qty", "total_produced_weight", "custom_total_produced_weight"):
			if pp_meta.has_field(f):
				cur = flt(frappe.db.get_value("Production Plan", pp, f) or 0)
				if abs(cur - total_produced) > 1e-9:
					frappe.db.set_value("Production Plan", pp, f, total_produced, update_modified=False)

	def _spr_run_manufacture_chunk_attempt(
		self,
		wo_id,
		wo_doc,
		chunk_rows,
		chunk_total_qty,
		chunk_idx,
		chunk_count,
		mfg_submit_savepoint,
		planned_wo_posts,
		actual_rm_map,
		created_entries,
		created_entries_by_wo,
		allow_wip_topup_retry: bool = True,
	):
		"""Build + submit one Manufacture Stock Entry; auto WIP top-up + retry when allowed."""
		se = frappe.new_doc("Stock Entry")
		se.flags.ignore_duplicate_for_work_order = True
		se.company = wo_doc.company
		se.posting_date = today()
		se.posting_time = nowtime()
		se.set_posting_time = 1
		se.stock_entry_type = self._manufacture_stock_entry_type_name()
		se.purpose = "Manufacture"
		se.work_order = None
		se.production_item = wo_doc.production_item
		se.fg_completed_qty = chunk_total_qty
		se.from_bom = 1
		se.bom_no = wo_doc.bom_no
		se.use_multi_level_bom = wo_doc.use_multi_level_bom
		se.wip_warehouse = wo_doc.wip_warehouse
		se.to_warehouse = wo_doc.fg_warehouse
		self._set_stock_entry_spr_link(se)
		self._set_stock_entry_unit(se, wo_doc)
		se.get_items()
		if spr_doc_is_bag_spr(self):
			_spr_apply_bag_rm_qty_from_bom(se, wo_doc.bom_no, chunk_total_qty)
		wip_warehouse = wo_doc.wip_warehouse
		for item in se.items or []:
			if not item.item_code:
				continue
			if not item.get("t_warehouse"):
				item.s_warehouse = wip_warehouse
				if item.s_warehouse != wip_warehouse:
					frappe.throw(
						_("Raw material {0} source warehouse is {1}, not {2}. ABORT.").format(
							item.item_code, item.s_warehouse, wip_warehouse
						),
						title=_("Warehouse Mismatch"),
					)
			elif item.t_warehouse != wo_doc.fg_warehouse:
				item.t_warehouse = wo_doc.fg_warehouse
		fg_templates = self._strip_finished_goods_from_stock_entry(se)
		self._append_manufacture_fg_from_spr_rolls(se, wo_doc, chunk_rows, fg_templates)
		self._spr_cap_manufacture_rm_lines_to_wip_available(se, wo_doc)
		self._assign_rm_batches_for_stock_entry(se, wo_id)
		self._spr_cap_manufacture_rm_lines_to_wip_available(se, wo_doc)
		self._spr_apply_stock_entry_item_accounts(se)
		se.stock_entry_type = self._manufacture_stock_entry_type_name()
		se.purpose = "Manufacture"
		se.insert()
		self._persist_stock_entry_spr_reference_db(se.name)
		if _cstr(se.purpose) != "Manufacture":
			frappe.throw(
				_("Stock Entry {0} resolved to purpose {1}; expected Manufacture.").format(
					se.name, _cstr(se.purpose) or "—"
				),
				title=_("Invalid Stock Entry purpose"),
			)
		se.reload()
		se.flags.ignore_duplicate_for_work_order = True
		self._set_stock_entry_spr_link(se)
		self._set_stock_entry_unit(se, wo_doc)
		self._apply_unit_to_submitted_stock_entry(se.name, wo_doc)
		if _cstr(se.purpose) != "Manufacture":
			frappe.throw(
				_("Stock Entry {0} changed to purpose {1} after insert; expected Manufacture.").format(
					se.name, _cstr(se.purpose) or "—"
				),
				title=_("Invalid Stock Entry purpose"),
			)
		try:
			se.flags.ignore_duplicate_for_work_order = True
			se.submit()
		except Exception as e:
			try:
				frappe.db.rollback(save_point=mfg_submit_savepoint)
			except Exception:
				pass
			shortages = self._rm_shortages_for_se(se, wo_doc)
			if not shortages:
				shortages = self._rm_shortages_from_exception(e)
				if shortages:
					shortages = self._filter_shortages_by_wo_transfer_remaining(wo_doc, shortages)
			if shortages:
				submit_shortage_events = [
					{
						"wo_id": wo_id,
						"wo_doc": wo_doc,
						"chunk_total_qty": chunk_total_qty,
						"shortages": shortages,
					}
				]
				for p2 in planned_wo_posts:
					wo_id2 = p2["wo_id"]
					wo_doc2 = p2["wo_doc"]
					for chunk_rows2 in p2["row_chunks"]:
						chunk_total_qty2 = sum(self._row_fg_qty(r2) for r2 in chunk_rows2)
						if chunk_total_qty2 <= 0:
							continue
						preview_se2 = self._build_shortage_preview_for_chunk(wo_doc2, chunk_total_qty2)
						shortages2 = self._rm_shortages_for_se(preview_se2, wo_doc2)
						if shortages2:
							submit_shortage_events.append(
								{
									"wo_id": wo_id2,
									"wo_doc": wo_doc2,
									"chunk_total_qty": chunk_total_qty2,
									"shortages": shortages2,
								}
							)
						wip_topup2 = self._spr_wip_topup_shortages_for_se(preview_se2, wo_doc2)
						if wip_topup2:
							submit_shortage_events.append(
								{
									"wo_id": wo_id2,
									"wo_doc": wo_doc2,
									"chunk_total_qty": chunk_total_qty2,
									"shortages": wip_topup2,
									"wip_topup": True,
								}
							)
				self._raise_shortage_with_transfer_batch(submit_shortage_events)
			# WO already shows RM transferred — auto RM->WIP transfer then retry Manufacture once.
			try:
				self._spr_try_wip_topup_transfer_and_retry_manufacture(
					wo_doc, e, allow_wip_topup_retry, mfg_submit_savepoint, mfg_se=se
				)
			except _SprWipTopupRetry:
				raise
			# WIP top-up could not auto-submit — raise transfer / no-stock message (never cap below BOM).
			wip_topup = self._spr_wip_topup_shortages_for_se(se, wo_doc)
			if not wip_topup:
				wip_topup = self._spr_wip_topup_from_manufacture_se(se, wo_doc)
				if wip_topup:
					company = _cstr(getattr(wo_doc, "company", None))
					wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None))
					wip_topup = [
						(
							ic,
							self._resolve_rm_source_warehouse_for_transfer(wo_doc, ic, wip_wh)
							or _spr_company_rm_warehouse(company, wip_wh)
							or _("RM warehouse"),
							flt(qty),
							0.0,
							flt(qty),
						)
						for ic, qty in wip_topup.items()
						if ic and flt(qty) > 0
					]
			if wip_topup:
				self._raise_shortage_with_transfer_batch(
					[
						{
							"wo_id": wo_id,
							"wo_doc": wo_doc,
							"chunk_total_qty": chunk_total_qty,
							"shortages": wip_topup,
							"wip_topup": True,
						}
					],
					ignore_wo_transfer_prune=True,
				)
			parsed_wip = self._rm_shortages_from_exception(e)
			if parsed_wip:
				self._raise_shortage_with_transfer_batch(
					[
						{
							"wo_id": wo_id,
							"wo_doc": wo_doc,
							"chunk_total_qty": chunk_total_qty,
							"shortages": parsed_wip,
						}
					],
					ignore_wo_transfer_prune=True,
				)
			self._throw_wip_stock_wo_transfer_mismatch(wo_doc, e)
			return
		frappe.db.set_value("Stock Entry", se.name, "work_order", wo_id, update_modified=False)
		self._apply_unit_to_submitted_stock_entry(se.name, wo_doc)
		self._apply_order_code_to_submitted_stock_entry(se.name)
		self._sync_work_order_produced_qty_from_submitted_manufacture(wo_id)
		self._sync_work_order_required_item_progress(wo_id)
		self._sync_production_plan_progress_from_work_orders(_cstr(getattr(wo_doc, "production_plan", None)))
		created_entries.append(se.name)
		created_entries_by_wo[wo_id].append(se.name)
		frappe.msgprint(
			_("WO {0}: Created {1}/{2} Manufacture entry {3} ({4} Kg).").format(
				wo_id, chunk_idx, chunk_count, se.name, flt(chunk_total_qty, 3)
			),
			alert=True,
		)
		# Merge RM map AFTER successful submit to prevent double-counting on retry
		actual_rm_map = self._merge_rm_maps(actual_rm_map, self._collect_rm_map_from_se(se))
		return {"actual_rm_map": actual_rm_map, "se_name": se.name}

	def create_manufacturing_stock_entries(self):
		"""Create submitted Manufacture Stock Entries from Roll Production Results (per WO / chunk).

		Operator flow (enforced in this method):

		1. **Before any Manufacture insert**: for every WO chunk, build a preview Manufacture entry and
		   check WIP raw-material stock. If anything is short, create a draft *Material Transfer for
		   Manufacture* (Raw Materials ΓåÆ WIP), ``commit`` it so it survives rollback, then throw with links.
		   After the operator submits that transfer, SPR submit can proceed.

		2. **Create / submit** Manufacture entries: each Stock Entry lists **one finished-good row per
		   roll/batch** (same item, different ``batch_no`` / qty) plus BOM raw materials — like a single
		   document with multiple FG lines (see standard Manufacture layout). Multiple Stock Entries are
		   created only when total FG for the WO exceeds the per-entry overproduction limit. Link WO after
		   submit, then sync each WO ``produced_qty`` and required-items ``consumed_qty`` /
		   ``transferred_qty`` from submitted Stock Entries, and sync Production Plan produced totals.

		3. **Guards**: no produced row without WO; FG roll coverage vs SPR rows must match so no silent
		   partial posting.

		Does not change Work Order ``qty`` (Qty To Manufacture). ERPNext caps Manufacture FG by WO qty
		plus Manufacturing Settings overproduction; if roll totals exceed that cap, raise overproduction
		percent or WO qty in ERPNext.
		"""
		if not cint(getattr(self.flags, "_spr_allow_manufacture_posting", 0)):
			frappe.throw(
				_(
					"Manufacture entries are allowed only during SPR submit. "
					"Click Submit on SPR after resolving any shortage transfer(s)."
				),
				title=_("Submit required"),
			)
		self._validate_no_pending_wo_width_rows()
		wo_groups = {}
		for row in self.items or []:
			wo_name = row.get("work_order") or row.get("wo_id")
			if not wo_name:
				continue
			wo_groups.setdefault(wo_name, []).append(row)
		if not wo_groups:
			positive_rows = [r for r in (self.items or []) if self._row_fg_qty(r) > 0]
			if positive_rows:
				frappe.throw(
					_(
						"SPR has produced rows, but none are linked to a Work Order. "
						"Map Work Order in Roll Production Results and submit again."
					),
					title=_("Missing Work Order mapping"),
				)
			frappe.throw(
				_(
					"Cannot submit SPR without any Work Order-linked production rows. "
					"Create Entry and ensure each row has Work Order plus produced weight "
					"(or achieved bag PCS for bag runs)."
				),
				title=_("No manufacturing rows"),
			)

		created_entries = []
		created_entries_by_wo = defaultdict(list)
		planned_wo_posts = []

		# Phase 1: validate all WO groups first (no Stock Entry insert/submit here).
		for wo_id, rows in wo_groups.items():
			wo_doc = frappe.get_doc("Work Order", wo_id)
			total_qty = self._fg_posting_qty_for_rows(rows, wo_doc)
			wo_item = _cstr(getattr(wo_doc, "production_item", None))
			if spr_doc_is_bag_spr(self):
				self._spr_validate_bag_fg_qty_for_wo(wo_doc, total_qty)

			# Hard safety: one WO must not receive rows of other finished items.
			mismatch_items = sorted(
				{
					_cstr(r.get("item_code"))
					for r in rows
					if _cstr(r.get("item_code")) and _cstr(r.get("item_code")) != wo_item
				}
			)
			if mismatch_items:
				frappe.throw(
					_(
						"Work Order {0} produces item {1}, but this SPR has roll lines mapped to this WO with "
						"different item(s): {2}. Correct Available Jobs ΓåÆ Work Orders mapping before submit."
					).format(wo_id, wo_item or "—", ", ".join(mismatch_items)),
					title=_("Wrong WO mapping"),
				)

			# ≡ƒôè DEBUG: Log WO and total quantity
			frappe.logger().info(f"[SPR CREATE] Processing WO: {wo_id}, SPR Total Qty: {total_qty} KG, WO Authorized Qty: {wo_doc.qty} KG")
			
			# Show in UI
			qty_label = "PCS" if spr_doc_is_bag_spr(self) else "KG"
			frappe.msgprint(
				_(f"Creating Manufacturing Entry for WO: {wo_id} | Total Quantity: {total_qty} {qty_label} | WO Authorized: {wo_doc.qty} {qty_label}"),
				alert=False
			)

			if total_qty <= 0:
				skip_msg = _("Skipping WO {0} — achieved bag PCS is 0").format(wo_id) if spr_doc_is_bag_spr(self) else _("Skipping WO {0} — net/gross weight is 0").format(wo_id)
				frappe.msgprint(skip_msg, alert=True)
				continue

			allowed_entry_qty, over_pct = self._wo_allowed_entry_qty(wo_doc)
			row_chunks = [rows]
			expected_rm_map = self._build_expected_rm_map_for_qty(wo_doc, total_qty)
			if len(row_chunks) > 1:
				frappe.msgprint(
					_(
						"WO {0}: SPR quantity {1} Kg exceeds per-entry limit {2} Kg "
						"(overproduction {3}%). Creating {4} Manufacture entries."
					).format(
						wo_id,
						flt(total_qty, 3),
						flt(allowed_entry_qty, 3),
						flt(over_pct, 3),
						len(row_chunks),
					),
					alert=False,
				)

			# ≡ƒöÆ VALIDATION: Ensure WIP warehouse exists
			if not wo_doc.wip_warehouse:
				frappe.throw(
					_("Work Order {0} has no WIP warehouse set. Raw materials cannot be fetched.").format(wo_id),
					title=_("Missing WIP Warehouse")
				)

			planned_wo_posts.append(
				{
					"wo_id": wo_id,
					"wo_doc": wo_doc,
					"rows": rows,
					"total_qty": total_qty,
					"row_chunks": row_chunks,
					"expected_rm_map": expected_rm_map,
				}
			)

		# Phase 2: after all WO groups are valid, create/submit Manufacture entries.
		# Preflight shortage check first so submit cannot partially create entries for only some WOs.
		shortage_events = []
		for plan in planned_wo_posts:
			wo_id = plan["wo_id"]
			wo_doc = plan["wo_doc"]
			for chunk_rows in plan["row_chunks"]:
				chunk_total_qty = self._fg_posting_qty_for_rows(chunk_rows, wo_doc)
				if chunk_total_qty <= 0:
					continue
				preview_se = self._build_shortage_preview_for_chunk(wo_doc, chunk_total_qty)
				shortages = self._rm_shortages_for_se(preview_se, wo_doc)
				if shortages:
					shortage_events.append(
						{
							"wo_id": wo_id,
							"wo_doc": wo_doc,
							"chunk_total_qty": chunk_total_qty,
							"shortages": shortages,
						}
					)
				wip_topup = self._spr_wip_topup_shortages_for_se(preview_se, wo_doc)
				if wip_topup:
					shortage_events.append(
						{
							"wo_id": wo_id,
							"wo_doc": wo_doc,
							"chunk_total_qty": chunk_total_qty,
							"shortages": wip_topup,
							"wip_topup": True,
						}
					)
		if shortage_events:
			self._raise_shortage_with_transfer_batch(shortage_events)

		self._spr_init_manual_fabric_batch_pools(planned_wo_posts)

		# Phase 2: create/submit Manufacture entries after preflight passes for all WO chunks.
		# Savepoint ensures we can roll back partial Manufacture submits if any later WO fails.
		mfg_submit_savepoint = "spr_mfg_submit"
		frappe.db.savepoint(mfg_submit_savepoint)
		for plan in planned_wo_posts:
			wo_id = plan["wo_id"]
			wo_doc = plan["wo_doc"]
			row_chunks = plan["row_chunks"]
			total_qty = plan["total_qty"]
			expected_rm_map = plan["expected_rm_map"]
			actual_rm_map = {}
			for idx, chunk_rows in enumerate(row_chunks, start=1):
				chunk_total_qty = self._fg_posting_qty_for_rows(chunk_rows, wo_doc)
				if chunk_total_qty <= 0:
					continue
				for _spr_mfg_try in range(2):
					try:
						chunk_done = self._spr_run_manufacture_chunk_attempt(
							wo_id=wo_id,
							wo_doc=wo_doc,
							chunk_rows=chunk_rows,
							chunk_total_qty=chunk_total_qty,
							chunk_idx=idx,
							chunk_count=len(row_chunks),
							mfg_submit_savepoint=mfg_submit_savepoint,
							planned_wo_posts=planned_wo_posts,
							actual_rm_map=actual_rm_map,
							created_entries=created_entries,
							created_entries_by_wo=created_entries_by_wo,
							allow_wip_topup_retry=(_spr_mfg_try == 0),
						)
						actual_rm_map = chunk_done["actual_rm_map"]
						break
					except _SprWipTopupRetry:
						if _spr_mfg_try == 0:
							continue
						raise
			self._validate_rm_split_variance(
				wo_id, total_qty, expected_rm_map, actual_rm_map, wo_doc=wo_doc
			)
			self._validate_fg_roll_coverage_for_wo(wo_doc, plan["rows"], created_entries_by_wo.get(wo_id, []))

		if created_entries:
			self.db_set("manufacturing_entries", ", ".join(created_entries))
			self._sync_production_plan_progress_from_work_orders(_cstr(self.get("production_plan")))
			self._refresh_batch_qty_for_codes([_cstr(r.get("batch_no")) for r in (self.items or []) if _cstr(r.get("batch_no"))])
			frappe.msgprint(
				_("Created {0} Manufacturing Entries: {1}").format(
					len(created_entries), ", ".join(created_entries)
				)
			)
		else:
			# Recovery-safe path: if old bug already posted Manufacture entries for this SPR, reuse them.
			existing_submitted = self._get_existing_submitted_manufacture_entries_for_spr()
			if existing_submitted:
				self.db_set("manufacturing_entries", ", ".join(existing_submitted))
				self._sync_production_plan_progress_from_work_orders(_cstr(self.get("production_plan")))
				self._refresh_batch_qty_for_codes([_cstr(r.get("batch_no")) for r in (self.items or []) if _cstr(r.get("batch_no"))])
				frappe.msgprint(
					_("No new Manufacture entry needed; reusing existing submitted entries: {0}").format(
						", ".join(existing_submitted[:20])
					),
					alert=True,
				)
			else:
				frappe.throw(
					_(
						"SPR submit blocked: no Manufacture Stock Entry was created. "
						"Check Work Order mapping and produced quantity "
						"(weight for roll runs, achieved bag PCS for bag runs), then retry."
					),
					title=_("No stock entry created"),
				)

	def create_mix_roll_material_receipts(self):
		"""Post mix roll FG via Material Receipt (no Work Order / Manufacture)."""
		if not spr_doc_is_mix_roll(self):
			frappe.throw(_("This method is only for mix roll Shaft Production Runs."))

		unit = _cstr(self.get("custom_unit") or self.get("unit"))
		company, fg_wh = resolve_mix_roll_company_and_fg_warehouse(unit)
		if self.get("company") and frappe.db.exists("Company", self.company):
			company = _cstr(self.company)
		if not company:
			frappe.throw(_("Company is required for mix roll stock posting."))
		if not fg_wh or not frappe.db.exists("Warehouse", fg_wh):
			frappe.throw(_("Finished goods warehouse not found for {0}.").format(unit or "unit"))

		lines = []
		for row in self.items or []:
			qty = flt(row.get("net_weight") or row.get("gross_weight") or 0)
			if qty <= 0:
				continue
			item_code = _cstr(row.get("item_code"))
			batch_id = _cstr(row.get("batch_no"))
			if not item_code:
				frappe.throw(_("Mix roll line missing item code (roll {0}).").format(row.get("roll_no") or "?"))
			if not batch_id:
				frappe.throw(_("Mix roll line missing batch (item {0}).").format(item_code))
			lines.append((row, item_code, batch_id, qty))

		if not lines:
			frappe.throw(
				_("Cannot submit mix roll SPR without produced roll weights on Roll Production Results."),
				title=_("No produced quantity"),
			)

		se = frappe.new_doc("Stock Entry")
		se.company = company
		se.posting_date = self.run_date or today()
		se.posting_time = nowtime()
		se.set_posting_time = 1
		se.stock_entry_type = self._stock_entry_type_name_for_purpose("Material Receipt")
		se.purpose = "Material Receipt"
		se.remarks = _("Mix roll production from {0}").format(self.name)
		self._set_stock_entry_spr_link(se)
		self._set_stock_entry_unit(se)
		se_meta = frappe.get_meta("Stock Entry")
		if se_meta.has_field("custom_is_mix_roll"):
			se.custom_is_mix_roll = 1

		for spr_row, item_code, batch_id, qty in lines:
			batch_link = self._get_batch_link_name_for_stock_entry(batch_id, item_code, company, spr_row)
			uom = _cstr(spr_row.get("uom")) or frappe.db.get_value("Item", item_code, "stock_uom") or "Kg"
			se.append(
				"items",
				{
					"item_code": item_code,
					"item_name": spr_row.get("item_name") or frappe.db.get_value("Item", item_code, "item_name"),
					"qty": qty,
					"transfer_qty": qty,
					"t_warehouse": fg_wh,
					"uom": uom,
					"stock_uom": uom,
					"conversion_factor": 1,
					"batch_no": batch_link or batch_id,
					"is_finished_item": 1,
				},
			)

		se.insert(ignore_permissions=True)
		se.submit()
		self._persist_stock_entry_spr_reference_db(se.name)
		self._apply_order_code_to_submitted_stock_entry(se.name)
		self.db_set("manufacturing_entries", se.name)
		self._refresh_batch_qty_for_codes([_cstr(r.get("batch_no")) for r, *_ in lines])
		frappe.msgprint(
			_("Mix roll Material Receipt created: {0} → {1}").format(se.name, fg_wh),
			alert=True,
		)

	def update_work_order_statuses(self):
		wo_ids = list(
			{
				(row.get("work_order") or row.get("wo_id"))
				for row in (self.items or [])
				if row.get("work_order") or row.get("wo_id")
			}
		)
		for wo_id in wo_ids:
			wo_doc = frappe.get_doc("Work Order", wo_id)
			total_produced = frappe.db.sql(
				"""
				SELECT IFNULL(SUM(fg_completed_qty), 0)
				FROM `tabStock Entry`
				WHERE work_order = %s
				  AND IFNULL(purpose, '') = 'Manufacture'
				  AND docstatus = 1
				""",
				wo_id,
			)[0][0]

			if flt(total_produced) >= flt(wo_doc.qty):
				wo_doc.db_set("status", "Completed")
				frappe.msgprint(_("Work Order {0} marked as Completed").format(wo_id), alert=True)

	def cancel_manufacturing_stock_entries(self):
		names = []
		if self.manufacturing_entries:
			names = [x.strip() for x in self.manufacturing_entries.split(",") if x.strip()]
		meta_se = frappe.get_meta("Stock Entry")
		if not names and meta_se.has_field("shaft_production_run"):
			conds = [
				"shaft_production_run = %s",
				"IFNULL(purpose, '') = 'Manufacture'",
				"docstatus = 1",
			]
			params = [self.name]
			if meta_se.has_field("roll_production_entry"):
				conds.append("IFNULL(roll_production_entry, '') = ''")
			names = frappe.db.sql_list(
				f"SELECT name FROM `tabStock Entry` WHERE {' AND '.join(conds)}",
				params,
			)
		for name in names:
			if not frappe.db.exists("Stock Entry", name):
				continue
			if frappe.db.get_value("Stock Entry", name, "docstatus") != 1:
				continue
			se = frappe.get_doc("Stock Entry", name)
			se.cancel()
			frappe.msgprint(_("Cancelled Manufacturing Entry {0}").format(name), alert=True)
		self.db_set("manufacturing_entries", "")


_SLITTING_PP_UNITS = (SLITTING_UNIT, SLITTING_UNIT_VTP, SLITTING_UNASSIGNED_UNIT)
_REWINDING_PP_UNITS = (REWINDING_UNIT_L3, REWINDING_UNIT_L4, REWINDING_UNIT_L5, REWINDING_UNASSIGNED_UNIT)
_PRINTING_PP_UNITS = (
	PRINTING_UNIT_2_COLOUR,
	PRINTING_UNIT_4_COLOUR,
	PRINTING_UNIT_TT,
	PRINTING_UNASSIGNED_UNIT,
)
_BAG_BOARD_PP_UNITS = (
	BOX_BAG_UNIT_L1,
	BOX_BAG_UNIT_L2,
	BOX_BAG_UNIT_L4_SCREEN,
	BOX_BAG_UNASSIGNED_UNIT,
) + tuple(W_CUT_D_CUT_ALL_UNITS)


def _pp_is_bag_board_unit_from_doc(pp_doc) -> bool:
	"""True when PP workstation is a Box Bag or W/D-CUT bag-board machine."""
	u = _spr_unit_value_for_current_field(pp_doc.get("custom_unit") if pp_doc else None)
	return u in _BAG_BOARD_PP_UNITS


def _spr_pp_process_flags(pp) -> dict:
	"""Map PP unit → SPR process checkboxes (unit wins over item/bundle heuristics)."""
	spr_meta = frappe.get_meta("Shaft Production Run")
	pp_unit = _spr_unit_value_for_current_field(pp.get("custom_unit"))
	flags = {}

	def _set_flag(fieldname: str, on: bool) -> None:
		if spr_meta.has_field(fieldname):
			flags[fieldname] = 1 if on else 0

	_set_flag("custom_is_box_bag", _pp_is_bag_board_unit_from_doc(pp))
	_set_flag("custom_is_sheet_cutting", pp_unit == SHEET_CUTTING_UNIT)
	_set_flag("custom_is_slitting", pp_unit in _SLITTING_PP_UNITS)
	_set_flag("custom_is_lamination", pp_unit == LAMINATION_UNIT)
	_set_flag("custom_is_rewinding", pp_unit in _REWINDING_PP_UNITS)
	_set_flag("custom_is_printing", pp_unit in _PRINTING_PP_UNITS)
	_set_flag("custom_is_bopp_film", pp_unit == PRINTED_BOPP_FILM_UNIT)
	return flags


@frappe.whitelist()
def get_production_plan_details(production_plan):
	"""Fill header fields from Production Plan."""
	if not production_plan or not frappe.db.exists("Production Plan", production_plan):
		return {}
	pp = frappe.get_doc("Production Plan", production_plan)
	pp_meta = frappe.get_meta("Production Plan")
	pp_unit = _spr_unit_value_for_current_field(pp.get("custom_unit"))
	out = {
		"company": pp.get("company"),
		"customer": pp.get("customer"),
		"custom_unit": pp_unit,
	}
	# custom_order_code comes from PP's custom_party_code
	if pp_meta.has_field("custom_party_code"):
		out["custom_order_code"] = pp.get("custom_party_code") or ""
	
	label_value = resolve_label_from_pp_doc(pp)
	if label_value:
		out["custom_label"] = label_value
	
	# Calculate custom_total_planned_qty from WO sum
	out["custom_total_planned_qty"] = _production_plan_total_planned_qty(production_plan)
	if frappe.get_meta("Shaft Production Run").has_field("custom_total_planned_pcs"):
		out["custom_total_planned_pcs"] = _production_plan_total_planned_pcs(production_plan)
	process_flags = _spr_pp_process_flags(pp)
	out.update(process_flags)
	is_sc = bool(cint(process_flags.get("custom_is_sheet_cutting", 0)))
	is_bb = bool(cint(process_flags.get("custom_is_box_bag", 0)))
	out["is_sheet_cutting"] = is_sc
	if is_sc or is_bb:
		out["bundle_rows"] = get_bundle_calculation_rows_for_production_plan(
			production_plan,
			out.get("custom_order_code"),
			0,
		)
	
	frappe.logger().info(f"[get_production_plan_details] PP {production_plan}: custom_order_code={out.get('custom_order_code')}, custom_label={out.get('custom_label')}, custom_total_planned_qty={out.get('custom_total_planned_qty')}")
	if pp.get("sales_order"):
		so = frappe.db.get_value(
			"Sales Order", pp.sales_order, ["customer", "transaction_date"], as_dict=True
		)
		if so:
			out["customer"] = out["customer"] or so.customer
	return out


PP_BUNDLE_CALC_FIELD = "custom_bundle_calculation"
BUNDLE_CALC_DOCTYPE = "Bundle Calculation"
SHEET_CUTTING_PROCESS_CODES = frozenset({"251", "252", "253", "254", "255"})


def _spr_item_process_prefix(item_code: str) -> str:
	"""Process prefix for FG items (design-first bag codes e.g. 6000-511-221…)."""
	try:
		from production_entry.production_planning.scheduler_api import _item_process_prefix

		return _cstr(_item_process_prefix(item_code)).strip()
	except Exception:
		return spr_fg_item_process_code(item_code)


def _is_sheet_cutting_fg_code(item_code: str) -> bool:
	return _spr_item_process_prefix(item_code) in SHEET_CUTTING_PROCESS_CODES


def _is_box_bag_fg_code(item_code: str) -> bool:
	try:
		from production_entry.production_planning.scheduler_api import BOX_BAG_PROCESS_CODES

		return _spr_item_process_prefix(item_code) in BOX_BAG_PROCESS_CODES
	except Exception:
		return False


def _is_wcut_dcut_fg_code(item_code: str) -> bool:
	try:
		from production_entry.production_planning.scheduler_api import W_CUT_D_CUT_FG_PROCESS_CODES

		return _spr_item_process_prefix(item_code) in W_CUT_D_CUT_FG_PROCESS_CODES
	except Exception:
		return False


def _is_bag_bundle_fg_code(item_code: str) -> bool:
	return bool(_spr_resolve_bag_fg_process_code(item_code))


def _spr_bag_size_from_item_code(item_code: str) -> str:
	"""Bag size label (inches) from FG item code — Bag Series master, same as Planning Sheet."""
	ic = _cstr(item_code).strip()
	if not ic:
		return ""
	try:
		from production_entry.production_planning.box_bag_api import resolve_bag_size_from_item_code

		return _cstr(resolve_bag_size_from_item_code(ic)).strip()
	except Exception:
		return ""


def _spr_sheet_size_from_item_code(item_code: str) -> str:
	"""Sheet size label from FG item code — Sheet Cutting Series master."""
	ic = _cstr(item_code).strip()
	if not ic:
		return ""
	try:
		from production_entry.production_planning.scheduler_api import _sheet_size_for_item_code

		sz, _ = _sheet_size_for_item_code(ic)
		return _cstr(sz).strip()
	except Exception:
		return ""


def _spr_resolve_roll_line_specs_from_item_code(item_code: str, item_name: str = None) -> dict:
	"""Quality, colour, GSM, sheet size, width from FG item code (251–255) for SPR roll lines."""
	ic = _cstr(item_code).strip()
	out = {"quality": "", "color": "", "gsm": 0, "sheet_size": "", "bag_size": "", "width_inch": 0.0}
	if not ic:
		return out
	if not item_name:
		item_name = _cstr(frappe.db.get_value("Item", ic, "item_name") or "")
	try:
		from production_entry.production_planning.scheduler_api import (
			_LAMINATION_QUALITY_BY_CODE,
			_combined_bopp_line_gsm,
			_get_color_by_code,
			_item_process_prefix,
			_lamination_process_from_item_code,
			_parse_253_item_code,
			_parse_254_item_code,
			_parse_255_item_code,
			_parse_sheet_cutting_item_code,
			_sheet_size_for_item_code,
			resolve_quality_color_gsm_from_item_code,
		)

		q, c, g = resolve_quality_color_gsm_from_item_code(ic, item_name)
		out["quality"] = _cstr(q).strip().upper()
		out["color"] = _cstr(c).strip().upper()
		out["gsm"] = cint(g or 0)
		sz, w = _sheet_size_for_item_code(ic)
		out["sheet_size"] = _cstr(sz).strip()
		out["width_inch"] = flt(w or 0)
		if _is_bag_bundle_fg_code(ic):
			try:
				from production_entry.production_planning.box_bag_api import (
					_parse_box_bag_item_code,
					_parse_dcut_bag_item_code,
					resolve_bag_size_from_item_code,
				)

				p221 = _parse_box_bag_item_code(ic) or _parse_dcut_bag_item_code(ic) or {}
				if p221:
					if out["gsm"] <= 0:
						out["gsm"] = cint(p221.get("total_gsm") or 0)
					if not out["quality"]:
						qc = _cstr(p221.get("quality_code") or "").strip().upper()
						out["quality"] = _cstr(
							p221.get("quality_name") or _LAMINATION_QUALITY_BY_CODE.get(qc, "") or ""
						).strip().upper()
					if not out["color"]:
						cc = _cstr(p221.get("colour_code") or "").strip()
						if cc:
							try:
								out["color"] = _cstr(_get_color_by_code(cc) or "").strip().upper()
							except Exception:
								out["color"] = ""
				bag_sz = _cstr(resolve_bag_size_from_item_code(ic)).strip()
				if bag_sz:
					out["bag_size"] = bag_sz
			except Exception:
				frappe.log_error(frappe.get_traceback(), "_spr_resolve_roll_line_specs:box_bag")
		if out["quality"] and out["color"] and out["gsm"] > 0:
			return out
		pp = _item_process_prefix(ic)
		lam = _lamination_process_from_item_code(ic)
		p = {}
		if lam == "255" or pp == "255":
			p = _parse_255_item_code(ic) or {}
		elif pp == "253":
			p = _parse_253_item_code(ic) or {}
		elif pp == "254":
			p = _parse_254_item_code(ic) or {}
		elif pp in ("251", "252"):
			p = _parse_sheet_cutting_item_code(ic) or {}
		if p:
			if not out["quality"]:
				qc = _cstr(p.get("quality_code") or "").strip().upper()
				out["quality"] = _cstr(p.get("quality_name") or _LAMINATION_QUALITY_BY_CODE.get(qc, "") or "").strip().upper()
			if not out["color"]:
				cc = _cstr(p.get("colour_code") or "").strip()
				if cc:
					try:
						out["color"] = _cstr(_get_color_by_code(cc) or "").strip().upper()
					except Exception:
						out["color"] = ""
			if out["gsm"] <= 0:
				out["gsm"] = cint(_combined_bopp_line_gsm(p) or 0) or cint(p.get("gsm") or p.get("fabric_gsm") or 0)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "_spr_resolve_roll_line_specs_from_item_code")
	if out["gsm"] <= 0:
		out["gsm"] = _sheet_cutting_parse_gsm(ic)
	if not out["quality"] or not out["color"]:
		q2, c2 = extract_quality_and_color(item_name or "", item_code=ic)
		if not out["quality"]:
			out["quality"] = _cstr(q2).strip().upper()
	if not out["color"]:
		out["color"] = _cstr(c2).strip().upper()
	if flt(out["width_inch"]) <= 0:
		out["width_inch"] = _spr_nominal_roll_width_inch(ic, item_name)
	return out


def _sheet_cutting_parse_gsm(item_code: str) -> int:
	ic = _cstr(item_code)
	if not ic:
		return 0
	try:
		from production_entry.production_planning.scheduler_api import (
			_parse_253_item_code,
			_parse_254_item_code,
			_parse_255_item_code,
			_parse_sheet_cutting_item_code,
			_item_process_prefix,
		)

		pp = _item_process_prefix(ic)
		if pp == "253":
			return cint((_parse_253_item_code(ic) or {}).get("gsm") or 0)
		if pp == "254":
			return cint((_parse_254_item_code(ic) or {}).get("gsm") or 0)
		if pp == "255":
			p = _parse_255_item_code(ic) or {}
			comb = cint(p.get("fabric_gsm") or 0) + cint(p.get("bopp_gsm") or 0) + cint(p.get("lam_gsm") or 0)
			return comb or cint(p.get("fabric_gsm") or 0)
		p = _parse_sheet_cutting_item_code(ic) or {}
		return cint(p.get("gsm") or 0)
	except Exception:
		pass
	gsm, _w = parse_item_code(ic)
	return cint(gsm or 0)


def _resolve_wo_for_pp_item_code(production_plan: str, item_code: str) -> dict:
	"""Best-effort WO for a sheet-cutting FG on this Production Plan."""
	pp = _cstr(production_plan)
	ic = _cstr(item_code)
	if not pp or not ic:
		return {}
	rows = frappe.get_all(
		"Work Order",
		filters={"production_plan": pp, "production_item": ic, "docstatus": ["<", 2]},
		fields=["name", "production_item", "qty", "production_plan_item"],
		order_by="creation asc",
		limit=1,
	) or []
	if rows:
		return rows[0]
	proc = spr_fg_item_process_code(ic)
	if not proc:
		return {}
	for wo in frappe.get_all(
		"Work Order",
		filters={"production_plan": pp, "docstatus": ["<", 2]},
		fields=["name", "production_item", "qty", "production_plan_item"],
		order_by="creation asc",
	) or []:
		if spr_fg_item_process_code(wo.get("production_item")) == proc:
			return wo
	return {}


def _bundle_child_field(row, default=None, *names):
	"""Read a field from a PP/SPR Bundle Calculation child row (supports box-bag aliases).

	When several field names are listed, numeric zero is skipped so e.g. pcs_per_packet=0
	on a box-bag PP row does not block pcs_per_box=200.
	"""
	if not names:
		return default
	skip_zero = len(names) > 1
	for n in names:
		try:
			v = row.get(n) if isinstance(row, dict) else getattr(row, n, None)
		except Exception:
			v = None
		if v in (None, ""):
			continue
		if skip_zero:
			try:
				if flt(v) == 0:
					continue
			except Exception:
				pass
		return v
	return default


def _bundle_optional_field(row, default=None, *names):
	"""Read PP/SPR bundle field; return default when missing (do not coerce empty to zero)."""
	if not names:
		return default
	for n in names:
		try:
			v = row.get(n) if isinstance(row, dict) else getattr(row, n, None)
		except Exception:
			v = None
		if v not in (None, ""):
			return v
	return default


def _bundle_row_bag_size(row, item_code: str, *, for_bag_fg: bool = False) -> str:
	if for_bag_fg:
		field_names = (
			"bag_size",
			"custom_bag_size",
			"sheet_cutting_size",
			"sheet_size",
			"custom_sheet_size",
		)
	else:
		field_names = (
			"sheet_cutting_size",
			"sheet_size",
			"bag_size",
			"custom_bag_size",
			"custom_sheet_size",
		)
	sz = _cstr(_bundle_child_field(row, "", *field_names))
	if sz:
		return sz
	if item_code:
		try:
			from production_entry.production_planning.box_bag_api import resolve_bag_size_from_item_code

			if for_bag_fg:
				sz = _cstr(resolve_bag_size_from_item_code(item_code)).strip()
				if sz:
					return sz
		except Exception:
			pass
		return _cstr(_spr_resolve_roll_line_specs_from_item_code(item_code).get("sheet_size") or "")
	return ""


def _pp_bundle_calc_child_table_names() -> list[str]:
	"""All Production Plan child tables that use Bundle Calculation doctype."""
	names = []
	try:
		meta = frappe.get_meta("Production Plan")
		for df in meta.fields:
			if df.fieldtype == "Table" and df.options == BUNDLE_CALC_DOCTYPE:
				if df.fieldname not in names:
					names.append(df.fieldname)
	except Exception:
		pass
	for fn in (PP_BUNDLE_CALC_FIELD, "bundle_calculation", "custom_bundle_calculation_table"):
		if fn not in names:
			names.append(fn)
	return names


def _pp_is_box_bag_unit(pp_doc) -> bool:
	u = _spr_unit_value_for_current_field(pp_doc.get("custom_unit") if pp_doc else None)
	return u in (BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L2, BOX_BAG_UNIT_L4_SCREEN, BOX_BAG_UNASSIGNED_UNIT)


def _pp_is_wcut_dcut_unit(pp_doc) -> bool:
	u = _spr_unit_value_for_current_field(pp_doc.get("custom_unit") if pp_doc else None)
	return u in W_CUT_D_CUT_ALL_UNITS


def spr_doc_is_bag_spr(doc) -> bool:
	"""True only when Is Bag is explicitly checked on the SPR — drives PCS qty + RM batch pick."""
	return bool(cint(getattr(doc, "custom_is_box_bag", 0)))


def _first_pp_bundle_calc_row(pp_doc):
	for tbl in _pp_bundle_calc_child_table_names():
		rows = pp_doc.get(tbl) or []
		if rows:
			return rows[0]
	return None


def _resolve_pp_bundle_item_code(row, pp_doc=None, default_item_code=None) -> str:
	ic = _cstr(
		_bundle_child_field(row, "", "item_code", "production_item", "finished_item", "item")
	).strip()
	if ic:
		return ic
	ic = _cstr(default_item_code).strip()
	if ic:
		return ic
	if not pp_doc:
		return ""
	for poi in pp_doc.get("po_items") or []:
		pic = _cstr(poi.get("item_code")).strip()
		if not pic:
			continue
		if _pp_is_box_bag_unit(pp_doc) or _is_bag_bundle_fg_code(pic) or _is_sheet_cutting_fg_code(pic):
			return pic
	for wo in frappe.get_all(
		"Work Order",
		filters={"production_plan": pp_doc.name, "docstatus": ["<", 2]},
		fields=["production_item"],
		order_by="creation asc",
		limit=5,
	):
		pic = _cstr(wo.get("production_item")).strip()
		if pic and (_pp_is_box_bag_unit(pp_doc) or _is_bag_bundle_fg_code(pic) or _is_sheet_cutting_fg_code(pic)):
			return pic
	return ""


def _normalize_pp_bundle_src_row(row, default_item_code=None, pp_doc=None) -> dict:
	"""Map PP bundle row to SPR bundle_calculation (sheet cutting + box bag field names)."""
	ic = _resolve_pp_bundle_item_code(row, pp_doc=pp_doc, default_item_code=default_item_code)
	if not ic:
		return {}
	is_bag = _is_bag_bundle_fg_code(ic) or bool(pp_doc and _pp_is_box_bag_unit(pp_doc))
	if is_bag:
		pcs = cint(
			_bundle_child_field(
				row,
				0,
				"pcs_per_box",
				"custom_pcs_per_box",
				"pcs_per_packet",
				"pcs_per_pack",
				"custom_pcs_per_packet",
			)
			or 0
		)
		pkts = cint(_bundle_child_field(row, 0, "pkts_per_bundle", "packets_per_bundle") or 0)
	else:
		pcs = cint(
			_bundle_child_field(
				row,
				0,
				"pcs_per_packet",
				"pcs_per_box",
				"pcs_per_pack",
				"custom_pcs_per_box",
				"custom_pcs_per_packet",
			)
			or 0
		)
		pkts = cint(_bundle_child_field(row, 0, "pkts_per_bundle", "packets_per_bundle") or 0)
		if pkts <= 0:
			pkts = 1
	n_boxes = flt(_bundle_child_field(row, 0, "no_of_boxes", "custom_no_of_boxes") or 0)
	n_bundles = flt(_bundle_child_field(row, 0, "no_of_bundles", "custom_no_of_bundles") or 0)
	if is_bag and n_boxes > 0:
		if n_bundles <= 0:
			n_bundles = n_boxes
	elif n_bundles <= 0 and n_boxes > 0:
		n_bundles = n_boxes
	if is_bag:
		# On box-bag PP, "Total Planned Pcs" is pcs per box (e.g. 200), not order total.
		pp_pcs_per_box = flt(
			_bundle_child_field(
				row,
				0,
				"total_planned_pcs",
				"custom_total_planned_pcs",
				"planned_bag_pcs",
				"custom_planned_bag_pcs",
			)
			or 0
		)
		if pcs <= 0 and pp_pcs_per_box > 0:
			pcs = cint(pp_pcs_per_box)
		if n_boxes > 0 and pcs > 0:
			tpb = flt(n_boxes * pcs)
		elif pcs > 0:
			tpb = flt(pcs)
		else:
			tpb = flt(
				_bundle_child_field(row, 0, "total_pcs_per_bundle", "total_planned_qty") or 0
			)
	else:
		tpb = flt(
			_bundle_child_field(
				row,
				0,
				"total_pcs_per_bundle",
				"total_planned_pcs",
				"total_planned_qty",
				"custom_total_planned_pcs",
			)
			or 0
		)
		if tpb <= 0 and pkts > 0 and pcs > 0:
			tpb = flt(pkts * pcs)
		if tpb <= 0 and n_boxes > 0 and pcs > 0:
			tpb = flt(n_boxes * pcs)
	bag_sz = _bundle_row_bag_size(row, ic, for_bag_fg=True) if is_bag else ""
	sheet_sz = "" if is_bag else _bundle_row_bag_size(row, ic, for_bag_fg=False)
	if is_bag and bag_sz:
		sheet_sz = bag_sz
	out = {
		"item_code": ic,
		"bag_size": bag_sz,
		"sheet_cutting_size": sheet_sz,
		"no_of_bundles": n_bundles,
		"no_of_boxes": n_boxes,
		"pkts_per_bundle": pkts,
		"pcs_per_packet": pcs,
		"total_pcs_per_bundle": tpb,
	}
	for spr_field, aliases in (
		("total_consumed_meter", ("total_consumed_meter", "consumed_meter", "custom_total_consumed_meter")),
		("total_achieved_weight", ("total_achieved_weight", "custom_total_achieved_weight")),
		("total_produced_sheets", ("total_produced_sheets", "custom_total_produced_sheets")),
		("total_produced_bag_pcs", ("total_produced_bag_pcs", "custom_total_produced_bag_pcs", "achieved_bag_pcs")),
	):
		v = _bundle_optional_field(row, None, *aliases)
		if v not in (None, ""):
			prec = 2 if spr_field in ("total_consumed_meter", "total_achieved_weight") else 0
			out[spr_field] = flt(v, prec)
	return out


def _production_plan_uses_bundle_calculation(pp) -> bool:
	"""True when PP has sheet-cutting or box-bag bundle calculation lines."""
	if not pp:
		return False
	pp_unit = _spr_unit_value_for_current_field(pp.get("custom_unit"))
	if pp_unit == SHEET_CUTTING_UNIT:
		return True
	if pp_unit in (BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L2, BOX_BAG_UNIT_L4_SCREEN, BOX_BAG_UNASSIGNED_UNIT):
		return True
	for row in pp.get(PP_BUNDLE_CALC_FIELD) or []:
		ic = _cstr(_bundle_child_field(row, "", "item_code", "production_item", "finished_item", "item"))
		if not ic:
			continue
		if _is_sheet_cutting_fg_code(ic) or _is_bag_bundle_fg_code(ic):
			return True
	for poi in pp.get("po_items") or []:
		ic = _cstr(poi.get("item_code"))
		if _is_sheet_cutting_fg_code(ic) or _is_bag_bundle_fg_code(ic):
			return True
	return False


def _pp_row_has_bundle_fields(row) -> bool:
	if _bundle_child_field(row, 0, "no_of_boxes", "custom_no_of_boxes", "no_of_bundles"):
		return True
	if _bundle_child_field(row, 0, "pcs_per_box", "custom_pcs_per_box", "pcs_per_packet", "pcs_per_pack"):
		return True
	if _bundle_child_field(
		row, 0, "total_planned_pcs", "custom_total_planned_pcs", "total_pcs_per_bundle", "total_planned_qty"
	):
		return True
	return bool(_cstr(_bundle_child_field(row, "", "item_code", "production_item", "finished_item", "item")).strip())


def _get_pp_doc(pp_or_name):
	if pp_or_name is None:
		return None
	if hasattr(pp_or_name, "get") and getattr(pp_or_name, "doctype", None) == "Production Plan":
		return pp_or_name
	name = _cstr(pp_or_name).strip()
	if not name or not frappe.db.exists("Production Plan", name):
		return None
	return frappe.get_doc("Production Plan", name)


def _pp_length_per_roll_for_item(pp_doc_or_name, item_code: str, production_plan_item: str = None) -> float:
	"""Length / Roll from PP Assembly Items (or po_items) for ordered length on SPR roll lines."""
	pp_doc = _get_pp_doc(pp_doc_or_name)
	if not pp_doc:
		return 0.0
	ic = _cstr(item_code).strip()
	ppi = _cstr(production_plan_item).strip()
	length_fields = (
		"length_per_roll",
		"custom_length_per_roll",
		"length__roll",
		"meter__roll",
		"custom_length_roll",
		"length_roll",
		"custom_meter_per_roll",
		"meter_per_roll",
		"planned_length",
		"custom_planned_length",
	)
	table_keys = (
		PP_BUNDLE_CALC_FIELD,
		"assembly_items",
		"custom_assembly_items",
		"sub_assembly_items",
		"custom_sub_assembly_items",
		"po_items",
		"prod_order_items",
	)
	for tk in table_keys:
		for row in pp_doc.get(tk) or []:
			row_ppi = _cstr(getattr(row, "name", None) or (row.get("name") if isinstance(row, dict) else "")).strip()
			if ppi and row_ppi != ppi:
				continue
			row_ic = _cstr(
				getattr(row, "item_code", None)
				or (row.get("item_code") if isinstance(row, dict) else None)
				or getattr(row, "production_item", None)
				or (row.get("production_item") if isinstance(row, dict) else None)
			).strip()
			if ic and row_ic and row_ic != ic and not ppi:
				continue
			for fn in length_fields:
				if hasattr(row, fn):
					v = flt(getattr(row, fn, 0) or 0)
				else:
					v = flt(row.get(fn) or 0) if isinstance(row, dict) else 0
				if v > 0:
					return v
	return 0.0


def _iter_pp_bundle_source_rows(pp_doc):
	"""Yield PP rows that carry bundle / box fields (child table + assembly + po_items)."""
	seen = set()
	is_bb = _pp_is_box_bag_unit(pp_doc)

	def _yield_row(row, key_ic: str = ""):
		ic = key_ic or _resolve_pp_bundle_item_code(row, pp_doc=pp_doc)
		key = (ic or "__no_item__", _cstr(getattr(row, "name", None)))
		if key in seen:
			return
		seen.add(key)
		yield row

	for tbl in _pp_bundle_calc_child_table_names():
		for row in pp_doc.get(tbl) or []:
			if not _pp_row_has_bundle_fields(row):
				continue
			yield from _yield_row(row)

	pp_meta = frappe.get_meta("Production Plan")
	skip_tables = frozenset(
		{
			"po_items",
			"mr_items",
			"prod_order_items",
			"material_request_plan_items",
			"sub_assembly_items",
		}
		| frozenset(_pp_bundle_calc_child_table_names())
	)
	for df in pp_meta.fields:
		if df.fieldtype != "Table" or df.fieldname in skip_tables:
			continue
		for row in pp_doc.get(df.fieldname) or []:
			if not _pp_row_has_bundle_fields(row):
				continue
			yield from _yield_row(row)

	for poi in pp_doc.get("po_items") or []:
		ic = _cstr(poi.get("item_code")).strip()
		if not ic:
			continue
		if not is_bb and not _is_bag_bundle_fg_code(ic) and not _is_sheet_cutting_fg_code(ic):
			continue
		key = (ic, _cstr(poi.name))
		if key in seen:
			continue
		seen.add(key)
		yield poi


def _fallback_bundle_rows_from_pp(pp_doc) -> list[dict]:
	"""When bundle child rows lack item_code or normalize empty, merge PP bundle qty with po_items / WO."""
	merged_src = _first_pp_bundle_calc_row(pp_doc)
	out = []
	seen_ic = set()
	is_bb = _pp_is_box_bag_unit(pp_doc)

	def _append(ic: str, src_row):
		if not ic or ic in seen_ic:
			return
		seen_ic.add(ic)
		norm = _normalize_pp_bundle_src_row(src_row, default_item_code=ic, pp_doc=pp_doc)
		if norm:
			out.append(norm)

	for poi in pp_doc.get("po_items") or []:
		ic = _cstr(poi.get("item_code")).strip()
		if not ic:
			continue
		if not is_bb and not _is_bag_bundle_fg_code(ic) and not _is_sheet_cutting_fg_code(ic):
			continue
		_append(ic, merged_src or poi)

	if out:
		return out

	for wo in frappe.get_all(
		"Work Order",
		filters={"production_plan": pp_doc.name, "docstatus": ["<", 2]},
		fields=["production_item"],
		order_by="creation asc",
	):
		ic = _cstr(wo.get("production_item")).strip()
		if not ic:
			continue
		if not is_bb and not _is_bag_bundle_fg_code(ic) and not _is_sheet_cutting_fg_code(ic):
			continue
		_append(ic, merged_src or {})

	if not out and merged_src:
		norm = _normalize_pp_bundle_src_row(merged_src, pp_doc=pp_doc)
		if norm:
			out.append(norm)

	return out


def _read_pp_bundle_calculation_rows(production_plan: str) -> list[dict]:
	"""Rows from PP bundle table + assembly/po_items fallback."""
	pp = _cstr(production_plan).strip()
	if not pp or not frappe.db.exists("Production Plan", pp):
		return []
	pp_doc = frappe.get_doc("Production Plan", pp)
	out = []
	seen_ic = set()
	for row in _iter_pp_bundle_source_rows(pp_doc):
		norm = _normalize_pp_bundle_src_row(row, pp_doc=pp_doc)
		if not norm:
			continue
		ic = norm.get("item_code") or ""
		if ic and ic in seen_ic:
			continue
		if ic:
			seen_ic.add(ic)
		out.append(norm)
	if not out:
		out = _fallback_bundle_rows_from_pp(pp_doc)
	return out


@frappe.whitelist()
def get_bundle_calculation_rows_for_production_plan(production_plan, order_code=None, order_meter=None):
	"""Copy PP bundle calculation rows for SPR (sheet cutting)."""
	if not production_plan or not frappe.db.exists("Production Plan", production_plan):
		return []
	oc = _cstr(order_code)
	if not oc:
		pp = frappe.get_doc("Production Plan", production_plan)
		oc = _cstr(pp.get("custom_party_code") or pp.get("party_code") or "")
	out = []
	for src in _read_pp_bundle_calculation_rows(production_plan):
		ic = src.get("item_code") or ""
		wo = _resolve_wo_for_pp_item_code(production_plan, ic)
		pkts = cint(src.get("pkts_per_bundle") or 0)
		pcs = cint(src.get("pcs_per_packet") or 0)
		n_boxes = flt(src.get("no_of_boxes") or 0)
		tpb = flt(src.get("total_pcs_per_bundle") or 0)
		if _is_bag_bundle_fg_code(ic) and n_boxes > 0 and pcs > 0:
			tpb = flt(n_boxes * pcs)
		elif tpb <= 0 and pkts > 0 and pcs > 0:
			tpb = flt(pkts * pcs)
		elif tpb <= 0 and n_boxes > 0 and pcs > 0:
			tpb = flt(n_boxes * pcs)
		row = dict(src)
		row["total_pcs_per_bundle"] = tpb
		if _is_bag_bundle_fg_code(ic) or _pp_is_box_bag_unit(frappe.get_doc("Production Plan", production_plan)):
			bz = _cstr(row.get("bag_size") or row.get("sheet_cutting_size") or "")
			if not bz and ic:
				bz = _bundle_row_bag_size(src, ic, for_bag_fg=True)
			if bz:
				row["bag_size"] = bz
				row["sheet_cutting_size"] = bz
		row["work_order"] = wo.get("name") if wo else ""
		row["order_code"] = oc
		row["job"] = _cstr(wo.get("production_plan_item") or "") if wo else ""
		for prod_field in (
			"total_consumed_meter",
			"total_achieved_weight",
			"total_produced_sheets",
			"total_produced_bag_pcs",
		):
			if prod_field not in row or row.get(prod_field) in (None, ""):
				row.pop(prod_field, None)
		out.append(row)
	return out


def populate_spr_bundle_calculation_from_pp(spr_doc, production_plan, order_code=None, order_meter=None):
	"""Replace SPR bundle_calculation child rows from PP."""
	if not spr_doc or not hasattr(spr_doc, "bundle_calculation"):
		return
	rows = get_bundle_calculation_rows_for_production_plan(production_plan, order_code, order_meter)
	spr_doc.set("bundle_calculation", [])
	for r in rows:
		spr_doc.append("bundle_calculation", r)
	return rows


@frappe.whitelist()
def spr_refresh_bundle_calculation_from_pp(shaft_production_run=None):
	"""Desk: reload bundle_calculation from linked Production Plan (box bag / sheet cutting)."""
	name = _cstr(shaft_production_run).strip()
	if not name or not frappe.db.exists("Shaft Production Run", name):
		frappe.throw(_("Shaft Production Run not found"))
	doc = frappe.get_doc("Shaft Production Run", name)
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Only draft Shaft Production Run can be refreshed"))
	pp = get_pp_from_spr(name)
	if not pp:
		frappe.throw(_("Production Plan not linked"))
	populate_spr_bundle_calculation_from_pp(doc, pp, doc.get("custom_order_code"), 0)
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": "ok", "rows": len(doc.get("bundle_calculation") or [])}


def _spr_bundle_job_tag(bundle_row, bundle_index: int, bundle_row_idx=None) -> str:
	"""Stable link between bundle_calculation row and roll lines (job field)."""
	row_id = _cstr(getattr(bundle_row, "name", None) or "")
	if not row_id and bundle_row_idx is not None:
		row_id = f"idx{cint(bundle_row_idx)}"
	return f"{row_id}::{cint(bundle_index)}"


def _spr_bundle_job_prefix(bundle_row, bundle_row_idx=None) -> str:
	row_id = _cstr(getattr(bundle_row, "name", None) or "")
	if not row_id and bundle_row_idx is not None:
		row_id = f"idx{cint(bundle_row_idx)}"
	return f"{row_id}::" if row_id else ""


def _spr_planned_pcs_per_bundle(bundle_row) -> float:
	pkts = cint(getattr(bundle_row, "pkts_per_bundle", 0) or 0)
	pcs = cint(getattr(bundle_row, "pcs_per_packet", 0) or 0)
	tpb = flt(getattr(bundle_row, "total_pcs_per_bundle", 0) or 0)
	if tpb <= 0 and pkts > 0 and pcs > 0:
		tpb = flt(pkts * pcs)
	n_boxes = flt(getattr(bundle_row, "no_of_boxes", 0) or 0)
	if tpb <= 0 and n_boxes > 0 and pcs > 0:
		tpb = flt(n_boxes * pcs)
	return flt(tpb)


def _spr_planned_pcs_per_bundle_entry(bundle_row, bundle_index: int, n_entries: int, is_box_bag: bool = False) -> float:
	"""Per roll line: box / W-CUT bag = pcs per box (e.g. 200), not order total ÷ boxes."""
	n_entries = cint(n_entries) or 1
	if is_box_bag:
		pcs = cint(getattr(bundle_row, "pcs_per_packet", 0) or 0)
		if pcs > 0:
			return flt(pcs)
		tpb = flt(getattr(bundle_row, "total_pcs_per_bundle", 0) or 0)
		n_boxes = cint(getattr(bundle_row, "no_of_boxes", 0) or 0)
		if tpb > 0 and n_boxes > 1:
			per_box = flt(tpb) / flt(n_boxes)
			if per_box > 0:
				return flt(per_box)
		if tpb > 0:
			return flt(tpb)
		return 0.0
	return _spr_planned_pcs_per_bundle(bundle_row)


def _spr_bundle_row_by_key(spr_doc, bundle_row_name=None, bundle_row_idx=None):
	rows = getattr(spr_doc, "bundle_calculation", None) or []
	if bundle_row_name:
		for r in rows:
			if r.name == bundle_row_name:
				return r
	if bundle_row_idx is not None:
		idx = cint(bundle_row_idx)
		if 0 <= idx < len(rows):
			return rows[idx]
	return None


def _spr_item_line_from_bundle(
	pp_name,
	bundle_row,
	bundle_index: int,
	wo: dict,
	order_code: str,
	bundle_row_idx=None,
	is_box_bag: bool = False,
	n_entries: int = 1,
):
	"""Build one Roll Production Result line for sheet-cutting / box-bag bundle Create Entry."""
	item_code = _cstr(getattr(bundle_row, "item_code", None) or wo.get("production_item"))
	if not item_code:
		frappe.throw(_("Item Code is missing on the bundle row and Work Order"))
	item_name = frappe.db.get_value("Item", item_code, "item_name") or ""
	specs = _spr_resolve_roll_line_specs_from_item_code(item_code, item_name)
	quality = specs.get("quality") or ""
	color = specs.get("color") or ""
	gsm = cint(specs.get("gsm") or 0)
	sz_from_item = specs.get("sheet_size") or ""
	w_from_item = flt(specs.get("width_inch") or 0)
	pcs_per_bundle = _spr_planned_pcs_per_bundle_entry(
		bundle_row, bundle_index, n_entries, is_box_bag=is_box_bag
	)
	ordered_len = _pp_length_per_roll_for_item(
		pp_name,
		item_code,
		_cstr(wo.get("production_plan_item") or getattr(bundle_row, "job", None)),
	)
	spi_meta = frappe.get_meta("Shaft Production Run Item")
	row = {
		"work_order": wo.get("name"),
		"item_code": item_code,
		"item_name": item_name,
		"quality": quality,
		"gsm": gsm,
		"planned_qty": 0,
		"job": _spr_bundle_job_tag(bundle_row, bundle_index, bundle_row_idx),
		"batch_no": "",
		"party_code": order_code or get_order_code(frappe.get_doc("Work Order", wo["name"])),
		"uom": _item_stock_uom_for_spr(item_code),
		"roll_no": 0,
		"meter_roll": flt(ordered_len) if ordered_len > 0 else 0,
		"produced_length_mtrs": 0,
		"net_weight": 0,
		"gross_weight": 0,
		"width_inch": w_from_item if w_from_item > 0 else 0,
		"color": color,
	}
	if is_box_bag:
		bag_sz = _cstr(
			getattr(bundle_row, "bag_size", None)
			or getattr(bundle_row, "sheet_cutting_size", None)
			or specs.get("bag_size")
			or sz_from_item
		)
		if not bag_sz and item_code:
			bag_sz = _spr_bag_size_from_item_code(item_code)
		if spi_meta.has_field("custom_bag_size") and bag_sz:
			row["custom_bag_size"] = bag_sz
		if w_from_item > 0 and spi_meta.has_field("width_inch"):
			row["width_inch"] = flt(w_from_item)
	elif spi_meta.has_field("custom_sheet_size"):
		sz = _cstr(specs.get("sheet_size") or "").strip()
		if not sz:
			sz = _spr_sheet_size_from_item_code(item_code)
		if not sz:
			sz = _cstr(getattr(bundle_row, "sheet_cutting_size", None))
		row["custom_sheet_size"] = sz or None
		if w_from_item > 0 and spi_meta.has_field("width_inch"):
			row["width_inch"] = flt(w_from_item)
	if spi_meta.has_field("custom_planned_sheets_pcs") and not is_box_bag:
		row["custom_planned_sheets_pcs"] = pcs_per_bundle
	elif spi_meta.has_field("planned_qty") and not is_box_bag:
		row["planned_qty"] = pcs_per_bundle
	if spi_meta.has_field("custom_planned_bag_pcs"):
		row["custom_planned_bag_pcs"] = pcs_per_bundle
	if spi_meta.has_field("custom_total_produced_sheets"):
		row["custom_total_produced_sheets"] = 0
	if spi_meta.has_field("custom_achieved_bag_pcs"):
		row["custom_achieved_bag_pcs"] = 0
	return row


@frappe.whitelist()
def build_spr_bundle_result_lines_for_row(
	shaft_production_run,
	bundle_row_name=None,
	bundle_row_idx=None,
):
	"""Append Roll Production Result lines for one bundle row (no_of_bundles lines)."""
	if not shaft_production_run or not frappe.db.exists("Shaft Production Run", shaft_production_run):
		frappe.throw(_("Save Shaft Production Run first"))
	spr_doc = frappe.get_doc("Shaft Production Run", shaft_production_run)
	if cint(spr_doc.docstatus) != 0:
		frappe.throw(_("Cannot add roll lines to a submitted Shaft Production Run"))
	if not (cint(getattr(spr_doc, "custom_is_sheet_cutting", 0)) or cint(getattr(spr_doc, "custom_is_box_bag", 0))):
		frappe.throw(_("Bundle Create Entry is only for sheet-cutting / bag SPR"))
	pp_name = get_pp_from_spr(shaft_production_run)
	if not pp_name:
		frappe.throw(_("Production Plan not found on this Shaft Production Run"))
	bundle_row = _spr_bundle_row_by_key(spr_doc, bundle_row_name, bundle_row_idx)
	if not bundle_row:
		frappe.throw(_("Bundle Calculation row not found"))
	n_bundles = cint(getattr(bundle_row, "no_of_bundles", 0) or 0)
	if cint(getattr(spr_doc, "custom_is_box_bag", 0)) and n_bundles < 1:
		n_bundles = cint(getattr(bundle_row, "no_of_boxes", 0) or 0)
	if n_bundles < 1:
		frappe.throw(_("No of Bundles / No of Boxes must be at least 1"))
	ic = _cstr(getattr(bundle_row, "item_code", None))
	wo = _resolve_wo_for_pp_item_code(pp_name, ic)
	if not wo:
		frappe.throw(_("No Work Order found for item {0} on Production Plan {1}").format(ic, pp_name))
	order_code = _cstr(getattr(spr_doc, "custom_order_code", None) or getattr(bundle_row, "order_code", None))
	resolved_idx = bundle_row_idx
	rows = list(getattr(spr_doc, "bundle_calculation", None) or [])
	if resolved_idx is None and bundle_row_name:
		for i, r in enumerate(rows):
			if r.name == bundle_row_name:
				resolved_idx = i
				break
	if resolved_idx is None:
		try:
			resolved_idx = rows.index(bundle_row)
		except ValueError:
			resolved_idx = max(cint(getattr(bundle_row, "idx", 0)) - 1, 0)
	is_bb = cint(getattr(spr_doc, "custom_is_box_bag", 0))
	lines = []
	for i in range(n_bundles):
		lines.append(
			_spr_item_line_from_bundle(
				pp_name,
				bundle_row,
				i + 1,
				wo,
				order_code,
				bundle_row_idx=resolved_idx,
				is_box_bag=bool(is_bb),
				n_entries=n_bundles,
			)
		)
	return lines


def _spr_sum_produced_sheets_for_bundle_row(spr_doc, bundle_row, bundle_row_idx=None) -> float:
	"""Sum Produced Sheets (PCS) from roll lines linked to one bundle_calculation row."""
	prefix = _spr_bundle_job_prefix(bundle_row, bundle_row_idx)
	spi_meta = frappe.get_meta("Shaft Production Run Item")
	pcs_field = (
		"custom_total_produced_sheets"
		if spi_meta.has_field("custom_total_produced_sheets")
		else None
	)
	if not pcs_field:
		return 0.0
	total = 0.0
	prefix_hits = 0
	ic = _cstr(getattr(bundle_row, "item_code", None))
	wo = _cstr(getattr(bundle_row, "work_order", None))
	n_bundles = cint(getattr(bundle_row, "no_of_bundles", 0) or 0)
	for it in spr_doc.get("items") or []:
		job = _cstr(getattr(it, "job", None))
		matched = bool(prefix and job.startswith(prefix))
		if matched:
			prefix_hits += 1
			total += flt(getattr(it, pcs_field, 0) or 0)
	if prefix_hits:
		return flt(total, 0)
	# Legacy rows: job was "1", "2", … before bundle-row tags were introduced.
	for it in spr_doc.get("items") or []:
		job = _cstr(getattr(it, "job", None))
		if _cstr(getattr(it, "item_code", None)) != ic or _cstr(getattr(it, "work_order", None)) != wo:
			continue
		try:
			jn = int(job)
		except (TypeError, ValueError):
			continue
		if n_bundles > 0 and not (1 <= jn <= n_bundles):
			continue
		total += flt(getattr(it, pcs_field, 0) or 0)
	return flt(total, 0)


def _spr_sum_net_weight_for_bundle_row(spr_doc, bundle_row, bundle_row_idx=None) -> float:
	"""Sum net_weight (Kg) on roll lines linked to one bundle_calculation row."""
	prefix = _spr_bundle_job_prefix(bundle_row, bundle_row_idx)
	total = 0.0
	prefix_hits = 0
	ic = _cstr(getattr(bundle_row, "item_code", None))
	wo = _cstr(getattr(bundle_row, "work_order", None))
	n_bundles = cint(getattr(bundle_row, "no_of_bundles", 0) or 0)
	for it in spr_doc.get("items") or []:
		job = _cstr(getattr(it, "job", None))
		if prefix and job.startswith(prefix):
			prefix_hits += 1
			total += flt(getattr(it, "net_weight", 0) or 0, 2)
	if prefix_hits:
		return flt(total, 2)
	for it in spr_doc.get("items") or []:
		job = _cstr(getattr(it, "job", None))
		if _cstr(getattr(it, "item_code", None)) != ic or _cstr(getattr(it, "work_order", None)) != wo:
			continue
		try:
			jn = int(job)
		except (TypeError, ValueError):
			continue
		if n_bundles > 0 and not (1 <= jn <= n_bundles):
			continue
		total += flt(getattr(it, "net_weight", 0) or 0, 2)
	return flt(total, 2)


def sync_bundle_total_produced_sheets_for_doc(spr_doc) -> None:
	"""Update bundle_calculation.total_produced_sheets from roll line sums."""
	if not spr_doc or not hasattr(spr_doc, "bundle_calculation"):
		return
	rows = list(spr_doc.get("bundle_calculation") or [])
	for idx, br in enumerate(rows):
		br.total_produced_sheets = _spr_sum_produced_sheets_for_bundle_row(spr_doc, br, bundle_row_idx=idx)


def _spr_sum_produced_bag_pcs_for_bundle_row(spr_doc, bundle_row, bundle_row_idx=None) -> float:
	"""Sum Achieved Bag PCS from roll lines linked to one bundle_calculation row."""
	prefix = _spr_bundle_job_prefix(bundle_row, bundle_row_idx)
	total = 0.0
	prefix_hits = 0
	ic = _cstr(getattr(bundle_row, "item_code", None))
	wo = _cstr(getattr(bundle_row, "work_order", None))
	n_bundles = cint(getattr(bundle_row, "no_of_bundles", 0) or 0)
	n_boxes = cint(getattr(bundle_row, "no_of_boxes", 0) or 0)
	n_rows = n_bundles if n_bundles > 0 else n_boxes
	for it in spr_doc.get("items") or []:
		job = _cstr(getattr(it, "job", None))
		matched = bool(prefix and job.startswith(prefix))
		if matched:
			prefix_hits += 1
			total += flt(getattr(it, "custom_achieved_bag_pcs", 0) or 0)
	if prefix_hits:
		return flt(total, 0)
	for it in spr_doc.get("items") or []:
		job = _cstr(getattr(it, "job", None))
		if _cstr(getattr(it, "item_code", None)) != ic or _cstr(getattr(it, "work_order", None)) != wo:
			continue
		try:
			jn = int(job)
		except (TypeError, ValueError):
			continue
		if n_rows > 0 and not (1 <= jn <= n_rows):
			continue
		total += flt(getattr(it, "custom_achieved_bag_pcs", 0) or 0)
	return flt(total, 0)


def sync_bundle_total_produced_bag_pcs_for_doc(spr_doc) -> None:
	"""Update bundle_calculation.total_produced_bag_pcs from roll line achieved bag pcs sums."""
	if not spr_doc or not hasattr(spr_doc, "bundle_calculation"):
		return
	rows = list(spr_doc.get("bundle_calculation") or [])
	for idx, br in enumerate(rows):
		if hasattr(br, "total_produced_bag_pcs"):
			br.total_produced_bag_pcs = _spr_sum_produced_bag_pcs_for_bundle_row(spr_doc, br, bundle_row_idx=idx)


def sync_bundle_total_achieved_weight_for_doc(spr_doc) -> None:
	"""Update bundle_calculation.total_achieved_weight from roll line net_weight sums."""
	if not spr_doc or not hasattr(spr_doc, "bundle_calculation"):
		return
	rows = list(spr_doc.get("bundle_calculation") or [])
	for idx, br in enumerate(rows):
		br.total_achieved_weight = _spr_sum_net_weight_for_bundle_row(spr_doc, br, bundle_row_idx=idx)


def sync_bundle_consumed_meter_header(spr_doc) -> None:
	"""Sheet cutting: SPR header consumed meters = sum of bundle Consumed Mtrs."""
	if not spr_doc or not (cint(getattr(spr_doc, "custom_is_sheet_cutting", 0)) or cint(getattr(spr_doc, "custom_is_box_bag", 0))):
		return
	meta = frappe.get_meta("Shaft Production Run")
	if not meta.has_field("custom_total_achieved_meter"):
		return
	total = sum(
		flt(getattr(br, "total_consumed_meter", 0) or 0, 2) for br in (spr_doc.get("bundle_calculation") or [])
	)
	spr_doc.custom_total_achieved_meter = flt(total, 2)


def _expand_spr_name_tokens_csv(spr_csv: str) -> list[str]:
	out = []
	for part in _cstr(spr_csv).split(","):
		p = part.strip()
		if p and p not in out:
			out.append(p)
	return out


def _sheet_cutting_spr_metrics(spr_names, pp_id=None):
	"""Aggregate sheet PCS and meters for order table / reporting."""
	metrics = {
		"total_planned_sheet_pcs": 0.0,
		"total_produced_sheet_pcs": 0.0,
		"produced_meter": 0.0,
		"achieved_kg": 0.0,
	}
	spr_list = []
	for nm in spr_names or []:
		spr_list.extend(_expand_spr_name_tokens_csv(nm))
	spr_list = [s for s in spr_list if s and frappe.db.exists("Shaft Production Run", s)]
	if not spr_list and pp_id and frappe.db.has_column("Production Plan", "custom_shaft_production_run_id"):
		pass
	if frappe.db.exists("DocType", BUNDLE_CALC_DOCTYPE):
		for spr_name in spr_list:
			try:
				spr = frappe.get_doc("Shaft Production Run", spr_name)
			except Exception:
				continue
			is_sub = cint(spr.docstatus) == 1
			for br in getattr(spr, "bundle_calculation", None) or []:
				metrics["total_planned_sheet_pcs"] += _spr_planned_pcs_per_bundle(br)
				if is_sub:
					metrics["total_produced_sheet_pcs"] += flt(getattr(br, "total_produced_sheets", 0) or 0)
					metrics["produced_meter"] += flt(getattr(br, "total_consumed_meter", 0) or 0)
	elif pp_id:
		for src in _read_pp_bundle_calculation_rows(pp_id):
			pkts = cint(src.get("pkts_per_bundle") or 0)
			pcs = cint(src.get("pcs_per_packet") or 0)
			tpb = flt(src.get("total_pcs_per_bundle") or 0)
			if tpb <= 0 and pkts > 0 and pcs > 0:
				tpb = flt(pkts * pcs)
			metrics["total_planned_sheet_pcs"] += tpb
	spr_cols = set(frappe.db.get_table_columns("Shaft Production Run Item") or [])
	weight_expr = "IFNULL(sri.net_weight, 0)" if "net_weight" in spr_cols else "0"
	len_expr = "IFNULL(sri.produced_length_mtrs, 0)" if "produced_length_mtrs" in spr_cols else "0"
	pcs_expr = "IFNULL(sri.custom_total_produced_sheets, 0)" if "custom_total_produced_sheets" in spr_cols else "0"
	if spr_list:
		placeholders = ",".join(["%s"] * len(spr_list))
		for r in frappe.db.sql(
			f"""
			SELECT
				sri.parent,
				SUM({weight_expr}) AS kgs,
				SUM({len_expr}) AS len_m,
				SUM({pcs_expr}) AS pcs_sum,
				MAX(spr.docstatus) AS spr_docstatus
			FROM `tabShaft Production Run Item` sri
			INNER JOIN `tabShaft Production Run` spr ON spr.name = sri.parent
			WHERE sri.parent IN ({placeholders})
			GROUP BY sri.parent
			""",
			tuple(spr_list),
			as_dict=True,
		) or []:
			if cint(r.get("spr_docstatus")) != 1:
				continue
			metrics["achieved_kg"] += flt(r.get("kgs"))
			if metrics["produced_meter"] <= 0:
				metrics["produced_meter"] += flt(r.get("len_m"))
			if metrics["total_produced_sheet_pcs"] <= 0:
				metrics["total_produced_sheet_pcs"] += flt(r.get("pcs_sum"))
	return metrics


@frappe.whitelist()
def get_production_plan_wo_summary(production_plan):
	"""Work Orders linked to this PP: status, order qty, pending qty — for desk popup after PP is set."""
	if not production_plan or not frappe.db.exists("Production Plan", production_plan):
		return []
	return frappe.db.sql(
		"""
		SELECT
			wo.name AS work_order,
			wo.status,
			IFNULL(wo.qty, 0) AS order_qty,
			GREATEST(0, IFNULL(wo.qty, 0) - IFNULL(wo.produced_qty, 0)) AS pending_qty
		FROM `tabWork Order` wo
		WHERE wo.production_plan = %(pp)s
		  AND wo.docstatus < 2
		ORDER BY wo.name
		""",
		{"pp": production_plan},
		as_dict=True,
	)


def _count_combination_segments(combination) -> int:
	"""How many width slots in a combination string like '48\\" + 37\\" + ...'."""
	if not combination:
		return 1
	parts = [p.strip() for p in re.split(r"\+", str(combination)) if p.strip()]
	return max(1, len(parts))


def _parse_net_weight_kg_parts(net_weight) -> list[float]:
	"""Parse '89.61 + 6.2' style net weight from shaft job into kg numbers."""
	if not net_weight:
		return []
	s = str(net_weight).strip()
	if not s:
		return []
	out: list[float] = []
	for part in re.split(r"\s*\+\s*", s):
		part = part.strip()
		if not part:
			continue
		m = re.search(r"(\d+(?:\.\d+)?)", part.replace(",", ""))
		if m:
			out.append(flt(m.group(1)))
	return out


def _segment_weights_kg(job_row, segs: int) -> list[float]:
	"""Per-combination-segment kg; falls back to equal split of total target weight."""
	if segs < 1:
		segs = 1
	parts = _parse_net_weight_kg_parts(getattr(job_row, "net_weight", None))
	tw = flt(getattr(job_row, "total_weight", 0) or 0)
	if len(parts) >= segs:
		return [flt(x) for x in parts[:segs]]
	if parts:
		avg = sum(parts) / len(parts)
		while len(parts) < segs:
			parts.append(avg)
		return [flt(x) for x in parts[:segs]]
	if tw > 0:
		return [tw / segs] * segs
	return [0.0] * segs


def _planned_qty_for_roll_line(job_row, roll_index: int, segs: int) -> float:
	"""Planned qty = net weight (kg) for this combination segment (e.g. 48\"ΓåÆ89.61, 37\"ΓåÆ69.08)."""
	if segs < 1:
		segs = 1
	seg_weights = _segment_weights_kg(job_row, segs)
	seg_i = roll_index % segs
	seg_kg = seg_weights[seg_i] if seg_i < len(seg_weights) else 0.0
	return round(flt(seg_kg), 3)


def _planned_kg_for_spr_result_roll(job_row, roll_index: int, n_rolls: int, segs: int) -> float:
	"""Planned kg for one Produced Rolls line: per physical roll, not full job total on every line.

	When ``net_weight`` lists one value per roll, use that. When it lists one value per combination
	segment, cycle segments as rolls repeat (multi-shaft). Otherwise split ``total_weight`` evenly
	across ``n_rolls`` (e.g. 97.08 kg / 2 rolls ΓåÆ 48.54 each).
	"""
	if n_rolls < 1:
		n_rolls = 1
	if segs < 1:
		segs = 1
	tw = flt(getattr(job_row, "total_weight", 0) or 0)
	parts = _parse_net_weight_kg_parts(getattr(job_row, "net_weight", None))

	if len(parts) == n_rolls:
		return round(flt(parts[roll_index]), 3)

	if parts and segs > 1 and len(parts) >= segs:
		return round(flt(parts[roll_index % segs]), 3)

	if tw > 0:
		return round(tw / n_rolls, 3)
	return 0.0


@frappe.whitelist()
def get_next_spr_batch_numbers(
	shaft_production_run,
	count,
	client_max_roll=None,
	run_date=None,
	custom_unit=None,
	shift=None,
	client_series_prefix=None,
):
	"""
	Preview batch/roll numbers for new rows (e.g. after Create Entry) without submitting SPR.
	Requires run_date, custom_unit, shift. Optional client_max_roll = highest roll index already on the form.

	Pass run_date, custom_unit, shift from the desk form when the document is saved but header
	fields were just edited and not yet re-saved — otherwise get_doc() would see stale DB values.
	"""
	count = cint(count)
	if count < 1:
		return []
	if not shaft_production_run or not frappe.db.exists("Shaft Production Run", shaft_production_run):
		frappe.throw(_("Save the Shaft Production Run first"))
	doc = frappe.get_doc("Shaft Production Run", shaft_production_run)
	if run_date not in (None, ""):
		doc.run_date = run_date
	if custom_unit not in (None, "") and str(custom_unit).strip():
		doc.custom_unit = custom_unit
	if shift not in (None, "") and str(shift).strip():
		doc.shift = shift
	rd_val = doc.run_date
	cu = _cstr(doc.get("custom_unit"))
	sh = _cstr(doc.shift)
	if not rd_val or not cu or not sh:
		frappe.throw(_("Set Run Date, Unit, and Shift to assign batch numbers."))
	rd = getdate(rd_val)
	comp_id, unit_num = doc._batch_prefix_parts()
	root_5 = f"{comp_id}-{unit_num}{rd.month:02d}{rd.year % 100:02d}"
	csp = _cstr(client_series_prefix).strip()
	if csp and csp.startswith(root_5):
		series_prefix = csp
	else:
		series_prefix = doc._resolve_series_prefix(root_5)
	next_roll = doc._next_roll_starting(series_prefix)
	try:
		if client_max_roll is not None and cint(client_max_roll) >= 0:
			next_roll = max(int(next_roll), cint(client_max_roll) + 1)
	except Exception:
		pass
	item_meta = frappe.get_meta("Shaft Production Run Item")
	out = []
	for _i in range(count):
		bn = f"{series_prefix}/{next_roll}"
		rf = item_meta.get_field("roll_no")
		rn = int(next_roll) if rf and rf.fieldtype == "Int" else str(next_roll)
		out.append({"batch_no": bn, "roll_no": rn})
		next_roll += 1
	return out


def _spr_parse_manual_item_codes(sj) -> list[str]:
	"""Parse manual_items from shaft job (comma list or JSON array)."""
	mi = _cstr(getattr(sj, "manual_items", None) or "").strip()
	if not mi:
		return []
	if mi.startswith("["):
		try:
			parsed = json.loads(mi)
			if isinstance(parsed, list):
				return [_cstr(x) for x in parsed if _cstr(x)]
		except Exception:
			pass
	return [_cstr(x) for x in mi.replace("\n", ",").split(",") if _cstr(x)]


def _spr_item_line_from_manual_item(job_row, job_id, item_code, planned_qty, width_inch=None, meter_roll=None):
	item_code = _cstr(item_code)
	item_name = frappe.db.get_value("Item", item_code, "item_name") or ""
	specs = _spr_resolve_roll_line_specs_from_item_code(item_code, item_name)
	_gsm, parsed_width = parse_item_code(item_code)
	if width_inch is not None and flt(width_inch) > 0:
		parsed_width = flt(width_inch)
	gsm = cint(specs.get("gsm") or 0) or (int(flt(_gsm)) if _gsm else 0)
	spi_meta = frappe.get_meta("Shaft Production Run Item")
	row: dict = {
		"item_code": item_code,
		"item_name": item_name,
		"quality": specs.get("quality") or getattr(job_row, "quality", None) or "",
		"gsm": gsm or getattr(job_row, "gsm", None) or 0,
		"planned_qty": flt(planned_qty),
		"job": job_id,
		"batch_no": "",
		"party_code": _cstr(getattr(job_row, "party_code", None) or ""),
		"uom": _item_stock_uom_for_spr(item_code),
		"roll_no": 0,
		"meter_roll": flt(meter_roll) if meter_roll else 0,
		"net_weight": 0,
		"gross_weight": 0,
		"width_inch": parsed_width,
		"color": specs.get("color") or getattr(job_row, "color", None) or "",
	}
	if spi_meta.has_field("custom_fabric_gsm"):
		fab_gsm = _fabric_gsm_from_item_name(item_name) or _fabric_gsm_from_item_name(item_code)
		if fab_gsm > 0:
			row["custom_fabric_gsm"] = fab_gsm
	return row


def _spr_job_max_roll_lines(job_row, spr_doc=None) -> int:
	"""Max Roll Production Result lines allowed for one Available Jobs row."""
	comb = getattr(job_row, "combination", None) or ""
	segs = _count_combination_segments(comb)
	no_shafts = max(1, cint(getattr(job_row, "no_of_shafts", 0) or 0))
	rolls_per_shaft = max(1, cint(getattr(job_row, "no_of_rolls", 0) or 0))

	if spr_doc and spr_doc_is_mix_roll(spr_doc):
		widths = _parse_combination_widths_inches(comb)
		item_codes = _spr_parse_manual_item_codes(job_row)
		n_items = len(item_codes) if item_codes else 0
		if widths:
			return max(1, max(len(widths), n_items) * rolls_per_shaft)
		return max(1, max(no_shafts, n_items) * rolls_per_shaft)

	if segs <= 1:
		return max(1, no_shafts * rolls_per_shaft)
	return max(1, no_shafts * segs * rolls_per_shaft)


def _spr_count_roll_lines_for_job(spr_doc, job_id) -> int:
	job_key = _cstr(job_id).strip()
	if not job_key:
		return 0
	cnt = 0
	for it in spr_doc.get("items") or []:
		if _spr_job_keys_match(_cstr(getattr(it, "job", None)), job_key):
			cnt += 1
	return cnt


def _spr_throw_roll_quota_exceeded(job_id, max_rolls: int, current_rolls: int) -> None:
	frappe.throw(
		_(
			"Maximum {0} roll lines allowed for job {1} ({2} already created). "
			"Use Manual Job for additional production."
		).format(max_rolls, job_id, current_rolls),
		title=_("Roll line limit reached"),
	)


def _build_mix_roll_result_lines_for_job(
	spr_doc, job_row, exact_roll_lines=None, roll_start_index=None
):
	"""Build roll lines for mix-roll SPR from manual_items (no Work Order)."""
	job_id = _spr_job_id(job_row)
	item_codes = _spr_parse_manual_item_codes(job_row)
	if not item_codes:
		frappe.throw(_("Mix roll job {0} has no manual items.").format(job_id))

	comb = getattr(job_row, "combination", None) or ""
	widths = _parse_combination_widths_inches(comb)
	no_shafts = max(1, cint(getattr(job_row, "no_of_shafts", 0) or 0))
	rolls_per_shaft = max(1, cint(getattr(job_row, "no_of_rolls", 0) or 0))
	exact_n = cint(exact_roll_lines or 0)
	start_idx = max(0, cint(roll_start_index or 0))
	max_job_rolls = _spr_job_max_roll_lines(job_row, spr_doc)

	if exact_n > 0:
		current = _spr_count_roll_lines_for_job(spr_doc, job_id)
		if current + exact_n > max_job_rolls:
			_spr_throw_roll_quota_exceeded(job_id, max_job_rolls, current)
		n_rolls = max(1, exact_n)
		planned_total_rolls = max_job_rolls
	elif widths:
		n_rolls = max(len(widths), len(item_codes)) * rolls_per_shaft
		planned_total_rolls = n_rolls
		start_idx = 0
	else:
		n_rolls = max(no_shafts, len(item_codes)) * rolls_per_shaft
		planned_total_rolls = n_rolls
		start_idx = 0

	total_weight = flt(getattr(job_row, "total_weight", None) or 0)
	fallback_planned_each = flt(total_weight / planned_total_rolls) if total_weight > 0 else 0

	meter_roll_job = None
	mr_attr = getattr(job_row, "meter_roll_mtrs", None)
	if mr_attr not in (None, "", 0):
		meter_roll_job = flt(mr_attr)

	lines = []
	for i in range(n_rolls):
		idx = start_idx + i
		item_code = item_codes[idx % len(item_codes)]
		width_inch = widths[idx % len(widths)] if widths else None
		row = _spr_item_line_from_manual_item(
			job_row,
			job_id,
			item_code,
			0,
			width_inch=width_inch,
			meter_roll=meter_roll_job,
		)
		gsm_val = flt(row.get("gsm") or 0)
		w_in = flt(row.get("width_inch") or 0)
		length_m = meter_roll_job or _spr_mix_roll_planned_length_m(row)
		planned_each = compute_mix_roll_planned_qty_kg(gsm_val, w_in, length_m)
		if planned_each <= 0:
			planned_each = fallback_planned_each
		row["planned_qty"] = planned_each
		row["roll_no"] = idx + 1
		lines.append(row)
	return lines


@frappe.whitelist()
def build_spr_roll_result_lines_for_job(
	shaft_production_run,
	job_id,
	lamination_rolls_per_combination=None,
	lamination_exact_roll_lines=None,
	exact_roll_lines=None,
	roll_start_index=None,
):
	"""
	Build Roll Production Result (SPR Item) lines for one job.
	
	Γ£à CORRECT: Extract GSM and WIDTH from Item Name, then match exactly.
	Combination "33+63" cycles rolls through widths [33, 63, 33, 63, ...]
	Each roll matched to correct WO by (GSM, WIDTH) tuple lookup.

	Lamination (104 + Is Lamination): pass ``lamination_rolls_per_combination`` = rolls per combination
	segment; total lines = segments × that number (shaft × roll formula is not used).
	"""
	if not job_id:
		frappe.throw(_("Job ID is required"))
	if not shaft_production_run or not frappe.db.exists("Shaft Production Run", shaft_production_run):
		frappe.throw(_("Save Shaft Production Run first"))
	spr_doc = frappe.get_doc("Shaft Production Run", shaft_production_run)
	if cint(spr_doc.docstatus) != 0:
		frappe.throw(_("Cannot add roll lines to a submitted Shaft Production Run"))
	job_row = None
	for j in _spr_job_rows(spr_doc):
		if _spr_job_keys_match(_spr_job_id(j), job_id):
			job_row = j
			break
	if not job_row:
		frappe.throw(_("Job {0} not found in Available Jobs").format(job_id))

	has_pinned_wos = bool(_cstr(getattr(job_row, "work_orders", None) or "").strip())
	if not has_pinned_wos and (
		spr_doc_is_mix_roll(spr_doc)
		or (
			_spr_is_manual_shaft_job(job_row)
			and _spr_parse_manual_item_codes(job_row)
			and not _cstr(getattr(spr_doc, "production_plan", None))
		)
	):
		return _build_mix_roll_result_lines_for_job(
			spr_doc,
			job_row,
			exact_roll_lines=exact_roll_lines,
			roll_start_index=roll_start_index,
		)

	pp_name = get_pp_from_spr(shaft_production_run)
	if not pp_name and has_pinned_wos:
		pp_name = None
	elif not pp_name or not frappe.db.exists("Production Plan", pp_name):
		if has_pinned_wos:
			pp_name = None
		else:
			frappe.throw(_("Production Plan not found on this Shaft Production Run"))

	no_shafts = int(flt(getattr(job_row, "no_of_shafts", 0) or 0))
	if no_shafts < 1:
		no_shafts = 1
	comb = getattr(job_row, "combination", None) or ""
	segs = _count_combination_segments(comb)
	rolls_per_shaft = cint(getattr(job_row, "no_of_rolls", 0) or 0)
	if rolls_per_shaft < 1:
		rolls_per_shaft = 1

	lam_exact_n = cint(lamination_exact_roll_lines or 0)
	lam_n = cint(lamination_rolls_per_combination or 0)
	exact_n = cint(exact_roll_lines or 0)
	if exact_n > 0:
		n_rolls = max(1, exact_n)
	elif lam_exact_n > 0:
		if not spr_doc_is_lamination(spr_doc):
			frappe.throw(
				_("Exact roll-line add mode is only for lamination: tick Is Lamination and use a 104 or 107 production plan.")
			)
		n_rolls = max(1, lam_exact_n)
	elif lam_n > 0:
		if not spr_doc_is_lamination(spr_doc):
			frappe.throw(
				_("Rolls-per-combination mode is only for lamination: tick Is Lamination and use a 104 or 107 production plan.")
			)
		n_rolls = max(1, segs * lam_n)
	elif spr_doc_is_lamination(spr_doc):
		frappe.throw(
			_("For lamination runs, enter **Number of rolls per combination** when clicking Create Entry (e.g. 10 rolls × 2 combinations = 20 lines).")
		)
	elif segs <= 1:
		n_rolls = max(1, no_shafts * rolls_per_shaft)
	else:
		n_rolls = max(1, no_shafts * segs * rolls_per_shaft)

	start_idx = max(0, cint(roll_start_index or 0))
	max_job_rolls = _spr_job_max_roll_lines(job_row, spr_doc)
	use_quota_append = exact_n > 0 and not spr_doc_is_lamination(spr_doc) and not lam_exact_n and lam_n <= 0
	if use_quota_append:
		current = _spr_count_roll_lines_for_job(spr_doc, job_id)
		if current + exact_n > max_job_rolls:
			_spr_throw_roll_quota_exceeded(job_id, max_job_rolls, current)
		planned_total_rolls = max_job_rolls
		roll_indices = range(start_idx, start_idx + exact_n)
	else:
		planned_total_rolls = n_rolls
		roll_indices = range(n_rolls)
		start_idx = 0

	shaft_combination = get_shaft_combination(pp_name, job_id)
	if getattr(job_row, "combination", None) and not shaft_combination:
		shaft_combination = job_row.combination

	wo_list = _get_work_orders_for_spr_job(pp_name, spr_doc, job_row)
	if not wo_list:
		frappe.throw(_("No Work Orders for job {0}").format(job_id))

	# Extract job GSM
	job_gsm = None
	if getattr(job_row, "gsm", None) not in (None, 0, "0"):
		try:
			job_gsm = int(flt(job_row.gsm))
		except Exception:
			pass
	
	individual_widths = _parse_combination_widths_inches(comb)

	gsm_width_to_wo = _build_gsm_width_to_wo_map_from_item_names(wo_list)

	meter_roll_job = None
	mr_attr = getattr(job_row, "meter_roll_mtrs", None)
	if mr_attr not in (None, "", 0):
		meter_roll_job = flt(mr_attr)

	spi_meta = frappe.get_meta("Shaft Production Run Item")
	fabric_gsm = _fabric_gsm_from_planning_for_pp(pp_name) if spr_doc_is_lamination(spr_doc) else 0

	lines = []
	for roll_i, idx in enumerate(roll_indices):
		individual_width = None
		if individual_widths:
			individual_width = individual_widths[idx % len(individual_widths)]

		wo = None
		if job_gsm is not None and individual_width is not None:
			iw = round(flt(individual_width), 1)
			key = (job_gsm, iw)
			if key in gsm_width_to_wo:
				wo = gsm_width_to_wo[key]
			else:
				for (g, w), wobj in gsm_width_to_wo.items():
					if int(g) == int(job_gsm) and abs(flt(w) - iw) <= 0.75:
						wo = wobj
						break
			if wo:
				frappe.logger().info(
					f"[SPR] Roll {idx + 1}: GSM {job_gsm} + Width {iw}\" ΓåÆ WO {wo['name']}"
				)

		if wo is None:
			wo = wo_list[0]
			frappe.logger().warning(
				f"[SPR WARNING] No exact match for GSM {job_gsm}, Width {individual_width}, using {wo['name']}"
			)

		if spr_doc_is_lamination(spr_doc):
			planned_qty = 0.0
		else:
			planned_qty = _planned_kg_for_spr_result_roll(job_row, idx, planned_total_rolls, segs)
		row = _spr_item_line_from_wo(pp_name, job_id, shaft_combination, planned_qty, wo)
		if not _cstr(row.get("party_code")) and _cstr(getattr(job_row, "party_code", None)):
			row["party_code"] = _cstr(job_row.party_code)
		if job_gsm is not None:
			row["gsm"] = job_gsm
		if individual_width is not None and flt(individual_width) > 0:
			row["width_inch"] = flt(individual_width)
		if meter_roll_job is not None and meter_roll_job > 0:
			row["meter_roll"] = meter_roll_job
			# Lamination add-flow: removed auto-fill of produced_length_mtrs based on user request

		# Fabric GSM: prefer Planning Table join result; fallback to parsing F-<N> from item name.
		eff_fabric_gsm = fabric_gsm
		if eff_fabric_gsm <= 0 and spr_doc_is_lamination(spr_doc):
			item_nm = row.get("item_name") or ""
			item_cd = row.get("item_code") or ""
			eff_fabric_gsm = _fabric_gsm_from_item_name(item_nm) or _fabric_gsm_from_item_name(item_cd)
		if eff_fabric_gsm > 0 and spi_meta.has_field("custom_fabric_gsm"):
			row["custom_fabric_gsm"] = int(eff_fabric_gsm)

		row["roll_no"] = idx + 1
		lines.append(row)
	return lines


def _build_gsm_width_to_wo_map_from_item_names(wo_list: list) -> dict:
	"""
	Γ£à Extract GSM and WIDTH from Item Code (the source of truth).
	Item Code format: "1001050010251600"
	  - Positions [9:12] = GSM (e.g., "025" = 25)
	  - Positions [12:16] = WIDTH in MM (e.g., "1600" = 1600mm = 63 inches)
	
	Returns: {(25, 63.0): WO, (90, 63.0): WO, ...}
	Keeps FIRST occurrence of each (GSM, WIDTH) pair.
	"""
	gsm_width_to_wo = {}
	
	for wo in wo_list:
		try:
			production_item = frappe.db.get_value("Work Order", wo["name"], "production_item")
			if not production_item:
				frappe.logger().warning(f"[WO MAP] No production_item for WO {wo['name']}")
				continue
			
			# Γ£à Parse item code to get GSM and WIDTH (SOURCE OF TRUTH)
			gsm, width = parse_item_code(_cstr(production_item))
			
			if gsm > 0 and width > 0:
				key = (gsm, width)
				# Γ£à KEEP FIRST OCCURRENCE: Don't overwrite if key already exists
				if key not in gsm_width_to_wo:
					gsm_width_to_wo[key] = wo
					frappe.logger().info(f"[WO MAP] {wo['name']} ΓåÆ GSM {gsm} + WIDTH {width}\" (from item code: {production_item})")
				else:
					# Duplicate width found - log it but keep first WO
					frappe.logger().info(f"[WO MAP] Note: {wo['name']} also has GSM {gsm} + WIDTH {width}\", but keeping first WO {gsm_width_to_wo[key]['name']}")
			else:
				frappe.logger().warning(f"[WO MAP] Could not parse item code {production_item} (GSM={gsm}, WIDTH={width})")
		
		except Exception as e:
			frappe.logger().warning(f"[WO MAP ERROR] WO {wo.get('name')}: {str(e)}")
	
	return gsm_width_to_wo


@frappe.whitelist()
def get_job_rows_for_production_plan(production_plan):
	if not production_plan:
		return []
	if not frappe.db.exists("Production Plan", production_plan):
		frappe.throw(_("Production Plan {0} not found").format(production_plan))
	custom_sd = _build_shaft_jobs_from_custom_shaft_details(production_plan)
	if custom_sd is not None:
		return custom_sd
	detailed = _build_shaft_jobs_from_pp_details(production_plan)
	if detailed is not None:
		return detailed
	rows = frappe.db.sql(
		"""
		SELECT wo.production_plan_item AS job_no, SUM(wo.qty) AS total_weight
		FROM `tabWork Order` wo
		WHERE wo.production_plan = %(pp)s
		  AND wo.docstatus < 2
		  AND IFNULL(wo.production_plan_item, '') != ''
		GROUP BY wo.production_plan_item
		ORDER BY MIN(wo.creation)
		""",
		{"pp": production_plan},
		as_dict=True,
	)
	job_meta = frappe.get_meta("Shaft Production Run Job")
	out = []
	for i, r in enumerate(rows):
		row = {"job_id": r.job_no, "total_weight": flt(r.total_weight)}
		if job_meta.has_field("production_plan_item"):
			row["production_plan_item"] = r.job_no
		comb = None
		if job_meta.has_field("combination"):
			comb = get_shaft_combination(production_plan, r.job_no)
			if comb:
				row["combination"] = comb
		m = dict(row)
		job_gsm = None
		if m.get("gsm") is not None:
			try:
				job_gsm = int(flt(m.get("gsm")))
			except Exception:
				pass
		wos = _resolve_wos_for_pp_job_row(
			production_plan,
			ppi=m.get("production_plan_item"),
			job_id=_cstr(m.get("job_id")),
			row_index=i,
			combination=m.get("combination"),
			job_gsm=job_gsm,
		)
		if job_meta.has_field("work_orders") and wos:
			row["work_orders"] = ", ".join(w["name"] for w in wos)
		_fill_party_code_from_resolved_wos(row, job_meta, wos)
		out.append(row)
	return out


def _spr_job_rows(spr_doc):
	return getattr(spr_doc, "shaft_jobs", None) or getattr(spr_doc, "jobs", None) or []


def _spr_job_id(job):
	return getattr(job, "job_id", None) or getattr(job, "job_no", None)


def _spr_shaft_job_for_roll(spr_doc, job_id_str):
	pid = _cstr(job_id_str)
	if not pid:
		return None
	for sj in _spr_job_rows(spr_doc):
		if _spr_job_keys_match(_spr_job_id(sj), pid):
			return sj
		if _cstr(getattr(sj, "production_plan_item", None)) == pid:
			return sj
	return None


def _spr_numeric_str_ok_for_eq(s: str) -> bool:
	s = (s or "").strip()
	if not s:
		return False
	try:
		float(s)
		return True
	except ValueError:
		return False


def _spr_job_keys_match(a, b) -> bool:
	"""Match job ids across 1 / 1.0 / '1 ' and identical non-numeric strings."""
	na = _cstr(a)
	nb = _cstr(b)
	if na == nb:
		return True
	if not na or not nb:
		return False
	if _spr_numeric_str_ok_for_eq(na) and _spr_numeric_str_ok_for_eq(nb):
		return flt(na) == flt(nb)
	return False


def _spr_item_roll_matches_bundle_job(sj, it, job_id: str) -> bool:
	if _spr_job_keys_match(getattr(it, "job", None), job_id):
		return True
	if sj:
		jj = _cstr(getattr(it, "job", None))
		ppi = _cstr(getattr(sj, "production_plan_item", None))
		if ppi and jj == ppi:
			return True
	return False


def _spr_resolve_item_job_to_canonical_id(spr_doc, it) -> str:
	"""Map a roll line's job field to shaft_jobs job_id (handles numeric drift + PP item name)."""
	raw = _cstr(getattr(it, "job", None))
	if not raw:
		return ""
	for sj in _spr_job_rows(spr_doc):
		canon = _cstr(_spr_job_id(sj))
		if _spr_job_keys_match(raw, canon):
			return canon
		ppi = _cstr(getattr(sj, "production_plan_item", None))
		if ppi and raw == ppi:
			return canon
	return raw


def _spr_job_product_code(sj):
	"""Product item from Available Jobs: manual_items, else Work Order production_item."""
	if not sj:
		return ""
	mi = _cstr(getattr(sj, "manual_items", None) or "").strip()
	if mi:
		return mi
	wos = _cstr(getattr(sj, "work_orders", None) or "")
	for raw in wos.replace("\n", ",").split(","):
		wo = raw.strip()
		if wo and frappe.db.exists("Work Order", wo):
			pi = frappe.db.get_value("Work Order", wo, "production_item")
			if pi:
				return _cstr(pi)
	return ""


def _spr_bundle_job_label(sj):
	jid = _cstr(_spr_job_id(sj))
	comb = _cstr(getattr(sj, "combination", None) or "").strip()
	if comb:
		return f"Job {jid} — {comb}"
	prod = _spr_job_product_code(sj) or ""
	if prod:
		return f"Job {jid} — {prod}"
	return f"Job {jid}"


def _spr_bundle_segment_widths_for_job(spr_doc, sj) -> list[float]:
	"""Per-job width options for Bundle Packaging: combination segments / WO item widths / existing roll widths."""
	out: list[float] = []
	if not sj:
		return out
	comb = _cstr(getattr(sj, "combination", None) or "")
	for w in _parse_combination_widths_inches(comb):
		fw = flt(w)
		if fw > 0 and fw not in out:
			out.append(fw)
	for wo in _get_work_orders_for_spr_job(get_pp_from_spr(spr_doc.name), spr_doc, sj):
		wo_name = _cstr(wo.get("name"))
		if not wo_name:
			continue
		item_code = frappe.db.get_value("Work Order", wo_name, "production_item")
		_gsm, width_inch = parse_item_code(item_code)
		fw = flt(width_inch)
		if fw > 0 and fw not in out:
			out.append(fw)
	jid = _cstr(_spr_job_id(sj))
	for it in spr_doc.items or []:
		if not _spr_item_roll_matches_bundle_job(sj, it, jid):
			continue
		fw = flt(getattr(it, "width_inch", None))
		if fw > 0 and fw not in out:
			out.append(fw)
	if not out:
		tw = flt(getattr(sj, "total_width", None))
		if tw > 0:
			out.append(tw)
	return sorted(set(out))


def _spr_bundle_job_segments_detail(spr_doc, sj) -> list[dict]:
	"""Per combination segment: width, net kg/shaft, linked WO item — for Bundle packaging UI."""
	if not sj:
		return []
	pp_name = get_pp_from_spr(spr_doc.name)
	comb = getattr(sj, "combination", None)
	segs = max(1, _count_combination_segments(comb))
	widths = _parse_combination_widths_inches(comb) if comb else []
	weights = _segment_weights_kg(sj, segs)
	wos = _get_work_orders_for_spr_job(pp_name, spr_doc, sj)
	out: list[dict] = []
	for i in range(segs):
		w_seg = flt(widths[i]) if i < len(widths) else flt(getattr(sj, "total_width", None))
		if w_seg <= 0:
			continue
		nk = weights[i] if i < len(weights) else None
		item_code = ""
		item_name = ""
		for wo in wos:
			won = _cstr(wo.get("name"))
			if not won:
				continue
			ic = frappe.db.get_value("Work Order", won, "production_item")
			if not ic:
				continue
			_g, w_item = parse_item_code(ic)
			if abs(flt(w_item) - w_seg) <= 0.75:
				item_code = _cstr(ic)
				item_name = _cstr(frappe.db.get_value("Item", ic, "item_name") or "")
				break
		out.append(
			{
				"width_inch": round(w_seg, 1),
				"net_kg_per_shaft": round(flt(nk), 3) if nk is not None else None,
				"item_code": item_code,
				"item_name": item_name,
			}
		)
	return out


def _spr_roll_effective_width_inch(it) -> float:
	"""Roll line width: prefer stored width_inch; else derive from item_code (handles total-width on row)."""
	rw = flt(getattr(it, "width_inch", None))
	if rw > 0.001:
		return rw
	ic = getattr(it, "item_code", None)
	if ic:
		_g, w = parse_item_code(ic)
		if flt(w) > 0.001:
			return flt(w)
	return 0.0


def _spr_roll_matches_bundle_width(it, width_inch: float, job_w: float) -> bool:
	"""Match roll to selected segment width; use item_code width when stored width is total or zero."""
	rw = _spr_roll_effective_width_inch(it)
	wx = flt(width_inch)
	jw = flt(job_w)
	tol = 0.75
	if rw > 0.001:
		return abs(rw - wx) <= tol
	if jw > 0.001 and wx > 0.001:
		return abs(jw - wx) <= tol
	return False


def _spr_item_line_from_wo(pp_name, job_id, shaft_combination, planned_qty, wo):
	wo_doc = frappe.get_doc("Work Order", wo["name"])
	item_code = wo_doc.production_item
	item_name = frappe.db.get_value("Item", item_code, "item_name") or ""
	_, width_inch = parse_item_code(item_code)
	specs = _spr_resolve_roll_line_specs_from_item_code(item_code, item_name)
	quality = specs.get("quality") or ""
	color = specs.get("color") or ""
	gsm = cint(specs.get("gsm") or 0)
	if flt(specs.get("width_inch") or 0) > 0:
		width_inch = flt(specs.get("width_inch"))
	spi_meta = frappe.get_meta("Shaft Production Run Item")
	row: dict = {
		"work_order": wo["name"],
		"item_code": item_code,
		"item_name": item_name,
		"quality": quality,
		"gsm": gsm,
		"planned_qty": planned_qty,
		"job": job_id,
		"batch_no": "",
		"party_code": get_order_code(wo_doc),
		"uom": _item_stock_uom_for_spr(item_code),
		"roll_no": 0,
		"meter_roll": 0,
		"net_weight": 0,
		"gross_weight": 0,
		"width_inch": width_inch,
		"color": color,
	}
	if _is_bag_bundle_fg_code(item_code):
		if spi_meta.has_field("custom_bag_size"):
			bag_sz = _cstr(specs.get("bag_size") or "").strip() or _spr_bag_size_from_item_code(item_code)
			if bag_sz:
				row["custom_bag_size"] = bag_sz
	elif _is_sheet_cutting_fg_code(item_code):
		if spi_meta.has_field("custom_sheet_size"):
			sz = _cstr(specs.get("sheet_size") or "").strip() or _spr_sheet_size_from_item_code(item_code)
			if sz:
				row["custom_sheet_size"] = sz
		if spi_meta.has_field("custom_planned_sheets_pcs") and planned_qty > 0:
			row["custom_planned_sheets_pcs"] = planned_qty
	# Fabric GSM (F-60 in item name) and Lamination GSM (L-15 GSM in item name or -C suffix)
	if spi_meta.has_field("custom_fabric_gsm"):
		fab_gsm = _fabric_gsm_from_item_name(item_name) or _fabric_gsm_from_item_name(item_code)
		if fab_gsm > 0:
			row["custom_fabric_gsm"] = fab_gsm
	if spi_meta.has_field("custom_lam_gsm"):
		lam_gsm = _lam_gsm_from_item(item_name, item_code)
		if lam_gsm > 0:
			row["custom_lam_gsm"] = lam_gsm
	if spi_meta.has_field("custom_bopp_gsm"):
		bopp_gsm = _bopp_gsm_from_item(item_code, item_name)
		if bopp_gsm > 0:
			row["custom_bopp_gsm"] = bopp_gsm
	return row


def _build_spr_items_from_pp(spr_doc, pp_name):
	items = []
	for job in _spr_job_rows(spr_doc):
		job_id = _spr_job_id(job)
		if not job_id:
			continue
		shaft_combination = get_shaft_combination(pp_name, job_id)
		if getattr(job, "combination", None) and not shaft_combination:
			shaft_combination = job.combination
		planned_qty = getattr(job, "total_weight", None) or 0
		for wo in _get_work_orders_for_spr_job(pp_name, spr_doc, job):
			items.append(_spr_item_line_from_wo(pp_name, job_id, shaft_combination, planned_qty, wo))
	return items


def _build_roll_items_from_spr(spr_doc, pp_name, job_id_filter=None):
	items = []
	for job in _spr_job_rows(spr_doc):
		job_id = _spr_job_id(job)
		if not job_id:
			continue
		if job_id_filter is not None and _cstr(job_id) != _cstr(job_id_filter):
			continue
		shaft_combination = get_shaft_combination(pp_name, job_id)
		if getattr(job, "combination", None) and not shaft_combination:
			shaft_combination = job.combination
		planned_qty = getattr(job, "total_weight", None) or 0
		for wo in _get_work_orders_for_spr_job(pp_name, spr_doc, job):
			wo_doc = frappe.get_doc("Work Order", wo["name"])
			item_code = wo_doc.production_item
			item_name = frappe.db.get_value("Item", item_code, "item_name")
			gsm, width_inch = parse_item_code(item_code)
			items.append(
				{
					"job_no": job_id,
					"shaft_combination": shaft_combination,
					"planned_qty": planned_qty,
					"wo_id": wo["name"],
					"item_code": item_code,
					"item_name": item_name,
					"gsm": gsm,
					"width_inches": width_inch,
					"order_code": get_order_code(wo_doc),
					"batch_no": "",
					"roll_no": "",
					"meter_per_roll": 0,
					"net_weight": 0,
					"gross_weight": 0,
				}
			)
	return items


@frappe.whitelist()
def get_item_rows_for_production_plan(production_plan):
	"""Build SPR Item rows from WOs for all jobs (API / legacy). Desk flow uses build_spr_roll_result_lines_for_job per job."""
	if not production_plan:
		return []
	jobs = get_job_rows_for_production_plan(production_plan)
	spr = frappe._dict(shaft_jobs=[])
	for j in jobs:
		spr.shaft_jobs.append(frappe._dict(job_id=j["job_id"], total_weight=j.get("total_weight")))
	return _build_spr_items_from_pp(spr, production_plan)


@frappe.whitelist()
def get_or_create_roll_entry(shaft_production_run):
	"""All jobs on SPR (legacy API). Prefer get_or_create_roll_entry_for_job from shaft_jobs row."""
	existing = frappe.db.get_value(
		"Roll Production Entry",
		{"shaft_production_run": shaft_production_run, "docstatus": ["!=", 2]},
		"name",
	)
	if existing:
		return {"existing": existing}
	pp_name = get_pp_from_spr(shaft_production_run)
	if not pp_name:
		frappe.throw(_("Could not find Production Plan linked to {0}").format(shaft_production_run))
	spr_doc = frappe.get_doc("Shaft Production Run", shaft_production_run)
	items = _build_roll_items_from_spr(spr_doc, pp_name)
	return {"production_plan": pp_name, "items": items}


@frappe.whitelist()
def get_or_create_roll_entry_for_job(shaft_production_run, job_id):
	"""Open/create Roll Production Entry for a single PP job (shaft + combination from shaft_jobs row)."""
	if not job_id:
		frappe.throw(_("Job ID is required"))
	if not shaft_production_run or not frappe.db.exists("Shaft Production Run", shaft_production_run):
		frappe.throw(_("Save Shaft Production Run first"))
	meta_rpe = frappe.get_meta("Roll Production Entry")
	filters = {
		"shaft_production_run": shaft_production_run,
		"docstatus": ["!=", 2],
	}
	if meta_rpe.has_field("job_id"):
		filters["job_id"] = _cstr(job_id)
	existing = frappe.db.get_value("Roll Production Entry", filters, "name")
	if existing:
		return {"existing": existing, "job_id": _cstr(job_id)}
	pp_name = get_pp_from_spr(shaft_production_run)
	if not pp_name:
		frappe.throw(_("Could not find Production Plan linked to {0}").format(shaft_production_run))
	spr_doc = frappe.get_doc("Shaft Production Run", shaft_production_run)
	items = _build_roll_items_from_spr(spr_doc, pp_name, job_id_filter=job_id)
	if not items:
		frappe.throw(
			_("No roll lines for job {0}. Check Work Orders for this Production Plan.").format(job_id)
		)
	return {
		"production_plan": pp_name,
		"items": items,
		"job_id": _cstr(job_id),
	}


def get_pp_from_spr(spr_name):
	pp_field = frappe.db.get_value("Shaft Production Run", spr_name, "production_plan")
	if pp_field:
		return pp_field
	if spr_name.startswith("SPR-"):
		return spr_name[4:]
	return None


def get_shaft_combination(pp_name, job_no):
	if frappe.db.exists("DocType", "Production Plan Shaft Detail"):
		v = frappe.db.get_value(
			"Production Plan Shaft Detail",
			{"parent": pp_name, "job_no": job_no},
			"shaft_combination",
		)
		if v:
			return v
	child_dt = _production_plan_custom_shaft_child_doctype()
	if child_dt:
		meta_child = frappe.get_meta(child_dt)
		if meta_child.has_field("s_no"):
			s_no_candidates = [job_no]
			try:
				s_no_candidates.append(cint(job_no))
			except Exception:
				pass
			for candidate in s_no_candidates:
				if candidate is None or candidate == "":
					continue
				v = frappe.db.get_value(child_dt, {"parent": pp_name, "s_no": candidate}, "combination")
				if v:
					return v
		for jf in ("job", "job_no", "job_id"):
			if not meta_child.has_field(jf):
				continue
			v = frappe.db.get_value(child_dt, {"parent": pp_name, jf: job_no}, "shaft_combination")
			if v:
				return v
			if meta_child.has_field("combination"):
				v = frappe.db.get_value(child_dt, {"parent": pp_name, jf: job_no}, "combination")
				if v:
					return v
	return ""


def _production_plan_item_row_names_ordered(pp_name: str) -> list[str]:
	"""Production Plan Item row `name` values in table order (matches WO.production_plan_item)."""
	if not pp_name or not frappe.db.exists("Production Plan", pp_name):
		return []
	if not frappe.db.exists("DocType", "Production Plan Item"):
		return []
	rows = frappe.db.sql(
		"""
		SELECT name FROM `tabProduction Plan Item`
		WHERE parent = %(p)s
		ORDER BY idx ASC, name ASC
		""",
		{"p": pp_name},
	)
	return [_cstr(r[0]) for r in rows if r[0]]


def _resolve_job_ref_to_production_plan_item(pp_name: str, job_ref: str) -> str | None:
	"""
	Map human job id (1, 2, ΓÇª from s_no) to the correct Production Plan Item row name.
	Work Orders link via production_plan_item = PPI row name, not the display job number.
	When the PP has only one line, every shaft job row maps to that line (same WO for multiple SPR jobs).
	"""
	names = _production_plan_item_row_names_ordered(pp_name)
	if not names:
		return None
	t = _cstr(job_ref).strip()
	if not t:
		return None
	if t in names:
		return t
	if len(names) == 1 and t.isdigit():
		return names[0]
	return None


def get_work_orders_for_job(pp_name, job_no):
	if not pp_name or job_no is None:
		return []
	jn = _cstr(job_no).strip()
	if not jn:
		return []
	wos = frappe.db.sql(
		"""
		SELECT wo.name, wo.production_item, wo.qty as planned_qty, wo.produced_qty, wo.status
		FROM `tabWork Order` wo
		WHERE wo.production_plan = %(pp_name)s
		  AND wo.production_plan_item = %(job_no)s
		  AND wo.docstatus != 2
		ORDER BY wo.name
		""",
		{"pp_name": pp_name, "job_no": jn},
		as_dict=True,
	)
	if wos:
		return wos
	pi = _resolve_job_ref_to_production_plan_item(pp_name, jn)
	if pi and pi != jn:
		return get_work_orders_for_job(pp_name, pi)
	return []


def parse_item_code(item_code):
	try:
		if len(item_code) >= 16:
			gsm = int(item_code[9:12])
			width_inch = _spr_nominal_roll_width_inch(item_code)
			if width_inch > 0:
				return gsm, width_inch
	except Exception:
		pass
	return 0, 0


def _spr_nominal_roll_width_inch(item_code, item_name=None) -> float:
	"""Roll width in inches: prefer item-name W - X.X, else 4-digit mm tail rounded to nearest 0.5\"."""
	ic = _cstr(item_code).strip()
	if not ic:
		return 0.0
	inm = _cstr(item_name).strip() if item_name else _cstr(frappe.db.get_value("Item", ic, "item_name") or "")
	try:
		from production_entry.production_planning.scheduler_api import _parse_gsm_width_from_item_text

		_, w_name = _parse_gsm_width_from_item_text(f"{ic} {inm}")
		if w_name > 0:
			rw = round(flt(w_name), 1)
			return float(int(rw)) if abs(rw - round(rw)) < 1e-9 else rw
	except Exception:
		pass
	try:
		if len(ic) >= 16 and ic[12:16].isdigit():
			width_mm = int(ic[12:16])
			if width_mm > 0:
				return round(round(width_mm / 25.4 * 2) / 2, 1)
	except Exception:
		pass
	return 0.0


def _item_stock_uom_for_spr(item_code: str) -> str:
	"""Resolve a valid UOM Link for Shaft Production Run Item (prefer Item.stock_uom, usually Kg)."""
	if not item_code:
		return "Kg"
	u = frappe.db.get_value("Item", item_code, "stock_uom")
	u = (u or "").strip()
	if u and frappe.db.exists("UOM", u):
		return u
	for cand in ("Kg", "kg", "Kgs", "KG"):
		if frappe.db.exists("UOM", cand):
			return cand
	return u or "Kg"


# Manual job + bundle packaging (Actions on Shaft Production Run)
SPR_MANUAL_SOURCE_WH = "Raw Materials - JSB-1ZT"
SPR_MANUAL_FG_WH = "Finished Goods - JSB-1ZT"


def _spr_require_saved(spr_name: str):
	if not spr_name or not frappe.db.exists("Shaft Production Run", spr_name):
		frappe.throw(_("Save the Shaft Production Run first"))


def _spr_pp_and_company(spr_name: str):
	pp_name = get_pp_from_spr(spr_name)
	if not pp_name:
		frappe.throw(_("Set Production Plan on this Shaft Production Run"))
	doc = frappe.get_doc("Shaft Production Run", spr_name)
	company = doc.get("company") or frappe.db.get_value("Production Plan", pp_name, "company")
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
	if not company:
		frappe.throw(_("Company could not be resolved"))
	return pp_name, company, doc


def _spr_warehouses_exist(spr_doc=None):
	unit = ""
	if spr_doc:
		unit = _cstr(getattr(spr_doc, "custom_unit", None) or getattr(spr_doc, "unit", None))
	if unit:
		from production_entry.production_planning.spr_unit_warehouses import (
			resolve_spr_unit_manufacturing_warehouses,
		)

		resolve_spr_unit_manufacturing_warehouses(unit)
		return
	for wh in (SPR_MANUAL_SOURCE_WH, SPR_MANUAL_FG_WH):
		if not frappe.db.exists("Warehouse", wh):
			frappe.throw(_("Warehouse {0} not found. Create it or update SPR_MANUAL_* constants.").format(wh))


def _spr_work_orders_linked_to_spr(spr_doc) -> set[str]:
	linked: set[str] = set()
	if not spr_doc:
		return linked
	for j in _spr_job_rows(spr_doc):
		wos = _cstr(getattr(j, "work_orders", None) or "")
		for part in wos.replace("\n", ",").split(","):
			p = part.strip()
			if p:
				linked.add(p)
	return linked


def _spr_is_manual_shaft_job(sj) -> bool:
	return cint(getattr(sj, "is_manual", 0) or 0) == 1


def _spr_net_kg_per_shaft_for_pp_line_width(
	spr_doc, width_inch: float, production_plan_item: str | None
) -> tuple[float | None, str | None]:
	"""
	Match item width (inch) to a segment in Available Jobs (non-manual): kg per shaft for that segment.
	Uses combination widths + net_weight split, or total_width for single-segment jobs.
	"""
	wx = flt(width_inch)
	if wx <= 0:
		return None, None
	ppi = _cstr(production_plan_item) if production_plan_item else ""
	rows = list(_spr_job_rows(spr_doc))
	preferred = [
		sj
		for sj in rows
		if not _spr_is_manual_shaft_job(sj) and ppi and _cstr(getattr(sj, "production_plan_item", None)) == ppi
	]
	candidates = preferred if preferred else [sj for sj in rows if not _spr_is_manual_shaft_job(sj)]
	for sj in candidates:
		comb = getattr(sj, "combination", None)
		segs = max(1, _count_combination_segments(comb))
		widths = _parse_combination_widths_inches(comb) if comb else []
		weights = _segment_weights_kg(sj, segs)
		jid = _cstr(_spr_job_id(sj))
		if segs > 1 and len(widths) >= segs:
			for i in range(segs):
				if abs(flt(widths[i]) - wx) <= 0.5:
					if i < len(weights) and flt(weights[i]) > 0:
						return flt(weights[i]), jid
			continue
		tw = flt(getattr(sj, "total_width", None))
		if tw > 0 and abs(tw - wx) <= 0.5 and weights:
			return flt(weights[0]), jid
	return None, None


def _spr_try_submit_manual_work_order(wo_name: str):
	"""Submit Work Order when possible so manufacturing can start (best-effort)."""
	try:
		wo = frappe.get_doc("Work Order", wo_name)
		if wo.docstatus == 0:
			wo.submit()
	except Exception:
		frappe.log_error(
			title=f"SPR manual job: could not submit Work Order {wo_name}",
			message=frappe.get_traceback(),
		)


def _spr_manual_wo_has_submitted_stock_entries(wo_name: str) -> bool:
	"""True when this WO already has submitted Stock Entries (manufacture/transfer)."""
	if not wo_name:
		return False
	cnt = frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tabStock Entry` se
		WHERE se.work_order = %(wo)s
		  AND se.docstatus = 1
		  AND IFNULL(se.purpose, '') IN (
			'Manufacture',
			'Material Transfer for Manufacture',
			'Material Consumption for Manufacture'
		  )
		""",
		{"wo": wo_name},
	)
	try:
		return cint((cnt or [[0]])[0][0]) > 0
	except Exception:
		return False


def _spr_find_reusable_manual_work_order(
	pp_name: str,
	item_code: str,
	production_plan_item: str,
	spr_doc=None,
) -> str | None:
	"""
	Find reusable open WO for this PP+item so manual job flow prefers reusing over creating duplicates.
	Priority:
	1) WOs tagged by SPR manual description for the same PP line
	2) Any open WO for same PP+item (fallback)
	"""
	if not pp_name or not item_code:
		return None
	rows = (
		frappe.get_all(
			"Work Order",
			filters={
				"production_plan": pp_name,
				"production_item": item_code,
				"docstatus": ["<", 2],
				"status": ["not in", ["Completed", "Stopped", "Cancelled"]],
			},
			fields=["name", "description", "produced_qty", "creation", "modified"],
			order_by="modified desc",
		)
		or []
	)
	ppi_tag = _cstr(production_plan_item)
	linked = _spr_work_orders_linked_to_spr(spr_doc) if spr_doc else set()
	fallback: list[str] = []
	for r in rows:
		wo_name = _cstr(r.get("name"))
		if not wo_name or wo_name in linked:
			continue
		desc = _cstr(r.get("description"))
		# Prefer explicit SPR-manual WO with matching PP-line tag when available.
		if "SPR manual job" in desc:
			if ppi_tag and ppi_tag in desc:
				return wo_name
			fallback.append(wo_name)
			continue
		# Generic fallback: still allow reusing open WO for same PP+item to avoid duplicate WO creation.
		fallback.append(wo_name)
	if fallback:
		return fallback[0]
	return None


def _spr_list_reusable_manual_work_orders(pp_name: str, item_code: str, production_plan_item: str) -> list[str]:
	"""All reusable open WOs (newest first) for a PP+item, manual-tagged first."""
	if not pp_name or not item_code:
		return []
	rows = (
		frappe.get_all(
			"Work Order",
			filters={
				"production_plan": pp_name,
				"production_item": item_code,
				"docstatus": ["<", 2],
				"status": ["not in", ["Completed", "Stopped", "Cancelled"]],
			},
			fields=["name", "description", "produced_qty", "modified"],
			order_by="modified desc",
		)
		or []
	)
	ppi_tag = _cstr(production_plan_item)
	manual_pref: list[str] = []
	fallback: list[str] = []
	for r in rows:
		wo_name = _cstr(r.get("name"))
		if not wo_name:
			continue
		desc = _cstr(r.get("description"))
		if "SPR manual job" in desc:
			if ppi_tag and ppi_tag in desc:
				manual_pref.append(wo_name)
			else:
				fallback.append(wo_name)
		else:
			fallback.append(wo_name)
	seen = set()
	out: list[str] = []
	for arr in (manual_pref, fallback):
		for wo in arr:
			if wo in seen:
				continue
			seen.add(wo)
			out.append(wo)
	return out


def _spr_resolve_manual_job_work_order(
	pp,
	company: str,
	pp_name: str,
	item_code: str,
	production_plan_item: str,
	ppi_row,
	qty: float,
	selected_reuse_work_order,
	spr_doc,
) -> tuple[str, bool]:
	"""Return (wo_name, reused). __NEW__ forces insert; blank auto-reuses; name reuses if candidate."""
	selected = _cstr(selected_reuse_work_order)
	reused = False
	wo_name = ""
	if selected and selected != "__NEW__":
		candidates = _spr_list_reusable_manual_work_orders(pp_name, item_code, production_plan_item)
		if selected in candidates:
			wo_name = selected
			reused = True
	if not wo_name and selected != "__NEW__":
		wo_name = _spr_find_reusable_manual_work_order(pp_name, item_code, production_plan_item, spr_doc=spr_doc) or ""
		if wo_name:
			reused = True
	if not wo_name:
		wo_name = _spr_insert_manual_work_order(
			pp, company, item_code, production_plan_item, ppi_row, qty, spr_doc=spr_doc
		)
	return wo_name, reused


def _spr_insert_manual_work_order(
	pp,
	company: str,
	item_code: str,
	production_plan_item: str,
	ppi_row,
	qty: float,
	spr_doc=None,
) -> str:
	"""Insert a new Work Order for manual job flow."""
	from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
		get_default_bom_for_item,
	)

	source_wh = SPR_MANUAL_SOURCE_WH
	fg_wh = SPR_MANUAL_FG_WH
	wip_wh = ""
	unit = _cstr(getattr(spr_doc, "custom_unit", None) or getattr(spr_doc, "unit", None)) if spr_doc else ""
	if unit:
		from production_entry.production_planning.spr_unit_warehouses import (
			resolve_spr_unit_manufacturing_warehouses,
		)

		wh_ctx = resolve_spr_unit_manufacturing_warehouses(unit)
		source_wh = _cstr(wh_ctx.get("source_warehouse"))
		fg_wh = _cstr(wh_ctx.get("fg_warehouse"))
		wip_wh = _cstr(wh_ctx.get("wip_warehouse"))
		if wh_ctx.get("company"):
			company = _cstr(wh_ctx["company"])

	bom = get_default_bom_for_item(item_code, company)
	if not bom:
		frappe.throw(_("No active BOM for item {0}").format(item_code))
	pp_name = pp.name
	wo = frappe.new_doc("Work Order")
	wo.production_item = item_code
	wo.bom_no = bom
	wo.qty = flt(qty)
	wo.company = company
	wo.production_plan = pp_name
	# Leave production_plan_item unset on insert so site "one WO per PP line" Server Scripts
	# do not block additional SPR manual Work Orders. Production Plan link stays for traceability.
	wo.production_plan_item = None
	meta_wo = frappe.get_meta("Work Order")
	if meta_wo.has_field("description"):
		wo.description = _("SPR manual job — PP line {0} ┬╖ Item {1}").format(production_plan_item, item_code)
	if pp.get("sales_order"):
		wo.sales_order = pp.sales_order
	if frappe.get_meta("Work Order").has_field("sales_order_item"):
		wo.sales_order_item = getattr(ppi_row, "sales_order_item", None) or None
	wo.source_warehouse = source_wh
	wo.fg_warehouse = fg_wh
	if meta_wo.has_field("wip_warehouse"):
		if wip_wh:
			wo.wip_warehouse = wip_wh
		else:
			wip = frappe.db.get_value("Stock Settings", None, "default_wip_warehouse")
			if wip:
				wo.wip_warehouse = wip
	frappe.flags.spr_manual_work_order_insert = True
	try:
		wo.insert(ignore_permissions=True)
	finally:
		frappe.flags.spr_manual_work_order_insert = False
	wo_name = wo.name
	_spr_set_wo_required_item_source_warehouses(wo_name, source_wh)
	try:
		wo.reload()
		wo.add_comment("Comment", _("SPR manual — Production Plan line {0}").format(production_plan_item))
	except Exception:
		pass
	_spr_try_submit_manual_work_order(wo_name)
	return wo_name


@frappe.whitelist()
def spr_get_manual_job_catalog(shaft_production_run):
	"""Production Plan po_items + width + existing net on SPR by item_code (reuse hint)."""
	_spr_require_saved(shaft_production_run)
	pp_name, company, spr = _spr_pp_and_company(shaft_production_run)
	pp = frappe.get_doc("Production Plan", pp_name)
	pp_order_code = _cstr(
		pp.get("custom_party_code")
		or pp.get("party_code")
		or pp.get("custom_order_code")
		or pp.get("order_code")
	)
	out = []
	net_by_item: dict[str, float] = {}
	for it in spr.items or []:
		ic = _cstr(getattr(it, "item_code", None))
		if not ic:
			continue
		net_by_item[ic] = net_by_item.get(ic, 0.0) + flt(getattr(it, "net_weight", None))
	for row in pp.get("po_items") or []:
		ic = _cstr(getattr(row, "item_code", None))
		if not ic:
			continue
		item_name = frappe.db.get_value("Item", ic, "item_name")
		gsm, width_inch = parse_item_code(ic)
		if flt(width_inch) <= 0:
			width_inch = _spr_nominal_roll_width_inch(ic, item_name)
		first_seg_kg = None
		for sj in _spr_job_rows(spr):
			if _cstr(getattr(sj, "production_plan_item", None)) == _cstr(row.name):
				segs = max(1, _count_combination_segments(getattr(sj, "combination", None)))
				segw = _segment_weights_kg(sj, segs)
				if segw:
					first_seg_kg = round(flt(segw[0]), 3)
				break
		if first_seg_kg is None:
			for sj in _spr_job_rows(spr):
				if _spr_job_product_code(sj) != ic:
					continue
				segs = max(1, _count_combination_segments(getattr(sj, "combination", None)))
				segw = _segment_weights_kg(sj, segs)
				if segw:
					first_seg_kg = round(flt(segw[0]), 3)
				break
		net_ps, mj = _spr_net_kg_per_shaft_for_pp_line_width(spr, width_inch, row.name)
		row_order_code = _cstr(
			getattr(row, "custom_party_code", None)
			or getattr(row, "party_code", None)
			or getattr(row, "custom_order_code", None)
			or getattr(row, "order_code", None)
			or pp_order_code
		)
		out.append(
			{
				"item_code": ic,
				"item_name": item_name or ic,
				"production_plan_item": row.name,
				"planned_qty": flt(getattr(row, "planned_qty", None)),
				"gsm": gsm,
				"width_inch": width_inch,
				"existing_net_weight_kg": round(net_by_item.get(ic, 0.0), 2),
				"first_segment_planned_kg": first_seg_kg,
				"net_per_shaft_kg": round(net_ps, 3) if net_ps is not None else None,
				"matched_job_id": mj,
				"order_code": row_order_code,
				"reusable_work_orders": _spr_list_reusable_manual_work_orders(pp_name, ic, row.name),
			}
		)
	unit = normalize_planning_unit_for_select(_cstr(getattr(spr, "custom_unit", None)))
	return {
		"production_plan": pp_name,
		"company": company,
		"custom_unit": unit,
		"max_shaft_inches": get_mix_roll_unit_max_shaft_inches(unit),
		"lines": out,
	}


def _format_shaft_combination_inches(width_inch) -> str:
	"""Combination column text: width in inches (e.g. 78\"). Not item color — used for manual jobs."""
	w = flt(width_inch)
	if w <= 0:
		return ""
	s = str(int(w)) if w == int(w) else str(w)
	return f'{s}"'


@frappe.whitelist()
def spr_create_manual_job(
	shaft_production_run,
	item_code,
	production_plan_item,
	no_of_shafts,
	wo_qty=None,
	width_inch=None,
):
	"""Create draft Work Order + append manual Shaft Production Run Job row."""
	item_code = _cstr(item_code)
	production_plan_item = _cstr(production_plan_item)
	selected_reuse_work_order = _cstr(frappe.form_dict.get("selected_reuse_work_order"))
	no_of_shafts = cint(no_of_shafts)
	if no_of_shafts < 1:
		frappe.throw(_("Number of shafts must be at least 1"))
	if not item_code or not production_plan_item:
		frappe.throw(_("Item and Production Plan line are required"))

	_spr_require_saved(shaft_production_run)
	pp_name, company, spr = _spr_pp_and_company(shaft_production_run)
	_spr_warehouses_exist(spr)

	pp = frappe.get_doc("Production Plan", pp_name)
	ppi_row = None
	for r in pp.get("po_items") or []:
		if _cstr(r.name) == production_plan_item and _cstr(r.item_code) == item_code:
			ppi_row = r
			break
	if not ppi_row:
		frappe.throw(_("Production Plan item line not found for this item"))

	qty = flt(wo_qty) if wo_qty is not None and str(wo_qty).strip() != "" else None
	if qty is None or qty <= 0:
		qty = flt(getattr(ppi_row, "planned_qty", None) or 0) or 1.0

	wo_name, reused = _spr_resolve_manual_job_work_order(
		pp,
		company,
		pp_name,
		item_code,
		production_plan_item,
		ppi_row,
		qty,
		selected_reuse_work_order,
		spr,
	)

	spr.reload()
	for j in _spr_job_rows(spr):
		wos = _cstr(getattr(j, "work_orders", None) or "")
		for part in wos.replace("\n", ",").split(","):
			if part.strip() == wo_name:
				frappe.throw(
					_("Work Order {0} is already linked to this Shaft Production Run (Job {1}).").format(
						wo_name,
						_spr_job_id(j),
					)
				)

	job_id = f"MAN-{frappe.generate_hash(length=6).upper()}"
	for _attempt in range(20):
		if not any(_cstr(_spr_job_id(j)) == job_id for j in _spr_job_rows(spr)):
			break
		job_id = f"MAN-{frappe.generate_hash(length=6).upper()}"

	gsm, parsed_width = parse_item_code(item_code)
	w_override = flt(width_inch) if width_inch is not None and str(width_inch).strip() != "" else flt(
		frappe.form_dict.get("width_inch")
	)
	if w_override > 0:
		width_inch = w_override
	elif flt(parsed_width) > 0:
		width_inch = flt(parsed_width)
	else:
		item_name_tmp = frappe.db.get_value("Item", item_code, "item_name")
		width_inch = _spr_nominal_roll_width_inch(item_code, item_name_tmp)
	item_name = frappe.db.get_value("Item", item_code, "item_name")
	quality, color = extract_quality_and_color(item_name or "", item_code=item_code)
	order_code = ""
	try:
		wo_doc = frappe.get_doc("Work Order", wo_name)
		order_code = _cstr(get_order_code(wo_doc))
	except Exception:
		order_code = ""

	row = {
		"job_id": job_id,
		"production_plan_item": production_plan_item,
		"is_manual": 1,
		"no_of_shafts": no_of_shafts,
		"work_orders": wo_name,
		"total_weight": qty,
	}
	meta = frappe.get_meta("Shaft Production Run Job")
	if meta.has_field("gsm") and gsm:
		try:
			row["gsm"] = int(gsm)
		except Exception:
			row["gsm"] = gsm
	if meta.has_field("quality") and quality:
		row["quality"] = quality
	if meta.has_field("combination"):
		cb = _format_shaft_combination_inches(width_inch)
		if cb:
			row["combination"] = cb
	if meta.has_field("total_width"):
		row["total_width"] = width_inch
	if meta.has_field("manual_items"):
		row["manual_items"] = item_code
	if meta.has_field("party_code") and order_code:
		row["party_code"] = order_code

	spr.reload()
	spr.append("shaft_jobs", row)
	spr.save(ignore_permissions=True)

	return {
		"work_order": wo_name,
		"job_id": job_id,
		"shaft_production_run": spr.name,
		"reused_work_order": wo_name if reused else "",
	}


@frappe.whitelist()
def spr_create_manual_jobs_multi(
	shaft_production_run, no_of_shafts, items, no_of_rolls=None, combination_input=None
):
	"""
	Create one new Work Order per selected Production Plan line; one manual Available Jobs row.
	items: list of { item_code, production_plan_item, wo_qty, meter_roll }.
	wo_qty is manufacturing Kg = net per roll × rolls_per_shaft × shafts (from the dialog).
	"""
	no_of_shafts = cint(no_of_shafts)
	if no_of_shafts < 1:
		frappe.throw(_("Number of shafts must be at least 1"))
	no_of_rolls = cint(no_of_rolls) if no_of_rolls is not None else 1
	if no_of_rolls < 1:
		no_of_rolls = 1
	if isinstance(items, str):
		items = frappe.parse_json(items)
	if not items or not isinstance(items, list):
		frappe.throw(_("Select at least one Production Plan line"))

	_spr_require_saved(shaft_production_run)
	pp_name, company, spr = _spr_pp_and_company(shaft_production_run)
	_spr_warehouses_exist(spr)
	pp = frappe.get_doc("Production Plan", pp_name)
	combo_raw = _cstr(combination_input).strip()
	if combo_raw:
		unit = normalize_planning_unit_for_select(_cstr(getattr(spr, "custom_unit", None)))
		validate_mix_shaft_width(unit, combo_raw)

	wo_names: list[str] = []
	reused_wo_names: list[str] = []
	qtys: list[float] = []
	widths_list: list[float] = []
	item_codes_list: list[str] = []
	ppi_rows = []
	meter_roll_from_popup: float | None = None

	for raw in items:
		if not isinstance(raw, dict):
			frappe.throw(_("Invalid line payload"))
		item_code = _cstr(raw.get("item_code"))
		production_plan_item = _cstr(raw.get("production_plan_item"))
		selected_reuse_work_order = _cstr(raw.get("selected_reuse_work_order"))
		qty = flt(raw.get("wo_qty"))
		if not item_code or not production_plan_item or qty <= 0:
			frappe.throw(_("Each line needs item, Production Plan row, and Work Order qty greater than zero"))
		ppi_row = None
		for r in pp.get("po_items") or []:
			if _cstr(r.name) == production_plan_item and _cstr(r.item_code) == item_code:
				ppi_row = r
				break
		if not ppi_row:
			frappe.throw(_("Production Plan item line not found for {0}").format(item_code))
		wo_name, reused = _spr_resolve_manual_job_work_order(
			pp,
			company,
			pp_name,
			item_code,
			production_plan_item,
			ppi_row,
			qty,
			selected_reuse_work_order,
			spr,
		)
		if reused:
			reused_wo_names.append(wo_name)
		spr.reload()
		for j in _spr_job_rows(spr):
			wos = _cstr(getattr(j, "work_orders", None) or "")
			for part in wos.replace("\n", ",").split(","):
				if part.strip() == wo_name:
					frappe.throw(
						_("Work Order {0} is already linked to this Shaft Production Run (Job {1}).").format(
							wo_name,
							_spr_job_id(j),
						)
					)
		wo_names.append(wo_name)
		qtys.append(qty)
		item_codes_list.append(item_code)
		ppi_rows.append(ppi_row)
		w_override = flt(raw.get("width_inch"))
		if w_override > 0:
			widths_list.append(w_override)
		else:
			_gsm, w_in = parse_item_code(item_code)
			if flt(w_in) <= 0:
				inm = frappe.db.get_value("Item", item_code, "item_name")
				w_in = _spr_nominal_roll_width_inch(item_code, inm)
			widths_list.append(flt(w_in))
		if meter_roll_from_popup is None and raw.get("meter_roll") not in (None, ""):
			mr = flt(raw.get("meter_roll"))
			if mr > 0:
				meter_roll_from_popup = mr

	job_id = f"MAN-{frappe.generate_hash(length=6).upper()}"
	for _attempt in range(20):
		if not any(_cstr(_spr_job_id(j)) == job_id for j in _spr_job_rows(spr)):
			break
		job_id = f"MAN-{frappe.generate_hash(length=6).upper()}"

	first_ic = item_codes_list[0]
	gsm, width_inch_one = parse_item_code(first_ic)
	item_name = frappe.db.get_value("Item", first_ic, "item_name")
	quality, color = extract_quality_and_color(item_name or "", item_code=first_ic)
	first_order_code = ""
	try:
		if wo_names:
			wo_doc = frappe.get_doc("Work Order", wo_names[0])
			first_order_code = _cstr(get_order_code(wo_doc))
	except Exception:
		first_order_code = ""

	def _fmt_w(w):
		w = flt(w)
		return str(int(w)) if w == int(w) else str(w)

	comb_str = ""
	if len(widths_list) > 1:
		comb_str = " + ".join([f'{_fmt_w(w)}"' for w in widths_list])
	total_w = sum(widths_list) if widths_list else width_inch_one
	total_qty = sum(qtys)

	row = {
		"job_id": job_id,
		"production_plan_item": _cstr(getattr(ppi_rows[0], "name", None)) if ppi_rows else None,
		"is_manual": 1,
		"no_of_shafts": no_of_shafts,
		"work_orders": ",".join(wo_names),
		"total_weight": total_qty,
	}
	meta = frappe.get_meta("Shaft Production Run Job")
	if meta.has_field("no_of_rolls"):
		row["no_of_rolls"] = no_of_rolls
	if meta.has_field("gsm") and gsm:
		try:
			row["gsm"] = int(gsm)
		except Exception:
			row["gsm"] = gsm
	if meta.has_field("quality") and quality:
		row["quality"] = quality
	if meta.has_field("combination"):
		if len(widths_list) > 1 and comb_str:
			row["combination"] = comb_str
		else:
			single_w = flt(widths_list[0]) if widths_list else flt(width_inch_one)
			cb = _format_shaft_combination_inches(single_w)
			if cb:
				row["combination"] = cb
	if meta.has_field("total_width"):
		row["total_width"] = total_w
	if meta.has_field("manual_items"):
		row["manual_items"] = ",".join(item_codes_list)
	if meta.has_field("party_code") and first_order_code:
		row["party_code"] = first_order_code
	if meta.has_field("meter_roll_mtrs") and meter_roll_from_popup is not None and meter_roll_from_popup > 0:
		row["meter_roll_mtrs"] = flt(meter_roll_from_popup)

	spr.reload()
	spr.append("shaft_jobs", row)
	spr.save(ignore_permissions=True)

	return {
		"work_orders": wo_names,
		"reused_work_orders": reused_wo_names,
		"job_id": job_id,
		"shaft_production_run": spr.name,
	}


def _spr_company_from_doc(spr_doc) -> str:
	company = _cstr(getattr(spr_doc, "company", None))
	if company:
		return company
	pp_name = get_pp_from_spr(spr_doc.name)
	if pp_name:
		company = _cstr(frappe.db.get_value("Production Plan", pp_name, "company"))
	if company:
		return company
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		frappe.throw(_("Company could not be resolved"))
	return company


def _spr_transfer_for_manufacture_type_name() -> str:
	if frappe.db.exists("Stock Entry Type", "Material Transfer for Manufacture"):
		p = _cstr(frappe.db.get_value("Stock Entry Type", "Material Transfer for Manufacture", "purpose"))
		if p == "Material Transfer for Manufacture":
			return "Material Transfer for Manufacture"
	name = frappe.db.get_value("Stock Entry Type", {"purpose": "Material Transfer for Manufacture"}, "name")
	return _cstr(name) if name else "Material Transfer for Manufacture"


def _spr_wo_has_submitted_mtfm(wo_name: str) -> bool:
	if not wo_name:
		return False
	return bool(
		frappe.db.exists(
			"Stock Entry",
			{"work_order": wo_name, "purpose": "Material Transfer for Manufacture", "docstatus": 1},
		)
	)


def _spr_validate_rm_stock_for_wo(bom_no: str, qty: float, source_wh: str, company: str) -> list[tuple]:
	"""Return shortages as (item_code, required, available, warehouse)."""
	bom_no = _cstr(bom_no)
	source_wh = _cstr(source_wh)
	rm_map, _multi = _bom_rm_stock_qty_map_for_fg(bom_no, flt(qty))
	shortages: list[tuple] = []
	for item_code, required in sorted((rm_map or {}).items()):
		req = _spr_round_rm_stock_qty(required)
		tol = _spr_rm_wip_shortage_tolerance(req)
		if req <= tol:
			continue
		avl = flt(
			frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": source_wh}, "actual_qty") or 0
		)
		if avl + tol < req:
			shortages.append((item_code, req, avl, source_wh))
	return shortages


def _spr_throw_trial_rm_stock_shortages(shortages: list[tuple]) -> None:
	if not shortages:
		return
	prec = _spr_rm_stock_qty_precision()
	lines = []
	for item_code, req, avl, wh in shortages:
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Kg"
		lines.append(
			_(
				"No stock for {0} in {1} (required {2} {3}, available {4} {3}). "
				"Transfer not done — Work Order not created."
			).format(item_code, wh, flt(req, prec), stock_uom, flt(avl, prec))
		)
	frappe.throw("\n".join(lines), title=_("Raw material stock shortage"))


def _spr_assign_batch_for_mtfm_line(sed, source_wh: str, need_qty: float = 0) -> None:
	"""Pick a batch that actually has stock in source warehouse (never a master-only fallback)."""
	if sed.get("batch_no"):
		return
	has_batch = cint(frappe.db.get_value("Item", sed.item_code, "has_batch_no") or 0)
	if not has_batch:
		return
	need = flt(need_qty or sed.get("transfer_qty") or sed.get("qty"))
	batches = _spr_batches_in_warehouse(sed.item_code, source_wh)
	if not batches:
		return
	for br in batches:
		if flt(br.get("qty") or 0) + 1e-9 >= need:
			sed.batch_no = _cstr(br.get("batch_no"))
			return
	sed.batch_no = _cstr(batches[0].get("batch_no"))


def _spr_create_and_submit_mtfm(wo_doc) -> str:
	"""Create and submit Material Transfer for Manufacture for a Work Order."""
	wo_name = _cstr(getattr(wo_doc, "name", None))
	if not wo_name:
		frappe.throw(_("Work Order is required for material transfer"))
	if _spr_wo_has_submitted_mtfm(wo_name):
		return _cstr(
			frappe.db.get_value(
				"Stock Entry",
				{"work_order": wo_name, "purpose": "Material Transfer for Manufacture", "docstatus": 1},
				"name",
			)
			or ""
		)

	wo_doc = frappe.get_doc("Work Order", wo_name)
	source_wh = _cstr(getattr(wo_doc, "source_warehouse", None))
	wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None))
	if not source_wh or not wip_wh:
		frappe.throw(_("Work Order {0} is missing source or WIP warehouse.").format(wo_name))

	se = frappe.new_doc("Stock Entry")
	se.purpose = "Material Transfer for Manufacture"
	se.stock_entry_type = _spr_transfer_for_manufacture_type_name()
	se.work_order = wo_name
	se.company = wo_doc.company
	se.from_warehouse = source_wh
	se.to_warehouse = wip_wh
	se.wip_warehouse = wip_wh
	se.fg_completed_qty = flt(getattr(wo_doc, "qty", 0)) or 1.0
	se.posting_date = today()
	se.posting_time = nowtime()
	se.set_posting_time = 1
	se_meta = frappe.get_meta("Stock Entry")
	if se_meta.has_field("use_serial_batch_fields"):
		se.use_serial_batch_fields = 1

	try:
		se.from_bom = 1
		se.bom_no = wo_doc.bom_no
		se.use_multi_level_bom = wo_doc.use_multi_level_bom
		se.get_items()
	except Exception:
		se.from_bom = 0
		se.items = []

	for sed in se.items or []:
		if not sed.work_order:
			sed.work_order = wo_name
		if not sed.s_warehouse:
			sed.s_warehouse = source_wh
		if not sed.t_warehouse:
			sed.t_warehouse = wip_wh
		if se_meta.has_field("use_serial_batch_fields"):
			sed.use_serial_batch_fields = 1
		_spr_finalize_mtfm_line_qty(sed, sed.s_warehouse or source_wh, flt(sed.qty))

	if not se.items:
		for row in wo_doc.get("required_items") or []:
			item_src = _cstr(getattr(row, "source_warehouse", None)) or source_wh
			se.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.required_qty,
					"transfer_qty": row.required_qty,
					"uom": row.stock_uom,
					"stock_uom": row.stock_uom,
					"s_warehouse": item_src,
					"t_warehouse": wip_wh,
					"conversion_factor": 1,
					"work_order": wo_name,
				},
			)
		for sed in se.items or []:
			_spr_finalize_mtfm_line_qty(sed, sed.s_warehouse or source_wh, flt(sed.qty))

	if not se.items:
		frappe.throw(_("No raw material lines to transfer for Work Order {0}.").format(wo_name))

	se.flags.ignore_permissions = True
	se.insert(ignore_permissions=True)
	se.submit()

	frappe.db.set_value(
		"Work Order",
		wo_name,
		{
			"material_transferred_for_manufacturing": wo_doc.qty,
			"status": "In Process",
		},
		update_modified=True,
	)
	try:
		frappe.db.set_value(
			"Work Order",
			wo_name,
			"actual_start_date",
			frappe.utils.now_datetime(),
			update_modified=True,
		)
	except Exception:
		pass
	return se.name


def _spr_set_wo_required_item_source_warehouses(wo_name: str, source_wh: str) -> None:
	source_wh = _cstr(source_wh)
	if not wo_name or not source_wh:
		return
	for req in frappe.get_all(
		"Work Order Item",
		filters={"parent": wo_name, "parenttype": "Work Order"},
		pluck="name",
	) or []:
		frappe.db.set_value("Work Order Item", req, "source_warehouse", source_wh, update_modified=False)


def _spr_submit_trial_work_order(wo_name: str) -> None:
	wo = frappe.get_doc("Work Order", wo_name)
	if wo.docstatus == 0:
		wo.flags.ignore_permissions = True
		wo.submit()


def _spr_finalize_trial_work_order(
	wo_name: str,
	wh_ctx: dict,
	bom_no: str,
	qty: float,
) -> str:
	"""Ensure trial WO has warehouses, RM transfer, and is submitted."""
	if not wo_name or not frappe.db.exists("Work Order", wo_name):
		frappe.throw(_("Work Order {0} not found").format(wo_name or "—"))

	if _spr_wo_has_submitted_mtfm(wo_name):
		wo = frappe.get_doc("Work Order", wo_name)
		if wo.docstatus == 0:
			_spr_submit_trial_work_order(wo_name)
		return wo_name

	shortages = _spr_validate_rm_stock_for_wo(
		bom_no,
		qty,
		_cstr(wh_ctx.get("source_warehouse")),
		_cstr(wh_ctx.get("company")),
	)
	_spr_throw_trial_rm_stock_shortages(shortages)

	wo = frappe.get_doc("Work Order", wo_name)
	company = _cstr(wh_ctx.get("company"))
	source_wh = _cstr(wh_ctx.get("source_warehouse"))
	wip_wh = _cstr(wh_ctx.get("wip_warehouse"))
	fg_wh = _cstr(wh_ctx.get("fg_warehouse"))

	if wo.docstatus == 0:
		updates = {}
		if company and wo.company != company:
			updates["company"] = company
		if source_wh and wo.source_warehouse != source_wh:
			updates["source_warehouse"] = source_wh
		if wip_wh and getattr(wo, "wip_warehouse", None) != wip_wh:
			updates["wip_warehouse"] = wip_wh
		if fg_wh and wo.fg_warehouse != fg_wh:
			updates["fg_warehouse"] = fg_wh
		if updates:
			frappe.db.set_value("Work Order", wo_name, updates, update_modified=True)
		_spr_set_wo_required_item_source_warehouses(wo_name, source_wh)

	wo.reload()
	if wo.docstatus == 0:
		_spr_submit_trial_work_order(wo_name)
	wo.reload()
	try:
		_spr_create_and_submit_mtfm(wo)
	except Exception:
		wo.reload()
		if wo.docstatus == 1 and not _spr_wo_has_submitted_mtfm(wo_name):
			try:
				wo.cancel()
			except Exception:
				pass
		raise
	return wo_name


def _spr_insert_trial_work_order(unit: str, item_code: str, qty: float, order_code: str) -> str:
	from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
		get_default_bom_for_item,
	)
	from production_entry.production_planning.spr_unit_warehouses import (
		resolve_spr_unit_manufacturing_warehouses,
	)

	wh_ctx = resolve_spr_unit_manufacturing_warehouses(unit)
	company = _cstr(wh_ctx.get("company"))
	source_wh = _cstr(wh_ctx.get("source_warehouse"))
	wip_wh = _cstr(wh_ctx.get("wip_warehouse"))
	fg_wh = _cstr(wh_ctx.get("fg_warehouse"))

	bom = get_default_bom_for_item(item_code, company)
	if not bom:
		frappe.throw(_("No active BOM for item {0}").format(item_code))

	shortages = _spr_validate_rm_stock_for_wo(bom, qty, source_wh, company)
	_spr_throw_trial_rm_stock_shortages(shortages)

	wo = frappe.new_doc("Work Order")
	wo.production_item = item_code
	wo.bom_no = bom
	wo.qty = flt(qty)
	wo.company = company
	meta_wo = frappe.get_meta("Work Order")
	if meta_wo.has_field("description"):
		wo.description = _("SPR trial order — Item {0} — Order {1}").format(item_code, order_code)
	for fn in ("custom_order_code", "order_code", "custom_party_code"):
		if meta_wo.has_field(fn) and order_code:
			wo.set(fn, order_code)
	wo.source_warehouse = source_wh
	wo.fg_warehouse = fg_wh
	if meta_wo.has_field("wip_warehouse"):
		wo.wip_warehouse = wip_wh
	frappe.flags.spr_manual_work_order_insert = True
	try:
		wo.insert(ignore_permissions=True)
	finally:
		frappe.flags.spr_manual_work_order_insert = False
	wo_name = wo.name
	_spr_set_wo_required_item_source_warehouses(wo_name, source_wh)
	_spr_finalize_trial_work_order(wo_name, wh_ctx, bom, qty)
	return wo_name


def _spr_list_reusable_trial_work_orders(item_code: str, order_code: str = "") -> list[str]:
	if not item_code:
		return []
	rows = (
		frappe.get_all(
			"Work Order",
			filters={
				"production_item": item_code,
				"docstatus": ["<", 2],
				"status": ["not in", ["Completed", "Stopped", "Cancelled"]],
			},
			fields=["name", "description", "modified", "production_plan"],
			order_by="modified desc",
		)
		or []
	)
	rows = [r for r in rows if not _cstr(r.get("production_plan"))]
	oc = _cstr(order_code)
	out: list[str] = []
	seen = set()
	for r in rows:
		wo_name = _cstr(r.get("name"))
		if not wo_name or wo_name in seen:
			continue
		desc = _cstr(r.get("description"))
		if "SPR trial" not in desc and oc:
			continue
		if oc:
			try:
				wo_doc = frappe.get_doc("Work Order", wo_name)
				if get_order_code(wo_doc) != oc:
					continue
			except Exception:
				pass
		seen.add(wo_name)
		out.append(wo_name)
	if not out:
		for r in rows:
			wo_name = _cstr(r.get("name"))
			if wo_name and wo_name not in seen:
				seen.add(wo_name)
				out.append(wo_name)
	return out


@frappe.whitelist()
def spr_get_trial_order_context(shaft_production_run):
	_spr_require_saved(shaft_production_run)
	spr = frappe.get_doc("Shaft Production Run", shaft_production_run)
	unit = normalize_planning_unit_for_select(_cstr(getattr(spr, "custom_unit", None)))
	from production_entry.production_planning.spr_unit_warehouses import (
		resolve_spr_unit_manufacturing_warehouses,
	)

	wh_ctx = resolve_spr_unit_manufacturing_warehouses(unit)
	company = _cstr(wh_ctx.get("company")) or _spr_company_from_doc(spr)
	qualities = frappe.get_all("Quality Master", fields=["name", "quality_name"], order_by="quality_name asc") or []
	colors = frappe.get_all("Colour Master", fields=["name", "colour_name"], order_by="colour_name asc") or []
	return {
		"company": company,
		"custom_unit": unit,
		"max_shaft_inches": get_mix_roll_unit_max_shaft_inches(unit),
		"source_warehouse": _cstr(wh_ctx.get("source_warehouse")),
		"wip_warehouse": _cstr(wh_ctx.get("wip_warehouse")),
		"fg_warehouse": _cstr(wh_ctx.get("fg_warehouse")),
		"plant_floor": _cstr(wh_ctx.get("plant_floor")),
		"workstation": _cstr(wh_ctx.get("workstation")),
		"qualities": qualities,
		"colors": colors,
	}


@frappe.whitelist()
def spr_resolve_trial_fabric_item(
	quality,
	color,
	gsm,
	width_inch,
	company=None,
	create_if_missing=1,
):
	from production_entry.production_planning.fabric_item_bom import (
		ensure_fabric_item,
		ensure_nonwoven_fabric_bom,
		resolve_fabric_item_code,
	)

	company = _cstr(company) or frappe.defaults.get_global_default("company")
	resolved = resolve_fabric_item_code(quality, color, gsm, width_inch)
	item_code = _cstr(resolved.get("item_code"))
	created = 0
	if not frappe.db.exists("Item", item_code) and cint(create_if_missing):
		out = ensure_fabric_item(company, quality, color, gsm, width_inch)
		item_code = _cstr(out.get("item_code"))
		created = cint(out.get("created"))
	bom_name = None
	if frappe.db.exists("Item", item_code):
		bom_name = ensure_nonwoven_fabric_bom(item_code, company, quality, color, gsm=gsm)
	return {
		"item_code": item_code,
		"item_name": frappe.db.get_value("Item", item_code, "item_name") if item_code else "",
		"width_inch": resolved.get("width_inch"),
		"width_mm": resolved.get("width_mm"),
		"gsm": int(flt(gsm)),
		"created": created,
		"bom": bom_name,
		"exists": bool(frappe.db.exists("Item", item_code)),
	}


@frappe.whitelist()
def spr_preview_trial_fabric_bom(item_code, company=None, quality=None, color=None, gsm=None):
	from production_entry.production_planning.fabric_item_bom import preview_fabric_bom

	return preview_fabric_bom(item_code, company=company, quality=quality, color=color, gsm=gsm)


@frappe.whitelist()
def spr_create_trial_fabric_bom(
	item_code,
	company=None,
	quality=None,
	color=None,
	gsm=None,
	recipe_payload=None,
	force_new=0,
):
	from production_entry.production_planning.fabric_item_bom import create_fabric_bom_from_recipe

	return create_fabric_bom_from_recipe(
		item_code,
		company=company,
		quality=quality,
		color=color,
		gsm=gsm,
		recipe_payload=recipe_payload,
		force_new=force_new,
	)


@frappe.whitelist()
def spr_create_trial_jobs_multi(
	shaft_production_run,
	order_code,
	no_of_shafts,
	items,
	no_of_rolls=None,
	combination_input=None,
):
	"""Create standalone trial Work Orders and append Available Jobs row (mirror manual job)."""
	order_code = _cstr(order_code)
	if not order_code:
		frappe.throw(_("Order code is required for Trail Order"))
	no_of_shafts = cint(no_of_shafts)
	if no_of_shafts < 1:
		frappe.throw(_("Number of shafts must be at least 1"))
	no_of_rolls = cint(no_of_rolls) if no_of_rolls is not None else 1
	if no_of_rolls < 1:
		no_of_rolls = 1
	if isinstance(items, str):
		items = frappe.parse_json(items)
	if not items or not isinstance(items, list):
		frappe.throw(_("Add at least one trial fabric line"))

	_spr_require_saved(shaft_production_run)
	spr = frappe.get_doc("Shaft Production Run", shaft_production_run)
	unit = normalize_planning_unit_for_select(_cstr(getattr(spr, "custom_unit", None)))
	from production_entry.production_planning.spr_unit_warehouses import (
		resolve_spr_unit_manufacturing_warehouses,
	)
	from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
		get_default_bom_for_item,
	)

	resolve_spr_unit_manufacturing_warehouses(unit)
	company = _spr_company_from_doc(spr)
	combo_raw = _cstr(combination_input).strip()
	if combo_raw:
		validate_mix_shaft_width(unit, combo_raw)

	wo_names: list[str] = []
	reused_wo_names: list[str] = []
	qtys: list[float] = []
	widths_list: list[float] = []
	item_codes_list: list[str] = []
	meter_roll_from_popup: float | None = None

	for raw in items:
		if not isinstance(raw, dict):
			frappe.throw(_("Invalid line payload"))
		item_code = _cstr(raw.get("item_code"))
		qty = flt(raw.get("wo_qty"))
		if not item_code or qty <= 0:
			frappe.throw(_("Each line needs item and Work Order qty greater than zero"))
		selected_reuse = _cstr(raw.get("selected_reuse_work_order"))
		wo_name = ""
		if selected_reuse and selected_reuse != "__NEW__":
			candidates = _spr_list_reusable_trial_work_orders(item_code, order_code)
			if selected_reuse in candidates:
				wo_name = selected_reuse
		if not wo_name:
			candidates = _spr_list_reusable_trial_work_orders(item_code, order_code)
			if candidates and selected_reuse != "__NEW__":
				wo_name = candidates[0]
		if not wo_name:
			wo_name = _spr_insert_trial_work_order(unit, item_code, qty, order_code)
		else:
			reused_wo_names.append(wo_name)
			wh_ctx = resolve_spr_unit_manufacturing_warehouses(unit)
			bom = get_default_bom_for_item(item_code, wh_ctx["company"])
			if not bom:
				frappe.throw(_("No active BOM for item {0}").format(item_code))
			_spr_finalize_trial_work_order(wo_name, wh_ctx, bom, qty)
		spr.reload()
		for j in _spr_job_rows(spr):
			wos = _cstr(getattr(j, "work_orders", None) or "")
			for part in wos.replace("\n", ",").split(","):
				if part.strip() == wo_name:
					frappe.throw(
						_("Work Order {0} is already linked to this Shaft Production Run (Job {1}).").format(
							wo_name,
							_spr_job_id(j),
						)
					)
		wo_names.append(wo_name)
		qtys.append(qty)
		item_codes_list.append(item_code)
		_gsm, w_in = parse_item_code(item_code)
		widths_list.append(flt(w_in))
		if meter_roll_from_popup is None and raw.get("meter_roll") not in (None, ""):
			mr = flt(raw.get("meter_roll"))
			if mr > 0:
				meter_roll_from_popup = mr

	job_id = f"TRIAL-{frappe.generate_hash(length=6).upper()}"
	for _attempt in range(20):
		if not any(_cstr(_spr_job_id(j)) == job_id for j in _spr_job_rows(spr)):
			break
		job_id = f"TRIAL-{frappe.generate_hash(length=6).upper()}"

	first_ic = item_codes_list[0]
	gsm, width_inch_one = parse_item_code(first_ic)
	item_name = frappe.db.get_value("Item", first_ic, "item_name")
	quality, color = extract_quality_and_color(item_name or "", item_code=first_ic)

	def _fmt_w(w):
		w = flt(w)
		return str(int(w)) if w == int(w) else str(w)

	comb_str = ""
	if len(widths_list) > 1:
		comb_str = " + ".join([f'{_fmt_w(w)}"' for w in widths_list])
	elif combo_raw:
		comb_str = combo_raw.replace("+", " + ")
	total_w = sum(widths_list) if widths_list else width_inch_one
	total_qty = sum(qtys)

	row = {
		"job_id": job_id,
		"is_manual": 1,
		"no_of_shafts": no_of_shafts,
		"work_orders": ",".join(wo_names),
		"total_weight": total_qty,
	}
	meta = frappe.get_meta("Shaft Production Run Job")
	if meta.has_field("no_of_rolls"):
		row["no_of_rolls"] = no_of_rolls
	if meta.has_field("gsm") and gsm:
		try:
			row["gsm"] = int(gsm)
		except Exception:
			row["gsm"] = gsm
	if meta.has_field("quality") and quality:
		row["quality"] = quality
	if meta.has_field("color") and color:
		row["color"] = color
	if meta.has_field("combination"):
		if len(widths_list) > 1 and comb_str:
			row["combination"] = comb_str
		else:
			cb = _format_shaft_combination_inches(width_inch_one)
			if cb:
				row["combination"] = cb
	if meta.has_field("total_width"):
		row["total_width"] = total_w
	if meta.has_field("manual_items"):
		row["manual_items"] = ",".join(item_codes_list)
	if meta.has_field("party_code"):
		row["party_code"] = order_code
	if meta.has_field("meter_roll_mtrs") and meter_roll_from_popup is not None and meter_roll_from_popup > 0:
		row["meter_roll_mtrs"] = flt(meter_roll_from_popup)

	spr.reload()
	spr.append("shaft_jobs", row)
	spr.save(ignore_permissions=True)

	return {
		"work_orders": wo_names,
		"reused_work_orders": reused_wo_names,
		"job_id": job_id,
		"shaft_production_run": spr.name,
	}


@frappe.whitelist()
def spr_cancel_duplicate_mtfm_entries(stock_entries, work_order=None):
	"""Cancel duplicate Material Transfer for Manufacture entries and resync WO required items."""
	frappe.only_for(("System Manager", "Manufacturing Manager", "Administrator"))

	if isinstance(stock_entries, str):
		try:
			stock_entries = json.loads(stock_entries)
		except Exception:
			stock_entries = [x.strip() for x in stock_entries.split(",") if x.strip()]
	names = [_cstr(x).strip() for x in (stock_entries or []) if _cstr(x).strip()]
	if not names:
		frappe.throw(_("Select at least one Stock Entry to cancel"))

	wo = _cstr(work_order).strip()
	if not wo:
		wo = _cstr(frappe.db.get_value("Stock Entry", names[0], "work_order"))
	if not wo:
		frappe.throw(_("Work Order is required"))

	entries = []
	for name in names:
		if not frappe.db.exists("Stock Entry", name):
			frappe.throw(_("Stock Entry {0} not found").format(name))
		se = frappe.get_doc("Stock Entry", name)
		if cint(se.docstatus) != 1:
			continue
		if _cstr(se.purpose) != "Material Transfer for Manufacture":
			frappe.throw(_("Stock Entry {0} is not Material Transfer for Manufacture").format(name))
		if _cstr(se.work_order) and _cstr(se.work_order) != wo:
			frappe.throw(_("Stock Entry {0} belongs to a different Work Order").format(name))
		entries.append(se)

	if not entries:
		frappe.throw(_("No submitted Material Transfer entries to cancel"))

	entries.sort(
		key=lambda s: (
			getdate(s.posting_date),
			_cstr(s.posting_time),
			s.creation,
		),
		reverse=True,
	)

	cancelled = []
	frappe.flags.spr_skip_wo_transfer_qty_validation = True
	try:
		for se in entries:
			se.flags.ignore_validate = True
			se.cancel()
			cancelled.append(se.name)
	finally:
		frappe.flags.spr_skip_wo_transfer_qty_validation = False

	dummy = frappe.new_doc("Shaft Production Run")
	dummy._sync_work_order_required_item_progress(wo)
	try:
		frappe.db.commit()
	except Exception:
		pass

	return {
		"status": "ok",
		"work_order": wo,
		"cancelled": cancelled,
		"message": _("Cancelled {0} transfer(s). Reopen Work Order {1} and submit SPR again.").format(
			len(cancelled), wo
		),
	}


@frappe.whitelist()
def spr_resync_work_order_consumption(work_order: str):
	"""Manual utility: recompute consumed/transferred qty on WO required items from submitted Stock Entries."""
	wo = _cstr(work_order)
	if not wo:
		frappe.throw(_("Work Order is required"))
	if not frappe.db.exists("Work Order", wo):
		frappe.throw(_("Work Order {0} not found").format(wo))
	dummy = frappe.new_doc("Shaft Production Run")
	dummy._sync_work_order_required_item_progress(wo)
	return {"status": "ok", "work_order": wo}


@frappe.whitelist()
def spr_resync_work_order_progress(work_order: str):
	"""Manual utility: recompute WO produced + required-item progress from submitted Stock Entries."""
	wo = _cstr(work_order)
	if not wo:
		frappe.throw(_("Work Order is required"))
	if not frappe.db.exists("Work Order", wo):
		frappe.throw(_("Work Order {0} not found").format(wo))

	dummy = frappe.new_doc("Shaft Production Run")
	dummy._sync_work_order_produced_qty_from_submitted_manufacture(wo)
	dummy._sync_work_order_required_item_progress(wo)

	wo_doc = frappe.get_doc("Work Order", wo)
	produced = flt(getattr(wo_doc, "produced_qty", 0))
	target = flt(getattr(wo_doc, "qty", 0))
	if target > 0 and produced + 1e-9 >= target and _cstr(getattr(wo_doc, "status", "")) not in ("Completed", "Stopped", "Cancelled"):
		wo_doc.db_set("status", "Completed")
	return {"status": "ok", "work_order": wo, "produced_qty": produced}


@frappe.whitelist()
def spr_resync_production_plan_progress(production_plan: str):
	"""Manual utility: recompute all Work Orders progress under a Production Plan for existing data."""
	pp = _cstr(production_plan)
	if not pp:
		frappe.throw(_("Production Plan is required"))
	if not frappe.db.exists("Production Plan", pp):
		frappe.throw(_("Production Plan {0} not found").format(pp))

	wo_names = frappe.get_all(
		"Work Order",
		filters={"production_plan": pp, "docstatus": ["<", 2]},
		pluck="name",
	) or []
	dummy = frappe.new_doc("Shaft Production Run")
	out = []
	for wo in wo_names:
		dummy._sync_work_order_produced_qty_from_submitted_manufacture(wo)
		dummy._sync_work_order_required_item_progress(wo)
		wo_doc = frappe.get_doc("Work Order", wo)
		produced = flt(getattr(wo_doc, "produced_qty", 0))
		target = flt(getattr(wo_doc, "qty", 0))
		if target > 0 and produced + 1e-9 >= target and _cstr(getattr(wo_doc, "status", "")) not in ("Completed", "Stopped", "Cancelled"):
			wo_doc.db_set("status", "Completed")
		out.append({"work_order": wo, "produced_qty": produced, "qty": target, "status": _cstr(getattr(wo_doc, "status", ""))})
	dummy._sync_production_plan_progress_from_work_orders(pp)
	return {"status": "ok", "production_plan": pp, "work_orders": out}


@frappe.whitelist()
def spr_force_relink_and_resync(production_plan: str, shaft_production_run: str | None = None):
	"""
	Recovery utility for old partial data:
	1) Relink submitted Manufacture Stock Entries with blank work_order (DB-level update).
	2) Resync WO produced/consumption progress.
	3) Resync Production Plan produced progress.
	"""
	pp = _cstr(production_plan)
	if not pp:
		frappe.throw(_("Production Plan is required"))
	if not frappe.db.exists("Production Plan", pp):
		frappe.throw(_("Production Plan {0} not found").format(pp))

	spr_name = _cstr(shaft_production_run)
	spr_doc = None
	if spr_name:
		if not frappe.db.exists("Shaft Production Run", spr_name):
			frappe.throw(_("Shaft Production Run {0} not found").format(spr_name))
		spr_doc = frappe.get_doc("Shaft Production Run", spr_name)

	wo_rows = frappe.get_all(
		"Work Order",
		filters={"production_plan": pp, "docstatus": ["<", 2]},
		fields=["name", "production_item"],
	) or []
	wo_by_item = defaultdict(list)
	for w in wo_rows:
		ic = _cstr(w.get("production_item"))
		if ic:
			wo_by_item[ic].append(_cstr(w.get("name")))

	se_names = []
	if spr_doc and _cstr(getattr(spr_doc, "manufacturing_entries", "")):
		se_names = [x.strip() for x in _cstr(getattr(spr_doc, "manufacturing_entries", "")).split(",") if x and x.strip()]
	if not se_names and spr_doc:
		spr_company = _cstr(getattr(spr_doc, "company", None) or spr_doc.get("company"))
		spr_posting_date = getattr(spr_doc, "run_date", None) or spr_doc.get("run_date")
		filters = {
			"purpose": "Manufacture",
			"docstatus": 1,
		}
		if spr_company:
			filters["company"] = spr_company
		if spr_posting_date:
			filters["posting_date"] = spr_posting_date
		se_names = frappe.get_all("Stock Entry", filters=filters, pluck="name") or []
	else:
		# Fallback without SPR: all submitted Manufacture entries whose WO belongs to this PP plus blanks.
		se_names = frappe.get_all(
			"Stock Entry",
			filters={"purpose": "Manufacture", "docstatus": 1},
			pluck="name",
		) or []

	linked = []
	skipped = []
	for se_name in se_names:
		se = frappe.get_doc("Stock Entry", se_name)
		if _cstr(getattr(se, "purpose", "")) != "Manufacture" or cint(getattr(se, "docstatus", 0)) != 1:
			continue
		if _cstr(getattr(se, "work_order", "")):
			continue
		fg_items = sorted(
			{
				_cstr(getattr(d, "item_code", ""))
				for d in (se.items or [])
				if cint(getattr(d, "is_finished_item", 0)) == 1 and _cstr(getattr(d, "item_code", ""))
			}
		)
		if len(fg_items) != 1:
			skipped.append({"stock_entry": se_name, "reason": "ambiguous_fg_items", "fg_items": fg_items})
			continue
		candidates = wo_by_item.get(fg_items[0], [])
		if len(candidates) != 1:
			skipped.append({"stock_entry": se_name, "reason": "ambiguous_wo_candidates", "item_code": fg_items[0], "candidates": candidates})
			continue
		wo_id = candidates[0]
		frappe.db.set_value("Stock Entry", se_name, "work_order", wo_id, update_modified=False)
		linked.append({"stock_entry": se_name, "work_order": wo_id, "item_code": fg_items[0]})

	dummy = frappe.new_doc("Shaft Production Run")
	out = []
	for wo in [w.get("name") for w in wo_rows]:
		dummy._sync_work_order_produced_qty_from_submitted_manufacture(wo)
		dummy._sync_work_order_required_item_progress(wo)
		wo_doc = frappe.get_doc("Work Order", wo)
		produced = flt(getattr(wo_doc, "produced_qty", 0))
		target = flt(getattr(wo_doc, "qty", 0))
		out.append({"work_order": wo, "produced_qty": produced, "qty": target, "status": _cstr(getattr(wo_doc, "status", ""))})
	dummy._sync_production_plan_progress_from_work_orders(pp)

	return {
		"status": "ok",
		"production_plan": pp,
		"shaft_production_run": spr_name or None,
		"linked_count": len(linked),
		"linked": linked,
		"skipped_count": len(skipped),
		"skipped": skipped[:50],
		"work_orders": out,
	}


@frappe.whitelist()
def spr_backfill_missing_manufacture_from_spr(shaft_production_run: str, submit_entries: int = 0):
	"""
	Create missing Manufacture entries from SPR roll rows (batch-wise), not whole WO qty.
	Useful for legacy partial cases where some WO/rolls were skipped earlier.
	"""
	spr_name = _cstr(shaft_production_run)
	if not spr_name:
		frappe.throw(_("Shaft Production Run is required"))
	if not frappe.db.exists("Shaft Production Run", spr_name):
		frappe.throw(_("Shaft Production Run {0} not found").format(spr_name))
	spr = frappe.get_doc("Shaft Production Run", spr_name)
	if not spr.get("production_plan"):
		frappe.throw(_("SPR {0} has no Production Plan").format(spr_name))

	# Group positive roll rows by WO
	wo_rows = defaultdict(list)
	for r in spr.items or []:
		q = flt(spr._row_fg_qty(r))
		wo = _cstr(r.get("work_order") or r.get("wo_id"))
		if q > 0 and wo:
			wo_rows[wo].append(r)
	if not wo_rows:
		return {"status": "ok", "created": [], "skipped": [{"reason": "no_wo_roll_rows"}]}

	created = []
	skipped = []
	do_submit = cint(submit_entries) == 1

	for wo_id, rows in wo_rows.items():
		if not frappe.db.exists("Work Order", wo_id):
			skipped.append({"work_order": wo_id, "reason": "wo_not_found"})
			continue
		wo_doc = frappe.get_doc("Work Order", wo_id)
		item_code = _cstr(getattr(wo_doc, "production_item", None))
		if not item_code:
			skipped.append({"work_order": wo_id, "reason": "wo_missing_production_item"})
			continue

		# Existing posted qty per batch in this SPR+WO (submitted and draft to avoid duplicates).
		existing_batch_qty = defaultdict(float)
		existing_total = 0.0
		se_has_spr_ref = frappe.db.has_column("Stock Entry", "custom_spr_reference")
		if se_has_spr_ref:
			existing = frappe.db.sql(
				"""
				SELECT IFNULL(sed.batch_no, '') AS batch_no, IFNULL(SUM(IFNULL(sed.qty, 0)), 0) AS qty
				FROM `tabStock Entry` se
				INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
				WHERE IFNULL(se.custom_spr_reference, '') = %(spr)s
				  AND IFNULL(se.purpose, '') = 'Manufacture'
				  AND IFNULL(se.docstatus, 0) < 2
				  AND IFNULL(se.work_order, '') = %(wo)s
				  AND IFNULL(sed.is_finished_item, 0) = 1
				  AND IFNULL(sed.item_code, '') = %(item)s
				GROUP BY IFNULL(sed.batch_no, '')
				""",
				{"spr": spr.name, "wo": wo_id, "item": item_code},
				as_dict=True,
			) or []
		else:
			# Site schema fallback: derive scope by WO + date (+ company) when custom_spr_reference is unavailable.
			existing = frappe.db.sql(
				"""
				SELECT IFNULL(sed.batch_no, '') AS batch_no, IFNULL(SUM(IFNULL(sed.qty, 0)), 0) AS qty
				FROM `tabStock Entry` se
				INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
				WHERE IFNULL(se.purpose, '') = 'Manufacture'
				  AND IFNULL(se.docstatus, 0) < 2
				  AND IFNULL(se.work_order, '') = %(wo)s
				  AND IFNULL(se.posting_date, '') = %(posting_date)s
				  AND IFNULL(se.company, '') = %(company)s
				  AND IFNULL(sed.is_finished_item, 0) = 1
				  AND IFNULL(sed.item_code, '') = %(item)s
				GROUP BY IFNULL(sed.batch_no, '')
				""",
				{
					"wo": wo_id,
					"posting_date": spr.run_date,
					"company": wo_doc.company,
					"item": item_code,
				},
				as_dict=True,
			) or []
		for e in existing:
			b = _cstr(e.get("batch_no"))
			q = flt(e.get("qty"))
			existing_total += q
			if b:
				existing_batch_qty[b] += q

		# Pick only truly missing roll rows (batch-wise when possible).
		missing_rows = []
		expected_total = 0.0
		for r in rows:
			rq = flt(spr._row_fg_qty(r))
			if rq <= 0:
				continue
			expected_total += rq
			bn_raw = _cstr(r.get("batch_no"))
			b_link = ""
			if bn_raw:
				try:
					b_link = _cstr(spr._get_batch_link_name_for_stock_entry(bn_raw, item_code, wo_doc.company, r))
				except Exception:
					b_link = ""
			if b_link:
				posted = flt(existing_batch_qty.get(b_link, 0))
				if posted + 1e-9 >= rq:
					continue
			missing_rows.append(r)

		missing_total = flt(sum(spr._row_fg_qty(x) for x in missing_rows))
		if missing_total <= 0:
			skipped.append(
				{
					"work_order": wo_id,
					"reason": "no_missing_rows",
					"expected_total": flt(expected_total, 3),
					"already_created_total": flt(existing_total, 3),
				}
			)
			continue

		# Build Manufacture entry exactly like SPR flow, but only for missing rows.
		se = frappe.new_doc("Stock Entry")
		se.flags.ignore_duplicate_for_work_order = True
		se.company = wo_doc.company
		se.posting_date = spr.run_date or today()
		se.posting_time = nowtime()
		se.set_posting_time = 1
		se.stock_entry_type = spr._manufacture_stock_entry_type_name()
		se.purpose = "Manufacture"
		se.work_order = None
		se.production_item = wo_doc.production_item
		se.fg_completed_qty = missing_total
		se.from_bom = 1
		se.bom_no = wo_doc.bom_no
		se.use_multi_level_bom = wo_doc.use_multi_level_bom
		se.wip_warehouse = wo_doc.wip_warehouse
		se.to_warehouse = wo_doc.fg_warehouse
		spr._set_stock_entry_spr_link(se)
		spr._set_stock_entry_unit(se, wo_doc)
		se.get_items()
		for d in se.items or []:
			if d.item_code and not d.get("t_warehouse"):
				d.s_warehouse = wo_doc.wip_warehouse
		spr._strip_finished_goods_from_stock_entry(se)
		spr._append_manufacture_fg_from_spr_rolls(se, wo_doc, missing_rows)
		se.insert()
		frappe.db.set_value("Stock Entry", se.name, "work_order", wo_id, update_modified=False)
		spr._apply_order_code_to_submitted_stock_entry(se.name)
		if do_submit:
			se.reload()
			se.flags.ignore_duplicate_for_work_order = True
			se.submit()
		created.append(
			{
				"work_order": wo_id,
				"stock_entry": se.name,
				"rows_added": len(missing_rows),
				"qty": flt(missing_total, 3),
				"docstatus": 1 if do_submit else 0,
			}
		)

	# Final sync
	dummy = frappe.new_doc("Shaft Production Run")
	for wo_id in wo_rows.keys():
		if frappe.db.exists("Work Order", wo_id):
			dummy._sync_work_order_produced_qty_from_submitted_manufacture(wo_id)
			dummy._sync_work_order_required_item_progress(wo_id)
	dummy._sync_production_plan_progress_from_work_orders(_cstr(spr.get("production_plan")))

	return {
		"status": "ok",
		"shaft_production_run": spr.name,
		"production_plan": _cstr(spr.get("production_plan")),
		"created_count": len(created),
		"created": created,
		"skipped_count": len(skipped),
		"skipped": skipped[:100],
	}


@frappe.whitelist()
def spr_repair_broken_fg_batch_stock(shaft_production_run: str, submit_entry: int = 1):
	"""
	Repair legacy SPR Manufacture entries whose FG batch rows exist but never posted positive stock ledger.

	Creates a corrective Material Receipt for only the missing FG batch quantities, without consuming RM again.
	"""
	spr_name = _cstr(shaft_production_run)
	if not spr_name:
		frappe.throw(_("Shaft Production Run is required"))
	if not frappe.db.exists("Shaft Production Run", spr_name):
		frappe.throw(_("Shaft Production Run {0} not found").format(spr_name))

	spr = frappe.get_doc("Shaft Production Run", spr_name)
	se_names = [
		x.strip() for x in _cstr(getattr(spr, "manufacturing_entries", "")).split(",") if x and x.strip()
	]
	if not se_names:
		se_names = spr._get_existing_submitted_manufacture_entries_for_spr()
	if not se_names:
		return {"status": "ok", "shaft_production_run": spr.name, "created": [], "skipped": [{"reason": "no_manufacture_entries"}]}

	repair_rows = []
	skipped = []
	for se_name in se_names:
		if not frappe.db.exists("Stock Entry", se_name):
			skipped.append({"stock_entry": se_name, "reason": "stock_entry_not_found"})
			continue
		se = frappe.get_doc("Stock Entry", se_name)
		if _cstr(se.get("purpose")) != "Manufacture" or cint(se.get("docstatus")) != 1:
			skipped.append({"stock_entry": se_name, "reason": "not_submitted_manufacture"})
			continue
		for row in se.items or []:
			if cint(row.get("is_finished_item")) != 1:
				continue
			batch_no = _cstr(row.get("batch_no"))
			item_code = _cstr(row.get("item_code"))
			target_wh = _cstr(row.get("t_warehouse") or getattr(se, "to_warehouse", None))
			qty = flt(row.get("qty"))
			if not batch_no or not item_code or qty <= 0 or not target_wh:
				continue
			posted_qty = flt(
				frappe.db.sql(
					"""
					SELECT IFNULL(SUM(actual_qty), 0)
					FROM `tabStock Ledger Entry`
					WHERE IFNULL(is_cancelled, 0) = 0
					  AND voucher_type = 'Stock Entry'
					  AND voucher_no = %(voucher_no)s
					  AND IFNULL(batch_no, '') = %(batch_no)s
					  AND IFNULL(item_code, '') = %(item_code)s
					  AND IFNULL(warehouse, '') = %(warehouse)s
					  AND actual_qty > 0
					""",
					{
						"voucher_no": se.name,
						"batch_no": batch_no,
						"item_code": item_code,
						"warehouse": target_wh,
					},
				)[0][0]
				or 0
			)
			missing_qty = flt(qty - posted_qty, 6)
			if missing_qty <= 1e-6:
				skipped.append({"stock_entry": se.name, "batch_no": batch_no, "reason": "already_has_fg_sle"})
				continue
			repair_rows.append(
				{
					"source_manufacture": se.name,
					"work_order": _cstr(se.get("work_order")),
					"item_code": item_code,
					"item_name": row.get("item_name"),
					"batch_no": batch_no,
					"qty": missing_qty,
					"uom": row.get("uom") or frappe.db.get_value("Item", item_code, "stock_uom") or "Kg",
					"stock_uom": row.get("stock_uom") or row.get("uom") or frappe.db.get_value("Item", item_code, "stock_uom") or "Kg",
					"conversion_factor": flt(row.get("conversion_factor") or 1),
					"basic_rate": flt(row.get("basic_rate") or row.get("valuation_rate") or 0),
					"t_warehouse": target_wh,
				}
			)

	if not repair_rows:
		return {
			"status": "ok",
			"shaft_production_run": spr.name,
			"created": [],
			"skipped_count": len(skipped),
			"skipped": skipped[:200],
		}

	receipt = frappe.new_doc("Stock Entry")
	receipt.company = repair_rows[0]["t_warehouse"] and frappe.db.get_value("Warehouse", repair_rows[0]["t_warehouse"], "company")
	receipt.posting_date = today()
	receipt.posting_time = nowtime()
	receipt.set_posting_time = 1
	receipt.stock_entry_type = spr._stock_entry_type_name_for_purpose("Material Receipt")
	receipt.purpose = "Material Receipt"
	receipt.remarks = _("SPR FG batch repair for {0}").format(spr.name)
	spr._set_stock_entry_spr_link(receipt)
	spr._set_stock_entry_unit(receipt)

	for r in repair_rows:
		row = {
			"item_code": r["item_code"],
			"item_name": r.get("item_name"),
			"qty": r["qty"],
			"transfer_qty": r["qty"],
			"uom": r["uom"],
			"stock_uom": r["stock_uom"],
			"conversion_factor": r["conversion_factor"],
			"t_warehouse": r["t_warehouse"],
			"batch_no": r["batch_no"],
			"basic_rate": r["basic_rate"],
		}
		if flt(r["basic_rate"]) <= 0:
			row["allow_zero_valuation_rate"] = 1
		receipt.append("items", row)

	receipt.insert()
	spr._persist_stock_entry_spr_reference_db(receipt.name)
	spr._apply_order_code_to_submitted_stock_entry(receipt.name)
	if cint(submit_entry) == 1:
		receipt.submit()

	spr._refresh_batch_qty_for_codes([r["batch_no"] for r in repair_rows])

	return {
		"status": "ok",
		"shaft_production_run": spr.name,
		"repair_stock_entry": receipt.name,
		"repair_docstatus": cint(receipt.docstatus),
		"repaired_batch_count": len(repair_rows),
		"repaired_batches": repair_rows[:200],
		"skipped_count": len(skipped),
		"skipped": skipped[:200],
	}


@frappe.whitelist()
def spr_sync_batches_to_manufacture_entries(shaft_production_run: str):
	"""Create Batch masters from SPR roll lines and patch submitted Manufacture FG lines with batch_no.

	For submitted SPRs where Manufacture entries were posted without batch numbers:
	1. Create tabBatch for each roll line batch_no (via _get_batch_link_name_for_stock_entry).
	2. Update submitted Manufacture STE FG lines to include batch_no.
	3. Refresh Batch qty from SLE.
	"""
	spr_name = _cstr(shaft_production_run)
	if not spr_name or not frappe.db.exists("Shaft Production Run", spr_name):
		frappe.throw(_("Shaft Production Run {0} not found").format(spr_name))
	spr = frappe.get_doc("Shaft Production Run", spr_name)
	if cint(spr.docstatus) != 1:
		frappe.throw(_("SPR {0} must be submitted.").format(spr_name))

	se_names = [
		x.strip() for x in _cstr(getattr(spr, "manufacturing_entries", "")).split(",") if x and x.strip()
	]
	if not se_names:
		se_names = spr._get_existing_submitted_manufacture_entries_for_spr()
	if not se_names:
		frappe.throw(_("No Manufacture entries found for SPR {0}.").format(spr_name))

	roll_batch_map: dict[str, dict] = {}
	for row in spr.items or []:
		bn = _cstr(getattr(row, "batch_no", "")).strip()
		ic = _cstr(getattr(row, "item_code", "")).strip()
		if bn and ic:
			roll_batch_map.setdefault(ic, {})[bn] = row

	created_batches = []
	updated_lines = []
	skipped = []

	for se_name in se_names:
		if not frappe.db.exists("Stock Entry", se_name):
			skipped.append({"stock_entry": se_name, "reason": "not_found"})
			continue
		se_doc = frappe.get_doc("Stock Entry", se_name)
		if _cstr(se_doc.get("purpose")) != "Manufacture" or cint(se_doc.get("docstatus")) != 1:
			skipped.append({"stock_entry": se_name, "reason": "not_submitted_manufacture"})
			continue

		item_code = _cstr(se_doc.get("production_item"))
		company = _cstr(se_doc.get("company"))
		fg_lines = [d for d in (se_doc.items or []) if cint(d.get("is_finished_item")) == 1]
		item_batches = roll_batch_map.get(item_code) or {}

		roll_rows_by_qty: dict[str, list] = {}
		for bn, row in item_batches.items():
			qty_key = f"{flt(spr._row_fg_qty(row), 6)}"
			roll_rows_by_qty.setdefault(qty_key, []).append((bn, row))

		used_batches: set = set()
		for fg in fg_lines:
			existing_bn = _cstr(fg.get("batch_no")).strip()
			if existing_bn:
				skipped.append({"stock_entry": se_name, "line_idx": fg.idx, "reason": "already_has_batch"})
				continue

			fg_qty = flt(fg.get("qty"))
			qty_key = f"{flt(fg_qty, 6)}"
			candidates = roll_rows_by_qty.get(qty_key) or []
			matched_bn = ""
			matched_row = None
			for bn, row in candidates:
				if bn not in used_batches:
					matched_bn = bn
					matched_row = row
					break
			if not matched_bn:
				for bn, row in item_batches.items():
					if bn not in used_batches:
						matched_bn = bn
						matched_row = row
						break
			if not matched_bn:
				skipped.append({"stock_entry": se_name, "line_idx": fg.idx, "reason": "no_matching_roll_batch"})
				continue

			used_batches.add(matched_bn)
			batch_link = spr._get_batch_link_name_for_stock_entry(
				matched_bn, item_code, company, matched_row
			)
			if not batch_link:
				skipped.append({"stock_entry": se_name, "line_idx": fg.idx, "batch_no": matched_bn, "reason": "batch_create_failed"})
				continue

			created_batches.append({"batch_no": batch_link, "item_code": item_code})
			try:
				frappe.db.set_value(
					"Stock Entry Detail",
					fg.name,
					"batch_no",
					batch_link,
					update_modified=False,
				)
				_spr_patch_sle_batch_for_fg_line(se_name, fg, batch_link)
				updated_lines.append({"stock_entry": se_name, "line_idx": fg.idx, "batch_no": batch_link})
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"SPR batch sync line update:{spr_name}")

	spr.sync_batch_custom_fields()
	all_batch_codes = [c["batch_no"] for c in created_batches]
	_spr_activate_batches(all_batch_codes)
	spr._refresh_batch_qty_for_codes(all_batch_codes)
	try:
		frappe.db.commit()
	except Exception:
		pass

	return {
		"status": "ok",
		"shaft_production_run": spr_name,
		"created_batches": len(created_batches),
		"updated_fg_lines": len(updated_lines),
		"updated_details": updated_lines[:200],
		"skipped_count": len(skipped),
		"skipped": skipped[:100],
	}


def _spr_patch_sle_batch_for_fg_line(se_name: str, fg_line, batch_no: str) -> None:
	"""Update Stock Ledger Entry rows for this FG line to include batch_no.

	The Manufacture STE was submitted without batch — SLE rows exist with
	empty batch_no.  We patch them so Batch Qty reflects the stock correctly.
	"""
	if not se_name or not fg_line or not batch_no:
		return
	item_code = _cstr(fg_line.get("item_code")).strip()
	warehouse = _cstr(fg_line.get("t_warehouse")).strip()
	qty = flt(fg_line.get("qty"))
	if not item_code or not warehouse or qty <= 0:
		return
	try:
		sle_names = frappe.db.sql_list(
			"""
			SELECT name FROM `tabStock Ledger Entry`
			WHERE voucher_type = 'Stock Entry'
			  AND voucher_no = %(voucher)s
			  AND IFNULL(item_code, '') = %(item)s
			  AND IFNULL(warehouse, '') = %(wh)s
			  AND actual_qty > 0
			  AND IFNULL(batch_no, '') = ''
			  AND IFNULL(is_cancelled, 0) = 0
			ORDER BY ABS(actual_qty - %(qty)s) ASC
			LIMIT 1
			""",
			{"voucher": se_name, "item": item_code, "wh": warehouse, "qty": qty},
		)
		for sle_name in sle_names or []:
			frappe.db.set_value(
				"Stock Ledger Entry", sle_name, "batch_no", batch_no, update_modified=False
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"SPR batch sync SLE patch:{se_name}")


def _spr_activate_batches(batch_codes: list[str]) -> None:
	"""Set Batch status to Active and recompute batch_qty from SLE."""
	for bn in {_cstr(x).strip() for x in (batch_codes or []) if _cstr(x).strip()}:
		if not frappe.db.exists("Batch", bn):
			continue
		try:
			qty = flt(
				frappe.db.sql(
					"""
					SELECT IFNULL(SUM(actual_qty), 0)
					FROM `tabStock Ledger Entry`
					WHERE IFNULL(is_cancelled, 0) = 0
					  AND IFNULL(batch_no, '') = %s
					""",
					(bn,),
				)[0][0] or 0
			)
			updates = {}
			if frappe.db.has_column("Batch", "batch_qty"):
				updates["batch_qty"] = qty
			if frappe.db.has_column("Batch", "status"):
				updates["status"] = "Active" if qty > 0 else "Empty"
			if updates:
				frappe.db.set_value("Batch", bn, updates, update_modified=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"SPR batch activate:{bn}")


@frappe.whitelist()
def spr_set_bundle_packaging_on_submit(shaft_production_run, enabled=0):
	"""Toggle whether SPR submit posts combined FG from Bundle Stickers (testing / rollout)."""
	_spr_require_saved(shaft_production_run)
	if not frappe.db.has_column("Shaft Production Run", "custom_use_bundle_packaging_on_submit"):
		frappe.throw(
			_("Field custom_use_bundle_packaging_on_submit is missing. Run bench migrate on Production Planning app."),
			title=_("Migrate required"),
		)
	on = 1 if cint(enabled) else 0
	spr = frappe.get_doc("Shaft Production Run", shaft_production_run)
	if cint(spr.docstatus) != 0:
		frappe.throw(_("Cannot change bundle packaging mode after submit."))
	spr.custom_use_bundle_packaging_on_submit = on
	spr.save(ignore_permissions=True)
	mode = _("ON — Bundle Stickers combined FG first, then roll lines") if on else _(
		"OFF — Each roll line is its own FG (Bundle Stickers ignored)"
	)
	return {"enabled": on, "mode_label": mode}


@frappe.whitelist()
def spr_get_bundle_packaging_on_submit_status(shaft_production_run):
	"""Return current bundle-packaging toggle for SPR toolbar."""
	if not shaft_production_run or not frappe.db.exists("Shaft Production Run", shaft_production_run):
		return {"enabled": 0, "available": False}
	if not frappe.db.has_column("Shaft Production Run", "custom_use_bundle_packaging_on_submit"):
		return {"enabled": 0, "available": False}
	enabled = cint(frappe.db.get_value("Shaft Production Run", shaft_production_run, "custom_use_bundle_packaging_on_submit") or 0)
	return {"enabled": enabled, "available": True}


@frappe.whitelist()
def spr_get_bundle_packaging_catalog(shaft_production_run):
	"""Jobs from Available Jobs; width options use per-segment widths (combination/WO), then roll widths."""
	_spr_require_saved(shaft_production_run)
	spr = frappe.get_doc("Shaft Production Run", shaft_production_run)
	jobs_out = []
	seen = set()
	for sj in _spr_job_rows(spr):
		jid = _cstr(_spr_job_id(sj))
		if not jid or jid in seen:
			continue
		seen.add(jid)
		jobs_out.append(
			{
				"job_id": jid,
				"label": _spr_bundle_job_label(sj),
				"total_width_available": flt(getattr(sj, "total_width", None)),
				"combination_text": _cstr(getattr(sj, "combination", None) or ""),
				"segments": _spr_bundle_job_segments_detail(spr, sj),
			}
		)
	widths_by_job: dict[str, list] = {j["job_id"]: [] for j in jobs_out}
	for j in jobs_out:
		jid = j["job_id"]
		sj = _spr_shaft_job_for_roll(spr, jid)
		if sj:
			widths_by_job[jid] = _spr_bundle_segment_widths_for_job(spr, sj)
	return {"jobs": jobs_out, "widths_by_job": widths_by_job}


@frappe.whitelist()
def spr_get_bundle_packaging_lines(shaft_production_run):
	"""Deprecated: use spr_get_bundle_packaging_catalog."""
	return spr_get_bundle_packaging_catalog(shaft_production_run)


def _spr_calc_net_weight_from_gross_for_bundle(row, gross_kg: float) -> float:
	"""
	Server-side replica of the desk calculation used when operators enter `gross_weight`.
	This is required because bundle packaging sets gross/prod length in the backend and
	grid triggers do not run on reload.
	"""
	try:
		width = flt(getattr(row, "width_inch", None))
	except Exception:
		width = 0.0
	gw = flt(gross_kg)
	if width <= 0 or gw <= 0:
		return 0.0

	gsm_val = flt(getattr(row, "gsm", None) or 0) or flt(getattr(row, "sticker_gsm", None) or 0) or 90.0
	width_in_meter = width * 0.0254
	raw_weight = (gsm_val * width_in_meter * gw) / 1000.0

	standard_widths = (63.0, 85.0, 90.0, 118.0, 126.0)
	is_standard = any(abs(width - w) < 0.01 for w in standard_widths)

	core_weight = 0.0
	if is_standard:
		base_weight_of_core = 1.3
		if 50.0 <= raw_weight <= 100.0:
			base_weight_of_core = 1.8
		elif raw_weight > 100.0:
			base_weight_of_core = 2.5
		numeric_core_width = flt(getattr(row, "custom_core_width_mm", None) or 1600.0) or 1600.0
		core_weight = (base_weight_of_core / 1600.0) * numeric_core_width
	else:
		if width < 63.0:
			core_width, prorate = 63.0, 1.30
		elif width < 85.0:
			core_width, prorate = 85.0, 1.75
		elif width < 90.0:
			core_width, prorate = 90.0, 1.86
		elif width < 118.0:
			core_width, prorate = 118.0, 2.43
		else:
			core_width, prorate = 126.0, 2.60
		core_weight = (width / core_width) * prorate

	net_val = gw - core_weight
	if net_val <= 0:
		net_val = gw
	return flt(net_val, 2)


@frappe.whitelist()
def spr_apply_bundle_packaging_for_job_width(
	shaft_production_run,
	job_id,
	width_inch,
	no_of_packaging,
	whole_gross_kg,
	produced_length_mtrs=None,
):
	"""Apply packaging to first-unpacked N roll lines for Job + selected width segment."""
	_spr_require_saved(shaft_production_run)
	job_id = _cstr(job_id)
	width_inch = flt(width_inch)
	no_of_packaging = cint(no_of_packaging)
	whole_gross_kg = flt(whole_gross_kg)
	produced_length_mtrs = flt(produced_length_mtrs)
	if no_of_packaging < 1:
		frappe.throw(_("Number of packaging must be at least 1"))
	if whole_gross_kg <= 0:
		frappe.throw(_("Whole gross weight must be greater than zero"))
	if produced_length_mtrs <= 0:
		frappe.throw(_("Produced length must be greater than zero"))
	if not job_id:
		frappe.throw(_("Select a job from Available Jobs"))
	if width_inch <= 0:
		frappe.throw(_("Select a width (in)"))

	spr = frappe.get_doc("Shaft Production Run", shaft_production_run)
	sj = _spr_shaft_job_for_roll(spr, job_id)
	if not sj:
		frappe.throw(_("Job {0} not found in Available Jobs").format(job_id))

	job_w = width_inch
	matching = []
	for it in spr.items or []:
		if not _spr_item_roll_matches_bundle_job(sj, it, job_id):
			continue
		if _spr_roll_matches_bundle_width(it, width_inch, job_w):
			matching.append(it)

	if not matching:
		for it in spr.items or []:
			if not _spr_item_roll_matches_bundle_job(sj, it, job_id):
				continue
			rw = _spr_roll_effective_width_inch(it)
			if rw > 0.001 and abs(rw - flt(width_inch)) <= 0.75:
				matching.append(it)

	if not matching:
		frappe.throw(
			_(
				"No roll lines for job {0} with width {1} in. Create roll entry or check widths. "
				"(If this is a combination job, pick the segment width that matches the roll item, not total width.)"
			).format(job_id, width_inch)
		)

	# Sequential real-world packing: always use first N unpacked rolls by roll_no/index.
	def _sort_key(it):
		rn = cint(getattr(it, "roll_no", 0) or 0)
		idx = cint(getattr(it, "idx", 0) or 0)
		return (rn if rn > 0 else 999999, idx if idx > 0 else 999999, _cstr(getattr(it, "name", "")))

	matching = sorted(matching, key=_sort_key)

	def _row_key(it):
		return _cstr(getattr(it, "name", "")) or str(cint(getattr(it, "idx", 0) or 0))

	def _is_unpackable(it):
		return flt(getattr(it, "gross_weight", 0) or 0) <= 0

	unpacked = []
	for it in matching:
		if not _is_unpackable(it):
			continue
		unpacked.append(it)

	if len(unpacked) < no_of_packaging:
		seen = {_row_key(it) for it in matching}
		ref_items = {_cstr(getattr(it, "item_code", None)) for it in matching if _cstr(getattr(it, "item_code", None))}
		job_item = _spr_job_product_code(sj)
		if job_item:
			ref_items.add(job_item)
		extra = []
		for it in spr.items or []:
			if not _spr_item_roll_matches_bundle_job(sj, it, job_id):
				continue
			if _row_key(it) in seen:
				continue
			if not _is_unpackable(it):
				continue
			item_code = _cstr(getattr(it, "item_code", None))
			if ref_items and item_code and item_code not in ref_items:
				continue
			extra.append(it)
		if extra:
			matching = sorted(list(matching) + extra, key=_sort_key)
			unpacked = [it for it in matching if _is_unpackable(it)]

	if len(unpacked) < no_of_packaging:
		frappe.throw(
			_("Only {0} unpacked rolls available for job {1} width {2} Inches, but {3} requested.")
			.format(len(unpacked), job_id, width_inch, no_of_packaging)
		)

	selected = unpacked[:no_of_packaging]
	single_gross = round(whole_gross_kg / float(no_of_packaging), 2)
	total_width_inch = round(width_inch * float(no_of_packaging), 4)

	item_meta = frappe.get_meta("Shaft Production Run Item")
	can_set_net = item_meta.has_field("net_weight")
	can_set_len = item_meta.has_field("produced_length_mtrs")
	for it in selected:
		it.gross_weight = single_gross
		if can_set_len:
			it.produced_length_mtrs = produced_length_mtrs
		if can_set_net:
			it.net_weight = _spr_calc_net_weight_from_gross_for_bundle(it, single_gross)

	bundle_net = round(sum(flt(getattr(it, "net_weight", None)) for it in selected), 2)

	# Extract batch_no (common prefix) and roll numbers from the selected rolls.
	# Batch format is "BATCHPREFIX/ROLLNO" — all rolls in a bundle share the same prefix.
	bundle_batch_no = ""
	roll_numbers_list = []
	for it in selected:
		bn = _cstr(getattr(it, "batch_no", "") or "")
		rn = _cstr(getattr(it, "roll_no", "") or "")
		if bn and "/" in bn:
			prefix = bn.rsplit("/", 1)[0]
			if not bundle_batch_no:
				bundle_batch_no = prefix
		elif bn and not bundle_batch_no:
			bundle_batch_no = bn
		if rn:
			roll_numbers_list.append(rn)
		elif bn and "/" in bn:
			# Fallback: extract roll number from batch_no suffix
			roll_numbers_list.append(bn.rsplit("/", 1)[1])
	roll_numbers_str = ", ".join(roll_numbers_list)

	# Store combination as: NO_OF_PACKAGING * WIDTH Inches (example: 4 * 39 Inches)
	comb_calculated = f"{no_of_packaging} * {width_inch} Inches"
	if bundle_batch_no:
		bundle_batch_no = _spr_next_bundle_batch_no(spr, bundle_batch_no)
	bs = {
		"combination": comb_calculated,
		"rolls_per_bundle": no_of_packaging,
		"single_roll_gross_weight_kg": single_gross,
		"sticker_width": total_width_inch,
		"sticker_bundle_gross_weight_kg": round(whole_gross_kg, 2),
		"sticker_bundle_weight": bundle_net,
	}
	bs_meta = frappe.get_meta("Bundle Stickers")
	# Some sites use a custom produced-length field on Bundle Stickers; populate whichever exists.
	if bs_meta.has_field("produced_length_mtrs"):
		bs["produced_length_mtrs"] = produced_length_mtrs
	if bs_meta.has_field("custom_produced_length_mtrs"):
		bs["custom_produced_length_mtrs"] = produced_length_mtrs
	if bs_meta.has_field("job_id"):
		bs["job_id"] = job_id or None
	if bs_meta.has_field("batch_no"):
		bs["batch_no"] = bundle_batch_no or None
	if bs_meta.has_field("roll_numbers"):
		bs["roll_numbers"] = roll_numbers_str or None
	spr.append("bundle_stickers", bs)
	spr.save(ignore_permissions=True)
	remaining_unpacked = max(len(unpacked) - no_of_packaging, 0)

	return {
		"updated_rolls": len(selected),
		"single_roll_gross_kg": single_gross,
		"total_width_inch": total_width_inch,
		"sticker_bundle_weight_kg": bundle_net,
		"remaining_unpacked_rolls": remaining_unpacked,
		"applied_produced_length": produced_length_mtrs,
	}


@frappe.whitelist()
def spr_apply_bundle_packaging(
	shaft_production_run,
	spr_item_row_name,
	no_of_packaging,
	whole_gross_kg,
):
	"""Single-roll gross on matched line + Bundle Stickers row (Kg / inch)."""
	_spr_require_saved(shaft_production_run)
	no_of_packaging = cint(no_of_packaging)
	whole_gross_kg = flt(whole_gross_kg)
	if no_of_packaging < 1:
		frappe.throw(_("Number of packaging must be at least 1"))
	if whole_gross_kg <= 0:
		frappe.throw(_("Whole gross weight must be greater than zero"))
	if not spr_item_row_name:
		frappe.throw(_("Select a roll line"))

	spr = frappe.get_doc("Shaft Production Run", shaft_production_run)
	target = None
	for it in spr.items or []:
		if _cstr(it.name) == _cstr(spr_item_row_name):
			target = it
			break
	if not target:
		frappe.throw(_("Roll line not found"))

	jid = _cstr(getattr(target, "job", None))
	sj = _spr_shaft_job_for_roll(spr, jid)
	sel_w = flt(getattr(sj, "total_width", None)) if sj else 0.0
	if sel_w <= 0:
		sel_w = flt(getattr(target, "width_inch", None))
	single_gross = round(whole_gross_kg / float(no_of_packaging), 2)
	total_width_inch = round(sel_w * float(no_of_packaging), 4)
	net_one = flt(getattr(target, "net_weight", None))
	item_meta = frappe.get_meta("Shaft Production Run Item")
	if item_meta.has_field("net_weight"):
		target.net_weight = _spr_calc_net_weight_from_gross_for_bundle(target, single_gross)
	net_one = flt(getattr(target, "net_weight", None))
	bundle_net = round(net_one * float(no_of_packaging), 2)

	target.gross_weight = single_gross

	comb = ""
	if sj:
		comb = _cstr(getattr(sj, "combination", None))
	else:
		for row in spr.shaft_jobs or []:
			if _cstr(_spr_job_id(row)) == jid:
				comb = _cstr(getattr(row, "combination", None))
				break

	# Extract batch_no and roll_no from the target roll line.
	bundle_batch_no = ""
	roll_numbers_str = ""
	bn = _cstr(getattr(target, "batch_no", "") or "")
	rn = _cstr(getattr(target, "roll_no", "") or "")
	if bn and "/" in bn:
		bundle_batch_no = bn.rsplit("/", 1)[0]
		if not rn:
			rn = bn.rsplit("/", 1)[1]
	elif bn:
		bundle_batch_no = bn
	if bundle_batch_no:
		bundle_batch_no = _spr_next_bundle_batch_no(spr, bundle_batch_no)
	roll_numbers_str = rn

	bs = {
		"combination": comb or None,
		"rolls_per_bundle": no_of_packaging,
		"single_roll_gross_weight_kg": single_gross,
		"sticker_width": total_width_inch,
		"sticker_bundle_gross_weight_kg": round(whole_gross_kg, 2),
		"sticker_bundle_weight": bundle_net,
	}
	bs_meta = frappe.get_meta("Bundle Stickers")
	if bs_meta.has_field("job_id"):
		bs["job_id"] = jid or None
	if bs_meta.has_field("batch_no"):
		bs["batch_no"] = bundle_batch_no or None
	if bs_meta.has_field("roll_numbers"):
		bs["roll_numbers"] = roll_numbers_str or None
	spr.append("bundle_stickers", bs)
	spr.save(ignore_permissions=True)

	return {
		"single_roll_gross_kg": single_gross,
		"total_width_inch": total_width_inch,
		"sticker_bundle_weight_kg": bundle_net,
	}


def _fill_party_code_from_resolved_wos(m: dict, job_meta, wos: list) -> None:
	"""Set child row party_code (Order Code) from the resolved WO when the plan row did not supply it."""
	if not wos or not job_meta or not job_meta.has_field("party_code"):
		return
	v = m.get("party_code")
	if v is not None and str(v).strip():
		return
	try:
		wo_doc = frappe.get_doc("Work Order", wos[0]["name"])
		pc = get_order_code(wo_doc)
		if pc:
			m["party_code"] = pc
	except Exception:
		pass


def get_order_code(wo_doc):
	"""Party / order code for roll lines: WO custom fields, then Sales Order."""
	for attr in ("order_code", "custom_order_code", "custom_party_code"):
		v = getattr(wo_doc, attr, None)
		if v is not None and str(v).strip():
			return str(v).strip()
	so = getattr(wo_doc, "sales_order", None)
	if so:
		for col in ("custom_party_code", "po_no"):
			if frappe.db.has_column("Sales Order", col):
				v = frappe.db.get_value("Sales Order", so, col)
				if v is not None and str(v).strip():
					return str(v).strip()
		return str(so).strip()
	return ""


@frappe.whitelist()
def spr_sync_bundle_produced_sheets(spr_name: str | None = None):
	"""Recompute bundle_calculation totals and sheet-cutting header fields (desk)."""
	spr_name = _cstr(spr_name)
	if not spr_name or not frappe.db.exists("Shaft Production Run", spr_name):
		frappe.throw(_("Shaft Production Run not found."))
	doc = frappe.get_doc("Shaft Production Run", spr_name)
	sync_bundle_total_produced_sheets_for_doc(doc)
	sync_bundle_total_produced_bag_pcs_for_doc(doc)
	if cint(getattr(doc, "custom_is_sheet_cutting", 0)) or cint(getattr(doc, "custom_is_box_bag", 0)):
		sync_bundle_total_achieved_weight_for_doc(doc)
		sync_bundle_consumed_meter_header(doc)
	if cint(doc.docstatus) == 0:
		doc._spr_recalc_total_produced_weight_header()
		doc.save()
	out = []
	for br in doc.get("bundle_calculation") or []:
		out.append(
			{
				"name": br.name,
				"total_produced_sheets": flt(getattr(br, "total_produced_sheets", 0) or 0),
				"total_produced_bag_pcs": flt(getattr(br, "total_produced_bag_pcs", 0) or 0),
				"total_achieved_weight": flt(getattr(br, "total_achieved_weight", 0) or 0),
				"total_consumed_meter": flt(getattr(br, "total_consumed_meter", 0) or 0),
			}
		)
	return {
		"status": "ok",
		"rows": out,
		"total_produced_weight": flt(getattr(doc, "total_produced_weight", 0) or 0),
		"custom_total_achieved_meter": flt(getattr(doc, "custom_total_achieved_meter", 0) or 0),
	}


@frappe.whitelist()
def spr_get_fabric_batch_pick_context(spr_name: str | None = None):
	"""Return WO / 100-fabric requirements, available WIP batches, and saved picks for the desk dialog."""
	spr_name = _cstr(spr_name)
	if not spr_name or not frappe.db.exists("Shaft Production Run", spr_name):
		frappe.throw(_("Shaft Production Run not found."))
	doc = frappe.get_doc("Shaft Production Run", spr_name)
	return doc._spr_build_fabric_batch_pick_context_dict()


def _spr_resolve_batch_link_name(batch_no: str, item_code: str = "") -> str:
	"""Map SLE / label batch text to a valid Batch.name for Link fields."""
	bn = _cstr(batch_no).strip()
	if not bn:
		return ""
	if frappe.db.exists("Batch", bn):
		return bn
	alt = frappe.db.get_value("Batch", {"batch_id": bn}, "name")
	if alt:
		return _cstr(alt)
	if frappe.db.has_column("Batch", "batch_id"):
		row = frappe.db.sql(
			"""
			SELECT name, item FROM `tabBatch`
			WHERE batch_id = %s OR name = %s
			ORDER BY creation DESC
			LIMIT 1
			""",
			(bn, bn),
			as_dict=True,
		)
		if row:
			name = _cstr(row[0].get("name"))
			batch_item = _cstr(row[0].get("item"))
			ic = _cstr(item_code)
			if ic and batch_item and batch_item != ic:
				frappe.throw(_("Batch {0} is for item {1}, not {2}.").format(name, batch_item, ic))
			return name
	frappe.throw(
		_("Batch {0} was not found in Batch master. Pick a batch from stock list or create the Batch record first.").format(
			bn
		),
		title=_("Invalid batch"),
	)


@frappe.whitelist()
def spr_diagnose_save_blockers(spr_name: str | None = None):
	"""Desk troubleshooting: duplicate fields, validate preview, RM batch gaps."""
	spr_name = _cstr(spr_name)
	out: dict = {
		"spr": spr_name,
		"docstatus": None,
		"is_bag_spr": False,
		"duplicate_custom_fields": [],
		"fabric_batch_picks_count": 0,
		"rm_batch_context": {},
		"validate_ok": True,
		"validate_error": "",
		"batch_prefix_ok": True,
		"batch_prefix_note": "",
		"form_dirty_causes": [],
	}
	if not spr_name or not frappe.db.exists("Shaft Production Run", spr_name):
		out["validate_ok"] = False
		out["validate_error"] = _("Shaft Production Run not found.")
		return out

	for fn in ("company", "custom_total_planned_pcs", "custom_total_achieved_pcs"):
		cfs = frappe.get_all(
			"Custom Field",
			filters={"dt": "Shaft Production Run", "fieldname": fn},
			pluck="name",
		)
		if cfs:
			out["duplicate_custom_fields"].append({"fieldname": fn, "names": cfs})

	doc = frappe.get_doc("Shaft Production Run", spr_name)
	out["docstatus"] = cint(doc.docstatus)
	out["is_bag_spr"] = spr_doc_is_bag_spr(doc)
	out["fabric_batch_picks_count"] = len(doc.get("fabric_batch_picks") or [])
	try:
		ctx = doc._spr_build_fabric_batch_pick_context_dict()
		out["rm_batch_context"] = {
			"needs_picks": bool(ctx.get("needs_picks")),
			"line_count": len(ctx.get("lines") or []),
			"is_bag_spr": bool(ctx.get("is_bag_spr")),
		}
	except Exception as exc:
		out["rm_batch_context"] = {"error": _cstr(exc)}

	parts = spr_batch_prefix_for_unit(doc.get("custom_unit"))
	if not parts and _cstr(doc.get("custom_unit")).strip():
		out["batch_prefix_ok"] = False
		out["batch_prefix_note"] = _(
			"Unit «{0}» has no roll batch prefix — roll batch_no assignment is skipped on Save."
		).format(doc.get("custom_unit"))

	if out["duplicate_custom_fields"]:
		out["form_dirty_causes"].append(
			_("Duplicate Custom Field rows on this site — run bench migrate (cleanup_spr_duplicate_custom_fields).")
		)

	try:
		probe = frappe.copy_doc(doc)
		probe.run_method("validate")
	except Exception as exc:
		out["validate_ok"] = False
		out["validate_error"] = _cstr(exc)

	if not out["validate_ok"]:
		out["form_dirty_causes"].append(_("Server validate() failed — see validate_error."))
	elif out["duplicate_custom_fields"]:
		out["form_dirty_causes"].append(
			_("Save may succeed but duplicate header fields confuse the desk — migrate to remove Custom Field copies.")
		)
	else:
		out["form_dirty_causes"].append(
			_(
				"If the form shows Not Saved after Save, hard-refresh (Ctrl+F5). "
				"Desk auto-sync was re-marking the form dirty — fixed in latest JS."
			)
		)

	return out


@frappe.whitelist()
def spr_save_fabric_batch_picks(spr_name: str | None = None, picks_json=None):
	"""Replace `fabric_batch_picks` on a Draft SPR from the desk dialog."""
	import json

	spr_name = _cstr(spr_name)
	if not spr_name or not frappe.db.exists("Shaft Production Run", spr_name):
		frappe.throw(_("Shaft Production Run not found."))
	doc = frappe.get_doc("Shaft Production Run", spr_name)
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Fabric batch picks can only be saved on a Draft SPR."))
	if not frappe.get_meta("Shaft Production Run").has_field("fabric_batch_picks"):
		frappe.throw(_("Run bench migrate to add fabric batch fields."))
	picks = picks_json
	if isinstance(picks, str):
		picks = json.loads(picks)
	doc.fabric_batch_picks = []
	for p in picks or []:
		wo = _cstr((p or {}).get("work_order"))
		ic = _cstr((p or {}).get("item_code"))
		bn_raw = _cstr((p or {}).get("batch_no"))
		q = flt((p or {}).get("qty"))
		if not wo or not ic or not bn_raw or q <= 0:
			continue
		bn = _spr_resolve_batch_link_name(bn_raw, ic)
		doc.append(
			"fabric_batch_picks",
			{"work_order": wo, "item_code": ic, "batch_no": bn, "qty": q},
		)
	try:
		doc.save()
	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), f"spr_save_fabric_batch_picks:{spr_name}")
		frappe.throw(
			_("Could not save RM batch picks on {0}: {1}").format(spr_name, _cstr(exc)),
			title=_("Save failed"),
		)
	return {"status": "ok", "name": doc.name, "count": len(doc.fabric_batch_picks or [])}


