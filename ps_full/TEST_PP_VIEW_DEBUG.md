# Debug Instructions: PP View Button Issue

## Problem
When clicking "View" on Production Table, the wrong Production Plan is shown even though item-level PP exists.

## Root Cause Checklist
The fix deployed adds console logging. Follow these steps:

### 1. Hard Refresh Browser
```
Ctrl + Shift + R  (Windows)
Cmd + Shift + R   (Mac)
```

### 2. Open Browser Console  
```
F12 → Console Tab
```

### 3. Click "View" Button on Any Production Table Row
Look for console output showing:
```javascript
openProductionPlanView called: {
  directPpId: "MFG-PP-2026-00263",    ← Should show item-level PP
  ppIdAfterTrim: "MFG-PP-2026-00263", ← Should NOT be empty
  ppIdExists: true,                    ← Should be TRUE
  ppIdToUse: "MFG-PP-2026-00263"
}
```

### 4. Interpret Results

**Case A: ppIdExists = true, directPpId matches expected item PP**
✅ Item-level PP is being passed correctly  
→ All data looks good on frontend  
→ Issue might be browser cache or UI refresh

**Case B: ppIdExists = false, directPpId = null/empty**
⚠️ Item-level PP is NOT populating in table data  
→ Backend `get_color_chart_data` is not returning `pp_id`  
→ Need to verify Planning Sheet Item has item-level PP link

**Case C: ppIdExists = true, but directPpId shows WRONG PP**
🛑 Table is showing wrong item-level assignment  
→ Item Master data issue  
→ Planning Sheet Item is linked to wrong PP

### 5. What to Share
If issue persists, provide:
1. Console logs (copy-paste the console output)
2. Order Code / Color / Quality of the row you clicked
3. Expected PP ID
4. Actual PP ID shown after clicking View

---
## Quick Action
**Right now, please:**
1. Hard refresh (Ctrl+Shift+R)
2. Click View on the same BRIGHT WHITE item
3. Check console - what does it say?
4. Does the correct PP now open?

