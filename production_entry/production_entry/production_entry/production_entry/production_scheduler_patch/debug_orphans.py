import frappe

def check_orphans():
    print("Checking for orphaned Planning Sheet Items...")
    orphans = frappe.db.sql("""
        SELECT i.name, i.parent, i.sales_order_item
        FROM `tabPlanning Sheet Item` i
        LEFT JOIN `tabPlanning sheet` p ON i.parent = p.name
        WHERE p.name IS NULL
    """, as_dict=True)
    
    if orphans:
        print(f"Found {len(orphans)} orphaned items.")
        for o in orphans:
            print(f"  - Item {o.name} (Parent: {o.parent}, SO Item: {o.sales_order_item})")
    else:
        print("No orphaned items found.")

def check_duplicates_in_sheets():
    print("\nChecking for duplicate SO items within the same Planning Sheet...")
    dups = frappe.db.sql("""
        SELECT parent, sales_order_item, COUNT(*) as cnt
        FROM `tabPlanning Sheet Item`
        GROUP BY parent, sales_order_item
        HAVING COUNT(*) > 1
    """, as_dict=True)
    
    if dups:
        print(f"Found {len(dups)} duplicate associations.")
        for d in dups:
            print(f"  - Sheet {d.parent}: SO Item {d.sales_order_item} appears {d.cnt} times.")
    else:
        print("No duplicates found within sheets.")

def check_sheet_existence(sheet_name):
    print(f"\nChecking existence of {sheet_name}...")
    exists = frappe.db.exists("Planning sheet", sheet_name)
    if exists:
        status = frappe.db.get_value("Planning sheet", sheet_name, "docstatus")
        print(f"  - {sheet_name} EXISTS. Docstatus: {status}")
    else:
        print(f"  - {sheet_name} DOES NOT EXIST in database.")

if __name__ == "__main__":
    check_orphans()
    check_duplicates_in_sheets()
    check_sheet_existence("PLAN-2026-00786")
    check_sheet_existence("PLAN-2026-00795")
