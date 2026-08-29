import os

import frappe


def execute():
	"""Disable old Work Order batch-pick client scripts and sync the fabric-only picker."""
	app_path = frappe.get_app_path("production_entry")
	js_path = os.path.join(app_path, "public", "js", "work_order_start_production.js")
	if not os.path.exists(js_path):
		return
	with open(js_path, "r", encoding="utf-8") as f:
		script = f.read()

	synced = None
	for cs in frappe.get_all("Client Script", filters={"dt": "Work Order"}, fields=["name"]):
		doc = frappe.get_doc("Client Script", cs.name)
		body = doc.script or ""
		if "wo_is_fabric_roll_item" in body:
			synced = doc
			continue
		if "wo_fabric_rm_rows" in body or "wo_open_fabric_batch_pick_dialog" in body:
			doc.enabled = 0
			doc.save(ignore_permissions=True)

	if synced:
		synced.script = script
		synced.enabled = 1
		synced.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			{
				"doctype": "Client Script",
				"dt": "Work Order",
				"view": "Form",
				"enabled": 1,
				"script": script,
			}
		).insert(ignore_permissions=True)

	for ss in frappe.get_all("Server Script", fields=["name", "api_method"]):
		if str(ss.get("api_method") or "").strip() == "auto_material_transfer":
			doc = frappe.get_doc("Server Script", ss.name)
			if hasattr(doc, "disabled"):
				doc.disabled = 1
				doc.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Work Order")
