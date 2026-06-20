# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

from production_entry.production_planning.design_verification.ocr_engine import run_ocr


def ocr_text_from_image(image_path: str, dpi: int = 300) -> str:
	result = run_ocr(image_path, dpi=dpi, enabled=True)
	return result.text or ""
