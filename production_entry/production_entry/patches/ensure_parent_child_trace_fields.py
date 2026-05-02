import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


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
    _ensure_slitting_unit_option("Planning Table")
    _ensure_slitting_unit_option("Planning sheet Item")
    _force_existing_103_rows_to_slitting_unit()
    frappe.db.commit()


def _ensure_slitting_unit_option(doctype_name):
    meta = frappe.get_meta(doctype_name)
    df = meta.get_field("unit")
    if not df or (df.fieldtype or "") != "Select":
        return
    options = [str(x).strip() for x in str(df.options or "").split("\n") if str(x).strip()]
    if "Slitting Unit" in options:
        return
    options.append("Slitting Unit")
    make_property_setter(
        doctype_name,
        "unit",
        "options",
        "\n".join(options),
        "Text",
        for_doctype=False,
    )


def _force_existing_103_rows_to_slitting_unit():
    if frappe.db.has_column("Planning Table", "unit"):
        frappe.db.sql(
            """
            UPDATE `tabPlanning Table`
            SET unit = 'Slitting Unit'
            WHERE item_code LIKE '103%%'
            """
        )
    if frappe.db.has_column("Planning sheet Item", "unit"):
        frappe.db.sql(
            """
            UPDATE `tabPlanning sheet Item`
            SET unit = 'Slitting Unit'
            WHERE item_code LIKE '103%%'
            """
        )
