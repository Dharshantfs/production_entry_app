<template>
  <div
    class="lk-container"
    :class="{
      'lk-mode-transfer': mode === 'transfer',
      'lk-mode-despatch': mode === 'despatch',
      'lk-mounted': mounted,
      'lk-gate-open': gateOpen,
    }"
  >
    <div class="lk-gate lk-gate-left" aria-hidden="true"><span class="lk-gate-label">IN</span></div>
    <div class="lk-gate lk-gate-right" aria-hidden="true"><span class="lk-gate-label">OUT</span></div>

    <div class="lk-hero">
      <div class="lk-hero-text">
        <h2 class="lk-title">Logistics</h2>
        <p class="lk-subtitle">Inter-company transfers and despatch lanes</p>
      </div>

      <div v-if="mode === 'transfer'" class="lk-truck-scene lk-scene-transfer" aria-hidden="true">
        <span class="lk-site lk-site-a">🏭</span>
        <div class="lk-road-transfer">
          <div class="lk-truck lk-truck-transfer">🚛</div>
        </div>
        <span class="lk-site lk-site-b">🏢</span>
      </div>
      <div v-else class="lk-truck-scene lk-scene-despatch" aria-hidden="true">
        <div class="lk-road-despatch">
          <div class="lk-truck lk-truck-despatch">🚛</div>
        </div>
        <span class="lk-customer">📦</span>
      </div>

      <div class="lk-toggle">
        <button type="button" :class="{ active: mode === 'transfer' }" @click="setMode('transfer')">Transfer</button>
        <button type="button" :class="{ active: mode === 'despatch' }" @click="setMode('despatch')">Despatch</button>
      </div>
    </div>

    <div class="lk-filters">
      <label>View</label>
      <select v-model="viewScope" @change="loadCards" class="lk-select lk-select-sm">
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
        <option value="all">All dates</option>
      </select>
      <template v-if="viewScope === 'daily'">
        <label>Date</label>
        <input type="date" v-model="filterDate" @change="loadCards" class="lk-input-date" />
      </template>
      <template v-else-if="viewScope === 'weekly'">
        <label>Week</label>
        <input type="week" v-model="filterWeek" @change="loadCards" class="lk-input-date" />
      </template>
      <template v-else-if="viewScope === 'monthly'">
        <label>Month</label>
        <input type="month" v-model="filterMonth" @change="loadCards" class="lk-input-date" />
      </template>
      <label>Order code</label>
      <input
        v-model="filterOrderCode"
        type="text"
        placeholder="Filter by order…"
        class="lk-input-text"
        @keyup.enter="loadCards"
      />
      <button type="button" class="cc-clear-btn" @click="loadCards">Apply</button>
    </div>

    <template v-if="mode === 'transfer'">
      <div class="lk-toolbar">
        <label>From company</label>
        <select v-model="fromCompany" @change="loadCards" class="lk-select">
          <option value="">Select company…</option>
          <option v-for="c in companies" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <label class="lk-filter-label">Show</label>
        <select v-model="historyFilter" class="lk-select lk-select-sm">
          <option value="all">All transfers</option>
          <option value="draft">Draft STE only</option>
          <option value="submitted">Submitted STE only</option>
        </select>
        <button type="button" class="lk-link-btn" @click="goApprovals">Transfer Approvals →</button>
      </div>

      <div v-if="!fromCompany" class="lk-hint">Select a company to see transfer destination cards.</div>
      <div v-else-if="!destinationCards.length" class="lk-hint">No destination companies configured.</div>

      <div v-else class="lk-grid">
        <div
          v-for="(card, idx) in destinationCards"
          :key="card.company"
          class="lk-card-wrap"
          :style="{ animationDelay: `${idx * 60}ms` }"
        >
          <button type="button" class="lk-card" @click="openTransfer(card)">
            <span class="lk-card-icon">📦</span>
            <span class="lk-card-title">{{ card.label }}</span>
            <span class="lk-card-cta">Start transfer →</span>
          </button>

          <div v-if="filteredHistory(card).length" class="lk-history-panel">
            <div class="lk-history-head">
              Transfer history
              <span class="lk-history-hint">Drag draft STEs to set queue priority</span>
            </div>
            <div
              class="lk-history-list"
              @dragover.prevent
              @drop.prevent="onHistoryDrop(card)"
            >
              <div
                v-for="ste in filteredHistory(card)"
                :key="ste.name"
                class="lk-history-chip"
                :class="{
                  'is-draft': ste.docstatus === 0,
                  'is-done': ste.docstatus === 1,
                  'is-drag-over': dragOverSteName === ste.name,
                  'is-draggable': ste.docstatus === 0,
                }"
                :draggable="ste.docstatus === 0"
                @dragstart="onHistoryDragStart(card, ste, $event)"
                @dragover.prevent="onHistoryDragOver(ste)"
                @dragleave="onHistoryDragLeave(ste)"
                @dragend="onHistoryDragEnd"
                @click.stop="openSte(ste.name)"
              >
                <span v-if="ste.docstatus === 0" class="lk-drag-grip" title="Drag to reorder">⋮⋮</span>
                <span class="lk-history-badge">{{ formatStatus(ste.status) }}</span>
                <span class="lk-history-main">
                  <span class="lk-history-ste">{{ ste.name }}</span>
                  <span class="lk-history-meta">
                    <span v-if="ste.order_codes_label">Order Code {{ ste.order_codes_label }}</span>
                    <span v-if="ste.transfer_date"> · {{ formatDate(ste.transfer_date) }}</span>
                    <span v-if="ste.qty_total"> · {{ ste.qty_total }} Kg</span>
                  </span>
                </span>
                <span class="lk-history-go">Open →</span>
              </div>
            </div>
          </div>
          <p v-else class="lk-no-history">No transfers in this period.</p>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="lk-toolbar">
        <label>From company</label>
        <select v-model="fromCompany" @change="loadDespatchCards" class="lk-select">
          <option value="">All companies…</option>
          <option v-for="c in companies" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <button type="button" class="lk-link-btn" @click="goDespatchApprovals">Despatch Approvals →</button>
      </div>

      <div v-if="!despatchCards.length" class="lk-hint">No company cards for despatch.</div>
      <div v-else class="lk-grid">
        <div v-for="(card, idx) in despatchCards" :key="card.company" class="lk-card-wrap" :style="{ animationDelay: `${idx * 60}ms` }">
          <button type="button" class="lk-card" @click="openDespatch(card)">
            <span class="lk-card-icon">📦</span>
            <span class="lk-card-title">{{ card.label }}</span>
            <span class="lk-card-cta">Start despatch →</span>
          </button>

          <div v-if="card.pending_approvals?.length" class="lk-history-panel">
            <div class="lk-history-head">Pending approval</div>
            <div class="lk-history-list">
              <div
                v-for="da in card.pending_approvals"
                :key="da.name"
                class="lk-history-chip is-pending"
                @click.stop="openDespatchApproval(da.name)"
              >
                <span class="lk-history-badge">Pending</span>
                <span class="lk-history-main">
                  <span class="lk-history-ste">{{ da.name }}</span>
                  <span class="lk-history-meta">
                    <span v-if="da.order_codes_label">Order {{ da.order_codes_label }}</span>
                    <span v-if="da.qty_total"> · {{ da.qty_total }} Kg</span>
                  </span>
                </span>
                <span class="lk-history-go">Review →</span>
              </div>
            </div>
          </div>

          <div v-if="card.approved_approvals?.length" class="lk-history-panel">
            <div class="lk-history-head">Approved despatch</div>
            <div class="lk-history-list">
              <div
                v-for="da in card.approved_approvals"
                :key="'a-' + da.name"
                class="lk-da-card"
                :class="despatchCardClass(da)"
                @click.stop="openDespatchApproval(da.name)"
              >
                <div class="lk-da-top">
                  <span class="lk-da-badge">{{ despatchCardBadge(da) }}</span>
                  <span class="lk-da-id">{{ da.name }}</span>
                </div>
                <div class="lk-da-grid">
                  <div class="lk-da-row">
                    <span class="lk-da-label">Order code</span>
                    <span class="lk-da-val">{{ da.order_codes_label || "—" }}</span>
                  </div>
                  <div class="lk-da-row">
                    <span class="lk-da-label">Customer</span>
                    <span class="lk-da-val">{{ da.customers_label || "—" }}</span>
                  </div>
                  <div class="lk-da-row">
                    <span class="lk-da-label">Items / Rolls</span>
                    <span class="lk-da-val">{{ da.item_count || 0 }} · {{ da.roll_count || 0 }} rolls</span>
                  </div>
                  <div class="lk-da-row">
                    <span class="lk-da-label">Qty</span>
                    <span class="lk-da-val">{{ da.qty_total || 0 }} Kg</span>
                  </div>
                </div>
                <button
                  v-if="da.dn_docstatus < 1"
                  type="button"
                  class="lk-dn-btn"
                  @click.stop="openDeliveryNote(da)"
                >
                  {{ despatchDnButtonLabel(da) }}
                </button>
                <button
                  v-else
                  type="button"
                  class="lk-dn-btn lk-dn-btn-done"
                  @click.stop="openDeliveryNote(da)"
                >
                  Despatched — Open DN
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <TransferDialog
      v-model="showDialog"
      board-kind="production"
      :filter-context="dialogFilters"
      :prefill="dialogPrefill"
      @submitted="loadCards"
    />
    <DespatchDialog
      v-model="showDespatchDialog"
      board-kind="production"
      :filter-context="dialogFilters"
      :prefill="despatchPrefill"
      @submitted="onDespatchSubmitted"
    />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import TransferDialog from "./TransferDialog.vue";
import DespatchDialog from "./DespatchDialog.vue";

const API = "production_entry.production_planning.transfer_logistics";
const DESPATCH_API = "production_entry.production_planning.despatch_logistics";
const mode = ref("transfer");
const mounted = ref(false);
const gateOpen = ref(false);
const historyFilter = ref("all");
const viewScope = ref("daily");
const filterDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref("");
const filterOrderCode = ref("");
const companies = ref([]);
const fromCompany = ref("Jayashree Spun Bond - 1ZT");
const destinationCards = ref([]);
const showDialog = ref(false);
const showDespatchDialog = ref(false);
const dialogPrefill = ref({});
const despatchPrefill = ref({});
const despatchCards = ref([]);
const dialogFilters = ref({ view_scope: "daily", date: frappe.datetime.get_today() });
const dragLane = ref(null);
const dragSte = ref(null);
const dragOverSteName = ref("");
let refreshTimer = null;

function initWeekMonth() {
  const d = new Date();
  if (!filterWeek.value) {
    const onejan = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil(((d - onejan) / 86400000 + onejan.getDay() + 1) / 7);
    filterWeek.value = `${d.getFullYear()}-W${String(week).padStart(2, "0")}`;
  }
  if (!filterMonth.value) {
    filterMonth.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  }
}

function setMode(m) {
  mode.value = m;
  if (m === "despatch") loadDespatchCards();
  else loadCards();
}

function formatDate(d) {
  if (!d) return "";
  try {
    return frappe.datetime.str_to_user(d);
  } catch {
    return String(d).slice(0, 10);
  }
}

function filteredHistory(card) {
  const list = card.transfer_history || card.draft_stock_entries || [];
  if (historyFilter.value === "draft") {
    return list.filter((x) => x.docstatus === 0 || x.status === "Draft");
  }
  if (historyFilter.value === "submitted") {
    return list.filter((x) => x.docstatus === 1 || x.status === "Submitted");
  }
  return list;
}

function draftSteOrder(card) {
  return filteredHistory(card)
    .filter((s) => s.docstatus === 0)
    .map((s) => s.name);
}

function formatStatus(status) {
  if (!status) return "";
  if (status.startsWith("Transferred")) return "Transferred";
  return status;
}

function onHistoryDragStart(card, ste, ev) {
  if (ste.docstatus !== 0) {
    ev.preventDefault();
    return;
  }
  dragLane.value = card;
  dragSte.value = ste;
  try {
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", ste.name);
  } catch (e) {}
}

function onHistoryDragOver(ste) {
  if (ste.docstatus !== 0) return;
  dragOverSteName.value = ste.name;
}

function onHistoryDragLeave(ste) {
  if (dragOverSteName.value === ste.name) dragOverSteName.value = "";
}

function onHistoryDragEnd() {
  dragSte.value = null;
  dragLane.value = null;
  dragOverSteName.value = "";
}

async function onHistoryDrop(card) {
  const drag = dragSte.value;
  const lane = dragLane.value;
  if (!drag || !lane || lane.company !== card.company) {
    onHistoryDragEnd();
    return;
  }
  const drafts = draftSteOrder(card);
  const from = drag.name;
  const to = dragOverSteName.value;
  if (to && from !== to) {
    const fi = drafts.indexOf(from);
    const ti = drafts.indexOf(to);
    if (fi >= 0 && ti >= 0) {
      drafts.splice(fi, 1);
      drafts.splice(ti, 0, from);
    }
  }
  try {
    await frappe.call({
      method: `${API}.reorder_transfer_lane_queue`,
      args: {
        from_company: fromCompany.value,
        to_company: card.company,
        ste_names: JSON.stringify(drafts),
      },
    });
    frappe.show_alert({ message: __("Queue order saved"), indicator: "green" });
  } catch (e) {
    frappe.show_alert({ message: __("Could not save queue order"), indicator: "red" });
  }
  onHistoryDragEnd();
  await loadCards();
}

function cardLoadArgs() {
  const args = { from_company: fromCompany.value };
  if (viewScope.value !== "all") {
    args.view_scope = viewScope.value;
    if (viewScope.value === "daily") args.date = filterDate.value;
    if (viewScope.value === "weekly") args.week = filterWeek.value;
    if (viewScope.value === "monthly") args.month = filterMonth.value;
  } else {
    args.view_scope = "all";
  }
  if ((filterOrderCode.value || "").trim()) {
    args.order_code = filterOrderCode.value.trim();
  }
  return args;
}

async function loadCompanies() {
  const r = await frappe.call({ method: `${API}.get_logistics_companies` });
  companies.value = r.message || [];
}

async function loadCards() {
  if (!fromCompany.value) {
    destinationCards.value = [];
    return;
  }
  dialogFilters.value = {
    view_scope: viewScope.value === "all" ? "daily" : viewScope.value,
    date: filterDate.value,
    week: filterWeek.value,
    month: filterMonth.value,
    party_code: filterOrderCode.value,
  };
  const r = await frappe.call({
    method: `${API}.get_transfer_destination_cards`,
    args: cardLoadArgs(),
  });
  destinationCards.value = r.message || [];
}

function openTransfer(card) {
  dialogPrefill.value = {
    from_company: fromCompany.value,
    to_company: card.company,
    party_code: filterOrderCode.value || "",
    customer: "",
  };
  showDialog.value = true;
}

function openSte(name) {
  frappe.set_route("Form", "Stock Entry", name);
}

function goApprovals() {
  frappe.set_route("transfer-approval-dashboard");
}

function goDespatchApprovals() {
  frappe.set_route("despatch-approval-dashboard");
}

async function loadDespatchCards() {
  dialogFilters.value = {
    view_scope: viewScope.value === "all" ? "daily" : viewScope.value,
    date: filterDate.value,
    week: filterWeek.value,
    month: filterMonth.value,
    party_code: filterOrderCode.value,
  };
  const args = { from_company: fromCompany.value || "" };
  if (viewScope.value !== "all") {
    args.view_scope = viewScope.value;
    if (viewScope.value === "daily") args.date = filterDate.value;
    if (viewScope.value === "weekly") args.week = filterWeek.value;
    if (viewScope.value === "monthly") args.month = filterMonth.value;
  } else {
    args.view_scope = "all";
  }
  if ((filterOrderCode.value || "").trim()) args.order_code = filterOrderCode.value.trim();
  const r = await frappe.call({ method: `${DESPATCH_API}.get_despatch_company_cards`, args });
  despatchCards.value = r.message || [];
}

function openDespatch(card) {
  despatchPrefill.value = {
    from_company: card.company || fromCompany.value,
  };
  showDespatchDialog.value = true;
}

function openDespatchApproval(name) {
  frappe.route_options = { approval: name };
  frappe.set_route("despatch-approval-dashboard");
}

function despatchCardBadge(da) {
  if (da.dn_docstatus >= 1 || da.card_status === "Despatched") return "Despatched";
  if (da.delivery_note || da.card_status === "Draft DN") return "Draft DN";
  return "Approved";
}

function despatchCardClass(da) {
  if (da.dn_docstatus >= 1) return "is-despatched";
  if (da.delivery_note) return "is-draft-dn";
  return "is-done";
}

function despatchDnButtonLabel(da) {
  if (da.delivery_note) return __("Open Draft DN");
  return __("Create Delivery Note");
}

async function openDeliveryNote(da) {
  if (!da?.name) return;
  if (da.delivery_note) {
    frappe.set_route("Form", "Delivery Note", da.delivery_note);
    return;
  }
  try {
    const r = await frappe.call({
      method: `${DESPATCH_API}.prepare_delivery_note_from_despatch_approval`,
      args: { name: da.name },
    });
    const msg = r.message || {};
    if (msg.mode === "existing" && msg.delivery_note) {
      frappe.set_route("Form", "Delivery Note", msg.delivery_note);
      return;
    }
    if (msg.mode !== "new" || !msg.doc) {
      frappe.msgprint(__("Could not open Delivery Note."));
      return;
    }
    frappe.model.with_doctype("Delivery Note", () => {
      const local = frappe.model.make_new_doc_and_get_name("Delivery Note");
      const target = locals["Delivery Note"][local];
      const src = msg.doc;
      Object.keys(src).forEach((k) => {
        if (["items", "doctype", "name", "__islocal", "__unsaved"].includes(k)) return;
        target[k] = src[k];
      });
      (src.items || []).forEach((row) => {
        const child = frappe.model.add_child(target, "Delivery Note Item", "items");
        Object.keys(row).forEach((k) => {
          if (["name", "parent", "parenttype", "parentfield", "doctype"].includes(k)) return;
          child[k] = row[k];
        });
      });
      frappe.route_options = { despatch_approval: da.name };
      frappe.set_route("Form", "Delivery Note", local);
    });
  } catch (e) {
    frappe.msgprint(e?.message || String(e));
  }
}

function onDespatchSubmitted() {
  loadDespatchCards();
}

function reloadBoard() {
  if (mode.value === "despatch") loadDespatchCards();
  else loadCards();
}

watch(fromCompany, reloadBoard);
watch([viewScope, filterDate, filterWeek, filterMonth, filterOrderCode], reloadBoard);

onMounted(() => {
  initWeekMonth();
  requestAnimationFrame(() => {
    mounted.value = true;
    setTimeout(() => {
      gateOpen.value = true;
    }, 120);
  });
  loadCompanies();
  loadCards();
  refreshTimer = window.setInterval(() => {
    if (showDialog.value || showDespatchDialog.value) return;
    if (mode.value === "despatch") loadDespatchCards();
    else loadCards();
  }, 5000);
});

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
});
</script>

<style scoped>
.lk-container {
  position: relative;
  padding: 20px 24px 32px;
  font-family: system-ui, sans-serif;
  background: linear-gradient(160deg, #f0f9ff 0%, #f8fafc 45%, #f1f5f9 100%);
  min-height: calc(100vh - 80px);
  opacity: 0;
  transform: translateY(10px);
  transition: opacity 0.45s ease, transform 0.45s ease;
  overflow: hidden;
}
.lk-container.lk-mounted {
  opacity: 1;
  transform: none;
}
.lk-gate {
  position: fixed;
  top: 0;
  bottom: 0;
  width: 48vw;
  background: linear-gradient(90deg, #042f49 0%, #0c4a6e 40%, #0369a1 100%);
  z-index: 9998;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.6s ease;
  box-shadow: 0 0 40px rgba(3, 105, 161, 0.45);
}
.lk-gate-label {
  color: rgba(255, 255, 255, 0.35);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.2em;
}
.lk-gate-left {
  left: 0;
  transform-origin: left center;
}
.lk-gate-right {
  right: 0;
  transform-origin: right center;
  background: linear-gradient(270deg, #042f49 0%, #0c4a6e 40%, #0369a1 100%);
}
.lk-container:not(.lk-gate-open) .lk-gate-left {
  transform: translateX(0);
  opacity: 1;
}
.lk-container:not(.lk-gate-open) .lk-gate-right {
  transform: translateX(0);
  opacity: 1;
}
.lk-container.lk-gate-open .lk-gate-left {
  transform: translateX(-102%);
  opacity: 0.6;
}
.lk-container.lk-gate-open .lk-gate-right {
  transform: translateX(102%);
  opacity: 0.6;
}
.lk-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
  margin-bottom: 16px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #0c4a6e 0%, #0369a1 55%, #0ea5e9 100%);
  border-radius: 16px;
  color: #ffffff;
  box-shadow: 0 8px 24px rgba(3, 105, 161, 0.25);
  position: relative;
  z-index: 1;
  overflow: hidden;
}
.lk-title {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  color: #ffffff;
}
.lk-subtitle {
  margin: 6px 0 0;
  color: rgba(255, 255, 255, 0.92);
  font-size: 13px;
  font-weight: 600;
}
.lk-hero-text {
  flex: 1;
  min-width: 180px;
}
.lk-scene-transfer {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  width: 260px;
  min-height: 48px;
}
.lk-site {
  font-size: 24px;
  line-height: 1;
  opacity: 0.95;
  flex-shrink: 0;
}
.lk-road-transfer {
  position: relative;
  flex: 1;
  height: 36px;
  border-bottom: 3px dashed rgba(255, 255, 255, 0.55);
}
.lk-truck-transfer {
  position: absolute;
  bottom: 8px;
  left: 0;
  font-size: 24px;
  line-height: 1;
  transform: scaleX(-1);
  animation: lk-transfer-end-to-end 5s linear infinite;
}
@keyframes lk-transfer-end-to-end {
  0% {
    left: 0;
    transform: scaleX(-1);
  }
  48% {
    left: calc(100% - 28px);
    transform: scaleX(-1);
  }
  50% {
    left: calc(100% - 28px);
    transform: scaleX(1);
  }
  98% {
    left: 0;
    transform: scaleX(1);
  }
  100% {
    left: 0;
    transform: scaleX(-1);
  }
}
.lk-scene-despatch {
  position: relative;
  width: 220px;
  height: 44px;
  flex-shrink: 0;
}
.lk-road-despatch {
  position: absolute;
  bottom: 6px;
  left: 0;
  right: 40px;
  height: 4px;
  background: rgba(255, 255, 255, 0.45);
  border-radius: 2px;
}
.lk-truck-despatch {
  position: absolute;
  bottom: 10px;
  left: 0;
  font-size: 24px;
  /* Emoji truck faces left by default — flip so it runs toward customer (right). */
  transform: scaleX(-1);
  animation: lk-despatch-to-customer 4s ease-in-out infinite;
}
.lk-customer {
  position: absolute;
  bottom: 8px;
  right: 0;
  font-size: 26px;
}
@keyframes lk-despatch-to-customer {
  0% {
    left: 0;
    transform: scaleX(1);
  }
  92% {
    left: calc(100% - 36px);
    transform: scaleX(1);
  }
  100% {
    left: calc(100% - 36px);
    transform: scaleX(1);
  }
}
.lk-toggle {
  display: flex;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.35);
  z-index: 1;
}
.lk-toggle button {
  padding: 10px 20px;
  border: none;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}
.lk-toggle button.active {
  background: #fff;
  color: #0369a1;
}
.lk-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  position: relative;
  z-index: 1;
}
.lk-filters label {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
}
.lk-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  position: relative;
  z-index: 1;
}
.lk-toolbar label {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}
.lk-select {
  min-width: 260px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
}
.lk-select-sm {
  min-width: 150px;
}
.lk-input-date,
.lk-input-text {
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  font-size: 13px;
}
.lk-input-text {
  min-width: 140px;
}
.lk-link-btn {
  margin-left: auto;
  background: #fff;
  border: 1px solid #0ea5e9;
  color: #0369a1;
  padding: 8px 14px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}
.lk-hint,
.lk-no-history {
  color: #64748b;
  padding: 16px;
  text-align: center;
  font-size: 13px;
}
.lk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  position: relative;
  z-index: 1;
}
.lk-card-wrap {
  opacity: 0;
  animation: lk-card-in 0.45s ease forwards;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
@keyframes lk-card-in {
  to {
    opacity: 1;
    transform: none;
  }
}
.lk-card {
  text-align: left;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 20px 18px;
  cursor: pointer;
  background: #fff;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lk-card:hover {
  border-color: #0ea5e9;
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.12);
}
.lk-card-icon {
  font-size: 28px;
}
.lk-card-title {
  font-size: 17px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.25;
}
.lk-card-cta {
  font-size: 13px;
  font-weight: 700;
  color: #0284c7;
  margin-top: 4px;
}
.lk-history-panel {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px;
}
.lk-history-head {
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  color: #475569;
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.lk-history-hint {
  font-size: 10px;
  font-weight: 600;
  text-transform: none;
  color: #94a3b8;
}
.lk-history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lk-history-chip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  border-radius: 10px;
  padding: 12px 12px;
  cursor: pointer;
  border: 1px solid #e2e8f0;
  background: #fff;
  text-align: left;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}
.lk-history-chip.is-draggable {
  cursor: grab;
}
.lk-history-chip.is-drag-over {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.25);
}
.lk-history-chip.is-draft {
  border-color: #fcd34d;
  background: #fffbeb;
}
.lk-history-chip.is-done {
  border-color: #86efac;
  background: #f0fdf4;
}
.lk-drag-grip {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1;
  padding-top: 2px;
  user-select: none;
}
.lk-history-badge {
  font-size: 10px;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: 6px;
  color: #fff;
  flex-shrink: 0;
}
.lk-history-chip.is-draft .lk-history-badge {
  background: #f59e0b;
}
.lk-history-chip.is-done .lk-history-badge {
  background: #16a34a;
}
.lk-history-main {
  flex: 1;
  min-width: 0;
}
.lk-history-ste {
  font-size: 14px;
  font-weight: 800;
  font-family: ui-monospace, monospace;
  color: #0f172a;
  display: block;
}
.lk-history-meta {
  font-size: 13px;
  color: #475569;
  display: block;
  margin-top: 4px;
  line-height: 1.35;
}
.lk-history-chip.is-pending .lk-history-badge {
  background: #ea580c;
}
.lk-history-chip.is-despatched .lk-history-badge {
  background: #0369a1;
}
.lk-history-chip.is-despatched {
  border-color: #bae6fd;
  background: #f0f9ff;
}
.lk-da-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid #bbf7d0;
  background: #f0fdf4;
  cursor: pointer;
}
.lk-da-card.is-draft-dn {
  border-color: #fde68a;
  background: #fffbeb;
}
.lk-da-card.is-despatched {
  border-color: #bae6fd;
  background: #f0f9ff;
}
.lk-da-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.lk-da-badge {
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 6px;
  background: #16a34a;
  color: #fff;
}
.lk-da-card.is-draft-dn .lk-da-badge {
  background: #d97706;
}
.lk-da-card.is-despatched .lk-da-badge {
  background: #0369a1;
}
.lk-da-id {
  font-size: 12px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: #334155;
}
.lk-da-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 14px;
}
.lk-da-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.lk-da-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #64748b;
  letter-spacing: 0.03em;
}
.lk-da-val {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  word-break: break-word;
}
.lk-dn-btn {
  align-self: flex-start;
  flex-shrink: 0;
  padding: 8px 14px;
  border-radius: 8px;
  border: none;
  background: #16a34a;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.lk-dn-btn:hover {
  background: #15803d;
}
.lk-dn-btn-done {
  background: #0369a1;
}
.lk-dn-btn-done:hover {
  background: #075985;
}
.lk-history-go {
  font-size: 12px;
  font-weight: 700;
  color: #0284c7;
  flex-shrink: 0;
  padding-top: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .lk-gate,
  .lk-truck-transfer,
  .lk-truck-despatch,
  .lk-card-wrap,
  .lk-container {
    animation: none !important;
    transition: none !important;
  }
}
</style>
