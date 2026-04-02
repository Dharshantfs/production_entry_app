import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


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
		self.generate_batch_numbers()

	def on_submit(self):
		self.sync_batch_custom_fields()

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


@frappe.whitelist()
def get_production_plan_details(production_plan):
	"""Fill header fields from Production Plan."""
	if not production_plan or not frappe.db.exists("Production Plan", production_plan):
		return {}
	pp = frappe.get_doc("Production Plan", production_plan)
	out = {
		"customer": pp.get("customer"),
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


def _build_roll_items_from_spr(spr_doc, pp_name):
	items = []
	for job in spr_doc.jobs or []:
		job_no = job.job_no
		shaft_combination = get_shaft_combination(pp_name, job_no)
		planned_qty = getattr(job, "total_weight", None) or 0
		for wo in get_work_orders_for_job(pp_name, job_no):
			wo_doc = frappe.get_doc("Work Order", wo["name"])
			item_code = wo_doc.production_item
			item_name = frappe.db.get_value("Item", item_code, "item_name")
			gsm, width_inch = parse_item_code(item_code)
			items.append(
				{
					"job_no": job_no,
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
