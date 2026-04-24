# Order Date Implementation - Deployment Guide

## What Was Changed

This update adds **Order Date** tracking to your Production Scheduler, allowing you to see when orders were received alongside their delivery dates.

### Files Modified

1. **`hooks.py`** - Added fixtures configuration for custom field
2. **`api.py`** - Updated to fetch and return `custom_order_date`
3. **`ProductionScheduler.vue`** - Updated card UI to display both order and delivery dates
4. **`install_custom_field.py`** (NEW) - Script to install the custom field

## Deployment Steps

### Step 1: Install Custom Field

After deploying the updated app to Frappe Cloud, you need to install the custom field. You have two options:

#### Option A: Run Installation Script (Recommended)

```bash
# SSH into your Frappe Cloud instance or run in bench console
bench --site [your-site-name] console
```

Then in the console:
```python
from production_scheduler.install_custom_field import execute
execute()
```

#### Option B: Manual Creation via Frappe UI

1. Go to **Customize Form** in Frappe
2. Select DocType: **Planning sheet**
3. Add a new field:
   - **Field Name**: `custom_order_date`
   - **Label**: Order Date
   - **Field Type**: Date
   - **Insert After**: dod (delivery date)
   - **Description**: Date when the order was received

### Step 2: Add Order Dates to Existing Records

After the field is created, you can:
1. Open any Planning Sheet form
2. Fill in the "Order Date" field
3. Save the form

### Step 3: Verify on Production Board

1. Navigate to **Production Board**
2. Cards will now show:
   - **ORDER:** [date] (if filled)
   - **DELIVERY:** [date]

## What You'll See

**Before:** Cards only showed delivery date
```
Customer Name       [DRAFT]
B26051
─────────────────────────────
0.001 T        2026-02-14
```

**After:** Cards show both dates
```
Customer Name       [DRAFT]
B26051
─────────────────────────────
0.001 T        ORDER: 2026-02-10
               DELIVERY: 2026-02-14
```

## Next Steps (Optional)

- Add order date range filter to the filter bar
- Sort cards by order date (oldest orders first)
- Add visual indicators for old orders (e.g., highlight orders > 7 days old)
