import frappe

def inspect_sheet(name):
    print(f"\n--- Investigating {name} ---")
    doc = frappe.get_doc("Planning sheet", name)
    print(f"Sales Order: {doc.sales_order}")
    print(f"Order Code: {doc.custom_order_code or doc.order_code}")
    print(f"Plan Name: {doc.custom_plan_name}")
    print(f"Status: {doc.docstatus}")
    
    print("\nItems in this sheet:")
    items = frappe.get_all("Planning Sheet Item", 
        filters={"parent": name},
        fields=["name", "sales_order", "sales_order_item", "item_code", "qty", "color", "parent"]
    )
    for i in items:
        # Check if the item's sales_order matches the sheet's sales_order
        mismatch = " [MISMATCH!]" if i.sales_order != doc.sales_order else ""
        print(f"  - Item: {i.item_code}, SO: {i.sales_order}, SO_Item: {i.sales_order_item}, Qty: {i.qty}{mismatch}")

if __name__ == "__main__":
    try:
        inspect_sheet("PLAN-2026-00786")
        inspect_sheet("PLAN-2026-00795")
    except Exception as e:
        print(f"Error: {e}")
