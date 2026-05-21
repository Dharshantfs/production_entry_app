<template>
  <div class="ta-container">
    <div class="ta-header">
      <div class="ta-header-left">
        <h2>Transfer Approvals</h2>
        <p class="ta-sub">Review inter-company transfers and approve or reject (creates draft Stock Entry on approve).</p>
      </div>
      <div class="ta-header-right">
        <div class="ta-pills">
          <button type="button" class="pill" :class="{ active: statusFilter === 'all' }" @click="setFilter('all')">All</button>
          <button type="button" class="pill" :class="{ active: statusFilter === 'pending' }" @click="setFilter('pending')">Pending</button>
          <button type="button" class="pill" :class="{ active: statusFilter === 'approved' }" @click="setFilter('approved')">Approved</button>
          <button type="button" class="pill" :class="{ active: statusFilter === 'rejected' }" @click="setFilter('rejected')">Rejected</button>
        </div>
        <button type="button" class="cc-clear-btn" @click="loadList"><i class="fa fa-refresh"></i> Refresh</button>
      </div>
    </div>

    <div v-if="loading" class="ta-muted ta-loading">Loading transfers…</div>

    <div v-else-if="!filteredList.length" class="ta-empty">
      <template v-if="!list.length">No transfer approvals yet.</template>
      <template v-else>No items match this filter.</template>
    </div>

    <div v-else class="ta-layout">
      <div class="ta-sidebar">
        <div class="ta-sidebar-meta">{{ filteredList.length }} shown · {{ list.length }} total</div>
        <div
          v-for="item in filteredList"
          :key="item.name"
          class="ta-card"
          :class="{ active: selected?.name === item.name }"
          @click="select(item)"
        >
          <div class="ta-card-title">{{ item.to_destination_label || item.name }}</div>
          <div class="ta-card-meta">{{ item.from_company }} → {{ item.to_company }}</div>
          <span :class="['ta-status', statusClass(item.status)]">{{ item.status }}</span>
        </div>
      </div>

      <div class="ta-detail" v-if="selected">
        <div class="ta-detail-head">
          <div>
            <h3>{{ selected.to_destination_label }}</h3>
            <p class="ta-detail-meta">
              {{ selected.from_company }} → {{ selected.to_company }}
              <span v-if="selected.owner"> · Requested by {{ selected.owner }}</span>
            </p>
          </div>
          <div class="ta-detail-actions" v-if="canAct && isPending(selected.status)">
            <button type="button" class="btn-approve" :disabled="busy" @click="approve">
              {{ busy ? "Processing…" : "✅ Approve & Create STE" }}
            </button>
            <button type="button" class="btn-reject" :disabled="busy" @click="reject">
              <i class="fa fa-times"></i> Reject
            </button>
          </div>
          <div v-else-if="selected.status === 'Approved'" class="ta-badge-lg approved">APPROVED</div>
          <div v-else-if="selected.status === 'Rejected'" class="ta-badge-lg rejected">REJECTED</div>
        </div>

        <table class="ta-table" v-if="lines.length">
          <thead>
            <tr>
              <th>Order</th>
              <th>Customer</th>
              <th>Item</th>
              <th>Batch</th>
              <th>Qty (Kg)</th>
              <th>SPR</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ln in lines" :key="ln.name">
              <td>{{ ln.party_code }}</td>
              <td>{{ ln.customer_name }}</td>
              <td>{{ ln.item_code }}</td>
              <td class="mono">{{ ln.batch_no }}</td>
              <td>{{ ln.qty }}</td>
              <td>{{ ln.spr_name }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="4" class="ta-total-label">Total qty</td>
              <td class="ta-total-val">{{ totalQty }} Kg</td>
              <td></td>
            </tr>
          </tfoot>
        </table>

        <p v-if="selected.stock_entry" class="ta-ste">
          Stock Entry:
          <a href="#" @click.prevent="openSte(selected.stock_entry)">{{ selected.stock_entry }}</a>
        </p>
        <button type="button" class="cc-clear-btn ta-open-form" @click="openForm(selected.name)">Open form</button>
      </div>

      <div v-else class="ta-detail ta-detail-placeholder">Select a transfer from the list.</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

const API = "production_entry.production_planning.transfer_logistics";
const APPROVER_ROLES = ["System Manager", "Manufacturing Manager", "Administrator"];

const loading = ref(false);
const busy = ref(false);
const statusFilter = ref("pending");
const list = ref([]);
const selected = ref(null);
const lines = ref([]);

const canAct = computed(() => {
  const roles = frappe.user_roles || [];
  return roles.some((r) => APPROVER_ROLES.includes(r));
});

const filteredList = computed(() => {
  const sf = statusFilter.value;
  if (sf === "all") return list.value;
  if (sf === "pending") {
    return list.value.filter((x) => isPending(x.status));
  }
  if (sf === "approved") return list.value.filter((x) => x.status === "Approved");
  if (sf === "rejected") return list.value.filter((x) => x.status === "Rejected");
  return list.value;
});

const totalQty = computed(() => {
  const s = lines.value.reduce((a, ln) => a + (parseFloat(ln.qty) || 0), 0);
  return Math.round(s * 1000) / 1000;
});

function isPending(status) {
  return status === "Pending Approval" || status === "Draft";
}

function statusClass(status) {
  if (status === "Approved") return "ok";
  if (status === "Rejected") return "bad";
  if (isPending(status)) return "pending";
  return "";
}

function setFilter(f) {
  statusFilter.value = f;
}

async function loadList() {
  loading.value = true;
  try {
    const r = await frappe.call({
      method: `${API}.get_transfer_approvals`,
      args: { status_filter: "all", limit: 300 },
    });
    list.value = r.message || [];
    if (selected.value) {
      const hit = list.value.find((x) => x.name === selected.value.name);
      if (hit) selected.value = hit;
      else {
        selected.value = null;
        lines.value = [];
      }
    }
  } finally {
    loading.value = false;
  }
}

async function select(item) {
  selected.value = item;
  const r = await frappe.call({
    method: `${API}.get_transfer_approval_detail`,
    args: { name: item.name },
  });
  lines.value = r.message?.lines || [];
}

function approve() {
  if (!selected.value) return;
  frappe.confirm(
    "Approve this transfer and create draft Stock Entry?",
    async () => {
      busy.value = true;
      try {
        const r = await frappe.call({
          method: `${API}.approve_transfer_approval`,
          args: { name: selected.value.name },
        });
        frappe.show_alert({
          message: `Approved — STE ${r.message?.stock_entry || ""}`,
          indicator: "green",
        });
        await loadList();
        if (r.message?.stock_entry) openSte(r.message.stock_entry);
        else if (selected.value) await select(selected.value);
      } finally {
        busy.value = false;
      }
    }
  );
}

function reject() {
  if (!selected.value) return;
  frappe.confirm("Reject this transfer request?", async () => {
    busy.value = true;
    try {
      await frappe.call({
        method: `${API}.reject_transfer_approval`,
        args: { name: selected.value.name },
      });
      frappe.show_alert({ message: "Rejected", indicator: "orange" });
      await loadList();
      const still = list.value.find((x) => x.name === selected.value?.name);
      if (still) await select(still);
    } finally {
      busy.value = false;
    }
  });
}

function openSte(name) {
  frappe.set_route("Form", "Stock Entry", name);
}

function openForm(name) {
  frappe.set_route("Form", "Transfer Approval", name);
}

onMounted(() => {
  loadList();
  const opts = frappe.route_options || {};
  if (opts.name) {
    setTimeout(async () => {
      await loadList();
      const hit = list.value.find((x) => x.name === opts.name);
      if (hit) select(hit);
    }, 400);
  }
});
</script>

<style scoped>
.ta-container {
  padding: 24px;
  background: #f1f5f9;
  min-height: calc(100vh - 80px);
  font-family: system-ui, sans-serif;
}
.ta-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.ta-header h2 {
  margin: 0;
  font-weight: 800;
  color: #0f172a;
}
.ta-sub {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}
.ta-header-right {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.ta-pills .pill {
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
}
.ta-pills .pill.active {
  background: #1e293b;
  color: #fff;
  border-color: #1e293b;
}
.ta-layout {
  display: flex;
  gap: 20px;
  min-height: 420px;
  height: calc(100vh - 200px);
}
.ta-sidebar {
  width: 300px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow-y: auto;
  padding: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.ta-sidebar-meta {
  font-size: 11px;
  color: #64748b;
  padding: 6px 8px 10px;
  border-bottom: 1px solid #f1f5f9;
  margin-bottom: 8px;
}
.ta-card {
  padding: 14px;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
  cursor: pointer;
  margin-bottom: 6px;
  transition: all 0.15s ease;
}
.ta-card:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
}
.ta-card.active {
  background: #eff6ff;
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.12);
}
.ta-card-title {
  font-weight: 600;
  font-size: 13px;
}
.ta-card-meta {
  font-size: 11px;
  color: #64748b;
  margin: 4px 0;
}
.ta-status {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}
.ta-status.pending {
  color: #d97706;
}
.ta-status.ok {
  color: #15803d;
}
.ta-status.bad {
  color: #b91c1c;
}
.ta-detail {
  flex: 1;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 20px;
  overflow: auto;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.ta-detail-placeholder {
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ta-detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.ta-detail-head h3 {
  margin: 0;
  font-size: 18px;
}
.ta-detail-meta {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
}
.ta-detail-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.btn-approve {
  background: #16a34a;
  color: #fff;
  border: none;
  padding: 10px 18px;
  border-radius: 8px;
  font-weight: 700;
  cursor: pointer;
  font-size: 14px;
}
.btn-approve:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-reject {
  background: #dc2626;
  color: #fff;
  border: none;
  padding: 10px 18px;
  border-radius: 8px;
  font-weight: 700;
  cursor: pointer;
  font-size: 14px;
}
.btn-reject:disabled {
  opacity: 0.6;
}
.ta-badge-lg {
  padding: 8px 14px;
  border-radius: 8px;
  font-weight: 800;
  font-size: 12px;
}
.ta-badge-lg.approved {
  background: #dcfce7;
  color: #166534;
}
.ta-badge-lg.rejected {
  background: #fee2e2;
  color: #991b1b;
}
.ta-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.ta-table th,
.ta-table td {
  border: 1px solid #e2e8f0;
  padding: 8px;
  text-align: left;
}
.ta-table .mono {
  font-family: ui-monospace, monospace;
}
.ta-total-label {
  text-align: right;
  font-weight: 700;
}
.ta-total-val {
  font-weight: 700;
  color: #0369a1;
}
.ta-ste {
  margin-top: 12px;
  font-size: 13px;
}
.ta-open-form {
  margin-top: 12px;
}
.ta-muted {
  color: #64748b;
}
.ta-loading,
.ta-empty {
  padding: 40px;
  text-align: center;
  color: #64748b;
}
</style>
