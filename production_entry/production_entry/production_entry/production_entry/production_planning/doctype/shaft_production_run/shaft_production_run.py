import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowtime, today

from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
	extract_quality_and_color,
)


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


def _pp_has_104_work_order(pp_name: str) -> bool:
	if not pp_name or not frappe.db.exists("Production Plan", pp_name):
		return False
	try:
		for w in frappe.get_all(
			"Work Order",
			filters={"production_plan": pp_name, "docstatus": ["!=", 2]},
			fields=["production_item"],
			limit=30,
		):
			pi = _cstr((w or {}).get("production_item") or "")
			if pi.upper().startswith("104"):
				return True
	except Exception:
		pass
	return False


def spr_doc_is_lamination(doc) -> bool:
	"""104 lamination flow: operator checks Is Lamination and plan / roll item is 104…"""
	if not doc or not cint(getattr(doc, "custom_is_lamination", 0) or 0):
		return False
	ic = _spr_first_roll_item_code(doc)
	if ic and ic.upper().startswith("104"):
		return True
	pp = _cstr(getattr(doc, "production_plan", None) or "")
	return _pp_has_104_work_order(pp)


def _fabric_gsm_from_item_name(item_name: str) -> int:
	"""Parse Fabric GSM from item name by finding the F-<number> pattern (e.g. 'F-60' or 'F - 60' → 60)."""
	if not item_name:
		return 0
	m = re.search(r'\bF\s*-\s*(\d+)\b', item_name, re.IGNORECASE)
	if m:
		try:
			return int(m.group(1))
		except Exception:
			pass
	return 0


# Lamination GSM suffix map: item code ending e.g. '1041030010750890-C' → suffix 'C' → 15 gsm
_LAM_GSM_SUFFIX_MAP: dict[str, int] = {
	"A": 10,
	"B": 12,
	"B1": 13,
	"C": 15,
	"D": 30,
	"E": 20,
}


def _lam_gsm_from_item(item_name: str, item_code: str) -> int:
	"""Parse Lamination GSM from item name 'L-15 GSM' pattern, with -C suffix fallback.

	Item name pattern: 'L- 15 GSM' or 'L-15GSM'  → 15
	Item code suffix:  '1041030010750890-C' → suffix 'C' → 15 via _LAM_GSM_SUFFIX_MAP
	"""
	# Primary: parse 'L-<N> GSM' or 'L- <N> GSM' from item name
	if item_name:
		m = re.search(r'\bL-\s*(\d+)\s*GSM\b', item_name, re.IGNORECASE)
		if m:
			try:
				return int(m.group(1))
			except Exception:
				pass
	# Fallback: suffix after last '-' in item code (e.g. '-C' → 'C' → 15)
	if item_code:
		parts = str(item_code).strip().upper().split('-')
		if len(parts) >= 2:
			suffix = parts[-1].strip()
			if suffix in _LAM_GSM_SUFFIX_MAP:
				return _LAM_GSM_SUFFIX_MAP[suffix]
	return 0


def _fabric_gsm_from_planning_for_pp(pp_name: str) -> int:
	"""Fabric (100…) GSM from Planning Table child row on same sheet as 104 lamination line."""
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


def _batch_fields_from_spr_row(batch_meta, spr_row) -> dict:
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

	# Batch.custom_party_code_text ← Roll Production line.party_code (explicit; fallback legacy line text)
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
	roll_no = _spr_row_get(spr_row, "roll_no")

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
	"""Numeric widths per '+' segment, aligned with _count_combination_segments (e.g. 39\" + 24\" → [39, 24])."""
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
	
	# ✅ Build (GSM, WIDTH) → WO map using ITEM CODE parsing
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
			frappe.logger().info(f"[COMBO] Segment ({job_gsm}, {target_w}\") → WO {best.get('name')}")
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
	
	# ✅ DEDUPLICATE: For "63+63", return only UNIQUE WOs
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
	# ✅ Extract GSM from job_row for (GSM, WIDTH) matching
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


class ShaftProductionRun(Document):
	def validate(self):
		self.sync_shaft_job_work_orders_from_plan()
		self._spr_round_item_net_weights()
		self.calculate_produced_gsm()
		self.recalculate_job_achieved_weights()
		self.recalculate_job_achieved_meters()
		self.generate_batch_numbers()
		self._spr_recalc_total_produced_weight_header()

	def on_update(self):
		try:
			frappe.publish_realtime("shaft_production_run_updated", {"name": self.name})
		except Exception:
			pass

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
		"""Header = sum of net_weight on every roll line (no job filter — matches operator spreadsheet total)."""
		meta = frappe.get_meta("Shaft Production Run")
		if not meta.has_field("total_produced_weight"):
			return
		total = sum(flt(getattr(r, "net_weight", None), 2) for r in (self.items or []))
		self.total_produced_weight = flt(total, 2)
		if meta.has_field("custom_total_produced_weight"):
			self.custom_total_produced_weight = flt(total, 2)

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
		if not spr_doc_is_lamination(self):
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
			# ✅ Extract GSM from row for (GSM, WIDTH) matching
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

	def calculate_produced_gsm(self):
		"""Set produced_gsm on each roll line from effective weight (net, else gross), width, length (m)."""
		meta = frappe.get_meta("Shaft Production Run Item")
		if not meta.has_field("produced_gsm"):
			return
		unit_lam = _cstr(getattr(self, "custom_unit", None)).strip() == "Lamination Unit"
		lam = spr_doc_is_lamination(self) or unit_lam
		for row in self.items or []:
			if lam:
				ln = 0.0
				for key in ("produced_length_mtrs", "custom_produced_length_mtrs"):
					v = _spr_row_get(row, key)
					if v is not None and flt(v) > 0:
						ln = flt(v)
						break
			else:
				ln_m = _spr_length_meters(row)
				if ln_m is None or flt(ln_m) <= 0:
					ln = flt(getattr(row, "meter_roll", None))
				else:
					ln = flt(ln_m)
			wgt = _effective_weight_kg_for_produced_gsm(row)
			row.produced_gsm = compute_produced_gsm(wgt, row.width_inch, flt(ln))

	def on_submit(self):
		self.sync_batch_custom_fields()
		self.update_work_order_statuses()

	def on_cancel(self):
		self.cancel_manufacturing_stock_entries()

	def on_trash(self):
		"""Remove stale row links so deleted SPR is not shown as Continue Entry on Production Table."""
		try:
			if frappe.db.exists("DocType", "Planning Table") and frappe.db.has_column("Planning Table", "spr_name"):
				frappe.db.sql(
					"""
					UPDATE `tabPlanning Table`
					SET spr_name = ''
					WHERE IFNULL(spr_name, '') = %s
					""",
					(self.name,),
				)
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

	def _unit_digit(self) -> int:
		u_raw = (self.get("custom_unit") or "").strip()
		if not u_raw:
			return 0
		ul = u_raw.lower()
		if "lamination" in ul:
			return 5
		if "slitting" in ul:
			return 6
		m = re.search(r"(\d+)", u_raw)
		return int(m.group(1)) if m else 0

	def generate_batch_numbers(self):
		"""Assign batch_no on each roll line when draft is saved (after Create Entry + required header fields).

		Format: ``{MM}{U}{YY}{S}/{N}`` — month (2) + unit digit + year (2) + shift suffix ``S`` + ``/`` + roll sequence ``N``.
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
		rd = getdate(self.run_date)
		unit_d = self._unit_digit()
		root_5 = f"{rd.month:02d}{unit_d}{rd.year % 100:02d}"
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

	def _resolve_series_prefix(self, root_5: str) -> str:
		"""Reuse series for same run_date + shift + unit when batches already exist."""
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
				if pref.startswith(root_5) and len(pref) >= 6:
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
		for row in self.items or []:
			if not row.batch_no:
				continue
			bn = _cstr(row.batch_no)
			batch_name = bn
			if not frappe.db.exists("Batch", batch_name) and row.get("item_code"):
				batch_name = (
					frappe.db.get_value(
						"Batch",
						{"item": row.item_code, "batch_id": bn},
						"name",
					)
					or batch_name
				)
			if not batch_name or not frappe.db.exists("Batch", batch_name):
				continue
			data = dict(_batch_fields_from_spr_row(batch_meta, row))
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
		qty = flt(row.net_weight)
		if qty <= 0:
			qty = flt(row.gross_weight)
		return qty

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
		oc = _cstr(self.get("custom_order_code") or "")
		if not oc:
			return
		meta = frappe.get_meta("Stock Entry")
		for fn in ("order_code", "custom_order_code", "custom_party_code", "party_code"):
			if meta.has_field(fn):
				try:
					frappe.db.set_value("Stock Entry", se_name, fn, oc, update_modified=False)
				except Exception:
					pass
				return

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
		if not meta.has_field("unit"):
			return
		unit_value = self._resolve_spr_unit_value(wo_doc)
		if unit_value:
			se.unit = unit_value

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

	def _rm_shortages_for_se(self, se) -> list[tuple[str, str, float, float, float]]:
		"""Return RM shortages as (item_code, s_warehouse, required, available, shortage)."""
		out = []
		for d in se.items or []:
			if not d.item_code or d.get("t_warehouse"):
				continue
			required = flt(d.get("transfer_qty") or d.get("qty"))
			if required <= 0:
				continue
			wh = _cstr(d.get("s_warehouse"))
			available = flt(frappe.db.get_value("Bin", {"item_code": d.item_code, "warehouse": wh}, "actual_qty") or 0)
			shortage = required - available
			if shortage > 1e-9:
				out.append((_cstr(d.item_code), wh, required, available, shortage))
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

	def _assign_rm_batches_for_stock_entry(self, se):
		"""Assign batch_no for batch-tracked RM lines before submit."""
		for d in list(se.items or []):
			if not d.item_code or d.get("t_warehouse"):
				continue
			if _cstr(d.get("batch_no")):
				continue
			if not cint(frappe.db.get_value("Item", d.item_code, "has_batch_no") or 0):
				continue
			wh = _cstr(d.get("s_warehouse"))
			required = flt(d.get("transfer_qty") or d.get("qty") or 0)
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

	def _transfer_for_manufacture_type_name(self) -> str:
		"""Resolve a valid Stock Entry Type for 'Material Transfer for Manufacture' purpose."""
		if frappe.db.exists("Stock Entry Type", "Material Transfer for Manufacture"):
			p = _cstr(frappe.db.get_value("Stock Entry Type", "Material Transfer for Manufacture", "purpose"))
			if p == "Material Transfer for Manufacture":
				return "Material Transfer for Manufacture"
		name = frappe.db.get_value("Stock Entry Type", {"purpose": "Material Transfer for Manufacture"}, "name")
		return _cstr(name) if name else "Material Transfer for Manufacture"

	def _create_wip_shortage_transfer_draft(self, wo_doc, chunk_total_qty: float, shortages: list[tuple[str, str, float, float, float]]) -> str:
		"""Create a draft Material Transfer for Manufacture for shortage items only."""
		if not wo_doc or not shortages:
			return ""
		# Use current day/time for shortage transfers to avoid backdated ledger insufficiency on old run dates.
		transfer_posting_date = today()
		transfer_posting_time = nowtime()
		# Reuse existing draft for same WO + SPR to avoid duplicate drafts on retry.
		existing = self._find_open_wip_shortage_transfer_draft(_cstr(getattr(wo_doc, "name", None)))
		if existing:
			return existing
		raw_source_wh = _cstr(getattr(wo_doc, "source_warehouse", None)) or ""
		wip_wh = _cstr(getattr(wo_doc, "wip_warehouse", None)) or ""
		if not wip_wh:
			return ""
		short_by_item = defaultdict(float)
		for item_code, _wh, _req, _avl, short_qty in shortages:
			if item_code and flt(short_qty) > 0:
				short_by_item[_cstr(item_code)] += flt(short_qty)
		if not short_by_item:
			return ""

		# Path A: BOM-driven draft (best when site config supports it)
		try:
			se = frappe.new_doc("Stock Entry")
			se.company = wo_doc.company
			se.posting_date = transfer_posting_date
			se.posting_time = transfer_posting_time
			se.set_posting_time = 1
			se.purpose = "Material Transfer for Manufacture"
			se.stock_entry_type = self._transfer_for_manufacture_type_name()
			se.work_order = wo_doc.name
			se.from_bom = 1
			se.bom_no = wo_doc.bom_no
			se.use_multi_level_bom = wo_doc.use_multi_level_bom
			se.from_warehouse = raw_source_wh or None
			se.wip_warehouse = wip_wh
			se.to_warehouse = wip_wh
			se.fg_completed_qty = flt(chunk_total_qty) if flt(chunk_total_qty) > 0 else 1.0
			self._set_stock_entry_spr_link(se)
			se.get_items()

			for i in range(len(se.items or []) - 1, -1, -1):
				d = se.items[i]
				if not d.item_code or d.get("t_warehouse"):
					continue
				short_qty = flt(short_by_item.get(_cstr(d.item_code)))
				if short_qty <= 0:
					se.items.pop(i)
					continue
				cf = flt(d.get("conversion_factor") or 1.0) or 1.0
				d.transfer_qty = flt(short_qty)
				d.qty = flt(short_qty / cf)
				if raw_source_wh:
					d.s_warehouse = raw_source_wh
				if not d.t_warehouse:
					d.t_warehouse = wip_wh
			if any(d.item_code and d.get("t_warehouse") for d in (se.items or [])):
				se.insert()
				return se.name
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SPR shortage draft transfer (BOM path) failed")

		# Path B (fallback): manual rows directly from shortage map
		se = frappe.new_doc("Stock Entry")
		se.company = wo_doc.company
		se.posting_date = transfer_posting_date
		se.posting_time = transfer_posting_time
		se.set_posting_time = 1
		se.purpose = "Material Transfer for Manufacture"
		se.stock_entry_type = self._transfer_for_manufacture_type_name()
		se.work_order = wo_doc.name
		se.from_bom = 0
		se.from_warehouse = raw_source_wh or None
		se.wip_warehouse = wip_wh
		se.to_warehouse = wip_wh
		self._set_stock_entry_spr_link(se)
		for item_code, wh, _req, _avl, short_qty in shortages:
			qty = flt(short_qty)
			if not item_code or qty <= 0:
				continue
			stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
			se.append(
				"items",
				{
					"item_code": item_code,
					"s_warehouse": raw_source_wh or wh or wip_wh,
					"t_warehouse": wip_wh,
					"uom": stock_uom,
					"stock_uom": stock_uom,
					"conversion_factor": 1.0,
					"qty": qty,
					"transfer_qty": qty,
				},
			)
		if not se.items:
			return ""
		se.insert()
		return se.name

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
		lines = "\n".join(
			[
				_("{0} @ {1}: required {2}, available {3}, shortage {4}").format(
					it, wh or "—", flt(req, 2), flt(avl, 2), flt(sh, 2)
				)
				for it, wh, req, avl, sh in shortages[:20]
			]
		)
		next_steps = _(
			"1) Submit shortage transfer (Raw Materials -> WIP).\n"
			"2) Return to SPR and submit again."
		)
		if transfer_name:
			next_steps = _(
				'1) Open draft transfer: <a href="/app/stock-entry/{0}" target="_blank">{0}</a> '
				'(/app/stock-entry/{0})\n'
				"2) Verify source warehouse = Raw Materials and target warehouse = WIP, then submit.\n"
				'3) Return to SPR: <a href="/app/shaft-production-run/{1}" target="_blank">{1}</a> and submit again.'
			).format(transfer_name, self.name)
		elif transfer_err:
			next_steps = _(
				"Could not auto-create draft transfer on this site. "
				"Create 'Material Transfer for Manufacture' manually (Raw Materials -> WIP), submit it, then submit SPR again."
			)
		frappe.throw(
			_("Insufficient WIP stock for WO {0}.\n\n{1}\n\n{2}").format(wo_id, lines, next_steps),
			title=_("Insufficient stock"),
		)

	def _raise_shortage_with_transfer_batch(self, shortage_events):
		"""Create/reuse drafts for all shortage WOs and raise one combined message."""
		if not shortage_events:
			return
		sections = []
		did_create_or_reuse = False
		for event in shortage_events:
			wo_id = _cstr(event.get("wo_id"))
			wo_doc = event.get("wo_doc")
			chunk_total_qty = flt(event.get("chunk_total_qty"))
			shortages = event.get("shortages") or []
			transfer_name = ""
			try:
				transfer_name = self._create_wip_shortage_transfer_draft(wo_doc, chunk_total_qty, shortages)
				if transfer_name:
					did_create_or_reuse = True
			except Exception:
				transfer_name = ""
			lines = "\n".join(
				[
					_("{0} @ {1}: required {2}, available {3}, shortage {4}").format(
						it, wh or "—", flt(req, 2), flt(avl, 2), flt(sh, 2)
					)
					for it, wh, req, avl, sh in shortages[:10]
				]
			)
			if transfer_name:
				sections.append(
					_("WO {0}\n{1}\nDraft Transfer: <a href=\"/app/stock-entry/{2}\" target=\"_blank\">{2}</a>").format(
						wo_id, lines, transfer_name
					)
				)
			else:
				sections.append(_("WO {0}\n{1}\nDraft Transfer: could not auto-create").format(wo_id, lines))
		# Persist auto-created draft transfers before throwing, else request rollback can hide them.
		if did_create_or_reuse:
			try:
				frappe.db.commit()
			except Exception:
				pass
		frappe.throw(
			_(
				"Insufficient WIP stock detected for {0} WO(s).\n\n{1}\n\n"
				"Submit all listed draft transfer(s), then return to SPR {2} and submit once."
			).format(len(shortage_events), "\n\n".join(sections), self.name),
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
		roll_batch_data = _batch_fields_from_spr_row(batch_meta, spr_row)

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

	def _append_manufacture_fg_from_spr_rolls(self, se, wo_doc, spr_rows: list, fg_templates=None):
		"""One finished-good Stock Entry line per SPR roll, cloned from ERPNext FG template rows."""
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

		for spr in spr_rows:
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

	def _validate_rm_split_variance(self, wo_id: str, fg_total_qty: float, expected_rm: dict[str, float], actual_rm: dict[str, float]):
		"""Ensure split-entry RM consumption matches BOM-expected RM for this FG qty (same path as phantom SE)."""
		issues = []
		for item_code in sorted(set(expected_rm or {}) | set(actual_rm or {})):
			exp = flt((expected_rm or {}).get(item_code))
			act = flt((actual_rm or {}).get(item_code))
			diff = abs(act - exp)
			threshold = max(0.01, abs(exp) * 0.001)  # 0.1% or 0.01 qty floor
			if diff > threshold + 1e-9:
				issues.append((item_code, exp, act, act - exp, threshold))
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
		for spr in spr_rows or []:
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

	def create_manufacturing_stock_entries(self):
		"""Create submitted Manufacture Stock Entries from Roll Production Results (per WO / chunk).

		Operator flow (enforced in this method):

		1. **Before any Manufacture insert**: for every WO chunk, build a preview Manufacture entry and
		   check WIP raw-material stock. If anything is short, create a draft *Material Transfer for
		   Manufacture* (Raw Materials → WIP), ``commit`` it so it survives rollback, then throw with links.
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
			positive_rows = [
				r for r in (self.items or []) if flt(r.get("net_weight") or r.get("gross_weight") or 0) > 0
			]
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
					"Create Entry and ensure each row has Work Order + produced weight."
				),
				title=_("No manufacturing rows"),
			)

		created_entries = []
		created_entries_by_wo = defaultdict(list)
		planned_wo_posts = []

		# Phase 1: validate all WO groups first (no Stock Entry insert/submit here).
		for wo_id, rows in wo_groups.items():
			wo_doc = frappe.get_doc("Work Order", wo_id)
			total_qty = sum(self._row_fg_qty(r) for r in rows)
			wo_item = _cstr(getattr(wo_doc, "production_item", None))

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
						"different item(s): {2}. Correct Available Jobs → Work Orders mapping before submit."
					).format(wo_id, wo_item or "—", ", ".join(mismatch_items)),
					title=_("Wrong WO mapping"),
				)

			# 📊 DEBUG: Log WO and total quantity
			frappe.logger().info(f"[SPR CREATE] Processing WO: {wo_id}, SPR Total Qty: {total_qty} KG, WO Authorized Qty: {wo_doc.qty} KG")
			
			# Show in UI
			frappe.msgprint(
				_(f"📊 Creating Manufacturing Entry for WO: {wo_id} | Total Quantity: {total_qty} KG | WO Authorized: {wo_doc.qty} KG"),
				alert=False
			)

			if total_qty <= 0:
				frappe.msgprint(_("Skipping WO {0} — net/gross weight is 0").format(wo_id), alert=True)
				continue

			allowed_entry_qty, over_pct = self._wo_allowed_entry_qty(wo_doc)
			row_chunks = self._split_rows_by_qty_limit(rows, allowed_entry_qty)
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

			# 🔒 VALIDATION: Ensure WIP warehouse exists
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
				chunk_total_qty = sum(self._row_fg_qty(r) for r in chunk_rows)
				if chunk_total_qty <= 0:
					continue
				preview_se = self._build_shortage_preview_for_chunk(wo_doc, chunk_total_qty)
				shortages = self._rm_shortages_for_se(preview_se)
				if shortages:
					shortage_events.append(
						{
							"wo_id": wo_id,
							"wo_doc": wo_doc,
							"chunk_total_qty": chunk_total_qty,
							"shortages": shortages,
						}
					)
		if shortage_events:
			self._raise_shortage_with_transfer_batch(shortage_events)

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
				chunk_total_qty = sum(self._row_fg_qty(r) for r in chunk_rows)
				if chunk_total_qty <= 0:
					continue
				se = frappe.new_doc("Stock Entry")
				# ERPNext blocks a second Manufacture against the same WO once cumulative FG >= WO qty.
				# We submit with work_order blank then link after submit; still set flag so validation
				# never blocks partial multi-day / multi-SPR manufacture for the same WO.
				se.flags.ignore_duplicate_for_work_order = True
				se.company = wo_doc.company
				se.posting_date = today()
				se.posting_time = nowtime()
				se.set_posting_time = 1
				# Keep explicit type + purpose for sites where Stock Entry Type is mandatory.
				se.stock_entry_type = self._manufacture_stock_entry_type_name()
				# ERPNext get_items() runs before validate; purpose must be set here or BOM + FG lines are never built.
				se.purpose = "Manufacture"
				# Keep empty while inserting/submitting to avoid transfer-duplicate blocker (MAT-STE).
				# We link back to WO immediately after submit.
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

				# get_items() clears `items` and rebuilds from BOM + finished good; do not append rows before it.
				se.get_items()

				# 🔒 ENFORCE: ALL RM items MUST use WIP warehouse ONLY - NO OTHER WAREHOUSE
				# This prevents double consumption (materials already transferred to WIP)
				wip_warehouse = wo_doc.wip_warehouse
				rm_count = 0

				for item in se.items or []:
					if item.item_code:
						# Check if this is a RM item (no t_warehouse means it's a raw material)
						if not item.get("t_warehouse"):
							rm_count += 1
							# 🔒 ENFORCE: Set source warehouse to WIP ONLY
							item.s_warehouse = wip_warehouse

							# 🔒 VALIDATE: Ensure warehouse was set correctly
							if item.s_warehouse != wip_warehouse:
								frappe.throw(
									_("Raw material {0} source warehouse is {1}, not {2}. ABORT.").format(
										item.item_code, item.s_warehouse, wip_warehouse
									),
									title=_("Warehouse Mismatch")
								)
						else:
							# This is a finished good item - target warehouse should be FG warehouse
							if item.t_warehouse != wo_doc.fg_warehouse:
								item.t_warehouse = wo_doc.fg_warehouse

				# Log for verification
				if rm_count > 0:
					frappe.msgprint(
						_("Confirmed: {0} RM items set to use WIP warehouse: {1}").format(rm_count, wip_warehouse),
						alert=False
					)
				actual_rm_map = self._merge_rm_maps(actual_rm_map, self._collect_rm_map_from_se(se))

				# Default FG line has no batch; batch-mandatory items require batch_no per ERPNext validation.
				fg_templates = self._strip_finished_goods_from_stock_entry(se)
				self._append_manufacture_fg_from_spr_rolls(se, wo_doc, chunk_rows, fg_templates)
				self._assign_rm_batches_for_stock_entry(se)

				# Hard guard: submit path must always be Manufacture (never Material Transfer).
				se.stock_entry_type = self._manufacture_stock_entry_type_name()
				se.purpose = "Manufacture"
				se.insert()
				self._persist_stock_entry_spr_reference_db(se.name)
				if _cstr(se.purpose) != "Manufacture":
					frappe.throw(
						_(
							"Stock Entry {0} resolved to purpose {1}; expected Manufacture. "
							"Check Stock Entry Type/site customization remapping and retry."
						).format(
							se.name, _cstr(se.purpose) or "—"
						),
						title=_("Invalid Stock Entry purpose"),
					)
				# If entry type remaps purpose during validate hooks, block before submit.
				se.reload()
				# reload() drops in-memory flags; submit() must see this again or ERPNext duplicate-WO check runs.
				se.flags.ignore_duplicate_for_work_order = True
				self._set_stock_entry_spr_link(se)
				self._set_stock_entry_unit(se, wo_doc)
				se_meta = frappe.get_meta("Stock Entry")
				if (
					se_meta.has_field("unit")
					and _cstr(self._resolve_spr_unit_value(wo_doc))
					and _cstr(se.get("unit")) != _cstr(self._resolve_spr_unit_value(wo_doc))
				):
					frappe.db.set_value("Stock Entry", se.name, "unit", self._resolve_spr_unit_value(wo_doc), update_modified=False)
				if _cstr(se.purpose) != "Manufacture":
					frappe.throw(
						_(
							"Stock Entry {0} changed to purpose {1} after insert; expected Manufacture. "
							"Fix Stock Entry Type mapping/custom script and retry."
						).format(se.name, _cstr(se.purpose) or "—"),
						title=_("Invalid Stock Entry purpose"),
					)
				try:
					se.flags.ignore_duplicate_for_work_order = True
					se.submit()
				except Exception as e:
					# Prevent partial Manufacture commits when shortage/submit failure happens mid-run.
					try:
						frappe.db.rollback(save_point=mfg_submit_savepoint)
					except Exception:
						pass
					shortages = self._rm_shortages_for_se(se)
					if not shortages:
						shortages = self._rm_shortages_from_exception(e)
					if shortages:
						# Build one combined shortage response for all WO chunks in this submit attempt.
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
								shortages2 = self._rm_shortages_for_se(preview_se2)
								if not shortages2:
									continue
								submit_shortage_events.append(
									{
										"wo_id": wo_id2,
										"wo_doc": wo_doc2,
										"chunk_total_qty": chunk_total_qty2,
										"shortages": shortages2,
									}
								)
						# Fallback for ERPNext future-SLE shortages: propagate same RM item shortages to all WO plans.
						# This avoids one-WO-at-a-time draft generation loops for the same missing RM item.
						short_item_codes = sorted({_cstr(it) for it, _wh, _req, _avl, _sh in shortages if _cstr(it)})
						if short_item_codes:
							for p2 in planned_wo_posts:
								wo_id2 = p2["wo_id"]
								wo_doc2 = p2["wo_doc"]
								expected_rm2 = p2.get("expected_rm_map") or {}
								wip_wh2 = _cstr(getattr(wo_doc2, "wip_warehouse", None))
								extra_shortages = []
								for ic in short_item_codes:
									req2 = flt(expected_rm2.get(ic, 0))
									if req2 <= 0:
										continue
									avl2 = flt(
										frappe.db.get_value(
											"Bin",
											{"item_code": ic, "warehouse": wip_wh2},
											"actual_qty",
										)
										or 0
									)
									sh2 = req2 - avl2
									if sh2 <= 0:
										# future-SLE path may still fail even when current bin is positive;
										# keep WO in draft list when the triggering RM is common.
										sh2 = req2
									extra_shortages.append((ic, wip_wh2, req2, avl2, sh2))
								if extra_shortages:
									submit_shortage_events.append(
										{
											"wo_id": wo_id2,
											"wo_doc": wo_doc2,
											"chunk_total_qty": flt(p2.get("total_qty") or 0),
											"shortages": extra_shortages,
										}
									)
						self._raise_shortage_with_transfer_batch(submit_shortage_events)
					raise
				# Link back to WO after successful submit, then sync WO produced qty.
				frappe.db.set_value("Stock Entry", se.name, "work_order", wo_id, update_modified=False)
				self._apply_order_code_to_submitted_stock_entry(se.name)
				self._sync_work_order_produced_qty_from_submitted_manufacture(wo_id)
				self._sync_work_order_required_item_progress(wo_id)
				self._sync_production_plan_progress_from_work_orders(_cstr(getattr(wo_doc, "production_plan", None)))
				created_entries.append(se.name)
				created_entries_by_wo[wo_id].append(se.name)

				frappe.msgprint(
					_("WO {0}: Created {1}/{2} Manufacture entry {3} ({4} Kg).").format(
						wo_id, idx, len(row_chunks), se.name, flt(chunk_total_qty, 3)
					),
					alert=True,
				)
			self._validate_rm_split_variance(wo_id, total_qty, expected_rm_map, actual_rm_map)
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
						"Check Work Order mapping and produced weights, then retry."
					),
					title=_("No stock entry created"),
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


@frappe.whitelist()
def get_production_plan_details(production_plan):
	"""Fill header fields from Production Plan."""
	if not production_plan or not frappe.db.exists("Production Plan", production_plan):
		return {}
	pp = frappe.get_doc("Production Plan", production_plan)
	pp_meta = frappe.get_meta("Production Plan")
	out = {
		"customer": pp.get("customer"),
		"custom_unit": pp.get("custom_unit"),
	}
	# custom_order_code comes from PP's custom_party_code
	if pp_meta.has_field("custom_party_code"):
		out["custom_order_code"] = pp.get("custom_party_code") or ""
	
	label_value = resolve_label_from_pp_doc(pp)
	if label_value:
		out["custom_label"] = label_value
	
	# Calculate custom_total_planned_qty from WO sum
	out["custom_total_planned_qty"] = _production_plan_total_planned_qty(production_plan)
	
	frappe.logger().info(f"[get_production_plan_details] PP {production_plan}: custom_order_code={out.get('custom_order_code')}, custom_label={out.get('custom_label')}, custom_total_planned_qty={out.get('custom_total_planned_qty')}")
	if pp.get("sales_order"):
		so = frappe.db.get_value(
			"Sales Order", pp.sales_order, ["customer", "transaction_date"], as_dict=True
		)
		if so:
			out["customer"] = out["customer"] or so.customer
	return out


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
	"""Planned qty = net weight (kg) for this combination segment (e.g. 48\"→89.61, 37\"→69.08)."""
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
	across ``n_rolls`` (e.g. 97.08 kg / 2 rolls → 48.54 each).
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
	unit_d = doc._unit_digit()
	root_5 = f"{rd.month:02d}{unit_d}{rd.year % 100:02d}"
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


@frappe.whitelist()
def build_spr_roll_result_lines_for_job(
	shaft_production_run,
	job_id,
	lamination_rolls_per_combination=None,
	lamination_exact_roll_lines=None,
):
	"""
	Build Roll Production Result (SPR Item) lines for one job.
	
	✅ CORRECT: Extract GSM and WIDTH from Item Name, then match exactly.
	Combination "33+63" cycles rolls through widths [33, 63, 33, 63, ...]
	Each roll matched to correct WO by (GSM, WIDTH) tuple lookup.

	Lamination (104 + Is Lamination): pass ``lamination_rolls_per_combination`` = rolls per combination
	segment; total lines = segments × that number (shaft × roll formula is not used).
	"""
	if not job_id:
		frappe.throw(_("Job ID is required"))
	if not shaft_production_run or not frappe.db.exists("Shaft Production Run", shaft_production_run):
		frappe.throw(_("Save Shaft Production Run first"))
	pp_name = get_pp_from_spr(shaft_production_run)
	if not pp_name:
		frappe.throw(_("Production Plan not found on this Shaft Production Run"))
	spr_doc = frappe.get_doc("Shaft Production Run", shaft_production_run)
	job_row = None
	for j in _spr_job_rows(spr_doc):
		if _spr_job_keys_match(_spr_job_id(j), job_id):
			job_row = j
			break
	if not job_row:
		frappe.throw(_("Job {0} not found in Available Jobs").format(job_id))

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
	if lam_exact_n > 0:
		if not spr_doc_is_lamination(spr_doc):
			frappe.throw(
				_("Exact roll-line add mode is only for lamination: tick Is Lamination and use a 104 production plan.")
			)
		n_rolls = max(1, lam_exact_n)
	elif lam_n > 0:
		if not spr_doc_is_lamination(spr_doc):
			frappe.throw(
				_("Rolls-per-combination mode is only for lamination: tick Is Lamination and use a 104 production plan.")
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

	shaft_combination = get_shaft_combination(pp_name, job_id)
	if getattr(job_row, "combination", None) and not shaft_combination:
		shaft_combination = job_row.combination

	wo_list = _get_work_orders_for_spr_job(pp_name, spr_doc, job_row)
	if not wo_list:
		frappe.throw(_("No Work Orders for job {0} on this Production Plan").format(job_id))

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
	for idx in range(n_rolls):
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
					f"[SPR] Roll {idx + 1}: GSM {job_gsm} + Width {iw}\" → WO {wo['name']}"
				)

		if wo is None:
			wo = wo_list[0]
			frappe.logger().warning(
				f"[SPR WARNING] No exact match for GSM {job_gsm}, Width {individual_width}, using {wo['name']}"
			)

		if spr_doc_is_lamination(spr_doc):
			planned_qty = 0.0
		else:
			planned_qty = _planned_kg_for_spr_result_roll(job_row, idx, n_rolls, segs)
		row = _spr_item_line_from_wo(pp_name, job_id, shaft_combination, planned_qty, wo)
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
	✅ Extract GSM and WIDTH from Item Code (the source of truth).
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
			
			# ✅ Parse item code to get GSM and WIDTH (SOURCE OF TRUTH)
			gsm, width = parse_item_code(_cstr(production_item))
			
			if gsm > 0 and width > 0:
				key = (gsm, width)
				# ✅ KEEP FIRST OCCURRENCE: Don't overwrite if key already exists
				if key not in gsm_width_to_wo:
					gsm_width_to_wo[key] = wo
					frappe.logger().info(f"[WO MAP] {wo['name']} → GSM {gsm} + WIDTH {width}\" (from item code: {production_item})")
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
	gsm, width_inch = parse_item_code(item_code)
	quality, color = extract_quality_and_color(item_name or "", item_code=item_code)
	spi_meta = frappe.get_meta("Shaft Production Run Item")
	row: dict = {
		"work_order": wo["name"],
		"item_code": item_code,
		"item_name": item_name,
		"quality": quality or None,
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
		"color": color or None,
	}
	# Fabric GSM (F-60 in item name) and Lamination GSM (L-15 GSM in item name or -C suffix)
	if spi_meta.has_field("custom_fabric_gsm"):
		fab_gsm = _fabric_gsm_from_item_name(item_name) or _fabric_gsm_from_item_name(item_code)
		if fab_gsm > 0:
			row["custom_fabric_gsm"] = fab_gsm
	if spi_meta.has_field("custom_lam_gsm"):
		lam_gsm = _lam_gsm_from_item(item_name, item_code)
		if lam_gsm > 0:
			row["custom_lam_gsm"] = lam_gsm
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
	Map human job id (1, 2, … from s_no) to the correct Production Plan Item row name.
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
			width_mm = int(item_code[12:16])
			width_inch = round(width_mm / 25.4, 1)
			return gsm, width_inch
	except Exception:
		pass
	return 0, 0


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


def _spr_warehouses_exist():
	for wh in (SPR_MANUAL_SOURCE_WH, SPR_MANUAL_FG_WH):
		if not frappe.db.exists("Warehouse", wh):
			frappe.throw(_("Warehouse {0} not found. Create it or update SPR_MANUAL_* constants.").format(wh))


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
	fallback: list[str] = []
	for r in rows:
		wo_name = _cstr(r.get("name"))
		if not wo_name:
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


def _spr_insert_manual_work_order(
	pp,
	company: str,
	item_code: str,
	production_plan_item: str,
	ppi_row,
	qty: float,
) -> str:
	"""Insert a new Work Order for manual job flow."""
	from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
		get_default_bom_for_item,
	)

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
		wo.description = _("SPR manual job — PP line {0} · Item {1}").format(production_plan_item, item_code)
	if pp.get("sales_order"):
		wo.sales_order = pp.sales_order
	if frappe.get_meta("Work Order").has_field("sales_order_item"):
		wo.sales_order_item = getattr(ppi_row, "sales_order_item", None) or None
	wo.source_warehouse = SPR_MANUAL_SOURCE_WH
	wo.fg_warehouse = SPR_MANUAL_FG_WH
	if frappe.get_meta("Work Order").has_field("wip_warehouse"):
		wip = frappe.db.get_value("Stock Settings", None, "default_wip_warehouse")
		if wip:
			wo.wip_warehouse = wip
	frappe.flags.spr_manual_work_order_insert = True
	try:
		wo.insert(ignore_permissions=True)
	finally:
		frappe.flags.spr_manual_work_order_insert = False
	wo_name = wo.name
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
	return {"production_plan": pp_name, "company": company, "lines": out}


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
	_spr_warehouses_exist()

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

	reused = False
	wo_name = ""
	if selected_reuse_work_order:
		candidates = _spr_list_reusable_manual_work_orders(pp_name, item_code, production_plan_item)
		if selected_reuse_work_order in candidates:
			wo_name = selected_reuse_work_order
			reused = True
	if not wo_name:
		wo_name = _spr_find_reusable_manual_work_order(pp_name, item_code, production_plan_item, spr_doc=spr)
		if wo_name:
			reused = True
	if not wo_name:
		wo_name = _spr_insert_manual_work_order(pp, company, item_code, production_plan_item, ppi_row, qty)

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

	gsm, width_inch = parse_item_code(item_code)
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
def spr_create_manual_jobs_multi(shaft_production_run, no_of_shafts, items, no_of_rolls=None):
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
	_spr_warehouses_exist()
	pp = frappe.get_doc("Production Plan", pp_name)

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
		wo_name = ""
		if selected_reuse_work_order:
			candidates = _spr_list_reusable_manual_work_orders(pp_name, item_code, production_plan_item)
			if selected_reuse_work_order in candidates:
				wo_name = selected_reuse_work_order
		if not wo_name:
			wo_name = _spr_find_reusable_manual_work_order(pp_name, item_code, production_plan_item, spr_doc=spr)
		if not wo_name:
			wo_name = _spr_insert_manual_work_order(pp, company, item_code, production_plan_item, ppi_row, qty)
		else:
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
		_gsm, w_in = parse_item_code(item_code)
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
			cb = _format_shaft_combination_inches(width_inch_one)
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


@frappe.whitelist()
def spr_apply_bundle_packaging_for_job_width(
	shaft_production_run,
	job_id,
	width_inch,
	no_of_packaging,
	whole_gross_kg,
):
	"""Apply same single-roll gross to every roll line matching Job + selected width segment."""
	_spr_require_saved(shaft_production_run)
	job_id = _cstr(job_id)
	width_inch = flt(width_inch)
	no_of_packaging = cint(no_of_packaging)
	whole_gross_kg = flt(whole_gross_kg)
	if no_of_packaging < 1:
		frappe.throw(_("Number of packaging must be at least 1"))
	if whole_gross_kg <= 0:
		frappe.throw(_("Whole gross weight must be greater than zero"))
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

	single_gross = round(whole_gross_kg / float(no_of_packaging), 2)
	total_width_inch = round(width_inch * float(no_of_packaging), 4)

	for it in matching:
		it.gross_weight = single_gross
		# Only set gross_weight. Net weight auto-calculates via other functions when operator enters it.
		# Do NOT force net_weight here — let Frappe field handlers and auto-calculation manage it.

	bundle_net = round(sum(flt(getattr(it, "net_weight", None)) for it in matching), 2)

	# Store combination as: NO_OF_PACKAGING * WIDTH INCH (example: 4 * 39 INCH)
	comb_calculated = f"{no_of_packaging} * {width_inch} INCH"
	bs = {
		"combination": comb_calculated,
		"rolls_per_bundle": no_of_packaging,
		"single_roll_gross_weight_kg": single_gross,
		"sticker_width": total_width_inch,
		"sticker_bundle_gross_weight_kg": round(whole_gross_kg, 2),
		"sticker_bundle_weight": bundle_net,
	}
	if frappe.get_meta("Bundle Stickers").has_field("job_id"):
		bs["job_id"] = job_id or None
	spr.append("bundle_stickers", bs)
	spr.save(ignore_permissions=True)

	return {
		"updated_rolls": len(matching),
		"single_roll_gross_kg": single_gross,
		"total_width_inch": total_width_inch,
		"sticker_bundle_weight_kg": bundle_net,
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

	bs = {
		"combination": comb or None,
		"rolls_per_bundle": no_of_packaging,
		"single_roll_gross_weight_kg": single_gross,
		"sticker_width": total_width_inch,
		"sticker_bundle_gross_weight_kg": round(whole_gross_kg, 2),
		"sticker_bundle_weight": bundle_net,
	}
	if frappe.get_meta("Bundle Stickers").has_field("job_id"):
		bs["job_id"] = jid or None
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
