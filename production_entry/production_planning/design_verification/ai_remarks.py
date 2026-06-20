# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations


def generate_ai_remarks(
	doc,
	bag_type: str,
	checklist_rows: list,
	score: float,
	status: str,
	analysis=None,
	color_mode: str = "Hybrid",
	color_note: str = "",
	manual_override: bool = False,
) -> str:
	design = getattr(doc, "design_name", None) or doc.name or ""
	file_name = getattr(doc, "file_name", None) or ""
	parts = [
		f"Design: {design} | Bag type: {bag_type} | File: {file_name}",
	]

	bag_inches = getattr(doc, "bag_size_inches", None) or ""
	if not bag_inches and analysis:
		bag_inches = getattr(analysis, "bag_size_inches_str", "") or ""

	dims = []
	mm_values = []
	for label, attr in (("W", "width"), ("H", "height"), ("G", "gusset"), ("Top fold", "top_folding")):
		val = getattr(doc, attr, None)
		if val:
			dims.append(f"{label} {val:g} mm")
			if attr != "top_folding":
				mm_values.append(f"{val:g}")

	if bag_inches and mm_values:
		inch_display = ' x '.join(f'{p.strip()}"' for p in bag_inches.split(' x '))
		parts.append(f"Bag size: {inch_display} ({' x '.join(mm_values)} mm)")
	elif dims:
		parts.append("Detected size: " + " x ".join(dims))
	elif bag_inches:
		parts.append(f"Bag size (inches): {bag_inches}")

	total = len(checklist_rows)
	passed = sum(1 for r in checklist_rows if r.get("checklist") == "1" or r.get("result") == "Pass")
	parts.append(f"Score: {passed}/{total} passed ({score:.0f}%) — Status: {status}")

	if manual_override:
		parts.append("Checklist reflects saved values (including manual edits).")

	if color_mode:
		parts.append(f"Color detection: {color_mode}")
	if color_note:
		parts.append(color_note)

	failed = [
		r.get("particulars") or r.get("sub_particular") or r.get("check_item")
		for r in checklist_rows
		if r.get("checklist") != "1" and r.get("result") != "Pass"
	]
	if failed:
		parts.append("Failed: " + ", ".join(failed[:8]) + ("..." if len(failed) > 8 else ""))

	if status == "Approved":
		parts.append("Recommendation: Ready for production release.")
	elif status == "Review":
		parts.append("Action: Review failed layout checks before releasing to production.")
	else:
		parts.append("Action: Fix PDF and re-upload — too many checks failed.")

	return "\n".join(parts)
