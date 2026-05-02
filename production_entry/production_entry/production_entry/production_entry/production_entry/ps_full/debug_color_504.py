#!/usr/bin/env python3
import frappe
frappe.init('/home/frappe/frappe-bench')
frappe.connect()

# Check Colour Master structure and find code 504
print("=== Checking Colour Master for code 504 ===\n")

# Get meta to see fields
meta = frappe.get_meta("Colour Master")
print("Available fields in Colour Master:")
for field in meta.fields:
    if field.fieldname in ['name', 'colour_name', 'color_name', 'colour_code', 'color_code', 'custom_color_code', 'short_code', 'code']:
        print(f"  - {field.fieldname} ({field.fieldtype})")

print("\n=== Searching for code 504 ===\n")

# Try different field names
fields_to_check = ['custom_color_code', 'colour_code', 'color_code', 'short_code', 'code']

for fld in fields_to_check:
    try:
        result = frappe.db.get_value(
            "Colour Master",
            {fld: "504"},
            ["name", "colour_name", "color_name", fld],
            as_dict=True
        )
        if result:
            print(f"✅ Found using field '{fld}':")
            print(f"   name: {result.get('name')}")
            print(f"   colour_name: {result.get('colour_name')}")
            print(f"   color_name: {result.get('color_name')}")
            print(f"   {fld}: {result.get(fld)}\n")
    except Exception as e:
        print(f"❌ Error checking {fld}: {e}\n")

# Also check if code is stored as integer
try:
    result = frappe.db.get_value(
        "Colour Master",
        {"custom_color_code": 504},
        ["name", "colour_name", "color_name"],
        as_dict=True
    )
    if result:
        print(f"✅ Found using numeric 504:")
        print(f"   {result}\n")
except Exception as e:
    print(f"Error: {e}\n")

# Get sample records to see structure
print("=== Sample Colour Master records ===\n")
samples = frappe.get_all("Colour Master", limit=5, fields=["name", "colour_name", "colour_code", "color_code", "custom_color_code", "short_code", "code"])
for sample in samples:
    print(f"  {sample}")

print("\n=== Searching for BEIGE 3.0 ===\n")
beige_recs = frappe.get_all("Colour Master", filters={"name": ["like", "%BEIGE%3.0%"]}, fields=["name", "colour_code", "color_code", "custom_color_code", "short_code", "code"])
for rec in beige_recs:
    print(f"  {rec}")
