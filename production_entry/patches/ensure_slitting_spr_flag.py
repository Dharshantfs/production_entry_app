import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Shaft Production Run": [
                {
                    "fieldname": "custom_is_slitting",
                    "label": "Is Slitting",
                    "fieldtype": "Check",
                    "insert_after": "custom_is_lamination",
                    "default": "0",
                }
            ]
        },
        ignore_validate=True,
        update=True,
    )
    frappe.db.commit()
