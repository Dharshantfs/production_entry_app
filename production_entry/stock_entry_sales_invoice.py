import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cstr, flt, getdate


def _merge_sales_invoice_items_by_item(target):
	"""One SI line per item (same warehouse/uom/rate); sum kg qty across STE rows."""
	if not target.get("items"):
		return

	buckets = {}
	order = []
	for row in target.items:
		key = (
			cstr(row.item_code),
			cstr(row.warehouse or ""),
			cstr(row.uom or row.stock_uom or ""),
			flt(row.rate),
		)
		if key not in buckets:
			data = row.as_dict()
			data.pop("name", None)
			data.pop("idx", None)
			buckets[key] = data
			order.append(key)
			continue

		existing = buckets[key]
		existing["qty"] = flt(existing["qty"]) + flt(row.qty)

	target.set("items", [])
	for key in order:
		data = buckets[key]
		data["amount"] = flt(data["qty"]) * flt(data["rate"])
		target.append("items", data)


@frappe.whitelist()
def make_sales_invoice_from_stock_entry(source_name, target_doc=None):
	"""Create Sales Invoice from submitted Stock Entry."""
	def set_missing_values(source, target):
		target.set_posting_time = 1
		target.posting_date = getdate(source.posting_date)
		target.due_date = getdate(source.posting_date)
		if source.get("party"):
			target.customer = source.get("party")
		target.set_warehouse = source.get("from_warehouse") or source.get("to_warehouse") or ""
		target.ignore_pricing_rule = 1
		_merge_sales_invoice_items_by_item(target)

	def condition(item):
		return flt(item.qty) > 0

	def update_item(source_item, target_item, source_parent):
		target_item.qty = flt(source_item.qty)
		target_item.rate = flt(source_item.basic_rate or source_item.valuation_rate or 0)
		target_item.uom = source_item.uom or source_item.stock_uom
		target_item.stock_uom = source_item.stock_uom or source_item.uom
		target_item.warehouse = source_item.t_warehouse or source_item.s_warehouse or source_parent.get("to_warehouse") or source_parent.get("from_warehouse")

	return get_mapped_doc(
		"Stock Entry",
		source_name,
		{
			"Stock Entry": {
				"doctype": "Sales Invoice",
				"field_no_map": ["name"],
				"validation": {"docstatus": ["=", 1]},
			},
			"Stock Entry Detail": {
				"doctype": "Sales Invoice Item",
				"field_map": {
					"item_code": "item_code",
					"item_name": "item_name",
					"description": "description",
				},
				"postprocess": update_item,
				"condition": condition,
			},
		},
		target_doc,
		set_missing_values,
	)
