/** Mesh / die tonnage thresholds (tons) for Production Table units 1–4. */

export const UNIT_MAINTENANCE_THRESHOLDS = {
  "Unit 1": { mesh: 30, die: 90 },
  "Unit 2": { mesh: 70, die: 210 },
  "Unit 3": { mesh: 75, die: 150 },
  "Unit 4": { mesh: 40, die: 120 },
};

export const PRODUCTION_TABLE_REMINDER_UNITS = ["Unit 1", "Unit 2", "Unit 3", "Unit 4"];

export function formatTons(value) {
  const n = parseFloat(value);
  if (!Number.isFinite(n)) return "0.00";
  return n.toFixed(2);
}

export function formatKg(value) {
  const n = parseFloat(value);
  if (!Number.isFinite(n)) return "0.00";
  return n.toFixed(2);
}

/** Same row eligibility rules as ProductionTable filteredData (for MTD target sum). */
export function filterProductionTableReminderRows(data, opts = {}) {
  const {
    partyCode = "",
    customer = "",
    allowedUnits = null,
    unitAllowedFn = null,
  } = opts;

  let rows = (data || []).filter((d) => !!(d.plannedDate || d.planned_date));

  rows = rows.filter((d) => {
    const ic = String(d.itemCode || d.item_code || "").trim();
    const isFabricChild = ic.startsWith("100");
    if (!d.unit || d.unit === "Mixed" || d.unit === "Unassigned") return false;
    if (!isFabricChild && (!d.quality || !d.color)) return false;
    const colorUpper = String(d.color || "")
      .toUpperCase()
      .trim();
    if (colorUpper === "NO COLOR") return false;
    return true;
  });

  if (partyCode) {
    const search = String(partyCode).toLowerCase();
    rows = rows.filter((d) => (d.partyCode || d.party_code || "").toLowerCase().includes(search));
  }
  if (customer) {
    const search = String(customer).toLowerCase();
    rows = rows.filter((d) =>
      String(d.customer_name || d.party_name || d.customer || d.partyCode || d.party_code || "")
        .toLowerCase()
        .includes(search)
    );
  }
  if (allowedUnits && allowedUnits.length && typeof unitAllowedFn === "function") {
    rows = rows.filter((d) => unitAllowedFn(d.unit, allowedUnits));
  }

  return rows;
}

/** Sum qty (TOTAL TARGET Kgs) per unit for rows in calendar month YYYY-MM. */
export function computeMtdTargetKgByUnit(rows, month, normalizeUnitFn) {
  const totals = {};
  PRODUCTION_TABLE_REMINDER_UNITS.forEach((u) => {
    totals[u] = { kg: 0, tons: 0 };
  });
  const monthKey = String(month || "").slice(0, 7);
  if (!monthKey || monthKey.length < 7) return totals;

  (rows || []).forEach((row) => {
    const planned = String(row.plannedDate || row.planned_date || "").slice(0, 10);
    if (!planned.startsWith(monthKey)) return;
    const unit = normalizeUnitFn(row.unit || "");
    if (!PRODUCTION_TABLE_REMINDER_UNITS.includes(unit)) return;
    const kg = parseFloat(row.qty) || 0;
    if (kg <= 0) return;
    totals[unit].kg += kg;
  });

  PRODUCTION_TABLE_REMINDER_UNITS.forEach((u) => {
    totals[u].tons = totals[u].kg / 1000;
  });
  return totals;
}

export function countMaintenanceLoggedInMonth(records, month, unit, reminderType, normalizeUnitFn) {
  const monthKey = String(month || "").slice(0, 7);
  const want = String(reminderType || "").trim();
  return (records || []).filter((rec) => {
    if (normalizeUnitFn(rec.unit) !== unit) return false;
    if (String(rec.maintenance_type || "").trim() !== want) return false;
    const sd = String(rec.start_date || "").slice(0, 7);
    return sd === monthKey;
  }).length;
}

export function buildMaintenanceReminders(unitStats, month, maintenanceRecords, thresholds, normalizeUnitFn) {
  const reminders = [];
  const monthKey = String(month || "").slice(0, 7);

  PRODUCTION_TABLE_REMINDER_UNITS.forEach((unit) => {
    const cfg = thresholds[unit] || {};
    const currentTons = parseFloat((unitStats[unit] && unitStats[unit].tons) || 0) || 0;
    const currentKg = parseFloat((unitStats[unit] && unitStats[unit].kg) || 0) || 0;

    [
      { key: "mesh", type: "Mesh Change", interval: cfg.mesh },
      { key: "die", type: "Die Change", interval: cfg.die },
    ].forEach(({ type, interval }) => {
      if (!interval || interval <= 0) return;
      const required = Math.floor(currentTons / interval);
      const logged = countMaintenanceLoggedInMonth(
        maintenanceRecords,
        monthKey,
        unit,
        type,
        normalizeUnitFn
      );
      const pending = Math.max(0, required - logged);
      if (pending <= 0) return;
      const level = logged + 1;
      reminders.push({
        unit,
        reminder_type: type,
        level,
        interval_tons: interval,
        threshold_tons: level * interval,
        current_tons: currentTons,
        current_kg: currentKg,
        pending_levels: pending,
        overdue: false,
      });
    });
  });

  reminders.sort((a, b) => {
    const ui = PRODUCTION_TABLE_REMINDER_UNITS.indexOf(a.unit) - PRODUCTION_TABLE_REMINDER_UNITS.indexOf(b.unit);
    if (ui !== 0) return ui;
    const ti = a.reminder_type === "Mesh Change" ? 0 : 1;
    const tj = b.reminder_type === "Mesh Change" ? 0 : 1;
    if (ti !== tj) return ti - tj;
    return (a.level || 0) - (b.level || 0);
  });
  return reminders;
}

export function buildReminderDialogBody(reminder, overdue) {
  const unit = reminder.unit || "";
  const type = reminder.reminder_type || "";
  const current = formatTons(reminder.current_tons);
  const currentKg = formatKg(reminder.current_kg != null ? reminder.current_kg : (reminder.current_tons || 0) * 1000);
  const threshold = formatTons(reminder.threshold_tons);
  const interval = formatTons(reminder.interval_tons);
  const prefix = overdue ? "<b>Reminder (overdue):</b>" : "<b>Maintenance required:</b>";
  return (
    `${prefix}<br><br>` +
    `<b>${unit}</b> month-to-date total target: <b>${current} tons</b> (${currentKg} kg).<br>` +
    `${type} is due at the <b>${threshold} ton</b> threshold ` +
    `(interval: every ${interval} tons this month).<br><br>` +
    `Please log ${type} via the Maintenance button.`
  );
}

export function nextThresholdHint(unit, type, currentTons, thresholds) {
  const cfg = thresholds[unit];
  if (!cfg) return "";
  const interval = type === "mesh" ? cfg.mesh : cfg.die;
  if (!interval || interval <= 0) return "";
  const tons = parseFloat(currentTons) || 0;
  const nextLevel = Math.floor(tons / interval) + 1;
  const nextAt = nextLevel * interval;
  const label = type === "mesh" ? "mesh" : "die";
  return `next ${label} @ ${formatTons(nextAt)} t`;
}

export function buildMtdHeaderLabel(unitStats, thresholds) {
  if (!unitStats) return "";
  const tons = parseFloat(unitStats.tons) || 0;
  const meshHint = nextThresholdHint(unitStats.unit, "mesh", tons, thresholds);
  return `MTD Target: ${formatTons(tons)} t` + (meshHint ? ` (${meshHint})` : "");
}
