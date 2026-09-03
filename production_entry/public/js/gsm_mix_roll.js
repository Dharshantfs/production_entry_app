/** GSM Mix Roll — operator select from Color Chart store, produce on shift SPR. */

import {
  sprCalcCbmFromDiameter,
  sprCalcNetFromGross,
  sprCalcProducedGsm,
  sprFlt,
  sprNormalizeGrossWeightInput,
  sprWholeMtrs,
  sprRecalcRollRow,
} from "./spr_roll_entry_utils.js";

export async function fetchGsmMixRollCandidates(unit, includeSubmitted = 0, browse = {}) {
  const args = {
    unit,
    include_submitted: includeSubmitted ? 1 : 0,
  };
  if (browse.plannedDate) {
    args.planned_date = browse.plannedDate;
  }
  if (browse.viewScope) {
    args.view_scope = browse.viewScope;
  }
  if (browse.filterWeek) {
    args.filter_week = browse.filterWeek;
  }
  if (browse.filterMonth) {
    args.filter_month = browse.filterMonth;
  }
  if (browse.runDate) {
    args.run_date = browse.runDate;
  }
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.get_gsm_mix_rolls_for_unit",
    args,
  });
  return res.message || { mix_rolls: [], unit };
}

export async function activateGsmMixRollForSession({
  dateKey,
  mixId,
  mixRowKey,
  runDate,
  shift,
  unit,
}) {
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.activate_gsm_mix_roll_for_session",
    args: {
      date_key: dateKey,
      mix_id: mixId || undefined,
      mix_row_key: mixRowKey || undefined,
      run_date: runDate,
      shift,
      unit,
    },
  });
  return res.message || {};
}

export async function loadGsmMixRollSprRolls(sprName) {
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.get_gsm_mix_roll_spr_rolls",
    args: { spr_name: sprName },
  });
  return res.message || {};
}

export async function addGsmMixRollLine({ sprName, itemCode, widthInch, batchNo, gsm }) {
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.add_gsm_mix_roll_line",
    args: {
      spr_name: sprName,
      item_code: itemCode || undefined,
      width_inch: widthInch || undefined,
      batch_no: batchNo || undefined,
      gsm: gsm || undefined,
    },
  });
  return res.message || {};
}

export async function saveGsmMixRollLine({ sprName, shift, rollPayload }) {
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.save_gsm_roll_line",
    args: {
      spr_name: sprName,
      shift,
      roll_payload: JSON.stringify(rollPayload),
    },
  });
  return res.message || {};
}

export async function submitGsmMixRollSpr(sprName) {
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.submit_gsm_mix_roll_spr",
    args: { spr_name: sprName },
  });
  return res.message || {};
}

export function mixRollItemOptions(mixRow) {
  const codes = String(mixRow?.item_code || "")
    .split(",")
    .map((c) => c.trim())
    .filter(Boolean);
  const names = String(mixRow?.item_name || "")
    .split("|")
    .map((n) => n.trim());
  return codes.map((code, i) => ({
    item_code: code,
    item_name: names[i] || code,
  }));
}

export function mixRollWidthOptions(mixRow) {
  const shaft = String(mixRow?.shaft || mixRow?.combination || "");
  const widths = shaft.match(/\d+(?:\.\d+)?/g) || [];
  return widths.map((w) => sprFlt(w)).filter((w) => w > 0);
}

function _mixWidthClose(a, b) {
  return Math.abs(sprFlt(a) - sprFlt(b)) < 0.15;
}

function _itemCodeWidthInch(itemCode) {
  const code = String(itemCode || "").trim();
  if (code.length < 4) {
    return 0;
  }
  const mm = sprFlt(code.slice(-4));
  return mm > 0 ? mm / 25.4 : 0;
}

/**
 * Next combination segment for Mix Roll "Add Roll Row".
 * Combination 46+42+38 → first row 46", second 42", third 38", fourth 46" again.
 * Picks the leftmost width that currently has the fewest rows (so a deleted 46" is filled before a second 42").
 */
export function nextMixRollCombinationSlot(mixRow, existingRows = []) {
  const widths = mixRollWidthOptions(mixRow);
  const items = mixRollItemOptions(mixRow);
  const fallbackItem = items[0] || {};
  if (!widths.length) {
    return {
      index: 0,
      widthInch: sprFlt(fallbackItem.width_inch) || 0,
      itemCode: fallbackItem.item_code || "",
      itemName: fallbackItem.item_name || "",
    };
  }

  const counts = widths.map(() => 0);
  for (const row of existingRows || []) {
    const w = sprFlt(row.width_inch);
    if (w <= 0) {
      continue;
    }
    let best = -1;
    let bestDiff = 0.15;
    for (let i = 0; i < widths.length; i++) {
      const d = Math.abs(widths[i] - w);
      if (d <= bestDiff) {
        best = i;
        bestDiff = d;
      }
    }
    if (best >= 0) {
      counts[best] += 1;
    }
  }

  const min = Math.min(...counts);
  const index = counts.findIndex((c) => c === min);
  const widthInch = widths[index];
  let item = items[index];
  if (!item && items.length) {
    item =
      items.find((it) => _mixWidthClose(_itemCodeWidthInch(it.item_code), widthInch)) ||
      items[0];
  }
  return {
    index,
    widthInch,
    itemCode: item?.item_code || fallbackItem.item_code || "",
    itemName: item?.item_name || fallbackItem.item_name || "",
  };
}

export function mixRollShaftCount(mixRow) {
  const n = Number(mixRow?.no_of_shaft || mixRow?.no_of_shafts || 1);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 1;
}

export function mixRollMaxRows(mixRow) {
  const segs = Math.max(1, mixRollWidthOptions(mixRow).length);
  return mixRollShaftCount(mixRow) * segs;
}

export function mixGridRowsForSpr(rows, sprName) {
  const spr = String(sprName || "").trim();
  return (rows || []).filter(
    (r) =>
      r &&
      r.is_mix_roll_row &&
      !r.is_wasted &&
      (!spr || String(r.spr_name || "").trim() === spr) &&
      (r.batch_no || r.spr_item_name)
  );
}

export function mixProducedRollCount(mixRow, gridRows) {
  const fromGrid = mixGridRowsForSpr(gridRows, mixRow?.spr_name).length;
  if (fromGrid > 0) {
    return fromGrid;
  }
  return Number(mixRow?.spr_roll_count || 0) || 0;
}

export function mixProducedShaftCount(mixRow, gridRows) {
  const rows = mixGridRowsForSpr(gridRows, mixRow?.spr_name);
  const shafts = new Set();
  for (const r of rows) {
    const n = Number(r.custom_no_of_shaft || 0);
    if (Number.isFinite(n) && n > 0) {
      shafts.add(Math.floor(n));
    }
  }
  if (shafts.size) {
    return Math.min(mixRollShaftCount(mixRow), shafts.size);
  }
  const segs = Math.max(1, mixRollWidthOptions(mixRow).length);
  const rolls = mixProducedRollCount(mixRow, gridRows);
  if (rolls <= 0) {
    return 0;
  }
  return Math.min(mixRollShaftCount(mixRow), Math.ceil(rolls / segs));
}

export function normalizeSpiDiameterCbm(line = {}) {
  const dia = sprFlt(line.custom_diameter_inches ?? line.custom_diameter ?? line.diameter);
  const cbm = sprFlt(line.custom_cbm_cubic_meters ?? line.custom_cbm ?? line.cbm);
  return {
    custom_diameter_inches: dia > 0 ? dia : "",
    custom_cbm_cubic_meters: cbm > 0 ? cbm : "",
    custom_diameter: dia > 0 ? dia : "",
    custom_cbm: cbm > 0 ? cbm : "",
  };
}

export function mapMixRollLineFromServer(line, mixMeta = {}) {
  const hasSavedProduction =
    sprFlt(line.produced_length_mtrs) > 0 &&
    sprNormalizeGrossWeightInput(line.gross_weight) > 0;
  return {
    _id: `mix-${line.spr_item_name || line.batch_no || Date.now()}`,
    is_mix_roll_row: 1,
    custom_unit: line.custom_unit || mixMeta.custom_unit || mixMeta.unit || "",
    spr_name: line.spr_name || mixMeta.spr_name || "",
    spr_item_name: line.spr_item_name || line.name || "",
    party_code: line.party_code || mixMeta.label || "",
    item_code: line.item_code || "",
    item_name: line.item_name || "",
    quality: line.quality || mixMeta.quality || "",
    color: line.color || mixMeta.clType || mixMeta.cl_type || mixMeta.color_transition || "",
    gsm: line.gsm || mixMeta.gsm || 0,
    width_inch: line.width_inch || 0,
    batch_no: line.batch_no || "",
    roll_no: line.roll_no || "",
    meter_roll: 0,
    produced_length_mtrs: sprWholeMtrs(line.produced_length_mtrs),
    produced_gsm: line.produced_gsm || 0,
    net_weight: line.net_weight || 0,
    gross_weight: line.gross_weight != null ? String(line.gross_weight) : "",
    planned_qty: line.planned_qty || 0,
    custom_core_width_mm: line.custom_core_width_mm || "",
    custom_polybag_kgs: line.custom_polybag_kgs || 0,
    ...normalizeSpiDiameterCbm(line),
    // An empty row may already exist on an older draft SPR. It must remain
    // editable; server serializers mark persisted rows locked by default.
    row_locked: hasSavedProduction && !!line.row_locked,
    row_ready_for_print: hasSavedProduction && !!line.row_ready_for_print,
    job_id: line.job_id || line.job || "1",
  };
}

export function buildMixRollSavePayload(row) {
  const gross = sprNormalizeGrossWeightInput(row.gross_weight);
  const updated = sprRecalcRollRow({ ...row, gross_weight: String(gross), meter_roll: 0 });
  const cbm = sprCalcCbmFromDiameter(row.width_inch, row.custom_diameter_inches);
  const dia = sprFlt(row.custom_diameter_inches);
  return {
    job_id: row.job_id || "1",
    item_code: row.item_code,
    item_name: row.item_name,
    quality: row.quality,
    color: row.color,
    gsm: row.gsm,
    width_inch: row.width_inch,
    batch_no: row.batch_no,
    roll_no: row.roll_no,
    meter_roll: 0,
    produced_length_mtrs: sprWholeMtrs(row.produced_length_mtrs) || 0,
    produced_gsm: updated.produced_gsm,
    net_weight: updated.net_weight,
    gross_weight: gross,
    planned_qty: 0,
    custom_core_width_mm: row.custom_core_width_mm,
    custom_polybag_kgs: row.custom_polybag_kgs,
    custom_diameter_inches: dia,
    custom_diameter: dia,
    custom_cbm_cubic_meters: cbm || sprFlt(row.custom_cbm_cubic_meters),
    custom_cbm: cbm || sprFlt(row.custom_cbm_cubic_meters),
    party_code: row.party_code,
    row_locked: 1,
    row_ready_for_print: 1,
    is_mix_roll_row: 1,
  };
}

export function recalcMixRollRow(row) {
  const gross = sprNormalizeGrossWeightInput(row.gross_weight);
  const updated = sprRecalcRollRow({ ...row, gross_weight: String(gross), meter_roll: 0 });
  row.net_weight = updated.net_weight;
  row.produced_gsm = updated.produced_gsm;
  row.planned_qty = 0;
  row.custom_cbm_cubic_meters = sprCalcCbmFromDiameter(row.width_inch, row.custom_diameter_inches);
  return row;
}

/** Color Chart mix-roll colour groups — used for GSM Add Mix Roll dropdowns / badges. */
export const MIX_COLOR_GROUPS = [
  { keywords: ["BRIGHT WHITE", "SUNSHINE WHITE", "MILKY WHITE", "SUPER WHITE", "BLEACH WHITE", "OPTICAL WHITE", "WHITE"], priority: 0, hex: "#FFFFFF" },
  { keywords: ["BABY PINK"], priority: 1, hex: "#FFB6C1" },
  { keywords: ["MEDICAL BLUE"], priority: 2, hex: "#0096FF" },
  { keywords: ["MEDICAL GREEN"], priority: 3, hex: "#00A36C" },
  { keywords: ["BRIGHT IVORY", "IVORY", "OFF WHITE", "CREAM"], priority: 4, hex: "#FFFFF0" },
  { keywords: ["LEMON YELLOW"], priority: 5, hex: "#FFF44F" },
  { keywords: ["YELLOW"], priority: 5, hex: "#FFEA00" },
  { keywords: ["GOLDEN YELLOW", "GOLD"], priority: 6, hex: "#FFD700" },
  { keywords: ["LIGHT ORANGE", "PEACH", "BRIGHT ORANGE", "ORANGE"], priority: 7, hex: "#FF8C00" },
  { keywords: ["DARK PINK"], priority: 8, hex: "#C71585" },
  { keywords: ["PINK", "PINK 1.0", "PINK 2.0", "PINK 3.0", "PINK 5.0", "HOT PINK"], priority: 8, hex: "#FFC0CB" },
  { keywords: ["BRIGHT RED", "SCARLET", "CRIMSON", "RED"], priority: 9, hex: "#D32F2F" },
  { keywords: ["MAROON", "BURGUNDY", "DARK RED"], priority: 9, hex: "#800000" },
  { keywords: ["LIGHT PEACOCK BLUE", "PEACOCK BLUE"], priority: 10, hex: "#008B8B" },
  { keywords: ["SKY BLUE", "LIGHT BLUE"], priority: 11, hex: "#87CEEB" },
  { keywords: ["ROYAL BLUE", "BLUE"], priority: 11, hex: "#2962FF" },
  { keywords: ["NAVY BLUE", "DARK BLUE"], priority: 12, hex: "#1A237E" },
  { keywords: ["VIOLET", "VOILET", "PURPLE"], priority: 13, hex: "#8B00FF" },
  { keywords: ["GREEN 1.0 MINT"], priority: 14, hex: "#00897B" },
  { keywords: ["PARROT GREEN", "RELIANCE GREEN", "GREEN"], priority: 15, hex: "#228B22" },
  { keywords: ["SEA GREEN"], priority: 16, hex: "#2E8B57" },
  { keywords: ["ARMY GREEN", "ARMY"], priority: 17, hex: "#4B5320" },
  { keywords: ["SILVER", "LIGHT GREY", "GREY", "GRAY", "DARK GREY"], priority: 18, hex: "#808080" },
  { keywords: ["BROWN", "CHOCOLATE"], priority: 19, hex: "#8B4513" },
  { keywords: ["BLACK"], priority: 20, hex: "#000000" },
  { keywords: ["DARK BEIGE"], priority: 21, hex: "#C2B280" },
  { keywords: ["LIGHT BEIGE", "BEIGE"], priority: 22, hex: "#F5F5DC" },
];

export const MIX_QUALITY_OPTIONS = ["Virgin Mix", "Eco Mix", "Deluxe Mix"];
export const MIX_CL_TYPE_OPTIONS = ["Color Mix", "Beige Mix", "White Mix", "Black Mix"];

export const MIX_COLOR_OPTIONS = Array.from(
  new Set(MIX_COLOR_GROUPS.flatMap((g) => g.keywords || []))
);

export function mixColorGroup(color) {
  const upper = String(color || "").toUpperCase().trim();
  if (!upper) {
    return null;
  }
  for (const group of MIX_COLOR_GROUPS) {
    for (const keyword of group.keywords || []) {
      if (upper.includes(keyword)) {
        return group;
      }
    }
  }
  return null;
}

export function mixColorBadgeStyle(colorName) {
  const group = mixColorGroup(colorName);
  const hex = group?.hex || "#e5e7eb";
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return {
    backgroundColor: hex,
    color: luminance > 0.55 ? "#1a1a1a" : "#ffffff",
  };
}

export function suggestMixClType(color1, color2) {
  const p1 = mixColorGroup(color1)?.priority ?? 50;
  const p2 = mixColorGroup(color2)?.priority ?? 50;
  const u1 = String(color1 || "").toUpperCase();
  const u2 = String(color2 || "").toUpperCase();
  if (p1 <= 6 && p2 <= 6) {
    return "White Mix";
  }
  if (u1.includes("BLACK") && u2.includes("BLACK")) {
    return "Black Mix";
  }
  if (u1.includes("BEIGE") || u2.includes("BEIGE")) {
    return "Beige Mix";
  }
  if (p1 === 90 && p2 === 90) {
    return "Black Mix";
  }
  if ((p1 >= 95 && p1 <= 96) || (p2 >= 95 && p2 <= 96)) {
    return "Beige Mix";
  }
  return "Color Mix";
}

export function mixShaftHint(unit, maxInches) {
  const maxIn = Number(maxInches) || 0;
  if (maxIn) {
    return `Max ${maxIn}" total`;
  }
  const fallback = { "Unit 1": 63, "Unit 2": 126, "Unit 3": 126, "Unit 4": 90 };
  const n = fallback[String(unit || "").trim()] || 0;
  return n ? `Max ${n}" total` : "";
}

export async function fetchGsmMixRollFormOptions(unit, browse = {}) {
  const args = { unit };
  if (browse.plannedDate) args.planned_date = browse.plannedDate;
  if (browse.viewScope) args.view_scope = browse.viewScope;
  if (browse.filterWeek) args.filter_week = browse.filterWeek;
  if (browse.filterMonth) args.filter_month = browse.filterMonth;
  if (browse.runDate) args.run_date = browse.runDate;
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.get_gsm_mix_roll_form_options",
    args,
  });
  return res.message || {};
}

export async function upsertGsmMixRollFromEntry(payload) {
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.upsert_gsm_mix_roll_from_entry",
    args: payload,
  });
  return res.message || {};
}
