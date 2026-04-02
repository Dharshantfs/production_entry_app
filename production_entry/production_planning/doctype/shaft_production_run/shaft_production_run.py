import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
	extract_quality_and_color,
)


def batch_shift_value(shift: str | None) -> str:
	if not shift:
		return ""
	if "night" in shift.lower():
		return "Night"
	if "day" in shift.lower():
		return "Day"
	return shift


class ShaftProductionRun(Document):
	def validate(self):
		self.sync_cloud_field_aliases()
		self.calculate_item_weights()
		self.generate_batch_numbers()

	def sync_cloud_field_aliases(self):
		"""Align legacy cloud column names (Frappe Cloud DB) with current app field names."""
		if self.get("custom_customer") and not self.customer:
			self.customer = self.custom_customer
		elif self.customer and not self.get("custom_customer"):
			self.custom_customer = self.customer
		if self.operator and not self.get("custom_operator"):
			self.custom_operator = self.operator
		elif self.get("custom_operator") and not self.operator:
			self.operator = self.custom_operator
		if self.supervisor and not self.get("custom_supervisor"):
			self.custom_supervisor = self.supervisor
		elif self.get("custom_supervisor") and not self.supervisor:
			self.supervisor = self.custom_supervisor

		planned_sum = 0.0
		achieved = 0.0
		for row in self.items or []:
			if row.get("work_order") and not row.wo_id:
				row.wo_id = row.work_order
			elif row.wo_id and not row.get("work_order"):
				row.work_order = row.wo_id
			if row.get("job") and not row.job_no:
				row.job_no = row.job
			elif row.job_no and not row.get("job"):
				row.job = row.job_no
			mpr = flt(row.meter_per_roll)
			mroll = flt(row.meter_roll)
			if mpr <= 0 and mroll > 0:
				row.meter_per_roll = mroll
			elif mpr > 0 and mroll <= 0:
				row.meter_roll = mpr
			wi = flt(row.width_inches)
			wic = flt(row.width_inch)
			if wi <= 0 and wic > 0:
				row.width_inches = wic
			elif wi > 0 and wic <= 0:
				row.width_inch = wi
			planned_sum += flt(row.planned_qty)
			gw = flt(row.gross_weight)
			nw = flt(row.net_weight)
			achieved += gw if gw > 0 else nw
		for job in self.jobs or []:
			if job.get("job_id") and not job.job_no:
				job.job_no = job.job_id
			elif job.job_no and not job.get("job_id"):
				job.job_id = job.job_no
		self.custom_total_planned_qty = planned_sum
		self.custom_total_achieved_weight = achieved
		self.total_produced_weight = achieved

	def on_submit(self):
		self.sync_batch_custom_fields()
		self.create_manufacturing_stock_entries()
		self.update_work_order_statuses()

	def on_cancel(self):
		self.cancel_manufacturing_stock_entries()

	def calculate_item_weights(self):
		"""Net weight (kg) = GSM × width(m) × meter/roll / 1000 — same as Roll Production Entry."""
		for row in self.items or []:
			gsm_val = flt(row.gsm) or flt(row.get("custom_production_gsm"))
			w_in = flt(row.width_inches) or flt(row.get("width_inch"))
			m_roll = flt(row.meter_per_roll) or flt(row.get("meter_roll"))
			if gsm_val and w_in and m_roll:
				width_m = w_in * 0.0254
				row.net_weight = round(gsm_val * width_m * m_roll / 1000, 3)
				if not row.width_inches:
					row.width_inches = w_in
				if not row.meter_per_roll:
					row.meter_per_roll = m_roll
				cpg = flt(row.get("custom_production_gsm"))
				if not row.gsm and cpg > 0:
					row.gsm = int(cpg)

	def _unit_digit(self) -> int:
		u = (self.get("custom_unit") or "").strip()
		if not u:
			return 0
		m = re.search(r"(\d+)", u)
		return int(m.group(1)) if m else 0

	def generate_batch_numbers(self):
		"""Assign batch IDs as MMUYY{S}/N using shared series for this date/shift/unit."""
		if not self.run_date or not self.get("custom_unit") or not self.shift:
			return
		rows = [r for r in (self.items or []) if r.item_code]
		if not rows:
			return
		rd = getdate(self.run_date)
		unit_d = self._unit_digit()
		root_5 = f"{rd.month:02d}{unit_d}{rd.year % 100:02d}"
		series_prefix = self._resolve_series_prefix(root_5)
		next_roll = self._next_roll_starting(series_prefix)
		for row in rows:
			if row.batch_no:
				continue
			row.batch_no = f"{series_prefix}/{next_roll}"
			row.roll_no = str(next_roll)
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
		pref = batch_id.split("/")[0].strip()
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
		for row in self.items or []:
			if not row.batch_no or not frappe.db.exists("Batch", row.batch_no):
				continue
			data = {}
			if row.get("gross_weight") is not None:
				data["custom_gross_weight"] = flt(row.gross_weight)
			if row.get("custom_cbm") is not None:
				data["custom_cbm"] = flt(row.custom_cbm)
			if row.get("custom_diameter") is not None:
				data["custom_diameter"] = flt(row.custom_diameter)
			if row.get("custom_shift"):
				data["custom_shift"] = row.custom_shift
			if row.get("custom_party_code_text"):
				data["custom_party_code_text"] = row.custom_party_code_text
			if not data:
				continue
			try:
				frappe.db.set_value("Batch", row.batch_no, data)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "SPR Batch sync skipped")

	def _row_fg_qty(self, row) -> float:
		qty = flt(row.net_weight)
		if qty <= 0:
			qty = flt(row.gross_weight)
		return qty

	def _set_stock_entry_spr_link(self, se):
		meta = frappe.get_meta("Stock Entry")
		if meta.has_field("shaft_production_run"):
			se.shaft_production_run = self.name

	def create_manufacturing_stock_entries(self):
		"""One Stock Entry (Manufacture) per Work Order, same pattern as Roll Production Entry."""
		wo_groups = {}
		for row in self.items or []:
			if not row.wo_id:
				continue
			wo_groups.setdefault(row.wo_id, []).append(row)

		created_entries = []

		for wo_id, rows in wo_groups.items():
			wo_doc = frappe.get_doc("Work Order", wo_id)
			total_qty = sum(self._row_fg_qty(r) for r in rows)

			if total_qty <= 0:
				frappe.msgprint(_("Skipping WO {0} — net/gross weight is 0").format(wo_id), alert=True)
				continue

			se = frappe.new_doc("Stock Entry")
			se.stock_entry_type = "Manufacture"
			se.work_order = wo_id
			se.production_item = wo_doc.production_item
			se.fg_completed_qty = total_qty
			se.from_bom = 1
			se.bom_no = wo_doc.bom_no
			se.use_multi_level_bom = wo_doc.use_multi_level_bom
			se.wip_warehouse = wo_doc.wip_warehouse
			se.to_warehouse = wo_doc.fg_warehouse

			self._set_stock_entry_spr_link(se)

			for row in rows:
				se.append(
					"items",
					{
						"item_code": row.item_code,
						"item_name": row.item_name,
						"qty": self._row_fg_qty(row),
						"uom": "Kg",
						"batch_no": row.batch_no,
						"serial_no": row.roll_no,
						"t_warehouse": wo_doc.fg_warehouse,
						"is_finished_item": 1,
					},
				)

			se.get_items()

			se.insert()
			se.submit()
			created_entries.append(se.name)

			frappe.msgprint(
				_("Manufacturing Entry {0} created for WO {1}").format(se.name, wo_id),
				alert=True,
			)

		if created_entries:
			self.db_set("manufacturing_entries", ", ".join(created_entries))
			frappe.msgprint(
				_("Created {0} Manufacturing Entries: {1}").format(
					len(created_entries), ", ".join(created_entries)
				)
			)

	def update_work_order_statuses(self):
		wo_ids = list({row.wo_id for row in (self.items or []) if row.wo_id})
		for wo_id in wo_ids:
			wo_doc = frappe.get_doc("Work Order", wo_id)
			total_produced = frappe.db.sql(
				"""
				SELECT IFNULL(SUM(fg_completed_qty), 0)
				FROM `tabStock Entry`
				WHERE work_order = %s
				  AND stock_entry_type = 'Manufacture'
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
				"stock_entry_type = 'Manufacture'",
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
	out = {
		"customer": pp.get("customer"),
		"custom_unit": pp.get("custom_unit"),
	}
	if pp.get("sales_order"):
		so = frappe.db.get_value(
			"Sales Order", pp.sales_order, ["customer", "transaction_date"], as_dict=True
		)
		if so:
			out["customer"] = out["customer"] or so.customer
	return out


@frappe.whitelist()
def get_job_rows_for_production_plan(production_plan):
	if not production_plan:
		return []
	if not frappe.db.exists("Production Plan", production_plan):
		frappe.throw(_("Production Plan {0} not found").format(production_plan))
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
	return [{"job_no": r.job_no, "total_weight": flt(r.total_weight)} for r in rows]


def get_planning_sheet_item_for_wo(wo_name: str) -> dict:
	"""Match Planning Sheet Item row saved against this Work Order (from Planning Sheet submit)."""
	if not wo_name:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT so_item, unit, dot_spec, gsm, meter, meter_per_roll, no_of_rolls,
			weight_per_roll, width_inch, quality, color, warehouse, allocated_to_unit
		FROM `tabPlanning Sheet Item`
		WHERE work_order = %(wo)s
		ORDER BY modified DESC
		LIMIT 1
		""",
		{"wo": wo_name},
		as_dict=True,
	)
	return rows[0] if rows else {}


def _merge_planning_sheet_item_line(base: dict, ctx: dict) -> None:
	if not ctx:
		return
	if ctx.get("quality"):
		base["quality"] = ctx["quality"]
	if ctx.get("color"):
		base["color"] = ctx["color"]
	if ctx.get("gsm") not in (None, ""):
		try:
			base["gsm"] = int(ctx["gsm"])
		except (TypeError, ValueError):
			pass
	if ctx.get("width_inch") is not None:
		w = flt(ctx["width_inch"])
		base["width_inches"] = w
		base["width_inch"] = w
	if ctx.get("so_item"):
		base["so_item"] = ctx["so_item"]
	if ctx.get("unit"):
		base["unit"] = ctx["unit"]
	if ctx.get("dot_spec"):
		base["dot_spec"] = ctx["dot_spec"]
	if ctx.get("meter") is not None:
		base["meter"] = ctx["meter"]
	if ctx.get("meter_per_roll") is not None:
		mp = flt(ctx["meter_per_roll"])
		base["meter_per_roll"] = mp
		base["meter_roll"] = mp
	if ctx.get("no_of_rolls") is not None:
		base["no_of_rolls"] = ctx["no_of_rolls"]
	if ctx.get("weight_per_roll") is not None:
		base["weight_per_roll"] = flt(ctx["weight_per_roll"])
	if ctx.get("warehouse"):
		base["warehouse"] = ctx["warehouse"]
	if ctx.get("allocated_to_unit"):
		base["allocated_to_unit"] = ctx["allocated_to_unit"]


def _build_roll_items_from_spr(spr_doc, pp_name):
	items = []
	for job in spr_doc.jobs or []:
		job_no = job.job_no
		shaft_combination = get_shaft_combination(pp_name, job_no)
		for wo in get_work_orders_for_job(pp_name, job_no):
			wo_doc = frappe.get_doc("Work Order", wo["name"])
			item_code = wo_doc.production_item
			item_name = frappe.db.get_value("Item", item_code, "item_name") or ""
			gsm, width_inch = parse_item_code(item_code)
			quality, color = extract_quality_and_color(item_name)
			wo_planned = flt(wo.get("planned_qty"))
			ctx = get_planning_sheet_item_for_wo(wo["name"])
			row = {
				"job_no": job_no,
				"shaft_combination": shaft_combination,
				"planned_qty": wo_planned,
				"wo_id": wo["name"],
				"item_code": item_code,
				"item_name": item_name,
				"quality": quality,
				"color": color,
				"gsm": gsm,
				"width_inches": width_inch,
				"order_code": get_order_code(wo_doc),
				"batch_no": "",
				"roll_no": "",
				"meter_per_roll": 0,
				"net_weight": 0,
				"gross_weight": 0,
			}
			_merge_planning_sheet_item_line(row, ctx)
			items.append(row)
	return items


@frappe.whitelist()
def get_item_rows_for_production_plan(production_plan):
	"""Build Shaft Production Run Item rows from WO for each job on this PP (draft/new forms)."""
	if not production_plan:
		return []
	jobs = get_job_rows_for_production_plan(production_plan)
	spr = frappe._dict(jobs=[])
	for j in jobs:
		spr.jobs.append(frappe._dict(job_no=j["job_no"], total_weight=j.get("total_weight")))
	return _build_roll_items_from_spr(spr, production_plan)


@frappe.whitelist()
def get_or_create_roll_entry(shaft_production_run):
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
	return ""


def get_work_orders_for_job(pp_name, job_no):
	return frappe.db.sql(
		"""
		SELECT wo.name, wo.production_item, wo.qty as planned_qty, wo.produced_qty, wo.status
		FROM `tabWork Order` wo
		WHERE wo.production_plan = %(pp_name)s
		  AND wo.production_plan_item = %(job_no)s
		  AND wo.docstatus != 2
		ORDER BY wo.name
		""",
		{"pp_name": pp_name, "job_no": job_no},
		as_dict=True,
	)


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


def get_order_code(wo_doc):
	return getattr(wo_doc, "order_code", None) or getattr(wo_doc, "sales_order", None) or ""
