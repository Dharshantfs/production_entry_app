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
        } else if (file === 'ProductionTable.vue') {
            filesToPatch.push(fullPath);
        }
    }
}

walkDir(searchDir);

for (const fpath of filesToPatch) {
    let content = fs.readFileSync(fpath, 'utf8');
    
    content = content.replace(
        /frappe\.set_route\(isLaminationBoard\.value \? "lamination-board" \: "production-board"\);/g,
        'frappe.set_route(isLaminationBoard.value ? "Lamination Board" : "Production Board");'
    );

    fs.writeFileSync(fpath, content, 'utf8');
}
console.log('Patched ' + filesToPatch.length + ' ProductionTable.vue files');
