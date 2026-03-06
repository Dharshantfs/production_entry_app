import frappe
from frappe.model.document import Document
from frappe.utils import flt

class ShaftProductionRun(Document):
    def validate(self):
        self.calculate_totals()

    def on_submit(self):
        """Auto-create individual Roll Production Entries for the logged roll weights"""
        self.create_roll_production_entries()
        self.status = "Completed"

    def calculate_totals(self):
        total = 0
        for item in self.items:
            total += flt(item.net_weight)
        self.total_produced_weight = total

    @frappe.whitelist()
    def fetch_pending_work_orders(self):
        if not self.allocated_unit:
            frappe.throw("Please select an Allocated Unit (Machine) first")
        
        filters = {
            "status": ["in", ["Ready to Manufacture", "In Progress"]],
            "docstatus": 1,
            "custom_allocated_unit": self.allocated_unit
        }
        
        if self.production_plan:
            filters["production_plan"] = self.production_plan
        
        wos = frappe.get_all("Work Order", 
            filters=filters,
            fields=["name", "production_item", "qty", "produced_qty"]
        )
        
        if not wos:
            return f"No pending Work Orders found for {self.allocated_unit}."
            
        return f"Found {len(wos)} Work Orders for {self.allocated_unit}. Please add roll weights below."

    def create_roll_production_entries(self):
        """
        Consolidates weights by Work Order and creates 'Manufacture' Stock Entries.
        This updates the WO status and Warehouse stock in ERPNext.
        """
        from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
        
        # Group rolls by Work Order to create consolidated entries
        wo_groups = {}
        for item in self.items:
            if not item.work_order: continue
            if item.work_order not in wo_groups:
                wo_groups[item.work_order] = 0
            wo_groups[item.work_order] += flt(item.net_weight)
            
        created_entries = []
        
        for wo_name, total_weight in wo_groups.items():
            try:
                # 1. Create the Stock Entry (Manufacture)
                # This moves raw materials from WIP to FG and updates WO produced_qty
                se_doc = make_stock_entry(wo_name, "Manufacture", total_weight)
                se = frappe.get_doc(se_doc)
                se.insert()
                se.submit()
                
                created_entries.append(se.name)
                
                # Tag the Stock Entry for reference
                se.db_set("remarks", f"Created from Shaft Production Run {self.name}")
                
            except Exception as e:
                frappe.log_error(f"Shaft Production Run Error for {wo_name}: {str(e)}")
                frappe.msgprint(f"Error creating production entry for {wo_name}: {str(e)}")
                
        if created_entries:
            frappe.msgprint(f"Successfully created Production (Stock) Entries: {', '.join(created_entries)}")
