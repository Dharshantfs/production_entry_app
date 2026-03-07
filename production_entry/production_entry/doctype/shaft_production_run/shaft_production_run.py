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
        
    @frappe.whitelist()
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
            
            # Handle sequential Batch and Roll numbering across the shift.
            if not row.batch_no:
                # 1. Fetch highest roll_no for this precise series_prefix globally today
                existing_batches = frappe.get_all("Batch", filters={"batch_id": ["like", f"{series_prefix}-%"]}, fields=["batch_id"])
                max_roll_num = 0
                for b in existing_batches:
                    try:
                        roll_part = b.batch_id.split("-")[-1]
                        max_roll_num = max(max_roll_num, int(roll_part))
                    except: pass
                
                # 2. Check current un-saved rows in memory
                for r in self.items:
                    if r.batch_no and r.batch_no.startswith(f"{series_prefix}-"):
                        try:
                            rp = r.batch_no.split("-")[-1]
                            max_roll_num = max(max_roll_num, int(rp))
                        except: pass
                        
                next_roll = max_roll_num + 1
                row.batch_no = f"{series_prefix}-{next_roll}"
                row.roll_no = next_roll
            
            target_batch_id = row.batch_no
            
            # Allow overwriting batch_no logic safely (delete old if wrong prefix)
            if target_batch_id and not target_batch_id.startswith(f"{series_prefix}-"):
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
def get_work_orders(production_plan):
    """Fetch all work orders linked to a production plan"""
    if not production_plan:
        return []
    
    return frappe.get_all("Work Order",
        filters={"production_plan": production_plan, "docstatus": ["!=", 2]},
        fields=["name", "production_item", "qty", "produced_qty", "status", "custom_gsm", "custom_color", "custom_quality"]
    )


@frappe.whitelist()
def get_shaft_jobs(production_plan, work_orders=None):
    """Fetch shaft details from Production Plan and map to Shaft Production Run Job format"""
    if not production_plan:
        return []
    
    if isinstance(work_orders, str) and work_orders and work_orders != "undefined":
        import json
        try:
            work_orders = json.loads(work_orders)
        except Exception:
            work_orders = None
    elif isinstance(work_orders, str):
        work_orders = None
        
    doc = frappe.get_doc("Production Plan", production_plan)
    source_table = doc.get("custom_shaft_details") or []
    
    relevant_widths = set()
    wo_qty_by_width = {}
    
    # We fetch ALL work orders for the production plan if no explicit work_orders are given,
    # so we can calculate the total planned weight for jobs.
    wo_filters = {"production_plan": production_plan, "docstatus": ["!=", 2]}
    if work_orders:
        wo_filters["name"] = ["in", work_orders]
        
    wos = frappe.get_all("Work Order",
        filters=wo_filters,
        fields=["name", "production_item", "custom_width_inch", "qty"]
    )
    
    for wo in wos:
        w_inch = None
        if wo.custom_width_inch and flt(wo.custom_width_inch) > 0:
            w_inch = round(flt(wo.custom_width_inch), 1)
        else:
            ic = str(wo.production_item)
            # Example item code: 1001091010800660
            # Length is 16. Digits 12:16 represent mm. "0660" -> 660. 660 / 25.4 = 25.98 -> 26.0
            if len(ic) >= 16:
                try:
                    w_inch = round(int(ic[12:16]) / 25.4, 1)
                except: pass
                
        if w_inch is not None:
            relevant_widths.add(w_inch)
            wo_qty_by_width[w_inch] = wo_qty_by_width.get(w_inch, 0) + flt(wo.qty)

    jobs = []
    
    jobs = []
    
    for idx, d in enumerate(source_table):
        # SKIP HEADER ROWS
        comb = str(d.get("combination") or "").lower()
        gsm_val = str(d.get("gsm") or "").lower()
        if not comb or "combination" in comb or "job" in comb or "gsm" in gsm_val:
            continue
            
        t_width_val = d.get("combined_width") or d.get("total_width") or d.get("total_width_inches")
        m_roll = d.get("meter__roll") or d.get("meter_roll_mtrs") or d.get("meter_per_roll")
        n_shafts = d.get("no_of_shaft") or d.get("no_of_shafts") or d.get("shafts")
        net_wt = d.get("net_weight")
        tot_wt = d.get("total_weight_kgs") or d.get("total_weight")
        
        # Parse combination widths for weight calc
        comb_str = str(d.get("combination") or "")
        widths = []
        import re
        for s in comb_str.split('+'):
            s = s.strip().replace('"', '')
            try:
                matches = re.findall(r"\d+\.?\d*", s)
                if matches:
                    widths.append(round(float(matches[0]), 1))
            except: continue
        
        # Priority: explicit job_id -> custom field -> name -> index
        job_id_val = d.get("s_no") or d.get("job_id") or d.get("job") or str(idx + 1)
        
        # Calculate planned weights from Work Orders associated with these widths
        job_total_planned_weight = 0
        for w in widths:
            # Find the closest width in our WO map
            for rw in wo_qty_by_width.keys():
                if abs(w - rw) <= 0.1:
                    job_total_planned_weight += wo_qty_by_width[rw]
                    break
                    
        # net_wt might be a string like "74.78 + 74.78 + 42.27 = 191.83"
        job_net_weight_str = str(net_wt or "")
        job_net_weight_val = 0.0
        if "=" in job_net_weight_str:
            try:
                job_net_weight_val = flt(job_net_weight_str.split("=")[-1].strip())
            except: pass
        else:
            try:
                # Just pluck the first number we see if there's no =
                matches = re.findall(r"\d+\.?\d*", job_net_weight_str)
                if matches:
                    job_net_weight_val = flt(matches[-1]) 
            except: pass
            
        # The user's system often calculates the final "combination" weight, so pass the raw string too
        
        job_total_weight = flt(tot_wt) if flt(tot_wt) > 0 else job_total_planned_weight

        jobs.append({
            "job_id": job_id_val,
            "gsm": d.get("gsm"),
            "combination": d.get("combination"),
            "total_width": flt(t_width_val),
            "meter_roll_mtrs": flt(m_roll),
            "no_of_shafts": cint(n_shafts) if n_shafts else 1,
            "net_weight": job_net_weight_str, # Always send exactly the equation string
            "total_weight": job_total_weight
        })
        
    return jobs



@frappe.whitelist()
def get_job_roll_details(production_plan, job_id, combination, no_of_shafts, gsm=0, meter_roll=0, work_orders=None):
    """
    Fetch exact rows required for the Popup Roll Entry based on combination and no_of_shafts.
    """
    if isinstance(work_orders, str) and work_orders and work_orders != "undefined":
        import json
        try:
            work_orders = json.loads(work_orders)
        except Exception:
            work_orders = None
    elif isinstance(work_orders, str):
        work_orders = None

    items_to_add = []
    
    widths = []
    for s in (combination or "").split('+'):
        s = s.strip().replace('"', '')
        if s:
            try:
                import re
                matches = re.findall(r"\d+\.?\d*", s)
                if matches:
                    val = float(matches[0])
                    widths.append(round(val, 1))
            except:
                continue

    query_filters = {
        "production_plan": production_plan,
        "docstatus": ["!=", 2]
    }
    
    # If selected work_orders are provided, restrict to them
    if work_orders:
        query_filters["name"] = ["in", work_orders]
    else:
        # If no explicit selection, we fallback to production_plan_item if job_id is numeric
        if str(job_id).isdigit():
            query_filters["production_plan_item"] = job_id
            
    # Generic fetch
    wos = frappe.get_all("Work Order",
        filters=query_filters,
    )
    
    # Build Map for Quality / Color from Production Plan po_items
    pp_item_map = {}
    if production_plan:
        try:
            pp_doc = frappe.get_doc("Production Plan", production_plan)
            for p in pp_doc.get("po_items", []):
                pp_item_map[p.item_code] = {
                    "quality": p.get("custom_quality") or p.get("quality"),
                    "color": p.get("custom_color") or p.get("color")
                }
            for p in pp_doc.get("sub_assembly_items", []):
                pp_item_map[p.production_item] = {
                    "quality": p.get("custom_quality") or p.get("quality"),
                    "color": p.get("custom_color") or p.get("color")
                }
        except: pass

    wo_by_width = {}
    for wo in wos:
        w = None
        if wo.custom_width_inch and flt(wo.custom_width_inch) > 0:
            w = round(flt(wo.custom_width_inch), 1)
        else:
            ic = str(wo.production_item)
            if len(ic) >= 16:
                try:
                    w = round(int(ic[12:16]) / 25.4, 1)
                except: pass
                
        if w is not None:
            if w not in wo_by_width:
                wo_by_width[w] = []
            wo_by_width[w].append(wo)

    n_shafts = cint(no_of_shafts) if cint(no_of_shafts) > 0 else 1
    
    for _ in range(n_shafts):
        for target_width in widths:
            tw_rounded = round(float(target_width), 1)
            
            matched_wo_width = None
            for w in wo_by_width.keys():
                if abs(w - tw_rounded) <= 0.1:
                    if len(wo_by_width[w]) > 0:
                        matched_wo_width = w
                        break
                        
            if matched_wo_width is not None and len(wo_by_width[matched_wo_width]) > 0:
                wo = None
                if len(wo_by_width[matched_wo_width]) == 1:
                    wo = wo_by_width[matched_wo_width][0] # Keep reusing
                else:
                    wo = wo_by_width[matched_wo_width].pop(0) # Consume
                    
                # Calculate planned net weight per roll based on combo
                # If a WO is 191kg for 12 shafts, it's roughly 15.9kg per shaft. We can divide by qty or use standard metric.
                wo_planned_weight = flt(wo.qty) / (n_shafts if n_shafts else 1)
                    
                # Get Quality and Color from Production Plan Assembly items
                wo_quality = pp_item_map.get(wo.production_item, {}).get("quality") or wo.custom_quality
                wo_color = pp_item_map.get(wo.production_item, {}).get("color") or wo.custom_color
                
                items_to_add.append({
                    "job": job_id,
                    "work_order": wo.name,
                    "item_code": wo.production_item,
                    "planned_qty": flt(wo.qty),
                    "width_inch": tw_rounded,
                    "gsm": gsm,
                    "uom": wo.stock_uom,
                    "color": wo_color,
                    "quality": wo_quality,
                    "meter_roll": meter_roll,
                    "net_weight": round(wo_planned_weight, 3),
                    "gross_weight": 0.0,
                    "roll_no": 0
                })
            else:
                # Fallback: assign an empty row for user to pick WO manually
                items_to_add.append({
                    "job": job_id,
                    "width_inch": tw_rounded,
                    "gsm": gsm,
                    "meter_roll": meter_roll,
                    "net_weight": 0.0,
                    "gross_weight": 0.0,
                    "roll_no": 0
                })
                
    return items_to_add
