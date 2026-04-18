# -*- coding: utf-8 -*-
"""
One-off migration: copy ``Planning sheet`` ``items`` (Planning sheet Item) into the board
child table (e.g. ``planned_items`` → Planning Table) when the board table is empty.

Run from bench console if needed::
    bench --site <site> execute production_entry.production_planning.migrate_scheduler_legacy_data.execute

Not registered in ``patches.txt`` by default (idempotent per sheet; safe to run manually).
"""
import frappe


def execute():
	frappe.logger().info("production_entry: Starting legacy → Planning Table migration...")
	child_doctype_last = None

	try:
		frappe.db.sql(
			"UPDATE `tabPlanning sheet` SET status = 'Locked (WO Created)' WHERE status = 'Locked (WO created)'"
		)
		frappe.db.commit()
	except Exception:
		pass

	try:
		frappe.db.sql(
			"UPDATE `tabPlanning sheet` SET planning_status = 'Locked (WO Created)' WHERE planning_status = 'Locked (WO created)'"
		)
		frappe.db.commit()
	except Exception:
		pass

	planning_sheets = frappe.get_all("Planning sheet", pluck="name")
	total_migrated = 0

	for ps_name in planning_sheets:
		doc = frappe.get_doc("Planning sheet", ps_name)

		target_field = None
		for field in [
			"planned_items",
			"custom_planned_items",
			"planning_table",
			"custom_planning_table",
			"table",
		]:
			if hasattr(doc, field) or doc.meta.has_field(field):
				target_field = field
				break

		if not target_field:
			continue

		existing_new_items = getattr(doc, target_field, [])
		if len(existing_new_items) > 0:
			continue

		old_items = getattr(doc, "items", [])
		if not old_items:
			continue

		child_doctype = doc.meta.get_field(target_field).options
		if not child_doctype:
			continue
		child_doctype_last = child_doctype

		for old_row in old_items:
			new_row = frappe.new_doc(child_doctype)
			new_row.parent = doc.name
			new_row.parentfield = target_field
			new_row.parenttype = "Planning sheet"

			def copy_field(target_doc, source_doc, target_field_name, source_field_name):
				val = source_doc.get(source_field_name)
				if val is not None:
					target_doc.set(target_field_name, val)

			fields_to_copy = [
				"sales_order_item",
				"item_code",
				"item_name",
				"qty",
				"uom",
				"color",
				"unit",
				"custom_quality",
				"gsm",
				"width_inch",
				"idx",
				"party_code",
			]
			if frappe.db.has_column(child_doctype, "quality"):
				fields_to_copy.append("quality")
			for f in fields_to_copy:
				copy_field(new_row, old_row, f, f)

			copy_field(new_row, old_row, "spr_name", "custom_spr_name")
			copy_field(new_row, old_row, "pp_id", "production_plan")
			copy_field(new_row, old_row, "planned_date", "custom_item_planned_date")
			copy_field(new_row, old_row, "plan_name", "custom_plan_code")
			copy_field(new_row, old_row, "is_split", "custom_is_split")
			copy_field(new_row, old_row, "split_from", "custom_split_from")

			if new_row.get("is_split") is None:
				new_row.is_split = 0
			if (
				frappe.db.has_column(child_doctype, "quality")
				and not (new_row.get("quality") or "").strip()
				and (new_row.get("custom_quality") or "").strip()
			):
				new_row.quality = new_row.custom_quality

			new_row.db_insert()
			total_migrated += 1

	frappe.db.commit()
	msg = (
		f"Migrated {total_migrated} legacy rows into {child_doctype_last or 'board child table'}."
	)
	print(msg)
	frappe.logger().info("production_entry: " + msg)
	return {"migrated": total_migrated, "child_doctype": child_doctype_last}

