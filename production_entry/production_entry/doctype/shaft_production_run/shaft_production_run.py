import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint

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
        # Normalize row dict to find fields by partial match
        row = d.as_dict()
        
        # 1. SKIP HEADER ROWS
        comb = str(row.get("combination") or "").lower()
        gsm_val = str(row.get("gsm") or "").lower()
        if "combination" in comb or "job" in comb or "gsm" in gsm_val:
            continue
            
        # 2. AGGRESSIVE MAPPING
        t_width = 0
        m_roll = 0
        n_shafts = 0
        
        # Try to find target fields by searching common substrings
        for k, v in row.items():
            k_lower = k.lower()
            if not t_width and "width" in k_lower:
                t_width = v
            if not m_roll and "meter" in k_lower:
                m_roll = v
            if not n_shafts and ("shaft" in k_lower or "rolls" in k_lower):
                n_shafts = v
        
        # Fallbacks for specific common names if loop didn't find them correctly
        t_width = t_width or row.get("total_width") or row.get("total_width_inches")
        m_roll = m_roll or row.get("meter_roll_mtrs") or row.get("meter_per_roll")
        n_shafts = n_shafts or row.get("no_of_shafts") or row.get("shafts")

        # Skip if it's still clearly a label row (e.g. value is "Total Width")
        if isinstance(t_width, str) and "total" in t_width.lower():
            continue

        jobs.append({
            "job_id": str(len(jobs) + 1), # Use sequential number as Job ID
            "gsm": row.get("gsm"),
            "combination": row.get("combination"),
            "total_width": flt(t_width),
            "meter_roll_mtrs": flt(m_roll),
            "no_of_shafts": cint(n_shafts) if n_shafts else 0
        })

    # --- Fetch Work Orders and pre-calculate Roll Production Results (items) ---
    items = []
    
    work_orders = frappe.get_list('Work Order', filters={
        'production_plan': production_plan,
        'docstatus': 1,
        'status': ['in', ['Ready to Manufacture', 'In Progress', 'Completed']]
    }, fields=['name', 'production_item', 'qty', 'produced_qty'])

    for wo in work_orders:
        item_code = wo.production_item
        if len(item_code) >= 16:
            try:
                wo.parsed_gsm = int(item_code[9:12])
                wo.parsed_width_inch = round(int(item_code[12:16]) / 25.4, 1)
            except (ValueError, IndexError):
                wo.parsed_gsm = 0
                wo.parsed_width_inch = 0
        else:
            wo.parsed_gsm = 0
            wo.parsed_width_inch = 0

    for job in jobs:
        combination = job.get('combination') or ''
        widths = []
        for s in combination.split('+'):
            s = s.strip().replace('"', '')
            if s:
                try: widths.append(float(s))
                except ValueError: continue

        no_of_shafts = job.get('no_of_shafts') or 1
        
        for _ in range(no_of_shafts):
            for w in widths:
                matching_wo = next((wo for wo in work_orders if 
                                   abs(wo.parsed_gsm - cint(job.get('gsm'))) < 1 and 
                                   abs(wo.parsed_width_inch - w) < 0.5), None)
                
                if matching_wo:
                    items.append({
                        'job_no': job.get('job_id'),
                        'shaft_combination': combination,
                        'planned_qty': 0, # Cannot calculate easily without WO planning details here
                        'work_order': matching_wo.name,
                        'item_code': matching_wo.production_item,
                        'item_name': frappe.db.get_value('Item', matching_wo.production_item, 'item_name'),
                        'gsm': wo.parsed_gsm or job.get('gsm'),
                        'width_inch': wo.parsed_width_inch or w,
                        'net_weight': 0,
                    })

    return {'jobs': jobs, 'items': items}


@frappe.whitelist()
def get_or_create_roll_entry(shaft_production_run):
    """
    Check if Roll Production Entry exists for this SPR.
    If yes → return its name to open.
    If no  → fetch all jobs + WOs and return pre-filled data.
    """
    if not shaft_production_run:
        return {}

    # Check existing
    existing = frappe.db.get_value(
        'Roll Production Entry',
        {'shaft_production_run': shaft_production_run, 'status': ['!=', 'Cancelled']},
        'name'
    )
    if existing:
        return {'existing': existing}

    spr_doc = frappe.get_doc('Shaft Production Run', shaft_production_run)
    pp_name = spr_doc.production_plan
    
    if not pp_name:
        # Extract from name if name contains PP (as per prompt)
        if "PP-" in shaft_production_run:
            pp_name = "PP-" + shaft_production_run.split("PP-")[1]
        else:
            frappe.throw(_('Could not find Production Plan linked to {0}').format(shaft_production_run))

    roll_wise_entry = []

    # Loop through all jobs in SPR
    for job in spr_doc.shaft_jobs:
        job_id = job.job_id
        combination = job.combination or ""
        
        # Determine target widths from combination (e.g. 46+46+26)
        widths = []
        for s in combination.split('+'):
            s = s.strip().replace('"', '')
            if s:
                try:
                    widths.append(float(s))
                except ValueError:
                    continue
        
        # Get ALL WOs for this Production Plan
        # Prompt says: Each WO has production_plan field linking back
        work_orders = frappe.get_list('Work Order', filters={
            'production_plan': pp_name,
            'docstatus': 1,
            'status': ['in', ['Ready to Manufacture', 'In Progress', 'Completed']]
        }, fields=['name', 'production_item', 'qty', 'produced_qty'])

        # Pre-calculate parsed details for each WO for faster matching
        for wo in work_orders:
            item_code = wo.production_item
            if len(item_code) >= 16:
                # 0-2 Process, 3-5 Quality, 6-8 Color, 9-11 GSM, 12-15 Width(mm)
                try:
                    wo.parsed_gsm = int(item_code[9:12])
                    wo.parsed_width_inch = round(int(item_code[12:16]) / 25.4, 1)
                except (ValueError, IndexError):
                    wo.parsed_gsm = 0
                    wo.parsed_width_inch = 0
            else:
                wo.parsed_gsm = 0
                wo.parsed_width_inch = 0

        no_of_shafts = cint(job.get('no_of_shafts') or 1)
        
        for _ in range(no_of_shafts):
            for w in widths:
                # Match by GSM and Width
                matching_wo = next((wo for wo in work_orders if 
                                   abs(wo.parsed_gsm - cint(job.gsm)) < 1 and 
                                   abs(wo.parsed_width_inch - w) < 0.5), None)
                
                if matching_wo:
                    roll_wise_entry.append({
                        'job_no': job_id,
                        'shaft_combination': combination,
                        'planned_qty': job.total_weight if hasattr(job, 'total_weight') else 0,
                        'wo_id': matching_wo.name,
                        'item_code': matching_wo.production_item,
                        'item_name': frappe.db.get_value('Item', matching_wo.production_item, 'item_name'),
                        'gsm': wo.parsed_gsm or job.gsm,
                        'width': wo.parsed_width_inch or w,
                        'order_code': matching_wo.name,
                        'meter_per_roll': job.meter_roll_mtrs,
                        'batch_no': '',
                        'roll_no': '',
                        'net_weight': 0,
                        'gross_weight': 0,
                    })

    return {
        'production_plan': pp_name,
        'roll_wise_entry': roll_wise_entry
    }
