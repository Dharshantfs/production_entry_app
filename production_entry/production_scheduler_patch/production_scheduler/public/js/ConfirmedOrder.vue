<template>
  <div class="cc-container">
    <!-- Filter Bar -->
    <div class="cc-filters">
      <div class="cc-filter-item">
        <label>View Scope</label>
        <select v-model="viewScope" @change="toggleViewScope" style="font-weight: bold; color: #4f46e5;">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </div>
      
      <div class="cc-filter-item" v-if="viewScope === 'daily'">
        <label>Planned Date</label>
        <input type="date" v-model="filterOrderDate" @change="fetchData" />
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
        <label>Delivery Date</label>
        <input type="date" v-model="filterDeliveryDate" @change="fetchData" />
      </div>
      <div class="cc-filter-item">
        <label>Party Code</label>
        <input type="text" v-model="filterPartyCode" placeholder="Search party..." @input="fetchData" />
      </div>
      <div class="cc-filter-item">
        <label>Customer</label>
        <input type="text" v-model="filterCustomer" placeholder="Search customer..." @input="fetchData" />
      </div>
      <div class="cc-filter-item">
        <label>Unit</label>
        <select v-model="filterUnit">
          <option value="">All Units</option>
          <option v-for="u in units" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>
      <button class="cc-clear-btn" @click="clearFilters">✕ Clear</button>
      
      <div class="cc-filter-item" style="flex-direction:row; align-items:flex-end; gap:4px; margin-left:auto;">
          <button class="cc-view-btn" :class="{ active: viewMode === 'kanban' }" @click="viewMode = 'kanban'">📋 Kanban</button>
          <button class="cc-view-btn" :class="{ active: viewMode === 'table' }" @click="viewMode = 'table'">📊 Table</button>
      </div>
    </div>

    <div v-if="viewMode === 'kanban'" class="cc-board" :key="renderKey">
      <div
        v-for="unit in visibleUnits"
        :key="unit"
        class="cc-column"
        :data-unit="unit"
      >
        <div class="cc-col-header" :style="{ borderTopColor: headerColors[unit] }">
          <div class="cc-header-top">
            <span class="cc-col-title">{{ unit === 'Mixed' ? 'Unassigned' : unit }}</span>
            <!-- Sort Controls -->
            <div class="cc-unit-controls">
              <span style="font-size:10px; color:#64748b; margin-right:4px;">{{ getSortLabel(unit) }}</span>
              <button class="cc-mini-btn" @click="toggleUnitColor(unit)" :title="getUnitSortConfig(unit).color === 'asc' ? 'Light->Dark' : 'Dark->Light'">
                {{ getUnitSortConfig(unit).color === 'asc' ? '☀️' : '🌙' }}
              </button>
              <button class="cc-mini-btn" @click="toggleUnitGsm(unit)" :title="getUnitSortConfig(unit).gsm === 'desc' ? 'High->Low' : 'Low->High'">
                {{ getUnitSortConfig(unit).gsm === 'desc' ? '⬇️' : '⬆️' }}
              </button>
              <button class="cc-mini-btn" @click="toggleUnitPriority(unit)" :title="getUnitSortConfig(unit).priority === 'color' ? 'Color Priority' : 'GSM Priority'">
                {{ getUnitSortConfig(unit).priority === 'color' ? '🎨' : '📏' }}
              </button>
            </div>
          </div>
            <span class="cc-stat-weight" :class="getUnitCapacityStatus(unit).class">
              {{ getUnitTotal(unit).toFixed(2) }} / {{ UNIT_TONNAGE_LIMITS[unit] }}T
            </span>
            <div v-if="getUnitCapacityStatus(unit).warning" class="text-xs text-red-600 font-bold">
              {{ getUnitCapacityStatus(unit).warning }}
            </div>
             <span class="cc-stat-mix" v-if="getMixRollCount(unit) > 0">
              ⚠️ {{ getMixRollCount(unit) }} mix{{ getMixRollCount(unit) > 1 ? 'es' : '' }}
              ({{ getMixRollTotalWeight(unit) }} Kg)
            </span>
          </div>

        <div class="cc-col-body" :data-unit="unit" ref="columnRefs">
          <template v-for="(entry, idx) in getUnitEntries(unit)" :key="entry.uniqueKey">
            <!-- Mix Roll Marker (HIDDEN as per user request) -->
            <div v-if="entry.type === 'mix'" class="cc-mix-marker" style="display:none;">
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
                    <span v-if="entry.partyCode !== entry.customer" style="font-weight:400; color:#6b7280;"> · {{ entry.customer }}</span>
                  </div>
                  <div class="cc-card-details">
                    {{ entry.quality }} · {{ entry.gsm }} GSM
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
            No confirmed orders
          </div>
        </div>

        <!-- Unit Footer -->
        <div class="cc-col-footer">
          <span>Total: {{ getUnitProductionTotal(unit).toFixed(2) }}T</span>
        </div>
      </div>
    </div>

    <!-- TABLE VIEW -->
    <div v-else-if="viewMode === 'table'" class="cc-table-container" style="padding:16px;">
        <div v-for="unitGroup in tableData" :key="unitGroup.unit" class="cc-table-unit-block">
            <!-- Unit Header -->
            <div class="cc-table-unit-header" :style="{ backgroundColor: getUnitHeaderColor(unitGroup.unit) }">
                {{ unitGroup.unit.toUpperCase() }} (06:00 am to 06:00 am) - Total: {{ unitGroup.totalWeight.toFixed(2) }} T
            </div>
            
            <table class="cc-prod-table">
                <thead>
                    <tr>
                        <th style="width: 80px;">DATE</th>
                        <th style="width: 80px;">DAY</th>
                        <th style="width: 100px;">PARTY CODE</th>
                        <th style="width: 150px;">PARTY NAME</th>
                        <th style="width: 80px;">QUALITY</th>
                        <th style="width: 100px;">COLOUR</th>
                        <th style="width: 80px;">GSM</th>
                        <th style="width: 80px;">WEIGHT (Kg)</th>
                        <th style="width: 80px;">ACTUAL PROD</th>
                        <th style="width: 100px;">DESPATCH STATUS</th>
                    </tr>
                </thead>
                <tbody>
                    <template v-for="dateGroup in unitGroup.dates" :key="dateGroup.date">
                        <template v-for="(item, idx) in dateGroup.items" :key="item.itemName">
                            <tr>
                                <td v-if="idx === 0" :rowspan="dateGroup.items.length" class="cell-center font-bold">
                                    {{ formatDate(dateGroup.date) }}
                                </td>
                                <td v-if="idx === 0" :rowspan="dateGroup.items.length" class="cell-center">
                                    {{ getDayName(dateGroup.date) }}
                                </td>
                                
                                <td class="cell-center">{{ item.partyCode }}</td>
                                <td>{{ item.customer }}</td>
                                <td class="cell-center">{{ item.quality }}</td>
                                <td class="cell-center font-bold">{{ item.color }}</td>
                                <td class="cell-center">{{ item.gsm }}</td>
                                <td class="cell-right font-bold">{{ item.qty }}</td>
                                
                                <td v-if="idx === 0" :rowspan="dateGroup.items.length" class="cell-center font-bold bg-yellow-50">
                                    {{ dateGroup.dailyTotal.toFixed(0) }}
                                </td>
                                
                                <td class="cell-center">
                                    <span class="status-badge" :class="getDispatchStatusClass(item.delivery_status || item.status)">
                                        {{ formatDispatchStatus(item.delivery_status || item.status) }}
                                    </span>
                                </td>
                            </tr>
                        </template>
                    </template>
                    <tr v-if="unitGroup.dates.length === 0">
                        <td colspan="10" style="text-align:center; padding: 20px; color:#999;">No production planned for this unit</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";

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

const unitSequenceStore = ref({});

const units = ["Unit 1", "Unit 2", "Unit 3", "Unit 4", "Mixed"];
const UNIT_TONNAGE_LIMITS = { "Unit 1": 4.4, "Unit 2": 12, "Unit 3": 9, "Unit 4": 5.5, "Mixed": 999 };
const headerColors = { "Unit 1": "#3b82f6", "Unit 2": "#10b981", "Unit 3": "#f59e0b", "Unit 4": "#8b5cf6", "Mixed": "#64748b" };

const storedDate = localStorage.getItem("confirmed_order_date");
const defaultDate = frappe.datetime.get_today();
const filterOrderDate = ref(storedDate || defaultDate); 
const filterWeek = ref("");
const filterMonth = ref("");
const viewScope = ref("daily");

watch(filterOrderDate, (newVal) => {
    localStorage.setItem("confirmed_order_date", newVal || "");
});
const filterDeliveryDate = ref("");
const filterPartyCode = ref("");
const filterCustomer = ref("");
const filterUnit = ref("");

const unitSortConfig = ref({});
const rawData = ref([]);
const columnRefs = ref(null);
const renderKey = ref(0);
const viewMode = ref('kanban'); // 'kanban' | 'table'
const tableSortKey = ref('unit');
const tableSortDir = ref('asc');

function toggleSort(key) {
    if (tableSortKey.value === key) {
        tableSortDir.value = tableSortDir.value === 'asc' ? 'desc' : 'asc';
    } else {
        tableSortKey.value = key;
        tableSortDir.value = 'asc';
    }
}

const tableData = computed(() => {
    return visibleUnits.value.map(unit => {
        let items = filteredData.value.filter(d => (d.unit || "Mixed") === unit);
        
        // Sort items using existing logic
        items = sortItems(unit, items);

        const dateGroupsObj = {};
        items.forEach(item => {
            const d = item.order_date || item.date || "No Date";
            if (!dateGroupsObj[d]) dateGroupsObj[d] = { date: d, items: [], dailyTotal: 0 };
            dateGroupsObj[d].items.push(item);
            dateGroupsObj[d].dailyTotal += (item.qty || 0);
        });
        
        const dates = Object.values(dateGroupsObj).sort((a, b) => new Date(a.date) - new Date(b.date));
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

function toggleViewScope() {
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

function goToPlan() {
    frappe.set_route("production-table");
}

const visibleUnits = computed(() =>
  filterUnit.value ? units.filter((u) => u === filterUnit.value) : units
);

const EXCLUDED_WHITES = ["WHITE", "BRIGHT WHITE", "P. WHITE", "P.WHITE", "R.F.D", "RFD", "BLEACHED", "B.WHITE", "SNOW WHITE"];

const filteredData = computed(() => {
  let data = rawData.value;

  data = data.filter(d => {
      if (!d.unit) d.unit = "Mixed";
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
    data = data.filter((d) => d.unit === filterUnit.value);
  }
  
  return data;
});

// ---- TABLE VIEW DATA ----

function clearFilters() {
  filterOrderDate.value = frappe.datetime.get_today();
  filterDeliveryDate.value = "";
  filterPartyCode.value = "";
  filterCustomer.value = "";
  filterUnit.value = "";
  filterWeek.value = "";
  filterMonth.value = "";
  viewScope.value = 'daily';
  fetchData();
}

// ... COLOR/SORT HELPERS (SAME AS COLOR CHART) ...
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

function getHexColor(color) {
  const group = findColorGroup(color);
  return group ? group.hex : "#ccc";
}

function getMixRollQty(gap) {
  const baseQty = 100;
  const increment = Math.floor(gap / 4) * 100;
  return Math.min(baseQty + increment, 1000);
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

const QUALITY_PRIORITY = {
  "Unit 1": { "PREMIUM": 1, "PLATINUM": 2, "SUPER PLATINUM": 3, "GOLD": 4, "SILVER": 5 },
  "Unit 2": { 
      "GOLD": 1, "SILVER": 2, "BRONZE": 3, "CLASSIC": 4, "SUPER CLASSIC": 5, 
      "LIFE STYLE": 6, "ECO SPECIAL": 7, "ECO GREEN": 8, "SUPER ECO": 9, "ULTRA": 10, "DELUXE": 11 
  },
  "Unit 3": { "PREMIUM": 1, "PLATINUM": 2, "SUPER PLATINUM": 3, "GOLD": 4, "SILVER": 5, "BRONZE": 6 },
  "Unit 4": { "PREMIUM": 1, "GOLD": 2, "SILVER": 3, "BRONZE": 4 },
};

function getQualityPriority(unit, quality) {
  const upper = (quality || "").toUpperCase().trim();
  return (QUALITY_PRIORITY[unit] || {})[upper] || 99;
}

function compareQuality(unit, a, b) {
    return getQualityPriority(unit, a.quality) - getQualityPriority(unit, b.quality);
}

function compareColor(a, b, direction) {
    const pA = getColorPriority(a.color);
    const pB = getColorPriority(b.color);
    return direction === 'asc' ? pA - pB : pB - pA;
}

function compareGsm(a, b, direction) {
    const gA = parseFloat(a.gsm || 0);
    const gB = parseFloat(b.gsm || 0);
    return direction === 'asc' ? gA - gB : gB - gA;
}

function getSortLabel(unit) {
    const config = getUnitSortConfig(unit);
    const p = config.priority === 'color' ? 'Color' : (config.priority === 'gsm' ? 'GSM' : 'Quality');
    const d = config.priority === 'color' ? config.color : (config.priority === 'gsm' ? config.gsm : 'ASC');
    return `${p} (${d.toUpperCase()})`; 
}

function sortItems(unit, items) {
  // 1. If we have a saved sequence (Manual Sort / Approved Sequence) for this unit/date, use it primarily
  const savedSeq = unitSequenceStore.value[unit];
  if (savedSeq && savedSeq.length) {
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

function getUnitSortConfig(unit) {
  if (!unitSortConfig.value[unit]) {
    unitSortConfig.value[unit] = { color: 'asc', gsm: 'desc', priority: 'color' };
  }
  return unitSortConfig.value[unit];
}

function toggleUnitColor(unit) {
  const config = getUnitSortConfig(unit);
  if (config.priority !== 'color') { config.priority = 'color'; config.color = 'asc'; } 
  else { config.color = config.color === 'asc' ? 'desc' : 'asc'; }
}

function toggleUnitGsm(unit) {
  const config = getUnitSortConfig(unit);
  if (config.priority !== 'gsm') { config.priority = 'gsm'; config.gsm = 'asc'; } 
  else { config.gsm = config.gsm === 'asc' ? 'desc' : 'asc'; }
}

function toggleUnitPriority(unit) {
  const config = getUnitSortConfig(unit);
  config.priority = config.priority === 'color' ? 'gsm' : 'color';
}

function getUnitEntries(unit) {
  let unitItems = filteredData.value.filter((d) => d.unit === unit);
  unitItems = sortItems(unit, unitItems);

  const entries = [];
  for (let i = 0; i < unitItems.length; i++) {
    entries.push({ type: "order", ...unitItems[i], uniqueKey: unitItems[i].itemName });
    if (i < unitItems.length - 1) {
      const curPri = getColorPriority(unitItems[i].color);
      const nextPri = getColorPriority(unitItems[i + 1].color);
      const gap = Math.abs(curPri - nextPri);
      
      if (gap > 0 || (unitItems[i].color !== unitItems[i+1].color)) {
         let mType = determineMixType(unitItems[i].color, unitItems[i + 1].color);
         if (gap > 0) {
            entries.push({
              type: "mix",
              mixType: mType,
              qty: getMixRollQty(gap),
              uniqueKey: `mix-${unitItems[i].itemName}-${unitItems[i + 1].itemName}`
            });
         }
      }
    }
  }
  return entries;
}

function getUnitTotal(unit) {
  return filteredData.value.filter((d) => d.unit === unit).reduce((sum, d) => sum + d.qty, 0) / 1000;
}

function getUnitProductionTotal(unit) {
  const production = filteredData.value.filter((d) => d.unit === unit).reduce((sum, d) => sum + d.qty, 0);
  const mixWeight = getMixRollTotalWeight(unit);
  return (production + mixWeight) / 1000;
}

function getMixRollCount(unit) {
  return getUnitEntries(unit).filter((e) => e.type === "mix").length;
}

function getMixRollTotalWeight(unit) {
  return getUnitEntries(unit).filter((e) => e.type === "mix").reduce((sum, e) => sum + e.qty, 0);
}

function getUnitCapacityStatus(unit) {
    const total = getUnitTotal(unit);
    const limit = UNIT_TONNAGE_LIMITS[unit] || 999;
    return total > limit ? { class: 'text-red-600 font-bold', warning: `⚠️ Over Limit (${limit}T)` } : {};
}

function openForm(name) {
  frappe.set_route("Form", "Planning sheet", name);
}

async function fetchData() {
  try {
    let args = {
        party_code: filterPartyCode.value || null,
        delivery_date: filterDeliveryDate.value || null
    };
    
    if (viewScope.value === 'monthly') {
        if (!filterMonth.value) return;
        const startDate = `${filterMonth.value}-01`;
        const [year, month] = filterMonth.value.split("-");
        const lastDay = new Date(year, month, 0).getDate();
        const endDate = `${filterMonth.value}-${lastDay}`;
        args.start_date = startDate;
        args.end_date = endDate;
    } else if (viewScope.value === 'weekly') {
        if (!filterWeek.value) return;
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
        args.order_date = filterOrderDate.value || null;
    }

    const r = await frappe.call({
      method: "production_scheduler.api.get_confirmed_orders_kanban", 
      args: args,
    });
    rawData.value = r.message || [];

    // Fetch sequences to match Board order
    const statusDate = args.date || args.start_date || args.order_date;
    if (statusDate) {
        for (const unit of units) {
            try {
                const seqRes = await frappe.call({
                    method: "production_scheduler.api.get_color_sequence",
                    args: { date: statusDate, unit: unit, plan_name: "__all__" }
                });
                if (seqRes.message && seqRes.message.sequence) {
                    unitSequenceStore.value[unit] = seqRes.message.sequence;
                } else {
                    unitSequenceStore.value[unit] = null;
                }
            } catch (e) {
                console.warn(`Failed to fetch sequence for ${unit}`, e);
            }
        }
    }
    renderKey.value++; 
  } catch (e) {
    frappe.msgprint("Error loading confirmed orders");
    console.error(e);
  }
}

// REMOVE SORTABLE LOGIC - Confirmed Order is Read-Only Visualization
/*
function initSortable() {
  if (!columnRefs.value) return;

  const cols = Array.isArray(columnRefs.value) ? columnRefs.value : [columnRefs.value];

  cols.forEach((col) => {
    new Sortable(col, {
      group: "kanban", 
      animation: 150,
      draggable: ".cc-card",
      onEnd: async (evt) => {
          // Logic Removed
      },
    });
  });
} 
*/

/* Function Removed as per User Request (Read Only Mode) */

onMounted(() => {
  console.log("ConfirmedOrder Vue Component Mounted");
  fetchData(); // Fetch all initially
});
</script>

<style scoped>
/* Reuse Color Chart Styles directly */
.cc-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #f3f4f6;
  font-family: 'Inter', sans-serif;
}
.cc-filters {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background-color: white;
  border-bottom: 1px solid #e5e7eb;
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
  outline: none;
}
.cc-clear-btn {
  margin-top: 14px;
  padding: 6px 12px;
  background-color: white;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  color: #374151;
}
.cc-clear-btn:hover { background-color: #f9fafb; }
.cc-board {
  flex: 1;
  display: flex;
  overflow-x: auto;
  padding: 16px;
  gap: 16px;
}

/* Columns */
.cc-column {
  flex: 0 0 280px;
  display: flex;
  flex-direction: column;
  background-color: white; /* Clean white column */
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  max-height: 100%;
}
.cc-col-header {
  padding: 12px;
  border-bottom: 1px solid #f3f4f6;
  background-color: #ffffff;
  border-top-width: 4px; /* Colored unit indicator */
  border-top-style: solid;
  border-radius: 6px 6px 0 0;
}
.cc-header-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.cc-col-title { font-weight: 700; font-size: 15px; color: #111827; }
.cc-unit-controls { display: flex; gap: 2px; align-items: center; }
.cc-mini-btn { font-size: 12px; background: none; border: none; cursor: pointer; padding: 2px; opacity: 0.7; }
.cc-mini-btn:hover { opacity: 1; background-color: #f3f4f6; border-radius: 4px; }
.cc-stat-weight { font-size: 13px; font-weight: 600; color: #4b5563; display: block; }
.cc-stat-mix { font-size: 11px; color: #f59e0b; display: block; margin-top: 2px; }

.cc-col-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  background-color: #f9fafb; /* Light gray info background inside column */
}
.cc-empty { 
    text-align: center; color: #9ca3af; font-size: 13px; margin-top: 20px; font-style: italic; 
}
.cc-col-footer {
  padding: 8px 12px;
  background-color: #ffffff;
  border-top: 1px solid #e5e7eb;
  font-size: 12px;
  color: #6b7280;
  display: flex;
  justify-content: space-between;
  border-radius: 0 0 6px 6px;
}

/* Cards */
.cc-card {
  background-color: white;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
  display: flex;
  cursor: grab;
  box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  transition: transform 0.1s, box-shadow 0.1s;
}
.cc-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 6px rgba(0,0,0,0.05);
  border-color: #d1d5db;
}
.cc-card:active { cursor: grabbing; }

.cc-card-left { display: flex; flex: 1; overflow: hidden; }
.cc-color-swatch {
  width: 12px;
  height: 40px;
  border-radius: 3px;
  margin-right: 8px;
  flex-shrink: 0;
  border: 1px solid rgba(0,0,0,0.1);
}
.cc-card-info { display: flex; flex-direction: column; overflow: hidden; justify-content: center; }
.cc-card-color-name { font-size: 13px; font-weight: 700; color: #1f2937; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cc-card-customer { font-size: 11px; color: #6b7280; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cc-card-details { font-size: 11px; color: #4b5563; margin-top: 2px; }

.cc-card-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  margin-left: 8px;
}
.cc-card-qty { font-size: 13px; font-weight: 700; color: #111827; }
.cc-card-qty-kg { font-size: 10px; color: #9ca3af; }

/* Mix Markers */
.cc-mix-marker { display: flex; align-items: center; margin: 8px 0; gap: 8px; opacity: 0.9; }
.cc-mix-line { flex: 1; height: 1px; background-color: #d1d5db; }
.cc-mix-label { font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 10px; background-color: #e5e7eb; color: #4b5563; white-space: nowrap; }
.cc-mix-label.white-mix { background-color: #f3f4f6; color: #000; border: 1px solid #d1d5db; }
.cc-mix-label.black-mix { background-color: #374151; color: #fff; }
.cc-mix-label.color-mix { background-color: #dbeafe; color: #1e40af; }

/* ---- TABLE VIEW STYLES ---- */
.cc-view-toggle {
    display: flex;
    gap: 4px;
    margin-left: auto; 
    background: #e5e7eb;
    padding: 2px;
    border-radius: 6px;
}
.cc-view-btn {
    border: none;
    background: transparent;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 600;
    color: #6b7280;
    cursor: pointer;
    border-radius: 4px;
}
.cc-view-btn.active {
    background: white;
    color: #1f2937;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
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
</style>
