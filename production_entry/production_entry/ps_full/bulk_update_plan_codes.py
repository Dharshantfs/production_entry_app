import frappe
from production_scheduler.api import update_sheet_plan_codes

def bulk_update():
    frappe.connect()
    # Get all unlocked planning sheets
    sheets = frappe.get_all("Planning sheet", filters={"docstatus": 0})
    print(f"Found {len(sheets)} sheets to update.")
    
    for s in sheets:
    	try:
    		doc = frappe.get_doc("Planning sheet", s.name)
    		update_sheet_plan_codes(doc)
    		
    		# Update DB for parent
    		frappe.db.sql("UPDATE `tabPlanning sheet` SET custom_plan_code = %s WHERE name = %s", (doc.custom_plan_code, doc.name))
    		
    		# Update DB for children
    		for d in doc.items:
    			frappe.db.sql("UPDATE `tabPlanning Sheet Item` SET custom_plan_code = %s WHERE name = %s", (d.custom_plan_code, d.name))
    			
    		print(f"Updated {doc.name}")
    	except Exception as e:
    		print(f"Error updating {s.name}: {str(e)}")
    
    frappe.db.commit()
    print("Done.")

if __name__ == "__main__":
    bulk_update()
