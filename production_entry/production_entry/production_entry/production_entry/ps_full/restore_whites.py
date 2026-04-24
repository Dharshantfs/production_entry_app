import frappe

def restore():
    frappe.connect()
    # Find sheets modified in last hour where planned_date is now empty
    sheets = frappe.db.sql("""
        SELECT name, ordered_date FROM `tabPlanning sheet`
        WHERE modified > DATE_SUB(NOW(), INTERVAL 1 HOUR)
          AND (custom_planned_date IS NULL OR custom_planned_date = '')
    """, as_dict=True)
    
    restored = 0
    for s in sheets:
        # If the sheet is White, it should probably have its planned_date = ordered_date
        # to appear back on the Board if it was already there.
        # But we don't know for sure if it was pushed.
        pass
        
    print(f"Found {len(sheets)} potentially affected sheets.")
    frappe.destroy()

if __name__ == "__main__":
    restore()
