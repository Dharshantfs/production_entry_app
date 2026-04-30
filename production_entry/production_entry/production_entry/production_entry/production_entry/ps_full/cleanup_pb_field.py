import frappe

def delete_pb_plan_field():
    frappe.connect()
    try:
        if frappe.db.exists('Custom Field', 'Planning sheet-custom_pb_plan_name'):
            frappe.delete_doc('Custom Field', 'Planning sheet-custom_pb_plan_name', force=True)
            frappe.db.commit()
            print("Successfully deleted 'custom_pb_plan_name' Custom Field from Planning sheet.")
        else:
            print("Custom Field 'custom_pb_plan_name' does not exist.")
    except Exception as e:
        print(f"Error deleting custom field: {str(e)}")
    finally:
        frappe.destroy()

if __name__ == "__main__":
    delete_pb_plan_field()
