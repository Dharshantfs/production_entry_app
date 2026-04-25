
import frappe

def execute():
    # Check distinct values of custom_production_status
    statuses = frappe.db.sql("SELECT DISTINCT custom_production_status FROM `tabSales Order`", as_dict=True)
    print("Distinct Statuses:", [s.custom_production_status for s in statuses])
    
    # Check counts for 'Confirmed'
    confirmed_count = frappe.db.count("Sales Order", {"custom_production_status": "Confirmed", "docstatus": 1})
    print(f"Confirmed (Submitted) Count: {confirmed_count}")
    
    draft_confirmed_count = frappe.db.count("Sales Order", {"custom_production_status": "Confirmed", "docstatus": 0})
    print(f"Confirmed (Draft) Count: {draft_confirmed_count}")
    
    # Check sample item
    sample = frappe.db.sql("""
        SELECT so.name, item.name as item_name 
        FROM `tabSales Order` so 
        JOIN `tabSales Order Item` item ON item.parent = so.name
        WHERE so.custom_production_status = 'Confirmed' 
        LIMIT 1
    """, as_dict=True)
    print("Sample Confirmed Item:", sample)

    if sample:
        # Check if this item is in Planning Sheet
        is_planned = frappe.db.sql("""
            SELECT name FROM `tabPlanning Sheet Item` 
            WHERE sales_order_item = %s AND docstatus < 2
        """, (sample[0].item_name,), as_dict=True)
        print("Is Planned?", is_planned)
