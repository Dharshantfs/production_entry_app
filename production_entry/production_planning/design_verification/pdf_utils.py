# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import frappe

from production_entry.production_planning.design_verification.constants import (
	DIM_INCH_2_RE,
	DIM_INCH_3_RE,
	DIM_MM_RE,
	INCH_TO_MM,
)


@dataclass
class TextBlock:
	text: str
	x0: float
	y0: float
	x1: float
	y1: float
	page: int = 0


@dataclass
class PDFAnalysis:
	file_path: str = ""
	full_text: str = ""
	text_blocks: list[TextBlock] = field(default_factory=list)
	width: float | None = None
	height: float | None = None
	gusset: float | None = None
	top_folding: float | None = None
	page_width_mm: float = 0.0
	page_height_mm: float = 0.0
	page_count: int = 0
	rendered_image_path: str | None = None
	cmyk_codes: list[str] = field(default_factory=list)
	pantone_hits: list[str] = field(default_factory=list)


def resolve_pdf_path(file_url: str) -> str | None:
	if not file_url:
		return None
	try:
		file_doc = frappe.get_doc("File", {"file_url": file_url})
		return file_doc.get_full_path()
	except Exception:
		path = frappe.get_site_path("public", file_url.lstrip("/"))
		return path if os.path.isfile(path) else None


def _points_to_mm(points: float) -> float:
	return points * 25.4 / 72.0


def _parse_label_dimensions(text: str, analysis: PDFAnalysis) -> None:
	label_map = {
		"face width": "width",
		"face height": "height",
		"gusset": "gusset",
		"gazette": "gusset",
		"top folding": "top_folding",
	}
	for block in analysis.text_blocks:
		low = block.text.lower().strip()
		for label, attr in label_map.items():
			if label in low:
				nums = re.findall(r"(\d+(?:\.\d+)?)", block.text)
				if nums and getattr(analysis, attr) is None:
					setattr(analysis, attr, float(nums[-1]))


def _parse_regex_dimensions(text: str, analysis: PDFAnalysis) -> None:
	for match in DIM_MM_RE.finditer(text):
		w, h, g = (float(x) for x in match.groups())
		analysis.width = analysis.width or w
		analysis.height = analysis.height or h
		analysis.gusset = analysis.gusset or g
		break

	if analysis.width is None:
		for match in DIM_INCH_3_RE.finditer(text):
			w, h, g = (float(x) * INCH_TO_MM for x in match.groups())
			analysis.width = analysis.width or w
			analysis.height = analysis.height or h
			analysis.gusset = analysis.gusset or g
			break

	if analysis.width is None:
		for match in DIM_INCH_2_RE.finditer(text):
			w, h = (float(x) * INCH_TO_MM for x in match.groups())
			analysis.width = analysis.width or w
			analysis.height = analysis.height or h
			break


def analyze_pdf(file_url: str, render_dpi: int = 150) -> PDFAnalysis:
	analysis = PDFAnalysis()
	path = resolve_pdf_path(file_url)
	if not path or not os.path.isfile(path):
		return analysis

	analysis.file_path = path
	try:
		import fitz
	except ImportError:
		frappe.log_error("PyMuPDF (pymupdf) is not installed", "Design Verification PDF")
		return analysis

	doc = fitz.open(path)
	analysis.page_count = len(doc)
	parts = []

	for page_index, page in enumerate(doc):
		parts.append(page.get_text("text") or "")
		analysis.page_width_mm = _points_to_mm(page.rect.width)
		analysis.page_height_mm = _points_to_mm(page.rect.height)
		block_dict = page.get_text("dict") or {}
		for block in block_dict.get("blocks") or []:
			if block.get("type") != 0:
				continue
			for line in block.get("lines") or []:
				spans = line.get("spans") or []
				if not spans:
					continue
				text = "".join(s.get("text", "") for s in spans).strip()
				if not text:
					continue
				x0 = min(s["bbox"][0] for s in spans)
				y0 = min(s["bbox"][1] for s in spans)
				x1 = max(s["bbox"][2] for s in spans)
				y1 = max(s["bbox"][3] for s in spans)
				analysis.text_blocks.append(TextBlock(text, x0, y0, x1, y1, page_index))

	analysis.full_text = "\n".join(parts)
	_parse_regex_dimensions(analysis.full_text, analysis)
	_parse_label_dimensions(analysis.full_text, analysis)

	from production_entry.production_planning.design_verification.constants import CMYK_RE, PANTONE_RE

	for match in CMYK_RE.finditer(analysis.full_text):
		analysis.cmyk_codes.append(match.group(0))
	for match in PANTONE_RE.finditer(analysis.full_text):
		analysis.pantone_hits.append(match.group(0))

	if doc.page_count:
		page = doc[0]
		pix = page.get_pixmap(dpi=render_dpi, alpha=False)
		analysis.rendered_image_path = path + ".preview.png"
		pix.save(analysis.rendered_image_path)

	doc.close()
	return analysis


def save_preview_to_design(doc, local_png_path: str, design_name: str) -> str | None:
	if not local_png_path or not os.path.isfile(local_png_path):
		return None
	try:
		with open(local_png_path, "rb") as f:
			content = f.read()
		from frappe.utils.file_manager import save_file

		ret = save_file(
			f"{frappe.scrub(design_name or 'design')}_preview.png",
			content,
			"Design Master",
			doc.name or "New Design Master",
			is_private=0,
		)
		return ret.file_url if ret else None
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Design Verification Preview Save")
		return None
