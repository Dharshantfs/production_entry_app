<template>
  <div class="cc-container">
    <!-- Filter Bar -->
    <div class="cc-filters">
      <div class="cc-filter-item">
        <label>{{ viewScope === 'weekly' ? 'Select Week' : 'Select Month' }}</label>
        <div style="display:flex; gap:4px;">
            <input v-if="viewScope === 'weekly'" type="week" v-model="filterWeek" @change="fetchData" />
            <input v-if="viewScope === 'monthly'" type="month" v-model="filterMonth" @change="fetchData" />
            
            <button class="cc-mini-btn" @click="toggleViewScope" :title="viewScope === 'weekly' ? 'Switch to Monthly View' : 'Switch to Weekly View'">
                {{ viewScope === 'weekly' ? '📅 Month' : '🗓️ Week' }}
            </button>
        </div>
      </div>
      <div class="cc-filter-item">
        <label>Party Code</label>
        <input
          type="text"
          v-model="filterPartyCode"
          placeholder="Search party..."
          @input="fetchData"
        />
      </div>
      <div class="cc-filter-item">
        <label>Customer</label>
        <input
          type="text"
          v-model="filterCustomer"
          placeholder="Search customer..."
          @input="fetchData"
        />
      </div>
      <div class="cc-filter-item">
        <label>Plan</label>
        <div style="display:flex; gap:4px; align-items:center;">
            <select v-model="selectedPlan" @change="fetchData">
                <option v-for="p in visiblePlans" :key="p.name" :value="p.name">
                    {{ p.locked ? '🔒 ' : '' }}{{ p.name === 'Default' ? 'Default' : currentMonthPrefix + ' ' + p.name }}
                </option>
            </select>
            <button v-if="selectedPlan" class="cc-mini-btn" @click="togglePlanLock" :title="isCurrentPlanLocked ? 'Unlock Plan' : 'Lock Plan'" style="margin-right:2px; padding: 2px 4px;font-size: 14px;">
                {{ isCurrentPlanLocked ? '🔒' : '🔓' }}
            </button>
            <button class="cc-mini-btn" @click="createNewPlan" title="Create New Plan Tab" style="color:#2563eb; font-weight:bold;">
                ➕ New
            </button>
            <button v-if="selectedPlan !== 'Default'" class="cc-mini-btn" @click="deletePlan" title="Delete this Plan" style="color:#dc2626; font-weight:bold;">
                🗑️
            </button>
        </div>
      </div>
      <div class="cc-filter-item">
        <label>Unit</label>
        <select v-model="filterUnit">
          <option value="">All Units</option>
          <option v-for="u in units" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>
      <div class="cc-filter-item">
        <label>Status</label>
        <select v-model="filterStatus">
          <option value="">All</option>
          <option value="Draft">Draft</option>
          <option value="Finalized">Finalized</option>
        </select>
      </div>

      <!-- NEW: dynamically computed Plan Code indicator -->
      <div v-if="derivedPlanCode" class="cc-filter-item" style="margin-left:8px; border-left: 1px solid #e5e7eb; padding-left: 12px; justify-content: center;">
          <label style="color:#6366f1; font-weight:bold;">Plan Code</label>
          <div style="font-family: monospace; font-size:14px; font-weight:800; color:#1e1b4b; background:#e0e7ff; padding: 4px 10px; border-radius: 6px; border: 1px solid #c7d2fe; letter-spacing: 0.5px;">
              {{ derivedPlanCode }}
          </div>
      </div>

      <div class="cc-filter-item" style="flex-direction:row; align-items:flex-end; gap:4px; margin-left:auto;">
          <button 
            class="cc-view-btn" 
            :class="{ active: viewMode === 'kanban' }" 
            @click="viewMode = 'kanban'"
            title="Kanban Board View"
          >
            📋 Kanban
          </button>
          <button 
            class="cc-view-btn" 
            :class="{ active: viewMode === 'matrix' }" 
            @click="viewMode = 'matrix'"
            title="Matrix Pivot View"
          >
            📊 Matrix
          </button>
      </div>
      
      <button class="cc-clear-btn" @click="clearFilters">✕ Clear</button>
      <button v-if="isAdmin" class="cc-clear-btn" style="color: #dc2626; border-color: #dc2626; margin-left: 8px;" @click="emergencyReset" title="FORCE UNLOCK: Returns all stuck orders to Color Chart">
        🚑 Emergency Reset
      </button>
      <button class="cc-clear-btn" style="color: #6366f1; border-color: #6366f1; margin-left: 8px;" @click="showGlobalSortInfo" title="View Color Hierarchy Rules">
        🎨 Sort Info
      </button>
      <button class="cc-clear-btn" style="color: #2563eb; border-color: #2563eb; margin-left: 8px;" @click="autoAllocate" title="Auto-assign orders based on Width & Quality">
        🪄 Auto Alloc
      </button>
      <button class="cc-clear-btn" style="color: #059669; border-color: #059669; margin-left: 8px;" @click="openPullOrdersDialog" title="Pull orders from a future date">
        📥 Pull Orders
      </button>
      <button class="cc-clear-btn" style="color: #7c3aed; border-color: #7c3aed; margin-left: 8px; font-weight:600;" @click="pushToProductionBoard" :disabled="!canPushToBoard" title="Push visible orders to Production Board plan">
        📤 Push to Board
      </button>
      <button class="cc-clear-btn" style="color: #ca8a04; border-color: #ca8a04; margin-left: 8px; font-weight:600;" @click="openMovePlanDialog" title="Move visible orders to another Color Chart plan">
        📥 Move to Plan
      </button>
      <button v-if="isAdmin" class="cc-clear-btn" style="color: #dc2626; border-color: #dc2626; margin-left: 8px;" @click="openRescueDialog" title="Rescue lost or stuck orders">
        🚑 Rescue Orders
      </button>
      <button class="cc-clear-btn" style="color: #7c3aed; border-color: #7c3aed; margin-left: 8px; font-weight:600;" @click="syncAllPlanCodes" title="Recalculate Plan Codes for all existing sheets">
        📂 Sync Plan Codes
      </button>
      <button v-if="hasRecentlyReset" class="cc-clear-btn" style="color: #ca8a04; border-color: #ca8a04; margin-left: 8px; font-weight:600;" @click="restoreWhiteOrders" title="Restore accidentally cleared white orders">
        🛠️ Restore Whites
      </button>
      <button class="cc-clear-btn" style="background-color: #10b981; color: white; border: none; margin-left: auto;" @click="goToConfirmedOrders" title="View Confirmed Orders Page">
          ✅ Confirmed Orders
      </button>
      <button v-if="canAccessDashboard" class="cc-clear-btn" style="background-color: #f59e0b; color: white; border: none; margin-left: 8px;" @click="goToSequenceApprovals" title="View Sequence Approval Dashboard">
          📋 Approval Dashboard
      </button>
    </div>

    <!-- Kanban View -->
    <div v-if="viewMode === 'kanban'" class="cc-board" :key="renderKey">
      
      <!-- DAILY & WEEKLY VIEW -->
      <template v-if="viewScope === 'daily' || viewScope === 'weekly'">
        <div
            v-for="unit in visibleUnits"
            :key="unit"
            class="cc-column"
            :data-unit="unit"
        >
            <div class="cc-col-header" :style="{ borderTopColor: headerColors[unit] }">
            <div class="cc-header-top">
                <span class="cc-col-title">{{ unit === 'UNASSIGNED' ? 'Unassigned' : unit }}</span>
                <span v-if="unit !== 'UNASSIGNED' && sequenceStatuses[unit]" :class="['cc-status-badge', sequenceStatuses[unit].toLowerCase().replace(' ', '-')]">
                  {{ sequenceStatuses[unit] }}
                </span>
                <!-- Sort Controls -->
                <div class="cc-unit-controls">
                <span style="font-size:10px; color:#64748b; margin-right:4px;">{{ getSortLabel(unit) }}</span>
                <button class="cc-mini-btn" @click="toggleUnitColor(unit)" :title="getUnitSortConfig(unit).color === 'asc' ? 'Currently: Light→Dark (click for Dark→Light)' : 'Currently: Dark→Light (click for Light→Dark)'">
                    {{ getUnitSortConfig(unit).color === 'asc' ? '☀️→🌙' : '🌙→☀️' }}
                </button>
                <button class="cc-mini-btn" @click="toggleUnitGsm(unit)" :title="getUnitSortConfig(unit).gsm === 'desc' ? 'GSM: High→Low (click to reverse)' : 'GSM: Low→High (click to reverse)'">
                    {{ getUnitSortConfig(unit).gsm === 'desc' ? '⬇️' : '⬆️' }}
                </button>
                <button class="cc-mini-btn" @click="toggleUnitPriority(unit)" :title="getUnitSortConfig(unit).priority === 'color' ? 'Priority: Color (click for GSM)' : 'Priority: GSM (click for Color)'">
                    {{ getUnitSortConfig(unit).priority === 'color' ? '🎨' : '📏' }}
                </button>
                <button class="cc-mini-btn" @click="showSortInfo(unit)" title="Show Sorting & Mixing Rules">
                    ℹ️
                </button>
                </div>
                <div class="cc-header-status-badge" :class="sequenceStatuses[unit] ? sequenceStatuses[unit].toLowerCase().replace(' ', '-') : 'draft'">
                    {{ sequenceStatuses[unit] || 'Draft' }}
                </div>
            </div>
            <div class="cc-header-stats">
                <div style="display:flex; flex-direction:column; align-items:flex-end;">
                    <span class="cc-stat-weight">
                    {{ getUnitTotal(unit).toFixed(2) }}T
                    </span>
                    <!-- Approval Actions -->
                    <div class="cc-approval-actions" v-if="viewMode === 'kanban' && filterOrderDate && !String(filterOrderDate.value || '').includes(',')">
                        <button v-if="(!sequenceStatuses[unit] || sequenceStatuses[unit] === 'Draft') && getUnitEntries(unit).length > 0" 
                                class="cc-approve-btn request" @click.stop="requestApproval(unit)">
                            📤 Request Approval
                        </button>
                        <button v-if="sequenceStatuses[unit] === 'Pending Approval' && currentUserRoles.includes('Manufacturing Manager')" 
                                class="cc-approve-btn approve" @click.stop="approveSequence(unit)">
                            ✅ Approve
                        </button>
                    </div>
                </div>
                <span class="cc-stat-mix" v-if="getMixRollCount(unit) > 0">
                ⚠️ {{ getMixRollCount(unit) }} mix{{ getMixRollCount(unit) > 1 ? 'es' : '' }}
                ({{ getMixRollTotalWeight(unit) }} Kg)
                </span>
            </div>
            </div>

            <!-- Maintenance Indicator -->
            <div v-if="getMaintenanceForDateAndUnit(filterOrderDate, unit)" class="cc-maintenance-indicator">
                🔧 {{ getMaintenanceForDateAndUnit(filterOrderDate, unit)[0].type }}
                <br><span style="font-size: 10px; font-weight: normal;">{{ getMaintenanceForDateAndUnit(filterOrderDate, unit)[0].start }} - {{ getMaintenanceForDateAndUnit(filterOrderDate, unit)[0].end }}</span>
            </div>

            <div class="cc-col-body" :data-unit="unit" ref="columnRefs">
            <template v-for="(entry, idx) in getUnitEntries(unit)" :key="entry.uniqueKey">
                <!-- Mix Roll Marker -->
                <div v-if="entry.type === 'mix'" class="cc-mix-marker">
                <div class="cc-mix-line"></div>
            <span class="cc-mix-label" :class="entry.mixType.toLowerCase().replace(' ', '-')">
                {{ entry.mixType }} — ~{{ entry.qty }} Kg
            </span>
                <div class="cc-mix-line"></div>
                </div>
                <!-- Order Card -->
                <div
                v-else
                class="cc-card"
                :data-name="entry.name"
                :data-item-name="entry.itemName"
                :data-color="entry.color"
                :data-planning-sheet="entry.planningSheet"
                @click="openForm(entry.planningSheet)"
                >
                <div class="cc-card-left">
                    <div
                    class="cc-color-swatch"
                    :style="{ backgroundColor: getHexColor(entry.color) }"
                    :title="entry.color"
                    ></div>
                    <div class="cc-card-info">
                    <div class="cc-card-color-name">{{ entry.color }}</div>
                    <div class="cc-card-customer">
                        <span style="font-weight:700; color:#111827;">{{ entry.partyCode }}</span>
                        <span v-if="entry.partyCode !== entry.customer_name" style="font-weight:400; color:#6b7280;"> · {{ entry.customer_name }}</span>
                    </div>
                    <div class="cc-card-details" style="display:flex; align-items:center;">
                        {{ entry.quality }} · {{ entry.gsm }} GSM
                        <span v-if="entry.has_wo" style="font-size:9px; padding:1px 4px; background:#dcfce7; color:#166534; border-radius:3px; margin-left:4px; font-weight:bold; border:1px solid #bbf7d0;" title="Work Order Created">WO</span>
                        <span v-else-if="entry.has_pp" style="font-size:9px; padding:1px 4px; background:#dbeafe; color:#1e40af; border-radius:3px; margin-left:4px; font-weight:bold; border:1px solid #bfdbfe;" title="Production Plan Created">PP</span>
                        <span v-else style="font-size:9px; padding:1px 4px; background:#fef3c7; color:#92400e; border-radius:3px; margin-left:4px; font-weight:bold; border:1px solid #fde68a;" title="Planning Sheet">PS</span>
                    </div>
                    </div>
                </div>
                <div class="cc-card-right">
                    <span class="cc-card-qty">{{ (entry.qty / 1000).toFixed(3) }} T</span>
                    <span class="cc-card-qty-kg">{{ entry.qty }} Kg</span>
                </div>
                </div>
            </template>

            <div v-if="!getUnitEntries(unit).length" class="cc-empty">
                No orders
            </div>
            </div>

            <!-- Unit Footer -->
            <div class="cc-col-footer">
            <span>Production: {{ getUnitProductionTotal(unit).toFixed(2) }}T</span>
            <span v-if="getMixRollTotalWeight(unit) > 0">
                Mix Waste: {{ (getMixRollTotalWeight(unit) / 1000).toFixed(3) }}T
            </span>
            </div>
        </div>
      </template>

      <!-- MONTHLY VIEW -->
      <div v-else class="cc-monthly-container">
          <!-- Header Row -->
          <div class="cc-monthly-header">
              <div class="cc-monthly-corner">Week / Unit</div>
              <div v-for="unit in visibleUnits" :key="unit" class="cc-monthly-col-header" :style="{ borderTopColor: headerColors[unit] }">
                  <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                      <span>{{ unit }}</span>
                      <!-- Removed Info Button -->
                  </div>
                  <span class="text-xs text-gray-500 block font-normal">
                      {{ getUnitProductionTotal(unit).toFixed(2) }}T
                  </span>
              </div>
          </div>

          <!-- Week Rows -->
          <div v-for="week in weeks" :key="week.id" class="cc-monthly-row-group">
              
              <!-- Week Label Header (Optional, if we want to separate weeks) -->
              <!-- <div class="cc-week-header">{{ week.label }} ({{ week.dateRange }})</div> -->

              <!-- Iterate Days in Week -->
              <div v-for="day in getDaysInWeek(week)" :key="day.date" class="cc-matrix-row" style="display:flex; border-bottom:1px solid #e5e7eb;">
                  
                  <!-- Date Column (Fixed Width & Centered) -->
                  <div class="cc-matrix-date-col" style="width:120px; flex-shrink:0; padding:8px; background:#f9fafb; border-right:1px solid #e5e7eb; font-weight:bold; color:#374151; font-size:12px; display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center;">
                      {{ day.label }}
                      <div class="text-[10px] text-gray-500 font-normal mt-1">{{ week.label }}</div>
                  </div>

                  <!-- Unit Columns -->
                  <div v-for="unit in visibleUnits" :key="unit" class="cc-matrix-cell" ref="monthlyCellRefs" :data-date="day.date" :data-unit="unit" :style="{ flex:1, borderRight:'1px solid #e5e7eb', padding:'4px', minHeight:'60px', display:'flex', flexDirection:'column', gap:'4px' }">
                      
                      <!-- Items for this Day/Unit -->
                      <div 
                          v-for="entry in getItemsForDay(day.date, unit)" 
                          :key="entry.uniqueKey"
                          class="cc-card cc-card-mini"
                          :data-name="entry.name"
                          :data-item-name="entry.itemName"
                          :data-color="entry.color"
                          :data-planning-sheet="entry.planningSheet"
                          :data-unit="unit"
                          :data-date="day.date"
                          @click="openForm(entry.planningSheet)"
                      >
                          <div class="cc-card-left" style="width: 100%;">
                              <div class="cc-color-swatch-mini" :style="{ backgroundColor: getHexColor(entry.color) }"></div>
                              <div class="cc-card-info" style="display:flex; flex-direction:column; justify-content:center; width: 100%;">
                                  <div class="cc-card-color-name text-xs truncate font-bold" style="line-height:1.2;">{{ entry.color }}</div>
                                  <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                                      <div style="display:flex; flex-direction:column; max-width:65%;">
                                          <div class="text-[10px] text-gray-800 truncate" style="line-height:1.1;" :title="entry.customer">
                                              <b>{{ entry.partyCode || entry.customer }}</b>
                                          </div>
                                          <div class="text-[9px] text-gray-500 truncate" style="line-height:1.1; display:flex; align-items:center; gap:3px;">
                                              <span>{{ entry.quality }}</span>
                                              <span v-if="entry.has_wo" style="font-size:8px; padding:0px 3px; background:#dcfce7; color:#166534; border-radius:2px; font-weight:bold;" title="Work Order Created">WO</span>
                                              <span v-else-if="entry.has_pp" style="font-size:8px; padding:0px 3px; background:#dbeafe; color:#1e40af; border-radius:2px; font-weight:bold;" title="Production Plan Created">PP</span>
                                              <span v-else style="font-size:8px; padding:0px 3px; background:#fef3c7; color:#92400e; border-radius:2px; font-weight:bold;" title="Planning Sheet">PS</span>
                                          </div>
                                      </div>
                                      <div class="text-[10px] font-bold text-gray-700" style="white-space:nowrap;">
                                          {{ formatWeight(entry.qty / 1000) }}
                                      </div>
                                  </div>
                              </div>
                          </div>
                      </div>
                  </div>
              </div>
          </div>
      </div>
    </div>

    <!-- Matrix Pivot View -->
    <div v-if="viewMode === 'matrix'" class="cc-matrix-container" :key="renderKey">
        <div class="cc-matrix-scroll">
            <table class="cc-matrix-table">
                <thead>
                    <!-- Row 1: Order Date (Merged) -->
                    <tr>
                        <th class="matrix-sticky-col">DATE</th>
                        <template v-for="(h, i) in matrixData.dateHeaders" :key="'date-' + i">
                            <th :colspan="h.span" class="text-center" style="background:#f1f5f9; border-left:1px solid #cbd5e1;">
                                {{ h.date }}
                            </th>
                        </template>
                        <th class="matrix-total-col" rowspan="9">TOTAL</th>
                    </tr>
                    <!-- Row 2: Days (Merged by Sheet) -->
                    <tr>
                        <th class="matrix-sticky-col">DAYS</th>
                        <template v-for="(sh, si) in matrixData.sheetHeaders" :key="'days-sh-'+si">
                            <th :colspan="sh.span" class="text-center font-normal" style="border-left:1px solid #cbd5e1;">
                                {{ sh.days }}
                            </th>
                        </template>
                    </tr>
                    <!-- Row 2b: Plan Name (Merged by Sheet) -->
                    <tr>
                        <th class="matrix-sticky-col">PLAN</th>
                        <template v-for="(sh, si) in matrixData.sheetHeaders" :key="'planname-sh-'+si">
                            <th :colspan="sh.span" class="text-center font-normal" style="font-size:10px; border-left:1px solid #cbd5e1; font-weight:700; color:#4338ca;">
                                {{ sh.planName }}
                            </th>
                        </template>
                    </tr>
                    <!-- Row 3: Plan Code (Merged by Sheet, Clickable) -->
                    <tr>
                        <th class="matrix-sticky-col">PLAN CODE</th>
                        <template v-for="(sh, si) in matrixData.sheetHeaders" :key="'sheet-sh-'+si">
                            <th :colspan="sh.span" class="text-center font-normal" style="font-size:10px; border-left:1px solid #cbd5e1; font-weight:700; color:#1e40af;">
                                {{ sh.planCode && sh.planCode !== '-' ? sh.planCode : '-' }}
                            </th>
                        </template>
                    </tr>
                    <!-- Row 3b: Planning Sheet ID (Merged by Sheet, Clickable) -->
                    <tr>
                        <th class="matrix-sticky-col">PLANNING SHEET</th>
                        <template v-for="(sh, si) in matrixData.sheetHeaders" :key="'ps-sh-'+si">
                            <th :colspan="sh.span" class="text-center font-normal" style="font-size:10px; border-left:1px solid #cbd5e1;">
                                <a href="javascript:void(0)" @click.stop="openForm(sh.code)" style="color:#2563eb; text-decoration:underline; cursor:pointer; font-weight:600;">{{ sh.code }}</a>
                            </th>
                        </template>
                    </tr>
                    <!-- Row 4: Customer (Merged by Sheet) -->
                    <tr>
                        <th class="matrix-sticky-col">CUSTOMER</th>
                        <template v-for="(sh, si) in matrixData.sheetHeaders" :key="'cust2-sh-'+si">
                            <th :colspan="sh.span" class="text-center font-normal" style="font-size:10px; border-left:1px solid #cbd5e1;">
                                {{ sh.customer }}
                            </th>
                        </template>
                    </tr>
                    <!-- Row 5: Party Code (Merged by Sheet) -->
                    <tr ref="matrixHeaderRow">
                        <th class="matrix-sticky-col">CODE</th>
                        <template v-for="(sh, si) in matrixData.sheetHeaders" :key="'code-sh-'+si">
                            <th :colspan="sh.span" class="text-center matrix-col-header" style="border-left:1px solid #cbd5e1;">
                                <div class="draggable-handle" style="cursor: grab;">{{ sh.partyCode }}</div>
                            </th>
                        </template>
                    </tr>
                    <!-- Row 5: Unit (Per Column) -->
                    <tr>
                        <th class="matrix-sticky-col">UNIT</th>
                        <th v-for="col in matrixData.columns" :key="'unit-'+col.id" class="text-center font-normal" style="font-size:10px;">
                            {{ col.unit }}
                        </th>
                    </tr>
                    <!-- Row 6: GSM -->
                    <tr>
                        <th class="matrix-sticky-col">GSM TYPE</th>
                        <th v-for="col in matrixData.columns" :key="'gsm-'+col.id" class="text-center font-normal">
                            {{ col.gsm }}
                        </th>
                    </tr>
                    <!-- Row 7: Quality -->
                    <tr>
                        <th class="matrix-sticky-col">QUALITY</th>
                        <th v-for="col in matrixData.columns" :key="'qual-'+col.id" class="text-center">
                            {{ col.quality }}
                        </th>
                    </tr>
                    <!-- Row 8: Customer (Merged by Sheet, Green Header) -->
                    <tr>
                        <th class="matrix-sticky-col" style="background:#dcfce7; color:#166534;">COLOURS</th>
                        <template v-for="(sh, si) in matrixData.sheetHeaders" :key="'cust-sh-'+si">
                            <th :colspan="sh.span" class="text-center" style="background:#dcfce7; color:#166534; font-size:10px; border-left:1px solid #cbd5e1;">
                                {{ sh.customer }}
                            </th>
                        </template>
                    </tr>
                </thead>
                <tbody ref="matrixBody">
                    <tr 
                        v-for="row in matrixData.rows" 
                        :key="row.color"
                        :data-color="row.color"
                        class="matrix-row"
                    >
                        <td class="matrix-sticky-col matrix-row-header" style="cursor: grab;">
                            <div class="flex items-center">
                                <span class="w-3 h-3 rounded mr-2 border border-gray-300" :style="{backgroundColor: getHexColor(row.color)}"></span>
                                {{ row.color }}
                                <button v-if="row.anyPushed || row.isPushed" 
                                    @click.stop="revertColorGroup(row.color)"
                                    style="margin-left:8px; background: #059669; color:white; border:none; padding:3px 10px; border-radius:12px; font-size:9px; font-weight:700; cursor:pointer; box-shadow: 0 2px 4px rgba(5,150,105,0.3); transition: all 0.2s;"
                                    title="Click to revert color group back to Color Chart"
                                >
                                    ✅ {{ row.isPushed ? 'FULL' : 'PARTIAL' }} ({{ row.pushedPlanName }})
                                </button>
                                <button v-if="!row.isPushed && row.total > 0" 
                                    @click.stop="openPushColorDialog(row.color)"
                                    style="margin-left:8px; background: linear-gradient(135deg, #3b82f6, #2563eb); color:white; border:none; padding:3px 10px; border-radius:12px; font-size:10px; font-weight:700; cursor:pointer; box-shadow: 0 2px 4px rgba(37,99,235,0.3); transition: all 0.2s;"
                                    onmouseover="this.style.transform='scale(1.05)'; this.style.boxShadow='0 4px 8px rgba(37,99,235,0.4)'"
                                    onmouseout="this.style.transform='scale(1)'; this.style.boxShadow='0 2px 4px rgba(37,99,235,0.3)'"
                                >
                                    <!-- 📤 Push {{ (row.anyPushed || row.isPushed) ? 'REM' : '' }} -->
                                    📤 Push
                                </button>
                            </div>
                        </td>
                        <td 
                            v-for="col in matrixData.columns" 
                            :key="col.id" 
                            class="text-right"
                            :style="(col.id !== 'Total' && (row.cells[col.id] || 0) > 0 && !row.isPushed) ? 'cursor:pointer;' : ''"
                            @click="(col.id !== 'Total' && (row.cells[col.id] || 0) > 0 && !row.isPushed) ? openPushColorDialog(row.color, col.id) : null"
                            :title="(col.id !== 'Total' && (row.cells[col.id] || 0) > 0 && !row.isPushed) ? `Click to push orders for ${col.id}` : ''"
                            onmouseover="if(this.style.cursor==='pointer') this.style.backgroundColor='#f1f5f9';"
                            onmouseout="if(this.style.cursor==='pointer') this.style.backgroundColor='';"
                        >
                            {{ (row.cells[col.id] || 0) > 0 ? (row.cells[col.id]).toFixed(0) : '' }}
                        </td>
                        <td class="matrix-total-col text-right font-bold bg-gray-50">
                            {{ row.total.toFixed(0) }}
                        </td>
                    </tr>
                </tbody>
                <tfoot>
                    <tr>
                        <th class="matrix-sticky-col" style="background:#ffeb3b; color:#000;">TOTAL</th>
                        <th v-for="col in matrixData.columns" :key="col.id" class="text-right" style="background:#ffeb3b; color:#000;">
                            {{ matrixData.colTotals[col.id] > 0 ? matrixData.colTotals[col.id].toFixed(0) : '' }}
                        </th>
                        <th class="matrix-total-col text-right" style="background:#ffeb3b; color:#000;">{{ matrixData.grandTotal.toFixed(0) }}</th>
                    </tr>
                    <!-- Whites Section -->
                    <tr 
                        v-for="row in matrixData.whiteRows" 
                        :key="'w-' + row.color"
                        class="matrix-row"
                    >
                        <td class="matrix-sticky-col bg-white">
                            <div class="flex items-center">
                                <span class="w-3 h-3 rounded mr-2 border border-gray-300" :style="{backgroundColor: getHexColor(row.color)}"></span>
                                {{ row.color }}
                                <button v-if="row.anyPushed || row.isPushed" 
                                    @click.stop="revertColorGroup(row.color)"
                                    style="margin-left:8px; background: #16a34a; color:white; border:none; padding:3px 10px; border-radius:12px; font-size:10px; font-weight:700; cursor:pointer; box-shadow: 0 2px 4px rgba(22,163,74,0.3); transition: all 0.2s;"
                                    title="Click to revert white orders"
                                    onmouseover="this.style.opacity='0.8'"
                                    onmouseout="this.style.opacity='1'"
                                >
                                    ✅ {{ row.isPushed ? 'FULL' : 'PARTIAL' }} ({{ row.pushedPlanName || 'Default' }})
                                </button>
                            </div>
                        </td>
                        <td 
                            v-for="col in matrixData.columns" 
                            :key="'w-' + col.id" 
                            class="text-right bg-white"
                        >
                            {{ (row.cells[col.id] || 0) > 0 ? (row.cells[col.id]).toFixed(0) : '' }}
                        </td>
                        <td class="matrix-total-col text-right font-bold bg-gray-50">
                            {{ row.total.toFixed(0) }}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    </div>
    
    <!-- MIX ROLL Manual Entry Section -->
    <div v-if="viewMode === 'matrix'" class="mt-8 bg-white p-4 rounded-lg shadow border border-gray-200" style="margin-bottom: 30px;">
        <h3 class="text-sm font-bold mb-4 text-gray-800 flex items-center">
            <span class="mr-2">♻️</span> MIX ROLL AREA (Manual Entry)
        </h3>
        <table class="w-full text-left border-collapse border border-gray-200" style="font-size: 13px;">
            <thead class="bg-gray-100 text-gray-800" style="font-weight: 800;">
                <tr>
                    <th class="p-2 border" style="width: 80px;">UNIT</th>
                    <th class="p-2 border" style="width: 130px;">COLOR 1</th>
                    <th class="p-2 border" style="width: 130px;">COLOR 2</th>
                    <th class="p-2 border" style="width: 150px;">MIX NAME</th>
                    <th class="p-2 border" style="width: 120px;">QUALITY</th>
                    <th class="p-2 border" style="width: 120px;">COLOR</th>
                    <th class="p-2 border" style="width: 60px;">GSM</th>
                    <th class="p-2 border" style="width: 140px;">SHAFT DETAILS</th>
                    <th class="p-2 border" style="width: 100px;">WEIGHT (Kg)</th>
                    <th class="p-2 border" style="width: 80px; text-align: center;">RECYCLE</th>
                    <th class="p-2 border" style="width: 120px; text-align: center;">ACTIONS</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="(mix, idx) in mixRolls" :key="idx" class="border-b hover:bg-gray-50" :style="mix.isRecycle ? 'background-color: #fef3c7;' : ''">
                    <td class="p-2 border font-bold text-gray-700 text-center">{{ mix.unit }}</td>
                    <!-- COLOR 1 with background badge -->
                    <td class="p-2 border">
                        <span class="mix-color-badge" :style="getMixColorBadgeStyle(mix.color1)">{{ mix.color1 }}</span>
                    </td>
                    <!-- COLOR 2 with background badge -->
                    <td class="p-2 border">
                        <span class="mix-color-badge" :style="getMixColorBadgeStyle(mix.color2)">{{ mix.color2 }}</span>
                    </td>
                    <!-- RECYCLE row: merge MIX NAME + QUALITY + COLOR + GSM + SHAFT + WEIGHT into one cell -->
                    <template v-if="mix.isRecycle">
                        <td class="p-2 border text-center font-bold" colspan="6" style="background: #fef3c7; font-size: 15px; letter-spacing: 2px; color: #92400e;">
                            ♻️ RECYCLE
                        </td>
                    </template>
                    <!-- Normal row: show all fields -->
                    <template v-else>
                        <td class="p-2 border">
                            <input type="text" class="w-full border p-1 rounded outline-none focus:border-blue-500 font-bold uppercase text-gray-800" style="font-size: 12px;" v-model="mix.mixName" :disabled="mix._submitted" @input="debouncedSaveMixRolls()" />
                            <!-- CODE display removed as per instruction -->
                            <!-- <div v-if="mix.item_code" class="text-[9px] text-blue-600 mt-1 font-mono break-all">
                                <b>CODE:</b> {{ mix.item_code }}
                                <div class="text-gray-500 font-sans uppercase">{{ mix.item_name }}</div>
                            </div> -->
                        </td>
                        <td class="p-2 border">
                            <select class="w-full border p-1 rounded font-bold text-gray-700" style="font-size: 12px;" v-model="mix.quality" :disabled="mix._submitted" @change="debouncedSaveMixRolls()">
                                <option value="Virgin Mix">Virgin Mix</option>
                                <option value="Eco Mix">Eco Mix</option>
                                <option value="Deluxe Mix">Deluxe Mix</option>
                            </select>
                        </td>
                        <td class="p-2 border">
                            <select class="w-full border p-1 rounded font-bold text-gray-700" style="font-size: 12px;" v-model="mix.clType" :disabled="mix._submitted" @change="debouncedSaveMixRolls()">
                                <option value="Color Mix">Color Mix</option>
                                <option value="Beige Mix">Beige Mix</option>
                                <option value="White Mix">White Mix</option>
                                <option value="Black Mix">Black Mix</option>
                            </select>
                        </td>
                        <td class="p-2 border">
                            <input type="text" class="w-full border p-1 rounded outline-none focus:border-blue-500 text-center font-bold text-gray-700" style="font-size: 12px;" v-model="mix.gsm" :disabled="mix._submitted" @input="debouncedSaveMixRolls()" />
                        </td>
                        <td class="p-2 border">
                            <input type="text" class="w-full border p-1 rounded outline-none focus:border-blue-500 text-center font-bold text-gray-700" style="font-size: 12px;" placeholder="32 + 30..." v-model="mix.shaft" :disabled="mix._submitted" @input="debouncedSaveMixRolls()" />
                        </td>
                        <td class="p-2 border text-center">
                        <input 
                            type="number" 
                            class="w-full border p-1 rounded outline-none focus:border-blue-500 text-right font-mono font-bold" 
                            style="font-size: 12px;" 
                            placeholder="0.0" 
                            v-model="mix.kg" 
                            :disabled="mix._submitted"
                            @input="debouncedSaveMixRolls()" 
                        />
                        </td>
                    </template>
                    <td class="p-2 border text-center">
                        <button 
                            @click="toggleRecycle(mix)"
                            :class="mix.isRecycle ? 'recycle-btn-active' : 'recycle-btn'"
                            :title="mix.isRecycle ? 'Click to undo Recycle' : 'Click to mark as Recycle'"
                        >
                            {{ mix.isRecycle ? '♻️ YES' : '⬜ No' }}
                        </button>
                    </td>
                    <td class="p-2 border text-center" style="white-space:nowrap;">
                        <div v-if="!mix.isRecycle" class="flex flex-col gap-1">
                            <button @click="createMixItem(mix)" 
                                    class="px-2 py-1 rounded text-[10px] font-bold text-white transition-all" 
                                    :disabled="mix._submitted"
                                    :style="(mix._submitted || !mix.gsm || !mix.shaft) ? 'background-color: #a5b4fc; cursor: not-allowed;' : 'background-color: #4f46e5; cursor: pointer;'">
                                {{ mix.item_code ? 'UPDATE ITEMS' : 'CREATE ITEMS' }}
                            </button>
                            <button @click="createMixStockEntry(mix)" 
                                    class="px-2 py-1 rounded text-[10px] font-bold text-white transition-all shadow-sm" 
                                    :style="(mix._submitted) ? 'background-color: #64748b; cursor: pointer;' : (mix.spr_name ? 'background-color: #3b82f6;' : 'background-color: #059669;')">
                                {{ mix._submitted ? 'SUBMITTED (OPEN)' : (mix.spr_name ? 'OPEN SPR' : 'STOCK ENTRY') }}
                            </button>
                        </div>
                        <div class="flex gap-1 justify-center mt-1">
                            <button @click="revertMixRow(idx)" title="Revert to auto-generated values" style="background:#f0f9ff;border:1px solid #7dd3fc;color:#0369a1;padding:2px 6px;border-radius:4px;font-size:11px;cursor:pointer;">↺</button>
                            <button @click="deleteMixRow(idx)" title="Delete this row" style="background:#fff1f2;border:1px solid #fca5a5;color:#dc2626;padding:2px 6px;border-radius:4px;font-size:11px;cursor:pointer;">✕</button>
                        </div>
                    </td>
                </tr>
            </tbody>
        </table>
        <div style="margin-top:8px; display:flex; gap:8px;">
            <button @click="addMixRow()" style="background:#f0fdf4;border:1px solid #86efac;color:#15803d;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:700;cursor:pointer;">+ Add Row</button>
            <button @click="rebuildMixRolls()" style="background:#f0f9ff;border:1px solid #7dd3fc;color:#0369a1;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:700;cursor:pointer;">🔄 Rebuild Auto</button>
        </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch, reactive } from "vue";
import Sortable from "sortablejs";

// Color groups for keyword-based matching
// Check MOST SPECIFIC (multi-word) first, then SINGLE-WORD catch-all groups
const COLOR_GROUPS = [
  // ── 1. WHITES (Priority 0) ───────────────────────────────────
  { keywords: ["BRIGHT WHITE", "SUNSHINE WHITE", "MILKY WHITE", "SUPER WHITE",
               "BLEACH WHITE", "OPTICAL WHITE"], priority: 0, hex: "#FFFFFF" },
  { keywords: ["WHITE"], priority: 0, hex: "#FFFFFF" },

  // ── 2. BABY PINK (Priority 1) ───────────────────────────────────
  { keywords: ["BABY PINK"], priority: 1, hex: "#FFB6C1" },

  // ── 3. MEDICAL BLUE (Priority 2) ───────────────────────────────────
  { keywords: ["MEDICAL BLUE"],          priority: 2, hex: "#0096FF" },

  // ── 4. MEDICAL GREEN (Priority 3) ───────────────────────────────────
  { keywords: ["MEDICAL GREEN"],         priority: 3, hex: "#00A36C" },

  // ── 5. IVORY / CREAM / OFF WHITE (Priority 4) ──────────────────
  { keywords: ["BRIGHT IVORY", "IVORY", "OFF WHITE", "CREAM"], priority: 4, hex: "#FFFFF0" },

  // ── 6. YELLOWS (Priority 5-6): Lemon → Yellow → Golden
  { keywords: ["LEMON YELLOW"],          priority: 5, hex: "#FFF44F" },
  { keywords: ["GOLDEN YELLOW", "GOLD"], priority: 6, hex: "#FFD700" },
  { keywords: ["YELLOW"],                priority: 5, hex: "#FFEA00" },

  // ── 7. ORANGES (Priority 7)
  { keywords: ["LIGHT ORANGE", "PEACH", "BRIGHT ORANGE", "ORANGE"], priority: 7, hex: "#FF8C00" },

  // ── 8. PINKS (Priority 8)
  { keywords: ["DARK PINK"],             priority: 8, hex: "#C71585" },
  { keywords: ["PINK", "PINK 1.0", "PINK 2.0", "PINK 3.0", "PINK 5.0", "HOT PINK"], priority: 8, hex: "#FFC0CB" },

  // ── 9. REDS / MAROONS (Priority 9)
  { keywords: ["BRIGHT RED", "SCARLET", "CRIMSON", "RED"],  priority: 9, hex: "#D32F2F" },
  { keywords: ["MAROON", "BURGUNDY", "DARK RED"],  priority: 9, hex: "#800000" },

  // ── 10. BLUES (Priority 10-12): Peacock → Royal → Navy
  { keywords: ["LIGHT PEACOCK BLUE", "PEACOCK BLUE"], priority: 10, hex: "#008B8B" },
  { keywords: ["SKY BLUE", "LIGHT BLUE"], priority: 11, hex: "#87CEEB" },
  { keywords: ["ROYAL BLUE", "BLUE"], priority: 11, hex: "#2962FF" },
  { keywords: ["NAVY BLUE", "DARK BLUE"], priority: 12, hex: "#1A237E" },

  // ── 11. VIOLET / PURPLE (Priority 13)
  { keywords: ["VIOLET", "VOILET", "PURPLE"], priority: 13, hex: "#8B00FF" },

  // ── 12. GREENS (Priority 14-17): Reliance / Parrot / Sea / Army
  { keywords: ["GREEN 1.0 MINT", "MEDICAL GREEN"], priority: 14, hex: "#00897B" },
  { keywords: ["PARROT GREEN", "RELIANCE GREEN", "GREEN"], priority: 15, hex: "#228B22" },
  { keywords: ["SEA GREEN"],             priority: 16, hex: "#2E8B57" },
  { keywords: ["ARMY GREEN", "ARMY"],    priority: 17, hex: "#4B5320" },

  // ── 13. GREYS / SILVERS (Priority 18)
  { keywords: ["SILVER", "LIGHT GREY", "GREY", "GRAY", "DARK GREY"], priority: 18, hex: "#808080" },

  // ── 14. BROWNS (Priority 19)
  { keywords: ["BROWN", "CHOCOLATE"], priority: 19, hex: "#8B4513" },

  // ── 15. BLACK (Priority 20)
  { keywords: ["BLACK"],                 priority: 20, hex: "#000000" },

  // ── 16. BEIGES (Priority 21-22) ── Transition Rule: Run last to recover machine
  { keywords: ["DARK BEIGE"], priority: 21, hex: "#C2B280" },
  { keywords: ["LIGHT BEIGE", "BEIGE"], priority: 22, hex: "#F5F5DC" },

  // ── MIX MARKERS (priority 199) ──
  { keywords: ["WHITE MIX", "BLACK MIX", "COLOR MIX", "BEIGE MIX"], priority: 199, hex: "#c0c0c0" },
  { keywords: ["NO COLOR"], priority: 999, hex: "#e5e7eb" },
];

const GAP_THRESHOLD = 0; // any color priority difference triggers mix roll

const units = ["Unit 1", "Unit 2", "Unit 3", "Unit 4", "UNASSIGNED"];
const UNIT_TONNAGE_LIMITS = { "Unit 1": 4.4, "Unit 2": 12, "Unit 3": 9, "Unit 4": 5.5, "UNASSIGNED": 999 };
const headerColors = { "Unit 1": "#3b82f6", "Unit 2": "#10b981", "Unit 3": "#f59e0b", "Unit 4": "#8b5cf6", "UNASSIGNED": "#64748b" };

const filterOrderDate = ref(frappe.datetime.get_today());
const viewScope = ref('weekly');
const filterWeek = ref("");
const filterMonth = ref(frappe.datetime.get_today().substring(0, 7));
const filterPartyCode = ref("");
const filterCustomer = ref("");
const filterUnit = ref("");
const hasRecentlyReset = ref(false);
const filterStatus = ref("");
const selectedPlan = ref("Default");

// Merge mode state
const mergeMode = ref(false);
const merges = ref([]);  // Stores all active merges for the current view
const mergedItemsMap = ref({});  // Map of item_name -> merge_id
const selectedForMerge = ref(new Set());  // Set of selected item names

// Flatpickr ref
const datePickerInput = ref(null);
let flatpickrInstance = ref(null);

const isCurrentPlanLocked = computed(() => {
  const plan = plans.value.find(p => p.name === selectedPlan.value);
  return plan ? !!plan.locked : false;
});

function initFlatpickr() {
    if (!datePickerInput.value) return;
    
    // Check if flatpickr library is loaded
    if (typeof flatpickr === 'undefined') {
        // Library not loaded yet, try loading it
        frappe.require('https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.js', () => {
            nextTick(() => initFlatpickr());
        });
        return;
    }
    
    // Destroy existing instance if any
    if (flatpickrInstance.value) {
        flatpickrInstance.value.destroy();
    }
    
    flatpickrInstance.value = flatpickr(datePickerInput.value, {
        mode: "multiple",
        dateFormat: "Y-m-d",
        defaultDate: filterOrderDate.value ? filterOrderDate.value.split(',').map(d => d.trim()) : "today",
        onChange: function(selectedDates, dateStr, instance) {
            filterOrderDate.value = dateStr;
            // updateUrlParams is called via watcher on filterOrderDate
        }
    });
}

async function togglePlanLock() {
    if (!selectedPlan.value) return;
    const p = plans.value.find(p => p.name === selectedPlan.value);
    if (!p) return;
    
    const newLock = p.locked ? 0 : 1;
    try {
        await frappe.call({
            method: "production_scheduler.api.toggle_plan_lock",
            args: { plan_type: "color_chart", name: selectedPlan.value, locked: newLock }
        });
        p.locked = newLock;
        frappe.show_alert({ message: newLock ? `Plan '${selectedPlan.value}' Locked` : `Plan '${selectedPlan.value}' Unlocked`, indicator: 'green' });
    } catch(e) { console.error("Error toggling lock", e); }
}
const plans = ref(["Default"]);

// Compute current month prefix for plan filtering
const currentMonthPrefix = computed(() => {
    const monthNames = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"];
    if (viewScope.value === 'monthly' && filterMonth.value) {
        const [y, m] = filterMonth.value.split("-");
        return `${monthNames[parseInt(m)-1]} ${y.slice(2)}`;
    } else if (viewScope.value === 'daily' && filterOrderDate.value) {
        const d = new Date(filterOrderDate.value.split(",")[0].trim());
        if (!isNaN(d)) return `${monthNames[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`;
    } else if (viewScope.value === 'weekly' && filterWeek.value) {
        const parts = filterWeek.value.split("-W");
        if (parts.length === 2) {
            const y = parseInt(parts[0]);
            const w = parseInt(parts[1]);
            const simple = new Date(y, 0, 1 + (w - 1) * 7);
            const dow = simple.getDay();
            const ISOweekStart = simple;
            if (dow <= 4) ISOweekStart.setDate(simple.getDate() - simple.getDay() + 1);
            else ISOweekStart.setDate(simple.getDate() + 8 - simple.getDay());
            
            return `${monthNames[ISOweekStart.getMonth()]} W${w} ${String(ISOweekStart.getFullYear()).slice(2)}`;
        }
    }
    const now = new Date();
    return `${monthNames[now.getMonth()]} ${String(now.getFullYear()).slice(2)}`;
});

const selectedPlanLabel = computed(() => {
    if (!selectedPlan.value || selectedPlan.value === 'Default') return 'Default';
    return currentMonthPrefix.value + ' ' + selectedPlan.value;
});

function isRowAlreadyPushed(d) {
    const c = (d.color || '').toUpperCase().trim();
    const isWhite = ["WHITE", "BRIGHT WHITE", "SUNSHINE WHITE", "MILKY WHITE", "SUPER WHITE", "BLEACH WHITE", "BLEACH WHITE 1.0", "BLEACH WHITE 2.0"].includes(c);
    if (isWhite) return true;

    const pb = (d.pbPlanName || d.custom_pb_plan_name || '').toString().trim();
    return !!pb;
}

function stripPlanPrefix(name) {
    if (!name) return '';
    let s = String(name).trim();
    // Pattern 1: MARCH W10 26 PLAN 1
    s = s.replace(/^(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+W\d+\s+\d{2}\s+/i, '');
    // Pattern 2: MAR-26 PLAN 1
    s = s.replace(/^[A-Z]{3}-\d{2}\s+/i, '');
    // Pattern 3: MARCH 26 PLAN 1
    s = s.replace(/^(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{2}\s+/i, '');
    return s.trim();
}

function isPlanSelected(planName) {
    const selected = (selectedPlan.value || 'Default').trim();
    const plan = (planName || 'Default').trim();

    if (selected === 'Default') {
        // Treat empty/legacy-default-like values as Default bucket.
        return !plan || plan === 'Default' || stripPlanPrefix(plan) === 'Default';
    }

    return stripPlanPrefix(plan) === stripPlanPrefix(selected);
}

// Only show plans that belong to the current month (or have no month prefix like "Default")
// All plans are now global "slots" and visible regardless of month
const visiblePlans = computed(() => {
    return plans.value;
});

// Calculate the frontend viewing Plan Code (e.g., 26CU1-PLAN 1)
const derivedPlanCode = computed(() => {
    if (!selectedPlan.value || selectedPlan.value === 'Default') return '';
    
    // Calculate Date
    let d = new Date();
    if (viewScope.value === 'daily' && filterOrderDate.value) {
        d = new Date(filterOrderDate.value.split(",")[0].trim());
    } else if (viewScope.value === 'monthly' && filterMonth.value) {
        const [y, m] = filterMonth.value.split("-");
        d = new Date(y, parseInt(m)-1, 1);
    } else if (viewScope.value === 'weekly' && filterWeek.value) {
        const parts = filterWeek.value.split("-W");
        if (parts.length === 2) {
            const y = parseInt(parts[0]);
            const w = parseInt(parts[1]);
            const simple = new Date(y, 0, 1 + (w - 1) * 7);
            const dow = simple.getDay();
            d = simple;
            if (dow <= 4) d.setDate(simple.getDate() - simple.getDay() + 1);
            else d.setDate(simple.getDate() + 8 - simple.getDay());
        }
    }
    
    if (isNaN(d)) return '';
    
    const yy = String(d.getFullYear()).slice(-2);
    const monthLetters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"];
    const monthChar = monthLetters[d.getMonth()] || "X";
    
    let uCode = "";
    if (filterUnit.value === "Unit 1") uCode = "U1";
    else if (filterUnit.value === "Unit 2") uCode = "U2";
    else if (filterUnit.value === "Unit 3") uCode = "U3";
    else if (filterUnit.value === "Unit 4") uCode = "U4";
    else return "";

    
    // Strip Month/Week prefix (e.g., "MARCH W10 26 PLAN 1" -> "PLAN 1" or "Mar-26 PLAN 1" -> "PLAN 1")
    // Uses specific month-name patterns to avoid stripping words like "PLAN"
    let cleanPlan = selectedPlan.value;
    // Pattern 1: MARCH W10 26 ... (full month + week + year)
    cleanPlan = cleanPlan.replace(/^(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+W\d+\s+\d{2}\s+/i, '');
    // Pattern 2: MAR-26 ... (short month-year)
    cleanPlan = cleanPlan.replace(/^[A-Z]{3}-\d{2}\s+/i, '');
    // Pattern 3: MARCH 26 ... (full month + year, no week)
    cleanPlan = cleanPlan.replace(/^(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{2}\s+/i, '');
    
    return `${yy}${monthChar}${uCode}-${cleanPlan}`;
});

// Per-unit sort configuration
const unitSortConfig = ref({});
// Pre-initialize for all units
units.forEach(u => {
    unitSortConfig.value[u] = { mode: 'auto', color: 'asc', gsm: 'desc', priority: 'color' };
});
const viewMode = ref('matrix'); // 'kanban' | 'matrix'
const sequenceStatuses = ref({}); // { "Unit 1": "Draft", ... }
const currentUserRoles = computed(() => frappe.boot.user.roles || []);
const isAdmin = computed(() => {
    const roles = currentUserRoles.value;
    return roles.includes('System Manager') || roles.includes('Administrator');
});
const canAccessDashboard = computed(() => {
    const roles = currentUserRoles.value;
    return isAdmin.value || roles.includes('Manufacturing Manager');
});
const rawData = ref([]);
const maintenanceRecords = ref([]);
const maintenanceData = reactive({});

const columnRefs = ref(null);
const monthlyCellRefs = ref(null);
const matrixHeaderRow = ref(null); // Ref for Matrix Column sorting
const matrixBody = ref(null);      // Ref for Matrix Row sorting
const customRowOrder = ref([]);    // Store user-defined row order (List of Colors)

async function fetchMaintenanceRecords() {
	try {
		const res = await frappe.call({
			method: "production_scheduler.api.get_all_equipment_maintenance"
		});
		if (res.message) {
			maintenanceRecords.value = res.message;
			// Map by date and unit for quick lookup
			maintenanceData.value = {};
			res.message.forEach(rec => {
				const startD = new Date(rec.start_date);
				const endD = new Date(rec.end_date);
				// FIX: Properly iterate through date range
				for (let d = new Date(startD); d.getTime() <= endD.getTime(); d.setDate(d.getDate() + 1)) {
					const dateStr = d.toISOString().split('T')[0];
					if (!maintenanceData.value[dateStr]) maintenanceData.value[dateStr] = {};
					if (!maintenanceData.value[dateStr][rec.unit]) maintenanceData.value[dateStr][rec.unit] = [];
					maintenanceData.value[dateStr][rec.unit].push({
						type: rec.maintenance_type,
						start: rec.start_date,
						end: rec.end_date,
						status: rec.status
					});
				}
			});
			console.log("✅ Maintenance records loaded:", maintenanceData.value);
		}
	} catch (e) {
		console.error("❌ Failed to fetch maintenance records", e);
	}
}

function getMaintenanceForDateAndUnit(date, unit) {
	if (!date || !unit) return null;
	try {
		const dateStr = typeof date === 'string' ? date.split('T')[0] : new Date(date).toISOString().split('T')[0];
		const data = maintenanceData.value[dateStr];
		if (!data) return null;
		return data[unit] || null;
	} catch (e) {
		console.error("Error getting maintenance data:", e);
		return null;
	}
}

async function syncAllPlanCodes() {
    frappe.confirm(
        'This will recalculate and sync Plan Codes for ALL existing Planning Sheets. It may take a few moments. Continue?',
        async () => {
            frappe.show_alert({ message: "Syncing Plan Codes...", indicator: "blue" });
            try {
                const res = await frappe.call({
                    method: "production_scheduler.api.recalculate_all_plan_codes"
                });
                if (res.message && res.message.status === "success") {
                    frappe.show_alert({ message: `Successfully synced plan codes for ${res.message.count} sheets`, indicator: "green" });
                    await fetchData(); // Refresh current view
                } else {
                    frappe.msgprint("Sync completed but returned unexpected status.");
                }
            } catch (e) {
                console.error(e);
                frappe.msgprint("Error syncing plan codes. Check console for details.");
            }
        }
    );
}

const renderKey = ref(0); // Force re-render for drag revert
const matrixSortableInstances = []; // Track matrix sortable instances for cleanup
const kanbanSortableInstances = [];
const monthlySortableInstances = [];
let matrixInitTimer = null; // Track pending matrix sortable init timeout

// Matrix View Helpers
const matrixData = computed(() => {
    const emptyResult = { dateHeaders: [], sheetHeaders: [], columns: [], rows: [], whiteRows: [], colTotals: {}, grandTotal: 0, whiteColTotals: {}, whiteGrandTotal: 0 };
    if (viewMode.value !== 'matrix') return emptyResult;
    
    // We need Whites in the matrix view, but separated.
    // baseData = only the selected plan's items (for columns)
    const baseData = rawData.value.filter(d => {
        // ---- PLAN FILTER (columns show only selected plan) ----
        if (!isPlanSelected(d.planName)) return false;

        // UNIT FILTER
        if (filterUnit.value && (d.unit || "UNASSIGNED").toUpperCase() !== filterUnit.value.toUpperCase()) return false;
        
        // STATUS FILTER
        if (filterStatus.value && d.planningStatus !== filterStatus.value) return false;

        // PARTY CODE FILTER
        if (filterPartyCode.value) {
            const search = filterPartyCode.value.toLowerCase();
            const pCode = (d.partyCode || "").toLowerCase();
            if (!pCode.includes(search)) return false;
        }
        // CUSTOMER FILTER
        if (filterCustomer.value) {
            const search = filterCustomer.value.toLowerCase();
            const cust = (d.customer || "").toLowerCase();
            if (!cust.includes(search)) return false;
        }

        // Hide NO COLOR completely
        const colorUpper = (d.color || "").toUpperCase();
        if (colorUpper === "NO COLOR") return false;

        return true;
    });

    const groups = {};
    
    baseData.forEach(d => {
        const sheetCode = d.planningSheet || "Unassigned";
        const gsm = d.gsm || "-";
        const quality = d.quality || "-";
        const unit = d.unit || "Mixed";
        // Backend returns the plan code as 'planCode' key
        const planCode = d.planCode || "-";
        const compositeKey = `${sheetCode}|${unit}|${planCode}|${gsm}|${quality}`;
        
        if (!groups[compositeKey]) {
            groups[compositeKey] = {
                id: compositeKey,
                date: d.ordered_date || d.order_date || "", // Date
                days: 0,
                code: sheetCode,
                partyCode: d.partyCode || d.customer || "",
                gsm: gsm,
                quality: quality,
                customer: d.customer || d.partyCode || "",
                unit: unit,
                planCode: planCode,
                planName: d.planName || "Default",
                items: [],
                idxSum: 0 
            };
            
            // Calculate Days
            if (d.dod) {
               const d1 = new Date(d.dod);
               const today = new Date();
               const diffTime = d1 - today; 
               const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
               groups[compositeKey].days = diffDays + " DAYS";
            } else if (groups[compositeKey].date) {
               const d1 = new Date(groups[compositeKey].date);
               const today = new Date();
               const diffTime = today - d1;
               const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24)); 
               groups[compositeKey].days = diffDays + " DAYS";
            }
        }
        groups[compositeKey].items.push(d);
    });

    // Sort Groups (Columns) by Date then Code
    const sortedGroups = Object.values(groups).sort((a, b) => {
        if (a.date !== b.date) return new Date(a.date) - new Date(b.date);
        return a.code.localeCompare(b.code);
    });

    // 2. Prepare Rows (Unique Colors and Whites)
    // ✅ FIX: Filter by selected plan before building color legend
    // This prevents deleted plans' colors from appearing as orphan rows with no data
    const allColors = new Set();
    const allWhites = new Set();
    
    rawData.value.filter(d => {
        // Apply same plan filter as baseData (columns)
        if (!isPlanSelected(d.planName)) return false;
        return true;
    }).forEach(d => {
        if (!d.color) return;
        const colorUpper = d.color.toUpperCase();
        
        // Skip NO COLOR for legend
        if (colorUpper === "NO COLOR") return;

        let isWhite = isExcludedWhite(d.color);
        
        if (isWhite) allWhites.add(d.color);
        else allColors.add(d.color);
    });
    
    // Always sort by Light to Dark default (ignore manual customRowOrder as per user request for strict sorting)
    let sortedColors = Array.from(allColors).sort((a,b) => compareColor({color: a}, {color: b}, 'asc'));

    const rows = sortedColors.map(color => {
        return { color: color, cells: {}, total: 0 };
    });
    
    // Sort whites
    const sortedWhites = Array.from(allWhites).sort((a,b) => compareColor({color: a}, {color: b}, 'asc'));
    const whiteRows = sortedWhites.map(color => {
        return { color: color, cells: {}, total: 0 };
    });

    const processRows = (rowArray) => {
        rowArray.forEach(row => {
            const isItemWhite = isExcludedWhite(row.color);
            let pushedPlanNames = new Set();
            let anyPushed = false;
            let hasItems = false;
            let totalItems = 0;
            let pushedItems = 0;
            
            sortedGroups.forEach(group => {
                const matchs = group.items.filter(i => i.color === row.color);
                matchs.forEach(m => {
                    hasItems = true;
                    totalItems++;
                    // Non-white: only "pushed" if it has plannedDate (manually pushed from Color Chart)
                    // White: always considered "on the board" (auto-placed)
                    let pushedForThisItem = isItemWhite ? true : (!!m.plannedDate && m.plannedDate !== "");

                    if (pushedForThisItem) {
                        anyPushed = true;
                        pushedItems++;
                        const pDate = m.plannedDate || m.custom_item_planned_date || (isItemWhite ? 'Board' : '');
                        if (pDate) pushedPlanNames.add(pDate);
                    }
                });
                
                const sumQty = matchs.reduce((sum, item) => sum + (item.qty || 0), 0);
                if (sumQty > 0) {
                    row.cells[group.id] = sumQty;
                    row.total += sumQty;
                }
            });
            
            row.anyPushed = anyPushed;
            row.isPushed = (hasItems && totalItems > 0 && totalItems === pushedItems);
            row.pushedPlanName = Array.from(pushedPlanNames).join(', ') || 'Pushed';
        });
    };
    
    processRows(rows);
    processRows(whiteRows);
    
    // Group Columns by DATE for Merged Header
    const dateHeaders = [];
    let lastDate = null;
    let currentSpan = 0;
    
    sortedGroups.forEach((g, index) => {
         const d = g.date;
         if (d !== lastDate) {
             if (lastDate !== null) {
                 dateHeaders.push({ date: lastDate, span: currentSpan });
             }
             lastDate = d;
             currentSpan = 1;
         } else {
             currentSpan++;
         }
         
         if (index === sortedGroups.length - 1) {
             dateHeaders.push({ date: lastDate, span: currentSpan });
         }
    });

    // Group Columns by Planning Sheet for Merged Headers (DAYS, SHEET, CODE, COLOURS)
    const sheetHeaders = [];
    let lastSheetCode = null;
    let sheetSpan = 0;
    let sheetData = null;

    sortedGroups.forEach((g, index) => {
        // Use the individual sheet code as the group key to separate different orders
        const groupKey = g.code; 
        
        if (groupKey !== lastSheetCode) {
            if (lastSheetCode !== null) {
                sheetHeaders.push(sheetData);
            }
            lastSheetCode = groupKey;
            sheetSpan = 1;
            sheetData = { code: g.code, planCode: g.planCode, planName: g.planName, partyCode: g.partyCode, days: g.days, customer: g.customer, span: 1 };
        } else {
            sheetSpan++;
            sheetData.span = sheetSpan;
        }
        if (index === sortedGroups.length - 1) {
            sheetHeaders.push(sheetData);
        }
    });

    // Column Totals (Main Colors Only)
    const colTotals = {};
    sortedGroups.forEach(g => {
        colTotals[g.id] = rows.reduce((sum, r) => sum + (r.cells[g.id] || 0), 0);
    });
    const grandTotal = rows.reduce((sum, r) => sum + r.total, 0);
    
    // Column Totals (Whites Only)
    const whiteColTotals = {};
    sortedGroups.forEach(g => {
        whiteColTotals[g.id] = whiteRows.reduce((sum, r) => sum + (r.cells[g.id] || 0), 0);
    });
    const whiteGrandTotal = whiteRows.reduce((sum, r) => sum + r.total, 0);

    return {
        dateHeaders,
        sheetHeaders,
        columns: sortedGroups,
        rows,
        whiteRows,
        colTotals,
        grandTotal,
        whiteColTotals,
        whiteGrandTotal
    };
});

const canPushToBoard = computed(() => {
    if (!matrixData.value || !matrixData.value.rows) return false;
    // Show global push if at least one COLOR row (non-white) has items and isn't fully pushed
    return matrixData.value.rows.some(r => !r.isPushed && r.total > 0);
});

const visibleUnits = computed(() =>
  filterUnit.value ? units.filter((u) => u === filterUnit.value) : units
);

const EXCLUDED_WHITES = [
  "WHITE", "BRIGHT WHITE", "SUNSHINE WHITE", "MILKY WHITE", 
  "SUPER WHITE", "BLEACH WHITE", "BLEACH WHITE 1.0", "BLEACH WHITE 2.0"
];

function isExcludedWhite(color) {
    if (!color) return false;
    const cUpper = String(color).toUpperCase();
    // Keep Ivory/Cream explicitly
    if (cUpper.includes("IVORY") || cUpper.includes("CREAM") || cUpper.includes("OFF WHITE")) return false;
    return EXCLUDED_WHITES.some(ex => cUpper.includes(ex));
}

// As per user request: "APART FROM THIS U CAN BRING ALL COLOR IVORY"
// So IVORY, CREAM, OFF WHITE are kept.

// Filter data by party code and status
const filteredData = computed(() => {
  let data = rawData.value;
  
  // Step 1: Normalize unit, exclude specific whites
  data = data.filter(d => {
      if (!d.unit) d.unit = "UNASSIGNED";

      const colorUpper = (d.color || "").toUpperCase();
      
      // Use helper to exclude specific whites
      if (isExcludedWhite(d.color)) return false;

      // Hide "NO COLOR" items visually (User request: "dont show here")
      // They remain in rawData so capacity calculation remains accurate.
      if (colorUpper === "NO COLOR") return false;

      return true;
  });

  if (filterPartyCode.value) {
    const search = filterPartyCode.value.toLowerCase();
    data = data.filter((d) =>
      (d.partyCode || "").toLowerCase().includes(search)
    );
  }
  if (filterCustomer.value) {
    const search = filterCustomer.value.toLowerCase();
    data = data.filter((d) =>
      (d.customer || "").toLowerCase().includes(search)
    );
  }
  if (filterUnit.value) {
    data = data.filter((d) => (d.unit || "").toUpperCase() === (filterUnit.value || "").toUpperCase());
  }
  if (filterStatus.value) {
    data = data.filter((d) => d.planningStatus === filterStatus.value);
  }
  
  if (selectedPlan.value && selectedPlan.value !== "Default") {
      data = data.filter((d) => isPlanSelected(d.planName));
  } else {
      data = data.filter((d) => isPlanSelected(d.planName));
  }

  return data;
});

// ═══════════════════════════════════════════════════════════════════════
// MIX ROLL — with backend persistence
// ═══════════════════════════════════════════════════════════════════════
const mixRolls = ref([]);
let _mixSaveTimeout = null;

// Unique key for the current date context (daily / weekly / monthly)
function getMixRollDateKey() {
    let base = 'day-' + (filterOrderDate.value || 'none');
    if (viewScope.value === 'monthly') base = 'month-' + (filterMonth.value || 'none');
    else if (viewScope.value === 'weekly') base = 'week-' + (filterWeek.value || 'none');
    
    // Ensure separate persistence per plan
    const planStr = (selectedPlan.value && selectedPlan.value !== 'Default') ? `-${selectedPlan.value}` : '';
    return base + planStr;
}

// Build mix rolls from current filteredData
function _buildRawMixRolls() {
    let data = filteredData.value || [];
    const results = [];
    const unitsList = visibleUnits.value;

    function sortUnitItems(items) {
        return items.sort((a, b) => {
            const pA = a.color ? getGroupPriority(a.color) : 999;
            const pB = b.color ? getGroupPriority(b.color) : 999;
            if (pA !== pB) return pA - pB;
            const gsmA = parseFloat(a.gsm) || 0;
            const gsmB = parseFloat(b.gsm) || 0;
            if (gsmA !== gsmB) return gsmB - gsmA;
            return (a.idx || 0) - (b.idx || 0);
        });
    }

    unitsList.forEach(unit => {
        let uItems = data.filter(d => (d.unit || "UNASSIGNED") === unit);
        if (uItems.length === 0) return;
        uItems = sortUnitItems(uItems);

        for (let i = 0; i < uItems.length - 1; i++) {
            const cur = uItems[i];
            const next = uItems[i+1];
            if ((cur.color || "").toUpperCase() !== (next.color || "").toUpperCase()) {
                let mixName = "RECYCLE";
                const q = (cur.quality || "").toUpperCase();
                if (q && q !== "RECYCLE") mixName = `GPKL - ${q} MIX`;
                else if (!q) mixName = "COLOURMIX";

                const quality = (q.includes("ECO") || q.includes("ECO SPECIAL")) ? "Eco Mix" : q.includes("DELUXE") ? "Deluxe Mix" : "Virgin Mix";
                const clType = getMixColorType(cur.color, next.color);

                results.push({
                    unit: unit,
                    color1: (cur.color || "").toUpperCase(),
                    color2: (next.color || "").toUpperCase(),
                    mixName: mixName,
                    quality: quality,
                    clType: clType,
                    gsm: cur.gsm || next.gsm || "",
                    shaft: "",
                    kg: "",
                    item_code: "",
                    item_name: "",
                    isRecycle: false,
                    _prevMixName: mixName
                });
            }
        }
    });
    return results;
}

// Generate a unique key for each mix roll row: unit|color1|color2
function _mixKey(m) {
    return `${m.unit}|${m.color1}|${m.color2}`;
}

// Rebuild mix rolls and merge saved state from backend
async function rebuildMixRolls() {
    const raw = _buildRawMixRolls();
    const dateKey = getMixRollDateKey();

    // Load saved state from backend
    let saved = [];
    try {
        const r = await frappe.call({
            method: "production_scheduler.api.get_mix_roll_data",
            args: { date_key: dateKey },
            async: true
        });
        saved = r.message || [];
    } catch(e) {
        console.warn("Could not load saved mix roll data:", e);
    }

    // Build a lookup from saved entries
    const savedMap = {};
    saved.forEach(s => {
        const key = _mixKey(s);
        savedMap[key] = s;
    });

    // Merge: for each computed row, if a saved entry exists, overlay its editable fields
    const merged = raw.map(row => {
        const key = _mixKey(row);
        const s = savedMap[key];
        if (s) {
            row.mixName = s.isRecycle ? "RECYCLE" : (s.mixName || row.mixName);
            row.quality = s.quality || row.quality || "Virgin Mix";
            row.clType = s.clType || row.clType || "Color Mix";
            row.gsm = s.gsm || row.gsm;
            row.shaft = s.shaft || "";
            row.kg = s.kg || "";
            row.item_code = s.item_code || "";
            row.item_name = s.item_name || "";
            row.isRecycle = !!s.isRecycle;
            row._prevMixName = s._prevMixName || row._prevMixName;
            row.spr_name = s.spr_name || "";
            row._submitted = !!s._submitted;
            row.mix_id = s.mix_id || "mix-" + Math.random().toString(36).substring(2, 9);
        } else {
            row.mix_id = "mix-" + Math.random().toString(36).substring(2, 9);
        }
        return row;
    });

    mixRolls.value = merged;
}

// Save current mix roll state to backend
function saveMixRolls() {
    const dateKey = getMixRollDateKey();
    const entries = mixRolls.value.map(m => ({
        unit: m.unit,
        color1: m.color1,
        color2: m.color2,
        mixName: m.mixName,
        quality: m.quality,
        clType: m.clType,
        gsm: m.gsm,
        shaft: m.shaft,
        kg: m.kg,
        item_code: m.item_code,
        item_name: m.item_name,
        isRecycle: m.isRecycle,
        _prevMixName: m._prevMixName,
        spr_name: m.spr_name,
        _submitted: m._submitted,
        mix_id: m.mix_id
    }));

    frappe.call({
        method: "production_scheduler.api.save_mix_roll_data",
        args: { date_key: dateKey, entries: JSON.stringify(entries) },
        async: true
    });
}

function debouncedSaveMixRolls() {
    if (_mixSaveTimeout) clearTimeout(_mixSaveTimeout);
    _mixSaveTimeout = setTimeout(() => saveMixRolls(), 600);
}

function toggleRecycle(mix) {
    mix.isRecycle = !mix.isRecycle;
    if (mix.isRecycle) {
        mix._prevMixName = mix.mixName;
        mix.mixName = "RECYCLE";
    } else {
        mix.mixName = mix._prevMixName || "GPKL - GOLD MIX";
    }
    saveMixRolls();
}

function deleteMixRow(idx) {
    mixRolls.value.splice(idx, 1);
    saveMixRolls();
}

function revertMixRow(idx) {
    // Rebuild auto-generated rows and restore this one from the fresh set
    const raw = _buildRawMixRolls();
    if (raw[idx]) {
        Object.assign(mixRolls.value[idx], raw[idx]);
    }
    saveMixRolls();
}

function addMixRow() {
    // Add a blank manual row at the end
    const units = [...new Set(filteredData.value.map(d => d.unit || 'Unit 1'))];
    const unit = units[0] || 'Unit 1';
    mixRolls.value.push({
        unit,
        color1: '',
        color2: '',
        mixName: 'GPKL - GOLD MIX',
        quality: 'Virgin Mix',
        clType: 'Color Mix',
        gsm: '',
        shaft: '',
        kg: 0,
        item_code: '',
        item_name: '',
        isRecycle: false,
        _prevMixName: '',
        _isManual: true,
        mix_id: "mix-" + Math.random().toString(36).substring(2, 9)
    });
    saveMixRolls();
}

function getMixColorType(c1, c2) {
    const p1 = getColorPriority(c1);
    const p2 = getColorPriority(c2);
    if (p1 <= 6 && p2 <= 6) return "White Mix";
    if (p1 === 90 && p2 === 90) return "Black Mix";
    if ((p1 >= 95 && p1 <= 96) || (p2 >= 95 && p2 <= 96)) return "Beige Mix";
    return "Color Mix";
}

async function createMixItem(mix) {
    if (!mix.gsm || !mix.shaft) {
        frappe.msgprint("Please enter GSM and Shaft Details (Widths like 32+30) to generate Items.");
        return;
    }
    
    try {
        const r = await frappe.call({
            method: "production_scheduler.api.create_mix_item",
            args: {
                quality: mix.quality,
                cl_type: mix.clType,
                gsm: mix.gsm,
                shaft: mix.shaft
            }
        });
        
        if (r.message && Array.isArray(r.message)) {
            // Store multiple codes/names as strings
            mix.item_code = r.message.map(m => m.item_code).join(", ");
            mix.item_name = r.message.map(m => m.item_name).join(" | ");
            frappe.show_alert({ message: `✅ Generated ${r.message.length} Item(s)`, indicator: 'green' });
            saveMixRolls();
        }
    } catch (e) {
        console.error("Item Creation failed", e);
        frappe.msgprint("Failed to create Item(s). Check Error Log.");
    }
}

async function createMixStockEntry(mix) {
    // If SPR already exists, just redirect to it
    if (mix.spr_name) {
        frappe.set_route('Form', 'Shaft Production Run', mix.spr_name);
        return;
    }
    
    // Legacy support for direct stock entry
    if (mix.stock_entry) {
        frappe.set_route('Form', 'Stock Entry', mix.stock_entry);
        return;
    }

    if (mix._submitted) {
        frappe.msgprint("This entry is already submitted but no linked document was found.");
        return;
    }

    if (!mix.item_code) {
        frappe.msgprint("Please ensure Items are created (Click CREATE/UPDATE ITEMS) before Stock Entry.");
        return;
    }
    
    if (!mix.gsm || !mix.shaft) {
        frappe.msgprint("Please ensure GSM and Combination (Shaft) are filled before creating SPR.");
        return;
    }
    
    frappe.confirm(`Create a <b>Shaft Production Run</b> for <b>${mix.item_code}</b>? This will redirect you to finalize roll entries.`, async () => {
        try {
            const dateKey = getMixRollDateKey();
            // Ensure cl_type is present for the API
            const mixDataPayload = { ...mix, cl_type: mix.cl_type || mix.clType };
            
            // We pass the single mix as an array for the API
            const r = await frappe.call({
                method: "production_scheduler.api.create_mix_spr",
                args: {
                    date_key: dateKey,
                    mix_data: [mixDataPayload]
                }
            });
            
            if (r.message) {
                // Instantly update local state to reflect the link
                mix.spr_name = r.message;
                
                frappe.show_alert({
                    message: `✅ Shaft Production Run Created: ${r.message}. Redirecting...`,
                    indicator: 'green'
                }, 3);
                
                // Redirect to the new form
                frappe.set_route('Form', 'Shaft Production Run', r.message);
                saveMixRolls();
            }
        } catch (e) {
             console.error("SPR Creation failed", e);
             frappe.msgprint("Failed to create Shaft Production Run. Check Error Log.");
        }
    });
}

async function createMixWO(mix) {
    if (mix._submitted) {
        frappe.msgprint("This row has already been submitted and cannot be modified.");
        return;
    }
    createMixStockEntry(mix);
}

// Watch filteredData changes → rebuild mix rolls with saved state
watch(filteredData, () => {
    rebuildMixRolls();
}, { deep: false });

// Returns inline style for color badge with background color + contrasting text
function getMixColorBadgeStyle(colorName) {
    const upper = (colorName || "").toUpperCase().trim();
    // Find matching color group from COLOR_GROUPS
    let hex = "#e5e7eb"; // default gray
    for (const group of COLOR_GROUPS) {
        for (const keyword of group.keywords) {
            if (upper.includes(keyword)) {
                hex = group.hex;
                break;
            }
        }
        if (hex !== "#e5e7eb") break;
    }
    // Calculate luminance to pick text color (white on dark, black on light)
    const r = parseInt(hex.slice(1,3), 16);
    const g = parseInt(hex.slice(3,5), 16);
    const b = parseInt(hex.slice(5,7), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    const textColor = luminance > 0.55 ? "#1a1a1a" : "#ffffff";
    return {
        backgroundColor: hex,
        color: textColor,
        padding: "3px 8px",
        borderRadius: "4px",
        fontWeight: "700",
        fontSize: "12px",
        display: "inline-block",
        border: "1px solid rgba(0,0,0,0.15)",
        textShadow: luminance > 0.55 ? "none" : "0 1px 2px rgba(0,0,0,0.3)"
    };
}

function clearFilters() {
  filterOrderDate.value = frappe.datetime.get_today();
  filterPartyCode.value = "";
  filterCustomer.value = "";
  filterUnit.value = "";
  filterStatus.value = "";
  selectedPlan.value = "Default";
  mergeMode.value = false;
  selectedForMerge.value.clear();
  fetchData();
}

function toggleMergeMode() {
  mergeMode.value = !mergeMode.value;
  selectedForMerge.value.clear();
  if (!mergeMode.value) {
    // When disabling merge mode, reload data to show individual items again
    fetchData();
  }
}

async function loadMergeData(statusDate) {
  // Load all active merges for the current date/unit/plan.
  if (!statusDate) return;
  
  try {
    const res = await frappe.call({
      method: "production_scheduler.api.get_merges_for_date",
      args: {
        date: statusDate,
        unit: filterUnit.value || null,
        plan_name: selectedPlan.value
      }
    });
    
    if (res.message) {
      merges.value = res.message;
      
      // Build reverse lookup map
      mergedItemsMap.value = {};
      res.message.forEach(merge => {
        const items = Array.isArray(merge.merged_items) ? merge.merged_items : [];
        items.forEach(itemName => {
          mergedItemsMap.value[itemName] = merge.name;
        });
      });
    }
  } catch (e) {
    console.error("Failed to load merges:", e);
    merges.value = [];
    mergedItemsMap.value = {};
  }
}

function toggleItemSelection(itemName) {
  if (selectedForMerge.value.has(itemName)) {
    selectedForMerge.value.delete(itemName);
  } else {
    selectedForMerge.value.add(itemName);
  }
}

async function createMergeFromSelection() {
  if (selectedForMerge.value.size < 2) {
    frappe.msgprint("Please select at least 2 items to merge");
    return;
  }
  
  const items = Array.from(selectedForMerge.value);
  const label = prompt("Enter merge label (e.g., 'Group A'):", `Merge ${items.length} items`);
  if (!label) return;
  
  try {
    const res = await frappe.call({
      method: "production_scheduler.api.create_merge",
      args: {
        date: filterOrderDate.value,
        unit: filterUnit.value || "Unit 1",
        plan_name: selectedPlan.value,
        item_names: JSON.stringify(items),
        merge_label: label
      }
    });
    
    if (res.message && res.message.status === "success") {
      frappe.msgprint(`Merge created successfully: ${label}`);
      selectedForMerge.value.clear();
      await loadMergeData(filterOrderDate.value);
    }
  } catch (e) {
    frappe.msgprint("Error creating merge: " + (e.message || String(e)));
    console.error(e);
  }
}

// Find matching color group by checking if color name contains any keyword
function findColorGroup(color) {
  const upper = (color || "").toUpperCase().trim();
  for (const group of COLOR_GROUPS) {
    for (const keyword of group.keywords) {
      if (upper.includes(keyword)) return group;
    }
  }
  return null;
}

function getColorPriority(color) {
  // Check custom order first (Sync with Matrix View)
  if (customRowOrder.value && customRowOrder.value.length > 0) {
      const idx = customRowOrder.value.indexOf(color);
      if (idx !== -1) {
          // Return a priority that overrides standard groups.
          // Lower number = higher priority. Standard groups are 10-99.
          return idx - 1000; 
      }
  }
  const group = findColorGroup(color);
  return group ? group.priority : 50;
}

// Pure group priority — ALWAYS uses COLOR_GROUPS only, ignores customRowOrder.
// Use this for Kanban light/dark sorting so Matrix drag order doesn't interfere.
function getGroupPriority(color) {
  const group = findColorGroup(color);
  return group ? group.priority : 50;
}

function getHexColor(color) {
  const group = findColorGroup(color);
  return group ? group.hex : "#ccc";
}

// Mix roll qty: 100 Kg increments based on color gap
// Gap 1-3: 100 Kg (close colors)
// Gap 4-7: 200 Kg
// Gap 8-11: 300 Kg
// ...every +4 gap = +100 Kg
// Gap 35 (WHITE to BLACK): ~1000 Kg (max)
function getMixRollQty(gap) {
  const baseQty = 100;
  const increment = Math.floor(gap / 4) * 100;
  const totalQty = baseQty + increment;
  return Math.min(totalQty, 1000); // Cap at 1000 Kg
}

function determineMixType(fromColor, toColor) {
  const fromGroup = findColorGroup(fromColor);
  const toGroup = findColorGroup(toColor);
  const fromPri = fromGroup ? fromGroup.priority : 50;
  const toPri = toGroup ? toGroup.priority : 50;
  if (fromPri === 1 || toPri === 1) return "WHITE MIX";
  if (fromPri === 36 || toPri === 36) return "BLACK MIX";
  const from = (fromColor || "").toUpperCase();
  const to = (toColor || "").toUpperCase();
  if (from.includes("BEIGE") || to.includes("BEIGE")) return "BEIGE MIX";
  return "COLOR MIX";
}

// Per-unit quality priorities (lower number = higher priority)
const QUALITY_PRIORITY = {
  "Unit 1": { "PREMIUM": 1, "PLATINUM": 2, "SUPERPLATINUM": 3, "GOLD": 4, "SILVER": 5 },
  "Unit 2": { 
      // Unit 2 allows ALL qualities per user request, sorted by priority
      "PREMIUM": 1, "PLATINUM": 2, "SUPERPLATINUM": 3,
      "GOLD": 4, "SILVER": 5, "BRONZE": 6, "CLASSIC": 7, "SUPERCLASSIC": 8, 
      "LIFESTYLE": 9, "ECOSPECIAL": 10, "ECOGREEN": 11, "SUPERECO": 12, "ULTRA": 13, "DELUXE": 14 
  },
  "Unit 3": { "PREMIUM": 1, "PLATINUM": 2, "SUPERPLATINUM": 3, "GOLD": 4, "SILVER": 5, "BRONZE": 6 },
    "Unit 4": { "PREMIUM": 1, "PLATINUM": 2, "GOLD": 3, "SILVER": 4, "BRONZE": 5, "CLASSIC": 6, "CRT": 6 },
};

function getQualityPriority(unit, quality) {
    const normalized = (quality || "").toUpperCase().replace(/[^A-Z0-9]+/g, "");
    const upper = normalized.startsWith("PREMIUM") ? "PREMIUM" : normalized;
  const unitMap = QUALITY_PRIORITY[unit] || {};
  return unitMap[upper] || 99; // Unknown quality = lowest priority
}

// Helper Comparators
function compareQuality(unit, a, b) {
    return getQualityPriority(unit, a.quality) - getQualityPriority(unit, b.quality);
}

function compareColor(a, b, direction) {
    // Use getGroupPriority (not getColorPriority) so Matrix customRowOrder
    // does NOT interfere with Kanban light/dark sorting
    const pA = getGroupPriority(a.color);
    const pB = getGroupPriority(b.color);
    return direction === 'asc' ? pA - pB : pB - pA;
}

function compareGsm(a, b, direction) {
    const gA = parseFloat(a.gsm || 0);
    const gB = parseFloat(b.gsm || 0);
    return direction === 'asc' ? gA - gB : gB - gA;
}

// Visually display sort state
function getSortLabel(unit) {
    const config = getUnitSortConfig(unit);
    if (config.mode === 'manual') return 'Manual Sort';
    if (config.priority === 'color') {
        return config.color === 'asc' ? 'Color (Light→Dark)' : 'Color (Dark→Light)';
    } else if (config.priority === 'gsm') {
        return config.gsm === 'desc' ? 'GSM (High→Low)' : 'GSM (Low→High)';
    }
    return 'Color Sort';
}

function getUnitTotal(unit) {
  return rawData.value
    .filter((d) => {
        if ((d.unit || "UNASSIGNED") !== unit) return false;
                const colorUpper = String(d.color || "").toUpperCase();
        if (colorUpper.includes("IVORY") || colorUpper.includes("CREAM") || colorUpper.includes("OFF WHITE")) return true;
        if (EXCLUDED_WHITES.some(ex => colorUpper.includes(ex))) return false;
        return true;
    })
    .reduce((sum, d) => sum + d.qty, 0) / 1000;
}

function getHiddenWhiteTotal(unit) {
  return rawData.value
    .filter((d) => {
        if ((d.unit || "UNASSIGNED") !== unit) return false;
                const colorUpper = String(d.color || "").toUpperCase();
        // Check if it IS an excluded white
        if (colorUpper.includes("IVORY") || colorUpper.includes("CREAM") || colorUpper.includes("OFF WHITE")) return false;
        return EXCLUDED_WHITES.some(ex => colorUpper.includes(ex));
    })
    .reduce((sum, d) => sum + d.qty, 0) / 1000;
}



function getUnitCapacityStatus(unit) {
    const total = getUnitTotal(unit);
    const limit = UNIT_TONNAGE_LIMITS[unit] || 999;
    
    // STRICT Warning (Red) if over limit
    if (total > limit) {
        return { 
            class: 'text-red-600 font-bold', 
            warning: `⚠️ Over Limit (${(total - limit).toFixed(2)}T)!` 
        };
    }
    // Warning (Orange) if near limit (within 10%)
    if (total > limit * 0.9) {
        return { 
            class: 'text-orange-600 font-bold', 
            warning: `⚠️ Near Limit` 
        };
    }
    
    return { class: 'text-gray-600', warning: '' };
}

// ... (Mix Roll functions use getUnitEntries which uses filteredData - Correct for VISUALS) ...

async function initSortable() {
  if (!columnRefs.value && !monthlyCellRefs.value) return;

  // Cancel any pending matrix init — prevents race condition
  if (matrixInitTimer !== null) {
      clearTimeout(matrixInitTimer);
      matrixInitTimer = null;
  }
  
  // Clear old kanban instances
  while (kanbanSortableInstances.length > 0) {
      try { kanbanSortableInstances.pop().destroy(); } catch(e) {}
  }
  
  // Clear old monthly instances
  while (monthlySortableInstances.length > 0) {
      try { monthlySortableInstances.pop().destroy(); } catch(e) {}
  }

  // Clear old matrix instances
  while (matrixSortableInstances.length > 0) {
      try { matrixSortableInstances.pop().destroy(); } catch(e) {}
  }

  // MATRIX VIEW
  if (viewMode.value === 'matrix') {
      matrixInitTimer = setTimeout(() => {
          matrixInitTimer = null;
          if (viewMode.value !== 'matrix') return;

          const headerRowEl = matrixHeaderRow.value;
          if (headerRowEl) {
              const colSortable = new Sortable(headerRowEl, {
                 group: 'matrix-cols',
                 animation: 150,
                 handle: '.draggable-handle',
                 draggable: '.matrix-col-header',
                 ghostClass: 'cc-ghost',
                 onEnd: async (evt) => {
                      const { newIndex, item } = evt;
                      setTimeout(async () => {
                          const allCols = Array.from(headerRowEl.querySelectorAll('.matrix-col-header'));
                          let targetDate = null;
                          const leftEl = allCols[newIndex - 1];
                          if (leftEl) targetDate = leftEl.dataset.date;
                          else {
                              const rightEl = allCols[newIndex + 1];
                              if (rightEl) targetDate = rightEl.dataset.date;
                          }
                          
                          if (targetDate) {
                              const originalDate = item.dataset.date;
                              if (originalDate === targetDate) return;
                              
                              if (confirm(`Move Order to ${targetDate}?`)) {
                                  const colId = item.dataset.id;
                                  const group = matrixData.value.columns.find(c => c.id === colId);
                                  if (group && group.items.length) {
                                      const itemNames = group.items.map(i => i.itemName);
                                      try {
                                          await frappe.call({
                                              method: "production_scheduler.api.move_orders_to_date",
                                              args: { item_names: itemNames, target_date: targetDate }
                                          });
                                          fetchData();
                                      } catch(e) { 
                                          console.error(e); 
                                          renderKey.value++; 
                                      }
                                  }
                              } else {
                                  renderKey.value++;
                                  fetchData();
                              }
                          }
                      }, 50);
                  }
              });
              matrixSortableInstances.push(colSortable);
          }

          const bodyEl = matrixBody.value;
          if (bodyEl) {
              const rowSortable = new Sortable(bodyEl, {
                  group: 'matrix-rows',
                  animation: 250,
                  handle: '.matrix-row-header',
                  draggable: '.matrix-row',
                  ghostClass: 'cc-ghost',
                  dragClass: 'cc-drag',
                  chosenClass: 'cc-chosen',
                  onEnd: (evt) => {
                      const { oldIndex, newIndex } = evt;
                      if (oldIndex === newIndex) return;
                      setTimeout(() => {
                          const rows = Array.from(bodyEl.querySelectorAll('.matrix-row'));
                          customRowOrder.value = rows.map(r => r.dataset.color);
                          frappe.call({
                              method: "production_scheduler.api.save_color_order",
                              args: { order: customRowOrder.value },
                              callback: () => frappe.show_alert("Color Order Saved", 2)
                          });
                      }, 50);
                  }
              });
              matrixSortableInstances.push(rowSortable);
          }
      }, 150);
      return; 
  }

  // MONTHLY VIEW KANBAN
  if (viewScope.value === 'monthly' && monthlyCellRefs.value) {
     monthlyCellRefs.value.forEach(cellEl => {
         if (!cellEl) return;
         const monthlySortable = new Sortable(cellEl, {
             group: "monthly-kanban",
             animation: 250,
             forceFallback: false, /* Native is smoother if optimized */
             fallbackClass: "cc-ghost",
             ghostClass: "cc-ghost",
             dragClass: "cc-drag",
             chosenClass: "cc-chosen",
             onEnd: async (evt) => {
                const { item, to, newIndex } = evt;
                const itemName = item.dataset.itemName;
                const newUnit = to.dataset.unit;
                const newDate = to.dataset.date;
                
                // Calculate "True Index" - ignore elements that aren't cards
                const siblings = Array.from(to.children);
                const cardsBefore = siblings.slice(0, newIndex).filter(el => el.classList.contains('cc-card')).length;
                const targetIdx = cardsBefore + 1; // 1-based

                setTimeout(async () => {
                    try {
                        await frappe.call({
                            method: "production_scheduler.api.update_schedule",
                            args: {
                                item_name: itemName,
                                unit: newUnit,
                                date: newDate,
                                index: targetIdx,
                                force_move: 1
                            }
                        });
                        frappe.show_alert("Order moved successfully", 2);
                        fetchData();
                    } catch (e) {
                        console.error("Failed to move order", e);
                        frappe.msgprint("Failed to move order");
                        fetchData(); 
                    }
                }, 10);
             }
         });
         monthlySortableInstances.push(monthlySortable);
         cellEl._sortable = monthlySortable;
     });
     return;
  }

  // DAILY VIEW KANBAN
  if (columnRefs.value) {
    columnRefs.value.forEach((colEl) => {
        if (!colEl) return;
        const kanbanSortable = new Sortable(colEl, {
        group: "kanban",
        animation: 250, // Smoother transition
        ghostClass: "cc-ghost",
        dragClass: "cc-drag",
        chosenClass: "cc-chosen",
        forceFallback: false,
        fallbackTolerance: 3, 
        onEnd: async (evt) => {
            const { item, to, from, newIndex, oldIndex } = evt;
            const itemName = item.dataset.itemName;
            const newUnit = to.dataset.unit;
            const oldUnit = from.dataset.unit;
            const isSameUnit = (to === from);
            if (!itemName || !newUnit) return;

            if (!isSameUnit || newIndex !== oldIndex) {
                 // Calculate "True Index" - ignore mix markers
                 const siblings = Array.from(to.children);
                 const cardsBefore = siblings.slice(0, newIndex).filter(el => el.classList.contains('cc-card')).length;
                 const targetIdx = cardsBefore + 1; // 1-based

                 setTimeout(async () => {
                 try {
                    const performMove = async (force=0, split=0) => {
                        return await frappe.call({
                            method: "production_scheduler.api.update_schedule",
                            args: {
                                item_name: itemName, 
                                unit: newUnit,
                                date: filterOrderDate.value,
                                index: targetIdx,
                                force_move: force,
                                perform_split: split,
                                plan_name: selectedPlan.value
                            }
                        });
                    };

                    let res = await performMove();
                    
                    // Switch both units to manual sort mode so they respect the new idx sequence
                    getUnitSortConfig(newUnit).mode = 'manual';
                    if (!isSameUnit) getUnitSortConfig(oldUnit).mode = 'manual';
                    
                    // Persist the full sequence to Color Sequence Approval
                    await persistSequence(newUnit);
                    if (!isSameUnit) await persistSequence(oldUnit);
                    
                    if (res.message && res.message.status === 'overflow') {
                         const showOverflowDialog = (overflowData, moveDate, moveUnit) => {
                             const avail = overflowData.available;
                             const limit = overflowData.limit;
                             const current = overflowData.current_load;
                             const orderWt = overflowData.order_weight;
                             const extraMsg = overflowData.message || '';
                             
                             const d = new frappe.ui.Dialog({
                                title: '⚠️ Capacity Full',
                                fields: [{
                                     fieldtype: 'HTML', fieldname: 'msg',
                                     options: `<div style="text-align:center; padding:10px;">
                                         <p class="text-lg font-bold text-red-600">Unit Capacity Exceeded!</p>
                                         ${extraMsg ? `<p style="color:#b45309; font-weight:600; margin-bottom:8px;">${extraMsg}</p>` : ''}
                                         <p>Unit Limit: <b>${limit}T</b> | Current: <b>${current.toFixed(2)}T</b></p>
                                         <p>Your Order: <b>${orderWt.toFixed(2)}T</b></p>
                                         <p class="mt-2 text-green-600 font-bold">Available Space: ${avail.toFixed(3)}T</p>
                                     </div>`
                                }],
                                primary_action_label: '🧠 Smart Move',
                                primary_action: async () => {
                                    d.hide();
                                    const res2 = await frappe.call({
                                        method: "production_scheduler.api.update_schedule",
                                        args: { item_name: itemName, unit: moveUnit, date: moveDate, index: targetIdx, force_move: 1, plan_name: selectedPlan.value }
                                    });
                                    if (res2.message && res2.message.status === 'success') {
                                        const dest = res2.message.moved_to;
                                        frappe.show_alert(`Placed in ${dest.unit} (${dest.date})`, 5);
                                    }
                                    fetchData();
                                },
                                secondary_action_label: 'Cancel',
                                secondary_action: () => { d.hide(); renderKey.value++; }
                             });
                             
                             // Move to Next Day button (strict — same unit, next day)
                             d.add_custom_action('📅 Next Day', async () => {
                                 d.hide();
                                 const res3 = await frappe.call({
                                     method: "production_scheduler.api.update_schedule",
                                     args: { item_name: itemName, unit: moveUnit, date: moveDate, index: 0, strict_next_day: 1 }
                                 });
                                 if (res3.message && res3.message.status === 'overflow') {
                                     // Next day also full — show dialog again for that date
                                     showOverflowDialog(res3.message, res3.message.target_date, res3.message.target_unit);
                                 } else if (res3.message && res3.message.status === 'success') {
                                     const dest = res3.message.moved_to;
                                     frappe.show_alert(`Moved to ${dest.unit} on ${dest.date}`, 5);
                                     fetchData();
                                 }
                             }, 'btn-info');
                             
                             // Split & Distribute button
                             d.add_custom_action('Split & Distribute', async () => {
                                 d.hide();
                                 if (avail < 0.1) {
                                     frappe.msgprint("Space too small to split.");
                                     renderKey.value++; return;
                                 }
                                 const res3 = await performMove(0, 1);
                                 handleMoveSuccess(res3, newUnit);
                             }, 'btn-warning');
                             d.show();
                         };
                         
                         showOverflowDialog(res.message, filterOrderDate.value, newUnit);
                    } else {
                         // Fix 3: Re-fetch data instead of silent splice for same-unit resequence
                         if (isSameUnit && res.message && res.message.status === 'success') {
                             frappe.show_alert({ message: "Order resequenced", indicator: "green" });
                             unitSortConfig.value[newUnit].mode = 'manual';
                             // Re-fetch to get correct order from server
                             fetchData();
                         } else {
                             handleMoveSuccess(res, newUnit);
                         }
                    }
                 } catch (e) {
                     console.error(e);
                     frappe.msgprint("❌ Move Failed");
                     renderKey.value++;
                 }
                 }, 50);
            }
        },
        });
        kanbanSortableInstances.push(kanbanSortable);
        colEl._sortable = kanbanSortable;
    });
  }
}

async function handleMoveSuccess(res, newUnit) {
    if (res.message && res.message.status === 'success') {
        const movedTo = res.message.moved_to || { unit: newUnit, date: filterOrderDate.value };
        if (movedTo.date !== filterOrderDate.value) {
             frappe.msgprint(`Moved to ${movedTo.date}`);
        } else if (movedTo.unit !== newUnit) {
             frappe.msgprint(`Placed in ${movedTo.unit} (Capacity Full in ${newUnit})`);
        } else {
             frappe.show_alert({ message: "Moved successfully", indicator: "green" });
        }
        unitSortConfig.value[movedTo.unit].mode = 'manual';
        await fetchData(); 
    }
}

function getUnitSortConfig(unit) {
  if (!unitSortConfig.value[unit]) {
    unitSortConfig.value[unit] = { mode: 'auto', color: 'asc', gsm: 'desc', priority: 'color' };
  }
  return unitSortConfig.value[unit];
}

function toggleUnitColor(unit) {
  const config = getUnitSortConfig(unit);
  config.mode = 'auto'; 
  if (config.priority !== 'color') {
      config.priority = 'color';
      config.color = 'asc';
  } else {
      config.color = config.color === 'asc' ? 'desc' : 'asc';
  }
  renderKey.value++; // Force re-render so cards re-sort immediately
}

function toggleUnitGsm(unit) {
  const config = getUnitSortConfig(unit);
  config.mode = 'auto';
  if (config.priority !== 'gsm') {
      config.priority = 'gsm';
      config.gsm = 'asc';
  } else {
      config.gsm = config.gsm === 'asc' ? 'desc' : 'asc';
  }
  renderKey.value++; // Force re-render so cards re-sort immediately
}

// ---- MONTHLY VIEW HELPERS ----


const weeks = computed(() => {
    try {
        if (viewScope.value !== 'monthly' || !filterMonth.value) return [];
        
        // Strict 7-Day Logic (User Request: "Accurate Date")
        // Week 1: Day 1-7
        // Week 2: Day 8-14
        // Week 3: Day 15-21
        // Week 4: Day 22-28
        // Week 5: Day 29-End
        
        let year, month;
        if (filterMonth.value.includes('-')) {
             [year, month] = filterMonth.value.split('-').map(Number);
        } else { return []; }

        const lastDayOfMonth = new Date(year, month, 0).getDate();
        const weekList = [];
        
        const ranges = [
            { start: 1, end: 7 },
            { start: 8, end: 14 },
            { start: 15, end: 21 },
            { start: 22, end: 28 },
            { start: 29, end: lastDayOfMonth }
        ];

        ranges.forEach((range, idx) => {
            if (range.start > lastDayOfMonth) return;
            
            const effectiveEnd = Math.min(range.end, lastDayOfMonth);
            
            // Format Dates YYYY-MM-DD
            const startStr = `${year}-${String(month).padStart(2, '0')}-${String(range.start).padStart(2, '0')}`;
            const endStr = `${year}-${String(month).padStart(2, '0')}-${String(effectiveEnd).padStart(2, '0')}`;
            
            const MONTH_ABBRS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
            const monthAbbr = MONTH_ABBRS[month-1];
            
            weekList.push({
                id: `w-${idx+1}-${startStr}`,
                label: `Week ${idx+1}`,
                dateRange: `${range.start} ${monthAbbr} - ${effectiveEnd} ${monthAbbr}`,
                startDay: range.start,
                endDay: effectiveEnd,
                start: startStr,
                end: endStr
            });
        });
        
        return weekList;
    } catch (e) {
        console.error("Error computing weeks:", e);
        return [];
    }
});

function showGlobalSortInfo() {
    // Build Color Order List
    const colorOrder = COLOR_GROUPS
        .map(g => {
             // Use first keyword as label
             const label = g.keywords[0];
             return { label, priority: g.priority };
        })
        .sort((a,b) => a.priority - b.priority)
        .map(g => `<li style="font-size:11px; margin-bottom:2px;">${g.priority}. <b>${g.label}</b></li>`)
        .join("");

    const d = new frappe.ui.Dialog({
        title: `🎨 Global Sort & Mix Rules`,
        fields: [{
            fieldtype: 'HTML',
            fieldname: 'info',
            options: `
                <div style="padding:10px;">
                    <div style="margin-bottom:15px; padding:8px; background:#f3f4f6; border-radius:4px;">
                        <p style="font-weight:bold; margin-bottom:4px;">Global Sorting Strategy</p>
                        <p>All views enforce <b>Light → Dark</b> and <b>Low → High GSM</b> sorting by default.</p>
                    </div>
                    
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                        <div>
                            <p style="font-weight:bold; border-bottom:1px solid #ddd; margin-bottom:5px;">Color Sequence (Light→Dark)</p>
                            <ul style="list-style:none; padding:0; height:200px; overflow-y:auto; border:1px solid #eee;">
                                ${colorOrder}
                            </ul>
                        </div>
                        <div>
                            <p style="font-weight:bold; border-bottom:1px solid #ddd; margin-bottom:5px;">Mixing Rules</p>
                            <div style="font-size:11px;">
                                <p><b>Gap Calculation:</b> Difference in Color Priority.</p>
                                <ul style="list-style:disc; padding-left:15px; margin-top:5px;">
                                    <li>Gap 0 (Same Color): <b>0 Kg</b></li>
                                    <li>Gap 1-5 (Similar): <b>10 Kg</b></li>
                                    <li>Gap > 20 (Contrast): <b>50 Kg+</b></li>
                                </ul>
                                <p style="margin-top:8px; font-style:italic; color:#666;">
                                    *High gaps create significant waste. Try to group similar colors!
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            `
        }]
    });
    d.show();
}

function showSortInfo(unit) {
    const config = getUnitSortConfig(unit);
    const isColor = config.priority === 'color';
    const direction = isColor ? config.color : config.gsm;
    
// Build Color Order List (Corrected Iteration)
    const colorOrder = COLOR_GROUPS
        .map(g => {
             // Use first keyword as label
             const label = g.keywords[0];
             return { label, priority: g.priority };
        })
        .sort((a,b) => a.priority - b.priority)
        .map(g => `<li style="font-size:11px; margin-bottom:2px;">${g.priority}. <b>${g.label}</b></li>`)
        .join("");

    const d = new frappe.ui.Dialog({
        title: `ℹ️ Sort & Mix Rules: ${unit}`,
        fields: [{
            fieldtype: 'HTML',
            fieldname: 'info',
            options: `
                <div style="padding:10px;">
                    <div style="margin-bottom:15px; padding:8px; background:#f3f4f6; border-radius:4px;">
                        <p style="font-weight:bold; margin-bottom:4px;">Current Strategy:</p>
                        <p>Priority: <b>${isColor ? 'Color' : 'GSM'}</b></p>
                        <p>Direction: <b>${direction === 'asc' ? (isColor ? 'Light → Dark' : 'Low → High') : (isColor ? 'Dark → Light' : 'High → Low')}</b></p>
                    </div>
                    
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                        <div>
                            <p style="font-weight:bold; border-bottom:1px solid #ddd; margin-bottom:5px;">Color Sequence (Light→Dark)</p>
                            <ul style="list-style:none; padding:0; height:200px; overflow-y:auto; border:1px solid #eee;">
                                ${colorOrder}
                            </ul>
                        </div>
                        <div>
                            <p style="font-weight:bold; border-bottom:1px solid #ddd; margin-bottom:5px;">Mixing Rules</p>
                            <div style="font-size:11px;">
                                <p><b>Gap Calculation:</b> Difference in Color Priority.</p>
                                <ul style="list-style:disc; padding-left:15px; margin-top:5px;">
                                    <li>Gap 0 (Same Color): <b>0 Kg</b></li>
                                    <li>Gap 1-5 (Similar): <b>10 Kg</b></li>
                                    <li>Gap > 20 (Contrast): <b>50 Kg+</b></li>
                                </ul>
                                <p style="margin-top:8px; font-style:italic; color:#666;">
                                    *High gaps create significant waste. Try to group similar colors!
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            `
        }]
    });
    d.show();
}

function getMonthlyCellTotal(week, unit) {
    try {
        const entries = getMonthlyCellEntries(week, unit);
        const total = entries.reduce((sum, e) => sum + (parseFloat(e.qty) || 0), 0);
        return (total / 1000).toFixed(2);
    } catch (e) {
        return "0.00";
    }
}

function getMonthlyCellDays(week, unit) {
    if (!week || !week.start || !week.end) return [];
    if (!filteredData.value) return [];

    try {
        // Filter by Unit
        let items = filteredData.value.filter(d => (d.unit || "Mixed") === unit);
        
        // Filter by Date Range
        items = items.filter(d => d.orderDate >= week.start && d.orderDate <= week.end);

        // Group by Date
        const itemsByDate = {};
        items.forEach(item => {
            const d = item.orderDate;
            if (!itemsByDate[d]) itemsByDate[d] = [];
            itemsByDate[d].push(item);
        });

        // Create Day Objects (Sorted Chronologically)
        const days = Object.keys(itemsByDate).sort().map(dateStr => {
           let dayItems = itemsByDate[dateStr];
           
           // Sort Items within Day (Light -> Dark)
           // Use existing logic for priority
           const config = getUnitSortConfig(unit);
           dayItems.sort((a, b) => {
                  let diff = 0;
                  if (config.priority === 'color') {
                      diff = compareColor(a, b, 'asc');
                      if (diff === 0) diff = compareGsm(a, b, 'asc');
                  } else {
                      diff = compareGsm(a, b, 'asc');
                      if (diff === 0) diff = compareColor(a, b, 'asc');
                  }
                  if (diff === 0) diff = (a.idx || 0) - (b.idx || 0);
                  return diff;
           });

           // Format Date Label (e.g., "2026-02-18" -> "18 Feb")
           const [y, m, d] = dateStr.split('-');
           const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
           const label = `${parseInt(d)} ${monthNames[parseInt(m)-1]}`;

           return {
               date: dateStr,
               label: label,
               items: dayItems.map(d => ({
                   ...d,
                   type: 'order',
                   uniqueKey: d.itemName
               }))
           };
        });

        return days;
    } catch (e) {
        console.error("Error grouping monthly days:", e);
        return [];
    }
}

function getMonthlyCellEntries(week, unit) {
    if (!week || !week.start || !week.end) return [];
    if (!filteredData.value) return [];
    
    try {
        // Filter by Unit
        let items = filteredData.value.filter(d => (d.unit || "UNASSIGNED") === unit);
        
        // Filter by Date Range
        items = items.filter(d => d.orderDate >= week.start && d.orderDate <= week.end);
        
        // --- DAILY-ASCENDING SORT [DATE -> COLOR] ---
        // 1. Group by Date (Locking Principle)
        const itemsByDate = {};
        items.forEach(item => {
            const d = item.orderDate;
            if (!itemsByDate[d]) itemsByDate[d] = [];
            itemsByDate[d].push(item);
        });
        
        // 2. Sort Dates Chronologically
        const distinctDates = Object.keys(itemsByDate).sort();
        
        // 3. Sort Items within Date (Always Light -> Dark)
        let finalSortedItems = [];
        distinctDates.forEach(date => {
             const dayItems = itemsByDate[date];
             
             // ALWAYS Sort Light -> Dark (Ascending)
             // This ensures Beige (96) is at End of Day 1
             // And White/Ivory (4/5) is at Start of Day 2
             const config = getUnitSortConfig(unit);
             
             dayItems.sort((a, b) => {
                  let diff = 0;
                  if (config.priority === 'color') {
                      diff = compareColor(a, b, 'asc'); // Force ASC
                      if (diff === 0) diff = compareGsm(a, b, 'asc');
                  } else {
                      diff = compareGsm(a, b, 'asc');
                      if (diff === 0) diff = compareColor(a, b, 'asc');
                  }
                  if (diff === 0) diff = (a.idx || 0) - (b.idx || 0);
                  return diff;
             });
             
             finalSortedItems = finalSortedItems.concat(dayItems);
        });
        
        return finalSortedItems.map(d => ({
            ...d,
            type: 'order',
            uniqueKey: d.itemName
        }));
    } catch (e) {
        console.error("Error getting monthly entries:", e);
        return [];
    }
}

// --- MATRIX LAYOUT HELPERS ---
function getDaysInWeek(week) {
    if (!filterMonth.value || !week) return [];
    
    try {
        let year, month;
        if (filterMonth.value.includes('-')) {
             [year, month] = filterMonth.value.split('-').map(Number);
        } else { return []; }

        const days = [];
        
        for (let d = week.startDay; d <= week.endDay; d++) {
             // Create date string manually: YYYY-MM-DD
             const yyyy = year;
             const mm = String(month).padStart(2, '0');
             const dd = String(d).padStart(2, '0');
             const dateStr = `${yyyy}-${mm}-${dd}`;
             
             // Label: "22 Feb"
             const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
             const label = `${d} ${monthNames[month-1]}`;
             
             days.push({
                 date: dateStr,
                 label: label,
                 dayNum: d
             });
        }
        return days;
    } catch (e) {
        console.error("Error generating days:", e);
        return [];
    }
}

function getItemsForDay(dateStr, unit) {
    if (!filteredData.value) return [];
    
    try {
       // Normalize dateStr to YYYY-MM-DD
       const normalizedDateStr = dateStr ? dateStr.trim() : "";
       
       // Filter by Unit and Exact Date (with date normalization)
       let dayItems = filteredData.value.filter(d => {
           if ((d.unit || "UNASSIGNED") !== unit) return false;
           // Normalize item's orderDate for comparison
           const itemDate = (d.orderDate || "").trim();
           // Try exact match first
           if (itemDate === normalizedDateStr) return true;
           // Try matching just the date part (in case backend returns datetime)
           if (itemDate && itemDate.substring(0, 10) === normalizedDateStr) return true;
           return false;
       });
       
       // Debug: log when plan is not Default and no items found
       if (selectedPlan.value && selectedPlan.value !== 'Default' && dayItems.length === 0) {
           // Only log once per unit per day to avoid spam
           const allForUnit = filteredData.value.filter(d => (d.unit || "UNASSIGNED") === unit);
           if (allForUnit.length > 0 && !getItemsForDay._logged) {
               console.warn(`[ColorChart Debug] Plan="${selectedPlan.value}", Unit="${unit}", DateStr="${normalizedDateStr}"`,
                   `filteredData has ${allForUnit.length} items for this unit.`,
                   `Sample orderDates:`, allForUnit.slice(0, 5).map(d => d.orderDate));
               getItemsForDay._logged = true;
               setTimeout(() => { getItemsForDay._logged = false; }, 2000);
           }
       }
       
       // Force sorting to ALWAYS strictly be Light -> Dark 
       const config = getUnitSortConfig(unit);
       dayItems.sort((a, b) => {
              let diff = 0;
              if (config.priority === 'color') {
                  diff = compareColor(a, b, 'asc');
                  if (diff === 0) diff = compareGsm(a, b, 'asc');
              } else {
                  diff = compareGsm(a, b, 'asc');
                  if (diff === 0) diff = compareColor(a, b, 'asc');
              }
              if (diff === 0) diff = (a.idx || 0) - (b.idx || 0);
              return diff;
       });
       
       return dayItems.map(d => ({
           ...d,
           type: 'order',
           uniqueKey: d.itemName
       }));
    } catch (e) {
        console.error("Error fetching items for day:", e);
        return [];
    }
}

function toggleUnitPriority(unit) {
  const config = getUnitSortConfig(unit);
  config.mode = 'auto';
  config.priority = config.priority === 'color' ? 'gsm' : 'color';
  renderKey.value++; // Force re-render so cards re-sort immediately
}

function sortItems(unit, items) {
  const config = getUnitSortConfig(unit);
  if (config.mode === 'manual') {
      // If we have a saved sequence from the Color Sequence Approval DocType, use it
      if (config.savedSequence && config.savedSequence.length) {
          const seqMap = {};
          config.savedSequence.forEach((name, i) => seqMap[name] = i);
          return [...items].sort((a, b) => {
              const idxA = seqMap[a.itemName] !== undefined ? seqMap[a.itemName] : 9999 + (a.idx || 0);
              const idxB = seqMap[b.itemName] !== undefined ? seqMap[b.itemName] : 9999 + (b.idx || 0);
              return idxA - idxB;
          });
      }
      return [...items].sort((a, b) => (a.idx || 0) - (b.idx || 0));
  }
  return [...items].sort((a, b) => {
      let diff = 0;
      if (config.priority === 'color') {
          diff = compareColor(a, b, config.color);
          if (diff === 0) diff = compareGsm(a, b, config.gsm);
      } else {
          diff = compareGsm(a, b, config.gsm);
          if (diff === 0) diff = compareColor(a, b, config.color);
      }
      if (diff === 0) diff = (a.idx || 0) - (b.idx || 0);
      return diff;
  });
}

// Group data by unit, sort, and insert mix markers
function getUnitEntries(unit) {
  let unitItems = filteredData.value.filter((d) => (d.unit || "UNASSIGNED").toUpperCase() === (unit || "").toUpperCase());
  unitItems = sortItems(unit, unitItems); 

  const entries = [];
  for (let i = 0; i < unitItems.length; i++) {
    entries.push({ 
      type: "order", 
      ...unitItems[i],
      uniqueKey: unitItems[i].itemName
    });
    if (i < unitItems.length - 1) {
      const curPri = getColorPriority(unitItems[i].color);
      const nextPri = getColorPriority(unitItems[i + 1].color);
      if (curPri !== nextPri || unitItems[i].color !== unitItems[i+1].color) {
          const gap = Math.abs(curPri - nextPri);
          entries.push({
              type: "mix",
              mixType: determineMixType(unitItems[i].color, unitItems[i+1].color),
              unit: unit,
              fromColor: unitItems[i].color,
              toColor: unitItems[i+1].color,
              qty: getMixRollQty(gap),
              uniqueKey: `mix-${unitItems[i].itemName}-${unitItems[i+1].itemName}`
          });
      }
    }
  }
  return entries;
}

function getUnitProductionTotal(unit) {
  return filteredData.value
    .filter((d) => (d.unit || "UNASSIGNED").toUpperCase() === (unit || "").toUpperCase())
    .reduce((sum, d) => sum + (parseFloat(d.qty) || 0), 0) / 1000;
}

function formatWeight(tonnage) {
  // Input is in Tons
  if (tonnage >= 1) {
      // If integer (e.g. 10.00), return "10 T"
      if (Number.isInteger(tonnage)) return tonnage.toFixed(0) + " T";
      // Else return with decimals, e.g. "1.23 T" or "1.20 T"
      // User said "remove 2 digit make it whole" for 10.00 -> 10T
      // Let's use clean logic:
      return parseFloat(tonnage.toFixed(3)) + " T"; 
  } else {
      // Less than 1 Ton -> Show Kg
      // 0.469 T -> 469 Kg
      return (tonnage * 1000).toFixed(0) + " Kg";
  }
}

function getMixRollCount(unit) {
  return getUnitEntries(unit).filter((e) => e.type === "mix").length;
}

function getMixRollTotalWeight(unit) {
  return getUnitEntries(unit)
    .filter((e) => e.type === "mix")
    .reduce((sum, e) => sum + e.qty, 0);
}

function toggleDirection() {
  direction.value = direction.value === "asc" ? "desc" : "asc";
}

async function persistSequence(unit) {
    if (!filterOrderDate.value || String(filterOrderDate.value).includes(",") || viewMode.value !== 'kanban') return;
    
    // Get current item names in the column after the drop
    const items = getUnitEntries(unit).filter(e => e.type === "order");
    const itemNames = items.map(i => i.itemName);
    
    try {
        await frappe.call({
            method: "production_scheduler.api.save_color_sequence",
            args: {
                date: filterOrderDate.value,
                unit: unit,
                sequence_data: itemNames,
                plan_name: selectedPlan.value
            }
        });
        // Reset status to Draft if it was Approved but then re-ordered? 
        // Or keep it? User said "after re order drag and drop the arrangement we and approved"
        // Usually, if you re-order an approved sequence, it should probably go back to Draft.
        if (sequenceStatuses.value[unit] === 'Approved') {
            sequenceStatuses.value[unit] = 'Draft';
        }
    } catch(e) {
        console.error("Failed to persist sequence", e);
    }
}

async function requestApproval(unit) {
    if (!filterOrderDate.value || !unit) return;
    try {
        // Save sequence first
        const items = getUnitEntries(unit).map(i => i.itemName);
        await frappe.call({
            method: "production_scheduler.api.save_color_sequence",
            args: { date: filterOrderDate.value, unit: unit, sequence_data: items, plan_name: selectedPlan.value }
        });

        await frappe.call({
            method: "production_scheduler.api.request_sequence_approval",
            args: { date: filterOrderDate.value, unit: unit, plan_name: selectedPlan.value }
        });
        sequenceStatuses.value[unit] = 'Pending Approval';
        frappe.show_alert(`Approval requested for ${unit}`, 2);
    } catch(e) { console.error(e); }
}

async function approveSequence(unit) {
    if (!filterOrderDate.value || !unit) return;
    try {
        // Save sequence first
        const items = getUnitEntries(unit).map(i => i.itemName);
        await frappe.call({
            method: "production_scheduler.api.save_color_sequence",
            args: { date: filterOrderDate.value, unit: unit, sequence_data: items, plan_name: selectedPlan.value }
        });

        await frappe.call({
            method: "production_scheduler.api.approve_sequence",
            args: { date: filterOrderDate.value, unit: unit, plan_name: selectedPlan.value }
        });
        sequenceStatuses.value[unit] = 'Approved';
        frappe.show_alert(`${unit} Sequence Approved`, 2);
    } catch(e) { console.error(e); }
}

function openForm(name) {
  frappe.set_route("Form", "Planning sheet", name);
}

async function analyzePreviousFlow() {
  if (!filterOrderDate.value) return;
  try {
    const prevDateArgs = await frappe.call({
      method: "production_scheduler.api.get_previous_production_date",
      args: { date: filterOrderDate.value }
    });
    const prevDate = prevDateArgs.message;
    
    if (prevDate) {
      const r = await frappe.call({
        method: "production_scheduler.api.get_color_chart_data",
        args: { date: prevDate }
      });
      const prevData = r.message || [];
      if (prevData.length > 0) {
        // Group previous data by unit
        const prevByUnit = {};
        units.forEach(u => prevByUnit[u] = []);
        prevData.forEach(item => {
           if (prevByUnit[item.unit]) prevByUnit[item.unit].push(item);
        });

         // Analyze each unit
         units.forEach(unit => {
            const prevItems = prevByUnit[unit];
            const config = getUnitSortConfig(unit);

            if (prevItems && prevItems.length > 0) {
               // Sort yesterday's items the same way they would have been displayed
               // (by their stored idx — the actual run order saved to DB)
               const sorted = [...prevItems].sort((a, b) => (a.idx || 0) - (b.idx || 0));
               const lastItem = sorted[sorted.length - 1];
               
               // DARK/LIGHT threshold:
               // Dark = priority >= 50 (Red, Maroon, Purple, Blue, Green, Grey, Brown, Black)
               // Light = priority < 50 (White, Ivory, Yellow, Orange, Pink)
               // Use getGroupPriority — NOT getColorPriority — so Matrix customRowOrder
               // does not affect this decision
               const lastPri = getGroupPriority(lastItem.color);
               
               // Rule (as stated by user):
               // Yesterday ended LIGHT (pri < 50)  → today start LIGHT → DARK ('asc')
               // Yesterday ended DARK  (pri >= 50) → today start DARK  → LIGHT ('desc')
               if (lastPri >= 50) {
                  config.color = 'desc'; // Ended Dark  → today: Dark → Light
               } else {
                  config.color = 'asc';  // Ended Light → today: Light → Dark
               }
               config.mode = 'auto';
               config.priority = 'color';
               
               console.log(`Unit ${unit}: Yesterday last color="${lastItem.color}" (pri=${lastPri}) → today sort: ${config.color}`);
               
               // GSM Logic - Smart Gap Minimization
               const lastGsm = parseFloat(lastItem.gsm || 0);
               const todayItems = filteredData.value.filter(d => d.unit === unit);
               
               if (todayItems.length > 0) {
                   const gsms = todayItems.map(d => parseFloat(d.gsm || 0));
                   const minGsm = Math.min(...gsms);
                   const maxGsm = Math.max(...gsms);
                   
                   const gapAsc = Math.abs(lastGsm - minGsm);  // Start Low
                   const gapDesc = Math.abs(lastGsm - maxGsm); // Start High
                   
                   config.gsm = gapDesc < gapAsc ? 'desc' : 'asc';
                   console.log(`Unit ${unit} GSM: Last=${lastGsm} Min=${minGsm} Max=${maxGsm} → ${config.gsm}`);
               }
            } else {
               // No data yesterday for this unit — default to Light→Dark
               config.color = 'asc';
               config.mode = 'auto';
               config.priority = 'color';
            }
         });
        
        
        frappe.show_alert({ message: "Sort updated from previous day", indicator: "blue" }, 3);
        // Only force re-render for kanban — matrix is already reactive via rawData
        if (viewMode.value !== 'matrix') {
            renderKey.value++;
        }
      }
    }
  } catch (e) {
    console.error("Error analyzing previous flow", e);
  }
}

// View Scope Logic — only weekly and monthly
async function toggleViewScope() {
  if (viewScope.value === 'weekly') {
      viewScope.value = 'monthly';
      if (!filterMonth.value) {
          filterMonth.value = frappe.datetime.get_today().substring(0, 7);
      }
  } else {
      viewScope.value = 'weekly';
      if (!filterWeek.value) {
          const d = new Date();
          const y = d.getFullYear();
          const firstDayOfYear = new Date(y, 0, 1);
          const pastDaysOfYear = (d - firstDayOfYear) / 86400000;
          const weekNum = Math.ceil((pastDaysOfYear + firstDayOfYear.getDay() + 1) / 7);
          filterWeek.value = `${y}-W${String(weekNum).padStart(2, '0')}`;
      }
  }
  await fetchData();
}

async function fetchPlans(args) {
    const stripLegacyPrefix = (name) => {
        if (!name || name === 'Default') return name;
        // Pattern 1: MARCH W10 26 PLAN 1
        let s = name.replace(/^[A-Z]+\s+W\d+\s+\d{2}\s+/i, '');
        if (s !== name) return s.trim();
        // Pattern 2: Feb-26 PLAN 1
        s = name.replace(/^[A-Z]{3}-\d{2}\s+/i, '');
        if (s !== name) return s.trim();
        // Pattern 3: MARCH 26 PLAN 1
        s = name.replace(/^[A-Z]+\s+\d{2}\s+/i, '');
        if (s !== name) return s.trim();
        return name.trim();
    };

    try {
        const planArgs = { ...args };
        if (planArgs.date && !planArgs.start_date) {
            const [year, month] = planArgs.date.split("-");
            const lastDay = new Date(year, month, 0).getDate();
            planArgs.start_date = `${year}-${month}-01`;
            planArgs.end_date = `${year}-${month}-${lastDay}`;
            delete planArgs.date;
        }
        
        const r = await frappe.call({
            method: "production_scheduler.api.get_monthly_plans",
            args: planArgs
        });
        plans.value = r.message || [{name: "Default", locked: 0}];
        // If the currently selected plan is not returned (e.g. new plan with no sheets yet),
        // keep it in the dropdown instead of silently falling back to Default.
        const strippedSelected = stripLegacyPrefix(selectedPlan.value);
        if (selectedPlan.value && selectedPlan.value !== 'Default') {
            const found = plans.value.find(p => p.name === strippedSelected || p.name === selectedPlan.value);
            if (found) {
                // Auto-migrate selection to base name if it matched
                if (selectedPlan.value !== found.name) {
                    selectedPlan.value = found.name;
                }
            } else {
                // Insert as an unlocked empty plan so user stays on it
                plans.value.push({ name: selectedPlan.value, locked: 0 });
            }
        }
    } catch(e) { console.error("Error fetching plans", e); }
}

function createNewPlan() {
    // Determine month prefix from current view context
    const monthNames = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE","JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"];
    let monthPrefix = "";
    if (viewScope.value === 'monthly' && filterMonth.value) {
        const [y, m] = filterMonth.value.split("-");
        monthPrefix = `${monthNames[parseInt(m)-1]} ${y.slice(2)} `;
    } else if (viewScope.value === 'daily' && filterOrderDate.value) {
        const d = new Date(filterOrderDate.value.split(",")[0].trim());
        if (!isNaN(d)) monthPrefix = `${monthNames[d.getMonth()]} ${String(d.getFullYear()).slice(2)} `;
    } else if (viewScope.value === 'weekly' && filterWeek.value) {
        const parts = filterWeek.value.split("-W");
        if (parts.length === 2) {
            const y = parts[0];
            const w = parts[1];
            const simple = new Date(parseInt(y), 0, 1 + (parseInt(w) - 1) * 7);
            const dow = simple.getDay();
            const ISOweekStart = simple;
            if (dow <= 4) ISOweekStart.setDate(simple.getDate() - simple.getDay() + 1);
            else ISOweekStart.setDate(simple.getDate() + 8 - simple.getDay());
            
            monthPrefix = `${monthNames[ISOweekStart.getMonth()]} W${w} ${y.slice(2)} `;
        }
    }
    if (!monthPrefix) {
        const now = new Date();
        monthPrefix = `${monthNames[now.getMonth()]} ${String(now.getFullYear()).slice(2)} `;
    }

    frappe.prompt({
        label: 'New Plan Name',
        fieldname: 'plan_name',
        fieldtype: 'Data',
        reqd: 1,
        description: `Plan will be displayed as: <b>${currentMonthPrefix.value} [your name]</b>`
    }, async (values) => {
        const fullName = values.plan_name;
        if (!plans.value.find(p => p.name === fullName)) {
            plans.value.push({name: fullName, locked: 0});
            // Persist the new plan so it survives refresh
            frappe.call({
                method: "production_scheduler.api.add_persistent_plan",
                args: { plan_type: "color_chart", name: fullName }
            });
        }
        
        frappe.show_alert({ message: `Created new empty Plan '${fullName}'`, indicator: 'green' });
        
        selectedPlan.value = fullName;
        fetchData();
    }, 'Create New Plan Tab', 'Create');
}

function deletePlan() {
    const planName = selectedPlan.value;
    if (!planName || planName === 'Default') {
        frappe.msgprint('Cannot delete the Default plan.');
        return;
    }
    frappe.confirm(
        `Delete plan "<b>${planName}</b>"? This will permanently remove all Planning Sheets under this plan for the current ${viewScope.value === 'daily' ? 'date' : 'month'}.`,
        async () => {
            let deleteArgs = { plan_name: planName };
            if (viewScope.value === 'daily') {
                deleteArgs.date = filterOrderDate.value;
            } else {
                const [year, month] = filterMonth.value.split("-");
                const lastDay = new Date(year, month, 0).getDate();
                deleteArgs.start_date = `${year}-${month}-01`;
                deleteArgs.end_date = `${year}-${month}-${lastDay}`;
            }
            try {
                const r = await frappe.call({
                    method: "production_scheduler.api.delete_plan",
                    args: deleteArgs
                });
                const count = (r.message && r.message.deleted_count) || 0;
                frappe.show_alert({ message: `Deleted plan "${planName}" (${count} sheet${count !== 1 ? 's' : ''} removed)`, indicator: 'green' });
                // Remove from dropdown and switch to Default
                plans.value = plans.value.filter(p => p.name !== planName);
                selectedPlan.value = 'Default';
                fetchData();
            } catch (e) {
                console.error('Failed to delete plan', e);
                frappe.msgprint('Error deleting plan.');
            }
        }
    );
}

// ---- PUSH TO PRODUCTION BOARD ----
async function pushToProductionBoard() {
    // Collect all items (we will mark the pushed ones visually instead of hiding them)
    // but MUST respect the color exclusion rules for Whites and NO COLOR
    const items = (rawData.value || []).filter(d => {
        const colorUpper = (d.color || "").toUpperCase();
        if (colorUpper === "NO COLOR") return false;
        return !isExcludedWhite(d.color);
    });
    if (items.length === 0) {
        frappe.msgprint('No orders visible to push. Apply filters first.');
        return;
    }

    // Calculate global color totals to apply the 800kg rule
    const globalColorTotals = {};
    items.forEach(i => {
        if (!i.color || i.color.trim() === '') return;
        const c = i.color.trim().toUpperCase();
        globalColorTotals[c] = (globalColorTotals[c] || 0) + (parseFloat(i.qty) || 0) / 1000.0;
    });

    // Collect item names from current view
    // Collect UNIQUE item DocIDs (the real database names) from current view
    const allItemIDs = [...new Set(items.map(d => d.itemName).filter(Boolean))];

    if (allItemIDs.length === 0) {
        frappe.msgprint('No valid items to push.');
        return;
    }

    const today = frappe.datetime.get_today();
    let fetchDates = [];
    
    if (viewScope.value === 'weekly' && filterWeek.value) {
        const [yearStr, weekStr] = filterWeek.value.split("-W");
        const simple = new Date(parseInt(yearStr), 0, 1 + (parseInt(weekStr) - 1) * 7);
        const ISOweekStart = new Date(simple);
        if (simple.getDay() <= 4) ISOweekStart.setDate(simple.getDate() - simple.getDay() + 1);
        else ISOweekStart.setDate(simple.getDate() + 8 - simple.getDay());
        
        for(let i=0; i<7; i++) {
            const d = new Date(ISOweekStart);
            d.setDate(ISOweekStart.getDate() + i);
            fetchDates.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`);
        }
    } else if (viewScope.value === 'monthly' && filterMonth.value) {
        const [yearStr, monthStr] = filterMonth.value.split("-");
        const year = parseInt(yearStr);
        const month = parseInt(monthStr);
        const lastDay = new Date(year, month, 0).getDate();
        for(let i=1; i<=lastDay; i++) {
            fetchDates.push(`${yearStr}-${monthStr}-${String(i).padStart(2,'0')}`);
        }
    } else {
        fetchDates = (filterOrderDate.value || today).split(",").map(d => d.trim()).filter(Boolean);
    }
    
    const defaultTargetDate = fetchDates.length ? fetchDates[0] : today;

    // State for the dialog
    let smartSequenceActive = false;
    let masterSequence = allItemIDs.map((id, i) => {
        const d = items.find(it => it.itemName === id) || {};
        const isWhite = (col) => {
            if (!col) return false;
            const w = ["WHITE", "BRIGHT WHITE", "SUNSHINE WHITE", "MILKY WHITE", "SUPER WHITE", "BLEACH WHITE", "BLEACH WHITE 1.0", "BLEACH WHITE 2.0"];
            return w.includes(col.toString().toUpperCase().trim());
        };
        // Pushed status: Whites are auto-pushed; Colors are pushed if they have a planned_date
        const isPushed = isRowAlreadyPushed(d);
        
        const rawUnit = d.unit || '';
        const normUnit = (rawUnit.toUpperCase().replace(/\s+/g, '').includes('UNIT1')) ? 'Unit 1' :
                         (rawUnit.toUpperCase().replace(/\s+/g, '').includes('UNIT2')) ? 'Unit 2' :
                         (rawUnit.toUpperCase().replace(/\s+/g, '').includes('UNIT3')) ? 'Unit 3' :
                         (rawUnit.toUpperCase().replace(/\s+/g, '').includes('UNIT4')) ? 'Unit 4' : 'Mixed';

        return {
            name: id, // Truly unique DocID (PSI-xxxx)
            uiKey: d.name, // The Sheet-Idx key for UI reference if needed
            color: d.color || '',
            quality: d.quality || d.custom_quality || '',
            gsm: d.gsm || '',
            unit: normUnit,
            qty: d.qty || '',
            itemName: id, // Duplicate for safety in some logic paths
            description: d.description || '', // Actual item description
            customer: d.customer || '',
            partyCode: d.partyCode || '',
            partyName: d.partyName || '',
            approvalStatus: d.approvalStatus || 'Draft',
            planningSheet: d.planningSheet || '',
            plannedDate: d.planned_date || '',
            phase: '',
            is_seed_bridge: false,
            pushed: isPushed,  // true = already on board, don't show in arrangement checkboxes
            checked: !isPushed // Only unchecked if pushed
        };
    });

    // ✅ SORT: Apply the Saved Sequence from Approval Dashboard (Manager's arrangement)
    masterSequence.sort((a, b) => {
        // Group by Unit first
        const unitNorm = (u) => (u || 'Unit 1').toUpperCase().trim();
        const unitA = unitNorm(a.unit);
        const unitB = unitNorm(b.unit);
        if (unitA !== unitB) {
            const order = ['UNIT 1', 'UNIT 2', 'UNIT 3', 'UNIT 4', 'MIXED'];
            const idxA = order.indexOf(unitA);
            const idxB = order.indexOf(unitB);
            if (idxA !== -1 && idxB !== -1) return idxA - idxB;
            return unitA.localeCompare(unitB);
        }

        // Within unit, PUSHED items always come LAST
        if (a.pushed !== b.pushed) return a.pushed ? 1 : -1;

        // Within unit, use manager's saved sequence if available
        const saved = unitSortConfig.value[unitA]?.savedSequence;
        if (saved && saved.length) {
            const idxA = saved.indexOf(a.name);
            const idxB = saved.indexOf(b.name);
            
            if (idxA !== -1 && idxB !== -1) return idxA - idxB;
            if (idxA !== -1) return -1;
            if (idxB !== -1) return 1;
        }
        
        // Fallback to stable Light-to-Dark sort
        const pA = a.color ? getColorPriority(a.color) : 999;
        const pB = b.color ? getColorPriority(b.color) : 999;
        if (pA !== pB) return pA - pB;
        return (parseFloat(b.gsm) || 0) - (parseFloat(a.gsm) || 0);
    });

    // Re-assign sequence numbers based on final sorted order
    masterSequence.forEach((item, i) => { item.sequence_no = i + 1; });
    const relevantUnits = [...new Set(masterSequence.map(s => s.unit || 'Unit 1'))];
    const unitStatuses = relevantUnits.map(u => sequenceStatuses.value[u] || 'Draft');
    const overallStatus = unitStatuses.some(s => s === 'Rejected') ? 'Rejected' :
                         (unitStatuses.every(s => s === 'Approved') ? 'Approved' : 
                          (unitStatuses.some(s => s === 'Pending Approval' || s === 'Draft') ? 
                           (unitStatuses.some(s => s === 'Draft') ? 'Draft' : 'Pending Approval') : 'Approved'));

    let dialogOverallStatus = overallStatus;
    let dialogApprovalMeta = null;
    let dialogPendingUnits = [];

    const canApprove = frappe.user.has_role('Manufacturing Manager') || frappe.user.has_role('System Manager') || frappe.user.has_role('Administrator') || frappe.session.user === 'Administrator';

    // Sort initial sequence
    masterSequence.forEach((item, i) => { item.sequence_no = i + 1; });
    let currentSequence = [...masterSequence];

    function getPhaseColor(phase) {
        if (phase === 'white') return '#e8f5e9';
        if (phase === 'color') return '#fff8e1';
        return '#f5f5f5';
    }

    // Escape text for safe insertion into Frappe microtemplate HTML strings
    function esc(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;').replace(/\\/g,'&#92;');
    }

    function renderTable(seq, currentArrangementStatus = null) {
        let lastUnit = null;
        const rows = seq.map((item, i) => {
            let unitDivider = '';
            const unitNorm = (u) => (u || 'Unit 1').toUpperCase().trim();
            const currentNorm = unitNorm(item.unit);
            if (currentNorm !== lastUnit) {
                lastUnit = currentNorm;
                unitDivider = `<tr style="background:#f1f5f9;color:#1e293b;font-size:11px;font-weight:700;border-bottom:1px solid #e2e8f0;">
                    <td colspan="10" style="padding:4px 12px;display:flex;align-items:center;gap:6px;">
                        <span style="font-size:14px;">📦</span> 
                        <span style="letter-spacing:0.05em;text-transform:uppercase;">${esc(currentNorm)}</span>
                    </td>
                </tr>`;
            }
            const bridge = item.is_seed_bridge ? ' 🔗' : '';
            const isPushed = item.pushed;
            const rowBg = smartSequenceActive ? getPhaseColor(item.phase) : (isPushed ? '#f8fafc' : '#fff');
            const rowOpacity = isPushed ? '0.6' : '1';
            const checked = item.checked !== false;
            const qty_str = item.qty ? parseFloat(item.qty).toFixed(0) + ' Kg' : '—';
            
            let actionHtml = '';
            if (item.pushed) {
                actionHtml = `<span style="font-size:10px;background:#e2e8f0;color:#475569;padding:2px 6px;border-radius:4px;font-weight:bold;">Pushed</span>`;
            } else {
                actionHtml = `<input type="checkbox" data-idx="${i}" ${checked ? 'checked' : ''} style="cursor:pointer;width:16px;height:16px;accent-color:#2563eb;">`;
            }

            const dragHandle = item.pushed ? '' : `<span class="drag-handle" style="cursor:grab;color:#94a3b8;font-size:16px;padding:0 8px;user-select:none;display:flex;align-items:center;" title="Drag to reorder">⠿</span>`;
            
            const statusBadge = item.approvalStatus === 'Approved' 
                ? '<span style="color:#16a34a;background:#f0fdf4;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:700;">APPROVED</span>'
                : (item.approvalStatus === 'Pending Approval' 
                    ? '<span style="color:#ca8a04;background:#fefce8;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:700;">PENDING</span>'
                    : (item.approvalStatus === 'Rejected'
                        ? '<span style="color:#dc2626;background:#fef2f2;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:700;">REJECTED</span>'
                        : '<span style="color:#64748b;background:#f1f5f9;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:700;">DRAFT</span>'));

            const partyInfo = `
                <div style="font-size:11px;font-weight:600;color:#1e293b;">${esc(item.partyName) || '—'}</div>
                <div style="font-size:9px;color:#64748b;">${esc(item.partyCode)} | ${esc(item.customer)}</div>
            `;

            return `${unitDivider}<tr data-seq-idx="${i}" style="background:${rowBg};border-bottom:1px solid #f1f5f9;opacity:${rowOpacity};">
                <td style="padding:6px 0;text-align:center;">${dragHandle}</td>
                <td style="padding:6px;text-align:center;">
                    ${actionHtml}
                </td>
                <td style="padding:6px;font-weight:bold;color:#64748b;font-size:11px;text-align:center;">${item.sequence_no}${bridge}</td>
                <td style="padding:6px;font-size:12px;font-weight:700;color:#1e293b;">
                    <div>${esc(item.color) || '—'}</div>
                    <div style="font-size:9px;font-weight:400;color:#64748b;">${esc(item.description || item.itemName || '')}</div>
                </td>
                <td style="padding:6px;font-size:11px;color:#475569;">${esc(item.quality) || '—'}</td>
                <td style="padding:6px;font-size:11px;color:#475569;text-align:center;">${esc(item.gsm) || '—'}</td>
                <td style="padding:6px;font-size:11px;color:#475569;">${esc(item.unit) || '—'}</td>
                <td style="padding:6px;">${partyInfo}</td>
                <td style="padding:6px;text-align:center;">${statusBadge}</td>
                <td style="padding:6px;font-size:11px;text-align:right;font-weight:700;color:#1e293b;">${qty_str}</td>
            </tr>`;
        }).join('');

        return `<div style="max-height:420px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:12px;box-shadow:inset 0 2px 4px rgba(0,0,0,0.02);">
            <table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;">
                <thead style="background:#f8fafc;color:#64748b;position:sticky;top:0;z-index:2;border-bottom:2px solid #e2e8f0;">
                    <tr>
                        <th style="padding:8px 6px;width:32px;text-align:center;">☰</th>
                        <th style="padding:8px 6px;width:36px;text-align:center;"><input type="checkbox" id="mtp-check-all" style="cursor:pointer;width:16px;height:16px;accent-color:#2563eb;"></th>
                        <th style="padding:8px 6px;width:34px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;">#</th>
                        <th style="padding:8px 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;text-align:left;">Color</th>
                        <th style="padding:8px 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;text-align:left;">Quality</th>
                        <th style="padding:8px 6px;width:50px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;">GSM</th>
                        <th style="padding:8px 6px;width:60px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;text-align:left;">Unit</th>
                        <th style="padding:8px 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;text-align:left;">Party / Customer</th>
                        <th style="padding:8px 6px;width:80px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;">Status</th>
                        <th style="padding:8px 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;text-align:right;">Qty</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }

    function buildDialogHtml(seq, statusOverride = null) {
        const total = seq.filter(i => i.checked !== false).length;
        const currentStatus = statusOverride || dialogOverallStatus;
        
        // Safety check: 'd' might be accessed during his own initialization (TDZ)
        // Using window.d or var d helps, but being extra defensive here.
        let hasD = false;
        try { hasD = (!!d && !!d.get_value); } catch(e) { hasD = false; }
        
        const activeFetchDates = hasD ? (d.get_value('fetch_dates') ? d.get_value('fetch_dates').split(',').map(s => s.trim()) : []) : fetchDates;
        const activeTargetDate = hasD ? d.get_value('target_date') : defaultTargetDate;
        
        const isDateMismatch = activeTargetDate && !activeFetchDates.some(fd => fd === activeTargetDate);

        const smartSeedsHtml = (hasD && d.smartSeeds) ? `
            <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
                ${['Unit 1', 'Unit 2', 'Unit 3', 'Unit 4'].map((unit) => {
                    const normUnit = unit.toUpperCase().replace(/\s+/g, '');
                    const seed = (d.smartSeeds && (d.smartSeeds[unit] || d.smartSeeds[normUnit])) ? (d.smartSeeds[unit] || d.smartSeeds[normUnit]) : null;
                    const displayColor = (seed && seed.color && seed.color !== '0' && seed.color !== 0) ? seed.color : 'NO ORDERS';
                    return `
                    <div style="background:#f8fafc; border:1px solid #e2e8f0; padding:4px 10px; border-radius:12px; font-size:10px; display:flex; align-items:center; gap:6px;">
                        <span style="color:#64748b; font-weight:700;">${esc(unit.toUpperCase())} BOARD END:</span>
                        <span style="color:${displayColor !== 'NO ORDERS' ? '#1e293b' : '#94a3b8'}; font-weight:800;">${esc(displayColor)}</span>
                        ${(displayColor !== 'NO ORDERS' && seed.quality) ? `<span style="color:#94a3b8; font-size:9px;">(${esc(seed.quality)})</span>` : ''}
                    </div>`;
                }).join('')}
            </div>
        ` : '';

        const statusSummary = `
            <div style="display:flex;gap:12px;align-items:center; flex-wrap: wrap; width: 100%;">
                <div style="background:#f1f5f9;padding:6px 12px;border-radius:20px;display:flex;align-items:center;gap:8px;">
                    <span style="width:8px;height:8px;border-radius:50%;background:${currentStatus === 'Approved' ? '#16a34a' : (currentStatus === 'Rejected' ? '#dc2626' : (currentStatus === 'Pending Approval' ? '#ca8a04' : '#64748b'))}"></span>
                    <div style="display:flex; flex-direction:column;">
                        <span style="font-size:11px;font-weight:700;color:#1e293b;text-transform:uppercase;letter-spacing:0.02em;">Arrangement for ${activeTargetDate}: ${currentStatus}</span>
                        ${currentStatus === 'Approved' && dialogApprovalMeta ? `
                            <div style="font-size:9px; color:#16a34a; margin-top:1px;">
                                <i class="fa fa-check-circle"></i> Approved by ${dialogApprovalMeta.modified_by} on ${frappe.datetime.str_to_user(dialogApprovalMeta.modified.split(' ')[0])}
                            </div>
                        ` : (dialogPendingUnits.length > 0 ? `
                            <div style="font-size:9px; color:#ca8a04; margin-top:1px;">
                                <i class="fa fa-info-circle"></i> Pending approval: <b>${dialogPendingUnits.join(', ')}</b>
                            </div>
                        ` : '')}
                    </div>
                </div>
                ${isDateMismatch ? `
                    <div style="background:#fff7ed; border:1px solid #ffedd5; padding:4px 10px; border-radius:20px; color:#c2410c; font-size:10px; font-weight:700; display:flex; align-items:center; gap:5px;">
                        <i class="fa fa-exchange"></i> Cross-Date: ${activeFetchDates.join(",")} ➔ ${activeTargetDate}
                    </div>
                ` : ''}
                <div style="cursor:pointer; color:#2563eb; font-size:12px; margin-left: auto;" onclick="window.refreshPushStatus()" title="Refresh Status">
                    <i class="fa fa-refresh"></i>
                </div>
                <div>
                    <span style="font-size:14px;color:#1e293b;font-weight:700;"><span id="seq-count-label">${total}</span></span> <span style="font-size:11px;color:#64748b;font-weight:500;">item(s) selected</span>
                </div>
            </div>
            ${(hasD && d.arrangementMismatch) ? `
                <div style="background:#fff1f2; border:1px solid #ffe4e6; padding:8px 12px; border-radius:12px; color:#be123c; font-size:10px; font-weight:700; display:flex; align-items:center; gap:8px; margin-top:10px;">
                    <i class="fa fa-exclamation-triangle" style="font-size:14px;"></i>
                    <div>
                        <div style="text-transform:uppercase; letter-spacing:0.02em;">Data Integrity Warning</div>
                        <div style="font-weight:500; opacity:0.9; margin-top:2px;">The saved arrangement for <b>${activeTargetDate}</b> contains different items than what is shown below.</div>
                    </div>
                </div>
            ` : ''}
        `;

        return `
        <div style="margin-bottom:12px;display:flex;flex-direction:column;background:#fff;padding:4px 0;">
            <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
                ${statusSummary}
                ${smartSequenceActive ? '<span style="font-size:10px;color:#166534;background:#dcfce7;padding:5px 12px;border-radius:20px;font-weight:600;display:flex;align-items:center;gap:4px;">✨ Smart Sequenced</span>' : ''}
            </div>
            ${smartSeedsHtml}
        </div>
        ${renderTable(seq, currentStatus)}`;
    }
    async function loadGlobalCapacityPreview(dialog, seq) {
        const checkedItems = seq.filter(i => i.checked !== false && !i.pushed);
        if (!checkedItems.length) {
            dialog.set_value("global_capacity_info", `<div style="font-size:11px;color:#64748b;font-style:italic;padding:12px;text-align:center;background:#f8fafc;border-radius:8px;border:1px dashed #cbd5e1;">Select items above to see capacity footprint.</div>`);
            dialog.capacityExceeded = false;
            return;
        }

        const targetDate = (dialog.get_value('target_date') || defaultTargetDate || today).trim();
        
        let filterUnitValue = 'All Units';
        try { filterUnitValue = dialog.get_value('filter_unit') || 'All Units'; } catch(e) {}

        let capHtml = `<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap:10px; margin-top:4px;">`;
        let capacityExceeded = false;

        try {
            // Capacity preview is target-day only.
            const rData = await frappe.call({
                method: "production_scheduler.api.get_color_chart_data",
                args: { date: targetDate, plan_name: '__all__', planned_only: 1 }
            });
            const allItems = rData.message || [];
            
            // Build capacity snapshot directly from the same PB dataset used by the board.
            // This keeps push preview perfectly aligned with Production Board totals.
            const UNIT_LIMITS = { "Unit 1": 4.4, "Unit 2": 12.0, "Unit 3": 9.0, "Unit 4": 5.5 };
            const capacities = {
                "Unit 1": { total_limit: UNIT_LIMITS["Unit 1"], total_load: 0 },
                "Unit 2": { total_limit: UNIT_LIMITS["Unit 2"], total_load: 0 },
                "Unit 3": { total_limit: UNIT_LIMITS["Unit 3"], total_load: 0 },
                "Unit 4": { total_limit: UNIT_LIMITS["Unit 4"], total_load: 0 }
            };

            allItems.forEach(i => {
                const u = i.unit || "Mixed";
                if (!capacities[u]) return;
                capacities[u].total_load += (parseFloat(i.qty || 0) / 1000);
            });

            const pushLoadsByDate = {}; // (date) -> { unit -> weight }
            
            checkedItems.forEach(sel => {
                const u = sel.unit || 'Unit 1';
                const limit = UNIT_LIMITS[u] || 999;
                const itemWt = (parseFloat(sel.qty || 0) / 1000);
                
                let checkDate = targetDate;
                while (true) {
                    if (!pushLoadsByDate[checkDate]) pushLoadsByDate[checkDate] = {};
                    if (!pushLoadsByDate[checkDate][u]) {
                        // For the first time we check a date, initialize with current board load
                        const boardLoad = capacities[u] ? (checkDate === targetDate ? capacities[u].total_load : 0) : 0;
                        // Note: For days beyond targetDate, we'd ideally fetch real load, 
                        // but for preview simplicity, we'll assume they are empty or just show target day footprint.
                        pushLoadsByDate[checkDate][u] = boardLoad;
                    }
                    
                    const currentDayLoad = pushLoadsByDate[checkDate][u];
                    if (currentDayLoad + itemWt <= limit || currentDayLoad === 0) {
                        pushLoadsByDate[checkDate][u] += itemWt;
                        break;
                    }
                    // Cascade to next day
                    const dObj = new Date(checkDate);
                    dObj.setDate(dObj.getDate() + 1);
                    checkDate = dObj.toISOString().split('T')[0];
                }
            });

            const uniqueDates = Object.keys(pushLoadsByDate).sort();
            
            uniqueDates.forEach(pDate => {
                const dayLoads = pushLoadsByDate[pDate];
                Object.keys(dayLoads).forEach(u => {
                    if (filterUnitValue !== 'All Units' && u !== filterUnitValue) return;
                    
                    const limit = UNIT_LIMITS[u] || 999;
                    const totalDayLoad = dayLoads[u];
                    const isOver = totalDayLoad > limit;
                    
                    if (isOver) capacityExceeded = true;
                    
                    capHtml += `
                    <div style="padding:10px;border-radius:12px;border:1px solid ${isOver ? '#fecaca' : '#e2e8f0'};background:${isOver ? '#fef2f2' : (pDate === targetDate ? '#fff' : '#f8fafc')};box-shadow:0 1px 2px rgba(0,0,0,0.05);">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="font-weight:700;font-size:10px;color:${isOver ? '#dc2626' : '#64748b'};text-transform:uppercase;">${u} ${pDate === targetDate ? '' : '('+pDate+')'}</span>
                            <span style="font-size:12px;">${isOver ? '⚠️' : '✅'}</span>
                        </div>
                        <div style="font-size:13px;font-weight:800;color:${isOver ? '#b91c1c' : '#1e293b'};">${totalDayLoad.toFixed(2)} / ${limit.toFixed(1)}T</div>
                        <div style="height:4px;background:#f1f5f9;border-radius:2px;margin:8px 0;overflow:hidden;">
                            <div style="height:100%;width:${Math.min((totalDayLoad/limit)*100, 100)}%;background:${isOver ? '#ef4444' : '#10b981'};"></div>
                        </div>
                        <div style="font-size:8px;color:#94a3b8;text-align:center;">
                            ${pDate === targetDate ? 'Start Day' : 'Cascaded Day'}
                        </div>
                    </div>`;
                });
            });
        } catch(e) { console.error('Error fetching global capacity', e); }

        capHtml += `</div>`;
        dialog.set_value("global_capacity_info", capHtml);
        dialog.capacityExceeded = capacityExceeded;
    }

    var d = new frappe.ui.Dialog({
        title: '🚀 Push to Production Board',
        fields: [
            { fieldname: 'fetch_dates', fieldtype: 'Data', label: 'Fetch Date(s)', default: (fetchDates.join(", ") || defaultTargetDate), read_only: 1 },
            { fieldname: 'plan_name_display', fieldtype: 'Data', label: 'Current Plan', default: selectedPlanLabel.value, read_only: 1 },
            { fieldtype: 'Column Break' },
            { fieldname: 'target_date', fieldtype: 'Date', label: 'Target Date', default: defaultTargetDate, reqd: 1, description: 'Push start point.' },
            
            { fieldtype: 'Section Break', label: 'Filters' },
            { fieldname: 'filter_unit', fieldtype: 'Select', label: 'Unit', options: ['All Units', 'Unit 1', 'Unit 2', 'Unit 3', 'Unit 4'], default: 'All Units' },
            { fieldtype: 'Column Break' },
            { fieldname: 'filter_logic', fieldtype: 'Select', label: 'Match', options: ['AND', 'OR'], default: 'AND' },
            { fieldtype: 'Section Break' },
            { fieldname: 'filter_quality', fieldtype: 'Data', label: 'Quality' },
            { fieldtype: 'Column Break' },
            { fieldname: 'filter_color', fieldtype: 'Data', label: 'Color' },
            { fieldtype: 'Column Break' },
            { fieldname: 'filter_party', fieldtype: 'Data', label: 'Party Code' },

            { fieldtype: 'Section Break' },
            {
                fieldname: 'sequence_html',
                fieldtype: 'HTML',
                options: buildDialogHtml(currentSequence, overallStatus)
            },
            { fieldtype: 'Section Break', label: 'Capacity Preview' },
            { fieldname: 'global_capacity_info', fieldtype: 'HTML', label: '' }
        ],
        primary_action_label: overallStatus === 'Approved' ? '🚀 Push to Board' : 
                          (overallStatus === 'Rejected' ? '📤 Re-submit for Approval' :
                          ((overallStatus === 'Pending Approval' || (overallStatus === 'Draft' && canApprove)) ? 
                           (canApprove ? '✅ Approve Arrangement' : '⏳ Waiting for Approval') : 
                           '📤 Request Arrangement Approval')),
        primary_action: async (values) => {
            const targetDate = (values.target_date || defaultTargetDate || today).trim();
            const currentStatus = dialogOverallStatus || d.overallStatus || overallStatus;
            
            const normalizeUnit = (u) => {
                const r = (u || "").toString().trim().toUpperCase().replace(/\s+/g, '');
                if (r.indexOf('UNIT1') !== -1) return 'Unit 1';
                if (r.indexOf('UNIT2') !== -1) return 'Unit 2';
                if (r.indexOf('UNIT3') !== -1) return 'Unit 3';
                if (r.indexOf('UNIT4') !== -1) return 'Unit 4';
                return 'Mixed';
            };

            const checkedItems = currentSequence.filter(i => i.checked !== false && !i.pushed);
            const allApproved = checkedItems.length > 0 && checkedItems.every(i => i.approvalStatus === 'Approved');

            if (currentStatus === 'Draft' || currentStatus === 'Rejected') {
                if (allApproved) {
                    // Force pushing despite overall draft/rejected status 
                } else {
                    if (checkedItems.length === 0) {
                        frappe.msgprint('No pending items selected for approval.');
                        return;
                    }
                    const unitsToRequest = [...new Set(checkedItems.map(s => normalizeUnit(s.unit || 'Unit 1')))];
                    for (const u of unitsToRequest) {
                        const unitItems = checkedItems.filter(s => normalizeUnit(s.unit || 'Unit 1') === u).map(s => s.name);
                        await frappe.call({
                            method: "production_scheduler.api.save_color_sequence",
                            args: { date: targetDate, unit: u, sequence_data: unitItems, plan_name: selectedPlan.value }
                        });
                        
                        await frappe.call({
                            method: "production_scheduler.api.request_sequence_approval",
                            args: { date: targetDate, unit: u, plan_name: selectedPlan.value }
                        });
                    }
                    frappe.show_alert({ message: 'Arrangement approval requested', indicator: 'orange' });
                    d.hide();
                    fetchData();
                    return;
                }
            }
            if ((currentStatus === 'Pending Approval' || (currentStatus === 'Draft' && canApprove)) && canApprove) {
                if (allApproved) {
                    // Force pushing despite pending status
                } else {
                    const unitsToApprove = [...new Set(checkedItems.map(s => normalizeUnit(s.unit || 'Unit 1')))];
                    for (const u of unitsToApprove) {
                        const unitItems = checkedItems.filter(s => normalizeUnit(s.unit || 'Unit 1') === u).map(s => s.name);
                        
                        // Always save the latest selection before approving
                        await frappe.call({
                            method: "production_scheduler.api.save_color_sequence",
                            args: { date: targetDate, unit: u, sequence_data: unitItems, plan_name: selectedPlan.value }
                        });

                        await frappe.call({
                            method: "production_scheduler.api.approve_sequence",
                            args: { date: targetDate, unit: u, plan_name: selectedPlan.value }
                        });
                    }
                    frappe.show_alert({ message: 'Arrangement Approved', indicator: 'green' });
                    d.hide();
                    fetchData();
                    return;
                }
            }
            if (currentStatus !== 'Approved' && !allApproved) {
                frappe.msgprint(__('The selected color arrangement must be Approved before pushing.'));
                return;
            }


            // PUSH LOGIC (Only if we are explicitly pushing now)
            const fetchDatesValue = values.fetch_dates || fetchDates.join(",");

            if (checkedItems.length === 0) { frappe.msgprint('No items selected.'); return; }

            const pBtn = d.get_primary_btn();
            
            // No auto-cascading on global push.
            // If target day is full, user must change target date and push again.
            if (d.capacityExceeded) {
                frappe.msgprint(
                    '<b>Target date capacity is full.</b><br>Please change target date and check capacity again.<br>Cascading is disabled.'
                );
                return;
            }

            pBtn.prop('disabled', true).text('⏳ Pushing...');
            frappe.show_alert({ message: `Pushing ${checkedItems.length} items from fetch date(s) to ${targetDate}...`, indicator: 'blue' });

            try {
                const itemsToMove = [];
                let seqNo = 1;

                for (const item of checkedItems) {
                    itemsToMove.push({
                        name: item.name,
                        target_date: targetDate,
                        target_unit: item.unit || 'Unit 1',
                        sequence_no: seqNo++
                    });
                }

                const r = await frappe.call({
                    method: "production_scheduler.api.push_items_to_pb",
                    args: {
                        items_data: JSON.stringify(itemsToMove),
                        fetch_dates: fetchDatesValue,
                        target_date: targetDate,
                        pb_plan_name: selectedPlanLabel.value,
                        strict_target_date: 1,
                        approve_cross_month: 0,
                        approve_maintenance_move: 0
                    }
                });
                if (r.message && r.message.status === "maintenance_move_approval_required") {
                    const rows = (r.message.candidates || []).slice(0, 15)
                      .map(c => `• ${c.party_code || '-'} | ${c.item_code || c.item_name || '-'} | ${c.from_date} → ${c.to_date} | ${c.qty} Kg`)
                      .join("<br>");
                    const more = (r.message.count || 0) > 15 ? `<br>...and ${(r.message.count || 0) - 15} more` : "";
                    const ok = await new Promise(resolve => {
                      frappe.confirm(
                        `<b>${r.message.count || 0} orders are on maintenance dates.</b><br><br>${rows}${more}<br><br>Approve moving these to shown dates?`,
                        () => resolve(true),
                        () => resolve(false)
                      );
                    });
                    if (!ok) {
                      pBtn.prop('disabled', false).text('✅ Approve Arrangement');
                      return;
                    }
                    const r2 = await frappe.call({
                      method: "production_scheduler.api.push_items_to_pb",
                      args: {
                        items_data: JSON.stringify(itemsToMove),
                        fetch_dates: fetchDatesValue,
                        target_date: targetDate,
                        pb_plan_name: selectedPlanLabel.value,
                        strict_target_date: 1,
                        approve_maintenance_move: 1,
                        approve_cross_month: 0
                      }
                    });
                    if (r2.message) {
                      r.message = r2.message;
                    }
                }
                if (r.message && r.message.status === "cross_month_approval_required") {
                    const rows = (r.message.candidates || []).slice(0, 15)
                      .map(c => `• ${c.party_code || '-'} | ${c.item_code || c.item_name || '-'} | ${c.from_date} → ${c.to_date} | ${c.qty} Kg`)
                      .join("<br>");
                    const more = (r.message.count || 0) > 15 ? `<br>...and ${(r.message.count || 0) - 15} more` : "";
                    const ok = await new Promise(resolve => {
                      frappe.confirm(
                        `<b>${r.message.count || 0} orders will move to next month.</b><br><br>${rows}${more}<br><br>Approve and continue?`,
                        () => resolve(true),
                        () => resolve(false)
                      );
                    });
                    if (!ok) {
                      pBtn.prop('disabled', false).text('✅ Approve Arrangement');
                      return;
                    }
                    const r2 = await frappe.call({
                      method: "production_scheduler.api.push_items_to_pb",
                      args: {
                        items_data: JSON.stringify(itemsToMove),
                        fetch_dates: fetchDatesValue,
                        target_date: targetDate,
                        pb_plan_name: selectedPlanLabel.value,
                        strict_target_date: 1,
                        approve_cross_month: 1,
                        approve_maintenance_move: 1
                      }
                    });
                    if (r2.message) {
                      r.message = r2.message;
                    }
                }
                if (r.message && r.message.status === 'success') {
                    pBtn.text('✅ Pushed').css({'background-color': '#059669', 'color': 'white'});
                    
                    const pushedCount = r.message.count || r.message.moved_items || itemsToMove.length;
                    let dateMsg = '';
                    if (r.message.dates && r.message.dates.length > 0) {
                        dateMsg = ` to ${r.message.dates.join(', ')}`;
                    } else {
                        dateMsg = ` to ${targetDate}`;
                    }

                    frappe.show_alert({
                        message: `✅ Pushed ${pushedCount} item(s)${dateMsg} to Production Board`,
                        indicator: 'green'
                    });
                    setTimeout(() => {
                        d.hide();
                        fetchData();
                    }, 1500);
                } else {
                    pBtn.prop('disabled', false).text('🚀 Push to Board');
                    frappe.msgprint(r.message?.message || 'Push failed.');
                }
            } catch (e) {
                console.error('Push to PB failed', e);
                frappe.msgprint('Error pushing to Production Board.');
            }
        }
    });

    const updateDialogStatus = async (newTargetDate) => {
        if (!newTargetDate) return;
        const relevantUnits = [...new Set(currentSequence.map(s => {
            const raw = (s.unit || s.unitKey || 'Unit 1').trim();
            // Robust normalization to 'Unit X' format
            if (raw.toUpperCase().includes('UNIT 1')) return 'Unit 1';
            if (raw.toUpperCase().includes('UNIT 2')) return 'Unit 2';
            if (raw.toUpperCase().includes('UNIT 3')) return 'Unit 3';
            if (raw.toUpperCase().includes('UNIT 4')) return 'Unit 4';
            return raw;
        }))].sort();
        
        const unitStatuses = [];
        dialogApprovalMeta = null;
        dialogPendingUnits = [];
        
        let combinedSequenceData = [];
        
        for (const u of relevantUnits) {
            const res = await frappe.call({
                method: "production_scheduler.api.get_color_sequence",
                args: { date: newTargetDate, unit: u, plan_name: selectedPlan.value }
            });
            const msg = res.message || {};
            const st = msg.status || 'Draft';
            unitStatuses.push(st);
            
            // Sync individual row statuses for this unit
            const approvedSequence = msg.sequence || [];
            currentSequence.forEach(it => {
                if ((it.unit || 'Unit 1') === u) {
                    if (approvedSequence.includes(it.name) && st !== 'Draft') {
                        it.approvalStatus = st;
                    } else {
                        it.approvalStatus = 'Draft';
                    }
                }
            });

            // ✅ Sync unitSortConfig so that 'Smart Auto-Tick' sees the same sequence
            if (msg.sequence && msg.sequence.length) {
                try {
                    const names = msg.sequence;
                    if (unitSortConfig.value[u]) unitSortConfig.value[u].savedSequence = names;
                    combinedSequenceData = combinedSequenceData.concat(names);
                } catch(e) {}
            }

            if ((msg.status === 'Approved' || msg.status === 'Rejected') && !dialogApprovalMeta) {
                dialogApprovalMeta = { modified_by: msg.modified_by, modified: msg.modified };
            }
            if (msg.status !== 'Approved') {
                if (!dialogPendingUnits.includes(u)) {
                    dialogPendingUnits.push(u);
                }
            }
        }

        // Fetch Board Seeds proactively to show "Board End" immediately
        try {
            const rSeeds = await frappe.call({
                method: "production_scheduler.api.get_board_seeds",
                args: { 
                    target_date: newTargetDate, 
                    plan_name: selectedPlan.value,
                    exclude_items: JSON.stringify(masterSequence.filter(s => !s.pushed).map(s => s.name))
                }
            });
            d.smartSeeds = rSeeds.message || {};
        } catch(e) { console.error("Failed to fetch seeds proactively", e); }

        // Re-sort currentSequence if we have sequence_data from the approval record(s)
        let matchedCount = 0;
        if (combinedSequenceData.length > 0) {
            const sorted = [];
            // Follow the order in combinedSequenceData, then add any missing items at the end
            combinedSequenceData.forEach(name => {
                const item = currentSequence.find(i => i.name === name);
                if (item) {
                    sorted.push(item);
                    matchedCount++;
                }
            });
            currentSequence.forEach(item => {
                if (!sorted.find(i => i.name === item.name)) sorted.push(item);
            });
            currentSequence = sorted;
            currentSequence.forEach((item, i) => { item.sequence_no = i + 1; });
        }

        const newOverallStatus = unitStatuses.some(s => s === 'Rejected') ? 'Rejected' :
                                (unitStatuses.every(s => s === 'Approved') ? 'Approved' : 
                                 (unitStatuses.some(s => s === 'Pending Approval' || s === 'Draft') ? 
                                  (unitStatuses.some(s => s === 'Draft') ? 'Draft' : 'Pending Approval') : 'Approved'));

        dialogOverallStatus = newOverallStatus;
        d.overallStatus = newOverallStatus;
        
        // Store metadata if available
        if (unitStatuses.length > 0) {
            // Pick first unit's meta as proxy for simplicity, or we could aggregate
            // But since all units must be approved for overall 'Approved', any is fine.
        }
        
        d.set_df_property('sequence_html', 'options', buildDialogHtml(currentSequence, newOverallStatus));
        setTimeout(() => { wireCheckboxes(); updateCountLabel(); }, 50);
        
        const label = newOverallStatus === 'Approved' ? '🚀 Push to Board' : 
                     (newOverallStatus === 'Rejected' ? '📤 Re-submit for Approval' :
                     ((newOverallStatus === 'Pending Approval' || (newOverallStatus === 'Draft' && canApprove)) ? 
                      (canApprove ? '✅ Approve Arrangement' : '⏳ Waiting for Approval') : 
                      '📤 Request Arrangement Approval'));
        
        const $btn = d.get_primary_btn();
        $btn.text(label);
        
        // Update button colors based on status
        if (newOverallStatus === 'Approved') {
            $btn.css({'background-color': '#16a34a', 'border-color': '#15803d', 'color': 'white'});
        } else if (newOverallStatus === 'Rejected') {
            $btn.css({'background-color': '#dc2626', 'border-color': '#b91c1c', 'color': 'white'});
        } else {
            $btn.css({'background-color': '', 'border-color': '', 'color': ''});
        }

        // Allow Smart Auto-Tick even if Approved (user can re-sequence if needed)
        const $smartBtn = d.$wrapper.find('.btn-custom').filter((i, el) => $(el).text().includes('Smart Auto-Tick'));
        $smartBtn.prop('disabled', false).css('opacity', '1').attr('title', '');
    };

    d.setup = () => {
        updateDialogStatus(defaultTargetDate);
    };

    d.fields_dict.target_date.df.onchange = () => {
        const val = d.get_value('target_date');
        if (val) updateDialogStatus(val);
    };

    d.show();
    
    d.on_hide = () => {
        window.refreshPushStatus = null;
    };

    d.$wrapper.find('.modal-dialog').css('max-width', '1000px');
    d.$wrapper.find('.modal-content').css({'border-radius': '16px', 'border': 'none', 'box-shadow': '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)'});
    d.$wrapper.find('.modal-header').css({'background': '#fff', 'border-bottom': '1px solid #f1f5f9', 'border-radius': '16px 16px 0 0', 'padding': '16px 24px'});
    d.$wrapper.find('.modal-title').css({'font-weight': '800', 'color': '#111827', 'font-size': '18px'});
    
    // Style Primary Button
    const pBtn = d.get_primary_btn();
    if (overallStatus === 'Approved') {
        pBtn.css({'background-color': '#2563eb', 'border': 'none', 'font-weight': '700', 'padding': '8px 24px', 'border-radius': '8px', 'box-shadow': '0 4px 6px -1px rgba(37, 99, 235, 0.2)'});
    } else if (overallStatus === 'Pending Approval') {
        if (canApprove) {
           pBtn.css({'background-color': '#ca8a04', 'border': 'none', 'font-weight': '700', 'padding': '8px 24px', 'border-radius': '8px', 'box-shadow': '0 4px 6px -1px rgba(202, 138, 4, 0.2)'});
        } else {
           pBtn.prop('disabled', true).css({'background-color': '#e2e8f0', 'color': '#94a3b8', 'border': 'none', 'font-weight': '700'});
        }
    } else {
        pBtn.css({'background-color': '#d97706', 'border': 'none', 'font-weight': '700', 'padding': '8px 24px', 'border-radius': '8px', 'box-shadow': '0 4px 6px -1px rgba(217, 119, 6, 0.2)'});
    }

    loadGlobalCapacityPreview(d, currentSequence);


    function applyFilters() {
        const unitSearch = d.get_value('filter_unit') || 'All Units';
        const qualitySearch = (d.get_value('filter_quality') || "").toLowerCase();
        const colorSearch = (d.get_value('filter_color') || "").toLowerCase();
        const partySearch = (d.get_value('filter_party') || "").toLowerCase();
        const matchLogic = d.get_value('filter_logic') || "AND";

        currentSequence = masterSequence.filter(item => {
            // Unit filter is always strict (AND condition)
            if (unitSearch !== 'All Units') {
                const u1 = (item.unit || '').toString().toUpperCase().trim();
                const u2 = unitSearch.toUpperCase().trim();
                if (u1 !== u2) return false;
            }

            const matchQ = qualitySearch ? item.quality.toLowerCase().includes(qualitySearch) : false;
            const matchC = colorSearch ? item.color.toLowerCase().includes(colorSearch) : false;
            const matchP = partySearch ? (item.partyCode.toLowerCase().includes(partySearch) || item.partyName.toLowerCase().includes(partySearch) || item.customer.toLowerCase().includes(partySearch)) : false;

            const hasAnySearch = qualitySearch || colorSearch || partySearch;
            if (!hasAnySearch) return true;

            if (matchLogic === "AND") {
                if (qualitySearch && !matchQ) return false;
                if (colorSearch && !matchC) return false;
                if (partySearch && !matchP) return false;
                return true;
            } else {
                return matchQ || matchC || matchP;
            }
        });

        // Re-number
        currentSequence.forEach((item, i) => { item.sequence_no = i + 1; });

        d.fields_dict.sequence_html.$wrapper.html(buildDialogHtml(currentSequence, dialogOverallStatus));
        wireCheckboxes();
        updateCountLabel();
        // REMOVED: updateDialogStatus(d.get_value('target_date')); 
        // Calling it here reverts the 'Draft' status to 'Approved' from DB before re-submission!
    }

    // Attach keyup events to inputs for real-time filtering
    ['filter_quality', 'filter_color', 'filter_party'].forEach(fn => {
        d.fields_dict[fn].$input.on('input', () => applyFilters());
    });
    d.fields_dict.filter_logic.$input.on('change', () => applyFilters());
    d.fields_dict.filter_unit.$input.on('change', () => { applyFilters(); loadGlobalCapacityPreview(d, currentSequence); });
    d.fields_dict.target_date.$input.on('change', () => loadGlobalCapacityPreview(d, currentSequence));

    // Wire up checkbox events
    function wireCheckboxes() {
        const wrapperEl = $(d.wrapper || d.$wrapper).get(0);
        if (!wrapperEl) return;
        const container = wrapperEl.querySelector('.frappe-control[data-fieldname="sequence_html"]') || wrapperEl;
        
        const mainCheckbox = container.querySelector('#mtp-check-all');
        if (mainCheckbox) {
            mainCheckbox.addEventListener('change', function() {
                const isChecked = this.checked;
                container.querySelectorAll('tbody input[type=checkbox]').forEach(cb => {
                    cb.checked = isChecked;
                    const idx = parseInt(cb.dataset.idx);
                    if (!isNaN(idx) && currentSequence[idx]) currentSequence[idx].checked = isChecked;
                });
                updateCountLabel();
            });
        }

        container.querySelectorAll('tbody input[type=checkbox]').forEach(cb => {
            cb.addEventListener('change', function() {
                const idx = parseInt(this.dataset.idx);
                if (!isNaN(idx) && currentSequence[idx]) currentSequence[idx].checked = this.checked;
                updateCountLabel();
            });
        });

        // ── Drag-and-drop reorder using SortableJS ──
        const tbody = container.querySelector('tbody');
        if (tbody && window.Sortable) {
            if (tbody._sortable) tbody._sortable.destroy();
            // User requested to allow reordering even if approved (locks were previous logic)
            // if (dialogOverallStatus === 'Approved') return; 
            
            tbody._sortable = new window.Sortable(tbody, {
                animation: 150,
                handle: '.drag-handle',
                filter: 'tr:not([data-seq-idx])', // skip unit-header rows
                ghostClass: 'sortable-ghost',
                onEnd: (evt) => {
                    const draggedRow = evt.item;
                    const fromIdx = parseInt(draggedRow.dataset.seqIdx);
                    const allDataRows = Array.from(tbody.querySelectorAll('tr[data-seq-idx]'));
                    const toIdx = allDataRows.indexOf(draggedRow);
                    if (isNaN(fromIdx) || toIdx < 0 || fromIdx === toIdx) return;
                    
                    const moved = currentSequence.splice(fromIdx, 1)[0];
                    currentSequence.splice(toIdx, 0, moved);
                    currentSequence.forEach((item, i) => { item.sequence_no = i + 1; });

                    if (dialogOverallStatus === 'Approved' || dialogOverallStatus === 'Rejected') {
                        dialogOverallStatus = 'Draft';
                        d.overallStatus = 'Draft';
                        dialogApprovalMeta = null;
                        // Update button label and style immediately
                        const label = '📤 Request Arrangement Approval';
                        const $btn = d.get_primary_btn();
                        $btn.text(label).css({'background-color': '#d97706', 'border': 'none', 'box-shadow': '0 4px 6px -1px rgba(217, 119, 6, 0.2)'});
                    }

                    d.fields_dict.sequence_html.$wrapper.html(buildDialogHtml(currentSequence, dialogOverallStatus));
                    setTimeout(() => { wireCheckboxes(); updateCountLabel(); }, 100);
                }
            });
        }
    }


    function updateCountLabel() {
        const checkedItems = currentSequence.filter(i => i.checked !== false && !i.pushed);
        const total = checkedItems.length;
        const wrapperEl = $(d.wrapper || d.$wrapper).get(0);
        if (wrapperEl) {
            const countSpan = wrapperEl.querySelector('#seq-count-label');
            if (countSpan) countSpan.textContent = total;
        }

        if (total > 0) {
            const allApproved = checkedItems.every(i => i.approvalStatus === 'Approved');
            const pBtn = d.get_primary_btn();
            if (allApproved) {
                pBtn.text('🚀 Push to Board').css({'background-color': '#2563eb', 'color': 'white', 'opacity': '1'});
            } else {
                if (dialogOverallStatus === 'Rejected') {
                    pBtn.text('📤 Re-submit for Approval').css({'background-color': '#dc2626', 'color': 'white'});
                } else if (canApprove) {
                    pBtn.text('✅ Approve Arrangement').css({'background-color': '#ca8a04', 'color': 'white'});
                } else {
                    pBtn.text('📤 Request Arrangement Approval').css({'background-color': '#d97706', 'color': 'white'});
                }
            }
        }
        
        loadGlobalCapacityPreview(d, currentSequence);
    }

    // Add Smart Push button to Dialog Footer
    d.add_custom_action('🧠 Smart Auto-Tick', async () => {
        if (smartSequenceActive) return; // Already active
        
        d.get_close_btn().hide();
        const smartBtn = d.$wrapper.find('.btn-custom').last();
        smartBtn.text('⏳ Sequencing...');
        smartBtn.prop('disabled', true);
        
        try {
            // Target date drives capacity/seed context (fetch dates only fetch source rows).
            let itemDate = frappe.datetime.get_today();
            if (items && items.length > 0) {
                itemDate = items[0].ordered_date || items[0].orderDate || items[0].date || itemDate;
            }

            // Get the last running order on Production Board per unit to use as seed
            const singleTargetDate = (d.get_value && d.get_value('target_date') ? d.get_value('target_date') : itemDate).trim();
            
            const r = await frappe.call({
                method: 'production_scheduler.api.get_smart_push_sequence',
                args: { 
                    // Use masterSequence instead of currentSequence to ensure we don't LOSE un-pushed items that are currently filtered out!
                    item_names: JSON.stringify(masterSequence.filter(s => !s.pushed).map(s => s.name)),
                    target_date: singleTargetDate,
                    plan_name: (selectedPlan && selectedPlan.value) ? selectedPlan.value : 'Default'
                }
            });
            const smartSeqData = r.message || {};
            const smartSeq = smartSeqData.sequence || [];
            d.smartSeeds = smartSeqData.seeds || {};
            if (smartSeq.length > 0) {
                
                // Get existing loads to respect capacity limits on target day only
                let currentLoads = {};
                try {
                    const targetDatesStr = singleTargetDate;
                    const rCap = await frappe.call({
                        method: "production_scheduler.api.get_multiple_dates_capacity",
                        args: { dates: targetDatesStr, plan_name: '__all__', pb_only: 1 }
                    });
                    
                    if (rCap.message) {
                        ["Unit 1", "Unit 2", "Unit 3", "Unit 4"].forEach(u => {
                             // Initialize tracking with the total aggregated load currently hitting the target dates.
                             currentLoads[u] = rCap.message[u] ? rCap.message[u].total_load : 0;
                        });
                    }
                } catch(e) { console.error("Failed to get capacity for Smart Tick", e); }

                smartSequenceActive = true;

                if (dialogOverallStatus === 'Approved' || dialogOverallStatus === 'Rejected') {
                    dialogOverallStatus = 'Draft';
                    d.overallStatus = 'Draft';
                    dialogApprovalMeta = null;
                    const $btn = d.get_primary_btn();
                    $btn.text('📤 Request Arrangement Approval').css({'background-color': '#d97706', 'border': 'none', 'box-shadow': '0 4px 6px -1px rgba(217, 119, 6, 0.2)'});
                    
                    // Force update the UI status badge
                    const $statusWrapper = d.$wrapper.find('.modal-content [style*="background:#f1f5f9"]');
                    if ($statusWrapper.length) {
                        $statusWrapper.html(`
                            <span style="width:8px;height:8px;border-radius:50%;background:#64748b"></span>
                            <div style="display:flex; flex-direction:column;">
                                <span style="font-size:11px;font-weight:700;color:#1e293b;text-transform:uppercase;letter-spacing:0.02em;">Arrangement for ${d.get_value('target_date')}: DRAFT</span>
                            </div>
                        `);
                    }
                }
                
                // Track target-day limits
                const limitsMap = {};
                limitsMap['Unit 1'] = 4.4;
                limitsMap['Unit 2'] = 12;
                limitsMap['Unit 3'] = 9;
                limitsMap['Unit 4'] = 5.5;
                
                const filterUnitValue = d.get_value('filter_unit') || 'All Units';
                
                let mappedSeq = smartSeq.map(s => {
                    const mapped = {
                        name: s.name,
                        color: s.color || '',
                        quality: s.quality || s.custom_quality || '',
                        gsm: s.gsm || s.gsmVal || '',
                        unit: s.unit || s.unitKey || '',
                        qty: s.qty || '',
                        customer: s.customer || '',
                        partyCode: s.partyCode || s.party_code || '',
                        partyName: s.partyName || s.customer || '',
                        approvalStatus: s.approvalStatus || 'Draft',
                        planningSheet: s.planningSheet || s.parent || '',
                        phase: s.phase || '',
                        is_seed_bridge: !!s.is_seed_bridge,
                        sequence_no: s.sequence_no,
                        plannedDate: s.plannedDate || '',
                        itemName: s.name,
                        description: s.description || s.item_name || '',
                        pushed: isExcludedWhite(s.color) ? true : !!s.pbPlanName
                    };
                    
                    if (mapped.pushed) {
                        mapped.checked = false;
                        return mapped;
                    }

                    const u = (mapped.unit || 'Unit 1').toUpperCase().trim();
                    
                    // If a specific unit is filtered in the dialog, don't auto-tick items from other units
                    let filterUnitValue = 'All Units';
                    try { filterUnitValue = (d.get_value('filter_unit') || 'All Units').toUpperCase().trim(); } catch(e) {}
                    
                    if (filterUnitValue !== 'ALL UNITS' && u !== filterUnitValue) {
                        mapped.checked = false;
                    } else {
                        mapped.checked = true; // Tick everything
                    }
                    
                    return mapped;
                });

                // ✅ SMART ORDER PRESERVED: We no longer re-sort by savedSequence here 
                // because the user explicitly requested a "Smart" sequence from the backend.
                // Smart sequence only returns un-pushed items. 
                // Pushed items (fixed seeds) MUST be at the BOTTOM.
                const pushedItems = masterSequence.filter(s => s.pushed);
                
                // Update masterSequence with the new smart order for draft items
                // This ensures that applyFilters() doesn't lose the Smart order!
                masterSequence = [...mappedSeq, ...pushedItems];
                
                // Keep the current filter (it will use the NEW masterSequence order)
                applyFilters();
                setTimeout(() => { wireCheckboxes(); updateCountLabel(); }, 100);
            } else {
                frappe.show_alert({ message: 'No sequence data returned', indicator: 'orange' });
            }
        } catch (e) {
            console.error('Smart sequence error', e);
            frappe.show_alert({ message: 'Smart sequence failed', indicator: 'red' });
        } finally {
            smartBtn.text('✅ Smart Sequenced');
            d.get_close_btn().show();
        }
    });

    // Style the custom action button to look distinct
    setTimeout(() => {
        const smartBtn = d.$wrapper.find('.btn-custom').last();
        smartBtn.removeClass('btn-default').addClass('btn-secondary');
        smartBtn.css({'background-color': '#10b981', 'color': 'white', 'border': 'none', 'font-weight': 'bold'});
    }, 100);

    setTimeout(() => { wireCheckboxes(); }, 300);

    // Global helper for refresh button in dialog
    window.refreshPushStatus = () => updateDialogStatus(d.get_value('target_date'));
}


// ---- MOVE TO PLAN ----
async function openMovePlanDialog() {
    // 1. Get ALL items from the current plan (rawData filtered by plan)
    //    Exclude white orders — they stay in the current plan
    const allItems = rawData.value.filter(d => {
        const planOk = selectedPlan.value === 'Default'
            ? (!d.planName || d.planName === '' || d.planName === 'Default')
            : d.planName === selectedPlan.value;
        if (!planOk) return false;
        // Exclude white colors — only show color orders in move dialog
        const colorUpper = (d.color || "").toUpperCase();
        if (EXCLUDED_WHITES.some(ex => colorUpper.includes(ex))) return false;
        return true;
    });

    if (allItems.length === 0) {
        frappe.msgprint('No orders in this plan to move.');
        return;
    }

    // 2. Get available target plans (excluding current, non-locked, current month only)
    const targetPlans = visiblePlans.value
        .filter(p => p.name !== selectedPlan.value && !p.locked)
        .map(p => p.name);

    if (targetPlans.length === 0) {
        frappe.msgprint('No other unlocked plans available. Create a new plan first using the "+" button.');
        return;
    }

    // 3. Separate items: moveable (no WO) vs locked (has WO)
    const moveableItems = allItems.filter(i => !i.has_wo);
    const lockedItems   = allItems.filter(i => i.has_wo);

    // 4. Sort moveable items: Color (Light→Dark), then Unit, then GSM
    const sorted = [...moveableItems].sort((a, b) => {
        const pA = getGroupPriority(a.color), pB = getGroupPriority(b.color);
        if (pA !== pB) return pA - pB;
        const uOrder = ['Unit 1','Unit 2','Unit 3','Unit 4','Mixed'];
        const uA = uOrder.indexOf(a.unit||'Mixed'), uB = uOrder.indexOf(b.unit||'Mixed');
        if (uA !== uB) return uA - uB;
        return (parseFloat(a.gsm)||0) - (parseFloat(b.gsm)||0);
    });

    // 5. Build HTML table
    const buildTable = () => {
        const unitBadge = u => {
            const c = u==='Unit 1'?'#3b82f6':u==='Unit 2'?'#10b981':u==='Unit 3'?'#f59e0b':u==='Unit 4'?'#8b5cf6':'#64748b';
            return `<span style="background:${c};color:#fff;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:600;">${u||'Mixed'}</span>`;
        };

        // Moveable rows
        const moveRows = sorted.map(item => {
            const hex = getHexColor(item.color);
            const wt = ((item.qty||0)/1000).toFixed(3);
            return `<tr class="mtp-row" data-unit="${item.unit||'Mixed'}" style="border-bottom:1px solid #f1f5f9;">
                <td style="padding:5px 6px;text-align:center;">
                    <input type="checkbox" class="mtp-check" data-name="${item.itemName}" checked style="cursor:pointer;width:14px;height:14px;">
                </td>
                <td style="padding:5px 6px;">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="width:12px;height:12px;background:${hex};border-radius:2px;border:1px solid #ccc;flex-shrink:0;display:inline-block;"></span>
                        <b style="font-size:11px;">${item.color||'N/A'}</b>
                    </div>
                </td>
                <td style="padding:5px 6px;">${unitBadge(item.unit)}</td>
                <td style="padding:5px 6px;font-size:11px;color:#555;">${item.quality||'-'}</td>
                <td style="padding:5px 6px;font-size:11px;text-align:center;">${item.gsm||'-'}</td>
                <td style="padding:5px 6px;font-size:11px;text-align:right;font-weight:600;">${wt} T</td>
                <td style="padding:5px 6px;font-size:11px;color:#888;">${item.partyCode||item.customer||'-'}</td>
                <td style="padding:5px 6px;text-align:center;"><span style="color:#16a34a;font-size:10px;font-weight:600;">✓ FREE</span></td>
            </tr>`;
        }).join('');

        // Locked rows (WO exists — stays in original plan)
        const lockRows = lockedItems.map(item => {
            const hex = getHexColor(item.color);
            const wt = ((item.qty||0)/1000).toFixed(3);
            return `<tr style="border-bottom:1px solid #f1f5f9;opacity:0.5;background:#fef9c3;">
                <td style="padding:5px 6px;text-align:center;">—</td>
                <td style="padding:5px 6px;">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="width:12px;height:12px;background:${hex};border-radius:2px;border:1px solid #ccc;flex-shrink:0;display:inline-block;"></span>
                        <b style="font-size:11px;">${item.color||'N/A'}</b>
                    </div>
                </td>
                <td style="padding:5px 6px;">${unitBadge(item.unit)}</td>
                <td style="padding:5px 6px;font-size:11px;color:#555;">${item.quality||'-'}</td>
                <td style="padding:5px 6px;font-size:11px;text-align:center;">${item.gsm||'-'}</td>
                <td style="padding:5px 6px;font-size:11px;text-align:right;font-weight:600;">${wt} T</td>
                <td style="padding:5px 6px;font-size:11px;color:#888;">${item.partyCode||item.customer||'-'}</td>
                <td style="padding:5px 6px;text-align:center;"><span style="color:#dc2626;font-size:10px;font-weight:600;">🔒 WO</span></td>
            </tr>`;
        }).join('');

        const totalMoveT = (sorted.reduce((s,i)=>s+(i.qty||0),0)/1000).toFixed(2);
        const totalLockT = (lockedItems.reduce((s,i)=>s+(i.qty||0),0)/1000).toFixed(2);

        return `<div style="font-family:-apple-system,sans-serif;">
            <!-- Source/Target Header -->
            <div style="display:flex;gap:12px;margin-bottom:10px;align-items:center;background:#f8fafc;padding:10px 14px;border-radius:8px;border:1px solid #e2e8f0;">
                <div>
                    <div style="font-size:10px;color:#64748b;margin-bottom:2px;">SOURCE PLAN</div>
                    <div style="font-weight:700;color:#0f172a;font-size:13px;">📋 ${selectedPlan.value}</div>
                </div>
                <div style="font-size:20px;color:#94a3b8;padding:0 6px;">→</div>
                <div>
                    <div style="font-size:10px;color:#64748b;margin-bottom:2px;">TARGET PLAN</div>
                    <select id="mtp-target-plan" style="font-weight:700;border:1px solid #7c3aed;padding:5px 8px;border-radius:6px;font-size:12px;color:#7c3aed;background:#faf5ff;">
                        ${targetPlans.map(p=>`<option value="${p}">${p}</option>`).join('')}
                    </select>
                </div>
            </div>

            <!-- Summary badges -->
            <div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap;">
                <span style="background:#dcfce7;color:#16a34a;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">✓ ${sorted.length} moveable (${totalMoveT} T)</span>
                ${lockedItems.length>0?`<span style="background:#fef9c3;color:#b45309;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">🔒 ${lockedItems.length} WO locked — stays in ${selectedPlan.value} (${totalLockT} T)</span>`:''}
                <button onclick="document.querySelectorAll('.mtp-check').forEach(c=>c.checked=true)" style="font-size:10px;padding:3px 8px;cursor:pointer;border:1px solid #10b981;color:#10b981;background:#f0fdf4;border-radius:4px;margin-left:auto;">✅ All</button>
                <button onclick="document.querySelectorAll('.mtp-check').forEach(c=>c.checked=false)" style="font-size:10px;padding:3px 8px;cursor:pointer;border:1px solid #ef4444;color:#ef4444;background:#fef2f2;border-radius:4px;">❌ None</button>
            </div>

            <!-- Unit Filter Buttons -->
            <div style="display:flex;gap:4px;margin-bottom:8px;align-items:center;">
                <span style="font-size:10px;color:#64748b;font-weight:600;margin-right:4px;">FILTER UNIT:</span>
                <button class="mtp-unit-filter" data-unit="all" onclick="document.querySelectorAll('.mtp-row').forEach(r=>{r.style.display='';r.querySelector('.mtp-check').checked=true}); document.querySelectorAll('.mtp-unit-filter').forEach(b=>b.style.background='#f1f5f9'); this.style.background='#dbeafe'" style="font-size:10px;padding:3px 10px;cursor:pointer;border:1px solid #cbd5e1;border-radius:4px;background:#dbeafe;font-weight:600;">All</button>
                ${['Unit 1','Unit 2','Unit 3','Unit 4'].map(u => {
                    const c = u==='Unit 1'?'#3b82f6':u==='Unit 2'?'#10b981':u==='Unit 3'?'#f59e0b':'#8b5cf6';
                    return `<button class="mtp-unit-filter" data-unit="${u}" onclick="document.querySelectorAll('.mtp-row').forEach(r=>{const ru=r.dataset.unit;if(ru==='${u}'){r.style.display='';r.querySelector('.mtp-check').checked=true}else{r.style.display='none';r.querySelector('.mtp-check').checked=false}}); document.querySelectorAll('.mtp-unit-filter').forEach(b=>b.style.background='#f1f5f9'); this.style.background='${c}22'" style="font-size:10px;padding:3px 10px;cursor:pointer;border:1px solid ${c};color:${c};border-radius:4px;background:#f1f5f9;font-weight:600;">${u}</button>`;
                }).join('')}
            </div>

            <!-- Table -->
            <div style="max-height:400px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                    <thead style="position:sticky;top:0;background:#f1f5f9;z-index:1;">
                        <tr>
                            <th style="padding:6px;width:30px;text-align:center;"><input type="checkbox" id="mtp-check-all" onclick="document.querySelectorAll('.mtp-check').forEach(c=>c.checked=this.checked)" style="cursor:pointer;"></th>
                            <th style="padding:6px;text-align:left;">Color</th>
                            <th style="padding:6px;text-align:left;">Unit</th>
                            <th style="padding:6px;text-align:left;">Quality</th>
                            <th style="padding:6px;text-align:center;">GSM</th>
                            <th style="padding:6px;text-align:right;">Weight</th>
                            <th style="padding:6px;text-align:left;">Party</th>
                            <th style="padding:6px;text-align:center;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${moveRows}
                        ${lockRows}
                    </tbody>
                </table>
            </div>
            ${lockedItems.length>0?`<p style="font-size:10px;color:#b45309;margin-top:6px;padding:6px 10px;background:#fef9c3;border-radius:4px;">⚠️ Yellow rows have Work Orders — they will <b>remain in "${selectedPlan.value}"</b> on the same date after the move.</p>`:''}
        </div>`;
    };

    const d = new frappe.ui.Dialog({
        title: `📥 Move Orders to Another Plan`,
        fields: [{ fieldtype: 'HTML', fieldname: 'move_table', options: buildTable() }],
        primary_action_label: '🚀 Move Selected',
        primary_action: async () => {
            const targetPlan = document.getElementById('mtp-target-plan')?.value;
            if (!targetPlan) { frappe.msgprint('Select a target plan.'); return; }

            const checkedNames = [...document.querySelectorAll('.mtp-check:checked')]
                .map(c => c.dataset.name).filter(Boolean);
            if (checkedNames.length === 0) { frappe.msgprint('No items selected.'); return; }

            d.hide();
            frappe.show_alert({ message: `Moving ${checkedNames.length} items to "${targetPlan}"...`, indicator: 'blue' });

            try {
                function getDaysInViewScope() {
    if (viewScope.value === 'weekly') return 7;
    if (viewScope.value === 'monthly' && filterMonth.value) {
        const [year, month] = filterMonth.value.split('-');
        return new Date(year, month, 0).getDate();
    }
    // Default to Daily: count the number of comma-separated dates
    if (viewScope.value === 'daily' && filterOrderDate.value) {
        return String(filterOrderDate.value).split(',').filter(d => d.trim()).length || 1;
    }
    return 1;
}
                const daysInView = getDaysInViewScope();
                const isAggregateView = viewScope.value === 'monthly' || viewScope.value === 'weekly';

                // Build date args from current view scope
                let dateArgs = {};
                if (viewScope.value === 'monthly' && filterMonth.value) {
                    const [year, month] = filterMonth.value.split("-");
                    const lastDay = new Date(year, month, 0).getDate();
                    dateArgs = { start_date: `${year}-${month}-01`, end_date: `${year}-${month}-${lastDay}` };
                } else if (viewScope.value === 'weekly' && filterWeek.value) {
                    // Use same week calculation as fetchData
                    const [yearStr, weekStr] = filterWeek.value.split("-W");
                    const yr = parseInt(yearStr), wk = parseInt(weekStr);
                    const simple = new Date(yr, 0, 1 + (wk - 1) * 7);
                    const dow = simple.getDay();
                    const ws = new Date(simple);
                    if (dow <= 4) ws.setDate(simple.getDate() - simple.getDay() + 1);
                    else ws.setDate(simple.getDate() + 8 - simple.getDay());
                    const fmt = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
                    const we = new Date(ws); we.setDate(ws.getDate() + 6);
                    dateArgs = { start_date: fmt(ws), end_date: fmt(we) };
                } else if (filterOrderDate.value) {
                    dateArgs = { date: filterOrderDate.value };
                }

                const r = await frappe.call({
                    method: 'production_scheduler.api.move_items_to_plan',
                    args: {
                        item_names: JSON.stringify(checkedNames),
                        target_plan: targetPlan,
                        days_in_view: daysInView,
                        force_move: isAggregateView ? 1 : 0,
                        ...dateArgs
                    }
                });

                if (r.message) {
                    const { moved, errors, skipped } = r.message;
                    if (moved > 0) frappe.show_alert({ message: `✅ Moved ${moved} items to "${targetPlan}"`, indicator: 'green' });
                    if (skipped?.length > 0) {
                        console.warn('Skipped (cancelled SO):', skipped);
                    }
                    if (errors?.length > 0) {
                        frappe.msgprint({
                            title: '⚠️ Some items blocked',
                            message: `<ul>${errors.map(e=>`<li>${e}</li>`).join('')}</ul>`,
                            indicator: 'orange'
                        });
                    }
                    // Auto-switch to target plan so moved items are immediately visible
                    if (moved > 0) {
                        selectedPlan.value = targetPlan;
                    }
                    await fetchData();
                }

            } catch (e) {
                console.error('Move to plan failed', e);
                frappe.msgprint('❌ Error moving orders.');
            }
        },
        secondary_action_label: 'Cancel',
        secondary_action: () => d.hide()
    });

    d.show();
    d.$wrapper.find('.modal-dialog').css('max-width', '720px');
}


let ccRealtimeHandlerRegistered = false;
function handleRealtimeColorUpdate(payload) {
  // Keep logic simple: always refetch so all viewers stay in sync.
  // Color Chart and Production Board share the same underlying data.
  fetchData();
}

async function fetchData() {

  // fetchData continues (Global Slots persist across months/weeks)

  let args = {};
  
  if (viewScope.value === 'monthly') {
      if (!filterMonth.value) return;
      const [year, month] = filterMonth.value.split("-");
      const startDate = `${filterMonth.value}-01`;
      // Get last day of month
      const lastDay = new Date(year, month, 0).getDate();
      const endDate = `${filterMonth.value}-${lastDay}`;
      
      args = { start_date: startDate, end_date: endDate };
      
  } else if (viewScope.value === 'weekly') {
      if (!filterWeek.value) return;
      const [yearStr, weekStr] = filterWeek.value.split("-W");
      const year = parseInt(yearStr);
      const week = parseInt(weekStr);
      
      const simple = new Date(year, 0, 1 + (week - 1) * 7);
      const dow = simple.getDay();
      const ISOweekStart = new Date(simple);
      if (dow <= 4)
          ISOweekStart.setDate(simple.getDate() - simple.getDay() + 1);
      else
          ISOweekStart.setDate(simple.getDate() + 8 - simple.getDay());
          
      const format = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
      const startStr = format(ISOweekStart);
      
      const endSimple = new Date(ISOweekStart);
      endSimple.setDate(ISOweekStart.getDate() + 6);
      const endStr = format(endSimple);
      
      // Let the backend handle standard start_date/end_date mapping
      args = { start_date: startStr, end_date: endStr };

  } else {
      if (!filterOrderDate.value) return;
      
      // Pass the potentially comma-separated string straight to the backend
      // Modified our backend to split by comma if 'date' comes in that way
      args = { date: filterOrderDate.value };
  }
  
  // ✅ IMPROVEMENT: Fetch ALL plans for the date range
  // This allows the Matrix View to maintain a consistent color legend 
  // even if the currently selected plan is empty.
  await fetchPlans(args); // Load plan names for the dropdown
  args.plan_name = "__all__"; 

  try {
    const r = await frappe.call({
      method: "production_scheduler.api.get_color_chart_data",
      args: args,
    });
    
    // Fetch Sequence Statuses for each unit
    // Fetch for the primary date in view, or the selected filter date
    const statusDate = filterOrderDate.value ? (String(filterOrderDate.value).includes(",") ? String(filterOrderDate.value).split(",")[0] : filterOrderDate.value) : args.start_date;

    if (statusDate) {
        // Load merge data for current view
        await loadMergeData(statusDate);
        
        for (const unit of units) {
            const seqRes = await frappe.call({
                method: "production_scheduler.api.get_color_sequence",
                args: { date: statusDate, unit: unit, plan_name: selectedPlan.value }
            });
            if (seqRes.message) {
                sequenceStatuses.value[unit] = seqRes.message.status;
                // If we have a saved sequence, we can store it in a temporary lookup
                // to help sortItems later if mode is 'manual'
                if (seqRes.message.sequence && seqRes.message.sequence.length) {
                    unitSortConfig.value[unit].savedSequence = seqRes.message.sequence;
                } else {
                    unitSortConfig.value[unit].savedSequence = null;
                }
            }
        }
    }
    
    // Normalize API fields for consistent UI behavior across views
    rawData.value = (r.message || []).map(d => {
        let u = d.unit || "Mixed";
        if (u.toUpperCase() === "UNIT 1") u = "Unit 1";
        else if (u.toUpperCase() === "UNIT 2") u = "Unit 2";
        else if (u.toUpperCase() === "UNIT 3") u = "Unit 3";
        else if (u.toUpperCase() === "UNIT 4") u = "Unit 4";

        return {
            ...d,
            unit: u,
            idx: parseInt(d.idx || 0) || 9999,
            // Ensure date is parsed for monthly grouping
            orderDate: d.orderDate || d.ordered_date || "",
            // Production Board status (snake_case -> camelCase)
            plannedDate: d.plannedDate || d.planned_date || "",
            // Ensure stable keys even if backend varies
            partyCode: d.partyCode || d.party_code || "",
            partyName: d.party_name || d.partyName || "",
            approvalStatus: d.custom_approval_status || d.approvalStatus || "Draft",
            itemName: d.itemName || d.item_name || d.name || "",
            // Robust mapping: Prioritize PB plan name if it exists, especially if planName is "Default"
            planName: (d.pbPlanName && d.pbPlanName !== "") ? d.pbPlanName : (d.planName || d.custom_pb_plan_name || d.custom_plan_name || "Default"),
            pbPlanName: d.pbPlanName || d.custom_pb_plan_name || ""
        };
    });
    
    // ===== DEBUG: Show all plan names in loaded data =====
    const planNames = {};
    rawData.value.forEach(d => {
        const pn = d.planName || "(empty/null)";
        planNames[pn] = (planNames[pn] || 0) + 1;
    });
    console.log(`[CC Debug] Loaded ${rawData.value.length} items. Plan names:`, planNames, `Selected plan: "${selectedPlan.value}"`);
    // ===================================================
    
    // Load Custom Color Order (Sync)
    try {
        const orderRes = await frappe.call("production_scheduler.api.get_color_order");
        customRowOrder.value = orderRes.message || [];
    } catch(e) { console.error("Failed to load color order", e); }

    // Fetch Maintenance Records
    await fetchMaintenanceRecords();

    // Re-init sortable for fresh DOM (all view modes)
    await nextTick();
    // Small delay ensures monthly refs are ready
    setTimeout(() => initSortable(), 200);
  } catch (e) {
    frappe.msgprint("Error loading color chart data");
    console.error(e);
  }
}

// Watch date to re-analyze flow
watch(filterOrderDate, async () => {
    if (viewScope.value === 'daily') {
        await fetchData();
        await analyzePreviousFlow(); 
    }
});

// ---- AUTO ALLOCATION (BIN PACKING) ----
const UNIT_WIDTHS = {
  "Unit 1": 63,
  "Unit 2": 126,
  "Unit 3": 126,
  "Unit 4": 90
};



async function autoAllocate() {
  if (!confirm("⚠️ STRICT WIDTH ENFORCEMENT:\nAuto-allocate with strict width capacity checks.\nUnit 1: 63\", Unit 2: 126\", Unit 3: 126\", Unit 4: 90\"\nAny Quality, Any GSM allowed. Proceed?")) return;

  const itemsToAlloc = filteredData.value;
  if (itemsToAlloc.length === 0) return;

  // 1. Group by Quality + Color (same run together)
  const groups = {};
  const unallocated = [];
  const failedWidth = []; // Orders that don't fit ANY unit width-wise
  itemsToAlloc.forEach(item => {
    const key = `${item.quality}|${item.color}`;
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  });

  const updates = [];

  // 2. Process each group
  for (const key in groups) {
    const groupItems = groups[key];
    
    // Sort items by width DESC (Best Fit Decreasing - largest first)
    groupItems.sort((a, b) => (b.width || 0) - (a.width || 0));

    // ANY QUALITY on ANY UNIT - no quality filtering
    let allUnits = ["Unit 1", "Unit 2", "Unit 3", "Unit 4"];
    
    // Sort units by width DESCENDING (try largest first for grouping efficiency)
    allUnits.sort((a, b) => UNIT_WIDTHS[b] - UNIT_WIDTHS[a]);
    
    // Track batch loads
    const batchLoads = {};
    units.forEach(u => batchLoads[u] = 0);

    for (const item of groupItems) {
        const itemWidth = parseFloat(item.width || 0);
        const itemTonnage = (item.qty || 0) / 1000;
        
        let bestUnit = null;
        let minWaste = Infinity;
        
        // STRICT WIDTH CHECK: Try each unit
        for (const unit of allUnits) {
             const unitWidth = UNIT_WIDTHS[unit];
             const limit = UNIT_TONNAGE_LIMITS[unit];
             
             // ✅ CHECK 1: STRICT Width Fit (112" order CANNOT go to Unit 4 with 90" max)
             if (unitWidth >= itemWidth) {
                 // ✅ CHECK 2: Tonnage Capacity Available
                 if (batchLoads[unit] + itemTonnage <= limit) {
                     const waste = unitWidth - itemWidth;
                     // ✅ CHECK 3: Best Fit (minimize waste)
                     if (waste < minWaste) {
                         minWaste = waste;
                         bestUnit = unit;
                     }
                 }
             }
        }
        
        if (bestUnit) {
            // ✅ Successfully allocated
            updates.push({
                name: item.itemName,
                unit: bestUnit
            });
            batchLoads[bestUnit] += itemTonnage;
            console.log(`✅ ${item.itemName}: Width=${itemWidth}" → Unit=${bestUnit} (${UNIT_WIDTHS[bestUnit]}")`);
        } else if (!allUnits.some(u => UNIT_WIDTHS[u] >= itemWidth)) {
            // ❌ Width doesn't fit ANY unit
            console.error(`❌ ${item.itemName}: Width=${itemWidth}" exceeds max unit width (126")`);
            failedWidth.push(item);
        } else {
            // ⚠️ Width fits but no tonnage available
            console.warn(`⚠️ ${item.itemName}: Width fits but no tonnage capacity today`);
            unallocated.push(item);
        }
    }
  }

  // 3. Apply updates
  if (updates.length > 0) {
      try {
          updates.forEach(upd => {
             const item = rawData.value.find(d => d.itemName === upd.name);
             if (item) item.unit = upd.unit;
          });

          await frappe.call({
            method: "production_scheduler.api.update_items_bulk",
            args: { items: updates }
          });
          
          frappe.show_alert({ 
            message: `✅ Auto-allocated ${updates.length} orders with STRICT width enforcement`, 
            indicator: "green" 
          });
      } catch (e) {
          console.error(e);
          frappe.msgprint("❌ Error auto-allocating");
          fetchData(); 
      }
  }

  // 4. Report unallocated orders
  if (failedWidth.length > 0) {
      const totalWidth = failedWidth.reduce((s, i) => s + (i.width || 0), 0).toFixed(1);
      frappe.msgprint(`
        <strong>❌ ${failedWidth.length} ORDERS EXCEED MAXIMUM WIDTH (126"):</strong><br/>
        Total width: ${totalWidth}"<br/>
        <em>These orders cannot fit on ANY unit. Verify item codes or split orders.</em>
      `);
  }

  if (unallocated.length > 0) {
      const nextDate = frappe.datetime.add_days(filterOrderDate.value, 1);
      const totalUnallocated = unallocated.reduce((s, i) => s + (i.qty/1000), 0).toFixed(2);
      
      if (confirm(`⚠️ ${unallocated.length} orders (${totalUnallocated}T) don't fit TODAY's capacity (width OK, tonnage full).\n\nMove to ${nextDate}?`)) {
          const dateUpdates = unallocated.map(item => ({
              name: item.itemName,
              custom_item_planned_date: nextDate 
          }));
          
          try {
              await frappe.call({
                method: "production_scheduler.api.update_items_bulk",
                args: { items: dateUpdates }
              });
              frappe.show_alert({ message: `⏩ Moved ${unallocated.length} orders to ${nextDate}`, indicator: "orange" });
              rawData.value = rawData.value.filter(d => !unallocated.find(u => u.itemName === d.itemName));
          } catch (e) {
              console.error(e);
              frappe.msgprint("❌ Error moving items");
          }
      }
  }

  if (updates.length === 0 && failedWidth.length === 0 && unallocated.length === 0) {
      frappe.msgprint("✓ All items already allocated.");
  }
}



// ---- STATE PERSISTENCE (URL SYNC) ----
function updateUrlParams() {
  const url = new URL(window.location);
  
  if (filterOrderDate.value) url.searchParams.set('date', filterOrderDate.value);
  
  if (filterUnit.value) url.searchParams.set('unit', filterUnit.value);
  else url.searchParams.delete('unit');
  
  if (filterStatus.value) url.searchParams.set('status', filterStatus.value);
  else url.searchParams.delete('status');
  
  if (selectedPlan.value && selectedPlan.value !== "Default") url.searchParams.set('plan', selectedPlan.value);
  else url.searchParams.delete('plan');
  
  // Persist view state
  url.searchParams.set('view', viewMode.value);
  url.searchParams.set('scope', viewScope.value);
  
  if (viewScope.value === 'monthly' && filterMonth.value) url.searchParams.set('month', filterMonth.value);
  else url.searchParams.delete('month');
  
  if (viewScope.value === 'weekly' && filterWeek.value) url.searchParams.set('week', filterWeek.value);
  else url.searchParams.delete('week');
  
  window.history.replaceState({}, '', url);
}

// Watchers to sync state
watch(filterOrderDate, () => {
    updateUrlParams();
    // fetchData called by existing watcher
});
watch(filterUnit, updateUrlParams);
watch(filterStatus, updateUrlParams);
watch(selectedPlan, updateUrlParams);

// Re-init Sortable when renderKey changes (forced re-render)
// Skip if matrix — matrix init is handled by its own 150ms timer inside initSortable()
watch(renderKey, () => {
    nextTick(() => {
        if (viewMode.value !== 'matrix') {
            initSortable();
        }
    });
});

// Re-init sortable when switching between kanban/matrix views
watch(viewMode, async () => {
    updateUrlParams();
    await nextTick();
    initSortable();
});
watch(viewScope, async (newVal) => {
    updateUrlParams();
    if (newVal === 'daily') {
        initFlatpickr();
    }
    await fetchData();
});
watch(filterMonth, async () => {
    updateUrlParams();
    await fetchData();
});
watch(filterWeek, async () => {
    updateUrlParams();
    await fetchData();
    // Week Change Sync: Try to maintain the same plan "family" (e.g. MARCH W12 26 PLAN 1 -> MARCH W11 26 PLAN 1)
    if (selectedPlan.value && selectedPlan.value !== "Default") {
        const parts = filterWeek.value.split("-W");
        if (parts.length === 2) {
            const yShort = parts[0].slice(2);
            const wNo = parts[1];
            
            // Extract the base plan name (e.g. "PLAN 1")
            const baseMatch = selectedPlan.value.match(/W\d+\s+\d{2}\s+(.+)$/i) || selectedPlan.value.match(/^[A-Z]{3}-\d{2}\s+(.+)$/i);
            const baseName = baseMatch ? baseMatch[1] : selectedPlan.value;
            
            // Find its equivalent in the new list (matching by base name)
            const targetPlan = plans.value.find(p => {
                const pBase = p.name.replace(/^([A-Z]+[-\s]\d{2}|[A-Z]+(\s+W\d+)?(\s+\d{2})?)\s+/i, '');
                return pBase === baseName;
            });
            
            if (targetPlan) {
                selectedPlan.value = targetPlan.name;
            } else {
                selectedPlan.value = "Default";
            }
        }
    }
});

onMounted(async () => {
  // 1. Read URL Params
  const params = new URLSearchParams(window.location.search);
  const dateParam = params.get('date');
  const unitParam = params.get('unit');
  const statusParam = params.get('status');
  const viewParam = params.get('view');
  const scopeParam = params.get('scope');
  const monthParam = params.get('month');
  const weekParam = params.get('week');
  
  // Restore view mode and scope FIRST (before data fetch)
  if (viewParam && ['kanban', 'matrix'].includes(viewParam)) viewMode.value = viewParam;
  if (scopeParam && ['daily', 'weekly', 'monthly'].includes(scopeParam)) viewScope.value = scopeParam;
  if (monthParam) filterMonth.value = monthParam;
  if (weekParam) {
      filterWeek.value = weekParam;
  } else {
      // Default to current ISO week (e.g. 2026-W11)
      const now = new Date();
      const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
      const dayNum = d.getUTCDay() || 7;
      d.setUTCDate(d.getUTCDate() + 4 - dayNum);
      const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
      const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
      filterWeek.value = `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
  }
  
  if (dateParam) {
      filterOrderDate.value = dateParam;
  } else {
      if (!filterOrderDate.value) filterOrderDate.value = frappe.datetime.get_today();
  }
  
  // Dynamically load Flatpickr style and script if not already present
  if (!document.getElementById('flatpickr-style')) {
      const link = document.createElement('link');
      link.id = 'flatpickr-style';
      link.rel = 'stylesheet';
      link.href = 'https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css';
      document.head.appendChild(link);
  }

  frappe.require('https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.js', () => {
       if (viewScope.value === 'daily') {
           nextTick(() => {
               initFlatpickr();
           });
       }
  });
  
  if (unitParam) filterUnit.value = unitParam;
  if (statusParam) {
       if (["Draft", "Finalized"].includes(statusParam)) filterStatus.value = statusParam;
  }
  
  if (params.get('plan')) selectedPlan.value = params.get('plan');
  
  // 2. Fetch Data
  frappe.call({ method: "production_scheduler.api.cleanup_legacy_plans" });
  await fetchData();
  analyzePreviousFlow();
  
  // DEBUG: Check plan field status
  try {
      const dbg = await frappe.call("production_scheduler.api.debug_plan_check");
      console.log("[CC Debug] Plan field check:", JSON.stringify(dbg.message, null, 2));
  } catch(e) { console.warn("debug_plan_check failed:", e); }

  // 3. Realtime sync with backend moves
  if (frappe.realtime && frappe.realtime.on && !ccRealtimeHandlerRegistered) {
      try {
          frappe.realtime.on("production_board_update", handleRealtimeColorUpdate);
          ccRealtimeHandlerRegistered = true;
      } catch (e) {
          console.error("Failed to attach realtime handler (Color Chart)", e);
      }
  }
});

onBeforeUnmount(() => {
  if (ccRealtimeHandlerRegistered && frappe.realtime && frappe.realtime.off) {
      try {
          frappe.realtime.off("production_board_update", handleRealtimeColorUpdate);
      } catch (e) {
          console.error("Failed to detach realtime handler (Color Chart)", e);
      }
      ccRealtimeHandlerRegistered = false;
  }
});

const NO_RULE_WHITES = ["BRIGHT WHITE", "MILKY WHITE", "SUPER WHITE", "SUNSHINE WHITE", "BLEACH WHITE 1.0", "BLEACH WHITE 2.0"];
function isWhiteExempt(color) {
    if (!color) return false;
    return NO_RULE_WHITES.includes(color.toUpperCase().trim());
}

// ---- SHARED ACTION ----
async function handleMoveOrders(items, date, unit, plan, dialog) {
    try {
        const args = {
            item_names: items,
            target_date: date,
            target_unit: unit || ""
        };
        if (plan) args.plan_name = plan;

        const r = await frappe.call({
            method: "production_scheduler.api.move_orders_to_date",
            args: args,
            freeze: true
        });
        
        if (r.message && r.message.status === 'success') {
            const currentFilterDate = filterOrderDate.value;
            const targetDate = date;
            
            const successMsg = `Successfully moved ${r.message.count} orders to ${targetDate}.`;
            frappe.show_alert({ message: successMsg, indicator: 'green' });
            
            // If moved to a date not currently viewed, show a more prominent message
            if (targetDate !== currentFilterDate) {
                frappe.msgprint({
                    title: __('Orders Moved'),
                    indicator: 'green',
                    primary_action: {
                        label: `Go to ${targetDate}`,
                        action: () => {
                            filterOrderDate.value = targetDate;
                            fetchData();
                        }
                    },
                    message: `Moved ${r.message.count} orders to <b>${targetDate}</b>.<br>They are no longer on this board.`
                });
            }
            
            if (dialog) dialog.hide();
            
            // Comprehensive Refresh
            await fetchData();
            await analyzePreviousFlow(); // Keep sorting consistent with flow
        }
    } catch (e) {
        console.error("Move failed", e);
        
        // Robust Error Extraction
        let msg = "";
        
        const cleanError = (raw) => {
            if (!raw) return "";
            
            // If it's a string, try to parse it (it might be double-encoded JSON)
            if (typeof raw === 'string') {
                const trimmed = raw.trim();
                if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
                    try {
                        return cleanError(JSON.parse(trimmed));
                    } catch (err) {
                        return raw;
                    }
                }
                // If it's HTML, try to strip tags or return as is
                if (raw.includes('<div') || raw.includes('<p')) {
                    const temp = document.createElement('div');
                    temp.innerHTML = raw;
                    return temp.textContent || temp.innerText || raw;
                }
                return raw;
            }
            
            // If it's an array, join its elements
            if (Array.isArray(raw)) {
                return raw.map(cleanError).filter(Boolean).join("\n");
            }
            
            // If it's an object, prioritize 'message' or 'error' property
            if (typeof raw === 'object') {
                if (raw.message) return cleanError(raw.message);
                if (raw.error) return cleanError(raw.error);
                // Last resort: stringify
                try {
                    return cleanError(JSON.stringify(raw));
                } catch (err) {
                    return String(raw);
                }
            }
            
            return String(raw);
        };

        const serverMsgs = e.server_messages || e._server_messages || (e.responseJSON && e.responseJSON._server_messages);
        msg = cleanError(serverMsgs || e.message || e.error || e.responseText || e);
        
        // Final trim and cleanup
        msg = msg.split('\n').map(s => s.trim()).filter(Boolean).join('\n');
        
        if (msg && msg.toLowerCase().includes("capacity exceeded")) {
             // Propose Next Day
             const nextDay = frappe.datetime.add_days(date, 1);
             frappe.confirm(
                 `<b>Capacity Limit Reached!</b><br>${msg}<br><br>Do you want to move these orders to <b>${nextDay}</b> instead?`,
                 () => {
                     handleMoveOrders(items, nextDay, unit, dialog);
                 },
                 () => {
                     // No / Cancel -> Revert UI
                     renderKey.value++;
                 }
             );
         }
    }
}

async function openPushColorDialog(color, inputTargetDate = null) {
    // Determine the default target date based on what was passed in, falling back to the global filter or today
    const dialogTargetDate = inputTargetDate || filterOrderDate.value || frappe.datetime.get_today();
    
    // ── Available options for filters ──
    const allForColor = rawData.value.filter(d => {
        // ✅ FIX: Only push orders from selected plan
        if (selectedPlan.value && selectedPlan.value !== 'Default') {
            if (d.planName !== selectedPlan.value && d.planName !== selectedPlanLabel.value) return false;
        } else {
            if (d.planName && d.planName !== '' && d.planName !== 'Default') return false;
        }
        
        if ((d.color || "").toUpperCase().trim() !== color.toUpperCase().trim()) return false;
        const colorUpper = (d.color || "").toUpperCase().trim();
        if (colorUpper === "WHITE" || colorUpper === "BRIGHT WHITE") return false;
        if (filterUnit.value && (d.unit || "UNASSIGNED") !== filterUnit.value) return false;
        if (filterStatus.value && d.planningStatus !== filterStatus.value) return false;
        return true;
    });

    // Active filter state
    let fQuality = "";
    let fPartyCode = "";
    let fGsm = "";

    function getFilteredItems() {
        return allForColor.filter(d => {
            if (isRowAlreadyPushed(d)) return false; // already pushed
            if (fQuality && (d.quality || "").toUpperCase().trim() !== fQuality.toUpperCase().trim()) return false;
            if (fPartyCode && (d.partyCode || "").toUpperCase().indexOf(fPartyCode.toUpperCase()) === -1) return false;
            if (fGsm && String(d.gsm || "").trim() !== String(fGsm).trim()) return false;
            return true;
        });
    }

    let items = getFilteredItems();

    if (allForColor.filter(d => !isRowAlreadyPushed(d)).length === 0) {
        frappe.msgprint("No eligible items found. (Note: White orders are auto-allocated and do not need to be pushed manually, and already-pushed items are hidden.)");
        return;
    }

    // Build unique quality/gsm options for datalists
    const qualities = [...new Set(allForColor.map(d => (d.quality || "").trim()).filter(Boolean))];
    const gsmOptions = [...new Set(allForColor.map(d => String(d.gsm || "").trim()).filter(Boolean))];

    const d = new frappe.ui.Dialog({
        title: `📤 Push ${color} to Production Board`,
        fields: [
            { fieldname: "target_date", label: "Target Date", fieldtype: "Date", reqd: 1, default: dialogTargetDate },
            { fieldname: "target_unit", label: "Target Unit", fieldtype: "Select", options: "\nUnit 1\nUnit 2\nUnit 3\nUnit 4", description: "Unit to push items to. Leave blank to preserve item's current unit." },
            { fieldname: "filters_info", label: "Filters", fieldtype: "HTML" },
            { fieldname: "items_info", label: "Order Selection", fieldtype: "HTML" }
        ],
        primary_action_label: "Push to Production Board",
        primary_action: async () => {
             items = getFilteredItems();
             const selected = d.calc_selected_items || [];
             if (!selected.length) { frappe.msgprint("Please select at least one order."); return; }
             
             const targetDate = d.get_value("target_date");
             const pbPlan = selectedPlanLabel.value;

             const selectedMap = new Map(selected.map(s => [s.name, s]));
             const selectedItems = allForColor.filter(x => selectedMap.has(x.itemName || x.name));

             // Compute additional load requested on target date per unit (in tons).
             const addByUnit = {};
             selectedItems.forEach(it => {
                 const key = it.itemName || it.name;
                 const sel = selectedMap.get(key);
                 const unit = (sel && sel.target_unit) ? sel.target_unit : (it.unit || "Unit 1");
                 const wt = (parseFloat(it.qty || 0) || 0) / 1000;
                 addByUnit[unit] = (addByUnit[unit] || 0) + wt;
             });

             let shouldAskCascade = false;
             let overflowLines = [];
             try {
                 const capRes = await frappe.call({
                     method: "production_scheduler.api.get_multiple_dates_capacity",
                     args: { dates: targetDate, plan_name: "__all__", pb_only: 1 },
                     freeze: false
                 });
                 const caps = capRes.message || {};

                 Object.keys(addByUnit).forEach(unit => {
                     const c = caps[unit] || { total_limit: 999, total_load: 0 };
                     const limit = parseFloat(c.total_limit || 0) || 0;
                     const load = parseFloat(c.total_load || 0) || 0;
                     const add = addByUnit[unit] || 0;
                     const projected = load + add;
                     if (projected > (limit * 1.05)) {
                         shouldAskCascade = true;
                         overflowLines.push(`${unit}: ${projected.toFixed(2)}T / ${limit.toFixed(2)}T`);
                     }
                 });
             } catch (e) {
                 console.warn("Capacity pre-check failed; proceeding with push on target date only (no cascade)", e);
             }

            const doPush = async () => {
                 const dialogTargetUnit = d.get_value("target_unit");
                 const payload = selected.map(s => ({
                     name: s.name,
                     target_unit: dialogTargetUnit || s.target_unit,
                     target_date: targetDate,
                    strict_target_date: 1
                 }));

                 d.get_primary_btn().prop("disabled", true).text("Pushing...");
                 try {
                     const r = await frappe.call({
                         method: "production_scheduler.api.push_items_to_pb",
                        args: { items_data: JSON.stringify(payload), pb_plan_name: pbPlan, approve_cross_month: 0, approve_maintenance_move: 0 },
                         freeze: true
                     });
                    if (r.message && r.message.status === "maintenance_move_approval_required") {
                        const rows = (r.message.candidates || []).slice(0, 15)
                          .map(c => `• ${c.party_code || '-'} | ${c.item_code || c.item_name || '-'} | ${c.from_date} → ${c.to_date} | ${c.qty} Kg`)
                          .join("<br>");
                        const more = (r.message.count || 0) > 15 ? `<br>...and ${(r.message.count || 0) - 15} more` : "";
                        const ok = await new Promise(resolve => {
                          frappe.confirm(
                            `<b>${r.message.count || 0} orders are on maintenance dates.</b><br><br>${rows}${more}<br><br>Approve moving these to shown dates?`,
                            () => resolve(true),
                            () => resolve(false)
                          );
                        });
                        if (!ok) {
                            d.get_primary_btn().prop("disabled", false).text("Push to Production Board");
                            return;
                        }
                        const r2 = await frappe.call({
                          method: "production_scheduler.api.push_items_to_pb",
                          args: { items_data: JSON.stringify(payload), pb_plan_name: pbPlan, approve_maintenance_move: 1, approve_cross_month: 0 },
                          freeze: true
                        });
                        if (r2.message) {
                          r.message = r2.message;
                        }
                    }
                    if (r.message && r.message.status === "cross_month_approval_required") {
                        const rows = (r.message.candidates || []).slice(0, 15)
                          .map(c => `• ${c.party_code || '-'} | ${c.item_code || c.item_name || '-'} | ${c.from_date} → ${c.to_date} | ${c.qty} Kg`)
                          .join("<br>");
                        const more = (r.message.count || 0) > 15 ? `<br>...and ${(r.message.count || 0) - 15} more` : "";
                        const ok = await new Promise(resolve => {
                          frappe.confirm(
                            `<b>${r.message.count || 0} orders will move to next month.</b><br><br>${rows}${more}<br><br>Approve and continue?`,
                            () => resolve(true),
                            () => resolve(false)
                          );
                        });
                        if (!ok) {
                            d.get_primary_btn().prop("disabled", false).text("Push to Production Board");
                            return;
                        }
                        const r2 = await frappe.call({
                          method: "production_scheduler.api.push_items_to_pb",
                          args: { items_data: JSON.stringify(payload), pb_plan_name: pbPlan, approve_cross_month: 1, approve_maintenance_move: 1 },
                          freeze: true
                        });
                        if (r2.message) {
                          r.message = r2.message;
                        }
                    }
                     if (r.message && r.message.status === 'success') {
                         d.get_primary_btn().text("✅ Pushed").css({"background-color": "#10b981", "color": "white"});
                         let dateMsg = '';
                        if (r.message.dates && r.message.dates.length > 0) {
                            dateMsg = ` to ${r.message.dates.join(', ')}`;
                        }
                        let whiteShiftMsg = '';
                        if ((r.message.white_shifted_count || 0) > 0) {
                            const wDates = (r.message.white_shifted_dates || []).join(', ');
                            whiteShiftMsg = ` Whites shifted: ${r.message.white_shifted_count}` + (wDates ? ` (${wDates})` : '');
                        }
                        frappe.show_alert({
                            message: `✅ Pushed ${r.message.count} order(s)${dateMsg} to Plan "${r.message.plan_name || pbPlan}".${whiteShiftMsg}`,
                            indicator: 'green'
                        });
                         setTimeout(() => { d.hide(); fetchData(); }, 1000);
                     } else {
                         frappe.msgprint(r.message?.message || "Push failed");
                         d.get_primary_btn().prop("disabled", false).text("Push to Production Board");
                     }
                 } catch(e) {
                     console.error("Push Error", e);
                     frappe.msgprint("Error pushing to Production Board.");
                     d.get_primary_btn().prop("disabled", false).text("Push to Production Board");
                 }
             };

             if (shouldAskCascade) {
                 const html = `<b>Capacity is full on ${targetDate}.</b><br>` +
                              `Projected load exceeds limit for:<br>${overflowLines.join('<br>')}<br><br>` +
                             `Please change target date and check capacity again.<br>` +
                             `Cascading is disabled.`;
                frappe.msgprint(html);
                 return;
             }

            await doPush();
        }
    });

    let smartActive = false;

    // Render item rows (re-renderable after Smart Sort)
    function renderItemRows(orderedItems) {
        let html = `
            <div style="max-height: 320px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff;">
                <div style="position: sticky; top: 0; background: #f8fafc; z-index: 10; padding: 10px; border-bottom: 1px solid #e2e8f0; display:flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 12px; color: #64748b;">
                    <div><input type="checkbox" checked class="push-select-all" /> Select All</div>
                    ${smartActive ? '<span style="font-size:11px;color:#1b5e20;background:#e8f5e9;padding:3px 8px;border-radius:10px;">✅ Smart Sequence Active</span>' : ''}
                </div>
                <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                    <thead style="background:#f1f5f9; color:#475569; border-bottom:1px solid #cbd5e1; text-align:left;">
                        <tr>
                            <th style="padding:6px;width:30px;text-align:center;">✓</th>
                            <th style="padding:6px;">Order Details</th>
                            <th style="padding:6px;width:110px;">Unit</th>
                            <th style="padding:6px;text-align:right;width:80px;">Qty</th>
                        </tr>
                    </thead>
                    <tbody>`;

        orderedItems.forEach(item => {
            let unit = item.unit || "Unit 1";
            if (unit === "UNASSIGNED") unit = "Unit 1";
            const phaseBg = item._phase === 'white' ? '#f0fdf4' : item._phase === 'color' ? '#fffbeb' : '#fff';
            html += `
                <tr style="border-bottom: 1px solid #f1f5f9; background:${phaseBg};">
                    <td style="padding: 8px; text-align:center; width:30px;">
                        <input type="checkbox" class="push-chk" value="${item.itemName}" checked />
                    </td>
                    <td style="padding: 8px;">
                        <div><b style="color:#1e293b;">${item.partyCode}</b></div>
                        <div style="color:#64748b; font-size:10px; margin-top:2px;">${item.quality} · ${item.gsm} GSM · ${item.color}</div>
                    </td>
                    <td style="padding: 8px; width: 110px;">
                        <select class="push-unit-sel" data-item="${item.itemName}" style="width:100%; padding:4px; font-size:11px; border:1px solid #cbd5e1; border-radius:4px; background:#fff; cursor:pointer;">
                            <option value="Unit 1" ${unit === 'Unit 1' ? 'selected' : ''}>Unit 1</option>
                            <option value="Unit 2" ${unit === 'Unit 2' ? 'selected' : ''}>Unit 2</option>
                            <option value="Unit 3" ${unit === 'Unit 3' ? 'selected' : ''}>Unit 3</option>
                            <option value="Unit 4" ${unit === 'Unit 4' ? 'selected' : ''}>Unit 4</option>
                        </select>
                    </td>
                    <td style="padding: 8px; text-align:right; width:80px;"><b>${item.qty ? parseFloat(item.qty).toFixed(0) : 0} Kg</b></td>
                </tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    }

    d.set_value("filters_info", `
        <div style="display:flex;gap:8px;flex-wrap:wrap;padding:6px 0 2px 0;">
            <div style="display:flex;flex-direction:column;gap:2px;">
                <label style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;">Quality</label>
                <input id="push-filter-quality" list="push-qual-list" placeholder="All" value="${fQuality}" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;width:140px;">
                <datalist id="push-qual-list">${qualities.map(q => `<option value="${q}">`).join('')}</datalist>
            </div>
            <div style="display:flex;flex-direction:column;gap:2px;">
                <label style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;">Party Code</label>
                <input id="push-filter-party" placeholder="Search party..." value="${fPartyCode}" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;width:140px;">
            </div>
            <div style="display:flex;flex-direction:column;gap:2px;">
                <label style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;">GSM</label>
                <input id="push-filter-gsm" list="push-gsm-list" placeholder="All" value="${fGsm}" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;width:80px;">
                <datalist id="push-gsm-list">${gsmOptions.map(g => `<option value="${g}">`).join('')}</datalist>
            </div>
        </div>
    `);

    function bindFilterEvents() {
        d.fields_dict.filters_info.$wrapper.find('#push-filter-quality').off('input').on('input', function() {
            fQuality = this.value;
            refreshItemList();
        });
        d.fields_dict.filters_info.$wrapper.find('#push-filter-party').off('input').on('input', function() {
            fPartyCode = this.value;
            refreshItemList();
        });
        d.fields_dict.filters_info.$wrapper.find('#push-filter-gsm').off('input').on('input', function() {
            fGsm = this.value;
            refreshItemList();
        });
    }

    function refreshItemList() {
        items = getFilteredItems();
        d.set_value("items_info", renderItemRows(items));
        setTimeout(() => { wireItemEvents(); bindFilterEvents(); }, 100);
    }

    d.set_value("items_info", renderItemRows(items));

    // Track selections
    window.updatePushSelection = () => {
        const selected = [];
        d.fields_dict.items_info.$wrapper.find('.push-chk').each(function() {
            if (this.checked) {
                const itemName = this.value;
                const sel = d.fields_dict.items_info.$wrapper.find(`.push-unit-sel[data-item="${itemName}"]`);
                selected.push({ name: itemName, target_unit: sel.length ? sel.val() : "Unit 1" });
            }
        });
        d.calc_selected_items = selected;
    };

    function wireItemEvents() {
        const wrapper = d.fields_dict.items_info.$wrapper;
        const selectAll = wrapper.find('.push-select-all');
        const checkboxes = wrapper.find('.push-chk');
        const selects = wrapper.find('.push-unit-sel');
        
        selectAll.on('change', function() {
            checkboxes.prop('checked', this.checked);
            window.updatePushSelection();
        });
        checkboxes.on('change', function() {
            selectAll.prop('checked', checkboxes.length === checkboxes.filter(':checked').length);
            window.updatePushSelection();
        });
        selects.on('change', () => window.updatePushSelection());
        window.updatePushSelection();
    }

    // Initial load - wait for DOM
    setTimeout(() => { wireItemEvents(); bindFilterEvents(); }, 200);

    d.show();
}

async function goToConfirmedOrders() {
    frappe.set_route("confirmed-order");
}

async function goToSequenceApprovals() {
    frappe.set_route("sequence-approval");
}

async function revertColorGroup(color) {
    if (!confirm(`Revert pushed items for color "${color}" back to the Color Chart?`)) return;
    
    // ✅ FIX: Only revert items from the selected plan
    const itemsToRevert = rawData.value.filter(d => {
        if (selectedPlan.value && selectedPlan.value !== 'Default') {
            if (d.planName !== selectedPlan.value && d.planName !== selectedPlanLabel.value) return false;
        } else {
            if (d.planName && d.planName !== '' && d.planName !== 'Default') return false;
        }
        return d.color === color && isRowAlreadyPushed(d);
    });
    
    if (itemsToRevert.length === 0) {
        frappe.msgprint(`No pushed orders found for ${color}.`);
        return;
    }
    
    const itemNames = itemsToRevert.map(d => d.itemName);
    
    try {
        const r = await frappe.call({
            method: "production_scheduler.api.revert_items_to_color_chart",
            args: { item_names: JSON.stringify(itemNames) }
        });
        if (r.message && r.message.status === 'success') {
            frappe.show_alert({ message: `✅ Reverted ${r.message.reverted_items} item(s) across ${r.message.sheets_checked} planning sheet(s).`, indicator: 'green' });
            fetchData();
        } else {
            frappe.msgprint(r.message?.message || "Revert failed.");
        }
    } catch(e) {
        console.error("Revert Error", e);
        frappe.msgprint("Error communicating with revert API.");
    }
}

async function restoreWhiteOrders() {
    try {
        const r = await frappe.call("production_scheduler.api.fix_recently_cleared_whites");
        if (r.message && r.message.status === 'success') {
            frappe.show_alert({ message: `✅ Restored ${r.message.restored_count} white orders to the Board.`, indicator: 'green' });
            hasRecentlyReset.value = false;
            fetchData();
        }
    } catch(e) {
        console.error("Restoration Error", e);
    }
}

async function emergencyReset() {
    frappe.confirm(
        "<b>⚠️ CRITICAL WARNING</b><br><br>This will find EVERY color order currently marked as 'Pushed' and unlock them, returning them to the Color Chart.<br><br>White orders will remain safely on the Board.<br><br>Are you sure you want to perform a <b>FULL RESET</b>?",
        async () => {
            try {
                const r = await frappe.call({
                    method: "production_scheduler.api.emergency_cleanup_all_pushed_status",
                    freeze: true
                });
                if (r.message && r.message.status === 'success') {
                    frappe.show_alert({ message: r.message.message, indicator: 'green' });
                    hasRecentlyReset.value = true;
                    fetchData();
                }
            } catch (e) {
                console.error("Emergency Reset Error", e);
            }
        }
    );
}

// ---- PULL ORDERS FROM FUTURE ----
function openPullOrdersDialog() {
    const nextDay = frappe.datetime.add_days(filterOrderDate.value, 1);
    
    // Create Dialog
    const d = new frappe.ui.Dialog({
        title: '📥 Pull Orders from Date',
        fields: [
            {
                label: 'Source Date',
                fieldname: 'source_date',
                fieldtype: 'Date',
                default: nextDay,
                reqd: 1,
                onchange: () => loadOrders(d)
            },
            {
                label: 'Target Unit (Optional)',
                fieldname: 'target_unit',
                fieldtype: 'Select',
                options: [
                    { label: 'Keep Original Unit', value: '' },
                    ...units.map(u => ({ label: `Move to ${u}`, value: u }))
                ],
                default: '',
                description: 'If selected, all pulled orders will be assigned to this unit.'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'preview_html'
            }
        ],
        primary_action_label: 'Move Selected to Today',
        primary_action: () => {
            const selected = d.calc_selected_items || [];
            if (selected.length === 0) {
                frappe.msgprint("Please select at least one order.");
                return;
            }
            const targetUnit = d.get_value('target_unit');
            handleMoveOrders(selected, filterOrderDate.value, targetUnit, d);
        }
    });
    
    d.show();
    // Initial Load
    loadOrders(d);
}

async function loadOrders(d) {
    const date = d.get_value('source_date');
    if (!date) return;
    
    d.set_value('preview_html', '<p class="text-gray-500 italic p-2">Loading...</p>');
    
    try {
        const r = await frappe.call({
            method: "production_scheduler.api.get_color_chart_data",
            args: { date: date, mode: 'pull' }
        });
        
        const items = r.message || [];
        if (items.length === 0) {
            d.set_value('preview_html', '<p class="text-gray-500 italic p-2">No active orders found for this date.</p>');
            d.calc_selected_items = [];
            return;
        }
        
        // --- FE FILTERS ---
        const uniqueUnits = [...new Set(items.map(i => i.unit || 'UNASSIGNED'))].sort();
        const uniqueQualities = [...new Set(items.map(i => i.quality || 'STD'))].sort();
        const uniqueParties = [...new Set(items.map(i => i.partyCode || i.customer || ''))].filter(Boolean).sort();
        
        let activeFilters = { unit: '', quality: '', party: '', color: '' };
        
        function buildFilterBar() {
            return `
            <div id="pull-filter-bar" style="background:#f8fafc; border:1px solid #e5e7eb; border-radius:6px; padding:10px 12px; margin-bottom:10px;">
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                    <span style="font-size:11px; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:.5px;">Filter</span>
                    
                    <select id="pull-filter-unit" style="font-size:11px; padding:2px 6px; border-radius:4px; border:1px solid #cbd5e1; background:#fff;">
                        <option value="">All Units</option>
                        ${uniqueUnits.map(u => `<option value="${u}">${u}</option>`).join('')}
                    </select>
                    
                    <select id="pull-filter-quality" style="font-size:11px; padding:2px 6px; border-radius:4px; border:1px solid #cbd5e1; background:#fff;">
                        <option value="">All Qualities</option>
                        ${uniqueQualities.map(q => `<option value="${q}">${q}</option>`).join('')}
                    </select>

                    <select id="pull-filter-party" style="font-size:11px; padding:2px 6px; border-radius:4px; border:1px solid #cbd5e1; background:#fff;">
                        <option value="">All Parties</option>
                        ${uniqueParties.map(p => `<option value="${p}">${p}</option>`).join('')}
                    </select>
                    
                    <input id="pull-filter-color" type="text" placeholder="Color..." style="font-size:11px; padding:2px 8px; border-radius:4px; border:1px solid #cbd5e1; width:110px;">
                    
                    <button id="pull-filter-reset" style="font-size:11px; padding:2px 8px; border-radius:4px; border:1px solid #cbd5e1; background:#fff; color:#dc2626; cursor:pointer;">✕ Reset</button>
                </div>
            </div>`;
        }
        
        function applyFilters() {
            return items.filter(i => {
                if (activeFilters.unit) {
                    let u = i.unit || 'UNASSIGNED';
                    if (u !== activeFilters.unit) return false;
                }
                if (activeFilters.quality) {
                    let q = i.quality || 'STD';
                    if (q !== activeFilters.quality) return false;
                }
                if (activeFilters.party) {
                    let p = i.partyCode || i.customer || '';
                    if (p !== activeFilters.party) return false;
                }
                if (activeFilters.color) {
                    let c = (i.color || '').toLowerCase();
                    if (!c.includes(activeFilters.color.toLowerCase())) return false;
                }
                return true;
            });
        }
        
        function renderItemsList() {
            let filtered = applyFilters();
            
            let html = buildFilterBar();
            
            if (filtered.length === 0) {
                html += '<div style="padding: 20px; text-align: center; color: #94a3b8; font-style: italic;">No orders match the current filters.</div>';
            } else {
                html += `
                <div style="max-height: 400px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff;">
                    <div style="position: sticky; top: 0; background: #f8fafc; z-index: 10; padding: 10px 12px; border-bottom: 1px solid #e2e8f0; display: grid; grid-template-columns: 40px 80px 1fr 100px; gap: 8px; font-weight: 600; font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">
                        <div style="display:flex; align-items:center; justify-content:center;"><input type="checkbox" id="select-all-pull" style="cursor:pointer;" /></div>
                        <div>Unit</div>
                        <div>Order Details</div>
                        <div style="text-align:right;">Qty</div>
                    </div>
                    <div style="display: flex; flex-direction: column;">
                `;
                
                filtered.forEach(item => {
                    const isChecked = d.calc_selected_items && d.calc_selected_items.includes(item.itemName) ? "checked" : "";
                    
                    // Quality Badge Color
                    const q = (item.quality || '').toUpperCase();
                    let qBadgeColor = '#e2e8f0';
                    let qTextColor = '#475569';
                    if (q.includes('PLATINUM')) { qBadgeColor = '#e0e7ff'; qTextColor = '#3730a3'; }
                    else if (q.includes('GOLD')) { qBadgeColor = '#fef3c7'; qTextColor = '#92400e'; }
                    else if (q.includes('PREMIUM')) { qBadgeColor = '#dcfce7'; qTextColor = '#166534'; }
                    
                    html += `
                        <div class="pull-item-row" style="display: grid; grid-template-columns: 40px 80px 1fr 100px; gap: 8px; padding: 10px 12px; border-bottom: 1px solid #f1f5f9; align-items: center; transition: background 0.2s;">
                            <div style="display:flex; align-items:center; justify-content:center;">
                                <input type="checkbox" class="pull-item-cb" data-name="${item.itemName}" style="cursor:pointer; transform: scale(1.1);" ${isChecked} />
                            </div>
                            
                            <!-- Unit -->
                            <div>
                                <span style="font-size: 11px; font-weight: 700; color: #64748b; background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">
                                    ${item.unit || 'UNASSIGNED'}
                                </span>
                            </div>
                            
                            <!-- Details -->
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <span style="font-size: 13px; font-weight: 600; color: #1e293b;">
                                    ${item.color || 'No Color'}
                                    <span style="font-weight: 400; color: #94a3b8; font-size: 12px; margin-left: 4px;">
                                        &bull; <span style="color: #0f172a;">${item.partyCode || item.customer || '-'}</span>
                                    </span>
                                </span>
                                
                                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 2px;">
                                    <!-- Color Badge -->
                                    <span style="display: inline-flex; align-items: center; gap: 4px; border: 1px solid #e2e8f0; padding: 1px 6px; border-radius: 99px; font-size: 11px; background: #fff;">
                                        <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color: ${getHexColor(item.color)}; box-shadow: 0 0 0 1px rgba(0,0,0,0.1);"></span>
                                        <span style="color: #334155; font-weight: 500;">${item.color || 'No Color'}</span>
                                    </span>
                                    
                                    <!-- Quality Badge -->
                                    <span style="font-size: 10px; font-weight: 600; background: ${qBadgeColor}; color: ${qTextColor}; padding: 1px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.3px;">
                                        ${item.quality || 'STD'}
                                    </span>
                                    
                                    <!-- GSM Badge -->
                                    <span style="font-size: 10px; font-weight: 600; background: #f3f4f6; color: #4b5563; padding: 1px 6px; border-radius: 4px;">
                                        ${item.gsm ? item.gsm + ' GSM' : 'N/A'}
                                    </span>
                                </div>
                            </div>
                            
                            <!-- Qty -->
                            <div style="text-align: right;">
                                <span style="display: block; font-size: 14px; font-weight: 700; color: #0f172a;">${(item.qty/1000).toFixed(2)} T</span>
                            </div>
                        </div>
                    `;
                });
                html += `</div></div>`;
            }
            
            html += `<div style="margin-top:8px; text-align:right; font-weight:600; font-size:12px; color:#64748b;">Filtered Orders: ${filtered.length} / ${items.length}</div>`;
            d.set_value('preview_html', html);
            
            d.$wrapper.find('#pull-filter-unit').val(activeFilters.unit);
            d.$wrapper.find('#pull-filter-quality').val(activeFilters.quality);
            d.$wrapper.find('#pull-filter-party').val(activeFilters.party);
            d.$wrapper.find('#pull-filter-color').val(activeFilters.color);
            d.$wrapper.find('#pull-filter-color').get(0)?.focus();
            
            bindListeners();
        }
        
        function bindListeners() {
            d.$wrapper.find('#pull-filter-unit, #pull-filter-quality, #pull-filter-party').on('change', function() {
                activeFilters.unit = d.$wrapper.find('#pull-filter-unit').val();
                activeFilters.quality = d.$wrapper.find('#pull-filter-quality').val();
                activeFilters.party = d.$wrapper.find('#pull-filter-party').val();
                renderItemsList();
            });
            d.$wrapper.find('#pull-filter-color').on('input', function() {
                activeFilters.color = $(this).val();
                renderItemsList();
            });
            d.$wrapper.find('#pull-filter-reset').on('click', function(e) {
                e.preventDefault();
                activeFilters = { unit: '', quality: '', party: '', color: '' };
                renderItemsList();
            });
            
            d.$wrapper.find('#select-all-pull').on('change', function() {
                const checked = $(this).prop('checked');
                d.$wrapper.find('.pull-item-cb').prop('checked', checked);
                updateSelection(d);
            });
            d.$wrapper.find('.pull-item-cb').on('change', function() {
                updateSelection(d);
            });
        }
        
        d.calc_selected_items = [];
        renderItemsList();
        
    } catch (e) {
        console.error(e);
        d.set_value('preview_html', '<p class="text-red-500">Error loading orders.</p>');
    }
}

function updateSelection(d) {
    let currentHtmlNames = new Set();
    d.$wrapper.find('.pull-item-cb').each(function() {
        currentHtmlNames.add($(this).data('name'));
    });
    
    const visibleSelected = [];
    d.$wrapper.find('.pull-item-cb:checked').each(function() {
        visibleSelected.push($(this).data('name'));
    });
    
    // Retain hidden selections
    const hiddenSelected = (d.calc_selected_items || []).filter(s => !currentHtmlNames.has(s));
    
    d.calc_selected_items = [...hiddenSelected, ...visibleSelected];
    d.get_primary_btn().text(`Move ${d.calc_selected_items.length} to Today`);
}

// ---- ADMIN RESCUE ----
// (isAdmin is now defined near the top of the script section)

function openRescueDialog() {
    const d = new frappe.ui.Dialog({
        title: '🚑 Rescue / Re-Queue Orders',
        fields: [
            {
                label: 'Source Planning Sheet',
                fieldname: 'sheet',
                fieldtype: 'Link',
                options: 'Planning sheet',
                reqd: 1,
                description: 'Select the sheet containing the lost/stuck orders.',
                onchange: () => loadRescueItems(d)
            },
            {
                label: 'Target Unit (Optional)',
                fieldname: 'target_unit',
                fieldtype: 'Select',
                options: [
                    { label: 'Keep Original Unit', value: '' },
                    ...units.map(u => ({ label: `Move to ${u}`, value: u }))
                ],
                default: '',
                description: 'If selected, all rescued orders will be assigned to this unit.'
            },
            {
                fieldtype: 'HTML',
                fieldname: 'rescue_html'
            }
        ],
        primary_action_label: 'Rescue Selected',
        primary_action: () => {
            const selected = d.calc_selected_rescue || [];
            if (selected.length === 0) {
                frappe.msgprint("Select at least one order to rescue.");
                return;
            }
            const targetUnit = d.get_value('target_unit');
            handleMoveOrders(selected, filterOrderDate.value, targetUnit, d);
        }
    });
    d.show();
}

async function loadRescueItems(d) {
    const sheet = d.get_value('sheet');
    if (!sheet) return;
    
    d.set_value('rescue_html', 'Loading...');
    
    try {
        const r = await frappe.call({
            method: "production_scheduler.api.get_items_by_sheet",
            args: { sheet_name: sheet }
        });
        
        const items = r.message || [];
        if (items.length === 0) {
            d.set_value('rescue_html', 'No items found in this sheet.');
            return;
        }
        
        // Simple List for Rescue
        let html = `
            <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ccc; margin-top:10px;">
                <table class="table table-bordered table-sm" style="margin:0;">
                    <thead>
                        <tr style="background:#f0f0f0;">
                            <th width="30"><input type="checkbox" id="select-all-rescue"></th>
                            <th>Item</th>
                            <th>Unit</th>
                            <th>Qty</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        items.forEach(item => {
            html += `
                <tr>
                    <td><input type="checkbox" class="rescue-cb" data-name="${item.name}"></td>
                    <td>${item.item_name} <br> <span class="text-muted" style="font-size:10px;">${item.name}</span></td>
                    <td>${item.unit || '-'}</td>
                    <td>${item.qty}</td>
                    <td>${item.docstatus === 0 ? 'Draft' : item.docstatus === 1 ? 'Submitted' : 'Cancelled'}</td>
                </tr>
            `;
        });
        
        html += `</tbody></table></div>`;
        d.set_value('rescue_html', html);
        
        // Bind Logic
        d.$wrapper.find('#select-all-rescue').on('change', function() {
            d.$wrapper.find('.rescue-cb').prop('checked', $(this).prop('checked'));
            updateRescueSelection(d);
        });
        
        d.$wrapper.find('.rescue-cb').on('change', () => updateRescueSelection(d));
        
        d.calc_selected_rescue = [];
        
    } catch (e) {
        d.set_value('rescue_html', 'Error loading items.');
    }
}

function updateRescueSelection(d) {
    const s = [];
    d.$wrapper.find('.rescue-cb:checked').each(function() {
        s.push($(this).data('name'));
    });
    d.calc_selected_rescue = s;
    d.get_primary_btn().text(`Rescue ${s.length} Orders`);
}
</script>

<style scoped>
/* ---- LAYOUT ---- */
.cc-container {
  padding: 16px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #f1f5f9;
  min-height: 100vh;
}

.cc-filters {
  display: flex;
  gap: 14px;
  align-items: flex-end;
  margin-bottom: 18px;
  padding: 14px 18px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  flex-wrap: wrap;
}

.cc-filter-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cc-filter-item label {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.cc-filter-item input,
.cc-filter-item select {
  padding: 6px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  background: #f8fafc;
}

.cc-direction-btn {
  padding: 6px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  background: #f8fafc;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s;
}

.cc-direction-btn:hover {
  background: #e2e8f0;
}

.cc-clear-btn {
  padding: 6px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 12px;
  background: #fff;
  cursor: pointer;
  color: #ef4444;
  font-weight: 600;
  transition: all 0.2s;
}

.cc-clear-btn:hover {
  background: #fef2f2;
  border-color: #ef4444;
}

/* ---- BOARD ---- */
.cc-board {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  padding-bottom: 20px;
}

.cc-column {
  flex: 0 0 280px;
  background: #f8fafc;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 180px);
}

.cc-col-header {
  padding: 12px 14px;
  background: #fff;
  border-top: 4px solid transparent;
  border-bottom: 1px solid #e2e8f0;
  border-radius: 12px 12px 0 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cc-header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.cc-unit-controls {
  display: flex;
  gap: 4px;
}

.cc-mini-btn {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 12px;
  color: #4a5568;
  transition: all 0.2s;
  display: flex; 
  align-items: center;
  justify-content: center;
  min-width: 24px;
}

.cc-mini-btn:hover {
  background: #f7fafc;
  border-color: #cbd5e0;
}

.cc-status-badge {
  font-size: 8px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  margin-left: 6px;
  letter-spacing: 0.05em;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.cc-status-badge.draft {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.cc-status-badge.pending-approval {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
  animation: pulse 2s infinite;
}

.cc-status-badge.approved {
  background: #ecfdf5;
  color: #065f46;
  border: 1px solid #6ee7b7;
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.02); opacity: 0.8; }
  100% { transform: scale(1); opacity: 1; }
}

.cc-col-title {
  font-weight: 700;
  font-size: 14px;
  color: #1e293b;
}

.cc-col-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.cc-stat-weight {
  font-size: 13px;
  font-weight: 700;
  color: #3b82f6;
}

.cc-stat-mix {
  font-size: 10px;
  font-weight: 600;
  color: #f59e0b;
}

.cc-header-status-badge {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: bold;
    text-transform: uppercase;
    margin-top: 4px;
    display: inline-block;
}
.cc-header-status-badge.draft { background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }
.cc-header-status-badge.pending-approval { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.cc-header-status-badge.approved { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }

.cc-approval-actions {
    margin-top: 4px;
    display: flex;
    gap: 4px;
}
.cc-approve-btn {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid transparent;
    cursor: pointer;
    font-weight: 600;
    transition: all 0.2s;
}
.cc-approve-btn.request { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }
.cc-approve-btn.request:hover { background: #dbeafe; }
.cc-approve-btn.approve { background: #10b981; color: white; }
.cc-approve-btn.approve:hover { background: #059669; }

.cc-maintenance-indicator {
  padding: 8px 12px;
  background-color: #fee2e2;
  border: 2px solid #dc2626;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #991b1b;
  text-align: center;
  margin: 0 10px;
}

.cc-col-body {
  padding: 10px;
  overflow-y: auto;
  flex-grow: 1;
  min-height: 200px;
}

.cc-col-body::-webkit-scrollbar { width: 4px; }
.cc-col-body::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }

.cc-col-footer {
  padding: 10px 14px;
  background: #fff;
  border-top: 1px solid #e2e8f0;
  border-radius: 0 0 12px 12px;
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
}

/* ---- ORDER CARD ---- */
.cc-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 6px;
  cursor: grab;
  box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  transition: all 0.15s;
}

.cc-card:hover {
  box-shadow: 0 3px 10px rgba(0,0,0,0.08);
  transform: translateY(-1px);
}

.cc-card:active { cursor: grabbing; }

.cc-card-locked {
  opacity: 0.8;
  cursor: not-allowed !important;
  background-color: #f9fafb !important;
  border: 1px dashed #d1d5db !important;
}

.cc-lock-badge {
  position: absolute;
  top: -8px;
  right: -8px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  z-index: 10;
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

.cc-card-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.cc-color-swatch {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 2px solid #e2e8f0;
  flex-shrink: 0;
}

.cc-card-info {
  min-width: 0;
}

.cc-card-color-name {
  font-weight: 700;
  font-size: 12px;
  color: #1e293b;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.cc-card-party {
  font-size: 10px;
  color: #94a3b8;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cc-card-details {
  font-size: 10px;
  color: #94a3b8;
}

.cc-card-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
}

.cc-card-qty {
  font-weight: 700;
  font-size: 13px;
  color: #1e293b;
}

.cc-card-qty-kg {
  font-size: 10px;
  color: #94a3b8;
}

/* ---- MIX ROLL MARKER ---- */
.cc-mix-marker {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  padding: 0 4px;
}

.cc-mix-line {
  flex: 1;
  height: 2px;
  background: #fbbf24;
}

.cc-mix-label {
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 4px 10px;
  border-radius: 12px;
  white-space: nowrap;
  border: 1px solid rgba(0,0,0,0.1);
}

.cc-mix-label.white-mix {
  background: #fef3c7;
  color: #92400e;
}

.cc-mix-label.black-mix {
  background: #374151;
  color: #f9fafb;
}

.cc-mix-label.color-mix {
  background: #dbeafe;
  color: #1e40af;
}

.cc-mix-label.beige-mix {
  background: #fde8cd;
  color: #92400e;
}

.cc-empty {
  text-align: center;
  padding: 40px 20px;
  color: #94a3b8;
  font-size: 13px;
  font-style: italic;
}
</style>

<style scoped>
/* ---- MATRIX VIEW ---- */
.cc-view-btn {
    background: white;
    border: 1px solid #d1d5db;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    color: #4b5563;
    cursor: pointer;
    font-weight: 500;
}
.cc-view-btn.active {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #1d4ed8;
    font-weight: 600;
}

.cc-matrix-container {
    flex: 1;
    overflow: hidden;
    padding: 16px;
    display: flex;
    flex-direction: column; 
}

.cc-matrix-scroll {
    flex: 1;
    overflow: auto;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: white;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.cc-matrix-table {
    width: 100%;
    border-collapse: separate; /* Required for sticky headers */
    border-spacing: 0;
    font-size: 12px;
}

.cc-matrix-table th, 
.cc-matrix-table td {
    padding: 8px 12px;
    border: 1px solid #d1d5db;
}

.cc-matrix-table thead th {
    background: #f8fafc;
    font-weight: 700;
    color: #334155;
    position: sticky;
    top: 0;
    z-index: 20;
    border-bottom: 2px solid #94a3b8;
}

.cc-matrix-table tbody tr:hover td {
    background: #f8fafc;
}

.matrix-sticky-col {
    position: sticky;
    left: 0;
    z-index: 10;
    background: #f8fafc;
    border-right: 2px solid #94a3b8 !important;
    min-width: 130px;
}

.cc-matrix-table thead th.matrix-sticky-col {
    z-index: 30; /* Higher than normal headers and normal sticky cols */
}

.matrix-row-header {
    font-weight: 600;
    color: #1e293b;
    min-width: 150px;
}

.matrix-highlight {
    background-color: #dcfce7 !important; /* Green-100 */
    color: #166534;
    font-weight: 700;
}

.matrix-total-col {
    background: #f1f5f9;
    font-weight: 700;
}

/* Drag & Drop Visuals */
.cc-ghost {
  opacity: 0.4;
  background: #c7d2fe !important;
  border: 2px dashed #6366f1 !important;
}

.cc-drag {
  opacity: 0;
}

.cc-chosen {
  background-color: #e0e7ff !important;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1) !important;
}

.draggable-handle {
    cursor: grab;
}
.draggable-handle:active {
    cursor: grabbing;
}
</style>

<style scoped>
/* ---- MONTHLY VIEW ---- */
.cc-monthly-container {
    display: flex;
    flex-direction: column;
    flex: 1;
    overflow-y: auto;
    overflow-x: auto;
    padding: 10px;
    gap: 10px;
}

.cc-monthly-header {
    display: flex;
    min-width: 1000px;
}

.cc-monthly-corner {
    min-width: 150px;
    width: 150px;
    padding: 10px;
    font-weight: bold;
    background: #f1f5f9;
    border-right: 1px solid #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: center;
    position: sticky;
    left: 0;
    z-index: 10;
}

.cc-monthly-col-header {
    flex: 1;
    min-width: 250px;
    padding: 10px;
    text-align: center;
    font-weight: bold;
    border-top: 4px solid transparent;
    background: white;
    border-right: 1px solid #f1f5f9;
    border-bottom: 2px solid #e2e8f0;
}

.cc-monthly-row {
    display: flex;
    border-bottom: 1px solid #e2e8f0;
    min-height: 150px;
    min-width: 1000px;
}

.cc-monthly-row-label {
    min-width: 150px;
    width: 150px;
    padding: 10px;
    background: #f8fafc;
    border-right: 1px solid #e2e8f0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: sticky;
    left: 0;
    z-index: 5;
}

.cc-monthly-cell {
    flex: 1;
    min-width: 250px;
    border-right: 1px solid #f1f5f9;
    padding: 4px;
    display: flex;
    flex-direction: column;
    background: #fff;
}

.cc-cell-header-tiny {
    font-size: 10px;
    font-weight: bold;
    text-align: right;
    color: #94a3b8;
    margin-bottom: 4px;
    padding-right: 4px;
}

.cc-cell-body {
    flex: 1;
    display: flex;
    flex-wrap: wrap;
    align-content: flex-start;
    gap: 6px;
    min-height: 80px;
    background: #fafafa; /* Slight tint to show droppable area */
    border-radius: 4px;
    padding: 4px;
}

.cc-card-mini {
    width: 100%; /* Full width in cell */
    padding: 4px 6px; /* Reduced vertical padding for compact view */
    margin-bottom: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    cursor: grab;
}

.cc-color-swatch-mini {
    width: 12px;
    height: 12px;
    border-radius: 4px;
    margin-right: 6px;
    border: 1px solid rgba(0,0,0,0.1);
    flex-shrink: 0;
}

/* Recycle toggle buttons */
.recycle-btn {
    padding: 4px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: #f9fafb;
    color: #6b7280;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
}
.recycle-btn:hover {
    background: #fef3c7;
    border-color: #f59e0b;
}
.recycle-btn-active {
    padding: 4px 10px;
    border: 2px solid #16a34a;
    border-radius: 6px;
    background: #dcfce7;
    color: #166534;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
}
.bg-yellow-100 { background-color: #fef3c7 !important; }
</style>