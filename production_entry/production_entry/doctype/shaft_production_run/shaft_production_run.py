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
            se_doc = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", total_qty))
            
            # Inherit properties from first item group for labeling
            first_item = items[0]
            
            se_doc.insert()
            se_doc.submit()
            
            frappe.msgprint(f"Created Stock Entry {se_doc.name} for Work Order {wo_name}")

@frappe.whitelist()
def get_shaft_jobs(production_plan):
    """Fetch shaft details from Production Plan and map to Shaft Production Run Job format"""
    if not production_plan:
        return []
        
    doc = frappe.get_doc("Production Plan", production_plan)
    
    # The user's field name is custom_shaft_details
    source_table = doc.get("custom_shaft_details") or []
    jobs = []
    
    for d in source_table:
        # 1. SKIP HEADER ROWS
        # If any field contains its own label text, it's a header
        comb = str(d.get("combination") or "").lower()
        gsm_val = str(d.get("gsm") or "").lower()
        if "combination" in comb or "job" in comb or "gsm" in gsm_val:
            continue
            
        t_width_val = d.get("total_width") or d.get("total_width_inches") or d.get("total_width_incl_wastage") or d.get("total_width_inch") or d.get("total_width_incl")
        if isinstance(t_width_val, str) and "total" in t_width_val.lower():
            continue

        # 2. RESILIENT MAPPING
        # Job ID: Prefer a real Job field, fallback to Combination if name is a hash
        job_id_val = d.get("job_id") or d.get("job") or d.get("job_no")
        # If job_id_val is missing, use a readable format: Combination + name[:4]
        if not job_id_val:
            job_id_val = f"{d.get('combination') or 'Job'}"
            
        m_roll = d.get("meter_roll_mtrs") or d.get("meter_per_roll") or d.get("meter_roll") or d.get("meter_per_roll_mtrs") or d.get("meter_roll_mtr")
        n_shafts = d.get("no_of_shafts") or d.get("shafts") or d.get("no_of_rolls") or d.get("no_of_shaft")
        
        jobs.append({
            "job_id": job_id_val,
            "gsm": d.get("gsm"),
            "combination": d.get("combination"),
            "total_width": flt(t_width_val),
            "meter_roll_mtrs": flt(m_roll),
            "no_of_shafts": cint(n_shafts) if n_shafts else 0
        })
        
    return jobs
