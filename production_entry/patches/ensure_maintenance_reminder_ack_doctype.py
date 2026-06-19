# -*- coding: utf-8 -*-
"""Ensure Maintenance Reminder Ack DocType exists for Production Table tonnage reminders."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	if frappe.db.exists("DocType", "Maintenance Reminder Ack"):
		return
	app_path = frappe.get_app_path("production_entry")
	json_path = os.path.join(
		app_path,
		"production_planning",
		"doctype",
		"maintenance_reminder_ack",
		"maintenance_reminder_ack.json",
	)
	if not os.path.isfile(json_path):
		return
	import_file_by_path(json_path, force=True, ignore_version=True)
	frappe.clear_cache(doctype="Maintenance Reminder Ack")
	frappe.db.commit()
