# Clubbing Sheet — Before Submit Server Script (paste on site ONLY if you keep site scripts)
#
# Script Type: DocType Event
# Reference Document Type: Clubbing Sheet
# DocType Event: Before Submit
# Enabled: Yes
#
# Prefer disabling this and using the app hook instead:
#   production_entry.production_planning.clubbing_sheet_hooks.clubbing_sheet_before_submit
#
# IMPORTANT: Do NOT use frappe.db.has_column — it is blocked in Server Script safe_exec.

if not (doc.trip_id or "").strip():
	frappe.throw("Please enter a Trip ID before submitting the Clubbing Sheet.")

if not doc.get("items"):
	frappe.throw("Please add at least one item before submitting.")


def _has_field(doctype, fieldname):
	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


has_pt_club = _has_field("Planning Table", "custom_clubbing_sheet")
has_psi_club = _has_field("Planning sheet Item", "custom_clubbing_sheet")
has_pt_seq = _has_field("Planning Table", "custom_loading_sequence")
has_pt_ord = _has_field("Planning Table", "custom_club_load_order")
has_psi_seq = _has_field("Planning sheet Item", "custom_loading_sequence")
has_psi_ord = _has_field("Planning sheet Item", "custom_club_load_order")

if not has_pt_club and not has_psi_club:
	frappe.msgprint(
		"Planning club fields missing — run bench migrate (custom_clubbing_sheet).",
		indicator="orange",
		alert=True,
	)
else:
	for item in doc.items:
		party = (item.party_code or "").strip()
		so = (item.sales_order or "").strip()
		seq = (item.loading_sequence or "").strip()
		load_order = int(item.idx or 0)
		ptr = (
			getattr(item, "custom_planning_table_row", None)
			or getattr(item, "planning_table_row", None)
			or ""
		)
		ptr = str(ptr).strip()
		planning_sheet = (
			getattr(item, "custom_planning_sheet", None)
			or getattr(item, "planning_sheet", None)
			or ""
		)
		planning_sheet = str(planning_sheet).strip()

		pt_rows = []
		if ptr:
			pt_rows = frappe.db.sql(
				"""
				select pt.name as pt_name, pt.parent
				from `tabPlanning Table` pt
				where pt.name = %s
				""",
				ptr,
				as_dict=True,
			) or []
		elif planning_sheet:
			pt_rows = frappe.db.sql(
				"""
				select pt.name as pt_name, pt.parent
				from `tabPlanning Table` pt
				where pt.parent = %s
				  and ifnull(pt.custom_movement_type, '') = 'Despatch'
				""",
				planning_sheet,
				as_dict=True,
			) or []
		elif so:
			pt_rows = frappe.db.sql(
				"""
				select pt.name as pt_name, pt.parent
				from `tabPlanning Table` pt
				inner join `tabPlanning sheet` ps on ps.name = pt.parent
				where ps.sales_order = %s
				  and ifnull(pt.custom_movement_type, '') = 'Despatch'
				  and ifnull(ps.docstatus, 0) < 2
				""",
				so,
				as_dict=True,
			) or []
		elif party:
			pt_rows = frappe.db.sql(
				"""
				select pt.name as pt_name, pt.parent
				from `tabPlanning Table` pt
				inner join `tabPlanning sheet` ps on ps.name = pt.parent
				where ps.party_code = %s
				  and ifnull(pt.custom_movement_type, '') = 'Despatch'
				  and ifnull(ps.docstatus, 0) < 2
				""",
				party,
				as_dict=True,
			) or []

		for m in pt_rows:
			if has_pt_club:
				vals = {"custom_clubbing_sheet": doc.name}
				if has_pt_seq:
					vals["custom_loading_sequence"] = seq
				if has_pt_ord:
					vals["custom_club_load_order"] = load_order
				frappe.db.set_value("Planning Table", m.pt_name, vals, update_modified=False)

			if has_psi_club and m.parent:
				psi_rows = frappe.db.sql(
					"""
					select name from `tabPlanning sheet Item`
					where parent = %s and ifnull(custom_movement_type, '') = 'Despatch'
					""",
					m.parent,
					as_dict=True,
				) or []
				for p in psi_rows:
					pvals = {"custom_clubbing_sheet": doc.name}
					if has_psi_seq:
						pvals["custom_loading_sequence"] = seq
					if has_psi_ord:
						pvals["custom_club_load_order"] = load_order
					frappe.db.set_value("Planning sheet Item", p.name, pvals, update_modified=False)
