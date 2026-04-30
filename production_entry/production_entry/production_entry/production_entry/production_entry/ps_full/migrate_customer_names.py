"""
Migration script to populate custom_customer_name field in existing Planning Sheets.
This script should be run once to backfill the customer name for all existing Planning Sheets.
"""

import frappe

def migrate_customer_names():
    """Fetch all Planning Sheets and populate custom_customer_name from Customer master."""
    planning_sheets = frappe.get_all("Planning sheet", fields=["name", "customer"], limit_page_length=None)
    
    total = len(planning_sheets)
    updated = 0
    failed = 0
    
    print(f"Starting migration for {total} Planning Sheets...")
    
    for idx, sheet in enumerate(planning_sheets, 1):
        try:
            if not sheet.get("customer"):
                continue
            
            # Fetch customer name
            customer_doc = frappe.get_doc("Customer", sheet["customer"])
            customer_name = customer_doc.customer_name
            
            # Update the Planning Sheet
            frappe.db.set_value("Planning sheet", sheet["name"], "custom_customer_name", customer_name)
            updated += 1
            
            if idx % 50 == 0:
                print(f"Progress: {idx}/{total} - Updated: {updated}")
                frappe.db.commit()
        
        except Exception as e:
            failed += 1
            print(f"Failed for {sheet['name']}: {str(e)}")
    
    print(f"\n✅ Migration Complete!")
    print(f"Total: {total} | Updated: {updated} | Failed: {failed}")
    frappe.db.commit()

if __name__ == "__main__":
    migrate_customer_names()
