# Copyright (c) 2026, Production Entry and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime


class GSMShiftSession(Document):
	def validate(self):
		self._normalize_shift()
		self._enforce_single_open_session()
		self._validate_reopen_fields()

	def _validate_reopen_fields(self):
		if cint(self.is_reopen or 0):
			reason = (self.reopen_reason or "").strip()
			if not reason:
				frappe.throw(_("Re-open reason is required."))
			if reason == "Other" and not (self.reopen_remarks or "").strip():
				frappe.throw(_("Re-open remarks are required when reason is Other."))

	def _normalize_shift(self):
		shift = (self.shift or "").strip()
		if shift and "night" in shift.lower():
			self.shift = "Night Shift"
		elif shift and "day" in shift.lower():
			self.shift = "Day Shift"

	def _enforce_single_open_session(self):
		if (self.status or "").strip() != "Open":
			return
		unit = (self.custom_unit or "").strip()
		if not unit:
			return
		filters = {"custom_unit": unit, "status": "Open"}
		if self.name:
			filters["name"] = ["!=", self.name]
		other = frappe.db.get_value("GSM Shift Session", filters, "name")
		if other:
			frappe.throw(
				_("Unit {0} already has an open shift session ({1}). Close it before opening another.").format(
					unit, other
				)
			)
		existing_same = frappe.db.exists(
			"GSM Shift Session",
			{
				"run_date": getdate(self.run_date),
				"shift": self.shift,
				"custom_unit": unit,
				"status": "Open",
				"name": ["!=", self.name] if self.name else ["!=", ""],
			},
		)
		if existing_same:
			frappe.throw(
				_("An open {0} session already exists for {1} on {2}.").format(
					self.shift, unit, self.run_date
				)
			)
