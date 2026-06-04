<template>
  <div v-if="modelValue" class="tl-overlay" @click.self="close">
    <div class="tl-dialog">
      <div class="tl-header">
        <h3>Despatch rows</h3>
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
      </div>
      <p v-if="loading" class="tl-muted">Loading…</p>
      <p v-else-if="!rows.length" class="tl-muted">
        No rows with movement <strong>Despatch</strong> for this table view (SPR submitted). Check month/unit filters or Planning Sheet movement.
      </p>
      <div v-else class="tl-table-wrap">
        <table class="tl-table">
          <thead>
            <tr>
              <th></th>
              <th>Order Code</th>
              <th>Customer</th>
              <th>Item</th>
              <th>SPR</th>
              <th>Status</th>
              <th>Batches</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="row.planning_table_row">
              <td>
                <input
                  type="checkbox"
                  :disabled="!row.can_despatch"
                  :checked="isSelected(row)"
                  @change="toggleRow(row, $event)"
                />
              </td>
              <td>{{ row.party_code }}</td>
              <td>{{ row.customer_name }}</td>
              <td>{{ row.item_code }}</td>
              <td>{{ row.spr_name || "—" }}</td>
              <td><span :class="statusClass(row)">{{ statusLabel(row) }}</span></td>
              <td class="tl-batch-cell">
                <template v-if="isSelected(row) && row.can_despatch">
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

      <div v-if="batchPickerOpenFor" class="tl-batch-panel">
        <div class="tl-batch-panel-head">
          <div>
            <strong>Select batches</strong>
            <span class="tl-batch-meta">{{ batchPickerRow?.party_code }} · {{ batchPickerRow?.customer_name }}</span>
          </div>
          <div class="tl-batch-head-actions">
            <label class="tl-batch-toggle">
              <input type="radio" value="spr" v-model="batchSource" @change="reloadBatches" />
              SPR produced
            </label>
            <label class="tl-batch-toggle">
              <input type="radio" value="other" v-model="batchSource" @change="reloadBatches" />
              Other batches
            </label>
            <button type="button" class="tl-close" @click="closeBatchPicker">✕</button>
          </div>
        </div>
        <p v-if="batchLoading" class="tl-muted">Loading batches…</p>
        <p v-else-if="!batchOptions.length" class="tl-block">No batches available.</p>
        <div v-else class="tl-batch-table-wrap">
          <table class="tl-batch-table">
            <thead>
              <tr>
                <th></th>
                <th>Batch No</th>
                <th class="text-right">Net / Avail (Kg)</th>
                <th class="text-right">Despatch Qty (Kg)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in batchOptions" :key="b.batch_no" :class="{ 'is-selected': b.selected }" @click="toggleBatchRow(b)">
                <td><input type="checkbox" v-model="b.selected" @click.stop /></td>
                <td class="tl-batch-no">{{ b.batch_no }}</td>
                <td class="text-right">{{ formatQty(b.available_qty) }}</td>
                <td class="text-right" @click.stop>
                  <input type="number" class="tl-batch-qty-input" step="0.001" min="0.001" :disabled="!b.selected" v-model.number="b.qty" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="tl-batch-panel-foot">
          <button type="button" class="cc-clear-btn" @click="closeBatchPicker">Cancel</button>
          <button type="button" class="cc-save-arrange-btn" :disabled="!batchApplyEnabled" @click="applyBatches">Apply batches</button>
        </div>
      </div>

      <div class="tl-footer">
        <button type="button" class="cc-clear-btn" @click="close">Cancel</button>
        <button type="button" class="cc-save-arrange-btn" :disabled="submitting || !canSubmit" @click="submit">
          {{ submitting ? "Submitting…" : "Submit for despatch approval" }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  boardKind: { type: String, default: "production" },
  filterContext: { type: Object, default: () => ({}) },
  prefill: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["update:modelValue", "submitted"]);

const API = "production_entry.production_planning.despatch_logistics";
const COMP_API = "production_entry.production_planning.transfer_logistics";

const loading = ref(false);
const submitting = ref(false);
const rows = ref([]);
const companies = ref([]);
const fromCompany = ref("");
const dlgParty = ref("");
const dlgCustomer = ref("");
const selection = ref({});
const batchPickerOpenFor = ref("");
const batchPickerRow = ref(null);
const batchOptions = ref([]);
const batchLoading = ref(false);
const batchSource = ref("spr");

const filteredRows = computed(() => {
  const pc = (dlgParty.value || "").trim().toLowerCase();
  const cu = (dlgCustomer.value || "").trim().toLowerCase();
  return rows.value.filter((r) => {
    if (pc && !(r.party_code || "").toLowerCase().includes(pc)) return false;
    if (cu && !(r.customer_name || "").toLowerCase().includes(cu)) return false;
    return true;
  });
});

const batchApplyEnabled = computed(() => {
  const picked = batchOptions.value.filter((b) => b.selected);
  return picked.length > 0 && picked.every((b) => b.batch_no && ltn(b.qty) > 0);
});

const canSubmit = computed(() => {
  if (!(fromCompany.value || "").trim()) return false;
  const entries = Object.values(selection.value);
  if (!entries.length) return false;
  return entries.every((s) => Array.isArray(s.batches) && s.batches.length > 0);
});

function ltn(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function formatQty(q) {
  return String(Math.round(ltn(q) * 1000) / 1000);
}

function isSelected(row) {
  return Boolean(selection.value[row.planning_table_row]);
}

function batchSummary(row) {
  const sel = selection.value[row.planning_table_row];
  if (!sel?.batches?.length) return "";
  return sel.batches.map((b) => `${b.batch_no} · ${formatQty(b.qty)} kg`).join("; ");
}

function statusLabel(row) {
  return row.can_despatch ? "Ready" : row.despatch_block_reason || "Blocked";
}

function statusClass(row) {
  return row.can_despatch ? "tl-ok" : "tl-block";
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
  if (!row.can_despatch) {
    ev.target.checked = false;
    frappe.msgprint(row.despatch_block_reason || "Cannot despatch this row.");
    return;
  }
  selection.value = { ...selection.value, [id]: { row, batches: selection.value[id]?.batches || [] } };
}

function openBatchPicker(row) {
  batchPickerRow.value = row;
  batchPickerOpenFor.value = row.planning_table_row;
  batchSource.value = "spr";
  reloadBatches();
}

function reloadBatches() {
  const row = batchPickerRow.value;
  if (!row) return;
  batchLoading.value = true;
  batchOptions.value = [];
  const existing = selection.value[row.planning_table_row]?.batches || [];
  const existingMap = {};
  existing.forEach((b) => {
    existingMap[b.batch_no] = b;
  });
  const method =
    batchSource.value === "other"
      ? `${API}.get_despatch_other_batches`
      : `${API}.get_despatch_spr_batches`;
  const args =
    batchSource.value === "other"
      ? { item_code: row.item_code, from_company: fromCompany.value, party_code: row.party_code }
      : {
          spr_name: row.spr_name,
          item_code: row.item_code,
          party_code: row.party_code,
          from_company: fromCompany.value,
        };
  frappe.call({
    method,
    args,
    callback: (r) => {
      const batches = r.message || [];
      batchOptions.value = batches.map((b) => {
        const prev = existingMap[b.batch_no];
        const avail = ltn(b.available_qty || b.qty) || 1;
        return {
          batch_no: b.batch_no,
          item_code: b.item_code || row.item_code,
          available_qty: avail,
          net_weight: ltn(b.net_weight || b.qty),
          qty: prev ? ltn(prev.qty) : avail,
          selected: Boolean(prev),
        };
      });
      batchLoading.value = false;
    },
    error: () => {
      batchLoading.value = false;
    },
  });
}

function closeBatchPicker() {
  batchPickerOpenFor.value = "";
  batchPickerRow.value = null;
  batchOptions.value = [];
}

function toggleBatchRow(b) {
  b.selected = !b.selected;
  if (b.selected && ltn(b.qty) <= 0) b.qty = b.available_qty || 1;
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
      net_weight: ltn(b.net_weight || b.qty),
      item_code: b.item_code || row.item_code,
    }));
  if (!picked.length) {
    frappe.msgprint("Select at least one batch.");
    return;
  }
  selection.value = { ...selection.value, [id]: { row, batches: picked } };
  closeBatchPicker();
}

function close() {
  closeBatchPicker();
  emit("update:modelValue", false);
}

function loadRows() {
  loading.value = true;
  const ctx = props.filterContext || {};
  frappe.call({
    method: `${API}.get_despatch_eligible_rows`,
    args: {
      board_kind: props.boardKind,
      view_scope: ctx.view_scope || "daily",
      date: ctx.date || "",
      week: ctx.week || "",
      month: ctx.month || "",
      unit: ctx.unit || "",
      party_code: dlgParty.value || ctx.party_code || "",
      customer: dlgCustomer.value || ctx.customer || "",
      from_company: fromCompany.value,
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

function submit() {
  if (!fromCompany.value) {
    frappe.msgprint("Select from company.");
    return;
  }
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
        net_weight: b.net_weight || b.qty,
        qty: Math.max(ltn(b.qty), 1),
        uom: "Kg",
      });
    });
  });
  if (!lines.length) {
    frappe.msgprint("Select rows and batches.");
    return;
  }
  submitting.value = true;
  frappe.call({
    method: `${API}.create_despatch_approval_request`,
    args: { from_company: fromCompany.value, lines: JSON.stringify(lines) },
    callback: (r) => {
      submitting.value = false;
      frappe.show_alert({ message: `Despatch approval ${r.message?.name}`, indicator: "green" });
      emit("submitted", r.message);
      close();
    },
    error: () => {
      submitting.value = false;
    },
  });
}

async function loadCompanies() {
  const r = await frappe.call({ method: `${COMP_API}.get_logistics_companies` });
  companies.value = r.message || [];
  if (!fromCompany.value && companies.value.length) {
    const pref = props.prefill?.from_company;
    fromCompany.value =
      pref && companies.value.some((c) => c.name === pref)
        ? pref
        : companies.value.find((c) => c.name.includes("Jayashree"))?.name || companies.value[0].name;
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    selection.value = {};
    const ctx = props.filterContext || {};
    dlgParty.value = props.prefill?.party_code || ctx.party_code || "";
    dlgCustomer.value = props.prefill?.customer || ctx.customer || "";
    fromCompany.value = props.prefill?.from_company || "";
    loadCompanies();
    loadRows();
  }
);

watch(fromCompany, () => {
  if (props.modelValue) loadRows();
});
</script>

<style scoped>
.tl-batch-toggle {
  font-size: 12px;
  margin-right: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
