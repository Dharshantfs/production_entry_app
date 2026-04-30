import frappe

def debug():
    frappe.connect()
    try:
        sheet_name = "PLAN-2026-00867"
        if not frappe.db.exists("Planning sheet", sheet_name):
            print(f"Sheet {sheet_name} not found")
            return
            
        doc = frappe.get_doc("Planning sheet", sheet_name)
        print(f"Sheet: {doc.name}, Date: {doc.custom_planned_date}, Plan: {doc.custom_plan_name}")
        for i in doc.items:
            print(f"  Item: {i.name}, Unit: {i.unit}, Code: {i.custom_plan_code}")
            
    finally:
        frappe.destroy()

if __name__ == "__main__":
    debug()
