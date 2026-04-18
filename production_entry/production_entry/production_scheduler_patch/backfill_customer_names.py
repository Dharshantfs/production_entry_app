"""
Migration script to backfill customer names in all existing Planning Sheets.
"""
import frappe

def backfill_customer_names():
    planning_sheets = frappe.get_all('Planning sheet', fields=['name', 'customer'], limit_page_length=None)
    print(f'Found {len(planning_sheets)} Planning Sheets')
    
    updated = 0
    for sheet in planning_sheets:
        if not sheet.get('customer'):
            continue
        
        try:
            customer_doc = frappe.get_doc('Customer', sheet['customer'])
            customer_name = customer_doc.customer_name
        except:
            customer_name = sheet['customer']
        
        frappe.db.set_value('Planning sheet', sheet['name'], 'customer_name', customer_name)
        updated += 1
    
    frappe.db.commit()
    print(f'Updated {updated} Planning Sheets!')

if __name__ == '__main__':
    backfill_customer_names()
