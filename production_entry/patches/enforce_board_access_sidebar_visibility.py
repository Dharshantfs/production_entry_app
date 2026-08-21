# -*- coding: utf-8 -*-
"""Clear cache so Production Board Access page visibility hooks take effect."""
from __future__ import annotations

import frappe


def execute():
	frappe.clear_cache()
	frappe.db.commit()
