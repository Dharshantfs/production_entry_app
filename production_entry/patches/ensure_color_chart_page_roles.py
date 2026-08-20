# -*- coding: utf-8 -*-
"""Ensure Color Chart Page roles include Operator/All so desk search can see it.

Also reloads Page metadata after Production Board Access page-permission hooks.
"""
from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("Page", "color-chart"):
		return

	needed = ("Operator", "Manufacturing User", "Manufacturing Manager")
	existing = {
		r.role
		for r in frappe.get_all(
			"Has Role",
			filters={"parent": "color-chart", "parenttype": "Page"},
			fields=["role"],
		)
	}
	page = frappe.get_doc("Page", "color-chart")
	changed = False
	for role in needed:
		if role in existing:
			continue
		if role != "All" and not frappe.db.exists("Role", role):
			continue
		page.append("roles", {"role": role})
		changed = True
	if changed:
		page.flags.ignore_permissions = True
		page.save(ignore_permissions=True)
		frappe.db.commit()
	frappe.clear_cache()
