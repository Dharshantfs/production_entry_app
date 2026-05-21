<template>
  <div v-if="modelValue" class="tl-overlay" @click.self="close">
    <div class="tl-dialog">
      <div class="tl-header">
        <h3>Transfer (Transport rows)</h3>
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
              <td>
                <template v-if="isSelected(row) && row.can_transfer">
                  <button type="button" class="cc-clear-btn" @click="openBatchPicker(row)">Select batch</button>
                  <span v-if="selection[row.planning_table_row]">
                    {{ selection[row.planning_table_row].batch_no }} · {{ selection[row.planning_table_row].qty }} kg
                  </span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
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
const selection = ref({});

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

const canSubmit = computed(() => {
  if (!(toCompany.value || "").trim()) return false;
  const keys = Object.keys(selection.value);
  return keys.length > 0 && keys.every((k) => selection.value[k]?.batch_no);
});

function isSelected(row) {
  return Boolean(selection.value[row.planning_table_row]);
}

function toggleRow(row, ev) {
  const id = row.planning_table_row;
  if (!ev.target.checked) {
    const next = { ...selection.value };
    delete next[id];
    selection.value = next;
    return;
  }
  if (!row.can_transfer) {
    ev.target.checked = false;
    frappe.msgprint(row.transfer_block_reason || __("SPR not done — transfer not allowed."));
    return;
  }
  selection.value = {
    ...selection.value,
    [id]: { row, batch_no: "", qty: 1 },
  };
}

function openBatchPicker(row) {
  const spr = (row.spr_name || "").trim();
  if (!spr) {
    frappe.msgprint(__("No SPR linked to this row."));
    return;
  }
  frappe.call({
    method: `${API}.get_spr_produced_batches`,
    args: {
      spr_name: spr,
      item_code: row.item_code,
      party_code: row.party_code,
    },
    callback: (r) => {
      const batches = r.message || [];
      if (!batches.length) {
        frappe.msgprint(__("No produced batches on submitted SPR {0}.", [spr]));
        return;
      }
      const fields = [
        {
          fieldtype: "Select",
          fieldname: "batch_no",
          label: "Batch",
          options: batches.map((b) => b.batch_no).join("\n"),
          reqd: 1,
        },
        {
          fieldtype: "Float",
          fieldname: "qty",
          label: "Qty (Kg)",
          default: batches[0]?.qty || 1,
          reqd: 1,
        },
      ];
      const d = new frappe.ui.Dialog({
        title: __("Select batch"),
        fields,
        primary_action_label: __("OK"),
        primary_action(values) {
          const bn = values.batch_no;
          const b = batches.find((x) => x.batch_no === bn) || {};
          const qty = Math.max(ltn(values.qty), 1);
          selection.value = {
            ...selection.value,
            [row.planning_table_row]: {
              row,
              batch_no: bn,
              qty,
              item_code: b.item_code || row.item_code,
            },
          };
          d.hide();
        },
      });
      d.show();
    },
  });
}

function ltn(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function close() {
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

function submit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  const lines = Object.values(selection.value).map((s) => ({
    planning_table_row: s.row.planning_table_row,
    planning_sheet: s.row.planning_sheet,
    party_code: s.row.party_code,
    customer_name: s.row.customer_name,
    item_code: s.item_code || s.row.item_code,
    unit: s.row.unit,
    spr_name: s.row.spr_name,
    batch_no: s.batch_no,
    qty: s.qty,
    uom: "Kg",
  }));
  frappe.call({
    method: `${API}.create_transfer_approval_request`,
    args: {
      from_company: fromCompany.value,
      to_company: toCompany.value,
      to_destination_label: destinationLabel.value,
      lines: JSON.stringify(lines),
    },
    callback: (r) => {
      submitting.value = false;
      frappe.show_alert({
        message: __("Transfer sent for approval: {0}", [r.message?.name || ""]),
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

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    selection.value = {};
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
  padding: 20px;
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
