#!/usr/bin/env python3
"""
Fix Missing Colors in Planning Sheets
Item code structure: 100[Qual:3][Color:3][GSM:3][Width:4]
Example: 1001035041001600 -> Positions 6-8 = "504" → Colour Master lookup → "BEIGE 3.0"
"""
import frappe
import sys

def test_color_code(code):
    """Test color lookup for debugging"""
    print(f"\n{'='*60}")
    print(f"Testing Color Code: {code}")
    print(f"{'='*60}\n")
    
    # Try different field names
    fields_to_check = ['custom_color_code', 'colour_code', 'color_code', 'short_code', 'code']
    
    found = False
    for field in fields_to_check:
        try:
            result = frappe.db.get_value(
                "Colour Master",
                {field: code},
                ["name", "colour_name", "color_name"],
                as_dict=True
            )
            if result:
                print(f"✅ Found in field '{field}':")
                print(f"   name: {result.get('name')}")
                print(f"   colour_name: {result.get('colour_name')}")
                print(f"   color_name: {result.get('color_name')}")
                found = True
                break
        except Exception as e:
            print(f"   Error checking {field}: {e}")
    
    if not found:
        print(f"❌ Color code '{code}' NOT FOUND in Colour Master\n")
        print("   Available colors with similar codes:")
        try:
            samples = frappe.get_all("Colour Master", limit=5, fields=["name", "colour_code", "color_code", "custom_color_code", "short_code", "code"])
            for sample in samples:
                print(f"   - {sample}")
        except Exception as e:
            print(f"   Error fetching samples: {e}")
    
    print()
    return found


def fix_missing_colors():
    """Fix all Planning Sheet items with missing colors"""
    print(f"\n{'='*60}")
    print(f"Fixing Missing Colors in Planning Sheets")
    print(f"{'='*60}\n")
    
    # Get all items with missing colors
    items = frappe.db.get_all(
        "Planning Sheet Item",
        filters={"color": ["in", ["", None]]},
        fields=["name", "parent", "item_code", "color"],
        limit_page_length=None
    )
    
    print(f"Found {len(items)} items with missing colors\n")
    
    fixed = 0
    failed = 0
    
    for item in items:
        item_code = str(item.get("item_code") or "").strip()
        
        # Check if item code follows 16-digit pattern
        if len(item_code) >= 9 and item_code.startswith("100"):
            color_code = item_code[6:9]
            
            # Look up color in Colour Master
            color_name = None
            fields_to_check = ['custom_color_code', 'colour_code', 'color_code', 'short_code', 'code']
            
            for field in fields_to_check:
                try:
                    result = frappe.db.get_value(
                        "Colour Master",
                        {field: color_code},
                        ["name", "colour_name", "color_name"],
                        as_dict=True
                    )
                    if result:
                        color_name = result.get("name") or result.get("colour_name") or result.get("color_name")
                        if color_name:
                            break
                except Exception:
                    pass
            
            if color_name:
                try:
                    frappe.db.set_value("Planning Sheet Item", item["name"], "color", color_name)
                    frappe.db.commit()
                    print(f"✅ {item['parent']} → Item {item['name']}: Code {color_code} = {color_name}")
                    fixed += 1
                except Exception as e:
                    print(f"❌ Error fixing {item['name']}: {e}")
                    failed += 1
            else:
                print(f"⚠️  Code {color_code} NOT FOUND for {item['name']} in Planning Sheet {item['parent']}")
                failed += 1
        else:
            print(f"⚠️  Invalid item code format: {item_code}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Fixed: {fixed}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(items)}")
    print(f"{'='*60}\n")
    
    return {"fixed": fixed, "failed": failed, "total": len(items)}


if __name__ == "__main__":
    frappe.init('/home/frappe/frappe-bench')
    frappe.connect()
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test mode: lookup specific color code
        code = sys.argv[2] if len(sys.argv) > 2 else "504"
        test_color_code(code)
    else:
        # Fix all missing colors
        fix_missing_colors()
    
    frappe.close()
