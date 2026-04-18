import frappe

def execute():
    frappe.logger().info("Starting legacy data migration to Planning Table...")
    
    # 0. Fix corrupted status data globally first to bypass validation crashes
    # We try both potential table names just in case
    try:
        frappe.db.sql("UPDATE `tabPlanning sheet` SET status = 'Locked (WO Created)' WHERE status = 'Locked (WO created)'")
        frappe.db.commit()
    except Exception:
        pass
        
    try:
        frappe.db.sql("UPDATE `tabPlanning sheet` SET planning_status = 'Locked (WO Created)' WHERE planning_status = 'Locked (WO created)'")
        frappe.db.commit()
    except Exception:
        pass

    # 1. Get all Planning Sheets
    planning_sheets = frappe.get_all("Planning sheet", pluck="name")
    
    total_migrated = 0
    
    for ps_name in planning_sheets:
        doc = frappe.get_doc("Planning sheet", ps_name)
        
        # Check if it already has planned_items populated
        # We rely on your UI name 'planned_items' but we will check all possibilities
        target_field = None
        for field in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
            if hasattr(doc, field) or doc.meta.has_field(field):
                target_field = field
                break
                
        if not target_field:
            continue # No target table found on this doctype
            
        existing_new_items = getattr(doc, target_field, [])
        if len(existing_new_items) > 0:
            continue # Already migrated or partially migrated, skip to be safe!
            
        old_items = getattr(doc, "items", [])
        if not old_items:
            continue # No legacy items
            
        # 5. Get the actual Child Doctype name from the field metadata
        child_doctype = doc.meta.get_field(target_field).options
        if not child_doctype:
            continue
            
        # Migrate each row
        for old_row in old_items:
            # Create a new child doc but use db_insert to bypass Submit checks
            new_row = frappe.new_doc(child_doctype)
            new_row.parent = doc.name
            new_row.parentfield = target_field
            new_row.parenttype = "Planning sheet"
            
            # Helper to safely copy fields
            def copy_field(target_doc, source_doc, target_field_name, source_field_name):
                val = source_doc.get(source_field_name)
                if val is not None:
                    target_doc.set(target_field_name, val)

            # Copy standard fields
            fields_to_copy = [
                "sales_order_item", "item_code", "item_name", "qty", "uom", 
                "color", "unit", "custom_quality", "gsm", "width_inch", 
                "idx", "party_code"
            ]
            for f in fields_to_copy:
                copy_field(new_row, old_row, f, f)
            
            # Map special/renamed fields
            copy_field(new_row, old_row, "spr_name", "custom_spr_name")
            copy_field(new_row, old_row, "pp_id", "production_plan")
            copy_field(new_row, old_row, "planned_date", "custom_item_planned_date")
            copy_field(new_row, old_row, "plan_name", "custom_plan_code")
            copy_field(new_row, old_row, "is_split", "custom_is_split")
            copy_field(new_row, old_row, "split_from", "custom_split_from")
            
            if new_row.get("is_split") is None:
                new_row.is_split = 0
            
            # Bypass validation by using db_insert directly on the child row
            new_row.db_insert()
            total_migrated += 1
            
    frappe.db.commit()
    print(f"Migration Complete! Successfully migrated {total_migrated} legacy rows into the new {child_doctype} table across all statuses.")
