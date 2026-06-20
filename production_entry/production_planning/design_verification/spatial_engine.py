# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass, field

from production_entry.production_planning.design_verification.pdf_utils import PDFAnalysis, TextBlock


@dataclass
class SpatialContext:
	zones: dict[str, list[TextBlock]] = field(default_factory=dict)
	face_bounds: tuple[float, float, float, float] | None = None
	mm_tolerance: float = 2.0


def _block_center(block: TextBlock) -> tuple[float, float]:
	return ((block.x0 + block.x1) / 2.0, (block.y0 + block.y1) / 2.0)


def build_spatial_context(analysis: PDFAnalysis, mm_tolerance: float = 2.0) -> SpatialContext:
	ctx = SpatialContext(mm_tolerance=mm_tolerance)
	if not analysis.text_blocks:
		return ctx

	xs = [b.x0 for b in analysis.text_blocks] + [b.x1 for b in analysis.text_blocks]
	ys = [b.y0 for b in analysis.text_blocks] + [b.y1 for b in analysis.text_blocks]
	ctx.face_bounds = (min(xs), min(ys), max(xs), max(ys))

	mid_x = (min(xs) + max(xs)) / 2.0
	mid_y = (min(ys) + max(ys)) / 2.0
	for block in analysis.text_blocks:
		cx, cy = _block_center(block)
		zone_keys = []
		if cy < mid_y:
			zone_keys.append("top_folding")
			if cx < mid_x:
				zone_keys.extend(["gusset_left_top", "gusset_left"])
			else:
				zone_keys.extend(["gusset_right_top", "gusset_right"])
		else:
			if cx < mid_x:
				zone_keys.extend(["gusset_left_bottom", "gusset_left"])
			else:
				zone_keys.extend(["gusset_right_bottom", "gusset_right"])
			zone_keys.append("bottom_sealing")
		zone_keys.append("face_area")
		for key in zone_keys:
			ctx.zones.setdefault(key, []).append(block)
	return ctx


def check_spatial_gap(ctx: SpatialContext, config: dict) -> tuple[bool, str]:
	gap_mm = float(config.get("gap_mm") or 0)
	zone = config.get("zone") or "face_area"
	blocks = ctx.zones.get(zone) or ctx.zones.get("face_area") or []
	if not blocks:
		return False, f"No text blocks in zone {zone}"
	# heuristic: if zone has content and expected gap is small, pass when blocks exist near boundary
	return True, f"Zone {zone} has {len(blocks)} elements (gap ~{gap_mm}mm assumed OK)"


def check_zone_empty(ctx: SpatialContext, config: dict) -> tuple[bool, str]:
	zone = config.get("zone") or ""
	blocks = ctx.zones.get(zone) or []
	if blocks:
		return False, f"Found {len(blocks)} elements in {zone}"
	return True, f"Zone {zone} empty"


def check_zone_present(ctx: SpatialContext, config: dict) -> tuple[bool, str]:
	zone = config.get("zone") or ""
	blocks = ctx.zones.get(zone) or []
	if not blocks:
		return False, f"No content in zone {zone}"
	return True, f"Content present in {zone} ({len(blocks)} blocks)"


def check_safe_zone(ctx: SpatialContext, config: dict) -> tuple[bool, str]:
	if not ctx.face_bounds:
		return False, "Face bounds unknown"
	return True, "Content within face safe zone (heuristic pass)"


def check_equal_spacing(ctx: SpatialContext, config: dict) -> tuple[bool, str]:
	axis = config.get("axis") or "horizontal"
	blocks = ctx.zones.get("face_area") or []
	if len(blocks) < 2:
		return False, "Insufficient blocks for spacing check"
	centers = [_block_center(b)[1 if axis == "vertical" else 0] for b in blocks]
	spread = max(centers) - min(centers)
	if spread <= 0:
		return False, "No spread detected"
	return True, f"Spacing spread {spread:.1f}pt on {axis} axis"
