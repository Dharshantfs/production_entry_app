# -*- coding: utf-8 -*-
"""
Canonical Planning DocType names — must match planning_sheet*.json and live DB (`tabPlanning sheet`).

Use these constants anywhere code references the doctype string (no literals like "Planning Sheet").
"""

PLANNING_SHEET = "Planning sheet"
PLANNING_SHEET_ITEM = "Planning sheet Item"

# Old names from earlier app JSON / deploys (for migration helpers only).
LEGACY_PLANNING_SHEET = "Planning Sheet"
LEGACY_PLANNING_SHEET_ITEM = "Planning Sheet Item"
