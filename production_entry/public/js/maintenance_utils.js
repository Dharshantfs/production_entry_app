/** Shared maintenance helpers for production boards and order tables. */

export function normalizeMaintenanceUnit(raw) {
  const s = String(raw || "").trim();
  if (!s) return "";
  const u = s.toUpperCase().replace(/\s+/g, "").replace(/_/g, "");

  if (u.includes("UNIT1") || s === "Unit 1" || s === "UNIT 1") return "Unit 1";
  if (u.includes("UNIT2") || s === "Unit 2" || s === "UNIT 2") return "Unit 2";
  if (u.includes("UNIT3") || s === "Unit 3" || s === "UNIT 3") return "Unit 3";
  if (u.includes("UNIT4") || s === "Unit 4" || s === "UNIT 4") return "Unit 4";

  if (u.includes("TNSPL") && u.includes("LAMINATION")) return "TNSPL - LAMINATION UNIT";
  if (u === "LAMINATIONUNIT" || s.toLowerCase() === "lamination unit") return "TNSPL - LAMINATION UNIT";

  if (u.includes("UNASSIGNED") && u.includes("SLITTING")) return "UNASSIGNED SLITTING MACHINE";
  if (u.includes("VTP") && u.includes("SLITTING")) return "VTP - SLITTING MACHINE";
  if (u.includes("JVESLITTINGMACHINE") || (u.includes("JVE") && u.includes("SLITTING"))) return "JVE - SLITTING MACHINE";
  if (u === "SLITTINGUNIT" || s.toLowerCase() === "slitting unit") return "JVE - SLITTING MACHINE";

  if (u.includes("JVESHEETCUTTING") || (u.includes("SHEET") && u.includes("CUTTING") && u.includes("JVE"))) {
    return "JVE - SHEET CUTTING MACHINE";
  }

  if (u.includes("VTP") && u.includes("L2") && (u.includes("LEADER") || u.includes("ZX"))) {
    return "VTP-L2 LEADER ZX MACHINE";
  }
  if (u.includes("VTP") && u.includes("L1") && (u.includes("LEADER") || u.includes("OYANG"))) {
    return "VTP-L1 LEADER OYANG MACHINE";
  }
  if (u.includes("VTP") && u.includes("L4") && u.includes("SCREEN")) {
    return "VTP-L4 SCREEN PRINTING MACHINE";
  }
  if (u.includes("BOXBAG") && u.includes("UNASSIGNED")) return "UNASSIGNED BOX BAG MACHINE";

  if (u.includes("TSNPL") && u.includes("L3") && u.includes("REWINDING")) return "TSNPL - L3 REWINDING MACHINE";
  if (u.includes("JSB") && u.includes("L4") && u.includes("REWINDING")) return "JSB - L4 REWINDING MACHINE";
  if (u.includes("JSB") && u.includes("L5") && u.includes("REWINDING")) return "JSB - L5 REWINDING MACHINE";
  if (u.includes("UNASSIGNED") && u.includes("REWINDING")) return "UNASSIGNED REWINDING UNIT";

  if (u.includes("PRINTINGMACHINE2COLOUR") || (u.includes("PRINTING") && u.includes("2COLOUR") && u.includes("1600"))) {
    return "JVE - PRINTING MACHINE 2 COLOUR 1600MM";
  }
  if (u.includes("PRINTINGMACHINE4COLOUR") && u.includes("1600")) {
    return "JVE - PRINTING MACHINE 4 COLOUR 1600MM";
  }
  if (u.includes("TT") && u.includes("PRINTING") && u.includes("1200")) {
    return "TT - PRINTING MACHINE 4 COLOUR 1200MM";
  }
  if (u.includes("UNASSIGNED") && u.includes("PRINTING")) return "UNASSIGNED PRINTING MACHINE";
  if (u.includes("1200MM") && u.includes("BOPP") && u.includes("PRINTING")) {
    return "VR - 1200MM BOPP PRINTING MACHINE";
  }

  if (u.includes("UNASSIGNED") && u.includes("WCUT")) return "UNASSIGNED W CUT BAG MACHINE";
  if (u.includes("UNASSIGNED") && u.includes("DCUT")) return "UNASSIGNED D CUT BAG MACHINE";
  if (u.includes("B700BAGMAKINGMACHINE") && u.includes("JVE") && u.includes("L1")) return "JVE-L1  B700 BAG MAKING MACHINE";
  if (u.includes("B700BAGMAKINGMACHINE") && u.includes("JVE") && u.includes("L2")) return "JVE-L2  B700 BAG MAKING MACHINE";
  if (u.includes("B700BAGMAKINGMACHINE") && u.includes("JVE") && u.includes("L3")) return "JVE-L3  B700 BAG MAKING MACHINE";
  if (u.includes("OYANGC700BAGMAKINGLINE") && u.includes("L1")) return "TTT- L1 - OYANG C700 BAG MAKING LINE";
  if (u.includes("OYANGC700BAGMAKINGLINE") && u.includes("L2")) return "TTT- L2 - OYANG C700 BAG MAKING LINE";
  if (u.includes("OYANGC900BAGMAKINGLINE") && u.includes("L3")) return "TTT- L3 - OYANG C900 BAG MAKING LINE";

  // Fabric pool: Workstation "UNASSIGNED" === Kanban column "Mixed" (UI label Unassigned).
  // Must run after process-specific UNASSIGNED * MACHINE checks above.
  if (u === "UNASSIGNED" || u === "MIXED") return "Mixed";
  const low = s.toLowerCase();
  if (low === "unassigned" || low === "mixed") return "Mixed";

  return s;
}

export function maintenanceUnitsEqual(a, b) {
  return normalizeMaintenanceUnit(a) === normalizeMaintenanceUnit(b);
}

/** True when *boardUnit* is allowed by Production Board Access scope. */
export function unitAllowedByBoardAccess(boardUnit, allowedUnits) {
  if (!allowedUnits || !allowedUnits.length) return true;
  return allowedUnits.some((a) => maintenanceUnitsEqual(a, boardUnit));
}

export function toLocalDateKey(value) {
  if (!value) return "";
  if (typeof value === "string") {
    const m = value.match(/^(\d{4}-\d{2}-\d{2})/);
    if (m) return m[1];
  }
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function expandMaintenanceDateRange(startDate, endDate) {
  const keys = [];
  const start = new Date(startDate);
  const end = new Date(endDate);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return keys;
  const cur = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const endLocal = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  while (cur <= endLocal) {
    keys.push(toLocalDateKey(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return keys;
}

export function buildMaintenanceData(records) {
  const data = {};
  (records || []).forEach((rec) => {
    const boardUnit = normalizeMaintenanceUnit(rec.unit);
    expandMaintenanceDateRange(rec.start_date, rec.end_date).forEach((dateStr) => {
      if (!data[dateStr]) data[dateStr] = {};
      if (!data[dateStr][boardUnit]) data[dateStr][boardUnit] = [];
      data[dateStr][boardUnit].push({
        name: rec.name,
        type: rec.maintenance_type,
        startDate: rec.start_date,
        endDate: rec.end_date,
        status: rec.status,
        unit: rec.unit,
      });
    });
  });
  return data;
}

export function getMaintenanceRecordsForDate(data, date, unit) {
  const dateKey = toLocalDateKey(date);
  const boardUnit = normalizeMaintenanceUnit(unit);
  if (!dateKey || !data?.[dateKey]) return [];
  return data[dateKey][boardUnit] || [];
}

export function getPrimaryMaintenanceRecord(data, date, unit) {
  const records = getMaintenanceRecordsForDate(data, date, unit);
  return records[0] || null;
}

export function filterMaintenanceRecordsForUnit(records, unit) {
  const boardUnit = normalizeMaintenanceUnit(unit);
  if (!boardUnit) return records || [];
  return (records || []).filter((rec) => maintenanceUnitsEqual(rec.unit, boardUnit));
}

export function filterMaintenanceRecordsForScope(records, { unit = "", allowedUnits = [] } = {}) {
  const rows = records || [];
  if (unit) return filterMaintenanceRecordsForUnit(rows, unit);
  if (allowedUnits?.length) {
    return rows.filter((rec) => allowedUnits.some((u) => maintenanceUnitsEqual(rec.unit, u)));
  }
  return rows;
}

export function buildMaintenanceByDateMap(records, { unitKeyFromRecord = normalizeMaintenanceUnit } = {}) {
  const mapped = {};
  (records || []).forEach((rec) => {
    const unitKey = unitKeyFromRecord(rec.unit);
    expandMaintenanceDateRange(rec.start_date, rec.end_date).forEach((key) => {
      if (!mapped[key]) mapped[key] = {};
      mapped[key][unitKey] = rec.maintenance_type || "Machine Off";
    });
  });
  return mapped;
}

export function maintenanceTypeForUnitDate(map, dateValue, unitValue) {
  const k = toLocalDateKey(dateValue);
  const unitKey = normalizeMaintenanceUnit(unitValue);
  if (!k || !unitKey || !map?.[k]) return "";
  return map[k][unitKey] || "";
}
