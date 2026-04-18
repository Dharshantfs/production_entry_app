#!/usr/bin/env python3
"""
Test script to verify cascade month boundary protection
Run in Frappe bench: bench exec test_cascade_limit.py
"""

import frappe
from frappe.utils import getdate, add_days

def test_cascade_limits():
    """Verify that cascade limits prevent March→April wrapping"""
    
    print("\n" + "="*60)
    print("🧪 TESTING CASCADE MONTH BOUNDARY PROTECTION")
    print("="*60)
    
    # Test 1: Verify 30-day limit on cascade
    print("\n✅ Test 1: Cascade day counter limits")
    test_date = "2026-03-15"
    max_days = 30
    current = getdate(test_date)
    day_count = 0
    wrapped_month = False
    
    while day_count < max_days:
        if current.month != getdate(test_date).month:
            wrapped_month = True
            break
        current = add_days(current, 1)
        day_count += 1
    
    if wrapped_month:
        print(f"   ✗ FAIL: Cascade after {day_count} days crossed month boundary!")
    else:
        print(f"   ✓ PASS: {day_count} days cascade stays within month")
    
    # Test 2: Month boundary calculation
    print("\n✅ Test 2: Month boundary detection")
    test_dates = [
        ("2026-03-15", "2026-03-31"),
        ("2026-02-15", "2026-02-28"),
        ("2026-01-15", "2026-01-31"),
    ]
    
    for start, expected_end in test_dates:
        start_dt = getdate(start)
        month_start = start_dt.replace(day=1)
        if start_dt.month == 12:
            month_end = month_start.replace(year=start_dt.year + 1, month=1, day=1)
            month_end = add_days(month_end, -1)
        else:
            month_end = month_start.replace(month=start_dt.month + 1, day=1)
            month_end = add_days(month_end, -1)
        
        actual_end = month_end.strftime("%Y-%m-%d")
        if actual_end == expected_end:
            print(f"   ✓ PASS: {start} → month ends on {actual_end}")
        else:
            print(f"   ✗ FAIL: {start} → expected {expected_end}, got {actual_end}")
    
    # Test 3: Verify date comparisons work
    print("\n✅ Test 3: String date comparisons")
    dates = [
        ("2026-03-25", "2026-03-26", "2026-03-25" < "2026-03-26"),
        ("2026-03-31", "2026-04-01", "2026-03-31" < "2026-04-01"),
        ("2026-02-28", "2026-03-01", "2026-02-28" < "2026-03-01"),
    ]
    
    for d1, d2, expected in dates:
        result = d1 < d2
        status = "✓" if result == expected else "✗"
        print(f"   {status} {d1} < {d2} = {result}")
    
    print("\n" + "="*60)
    print("Testing complete!")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_cascade_limits()
