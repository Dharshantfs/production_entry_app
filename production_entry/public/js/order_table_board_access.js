/** Shared Production Board Access wiring for *OrderTable.vue pages. */
import { ref, computed } from "vue";
import {
	applyBoardAccessDateScope,
	applyBoardAccessUnitScope,
	boardActionFrozenStyle,
	isBoardActionFrozen,
	shouldHideCustomerColumns,
} from "./board_access_ui.js";
import { unitAllowedByBoardAccess } from "./maintenance_utils.js";

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
 * @param {{ filterOrderDate: import('vue').Ref, viewScope: import('vue').Ref, filterUnit?: import('vue').Ref, getBoardUnits?: () => string[] }} refs
 */
export function createOrderTableBoardAccess(boardSlug, refs) {
	const boardAccessContext = ref({
		unlimited: false,
		allowed_units: [],
		loaded: false,
		permitted: true,
		frozen_actions: {},
	});

	const unitFilterState = ref({ pool: null, showUnitFilter: true, unitLocked: false });

	const accessDenied = computed(
		() => boardAccessContext.value.loaded && boardAccessContext.value.permitted === false
	);

	const hideCustomerColumns = computed(() => shouldHideCustomerColumns(boardAccessContext.value));

	function applyBoardAccessContext(ctx) {
		const scope = ctx || { unlimited: false, allowed_units: [], allowed_boards: [], frozen_actions: {} };
		boardAccessContext.value = { ...scope, loaded: true };
		if (!scope || scope.unlimited) {
			unitFilterState.value = { pool: null, showUnitFilter: true, unitLocked: false };
			return;
		}
		applyBoardAccessDateScope(scope, refs);
		const boardUnits = refs.getBoardUnits?.() || null;
		unitFilterState.value = applyBoardAccessUnitScope(scope, refs.filterUnit, boardUnits);
	}

	const freezeMaintenance = computed(() => isBoardActionFrozen(boardAccessContext.value, "maintenance"));
	const freezeTransfer = computed(() => isBoardActionFrozen(boardAccessContext.value, "transfer"));
	const freezeDespatch = computed(() => isBoardActionFrozen(boardAccessContext.value, "despatch"));
	const freezeArrangement = computed(() => isBoardActionFrozen(boardAccessContext.value, "arrangement"));
	const freezeAssignShift = computed(() => isBoardActionFrozen(boardAccessContext.value, "assign_shift"));
	const freezeSyncSpr = computed(() => isBoardActionFrozen(boardAccessContext.value, "sync_spr"));
	const freezeMerge = computed(() => isBoardActionFrozen(boardAccessContext.value, "merge"));
	const freezeReorder = computed(() => isBoardActionFrozen(boardAccessContext.value, "reorder"));

	function frozenStyle(action) {
		return boardActionFrozenStyle(boardAccessContext.value, action);
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
		const pool = unitFilterState.value.pool;
		if (Array.isArray(pool) && pool.length) {
			return list.filter((u) => pool.some((p) => unitAllowedByBoardAccess(u, [p])));
		}
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

	function refreshUnitScope() {
		const ctx = boardAccessContext.value;
		if (!ctx || !ctx.loaded || ctx.unlimited || !refs.filterUnit) return;
		const boardUnits = refs.getBoardUnits?.() || null;
		unitFilterState.value = applyBoardAccessUnitScope(ctx, refs.filterUnit, boardUnits);
	}

	return {
		boardAccessContext,
		unitFilterState,
		accessDenied,
		hideCustomerColumns,
		loadBoardAccessContext,
		boardArgs,
		filterListByAccess,
		filterRowsByAccess,
		refreshUnitScope,
		freezeMaintenance,
		freezeTransfer,
		freezeDespatch,
		freezeArrangement,
		freezeAssignShift,
		freezeSyncSpr,
		freezeMerge,
		freezeReorder,
		frozenStyle,
	};
}
