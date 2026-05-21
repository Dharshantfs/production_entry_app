<template>
  <div class="ta-container">
    <div class="ta-header">
      <h2>Transfer Approval</h2>
      <button type="button" class="cc-clear-btn" @click="loadList">Refresh</button>
    </div>
    <div class="ta-layout">
      <div class="ta-sidebar">
        <div
          v-for="item in list"
          :key="item.name"
          class="ta-card"
          :class="{ active: selected?.name === item.name }"
          @click="select(item)"
        >
          <div class="ta-card-title">{{ item.to_destination_label || item.name }}</div>
          <div class="ta-card-meta">{{ item.from_company }} → {{ item.to_company }}</div>
          <span class="ta-status">{{ item.status }}</span>
        </div>
        <p v-if="!list.length" class="ta-muted">No pending transfers.</p>
      </div>
      <div class="ta-detail" v-if="selected">
        <h3>{{ selected.to_destination_label }}</h3>
        <p>{{ selected.from_company }} → {{ selected.to_company }}</p>
        <table class="ta-table" v-if="lines.length">
          <thead>
            <tr>
              <th>Order</th>
              <th>Item</th>
              <th>Batch</th>
              <th>Qty</th>
              <th>SPR</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ln in lines" :key="ln.name">
              <td>{{ ln.party_code }}</td>
              <td>{{ ln.item_code }}</td>
              <td>{{ ln.batch_no }}</td>
              <td>{{ ln.qty }}</td>
              <td>{{ ln.spr_name }}</td>
            </tr>
          </tbody>
        </table>
        <div class="ta-actions" v-if="selected.status === 'Pending Approval'">
          <button type="button" class="cc-save-arrange-btn" :disabled="busy" @click="approve">Approve & create STE</button>
          <button type="button" class="cc-clear-btn" :disabled="busy" @click="reject">Reject</button>
        </div>
        <p v-if="selected.stock_entry" class="ta-muted">
          Stock Entry:
          <a href="#" @click.prevent="openSte(selected.stock_entry)">{{ selected.stock_entry }}</a>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const API = "production_entry.production_planning.transfer_logistics";
const list = ref([]);
const selected = ref(null);
const lines = ref([]);
const busy = ref(false);

async function loadList() {
  const r = await frappe.call({ method: `${API}.get_pending_transfer_approvals` });
  list.value = r.message || [];
}

async function select(item) {
  selected.value = item;
  const r = await frappe.call({ method: `${API}.get_transfer_approval_detail`, args: { name: item.name } });
  lines.value = r.message?.lines || [];
}

async function approve() {
  if (!selected.value) return;
  busy.value = true;
  try {
    const r = await frappe.call({
      method: `${API}.approve_transfer_approval`,
      args: { name: selected.value.name },
    });
    frappe.show_alert({ message: `Approved — STE ${r.message?.stock_entry || ""}`, indicator: "green" });
    await loadList();
    if (r.message?.stock_entry) openSte(r.message.stock_entry);
  } finally {
    busy.value = false;
  }
}

async function reject() {
  if (!selected.value) return;
  busy.value = true;
  try {
    await frappe.call({ method: `${API}.reject_transfer_approval`, args: { name: selected.value.name } });
    frappe.show_alert({ message: "Rejected", indicator: "orange" });
    selected.value = null;
    lines.value = [];
    await loadList();
  } finally {
    busy.value = false;
  }
}

function openSte(name) {
  frappe.set_route("Form", "Stock Entry", name);
}

loadList();
</script>

<style scoped>
.ta-container { padding: 16px; font-family: system-ui, sans-serif; }
.ta-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.ta-layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; min-height: 400px; }
.ta-sidebar { border: 1px solid #e2e8f0; border-radius: 8px; overflow: auto; max-height: 70vh; }
.ta-card { padding: 12px; border-bottom: 1px solid #f1f5f9; cursor: pointer; }
.ta-card.active { background: #eff6ff; }
.ta-card-title { font-weight: 600; font-size: 13px; }
.ta-card-meta { font-size: 11px; color: #64748b; }
.ta-status { font-size: 10px; color: #0ea5e9; }
.ta-detail { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
.ta-table { width: 100%; border-collapse: collapse; font-size: 12px; margin: 12px 0; }
.ta-table th, .ta-table td { border: 1px solid #e2e8f0; padding: 6px; }
.ta-actions { display: flex; gap: 10px; margin-top: 16px; }
.ta-muted { color: #64748b; font-size: 13px; }
</style>
