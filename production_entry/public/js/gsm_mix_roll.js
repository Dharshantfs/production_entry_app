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
