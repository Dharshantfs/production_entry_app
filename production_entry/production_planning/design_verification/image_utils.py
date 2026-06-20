# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import os


def detect_qr(image_path: str) -> tuple[bool, str]:
	if not image_path or not os.path.isfile(image_path):
		return False, "No rendered image"
	try:
		import cv2

		img = cv2.imread(image_path)
		if img is None:
			return False, "Could not read image"
		detector = cv2.QRCodeDetector()
		data, points, _ = detector.detectAndDecode(img)
		if data:
			return True, data
		retval, decoded, _, _ = detector.detectAndDecodeMulti(img)
		if retval and decoded:
			for item in decoded:
				if item:
					return True, item
		return False, "No QR code detected"
	except Exception as exc:
		return False, str(exc)


def detect_dominant_colors(image_path: str, count: int = 5) -> list[str]:
	if not image_path or not os.path.isfile(image_path):
		return []
	try:
		from collections import Counter

		from PIL import Image

		img = Image.open(image_path).convert("RGB")
		img = img.resize((200, 200))
		pixels = list(img.getdata())
		quantized = []
		for r, g, b in pixels:
			# Skip near-white background / paper
			if r > 240 and g > 240 and b > 240:
				continue
			quantized.append((r // 16 * 16, g // 16 * 16, b // 16 * 16))
		common = Counter(quantized).most_common(count * 3)
		out = []
		for rgb, _ in common:
			hx = "#%02x%02x%02x" % rgb
			if hx not in out:
				out.append(hx)
			if len(out) >= count:
				break
		return out
	except Exception:
		return []


def detect_shapes(image_path: str, shape_key: str, page_width_mm: float, page_height_mm: float) -> tuple[bool, str]:
	if not image_path or not os.path.isfile(image_path):
		return False, "No rendered image"
	try:
		import cv2
		import numpy as np

		img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
		if img is None:
			return False, "Could not read image"
		_, thresh = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY_INV)
		contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
		h_px, w_px = img.shape[:2]
		mm_per_px_x = page_width_mm / max(w_px, 1)
		mm_per_px_y = page_height_mm / max(h_px, 1)

		targets = {
			"28x4": (28, 4),
			"22x4": (22, 4),
			"28x2.5": (28, 2.5),
			"23x2.5": (23, 2.5),
			"20x2.5": (20, 2.5),
			"registration": (6, 6),
		}
		tw, th = targets.get(shape_key, (0, 0))
		if not tw:
			return False, f"Unknown shape {shape_key}"

		tol = 0.45
		for cnt in contours:
			x, y, cw, ch = cv2.boundingRect(cnt)
			w_mm = cw * mm_per_px_x
			h_mm = ch * mm_per_px_y
			if abs(w_mm - tw) <= tw * tol and abs(h_mm - th) <= th * tol:
				return True, f"Found ~{w_mm:.1f}x{h_mm:.1f} mm"
			if abs(w_mm - th) <= th * tol and abs(h_mm - tw) <= tw * tol:
				return True, f"Found rotated ~{w_mm:.1f}x{h_mm:.1f} mm"
		if shape_key == "registration":
			# fallback: dark square blobs
			for cnt in contours:
				x, y, cw, ch = cv2.boundingRect(cnt)
				if 3 <= cw * mm_per_px_x <= 10 and 3 <= ch * mm_per_px_y <= 10:
					ratio = cw / max(ch, 1)
					if 0.7 <= ratio <= 1.3:
						return True, "Registration-like mark found"
		return False, f"Shape {shape_key} not detected"
	except Exception as exc:
		return False, str(exc)
