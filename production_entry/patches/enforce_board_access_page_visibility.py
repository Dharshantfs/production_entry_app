# -*- coding: utf-8 -*-
"""Enforce Production Board Access on desk pages (hide GSM unless granted)."""
from __future__ import annotations

import frappe


def execute():
	# Clear page caches so bootinfo / permission hooks apply after deploy.
	frappe.clear_cache()
	frappe.db.commit()
