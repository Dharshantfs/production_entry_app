import frappe

def check_sheet_db(name):
    print(f"\n--- Database Check for {name} ---")
    doc = frappe.get_doc("Planning sheet", name)
    print(f"Sheet docstatus: {doc.docstatus}")
    print(f"Items in Doc (Memory): {len(doc.items)}")
    
    db_items = frappe.db.sql("""
        SELECT name, item_code, color, qty, parent, parentfield, docstatus
        FROM `tabPlanning Sheet Item`
        WHERE parent = %s
    """, (name,), as_dict=True)
    
    print(f"Items in DB (Table): {len(db_items)}")
    for i in db_items:
        print(f"  - {i.name}: {i.item_code}, {i.color}, Qty: {i.qty}, PF: {i.parentfield}, DS: {i.docstatus}")

if __name__ == "__main__":
    try:
        check_sheet_db("PLAN-2026-00787")
    except Exception as e:
        print(f"Error: {e}")
