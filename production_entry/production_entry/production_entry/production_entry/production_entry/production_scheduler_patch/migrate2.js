const fs = require('fs');

const path = 'production_scheduler/api.py';
let content = fs.readFileSync(path, 'utf8');

const regex = /        else:\r?\n            # CREATE new PSI record[\s\S]*?break # Stop after appending to the first matched field/;

const newPop = `        else:
            pt_data = psi_data.copy()
            pt_data["planned_date"] = p_date
            pt_data["plan_name"] = ps.get("custom_plan_name")
            
            target_fields = ["planned_items", "custom_planned_items", "planning_table", "custom_planning_table", "table"]
            for field in target_fields:
                if hasattr(ps, field) or ps.meta.has_field(field):
                    ps.append(field, pt_data)
                    break `;

if (regex.test(content)) {
    content = content.replace(regex, newPop);
    console.log("Replaced population logic successfully.");
} else {
    console.log("Regex still failed to match.");
}

fs.writeFileSync(path, content, 'utf8');
