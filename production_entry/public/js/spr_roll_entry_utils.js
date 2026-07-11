/**
 * Shared roll-line calculations for SPR form and GSM Production Entry.
 * Keep in sync with shaft_production_run.js gross_weight / produced_gsm logic.
 */

export function sprFlt(v) {
	const n = parseFloat(v);
	return Number.isFinite(n) ? n : 0;
}

export function sprNormalizeGrossWeightInput(val) {
	if (val === null || val === undefined || val === '') {
		return 0;
	}
	if (typeof val === 'number') {
		return Number.isFinite(val) && val > 0 ? val : 0;
	}
	let s = String(val).replace(/,/g, '').trim();
	const firstNum = s.match(/-?\d+(?:\.\d+)?/);
	if (firstNum) {
		s = firstNum[0];
	}
	const dup = s.match(/^(\d+\.\d{1,4})\1+$/);
	if (dup) {
		s = dup[1];
	}
	const glued = s.match(/^(\d+\.\d{1,4})(\d+\.\d{1,4})$/);
	if (glued && glued[1] === glued[2]) {
		s = glued[1];
	}
	const n = parseFloat(s);
	return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Allow free decimal typing in GSM/SPR gross weight fields (digits + one dot). */
export function sprSanitizeGrossWeightTyping(val) {
	let s = String(val ?? '').replace(/,/g, '');
	const negative = s.startsWith('-');
	s = s.replace(/[^\d.]/g, '');
	const dot = s.indexOf('.');
	if (dot >= 0) {
		s = s.slice(0, dot + 1) + s.slice(dot + 1).replace(/\./g, '');
	}
	return negative && s ? `-${s}` : s;
}

export function sprGrossWeightDisplay(val) {
	if (val === null || val === undefined || val === '') {
		return '';
	}
	return sprSanitizeGrossWeightTyping(val);
}

export function sprRoundNetWeightKg(v) {
	return Math.round(sprFlt(v) * 100) / 100;
}

export function sprResolveLengthMeters(row) {
	const pl = sprFlt(row?.produced_length_mtrs);
	if (pl > 0) {
		return pl;
	}
	return sprFlt(row?.meter_roll);
}

/** Fabric width used for GSM / net formulas (bundle rows: segment × pack count). */
export function sprEffectiveWidthInch(row) {
	if (row?.is_bundle_row && cint(row?.pack_count) > 1 && sprFlt(row?.segment_width) > 0) {
		return sprFlt(row.segment_width) * cint(row.pack_count);
	}
	return sprFlt(row?.width_inch);
}

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}

export function sprCalcCoreWeightKg(width, grossWeight, coreWidthMmOrItem, coreOptions) {
	const widthInch = sprFlt(width);
	if (widthInch <= 0) {
		return 0;
	}
	const opts = coreOptions || [];
	const key = coreWidthMmOrItem != null ? String(coreWidthMmOrItem) : "";
	const opt = opts.find(
		(o) =>
			String(o.value) === key ||
			String(o.item_code) === key ||
			String(o.core_size) === key ||
			String(o.label) === key
	);
	if (opt && sprFlt(opt.core_inch) > 0 && sprFlt(opt.base_weight_kgs) > 0) {
		return (widthInch / sprFlt(opt.core_inch)) * sprFlt(opt.base_weight_kgs);
	}
	// Legacy fallback when Core Size master data is unavailable
	const gw = sprFlt(grossWeight);
	if (gw <= 0) {
		return 0;
	}
	let numericCoreWidth = parseFloat(coreWidthMmOrItem);
	if (!Number.isFinite(numericCoreWidth) || numericCoreWidth < 100) {
		numericCoreWidth = opt ? sprFlt(opt.width_mm) : 1600;
	}
	const widthInMeter = widthInch * 0.0254;
	const gsmVal = 90;
	const rawWeight = (gsmVal * widthInMeter * gw) / 1000;
	const standardWidths = [63, 85, 90, 118, 126];
	const isStandard = standardWidths.some((w) => Math.abs(widthInch - w) < 0.01);
	if (isStandard) {
		let baseWeightOfCore = 1.3;
		if (rawWeight >= 50 && rawWeight <= 100) {
			baseWeightOfCore = 1.8;
		} else if (rawWeight > 100) {
			baseWeightOfCore = 2.5;
		}
		return (baseWeightOfCore / 1600) * numericCoreWidth;
	}
	let coreW;
	let prorate;
	if (widthInch < 63) {
		coreW = 63;
		prorate = 1.3;
	} else if (widthInch < 85) {
		coreW = 85;
		prorate = 1.75;
	} else if (widthInch < 90) {
		coreW = 90;
		prorate = 1.86;
	} else if (widthInch < 118) {
		coreW = 118;
		prorate = 2.43;
	} else {
		coreW = 126;
		prorate = 2.6;
	}
	return (widthInch / coreW) * prorate;
}

export function sprCoreBaseWeightKgs(coreWidthMmOrItem, coreOptions) {
	const opts = coreOptions || [];
	const key = coreWidthMmOrItem != null ? String(coreWidthMmOrItem) : "";
	const opt = opts.find(
		(o) =>
			String(o.value) === key ||
			String(o.item_code) === key ||
			String(o.core_size) === key ||
			String(o.label) === key
	);
	return opt ? sprFlt(opt.base_weight_kgs) : 0;
}

export function sprCalcNetFromGross(row) {
	const gw = sprNormalizeGrossWeightInput(row?.gross_weight);
	if (gw <= 0) {
		return 0;
	}
	const width = sprEffectiveWidthInch(row);
	if (width <= 0) {
		return 0;
	}
	const coreWeight = sprCalcCoreWeightKg(width, gw, row?.custom_core_width_mm, row?.core_width_options);
	const polybag = sprFlt(row?.custom_polybag_kgs);
	const calcNet = gw - coreWeight - polybag;
	const netVal = calcNet > 0 ? calcNet : gw - polybag > 0 ? gw - polybag : gw;
	return sprRoundNetWeightKg(netVal);
}

export function sprCalcProducedGsm(row) {
	const gw = sprNormalizeGrossWeightInput(row?.gross_weight);
	let nw = sprFlt(row?.net_weight);
	if (gw <= 0) {
		return 0;
	}
	if (nw <= 0) {
		nw = gw;
	}
	const wi = sprEffectiveWidthInch(row);
	const mr = sprResolveLengthMeters(row);
	if (nw <= 0 || wi <= 0 || mr <= 0) {
		return 0;
	}
	return Math.round(((nw * 1000) / (wi * mr * 0.0254)) * 100) / 100;
}

export function sprRecalcRollRow(row) {
	const preserveNet = row?.is_bundle_row && sprFlt(row?.net_weight) > 0;
	const gwForCalc = sprNormalizeGrossWeightInput(row.gross_weight);
	const rowForCalc = { ...row, gross_weight: gwForCalc };
	const net = preserveNet ? sprFlt(row.net_weight) : sprCalcNetFromGross(rowForCalc);
	const produced = sprCalcProducedGsm({ ...rowForCalc, net_weight: net });
	const lengthM = sprResolveLengthMeters(row);
	const planned =
		sprFlt(row.planned_qty) > 0
			? sprFlt(row.planned_qty)
			: sprComputePlannedQtyKg(row.gsm, row.width_inch, lengthM || row.meter_roll);
	return {
		net_weight: net,
		produced_gsm: produced,
		planned_qty: planned > 0 ? planned : row.planned_qty,
	};
}

export function sprGsmBandDiff(stickerGsm, producedGsm) {
	const sticker = sprFlt(stickerGsm);
	const produced = sprFlt(producedGsm);
	if (sticker <= 0 || produced <= 0) {
		return null;
	}
	return Math.abs(produced - sticker);
}

export function sprGsmBandClass(stickerGsm, producedGsm, hasWeight) {
	if (!hasWeight) {
		return 'gpe-gsm-incomplete';
	}
	const diff = sprGsmBandDiff(stickerGsm, producedGsm);
	if (diff === null) {
		return 'gpe-gsm-incomplete';
	}
	if (diff < 1) {
		return 'gpe-gsm-band-0';
	}
	if (diff < 2) {
		return 'gpe-gsm-band-1';
	}
	if (diff < 3) {
		return 'gpe-gsm-band-2';
	}
	return 'gpe-gsm-band-3';
}

export function sprComputePlannedQtyKg(gsm, widthInch, lengthM) {
	const g = sprFlt(gsm);
	const w = sprFlt(widthInch);
	const ln = sprFlt(lengthM);
	if (g <= 0 || w <= 0 || ln <= 0) {
		return 0;
	}
	return Math.round((g * w * ln * 0.0254) / 1000 * 100) / 100;
}

export function sprFormatKg(v) {
	return sprFlt(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Combo segment count from combination string (e.g. 58+58 → 2). */
export function sprComboSegmentCount(combination) {
	const comb = String(combination || '').trim();
	if (!comb) {
		return 1;
	}
	return comb.split('+').map((s) => s.trim()).filter(Boolean).length || 1;
}

/**
 * 1-based shaft number for a roll at zero-based index idx within a job.
 * Matches desk SPR / _spr_shaft_no_for_roll_index in shaft_production_run.py.
 */
export function sprShaftNoForRollIndex(idx, noShafts, rollsPerShaft, segs = 1) {
	const shafts = Math.max(1, cint(noShafts));
	const rps = Math.max(1, cint(rollsPerShaft));
	const segments = Math.max(1, cint(segs));
	const effectiveRolls = segments > 1 ? rps * segments : rps;
	const index = Math.max(0, cint(idx));
	return Math.min(shafts, Math.floor(index / effectiveRolls) + 1);
}
