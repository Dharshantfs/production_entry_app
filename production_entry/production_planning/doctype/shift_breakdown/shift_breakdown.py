# Copyright (c) 2026, Production Entry and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ShiftBreakdown(Document):
	def validate(self):
		shift = (self.shift or "").strip()
		if shift and "night" in shift.lower():
			self.shift = "Night Shift"
		elif shift and "day" in shift.lower():
			self.shift = "Day Shift"
		self.sync_machine_status()

	def sync_machine_status(self):
		"""Off until every stop has Machine On — carries across later shifts on the same unit."""
		open_row = None
		last_row = None
		for row in self.breakdowns or []:
			last_row = row
			on_time = getattr(row, "on_time", None)
			is_open = not on_time
			if hasattr(row, "row_status"):
				row.row_status = "Open" if is_open else "Closed"
			if is_open:
				open_row = row
		if open_row:
			self.machine_status = "Off"
			self.last_reason = (open_row.reason or "").strip()
			self.open_since = open_row.stop_time
		else:
			self.machine_status = "On"
			self.last_reason = ((last_row.reason or "").strip() if last_row else "")
			self.open_since = None
