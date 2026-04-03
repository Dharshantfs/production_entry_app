import frappe

def check_columns():
    try:
        cols = frappe.db.get_table_columns("Planning Sheet Item")
        print(f"Columns in Planning Sheet Item: {cols}")
        
        has_split = "custom_is_split" in cols
        print(f"Has custom_is_split: {has_split}")
        
        # Also check if any items have it set
        if has_split:
            counts = frappe.db.sql("SELECT custom_is_split, count(*) FROM `tabPlanning Sheet Item` GROUP BY custom_is_split")
            print(f"Splits counts: {counts}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    frappe.init(site="jayashreespunbond-1zt.frappe.cloud")
    frappe.connect()
    check_columns()
    frappe.destroy()
