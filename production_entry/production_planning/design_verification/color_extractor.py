# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
from dataclasses import dataclass, field

from production_entry.production_planning.design_verification.constants import CMYK_RE, PANTONE_RE

CMYK_NAMED_RE = re.compile(
	r"(?P<name>[A-Za-z][A-Za-z ]{2,30}?)\s+(?P<cmyk>C\s*\d+\s+M\s*\d+\s+Y\s*\d+\s+K\s*\d+)",
	re.I,
)
PANTONE_CODE_RE = re.compile(r"PANTONE\s+(\d+\s*[A-Z]?)|PMS\s+(\d+\s*[A-Z]?)", re.I)


@dataclass
class ColorExtraction:
	cmyk_entries: list[dict] = field(default_factory=list)
	pantone_entries: list[str] = field(default_factory=list)
	dominant_hex: list[str] = field(default_factory=list)
	mode_note: str = ""


def extract_colors_from_text(full_text: str) -> ColorExtraction:
	out = ColorExtraction()
	text = full_text or ""

	for match in CMYK_NAMED_RE.finditer(text):
		out.cmyk_entries.append({
			"name": match.group("name").strip(),
			"cmyk": re.sub(r"\s+", " ", match.group("cmyk").strip()),
		})

	for match in CMYK_RE.finditer(text):
		code = match.group(0).strip()
		if not any(e.get("cmyk") == code for e in out.cmyk_entries):
			out.cmyk_entries.append({"name": "", "cmyk": code})

	for match in PANTONE_CODE_RE.finditer(text):
		code = (match.group(1) or match.group(2) or "").strip()
		if code:
			out.pantone_entries.append(f"PANTONE {code}")

	for match in PANTONE_RE.finditer(text):
		if match.group(0) not in out.pantone_entries:
			out.pantone_entries.append(match.group(0))

	return out


def apply_image_fallback(extraction: ColorExtraction, hex_colors: list[str], mode: str = "Hybrid") -> ColorExtraction:
	extraction.dominant_hex = hex_colors or []
	if mode == "Manual":
		return extraction
	if extraction.cmyk_entries or extraction.pantone_entries:
		return extraction
	if mode in ("Hybrid", "Text Only") and hex_colors:
		for hx in hex_colors[:5]:
			extraction.cmyk_entries.append({"name": "Detected color", "cmyk": hx})
		extraction.mode_note = "CMYK/Pantone not in PDF text — dominant colors from image; confirm manually."
	return extraction


def get_cmyk_slot(extraction: ColorExtraction, slot: str) -> tuple[bool, str, str]:
	idx = ord(slot) - ord("a") if slot else 0
	if idx < len(extraction.cmyk_entries):
		entry = extraction.cmyk_entries[idx]
		name = entry.get("name") or "Colour"
		cmyk = entry.get("cmyk") or ""
		measurement = f"{name} / {cmyk}".strip(" /")
		return True, measurement, cmyk
	return False, "", "Not found — enter code manually"


def get_pantone_slot(extraction: ColorExtraction, slot: str) -> tuple[bool, str]:
	idx = ord(slot) - ord("a") if slot else 0
	if idx < len(extraction.pantone_entries):
		return True, extraction.pantone_entries[idx]
	return False, "Not found — enter Pantone manually"
