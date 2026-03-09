import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint

class ShaftProductionRun(Document):
    def validate(self):
        self.calculate_actual_qty()
        self.generate_batch_numbers()
        self.sync_job_weights()

    def sync_job_weights(self):
        """Sync weights from produced rolls back to job rows (Manual Jobs Only)"""
        job_totals = {}
        job_net_formulas = {}

        for row in self.items:
            if not row.job: continue
            job_id = str(row.job)
            
            # Sum total weights
            job_totals[job_id] = job_totals.get(job_id, 0.0) + flt(row.net_weight or 0.0)
            
            # Build net weight formula (74.78 + 74.78...)
            if job_id not in job_net_formulas:
                job_net_formulas[job_id] = []
            job_net_formulas[job_id].append(str(flt(row.net_weight or 0.0)))

        for job in self.shaft_jobs:
            jid = str(job.job_id)
            # ONLY SYNC IF JOB IS MANUAL
            if jid in job_totals and job.is_manual:
                job.total_weight = job_totals[jid]
                # Format: "74.78 + 74.78 = 149.56"
                formula = " + ".join(job_net_formulas[jid])
                job.net_weight = f"{formula} = {job_totals[jid]}"
        
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

            # FORCE RE-GENERATION IF PREFIX MISMATCH (e.g. Shift Changed)
            if row.batch_no and not row.batch_no.startswith(f"{series_prefix}-"):
                row.batch_no = None
                row.roll_no = None

            # Handle sequential Batch and Roll numbering across the shift.
            if not row.batch_no:
                # 1. Fetch highest roll_no for this precise series_prefix globally from Batch documents
                existing_batches = frappe.get_all("Batch", filters={"batch_id": ["like", f"{series_prefix}-%"]}, fields=["batch_id"])
                max_roll_num = 0
                for b in existing_batches:
                    try:
                        roll_part = b.batch_id.split("-")[-1]
                        max_roll_num = max(max_roll_num, int(roll_part))
                    except: pass
                
                # 2. Check current rows in this document
                for r in self.items:
                    if r.batch_no and r.batch_no.startswith(f"{series_prefix}-"):
                        try:
                            rp = r.batch_no.split("-")[-1]
                            max_roll_num = max(max_roll_num, int(rp))
                        except: pass
                        
                next_roll = max_roll_num + 1
                row.batch_no = f"{series_prefix}-{next_roll}"
                row.roll_no = next_roll
            
            # Ensure roll_no syncs with batch_no suffix if possible
            if row.batch_no and "-" in row.batch_no:
                try:
                    row.roll_no = int(row.batch_no.split("-")[-1])
                except:
                    pass
        
        # Return the document dict so the client can refresh values (PREVIEW ONLY until saved)
        return self.as_dict()


    def get_shift_series_by_identity(self, item_code, unit_code, current_shift):
        today_str = frappe.utils.today()
        month_str = today_str[5:7]
        year_str = today_str[2:4]
        
        date_prefix = f"{month_str}{unit_code}{year_str}"

        # 1. Search for an existing prefix assigned to this shift today
        # Check Batch records first (Submitted)
        existing_shift_batch = frappe.db.get_value("Batch",
            filters={
                "batch_id": ["like", f"{date_prefix}%"],
                "description": ["like", f"%Shift: {current_shift}%"]
            },
            fieldname="batch_id"
        )

        if not existing_shift_batch:
            # Check other Shaft Production Runs for this shift (Drafts)
            other_run_item = frappe.db.sql("""
                select i.batch_no 
                from `tabShaft Production Run Item` i
                join `tabShaft Production Run` p on i.parent = p.name
                where p.shift = %s and i.batch_no like %s
                limit 1
            """, (current_shift, f"{date_prefix}%"))
            if other_run_item:
                existing_shift_batch = other_run_item[0][0]

        if existing_shift_batch:
            return existing_shift_batch.replace("/", "-").split('-')[0]
        else:
            # Find max series suffix globally for today across both Batch and SPR Item
            max_series_num = 0
            
            # Check Batches
            all_batches_today = frappe.get_all("Batch", filters={"batch_id": ["like", f"{date_prefix}%"]}, fields=["batch_id"])
            for b in all_batches_today:
                try:
                    temp_series = b.batch_id.replace(date_prefix, "").replace("/", "-").split('-')[0]
                    max_series_num = max(max_series_num, int(temp_series))
                except: pass
                
            # Check SPR Items (Drafts)
            all_items_today = frappe.get_all("Shaft Production Run Item", filters={"batch_no": ["like", f"{date_prefix}%"]}, fields=["batch_no"])
            for i in all_items_today:
                try:
                    temp_series = i.batch_no.replace(date_prefix, "").replace("/", "-").split('-')[0]
                    max_series_num = max(max_series_num, int(temp_series))
                except: pass

            return f"{date_prefix}{max_series_num + 1}"



    def on_submit(self):
        """Create Stock Entries grouped by Work Order for all completed rows"""
        if not self.items:
            frappe.throw("No Rolls entered to produce.")
            
        wo_groups = {}
        for row in self.items:
            if not row.work_order: continue
            
            if row.work_order not in wo_groups:
                wo_groups[row.work_order] = {
                    "total_actual_weight": 0.0, 
                    "total_planned_weight": 0.0,
                    "rows": []
                }
                
            wo_groups[row.work_order]["total_actual_weight"] += flt(row.net_weight)
            wo_groups[row.work_order]["total_planned_weight"] += flt(row.planned_qty)
            wo_groups[row.work_order]["rows"].append(row)
            
        
        for wo_name, group in wo_groups.items():
            actual_qty = group["total_actual_weight"]
            planned_qty = group["total_planned_weight"]
            
            wo = frappe.get_doc("Work Order", wo_name)
            wo_party = wo.get("custom_party_code") or wo.get("party_code")

            # 1. Prepare Batch creation (will only be inserted if we have valid production)
            for row in group["rows"]:
                if not row.batch_no or flt(row.net_weight) <= 0: continue
                
                if not frappe.db.exists("Batch", row.batch_no):
                    b = frappe.new_doc("Batch")
                    b.batch_id = row.batch_no
                    b.item = wo.production_item
                    b.custom_net_weight = flt(row.net_weight)
                    b.custom_gross_weight = flt(row.gross_weight)
                    b.custom_meter = flt(row.meter_roll)
                    b.custom_party_code_text = wo_party
                    b.description = f"Shift: {self.shift}"
                    b.insert(ignore_permissions=True)
                else:
                    frappe.db.set_value("Batch", row.batch_no, {
                        "custom_net_weight": flt(row.net_weight),
                        "custom_meter": flt(row.meter_roll),
                        "description": f"Shift: {self.shift}"
                    })

            # 2. Clean up old drafts
            old_drafts = frappe.get_all("Stock Entry",
                filters={"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 0},
                fields=["name"]
            )
            for draft in old_drafts:
                frappe.delete_doc("Stock Entry", draft.name, force=1, ignore_permissions=True)

            se_items = []
            wo_planned_qty = flt(wo.qty) or 1.0
            
            # Use actual weight for consumption ratio
            # If we produced 191.83kg, we consume material for 191.83kg.
            ratio = actual_qty / wo_planned_qty if actual_qty > 0 else 0

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
                        "uom": wo_item.stock_uom,
                        "stock_uom": wo_item.stock_uom,
                        "is_finished_item": 0,
                    })

            # Finished Goods per Roll (for unique Batches)
            fg_uom = wo.stock_uom or "Kg"
            for row in group["rows"]:
                if flt(row.net_weight) > 0:
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

            if se_items:
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

            # Finalize Produced Qty and Status by summing across all submitted Stock Entries
            se_names = frappe.get_all("Stock Entry", filters={"work_order": wo.name, "docstatus": 1}, pluck="name")
            total_produced = 0.0
            if se_names:
                total_produced = sum(flt(d.qty) for d in frappe.get_all("Stock Entry Detail", 
                    filters={"parent": ["in", se_names], "is_finished_item": 1}, 
                    fields=["qty"]
                ))

            updated_status = "In Process"
            if total_produced >= wo_planned_qty:
                # Only set to completed if it actually reached the ORIGINAL planned qty
                updated_status = "Completed"
            elif total_produced > 0:
                updated_status = "In Process"

            frappe.db.set_value("Work Order", wo.name, {
                "produced_qty": total_produced,
                "status": updated_status
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
    wo_names_by_width = {}
    wo_party_by_width = {}
    
    # We fetch ALL work orders for the production plan if no explicit work_orders are given,
    # so we can calculate the total planned weight for jobs.
    wo_filters = {"production_plan": production_plan, "docstatus": ["!=", 2]}
    if work_orders:
        wo_filters["name"] = ["in", work_orders]
        
    wos = frappe.get_all("Work Order",
        filters=wo_filters,
        fields=["name", "production_item", "custom_width_inch", "qty", "custom_label", "custom_party_code", "status"]
    )
    
    # Fetch exact widths from Production Plan items
    pp_widths = {}
    if production_plan:
        try:
            pp_doc = frappe.get_doc("Production Plan", production_plan)
            for p in pp_doc.get("po_items", []):
                pp_widths[p.item_code] = flt(p.get("width_inch")) or flt(p.get("custom_width_inch"))
            for p in pp_doc.get("sub_assembly_items", []):
                pp_widths[p.production_item] = flt(p.get("width_inch")) or flt(p.get("custom_width_inch"))
        except: pass

    for wo in wos:
        w_inch = None
        # Priority 1: Exact mapping from Production Plan
        if wo.production_item in pp_widths and pp_widths[wo.production_item]:
            w_inch = round(float(pp_widths[wo.production_item]), 1)
        # Priority 2: Work Order custom field
        elif wo.custom_width_inch and flt(wo.custom_width_inch) > 0:
            w_inch = round(flt(wo.custom_width_inch), 1)
        # Priority 3: Parse metric item code
        else:
            ic = str(wo.production_item)
            if len(ic) >= 16:
                try:
                    w_inch = round(int(ic[12:16]) / 25.4, 1)
                except: pass
                
            relevant_widths.add(w_inch)
            wo_qty_by_width[w_inch] = wo_qty_by_width.get(w_inch, 0) + flt(wo.qty)
            if w_inch not in wo_names_by_width: wo_names_by_width[w_inch] = []
            if w_inch not in wo_party_by_width: wo_party_by_width[w_inch] = set()
            wo_names_by_width[w_inch].append(wo.name)
            p_code = wo.get("custom_party_code")
            if p_code: wo_party_by_width[w_inch].add(p_code)

    # Determine the label type from the first Work Order
    label_type = "Default"
    for wo in wos:
        if wo.get("custom_label"):
            label_type = wo.custom_label
            break

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
        job_wos = set()
        job_parties = set()
        for w in widths:
            # Find the closest width in our WO map
            for rw in wo_qty_by_width.keys():
                if abs(w - rw) <= 1.0:
                    job_total_planned_weight += wo_qty_by_width[rw]
                    if rw in wo_names_by_width:
                        job_wos.update(wo_names_by_width[rw])
                    if rw in wo_party_by_width:
                        job_parties.update(wo_party_by_width[rw])
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
            "quality": d.get("quality") or d.get("custom_quality"), # Try both
            "color": d.get("color") or d.get("custom_color"), # Try both
            "combination": d.get("combination"),
            "total_width": flt(t_width_val),
            "meter_roll_mtrs": flt(m_roll),
            "no_of_shafts": cint(n_shafts) if n_shafts else 1,
            "net_weight": job_net_weight_str, # Always send exactly the equation string
            "total_weight": job_total_weight,
            "work_orders": ", ".join(job_wos),
            "party_code": ", ".join(job_parties)
        })
        
    all_party_codes = set()
    wo_summary = []
    for wo in wos:
        p_code = wo.get("custom_party_code")
        if p_code:
            all_party_codes.add(p_code)
        
        wo_summary.append({
            "name": wo.name,
            "item": wo.production_item,
            "status": wo.status,
            "qty": wo.qty
        })

    return {
        "jobs": jobs,
        "label_type": label_type,
        "all_party_codes": ", ".join(sorted(list(all_party_codes))),
        "wo_summary": wo_summary
    }



@frappe.whitelist()
def get_job_roll_details(production_plan, job_id, combination, no_of_shafts, gsm=0, meter_roll=0, net_weight="", work_orders=None, claimed_wos=None, parent_spr=None, manual_item_list=None):
    """
    Fetch exact rows required for the Produced Rolls table based on combination and no_of_shafts.
    Maps Work Orders accurately and sets Planned Qty based on the individual weight components in net_weight formula.
    """
    if isinstance(work_orders, str) and work_orders and work_orders != "undefined":
        import json
        try:
            work_orders = json.loads(work_orders)
        except Exception:
            work_orders = None
    elif isinstance(work_orders, str):
        work_orders = None

    if isinstance(claimed_wos, str) and claimed_wos and claimed_wos != "undefined":
        import json
        try:
            claimed_wos = json.loads(claimed_wos)
        except Exception:
            claimed_wos = None
    elif isinstance(claimed_wos, str):
        claimed_wos = None
        
    if isinstance(manual_item_list, str) and manual_item_list:
        import json
        try:
            manual_item_list = json.loads(manual_item_list)
        except: pass

    items_to_add = []
    
    # 1. Parse widths from combination string (e.g. 46 + 46 + 26)
    widths = []
    import re
    # Match numbers like 46, 46.5, etc.
    for s in (combination or "").split('+'):
        s = s.strip().replace('"', '')
        if s:
            try:
                matches = re.findall(r"\d+\.?\d*", s)
                if matches:
                    val = float(matches[0])
                    widths.append(round(val, 2))
            except:
                continue

    # 2. Cache Production Plan Assembly Items (po_items) for lookup
    pp_items = []
    
    if not manual_item_list and parent_spr:
        spr_doc = frappe.get_doc("Shaft Production Run", parent_spr)
        for j in spr_doc.shaft_jobs:
            if str(j.job_id) == str(job_id) and j.is_manual:
                import json
                try:
                    manual_item_list = json.loads(j.manual_items) if j.manual_items else []
                except: pass
                break

    if production_plan:
        pp_doc = frappe.get_doc("Production Plan", production_plan)
        pp_items = pp_doc.po_items

    def get_matched_item_detail(target_width_inch, target_gsm):
        tw_rounded = round(flt(target_width_inch), 1)
        
        # 1. First priority: Check manual items if this is a manual job
        if manual_item_list:
            for item_code in manual_item_list:
                item_doc = frappe.get_cached_doc("Item", item_code)
                details = extract_details_from_name(item_doc.item_name or item_doc.item_code, item_doc.item_code)
                # Check for Width match
                if abs(flt(details.get("width_inch")) - flt(target_width_inch)) < 0.2:
                    return item_doc

        # 2. Second priority: Production Plan items (Exact match on GSM and Width)
        for p in pp_items:
            p_gsm = flt(p.get("gsm")) or flt(p.get("custom_gsm"))
            p_width = flt(p.get("width_inch")) or flt(p.get("custom_width_inch"))
            if abs(p_gsm - flt(target_gsm)) < 0.1 and abs(p_width - tw_rounded) < 0.5:
                return p
        
        # 3. Third priority: Metric check (46 inch -> 1170mm) for Production Plan items
        width_mm = round(flt(target_width_inch) * 25.4)
        for p in pp_items:
            p_gsm = flt(p.get("gsm")) or flt(p.get("custom_gsm"))
            if abs(p_gsm - flt(target_gsm)) < 0.1:
                ic = str(p.item_code)
                if str(width_mm) in ic:
                    return p
                try:
                    # Slice last 4 digits for width mm in some formats
                    if len(ic) >= 4 and abs(cint(ic[-4:]) - width_mm) <= 5:
                        return p
                except: pass
        
        return None

    # 3. Parse individual weight components from net_weight formula (e.g. 74.78 + 74.78 + 42.27 = 191.83)
    # Goal: Extract [74.78, 74.78, 42.27]
    weight_components = []
    if net_weight and "=" in str(net_weight):
        try:
            formula_part = str(net_weight).split('=')[0].strip()
            # Split by + and extract numbers
            for p in formula_part.split('+'):
                matches = re.findall(r"\d+\.?\d*", p)
                if matches:
                    weight_components.append(flt(matches[0]))
        except:
            pass
    elif net_weight:
        # Fallback: maybe it's just a list of numbers or a single number
        try:
            matches = re.findall(r"\d+\.?\d*", str(net_weight))
            if matches:
                 # If it was just "191.83", we might have one component. 
                 # If it was "74.78 + 74.78", we get two.
                 weight_components = [flt(m) for m in matches]
        except: pass

    # Gather all Work Orders already claimed by other manual jobs in this document to prevent cross-job re-use
    excluded_wos = []
    
    # Add WOs explicitly passed from the frontend (unsaved on screen)
    if claimed_wos and isinstance(claimed_wos, list):
        for w in claimed_wos:
            if w.strip() and w.strip() not in excluded_wos:
                excluded_wos.append(w.strip())

    if parent_spr:
        try:
            spr_doc = frappe.get_doc("Shaft Production Run", parent_spr)
            for j in spr_doc.shaft_jobs:
                if str(j.job_id) != str(job_id) and j.work_orders:
                    for w in j.work_orders.split(","):
                        if w.strip() and w.strip() not in excluded_wos:
                            excluded_wos.append(w.strip())
        except Exception: pass

    # 4. Build the roll rows
    n_shafts = cint(no_of_shafts) if cint(no_of_shafts) > 0 else 1
    
    for _ in range(n_shafts):
        for idx, target_width in enumerate(widths):
            matched_p_item = get_matched_item_detail(target_width, gsm)
            
            wo_name = None
            item_code = None
            planned_qty = 0.0
            quality = None
            color = None
            uom = "Kg"
            
            # Map the weight component from the formula if index matches
            if idx < len(weight_components):
                planned_qty = weight_components[idx]
            
            if matched_p_item:
                item_code = matched_p_item.item_code
                quality = matched_p_item.get("quality") or matched_p_item.get("custom_quality")
                color = matched_p_item.get("color") or matched_p_item.get("custom_color")
                uom = matched_p_item.get("uom") or "Kg"
                
                # FALLBACK: If color/quality missing, fetch from Item Master
                if not quality or not color:
                    item_doc = frappe.get_cached_doc("Item", item_code)
                    if not quality:
                        quality = item_doc.get("quality") or item_doc.get("custom_quality")
                    if not color:
                        color = item_doc.get("color") or item_doc.get("custom_color")
                    
                    # FINAL FALLBACK: Parse from Item Name
                    if not quality or not color:
                        item_name = item_doc.item_name or item_doc.item_code
                        parsed = extract_details_from_name(item_name, item_code)
                        if not quality: quality = parsed.get("quality")
                        if not color: color = parsed.get("color")

                # If we didn't get a weight component from formula, fallback to the item's planned_qty
                if planned_qty <= 0:
                    planned_qty = flt(matched_p_item.get("planned_qty")) or flt(matched_p_item.get("qty"))
            
            # Final calculation fallback for manual entries (Width * GSM * Length formula)
            if planned_qty <= 0 and target_width and gsm and meter_roll:
                # User formula: (gsm * target_width * meter_roll * 0.0254) / 1000
                planned_qty = round((flt(gsm) * flt(target_width) * flt(meter_roll) * 0.0254) / 1000.0, 3)

            # Force UOM to Kg for ALL rolls returned by this function
            uom = "Kg"

            # Fetch Work Order for this specific Item in this Plan
            
            wo_name = None
            # 1. PRIMARY: Match from the specific work_orders list passed for this Job
            if work_orders and isinstance(work_orders, list):
                # Ensure we match to a UNIQUE work order for duplicates by popping from the list
                for wo in work_orders:
                    # Match by item_code to ensure we grabbed the right one from the set
                    wo_doc = frappe.db.get_value("Work Order", {"name": wo, "production_item": item_code}, "name")
                    if wo_doc:
                        wo_name = wo_doc
                        work_orders.remove(wo) # Prevent this WO from being assigned to the next identical roll
                        break
            
            # 2. FALLBACK: Search Plan's Work Orders, but EXCLUDE anything claimed by other jobs
            if not wo_name:
                wo_filters = {
                    "production_plan": production_plan,
                    "production_item": item_code,
                    "docstatus": 1,
                    "status": ["!=", "Completed"]
                }
                if excluded_wos:
                    wo_filters["name"] = ["not in", excluded_wos]

                wo_name = frappe.db.get_value("Work Order", wo_filters, "name")

                # 3. FINAL FALLBACK: Draft WOs
                if not wo_name:
                    draft_filters = {
                        "production_plan": production_plan,
                        "production_item": item_code,
                        "docstatus": 0
                    }
                    if excluded_wos:
                        draft_filters["name"] = ["not in", excluded_wos]
                    wo_name = frappe.db.get_value("Work Order", draft_filters, "name")
            
            party_code = None
            if wo_name:
                wo_data = frappe.db.get_value("Work Order", wo_name, ["status", "custom_party_code"], as_dict=1)
                if wo_data:
                    party_code = wo_data.get("custom_party_code")
                    wo_status = wo_data.get("status")
            else:
                wo_status = None

            items_to_add.append({
                "job": job_id,
                "work_order": wo_name,
                "party_code": party_code,
                "item_code": item_code,
                "planned_qty": planned_qty,
                "width_inch": target_width,
                "gsm": gsm,
                "meter_roll": meter_roll,
                "net_weight": 0.0, # RESET TO 0.0 FOR MANUAL ENTRY
                "quality": quality,
                "color": color,
                "uom": uom
            })
                
    return items_to_add

@frappe.whitelist()
def create_manual_work_order(production_plan, item_code, qty, company=None):
    """Create a manual Work Order for a job addition, linked to the same Production Plan"""
    if not company:
        company = frappe.db.get_default("Company")

    # Get warehouse defaults from the Production Plan or Settings
    pp_doc = frappe.get_doc("Production Plan", production_plan)
    
    # Defensive fetching for wip_warehouse
    wip_wh = pp_doc.get("wip_warehouse")
    if not wip_wh:
        # In some versions it's wip_warehouse, in others default_wip_warehouse
        m_settings = frappe.get_single("Manufacturing Settings")
        wip_wh = m_settings.get("wip_warehouse") or m_settings.get("default_wip_warehouse")
    if not wip_wh:
        wip_wh = frappe.db.get_value("Stock Settings", None, "default_wip_warehouse")

    # Defensive fetching for fg_warehouse
    fg_wh = pp_doc.get("fg_warehouse")
    if not fg_wh:
        m_settings = frappe.get_single("Manufacturing Settings")
        fg_wh = m_settings.get("fg_warehouse") or m_settings.get("default_fg_warehouse")
    if not fg_wh:
        fg_wh = frappe.db.get_value("Stock Settings", None, "default_finished_goods_warehouse")

    wo = frappe.new_doc("Work Order")
    wo.production_plan = production_plan
    wo.production_item = item_code
    wo.qty = flt(qty)
    wo.company = company or pp_doc.company
    wo.wip_warehouse = wip_wh
    wo.fg_warehouse = fg_wh
    wo.fg_uom = "Kg"
    wo.stock_uom = "Kg"

    # Try to fetch default BOM
    bom = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")
    if bom:
        wo.bom_no = bom

    wo.insert(ignore_permissions=True)

    if bom:
        wo.reload()
        wo.submit()
    else:
        frappe.msgprint(f"Work Order {wo.name} created as Draft \u2014 no active BOM found for {item_code}. Please add a BOM and submit the WO manually.")

    return wo.name


def extract_details_from_name(name, code):
    """Mirror of JS extract_details_enhanced logic for server-side use"""
    QUALITY_MASTER = {
        "100": "PREMIUM", "101": "PLATINUM", "102": "SUPER PLATINUM",
        "103": "GOLD", "104": "SILVER", "105": "BRONZE",
        "106": "CLASSIC", "107": "SUPER CLASSIC", "108": "LIFE STYLE",
        "109": "ECO SPECIAL", "110": "ECO GREEN", "111": "SUPER ECO",
        "112": "ULTRA", "113": "DELUXE", "114": "UV"
    }
    
    res = {"gsm": None, "color": None, "width_inch": None, "quality": None}
    name_upper = (name or "").upper()
    code = str(code or "")

    # 1. Try extraction from 16-digit code
    if len(code) == 16 and code.isdigit():
        qual_code = code[3:6]
        if qual_code in QUALITY_MASTER:
            res["quality"] = QUALITY_MASTER[qual_code]
        
        try:
            res["gsm"] = str(int(code[9:12]))
            res["width_inch"] = str(round(int(code[12:16]) / 25.4))
        except: pass

    # 2. Try extraction from Name if still missing
    if not res["quality"]:
        known_qualities = sorted(QUALITY_MASTER.values(), key=len, reverse=True)
        for q in known_qualities:
            if q.upper() in name_upper:
                res["quality"] = q
                break

    if res["quality"] and name:
        import re
        q_regex = re.escape(res["quality"].upper())
        match = re.search(q_regex, name_upper)
        if match:
            after_qual = name[match.end():].strip()
            # Remove GSM parts
            after_qual = re.split(r'\s*\d+\s*GSM', after_qual, flags=re.I)[0].strip()
            if after_qual:
                res["color"] = after_qual

    # Parse GSM from name if not already found
    if not res["gsm"] and name:
        import re
        gsm_match = re.search(r'(\d+)\s*GSM', name, re.I)
        if gsm_match:
            res["gsm"] = gsm_match.group(1)

    # Parse width (inch) from name if not already found
    if not res["width_inch"] and name:
        import re
        width_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:"|inch|in(?:ch)?|\'\')', name, re.I)
        if width_match:
            res["width_inch"] = width_match.group(1)

    return res
