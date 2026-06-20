# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

from production_entry.production_planning.design_verification import image_utils, text_utils
from production_entry.production_planning.design_verification.constants import CMYK_RE, PANTONE_RE
from production_entry.production_planning.design_verification.pdf_utils import PDFAnalysis
from production_entry.production_planning.design_verification.spatial_engine import (
	SpatialContext,
	build_spatial_context,
	check_equal_spacing,
	check_safe_zone,
	check_spatial_gap,
	check_zone_empty,
	check_zone_present,
)


def _result_to_checklist(passed: bool, manual: bool = False) -> tuple[str, str]:
	if manual:
		return "Manual Review", "0"
	return ("Pass", "1") if passed else ("Fail", "0")


def run_rule(rule, doc, settings, analysis: PDFAnalysis, spatial: SpatialContext, qr_ok: bool, qr_msg: str, colors: list[str]):
	method = rule.check_method or "TextMatch"
	config = rule.rule_config
	if isinstance(config, str):
		try:
			config = json.loads(config) if config else {}
		except Exception:
			config = {}

	passed = False
	manual = False
	remarks = ""
	measurement = rule.expected_measurement or ""

	if method == "DimensionRegex":
		field = (config or {}).get("field")
		val = getattr(analysis, field, None) if field else None
		if val is not None:
			passed = True
			measurement = str(int(val) if float(val).is_integer() else val)
			remarks = f"Detected {field}: {measurement} mm"
		else:
			remarks = f"{field or 'dimension'} not detected"

	elif method == "QRDetect":
		passed = qr_ok
		remarks = qr_msg

	elif method == "TextMatch":
		phrases = (config or {}).get("phrases") or []
		if phrases:
			hit = text_utils.match_any_phrase(phrases, analysis.full_text)
			passed = bool(hit)
			remarks = f"Matched: {hit}" if hit else f"Missing phrases: {', '.join(phrases)}"
		else:
			passed, remarks = text_utils.match_logo_phrases(settings, analysis.full_text)

	elif method == "SpatialGap":
		passed, remarks = check_spatial_gap(spatial, config or {})

	elif method == "ZoneEmpty":
		passed, remarks = check_zone_empty(spatial, config or {})

	elif method == "ZonePresent":
		passed, remarks = check_zone_present(spatial, config or {})

	elif method == "SafeZone":
		passed, remarks = check_safe_zone(spatial, config or {})

	elif method == "EqualSpacing":
		passed, remarks = check_equal_spacing(spatial, config or {})

	elif method == "ShapeDetect":
		shape = (config or {}).get("shape") or rule.expected_measurement or ""
		passed, remarks = image_utils.detect_shapes(
			analysis.rendered_image_path,
			shape,
			analysis.page_width_mm,
			analysis.page_height_mm,
		)

	elif method == "CMYKPattern":
		codes = [m.group(0) for m in CMYK_RE.finditer(analysis.full_text or "")]
		slot = (config or {}).get("slot")
		if codes:
			idx = ord(slot) - ord("a") if slot else 0
			if idx < len(codes):
				passed = True
				measurement = codes[idx]
				remarks = measurement
			else:
				remarks = "CMYK slot empty"
		else:
			remarks = "No CMYK codes in PDF"

	elif method == "PantonePattern":
		hits = PANTONE_RE.findall(analysis.full_text or "")
		passed = bool(hits)
		remarks = f"Found Pantone refs: {len(hits)}" if hits else "No Pantone reference"

	elif method == "ColorDetect":
		passed = len(colors) >= int((config or {}).get("min") or 1)
		remarks = ", ".join(colors[:5])

	elif method == "ProductCode":
		passed, remarks = text_utils.product_code_in_text(doc, analysis.full_text)

	else:
		manual = True
		remarks = f"Unknown method {method}"

	result, checklist = _result_to_checklist(passed, manual)
	return {
		"result": result,
		"checklist": checklist,
		"remarks": remarks,
		"measurement": measurement,
		"check_method": method,
	}
