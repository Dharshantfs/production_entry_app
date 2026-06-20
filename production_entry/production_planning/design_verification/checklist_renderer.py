# Copyright (c) 2026, Production Planning and contributors
# For license information, please see license.txt

from __future__ import annotations

import html
from collections import OrderedDict


def render_checklist_html(doc) -> str:
	rows = getattr(doc, "design_verification_checklist", None) or []
	design_name = html.escape(getattr(doc, "design_name", None) or "")
	file_name = html.escape(getattr(doc, "file_name", None) or "")
	file_type = html.escape(getattr(doc, "file_type", None) or "CDR & PDF")
	cdr_version = html.escape(getattr(doc, "cdr_version", None) or "25 VERSION")
	checked_by = html.escape(getattr(doc, "checked_by_name", None) or "")
	checked_date = html.escape(str(getattr(doc, "checked_by_date", None) or ""))
	checked_sign = html.escape(getattr(doc, "checked_by_sign", None) or "")

	header = (
		f"<div class='dv-header'>"
		f"<strong>DESIGN NAME:</strong> {design_name} &nbsp;&nbsp; "
		f"<strong>FILE NAME:</strong> {file_name} &nbsp;&nbsp; "
		f"<strong>FILE TYPE:</strong> {file_type} &nbsp;&nbsp; "
		f"<strong>CDR VERSION:</strong> {cdr_version}"
		f"</div>"
	)

	# group by sno + particulars
	groups: OrderedDict[tuple, list] = OrderedDict()
	for row in rows:
		key = (row.sno, (row.particulars or "").strip())
		groups.setdefault(key, []).append(row)

	body_rows = []
	for (sno, particulars), group in groups.items():
		rowspan = len(group)
		for idx, row in enumerate(group):
			display_sno = str(sno or "") if idx == 0 else ""
			display_part = html.escape(particulars) if idx == 0 else ""
			sno_cell = f"<td rowspan='{rowspan}'>{display_sno}</td>" if idx == 0 else ""
			part_cell = f"<td rowspan='{rowspan}'>{display_part}</td>" if idx == 0 else ""
			body_rows.append(
				"<tr>"
				f"{sno_cell}"
				f"{part_cell}"
				f"<td>{html.escape(row.sub_item or '')}</td>"
				f"<td>{html.escape(row.sub_particular or '')}</td>"
				f"<td>{html.escape(str(row.measurement or ''))}</td>"
				f"<td style='text-align:center'>{html.escape(row.checklist or '0')}</td>"
				"</tr>"
			)

	table = (
		"<table class='dv-checklist' border='1' cellspacing='0' cellpadding='4' style='width:100%;border-collapse:collapse'>"
		"<thead><tr>"
		"<th>S.No</th><th>Particulars</th><th></th><th></th><th>Measurement</th><th>Checklist</th>"
		"</tr></thead>"
		f"<tbody>{''.join(body_rows)}</tbody></table>"
	)

	footer = (
		f"<div class='dv-footer' style='margin-top:12px'>"
		f"<strong>CHECKED BY</strong><br>"
		f"NAME : {checked_by}<br>"
		f"DATE : {checked_date}<br>"
		f"SIGN: {checked_sign}"
		f"</div>"
	)

	css = (
		"<style>"
		".dv-header{margin-bottom:8px;font-size:12px}"
		".dv-checklist th{background:#f0f0f0;font-weight:bold;font-size:11px}"
		".dv-checklist td{font-size:11px;vertical-align:top}"
		".dv-footer{font-size:11px}"
		"</style>"
	)
	return css + header + table + footer
