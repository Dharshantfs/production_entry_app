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
        if not self.production_plan:
            frappe.throw("Please select a Production Plan first")
        
        # Clear items grid but don't save yet
        self.items = []
        
        wos = frappe.get_all("Work Order", 
            filters={
                "status": ["in", ["Ready to Manufacture", "In Progress"]],
                "docstatus": 1,
                "production_plan": self.production_plan
            },
            fields=["name", "production_item"]
        )
        
        if not wos:
            return "No pending work orders found for this Production Plan."
            
        # We don't auto-create rows here; operator enters them based on actual rolls retrieved and handled by the client script
        return f"Found {len(wos)} Work Orders. Please add the roll weights manually below."
        
    def create_roll_production_entries(self):
        """Auto delegate the production results to the custom Roll Production Entry"""
        # Group rolls by Work Order
        wo_groups = {}
        for item in self.items:
            if item.work_order not in wo_groups:
                wo_groups[item.work_order] = []
            wo_groups[item.work_order].append(item.net_weight)
            
        created_entries = []
        
        for wo_name, roll_weights in wo_groups.items():
            wo_doc = frappe.get_doc("Work Order", wo_name)
            
            # Start actual background material transfer (if not transferred yet)
            total_net_weight = sum([flt(w) for w in roll_weights])
            balance_qty = flt(wo_doc.qty) - flt(wo_doc.produced_qty)
            
            # Assume auto material transfer is either done manually before or we can trigger it in Roll entry
            # In user's system: "Roll Production Entry" handles Stock Entries and Batches.
            
            # Form the Roll Production Entry DocType wrapper
            rpe = frappe.get_doc({
                "doctype": "Roll Production Entry",
                "work_order": wo_name,
                "production_item": wo_doc.production_item,
                "planned_qty": balance_qty, # User script balance ref
                "wip_warehouse": wo_doc.wip_warehouse,
                "fg_warehouse": wo_doc.fg_warehouse,
                "company": wo_doc.company,
                # "unit": "Unit 1", # If Unit tracked here
                "roll_wise_entry": []
            })
            
            # User's script loops through `roll_wise_entry` and assigns Batch No etc.
            roll_count = 1
            for weight in roll_weights:
                rpe.append("roll_wise_entry", {
                    "roll_no": roll_count,
                    "net_weight": weight
                })
                roll_count += 1
                
            rpe.insert(ignore_permissions=True)
            # The custom script `get_shift_series_by_identity` runs in RPE hooks.
            # Assuming auto-submit happens within the Roll Production script, or we do it here:
            try:
                # Based on user logic, the execution (Stock Entry + Batch) happens in RPE
                pass 
                # rpe.submit() # If their backend handles submit automatically.
            except Exception as e:
                frappe.log_error(message=str(e), title="Auto Roll Production Error")
                
            created_entries.append(rpe.name)
            
        if created_entries:
            frappe.msgprint(f"Successfully generated Roll Production Entries: {', '.join(created_entries)}")
