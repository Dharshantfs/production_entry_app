# -*- coding: utf-8 -*-
"""Re-sync SPR core/wastage Client Scripts (recycle field-map + unique-shaft core nos)."""
from production_entry.patches.sync_spr_core_wastage_client_scripts import execute as _sync


def execute():
	_sync()
