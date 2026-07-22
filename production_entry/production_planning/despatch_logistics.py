# -*- coding: utf-8 -*-
"""Despatch logistics: approval workflow and Delivery Note creation (mirrors transfer approvals)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime

from production_entry.production_planning.scheduler_api import (
	MOVEMENT_DESPATCH,
	get_color_chart_data,
	normalize_movement_type,
)
from production_entry.production_planning.transfer_logistics import (
	BOARD_KIND_TO_SCOPE,
	TRANSFER_WAREHOUSE_BY_COMPANY,
	_cstr,
	_chart_fetch_kwargs,
	_parse_chart_rows,
	_primary_submitted_spr_for_batch,
	_row_matches_filters,
	_transfer_date_in_scope,
	_transfer_row_unit_is_unassigned,
	_user_can_approve_transfer,
	get_logistics_companies,
	get_spr_produced_batches,
)

DESPATCH_APPROVER_ROLES = frozenset({"System Manager", "Manufacturing Manager", "Administrator"})
DESPATCH_PENDING_ARRANGEMENT_HISTORY_KEY = "despatch_pending_arrangement_history"
DESPATCH_APPROVED_ARRANGEMENT_HISTORY_KEY = "despatch_approved_arrangement_history"
DESPATCH_QUEUE_DEFAULTS_PENDING = "despatch_queue_pending"
DESPATCH_QUEUE_DEFAULTS_APPROVED = "despatch_queue_approved"


def _user_can_approve_despatch():
	roles = set(frappe.get_roles(frappe.session.user) or [])
	return bool(roles & DESPATCH_APPROVER_ROLES) or _user_can_approve_transfer()


def _fg_warehouse_for_company(company):
	wh = TRANSFER_WAREHOUSE_BY_COMPANY.get(_cstr(company))
	if wh:
		return wh.get("s_warehouse")
	return frappe.db.get_value(
		"Warehouse",
		{"company": company, "is_group": 0},
		"name",
		order_by="modified desc",
	)


def _batches_reserved_on_despatch():
	rows = frappe.db.sql(
		"""
		select dl.batch_no
		from `tabDespatch Approval Line` dl
		inner join `tabDespatch Approval` da on da.name = dl.parent
		where da.status != 'Rejected' and ifnull(dl.batch_no,'') != ''
		""",
		as_dict=1,
	)
	return {r.batch_no for r in rows if r.batch_no}


def _despatch_approval_queue_fieldname():
	if frappe.db.has_column("Despatch Approval", "custom_logistics_queue_idx"):
		return "custom_logistics_queue_idx"
	return None


def _despatch_pending_arrangement_history_key(from_company):
	return f"{DESPATCH_PENDING_ARRANGEMENT_HISTORY_KEY}::{_cstr(from_company)}"


def _load_despatch_pending_arrangement_history(from_company):
	key = _despatch_pending_arrangement_history_key(from_company)
	raw = frappe.defaults.get_global_default(key) or "[]"
	try:
		arr = json.loads(raw) if isinstance(raw, str) else (raw or [])
		return arr if isinstance(arr, list) else []
	except Exception:
		return []


def _save_despatch_pending_arrangement_history(from_company, snapshot):
	key = _despatch_pending_arrangement_history_key(from_company)
	history = _load_despatch_pending_arrangement_history(from_company)
	history.append(snapshot)
	if len(history) > 20:
		history = history[-20:]
	frappe.defaults.set_global_default(key, json.dumps(history))


def _despatch_queue_defaults_key(from_company, scope):
	prefix = DESPATCH_QUEUE_DEFAULTS_PENDING if scope == "pending" else DESPATCH_QUEUE_DEFAULTS_APPROVED
	return f"{prefix}::{_cstr(from_company)}"


def _load_despatch_queue_from_defaults(from_company, scope):
	raw = frappe.defaults.get_global_default(_despatch_queue_defaults_key(from_company, scope)) or "[]"
	try:
		arr = json.loads(raw) if isinstance(raw, str) else (raw or [])
		return [n for n in arr if _cstr(n)]
	except Exception:
		return []


def _save_despatch_queue_to_defaults(from_company, scope, approval_names):
	names = [n for n in (approval_names or []) if _cstr(n)]
	frappe.defaults.set_global_default(
		_despatch_queue_defaults_key(from_company, scope),
		json.dumps(names),
	)


def _order_approval_cards(cards, from_company, scope):
	"""Apply saved queue order (defaults + DB queue_idx fallback)."""
	items = list(cards or [])
	if not items:
		return items
	saved = _load_despatch_queue_from_defaults(from_company, scope)
	if saved:
		by_name = {c["name"]: c for c in items}
		ordered = [by_name[n] for n in saved if n in by_name]
		tail = [c for c in items if c["name"] not in saved]
		return ordered + tail
	items.sort(
		key=lambda a: (
			cint(a.get("queue_idx") or 0) or 9999,
			_cstr(a.get("creation")),
		)
	)
	return items


def _despatch_status_blocks_request(status):
	st = _cstr(status).strip().lower()
	if not st:
		return False
	if st == "rejected":
		return False
	if st in {"pending approval", "approved", "draft", "draft dn", "despatched"}:
		return True
	return False


def _sync_psi_despatch_fields(pt_name, updates):
	if not updates or not frappe.db.table_exists("Planning sheet Item"):
		return
	pt = frappe.db.get_value(
		"Planning Table",
		pt_name,
		["item_code", "sales_order_item", "so_item", "parent", "source_item"],
		as_dict=True,
	)
	if not pt:
		return
	psi = _cstr(pt.get("source_item"))
	if not psi or not frappe.db.exists("Planning sheet Item", psi):
		soik = _cstr(pt.get("sales_order_item") or pt.get("so_item"))
		filters = {"parent": pt.parent, "item_code": pt.item_code}
		if soik and frappe.db.has_column("Planning sheet Item", "sales_order_item"):
			filters["sales_order_item"] = soik
		elif soik and frappe.db.has_column("Planning sheet Item", "so_item"):
			filters["so_item"] = soik
		psi = frappe.db.get_value("Planning sheet Item", filters, "name")
	if psi:
		frappe.db.set_value("Planning sheet Item", psi, updates, update_modified=False)


def update_planning_row_despatch_status(ptr):
	"""Mirror active despatch approval state onto Planning Table + Planning sheet Item."""
	ptr = _cstr(ptr)
	if not ptr or not frappe.db.exists("Planning Table", ptr):
		return
	rows = frappe.db.sql(
		"""
		select da.name, da.status, da.delivery_note
		from `tabDespatch Approval Line` dl
		inner join `tabDespatch Approval` da on da.name = dl.parent
		where dl.planning_table_row = %s and ifnull(da.status, '') != 'Rejected'
		group by da.name, da.status, da.delivery_note
		order by da.modified desc
		""",
		ptr,
		as_dict=1,
	)
	if not rows:
		updates = {"custom_despatch_status": "", "custom_despatch_approval": ""}
	else:
		statuses = [_cstr(r.get("status")) for r in rows]
		approval = _cstr(rows[0].get("name"))
		if any(s in ("Pending Approval", "Draft") for s in statuses):
			final_status = "Pending Approval"
			for r in rows:
				if r.get("status") in ("Pending Approval", "Draft"):
					approval = _cstr(r.get("name"))
					break
		elif any(s == "Approved" for s in statuses):
			final_status = "Approved"
			for r in rows:
				if r.get("status") == "Approved":
					approval = _cstr(r.get("name"))
					dn = _cstr(r.get("delivery_note"))
					if dn and frappe.db.exists("Delivery Note", dn):
						ds = cint(frappe.db.get_value("Delivery Note", dn, "docstatus") or 0)
						if ds >= 1:
							final_status = "Despatched"
					break
		else:
			final_status = statuses[0] or ""
		updates = {"custom_despatch_status": final_status, "custom_despatch_approval": approval}
	if frappe.db.has_column("Planning Table", "custom_despatch_status"):
		frappe.db.set_value("Planning Table", ptr, updates, update_modified=False)
	_sync_psi_despatch_fields(ptr, updates)


def _resolved_planning_row_despatch_status(ptr, fallback_status=""):
	ptr = _cstr(ptr)
	if not ptr or not frappe.db.has_column("Planning Table", "custom_despatch_status"):
		return _cstr(fallback_status)
	row = frappe.db.get_value(
		"Planning Table",
		ptr,
		["custom_despatch_status", "custom_despatch_approval"],
		as_dict=True,
	)
	if not row:
		return _cstr(fallback_status)
	status = _cstr(row.get("custom_despatch_status") or fallback_status)
	if not status:
		live_rows = frappe.db.sql(
			"""
			select da.status
			from `tabDespatch Approval Line` dl
			inner join `tabDespatch Approval` da on da.name = dl.parent
			where dl.planning_table_row = %s and ifnull(da.status, '') != 'Rejected'
			order by da.modified desc
			limit 1
			""",
			ptr,
			as_dict=1,
		)
		if live_rows:
			update_planning_row_despatch_status(ptr)
			status = _cstr(
				frappe.db.get_value("Planning Table", ptr, "custom_despatch_status") or live_rows[0].get("status")
			)
	approval = _cstr(row.get("custom_despatch_approval"))
	if approval and frappe.db.exists("Despatch Approval", approval):
		live = _cstr(frappe.db.get_value("Despatch Approval", approval, "status"))
		if live == "Rejected":
			update_planning_row_despatch_status(ptr)
			return _cstr(
				frappe.db.get_value("Planning Table", ptr, "custom_despatch_status") or ""
			)
		if live and live != status:
			status = live
	return status


def _stamp_planning_rows_for_despatch_request(approval_name):
	da = frappe.get_doc("Despatch Approval", approval_name)
	for ln in da.lines or []:
		if ln.planning_table_row:
			update_planning_row_despatch_status(ln.planning_table_row)


def _pending_approval_names_sorted(from_company):
	qf = _despatch_approval_queue_fieldname()
	fields = ["name", "status", "creation"]
	if qf:
		fields.append(qf)
	rows = frappe.get_all(
		"Despatch Approval",
		filters={"from_company": _cstr(from_company), "status": ["in", ["Pending Approval", "Draft"]]},
		fields=fields,
		order_by="modified desc",
		limit_page_length=200,
	)
	rows.sort(
		key=lambda a: (
			cint(a.get(qf) or 0) or 9999 if qf else 9999,
			_cstr(a.get("creation")),
		)
	)
	return [_cstr(r.name) for r in rows if _cstr(r.name)]


def _apply_despatch_pending_queue(from_company, approval_names):
	qf = _despatch_approval_queue_fieldname()
	if not qf:
		return 0
	fc = _cstr(from_company)
	names = [n for n in (approval_names or []) if _cstr(n)]
	updated = 0
	for idx, name in enumerate(names, start=1):
		if not frappe.db.exists("Despatch Approval", name):
			continue
		st = _cstr(frappe.db.get_value("Despatch Approval", name, "status"))
		if st not in ("Pending Approval", "Draft"):
			continue
		if fc and _cstr(frappe.db.get_value("Despatch Approval", name, "from_company")) != fc:
			continue
		frappe.db.set_value("Despatch Approval", name, qf, idx, update_modified=False)
		updated += 1
	_save_despatch_queue_to_defaults(fc, "pending", names)
	frappe.db.commit()
	return updated


def _approved_approval_names_sorted(from_company):
	qf = _despatch_approval_queue_fieldname()
	fields = ["name", "status", "creation"]
	if qf:
		fields.append(qf)
	rows = frappe.get_all(
		"Despatch Approval",
		filters={"from_company": _cstr(from_company), "status": "Approved"},
		fields=fields,
		order_by="modified desc",
		limit_page_length=200,
	)
	rows.sort(
		key=lambda a: (
			cint(a.get(qf) or 0) or 9999 if qf else 9999,
			_cstr(a.get("creation")),
		)
	)
	return [_cstr(r.name) for r in rows if _cstr(r.name)]


def _apply_despatch_approved_queue(from_company, approval_names):
	qf = _despatch_approval_queue_fieldname()
	fc = _cstr(from_company)
	names = [n for n in (approval_names or []) if _cstr(n)]
	updated = 0
	for idx, name in enumerate(names, start=1):
		if not frappe.db.exists("Despatch Approval", name):
			continue
		if _cstr(frappe.db.get_value("Despatch Approval", name, "status")) != "Approved":
			continue
		if fc and _cstr(frappe.db.get_value("Despatch Approval", name, "from_company")) != fc:
			continue
		if qf:
			frappe.db.set_value("Despatch Approval", name, qf, idx, update_modified=False)
		updated += 1
	_save_despatch_queue_to_defaults(fc, "approved", names)
	frappe.db.commit()
	return updated


def _resolve_customer(customer_name):
	cn = _cstr(customer_name)
	if not cn:
		return ""
	if frappe.db.exists("Customer", cn):
		return cn
	found = frappe.db.get_value("Customer", {"customer_name": cn}, "name")
	return found or ""


@frappe.whitelist()
def get_despatch_company_cards(
	from_company=None,
	view_scope=None,
	date=None,
	week=None,
	month=None,
	order_code=None,
):
	"""Company cards for despatch mode with pending/approved approval chips."""
	fc = _cstr(from_company)
	companies = get_logistics_companies()
	oc = _cstr(order_code).strip().lower()
	out = []
	for c in companies:
		name = c["name"]
		if fc and name != fc:
			continue
		filters = {"from_company": name}
		if oc:
			pass
		qf = _despatch_approval_queue_fieldname()
		approval_fields = ["name", "status", "delivery_note", "modified", "creation"]
		if qf:
			approval_fields.append(qf)
		approvals = frappe.get_all(
			"Despatch Approval",
			filters=filters,
			fields=approval_fields,
			order_by="modified desc",
			limit_page_length=80,
		)
		enriched = []
		for da in approvals or []:
			despatch_date = _cstr(da.get("modified") or da.get("creation"))[:10]
			if not _transfer_date_in_scope(despatch_date, view_scope, date, week, month):
				continue
			lines = frappe.get_all(
				"Despatch Approval Line",
				filters={"parent": da.name},
				fields=["party_code", "customer_name", "item_code", "qty", "batch_no"],
				limit_page_length=200,
			)
			codes = []
			customers = []
			items = set()
			batches = set()
			for ln in lines:
				pc = _cstr(ln.get("party_code"))
				if pc and pc not in codes:
					codes.append(pc)
				cn = _cstr(ln.get("customer_name"))
				if cn and cn not in customers:
					customers.append(cn)
				ic = _cstr(ln.get("item_code"))
				if ic:
					items.add(ic)
				bn = _cstr(ln.get("batch_no"))
				if bn:
					batches.add(bn)
			if oc and not any(oc in _cstr(x).lower() for x in codes):
				continue
			total_qty = round(sum(flt(ln.get("qty")) for ln in lines), 3)
			dn_name = _cstr(da.delivery_note)
			dn_docstatus = 0
			if dn_name and frappe.db.exists("Delivery Note", dn_name):
				dn_docstatus = cint(frappe.db.get_value("Delivery Note", dn_name, "docstatus") or 0)
			roll_count = len(batches) or len(lines)
			item_count = len(items) or len(lines)
			card_status = da.status
			if da.status == "Approved" and dn_docstatus >= 1:
				card_status = "Despatched"
			elif da.status == "Approved" and dn_name and dn_docstatus == 0:
				card_status = "Draft DN"
			queue_idx = cint(da.get(qf) or 0) if qf else 0
			enriched.append(
				{
					"name": da.name,
					"status": da.status,
					"card_status": card_status,
					"delivery_note": dn_name,
					"dn_docstatus": dn_docstatus,
					"roll_count": roll_count,
					"item_count": item_count,
					"line_count": len(lines),
					"order_codes_label": ", ".join(codes),
					"customers_label": ", ".join(customers),
					"qty_total": total_qty,
					"creation": da.creation,
					"despatch_date": despatch_date,
					"queue_idx": queue_idx,
				}
			)
		pending = [a for a in enriched if a["status"] in ("Pending Approval", "Draft")]
		pending = _order_approval_cards(pending, name, "pending")
		approved_ready_dn = [
			a
			for a in enriched
			if a["status"] == "Approved"
			and (not a.get("delivery_note") or cint(a.get("dn_docstatus")) == 0)
		]
		despatched = [a for a in enriched if a.get("card_status") == "Despatched"]
		approved_on_card = [a for a in enriched if a["status"] == "Approved"]
		approved_on_card = _order_approval_cards(approved_on_card, name, "approved")
		out.append(
			{
				"company": name,
				"label": name,
				"pending_approvals": pending,
				"approved_ready_dn": approved_ready_dn,
				"approved_approvals": approved_on_card,
				"despatched_approvals": despatched,
				"despatch_history": enriched,
			}
		)
	return out


@frappe.whitelist()
def get_despatch_eligible_rows(
	board_kind=None,
	view_scope=None,
	date=None,
	week=None,
	month=None,
	unit=None,
	party_code=None,
	customer=None,
	from_company=None,
	board_slug=None,
):
	"""Planning rows with movement Despatch and submitted SPR."""
	kwargs = _chart_fetch_kwargs(
		view_scope, date, week, month, board_kind, board_slug=board_slug
	)
	try:
		raw = get_color_chart_data(**kwargs)
	except frappe.PermissionError:
		raise
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_despatch_eligible_rows")
		raw = []
	rows = _parse_chart_rows(raw)
	out = []
	for r in rows:
		mt = normalize_movement_type(r.get("movement_type"))
		if mt != MOVEMENT_DESPATCH:
			continue
		if not _row_matches_filters(r, party_code, customer, unit):
			continue
		if _transfer_row_unit_is_unassigned(r.get("unit")):
			continue
		spr = _cstr(r.get("spr_name"))
		spr_ds = cint(r.get("spr_docstatus") or 0)
		ptr = _cstr(r.get("itemName") or r.get("name"))
		despatch_status = _resolved_planning_row_despatch_status(
			ptr, _cstr(r.get("custom_despatch_status") or r.get("despatch_status"))
		)
		can = bool(spr and spr_ds == 1)
		block = ""
		if not spr:
			block = _("No SPR linked")
		elif spr_ds != 1:
			block = _("SPR must be submitted")
		elif _despatch_status_blocks_request(despatch_status):
			can = False
			block = despatch_status or _("Despatch approval in progress")
		out.append(
			{
				"planning_table_row": ptr,
				"planning_sheet": r.get("planningSheet"),
				"party_code": r.get("partyCode"),
				"customer_name": r.get("customer_name") or r.get("customer"),
				"item_code": r.get("itemCode"),
				"item_name": r.get("description"),
				"unit": r.get("unit"),
				"qty": flt(r.get("qty")),
				"spr_name": spr,
				"spr_docstatus": spr_ds,
				"can_despatch": can,
				"despatch_block_reason": block,
				"despatch_status": despatch_status,
				"movement_type": mt,
			}
		)
	return out


@frappe.whitelist()
def get_despatch_spr_batches(spr_name=None, item_code=None, party_code=None, from_company=None):
	"""Produced batches from submitted SPR(s) — supports multi-SPR CSV on planning rows."""
	batches = get_spr_produced_batches(spr_name, item_code, party_code, from_company) or []
	reserved = _batches_reserved_on_despatch()
	if not reserved:
		return batches
	return [b for b in batches if _cstr(b.get("batch_no")) not in reserved]


@frappe.whitelist()
def get_despatch_other_batches(item_code=None, from_company=None, party_code=None):
	"""All batches with stock for item in company warehouses (excluding reserved despatch batches)."""
	ic = _cstr(item_code)
	fc = _cstr(from_company)
	if not ic:
		return []
	reserved = _batches_reserved_on_despatch()
	wh_list = frappe.get_all("Warehouse", filters={"company": fc}, pluck="name") if fc else []
	if not wh_list:
		return []
	seen = set()
	out = []
	for sle in frappe.db.sql(
		"""
		select batch_no, item_code, sum(actual_qty) as qty, warehouse
		from `tabStock Ledger Entry`
		where is_cancelled = 0
		  and ifnull(batch_no,'') != ''
		  and item_code = %s
		  and warehouse in ({whs})
		group by batch_no, item_code, warehouse
		having sum(actual_qty) > 0.001
		order by batch_no asc
		limit 500
		""".format(whs=", ".join(["%s"] * len(wh_list))),
		tuple([ic] + wh_list),
		as_dict=1,
	):
		bn = _cstr(sle.get("batch_no"))
		if not bn or bn in seen or bn in reserved:
			continue
		seen.add(bn)
		out.append(
			{
				"batch_no": bn,
				"item_code": sle.item_code,
				"item_name": frappe.db.get_value("Item", ic, "item_name") or "",
				"qty": flt(sle.qty),
				"available_qty": flt(sle.qty),
				"warehouse": sle.warehouse,
				"party_code": party_code or "",
				"source": "other",
			}
		)
	return out


@frappe.whitelist()
def create_despatch_approval_request(from_company=None, lines=None):
	fc = _cstr(from_company)
	if not fc or not frappe.db.exists("Company", fc):
		frappe.throw(_("From company is required."))
	parsed = json.loads(lines) if isinstance(lines, str) else (lines or [])
	if not parsed:
		frappe.throw(_("Select at least one line with batch and qty."))

	doc = frappe.new_doc("Despatch Approval")
	doc.from_company = fc
	doc.status = "Pending Approval"
	doc.requested_by = frappe.session.user

	for line in parsed:
		ptr = _cstr(line.get("planning_table_row"))
		if ptr and not ptr.startswith("sprgrp:"):
			st = _resolved_planning_row_despatch_status(ptr, "")
			if _despatch_status_blocks_request(st):
				frappe.throw(
					_("Row {0} already has despatch status: {1}. Reject the approval to request again.").format(
						ptr, st
					)
				)
		bn = _cstr(line.get("batch_no"))
		if not bn:
			frappe.throw(_("Batch is required for each line."))
		spr = _primary_submitted_spr_for_batch(line.get("spr_name"), bn)
		if line.get("spr_name") and not spr:
			frappe.throw(_("SPR not submitted for row {0}.").format(ptr or bn))
		qty = flt(line.get("qty") or 0)
		nw = flt(line.get("net_weight") or qty)
		if qty <= 0:
			qty = nw or 1.0
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
				"net_weight": nw,
				"qty": qty,
				"uom": line.get("uom") or "Kg",
			},
		)
	doc.insert(ignore_permissions=True)
	_stamp_planning_rows_for_despatch_request(doc.name)
	frappe.db.commit()
	return {"ok": True, "name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_despatch_approvals(status_filter=None, limit=200, from_date=None, to_date=None, order_code=None):
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
		"Despatch Approval",
		filters=filters,
		fields=[
			"name",
			"from_company",
			"status",
			"owner",
			"modified",
			"delivery_note",
			"requested_by",
			"creation",
		],
		order_by="modified desc",
		limit_page_length=cint(limit) or 200,
	)
	if not rows:
		return rows
	names = [r.name for r in rows]
	line_rows = frappe.get_all(
		"Despatch Approval Line",
		filters={"parent": ["in", names]},
		fields=["parent", "party_code", "customer_name"],
		limit_page_length=0,
	) or []
	codes_by_parent = {}
	customers_by_parent = {}
	for ln in line_rows:
		pc = _cstr(ln.get("party_code")).strip()
		if pc:
			codes_by_parent.setdefault(ln.get("parent"), [])
			if pc not in codes_by_parent[ln.get("parent")]:
				codes_by_parent[ln.get("parent")].append(pc)
		cn = _cstr(ln.get("customer_name")).strip()
		if cn:
			customers_by_parent.setdefault(ln.get("parent"), [])
			if cn not in customers_by_parent[ln.get("parent")]:
				customers_by_parent[ln.get("parent")].append(cn)
	oc = _cstr(order_code).strip().lower()
	out = []
	for row in rows:
		codes = codes_by_parent.get(row.name, [])
		row["order_codes"] = codes
		row["order_codes_label"] = ", ".join(codes)
		row["customers_label"] = ", ".join(customers_by_parent.get(row.name, []))
		row["despatch_date"] = str(row.get("creation") or "")[:10]
		dn_name = _cstr(row.get("delivery_note"))
		row["dn_docstatus"] = 0
		if dn_name and frappe.db.exists("Delivery Note", dn_name):
			row["dn_docstatus"] = cint(frappe.db.get_value("Delivery Note", dn_name, "docstatus") or 0)
		if row.get("status") == "Approved" and row["dn_docstatus"] >= 1:
			row["card_status"] = "Despatched"
		elif row.get("status") == "Approved" and dn_name:
			row["card_status"] = "Draft DN"
		else:
			row["card_status"] = row.get("status")
		if oc and not any(oc in _cstr(c).lower() for c in codes):
			continue
		out.append(row)
	return out


@frappe.whitelist()
def get_despatch_approval_detail(name=None):
	if not name or not frappe.db.exists("Despatch Approval", name):
		frappe.throw(_("Despatch Approval not found."))
	doc = frappe.get_doc("Despatch Approval", name).as_dict()
	dn_name = _cstr(doc.get("delivery_note"))
	doc["dn_docstatus"] = 0
	if dn_name and frappe.db.exists("Delivery Note", dn_name):
		doc["dn_docstatus"] = cint(frappe.db.get_value("Delivery Note", dn_name, "docstatus") or 0)
	lines = doc.get("lines") or []
	codes = []
	customers = []
	items = set()
	batches = set()
	for ln in lines:
		pc = _cstr(ln.get("party_code"))
		if pc and pc not in codes:
			codes.append(pc)
		cn = _cstr(ln.get("customer_name"))
		if cn and cn not in customers:
			customers.append(cn)
		ic = _cstr(ln.get("item_code"))
		if ic:
			items.add(ic)
		bn = _cstr(ln.get("batch_no"))
		if bn:
			batches.add(bn)
	doc["order_codes_label"] = ", ".join(codes)
	doc["customers_label"] = ", ".join(customers)
	doc["item_count"] = len(items) or len(lines)
	doc["roll_count"] = len(batches) or len(lines)
	return doc


@frappe.whitelist()
def approve_despatch_approval(name=None):
	if not _user_can_approve_despatch():
		frappe.throw(_("You do not have permission to approve despatch."), frappe.PermissionError)
	if not name or not frappe.db.exists("Despatch Approval", name):
		frappe.throw(_("Despatch Approval not found."))
	da = frappe.get_doc("Despatch Approval", name)
	if da.status == "Approved":
		return {"ok": True, "name": name, "delivery_note": da.delivery_note}
	if da.status == "Rejected":
		frappe.throw(_("This despatch was rejected."))
	da.status = "Approved"
	da.approved_by = frappe.session.user
	da.save(ignore_permissions=True)
	_stamp_planning_rows_for_despatch_request(da.name)
	frappe.db.commit()
	return {"ok": True, "name": name, "delivery_note": da.delivery_note}


@frappe.whitelist()
def reject_despatch_approval(name=None):
	if not _user_can_approve_despatch():
		frappe.throw(_("You do not have permission to reject despatch."), frappe.PermissionError)
	da = frappe.get_doc("Despatch Approval", name)
	da.status = "Rejected"
	da.approved_by = frappe.session.user
	da.save(ignore_permissions=True)
	_stamp_planning_rows_for_despatch_request(da.name)
	frappe.db.commit()
	return {"ok": True, "name": name}


@frappe.whitelist()
def reorder_despatch_pending_queue(from_company=None, approval_names=None):
	"""Persist pending despatch approval priority (logistics kanban drag-and-drop)."""
	fc = _cstr(from_company)
	if not fc:
		frappe.throw(_("From company is required."))
	if isinstance(approval_names, str):
		try:
			approval_names = json.loads(approval_names)
		except Exception:
			approval_names = [s.strip() for s in approval_names.split(",") if s.strip()]
	updated = _apply_despatch_pending_queue(fc, approval_names or [])
	return {"updated": updated, "from_company": fc}


@frappe.whitelist()
def save_despatch_pending_arrangement(from_company=None, approval_names=None):
	"""Save pending despatch queue order and snapshot previous order for restore."""
	fc = _cstr(from_company)
	if not fc:
		frappe.throw(_("From company is required."))
	if isinstance(approval_names, str):
		try:
			approval_names = json.loads(approval_names)
		except Exception:
			approval_names = [s.strip() for s in approval_names.split(",") if s.strip()]
	names = [n for n in (approval_names or []) if _cstr(n)]
	current = _pending_approval_names_sorted(fc)
	if current:
		_save_despatch_pending_arrangement_history(
			fc,
			{"approval_names": current, "saved_at": _cstr(now_datetime())},
		)
	updated = _apply_despatch_pending_queue(fc, names)
	return {"updated": updated, "from_company": fc, "approval_names": names}


@frappe.whitelist()
def restore_despatch_pending_arrangement(from_company=None):
	"""Restore previous pending despatch queue snapshot."""
	fc = _cstr(from_company)
	if not fc:
		frappe.throw(_("From company is required."))
	history = _load_despatch_pending_arrangement_history(fc)
	if not history:
		frappe.throw(_("No previous arrangement to restore."))
	last = history.pop()
	frappe.defaults.set_global_default(
		_despatch_pending_arrangement_history_key(fc),
		json.dumps(history),
	)
	names = last.get("approval_names") or []
	updated = _apply_despatch_pending_queue(fc, names)
	return {"updated": updated, "from_company": fc, "approval_names": names}


def _despatch_approved_arrangement_history_key(from_company):
	return f"{DESPATCH_APPROVED_ARRANGEMENT_HISTORY_KEY}::{_cstr(from_company)}"


def _load_despatch_approved_arrangement_history(from_company):
	raw = frappe.defaults.get_global_default(_despatch_approved_arrangement_history_key(from_company)) or "[]"
	try:
		arr = json.loads(raw) if isinstance(raw, str) else (raw or [])
		return arr if isinstance(arr, list) else []
	except Exception:
		return []


def _save_despatch_approved_arrangement_history(from_company, snapshot):
	history = _load_despatch_approved_arrangement_history(from_company)
	history.append(snapshot)
	if len(history) > 20:
		history = history[-20:]
	frappe.defaults.set_global_default(
		_despatch_approved_arrangement_history_key(from_company),
		json.dumps(history),
	)


@frappe.whitelist()
def save_despatch_approved_arrangement(from_company=None, approval_names=None):
	"""Save approved despatch delivery queue order."""
	fc = _cstr(from_company)
	if not fc:
		frappe.throw(_("From company is required."))
	if isinstance(approval_names, str):
		try:
			approval_names = json.loads(approval_names)
		except Exception:
			approval_names = [s.strip() for s in approval_names.split(",") if s.strip()]
	names = [n for n in (approval_names or []) if _cstr(n)]
	current = _approved_approval_names_sorted(fc)
	if current:
		_save_despatch_approved_arrangement_history(
			fc,
			{"approval_names": current, "saved_at": _cstr(now_datetime())},
		)
	updated = _apply_despatch_approved_queue(fc, names)
	return {"updated": updated, "from_company": fc, "approval_names": names}


@frappe.whitelist()
def restore_despatch_approved_arrangement(from_company=None):
	fc = _cstr(from_company)
	if not fc:
		frappe.throw(_("From company is required."))
	history = _load_despatch_approved_arrangement_history(fc)
	if not history:
		frappe.throw(_("No previous arrangement to restore."))
	last = history.pop()
	frappe.defaults.set_global_default(
		_despatch_approved_arrangement_history_key(fc),
		json.dumps(history),
	)
	names = last.get("approval_names") or []
	updated = _apply_despatch_approved_queue(fc, names)
	return {"updated": updated, "from_company": fc, "approval_names": names}


@frappe.whitelist()
def reorder_despatch_approval_lines(name=None, line_names=None):
	if not name or not frappe.db.exists("Despatch Approval", name):
		frappe.throw(_("Despatch Approval not found."))
	da = frappe.get_doc("Despatch Approval", name)
	if da.status not in ("Pending Approval", "Draft"):
		frappe.throw(_("Only pending despatch can be reordered."))
	if isinstance(line_names, str):
		try:
			line_names = json.loads(line_names)
		except Exception:
			line_names = [x.strip() for x in line_names.split(",") if x.strip()]
	names = [n for n in (line_names or []) if _cstr(n)]
	if not names:
		return {"ok": True}
	by_name = {ln.name: ln for ln in (da.lines or [])}
	new_lines = []
	for nm in names:
		if nm in by_name:
			new_lines.append(by_name[nm])
	for ln in da.lines or []:
		if ln.name not in names:
			new_lines.append(ln)
	for i, ln in enumerate(new_lines, start=1):
		ln.idx = i
	da.lines = new_lines
	da.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "name": name}


@frappe.whitelist()
def prepare_delivery_note_from_despatch_approval(name=None):
	"""Return unsaved Delivery Note doc for desk form (operator saves manually)."""
	if not name or not frappe.db.exists("Despatch Approval", name):
		frappe.throw(_("Despatch Approval not found."))
	da = frappe.get_doc("Despatch Approval", name)
	if da.status != "Approved":
		frappe.throw(_("Despatch must be approved before creating Delivery Note."))
	if da.delivery_note and frappe.db.exists("Delivery Note", da.delivery_note):
		ds = cint(frappe.db.get_value("Delivery Note", da.delivery_note, "docstatus") or 0)
		return {
			"ok": True,
			"mode": "existing",
			"delivery_note": da.delivery_note,
			"docstatus": ds,
		}
	from production_entry.production_planning.despatch_delivery import build_delivery_note_from_despatch

	dn = build_delivery_note_from_despatch(da)
	return {"ok": True, "mode": "new", "doc": dn.as_dict(), "despatch_approval": da.name}


@frappe.whitelist()
def link_delivery_note_to_despatch(despatch_approval=None, delivery_note=None):
	"""Link saved Delivery Note back to Despatch Approval."""
	da_name = _cstr(despatch_approval)
	dn_name = _cstr(delivery_note)
	if not da_name or not frappe.db.exists("Despatch Approval", da_name):
		frappe.throw(_("Despatch Approval not found."))
	if not dn_name or not frappe.db.exists("Delivery Note", dn_name):
		frappe.throw(_("Delivery Note not found."))
	cur = _cstr(frappe.db.get_value("Despatch Approval", da_name, "delivery_note"))
	if cur and cur != dn_name and frappe.db.exists("Delivery Note", cur):
		frappe.throw(_("Despatch Approval already linked to {0}.").format(cur))
	frappe.db.set_value("Despatch Approval", da_name, "delivery_note", dn_name, update_modified=True)
	frappe.db.commit()
	return {"ok": True, "despatch_approval": da_name, "delivery_note": dn_name}


@frappe.whitelist()
def create_delivery_note_from_despatch_approval(name=None):
	"""Legacy alias — opens existing DN or returns unsaved doc (no auto-insert)."""
	return prepare_delivery_note_from_despatch_approval(name)
