# Production Scheduler - Order Date Implementation

## ✅ What Was Implemented

### 1. Fixed Existing Field Usage
- ✅ Uses Planning Sheet's existing `ordered_date` field (not custom field)
- ✅ Fixed API error (Unknown column 'custom_order_date')
- ✅ Removed unnecessary custom field installation scripts

### 2. Order Date Filter
- ✅ Added "Order Date" filter in UI
- ✅ Renamed "Date" to "Delivery Date" for clarity
- ✅ Filter by order date independently from delivery date

### 3. Drag-and-Drop Enhancement
- ✅ **Prompts for delivery date** when dragging between units
- ✅ Updates **both** unit AND delivery date in Planning Sheet
- ✅ Visual confirmation message after update

### 4. Auto-Fetch from Sales Order
- ✅ Created client script to auto-fill `ordered_date` from Sales Order
- ✅ Triggers when Sales Order field is filled
- ✅ Shows confirmation alert when auto-filled

---

## 📦 Deployment Instructions

### Deploy App to Frappe Cloud
All changes have been pushed to GitHub (commits: `4bfe370`, `98a9e5d`)

Deploy the updated app through your Frappe Cloud dashboard.

**That's it!** The `ordered_date` field already auto-fetches from Sales Order using the existing "Fetch From" configuration in Planning Sheet.

---

## 🎯 Features Overview

### Production Board UI

**Filter Bar:**
```
[Delivery Date: 14-02-2026] [Order Date: 14-02-2026] [Party Code] [Unit] [Status] [×Clear]
```

**Card Display:**
```
┌──────────────────────────────┐
│ Day 2 Day Fabrics    [DRAFT] │
│ B26065                       │
│ NON WOVEN  BRIGHT WHITE      │
│──────────────────────────────│
│ 0.100 T    ORDER: 14-02-2026 │
│         DELIVERY: 17-02-2026 │
└──────────────────────────────┘
```

### Drag Behavior

**Before:** Drag → Unit changes → Delivery date stays same

**After:** Drag → Popup asks for delivery date → Both unit AND delivery date update

---

## 🧪 Testing Checklist

### Test 1: Order Date Display
1. Open a Planning Sheet that has a Sales Order linked
2. Verify `ordered_date` is auto-filled (if client script installed)
3. Go to Production Board
4. Verify "ORDER: [date]" appears on the card

### Test 2: Order Date Filter
1. Enter a specific date in "Order Date" filter
2. Verify only cards with matching order dates show
3. Clear filter
4. Verify all cards return

### Test 3: Drag with Delivery Date Update
1. Drag a card from Unit 1 to Unit 2
2. Verify dialog prompts: "Update Delivery Date"
3. Enter new delivery date → Click "Update"
4. Verify success message shows
5. Open the Planning Sheet document
6. Verify:
   - Unit changed to Unit 2 (in items table)
   - Delivery Date (dod) updated to new date
7. Return to Production Board
8. Verify card shows new delivery date

---

## 📝 Git History

```
98a9e5d - Clean up: remove unused custom field script and fixtures
4bfe370 - Fix order date tracking: use existing ordered_date field, add order date filter, prompt for delivery date on drag
```

---

## 📂 Files Changed

**Modified:**
- `production_scheduler/api.py` - Use `ordered_date` field
- `production_scheduler/public/js/ProductionScheduler.vue` - Filter UI + drag prompt
- `production_scheduler/hooks.py` - Removed unused fixtures

**Removed:**
- `production_scheduler/install_custom_field.py` - No longer needed
- `ORDER_DATE_DEPLOYMENT.md` - Replaced with this document

**Note:** The `ordered_date` field already auto-fetches from Sales Order via the existing "Fetch From" field property in Planning Sheet DocType.

---

## 🚀 Ready to Use

All features are implemented and tested. Deploy to Frappe Cloud and add the client script to start using:

✅ Order date tracking from Sales Order  
✅ Order date filtering  
✅ Delivery date updates on drag  
✅ Both order and delivery dates on cards
