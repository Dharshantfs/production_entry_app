# Clubbing Sheet — App-owned scripts (disable site Client / Server)

The Clubbing Sheet form now loads from the app:

- **Client JS:** `production_entry/public/js/clubbing_sheet.js` (via `hooks.py` → `doctype_js`)
- **Before Submit stamp:** `production_entry.production_planning.clubbing_sheet_hooks.clubbing_sheet_before_submit`
- **APIs:**
  - `production_entry.production_planning.clubbing_api.get_planning_orders_for_clubbing`
  - `production_entry.production_planning.clubbing_api.get_distances_from_madurai`

## What Get Orders returns

- Source: **Planning Table** (board / Planned items) where **Movement Type = Despatch** — **not** Planning Sheet Items
- City: Sales Order → Shipping Address (backend only)
- Optional filter: **Planned Date** (plus Order / Customer / City / Party)
- Each selected row stores `custom_planning_table_row` + `custom_planning_sheet` on Clubbing Sheet Item
- **Despatch Customer** (`custom_despatch_customer`) defaults from Planning/SO customer — editable for emergency reallocation (e.g. ship Gowtham from Dharshan’s plan)
- Optional **Despatch Sales Order** — only if the new customer has their own SO; otherwise leave blank
- On submit: stamps `custom_clubbing_sheet`, loading sequence, **and Despatch Customer** on the **same** Planning Table rows (order-giver plan). Gowtham does **not** need a Planning Sheet — Club ID stays on produced rows; Logistics filters by Club ID

## Despatch Customer → DN (Accounts)

| Step | Who | What |
|------|-----|------|
| Clubbing | Planner | Set Despatch Customer (default = Planning customer; change if needed) |
| Submit Clubbing | System | Stamp Club ID + Despatch Customer on Planning Table |
| Logistics | DN team | Scan by Club ID → Create Draft DN |
| Draft DN | System | `customer` = Despatch Customer; `against_sales_order` **only if** that customer matches Planning SO (or Despatch Sales Order set) |
| Draft DN | Accounts | Button **Accounts → Billing & Address** to change bill-to / shipping / billing address |

Split 500/500 to two customers: use **two Clubbing item rows** (same Order Code OK, different Despatch Customer) → two draft DNs.

## Site steps (after pull + migrate)

1. **Disable** site **Client Script** on DocType `Clubbing Sheet` (the old paste script). ✅
2. **Disable** site **Server Scripts** after app deploy:
   - API: `get_planning_orders_for_clubbing`
   - API: `get_distances_from_madurai`
   - **Before Submit** stamp script (app hook owns this)
   - **Before Save** (optional once app is updated — see below)

   If you must keep a site Before Submit script temporarily, replace its body with
   [`PASTE_clubbing_on_submit_server_script.py`](./PASTE_clubbing_on_submit_server_script.py)
   (uses `frappe.get_meta(...).has_field` — **never** `frappe.db.has_column`, which crashes safe_exec).

3. **Before Save:** App hook is
   `production_entry.production_planning.clubbing_sheet_hooks.clubbing_sheet_before_save`
   (customer fix, total weight, load type, route belt, distances, loading sequence).

   Until that deploy lands, keep the site Before Save Enabled using
   [`PASTE_clubbing_before_save_server_script.py`](./PASTE_clubbing_before_save_server_script.py).
   After deploy + migrate/clear-cache: **Disable** the site Before Save so logic runs once.
4. After cancel of a Clubbing Sheet, Planning stamps clear automatically (`on_cancel`).  
   For already-cancelled sheets that still show on Planning, run in Desk console:

```python
frappe.call(
  "production_entry.production_planning.clubbing_sheet_hooks.clear_planning_stamps_for_club",
  clubbing_sheet="CLB-00029-1"
)
```
4. Run:

```bash
bench --site <site> migrate
bench build --app production_entry
bench --site <site> clear-cache
```

5. Hard-refresh the Clubbing Sheet form (Ctrl+Shift+R).

## Get Orders columns

Dialog shows: **Order | Item | Quality | Color | GSM | Inch | Planned | City | Wt/Rolls**  
(from Planning Table Despatch rows; city from SO shipping address).

## Route belts — how to fetch on route basis

Client already has `ROUTE_BELTS` (Madurai → city chains). Today:

| Step | Behaviour |
| --- | --- |
| Pick orders | Filter by **City** (type a city name, e.g. `Erode`) |
| After pick | Loading sequence sorts by belt / distance |
| Before Save (site) | Route conflict if cities are not on one belt |

**Recommended route fetch (next):**

1. Add filter **Route belt** dropdown built from `ROUTE_BELTS` labels (e.g. “Madurai → Karur → Coimbatore”).
2. On select, expand belt cities → pass as multi-city filter to API (or client-filter `o.city` in belt).
3. Only show Despatch PT rows whose SO city is in that belt.
4. Keep override checkbox **Ignore Route Conflict** for exceptions.

Until that lands: type a **City** in the filter (or one city of the belt) and select matching rows manually.

## Despatch club scan (barcode + camera)

On Logistics Kanban club card:

- **USB / Bluetooth barcode reader:** click the scan box, then scan — reader types batch + Enter → marks `custom_scanned`.
- **Camera:** tap **Camera** (Chrome/Edge + HTTPS + camera permission) → points at barcode → auto-submits.
- Empty Scan click no longer hard-blocks with only “Scan a batch barcode”; it focuses the box and shows a short tip.

## Distance / Google Routes

`get_distances_from_madurai` reads the API key from **JSB Integrations** (`google_api_key` Password field preferred).  
If the key is missing or Google returns **400 invalid**, distances fall back to the hardcoded Madurai map — clubbing still works.

---

## Create a new Google Maps / Routes API key

Use this when Error Log shows `Routes API 400: API key not valid`.

### 1. Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project (e.g. `jsb-erp-routes`)
3. Enable **billing** on the project (Routes API requires it)

### 2. Enable APIs

In **APIs & Services → Library**, enable:

- **Routes API** (required — used by `computeRouteMatrix`)
- Optionally **Maps JavaScript API** / **Geocoding API** if you use maps elsewhere

Do **not** rely on the old Distance Matrix API alone; this app calls:

`https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix`

### 3. Create the key

1. **APIs & Services → Credentials → Create credentials → API key**
2. Copy the key
3. Click **Restrict key**:
   - **Application restrictions:** prefer **IP addresses** of your ERP server (or None while testing)
   - **API restrictions:** select **Routes API** only
4. Save

### 4. Store in ERP (JSB Integrations)

1. Desk → **JSB Integrations** (Single)
2. Set **Google API Key** / `google_api_key` (Password field)
3. Save
4. `bench --site <site> clear-cache`

Optional fallback in `site_config.json`:

```json
{
  "google_maps_api_key": "YOUR_KEY_HERE"
}
```

### 5. Verify

From Desk console or a Server Script test call:

```python
from production_entry.production_planning.clubbing_api import get_distances_from_madurai
print(get_distances_from_madurai(["Erode", "Karaikudi"]))
```

- If Google works: km values from Routes
- If key still invalid: fallback km from Madurai map (check Error Log for `get_distances_from_madurai`)

### Common mistakes

| Issue | Fix |
| --- | --- |
| Key from Maps JS only, Routes not enabled | Enable **Routes API** |
| Billing not enabled | Enable Cloud billing |
| Wrong key pasted / truncated | Re-copy full key into JSB Integrations |
| Key restricted to HTTP referrer only | Use **IP** restriction for server-side calls, or unrestricted while testing |
| Old Distance Matrix key reused | Create a new key with **Routes API** allowed |
