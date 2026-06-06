<template>
  <div class="sequence-approval-container ta-transfer ta-despatch">
    <div class="dashboard-header">
      <div class="header-left">
        <h2>Despatch Approvals Dashboard</h2>
        <p class="text-muted">Review batches, net weight, order code and customer — approve then create Delivery Note from Logistics or here.</p>
      </div>
      <div class="header-right" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: flex-end">
        <div class="status-filter-row" aria-label="Filter by status">
          <button type="button" class="pill" :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">All</button>
          <button type="button" class="pill" :class="{ active: statusFilter === 'pending' }" @click="statusFilter = 'pending'">Pending</button>
          <button type="button" class="pill" :class="{ active: statusFilter === 'draft' }" @click="statusFilter = 'draft'">Draft</button>
          <button type="button" class="pill" :class="{ active: statusFilter === 'approved' }" @click="statusFilter = 'approved'">Approved</button>
          <button type="button" class="pill" :class="{ active: statusFilter === 'rejected' }" @click="statusFilter = 'rejected'">Rejected</button>
        </div>
        <div class="ta-date-filter">
          <label>From</label>
          <input v-model="fromDate" type="date" />
          <label>To</label>
          <input v-model="toDate" type="date" />
          <input v-model="orderFilter" type="text" placeholder="Order code" @keyup.enter="loadList" />
        </div>
        <button type="button" class="btn btn-primary btn-sm" @click="loadList">
          <i class="fa fa-refresh"></i> Refresh
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <div class="spinner-border text-primary" role="status"></div>
      <p class="mt-3">Loading despatch approvals…</p>
    </div>

    <div v-else-if="!filteredList.length" class="empty-state">
      <div class="empty-icon">📦</div>
      <template v-if="!list.length">
        <h3>No despatch approvals yet</h3>
        <p>Submit despatch from Logistics Kanban (Despatch mode).</p>
      </template>
      <template v-else>
        <h3>No despatch requests match this filter</h3>
        <p>Try <strong>All</strong> or switch status.</p>
      </template>
    </div>

    <div v-else class="approval-layout">
      <div class="approval-sidebar">
        <div class="sidebar-header">
          <span class="badge badge-pill badge-info" style="background: #f1f5f9; color: #475569">
            {{ filteredList.length }} shown · {{ list.length }} total
          </span>
        </div>
        <div
          v-for="item in filteredList"
          :key="item.name"
          :class="['approval-card', { active: selected?.name === item.name }]"
          @click="select(item)"
        >
          <div class="card-title">
            <span class="plan-badge">{{ item.from_company || item.name }}</span>
          </div>
          <div class="card-details">
            <span class="date">{{ item.from_company }}</span>
            <span :class="['status-badge', statusSlug(item.status)]">{{ item.status }}</span>
          </div>
          <div v-if="item.order_codes_label" class="ta-card-nature">Order Code {{ item.order_codes_label }}</div>
          <div v-if="item.despatch_date" class="ta-card-date">{{ formatDate(item.despatch_date) }}</div>
          <div v-if="item.customers_label" class="ta-card-nature">{{ item.customers_label }}</div>
        </div>
      </div>

      <div class="approval-editor" v-if="selected">
        <div class="editor-header">
          <div>
            <h3>Despatch — {{ selected.from_company }}</h3>
            <p class="mb-0 text-muted" style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center">
              <span><strong>From company:</strong> {{ selected.from_company }}</span>
              <span v-if="selected.customers_label"><strong>Customer:</strong> {{ selected.customers_label }}</span>
              <span v-if="selected.order_codes_label"><strong>Order Code:</strong> {{ selected.order_codes_label }}</span>
              <span v-if="selected.owner"><i class="fa fa-user-circle"></i> {{ selected.owner }}</span>
            </p>
          </div>
          <div class="editor-actions" style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
            <template v-if="canAct && isPending(selected.status)">
              <button type="button" class="btn btn-secondary btn-lg" :disabled="busy || !lines.length" @click="saveLineOrder">
                <i class="fa fa-save"></i> Save order
              </button>
              <button type="button" class="btn btn-primary btn-lg" :disabled="busy" @click="approve">
                {{ busy ? "Processing…" : "✅ Approve" }}
              </button>
              <button type="button" class="btn btn-danger btn-lg" :disabled="busy" @click="reject">
                <i class="fa fa-times"></i> Reject
              </button>
            </template>
            <div v-else-if="selected.status === 'Approved'" class="status-indicator" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
              <span class="status-badge-lg approved"><i class="fa fa-check-circle"></i> {{ dnStatusLabel }}</span>
              <button
                v-if="dnDocstatus < 1"
                type="button"
                class="btn btn-success btn-lg"
                :disabled="busy"
                @click="openDeliveryNoteFlow"
              >
                {{ dnButtonLabel }}
              </button>
              <a v-else href="#" class="btn btn-default btn-lg" @click.prevent="openDn(selected.delivery_note)">
                Open {{ selected.delivery_note }}
              </a>
            </div>
            <div v-else-if="selected.status === 'Rejected'" class="status-indicator">
              <span class="status-badge-lg rejected"><i class="fa fa-times-circle"></i> REJECTED</span>
            </div>
          </div>
        </div>

        <div class="editor-info" v-if="canAct && isPending(selected.status)">
          <i class="fa fa-info-circle"></i>
          <span>Drag rows to set despatch queue order. After approve, use Create Delivery Note on Logistics company card or here.</span>
        </div>

        <div v-if="selected.delivery_note" class="ta-ste-banner">
          Delivery Note:
          <a href="#" @click.prevent="openDn(selected.delivery_note)">{{ selected.delivery_note }}</a>
        </div>

        <div class="sequence-list" v-if="lines.length">
          <div class="list-header">
            <div class="col-drag"></div>
            <div class="col-idx">#</div>
            <div class="col-party">Order Code</div>
            <div class="col-color">Customer</div>
            <div class="col-quality">Item / Batch</div>
            <div class="col-qty text-right">Net / Qty (Kg)</div>
          </div>
          <div class="draggable-container" ref="dragContainer">
            <div v-for="(ln, index) in lines" :key="ln.name" class="sequence-item" :data-id="ln.name">
              <div class="col-drag draggable-handle" v-if="canAct && isPending(selected.status)">⠿</div>
              <div class="col-drag" v-else></div>
              <div class="col-idx">{{ index + 1 }}</div>
              <div class="col-party"><b>{{ ln.party_code }}</b></div>
              <div class="col-color">
                <b>{{ ln.customer_name }}</b>
                <div class="sub-text text-muted">{{ ln.spr_name }}</div>
              </div>
              <div class="col-quality">
                {{ ln.item_code }}
                <div class="sub-text text-muted mono">{{ ln.batch_no }}</div>
              </div>
              <div class="col-qty text-right font-weight-bold">{{ formatQty(ln.net_weight || ln.qty) }}</div>
            </div>
          </div>
          <div class="list-footer">
            <div class="col-total-label">Total qty</div>
            <div class="col-total-val text-right">{{ formatQty(totalQty) }} Kg</div>
          </div>
        </div>
        <p v-else class="ta-empty-lines">No lines on this despatch.</p>

        <button type="button" class="btn btn-default btn-sm ta-open-form" @click="openForm(selected.name)">Open form</button>
      </div>

      <div class="editor-placeholder" v-else>
        <div class="placeholder-content">
          <i class="fa fa-mouse-pointer mb-3" style="font-size: 40px; color: #cbd5e1"></i>
          <p>Select a despatch request from the sidebar to review and approve.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";

const API = "production_entry.production_planning.despatch_logistics";
const APPROVER_ROLES = ["System Manager", "Manufacturing Manager", "Administrator"];

const loading = ref(false);
const busy = ref(false);
const statusFilter = ref("pending");
const fromDate = ref(frappe.datetime.get_today());
const toDate = ref(frappe.datetime.get_today());
const orderFilter = ref("");
const list = ref([]);
const selected = ref(null);
const lines = ref([]);
const dragContainer = ref(null);
let sortableInstance = null;
const lineOrderDirty = ref(false);

const canAct = computed(() => {
  const roles = frappe.user_roles || [];
  return roles.some((r) => APPROVER_ROLES.includes(r));
});

function statusSlug(s) {
  return String(s || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-");
}

function isPending(status) {
  return status === "Pending Approval" || status === "Draft";
}

function matchesFilter(item) {
  const f = statusFilter.value;
  if (f === "all") return true;
  const st = String(item.status || "").trim();
  if (f === "pending") return isPending(st);
  if (f === "draft") return st === "Draft";
  if (f === "approved") return st === "Approved";
  if (f === "rejected") return st === "Rejected";
  return true;
}

const filteredList = computed(() => (list.value || []).filter(matchesFilter));

const totalQty = computed(() => {
  const s = lines.value.reduce((a, ln) => a + (parseFloat(ln.net_weight || ln.qty) || 0), 0);
  return Math.round(s * 1000) / 1000;
});

const dnDocstatus = computed(() => parseInt(selected.value?.dn_docstatus, 10) || 0);

const dnStatusLabel = computed(() => {
  if (dnDocstatus.value >= 1) return "DESPATCHED";
  if (selected.value?.delivery_note) return "DRAFT DN";
  return "APPROVED";
});

const dnButtonLabel = computed(() => {
  if (selected.value?.delivery_note) return __("Open Draft DN");
  return __("Create Delivery Note");
});

function formatQty(q) {
  const n = parseFloat(q);
  return Number.isFinite(n) ? (Math.round(n * 1000) / 1000).toString() : "0";
}

function formatDate(d) {
  if (!d) return "";
  try {
    return frappe.datetime.str_to_user(d);
  } catch {
    return String(d).slice(0, 10);
  }
}

async function loadList() {
  loading.value = true;
  try {
    const args = {
      status_filter: statusFilter.value || "all",
      limit: 300,
      from_date: fromDate.value || "",
      to_date: toDate.value || "",
      order_code: (orderFilter.value || "").trim(),
    };
    const r = await frappe.call({
      method: `${API}.get_despatch_approvals`,
      args,
    });
    list.value = r.message || [];
    if (selected.value) {
      const hit = list.value.find((x) => x.name === selected.value.name);
      if (hit) {
        selected.value = hit;
      } else {
        selected.value = null;
        lines.value = [];
        destroySortable();
      }
    }
  } finally {
    loading.value = false;
  }
}

function destroySortable() {
  if (sortableInstance) {
    sortableInstance.destroy();
    sortableInstance = null;
  }
}

function initSortable() {
  destroySortable();
  if (!dragContainer.value || !selected.value || !isPending(selected.value.status) || !canAct.value) return;
  if (typeof Sortable === "undefined") return;
  sortableInstance = new Sortable(dragContainer.value, {
    handle: ".draggable-handle",
    animation: 150,
    ghostClass: "ghost-item",
    chosenClass: "chosen-item",
    onEnd() {
      const newOrder = Array.from(dragContainer.value.querySelectorAll(".sequence-item"))
        .map((el) => el.getAttribute("data-id"))
        .filter(Boolean);
      const byName = Object.fromEntries(lines.value.map((ln) => [ln.name, ln]));
      lines.value = newOrder.map((nm) => byName[nm]).filter(Boolean);
      lineOrderDirty.value = true;
    },
  });
}

async function select(item) {
  selected.value = item;
  lineOrderDirty.value = false;
  destroySortable();
  const r = await frappe.call({
    method: `${API}.get_despatch_approval_detail`,
    args: { name: item.name },
  });
  const doc = r.message || {};
  lines.value = doc.lines || [];
  selected.value = { ...item, ...doc };
  await nextTick();
  initSortable();
}

async function saveLineOrder() {
  if (!selected.value || !lineOrderDirty.value) {
    frappe.show_alert({ message: __("Order saved"), indicator: "blue" });
    return;
  }
  busy.value = true;
  try {
    await frappe.call({
      method: `${API}.reorder_despatch_approval_lines`,
      args: {
        name: selected.value.name,
        line_names: JSON.stringify(lines.value.map((ln) => ln.name)),
      },
    });
    lineOrderDirty.value = false;
    frappe.show_alert({ message: __("Line order saved"), indicator: "green" });
  } finally {
    busy.value = false;
  }
}

function approve() {
  if (!selected.value) return;
  frappe.confirm(
    __("Approve despatch from <b>{0}</b> for order(s) <b>{1}</b>?", [
      selected.value.from_company,
      selected.value.order_codes_label || "—",
    ]),
    async () => {
      if (lineOrderDirty.value) await saveLineOrder();
      busy.value = true;
      try {
        await frappe.call({
          method: `${API}.approve_despatch_approval`,
          args: { name: selected.value.name },
        });
        frappe.show_alert({ message: __("Despatch approved"), indicator: "green" });
        await loadList();
        const hit = list.value.find((x) => x.name === selected.value?.name);
        if (hit) await select(hit);
      } finally {
        busy.value = false;
      }
    }
  );
}

async function openDeliveryNoteFlow() {
  if (!selected.value) return;
  if (selected.value.delivery_note) {
    openDn(selected.value.delivery_note);
    return;
  }
  busy.value = true;
  try {
    const r = await frappe.call({
      method: `${API}.prepare_delivery_note_from_despatch_approval`,
      args: { name: selected.value.name },
    });
    const msg = r.message || {};
    if (msg.mode === "existing" && msg.delivery_note) {
      openDn(msg.delivery_note);
      return;
    }
    if (msg.mode !== "new" || !msg.doc) {
      frappe.msgprint(__("Could not open Delivery Note."));
      return;
    }
    frappe.set_route("List", "Delivery Note");
  } finally {
    busy.value = false;
  }
}

function openDn(name) {
  frappe.set_route("Form", "Delivery Note", name);
}

function reject() {
  if (!selected.value) return;
  frappe.confirm(__("Reject this despatch request?"), async () => {
    busy.value = true;
    try {
      await frappe.call({
          method: `${API}.reject_despatch_approval`,
        args: { name: selected.value.name },
      });
      frappe.show_alert({ message: __("Rejected"), indicator: "orange" });
      await loadList();
      const still = list.value.find((x) => x.name === selected.value?.name);
      if (still) await select(still);
    } finally {
      busy.value = false;
    }
  });
}


function openForm(name) {
  frappe.set_route("Form", "Despatch Approval", name);
}

watch(statusFilter, () => {
  loadList();
  if (selected.value && !filteredList.value.find((x) => x.name === selected.value.name)) {
    selected.value = null;
    lines.value = [];
    destroySortable();
  }
});

onMounted(() => {
  const opts = frappe.route_options || {};
  if (opts.status_filter) statusFilter.value = opts.status_filter;
  if (opts.order_code) orderFilter.value = opts.order_code;
  if (opts.from_date) fromDate.value = opts.from_date;
  if (opts.to_date) toDate.value = opts.to_date;
  loadList().then(() => {
    const pick = opts.name || opts.approval;
    if (pick) {
      const hit = list.value.find((x) => x.name === pick);
      if (hit) select(hit);
    }
  });
});
</script>

<style scoped>
.ta-transfer .ta-card-nature {
  font-size: 10px;
  color: #0369a1;
  font-weight: 700;
  margin-top: 4px;
}
.ta-transfer .ta-card-date {
  font-size: 10px;
  color: #64748b;
  font-weight: 700;
  margin-top: 3px;
}
.ta-date-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}
.ta-date-filter label {
  margin: 0;
  font-size: 11px;
  font-weight: 800;
  color: #64748b;
}
.ta-date-filter input {
  height: 28px;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  padding: 3px 8px;
  font-size: 12px;
}
.ta-date-filter input[type="text"] {
  width: 110px;
}
.ta-ste-banner {
  padding: 10px 24px;
  background: #f0fdf4;
  border-bottom: 1px solid #bbf7d0;
  font-size: 13px;
  font-weight: 600;
}
.ta-ste-banner a {
  color: #15803d;
  font-weight: 800;
}
.ta-empty-lines {
  padding: 24px;
  color: #94a3b8;
  text-align: center;
}
.ta-open-form {
  margin: 12px 24px 20px;
}
.mono {
  font-family: ui-monospace, monospace;
}
/* Reuse sequence approval layout (global scheduler.css + SequenceApproval styles) */
.sequence-approval-container {
  padding: 24px;
  background: #f1f5f9;
  min-height: calc(100vh - 80px);
  font-family: system-ui, sans-serif;
}
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  gap: 16px;
  flex-wrap: wrap;
}
.dashboard-header h2 {
  margin: 0;
  font-weight: 800;
  color: #0f172a;
}
.pill {
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
}
.pill.active {
  background: #1e293b;
  color: #fff;
  border-color: #1e293b;
}
.approval-layout {
  display: flex;
  gap: 20px;
  height: calc(100vh - 200px);
}
.approval-sidebar {
  width: 320px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  overflow-y: auto;
  padding: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.approval-card {
  padding: 14px;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
  cursor: pointer;
  margin-bottom: 6px;
  transition: all 0.15s ease;
}
.approval-card:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
}
.approval-card.active {
  background: #eff6ff;
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.12);
}
.plan-badge {
  font-size: 11px;
  font-weight: 800;
  color: #0f172a;
}
.card-details {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  margin-top: 6px;
  gap: 6px;
}
.date {
  color: #64748b;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
.status-badge {
  padding: 2px 8px;
  border-radius: 20px;
  font-weight: 800;
  font-size: 9px;
  text-transform: uppercase;
  flex-shrink: 0;
}
.status-badge.pending-approval,
.status-badge.draft {
  background: #fefce8;
  color: #854d0e;
  border: 1px solid #fef08a;
}
.status-badge.approved {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}
.status-badge.rejected {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}
.approval-editor {
  flex: 1;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}
.editor-header {
  padding: 20px 24px;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.editor-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
}
.editor-info {
  padding: 10px 24px;
  background: #f0f9ff;
  color: #0369a1;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.sequence-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px;
}
.list-header {
  display: flex;
  padding: 12px 0;
  border-bottom: 2px solid #f1f5f9;
  font-size: 10px;
  font-weight: 800;
  color: #94a3b8;
  text-transform: uppercase;
}
.sequence-item {
  display: flex;
  padding: 14px 0;
  border-bottom: 1px solid #f8fafc;
  align-items: center;
  font-size: 14px;
}
.col-drag {
  width: 36px;
  text-align: center;
  color: #cbd5e1;
  cursor: grab;
  font-size: 18px;
}
.col-idx {
  width: 36px;
  text-align: center;
  color: #94a3b8;
  font-weight: 700;
  font-size: 12px;
}
.col-party {
  width: 100px;
  color: #1e40af;
  font-weight: 700;
}
.col-color {
  flex: 1.2;
}
.col-quality {
  flex: 1.5;
  color: #64748b;
  font-size: 13px;
}
.col-qty {
  width: 90px;
}
.list-footer {
  display: flex;
  padding: 16px 0;
  border-top: 2px solid #0f172a;
  margin-top: 8px;
  font-weight: 800;
}
.col-total-label {
  flex: 1;
  padding-left: 72px;
  font-size: 14px;
  text-transform: uppercase;
}
.col-total-val {
  width: 120px;
  font-size: 16px;
}
.sub-text {
  font-size: 10px;
  margin-top: 2px;
}
.text-right {
  text-align: right;
}
.ghost-item {
  opacity: 0.4;
  background: #eff6ff !important;
  border: 1px dashed #3b82f6;
}
.chosen-item {
  background: #f8fafc;
}
.status-badge-lg {
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: 800;
  font-size: 14px;
}
.status-badge-lg.approved {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}
.status-badge-lg.rejected {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}
.loading-state,
.empty-state,
.editor-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  color: #64748b;
  min-height: 320px;
}
.empty-icon {
  font-size: 56px;
  margin-bottom: 16px;
  opacity: 0.5;
}
</style>
