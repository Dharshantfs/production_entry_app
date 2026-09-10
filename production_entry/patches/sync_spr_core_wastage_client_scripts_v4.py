# -*- coding: utf-8 -*-
"""Re-sync SPR Client Scripts after draft auto-save / wastage repair updates."""
from production_entry.patches.sync_spr_core_wastage_client_scripts import execute as _sync


def execute():
	_sync()
