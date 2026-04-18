import frappe

def check_and_create_field():
    frappe.init('1zt.frappe.cloud')
    frappe.connect()
    
    fields = [f.fieldname for f in frappe.get_meta('Planning Sheet Item').fields]
    print(f"Fields in Planning Sheet Item: {fields}")
    
    if "planned_date" not in fields and "custom_planned_date" not in fields:
        print("Creating custom field for planned_date...")
        # Create Custom Field
        doc = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Planning Sheet Item",
            "fieldname": "planned_date",
            "label": "Planned Date",
            "fieldtype": "Date",
            "insert_after": "unit"
        })
        doc.insert()
        frappe.db.commit()
        print("Created planned_date custom field.")
    elif "planned_date" in fields:
        print("planned_date already exists.")
    elif "custom_planned_date" in fields:
        print("custom_planned_date already exists.")

if __name__ == "__main__":
    check_and_create_field()
