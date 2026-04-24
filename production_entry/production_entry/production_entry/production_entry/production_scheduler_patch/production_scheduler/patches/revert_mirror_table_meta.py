import frappe

def execute():
    """Revert Planning Table metadata to fix the 'Unknown column parent' error."""
    # 1. Delete the custom table field that triggers the Child Table loading logic
    if frappe.db.exists("Custom Field", {"dt": "Planning sheet", "fieldname": "planning_table"}):
        frappe.db.delete("Custom Field", {"dt": "Planning sheet", "fieldname": "planning_table"})
    
    # 2. Reset Planning Table DocType to a standalone state (istable: 0)
    # This stops Frappe from treating it as a child table during form loads
    if frappe.db.exists("DocType", "Planning Table"):
        frappe.db.set_value("DocType", "Planning Table", "istable", 1)
        frappe.db.set_value("DocType", "Planning Table", "custom", 1)  # Ensure it remains a custom doc
    
    # 3. Clear cache and commit
    frappe.clear_cache(doctype="Planning sheet")
    frappe.clear_cache(doctype="Planning Table")
    frappe.db.commit()
