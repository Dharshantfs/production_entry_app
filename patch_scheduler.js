const fs = require('fs');

const filePath = 'c:\\Users\\Admin\\both app\\PRODUCTION ENTRY\\public\\js\\ProductionScheduler.vue';
let content = fs.readFileSync(filePath, 'utf8');

content = content.replace(
    /isLaminationBoard\.value = Boolean\(r && r\[0\] === "lamination-board"\);/g,
    'isLaminationBoard.value = Boolean(r && r[0] && r[0].toLowerCase().replace(/-/g, " ") === "lamination board");'
);

content = content.replace(
    /frappe\.set_route\("lamination-order-table", query\);/g,
    'frappe.set_route("Lamination Order Table", query);'
);

content = content.replace(
    /frappe\.set_route\("production-table", query\);/g,
    'frappe.set_route("Production Table", query);'
);

fs.writeFileSync(filePath, content, 'utf8');
console.log("Patched ProductionScheduler.vue");
