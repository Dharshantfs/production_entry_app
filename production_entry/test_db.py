import frappe
frappe.init(site="jayashreespunbond-1zl.frappe.cloud")
frappe.connect()

print("--- 1001132211200950 ---")
pt_rows = frappe.get_all("Planning Table", filters={"item_code": "1001132211200950"}, fields=["name", "parent", "item_code", "qty", "planned_date", "docstatus", "color", "custom_parent_child_trace_id", "sales_order_item"])
print(f"Planning Table: {pt_rows}")

sheet_rows = frappe.get_all("Planning sheet Item", filters={"item_code": "1001132211200950"}, fields=["name", "parent", "item_code", "qty", "docstatus"])
print(f"Planning sheet Item: {sheet_rows}")

print("--- 1001101010801020 ---")
pt_rows2 = frappe.get_all("Planning Table", filters={"item_code": "1001101010801020"}, fields=["name", "parent", "item_code", "qty", "planned_date", "docstatus", "color", "custom_parent_child_trace_id", "sales_order_item"])
print(f"Planning Table: {pt_rows2}")

sheet_rows2 = frappe.get_all("Planning sheet Item", filters={"item_code": "1001101010801020"}, fields=["name", "parent", "item_code", "qty", "docstatus"])
print(f"Planning sheet Item: {sheet_rows2}")

