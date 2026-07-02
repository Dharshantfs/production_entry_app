"""GSM Production Entry — additive APIs only. Does not modify Production Table core."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from production_entry.production_planning.doctype.shaft_production_run.shaft_production_run import (
	_cstr,
	_count_combination_segments,
	_parse_combination_widths_inches,
	_resolve_wos_for_pp_job_row,
	_spr_count_roll_lines_for_job,
	_spr_job_max_roll_lines,
	_spr_job_rows,
	parse_item_code,
)
from production_entry.production_planning.scheduler_api import create_item_spr, get_current_shift


def _pick_value(row, keys, default=None):
	if not row:
		return default
	if isinstance(row, dict):
		getter = row.get
	else:
		getter = lambda k, d=None: getattr(row, k, d)
	for k in keys:
		v = getter(k, None)
		if v is not None and str(v).strip() != "":
			return v
	return default


def _meter_keys():
	return [
		"meter__roll",
		"meter_roll_mtrs",
		"meter_per_roll",
		"meter_roll",
		"roll_mtrs",
		"custom_meter_roll_mtrs",
		"custom_meter_per_roll",
		"custom_meterperroll",
		"meter_per_roll_mtrs",
		"roll",
		"meter",
		"length_per_roll",
		"length_roll",
		"length",
		"planned_length",
	]


def _shaft_width_inch(shaft_row) -> float:
	w = flt(_pick_value(shaft_row, ["total_width", "combined_width", "width", "total_width_inches"], 0))
	if w > 0:
		return w
	comb = _cstr(_pick_value(shaft_row, ["combination", "combined_width", "shaft", "shaft_details"], ""))
	if comb and "+" not in comb:
		try:
			return flt(comb)
		except Exception:
			pass
	widths = _parse_combination_widths_inches(comb) if comb else []
	return flt(widths[0]) if widths else 0.0


def _shaft_gsm(shaft_row) -> int:
	try:
		return int(flt(_pick_value(shaft_row, ["gsm"], 0)))
	except Exception:
		return 0


def _find_spr_for_pp(pp_id: str, prefer_draft: bool = True) -> str | None:
	if not pp_id:
		return None
	sprs = frappe.get_all(
		"Shaft Production Run",
		filters={"production_plan": pp_id, "docstatus": ["<", 2]},
		fields=["name", "docstatus"],
		order_by="modified desc",
		limit=20,
	)
	if not sprs:
		return None
	if prefer_draft:
		for row in sprs:
			if cint(row.docstatus) == 0:
				return row.name
	return sprs[0].name


def _match_shaft_job_for_line(spr_doc, pp_id: str, gsm=None, width_inch=None, production_plan_item=None):
	target_gsm = cint(gsm) if gsm is not None else 0
	target_w = flt(width_inch) if width_inch is not None else 0.0
	ppi = _cstr(production_plan_item).strip()

	for sj in _spr_job_rows(spr_doc):
		if ppi and _cstr(getattr(sj, "production_plan_item", None)) == ppi:
			return sj
		jg = cint(getattr(sj, "gsm", 0) or 0)
		if target_gsm and jg and jg != target_gsm:
			continue
		comb = _cstr(getattr(sj, "combination", None))
		if target_w > 0:
			widths = _parse_combination_widths_inches(comb) if comb else []
			if widths:
				if any(abs(flt(w) - target_w) < 0.05 for w in widths):
					return sj
			elif abs(_shaft_width_inch(sj) - target_w) < 0.05:
				return sj
			elif comb and abs(flt(comb) - target_w) < 0.05:
				return sj

	if pp_id and target_gsm and target_w > 0:
		pp = frappe.get_doc("Production Plan", pp_id)
		pp_shafts = pp.get("custom_shaft_details") or pp.get("shaft_details") or []
		for idx, shaft in enumerate(pp_shafts, start=1):
			if target_gsm and _shaft_gsm(shaft) != target_gsm:
				continue
			if abs(_shaft_width_inch(shaft) - target_w) >= 0.05:
				comb = _cstr(_pick_value(shaft, ["combination", "combined_width", "shaft", "shaft_details"], ""))
				widths = _parse_combination_widths_inches(comb) if comb else []
				if not any(abs(flt(w) - target_w) < 0.05 for w in widths):
					continue
			for sj in _spr_job_rows(spr_doc):
				jid = _cstr(getattr(sj, "job_id", None) or getattr(sj, "job_no", None))
				if jid == str(idx):
					return sj
	return None


@frappe.whitelist()
def get_gsm_current_shift():
	return get_current_shift()


@frappe.whitelist()
def preview_spr_batch_numbers_for_entry(
	unit,
	run_date,
	shift,
	count=1,
	client_max_roll=None,
	client_series_prefix=None,
	existing_batches=None,
):
	"""Read-only batch/roll preview for GSM Production Entry (no SPR document required)."""
	count = cint(count)
	if count < 1:
		return []
	unit = _cstr(unit).strip()
	shift = _cstr(shift).strip()
	if not unit or not run_date or not shift:
		frappe.throw(_("Set Run Date, Unit, and Shift to preview batch numbers."))

	doc = frappe.new_doc("Shaft Production Run")
	doc.run_date = run_date
	doc.custom_unit = unit
	doc.shift = shift

	existing = []
	if existing_batches:
		if isinstance(existing_batches, str):
			try:
				existing = json.loads(existing_batches) or []
			except Exception:
				existing = [x.strip() for x in existing_batches.split(",") if x.strip()]
		elif isinstance(existing_batches, (list, tuple)):
			existing = list(existing_batches)

	for bn in existing:
		bn = _cstr(bn).strip()
		if bn:
			row = doc.append("items", {})
			row.batch_no = bn

	rd = getdate(run_date)
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

	used_batches = set(existing)
	out = []
	for _i in range(count):
		while f"{series_prefix}/{next_roll}" in used_batches:
			next_roll += 1
		bn = f"{series_prefix}/{next_roll}"
		used_batches.add(bn)
		out.append({"batch_no": bn, "roll_no": next_roll, "series_prefix": series_prefix})
		next_roll += 1
	return out


@frappe.whitelist()
def get_order_length_for_pt_line(pp_id, gsm=None, width_inch=None, item_code=None, production_plan_item=None):
	"""Order length (meters per roll) from PP shaft details for a GSM+width line."""
	pp_id = _cstr(pp_id).strip()
	if not pp_id or not frappe.db.exists("Production Plan", pp_id):
		frappe.throw(_("Production Plan not found"))
	target_gsm = cint(gsm) if gsm is not None else 0
	target_w = flt(width_inch) if width_inch is not None else 0.0
	item_code = _cstr(item_code).strip()

	pp = frappe.get_doc("Production Plan", pp_id)
	pp_shafts = pp.get("custom_shaft_details") or pp.get("shaft_details") or []
	meter_keys = _meter_keys()

	for shaft in pp_shafts:
		sg = _shaft_gsm(shaft)
		sw = _shaft_width_inch(shaft)
		if target_gsm and sg and sg != target_gsm:
			continue
		if target_w > 0:
			comb = _cstr(_pick_value(shaft, ["combination", "combined_width", "shaft", "shaft_details"], ""))
			widths = _parse_combination_widths_inches(comb) if comb else []
			width_match = abs(sw - target_w) < 0.05
			if widths and not width_match:
				width_match = any(abs(flt(w) - target_w) < 0.05 for w in widths)
			if not width_match:
				continue
		raw_meter = flt(_pick_value(shaft, meter_keys, 0))
		if raw_meter > 0:
			return {"meter_roll_mtrs": raw_meter, "source": "shaft_details"}

	if production_plan_item:
		for row in pp.get("po_items") or []:
			if _cstr(getattr(row, "name", None)) != _cstr(production_plan_item):
				continue
			raw_meter = flt(_pick_value(row, meter_keys, 0))
			if raw_meter > 0:
				return {"meter_roll_mtrs": raw_meter, "source": "po_item"}

	if item_code:
		try:
			g, w = parse_item_code(item_code)
			if not target_gsm and g:
				target_gsm = int(g)
			if not target_w and w:
				target_w = flt(w)
		except Exception:
			pass

	for psi_name in frappe.get_all(
		"Planning Table",
		filters={"production_plan": pp_id} if frappe.db.has_column("Planning Table", "production_plan") else {},
		fields=["name", "meter", "meter_roll", "planned_length"],
		limit=50,
	):
		raw_meter = flt(_pick_value(psi_name, meter_keys, 0))
		if raw_meter > 0:
			return {"meter_roll_mtrs": raw_meter, "source": "planning_table"}

	fallback = flt(
		pp.get("meter__roll")
		or pp.get("custom_meter_roll_mtrs")
		or pp.get("meter_roll_mtrs")
		or pp.get("custom_meter_per_roll")
		or pp.get("meter")
		or 0
	)
	return {"meter_roll_mtrs": fallback or 0, "source": "pp_fallback"}


@frappe.whitelist()
def resolve_work_order_for_roll_line(pp_id, gsm=None, width_inch=None, item_code=None, production_plan_item=None):
	"""Resolve primary Work Order name for a GSM+width roll line."""
	pp_id = _cstr(pp_id).strip()
	if not pp_id:
		return {"work_order": "", "work_orders": []}
	job_gsm = cint(gsm) if gsm is not None else None
	if not job_gsm and item_code:
		try:
			g, _w = parse_item_code(_cstr(item_code))
			if g > 0:
				job_gsm = int(g)
		except Exception:
			pass
	ppi = _cstr(production_plan_item).strip() or None
	wos = _resolve_wos_for_pp_job_row(
		pp_id,
		ppi=ppi,
		job_gsm=job_gsm,
		combination=_cstr(width_inch) if flt(width_inch) > 0 else None,
	)
	names = [_cstr(w.get("name")) for w in (wos or []) if w.get("name")]
	return {"work_order": names[0] if names else "", "work_orders": names}


@frappe.whitelist()
def get_pt_line_roll_quota_status(pp_id, production_plan_item=None, gsm=None, width_inch=None, item_code=None):
	"""Roll line quota for one PP line / GSM+width (SPR Create Entry limit)."""
	pp_id = _cstr(pp_id).strip()
	if not pp_id:
		return {
			"max_rolls": 0,
			"current_rolls": 0,
			"can_add_roll": False,
			"spr_name": "",
			"job_id": "",
		}

	spr_name = _find_spr_for_pp(pp_id, prefer_draft=True) or ""
	max_rolls = 0
	current_rolls = 0
	job_id = ""

	if spr_name:
		spr = frappe.get_doc("Shaft Production Run", spr_name)
		job_row = _match_shaft_job_for_line(
			spr,
			pp_id,
			gsm=gsm,
			width_inch=width_inch,
			production_plan_item=production_plan_item,
		)
		if job_row:
			job_id = _cstr(getattr(job_row, "job_id", None) or getattr(job_row, "job_no", None))
			max_rolls = cint(_spr_job_max_roll_lines(job_row, spr))
			current_rolls = cint(_spr_count_roll_lines_for_job(spr, job_id))
	else:
		pp = frappe.get_doc("Production Plan", pp_id)
		pp_shafts = pp.get("custom_shaft_details") or pp.get("shaft_details") or []
		target_gsm = cint(gsm) if gsm is not None else 0
		target_w = flt(width_inch) if width_inch is not None else 0.0
		for idx, shaft in enumerate(pp_shafts, start=1):
			if target_gsm and _shaft_gsm(shaft) != target_gsm:
				continue
			sw = _shaft_width_inch(shaft)
			comb = _cstr(_pick_value(shaft, ["combination", "combined_width", "shaft", "shaft_details"], ""))
			widths = _parse_combination_widths_inches(comb) if comb else []
			width_match = target_w <= 0 or abs(sw - target_w) < 0.05
			if widths and not width_match:
				width_match = any(abs(flt(w) - target_w) < 0.05 for w in widths)
			if not width_match:
				continue
			no_shafts = max(1, cint(_pick_value(shaft, ["no_of_shafts", "no_of_shaft", "no_of_sh"], 1)))
			rolls_per = max(1, cint(_pick_value(shaft, ["no_of_rolls", "rolls_per_shaft"], 1)))
			segs = max(1, _count_combination_segments(comb) if comb else 1)
			if segs <= 1:
				max_rolls = no_shafts * rolls_per
			else:
				max_rolls = no_shafts * segs * rolls_per
			job_id = str(idx)
			break

	can_add = max_rolls <= 0 or current_rolls < max_rolls
	return {
		"max_rolls": max_rolls,
		"current_rolls": current_rolls,
		"can_add_roll": can_add,
		"spr_name": spr_name,
		"job_id": job_id,
	}


@frappe.whitelist()
def ensure_draft_spr_for_pp(pp_id, planning_sheet_item_names, unit=None, run_date=None, shift=None):
	"""Return draft SPR for PP; create via create_item_spr when missing."""
	pp_id = _cstr(pp_id).strip()
	if isinstance(planning_sheet_item_names, str):
		try:
			planning_sheet_item_names = json.loads(planning_sheet_item_names)
		except Exception:
			planning_sheet_item_names = [
				x.strip() for x in planning_sheet_item_names.split(",") if x.strip()
			]
	if not planning_sheet_item_names:
		frappe.throw(_("Planning Table row name(s) required"))

	existing = _find_spr_for_pp(pp_id, prefer_draft=True)
	if existing:
		return {"status": "ok", "spr_name": existing, "reused": 1}

	result = create_item_spr(pp_id, planning_sheet_item_names)
	if isinstance(result, dict):
		if result.get("status") == "ok" and result.get("spr_id"):
			spr_name = result["spr_id"]
			if unit and run_date and shift and frappe.db.exists("Shaft Production Run", spr_name):
				spr = frappe.get_doc("Shaft Production Run", spr_name)
				changed = False
				if unit and _cstr(spr.get("custom_unit")) != _cstr(unit):
					spr.custom_unit = unit
					changed = True
				if run_date and str(spr.get("run_date") or "") != str(run_date):
					spr.run_date = run_date
					changed = True
				if shift and _cstr(spr.get("shift")) != _cstr(shift):
					spr.shift = shift
					changed = True
				if changed:
					spr.save(ignore_permissions=True)
			return {
				"status": "ok",
				"spr_name": spr_name,
				"reused": cint(result.get("reused") or 0),
				"message": result.get("message") or "",
			}
		return result
	if result:
		return {"status": "ok", "spr_name": _cstr(result), "reused": 0}
	return {"status": "error", "message": _("Could not create SPR")}


@frappe.whitelist()
def get_gsm_shift_submitted_entries(run_date, shift, unit=None):
	"""Submitted SPRs for a shift — GSM admin Shift Entries tab."""
	run_date = getdate(run_date)
	shift = _cstr(shift).strip()
	filters = {"docstatus": 1, "run_date": run_date}
	if shift:
		filters["shift"] = shift
	if unit:
		filters["custom_unit"] = unit

	sprs = frappe.get_all(
		"Shaft Production Run",
		filters=filters,
		fields=[
			"name",
			"production_plan",
			"run_date",
			"shift",
			"custom_unit",
			"operator",
			"supervisor",
			"modified",
		],
		order_by="modified desc",
		limit=100,
	)
	out = []
	for row in sprs:
		spr = frappe.get_doc("Shaft Production Run", row.name)
		rolls = spr.get("items") or []
		total_net = sum(flt(getattr(it, "net_weight", 0)) for it in rolls)
		total_gross = sum(flt(getattr(it, "gross_weight", 0)) for it in rolls)
		order_codes = set()
		for it in rolls:
			oc = _cstr(getattr(it, "party_code", None) or getattr(it, "custom_order_code", None))
			if oc:
				order_codes.add(oc)
		wo_status = []
		for sj in _spr_job_rows(spr):
			wos_raw = _cstr(getattr(sj, "work_orders", None) or getattr(sj, "work_order", None))
			for part in wos_raw.replace("\n", ",").split(","):
				wn = part.strip()
				if not wn:
					continue
				st = frappe.db.get_value("Work Order", wn, "status") or ""
				wo_status.append({"name": wn, "status": st})
		roll_rows = []
		for it in rolls:
			roll_rows.append(
				{
					"batch_no": _cstr(getattr(it, "batch_no", None)),
					"gsm": getattr(it, "gsm", None) or getattr(it, "custom_fabric_gsm", None),
					"width_inch": getattr(it, "width_inch", None) or getattr(it, "custom_width_inch", None),
					"net_weight": flt(getattr(it, "net_weight", 0)),
					"gross_weight": flt(getattr(it, "gross_weight", 0)),
					"party_code": _cstr(getattr(it, "party_code", None)),
					"work_order": _cstr(getattr(it, "work_order", None)),
				}
			)
		out.append(
			{
				"spr_name": row.name,
				"production_plan": row.production_plan,
				"run_date": str(row.run_date),
				"shift": row.shift,
				"unit": row.custom_unit,
				"operator": row.operator,
				"supervisor": row.supervisor,
				"roll_count": len(rolls),
				"total_net_kg": round(total_net, 2),
				"total_gross_kg": round(total_gross, 2),
				"order_codes": sorted(order_codes),
				"wo_status": wo_status,
				"rolls": roll_rows,
			}
		)
	return out
