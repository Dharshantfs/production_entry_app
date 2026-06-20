# -*- coding: utf-8 -*-
"""Ensure Design Verification Checklist Print Format exists for Design Master."""

import frappe


PRINT_HTML = """
{% if doc.checklist_view_html %}
{{ doc.checklist_view_html | safe }}
{% else %}
<p>No checklist generated yet. Save a Design Master record with a PDF in design_image.</p>
{% endif %}
"""


def execute():
	dt = None
	for candidate in ("DESIGN MASTER", "Design Master", "Design master"):
		if frappe.db.exists("DocType", candidate):
			dt = candidate
			break
	if not dt:
		return
	name = "Design Verification Checklist"
	if frappe.db.exists("Print Format", name):
		frappe.db.set_value("Print Format", name, "doc_type", dt, update_modified=False)
		return
	doc = frappe.get_doc(
		{
			"doctype": "Print Format",
			"name": name,
			"doc_type": dt,
			"module": "Production Planning",
			"print_format_type": "Jinja",
			"standard": "No",
			"custom_format": 1,
			"html": PRINT_HTML,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
