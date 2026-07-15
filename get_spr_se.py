import frappe
def get_spr_stock_entries():
    spr_name = "SPR-2026-00457" # From screenshot
    entries = frappe.get_all("Stock Entry", filters={"shaft_production_run": spr_name, "docstatus": 1}, fields=["name", "work_order", "production_item", "fg_completed_qty"])
    with open("c:/Users/Dharshan S S/Desktop/erp/spr_entries.json", "w") as f:
        import json
        json.dump(entries, f, indent=4)
