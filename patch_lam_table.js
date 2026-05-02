const fs = require('fs');
const path = require('path');

const searchDir = path.join(__dirname, 'production_entry');
let filesToPatch = [];

function walkDir(dir) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
        const fullPath = path.join(dir, file);
        if (fs.statSync(fullPath).isDirectory()) {
            walkDir(fullPath);
        } else if (file === 'LaminationOrderTable.vue') {
            filesToPatch.push(fullPath);
        }
    }
}

walkDir(searchDir);

const templateSearch = '<tr\\s+v-for="\\(row, idx\\) in filteredRows"\\s+:key="row.itemName \\|\\| idx"';
const templateReplace = '<template v-for="(row, idx) in displayRows" :key="row.dateKey + (row.is_maintenance_row ? \'-maint\' : (row.is_maintenance_empty ? \'-empty\' : (\'-item-\' + (row.itemName || idx))))">\n' +
'            <tr v-if="row.is_maintenance_row" class="pt-non-draggable" style="background-color: #fee2e2; border: 2px solid #dc2626;">\n' +
'              <td colspan="16" style="padding: 8px 12px; font-weight: 700; color: #991b1b; text-align: center;">\n' +
'                <div style="display: inline-flex; align-items: center; justify-content: center; gap: 10px; flex-wrap: wrap;">\n' +
'                  <span>?? MAINTENANCE: {{ row.record.maintenance_type }} ({{ row.record.start_date }} - {{ row.record.end_date }})</span>\n' +
'                  <button @click="deleteMaintenanceRecord(row.record.name)" style="background: #dc2626; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 11px;">Remove</button>\n' +
'                </div>\n' +
'              </td>\n' +
'            </tr>\n' +
'            <tr v-else-if="row.is_maintenance_empty">\n' +
'              <td class="cell-center">-</td>\n' +
'              <td class="cell-center">\n' +
'                <span v-if="!arrangementUnlocked" class="cc-lock-hint">Locked</span>\n' +
'              </td>\n' +
'              <td class="cell-center font-bold">{{ formatDate(row.dateKey) }}</td>\n' +
'              <td colspan="13" style="text-align:center; color:#94a3b8; font-style:italic;">No lamination orders (maintenance day)</td>\n' +
'            </tr>\n' +
'            <tr v-else';

const idxSearch = '<td class="cell-center">\\{\\{ idx \\+ 1 \\}\\}\\<\\/td>\\s*<td class="cell-center">\\s*<span v-if="arrangementUnlocked" class="cc-drag-handle"';
const idxReplace = '<td class="cell-center">{{ row._sno }}</td>\n' +
'            <td class="cell-center">\n' +
'              <span v-if="arrangementUnlocked" class="cc-drag-handle"';

const emptySearch = '<tr v-if="!filteredRows\\.length">';
const emptyReplace = '</template>\n' +
'          <tr v-if="!displayRows.length">';

const funcSearch = 'function getRowDateKey\\(row\\) \\{';
const funcReplace = 'const displayRows = computed(() => {\n' +
'  const normalRows = filteredRows.value || [];\n' +
'  const { start_date, end_date } = getScopeDateRange();\n' +
'  if (!start_date || !end_date) {\n' +
'    normalRows.forEach((r, i) => { r._sno = i + 1; });\n' +
'    return normalRows;\n' +
'  }\n' +
'  \n' +
'  const start = new Date(start_date);\n' +
'  const end = new Date(end_date);\n' +
'  const out = [];\n' +
'  \n' +
'  let sno = 1;\n' +
'  const datesHandled = new Set();\n' +
'  const renderedMaintRecords = new Set();\n' +
'  \n' +
'  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {\n' +
'    const k = toDateKey(d);\n' +
'    datesHandled.add(k);\n' +
'    \n' +
'    const recs = (maintenanceRecords.value || []).filter(r => {\n' +
'      const rStart = new Date(r.start_date);\n' +
'      const rEnd = new Date(r.end_date);\n' +
'      return d >= rStart && d <= rEnd;\n' +
'    });\n' +
'    \n' +
'    let hasMaintToday = false;\n' +
'    if (recs && recs.length > 0) {\n' +
'      hasMaintToday = true;\n' +
'      for (const rec of recs) {\n' +
'        if (!renderedMaintRecords.has(rec.name)) {\n' +
'          out.push({\n' +
'            is_maintenance_row: true,\n' +
'            dateKey: k,\n' +
'            record: rec\n' +
'          });\n' +
'          renderedMaintRecords.add(rec.name);\n' +
'        }\n' +
'      }\n' +
'    }\n' +
'    \n' +
'    const dateRows = normalRows.filter(r => getRowDateKey(r) === k);\n' +
'    for (const r of dateRows) {\n' +
'      r._sno = sno++;\n' +
'      out.push(r);\n' +
'    }\n' +
'    \n' +
'    if (hasMaintToday && dateRows.length === 0) {\n' +
'      out.push({\n' +
'        is_maintenance_empty: true,\n' +
'        dateKey: k\n' +
'      });\n' +
'    }\n' +
'  }\n' +
'  \n' +
'  const unhandled = normalRows.filter(r => !datesHandled.has(getRowDateKey(r)));\n' +
'  for (const r of unhandled) {\n' +
'    r._sno = sno++;\n' +
'    out.push(r);\n' +
'  }\n' +
'  \n' +
'  return out;\n' +
'});\n' +
'\n' +
'async function deleteMaintenanceRecord(recordName) {\n' +
'  if (!confirm("Remove this maintenance record?")) return;\n' +
'  try {\n' +
'    const res = await frappe.call({\n' +
'      method: "production_scheduler.api.delete_maintenance_and_cascade",\n' +
'      args: { maintenance_record_name: recordName }\n' +
'    });\n' +
'    if (res.message && res.message.status === "success") {\n' +
'      frappe.show_alert({ message: res.message.message, indicator: "green" });\n' +
'      await fetchMaintenanceRecords();\n' +
'      if (typeof fetchData === "function") await fetchData();\n' +
'    } else if (res.message && res.message.status === "error") {\n' +
'      frappe.msgprint(res.message.message || "Error deleting maintenance record");\n' +
'    }\n' +
'  } catch (e) {\n' +
'    frappe.msgprint("Error deleting maintenance record");\n' +
'    console.error(e);\n' +
'  }\n' +
'}\n' +
'\n' +
'function getRowDateKey(row) {';

for (const fpath of filesToPatch) {
    let content = fs.readFileSync(fpath, 'utf8');
    if (!content.includes('displayRows = computed(')) {
        content = content.replace(new RegExp(templateSearch), templateReplace);
        content = content.replace(new RegExp(idxSearch), idxReplace);
        content = content.replace(new RegExp(emptySearch), emptyReplace);
        content = content.replace(new RegExp(funcSearch), funcReplace);
        fs.writeFileSync(fpath, content, 'utf8');
    }
}
console.log('Patched ' + filesToPatch.length + ' files');
