<template>
  <div class="cc-container">
    <div class="cc-filters">
      <div class="cc-filter-title">Lamination Order Table</div>
      <div class="cc-filter-item">
        <label>View Scope</label>
        <select v-model="viewScope" @change="toggleViewScope" class="cc-select-scope">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>
      <div class="cc-filter-item" v-if="viewScope === 'daily'">
        <label>Planned Date</label>
        <input type="date" v-model="filterOrderDate" />
      </div>
      <div class="cc-filter-item" v-else-if="viewScope === 'weekly'">
        <label>Select Week</label>
        <input type="week" v-model="filterWeek" />
      </div>
      <div class="cc-filter-item" v-else-if="viewScope === 'monthly'">
        <label>Select Month</label>
        <input type="month" v-model="filterMonth" />
      </div>
      <div class="cc-filter-item cc-shift-filter">
        <label>Shift</label>
        <div class="cc-shift-btns">
          <button type="button" :class="{ active: filterShift === 'all' }" @click="filterShift = 'all'">All</button>
          <button type="button" :class="{ active: filterShift === 'day' }" @click="filterShift = 'day'">Day</button>
          <button type="button" :class="{ active: filterShift === 'night' }" @click="filterShift = 'night'">Night</button>
        </div>
      </div>
      <div class="cc-filter-item">
        <label>Order Code</label>
        <input type="text" v-model="filterPartyCode" placeholder="Search..." @input="debouncedFetch" />
      </div>
      <div class="cc-filter-item">
        <label>Customer</label>
        <input type="text" v-model="filterCustomer" placeholder="Search..." @input="debouncedFetch" />
      </div>
      <div class="cc-filter-actions">
        <button type="button" class="cc-maint-btn" @click="openMachineOffDialog">Machine Off</button>
        <button type="button" class="cc-clear-btn" @click="toggleArrangementLock">{{ arrangementLocked ? "Unlock Arrangement" : "Lock Arrangement" }}</button>
        <button type="button" class="cc-clear-btn" @click="saveLaminationArrangement">Save Arrangement</button>
        <button type="button" class="cc-clear-btn" @click="restoreLaminationArrangement">Restore Arrangement</button>
        <button type="button" class="cc-clear-btn" @click="openAssignShiftDialog">Assign Shift</button>
        <button type="button" class="cc-clear-btn" @click="fetchData">Refresh</button>
        <button type="button" class="cc-view-btn" @click="goToBoard">Back to Lamination Board</button>
      </div>
    </div>

    <div class="cc-table-container">
      <div class="cc-table-unit-header lot-header">Lamination Unit - Planned orders ({{ filteredRows.length }})</div>
      <table class="cc-prod-table lot-table">
        <thead>
          <tr>
            <th class="th-n">S.NO</th>
            <th>DATE</th>
            <th>SHIFT</th>
            <th>BOOKING ID</th>
            <th>CUSTOMER</th>
            <th>QUALITY</th>
            <th>DESIGN</th>
            <th>FABRIC GSM</th>
            <th>LAM GSM</th>
            <th>PLANNED MTR</th>
            <th>ACHIEVED MTR</th>
            <th>KGS</th>
            <th>FABRIC QTY (KG)</th>
            <th>PRODUCED FABRIC WT (KG)</th>
            <th>PRODUCTION PLAN</th>
            <th>ACTIONS</th>
            <th style="min-width:84px;">ORDER</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in filteredRows"
            :key="row.itemName || idx"
            :draggable="arrangementUnlocked"
            @dragstart="onOrderDragStart(row, $event)"
            @dragover.prevent="onOrderDragOver(row)"
            @dragleave="onOrderDragLeave(row)"
            @drop.prevent="onOrderDrop(row)"
            @dragend="onOrderDragEnd"
            :class="{ 'cc-row-draggable': arrangementUnlocked, 'cc-row-drag-over': dragOverItemName === row.itemName }"
          >
            <td class="cell-center">{{ idx + 1 }}</td>
            <td class="cell-center">
              {{ formatDate(row.plannedDate || row.planned_date) }}
              <span v-if="maintenanceTypeForDate(row.plannedDate || row.planned_date)" class="cc-maint-chip">
                OFF: {{ maintenanceTypeForDate(row.plannedDate || row.planned_date) }}
              </span>
            </td>
            <td class="cell-center">{{ row.shift_label || "DAY" }}</td>
            <td class="cell-center font-mono font-bold" style="font-size:11px;color:#047857;">{{ row.lamination_booking_id || "-" }}</td>
            <td>{{ row.customer_name || row.customer || row.partyCode }}</td>
            <td class="cell-center">{{ row.quality }}</td>
            <td class="cell-center font-bold">{{ row.color }}</td>
            <td class="cell-center">{{ row.fabric_gsm || "-" }}</td>
            <td class="cell-center">{{ row.lamination_gsm ?? row.gsm }}</td>
            <td class="cell-right">{{ row.planned_meter ?? "-" }}</td>
            <td class="cell-right">{{ formatNum(row.achieved_meter) }}</td>
            <td class="cell-right">{{ formatKg2(row.actual_production_weight_kgs) }}</td>
            <td class="cell-right">{{ formatKg2(row.fabric_achieved_kg) }} / {{ formatKg2(row.fabric_required_kg) }}</td>
            <td class="cell-right" style="background:#fff9e6;">
              <input 
                type="number" 
                v-model.number="row.produced_fabric_weight_kg" 
                @change="saveProducedWeight(row)"
                step="0.01"
                min="0"
                style="width:100%;padding:2px;border:1px solid #fcd34d;border-radius:4px;"
                title="Actual production weight of fabric for this item"
              />
            </td>
            <td class="cell-center">
              <button v-if="row.pp_id" type="button" @click="openProductionPlanView(row.planningSheet, row.salesOrderItem, row.itemName, row.pp_id || '')" class="cc-pp-btn">📋 View</button>
              <span v-else class="pt-no-pp-hint">No PP</span>
            </td>
            <td class="cell-center" style="min-width:180px;">
              <div class="pt-action-cell">
                <!-- Open WO Button: Show if parent WO exists in draft state -->
                <button
                  v-if="row.parent_wo_name && Number(row.parent_wo_docstatus || 0) === 0"
                  type="button"
                  @click="openParentWO(row)"
                  class="cc-pp-btn"
                  style="font-size:11px;padding:4px 8px;background:#e0f2fe;color:#0369a1;border-color:#0284c7;"
                  title="Open Work Order and set source warehouse if needed"
                >📂 Open WO</button>

                <!-- Start WO Button: Show if conditions are met -->
                <button
                  v-if="row.is_lamination_parent && canStartWO(row)"
                  type="button"
                  @click="startParentWO(row)"
                  class="cc-pp-btn pt-btn-entry"
                  :title="getStartWOTitle(row)"
                  style="font-size:11px;padding:4px 8px;"
                >▶ Start WO</button>

                <!-- Disabled Start WO: Show why it can't start -->
                <button
                  v-if="row.is_lamination_parent && !canStartWO(row) && row.pp_id"
                  type="button"
                  disabled
                  class="cc-pp-btn pt-btn-entry"
                  style="font-size:11px;padding:4px 8px;opacity:0.5;cursor:not-allowed;"
                  :title="getStartWOBlockedReason(row)"
                >⛔ {{ getStartWOBlockedReason(row) }}</button>

                <!-- Stock Entry (SPR) Button -->
                <button
                  v-if="canShowStockEntry(row)"
                  type="button"
                  @click="handleStockEntryAction(row)"
                  class="cc-pp-btn pt-btn-entry"
                  :title="getStockEntryTitle(row)"
                  style="font-size:11px;padding:4px 8px;"
                >{{ getStockEntryLabel(row) }}</button>

                <!-- View SPR Button -->
                <button
                  v-else-if="row.spr_name"
                  type="button"
                  @click="openItemSPR(row.spr_name, row)"
                  class="cc-pp-btn pt-btn-entry"
                  :class="Number(row.spr_docstatus) === 1 && row.wo_terminal ? 'pt-spr-btn-done' : Number(row.spr_docstatus) === 1 ? 'pt-spr-btn-submitted' : 'pt-spr-btn-draft'"
                  :title="itemSprPrimaryButtonTitle(row)"
                  style="font-size:11px;padding:4px 8px;"
                >{{ itemSprPrimaryButtonLabel(row) }}</button>

                <!-- Status Messages -->
                <span v-else-if="row.pp_id && Number(row.pp_docstatus) !== 1" class="pt-wo-closed-hint">PP Draft</span>
                <span v-else-if="row.pp_id && row.wo_terminal" class="pt-wo-closed-hint">✓ WO closed</span>
                <span v-else-if="row.is_lamination_parent && !row.parent_ready_for_wo" class="pt-wo-closed-hint" style="color:#d97706;">⚠ Complete child WO first</span>
                <span v-else style="color:#999;font-size:10px;">No PP</span>
              </div>
            </td>
            <td class="cell-center">
              <span v-if="arrangementUnlocked" class="cc-drag-handle" title="Drag to reorder inside same date">≡≡</span>
              <span v-else class="cc-lock-hint" title="Unlock arrangement to reorder">🔒</span>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="17" class="cell-center" style="padding:24px;color:#64748b;">No lamination orders for this view.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";

const filterOrderDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref("");
const viewScope = ref("daily");
const filterPartyCode = ref("");
const filterCustomer = ref("");
const filterShift = ref("all");
const rawData = ref([]);
const filtersReady = ref(false);
const maintenanceByDate = ref({});
const maintenanceRecords = ref([]);
const moveTargetDate = ref(frappe.datetime.get_today());
const dragRow = ref(null);
const dragOverShift = ref("");
const laminationSequenceStore = ref({});
const pendingArrangementUpdates = ref({});
const arrangementDirty = ref(false);
const arrangementSaving = ref(false);
const arrangementLocked = ref(true);
const dragOrderRow = ref(null);
const dragOverItemName = ref("");
let fetchTimer = null;
let initialFetchRetried = false;

const showShiftPlanner = computed(() => viewScope.value !== "monthly");
const arrangementUnlocked = computed(() => !arrangementLocked.value);

const filteredRows = computed(() => {
  let d = rawData.value || [];
  const pc = (filterPartyCode.value || "").trim().toLowerCase();
  const cu = (filterCustomer.value || "").trim().toLowerCase();
  if (pc) {
    d = d.filter((r) => String(r.partyCode || "").toLowerCase().includes(pc));
  }
  if (cu) {
    d = d.filter((r) => String(r.customer_name || r.customer || "").toLowerCase().includes(cu));
  }
  const sh = (filterShift.value || "all").toLowerCase();
  if (sh === "day") {
    d = d.filter((r) => String(r.shift_label || "DAY").toUpperCase() === "DAY");
  } else if (sh === "night") {
    d = d.filter((r) => String(r.shift_label || "").toUpperCase() === "NIGHT");
  }
  return sortRowsBySavedSequence(d);
});

function getRowDateKey(row) {
  return toDateKey(row?.plannedDate || row?.planned_date);
}

function sortRowsBySavedSequence(rows) {
  const groups = {};
  (rows || []).forEach((row) => {
    const k = getRowDateKey(row) || "no-date";
    if (!groups[k]) groups[k] = [];
    groups[k].push(row);
  });
  const out = [];
  Object.keys(groups)
    .sort()
    .forEach((dateKey) => {
      const seq = laminationSequenceStore.value[dateKey] || [];
      const map = {};
      seq.forEach((name, idx) => {
        map[String(name || "").trim()] = idx;
      });
      const sorted = groups[dateKey].slice().sort((a, b) => {
        const aKey = String(a.itemName || "").trim();
        const bKey = String(b.itemName || "").trim();
        const ai = map[aKey] !== undefined ? map[aKey] : 999999;
        const bi = map[bKey] !== undefined ? map[bKey] : 999999;
        if (ai !== bi) return ai - bi;
        return Number(a.idx || 0) - Number(b.idx || 0);
      });
      out.push(...sorted);
    });
  return out;
}

function debouncedFetch() {
  if (fetchTimer) clearTimeout(fetchTimer);
  fetchTimer = setTimeout(() => fetchData(), 200);
}

function formatDate(d) {
  if (!d) return "-";
  try {
    if (frappe.datetime && frappe.datetime.format_date) {
      return frappe.datetime.format_date(d);
    }
  } catch (e) {}
  return d;
}

function toDateKey(d) {
  if (!d) return "";
  const s = String(d).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const dt = new Date(s);
  if (Number.isNaN(dt.getTime())) return "";
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const day = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function getScopeDateRange() {
  if (viewScope.value === "monthly" && filterMonth.value) {
    const [year, month] = filterMonth.value.split("-");
    const lastDay = new Date(year, month, 0).getDate();
    return { start_date: `${filterMonth.value}-01`, end_date: `${filterMonth.value}-${lastDay}` };
  }
  if (viewScope.value === "weekly" && filterWeek.value) {
    const [yearStr, weekStr] = filterWeek.value.split("-W");
    const y = parseInt(yearStr, 10);
    const w = parseInt(weekStr, 10);
    const simple = new Date(y, 0, 1 + (w - 1) * 7);
    const dow = simple.getDay();
    const weekStart = new Date(simple);
    if (dow <= 4) weekStart.setDate(simple.getDate() - simple.getDay() + 1);
    else weekStart.setDate(simple.getDate() + 8 - simple.getDay());
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const fmt = (d) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { start_date: fmt(weekStart), end_date: fmt(weekEnd) };
  }
  const day = filterOrderDate.value || frappe.datetime.get_today();
  return { start_date: day, end_date: day };
}

async function fetchMaintenanceRecords() {
  try {
    const { start_date, end_date } = getScopeDateRange();
    const res = await frappe.call({
      method: "production_scheduler.api.get_all_equipment_maintenance",
      args: { start_date, end_date },
    });
    const rows = (res?.message || []).filter((r) => (r.unit || "").trim() === "Lamination Unit");
    maintenanceRecords.value = rows;
    const mapped = {};
    rows.forEach((rec) => {
      const start = new Date(rec.start_date);
      const end = new Date(rec.end_date);
      for (let cur = new Date(start); cur <= end; cur.setDate(cur.getDate() + 1)) {
        const key = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, "0")}-${String(cur.getDate()).padStart(2, "0")}`;
        mapped[key] = rec.maintenance_type || "Machine Off";
      }
    });
    maintenanceByDate.value = mapped;
  } catch (e) {
    console.error("Failed to load lamination maintenance", e);
    maintenanceByDate.value = {};
  }
}

function maintenanceTypeForDate(dateValue) {
  const k = toDateKey(dateValue);
  return k ? maintenanceByDate.value[k] : "";
}

async function fetchLaminationSequences() {
  try {
    const { start_date, end_date } = getScopeDateRange();
    const res = await frappe.call({
      method: "production_scheduler.api.get_color_sequences_range",
      args: {
        start_date,
        end_date,
        unit: "Lamination Unit",
        plan_name: "Default",
      },
    });
    const store = {};
    const payload = res?.message || {};
    if (Array.isArray(payload)) {
      payload.forEach((rec) => {
        const d = toDateKey(rec?.date);
        if (!d) return;
        let seq = rec?.sequence_data || rec?.sequence || [];
        if (typeof seq === "string") {
          try {
            seq = JSON.parse(seq);
          } catch (e) {
            seq = [];
          }
        }
        if (Array.isArray(seq) && seq.length) {
          store[d] = seq.map((x) => String(x || "").trim()).filter(Boolean);
        }
      });
    } else if (payload && typeof payload === "object") {
      Object.entries(payload).forEach(([key, rec]) => {
        const parts = String(key || "").split("-");
        const d = parts.length >= 4 ? parts.slice(-3).join("-") : toDateKey(rec?.date);
        if (!d) return;
        let seq = rec?.sequence_data || rec?.sequence || [];
        if (typeof seq === "string") {
          try {
            seq = JSON.parse(seq);
          } catch (e) {
            seq = [];
          }
        }
        if (Array.isArray(seq) && seq.length) {
          store[d] = seq.map((x) => String(x || "").trim()).filter(Boolean);
        }
      });
    }
    laminationSequenceStore.value = store;
  } catch (e) {
    console.error("Failed to fetch lamination sequence", e);
    laminationSequenceStore.value = {};
  }
}

function toggleArrangementLock() {
  arrangementLocked.value = !arrangementLocked.value;
  frappe.show_alert(
    { message: arrangementLocked.value ? "Arrangement locked" : "Arrangement unlocked. Drag rows to reorder.", indicator: "blue" },
    2
  );
}

function reorderRowsInDate(sourceRow, targetRow) {
  const sourceDate = getRowDateKey(sourceRow);
  const targetDate = getRowDateKey(targetRow);
  if (!sourceDate || !targetDate || sourceDate !== targetDate) {
    frappe.show_alert({ message: "Reorder allowed only inside same date", indicator: "orange" }, 3);
    return;
  }
  const dayRows = filteredRows.value.filter((r) => getRowDateKey(r) === sourceDate);
  const seq = dayRows.map((r) => String(r.itemName || "").trim()).filter(Boolean);
  const sourceName = String(sourceRow?.itemName || "").trim();
  const targetName = String(targetRow?.itemName || "").trim();
  const fromIdx = seq.indexOf(sourceName);
  const toIdx = seq.indexOf(targetName);
  if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return;
  const [mv] = seq.splice(fromIdx, 1);
  seq.splice(toIdx, 0, mv);
  laminationSequenceStore.value = { ...laminationSequenceStore.value, [sourceDate]: seq };
  pendingArrangementUpdates.value[sourceDate] = seq;
  arrangementDirty.value = true;
}

function onOrderDragStart(row, ev) {
  if (!arrangementUnlocked.value) return;
  dragOrderRow.value = row;
  dragOverItemName.value = String(row?.itemName || "");
  try {
    if (ev?.dataTransfer) ev.dataTransfer.effectAllowed = "move";
  } catch (e) {}
}

function onOrderDragOver(row) {
  if (!arrangementUnlocked.value) return;
  dragOverItemName.value = String(row?.itemName || "");
}

function onOrderDragLeave(row) {
  if (dragOverItemName.value === String(row?.itemName || "")) {
    dragOverItemName.value = "";
  }
}

function onOrderDrop(row) {
  if (!arrangementUnlocked.value || !dragOrderRow.value) return;
  reorderRowsInDate(dragOrderRow.value, row);
  dragOrderRow.value = null;
  dragOverItemName.value = "";
}

function onOrderDragEnd() {
  dragOrderRow.value = null;
  dragOverItemName.value = "";
}

async function saveLaminationArrangement() {
  if (arrangementSaving.value) return;
  if (!arrangementDirty.value) {
    frappe.show_alert({ message: "No arrangement changes to save", indicator: "orange" }, 2);
    return;
  }
  arrangementSaving.value = true;
  try {
    for (const [dateKey, seq] of Object.entries(pendingArrangementUpdates.value || {})) {
      if (!Array.isArray(seq) || !seq.length) continue;
      await frappe.call({
        method: "production_scheduler.api.save_color_sequence",
        args: {
          date: dateKey,
          unit: "Lamination Unit",
          sequence_data: JSON.stringify(seq),
          plan_name: "Default",
        },
      });
    }
    pendingArrangementUpdates.value = {};
    arrangementDirty.value = false;
    frappe.show_alert({ message: "Lamination arrangement saved", indicator: "green" }, 3);
  } catch (e) {
    frappe.msgprint(`Failed to save arrangement: ${e?.message || e}`);
  } finally {
    arrangementSaving.value = false;
  }
}

async function restoreLaminationArrangement() {
  try {
    const { start_date, end_date } = getScopeDateRange();
    const start = new Date(start_date);
    const end = new Date(end_date);
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const dateKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      await frappe.call({
        method: "production_scheduler.api.restore_last_color_sequence",
        args: { date: dateKey, unit: "Lamination Unit", plan_name: "Default" },
      });
    }
    pendingArrangementUpdates.value = {};
    arrangementDirty.value = false;
    await fetchData();
    frappe.show_alert({ message: "Lamination arrangement restored", indicator: "green" }, 3);
  } catch (e) {
    frappe.msgprint(`Failed to restore arrangement: ${e?.message || e}`);
  }
}

function formatKg2(value) {
  const num = parseFloat(value || 0);
  if (!Number.isFinite(num)) return "0.00";
  return num.toFixed(2);
}

function formatNum(v) {
  const n = parseFloat(v || 0);
  if (!Number.isFinite(n)) return "0";
  return n.toFixed(0);
}

function sprPillLabel(item) {
  if (!item?.spr_name) return "";
  if (Number(item.spr_docstatus) === 0) return "Draft";
  if (Number(item.spr_docstatus) === 1) return "Submitted";
  return "SPR";
}

function sprPillClass(item) {
  if (!item?.spr_name) return "pt-pill-muted";
  if (Number(item.spr_docstatus) === 0) return "pt-pill-draft";
  if (Number(item.spr_docstatus) === 1) return "pt-pill-submitted";
  return "pt-pill-muted";
}

function sprPillTitle(item) {
  if (!item?.spr_name) return "";
  const id = item.spr_name || "";
  if (Number(item.spr_docstatus) === 0) return `Draft SPR ${id}`;
  if (Number(item.spr_docstatus) === 1) return `Submitted SPR ${id}`;
  return id;
}

function woPillLabelItem(item) {
  if (!item) return "";
  if (item.wo_terminal) return "WO done";
  if (item.wo_open) return "WO open";
  return "WO";
}

function woPillClassItem(item) {
  if (item.wo_terminal) return "pt-pill-wo-done";
  if (item.wo_open) return "pt-pill-wo-open";
  return "pt-pill-wo-unknown";
}

function woPillTitleItem(item) {
  if (!item) return "";
  if (item.wo_terminal) return "All work orders closed or terminal.";
  if (item.wo_open) return "At least one WO open.";
  return "WO status";
}

function itemProductionStatusLine(item) {
  if (!item) return "";
  const t = parseFloat(item.qty) || 0;
  const a = parseFloat(item.actual_production_weight_kgs) || 0;
  const gap = t - a;
  if (Math.abs(gap) <= 0.5) return "";
  return gap > 0 ? `${formatKg2(gap)} kg below target` : `${formatKg2(-gap)} kg over target`;
}

function itemSprPrimaryButtonLabel(item) {
  if (!item?.spr_name) return "";
  if (Number(item.spr_docstatus) === 0) return "Open draft SPR";
  if (item.wo_terminal) return "View SPR (done)";
  return "View SPR";
}

function itemSprPrimaryButtonTitle(item) {
  if (!item?.spr_name) return "";
  if (Number(item.spr_docstatus) === 0) return "Draft SPR - continue recording rolls.";
  if (item.wo_terminal) return "WO terminal - review only.";
  return "Open submitted SPR.";
}

function getItemDisplayName(item) {
  if (!item) return "-";
  return item.description || item.itemCode || item.item_code || item.itemName || "-";
}

function syncSprNameForSamePP(ppId, sprId, sourceItemName = "") {
  const pid = String(ppId || "").trim();
  const sid = String(sprId || "").trim();
  if (!pid || !sid) return;
  (rawData.value || []).forEach((row) => {
    if (
      String(row.pp_id || "").trim() === pid &&
      (!sourceItemName || String(row.itemName || "") === String(sourceItemName || ""))
    ) {
      row.spr_name = sid;
    }
  });
}

async function openProductionPlanView(planningSheetName, salesOrderItem = null, planningSheetItem = null, directPpId = null) {
  if (!planningSheetName) {
    frappe.msgprint("Planning Sheet not found");
    return;
  }
  let ppId = String(directPpId || "").trim();
  if (ppId) {
    const printUrl = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(ppId)}&format=${encodeURIComponent("Assembly Item - Raw Material")}&trigger_print=0`;
    window.open(printUrl, "_blank");
    return;
  }
  try {
    const res = await frappe.call({
      method: "production_scheduler.api.get_planning_sheet_pp_id",
      args: {
        planning_sheet_name: planningSheetName,
        sales_order_item: salesOrderItem,
        planning_sheet_item: planningSheetItem,
      },
    });
    if (res.message && res.message.status === "ok") {
      ppId = String(res.message.pp_id || "").trim();
      if (ppId) {
        const printUrl = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(ppId)}&format=${encodeURIComponent("Assembly Item - Raw Material")}&trigger_print=0`;
        window.open(printUrl, "_blank");
      } else {
        frappe.msgprint("No Production Plan found");
      }
    } else {
      frappe.msgprint(res.message?.message || "Error");
    }
  } catch (e) {
    frappe.msgprint("Error opening Production Plan");
  }
}

function handleStockEntryAction(item) {
  if (!item) return;
  const isDraftSpr = !!item.spr_name && Number(item.spr_docstatus) === 0;
  if (isDraftSpr) {
    openItemSPR(item.spr_name, item);
    return;
  }
  createItemStockEntry(item);
}

function openItemSPR(sprName, item = null) {
  if (!sprName) {
    frappe.msgprint("No SPR linked");
    return;
  }
  frappe.call({
    method: "frappe.client.get",
    args: { doctype: "Shaft Production Run", name: sprName },
    callback: (r) => {
      if (r.message) {
        frappe.set_route("Form", "Shaft Production Run", sprName);
      } else if (item) {
        item.spr_name = "";
        frappe.show_alert({ message: "SPR was deleted.", indicator: "orange" }, 3);
        createItemStockEntry(item);
      } else {
        frappe.msgprint("SPR not found");
      }
    },
  });
}

async function createItemStockEntry(item) {
  if (item.__creating_spr) return;
  if (!item.pp_id && item.planningSheet) {
    try {
      const ppRes = await frappe.call({
        method: "production_scheduler.api.get_planning_sheet_pp_id",
        args: {
          planning_sheet_name: item.planningSheet,
          sales_order_item: item.salesOrderItem || null,
          planning_sheet_item: item.itemName || null,
        },
      });
      if (ppRes.message && ppRes.message.status === "ok" && ppRes.message.pp_id) {
        item.pp_id = ppRes.message.pp_id;
      }
    } catch (e) {}
  }
  if (!item.pp_id) {
    frappe.msgprint("No Production Plan linked");
    return;
  }
  if (!item.itemName) {
    frappe.msgprint("Planning row name missing");
    return;
  }
  const itemDisplay = getItemDisplayName(item);
  frappe.confirm(
    `Create Stock Entry for <b>${item.partyCode}</b> (${item.color})?<br/>PP: ${item.pp_id}<br/>Item: ${itemDisplay}`,
    async () => {
      item.__creating_spr = true;
      try {
        const res = await frappe.call({
          method: "production_scheduler.api.create_item_spr",
          args: {
            pp_id: item.pp_id,
            planning_sheet_item_names: JSON.stringify([item.itemName]),
          },
        });
        if (res.message && res.message.status === "ok") {
          const sprId = res.message.spr_id;
          item.spr_name = sprId;
          syncSprNameForSamePP(item.pp_id, sprId, item.itemName);
          frappe.flags.spr_show_wo_popup = item.pp_id;
          frappe.show_alert({ message: `SPR: ${sprId}`, indicator: "green" }, 3);
          setTimeout(() => frappe.set_route("Form", "Shaft Production Run", sprId), 600);
        } else {
          frappe.msgprint(res.message?.message || "Failed to create SPR");
        }
      } catch (e) {
        frappe.msgprint(`Error: ${e.message || e}`);
      } finally {
        item.__creating_spr = false;
      }
    }
  );
}

function goToBoard() {
  frappe.set_route("lamination-board");
}

function toggleViewScope() {
  if (viewScope.value === "monthly" && !filterMonth.value) {
    filterMonth.value = frappe.datetime.get_today().substring(0, 7);
  } else if (viewScope.value === "weekly" && !filterWeek.value) {
    const d = new Date();
    const dStart = new Date(d.getFullYear(), 0, 1);
    const days = Math.floor((d - dStart) / (24 * 60 * 60 * 1000));
    const weekNum = Math.ceil(days / 7);
    filterWeek.value = `${d.getFullYear()}-W${String(weekNum).padStart(2, "0")}`;
  }
  updateUrlParams();
  fetchData();
}

/** VALIDATION: Check if parent WO can be started */
function canStartWO(item) {
  if (!item) return false;
  if (!item.is_lamination_parent) return false;
  if (!item.pp_id) return false;
  if (Number(item.pp_docstatus) !== 1) return false;
  if (item.parent_wo_terminal) return false;

  // CRITICAL: Child items must have completed WO and submitted SPR
  if (!item.parent_ready_for_wo) return false;

  return true;
}

/** Get reason why Start WO is blocked */
function getStartWOBlockedReason(item) {
  if (!item) return "No data";
  if (!item.is_lamination_parent) return "Not parent";
  if (!item.pp_id) return "No PP";
  if (Number(item.pp_docstatus) !== 1) return "PP Draft";
  if (item.parent_wo_terminal) return "WO closed";
  if (!item.parent_ready_for_wo) return "Complete child WO";
  return "Cannot start";
}

/** Get title for Start WO button */
function getStartWOTitle(item) {
  if (!item.parent_wo_name && Number(item.parent_wo_docstatus || 0) === 0 && !item.parent_wo_warehouse_set) {
    return "Create Work Order draft and set source warehouse";
  }
  if (Number(item.parent_wo_docstatus || 0) === 0 && item.parent_wo_warehouse_set) {
    return "Submit Work Order to start production";
  }
  return "Start Work Order";
}

function canShowStockEntry(item) {
  if (!item || !item.pp_id) return false;
  if (item.is_lamination_parent && !item.parent_wo_started) return false;
  if (item.is_lamination_parent && Number(item.parent_wo_docstatus || 0) !== 1) return false;
  if (!item.wo_open && !item.wo_terminal) return false;
  if (item.is_lamination_parent && !item.parent_ready_for_wo) return false;
  if (Number(item.pp_docstatus) !== 1) return false;
  const pendingQty = Number(item.pp_pending_qty ?? item.pending_qty ?? item.item_pending_qty ?? 0);
  if (!(pendingQty > 0)) return false;
  const targetKg = Number(item.qty ?? 0);
  const actualKg = Number(item.actual_production_weight_kgs ?? item.total_achieved_weight_kgs ?? 0);
  if (targetKg > 0 && actualKg >= targetKg - 1e-6) return false;
  if (item.wo_terminal) return false;
  return true;
}

/** Open existing Work Order for editing */
function openParentWO(item) {
  const woName = String(item?.parent_wo_name || "").trim();
  if (!woName) return;
  frappe.set_route("Form", "Work Order", woName);
}

/** Start or submit Work Order */
async function startParentWO(item) {
  if (!item?.itemName) return;
  try {
    const submitExisting = item.parent_wo_name && Number(item.parent_wo_docstatus || 0) === 0 && item.parent_wo_warehouse_set;
    const res = await frappe.call({
      method: "production_scheduler.api.start_lamination_parent_wo",
      args: { item_name: item.itemName, submit_existing: submitExisting ? 1 : 0 },
    });
    const msg = res?.message || {};
    if (msg.status === "ok") {
      if (msg.draft && msg.wo_name && !submitExisting) {
        frappe.show_alert({ message: `WO draft created: ${msg.wo_name}. Set source warehouse then come back to Start WO.`, indicator: "blue" }, 6);
        frappe.set_route("Form", "Work Order", msg.wo_name);
      } else if (msg.started) {
        frappe.show_alert({ message: `WO started: ${msg.wo_name}`, indicator: "green" }, 4);
      } else if (msg.wo_name) {
        frappe.show_alert({ message: `WO: ${msg.wo_name}`, indicator: "green" }, 4);
      }
      await fetchData();
      return;
    }
    frappe.msgprint(msg.message || "Unable to start WO");
  } catch (e) {
    frappe.msgprint(`Failed to start WO: ${e?.message || e}`);
  }
}

/** Save produced fabric weight */
async function saveProducedWeight(row) {
  if (!row.itemName) return;
  try {
    await frappe.call({
      method: "production_scheduler.api.update_lamination_produced_weight",
      args: {
        item_name: row.itemName,
        produced_fabric_weight_kg: Number(row.produced_fabric_weight_kg || 0),
      },
    });
    frappe.show_alert({ message: "Produced weight saved", indicator: "green" }, 2);
  } catch (e) {
    frappe.msgprint(`Failed to save weight: ${e?.message || e}`);
    row.produced_fabric_weight_kg = 0;
  }
}

function getStockEntryLabel(item) {
  if (!item) return "New SPR";
  const isDraftSpr = !!item.spr_name && Number(item.spr_docstatus) === 0;
  return isDraftSpr ? "Continue SPR" : "New SPR";
}

function getStockEntryTitle(item) {
  if (!item) return "Create Shaft Production Run";
  const isDraftSpr = !!item.spr_name && Number(item.spr_docstatus) === 0;
  const pendingQty = Number(item.pending_qty || 0);
  if (isDraftSpr) return `Continue draft SPR. Pending: ${pendingQty.toFixed(0)} Kg`;
  return `New SPR. Pending: ${pendingQty.toFixed(0)} Kg`;
}

async function fetchData() {
  try {
    let args = { party_code: filterPartyCode.value, planned_only: 1 };
    if (viewScope.value === "monthly") {
      if (!filterMonth.value) return;
      const [year, month] = filterMonth.value.split("-");
      const lastDay = new Date(year, month, 0).getDate();
      args.start_date = `${filterMonth.value}-01`;
      args.end_date = `${filterMonth.value}-${lastDay}`;
    } else if (viewScope.value === "weekly") {
      if (!filterWeek.value) return;
      const [yearStr, weekStr] = filterWeek.value.split("-W");
      const y = parseInt(yearStr, 10);
      const w = parseInt(weekStr, 10);
      const simple = new Date(y, 0, 1 + (w - 1) * 7);
      const dow = simple.getDay();
      const ISOweekStart = new Date(simple);
      if (dow <= 4) ISOweekStart.setDate(simple.getDate() - simple.getDay() + 1);
      else ISOweekStart.setDate(simple.getDate() + 8 - simple.getDay());
      const ISOweekEnd = new Date(ISOweekStart);
      ISOweekEnd.setDate(ISOweekEnd.getDate() + 6);
      const fmt = (d) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      args.start_date = fmt(ISOweekStart);
      args.end_date = fmt(ISOweekEnd);
    } else {
      args.date = filterOrderDate.value;
    }

    const r = await frappe.call({
      method: "production_scheduler.api.get_lamination_order_table_data",
      args,
    });
    rawData.value = (r.message || []).map((d) => ({
      ...d,
      salesOrderItem: d.salesOrderItem || d.sales_order_item || "",
      produced_fabric_weight_kg: d.produced_fabric_weight_kg || 0,
    }));
    if (!initialFetchRetried && (!rawData.value || rawData.value.length === 0)) {
      initialFetchRetried = true;
      setTimeout(() => fetchData(), 450);
    }
    await fetchLaminationSequences();
    await fetchMaintenanceRecords();
  } catch (e) {
    console.error(e);
    frappe.msgprint("Error loading lamination order table");
  }
}

function updateUrlParams() {
  const q = new URLSearchParams();
  if (viewScope.value === "daily") q.set("date", filterOrderDate.value);
  if (viewScope.value === "weekly") q.set("week", filterWeek.value);
  if (viewScope.value === "monthly") q.set("month", filterMonth.value);
  q.set("scope", viewScope.value);
  window.history.replaceState({}, "", `${window.location.pathname}?${q.toString()}`);
}

function openMachineOffDialog() {
  const d = new frappe.ui.Dialog({
    title: "Lamination Machine Off",
    fields: [
      { fieldtype: "Date", fieldname: "start_date", label: "From Date", reqd: 1, default: filterOrderDate.value || frappe.datetime.get_today() },
      { fieldtype: "Date", fieldname: "end_date", label: "To Date", reqd: 1, default: filterOrderDate.value || frappe.datetime.get_today() },
      {
        fieldtype: "Select",
        fieldname: "maintenance_type",
        label: "Type",
        options: "Machine Off\nBreakdown - Full\nBreakdown - Partial\nEB Shutdown\nMesh Change\nDie Change",
        default: "Machine Off",
        reqd: 1,
      },
      { fieldtype: "Small Text", fieldname: "notes", label: "Notes" },
    ],
    primary_action_label: "Save",
    primary_action: async (vals) => {
      try {
        const res = await frappe.call({
          method: "production_scheduler.api.add_lamination_machine_off",
          args: {
            start_date: vals.start_date,
            end_date: vals.end_date,
            maintenance_type: vals.maintenance_type,
            notes: vals.notes || "",
          },
        });
        if (res?.message?.status === "success") {
          frappe.show_alert({ message: res.message.message || "Lamination maintenance saved", indicator: "green" }, 4);
          d.hide();
          await fetchMaintenanceRecords();
          await fetchData();
        } else {
          frappe.msgprint(res?.message?.message || "Failed to save maintenance.");
        }
      } catch (e) {
        frappe.msgprint(`Error saving maintenance: ${e?.message || e}`);
      }
    },
  });
  d.show();
}

function openAssignShiftDialog() {
  const d = new frappe.ui.Dialog({
    title: "Assign Lamination Shift",
    fields: [
      { fieldname: "shift_date", label: "Planned Date", fieldtype: "Date", reqd: 1, default: filterOrderDate.value || frappe.datetime.get_today() },
      { fieldname: "shift_label", label: "Shift", fieldtype: "Select", options: "DAY\nNIGHT", reqd: 1, default: "DAY" },
    ],
    primary_action_label: "Apply",
    primary_action: async (vals) => {
      try {
        if (maintenanceTypeForDate(vals.shift_date)) {
          frappe.msgprint(`Cannot assign shift on ${vals.shift_date}. Machine is OFF.`);
          return;
        }
        const res = await frappe.call({
          method: "production_scheduler.api.assign_lamination_shift",
          args: { shift_date: vals.shift_date, shift_label: vals.shift_label },
        });
        const msg = res?.message || {};
        frappe.show_alert(
          { message: `Shift ${msg.shift || vals.shift_label} applied to ${msg.updated_count || 0} order(s)`, indicator: "green" },
          5
        );
        d.hide();
        if (viewScope.value === "daily") filterOrderDate.value = vals.shift_date;
        await fetchData();
      } catch (e) {
        frappe.msgprint(`Failed to assign shift: ${e?.message || e}`);
      }
    },
  });
  d.show();
}

watch([filterOrderDate, filterWeek, filterMonth], () => {
  if (!filtersReady.value) return;
  if (viewScope.value === "daily" && filterOrderDate.value) {
    moveTargetDate.value = toDateKey(filterOrderDate.value) || moveTargetDate.value;
  }
  updateUrlParams();
  fetchData();
});

onMounted(async () => {
  const p = new URLSearchParams(window.location.search);
  if (p.get("scope")) viewScope.value = p.get("scope");
  if (p.get("date")) filterOrderDate.value = p.get("date");
  if (p.get("week")) filterWeek.value = p.get("week");
  if (p.get("month")) filterMonth.value = p.get("month");
  await fetchData();
  moveTargetDate.value = toDateKey(filterOrderDate.value) || frappe.datetime.get_today();
  updateUrlParams();
  filtersReady.value = true;
});
</script>

<style scoped>
.cc-container {
  display: flex;
  flex-direction: column;
  padding: 16px;
  background-color: #f3f4f6;
  min-height: 100vh;
}
.cc-filters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 12px;
  align-items: end;
  margin-bottom: 12px;
  padding: 12px 14px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
}
.cc-filter-title {
  grid-column: 1 / -1;
  padding: 8px 0 4px;
  font-weight: 700;
  color: #047857;
  font-size: 15px;
}
.cc-select-scope {
  font-weight: 700;
  color: #047857;
  min-height: 34px;
}
.cc-shift-btns {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.cc-shift-btns button {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}
.cc-shift-btns button.active {
  background: #047857;
  color: #fff;
  border-color: #047857;
}
.cc-filter-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-end;
  justify-content: flex-end;
  grid-column: 1 / -1;
}
.cc-filter-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cc-filter-item label {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
}
.cc-clear-btn,
.cc-maint-btn,
.cc-view-btn {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}
.cc-maint-btn {
  background: #fff7ed;
  border-color: #fdba74;
  color: #9a3412;
  font-weight: 700;
}
.cc-view-btn {
  background: #3b82f6;
  color: #fff;
  border-color: #2563eb;
}
.cc-table-container {
  background: #fff;
  border-radius: 8px;
  overflow: auto;
  border: 1px solid #e5e7eb;
}
.cc-table-unit-header {
  padding: 12px 16px;
  background: #fcd34d;
  font-weight: 700;
  color: #78350f;
}
.lot-header {
  font-size: 14px;
}
.cc-prod-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.lot-table thead tr {
  background: #065f46;
  color: #fff;
  font-weight: 700;
  font-size: 11px;
  text-transform: uppercase;
}
.lot-table th {
  padding: 8px;
  text-align: left;
  white-space: nowrap;
}
.th-n {
  width: 40px;
  text-align: center;
}
.lot-table td {
  padding: 8px;
  border-bottom: 1px solid #f3f4f6;
}
.lot-table tbody tr:hover {
  background: #f8fafc;
}
.cell-center {
  text-align: center;
}
.cell-right {
  text-align: right;
}
.font-bold {
  font-weight: 700;
}
.font-mono {
  font-family: monospace;
}
.cc-drag-handle {
  display: inline-block;
  cursor: grab;
  color: #cbd5e1;
  font-weight: 700;
}
.cc-lock-hint {
  color: #cbd5e1;
  font-size: 14px;
}
.cc-maint-chip {
  display: inline-block;
  background: #fee2e2;
  color: #991b1b;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  margin-left: 4px;
}
.cc-pp-btn {
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #f0f9ff;
  color: #0369a1;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  transition: all 0.2s;
  margin: 2px;
}
.cc-pp-btn:hover {
  background: #e0f2fe;
  border-color: #0284c7;
}
.pt-btn-entry {
  background: #dcfce7;
  color: #166534;
  border-color: #86efac;
}
.pt-btn-entry:hover {
  background: #bbf7d0;
  border-color: #34d399;
}
.pt-spr-btn-draft {
  background: #f3f4f6;
  color: #475569;
}
.pt-spr-btn-submitted {
  background: #fef3c7;
  color: #92400e;
}
.pt-spr-btn-done {
  background: #d1fae5;
  color: #065f46;
}
.pt-pill-wo-done {
  background: #d1fae5;
  color: #065f46;
}
.pt-pill-wo-open {
  background: #fef3c7;
  color: #92400e;
}
.pt-pill-wo-unknown {
  background: #f3f4f6;
  color: #475569;
}
.pt-no-pp-hint {
  color: #999;
  font-size: 11px;
}
.pt-wo-closed-hint {
  color: #666;
  font-size: 11px;
  font-weight: 500;
}
.cc-row-draggable {
  cursor: move;
}
.cc-row-drag-over {
  background: #e0f2fe !important;
  border-top: 2px solid #0284c7;
}
.pt-action-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
}
</style>
