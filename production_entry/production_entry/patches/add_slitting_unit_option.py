import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    _ensure_option("Planning Table")
    _ensure_option("Planning sheet Item")
    frappe.db.commit()


def _ensure_option(doctype_name):
    meta = frappe.get_meta(doctype_name)
    df = meta.get_field("unit")
    if not df or (df.fieldtype or "") != "Select":
        return

    options = [str(x).strip() for x in str(df.options or "").split("\n") if str(x).strip()]
    if "Slitting Unit" not in options:
        options.append("Slitting Unit")
        make_property_setter(
            doctype_name,
            "unit",
            "options",
            "\n".join(options),
            "Text",
            for_doctype=False,
        )
