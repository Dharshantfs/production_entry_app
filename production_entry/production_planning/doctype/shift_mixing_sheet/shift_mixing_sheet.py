# Copyright (c) 2026, Production Entry and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


class ShiftMixingSheet(Document):
	def validate(self):
		self._normalize_shift()
		if (self.status or "").strip() == "Completed" and not self.completed_on:
			self.completed_by = frappe.session.user
			self.completed_on = now_datetime()

	def _normalize_shift(self):
		shift = (self.shift or "").strip()
		if shift and "night" in shift.lower():
			self.shift = "Night Shift"
		elif shift and "day" in shift.lower():
			self.shift = "Day Shift"
