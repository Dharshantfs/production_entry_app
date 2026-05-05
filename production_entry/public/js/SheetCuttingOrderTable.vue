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
      <div class="cc-filter-item">
        <label>Order Code</label>
        <input type="text" v-model="filterPartyCode" placeholder="Search..." @input="debouncedFetch" />
      </div>
      <div class="cc-filter-item">
        <label>Customer</label>
        <input type="text" v-model="filterCustomer" placeholder="Search..." @input="debouncedFetch" />
      </div>
      <div class="cc-filter-actions">
        <button type="button" class="cc-clear-btn" @click="fetchData">Refresh</button>
        <button type="button" class="cc-view-btn" @click="goToBoard">Back to Sheet Cutting Board</button>
      </div>
    </div>

    <div class="cc-table-container">
      <div class="cc-table-unit-header lot-header">JVE - SHEET CUTTING MACHINE - Planned orders (251)</div>
      <table class="cc-prod-table lot-table">
        <thead>
          <tr>
            <th class="th-n">S.NO</th>
            <th>DATE</th>
            <th>SHIFT</th>
            <th>CUSTOMER NAME</th>
            <th>QUALITY</th>
            <th>GSM</th>
            <th>ROLL SIZE</th>
            <th>MTR</th>
            <th>SHEET SIZE</th>
            <th>PLANNED QTY</th>
            <th>ACHIEVED QTY</th>
            <th>PER DAY PRODUCTION</th>
            <th style="min-width:90px;">PRODUCTION PLAN</th>
            <th style="min-width:110px;">SPR</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in filteredRows" :key="row.itemName || row.item_name || idx">
            <td class="cell-center">{{ idx + 1 }}</td>
            <td class="cell-center">{{ formatDate(row.plannedDate || row.planned_date) }}</td>
            <td class="cell-center">{{ row.shift_label || "DAY" }}</td>
            <td>{{ row.customer_name || row.customer || row.partyCode || row.party_code || "-" }}</td>
            <td class="cell-center">{{ row.quality || "-" }}</td>
            <td class="cell-center">{{ row.gsm || "-" }}</td>
            <td class="cell-center">{{ formatNum(row.roll_size) }}</td>
            <td class="cell-right">{{ formatNum(row.mtr) }}</td>
            <td class="cell-center">{{ row.sheet_size || "-" }}</td>
            <td class="cell-right">{{ formatNum(row.planned_quantity) }}</td>
            <td class="cell-right">{{ formatNum(row.achieved_quantity) }}</td>
            <td class="cell-right">{{ formatNum(row.per_day_production) }}</td>
            <td class="cell-center">
              <button v-if="row.pp_id && Number(row.pp_docstatus) === 1" type="button" class="cc-view-btn" @click="openProductionPlan(row.pp_id)">View</button>
              <span v-else-if="row.pp_id" class="muted">PP Draft</span>
              <span v-else class="muted">No PP</span>
            </td>
            <td class="cell-center">
              <button v-if="row.spr_name" type="button" class="cc-clear-btn" @click="openSPR(row.spr_name)">Open</button>
              <span v-else class="muted">-</span>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="14" class="cell-center" style="padding:24px;color:#64748b;">No sheet cutting orders for this view.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";

const filterOrderDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref("");
const viewScope = ref("daily");
const filterPartyCode = ref("");
const filterCustomer = ref("");
const rawData = ref([]);
let fetchTimer = null;

const filteredRows = computed(() => {
  let d = rawData.value || [];
  const pc = (filterPartyCode.value || "").trim().toLowerCase();
  const cu = (filterCustomer.value || "").trim().toLowerCase();
  if (pc) {
    d = d.filter((r) => String(r.partyCode || r.party_code || "").toLowerCase().includes(pc));
  }
  if (cu) {
    d = d.filter((r) => String(r.customer_name || r.customer || "").toLowerCase().includes(cu));
  }
  return d;
});

function formatDate(v) {
  if (!v) return "";
  return frappe.datetime.str_to_user(v);
}

function formatNum(v) {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(2).replace(/\.00$/, "");
}

function goToBoard() {
  frappe.set_route("sheet-cutting-board");
}

function openProductionPlan(ppId) {
  if (!ppId) return;
  frappe.set_route("Form", "Production Plan", ppId);
}

function openSPR(sprName) {
  if (!sprName) return;
  frappe.set_route("Form", "Shaft Production Run", sprName);
}

function debouncedFetch() {
  if (fetchTimer) clearTimeout(fetchTimer);
  fetchTimer = setTimeout(() => fetchData(), 300);
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

async function fetchData() {
  let args = { planned_only: 1 };
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
    const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    args.start_date = fmt(ISOweekStart);
    args.end_date = fmt(ISOweekEnd);
  } else {
    args.date = filterOrderDate.value;
  }

  try {
    const r = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.get_sheet_cutting_order_table_data",
      args,
    });
    rawData.value = (r.message || []).map((d) => ({
      ...d,
      itemName: d.itemName || d.item_name || "",
      plannedDate: d.plannedDate || d.planned_date || "",
    }));
  } catch (e) {
    console.error(e);
    frappe.msgprint(`Error loading Sheet Cutting Order Table: ${e?.message || e}`);
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

watch([filterOrderDate, filterWeek, filterMonth], () => {
  updateUrlParams();
  fetchData();
});

onMounted(async () => {
  const p = new URLSearchParams(window.location.search);
  if (p.get("scope")) viewScope.value = p.get("scope");
  if (p.get("date")) filterOrderDate.value = p.get("date");
  if (p.get("week")) filterWeek.value = p.get("week");
  if (p.get("month")) filterMonth.value = p.get("month");
  updateUrlParams();
  await fetchData();
});
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
  overflow: auto;
}
.cc-table-unit-header {
  padding: 10px 12px;
  border-bottom: 1px solid #e2e8f0;
  font-weight: 700;
  color: #065f46;
  background: #f8fafc;
}
.cc-prod-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1280px;
}
.cc-prod-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f1f5f9;
  color: #0f172a;
  border-bottom: 1px solid #cbd5e1;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .2px;
}
.cc-prod-table th,
.cc-prod-table td {
  padding: 8px 9px;
  border-bottom: 1px solid #f1f5f9;
  white-space: nowrap;
}
.cc-prod-table tbody tr:hover {
  background: #f8fafc;
}
.cell-center {
  text-align: center;
}
.cell-right {
  text-align: right;
}
.muted {
  color: #94a3b8;
  font-size: 12px;
}
</style>
