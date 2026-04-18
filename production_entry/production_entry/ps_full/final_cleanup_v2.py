import frappe

# --- 1. CLEAN UP ORPHANED ITEMS ---
# Deletes items that have a parent sheet name that DOES NOT exist in tabPlanning sheet
print("Cleaning up orphaned Planning Sheet Items...")
orphans = frappe.db.sql("""
    DELETE i FROM `tabPlanning Sheet Item` i
    LEFT JOIN `tabPlanning sheet` p ON i.parent = p.name
    WHERE p.name IS NULL
""")
print(f"Purged orphans from database.")

# --- 2. DEDUPLICATE ITEMS WITHIN SHEETS ---
# If a sheet accidentally has the same Sales Order Item twice, remove the duplicate
print("Deduplicating items within existing sheets...")
frappe.db.sql("""
    DELETE i1 FROM `tabPlanning Sheet Item` i1
    JOIN `tabPlanning Sheet Item` i2 ON i1.parent = i2.parent 
        AND i1.sales_order_item = i2.sales_order_item
        AND i1.name > i2.name
""")
print("Deduplication complete.")

# --- 3. FIX SPECIFIC DUPLICATE SHEET (IF NEEDED) ---
# Check if PLAN-2026-00786 still exists and has docstatus 0
sheet_name = "PLAN-2026-00786"
if frappe.db.exists("Planning sheet", sheet_name):
    status = frappe.db.get_value("Planning sheet", sheet_name, "docstatus")
    if status == 0:
        print(f"Found active sheet {sheet_name}. Deleting it properly...")
        frappe.delete_doc("Planning sheet", sheet_name, force=1)
        print(f"Successfully deleted {sheet_name} and its child items.")
    else:
        print(f"Sheet {sheet_name} exists but status is {status}. Skipping deletion.")

frappe.db.commit()
print("\n--- ALL CLEANUP TASKS COMPLETE ---")
