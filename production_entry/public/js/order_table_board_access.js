/** Shared Production Board Access wiring for *OrderTable.vue pages. */
import { ref, computed } from "vue";
import { applyBoardAccessDateScope } from "./board_access_ui.js";
import { unitAllowedByBoardAccess, maintenanceUnitsEqual } from "./maintenance_utils.js";

export function formatBoardAccessError(e) {
	if (!e) return "Unknown error";
	if (typeof e === "string") return e;
	if (e.message && typeof e.message === "string") return e.message;
	if (e._server_messages) {
		try {
			const msgs = JSON.parse(e._server_messages);
			return msgs
				.map((m) => {
					try {
						return JSON.parse(m).message;
					} catch {
						return m;
					}
				})
				.join("; ");
		} catch {
			/* ignore */
		}
	}
	if (e.exc_type) return `${e.exc_type}: ${e.message || ""}`;
	try {
		return JSON.stringify(e);
	} catch {
		return String(e);
	}
}

export function isBoardPermissionError(e) {
	if (e?.exc_type === "PermissionError") return true;
	return /not permitted/i.test(formatBoardAccessError(e));
}

/**
 * @param {string} boardSlug - table page slug (e.g. rewinding-order-table); board alias is resolved server-side
 * @param {{ filterOrderDate: import('vue').Ref, viewScope: import('vue').Ref, filterUnit?: import('vue').Ref }} refs
 */
export function createOrderTableBoardAccess(boardSlug, refs) {
	const boardAccessContext = ref({
		unlimited: false,
		allowed_units: [],
		loaded: false,
		permitted: true,
	});

	const accessDenied = computed(
		() => boardAccessContext.value.loaded && boardAccessContext.value.permitted === false
	);

	function applyBoardAccessContext(ctx) {
		const scope = ctx || { unlimited: false, allowed_units: [], allowed_boards: [] };
		boardAccessContext.value = { ...scope, loaded: true };
		if (!scope || scope.unlimited) return;
		applyBoardAccessDateScope(scope, refs);
		const fu = refs.filterUnit;
		if (!fu) return;
		if (scope.allowed_units && scope.allowed_units.length === 1) {
			fu.value = scope.allowed_units[0];
		} else if (scope.allowed_units && scope.allowed_units.length > 1) {
			const cur = (fu.value || "").trim();
			if (cur && !scope.allowed_units.some((u) => maintenanceUnitsEqual(u, cur))) {
				fu.value = "";
			}
		}
	}

	async function loadBoardAccessContext() {
		await new Promise((resolve) => {
			frappe.call({
				method:
					"production_entry.production_planning.board_access.get_production_board_user_context",
				args: { board_slug: boardSlug },
				callback: (r) => {
					const scope = (r && r.message) || {
						unlimited: false,
						allowed_units: [],
						permitted: false,
					};
					applyBoardAccessContext(scope);
					resolve();
				},
				error: () => {
					applyBoardAccessContext({
						unlimited: false,
						allowed_units: [],
						permitted: false,
					});
					resolve();
				},
			});
		});
	}

	function boardArgs(extra = {}) {
		return { board_slug: boardSlug, ...extra };
	}

	function filterListByAccess(list) {
		const ctx = boardAccessContext.value;
		if (!ctx || !ctx.loaded || ctx.unlimited) return list;
		const allowed = ctx.allowed_units || [];
		if (!allowed.length) return [];
		return list.filter((u) => unitAllowedByBoardAccess(u, allowed));
	}

	function filterRowsByAccess(rows) {
		const ctx = boardAccessContext.value;
		if (!ctx || !ctx.loaded || ctx.unlimited) return rows;
		const allowed = ctx.allowed_units || [];
		if (!allowed.length) return [];
		return rows.filter((r) => unitAllowedByBoardAccess(r.unit, allowed));
	}

	return {
		boardAccessContext,
		accessDenied,
		loadBoardAccessContext,
		boardArgs,
		filterListByAccess,
		filterRowsByAccess,
	};
}
