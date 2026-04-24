import os
import re

def migrate_api_py():
    path = "production_scheduler/api.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Table name replacements
    content = content.replace("tabPlanning Sheet Item", "tabPlanning Table")
    content = content.replace('"Planning Sheet Item"', '"Planning Table"')
    content = content.replace("'Planning Sheet Item'", "'Planning Table'")

    # 2. Column fieldname replacements (Specific to item fields)
    content = content.replace("custom_item_planned_date", "planned_date")
    content = content.replace("custom_is_split", "is_split")
    content = content.replace("custom_split_from", "split_from")
    # custom_plan_code to plan_name. Be careful not to replace completely unrelated vars, but this is highly specific
    content = content.replace("custom_plan_code", "plan_name")
    
    # 3. Replace the population logic in _populate_planning_sheet_items
    old_pop = '''        if is_existing:
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
                    break # Stop after appending to the first matched field'''
                    
    new_pop_str = '''        target_field = None
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
                ps.append(target_field, pt_data)'''
    
    # Replace in file if exists, fall back to regex if exact match fails
    if old_pop in content:
        content = content.replace(old_pop, new_pop_str)
    
    # Wait, existing_items_map was populated from ps.items. Need to update that.
    old_map = 'existing_items_map = {it.sales_order_item: it for it in ps.items}'
    new_map = '''    target_field = "planned_items"
    for field in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
        if hasattr(ps, field) or ps.meta.has_field(field):
            target_field = field
            break
    existing_items_map = {it.sales_order_item: it for it in getattr(ps, target_field, ps.get("items", []))}'''
    
    if old_map in content:
        content = content.replace(old_map, new_map)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("Migrated api.py successfully.")

if __name__ == "__main__":
    migrate_api_py()
