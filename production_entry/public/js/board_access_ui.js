/** Shared Production Board Access date + scope UI helpers. */

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
