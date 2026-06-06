import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from production_entry.production_planning.parent_fabric_options import PARENT_FABRIC_OPTIONS


def execute():
	create_custom_fields(
		{
			"Planning Table": [
				{
					"fieldname": "custom_parent_fabric",
					"label": "Parent Fabric",
					"fieldtype": "Select",
					"options": PARENT_FABRIC_OPTIONS,
					"read_only": 1,
					"insert_after": "custom_parent_child_trace_id",
					"in_list_view": 1,
				}
			],
			"Planning sheet Item": [
				{
					"fieldname": "custom_parent_fabric",
					"label": "Parent Fabric",
					"fieldtype": "Select",
					"options": PARENT_FABRIC_OPTIONS,
					"read_only": 1,
					"insert_after": "custom_parent_child_trace_id",
					"in_list_view": 1,
				}
			],
		},
		ignore_validate=True,
		update=True,
	)
	frappe.db.commit()
