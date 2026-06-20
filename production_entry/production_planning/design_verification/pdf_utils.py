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
	found_mm_values: set[float] = field(default_factory=set)
	dimension_context: object | None = None
	bag_size_inches_str: str = ""
	text_layer_missing: bool = False
	ocr_text: str = ""
	ocr_method: str = ""


def resolve_original_filename(file_url: str) -> str:
	"""Original upload name from File doctype (may differ from file_url basename)."""
	file_url = (file_url or "").strip()
	if not file_url:
		return ""
	clean = file_url.split("?")[0]
	try:
		for url in (file_url, clean):
			name = frappe.db.get_value("File", {"file_url": url}, "file_name")
			if name:
				return name
	except Exception:
		pass
	return os.path.basename(clean)


def _preview_image_path(pdf_path: str) -> str:
	"""Write preview PNG to a writable temp path (Frappe Cloud private files may be read-only)."""
	import tempfile

	base = os.path.basename(pdf_path or "design")
	safe = re.sub(r"[^\w.-]+", "_", base)[:80]
	try:
		site_tmp = frappe.get_site_path("private", "files")
		os.makedirs(site_tmp, exist_ok=True)
		fd, path = tempfile.mkstemp(suffix=".png", prefix=f"dv_{safe}_", dir=site_tmp)
		os.close(fd)
		return path
	except Exception:
		fd, path = tempfile.mkstemp(suffix=".png", prefix="dv_")
		os.close(fd)
		return path


def resolve_pdf_path(file_url: str) -> str | None:
	file_url = (file_url or "").strip()
	if not file_url:
		return None

	# 1) File doctype by exact URL
	try:
		file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
		if file_name:
			return frappe.get_doc("File", file_name).get_full_path()
	except Exception:
		pass

	# 2) Strip query string and retry
	clean = file_url.split("?")[0]
	if clean != file_url:
		try:
			file_name = frappe.db.get_value("File", {"file_url": clean}, "name")
			if file_name:
				return frappe.get_doc("File", file_name).get_full_path()
		except Exception:
			pass

	# 3) Site path public/private
	rel = clean.lstrip("/")
	site_path = frappe.get_site_path()
	candidate = os.path.normpath(os.path.join(site_path, rel.replace("/", os.sep)))
	if os.path.isfile(candidate):
		return candidate

	for prefix in ("public", "private"):
		if rel.startswith("files/"):
			candidate = frappe.get_site_path(prefix, rel)
			if os.path.isfile(candidate):
				return candidate

	return None


def _parse_filename_dimensions(file_url: str, analysis: PDFAnalysis) -> None:
	name = os.path.basename((file_url or "").split("?")[0])
	_parse_regex_dimensions(name, analysis)


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


def analyze_pdf(
	file_url: str,
	render_dpi: int = 150,
	design_name: str = "",
	filename_hint: str = "",
	mm_tolerance: float = 2.0,
	ocr_enabled: bool = True,
	ocr_dpi: int = 300,
) -> PDFAnalysis:
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

		for word in page.get_text("words") or []:
			if len(word) < 5:
				continue
			text = (word[4] or "").strip()
			if not text:
				continue
			x0, y0, x1, y1 = word[0], word[1], word[2], word[3]
			analysis.text_blocks.append(TextBlock(text, x0, y0, x1, y1, page_index))

	analysis.full_text = "\n".join(parts)
	_parse_regex_dimensions(analysis.full_text, analysis)
	_parse_label_dimensions(analysis.full_text, analysis)
	_parse_filename_dimensions(filename_hint or file_url, analysis)

	from production_entry.production_planning.design_verification.constants import CMYK_RE, PANTONE_RE

	for match in CMYK_RE.finditer(analysis.full_text):
		analysis.cmyk_codes.append(match.group(0))
	for match in PANTONE_RE.finditer(analysis.full_text):
		analysis.pantone_hits.append(match.group(0))

	from production_entry.production_planning.design_verification.dimension_extractor import (
		build_dimension_context,
	)

	name_sources = [filename_hint, resolve_original_filename(file_url), file_url, design_name]
	ctx = build_dimension_context(analysis, *name_sources, tolerance=mm_tolerance)
	analysis.found_mm_values = ctx.found_mm_values
	analysis.dimension_context = ctx
	analysis.bag_size_inches_str = ctx.bag_size_inches_str
	analysis.text_layer_missing = not (analysis.full_text or "").strip()

	ocr_page = doc[0] if doc.page_count else None
	ocr_dpi_use = int(ocr_dpi or 300)
	preview_dpi = max(int(render_dpi or 150), ocr_dpi_use if ocr_enabled else 0)

	if ocr_page is not None:
		pix = ocr_page.get_pixmap(dpi=preview_dpi, alpha=False)
		analysis.rendered_image_path = _preview_image_path(path)
		pix.save(analysis.rendered_image_path)

	needs_ocr = ocr_enabled and (
		analysis.text_layer_missing or len(analysis.found_mm_values or []) < 8
	)
	if needs_ocr and analysis.rendered_image_path:
		from production_entry.production_planning.design_verification.ocr_engine import (
			merge_ocr_into_analysis,
			run_ocr,
		)

		ocr_result = run_ocr(
			analysis.rendered_image_path,
			fitz_page=ocr_page,
			existing_text=analysis.full_text or "",
			dpi=ocr_dpi_use,
			enabled=ocr_enabled,
		)
		if ocr_result.text:
			merge_ocr_into_analysis(analysis, ocr_result)
			analysis.text_layer_missing = False
			ctx = build_dimension_context(analysis, *name_sources, tolerance=mm_tolerance)
			analysis.found_mm_values = ctx.found_mm_values
			analysis.dimension_context = ctx
			analysis.bag_size_inches_str = ctx.bag_size_inches_str
			analysis.cmyk_codes = []
			analysis.pantone_hits = []
			for match in CMYK_RE.finditer(analysis.full_text or ""):
				analysis.cmyk_codes.append(match.group(0))
			for match in PANTONE_RE.finditer(analysis.full_text or ""):
				analysis.pantone_hits.append(match.group(0))
		elif ocr_result.error and ocr_enabled:
			frappe.log_error(
				f"Design Verification OCR: {ocr_result.error}",
				"Design Verification OCR",
			)

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
			doc.doctype,
			doc.name or f"New {doc.doctype}",
			is_private=0,
		)
		return ret.file_url if ret else None
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Design Verification Preview Save")
		return None
