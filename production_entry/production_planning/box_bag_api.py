# -*- coding: utf-8 -*-
"""
Box Bag (process 221) — Board + Order Table API functions.

All functions are imported and called from scheduler_api.py.
"""
import frappe
from frappe.utils import flt, cint

from production_entry.production_planning.planning_doctypes import (
	BOX_BAG_UNIT_L1,
	BOX_BAG_UNIT_L2,
	BOX_BAG_UNASSIGNED_UNIT,
	W_CUT_D_CUT_UNIT_JVE_L1,
	W_CUT_D_CUT_UNIT_JVE_L2,
	W_CUT_D_CUT_UNIT_JVE_L3,
	W_CUT_D_CUT_UNIT_L1,
	W_CUT_D_CUT_UNIT_L2,
	W_CUT_D_CUT_UNIT_L3,
	W_CUT_D_CUT_ALL_UNITS,
	W_CUT_UNASSIGNED_UNIT,
	D_CUT_UNASSIGNED_UNIT,
)

BOX_BAG_UNITS = (BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L2, BOX_BAG_UNASSIGNED_UNIT)
W_CUT_D_CUT_UNITS = W_CUT_D_CUT_ALL_UNITS
D_CUT_PROCESS_CODES = ("211", "212", "213", "214", "216", "217")
W_CUT_PROCESS_CODES = ("200", "201", "202", "203")
W_CUT_D_CUT_FG_PROCESS_CODES = D_CUT_PROCESS_CODES + W_CUT_PROCESS_CODES
ALL_BAG_FG_PROCESS_CODES = W_CUT_D_CUT_FG_PROCESS_CODES  # extended in scheduler with box bag codes

_BOX_BAG_FINISHING_MAP = {
	"PP": "Plain",
	"MM": "Metallic / Matte",
	"MG": "Metallic / Glossy",
	"CM": "Cooler / Matte",
	"CG": "Cooler / Glossy",
	"PM": "Plain / Matte",
	"PG": "Plain / Glossy",
	"0M": "Matte",
	"M": "Matte",
	"G": "Glossy",
}


def _spr_achieved_bag_pcs_total(spr_name_csv: str) -> float:
	"""Sum achieved bag pcs across submitted/draft SPR ids stored in CSV."""
	if not frappe.db.table_exists("Shaft Production Run Item"):
		return 0.0
	raw = str(spr_name_csv or "").strip()
	if not raw:
		return 0.0
	names = [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]
	if not names:
		return 0.0
	placeholders = ", ".join(["%s"] * len(names))
	rows = frappe.db.sql(
		f"""
		SELECT SUM(IFNULL(custom_achieved_bag_pcs, 0)) AS pcs_sum
		FROM `tabShaft Production Run Item`
		WHERE parent IN ({placeholders})
		""",
		tuple(names),
		as_dict=True,
	)
	return flt((rows[0] or {}).get("pcs_sum") or 0)


def _spr_total_achieved_meters_from_bundle(spr_name_csv: str) -> float:
	"""Board Total Achieved Meters: SUM(bundle_calculation.total_consumed_meter) for linked SPR(s)."""
	if not frappe.db.table_exists("Bundle Calculation"):
		return 0.0
	raw = str(spr_name_csv or "").strip()
	if not raw:
		return 0.0
	names = [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]
	if not names:
		return 0.0
	placeholders = ", ".join(["%s"] * len(names))
	rows = frappe.db.sql(
		f"""
		SELECT SUM(IFNULL(total_consumed_meter, 0)) AS m_sum
		FROM `tabBundle Calculation`
		WHERE parent IN ({placeholders})
		""",
		tuple(names),
		as_dict=True,
	)
	return flt((rows[0] or {}).get("m_sum") or 0)


def _box_bag_finishing_label(code):
	"""Decode 2-char finishing suffix to human label."""
	return _BOX_BAG_FINISHING_MAP.get(str(code or "").strip().upper(), str(code or "").strip())


def _parse_box_bag_item_code(item_code):
	"""Parse box bag item code: DESIGN-BAGSIZE-221QCCCGLLBB
	Format: 6000-511-221N101Q00PP or 6000-511-224F542R0C0M
	  - 6000   = design code (before first hyphen)
	  - 511    = bag size id (between first and second hyphen, from Bag Series)
	  - 221/224 = process code
	  - F      = quality letter (1 char, from Quality Master / LAMINATION_QUALITY_CODES)
	  - 542    = colour code (3 digits)
	  - R      = fabric GSM letter (105)
	  - 0      = bopp GSM digit/letter (0)
	  - C      = lam GSM letter (15)
	  - 0M     = finishing code (optional tail)
	  Total GSM = fabric + bopp + lam (e.g. 105 + 0 + 15 = 120)
	"""
	result = {
		"design_code": "",
		"bag_size_id": "",
		"process": "221",
		"quality_letter": "",
		"colour_code": "",
		"fabric_gsm": 0,
		"lam_gsm": 0,
		"bopp_gsm": 0,
		"total_gsm": 0,
		"finishing_code": "",
		"finishing_label": "",
	}
	ic = str(item_code or "").strip()
	if not ic:
		return result

	parts = ic.split("-")
	if len(parts) >= 3:
		result["design_code"] = parts[0].strip()
		result["bag_size_id"] = parts[1].strip()
		tail = "-".join(parts[2:]).strip()  # e.g. 221N101Q00PP
	elif len(parts) == 2:
		result["design_code"] = parts[0].strip()
		tail = parts[1].strip()
	else:
		tail = ic

	# Find "221" or "224" in the tail
	idx221 = tail.find("221")
	idx224 = tail.find("224")
	
	process = "221"
	idx = idx221
	
	if idx224 >= 0 and (idx221 < 0 or idx224 < idx221):
		process = "224"
		idx = idx224

	if idx < 0:
		return result
		
	result["process"] = process

	after = tail[idx + 3:]  # e.g. N101Q00PP
	if len(after) >= 1:
		result["quality_letter"] = after[0]
	if len(after) >= 4:
		result["colour_code"] = after[1:4]
	if len(after) >= 5:
		from production_entry.production_planning.bopp_bag_api import _decode_fabric_gsm_char, _decode_lam_bopp_gsm_char
		result["fabric_gsm"] = _decode_fabric_gsm_char(after[4])
	if len(after) >= 6:
		result["lam_gsm"] = _decode_lam_bopp_gsm_char(after[5])
	if len(after) >= 7:
		result["bopp_gsm"] = _decode_lam_bopp_gsm_char(after[6])
	if len(after) >= 9:
		result["finishing_code"] = after[7:9].upper()
		result["finishing_label"] = _box_bag_finishing_label(after[7:9])
	elif len(after) > 7:
		result["finishing_code"] = after[7:].upper()
		result["finishing_label"] = _box_bag_finishing_label(after[7:])

	result["total_gsm"] = result["fabric_gsm"] + result["lam_gsm"] + result["bopp_gsm"]
	return result


def _dcut_process_label(process_code):
	p = str(process_code or "").strip()
	if p == "211":
		return "211 plain d cut bag"
	if p == "212":
		return "212 printed d cut bag"
	if p == "213":
		return "213 plain laminated d cut bag"
	if p == "217":
		return "217 d cut bopp bag"
	if p == "216":
		return "216 d cut mettalic roto"
	if p == "214":
		return "214 printed d cut bag"
	return p


def _wcut_process_label(process_code):
	p = str(process_code or "").strip()
	if p == "200":
		return "200 plain w cut bag"
	if p == "201":
		return "201 printed w cut bag"
	if p == "202":
		return "202 laminated w cut bag"
	if p == "203":
		return "203 printed laminated w cut bag"
	return p


def _wcut_dcut_process_label(process_code):
	p = str(process_code or "").strip()
	if p in W_CUT_PROCESS_CODES:
		return _wcut_process_label(p)
	return _dcut_process_label(p)


def _parse_dcut_bag_item_code(item_code):
	"""Parse D-CUT code: DESIGN[-NCOLOURS]-SIZE-PROCESSQCCCFLBBFF."""
	from production_entry.production_planning.bopp_bag_api import _decode_fabric_gsm_char, _decode_lam_bopp_gsm_char

	out = {
		"design_code": "",
		"num_colors": "",
		"bag_size_id": "",
		"process": "",
		"quality_letter": "",
		"colour_code": "",
		"fabric_gsm": 0,
		"lam_gsm": 0,
		"bopp_gsm": 0,
		"total_gsm": 0,
		"finishing_code": "",
		"finishing_label": "",
	}
	ic = str(item_code or "").strip()
	if not ic:
		return out

	parts = ic.split("-")
	if not parts:
		return out
	out["design_code"] = parts[0].strip()

	tail_idx = 1
	if len(parts) >= 4:
		m = str(parts[1] or "").strip()
		if m.upper().endswith("C") and m[:-1].isdigit():
			out["num_colors"] = m[:-1]
			out["bag_size_id"] = str(parts[2] or "").strip()
			tail_idx = 3
		else:
			out["bag_size_id"] = str(parts[1] or "").strip()
			tail_idx = 2
	elif len(parts) >= 3:
		out["bag_size_id"] = str(parts[1] or "").strip()
		tail_idx = 2

	tail = "-".join(parts[tail_idx:]).strip()
	process = ""
	at = -1
	for p in W_CUT_D_CUT_FG_PROCESS_CODES:
		i = tail.find(p)
		if i >= 0 and (at < 0 or i < at):
			at = i
			process = p
	if at < 0:
		return out
	out["process"] = process
	after = tail[at + 3:]
	if len(after) >= 1:
		out["quality_letter"] = after[0]
	if len(after) >= 4:
		out["colour_code"] = after[1:4]
	if len(after) >= 5:
		out["fabric_gsm"] = _decode_fabric_gsm_char(after[4])
	if len(after) >= 6:
		out["lam_gsm"] = _decode_lam_bopp_gsm_char(after[5])
	if len(after) >= 7:
		out["bopp_gsm"] = _decode_lam_bopp_gsm_char(after[6])
	if len(after) >= 9:
		out["finishing_code"] = after[7:9].upper()
		out["finishing_label"] = _box_bag_finishing_label(after[7:9])
	elif len(after) > 7:
		out["finishing_code"] = after[7:].upper()
		out["finishing_label"] = _box_bag_finishing_label(after[7:])
	out["total_gsm"] = out["fabric_gsm"] + out["lam_gsm"] + out["bopp_gsm"]
	return out


def _bag_series_size_map():
	"""Return {bag_series_name: size_in_inches} from the Bag Series doctype."""
	cache_key = "box_bag_series_size_map"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached
	result = {}
	try:
		if not frappe.db.exists("DocType", "Bag Series"):
			return result
		meta = frappe.get_meta("Bag Series")
		size_field = None
		for fn in ("size_in_inches", "custom_size_in_inches", "size"):
			if meta.has_field(fn):
				size_field = fn
				break
		if not size_field:
			return result
		rows = frappe.get_all("Bag Series", fields=["name", size_field], limit_page_length=0) or []
		for r in rows:
			result[str(r.name).strip()] = str(r.get(size_field) or "").strip()
	except Exception:
		pass
	frappe.cache().set_value(cache_key, result, expires_in_sec=300)
	return result


def _force_box_bag_unit_on_sheet(planning_sheet_name=None):
	"""Ensure all 221-process rows on Planning Table have a box bag unit assigned.
	 Handles item codes: 221N..., 6000-221N..., 6000-511-221N... (any number of leading segments).
	"""
	if not frappe.db.has_column("Planning Table", "unit"):
		return
	# Match 221 or 224 process code safely (either starts with 221/224 or preceded by hyphen)
	conditions = """
		(item_code LIKE '221%%' OR item_code LIKE '%%-221%%' OR item_code LIKE '224%%' OR item_code LIKE '%%-224%%')
		AND (
			IFNULL(unit, '') NOT IN (%s, %s, %s)
			OR unit IN ('Unit 1', 'Unit 2', 'Unit 3', 'Unit 4', 'Mixed', 'UNASSIGNED')
		)
	"""
	params = list(BOX_BAG_UNITS)
	if planning_sheet_name:
		conditions += " AND parent = %s"
		params.append(planning_sheet_name)

	frappe.db.sql(
		f"""UPDATE `tabPlanning Table`
		SET unit = %s
		WHERE {conditions}
		""",
		[BOX_BAG_UNASSIGNED_UNIT] + params,
	)


def _force_dcut_unit_on_sheet(planning_sheet_name=None):
	"""Ensure all D-CUT parent rows have D-CUT default unit."""
	if not frappe.db.has_column("Planning Table", "unit"):
		return
	proc_like = " OR ".join([f"item_code LIKE '{p}%%' OR item_code LIKE '%%-{p}%%'" for p in D_CUT_PROCESS_CODES])
	placeholders = ", ".join(["%s"] * len(W_CUT_D_CUT_UNITS))
	conditions = f"""
		({proc_like})
		AND IFNULL(unit, '') NOT IN ({placeholders})
	"""
	params = list(W_CUT_D_CUT_UNITS)
	if planning_sheet_name:
		conditions += " AND parent = %s"
		params.append(planning_sheet_name)
	frappe.db.sql(
		f"""UPDATE `tabPlanning Table`
		SET unit = %s
		WHERE {conditions}
		""",
		[D_CUT_UNASSIGNED_UNIT] + params,
	)


def _force_wcut_unit_on_sheet(planning_sheet_name=None):
	"""Ensure all W-CUT parent rows (200–202) default to W-CUT unassigned unless on a valid machine."""
	if not frappe.db.has_column("Planning Table", "unit"):
		return
	proc_like = " OR ".join([f"item_code LIKE '{p}%%' OR item_code LIKE '%%-{p}%%'" for p in W_CUT_PROCESS_CODES])
	placeholders = ", ".join(["%s"] * len(W_CUT_D_CUT_UNITS))
	conditions = f"""
		({proc_like})
		AND IFNULL(unit, '') NOT IN ({placeholders})
	"""
	params = list(W_CUT_D_CUT_UNITS)
	if planning_sheet_name:
		conditions += " AND parent = %s"
		params.append(planning_sheet_name)
	frappe.db.sql(
		f"""UPDATE `tabPlanning Table`
		SET unit = %s
		WHERE {conditions}
		""",
		[W_CUT_UNASSIGNED_UNIT] + params,
	)


def _wcut_dcut_bag_field_updates_from_parsed(parsed, row, so_name=""):
	"""Build PT/PSI field updates from _parse_dcut_bag_item_code result."""
	updates = {}
	if not parsed:
		return updates
	total = flt(parsed.get("total_gsm") or 0)
	if total > 0:
		updates["gsm"] = int(total)
	quality_name = ""
	color_name = ""
	try:
		from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
			_quality_name_by_code,
			_color_name_by_code,
		)
		if parsed.get("quality_letter"):
			quality_name = _quality_name_by_code(parsed["quality_letter"]) or parsed["quality_letter"]
		if parsed.get("colour_code"):
			color_name = _color_name_by_code(parsed["colour_code"]) or parsed["colour_code"]
	except Exception:
		quality_name = parsed.get("quality_letter") or ""
		color_name = parsed.get("colour_code") or ""
	if parsed.get("lam_gsm"):
		updates["custom_lam_gsm"] = int(parsed.get("lam_gsm") or 0)
	if parsed.get("bopp_gsm"):
		updates["custom_bopp_gsm"] = int(parsed.get("bopp_gsm") or 0)
	if parsed.get("num_colors"):
		updates["custom_no_of_design_colours"] = f"{parsed['num_colors']}C"
	fin = parsed.get("finishing_label") or parsed.get("finishing_code")
	if fin:
		updates["custom_finishing"] = fin
		updates["finishing"] = fin
	if quality_name:
		updates["quality"] = quality_name
		updates["custom_quality"] = quality_name
	if color_name:
		updates["color"] = color_name
	if parsed.get("bag_size_id"):
		updates["bag_size"] = parsed["bag_size_id"]
	dc = parsed.get("design_code")
	if dc:
		updates["custom_design_code"] = dc
		try:
			from production_entry.production_planning.scheduler_api import (
				_design_master_extra_fields,
				_pb_design_name_from_sales_order_item,
				_printing_design_attachment_from_sales_order_item,
			)
			dm_info = _design_master_extra_fields(dc) or {}
			soi_name = str(row.get("sales_order_item") or row.get("so_item") or "").strip()
			design_name = dm_info.get("custom_design_name")
			design_attachment = dm_info.get("custom_design_attachment")
			if soi_name:
				if not design_name:
					design_name = _pb_design_name_from_sales_order_item(soi_name)
				if not design_attachment:
					design_attachment = _printing_design_attachment_from_sales_order_item(soi_name)
			if design_name:
				updates["custom_design_name"] = design_name
			if design_attachment:
				updates["custom_design_attachment"] = design_attachment
			if dm_info.get("custom_design_colour"):
				updates["custom_design_colour"] = dm_info["custom_design_colour"]
		except Exception:
			pass
	return updates


def _update_wcut_dcut_bag_fields_on_sheet(planning_sheet_name):
	"""Stamp GSM, finishing, design, bag size on W/D-CUT FG rows (Planning Table + Planning sheet Item)."""
	if not planning_sheet_name:
		return
	so_name = str(frappe.db.get_value("Planning sheet", planning_sheet_name, "sales_order") or "").strip()

	def _apply(doctype, table):
		if not frappe.db.exists("DocType", doctype):
			return
		rows = frappe.db.sql(
			f"""SELECT name, item_code, sales_order_item, so_item FROM `tab{table}`
			   WHERE parent = %s""",
			(planning_sheet_name,),
			as_dict=True,
		) or []
		for row in rows:
			parsed = _parse_dcut_bag_item_code(row.get("item_code") or "")
			if parsed.get("process") not in W_CUT_D_CUT_FG_PROCESS_CODES:
				continue
			updates = _wcut_dcut_bag_field_updates_from_parsed(parsed, row, so_name)
			if not updates:
				continue
			safe = {k: v for k, v in updates.items() if frappe.db.has_column(doctype, k)}
			if safe:
				frappe.db.set_value(doctype, row["name"], safe, update_modified=False)

	_apply("Planning Table", "Planning Table")
	_apply("Planning sheet Item", "Planning sheet Item")


def _sync_dcut_bopp_bag_planning_rows(planning_sheet_name):
	"""216/217 D-CUT BOPP: FG→107→100 + PB."""
	if not planning_sheet_name:
		return
	from production_entry.production_planning.scheduler_api import (
		_sync_bom_child_rows_from_planning_rows,
		LAMINATION_UNIT,
	)
	_dcut_bopp_parents = ("216", "217")
	_sync_bom_child_rows_from_planning_rows(
		planning_sheet_name,
		_dcut_bopp_parents,
		"107",
		LAMINATION_UNIT,
		process_label="216/217 D-CUT BOPP (FG → 107)",
	)
	_sync_bom_child_rows_from_planning_rows(
		planning_sheet_name,
		("107",),
		"100",
		so_parent_processes=_dcut_bopp_parents,
		process_label="216/217 D-CUT BOPP fabric (107 → 100)",
	)
	try:
		from production_entry.production_planning.bopp_bag_api import _sync_bopp_pb_rows_from_107_for_fg_parents
		_sync_bopp_pb_rows_from_107_for_fg_parents(planning_sheet_name, _dcut_bopp_parents)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "_sync_dcut_bopp_bag_planning_rows:pb")


@frappe.whitelist()
def get_box_bag_order_table_data(
	date=None,
	start_date=None,
	end_date=None,
	planned_only=1,
):
	"""Box Bag board rows (process 221) for Box Bag Order Table."""
	from production_entry.production_planning.scheduler_api import (
		_get_color_chart_data_impl,
		_item_process_prefix,
		_normalize_filter_date,
		_transfer_payload_for_chart_row,
		PLANNING_MOVEMENT_TYPE_FIELD,
	)

	# Ensure any unassigned 221 rows get a box bag unit
	try:
		_force_box_bag_unit_on_sheet()
	except Exception:
		pass

	raw = _get_color_chart_data_impl(
		date=date,
		start_date=start_date,
		end_date=end_date,
		plan_name="__all__",
		mode=None,
		planned_only=cint(planned_only),
		board_process_scope="box_bag_only",
	)

	# Hard safety filter: only process 221 and 224 (233 is handled by bopp_bag_api.py)
	raw = [
		r for r in (raw or [])
		if _item_process_prefix(str(r.get("item_code") or r.get("itemCode") or "")) in ("221", "224")
	]

	bag_sizes = _bag_series_size_map()

	out = []
	from production_entry.production_planning.bopp_bag_api import _parse_bopp_bag_item_code
	for row in raw:
		ic = str(row.get("item_code") or row.get("itemCode") or "").strip()
		proc_prefix = _item_process_prefix(ic)
		if proc_prefix == "233":
			parsed = _parse_bopp_bag_item_code(ic)
		else:
			parsed = _parse_box_bag_item_code(ic)
		item_name = str(row.get("item_name") or "").strip()
		planning_sheet = str(row.get("planningSheet") or row.get("planning_sheet") or row.get("parent") or "").strip()

		# Resolve quality and color names
		quality_name = ""
		color_name = ""
		try:
			from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
				_quality_name_by_code,
				_color_name_by_code,
			)
			if parsed["quality_letter"]:
				quality_name = _quality_name_by_code(parsed["quality_letter"]) or parsed["quality_letter"]
			if parsed["colour_code"]:
				color_name = _color_name_by_code(parsed["colour_code"]) or parsed["colour_code"]
		except Exception:
			quality_name = parsed["quality_letter"]
			color_name = parsed["colour_code"]

		# Bag size from Bag Series
		bag_size_id = parsed["bag_size_id"]
		bag_size_inches = bag_sizes.get(bag_size_id, "")

		# Design info — fetch from SO if available
		design_code = parsed["design_code"]
		design_name = ""
		so_name = ""
		if planning_sheet:
			try:
				so_name = str(frappe.db.get_value("Planning sheet", planning_sheet, "sales_order") or "").strip()
			except Exception:
				pass
		if design_code and so_name:
			try:
				so_doc = frappe.get_doc("Sales Order", so_name)
				for it in so_doc.items or []:
					sic = str(it.item_code or "").strip()
					if sic.startswith(design_code + "-"):
						design_name = str(it.item_name or "").strip()
						break
			except Exception:
				pass
		if not design_name:
			design_name = item_name

		# Shift label
		shift_label = "DAY"
		try:
			pt_name = str(row.get("itemName") or row.get("item_name") or "").strip()
			if pt_name:
				for sf in ("custom_box_bag_shift", "custom_sheet_cutting_shift", "custom_slitting_shift"):
					if frappe.db.has_column("Planning Table", sf):
						val = frappe.db.get_value("Planning Table", pt_name, sf)
						if val:
							shift_label = str(val).strip().upper()
							break
		except Exception:
			pass

		# Unit
		unit = str(row.get("unit") or "").strip()
		if unit not in BOX_BAG_UNITS:
			unit = BOX_BAG_UNASSIGNED_UNIT

		# Planned and achieved qty (PCS for box bag)
		planned_qty = flt(row.get("qty") or row.get("quantity") or 0)
		achieved_qty = flt(row.get("actual_production_weight_kgs") or row.get("produced_qty") or 0)
		spr_name = str(row.get("spr_name") or "").strip()
		achieved_bag_pcs = _spr_achieved_bag_pcs_total(spr_name)
		if achieved_bag_pcs > 0:
			achieved_qty = achieved_bag_pcs

		# Length from row data
		length = flt(row.get("length") or row.get("meter") or row.get("mtr") or row.get("planned_meter") or 0)

		# PP/WO/SPR data
		pp_id = str(row.get("pp_id") or row.get("production_plan") or "").strip()
		pp_docstatus = row.get("pp_docstatus") or 0
		wo_name = ""
		wo_open = False
		wo_terminal = False
		spr_name = str(row.get("spr_name") or "").strip()
		spr_docstatus = row.get("spr_docstatus") or 0
		total_achieved_meters = _spr_total_achieved_meters_from_bundle(spr_name)

		# Try to find WO
		if pp_id:
			try:
				wos = frappe.get_all(
					"Work Order",
					filters={"production_plan": pp_id, "docstatus": ["<", 2]},
					fields=["name", "status", "produced_qty", "qty"],
					order_by="creation desc",
					limit_page_length=5,
				) or []
				for w in wos:
					wo_name = w.name
					wo_status = str(w.get("status") or "").strip()
					wo_open = wo_status in ("Not Started", "In Process", "Open")
					wo_terminal = wo_status in ("Completed", "Stopped", "Cancelled")
					break
			except Exception:
				pass

		enriched = {
			"itemName": row.get("itemName") or row.get("item_name") or row.get("name") or "",
			"item_code": ic,
			"item_name": item_name,
			"planningSheet": planning_sheet,
			"plannedDate": row.get("plannedDate") or row.get("planned_date") or "",
			"partyCode": row.get("partyCode") or row.get("party_code") or row.get("order_code") or "",
			"customer": row.get("customer") or row.get("customer_name") or "",
			"customer_name": row.get("customer_name") or row.get("customer") or "",
			"unit": unit,
			"shift_label": shift_label,
			"design_code": design_code,
			"design_name": design_name,
			"bag_size_id": bag_size_id,
			"bag_size_inches": bag_size_inches,
			"quality": quality_name or row.get("quality") or row.get("custom_quality") or "",
			"color": color_name or row.get("color") or "",
			"colour_code": parsed["colour_code"],
			"fabric_gsm": parsed["fabric_gsm"],
			"gsm": parsed["total_gsm"],
			"lam_gsm": parsed["lam_gsm"],
			"bopp_gsm": parsed["bopp_gsm"],
			"finishing_code": parsed["finishing_code"],
			"finishing": parsed["finishing_label"] or parsed["finishing_code"],
			"length": length,
			"planned_quantity": planned_qty,
			"achieved_quantity": achieved_qty,
			"planned_bag_pcs": planned_qty,
			"achieved_bag_pcs": achieved_qty,
			"total_achieved_meters": total_achieved_meters,
			"per_day_production": flt(row.get("per_day_production") or 0),
			"pp_id": pp_id,
			"pp_docstatus": pp_docstatus,
			"wo_name": wo_name,
			"wo_open": wo_open,
			"wo_terminal": wo_terminal,
			"spr_name": spr_name,
			"spr_docstatus": spr_docstatus,
			"salesOrderItem": row.get("salesOrderItem") or row.get("sales_order_item") or "",
			"process": "233" if proc_prefix == "233" else ("224" if proc_prefix == "224" else "221"),
			"process_label": (
				"233 BOPP Box Bag"
				if proc_prefix == "233"
				else ("224 PLAIN LAMINATED BOX BAG" if proc_prefix == "224" else "221 Box Bag")
			),
			"movement_type": row.get(PLANNING_MOVEMENT_TYPE_FIELD) or row.get("movement_type") or "",
		}

		# Transfer payload
		try:
			transfer_data = _transfer_payload_for_chart_row(row, wo_terminal, spr_docstatus)
			enriched.update(transfer_data)
		except Exception:
			pass

		out.append(enriched)

	return out


@frappe.whitelist()
def get_w_cut_d_cut_order_table_data(
	date=None,
	start_date=None,
	end_date=None,
	planned_only=1,
):
	"""W CUT / D CUT table rows (211–213, 217, 200–202)."""
	from production_entry.production_planning.scheduler_api import (
		_get_color_chart_data_impl,
		_item_process_prefix,
		_transfer_payload_for_chart_row,
		PLANNING_MOVEMENT_TYPE_FIELD,
	)

	try:
		_force_dcut_unit_on_sheet()
		_force_wcut_unit_on_sheet()
	except Exception:
		pass

	raw = _get_color_chart_data_impl(
		date=date,
		start_date=start_date,
		end_date=end_date,
		plan_name="__all__",
		mode=None,
		planned_only=cint(planned_only),
		board_process_scope="w_cut_d_cut_only",
	)
	raw = [
		r for r in (raw or [])
		if _item_process_prefix(str(r.get("item_code") or r.get("itemCode") or "")) in W_CUT_D_CUT_FG_PROCESS_CODES
	]
	bag_sizes = _bag_series_size_map()
	out = []
	for row in raw:
		ic = str(row.get("item_code") or row.get("itemCode") or "").strip()
		parsed = _parse_dcut_bag_item_code(ic)
		prefix = _item_process_prefix(ic)
		shift_label = "DAY"
		try:
			pt_name = str(row.get("itemName") or row.get("item_name") or "").strip()
			if pt_name:
				for sf in ("custom_box_bag_shift", "custom_sheet_cutting_shift", "custom_slitting_shift"):
					if frappe.db.has_column("Planning Table", sf):
						val = frappe.db.get_value("Planning Table", pt_name, sf)
						if val:
							shift_label = str(val).strip().upper()
							break
		except Exception:
			pass
		unit = str(row.get("unit") or "").strip()
		if unit not in W_CUT_D_CUT_UNITS:
			unit = W_CUT_UNASSIGNED_UNIT if prefix in W_CUT_PROCESS_CODES else D_CUT_UNASSIGNED_UNIT
		planned_qty = flt(row.get("qty") or row.get("quantity") or 0)
		achieved_qty = flt(row.get("actual_production_weight_kgs") or row.get("produced_qty") or 0)
		spr_name = str(row.get("spr_name") or "").strip()
		achieved_bag_pcs = _spr_achieved_bag_pcs_total(spr_name)
		if achieved_bag_pcs > 0:
			achieved_qty = achieved_bag_pcs
		length = flt(row.get("length") or row.get("meter") or row.get("mtr") or row.get("planned_meter") or 0)
		pp_id = str(row.get("pp_id") or row.get("production_plan") or "").strip()
		pp_docstatus = row.get("pp_docstatus") or 0
		spr_name = str(row.get("spr_name") or "").strip()
		total_achieved_meters = _spr_total_achieved_meters_from_bundle(spr_name)
		wo_name = ""
		wo_open = False
		wo_terminal = False
		if pp_id:
			try:
				wos = frappe.get_all(
					"Work Order",
					filters={"production_plan": pp_id, "docstatus": ["<", 2]},
					fields=["name", "status"],
					order_by="creation desc",
					limit_page_length=5,
				) or []
				for w in wos:
					wo_name = w.name
					wo_status = str(w.get("status") or "").strip()
					wo_open = wo_status in ("Not Started", "In Process", "Open")
					wo_terminal = wo_status in ("Completed", "Stopped", "Cancelled")
					break
			except Exception:
				pass
		enriched = {
			"itemName": row.get("itemName") or row.get("item_name") or row.get("name") or "",
			"item_code": ic,
			"item_name": row.get("item_name") or "",
			"planningSheet": str(row.get("planningSheet") or row.get("planning_sheet") or row.get("parent") or "").strip(),
			"plannedDate": row.get("plannedDate") or row.get("planned_date") or "",
			"partyCode": row.get("partyCode") or row.get("party_code") or row.get("order_code") or "",
			"customer": row.get("customer") or row.get("customer_name") or "",
			"customer_name": row.get("customer_name") or row.get("customer") or "",
			"unit": unit,
			"shift_label": shift_label,
			"design_code": parsed.get("design_code") or "",
			"design_name": row.get("item_name") or "",
			"bag_size_id": parsed.get("bag_size_id") or "",
			"bag_size_inches": bag_sizes.get(parsed.get("bag_size_id") or "", ""),
			"quality": parsed.get("quality_letter") or "",
			"color": parsed.get("colour_code") or "",
			"colour_code": parsed.get("colour_code") or "",
			"num_colors": parsed.get("num_colors") or "",
			"fabric_gsm": parsed.get("fabric_gsm") or 0,
			"gsm": parsed.get("total_gsm") or 0,
			"lam_gsm": parsed.get("lam_gsm") or 0,
			"bopp_gsm": parsed.get("bopp_gsm") or 0,
			"total_gsm": parsed.get("total_gsm") or 0,
			"finishing_code": parsed.get("finishing_code") or "",
			"finishing": parsed.get("finishing_label") or parsed.get("finishing_code") or "",
			"length": length,
			"planned_quantity": planned_qty,
			"achieved_quantity": achieved_qty,
			"planned_bag_pcs": planned_qty,
			"achieved_bag_pcs": achieved_qty,
			"total_achieved_meters": total_achieved_meters,
			"per_day_production": flt(row.get("per_day_production") or 0),
			"pp_id": pp_id,
			"pp_docstatus": pp_docstatus,
			"wo_name": wo_name,
			"wo_open": wo_open,
			"wo_terminal": wo_terminal,
			"spr_name": spr_name,
			"spr_docstatus": row.get("spr_docstatus") or 0,
			"salesOrderItem": row.get("salesOrderItem") or row.get("sales_order_item") or "",
			"process": prefix,
			"process_label": _wcut_dcut_process_label(prefix),
			"movement_type": row.get(PLANNING_MOVEMENT_TYPE_FIELD) or row.get("movement_type") or "",
		}
		try:
			transfer_data = _transfer_payload_for_chart_row(row, False, enriched["spr_docstatus"])
			enriched.update(transfer_data)
		except Exception:
			pass
		out.append(enriched)
	return out


@frappe.whitelist()
def assign_box_bag_shift(shift_date=None, shift_label="DAY", item_name=None):
	"""Assign DAY/NIGHT shift for box bag (221) rows on the Planning Table."""
	from production_entry.production_planning.scheduler_api import (
		_normalize_filter_date,
		is_date_under_maintenance,
	)

	shift_label = str(shift_label or "DAY").strip().upper()
	if shift_label not in ("DAY", "NIGHT"):
		shift_label = "DAY"

	shift_field = None
	for sf in ("custom_box_bag_shift", "custom_sheet_cutting_shift", "custom_slitting_shift"):
		if frappe.db.has_column("Planning Table", sf):
			shift_field = sf
			break
	if not shift_field:
		return {"status": "error", "message": "No shift column found on Planning Table"}

	if item_name:
		item_name = str(item_name).strip()
		if frappe.db.exists("Planning Table", item_name):
			frappe.db.set_value("Planning Table", item_name, shift_field, shift_label, update_modified=False)
			frappe.db.commit()
			return {"status": "success", "updated": 1}
		return {"status": "error", "message": f"Planning Table row {item_name} not found"}

	# Bulk: assign all 221 rows on a given date
	sd = _normalize_filter_date(shift_date)
	if not sd:
		return {"status": "error", "message": "No shift_date provided"}

	# Check maintenance
	for u in BOX_BAG_UNITS:
		try:
			if is_date_under_maintenance(u, sd):
				return {"status": "error", "message": f"{u} is under maintenance on {sd}"}
		except Exception:
			pass

	items = get_box_bag_order_table_data(date=sd, planned_only=1)
	updated = 0
	for it in items:
		it_name = it.get("itemName")
		if it_name:
			frappe.db.set_value("Planning Table", it_name, shift_field, shift_label, update_modified=False)
			updated += 1

	frappe.db.commit()
	return {"status": "success", "updated": updated}
