import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint
import json
import re
import hashlib


class ShaftProductionRun(Document):
    def onload(self):
        # Force cleanup of any Property Setters that interfere with the Unit dropdown
        if frappe.db.exists("Property Setter", {"doc_type": "Shaft Production Run", "field_name": "custom_unit"}):
            frappe.db.delete("Property Setter", {"doc_type": "Shaft Production Run", "field_name": "custom_unit"})
            frappe.db.commit()

    def validate(self):
        self.validate_production_plan()
        self.calculate_actual_qty()
        self.generate_batch_numbers()
        self.sync_job_weights()

    def validate_production_plan(self):
        if not self.is_mix_roll and not self.production_plan:
            frappe.throw("Production Plan is required for standard runs.")

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

        # Fetch Production Plan unit STRICTLY from PP or from custom_unit if Mix Roll
        pp_unit_val = None
        if self.get("production_plan"):
            pp_unit_val = frappe.db.get_value("Production Plan", self.production_plan, "custom_unit")
        elif self.is_mix_roll:
            pp_unit_val = self.custom_unit
        
        if not pp_unit_val:
            if self.is_mix_roll:
                # Return early if no unit selected yet, so we can save as draft
                return
            frappe.throw("Please ensure the linked Production Plan has a Unit assigned (custom_unit field).")

        wo_cache = {}
            
        for row in self.items:
            wo = None
            if row.work_order:
                if row.work_order not in wo_cache:
                    wo_cache[row.work_order] = frappe.get_doc("Work Order", row.work_order)
                wo = wo_cache[row.work_order]
            
            elif not self.is_mix_roll:
                continue
            
            # Unit Mapping: Strictly from PP
            unit_val = pp_unit_val
            try:
                unit_code = str(unit_val).strip()[-1]
                if not unit_code.isdigit(): unit_code = "3"
            except:
                unit_code = "2"

            # 1. Get Series Prefix (Identity) for current shift e.g. "032261"
            series_prefix = self.get_shift_series_by_identity(row.item_code or (wo.production_item if wo else None), unit_code, shift_name)
            
            # FORCE RE-GENERATION IF PREFIX MISMATCH (e.g. Shift Changed, legacy delimiter, or extra digit)
            if row.batch_no:
                # Extract whatever prefix is there before any separator (\ or / or -)
                curr_prefix = ""
                for sep in ["/", "\\", "-"]:
                    if sep in row.batch_no:
                        curr_prefix = row.batch_no.split(sep)[0]
                        break
                
                # If prefix differs or contains legacy delimiters like '\', clear it
                if curr_prefix != series_prefix or "\\" in row.batch_no or "-" in row.batch_no:
                    row.batch_no = None
                    row.roll_no = None

            # Handle sequential Batch and Roll numbering across the unit for the day.
            if not row.batch_no:
                # 1. Fetch highest roll_no globally for this precise 6-digit series prefix.
                existing_batches = frappe.get_all("Batch", 
                    filters={"batch_id": ["like", f"{series_prefix}/%"]}, 
                    fields=["batch_id"])
                
                max_roll_num = 0
                
                def parse_roll_num(bid):
                    if not bid or "/" not in bid: return None
                    last_part = bid.split("/")[-1]
                    if last_part.isdigit():
                        return int(last_part)
                    return None

                for b in existing_batches:
                    val = parse_roll_num(b.batch_id)
                    if val is not None:
                        max_roll_num = max(max_roll_num, val)
                
                # 2. Check current and other Draft SPRs for this series
                all_draft_items = frappe.get_all("Shaft Production Run Item", 
                    filters={"batch_no": ["like", f"{series_prefix}/%"]}, 
                    fields=["batch_no"])
                for i in all_draft_items:
                    val = parse_roll_num(i.batch_no)
                    if val is not None:
                        max_roll_num = max(max_roll_num, val)
                
                # 3. Check items already processed in THIS document instance
                for r in self.items:
                    if r.batch_no and r.batch_no.startswith(f"{series_prefix}/"):
                        val = parse_roll_num(r.batch_no)
                        if val is not None:
                            max_roll_num = max(max_roll_num, val)
                        
                next_roll = max_roll_num + 1
                row.batch_no = f"{series_prefix}/{next_roll}"
                row.roll_no = next_roll
            
            # Synchronize roll_no field
            try:
                if "/" in row.batch_no:
                    row.roll_no = int(row.batch_no.split("/")[-1])
            except:
                pass
        
        # Return the document dict so the client can refresh values (PREVIEW ONLY until saved)
        return self.as_dict()


    def get_shift_series_by_identity(self, item_code, unit_code, current_shift):
        # 1. Define Root Prefix e.g. "03226" (MM U YY)
        run_date = self.run_date or frappe.utils.today()
        month_str = frappe.utils.getdate(run_date).strftime("%m")
        year_str = frappe.utils.getdate(run_date).strftime("%y")
        root_prefix = f"{month_str}{unit_code}{year_str}"

        # 2. Check if this specific shift on this literal date already has a prefix started
        # We search specifically in Shaft Production Run to find the literal shift link
        existing_shift_doc = frappe.db.get_value("Shaft Production Run", 
            {"run_date": run_date, "shift": current_shift, "custom_unit": ["like", f"%{unit_code}%"], "docstatus": ["<", 2]}, 
            "name")
        
        if existing_shift_doc:
            # Find any item in this doc that has a batch number with root_prefix
            existing_batch = frappe.db.get_value("Shaft Production Run Item", 
                {"parent": existing_shift_doc, "batch_no": ["like", f"{root_prefix}%"]}, 
                "batch_no")
            if existing_batch:
                # Split by any separator to get just the 6-digit prefix
                for sep in ["/", "\\", "-"]:
                    if sep in str(existing_batch):
                        return str(existing_batch).split(sep)[0]
                return str(existing_batch)

        # 3. If no document/prefix exists for this literal shift yet, increment the global suffix 'S'
        # based on ALL prefixes using this MMUYY root globally.
        # This ensures S=1, S=2, S=3... regardless of day, as long as the month/unit/year is the same.
        
        # Search Shaft Production Run Item
        all_today_items = frappe.db.sql("""
            select batch_no from `tabShaft Production Run Item` 
            where batch_no like %s
        """, (f"{root_prefix}%",))
        
        # Search official Batch records
        all_official_batches = frappe.get_all("Batch", filters={"batch_id": ["like", f"{root_prefix}%"]}, fields=["batch_id"])
        
        max_s = 0
        def get_s(bid):
            if not bid: return None
            # Find prefix part before / or \ or -
            pref = ""
            for sep in ["/", "\\", "-"]:
                if sep in bid:
                    pref = bid.split(sep)[0]
                    break
            
            if not pref or len(pref) != 6: return None
            
            # S is the 6th digit
            s_val = pref[5:6]
            if s_val.isdigit(): return int(pref.replace(root_prefix, ""))
            return None

        for b in all_today_items:
            val = get_s(b[0])
            if val is not None: max_s = max(max_s, val)
        for b in all_official_batches:
            val = get_s(b.batch_id)
            if val is not None: max_s = max(max_s, val)

        # Start from 1 if none found, else increment
        return f"{root_prefix}{max_s + 1}"



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
            
        
        if self.is_mix_roll:
            # Group by Item Code instead of Work Order
            groups = {}
            for row in self.items:
                if not row.item_code: continue
                if row.item_code not in groups:
                    groups[row.item_code] = {"total_actual_weight": 0.0, "rows": []}
                groups[row.item_code]["total_actual_weight"] += flt(row.net_weight)
                groups[row.item_code]["rows"].append(row)
            
            for item_code, group in groups.items():
                self.process_mix_roll_submission(item_code, group)
            return

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
                se.stock_entry_type = "Manufacture" if not self.is_mix_roll else "Material Receipt"
                if not self.is_mix_roll:
                    se.work_order = wo.name
                    se.from_bom = 1
                    se.bom_no = wo.bom_no
                    se.use_multi_level_bom = wo.use_multi_level_bom
                    se.fg_completed_qty = actual_qty
                
                se.company = wo.company if wo else "Jayashree Spun Bond"
                
                # Need to attach items properly
                for item in se_items:
                    se.append("items", item)
                    
                se.insert(ignore_permissions=True)
                se.submit()

                msg = f"✅ Auto-Generated & Submitted Stock Entry: <a href='/app/stock-entry/{se.name}' target='_blank'><b>{se.name}</b></a>"
                if not self.is_mix_roll:
                     msg += f" for Work Order <b>{wo.name}</b>."
                frappe.msgprint(msg)

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

    def process_mix_roll_submission(self, item_code, group):
        actual_qty = group["total_actual_weight"]
        
        # 1. Prepare/Sync Batch creation
        item_has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")

        for row in group["rows"]:
            if not row.batch_no or flt(row.net_weight) <= 0: continue
            
            if item_has_batch:
                if not frappe.db.exists("Batch", row.batch_no):
                    b = frappe.new_doc("Batch")
                    b.batch_id = row.batch_no
                    b.item = item_code
                    b.custom_net_weight = flt(row.net_weight)
                    b.custom_gross_weight = flt(row.gross_weight) or flt(row.net_weight)
                    b.custom_meter = flt(row.meter_roll)
                    b.description = f"Shift: {self.shift} (Mix Roll)"
                    b.insert(ignore_permissions=True)
                else:
                    frappe.db.set_value("Batch", row.batch_no, {
                        "custom_net_weight": flt(row.net_weight),
                        "custom_gross_weight": flt(row.gross_weight) or flt(row.net_weight),
                        "custom_meter": flt(row.meter_roll),
                        "description": f"Shift: {self.shift} (Mix Roll)"
                    })
            else:
                # If item is not batch enabled, we just clear the batch_no on the row to avoid errors
                # but keep the production.
                row.batch_no = None

        se_items = []
        for row in group["rows"]:
            if flt(row.net_weight) > 0:
                target_wh = "Finished Goods - JSB-1ZT"
                if not frappe.db.exists("Warehouse", target_wh):
                    target_wh = "Finished Goods - IZT"
                
                se_items.append({
                    "item_code": item_code,
                    "t_warehouse": target_wh,
                    "qty": flt(row.net_weight),
                    "uom": "Kg",
                    "stock_uom": "Kg",
                    "conversion_factor": 1.0,
                    "batch_no": row.batch_no
                })

        if se_items:
            se = frappe.new_doc("Stock Entry")
            se.stock_entry_type = "Material Receipt"
            se.company = "Jayashree Spun Bond"
            for item in se_items:
                se.append("items", item)
            se.insert(ignore_permissions=True)
            se.submit()

            frappe.msgprint(f"✅ Auto-Generated & Submitted Stock Entry (Material Receipt): <a href='/app/stock-entry/{se.name}' target='_blank'><b>{se.name}</b></a> for Item <b>{item_code}</b>.")


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

        if w_inch is not None:
            relevant_widths.add(w_inch)
            wo_qty_by_width[w_inch] = wo_qty_by_width.get(w_inch, 0) + flt(wo.qty)
            if w_inch not in wo_names_by_width: 
                wo_names_by_width[w_inch] = []
            if w_inch not in wo_party_by_width: 
                wo_party_by_width[w_inch] = set()
            wo_names_by_width[w_inch].append(wo.name)
            p_code = wo.get("custom_party_code")
            if p_code: 
                wo_party_by_width[w_inch].add(p_code)

    # Determine the label type from the first Work Order
    label_type = "Default"
    for wo in wos:
        if wo.get("custom_label"):
            label_type = wo.custom_label
            break

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
            for rw in list(wo_qty_by_width.keys()):
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
        "custom_unit": doc.custom_unit,
        "all_party_codes": ", ".join(sorted(list(all_party_codes))),
        "wo_summary": wo_summary
    }



@frappe.whitelist()
def get_job_roll_details(production_plan=None, job_id=None, combination=None, no_of_shafts=1, gsm=0, meter_roll=0, net_weight="", work_orders=None, claimed_wos=None, parent_spr=None, manual_item_list=None):
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
        try:
            claimed_wos = json.loads(claimed_wos)
        except Exception:
            claimed_wos = None
    elif isinstance(claimed_wos, str):
        claimed_wos = None
        
    if isinstance(manual_item_list, str) and manual_item_list:
        try:
            manual_item_list = json.loads(manual_item_list)
        except: pass

    items_to_add = []
    # 1. Parse widths from combination string (e.g. 46 + 46 + 26)
    widths = []
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
                try:
                    manual_item_list = j.manual_items
                except: pass
                break
    
    # 2. Parse manual_item_list into a flat list of strings
    if manual_item_list:
        if isinstance(manual_item_list, str):
            try:
                # Try JSON first [ "item1", "item2" ]
                loaded = json.loads(manual_item_list)
                if isinstance(loaded, list):
                    manual_item_list = loaded
                else:
                    manual_item_list = [str(loaded)]
            except:
                # Fallback to comma split "item1, item2"
                manual_item_list = [x.strip() for x in manual_item_list.split(",") if x.strip()]
        
        # Ensure it's a list for flattening logic below
        if not isinstance(manual_item_list, list):
            manual_item_list = [manual_item_list]
    
    # Flatten any sub-lists if strings contain commas "item1,item2" inside a list ["item1,item2", "item3"]
    final_items = []
    if manual_item_list and isinstance(manual_item_list, list):
        for entry in manual_item_list:
            if isinstance(entry, str) and "," in entry:
                final_items.extend([x.strip() for x in entry.split(",") if x.strip()])
            else:
                final_items.append(entry)
    manual_item_list = final_items

    if production_plan:
        pp_doc = frappe.get_doc("Production Plan", production_plan)
        pp_items = pp_doc.po_items

    def get_matched_item_detail(target_width_inch, target_gsm):
        tw_rounded = round(flt(target_width_inch), 1)
        tg_rounded = round(flt(target_gsm), 1)
        
        # 1. First priority: Check manual items if this is a manual job
        if manual_item_list:
            # Flatten list if strings contain commas
            flattened_items = []
            for entry in manual_item_list:
                if isinstance(entry, str) and "," in entry:
                    flattened_items.extend([x.strip() for x in entry.split(",") if x.strip()])
                else:
                    flattened_items.append(entry)
            
            for item_code in flattened_items:
                if not frappe.db.exists("Item", item_code):
                    continue
                item_doc = frappe.get_cached_doc("Item", item_code)
                details = extract_details_from_name(item_doc.item_name or item_doc.item_code, item_doc.item_code)
                # Check for Width and GSM match (within 0.2 and 0.5 tolerances)
                i_width = flt(details.get("width_inch"))
                i_gsm = flt(details.get("gsm"))
                
                if abs(i_width - flt(target_width_inch)) < 0.2:
                    # If it's a manual job, we almost always want this item, but check GSM if we have it
                    if i_gsm > 0 and abs(i_gsm - tg_rounded) < 1.0:
                        return item_doc
                    elif i_gsm <= 0:
                        return item_doc

        # 2. Second priority: Production Plan items (Exact match on GSM and Width)
        for p in pp_items:
            p_gsm = flt(p.get("gsm")) or flt(p.get("custom_gsm"))
            p_width = flt(p.get("width_inch")) or flt(p.get("custom_width_inch"))
            if abs(p_gsm - tg_rounded) < 0.2 and abs(p_width - tw_rounded) < 0.5:
                return p
        
        # 3. Third priority: Metric check (46 inch -> 1170mm) for Production Plan items
        width_mm = round(flt(target_width_inch) * 25.4)
        for p in pp_items:
            p_gsm = flt(p.get("gsm")) or flt(p.get("custom_gsm"))
            if abs(p_gsm - tg_rounded) < 0.5:
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
                    if frappe.db.exists("Item", item_code):
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
                    else:
                        # If item doesn't exist, try parsing from code directly if possible
                        parsed = extract_details_from_name(item_code, item_code)
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
                        # NOTE: We do NOT remove(wo) here because multiple rolls in one job 
                        # often share the same Work Order (e.g. 46+46).
                        # claimed_wos already protects against OTHER jobs stealing it.
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

            # RESET TO 0.0 INITIALLY so user has to fill it in
            final_net_weight = 0.0

            items_to_add.append({
                "job": job_id,
                "work_order": wo_name,
                "party_code": party_code,
                "item_code": item_code,
                "planned_qty": planned_qty,
                "width_inch": target_width,
                "gsm": gsm,
                "meter_roll": meter_roll,
                "net_weight": final_net_weight, 
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
    QUALITY_MASTER = {
        "100": "PREMIUM", "101": "PLATINUM", "102": "SUPER PLATINUM",
        "103": "GOLD", "104": "SILVER", "105": "BRONZE",
        "106": "CLASSIC", "107": "SUPER CLASSIC", "108": "LIFE STYLE",
        "109": "ECO SPECIAL", "110": "ECO GREEN", "111": "SUPER ECO",
        "112": "ULTRA", "113": "DELUXE", "114": "UV",
        "120": "PREMIUM PLUS",
        "012": "ULTRA", "010": "PREMIUM", "011": "PLATINUM"
    }
    
    res = {"gsm": "", "color": "", "width_inch": "", "quality": ""}
    name_upper = (name or "").upper()
    code_str = str(code or "")

    # 1. First priority: Check dedicated Master tables using code parts
    if code_str.isdigit() and len(code_str) >= 9:
        q_code = code_str[3:6]
        c_code = code_str[6:9]
        
        # Check Quality Master
        if q_code.isdigit() and frappe.db.exists("DocType", "Quality Master"):
            try:
                q_match = frappe.db.get_value("Quality Master", {"code": q_code}, "quality_name")
                if q_match: res["quality"] = q_match
            except Exception: pass
            
        if not res["quality"] and q_code in QUALITY_MASTER: 
            res["quality"] = QUALITY_MASTER[q_code]

        # Check Colour Master
        if c_code.isdigit() and frappe.db.exists("DocType", "Colour Master"):
            try:
                c_match = frappe.db.get_value("Colour Master", {"code": c_code}, "color_name")
                if c_match: res["color"] = c_match
            except Exception: pass

    # 2. Extract standard patterns from name
    gsm_m = re.search(r'(\d+)\s*GSM', name_upper)
    if gsm_m: res["gsm"] = gsm_m.group(1)
    
    width_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:"|INCH|IN|inch|\'\')', name_upper)
    if width_m: res["width_inch"] = width_m.group(1)

    # 3. Fallback extraction from code if still missing
    if code_str.isdigit():
        cl = len(code_str)
        if cl == 16:
            # Quality (4-6)
            if not res["quality"]:
                qc = code_str[3:6]
                if qc in QUALITY_MASTER: res["quality"] = QUALITY_MASTER[qc]
                elif frappe.db.exists("DocType", "Quality Master"):
                    try:
                        q_match = frappe.db.get_value("Quality Master", {"code": qc}, "quality_name")
                        if q_match: res["quality"] = q_match
                    except: pass
            
            # Color (7-9)
            if not res["color"]:
                cc = code_str[6:9]
                if frappe.db.exists("DocType", "Colour Master"):
                    try:
                        c_match = frappe.db.get_value("Colour Master", {"code": cc}, "color_name")
                        if c_match: res["color"] = c_match
                    except: pass
            
            # GSM (10-12)
            if not res["gsm"]: 
                res["gsm"] = str(int(code_str[9:12]))
            
            # Width (13-16)
            if not res["width_inch"]: 
                res["width_inch"] = str(round(int(code_str[12:16]) / 25.4))
        
        elif cl == 15:
            if not res["gsm"]: res["gsm"] = str(int(code_str[8:11]))
            if not res["width_inch"]: res["width_inch"] = str(round(int(code_str[11:15]) / 25.4))
        
        elif cl == 12:
            if not res["gsm"]: res["gsm"] = str(int(code_str[7:10]))
            if not res["width_inch"]: res["width_inch"] = str(int(code_str[10:12]))

    # 4. Final keyword lookup in name if still missing
    if not res["quality"]:
        for q_code, q_name in list(QUALITY_MASTER.items()):
            if q_name in name_upper:
                res["quality"] = q_name
                break

    if name and not res["color"]:
        # Try to find anything after GSM or Quality
        parts = re.split(r'(\d+\s*GSM|(?:"|INCH|IN|inch|\'\')|PLATINUM|PREMIUM|ULTRA|GOLD|SILVER|BRONZE|UV)', name_upper)
        if parts:
            for p in parts:
                p_clean = p.strip()
                if not p_clean or len(p_clean) < 3: continue
                if p_clean.isdigit(): continue
                is_marker = False
                for q in list(QUALITY_MASTER.values()):
                    if q in p_clean: 
                        is_marker = True
                        break
                if is_marker: continue
                res["color"] = p_clean
                break

    return res
