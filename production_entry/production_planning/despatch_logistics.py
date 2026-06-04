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
	_row_matches_filters,
	_transfer_row_unit_is_unassigned,
	_user_can_approve_transfer,
	get_logistics_companies,
	get_spr_produced_batches,
)

DESPATCH_APPROVER_ROLES = frozenset({"System Manager", "Manufacturing Manager", "Administrator"})


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
		approvals = frappe.get_all(
			"Despatch Approval",
			filters=filters,
			fields=["name", "status", "delivery_note", "modified", "creation"],
			order_by="modified desc",
			limit_page_length=80,
		)
		enriched = []
		for da in approvals or []:
			lines = frappe.get_all(
				"Despatch Approval Line",
				filters={"parent": da.name},
				fields=["party_code", "customer_name", "qty"],
				limit_page_length=200,
			)
			codes = []
			for ln in lines:
				pc = _cstr(ln.get("party_code"))
				if pc and pc not in codes:
					codes.append(pc)
			if oc and not any(oc in _cstr(x).lower() for x in codes):
				continue
			total_qty = sum(flt(ln.get("qty")) for ln in lines)
			enriched.append(
				{
					"name": da.name,
					"status": da.status,
					"delivery_note": da.delivery_note,
					"order_codes_label": ", ".join(codes),
					"qty_total": total_qty,
					"creation": da.creation,
				}
			)
		pending = [a for a in enriched if a["status"] in ("Pending Approval", "Draft")]
		approved = [a for a in enriched if a["status"] == "Approved" and not a.get("delivery_note")]
		out.append(
			{
				"company": name,
				"label": name,
				"pending_approvals": pending,
				"approved_ready_dn": approved,
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
):
	"""Planning rows with movement Despatch and submitted SPR."""
	kwargs = _chart_fetch_kwargs(view_scope, date, week, month, board_kind)
	try:
		raw = get_color_chart_data(**kwargs)
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
		can = bool(spr and spr_ds == 1)
		block = ""
		if not spr:
			block = _("No SPR linked")
		elif spr_ds != 1:
			block = _("SPR must be submitted")
		out.append(
			{
				"planning_table_row": r.get("itemName") or r.get("name"),
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
				"movement_type": mt,
			}
		)
	return out


@frappe.whitelist()
def get_despatch_spr_batches(spr_name=None, item_code=None, party_code=None, from_company=None):
	"""Produced batches from submitted SPR (same as transfer)."""
	return get_spr_produced_batches(spr_name, item_code, party_code, from_company)


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
		bn = _cstr(line.get("batch_no"))
		if not bn:
			frappe.throw(_("Batch is required for each line."))
		spr = _cstr(line.get("spr_name"))
		if spr and cint(frappe.db.get_value("Shaft Production Run", spr, "docstatus") or 0) != 1:
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
		if oc and not any(oc in _cstr(c).lower() for c in codes):
			continue
		out.append(row)
	return out


@frappe.whitelist()
def get_despatch_approval_detail(name=None):
	if not name or not frappe.db.exists("Despatch Approval", name):
		frappe.throw(_("Despatch Approval not found."))
	return frappe.get_doc("Despatch Approval", name).as_dict()


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
	frappe.db.commit()
	return {"ok": True, "name": name}


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
def create_delivery_note_from_despatch_approval(name=None):
	"""Create draft Delivery Note after despatch approval (operator action)."""
	if not name or not frappe.db.exists("Despatch Approval", name):
		frappe.throw(_("Despatch Approval not found."))
	da = frappe.get_doc("Despatch Approval", name)
	if da.status != "Approved":
		frappe.throw(_("Despatch must be approved before creating Delivery Note."))
	if da.delivery_note and frappe.db.exists("Delivery Note", da.delivery_note):
		return {"ok": True, "delivery_note": da.delivery_note}

	from production_entry.production_planning.despatch_delivery import make_delivery_note_from_despatch

	dn_name = make_delivery_note_from_despatch(da)
	da.delivery_note = dn_name
	da.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "delivery_note": dn_name}
