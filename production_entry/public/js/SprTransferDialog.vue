<template>
  <Teleport to="body">
    <div v-if="open" class="tl-overlay" @click.self="close">
      <div class="tl-dialog" role="dialog" aria-modal="true" aria-labelledby="spr-transfer-title">
        <div class="tl-header">
          <h3 id="spr-transfer-title">Transfer rolls — {{ sprName }}</h3>
          <button type="button" class="tl-close" @click="close">✕</button>
        </div>

        <div v-if="loading" class="tl-muted" style="padding: 20px">Loading…</div>
        <template v-else>
          <div class="tl-company-row">
            <label>From company</label>
            <span class="tl-readonly">{{ fromCompany || "—" }}</span>
            <label>To company</label>
            <select v-model="toCompany" class="tl-select">
              <option value="">Select destination…</option>
              <option v-for="c in toCompanyOptions" :key="c.name" :value="c.name">{{ c.label }}</option>
            </select>
          </div>

          <div class="tl-nature-panel">
            <div class="tl-nature-grid">
              <div class="tl-nature-field">
                <label class="tl-nature-label">Nature of Processing <span class="tl-req">*</span></label>
                <select v-model="natureOfProcessing" class="tl-nature-select">
                  <option value="">— Select —</option>
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
              Party on Stock Entry: <strong>{{ toCompany }}</strong>
            </p>
          </div>

          <p v-if="!batchOptions.length" class="tl-muted" style="padding: 12px 20px">
            No transferable batches on this SPR (or all already in transfer).
          </p>
          <div v-else class="tl-batch-table-wrap" style="margin: 0 20px 12px">
            <div class="tl-batch-panel-head" style="margin-bottom: 8px">
              <strong>Select batches</strong>
              <div class="tl-batch-head-actions">
                <button type="button" class="cc-clear-btn tl-batch-mini" @click="selectAll">Select all</button>
                <button type="button" class="cc-clear-btn tl-batch-mini" @click="clearAll">Clear</button>
              </div>
            </div>
            <table class="tl-batch-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Batch No</th>
                  <th>Item</th>
                  <th>Order</th>
                  <th class="text-right">Qty (Kg)</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="b in batchOptions"
                  :key="b.batch_no"
                  :class="{ 'is-selected': b.selected, 'is-blocked': !b.planning_table_row }"
                  @click="toggleBatch(b)"
                >
                  <td>
                    <input
                      type="checkbox"
                      v-model="b.selected"
                      :disabled="!b.planning_table_row"
                      @click.stop
                    />
                  </td>
                  <td class="tl-batch-no">{{ b.batch_no }}</td>
                  <td>{{ b.item_code }}</td>
                  <td>{{ b.party_code || "—" }}</td>
                  <td class="text-right" @click.stop>
                    <input
                      v-model.number="b.qty"
                      type="number"
                      min="0"
                      step="0.01"
                      class="tl-qty-input"
                      :disabled="!b.selected"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="hasMissingPlanning" class="tl-block" style="color: #b45309; font-size: 12px; margin-top: 8px">
              Rows without a Planning Table link cannot be transferred. Link this SPR on the planning sheet first.
            </p>
          </div>
        </template>

        <div class="tl-footer">
          <button type="button" class="cc-clear-btn" @click="close">Cancel</button>
          <button type="button" class="cc-save-arrange-btn" :disabled="submitting || !canSubmit" @click="submit">
            {{ submitting ? "Creating STE…" : "Transfer & create Stock Entry" }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

const props = defineProps({
  sprName: { type: String, required: true },
});

const emit = defineEmits(["close", "submitted"]);

const API = "production_entry.production_planning.transfer_logistics";

const open = ref(true);
const loading = ref(true);
const submitting = ref(false);
const fromCompany = ref("");
const toCompany = ref("");
const toCompanyOptions = ref([]);
const customer = ref("");
const unit = ref("");
const natureOfProcessing = ref("");
const natureOther = ref("");
const batchOptions = ref([]);

const resolvedNature = computed(() => {
  if (natureOfProcessing.value === "Other") {
    return (natureOther.value || "").trim();
  }
  return (natureOfProcessing.value || "").trim();
});

const hasMissingPlanning = computed(() =>
  batchOptions.value.some((b) => !b.planning_table_row)
);

const canSubmit = computed(() => {
  if (!(toCompany.value || "").trim() || !resolvedNature.value) return false;
  return batchOptions.value.some((b) => b.selected && b.planning_table_row && ltn(b.qty) > 0);
});

function ltn(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function close() {
  open.value = false;
  emit("close");
}

function toggleBatch(b) {
  if (!b.planning_table_row) return;
  b.selected = !b.selected;
  if (b.selected && ltn(b.qty) <= 0) {
    b.qty = b.available_qty || 1;
  }
}

function selectAll() {
  batchOptions.value.forEach((b) => {
    if (b.planning_table_row) {
      b.selected = true;
      if (ltn(b.qty) <= 0) b.qty = b.available_qty || 1;
    }
  });
}

function clearAll() {
  batchOptions.value.forEach((b) => {
    b.selected = false;
  });
}

async function loadContext() {
  loading.value = true;
  try {
    const ctxRes = await frappe.call({
      method: `${API}.get_spr_transfer_context`,
      args: { spr_name: props.sprName },
    });
    const ctx = ctxRes.message || {};
    fromCompany.value = ctx.from_company || "";
    customer.value = ctx.customer || "";
    unit.value = ctx.unit || "";
    toCompanyOptions.value = ctx.to_company_options || [];

    const batchRes = await frappe.call({
      method: `${API}.get_spr_produced_batches`,
      args: {
        spr_name: props.sprName,
        from_company: fromCompany.value,
      },
    });
    const produced = batchRes.message || [];
    const rollMap = {};
    (ctx.rolls || []).forEach((r) => {
      rollMap[r.batch_no] = r;
    });

    batchOptions.value = produced.map((b) => {
      const meta = rollMap[b.batch_no] || {};
      const avail = ltn(b.qty) || ltn(meta.qty) || 1;
      return {
        batch_no: b.batch_no,
        item_code: b.item_code || meta.item_code,
        party_code: meta.party_code || b.party_code || "",
        planning_table_row: meta.planning_table_row || "",
        planning_sheet: meta.planning_sheet || "",
        available_qty: avail,
        qty: avail,
        selected: false,
      };
    });
  } catch (e) {
    console.error("SPR transfer context", e);
    frappe.msgprint(__("Failed to load transfer data for this SPR."));
    close();
  } finally {
    loading.value = false;
  }
}

function submit() {
  if (!(toCompany.value || "").trim()) {
    frappe.msgprint(__("Select destination company."));
    return;
  }
  if (!resolvedNature.value) {
    frappe.msgprint(__("Select Nature of Processing."));
    return;
  }
  const picked = batchOptions.value.filter(
    (b) => b.selected && b.planning_table_row && b.batch_no && ltn(b.qty) > 0
  );
  if (!picked.length) {
    frappe.msgprint(__("Select at least one batch with qty."));
    return;
  }

  const lines = picked.map((b) => ({
    planning_table_row: b.planning_table_row,
    planning_sheet: b.planning_sheet,
    party_code: b.party_code,
    customer_name: customer.value,
    item_code: b.item_code,
    unit: unit.value,
    spr_name: props.sprName,
    batch_no: b.batch_no,
    qty: ltn(b.qty),
    uom: "Kg",
  }));

  submitting.value = true;
  frappe.call({
    method: `${API}.create_and_approve_transfer_from_spr`,
    args: {
      spr_name: props.sprName,
      from_company: fromCompany.value,
      to_company: toCompany.value,
      to_destination_label: `Transfer to ${toCompany.value}`,
      nature_of_processing: resolvedNature.value,
      lines: JSON.stringify(lines),
    },
    callback: (r) => {
      submitting.value = false;
      const ste = r.message?.stock_entry || "";
      const ta = r.message?.transfer_approval || "";
      frappe.show_alert({
        message: ste ? `Stock Entry ${ste} created` : `Transfer ${ta} approved`,
        indicator: "green",
      });
      emit("submitted", r.message || {});
      close();
      if (ste) {
        frappe.set_route("Form", "Stock Entry", ste);
      }
    },
    error: () => {
      submitting.value = false;
    },
  });
}

onMounted(() => {
  loadContext();
});
</script>

<style scoped>
.tl-readonly {
  font-weight: 600;
  color: #334155;
  padding: 6px 0;
}
.is-blocked {
  opacity: 0.55;
}
.tl-qty-input {
  width: 88px;
  text-align: right;
  padding: 4px 6px;
}
</style>
