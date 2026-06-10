# -*- coding: utf-8 -*-
"""Backfill Planning sheet.custom_company from the linked Sales Order's company."""
import frappe


def execute():
	if not frappe.db.has_column("Planning sheet", "custom_company"):
		return
	frappe.db.sql(
		"""
		UPDATE `tabPlanning sheet` ps
		INNER JOIN `tabSales Order` so ON so.name = ps.sales_order
		SET ps.custom_company = so.company
		WHERE IFNULL(ps.custom_company, '') = ''
		  AND IFNULL(so.company, '') != ''
		"""
	)
	frappe.db.commit()
