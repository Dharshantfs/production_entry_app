import frappe
import json

frappe.init(site='production_entry')
frappe.connect()

pp_name = "MFG-PP-2026-00203"
pp = frappe.get_doc("Production Plan", pp_name)

print("--- custom_shaft_details row keys ---")
if pp.get("custom_shaft_details"):
    for row in pp.custom_shaft_details:
        if row.gsm and row.combination:
            print(json.dumps(row.as_dict().keys(), default=str))
            print(json.dumps(row.as_dict(), indent=2, default=str))
            break
else:
    print("No custom_shaft_details")
