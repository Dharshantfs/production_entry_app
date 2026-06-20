# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field

import frappe


@dataclass
class OCRResult:
	text: str = ""
	method: str = ""
	char_count: int = 0
	text_blocks: list = field(default_factory=list)
	error: str = ""


def _ocr_needed(existing_text: str, min_chars: int = 80) -> bool:
	return len((existing_text or "").strip()) < min_chars


def _preprocess_image(image_path: str) -> str | None:
	"""Enhance layout PDF render for OCR (contrast + optional upscale)."""
	if not image_path or not os.path.isfile(image_path):
		return None
	try:
		import cv2

		img = cv2.imread(image_path)
		if img is None:
			return None
		gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
		h, w = gray.shape[:2]
		if max(h, w) < 2400:
			scale = 2400 / max(h, w)
			gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
		clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
		enhanced = clahe.apply(gray)
		fd, out_path = tempfile.mkstemp(suffix=".png", prefix="dv_ocr_")
		os.close(fd)
		cv2.imwrite(out_path, enhanced)
		return out_path
	except Exception:
		return None


def _blocks_from_rapidocr_lines(lines: list) -> list:
	from production_entry.production_planning.design_verification.pdf_utils import TextBlock

	blocks = []
	for item in lines or []:
		if not item or len(item) < 2:
			continue
		box, text = item[0], (item[1] or "").strip()
		if not text:
			continue
		try:
			xs = [p[0] for p in box]
			ys = [p[1] for p in box]
			blocks.append(TextBlock(text, min(xs), min(ys), max(xs), max(ys), 0))
		except Exception:
			blocks.append(TextBlock(text, 0, 0, 0, 0, 0))
	return blocks


def _ocr_pymupdf_page(page, dpi: int = 300) -> OCRResult:
	try:
		tp = page.get_textpage_ocr(dpi=dpi, full=True, language="eng")
		text = page.get_text("text", textpage=tp) or ""
		if len(text.strip()) < 20:
			return OCRResult()
		return OCRResult(text=text.strip(), method="pymupdf+tesseract", char_count=len(text.strip()))
	except Exception as exc:
		return OCRResult(error=str(exc))


def _ocr_tesseract(image_path: str) -> OCRResult:
	try:
		import pytesseract
		from PIL import Image

		text = pytesseract.image_to_string(Image.open(image_path), config="--psm 6") or ""
		text = text.strip()
		if len(text) < 20:
			return OCRResult()
		return OCRResult(text=text, method="tesseract", char_count=len(text))
	except Exception as exc:
		return OCRResult(error=str(exc))


def _ocr_rapidocr(image_path: str) -> OCRResult:
	try:
		from rapidocr_onnxruntime import RapidOCR

		engine = RapidOCR()
		lines, _ = engine(image_path)
		if not lines:
			return OCRResult()
		parts = []
		for item in lines:
			if len(item) >= 2 and item[1]:
				parts.append(str(item[1]).strip())
		text = "\n".join(p for p in parts if p)
		if len(text) < 15:
			return OCRResult()
		return OCRResult(
			text=text,
			method="rapidocr",
			char_count=len(text),
			text_blocks=_blocks_from_rapidocr_lines(lines),
		)
	except Exception as exc:
		return OCRResult(error=str(exc))


def run_ocr(
	image_path: str,
	fitz_page=None,
	existing_text: str = "",
	dpi: int = 300,
	enabled: bool = True,
) -> OCRResult:
	"""Run OCR when PDF text layer is missing or too short."""
	if not enabled:
		return OCRResult(method="disabled")
	if not _ocr_needed(existing_text):
		return OCRResult(method="skipped", text=existing_text, char_count=len(existing_text))

	if not image_path or not os.path.isfile(image_path):
		return OCRResult(error="No rendered image for OCR")

	enhanced = _preprocess_image(image_path) or image_path
	cleanup = enhanced != image_path

	try:
		# 1) PyMuPDF built-in OCR (needs system Tesseract)
		if fitz_page is not None:
			result = _ocr_pymupdf_page(fitz_page, dpi=dpi)
			if result.char_count >= 20:
				return result

		# 2) Tesseract via pytesseract
		result = _ocr_tesseract(enhanced)
		if result.char_count >= 20:
			return result

		# 3) RapidOCR (pip-only, works on Frappe Cloud)
		result = _ocr_rapidocr(enhanced)
		if result.char_count >= 15:
			return result

		return OCRResult(
			error=result.error or "OCR returned insufficient text",
			method=result.method or "none",
		)
	finally:
		if cleanup and os.path.isfile(enhanced):
			try:
				os.remove(enhanced)
			except OSError:
				pass


def merge_ocr_into_analysis(analysis, ocr: OCRResult) -> None:
	if not ocr or not ocr.text:
		return
	from production_entry.production_planning.design_verification.pdf_utils import TextBlock

	analysis.ocr_text = ocr.text
	analysis.ocr_method = ocr.method
	analysis.full_text = ((analysis.full_text or "").strip() + "\n" + ocr.text).strip()
	for block in ocr.text_blocks or []:
		analysis.text_blocks.append(block)
	# Split OCR plain text into pseudo-blocks for phrase matching
	for line in re.split(r"[\r\n]+", ocr.text):
		line = line.strip()
		if line and len(line) >= 2:
			analysis.text_blocks.append(TextBlock(line, 0, 0, 0, 0, 0))
