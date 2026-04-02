from __future__ import print_function
import frappe
import json

frappe.init(site='production_entry')
frappe.connect()

pp = frappe.get_doc("Production Plan", "MFG-PP-2026-00203")

print("--- ASSEMBLY ITEMS (po_items) ---")
if pp.get("po_items"):
    print(json.dumps(pp.po_items[0].as_dict(), default=str, indent=2))
else:
    print("No po_items")

print("\n--- WORK ORDERS ---")
wos = frappe.get_all("Work Order", filters={"production_plan": "MFG-PP-2026-00203"}, fields=["name", "production_item", "qty"])
for w in wos:
    print(f"WO: {w['name']}, Item: {w['production_item']}, Qty: {w['qty']}")
