# =============================================================================
# Frappe Server Script — API
# Method name: update_planning_sheet  (set in Server Script record)
#
# Partial Sales Order → Draft Planning Sheet update:
#   - Existing lines: qty / meter / meter_per_roll / no_of_rolls on FG rows only
#   - New lines (e.g. another 108): populate + full BOM post-sync via production_entry
#
# Requires on site (production_entry app):
#   production_entry.production_planning.scheduler_api.update_planning_sheet_from_sales_order
#
# Do NOT use regenerate_planning_sheet or sync_bom_children from this button — they wipe tables.
# No import lines. No frappe.get_attr (blocked in safe_exec). Use frappe.call only.
# =============================================================================

try:
    sales_order = (frappe.form_dict.get("sales_order") or frappe.form_dict.get("so_name") or "").strip()

    if not sales_order:
        frappe.response["message"] = {
            "success": False,
            "message": "Sales Order not provided",
        }
    else:
        result = frappe.call(
            "production_entry.production_planning.scheduler_api.update_planning_sheet_from_sales_order",
            sales_order=sales_order,
        )

        ok = True
        msg = "Planning Sheet updated"
        ps_name = ""
        had_new = False
        fg_updates = 0

        if result and isinstance(result, dict):
            ok = bool(result.get("ok", True))
            msg = result.get("message") or msg
            ps_name = result.get("planning_sheet") or ""
            had_new = bool(result.get("had_new_lines", False))
            fg_updates = int(result.get("fg_field_updates") or 0)
        elif result:
            msg = str(result)

        frappe.response["message"] = {
            "success": ok,
            "message": msg,
            "planning_sheet": ps_name,
            "had_new_lines": had_new,
            "fg_field_updates": fg_updates,
        }

except Exception as e:
    err = str(e)
    try:
        frappe.log_error("update_planning_sheet: " + err, "update_planning_sheet")
    except Exception:
        pass
    frappe.response["message"] = {
        "success": False,
        "message": "Error: " + err,
    }
