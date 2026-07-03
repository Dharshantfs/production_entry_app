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
	const s = String(val).replace(/,/g, '').trim();
	const n = parseFloat(s);
	return Number.isFinite(n) && n > 0 ? n : 0;
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

export function sprCalcCoreWeightKg(width, grossWeight, coreWidthMmOrItem, coreOptions) {
	const widthInch = sprFlt(width);
	const gw = sprFlt(grossWeight);
	if (widthInch <= 0 || gw <= 0) {
		return 0;
	}
	let numericCoreWidth = parseFloat(coreWidthMmOrItem);
	if (!Number.isFinite(numericCoreWidth) || numericCoreWidth < 100) {
		const opts = coreOptions || [];
		const key = coreWidthMmOrItem != null ? String(coreWidthMmOrItem) : "";
		const opt = opts.find((o) => String(o.value) === key || String(o.item_code) === key);
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

export function sprCalcNetFromGross(row) {
	const gw = sprNormalizeGrossWeightInput(row?.gross_weight);
	if (gw <= 0) {
		return 0;
	}
	const width = sprFlt(row?.width_inch);
	if (width <= 0) {
		return 0;
	}
	const coreWeight = sprCalcCoreWeightKg(width, gw, row?.custom_core_width_mm, row?.core_width_options);
	const calcNet = gw - coreWeight;
	const netVal = calcNet > 0 ? calcNet : gw;
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
	const wi = sprFlt(row?.width_inch);
	const mr = sprResolveLengthMeters(row);
	if (nw <= 0 || wi <= 0 || mr <= 0) {
		return 0;
	}
	return Math.round(((nw * 1000) / (wi * mr * 0.0254)) * 100) / 100;
}

export function sprRecalcRollRow(row) {
	const net = sprCalcNetFromGross(row);
	const produced = sprCalcProducedGsm({ ...row, net_weight: net });
	const lengthM = sprResolveLengthMeters(row);
	const planned =
		sprFlt(row.planned_qty) > 0
			? sprFlt(row.planned_qty)
			: sprComputePlannedQtyKg(row.gsm, row.width_inch, lengthM || row.meter_roll);
	return {
		...row,
		gross_weight: sprNormalizeGrossWeightInput(row.gross_weight) || row.gross_weight,
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
