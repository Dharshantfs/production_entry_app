import frappe
import json

def restore():
    frappe.connect()
    # Find versions created in the last hour for Planning sheet
    versions = frappe.db.sql("""
        SELECT docname, data 
        FROM `tabVersion` 
        WHERE ref_doctype = 'Planning sheet' 
          AND modified > DATE_SUB(NOW(), INTERVAL 1 HOUR)
        ORDER BY modified DESC
    """, as_dict=True)
    
    restored_sheets = set()
    for v in versions:
        if not v.data: continue
        data = json.loads(v.data)
        
        # Look for changed values where custom_planned_date was cleared
        changed = data.get("changed", [])
        # 'changed' is usually a list of [fieldname, old_value, new_value]
        
        old_date = None
        was_cleared = False
        
        for field, old, new in changed:
            if field == "custom_planned_date" and old and not new:
                old_date = old
                was_cleared = True
                break
        
        if was_cleared and old_date and v.docname not in restored_sheets:
            # Only restore if it's currently empty
            current = frappe.db.get_value("Planning sheet", v.docname, "custom_planned_date")
            if not current:
                frappe.db.set_value("Planning sheet", v.docname, "custom_planned_date", old_date)
                # Also restore the pb plan name if cleared
                old_pb_plan = None
                for field, old_p, new_p in changed:
                    if field == "custom_pb_plan_name" and old_p and not new_p:
                        old_pb_plan = old_p
                        break
                if old_pb_plan:
                    frappe.db.set_value("Planning sheet", v.docname, "custom_pb_plan_name", old_pb_plan)
                
                print(f"Restored {v.docname} back to {old_date} ({old_pb_plan})")
                restored_sheets.add(v.docname)
                
    frappe.db.commit()
    print(f"Total sheets restored: {len(restored_sheets)}")
    frappe.destroy()

if __name__ == "__main__":
    restore()
