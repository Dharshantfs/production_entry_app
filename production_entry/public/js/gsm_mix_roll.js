/** GSM Mix Roll — operator select from Color Chart store, produce on shift SPR. */

import {
  sprCalcNetFromGross,
  sprCalcProducedGsm,
  sprFlt,
  sprNormalizeGrossWeightInput,
  sprRecalcRollRow,
} from "./spr_roll_entry_utils.js";

export async function fetchGsmMixRollCandidates(unit, includeSubmitted = 0, runDate = null) {
  const res = await frappe.call({
    method: "production_entry.production_planning.unified_production_entry_api.get_gsm_mix_rolls_for_unit",
    args: { unit, include_submitted: includeSubmitted ? 1 : 0, run_date: runDate || undefined },
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
  const shaft = String(mixRow?.shaft || "");
  const widths = shaft.match(/\d+(?:\.\d+)?/g) || [];
  return widths.map((w) => sprFlt(w)).filter((w) => w > 0);
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
    color: line.color || mixMeta.clType || "",
    gsm: line.gsm || mixMeta.gsm || 0,
    width_inch: line.width_inch || 0,
    batch_no: line.batch_no || "",
    roll_no: line.roll_no || "",
    meter_roll: 0,
    produced_length_mtrs: line.produced_length_mtrs ?? "",
    produced_gsm: line.produced_gsm || 0,
    net_weight: line.net_weight || 0,
    gross_weight: line.gross_weight != null ? String(line.gross_weight) : "",
    planned_qty: line.planned_qty || 0,
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
    produced_length_mtrs: row.produced_length_mtrs,
    produced_gsm: updated.produced_gsm,
    net_weight: updated.net_weight,
    gross_weight: gross,
    planned_qty: updated.planned_qty,
    party_code: row.party_code,
    row_locked: 1,
    row_ready_for_print: 1,
  };
}

export function recalcMixRollRow(row) {
  const gross = sprNormalizeGrossWeightInput(row.gross_weight);
  const updated = sprRecalcRollRow({ ...row, gross_weight: String(gross), meter_roll: 0 });
  row.net_weight = updated.net_weight;
  row.produced_gsm = updated.produced_gsm;
  row.planned_qty = updated.planned_qty;
  return row;
}
