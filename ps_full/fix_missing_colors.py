#!/usr/bin/env python3
"""
Utility to fix missing colors in Planning Sheets.
Item code structure: 100[Qual:3][Color:3][GSM:3][Width:4]
Example: 1001035041001600 -> Color code at [6:9] = 504 = BEIGE 3.0
"""
import frappe


def _get_color_by_code(color_code):
    """
    Look up color in Colour Master by color code.
    Returns the color name if found, None otherwise.
    """
    if not color_code:
        return None
    
    color_code = str(color_code).strip()
    
    # Try multiple field names in order of preference
    fields_to_try = ["custom_color_code", "colour_code", "color_code", "short_code", "code"]
    
    for field in fields_to_try:
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
                    return color_name.upper().strip()
        except Exception:
            pass
    
    return None


@frappe.whitelist()
def fix_missing_colors_in_planning_sheets():
    """
    Scans all Planning Sheet items and populates missing colors.
    Returns summary of fixed items.
    """
    frappe.only_for("System Manager")
    
    fixed_count = 0
    failed_count = 0
    unchanged_count = 0
    
    # Get all Planning Sheet items with missing colors
    items = frappe.db.get_all(
        "Planning Sheet Item",
        filters={"color": ["in", ["", None]]},
        fields=["name", "parent", "item_code", "color"],
        limit_page_length=0
    )
    
    print(f"\n{'='*60}")
    print(f"Found {len(items)} Planning Sheet items with missing colors")
    print(f"{'='*60}\n")
    
    for item in items:
        item_code = item.get("item_code", "")
        item_code_str = str(item_code or "").strip()
        
        # Extract color code from item code (positions 6-8 for 16-digit codes)
        if len(item_code_str) >= 9 and item_code_str.startswith("100"):
            c_code = item_code_str[6:9]
            
            # Look up color
            color_name = _get_color_by_code(c_code)
            
            if color_name:
                # Update the item
                try:
                    frappe.db.set_value("Planning Sheet Item", item["name"], "color", color_name)
                    frappe.db.commit()
                    print(f"✅ Fixed {item['name']}: Code {c_code} → {color_name}")
                    fixed_count += 1
                except Exception as e:
                    print(f"❌ Error fixing {item['name']}: {str(e)}")
                    failed_count += 1
            else:
                print(f"⚠️  Code {c_code} not found in Colour Master for {item['name']}")
                failed_count += 1
        else:
            unchanged_count += 1
    
    summary = {
        "fixed": fixed_count,
        "failed": failed_count,
        "unchanged": unchanged_count,
        "total": len(items)
    }
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Fixed: {fixed_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Unchanged: {unchanged_count}")
    print(f"  Total: {len(items)}")
    print(f"{'='*60}\n")
    
    return summary


@frappe.whitelist()
def test_color_lookup(color_code):
    """
    Test color lookup for a specific code.
    Usage: bench execute fix_missing_colors.test_color_lookup --args '["504"]'
    """
    result = _get_color_by_code(color_code)
    print(f"\nColor lookup for code '{color_code}':")
    print(f"Result: {result}\n")
    return result


if __name__ == "__main__":
    frappe.init('/home/frappe/frappe-bench')
    frappe.connect()
    
    # Test lookup for code 504
    result = test_color_lookup("504")
    
    # Fix all missing colors
    # summary = fix_missing_colors_in_planning_sheets()
