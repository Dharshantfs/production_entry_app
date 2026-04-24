# 🚨 CRITICAL FIX: Infinite Cascade Bug (March → April Wrap-around)

## Problem Statement
**ALL items from March, January, and February were being pushed to April regardless of selected date.**

### Root Cause
The cascade while loop in `push_items_to_pb()` had **NO BREAKING CONDITION**:
```python
while True:  # ← INFINITE LOOP!
    if capacity_full:
        add_days(current_date, 1)
    else:
        break
```

**What was happening:**
1. User selects March items
2. Pushes to Production Board
3. System checks capacity on March 15
4. If FULL, it adds 1 day → March 16
5. If still FULL, adds 1 day → March 17
6. ...continues for entire month...
7. March 31 + 1 day = April 1 ✗ **ITEMS WRAP TO APRIL**
8. Loop never stops because it finds empty capacity in April

---

## Solution Deployed (Commit: `23f533d`)

### Change 1: Add 30-Day Cascade Window Limit
```python
max_cascade_days = 30  # Maximum cascade window
while cascade_days < max_cascade_days:
    # ... check capacity, add days, increment cascade_days ...
    
if cascade_days >= max_cascade_days:
    # Item rejected - can't fit within 30 days
```

### Change 2: Month Boundary Detection (Strict Mode)
When user does NOT confirm cascade:
```python
strict_keep_date = cint(strict_target_date)  # Should be 1 (true)
if strict_keep_date:  # Don't cascade
    # Calculate month end date
    month_end = calculate_month_end(target_date)
    
    # Check: would next day exceed month boundary?
    if next_day > month_end:
        # Skip item with warning
        continue
```

### Change 3: Item-Level Skip Handling
```python
# If effective_date is None (item couldn't be placed), skip it
if not effective_date:
    continue  # ← Don't try to push broken items
```

---

## How It Works Now

### STRICT MODE (Most Items - Default)
**When:** User clicks push without confirming cascade  
**Sends:** `strict_target_date: 1`

**Behavior:**
- ✅ Items push to exact target date
- ✅ If maintenance on target: cascade only within same month
- ✅ If can't fit in month: item SKIPPED (not pushed)
- ✅ NO wrap-around to next month

### FLEX MODE (User Explicitly Confirms)
**When:** User sees "Capacity full" dialog and clicks "YES, cascade"  
**Sends:** `strict_target_date: 0`

**Behavior:**
- ✅ Items cascade up to 30 days max
- ✅ Can cross month boundaries (April if needed, but only if user approved)
- ✅ Limited window prevents infinite cascading

---

## Deployment Steps

### 1. Pull Latest Code
```bash
cd /path/to/production_scheduler
git pull
# You should have commit 23f533d
git log --oneline -1
```

### 2. Deploy in Bench
```bash
# Terminal 1: Clear cache and restart
bench clear-cache
bench restart

# Terminal 2: Run migrations if needed
bench migrate
```

### 3. Verify Fix
In browser, go to Color Chart:
1. Select items from **March**
2. Click "Push to Production Board"
3. **WITHOUT confirming cascade dialog**, push should:
   - ✅ Push items to March (selected date)
   - ✅ NOT appear in April
   - ✅ Show orange warning if can't fit: "Cannot fit in March. Month boundary reached."

---

## Testing Cascade Limit

Run diagnostic script (in Frappe bench):
```bash
bench exec test_cascade_limit.py
```

This verifies:
- ✅ 30-day limit prevents infinite loops
- ✅ Month boundary calculations are correct
- ✅ Date string comparisons work properly

---

## Production Qty Still Showing 0?

That's a separate issue. Use the diagnostic API to check:
```javascript
// In browser console
frappe.call('production_scheduler.api.debug_production_qty_mapping', {
    'planning_sheet': 'PS-0001',
    'item_name': 'PSI-xxxxxx'
}, r => console.log(r.message))
```

This shows:
- Is Production Plan linked?
- Are Work Orders found?
- What are their produced_qty values?

---

## Commits Involved
- `23f533d` - 🚨 CRITICAL FIX: Infinite cascade limit + month boundaries
- `3c8bce7` - Fix cascading confirmation requirement
- `12c721e` - Add diagnostic API
- `67976ce` - Target Unit field + month boundary attempt

---

## Emergency Rollback
If issues arise:
```bash
git checkout 52a057a  # Last known good commit
bench clear-cache
bench restart
```

---

**Status:** ✅ DEPLOYED  
**Date:** 2026-03-26  
**Critical:** YES - Prevents data corruption (items in wrong month)
