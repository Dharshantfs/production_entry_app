const fs = require('fs');

const path = 'production_scheduler/api.py';
let content = fs.readFileSync(path, 'utf8');

// 1. Table name replacements
content = content.replace(/tabPlanning Sheet Item/g, 'tabPlanning Table');
content = content.replace(/"Planning Sheet Item"/g, '"Planning Table"');
content = content.replace(/'Planning Sheet Item'/g, "'Planning Table'");

// 2. Column fieldname replacements
content = content.replace(/custom_item_planned_date/g, 'planned_date');
content = content.replace(/custom_is_split/g, 'is_split');
content = content.replace(/custom_split_from/g, 'split_from');
content = content.replace(/custom_plan_code/g, 'plan_name');

// 3. Replace the population logic accurately regardless of CRLF or LF
const oldPop = `        if is_existing:
            # UPDATE existing PSI if unit changed (e.g., white order now assigned to a unit)
            old_unit = existing_psi.unit
            if old_unit != unit:
                existing_psi.unit = unit
                existing_psi.planned_date = p_date
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
                    break # Stop after appending to the first matched field`;

const newPop = `        target_field = None
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
            pt_data = psi_data.copy()
            pt_data["planned_date"] = p_date
            pt_data["plan_name"] = ps.get("custom_plan_name")
            if target_field:
                ps.append(target_field, pt_data)`;

// We normalize line endings in both content and search string to ensure match
let normalizedContent = content.replace(/\\r\\n/g, '\\n');
let normalizedOldPop = oldPop.replace(/\\r\\n/g, '\\n');

if (normalizedContent.includes(normalizedOldPop)) {
    normalizedContent = normalizedContent.replace(normalizedOldPop, newPop);
    console.log("Replaced population logic successfully.");
} else {
    console.log("WARNING: Could not perfectly match old population logic.");
}

const oldMap = `existing_items_map = {it.sales_order_item: it for it in ps.items}`;
const newMap = `    target_field = "planned_items"
    for field in ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]:
        if hasattr(ps, field) or ps.meta.has_field(field):
            target_field = field
            break
    existing_items_map = {it.sales_order_item: it for it in getattr(ps, target_field, ps.get("items", []))}`;

if (normalizedContent.includes(oldMap)) {
    normalizedContent = normalizedContent.replace(oldMap, newMap);
    console.log("Replaced dictionary mapping logic successfully.");
} else {
    console.log("WARNING: Could not match map logic.");
}

fs.writeFileSync(path, normalizedContent, 'utf8');
console.log("Migration complete.");
