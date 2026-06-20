# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations


def ocr_text_from_image(image_path: str) -> str:
	try:
		import pytesseract
		from PIL import Image

		return pytesseract.image_to_string(Image.open(image_path)) or ""
	except Exception:
		return ""
