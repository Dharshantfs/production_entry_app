import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate

class ProductionEntry(Document):
    def validate(self):
        self.calculate_totals()

    def on_submit(self):
        """Build separate Production Plans and Work Orders for each item on submission"""
        self.create_production_docs()

    def calculate_totals(self):
        """Recalculate total weight based on items"""
        total = 0
        for item in self.items:
            total += flt(item.qty)
        self.total_weight = total

    def create_production_docs(self):
        """Logic to create individual PPs and WOs for each item row"""
        for item in self.items:
            # 1. Create Production Plan
            pp = frappe.get_doc({
                "doctype": "Production Plan",
                "naming_series": "PP-",
                "company": self.company or frappe.defaults.get_user_default('company'),
                "get_items_from": "Sales Order",
                "posting_date": getdate(),
                "po_items": [
                    {
                        "sales_order": self.sales_order,
                        "sales_order_item": item.so_item,
                        "item_code": item.item_code,
                        "planned_qty": item.qty,
                        "description": item.mixing_details or "" # Mixing details here
                    }
                ]
            })
            pp.insert()
            pp.submit()

            # 2. Create Work Order from PP
            pp.make_work_orders()
            
            # Map WO back to item row and tag it with the machine/unit
            wo_name = frappe.db.get_value("Work Order", {"production_plan": pp.name}, "name")
            if wo_name:
                wo = frappe.get_doc("Work Order", wo_name)
                wo.custom_allocated_unit = self.allocated_unit # Tag it for Production Run
                wo.custom_quality = item.quality
                wo.custom_color = item.color
                wo.custom_width_inch = item.width_inch
                wo.custom_gsm = item.gsm
                wo.save()
                
                item.work_order = wo_name
                item.production_plan = pp.name
        
        self.db_update()

    @frappe.whitelist()
    def make_consolidated_entry(self):
        """Consolidated production entry for all Work Orders in this machine run"""
        results = []
        for item in self.items:
            if not item.work_order: continue
            
            # Simplified Manufacture Entry Logic
            try:
                from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
                se = frappe.get_doc(make_stock_entry(item.work_order, "Manufacture", item.qty))
                se.insert()
                se.submit()
                results.append(f"Produced {item.item_code}: {se.name}")
            except Exception as e:
                results.append(f"Error {item.item_code}: {str(e)}")
        
        return results
