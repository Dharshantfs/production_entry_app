# Copyright (c) 2026, Production Entry and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ShiftWiseConsumableList(Document):
	def validate(self):
		shift = (self.shift or "").strip()
		if shift and "night" in shift.lower():
			self.shift = "Night Shift"
		elif shift and "day" in shift.lower():
			self.shift = "Day Shift"
		self._enforce_one_per_shift()

	def _enforce_one_per_shift(self):
		unit = (self.custom_unit or "").strip()
		shift = (self.shift or "").strip()
		if not (self.run_date and shift and unit):
			return
		filters = {
			"run_date": getdate(self.run_date),
			"shift": shift,
			"custom_unit": unit,
			"name": ["!=", self.name] if self.name else ["!=", ""],
		}
		other = frappe.db.get_value("Shift Wise Consumable List", filters, "name")
		if other:
			frappe.throw(
				_("Shift Wise Consumable List {0} already exists for {1} / {2} / {3}.").format(
					other, self.run_date, shift, unit
				)
			)
