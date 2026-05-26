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
)

BOX_BAG_UNITS = (BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L2, BOX_BAG_UNASSIGNED_UNIT)

_BOX_BAG_FINISHING_MAP = {
	"PP": "Plain",
	"MM": "Metallic / Matte",
	"MG": "Metallic / Glossy",
	"CM": "Cooler / Matte",
	"CG": "Cooler / Glossy",
	"PM": "Plain / Matte",
	"PG": "Plain / Glossy",
}


def _box_bag_finishing_label(code):
	"""Decode 2-char finishing suffix to human label."""
	return _BOX_BAG_FINISHING_MAP.get(str(code or "").strip().upper(), str(code or "").strip())


def _parse_box_bag_item_code(item_code):
	"""Parse box bag item code: DESIGN-BAGSIZE-221QCCCGLLBB
	Format: 6000-511-221N101Q00PP
	  - 6000   = design code (before first hyphen)
	  - 511    = bag size id (between first and second hyphen, from Bag Series)
	  - 221    = process code
	  - N      = quality letter (1 char, from Quality Master)
	  - 101    = colour code (3 digits)
	  - Q      = fabric GSM encoded (single char)
	  - 0      = lam_gsm digit
	  - 0      = bopp_gsm digit
	  - PP     = finishing code (2 chars)
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

	# Find "221" in the tail
	idx221 = tail.find("221")
	if idx221 < 0:
		return result

	after = tail[idx221 + 3:]  # e.g. N101Q00PP
	if len(after) >= 1:
		result["quality_letter"] = after[0]
	if len(after) >= 4:
		result["colour_code"] = after[1:4]
	if len(after) >= 5:
		# The GSM char — try numeric interpretation
		gsm_char = after[4]
		try:
			if gsm_char.isdigit():
				result["fabric_gsm"] = int(gsm_char) * 10
			else:
				# Letter encoding: A=10, B=20, ... or the char represents a range
				result["fabric_gsm"] = (ord(gsm_char.upper()) - ord('A') + 1) * 10
		except Exception:
			pass
	if len(after) >= 6:
		try:
			result["lam_gsm"] = int(after[5]) * 10
		except Exception:
			pass
	if len(after) >= 7:
		try:
			result["bopp_gsm"] = int(after[6]) * 10
		except Exception:
			pass
	if len(after) >= 9:
		result["finishing_code"] = after[7:9].upper()
		result["finishing_label"] = _box_bag_finishing_label(after[7:9])
	elif len(after) > 7:
		result["finishing_code"] = after[7:].upper()
		result["finishing_label"] = _box_bag_finishing_label(after[7:])

	return result


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
	# Match 221 anywhere in item_code — covers all segment patterns
	conditions = """
		item_code LIKE '%%221%%'
		AND IFNULL(unit, '') NOT IN (%s, %s, %s)
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

	# Hard safety filter: only process 221
	raw = [
		r for r in (raw or [])
		if _item_process_prefix(str(r.get("item_code") or r.get("itemCode") or "")) == "221"
	]

	bag_sizes = _bag_series_size_map()

	out = []
	for row in raw:
		ic = str(row.get("item_code") or row.get("itemCode") or "").strip()
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
			pt_name = str(row.get("name") or "").strip()
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

		# Length from row data
		length = flt(row.get("meter") or row.get("mtr") or 0)

		# PP/WO/SPR data
		pp_id = str(row.get("pp_id") or row.get("production_plan") or "").strip()
		pp_docstatus = row.get("pp_docstatus") or 0
		wo_name = ""
		wo_open = False
		wo_terminal = False
		spr_name = str(row.get("spr_name") or "").strip()
		spr_docstatus = row.get("spr_docstatus") or 0

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
			"gsm": parsed["fabric_gsm"],
			"lam_gsm": parsed["lam_gsm"],
			"bopp_gsm": parsed["bopp_gsm"],
			"finishing_code": parsed["finishing_code"],
			"finishing": parsed["finishing_label"] or parsed["finishing_code"],
			"length": length,
			"planned_quantity": planned_qty,
			"achieved_quantity": achieved_qty,
			"per_day_production": flt(row.get("per_day_production") or 0),
			"pp_id": pp_id,
			"pp_docstatus": pp_docstatus,
			"wo_name": wo_name,
			"wo_open": wo_open,
			"wo_terminal": wo_terminal,
			"spr_name": spr_name,
			"spr_docstatus": spr_docstatus,
			"salesOrderItem": row.get("salesOrderItem") or row.get("sales_order_item") or "",
			"process": "221",
			"process_label": "221 Box Bag",
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

	box_bag_like = "%-221%"
	frappe.db.sql(
		f"""
		UPDATE `tabPlanning Table`
		SET `{shift_field}` = %s
		WHERE IFNULL(planned_date, '') = %s
		  AND (
			item_code LIKE '221%%'
			OR item_code LIKE %s
		  )
		""",
		(shift_label, sd, box_bag_like),
	)
	frappe.db.commit()
	return {"status": "success"}
