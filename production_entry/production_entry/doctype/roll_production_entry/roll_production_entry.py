import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint

class RollProductionEntry(Document):
    def validate(self):
        self.calculate_actual_qty()
        self.generate_batch_numbers()
        
    def calculate_actual_qty(self):
        total_qty = 0.0
        for row in self.items:
            total_qty += flt(row.net_weight or row.get("net_wt") or 0.0)
        self.actual_qty = total_qty
        
    def generate_batch_numbers(self):
        if not self.production_item:
            return
            
        wo = frappe.get_doc("Work Order", self.items[0].work_order) if self.items and self.items[0].work_order else None
        if not wo:
            return
            
        unit_val = self.get("unit") or wo.get("custom_unit_") or wo.get("unit")
        try:
            unit_code = str(unit_val).strip()[-1]
            if not unit_code.isdigit(): unit_code = "3"
        except:
            unit_code = "3"

        series_prefix = self.get_shift_series_by_identity(self.production_item, unit_code)
        self.shift_batch_number = series_prefix

        wo_party = wo.get("custom_party_code") or wo.get("party_code")
        shift_name = str(self.get("shift") or "DAY").upper()

        for row in self.items:
            row.party_code = wo_party

            target_batch_id = f"{series_prefix}-{row.roll_no}"

            if row.batch_no and row.batch_no != target_batch_id:
                if frappe.db.exists("Batch", row.batch_no):
                    try:
                        if row.batch_no.startswith(series_prefix[:5]):
                            frappe.delete_doc("Batch", row.batch_no, force=1, ignore_permissions=True)
                    except:
                        pass

            row.batch_no = target_batch_id

            if frappe.db.exists("Batch", target_batch_id):
                existing_item = frappe.db.get_value("Batch", target_batch_id, "item")
                if existing_item and existing_item != wo.production_item:
                    frappe.throw(f"""
                        <div style='color:red; font-weight:bold;'>⛔ CRITICAL DUPLICATE ERROR</div>
                        Batch <b>{target_batch_id}</b> exists for a different item: <b>{existing_item}</b>.
                        Please check your Unit Code, Date, or Roll Sequence.
                    """)

            if not frappe.db.exists("Batch", target_batch_id):
                b = frappe.new_doc("Batch")
                b.batch_id = target_batch_id
                b.item = wo.production_item
                b.custom_net_weight = float(row.get("net_weight") or row.get("net_wt") or 0)
                b.custom_gross_weight = float(row.get("gross_weight") or row.get("gross_wt") or 0)
                b.custom_meter = float(row.get("meter_per_roll") or 0)
                b.custom_party_code_text = wo_party
                b.description = f"Shift: {shift_name}"
                b.insert(ignore_permissions=True)
            else:
                frappe.db.set_value("Batch", target_batch_id, "description", f"Shift: {shift_name}")


    def get_shift_series_by_identity(self, item_code, unit_code):
        today_str = frappe.utils.today()
        month_str = today_str[5:7]
        year_str = today_str[2:4]
        
        date_prefix = f"{month_str}{unit_code}{year_str}"
        current_shift = str(self.get("shift") or "DAY").upper()

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


@frappe.whitelist()
def execute_production(roll_entry):
    try:
        if not roll_entry:
            frappe.throw("Entry ID is missing.")

        re_doc = frappe.get_doc("Roll Production Entry", roll_entry)
        existing_se = re_doc.get("manufacture_stock_entry")

        # Fallback to get Work Order from the first item if not globally set
        wo_name = None
        if re_doc.items and len(re_doc.items) > 0:
            wo_name = re_doc.items[0].work_order
            
        if not wo_name:
            frappe.throw("Work Order not found in items")

        # --- CLICK 2: SE already exists — check its status ---
        if existing_se:
            se_docstatus = frappe.db.get_value("Stock Entry", existing_se, "docstatus")

            if se_docstatus == 1:
                se_doc = frappe.get_doc("Stock Entry", existing_se)
                actual_produced = sum(
                    float(row.qty or 0)
                    for row in se_doc.items
                    if row.is_finished_item
                )

                wo_qty = float(
                    frappe.db.get_value("Work Order", wo_name, "qty") or 1
                )

                all_ses = frappe.get_all("Stock Entry",
                    filters={
                        "work_order": wo_name,
                        "stock_entry_type": "Manufacture",
                        "docstatus": 1
                    },
                    fields=["name"]
                )
                total_produced = 0.0
                for s in all_ses:
                    rows = frappe.get_all("Stock Entry Detail",
                        filters={"parent": s.name, "is_finished_item": 1},
                        fields=["qty"]
                    )
                    total_produced += sum(float(r.qty or 0) for r in rows)

                new_status = "Completed" if total_produced >= wo_qty else "In Process"
                additional_qty = max(0.0, total_produced - wo_qty)

                frappe.db.set_value("Work Order", wo_name, {
                    "produced_qty": total_produced,
                    "additional_transferred_qty": additional_qty,
                    "status": new_status
                })

                if additional_qty > 0:
                    wo_doc = frappe.get_doc("Work Order", wo_name)
                    for wo_item in wo_doc.required_items:
                        consumed_total = 0.0
                        for s in all_ses:
                            consumed_rows = frappe.get_all("Stock Entry Detail",
                                filters={
                                    "parent": s.name,
                                    "item_code": wo_item.item_code,
                                    "is_finished_item": 0
                                },
                                fields=["qty"]
                            )
                            consumed_total += sum(float(r.qty or 0) for r in consumed_rows)
                        if consumed_total > 0:
                            frappe.db.set_value(
                                "Work Order Item",
                                wo_item.name,
                                "transferred_qty",
                                consumed_total
                            )

                frappe.db.set_value("Roll Production Entry", roll_entry, {
                    "status": "Completed",
                    "actual_qty": actual_produced
                })
                frappe.db.commit()

                # Auto-submit if not already
                if re_doc.docstatus == 0:
                    re_doc_fresh = frappe.get_doc("Roll Production Entry", roll_entry)
                    re_doc_fresh.flags.ignore_permissions = True
                    re_doc_fresh.submit()

                msg = f"<b>✅ Production Completed!</b><br>"
                msg += f"Stock Entry: <a href='/app/stock-entry/{existing_se}' target='_blank'><b>{existing_se}</b></a><br>"
                msg += f"Actual Produced: <b>{actual_produced} Kg</b><br>"
                msg += f"WO Total Produced: <b>{total_produced} Kg</b> / {wo_qty} Kg | Status: <b>{new_status}</b>"
                if additional_qty > 0:
                    msg += f"<br>Additional Transferred Qty: <b>{additional_qty} Kg</b>"
                msg += f"<br><b>Roll Production Entry submitted ✅</b>"
                
                frappe.msgprint({"title": "Success", "message": msg, "indicator": "green"})
                return {"success": True, "stock_entry": msg}

            elif se_docstatus == 0:
                msg = f"<b>⚠️ Draft SE pending submission.</b><br><a href='/app/stock-entry/{existing_se}' target='_blank'><b>Open {existing_se}</b></a><br>Edit raw material quantities → Submit SE → Come back here → Click Submit Production again."
                frappe.msgprint({"title": "Pending", "message": msg, "indicator": "orange"})
                return {"success": False, "stock_entry": msg}

        # --- CLICK 1: No SE yet — create Draft SE ---
        wo = frappe.get_doc("Work Order", wo_name)

        actual_qty = 0.0
        for row in re_doc.items:
            w = float(row.get("net_weight") or row.get("net_wt") or 0)
            actual_qty += w

        if actual_qty <= 0:
            frappe.throw("Error: Total Net Weight is 0. Please check your rolls.")

        old_drafts = frappe.get_all("Stock Entry",
            filters={"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 0},
            fields=["name"]
        )
        for draft in old_drafts:
            frappe.delete_doc("Stock Entry", draft.name, force=1, ignore_permissions=True)

        items_list = []
        wo_planned_qty = float(wo.qty or 1)
        ratio = actual_qty / wo_planned_qty

        for item in wo.required_items:
            if item.item_code != wo.production_item:
                suggested_qty = float(item.required_qty or 0) * ratio
                if suggested_qty <= 0:
                    continue
                items_list.append({
                    "item_code": item.item_code,
                    "s_warehouse": wo.wip_warehouse,
                    "t_warehouse": "",
                    "qty": suggested_qty,
                    "uom": item.uom,
                    "stock_uom": item.stock_uom or item.uom,
                    "conversion_factor": item.conversion_factor or 1.0,
                    "is_finished_item": 0,
                    "description": item.description,
                    "item_name": item.item_name
                })

        wo_party = wo.get("custom_party_code") or wo.get("party_code")
        shift_name = str(re_doc.get("shift") or "DAY").upper()
        fg_uom = wo.stock_uom or "Kg"

        for row in re_doc.items:
            row_weight = float(row.get("net_weight") or 0)
            if row_weight <= 0:
                continue

            if not frappe.db.exists("Batch", row.batch_no):
                b = frappe.new_doc("Batch")
                b.batch_id = row.batch_no
                b.item = wo.production_item
                b.description = f"Shift: {shift_name}"
                b.custom_party_code_text = wo_party
                b.custom_net_weight = row_weight
                b.insert(ignore_permissions=True)

            items_list.append({
                "item_code": wo.production_item,
                "s_warehouse": "",
                "t_warehouse": wo.fg_warehouse,
                "qty": row_weight,
                "uom": fg_uom,
                "stock_uom": fg_uom,
                "conversion_factor": 1.0,
                "is_finished_item": 1,
                "batch_no": row.batch_no,
                "description": f"Roll No: {row.roll_no}",
                "custom_roll_no": row.roll_no,
                "item_name": wo.item_name
            })

        se_doc = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Manufacture",
            "work_order": wo.name,
            "company": wo.company,
            "from_warehouse": wo.wip_warehouse,
            "to_warehouse": wo.fg_warehouse,
            "use_multi_level_bom": 0,
            "from_bom": 0,
            "fg_completed_qty": actual_qty,
            "items": items_list
        })

        se_doc.flags.ignore_mandatory = True
        se_doc.flags.ignore_validate = True
        se_doc.insert(ignore_permissions=True)

        frappe.db.set_value("Stock Entry", se_doc.name, "fg_completed_qty", actual_qty)

        frappe.db.set_value("Roll Production Entry", roll_entry, "manufacture_stock_entry", se_doc.name)
        frappe.db.commit()

        msg = f"<b>Step 1 — Draft SE Created!</b><br>"
        msg += f"<a href='/app/stock-entry/{se_doc.name}' target='_blank'><b>Open {se_doc.name}</b></a><br>"
        msg += f"FG Weight: <b>{actual_qty} Kg</b><br>"
        msg += f"<span style='color:orange'>⚠️ Edit RM quantities in SE → Submit SE → Come back here → Click Submit Production again.</span>"

        return {"success": True, "stock_entry": msg}

    except Exception as e:
        frappe.log_error(message=str(e), title="Roll Production Error")
        frappe.throw(f"Error: {str(e)}")

@frappe.whitelist()
def create_stock_entries_for_roll(doc_name):
    # This acts as an alias wrapper for the Submit Roll button action just in case 
    # it specifically expects to be named this way based on client logic
    return execute_production(doc_name)
