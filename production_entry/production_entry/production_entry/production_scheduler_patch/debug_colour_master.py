import frappe

def debug_colour_master():
    print("Inspecting Colour Master DocType...")
    try:
        meta = frappe.get_meta("Colour Master")
        print("Fields:")
        for f in meta.fields:
            print(f"  - {f.fieldname} ({f.label})")
        
        print("\nSearching for record with code 483...")
        # Try different possible filters
        records = frappe.get_all("Colour Master", 
            filters={"colour_code": "483"}, 
            fields=["name", "colour_name", "colour_code"]
        )
        if not records:
             records = frappe.get_all("Colour Master", 
                filters={"custom_color_code": "483"}, 
                fields=["*"]
            )
        
        if records:
            print(f"Found record: {records[0]}")
        else:
            print("No record found for code 483 with standard filters.")
            # List some records to see structure
            samples = frappe.get_all("Colour Master", limit=5, fields=["*"])
            print(f"Sample records: {samples}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_colour_master()
