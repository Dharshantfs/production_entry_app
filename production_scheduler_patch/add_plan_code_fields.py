import frappe

def create_custom_fields():
    fields = [
        {
            "dt": "Planning sheet",
            "fieldname": "custom_plan_code",
            "label": "Plan Code",
            "fieldtype": "Data",
            "insert_after": "custom_plan_name",
            "read_only": 1
        },
        {
            "dt": "Planning Sheet Item",
            "fieldname": "custom_plan_code",
            "label": "Plan Code",
            "fieldtype": "Data",
            "insert_after": "unit",
            "read_only": 1
        }
    ]
    
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    
    try:
        custom_fields = {}
        for f in fields:
            dt = f.pop("dt")
            if dt not in custom_fields:
                custom_fields[dt] = []
            custom_fields[dt].append(f)
            
        create_custom_fields(custom_fields)
        print("Custom fields created successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    frappe.init(site="jayashreespunbond-1zt.frappe.cloud")
    frappe.connect()
    create_custom_fields()
    frappe.destroy()
