<template>
  <div class="cc-container">
    <!-- Filter Bar -->
    <div class="cc-filters">
      <div class="cc-filter-item">
        <label>View Scope</label>
        <select v-model="viewScope" @change="toggleViewScope" :disabled="isManufactureUser" style="font-weight: bold; color: #4f46e5;" :style="isManufactureUser ? { opacity: '0.3', cursor: 'not-allowed', pointerEvents: 'none' } : {}">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>
      
      <div class="cc-filter-item" v-if="viewScope === 'daily'">
        <label>Planned Date</label>
        <input type="date" v-model="filterOrderDate" @change="fetchData" :disabled="isManufactureUser" :style="isManufactureUser ? { opacity: '0.5', cursor: 'not-allowed' } : {}" />
      </div>
      <div class="cc-filter-item" v-else-if="viewScope === 'weekly'">
        <label>Select Week</label>
        <input type="week" v-model="filterWeek" @change="fetchData" />
      </div>
      <div class="cc-filter-item" v-else-if="viewScope === 'monthly'">
        <label>Select Month</label>
        <input type="month" v-model="filterMonth" @change="fetchData" />
      </div>
      <div class="cc-filter-item">
        <label>Order Code</label>
        <input type="text" v-model="filterPartyCode" placeholder="Search order..." @input="fetchData" />
      </div>
      <div class="cc-filter-item">
        <label>Customer</label>
        <input type="text" v-model="filterCustomer" placeholder="Search customer..." @input="fetchData" />
      </div>
      <div class="cc-filter-item">
        <label>Unit</label>
        <select v-model="filterUnit" @change="fetchData">
          <option value="">All Units</option>
          <option v-for="u in units" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>
      <button class="cc-clear-btn" @click="fetchData">🔄 Refresh</button>
      <button
        class="cc-lock-btn"
        @click="toggleTableReorder"
        :title="tableReorderLocked ? 'Unlock to enable drag and drop reordering' : 'Lock to disable drag and drop reordering'"
      >
        {{ tableReorderLocked ? '🔒 Reorder Locked' : '🔓 Reorder Enabled' }}
      </button>
      <button
        class="cc-save-arrange-btn"
        @click="saveArrangement"
        :disabled="!arrangementDirty || arrangementSaving"
        :title="arrangementDirty ? 'Save current row arrangement permanently' : 'No pending arrangement changes'"
      >
        {{ arrangementSaving ? 'Saving Arrangement...' : '💾 Save Arrangement' }}
      </button>
      <button
        class="cc-clear-btn"
        @click="restoreLastArrangement"
        :disabled="arrangementSaving || arrangementRestoring"
        title="Restore last saved arrangement snapshot for current table view"
      >
        {{ arrangementRestoring ? 'Restoring...' : '↩ Restore Last' }}
      </button>
      <span v-if="arrangementSaving" class="cc-arrange-indicator saving">Saving...</span>
      <span v-else-if="arrangementDirty" class="cc-arrange-indicator dirty">Unsaved arrangement changes</span>
      <span v-else class="cc-arrange-indicator clean">Arrangement saved</span>
      <button
        class="cc-lock-btn"
        @click="toggleMergeMode"
        :title="mergeMode ? 'Disable merge mode' : 'Enable merge mode'"
        :style="mergeMode ? { background: '#fee2e2', color: '#991b1b', borderColor: '#fca5a5' } : {}"
      >
        {{ mergeMode ? '🔗 Merge Mode ON' : '🔗 Merge Mode OFF' }}
      </button>
      <button class="cc-maint-btn" @click="openMaintenanceDialog" title="Manage equipment maintenance schedules">⚙️ Maintenance</button>
      
      <div class="cc-filter-item" style="margin-left: auto;">
          <button class="cc-view-btn" @click="goToBoard">📊 Back to Board</button>
      </div>
    </div>

    <div v-if="showMergeDialog" class="pt-merge-overlay" @click.self="closeMergeDialog">
      <div class="pt-merge-dialog">
        <div class="pt-merge-header">
          <h3>Merge Items</h3>
          <button class="pt-merge-close" @click="closeMergeDialog">✕</button>
        </div>
        <div class="pt-merge-filters">
          <input v-model="mergeFilterOrderCode" type="text" placeholder="Filter Order Code" />
          <input v-model="mergeFilterCustomer" type="text" placeholder="Filter Customer" />
          <input v-model="mergeFilterQuality" type="text" placeholder="Filter Quality" />
          <input v-model="mergeFilterColor" type="text" placeholder="Filter Colour" />
          <button class="cc-save-arrange-btn" @click="applyAutoMergeSuggestion">✨ Auto Suggest</button>
        </div>
        <div class="pt-merge-suggest" v-if="autoMergeSuggestions.length">
          <strong>Suggested Groups:</strong>
          <div class="pt-merge-suggest-list">
            <button
              v-for="s in autoMergeSuggestions"
              :key="s.key"
              class="pt-merge-suggest-pill"
              @click="selectSuggestion(s)"
            >
              {{ s.partyCode }} · {{ s.quality }} · {{ s.color }} · GSM: {{ s.gsmSummary }} ({{ s.items.length }})
            </button>
          </div>
        </div>
        <div class="pt-merge-summary">
          <span><b>Selected:</b> {{ selectedMergeSummary.count }} items</span>
          <span><b>Total Target:</b> {{ formatKg(selectedMergeSummary.targetWeight) }} Kg</span>
          <span><b>Total Actual:</b> {{ formatKg(selectedMergeSummary.actualWeight) }} Kg</span>
        </div>
        <div class="pt-merge-list">
          <label v-for="item in mergeDialogItems" :key="item.itemName" class="pt-merge-item">
            <input type="checkbox" :checked="selectedMergeItems.has(item.itemName)" @change="toggleMergeSelection(item.itemName)" />
            <span>{{ item.partyCode }} | {{ item.customer_name || item.customer || '-' }} | {{ item.quality }} | {{ item.color }} | {{ item.gsm }} GSM | {{ item.qty }} Kg</span>
          </label>
          <div v-if="!mergeDialogItems.length" class="pt-merge-empty">No items found for merge filters.</div>
        </div>
        <div class="pt-merge-actions">
          <button class="cc-clear-btn" @click="closeMergeDialog">Cancel</button>
          <button class="cc-clear-btn" :disabled="!autoMergeSuggestions.length" @click="createAllSuggestedMerges">Add All Suggested</button>
          <button class="cc-save-arrange-btn" :disabled="selectedMergeItems.size < 2" @click="createMergeFromDialog">Add Merge</button>
        </div>
      </div>
    </div>

    <!-- Table View (Always Visible in this page) -->
    <div class="cc-table-container">
        <div v-for="unitGroup in tableData" :key="unitGroup.unit" class="cc-table-unit-block">
            <!-- Unit Header -->
            <div class="cc-table-unit-header" :style="{ backgroundColor: getUnitHeaderColor(unitGroup.unit) }">
                {{ unitGroup.unit.toUpperCase() }} (06:00 am to 06:00 am) - Total: {{ unitGroup.totalWeight.toFixed(2) }} T
            </div>
            
            <table class="cc-prod-table">
                <thead>
                    <tr>
                    <th style="width: 36px;">DRAG</th>
                        <th style="width: 80px;">DATE</th>
                        <th style="width: 80px;">DAY</th>
                        <th style="width: 100px;">ORDER CODE</th>
                        <th style="width: 150px;">PARTY NAME</th>
                        <th style="width: 120px;">PLAN CODE</th>
                        <th style="width: 80px;">QUALITY</th>
                        <th style="width: 100px;">COLOUR</th>
                        <th style="width: 80px;">GSM</th>
                        <th style="width: 120px;">TARGET WEIGHT (Kgs)</th>
                        <th style="width: 100px;">TOTAL TARGET (Kgs)</th>
                        <th style="width: 150px;">ACTUAL PRODUCTION WEIGHT (Kgs)</th>
                        <th style="width: 100px;">TOTAL ACTUAL (Kgs)</th>
                        <th style="width: 110px;">MERGE ACTION</th>
                        <th style="width: 100px;">DESPATCH STATUS</th>
                        <th style="width: 90px; position: sticky; right: 100px; background: #fafafa; z-index: 10;">PRODUCTION PLAN</th>
                        <th style="width: 110px; position: sticky; right: 0; background: #fafafa; z-index: 10;">STOCK ENTRY</th>
                    </tr>
                </thead>
                <tbody
                  v-for="dateGroup in unitGroup.dates"
                  :key="dateGroup.date"
                  class="pt-sortable-body"
                  :data-unit="unitGroup.unit"
                  :data-date="dateGroup.date"
                >
                      <!-- Maintenance Row (show once at maintenance start date, centered) -->
                      <tr v-if="getMaintenanceBannerForDate(dateGroup.date, unitGroup.unit)" class="pt-non-draggable" style="background-color: #fee2e2; border: 2px solid #dc2626;">
                        <td colspan="15" style="padding: 8px 12px; font-weight: 700; color: #991b1b; text-align: center;">
                          <div style="display: inline-flex; align-items: center; justify-content: center; gap: 10px; flex-wrap: wrap;">
                            <span>🔧 MAINTENANCE: {{ getMaintenanceBannerForDate(dateGroup.date, unitGroup.unit).type }} ({{ getMaintenanceBannerForDate(dateGroup.date, unitGroup.unit).startDate }} - {{ getMaintenanceBannerForDate(dateGroup.date, unitGroup.unit).endDate }})</span>
                            <button @click="deleteMaintenanceRecord(getMaintenanceBannerForDate(dateGroup.date, unitGroup.unit).name)" style="background: #dc2626; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 11px;">Remove</button>
                          </div>
                        </td>
                      </tr>

                      <template v-if="dateGroup.rows.length">
                        <template v-for="(row, idx) in dateGroup.rows" :key="row.rowKey">
                          <tr v-if="row.type === 'item'" class="pt-draggable-row" :data-item-name="row.item.itemName">
                            <td class="cell-center" style="cursor: grab; color: #94a3b8; font-size: 15px;" :title="tableReorderLocked ? 'Unlock reorder to drag' : 'Drag to reorder'">
                              <span class="pt-drag-handle">⠿</span>
                            </td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-center font-bold">
                              {{ formatDate(dateGroup.date) }}
                            </td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-center">
                              {{ getDayName(dateGroup.date) }}
                            </td>
                                    
                            <td class="cell-center">{{ row.item.partyCode }}</td>
                            <td>{{ row.item.customer_name || row.item.party_name || row.item.customer || row.item.partyCode }}</td>
                            <td class="cell-center font-mono font-bold" style="font-size:11px; color:#4f46e5;">{{ row.item.planCode }}</td>
                            <td class="cell-center">{{ row.item.quality }}</td>
                            <td class="cell-center font-bold">{{ row.item.color }}</td>
                            <td class="cell-center">{{ row.item.gsm }}</td>
                            <td class="cell-right font-bold">{{ formatKg(row.item.qty) }}</td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-right font-bold bg-blue-50">
                              {{ formatKg(dateGroup.dailyTotal) }}
                            </td>
                            <td class="cell-right font-bold">{{ formatKg2(row.item.actual_production_weight_kgs) }}</td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-right font-bold bg-yellow-50">
                              {{ formatKg2(dateGroup.dailyActualTotal) }}
                            </td>
                            <td class="cell-center">-</td>
                                    
                            <td class="cell-center">
                              <span class="status-badge" :class="getDispatchStatusClass(row.item.delivery_status)">
                                {{ formatDispatchStatus(row.item.delivery_status) }}
                              </span>
                            </td>
                            <td class="cell-center" style="position: sticky; right: 100px; background: white; z-index: 9;">
                              <button @click="openProductionPlanView(row.item.planningSheet, row.item.salesOrderItem, row.item.itemName, row.item.pp_id || '')" class="cc-pp-btn" :title="`View PP: ${row.item.pp_id || 'resolve from sheet'}`">
                                📋 View
                              </button>
                            </td>
                            <td class="cell-center" style="position: sticky; right: 0; background: white; z-index: 9;">
                              <button 
                                v-if="canShowStockEntry(row.item)" 
                                @click="handleStockEntryAction(row.item)" 
                                class="cc-pp-btn" 
                                :title="getStockEntryTitle(row.item)">
                                {{ getStockEntryLabel(row.item) }}
                              </button>
                              <button 
                                v-else-if="row.item.spr_name" 
                                @click="openItemSPR(row.item.spr_name, row.item)" 
                                class="cc-pp-btn" 
                                style="background:#10b981; color:white;" 
                                title="View SPR">
                                {{ row.item.spr_docstatus === 1 ? '✅ Completed Entry' : '✅ Open SPR' }}
                              </button>
                              <span v-else style="color:#999; font-size:10px; white-space: nowrap;">No PP</span>
                            </td>
                          </tr>

                          <tr v-else class="pt-merge-row pt-draggable-row" :data-merge-id="row.mergeId">
                            <td class="cell-center" style="cursor: grab; color: #7c3aed; font-size: 15px;" :title="tableReorderLocked ? 'Unlock reorder to drag' : 'Drag merged row'">
                              <span class="pt-drag-handle">🔗</span>
                            </td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-center font-bold">
                              {{ formatDate(dateGroup.date) }}
                            </td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-center">
                              {{ getDayName(dateGroup.date) }}
                            </td>
                            <td class="cell-center font-bold">{{ row.partyCode }}</td>
                            <td>
                              <button v-if="canExpandMergedRows" class="pt-merge-expand-btn" @click="toggleMergeExpanded(row.mergeId)">
                                {{ isMergeExpanded(row.mergeId) ? '▼' : '▶' }} {{ row.displayLabel }}
                              </button>
                              <span v-else>{{ row.displayLabel }}</span>
                              <div v-if="canExpandMergedRows && isMergeExpanded(row.mergeId)" class="pt-merge-inline-details">
                                <div v-for="mItem in row.items" :key="mItem.itemName" class="pt-merge-inline-item">
                                  <span><b>{{ mItem.partyCode }}</b></span>
                                  <span>{{ mItem.customer_name || mItem.customer || '-' }}</span>
                                  <span>{{ mItem.quality }}</span>
                                  <span>{{ mItem.color }}</span>
                                  <span>{{ mItem.gsm }} GSM</span>
                                  <span>Width: {{ formatWidth(mItem.width_inch || mItem.width || mItem.custom_width) }}</span>
                                  <span>Target: {{ formatKg(mItem.qty) }} Kg</span>
                                  <span>Actual: {{ formatKg2(mItem.actual_production_weight_kgs) }} Kg</span>
                                </div>
                              </div>
                            </td>
                            <td class="cell-center font-mono font-bold" style="font-size:11px; color:#4f46e5;">MERGED</td>
                            <td class="cell-center">{{ row.quality }}</td>
                            <td class="cell-center font-bold">{{ row.color }}</td>
                            <td class="cell-center">{{ row.gsm }}</td>
                            <td class="cell-right font-bold">{{ formatKg(row.totalTargetWeight) }}</td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-right font-bold bg-blue-50">
                              {{ formatKg(dateGroup.dailyTotal) }}
                            </td>
                            <td class="cell-right font-bold">{{ formatKg2(row.totalActualWeight) }}</td>
                            <td v-if="idx === 0" :rowspan="dateGroup.rows.length" class="cell-right font-bold bg-yellow-50">
                              {{ formatKg2(dateGroup.dailyActualTotal) }}
                            </td>
                            <td class="cell-center">
                              <button
                                class="cc-clear-btn"
                                style="padding: 4px 8px; font-size: 11px;"
                                :disabled="row.hasDispatchLock"
                                :title="row.hasDispatchLock ? 'Cannot unmerge dispatched rows' : 'Unmerge'"
                                @click="deleteMerge(row.mergeId)"
                              >
                                Unmerge
                              </button>
                            </td>
                            <td class="cell-center">
                              <span class="status-badge" :class="getDispatchStatusClass(row.mergeDispatchStatus)">
                                {{ formatDispatchStatus(row.mergeDispatchStatus) }}
                              </span>
                            </td>
                            <td class="cell-center" style="position: sticky; right: 100px; background: white; z-index: 9;">
                              <button @click="openMergedProductionPlan(row)" class="cc-pp-btn" :title="`View PP for merged row`">
                                📋 View
                              </button>
                            </td>
                            <td class="cell-center" style="position: sticky; right: 0; background: white; z-index: 9;">
                              <button 
                                v-if="!row.spr_name" 
                                @click="createMergedStockEntry(row)" 
                                class="cc-pp-btn" 
                                title="Create Stock Entry for merged items">
                                📝 Stock Entry
                              </button>
                              <button 
                                v-else 
                                @click="openMergedSPR(row.spr_name, row)" 
                                class="cc-pp-btn" 
                                style="background:#10b981; color:white;" 
                                title="View SPR">
                                ✅ Open SPR
                              </button>
                            </td>
                          </tr>
                        </template>
                      </template>

                      <tr v-else>
                        <td class="cell-center">-</td>
                        <td class="cell-center font-bold">{{ formatDate(dateGroup.date) }}</td>
                        <td class="cell-center">{{ getDayName(dateGroup.date) }}</td>
                        <td colspan="12" style="text-align:center; color:#94a3b8; font-style:italic;">No orders (maintenance day)</td>
                      </tr>
                </tbody>
                <tbody>
                    <tr v-if="unitGroup.dates.length === 0">
                        <td colspan="15" style="text-align:center; padding: 20px; color:#999;">No production planned for this unit</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch, reactive } from "vue";
import Sortable from "sortablejs";

// ===== MAINTENANCE DATA =====
const maintenanceRecords = ref([]);
const maintenanceData = ref({});

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
				for (let d = new Date(startD); d <= endD; d.setDate(d.getDate() + 1)) {
					const dateStr = d.toISOString().split('T')[0];
          if (!maintenanceData.value[dateStr]) maintenanceData.value[dateStr] = {};
          if (!maintenanceData.value[dateStr][rec.unit]) maintenanceData.value[dateStr][rec.unit] = [];
          maintenanceData.value[dateStr][rec.unit].push({
						name: rec.name,
						type: rec.maintenance_type,
						startDate: rec.start_date,
						endDate: rec.end_date,
						status: rec.status
					});
				}
			});
		}
	} catch (e) {
		console.error("Failed to fetch maintenance records", e);
	}
}

async function deleteMaintenanceRecord(recordName) {
  if (!confirm('Remove this maintenance record?')) return;
	try {
		const res = await frappe.call({
			method: "production_scheduler.api.delete_maintenance_and_cascade",
			args: { maintenance_record_name: recordName }
		});
		if (res.message && res.message.status === 'success') {
			frappe.show_alert({ message: `${res.message.message}`, indicator: 'green' });
			await fetchMaintenanceRecords();
			await fetchData();
		} else if (res.message && res.message.status === 'error') {
			frappe.msgprint(res.message.message || "Error deleting maintenance record");
		}
	} catch (e) {
		frappe.msgprint("Error deleting maintenance record");
		console.error(e);
	}
}

function getMaintenanceForDate(date, unit) {
  if (!date || !maintenanceData.value[date]) return null;
  return maintenanceData.value[date][unit];
}

function normalizeDateString(dateValue) {
  if (!dateValue) return "";
  return String(dateValue).split(' ')[0].split('T')[0];
}

function getMaintenanceBannerForDate(date, unit) {
  const records = getMaintenanceForDate(date, unit) || [];
  return records.find(rec => normalizeDateString(rec.startDate) === date) || null;
}

function getCurrentScopeDateRange() {
  if (viewScope.value === 'monthly') {
    if (!filterMonth.value) return null;
    const [year, month] = filterMonth.value.split('-').map(v => parseInt(v, 10));
    const start = new Date(year, month - 1, 1);
    const end = new Date(year, month, 0);
    return { start, end };
  }

  if (viewScope.value === 'weekly') {
    if (!filterWeek.value) return null;
    const [yearStr, weekStr] = filterWeek.value.split('-W');
    const year = parseInt(yearStr, 10);
    const week = parseInt(weekStr, 10);
    const simple = new Date(year, 0, 1 + (week - 1) * 7);
    const dow = simple.getDay();
    const start = new Date(simple);
    if (dow <= 4) start.setDate(simple.getDate() - dow + 1);
    else start.setDate(simple.getDate() + 8 - dow);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return { start, end };
  }

  if (!filterOrderDate.value) return null;
  const d = new Date(filterOrderDate.value);
  return { start: d, end: d };
}

function getScopeMaintenanceDates(unit) {
  const range = getCurrentScopeDateRange();
  if (!range) return [];

  const out = [];
  const cur = new Date(range.start);
  while (cur <= range.end) {
    const y = cur.getFullYear();
    const m = String(cur.getMonth() + 1).padStart(2, '0');
    const d = String(cur.getDate()).padStart(2, '0');
    const dateStr = `${y}-${m}-${d}`;
    if (getMaintenanceForDate(dateStr, unit)) out.push(dateStr);
    cur.setDate(cur.getDate() + 1);
  }

  return out;
}

async function openMaintenanceDialog() {
	const d = new frappe.ui.Dialog({
		title: "⚙️ Equipment Maintenance Management",
		fields: [
			{
				fieldtype: "Section Break",
				label: "Add New Maintenance"
			},
			{
				fieldtype: "Select",
				fieldname: "new_unit",
				label: "Unit",
				options: "Unit 1\nUnit 2\nUnit 3\nUnit 4",
				reqd: 1
			},
			{
				fieldtype: "Select",
				fieldname: "maint_type",
				label: "Maintenance Type",
        options: "Mesh Change\nDie Change\nBreakdown - Partial\nBreakdown - Full\nEB Shutdown\nMachine Off",
				reqd: 1
			},
			{
				fieldtype: "Date",
				fieldname: "start_date",
				label: "Start Date",
				reqd: 1
			},
			{
				fieldtype: "Date",
				fieldname: "end_date",
				label: "End Date",
				reqd: 1
			},
			{
				fieldtype: "Small Text",
				fieldname: "notes",
				label: "Notes"
			},
			{
				fieldtype: "Section Break",
				label: "Existing Maintenance Records"
			},
			{
				fieldtype: "HTML",
				fieldname: "records_display",
				options: getMaintenanceRecordsHTML()
			}
		],
		primary_action_label: "Add Maintenance",
		primary_action: async (vals) => {
			if (!vals.new_unit || !vals.maint_type || !vals.start_date || !vals.end_date) {
				frappe.msgprint("Please fill all required fields");
				return;
			}
			try {
				const res = await frappe.call({
					method: "production_scheduler.api.add_equipment_maintenance",
					args: {
						unit: vals.new_unit,
						maintenance_type: vals.maint_type,
						start_date: vals.start_date,
						end_date: vals.end_date,
						notes: vals.notes || ""
					}
				});
				if (res.message && res.message.status === 'success') {
					frappe.show_alert({ message: res.message.message, indicator: 'green' });
					await fetchMaintenanceRecords();
          await fetchData();
          d.hide();
				}
			} catch (e) {
				frappe.msgprint("Error adding maintenance record");
				console.error(e);
			}
		}
	});
	d.show();
	await fetchMaintenanceRecords();
}

function getMaintenanceRecordsHTML() {
	if (!maintenanceRecords.value || maintenanceRecords.value.length === 0) {
		return '<p style="color: #999; text-align: center;">No maintenance records scheduled</p>';
	}
	
	let html = '<table style="width:100%; border-collapse: collapse; font-size: 12px;"><tr style="background: #f1f5f9; font-weight: 600;">';
	html += '<th style="border: 1px solid #ddd; padding: 6px;">Unit</th>';
	html += '<th style="border: 1px solid #ddd; padding: 6px;">Type</th>';
	html += '<th style="border: 1px solid #ddd; padding: 6px;">Start</th>';
	html += '<th style="border: 1px solid #ddd; padding: 6px;">End</th>';
	html += '<th style="border: 1px solid #ddd; padding: 6px;">Status</th>';
	html += '</tr>';
	
	maintenanceRecords.value.forEach(rec => {
		html += `<tr style="border: 1px solid #ddd;">`;
		html += `<td style="border: 1px solid #ddd; padding: 6px; text-align: center; font-weight: 600;">${rec.unit}</td>`;
		html += `<td style="border: 1px solid #ddd; padding: 6px; text-align: center;">${rec.maintenance_type}</td>`;
		html += `<td style="border: 1px solid #ddd; padding: 6px; text-align: center;">${rec.start_date}</td>`;
		html += `<td style="border: 1px solid #ddd; padding: 6px; text-align: center;">${rec.end_date}</td>`;
		html += `<td style="border: 1px solid #ddd; padding: 6px; text-align: center;">`;
		const statusColor = rec.status === 'Completed' ? '#10b981' : rec.status === 'In Progress' ? '#f59e0b' : '#999';
		html += `<span style="background: ${statusColor}20; color: ${statusColor}; padding: 2px 6px; border-radius: 4px; font-weight: 600;">${rec.status}</span>`;
		html += `</td>`;
		html += `</tr>`;
	});
	
	html += '</table>';
	return html;
}

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
  const group = findColorGroup(color);
  return group ? group.priority : 50;
}

function compareColor(a, b, direction) {
  const pA = getColorPriority(a.color);
  const pB = getColorPriority(b.color);
  return direction === 'asc' ? pA - pB : pB - pA;
}

function compareGsm(a, b, direction) {
  const gsmA = parseFloat(a.gsm) || 0;
  const gsmB = parseFloat(b.gsm) || 0;
  return direction === 'asc' ? gsmA - gsmB : gsmB - gsmA;
}

// Track saved sequences from 'Color Sequence Approval' to match Board order exactly
const unitSequenceStore = reactive({});

function sortItems(unit, items, date) {
  // 1. If we have a saved sequence (Manual Sort / Approved Sequence) for this unit/date, use it primarily
  const normalizedUnit = normalizeUnit(unit);
  const key = `${normalizedUnit}||${date}`;
  const savedSeq = unitSequenceStore[key]?.sequence;

  if (savedSeq && savedSeq.length) {
    const rowNames = items.map(a => a.itemName || a.name);
    console.log(`Applying saved sequence for ${key}:`, savedSeq.length, "items");
    console.log('Saved sequence:', savedSeq);
    console.log('Table row names:', rowNames);
    const seqMap = {};
    savedSeq.forEach((name, i) => seqMap[name] = i);

    return [...items].sort((a, b) => {
      const nameA = a.itemName || a.name;
      const nameB = b.itemName || b.name;

      const idxA = seqMap[nameA] !== undefined ? seqMap[nameA] : 9999 + parseInt(a.idx || 0);
      const idxB = seqMap[nameB] !== undefined ? seqMap[nameB] : 9999 + parseInt(b.idx || 0);

      if (idxA !== idxB) return idxA - idxB;

      // Fallback if not in sequence map
      const pA = getColorPriority(a.color);
      const pB = getColorPriority(b.color);
      if (pA !== pB) return pA - pB;
      return (parseFloat(b.gsm) || 0) - (parseFloat(a.gsm) || 0);
    });
  }

  // 2. Default Auto Sort (Matches Board's default when no manual sequence): 
  // Color Priority (Asc) -> GSM (Desc) -> DB Index
  return [...items].sort((a, b) => {
    // A. Color Priority
    const pA = getColorPriority(a.color);
    const pB = getColorPriority(b.color);
    if (pA !== pB) return pA - pB;

    // B. GSM Descending (Heuristic: heavier first to minimize gaps)
    const gsmA = parseFloat(a.gsm) || 0;
    const gsmB = parseFloat(b.gsm) || 0;
    if (gsmB !== gsmA) return gsmB - gsmA;

    // C. Database Index (Initial Sequence)
    const idxA = parseInt(a.idx || 0);
    const idxB = parseInt(b.idx || 0);
    return idxA - idxB;
  });
}
// ─────────────────────────────────────────────────────────────────────────────

const units = ["Unit 1", "Unit 2", "Unit 3", "Unit 4", "Mixed"];
const filterOrderDate = ref(frappe.datetime.get_today());
const filterWeek = ref("");
const filterMonth = ref("");
const viewScope = ref("daily");

const filterPartyCode = ref("");
const filterCustomer = ref("");
const filterUnit = ref("");
const rawData = ref([]);
const tableReorderLocked = ref(true);
const sortableInstances = ref([]);
const pendingArrangementUpdates = ref({});
const arrangementDirty = ref(false);
const arrangementSaving = ref(false);
const arrangementRestoring = ref(false);
const mergeMode = ref(false);
const showMergeDialog = ref(false);
const merges = ref([]);
const mergedItemsMap = ref({});
const expandedMerges = ref(new Set());
const selectedMergeItems = ref(new Set());
const mergeFilterOrderCode = ref("");
const mergeFilterCustomer = ref("");
const mergeFilterQuality = ref("");
const mergeFilterColor = ref("");
const UNIT_TONNAGE_LIMITS = { "Unit 1": 4.4, "Unit 2": 12, "Unit 3": 9, "Unit 4": 5.5, "Mixed": 999 };

function getArrangementKey(unit, date) {
  return `${unit}||${date}`;
}

// Removed duplicate normalizeUnit definition
function normalizeUnit(raw) {
  const r = String(raw || "").trim().toUpperCase().replace(/\s+/g, "");
  if (r.includes("UNIT1")) return "Unit 1";
  if (r.includes("UNIT2")) return "Unit 2";
  if (r.includes("UNIT3")) return "Unit 3";
  if (r.includes("UNIT4")) return "Unit 4";
  return "Mixed";
}

function destroyTableSortables() {
  sortableInstances.value.forEach((instance) => {
    try {
      instance.destroy();
    } catch (e) {}
  });
  sortableInstances.value = [];
}

async function persistDateGroupOrder(tbodyEl) {
  const unit = tbodyEl?.dataset?.unit;
  const date = tbodyEl?.dataset?.date;
  if (!unit || !date) return;

  const rows = Array.from(tbodyEl.querySelectorAll('.pt-draggable-row'));
  const expandedNames = [];

  // Persist merge rows as a contiguous block by expanding to all child item names.
  rows.forEach((row) => {
    const mergeId = row.dataset.mergeId;
    if (mergeId) {
      const unitGroup = tableData.value.find((g) => normalizeUnit(g.unit) === normalizeUnit(unit));
      const dateGroup = unitGroup?.dates?.find((d) => String(d.date) === String(date));
      const mergeRow = dateGroup?.rows?.find((r) => r.type === 'merge' && r.mergeId === mergeId);
      const mergeItemNames = (mergeRow?.items || []).map((it) => it.itemName).filter(Boolean);
      expandedNames.push(...mergeItemNames);
      return;
    }

    if (row.dataset.itemName) {
      expandedNames.push(row.dataset.itemName);
    }
  });

  const items = expandedNames
    .map((name, idx) => ({
      name,
      unit,
      date,
      index: idx + 1,
    }))
    .filter((row) => row.name);

  if (!items.length) return;

  pendingArrangementUpdates.value[getArrangementKey(unit, date)] = items;
  arrangementDirty.value = true;
}

async function saveArrangement() {
  if (!arrangementDirty.value || arrangementSaving.value) return;

  const groupedUpdates = Object.entries(pendingArrangementUpdates.value);
  const hasRows = groupedUpdates.some(([, items]) => (items || []).length > 0);
  if (!hasRows) {
    arrangementDirty.value = false;
    return;
  }

  arrangementSaving.value = true;
  try {
    // Persist explicit sequence per unit/date only.
    for (const [, items] of groupedUpdates) {
      if (!items.length) continue;
      const unit = normalizeUnit(items[0].unit);
      const date = items[0].date;
      const sequence = items.map((row) => row.name).filter(Boolean);
      if (!unit || !date || !sequence.length) continue;

      // Save to backend
      await frappe.call({
        method: "production_scheduler.api.save_color_sequence",
        args: {
          date,
          unit,
          sequence_data: JSON.stringify(sequence),
          plan_name: "Default",
        },
      });

      // Update local store with the saved sequence
      const storeKey = `${unit}||${date}`;
      unitSequenceStore[storeKey] = {
        sequence,
        status: "Draft",
      };
      console.log(`Saved and cached sequence for ${storeKey}:`, sequence.length, "items");
    }

    pendingArrangementUpdates.value = {};
    arrangementDirty.value = false;
    frappe.show_alert({ message: 'Arrangement saved permanently', indicator: 'green' });
    
    // DO NOT call fetchData() here - it would reset the sequences we just saved
    // Arrangement stays visible until user manually refreshes if they want to verify
  } catch (e) {
    console.error('Failed to save arrangement:', e);
    frappe.msgprint('Failed to save arrangement');
  } finally {
    arrangementSaving.value = false;
  }
}

async function restoreLastArrangement() {
  if (arrangementSaving.value || arrangementRestoring.value) return;
  if (!window.confirm("Restore previous saved row arrangement for current view?")) return;

  const pairs = [];
  (tableData.value || []).forEach((unitGroup) => {
    const unit = normalizeUnit(unitGroup.unit);
    (unitGroup.dateGroups || []).forEach((dg) => {
      const date = dg.date;
      if (unit && date && date !== "No Date") {
        pairs.push({ unit, date });
      }
    });
  });

  if (!pairs.length) {
    frappe.msgprint("No date/unit groups available to restore.");
    return;
  }

  arrangementRestoring.value = true;
  try {
    let restored = 0;
    for (const p of pairs) {
      const res = await frappe.call({
        method: "production_scheduler.api.restore_last_color_sequence",
        args: { date: p.date, unit: p.unit, plan_name: "Default" },
      });
      if (res?.message?.status === "success") restored += 1;
    }
    arrangementDirty.value = false;
    pendingArrangementUpdates.value = {};
    await fetchData();
    frappe.show_alert({ message: `Restored ${restored} arrangement snapshot(s).`, indicator: "green" });
  } catch (e) {
    console.error("Failed to restore arrangement:", e);
    frappe.msgprint("Failed to restore last arrangement.");
  } finally {
    arrangementRestoring.value = false;
  }
}

async function initTableSortables() {
  destroyTableSortables();
  if (tableReorderLocked.value) return;

  await nextTick();
  const bodies = document.querySelectorAll('.pt-sortable-body');

  bodies.forEach((tbody) => {
    const sortable = new Sortable(tbody, {
      animation: 200,
      easing: "cubic-bezier(1, 0, 0, 1)",
      handle: '.pt-drag-handle',
      draggable: '.pt-draggable-row',
      filter: '.pt-non-draggable',
      ghostClass: 'pt-drag-ghost',
      chosenClass: 'pt-drag-chosen',
      dragClass: 'pt-drag-dragging',
      scrollSensitivity: 30,
      scrollSpeed: 10,
      onStart: () => {
        document.body.style.cursor = 'grabbing';
      },
      onEnd: async (evt) => {
        document.body.style.cursor = 'default';
        try {
          await persistDateGroupOrder(evt.to);
          frappe.show_alert({ message: 'Arrangement changed. Click Save Arrangement.', indicator: 'orange' });
        } catch (e) {
          console.error('Failed to queue row order:', e);
          frappe.msgprint('Failed to stage new row order');
          await fetchData();
        }
      },
    });

    sortableInstances.value.push(sortable);
  });
}

async function toggleTableReorder() {
  tableReorderLocked.value = !tableReorderLocked.value;

  if (tableReorderLocked.value) {
    destroyTableSortables();
    frappe.show_alert({ message: 'Row reorder locked', indicator: 'blue' });
    return;
  }

  await initTableSortables();
  frappe.show_alert({ message: 'Row reorder enabled', indicator: 'orange' });
}

// ===== ROLE-BASED VISIBILITY CONTROL =====
const isManufactureUser = ref(false);

const RESTRICTED_ROLE_NAMES = [
  "Manufacturing User",
  "Manufacture User"
];
const PRIVILEGED_ROLE_NAMES = ["System Manager"];
const MERGE_EXPAND_ALLOWED_ROLES = ["System Manager", "Manufacturing Manager"];

function getCurrentUserRoles() {
  const roleSet = new Set();

  if (Array.isArray(frappe?.user_roles)) {
    frappe.user_roles.forEach((r) => roleSet.add(String(r || "").trim()));
  }

  const bootRoles = frappe?.boot?.user?.roles;
  if (Array.isArray(bootRoles)) {
    bootRoles.forEach((r) => {
      if (typeof r === "string") roleSet.add(r.trim());
      else if (r && typeof r === "object" && r.role) roleSet.add(String(r.role).trim());
    });
  }

  return Array.from(roleSet);
}

function detectRestrictedUser() {
  const currentUser = String(frappe?.session?.user || "").toLowerCase();
  if (currentUser === "administrator") return false;

  const roles = getCurrentUserRoles();
  if (roles.length) {
    const lower = roles.map((r) => r.toLowerCase());
    const isPrivileged = PRIVILEGED_ROLE_NAMES.some((r) => lower.includes(r.toLowerCase()));
    if (isPrivileged) return false;
    return RESTRICTED_ROLE_NAMES.some((r) => lower.includes(r.toLowerCase()));
  }

  try {
    if (frappe?.user?.has_role) {
      if (PRIVILEGED_ROLE_NAMES.some((r) => frappe.user.has_role(r))) return false;
      return RESTRICTED_ROLE_NAMES.some((r) => frappe.user.has_role(r));
    }
  } catch (e) {}

  try {
    if (frappe?.has_role) {
      if (PRIVILEGED_ROLE_NAMES.some((r) => frappe.has_role(r))) return false;
      return RESTRICTED_ROLE_NAMES.some((r) => frappe.has_role(r));
    }
  } catch (e) {}

  return false;
}

const canExpandMergedRows = computed(() => {
  const currentUser = String(frappe?.session?.user || "").toLowerCase();
  if (currentUser === "administrator") return true;

  const roles = getCurrentUserRoles().map((r) => r.toLowerCase());
  return MERGE_EXPAND_ALLOWED_ROLES.some((role) => roles.includes(role.toLowerCase()));
});

const visibleUnits = computed(() => {
  if (!filterUnit.value) return units;
  return units.filter((u) => u === filterUnit.value);
});

const filteredData = computed(() => {
  let data = rawData.value || [];
  
  // Only show items that have been pushed to Production Board
  data = data.filter(d => !!d.plannedDate);

  // Exclude missing parameters and NO COLOR
  data = data.filter(d => {

      if (!d.quality || !d.color || !d.unit || d.unit === "Mixed" || d.unit === "Unassigned") return false;
      const colorUpper = d.color.toUpperCase().trim();
      if (colorUpper === "NO COLOR") return false;
      return true;
  });
  
  data = data.map(d => ({ ...d, unit: d.unit || "Mixed" }));

  if (filterPartyCode.value) {
    const search = filterPartyCode.value.toLowerCase();
    data = data.filter((d) =>
      (d.partyCode || "").toLowerCase().includes(search)
    );
  }
  if (filterCustomer.value) {
    const search = filterCustomer.value.toLowerCase();
    data = data.filter((d) =>
      (
        d.customer_name ||
        d.party_name ||
        d.customer ||
        d.partyCode ||
        d.party_code ||
        ""
      ).toLowerCase().includes(search)
    );
  }
  return data;
});

const mergeDialogItems = computed(() => {
  let items = filteredData.value || [];

  // Merge dialog must follow active table scope, not full dataset.
  if (filterUnit.value) {
    items = items.filter((d) => (d.unit || "") === filterUnit.value);
  }

  if (viewScope.value === "daily" && filterOrderDate.value) {
    items = items.filter((d) => String(d.plannedDate || "") === String(filterOrderDate.value));
  }

  const orderSearch = mergeFilterOrderCode.value.trim().toLowerCase();
  const customerSearch = mergeFilterCustomer.value.trim().toLowerCase();
  const qualitySearch = mergeFilterQuality.value.trim().toLowerCase();
  const colorSearch = mergeFilterColor.value.trim().toLowerCase();

  if (orderSearch) {
    items = items.filter((d) => (d.partyCode || "").toLowerCase().includes(orderSearch));
  }
  if (customerSearch) {
    items = items.filter((d) => ((d.customer_name || d.customer || "").toLowerCase().includes(customerSearch)));
  }
  if (qualitySearch) {
    items = items.filter((d) => (d.quality || "").toLowerCase().includes(qualitySearch));
  }
  if (colorSearch) {
    items = items.filter((d) => (d.color || "").toLowerCase().includes(colorSearch));
  }

  return items.filter((d) => !mergedItemsMap.value[d.itemName]);
});

const autoMergeSuggestions = computed(() => {
  const grouped = {};
  (mergeDialogItems.value || []).forEach((item) => {
    const key = [item.partyCode || "", item.quality || "", item.color || "", item.unit || "", item.plannedDate || ""].join("||");
    if (!grouped[key]) {
      grouped[key] = {
        key,
        partyCode: item.partyCode || "",
        quality: item.quality || "",
        color: item.color || "",
        gsmSet: new Set(),
        unit: item.unit || "",
        plannedDate: item.plannedDate || "",
        items: [],
      };
    }
    grouped[key].items.push(item);
    grouped[key].gsmSet.add(String(item.gsm || "-"));
  });
  return Object.values(grouped)
    .map((g) => ({ ...g, gsmSummary: Array.from(g.gsmSet).sort((a, b) => Number(a) - Number(b)).join(",") }))
    .filter((g) => g.items.length >= 2)
    .sort((a, b) => b.items.length - a.items.length);
});

const selectedMergeSummary = computed(() => {
  const selectedItems = (mergeDialogItems.value || []).filter((it) => selectedMergeItems.value.has(it.itemName));
  const targetWeight = selectedItems.reduce((sum, it) => sum + (parseFloat(it.qty) || 0), 0);
  const actualWeight = selectedItems.reduce((sum, it) => sum + (parseFloat(it.actual_production_weight_kgs) || 0), 0);
  return {
    count: selectedItems.length,
    targetWeight,
    actualWeight,
  };
});

function getMergeById(mergeId) {
  return (merges.value || []).find((m) => m.name === mergeId);
}

function isMergeExpanded(mergeId) {
  return expandedMerges.value.has(mergeId);
}

function toggleMergeExpanded(mergeId) {
  if (!canExpandMergedRows.value) return;
  if (expandedMerges.value.has(mergeId)) expandedMerges.value.delete(mergeId);
  else expandedMerges.value.add(mergeId);
}

const tableData = computed(() => {
    return visibleUnits.value.map(unit => {
        let items = filteredData.value.filter(d => (d.unit || "Mixed") === unit);
        
        const dateGroupsObj = {};
        items.forEach(item => {
            const d = item.plannedDate || "No Date";
            if (!dateGroupsObj[d]) dateGroupsObj[d] = { date: d, items: [], dailyTotal: 0 };
            dateGroupsObj[d].items.push(item);
            dateGroupsObj[d].dailyTotal += (item.qty || 0);
        });

    // Ensure maintenance dates are visible even when there are zero orders on those dates.
    for (const maintenanceDate of getScopeMaintenanceDates(unit)) {
      if (!dateGroupsObj[maintenanceDate]) {
        dateGroupsObj[maintenanceDate] = { date: maintenanceDate, items: [], dailyTotal: 0 };
      }
    }
        
        const dates = Object.values(dateGroupsObj).sort((a, b) => new Date(a.date) - new Date(b.date));
        
        // Sort each date group individually using Board's exact queuing for that day
        dates.forEach(group => {
            group.items = sortItems(unit, group.items, group.date);
            group.dailyActualTotal = group.items.reduce((sum, item) => sum + (parseFloat(item.actual_production_weight_kgs) || 0), 0);

            const seenMerges = new Set();
            const rows = [];
            group.items.forEach((item) => {
              const mergeId = mergedItemsMap.value[item.itemName];
              if (!mergeId) {
                rows.push({ type: "item", rowKey: `item-${item.itemName}`, item });
                return;
              }
              if (seenMerges.has(mergeId)) return;
              seenMerges.add(mergeId);

              const merge = getMergeById(mergeId);
              const mergeItems = (group.items || []).filter((it) => mergedItemsMap.value[it.itemName] === mergeId);
              const totalTargetWeight = mergeItems.reduce((s, it) => s + (parseFloat(it.qty) || 0), 0);
              const totalActualWeight = mergeItems.reduce((s, it) => s + (parseFloat(it.actual_production_weight_kgs) || 0), 0);
              const hasDispatchLock = mergeItems.some((it) => ["Partly Delivered", "Fully Delivered"].includes(String(it.delivery_status || "")));
              const statuses = mergeItems.map((it) => String(it.delivery_status || "Not Delivered"));
              const mergeDispatchStatus = statuses.every((s) => s === "Fully Delivered")
                ? "Fully Delivered"
                : statuses.some((s) => s === "Partly Delivered" || s === "Fully Delivered")
                  ? "Partly Delivered"
                  : "Not Delivered";
              const first = mergeItems[0] || item;
              const customer = first.customer_name || first.customer || "-";
              const gsmSummary = Array.from(new Set(mergeItems.map((it) => String(it.gsm || "-")).filter(Boolean)))
                .sort((a, b) => Number(a) - Number(b))
                .join(",");
              const displayLabel = `${customer}(${mergeItems.length}items)`;
              rows.push({
                type: "merge",
                rowKey: `merge-${mergeId}`,
                mergeId,
                mergeLabel: (merge && merge.merge_label) || `Merge ${mergeItems.length}`,
                displayLabel,
                items: mergeItems,
                partyCode: first.partyCode,
                customer,
                quality: first.quality,
                color: first.color,
                gsm: gsmSummary,
                totalTargetWeight,
                totalActualWeight,
                hasDispatchLock,
                mergeDispatchStatus,
              });
            });

            group.rows = rows;
        });

        const totalWeight = items.reduce((s, i) => s + (i.qty || 0), 0) / 1000;

        return { unit, dates, totalWeight };
    });
});

function formatDate(dateStr) {
    if (!dateStr || dateStr === 'No Date') return '-';
    const d = new Date(dateStr);
    return `${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()}`;
}

function getDayName(dateStr) {
    if (!dateStr || dateStr === 'No Date') return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { weekday: 'long' }).toUpperCase();
}

function getUnitHeaderColor(unit) {
    return "#fcd34d"; 
}

function formatKg(value) {
  const num = parseFloat(value || 0);
  if (!Number.isFinite(num)) return "0";
  return num.toFixed(0);
}

function formatKg2(value) {
  const num = parseFloat(value || 0);
  if (!Number.isFinite(num)) return "0.00";
  return num.toFixed(2);
}

function formatWidth(value) {
  const num = parseFloat(value);
  if (!Number.isFinite(num) || num <= 0) return "-";
  return `${num} in`;
}

function getMergeRuleKey(item) {
  return [
    String(item?.partyCode || "").trim().toUpperCase(),
    String(item?.quality || "").trim().toUpperCase(),
    String(item?.color || "").trim().toUpperCase(),
    String(item?.unit || "").trim().toUpperCase(),
    String(item?.plannedDate || "").trim(),
  ].join("||");
}

function formatDispatchStatus(status) {
    if (!status || status === 'Not Delivered') return 'NOT DESPATCHED';
    if (status === 'Fully Delivered') return 'DESPATCHED';
    if (status === 'Partly Delivered') return 'PARTLY DESPATCHED';
    return status.toUpperCase();
}

function getDispatchStatusClass(status) {
    if (!status || status === 'Not Delivered') return 'bg-red-100 text-red-800';
    if (status === 'Fully Delivered') return 'bg-green-100 text-green-800';
    if (status === 'Partly Delivered') return 'bg-orange-100 text-orange-800';
    return 'bg-gray-100 text-gray-800';
}

function toggleMergeMode() {
  mergeMode.value = !mergeMode.value;
  if (mergeMode.value) {
    showMergeDialog.value = true;
    tableReorderLocked.value = true;
    destroyTableSortables();
  } else {
    closeMergeDialog();
  }
}

function closeMergeDialog() {
  showMergeDialog.value = false;
  mergeMode.value = false;
  selectedMergeItems.value = new Set();
}

function openMergedProductionPlan(row) {
  const planningSheets = Array.from(new Set((row.items || []).map((it) => it.planningSheet).filter(Boolean)));
  if (!planningSheets.length) {
    frappe.msgprint("No Planning Sheet found for this merged row");
    return;
  }
  if (planningSheets.length > 1) {
    frappe.show_alert({ message: `Multiple planning sheets in merge. Opening first: ${planningSheets[0]}`, indicator: 'orange' });
  }
  const firstItem = (row.items || [])[0] || {};
  openProductionPlanView(planningSheets[0], firstItem.salesOrderItem, firstItem.itemName, firstItem.pp_id);
}

function toggleMergeSelection(itemName) {
  const next = new Set(selectedMergeItems.value);
  if (next.has(itemName)) next.delete(itemName);
  else next.add(itemName);
  selectedMergeItems.value = next;
}

function applyAutoMergeSuggestion() {
  const top = autoMergeSuggestions.value[0];
  if (!top) {
    frappe.msgprint("No auto merge suggestions available.");
    return;
  }
  const next = new Set(selectedMergeItems.value);
  top.items.forEach((item) => next.add(item.itemName));
  selectedMergeItems.value = next;
}

function selectSuggestion(suggestion) {
  const next = new Set(selectedMergeItems.value);
  suggestion.items.forEach((item) => next.add(item.itemName));
  selectedMergeItems.value = next;
}

async function loadMergesForCurrentData() {
  const dates = Array.from(new Set((filteredData.value || []).map((d) => d.plannedDate).filter(Boolean)));
  const all = [];
  for (const date of dates) {
    try {
      const res = await frappe.call({
        method: "production_scheduler.api.get_merges_for_date",
        args: {
          date,
          unit: filterUnit.value || null,
          plan_name: "Default",
        },
      });
      if (Array.isArray(res.message)) {
        res.message.forEach((m) => all.push(m));
      }
    } catch (e) {
      console.warn("Failed to load merge records", e);
    }
  }
  merges.value = all;
  const map = {};
  all.forEach((m) => {
    const mergedItems = Array.isArray(m.merged_items) ? m.merged_items : [];
    mergedItems.forEach((itemName) => {
      map[itemName] = m.name;
    });
  });
  mergedItemsMap.value = map;
}

async function createMergeFromDialog() {
  const selectedItems = (mergeDialogItems.value || []).filter((it) => selectedMergeItems.value.has(it.itemName));
  if (selectedItems.length < 2) {
    frappe.msgprint("Select at least 2 items to merge.");
    return;
  }

  const groupedByKey = {};
  selectedItems.forEach((it) => {
    const key = getMergeRuleKey(it);
    if (!groupedByKey[key]) groupedByKey[key] = [];
    groupedByKey[key].push(it);
  });
  const groupedSelections = Object.values(groupedByKey);

  if (groupedSelections.length > 1) {
    let success = 0;
    let failed = 0;

    for (const groupItems of groupedSelections) {
      if ((groupItems || []).length < 2) {
        failed += 1;
        continue;
      }

      const firstGroupItem = groupItems[0];
      const groupGsmSummary = Array.from(new Set(groupItems.map((it) => String(it.gsm || "-")).filter(Boolean)))
        .sort((a, b) => Number(a) - Number(b))
        .join(",");
      const groupLabel = `${firstGroupItem.partyCode || ''}, ${firstGroupItem.customer_name || firstGroupItem.customer || '-'}, ${firstGroupItem.quality || ''}, ${firstGroupItem.color || ''}, GSM: ${groupGsmSummary}`;

      const ok = await createMergeForItems(groupItems, groupLabel);
      if (ok) success += 1;
      else failed += 1;
    }

    await loadMergesForCurrentData();
    frappe.show_alert({ message: `Merge created: ${success}, failed: ${failed}`, indicator: failed ? "orange" : "green" });
    if (success > 0) closeMergeDialog();
    return;
  }

  const first = selectedItems[0];
  const sameSlot = selectedItems.every((it) => it.unit === first.unit && it.plannedDate === first.plannedDate);
  if (!sameSlot) {
    frappe.msgprint("Please select items from same Unit and Planned Date.");
    return;
  }

  const totalSelectedKg = selectedItems.reduce((s, it) => s + (parseFloat(it.qty) || 0), 0);
  const unitLimitKg = (UNIT_TONNAGE_LIMITS[first.unit] || 999) * 1000;
  if (totalSelectedKg > unitLimitKg) {
    frappe.msgprint(`Selected merge weight ${formatKg(totalSelectedKg)} Kg exceeds ${first.unit} capacity ${formatKg(unitLimitKg)} Kg`);
    return;
  }

  const selectedGsmSummary = Array.from(new Set(selectedItems.map((it) => String(it.gsm || "-")).filter(Boolean)))
    .sort((a, b) => Number(a) - Number(b))
    .join(",");

  const label = window.prompt(
    "Merge label",
    `${first.partyCode || ''}, ${first.customer_name || first.customer || '-'}, ${first.quality || ''}, ${first.color || ''}, GSM: ${selectedGsmSummary}`
  ) || "";
  if (!label.trim()) return;

  const ok = await createMergeForItems(selectedItems, label.trim());
  if (ok) {
    await loadMergesForCurrentData();
    frappe.show_alert({ message: "Merge created", indicator: "green" });
    closeMergeDialog();
  }
}

async function createMergeForItems(selectedItems, label) {
  if (!selectedItems || selectedItems.length < 2) {
    frappe.msgprint("Select at least 2 items to merge.");
    return false;
  }

  const first = selectedItems[0];
  const sameSlot = selectedItems.every((it) => it.unit === first.unit && it.plannedDate === first.plannedDate);
  if (!sameSlot) {
    frappe.msgprint("Please select items from same Unit and Planned Date.");
    return false;
  }

  const mergeKeys = new Set(selectedItems.map(getMergeRuleKey));
  if (mergeKeys.size > 1) {
    frappe.msgprint("Cannot merge different Order Code / Quality / Color groups together.");
    return false;
  }

  const totalSelectedKg = selectedItems.reduce((s, it) => s + (parseFloat(it.qty) || 0), 0);
  const unitLimitKg = (UNIT_TONNAGE_LIMITS[first.unit] || 999) * 1000;
  if (totalSelectedKg > unitLimitKg) {
    frappe.msgprint(`Selected merge weight ${formatKg(totalSelectedKg)} Kg exceeds ${first.unit} capacity ${formatKg(unitLimitKg)} Kg`);
    return false;
  }

  try {
    const res = await frappe.call({
      method: "production_scheduler.api.create_merge",
      args: {
        date: first.plannedDate,
        unit: first.unit,
        plan_name: "Default",
        item_names: JSON.stringify(selectedItems.map((it) => it.itemName)),
        merge_label: label,
      },
    });
    if (res.message && res.message.status === "success") {
      return true;
    }
  } catch (e) {
    frappe.msgprint(e?.message || "Unable to create merge");
  }
  return false;
}

async function createAllSuggestedMerges() {
  const suggestions = autoMergeSuggestions.value || [];
  if (!suggestions.length) {
    frappe.msgprint("No suggested groups found.");
    return;
  }

  let success = 0;
  let failed = 0;

  for (const s of suggestions) {
    const items = (s.items || []).filter(Boolean);
    if (items.length < 2) {
      failed += 1;
      continue;
    }

    const label = `${s.partyCode || ''}, ${items[0]?.customer_name || items[0]?.customer || '-'}, ${s.quality || ''}, ${s.color || ''}, GSM: ${s.gsmSummary || '-'}`;
    const ok = await createMergeForItems(items, label);
    if (ok) success += 1;
    else failed += 1;
  }

  await loadMergesForCurrentData();
  frappe.show_alert({ message: `Merge created: ${success}, failed: ${failed}`, indicator: failed ? "orange" : "green" });
  if (success > 0) closeMergeDialog();
}

async function deleteMerge(mergeId) {
  if (!mergeId) return;
  if (!window.confirm("Remove this merge and restore individual rows?")) return;
  try {
    const res = await frappe.call({
      method: "production_scheduler.api.delete_merge",
      args: { merge_id: mergeId },
    });
    if (res.message && res.message.status === "success") {
      frappe.show_alert({ message: "Merge removed", indicator: "orange" });
      await loadMergesForCurrentData();
    }
  } catch (e) {
    frappe.msgprint("Unable to remove merge");
  }
}

async function openProductionPlanView(planningSheetName, salesOrderItem = null, planningSheetItem = null, directPpId = null) {
  if (!planningSheetName) {
    frappe.msgprint("Planning Sheet not found for this order");
    return;
  }
  
  try {
    // STRICT PRIORITY: Item-level PP ID overrides everything. NO fallback allowed.
    let ppId = String(directPpId || "").trim();
    
    console.log("openProductionPlanView - STRICT mode:", {
      planningSheetName,
      planningSheetItem,
      directPpId,
      ppIdTrimmed: ppId,
      usingItemLevelPP: !!ppId
    });
    
    // If item-level PP is provided, use it directly and open immediately
    // WITHOUT calling API fallback, which might return different PP from Planning Sheet level
    if (ppId) {
      console.log("✅ Using ITEM-LEVEL PP ID directly (NO API fallback):", ppId);
      const printUrl = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(ppId)}&format=${encodeURIComponent("Assembly Item - Raw Material")}&trigger_print=0`;
      window.open(printUrl, '_blank');
      return;
    }
    
    // Only if NO item-level PP provided, fallback to API resolution (sheet-level or SO-level)
    console.warn("No item-level PP provided. Using API fallback for sheet:", planningSheetName);
    const res = await frappe.call({
      method: "production_scheduler.api.get_planning_sheet_pp_id",
      args: {
        planning_sheet_name: planningSheetName,
        sales_order_item: salesOrderItem,
        planning_sheet_item: planningSheetItem,
      }
    });
    
    if (res.message && res.message.status === "ok") {
      ppId = String(res.message.pp_id || "").trim();
      console.log("📌 API resolved PP (fallback):", ppId);
      
      if (ppId) {
        const printUrl = `/printview?doctype=${encodeURIComponent("Production Plan")}&name=${encodeURIComponent(ppId)}&format=${encodeURIComponent("Assembly Item - Raw Material")}&trigger_print=0`;
        window.open(printUrl, '_blank');
      } else {
        frappe.msgprint("No Production Plan found for this item");
      }
    } else {
      const errorMsg = res.message?.message || "Error fetching Production Plan";
      frappe.msgprint(errorMsg);
    }
  } catch (e) {
    frappe.msgprint("Error opening Production Plan");
    console.error(e);
  }
}

function canShowStockEntry(item) {
  if (!item || !item.pp_id) return false;

  const pendingQty = Number(item.pending_qty || item.pp_pending_qty || 0);
  if (!(pendingQty > 0)) return false;

  const woTerminal = !!item.wo_terminal;
  if (woTerminal) return false;

  // Strict remaining rule: continue entry only while pending qty exists and WO is non-terminal.
  return true;
}

function getStockEntryLabel(item) {
  if (!item) return '📝 Stock Entry';
  const isDraftSpr = !!item.spr_name && Number(item.spr_docstatus) === 0;
  if (isDraftSpr) {
    return `📝 Continue Entry${item.spr_unit ? ' (' + item.spr_unit + ')' : ''}`;
  }
  return '📝 Stock Entry';
}

function getStockEntryTitle(item) {
  if (!item) return 'Create Stock Entry';
  const isDraftSpr = !!item.spr_name && Number(item.spr_docstatus) === 0;
  const pendingQty = Number(item.pending_qty || 0);
  if (isDraftSpr) {
    return `Continue entry in draft SPR${item.spr_unit ? ' (' + item.spr_unit + ')' : ''}. Pending: ${pendingQty.toFixed(0)} Kg`;
  }
  return `Create new entry for pending qty ${pendingQty.toFixed(0)} Kg`;
}

function handleStockEntryAction(item) {
  if (!item) return;
  const isDraftSpr = !!item.spr_name && Number(item.spr_docstatus) === 0;
  if (isDraftSpr) {
    openItemSPR(item.spr_name, item);
    return;
  }
  createItemStockEntry(item);
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
      row.spr_name = sid;
    }
  });
}

async function createItemStockEntry(item) {
  if (item.__creating_spr) {
    return;
  }

  // Detailed debug logging
  console.log("createItemStockEntry called with item:", {
    itemName: item.itemName,
    pp_id: item.pp_id,
    partyCode: item.partyCode,
    color: item.color
  });
  // Resolve pp_id if missing but planningSheet exists
  if (!item.pp_id && item.planningSheet) {
    try {
      const ppRes = await frappe.call({
        method: "production_scheduler.api.get_planning_sheet_pp_id",
        args: {
          planning_sheet_name: item.planningSheet,
          sales_order_item: item.salesOrderItem || null,
          planning_sheet_item: item.itemName || null,
        }
      });
      if (ppRes.message && ppRes.message.status === "ok" && ppRes.message.pp_id) {
        item.pp_id = ppRes.message.pp_id;
        console.log(`Resolved PP for ${item.itemName}: ${item.pp_id}`);
      }
    } catch (e) {
      console.warn("Could not resolve PP for item", item.itemName, e);
    }
  }

  if (!item.pp_id) {
    frappe.msgprint("❌ No Production Plan linked to this item.<br/>Item Details:<br/>Code: " + item.partyCode + "<br/>Color: " + item.color);
    return;
  }
  
  if (!item.itemName) {
    frappe.msgprint("❌ Item Name missing - cannot create Stock Entry");
    return;
  }
  
  // Check if PP exists and has WOs started
  try {
    const ppCheckRes = await frappe.call({
      method: "frappe.client.get",
      args: {
        doctype: "Production Plan",
        name: item.pp_id
      }
    });
    
    if (!ppCheckRes.message) {
      frappe.msgprint(`❌ Production Plan '${item.pp_id}' not found in system.<br/>Please verify PP exists.`);
      console.error("PP not found:", item.pp_id);
      return;
    }
    
    const pp = ppCheckRes.message;
    console.log("Found PP:", pp.name);
    
    // Check if PP has Work Orders
    const woCheckRes = await frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Work Order",
        filters: { "production_plan": item.pp_id, "docstatus": ["<", 2] },
        limit_page_length: 1
      }
    });
    
    if (!woCheckRes.message || woCheckRes.message.length === 0) {
      frappe.msgprint(`⚠️ Production Plan '${item.pp_id}' has no started Work Orders.<br/>Please start production (create Work Orders) first.`);
      console.warn("No WO for PP:", item.pp_id);
      return;
    }
    
    console.log("Found WO for PP:", item.pp_id);
  } catch (e) {
    console.warn("Could not validate PP, proceeding anyway", e);
  }
  
  const itemDisplay = getItemDisplayName(item);

  frappe.confirm(
    `Create Stock Entry for <b>${item.partyCode}</b> (${item.color})?<br/>PP: ${item.pp_id}<br/>Item: ${itemDisplay}`,
    async () => {
      item.__creating_spr = true;
      try {
        console.log("Calling create_item_spr with:", {
          pp_id: item.pp_id,
          planning_sheet_item_names: [item.itemName]
        });
        
        const res = await frappe.call({
          method: "production_scheduler.api.create_item_spr",
          args: {
            pp_id: item.pp_id,
            planning_sheet_item_names: JSON.stringify([item.itemName])
          }
        });
        
        console.log("create_item_spr response:", res);
        console.log("Response status:", res.message?.status);
        console.log("Response message:", res.message?.message);
        console.log("Response full:", JSON.stringify(res.message));
        
        if (res.message && res.message.status === "ok") {
          const sprId = res.message.spr_id;
          item.spr_name = sprId;
          syncSprNameForSamePP(item.pp_id, sprId, item.itemName);
          const reused = !!res.message.reused;
          
          frappe.show_alert({
            message: reused ? `✅ Using existing SPR: ${sprId}. Opening form...` : `✅ SPR Created: ${sprId}. Opening form...`,
            indicator: 'green'
          }, 3);
          
          // Set flag for WO popup on SPR form
          frappe.flags.spr_show_wo_popup = item.pp_id;

          await new Promise(resolve => {
            setTimeout(() => {
              frappe.set_route('Form', 'Shaft Production Run', sprId);
              resolve();
            }, 800);
          });
        } else {
          const msg = res.message?.message || JSON.stringify(res.message) || "Failed to create SPR";
          console.error("SPR creation failed - Full response:", res.message);
          frappe.msgprint(`❌ Error: ${msg}`);
        }
      } catch (e) {
        console.error("Exception in createItemStockEntry:", e);
        frappe.msgprint(`❌ Error creating Stock Entry: ${e.message || e}`);
      } finally {
        item.__creating_spr = false;
      }
    }
  );
}

function getItemDisplayName(item) {
  if (!item) return "-";
  const semanticName = [item.quality, item.color, item.gsm].filter(Boolean).join(" ").trim();
  return (
    item.description ||
    item.item_name ||
    item.itemCode ||
    item.item_code ||
    semanticName ||
    item.itemName ||
    "-"
  );
}

async function createMergedStockEntry(mergedRow) {
  if (!mergedRow || !mergedRow.items || mergedRow.items.length === 0) {
    frappe.msgprint("No items in merged row");
    return;
  }
  
  // Resolve missing pp_id for items that have a planningSheet but no pp_id
  for (const item of mergedRow.items) {
    if (!item.pp_id && item.planningSheet) {
      try {
        const res = await frappe.call({
          method: "production_scheduler.api.get_planning_sheet_pp_id",
          args: {
            planning_sheet_name: item.planningSheet,
            sales_order_item: item.salesOrderItem || null,
            planning_sheet_item: item.itemName || null,
          }
        });
        if (res.message && res.message.status === "ok" && res.message.pp_id) {
          item.pp_id = res.message.pp_id;
          console.log(`Resolved PP for ${item.itemName}: ${item.pp_id}`);
        }
      } catch (e) {
        console.warn("Could not resolve PP for item", item.itemName, e);
      }
    }
  }
  
  // Group by PP ID
  const groupedByPP = {};
  let noPPCount = 0;
  
  for (const item of mergedRow.items) {
    if (!item.pp_id) {
      noPPCount++;
      continue;
    }
    const pp = item.pp_id;
    if (!groupedByPP[pp]) groupedByPP[pp] = [];
    groupedByPP[pp].push(item);
  }
  
  const ppGroups = Object.entries(groupedByPP);
  
  if (ppGroups.length === 0) {
    if (noPPCount > 0) {
      frappe.msgprint(`⚠️ All ${noPPCount} items in merged row have no Production Plan linked.<br/>Please create Production Plans first.`);
    } else {
      frappe.msgprint("No items found in merged row");
    }
    return;
  }
  
  if (noPPCount > 0) {
    frappe.show_alert({
      message: `⚠️ ${noPPCount} item(s) have no PP. Creating SPRs for ${ppGroups.reduce((sum, [, items]) => sum + items.length, 0)} items with PPs.`,
      indicator: 'orange'
    }, 5);
  }
  
  if (ppGroups.length === 1) {
    // Same PP - create 1 SPR
    await createSingleMergedSPR(ppGroups[0][0], ppGroups[0][1], mergedRow);
  } else {
    // Multiple PPs - create separate SPRs
    frappe.msgprint(`Merged items have ${ppGroups.length} different Production Plans.<br/>Creating separate SPRs for each...`);
    for (const [pp, items] of ppGroups) {
      await createSingleMergedSPR(pp, items, mergedRow);
    }
  }
}

async function createSingleMergedSPR(ppId, mergedItems, mergedRow) {
  return new Promise((resolve) => {
    // First validate WO exists
    frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Work Order",
        filters: { "production_plan": ppId, "docstatus": ["<", 2] },
        limit_page_length: 1
      },
      async callback(r) {
        if (!r.message || r.message.length === 0) {
          frappe.msgprint(`⚠️ No Work Orders found for PP: ${ppId}<br/>Please start production first.`);
          resolve();
          return;
        }
        
        // WO exists, proceed with confirmation
        frappe.confirm(
          `Create SPR for ${mergedItems.length} merged items?<br/>PP: ${ppId}`,
          async () => {
            try {
              const itemNames = mergedItems.map(it => it.itemName);
              const res = await frappe.call({
                method: "production_scheduler.api.create_item_spr",
                args: {
                  pp_id: ppId,
                  planning_sheet_item_names: JSON.stringify(itemNames)
                }
              });
              
              if (res.message && res.message.status === "ok") {
                const sprId = res.message.spr_id;
                mergedRow.spr_name = sprId;
                const reused = !!res.message.reused;

                showLinkedWorkOrdersPopup(ppId);
                
                frappe.show_alert({
                  message: reused ? `✅ Using existing merged SPR: ${sprId}. Opening form...` : `✅ Merged SPR Created: ${sprId}. Opening form...`,
                  indicator: 'green'
                }, 3);
                
                await new Promise(rr => setTimeout(() => {
                  frappe.set_route('Form', 'Shaft Production Run', sprId);
                  rr();
                }, 1000));
              } else {
                frappe.msgprint(res.message?.message || "Failed to create SPR");
              }
              resolve();
            } catch (e) {
              frappe.msgprint("Error creating SPR");
              console.error(e);
              resolve();
            }
          },
          () => resolve()
        );
      }
    });
  });
}

function openItemSPR(sprName, item = null) {
  if (!sprName) {
    frappe.msgprint("No SPR linked");
    return;
  }
  
  // Verify SPR still exists
  frappe.call({
    method: "frappe.client.get",
    args: { doctype: "Shaft Production Run", name: sprName },
    callback: (r) => {
      if (r.message) {
        // SPR exists, open it
        frappe.set_route('Form', 'Shaft Production Run', sprName);
      } else {
        // SPR was deleted, allow creating new one
        if (item) {
          item.spr_name = "";
          frappe.show_alert({
            message: '⚠️ SPR was deleted. You can create a new one.',
            indicator: 'orange'
          }, 3);
          createItemStockEntry(item);
        } else {
          frappe.msgprint("SPR not found. It may have been deleted.");
        }
      }
    }
  });
}

function openMergedSPR(sprName, mergedRow) {
  if (!sprName) {
    frappe.msgprint("No SPR linked");
    return;
  }
  
  // Verify SPR still exists
  frappe.call({
    method: "frappe.client.get",
    args: { doctype: "Shaft Production Run", name: sprName },
    callback: (r) => {
      if (r.message) {
        // SPR exists, open it
        frappe.set_route('Form', 'Shaft Production Run', sprName);
      } else {
        // SPR was deleted, allow creating new one
        if (mergedRow) {
          mergedRow.spr_name = "";
          frappe.show_alert({
            message: '⚠️ SPR was deleted. You can create a new one.',
            indicator: 'orange'
          }, 3);
          createMergedStockEntry(mergedRow);
        } else {
          frappe.msgprint("SPR not found. It may have been deleted.");
        }
      }
    }
  });
}

function showLinkedWorkOrdersPopup(ppId) {
  if (!ppId) return;

  frappe.call({
    method: "frappe.client.get_list",
    args: {
      doctype: "Work Order",
      filters: {
        production_plan: ppId,
        docstatus: ["<", 2]
      },
      fields: ["name", "production_item", "status", "qty", "produced_qty"],
      order_by: "creation asc",
      limit_page_length: 20
    },
    callback: (r) => {
      const rows = Array.isArray(r.message) ? r.message : [];
      if (!rows.length) return;

      const body = rows.map((wo) => {
        const target = Number(wo.qty || 0);
        const produced = Number(wo.produced_qty || 0);
        const pending = target - produced;
        return `
          <tr>
            <td><b>${wo.name}</b></td>
            <td>${wo.production_item || "-"}</td>
            <td>${wo.status || "-"}</td>
            <td style="text-align:right;">${target.toFixed(2)}</td>
            <td style="text-align:right;">${produced.toFixed(2)}</td>
            <td style="text-align:right;">${pending.toFixed(2)}</td>
          </tr>
        `;
      }).join("");

      const html = `
        <div style="max-height:420px; overflow:auto;">
          <table class="table table-sm table-bordered">
            <thead>
              <tr>
                <th>WO</th>
                <th>Item</th>
                <th>Status</th>
                <th style="text-align:right;">Target</th>
                <th style="text-align:right;">Produced</th>
                <th style="text-align:right;">Pending</th>
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;

      const d = new frappe.ui.Dialog({
        title: `Work Orders for ${ppId}`,
        fields: [{ fieldtype: "HTML", fieldname: "wo_html", options: html }],
        primary_action_label: "Close",
        primary_action() {
          d.hide();
        }
      });
      d.show();
    }
  });
}

function goToBoard() {
    frappe.set_route("production-board");
}

function toggleViewScope() {
    // Prevent manufacture users from changing view scope - force back to daily
    if (isManufactureUser.value) {
        viewScope.value = "daily";
        filterOrderDate.value = frappe.datetime.get_today();
        console.warn("Manufacture users cannot change view scope");
        return;
    }
    
    // Normal users can change scope
    if (viewScope.value === 'monthly' && !filterMonth.value) {
        filterMonth.value = frappe.datetime.get_today().substring(0, 7);
    } else if (viewScope.value === 'weekly' && !filterWeek.value) {
        const d = new Date();
        const dStart = new Date(d.getFullYear(), 0, 1);
        const days = Math.floor((d - dStart) / (24 * 60 * 60 * 1000));
        const weekNum = Math.ceil(days / 7);
        filterWeek.value = `${d.getFullYear()}-W${String(weekNum).padStart(2,'0')}`;
    }
    fetchData();
}

let fetchTimeout = null;

async function fetchData() {
  return new Promise((resolve) => {
    if (fetchTimeout) clearTimeout(fetchTimeout);
    fetchTimeout = setTimeout(async () => {
      try {
        let args = { party_code: filterPartyCode.value };
        
        if (viewScope.value === 'monthly') {
            if (!filterMonth.value) return resolve();
            const startDate = `${filterMonth.value}-01`;
            const [year, month] = filterMonth.value.split("-");
            const lastDay = new Date(year, month, 0).getDate();
            const endDate = `${filterMonth.value}-${lastDay}`;
            args.start_date = startDate;
            args.end_date = endDate;
        } else if (viewScope.value === 'weekly') {
            if (!filterWeek.value) return resolve();
            const [yearStr, weekStr] = filterWeek.value.split('-W');
            const y = parseInt(yearStr);
            const w = parseInt(weekStr);
            const simple = new Date(y, 0, 1 + (w - 1) * 7);
            const dow = simple.getDay();
            const ISOweekStart = new Date(simple);
            if (dow <= 4) ISOweekStart.setDate(simple.getDate() - simple.getDay() + 1);
            else ISOweekStart.setDate(simple.getDate() + 8 - simple.getDay());
            
            const ISOweekEnd = new Date(ISOweekStart);
            ISOweekEnd.setDate(ISOweekEnd.getDate() + 6);
            
            const format = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
            args.start_date = format(ISOweekStart);
            args.end_date = format(ISOweekEnd);
        } else {
            args.date = filterOrderDate.value;
        }

        args.plan_name = "__all__";
        args.planned_only = 1;

    const r = await frappe.call({
      method: "production_scheduler.api.get_color_chart_data",
      args: args,
    });
    rawData.value = (r.message || []).map(d => ({
      ...d,
      plannedDate: d.plannedDate || d.planned_date || "",
      partyCode: d.partyCode || d.party_code || "",
      customer_name: d.customer_name || d.party_name || d.customer || d.party_code || "",
      itemName: d.itemName || d.item_name || "",
      orderDate: d.orderDate || d.ordered_date || "",
      planCode: d.custom_plan_code || "",
      // Actual production weight must come only from SPR achieved fields.
      actual_production_weight_kgs: parseFloat(
        d.actual_production_weight_kgs ?? d.total_achieved_weight_kgs ?? 0
      ) || 0,
    }));

    // After loading raw data, fetch the exact sequence for the range 
    // to match the Production Board's exact queuing flow for each day.
    let seqStart = args.start_date;
    let seqEnd = args.end_date;
    
    // For single day, use the same date for start/end
    if (args.date && !seqStart) {
        seqStart = args.date;
        seqEnd = args.date;
    }
    
    if (seqStart && seqEnd) {
        try {
            const seqRes = await frappe.call({
                method: "production_scheduler.api.get_color_sequences_range",
                args: { 
                    start_date: seqStart, 
                    end_date: seqEnd, 
                    unit: filterUnit.value || "All Units",
                // Must match save_color_sequence plan_name to avoid loading stale rows
                plan_name: "Default" 
                }
            });
            if (seqRes.message) {
                // Backend returns keys as "unit-date", but unit might have dashes.
                // Reconstruct using the unit and date from object properties instead.
                const normalized = {};
                for (const [origKey, val] of Object.entries(seqRes.message)) {
                    // Parse the key carefully: "Unit 1-2026-01-18" -> unit="Unit 1", date="2026-01-18"
                    // Assume date is always YYYY-MM-DD at the end
                    const dateMatch = origKey.match(/(\d{4}-\d{2}-\d{2})$/);
                    if (dateMatch) {
                        const date = dateMatch[1];
                        const unit = origKey.substring(0, origKey.length - date.length - 1).trim();
                        const normalizedUnit = normalizeUnit(unit);
                        const newKey = `${normalizedUnit}||${date}`;
                        normalized[newKey] = val;
                        console.log(`Mapped key: ${origKey} -> ${newKey}`);
                    }
                }
                Object.assign(unitSequenceStore, normalized);
                console.log("Sequences loaded:", Object.keys(normalized).length, "keys");
            }
        } catch (e) {
            console.warn(`Failed to fetch sequence range`, e);
        }
    }

    await loadMergesForCurrentData();
      } catch (e) {
        frappe.msgprint("Error loading plan data");
        console.error(e);
      }
      await initTableSortables();
      resolve();
    }, 150);
  });
}

function updateUrlParams() {
    let query = {};
    if (viewScope.value === 'daily') query.date = filterOrderDate.value;
    if (viewScope.value === 'weekly') query.week = filterWeek.value;
    if (viewScope.value === 'monthly') query.month = filterMonth.value;
    query.scope = viewScope.value;
    
    const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname + '?' + new URLSearchParams(query).toString();
    window.history.replaceState({path: newUrl}, '', newUrl);
}

watch(viewScope, (newVal) => {
  // Manufacture users are locked to "daily" view
  if (isManufactureUser.value && newVal !== "daily") {
    console.warn("Manufacture users cannot change view scope - resetting to daily");
    viewScope.value = "daily";
    fetchData();
    return;
  }
  updateUrlParams();
});
watch(filterOrderDate, (newVal) => {
  // Prevent manufacture users from changing the date - force today
  if (isManufactureUser.value && newVal !== frappe.datetime.get_today()) {
    filterOrderDate.value = frappe.datetime.get_today();
    return;
  }
  updateUrlParams();
});
watch(filterWeek, updateUrlParams);
watch(filterMonth, updateUrlParams);

onMounted(async () => {
  // Check user role for visibility control
  try {
    isManufactureUser.value = detectRestrictedUser();
  } catch (e) {
    console.log("Could not detect user role", e);
    isManufactureUser.value = false;
  }
  
  const params = new URLSearchParams(window.location.search);
  const scopeParam = params.get('scope');
  const dateParam = params.get('date');
  const weekParam = params.get('week');
  const monthParam = params.get('month');
  
  // For manufacture users: FORCE daily view with today's date only
  if (isManufactureUser.value) {
    viewScope.value = "daily";
    filterOrderDate.value = frappe.datetime.get_today();
  } else {
    // For other users: respect URL parameters
    if (scopeParam) viewScope.value = scopeParam;
    if (dateParam) filterOrderDate.value = dateParam;
    if (weekParam) filterWeek.value = weekParam;
    if (monthParam) filterMonth.value = monthParam;
  }
  
  await fetchMaintenanceRecords();
  await fetchData();
});

onBeforeUnmount(() => {
  destroyTableSortables();
});
</script>

<style scoped>
.cc-container {
  display: flex;
  flex-direction: column;
  padding: 16px;
  background-color: #f3f4f6;
  min-height: 100vh;
}
.cc-filters {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  margin-bottom: 20px;
  gap: 12px;
}
.cc-filter-item {
  display: flex;
  flex-direction: column;
}
.cc-filter-item label {
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 2px;
}
.cc-filter-item input,
.cc-filter-item select {
  padding: 6px 8px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
}
.cc-clear-btn, .cc-view-btn {
  padding: 8px 16px;
  background-color: white;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  font-weight: 500;
}
.cc-lock-btn {
  padding: 8px 14px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  font-weight: 600;
  background: #fff7ed;
  color: #9a3412;
}
.cc-save-arrange-btn {
  padding: 8px 14px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  font-weight: 600;
  background: #16a34a;
  color: white;
}
.cc-save-arrange-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.cc-arrange-indicator {
  font-size: 12px;
  font-weight: 600;
}
.cc-arrange-indicator.saving {
  color: #2563eb;
}
.cc-arrange-indicator.dirty {
  color: #c2410c;
}
.cc-arrange-indicator.clean {
  color: #15803d;
}
.cc-view-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
}
.cc-maint-btn {
    padding: 8px 16px;
    background-color: #f97316;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    font-weight: 600;
    transition: all 0.2s;
}
.cc-maint-btn:hover {
    background-color: #ea580c;
    box-shadow: 0 2px 4px rgba(249, 115, 22, 0.3);
}

.cc-pp-btn {
    padding: 6px 12px;
    background-color: #8b5cf6;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    font-weight: 600;
    transition: all 0.2s;
    white-space: nowrap;
}
.cc-pp-btn:hover {
    background-color: #7c3aed;
    box-shadow: 0 2px 4px rgba(139, 92, 246, 0.3);
}

.cc-table-container {
    display: flex;
    flex-direction: column;
    gap: 30px;
}
.cc-table-unit-header {
    padding: 10px 15px;
    font-weight: 800;
    font-size: 14px;
    border-radius: 8px 8px 0 0;
    border: 1px solid #e5e7eb;
    border-bottom: none;
}
.cc-prod-table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    font-size: 12px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.cc-prod-table th {
    background: #f8fafc;
    padding: 10px;
    border: 1px solid #e5e7eb;
    text-align: center;
    font-weight: 700;
}
.pt-sortable-body .pt-draggable-row {
  transition: background-color 0.2s;
}
.pt-sortable-body .pt-draggable-row:hover {
  background-color: #f8fafc;
}
.pt-drag-handle {
  display: inline-block;
  user-select: none;
}
.cc-prod-table td {
    padding: 8px;
    border: 1px solid #e5e7eb;
}
.cell-center { text-align: center; }
.cell-right { text-align: right; }
.font-bold { font-weight: 700; }
.bg-yellow-50 { background-color: #fefce8; }

.status-badge {
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
}
.bg-red-100 { background: #fee2e2; color: #991b1b; }
.bg-green-100 { background: #dcfce7; color: #166534; }
.bg-orange-100 { background: #ffedd5; color: #9a3412; }
.bg-gray-100 { background: #f3f4f6; color: #374151; }

.pt-draggable-row.pt-drag-ghost {
  opacity: 0.4 !important;
  background-color: #f0f9ff !important;
}

.pt-draggable-row.pt-drag-chosen {
  background-color: #dbeafe !important;
  box-shadow: inset 0 0 8px rgba(59, 130, 246, 0.3) !important;
}

.pt-draggable-row.pt-drag-dragging {
  opacity: 1 !important;
  background-color: #e0f2fe !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
  z-index: 1000 !important;
  transform: scale(1.01) !important;
}

.pt-sortable-body.sortable-ghost {
  background-color: #f5f5f5 !important;
}

.pt-merge-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pt-merge-dialog {
  width: min(980px, 92vw);
  max-height: 88vh;
  overflow: hidden;
  background: white;
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
}

.pt-merge-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.pt-merge-close {
  border: none;
  background: transparent;
  font-size: 18px;
  cursor: pointer;
}

.pt-merge-filters {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.pt-merge-filters input {
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 8px;
  font-size: 13px;
}

.pt-merge-suggest {
  padding: 8px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.pt-merge-summary {
  display: flex;
  gap: 20px;
  padding: 8px 16px;
  border-bottom: 1px solid #e5e7eb;
  background: #f8fafc;
  font-size: 12px;
  color: #334155;
}

.pt-merge-suggest-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.pt-merge-suggest-pill {
  border: 1px solid #c4b5fd;
  background: #f5f3ff;
  color: #5b21b6;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.pt-merge-list {
  padding: 10px 16px;
  overflow: auto;
  max-height: 45vh;
}

.pt-merge-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed #e5e7eb;
  font-size: 12px;
}

.pt-merge-empty {
  color: #6b7280;
  font-style: italic;
}

.pt-merge-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #e5e7eb;
}

.pt-merge-row {
  background: #faf5ff;
}

.pt-merge-expand-btn {
  border: none;
  background: transparent;
  color: #6d28d9;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
}

.pt-merge-expanded-row {
  background: #fdf4ff;
}

.pt-merge-inline-details {
  margin-top: 6px;
  padding: 6px 8px;
  background: #faf5ff;
  border: 1px solid #e9d5ff;
  border-radius: 6px;
}

.pt-merge-inline-item {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  padding: 2px 0;
  color: #334155;
}
</style>