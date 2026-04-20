import frappe

def add_split_fields():
    fields = [
        {
            "dt": "Planning Sheet Item",
            "fieldname": "custom_split_from",
            "label": "Split From",
            "fieldtype": "Link",
            "options": "Planning Sheet Item",
            "insert_after": "idx",
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
        print("Split tracking field created successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    frappe.init(site="jayashreespunbond-1zt.frappe.cloud")
    frappe.connect()
    add_split_fields()
    frappe.destroy()
