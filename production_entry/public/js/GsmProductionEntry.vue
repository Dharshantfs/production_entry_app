<template>
  <div class="gpe-root">
    <div class="gpe-info-strip">
      Create SPRs for selected orders, enter rolls, Save Row saves to server. Submit Entry pushes to SPR and submits.
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
    <div v-show="pageTab === 'entry'" class="gpe-layout gpe-layout-entry">
      <div v-if="showShiftOpeningPanel" class="gpe-shift-open-overlay gpe-card">
        <div class="gpe-shift-open-card">
          <h3>Open {{ shift }}</h3>
          <p class="gpe-hint">Start this shift before selecting jobs or entering rolls. Day and Night are separate sessions.</p>
          <div v-if="shiftStatusChips.length" class="gpe-shift-status-strip">
            <span v-for="chip in shiftStatusChips" :key="chip.shift" :class="['gpe-shift-chip', chip.tone]">
              {{ chip.shift }}: {{ chip.label }}
            </span>
          </div>
          <div class="gpe-shift-open-fields">
            <label class="gpe-emp-link">
              Operator
              <div class="gpe-emp-link-row">
                <input :value="operator" type="text" readonly placeholder="Select employee" />
                <button type="button" class="gpe-btn" @click="pickEmployeeLink('operator', 'Operator')">Pick</button>
              </div>
            </label>
            <label class="gpe-emp-link">
              Supervisor
              <div class="gpe-emp-link-row">
                <input :value="supervisor" type="text" readonly placeholder="Select employee" />
                <button type="button" class="gpe-btn" @click="pickEmployeeLink('supervisor', 'Supervisor')">Pick</button>
              </div>
            </label>
            <div class="gpe-shift-batch-preview">
              <span class="gpe-shift-batch-label">Shift batch</span>
              <strong class="gpe-batch-badge">{{ shiftPreviewBatch || "…" }}</strong>
            </div>
          </div>
          <button
            type="button"
            class="gpe-btn primary gpe-shift-start-btn"
            :disabled="shiftOpeningBusy || !operator || !supervisor || !shiftPreviewBatch"
            @click="startShift"
          >
            {{ shiftOpeningBusy ? "Starting…" : "Start Shift" }}
          </button>
        </div>
      </div>
      <aside class="gpe-sidebar gpe-card">
        <h3>Orders &amp; Jobs</h3>
        <p class="gpe-hint">PP shaft jobs. Confirm selection, then add roll rows.</p>
        <div v-if="selectionLocked && selectedEntries.length" class="gpe-session-panel">
          <div class="gpe-session-panel-head">Locked session · {{ selectedEntries.length }} job(s)</div>
          <div v-for="e in selectedEntries" :key="e.key" class="gpe-session-entry">
            <strong>{{ e.orderCode }}</strong>
            <span>Job {{ e.jobId || e.job_id }} · {{ e.gsm }} GSM</span>
            <span v-if="e.combination_label">{{ e.combination_label }}</span>
          </div>
          <p class="gpe-session-hint">Change run date above to add more jobs — session stays locked.</p>
        </div>
        <div v-if="loadingOrders" class="gpe-muted">Loading…</div>
        <div v-else-if="!jobOrderGroups.length" class="gpe-muted">
          No PP-submitted jobs for this date/unit.
        </div>

        <div v-for="grp in filteredActiveJobGroups" :key="grp.key" class="gpe-order-card">
          <div class="gpe-order-head">
            <span class="gpe-order-code">{{ grp.orderCode }}</span>
            <button
              v-if="grp.ppId"
              type="button"
              class="gpe-link-btn"
              @click="viewPP(grp.ppId)"
            >View PP</button>
          </div>
          <div v-if="grp.dayTargetKg > 0" class="gpe-order-target">
            <span class="gpe-day-target">Order Tgt {{ formatKg(grp.dayTargetKg) }} Kg</span>
            <span class="gpe-day-rem">Rem {{ formatKg(grp.dayRemKg) }} Kg</span>
          </div>
          <label
            v-for="job in grp.jobs"
            :key="job.job_key"
            class="gpe-job-card"
            :class="jobRowClass(job)"
            :title="job.tooltip"
          >
            <input
              type="checkbox"
              class="gpe-line-check"
              :checked="isJobSelected(job)"
              :disabled="!shiftOpened || !job.selectable || (selectionLocked && isJobSelected(job))"
              @change="toggleJob(job, $event)"
            />
            <div class="gpe-job-body" @click.prevent="onJobLabelClick(job)">
              <div class="gpe-job-head">
                <span class="gpe-job-title">Job {{ job.job_id }}</span>
                <span class="gpe-job-head-dot">·</span>
                <span class="gpe-job-gsm">{{ job.gsm }} GSM</span>
              </div>
              <div class="gpe-job-combination">{{ job.combination_label || "—" }}</div>
              <div v-if="job.job_target_kg > 0" class="gpe-job-target">
                <span class="gpe-day-target">Job Tgt {{ formatKg(job.job_target_kg) }} Kg</span>
                <span class="gpe-day-rem">Rem {{ formatKg(job.job_remaining_kg) }} Kg</span>
              </div>
              <div class="gpe-dual-meter" :class="{ 'gpe-dual-meter-full': job.quota_full }">
                <div class="gpe-meter-col">
                  <span class="gpe-meter-label">Shafts</span>
                  <span class="gpe-meter-frac">
                    <em>{{ job.job_shafts_produced }}</em><span>/</span><strong>{{ job.max_shafts }}</strong>
                  </span>
                </div>
                <div class="gpe-meter-col">
                  <span class="gpe-meter-label">Rolls</span>
                  <span class="gpe-meter-frac">
                    <em>{{ job.job_rolls_produced }}</em><span>/</span><strong>{{ job.max_rolls }}</strong>
                  </span>
                </div>
              </div>
              <div class="gpe-meter-context">{{ shift }} · {{ formatPlannedDate(runDate) }}</div>
              <div v-if="cint(job.today_rolls) > 0" class="gpe-shift-breakdown">
                <span class="gpe-shift-today">Today: {{ job.today_rolls }} {{ plural(job.today_rolls, "roll", "rolls") }}</span>
                <span
                  v-for="part in shiftBreakdownParts(job)"
                  :key="part.shift"
                  :class="['gpe-shift-part', part.shift === shift ? 'gpe-shift-current' : 'gpe-shift-other']"
                > · {{ part.shift }}: <strong>{{ part.count }}</strong></span>
              </div>
              <div v-if="job.rem_shafts > 0 || job.rem_rolls > 0" class="gpe-job-remaining">
                Remaining: {{ jobRemainingText(job) }}
              </div>
              <div v-if="job.chip" class="gpe-job-foot">
                <span :class="['gpe-chip', job.chipClass]">{{ job.chip }}</span>
              </div>
            </div>
          </label>
        </div>

        <div v-if="filteredCompletedJobGroups.length" class="gpe-sidebar-section">
          <button type="button" class="gpe-collapse-btn" @click="showCompletedOrders = !showCompletedOrders">
            {{ showCompletedOrders ? "▼" : "▶" }} Completed jobs ({{ completedJobCount }})
          </button>
          <div v-show="showCompletedOrders">
            <div v-for="grp in filteredCompletedJobGroups" :key="'c-' + grp.key" class="gpe-order-card gpe-completed">
              <div class="gpe-order-head">
                <span class="gpe-order-code">{{ grp.orderCode }}</span>
                <button
                  v-if="grp.ppId"
                  type="button"
                  class="gpe-link-btn"
                  @click="viewPP(grp.ppId)"
                >View PP</button>
              </div>
              <div v-if="grp.dayTargetKg > 0" class="gpe-order-target">
                <span class="gpe-day-target">Order Tgt {{ formatKg(grp.dayTargetKg) }} Kg</span>
                <span class="gpe-day-rem">Rem {{ formatKg(grp.dayRemKg) }} Kg</span>
              </div>
              <label
                v-for="job in grp.jobs"
                :key="job.job_key"
                class="gpe-job-card gpe-line-disabled"
                :title="job.tooltip"
              >
                <input type="checkbox" class="gpe-line-check" disabled />
                <div class="gpe-job-body">
                  <div class="gpe-job-head">
                    <span class="gpe-job-title">Job {{ job.job_id }}</span>
                    <span class="gpe-job-head-dot">·</span>
                    <span class="gpe-job-gsm">{{ job.gsm }} GSM</span>
                  </div>
                  <div class="gpe-job-combination">{{ job.combination_label || "—" }}</div>
                  <div v-if="job.job_target_kg > 0" class="gpe-job-target">
                    <span class="gpe-day-target">Job Tgt {{ formatKg(job.job_target_kg) }} Kg</span>
                    <span class="gpe-day-rem">Rem {{ formatKg(job.job_remaining_kg) }} Kg</span>
                  </div>
                  <div class="gpe-dual-meter gpe-dual-meter-done">
                    <div class="gpe-meter-col">
                      <span class="gpe-meter-label">Shafts</span>
                      <span class="gpe-meter-frac">
                        <em>{{ job.job_shafts_produced }}</em><span>/</span><strong>{{ job.max_shafts }}</strong>
                      </span>
                    </div>
                    <div class="gpe-meter-col">
                      <span class="gpe-meter-label">Rolls</span>
                      <span class="gpe-meter-frac">
                        <em>{{ job.job_rolls_produced }}</em><span>/</span><strong>{{ job.max_rolls }}</strong>
                      </span>
                    </div>
                  </div>
                  <div class="gpe-job-foot">
                    <span :class="['gpe-chip', job.chipClass]">{{ job.chip }}</span>
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>
      </aside>

      <main class="gpe-main gpe-card">
        <div class="gpe-header gpe-session-panel-main gpe-card-inner">
          <div class="gpe-session-head-row">
            <h3 class="gpe-session-title">Production Session</h3>
            <div v-if="shiftOpened && shiftBatchPrefix" class="gpe-batch-badge-wrap">
              <span class="gpe-batch-badge">{{ shift }} · {{ shiftBatchPrefix }}</span>
            </div>
            <button
              v-if="shiftOpened"
              type="button"
              class="gpe-btn gpe-btn-warn gpe-close-shift-btn"
              :disabled="shiftClosingBusy"
              @click="closeShift"
            >
              {{ shiftClosingBusy ? "Closing…" : "Close Shift" }}
            </button>
          </div>
          <div v-if="shiftStatusChips.length" class="gpe-shift-status-strip gpe-shift-status-strip-compact">
            <span v-for="chip in shiftStatusChips" :key="'h-' + chip.shift" :class="['gpe-shift-chip', chip.tone]">
              {{ chip.shift }}: {{ chip.label }}
            </span>
          </div>
          <div class="gpe-tags" v-if="!selectionLocked && headerTags.length">
            <span v-for="t in headerTags" :key="t" class="gpe-tag">{{ t }}</span>
          </div>
          <div class="gpe-header-session-row">
            <div class="gpe-header-fields gpe-header-fields-lg">
              <label>Run Date <input type="date" v-model="runDate" :disabled="shiftOpened" /></label>
              <label>
                Shift
                <select v-model="shift" :disabled="shiftOpened" @change="onShiftHeaderChange">
                  <option value="Day Shift">Day Shift</option>
                  <option value="Night Shift">Night Shift</option>
                </select>
              </label>
              <label>Unit <input v-model="headerUnit" type="text" readonly /></label>
              <label>Operator <input :value="operator" type="text" readonly /></label>
              <label>Supervisor <input :value="supervisor" type="text" readonly /></label>
            </div>
            <div v-if="sessionSprList.length" class="gpe-spr-table-wrap gpe-spr-inline">
              <div class="gpe-spr-table-title">Order · Label Type · SPR</div>
              <table class="gpe-spr-table">
                <thead>
                  <tr><th>Order Code</th><th>Label Type</th><th>SPR</th></tr>
                </thead>
                <tbody>
                  <tr v-for="s in sessionSprList" :key="s.pp_id">
                    <td>{{ s.order_code }}</td>
                    <td>{{ s.label_type || "Default" }}</td>
                    <td>
                      <button type="button" class="gpe-link-btn" @click="openSpr(s.spr_name)">{{ s.spr_name }}</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-if="selectedSummary || selectedEntries.length" class="gpe-selection-strip gpe-selection-strip-lg">
            <div class="gpe-selection-text">
              <strong>{{ selectedSummary?.count || 0 }}</strong> line(s) ·
              Session plan <strong>{{ formatKg(selectedSummary?.dayPlanned || 0) }}</strong> Kg ·
              Session rem <strong>{{ formatKg(metrics.dayRemaining) }}</strong> Kg
              <span v-if="selectionLocked" class="gpe-lock-badge inline">Locked</span>
            </div>
            <div class="gpe-selection-actions">
              <button
                v-if="!selectionLocked"
                type="button"
                class="gpe-btn primary"
                :disabled="!shiftOpened || !selectedEntries.length"
                @click="openConfirmSelection"
              >Confirm selection</button>
              <button
                v-else
                type="button"
                class="gpe-btn"
                @click="unlockSelection"
              >Unlock</button>
              <button type="button" class="gpe-link-btn" @click="clearSelection">Clear</button>
            </div>
          </div>
        </div>

        <div class="gpe-entry-workspace">
        <div class="gpe-metrics gpe-metrics-compact">
          <div class="gpe-metric slate">Board plan (Kg)<br /><strong>{{ formatKg(boardDayTotalKg) }}</strong></div>
          <div class="gpe-metric blue">Total Entry (Kg)<br /><strong>{{ formatKg(metrics.totalGross) }}</strong></div>
          <div class="gpe-metric green">Net Production (Kg)<br /><strong>{{ formatKg(metrics.totalNet) }}</strong></div>
          <div class="gpe-metric orange">Day remaining (Kg)<br /><strong>{{ formatKg(metrics.dayRemaining) }}</strong></div>
          <div class="gpe-metric grey">Rolls<br /><strong>{{ sessionRollCount }}</strong></div>
        </div>

        <div class="gpe-toolbar">
          <div class="gpe-toolbar-left">
            <button
              v-if="allSelectedJobsMaxed && selectedEntries.length"
              type="button"
              class="gpe-btn warn"
              @click="openManualJobForAllMaxed"
            >All jobs at max — Manual Job</button>
            <button v-else type="button" class="gpe-btn primary" :disabled="!canAddRow || addRollInProgress" @click="addRollRow">
              {{ addRollInProgress ? "Adding…" : "Add Roll Row" }}
            </button>
            <button type="button" class="gpe-btn" :disabled="!rollLines.length" @click="removeTopRow">Remove Top Row</button>
            <button
              type="button"
              class="gpe-btn gpe-btn-warn"
              :disabled="!rollLines.length && !sessionSprList.length"
              title="Clear grid for another entry same date/shift — then Create SPRs again"
              @click="clearGridEntries"
            >Clear Entries</button>
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
                <button type="button" @click="runTool('bundlese')">SPR — Bundle SE on Submit</button>
                <button type="button" @click="runTool('rmbatches')">SPR — Select RM batches</button>
              </div>
            </div>
            <button type="button" class="gpe-btn" :disabled="!selectedEntries.length" @click="openShaftDetails">Shaft Details</button>
            <button v-if="!allSprsCreated" type="button" class="gpe-btn" :disabled="!canCreateSprs" @click="createSprs">Create SPRs</button>
            <button
              v-else-if="forceNewSprSession"
              type="button"
              class="gpe-btn primary"
              :disabled="!canCreateSprs"
              @click="createSprs"
            >Create new SPRs</button>
            <span v-else class="gpe-spr-ready-badge" title="All selected orders have draft SPRs">SPRs ready</span>
            <button type="button" class="gpe-btn primary" :disabled="!canSubmitEntry" @click="submitEntry">Submit Entry</button>
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

        <div class="gpe-grid-wrap gpe-grid-wrap-entry">
          <table class="gpe-grid gpe-grid-entry">
            <thead>
              <tr>
                <th class="gpe-sticky-col gpe-sticky-0">#</th>
                <th class="gpe-sticky-col gpe-sticky-1">Order Code</th>
                <th class="gpe-num">Job</th>
                <th>Quality</th>
                <th>Color</th>
                <th class="gpe-num">Sticker GSM</th>
                <th class="gpe-num">Width</th>
                <th class="gpe-num">Ordered Length (MTR)</th>
                <th class="gpe-num">Produced Length (MTR)</th>
                <th>Prod GSM</th>
                <th>Batch</th>
                <th>Net (Kgs)</th>
                <th>Gross (Kgs)</th>
                <th>Planned Qty (Kgs)</th>
                <th>UOM</th>
                <th>WO</th>
                <th>Core</th>
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
                <td class="gpe-sticky-col gpe-sticky-0">{{ rollLines.length - idx }}</td>
                <td class="gpe-sticky-col gpe-sticky-1">{{ row.party_code }}</td>
                <td class="gpe-num">{{ row.job_id || row.job || "—" }}</td>
                <td>{{ row.quality }}</td>
                <td>{{ row.color }}</td>
                <td class="gpe-num">{{ row.gsm }}</td>
                <td class="gpe-num">{{ widthDisplay(row) }}</td>
                <td class="gpe-num">{{ row.meter_roll }}</td>
                <td class="gpe-len-cell gpe-num">
                  <input
                    v-model.number="row.produced_length_mtrs"
                    type="number"
                    step="0.01"
                    class="gpe-inp gpe-inp-len"
                    :disabled="row.row_locked || row.is_bundle_row"
                    @input="onRowEdit(row)"
                  />
                  <span class="gpe-unit-suffix">MTR</span>
                </td>
                <td class="gpe-num">{{ row.produced_gsm }}</td>
                <td class="gpe-num">{{ row.batch_no }}</td>
                <td class="gpe-num">{{ formatKg(row.net_weight) }}</td>
                <td class="gpe-num">
                  <input
                    v-model="row.gross_weight"
                    type="text"
                    class="gpe-inp"
                    :disabled="row.row_locked || row.is_bundle_row"
                    @input="onRowEdit(row)"
                  />
                </td>
                <td class="gpe-num">{{ formatKg(row.planned_qty) }}</td>
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
                    v-model="row.custom_core_width_mm"
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
                    class="gpe-btn sm gpe-btn-label"
                    :disabled="!isRowLabelReady(row)"
                    :title="isRowLabelReady(row) ? 'Print production label' : 'Save Row first'"
                    @click="printLabel(row)"
                  >Label</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
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
        Save Row writes to draft SPR on server. Submit Entry imports and submits SPR(s) for selected orders.
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

    <!-- Shift ending reminder -->
    <div v-if="showShiftReminder" class="gpe-dialog-overlay">
      <div class="gpe-dialog gpe-card">
        <h3>Shift ending reminder</h3>
        <p>It is time to close the shift. You will be redirected to Shift Wise Production Entry.</p>
        <div class="gpe-dialog-actions">
          <button type="button" class="gpe-btn" @click="dismissShiftReminder">Later</button>
          <button type="button" class="gpe-btn primary" @click="closeShiftFromReminder">Go to Shift Wise Entry</button>
        </div>
      </div>
    </div>

    <!-- Confirm selection dialog -->
    <div v-if="showConfirmDialog" class="gpe-dialog-overlay" @click.self="showConfirmDialog = false">
      <div class="gpe-dialog gpe-card">
        <h3>Confirm job selection</h3>
        <p>Lock these jobs for roll entry? You can unlock later.</p>
        <table class="gpe-confirm-grid">
          <thead>
            <tr>
              <th>Order</th><th>Job</th><th>GSM</th><th>Combination</th><th>Progress</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="line in confirmLines" :key="line.key">
              <td>{{ line.orderCode }}</td>
              <td>{{ line.jobId || line.job_id }}</td>
              <td>{{ line.gsm }}</td>
              <td>{{ line.combination_label || line.widthLabel }}</td>
              <td>{{ confirmLineProgress(line) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="gpe-dialog-actions">
          <button type="button" class="gpe-btn" @click="showConfirmDialog = false">Cancel</button>
          <button type="button" class="gpe-btn primary" @click="confirmSelection">Lock selection</button>
        </div>
      </div>
    </div>

    <!-- Add Roll wizard: Job → Width -->
    <div v-if="showAddRollWizard" class="gpe-dialog-overlay" @click.self="cancelAddRollWizard">
      <div class="gpe-dialog gpe-card">
        <h3>{{ addRollWizardStep === 1 ? "Choose job for new roll" : "Choose width" }}</h3>
        <div v-if="addRollWizardStep === 1 && !addRollWizardSkipJobStep" class="gpe-picker-list">
          <label
            v-for="entry in wizardJobChoices"
            :key="entry.key"
            class="gpe-picker-row"
            :class="{ 'gpe-picker-maxed': entry.maxed }"
          >
            <input v-model="addRollJobChoice" type="radio" :value="entry.key" />
            <span>
              {{ entry.orderCode }} · Job {{ entry.jobId || entry.job_id }} · {{ entry.gsm }} GSM
              <em v-if="entry.board" class="gpe-picker-sub">
                {{ entry.board.job_shafts_produced }}/{{ entry.board.max_shafts }} shafts ·
                {{ entry.board.job_rolls_produced }}/{{ entry.board.max_rolls }} rolls
                <strong v-if="entry.maxed" class="gpe-picker-maxed-tag"> · MAX — Manual Job only</strong>
              </em>
            </span>
          </label>
        </div>
        <div v-else class="gpe-picker-list">
          <div v-if="wizardSelectedJobMaxed" class="gpe-picker-maxed-note">
            This job reached its planned max rolls
            ({{ wizardSelectedJob?.job_rolls_produced }}/{{ wizardSelectedJob?.max_rolls }}).
            Extra production must go through Manual Job.
          </div>
          <label v-for="seg in wizardWidthSegments" :key="seg.width_inch" class="gpe-picker-row" :class="{ 'gpe-picker-disabled': !seg.can_add }">
            <input
              v-model="addRollWidthChoice"
              type="radio"
              :value="seg.width_inch"
              :disabled="!seg.can_add"
            />
            <span>
              {{ seg.width_inch }}" · {{ seg.current }}/{{ seg.max }} rolls
              <em v-if="!seg.can_add" class="gpe-picker-sub">(full)</em>
            </span>
          </label>
        </div>
        <div class="gpe-dialog-actions">
          <button
            type="button"
            class="gpe-btn"
            @click="addRollWizardStep === 1 || addRollWizardSkipJobStep ? cancelAddRollWizard() : (addRollWizardStep = 1)"
          >
            {{ addRollWizardStep === 1 || addRollWizardSkipJobStep ? "Cancel" : "Back" }}
          </button>
          <button
            v-if="wizardSelectedJobMaxed"
            type="button"
            class="gpe-btn warn"
            @click="openManualJobFromWizard"
          >Manual Job</button>
          <button
            v-else
            type="button"
            class="gpe-btn primary"
            :disabled="addRollWizardStep === 1 ? !addRollJobChoice : addRollWidthChoice == null"
            @click="proceedAddRollWizard"
          >{{ addRollWizardStep === 1 ? "Next" : "Add row" }}</button>
        </div>
      </div>
    </div>
    <!-- Tolerance approval dialog (multi-order) -->
    <div v-if="showToleranceDialog" class="gpe-dialog-overlay" @click.self="showToleranceDialog = false">
      <div class="gpe-dialog gpe-dialog-wide gpe-card">
        <h3>Tolerance approval required</h3>
        <p class="gpe-muted">{{ toleranceOrders.length }} order(s) need approval before submit.</p>
        <div v-for="order in toleranceOrders" :key="order.spr_name" class="gpe-tol-card">
          <div class="gpe-tol-card-head">
            <strong>{{ order.order_code || "—" }}</strong>
            <span>{{ order.spr_name }}</span>
          </div>
          <table class="gpe-grid gpe-tol-table">
            <thead>
              <tr><th>Job</th><th>Roll</th><th>Planned (Kg)</th><th>Net/Gross (Kg)</th><th>Variance</th></tr>
            </thead>
            <tbody>
              <tr v-for="(v, vi) in order.violations" :key="vi">
                <td>{{ v.job }}</td>
                <td>{{ v.roll_no }}</td>
                <td>{{ formatKg(v.planned) }}</td>
                <td>{{ formatKg(v.actual) }}</td>
                <td>{{ v.dev_pct }}%</td>
              </tr>
            </tbody>
          </table>
          <label class="gpe-tol-reason">
            Reason for override
            <textarea v-model="toleranceForm[order.spr_name].reason" rows="2" />
          </label>
          <label class="gpe-tol-check">
            <input v-model="toleranceForm[order.spr_name].approved" type="checkbox" />
            I approve this deviation
          </label>
        </div>
        <div class="gpe-dialog-actions">
          <button type="button" class="gpe-btn" @click="showToleranceDialog = false">Cancel</button>
          <button type="button" class="gpe-btn primary" :disabled="!toleranceFormComplete" @click="submitWithTolerance">Submit all with approval</button>
        </div>
      </div>
    </div>
    <!-- Shaft details dialog -->
    <div v-if="showShaftDetailsDialog" class="gpe-dialog-overlay" @click.self="showShaftDetailsDialog = false">
      <div class="gpe-dialog gpe-dialog-wide gpe-card">
        <h3>Shaft Details</h3>
        <p v-if="shaftDetailsLoading" class="gpe-muted">Loading…</p>
        <div v-for="block in shaftDetailsBlocks" :key="block.pp_id" class="gpe-shaft-block">
          <div class="gpe-shaft-block-head">
            <strong>{{ block.order_code || block.pp_id }}</strong>
            <span v-if="block.label_type">· {{ block.label_type }}</span>
          </div>
          <table v-if="block.shaft_rows?.length" class="gpe-grid gpe-shaft-grid">
            <thead>
              <tr>
                <th>Job</th><th>No of Shafts</th><th>GSM</th><th>Combination</th><th>Total Width</th><th>Meter/Roll</th><th>Net Weight</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, ri) in block.shaft_rows" :key="ri">
                <td>{{ row.job }}</td>
                <td>{{ row.no_of_shafts }}</td>
                <td>{{ row.gsm }}</td>
                <td>{{ row.combination }}</td>
                <td>{{ row.total_width }}</td>
                <td>{{ row.meter_roll }}</td>
                <td>{{ formatKg(row.net_weight) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="gpe-muted">{{ block.message || "No shaft rows on this PP." }}</p>
        </div>
        <div class="gpe-dialog-actions">
          <button type="button" class="gpe-btn primary" @click="showShaftDetailsDialog = false">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { openProductionPlanPrintPreview } from "./pp_print_utils.js";
import {
  gsmOpenBundlePackaging,
  gsmOpenManualJob,
  gsmOpenRmBatches,
  gsmOpenTrailOrder,
  gsmPrintRollLabel,
  gsmPrintBundleLabel,
  gsmToggleBundleSeOnSubmit,
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

const STORAGE_KEY = "gsm_production_entry_draft_v3";
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
const selectedEntries = ref([]);
const selectionLocked = ref(false);
const showCompletedOrders = ref(false);
const showConfirmDialog = ref(false);
const showAddRollWizard = ref(false);
const addRollWizardStep = ref(1);
const addRollWizardSkipJobStep = ref(false);
const addRollJobChoice = ref("");
const addRollWidthChoice = ref(null);
let pendingAddRowResolve = null;

const jobBoardJobs = ref([]);
const sessionJobApiBaseline = ref({});

const seriesPrefix = ref("");
const maxRollSuffix = ref(0);
const reservedBatchNos = ref(new Set());
const addRollInProgress = ref(false);
const batchContextKey = ref("");

function currentBatchContextKey() {
  return `${runDate.value}|${shift.value}|${headerUnit.value}`;
}

function resetBatchSeriesCache() {
  seriesPrefix.value = "";
  maxRollSuffix.value = 0;
  reservedBatchNos.value = new Set();
}

function allExistingBatchNos() {
  const seen = new Set(reservedBatchNos.value);
  for (const r of rollLines.value) {
    const bn = _cstr(r.batch_no || "");
    if (bn) {
      seen.add(bn);
    }
  }
  return [...seen];
}

function reserveBatchNo(batchNo, rollNo) {
  const bn = _cstr(batchNo || "");
  if (!bn) {
    return;
  }
  reservedBatchNos.value = new Set([...reservedBatchNos.value, bn]);
  const prefix = bn.split("/")[0];
  if (prefix) {
    seriesPrefix.value = prefix;
  }
  const rn = parseInt(rollNo, 10);
  if (!Number.isNaN(rn)) {
    maxRollSuffix.value = Math.max(maxRollSuffix.value, rn);
  } else {
    const suf = parseInt(bn.split("/").pop(), 10);
    if (!Number.isNaN(suf)) {
      maxRollSuffix.value = Math.max(maxRollSuffix.value, suf);
    }
  }
}

const sessionSprs = ref({});
const forceNewSprSession = ref(false);
const showToleranceDialog = ref(false);
const toleranceOrders = ref([]);
const toleranceForm = ref({});
const submitInProgress = ref(false);

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
const coreWidthOptions = ref([]);

const shiftSession = ref(null);
const shiftSessionReady = ref(false);
const shiftBatchPrefix = ref("");
const shiftPreviewBatch = ref("");
const shiftStatusByShift = ref({});
const shiftOpeningBusy = ref(false);
const shiftClosingBusy = ref(false);
const showShiftReminder = ref(false);
let shiftReminderTimer = null;
let shiftReminderInterval = null;
let shiftReminderDismissedAt = 0;

const showShaftDetailsDialog = ref(false);
const shaftDetailsLoading = ref(false);
const shaftDetailsBlocks = ref([]);

let autosaveTimer = null;

function entryKey(plannedDate, lineId) {
  return `${plannedDate}::${lineId}`;
}

function entryKeyJob(ppId, jobId) {
  return `${ppId}::${jobId}`;
}

function orderMetaForPp(ppId) {
  const row =
    filteredPpSubmittedRows.value.find((r) => r.pp_id === ppId) ||
    ppSubmittedRows.value.find((r) => r.pp_id === ppId);
  return {
    orderCode: row?.partyCode || row?.party_code || ppId,
    partyName: row?.customer_name || row?.customer || "",
    quality: row?.quality || "",
    color: row?.color || row?.fabric_colour || "",
    planningLineId: row?.itemName || row?.name || "",
  };
}

function ppChartMetaForPp(ppId) {
  const rows = filteredPpSubmittedRows.value.filter((r) => r.pp_id === ppId);
  const row = rows[0];
  return {
    wo_terminal: !!(row?.wo_terminal === true || row?.wo_terminal === 1),
    spr_docstatus: Number(row?.spr_docstatus ?? 0),
    pp_docstatus: Number(row?.pp_docstatus ?? 1),
  };
}

function orderDayStatsForPp(ppId) {
  const rows = filteredPpSubmittedRows.value.filter((r) => r.pp_id === ppId);
  const dayTargetKg = rows.reduce((s, r) => s + sprFlt(r.qty), 0);
  const achievedKg = rows.reduce(
    (s, r) => s + sprFlt(r.actual_production_weight_kgs ?? r.total_achieved_weight_kgs),
    0
  );
  return {
    dayTargetKg,
    dayRemKg: Math.max(0, dayTargetKg - achievedKg),
  };
}

function ensureJobApiBaseline(job) {
  const key = entryKeyJob(job.pp_id, job.job_id);
  if (sessionJobApiBaseline.value[key] == null) {
    sessionJobApiBaseline.value[key] = cint(job.job_rolls_produced);
  }
}

function allGridRollRowsForJob(ppId, jobId) {
  const jid = String(jobId || "");
  return rollLines.value.filter(
    (row) =>
      !row.is_bundle_row &&
      row.pp_id === ppId &&
      String(row.job_id || row.job || "") === jid
  );
}

function gridBundleRollCountForJob(ppId, jobId, widthInch = null) {
  const jid = String(jobId || "");
  const target = widthInch == null ? null : sprFlt(widthInch);
  return rollLines.value
    .filter((row) => {
      if (!row.is_bundle_row || row.pp_id !== ppId || String(row.job_id || row.job || "") !== jid) {
        return false;
      }
      if (target == null) {
        return true;
      }
      const w = sprFlt(row.segment_width || row.width_inch);
      return Math.abs(w - target) < 0.05;
    })
    .reduce((sum, row) => sum + Math.max(1, cint(row.pack_count || 0)), 0);
}

function effectiveJobRollCount(job) {
  if (job?.api_job_rolls_produced != null) {
    return cint(job.api_job_rolls_produced) + cint(job.local_pending_rolls || 0);
  }
  const savedOnServer = Math.max(
    cint(job.job_rolls_produced),
    gridBundleRollCountForJob(job.pp_id, job.job_id)
  );
  return savedOnServer + localPendingRollCountForJob(job.pp_id, job.job_id);
}

function effectiveWidthRollCount(job, widthInch) {
  const target = sprFlt(widthInch);
  const seg = (job.width_segments || []).find((s) => Math.abs(sprFlt(s.width_inch) - target) < 0.05);
  if (seg?.api_current != null) {
    return cint(seg.api_current) + localPendingWidthCountForJob(job.pp_id, job.job_id, widthInch);
  }
  const savedAtWidth = Math.max(
    cint(seg?.current || 0),
    gridBundleRollCountForJob(job.pp_id, job.job_id, widthInch)
  );
  return savedAtWidth + localPendingWidthCountForJob(job.pp_id, job.job_id, widthInch);
}

function canJobAddOneMoreRoll(job) {
  if (!job || job.wo_terminal) {
    return false;
  }
  const j = job.api_job_rolls_produced != null ? job : withLocalPendingQuota(job);
  if (j.roll_limit_reached) {
    return false;
  }
  const maxRolls = cint(j.max_rolls);
  if (maxRolls <= 0) {
    return true;
  }
  return cint(j.rem_rolls) > 0;
}

function canJobAddWidthRoll(job, widthInch) {
  if (!job || job.wo_terminal) {
    return false;
  }
  const j = job.api_job_rolls_produced != null ? job : withLocalPendingQuota(job);
  if (!canJobAddOneMoreRoll(j)) {
    return false;
  }
  const target = sprFlt(widthInch);
  const seg = (j.width_segments || []).find((s) => Math.abs(sprFlt(s.width_inch) - target) < 0.05);
  const max = cint(seg?.max || j.max_rolls);
  if (max <= 0) {
    return true;
  }
  return effectiveWidthRollCount(j, widthInch) < max;
}

function recordJobApiBaselines(jobs) {
  const next = { ...sessionJobApiBaseline.value };
  for (const job of jobs || []) {
    const key = entryKeyJob(job.pp_id, job.job_id);
    if (next[key] == null) {
      next[key] = cint(job.job_rolls_produced);
    }
  }
  sessionJobApiBaseline.value = next;
}

function localPendingRollRowsForJob(ppId, jobId) {
  const jid = String(jobId || "");
  return rollLines.value.filter(
    (row) =>
      !row.is_bundle_row &&
      row.pp_id === ppId &&
      String(row.job_id || row.job || "") === jid &&
      !row.spr_item_name &&
      !row.row_locked
  );
}

function localPendingRollCountForJob(ppId, jobId) {
  return localPendingRollRowsForJob(ppId, jobId).length;
}

function localPendingWidthCountForJob(ppId, jobId, widthInch) {
  const target = sprFlt(widthInch);
  return localPendingRollRowsForJob(ppId, jobId).filter(
    (row) => Math.abs(sprFlt(row.width_inch) - target) < 0.05
  ).length;
}

function withLocalPendingQuota(job) {
  const pending = localPendingRollCountForJob(job.pp_id, job.job_id);
  const savedOnServer = Math.max(
    cint(job.job_rolls_produced),
    gridBundleRollCountForJob(job.pp_id, job.job_id)
  );
  const jobRolls = savedOnServer + pending;
  const rollsPerShaft = Math.max(1, cint(job.rolls_per_shaft));
  const jobShafts = Math.min(cint(job.max_shafts), Math.floor(jobRolls / rollsPerShaft));
  const remRolls = Math.max(0, cint(job.max_rolls) - jobRolls);
  const remShafts = Math.max(0, cint(job.max_shafts) - jobShafts);
  const currentShaftRolls = jobRolls % rollsPerShaft;
  const currentShaftRemainingRolls =
    remRolls > 0 && currentShaftRolls ? Math.max(0, rollsPerShaft - currentShaftRolls) : 0;
  const widthSegments = (job.width_segments || []).map((seg) => {
    const savedAtWidth = Math.max(
      cint(seg.current),
      gridBundleRollCountForJob(job.pp_id, job.job_id, seg.width_inch)
    );
    const pendingAtWidth = localPendingWidthCountForJob(job.pp_id, job.job_id, seg.width_inch);
    const current = savedAtWidth + pendingAtWidth;
    const max = cint(seg.max);
    return {
      ...seg,
      api_current: savedAtWidth,
      current,
      can_add: current < max && remRolls > 0 && !job.wo_terminal,
    };
  });
  // Roll limit gates Add Roll (drafts + saved count). A job is only "Completed"
  // (quota_full) once its rolls are SUBMITTED to the full quota, or the WO is done.
  const rollLimitReached = remRolls <= 0 || jobShafts >= cint(job.max_shafts);
  const submittedRolls = cint(job.submitted_rolls);
  const submittedComplete = cint(job.max_rolls) > 0 && submittedRolls >= cint(job.max_rolls);
  const quotaFull = !!job.wo_terminal || submittedComplete;
  return {
    ...job,
    api_job_rolls_produced: savedOnServer,
    local_pending_rolls: pending,
    job_rolls_produced: jobRolls,
    job_shafts_produced: jobShafts,
    rem_rolls: remRolls,
    rem_shafts: remShafts,
    current_shaft_rolls: currentShaftRolls,
    current_shaft_remaining_rolls: currentShaftRemainingRolls,
    width_segments: widthSegments,
    roll_limit_reached: rollLimitReached,
    quota_full: quotaFull,
    can_add_roll: !rollLimitReached && jobRolls < cint(job.max_rolls),
  };
}

function enrichJobCard(job) {
  job = withLocalPendingQuota(job);
  const meta = orderMetaForPp(job.pp_id);
  const chartMeta = ppChartMetaForPp(job.pp_id);
  const woTerminal = !!(job.wo_terminal || chartMeta.wo_terminal);
  const quotaFull = job.quota_full || woTerminal;
  const selectable = !quotaFull && !woTerminal;
  let chip = "";
  let chipClass = "";
  let tooltip = "Select for production";
  if (woTerminal) {
    chip = "WO Closed";
    chipClass = "gpe-chip-closed";
    tooltip = "Work Orders closed on this PP";
  } else if (job.quota_full) {
    chip = "Completed";
    chipClass = "gpe-chip-done";
    tooltip = "Job shaft/roll quota met";
  } else if (chartMeta.spr_docstatus === 1) {
    chip = "SPR Submitted";
    chipClass = "gpe-chip-submitted";
    tooltip = "Submitted SPR — more production allowed while WO is open";
  } else if ((job.active_spr_names || []).length || sessionSprs.value[job.pp_id]?.spr_name) {
    chip = "SPR Active";
    chipClass = "gpe-chip-draft";
    tooltip = "Draft SPR exists for this run date and shift";
  }
  return {
    ...job,
    orderCode: meta.orderCode,
    partyName: meta.partyName,
    quality: meta.quality,
    color: meta.color,
    planningLineId: meta.planningLineId,
    selectable,
    chip,
    chipClass,
    tooltip,
  };
}

function snapshotFromJob(job) {
  const meta = orderMetaForPp(job.pp_id);
  return {
    key: entryKeyJob(job.pp_id, job.job_id),
    jobId: job.job_id,
    lineId: meta.planningLineId,
    plannedDate: filterDate.value || runDate.value,
    ppId: job.pp_id,
    orderCode: meta.orderCode,
    partyName: meta.partyName,
    quality: meta.quality,
    color: meta.color,
    gsm: job.gsm,
    combination_label: job.combination_label,
    width_inch: null,
    widthLabel: job.combination_label || "",
    max_shafts: job.max_shafts,
    max_rolls: job.max_rolls,
    dayTargetKg: orderDayStatsForPp(job.pp_id).dayTargetKg,
    sourceSnapshot: {
      pp_id: job.pp_id,
      gsm: job.gsm,
      meter_roll: job.meter_roll,
      net_weight: job.net_weight,
    },
  };
}

function firstPtLineForPp(ppId, gsm) {
  let rows = ppSubmittedRows.value.filter((r) => r.pp_id === ppId);
  if (gsm) {
    const hit = rows.find((r) => String(r.gsm) === String(gsm));
    if (hit) {
      return buildLineFromItem(hit);
    }
  }
  return rows[0] ? buildLineFromItem(rows[0]) : null;
}

function confirmLineProgress(entry) {
  const job = jobBoardJobs.value.find(
    (j) => j.pp_id === entry.ppId && String(j.job_id) === String(entry.jobId || entry.job_id)
  );
  if (!job) {
    return "—";
  }
  return `${job.job_shafts_produced}/${job.max_shafts} shafts · ${job.job_rolls_produced}/${job.max_rolls} rolls`;
}

function plural(n, one, many) {
  return Number(n) === 1 ? one : many;
}

function shiftBreakdownParts(job) {
  const byShift = job?.rolls_by_shift_today || {};
  const known = ["Day Shift", "Night Shift"];
  const parts = known.map((sh) => ({ shift: sh, count: cint(byShift[sh]) }));
  for (const [sh, cnt] of Object.entries(byShift)) {
    if (!known.includes(sh)) {
      parts.push({ shift: sh, count: cint(cnt) });
    }
  }
  return parts;
}

function jobRemainingText(job) {
  const remRolls = cint(job.rem_rolls);
  const remShafts = cint(job.rem_shafts);
  const rollsPerShaft = Math.max(1, cint(job.rolls_per_shaft));
  if (remRolls <= 0) {
    return "0 rolls";
  }
  const pieces = [];
  let remainingShafts = remShafts;
  const currentNeed = cint(job.current_shaft_remaining_rolls);
  if (currentNeed > 0) {
    const shaftNo = cint(job.job_shafts_produced) + 1;
    pieces.push(`Shaft ${shaftNo}: ${currentNeed} ${plural(currentNeed, "roll", "rolls")}`);
    remainingShafts = Math.max(0, remainingShafts - 1);
  }
  if (remainingShafts === 1) {
    const shaftNo = cint(job.max_shafts) - remainingShafts + 1;
    pieces.push(`Shaft ${shaftNo}: ${rollsPerShaft} ${plural(rollsPerShaft, "roll", "rolls")}`);
  } else if (remainingShafts > 1) {
    pieces.push(`${remainingShafts} full ${plural(remainingShafts, "shaft", "shafts")}`);
  }
  if (!pieces.length) {
    pieces.push(`${remShafts} ${plural(remShafts, "shaft", "shafts")} · ${remRolls} ${plural(remRolls, "roll", "rolls")}`);
  }
  return `${pieces.join(" · ")} (${remRolls} ${plural(remRolls, "roll", "rolls")} total)`;
}

function linePlannedDate(item) {
  return String(item?.plannedDate || item?.planned_date || filterDate.value || "").slice(0, 10);
}

function formatPlannedDate(d) {
  if (!d) {
    return "—";
  }
  const parts = String(d).slice(0, 10).split("-");
  if (parts.length === 3) {
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
  }
  return d;
}

function snapshotFromLine(line) {
  const src = line.source || {};
  const plannedDate = line.plannedDate || linePlannedDate(src);
  return {
    key: entryKey(plannedDate, line.id),
    lineId: line.id,
    plannedDate,
    ppId: line.ppId || src.pp_id,
    orderCode: line.orderCode,
    partyName: line.partyName,
    quality: line.quality,
    color: line.color,
    gsm: line.gsm,
    width_inch: line.width_inch,
    widthLabel: line.widthLabel,
    dayTargetKg: line.dayTargetKg,
    sourceSnapshot: {
      pp_id: line.ppId || src.pp_id,
      item_code: src.itemCode || src.item_code,
      itemCode: src.itemCode || src.item_code,
      item_name: src.description || src.item_name,
      description: src.description || src.item_name,
      uom: src.uom || src.stock_uom,
      stock_uom: src.stock_uom,
      qty: src.qty,
      actual_production_weight_kgs: src.actual_production_weight_kgs,
      gsm: line.gsm,
    },
  };
}

function entryToRollLine(entry) {
  if (entry.jobId || entry.job_id) {
    const line = firstPtLineForPp(entry.ppId, entry.gsm);
    if (line) {
      return {
        ...line,
        ppId: entry.ppId,
        jobId: entry.jobId || entry.job_id,
        plannedDate: entry.plannedDate,
        source: line.source,
      };
    }
  }
  const live = lineById.value.get(entry.lineId);
  if (live) {
    const livePd = live.plannedDate || linePlannedDate(live.source || {});
    if (livePd === entry.plannedDate) {
      return { ...live, ppId: entry.ppId || live.ppId, plannedDate: entry.plannedDate, source: live.source };
    }
  }
  const src = entry.sourceSnapshot || {};
  return {
    id: entry.lineId,
    ppId: entry.ppId,
    orderCode: entry.orderCode,
    partyName: entry.partyName,
    quality: entry.quality,
    color: entry.color,
    gsm: entry.gsm,
    width_inch: entry.width_inch,
    widthLabel: entry.widthLabel,
    dayTargetKg: entry.dayTargetKg,
    plannedDate: entry.plannedDate,
    source: src,
    selectable: true,
  };
}

const selectedEntryKeys = computed(() => new Set(selectedEntries.value.map((e) => e.key)));

const entryLinesForSession = computed(() => selectedEntries.value.map((e) => entryToRollLine(e)));

function isEntrySelected(line) {
  const pd = line.plannedDate || linePlannedDate(line.source || {});
  return selectedEntryKeys.value.has(entryKey(pd, line.id));
}

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

function rowMatchesFilterDate(row) {
  const pd = String(row.plannedDate || row.planned_date || "").slice(0, 10);
  if (!pd) {
    return false;
  }
  if (viewScope.value === "daily") {
    return pd === filterDate.value;
  }
  const args = buildFetchArgs();
  if (args.start_date && args.end_date) {
    return pd >= args.start_date && pd <= args.end_date;
  }
  return true;
}

const filteredPpSubmittedRows = computed(() => {
  let rows = ppSubmittedRows.value;
  if (filterUnit.value) {
    rows = rows.filter((r) => r.unit === filterUnit.value);
  }
  rows = rows.filter((r) => rowMatchesFilterDate(r));
  return rows;
});

const filteredPpIdSet = computed(
  () => new Set(filteredPpSubmittedRows.value.map((r) => r.pp_id).filter(Boolean))
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
    plannedDate: linePlannedDate(item),
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

const jobOrderGroups = computed(() => {
  const map = new Map();
  const allowedPpIds = filteredPpIdSet.value;
  for (const job of jobBoardJobs.value) {
    if (!allowedPpIds.has(job.pp_id)) {
      continue;
    }
    const enriched = enrichJobCard(job);
    const key = `${enriched.orderCode}::${job.pp_id}`;
    if (!map.has(key)) {
      const dayStats = orderDayStatsForPp(job.pp_id);
      map.set(key, {
        key,
        orderCode: enriched.orderCode,
        partyName: enriched.partyName,
        ppId: job.pp_id,
        dayTargetKg: dayStats.dayTargetKg,
        dayRemKg: dayStats.dayRemKg,
        jobs: [],
      });
    }
    map.get(key).jobs.push(enriched);
  }
  return [...map.values()].sort((a, b) => a.orderCode.localeCompare(b.orderCode));
});

const activeJobOrderGroups = computed(() =>
  jobOrderGroups.value
    .map((g) => ({ ...g, jobs: g.jobs.filter((j) => j.selectable) }))
    .filter((g) => g.jobs.length)
);

const completedJobOrderGroups = computed(() =>
  jobOrderGroups.value
    .map((g) => ({ ...g, jobs: g.jobs.filter((j) => !j.selectable) }))
    .filter((g) => g.jobs.length)
);

function filterJobGroups(groups) {
  const q = (searchText.value || "").trim().toLowerCase();
  if (!q) {
    return groups;
  }
  return groups
    .map((g) => ({
      ...g,
      jobs: g.jobs.filter(
        (j) =>
          g.orderCode.toLowerCase().includes(q) ||
          String(j.job_id).toLowerCase().includes(q) ||
          (j.combination_label || "").toLowerCase().includes(q) ||
          String(j.gsm).toLowerCase().includes(q)
      ),
    }))
    .filter((g) => g.jobs.length);
}

const filteredActiveJobGroups = computed(() => filterJobGroups(activeJobOrderGroups.value));
const filteredCompletedJobGroups = computed(() => filterJobGroups(completedJobOrderGroups.value));
const completedJobCount = computed(() =>
  completedJobOrderGroups.value.reduce((n, g) => n + g.jobs.length, 0)
);

const wizardJobChoices = computed(() =>
  selectedEntries.value.map((entry) => {
    const jid = entry.jobId || entry.job_id;
    const boardRaw = jobBoardJobs.value.find((j) => j.pp_id === entry.ppId && String(j.job_id) === String(jid));
    const board = boardRaw ? withLocalPendingQuota(boardRaw) : null;
    const maxed = board ? !canJobAddOneMoreRoll(board) : false;
    return { ...entry, board, maxed };
  })
);

const wizardSelectedJob = computed(() => {
  const key = addRollJobChoice.value;
  if (!key) {
    return null;
  }
  const raw = jobBoardJobs.value.find((j) => entryKeyJob(j.pp_id, j.job_id) === key);
  return raw ? withLocalPendingQuota(raw) : null;
});

const wizardSelectedJobMaxed = computed(() => {
  const job = wizardSelectedJob.value;
  return job ? !canJobAddOneMoreRoll(job) : false;
});

const allSelectedJobsMaxed = computed(() => {
  if (!selectedEntries.value.length) {
    return false;
  }
  return selectedEntries.value.every((entry) => {
    const jid = entry.jobId || entry.job_id;
    const raw = jobBoardJobs.value.find((j) => j.pp_id === entry.ppId && String(j.job_id) === String(jid));
    if (!raw) {
      return false;
    }
    return !canJobAddOneMoreRoll(withLocalPendingQuota(raw));
  });
});

const wizardWidthSegments = computed(() => {
  const key = addRollJobChoice.value;
  if (!key) {
    return [];
  }
  const rawJob = jobBoardJobs.value.find((j) => entryKeyJob(j.pp_id, j.job_id) === key);
  const job = rawJob ? withLocalPendingQuota(rawJob) : null;
  return job?.width_segments || [];
});

const orderGroups = computed(() => {
  const map = new Map();
  filteredPpSubmittedRows.value.forEach((item) => {
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
  if (!selectedEntries.value.length) {
    return null;
  }
  let dayPlanned = 0;
  for (const entry of selectedEntries.value) {
    dayPlanned += sprFlt(entry.dayTargetKg);
  }
  return { count: selectedEntries.value.length, dayPlanned };
});

const confirmLines = computed(() => selectedEntries.value);

const headerTags = computed(() => {
  const tags = [];
  selectedEntries.value.forEach((entry) => {
    const jid = entry.jobId || entry.job_id;
    tags.push(`${entry.orderCode} / Job ${jid} · ${entry.gsm} GSM`);
  });
  return tags.slice(0, 12);
});

const toolsPpOptions = computed(() => {
  const map = new Map();
  for (const entry of selectedEntries.value) {
    const ppId = entry.ppId;
    if (!ppId || !sessionSprs.value[ppId]?.spr_name) {
      continue;
    }
    if (!map.has(ppId)) {
      map.set(ppId, {
        ppId,
        orderCode: entry.orderCode,
        spr_name: sessionSprs.value[ppId].spr_name,
        lineIds: [],
      });
    }
    map.get(ppId).lineIds.push(entry.lineId);
  }
  return [...map.values()];
});

const toolsContext = computed(() => {
  const options = toolsPpOptions.value;
  if (!selectionLocked.value || !options.length) {
    return null;
  }
  if (options.length === 1) {
    const o = options[0];
    return { ppId: o.ppId, planningNames: o.lineIds, orderCode: o.orderCode };
  }
  return { multi: true, options };
});

const allSprsCreated = computed(() => {
  const ppIds = new Set(selectedEntries.value.map((e) => e.ppId).filter(Boolean));
  if (!ppIds.size) {
    return false;
  }
  return [...ppIds].every((id) => sessionSprs.value[id]?.spr_name);
});

const toolsEnabled = computed(() => !!toolsPpOptions.value.length && selectionLocked.value);
const toolsHint = computed(() => {
  if (!selectionLocked.value) {
    return "Confirm & lock lines first";
  }
  if (!toolsPpOptions.value.length) {
    return "Create SPRs first, then use Tools";
  }
  if (toolsPpOptions.value.length > 1) {
    return "Tools — pick which order/SPR to open";
  }
  return "SPR tools for this order";
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

const boardDayTotalKg = computed(() =>
  filteredPpSubmittedRows.value.reduce((s, r) => s + sprFlt(r.qty), 0)
);

const metrics = computed(() => {
  let totalGross = 0;
  let totalNet = 0;
  rollLines.value.forEach((r) => {
    totalGross += sprNormalizeGrossWeightInput(r.gross_weight);
    totalNet += sprFlt(r.net_weight);
  });
  let dayPlanned = 0;
  selectedEntries.value.forEach((entry) => {
    dayPlanned += sprFlt(entry.dayTargetKg);
  });
  rollLines.value.forEach((r) => {
    dayPlanned -= sprFlt(r.net_weight);
  });
  return { totalGross, totalNet, dayRemaining: Math.max(0, dayPlanned) };
});

const sessionRollCount = computed(() => {
  if (selectedEntries.value.length) {
    let total = 0;
    const seen = new Set();
    for (const entry of selectedEntries.value) {
      const jid = entry.jobId || entry.job_id;
      const key = entryKeyJob(entry.ppId, jid);
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      const raw = jobBoardJobs.value.find(
        (j) => j.pp_id === entry.ppId && String(j.job_id) === String(jid)
      );
      if (raw) {
        total += withLocalPendingQuota(raw).job_rolls_produced;
      }
    }
    if (total > 0) {
      return total;
    }
  }
  return rollLines.value.reduce(
    (sum, r) => sum + (r.is_bundle_row ? Math.max(1, cint(r.pack_count || 0)) : 1),
    0
  );
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
  selectedEntries.value.forEach((entry) => {
    const src = entry.sourceSnapshot || {};
    addReq(entry.orderCode, entry.partyName, sprFlt(src.qty));
    byOrder.get(entry.orderCode).achieved += sprFlt(src.actual_production_weight_kgs);
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
  selectedEntries.value.forEach((entry) => {
    const g = String(entry.gsm);
    if (!m.has(g)) {
      m.set(g, { gsm: g, required: 0, session: 0, achieved: 0 });
    }
    const src = entry.sourceSnapshot || {};
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

const selectedLinesDetail = computed(() =>
  selectedEntries.value.map((entry) => {
    const sessionKg = rollLines.value
      .filter((r) => r.planning_table_row === entry.lineId)
      .reduce((s, r) => s + sprFlt(r.net_weight), 0);
    const src = entry.sourceSnapshot || {};
    return {
      id: entry.lineId,
      orderCode: entry.orderCode,
      partyName: entry.partyName,
      gsm: entry.gsm,
      width_inch: entry.width_inch,
      plannedDate: entry.plannedDate,
      requiredKg: sprFlt(src.qty),
      sessionKg,
      achievedKg: sprFlt(src.actual_production_weight_kgs),
    };
  })
);

const canAddRow = computed(() => {
  if (
    !shiftOpened.value ||
    !selectionLocked.value ||
    !selectedEntries.value.length ||
    !headerUnit.value ||
    !runDate.value ||
    !shift.value ||
    !sessionSprList.value.length
  ) {
    return false;
  }
  return selectedEntries.value.some((entry) => {
    const jid = entry.jobId || entry.job_id;
    const raw = jobBoardJobs.value.find((j) => j.pp_id === entry.ppId && String(j.job_id) === String(jid));
    if (!raw) {
      return true;
    }
    return canJobAddOneMoreRoll(withLocalPendingQuota(raw));
  });
});

const sessionSprList = computed(() => {
  const ppIds = new Set(selectedEntries.value.map((e) => e.ppId).filter(Boolean));
  if (!ppIds.size) {
    return [];
  }
  return Object.values(sessionSprs.value || {}).filter((s) => ppIds.has(s.pp_id));
});

function pruneSessionSprsToSelection() {
  if (selectionLocked.value) {
    return;
  }
  const ppIds = new Set(selectedEntries.value.map((e) => e.ppId).filter(Boolean));
  const next = {};
  for (const [k, v] of Object.entries(sessionSprs.value || {})) {
    if (ppIds.has(k)) {
      next[k] = v;
    }
  }
  if (Object.keys(next).length !== Object.keys(sessionSprs.value || {}).length) {
    sessionSprs.value = next;
    scheduleAutosave();
  }
}

function pruneSelectedEntriesToFilter() {
  const allowedPpIds = filteredPpIdSet.value;
  if (!selectedEntries.value.length || !allowedPpIds.size) {
    return;
  }
  const next = selectedEntries.value.filter((e) => allowedPpIds.has(e.ppId));
  if (next.length === selectedEntries.value.length) {
    return;
  }
  selectedEntries.value = next;
  if (!next.length) {
    selectionLocked.value = false;
    rollLines.value = [];
    sessionSprs.value = {};
  } else {
    pruneSessionSprsToSelection();
  }
  scheduleAutosave();
}

const shiftOpened = computed(() => {
  const s = shiftSession.value;
  return !!(s && s.status === "Open");
});

const showShiftOpeningPanel = computed(
  () => pageTab.value === "entry" && !!headerUnit.value && shiftSessionReady.value && !shiftOpened.value
);

const shiftStatusChips = computed(() => {
  const map = shiftStatusByShift.value || {};
  return ["Day Shift", "Night Shift"].map((shiftName) => {
    const row = map[shiftName] || {};
    const status = row.status || "Not started";
    let tone = "muted";
    let label = status;
    if (status === "Open") {
      tone = shiftName === shift.value ? "open" : "other-open";
      label = row.batch_series_prefix ? `Open · ${row.batch_series_prefix}` : "Open";
    } else if (status === "Closed") {
      tone = "closed";
      label = row.batch_series_prefix ? `Closed · ${row.batch_series_prefix}` : "Closed";
    }
    return { shift: shiftName, label, tone };
  });
});

const canCreateSprs = computed(
  () =>
    shiftOpened.value &&
    !allSprsCreated.value &&
    selectionLocked.value &&
    selectedEntries.value.length > 0 &&
    headerUnit.value &&
    runDate.value &&
    shift.value
);

const canSubmitEntry = computed(
  () =>
    shiftOpened.value &&
    !submitInProgress.value &&
    selectionLocked.value &&
    sessionSprList.value.length > 0 &&
    rollLines.value.length > 0 &&
    rollLines.value.every((r) => r.row_locked && r.batch_no && sprNormalizeGrossWeightInput(r.gross_weight) > 0)
);

const toleranceFormComplete = computed(() => {
  if (!toleranceOrders.value.length) {
    return false;
  }
  return toleranceOrders.value.every((o) => {
    const f = toleranceForm.value[o.spr_name] || {};
    return (f.reason || "").trim() && f.approved;
  });
});

function jobRowClass(job) {
  return {
    selected: isJobSelected(job),
    "gpe-line-disabled": !job.selectable,
  };
}

function isJobSelected(job) {
  return selectedEntryKeys.value.has(entryKeyJob(job.pp_id, job.job_id));
}

function toggleJob(job, ev) {
  if (!shiftOpened.value && ev.target.checked) {
    ev.target.checked = false;
    frappe.msgprint(__("Start the shift before selecting jobs."));
    return;
  }
  if (!job?.selectable && ev.target.checked) {
    ev.target.checked = false;
    return;
  }
  const snap = snapshotFromJob(job);
  const checked = ev.target.checked;

  if (selectionLocked.value) {
    if (!checked) {
      ev.target.checked = true;
      return;
    }
    if (!selectedEntryKeys.value.has(snap.key)) {
      selectedEntries.value = [...selectedEntries.value, snap];
      scheduleAutosave();
    }
    return;
  }

  const next = selectedEntries.value.filter((e) => e.key !== snap.key);
  if (checked) {
    next.push(snap);
  }
  selectedEntries.value = next;
  pruneSessionSprsToSelection();
  scheduleAutosave();
}

function onJobLabelClick(job) {
  if (!shiftOpened.value) {
    frappe.msgprint(__("Start the shift before selecting jobs."));
    return;
  }
  if (!job.selectable) {
    return;
  }
  if (selectionLocked.value) {
    if (isJobSelected(job)) {
      return;
    }
    const snap = snapshotFromJob(job);
    if (!selectedEntryKeys.value.has(snap.key)) {
      selectedEntries.value = [...selectedEntries.value, snap];
      scheduleAutosave();
    }
    return;
  }
  const snap = snapshotFromJob(job);
  const next = selectedEntries.value.filter((e) => e.key !== snap.key);
  if (!isJobSelected(job)) {
    next.push(snap);
  }
  selectedEntries.value = next;
  pruneSessionSprsToSelection();
  scheduleAutosave();
}

function lineRowClass(line) {
  return {
    selected: isEntrySelected(line),
    "gpe-line-disabled": !line.selectable,
  };
}

function toggleLine(line, ev) {
  if (!line?.selectable && ev.target.checked) {
    ev.target.checked = false;
    return;
  }
  const snap = snapshotFromLine(line);
  const checked = ev.target.checked;

  if (selectionLocked.value) {
    if (!checked) {
      ev.target.checked = true;
      return;
    }
    if (!selectedEntryKeys.value.has(snap.key)) {
      selectedEntries.value = [...selectedEntries.value, snap];
      scheduleAutosave();
    }
    return;
  }

  const next = selectedEntries.value.filter((e) => e.key !== snap.key);
  if (checked) {
    next.push(snap);
  }
  selectedEntries.value = next;
  pruneSessionSprsToSelection();
  scheduleAutosave();
}

function onLineLabelClick(line) {
  if (!line.selectable) {
    return;
  }
  if (selectionLocked.value) {
    if (isEntrySelected(line)) {
      return;
    }
    const snap = snapshotFromLine(line);
    if (!selectedEntryKeys.value.has(snap.key)) {
      selectedEntries.value = [...selectedEntries.value, snap];
      scheduleAutosave();
    }
    return;
  }
  const snap = snapshotFromLine(line);
  const next = selectedEntries.value.filter((e) => e.key !== snap.key);
  if (!isEntrySelected(line)) {
    next.push(snap);
  }
  selectedEntries.value = next;
  pruneSessionSprsToSelection();
  scheduleAutosave();
}

function openConfirmSelection() {
  if (!shiftOpened.value) {
    frappe.msgprint(__("Start the shift before confirming job selection."));
    return;
  }
  if (!selectedEntries.value.length) {
    return;
  }
  showConfirmDialog.value = true;
}

function confirmSelection() {
  recordJobApiBaselines(jobBoardJobs.value);
  selectionLocked.value = true;
  showConfirmDialog.value = false;
  scheduleAutosave();
}

function unlockSelection() {
  if (rollLines.value.length) {
    frappe.confirm("Unlock selection? Existing roll rows stay in the grid.", () => {
      selectionLocked.value = false;
      pruneSessionSprsToSelection();
      scheduleAutosave();
    });
    return;
  }
  selectionLocked.value = false;
  pruneSessionSprsToSelection();
  scheduleAutosave();
}

function clearSelection() {
  if (selectionLocked.value) {
    frappe.msgprint("Unlock selection first.");
    return;
  }
  selectedEntries.value = [];
  pruneSessionSprsToSelection();
  scheduleAutosave();
}

async function openShaftDetails() {
  const ppIds = [...new Set(selectedEntries.value.map((e) => e.ppId).filter(Boolean))];
  if (!ppIds.length) {
    frappe.msgprint(__("Select orders first."));
    return;
  }
  showShaftDetailsDialog.value = true;
  shaftDetailsLoading.value = true;
  shaftDetailsBlocks.value = [];
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_pp_shaft_details",
      args: { pp_ids: JSON.stringify(ppIds) },
    });
    shaftDetailsBlocks.value = (res.message || []).filter((b) => b.status === "ok");
  } catch (e) {
    console.error(e);
    frappe.msgprint(__("Could not load shaft details."));
  } finally {
    shaftDetailsLoading.value = false;
  }
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

function pickToolOrder(options) {
  return new Promise((resolve) => {
    frappe.prompt(
      [
        {
          fieldtype: "Select",
          fieldname: "pp_id",
          label: __("Order / SPR"),
          options: options.map((o) => ({ value: o.ppId, label: `${o.orderCode} · ${o.spr_name}` })),
          reqd: 1,
        },
      ],
      (values) => {
        const chosen = options.find((o) => o.ppId === values.pp_id);
        resolve(chosen || options[0]);
      },
      __("Choose order for SPR Tools"),
      __("Open")
    );
  });
}

async function resolveToolContext() {
  const ctx = toolsContext.value;
  if (!ctx) {
    return null;
  }
  if (!ctx.multi) {
    return ctx;
  }
  const chosen = await pickToolOrder(ctx.options);
  if (!chosen) {
    return null;
  }
  return { ppId: chosen.ppId, planningNames: chosen.lineIds, orderCode: chosen.orderCode };
}

async function runTool(kind) {
  closeToolsMenu();
  const ctx = await resolveToolContext();
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
    await gsmOpenBundlePackaging(ppId, async (m) => {
      await handleBundleApplyResult(m, ppId);
      await fetchOrders();
    });
  } else if (kind === "bundlese") {
    await gsmToggleBundleSeOnSubmit(ppId);
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
  const updated = sprRecalcRollRow({ ...row, core_width_options: coreWidthOptions.value });
  Object.assign(row, updated);
  scheduleAutosave();
}

function buildSessionEntries() {
  return selectedEntries.value.map((entry) => ({
    pp_id: entry.ppId,
    job_id: entry.jobId || entry.job_id,
    jobId: entry.jobId || entry.job_id,
    lineId: entry.lineId,
    orderCode: entry.orderCode,
    quality: entry.quality,
    color: entry.color,
    gsm: entry.gsm,
    width_inch: entry.width_inch,
    plannedDate: entry.plannedDate,
  }));
}

function sprNameForPp(ppId) {
  return sessionSprs.value[ppId]?.spr_name || "";
}

function widthDisplay(row) {
  if (!row) {
    return "";
  }
  if (row.width_label) {
    return row.width_label;
  }
  if (row.is_bundle_row && row.pack_count > 1 && row.segment_width) {
    const w = row.segment_width;
    const lbl = Number.isInteger(w) ? String(w) : String(w);
    return `${lbl}" × ${row.pack_count}`;
  }
  return row.width_inch != null && row.width_inch !== "" ? row.width_inch : "";
}

async function handleBundleApplyResult(m, ppId) {
  if (!m || m.status !== "ok") {
    return;
  }
  let coreItem = "";
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_roll_row_extras",
      args: {
        gsm: m.gsm,
        width_inch: m.segment_width || 0,
        length_m: m.produced_length_mtrs || m.meter_roll || 0,
        pp_id: m.pp_id || ppId,
      },
    });
    const extras = res.message || {};
    coreItem = pickCoreForFabricWidth(
      m.segment_width || 0,
      extras.custom_core_width_mm || extras.core_size || ""
    );
  } catch (e) {
    coreItem = pickCoreForFabricWidth(m.segment_width || 0, "");
  }
  creationSeq.value += 1;
  const bundleRow = sprRecalcRollRow({
    _id: `bundle-${Date.now()}-${creationSeq.value}`,
    creation_seq: creationSeq.value,
    is_bundle_row: true,
    pp_id: m.pp_id || ppId,
    party_code: m.order_code || "",
    job_id: m.job_id || "",
    quality: m.quality || "",
    color: m.color || "",
    gsm: m.gsm || "",
    width_inch: m.segment_width || 0,
    width_label: m.width_label || "",
    pack_count: m.pack_count || 0,
    segment_width: m.segment_width || 0,
    batch_no: m.bundle_batch_no || "",
    roll_no: "",
    roll_numbers: m.roll_numbers || "",
    combination: m.combination || "",
    meter_roll: m.meter_roll || 0,
    produced_length_mtrs: m.produced_length_mtrs || 0,
    produced_gsm: 0,
    net_weight: m.sticker_bundle_weight_kg || 0,
    gross_weight: m.whole_gross_kg || 0,
    planned_qty: m.planned_qty || 0,
    uom: m.uom || "Kg",
    work_order: m.work_order || "",
    child_roll_batches: m.child_roll_batches || [],
    child_spr_item_names: m.child_spr_item_names || [],
    spr_item_name: "",
    row_locked: 1,
    row_ready_for_print: 1,
    custom_core_width_mm: coreItem,
    core_width_options: coreWidthOptions.value,
  });
  rollLines.value.unshift(bundleRow);
  if (m.child_roll_batches?.length) {
    syncBatchCounterFromGrid();
  }
  saveStatus.value = __("Bundle applied — {0} roll(s)", [m.updated_rolls || m.pack_count || 0]);
  scheduleAutosave();
  await loadJobBoard();
  frappe.show_alert({
    message: __("Bundle row added ({0})", [m.width_label || m.bundle_batch_no]),
    indicator: "green",
  });
}

async function fetchShaftJobsForPp(ppId) {
  if (!ppId) {
    return [];
  }
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_pp_shaft_details",
      args: { pp_ids: JSON.stringify([ppId]) },
    });
    const rows = res.message || [];
    const hit = rows.find((r) => r.pp_id === ppId);
    return hit?.shaft_rows || [];
  } catch (e) {
    return [];
  }
}

function pickJobIdForLine(line) {
  const ppId = line?.ppId;
  if (!ppId) {
    return Promise.resolve("");
  }
  return fetchShaftJobsForPp(ppId).then((jobs) => {
    const ids = [
      ...new Set(
        (jobs || [])
          .map((j) => String(j.job || "").trim())
          .filter(Boolean)
      ),
    ];
    if (ids.length <= 1) {
      return ids[0] || "";
    }
    return new Promise((resolve) => {
      const d = new frappe.ui.Dialog({
        title: __("Select Job ID"),
        fields: [
          {
            fieldname: "job_id",
            fieldtype: "Select",
            label: __("Job ID"),
            options: ids.join("\n"),
            reqd: 1,
            default: ids[0],
          },
        ],
        primary_action_label: __("Continue"),
        primary_action(values) {
          d.hide();
          resolve(values.job_id || ids[0]);
        },
      });
      d.show();
    });
  });
}

function buildRollPayload(row) {
  return {
    pp_id: row.pp_id,
    planning_table_row: row.planning_table_row,
    party_code: row.party_code,
    item_code: row.item_code,
    item_name: row.item_name,
    quality: row.quality,
    color: row.color,
    gsm: row.gsm,
    batch_no: row.batch_no,
    roll_no: row.roll_no,
    width_inch: row.width_inch,
    meter_roll: row.meter_roll,
    produced_length_mtrs: row.produced_length_mtrs,
    produced_gsm: row.produced_gsm,
    net_weight: row.net_weight,
    gross_weight: row.gross_weight,
    planned_qty: row.planned_qty,
    work_order: row.work_order,
    uom: row.uom || "Kg",
    custom_core_width_mm: row.custom_core_width_mm,
    custom_polybag_kgs: row.custom_polybag_kgs,
    custom_diameter_inches: row.custom_diameter_inches,
    custom_cbm_cubic_meters: row.custom_cbm_cubic_meters,
    job_id: row.job_id || row.job || "",
    is_bundle_row: row.is_bundle_row ? 1 : 0,
    row_locked: row.row_locked ? 1 : 0,
    row_ready_for_print: row.row_ready_for_print ? 1 : 0,
  };
}

function buildSessionSprsPayload() {
  return sessionSprList.value.map((s) => ({
    pp_id: s.pp_id,
    spr_name: s.spr_name,
    order_code: s.order_code,
  }));
}

async function clearGridEntries() {
  if (!rollLines.value.length && !sessionSprList.value.length) {
    return;
  }
  frappe.confirm(
    __("Clear all roll rows from this screen? Server SPRs are kept — click Create new SPRs for another entry on the same shift."),
    () => {
      rollLines.value = [];
      sessionSprs.value = {};
      sessionJobApiBaseline.value = {};
      forceNewSprSession.value = true;
      resetBatchSeriesCache();
      saveStatus.value = "Cleared — create new SPRs";
      scheduleAutosave();
      frappe.show_alert({ message: __("Grid cleared"), indicator: "blue" });
    }
  );
}

async function createSprs() {
  if (!canCreateSprs.value) {
    return;
  }
  const entries = buildSessionEntries();
  if (!entries.length) {
    frappe.msgprint(__("Select at least one line."));
    return;
  }
  saveStatus.value = "Creating SPRs…";
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.create_gsm_sprs_for_session",
      args: {
        run_date: runDate.value,
        shift: shift.value,
        unit: headerUnit.value,
        operator: operator.value,
        supervisor: supervisor.value,
        entries: JSON.stringify(entries),
        force_new_session: forceNewSprSession.value ? 1 : 0,
      },
    });
    const sprs = (res.message || {}).sprs || [];
    const next = { ...sessionSprs.value };
    const errors = [];
    for (const row of sprs) {
      if (row.status === "ok" && row.spr_name) {
        next[row.pp_id] = {
          pp_id: row.pp_id,
          spr_name: row.spr_name,
          order_code: row.order_code,
          label_type: row.label_type,
          reused: row.reused,
        };
      } else {
        errors.push(row.message || row.pp_id);
      }
    }
    sessionSprs.value = next;
    forceNewSprSession.value = false;
    recordJobApiBaselines(jobBoardJobs.value);
    scheduleAutosave();
    if (errors.length) {
      frappe.msgprint({
        title: __("Some SPRs failed"),
        message: errors.join("<br>"),
        indicator: "orange",
      });
    }
    const okCount = sprs.filter((s) => s.status === "ok").length;
    if (okCount) {
      frappe.show_alert({ message: __("{0} SPR(s) ready", [okCount]), indicator: "green" });
    }
    saveStatus.value = "SPRs created";
  } catch (e) {
    console.error(e);
    saveStatus.value = "SPR create failed";
    frappe.msgprint(__("Could not create SPRs. Check console."));
  }
}

function openToleranceDialog(orders) {
  toleranceOrders.value = orders || [];
  const form = {};
  for (const o of toleranceOrders.value) {
    form[o.spr_name] = { reason: "", approved: false };
  }
  toleranceForm.value = form;
  showToleranceDialog.value = true;
}

async function callSubmitGsm(overrides = []) {
  return frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.submit_gsm_production_entry",
    args: {
      run_date: runDate.value,
      shift: shift.value,
      unit: headerUnit.value,
      operator: operator.value,
      supervisor: supervisor.value,
      rolls: JSON.stringify(rollLines.value.filter((r) => !r.is_bundle_row).map(buildRollPayload)),
      session_sprs: JSON.stringify(buildSessionSprsPayload()),
      tolerance_overrides: JSON.stringify(overrides),
    },
  });
}

async function submitEntry(overrides = []) {
  if (!canSubmitEntry.value && !overrides.length) {
    frappe.msgprint(__("Create SPRs, enter rolls, and Save Row on each line before submit."));
    return;
  }
  const missingSpr = [...new Set(rollLines.value.map((r) => r.pp_id))].filter((pp) => !sprNameForPp(pp));
  if (missingSpr.length) {
    frappe.msgprint(__("Create SPRs for all selected orders first."));
    return;
  }
  submitInProgress.value = true;
  saveStatus.value = "Submitting…";
  try {
    const res = await callSubmitGsm(overrides);
    const msg = res.message || {};
    if (msg.status === "tolerance_required") {
      openToleranceDialog(msg.orders || []);
      saveStatus.value = "Tolerance approval needed";
      return;
    }
    if (msg.status === "import_failed" || msg.status === "failed") {
      const errs = (msg.failed || []).map((f) => `${f.spr_name || f.pp_id}: ${f.error}`).join("<br>");
      frappe.msgprint({ title: __("Submit failed"), message: errs || __("Unknown error"), indicator: "red" });
      saveStatus.value = "Submit failed";
      return;
    }
    showToleranceDialog.value = false;
    const submitted = msg.submitted || [];
    const partial = (msg.failed || []).length;
    if (partial) {
      frappe.msgprint({
        title: __("Partial submit"),
        message: (msg.failed || []).map((f) => `${f.spr_name}: ${f.error}`).join("<br>"),
        indicator: "orange",
      });
    }
    if (submitted.length) {
      const links = submitted.map((s) => `<a href="/app/shaft-production-run/${s.spr_name}">${s.spr_name}</a>`).join(", ");
      frappe.msgprint({
        title: __("Submitted"),
        message: __("{0} SPR(s) submitted: {1}", [submitted.length, links]),
        indicator: "green",
      });
    }
    saveStatus.value = "Submitted";
    await fetchOrders();
  } catch (e) {
    console.error(e);
    saveStatus.value = "Submit failed";
    frappe.msgprint(__("Submit failed. Check console."));
  } finally {
    submitInProgress.value = false;
  }
}

function submitWithTolerance() {
  if (!toleranceFormComplete.value) {
    frappe.msgprint(__("Enter reason and approve for every order."));
    return;
  }
  const overrides = toleranceOrders.value.map((o) => ({
    spr_name: o.spr_name,
    reason: (toleranceForm.value[o.spr_name]?.reason || "").trim(),
    approved: toleranceForm.value[o.spr_name]?.approved ? 1 : 0,
  }));
  submitEntry(overrides);
}

async function saveRow(row) {
  const sprName = sprNameForPp(row.pp_id);
  if (!sprName) {
    frappe.msgprint(__("Click Create SPRs first, then Save Row."));
    return;
  }
  if (!row.batch_no) {
    frappe.msgprint(__("Batch number is required."));
    return;
  }
  const gross = sprNormalizeGrossWeightInput(row.gross_weight);
  if (gross <= 0) {
    frappe.msgprint(__("Enter gross weight before saving."));
    return;
  }
  const updated = sprRecalcRollRow({ ...row, core_width_options: coreWidthOptions.value });
  Object.assign(row, updated);
  saveStatus.value = "Saving row…";
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.save_gsm_roll_line",
      args: {
        spr_name: sprName,
        shift: shift.value,
        roll_payload: JSON.stringify(buildRollPayload({ ...row, row_locked: 1, row_ready_for_print: 1 })),
      },
    });
    const msg = res.message || {};
    row.row_locked = 1;
    row.row_ready_for_print = 1;
    if (msg.row_name) {
      row.spr_item_name = msg.row_name;
    }
    scheduleAutosave();
    saveStatus.value = "Saved to SPR";
    frappe.show_alert({ message: __("Row saved to {0}", [sprName]), indicator: "green" });
    await loadJobBoard();
  } catch (e) {
    console.error(e);
    saveStatus.value = "Save failed";
    frappe.msgprint(__("Could not save row to server."));
  }
}

function editRow(row) {
  row.row_locked = 0;
  row.row_ready_for_print = 0;
  scheduleAutosave();
}

function isRowLabelReady(row) {
  return !!(row.row_locked || row.row_ready_for_print || row.spr_item_name);
}

async function resolveSprItemRowName(row) {
  if (row.spr_item_name) {
    return row.spr_item_name;
  }
  const sprName = sprNameForPp(row.pp_id);
  if (!sprName || !row.batch_no) {
    return "";
  }
  try {
    const res = await frappe.db.get_list("Shaft Production Run Item", {
      filters: { parent: sprName, batch_no: row.batch_no },
      fields: ["name"],
      limit: 1,
    });
    const name = res?.[0]?.name || "";
    if (name) {
      row.spr_item_name = name;
      row.row_locked = 1;
      row.row_ready_for_print = 1;
      scheduleAutosave();
    }
    return name;
  } catch (e) {
    return "";
  }
}

async function printLabel(row) {
  if (!isRowLabelReady(row)) {
    frappe.msgprint(__("Save Row first to enable the label."));
    return;
  }
  const sprName = sprNameForPp(row.pp_id);
  if (!sprName) {
    frappe.msgprint(__("Create SPRs first."));
    return;
  }
  if (row.is_bundle_row) {
    try {
      await gsmPrintBundleLabel(sprName, row);
    } catch (e) {
      console.error(e);
      frappe.msgprint(__("Could not open bundle label print."));
    }
    return;
  }
  let itemName = row.spr_item_name || (await resolveSprItemRowName(row));
  if (!itemName) {
    frappe.msgprint(__("Save Row first to enable the label."));
    return;
  }
  try {
    await gsmPrintRollLabel(sprName, itemName, row);
  } catch (e) {
    console.error(e);
    frappe.msgprint(__("Could not open label print."));
  }
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
  const rows = filteredPpSubmittedRows.value;
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

async function loadJobBoard() {
  const ppIds = [...filteredPpIdSet.value];
  if (!ppIds.length) {
    jobBoardJobs.value = [];
    return;
  }
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_pp_job_board",
      args: {
        pp_ids: JSON.stringify(ppIds),
        run_date: runDate.value,
        shift: shift.value,
        unit: filterUnit.value || headerUnit.value || undefined,
      },
    });
    jobBoardJobs.value = res.message?.jobs || [];
    recordJobApiBaselines(jobBoardJobs.value);
  } catch (e) {
    console.warn("job board", e);
    jobBoardJobs.value = [];
  }
}

function enrichSelectedEntriesFromBoard() {
  if (!selectedEntries.value.length) {
    return;
  }
  let changed = false;
  const next = selectedEntries.value.map((entry) => {
    const jid = entry.jobId || entry.job_id;
    if (jid && entry.ppId) {
      const job = jobBoardJobs.value.find((j) => j.pp_id === entry.ppId && String(j.job_id) === String(jid));
      if (job) {
        const snap = snapshotFromJob(job);
        if (entry.key !== snap.key || entry.combination_label !== snap.combination_label) {
          changed = true;
          return { ...entry, ...snap, key: entry.key };
        }
      }
      return entry;
    }
    const live = lineById.value.get(entry.lineId);
    if (!live) {
      return entry;
    }
    const livePd = live.plannedDate || linePlannedDate(live.source || {});
    if (entry.ppId && entry.orderCode && entry.plannedDate === livePd) {
      return entry;
    }
    changed = true;
    return snapshotFromLine({ ...live, plannedDate: entry.plannedDate || livePd });
  });
  if (changed) {
    selectedEntries.value = next;
    scheduleAutosave();
  }
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
    await Promise.all([fetchMerges(), loadQuotaForLines(), loadJobBoard()]);
    pruneSelectedEntriesToFilter();
    enrichSelectedEntriesFromBoard();
  } catch (e) {
    console.error(e);
    frappe.msgprint("Failed to load orders");
  } finally {
    loadingOrders.value = false;
  }
}

function onUnitChange() {
  if (shiftOpened.value && filterUnit.value !== headerUnit.value) {
    frappe.msgprint(__("Close the current shift before changing unit."));
    filterUnit.value = headerUnit.value;
    return;
  }
  headerUnit.value = filterUnit.value;
  pruneSelectedEntriesToFilter();
  fetchMerges().then(() =>
    Promise.all([loadQuotaForLines(), loadJobBoard()]).then(() => {
      pruneSelectedEntriesToFilter();
      enrichSelectedEntriesFromBoard();
    })
  );
  refreshShiftSession();
  scheduleAutosave();
}

function pickEmployeeLink(fieldKey, label) {
  const targetRef = fieldKey === "supervisor" ? supervisor : operator;
  const d = new frappe.ui.Dialog({
    title: label,
    fields: [
      {
        fieldtype: "Link",
        fieldname: "employee",
        label,
        options: "Employee",
        reqd: 1,
        default: targetRef.value || "",
      },
    ],
    primary_action_label: __("Select"),
    primary_action(values) {
      if (values.employee) {
        targetRef.value = values.employee;
      }
      d.hide();
    },
  });
  d.show();
}

function applyShiftSessionHydration(session) {
  shiftSession.value = session || null;
  if (session && session.status === "Open") {
    operator.value = session.operator || "";
    supervisor.value = session.supervisor || "";
    shiftBatchPrefix.value = session.batch_series_prefix || "";
    if (session.batch_series_prefix) {
      seriesPrefix.value = session.batch_series_prefix;
    }
    startShiftReminderTimers();
  } else {
    shiftBatchPrefix.value = "";
    stopShiftReminderTimers();
  }
}

async function loadShiftStatusForDate() {
  if (!headerUnit.value || !runDate.value) {
    shiftStatusByShift.value = {};
    return;
  }
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_shift_sessions_for_date",
      args: {
        run_date: runDate.value,
        unit: headerUnit.value,
      },
    });
    shiftStatusByShift.value = res.message?.shifts || {};
  } catch (e) {
    console.warn("shift status", e);
    shiftStatusByShift.value = {};
  }
}

async function previewShiftBatchPrefix() {
  if (!headerUnit.value || !runDate.value || !shift.value || shiftOpened.value) {
    return;
  }
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.preview_gsm_shift_batch_prefix",
      args: {
        run_date: runDate.value,
        shift: shift.value,
        unit: headerUnit.value,
      },
    });
    shiftPreviewBatch.value = res.message?.series_prefix || "";
  } catch (e) {
    console.warn("shift batch preview", e);
    shiftPreviewBatch.value = "";
  }
}

async function refreshShiftSession() {
  if (!headerUnit.value || !runDate.value || !shift.value) {
    shiftSessionReady.value = true;
    shiftSession.value = null;
    shiftPreviewBatch.value = "";
    await loadShiftStatusForDate();
    return;
  }
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.get_gsm_shift_session",
      args: {
        run_date: runDate.value,
        shift: shift.value,
        unit: headerUnit.value,
      },
    });
    const session = res.message?.session || null;
    applyShiftSessionHydration(session);
    await loadShiftStatusForDate();
    if (!session) {
      await previewShiftBatchPrefix();
    } else {
      shiftPreviewBatch.value = session.batch_series_prefix || "";
    }
  } catch (e) {
    console.warn("shift session", e);
    applyShiftSessionHydration(null);
  } finally {
    shiftSessionReady.value = true;
  }
}

async function startShift() {
  if (!operator.value || !supervisor.value) {
    frappe.msgprint(__("Select Operator and Supervisor."));
    return;
  }
  shiftOpeningBusy.value = true;
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.open_gsm_shift_session",
      args: {
        run_date: runDate.value,
        shift: shift.value,
        unit: headerUnit.value,
        operator: operator.value,
        supervisor: supervisor.value,
      },
    });
    applyShiftSessionHydration(res.message?.session || null);
    await loadShiftStatusForDate();
    scheduleAutosave();
    frappe.show_alert({ message: __("Shift opened"), indicator: "green" });
  } catch (e) {
    console.error(e);
  } finally {
    shiftOpeningBusy.value = false;
  }
}

function clearGsmAfterClose() {
  selectionLocked.value = false;
  selectedEntries.value = [];
  rollLines.value = [];
  sessionSprs.value = {};
  sessionJobApiBaseline.value = {};
  forceNewSprSession.value = true;
  resetBatchSeriesCache();
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("gsm_production_entry_draft_v2");
  } catch (e) {
    console.warn("draft clear", e);
  }
  saveStatus.value = "";
}

function redirectToShiftWise(redirect) {
  const payload = redirect || {};
  const opts = payload.route_options || {};
  frappe.route_options = { ...opts };
  const doctype = payload.doctype || "Shift Wise Production Entry";
  frappe.set_route("Form", doctype, "new");
}

function dismissShiftReminder() {
  showShiftReminder.value = false;
  shiftReminderDismissedAt = Date.now();
}

function closeShiftFromReminder() {
  showShiftReminder.value = false;
  closeShift();
}

function stopShiftReminderTimers() {
  if (shiftReminderTimer) {
    clearTimeout(shiftReminderTimer);
    shiftReminderTimer = null;
  }
  if (shiftReminderInterval) {
    clearInterval(shiftReminderInterval);
    shiftReminderInterval = null;
  }
  showShiftReminder.value = false;
}

function startShiftReminderTimers() {
  stopShiftReminderTimers();
  const thirtyMin = 30 * 60 * 1000;
  shiftReminderTimer = setTimeout(() => {
    if (shiftOpened.value) {
      showShiftReminder.value = true;
    }
  }, thirtyMin);
  shiftReminderInterval = setInterval(() => {
    if (!shiftOpened.value) {
      return;
    }
    const sinceDismiss = Date.now() - shiftReminderDismissedAt;
    if (sinceDismiss >= thirtyMin) {
      showShiftReminder.value = true;
    }
  }, thirtyMin);
}

async function closeShift() {
  if (!shiftOpened.value || shiftClosingBusy.value) {
    return;
  }
  shiftClosingBusy.value = true;
  try {
    const validation = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.validate_gsm_shift_close",
      args: {
        run_date: runDate.value,
        shift: shift.value,
        unit: headerUnit.value,
        session_sprs: sessionSprList.value,
      },
    });
    const errors = validation.message?.errors || [];
    if (errors.length) {
      frappe.msgprint(errors.join("<br>"));
      return;
    }
    await new Promise((resolve, reject) => {
      frappe.confirm(
        __("Close shift? This will clear GSM entries and open Shift Wise Production Entry."),
        () => resolve(),
        () => reject(new Error("cancelled"))
      );
    });
    const res = await frappe.call({
      method: "production_entry.production_planning.unified_production_entry_api.close_gsm_shift_session",
      args: {
        run_date: runDate.value,
        shift: shift.value,
        unit: headerUnit.value,
      },
    });
    const nextShift = res.message?.next_shift;
    clearGsmAfterClose();
    applyShiftSessionHydration(null);
    if (nextShift) {
      shift.value = nextShift;
      shiftFilterShift.value = nextShift;
    }
    await refreshShiftSession();
    redirectToShiftWise(res.message?.redirect);
  } catch (e) {
    if (e?.message !== "cancelled") {
      console.error(e);
    }
  } finally {
    shiftClosingBusy.value = false;
  }
}

function onShiftHeaderChange() {
  refreshShiftSession();
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

function syncBatchCounterFromGrid() {
  let mx = maxRollSuffix.value;
  for (const bn of reservedBatchNos.value) {
    if (bn.includes("/")) {
      const suf = parseInt(bn.split("/").pop(), 10);
      if (!Number.isNaN(suf)) {
        mx = Math.max(mx, suf);
      }
    }
  }
  for (const r of rollLines.value) {
    const rn = parseInt(r.roll_no, 10);
    if (!Number.isNaN(rn)) {
      mx = Math.max(mx, rn);
    }
    const bn = _cstr(r.batch_no || "");
    if (bn.includes("/")) {
      const suf = parseInt(bn.split("/").pop(), 10);
      if (!Number.isNaN(suf)) {
        mx = Math.max(mx, suf);
      }
    }
  }
  maxRollSuffix.value = mx;
}

function _cstr(v) {
  return v == null ? "" : String(v).trim();
}

function fabricWidthToStockCoreInch(widthInch) {
  const w = sprFlt(widthInch);
  if (w <= 0) {
    return 63;
  }
  for (const k of [63, 85, 90, 118, 126]) {
    if (Math.abs(w - k) < 0.6) {
      return k;
    }
  }
  if (w < 63) {
    return 63;
  }
  if (w < 85) {
    return 85;
  }
  if (w < 90) {
    return 90;
  }
  if (w < 118) {
    return 118;
  }
  return 126;
}

function pickCoreForFabricWidth(widthInch, apiCoreValue) {
  const opts = coreWidthOptions.value || [];
  const raw = _cstr(apiCoreValue);
  if (raw && opts.some((o) => o.value === raw)) {
    return raw;
  }
  const targetInch = fabricWidthToStockCoreInch(widthInch);
  const byInch = opts.find((o) => Math.abs(sprFlt(o.core_inch) - targetInch) < 0.6);
  if (byInch?.value) {
    return byInch.value;
  }
  const labelMatch = opts.find(
    (o) =>
      _cstr(o.label).startsWith(String(targetInch)) ||
      _cstr(o.value).startsWith(String(targetInch))
  );
  if (labelMatch?.value) {
    return labelMatch.value;
  }
  return raw || opts[0]?.value || "";
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
        pp_id: line.ppId || src.pp_id,
        production_plan_item: line.id,
      },
    });
    return res.message || {};
  } catch (e) {
    return {
      planned_qty: 0,
      custom_polybag_kgs: 0,
      custom_core_width_mm: pickCoreForFabricWidth(line.width_inch, ""),
      core_width_mm: 0,
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
        value: r.core_size || r.value || r.item_code || "",
        core_size: r.core_size || r.value || "",
        item_code: r.item_code || "",
        label: r.label || r.core_size || r.value || `${r.width_mm} mm`,
        width_mm: sprFlt(r.width_mm) || 1600,
        core_inch: sprFlt(r.core_inch) || 0,
      }));
    }
  } catch (e) {
    console.warn("core width options", e);
  }
}

function pickJobAndWidthForRow() {
  if (!selectedEntries.value.length) {
    return Promise.resolve(null);
  }
  const entries = selectedEntries.value;
  if (entries.length === 1) {
    const entry = entries[0];
    const key = entry.key || entryKeyJob(entry.ppId, entry.jobId || entry.job_id);
    addRollJobChoice.value = key;
    const rawJob = jobBoardJobs.value.find((j) => entryKeyJob(j.pp_id, j.job_id) === key);
    if (!rawJob) {
      return Promise.resolve(null);
    }
    const job = withLocalPendingQuota(rawJob);
    const addable = (job.width_segments || []).filter((s) => s.can_add);
    const maxed = !canJobAddOneMoreRoll(job);
    if (!maxed && addable.length === 1) {
      return Promise.resolve({ job: rawJob, widthInch: addable[0].width_inch });
    }
    addRollWizardSkipJobStep.value = true;
    addRollWizardStep.value = 2;
    addRollWidthChoice.value =
      addable[0]?.width_inch ?? job.width_segments?.[0]?.width_inch ?? null;
    showAddRollWizard.value = true;
    return new Promise((resolve) => {
      pendingAddRowResolve = resolve;
    });
  }
  addRollWizardSkipJobStep.value = false;
  addRollWizardStep.value = 1;
  const first = entries[0];
  addRollJobChoice.value = first.key || entryKeyJob(first.ppId, first.jobId || first.job_id);
  addRollWidthChoice.value = null;
  showAddRollWizard.value = true;
  return new Promise((resolve) => {
    pendingAddRowResolve = resolve;
  });
}

function cancelAddRollWizard() {
  showAddRollWizard.value = false;
  addRollWizardStep.value = 1;
  addRollWizardSkipJobStep.value = false;
  if (pendingAddRowResolve) {
    pendingAddRowResolve(null);
    pendingAddRowResolve = null;
  }
}

function manualJobContextForPp(ppId) {
  const lineIds = [
    ...new Set(
      selectedEntries.value
        .filter((e) => e.ppId === ppId)
        .map((e) => e.lineId)
        .filter(Boolean)
    ),
  ];
  return { ppId, planningNames: lineIds };
}

async function openManualJobForPp(ppId) {
  if (!ppId) {
    frappe.msgprint(__("No order selected for Manual Job."));
    return;
  }
  const ctx = manualJobContextForPp(ppId);
  await gsmOpenManualJob(
    ctx.ppId,
    ctx.planningNames,
    headerUnit.value,
    runDate.value,
    shift.value,
    () => Promise.all([fetchOrders(), loadJobBoard()])
  );
}

async function openManualJobFromWizard() {
  const job = wizardSelectedJob.value;
  cancelAddRollWizard();
  if (job) {
    await openManualJobForPp(job.pp_id);
  }
}

async function openManualJobForAllMaxed() {
  const ppIds = [...new Set(selectedEntries.value.map((e) => e.ppId).filter(Boolean))];
  if (!ppIds.length) {
    return;
  }
  if (ppIds.length === 1) {
    await openManualJobForPp(ppIds[0]);
    return;
  }
  const options = ppIds.map((ppId) => {
    const meta = orderMetaForPp(ppId);
    return { value: ppId, label: meta.orderCode || ppId };
  });
  frappe.prompt(
    [
      {
        fieldtype: "Select",
        fieldname: "pp_id",
        label: __("Order for Manual Job"),
        options,
        reqd: 1,
        default: ppIds[0],
      },
    ],
    (values) => openManualJobForPp(values.pp_id),
    __("Choose order for Manual Job"),
    __("Open")
  );
}

function proceedAddRollWizard() {
  if (addRollWizardStep.value === 1) {
    if (!addRollJobChoice.value) {
      return;
    }
    addRollWizardStep.value = 2;
    const segs = wizardWidthSegments.value;
    const pick = segs.find((s) => s.can_add) || segs[0];
    addRollWidthChoice.value = pick?.width_inch ?? null;
    return;
  }
  const key = addRollJobChoice.value;
  const rawJob = jobBoardJobs.value.find((j) => entryKeyJob(j.pp_id, j.job_id) === key);
  const widthInch = sprFlt(addRollWidthChoice.value);
  showAddRollWizard.value = false;
  addRollWizardStep.value = 1;
  addRollWizardSkipJobStep.value = false;
  if (pendingAddRowResolve) {
    pendingAddRowResolve(rawJob && widthInch > 0 ? { job: rawJob, widthInch } : null);
    pendingAddRowResolve = null;
  }
}

async function addRollRow() {
  if (addRollInProgress.value) {
    return;
  }
  if (!selectionLocked.value) {
    frappe.msgprint("Confirm and lock your GSM selection first.");
    return;
  }
  if (!sessionSprList.value.length) {
    frappe.msgprint(__("Click Create SPRs before adding roll rows."));
    return;
  }
  if (!headerUnit.value) {
    frappe.msgprint("Select a unit filter first.");
    return;
  }
  addRollInProgress.value = true;
  try {
  const pick = await pickJobAndWidthForRow();
  if (!pick) {
    return;
  }
  const { widthInch, job: pickedJob } = pick;
  const rawJob =
    jobBoardJobs.value.find(
      (j) => j.pp_id === pickedJob.pp_id && String(j.job_id) === String(pickedJob.job_id)
    ) || pickedJob;
  const job = withLocalPendingQuota(rawJob);
  if (!canJobAddOneMoreRoll(job)) {
    frappe.confirm(
      __("Job roll limit reached ({0}/{1}) — use Manual Job. Open Manual Job now?", [
        effectiveJobRollCount(job),
        job.max_rolls,
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
            () => Promise.all([fetchOrders(), loadJobBoard()])
          );
        }
      }
    );
    return;
  }
  if (!canJobAddWidthRoll(job, widthInch)) {
    const seg = (job.width_segments || []).find((s) => Math.abs(sprFlt(s.width_inch) - widthInch) < 0.05);
    frappe.confirm(
      __("Width {0}\" is full ({1}/{2}) — use Manual Job. Open Manual Job now?", [
        widthInch,
        effectiveWidthRollCount(job, widthInch),
        seg?.max || job.max_rolls,
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
            () => Promise.all([fetchOrders(), loadJobBoard()])
          );
        }
      }
    );
    return;
  }
  const baseLine = firstPtLineForPp(job.pp_id, job.gsm);
  if (!baseLine) {
    frappe.msgprint(__("No planning line found for this order."));
    return;
  }
  const line = {
    ...baseLine,
    ppId: job.pp_id,
    width_inch: widthInch,
    widthLabel: `${widthInch}"`,
  };
  const jobId = job.job_id;
  const src = line.source;
  const [batchInfo, ordLen, wo] = await Promise.all([
    previewNextBatch(line.ppId),
    resolveOrderLength(line),
    resolveWorkOrder(line),
  ]);
  let batch = batchInfo;
  if (batch?.batch_no && rollLines.value.some((r) => r.batch_no === batch.batch_no)) {
    batch = await previewNextBatch(line.ppId);
  }
  if (!batch?.batch_no || rollLines.value.some((r) => r.batch_no === batch.batch_no)) {
    frappe.msgprint(__("Could not assign a unique batch number. Try again."));
    return;
  }
  const extras = await fetchRollRowExtras(line, ordLen);
  const coreItem = pickCoreForFabricWidth(
    line.width_inch,
    extras.custom_core_width_mm || extras.core_size || ""
  );
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
    batch_no: batch.batch_no || "",
    roll_no: batch.roll_no || "",
    width_inch: line.width_inch,
    meter_roll: ordLen,
    produced_length_mtrs: "",
    produced_gsm: 0,
    net_weight: 0,
    gross_weight: "",
    planned_qty: sprFlt(extras.planned_qty),
    uom: src.uom || src.stock_uom || "Kg",
    custom_core_width_mm: coreItem,
    custom_polybag_kgs: extras.custom_polybag_kgs || 0,
    custom_diameter_inches: "",
    custom_cbm_cubic_meters: "",
    work_order: wo,
    job_id: jobId,
    row_locked: 0,
    row_ready_for_print: 0,
    core_width_options: coreWidthOptions.value,
  });
  rollLines.value.unshift(newRow);
  scheduleAutosave();
  } finally {
    addRollInProgress.value = false;
  }
}

async function previewNextBatch(ppId) {
  syncBatchCounterFromGrid();
  const existing = allExistingBatchNos();
  const sprName = ppId ? sprNameForPp(ppId) : "";
  if (sprName) {
    try {
      const res = await frappe.call({
        method:
          "production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_next_spr_batch_numbers",
        args: {
          shaft_production_run: sprName,
          count: 1,
          client_max_roll: maxRollSuffix.value,
          run_date: runDate.value,
          custom_unit: headerUnit.value,
          shift: shift.value,
          client_series_prefix: seriesPrefix.value || undefined,
          existing_batches: JSON.stringify(existing),
        },
      });
      const row = (res.message || [])[0];
      if (row?.batch_no) {
        reserveBatchNo(row.batch_no, row.roll_no);
      }
      return row || { batch_no: "", roll_no: "" };
    } catch (e) {
      console.warn("get_next_spr_batch_numbers", e);
    }
  }
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
      session_local: 1,
    },
  });
  const row = (res.message || [])[0];
  if (row?.batch_no) {
    reserveBatchNo(row.batch_no, row.roll_no);
  } else if (row?.series_prefix) {
    seriesPrefix.value = row.series_prefix;
  }
  return row || { batch_no: "", roll_no: "" };
}

async function removeTopRow() {
  if (!rollLines.value.length) {
    return;
  }
  const row = rollLines.value[0];
  const sprName = sprNameForPp(row.pp_id);
  const wasSaved = !!(row.spr_item_name || (row.row_locked && row.batch_no));

  const doRemove = async () => {
    if (row.is_bundle_row && sprName && (row.batch_no || row.child_roll_batches?.length)) {
      saveStatus.value = "Deleting bundle from SPR…";
      try {
        await frappe.call({
          method: "production_entry.production_planning.unified_production_entry_api.delete_gsm_bundle_packaging",
          args: {
            spr_name: sprName,
            bundle_batch_no: row.batch_no || "",
            child_roll_batches: JSON.stringify(row.child_roll_batches || []),
          },
        });
      } catch (e) {
        console.error(e);
        saveStatus.value = "Delete failed";
        frappe.msgprint(__("Could not remove bundle from {0}.", [sprName]));
        return;
      }
    } else if (wasSaved && sprName && row.batch_no) {
      saveStatus.value = "Deleting from SPR…";
      try {
        await frappe.call({
          method: "production_entry.production_planning.unified_production_entry_api.delete_gsm_roll_line",
          args: {
            spr_name: sprName,
            batch_no: row.batch_no,
            row_name: row.spr_item_name || undefined,
          },
        });
      } catch (e) {
        console.error(e);
        saveStatus.value = "Delete failed";
        frappe.msgprint(__("Could not remove row from {0}.", [sprName]));
        return;
      }
    }
    rollLines.value.shift();
    syncBatchCounterFromGrid();
    scheduleAutosave();
    saveStatus.value = wasSaved ? "Removed from SPR" : "Row removed";
    await loadJobBoard();
  };

  if ((wasSaved && sprName) || (row.is_bundle_row && row.child_roll_batches?.length)) {
    frappe.confirm(
      __("Remove this row from the grid and delete it from {0}?", [sprName]),
      () => {
        doRemove();
      }
    );
    return;
  }
  await doRemove();
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
      selectedEntries: selectedEntries.value,
      selectionLocked: selectionLocked.value,
      rollLines: rollLines.value,
      seriesPrefix: seriesPrefix.value,
      maxRollSuffix: maxRollSuffix.value,
      sessionSprs: sessionSprs.value,
      creationSeq: creationSeq.value,
      batchContextKey: currentBatchContextKey(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    if (!saveStatus.value || saveStatus.value === "Saved locally") {
      saveStatus.value = "Draft saved";
    }
  } catch (e) {
    saveStatus.value = "Save failed";
  }
}

function restoreDraft() {
  try {
    let raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      raw = localStorage.getItem("gsm_production_entry_draft_v2");
    }
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
    if (d.selectedEntries?.length) {
      selectedEntries.value = d.selectedEntries;
    } else if (d.selectedLineIds?.length) {
      const pd = d.filterDate || filterDate.value;
      selectedEntries.value = d.selectedLineIds.map((id) => ({
        key: entryKey(pd, id),
        lineId: id,
        plannedDate: pd,
        ppId: "",
        orderCode: "",
        quality: "",
        color: "",
        gsm: 0,
        width_inch: 0,
        widthLabel: "",
        dayTargetKg: 0,
        sourceSnapshot: {},
      }));
    } else {
      selectedEntries.value = [];
    }
    selectionLocked.value = !!d.selectionLocked;
    rollLines.value = (d.rollLines || []).map((r) => ({
      ...r,
      row_locked: !!r.row_locked,
      row_ready_for_print: !!r.row_ready_for_print,
    }));
    const ctxKey = currentBatchContextKey();
    if (d.batchContextKey && d.batchContextKey === ctxKey) {
      seriesPrefix.value = d.seriesPrefix || "";
      maxRollSuffix.value = d.maxRollSuffix || 0;
    } else {
      resetBatchSeriesCache();
    }
    batchContextKey.value = ctxKey;
    sessionSprs.value = d.sessionSprs || {};
    creationSeq.value = d.creationSeq || 0;
    syncBatchCounterFromGrid();
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

watch([runDate, shift, headerUnit], () => {
  const key = currentBatchContextKey();
  if (batchContextKey.value && batchContextKey.value !== key) {
    resetBatchSeriesCache();
    sessionSprs.value = {};
    sessionJobApiBaseline.value = {};
    forceNewSprSession.value = false;
  }
  batchContextKey.value = key;
  if (ppSubmittedRows.value.length) {
    loadJobBoard();
    loadQuotaForLines();
  }
  refreshShiftSession();
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
  batchContextKey.value = currentBatchContextKey();
  await refreshShiftSession();
});

onUnmounted(() => {
  if (autosaveTimer) {
    clearTimeout(autosaveTimer);
  }
  stopShiftReminderTimers();
});
</script>

<style scoped>
.gpe-root {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 15px;
  color: #0f172a;
  padding: 10px 12px;
  background: linear-gradient(160deg, #f1f5f9 0%, #e2e8f0 100%);
  min-height: 100vh;
  box-sizing: border-box;
  overflow-x: hidden;
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
  grid-template-columns: minmax(220px, 260px) minmax(0, 1fr);
  gap: 10px;
  align-items: stretch;
  height: calc(100vh - 168px);
  min-height: 520px;
}
.gpe-layout-entry {
  position: relative;
}
.gpe-shift-open-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.45);
  padding: 16px;
}
.gpe-shift-open-card {
  width: min(440px, 100%);
  padding: 20px 22px;
}
.gpe-shift-open-card h3 {
  margin: 0 0 6px;
}
.gpe-shift-open-fields {
  display: grid;
  gap: 12px;
  margin: 14px 0 16px;
}
.gpe-emp-link label {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 4px;
}
.gpe-emp-link-row {
  display: flex;
  gap: 8px;
}
.gpe-emp-link-row input {
  flex: 1;
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
}
.gpe-shift-batch-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gpe-shift-batch-label {
  font-size: 11px;
  color: #64748b;
}
.gpe-batch-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 13px;
  letter-spacing: 0.02em;
}
.gpe-batch-badge-wrap {
  flex: 1;
}
.gpe-session-head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.gpe-session-head-row .gpe-session-title {
  margin: 0;
}
.gpe-close-shift-btn {
  margin-left: auto;
}
.gpe-shift-status-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.gpe-shift-status-strip-compact {
  margin-top: -4px;
}
.gpe-shift-chip {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
}
.gpe-shift-chip.open {
  background: #ecfdf5;
  border-color: #6ee7b7;
  color: #047857;
}
.gpe-shift-chip.other-open {
  background: #fff7ed;
  border-color: #fdba74;
  color: #c2410c;
}
.gpe-shift-chip.closed {
  background: #f1f5f9;
  color: #64748b;
}
.gpe-shift-start-btn {
  width: 100%;
}
@media (max-width: 1100px) {
  .gpe-layout {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
  }
}
.gpe-sidebar {
  padding: 10px;
  max-height: none;
  height: 100%;
  overflow: auto;
}
.gpe-sidebar h3 {
  margin: 0 0 8px;
  font-size: 15px;
}
.gpe-session-panel {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 10px;
  font-size: 12px;
}
.gpe-session-panel-head {
  font-weight: 700;
  color: #3730a3;
  margin-bottom: 8px;
  font-size: 13px;
}
.gpe-session-entry {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  padding: 6px 0;
  border-bottom: 1px solid #e0e7ff;
  align-items: center;
}
.gpe-session-entry:last-of-type {
  border-bottom: none;
}
.gpe-session-date {
  background: #dbeafe;
  color: #1e40af;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 11px;
}
.gpe-session-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: #64748b;
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
.gpe-order-target,
.gpe-job-target {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 11px;
  width: 100%;
}
.gpe-order-target {
  padding: 0 2px 4px;
  margin-bottom: 6px;
}
.gpe-day-target {
  color: #1d4ed8;
  font-weight: 600;
}
.gpe-day-rem {
  color: #b45309;
  font-weight: 600;
}
.gpe-job-card {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  overflow: hidden;
}
.gpe-job-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}
.gpe-job-card.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}
.gpe-job-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}
.gpe-job-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  line-height: 1.3;
}
.gpe-job-head-dot {
  color: #94a3b8;
  font-weight: 700;
  font-size: 14px;
}
.gpe-job-title {
  font-weight: 800;
  font-size: 15px;
  color: #0f172a;
  letter-spacing: -0.01em;
}
.gpe-job-gsm {
  font-weight: 800;
  font-size: 13px;
  color: #1d4ed8;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 5px;
  padding: 2px 8px;
  white-space: nowrap;
  line-height: 1.35;
}
.gpe-job-combination {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.4;
  padding: 7px 9px;
  background: #f1f5f9;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  word-break: break-word;
  overflow-wrap: anywhere;
  text-align: left;
  width: 100%;
  box-sizing: border-box;
}
.gpe-job-card.selected .gpe-job-combination {
  background: #dbeafe;
  border-color: #bfdbfe;
}
.gpe-dual-meter {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 8px;
  background: #f1f5f9;
  border-radius: 8px;
  width: 100%;
  box-sizing: border-box;
}
.gpe-dual-meter-full {
  background: #fef3c7;
}
.gpe-dual-meter-done {
  background: #ecfdf5;
}
.gpe-meter-col {
  text-align: center;
}
.gpe-meter-label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
  margin-bottom: 2px;
}
.gpe-meter-frac {
  font-size: 16px;
  font-weight: 600;
}
.gpe-meter-frac em {
  font-style: normal;
  color: #2563eb;
}
.gpe-meter-frac span {
  margin: 0 2px;
  color: #94a3b8;
}
.gpe-meter-frac strong {
  color: #0f172a;
}
.gpe-meter-context {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  width: 100%;
  text-align: left;
}
.gpe-shift-breakdown {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.45;
  width: 100%;
  text-align: left;
}
.gpe-shift-today {
  font-weight: 800;
  color: #0f172a;
}
.gpe-shift-part {
  font-weight: 700;
}
.gpe-shift-other {
  color: #c2410c;
}
.gpe-shift-other strong {
  color: #9a3412;
  font-weight: 800;
}
.gpe-shift-current {
  color: #2563eb;
  font-weight: 800;
}
.gpe-shift-current strong {
  color: #1d4ed8;
  font-weight: 800;
}
.gpe-job-remaining {
  font-size: 14px;
  color: #b45309;
  font-weight: 700;
  padding: 6px 8px;
  background: #fff7ed;
  border-radius: 6px;
  line-height: 1.35;
  width: 100%;
  box-sizing: border-box;
  text-align: left;
}
.gpe-job-foot {
  width: 100%;
}
.gpe-picker-sub {
  display: block;
  font-size: 11px;
  color: #64748b;
  font-style: normal;
  margin-top: 2px;
}
.gpe-picker-disabled {
  opacity: 0.55;
}
.gpe-picker-maxed {
  background: #fffbeb;
  border-radius: 6px;
}
.gpe-picker-maxed-tag {
  color: #b45309;
}
.gpe-picker-maxed-note {
  background: #fef3c7;
  border: 1px solid #fcd34d;
  color: #92400e;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
  font-size: 12px;
}
.gpe-btn.warn {
  border-color: #f59e0b;
  color: #92400e;
  background: #fffbeb;
}
.gpe-btn.warn:hover:not(:disabled) {
  background: #fef3c7;
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
  gap: 12px;
  margin-top: 12px;
  padding: 14px 16px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 12px;
}
.gpe-selection-strip-lg {
  padding: 16px 18px;
}
.gpe-selection-text {
  font-size: 15px;
  line-height: 1.5;
}
.gpe-session-title {
  margin: 0 0 10px;
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
}
.gpe-session-panel-main {
  padding: 16px 18px !important;
}
.gpe-header-fields-lg label {
  font-size: 13px;
  font-weight: 600;
}
.gpe-header-fields-lg input,
.gpe-header-fields-lg select {
  min-height: 36px;
  font-size: 14px;
  padding: 8px 10px;
}
.gpe-spr-table-title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 6px;
}
.gpe-spr-table-wrap {
  margin-top: 12px;
  overflow-x: auto;
}
.gpe-spr-table {
  width: 100%;
  max-width: 640px;
  border-collapse: collapse;
  font-size: 14px;
}
.gpe-spr-table th,
.gpe-spr-table td {
  border: 1px solid #e2e8f0;
  padding: 10px 14px;
  text-align: left;
}
.gpe-spr-table th {
  background: #f8fafc;
  font-weight: 600;
  color: #475569;
}
.gpe-shaft-block {
  margin-bottom: 16px;
}
.gpe-shaft-block-head {
  margin-bottom: 8px;
  font-size: 14px;
}
.gpe-shaft-grid {
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
  width: 160px;
  max-width: 180px;
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
  padding: 8px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.gpe-entry-workspace {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.gpe-session-panel-main {
  flex-shrink: 0;
}
.gpe-header.gpe-session-panel-main {
  padding: 8px;
  margin-bottom: 6px;
}
.gpe-header-session-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px 16px;
  margin-top: 6px;
}
.gpe-spr-inline {
  flex: 1 1 320px;
  min-width: 280px;
  margin-top: 0 !important;
}
.gpe-spr-ready-badge {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 8px;
  background: #dcfce7;
  color: #166534;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid #86efac;
}
.gpe-metrics-compact {
  margin: 4px 0 !important;
  flex-shrink: 0;
}
.gpe-metrics-compact .gpe-metric {
  padding: 6px 8px;
  font-size: 13px;
}
.gpe-metrics-compact .gpe-metric strong {
  font-size: 20px;
}
.gpe-gsm-legend {
  flex-shrink: 0;
  margin: 2px 0 4px;
  font-size: 13px;
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
.gpe-spr-table-wrap {
  margin-top: 10px;
  overflow-x: auto;
}
.gpe-spr-table {
  width: 100%;
  max-width: 520px;
  border-collapse: collapse;
  font-size: 12px;
}
.gpe-spr-table th,
.gpe-spr-table td {
  border: 1px solid #e2e8f0;
  padding: 6px 10px;
  text-align: left;
}
.gpe-spr-table th {
  background: #f8fafc;
  font-weight: 600;
  color: #475569;
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
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 4px 0;
  flex-shrink: 0;
}
.gpe-toolbar-left {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.gpe-toolbar-right {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.gpe-btn {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
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
.gpe-btn-warn {
  border-color: #f59e0b;
  color: #92400e;
  background: #fffbeb;
}
.gpe-btn-warn:hover:not(:disabled) {
  background: #fef3c7;
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
.gpe-grid-wrap-entry {
  overflow: auto;
  flex: 1 1 auto;
  min-height: 200px;
  max-height: none;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: inset -8px 0 12px -8px rgba(15, 23, 42, 0.12);
  -webkit-overflow-scrolling: touch;
}
.gpe-grid-entry {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 17px;
}
.gpe-grid-entry th,
.gpe-grid-entry td {
  border-bottom: 1px solid #f1f5f9;
  padding: 8px 10px;
  white-space: nowrap;
}
.gpe-grid-entry tbody td {
  font-size: 17px;
  font-weight: 600;
}
.gpe-grid-entry td.gpe-num,
.gpe-grid-entry th.gpe-num {
  text-align: center;
}
.gpe-grid-entry th {
  background: #f8fafc;
  position: sticky;
  top: 0;
  z-index: 2;
  font-size: 15px;
  font-weight: 700;
}
.gpe-sticky-col {
  position: sticky;
  z-index: 3;
  background: inherit;
}
.gpe-sticky-0 {
  left: 0;
  min-width: 36px;
}
.gpe-sticky-1 {
  left: 36px;
  min-width: 88px;
  box-shadow: 2px 0 4px -2px rgba(15, 23, 42, 0.08);
}
.gpe-grid-entry thead .gpe-sticky-col {
  background: #f8fafc;
  z-index: 4;
}
.gpe-len-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}
.gpe-inp-len {
  width: 72px;
}
.gpe-unit-suffix {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
}
.gpe-btn-label {
  font-size: 13px;
  padding: 6px 10px;
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
  width: 88px;
  min-height: 42px;
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 16px;
}
.gpe-grid-entry .gpe-inp {
  min-height: 42px;
  font-size: 16px;
}
.gpe-grid-entry .gpe-btn.sm {
  font-size: 13px;
  padding: 8px 12px;
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
  font-size: 14px;
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
.gpe-confirm-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin: 12px 0;
}
.gpe-confirm-grid th,
.gpe-confirm-grid td {
  border: 1px solid #e2e8f0;
  padding: 8px 10px;
  text-align: left;
}
.gpe-confirm-grid th {
  background: #f8fafc;
}
.gpe-dialog-wide {
  width: min(720px, 94vw);
  max-height: 85vh;
  overflow: auto;
}
.gpe-spr-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0 0;
  font-size: 12px;
}
.gpe-spr-chip {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  padding: 4px 8px;
}
.gpe-label-type {
  margin-left: 6px;
  color: #64748b;
  font-size: 11px;
}
.gpe-tol-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  margin: 12px 0;
}
.gpe-tol-card-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}
.gpe-tol-table {
  font-size: 12px;
  margin-bottom: 8px;
}
.gpe-tol-reason {
  display: block;
  font-size: 12px;
  margin-bottom: 8px;
}
.gpe-tol-reason textarea {
  width: 100%;
  margin-top: 4px;
}
.gpe-tol-check {
  display: flex;
  align-items: center;
  gap: 8px;
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
