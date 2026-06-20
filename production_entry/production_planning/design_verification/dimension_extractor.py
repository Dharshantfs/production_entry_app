# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
from dataclasses import dataclass, field

from production_entry.production_planning.design_verification.constants import (
	DIM_INCH_2_RE,
	DIM_INCH_3_RE,
	INCH_TO_MM,
)

MM_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.I)
INCH_BAG_RE = re.compile(
	r"(\d+(?:\.\d+)?)\s*[\"']?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[\"']?\s*[xX×]\s*(\d+(?:\.\d+)?)",
	re.I,
)

# Primary dimension targets for layout marking PDFs
FACE_WIDTH_CANDIDATES = (305, 300, 304.8)
FACE_HEIGHT_CANDIDATES = (380, 381, 381.0)
GUSSET_CANDIDATES = (110, 108, 107.95)
TOP_FOLDING_CANDIDATES = (40, 80)


@dataclass
class DimensionContext:
	found_mm_values: set[float] = field(default_factory=set)
	mm_annotations: list[dict] = field(default_factory=list)
	bag_size_inches: tuple[float, float, float] | None = None
	bag_size_inches_str: str = ""
	expected_mm: dict = field(default_factory=dict)


def _near(value: float, target: float, tolerance: float) -> bool:
	return abs(value - target) <= tolerance


def _find_nearest_in_set(found: set[float], candidates: tuple, tolerance: float) -> float | None:
	for cand in candidates:
		for val in found:
			if _near(val, cand, tolerance):
				return val
	return None


def _collect_mm_from_text(text: str, found: set[float], annotations: list, block=None):
	for match in MM_TOKEN_RE.finditer(text or ""):
		val = float(match.group(1))
		found.add(val)
		annotations.append({
			"value": val,
			"text": match.group(0),
			"x": block.x0 if block else 0,
			"y": block.y0 if block else 0,
		})


def parse_inch_bag_size(*sources: str) -> tuple[float, float, float] | None:
	for src in sources:
		if not src:
			continue
		for match in INCH_BAG_RE.finditer(src):
			w, h, g = (float(x) for x in match.groups())
			if w < 50 and h < 50:
				return (w, h, g)
		for match in DIM_INCH_3_RE.finditer(src):
			w, h, g = (float(x) for x in match.groups())
			if w < 50 and h < 50:
				return (w, h, g)
	return None


def build_dimension_context(analysis, file_url: str = "", design_name: str = "", tolerance: float = 2.0) -> DimensionContext:
	ctx = DimensionContext()
	found: set[float] = set()
	annotations: list[dict] = []

	for block in analysis.text_blocks or []:
		_collect_mm_from_text(block.text, found, annotations, block)

	_collect_mm_from_text(analysis.full_text or "", found, annotations)

	# Plain numbers in dimension range from blocks (layout PDFs show "305" without mm suffix)
	for block in analysis.text_blocks or []:
		text = (block.text or "").strip()
		if re.fullmatch(r"\d+(?:\.\d+)?", text):
			val = float(text)
			if 5 <= val <= 2000:
				found.add(val)
				annotations.append({"value": val, "text": text, "x": block.x0, "y": block.y0})

	ctx.found_mm_values = found
	ctx.mm_annotations = annotations

	inches = parse_inch_bag_size(file_url, analysis.full_text or "", design_name or "")
	if inches:
		ctx.bag_size_inches = inches
		ctx.bag_size_inches_str = f'{inches[0]} x {inches[1]} x {inches[2]}'
		ctx.expected_mm = {
			"width": round(inches[0] * INCH_TO_MM, 1),
			"height": round(inches[1] * INCH_TO_MM, 1),
			"gusset": round(inches[2] * INCH_TO_MM, 1),
		}

	# Assign primary dimensions from found mm values
	width = _find_nearest_in_set(found, FACE_WIDTH_CANDIDATES, tolerance)
	if width is None and ctx.expected_mm.get("width"):
		width = _find_nearest_in_set(found, (ctx.expected_mm["width"],), tolerance + 3)
	analysis.width = width or analysis.width

	height = _find_nearest_in_set(found, FACE_HEIGHT_CANDIDATES, tolerance)
	if height is None and ctx.expected_mm.get("height"):
		height = _find_nearest_in_set(found, (ctx.expected_mm["height"],), tolerance + 3)
	analysis.height = height or analysis.height

	gusset = _find_nearest_in_set(found, GUSSET_CANDIDATES, tolerance)
	if gusset is None and ctx.expected_mm.get("gusset"):
		gusset = _find_nearest_in_set(found, (ctx.expected_mm["gusset"],), tolerance + 5)
	analysis.gusset = gusset or analysis.gusset

	top_folding = _find_nearest_in_set(found, TOP_FOLDING_CANDIDATES, tolerance)
	if top_folding is None:
		for block in analysis.text_blocks or []:
			if "top folding" in (block.text or "").lower() or "top fold" in (block.text or "").lower():
				for ann in annotations:
					if ann.get("y") and abs(ann["y"] - block.y0) < 50:
						if ann["value"] in TOP_FOLDING_CANDIDATES:
							top_folding = ann["value"]
							break
	analysis.top_folding = top_folding or analysis.top_folding

	# Fallback from inch conversion
	if not analysis.width and ctx.expected_mm.get("width"):
		analysis.width = ctx.expected_mm["width"]
	if not analysis.height and ctx.expected_mm.get("height"):
		analysis.height = ctx.expected_mm["height"]
	if not analysis.gusset and ctx.expected_mm.get("gusset"):
		analysis.gusset = ctx.expected_mm["gusset"]

	analysis.found_mm_values = found
	analysis.dimension_context = ctx
	return ctx


def mm_value_present(found: set[float], values: list, tolerance: float = 0) -> tuple[bool, float | None]:
	for expected in values or []:
		exp = float(expected)
		for val in found:
			if _near(val, exp, tolerance):
				return True, val
	return False, None


def match_dimension_field(field: str, found: set[float], tolerance: float = 2.0) -> tuple[bool, str]:
	field_map = {
		"width": FACE_WIDTH_CANDIDATES,
		"height": FACE_HEIGHT_CANDIDATES,
		"gusset": GUSSET_CANDIDATES,
		"top_folding": TOP_FOLDING_CANDIDATES,
		"content_box_w": (20,),
		"content_box_h": (40,),
		"content_box_w2": (20,),
		"content_box_h2": (60,),
	}
	candidates = field_map.get(field)
	if not candidates:
		return False, ""
	ok, val = mm_value_present(found, list(candidates), tolerance)
	if ok and val is not None:
		return True, str(int(val) if float(val).is_integer() else val)
	return False, ""


def match_dimension_config(config: dict, found: set[float], tolerance: float = 2.0) -> tuple[bool, str]:
	field = (config or {}).get("field")
	if field == "top_folding":
		ok, val = mm_value_present(found, list(TOP_FOLDING_CANDIDATES), tolerance)
	elif field:
		return match_dimension_field(field, found, tolerance)
	else:
		expected = (config or {}).get("expected_mm")
		if expected is not None:
			ok, val = mm_value_present(found, [expected], tolerance)
		else:
			values = (config or {}).get("values") or []
			ok, val = mm_value_present(found, values, tolerance)
	if ok and val is not None:
		return True, str(int(val) if float(val).is_integer() else val)
	return False, ""
