const fs = require('fs');
const path = require('path');

const searchDir = 'c:\\Users\\Admin\\both app\\PRODUCTION ENTRY';
let filesToPatch = [];

function walkDir(dir) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
        const fullPath = path.join(dir, file);
        if (fs.statSync(fullPath).isDirectory()) {
            walkDir(fullPath);
        } else if (file === 'ProductionScheduler.vue') {
            filesToPatch.push(fullPath);
        }
    }
}

walkDir(searchDir);

for (const fpath of filesToPatch) {
    let content = fs.readFileSync(fpath, 'utf8');
    
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

    fs.writeFileSync(fpath, content, 'utf8');
}
console.log('Patched ' + filesToPatch.length + ' ProductionScheduler.vue files');
