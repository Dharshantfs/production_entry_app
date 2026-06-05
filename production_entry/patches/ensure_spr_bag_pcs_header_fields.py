# -*- coding: utf-8 -*-
"""Legacy patch — fields now live in shaft_production_run.json; only dedupe Custom Field rows."""
from production_entry.patches.cleanup_spr_duplicate_custom_fields import execute as cleanup_execute


def execute():
	cleanup_execute()
