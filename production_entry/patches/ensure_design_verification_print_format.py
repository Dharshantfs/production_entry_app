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
	if not frappe.db.exists("DocType", "Design Master"):
		return
	name = "Design Verification Checklist"
	if frappe.db.exists("Print Format", name):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Print Format",
			"name": name,
			"doc_type": "Design Master",
			"module": "Production Planning",
			"print_format_type": "Jinja",
			"standard": "No",
			"custom_format": 1,
			"html": PRINT_HTML,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
