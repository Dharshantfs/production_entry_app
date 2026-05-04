# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document


class PlanningTable(Document):
	def validate(self):
		"""Keep ``custom_total_no_of_colours`` aligned when White Tint (Yes) adds a station colour."""
		try:
			if not frappe.db.has_column("Planning Table", "custom_total_no_of_colours"):
				return
			ic = (self.item_code or "").strip().upper()
			if not ic:
				return
			from production_entry.production_planning.scheduler_api import (
				PRINTED_BOPP_FILM_UNIT,
				_printed_bopp_design_colours_token,
				_total_colours_token_for_printed_bopp,
			)

			is_pb = ic.startswith("PB-") or ("PRINTED" in ic and "BOPP" in ic)
			if not is_pb and (self.unit or "").strip() != PRINTED_BOPP_FILM_UNIT:
				return
			ndc = (getattr(self, "custom_no_of_design_colours", None) or "").strip()
			if not ndc:
				pb_nm = frappe.db.get_value("Item", self.item_code, "item_name") or ""
				ndc = (_printed_bopp_design_colours_token(self.item_code, pb_nm) or "").strip()
			if not ndc:
				return
			wt = (getattr(self, "custom_white_tint", None) or "").strip()
			tnc = _total_colours_token_for_printed_bopp(ndc, wt) or ndc
			self.custom_total_no_of_colours = tnc
		except Exception:
			pass
