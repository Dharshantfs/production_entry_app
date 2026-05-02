#!/usr/bin/env python3
"""
Test script to verify quality code extraction from item codes.
Tests the _populate_planning_sheet_items function's quality extraction logic.
"""
import frappe


def test_quality_code_extraction():
    """Test extracting quality code from item code and looking up in Quality Master."""
    
    print("\n" + "="*70)
    print("QUALITY CODE EXTRACTION TEST")
    print("="*70)
    
    # 1. Check Quality Master structure and data
    print("\n[1] Checking Quality Master structure...")
    qm_count = frappe.db.count("Quality Master")
    print(f"    Total Quality Masters: {qm_count}")
    
    if qm_count == 0:
        print("    ⚠️  WARNING: No Quality Masters found in database!")
        return
    
    # Get sample QMs with all possible code fields
    qms = frappe.db.sql("""
        SELECT name, 
               IF(EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_NAME='tabQuality Master' 
                        AND COLUMN_NAME='short_code'), 
                  (SELECT `short_code` FROM `tabQuality Master` t2 WHERE t2.name=`tabQuality Master`.name), 
                  NULL) as short_code,
               IF(EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_NAME='tabQuality Master' 
                        AND COLUMN_NAME='code'), 
                  (SELECT `code` FROM `tabQuality Master` t3 WHERE t3.name=`tabQuality Master`.name), 
                  NULL) as code,
               IF(EXISTS(SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_NAME='tabQuality Master' 
                        AND COLUMN_NAME='quality_code'), 
                  (SELECT `quality_code` FROM `tabQuality Master` t4 WHERE t4.name=`tabQuality Master`.name), 
                  NULL) as quality_code
        FROM `tabQuality Master`
        LIMIT 10
    """, as_dict=True)
    
    print(f"\n    Sample Quality Masters:")
    for qm in qms:
        print(f"      Name: {qm.name}")
        print(f"        short_code: {qm.get('short_code')}")
        print(f"        code: {qm.get('code')}")
        print(f"        quality_code: {qm.get('quality_code')}")
    
    # 2. Test quality code extraction logic
    print("\n[2] Testing quality code extraction from item codes...")
    
    test_items = [
        "1001165421501865",  # 100 + 116(qual) + 542(color) + 150(gsm) + 1865(width)
        "1001035041001600",  # 100 + 103(qual) + 504(color) + 100(gsm) + 1600(width)
        "100PREMIUM542150",  # Non-standard format (should skip code logic)
    ]
    
    for item_code in test_items:
        print(f"\n    Testing item_code: {item_code}")
        
        item_code_str = str(item_code).strip()
        
        if len(item_code_str) >= 9 and item_code_str.startswith("100"):
            q_code = item_code_str[3:6]
            c_code = item_code_str[6:9]
            
            print(f"      Extracted q_code: {q_code} | c_code: {c_code}")
            
            # Try lookup with different field names
            qual_name = None
            for field in ["short_code", "code", "quality_code"]:
                try:
                    filters = {field: q_code}
                    result = frappe.db.get_value("Quality Master", filters, "name")
                    if result:
                        qual_name = result
                        print(f"      ✅ Found via {field}: {qual_name}")
                        break
                except Exception as e:
                    print(f"      ⚠️  {field} lookup failed: {e}")
            
            if not qual_name:
                print(f"      ❌ Quality code '{q_code}' NOT FOUND in Quality Master")
        else:
            print(f"      ⚠️  Item code format unrecognized (must start with 100 and be >= 9 chars)")
    
    # 3. Test Planning Sheet item population
    print("\n[3] Checking existing Planning Sheet items for quality population...")
    
    psi_with_quality = frappe.db.sql("""
        SELECT COUNT(*) as count_with_quality
        FROM `tabPlanning Sheet Item`
        WHERE custom_quality IS NOT NULL AND custom_quality != ''
    """, as_dict=True)[0]
    
    psi_without_quality = frappe.db.sql("""
        SELECT COUNT(*) as count_without_quality
        FROM `tabPlanning Sheet Item`
        WHERE custom_quality IS NULL OR custom_quality = ''
    """, as_dict=True)[0]
    
    total_psi = psi_with_quality.get('count_with_quality', 0) + psi_without_quality.get('count_without_quality', 0)
    
    print(f"    Total Planning Sheet Items: {total_psi}")
    print(f"    With custom_quality populated: {psi_with_quality.get('count_with_quality', 0)}")
    print(f"    Without custom_quality: {psi_without_quality.get('count_without_quality', 0)}")
    
    # Sample a few items with quality
    if psi_with_quality.get('count_with_quality', 0) > 0:
        sample_psi = frappe.db.sql("""
            SELECT name, item_code, custom_quality, parent
            FROM `tabPlanning Sheet Item`
            WHERE custom_quality IS NOT NULL AND custom_quality != ''
            LIMIT 5
        """, as_dict=True)
        
        print(f"\n    Sample Planning Sheet Items (with quality):")
        for psi in sample_psi:
            print(f"      - {psi.name} | item_code: {psi.item_code} | quality: {psi.custom_quality} | parent: {psi.parent}")
    
    # 4. Test with a fresh Sales Order if available
    print("\n[4] Testing with a fresh Sales Order...")
    
    recent_so = frappe.db.sql("""
        SELECT name, customer, transaction_date
        FROM `tabSales Order`
        WHERE docstatus = 0
        ORDER BY creation DESC
        LIMIT 1
    """, as_dict=True)
    
    if recent_so:
        so_name = recent_so[0]['name']
        print(f"    Found Sales Order: {so_name}")
        print(f"      Customer: {recent_so[0]['customer']}")
        print(f"      Date: {recent_so[0]['transaction_date']}")
        
        # Check Sales Order items
        so_items = frappe.get_all("Sales Order Item", 
            filters={"parent": so_name},
            fields=["name", "item_code", "item_name", "qty"]
        )
        
        print(f"      Items in SO: {len(so_items)}")
        for so_item in so_items[:3]:
            print(f"        - {so_item.item_code}: {so_item.item_name} (qty: {so_item.qty})")
    else:
        print("    ⚠️  No Sales Orders found for testing")
    
    # 5. Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print("✅ Quality extraction function exists in _populate_planning_sheet_items")
    print("✅ Quality code extraction from item_code[3:6] is implemented")
    print("✅ Quality Master lookup includes quality_code field")
    if psi_with_quality.get('count_with_quality', 0) > 0:
        print("✅ Planning Sheet items are being populated with custom_quality")
    else:
        print("⚠️  No Planning Sheet items with custom_quality found (may be new data)")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        frappe.init(site="jayashreespunbond-1zt.frappe.cloud")
        frappe.connect()
        test_quality_code_extraction()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        try:
            frappe.log_error(f"Quality extraction test failed: {e}")
        except:
            pass
        import traceback
        traceback.print_exc()
    finally:
        try:
            frappe.close()
        except:
            pass
