import frappe

from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class SPRStockEntryOverride(StockEntry):
	"""Stock Entry safeguards for Shaft Production Run generated entries."""

	def _is_spr_generated_entry(self) -> bool:
		meta = frappe.get_meta("Stock Entry")
		if not meta.has_field("shaft_production_run"):
			return False
		return bool((self.get("shaft_production_run") or "").strip())

	def _manufacture_type_name(self) -> str:
		if frappe.db.exists("Stock Entry Type", "Manufacture"):
			purpose = (frappe.db.get_value("Stock Entry Type", "Manufacture", "purpose") or "").strip()
			if purpose == "Manufacture":
				return "Manufacture"
		return (
			frappe.db.get_value("Stock Entry Type", {"purpose": "Manufacture", "is_standard": 1}, "name")
			or frappe.db.get_value("Stock Entry Type", {"purpose": "Manufacture"}, "name")
			or "Manufacture"
		)

	def _normalize_spr_manufacture_context(self):
		if not self._is_spr_generated_entry():
			return
		self.purpose = "Manufacture"
		if self.meta.has_field("stock_entry_type"):
			self.stock_entry_type = self._manufacture_type_name()

	def validate(self):
		self._normalize_spr_manufacture_context()
		super().validate()

	def check_duplicate_entry_for_work_order(self):
		# SPR can have prior MAT-STE transfers on WO; do not block Manufacture submit on this check.
		if self._is_spr_generated_entry():
			return
		return super().check_duplicate_entry_for_work_order()
