import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    custom_fields = {
        "Planning Table": [
            {
                "fieldname": "custom_parent_child_trace_id",
                "label": "Parent Child Trace ID",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "custom_lamination_order_code_",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_slitting_shift",
                "label": "Slitting Shift",
                "fieldtype": "Select",
                "options": "DAY\nNIGHT",
                "default": "DAY",
                "insert_after": "custom_lamination_shift",
                "in_list_view": 1,
            },
        ],
        "Planning sheet Item": [
            {
                "fieldname": "custom_parent_child_trace_id",
                "label": "Parent Child Trace ID",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "custom_lamination_order_code",
            }
        ],
    }

    create_custom_fields(custom_fields, ignore_validate=True, update=True)
    frappe.db.commit()
