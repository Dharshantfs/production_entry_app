<template>
  <div class="cc-container" :class="{ 'printed-bopp-film-table': isPrintedBoppTable, 'printing-105-table': isPrinting105Table }">
    <div class="cc-filters">
      <div class="cc-filter-title">{{ pageTitle }}</div>
      <div class="cc-filter-item">
        <label>View Scope</label>
        <select v-model="viewScope" @change="toggleViewScope" class="cc-select-scope">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>
      <div class="cc-filter-item" v-if="viewScope === 'daily'">
        <label>Planned Date</label>
        <input type="date" v-model="filterOrderDate" />
      </div>
      <div class="cc-filter-item" v-else-if="viewScope === 'weekly'">
        <label>Select Week</label>
        <input type="week" v-model="filterWeek" />
      </div>
      <div class="cc-filter-item" v-else-if="viewScope === 'monthly'">
        <label>Select Month</label>
        <input type="month" v-model="filterMonth" />
      </div>
      <div class="cc-filter-item cc-shift-filter">
        <label>Shift</label>
        <div class="cc-shift-btns">
          <button type="button" :class="{ active: filterShift === 'all' }" @click="filterShift = 'all'">All</button>
          <button type="button" :class="{ active: filterShift === 'day' }" @click="filterShift = 'day'">Day</button>
          <button type="button" :class="{ active: filterShift === 'night' }" @click="filterShift = 'night'">Night</button>
        </div>
      </div>
      <div v-if="!isPrintedBoppTable && !isPrinting105Table" class="cc-filter-item cc-shift-filter">
        <label>Lamination process</label>
        <div class="cc-shift-btns">
          <button type="button" :class="{ active: laminationProcess === '104' }" @click="setLaminationProcess('104')">104 Plain Lamination Fabric</button>
          <button type="button" :class="{ active: laminationProcess === '107' }" @click="setLaminationProcess('107')">107 BOPP Lamination Fabric</button>
          <button type="button" :class="{ active: laminationProcess === '__all__' }" @click="setLaminationProcess('__all__')">All</button>
        </div>
      </div>
      <div v-if="isPrinting105Table" class="cc-filter-item cc-shift-filter">
        <label>Printing process</label>
        <div class="cc-shift-btns">
          <button type="button" :class="{ active: printingProcess === '105' }" @click="setPrintingProcess('105')">105</button>
          <button type="button" :class="{ active: printingProcess === '106' }" @click="setPrintingProcess('106')">106</button>
          <button type="button" :class="{ active: printingProcess === '__all__' }" @click="setPrintingProcess('__all__')">All</button>
        </div>
      </div>
      <div class="cc-filter-item">
        <label>Order Code</label>
        <input type="text" v-model="filterPartyCode" placeholder="Search..." @input="debouncedFetch" />
      </div>
      <div class="cc-filter-item">
        <label>Customer</label>
        <input type="text" v-model="filterCustomer" placeholder="Search..." @input="debouncedFetch" />
      </div>
      <div v-if="isPrinting105Table" class="cc-filter-item">
        <label>Unit</label>
        <select v-model="filterUnit" class="cc-select-scope">
          <option value="">All Units</option>
          <option v-for="u in PRINTING_FILTER_UNITS" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>
      <div class="cc-filter-actions">
        <button type="button" class="cc-maint-btn" @click="openMachineOffDialog">{{ isPrinting105Table ? "Printing Machine Off" : "Machine Off" }}</button>
        <TransferToolbarBlock :board-kind="transferBoardKind" :filter-context="transferFilterContext" @submitted="fetchData" />
        <DespatchToolbarBlock :board-kind="transferBoardKind" :filter-context="transferFilterContext" @submitted="fetchData" />
        <button type="button" class="cc-clear-btn" @click="syncSprWeightToTable">Sync SPR Data</button>
        <button type="button" class="cc-clear-btn" @click="toggleArrangementLock">{{ arrangementLocked ? "Unlock Arrangment" : "Lock Arrangment" }}</button>
        <button type="button" class="cc-clear-btn" @click="saveLaminationArrangement">Save Arrangment</button>
        <button type="button" class="cc-clear-btn" @click="restoreLaminationArrangement">Restore Arrangment</button>
        <button type="button" class="cc-clear-btn" @click="openAssignShiftDialog">Assign Shift</button>
        <button
          v-if="!isPrintedBoppTable"
          type="button"
          class="cc-clear-btn"
          :title="sizeDimUnit === 'inches' ? 'Show width in millimetres (nearest 5 mm)' : 'Show width in inches'"
          @click="toggleSizeDimUnit"
        >{{ sizeDimUnit === "inches" ? "Width: mm" : "Width: in" }}</button>
        <button type="button" class="cc-clear-btn" @click="fetchData">Refresh</button>
        <button type="button" class="cc-view-btn" @click="goToBoard">{{ backToBoardLabel }}</button>
      </div>
    </div>

    <div class="cc-shift-board" v-if="showShiftPlanner">
      <div class="cc-shift-board-head">
        <div class="cc-shift-board-title">Shift Planner (drag between Day/Night)</div>
        <div class="cc-shift-board-date">
          <label>Shift Date</label>
          <input type="date" v-model="moveTargetDate" />
        </div>
      </div>
      <div class="cc-shift-lanes">
        <div class="cc-shift-lane" :class="{ over: dragOverShift === 'DAY' }" @dragover.prevent @dragenter.prevent="dragOverShift = 'DAY'" @dragleave="dragOverShift = ''" @drop.prevent="handleShiftDrop('DAY')">
          <div class="cc-shift-lane-title">DAY</div>
          <div v-for="row in scheduleRowsByShift('DAY')" :key="`${row.itemName}-day`" class="cc-shift-card" draggable="true" @dragstart="onRowDragStart(row)" @dragend="onRowDragEnd">
            <div class="cc-shift-card-code">{{ row.partyCode || row.order_code || row.lamination_booking_id || row.itemCode }}</div>
            <div class="cc-shift-card-meta">{{ row.customer_name || row.customer }}</div>
          </div>
        </div>
        <div class="cc-shift-lane" :class="{ over: dragOverShift === 'NIGHT' }" @dragover.prevent @dragenter.prevent="dragOverShift = 'NIGHT'" @dragleave="dragOverShift = ''" @drop.prevent="handleShiftDrop('NIGHT')">
          <div class="cc-shift-lane-title">NIGHT</div>
          <div v-for="row in scheduleRowsByShift('NIGHT')" :key="`${row.itemName}-night`" class="cc-shift-card" draggable="true" @dragstart="onRowDragStart(row)" @dragend="onRowDragEnd">
            <div class="cc-shift-card-code">{{ row.partyCode || row.order_code || row.lamination_booking_id || row.itemCode }}</div>
            <div class="cc-shift-card-meta">{{ row.customer_name || row.customer }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="cc-table-container">
      <div class="cc-table-unit-header lot-header">
        {{ tableUnitHeader }}
      </div>
      <div class="cc-order-table-scroll">
      <table class="cc-prod-table lot-table">
        <thead>
          <tr>
            <th class="th-n">S.NO</th>
            <th style="min-width:84px;">ARRANGMENT</th>
            <th>DATE</th>
            <th>SHIFT</th>
            <th>ORDER CODE</th>
            <th>CUSTOMER</th>
            <th v-if="showProcessColumn">PROCESS</th>
            <th v-if="!isPrintedBoppTable">QUALITY</th>
            <th v-if="!isPrintedBoppTable">{{ widthColumnHeader }}</th>
            <th v-if="!isPrintedBoppTable">FABRIC COLOUR</th>
            <th v-if="showPrintingLamGsmColumn">LAM GSM</th>
            <th v-if="isPrinting105Table">DESIGN CODE</th>
            <th v-if="showDesignNameColumn">DESIGN NAME</th>
            <th v-if="showDesignAttachmentColumn">ATTACHMENT</th>
            <th v-if="isPrinting105Table">OPERATOR</th>
            <th v-if="isPrinting105Table">FABRIC INPUT (KGS)</th>
            <th v-if="isPrinting105Table">PLANNED WT (KGS)</th>
            <th v-if="isPrinting105Table">ACHIEVED WT (KGS)</th>
            <th v-if="isPrinting105Table">PLANNED MTRS</th>
            <th v-if="isPrinting105Table">ACHIEVED MTRS</th>
            <th v-if="isPrinting105Table">PRODUCED ROLLS</th>
            <th v-if="showCylinderTypeColumn">CYLINDER TYPE</th>
            <th v-if="isPrintedBoppTable">FINISHING</th>
            <th v-if="isPrintedBoppTable">BOPP FINISH SIZE (MM)</th>
            <th v-if="isPrintedBoppTable">DESIGN COLOUR</th>
            <th v-if="isPrintedBoppTable">NO OF DESIGN COLOURS</th>
            <th v-if="isPrintedBoppTable">WHITE TINT</th>
            <th v-if="isPrintedBoppTable">TOTAL NO OF COLOURS</th>
            <th v-if="isPrintedBoppTable">PLANNED LENGTH (MTRS)</th>
            <th v-if="isPrintedBoppTable">ACHIEVED LENGTH (MTRS)</th>
            <th v-if="isPrintedBoppTable">BOPP BOM KGS</th>
            <th v-if="!isPrintedBoppTable && !isPrinting105Table">FABRIC GSM</th>
            <th v-if="showBoppGsmColumn">BOPP GSM</th>
            <th v-if="!isPrintedBoppTable && !isPrinting105Table">LAM GSM</th>
            <th v-if="!isPrintedBoppTable && !isPrinting105Table">FABRIC READY DATE</th>
            <th v-if="!isPrintedBoppTable && !isPrinting105Table">PRODUCED FABRIC WT (KGS)</th>
            <th v-if="!isPrinting105Table">{{ producedWeightHeader }}</th>
            <th v-if="!isPrintedBoppTable && !isPrinting105Table">PLANNED LENGTH (MTRS)</th>
            <th v-if="!isPrintedBoppTable && !isPrinting105Table">ACHIEVED LENGTH (MTRS)</th>
            <th style="min-width:100px;">MOVEMENT</th>
            <th style="min-width:90px;">PRODUCTION PLAN</th>
            <th style="min-width:128px;">SPR / WO</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(row, idx) in displayRows" :key="row.dateKey + (row.is_maintenance_row ? '-maint' : (row.is_maintenance_empty ? '-empty' : ('-item-' + (row.itemName || idx))))">
            <tr v-if="row.is_maintenance_row" class="pt-non-draggable" style="background-color: #fee2e2; border: 2px solid #dc2626;">
              <td :colspan="tableColCount" style="padding: 8px 12px; font-weight: 700; color: #991b1b; text-align: center;">
                <div style="display: inline-flex; align-items: center; justify-content: center; gap: 10px; flex-wrap: wrap;">
                  <span>?? MAINTENANCE: {{ row.record.maintenance_type }} ({{ row.record.start_date }} - {{ row.record.end_date }})</span>
                  <button @click="deleteMaintenanceRecord(row.record.name)" style="background: #dc2626; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 11px;">Remove</button>
                </div>
              </td>
            </tr>
            <tr v-else-if="row.is_maintenance_empty">
              <td class="cell-center">-</td>
              <td class="cell-center">
                <span v-if="!arrangementUnlocked" class="cc-lock-hint">Locked</span>
              </td>
              <td class="cell-center font-bold">{{ formatDate(row.dateKey) }}</td>
              <td :colspan="maintenanceEmptyColspan" style="text-align:center; color:#94a3b8; font-style:italic;">{{ emptyMaintenanceDayLabel }}</td>
            </tr>
            <tr v-else
            :draggable="arrangementUnlocked"
            @dragstart="onOrderDragStart(row, $event)"
            @dragover.prevent="onOrderDragOver(row)"
            @dragleave="onOrderDragLeave(row)"
            @drop.prevent="onOrderDrop(row)"
            @dragend="onOrderDragEnd"
            :class="{ 'cc-row-draggable': arrangementUnlocked, 'cc-row-drag-over': dragOverItemName === row.itemName }"
          >
            <td v-if="row.isFirstOfDate !== false" :rowspan="row.dateRowspan || 1" class="cell-center">{{ row._sno || (idx + 1) }}</td>
            <td class="cell-center">
              <span v-if="arrangementUnlocked" class="cc-drag-handle" title="Drag to reorder inside same date">Drag</span>
              <span v-else class="cc-lock-hint" title="Unlock arrangement to reorder">Locked</span>
            </td>
            <td v-if="row.isFirstOfDate !== false" :rowspan="row.dateRowspan || 1" class="cell-center">
              {{ formatDate(row.plannedDate || row.planned_date) }}
              <span v-if="maintenanceTypeForDate(row.plannedDate || row.planned_date, row.unit)" class="cc-maint-chip">
                OFF: {{ maintenanceTypeForDate(row.plannedDate || row.planned_date, row.unit) }}
              </span>
            </td>
            <td class="cell-center">{{ row.shift_label || "DAY" }}</td>
            <td class="cell-center font-mono font-bold" style="font-size:11px;color:#047857;">{{ row.partyCode || row.order_code || "-" }}</td>
            <td>{{ row.customer_name || row.customer || row.partyCode }}</td>
            <td v-if="showProcessColumn" class="cell-center font-bold">{{ processLabel(row) }}</td>
            <td v-if="!isPrintedBoppTable" class="cell-center">{{ row.quality }}</td>
            <td v-if="!isPrintedBoppTable" class="cell-center">{{ formatWidthCell(row) }}</td>
            <td v-if="!isPrintedBoppTable" class="cell-center font-bold">{{ row.fabric_colour || row.color }}</td>
            <td v-if="showPrintingLamGsmColumn" class="cell-center font-bold">{{ row.lamination_gsm || row.custom_lam_gsm || "-" }}</td>
            <td v-if="isPrinting105Table" class="cell-center font-bold">{{ row.custom_design_code || row.design_code || "—" }}</td>
            <td v-if="showDesignNameColumn" class="cell-center font-bold">{{ displayDesignName(row) }}</td>
            <td v-if="showDesignAttachmentColumn" class="cell-center">
              <button
                type="button"
                class="cc-preview-btn"
                :disabled="!getDesignAttachmentUrl(row)"
                @click="openDesignPreview(row)"
                :title="getDesignAttachmentUrl(row) ? 'Preview design attachment' : 'No attachment'"
              >
                👁 Preview
              </button>
            </td>
            <td v-if="isPrinting105Table" class="cell-center font-bold">{{ row.operator_name || row.operator_code || "—" }}</td>
            <td v-if="isPrinting105Table" class="cell-right font-bold">{{ formatKg2(row.transferred_qty || 0) }}</td>
            <td v-if="isPrinting105Table" class="cell-right font-bold">{{ formatKg2(row.qty || 0) }}</td>
            <td v-if="isPrinting105Table" class="cell-right font-bold">{{ formatKg2(row.produced_qty || 0) }}</td>
            <td v-if="isPrinting105Table" class="cell-right font-bold">{{ formatNum(row.meter || 0) }}</td>
            <td v-if="isPrinting105Table" class="cell-right font-bold">{{ formatNum(row.achieved_meter || 0) }}</td>
            <td v-if="isPrinting105Table" class="cell-center font-bold">{{ row.produced_rolls ?? "—" }}</td>
            <td v-if="showCylinderTypeColumn" class="cell-center font-bold">{{ row.cylinder_type || "—" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-center">{{ row.finishing || "—" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-center font-bold">{{ row.bopp_finish_size_mm || "—" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-center font-bold">{{ row.design_colour || "—" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-center font-bold">{{ row.no_of_design_colours || "—" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-center">{{ row.white_tint || "—" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-center font-bold">{{ row.total_no_of_colours || row.no_of_design_colours || "—" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-right">{{ row.planned_meter ?? "-" }}</td>
            <td v-if="isPrintedBoppTable" class="cell-right">{{ formatNum(row.achieved_meter) }}</td>
            <td v-if="isPrintedBoppTable" class="cell-right">{{ formatKg2(row.bopp_bom_kgs) }}</td>
            <td v-if="!isPrintedBoppTable && !isPrinting105Table" class="cell-center">{{ row.fabric_gsm || "-" }}</td>
            <td v-if="showBoppGsmColumn" class="cell-center">{{ row.bopp_gsm || "-" }}</td>
            <td v-if="!isPrintedBoppTable && !isPrinting105Table" class="cell-center">{{ row.lamination_gsm ?? row.gsm }}</td>
            <td v-if="!isPrintedBoppTable && !isPrinting105Table" class="cell-center">{{ formatDate(row.fabric_ready_date) || "-" }}</td>
            <td v-if="!isPrintedBoppTable && !isPrinting105Table" class="cell-right" :title="`Fabric WO: ${formatKg2(row.child_wo_produced_kg)} produced / ${formatKg2(row.fabric_required_kg)} planned`">
              {{ formatKg2(row.child_wo_produced_kg) }} / {{ formatKg2(row.fabric_required_kg) }}
            </td>
            <td v-if="!isPrinting105Table" class="cell-right" :title="(!isPrintedBoppTable && !isPrinting105Table) ? `Lamination: produced / planned (${formatKg2(row.planned_lamination_weight_kgs)} kg)` : ''">
              <template v-if="isPrintedBoppTable">{{ formatKg2(row.actual_production_weight_kgs) }}</template>
              <template v-else>{{ formatKg2(row.actual_production_weight_kgs) }} / {{ formatKg2(row.planned_lamination_weight_kgs) }}</template>
            </td>
            <td v-if="!isPrintedBoppTable && !isPrinting105Table" class="cell-right">{{ row.planned_meter ?? "-" }}</td>
            <td v-if="!isPrintedBoppTable && !isPrinting105Table" class="cell-right">{{ formatNum(row.achieved_meter) }}</td>
            <td class="cell-center" style="font-size:11px;">{{ formatMovementCell(row) }}</td>
            <td class="cell-center">
              <template v-if="isPrinting105Table">
                <button v-if="row.pp_id && Number(row.pp_docstatus) === 1" type="button" @click="openProductionPlanView(row.planningSheet || row.plan_name, row.salesOrderItem, row.itemName, row.pp_id || '')" class="cc-pp-btn">PP View</button>
                <span v-else-if="row.pp_id" class="pt-wo-closed-hint" title="Submit Production Plan to open print/form view">PP Draft</span>
                <span v-else class="pt-no-pp-hint">No PP</span>
              </template>
              <template v-else>
                <button v-if="row.pp_id && Number(row.pp_docstatus) === 1" type="button" @click="openProductionPlanView(row.planningSheet, row.salesOrderItem, row.itemName, row.pp_id || '')" class="cc-pp-btn">{{ isPrinting105Table ? 'PP View' : 'View' }}</button>
                <span v-else-if="row.pp_id" class="pt-wo-closed-hint" title="Submit Production Plan to open print/form view">PP Draft</span>
                <span v-else class="pt-no-pp-hint">No PP</span>
              </template>
            </td>
            <td class="cell-center">
              <div class="pt-stock-cell">
                <template v-if="isPrinting105Table">
                  <div class="pt-pill-row">
                    <span class="pt-pill pt-pill-muted" :title="`Transferred ${formatKg2(row.transferred_qty || 0)} Kg`">Transferred: {{ formatKg2(row.transferred_qty || 0) }} Kg</span>
                    <span class="pt-pill pt-pill-wo" :title="`Produced ${formatKg2(row.produced_qty || 0)} Kg`">Produced: {{ formatKg2(row.produced_qty || 0) }} Kg</span>
                  </div>
                  <div v-if="row.transfer_details && row.transfer_details.length" class="pt-prod-status-line">
                    {{ row.transfer_status || 'pending' }} · {{ row.transfer_details.length }} transfer(s)
                  </div>
                  <div
                    v-if="row.linked_work_orders && row.linked_work_orders.length"
                    class="pt-prod-status-line pt-linked-wo-line"
                    :title="row.linked_work_orders.join(', ')"
                  >
                    WO:
                    <a
                      v-for="(wn, wi) in row.linked_work_orders"
                      :key="wn"
                      href="#"
                      class="pt-linked-wo-link"
                      @click.prevent="frappe.set_route('Form', 'Work Order', wn)"
                    >{{ wn }}<template v-if="wi < row.linked_work_orders.length - 1">, </template></a>
                  </div>
                  <button
                    v-if="canShowStockEntry(row)"
                    type="button"
                    @click="handleStockEntryAction(row)"
                    class="cc-pp-btn pt-btn-entry"
                    :title="getStockEntryTitle(row)"
                  >{{ getStockEntryLabel(row) }}</button>
                  <button
                    v-else-if="row.spr_name"
                    type="button"
                    @click="openItemSPR(row.spr_name, row)"
                    class="cc-pp-btn pt-btn-entry"
                    :class="Number(row.spr_docstatus) === 1 ? 'pt-spr-btn-submitted' : 'pt-spr-btn-draft'"
                    :title="itemSprPrimaryButtonTitle(row)"
                  >{{ itemSprPrimaryButtonLabel(row) }}</button>
                  <span v-else class="pt-wo-closed-hint">Transfer pending</span>
                </template>
                <template v-else>
                  <div v-if="row.pp_id" class="pt-pill-row">
                    <span v-if="row.spr_name" class="pt-pill" :class="sprPillClass(row)" :title="sprPillTitle(row)">{{ sprPillLabel(row) }}</span>
                    <span v-else class="pt-pill pt-pill-muted">SPR: -</span>
                    <span class="pt-pill pt-pill-wo" :class="woPillClassItem(row)" :title="woPillTitleItem(row)">{{ woPillLabelItem(row) }}</span>
                  </div>
                  <div v-if="itemProductionStatusLine(row)" class="pt-prod-status-line">{{ itemProductionStatusLine(row) }}</div>
                  <template v-if="row.is_lamination_parent && !row.parent_wo_terminal && Number(row.pp_docstatus) === 1 && row.child_wo_created">
                  <button
                    v-if="!row.parent_wo_name"
                    type="button"
                    @click="startParentWO(row)"
                    class="cc-pp-btn pt-btn-entry"
                    title="Create Work Order draft"
                  >Start WO</button>
                  <button
                    v-else-if="Number(row.parent_wo_docstatus || 0) === 0 && !row.parent_wo_warehouse_set"
                    type="button"
                    @click="openParentWO(row)"
                    class="cc-pp-btn pt-btn-entry"
                    title="Open WO and set source warehouse, then save"
                  >Open WO</button>
                  <button
                    v-else-if="Number(row.parent_wo_docstatus || 0) === 0 && row.parent_wo_warehouse_set"
                    type="button"
                    @click="startParentWO(row)"
                    class="cc-pp-btn pt-btn-entry"
                    title="Submit Work Order to start production"
                  >Start WO</button>
                  <button
                    v-else-if="Number(row.parent_wo_docstatus || 0) === 1"
                    type="button"
                    @click="openParentWO(row)"
                    class="cc-pp-btn pt-btn-entry"
                    :title="`Open WO: ${row.parent_wo_name} (${row.parent_wo_status || 'In Process'})`"
                  >Open WO</button>
                  <div v-if="row.is_lamination_parent && !row.parent_ready_for_wo" class="pt-wo-closed-hint" style="font-size:10px;margin-top:2px;">Complete child WO first</div>
                </template>
                  <div v-else-if="row.is_lamination_parent && !row.parent_wo_terminal && row.pp_id && Number(row.pp_docstatus) === 1 && !row.child_wo_created" class="pt-wo-closed-hint" style="font-size:10px;margin-top:2px;">Start fabric WO first</div>
                  <button
                    v-else-if="row.is_lamination_parent && !row.parent_wo_terminal && !row.pp_id"
                    type="button"
                    disabled
                    class="cc-pp-btn pt-btn-entry"
                    style="opacity:0.45;cursor:not-allowed;"
                    title="No Production Plan yet"
                  >Start WO</button>
                  <button
                    v-if="canShowStockEntry(row)"
                    type="button"
                    @click="handleStockEntryAction(row)"
                    class="cc-pp-btn pt-btn-entry"
                    :title="getStockEntryTitle(row)"
                  >{{ getStockEntryLabel(row) }}</button>
                  <button
                    v-else-if="row.spr_name"
                    type="button"
                    @click="openItemSPR(row.spr_name, row)"
                    class="cc-pp-btn pt-btn-entry"
                    :class="Number(row.spr_docstatus) === 1 && row.wo_terminal ? 'pt-spr-btn-done' : Number(row.spr_docstatus) === 1 ? 'pt-spr-btn-submitted' : 'pt-spr-btn-draft'"
                    :title="itemSprPrimaryButtonTitle(row)"
                  >{{ itemSprPrimaryButtonLabel(row) }}</button>
                  <span v-else-if="row.pp_id && Number(row.pp_docstatus) !== 1" class="pt-wo-closed-hint">PP Draft</span>
                  <span v-else-if="!row.is_lamination_parent && row.pp_id && row.wo_terminal" class="pt-wo-closed-hint">WO closed</span>
                  <span v-else-if="!row.is_lamination_parent && !row.pp_id" style="color:#999;font-size:10px;">No PP</span>
                </template>
              </div>
            </td>
          </tr>
          </template>
          <tr v-if="!displayRows.length">
            <td :colspan="tableColCount" class="cell-center" style="padding:24px;color:#64748b;">{{ emptyTableLabel }}</td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { formatSingleDimension } from "./planning_table_size_units.js";
import { mergeSprCsv, resolveSprNavigationTarget } from "./spr_csv_utils.js";
import TransferToolbarBlock from "./TransferToolbarBlock.vue";
import DespatchToolbarBlock from "./DespatchToolbarBlock.vue";
import { formatMovementCell } from "./movementDisplay.js";

const DIM_UNIT_LS_KEY = "pp_planning_table_dim_unit_lamination_printing";
const sizeDimUnit = ref("inches");
const widthColumnHeader = computed(() =>
  sizeDimUnit.value === "mm" ? "WIDTH (mm)" : "WIDTH (INCHES)"
);
function toggleSizeDimUnit() {
  sizeDimUnit.value = sizeDimUnit.value === "mm" ? "inches" : "mm";
  try {
    localStorage.setItem(DIM_UNIT_LS_KEY, sizeDimUnit.value);
  } catch (_) {}
}
function formatWidthCell(row) {
  if (!row || row.is_maintenance_row || row.is_maintenance_empty) return "-";
  const fb = row.itemCode || row.item_code || "";
  return formatSingleDimension(row, "width_inch", sizeDimUnit.value, fb);
}

const props = defineProps({
  /** `lamination` = 104/107 lamination table; `printed_bopp_film` = PB / VR BOPP printing unit; `printing_105` = process 105 board. */
  tableBoardKind: { type: String, default: "lamination" },
  /** Render context: `table` or `board` (used for title/back-route labels). */
  tableMode: { type: String, default: "table" },
});

const PRINTED_BOPP_FILM_UNIT = "VR - 1200MM BOPP PRINTING MACHINE";
const PRINTING_UNIT_2_COLOUR = "JVE - PRINTING MACHINE 2 COLOUR 1600MM";
const PRINTING_UNIT_4_COLOUR = "JVE - PRINTING MACHINE 4 COLOUR 1600MM";
const PRINTING_UNIT_TT = "TT - PRINTING MACHINE 4 COLOUR 1200MM";
const PRINTING_UNASSIGNED_UNIT = "UNASSIGNED PRINTING MACHINE";
/** Table + unit filter: real machines only (queue rows are hidden in table view). */
const PRINTING_REAL_MACHINE_UNITS = [PRINTING_UNIT_2_COLOUR, PRINTING_UNIT_4_COLOUR, PRINTING_UNIT_TT];
const PRINTING_FILTER_UNITS = PRINTING_REAL_MACHINE_UNITS;
const filterUnit = ref("");
/** Must match ``planning_doctypes.LAMINATION_UNIT`` */
const LAMINATION_UNIT = "TNSPL - LAMINATION UNIT";
const isPrinting105Table = computed(() => (props.tableBoardKind || "").trim() === "printing_105");
const isPrintedBoppTable = computed(() => (props.tableBoardKind || "").trim() === "printed_bopp_film");
const isBoardMode = computed(() => (props.tableMode || "table").trim().toLowerCase() === "board");
const pageTitle = computed(() => {
  if (isPrinting105Table.value) return isBoardMode.value ? "Printing Order Board" : "Printing Order Table";
  return isPrintedBoppTable.value ? "Printed BOPP Film Table" : "Lamination Order Table";
});
const tableMaintenanceUnit = computed(() => {
  if (isPrinting105Table.value) return filterUnit.value || PRINTING_UNIT_2_COLOUR;
  return isPrintedBoppTable.value ? PRINTED_BOPP_FILM_UNIT : LAMINATION_UNIT;
});
const tableUnitHeader = computed(() => {
  if (isPrinting105Table.value) {
    const proc = printingProcess.value === "__all__" ? "105 + 106" : printingProcess.value;
    return `${filterUnit.value || 'All Printing Units'} — Planned orders (Process ${proc})`;
  }
  if (isPrintedBoppTable.value) {
    return `${PRINTED_BOPP_FILM_UNIT} — Planned orders (Printed BOPP film)`;
  }
  if (showAllProcesses.value) {
    return `${LAMINATION_UNIT} - Planned orders (104 + 107) — All`;
  }
  return `${LAMINATION_UNIT} - Planned orders (${laminationProcess.value}) — ${laminationProcess.value === "107" ? "BOPP" : "Plain"}`;
});
const showAllProcesses = computed(() => !isPrintedBoppTable.value && !isPrinting105Table.value && laminationProcess.value === "__all__");
const showPrintingAllProcesses = computed(() => isPrinting105Table.value && printingProcess.value === "__all__");
const showProcessColumn = computed(() => showAllProcesses.value || showPrintingAllProcesses.value);
const showPrintingLamGsmColumn = computed(() => isPrinting105Table.value && (printingProcess.value === "106" || printingProcess.value === "__all__"));
const showDesignNameColumn = computed(
  () => isPrinting105Table.value || isPrintedBoppTable.value || laminationProcess.value === "107" || showAllProcesses.value
);
const showDesignAttachmentColumn = computed(
  () => isPrinting105Table.value || isPrintedBoppTable.value
);
const showCylinderTypeColumn = computed(() => isPrintedBoppTable.value);
const showBoppGsmColumn = computed(
  () => !isPrintedBoppTable.value && !isPrinting105Table.value && (laminationProcess.value === "107" || showAllProcesses.value)
);
const producedWeightHeader = computed(() =>
  isPrinting105Table.value ? "PRODUCED PRINTING WEIGHT (KGS)" : isPrintedBoppTable.value ? "PRODUCED BOPP WEIGHT (KGS)" : "PRODUCED LAMINATION WEIGHT (KGS)"
);
const backToBoardLabel = computed(() =>
  isPrinting105Table.value
    ? (isBoardMode.value ? "Back to Printing Table" : "Back to Printing Board")
    : isPrintedBoppTable.value
    ? "Back to Printed BOPP Film Board"
    : "Back to Lamination Board"
);
const emptyMaintenanceDayLabel = computed(() =>
  isPrinting105Table.value ? "No printing orders (maintenance day)" : isPrintedBoppTable.value ? "No printed BOPP film orders (maintenance day)" : "No lamination orders (maintenance day)"
);
const emptyTableLabel = computed(() =>
  isPrinting105Table.value ? "No printing orders for this view." : isPrintedBoppTable.value ? "No printed BOPP film orders for this view." : "No lamination orders for this view."
);
const assignShiftMethod = computed(() =>
  isPrinting105Table.value
    ? "production_entry.production_planning.scheduler_api.assign_printing_shift"
    : isPrintedBoppTable.value
    ? "production_entry.production_planning.scheduler_api.assign_printed_bopp_film_shift"
    : "production_entry.production_planning.scheduler_api.assign_lamination_shift"
);
const addMachineOffMethod = computed(() =>
  isPrinting105Table.value
    ? "production_entry.production_planning.scheduler_api.add_printing_machine_off"
    : isPrintedBoppTable.value
    ? "production_entry.production_planning.scheduler_api.add_printed_bopp_film_machine_off"
    : "production_entry.production_planning.scheduler_api.add_lamination_machine_off"
);

const filterOrderDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref("");
const viewScope = ref("daily");
const filterPartyCode = ref("");
const filterCustomer = ref("");
/** Plain lamination (104) vs BOPP (107) vs All; drives API filter and column layout. */
const laminationProcess = ref("104");
/** Printing parent process filter: 105, 106, or All. */
const printingProcess = ref("105");
/** Client-side filter: server rows use shift_label DAY/NIGHT when available */
const filterShift = ref("all");
const rawData = ref([]);
const filtersReady = ref(false);
const maintenanceByDate = ref({});
const maintenanceRecords = ref([]);
const moveTargetDate = ref(frappe.datetime.get_today());
const dragRow = ref(null);
const dragOverShift = ref("");
const laminationSequenceStore = ref({});
const pendingArrangementUpdates = ref({});
const arrangementDirty = ref(false);
const arrangementSaving = ref(false);
const arrangementLocked = ref(true);
const dragOrderRow = ref(null);
const dragOverItemName = ref("");
let fetchTimer = null;
let initialFetchRetried = false;
let autoRefreshTimer = null;
let fetchInProgress = false;
let fetchQueued = false;
let visibilityRefreshTimer = null;
let sprRealtimeHandlerRegistered = false;
const showShiftPlanner = computed(() => viewScope.value !== "monthly");
const arrangementUnlocked = computed(() => !arrangementLocked.value);

function getErrorText(err, fallback = "Request failed") {
  try {
    const serverMsgs = err?._server_messages;
    if (typeof serverMsgs === "string" && serverMsgs) {
      const parsed = JSON.parse(serverMsgs);
      if (Array.isArray(parsed) && parsed.length) {
        const first = parsed[0];
        if (typeof first === "string") return first;
        if (first?.message) return first.message;
      }
    }
  } catch (_) {}

  if (typeof err === "string" && err.trim()) return err;
  if (typeof err?.message === "string" && err.message.trim()) return err.message;
  if (typeof err?.exception === "string" && err.exception.trim()) return err.exception;
  if (typeof err?.exc === "string" && err.exc.trim()) return err.exc;
  return fallback;
}

const filteredRows = computed(() => {
  let d = rawData.value || [];
  const pc = (filterPartyCode.value || "").trim().toLowerCase();
  const cu = (filterCustomer.value || "").trim().toLowerCase();

  if (isPrinting105Table.value) {
    d = d.filter((r) => !isPrintingQueueUnit(r));
    if (filterUnit.value) {
      d = d.filter((r) => normalizeUnitValue(r.unit) === filterUnit.value);
    }
  }

  if (pc) {
    d = d.filter((r) => String(r.partyCode || "").toLowerCase().includes(pc));
  }
  if (cu) {
    d = d.filter((r) => String(r.customer_name || r.customer || "").toLowerCase().includes(cu));
  }
  const sh = (filterShift.value || "all").toLowerCase();
  if (sh === "day") {
    d = d.filter((r) => String(r.shift_label || "DAY").toUpperCase() === "DAY");
  } else if (sh === "night") {
    d = d.filter((r) => String(r.shift_label || "").toUpperCase() === "NIGHT");
  }
  return sortRowsBySavedSequence(d);
});

const transferBoardKind = computed(() => {
  if (isPrintedBoppTable.value) return "printed_bopp_film";
  if (isPrinting105Table.value) return "printing_105";
  return "lamination";
});
const transferFilterContext = computed(() => ({
  view_scope: viewScope.value,
  date: filterOrderDate.value,
  week: filterWeek.value,
  month: filterMonth.value,
  unit: filterUnit.value || "",
  party_code: filterPartyCode.value,
  customer: filterCustomer.value,
}));

const tableColCount = computed(() => {
  if (isPrinting105Table.value) {
    let n = 23;
    if (showPrintingAllProcesses.value) n += 1;
    if (showPrintingLamGsmColumn.value) n += 1;
    return n;
  }
  if (isPrintedBoppTable.value) {
    return 21;
  }
  let n = 19;
  if (showAllProcesses.value) n += 1;
  if (showDesignNameColumn.value) n += 1;
  if (showCylinderTypeColumn.value) n += 1;
  if (showBoppGsmColumn.value) n += 1;
  return n;
});
const maintenanceEmptyColspan = computed(() => Math.max(1, tableColCount.value - 3));

function normalizeUnitValue(unit) {
  return String(unit || "").trim();
}

/** Printing “queue” pseudo-machine — shown on board, omitted from order table + filters. */
function isPrintingQueueUnit(row) {
  if (!isPrinting105Table.value) return false;
  const u = normalizeUnitValue(row?.unit);
  if (!u) return false;
  return u.toUpperCase() === PRINTING_UNASSIGNED_UNIT.toUpperCase();
}

function rowMatchesPrintingUnit(row) {
  if (!isPrinting105Table.value) return true;
  if (isPrintingQueueUnit(row)) return false;
  if (!filterUnit.value) return true;
  return normalizeUnitValue(row?.unit) === filterUnit.value;
}

function setLaminationProcess(v) {
  if (isPrinting105Table.value) return;
  const next = v === "107" ? "107" : v === "__all__" ? "__all__" : "104";
  if (laminationProcess.value === next) return;
  laminationProcess.value = next;
  updateUrlParams();
  fetchData();
}

function setPrintingProcess(v) {
  if (!isPrinting105Table.value) return;
  const next = v === "106" ? "106" : v === "__all__" ? "__all__" : "105";
  if (printingProcess.value === next) return;
  printingProcess.value = next;
  updateUrlParams();
  fetchData();
}

const displayRows = computed(() => {
  const normalRows = filteredRows.value || [];
  const { start_date, end_date } = getScopeDateRange();
  if (!start_date || !end_date) {
    normalRows.forEach((r, i) => { r._sno = i + 1; });
    return normalRows;
  }
  
  const start = new Date(start_date);
  const end = new Date(end_date);
  const out = [];
  
  let sno = 1;
  const datesHandled = new Set();
  const renderedMaintRecords = new Set();
  
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const k = toDateKey(d);
    datesHandled.add(k);
    
    const recs = (maintenanceRecords.value || []).filter(r => {
      const rStart = new Date(r.start_date);
      const rEnd = new Date(r.end_date);
      return d >= rStart && d <= rEnd;
    });
    
    let hasMaintToday = false;
    if (recs && recs.length > 0) {
      hasMaintToday = true;
      for (const rec of recs) {
        if (!renderedMaintRecords.has(rec.name)) {
          out.push({
            is_maintenance_row: true,
            dateKey: k,
            record: rec
          });
          renderedMaintRecords.add(rec.name);
        }
      }
    }
    
    const dateRows = normalRows.filter(r => getRowDateKey(r) === k);
    for (let i = 0; i < dateRows.length; i++) {
      const r = dateRows[i];
      r._sno = sno;
      r.isFirstOfDate = (i === 0);
      r.dateRowspan = dateRows.length;
      out.push(r);
    }
    if (dateRows.length > 0) sno++;
    
    if (hasMaintToday && dateRows.length === 0) {
      out.push({
        is_maintenance_empty: true,
        dateKey: k
      });
    }
  }
  
  const unhandled = normalRows.filter(r => !datesHandled.has(getRowDateKey(r)));
  for (const r of unhandled) {
    r._sno = sno++;
    r.isFirstOfDate = true;
    r.dateRowspan = 1;
    out.push(r);
  }
  
  return out;
});

async function deleteMaintenanceRecord(recordName) {
  if (!confirm("Remove this maintenance record?")) return;
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.delete_maintenance_and_cascade",
      args: { maintenance_record_name: recordName },
    });
    if (res.message && res.message.status === "success") {
      frappe.show_alert({ message: res.message.message, indicator: "green" });
      await fetchMaintenanceRecords();
      if (typeof fetchData === "function") await fetchData();
    } else if (res.message && res.message.status === "error") {
      frappe.msgprint(res.message.message || "Error deleting maintenance record");
    }
  } catch (e) {
    frappe.msgprint("Error deleting maintenance record");
    console.error(e);
  }
}

function getRowDateKey(row) {
  return toDateKey(row?.plannedDate || row?.planned_date);
}

function sortRowsBySavedSequence(rows) {
  const groups = {};
  (rows || []).forEach((row) => {
    const k = getRowDateKey(row) || "no-date";
    if (!groups[k]) groups[k] = [];
    groups[k].push(row);
  });
  const out = [];
  Object.keys(groups)
    .sort()
    .forEach((dateKey) => {
      const seq = laminationSequenceStore.value[dateKey] || [];
      const map = {};
      seq.forEach((name, idx) => {
        map[String(name || "").trim()] = idx;
      });
      const sorted = groups[dateKey].slice().sort((a, b) => {
        const aKey = String(a.itemName || "").trim();
        const bKey = String(b.itemName || "").trim();
        const ai = map[aKey] !== undefined ? map[aKey] : null;
        const bi = map[bKey] !== undefined ? map[bKey] : null;
        if (ai !== null && bi !== null && ai !== bi) return ai - bi;
        if (ai !== null && bi === null) return -1;
        if (ai === null && bi !== null) return 1;
        if (isPrinting105Table.value) {
          const as = Number(a.custom_printing_arrangement_seq || 0) || 999999;
          const bs = Number(b.custom_printing_arrangement_seq || 0) || 999999;
          if (as !== bs) return as - bs;
        }
        const qa = String(a.quality || "").toLowerCase();
        const qb = String(b.quality || "").toLowerCase();
        if (qa !== qb) return qa.localeCompare(qb);
        return Number(a.idx || 0) - Number(b.idx || 0);
      });
      out.push(...sorted);
    });
  return out;
}

function debouncedFetch() {
  if (fetchTimer) clearTimeout(fetchTimer);
  fetchTimer = setTimeout(() => fetchData(), 80);
}

function onVisibilityRefresh() {
  if (document.visibilityState !== "visible") return;
  if (visibilityRefreshTimer) clearTimeout(visibilityRefreshTimer);
  visibilityRefreshTimer = setTimeout(() => {
    visibilityRefreshTimer = null;
    fetchData();
  }, 400);
}

function handleSprRealtimeUpdate() {
  debouncedFetch();
}

function formatDate(d) {
  if (!d) return "-";
  try {
    if (frappe.datetime && frappe.datetime.format_date) {
      return frappe.datetime.format_date(d);
    }
  } catch (e) {}
  return d;
}

function toDateKey(d) {
  if (!d) return "";
  const s = String(d).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const dt = new Date(s);
  if (Number.isNaN(dt.getTime())) return "";
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const day = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function getScopeDateRange() {
  if (viewScope.value === "monthly" && filterMonth.value) {
    const [year, month] = filterMonth.value.split("-");
    const lastDay = new Date(year, month, 0).getDate();
    return { start_date: `${filterMonth.value}-01`, end_date: `${filterMonth.value}-${lastDay}` };
  }
  if (viewScope.value === "weekly" && filterWeek.value) {
    const [yearStr, weekStr] = filterWeek.value.split("-W");
    const y = parseInt(yearStr, 10);
    const w = parseInt(weekStr, 10);
    const simple = new Date(y, 0, 1 + (w - 1) * 7);
    const dow = simple.getDay();
    const weekStart = new Date(simple);
    if (dow <= 4) weekStart.setDate(simple.getDate() - simple.getDay() + 1);
    else weekStart.setDate(simple.getDate() + 8 - simple.getDay());
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const fmt = (d) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { start_date: fmt(weekStart), end_date: fmt(weekEnd) };
  }
  const day = filterOrderDate.value || frappe.datetime.get_today();
  return { start_date: day, end_date: day };
}

async function fetchMaintenanceRecords() {
  try {
    const { start_date, end_date } = getScopeDateRange();
    const res = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.get_all_equipment_maintenance",
      args: { start_date, end_date },
    });
    const allRows = res?.message || [];
    const rows = isPrinting105Table.value
      ? allRows.filter((r) => {
          const u = normalizeUnitValue(r.unit);
          return filterUnit.value ? u === filterUnit.value : PRINTING_FILTER_UNITS.includes(u);
        })
      : allRows.filter((r) => normalizeUnitValue(r.unit) === tableMaintenanceUnit.value);
    maintenanceRecords.value = rows;
    const mapped = {};
    rows.forEach((rec) => {
      const start = new Date(rec.start_date);
      const end = new Date(rec.end_date);
      for (let cur = new Date(start); cur <= end; cur.setDate(cur.getDate() + 1)) {
        const key = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, "0")}-${String(cur.getDate()).padStart(2, "0")}`;
        if (!mapped[key]) mapped[key] = [];
        mapped[key].push({
          unit: normalizeUnitValue(rec.unit),
          type: rec.maintenance_type || "Machine Off",
        });
      }
    });
    maintenanceByDate.value = mapped;
  } catch (e) {
    console.error("Failed to load lamination maintenance", e);
    maintenanceByDate.value = {};
  }
}

function maintenanceTypeForDate(dateValue, unitValue = "") {
  const k = toDateKey(dateValue);
  const recs = k ? (maintenanceByDate.value[k] || []) : [];
  if (!Array.isArray(recs) || recs.length === 0) return "";
  if (isPrinting105Table.value) {
    const targetUnit = normalizeUnitValue(unitValue) || filterUnit.value;
    if (targetUnit) {
      const hit = recs.find((r) => r.unit === targetUnit);
      return hit ? hit.type : "";
    }
    return recs.map((r) => `${r.unit}: ${r.type}`).join(", ");
  }
  return recs[0]?.type || "";
}

function scheduleRowsByShift(shift) {
  const dateKey =
    viewScope.value === "daily" && filterOrderDate.value
      ? toDateKey(filterOrderDate.value)
      : toDateKey(moveTargetDate.value);
  if (!dateKey) return [];
  const rows = (rawData.value || []).filter((r) => {
    const rk = toDateKey(r.plannedDate || r.planned_date);
    const sh = String(r.shift_label || "DAY").toUpperCase();
    const pc = (filterPartyCode.value || "").trim().toLowerCase();
    const cu = (filterCustomer.value || "").trim().toLowerCase();
    if (rk !== dateKey || sh !== String(shift || "").toUpperCase()) return false;
    if (!rowMatchesPrintingUnit(r)) return false;
    if (pc && !String(r.partyCode || "").toLowerCase().includes(pc)) return false;
    if (cu && !String(r.customer_name || r.customer || "").toLowerCase().includes(cu)) return false;
    return true;
  });
  return isPrinting105Table.value ? sortRowsBySavedSequence(rows) : rows;
}

function seedPrintingArrangementStoreFromRows() {
  const pending = pendingArrangementUpdates.value || {};
  const nextStore = { ...laminationSequenceStore.value };
  const byDate = {};
  (rawData.value || []).forEach((r) => {
    if (isPrintingQueueUnit(r)) return;
    if (filterUnit.value && normalizeUnitValue(r.unit) !== filterUnit.value) return;
    const dk = getRowDateKey(r);
    if (!dk) return;
    if (!byDate[dk]) byDate[dk] = [];
    byDate[dk].push(r);
  });
  Object.keys(byDate).forEach((dk) => {
    const pend = pending[dk];
    if (arrangementDirty.value && Array.isArray(pend) && pend.length) {
      nextStore[dk] = pend.map((x) => String(x || "").trim()).filter(Boolean);
      return;
    }
    byDate[dk].sort((a, b) => {
      const as = Number(a.custom_printing_arrangement_seq || 0) || 999999;
      const bs = Number(b.custom_printing_arrangement_seq || 0) || 999999;
      if (as !== bs) return as - bs;
      return Number(a.idx || 0) - Number(b.idx || 0);
    });
    nextStore[dk] = byDate[dk].map((r) => String(r.itemName || "").trim()).filter(Boolean);
  });
  laminationSequenceStore.value = nextStore;
}

async function fetchLaminationSequences() {
  if (isPrinting105Table.value) {
    seedPrintingArrangementStoreFromRows();
    return;
  }
  try {
    const { start_date, end_date } = getScopeDateRange();
    const res = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.get_color_sequences_range",
      args: {
        start_date,
        end_date,
        unit: tableMaintenanceUnit.value,
        plan_name: "Default",
      },
    });
    const store = {};
    const payload = res?.message || {};
    if (Array.isArray(payload)) {
      payload.forEach((rec) => {
        const d = toDateKey(rec?.date);
        if (!d) return;
        let seq = rec?.sequence_data || rec?.sequence || [];
        if (typeof seq === "string") {
          try {
            seq = JSON.parse(seq);
          } catch (e) {
            seq = [];
          }
        }
        if (Array.isArray(seq) && seq.length) {
          store[d] = seq.map((x) => String(x || "").trim()).filter(Boolean);
        }
      });
    } else if (payload && typeof payload === "object") {
      Object.entries(payload).forEach(([key, rec]) => {
        const parts = String(key || "").split("-");
        const d = parts.length >= 4 ? parts.slice(-3).join("-") : toDateKey(rec?.date);
        if (!d) return;
        let seq = rec?.sequence_data || rec?.sequence || [];
        if (typeof seq === "string") {
          try {
            seq = JSON.parse(seq);
          } catch (e) {
            seq = [];
          }
        }
        if (Array.isArray(seq) && seq.length) {
          store[d] = seq.map((x) => String(x || "").trim()).filter(Boolean);
        }
      });
    }
    laminationSequenceStore.value = store;
  } catch (e) {
    console.error("Failed to fetch lamination sequence", e);
    laminationSequenceStore.value = {};
  }
}

function toggleArrangementLock() {
  arrangementLocked.value = !arrangementLocked.value;
  frappe.show_alert(
    { message: arrangementLocked.value ? "Arrangement locked" : "Arrangement unlocked. Drag rows to reorder.", indicator: "blue" },
    2
  );
}

function reorderRowsInDate(sourceRow, targetRow) {
  const sourceDate = getRowDateKey(sourceRow);
  const targetDate = getRowDateKey(targetRow);
  if (!sourceDate || !targetDate || sourceDate !== targetDate) {
    frappe.show_alert({ message: "Reorder allowed only inside same date", indicator: "orange" }, 3);
    return;
  }
  const dayRows = filteredRows.value.filter((r) => getRowDateKey(r) === sourceDate);
  const seq = dayRows.map((r) => String(r.itemName || "").trim()).filter(Boolean);
  const sourceName = String(sourceRow?.itemName || "").trim();
  const targetName = String(targetRow?.itemName || "").trim();
  const fromIdx = seq.indexOf(sourceName);
  const toIdx = seq.indexOf(targetName);
  if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return;
  const [mv] = seq.splice(fromIdx, 1);
  seq.splice(toIdx, 0, mv);
  laminationSequenceStore.value = { ...laminationSequenceStore.value, [sourceDate]: seq };
  pendingArrangementUpdates.value[sourceDate] = seq;
  arrangementDirty.value = true;
}

function onOrderDragStart(row, ev) {
  if (!arrangementUnlocked.value) return;
  dragOrderRow.value = row;
  dragOverItemName.value = String(row?.itemName || "");
  try {
    if (ev?.dataTransfer) ev.dataTransfer.effectAllowed = "move";
  } catch (e) {}
}

function onOrderDragOver(row) {
  if (!arrangementUnlocked.value) return;
  dragOverItemName.value = String(row?.itemName || "");
}

function onOrderDragLeave(row) {
  if (dragOverItemName.value === String(row?.itemName || "")) {
    dragOverItemName.value = "";
  }
}

function onOrderDrop(row) {
  if (!arrangementUnlocked.value || !dragOrderRow.value) return;
  reorderRowsInDate(dragOrderRow.value, row);
  dragOrderRow.value = null;
  dragOverItemName.value = "";
}

function onOrderDragEnd() {
  dragOrderRow.value = null;
  dragOverItemName.value = "";
}

async function saveLaminationArrangement() {
  if (arrangementSaving.value) return;
  if (!arrangementDirty.value) {
    frappe.show_alert({ message: "No arrangement changes to save", indicator: "orange" }, 2);
    return;
  }
  arrangementSaving.value = true;
  try {
    for (const [dateKey, seq] of Object.entries(pendingArrangementUpdates.value || {})) {
      if (!Array.isArray(seq) || !seq.length) continue;
      if (isPrinting105Table.value) {
        await frappe.call({
          method: "production_entry.production_planning.scheduler_api.save_printing_arrangement",
          args: { date: dateKey, sequence_data: JSON.stringify(seq) },
        });
      } else {
        await frappe.call({
          method: "production_entry.production_planning.scheduler_api.save_color_sequence",
          args: {
            date: dateKey,
            unit: tableMaintenanceUnit.value,
            sequence_data: JSON.stringify(seq),
            plan_name: "Default",
          },
        });
      }
    }
    pendingArrangementUpdates.value = {};
    arrangementDirty.value = false;
    frappe.show_alert(
      {
        message: isPrinting105Table.value
          ? "Printing arrangement saved"
          : isPrintedBoppTable.value
          ? "Printed BOPP film arrangement saved"
          : "Lamination arrangement saved",
        indicator: "green",
      },
      3
    );
  } catch (e) {
    frappe.msgprint(`Failed to save arrangement: ${e?.message || e}`);
  } finally {
    arrangementSaving.value = false;
  }
}

async function restoreLaminationArrangement() {
  try {
    const { start_date, end_date } = getScopeDateRange();
    const start = new Date(start_date);
    const end = new Date(end_date);
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const dateKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      if (isPrinting105Table.value) {
        await frappe.call({
          method: "production_entry.production_planning.scheduler_api.restore_printing_arrangement",
          args: { date: dateKey },
        });
      } else {
        await frappe.call({
          method: "production_entry.production_planning.scheduler_api.restore_last_color_sequence",
          args: { date: dateKey, unit: tableMaintenanceUnit.value, plan_name: "Default" },
        });
      }
    }
    pendingArrangementUpdates.value = {};
    arrangementDirty.value = false;
    await fetchData();
    frappe.show_alert(
      {
        message: isPrinting105Table.value
          ? "Printing arrangement restored"
          : isPrintedBoppTable.value
          ? "Printed BOPP film arrangement restored"
          : "Lamination arrangement restored",
        indicator: "green",
      },
      3
    );
  } catch (e) {
    frappe.msgprint(`Failed to restore arrangement: ${e?.message || e}`);
  }
}

function formatKg2(value) {
  const num = parseFloat(value || 0);
  if (!Number.isFinite(num)) return "0.00";
  return num.toFixed(2);
}

function formatNum(v) {
  const n = parseFloat(v || 0);
  if (!Number.isFinite(n)) return "0";
  return n.toFixed(0);
}

function sprPillLabel(item) {
  if (!item?.spr_name) return "";
  if (item.spr_docstatus === 0 || item.spr_docstatus === "0") return "Draft";
  if (Number(item.spr_docstatus) === 1) return "Submitted";
  return "SPR";
}
function sprPillClass(item) {
  if (!item?.spr_name) return "pt-pill-muted";
  if (item.spr_docstatus === 0 || item.spr_docstatus === "0") return "pt-pill-draft";
  if (Number(item.spr_docstatus) === 1) return "pt-pill-submitted";
  return "pt-pill-muted";
}
function sprPillTitle(item) {
  if (!item?.spr_name) return "";
  const id = item.spr_name || "";
  if (item.spr_docstatus === 0 || item.spr_docstatus === "0") return `Draft SPR ${id}`;
  if (Number(item.spr_docstatus) === 1) return `Submitted SPR ${id}`;
  return id;
}
function woPillLabelItem(item) {
  if (!item) return "";
  if (item.wo_terminal) return "WO done";
  if (item.wo_open) return "WO open";
  return "WO";
}
function woPillClassItem(item) {
  if (item.wo_terminal) return "pt-pill-wo-done";
  if (item.wo_open) return "pt-pill-wo-open";
  return "pt-pill-wo-unknown";
}
function woPillTitleItem(item) {
  if (!item) return "";
  if (item.wo_terminal) return "All work orders closed or terminal.";
  if (item.wo_open) return "At least one WO open.";
  return "WO status";
}
function itemProductionStatusLine(item) {
  if (!item) return "";
  const t = parseFloat(item.qty) || 0;
  const a = parseFloat(item.actual_production_weight_kgs) || 0;
  const gap = t - a;
  if (Math.abs(gap) <= 0.5) return "";
  return gap > 0 ? `${formatKg2(gap)} kg below target` : `${formatKg2(-gap)} kg over target`;
}
function itemSprPrimaryButtonLabel(item) {
  if (!item?.spr_name) return "";
  if (item.spr_docstatus === 0 || item.spr_docstatus === "0") return "Open draft SPR";
  if (item.wo_terminal) return "View SPR (done)";
  return "View SPR";
}
function itemSprPrimaryButtonTitle(item) {
  if (!item?.spr_name) return "";
  if (item.spr_docstatus === 0 || item.spr_docstatus === "0") return "Draft SPR - continue recording rolls.";
  if (item.wo_terminal) return "WO terminal - review only.";
  return "Open submitted SPR.";
}

function canShowStockEntry(item) {
  if (!item) return false;
  if (isPrinting105Table.value) {
    if (item.spr_name) return true;
    return item.can_create_spr !== false;
  }
  if (!item.pp_id) return false;
  if (item.is_lamination_parent && !item.parent_wo_started) return false;
  if (item.is_lamination_parent && Number(item.parent_wo_docstatus || 0) !== 1) return false;
  if (!item.wo_open && !item.wo_terminal) return false;
  if (item.is_lamination_parent && !item.parent_ready_for_wo) return false;
  if (Number(item.pp_docstatus) !== 1) return false;
  const pendingQty = Number(item.pp_pending_qty ?? item.pending_qty ?? item.item_pending_qty ?? 0);
  if (!(pendingQty > 0)) return false;
  const targetKg = Number(item.qty ?? 0);
  const actualKg = Number(item.actual_production_weight_kgs ?? item.total_achieved_weight_kgs ?? 0);
  if (targetKg > 0 && actualKg >= targetKg - 1e-6) return false;
  if (item.wo_terminal) return false;
  return true;
}

function openParentWO(item) {
  const woName = String(item?.parent_wo_name || "").trim();
  if (!woName) return;
  frappe.set_route("Form", "Work Order", woName);
}

async function startParentWO(item) {
  if (!item?.itemName) return;
  try {
    const submitExisting = item.parent_wo_name && Number(item.parent_wo_docstatus || 0) === 0 && item.parent_wo_warehouse_set;
    const res = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.start_lamination_parent_wo",
      args: { item_name: item.itemName, submit_existing: submitExisting ? 1 : 0 },
    });
    const msg = res?.message || {};
    if (msg.status === "ok") {
      if (msg.draft && msg.wo_name && !submitExisting) {
        frappe.show_alert({ message: `WO draft created: ${msg.wo_name}. Set source warehouse then come back to Start WO.`, indicator: "blue" }, 6);
        frappe.set_route("Form", "Work Order", msg.wo_name);
      } else if (msg.started) {
        frappe.show_alert({ message: `WO started: ${msg.wo_name}`, indicator: "green" }, 4);
      } else if (msg.wo_name) {
        frappe.show_alert({ message: `WO: ${msg.wo_name}`, indicator: "green" }, 4);
      }
      await fetchData();
      return;
    }
    frappe.msgprint(msg.message || "Unable to start WO");
  } catch (e) {
    frappe.msgprint(`Failed to start WO: ${e?.message || e}`);
  }
}

function getDesignAttachmentUrl(item) {
  if (!item) return "";
  let url = String(
    item.custom_design_attachment ||
      item.design_attachment ||
      item.custom_design_image ||
      item.design_image ||
      ""
  ).trim();
  if (!url) return "";
  if (url.startsWith("/")) {
    const base = window.location.origin || "";
    url = base ? base + url : url;
  }
  return url;
}

function displayDesignName(row) {
  if (!row) return "—";
  const code = String(row.custom_design_code || row.design_code || "").trim();
  const name = String(row.custom_design_name || row.design_name || "").trim();
  if (!name) return isPrinting105Table.value ? "—" : (code || "—");
  if (isPrinting105Table.value && name === code) return "—";
  return name;
}

function openDesignPreview(item) {
  const url = getDesignAttachmentUrl(item);
  if (!url) {
    frappe.msgprint("No design attachment found");
    return;
  }
  window.open(url, "_blank");
}

function getStockEntryLabel(item) {
  if (!item) return "New SPR";
  const isDraftSpr = !!item.spr_name && (item.spr_docstatus === 0 || item.spr_docstatus === "0");
  if (isPrinting105Table.value) return isDraftSpr ? "Continue SPR" : "Create SPR";
  return isDraftSpr ? "Continue SPR" : "New SPR";
}

function getStockEntryTitle(item) {
  if (!item) return "Create Shaft Production Run";
  const isDraftSpr = !!item.spr_name && (item.spr_docstatus === 0 || item.spr_docstatus === "0");
  const pendingQty = Number(item.pending_qty || 0);
  if (isPrinting105Table.value) return isDraftSpr ? `Continue printing SPR. Pending: ${pendingQty.toFixed(0)} Kg` : `Create printing SPR. Pending: ${pendingQty.toFixed(0)} Kg`;
  if (isDraftSpr) return `Continue draft SPR. Pending: ${pendingQty.toFixed(0)} Kg`;
  return `New SPR. Pending: ${pendingQty.toFixed(0)} Kg`;
}

function getItemDisplayName(item) {
  if (!item) return "-";
  return item.description || item.itemCode || item.item_code || item.itemName || "-";
}

function syncSprNameForSamePP(ppId, sprId, sourceItemName = "") {
  const pid = String(ppId || "").trim();
  const sid = String(sprId || "").trim();
  if (!pid || !sid) return;
  (rawData.value || []).forEach((row) => {
    if (
      String(row.pp_id || "").trim() === pid &&
      (!sourceItemName || String(row.itemName || "") === String(sourceItemName || ""))
    ) {
      row.spr_name = mergeSprCsv(row.spr_name, sid);
    }
  });
}

async function openProductionPlanView(planningSheetName, salesOrderItem = null, planningSheetItem = null, directPpId = null) {
  if (!planningSheetName) {
    frappe.msgprint("Planning Sheet not found");
    return;
  }
  let ppId = String(directPpId || "").trim();
  const ppPrintFormat = isPrinting105Table.value || isPrintedBoppTable.value
    ? "bopp printing"
    : "Assembly Item - Raw Material";
  if (ppId) {
    const printUrl = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(ppId)}&format=${encodeURIComponent(ppPrintFormat)}&trigger_print=0`;
    window.open(printUrl, "_blank");
    return;
  }
  try {
    const res = await frappe.call({
      method: "production_entry.production_planning.scheduler_api.get_planning_sheet_pp_id",
      args: {
        planning_sheet_name: planningSheetName,
        sales_order_item: salesOrderItem,
        planning_sheet_item: planningSheetItem,
      },
    });
    if (res.message && res.message.status === "ok") {
      ppId = String(res.message.pp_id || "").trim();
      if (ppId) {
        const printUrl = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(ppId)}&format=${encodeURIComponent(ppPrintFormat)}&trigger_print=0`;
        window.open(printUrl, "_blank");
      } else {
        frappe.msgprint("No Production Plan found");
      }
    } else {
      frappe.msgprint(res.message?.message || "Error");
    }
  } catch (e) {
    frappe.msgprint("Error opening Production Plan");
  }
}

async function handleStockEntryAction(item) {
  if (!item) return;
  const isDraftSpr = !!item.spr_name && (item.spr_docstatus === 0 || item.spr_docstatus === "0");
  if (isDraftSpr) {
    await openItemSPR(item.spr_name, item);
    return;
  }
  createItemStockEntry(item);
}

async function openItemSPR(sprName, item = null) {
  if (!sprName) {
    frappe.msgprint("No SPR linked");
    return;
  }
  const target = await resolveSprNavigationTarget(sprName, item?.spr_docstatus);
  if (!target) {
    frappe.msgprint("No SPR linked");
    return;
  }
  try {
    const r = await frappe.call({
      method: "frappe.client.get",
      args: { doctype: "Shaft Production Run", name: target },
    });
    if (r.message) {
      frappe.set_route("Form", "Shaft Production Run", target);
    } else if (item) {
      try {
        await frappe.call({
          method: "production_entry.production_planning.scheduler_api.prune_planning_table_spr_links",
          args: { planning_table_names: JSON.stringify([item.itemName || ""]) },
        });
      } catch (e2) {}
      item.spr_name = "";
      frappe.show_alert({ message: "SPR was deleted.", indicator: "orange" }, 3);
      createItemStockEntry(item);
    } else {
      frappe.msgprint("SPR not found");
    }
  } catch (e) {
    if (item) {
      try {
        await frappe.call({
          method: "production_entry.production_planning.scheduler_api.prune_planning_table_spr_links",
          args: { planning_table_names: JSON.stringify([item.itemName || ""]) },
        });
      } catch (e2) {}
      item.spr_name = "";
      frappe.show_alert({ message: "SPR was deleted.", indicator: "orange" }, 3);
      createItemStockEntry(item);
    } else {
      frappe.msgprint("SPR not found");
    }
  }
}

async function createItemStockEntry(item) {
  if (item.__creating_spr) return;
  if (!item.pp_id && item.planningSheet) {
    try {
      const ppRes = await frappe.call({
        method: "production_entry.production_planning.scheduler_api.get_planning_sheet_pp_id",
        args: {
          planning_sheet_name: item.planningSheet,
          sales_order_item: item.salesOrderItem || null,
          planning_sheet_item: item.itemName || null,
        },
      });
      if (ppRes.message && ppRes.message.status === "ok" && ppRes.message.pp_id) {
        item.pp_id = ppRes.message.pp_id;
      }
    } catch (e) {}
  }
  if (!item.pp_id) {
    frappe.msgprint("No Production Plan linked");
    return;
  }
  if (!item.itemName) {
    frappe.msgprint("Planning row name missing");
    return;
  }
  const itemDisplay = getItemDisplayName(item);
  const isBoppMode = isPrintedBoppTable.value || isPrinting105Table.value;
  const processTypeHint = isPrintedBoppTable.value ? "bopp_film" : isPrinting105Table.value ? "printing_105" : null;

  async function _doCreateSpr() {
    item.__creating_spr = true;
    try {
      const res = await frappe.call({
        method: "production_entry.production_planning.scheduler_api.create_item_spr",
        args: {
          pp_id: item.pp_id,
          planning_sheet_item_names: JSON.stringify([item.itemName]),
          process_type: processTypeHint,
        },
      });
      if (res.message && res.message.status === "ok") {
        const sprId = res.message.spr_id || res.message.spr_name;
        item.spr_name = mergeSprCsv(item.spr_name, sprId);
        syncSprNameForSamePP(item.pp_id, sprId, item.itemName);
        frappe.show_alert({ message: `SPR: ${sprId}`, indicator: "green" }, 3);
        setTimeout(() => frappe.set_route("Form", "Shaft Production Run", sprId), 600);
      } else {
        frappe.msgprint(res.message?.message || "Failed to create SPR");
      }
    } catch (e) {
      frappe.msgprint(`Error: ${e.message || e}`);
    } finally {
      item.__creating_spr = false;
    }
  }

  const confirmMsg = isBoppMode
    ? `Create Printing SPR for <b>${item.partyCode || item.order_code || ""}</b> (${item.color || item.fabric_colour || ""})?<br/>PP: ${item.pp_id}<br/>Item: ${itemDisplay}`
    : `Create Stock Entry for <b>${item.partyCode}</b> (${item.color})?<br/>PP: ${item.pp_id}<br/>Item: ${itemDisplay}`;
  frappe.confirm(confirmMsg, async () => { await _doCreateSpr(); });
}

function goToBoard() {
  if (isPrinting105Table.value) {
    frappe.set_route(isBoardMode.value ? "printing-order-table" : "printing-order-board");
    return;
  }
  frappe.set_route(isPrintedBoppTable.value ? "printed-bopp-film-board" : "lamination-board");
}

function onRowDragStart(row) {
  dragRow.value = row;
}

function onRowDragEnd() {
  dragOverShift.value = "";
}

async function handleShiftDrop(targetShift) {
  const row = dragRow.value;
  dragOverShift.value = "";
  if (!row || !row.itemName) return;
  const dateKey =
    viewScope.value === "daily" && filterOrderDate.value
      ? toDateKey(filterOrderDate.value)
      : toDateKey(moveTargetDate.value);
  if (!dateKey) {
    frappe.msgprint("Please choose a valid shift date.");
    return;
  }
  try {
    const res = await frappe.call({
      method: assignShiftMethod.value,
      args: {
        shift_date: dateKey,
        shift_label: targetShift,
        item_name: row.itemName,
        unit: isPrinting105Table.value ? row.unit || filterUnit.value || "" : undefined,
      },
    });
    const msg = res?.message || {};
    frappe.show_alert({ message: `Moved to ${targetShift} on ${dateKey} (${msg.updated_count || 0})`, indicator: "green" }, 3);
    await fetchData();
  } catch (e) {
    frappe.msgprint(`Failed to move row: ${e?.message || e}`);
  } finally {
    dragRow.value = null;
  }
}

function currentShiftDateForDialog() {
  if (viewScope.value === "daily" && filterOrderDate.value) return filterOrderDate.value;
  return frappe.datetime.get_today();
}

function printingRowsForShiftDate(dateKey) {
  const dk = toDateKey(dateKey);
  const pc = (filterPartyCode.value || "").trim().toLowerCase();
  const cu = (filterCustomer.value || "").trim().toLowerCase();
  let rows = (rawData.value || []).filter((r) => {
    if (toDateKey(r.plannedDate || r.planned_date) !== dk) return false;
    if (isPrinting105Table.value && isPrintingQueueUnit(r)) return false;
    if (filterUnit.value && normalizeUnitValue(r.unit) !== filterUnit.value) return false;
    if (pc && !String(r.partyCode || r.order_code || "").toLowerCase().includes(pc)) return false;
    if (cu && !String(r.customer_name || r.customer || "").toLowerCase().includes(cu)) return false;
    return !!(r.itemName || r.item_name);
  });
  return sortRowsBySavedSequence(rows);
}

function shiftOrderLabel(row, idx = 0) {
  const code = String(row.partyCode || row.order_code || row.itemCode || row.item_code || "-").trim();
  const customer = String(row.customer_name || row.customer || "-").trim();
  const design = String(row.custom_design_code || row.design_code || "").trim();
  const item = String(row.itemCode || row.item_code || "").trim();
  return `${idx + 1}. ${code} - ${customer}${design ? ` - Design ${design}` : ""}${item ? ` - ${item}` : ""}`;
}

function openAssignShiftDialog() {
  let dialog = null;
  const rowOptionMap = {};
  const updatePrintingOrderChoices = () => {
    if (!dialog || !isPrinting105Table.value) return;
    const dateKey = dialog.get_value("shift_date") || currentShiftDateForDialog();
    const rows = printingRowsForShiftDate(dateKey);
    const options = [`All visible printing orders (${rows.length})`];
    Object.keys(rowOptionMap).forEach((k) => delete rowOptionMap[k]);
    rows.forEach((row, idx) => {
      const label = shiftOrderLabel(row, idx);
      rowOptionMap[label] = row;
      options.push(label);
    });
    dialog.set_df_property("target_order", "options", options.join("\n"));
    dialog.set_value("target_order", options[0]);
    const preview = rows.length
      ? rows.map((row, idx) => `<div>${shiftOrderLabel(row, idx)}</div>`).join("")
      : "<div style='color:#b91c1c;'>No visible printing orders for this date/filter.</div>";
    dialog.fields_dict.order_preview.$wrapper.html(`<div style="font-size:12px;color:#334155;line-height:1.5;"><b>Orders to assign:</b>${preview}</div>`);
  };
  const d = new frappe.ui.Dialog({
    title: isPrinting105Table.value ? "Assign Printing Shift" : isPrintedBoppTable.value ? "Assign Printed BOPP film shift" : "Assign Lamination Shift",
    fields: [
      { fieldname: "shift_date", label: "Planned Date", fieldtype: "Date", reqd: 1, default: currentShiftDateForDialog(), onchange: () => updatePrintingOrderChoices() },
      { fieldname: "shift_label", label: "Shift", fieldtype: "Select", options: "DAY\nNIGHT", reqd: 1, default: "DAY" },
      { fieldname: "target_order", label: "Printing Order", fieldtype: "Select", hidden: !isPrinting105Table.value },
      { fieldname: "order_preview", fieldtype: "HTML", hidden: !isPrinting105Table.value },
    ],
    primary_action_label: "Apply",
    primary_action: async (vals) => {
      try {
        if (maintenanceTypeForDate(vals.shift_date)) {
          frappe.msgprint(`Cannot assign shift on ${vals.shift_date}. Machine is OFF (${maintenanceTypeForDate(vals.shift_date)}).`);
          return;
        }
        let msg = {};
        let affectedLabels = [];
        if (isPrinting105Table.value) {
          const selected = String(vals.target_order || "").trim();
          let rows = selected === "All visible printing orders (0)"
            ? []
            : selected.startsWith("All visible printing orders")
            ? printingRowsForShiftDate(vals.shift_date)
            : [rowOptionMap[selected]].filter(Boolean);
          if (!rows.length) {
            frappe.msgprint("Choose at least one printing order for this shift.");
            return;
          }
          let updated = 0;
          for (const row of rows) {
            const res = await frappe.call({
              method: assignShiftMethod.value,
              args: {
                shift_date: vals.shift_date,
                shift_label: vals.shift_label,
                item_name: row.itemName || row.item_name,
                unit: row.unit || filterUnit.value || "",
              },
            });
            updated += Number(res?.message?.updated_count || 0);
            affectedLabels.push(shiftOrderLabel(row, affectedLabels.length));
          }
          msg = { shift: vals.shift_label, updated_count: updated };
        } else {
          const assignArgs = { shift_date: vals.shift_date, shift_label: vals.shift_label };
          const res = await frappe.call({
            method: assignShiftMethod.value,
            args: assignArgs,
          });
          msg = res?.message || {};
        }
        frappe.show_alert(
          { message: `Shift ${msg.shift || vals.shift_label} applied to ${msg.updated_count || 0} update(s)${affectedLabels.length ? `: ${affectedLabels.join("; ")}` : ""}`, indicator: "green" },
          5
        );
        d.hide();
        if (viewScope.value === "daily") filterOrderDate.value = vals.shift_date;
        await fetchData();
      } catch (e) {
        frappe.msgprint(`Failed to assign shift: ${e?.message || e}`);
      }
    },
  });
  dialog = d;
  d.show();
  updatePrintingOrderChoices();
}

function getMaintenanceRecordsHTML() {
  if (!maintenanceRecords.value.length) {
    return `<p style="color:#64748b;text-align:center;padding:6px 0;">No maintenance records for ${isPrinting105Table.value ? "Printing" : isPrintedBoppTable.value ? "Printed BOPP film" : "Lamination"} in this scope.</p>`;
  }
  let html = '<table style="width:100%;border-collapse:collapse;font-size:12px;"><tr style="background:#f8fafc;font-weight:700;"><th style="border:1px solid #e2e8f0;padding:6px;">Unit</th><th style="border:1px solid #e2e8f0;padding:6px;">Type</th><th style="border:1px solid #e2e8f0;padding:6px;">From</th><th style="border:1px solid #e2e8f0;padding:6px;">To</th><th style="border:1px solid #e2e8f0;padding:6px;">Status</th></tr>';
  maintenanceRecords.value.forEach((rec) => {
    html += `<tr><td style="border:1px solid #e2e8f0;padding:6px;text-align:center;">${rec.unit || "-"}</td><td style="border:1px solid #e2e8f0;padding:6px;text-align:center;">${rec.maintenance_type || "-"}</td><td style="border:1px solid #e2e8f0;padding:6px;text-align:center;">${rec.start_date || "-"}</td><td style="border:1px solid #e2e8f0;padding:6px;text-align:center;">${rec.end_date || "-"}</td><td style="border:1px solid #e2e8f0;padding:6px;text-align:center;">${rec.status || "-"}</td></tr>`;
  });
  html += "</table>";
  return html;
}

function openMachineOffDialog() {
  const fields = [
    { fieldtype: "Date", fieldname: "start_date", label: "From Date", reqd: 1, default: filterOrderDate.value || frappe.datetime.get_today() },
    { fieldtype: "Date", fieldname: "end_date", label: "To Date", reqd: 1, default: filterOrderDate.value || frappe.datetime.get_today() },
  ];
  if (isPrinting105Table.value) {
    fields.push({
      fieldtype: "Select",
      fieldname: "unit",
      label: "Printing Unit",
      options: PRINTING_FILTER_UNITS.join("\n"),
      default: filterUnit.value || PRINTING_UNIT_2_COLOUR,
      reqd: 1,
    });
  }
  fields.push(
    {
      fieldtype: "Select",
      fieldname: "maintenance_type",
      label: "Type",
      options: "Machine Off\nBreakdown - Full\nBreakdown - Partial\nEB Shutdown\nMesh Change\nDie Change",
      default: "Machine Off",
      reqd: 1,
    },
    { fieldtype: "Small Text", fieldname: "notes", label: "Notes" },
    { fieldtype: "HTML", fieldname: "records", options: getMaintenanceRecordsHTML() }
  );
  const d = new frappe.ui.Dialog({
    title: isPrinting105Table.value ? "Printing Machine Off" : isPrintedBoppTable.value ? "Printed BOPP film — Machine Off" : "Lamination Machine Off",
    fields,
    primary_action_label: "Save",
    primary_action: async (vals) => {
      try {
        const res = await frappe.call({
          method: addMachineOffMethod.value,
          args: {
            start_date: vals.start_date,
            end_date: vals.end_date,
            maintenance_type: vals.maintenance_type,
            notes: vals.notes || "",
            unit: isPrinting105Table.value ? vals.unit : undefined,
          },
        });
        if (res?.message?.status === "success") {
          frappe.show_alert(
            {
              message:
                res.message.message ||
                (isPrinting105Table.value ? "Printing maintenance saved" : isPrintedBoppTable.value ? "Printed BOPP film maintenance saved" : "Lamination maintenance saved"),
              indicator: "green",
            },
            4
          );
          d.hide();
          await fetchMaintenanceRecords();
          await fetchData();
        } else {
          frappe.msgprint(res?.message?.message || "Failed to save maintenance.");
        }
      } catch (e) {
        frappe.msgprint(`Error saving maintenance: ${e?.message || e}`);
      }
    },
  });
  d.show();
}

function toggleViewScope() {
  if (viewScope.value === "monthly" && !filterMonth.value) {
    filterMonth.value = frappe.datetime.get_today().substring(0, 7);
  } else if (viewScope.value === "weekly" && !filterWeek.value) {
    const d = new Date();
    const dStart = new Date(d.getFullYear(), 0, 1);
    const days = Math.floor((d - dStart) / (24 * 60 * 60 * 1000));
    const weekNum = Math.ceil(days / 7);
    filterWeek.value = `${d.getFullYear()}-W${String(weekNum).padStart(2, "0")}`;
  }
  updateUrlParams();
  fetchData();
}

async function fetchData() {
  if (fetchInProgress) {
    fetchQueued = true;
    return;
  }
  fetchInProgress = true;
  try {
    let args = {
      party_code: filterPartyCode.value,
      planned_only: 1,
    };
    if (!isPrintedBoppTable.value && !isPrinting105Table.value) {
      args.lamination_process = laminationProcess.value;
    }
    if (isPrinting105Table.value && filterUnit.value) {
      args.unit = filterUnit.value;
    }
    if (isPrinting105Table.value) {
      args.process = printingProcess.value;
    }
    if (viewScope.value === "monthly") {
      if (!filterMonth.value) return;
      const [year, month] = filterMonth.value.split("-");
      const lastDay = new Date(year, month, 0).getDate();
      args.start_date = `${filterMonth.value}-01`;
      args.end_date = `${filterMonth.value}-${lastDay}`;
    } else if (viewScope.value === "weekly") {
      if (!filterWeek.value) return;
      const [yearStr, weekStr] = filterWeek.value.split("-W");
      const y = parseInt(yearStr, 10);
      const w = parseInt(weekStr, 10);
      const simple = new Date(y, 0, 1 + (w - 1) * 7);
      const dow = simple.getDay();
      const ISOweekStart = new Date(simple);
      if (dow <= 4) ISOweekStart.setDate(simple.getDate() - simple.getDay() + 1);
      else ISOweekStart.setDate(simple.getDate() + 8 - simple.getDay());
      const ISOweekEnd = new Date(ISOweekStart);
      ISOweekEnd.setDate(ISOweekEnd.getDate() + 6);
      const fmt = (d) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      args.start_date = fmt(ISOweekStart);
      args.end_date = fmt(ISOweekEnd);
    } else {
      args.date = filterOrderDate.value;
    }

    const tableMethods = isPrinting105Table.value
      ? [
          "production_entry.production_planning.scheduler_api.get_printing_order_table_data",
          "production_scheduler.api.get_printing_order_table_data",
        ]
      : isPrintedBoppTable.value
      ? [
          "production_entry.production_planning.scheduler_api.get_printed_bopp_film_table_data",
          "production_scheduler.api.get_printed_bopp_film_table_data",
        ]
      : [
          "production_entry.production_planning.scheduler_api.get_lamination_order_table_data",
          "production_scheduler.api.get_lamination_order_table_data",
        ];
    let r = null;
    let lastErr = null;
    for (const method of tableMethods) {
      try {
        r = await frappe.call({ method, args });
        break;
      } catch (e) {
        lastErr = e;
      }
    }
    if (!r) throw lastErr || new Error("Failed to load order table data");
    rawData.value = (r.message || []).map((d) => {
      if (isPrinting105Table.value) {
        return {
          ...d,
          itemName: d.psi_name || d.itemName || d.name || "",
          itemCode: d.item_code || d.itemCode || "",
          planningSheet: d.plan_name || d.planningSheet || "",
          customer_name: d.customer || d.customer_name || "",
          partyCode: d.order_code || d.partyCode || "",
          order_code: d.order_code || d.partyCode || "",
          color: d.color || "",
          fabric_colour: d.color || "",
          quality: d.quality || d.custom_quality || "",
          unit: d.unit || "",
          gsm: d.gsm || 0,
          width_inch: d.width_inch || 0,
          design_code: d.custom_design_code || d.design_code || "",
          design_name: d.custom_design_name || d.design_name || "",
          custom_design_name: d.custom_design_name || d.design_name || "",
          custom_design_attachment: d.custom_design_attachment || d.design_attachment || d.custom_design_image || d.design_image || "",
          process: d.process || inferProcessFromItemCode(d.item_code || d.itemCode || ""),
          lamination_gsm: d.lamination_gsm || d.custom_lam_gsm || 0,
          custom_printing_shift: d.custom_printing_shift || d.shift_label || "DAY",
          custom_printing_arrangement_seq: d.custom_printing_arrangement_seq || "",
          plannedDate: d.planned_date || d.plannedDate || filterOrderDate.value,
          planned_date: d.planned_date || d.plannedDate || filterOrderDate.value,
          shift_label: d.custom_printing_shift || d.shift_label || "DAY",
          can_create_spr: d.can_create_spr !== false,
          transfer_details: d.transfer_details || [],
          produced_qty: d.produced_qty || 0,
          transferred_qty: d.transferred_qty || 0,
          linked_work_orders: d.linked_work_orders || [],
          salesOrderItem: d.salesOrderItem || d.sales_order_item || "",
          idx: d.idx != null ? Number(d.idx) : 0,
        };
      }
      const soi = d.salesOrderItem || d.sales_order_item || "";
      const designAttachment =
        d.custom_design_attachment ||
        d.design_attachment ||
        d.custom_design_image ||
        d.design_image ||
        "";
      return {
        ...d,
        itemName: d.psi_name || d.itemName || d.name || "",
        itemCode: d.item_code || d.itemCode || "",
        salesOrderItem: soi,
        sales_order_item: soi,
        custom_design_attachment: designAttachment,
        design_attachment: designAttachment,
        custom_design_code: d.custom_design_code || d.design_code || "",
        design_code: d.design_code || d.custom_design_code || "",
        width_inch: d.width_inch || d.widthInch || 0,
      };
    });
    if (!initialFetchRetried && (!rawData.value || rawData.value.length === 0)) {
      initialFetchRetried = true;
      setTimeout(() => fetchData(), 450);
    }
    await fetchLaminationSequences();
    await fetchMaintenanceRecords();
  } catch (e) {
    console.error(e);
    const tableLabel = isPrinting105Table.value
      ? "printing order table"
      : isPrintedBoppTable.value
      ? "printed BOPP film table"
      : "lamination order table";
    frappe.msgprint(`Error loading ${tableLabel}: ${getErrorText(e)}`);
  } finally {
    fetchInProgress = false;
    if (fetchQueued) {
      fetchQueued = false;
      fetchData();
    }
  }
}

function processLabel(row) {
  const disp = String(row?.process_display || "").trim();
  if (disp) return disp;
  const p =
    String(row?.lamination_process || row?.laminationProcess || row?.process || "").trim() ||
    inferProcessFromItemCode(row?.itemCode || row?.item_code || "");
  if (p === "108") return "108 BOPP Slitting";
  if (p === "107") return "107 BOPP Lamination Fabric";
  if (p === "106") return "106 Laminated Printing";
  if (p === "105") return "105 Printing";
  return p === "104" ? "104 Plain Lamination Fabric" : p || "-";
}

function inferProcessFromItemCode(itemCode) {
  const ic = String(itemCode || "").trim().toUpperCase();
  if (!ic) return "";
  const body = ic.includes("-") ? ic.split("-").slice(1).join("-") : ic;
  const m = body.match(/(\d{3})/);
  return m ? m[1] : "";
}

function inferLaminationProcessFromItemCode(itemCode) {
  const ic = String(itemCode || "").trim().toUpperCase();
  if (!ic) return "";
  if (ic.startsWith("104")) return "104";
  if (ic.startsWith("107")) return "107";
  if (ic.includes("-107")) return "107";
  if (ic.includes("-104")) return "104";
  return "";
}

function startAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(() => {
    if (document.visibilityState !== "visible") return;
    fetchData();
  }, 15000);
}

function updateUrlParams() {
  const q = new URLSearchParams();
  if (viewScope.value === "daily") q.set("date", filterOrderDate.value);
  if (viewScope.value === "weekly") q.set("week", filterWeek.value);
  if (viewScope.value === "monthly") q.set("month", filterMonth.value);
  q.set("scope", viewScope.value);
  if (!isPrintedBoppTable.value && !isPrinting105Table.value) {
    q.set("lamination_process", laminationProcess.value);
  }
  if (isPrinting105Table.value && filterUnit.value) {
    q.set("unit", filterUnit.value);
  }
  if (isPrinting105Table.value) {
    q.set("process", printingProcess.value);
  }
  window.history.replaceState({}, "", `${window.location.pathname}?${q.toString()}`);
}

async function syncSprWeightToTable() {
  try {
    // Fabric qty / child WO qty now comes from live WO+PP data path in get_lamination_order_table_data.
    // Keep this button as a manual refresh action without heavy backend sync.
    await fetchData();
    frappe.show_alert(
      {
        message: isPrintedBoppTable.value
          ? "Printed BOPP film table refreshed from live WO data"
          : isPrinting105Table.value
            ? "Printing table refreshed from live WO data"
            : "Lamination table refreshed from live WO data",
        indicator: "green",
      },
      4
    );
  } catch (e) {
    console.error(e);
    frappe.msgprint(`Failed to sync SPR data: ${getErrorText(e)}`);
  }
}

watch([filterOrderDate, filterWeek, filterMonth], () => {
  if (!filtersReady.value) return;
  if (viewScope.value === "daily" && filterOrderDate.value) {
    moveTargetDate.value = toDateKey(filterOrderDate.value) || moveTargetDate.value;
  }
  updateUrlParams();
  fetchData();
});

watch(filterUnit, () => {
  if (!filtersReady.value || !isPrinting105Table.value) return;
  updateUrlParams();
  fetchData();
});

onMounted(async () => {
  try {
    const u = localStorage.getItem(DIM_UNIT_LS_KEY);
    if (u === "mm" || u === "inches") sizeDimUnit.value = u;
  } catch (_) {}
  const p = new URLSearchParams(window.location.search);
  if (p.get("scope")) viewScope.value = p.get("scope");
  if (p.get("date")) filterOrderDate.value = p.get("date");
  if (p.get("week")) filterWeek.value = p.get("week");
  if (p.get("month")) filterMonth.value = p.get("month");
  if (isPrinting105Table.value && p.get("unit")) {
    const u = normalizeUnitValue(p.get("unit"));
    if (u && u.toUpperCase() !== PRINTING_UNASSIGNED_UNIT.toUpperCase()) {
      filterUnit.value = u;
    }
  }
  if (isPrinting105Table.value) {
    const pp = (p.get("process") || "").trim();
    if (pp === "105" || pp === "106" || pp === "__all__") printingProcess.value = pp;
  }
  if (!isPrintedBoppTable.value && !isPrinting105Table.value) {
    const lp = (p.get("lamination_process") || p.get("lam_proc") || "").trim();
    if (lp === "104" || lp === "107" || lp === "__all__") laminationProcess.value = lp;
  }
  await fetchData();
  startAutoRefresh();
  document.addEventListener("visibilitychange", onVisibilityRefresh);
  if (frappe.realtime && frappe.realtime.on && !sprRealtimeHandlerRegistered) {
    frappe.realtime.on("shaft_production_run_updated", handleSprRealtimeUpdate);
    sprRealtimeHandlerRegistered = true;
  }
  moveTargetDate.value = toDateKey(filterOrderDate.value) || frappe.datetime.get_today();
  updateUrlParams();
  filtersReady.value = true;
});

onUnmounted(() => {
  document.removeEventListener("visibilitychange", onVisibilityRefresh);
  if (sprRealtimeHandlerRegistered && frappe.realtime && frappe.realtime.off) {
    frappe.realtime.off("shaft_production_run_updated", handleSprRealtimeUpdate);
    sprRealtimeHandlerRegistered = false;
  }
  if (visibilityRefreshTimer) {
    clearTimeout(visibilityRefreshTimer);
    visibilityRefreshTimer = null;
  }
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
});
</script>

<style scoped>
.cc-container {
  display: flex;
  flex-direction: column;
  padding: 20px;
  background: linear-gradient(160deg, #ecfdf5 0%, #f8fafc 45%, #eef2ff 100%);
  min-height: 100vh;
}
.cc-filters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 14px;
  align-items: end;
  margin-bottom: 16px;
  padding: 16px 18px;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 14px;
  border: 1px solid rgba(16, 185, 129, 0.18);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(6px);
}
.cc-filter-title {
  grid-column: 1 / -1;
  padding: 4px 0 6px;
  font-weight: 800;
  color: #065f46;
  font-size: 18px;
  letter-spacing: 0.02em;
}
.cc-select-scope {
  font-weight: 700;
  color: #047857;
  min-height: 34px;
}
.cc-shift-btns {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.cc-shift-btns button {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}
.cc-shift-btns button.active {
  background: #047857;
  color: #fff;
  border-color: #047857;
}
.cc-filter-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-end;
  justify-content: flex-end;
  grid-column: 1 / -1;
}
.cc-filter-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cc-filter-item label {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
}
.cc-clear-btn,
.cc-maint-btn,
.cc-view-btn {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}
.cc-maint-btn {
  background: #fff7ed;
  border-color: #fdba74;
  color: #9a3412;
  font-weight: 700;
}
.cc-view-btn {
  background: #3b82f6;
  color: #fff;
  border-color: #2563eb;
}
.cc-table-container {
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(16, 185, 129, 0.2);
  width: 100%;
  max-width: 100%;
  overflow: visible;
  font-size: 14px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
}
.cc-order-table-scroll {
  width: 100%;
  max-width: 100%;
  max-height: calc(100vh - 240px);
  overflow: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 0 0 14px 14px;
}
.cc-shift-board {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  margin-bottom: 12px;
  padding: 10px 12px;
}
.cc-shift-board-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 10px;
}
.cc-shift-board-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f766e;
}
.cc-shift-board-date label {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 4px;
}
.cc-shift-lanes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.cc-shift-lane {
  min-height: 88px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  padding: 8px;
  background: #f8fafc;
}
.cc-shift-lane.over {
  border-color: #0ea5e9;
  background: #eff6ff;
}
.cc-shift-lane-title {
  font-size: 11px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 6px;
}
.cc-shift-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px;
  margin-bottom: 6px;
  cursor: grab;
}
.cc-shift-card-code {
  font-size: 11px;
  font-weight: 700;
  color: #0f172a;
}
.cc-shift-card-meta {
  font-size: 10px;
  color: #64748b;
}
.lot-header {
  padding: 14px 16px;
  font-weight: 800;
  font-size: 15px;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  background: linear-gradient(90deg, #047857 0%, #059669 55%, #10b981 100%);
  color: #ecfdf5;
  border-bottom: 1px solid rgba(255, 255, 255, 0.25);
}
.cc-prod-table {
  width: 100%;
  min-width: 1280px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  line-height: 1.55;
}
.cc-prod-table th {
  position: sticky;
  top: 0;
  z-index: 30;
  background: linear-gradient(180deg, #065f46 0%, #047857 100%);
  color: #f0fdf4;
  padding: 14px 12px;
  text-align: left;
  font-weight: 700;
  white-space: normal;
  min-width: 100px;
  word-wrap: break-word;
  border-bottom: 2px solid #10b981;
  box-shadow: 0 2px 0 rgba(0, 0, 0, 0.06);
}
.cc-prod-table td {
  border-bottom: 1px solid #e5e7eb;
  border-right: 1px solid #f1f5f9;
  padding: 12px 12px;
  vertical-align: middle;
  line-height: 1.5;
  background: #fff;
}
.cc-row-draggable {
  cursor: move;
  transition: background-color 0.15s ease, box-shadow 0.15s ease;
}
.cc-row-drag-over {
  outline: 2px dashed #0ea5e9;
  outline-offset: -2px;
  background: #f0f9ff !important;
}
.cc-prod-table tbody tr {
  height: auto;
  transition: background-color 0.2s ease, transform 0.15s ease;
}
.cc-prod-table tbody tr:nth-child(even) td {
  background: #f8fafc;
}
.cc-prod-table tbody tr:hover td {
  background: #ecfdf5;
}
.th-n {
  width: 60px;
  text-align: center;
}
.cell-center {
  text-align: center;
  min-width: 80px;
}
.cc-maint-chip {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  color: #b91c1c;
  background: #fee2e2;
  border: 1px solid #fecaca;
}
.cc-order-btns {
  display: inline-flex;
  gap: 4px;
}
.cc-drag-handle {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #fff;
  color: #334155;
  font-weight: 700;
  letter-spacing: 1px;
}
.cc-lock-hint {
  color: #94a3b8;
}
.cc-row-order-btn {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #0f172a;
  border-radius: 4px;
  width: 24px;
  height: 22px;
  line-height: 1;
  cursor: pointer;
}
.cc-row-order-btn:hover {
  background: #e2e8f0;
}
.cell-right {
  text-align: right;
  padding-right: 16px;
}
.cc-pp-btn {
  padding: 6px 10px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid #6366f1;
  background: #eef2ff;
  color: #3730a3;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}
.cc-pp-btn:hover {
  background: #c7d2fe;
  border-color: #4f46e5;
}
.cc-preview-btn {
  padding: 4px 8px;
  font-size: 10px;
  border-radius: 999px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #334155;
  cursor: pointer;
  white-space: nowrap;
}
.cc-preview-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.pt-no-pp-hint {
  font-size: 10px;
  color: #94a3b8;
}
.pt-stock-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}
.pt-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}
.pt-pill {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 999px;
  font-weight: 600;
  display: inline-block;
  white-space: nowrap;
}
.pt-pill-muted {
  background: #f1f5f9;
  color: #64748b;
}
.pt-pill-draft {
  background: #fef3c7;
  color: #92400e;
}
.pt-pill-submitted {
  background: #d1fae5;
  color: #065f46;
}
.pt-pill-wo {
  background: #e0e7ff;
  color: #3730a3;
}
.pt-pill-wo-done {
  background: #dcfce7;
  color: #166534;
}
.pt-pill-wo-open {
  background: #ffedd5;
  color: #9a3412;
}
.pt-pill-wo-unknown {
  background: #f1f5f9;
  color: #475569;
}
.pt-prod-status-line {
  font-size: 9px;
  color: #64748b;
}
.pt-btn-entry {
  margin-top: 4px;
}
.pt-wo-closed-hint {
  font-size: 10px;
  color: #94a3b8;
}
.pt-linked-wo-line {
  margin-top: 2px;
  word-break: break-all;
}
.pt-linked-wo-link {
  color: #0369a1;
  text-decoration: none;
  font-weight: 600;
  font-size: 9px;
}
.pt-linked-wo-link:hover {
  text-decoration: underline;
}
.pt-spr-btn-draft {
  border-color: #f59e0b !important;
  background: #fffbeb !important;
}
.pt-spr-btn-submitted {
  border-color: #10b981 !important;
  background: #ecfdf5 !important;
}
.pt-spr-btn-done {
  border-color: #94a3b8 !important;
  background: #f8fafc !important;
}
.font-mono {
  font-family: ui-monospace, monospace;
}

.printed-bopp-film-table .cc-filter-title {
  color: #5b21b6;
}
.printed-bopp-film-table .cc-select-scope {
  color: #5b21b6;
}
.printed-bopp-film-table .cc-shift-btns button.active {
  background: #6d28d9;
  border-color: #5b21b6;
}
.printed-bopp-film-table .lot-header {
  background: linear-gradient(90deg, #ede9fe 0%, #ddd6fe 100%);
  color: #4c1d95;
  border-bottom-color: #c4b5fd;
}
.printed-bopp-film-table .cc-prod-table th {
  background: linear-gradient(180deg, #7c3aed 0%, #5b21b6 100%);
}
.printed-bopp-film-table .cc-shift-board-title {
  color: #5b21b6;
}
.printed-bopp-film-table .cc-shift-lane.over {
  border-color: #7c3aed;
  background: #f5f3ff;
}
.printing-105-table .cc-filter-title,
.printing-105-table .cc-select-scope,
.printing-105-table .cc-shift-board-title {
  color: #0f766e;
}
.printing-105-table .lot-header {
  background: linear-gradient(90deg, #ccfbf1 0%, #99f6e4 100%);
  color: #115e59;
  border-bottom-color: #5eead4;
}
.printing-105-table .cc-prod-table th {
  background: linear-gradient(180deg, #14b8a6 0%, #0f766e 100%);
}
.printing-105-table .cc-preview-btn {
  border-color: #5eead4;
  background: #ecfdf5;
  color: #0f766e;
}
</style>


