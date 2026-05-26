import frappe

def execute():
    # Remove any Property Setters that force custom_unit to be a Select field
    frappe.db.sql("""
        DELETE FROM `tabProperty Setter` 
        WHERE doc_type = 'Shaft Production Run' 
        AND field_name = 'custom_unit' 
        AND property IN ('fieldtype', 'options')
    """)
    
    # Also fix it for Production Plan, Work Order, Stock Entry if they have similar overrides
    frappe.db.sql("""
        DELETE FROM `tabProperty Setter` 
        WHERE doc_type IN ('Production Plan', 'Work Order', 'Stock Entry') 
        AND field_name = 'custom_unit' 
        AND property IN ('fieldtype', 'options')
    """)
    
    # If custom_unit was accidentally created as a Custom Field, we need to update it there too
    frappe.db.sql("""
        UPDATE `tabCustom Field`
        SET fieldtype = 'Link', options = 'Workstation'
        WHERE fieldname = 'custom_unit' 
        AND dt IN ('Shaft Production Run', 'Production Plan', 'Work Order', 'Stock Entry')
    """)
    
    frappe.clear_cache(doctype="Shaft Production Run")
    frappe.clear_cache(doctype="Production Plan")
    frappe.clear_cache(doctype="Work Order")
    frappe.clear_cache(doctype="Stock Entry")
