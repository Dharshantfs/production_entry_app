<template>
  <div class="lk-container" :class="{ 'lk-mode-transfer': mode === 'transfer', 'lk-mode-despatch': mode === 'despatch', 'lk-mounted': mounted }">
    <div class="lk-hero">
      <div class="lk-hero-text">
        <h2 class="lk-title">Logistics</h2>
        <p class="lk-subtitle">Inter-company transfers and despatch lanes</p>
      </div>
      <div class="lk-truck-scene" aria-hidden="true">
        <div class="lk-road"></div>
        <div class="lk-truck">🚛</div>
        <div class="lk-customer">🏭</div>
      </div>
      <div class="lk-toggle">
        <button type="button" :class="{ active: mode === 'transfer' }" @click="setMode('transfer')">Transfer</button>
        <button type="button" :class="{ active: mode === 'despatch' }" @click="setMode('despatch')">Despatch</button>
      </div>
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
import { onMounted, ref } from "vue";
import TransferDialog from "./TransferDialog.vue";

const API = "production_entry.production_planning.transfer_logistics";
const mode = ref("transfer");
const mounted = ref(false);
const historyFilter = ref("all");
const companies = ref([]);
const fromCompany = ref("Jayashree Spun Bond - 1ZT");
const destinationCards = ref([]);
const showDialog = ref(false);
const dialogPrefill = ref({});
const dialogFilters = ref({ view_scope: "daily", date: frappe.datetime.get_today() });

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

async function loadCompanies() {
  const r = await frappe.call({ method: `${API}.get_logistics_companies` });
  companies.value = r.message || [];
}

async function loadCards() {
  if (!fromCompany.value) {
    destinationCards.value = [];
    return;
  }
  const r = await frappe.call({
    method: `${API}.get_transfer_destination_cards`,
    args: { from_company: fromCompany.value },
  });
  destinationCards.value = r.message || [];
}

function openTransfer(card) {
  dialogPrefill.value = {
    from_company: fromCompany.value,
    to_company: card.company,
    party_code: "",
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

onMounted(() => {
  requestAnimationFrame(() => {
    mounted.value = true;
  });
  loadCompanies();
  loadCards();
});
</script>

<style scoped>
.lk-container {
  padding: 20px 24px 32px;
  font-family: system-ui, sans-serif;
  background: linear-gradient(160deg, #f0f9ff 0%, #f8fafc 45%, #f1f5f9 100%);
  min-height: calc(100vh - 80px);
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.35s ease, transform 0.35s ease;
}
.lk-container.lk-mounted {
  opacity: 1;
  transform: none;
}
.lk-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
  margin-bottom: 24px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #0c4a6e 0%, #0369a1 55%, #0ea5e9 100%);
  border-radius: 16px;
  color: #ffffff;
  box-shadow: 0 8px 24px rgba(3, 105, 161, 0.25);
  position: relative;
  overflow: hidden;
}
.lk-title {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  color: #ffffff;
  letter-spacing: -0.02em;
}
.lk-subtitle {
  margin: 6px 0 0;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  opacity: 0.95;
}
.lk-hero-text {
  flex: 1;
  min-width: 180px;
  z-index: 1;
}
.lk-truck-scene {
  position: relative;
  width: 200px;
  height: 40px;
  flex-shrink: 0;
  z-index: 1;
}
.lk-road {
  position: absolute;
  bottom: 4px;
  left: 0;
  right: 0;
  height: 4px;
  background: rgba(255, 255, 255, 0.35);
  border-radius: 2px;
}
.lk-truck {
  position: absolute;
  bottom: 10px;
  left: 0;
  font-size: 22px;
  line-height: 1;
  will-change: transform;
}
.lk-customer {
  position: absolute;
  bottom: 8px;
  right: 0;
  font-size: 20px;
  opacity: 0.85;
}
.lk-mode-despatch .lk-truck {
  animation: lk-truck-to-customer 5s ease-in-out infinite;
}
.lk-mode-transfer .lk-truck {
  animation: lk-truck-idle 3s ease-in-out infinite;
}
@keyframes lk-truck-to-customer {
  0%,
  100% {
    transform: translateX(0);
  }
  55% {
    transform: translateX(148px);
  }
}
@keyframes lk-truck-idle {
  0%,
  100% {
    transform: translateX(20px);
  }
  50% {
    transform: translateX(60px);
  }
}
.lk-toggle {
  display: flex;
  gap: 0;
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
.lk-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
}
.lk-toolbar label {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}
.lk-filter-label {
  margin-left: 8px;
}
.lk-select {
  min-width: 280px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
}
.lk-select-sm {
  min-width: 160px;
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
  font-size: 13px;
}
.lk-link-btn:hover {
  background: #eff6ff;
}
.lk-hint {
  color: #64748b;
  padding: 24px;
  text-align: center;
}
.lk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  align-items: start;
}
.lk-card-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  opacity: 0;
  animation: lk-card-in 0.4s ease forwards;
}
@keyframes lk-card-in {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
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
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.lk-card:hover {
  border-color: #0ea5e9;
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.15);
}
.lk-card-icon {
  font-size: 28px;
  line-height: 1;
}
.lk-card-title {
  font-weight: 700;
  font-size: 14px;
  color: #0f172a;
  margin-top: 4px;
}
.lk-card-sub {
  font-size: 11px;
  color: #64748b;
}
.lk-card-cta {
  margin-top: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #0284c7;
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
  letter-spacing: 0.04em;
}
.lk-history-chip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  text-align: left;
  border: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.lk-history-chip:last-child {
  margin-bottom: 0;
}
.lk-history-chip.is-draft {
  border-color: #fcd34d;
  background: #fffbeb;
}
.lk-history-chip.is-draft:hover {
  background: #fef3c7;
}
.lk-history-chip.is-done {
  border-color: #86efac;
  background: #f0fdf4;
}
.lk-history-chip.is-done:hover {
  background: #dcfce7;
}
.lk-history-badge {
  font-size: 9px;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.lk-history-chip.is-draft .lk-history-badge {
  background: #f59e0b;
  color: #fff;
}
.lk-history-chip.is-done .lk-history-badge {
  background: #16a34a;
  color: #fff;
}
.lk-history-main {
  flex: 1;
  min-width: 0;
}
.lk-history-ste {
  display: block;
  font-size: 12px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: #0f172a;
}
.lk-history-meta {
  display: block;
  font-size: 10px;
  color: #64748b;
  margin-top: 2px;
  line-height: 1.35;
}
.lk-history-go {
  font-size: 11px;
  font-weight: 700;
  color: #0284c7;
  flex-shrink: 0;
}
.lk-grid-muted .lk-card-disabled {
  cursor: default;
  opacity: 0.75;
}
@media (prefers-reduced-motion: reduce) {
  .lk-container,
  .lk-card-wrap,
  .lk-truck {
    animation: none !important;
    transition: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
</style>
