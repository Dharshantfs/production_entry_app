# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations


def generate_ai_remarks(doc, bag_type: str, checklist_rows: list, score: float, status: str) -> str:
	design = getattr(doc, "design_name", None) or doc.name or ""
	file_name = getattr(doc, "file_name", None) or ""
	parts = [
		f"Design: {design} | Bag type: {bag_type} | File: {file_name}",
	]

	dims = []
	for label, attr in (("W", "width"), ("H", "height"), ("G", "gusset"), ("Top fold", "top_folding")):
		val = getattr(doc, attr, None)
		if val:
			dims.append(f"{label} {val:g} mm")
	if dims:
		parts.append("Detected size: " + " x ".join(dims))

	total = len(checklist_rows)
	passed = sum(1 for r in checklist_rows if r.get("result") == "Pass")
	parts.append(f"Score: {passed}/{total} passed ({score:.0f}%) — Status: {status}")

	failed = [
		r.get("particulars") or r.get("sub_particular") or r.get("check_item")
		for r in checklist_rows
		if r.get("result") != "Pass"
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
