<template>
  <Teleport to="body">
    <div v-if="modelValue" class="tl-overlay" @click.self="close">
      <div class="tl-dialog" role="dialog" aria-modal="true" aria-labelledby="tl-transfer-title">
      <div class="tl-header">
        <h3 id="tl-transfer-title">Transfer rows</h3>
        <button type="button" class="tl-close" @click="close">✕</button>
      </div>
      <div class="tl-filters">
        <input v-model="dlgParty" type="text" placeholder="Filter order code" />
        <input v-model="dlgCustomer" type="text" placeholder="Filter customer" />
        <button type="button" class="cc-clear-btn" :disabled="loading" @click="loadRows">Refresh list</button>
      </div>
      <div class="tl-company-row">
        <label>From company</label>
        <select v-model="fromCompany" class="tl-select">
          <option value="">—</option>
          <option v-for="c in companies" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <label>To company</label>
        <select v-model="toCompany" class="tl-select">
          <option value="">Select destination…</option>
          <option v-for="c in toCompanyOptions" :key="c.name" :value="c.name">{{ c.label }}</option>
        </select>
      </div>
      <p v-if="loading" class="tl-muted">Loading…</p>
      <p v-else-if="!rows.length" class="tl-muted">No transfer rows for this view.</p>
      <div v-else class="tl-table-wrap">
        <table class="tl-table">
          <thead>
            <tr>
              <th></th>
              <th>Order Code</th>
              <th>Customer</th>
              <th>Item</th>
              <th>Unit</th>
              <th>SPR</th>
              <th>Status</th>
              <th>Batch / Qty</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="rowSelectionId(row)">
              <td>
                <input
                  type="checkbox"
                  :disabled="!row.can_transfer"
                  :checked="isSelected(row)"
                  @change="toggleRow(row, $event)"
                />
              </td>
              <td>{{ row.party_code }}</td>
              <td>{{ row.customer_name }}</td>
              <td>
                <span v-if="row._isSprGroup" :title="(row.item_codes || []).join(', ')">{{ row.item_code }}</span>
                <span v-else>{{ row.item_code }}</span>
              </td>
              <td>{{ row.unit }}</td>
              <td>{{ row.spr_name || "—" }}</td>
              <td>
                <span :class="transferStatusClass(row)">{{ transferStatusLabel(row) }}</span>
              </td>
              <td class="tl-batch-cell">
                <template v-if="isSelected(row) && row.can_transfer">
                  <button type="button" class="cc-clear-btn" @click="openBatchPicker(row)">
                    {{ batchPickerOpenFor === rowSelectionId(row) ? "Edit batches" : "Select batches" }}
                  </button>
                  <div v-if="batchSummary(row)" class="tl-batch-summary">{{ batchSummary(row) }}</div>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Batch picker: full-width panel below table (not hidden behind overlay) -->
      <div v-if="batchPickerOpenFor" class="tl-batch-panel">
        <div class="tl-batch-panel-head">
          <div>
            <strong>Select batches</strong>
            <span class="tl-batch-meta">
              Order Code {{ batchPickerRow?.party_code }} · {{ batchPickerRow?.spr_name }}
            </span>
            <div v-if="batchPickerRow?._isSprGroup && batchPickerRow.item_codes?.length" class="tl-batch-items">
              Items: {{ batchPickerRow.item_codes.join(", ") }}
            </div>
          </div>
          <div class="tl-batch-head-actions">
            <button type="button" class="cc-clear-btn tl-batch-mini" @click="selectAllBatches">Select all</button>
            <button type="button" class="cc-clear-btn tl-batch-mini" @click="clearAllBatches">Clear</button>
            <button type="button" class="tl-close" @click="closeBatchPicker">✕</button>
          </div>
        </div>
        <p v-if="batchLoading" class="tl-muted">Loading batches from SPR…</p>
        <p v-else-if="!batchOptions.length" class="tl-block">No produced batches on this SPR.</p>
        <div v-else class="tl-batch-table-wrap">
          <table class="tl-batch-table">
            <thead>
              <tr>
                <th></th>
                <th>Batch No</th>
                <th>Item</th>
                <th class="text-right">Available (Kg)</th>
                <th class="text-right">Transfer Qty (Kg)</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="b in batchOptions"
                :key="b.batch_no"
                :class="{ 'is-selected': b.selected }"
                @click="toggleBatchRow(b)"
              >
                <td><input type="checkbox" v-model="b.selected" @click.stop /></td>
                <td class="tl-batch-no">{{ b.batch_no }}</td>
                <td>{{ b.item_code }}</td>
                <td class="text-right">{{ formatQty(b.available_qty) }}</td>
                <td class="text-right" @click.stop>
                  <input
                    type="number"
                    class="tl-batch-qty-input"
                    step="0.001"
                    min="0.001"
                    :disabled="!b.selected"
                    v-model.number="b.qty"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="tl-batch-summary-bar" v-if="batchPickerTotals.count">
          <span>{{ batchPickerTotals.count }} batch(es)</span>
          <span><strong>{{ formatQty(batchPickerTotals.qty) }} Kg</strong> total</span>
        </div>
        <div class="tl-batch-panel-foot">
          <button type="button" class="cc-clear-btn" @click="closeBatchPicker">Cancel</button>
          <button type="button" class="cc-save-arrange-btn" :disabled="!batchApplyEnabled" @click="applyBatches">
            Apply {{ batchPickerTotals.count || "" }} batch(es)
          </button>
        </div>
      </div>

      <div class="tl-nature-panel">
        <div class="tl-nature-grid">
          <div class="tl-nature-field">
            <label class="tl-nature-label">Nature of Processing <span class="tl-req">*</span></label>
            <select v-model="natureOfProcessing" class="tl-select tl-nature-select">
              <option value="">Select nature of processing…</option>
              <option value="Lamination">Lamination</option>
              <option value="Printing">Printing</option>
              <option value="Slitting">Slitting</option>
              <option value="Rewinding">Rewinding</option>
              <option value="Sheet Cutting">Sheet Cutting</option>
              <option value="FG Transfer">FG Transfer</option>
              <option value="Other">Other</option>
            </select>
          </div>
          <div v-if="natureOfProcessing === 'Other'" class="tl-nature-field">
            <label class="tl-nature-label">Specify</label>
            <input v-model="natureOther" type="text" class="tl-input-nature" placeholder="Enter nature of processing" />
          </div>
        </div>
        <p v-if="toCompany" class="tl-party-hint">
          Party on Stock Entry after approval: <strong>{{ toCompany }}</strong>
        </p>
      </div>

      <div class="tl-footer">
        <button type="button" class="cc-clear-btn" @click="close">Cancel</button>
        <button type="button" class="cc-save-arrange-btn" :disabled="submitting || !canSubmit" @click="submit">
          {{ submitting ? "Submitting…" : "Submit for approval" }}
        </button>
      </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import {
  groupRowsBySpr,
  rowSelectionId,
  buildLogisticsSubmitLines,
} from "./logistics_spr_group.js";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  boardKind: { type: String, required: true },
  filterContext: { type: Object, default: () => ({}) },
  prefill: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["update:modelValue", "submitted"]);

const API = "production_entry.production_planning.transfer_logistics";

const loading = ref(false);
const submitting = ref(false);
const rows = ref([]);
const companies = ref([]);
const fromCompany = ref("");
const toCompany = ref("");
const dlgParty = ref("");
const dlgCustomer = ref("");
/** planning_table_row → { row, batches: [{ batch_no, qty, item_code }] } */
const selection = ref({});

const batchPickerOpenFor = ref("");
const batchPickerRow = ref(null);
const batchOptions = ref([]);
const batchLoading = ref(false);
const natureOfProcessing = ref("");
const natureOther = ref("");

const toCompanyOptions = computed(() => {
  const fc = (fromCompany.value || "").trim();
  return companies.value
    .filter((c) => c.name !== fc)
    .map((c) => ({ name: c.name, label: `Transfer to ${c.name}` }));
});

const displayRows = computed(() => groupRowsBySpr(rows.value));

const filteredRows = computed(() => {
  const pc = (dlgParty.value || "").trim().toLowerCase();
  const cu = (dlgCustomer.value || "").trim().toLowerCase();
  return displayRows.value.filter((r) => {
    if (pc && !(r.party_code || "").toLowerCase().includes(pc)) return false;
    if (cu && !(r.customer_name || "").toLowerCase().includes(cu)) return false;
    return true;
  });
});

const destinationLabel = computed(() => {
  const tc = (toCompany.value || "").trim();
  if (!tc) return "";
  return `Transfer to ${tc}`;
});

const batchApplyEnabled = computed(() => {
  const picked = batchOptions.value.filter((b) => b.selected);
  return picked.length > 0 && picked.every((b) => b.batch_no && ltn(b.qty) > 0);
});

const batchPickerTotals = computed(() => {
  const picked = batchOptions.value.filter((b) => b.selected && ltn(b.qty) > 0);
  return {
    count: picked.length,
    qty: picked.reduce((a, b) => a + ltn(b.qty), 0),
  };
});

const resolvedNature = computed(() => {
  let nat = (natureOfProcessing.value || "").trim();
  if (nat === "Other") nat = (natureOther.value || "").trim();
  return nat;
});

const canSubmit = computed(() => {
  if (!(toCompany.value || "").trim()) return false;
  if (!resolvedNature.value) return false;
  const entries = Object.values(selection.value);
  if (!entries.length) return false;
  return entries.every((s) => Array.isArray(s.batches) && s.batches.length > 0);
});

function isSelected(row) {
  return Boolean(selection.value[rowSelectionId(row)]);
}

function batchSummary(row) {
  const sel = selection.value[rowSelectionId(row)];
  if (!sel?.batches?.length) return "";
  return sel.batches.map((b) => `${b.batch_no} · ${formatQty(b.qty)} kg`).join("; ");
}

function formatQty(q) {
  const n = ltn(q);
  return Number.isFinite(n) ? (Math.round(n * 1000) / 1000).toString() : "0";
}

function transferStatusLabel(row) {
  const status = (row?.transfer_status || "").trim();
  if (status.startsWith("Transferred")) return status;
  if (status === "Rejected" && row?.can_transfer) return "Rejected - can request again";
  if (status && !row?.can_transfer) return status;
  if (row?.can_transfer) return "Ready";
  return row?.transfer_block_reason || "Blocked";
}

function transferStatusClass(row) {
  const status = (row?.transfer_status || "").trim().toLowerCase();
  if (status.startsWith("transferred")) return "tl-transferred";
  if (status === "rejected" && row?.can_transfer) return "tl-warn";
  return row?.can_transfer ? "tl-ok" : "tl-block";
}

function toggleRow(row, ev) {
  const id = rowSelectionId(row);
  if (!ev.target.checked) {
    const next = { ...selection.value };
    delete next[id];
    selection.value = next;
    if (batchPickerOpenFor.value === id) closeBatchPicker();
    return;
  }
  if (!row.can_transfer) {
    ev.target.checked = false;
    frappe.msgprint(row.transfer_block_reason || "SPR not done — transfer not allowed.");
    return;
  }
  selection.value = {
    ...selection.value,
    [id]: { row, batches: selection.value[id]?.batches || [] },
  };
}

function ensureRowSelected(row) {
  const id = rowSelectionId(row);
  if (!selection.value[id]) {
    selection.value = {
      ...selection.value,
      [id]: { row, batches: [] },
    };
  }
  return selection.value[id];
}

function openBatchPicker(row) {
  if (!row.can_transfer) {
    frappe.msgprint(row.transfer_block_reason || "Cannot transfer this row.");
    return;
  }
  const spr = (row.spr_name || "").trim();
  if (!spr) {
    frappe.msgprint("No SPR linked to this row.");
    return;
  }
  ensureRowSelected(row);
  batchPickerRow.value = row;
  batchPickerOpenFor.value = rowSelectionId(row);
  batchLoading.value = true;
  batchOptions.value = [];

  const existing = selection.value[rowSelectionId(row)]?.batches || [];
  const existingMap = {};
  existing.forEach((b) => {
    existingMap[b.batch_no] = b;
  });

  frappe.call({
    method: `${API}.get_spr_produced_batches`,
    args: {
      spr_name: spr,
      item_code: row._isSprGroup ? "" : row.item_code,
      party_code: row.party_code,
      from_company: fromCompany.value,
    },
    callback: (r) => {
      const batches = r.message || [];
      batchOptions.value = batches.map((b) => {
        const prev = existingMap[b.batch_no];
        const avail = ltn(b.qty) || 1;
        return {
          batch_no: b.batch_no,
          item_code: b.item_code || row.item_code,
          item_name: b.item_name,
          available_qty: avail,
          qty: prev ? ltn(prev.qty) : avail,
          selected: Boolean(prev),
        };
      });
      batchLoading.value = false;
      if (!batchOptions.value.length) {
        frappe.msgprint(`No produced batches on submitted SPR ${spr}.`);
      }
    },
    error: () => {
      batchLoading.value = false;
      frappe.msgprint("Failed to load batches from SPR.");
    },
  });
}

function closeBatchPicker() {
  batchPickerOpenFor.value = "";
  batchPickerRow.value = null;
  batchOptions.value = [];
}

function selectAllBatches() {
  batchOptions.value = batchOptions.value.map((b) => ({
    ...b,
    selected: true,
    qty: ltn(b.qty) > 0 ? b.qty : b.available_qty || 1,
  }));
}

function clearAllBatches() {
  batchOptions.value = batchOptions.value.map((b) => ({ ...b, selected: false }));
}

function toggleBatchRow(b) {
  b.selected = !b.selected;
  if (b.selected && ltn(b.qty) <= 0) {
    b.qty = b.available_qty || 1;
  }
}

function applyBatches() {
  const row = batchPickerRow.value;
  if (!row) return;
  const id = rowSelectionId(row);
  const picked = batchOptions.value
    .filter((b) => b.selected && b.batch_no && ltn(b.qty) > 0)
    .map((b) => ({
      batch_no: b.batch_no,
      qty: ltn(b.qty),
      item_code: b.item_code || row.item_code,
    }));
  if (!picked.length) {
    frappe.msgprint("Select at least one batch with qty.");
    return;
  }
  selection.value = {
    ...selection.value,
    [id]: { row, batches: picked },
  };
  frappe.show_alert({ message: `${picked.length} batch(es) applied`, indicator: "green" }, 3);
  closeBatchPicker();
}

function ltn(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function close() {
  closeBatchPicker();
  emit("update:modelValue", false);
}

async function loadCompanies() {
  const r = await frappe.call({ method: `${API}.get_logistics_companies` });
  companies.value = r.message || [];
  const names = new Set((companies.value || []).map((c) => c.name));
  if (!fromCompany.value || !names.has(fromCompany.value)) {
    if (names.has("Jayashree Spun Bond - 1ZT")) {
      fromCompany.value = "Jayashree Spun Bond - 1ZT";
    } else {
      fromCompany.value = (companies.value[0] || {}).name || "";
    }
  }
  if (toCompany.value && toCompany.value === fromCompany.value) {
    toCompany.value = "";
  }
}

function loadRows() {
  loading.value = true;
  const ctx = props.filterContext || {};
  frappe.call({
    method: `${API}.get_transfer_eligible_rows`,
    args: {
      board_kind: props.boardKind,
      view_scope: ctx.view_scope || "daily",
      date: ctx.date || "",
      week: ctx.week || "",
      month: ctx.month || "",
      unit: ctx.unit || "",
      party_code: ctx.party_code || dlgParty.value || "",
      customer: ctx.customer || dlgCustomer.value || "",
    },
    callback: (r) => {
      rows.value = r.message || [];
      loading.value = false;
    },
    error: () => {
      loading.value = false;
    },
  });
}

function buildSubmitLines() {
  return buildLogisticsSubmitLines(selection.value, "transfer");
}

function sendForApproval(natureOfProcessing) {
  const lines = buildSubmitLines();
  submitting.value = true;
  frappe.call({
    method: `${API}.create_transfer_approval_request`,
    args: {
      from_company: fromCompany.value,
      to_company: toCompany.value,
      to_destination_label: destinationLabel.value,
      nature_of_processing: natureOfProcessing,
      lines: JSON.stringify(lines),
    },
    callback: (r) => {
      submitting.value = false;
      const docname = r.message?.name || "";
      frappe.show_alert({
        message: `Transfer sent for approval: ${docname}`,
        indicator: "green",
      });
      frappe.show_alert({
        message: __("Transfer {0} sent for approval. Admin will approve from Transfer Approval dashboard.", [
          docname,
        ]),
        indicator: "green",
      });
      emit("submitted", r.message);
      close();
    },
    error: () => {
      submitting.value = false;
    },
  });
}

function submit() {
  if (!(toCompany.value || "").trim()) {
    frappe.msgprint(__("Select destination company."));
    return;
  }
  if (!resolvedNature.value) {
    frappe.msgprint(__("Select Nature of Processing before submitting."));
    return;
  }
  if (!Object.values(selection.value).length) {
    frappe.msgprint(__("Select at least one row."));
    return;
  }
  const missingBatches = Object.values(selection.value).some(
    (s) => !Array.isArray(s.batches) || !s.batches.length
  );
  if (missingBatches) {
    frappe.msgprint(__("Apply batches for each selected row."));
    return;
  }
  sendForApproval(resolvedNature.value);
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    selection.value = {};
    closeBatchPicker();
    dlgParty.value = props.prefill?.party_code || props.filterContext?.party_code || "";
    dlgCustomer.value = props.prefill?.customer || props.filterContext?.customer || "";
    fromCompany.value = props.prefill?.from_company || "";
    toCompany.value = props.prefill?.to_company || "";
    natureOfProcessing.value = "";
    natureOther.value = "";
    loadCompanies();
    loadRows();
  }
);

watch(fromCompany, (fc) => {
  if ((toCompany.value || "").trim() === (fc || "").trim()) {
    toCompany.value = "";
  }
});
</script>

<style scoped>
.tl-nature-panel {
  padding: 14px 20px;
  border-top: 1px solid #e2e8f0;
  background: #f0f9ff;
}
.tl-nature-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  align-items: flex-end;
}
.tl-nature-field {
  flex: 1;
  min-width: 220px;
}
.tl-nature-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #0369a1;
  margin-bottom: 6px;
}
.tl-req {
  color: #dc2626;
}
.tl-nature-select {
  width: 100%;
  min-width: 0;
}
.tl-input-nature {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 13px;
}
.tl-party-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #475569;
}
.tl-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.tl-dialog {
  background: #fff;
  border-radius: 12px;
  max-width: 1100px;
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  position: relative;
}
.tl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e2e8f0;
}
.tl-header h3 {
  margin: 0;
  font-size: 18px;
}
.tl-close {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
}
.tl-filters,
.tl-company-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 20px;
  align-items: center;
}
.tl-company-row label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
}
.tl-select {
  min-width: 220px;
  padding: 6px 8px;
}
.tl-table-wrap {
  overflow: auto;
  flex: 1;
  min-height: 120px;
  padding: 0 20px;
}
.tl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.tl-table th,
.tl-table td {
  border: 1px solid #e2e8f0;
  padding: 8px;
  text-align: left;
  vertical-align: top;
}
.tl-batch-cell {
  min-width: 200px;
}
.tl-batch-summary {
  margin-top: 4px;
  font-size: 11px;
  color: #0369a1;
  line-height: 1.4;
}
.tl-batch-panel {
  margin: 0 20px 12px;
  padding: 14px 16px;
  border: 2px solid #0ea5e9;
  border-radius: 10px;
  background: #f0f9ff;
  max-height: 42vh;
  display: flex;
  flex-direction: column;
}
.tl-batch-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.tl-batch-head-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tl-batch-mini {
  font-size: 11px;
  padding: 4px 8px;
}
.tl-batch-meta {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}
.tl-batch-table-wrap {
  overflow: auto;
  flex: 1;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #bae6fd;
}
.tl-batch-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.tl-batch-table th,
.tl-batch-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #e2e8f0;
}
.tl-batch-table tr.is-selected {
  background: #eff6ff;
}
.tl-batch-table tr {
  cursor: pointer;
}
.tl-batch-no {
  font-weight: 700;
  font-family: ui-monospace, monospace;
}
.tl-batch-qty-input {
  width: 100px;
  padding: 6px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  text-align: right;
}
.text-right {
  text-align: right;
}
.tl-batch-summary-bar {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #0369a1;
}
.tl-batch-panel-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #bae6fd;
}
.tl-ok {
  color: #15803d;
  font-weight: 600;
}
.tl-block {
  color: #b91c1c;
  font-size: 11px;
}
.tl-warn {
  color: #b45309;
  font-size: 11px;
  font-weight: 600;
}
.tl-transferred {
  color: #0284c7;
  font-weight: 600;
}
.tl-muted {
  padding: 8px 0;
  color: #64748b;
}
.tl-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid #e2e8f0;
}
</style>
