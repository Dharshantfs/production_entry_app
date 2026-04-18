import frappe
frappe.connect()
items = frappe.db.get_all('Planning Sheet Item', 
    filters={'parent': 'PLAN-2026-00867'}, 
    fields=['name', 'unit', 'custom_plan_code'])
for i in items:
    print(i)
frappe.destroy()
