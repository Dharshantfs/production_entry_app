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
	_segment_weights_kg,
	_spr_count_roll_lines_for_job,
	_spr_job_max_roll_lines,
	_spr_job_rows,
	_spr_net_kg_per_shaft_for_pp_line_width,
	compute_mix_roll_planned_qty_kg,
	delete_gsm_roll_line_from_spr,
	import_gsm_roll_lines_to_spr,
	parse_item_code,
	resolve_label_from_pp_doc,
	save_gsm_roll_line_to_spr,
	spr_get_tolerance_violations,
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


def _find_draft_spr_for_pp(pp_id: str) -> str | None:
	"""Return draft (docstatus=0) SPR for PP, or None."""
	if not pp_id:
		return None
	row = frappe.db.get_value(
		"Shaft Production Run",
		{"production_plan": pp_id, "docstatus": 0},
		"name",
		order_by="modified desc",
	)
	return _cstr(row).strip() or None


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
		return None
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
	session_local=None,
):
	"""Read-only batch/roll preview for GSM Production Entry (no SPR document required).

	When session_local=1, roll suffix is based only on existing_batches + client_max_roll
	(not global DB max) so unsaved GSM grid rows start at /1 and removed rows do not skip numbers.
	"""
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
	fresh_prefix = doc._resolve_series_prefix(root_5)
	csp = _cstr(client_series_prefix).strip()
	if csp and csp.startswith(root_5) and csp == fresh_prefix:
		series_prefix = csp
	else:
		series_prefix = fresh_prefix

	next_roll = doc._next_roll_starting(series_prefix)
	if cint(session_local):
		mx = 0
		for row in doc.items or []:
			bn = _cstr(getattr(row, "batch_no", "")).strip()
			if bn:
				mx = max(mx, doc._roll_no_from_batch(bn, series_prefix))
		try:
			if client_max_roll is not None and cint(client_max_roll) >= 0:
				mx = max(mx, cint(client_max_roll))
		except Exception:
			pass
		next_roll = (mx + 1) if mx > 0 else 1
	else:
		try:
			if client_max_roll is not None and cint(client_max_roll) >= 0 and csp == series_prefix:
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
def get_spr_for_pp(pp_id, prefer_draft=1):
	"""Read-only: return existing SPR for PP (never creates)."""
	pp_id = _cstr(pp_id).strip()
	if not pp_id:
		return {"spr_name": ""}
	name = _find_spr_for_pp(pp_id, prefer_draft=cint(prefer_draft) != 0)
	return {"spr_name": name or ""}


@frappe.whitelist()
def get_pt_line_roll_quota_status(
	pp_id,
	production_plan_item=None,
	gsm=None,
	width_inch=None,
	item_code=None,
	run_date=None,
	shift=None,
	unit=None,
):
	"""Roll line quota for one PP line / GSM+width.

	When run_date is set: current_rolls = this shift only; shift_max_rolls = job max minus
	rolls already recorded on other shifts the same day (e.g. Night 0/67 after Day 100/167).
	"""
	pp_id = _cstr(pp_id).strip()
	if not pp_id:
		return {
			"max_rolls": 0,
			"current_rolls": 0,
			"shift_max_rolls": 0,
			"day_rolls_total": 0,
			"other_shifts_rolls": 0,
			"prior_shifts": [],
			"can_add_roll": False,
			"spr_name": "",
			"job_id": "",
		}

	max_rolls = 0
	current_rolls = 0
	job_id = ""
	spr_name = ""

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

	if run_date:
		run_d = getdate(run_date)
		cur_shift = _cstr(shift).strip() if shift else ""
		spr_filters = {
			"production_plan": pp_id,
			"docstatus": ["<", 2],
			"run_date": run_d,
		}
		if unit:
			spr_filters["custom_unit"] = _cstr(unit).strip()
		sprs = frappe.get_all(
			"Shaft Production Run",
			filters=spr_filters,
			fields=["name", "shift"],
			order_by="modified desc",
			limit=50,
		)
		day_rolls_total = 0
		shift_rolls = 0
		prior_by_shift = {}
		for spr_row in sprs:
			spr = frappe.get_doc("Shaft Production Run", spr_row.name)
			job_row = _match_shaft_job_for_line(
				spr,
				pp_id,
				gsm=gsm,
				width_inch=width_inch,
				production_plan_item=production_plan_item,
			)
			if not job_row:
				continue
			jid = _cstr(getattr(job_row, "job_id", None) or getattr(job_row, "job_no", None))
			if not job_id:
				job_id = jid
			mx = cint(_spr_job_max_roll_lines(job_row, spr))
			if mx > 0:
				max_rolls = max(max_rolls, mx)
			cnt = cint(_spr_count_roll_lines_for_job(spr, jid))
			if cnt <= 0:
				continue
			if not spr_name:
				spr_name = spr_row.name
			day_rolls_total += cnt
			spr_shift = _cstr(getattr(spr, "shift", None) or spr_row.get("shift") or "").strip()
			if cur_shift and spr_shift == cur_shift:
				shift_rolls += cnt
			elif spr_shift:
				prior_by_shift[spr_shift] = prior_by_shift.get(spr_shift, 0) + cnt
			else:
				prior_by_shift["Other"] = prior_by_shift.get("Other", 0) + cnt

		other_shifts_rolls = max(0, day_rolls_total - shift_rolls)
		if not cur_shift:
			shift_rolls = day_rolls_total
			other_shifts_rolls = 0
			prior_by_shift = {}
		shift_max_rolls = max(0, max_rolls - other_shifts_rolls) if max_rolls > 0 else 0
		current_rolls = shift_rolls
		prior_shifts = [
			{"shift": k, "rolls": v} for k, v in sorted(prior_by_shift.items(), key=lambda x: x[0])
		]
		can_add = max_rolls <= 0 or day_rolls_total < max_rolls
	else:
		day_rolls_total = 0
		shift_max_rolls = max_rolls
		other_shifts_rolls = 0
		prior_shifts = []
		spr_name = _find_spr_for_pp(pp_id, prefer_draft=True) or ""
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
				mx = cint(_spr_job_max_roll_lines(job_row, spr))
				if mx > 0:
					max_rolls = mx
				current_rolls = cint(_spr_count_roll_lines_for_job(spr, job_id))
				day_rolls_total = current_rolls
				shift_max_rolls = max_rolls
		can_add = max_rolls <= 0 or current_rolls < max_rolls

	return {
		"max_rolls": max_rolls,
		"current_rolls": current_rolls,
		"shift_max_rolls": shift_max_rolls,
		"day_rolls_total": day_rolls_total,
		"other_shifts_rolls": other_shifts_rolls,
		"prior_shifts": prior_shifts,
		"can_add_roll": can_add,
		"spr_name": spr_name,
		"job_id": job_id,
	}


@frappe.whitelist()
def ensure_draft_spr_for_pp(pp_id, planning_sheet_item_names, unit=None, run_date=None, shift=None, force_new=0):
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

	if not cint(force_new):
		existing = _find_draft_spr_for_pp(pp_id)
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


def _spr_doc_fields(*names):
	"""Return field names that exist on Shaft Production Run (site custom fields vary)."""
	out = []
	for n in names:
		if frappe.db.has_column("Shaft Production Run", n):
			out.append(n)
	return out


def _spr_pick_doc_field(doc, *candidates, default=""):
	for key in candidates:
		if frappe.db.has_column("Shaft Production Run", key):
			val = doc.get(key)
			if val is not None and str(val).strip() != "":
				return _cstr(val)
	return _cstr(default)


def _extract_core_width_mm_from_item(item_name: str, item_code: str = "") -> float:
	"""Best-effort mm from paper-core Item name / custom fields."""
	for key in ("custom_core_width_mm", "core_width_mm", "custom_width_mm"):
		if item_code and frappe.db.has_column("Item", key):
			v = frappe.db.get_value("Item", item_code, key)
			if v and flt(v) > 0:
				return flt(v)
	name = _cstr(item_name)
	import re

	m = re.search(r"(\d{3,4})\s*mm", name, re.I)
	if m:
		return flt(m.group(1))
	m = re.search(r'(\d+(?:\.\d+)?)\s*["\u201d]', name)
	if m:
		# Inch label on core item — common stock sizes map to mm presets
		inch = flt(m.group(1))
		preset = {63: 1500, 85: 1600, 90: 1700, 118: 1800, 126: 1900}
		for k, mm in preset.items():
			if abs(inch - k) < 0.6:
				return float(mm)
	return 1600.0


def _preset_core_mm_for_fabric_width(width_inch: float) -> float:
	"""Map fabric roll width (inches) to stock core mm — SPR desk parity."""
	w = flt(width_inch)
	if w <= 0:
		return 1600.0
	preset = {63: 1500.0, 85: 1600.0, 90: 1700.0, 118: 1800.0, 126: 1900.0}
	for k, mm in preset.items():
		if abs(w - k) < 0.6:
			return mm
	if w < 63:
		return 1500.0
	if w < 85:
		return 1600.0
	if w < 90:
		return 1700.0
	if w < 118:
		return 1800.0
	return 1900.0


def _resolve_core_item_code_for_mm(mm: float) -> str:
	"""Paper-core Item name/code for a preset mm width (SPR Link field on roll lines)."""
	mm = flt(mm)
	if mm <= 0:
		return ""
	for row in get_gsm_core_width_options():
		if abs(flt(row.get("width_mm")) - mm) < 0.01:
			return _cstr(row.get("item_code")).strip()
	# Closest preset
	best = ""
	best_diff = 1e9
	for row in get_gsm_core_width_options():
		wm = flt(row.get("width_mm"))
		if wm <= 0:
			continue
		diff = abs(wm - mm)
		if diff < best_diff:
			best_diff = diff
			best = _cstr(row.get("item_code")).strip()
	return best


def _gsm_core_width_value_for_spr_item(payload: dict) -> str:
	"""Map GSM payload core width to SPR Item custom_core_width_mm (Link or numeric field)."""
	spi_meta = frappe.get_meta("Shaft Production Run Item")
	if not spi_meta.has_field("custom_core_width_mm"):
		return ""
	df = spi_meta.get_field("custom_core_width_mm")
	raw = payload.get("custom_core_width_mm")
	if raw in (None, ""):
		return ""
	if df.fieldtype == "Link":
		s = _cstr(raw).strip()
		if frappe.db.exists(df.options, s):
			return s
		# Numeric mm from GSM grid — resolve to paper-core Item
		try:
			mm = flt(s)
			if mm > 0:
				code = _resolve_core_item_code_for_mm(mm)
				if code and frappe.db.exists(df.options, code):
					return code
		except Exception:
			pass
		return ""
	return _cstr(raw).strip() if df.fieldtype in ("Data", "Small Text") else _cstr(flt(raw))


def _normalize_pp_shaft_job_row(shaft) -> frappe._dict:
	"""Align PP shaft detail field names with Shaft Production Run Job for weight helpers."""
	if not shaft:
		return frappe._dict()
	if isinstance(shaft, dict):
		row = frappe._dict(shaft)
	elif hasattr(shaft, "as_dict"):
		row = frappe._dict(shaft.as_dict())
	else:
		row = frappe._dict()
	if not _cstr(row.get("net_weight") or "").strip():
		nw = _pick_value(
			row,
			["net_weight_shaft_kgs", "net_weight_shaft", "custom_net_weight_shaft_kgs", "net_weight"],
			"",
		)
		if nw:
			row.net_weight = nw
	if not flt(row.get("total_weight")):
		tw = _pick_value(row, ["total_weight_kgs", "total_weight", "weight", "planned_qty"], 0)
		if tw:
			row.total_weight = tw
	return row


def _planned_qty_kg_from_pp_shaft(
	pp_id: str,
	width_inch=None,
	gsm=None,
	production_plan_item=None,
) -> float:
	"""Per-roll planned kg from PP shaft net weight (SPR Create Entry parity), not GSM formula."""
	pp_id = _cstr(pp_id).strip()
	wx = flt(width_inch)
	if not pp_id or wx <= 0:
		return 0.0
	ppi = _cstr(production_plan_item).strip()
	target_gsm = cint(gsm) if gsm is not None else 0

	spr_name = _find_spr_for_pp(pp_id, prefer_draft=True)
	if spr_name:
		spr = frappe.get_doc("Shaft Production Run", spr_name)
		net_ps, _jid = _spr_net_kg_per_shaft_for_pp_line_width(spr, wx, ppi or None)
		if net_ps is not None and flt(net_ps) > 0:
			return round(flt(net_ps), 3)

	if not frappe.db.exists("Production Plan", pp_id):
		return 0.0
	pp = frappe.get_doc("Production Plan", pp_id)
	for shaft in pp.get("custom_shaft_details") or pp.get("shaft_details") or []:
		row = _normalize_pp_shaft_job_row(shaft)
		if target_gsm and _shaft_gsm(row) != target_gsm:
			continue
		comb = _cstr(_pick_value(row, ["combination", "combined_width", "shaft", "shaft_details"], ""))
		segs = max(1, _count_combination_segments(comb))
		widths = _parse_combination_widths_inches(comb) if comb else []
		weights = _segment_weights_kg(row, segs)
		if segs > 1 and len(widths) >= segs:
			for i in range(segs):
				if abs(flt(widths[i]) - wx) <= 0.75 and i < len(weights) and flt(weights[i]) > 0:
					return round(flt(weights[i]), 3)
			continue
		tw = flt(row.get("total_width"))
		if tw > 0 and abs(tw - wx) <= 0.75 and weights:
			return round(flt(weights[0]), 3)
		if not comb and weights and flt(weights[0]) > 0:
			sw = _shaft_width_inch(row)
			if sw <= 0 or abs(sw - wx) <= 0.75:
				return round(flt(weights[0]), 3)
	return 0.0


def _resolve_core_mm_for_fabric_width(width_inch: float) -> float:
	"""Pick paper-core mm from Item master for fabric width (inch label or closest preset)."""
	import re

	w = flt(width_inch)
	target_mm = _preset_core_mm_for_fabric_width(w)
	rows = frappe.db.sql(
		"""
		SELECT name, item_name
		FROM `tabItem`
		WHERE disabled = 0
		  AND (item_name LIKE %s OR item_name LIKE %s OR name LIKE %s)
		ORDER BY item_name
		LIMIT 200
		""",
		('%" PC%', '% PC -%', '%PC%'),
		as_dict=True,
	)
	w_label = str(int(w)) if abs(w - round(w)) < 0.01 else f"{w:.1f}".rstrip("0").rstrip(".")
	for row in rows or []:
		name = _cstr(row.get("item_name") or "")
		if re.match(rf"^{re.escape(w_label)}\s*['\"\u201d″]", name):
			mm = _extract_core_width_mm_from_item(name, row.get("name") or "")
			if mm > 0:
				return mm
	best_mm = target_mm
	best_diff = 999999.0
	for row in rows or []:
		mm = _extract_core_width_mm_from_item(row.get("item_name") or "", row.get("name") or "")
		if mm <= 0:
			continue
		diff = abs(mm - target_mm)
		if diff < best_diff:
			best_diff = diff
			best_mm = mm
	return flt(best_mm) if best_mm > 0 else target_mm


@frappe.whitelist()
def get_gsm_roll_row_extras(
	gsm=None,
	width_inch=None,
	length_m=None,
	item_code=None,
	pp_id=None,
	production_plan_item=None,
):
	"""Planned qty (PP shaft net kg) + polybag + auto core mm for a GSM roll line."""
	gsm_val = cint(gsm) if gsm is not None else 0
	w_in = flt(width_inch) if width_inch is not None else 0.0
	ln = flt(length_m) if length_m is not None else 0.0
	item_code = _cstr(item_code).strip()
	pp_id = _cstr(pp_id).strip()
	ppi = _cstr(production_plan_item).strip()
	if not gsm_val and item_code:
		try:
			g, w = parse_item_code(item_code)
			if g > 0:
				gsm_val = int(g)
			if w > 0 and w_in <= 0:
				w_in = flt(w)
		except Exception:
			pass

	planned_qty = 0.0
	if pp_id and w_in > 0:
		planned_qty = _planned_qty_kg_from_pp_shaft(pp_id, w_in, gsm_val, ppi or None)
	if planned_qty <= 0 and gsm_val and w_in > 0 and ln > 0:
		planned_qty = compute_mix_roll_planned_qty_kg(gsm_val, w_in, ln)

	core_mm = _resolve_core_mm_for_fabric_width(w_in) if w_in > 0 else 1600.0
	core_item = _resolve_core_item_code_for_mm(core_mm)
	polybag = 0.0
	if item_code and frappe.db.exists("Item", item_code):
		for key in ("custom_polybag_kgs", "polybag_kgs", "custom_polybag_weight"):
			if frappe.db.has_column("Item", key):
				polybag = flt(frappe.db.get_value("Item", item_code, key) or 0)
				if polybag > 0:
					break
	return {
		"planned_qty": planned_qty,
		"custom_polybag_kgs": polybag,
		"custom_core_width_mm": core_item or "",
		"core_width_mm": core_mm,
	}


@frappe.whitelist()
def get_gsm_core_width_options():
	"""Paper-core Item options for Core Width select (SPR desk parity)."""
	rows = frappe.db.sql(
		"""
		SELECT name, item_name
		FROM `tabItem`
		WHERE disabled = 0
		  AND (item_name LIKE %s OR item_name LIKE %s OR name LIKE %s)
		ORDER BY item_name
		LIMIT 200
		""",
		('%" PC%', '% PC -%', '%PC%'),
		as_dict=True,
	)
	out = []
	seen_mm = set()
	for row in rows or []:
		mm = _extract_core_width_mm_from_item(row.get("item_name") or "", row.get("name") or "")
		label = _cstr(row.get("item_name") or row.get("name"))
		out.append({"item_code": row.get("name"), "label": label, "width_mm": mm})
		seen_mm.add(int(mm))
	# Standard fallbacks when Item master has no paper-core rows
	for mm in (1500, 1600, 1700, 1800, 1900):
		if mm not in seen_mm:
			out.append({"item_code": "", "label": f"{mm} mm", "width_mm": mm})
			seen_mm.add(mm)
	out.sort(key=lambda x: (flt(x.get("width_mm")), x.get("label") or ""))
	return out


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

	list_fields = [
		"name",
		"production_plan",
		"run_date",
		"shift",
		"custom_unit",
		"modified",
	]
	list_fields.extend(
		_spr_doc_fields(
			"operator",
			"supervisor",
			"custom_operator",
			"custom_supervisor",
			"custom_shift_operator",
			"custom_shift_supervisor",
		)
	)
	list_fields = list(dict.fromkeys(list_fields))

	sprs = frappe.get_all(
		"Shaft Production Run",
		filters=filters,
		fields=list_fields,
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
				"operator": _spr_pick_doc_field(
					spr,
					"operator",
					"custom_operator",
					"custom_shift_operator",
				),
				"supervisor": _spr_pick_doc_field(
					spr,
					"supervisor",
					"custom_supervisor",
					"custom_shift_supervisor",
				),
				"roll_count": len(rolls),
				"total_net_kg": round(total_net, 2),
				"total_gross_kg": round(total_gross, 2),
				"order_codes": sorted(order_codes),
				"wo_status": wo_status,
				"rolls": roll_rows,
			}
		)
	return out


def _parse_json_arg(val, default=None):
	if val is None:
		return default if default is not None else []
	if isinstance(val, str):
		try:
			return json.loads(val)
		except Exception:
			return default if default is not None else []
	return val


def _apply_gsm_session_header_to_spr(spr, run_date=None, shift=None, unit=None, operator=None, supervisor=None):
	"""Set GSM session header fields on draft SPR without touching desk SPR flows."""
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
	for value, candidates in (
		(operator, ("operator", "custom_operator", "custom_shift_operator")),
		(supervisor, ("supervisor", "custom_supervisor", "custom_shift_supervisor")),
	):
		val = _cstr(value).strip()
		if not val:
			continue
		for key in candidates:
			if frappe.db.has_column("Shaft Production Run", key) and _cstr(spr.get(key)) != val:
				spr.set(key, val)
				changed = True
				break
	return changed


def _gsm_pp_shaft_rows(pp) -> list[dict]:
	"""Read-only PP shaft details for GSM Shaft Details popup."""
	meter_keys = _meter_keys()
	out = []
	for idx, shaft in enumerate(pp.get("custom_shaft_details") or pp.get("shaft_details") or [], start=1):
		row = _normalize_pp_shaft_job_row(shaft)
		comb = _cstr(
			_pick_value(row, ["combination", "combined_width", "shaft", "shaft_details"], "")
		)
		meter_roll = flt(_pick_value(row, meter_keys, 0))
		no_of_shafts = _pick_value(
			row,
			["no_of_shafts", "no_of_shaft", "custom_no_of_shafts", "shaft_count", "number_of_shafts"],
			"",
		)
		if not no_of_shafts and comb:
			try:
				seg = _count_combination_segments(comb)
				if seg > 0:
					no_of_shafts = seg
			except Exception:
				pass
		net_weight = _pick_value(
			row,
			["net_weight", "net_weight_shaft_kgs", "net_weight_shaft", "custom_net_weight_shaft_kgs"],
			0,
		)
		out.append(
			{
				"job": _cstr(_pick_value(row, ["job_id", "job", "job_no"], str(idx))),
				"no_of_shafts": no_of_shafts,
				"gsm": _shaft_gsm(row),
				"combination": comb,
				"total_width": flt(_pick_value(row, ["total_width", "combined_width", "width"], 0))
				or _shaft_width_inch(row),
				"meter_roll": meter_roll,
				"net_weight": flt(net_weight),
			}
		)
	return out


def _gsm_order_code_for_pp(pp_id: str) -> str:
	if not pp_id or not frappe.db.exists("Production Plan", pp_id):
		return ""
	pp = frappe.get_doc("Production Plan", pp_id)
	if frappe.get_meta("Production Plan").has_field("custom_party_code"):
		return _cstr(pp.get("custom_party_code") or "")
	return _cstr(pp.get("custom_order_code") or "")


@frappe.whitelist()
def create_gsm_sprs_for_session(
	run_date=None,
	shift=None,
	unit=None,
	operator=None,
	supervisor=None,
	entries=None,
	force_new_session=0,
):
	"""GSM Step 1 — create/reuse one draft SPR per PP (same as Production Table create_item_spr)."""
	entries = _parse_json_arg(entries, [])
	if not entries:
		frappe.throw(_("Select at least one planning line"))

	pp_groups: dict[str, list] = {}
	for entry in entries:
		if not isinstance(entry, dict):
			continue
		pp_id = _cstr(entry.get("pp_id") or entry.get("ppId")).strip()
		line_id = _cstr(entry.get("lineId") or entry.get("planning_table_row") or entry.get("id")).strip()
		if not pp_id or not line_id:
			continue
		pp_groups.setdefault(pp_id, [])
		if line_id not in pp_groups[pp_id]:
			pp_groups[pp_id].append(line_id)

	if not pp_groups:
		frappe.throw(_("No valid Production Plan rows in selection"))

	sprs_out = []
	for pp_id, psi_names in pp_groups.items():
		result = ensure_draft_spr_for_pp(
			pp_id,
			psi_names,
			unit=unit,
			run_date=run_date,
			shift=shift,
			force_new=cint(force_new_session),
		)
		if not isinstance(result, dict) or result.get("status") != "ok" or not result.get("spr_name"):
			sprs_out.append(
				{
					"pp_id": pp_id,
					"status": "error",
					"message": _cstr(result.get("message") if isinstance(result, dict) else result) or _("Could not create SPR"),
				}
			)
			continue
		spr_name = result["spr_name"]
		spr = frappe.get_doc("Shaft Production Run", spr_name)
		if _apply_gsm_session_header_to_spr(spr, run_date, shift, unit, operator, supervisor):
			spr.save(ignore_permissions=True)
		label_type = resolve_label_from_pp_doc(frappe.get_doc("Production Plan", pp_id)) if frappe.db.exists(
			"Production Plan", pp_id
		) else ""
		sprs_out.append(
			{
				"pp_id": pp_id,
				"status": "ok",
				"spr_name": spr_name,
				"order_code": _cstr(spr.get("custom_order_code") or _gsm_order_code_for_pp(pp_id)),
				"label_type": label_type or _cstr(spr.get("custom_label") or ""),
				"reused": cint(result.get("reused") or 0),
				"shaft_job_count": len(_spr_job_rows(spr)),
			}
		)
	return {"status": "ok", "sprs": sprs_out}


@frappe.whitelist()
def get_gsm_pp_shaft_details(pp_ids=None):
	"""GSM Shaft Details popup — read PP shaft table (no SPR required)."""
	pp_ids = _parse_json_arg(pp_ids, [])
	if isinstance(pp_ids, str):
		pp_ids = [x.strip() for x in pp_ids.split(",") if x.strip()]
	if not pp_ids:
		frappe.throw(_("Production Plan id(s) required"))
	out = []
	for pp_id in pp_ids:
		pp_id = _cstr(pp_id).strip()
		if not pp_id or not frappe.db.exists("Production Plan", pp_id):
			out.append({"pp_id": pp_id, "status": "error", "message": _("Production Plan not found")})
			continue
		pp = frappe.get_doc("Production Plan", pp_id)
		out.append(
			{
				"pp_id": pp_id,
				"status": "ok",
				"order_code": _gsm_order_code_for_pp(pp_id),
				"label_type": resolve_label_from_pp_doc(pp) or "",
				"shaft_rows": _gsm_pp_shaft_rows(pp),
			}
		)
	return out


def _gsm_tolerance_orders_from_sprs(spr_names: list[str]) -> list[dict]:
	orders = []
	for spr_name in spr_names:
		check = spr_get_tolerance_violations(spr_name)
		if check.get("skipped") or not check.get("violations"):
			continue
		orders.append(
			{
				"spr_name": spr_name,
				"order_code": check.get("order_code") or "",
				"tolerance_percent": check.get("tolerance_percent"),
				"violations": check.get("violations") or [],
			}
		)
	return orders


def _gsm_apply_tolerance_override(spr_name: str, reason: str, approved: int):
	"""Set SPR tolerance override fields — same fields desk submit dialog uses."""
	spr = frappe.get_doc("Shaft Production Run", spr_name)
	meta = frappe.get_meta("Shaft Production Run")
	if not meta.has_field("tolerance_override_approved") or not meta.has_field("tolerance_override_reason"):
		return
	spr.tolerance_override_approved = cint(approved)
	spr.tolerance_override_reason = _cstr(reason).strip()
	spr.save(ignore_permissions=True)


@frappe.whitelist()
def save_gsm_roll_line(spr_name, roll_payload, shift=None):
	"""GSM real-time Save Row — thin wrapper for Vue."""
	return save_gsm_roll_line_to_spr(spr_name, roll_payload, shift=shift)


@frappe.whitelist()
def delete_gsm_roll_line(spr_name, batch_no=None, row_name=None):
	"""GSM Remove Row — delete one saved roll line from draft SPR."""
	return delete_gsm_roll_line_from_spr(spr_name, batch_no=batch_no, row_name=row_name)


@frappe.whitelist()
def submit_gsm_production_entry(
	run_date=None,
	shift=None,
	unit=None,
	operator=None,
	supervisor=None,
	rolls=None,
	session_sprs=None,
	tolerance_overrides=None,
	submit_sprs=True,
):
	"""
	GSM Step 2 — import rolls to draft SPRs, check existing SPR tolerance rules, submit.

	Does not change desk SPR flows. Uses the same tolerance_override_* fields and doc.submit()
	pipeline (manufacturing entries included).
	"""
	rolls = _parse_json_arg(rolls, [])
	session_sprs = _parse_json_arg(session_sprs, [])
	tolerance_overrides = _parse_json_arg(tolerance_overrides, [])
	submit_sprs = cint(submit_sprs)

	if not rolls:
		frappe.throw(_("No roll lines to submit"))
	if not session_sprs:
		frappe.throw(_("Create SPRs first"))

	pp_to_spr = {}
	for row in session_sprs:
		if not isinstance(row, dict):
			continue
		pp_id = _cstr(row.get("pp_id") or row.get("ppId")).strip()
		spr_name = _cstr(row.get("spr_name")).strip()
		if pp_id and spr_name:
			pp_to_spr[pp_id] = spr_name

	if not pp_to_spr:
		frappe.throw(_("No SPR mapping in session"))

	override_by_spr = {}
	for ov in tolerance_overrides:
		if not isinstance(ov, dict):
			continue
		sn = _cstr(ov.get("spr_name")).strip()
		if sn:
			override_by_spr[sn] = ov

	rolls_by_pp: dict[str, list] = {}
	for roll in rolls:
		if not isinstance(roll, dict):
			continue
		pp_id = _cstr(roll.get("pp_id")).strip()
		if not pp_id:
			continue
		rolls_by_pp.setdefault(pp_id, []).append(roll)

	imported = []
	import_failed = []
	for pp_id, spr_name in pp_to_spr.items():
		payloads = rolls_by_pp.get(pp_id) or []
		if not payloads:
			continue
		try:
			spr = frappe.get_doc("Shaft Production Run", spr_name)
			if _apply_gsm_session_header_to_spr(spr, run_date, shift, unit, operator, supervisor):
				spr.save(ignore_permissions=True)
			res = import_gsm_roll_lines_to_spr(spr_name, payloads, shift=shift)
			imported.append({"pp_id": pp_id, "spr_name": spr_name, **res})
		except Exception as e:
			import_failed.append({"pp_id": pp_id, "spr_name": spr_name, "error": _cstr(e)})

	if import_failed:
		return {
			"status": "import_failed",
			"imported": imported,
			"failed": import_failed,
		}

	spr_names = list(pp_to_spr.values())
	tolerance_orders = _gsm_tolerance_orders_from_sprs(spr_names)

	if tolerance_orders and submit_sprs:
		missing_override = []
		for order in tolerance_orders:
			sn = order["spr_name"]
			ov = override_by_spr.get(sn) or {}
			reason = _cstr(ov.get("reason") or ov.get("tolerance_override_reason")).strip()
			approved = cint(ov.get("approved") or ov.get("tolerance_override_approved"))
			if not (approved and reason):
				missing_override.append(sn)
		if missing_override:
			return {
				"status": "tolerance_required",
				"imported": imported,
				"orders": tolerance_orders,
				"message": _("Tolerance approval required for one or more orders"),
			}

	if not submit_sprs:
		return {
			"status": "imported",
			"imported": imported,
			"orders": tolerance_orders,
		}

	submitted = []
	submit_failed = []
	for pp_id, spr_name in pp_to_spr.items():
		try:
			ov = override_by_spr.get(spr_name) or {}
			reason = _cstr(ov.get("reason") or ov.get("tolerance_override_reason")).strip()
			approved = cint(ov.get("approved") or ov.get("tolerance_override_approved"))
			if reason and approved:
				_gsm_apply_tolerance_override(spr_name, reason, approved)
			doc = frappe.get_doc("Shaft Production Run", spr_name)
			if cint(doc.docstatus) == 0:
				doc.submit()
			submitted.append(
				{
					"pp_id": pp_id,
					"spr_name": spr_name,
					"order_code": _cstr(doc.get("custom_order_code") or ""),
					"roll_count": len(doc.items or []),
				}
			)
		except Exception as e:
			submit_failed.append({"pp_id": pp_id, "spr_name": spr_name, "error": _cstr(e)})

	status = "ok"
	if submit_failed and submitted:
		status = "partial"
	elif submit_failed and not submitted:
		status = "failed"

	total_kg = 0.0
	for row in submitted:
		try:
			doc = frappe.get_doc("Shaft Production Run", row["spr_name"])
			total_kg += sum(flt(getattr(it, "net_weight", 0)) for it in (doc.items or []))
		except Exception:
			pass

	return {
		"status": status,
		"imported": imported,
		"submitted": submitted,
		"failed": submit_failed,
		"total_kg": round(total_kg, 2),
	}
