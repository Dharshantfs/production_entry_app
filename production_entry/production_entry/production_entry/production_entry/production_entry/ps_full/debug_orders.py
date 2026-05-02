import frappe

def debug_unit_orders():
    frappe.connect()
    try:
        query = """
            SELECT 
                i.color, i.idx, p.name as sheet, p.docstatus, 
                i.custom_item_planned_date as item_date,
                p.custom_planned_date as sheet_date,
                p.modified
            FROM `tabPlanning Sheet Item` i
            JOIN `tabPlanning sheet` p ON i.parent = p.name
            WHERE REPLACE(UPPER(i.unit), ' ', '') = 'UNIT2'
              AND p.docstatus < 2
            ORDER BY 
              DATE(COALESCE(i.custom_item_planned_date, p.custom_planned_date, p.ordered_date)) DESC,
              i.idx DESC,
              p.modified DESC
            LIMIT 20
        """
        items = frappe.db.sql(query, as_dict=1)
        print("LAST 20 ITEMS FOR UNIT 2:")
        for it in items:
            print(f"- {it.color} (idx: {it.idx}, sheet: {it.sheet}, status: {it.docstatus}, item_date: {it.item_date}, sheet_date: {it.sheet_date}, mod: {it.modified})")
    finally:
        frappe.destroy()

if __name__ == "__main__":
    debug_unit_orders()
