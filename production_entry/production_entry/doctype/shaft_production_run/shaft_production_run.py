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

    for job in jobs:
        job_id = job.get('job_id')
        combination = job.get('combination') or ''
        widths = []
        for s in combination.split('+'):
            s = s.strip().replace('"', '')
            if s:
                try: widths.append(float(s))
                except ValueError: continue

        no_of_shafts = job.get('no_of_shafts') or 1
        
        work_orders = frappe.db.sql("""
            SELECT wo.name, wo.production_item, wo.qty
            FROM `tabWork Order` wo
            WHERE wo.production_plan = %s
            AND wo.production_plan_item = %s
            AND wo.docstatus != 2
        """, (production_plan, job_id), as_dict=True)

        wo_by_width = {}
        for wo in work_orders:
            item_code = wo.production_item
            try:
                if len(item_code) >= 16:
                    width_inch = round(int(item_code[12:16]) / 25.4, 1)
                    wo_by_width[width_inch] = wo
            except (ValueError, IndexError):
                pass

        for _ in range(no_of_shafts):
            for width in widths:
                target_width = round(float(width), 1)
                wo = wo_by_width.get(target_width, {})
                
                item_code = wo.get('production_item', '') if wo else ''
                item_name = frappe.db.get_value('Item', item_code, 'item_name') if item_code else ''
                
                gsm_val = job.get('gsm')
                width_val = width
                
                if item_code and len(item_code) >= 16:
                    try:
                        gsm_val = int(item_code[9:12])
                        width_val = round(int(item_code[12:16]) / 25.4, 1)
                    except:
                        pass
                
                if wo:
                    items.append({
                        'job': job_id,
                        'shaft_combination': combination,
                        'work_order': wo.get('name', ''),
                        'item_code': item_code,
                        'item_name': item_name,
                        'gsm': gsm_val,
                        'width_inch': width_val,
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

    items = []

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
        
        # Get all WOs for this PP + job
        work_orders = frappe.db.sql("""
            SELECT wo.name, wo.production_item, wo.qty
            FROM `tabWork Order` wo
            WHERE wo.production_plan = %s
            AND wo.production_plan_item = %s
            AND wo.docstatus != 2
        """, (pp_name, job_id), as_dict=True)

        # Map WOs to widths
        wo_by_width = {}
        for wo in work_orders:
            item_code = wo.production_item
            try:
                if len(item_code) >= 16:
                    # Item code positions 12-15 = width in mm
                    width_inch = round(int(item_code[12:16]) / 25.4, 1)
                    wo_by_width[width_inch] = wo
            except (ValueError, IndexError):
                pass
                
        no_of_shafts = cint(job.no_of_shafts) if job.no_of_shafts else 1
        
        for _ in range(no_of_shafts):
            for width in widths:
                # Find WO for this specific width
                target_width = round(float(width), 1)
                wo = wo_by_width.get(target_width, {})
                
                item_code = wo.get('production_item', '') if wo else ''
                item_name = frappe.db.get_value('Item', item_code, 'item_name') if item_code else ''
                
                # Try to parse properties from item code, fallback to job properties
                gsm_val = job.gsm
                width_val = width
                
                if item_code and len(item_code) >= 16:
                    try:
                        gsm_val = int(item_code[9:12])
                        width_val = round(int(item_code[12:16]) / 25.4, 1)
                    except:
                        pass
                
                if wo:
                    items.append({
                        'job_id': job_id,
                        'shaft_combination': combination,
                        'planned_qty': job.total_width,
                        'work_order': wo.get('name', ''),
                        'item_code': item_code,
                        'item_name': item_name,
                        'gsm': gsm_val,
                        'width_inch': width_val,
                        'color': '',
                        'quality': '',
                        'uom': 'Kg',
                        'order_code': wo.get('name', ''),
                        'meter_per_roll': job.meter_roll_mtrs,
                        'batch_no': '',
                        'roll_no': '',
                        'net_weight': 0,
                        'gross_weight': 0,
                    })

    return {
        'production_plan': pp_name,
        'items': items
    }
