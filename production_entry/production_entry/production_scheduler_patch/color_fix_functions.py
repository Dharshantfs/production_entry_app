
# Utility functions for fixing missing colors in Planning Sheets

@frappe.whitelist()
def fix_missing_colors_in_planning_sheets(planning_sheet_name=None):
    """
    Scans Planning Sheet items and populates missing colors from item codes.
    Item code structure: 100[Qual:3][Color:3][GSM:3][Width:4]
    Example: 1001035041001600 -> Color code at [6:9] = 504 = BEIGE 3.0
    
    Args:
        planning_sheet_name: Optional specific Planning Sheet to fix. If None, fixes all.
    
    Returns:
        {"fixed": count, "failed": count, "total": count}
    """
    frappe.only_for("System Manager")
    
    if planning_sheet_name:
        # Fix specific Planning Sheet
        items = frappe.db.get_all(
            "Planning Sheet Item",
            filters={"parent": planning_sheet_name},
            fields=["name", "parent", "item_code", "color"],
            limit_page_length=0
        )
        print(f"\nFixing colors for Planning Sheet: {planning_sheet_name}")
    else:
        # Fix all Planning Sheets with missing colors
        items = frappe.db.get_all(
            "Planning Sheet Item",
            filters={"color": ["in", ["", None]]},
            fields=["name", "parent", "item_code", "color"],
            limit_page_length=0
        )
        print(f"\nFixing ALL Planning Sheet items with missing colors")
    
    fixed_count = 0
    failed_count = 0
    
    for item in items:
        item_code_str = str(item.get("item_code") or "").strip()
        
        # Extract color code from item code (positions 6-8 for 16-digit codes)
        if len(item_code_str) >= 9 and item_code_str.startswith("100"):
            c_code = item_code_str[6:9]
            
            # Look up color using helper
            color_name = _get_color_by_code(c_code)
            
            if color_name:
                try:
                    frappe.db.set_value("Planning Sheet Item", item["name"], "color", color_name)
                    frappe.db.commit()
                    frappe.logger().info(
                        f"[Fix Color] Item {item['name']}: Code {c_code} → {color_name}"
                    )
                    fixed_count += 1
                except Exception as e:
                    frappe.logger().error(f"[Fix Color] Error: {str(e)}")
                    failed_count += 1
            else:
                frappe.logger().warning(
                    f"[Fix Color] Color code '{c_code}' not found in Colour Master for {item['name']}"
                )
                failed_count += 1
    
    result = {
        "fixed": fixed_count,
        "failed": failed_count,
        "total": len(items)
    }
    
    frappe.msgprint(
        f"✅ Color Fix Complete:<br/>"
        f"Fixed: {fixed_count}<br/>"
        f"Failed: {failed_count}<br/>"
        f"Total Checked: {len(items)}",
        title="Planning Sheet Color Fix"
    )
    
    return result


@frappe.whitelist()
def test_color_code_lookup(color_code):
    """
    Test color lookup for a specific code (for debugging).
    Returns the color name if found, None otherwise.
    """
    result = _get_color_by_code(color_code)
    return {
        "color_code": color_code,
        "color_name": result,
        "found": result is not None
    }
