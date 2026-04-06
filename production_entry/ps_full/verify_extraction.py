# Mocking frappe for verification
class MockDB:
    def get_value(self, doctype, filters, fieldname):
        if doctype == "Quality Master":
            code = filters.get("short_code") or filters.get("code") or filters.get("quality_code")
            if code == "100": return "PREMIUM"
        if doctype == "Colour Master":
            code = filters.get("colour_code") or filters.get("color_code") or filters.get("custom_color_code") or filters.get("short_code")
            if code == "483": return "BROWN 1.0"
        return None

class MockFrappe:
    db = MockDB()

frappe = MockFrappe()

item_code_str = "1001004830551420"
qual = ""
col = ""

if len(item_code_str) >= 9 and item_code_str.startswith("100"):
    q_code = item_code_str[3:6]
    c_code = item_code_str[6:9]
    
    qual_name = frappe.db.get_value("Quality Master", {"short_code": q_code}, "name") or \
               frappe.db.get_value("Quality Master", {"code": q_code}, "name") or \
               frappe.db.get_value("Quality Master", {"quality_code": q_code}, "name")
    if qual_name:
        qual = qual_name
    
    color_name = frappe.db.get_value("Colour Master", {"colour_code": c_code}, "colour_name") or \
                frappe.db.get_value("Colour Master", {"color_code": c_code}, "color_name") or \
                frappe.db.get_value("Colour Master", {"custom_color_code": c_code}, "color_name") or \
                frappe.db.get_value("Colour Master", {"short_code": c_code}, "colour_name")
    if color_name:
        col = color_name.upper().strip()

print(f"Item Code: {item_code_str}")
print(f"Extracted Quality: {qual}")
print(f"Extracted Color: {col}")

assert qual == "PREMIUM"
assert col == "BROWN 1.0"
print("✅ Verification Successful!")
