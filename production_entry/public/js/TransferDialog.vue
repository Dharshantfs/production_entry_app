<template>
  <div v-if="modelValue" class="tl-overlay" @click.self="close">
    <div class="tl-dialog">
      <div class="tl-header">
        <h3>Transfer rows</h3>
        <button type="button" class="tl-close" @click="close">✕</button>
      </div>
      <div class="tl-filters">
        <input v-model="dlgParty" type="text" placeholder="Filter order code" />
        <input v-model="dlgCustomer" type="text" placeholder="Filter customer" />
        <button type="button" class="cc-clear-btn" :disabled="loading" @click="loadRows">Refresh list</button>
      </div>
      <div class="tl-company-row">
        <label>From company</label>
        <select v-model="fromCompany" disabled class="tl-select">
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
      <p v-else-if="!rows.length" class="tl-muted">No transport rows for this view.</p>
      <div v-else class="tl-table-wrap">
        <table class="tl-table">
          <thead>
            <tr>
              <th></th>
              <th>Order</th>
              <th>Customer</th>
              <th>Item</th>
              <th>Unit</th>
              <th>SPR</th>
              <th>Status</th>
              <th>Batch / Qty</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="row.planning_table_row">
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
              <td>{{ row.item_code }}</td>
              <td>{{ row.unit }}</td>
              <td>{{ row.spr_name || "—" }}</td>
              <td>
                <span v-if="row.can_transfer" class="tl-ok">Ready</span>
                <span v-else class="tl-block">{{ row.transfer_block_reason || "Blocked" }}</span>
              </td>
              <td class="tl-batch-cell">
                <template v-if="isSelected(row) && row.can_transfer">
                  <button type="button" class="cc-clear-btn" @click="openBatchPicker(row)">
                    {{ batchPickerOpenFor === row.planning_table_row ? "Edit batches" : "Select batches" }}
                  </button>
                  <div v-if="batchSummary(row)" class="tl-batch-summary">{{ batchSummary(row) }}</div>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- In-dialog batch picker (stays inside Transfer popup) -->
      <div v-if="batchPickerOpenFor" class="tl-batch-panel">
        <div class="tl-batch-panel-head">
          <strong>Select batches (multi)</strong>
          <span class="tl-batch-meta">Order {{ batchPickerRow?.party_code }} · {{ batchPickerRow?.spr_name }}</span>
          <button type="button" class="tl-close" @click="closeBatchPicker">✕</button>
        </div>
        <p v-if="batchLoading" class="tl-muted">Loading batches from SPR…</p>
        <p v-else-if="!batchOptions.length" class="tl-block">No produced batches on this SPR.</p>
        <div v-else class="tl-batch-list">
          <label v-for="(b, idx) in batchOptions" :key="b.batch_no" class="tl-batch-row">
            <input type="checkbox" v-model="b.selected" />
            <span class="tl-batch-no">{{ b.batch_no }}</span>
            <span class="tl-batch-item">{{ b.item_code }}</span>
            <input
              type="number"
              class="tl-batch-qty"
              step="0.001"
              min="0.001"
              :disabled="!b.selected"
              v-model.number="b.qty"
            />
            <span class="tl-batch-uom">Kg</span>
          </label>
        </div>
        <div class="tl-batch-panel-foot">
          <button type="button" class="cc-clear-btn" @click="closeBatchPicker">Cancel</button>
          <button type="button" class="cc-save-arrange-btn" :disabled="!batchApplyEnabled" @click="applyBatches">
            Apply batches
          </button>
        </div>
      </div>

      <div class="tl-footer">
        <button type="button" class="cc-clear-btn" @click="close">Cancel</button>
        <button type="button" class="cc-save-arrange-btn" :disabled="submitting || !canSubmit" @click="submit">
          {{ submitting ? "Submitting…" : "Submit for approval" }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

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
const fromCompany = ref("Jayashree Spun Bond - 1ZT");
const toCompany = ref("");
const dlgParty = ref("");
const dlgCustomer = ref("");
/** planning_table_row → { row, batches: [{ batch_no, qty, item_code }] } */
const selection = ref({});

const batchPickerOpenFor = ref("");
const batchPickerRow = ref(null);
const batchOptions = ref([]);
const batchLoading = ref(false);

const toCompanyOptions = computed(() => {
  const fc = (fromCompany.value || "").trim();
  return companies.value
    .filter((c) => c.name !== fc)
    .map((c) => ({ name: c.name, label: `Transfer to ${c.name}` }));
});

const filteredRows = computed(() => {
  const pc = (dlgParty.value || "").trim().toLowerCase();
  const cu = (dlgCustomer.value || "").trim().toLowerCase();
  return rows.value.filter((r) => {
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

const canSubmit = computed(() => {
  if (!(toCompany.value || "").trim()) return false;
  const entries = Object.values(selection.value);
  if (!entries.length) return false;
  return entries.every((s) => Array.isArray(s.batches) && s.batches.length > 0);
});

function isSelected(row) {
  return Boolean(selection.value[row.planning_table_row]);
}

function batchSummary(row) {
  const sel = selection.value[row.planning_table_row];
  if (!sel?.batches?.length) return "";
  return sel.batches.map((b) => `${b.batch_no} · ${formatQty(b.qty)} kg`).join("; ");
}

function formatQty(q) {
  const n = ltn(q);
  return Number.isFinite(n) ? (Math.round(n * 1000) / 1000).toString() : "0";
}

function toggleRow(row, ev) {
  const id = row.planning_table_row;
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
  const id = row.planning_table_row;
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
  batchPickerOpenFor.value = row.planning_table_row;
  batchLoading.value = true;
  batchOptions.value = [];

  const existing = selection.value[row.planning_table_row]?.batches || [];
  const existingMap = {};
  existing.forEach((b) => {
    existingMap[b.batch_no] = b;
  });

  frappe.call({
    method: `${API}.get_spr_produced_batches`,
    args: {
      spr_name: spr,
      item_code: row.item_code,
      party_code: row.party_code,
    },
    callback: (r) => {
      const batches = r.message || [];
      batchOptions.value = batches.map((b) => {
        const prev = existingMap[b.batch_no];
        return {
          batch_no: b.batch_no,
          item_code: b.item_code || row.item_code,
          item_name: b.item_name,
          qty: prev ? ltn(prev.qty) : ltn(b.qty) || 1,
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

function applyBatches() {
  const row = batchPickerRow.value;
  if (!row) return;
  const id = row.planning_table_row;
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
  const lines = [];
  Object.values(selection.value).forEach((s) => {
    (s.batches || []).forEach((b) => {
      lines.push({
        planning_table_row: s.row.planning_table_row,
        planning_sheet: s.row.planning_sheet,
        party_code: s.row.party_code,
        customer_name: s.row.customer_name,
        item_code: b.item_code || s.row.item_code,
        unit: s.row.unit,
        spr_name: s.row.spr_name,
        batch_no: b.batch_no,
        qty: Math.max(ltn(b.qty), 1),
        uom: "Kg",
      });
    });
  });
  return lines;
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
      frappe.msgprint({
        title: __("Transfer submitted"),
        message: __("Party on STE will be set to {0} after approval.", [toCompany.value]),
        primary_action: {
          label: __("Open Transfer Approval"),
          action() {
            frappe.set_route("transfer-approval");
          },
        },
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
  if (!canSubmit.value) {
    if (!(toCompany.value || "").trim()) {
      frappe.msgprint("Select destination company.");
    } else {
      frappe.msgprint("Select at least one row and apply batches for each.");
    }
    return;
  }
  const tc = (toCompany.value || "").trim();
  const d = new frappe.ui.Dialog({
    title: __("Nature of Processing"),
    fields: [
      {
        fieldname: "party_help",
        fieldtype: "HTML",
        options: `<p class="text-muted small">${__(
          "Transfer to <b>{0}</b>. This company will be set as <b>Party</b> on the Stock Entry after approval.",
          [frappe.utils.escape_html(tc)]
        )}</p>`,
      },
      {
        fieldname: "nature_of_processing",
        fieldtype: "Select",
        label: __("Nature of Processing"),
        reqd: 1,
        options: [
          "Lamination",
          "Printing",
          "Slitting",
          "Rewinding",
          "Sheet Cutting",
          "FG Transfer",
          "Other",
        ].join("\n"),
      },
      {
        fieldname: "nature_other",
        fieldtype: "Data",
        label: __("Specify (if Other)"),
        depends_on: "eval:doc.nature_of_processing=='Other'",
      },
    ],
    primary_action_label: __("Submit for approval"),
    primary_action(values) {
      let nat = (values.nature_of_processing || "").trim();
      if (nat === "Other") {
        nat = (values.nature_other || "").trim();
      }
      if (!nat) {
        frappe.msgprint(__("Nature of Processing is required."));
        return;
      }
      d.hide();
      sendForApproval(nat);
    },
  });
  d.show();
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    selection.value = {};
    closeBatchPicker();
    dlgParty.value = props.prefill?.party_code || props.filterContext?.party_code || "";
    dlgCustomer.value = props.prefill?.customer || props.filterContext?.customer || "";
    fromCompany.value = props.prefill?.from_company || "Jayashree Spun Bond - 1ZT";
    toCompany.value = props.prefill?.to_company || "";
    loadCompanies();
    loadRows();
  }
);
</script>

<style scoped>
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
  padding: 12px 14px;
  border: 2px solid #0ea5e9;
  border-radius: 8px;
  background: #f0f9ff;
  max-height: 240px;
  display: flex;
  flex-direction: column;
}
.tl-batch-panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.tl-batch-meta {
  font-size: 11px;
  color: #64748b;
  flex: 1;
}
.tl-batch-list {
  overflow: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tl-batch-row {
  display: grid;
  grid-template-columns: auto 1fr auto 90px auto;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.tl-batch-no {
  font-weight: 600;
  font-family: monospace;
}
.tl-batch-item {
  color: #64748b;
  font-size: 11px;
}
.tl-batch-qty {
  width: 80px;
  padding: 4px 6px;
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
