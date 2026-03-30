# Roll Production Entry - Antigravity IDE Prompt

## Context
I am building a custom Frappe app called `production_entry` for a Non-Woven Fabric Manufacturing company. The app is already installed in ERPNext with these existing doctypes:
- Shaft Production Run (custom)
- Roll Production Entry (custom - already exists, needs modification)
- Production Plan (ERPNext built-in)
- Work Order (ERPNext built-in)

---

## What I Need

### 1. Modify: `Shaft Production Run` doctype
Add a custom button **"Create Roll Production Entry"** that:
- Only shows when document is Submitted (docstatus = 1)
- Calls server method to fetch all jobs + WOs from linked Production Plan
- If Roll Production Entry already exists for this SPR → open it directly
- If not → create new Roll Production Entry pre-filled with all job data

### 2. Modify: `Roll Production Entry` doctype
Add these fields if not present:
- `shaft_production_run` (Link → Shaft Production Run)
- `production_plan` (Link → Production Plan)
- `manufacturing_entries` (Small Text, read-only)

Child table `Roll Production Entry Item` needs these fields:
- `job_no` (Data)
- `shaft_combination` (Data)
- `planned_qty` (Float)
- `wo_id` (Link → Work Order)
- `item_code` (Link → Item)
- `item_name` (Data, read-only)
- `batch_no` (Link → Batch)
- `roll_no` (Data) ← manual entry
- `gsm` (Int, read-only)
- `width_inches` (Float, read-only)
- `meter_per_roll` (Float) ← manual entry
- `net_weight` (Float, auto-calculated)
- `gross_weight` (Float) ← manual entry
- `order_code` (Data, read-only)

---

## Business Logic

### Item Code Format (16 characters)
Example: `1001091010801065`
- Positions 0-2: Process code (100)
- Positions 3-5: Quality code (109)
- Positions 6-8: Color code (101)
- Positions 9-11: GSM (080 = 80 GSM)
- Positions 12-15: Width in mm (1065 → divide by 25.4 → 41.9 inches)

### Net Weight Formula
`net_weight (kg) = GSM × (width_inches × 0.0254) × meter_per_roll / 1000`

### Shaft Combination Logic
- 46+46+26 means 3 rolls per machine run
- 46+46 = SAME product (same item code, same WO) → 2 rows, 1 WO
- 26 = different product (different item code, different WO) → 1 row, 1 WO
- Total = 2 WOs for job 46+46+26

### Production Plan → Job → WO Linking
- SPR name contains PP reference (e.g. SPR-PP-2024-0001)
- Each job in PP has shaft combination and planned total weight
- Each WO has `production_plan` and `production_plan_item` fields linking back

### On Submit of Roll Production Entry
1. Group all rows by `wo_id`
2. For each WO group → create one `Stock Entry` (type: Manufacture)
3. Each roll = one FG item row in Stock Entry with batch_no and roll_no
4. After creating Stock Entry → check if WO produced_qty >= planned qty → mark WO as Completed
5. Store all created Stock Entry names in `manufacturing_entries` field

### On Cancel of Roll Production Entry
- Cancel all linked Stock Entries

---

## Files to Create/Modify

### `shaft_production_run.js`
- Add "Create Roll Production Entry" button
- Call `get_or_create_roll_entry` server method
- If existing → frappe.set_route to open it
- If new → frappe.new_doc with pre-filled items

### `shaft_production_run.py`
- `@frappe.whitelist()` method `get_or_create_roll_entry(shaft_production_run)`
- Check existing Roll Production Entry for this SPR
- Get PP from SPR (via field or by stripping 'SPR-' prefix)
- Loop all jobs in SPR → get shaft combination from PP child table
- Get all WOs per job via `production_plan` + `production_plan_item`
- Parse item code for GSM and width
- Return flat list of pre-filled item rows with job_no included

### `roll_production_entry.js`
- On refresh: render colored job section headers above grid (grouped by job_no)
- Auto-calculate net_weight when meter_per_roll, gsm, or width_inches changes
- Show totals: total rolls, total net weight, total gross weight

### `roll_production_entry.py`
- Class `RollProductionEntry`
- `validate()`: calculate weights, check mandatory fields (roll_no, meter_per_roll)
- `on_submit()`: create manufacturing entries, update WO statuses
- `on_cancel()`: cancel linked stock entries

---

## Important Notes
- Do NOT hardcode job counts or WO counts
- All counts must be dynamic from actual PP data
- Batch numbers are already auto-created by existing script (do not change batch logic)
- GSM and width_inches are read-only (parsed from item code)
- Roll No and Meter/Roll are the only manual inputs per row
- Net weight auto-calculates, Gross weight is manual
