"""Work Order overrides for SPR duplicate MTFM cleanup."""

import frappe
from frappe.utils import flt

from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder


class SPRWorkOrderOverride(WorkOrder):
	"""Allow cancelling over-transferred MTFM entries without StockOverProductionError."""

	def update_work_order_qty(self):
		if frappe.flags.get("spr_skip_wo_transfer_qty_validation"):
			self._spr_update_work_order_qty_without_cap()
			return
		return super().update_work_order_qty()

	def _spr_update_work_order_qty_without_cap(self):
		"""Same as ERPNext update_work_order_qty but never throw on over-transferred FG."""
		if self.track_semi_finished_goods:
			return

		for purpose, fieldname in (
			("Manufacture", "produced_qty"),
			("Material Transfer for Manufacture", "material_transferred_for_manufacturing"),
			("Material Transfer for Manufacture", "additional_transferred_qty"),
		):
			if (
				purpose == "Material Transfer for Manufacture"
				and self.operations
				and self.transfer_material_against == "Job Card"
			):
				continue

			qty = self.get_transferred_or_manufactured_qty(purpose, fieldname)
			self.db_set(fieldname, qty)
			self.set_process_loss_qty()

			if purpose == "Manufacture":
				from erpnext.selling.doctype.sales_order.sales_order import update_produced_qty_in_so_item

				if self.sales_order and self.sales_order_item and not self.production_plan_sub_assembly_item:
					update_produced_qty_in_so_item(self.sales_order, self.sales_order_item)

		if self.production_plan:
			self.set_produced_qty_for_sub_assembly_item()
			self.update_production_plan_status()

		if self.additional_transferred_qty and not frappe.flags.get("spr_skip_wo_transfer_qty_validation"):
			self.validate_additional_transferred_qty()
