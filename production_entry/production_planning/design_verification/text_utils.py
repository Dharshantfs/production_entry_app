# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import re

from production_entry.production_planning.design_verification.constants import CMYK_RE


def normalize_text(text: str) -> str:
	text = (text or "").upper()
	text = re.sub(r"\s+", " ", text)
	return text.strip()


def phrase_in_text(phrase: str, haystack: str) -> bool:
	if not phrase:
		return False
	return normalize_text(phrase) in normalize_text(haystack)


def match_any_phrase(phrases: list[str], haystack: str) -> str | None:
	for phrase in phrases or []:
		if phrase_in_text(phrase, haystack):
			return phrase
	return None


def match_customer_name(doc, settings, haystack: str) -> tuple[bool, str]:
	source = getattr(settings, "customer_field_source", None) or "Design Name"
	name = (getattr(doc, "design_name", None) or "").strip()
	if source == "Customer Link" and getattr(doc, "customer", None):
		try:
			import frappe

			name = frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer
		except Exception:
			name = doc.customer
	if not name:
		return False, "No customer name configured"
	found = phrase_in_text(name, haystack)
	return found, name if found else f"Not found: {name}"


def match_logo_phrases(settings, haystack: str) -> tuple[bool, str]:
	phrases = [r.phrase for r in (settings.logo_phrases or []) if r.phrase]
	hit = match_any_phrase(phrases, haystack)
	return bool(hit), hit or "No logo phrase matched"


def match_gov_phrases(settings, haystack: str) -> tuple[bool, str]:
	required = [r.phrase for r in (settings.mandatory_government_text or []) if r.phrase and r.required]
	missing = [p for p in required if not phrase_in_text(p, haystack)]
	if missing:
		return False, f"Missing: {', '.join(missing)}"
	return True, "All mandatory government text found"


def find_cmyk_codes(text: str) -> list[str]:
	return CMYK_RE.findall(text) if text else []


def find_cmyk_full(text: str) -> list[str]:
	return CMYK_RE.findall(text) and [m.group(0) for m in CMYK_RE.finditer(text or "")] or []


def product_code_in_text(doc, haystack: str) -> tuple[bool, str]:
	candidates = []
	for val in (getattr(doc, "design_name", None), getattr(doc, "name", None), getattr(doc, "file_name", None)):
		val = (val or "").strip()
		if val:
			candidates.append(val)
	# product code often numeric prefix in filename
	for cand in candidates:
		m = re.search(r"\b(\d{3,6})\b", cand)
		if m and m.group(1) in haystack:
			return True, m.group(1)
		if cand and phrase_in_text(cand, haystack):
			return True, cand
	return False, "Product code not found in PDF text"
