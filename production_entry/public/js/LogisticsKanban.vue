<template>
  <div
    class="lk-container"
    :class="{
      'lk-mode-transfer': mode === 'transfer',
      'lk-mode-despatch': mode === 'despatch',
      'lk-mounted': mounted,
      'lk-gate-open': gateOpen,
    }"
  >
    <div class="lk-gate lk-gate-left" aria-hidden="true"></div>
    <div class="lk-gate lk-gate-right" aria-hidden="true"></div>

    <div class="lk-hero">
      <div class="lk-hero-text">
        <h2 class="lk-title">Logistics</h2>
        <p class="lk-subtitle">Inter-company transfers and despatch lanes</p>
      </div>

      <!-- Transfer: move between two sites -->
      <div v-if="mode === 'transfer'" class="lk-truck-scene lk-scene-transfer" aria-hidden="true">
        <span class="lk-site lk-site-a">🏭</span>
        <div class="lk-road-transfer">
          <div class="lk-truck">🚛</div>
        </div>
        <span class="lk-site lk-site-b">🏢</span>
      </div>
      <!-- Despatch: truck to customer only -->
      <div v-else class="lk-truck-scene lk-scene-despatch" aria-hidden="true">
        <div class="lk-road-despatch">
          <div class="lk-truck">🚛</div>
        </div>
        <span class="lk-customer">🏭</span>
      </div>

      <div class="lk-toggle">
        <button type="button" :class="{ active: mode === 'transfer' }" @click="setMode('transfer')">Transfer</button>
        <button type="button" :class="{ active: mode === 'despatch' }" @click="setMode('despatch')">Despatch</button>
      </div>
    </div>

    <div class="lk-filters">
      <label>View</label>
      <select v-model="viewScope" @change="loadCards" class="lk-select lk-select-sm">
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
        <option value="all">All dates</option>
      </select>
      <template v-if="viewScope === 'daily'">
        <label>Date</label>
        <input type="date" v-model="filterDate" @change="loadCards" class="lk-input-date" />
      </template>
      <template v-else-if="viewScope === 'weekly'">
        <label>Week</label>
        <input type="week" v-model="filterWeek" @change="loadCards" class="lk-input-date" />
      </template>
      <template v-else-if="viewScope === 'monthly'">
        <label>Month</label>
        <input type="month" v-model="filterMonth" @change="loadCards" class="lk-input-date" />
      </template>
      <label>Order code</label>
      <input
        v-model="filterOrderCode"
        type="text"
        placeholder="Filter by order…"
        class="lk-input-text"
        @keyup.enter="loadCards"
      />
      <button type="button" class="cc-clear-btn" @click="loadCards">Apply</button>
    </div>

    <template v-if="mode === 'transfer'">
      <div class="lk-toolbar">
        <label>From company</label>
        <select v-model="fromCompany" @change="loadCards" class="lk-select">
          <option value="">Select company…</option>
          <option v-for="c in companies" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <label class="lk-filter-label">Show</label>
        <select v-model="historyFilter" class="lk-select lk-select-sm">
          <option value="all">All transfers</option>
          <option value="draft">Draft STE only</option>
          <option value="submitted">Submitted STE only</option>
        </select>
        <button type="button" class="lk-link-btn" @click="goApprovals">Transfer Approvals →</button>
      </div>

      <div v-if="!fromCompany" class="lk-hint">Select a company to see transfer destination cards.</div>
      <div v-else-if="!destinationCards.length" class="lk-hint">No destination companies configured.</div>

      <div v-else class="lk-grid">
        <div
          v-for="(card, idx) in destinationCards"
          :key="card.company"
          class="lk-card-wrap"
          :style="{ animationDelay: `${idx * 60}ms` }"
        >
          <button type="button" class="lk-card" @click="openTransfer(card)">
            <span class="lk-card-icon">📦</span>
            <span class="lk-card-title">{{ card.label }}</span>
            <span class="lk-card-sub">{{ card.company }}</span>
            <span class="lk-card-cta">Start transfer →</span>
          </button>

          <div v-if="filteredHistory(card).length" class="lk-history-panel">
            <div class="lk-history-head">Transfer history</div>
            <button
              v-for="ste in filteredHistory(card)"
              :key="ste.name"
              type="button"
              class="lk-history-chip"
              :class="ste.docstatus === 0 ? 'is-draft' : 'is-done'"
              @click="openSte(ste.name)"
            >
              <span class="lk-history-badge">{{ ste.status }}</span>
              <span class="lk-history-main">
                <span class="lk-history-ste">{{ ste.name }}</span>
                <span class="lk-history-meta">
                  <span v-if="ste.order_codes_label">Order {{ ste.order_codes_label }}</span>
                  <span v-if="ste.transfer_date"> · {{ formatDate(ste.transfer_date) }}</span>
                  <span v-if="ste.qty_total"> · {{ ste.qty_total }} Kg</span>
                </span>
              </span>
              <span class="lk-history-go">Open →</span>
            </button>
          </div>
          <p v-else class="lk-no-history">No transfers in this period.</p>
        </div>
      </div>
    </template>

    <template v-else>
      <p class="lk-hint">Despatch — Delivery Note coming soon.</p>
      <div class="lk-grid lk-grid-muted">
        <div v-for="c in companies" :key="'d-' + c.name" class="lk-card lk-card-disabled">
          <span class="lk-card-icon">🚚</span>
          <span class="lk-card-title">{{ c.name }}</span>
          <span class="lk-card-sub">Delivery Note — coming soon</span>
        </div>
      </div>
    </template>

    <TransferDialog
      v-model="showDialog"
      board-kind="production"
      :filter-context="dialogFilters"
      :prefill="dialogPrefill"
      @submitted="loadCards"
    />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import TransferDialog from "./TransferDialog.vue";

const API = "production_entry.production_planning.transfer_logistics";
const mode = ref("transfer");
const mounted = ref(false);
const gateOpen = ref(false);
const historyFilter = ref("all");
const viewScope = ref("daily");
const filterDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref("");
const filterOrderCode = ref("");
const companies = ref([]);
const fromCompany = ref("Jayashree Spun Bond - 1ZT");
const destinationCards = ref([]);
const showDialog = ref(false);
const dialogPrefill = ref({});
const dialogFilters = ref({ view_scope: "daily", date: frappe.datetime.get_today() });

function initWeekMonth() {
  const d = new Date();
  if (!filterWeek.value) {
    const onejan = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil(((d - onejan) / 86400000 + onejan.getDay() + 1) / 7);
    filterWeek.value = `${d.getFullYear()}-W${String(week).padStart(2, "0")}`;
  }
  if (!filterMonth.value) {
    filterMonth.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  }
}

function setMode(m) {
  mode.value = m;
}

function formatDate(d) {
  if (!d) return "";
  try {
    return frappe.datetime.str_to_user(d);
  } catch {
    return String(d).slice(0, 10);
  }
}

function filteredHistory(card) {
  const list = card.transfer_history || card.draft_stock_entries || [];
  if (historyFilter.value === "draft") {
    return list.filter((x) => x.docstatus === 0 || x.status === "Draft");
  }
  if (historyFilter.value === "submitted") {
    return list.filter((x) => x.docstatus === 1 || x.status === "Submitted");
  }
  return list;
}

function cardLoadArgs() {
  const args = { from_company: fromCompany.value };
  if (viewScope.value !== "all") {
    args.view_scope = viewScope.value;
    if (viewScope.value === "daily") args.date = filterDate.value;
    if (viewScope.value === "weekly") args.week = filterWeek.value;
    if (viewScope.value === "monthly") args.month = filterMonth.value;
  } else {
    args.view_scope = "all";
  }
  if ((filterOrderCode.value || "").trim()) {
    args.order_code = filterOrderCode.value.trim();
  }
  return args;
}

async function loadCompanies() {
  const r = await frappe.call({ method: `${API}.get_logistics_companies` });
  companies.value = r.message || [];
}

async function loadCards() {
  if (!fromCompany.value) {
    destinationCards.value = [];
    return;
  }
  dialogFilters.value = {
    view_scope: viewScope.value === "all" ? "daily" : viewScope.value,
    date: filterDate.value,
    week: filterWeek.value,
    month: filterMonth.value,
    party_code: filterOrderCode.value,
  };
  const r = await frappe.call({
    method: `${API}.get_transfer_destination_cards`,
    args: cardLoadArgs(),
  });
  destinationCards.value = r.message || [];
}

function openTransfer(card) {
  dialogPrefill.value = {
    from_company: fromCompany.value,
    to_company: card.company,
    party_code: filterOrderCode.value || "",
    customer: "",
  };
  showDialog.value = true;
}

function openSte(name) {
  frappe.set_route("Form", "Stock Entry", name);
}

function goApprovals() {
  frappe.set_route("transfer-approval");
}

watch(fromCompany, loadCards);

onMounted(() => {
  initWeekMonth();
  requestAnimationFrame(() => {
    mounted.value = true;
    setTimeout(() => {
      gateOpen.value = true;
    }, 80);
  });
  loadCompanies();
  loadCards();
});
</script>

<style scoped>
.lk-container {
  position: relative;
  padding: 20px 24px 32px;
  font-family: system-ui, sans-serif;
  background: linear-gradient(160deg, #f0f9ff 0%, #f8fafc 45%, #f1f5f9 100%);
  min-height: calc(100vh - 80px);
  opacity: 0;
  transform: translateY(10px);
  transition: opacity 0.4s ease, transform 0.4s ease;
  overflow: hidden;
}
.lk-container.lk-mounted {
  opacity: 1;
  transform: none;
}
.lk-gate {
  position: fixed;
  top: 0;
  bottom: 0;
  width: 0;
  background: linear-gradient(90deg, #0c4a6e, #0369a1);
  z-index: 9998;
  pointer-events: none;
  transition: width 0.55s cubic-bezier(0.4, 0, 0.2, 1);
}
.lk-gate-left {
  left: 0;
}
.lk-gate-right {
  right: 0;
}
.lk-container.lk-gate-open .lk-gate-left,
.lk-container.lk-gate-open .lk-gate-right {
  width: 0;
}
.lk-container:not(.lk-gate-open) .lk-gate-left,
.lk-container:not(.lk-gate-open) .lk-gate-right {
  width: 42vw;
}
.lk-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
  margin-bottom: 16px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #0c4a6e 0%, #0369a1 55%, #0ea5e9 100%);
  border-radius: 16px;
  color: #ffffff;
  box-shadow: 0 8px 24px rgba(3, 105, 161, 0.25);
  position: relative;
  z-index: 1;
  overflow: hidden;
}
.lk-title {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  color: #ffffff;
}
.lk-subtitle {
  margin: 6px 0 0;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
}
.lk-hero-text {
  flex: 1;
  min-width: 180px;
}
.lk-scene-transfer {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  width: 220px;
  min-height: 44px;
}
.lk-site {
  font-size: 22px;
  line-height: 1;
  opacity: 0.9;
}
.lk-road-transfer {
  position: relative;
  flex: 1;
  height: 28px;
  border-bottom: 3px solid rgba(255, 255, 255, 0.4);
}
.lk-scene-transfer .lk-truck {
  position: absolute;
  bottom: 6px;
  left: 0;
  font-size: 20px;
  animation: lk-transfer-lr 4s ease-in-out infinite;
}
@keyframes lk-transfer-lr {
  0%,
  100% {
    transform: translateX(0);
    opacity: 1;
  }
  48% {
    transform: translateX(calc(100% - 24px));
  }
  50% {
    transform: translateX(calc(100% - 24px)) scaleX(-1);
  }
  98% {
    transform: translateX(0) scaleX(-1);
  }
}
.lk-scene-despatch {
  position: relative;
  width: 200px;
  height: 40px;
}
.lk-road-despatch {
  position: absolute;
  bottom: 4px;
  left: 0;
  right: 36px;
  height: 4px;
  background: rgba(255, 255, 255, 0.35);
  border-radius: 2px;
}
.lk-scene-despatch .lk-truck {
  position: absolute;
  bottom: 8px;
  left: 0;
  font-size: 22px;
  animation: lk-despatch-to-customer 4.5s ease-in-out infinite;
}
.lk-customer {
  position: absolute;
  bottom: 6px;
  right: 0;
  font-size: 22px;
}
@keyframes lk-despatch-to-customer {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(140px);
  }
}
.lk-toggle {
  display: flex;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.35);
  z-index: 1;
}
.lk-toggle button {
  padding: 10px 20px;
  border: none;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}
.lk-toggle button.active {
  background: #fff;
  color: #0369a1;
}
.lk-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  position: relative;
  z-index: 1;
}
.lk-filters label {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
}
.lk-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  position: relative;
  z-index: 1;
}
.lk-toolbar label {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}
.lk-select {
  min-width: 260px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
}
.lk-select-sm {
  min-width: 150px;
}
.lk-input-date,
.lk-input-text {
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  font-size: 13px;
}
.lk-input-text {
  min-width: 140px;
}
.lk-link-btn {
  margin-left: auto;
  background: #fff;
  border: 1px solid #0ea5e9;
  color: #0369a1;
  padding: 8px 14px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}
.lk-hint,
.lk-no-history {
  color: #64748b;
  padding: 16px;
  text-align: center;
  font-size: 12px;
}
.lk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  position: relative;
  z-index: 1;
}
.lk-card-wrap {
  opacity: 0;
  animation: lk-card-in 0.45s ease forwards;
}
@keyframes lk-card-in {
  to {
    opacity: 1;
    transform: none;
  }
}
.lk-card {
  text-align: left;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 18px 16px;
  cursor: pointer;
  background: #fff;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.lk-card:hover {
  border-color: #0ea5e9;
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.12);
}
.lk-history-panel {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 10px;
}
.lk-history-head {
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  color: #64748b;
  margin-bottom: 8px;
}
.lk-history-chip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
  border: 1px solid #e2e8f0;
  background: #fff;
  text-align: left;
}
.lk-history-chip.is-draft {
  border-color: #fcd34d;
  background: #fffbeb;
}
.lk-history-chip.is-done {
  border-color: #86efac;
  background: #f0fdf4;
}
.lk-history-badge {
  font-size: 9px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
  color: #fff;
}
.lk-history-chip.is-draft .lk-history-badge {
  background: #f59e0b;
}
.lk-history-chip.is-done .lk-history-badge {
  background: #16a34a;
}
.lk-history-ste {
  font-size: 12px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
}
.lk-history-meta {
  font-size: 10px;
  color: #64748b;
  display: block;
  margin-top: 2px;
}
.lk-history-go {
  font-size: 11px;
  font-weight: 700;
  color: #0284c7;
}
@media (prefers-reduced-motion: reduce) {
  .lk-gate,
  .lk-truck,
  .lk-card-wrap,
  .lk-container {
    animation: none !important;
    transition: none !important;
  }
}
</style>
