/** Shared Production Board Access date + scope UI helpers. */

import { maintenanceUnitsEqual } from "./maintenance_utils.js";

export function formatAccessDateLabel(iso) {
	const s = String(iso || "").trim();
	if (!s) return s;
	try {
		if (typeof frappe !== "undefined" && frappe.datetime?.str_to_user) {
			return frappe.datetime.str_to_user(s);
		}
	} catch (e) {
		/* ignore */
	}
	return s;
}

export function applyBoardAccessDateScope(scope, refs) {
	if (!scope || scope.unlimited) return;
	const { filterOrderDate, viewScope } = refs || {};
	if (!filterOrderDate) return;

	if (scope.view_scope_locked && viewScope) {
		viewScope.value = "daily";
	}

	if (scope.date_picker_frozen) {
		filterOrderDate.value = scope.max_date || frappe.datetime.get_today();
		return;
	}

	const dates = scope.allowed_dates || [];
	if (dates.length && (!viewScope || viewScope.value === "daily")) {
		const cur = filterOrderDate.value || frappe.datetime.get_today();
		if (!dates.includes(cur)) {
			filterOrderDate.value = dates[dates.length - 1];
		}
		return;
	}

	if (scope.min_date && scope.max_date && (!viewScope || viewScope.value === "daily")) {
		let d = filterOrderDate.value || frappe.datetime.get_today();
		if (d < scope.min_date) filterOrderDate.value = scope.min_date;
		if (d > scope.max_date) filterOrderDate.value = scope.max_date;
	}
}

export function boardAccessDatePickerDisabled(ctx, isManufactureUser) {
	if (isManufactureUser) return true;
	if (!ctx || !ctx.loaded || ctx.unlimited) return false;
	return !!ctx.date_picker_frozen;
}

export function boardAccessDateUseSelect(ctx) {
	if (!ctx || !ctx.loaded || ctx.unlimited) return false;
	const dates = ctx.allowed_dates || [];
	return dates.length > 0 && !ctx.date_picker_frozen;
}

export function boardAccessViewScopeLocked(ctx, isManufactureUser) {
	if (isManufactureUser) return true;
	if (!ctx || !ctx.loaded || ctx.unlimited) return false;
	return !!ctx.view_scope_locked;
}

/** True when a toolbar action is frozen for the current board (button visible but disabled). */
export function isBoardActionFrozen(ctx, action) {
	if (!ctx || !ctx.loaded || ctx.unlimited) return false;
	const frozen = ctx.frozen_actions || {};
	return !!frozen[action];
}

export function boardActionFrozenStyle(ctx, action) {
	if (!isBoardActionFrozen(ctx, action)) return {};
	return { opacity: "0.45", cursor: "not-allowed", pointerEvents: "none" };
}

/**
 * Apply unit scope for restricted operators.
 * When boardUnits is given, only units valid on the current page are considered
 * (e.g. VTP-L1 on box-bag board, Unit 1 on production board).
 */
export function applyBoardAccessUnitScope(scope, filterUnitRef, boardUnits = null) {
	if (!scope || scope.unlimited || !filterUnitRef) return;
	const allowed = scope.allowed_units || [];
	if (!allowed.length) return;

	const pool = (() => {
		const list = Array.isArray(boardUnits) ? boardUnits : [];
		if (!list.length) return allowed;
		return allowed.filter((u) => list.some((b) => maintenanceUnitsEqual(u, b)));
	})();
	if (!pool.length) return;

	const cur = (filterUnitRef.value || "").trim();
	if (!cur) {
		filterUnitRef.value = pool[0];
		return;
	}
	const ok = pool.some((u) => maintenanceUnitsEqual(u, cur));
	if (!ok) filterUnitRef.value = pool[0];
}
