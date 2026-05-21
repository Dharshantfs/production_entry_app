<template>
  <div class="lk-container">
    <div class="lk-header">
      <h2>Logistics</h2>
      <div class="lk-toggle">
        <button type="button" :class="{ active: mode === 'transfer' }" @click="mode = 'transfer'">Transfer</button>
        <button type="button" :class="{ active: mode === 'despatch' }" @click="mode = 'despatch'">Despatch</button>
      </div>
    </div>

    <template v-if="mode === 'transfer'">
      <div class="lk-filters">
        <label>From company</label>
        <select v-model="fromCompany" @change="loadCards">
          <option value="">Select company…</option>
          <option v-for="c in companies" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
      </div>
      <div class="lk-cards" v-if="fromCompany">
        <div
          v-for="card in destinationCards"
          :key="card.company"
          class="lk-card"
          @click="openTransfer(card)"
        >
          <div class="lk-card-title">{{ card.label }}</div>
        </div>
      </div>
      <p v-else class="lk-muted">Select a company to see transfer destinations.</p>
    </template>

    <template v-else>
      <p class="lk-muted">Despatch — Delivery Note coming soon. Company lanes:</p>
      <div class="lk-cards">
        <div v-for="c in companies" :key="'d-' + c.name" class="lk-card lk-card-placeholder">
          <div class="lk-card-title">{{ c.name }}</div>
          <div class="lk-card-sub">Delivery Note — coming soon</div>
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

watch(fromCompany, loadCards);
loadCompanies();
loadCards();
</script>

<style scoped>
.lk-container { padding: 20px; font-family: system-ui, sans-serif; }
.lk-header { display: flex; align-items: center; gap: 20px; margin-bottom: 20px; }
.lk-toggle button {
  padding: 8px 16px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
}
.lk-toggle button.active { background: #0ea5e9; color: #fff; border-color: #0284c7; }
.lk-filters { margin-bottom: 16px; display: flex; gap: 10px; align-items: center; }
.lk-filters select { min-width: 280px; padding: 6px; }
.lk-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.lk-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  background: #f8fafc;
}
.lk-card:hover { border-color: #0ea5e9; background: #eff6ff; }
.lk-card-placeholder { cursor: default; opacity: 0.85; }
.lk-card-title { font-weight: 600; font-size: 14px; }
.lk-card-sub { font-size: 11px; color: #64748b; margin-top: 6px; }
.lk-muted { color: #64748b; }
</style>
