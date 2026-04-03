import frappe
from frappe.utils import getdate

def debug_seeds():
    unit = "Unit 1"
    target_date = "2026-03-13" # Based on screenshot
    
    print(f"--- Debugging Seed Detection for {unit} on {target_date} ---")
    
    # 1. Check all items for that unit (regardless of date/status) to see naming
    all_units = frappe.db.sql("SELECT DISTINCT unit FROM `tabPlanning Sheet Item` LIMIT 20", as_dict=True)
    print(f"Distinct units in DB: {[r.unit for r in all_units]}")
    
    # 2. Check items on target date
    items = frappe.db.sql("""
        SELECT i.name, i.color, i.unit, p.name as sheet, p.docstatus, 
               p.custom_planned_date, p.ordered_date,
               COALESCE(p.custom_planned_date, p.ordered_date) as effective_date
        FROM `tabPlanning Sheet Item` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        WHERE (TRIM(i.unit) = %s OR TRIM(i.unit) = UPPER(%s))
          AND COALESCE(p.custom_planned_date, p.ordered_date) = %s
    """, (unit, unit, target_date), as_dict=True)
    
    print(f"Items found for {unit} on {target_date} (ignoring docstatus): {len(items)}")
    for it in items:
        print(f"  - {it.name}: {it.color} | Unit: [{it.unit}] | Sheet: {it.sheet} | Docstatus: {it.docstatus} | Effective Date: {it.effective_date}")

    # 3. Check for any items on that date to see what units exist
    any_items = frappe.db.sql("""
        SELECT i.unit, COUNT(*) as count
        FROM `tabPlanning Sheet Item` i
        JOIN `tabPlanning sheet` p ON i.parent = p.name
        WHERE COALESCE(p.custom_planned_date, p.ordered_date) = %s
        GROUP BY i.unit
    """, (target_date,), as_dict=True)
    print(f"Units found on {target_date}: {any_items}")

if __name__ == "__main__":
    debug_seeds()
