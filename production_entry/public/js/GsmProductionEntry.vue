<template>
  <div class="gpe-root">
    <div class="gpe-info-strip">
      Phase 1 — entries save locally. Submit Entry and label print connect in Phase 2.
    </div>

    <div class="gpe-page-tabs">
      <button type="button" :class="{ active: pageTab === 'entry' }" @click="pageTab = 'entry'">Entry</button>
      <button type="button" :class="{ active: pageTab === 'summary' }" @click="pageTab = 'summary'">Summary</button>
      <button type="button" :class="{ active: pageTab === 'shift' }" @click="openShiftTab">Shift Entries</button>
    </div>

    <div v-if="pageTab !== 'shift'" class="gpe-filters gpe-card">
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
          <option value="">Select unit</option>
          <option v-for="u in unitOptions" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>
      <div class="gpe-filter">
        <label>Search</label>
        <input v-model="searchText" type="text" placeholder="Order / party..." />
      </div>
      <button type="button" class="gpe-btn" @click="fetchOrders">Refresh</button>
    </div>

    <!-- Entry tab -->
    <div v-show="pageTab === 'entry'" class="gpe-layout">
      <aside class="gpe-sidebar gpe-card">
        <h3>Orders &amp; GSM</h3>
        <p class="gpe-hint">PP-submitted lines. Confirm selection, then add roll rows.</p>
        <div v-if="loadingOrders" class="gpe-muted">Loading…</div>
        <div v-else-if="!orderGroups.length" class="gpe-muted">
          No PP-submitted orders for this date/unit.
        </div>

        <div v-for="grp in filteredActiveGroups" :key="grp.key" class="gpe-order-card">
          <div class="gpe-order-head">
            <span class="gpe-order-code">{{ grp.orderCode }}</span>
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
            class="gpe-line-card"
            :class="lineRowClass(line)"
            :title="line.tooltip"
          >
            <input
              type="checkbox"
              class="gpe-line-check"
              :checked="selectedLineIds.has(line.id)"
              :disabled="!line.selectable || selectionLocked"
              @change="toggleLine(line.id, $event)"
            />
            <div class="gpe-line-body" @click.prevent="onLineLabelClick(line)">
              <div class="gpe-line-meta">
                <span class="gpe-quality">{{ line.quality }}</span>
                <span class="gpe-color">{{ line.color }}</span>
              </div>
              <div class="gpe-line-spec">
                <strong class="gpe-gsm">{{ line.gsm }} GSM</strong>
                <span>{{ line.widthLabel }}</span>
                <span class="gpe-day-target">Tgt {{ formatKg(line.dayTargetKg) }} Kg</span>
                <span class="gpe-day-rem">Rem {{ formatKg(line.dayRemKg) }} Kg</span>
              </div>
              <div v-if="line.rollQuota || line.mergeBadge || line.chip" class="gpe-line-foot">
                <div v-if="line.rollQuota" class="gpe-roll-meter" :class="{ 'gpe-roll-meter-full': line.rollQuota.isFull }" :title="line.rollQuota.tooltip">
                  <div class="gpe-roll-meter-head">
                    <span class="gpe-roll-meter-title">Rolls · {{ shift }}</span>
                    <span class="gpe-roll-meter-frac">
                      <em>{{ line.rollQuota.current }}</em>
                      <span>/</span>
                      <strong>{{ line.rollQuota.shiftMax }}</strong>
                    </span>
                  </div>
                  <div v-if="line.rollQuota.priorShifts.length || line.rollQuota.dayTotal > line.rollQuota.current" class="gpe-roll-meter-sub">
                    <span
                      v-for="ps in line.rollQuota.priorShifts"
                      :key="ps.shift"
                      class="gpe-roll-prior"
                    >{{ ps.shift }} {{ ps.rolls }} done</span>
                    <span class="gpe-roll-day">Day {{ line.rollQuota.dayTotal }}/{{ line.rollQuota.jobMax }}</span>
                  </div>
                </div>
                <span v-if="line.mergeBadge" class="gpe-chip gpe-chip-merge">{{ line.mergeBadge }}</span>
                <span v-if="line.chip" :class="['gpe-chip', line.chipClass]">{{ line.chip }}</span>
              </div>
            </div>
          </label>
        </div>

        <div v-if="filteredCompletedGroups.length" class="gpe-sidebar-section">
          <button type="button" class="gpe-collapse-btn" @click="showCompletedOrders = !showCompletedOrders">
            {{ showCompletedOrders ? "▼" : "▶" }} Completed orders ({{ completedLineCount }})
          </button>
          <div v-show="showCompletedOrders">
            <div v-for="grp in filteredCompletedGroups" :key="'c-' + grp.key" class="gpe-order-card gpe-completed">
              <div class="gpe-order-head">
                <span class="gpe-order-code">{{ grp.orderCode }}</span>
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
                class="gpe-line-card gpe-line-disabled"
                :title="line.tooltip"
              >
                <input type="checkbox" class="gpe-line-check" disabled />
                <div class="gpe-line-body">
                  <div class="gpe-line-meta">
                    <span class="gpe-quality">{{ line.quality }}</span>
                    <span class="gpe-color">{{ line.color }}</span>
                  </div>
                  <div class="gpe-line-spec">
                    <strong class="gpe-gsm">{{ line.gsm }} GSM</strong>
                    <span>{{ line.widthLabel }}</span>
                    <span class="gpe-day-target">Tgt {{ formatKg(line.dayTargetKg) }} Kg</span>
                    <span class="gpe-day-rem">Rem {{ formatKg(line.dayRemKg) }} Kg</span>
                  </div>
                  <div v-if="line.rollQuota || line.mergeBadge || line.chip" class="gpe-line-foot">
                    <div v-if="line.rollQuota" class="gpe-roll-meter gpe-roll-meter-done" :title="line.rollQuota.tooltip">
                      <div class="gpe-roll-meter-head">
                        <span class="gpe-roll-meter-title">Rolls</span>
                        <span class="gpe-roll-meter-frac">
                          <em>{{ line.rollQuota.current }}</em>
                          <span>/</span>
                          <strong>{{ line.rollQuota.shiftMax }}</strong>
                        </span>
                      </div>
                      <div v-if="line.rollQuota.dayTotal" class="gpe-roll-meter-sub">
                        <span class="gpe-roll-day">Day {{ line.rollQuota.dayTotal }}/{{ line.rollQuota.jobMax }}</span>
                      </div>
                    </div>
                    <span v-if="line.mergeBadge" class="gpe-chip gpe-chip-merge">{{ line.mergeBadge }}</span>
                    <span :class="['gpe-chip', line.chipClass]">{{ line.chip }}</span>
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>
      </aside>

      <main class="gpe-main gpe-card">
        <div class="gpe-header gpe-card-inner">
          <div class="gpe-tags">
            <span v-for="t in headerTags" :key="t" class="gpe-tag">{{ t }}</span>
          </div>
          <div class="gpe-header-fields">
            <label>Run Date <input type="date" v-model="runDate" /></label>
            <label>
              Shift
              <select v-model="shift">
                <option value="Day Shift">Day Shift</option>
                <option value="Night Shift">Night Shift</option>
              </select>
            </label>
            <label>Unit <input v-model="headerUnit" type="text" readonly /></label>
            <label>Operator <input v-model="operator" type="text" /></label>
            <label>Supervisor <input v-model="supervisor" type="text" /></label>
          </div>
          <div v-if="selectedSummary || selectedLineIds.size" class="gpe-selection-strip">
            <div class="gpe-selection-text">
              <strong>{{ selectedSummary?.count || 0 }}</strong> line(s) ·
              Day plan <strong>{{ formatKg(selectedSummary?.dayPlanned || 0) }}</strong> Kg ·
              Session rem <strong>{{ formatKg(metrics.dayRemaining) }}</strong> Kg
              <span v-if="selectionLocked" class="gpe-lock-badge inline">Locked</span>
            </div>
            <div class="gpe-selection-actions">
              <button
                v-if="!selectionLocked"
                type="button"
                class="gpe-btn primary sm"
                :disabled="!selectedLineIds.size"
                @click="openConfirmSelection"
              >Confirm selection</button>
              <button
                v-else
                type="button"
                class="gpe-btn sm"
                @click="unlockSelection"
              >Unlock</button>
              <button type="button" class="gpe-link-btn" @click="clearSelection">Clear</button>
            </div>
          </div>
        </div>

        <div class="gpe-metrics">
          <div class="gpe-metric slate">Board plan (Kg)<br /><strong>{{ formatKg(boardDayTotalKg) }}</strong></div>
          <div class="gpe-metric blue">Total Entry (Kg)<br /><strong>{{ formatKg(metrics.totalGross) }}</strong></div>
          <div class="gpe-metric green">Net Production (Kg)<br /><strong>{{ formatKg(metrics.totalNet) }}</strong></div>
          <div class="gpe-metric orange">Day remaining (Kg)<br /><strong>{{ formatKg(metrics.dayRemaining) }}</strong></div>
          <div class="gpe-metric grey">Rolls<br /><strong>{{ rollLines.length }}</strong></div>
        </div>

        <div class="gpe-toolbar">
          <div class="gpe-toolbar-left">
            <button type="button" class="gpe-btn primary" :disabled="!canAddRow" @click="addRollRow">Add Roll Row</button>
            <button type="button" class="gpe-btn" :disabled="!rollLines.length" @click="removeTopRow">Remove Top Row</button>
          </div>
          <span class="gpe-save-status">{{ saveStatus }}</span>
          <div class="gpe-toolbar-right">
            <div class="gpe-tools-wrap" v-click-outside="closeToolsMenu">
              <button
                type="button"
                class="gpe-btn"
                :disabled="!toolsEnabled"
                :title="toolsHint"
                @click="toolsMenuOpen = !toolsMenuOpen"
              >Tools ▾</button>
              <div v-if="toolsMenuOpen && toolsEnabled" class="gpe-tools-menu">
                <button type="button" @click="runTool('manual')">SPR — Manual job</button>
                <button type="button" @click="runTool('trail')">SPR — Trail Order</button>
                <button type="button" @click="runTool('bundle')">SPR — Bundle packaging</button>
                <button type="button" @click="runTool('rmbatches')">SPR — Select RM batches</button>
              </div>
            </div>
            <button type="button" class="gpe-btn disabled" disabled title="Phase 2">Submit Entry</button>
          </div>
        </div>

        <div class="gpe-gsm-legend">
          <span class="gpe-legend-title">GSM diff (Sticker vs Produced):</span>
          <span class="gpe-legend-chip gpe-gsm-band-0">|diff| &lt; 1</span>
          <span class="gpe-legend-chip gpe-gsm-band-1">1 – 2</span>
          <span class="gpe-legend-chip gpe-gsm-band-2">2 – 3</span>
          <span class="gpe-legend-chip gpe-gsm-band-3">≥ 3</span>
          <span class="gpe-legend-chip gpe-gsm-incomplete">Awaiting / incomplete</span>
        </div>

        <div class="gpe-grid-wrap">
          <table class="gpe-grid">
            <thead>
              <tr>
                <th>#</th>
                <th>Order</th>
                <th>Quality</th>
                <th>Color</th>
                <th>Sticker GSM</th>
                <th>Width</th>
                <th>Ord Len</th>
                <th>Prod Len</th>
                <th>Prod GSM</th>
                <th>Batch</th>
                <th>Net</th>
                <th>Gross</th>
                <th>Planned Qty</th>
                <th>UOM</th>
                <th>WO</th>
                <th>Core mm</th>
                <th>Polybag</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, idx) in rollLines"
                :key="row._id"
                :class="[rowBandClass(row), { 'gpe-row-locked': row.row_locked }]"
              >
                <td>{{ rollLines.length - idx }}</td>
                <td>{{ row.party_code }}</td>
                <td>{{ row.quality }}</td>
                <td>{{ row.color }}</td>
                <td>{{ row.gsm }}</td>
                <td>{{ row.width_inch }}</td>
                <td>{{ row.meter_roll }}</td>
                <td>
                  <input
                    v-model.number="row.produced_length_mtrs"
                    type="number"
                    step="0.01"
                    class="gpe-inp"
                    :disabled="row.row_locked"
                    @input="onRowEdit(row)"
                  />
                </td>
                <td>{{ row.produced_gsm }}</td>
                <td>{{ row.batch_no }}</td>
                <td>{{ row.net_weight }}</td>
                <td>
                  <input
                    v-model="row.gross_weight"
                    type="text"
                    class="gpe-inp"
                    :disabled="row.row_locked"
                    @input="onRowEdit(row)"
                  />
                </td>
                <td>{{ formatKg(row.planned_qty) }}</td>
                <td>{{ row.uom || "Kg" }}</td>
                <td>
                  <a
                    v-if="row.work_order"
                    href="#"
                    class="gpe-wo-link"
                    @click.prevent="openWorkOrder(row.work_order)"
                  >{{ row.work_order }}</a>
                </td>
                <td>
                  <select
                    v-model.number="row.custom_core_width_mm"
                    class="gpe-inp gpe-inp-wide"
                    :disabled="row.row_locked"
                    @change="onRowEdit(row)"
                  >
                    <option v-for="opt in coreWidthOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                </td>
                <td>{{ formatKg(row.custom_polybag_kgs) }}</td>
                <td class="gpe-actions">
                  <button
                    v-if="!row.row_locked"
                    type="button"
                    class="gpe-btn sm"
                    @click="saveRow(row)"
                  >Save Row</button>
                  <button
                    v-else
                    type="button"
                    class="gpe-btn sm"
                    @click="editRow(row)"
                  >Edit Row</button>
                  <button
                    type="button"
                    class="gpe-btn sm"
                    :disabled="!row.row_locked"
                    :title="row.row_locked ? 'Label stub until Phase 2' : 'Save Row first'"
                    @click="printLabel(row)"
                  >Label</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>
    </div>

    <!-- Summary tab -->
    <div v-show="pageTab === 'summary'" class="gpe-main gpe-card gpe-summary-tab">
      <div class="gpe-tabs">
        <button :class="{ active: summaryTab === 'summary' }" @click="summaryTab = 'summary'">Summary</button>
        <button :class="{ active: summaryTab === 'linked' }" @click="summaryTab = 'linked'">Linked Orders</button>
      </div>
      <div v-show="summaryTab === 'summary'" class="gpe-summary-panels">
        <div class="gpe-panel gpe-card-inner">
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
        <div class="gpe-panel gpe-card-inner">
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
        <div class="gpe-panel gpe-card-inner">
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
        Entries are captured roll-wise with batch reference. Backend SPR submit connects in Phase 2.
      </p>
      <div v-show="summaryTab === 'linked'" class="gpe-panel wide gpe-card-inner">
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

    <!-- Shift Entries tab -->
    <div v-show="pageTab === 'shift'" class="gpe-shift-layout">
      <div class="gpe-shift-filters gpe-card">
        <span class="gpe-shift-filter-title">Submitted SPRs for shift</span>
        <label>Date <input type="date" v-model="shiftFilterDate" /></label>
        <label>
          Shift
          <select v-model="shiftFilterShift">
            <option value="Day Shift">Day Shift</option>
            <option value="Night Shift">Night Shift</option>
          </select>
        </label>
        <label>
          Unit
          <select v-model="shiftFilterUnit">
            <option value="">All fabric units</option>
            <option v-for="u in fabricUnitOptions" :key="'su-' + u" :value="u">{{ u }}</option>
          </select>
        </label>
        <button type="button" class="gpe-btn primary" @click="loadShiftEntries">Refresh</button>
      </div>

      <div v-if="shiftLoading" class="gpe-muted gpe-card">Loading shift entries…</div>
      <div v-else-if="!shiftEntries.length" class="gpe-empty-state gpe-card">
        <h3>No submitted entries for this shift</h3>
        <p>Submitted SPRs for the selected date, shift, and unit appear here.</p>
      </div>
      <div v-else class="gpe-shift-split">
        <aside class="gpe-shift-sidebar gpe-card">
          <div
            v-for="entry in shiftEntries"
            :key="entry.spr_name"
            class="gpe-shift-card"
            :class="{ active: selectedShiftEntry?.spr_name === entry.spr_name }"
            @click="selectedShiftEntry = entry"
          >
            <div class="gpe-shift-card-title">{{ entry.spr_name }}</div>
            <div class="gpe-shift-card-meta">
              {{ entry.order_codes?.join(", ") || "—" }}
            </div>
            <div class="gpe-shift-card-stats">
              {{ entry.roll_count }} rolls · {{ formatKg(entry.total_net_kg) }} Kg net
            </div>
            <span class="gpe-chip gpe-chip-submitted">Submitted</span>
          </div>
        </aside>
        <div v-if="selectedShiftEntry" class="gpe-shift-detail gpe-card">
          <div class="gpe-shift-detail-head">
            <h3>{{ selectedShiftEntry.spr_name }}</h3>
            <button type="button" class="gpe-btn sm" @click="openSpr(selectedShiftEntry.spr_name)">Open SPR</button>
          </div>
          <p class="gpe-shift-meta">
            PP: <a href="#" @click.prevent="viewPP(selectedShiftEntry.production_plan)">{{ selectedShiftEntry.production_plan }}</a>
            · Operator: {{ selectedShiftEntry.operator || "—" }}
            · Supervisor: {{ selectedShiftEntry.supervisor || "—" }}
          </p>
          <div v-if="selectedShiftEntry.wo_status?.length" class="gpe-wo-chips">
            <span
              v-for="wo in selectedShiftEntry.wo_status"
              :key="wo.name"
              :class="['gpe-chip', wo.status === 'Completed' ? 'gpe-chip-done' : 'gpe-chip-draft']"
            >{{ wo.name }} ({{ wo.status }})</span>
          </div>
          <table class="gpe-grid">
            <thead>
              <tr>
                <th>Batch</th><th>GSM</th><th>Width</th><th>Net</th><th>Gross</th><th>Order</th><th>WO</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in selectedShiftEntry.rolls" :key="i">
                <td>{{ r.batch_no }}</td>
                <td>{{ r.gsm }}</td>
                <td>{{ r.width_inch }}</td>
                <td>{{ formatKg(r.net_weight) }}</td>
                <td>{{ formatKg(r.gross_weight) }}</td>
                <td>{{ r.party_code }}</td>
                <td>{{ r.work_order }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="gpe-shift-detail gpe-card gpe-muted">Select an entry to view rolls.</div>
      </div>
    </div>

    <!-- Confirm selection dialog -->
    <div v-if="showConfirmDialog" class="gpe-dialog-overlay" @click.self="showConfirmDialog = false">
      <div class="gpe-dialog gpe-card">
        <h3>Confirm GSM selection</h3>
        <p>Lock these lines for roll entry? You can unlock later.</p>
        <ul class="gpe-confirm-list">
          <li v-for="line in confirmLines" :key="line.id">
            {{ line.orderCode }} · {{ line.quality }} · {{ line.color }} · {{ line.gsm }} GSM · {{ line.widthLabel }} · Tgt {{ formatKg(line.dayTargetKg) }} Kg · Rem {{ formatKg(line.dayRemKg) }} Kg
          </li>
        </ul>
        <div class="gpe-dialog-actions">
          <button type="button" class="gpe-btn" @click="showConfirmDialog = false">Cancel</button>
          <button type="button" class="gpe-btn primary" @click="confirmSelection">Lock selection</button>
        </div>
      </div>
    </div>

    <!-- Width picker dialog -->
    <div v-if="showWidthPicker" class="gpe-dialog-overlay" @click.self="showWidthPicker = false">
      <div class="gpe-dialog gpe-card">
        <h3>Choose GSM line for new roll</h3>
        <div class="gpe-picker-list">
          <label v-for="line in widthPickerLines" :key="line.id" class="gpe-picker-row">
            <input v-model="widthPickerChoice" type="radio" :value="line.id" />
            {{ line.orderCode }} · {{ line.gsm }} GSM · {{ line.widthLabel }}
          </label>
        </div>
        <div class="gpe-dialog-actions">
          <button type="button" class="gpe-btn" @click="showWidthPicker = false">Cancel</button>
          <button type="button" class="gpe-btn primary" :disabled="!widthPickerChoice" @click="proceedAddRow">Add row</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { openProductionPlanPrintPreview } from "./pp_print_utils.js";
import {
  gsmOpenManualJob,
  gsmOpenRmBatches,
  gsmOpenTrailOrder,
  gsmToggleBundlePackaging,
  openSprForm,
} from "./spr_gsm_tools.js";
import {
  sprCalcNetFromGross,
  sprCalcProducedGsm,
  sprComputePlannedQtyKg,
  sprFlt,
  sprFormatKg,
  sprGsmBandClass,
  sprNormalizeGrossWeightInput,
  sprRecalcRollRow,
} from "./spr_roll_entry_utils.js";

const STORAGE_KEY = "gsm_production_entry_draft_v2";
const BOARD_SLUG = "production-table";
const FABRIC_UNITS = ["Unit 1", "Unit 2", "Unit 3", "Unit 4"];

const viewScope = ref("daily");
const filterDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref(frappe.datetime.get_today().slice(0, 7));
const filterUnit = ref("");
const searchText = ref("");
const loadingOrders = ref(false);
const rawOrders = ref([]);
const merges = ref([]);
const quotaByLineId = ref({});

const pageTab = ref("entry");
const runDate = ref(frappe.datetime.get_today());
const shift = ref("Day Shift");
const headerUnit = ref("");
const operator = ref("");
const supervisor = ref("");

const rollLines = ref([]);
const selectedLineIds = ref(new Set());
const selectionLocked = ref(false);
const showCompletedOrders = ref(false);
const showConfirmDialog = ref(false);
const showWidthPicker = ref(false);
const widthPickerLines = ref([]);
const widthPickerChoice = ref("");
let pendingAddRowResolve = null;

const seriesPrefix = ref("");
const maxRollSuffix = ref(0);
const creationSeq = ref(0);

const summaryTab = ref("summary");
const saveStatus = ref("");
const toolsMenuOpen = ref(false);

const shiftFilterDate = ref(frappe.datetime.get_today());
const shiftFilterShift = ref("Day Shift");
const shiftFilterUnit = ref("");
const shiftEntries = ref([]);
const shiftLoading = ref(false);
const selectedShiftEntry = ref(null);
const coreWidthOptions = ref([{ value: 1600, label: "1600 mm" }]);

let autosaveTimer = null;

const vClickOutside = {
  mounted(el, binding) {
    el._gpeClickOutside = (e) => {
      if (!el.contains(e.target)) {
        binding.value();
      }
    };
    document.addEventListener("click", el._gpeClickOutside);
  },
  unmounted(el) {
    document.removeEventListener("click", el._gpeClickOutside);
  },
};

function formatKg(v) {
  return sprFormatKg(v);
}

function isDraftSpr(item) {
  return !!item?.spr_name && (item.spr_docstatus === 0 || item.spr_docstatus === "0");
}

function itemTargetGapKg(item) {
  const t = sprFlt(item?.qty);
  const a = sprFlt(item?.actual_production_weight_kgs ?? item?.total_achieved_weight_kgs);
  return t - a;
}

function itemRemainingKg(item) {
  if (!item) {
    return 0;
  }
  const pendingKg = sprFlt(item.pp_pending_qty ?? item.pending_qty ?? item.item_pending_qty);
  const gap = itemTargetGapKg(item);
  if (gap > 0.5) {
    return Math.max(pendingKg, gap);
  }
  return pendingKg;
}

function isFabricUnit(unit) {
  const u = (unit || "").trim();
  if (!u || u.toUpperCase().includes("UNASSIGNED")) {
    return false;
  }
  return FABRIC_UNITS.includes(u);
}

function buildRollQuotaDisplay(lineId) {
  const q = quotaByLineId.value[lineId];
  if (!q || q.max_rolls <= 0) {
    return null;
  }
  const jobMax = cint(q.max_rolls);
  const current = cint(q.current_rolls);
  const shiftMax = Math.max(
    0,
    cint(q.shift_max_rolls) || Math.max(0, jobMax - cint(q.other_shifts_rolls))
  );
  const dayTotal = cint(q.day_rolls_total);
  const priorShifts = Array.isArray(q.prior_shifts) ? q.prior_shifts : [];
  const priorParts = priorShifts.map((ps) => `${ps.shift}: ${ps.rolls} done`);
  let tooltip = `${current} produced this shift · ${shiftMax} allowed this shift · ${dayTotal}/${jobMax} rolls today`;
  if (priorParts.length) {
    tooltip += ` · Earlier: ${priorParts.join(", ")}`;
  }
  return {
    current,
    shiftMax,
    jobMax,
    dayTotal,
    priorShifts,
    tooltip,
    isFull: q.can_add_roll === false || q.can_add_roll === 0,
  };
}

function cint(v) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : 0;
}

function quotaTooltipForLine(lineId) {
  const rq = buildRollQuotaDisplay(lineId);
  return rq?.tooltip || "";
}

function lineEligibility(item, lineId) {
  if (!item?.pp_id || Number(item.pp_docstatus) !== 1) {
    return { selectable: false, chip: "", chipClass: "", tooltip: "PP not submitted" };
  }
  if (isDraftSpr(item)) {
    return {
      selectable: true,
      chip: "Draft SPR",
      chipClass: "gpe-chip-draft",
      tooltip: `Draft SPR ${item.spr_name} — continue entry`,
    };
  }
  const quota = quotaByLineId.value[lineId];
  if (quota?.max_rolls > 0 && !quota.can_add_roll) {
    return {
      selectable: false,
      chip: "Quota full",
      chipClass: "gpe-chip-quota",
      tooltip: `${quotaTooltipForLine(lineId)} — use Manual Job`,
    };
  }
  if (item.wo_terminal) {
    return {
      selectable: false,
      chip: "WO Closed",
      chipClass: "gpe-chip-closed",
      tooltip:
        "All Work Orders on this PP are closed (Completed / Stopped / Cancelled). Frozen until a new WO or Draft SPR exists.",
    };
  }
  const rem = itemRemainingKg(item);
  if (rem <= 0.5) {
    return {
      selectable: false,
      chip: "Completed",
      chipClass: "gpe-chip-done",
      tooltip: "PP line target met (remaining ≤ 0.5 Kg)",
    };
  }
  if (Number(item.spr_docstatus) === 1 && !item.wo_terminal) {
    return {
      selectable: true,
      chip: "SPR Submitted",
      chipClass: "gpe-chip-submitted",
      tooltip: "Submitted SPR — more production allowed while WO is open",
    };
  }
  return { selectable: true, chip: "", chipClass: "", tooltip: "Select for today's planned production" };
}

function quotaLabelForLine(lineId) {
  const rq = buildRollQuotaDisplay(lineId);
  if (!rq) {
    return "";
  }
  return `Rolls ${rq.current}/${rq.shiftMax}`;
}

const ppSubmittedRows = computed(() =>
  (rawOrders.value || []).filter(
    (r) => r.pp_id && Number(r.pp_docstatus) === 1 && isFabricUnit(r.unit)
  )
);

const mergedItemIds = computed(() => {
  const s = new Set();
  (merges.value || []).forEach((m) => {
    (m.merged_items || []).forEach((id) => s.add(id));
  });
  return s;
});

const mergeBadgeByItemId = computed(() => {
  const m = {};
  (merges.value || []).forEach((merge) => {
    const label = merge.merge_label || "Merged";
    (merge.merged_items || []).forEach((id) => {
      m[id] = label;
    });
  });
  return m;
});

function quotaContextArgs() {
  return {
    run_date: runDate.value || quotaPlannedDate(),
    shift: shift.value,
    unit: filterUnit.value || headerUnit.value || undefined,
  };
}

function quotaPlannedDate() {
  if (viewScope.value === "daily" && filterDate.value) {
    return filterDate.value;
  }
  const args = buildFetchArgs();
  return args.date || args.start_date || filterDate.value;
}

function buildLineFromItem(item) {
  const id = item.itemName || item.name;
  const w = sprFlt(item.width_inch || item.width);
  const elig = lineEligibility(item, id);
  const achieved = sprFlt(item.actual_production_weight_kgs ?? item.total_achieved_weight_kgs);
  const dayTarget = sprFlt(item.qty);
  return {
    id,
    source: item,
    gsm: item.gsm,
    quality: item.quality || "",
    color: item.color || item.fabric_colour || "",
    width_inch: w,
    widthLabel: w ? `${w}"` : "—",
    dayTargetKg: dayTarget,
    dayRemKg: Math.max(0, dayTarget - achieved),
    remainingKg: itemRemainingKg(item),
    mergeBadge: mergeBadgeByItemId.value[id] || "",
    orderCode: item.partyCode || item.party_code || "",
    partyName: item.customer_name || item.customer || "",
    ppId: item.pp_id,
    selectable: elig.selectable,
    chip: elig.chip,
    chipClass: elig.chipClass,
    tooltip: elig.tooltip,
    rollQuota: buildRollQuotaDisplay(id),
    quotaLabel: quotaLabelForLine(id),
    quotaTooltip: quotaTooltipForLine(id),
  };
}

const unitOptions = computed(() => {
  const s = new Set();
  ppSubmittedRows.value.forEach((r) => {
    if (r.unit && isFabricUnit(r.unit)) {
      s.add(r.unit);
    }
  });
  return FABRIC_UNITS.filter((u) => s.has(u));
});

const fabricUnitOptions = computed(() => unitOptions.value);

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
    map.get(key).lines.push(buildLineFromItem(item));
  });
  return [...map.values()].sort((a, b) => a.orderCode.localeCompare(b.orderCode));
});

const activeOrderGroups = computed(() =>
  orderGroups.value
    .map((g) => ({ ...g, lines: g.lines.filter((l) => l.selectable) }))
    .filter((g) => g.lines.length)
);

const completedOrderGroups = computed(() =>
  orderGroups.value
    .map((g) => ({ ...g, lines: g.lines.filter((l) => !l.selectable) }))
    .filter((g) => g.lines.length)
);

const filteredActiveGroups = computed(() => filterGroups(activeOrderGroups.value));
const filteredCompletedGroups = computed(() => filterGroups(completedOrderGroups.value));
const completedLineCount = computed(() =>
  completedOrderGroups.value.reduce((n, g) => n + g.lines.length, 0)
);

function filterGroups(groups) {
  const q = (searchText.value || "").trim().toLowerCase();
  if (!q) {
    return groups;
  }
  return groups
    .map((g) => ({
      ...g,
      lines: g.lines.filter(
        (l) =>
          g.orderCode.toLowerCase().includes(q) ||
          (l.quality || "").toLowerCase().includes(q) ||
          (l.color || "").toLowerCase().includes(q) ||
          String(l.gsm).toLowerCase().includes(q)
      ),
    }))
    .filter((g) => g.lines.length);
}

const lineById = computed(() => {
  const m = new Map();
  orderGroups.value.forEach((g) => {
    g.lines.forEach((l) => m.set(l.id, { ...l, ppId: g.ppId }));
  });
  return m;
});

const selectedSummary = computed(() => {
  if (!selectedLineIds.value.size) {
    return null;
  }
  let dayPlanned = 0;
  let count = 0;
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (line?.selectable !== false) {
      dayPlanned += sprFlt(line.dayTargetKg);
      count += 1;
    }
  });
  return { count, dayPlanned };
});

const confirmLines = computed(() =>
  [...selectedLineIds.value].map((id) => lineById.value.get(id)).filter(Boolean)
);

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

const toolsContext = computed(() => {
  if (!selectionLocked.value || !selectedLineIds.value.size) {
    return null;
  }
  const ppIds = new Set();
  const orderCodes = new Set();
  const planningNames = [];
  for (const id of selectedLineIds.value) {
    const line = lineById.value.get(id);
    if (!line) {
      continue;
    }
    ppIds.add(line.ppId);
    planningNames.push(id);
    orderCodes.add(line.orderCode);
  }
  if (ppIds.size !== 1 || orderCodes.size !== 1) {
    return null;
  }
  return {
    ppId: [...ppIds][0],
    planningNames,
    orderCode: [...orderCodes][0],
  };
});

const toolsEnabled = computed(() => !!toolsContext.value);
const toolsHint = computed(() => {
  if (!selectionLocked.value) {
    return "Confirm & lock lines from one order first";
  }
  if (!toolsContext.value) {
    return "Lock lines from a single order / PP only";
  }
  return "SPR tools — opens existing SPR from Production Table (does not create SPR)";
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

const boardDayTotalKg = computed(() => {
  let rows = ppSubmittedRows.value;
  if (filterUnit.value) {
    rows = rows.filter((r) => r.unit === filterUnit.value);
  }
  if (viewScope.value === "daily" && filterDate.value) {
    rows = rows.filter((r) => String(r.plannedDate || "").slice(0, 10) === filterDate.value);
  }
  return rows.reduce((s, r) => s + sprFlt(r.qty), 0);
});

const metrics = computed(() => {
  let totalGross = 0;
  let totalNet = 0;
  rollLines.value.forEach((r) => {
    totalGross += sprNormalizeGrossWeightInput(r.gross_weight);
    totalNet += sprFlt(r.net_weight);
  });
  let dayPlanned = 0;
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (line) {
      dayPlanned += sprFlt(line.dayTargetKg);
    }
  });
  rollLines.value.forEach((r) => {
    dayPlanned -= sprFlt(r.net_weight);
  });
  return { totalGross, totalNet, dayRemaining: Math.max(0, dayPlanned) };
});

const linkedOrderSummary = computed(() => {
  const byOrder = new Map();
  const addReq = (orderCode, partyName, required) => {
    if (!byOrder.has(orderCode)) {
      byOrder.set(orderCode, { orderCode, partyName, required: 0, produced: 0, achieved: 0 });
    }
    byOrder.get(orderCode).required += required;
    if (partyName) {
      byOrder.get(orderCode).partyName = partyName;
    }
  };
  selectedLineIds.value.forEach((id) => {
    const line = lineById.value.get(id);
    if (!line) {
      return;
    }
    const src = line.source;
    addReq(line.orderCode, line.partyName, sprFlt(src.qty));
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
    m.get(g).required += sprFlt(src.qty);
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
      requiredKg: sprFlt(line.source.qty),
      sessionKg,
      achievedKg: sprFlt(line.source.actual_production_weight_kgs),
    });
  });
  return out;
});

const canAddRow = computed(
  () =>
    selectionLocked.value &&
    selectedLineIds.value.size > 0 &&
    headerUnit.value &&
    runDate.value &&
    shift.value
);

function lineRowClass(line) {
  return {
    selected: selectedLineIds.value.has(line.id),
    "gpe-line-disabled": !line.selectable,
  };
}

function pruneInvalidSelection() {
  const valid = new Set();
  ppSubmittedRows.value.forEach((item) => {
    valid.add(item.itemName || item.name);
  });
  let changed = false;
  const next = new Set();
  selectedLineIds.value.forEach((id) => {
    if (valid.has(id)) {
      next.add(id);
    } else {
      changed = true;
    }
  });
  if (!changed) {
    return;
  }
  selectedLineIds.value = next;
  if (!next.size) {
    selectionLocked.value = false;
  }
  scheduleAutosave();
}

function toggleLine(id, ev) {
  if (selectionLocked.value) {
    return;
  }
  const line = lineById.value.get(id);
  if (!line?.selectable && ev.target.checked) {
    ev.target.checked = false;
    return;
  }
  const next = new Set(selectedLineIds.value);
  if (ev.target.checked) {
    next.add(id);
  } else {
    next.delete(id);
  }
  selectedLineIds.value = next;
  scheduleAutosave();
}

function onLineLabelClick(line) {
  if (selectionLocked.value || !line.selectable) {
    return;
  }
  const next = new Set(selectedLineIds.value);
  if (next.has(line.id)) {
    next.delete(line.id);
  } else {
    next.add(line.id);
  }
  selectedLineIds.value = next;
  scheduleAutosave();
}

function openConfirmSelection() {
  if (!selectedLineIds.value.size) {
    return;
  }
  showConfirmDialog.value = true;
}

function confirmSelection() {
  selectionLocked.value = true;
  showConfirmDialog.value = false;
  scheduleAutosave();
}

function unlockSelection() {
  if (rollLines.value.length) {
    frappe.confirm("Unlock selection? Existing roll rows stay in the grid.", () => {
      selectionLocked.value = false;
      scheduleAutosave();
    });
    return;
  }
  selectionLocked.value = false;
  scheduleAutosave();
}

function clearSelection() {
  if (selectionLocked.value) {
    frappe.msgprint("Unlock selection first.");
    return;
  }
  selectedLineIds.value = new Set();
  scheduleAutosave();
}

function openShiftTab() {
  pageTab.value = "shift";
  shiftFilterDate.value = runDate.value;
  shiftFilterShift.value = shift.value;
  shiftFilterUnit.value = filterUnit.value || headerUnit.value || shiftFilterUnit.value;
  loadShiftEntries();
}

function closeToolsMenu() {
  toolsMenuOpen.value = false;
}

async function runTool(kind) {
  closeToolsMenu();
  const ctx = toolsContext.value;
  if (!ctx) {
    return;
  }
  const { ppId, planningNames } = ctx;
  const onSuccess = () => fetchOrders();
  if (kind === "manual") {
    await gsmOpenManualJob(ppId, planningNames, headerUnit.value, runDate.value, shift.value, onSuccess);
  } else if (kind === "trail") {
    await gsmOpenTrailOrder(ppId);
  } else if (kind === "bundle") {
    await gsmToggleBundlePackaging(ppId);
  } else if (kind === "rmbatches") {
    await gsmOpenRmBatches(ppId);
  }
}

function viewPP(ppId) {
  if (ppId) {
    openProductionPlanPrintPreview(ppId);
  }
}

function openSpr(name) {
  openSprForm(name);
}

function openWorkOrder(wo) {
  if (wo) {
    frappe.set_route("Form", "Work Order", wo);
  }
}

function rowBandClass(row) {
  const hasWeight = sprNormalizeGrossWeightInput(row.gross_weight) > 0;
  return sprGsmBandClass(row.gsm, row.produced_gsm, hasWeight);
}

function onRowEdit(row) {
  if (row.row_locked) {
    return;
  }
  const updated = sprRecalcRollRow(row);
  Object.assign(row, updated);
  scheduleAutosave();
}

function saveRow(row) {
  row.row_locked = 1;
  row.row_ready_for_print = 1;
  scheduleAutosave();
  frappe.show_alert({ message: __("Row saved locally"), indicator: "green" });
}

function editRow(row) {
  row.row_locked = 0;
  row.row_ready_for_print = 0;
  scheduleAutosave();
}

function printLabel(row) {
  if (!row.row_locked) {
    frappe.msgprint(__("Save Row first to enable the label."));
    return;
  }
  frappe.show_alert({
    message: __("Production label print connects in Phase 2."),
    indicator: "blue",
  });
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

function mergeFetchDate() {
  if (viewScope.value === "daily") {
    return filterDate.value;
  }
  const args = buildFetchArgs();
  return args.date || args.start_date || filterDate.value;
}

async function fetchMerges() {
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.get_merges_for_date",
      args: {
        date: mergeFetchDate(),
        unit: filterUnit.value || null,
        plan_name: "Default",
      },
    });
    merges.value = Array.isArray(res.message) ? res.message : [];
  } catch (e) {
    console.warn("merge fetch failed", e);
    merges.value = [];
  }
}

async function loadQuotaForLines() {
  const cache = {};
  const seen = new Set();
  const rows = ppSubmittedRows.value;
  const quotaArgs = quotaContextArgs();
  const tasks = rows.map(async (item) => {
    const lineId = item.itemName || item.name;
    const key = `${item.pp_id}::${lineId}::${item.gsm}::${item.width_inch}::${quotaArgs.run_date}::${quotaArgs.shift}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    try {
      const res = await frappe.call({
        method: "production_entry.production_planning.unified_production_entry_api.get_pt_line_roll_quota_status",
        args: {
          pp_id: item.pp_id,
          production_plan_item: lineId,
          gsm: item.gsm,
          width_inch: sprFlt(item.width_inch || item.width),
          item_code: item.itemCode || item.item_code,
          run_date: quotaArgs.run_date,
          shift: quotaArgs.shift,
          unit: quotaArgs.unit,
        },
      });
      cache[lineId] = res.message || {};
    } catch (e) {
      console.warn("quota fetch", lineId, e);
    }
  });
  await Promise.all(tasks);
  quotaByLineId.value = cache;
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
    if (!filterUnit.value && unitOptions.value.length) {
      filterUnit.value = unitOptions.value[0];
      headerUnit.value = filterUnit.value;
    }
    await Promise.all([fetchMerges(), loadQuotaForLines()]);
    pruneInvalidSelection();
  } catch (e) {
    console.error(e);
    frappe.msgprint("Failed to load orders");
  } finally {
    loadingOrders.value = false;
  }
}

function onUnitChange() {
  headerUnit.value = filterUnit.value;
  fetchMerges().then(() => loadQuotaForLines());
  scheduleAutosave();
}

async function loadCurrentShift() {
  try {
    const r = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_current_shift",
    });
    if (r.message) {
      shift.value = r.message;
      shiftFilterShift.value = r.message;
    }
  } catch (e) {
    console.warn("shift default", e);
  }
}

async function fetchQuotaForLine(line) {
  try {
    const src = line.source;
    const quotaArgs = quotaContextArgs();
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_pt_line_roll_quota_status",
      args: {
        pp_id: line.ppId || src.pp_id,
        production_plan_item: line.id,
        gsm: line.gsm,
        width_inch: line.width_inch,
        item_code: src.itemCode || src.item_code,
        run_date: quotaArgs.run_date,
        shift: quotaArgs.shift,
        unit: quotaArgs.unit,
      },
    });
    return res.message || {};
  } catch (e) {
    return {};
  }
}

async function resolveOrderLength(line) {
  const src = line.source;
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_order_length_for_pt_line",
      args: {
        pp_id: line.ppId || src.pp_id,
        gsm: line.gsm,
        width_inch: line.width_inch,
        item_code: src.itemCode || src.item_code,
        production_plan_item: line.id,
      },
    });
    return sprFlt(res.message?.meter_roll_mtrs);
  } catch (e) {
    return sprFlt(src.meter || src.meter_roll);
  }
}

async function resolveWorkOrder(line) {
  const src = line.source;
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.resolve_work_order_for_roll_line",
      args: {
        pp_id: line.ppId || src.pp_id,
        gsm: line.gsm,
        width_inch: line.width_inch,
        item_code: src.itemCode || src.item_code,
        production_plan_item: line.id,
      },
    });
    return res.message?.work_order || "";
  } catch (e) {
    return "";
  }
}

async function fetchRollRowExtras(line, lengthM) {
  const src = line.source;
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_roll_row_extras",
      args: {
        gsm: line.gsm,
        width_inch: line.width_inch,
        length_m: lengthM || sprFlt(src.meter || src.meter_roll),
        item_code: src.itemCode || src.item_code,
      },
    });
    return res.message || {};
  } catch (e) {
    return {
      planned_qty: sprComputePlannedQtyKg(line.gsm, line.width_inch, lengthM),
      custom_polybag_kgs: 0,
    };
  }
}

async function loadCoreWidthOptions() {
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_core_width_options",
    });
    const rows = res.message || [];
    if (rows.length) {
      coreWidthOptions.value = rows.map((r) => ({
        value: sprFlt(r.width_mm) || 1600,
        label: r.label || `${r.width_mm} mm`,
      }));
    }
  } catch (e) {
    console.warn("core width options", e);
  }
}

function pickLineForRow() {
  const lines = [...selectedLineIds.value].map((id) => lineById.value.get(id)).filter(Boolean);
  if (lines.length <= 1) {
    return Promise.resolve(lines[0] || null);
  }
  widthPickerLines.value = lines;
  widthPickerChoice.value = lines[0]?.id || "";
  showWidthPicker.value = true;
  return new Promise((resolve) => {
    pendingAddRowResolve = resolve;
  });
}

async function proceedAddRow() {
  const line = lineById.value.get(widthPickerChoice.value);
  showWidthPicker.value = false;
  if (pendingAddRowResolve) {
    pendingAddRowResolve(line || null);
    pendingAddRowResolve = null;
  }
}

async function addRollRow() {
  if (!selectionLocked.value) {
    frappe.msgprint("Confirm and lock your GSM selection first.");
    return;
  }
  if (!headerUnit.value) {
    frappe.msgprint("Select a unit filter first.");
    return;
  }
  const line = await pickLineForRow();
  if (!line) {
    return;
  }
  const quota = await fetchQuotaForLine(line);
  if (quota.max_rolls > 0 && !quota.can_add_roll) {
    frappe.confirm(
      __("Roll limit reached for today ({0}/{1}) — use Manual Job. Open Manual Job now?", [
        quota.day_rolls_total || quota.current_rolls,
        quota.max_rolls,
      ]),
      async () => {
        const ctx = toolsContext.value;
        if (ctx) {
          await gsmOpenManualJob(
            ctx.ppId,
            ctx.planningNames,
            headerUnit.value,
            runDate.value,
            shift.value,
            () => fetchOrders()
          );
        }
      }
    );
    return;
  }
  const src = line.source;
  const [batchInfo, ordLen, wo, extras] = await Promise.all([
    previewNextBatch(),
    resolveOrderLength(line),
    resolveWorkOrder(line),
    fetchRollRowExtras(line, 0),
  ]);
  const defaultCore = coreWidthOptions.value[0]?.value || 1600;
  creationSeq.value += 1;
  const newRow = sprRecalcRollRow({
    _id: `row-${Date.now()}-${creationSeq.value}`,
    creation_seq: creationSeq.value,
    planning_table_row: line.id,
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
    meter_roll: ordLen,
    produced_length_mtrs: "",
    produced_gsm: 0,
    net_weight: 0,
    gross_weight: "",
    planned_qty: extras.planned_qty || sprComputePlannedQtyKg(src.gsm, line.width_inch, ordLen),
    uom: src.uom || src.stock_uom || "Kg",
    custom_core_width_mm: defaultCore,
    custom_polybag_kgs: extras.custom_polybag_kgs || 0,
    custom_diameter_inches: "",
    custom_cbm_cubic_meters: "",
    work_order: wo,
    row_locked: 0,
    row_ready_for_print: 0,
  });
  rollLines.value.unshift(newRow);
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

function removeTopRow() {
  if (!rollLines.value.length) {
    return;
  }
  rollLines.value.shift();
  scheduleAutosave();
}

async function loadShiftEntries() {
  shiftLoading.value = true;
  selectedShiftEntry.value = null;
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_shift_submitted_entries",
      args: {
        run_date: shiftFilterDate.value,
        shift: shiftFilterShift.value,
        unit: shiftFilterUnit.value || undefined,
      },
    });
    shiftEntries.value = res.message || [];
    if (shiftEntries.value.length) {
      selectedShiftEntry.value = shiftEntries.value[0];
    }
  } catch (e) {
    console.error(e);
    frappe.msgprint("Failed to load shift entries");
  } finally {
    shiftLoading.value = false;
  }
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
      selectionLocked: selectionLocked.value,
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
    selectionLocked.value = !!d.selectionLocked;
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

watch([runDate, shift], () => {
  if (ppSubmittedRows.value.length) {
    loadQuotaForLines();
  }
});

watch([runDate, shift, operator, supervisor], () => scheduleAutosave());

onMounted(async () => {
  restoreDraft();
  await loadCurrentShift();
  await loadCoreWidthOptions();
  shiftFilterDate.value = runDate.value;
  shiftFilterShift.value = shift.value;
  shiftFilterUnit.value = filterUnit.value || headerUnit.value;
  await fetchOrders();
  if (!filterUnit.value && unitOptions.value.length) {
    filterUnit.value = unitOptions.value[0];
    headerUnit.value = filterUnit.value;
  }
});

onUnmounted(() => {
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
  }
});
</script>

<style scoped>
.gpe-root {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 15px;
  color: #0f172a;
  padding: 16px;
  background: linear-gradient(160deg, #f1f5f9 0%, #e2e8f0 100%);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}
.gpe-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
}
.gpe-card-inner {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px;
  background: #f8fafc;
}
.gpe-info-strip {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1e40af;
  padding: 8px 12px;
  border-radius: 12px;
  margin-bottom: 12px;
  font-size: 12px;
}
.gpe-page-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}
.gpe-page-tabs button {
  padding: 8px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  font-weight: 500;
}
.gpe-page-tabs button.active {
  background: #4f46e5;
  color: #fff;
  border-color: #4f46e5;
}
.gpe-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 12px;
  padding: 12px;
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
  border-radius: 8px;
}
.gpe-layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 12px;
  align-items: start;
}
@media (max-width: 1100px) {
  .gpe-layout {
    grid-template-columns: 1fr;
  }
}
.gpe-sidebar {
  padding: 12px;
  max-height: calc(100vh - 220px);
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
.gpe-sidebar-section {
  margin-bottom: 10px;
}
.gpe-section-title {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.gpe-collapse-btn {
  border: none;
  background: none;
  color: #4f46e5;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  margin-bottom: 8px;
}
.gpe-order-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 12px;
  margin-bottom: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.gpe-order-code {
  font-size: 17px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
}
.gpe-order-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f1f5f9;
}
.gpe-line-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: 12px;
  cursor: pointer;
  border: 1px solid #e2e8f0;
  margin-bottom: 8px;
  align-items: flex-start;
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}
.gpe-line-card:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
}
.gpe-line-card.selected {
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  border-color: #818cf8;
  box-shadow: 0 0 0 1px #c7d2fe;
}
.gpe-line-check {
  margin-top: 4px;
  flex-shrink: 0;
}
.gpe-line-body {
  flex: 1;
  min-width: 0;
}
.gpe-line-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.gpe-quality {
  color: #1e3a8a;
}
.gpe-color {
  color: #6b21a8;
}
.gpe-line-spec {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  margin-top: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #475569;
}
.gpe-gsm {
  font-size: 18px;
  font-weight: 800;
  color: #312e81;
  letter-spacing: -0.02em;
}
.gpe-day-target {
  color: #0f766e;
  font-weight: 700;
  font-size: 14px;
}
.gpe-day-rem {
  color: #c2410c;
  font-weight: 700;
  font-size: 14px;
}
.gpe-line-foot {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
}
.gpe-roll-meter {
  border-radius: 10px;
  padding: 10px 12px;
  background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%);
  border: 1px solid #fdba74;
}
.gpe-roll-meter-full {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-color: #fca5a5;
}
.gpe-roll-meter-done {
  opacity: 0.85;
}
.gpe-roll-meter-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.gpe-roll-meter-title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #9a3412;
}
.gpe-roll-meter-frac {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 22px;
  font-weight: 800;
  color: #7c2d12;
  line-height: 1;
}
.gpe-roll-meter-frac em {
  font-style: normal;
  font-size: 26px;
  color: #c2410c;
}
.gpe-roll-meter-frac span {
  font-weight: 600;
  color: #9a3412;
  font-size: 18px;
}
.gpe-roll-meter-frac strong {
  font-size: 22px;
  color: #431407;
}
.gpe-roll-meter-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(154, 52, 18, 0.25);
  font-size: 12px;
  font-weight: 600;
}
.gpe-roll-prior {
  background: #fff;
  color: #1d4ed8;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid #bfdbfe;
}
.gpe-roll-day {
  color: #64748b;
  font-weight: 700;
}
.gpe-selection-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  padding: 10px 12px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 10px;
}
.gpe-selection-text {
  font-size: 13px;
}
.gpe-lock-badge.inline {
  margin-left: 8px;
  display: inline-block;
  margin-top: 0;
}
.gpe-gsm-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}
.gpe-legend-title {
  font-weight: 600;
  color: #475569;
}
.gpe-legend-chip {
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  font-weight: 600;
}
.gpe-shift-filter-title {
  font-weight: 600;
  color: #334155;
  margin-right: 8px;
}
.gpe-inp-wide {
  width: 140px;
  max-width: 160px;
}
.gpe-order-group {
  margin-top: 8px;
}
.gpe-party {
  display: none;
}
.gpe-line {
  display: flex;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  align-items: flex-start;
}
.gpe-line.selected {
  background: #eef2ff;
  font-weight: 600;
}
.gpe-line-disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.gpe-completed .gpe-order-head {
  opacity: 0.7;
}
.gpe-merge-label {
  font-weight: 600;
  color: #7c3aed;
}
.gpe-quota {
  color: #b45309;
  font-size: 11px;
}
.gpe-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  align-self: flex-start;
}
.gpe-chip-draft {
  background: #fef3c7;
  color: #92400e;
}
.gpe-chip-done {
  background: #f1f5f9;
  color: #64748b;
}
.gpe-chip-closed {
  background: #fee2e2;
  color: #991b1b;
}
.gpe-chip-quota {
  background: #ffedd5;
  color: #c2410c;
}
.gpe-chip-submitted {
  background: #dcfce7;
  color: #166534;
}
.gpe-chip-merge {
  background: #ede9fe;
  color: #6d28d9;
}
.gpe-selected-box {
  margin-top: 12px;
  padding: 10px;
  background: #f1f5f9;
  border-radius: 10px;
  font-size: 12px;
}
.gpe-selection-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
  flex-wrap: wrap;
}
.gpe-lock-badge {
  margin-top: 6px;
  font-size: 11px;
  color: #4f46e5;
  font-weight: 600;
}
.gpe-main {
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
.gpe-header-fields input,
.gpe-header-fields select {
  padding: 6px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
}
.gpe-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gpe-tag {
  background: #e0e7ff;
  color: #3730a3;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
}
.gpe-metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  margin: 12px 0;
}
@media (max-width: 1100px) {
  .gpe-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
}
.gpe-metric {
  padding: 12px;
  border-radius: 12px;
  text-align: center;
  font-size: 11px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
.gpe-metric strong {
  font-size: 20px;
  display: block;
  margin-top: 4px;
}
.gpe-metric.slate { background: #e2e8f0; color: #1e293b; }
.gpe-metric.blue { background: #93c5fd; color: #1e3a8a; }
.gpe-metric.green { background: #86efac; color: #14532d; }
.gpe-metric.orange { background: #fdba74; color: #9a3412; }
.gpe-metric.grey { background: #cbd5e1; color: #334155; }
.gpe-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.gpe-toolbar-left {
  display: flex;
  gap: 8px;
}
.gpe-toolbar-right {
  margin-left: auto;
  display: flex;
  gap: 8px;
  align-items: center;
}
.gpe-btn {
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}
.gpe-btn.sm {
  padding: 3px 8px;
  font-size: 11px;
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
  font-size: 11px;
  color: #64748b;
}
.gpe-tools-wrap {
  position: relative;
}
.gpe-tools-menu {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  z-index: 20;
  min-width: 200px;
  overflow: hidden;
}
.gpe-tools-menu button {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  border: none;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}
.gpe-tools-menu button:hover {
  background: #f8fafc;
}
.gpe-grid-wrap {
  overflow: auto;
  max-height: 420px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}
.gpe-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.gpe-grid th,
.gpe-grid td {
  border-bottom: 1px solid #f1f5f9;
  padding: 6px 8px;
  white-space: nowrap;
}
.gpe-grid th {
  background: #f8fafc;
  position: sticky;
  top: 0;
  z-index: 1;
}
.gpe-grid tbody tr:nth-child(even) {
  background: #fafbfc;
}
.gpe-row-locked {
  background: #f0fdf4 !important;
}
.gpe-inp {
  width: 72px;
  padding: 3px 5px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
.gpe-inp:disabled {
  background: #f1f5f9;
  color: #64748b;
}
.gpe-actions {
  display: flex;
  gap: 4px;
}
.gpe-wo-link {
  color: #4f46e5;
  text-decoration: none;
  font-size: 11px;
}
.gpe-gsm-band-0 { background: #6ee7b7 !important; color: #064e3b; }
.gpe-gsm-band-1 { background: #fde047 !important; color: #713f12; }
.gpe-gsm-band-2 { background: #fdba74 !important; color: #9a3412; }
.gpe-gsm-band-3 { background: #fca5a5 !important; color: #7f1d1d; }
.gpe-gsm-incomplete { background: #e2e8f0 !important; color: #475569; }
.gpe-summary-tab {
  margin-top: 0;
}
.gpe-tabs button {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  cursor: pointer;
  border-radius: 8px 8px 0 0;
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
  padding: 16px;
}
.gpe-shift-layout {
  margin-top: 0;
}
.gpe-shift-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  padding: 12px;
  margin-bottom: 12px;
}
.gpe-shift-filters label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: #64748b;
}
.gpe-shift-split {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 12px;
  min-height: 400px;
}
@media (max-width: 1000px) {
  .gpe-shift-split {
    grid-template-columns: 1fr;
  }
}
.gpe-shift-sidebar {
  padding: 8px;
  max-height: 520px;
  overflow: auto;
}
.gpe-shift-card {
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  margin-bottom: 8px;
  cursor: pointer;
  background: #fff;
}
.gpe-shift-card.active {
  border-color: #4f46e5;
  background: #eef2ff;
}
.gpe-shift-card-title {
  font-weight: 700;
  font-size: 12px;
}
.gpe-shift-card-meta {
  font-size: 11px;
  color: #64748b;
  margin-top: 4px;
}
.gpe-shift-card-stats {
  font-size: 11px;
  margin-top: 4px;
}
.gpe-shift-detail {
  padding: 12px;
}
.gpe-shift-detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gpe-shift-meta {
  font-size: 12px;
  color: #64748b;
}
.gpe-wo-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}
.gpe-empty-state {
  padding: 32px;
  text-align: center;
}
.gpe-empty-state h3 {
  margin: 0 0 8px;
}
.gpe-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.gpe-dialog {
  width: min(480px, 92vw);
  padding: 16px;
}
.gpe-dialog h3 {
  margin: 0 0 8px;
}
.gpe-confirm-list {
  margin: 12px 0;
  padding-left: 18px;
  font-size: 12px;
}
.gpe-picker-list {
  margin: 12px 0;
}
.gpe-picker-row {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  font-size: 12px;
}
.gpe-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
