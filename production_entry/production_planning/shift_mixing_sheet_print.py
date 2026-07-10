# -*- coding: utf-8 -*-
"""Build Excel-style print context from Shift Mixing Sheet JSON."""

from __future__ import annotations

import json
import re

from frappe.utils import cint, flt


PRINTING_UNITS = {
	"VR - 1200MM BOPP PRINTING MACHINE",
	"JVE - PRINTING MACHINE 2 COLOUR 1600MM",
	"JVE - PRINTING MACHINE 4 COLOUR 1600MM",
	"TT - PRINTING MACHINE 4 COLOUR 1200MM",
}

PP_COLUMNS = [
	("advanced", "ADVANCED"),
	("basell", "BASELL"),
	("china", "CHINA"),
	("exxon", "EXXON"),
	("poly_maxx", "POLY MAXX"),
	("reliance", "RELIANCE"),
]

FILLER_COLUMNS = [
	("bajaj_440", "BAJAJ 440"),
	("bajaj_700", "BAJAJ 700"),
	("capital", "CAPITAL"),
	("f560", "560"),
	("f700", "700"),
]

COLOUR_COLUMNS = [
	("ar_white", "AR WHITE 1071"),
	("clr2", "CLR 2"),
	("clr3", "CLR 3"),
	("antistatic", "ANTISTATIC"),
]

MIN_EXCEL_ROWS = 20


def _norm_text(*parts) -> str:
	return re.sub(r"\s+", " ", " ".join((p or "") for p in parts)).strip().upper()


def _parse_state(raw) -> dict:
	if not raw:
		return {"mixing_type": "", "sets": [], "completed": False}
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
	except Exception:
		return {"mixing_type": "", "sets": [], "completed": False}
	if not isinstance(data, dict):
		return {"mixing_type": "", "sets": [], "completed": False}
	return data


def _item_label(item_code: str, item_names: dict, key: str) -> str:
	name = (item_names or {}).get(key) or ""
	return _norm_text(name, item_code)


def _match_pp_column(text: str) -> str | None:
	if "ADVANCED" in text:
		return "advanced"
	if "BASELL" in text:
		return "basell"
	if "CHINA" in text:
		return "china"
	if "EXXON" in text:
		return "exxon"
	if "POLY MAXX" in text or "POLYMAXX" in text:
		return "poly_maxx"
	if "RELIANCE" in text:
		return "reliance"
	return None


def _match_filler_column(text: str) -> str | None:
	if "BAJAJ" in text and "440" in text:
		return "bajaj_440"
	if "BAJAJ" in text and "700" in text:
		return "bajaj_700"
	if "CAPITAL" in text:
		return "capital"
	# Standalone 560 / 700 filler codes
	if re.search(r"(?:^|\s|FL\s*-?\s*)560(?:\s|$)", text) or text.endswith(" 560") or text == "560":
		return "f560"
	if re.search(r"(?:^|\s|FL\s*-?\s*)700(?:\s|$)", text) or (text.endswith(" 700") and "BAJAJ" not in text):
		return "f700"
	return None


def _match_colour_column(text: str, role: str) -> str | None:
	if role == "antistatic" or "ANTISTATIC" in text:
		return "antistatic"
	if "1071" in text or "AR WHITE" in text:
		return "ar_white"
	if "CLR 2" in text or "CLR2" in text or "COLOUR 2" in text:
		return "clr2"
	if "CLR 3" in text or "CLR3" in text or "COLOUR 3" in text:
		return "clr3"
	if role == "masterbatch":
		if "CLR 2" in text:
			return "clr2"
		if "CLR 3" in text:
			return "clr3"
		return "ar_white"
	return None


def _blank_qty_row(keys: list[str]) -> dict:
	return {k: "" for k in keys}


def _fmt_qty(val) -> str:
	q = flt(val)
	if not q:
		return ""
	if q == int(q):
		return str(int(q))
	return f"{q:g}"


def _row_time(row: dict) -> str:
	at = (row.get("consumed_at") or "").strip()
	if len(at) >= 16:
		return at[11:16]
	return ""


def _build_extrusion_set_rows(set_obj: dict) -> list[dict]:
	materials = set_obj.get("materials") or {}
	item_names = set_obj.get("item_names") or {}
	rows_in = set_obj.get("rows") or []

	pp_key = _match_pp_column(_item_label(materials.get("PP"), item_names, "PP"))
	filler_key = _match_filler_column(_item_label(materials.get("Filler"), item_names, "Filler"))
	mb_key = _match_colour_column(_item_label(materials.get("Masterbatch"), item_names, "Masterbatch"), "masterbatch")
	anti_key = _match_colour_column(_item_label(materials.get("Antistatic"), item_names, "Antistatic"), "antistatic")
	modifier_key = "modifier"

	pp_keys = [k for k, _ in PP_COLUMNS]
	filler_keys = [k for k, _ in FILLER_COLUMNS]
	colour_keys = [k for k, _ in COLOUR_COLUMNS]

	out = []
	for row in rows_in:
		pp_vals = _blank_qty_row(pp_keys)
		filler_vals = _blank_qty_row(filler_keys)
		colour_vals = _blank_qty_row(colour_keys)

		if pp_key:
			pp_vals[pp_key] = _fmt_qty(row.get("pp_qty"))
		if filler_key:
			filler_vals[filler_key] = _fmt_qty(row.get("filler_qty"))
		if mb_key:
			colour_vals[mb_key] = _fmt_qty(row.get("mb_qty"))
		if anti_key:
			colour_vals[anti_key] = _fmt_qty(row.get("anti_qty"))

		extras = row.get("extras") or {}
		for ex in set_obj.get("extras") or []:
			code = ex.get("item_code")
			if not code:
				continue
			ex_text = _norm_text(ex.get("item_name"), code)
			ex_key = _match_colour_column(ex_text, "masterbatch") or _match_filler_column(ex_text)
			val = _fmt_qty(extras.get(code))
			if ex_key in colour_vals:
				colour_vals[ex_key] = val
			elif ex_key in filler_vals:
				filler_vals[ex_key] = val

		out.append(
			{
				"pp": pp_vals,
				"filler": filler_vals,
				"colours": colour_vals,
				"modifier": _fmt_qty(row.get("ppa_qty")),
				"time": _row_time(row),
				"consumed": cint(row.get("consumed")),
			}
		)

	# Pad to minimum rows like Excel template
	while len(out) < MIN_EXCEL_ROWS:
		out.append(
			{
				"pp": _blank_qty_row(pp_keys),
				"filler": _blank_qty_row(filler_keys),
				"colours": _blank_qty_row(colour_keys),
				"modifier": "",
				"time": "",
				"consumed": 0,
			}
		)
	return out


def _build_printing_set_rows(set_obj: dict) -> list[dict]:
	materials = set_obj.get("materials") or {}
	item_names = set_obj.get("item_names") or {}
	rows_in = set_obj.get("rows") or []
	ink_label = item_names.get("Ink") or materials.get("Ink") or "BOPP Ink"

	out = []
	for row in rows_in:
		out.append(
			{
				"ink": _fmt_qty(row.get("ink_qty")),
				"ethyl_acetate": _fmt_qty(row.get("ea_qty")),
				"toluene": _fmt_qty(row.get("tol_qty")),
				"iso_butanol": _fmt_qty(row.get("iso_qty")),
				"extras": {ex.get("item_code"): _fmt_qty((row.get("extras") or {}).get(ex.get("item_code"))) for ex in set_obj.get("extras") or []},
				"time": _row_time(row),
				"consumed": cint(row.get("consumed")),
			}
		)
	while len(out) < MIN_EXCEL_ROWS:
		out.append(
			{
				"ink": "",
				"ethyl_acetate": "",
				"toluene": "",
				"iso_butanol": "",
				"extras": {},
				"time": "",
				"consumed": 0,
			}
		)

	return {"rows": out, "ink_label": ink_label, "materials": materials}


def build_shift_mixing_print_context(doc) -> dict:
	state = _parse_state(doc.get("mixing_sheet_data"))
	unit = (doc.get("custom_unit") or "").strip()
	is_printing = unit in PRINTING_UNITS

	sets_out = []
	for idx, set_obj in enumerate(state.get("sets") or []):
		if not set_obj.get("materials"):
			continue
		if is_printing:
			sets_out.append({"index": idx + 1, "printing": _build_printing_set_rows(set_obj)})
		else:
			sets_out.append({"index": idx + 1, "rows": _build_extrusion_set_rows(set_obj)})

	return {
		"is_printing": is_printing,
		"mixing_type": state.get("mixing_type") or doc.get("mixing_type") or "",
		"pp_columns": PP_COLUMNS,
		"filler_columns": FILLER_COLUMNS,
		"colour_columns": COLOUR_COLUMNS,
		"sets": sets_out,
		"completed": cint(state.get("completed")),
	}
