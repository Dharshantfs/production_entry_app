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
  const dieHint = nextThresholdHint(unitStats.unit, "die", tons, thresholds);
  return `MTD Target: ${formatTons(tons)} t` + (meshHint ? ` (${meshHint})` : "");
}
