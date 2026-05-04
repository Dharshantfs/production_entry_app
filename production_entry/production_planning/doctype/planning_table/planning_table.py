# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document


class PlanningTable(Document):
	def validate(self):
		"""Keep ``custom_total_no_of_colours`` aligned when White Tint (Yes) adds a station colour."""
		try:
			from production_entry.production_planning.scheduler_api import _apply_printed_bopp_total_colours_to_row

			_apply_printed_bopp_total_colours_to_row(self)
		except Exception:
			pass
