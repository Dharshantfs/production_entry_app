import frappe


def execute():
    # Add custom fields to Planning sheet header
    try:
        if not frappe.db.exists("Custom Field", "Planning sheet-custom_design_attachment"):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Planning sheet",
                "label": "Design Attachment",
                "fieldname": "custom_design_attachment",
                "fieldtype": "Attach",
                "insert_after": "notes",
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "add_process_105_fields_header_error")

    # Child table: Planning sheet Item
    child = "Planning sheet Item"
    def add_child_field(fname, label, ftype, options=None):
        key = f"{child}-{fname}"
        try:
            if not frappe.db.exists("Custom Field", key):
                doc = frappe.get_doc({
                    "doctype": "Custom Field",
                    "dt": child,
                    "label": label,
                    "fieldname": fname,
                    "fieldtype": ftype,
                })
                if options:
                    doc.options = options
                doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"add_child_field_{fname}")

    add_child_field("custom_design_code", "Design Code", "Data")
    add_child_field("custom_design_name", "Design Name", "Data")
    add_child_field("custom_design_image", "Design Image", "Attach")
    add_child_field("custom_printing_shift", "Printing Shift", "Select", "Day\nNight")
    add_child_field("custom_printing_arrangement_seq", "Printing Arrangement Seq", "Int")

    # Create Workstation records if not present
    units = [
        "JVE - PRINTING MACHINE 2 COLOUR",
        "JVE - PRINTING MACHINE 6 COLOUR",
        "UNASSIGNED PRINTING MACHINE",
    ]
    for u in units:
        try:
            if not frappe.db.exists("Workstation", u):
                frappe.get_doc({
                    "doctype": "Workstation",
                    "workstation_name": u,
                    "name": u,
                }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"create_workstation_{u}")
