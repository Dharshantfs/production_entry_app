"""
Simple Frappe Whitelist Test for Quality Extraction
Add this to production_scheduler/api.py and call via frappe.call() from console

Usage:
frappe.call({
    method: 'production_scheduler.api.test_quality_extraction_whitelist',
    callback: function(r) { console.log(r.message); }
});
"""

@frappe.whitelist()
def test_quality_extraction_whitelist():
    """
    Standalone test for quality code extraction.
    Can be called from console or API.
    Returns results that verify the implementation is working.
    """
    import json
    
    results = {
        "status": "pending",
        "tests": [],
        "warnings": [],
        "errors": []
    }
    
    try:
        # TEST 1: Check Quality Master has quality_code field
        print("\n[TEST 1] Checking Quality Master structure...")
        qm_count = frappe.db.count("Quality Master")
        results["tests"].append({
            "name": "Quality Master Count",
            "value": qm_count,
            "passed": qm_count > 0
        })
        
        if qm_count == 0:
            results["warnings"].append("No Quality Masters found in database")
        
        # Get meta to check for quality_code field
        try:
            qm_meta = frappe.get_meta("Quality Master")
            qm_fields = [f.fieldname for f in qm_meta.fields]
            has_qc_field = "quality_code" in qm_fields
            results["tests"].append({
                "name": "Quality Master has quality_code field",
                "value": has_qc_field,
                "passed": has_qc_field,
                "available_fields": qm_fields[:10]  # Sample
            })
        except Exception as e:
            results["warnings"].append(f"Could not check QM meta: {e}")
        
        # TEST 2: Sample Quality Masters
        print("\n[TEST 2] Sampling Quality Masters...")
        qm_sample = frappe.db.sql("""
            SELECT name, 
                   short_code, 
                   code,
                   quality_code
            FROM `tabQuality Master`
            LIMIT 5
        """, as_dict=True)
        
        results["tests"].append({
            "name": "Quality Master Samples",
            "count": len(qm_sample),
            "samples": qm_sample
        })
        
        # TEST 3: Test extraction logic manually
        print("\n[TEST 3] Testing extraction logic...")
        test_item_codes = [
            "1001165421501865",  # 100 + 116 + 542 + 150 + 1865
            "1001035041001600",  # 100 + 103 + 504 + 100 + 1600
        ]
        
        extraction_results = []
        for item_code in test_item_codes:
            item_code_str = str(item_code).strip()
            if len(item_code_str) >= 9 and item_code_str.startswith("100"):
                q_code = item_code_str[3:6]
                c_code = item_code_str[6:9]
                
                # Try lookups
                qual_name = None
                lookup_method = None
                
                for field in ["short_code", "code", "quality_code"]:
                    try:
                        result = frappe.db.get_value("Quality Master", {field: q_code}, "name")
                        if result:
                            qual_name = result
                            lookup_method = field
                            break
                    except:
                        pass
                
                extraction_results.append({
                    "item_code": item_code,
                    "extracted_q_code": q_code,
                    "extracted_c_code": c_code,
                    "quality_found": qual_name or "NOT FOUND",
                    "lookup_field": lookup_method or "none"
                })
        
        results["tests"].append({
            "name": "Manual Extraction Tests",
            "results": extraction_results
        })
        
        # TEST 4: Check existing Planning Sheet items
        print("\n[TEST 4] Checking existing Planning Sheet items...")
        psi_with_quality = frappe.db.sql("""
            SELECT COUNT(*) as count_with_quality
            FROM `tabPlanning Sheet Item`
            WHERE custom_quality IS NOT NULL AND custom_quality != ''
        """, as_dict=True)[0]['count_with_quality']
        
        psi_without_quality = frappe.db.sql("""
            SELECT COUNT(*) as count_without_quality
            FROM `tabPlanning Sheet Item`
            WHERE custom_quality IS NULL OR custom_quality = ''
        """, as_dict=True)[0]['count_without_quality']
        
        psi_total = psi_with_quality + psi_without_quality
        
        results["tests"].append({
            "name": "Planning Sheet Item Quality Population",
            "total_items": psi_total,
            "with_quality": psi_with_quality,
            "without_quality": psi_without_quality,
            "percentage_populated": round((psi_with_quality / psi_total * 100) if psi_total > 0 else 0, 2)
        })
        
        # Get sample items with quality
        if psi_with_quality > 0:
            psi_samples = frappe.db.sql("""
                SELECT name, item_code, custom_quality, parent
                FROM `tabPlanning Sheet Item`
                WHERE custom_quality IS NOT NULL AND custom_quality != ''
                LIMIT 5
            """, as_dict=True)
            
            results["tests"].append({
                "name": "Sample PSI Items with Quality",
                "samples": psi_samples
            })
        
        # TEST 5: Verify function exists and is callable
        print("\n[TEST 5] Verifying _populate_planning_sheet_items function...")
        try:
            from production_scheduler.api import _populate_planning_sheet_items
            results["tests"].append({
                "name": "_populate_planning_sheet_items function",
                "status": "exists and callable",
                "passed": True
            })
        except ImportError as e:
            results["errors"].append(f"Failed to import function: {e}")
            results["tests"].append({
                "name": "_populate_planning_sheet_items function",
                "status": "import failed",
                "passed": False
            })
        
        # Overall status
        failed_tests = [t for t in results["tests"] if "passed" in t and not t["passed"]]
        results["status"] = "PASSED" if not failed_tests and not results["errors"] else "PARTIAL" if not results["errors"] else "FAILED"
        
        print("\n" + "="*70)
        print("QUALITY EXTRACTION TEST RESULTS")
        print("="*70)
        print(json.dumps(results, indent=2, default=str))
        
        return results
        
    except Exception as e:
        results["status"] = "ERROR"
        results["errors"].append(str(e))
        import traceback
        results["traceback"] = traceback.format_exc()
        return results
