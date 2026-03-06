import frappe
from frappe.model.document import Document
from frappe.utils import flt

class ShaftProductionRun(Document):
    def validate(self):
        self.calculate_totals()

    def on_submit(self):
        """Build Stock Entries for each item/roll recorded"""
        self.create_stock_entries()
        self.status = "Completed"

    def calculate_totals(self):
        total = 0
        for item in self.items:
            total += flt(item.net_weight)
        self.total_produced_weight = total

    def create_stock_entries(self):
        """Group items by Work Order and create Manufacture entries"""
        wo_groups = {}
        for item in self.items:
            if item.work_order not in wo_groups:
                wo_groups[item.work_order] = []
            wo_groups[item.work_order].append(item)
            
        for wo_name, items in wo_groups.items():
            total_qty = sum([flt(i.net_weight) for i in items])
            if total_qty <= 0:
                continue
                
            wo = frappe.get_doc("Work Order", wo_name)
            
            # Create Stock Entry (Manufacture)
            from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
            # The standard function returns a doc object
            se_doc = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", total_qty))
            
            # If we have multiple rolls for the same WO, we might need to handle batch creation
            # For now, we consolidate the qty into one Stock Entry per WO in this run.
            
            se_doc.insert()
            se_doc.submit()
            
            frappe.msgprint(f"Created Stock Entry {se_doc.name} for Work Order {wo_name}")
