# -*- coding: utf-8 -*-
"""Re-sync SPR wastage Client Scripts for live fieldnames (wastage_qty_kgs, meter_roll_mtrs)."""
from production_entry.patches.sync_spr_core_wastage_client_scripts import execute as _sync


def execute():
	_sync()
