<template>
  <div class="lk-container">
    <div class="lk-hero">
      <div class="lk-hero-text">
        <h2>Logistics</h2>
        <p>Inter-company transfers and despatch lanes</p>
      </div>
      <div class="lk-truck-lane" aria-hidden="true">
        <div class="lk-road"></div>
        <div class="lk-truck">🚛</div>
      </div>
      <div class="lk-toggle">
        <button type="button" :class="{ active: mode === 'transfer' }" @click="mode = 'transfer'">Transfer</button>
        <button type="button" :class="{ active: mode === 'despatch' }" @click="mode = 'despatch'">Despatch</button>
      </div>
    </div>

    <template v-if="mode === 'transfer'">
      <div class="lk-toolbar">
        <label>From company</label>
        <select v-model="fromCompany" @change="loadCards" class="lk-select">
          <option value="">Select company…</option>
          <option v-for="c in companies" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <button type="button" class="lk-link-btn" @click="goApprovals">Transfer Approvals →</button>
      </div>

      <div v-if="!fromCompany" class="lk-hint">Select a company to see transfer destination cards.</div>

      <div v-else-if="!destinationCards.length" class="lk-hint">No destination companies configured.</div>

      <div v-else class="lk-grid">
        <button
          v-for="card in destinationCards"
          :key="card.company"
          type="button"
          class="lk-card"
          @click="openTransfer(card)"
        >
          <span class="lk-card-icon">📦</span>
          <span class="lk-card-title">{{ card.label }}</span>
          <span class="lk-card-sub">{{ card.company }}</span>
          <span class="lk-card-cta">Start transfer →</span>
        </button>
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
    />
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import TransferDialog from "./TransferDialog.vue";

const API = "production_entry.production_planning.transfer_logistics";
const mode = ref("transfer");
const companies = ref([]);
const fromCompany = ref("Jayashree Spun Bond - 1ZT");
const destinationCards = ref([]);
const showDialog = ref(false);
const dialogPrefill = ref({});
const dialogFilters = ref({ view_scope: "daily", date: frappe.datetime.get_today() });

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

function goApprovals() {
  frappe.set_route("transfer-approval");
}

watch(fromCompany, loadCards);
loadCompanies();
loadCards();
</script>

<style scoped>
.lk-container {
  padding: 20px 24px 32px;
  font-family: system-ui, sans-serif;
  background: linear-gradient(160deg, #f0f9ff 0%, #f8fafc 45%, #f1f5f9 100%);
  min-height: calc(100vh - 80px);
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
  color: #fff;
  box-shadow: 0 8px 24px rgba(3, 105, 161, 0.25);
  position: relative;
  overflow: hidden;
}
.lk-hero h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
}
.lk-hero p {
  margin: 4px 0 0;
  opacity: 0.9;
  font-size: 13px;
}
.lk-hero-text {
  flex: 1;
  min-width: 180px;
  z-index: 1;
}
.lk-truck-lane {
  position: relative;
  width: 140px;
  height: 36px;
  flex-shrink: 0;
  z-index: 1;
}
.lk-road {
  position: absolute;
  bottom: 6px;
  left: 0;
  right: 0;
  height: 4px;
  background: rgba(255, 255, 255, 0.35);
  border-radius: 2px;
}
.lk-truck {
  position: absolute;
  bottom: 8px;
  left: 0;
  font-size: 22px;
  line-height: 1;
  animation: lk-truck-drive 4s ease-in-out infinite;
  will-change: transform;
}
@keyframes lk-truck-drive {
  0%,
  100% {
    transform: translateX(0);
  }
  50% {
    transform: translateX(88px);
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
.lk-select {
  min-width: 280px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
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
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
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
.lk-grid-muted .lk-card-disabled {
  cursor: default;
  opacity: 0.75;
}
.lk-card-disabled:hover {
  transform: none;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
}
@media (prefers-reduced-motion: reduce) {
  .lk-truck {
    animation: none;
  }
}
</style>
