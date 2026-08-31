import frappe
from frappe.utils import cstr, flt

from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class SPRStockEntryOverride(StockEntry):
	"""Stock Entry safeguards for Shaft Production Run generated entries."""

	def _is_spr_generated_entry(self) -> bool:
		meta = frappe.get_meta("Stock Entry")
		if meta.has_field("shaft_production_run") and (self.get("shaft_production_run") or "").strip():
			return True
		if frappe.db.has_column("Stock Entry", "custom_spr_reference"):
			ref = (self.get("custom_spr_reference") or "").strip()
			if not ref and self.name:
				ref = cstr(frappe.db.get_value("Stock Entry", self.name, "custom_spr_reference")).strip()
			return bool(ref)
		return False

	def _spr_wo_overproduction_cap(self, wo) -> float:
		allowance = flt(
			frappe.db.get_single_value("Manufacturing Settings", "overproduction_percentage_for_work_order")
		)
		if not allowance:
			allowance = flt(
				frappe.db.get_single_value("Manufacturing Settings", "transfer_extra_materials_percentage")
			)
		return flt(wo.qty) + (allowance / 100.0 * flt(wo.qty))

	def _spr_should_skip_wo_transfer_cap_on_cancel(self) -> bool:
		"""Skip WO cap validation when cancelling duplicate SPR entries or cleaning an over-posted WO."""
		purpose = (self.purpose or "").strip()
		if self._is_spr_generated_entry():
			return True
		wo_name = (self.work_order or "").strip()
		if not wo_name or not frappe.db.exists("Work Order", wo_name):
			return False
		wo = frappe.get_doc("Work Order", wo_name)
		if purpose == "Material Transfer for Manufacture":
			cap = self._spr_wo_overproduction_cap(wo)
			current = flt(wo.material_transferred_for_manufacturing)
			return current > cap + 1e-9
		if purpose == "Manufacture":
			cap = self._spr_wo_overproduction_cap(wo)
			return flt(wo.produced_qty) > cap + 1e-9
		return False

	def on_cancel(self):
		skip_cap = self._spr_should_skip_wo_transfer_cap_on_cancel()
		if skip_cap:
			frappe.flags.spr_skip_wo_transfer_qty_validation = True
		try:
			super().on_cancel()
		finally:
			if skip_cap:
				frappe.flags.spr_skip_wo_transfer_qty_validation = False

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
		if getattr(self.flags, "ignore_validate_work_order", False) or frappe.flags.get("spr_skip_wo_transfer_qty_validation"):
			_wo = self.work_order
			self.work_order = None
			try:
				super().validate()
			finally:
				self.work_order = _wo
			return
		super().validate()

	def validate_work_order(self):
		if getattr(self.flags, "ignore_validate_work_order", False) or frappe.flags.get("spr_skip_wo_transfer_qty_validation"):
			return
		if hasattr(super(), "validate_work_order"):
			return super().validate_work_order()

	def validate_work_order_qty(self):
		"""Allow whole-roll fabric transfers that exceed BOM remaining."""
		if getattr(self.flags, "ignore_validate_work_order", False) or frappe.flags.get("spr_skip_wo_transfer_qty_validation"):
			return
		if hasattr(super(), "validate_work_order_qty"):
			return super().validate_work_order_qty()

	def check_duplicate_entry_for_work_order(self):
		# Skipping this check does not change RM consumption: Manufacture lines still come from
		# get_items()/BOM; Stock Ledger posts whatever transfer_qty is on each RM row.
		# SPR submits Manufacture with work_order linked after submit; also allow repeated partial
		# manufacture for the same WO across multiple SPRs until cumulative FG reaches the limit.
		if getattr(self.flags, "ignore_duplicate_for_work_order", False):
			return
		# SPR can have prior MAT-STE transfers on WO; do not block Manufacture submit on this check.
		if self._is_spr_generated_entry():
			return
		return super().check_duplicate_entry_for_work_order()
