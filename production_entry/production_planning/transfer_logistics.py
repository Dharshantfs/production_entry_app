# -*- coding: utf-8 -*-
"""Inter-company transfer logistics (isolated from BOM/planning sync)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime

from production_entry.production_planning.scheduler_api import (
	PLANNING_MOVEMENT_TYPE_FIELD,
	get_color_chart_data,
	is_transfer_movement,
	normalize_movement_type,
)

TRANSFER_WAREHOUSE_BY_COMPANY = {
	"Jayashree Spun Bond - 1ZT": {
		"s_warehouse": "Finished Goods - JSB-1ZT",
		"t_warehouse": "Goods In Transit - JSB-1ZT",
	},
	"J Vasanth Exports": {
		"s_warehouse": "Finished Goods Warehouse  - JVE",
		"t_warehouse": "Goods In Transit Warehouse  - JVE",
	},
}

BOARD_KIND_TO_SCOPE = {
	"production": "only_100",
	"lamination": "lamination_only",
	"printing_105": "printing_only",
	"printed_bopp_film": "printed_bopp_pb_only",
	"slitting": "slitting_only",
	"rewinding": "rewinding_only",
	"sheet_cutting": "sheet_cutting_only",
	"box_bag": "box_bag_only",
	"w_cut_d_cut": "dcut_only",
}

TRANSFER_APPROVER_ROLES = frozenset({"System Manager", "Manufacturing Manager", "Administrator"})

_EXTERNAL_TRANSFER_FIELD_CANDIDATES = (
	"external_transfer",
	"custom_external_transfer",
	"is_external_transfer",
	"ge_external_transfer",
)


def _cstr(v):
	return str(v or "").strip()


def _stock_entry_external_transfer_fieldname():
	"""Resolve Stock Entry checkbox field for External Transfer (site may use custom fieldname)."""
	for fn in _EXTERNAL_TRANSFER_FIELD_CANDIDATES:
		if frappe.db.has_column("Stock Entry", fn):
			return fn
	try:
		meta = frappe.get_meta("Stock Entry")
		for df in meta.fields:
			if df.fieldtype != "Check":
				continue
			lab = (df.label or "").strip().lower()
			if lab == "external transfer" or "external transfer" in lab:
				if frappe.db.has_column("Stock Entry", df.fieldname):
					return df.fieldname
	except Exception:
		pass
	return ""


def _set_stock_entry_external_transfer(se, value=1):
	fn = _stock_entry_external_transfer_fieldname()
	if not fn:
		return False
	se.set(fn, cint(value))
	return True


def _ensure_stock_entry_external_transfer(stock_entry_name, value=1):
	fn = _stock_entry_external_transfer_fieldname()
	if not fn or not stock_entry_name:
		return False
	if cint(frappe.db.get_value("Stock Entry", stock_entry_name, fn) or 0) == cint(value):
		return True
	frappe.db.set_value("Stock Entry", stock_entry_name, fn, cint(value), update_modified=False)
	return True


_ORDER_CODE_FIELD_CANDIDATES = (
	"order_code",
	"custom_order_code",
	"party_code",
	"custom_party_code",
)

_NATURE_OF_PROCESSING_FIELD_CANDIDATES = (
	"nature_of_processing",
	"custom_nature_of_processing",
)


def _stock_entry_order_code_fieldname():
	for fn in _ORDER_CODE_FIELD_CANDIDATES:
		if frappe.db.has_column("Stock Entry", fn):
			return fn
	try:
		meta = frappe.get_meta("Stock Entry")
		for df in meta.fields:
			lab = (df.label or "").strip().lower()
			if lab in ("order code", "order_code", "party code"):
				if frappe.db.has_column("Stock Entry", df.fieldname):
					return df.fieldname
	except Exception:
		pass
	return ""


def _order_codes_from_transfer_approval(ta):
	codes = []
	for ln in ta.lines or []:
		pc = _cstr(ln.party_code)
		if pc and pc not in codes:
			codes.append(pc)
	return codes


def _set_stock_entry_order_codes(se, order_codes):
	fn = _stock_entry_order_code_fieldname()
	if not fn or not order_codes:
		return False
	val = ", ".join(order_codes) if len(order_codes) > 1 else order_codes[0]
	se.set(fn, val)
	return True


def _ensure_stock_entry_order_codes(stock_entry_name, order_codes):
	fn = _stock_entry_order_code_fieldname()
	if not fn or not order_codes or not stock_entry_name:
		return False
	val = ", ".join(order_codes) if len(order_codes) > 1 else order_codes[0]
	frappe.db.set_value("Stock Entry", stock_entry_name, fn, val, update_modified=False)
	return True


def _stock_entry_nature_of_processing_fieldname():
	for fn in _NATURE_OF_PROCESSING_FIELD_CANDIDATES:
		if frappe.db.has_column("Stock Entry", fn):
			return fn
	try:
		meta = frappe.get_meta("Stock Entry")
		for df in meta.fields:
			if (df.label or "").strip().lower() in ("nature of processing", "nature_of_processing"):
				if frappe.db.has_column("Stock Entry", df.fieldname):
					return df.fieldname
	except Exception:
		pass
	return ""


_PARTY_FIELD_CANDIDATES = (
	"party",
	"custom_party",
	"custom_transfer_party",
	"custom_party_name",
)


def _resolve_stock_entry_party_fields(to_company):
	"""Find Party (+ party_type) fields on Stock Entry; prefer Link to Company."""
	tc = _cstr(to_company).strip()
	if not tc:
		return None, None, None
	party_fn = None
	party_type_fn = None
	fieldtype = ""
	try:
		meta = frappe.get_meta("Stock Entry")
		for df in meta.fields:
			lab = (df.label or "").strip().lower()
			fn = df.fieldname
			if lab != "party" and fn not in _PARTY_FIELD_CANDIDATES:
				continue
			opts = _cstr(df.options).strip()
			ft = df.fieldtype or ""
			if ft == "Link" and opts and opts != "Company" and "Company" not in opts.split("\n"):
				continue
			if ft in ("Link", "Dynamic Link", "Data", "Small Text"):
				party_fn = fn
				fieldtype = ft
				break
	except Exception:
		pass
	if not party_fn:
		for fn in _PARTY_FIELD_CANDIDATES:
			if frappe.db.has_column("Stock Entry", fn):
				party_fn = fn
				fieldtype = "Data"
				break
	if frappe.db.has_column("Stock Entry", "party_type"):
		party_type_fn = "party_type"
	return party_fn, party_type_fn, fieldtype


def _set_stock_entry_party(se, to_company):
	"""Party on STE = destination company (To Company from transfer approval)."""
	tc = _cstr(to_company).strip()
	if not tc:
		return False
	wrote = False
	if frappe.db.has_column("Stock Entry", "custom_transfer_to_company"):
		se.set("custom_transfer_to_company", tc)
		wrote = True
	party_fn, party_type_fn, ft = _resolve_stock_entry_party_fields(tc)
	if party_fn:
		if ft == "Data" or ft == "Small Text":
			se.set(party_fn, tc)
			wrote = True
		elif ft == "Link" and frappe.db.exists("Company", tc):
			se.set(party_fn, tc)
			if party_type_fn:
				se.set(party_type_fn, "Company")
			wrote = True
		elif ft == "Dynamic Link":
			se.set(party_fn, tc)
			if party_type_fn:
				se.set(party_type_fn, "Company")
			wrote = True
	return wrote


def _set_stock_entry_nature_of_processing(se, nature):
	nat = _cstr(nature).strip()
	if not nat:
		return False
	fn = _stock_entry_nature_of_processing_fieldname()
	if not fn:
		return False
	se.set(fn, nat)
	return True


def _ensure_stock_entry_party_and_nature(stock_entry_name, to_company, nature_of_processing):
	"""Re-apply party/nature after insert (insert may drop invalid Link values)."""
	if not stock_entry_name or not frappe.db.exists("Stock Entry", stock_entry_name):
		return
	tc = _cstr(to_company).strip()
	nat = _cstr(nature_of_processing).strip()
	try:
		se = frappe.get_doc("Stock Entry", stock_entry_name)
		if tc:
			_set_stock_entry_party(se, tc)
			if frappe.db.has_column("Stock Entry", "custom_transfer_to_company"):
				se.custom_transfer_to_company = tc
		if nat:
			_set_stock_entry_nature_of_processing(se, nat)
		se.flags.ignore_validate = True
		se.flags.ignore_links = True
		se.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "_ensure_stock_entry_party_and_nature")
		party_fn, party_type_fn, _ft = _resolve_stock_entry_party_fields(tc)
		if party_fn and tc:
			frappe.db.set_value("Stock Entry", stock_entry_name, party_fn, tc, update_modified=False)
		if party_type_fn and tc:
			frappe.db.set_value("Stock Entry", stock_entry_name, party_type_fn, "Company", update_modified=False)
		fn = _stock_entry_nature_of_processing_fieldname()
		if fn and nat:
			frappe.db.set_value("Stock Entry", stock_entry_name, fn, nat, update_modified=False)


def _transfer_date_in_scope(transfer_date, view_scope=None, date=None, week=None, month=None):
	"""Filter transfer history by daily / weekly / monthly scope (same as production table)."""
	try:
		td = getdate(transfer_date) if transfer_date else None
	except Exception:
		td = None
	if not td:
		return True
	vs = _cstr(view_scope).lower() or "all"
	if vs == "all":
		return True
	if vs == "weekly" and week:
		start, end = _week_range(week)
		return getdate(start) <= td <= getdate(end)
	if vs == "monthly" and month:
		start, end = _month_range(month)
		return getdate(start) <= td <= getdate(end)
	if vs == "daily" and date:
		return td == getdate(date)
	return True


def _transfer_approval_queue_fieldname():
	if frappe.db.has_column("Transfer Approval", "custom_logistics_queue_idx"):
		return "custom_logistics_queue_idx"
	return None


def _queue_idx_for_stock_entry(ste_name, from_company=None, to_company=None):
	qf = _transfer_approval_queue_fieldname()
	if not qf or not ste_name:
		return 0
	filters = {"stock_entry": ste_name, "status": "Approved"}
	if from_company:
		filters["from_company"] = _cstr(from_company)
	if to_company:
		filters["to_company"] = _cstr(to_company)
	return cint(frappe.db.get_value("Transfer Approval", filters, qf) or 0)


def _transfer_lane_stock_entries(
	from_company,
	to_company,
	include_submitted=1,
	view_scope=None,
	date=None,
	week=None,
	month=None,
	order_code=None,
):
	"""All approved transfers for a lane (draft + submitted) with dates and order codes."""
	fc = _cstr(from_company)
	tc = _cstr(to_company)
	if not fc or not tc:
		return []
	rows = frappe.get_all(
		"Transfer Approval",
		filters={
			"from_company": fc,
			"to_company": tc,
			"status": "Approved",
			"stock_entry": ["is", "set"],
		},
		fields=["name", "stock_entry", "modified", "creation", "to_destination_label", "approved_by"],
		order_by="modified desc",
		limit_page_length=50,
	)
	out = []
	oc_fn = _stock_entry_order_code_fieldname()
	for row in rows:
		ste = _cstr(row.get("stock_entry"))
		if not ste or not frappe.db.exists("Stock Entry", ste):
			continue
		ds = cint(frappe.db.get_value("Stock Entry", ste, "docstatus") or 0)
		if ds != 0 and not cint(include_submitted):
			continue
		ste_fields = ["posting_date", "posting_time"]
		if oc_fn:
			ste_fields.append(oc_fn)
		ste_row = frappe.db.get_value("Stock Entry", ste, ste_fields, as_dict=True) or {}
		try:
			ta = frappe.get_doc("Transfer Approval", row.name)
			order_codes = _order_codes_from_transfer_approval(ta)
			qty_total = sum(flt(ln.qty) for ln in ta.lines or [])
			line_count = len(ta.lines or [])
			submitted_status = _transfer_submitted_status_text(ta)
		except Exception:
			order_codes = []
			qty_total = 0
			line_count = 0
			submitted_status = _("Transferred")
		if oc_fn and ste_row.get(oc_fn):
			ste_oc = _cstr(ste_row.get(oc_fn))
			if ste_oc and ste_oc not in order_codes:
				order_codes = [ste_oc] + [c for c in order_codes if c != ste_oc]
		transfer_date = _cstr(ste_row.get("posting_date") or row.get("modified") or row.get("creation"))
		if not _transfer_date_in_scope(transfer_date, view_scope, date, week, month):
			continue
		oc_filter = _cstr(order_code).lower()
		if oc_filter:
			hay = " ".join(order_codes).lower()
			if oc_filter not in hay:
				continue
		qty_display = round(flt(qty_total), 2) if qty_total else 0
		out.append(
			{
				"name": ste,
				"approval": row.get("name"),
				"modified": row.get("modified"),
				"transfer_date": transfer_date,
				"docstatus": ds,
				"status": "Draft" if ds == 0 else submitted_status,
				"order_codes": order_codes,
				"order_codes_label": ", ".join(order_codes) if order_codes else "",
				"qty_total": qty_display,
				"line_count": line_count,
				"label": ste,
				"queue_idx": _queue_idx_for_stock_entry(ste, fc, tc),
				"can_reorder": ds == 0,
			}
		)
	out.sort(
		key=lambda x: (
			0 if x.get("docstatus") == 0 else 1,
			cint(x.get("queue_idx") or 0) or 9999,
			_cstr(x.get("modified")),
		)
	)
	return out


@frappe.whitelist()
def reorder_transfer_lane_queue(from_company=None, to_company=None, ste_names=None):
	"""Persist draft STE priority on Transfer Approval (logistics kanban drag-and-drop)."""
	fc = _cstr(from_company)
	tc = _cstr(to_company)
	if not fc or not tc:
		frappe.throw(_("From company and to company are required."))
	qf = _transfer_approval_queue_fieldname()
	if not qf:
		return {"updated": 0, "noop": "custom_logistics_queue_idx missing — run bench migrate"}
	if isinstance(ste_names, str):
		try:
			ste_names = json.loads(ste_names)
		except Exception:
			ste_names = [s.strip() for s in ste_names.split(",") if s.strip()]
	names = [n for n in (ste_names or []) if _cstr(n)]
	updated = 0
	for idx, ste in enumerate(names, start=1):
		if cint(frappe.db.get_value("Stock Entry", ste, "docstatus") or 0) != 0:
			continue
		ta_name = frappe.db.get_value(
			"Transfer Approval",
			{"stock_entry": ste, "from_company": fc, "to_company": tc, "status": "Approved"},
			"name",
		)
		if not ta_name:
			continue
		frappe.db.set_value("Transfer Approval", ta_name, qf, idx, update_modified=False)
		updated += 1
	frappe.db.commit()
	return {"updated": updated, "from_company": fc, "to_company": tc}


def _draft_stock_entries_for_lane(from_company, to_company):
	"""Backward-compatible: draft-only entries."""
	return [e for e in _transfer_lane_stock_entries(from_company, to_company) if e.get("docstatus") == 0]


def chart_row_transfer_fields(item):
	"""Read transfer columns from a Planning Table row dict."""
	mt = _cstr(item.get(PLANNING_MOVEMENT_TYPE_FIELD) or item.get("movement_type"))
	dest = _cstr(item.get("custom_transfer_destination"))
	status = _cstr(item.get("custom_transfer_status"))
	return mt, dest, status


def _produced_roll_count_for_chart_row(item):
	"""Rolls recorded on submitted SPR (Roll Production Results or summary field)."""
	pr = cint(item.get("produced_rolls") or 0) if isinstance(item, dict) else 0
	if pr > 0:
		return pr
	spr = _cstr(item.get("spr_name") if isinstance(item, dict) else "")
	if not spr or not frappe.db.exists("Shaft Production Run", spr):
		return 0
	if cint(frappe.db.get_value("Shaft Production Run", spr, "docstatus") or 0) != 1:
		return 0
	try:
		if frappe.db.table_exists("Roll Production Result"):
			cnt = frappe.db.count(
				"Roll Production Result",
				{"parent": spr, "parenttype": "Shaft Production Run"},
			)
			if cnt:
				return cint(cnt)
	except Exception:
		pass
	for fn in ("custom_no_of_rolls_created", "no_of_rolls", "roll_count_per_shaft"):
		if frappe.db.has_column("Shaft Production Run", fn):
			val = cint(frappe.db.get_value("Shaft Production Run", spr, fn) or 0)
			if val:
				return val
	return 0


def _transferred_roll_count_for_planning_row(ptr):
	"""Non-rejected transfer approval lines linked to this planning row."""
	row_id = _cstr(ptr)
	if not row_id:
		return 0
	rows = frappe.db.sql(
		"""
		select count(tl.name) as cnt
		from `tabTransfer Approval Line` tl
		inner join `tabTransfer Approval` ta on ta.name = tl.parent
		where tl.planning_table_row = %s and ifnull(ta.status, '') != 'Rejected'
		""",
		row_id,
		as_dict=True,
	)
	return cint(rows[0].cnt if rows else 0)


def _transfer_status_blocks_request(status, planning_table_row=None, produced_rolls=0, transferred_rolls=0):
	st = _cstr(status).lower()
	if not st:
		return False
	if st == "rejected":
		return False
	if st in {"pending approval", "approved", "draft ste created"}:
		return True
	if st.startswith("transferred") or "partially transferred" in st:
		pr = cint(produced_rolls)
		tr = cint(transferred_rolls)
		if pr > 0 and tr < pr:
			return False
		return True
	return False


def enrich_chart_row_transfer_payload(item, wo_terminal=False, spr_docstatus=0):
	"""Build API payload fields for order tables (no change to planning sync)."""
	mt, dest, status = chart_row_transfer_fields(item)
	mt_norm = normalize_movement_type(mt)
	if not mt_norm:
		try:
			from production_entry.production_planning.scheduler_api import resolve_movement_type_for_chart_row

			mt_norm = normalize_movement_type(resolve_movement_type_for_chart_row(item))
		except Exception:
			mt_norm = ""
	ptr = _cstr(item.get("itemName") or item.get("name") or item.get("planning_table_row"))
	produced_rolls = _produced_roll_count_for_chart_row(item)
	transferred_rolls = _transferred_roll_count_for_planning_row(ptr)
	can_transfer = (
		is_transfer_movement(mt)
		and bool(wo_terminal)
		and cint(spr_docstatus) == 1
		and not _transfer_status_blocks_request(
			status, ptr, produced_rolls, transferred_rolls
		)
	)
	block_reason = ""
	if not is_transfer_movement(mt):
		block_reason = "Not a transfer row"
	elif not wo_terminal:
		block_reason = "Work order not completed"
	elif cint(spr_docstatus) != 1:
		block_reason = "SPR not done"
	elif _transfer_status_blocks_request(status, ptr, produced_rolls, transferred_rolls):
		if produced_rolls > 0 and transferred_rolls >= produced_rolls:
			block_reason = _("All {0} produced rolls already in transfer").format(produced_rolls)
		else:
			block_reason = status
	movement_display = mt_norm or ""
	if dest and is_transfer_movement(mt):
		if produced_rolls > 0:
			movement_display = f"{mt_norm} → {dest} ({transferred_rolls}/{produced_rolls} rolls)"
		else:
			movement_display = f"{mt_norm} → {dest}"
	elif mt_norm == "Despatch":
		movement_display = "Despatch"
	return {
		"movement_type": mt_norm,
		"transfer_destination": dest,
		"transfer_status": status,
		"movement_display": movement_display,
		"can_transfer": can_transfer,
		"transfer_block_reason": block_reason,
		"produced_rolls": produced_rolls,
		"transferred_rolls": transferred_rolls,
	}


def _parse_chart_rows(raw):
	if raw is None:
		return []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except Exception:
			return []
	return list(raw) if isinstance(raw, list) else []


def _chart_fetch_kwargs(view_scope, date=None, week=None, month=None, board_kind=None):
	scope = BOARD_KIND_TO_SCOPE.get(_cstr(board_kind)) or "exclude_special"
	kwargs = {"planned_only": 1, "board_process_scope": scope, "plan_name": "__all__"}
	vs = _cstr(view_scope).lower() or "daily"
	if vs == "weekly" and week:
		kwargs["start_date"], kwargs["end_date"] = _week_range(week)
	elif vs == "monthly" and month:
		kwargs["start_date"], kwargs["end_date"] = _month_range(month)
	elif date:
		kwargs["date"] = date
	else:
		kwargs["date"] = getdate()
	return kwargs


def _week_range(week_val):
	"""ISO week input YYYY-Www → start/end dates."""
	try:
		parts = _cstr(week_val).split("-W")
		if len(parts) == 2:
			y, w = int(parts[0]), int(parts[1])
			from datetime import datetime, timedelta

			d = datetime.strptime(f"{y}-W{w}-1", "%G-W%V-%u").date()
			return str(d), str(d + timedelta(days=6))
	except Exception:
		pass
	return getdate(), getdate()


def _month_range(month_val):
	try:
		from frappe.utils import get_first_day, get_last_day

		d = getdate(f"{month_val}-01")
		return str(get_first_day(d)), str(get_last_day(d))
	except Exception:
		return getdate(), getdate()


def _row_matches_filters(row, party_code=None, customer=None, unit=None):
	if unit and _cstr(row.get("unit")) != _cstr(unit):
		return False
	pc = _cstr(party_code).lower()
	if pc:
		code = _cstr(row.get("partyCode") or row.get("party_code")).lower()
		if pc not in code:
			return False
	cu = _cstr(customer).lower()
	if cu:
		cn = _cstr(row.get("customer_name") or row.get("customer")).lower()
		if cu not in cn:
			return False
	return True


@frappe.whitelist()
def get_logistics_companies():
	rows = frappe.get_all(
		"Company",
		filters={},
		fields=["name"],
		order_by="name asc",
		limit_page_length=0,
	)
	return [{"name": r.name, "label": r.name} for r in rows]


@frappe.whitelist()
def get_transfer_destination_cards(
	from_company=None,
	view_scope=None,
	date=None,
	week=None,
	month=None,
	order_code=None,
):
	fc = _cstr(from_company)
	companies = get_logistics_companies()
	lane_kw = {
		"view_scope": view_scope,
		"date": date,
		"week": week,
		"month": month,
		"order_code": order_code,
	}
	out = []
	for c in companies:
		if fc and c["name"] == fc:
			continue
		tc = c["name"]
		history = _transfer_lane_stock_entries(fc, tc, **lane_kw) if fc else []
		out.append(
			{
				"company": tc,
				"label": _("Transfer to {0}").format(tc),
				"draft_stock_entries": [e for e in history if e.get("docstatus") == 0],
				"transfer_history": history,
			}
		)
	return out


@frappe.whitelist()
def get_transfer_eligible_rows(
	board_kind=None,
	view_scope=None,
	date=None,
	week=None,
	month=None,
	unit=None,
	party_code=None,
	customer=None,
):
	"""Rows with movement Transport; reuses color-chart WO/SPR flags without altering sync."""
	kwargs = _chart_fetch_kwargs(view_scope, date, week, month, board_kind)
	try:
		raw = get_color_chart_data(**kwargs)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_transfer_eligible_rows")
		raw = []
	rows = _parse_chart_rows(raw)
	out = []
	for r in rows:
		mt = normalize_movement_type(r.get("movement_type"))
		if not is_transfer_movement(mt):
			continue
		if not _row_matches_filters(r, party_code, customer, unit):
			continue
		pt_name = r.get("itemName") or r.get("name")
		if pt_name:
			r["transfer_status"] = _resolved_planning_row_transfer_status(pt_name, r.get("transfer_status"))
			r["custom_transfer_status"] = r["transfer_status"]
		spr_ds = cint(r.get("spr_docstatus") or 0)
		wo_terminal = bool(r.get("wo_terminal") or (spr_ds == 1 and _cstr(r.get("spr_name"))))
		extra = enrich_chart_row_transfer_payload(
			{"custom_movement_type": mt, **r},
			wo_terminal=wo_terminal,
			spr_docstatus=spr_ds,
		)
		out.append(
			{
				"planning_table_row": pt_name,
				"planning_sheet": r.get("planningSheet"),
				"party_code": r.get("partyCode"),
				"customer_name": r.get("customer_name") or r.get("customer"),
				"item_code": r.get("itemCode"),
				"item_name": r.get("description"),
				"unit": r.get("unit"),
				"qty": flt(r.get("qty")),
				"spr_name": r.get("spr_name"),
				"spr_docstatus": spr_ds,
				"wo_terminal": wo_terminal,
				"pp_id": r.get("pp_id"),
				"transfer_destination": r.get("transfer_destination"),
				"transfer_status": r.get("transfer_status"),
				**extra,
			}
		)
	return out


@frappe.whitelist()
def get_spr_produced_batches(spr_name=None, item_code=None, party_code=None, from_company=None):
	sn = _cstr(spr_name)
	if not sn or not frappe.db.exists("Shaft Production Run", sn):
		return []
	if cint(frappe.db.get_value("Shaft Production Run", sn, "docstatus") or 0) != 1:
		frappe.throw(_("SPR {0} must be submitted before transfer.").format(sn))
	ic_filter = _cstr(item_code)
	pc_filter = _cstr(party_code)
	fc = _cstr(from_company)
	batches = []
	seen = set()
	existing_transferred = frappe.db.sql("""
		select tl.batch_no 
		from `tabTransfer Approval Line` tl
		inner join `tabTransfer Approval` ta on ta.name = tl.parent
		where ta.status != 'Rejected' and tl.batch_no is not null
	""", as_dict=1)
	transferred_batches = {r.batch_no for r in existing_transferred}
	
	wh_list = []
	if fc:
		wh_list = frappe.get_all("Warehouse", filters={"company": fc}, pluck="name")

	def _add_batch(batch_no, qty, row=None, warehouse=None):
		bn = _cstr(batch_no)
		if not bn or bn in seen or bn in transferred_batches:
			return
			
		stock_qty = flt(frappe.db.sql("select sum(actual_qty) from `tabStock Ledger Entry` where batch_no=%s and is_cancelled=0", bn)[0][0] or 0)
			
		q = flt(qty or 0)
		if q <= 0:
			q = stock_qty
			
		seen.add(bn)
		batches.append(
			{
				"batch_no": bn,
				"item_code": (row or {}).get("item_code") or ic_filter,
				"item_name": (row or {}).get("item_name") or (frappe.db.get_value("Item", ic_filter, "item_name") if ic_filter else ""),
				"qty": q,
				"party_code": (row or {}).get("party_code") or pc_filter,
				"work_order": (row or {}).get("work_order"),
				"warehouse": warehouse,
			}
		)

	for row in frappe.get_all(
		"Shaft Production Run Item",
		filters={"parent": sn},
		fields=["batch_no", "item_code", "item_name", "net_weight", "gross_weight", "party_code", "work_order"],
		order_by="idx asc",
		limit_page_length=0,
	):
		bn = _cstr(row.get("batch_no"))
		if not bn or bn in seen:
			continue
		
		# Original exact batch
		_add_batch(bn, row.get("net_weight") or row.get("gross_weight") or 0, row)
		
		# Check for split batches (e.g. JS-01052611/1)
		split_bns = frappe.db.sql("""
			select distinct batch_no
			from `tabStock Ledger Entry`
			where batch_no like %s and is_cancelled=0
		""", (bn + "/%",), as_dict=1)
		for sb in split_bns:
			_add_batch(sb.batch_no, 0, row)
			
	if batches:
		return batches

	# Some submitted SPRs create stock/batches but the roll grid has no batch_no.
	# Fall back to linked Manufacture Stock Entries / Stock Ledger quantities.
	se_filters = {"docstatus": 1}
	se_meta = frappe.get_meta("Stock Entry")
	if se_meta.has_field("shaft_production_run"):
		se_filters["shaft_production_run"] = sn
	elif frappe.db.has_column("Stock Entry", "custom_spr_reference"):
		se_filters["custom_spr_reference"] = sn
	else:
		return []
	se_names = frappe.get_all("Stock Entry", filters=se_filters, pluck="name", limit_page_length=100) or []
	if not se_names:
		return []
	sle_filters = {
		"voucher_type": "Stock Entry",
		"voucher_no": ["in", se_names],
		"actual_qty": [">", 0],
	}
	if ic_filter:
		sle_filters["item_code"] = ic_filter
	for sle in frappe.get_all(
		"Stock Ledger Entry",
		filters=sle_filters,
		fields=["batch_no", "item_code", "actual_qty", "warehouse"],
		order_by="posting_date asc, posting_time asc, creation asc",
		limit_page_length=500,
	):
		if not _cstr(sle.get("batch_no")):
			continue
		_add_batch(
			sle.get("batch_no"),
			sle.get("actual_qty"),
			{"item_code": sle.get("item_code"), "item_name": frappe.db.get_value("Item", sle.get("item_code"), "item_name")},
			sle.get("warehouse"),
		)
	return batches


def _user_can_approve_transfer():
	roles = set(frappe.get_roles(frappe.session.user) or [])
	return bool(roles & TRANSFER_APPROVER_ROLES)


@frappe.whitelist()
def create_transfer_approval_request(
	from_company=None,
	to_company=None,
	to_destination_label=None,
	lines=None,
	nature_of_processing=None,
):
	fc = _cstr(from_company)
	tc = _cstr(to_company)
	label = _cstr(to_destination_label) or (_("Transfer to {0}").format(tc) if tc else "")
	if not fc or not tc:
		frappe.throw(_("From company and to company are required."))
	if fc == tc:
		frappe.throw(_("From and to company must be different."))
	if not frappe.db.exists("Company", fc) or not frappe.db.exists("Company", tc):
		frappe.throw(_("Invalid company."))
	wh = TRANSFER_WAREHOUSE_BY_COMPANY.get(fc)
	if not wh:
		frappe.throw(
			_("Transfer warehouses are not configured for company {0}. Contact administrator.").format(fc)
		)
	parsed = json.loads(lines) if isinstance(lines, str) else (lines or [])
	if not parsed:
		frappe.throw(_("Select at least one line with batch and qty."))
	nature = _cstr(nature_of_processing).strip()
	if not nature:
		frappe.throw(_("Nature of Processing is required before sending for approval."))

	doc = frappe.new_doc("Transfer Approval")
	doc.from_company = fc
	doc.to_company = tc
	doc.to_destination_label = label
	if frappe.db.has_column("Transfer Approval", "nature_of_processing"):
		doc.set("nature_of_processing", nature)
	elif hasattr(doc, "nature_of_processing"):
		doc.nature_of_processing = nature
	doc.status = "Pending Approval"
	doc.requested_by = frappe.session.user

	for line in parsed:
		ptr = _cstr(line.get("planning_table_row"))
		if not ptr or not frappe.db.exists("Planning Table", ptr):
			frappe.throw(_("Invalid planning row."))
		current_status = _cstr(
			frappe.db.get_value("Planning Table", ptr, "custom_transfer_status")
			if frappe.db.has_column("Planning Table", "custom_transfer_status")
			else ""
		)
		current_status = _resolved_planning_row_transfer_status(ptr, current_status)
		spr = _cstr(line.get("spr_name"))
		if not spr or cint(frappe.db.get_value("Shaft Production Run", spr, "docstatus") or 0) != 1:
			frappe.throw(_("SPR not done for row {0}. Cannot request transfer.").format(ptr))
		bn = _cstr(line.get("batch_no"))
		if not bn:
			frappe.throw(_("Batch is required for each line."))
		qty = flt(line.get("qty") or 0)
		if qty <= 0:
			qty = 1.0
		doc.append(
			"lines",
			{
				"planning_table_row": ptr,
				"planning_sheet": line.get("planning_sheet"),
				"party_code": line.get("party_code"),
				"customer_name": line.get("customer_name"),
				"item_code": line.get("item_code"),
				"unit": line.get("unit"),
				"spr_name": spr,
				"batch_no": bn,
				"qty": qty,
				"uom": line.get("uom") or "Kg",
				"transfer_allowed": 1,
				"block_reason": "",
			},
		)

	doc.insert(ignore_permissions=True)
	_stamp_planning_rows_for_transfer_request(doc.name, label)
	frappe.db.commit()
	return {"ok": True, "name": doc.name, "status": doc.status}


def update_planning_row_transfer_status(ptr):
	if not ptr or not frappe.db.exists("Planning Table", ptr):
		return
		
	rows = frappe.db.sql("""
		select ta.to_destination_label, ta.to_company, ta.status, count(tl.name) as roll_count
		from `tabTransfer Approval Line` tl
		inner join `tabTransfer Approval` ta on ta.name = tl.parent
		where tl.planning_table_row = %s and ta.status != 'Rejected'
		group by ta.name
	""", ptr, as_dict=1)
	
	if not rows:
		updates = {
			"custom_transfer_destination": "",
			"custom_transfer_status": ""
		}
	else:
		dests = []
		statuses = []
		total_transferred = 0
		for r in rows:
			lbl = r.to_destination_label or r.to_company or ""
			rc = cint(r.roll_count)
			total_transferred += rc
			if lbl and rc:
				dests.append(f"{lbl} ({rc} roll{'s' if rc != 1 else ''})")
			elif lbl:
				dests.append(lbl)
			statuses.append(r.status)

		produced_rolls = 0
		try:
			pt_row = frappe.db.get_value(
				"Planning Table",
				ptr,
				["spr_name", "item_code"],
				as_dict=True,
			)
			if pt_row:
				produced_rolls = _produced_roll_count_for_chart_row(
					{"spr_name": pt_row.get("spr_name"), "item_code": pt_row.get("item_code")}
				)
		except Exception:
			pass

		if "Pending Approval" in statuses:
			final_status = "Pending Approval"
		elif produced_rolls > 0 and total_transferred < produced_rolls:
			final_status = _("Partially transferred ({0}/{1} rolls)").format(
				total_transferred, produced_rolls
			)
		else:
			final_status = "Transferred"
		final_dest = " | ".join(dests)
		
		updates = {
			"custom_transfer_destination": final_dest,
			"custom_transfer_status": final_status
		}
		
	if frappe.db.has_column("Planning Table", "custom_transfer_destination"):
		frappe.db.set_value("Planning Table", ptr, updates, update_modified=False)
	_sync_psi_transfer_fields(ptr, updates)


def _stamp_planning_rows_for_transfer_request(approval_name, label):
	ta = frappe.get_doc("Transfer Approval", approval_name)
	for ln in ta.lines or []:
		if ln.planning_table_row:
			update_planning_row_transfer_status(ln.planning_table_row)


def _sync_psi_transfer_fields(pt_name, updates):
	if not updates or not frappe.db.table_exists("Planning sheet Item"):
		return
	pt = frappe.db.get_value(
		"Planning Table",
		pt_name,
		["item_code", "sales_order_item", "so_item", "parent"],
		as_dict=True,
	)
	if not pt:
		return
	soik = _cstr(pt.get("sales_order_item") or pt.get("so_item"))
	filters = {"parent": pt.parent, "item_code": pt.item_code}
	if soik and frappe.db.has_column("Planning sheet Item", "sales_order_item"):
		filters["sales_order_item"] = soik
	psi = frappe.db.get_value("Planning sheet Item", filters, "name")
	if psi:
		frappe.db.set_value("Planning sheet Item", psi, updates, update_modified=False)


def _transfer_submitted_status_text(ta):
	if isinstance(ta, dict):
		dest = _cstr(ta.get("to_company")) or _cstr(ta.get("to_destination_label"))
	else:
		dest = _cstr(getattr(ta, "to_company", None)) or _cstr(getattr(ta, "to_destination_label", None))
	return _("Transferred to {0}").format(dest) if dest else _("Transferred")


def _stamp_planning_rows_after_transfer_submit(ta):
	for ln in ta.lines or []:
		if ln.planning_table_row:
			update_planning_row_transfer_status(ln.planning_table_row)


def _resolved_planning_row_transfer_status(pt_name, fallback_status=""):
	ptr = _cstr(pt_name)
	if not ptr or not frappe.db.has_column("Planning Table", "custom_transfer_approval"):
		return _cstr(fallback_status)
	row = frappe.db.get_value(
		"Planning Table",
		ptr,
		["custom_transfer_status", "custom_transfer_approval"],
		as_dict=True,
	)
	if not row:
		return _cstr(fallback_status)
	status = _cstr(row.get("custom_transfer_status") or fallback_status)
	approval = _cstr(row.get("custom_transfer_approval"))
	if not approval:
		return status
	ta_row = frappe.db.get_value(
		"Transfer Approval",
		approval,
		["stock_entry", "to_company", "to_destination_label"],
		as_dict=True,
	)
	if not ta_row or not ta_row.get("stock_entry"):
		return status
	if cint(frappe.db.get_value("Stock Entry", ta_row.get("stock_entry"), "docstatus") or 0) != 1:
		return status
	transfer_status = _transfer_submitted_status_text(ta_row)
	if transfer_status != status and frappe.db.has_column("Planning Table", "custom_transfer_status"):
		updates = {"custom_transfer_status": transfer_status}
		frappe.db.set_value("Planning Table", ptr, updates, update_modified=False)
		_sync_psi_transfer_fields(ptr, updates)
	return transfer_status


def stock_entry_on_submit(doc, method=None):
	"""When transfer STE is submitted, mark source planning rows as transferred to destination."""
	ste_name = _cstr(getattr(doc, "name", None))
	if not ste_name or not frappe.db.exists("Transfer Approval", {"stock_entry": ste_name}):
		return
	ta_name = frappe.db.get_value("Transfer Approval", {"stock_entry": ste_name}, "name")
	if not ta_name:
		return
	ta = frappe.get_doc("Transfer Approval", ta_name)
	_stamp_planning_rows_after_transfer_submit(ta)


@frappe.whitelist()
def get_transfer_approvals(status_filter=None, limit=200, from_date=None, to_date=None, order_code=None):
	"""List transfer approvals for dashboard with status/date/order filters."""
	sf = _cstr(status_filter).lower() or "pending"
	filters = {}
	if sf == "pending":
		filters["status"] = ["in", ["Pending Approval", "Draft"]]
	elif sf == "approved":
		filters["status"] = "Approved"
	elif sf == "rejected":
		filters["status"] = "Rejected"
	elif sf == "draft":
		filters["status"] = "Draft"
	# sf == "all" → no status filter
	fd = _cstr(from_date).strip()
	td = _cstr(to_date).strip()
	if fd and len(fd) == 10:
		fd = fd + " 00:00:00"
	if td and len(td) == 10:
		td = td + " 23:59:59"
	if fd and td:
		filters["creation"] = ["between", [fd, td]]
	elif fd:
		filters["creation"] = [">=", fd]
	elif td:
		filters["creation"] = ["<=", td]

	rows = frappe.get_all(
		"Transfer Approval",
		filters=filters,
		fields=[
			"name",
			"from_company",
			"to_company",
			"to_destination_label",
			"status",
			"owner",
			"modified",
			"stock_entry",
			"requested_by",
			"nature_of_processing",
			"creation",
		],
		order_by="modified desc",
		limit_page_length=cint(limit) or 200,
	)
	if not rows:
		return rows
	names = [r.name for r in rows]
	line_rows = frappe.get_all(
		"Transfer Approval Line",
		filters={"parent": ["in", names]},
		fields=["parent", "party_code"],
		limit_page_length=0,
	) or []
	codes_by_parent = {}
	for ln in line_rows:
		pc = _cstr(ln.get("party_code")).strip()
		if not pc:
			continue
		codes_by_parent.setdefault(ln.get("parent"), [])
		if pc not in codes_by_parent[ln.get("parent")]:
			codes_by_parent[ln.get("parent")].append(pc)
	oc = _cstr(order_code).strip().lower()
	out = []
	for row in rows:
		codes = codes_by_parent.get(row.name, [])
		row["order_codes"] = codes
		row["order_codes_label"] = ", ".join(codes)
		row["transfer_date"] = str(row.get("creation") or "")[:10]
		if oc and not any(oc in _cstr(c).lower() for c in codes):
			continue
		out.append(row)
	return out


@frappe.whitelist()
def get_pending_transfer_approvals(limit=200):
	"""Backward-compatible alias."""
	return get_transfer_approvals(status_filter="pending", limit=limit)


@frappe.whitelist()
def get_transfer_approval_detail(name=None):
	if not name or not frappe.db.exists("Transfer Approval", name):
		frappe.throw(_("Transfer Approval not found."))
	doc = frappe.get_doc("Transfer Approval", name)
	return doc.as_dict()


@frappe.whitelist()
def approve_transfer_approval(name=None):
	if not _user_can_approve_transfer():
		frappe.throw(_("You do not have permission to approve transfers."), frappe.PermissionError)
	if not name or not frappe.db.exists("Transfer Approval", name):
		frappe.throw(_("Transfer Approval not found."))
	ta = frappe.get_doc("Transfer Approval", name)
	if ta.status == "Approved":
		return {"ok": True, "name": name, "stock_entry": ta.stock_entry}
	if ta.status == "Rejected":
		frappe.throw(_("This transfer was rejected."))
	ste = _create_draft_transfer_stock_entry(ta)
	ta.stock_entry = ste
	ta.status = "Approved"
	ta.approved_by = frappe.session.user
	ta.save(ignore_permissions=True)
	_finalize_planning_rows_after_approval(ta)
	frappe.db.commit()
	return {"ok": True, "name": name, "stock_entry": ste}


@frappe.whitelist()
def reorder_transfer_approval_lines(name=None, line_names=None):
	"""Reorder transfer lines before approval (same UX as sequence approval)."""
	if not name or not frappe.db.exists("Transfer Approval", name):
		frappe.throw(_("Transfer Approval not found."))
	ta = frappe.get_doc("Transfer Approval", name)
	if ta.status not in ("Pending Approval", "Draft"):
		frappe.throw(_("Only pending transfers can be reordered."))
	if isinstance(line_names, str):
		try:
			line_names = json.loads(line_names)
		except Exception:
			line_names = [x.strip() for x in line_names.split(",") if x.strip()]
	names = [n for n in (line_names or []) if _cstr(n)]
	if not names:
		return {"ok": True}
	by_name = {ln.name: ln for ln in (ta.lines or [])}
	new_lines = []
	for nm in names:
		if nm in by_name:
			new_lines.append(by_name[nm])
	for ln in ta.lines or []:
		if ln.name not in names:
			new_lines.append(ln)
	for i, ln in enumerate(new_lines, start=1):
		ln.idx = i
	ta.lines = new_lines
	ta.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "name": name}


@frappe.whitelist()
def reject_transfer_approval(name=None):
	if not _user_can_approve_transfer():
		frappe.throw(_("You do not have permission to reject transfers."), frappe.PermissionError)
	ta = frappe.get_doc("Transfer Approval", name)
	ta.status = "Rejected"
	ta.approved_by = frappe.session.user
	ta.save(ignore_permissions=True)
	for ln in ta.lines or []:
		if ln.planning_table_row:
			update_planning_row_transfer_status(ln.planning_table_row)
	frappe.db.commit()
	return {"ok": True, "name": name}


def _create_draft_transfer_stock_entry(ta):
	fc = _cstr(ta.from_company)
	wh = TRANSFER_WAREHOUSE_BY_COMPANY.get(fc)
	if not wh:
		frappe.throw(_("Warehouses not configured for {0}").format(fc))
	s_wh = wh["s_warehouse"]
	t_wh = wh["t_warehouse"]
	if not frappe.db.exists("Warehouse", s_wh):
		frappe.throw(_("Source warehouse missing: {0}").format(s_wh))
	if not frappe.db.exists("Warehouse", t_wh):
		frappe.throw(_("Target warehouse missing: {0}").format(t_wh))

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.company = fc
	se.set_posting_time = 1
	se.posting_date = getdate()
	se.posting_time = now_datetime().strftime("%H:%M:%S")
	_set_stock_entry_external_transfer(se, 1)
	if frappe.db.has_column("Stock Entry", "add_to_transit"):
		se.add_to_transit = 1
	unit_val = ""
	for ln in ta.lines or []:
		if ln.unit:
			unit_val = ln.unit
			break
	if unit_val and frappe.db.has_column("Stock Entry", "unit"):
		se.unit = unit_val
	order_codes = _order_codes_from_transfer_approval(ta)
	_set_stock_entry_order_codes(se, order_codes)
	_set_stock_entry_party(se, ta.to_company)
	nature = _cstr(getattr(ta, "nature_of_processing", None)).strip()
	_set_stock_entry_nature_of_processing(se, nature)

	for ln in ta.lines or []:
		qty = flt(ln.qty or 0)
		if qty <= 0:
			qty = 1.0
		ic = ln.item_code
		
		row = {
			"item_code": ic,
			"qty": qty,
			"s_warehouse": s_wh,
			"t_warehouse": t_wh,
			"uom": ln.uom or frappe.db.get_value("Item", ic, "stock_uom") or "Kg",
			"batch_no": ln.batch_no,
		}
		
		if frappe.db.has_column("Stock Entry Detail", "use_serial_batch_fields"):
			row["use_serial_batch_fields"] = 0
		if frappe.db.has_column("Stock Entry Detail", "scanned_qty"):
			row["scanned_qty"] = 0.0
		if frappe.db.has_column("Stock Entry Detail", "custom_scanned_qty"):
			row["custom_scanned_qty"] = 0.0
			
		se.append("items", row)

	se.insert(ignore_permissions=True)
	_ensure_stock_entry_order_codes(se.name, order_codes)
	_ensure_stock_entry_party_and_nature(se.name, ta.to_company, nature)
	if not _ensure_stock_entry_external_transfer(se.name, 1):
		frappe.log_error(
			title="Transfer Stock Entry — External Transfer field missing",
			message=_("Could not set External Transfer on {0}. Add a Check field labeled 'External Transfer' on Stock Entry.").format(
				se.name
			),
		)
	return se.name


def _finalize_planning_rows_after_approval(ta):
	for ln in ta.lines or []:
		ptr = ln.planning_table_row
		if not ptr:
			continue
		updates = {}
		if frappe.db.has_column("Planning Table", "custom_transfer_status"):
			updates["custom_transfer_status"] = "Draft STE Created"
		if frappe.db.has_column("Planning Table", "custom_transfer_destination"):
			updates["custom_transfer_destination"] = ta.to_destination_label
		if updates:
			frappe.db.set_value("Planning Table", ptr, updates, update_modified=False)
			_sync_psi_transfer_fields(ptr, updates)


def _find_transfer_ste_row_for_barcode(se, barcode):
	"""Match STE line by batch/roll barcode; multi-item transfers use batch, not first row item."""
	barcode = (barcode or "").strip()
	if not barcode:
		return None

	has_roll_no = frappe.db.has_column("Stock Entry Detail", "custom_roll_no")
	for row in se.items or []:
		roll = (row.get("custom_roll_no") or "").strip() if has_roll_no else ""
		if (row.batch_no or "").strip() == barcode or roll == barcode:
			return row

	if frappe.db.exists("Batch", barcode):
		batch_item = frappe.db.get_value("Batch", barcode, "item")
		if batch_item:
			for row in se.items or []:
				if row.item_code == batch_item and (row.batch_no or "").strip() == barcode:
					return row

	return None


@frappe.whitelist()
def record_transfer_barcode_scan(stock_entry, barcode):
	"""Material Transfer: scan marks full approved batch weight as scanned; never changes approved qty."""
	barcode = (barcode or "").strip()
	if not barcode:
		return {"ok": False, "error": _("No barcode provided")}
	if not stock_entry:
		return {"ok": False, "error": _("Stock Entry is required")}

	se = frappe.get_doc("Stock Entry", stock_entry)
	if se.docstatus != 0:
		return {"ok": False, "error": _("Cannot scan on a submitted Stock Entry")}
	if (se.stock_entry_type or "").strip() != "Material Transfer":
		return {"ok": False, "error": _("Barcode scan is only for Material Transfer")}

	has_scanned = frappe.db.has_column("Stock Entry Detail", "scanned_qty")
	has_custom_scanned = frappe.db.has_column("Stock Entry Detail", "custom_scanned_qty")

	match = _find_transfer_ste_row_for_barcode(se, barcode)

	if not match:
		return {"ok": False, "error": _("Batch {0} is not in the approved transfer list").format(barcode)}

	approved_qty = flt(match.qty)
	new_scanned = approved_qty if approved_qty > 0 else 0

	updates = {}
	if has_scanned:
		updates["scanned_qty"] = new_scanned
	if has_custom_scanned:
		updates["custom_scanned_qty"] = new_scanned
	if updates:
		frappe.db.set_value("Stock Entry Detail", match.name, updates, update_modified=False)
	if flt(match.qty) != approved_qty:
		frappe.db.set_value("Stock Entry Detail", match.name, "qty", approved_qty, update_modified=False)

	return {
		"ok": True,
		"row_name": match.name,
		"idx": match.idx,
		"scanned_qty": new_scanned,
		"qty": approved_qty,
		"batch_no": barcode,
	}
