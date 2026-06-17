# -*- coding: utf-8 -*-
"""Per-user production board visibility (units, boards, date window)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, today

from production_entry.production_planning.planning_doctypes import (
	maintenance_unit_match_values,
	normalize_planning_unit_for_select,
	W_CUT_D_CUT_ALL_UNITS,
	W_CUT_D_CUT_JVE_UNITS,
	W_CUT_D_CUT_VTP_UNITS,
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

# Boards shown in Production Board Access picker (table pages inherit via alias — do not list here).
BOARD_PICKER_SLUGS = (
	"production-board",
	"printing-order-board",
	"lamination-board",
	"slitting-board",
	"rewinding-board",
	"sheet-cutting-board",
	"printed-bopp-film-board",
	"box-bag-board",
	"w-cut-d-cut-board",
	"color-chart",
	"confirm-orders",
	"planning",
	"logistics-kanban",
	"despatch-approval-dashboard",
	"transfer-approval-dashboard",
)

BOARD_PICKER_LABELS = {
	"production-board": "Production Board (Kanban)",
	"printing-order-board": "Printing Order Board",
	"lamination-board": "Lamination Board",
	"slitting-board": "Slitting Board",
	"rewinding-board": "Rewinding Board",
	"sheet-cutting-board": "Sheet Cutting Board",
	"printed-bopp-film-board": "Printed BOPP Film Board",
	"box-bag-board": "Box Bag Board",
	"w-cut-d-cut-board": "W CUT / D CUT Board",
	"color-chart": "Color Chart",
	"confirm-orders": "Confirm Orders",
	"planning": "Planning",
	"logistics-kanban": "Logistics Kanban",
	"despatch-approval-dashboard": "Despatch Approval",
	"transfer-approval-dashboard": "Transfer Approval",
}

# Table / companion pages — access granted automatically when matching board is allowed.
_TABLE_PAGE_SUFFIXES = ("-order-table",)
_TABLE_PAGE_EXACT = frozenset({"production-table", "printed-bopp-film-table"})

# Kanban + table share one permission scope per process family.
PRODUCTION_VIEW_SLUGS = ("production-board", "production-table")

_BOARD_SLUG_ALIASES = {
	"production-board": ("production-table",),
	"production-table": ("production-board",),
	"printing-order-board": ("printing-order-table",),
	"printing-order-table": ("printing-order-board",),
	"lamination-board": ("lamination-order-table",),
	"lamination-order-table": ("lamination-board",),
	"slitting-board": ("slitting-order-table",),
	"slitting-order-table": ("slitting-board",),
	"rewinding-board": ("rewinding-order-table",),
	"rewinding-order-table": ("rewinding-board",),
	"sheet-cutting-board": ("sheet-cutting-order-table",),
	"sheet-cutting-order-table": ("sheet-cutting-board",),
	"printed-bopp-film-board": ("printed-bopp-film-table",),
	"printed-bopp-film-table": ("printed-bopp-film-board",),
	"box-bag-board": ("box-bag-order-table",),
	"box-bag-order-table": ("box-bag-board",),
	"w-cut-d-cut-board": ("w-cut-d-cut-order-table",),
	"w-cut-d-cut-order-table": ("w-cut-d-cut-board",),
}


def _normalize_board_slug(raw: str | None) -> str:
	"""Normalize Select values (slug|Label) and legacy typos like 'box bag-board'."""
	s = (raw or "").strip().lower()
	if not s:
		return ""
	if "|" in s:
		s = s.split("|", 1)[0].strip()
	s = s.replace("_", "-")
	s = s.replace(" ", "-")
	while "--" in s:
		s = s.replace("--", "-")
	return s.strip("-")


def _equivalent_board_slugs(board_slug: str | None) -> set[str]:
	slug = _normalize_board_slug(board_slug)
	if not slug:
		return set()
	out = {slug}
	for a in _BOARD_SLUG_ALIASES.get(slug, ()) or ():
		norm = _normalize_board_slug(a)
		if norm:
			out.add(norm)
	return out


def _expand_allowed_boards(slugs: list[str]) -> list[str]:
	"""Expand board list using alias rules while preserving input order."""
	out: list[str] = []
	seen: set[str] = set()
	for s in slugs or []:
		norm = _normalize_board_slug(s)
		if not norm:
			continue
		for eq in _equivalent_board_slugs(norm):
			if eq and eq not in seen:
				seen.add(eq)
				out.append(eq)
	return out

API_BOARD_MAP = {
	"get_color_chart_data": "production-board",
	"get_kanban_board": "production-board",
	"get_color_sequences_range": "production-board",
	"save_color_sequence": "production-board",
	"restore_last_color_sequence": "production-board",
	"get_transfer_eligible_rows": "production-board",
	"get_despatch_eligible_rows": "production-board",
	"get_printing_order_table_data": "printing-order-board",
	"get_lamination_order_table_data": "lamination-board",
	"get_slitting_order_table_data": "slitting-board",
	"get_rewinding_order_table_data": "rewinding-board",
	"get_sheet_cutting_order_table_data": "sheet-cutting-board",
	"get_printed_bopp_film_table_data": "printed-bopp-film-board",
	"get_box_bag_order_table_data": "box-bag-board",
	"get_w_cut_d_cut_order_table_data": "w-cut-d-cut-board",
	"get_bopp_bag_order_table_data": "box-bag-board",
}

# Transfer / despatch toolbar board_kind → page slug (Production Board Access).
BOARD_KIND_TO_SLUG = {
	"production": "production-board",
	"lamination": "lamination-board",
	"printing_105": "printing-order-board",
	"printed_bopp_film": "printed-bopp-film-board",
	"slitting": "slitting-board",
	"rewinding": "rewinding-board",
	"sheet_cutting": "sheet-cutting-board",
	"box_bag": "box-bag-board",
	"w_cut_d_cut": "w-cut-d-cut-board",
}


def _is_privileged_user(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user in ("Administrator",) or "System Manager" in frappe.get_roles(user):
		return True
	return False


def _user_has_operator_role(user: str | None = None) -> bool:
	"""Shop-floor Operator role — hide customer/party columns on board tables."""
	user = user or frappe.session.user
	if _is_privileged_user(user):
		return False
	return "Operator" in frappe.get_roles(user)


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
	board_slug_norm = _normalize_board_slug(board_slug)
	permitted = True
	frozen_actions: dict = {}
	w_cut_settings = {"company_scope": None, "company_scope_locked": False}
	if board_slug_norm:
		if scope.get("unlimited"):
			permitted = True
		else:
			allowed = set(scope.get("allowed_boards") or [])
			permitted = bool(_equivalent_board_slugs(board_slug_norm) & allowed)
			access_name = _access_docname_for_user(frappe.session.user)
			if access_name and permitted:
				frozen_actions = _frozen_actions_for_board(access_name, board_slug_norm)
				w_cut_settings = _w_cut_d_cut_settings_for_board(access_name, board_slug_norm)
	hide_customer_columns = bool(
		not scope.get("unlimited") and _user_has_operator_role(frappe.session.user)
	)
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
		"frozen_actions": frozen_actions,
		"w_cut_d_cut_company_scope": w_cut_settings.get("company_scope"),
		"company_scope_locked": bool(w_cut_settings.get("company_scope_locked")),
		"hide_customer_columns": hide_customer_columns,
	}


def _frozen_actions_for_board(access_name: str, board_slug: str) -> dict:
	"""Per-board toolbar freeze flags from Allowed Boards child rows."""
	from frappe.utils import cint

	doc = frappe.get_doc(DOCTYPE_ACCESS, access_name)
	requested = _equivalent_board_slugs(board_slug)
	for row in doc.get("allowed_boards") or []:
		row_slug = _normalize_board_slug(row.board)
		if not row_slug:
			continue
		if requested & _equivalent_board_slugs(row_slug):
			return {
				"maintenance": bool(cint(getattr(row, "freeze_maintenance", 0))),
				"transfer": bool(cint(getattr(row, "freeze_transfer", 0))),
				"despatch": bool(cint(getattr(row, "freeze_despatch", 0))),
				"arrangement": bool(cint(getattr(row, "freeze_arrangement", 0))),
				"assign_shift": bool(cint(getattr(row, "freeze_assign_shift", 0))),
				"sync_spr": bool(cint(getattr(row, "freeze_sync_spr", 0))),
				"merge": bool(cint(getattr(row, "freeze_merge", 0))),
				"reorder": bool(cint(getattr(row, "freeze_reorder", 0))),
			}
	return {}


_W_CUT_D_CUT_BOARD_SLUGS = frozenset({"w-cut-d-cut-board", "w-cut-d-cut-order-table"})


def _w_cut_d_cut_settings_for_board(access_name: str, board_slug: str) -> dict:
	"""Company scope for W CUT / D CUT board rows (JVE / VTP / both)."""
	requested = _equivalent_board_slugs(board_slug)
	if not (requested & _W_CUT_D_CUT_BOARD_SLUGS):
		return {"company_scope": None, "company_scope_locked": False}

	doc = frappe.get_doc(DOCTYPE_ACCESS, access_name)
	for row in doc.get("allowed_boards") or []:
		row_slug = _normalize_board_slug(row.board)
		if not row_slug or not (_equivalent_board_slugs(row_slug) & _W_CUT_D_CUT_BOARD_SLUGS):
			continue
		if not (requested & _equivalent_board_slugs(row_slug)):
			continue
		company = (getattr(row, "w_cut_d_cut_company", None) or "Both").strip()
		key = company.lower()
		if key not in ("jve", "vtp", "both"):
			key = "both"
		return {
			"company_scope": key,
			"company_scope_locked": key in ("jve", "vtp"),
		}
	return {"company_scope": None, "company_scope_locked": False}


def _workstations_for_w_cut_companies(companies: set[str]) -> set[str]:
	"""Union of workstation labels for JVE/VTP/Both company picks."""
	out: set[str] = set()
	for company in companies or {"both"}:
		c = (company or "both").strip().lower()
		if c == "jve":
			out.update(W_CUT_D_CUT_JVE_UNITS)
		elif c == "vtp":
			out.update(W_CUT_D_CUT_VTP_UNITS)
		else:
			out.update(W_CUT_D_CUT_ALL_UNITS)
	return out


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def production_board_access_workstation_query(doctype, txt, searchfield, start, page_len, filters):
	"""Workstation link search for Allowed Units — optional W/D Cut company filter."""
	filters = filters or {}
	txt = f"%{txt}%"
	w_cut_companies = filters.get("w_cut_companies") or []
	has_w_cut = bool(filters.get("has_w_cut"))
	has_other_boards = bool(filters.get("has_other_boards"))

	allowed_names: set[str] | None = None
	if has_w_cut and not has_other_boards:
		companies = w_cut_companies or ["BOTH"]
		allowed_names = _workstations_for_w_cut_companies(set(companies))

	conditions = ["w.name LIKE %(txt)s"]
	if allowed_names:
		placeholders = ", ".join([f"%(u{i})s" for i in range(len(allowed_names))])
		conditions.append(f"w.name IN ({placeholders})")
		params = {f"u{i}": v for i, v in enumerate(sorted(allowed_names))}
	else:
		params = {}

	params.update({"txt": txt, "start": start, "page_len": page_len})
	return frappe.db.sql(
		f"""
		SELECT w.name, w.name AS label
		FROM `tabWorkstation` w
		WHERE {" AND ".join(conditions)}
		ORDER BY w.name
		LIMIT %(start)s, %(page_len)s
		""",
		params,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def production_board_access_user_query(doctype, txt, searchfield, start, page_len, filters):
	"""User link search: show full name + email (assign by name)."""
	txt = f"%{txt}%"
	return frappe.db.sql(
		"""
		SELECT u.name, CONCAT(IFNULL(u.full_name, ''), ' — ', u.name) AS label
		FROM `tabUser` u
		WHERE u.enabled = 1
		  AND u.name NOT IN ('Guest', 'Administrator')
		  AND (
			u.name LIKE %(txt)s
			OR IFNULL(u.full_name, '') LIKE %(txt)s
		  )
		ORDER BY IFNULL(u.full_name, u.name)
		LIMIT %(start)s, %(page_len)s
		""",
		{"txt": txt, "start": start, "page_len": page_len},
	)


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
		b = _normalize_board_slug(row.board)
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


# Arrangement / color-sequence storage keys — not Workstation names; skip unit ACL.
_ARRANGEMENT_STORAGE_UNITS = frozenset(
	{
		"wcutdcut",
		"boxbag",
		"default",
		"__all__",
		"allunits",
	}
)


def _unit_requires_access_check(unit) -> bool:
	if unit in (None, ""):
		return False
	normalized = str(unit).strip()
	if not normalized:
		return False
	if normalized in ("All Units", "__all__"):
		return False
	key = normalized.lower().replace(" ", "").replace("_", "").replace("-", "")
	if key in _ARRANGEMENT_STORAGE_UNITS:
		return False
	return True


def assert_board_allowed(board_slug: str, user: str | None = None) -> None:
	scope = get_user_board_scope(user)
	if scope.get("unlimited"):
		return
	requested = _equivalent_board_slugs(board_slug)
	if not requested:
		return
	allowed = set(_normalize_board_slug(s) for s in (scope.get("allowed_boards") or []) if s)
	if not (requested & allowed):
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
		if _unit_requires_access_check(unit):
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
	if _unit_requires_access_check(unit):
		assert_unit_allowed(unit, user=user, scope=scope)
	if date not in (None, ""):
		clamp_date(date, user=user, scope=scope)
	return scope


def request_board_slug(default: str | None = None) -> str:
	raw = (
		frappe.form_dict.get("board_slug")
		or frappe.form_dict.get("board")
		or default
		or ""
	)
	return _normalize_board_slug(raw)


def board_slug_for_api(api_name: str) -> str:
	return API_BOARD_MAP.get(api_name, "production-board")


def board_slug_for_board_kind(board_kind: str | None) -> str:
	kind = (board_kind or "").strip().lower()
	return BOARD_KIND_TO_SLUG.get(kind) or "production-board"


def resolve_board_slug(explicit: str | None = None, api_name: str | None = None) -> str:
	"""Prefer explicit slug (API arg / internal kwarg), then form_dict, then API default."""
	norm = _normalize_board_slug(explicit)
	if norm:
		return norm
	return request_board_slug(board_slug_for_api(api_name or ""))


@frappe.whitelist()
def get_production_board_page_options():
	"""Return Select options (page_id|Title) for board picker — boards only, not table pages."""
	return build_board_picker_select_options()


def _is_table_page_slug(slug: str) -> bool:
	if slug in _TABLE_PAGE_EXACT:
		return True
	return any(slug.endswith(sfx) for sfx in _TABLE_PAGE_SUFFIXES)


def _is_board_picker_page(name: str) -> bool:
	slug = _normalize_board_slug(name)
	if not slug or _is_table_page_slug(slug):
		return False
	if slug in BOARD_PICKER_SLUGS:
		return True
	if slug.endswith("-board"):
		return True
	if slug in (
		"color-chart",
		"confirm-orders",
		"planning",
		"logistics-kanban",
		"despatch-approval-dashboard",
		"transfer-approval-dashboard",
	):
		return True
	return False


def build_board_picker_select_options() -> str:
	"""Canonical board list + optional extra *-board pages from Page module."""
	seen: set[str] = set()
	lines: list[str] = []

	def _add(slug: str, title: str | None = None) -> None:
		norm = _normalize_board_slug(slug)
		if not norm or norm in seen or _is_table_page_slug(norm):
			return
		seen.add(norm)
		label = (title or BOARD_PICKER_LABELS.get(norm) or norm.replace("-", " ").title()).strip()
		lines.append(f"{norm}|{label}")

	for slug in BOARD_PICKER_SLUGS:
		label = BOARD_PICKER_LABELS.get(slug)
		if frappe.db.exists("Page", slug):
			label = frappe.db.get_value("Page", slug, "title") or label
		_add(slug, label)

	if frappe.db.exists("DocType", "Page"):
		for row in frappe.get_all(
			"Page",
			filters={"module": "Production Planning"},
			fields=["name", "title"],
			order_by="title asc",
		):
			if _is_board_picker_page(row.name):
				_add(row.name, row.title)

	return "\n".join(lines)


def sync_board_access_board_field_options():
	"""Update child-table Select options so savedocs validation matches the form dropdown."""
	options = build_board_picker_select_options()
	if not options:
		return

	child_dt = "Production Board Access Board"
	existing = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": child_dt,
			"field_name": "board",
			"property": "options",
		},
		"name",
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", options, update_modified=False)
	else:
		try:
			frappe.make_property_setter(
				{
					"doctype": child_dt,
					"fieldname": "board",
					"property": "options",
					"value": options,
					"property_type": "Text",
				},
				ignore_validate=True,
				is_system_generated=True,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "sync_board_access_board_field_options")
	frappe.db.commit()
