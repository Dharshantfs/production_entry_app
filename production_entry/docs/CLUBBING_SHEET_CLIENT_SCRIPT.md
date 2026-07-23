# Clubbing Sheet — Client Script (legacy paste)

> **Prefer the app file.** After deploy, use `public/js/clubbing_sheet.js` via hooks and **disable** the site Client Script.
>
> Full setup + Google Maps key guide: [CLUBBING_SHEET_APP_SETUP.md](./CLUBBING_SHEET_APP_SETUP.md)

**DocType:** Clubbing Sheet  

**Disable on site:**
- Client Script on Clubbing Sheet
- Server Script APIs `get_planning_orders_for_clubbing` / `get_distances_from_madurai`
- Before Submit stamp Server Script (replaced by `clubbing_sheet_hooks`)

App methods:
- `production_entry.production_planning.clubbing_api.get_planning_orders_for_clubbing`
- `production_entry.production_planning.clubbing_api.get_distances_from_madurai`

Source of truth for JS: `production_entry/public/js/clubbing_sheet.js`
