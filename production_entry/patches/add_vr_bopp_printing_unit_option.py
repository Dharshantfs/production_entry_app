# -*- coding: utf-8 -*-
"""Ensure Planning child tables accept VR BOPP printing unit (Select options + Property Setter)."""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

VR_UNIT = "VR - 1200MM BOPP PRINTING MACHINE"


def execute():
    for dt in ("Planning Table", "Planning sheet Item"):
        _ensure_vr_unit_option(dt)
    frappe.clear_cache(doctype="Planning Table")
    frappe.clear_cache(doctype="Planning sheet Item")
    frappe.db.commit()


def _ensure_vr_unit_option(doctype_name):
    meta = frappe.get_meta(doctype_name)
    df = meta.get_field("unit")
    if not df or (df.fieldtype or "") != "Select":
        return
    options = [str(x).strip() for x in str(df.options or "").split("\n") if str(x).strip()]
    changed = False
    if "Slitting Unit" not in options:
        options.append("Slitting Unit")
        changed = True
    if VR_UNIT not in options:
        options.append(VR_UNIT)
        changed = True
    if not changed:
        return
    make_property_setter(
        doctype_name,
        "unit",
        "options",
        "\n".join(options),
        "Text",
        for_doctype=False,
    )
