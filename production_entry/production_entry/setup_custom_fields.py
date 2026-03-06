import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    create_custom_fields({
        "Work Order": [
            {
                "fieldname": "custom_allocated_unit",
                "label": "Allocated Unit",
                "fieldtype": "Link",
                "options": "Unit Capacity",
                "insert_after": "status"
            },
            {
                "fieldname": "custom_quality",
                "label": "Quality",
                "fieldtype": "Data",
                "insert_after": "custom_allocated_unit"
            },
            {
                "fieldname": "custom_color",
                "label": "Color",
                "fieldtype": "Data",
                "insert_after": "custom_quality"
            },
            {
                "fieldname": "custom_width_inch",
                "label": "Width (Inch)",
                "fieldtype": "Float",
                "insert_after": "custom_color"
            },
            {
                "fieldname": "custom_gsm",
                "label": "GSM",
                "fieldtype": "Data",
                "insert_after": "custom_width_inch"
            }
        ]
    })
