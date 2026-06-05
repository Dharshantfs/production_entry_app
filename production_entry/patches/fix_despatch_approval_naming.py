# -*- coding: utf-8 -*-
import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	make_property_setter(
		"Despatch Approval",
		None,
		"autoname",
		"format:DESP-APPR-{YYYY}-{#####}",
		"Data",
		for_doctype=True,
	)
	frappe.db.commit()
