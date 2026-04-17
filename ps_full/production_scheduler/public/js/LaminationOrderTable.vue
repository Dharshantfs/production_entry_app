<template>
  <div class="cc-container">
    <div class="cc-filters">
      <div class="cc-filter-title">Lamination Order Table</div>
      <div class="cc-filter-item">
        <label>View Scope</label>
        <select v-model="viewScope" @change="toggleViewScope" :disabled="isManufactureUser" class="cc-select-scope">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>
      <div class="cc-filter-item" v-if="viewScope === 'daily'">
        <label>Planned Date</label>
        <input type="date" v-model="filterOrderDate" :disabled="isManufactureUser" />
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
        <button type="button" class="cc-clear-btn" @click="fetchData">Refresh</button>
        <button type="button" class="cc-view-btn" @click="goToBoard">Back to Lamination Board</button>
      </div>
    </div>

    <div class="cc-table-container">
      <div class="cc-table-unit-header lot-header">Lamination Unit — Planned orders (104)</div>
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
            <th style="min-width:90px;">PRODUCTION PLAN</th>
            <th style="min-width:128px;">SPR / WO</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in filteredRows" :key="row.itemName || idx">
            <td class="cell-center">{{ idx + 1 }}</td>
            <td class="cell-center">{{ formatDate(row.plannedDate || row.planned_date) }}</td>
            <td class="cell-center">{{ row.shift_label || "DAY" }}</td>
            <td class="cell-center font-mono font-bold" style="font-size:11px;color:#047857;">{{ row.lamination_booking_id || "—" }}</td>
            <td>{{ row.customer_name || row.customer || row.partyCode }}</td>
            <td class="cell-center">{{ row.quality }}</td>
            <td class="cell-center font-bold">{{ row.color }}</td>
            <td class="cell-center">{{ row.fabric_gsm || "—" }}</td>
            <td class="cell-center">{{ row.lamination_gsm ?? row.gsm }}</td>
            <td class="cell-right">{{ row.planned_meter ?? "—" }}</td>
            <td class="cell-right">{{ formatNum(row.achieved_meter) }}</td>
            <td class="cell-right">{{ formatKg2(row.actual_production_weight_kgs) }}</td>
            <td class="cell-center">
              <button v-if="row.pp_id" type="button" @click="openProductionPlanView(row.planningSheet, row.salesOrderItem, row.itemName, row.pp_id || '')" class="cc-pp-btn">📋 View</button>
              <span v-else class="pt-no-pp-hint">No PP</span>
            </td>
            <td class="cell-center">
              <div class="pt-stock-cell">
                <div v-if="row.pp_id" class="pt-pill-row">
                  <span v-if="row.spr_name" class="pt-pill" :class="sprPillClass(row)" :title="sprPillTitle(row)">{{ sprPillLabel(row) }}</span>
                  <span v-else class="pt-pill pt-pill-muted">SPR: —</span>
                  <span class="pt-pill pt-pill-wo" :class="woPillClassItem(row)" :title="woPillTitleItem(row)">{{ woPillLabelItem(row) }}</span>
                </div>
                <div v-if="itemProductionStatusLine(row)" class="pt-prod-status-line">{{ itemProductionStatusLine(row) }}</div>
                <button
                  v-if="canShowStockEntry(row)"
                  type="button"
                  @click="handleStockEntryAction(row)"
                  class="cc-pp-btn pt-btn-entry"
                  :title="getStockEntryTitle(row)"
                >{{ getStockEntryLabel(row) }}</button>
                <button
                  v-else-if="row.spr_name"
                  type="button"
                  @click="openItemSPR(row.spr_name, row)"
                  class="cc-pp-btn pt-btn-entry"
                  :class="Number(row.spr_docstatus) === 1 && row.wo_terminal ? 'pt-spr-btn-done' : Number(row.spr_docstatus) === 1 ? 'pt-spr-btn-submitted' : 'pt-spr-btn-draft'"
                  :title="itemSprPrimaryButtonTitle(row)"
                >{{ itemSprPrimaryButtonLabel(row) }}</button>
                <span v-else-if="row.pp_id && Number(row.pp_docstatus) !== 1" class="pt-wo-closed-hint">PP Draft</span>
                <span v-else-if="row.pp_id && row.wo_terminal" class="pt-wo-closed-hint">✅ WO closed</span>
                <span v-else style="color:#999;font-size:10px;">No PP</span>
              </div>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td colspan="14" class="cell-center" style="padding:24px;color:#64748b;">No lamination orders for this view.</td>
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
/** Client-side filter: server rows use shift_label DAY/NIGHT when available */
const filterShift = ref("all");
const rawData = ref([]);
const isManufactureUser = ref(false);
const filtersReady = ref(false);
let fetchTimer = null;

function detectRestrictedUser() {
  try {
    const RESTRICTED = ["Manufacture User", "Manufacturing User"];
    if (frappe?.user_roles) {
      return RESTRICTED.some((r) => (frappe.user_roles || []).includes(r));
    }
  } catch (e) {}
  return false;
}

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
  return d;
});

function debouncedFetch() {
  if (fetchTimer) clearTimeout(fetchTimer);
  fetchTimer = setTimeout(() => fetchData(), 200);
}

function formatDate(d) {
  if (!d) return "—";
  try {
    if (frappe.datetime && frappe.datetime.format_date) {
      return frappe.datetime.format_date(d);
    }
  } catch (e) {}
  return d;
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
  if (Number(item.spr_docstatus) === 0) return "Draft SPR — continue recording rolls.";
  if (item.wo_terminal) return "WO terminal — review only.";
  return "Open submitted SPR.";
}

function canShowStockEntry(item) {
  if (!item || !item.pp_id) return false;
  if (Number(item.pp_docstatus) !== 1) return false;
  const pendingQty = Number(item.pp_pending_qty ?? item.pending_qty ?? item.item_pending_qty ?? 0);
  if (!(pendingQty > 0)) return false;
  const targetKg = Number(item.qty ?? 0);
  const actualKg = Number(item.actual_production_weight_kgs ?? item.total_achieved_weight_kgs ?? 0);
  if (targetKg > 0 && actualKg >= targetKg - 1e-6) return false;
  if (item.wo_terminal) return false;
  return true;
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
  if (isManufactureUser.value) {
    viewScope.value = "daily";
    filterOrderDate.value = frappe.datetime.get_today();
    return;
  }
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
    }));
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

watch([filterOrderDate, filterWeek, filterMonth], () => {
  if (!filtersReady.value) return;
  updateUrlParams();
  fetchData();
});

onMounted(async () => {
  isManufactureUser.value = detectRestrictedUser();
  if (isManufactureUser.value) {
    viewScope.value = "daily";
    filterOrderDate.value = frappe.datetime.get_today();
  } else {
    const p = new URLSearchParams(window.location.search);
    if (p.get("scope")) viewScope.value = p.get("scope");
    if (p.get("date")) filterOrderDate.value = p.get("date");
    if (p.get("week")) filterWeek.value = p.get("week");
    if (p.get("month")) filterMonth.value = p.get("month");
  }
  await fetchData();
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
.cc-view-btn {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
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
.lot-header {
  padding: 10px 12px;
  font-weight: 700;
  background: #d1fae5;
  color: #065f46;
  border-bottom: 1px solid #6ee7b7;
}
.cc-prod-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.cc-prod-table th {
  background: #047857;
  color: #fff;
  padding: 8px 6px;
  text-align: left;
  font-weight: 700;
  white-space: nowrap;
}
.cc-prod-table td {
  border-bottom: 1px solid #e5e7eb;
  padding: 8px 6px;
  vertical-align: middle;
}
.th-n {
  width: 48px;
  text-align: center;
}
.cell-center {
  text-align: center;
}
.cell-right {
  text-align: right;
}
.cc-pp-btn {
  padding: 4px 8px;
  font-size: 11px;
  border-radius: 6px;
  border: 1px solid #6366f1;
  background: #eef2ff;
  color: #3730a3;
  cursor: pointer;
}
.pt-no-pp-hint {
  font-size: 10px;
  color: #94a3b8;
}
.pt-stock-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}
.pt-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}
.pt-pill {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 999px;
  font-weight: 700;
}
.pt-pill-muted {
  background: #f1f5f9;
  color: #64748b;
}
.pt-pill-draft {
  background: #fef3c7;
  color: #92400e;
}
.pt-pill-submitted {
  background: #d1fae5;
  color: #065f46;
}
.pt-pill-wo {
  background: #e0e7ff;
  color: #3730a3;
}
.pt-pill-wo-done {
  background: #dcfce7;
  color: #166534;
}
.pt-pill-wo-open {
  background: #ffedd5;
  color: #9a3412;
}
.pt-pill-wo-unknown {
  background: #f1f5f9;
  color: #475569;
}
.pt-prod-status-line {
  font-size: 9px;
  color: #64748b;
}
.pt-btn-entry {
  margin-top: 4px;
}
.pt-wo-closed-hint {
  font-size: 10px;
  color: #94a3b8;
}
.pt-spr-btn-draft {
  border-color: #f59e0b !important;
  background: #fffbeb !important;
}
.pt-spr-btn-submitted {
  border-color: #10b981 !important;
  background: #ecfdf5 !important;
}
.pt-spr-btn-done {
  border-color: #94a3b8 !important;
  background: #f8fafc !important;
}
.font-mono {
  font-family: ui-monospace, monospace;
}
</style>
