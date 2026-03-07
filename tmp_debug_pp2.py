import frappe
from __future__ import print_function
import json

frappe.init(site='production_entry')
frappe.connect()

pp = frappe.get_doc("Production Plan", "MFG-PP-2026-00203")

print("--- ASSEMBLY ITEMS (po_items) ---")
if pp.get("po_items"):
    print(json.dumps(pp.po_items[0].as_dict(), default=str, indent=2))
else:
    print("No po_items")
