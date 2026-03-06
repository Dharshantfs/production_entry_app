import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint

class ShaftProductionRun(Document):
    def validate(self):
        self.calculate_actual_qty()
        self.generate_batch_numbers()
        
    def calculate_actual_qty(self):
        total_qty = 0.0
        for row in self.items:
            total_qty += flt(row.net_weight or 0.0)
        self.total_produced_weight = total_qty
        
    def generate_batch_numbers(self):
        # Only operate if shift has been determined
        shift_name = str(self.get("shift") or "DAY").upper()

        wo_cache = {}
            
        for row in self.items:
            if not row.work_order:
                continue

            if row.work_order not in wo_cache:
                wo_cache[row.work_order] = frappe.get_doc("Work Order", row.work_order)
            wo = wo_cache[row.work_order]
            
            unit_val = self.get("allocated_unit") or wo.get("custom_unit_") or wo.get("unit")
            try:
                unit_code = str(unit_val).strip()[-1]
                if not unit_code.isdigit(): unit_code = "3"
            except:
                unit_code = "3"

            series_prefix = self.get_shift_series_by_identity(wo.production_item, unit_code, shift_name)

            wo_party = wo.get("custom_party_code") or wo.get("party_code")
            
            # Map batch for Roll No uniqueness
            if not row.roll_no:
                continue

            target_batch_id = f"{series_prefix}-{row.roll_no}"

            # Allow overwriting batch_no logic safely (delete old if wrong prefix)
            if row.batch_no and row.batch_no != target_batch_id:
                if frappe.db.exists("Batch", row.batch_no):
                    try:
                        if row.batch_no.startswith(series_prefix[:5]):
                            frappe.delete_doc("Batch", row.batch_no, force=1, ignore_permissions=True)
                    except:
                        pass

            row.batch_no = target_batch_id

            if not frappe.db.exists("Batch", target_batch_id):
                b = frappe.new_doc("Batch")
                b.batch_id = target_batch_id
                b.item = wo.production_item
                b.custom_net_weight = flt(row.get("net_weight"))
                b.custom_gross_weight = flt(row.get("gross_weight"))
                b.custom_meter = flt(row.get("meter_roll"))
                b.custom_party_code_text = wo_party
                b.description = f"Shift: {shift_name}"
                b.insert(ignore_permissions=True)
            else:
                frappe.db.set_value("Batch", target_batch_id, {
                    "description": f"Shift: {shift_name}",
                    "custom_net_weight": flt(row.get("net_weight"))
                })


    def get_shift_series_by_identity(self, item_code, unit_code, current_shift):
        today_str = frappe.utils.today()
        month_str = today_str[5:7]
        year_str = today_str[2:4]
        
        date_prefix = f"{month_str}{unit_code}{year_str}"

        existing_shift_batch = frappe.db.get_value("Batch",
            filters={
                "batch_id": ["like", f"{date_prefix}%"],
                "description": ["like", f"%Shift: {current_shift}%"]
            },
            fieldname="batch_id"
        )

        if existing_shift_batch:
            return existing_shift_batch.replace("/", "-").split('-')[0]
        else:
            all_batches_today = frappe.get_all("Batch",
                filters={"batch_id": ["like", f"{date_prefix}%"]},
                fields=["batch_id"]
            )
            max_series_num = 0
            for b in all_batches_today:
                try:
                    temp_series = b.batch_id.replace(date_prefix, "").replace("/", "-").split('-')[0]
                    max_series_num = max(max_series_num, int(temp_series))
                except:
                    continue
            return f"{date_prefix}{max_series_num + 1}"


    def on_submit(self):
        """Create Stock Entries grouped by Work Order for all completed rows"""
        if not self.items:
            frappe.throw("No Rolls entered to produce.")
            
        wo_groups = {}
        for row in self.items:
            if not row.work_order: continue
            if flt(row.net_weight) <= 0: continue
            
            if row.work_order not in wo_groups:
                wo_groups[row.work_order] = {"total_weight": 0.0, "rows": []}
                
            wo_groups[row.work_order]["total_weight"] += flt(row.net_weight)
            wo_groups[row.work_order]["rows"].append(row)
            
        
        for wo_name, group in wo_groups.items():
            actual_qty = group["total_weight"]
            wo = frappe.get_doc("Work Order", wo_name)
            
            # 1. Clean up old drafts
            old_drafts = frappe.get_all("Stock Entry",
                filters={"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 0},
                fields=["name"]
            )
            for draft in old_drafts:
                frappe.delete_doc("Stock Entry", draft.name, force=1, ignore_permissions=True)

            se_items = []
            wo_planned_qty = flt(wo.qty) or 1.0
            ratio = actual_qty / wo_planned_qty

            # Raw Materials Consumption
            for wo_item in wo.required_items:
                if wo_item.item_code != wo.production_item:
                    suggested_qty = flt(wo_item.required_qty) * ratio
                    if suggested_qty <= 0:
                        continue
                    se_items.append({
                        "item_code": wo_item.item_code,
                        "s_warehouse": wo.wip_warehouse,
                        "t_warehouse": "",
                        "qty": suggested_qty,
                        "uom": wo_item.uom,
                        "stock_uom": wo_item.stock_uom or wo_item.uom,
                        "conversion_factor": wo_item.conversion_factor or 1.0,
                        "is_finished_item": 0,
                    })

            # Finished Goods per Roll (for unique Batches)
            fg_uom = wo.stock_uom or "Kg"
            for row in group["rows"]:
                se_items.append({
                    "item_code": wo.production_item,
                    "s_warehouse": "",
                    "t_warehouse": wo.fg_warehouse,
                    "qty": flt(row.net_weight),
                    "uom": fg_uom,
                    "stock_uom": fg_uom,
                    "conversion_factor": 1.0,
                    "is_finished_item": 1,
                    "batch_no": row.batch_no
                })

            se = frappe.new_doc("Stock Entry")
            se.stock_entry_type = "Manufacture"
            se.work_order = wo.name
            se.company = wo.company
            se.from_bom = 1
            se.bom_no = wo.bom_no
            se.use_multi_level_bom = wo.use_multi_level_bom
            se.fg_completed_qty = actual_qty
            
            # Need to attach items properly
            for item in se_items:
                se.append("items", item)
                
            se.insert(ignore_permissions=True)
            se.submit()

            frappe.msgprint(f"✅ Auto-Generated & Submitted Stock Entry: <a href='/app/stock-entry/{se.name}' target='_blank'><b>{se.name}</b></a> for Work Order <b>{wo.name}</b>.")

            # Update WO Qty manually as post-processing 
            total_produced = 0.0
            all_ses = frappe.get_all("Stock Entry",
                filters={"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 1},
                fields=["name"]
            )
            for s in all_ses:
                rows = frappe.get_all("Stock Entry Detail",
                    filters={"parent": s.name, "is_finished_item": 1},
                    fields=["qty"]
                )
                total_produced += sum(flt(r.qty) for r in rows)
                
            new_status = "Completed" if total_produced >= wo_planned_qty else "In Process"
            additional_qty = max(0.0, total_produced - wo_planned_qty)
            
            frappe.db.set_value("Work Order", wo.name, {
                "produced_qty": total_produced,
                "additional_transferred_qty": additional_qty,
                "status": new_status
            })


@frappe.whitelist()
def get_shaft_jobs(production_plan):
    """Fetch shaft details from Production Plan and map to Shaft Production Run Job format"""
    if not production_plan:
        return []
        
    doc = frappe.get_doc("Production Plan", production_plan)
    source_table = doc.get("custom_shaft_details") or []
    jobs = []
    
    for d in source_table:
        # SKIP HEADER ROWS
        comb = str(d.get("combination") or "").lower()
        gsm_val = str(d.get("gsm") or "").lower()
        if "combination" in comb or "job" in comb or "gsm" in gsm_val:
            continue
            
        t_width_val = d.get("total_width") or d.get("total_width_inches") or d.get("total_width_incl_wastage") or d.get("total_width_inch") or d.get("total_width_incl")
        if isinstance(t_width_val, str) and "total" in t_width_val.lower():
            continue

        job_id_val = d.get("job_id") or d.get("job") or d.get("job_no")
        if not job_id_val:
            job_id_val = f"{d.get('combination') or 'Job'}"
            
        m_roll = d.get("meter_roll_mtrs") or d.get("meter_per_roll") or d.get("meter_roll")
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

@frappe.whitelist()
def get_job_roll_details(production_plan, job_id, combination, no_of_shafts, gsm=0, meter_roll=0):
    """
    Fetch exact rows required for the Popup Roll Entry based on combination and no_of_shafts.
    """
    items_to_add = []
    
    widths = []
    for s in (combination or "").split('+'):
        s = s.strip().replace('"', '')
        if s:
            try:
                widths.append(float(s))
            except ValueError:
                continue

    work_orders = frappe.db.sql("""
        SELECT wo.name, wo.production_item, wo.qty, wo.stock_uom, wo.custom_quality, wo.custom_color
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
            
    n_shafts = cint(no_of_shafts) if cint(no_of_shafts) > 0 else 1
    
    for _ in range(n_shafts):
        for target_width in widths:
            tw_rounded = round(float(target_width), 1)
            wo = wo_by_width.get(tw_rounded)
            
            if wo:
                items_to_add.append({
                    "job": job_id,
                    "work_order": wo.name,
                    "item_code": wo.production_item,
                    "planned_qty": flt(wo.qty),
                    "width_inch": tw_rounded,
                    "gsm": gsm,
                    "uom": wo.stock_uom,
                    "color": wo.custom_color,
                    "quality": wo.custom_quality,
                    "meter_roll": meter_roll,
                    "net_weight": 0.0,
                    "gross_weight": 0.0,
                    "roll_no": 0
                })
                
    return items_to_add
