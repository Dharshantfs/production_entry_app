/** Inch ↔ mm helpers for Rewinding / Slitting / Sheet Cutting order tables */

export function mmFromInchesRounded5(inches) {
	const v = Number(inches);
	if (!Number.isFinite(v) || v <= 0) {
		return null;
	}
	return Math.round((v * 25.4) / 5) * 5;
}

/** Last 4 numeric digits from an item/item-style code → mm hint (fallback). */
export function lastFourDigitsMm(code) {
	const raw = String(code || '').trim();
	if (!raw) {
		return null;
	}
	const digits = raw.replace(/\D/g, '');
	if (digits.length < 4) {
		return null;
	}
	const n = parseInt(digits.slice(-4), 10);
	return Number.isFinite(n) ? n : null;
}

/**
 * Convert inches→mm rounded to nearest 5; if result disagrees badly with BOM/item-code tail, prefer tail.
 */
export function mmDisplayFromInchesWithCodeFallback(inches, fallbackCode, disagreeThreshold = 10) {
	const calc = mmFromInchesRounded5(inches);
	const fb = lastFourDigitsMm(fallbackCode);
	if (fb == null) {
		return calc;
	}
	if (calc == null || !(calc > 0)) {
		return fb;
	}
	if (Math.abs(calc - fb) > disagreeThreshold) {
		return fb;
	}
	return calc;
}

/** @param fallbackItemCode — optional fabric/parent item code string for last-4-digit mm hint */
export function formatSingleDimension(row, inchesField, unitMode, fallbackItemCode) {
	let inchVal = Number(row[inchesField]);
	if (!Number.isFinite(inchVal) || inchVal <= 0) {
		return '-';
	}
	if (unitMode === 'inches') {
		return inchVal % 1 === 0 ? String(inchVal) : String(Math.round(inchVal * 100) / 100);
	}
	const mm = mmDisplayFromInchesWithCodeFallback(inchVal, fallbackItemCode);
	return mm != null ? String(mm) : '-';
}

export function parseTwoInchDims(sheetSizeStr, wInch, hInch) {
	const w0 = Number(wInch);
	const h0 = Number(hInch);
	if (Number.isFinite(w0) && w0 > 0 && Number.isFinite(h0) && h0 > 0) {
		return [w0, h0];
	}
	const s = String(sheetSizeStr || '').trim();
	if (!s) {
		return null;
	}
	let m = s.match(/(\d+(?:\.\d+)?)\s*["'′]?\s*[x×*]\s*(\d+(?:\.\d+)?)\s*["'′]?/i);
	if (m) {
		return [parseFloat(m[1]), parseFloat(m[2])];
	}
	m = s.match(/^(\d+(?:\.\d+)?)\s*\*\s*(\d+(?:\.\d+)?)$/);
	if (m) {
		return [parseFloat(m[1]), parseFloat(m[2])];
	}
	return null;
}

export function formatSheetSizeCell(row, unitMode) {
	const dims = parseTwoInchDims(row.sheet_size, row.sheet_width_inch, row.sheet_height_inch);
	if (!dims) {
		return row.sheet_size || '-';
	}
	const [wi, hi] = dims;
	if (unitMode === 'inches') {
		const wf = wi % 1 === 0 ? String(wi) : String(Math.round(wi * 100) / 100);
		const hf = hi % 1 === 0 ? String(hi) : String(Math.round(hi * 100) / 100);
		return `${wf}" x ${hf}"`;
	}
	const wm = mmFromInchesRounded5(wi);
	const hm = mmFromInchesRounded5(hi);
	if (wm == null || hm == null) {
		return row.sheet_size || '-';
	}
	return `${wm} x ${hm} mm`;
}

/** Target/planned kg from Planning sheet — no integer rounding (164.580 → 164.58). */
export function formatKgPlanning(value) {
	const num = parseFloat(value || 0);
	if (!Number.isFinite(num)) return '0';
	if (Math.abs(num - Math.round(num)) < 1e-9) return String(Math.round(num));
	return num
		.toFixed(3)
		.replace(/0+$/, '')
		.replace(/\.$/, '');
}
