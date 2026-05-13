<template>
  <div class="cc-container">
    <div class="cc-filters">
      <div class="cc-filter-title">Sheet Cutting Order Table</div>
      <div class="cc-filter-item">
        <label>View Scope</label>
        <select v-model="viewScope" @change="toggleViewScope" class="cc-select-scope">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>
      <div class="cc-filter-item" v-if="viewScope === 'daily'"><label>Planned Date</label><input type="date" v-model="filterOrderDate" /></div>
      <div class="cc-filter-item" v-else-if="viewScope === 'weekly'"><label>Select Week</label><input type="week" v-model="filterWeek" /></div>
      <div class="cc-filter-item" v-else-if="viewScope === 'monthly'"><label>Select Month</label><input type="month" v-model="filterMonth" /></div>
      <div class="cc-filter-item cc-shift-filter">
        <label>Shift</label>
        <div class="cc-shift-btns">
          <button type="button" :class="{ active: filterShift === 'all' }" @click="filterShift = 'all'">All</button>
          <button type="button" :class="{ active: filterShift === 'day' }" @click="filterShift = 'day'">Day</button>
          <button type="button" :class="{ active: filterShift === 'night' }" @click="filterShift = 'night'">Night</button>
        </div>
      </div>
      <div class="cc-filter-item cc-shift-filter">
        <label>Process</label>
        <div class="cc-shift-btns">
          <button type="button" :class="{ active: processFilter === '251' }" @click="setProcessFilter('251')">251</button>
          <button type="button" :class="{ active: processFilter === '252' }" @click="setProcessFilter('252')">252</button>
          <button type="button" :class="{ active: processFilter === '253' }" @click="setProcessFilter('253')">253</button>
          <button type="button" :class="{ active: processFilter === '255' }" @click="setProcessFilter('255')">255</button>
          <button type="button" :class="{ active: processFilter === '__all__' }" @click="setProcessFilter('__all__')">All</button>
        </div>
      </div>
      <div class="cc-filter-item"><label>Order Code</label><input type="text" v-model="filterPartyCode" placeholder="Search..." @input="debouncedFetch" /></div>
      <div class="cc-filter-item"><label>Customer</label><input type="text" v-model="filterCustomer" placeholder="Search..." @input="debouncedFetch" /></div>
      <div class="cc-filter-actions">
        <button type="button" class="cc-maint-btn" @click="openMachineOffDialog">Machine Off</button>
        <button type="button" class="cc-clear-btn" @click="toggleArrangementLock">{{ arrangementLocked ? "Unlock Arrangment" : "Lock Arrangment" }}</button>
        <button type="button" class="cc-clear-btn" @click="saveArrangement">Save Arrangment</button>
        <button type="button" class="cc-clear-btn" @click="restoreArrangement">Restore Arrangment</button>
        <button type="button" class="cc-clear-btn" @click="openAssignShiftDialog">Assign Shift</button>
        <button type="button" class="cc-clear-btn" @click="fetchData">Refresh</button>
        <button type="button" class="cc-clear-btn" :title="sizeDimUnit === 'inches' ? 'Show roll & sheet size in mm (nearest 5)' : 'Show sizes in inches'" @click="toggleSizeDimUnit">{{ sizeDimUnit === "inches" ? "Sizes: mm" : "Sizes: Inches" }}</button>
        <button type="button" class="cc-view-btn" @click="goToBoard">Back to Sheet Cutting Board</button>
      </div>
    </div>

    <div class="cc-shift-board" v-if="showShiftPlanner">
      <div class="cc-shift-board-head">
        <div class="cc-shift-board-title">Shift Planner (drag between Day/Night)</div>
        <div class="cc-shift-board-date"><label>Shift Date</label><input type="date" v-model="moveTargetDate" /></div>
      </div>
      <div class="cc-shift-lanes">
        <div class="cc-shift-lane" :class="{ over: dragOverShift === 'DAY' }" @dragover.prevent @dragenter.prevent="dragOverShift = 'DAY'" @dragleave="dragOverShift = ''" @drop.prevent="handleShiftDrop('DAY')">
          <div class="cc-shift-lane-title">DAY</div>
          <div v-for="row in scheduleRowsByShift('DAY')" :key="`${row.itemName}-day`" class="cc-shift-card" draggable="true" @dragstart="onRowDragStart(row)" @dragend="onRowDragEnd">
            <div class="cc-shift-card-code">{{ row.partyCode || row.itemCode }}</div>
            <div class="cc-shift-card-meta">{{ row.customer_name || row.customer }}</div>
          </div>
        </div>
        <div class="cc-shift-lane" :class="{ over: dragOverShift === 'NIGHT' }" @dragover.prevent @dragenter.prevent="dragOverShift = 'NIGHT'" @dragleave="dragOverShift = ''" @drop.prevent="handleShiftDrop('NIGHT')">
          <div class="cc-shift-lane-title">NIGHT</div>
          <div v-for="row in scheduleRowsByShift('NIGHT')" :key="`${row.itemName}-night`" class="cc-shift-card" draggable="true" @dragstart="onRowDragStart(row)" @dragend="onRowDragEnd">
            <div class="cc-shift-card-code">{{ row.partyCode || row.itemCode }}</div>
            <div class="cc-shift-card-meta">{{ row.customer_name || row.customer }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="cc-table-container">
      <div class="cc-table-unit-header lot-header">JVE - SHEET CUTTING MACHINE - Planned orders ({{ processFilter === "__all__" ? "251 + 252 + 253 + 255" : processFilter }})</div>
      <table class="cc-prod-table lot-table">
        <thead><tr><th class="th-n">S.NO</th><th style="min-width:84px;">ARRANGMENT</th><th style="min-width:90px;">DATE</th><th style="min-width:64px;">SHIFT</th><th style="min-width:120px;">ORDER CODE</th><th style="min-width:150px;">CUSTOMER NAME</th><th v-if="showProcessColumn" style="min-width:80px;">PROCESS</th><th v-if="showDesignColumns" style="min-width:90px;">DESIGN CODE</th><th v-if="showDesignColumns" style="min-width:120px;">DESIGN NAME</th><th style="min-width:90px;">QUALITY</th><th style="min-width:64px;">GSM</th><th v-if="showLamGsmColumn" style="min-width:72px;">LAM GSM</th><th v-if="showBoppGsmColumn" style="min-width:80px;">BOPP GSM</th><th style="min-width:96px;">{{ rollSizeHeader }}</th><th style="min-width:76px;">MTR</th><th style="min-width:110px;">{{ sheetSizeHeader }}</th><th style="min-width:90px;">PLANNED QTY</th><th style="min-width:96px;">ACHIEVED QTY</th><th style="min-width:120px;">PER DAY PRODUCTION</th><th style="min-width:120px;">PRODUCTION PLAN</th><th style="min-width:160px;">SPR / WO</th></tr></thead>
        <tbody>
          <template v-for="(row, idx) in displayRows" :key="row.dateKey + (row.is_maintenance_row ? '-maint' : (row.is_maintenance_empty ? '-empty' : ('-item-' + (row.itemName || idx))))">
            <tr v-if="row.is_maintenance_row" class="pt-non-draggable" style="background-color:#fee2e2;border:2px solid #dc2626;"><td :colspan="tableColCount" style="padding:8px 12px;font-weight:700;color:#991b1b;text-align:center;">MAINTENANCE: {{ row.record.maintenance_type }} ({{ row.record.start_date }} - {{ row.record.end_date }})</td></tr>
            <tr v-else-if="row.is_maintenance_empty"><td class="cell-center">-</td><td class="cell-center"><span v-if="!arrangementUnlocked" class="cc-lock-hint">Locked</span></td><td class="cell-center font-bold">{{ formatDate(row.dateKey) }}</td><td :colspan="Math.max(1, tableColCount - 3)" style="text-align:center;color:#94a3b8;font-style:italic;">No sheet cutting orders (maintenance day)</td></tr>
            <tr v-else :draggable="arrangementUnlocked" @dragstart="onOrderDragStart(row, $event)" @dragover.prevent="onOrderDragOver(row)" @dragleave="onOrderDragLeave(row)" @drop.prevent="onOrderDrop(row)" @dragend="onOrderDragEnd" :class="{ 'cc-row-draggable': arrangementUnlocked, 'cc-row-drag-over': dragOverItemName === row.itemName }">
              <td class="cell-center">{{ row._sno }}</td>
              <td class="cell-center"><span v-if="arrangementUnlocked" class="cc-drag-handle">Drag</span><span v-else>-</span></td>
              <td class="cell-center">{{ formatDate(row.plannedDate || row.planned_date) }}</td>
              <td class="cell-center">{{ row.shift_label || "DAY" }}</td>
              <td class="cell-center">{{ row.partyCode || row.party_code || row.order_code || "-" }}</td>
              <td>{{ row.customer_name || row.customer || "-" }}</td>
              <td v-if="showProcessColumn" class="cell-center font-bold">{{ row.process || inferProcessFromItemCode(row.itemCode || row.item_code) || "-" }}</td>
              <td v-if="showDesignColumns" class="cell-center font-bold">{{ row.design_code || row.custom_design_code || "-" }}</td>
              <td v-if="showDesignColumns" class="cell-center font-bold">{{ row.design_name || row.custom_design_name || "-" }}</td>
              <td class="cell-center">{{ row.quality || "-" }}</td><td class="cell-center">{{ row.gsm || "-" }}</td>
              <td v-if="showLamGsmColumn" class="cell-center">{{ formatNum(row.custom_lam_gsm) }}</td>
              <td v-if="showBoppGsmColumn" class="cell-center">{{ formatNum(row.custom_bopp_gsm) }}</td>
              <td class="cell-center">{{ formatRollSizeCell(row) }}</td><td class="cell-right">{{ formatNum(row.mtr) }}</td><td class="cell-center">{{ formatSheetSizeCell(row) }}</td>
              <td class="cell-right">{{ formatNum(row.planned_quantity) }}</td><td class="cell-right">{{ formatNum(row.achieved_quantity) }}</td><td v-if="showMergedPerDayProductionCell(row)" class="cell-right pt-merged-perday" :rowspan="getMergedPerDayProductionRowSpan(row)">{{ formatNum(row.per_day_production) }}</td>
              <!-- PRODUCTION PLAN: open print format (same as Lamination table) -->
              <td class="cell-center">
                <button v-if="row.pp_id && Number(row.pp_docstatus) === 1" type="button" class="cc-pp-btn" @click="openProductionPlanView(row.planningSheet, row.salesOrderItem, row.itemName, row.pp_id)">View</button>
                <span v-else-if="row.pp_id" class="pt-wo-closed-hint">PP Draft</span>
                <span v-else class="muted">No PP</span>
              </td>
              <!-- SPR / WO: status pills + action buttons -->
              <td class="cell-center">
                <div class="pt-stock-cell">
                  <div v-if="row.pp_id" class="pt-pill-row">
                    <span v-if="row.spr_name" class="pt-pill" :class="sprPillClass(row)" :title="sprPillTitle(row)">{{ sprPillLabel(row) }}</span>
                    <span v-else class="pt-pill pt-pill-muted">SPR: -</span>
                    <span class="pt-pill pt-pill-wo" :class="woPillClass(row)" :title="woPillTitle(row)">{{ woPillLabel(row) }}</span>
                  </div>
                  <div v-if="itemProductionStatusLine(row)" class="pt-prod-status-line">{{ itemProductionStatusLine(row) }}</div>
                  <!-- View SPR button -->
                  <button v-if="row.spr_name" type="button" @click="openResolvedSPR(row)"
                    class="cc-pp-btn pt-btn-entry"
                    :class="Number(row.spr_docstatus) === 1 && row.wo_terminal ? 'pt-spr-btn-done' : Number(row.spr_docstatus) === 1 ? 'pt-spr-btn-submitted' : 'pt-spr-btn-draft'"
                    :title="itemSprTitle(row)">{{ itemSprLabel(row) }}</button>
                  <button v-if="canCreateSpr(row) && Number(row.spr_docstatus) !== 0" type="button" @click="createSheetCuttingSpr(row)"
                    class="cc-pp-btn pt-btn-entry" title="Create another Shaft Production Run">New SPR</button>
                  <!-- Open WO directly when WO exists and is open -->
                  <button v-else-if="row.wo_name && row.wo_open && Number(row.pp_docstatus) === 1"
                    type="button" @click="openWO(row.wo_name)"
                    class="cc-pp-btn pt-btn-entry pt-spr-btn-submitted" title="Open Work Order">Open WO</button>
                  <!-- Start WO: open PP form to create WO -->
                  <button v-else-if="row.pp_id && Number(row.pp_docstatus) === 1 && !row.wo_open && !row.wo_terminal"
                    type="button" @click="openPPForm(row.pp_id)"
                    class="cc-pp-btn pt-btn-entry" title="Open Production Plan to start Work Order">Start WO</button>
                  <span v-else-if="row.pp_id && Number(row.pp_docstatus) !== 1" class="muted" style="font-size:11px;">PP Draft</span>
                  <span v-else-if="!row.pp_id" class="muted" style="font-size:11px;">No PP</span>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="!displayRows.length"><td :colspan="tableColCount" class="cell-center" style="padding:24px;color:#64748b;">No sheet cutting orders for this view.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { formatSheetSizeCell as formatSheetSizeCellMm, formatSingleDimension } from "./planning_table_size_units.js";
import { mergeSprCsv, resolveSprNavigationTarget } from "./spr_csv_utils.js";
const DIM_UNIT_LS_KEY = "pp_planning_table_dim_unit_sheet_cutting";
const sizeDimUnit = ref("inches");
const rollSizeHeader = computed(() => (sizeDimUnit.value === "mm" ? "ROLL SIZE (mm)" : "ROLL SIZE (Inches)"));
const sheetSizeHeader = computed(() =>
  sizeDimUnit.value === "mm" ? "SHEET SIZE (mm)" : "SHEET SIZE (Inches)"
);
function toggleSizeDimUnit() {
  sizeDimUnit.value = sizeDimUnit.value === "mm" ? "inches" : "mm";
  try {
    localStorage.setItem(DIM_UNIT_LS_KEY, sizeDimUnit.value);
  } catch (_) {}
}
function formatRollSizeCell(row) {
  if (!row || row.is_maintenance_row || row.is_maintenance_empty) return "-";
  return formatSingleDimension(row, "roll_size", sizeDimUnit.value, row.fabric_item_code || "");
}
function formatSheetSizeCell(row) {
  if (!row || row.is_maintenance_row || row.is_maintenance_empty) return "-";
  return formatSheetSizeCellMm(row, sizeDimUnit.value);
}
const SHEET_CUTTING_UNIT = "JVE - SHEET CUTTING MACHINE";
const filterOrderDate = ref(frappe.datetime.get_today()); const filterWeek = ref(""); const filterMonth = ref(""); const viewScope = ref("daily");
const filterPartyCode = ref(""); const filterCustomer = ref(""); const filterShift = ref("all"); const processFilter = ref("251"); const rawData = ref([]);
const maintenanceRecords = ref([]); const moveTargetDate = ref(frappe.datetime.get_today()); const dragRow = ref(null); const dragOverShift = ref("");
const arrangementLocked = ref(true); const dragOrderRow = ref(null); const dragOverItemName = ref(""); const customOrderByDate = ref({});
let fetchTimer = null; let fetchInProgress = false; let autoRefreshTimer = null; const showShiftPlanner = computed(() => viewScope.value !== "monthly");
const arrangementUnlocked = computed(() => !arrangementLocked.value);
const showProcessColumn = computed(() => processFilter.value === "__all__");
const showDesignColumns = computed(() => ["252", "255", "__all__"].includes(processFilter.value));
const showLamGsmColumn = computed(() => processFilter.value === "253" || processFilter.value === "__all__");
const showBoppGsmColumn = computed(() => processFilter.value === "255" || processFilter.value === "__all__");
const tableColCount = computed(
  () => 16 + (showProcessColumn.value ? 1 : 0) + (showDesignColumns.value ? 2 : 0) + (showLamGsmColumn.value ? 1 : 0) + (showBoppGsmColumn.value ? 1 : 0)
);
function setProcessFilter(value) {
  const allowed = new Set(["251", "252", "253", "255", "__all__"]);
  const next = allowed.has(value) ? value : "251";
  if (processFilter.value === next) return;
  processFilter.value = next;
  updateUrlParams();
  fetchData();
}
function inferProcessFromItemCode(itemCode) {
  const ic = String(itemCode || "").trim().toUpperCase();
  if (!ic) return "";
  if (/^253-/.test(ic) || /^[A-Z0-9]+-253/.test(ic)) return "253";
  if (/-255[A-Z]/.test(ic) || /^255/.test(ic)) return "255";
  const body = ic.includes("-") ? ic.split("-").slice(1).join("-") : ic;
  const m = body.match(/(\d{3})/);
  return m ? m[1] : "";
}
const mergedPerDayProductionDates = computed(() => {
  const map = {};
  const seen = new Set();
  for (const row of displayRows.value || []) {
    if (!row || row.is_maintenance_row || row.is_maintenance_empty) continue;
    const dateKey = getRowDateKey(row);
    if (!dateKey || seen.has(dateKey)) continue;
    seen.add(dateKey);
    map[dateKey] = String(row.itemName || row.item_name || "");
  }
  return map;
});
const mergedPerDayProductionRowCounts = computed(() => {
  const counts = {};
  for (const row of filteredRows.value || []) {
    const dateKey = getRowDateKey(row);
    if (!dateKey) continue;
    counts[dateKey] = (counts[dateKey] || 0) + 1;
  }
  return counts;
});
const filteredRows = computed(() => {
  let d = rawData.value || []; const pc = (filterPartyCode.value || "").trim().toLowerCase(); const cu = (filterCustomer.value || "").trim().toLowerCase();
  if (pc) d = d.filter((r) => String(r.partyCode || r.party_code || "").toLowerCase().includes(pc));
  if (cu) d = d.filter((r) => String(r.customer_name || r.customer || "").toLowerCase().includes(cu));
  const sh = (filterShift.value || "all").toLowerCase(); if (sh === "day") d = d.filter((r) => String(r.shift_label || "DAY").toUpperCase() === "DAY"); else if (sh === "night") d = d.filter((r) => String(r.shift_label || "").toUpperCase() === "NIGHT");
  return sortRowsBySavedSequence(d);
});
const displayRows = computed(() => {
  const normalRows = filteredRows.value || [];
  const { start_date, end_date } = getScopeDateRange();
  if (!start_date || !end_date) {
    normalRows.forEach((r, i) => {
      r._sno = i + 1;
    });
    return normalRows;
  }
  const start = new Date(start_date);
  const end = new Date(end_date);
  const out = [];
  let sno = 1;
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const k = toDateKey(d);
    const recs = (maintenanceRecords.value || []).filter(
      (r) => new Date(k) >= new Date(r.start_date) && new Date(k) <= new Date(r.end_date)
    );
    if (recs.length) out.push({ is_maintenance_row: true, dateKey: k, record: recs[0] });

    const dateRows = normalRows.filter((r) => getRowDateKey(r) === k);

    // PER DAY PRODUCTION is merged via rowspan in non-daily views (template uses v-if + rowspan),
    // so do not mutate row values here.

    for (const r of dateRows) {
      r._sno = sno++;
      out.push(r);
    }
    if (!dateRows.length && recs.length) out.push({ is_maintenance_empty: true, dateKey: k });
  }
  return out;
});
function toDateKey(v) { if (!v) return ""; const d = new Date(v); if (Number.isNaN(d.getTime())) return ""; return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
function getRowDateKey(row) { return toDateKey(row?.plannedDate || row?.planned_date || row?.date || ""); }
function sortRowsBySavedSequence(rows) { const grouped = {}; (rows || []).forEach((r) => { const dk = getRowDateKey(r); grouped[dk] = grouped[dk] || []; grouped[dk].push(r); }); const out = []; Object.keys(grouped).sort().forEach((dk) => { const arr = grouped[dk]; const saved = customOrderByDate.value[dk] || []; const rank = new Map(saved.map((nm, i) => [nm, i])); arr.sort((a, b) => { const ra = rank.has(a.itemName) ? rank.get(a.itemName) : 99999; const rb = rank.has(b.itemName) ? rank.get(b.itemName) : 99999; if (ra !== rb) return ra - rb; return String(a.itemName || "").localeCompare(String(b.itemName || "")); }); out.push(...arr); }); return out; }
function formatDate(v) { if (!v) return ""; return frappe.datetime.str_to_user(v); }
function formatNum(v) {
  if (v === "" || v === null || typeof v === "undefined") return "-";
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(2).replace(/\.00$/, "");
}
function getMergedPerDayProductionRowSpan(row) {
  const dateKey = getRowDateKey(row);
  return mergedPerDayProductionRowCounts.value[dateKey] || 1;
}
function showMergedPerDayProductionCell(row) {
  const dateKey = getRowDateKey(row);
  const firstItemName = mergedPerDayProductionDates.value[dateKey];
  return String(row.itemName || row.item_name || "") === String(firstItemName || "");
}
function goToBoard() { frappe.set_route("sheet-cutting-board"); }
function syncSprNameForSamePP(ppId, sprId, sourceItemName = "") {
  const pid = String(ppId || "").trim();
  const sid = String(sprId || "").trim();
  if (!pid || !sid) return;
  (rawData.value || []).forEach((row) => {
    if (
      String(row.pp_id || "").trim() === pid &&
      (!sourceItemName || String(row.itemName || "") === String(sourceItemName || ""))
    ) {
      row.spr_name = mergeSprCsv(row.spr_name, sid);
    }
  });
}
async function openResolvedSPR(row) {
  const target = await resolveSprNavigationTarget(row?.spr_name, row?.spr_docstatus);
  if (target) frappe.set_route("Form", "Shaft Production Run", target);
}
function openPPForm(ppId) { if (ppId) frappe.set_route("Form", "Production Plan", ppId); }
function openWO(woName) { if (woName) frappe.set_route("Form", "Work Order", woName); }
function openProductionPlanView(planningSheetName, salesOrderItem, planningSheetItemName, directPpId) {
  if (directPpId) {
    const url = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(directPpId)}&format=${encodeURIComponent("Assembly Item - Raw Material")}&trigger_print=0`;
    window.open(url, "_blank");
    return;
  }
  if (planningSheetName) {
    frappe.call({ method: "production_entry.production_planning.scheduler_api.get_planning_sheet_pp_id", args: { planning_sheet_name: planningSheetName, sales_order_item: salesOrderItem || null, planning_sheet_item: planningSheetItemName || null } }).then(res => {
      const ppId = res?.message?.pp_id;
      if (ppId) { const url = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(ppId)}&format=${encodeURIComponent("Assembly Item - Raw Material")}&trigger_print=0`; window.open(url, "_blank"); }
      else { frappe.msgprint("No Production Plan found for this item."); }
    });
  }
}
function sprPillLabel(row) { if (!row?.spr_name) return ""; if (row.spr_docstatus === 0 || row.spr_docstatus === "0") return "Draft"; if (Number(row.spr_docstatus) === 1) return "Submitted"; return "SPR"; }
function sprPillClass(row) { if (!row?.spr_name) return "pt-pill-muted"; if (row.spr_docstatus === 0 || row.spr_docstatus === "0") return "pt-pill-draft"; if (Number(row.spr_docstatus) === 1) return "pt-pill-submitted"; return "pt-pill-muted"; }
function sprPillTitle(row) { if (!row?.spr_name) return ""; return `SPR: ${row.spr_name}`; }
function woPillLabel(row) { if (row.wo_terminal) return "WO done"; if (row.wo_open) return "WO open"; return "WO"; }
function woPillClass(row) { if (row.wo_terminal) return "pt-pill-wo-done"; if (row.wo_open) return "pt-pill-wo-open"; return "pt-pill-wo-unknown"; }
function woPillTitle(row) { if (row.wo_terminal) return "All work orders complete."; if (row.wo_open) return "Work order in progress."; return "No work order yet."; }
function itemProductionStatusLine(row) { const t = parseFloat(row.planned_quantity || 0); const a = parseFloat(row.achieved_quantity || 0); const gap = t - a; if (Math.abs(gap) <= 0.5) return ""; return gap > 0 ? `${gap.toFixed(2)} kg below target` : `${(-gap).toFixed(2)} kg over target`; }
function itemSprLabel(row) { if (!row?.spr_name) return ""; if (row.spr_docstatus === 0 || row.spr_docstatus === "0") return "Open draft SPR"; if (row.wo_terminal) return "View SPR (done)"; return "View SPR"; }
function itemSprTitle(row) { if (!row?.spr_name) return ""; if (row.spr_docstatus === 0 || row.spr_docstatus === "0") return "Continue recording production in draft SPR"; if (row.wo_terminal) return "WO complete — view final SPR"; return "Open submitted SPR"; }
function canCreateSpr(row) { if (!row.pp_id || Number(row.pp_docstatus) !== 1) return false; if (!row.wo_open) return false; const planned = parseFloat(row.planned_quantity || 0); const achieved = parseFloat(row.achieved_quantity || 0); if (planned > 0 && achieved >= planned - 0.001) return false; return true; }
async function createSheetCuttingSpr(item) {
  if (!item.pp_id) { frappe.msgprint("No Production Plan linked"); return; }
  if (item.__creating_spr) return;
  item.__creating_spr = true;
  try {
    const r = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.create_item_spr",
      args: { pp_id: item.pp_id, planning_sheet_item_names: JSON.stringify([item.itemName]), process_type: "sheet_cutting" }
    });
    const msg = r?.message || {};
    const sprName = msg.spr_id || msg.spr_name;
    if (sprName) {
      item.spr_name = mergeSprCsv(item.spr_name, sprName);
      syncSprNameForSamePP(item.pp_id, sprName, item.itemName);
      frappe.show_alert({ message: `SPR created: ${sprName}`, indicator: "green" }, 3);
      setTimeout(() => frappe.set_route("Form", "Shaft Production Run", sprName), 600);
    } else { frappe.msgprint(msg.message || "SPR creation failed"); }
  } catch (e) { frappe.msgprint(`Failed to create SPR: ${e?.message || e}`); }
  finally { item.__creating_spr = false; }
}
function debouncedFetch() { if (fetchTimer) clearTimeout(fetchTimer); fetchTimer = setTimeout(() => fetchData(), 300); }
function toggleArrangementLock() { arrangementLocked.value = !arrangementLocked.value; }
function onOrderDragStart(row, e) { if (!arrangementUnlocked.value || row?.is_maintenance_row || row?.is_maintenance_empty) return; dragOrderRow.value = row; e.dataTransfer.effectAllowed = "move"; }
function onOrderDragOver(row) { if (!arrangementUnlocked.value || !dragOrderRow.value || row?.is_maintenance_row || row?.is_maintenance_empty) return; dragOverItemName.value = row.itemName; }
function onOrderDragLeave(row) { if (dragOverItemName.value === row?.itemName) dragOverItemName.value = ""; }
function onOrderDrop(targetRow) { if (!arrangementUnlocked.value || !dragOrderRow.value || !targetRow || targetRow.is_maintenance_row || targetRow.is_maintenance_empty) return; const source = dragOrderRow.value; const sDate = getRowDateKey(source); const tDate = getRowDateKey(targetRow); if (!sDate || sDate !== tDate) { dragOrderRow.value = null; dragOverItemName.value = ""; return; } const dateRows = (filteredRows.value || []).filter(r => getRowDateKey(r) === sDate); const srcIdx = dateRows.findIndex(r => r.itemName === source.itemName); const tgtIdx = dateRows.findIndex(r => r.itemName === targetRow.itemName); if (srcIdx < 0 || tgtIdx < 0 || srcIdx === tgtIdx) { dragOrderRow.value = null; dragOverItemName.value = ""; return; } const cloned = [...dateRows]; const [moved] = cloned.splice(srcIdx, 1); cloned.splice(tgtIdx, 0, moved); customOrderByDate.value[sDate] = cloned.map(r => r.itemName); dragOrderRow.value = null; dragOverItemName.value = ""; }
function onOrderDragEnd() { dragOrderRow.value = null; dragOverItemName.value = ""; }
function scheduleRowsByShift(shift) { return (filteredRows.value || []).filter(r => String(r.shift_label || "DAY").toUpperCase() === shift); }
function onRowDragStart(row) { dragRow.value = row; } function onRowDragEnd() { dragOverShift.value = ""; }
async function handleShiftDrop(targetShift) { const row = dragRow.value; dragOverShift.value = ""; if (!row?.itemName) return; const dateKey = toDateKey(moveTargetDate.value); if (!dateKey) return; try { await frappe.call({ method: "production_entry.production_planning.scheduler_api.assign_sheet_cutting_shift", args: { shift_date: dateKey, shift_label: targetShift, item_name: row.itemName } }); await fetchData(); } catch (e) { frappe.msgprint(`Failed to move row: ${e?.message || e}`); } finally { dragRow.value = null; } }
function currentShiftDateForDialog() { if (viewScope.value === "daily" && filterOrderDate.value) return filterOrderDate.value; return frappe.datetime.get_today(); }
function openAssignShiftDialog() { const d = new frappe.ui.Dialog({ title: "Assign Sheet Cutting Shift", fields: [{ fieldname: "shift_date", label: "Planned Date", fieldtype: "Date", reqd: 1, default: currentShiftDateForDialog() }, { fieldname: "shift_label", label: "Shift", fieldtype: "Select", options: "DAY\nNIGHT", reqd: 1, default: "DAY" }], primary_action_label: "Apply", primary_action: async (vals) => { await frappe.call({ method: "production_entry.production_planning.scheduler_api.assign_sheet_cutting_shift", args: { shift_date: vals.shift_date, shift_label: vals.shift_label } }); d.hide(); if (viewScope.value === "daily") filterOrderDate.value = vals.shift_date; await fetchData(); } }); d.show(); }
async function openMachineOffDialog() { const d = new frappe.ui.Dialog({ title: "Sheet Cutting Machine Off", fields: [{ fieldtype: "Date", fieldname: "start_date", label: "From Date", reqd: 1, default: filterOrderDate.value || frappe.datetime.get_today() }, { fieldtype: "Date", fieldname: "end_date", label: "To Date", reqd: 1, default: filterOrderDate.value || frappe.datetime.get_today() }, { fieldtype: "Select", fieldname: "maintenance_type", label: "Type", options: "Machine Off\nBreakdown - Full\nBreakdown - Partial\nEB Shutdown\nMesh Change\nDie Change", default: "Machine Off", reqd: 1 }, { fieldtype: "Small Text", fieldname: "notes", label: "Notes" }], primary_action_label: "Save", primary_action: async (vals) => { await frappe.call({ method: "production_entry.production_planning.scheduler_api.add_equipment_maintenance", args: { unit: SHEET_CUTTING_UNIT, start_date: vals.start_date, end_date: vals.end_date, maintenance_type: vals.maintenance_type, notes: vals.notes || "" } }); d.hide(); await fetchMaintenanceRecords(); await fetchData(); } }); d.show(); }
async function saveArrangement() { try { const seq = {}; Object.keys(customOrderByDate.value || {}).forEach((dateKey) => { seq[dateKey] = { date: dateKey, sequence: (customOrderByDate.value[dateKey] || []).map((nm, idx) => ({ item_name: nm, idx: idx + 1 })) }; }); await frappe.call({ method: "production_entry.production_planning.scheduler_api.save_color_sequence", args: { date: filterOrderDate.value || frappe.datetime.get_today(), unit: SHEET_CUTTING_UNIT, sequence_data: JSON.stringify(seq), plan_name: "sheet_cutting_table" } }); frappe.show_alert({ message: "Arrangement saved", indicator: "green" }, 3); } catch (e) { frappe.msgprint(`Save failed: ${e?.message || e}`); } }
async function restoreArrangement() { try { const r = await frappe.call({ method: "production_entry.production_planning.scheduler_api.restore_last_color_sequence", args: { date: filterOrderDate.value || frappe.datetime.get_today(), unit: SHEET_CUTTING_UNIT, plan_name: "sheet_cutting_table" } }); const payload = r?.message?.sequence_data ? JSON.parse(r.message.sequence_data) : {}; const next = {}; Object.keys(payload || {}).forEach((k) => { next[k] = (payload[k]?.sequence || []).map(x => x.item_name).filter(Boolean); }); customOrderByDate.value = next; } catch (e) { frappe.msgprint(`Restore failed: ${e?.message || e}`); } }
function getScopeDateRange() { if (viewScope.value === "monthly" && filterMonth.value) { const [year, month] = filterMonth.value.split("-"); const lastDay = new Date(year, month, 0).getDate(); return { start_date: `${filterMonth.value}-01`, end_date: `${filterMonth.value}-${lastDay}` }; } if (viewScope.value === "weekly" && filterWeek.value) { const [yearStr, weekStr] = filterWeek.value.split("-W"); const y = parseInt(yearStr, 10); const w = parseInt(weekStr, 10); const simple = new Date(y, 0, 1 + (w - 1) * 7); const dow = simple.getDay(); const ws = new Date(simple); if (dow <= 4) ws.setDate(simple.getDate() - simple.getDay() + 1); else ws.setDate(simple.getDate() + 8 - simple.getDay()); const we = new Date(ws); we.setDate(we.getDate() + 6); const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; return { start_date: fmt(ws), end_date: fmt(we) }; } return { start_date: filterOrderDate.value, end_date: filterOrderDate.value }; }
async function fetchMaintenanceRecords() { try { const res = await frappe.call({ method: "production_entry.production_planning.scheduler_api.get_all_equipment_maintenance" }); maintenanceRecords.value = (res?.message || []).filter((r) => String(r.unit || "") === SHEET_CUTTING_UNIT); } catch { maintenanceRecords.value = []; } }
function toggleViewScope() { if (viewScope.value === "monthly" && !filterMonth.value) filterMonth.value = frappe.datetime.get_today().substring(0, 7); updateUrlParams(); fetchData(); }
async function fetchData() { if (fetchInProgress) return; fetchInProgress = true; try { let args = { planned_only: 1, process: processFilter.value }; if (viewScope.value === "monthly") { if (!filterMonth.value) return; const [year, month] = filterMonth.value.split("-"); const lastDay = new Date(year, month, 0).getDate(); args.start_date = `${filterMonth.value}-01`; args.end_date = `${filterMonth.value}-${lastDay}`; } else if (viewScope.value === "weekly") { if (!filterWeek.value) return; const [yearStr, weekStr] = filterWeek.value.split("-W"); const y = parseInt(yearStr, 10); const w = parseInt(weekStr, 10); const simple = new Date(y, 0, 1 + (w - 1) * 7); const dow = simple.getDay(); const ws = new Date(simple); if (dow <= 4) ws.setDate(simple.getDate() - simple.getDay() + 1); else ws.setDate(simple.getDate() + 8 - simple.getDay()); const we = new Date(ws); we.setDate(we.getDate() + 6); const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; args.start_date = fmt(ws); args.end_date = fmt(we); } else args.date = filterOrderDate.value; const r = await frappe.call({ method: "production_entry.production_planning.scheduler_api.get_sheet_cutting_order_table_data", args }); rawData.value = (r.message || []).map((d) => ({ ...d, itemName: d.itemName || d.item_name || "", plannedDate: d.plannedDate || d.planned_date || "", planningSheet: d.planningSheet || d.planning_sheet || "", process: d.process || inferProcessFromItemCode(d.itemCode || d.item_code || ""), design_code: d.design_code || d.custom_design_code || "", design_name: d.design_name || d.custom_design_name || "", salesOrderItem: d.salesOrderItem || d.sales_order_item || "", custom_lam_gsm: d.custom_lam_gsm ?? d.customLamGsm, custom_bopp_gsm: d.custom_bopp_gsm ?? d.customBoppGsm })); await fetchMaintenanceRecords(); } catch (e) { frappe.msgprint(`Error loading Sheet Cutting Order Table: ${e?.message || e}`); } finally { fetchInProgress = false; } }
function updateUrlParams() { const q = new URLSearchParams(); if (viewScope.value === "daily") q.set("date", filterOrderDate.value); if (viewScope.value === "weekly") q.set("week", filterWeek.value); if (viewScope.value === "monthly") q.set("month", filterMonth.value); q.set("scope", viewScope.value); q.set("process", processFilter.value); window.history.replaceState({}, "", `${window.location.pathname}?${q.toString()}`); }
function startAutoRefresh() { if (autoRefreshTimer) clearInterval(autoRefreshTimer); autoRefreshTimer = setInterval(() => { if (document.visibilityState === "visible") fetchData(); }, 15000); }
watch([filterOrderDate, filterWeek, filterMonth], () => { updateUrlParams(); fetchData(); });
onMounted(async () => { try { const u = localStorage.getItem(DIM_UNIT_LS_KEY); if (u === "mm" || u === "inches") sizeDimUnit.value = u; } catch (_) {} const p = new URLSearchParams(window.location.search); if (p.get("scope")) viewScope.value = p.get("scope"); if (p.get("date")) filterOrderDate.value = p.get("date"); if (p.get("week")) filterWeek.value = p.get("week"); if (p.get("month")) filterMonth.value = p.get("month"); if (["251", "252", "253", "255", "__all__"].includes(p.get("process"))) processFilter.value = p.get("process"); moveTargetDate.value = filterOrderDate.value || frappe.datetime.get_today(); updateUrlParams(); await fetchData(); startAutoRefresh(); });
onUnmounted(() => { if (autoRefreshTimer) clearInterval(autoRefreshTimer); });
</script>

<style scoped>
.cc-container {
  display: flex;
  flex-direction: column;
  padding: 14px;
  background: #f3f4f6;
  min-height: 100vh;
  color: #0f172a;
}
.cc-filters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
  align-items: end;
  margin-bottom: 12px;
  padding: 12px 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}
.cc-filter-title {
  grid-column: 1 / -1;
  font-weight: 700;
  color: #065f46;
}
.cc-filter-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cc-filter-item label {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}
.cc-filter-item input,
.cc-filter-item select {
  min-height: 34px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 6px 8px;
  background: #fff;
}
.cc-filter-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: flex-end;
  grid-column: 1 / -1;
}
.cc-clear-btn,
.cc-view-btn {
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  min-height: 34px;
  padding: 0 10px;
  background: #f8fafc;
  font-weight: 600;
}
.cc-view-btn {
  background: #ecfeff;
  border-color: #99f6e4;
}
.cc-table-container {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.cc-shift-board {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  margin-bottom: 12px;
  padding: 10px 12px;
}
.cc-shift-board-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 10px;
}
.cc-shift-board-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f766e;
}
.cc-shift-board-date label {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 4px;
}
.cc-shift-lanes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.cc-shift-lane {
  min-height: 88px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  padding: 8px;
  background: #f8fafc;
}
.cc-shift-lane.over {
  border-color: #0ea5e9;
  background: #eff6ff;
}
.cc-shift-lane-title {
  font-size: 11px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 6px;
}
.cc-shift-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px;
  margin-bottom: 6px;
  cursor: grab;
}
.cc-shift-card-code { font-size: 11px; font-weight: 700; color: #0f172a; }
.cc-shift-card-meta { font-size: 10px; color: #64748b; }
.cc-table-unit-header {
  padding: 10px 12px;
  border-bottom: 1px solid #e2e8f0;
  font-weight: 700;
  color: #065f46;
  background: #f8fafc;
}
.cc-prod-table {
  width: 100%;
  min-width: 1280px;
  border-collapse: collapse;
  font-size: 13px;
  line-height: 1.6;
}
.cc-prod-table th {
  position: sticky;
  top: 0;
  z-index: 14;
  background: #047857;
  color: #fff;
  padding: 14px 12px;
  text-align: left;
  font-weight: 700;
  white-space: normal;
  min-width: 100px;
  word-wrap: break-word;
  border-bottom: 1px solid #065f46;
}
.cc-prod-table td {
  border-bottom: 1px solid #d1d5db;
  padding: 12px 12px;
  vertical-align: middle;
  line-height: 1.5;
}
.cc-prod-table tbody tr {
  height: auto;
  transition: background-color 0.2s ease;
}
.cc-prod-table tbody tr:hover {
  background-color: #f9fafb;
}
.th-n {
  width: 60px;
  text-align: center;
}
.cell-center {
  text-align: center;
  min-width: 80px;
}
.cell-right {
  text-align: right;
}
.cc-row-draggable {
  cursor: move;
}
.cc-row-drag-over {
  outline: 2px dashed #0ea5e9;
  outline-offset: -2px;
  background: #f0f9ff;
}
.pt-merged-perday{
  background: #f8fafc;
  font-weight: 700;
  border: 2px solid #cbd5e1;
  text-align: center;
  vertical-align: middle;
}
.muted {
  color: #94a3b8;
  font-size: 12px;
}
.cc-pp-btn {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  min-height: 28px;
  padding: 0 10px;
  background: #ecfeff;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
}
.pt-stock-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}
.pt-pill-row {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: center;
}
.pt-pill {
  padding: 2px 7px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}
.pt-pill-draft { background: #fef3c7; color: #92400e; }
.pt-pill-submitted { background: #dcfce7; color: #166534; }
.pt-pill-muted { background: #f1f5f9; color: #64748b; }
.pt-pill-wo {}
.pt-pill-wo-done { background: #dcfce7; color: #166534; }
.pt-pill-wo-open { background: #dbeafe; color: #1d4ed8; }
.pt-pill-wo-unknown { background: #f1f5f9; color: #64748b; }
.pt-prod-status-line {
  font-size: 11px;
  color: #64748b;
  white-space: nowrap;
}
.pt-btn-entry {
  padding: 3px 8px;
  font-size: 11px;
  min-height: 26px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  cursor: pointer;
  font-weight: 600;
  background: #f8fafc;
}
.pt-spr-btn-done { background: #dcfce7; border-color: #86efac; color: #166534; }
.pt-spr-btn-submitted { background: #dbeafe; border-color: #93c5fd; color: #1d4ed8; }
.pt-spr-btn-draft { background: #fef3c7; border-color: #fcd34d; color: #92400e; }
.pt-wo-closed-hint { color: #94a3b8; font-size: 11px; }
</style>
