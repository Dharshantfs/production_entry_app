# -*- coding: utf-8 -*-
"""Per-user production board visibility (units, boards, date window)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, today

from production_entry.production_planning.planning_doctypes import (
	maintenance_unit_match_values,
	normalize_planning_unit_for_select,
)

DOCTYPE_ACCESS = "Production Board Access"
CHILD_DOCTYPES = ("Production Board Access Unit", "Production Board Access Board")
DATE_MODES = ("Today", "Last 24 Hours", "Last N Days", "Unlimited")

BOARD_SLUGS = (
	"production-board",
	"printing-order-board",
	"lamination-board",
	"slitting-board",
	"rewinding-board",
	"sheet-cutting-board",
	"printed-bopp-film-board",
	"box-bag-board",
	"w-cut-d-cut-board",
	"production-table",
	"color-chart",
	"confirm-orders",
	"planning",
)

# Kanban + table share one permission scope: allowing either grants both.
PRODUCTION_VIEW_SLUGS = ("production-board", "production-table")

_BOARD_SLUG_ALIASES = {
	"production-board": ("production-table",),
	"production-table": ("production-board",),
}


def _equivalent_board_slugs(board_slug: str | None) -> set[str]:
	slug = (board_slug or "").strip().lower()
	if not slug:
		return set()
	out = {slug}
	for a in _BOARD_SLUG_ALIASES.get(slug, ()) or ():
		if a:
			out.add(str(a).strip().lower())
	return out


def _expand_allowed_boards(slugs: list[str]) -> list[str]:
	"""Expand board list using alias rules while preserving input order."""
	out: list[str] = []
	seen: set[str] = set()
	for s in slugs or []:
		for eq in _equivalent_board_slugs(s) or {str(s).strip().lower()}:
			if eq and eq not in seen:
				seen.add(eq)
				out.append(eq)
	return out

API_BOARD_MAP = {
	"get_color_chart_data": "production-board",
	"get_kanban_board": "production-board",
	"get_color_sequences_range": "production-board",
	"get_printing_order_table_data": "printing-order-board",
	"get_lamination_order_table_data": "lamination-board",
	"get_slitting_order_table_data": "slitting-board",
	"get_rewinding_order_table_data": "rewinding-board",
	"get_sheet_cutting_order_table_data": "sheet-cutting-board",
	"get_printed_bopp_film_table_data": "printed-bopp-film-board",
	"get_box_bag_order_table_data": "box-bag-board",
	"get_w_cut_d_cut_order_table_data": "w-cut-d-cut-board",
	"get_bopp_bag_order_table_data": "printed-bopp-film-board",
}


def _is_privileged_user(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user in ("Administrator",) or "System Manager" in frappe.get_roles(user):
		return True
	return False


def _board_access_schema_ready() -> bool:
	return bool(frappe.db.exists("DocType", DOCTYPE_ACCESS))



def _access_docname_for_user(user: str) -> str | None:
	if not _board_access_schema_ready():
		return None
	return frappe.db.get_value(
		DOCTYPE_ACCESS,
		{"user": user, "active": 1},
		"name",
	)


@frappe.whitelist()
def get_production_board_user_context(board_slug: str | None = None):
	"""Return board access scope for the session user (page gate + Vue)."""
	scope = get_user_board_scope()
	board_slug = (board_slug or "").strip().lower()
	permitted = True
	if board_slug:
		if scope.get("unlimited"):
			permitted = True
		else:
			allowed = set(scope.get("allowed_boards") or [])
			permitted = bool(_equivalent_board_slugs(board_slug) & allowed)
	return {
		"permitted": permitted,
		"unlimited": bool(scope.get("unlimited")),
		"allowed_units": scope.get("allowed_units") or [],
		"allowed_boards": scope.get("allowed_boards") or [],
		"min_date": scope.get("min_date"),
		"max_date": scope.get("max_date"),
		"date_mode": scope.get("date_mode"),
		"allowed_dates": scope.get("allowed_dates") or [],
		"date_picker_frozen": bool(scope.get("date_picker_frozen")),
		"view_scope_locked": bool(scope.get("view_scope_locked")),
	}


def _resolve_allowed_unit_labels(raw: str) -> list[str]:
	"""Expand Workstation link / unit label to canonical board column names."""
	out: list[str] = []
	seen: set[str] = set()
	for v in maintenance_unit_match_values(raw):
		canon = normalize_planning_unit_for_select(v)
		if canon and canon not in seen:
			seen.add(canon)
			out.append(canon)
	if not out:
		fallback = normalize_planning_unit_for_select(raw) or (raw or "").strip()
		if fallback:
			out.append(fallback)
	return out


def _scope_from_access_doc(access_name: str) -> dict:
	doc = frappe.get_doc(DOCTYPE_ACCESS, access_name)
	date_mode = doc.date_mode or "Today"
	window_days = int(doc.date_window_days or 0)

	allowed_boards = []
	for row in doc.get("allowed_boards") or []:
		b = (row.board or "").strip().lower()
		if b:
			allowed_boards.append(b)
	allowed_boards = _expand_allowed_boards(allowed_boards)

	allowed_units: list[str] = []
	seen_units: set[str] = set()
	for row in doc.get("allowed_units") or []:
		u = (row.unit or "").strip()
		if not u:
			continue
		for label in _resolve_allowed_unit_labels(u):
			if label not in seen_units:
				seen_units.add(label)
				allowed_units.append(label)

	min_date, max_date = _date_window_for_mode(date_mode, window_days)
	allowed_dates = _allowed_dates_for_window(min_date, max_date)

	return {
		"unlimited": False,
		"allowed_units": allowed_units,
		"allowed_boards": allowed_boards,
		"min_date": min_date,
		"max_date": max_date,
		"date_mode": date_mode,
		"allowed_dates": allowed_dates,
		"date_picker_frozen": date_mode == "Today",
		"view_scope_locked": date_mode != "Unlimited",
	}


def get_user_board_scope(user: str | None = None) -> dict:
	user = user or frappe.session.user

	if not _board_access_schema_ready():
		if _is_privileged_user(user):
			return {
				"unlimited": True,
				"allowed_units": [],
				"allowed_boards": list(BOARD_SLUGS),
				"min_date": None,
				"max_date": None,
				"date_mode": "Unlimited",
				"allowed_dates": [],
				"date_picker_frozen": False,
				"view_scope_locked": False,
			}
		return {
			"unlimited": False,
			"allowed_units": [],
			"allowed_boards": [],
			"min_date": today(),
			"max_date": today(),
			"date_mode": "Today",
			"allowed_dates": [today()],
			"date_picker_frozen": True,
			"view_scope_locked": True,
		}

	# Explicit Production Board Access row always wins (even for System Manager).
	access_name = _access_docname_for_user(user)
	if access_name:
		return _scope_from_access_doc(access_name)

	if _is_privileged_user(user):
		return {
			"unlimited": True,
			"allowed_units": [],
			"allowed_boards": list(BOARD_SLUGS),
			"min_date": None,
			"max_date": None,
			"date_mode": "Unlimited",
			"allowed_dates": [],
			"date_picker_frozen": False,
			"view_scope_locked": False,
		}

	return {
		"unlimited": False,
		"allowed_units": [],
		"allowed_boards": [],
		"min_date": today(),
		"max_date": today(),
		"date_mode": "Today",
		"allowed_dates": [today()],
		"date_picker_frozen": True,
		"view_scope_locked": True,
	}


def _date_window_for_mode(date_mode: str, window_days: int) -> tuple[str | None, str | None]:
	mode = (date_mode or "Today").strip()
	today_s = today()
	if mode == "Unlimited":
		return None, None
	if mode == "Today":
		return today_s, today_s
	if mode == "Last 24 Hours":
		start = add_days(now_datetime().date(), -1)
		return str(start), today_s
	if mode == "Last N Days":
		days = max(1, window_days or 1)
		return str(add_days(today_s, -(days - 1))), today_s
	return today_s, today_s


def _allowed_dates_for_window(min_date: str | None, max_date: str | None) -> list[str]:
	if not min_date or not max_date:
		return []
	out: list[str] = []
	d = getdate(min_date)
	end = getdate(max_date)
	while d <= end:
		out.append(str(d))
		d = add_days(d, 1)
	return out


def assert_board_allowed(board_slug: str, user: str | None = None) -> None:
	scope = get_user_board_scope(user)
	if scope.get("unlimited"):
		return
	board_slug = (board_slug or "").strip().lower()
	if board_slug not in (scope.get("allowed_boards") or []):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def assert_unit_allowed(unit: str, user: str | None = None, scope: dict | None = None) -> None:
	scope = scope or get_user_board_scope(user)
	if scope.get("unlimited"):
		return
	allowed = scope.get("allowed_units") or []
	if not allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	allowed_expanded = set()
	for u in allowed:
		for v in maintenance_unit_match_values(u):
			allowed_expanded.add(normalize_planning_unit_for_select(v) or v)
		allowed_expanded.add(normalize_planning_unit_for_select(u) or u)
	for v in maintenance_unit_match_values(unit):
		if (normalize_planning_unit_for_select(v) or v) in allowed_expanded:
			return
	target = normalize_planning_unit_for_select(unit)
	if target in allowed_expanded:
		return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def clamp_date(value, user: str | None = None, scope: dict | None = None):
	if value in (None, ""):
		return value
	scope = scope or get_user_board_scope(user)
	if scope.get("unlimited"):
		return getdate(value)
	d = getdate(value)
	min_d = scope.get("min_date")
	max_d = scope.get("max_date")
	if min_d and d < getdate(min_d):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if max_d and d > getdate(max_d):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return d


def clamp_date_range(start_date, end_date, user: str | None = None, scope: dict | None = None) -> tuple:
	scope = scope or get_user_board_scope(user)
	if scope.get("unlimited"):
		return getdate(start_date), getdate(end_date)
	s = clamp_date(start_date, user=user, scope=scope)
	e = clamp_date(end_date, user=user, scope=scope)
	if s > e:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return s, e


def get_unit_sql_values(units: list | None = None, user: str | None = None) -> list[str]:
	scope = get_user_board_scope(user)
	if scope.get("unlimited"):
		return []
	source = units if units is not None else (scope.get("allowed_units") or [])
	out = set()
	for u in source:
		for v in maintenance_unit_match_values(u):
			if v:
				out.add(v)
	return sorted(out)


def enforce_board_read(
	board_slug: str,
	unit=None,
	date=None,
	start_date=None,
	end_date=None,
	user: str | None = None,
) -> dict:
	scope = get_user_board_scope(user)
	if not scope.get("unlimited"):
		assert_board_allowed(board_slug, user=user)
		if unit:
			assert_unit_allowed(unit, user=user, scope=scope)
		if date not in (None, ""):
			clamp_date(date, user=user, scope=scope)
		if start_date and end_date:
			clamp_date_range(start_date, end_date, user=user, scope=scope)
	return scope


def enforce_board_write(board_slug: str | None, unit=None, date=None, user: str | None = None) -> dict:
	scope = get_user_board_scope(user)
	if scope.get("unlimited"):
		return scope
	if board_slug:
		assert_board_allowed(board_slug, user=user)
	if unit:
		assert_unit_allowed(unit, user=user, scope=scope)
	if date not in (None, ""):
		clamp_date(date, user=user, scope=scope)
	return scope


def request_board_slug(default: str | None = None) -> str:
	return (
		(frappe.form_dict.get("board_slug") or frappe.form_dict.get("board") or default or "")
		.strip()
		.lower()
	)


def board_slug_for_api(api_name: str) -> str:
	return API_BOARD_MAP.get(api_name, "production-board")
