# -*- coding: utf-8 -*-
"""Work Order Start Production: pick fabric roll batches; auto-transfer PP and other RM."""

from __future__ import annotations

import frappe
from frappe.utils import flt

MANUAL_FG_PROCESSES = ("102", "103", "104", "105", "106", "107", "109", "251", "252")


def is_fabric_roll_item_code(item_code: str) -> bool:
	"""True only for process-100 fabric rolls (e.g. 1001030011001615), not PP / filler / dana."""
	ic = str(item_code or "").strip().upper()
	if not ic:
		return False
	head = ic.split(" - ", 1)[0].strip()
	if head in ("PP", "FL", "MB", "PPA") or ic.startswith("PP") or ic.startswith("FL") or "DANA" in ic:
		return False
	if not ic.startswith("100") or ic.startswith("1000"):
		return False
	digits = "".join(ch for ch in ic if ch.isdigit())
	if len(digits) >= 15:
		return True
	return len(ic) >= 9 and ic[:9].isdigit()


def fg_item_process_code(item_code: str) -> str:
	raw = str(item_code or "").strip().upper()
	if not raw:
		return ""
	if "-" in raw:
		parts = raw.split("-", 1)
		tail = parts[1] if len(parts) > 1 else ""
		tail_digits = "".join(ch for ch in tail if ch.isdigit())
		if len(tail_digits) >= 3:
			return tail_digits[:3]
	digits = "".join(ch for ch in raw if ch.isdigit())
	return digits[:3] if len(digits) >= 3 else ""


def fg_needs_manual_fabric_picks(production_item: str) -> bool:
	return fg_item_process_code(production_item) in MANUAL_FG_PROCESSES


def _is_finished_goods_warehouse(name: str) -> bool:
	low = str(name or "").strip().lower()
	return "finished good" in low or "fg warehouse" in low


def source_warehouse_for_row(wo, row, fabric: bool) -> str:
	src = str(getattr(row, "source_warehouse", None) or wo.source_warehouse or "").strip()
	if fabric or not _is_finished_goods_warehouse(src):
		return src
	company = str(wo.company or "").strip()
	suffix = src.rsplit(" - ", 1)[-1].strip() if " - " in src else ""
	try:
		from production_entry.production_planning.spr_unit_warehouses import _company_rm_warehouse

		rm = _company_rm_warehouse(company, str(wo.wip_warehouse or ""), suffix)
		if rm:
			return rm
	except Exception:
		pass
	return src


def _meta_first_field(meta, names):
	for fn in names:
		if meta.has_field(fn):
			return fn
	return ""


def _sle_has_bundle_link() -> bool:
	try:
		return bool(frappe.get_meta("Stock Ledger Entry").has_field("serial_and_batch_bundle"))
	except Exception:
		return False


def get_total_qty(item_code, warehouse) -> float:
	qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
	return flt(qty or 0)


def batch_qty_classic_sle(item_code, batch_no, warehouse) -> float:
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(actual_qty), 0)
		FROM `tabStock Ledger Entry`
		WHERE IFNULL(is_cancelled, 0) = 0
		  AND item_code = %s AND warehouse = %s AND IFNULL(batch_no, '') = %s
		""",
		(item_code, warehouse, batch_no),
	)
	return flt((row and row[0] and row[0][0]) or 0)


def batch_qty_bundle_sle(item_code, batch_no, warehouse) -> float:
	if not _sle_has_bundle_link() or not frappe.db.exists("DocType", "Serial and Batch Entry"):
		return 0.0
	try:
		meta = frappe.get_meta("Serial and Batch Entry")
		batch_field = _meta_first_field(meta, ("batch_no", "batch", "batch_id"))
		qty_field = _meta_first_field(meta, ("qty", "quantity"))
		if not batch_field or not qty_field:
			return 0.0
		rows = frappe.db.sql(
			f"""
			SELECT SUM(
				CASE WHEN IFNULL(sle.actual_qty, 0) < 0
					THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
					ELSE ABS(IFNULL(sbe.`{qty_field}`, 0)) END
			) AS q
			FROM `tabStock Ledger Entry` sle
			INNER JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
			WHERE IFNULL(sle.is_cancelled, 0) = 0
			  AND IFNULL(sle.item_code, '') = %s
			  AND IFNULL(sle.warehouse, '') = %s
			  AND IFNULL(sle.serial_and_batch_bundle, '') != ''
			  AND IFNULL(sbe.`{batch_field}`, '') = %s
			""",
			(item_code, warehouse, batch_no),
		)
		return flt((rows and rows[0] and rows[0][0]) or 0)
	except Exception:
		return 0.0


def get_batch_qty_in_warehouse(item_code, batch_no, warehouse) -> float:
	if not item_code or not batch_no or not warehouse:
		return 0.0
	return max(
		batch_qty_classic_sle(item_code, batch_no, warehouse),
		batch_qty_bundle_sle(item_code, batch_no, warehouse),
	)


def get_batches_from_ledger(item_code, warehouse):
	acc = {}
	for r in frappe.db.sql(
		"""
		SELECT batch_no, SUM(actual_qty) AS qty
		FROM `tabStock Ledger Entry`
		WHERE IFNULL(is_cancelled, 0) = 0
		  AND item_code = %s AND warehouse = %s AND IFNULL(batch_no, '') != ''
		GROUP BY batch_no
		HAVING SUM(actual_qty) > 0
		""",
		(item_code, warehouse),
		as_dict=True,
	):
		bn = str(r.get("batch_no") or "").strip()
		q = flt(r.get("qty") or 0)
		if bn and q > 0:
			acc[bn] = acc.get(bn, 0.0) + q

	if _sle_has_bundle_link() and frappe.db.exists("DocType", "Serial and Batch Entry"):
		try:
			meta = frappe.get_meta("Serial and Batch Entry")
			batch_field = _meta_first_field(meta, ("batch_no", "batch", "batch_id"))
			qty_field = _meta_first_field(meta, ("qty", "quantity"))
			if batch_field and qty_field:
				rows = frappe.db.sql(
					f"""
					SELECT sbe.`{batch_field}` AS batch_no,
						SUM(CASE WHEN IFNULL(sle.actual_qty, 0) < 0
							THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
							ELSE ABS(IFNULL(sbe.`{qty_field}`, 0)) END) AS qty
					FROM `tabStock Ledger Entry` sle
					INNER JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
					WHERE IFNULL(sle.is_cancelled, 0) = 0
					  AND IFNULL(sle.item_code, '') = %s
					  AND IFNULL(sle.warehouse, '') = %s
					  AND IFNULL(sle.serial_and_batch_bundle, '') != ''
					  AND IFNULL(sbe.`{batch_field}`, '') != ''
					GROUP BY sbe.`{batch_field}`
					HAVING SUM(CASE WHEN IFNULL(sle.actual_qty, 0) < 0
						THEN -ABS(IFNULL(sbe.`{qty_field}`, 0))
						ELSE ABS(IFNULL(sbe.`{qty_field}`, 0)) END) > 0
					""",
					(item_code, warehouse),
					as_dict=True,
				)
				for r in rows or []:
					bn = str(r.get("batch_no") or "").strip()
					q = flt(r.get("qty") or 0)
					if bn and q > 0:
						acc[bn] = max(acc.get(bn, 0.0), q)
		except Exception:
			pass

	out = [{"batch_no": k, "qty": flt(v)} for k, v in acc.items()]
	out.sort(key=lambda r: flt(r.get("qty") or 0), reverse=True)
	return out


def parse_fabric_batch_picks(raw):
	if raw is None:
		return []
	if isinstance(raw, (list, tuple)):
		return [p for p in raw if p]
	if isinstance(raw, dict):
		return [raw] if raw else []
	s = str(raw).strip()
	if not s:
		return []
	try:
		data = frappe.parse_json(s)
	except Exception:
		return []
	if isinstance(data, list):
		return data
	if isinstance(data, dict):
		return [data]
	return []


def extract_fabric_picks(kwargs=None):
	fd = dict(frappe.form_dict or {})
	if kwargs:
		fd.update(kwargs)
	for key in (
		"fabric_batch_picks",
		"fabric_picks_json",
		"fbp",
		"fabric_batch_picks_list",
	):
		out = parse_fabric_batch_picks(fd.get(key))
		if out:
			return out
	env = fd.get("wo_transfer_payload")
	if env:
		try:
			ed = frappe.parse_json(str(env).strip())
			if isinstance(ed, dict):
				out = parse_fabric_batch_picks(ed.get("fabric_batch_picks"))
				if out:
					return out
		except Exception:
			pass
	return []


def picks_pool_for_item(picks_list, item_code):
	target = str(item_code or "").strip()
	out = []
	for p in picks_list or []:
		if not isinstance(p, dict):
			try:
				p = frappe.parse_json(str(p))
			except Exception:
				continue
		if str(p.get("item_code") or "").strip() != target:
			continue
		bn = str(p.get("batch_no") or "").strip()
		q = flt(p.get("qty"))
		if bn and q > 0:
			out.append({"batch_no": bn, "qty": q})
	return out


def wo_rm_transferred_qty_by_item(wo_name):
	rows = (
		frappe.db.sql(
			"""
			SELECT sed.item_code, SUM(ABS(COALESCE(sed.qty, 0))) AS qty
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.docstatus = 1
			  AND IFNULL(se.work_order, '') = %s
			  AND se.purpose = 'Material Transfer for Manufacture'
			  AND IFNULL(sed.t_warehouse, '') != ''
			GROUP BY sed.item_code
			""",
			(str(wo_name),),
			as_dict=True,
		)
		or []
	)
	acc = {}
	for r in rows:
		ic = str(r.get("item_code") or "").strip()
		if ic:
			acc[ic] = flt(r.get("qty") or 0)
	return acc


def wo_any_rm_remaining(wo, rm_map) -> bool:
	for row in wo.required_items or []:
		req = flt(row.required_qty)
		ic = str(row.item_code or "").strip()
		if req <= 0 or not ic:
			continue
		if flt((rm_map or {}).get(ic) or 0) + 1e-9 < req:
			return True
	return False


def wo_recompute_material_transferred_field(wo):
	rm_map = wo_rm_transferred_qty_by_item(wo.name)
	wo_qty = flt(wo.qty) or 0.0
	if wo_qty <= 0:
		wo.db_set("material_transferred_for_manufacturing", 0)
		return 0.0
	ratios = []
	for row in wo.required_items or []:
		req = flt(row.required_qty)
		ic = str(row.item_code or "").strip()
		if req <= 0 or not ic:
			continue
		tr = flt(rm_map.get(ic) or 0.0)
		ratios.append(tr / req if req else 1.0)
	cov = wo_qty * (min(ratios) if ratios else 1.0)
	cov = max(0.0, min(cov, wo_qty))
	wo.db_set("material_transferred_for_manufacturing", cov)
	return cov


def wo_has_fabric_batch_rm(wo) -> bool:
	for row in wo.required_items or []:
		ic = str(row.item_code or "").strip()
		if not is_fabric_roll_item_code(ic) or flt(row.required_qty or 0) <= 0:
			continue
		try:
			if frappe.db.get_value("Item", ic, "has_batch_no"):
				return True
		except Exception:
			pass
	return False


def _append_se_item(se, wo, item_code, source_wh, qty, stock_uom, batch_no=None):
	row = {
		"item_code": item_code,
		"s_warehouse": source_wh,
		"t_warehouse": wo.wip_warehouse,
		"qty": qty,
		"transfer_qty": qty,
		"uom": stock_uom,
		"stock_uom": stock_uom,
		"conversion_factor": 1,
	}
	if batch_no:
		row["batch_no"] = batch_no
		row["use_serial_batch_fields"] = 1
	se.append("items", row)


@frappe.whitelist()
def auto_material_transfer(work_order=None, fabric_batch_picks=None, **kwargs):
	"""Transfer remaining BOM qty to WIP. Fabric rolls use picked batches; PP/other RM auto-FIFO from RM store."""
	wo_id = work_order or frappe.form_dict.get("work_order") or frappe.form_dict.get("wo_id")
	if not wo_id:
		frappe.throw("Work Order Missing")

	wo = frappe.get_doc("Work Order", wo_id)
	if wo.docstatus != 1:
		frappe.throw("Submit Work Order First")

	had_actual_start = bool(wo.actual_start_date)
	rm_map = wo_rm_transferred_qty_by_item(wo.name)
	if not wo_any_rm_remaining(wo, rm_map):
		wo_recompute_material_transferred_field(wo)
		wo.db_set("status", "In Process")
		return {
			"success": True,
			"message": (
				"All BOM materials for this Work Order are already transferred to WIP. "
				"Use Finish Production when output is complete."
			),
		}

	kwargs = dict(kwargs or {})
	if fabric_batch_picks is not None:
		kwargs["fabric_batch_picks"] = fabric_batch_picks
	fabric_picks = extract_fabric_picks(kwargs)
	fg_manual = fg_needs_manual_fabric_picks(wo.production_item)
	if fg_manual and not fabric_picks and wo_has_fabric_batch_rm(wo):
		# Still allow start when only non-fabric RM remains.
		need_fabric = False
		for row in wo.required_items or []:
			ic = str(row.item_code or "").strip()
			if not is_fabric_roll_item_code(ic):
				continue
			req = flt(row.required_qty)
			already = flt(rm_map.get(ic) or 0)
			if req - already > 1e-9:
				need_fabric = True
				break
		if need_fabric:
			frappe.throw(
				"Select fabric roll batches, then Start Transfer. "
				"PP and other raw materials are transferred automatically."
			)
		fg_manual = False

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer for Manufacture"
	se.purpose = "Material Transfer for Manufacture"
	se.company = wo.company
	se.work_order = wo.name
	se.to_warehouse = wo.wip_warehouse
	se.use_serial_batch_fields = 1

	items_added = False
	batch_reserved = {}

	for row in wo.required_items:
		item_code = str(row.item_code or "").strip()
		if not item_code:
			continue
		req_qty = flt(row.required_qty)
		if req_qty <= 0:
			continue
		already = flt(rm_map.get(item_code) or 0.0)
		remaining = max(0.0, req_qty - already)
		if remaining <= 1e-9:
			continue

		fabric = is_fabric_roll_item_code(item_code)
		source_wh = source_warehouse_for_row(wo, row, fabric)
		has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")

		if not has_batch:
			avail = get_total_qty(item_code, source_wh)
			if avail < remaining:
				frappe.throw(
					f"{item_code} need remaining {flt(remaining, 4)} available {avail} in {source_wh}"
				)
			xfer = min(remaining, avail)
			_append_se_item(se, wo, item_code, source_wh, xfer, row.stock_uom)
			items_added = True
			continue

		total = get_total_qty(item_code, source_wh)
		if total < remaining:
			frappe.throw(
				f"{item_code} need remaining {flt(remaining, 4)} stock {total} in {source_wh}"
			)

		use_manual_fabric = fg_manual and fabric
		if use_manual_fabric:
			pool = picks_pool_for_item(fabric_picks, item_code)
			if not pool:
				frappe.throw(
					f"Select batches for fabric item {item_code}. PP and other RM transfer automatically."
				)
			allocated = 0.0
			for pick in pool:
				bn = pick["batch_no"]
				max_from_pick = flt(pick["qty"])
				rk = (item_code, source_wh, bn)
				ledger_bal = get_batch_qty_in_warehouse(item_code, bn, source_wh)
				used_here = flt(batch_reserved.get(rk) or 0)
				wh_avail = max(0.0, ledger_bal - used_here)
				use_qty = min(max_from_pick, wh_avail)
				if use_qty <= 0:
					continue
				_append_se_item(se, wo, item_code, source_wh, use_qty, row.stock_uom, bn)
				allocated += use_qty
				batch_reserved[rk] = used_here + use_qty
				items_added = True
			if allocated + 1e-9 < remaining:
				frappe.throw(
					f"{item_code}: fabric picks cover {flt(allocated, 4)} but remaining BOM need is "
					f"{flt(remaining, 4)} in {source_wh}."
				)
			continue

		pending = remaining
		if has_batch:
			for b in get_batches_from_ledger(item_code, source_wh):
				if pending <= 0:
					break
				bn = b.get("batch_no")
				wh_avail = get_batch_qty_in_warehouse(item_code, bn, source_wh)
				if wh_avail <= 0:
					continue
				use_qty = min(wh_avail, pending)
				_append_se_item(se, wo, item_code, source_wh, use_qty, row.stock_uom, bn)
				pending -= use_qty
				items_added = True
			if pending > 1e-6:
				frappe.throw(f"{item_code} pending batch qty {flt(pending, 4)} in {source_wh}")
		else:
			xfer = min(remaining, get_total_qty(item_code, source_wh))
			_append_se_item(se, wo, item_code, source_wh, xfer, row.stock_uom)
			items_added = True

	if not items_added:
		frappe.throw("No materials left to transfer for this Work Order (all lines already satisfied in WIP).")

	se.insert(ignore_permissions=True)
	se.submit()
	frappe.db.commit()

	wo.reload()
	wo_recompute_material_transferred_field(wo)
	wo.reload()
	wo.db_set("status", "In Process")
	if not had_actual_start:
		wo.db_set("actual_start_date", frappe.utils.now_datetime())

	return {"success": True, "message": f"Material transferred : {se.name}"}
