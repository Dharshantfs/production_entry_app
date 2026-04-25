import frappe

def execute():
    print("Starting Global Cleanup of Duplicate Planning Sheet Items...")
    
    # 1. Find all duplicate sales_order_item names
    duplicates = frappe.db.sql("""
        SELECT sales_order_item, COUNT(*) as cnt
        FROM `tabPlanning Sheet Item`
        WHERE sales_order_item IS NOT NULL AND sales_order_item != ''
        GROUP BY sales_order_item
        HAVING COUNT(*) > 1
    """, as_dict=True)
    
    print(f"Found {len(duplicates)} Sales Order Items with duplicates.")
    
    removed_count = 0
    for dup in duplicates:
        so_item = dup.sales_order_item
        
        # Fetch all records for this so_item
        # We also need to know if they are pushed to PB (plannedDate) and their parent plan
        items = frappe.db.sql("""
            SELECT it.name, it.parent, it.plannedDate, ps.custom_plan_name, it.creation
            FROM `tabPlanning Sheet Item` it
            JOIN `tabPlanning sheet` ps ON it.parent = ps.name
            WHERE it.sales_order_item = %s
            ORDER BY 
                CASE WHEN it.plannedDate IS NOT NULL AND it.plannedDate != '' THEN 0 ELSE 1 END,
                CASE WHEN ps.custom_plan_name IS NOT NULL AND ps.custom_plan_name != 'Default' AND ps.custom_plan_name != '' THEN 0 ELSE 1 END,
                it.creation DESC
        """, (so_item,), as_dict=True)
        
        if len(items) <= 1:
            continue
            
        # The first item in the sorted list is the one we KEEP
        keep_name = items[0].name
        to_remove = [it.name for it in items[1:]]
        
        print(f"SO Item {so_item}: Keeping {keep_name}, Removing {to_remove}")
        
        for name in to_remove:
            frappe.db.delete("Planning Sheet Item", {"name": name})
            removed_count += 1
            
    frappe.db.commit()
    print(f"Cleanup complete. Removed {removed_count} duplicate records.")

if __name__ == "__main__":
    execute()
