import frappe

def check_color_code(code):
    res = frappe.db.get_value("Colour Master", {"custom_color_code": code}, ["name", "color_name", "short_code"], as_dict=True)
    if not res:
        res = frappe.db.get_value("Colour Master", {"color_code": code}, ["name", "color_name", "short_code"], as_dict=True)
    if not res:
        res = frappe.db.get_value("Colour Master", {"code": code}, ["name", "color_name", "short_code"], as_dict=True)
    return res

print(f"Code 483: {check_color_code('483')}")
print(f"Code 100 (Qual): {frappe.db.get_value('Quality Master', {'code': '100'}, 'name')}")
