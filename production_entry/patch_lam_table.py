import os
import re

search_dir = r"c:\Users\Admin\both app\PRODUCTION ENTRY"
files_to_patch = []

for root, dirs, files in os.walk(search_dir):
    for f in files:
        if f == "LaminationOrderTable.vue":
            files_to_patch.append(os.path.join(root, f))

template_search = r'<tr\s+v-for="\(row, idx\) in filteredRows"\s+:key="row.itemName \|\| idx"'
template_replace = r'''<template v-for="(row, idx) in displayRows" :key="row.dateKey + (row.is_maintenance_row ? '-maint' : (row.is_maintenance_empty ? '-empty' : ('-item-' + (row.itemName || idx))))">
            <tr v-if="row.is_maintenance_row" class="pt-non-draggable" style="background-color: #fee2e2; border: 2px solid #dc2626;">
              <td colspan="16" style="padding: 8px 12px; font-weight: 700; color: #991b1b; text-align: center;">
                <div style="display: inline-flex; align-items: center; justify-content: center; gap: 10px; flex-wrap: wrap;">
                  <span>?? MAINTENANCE: {{ row.record.maintenance_type }} ({{ row.record.start_date }} - {{ row.record.end_date }})</span>
                  <button @click="deleteMaintenanceRecord(row.record.name)" style="background: #dc2626; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 11px;">Remove</button>
                </div>
              </td>
            </tr>
            <tr v-else-if="row.is_maintenance_empty">
              <td class="cell-center">-</td>
              <td class="cell-center">
                <span v-if="!arrangementUnlocked" class="cc-lock-hint">Locked</span>
              </td>
              <td class="cell-center font-bold">{{ formatDate(row.dateKey) }}</td>
              <td colspan="13" style="text-align:center; color:#94a3b8; font-style:italic;">No lamination orders (maintenance day)</td>
            </tr>
            <tr v-else'''

idx_search = r'<td class="cell-center">\{\{ idx \+ 1 \}\}<\/td>\s*<td class="cell-center">\s*<span v-if="arrangementUnlocked" class="cc-drag-handle"'
idx_replace = r'''<td class="cell-center">{{ row._sno }}</td>
            <td class="cell-center">
              <span v-if="arrangementUnlocked" class="cc-drag-handle"'''

empty_search = r'<tr v-if="!filteredRows\.length">'
empty_replace = r'''</template>
          <tr v-if="!displayRows.length">'''

func_search = r'function getRowDateKey\(row\) \{'
func_replace = r'''const displayRows = computed(() => {
  const normalRows = filteredRows.value || [];
  const { start_date, end_date } = getScopeDateRange();
  if (!start_date || !end_date) {
    normalRows.forEach((r, i) => { r._sno = i + 1; });
    return normalRows;
  }
  
  const start = new Date(start_date);
  const end = new Date(end_date);
  const out = [];
  
  let sno = 1;
  const datesHandled = new Set();
  const renderedMaintRecords = new Set();
  
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const k = toDateKey(d);
    datesHandled.add(k);
    
    const recs = (maintenanceRecords.value || []).filter(r => {
      const rStart = new Date(r.start_date);
      const rEnd = new Date(r.end_date);
      return d >= rStart && d <= rEnd;
    });
    
    let hasMaintToday = false;
    if (recs && recs.length > 0) {
      hasMaintToday = true;
      for (const rec of recs) {
        if (!renderedMaintRecords.has(rec.name)) {
          out.push({
            is_maintenance_row: true,
            dateKey: k,
            record: rec
          });
          renderedMaintRecords.add(rec.name);
        }
      }
    }
    
    const dateRows = normalRows.filter(r => getRowDateKey(r) === k);
    for (const r of dateRows) {
      r._sno = sno++;
      out.push(r);
    }
    
    if (hasMaintToday && dateRows.length === 0) {
      out.push({
        is_maintenance_empty: true,
        dateKey: k
      });
    }
  }
  
  const unhandled = normalRows.filter(r => !datesHandled.has(getRowDateKey(r)));
  for (const r of unhandled) {
    r._sno = sno++;
    out.push(r);
  }
  
  return out;
});

async function deleteMaintenanceRecord(recordName) {
  if (!confirm('Remove this maintenance record?')) return;
  try {
    const res = await frappe.call({
      method: "production_scheduler.api.delete_maintenance_and_cascade",
      args: { maintenance_record_name: recordName }
    });
    if (res.message && res.message.status === 'success') {
      frappe.show_alert({ message: res.message.message, indicator: 'green' });
      await fetchMaintenanceRecords();
      if (typeof fetchData === 'function') await fetchData();
    } else if (res.message && res.message.status === 'error') {
      frappe.msgprint(res.message.message || "Error deleting maintenance record");
    }
  } catch (e) {
    frappe.msgprint("Error deleting maintenance record");
    console.error(e);
  }
}

function getRowDateKey(row) {'''

for fpath in files_to_patch:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = re.sub(template_search, template_replace, content, count=1)
    content = re.sub(idx_search, idx_replace, content, count=1)
    content = re.sub(empty_search, empty_replace, content, count=1)
    content = re.sub(func_search, func_replace, content, count=1)
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)

print(f"Patched {len(files_to_patch)} files")
