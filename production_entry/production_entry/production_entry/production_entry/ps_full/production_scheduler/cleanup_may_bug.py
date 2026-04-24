import frappe
import json

def cleanup_may_bug():
	frappe.init(site="1zt.frappe.cloud")
	frappe.connect()

	# Find any items that got pushed to May 2026 (the bug)
	# The bug pushed items to 2026-05-xx instead of 2026-03-xx
	items_to_revert = frappe.db.sql("""
		SELECT i.name, i.item_name, p.custom_pb_plan_name
		FROM `tabPlanning Sheet Item` i
		JOIN `tabPlanning sheet` p ON i.parent = p.name
		WHERE p.custom_pb_plan_name IS NOT NULL
		AND p.custom_planned_date >= '2026-05-01'
		AND p.custom_planned_date <= '2026-05-31'
	""", as_dict=True)

	print(f"Found {len(items_to_revert)} items stuck in May 2026 due to the date bug.")
	
	if not items_to_revert:
		print("No items to clean up.")
		return

	# Use the built-in revert APIs to safely pull them back
	# Wait, revert_items_to_color_chart cleans up the PB plan name now since my recent fix.
	from production_scheduler.api import revert_items_to_color_chart
	
	names = [i.item_name for i in items_to_revert]
	
	res = revert_items_to_color_chart(names)
	print("Cleanup result:", res)
	
if __name__ == "__main__":
	cleanup_may_bug()
