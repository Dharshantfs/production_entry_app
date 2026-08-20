# -*- coding: utf-8 -*-
"""Split Color Chart + GSM into dedicated Production Board Access child tables.

Migrates legacy allowed_boards rows for color-chart / gsm-production-entry into
allowed_color_chart / allowed_gsm, and reloads DocType metadata.
"""
from __future__ import annotations

import frappe
from frappe.utils import cint

from production_entry.production_planning.board_access import sync_board_access_board_field_options

GSM_FREEZE_FIELDS = (
	"freeze_gsm_unit",
	"freeze_gsm_date",
	"freeze_gsm_shift",
	"freeze_gsm_add_row",
	"freeze_gsm_submit",
	"freeze_gsm_tools",
	"freeze_gsm_summary",
	"freeze_gsm_shift_entries",
	"freeze_gsm_clear_entries",
	"freeze_gsm_prev_shift",
)


def _normalize_board_slug(raw: str | None) -> str:
	s = (raw or "").strip().lower()
	if not s:
		return ""
	if "|" in s:
		s = s.split("|", 1)[0].strip()
	return s.replace("_", "-").replace(" ", "-").strip("-")


def execute():
	# Install / reload new child DocTypes + parent
	for dt in (
		"production_board_access_color_chart",
		"production_board_access_gsm",
		"production_board_access_board",
		"production_board_access",
	):
		try:
			frappe.reload_doc("production_planning", "doctype", dt, force=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"reload_{dt}")

	if not frappe.db.exists("DocType", "Production Board Access"):
		return
	if not frappe.db.exists("DocType", "Production Board Access Color Chart"):
		return
	if not frappe.db.exists("DocType", "Production Board Access GSM"):
		return

	parents = frappe.get_all("Production Board Access", pluck="name")
	for name in parents:
		doc = frappe.get_doc("Production Board Access", name)
		boards = list(doc.get("allowed_boards") or [])
		keep = []
		moved_cc = False
		moved_gsm = False

		for row in boards:
			slug = _normalize_board_slug(row.board)
			if slug == "color-chart":
				if not (doc.get("allowed_color_chart") or []) and not moved_cc:
					doc.append("allowed_color_chart", {})
					moved_cc = True
				continue
			if slug == "gsm-production-entry":
				if not (doc.get("allowed_gsm") or []) and not moved_gsm:
					gsm_row = {}
					for fn in GSM_FREEZE_FIELDS:
						if hasattr(row, fn):
							gsm_row[fn] = cint(getattr(row, fn, 0))
					doc.append("allowed_gsm", gsm_row)
					moved_gsm = True
				continue
			keep.append(row)

		if moved_cc or moved_gsm or len(keep) != len(boards):
			doc.set("allowed_boards", keep)
			doc.flags.ignore_validate = True
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)

	sync_board_access_board_field_options()
	frappe.clear_cache(doctype="Production Board Access")
	frappe.clear_cache(doctype="Production Board Access Board")
	frappe.db.commit()
