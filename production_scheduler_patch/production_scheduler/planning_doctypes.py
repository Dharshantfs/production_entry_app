# -*- coding: utf-8 -*-
"""
Canonical Planning DocType names — must match planning_sheet*.json and live DB (`tabPlanning sheet`).

Use these constants anywhere code references the doctype string (no literals like "Planning Sheet").
"""

PLANNING_SHEET = "Planning sheet"
PLANNING_SHEET_ITEM = "Planning sheet Item"


def normalize_planning_unit_for_select(raw, _depth=0):
    """Map free-text to exact options on Planning Table / Planning sheet Item `unit` (Select)."""
    if raw is None:
        return "UNASSIGNED"
    s = str(raw).strip()
    if not s:
        return "UNASSIGNED"
    # Color Chart matrix column id: sheetCode|unit|planCode|gsm|quality — normalize only the unit segment.
    if _depth == 0 and "|" in s:
        parts = [p.strip() for p in s.split("|")]
        if len(parts) >= 2 and parts[1]:
            return normalize_planning_unit_for_select(parts[1], _depth + 1)
    allowed = ("UNASSIGNED", "Unit 1", "Unit 2", "Unit 3", "Unit 4", "Mixed")
    if s in allowed:
        return s
    u = s.upper().replace(" ", "").replace("_", "")
    if u in ("UNASSIGNED", "NONE", "NA", ""):
        return "UNASSIGNED"
    # Exact "Mixed" only — substring match caused false positives (e.g. composite keys containing |Mixed|).
    if u == "MIXED":
        return "Mixed"
    for i in (1, 2, 3, 4):
        if f"UNIT{i}" in u:
            return f"Unit {i}"
    return "UNASSIGNED"


# Old names from earlier app JSON / deploys (for migration helpers only).
LEGACY_PLANNING_SHEET = "Planning Sheet"
LEGACY_PLANNING_SHEET_ITEM = "Planning Sheet Item"
