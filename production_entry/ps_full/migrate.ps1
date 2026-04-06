$path = "production_scheduler/api.py"
$content = Get-Content -Path $path -Raw

# 1. Table name replacements
$content = $content.Replace("tabPlanning Sheet Item", "tabPlanning Table")
$content = $content.Replace('"Planning Sheet Item"', '"Planning Table"')
$content = $content.Replace("'Planning Sheet Item'", "'Planning Table'")

# 2. Column fieldname replacements
$content = $content.Replace("custom_item_planned_date", "planned_date")
$content = $content.Replace("custom_is_split", "is_split")
$content = $content.Replace("custom_split_from", "split_from")
$content = $content.Replace("custom_plan_code", "plan_name")

# 3. Replace the population logic
$old_pop = @"
        if is_existing:
            # UPDATE existing PSI if unit changed (e.g., white order now assigned to a unit)
            old_unit = existing_psi.unit
            if old_unit != unit:
                existing_psi.unit = unit
                existing_psi.custom_item_planned_date = p_date
        else:
            # CREATE new PSI record
            ps.append("items", psi_data)
            
            # DUPLICATE into the new 'Planning Table' child doctype
            pt_data = psi_data.copy()
            # Map the planned date to the correct fieldname in the new table
            pt_data["planned_date"] = p_date
            
            # Check for various common fieldnames you may have given this child table in the UI
            target_fields = ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]
            for field in target_fields:
                if hasattr(ps, field) or ps.meta.has_field(field):
                    ps.append(field, pt_data)
                    break # Stop after appending to the first matched field
"@

$new_pop_str = @"
        target_field = None
        for field in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table", "items"]:
            if hasattr(ps, field) or ps.meta.has_field(field):
                target_field = field
                break
                
        if is_existing:
            old_unit = existing_psi.unit
            if old_unit != unit:
                existing_psi.unit = unit
                existing_psi.planned_date = p_date
        else:
            # Map the planned date and plan name to the correct fieldname in the new table
            pt_data = psi_data.copy()
            pt_data["planned_date"] = p_date
            pt_data["plan_name"] = ps.get("custom_plan_name")
            if target_field:
                ps.append(target_field, pt_data)
"@

if ($content.Contains($old_pop)) {
    $content = $content.Replace($old_pop, $new_pop_str)
} else {
    Write-Host "Warning: Old population logic not found exactly"
}

$old_map = "existing_items_map = {it.sales_order_item: it for it in ps.items}"
$new_map = @"
    target_field = "planned_items"
    for field in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
        if hasattr(ps, field) or ps.meta.has_field(field):
            target_field = field
            break
    existing_items_map = {it.sales_order_item: it for it in getattr(ps, target_field, ps.get("items", []))}
"@

if ($content.Contains($old_map)) {
    $content = $content.Replace($old_map, $new_map)
}

[IO.File]::WriteAllText((Resolve-Path $path).Path, $content, (New-Object System.Text.UTF8Encoding($False)))
Write-Host "Migrated api.py successfully."
