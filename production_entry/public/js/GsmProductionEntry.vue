<template>
  <div class="gpe-root">
    <div class="gpe-banner">
      UI test mode — entries save locally only. Production Table and SPR flow are unchanged. Submit Entry disabled.
    </div>

    <div class="gpe-filters">
      <div class="gpe-filter">
        <label>View</label>
        <select v-model="viewScope" @change="fetchOrders">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>
      <div class="gpe-filter" v-if="viewScope === 'daily'">
        <label>Planned Date</label>
        <input type="date" v-model="filterDate" @change="fetchOrders" />
      </div>
      <div class="gpe-filter" v-else-if="viewScope === 'weekly'">
        <label>Week</label>
        <input type="week" v-model="filterWeek" @change="fetchOrders" />
      </div>
      <div class="gpe-filter" v-else>
        <label>Month</label>
        <input type="month" v-model="filterMonth" @change="fetchOrders" />
      </div>
      <div class="gpe-filter">
        <label>Unit</label>
        <select v-model="filterUnit" @change="onUnitChange">
          <option value="">All units</option>
          <option v-for="u in unitOptions" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>
      <div class="gpe-filter">
        <label>Search</label>
        <input v-model="searchText" type="text" placeholder="Order / party..." />
      </div>
      <button class="gpe-btn" @click="fetchOrders">Refresh</button>
    </div>

    <div class="gpe-layout">
      <aside class="gpe-sidebar">
        <h3>Orders &amp; GSM</h3>
        <p class="gpe-hint">PP submitted only. Select GSM lines, then Add Roll Row.</p>
        <div v-if="loadingOrders" class="gpe-muted">Loading…</div>
        <div v-else-if="!orderGroups.length" class="gpe-muted">No PP-submitted orders for this date/unit.</div>
        <div v-for="grp in filteredOrderGroups" :key="grp.key" class="gpe-order-group">
          <div class="gpe-order-head">
            <strong>{{ grp.orderCode }}</strong>
            <span class="gpe-party">{{ grp.partyName }}</span>
            <button
              v-if="grp.ppId"
              type="button"
              class="gpe-link-btn"
              @click="viewPP(grp.ppId)"
            >View PP</button>
          </div>
          <label
            v-for="line in grp.lines"
            :key="line.id"
            class="gpe-line"
            :class="{ active: activeLineId === line.id, selected: selectedLineIds.has(line.id) }"
          >
            <input
              type="checkbox"
              :checked="selectedLineIds.has(line.id)"
              @change="toggleLine(line.id, $event)"
            />
            <span @click.prevent="setActiveLine(line.id)">
              {{ line.gsm }} GSM · {{ line.widthLabel }} · Rem {{ formatKg(line.remainingKg) }} Kg
            </span>
          </label>
        </div>
        <div v-if="selectedSummary" class="gpe-selected-box">
          <div>Selected: {{ selectedSummary.count }} GSM line(s)</div>
          <div>Total remaining: {{ formatKg(selectedSummary.remaining) }} Kg</div>
          <button type="button" class="gpe-link-btn" @click="clearSelection">Clear</button>
        </div>
      </aside>

      <main class="gpe-main">
        <div class="gpe-header">
          <div class="gpe-tags">
            <span v-for="t in headerTags" :key="t" class="gpe-tag">{{ t }}</span>
          </div>
          <div class="gpe-header-fields">
            <label>Run Date <input type="date" v-model="runDate" /></label>
            <label>Shift <input v-model="shift" type="text" placeholder="e.g. 1" /></label>
            <label>Unit <input v-model="headerUnit" type="text" readonly /></label>
            <label>Operator <input v-model="operator" type="text" /></label>
            <label>Supervisor <input v-model="supervisor" type="text" /></label>
          </div>
        </div>

        <div class="gpe-metrics">
          <div class="gpe-metric blue">Total Entry (Kg)<br /><strong>{{ formatKg(metrics.totalGross) }}</strong></div>
          <div class="gpe-metric green">Net Production (Kg)<br /><strong>{{ formatKg(metrics.totalNet) }}</strong></div>
          <div class="gpe-metric orange">Remaining (Kg)<br /><strong>{{ formatKg(metrics.remaining) }}</strong></div>
          <div class="gpe-metric grey">Rolls<br /><strong>{{ rollLines.length }}</strong></div>
        </div>

        <div class="gpe-toolbar">
          <button type="button" class="gpe-btn primary" :disabled="!canAddRow" @click="addRollRow">Add Roll Row</button>
          <button type="button" class="gpe-btn" :disabled="!rollLines.length" @click="removeTopRow">Remove Top Row</button>
          <span class="gpe-save-status">{{ saveStatus }}</span>
          <button type="button" class="gpe-btn disabled" disabled title="Phase 1B">Submit Entry (disabled)</button>
        </div>

        <div class="gpe-grid-wrap">
          <table class="gpe-grid">
            <thead>
              <tr>
                <th>#</th>
                <th>Order</th>
                <th>Item</th>
                <th>GSM</th>
                <th>Batch</th>
                <th>Quality</th>
                <th>Color</th>
                <th>Width</th>
                <th>Ord Len</th>
                <th>Prod Len</th>
                <th>Sticker GSM</th>
                <th>Prod GSM</th>
                <th>Net</th>
                <th>Gross</th>
                <th>Core mm</th>
                <th>Dia in</th>
                <th>CBM</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, idx) in rollLines"
                :key="row._id"
                :class="rowBandClass(row)"
              >
                <td>{{ rollLines.length - idx }}</td>
                <td>{{ row.party_code }}</td>
                <td :title="row.item_name">{{ row.item_code }}</td>
                <td>{{ row.gsm }}</td>
                <td>{{ row.batch_no }}</td>
                <td>{{ row.quality }}</td>
                <td>{{ row.color }}</td>
                <td>{{ row.width_inch }}</td>
                <td>{{ row.meter_roll }}</td>
                <td>
                  <input
                    v-model.number="row.produced_length_mtrs"
                    type="number"
                    step="0.01"
                    class="gpe-inp"
                    @input="onRowEdit(row)"
                  />
                </td>
                <td>{{ row.gsm }}</td>
                <td>{{ row.produced_gsm }}</td>
                <td>{{ row.net_weight }}</td>
                <td>
                  <input
                    v-model="row.gross_weight"
                    type="text"
                    class="gpe-inp"
                    @input="onRowEdit(row)"
                  />
                </td>
                <td>
                  <input
                    v-model.number="row.custom_core_width_mm"
                    type="number"
                    step="1"
                    class="gpe-inp"
                    @input="onRowEdit(row)"
                  />
                </td>
                <td>
                  <input
                    v-model.number="row.custom_diameter_inches"
                    type="number"
                    step="0.01"
                    class="gpe-inp"
                  />
                </td>
                <td>
                  <input
                    v-model.number="row.custom_cbm_cubic_meters"
                    type="number"
                    step="0.001"
                    class="gpe-inp"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="gpe-summaries">
          <div class="gpe-tabs">
            <button :class="{ active: summaryTab === 'summary' }" @click="summaryTab = 'summary'">Summary</button>
            <button :class="{ active: summaryTab === 'linked' }" @click="summaryTab = 'linked'">Linked Orders</button>
          </div>
          <div v-show="summaryTab === 'summary'" class="gpe-summary-panels">
            <div class="gpe-panel">
              <h4>Linked Orders{{ primaryGsmLabel }}</h4>
              <table>
                <thead>
                  <tr><th>Order</th><th>Party</th><th>Required</th><th>Produced</th><th>Remaining</th></tr>
                </thead>
                <tbody>
                  <tr v-for="r in linkedOrderSummary" :key="r.orderCode">
                    <td>{{ r.orderCode }}</td>
                    <td>{{ r.partyName }}</td>
                    <td>{{ formatKg(r.required) }}</td>
                    <td>{{ formatKg(r.produced) }}</td>
                    <td>{{ formatKg(r.remaining) }}</td>
                  </tr>
                  <tr class="total">
                    <td colspan="2">Total</td>
                    <td>{{ formatKg(linkedTotals.required) }}</td>
                    <td>{{ formatKg(linkedTotals.produced) }}</td>
                    <td>{{ formatKg(linkedTotals.remaining) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="gpe-panel">
              <h4>Batch Summary (session)</h4>
              <table>
                <thead>
                  <tr><th>Batch</th><th>Rolls</th><th>Total Kg</th><th>Net Kg</th></tr>
                </thead>
                <tbody>
                  <tr v-for="b in batchSummary" :key="b.batch_no">
                    <td>{{ b.batch_no }}</td>
                    <td>{{ b.rolls }}</td>
                    <td>{{ formatKg(b.totalGross) }}</td>
                    <td>{{ formatKg(b.totalNet) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="gpe-panel">
              <h4>GSM-wise Summary</h4>
              <table>
                <thead>
                  <tr><th>GSM</th><th>Required</th><th>Produced</th><th>Remaining</th><th>Progress</th></tr>
                </thead>
                <tbody>
                  <tr v-for="g in gsmSummary" :key="g.gsm">
                    <td>{{ g.gsm }}</td>
                    <td>{{ formatKg(g.required) }}</td>
                    <td>{{ formatKg(g.produced) }}</td>
                    <td>{{ formatKg(g.remaining) }}</td>
                    <td>
                      <div class="gpe-progress"><div :style="{ width: g.pct + '%' }"></div></div>
                      {{ g.pct.toFixed(1) }}%
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <p v-if="summaryTab === 'summary'" class="gpe-note">
            Note: Entries are captured roll-wise with batch reference. Backend SPR submit not connected in this phase.
          </p>
          <div v-show="summaryTab === 'linked'" class="gpe-panel wide">
            <table>
              <thead>
                <tr><th>Order</th><th>Party</th><th>GSM</th><th>Width</th><th>Required</th><th>Session Kg</th><th>PT Achieved</th></tr>
              </thead>
              <tbody>
                <tr v-for="line in selectedLinesDetail" :key="line.id">
                  <td>{{ line.orderCode }}</td>
                  <td>{{ line.partyName }}</td>
                  <td>{{ line.gsm }}</td>
                  <td>{{ line.width_inch }}</td>
                  <td>{{ formatKg(line.requiredKg) }}</td>
                  <td>{{ formatKg(line.sessionKg) }}</td>
                  <td>{{ formatKg(line.achievedKg) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { openProductionPlanPrintPreview } from "./pp_print_utils.js";
import {
  sprCalcNetFromGross,
  sprCalcProducedGsm,
  sprFlt,
  sprFormatKg,
  sprGsmBandClass,
  sprNormalizeGrossWeightInput,
  sprRecalcRollRow,
} from "./spr_roll_entry_utils.js";

const STORAGE_KEY = "gsm_production_entry_draft_v1";
const BOARD_SLUG = "production-table";

const viewScope = ref("daily");
const filterDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref(frappe.datetime.get_today().slice(0, 7));
const filterUnit = ref("");
const searchText = ref("");
const loadingOrders = ref(false);
const rawOrders = ref([]);

const runDate = ref(frappe.datetime.get_today());
const shift = ref("1");
const headerUnit = ref("");
const operator = ref("");
const supervisor = ref("");

const rollLines = ref([]);
const selectedLineIds = ref(new Set());
const activeLineId = ref("");
const seriesPrefix = ref("");
const maxRollSuffix = ref(0);
const creationSeq = ref(0);

const summaryTab = ref("summary");
const saveStatus = ref("");
let saveTimer = null;
let autosaveTimer = null;

function formatKg(v) {
  return sprFormatKg(v);
}

function itemRemainingKg(item) {
  const target = sprFlt(item.pp_target_qty || item.qty);
  const achieved = sprFlt(item.actual_production_weight_kgs);
  const pending = sprFlt(item.pending_qty);
  if (pending > 0) {
    return pending;
  }
  return Math.max(0, target - achieved);
}

const ppSubmittedRows = computed(() =>
  (rawOrders.value || []).filter((r) => r.pp_id && Number(r.pp_docstatus) === 1)
);

const unitOptions = computed(() => {
  const s = new Set();
  ppSubmittedRows.value.forEach((r) => {
    if (r.unit) {
      s.add(r.unit);
    }
  });
  return [...s].sort();
});

const orderGroups = computed(() => {
  const map = new Map();
  let rows = ppSubmittedRows.value;
  if (filterUnit.value) {
    rows = rows.filter((r) => r.unit === filterUnit.value);
  }
  rows.forEach((item) => {
    const orderCode = item.partyCode || item.party_code || "";
    const key = `${orderCode}::${item.customer_name || item.customer || ""}`;
    if (!map.has(key)) {
      map.set(key, {
        key,
        orderCode,
        partyName: item.customer_name || item.customer || "",
        ppId: item.pp_id,
        lines: [],
      });
    }
    const w = sprFlt(item.width_inch || item.width);
    map.get(key).lines.push({
      id: item.itemName || item.name,
      source: item,
      gsm: item.gsm,
      width_inch: w,
      widthLabel: w ? `${w}"` : "—",
      remainingKg: itemRemainingKg(item),
      orderCode,
      partyName: item.customer_name || item.customer || "",
    });
  });
  return [...map.values()].sort((a, b) => a.orderCode.localeCompare(b.orderCode));
});

const filteredOrderGroups = computed(() => {
  const q = (searchText.value || "").trim().toLowerCase();
  if (!q) {
    return orderGroups.value;
  }
  return orderGroups.value
    .map((g) => ({
      ...g,
      lines: g.lines.filter(
        (l) =>
          g.orderCode.toLowerCase().includes(q) ||
          g.partyName.toLowerCase().includes(q) ||
          String(l.gsm).toLowerCase().includes(q)
      ),
    }))
    .filter((g) => g.lines.length);
});

const lineById = computed(() => {
  const m = new Map();
  orderGroups.value.forEach((g) => {
    g.lines.forEach((l) => m.set(l.id, { ...l, ppId: g.ppId }));
  });
  return m;
});

const selectedSummary = computed(() => {
  let remaining = 0;
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (line) {
      remaining += line.remainingKg;
    }
  });
  return { count: selectedLineIds.value.size, remaining };
});

const headerTags = computed(() => {
  const tags = [];
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (line) {
      tags.push(`${line.orderCode} / ${line.gsm} GSM`);
    }
  });
  return tags.slice(0, 8);
});

const primaryGsmLabel = computed(() => {
  const gsms = new Set();
  rollLines.value.forEach((r) => {
    if (r.gsm) {
      gsms.add(r.gsm);
    }
  });
  if (gsms.size === 1) {
    return ` with ${[...gsms][0]} GSM`;
  }
  return "";
});

const metrics = computed(() => {
  let totalGross = 0;
  let totalNet = 0;
  rollLines.value.forEach((r) => {
    totalGross += sprNormalizeGrossWeightInput(r.gross_weight);
    totalNet += sprFlt(r.net_weight);
  });
  let remaining = 0;
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (line) {
      remaining += line.remainingKg;
    }
  });
  rollLines.value.forEach((r) => {
    const line = lineById.value.get(r.planning_table_row);
    if (line) {
      remaining -= sprFlt(r.net_weight);
    }
  });
  return { totalGross, totalNet, remaining: Math.max(0, remaining) };
});

const linkedOrderSummary = computed(() => {
  const byOrder = new Map();
  const addReq = (orderCode, partyName, required) => {
    const k = orderCode;
    if (!byOrder.has(k)) {
      byOrder.set(k, { orderCode, partyName, required: 0, produced: 0, achieved: 0 });
    }
    byOrder.get(k).required += required;
    if (partyName) {
      byOrder.get(k).partyName = partyName;
    }
  };
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (!line) {
      return;
    }
    const src = line.source;
    addReq(line.orderCode, line.partyName, sprFlt(src.pp_target_qty || src.qty));
    byOrder.get(line.orderCode).achieved += sprFlt(src.actual_production_weight_kgs);
  });
  rollLines.value.forEach((r) => {
    const k = r.party_code;
    if (!byOrder.has(k)) {
      byOrder.set(k, { orderCode: k, partyName: "", required: 0, produced: 0, achieved: 0 });
    }
    byOrder.get(k).produced += sprFlt(r.net_weight);
  });
  return [...byOrder.values()].map((o) => ({
    ...o,
    remaining: Math.max(0, o.required - o.achieved - o.produced),
    produced: o.achieved + o.produced,
  }));
});

const linkedTotals = computed(() => {
  const rows = linkedOrderSummary.value;
  return rows.reduce(
    (a, r) => ({
      required: a.required + r.required,
      produced: a.produced + r.produced,
      remaining: a.remaining + r.remaining,
    }),
    { required: 0, produced: 0, remaining: 0 }
  );
});

const batchSummary = computed(() => {
  const m = new Map();
  rollLines.value.forEach((r) => {
    const bn = r.batch_no || "(pending)";
    if (!m.has(bn)) {
      m.set(bn, { batch_no: bn, rolls: 0, totalGross: 0, totalNet: 0 });
    }
    const b = m.get(bn);
    b.rolls += 1;
    b.totalGross += sprNormalizeGrossWeightInput(r.gross_weight);
    b.totalNet += sprFlt(r.net_weight);
  });
  return [...m.values()];
});

const gsmSummary = computed(() => {
  const m = new Map();
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (!line) {
      return;
    }
    const g = String(line.gsm);
    if (!m.has(g)) {
      m.set(g, { gsm: g, required: 0, session: 0, achieved: 0 });
    }
    const src = line.source;
    m.get(g).required += sprFlt(src.pp_target_qty || src.qty);
    m.get(g).achieved += sprFlt(src.actual_production_weight_kgs);
  });
  rollLines.value.forEach((r) => {
    const g = String(r.gsm);
    if (!m.has(g)) {
      m.set(g, { gsm: g, required: 0, session: 0, achieved: 0 });
    }
    m.get(g).session += sprFlt(r.net_weight);
  });
  return [...m.values()].map((x) => {
    const produced = x.achieved + x.session;
    const remaining = Math.max(0, x.required - produced);
    const pct = x.required > 0 ? Math.min(100, (produced / x.required) * 100) : 0;
    return { gsm: x.gsm, required: x.required, produced, remaining, pct };
  });
});

const selectedLinesDetail = computed(() => {
  const out = [];
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (!line) {
      return;
    }
    const sessionKg = rollLines.value
      .filter((r) => r.planning_table_row === id)
      .reduce((s, r) => s + sprFlt(r.net_weight), 0);
    out.push({
      id,
      orderCode: line.orderCode,
      partyName: line.partyName,
      gsm: line.gsm,
      width_inch: line.width_inch,
      requiredKg: sprFlt(line.source.pp_target_qty || line.source.qty),
      sessionKg,
      achievedKg: sprFlt(line.source.actual_production_weight_kgs),
    });
  });
  return out;
});

const canAddRow = computed(
  () => !!(activeLineId.value || selectedLineIds.value.size) && headerUnit.value && runDate.value && shift.value
);

function toggleLine(id, ev) {
  const next = new Set(selectedLineIds.value);
  if (ev.target.checked) {
    next.add(id);
    activeLineId.value = id;
  } else {
    next.delete(id);
    if (activeLineId.value === id) {
      activeLineId.value = next.size ? [...next][0] : "";
    }
  }
  selectedLineIds.value = next;
  scheduleAutosave();
}

function setActiveLine(id) {
  activeLineId.value = id;
  const next = new Set(selectedLineIds.value);
  next.add(id);
  selectedLineIds.value = next;
}

function clearSelection() {
  selectedLineIds.value = new Set();
  activeLineId.value = "";
}

function viewPP(ppId) {
  if (ppId) {
    openProductionPlanPrintPreview(ppId);
  }
}

function rowBandClass(row) {
  const hasWeight = sprNormalizeGrossWeightInput(row.gross_weight) > 0;
  return sprGsmBandClass(row.gsm, row.produced_gsm, hasWeight);
}

function onRowEdit(row) {
  const updated = sprRecalcRollRow(row);
  Object.assign(row, updated);
  scheduleAutosave();
}

function buildFetchArgs() {
  const args = { board_slug: BOARD_SLUG, plan_name: "__all__", planned_only: 1, board_process_scope: "only_100" };
  if (viewScope.value === "monthly" && filterMonth.value) {
    const [year, month] = filterMonth.value.split("-");
    const lastDay = new Date(parseInt(year, 10), parseInt(month, 10), 0).getDate();
    args.start_date = `${filterMonth.value}-01`;
    args.end_date = `${filterMonth.value}-${String(lastDay).padStart(2, "0")}`;
  } else if (viewScope.value === "weekly" && filterWeek.value) {
    const [yearStr, weekStr] = filterWeek.value.split("-W");
    const y = parseInt(yearStr, 10);
    const w = parseInt(weekStr, 10);
    const simple = new Date(y, 0, 1 + (w - 1) * 7);
    const dow = simple.getDay();
    const start = new Date(simple);
    if (dow <= 4) {
      start.setDate(simple.getDate() - simple.getDay() + 1);
    } else {
      start.setDate(simple.getDate() + 8 - simple.getDay());
    }
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    const fmt = (d) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    args.start_date = fmt(start);
    args.end_date = fmt(end);
  } else {
    args.date = filterDate.value;
  }
  return args;
}

async function fetchOrders() {
  loadingOrders.value = true;
  try {
    const r = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.get_color_chart_data",
      args: buildFetchArgs(),
    });
    rawOrders.value = (r.message || []).map((d) => ({
      ...d,
      plannedDate: d.plannedDate || d.planned_date || "",
      partyCode: d.partyCode || d.party_code || "",
      customer_name: d.customer_name || d.party_name || d.customer || "",
      itemName: d.itemName || d.item_name || d.name,
      width_inch: sprFlt(d.width_inch || d.width),
    }));
    if (!filterUnit.value && unitOptions.value.length === 1) {
      filterUnit.value = unitOptions.value[0];
      headerUnit.value = filterUnit.value;
    }
  } catch (e) {
    console.error(e);
    frappe.msgprint("Failed to load orders");
  } finally {
    loadingOrders.value = false;
  }
}

function onUnitChange() {
  headerUnit.value = filterUnit.value;
  scheduleAutosave();
}

async function previewNextBatch() {
  const existing = rollLines.value.map((r) => r.batch_no).filter(Boolean);
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.preview_spr_batch_numbers_for_entry",
    args: {
      unit: headerUnit.value,
      run_date: runDate.value,
      shift: shift.value,
      count: 1,
      client_max_roll: maxRollSuffix.value,
      client_series_prefix: seriesPrefix.value || undefined,
      existing_batches: JSON.stringify(existing),
    },
  });
  const row = (res.message || [])[0];
  if (row?.series_prefix) {
    seriesPrefix.value = row.series_prefix;
  }
  if (row?.roll_no) {
    maxRollSuffix.value = Math.max(maxRollSuffix.value, parseInt(row.roll_no, 10));
  }
  return row || { batch_no: "", roll_no: "" };
}

async function addRollRow() {
  const lineId = activeLineId.value || [...selectedLineIds.value][0];
  const line = lineById.value.get(lineId);
  if (!line) {
    frappe.msgprint("Select an order GSM line on the left.");
    return;
  }
  if (!headerUnit.value) {
    frappe.msgprint("Select a unit filter first.");
    return;
  }
  const src = line.source;
  const batchInfo = await previewNextBatch();
  creationSeq.value += 1;
  const newRow = sprRecalcRollRow({
    _id: `row-${Date.now()}-${creationSeq.value}`,
    creation_seq: creationSeq.value,
    planning_table_row: lineId,
    pp_id: line.ppId || src.pp_id,
    party_code: line.orderCode,
    item_code: src.itemCode || src.item_code,
    item_name: src.description || src.item_name || "",
    quality: src.quality || "",
    color: src.color || src.fabric_colour || "",
    gsm: src.gsm,
    batch_no: batchInfo.batch_no || "",
    roll_no: batchInfo.roll_no || "",
    width_inch: line.width_inch,
    meter_roll: sprFlt(src.meter || src.meter_roll),
    produced_length_mtrs: sprFlt(src.meter || src.meter_roll),
    produced_gsm: 0,
    net_weight: 0,
    gross_weight: "",
    custom_core_width_mm: 1600,
    custom_diameter_inches: "",
    custom_cbm_cubic_meters: "",
    work_order: "",
  });
  rollLines.value.unshift(newRow);
  scheduleAutosave();
}

function removeTopRow() {
  if (!rollLines.value.length) {
    return;
  }
  rollLines.value.shift();
  scheduleAutosave();
}

function persistDraft() {
  try {
    const payload = {
      runDate: runDate.value,
      shift: shift.value,
      headerUnit: headerUnit.value,
      operator: operator.value,
      supervisor: supervisor.value,
      filterUnit: filterUnit.value,
      filterDate: filterDate.value,
      selectedLineIds: [...selectedLineIds.value],
      activeLineId: activeLineId.value,
      rollLines: rollLines.value,
      seriesPrefix: seriesPrefix.value,
      maxRollSuffix: maxRollSuffix.value,
      creationSeq: creationSeq.value,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    saveStatus.value = "Saved locally";
  } catch (e) {
    saveStatus.value = "Save failed";
  }
}

function restoreDraft() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return;
    }
    const d = JSON.parse(raw);
    if (d.runDate) {
      runDate.value = d.runDate;
    }
    if (d.shift) {
      shift.value = d.shift;
    }
    if (d.headerUnit) {
      headerUnit.value = d.headerUnit;
      filterUnit.value = d.filterUnit || d.headerUnit;
    }
    operator.value = d.operator || "";
    supervisor.value = d.supervisor || "";
    if (d.filterDate) {
      filterDate.value = d.filterDate;
    }
    selectedLineIds.value = new Set(d.selectedLineIds || []);
    activeLineId.value = d.activeLineId || "";
    rollLines.value = d.rollLines || [];
    seriesPrefix.value = d.seriesPrefix || "";
    maxRollSuffix.value = d.maxRollSuffix || 0;
    creationSeq.value = d.creationSeq || 0;
    saveStatus.value = "Draft restored";
  } catch (e) {
    console.warn("draft restore failed", e);
  }
}

function scheduleAutosave() {
  saveStatus.value = "Saving…";
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
  }
  autosaveTimer = setTimeout(() => {
    persistDraft();
  }, 5000);
}

watch([runDate, shift, operator, supervisor], () => scheduleAutosave());

onMounted(async () => {
  restoreDraft();
  await fetchOrders();
});

onUnmounted(() => {
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
  }
  if (saveTimer) {
    clearTimeout(saveTimer);
  }
});
</script>

<style scoped>
.gpe-root {
  font-family: system-ui, sans-serif;
  font-size: 13px;
  color: #1e293b;
  padding: 12px;
  background: #f8fafc;
  min-height: 100vh;
}
.gpe-banner {
  background: #fef3c7;
  border: 1px solid #f59e0b;
  color: #92400e;
  padding: 8px 12px;
  border-radius: 8px;
  margin-bottom: 12px;
  font-weight: 600;
}
.gpe-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 12px;
  background: #fff;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.gpe-filter label {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 2px;
}
.gpe-filter input,
.gpe-filter select {
  padding: 6px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
.gpe-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 12px;
  align-items: start;
}
@media (max-width: 1100px) {
  .gpe-layout {
    grid-template-columns: 1fr;
  }
}
.gpe-sidebar {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  max-height: calc(100vh - 200px);
  overflow: auto;
}
.gpe-sidebar h3 {
  margin: 0 0 8px;
  font-size: 15px;
}
.gpe-hint {
  font-size: 11px;
  color: #64748b;
  margin: 0 0 10px;
}
.gpe-order-group {
  border-top: 1px solid #f1f5f9;
  padding-top: 8px;
  margin-top: 8px;
}
.gpe-order-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.gpe-party {
  font-size: 11px;
  color: #64748b;
}
.gpe-line {
  display: flex;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.gpe-line.active {
  background: #eef2ff;
}
.gpe-line.selected {
  font-weight: 600;
}
.gpe-selected-box {
  margin-top: 12px;
  padding: 8px;
  background: #f1f5f9;
  border-radius: 6px;
  font-size: 12px;
}
.gpe-main {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
}
.gpe-header-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
}
.gpe-header-fields label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gpe-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gpe-tag {
  background: #e0e7ff;
  color: #3730a3;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
}
.gpe-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin: 12px 0;
}
.gpe-metric {
  padding: 10px;
  border-radius: 8px;
  text-align: center;
  font-size: 11px;
}
.gpe-metric strong {
  font-size: 18px;
  display: block;
  margin-top: 4px;
}
.gpe-metric.blue {
  background: #dbeafe;
}
.gpe-metric.green {
  background: #dcfce7;
}
.gpe-metric.orange {
  background: #ffedd5;
}
.gpe-metric.grey {
  background: #f1f5f9;
}
.gpe-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.gpe-btn {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
}
.gpe-btn.primary {
  background: #4f46e5;
  color: #fff;
  border-color: #4f46e5;
}
.gpe-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.gpe-link-btn {
  border: none;
  background: none;
  color: #4f46e5;
  cursor: pointer;
  font-size: 11px;
  text-decoration: underline;
}
.gpe-save-status {
  margin-left: auto;
  font-size: 11px;
  color: #64748b;
}
.gpe-grid-wrap {
  overflow: auto;
  max-height: 360px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}
.gpe-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.gpe-grid th,
.gpe-grid td {
  border-bottom: 1px solid #f1f5f9;
  padding: 4px 6px;
  white-space: nowrap;
}
.gpe-grid th {
  background: #f8fafc;
  position: sticky;
  top: 0;
  z-index: 1;
}
.gpe-inp {
  width: 72px;
  padding: 2px 4px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
}
.gpe-gsm-band-0 {
  background: #ecfdf5;
}
.gpe-gsm-band-1 {
  background: #fefce8;
}
.gpe-gsm-band-2 {
  background: #fff7ed;
}
.gpe-gsm-band-3 {
  background: #fef2f2;
}
.gpe-gsm-incomplete {
  background: #f8fafc;
}
.gpe-summaries {
  margin-top: 16px;
}
.gpe-tabs button {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  cursor: pointer;
}
.gpe-tabs button.active {
  background: #4f46e5;
  color: #fff;
  border-color: #4f46e5;
}
.gpe-summary-panels {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 10px;
}
@media (max-width: 1200px) {
  .gpe-summary-panels {
    grid-template-columns: 1fr;
  }
}
.gpe-panel {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px;
  overflow: auto;
}
.gpe-panel.wide {
  grid-column: 1 / -1;
}
.gpe-panel h4 {
  margin: 0 0 6px;
  font-size: 12px;
}
.gpe-panel table {
  width: 100%;
  font-size: 11px;
  border-collapse: collapse;
}
.gpe-panel th,
.gpe-panel td {
  padding: 3px 4px;
  border-bottom: 1px solid #f1f5f9;
  text-align: right;
}
.gpe-panel th:first-child,
.gpe-panel td:first-child,
.gpe-panel th:nth-child(2),
.gpe-panel td:nth-child(2) {
  text-align: left;
}
.gpe-panel tr.total {
  font-weight: 700;
}
.gpe-progress {
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
  display: inline-block;
  width: 60px;
  vertical-align: middle;
}
.gpe-progress div {
  height: 100%;
  background: #3b82f6;
}
.gpe-note {
  font-size: 11px;
  color: #64748b;
  margin-top: 8px;
}
.gpe-muted {
  color: #94a3b8;
  font-size: 12px;
}
</style>
