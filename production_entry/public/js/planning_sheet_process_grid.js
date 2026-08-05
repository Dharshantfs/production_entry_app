/**
 * Planning Sheet child-grid columns by item_code process prefix.
 * Uses in_list_view only (via child_grid_columns.js) — never hidden=1 on data fields.
 */
frappe.provide('production_entry.planning_sheet_process_grid');

const PS_KNOWN_PREFIXES = new Set([
	'100', '102', '103', '104', '105', '106', '107', '108', '109', '110',
	'200', '201', '202', '203',
	'211', '212', '213', '214', '216', '217',
	'221', '222', '223', '224', '231', '232', '233', '241', '242', '225', '226',
	'251', '252', '253', '254', '255',
]);

const PS_GRID_TABLE_FIELDS = ['items', 'planned_items'];

const PS_GRID_META_BY_FIELD = {
	items: 'Planning sheet Item',
	planned_items: 'Planning Table',
};

/** Always visible — never toggle off. */
const PS_CORE_GRID_FIELDS = new Set(['item_code', 'item_name', 'qty', 'uom', 'unit']);

/** Never show in planning sheet child grids (shift / arrangement — board-only). */
const PS_NEVER_SHOW_GRID_FIELDS = new Set([
	'custom_printing_shift',
	'custom_printing_arrangement_seq',
	'custom_lamination_shift',
	'custom_slitting_shift',
	'custom_sheet_cutting_shift',
	// Board must not show Custom Quality (use `quality`); items keep Planned Date via logical planned_date.
	'custom_quality',
]);

function ps_filter_grid_show_fields(fieldnames) {
	return (fieldnames || []).filter((fn) => fn && !PS_NEVER_SHOW_GRID_FIELDS.has(fn));
}

/** Fabric 100 / 102 / 103 — canonical grid column order (user-enforced). */
const PS_CANONICAL_FABRIC_ORDER = [
	'item_code', 'item_name', 'qty', 'uom', 'gsm', 'quality', 'color', 'width_inch', 'unit',
	'planned_date', 'custom_parent_child_trace_id', 'custom_parent_fabric',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
];
const PS_ORDER_FABRIC_BASE = PS_CANONICAL_FABRIC_ORDER;

const PS_ORDER_SHEET_251 = [
	'item_code', 'item_name', 'qty', 'uom', 'gsm', 'quality', 'color', 'width_inch', 'unit',
	'planned_date', 'custom_parent_child_trace_id', 'custom_parent_fabric',
	'sheet_size', 'custom_no_of_sheets',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
];

const PS_ORDER_SHEET_252 = [
	'item_code', 'item_name', 'qty', 'custom_design_code', 'custom_design_name',
	'custom_design_colour', 'custom_design_attachment', 'uom', 'gsm', 'quality', 'color', 'width_inch', 'unit',
	'planned_date', 'custom_parent_child_trace_id', 'custom_parent_fabric',
	'sheet_size', 'custom_no_of_sheets',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
];

const PS_ORDER_SHEET_253 = [
	'item_code', 'item_name', 'qty', 'uom', 'gsm', 'custom_lam_gsm', 'custom_lam_side',
	'quality', 'color', 'width_inch', 'unit', 'planned_date', 'custom_parent_child_trace_id',
	'custom_parent_fabric', 'sheet_size', 'custom_no_of_sheets',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
];

const PS_ORDER_SHEET_254 = [
	'item_code', 'item_name', 'qty', 'custom_design_code', 'custom_design_name',
	'custom_design_colour', 'custom_design_attachment', 'uom', 'gsm', 'custom_lam_gsm', 'custom_lam_side',
	'quality', 'color', 'width_inch', 'unit', 'planned_date', 'custom_parent_child_trace_id',
	'custom_parent_fabric', 'sheet_size', 'custom_no_of_sheets',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
];

const PS_FIELD_ORDER_BY_PROCESS = {
	100: PS_CANONICAL_FABRIC_ORDER,
	102: PS_CANONICAL_FABRIC_ORDER,
	103: PS_CANONICAL_FABRIC_ORDER,
	104: [
		'item_code', 'item_name', 'qty', 'uom', 'gsm', 'custom_lam_gsm', 'custom_lam_side',
		'quality', 'color', 'width_inch', 'unit', 'planned_date', 'custom_parent_child_trace_id',
		'custom_parent_fabric', 'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll',
		'order_sheet', 'spr_name',
	],
	105: [
		'item_code', 'item_name', 'qty', 'custom_design_code', 'custom_design_name',
		'custom_design_attachment', 'uom', 'gsm', 'quality', 'color', 'width_inch', 'unit',
		'planned_date', 'custom_parent_child_trace_id', 'custom_parent_fabric',
		'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
	],
	251: PS_ORDER_SHEET_251,
	252: PS_ORDER_SHEET_252,
	253: PS_ORDER_SHEET_253,
	254: PS_ORDER_SHEET_254,
};

const PS_BASE_FIELDS = [
	'item_code', 'item_name', 'qty', 'uom', 'unit',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'width_inch',
	'gsm', 'quality', 'color',
	'custom_parent_fabric', 'custom_parent_child_trace_id',
	'planned_date', 'custom_plan_code', 'plan_name',
	'custom_movement_type', 'order_sheet', 'spr_name',
];

const PS_PRINT_105_FIELDS = [
	'custom_design_code', 'custom_design_name', 'custom_design_colour',
	'custom_design_attachment',
];

const PS_BOPP_STACK_FIELDS = [
	'custom_lam_gsm', 'custom_bopp_gsm', 'custom_finishing', 'custom_white_tint',
	'custom_design_code', 'custom_design_name', 'custom_design_colour',
	'custom_design_attachment',
	'custom_lam_side', 'custom_lam_side_',
];

const PS_SLITTING_FIELDS = [];

const PS_SHEET_CUT_FIELDS = [
	'sheet_size', 'custom_no_of_sheets',
];

const PS_BAG_FIELDS = [
	'bag_size', 'custom_finishing', 'custom_no_of_design_colours',
	'custom_total_no_of_colours',
];

const PS_PB_FIELDS = [
	'custom_bopp_gsm', 'custom_cylinder_type', 'custom_bopp_finish_size_mm',
	'custom_no_of_design_colours', 'custom_total_no_of_colours', 'custom_bopp_bom_kgs',
	'custom_design_code', 'custom_design_name', 'custom_design_colour',
	'custom_design_attachment', 'custom_finishing', 'custom_white_tint',
];

function ps_get_grid_columns_module() {
	try {
		const pe = typeof window !== 'undefined' && window.production_entry;
		if (pe && pe.grid_columns) {
			return pe.grid_columns;
		}
	} catch (e) {
		/* ignore */
	}
	return null;
}

function ps_item_process_prefix(item_code) {
	const ic = String(item_code || '').trim();
	if (!ic) {
		return '';
	}
	if (ic.toUpperCase().startsWith('PB') || ic.toUpperCase().startsWith('PB-')) {
		return 'PB';
	}
	if (ic.indexOf('-') >= 0) {
		const upper = ic.toUpperCase();
		if (/^[A-Z0-9]+-105\d/.test(upper)) {
			return '105';
		}
		if (/^[A-Z0-9]+-106/.test(upper)) {
			return '106';
		}
		const segments = ic.split('-');
		for (let i = 0; i < segments.length; i += 1) {
			const segDigits = segments[i].replace(/\D/g, '');
			if (segDigits.length >= 3) {
				const sp = segDigits.substring(0, 3);
				if (PS_KNOWN_PREFIXES.has(sp)) {
					return sp;
				}
			}
		}
		return '';
	}
	const digits = ic.replace(/\D/g, '');
	const sp = digits.length >= 3 ? digits.substring(0, 3) : '';
	return PS_KNOWN_PREFIXES.has(sp) ? sp : '';
}

function ps_resolve_field_for_table(table_fieldname, logicalField) {
	if (logicalField === 'planned_date') {
		return table_fieldname === 'planned_items' ? 'planned_date' : 'custom_item_planned_date';
	}
	if (logicalField === 'custom_lam_side') {
		return table_fieldname === 'planned_items' ? 'custom_lam_side_' : 'custom_lam_side';
	}
	return logicalField;
}

function ps_resolve_order_for_table(table_fieldname, logicalOrder) {
	const metaDoctype = PS_GRID_META_BY_FIELD[table_fieldname];
	if (!metaDoctype || !logicalOrder || !logicalOrder.length) {
		return [];
	}
	const out = [];
	const seen = {};
	ps_filter_grid_show_fields(logicalOrder).forEach((fn) => {
		const resolved = ps_resolve_field_for_table(table_fieldname, fn);
		// Board schedule date is `planned_date` only — never show legacy Item planned date column.
		if (table_fieldname === 'planned_items' && resolved === 'custom_item_planned_date') {
			return;
		}
		if (seen[resolved]) {
			return;
		}
		if (frappe.meta.get_docfield(metaDoctype, resolved)) {
			seen[resolved] = 1;
			out.push(resolved);
		}
	});
	return out;
}

function ps_merge_process_field_orders(codes) {
	const sorted = Array.from(codes).sort();
	if (!sorted.length) {
		return PS_ORDER_FABRIC_BASE.slice();
	}
	let merged = (PS_FIELD_ORDER_BY_PROCESS[sorted[0]] || PS_ORDER_FABRIC_BASE).slice();
	const seen = new Set(merged);
	for (let i = 1; i < sorted.length; i += 1) {
		const tpl = PS_FIELD_ORDER_BY_PROCESS[sorted[i]] || [];
		tpl.forEach((fn) => {
			if (seen.has(fn)) {
				return;
			}
			seen.add(fn);
			const idxInTpl = tpl.indexOf(fn);
			let insertAt = merged.length;
			for (let j = idxInTpl - 1; j >= 0; j -= 1) {
				const anchor = tpl[j];
				const anchorIdx = merged.indexOf(anchor);
				if (anchorIdx >= 0) {
					insertAt = anchorIdx + 1;
					break;
				}
			}
			merged.splice(insertAt, 0, fn);
		});
	}
	return merged;
}

function ps_merge_fields_into_canonical_order(allowedSet, baseOrder) {
	const merged = (baseOrder || PS_CANONICAL_FABRIC_ORDER).filter((f) => allowedSet.has(f));
	const seen = new Set(merged);
	Array.from(allowedSet).forEach((fn) => {
		if (seen.has(fn)) {
			return;
		}
		let insertAt = merged.length;
		Object.values(PS_FIELD_ORDER_BY_PROCESS).forEach((tpl) => {
			const idx = tpl.indexOf(fn);
			if (idx < 0) {
				return;
			}
			for (let j = idx - 1; j >= 0; j -= 1) {
				const anchorIdx = merged.indexOf(tpl[j]);
				if (anchorIdx >= 0) {
					insertAt = Math.min(insertAt, anchorIdx + 1);
					break;
				}
			}
		});
		merged.splice(insertAt, 0, fn);
		seen.add(fn);
	});
	return merged;
}

function ps_child_tables_empty(frm) {
	const items = (frm && frm.doc && frm.doc.items) || [];
	const planned = (frm && frm.doc && frm.doc.planned_items) || [];
	return !items.length && !planned.length;
}

function ps_fields_for_process(code) {
	if (PS_FIELD_ORDER_BY_PROCESS[code]) {
		return new Set(PS_FIELD_ORDER_BY_PROCESS[code]);
	}
	const out = new Set(PS_BASE_FIELDS);
	if (!code || code === 'PB') {
		if (code === 'PB') {
			PS_PB_FIELDS.forEach((f) => out.add(f));
		}
		return out;
	}
	if (code === '106') {
		PS_PRINT_105_FIELDS.forEach((f) => out.add(f));
		out.add('custom_lam_gsm');
		return out;
	}
	if (code === '107' || code === '255') {
		PS_BOPP_STACK_FIELDS.forEach((f) => out.add(f));
		if (code === '255') {
			PS_SHEET_CUT_FIELDS.forEach((f) => out.add(f));
		}
		return out;
	}
	if (code === '108' || code === '109' || code === '110') {
		PS_BOPP_STACK_FIELDS.forEach((f) => out.add(f));
		return out;
	}
	if (code === '251') {
		PS_SHEET_CUT_FIELDS.forEach((f) => out.add(f));
		return out;
	}
	if (code === '252') {
		PS_SHEET_CUT_FIELDS.forEach((f) => out.add(f));
		PS_PRINT_105_FIELDS.forEach((f) => out.add(f));
		return out;
	}
	if (code === '253') {
		PS_SHEET_CUT_FIELDS.forEach((f) => out.add(f));
		out.add('custom_lam_gsm');
		out.add('custom_lam_side');
		out.add('custom_lam_side_');
		return out;
	}
	if (code === '254') {
		PS_SHEET_CUT_FIELDS.forEach((f) => out.add(f));
		PS_PRINT_105_FIELDS.forEach((f) => out.add(f));
		out.add('custom_lam_gsm');
		out.add('custom_lam_side');
		out.add('custom_lam_side_');
		return out;
	}
	if (
		code === '200' || code === '201' || code === '202' || code === '203'
		|| code === '211' || code === '212' || code === '213' || code === '214'
		|| code === '216' || code === '217'
		|| code === '221' || code === '222' || code === '223' || code === '224'
		|| code === '231' || code === '232' || code === '233' || code === '241' || code === '242'
		|| code === '225' || code === '226'
	) {
		PS_BAG_FIELDS.forEach((f) => out.add(f));
		PS_BOPP_STACK_FIELDS.forEach((f) => out.add(f));
		return out;
	}
	return out;
}

function ps_collect_active_process_codes(frm) {
	const codes = new Set();
	(frm.doc.items || []).concat(frm.doc.planned_items || []).forEach((row) => {
		const p = ps_item_process_prefix(row && row.item_code);
		if (p) {
			codes.add(p);
		}
	});
	return codes;
}

function ps_build_logical_field_order(frm) {
	const codes = ps_collect_active_process_codes(frm);
	if (!codes.size) {
		return ps_filter_grid_show_fields(PS_CANONICAL_FABRIC_ORDER.slice());
	}
	const sorted = Array.from(codes).sort();
	if (sorted.every((c) => PS_FIELD_ORDER_BY_PROCESS[c])) {
		return ps_filter_grid_show_fields(ps_merge_process_field_orders(codes));
	}
	const allowed = new Set();
	codes.forEach((code) => {
		ps_fields_for_process(code).forEach((f) => allowed.add(f));
	});
	PS_CORE_GRID_FIELDS.forEach((f) => allowed.add(f));
	PS_NEVER_SHOW_GRID_FIELDS.forEach((f) => allowed.delete(f));
	return ps_filter_grid_show_fields(ps_merge_fields_into_canonical_order(allowed, PS_CANONICAL_FABRIC_ORDER));
}

function ps_build_show_fieldnames(frm, table_fieldname) {
	const logicalOrder = ps_build_logical_field_order(frm);
	return ps_resolve_order_for_table(table_fieldname, logicalOrder);
}

function ps_attach_planning_grid_scroll_sync(frm, tableField) {
	const fd = frm && frm.fields_dict && frm.fields_dict[tableField];
	if (!fd || !fd.$wrapper || !fd.$wrapper.length) {
		return;
	}
	const $w = fd.$wrapper;
	const syncKey = 'ps-grid-scroll-sync-' + tableField;
	if ($w.data(syncKey)) {
		return;
	}
	$w.data(syncKey, 1);
	$w.on('scroll.psGridAlign', '.form-grid-container, .dt-scrollable, .form-grid .grid-body, .grid-heading-row', function () {
		const gc = ps_get_grid_columns_module();
		if (gc && typeof gc.sync_header_scroll === 'function') {
			gc.sync_header_scroll(frm, tableField);
		}
	});
}

function ps_wrap_planning_grids(frm) {
	if (!frm || !frm.fields_dict) {
		return;
	}
	PS_GRID_TABLE_FIELDS.forEach((tableField) => {
		const fd = frm.fields_dict[tableField];
		if (fd && fd.$wrapper && fd.$wrapper.length) {
			fd.$wrapper.addClass('ps-grid-wrap');
			if (tableField === 'items') {
				fd.$wrapper.addClass('ps-grid-items-wrap');
			} else if (tableField === 'planned_items') {
				fd.$wrapper.addClass('ps-grid-board-wrap');
			}
			ps_attach_planning_grid_scroll_sync(frm, tableField);
		}
	});
}

function ps_clear_planning_grid_user_settings(grid) {
	if (!grid) {
		return;
	}
	try {
		delete grid.user_settings;
		delete grid.user_defined_columns;
		grid.visible_columns = null;
	} catch (e) {
		/* ignore */
	}
}

function ps_bind_planning_grid_user_settings_hook(frm, tableField) {
	const grid = frm.fields_dict[tableField] && frm.fields_dict[tableField].grid;
	if (!grid || grid._ps_user_settings_hooked) {
		return;
	}
	grid._ps_user_settings_hooked = true;
	const origGet = grid.get_user_settings;
	if (typeof origGet !== 'function') {
		return;
	}
	grid.get_user_settings = function psPlanningGridUserSettings() {
		const settings = origGet.apply(this, arguments) || {};
		if (settings.GridView) {
			delete settings.GridView;
		}
		ps_clear_planning_grid_user_settings(this);
		return settings;
	};
}

function ps_apply_grid_columns(frm, tableFieldname) {
	const metaDoctype = PS_GRID_META_BY_FIELD[tableFieldname];
	const gc = ps_get_grid_columns_module();
	const fd = frm.fields_dict[tableFieldname];
	if (!metaDoctype || !gc || typeof gc.apply !== 'function' || !fd || !fd.grid) {
		return;
	}
	ps_bind_planning_grid_user_settings_hook(frm, tableFieldname);
	ps_clear_planning_grid_user_settings(fd.grid);
	const showFields = ps_build_show_fieldnames(frm, tableFieldname);
	if (!showFields.length) {
		return;
	}
	gc.apply(frm, tableFieldname, metaDoctype, showFields, { fullRefresh: false });
}

function ps_ensure_both_grids_have_rows(frm) {
	if (!frm || !frm.doc) {
		return;
	}
	const gc = ps_get_grid_columns_module();
	PS_GRID_TABLE_FIELDS.forEach(function (t) {
		if (gc && typeof gc.ensure_rows_from_doc === 'function') {
			gc.ensure_rows_from_doc(frm, t);
		}
	});
}

function ps_clear_saved_grid_view_settings(metaDoctype) {
	try {
		const key = frappe.scrub(metaDoctype);
		const us = frappe.model.user_settings && frappe.model.user_settings[key];
		if (us && us.GridView) {
			delete us.GridView;
		}
	} catch (e) {
		/* ignore */
	}
}

function ps_enforce_planning_sheet_grids(frm) {
	if (!frm || frm.doctype !== 'Planning sheet' || frm._ps_enforcing_grids) {
		return;
	}
	if (!frm.fields_dict || !frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	if (ps_child_tables_empty(frm) && !frm.doc.name) {
		return;
	}
	frm._ps_enforcing_grids = true;
	try {
		ps_wrap_planning_grids(frm);
		ps_install_grid_refresh_guards(frm);
		ps_ensure_both_grids_have_rows(frm);
		const logicalOrder = ps_build_logical_field_order(frm);
		const gc = ps_get_grid_columns_module();
		PS_GRID_TABLE_FIELDS.forEach((t) => {
			const showFields = ps_resolve_order_for_table(t, logicalOrder);
			const metaDoctype = PS_GRID_META_BY_FIELD[t];
			if (!showFields.length || !metaDoctype || !gc || typeof gc.apply !== 'function') {
				return;
			}
			ps_bind_planning_grid_user_settings_hook(frm, t);
			ps_clear_saved_grid_view_settings(metaDoctype);
			const fd = frm.fields_dict[t];
			if (fd && fd.grid) {
				ps_clear_planning_grid_user_settings(fd.grid);
			}
			gc.apply(frm, t, metaDoctype, showFields, { fullRefresh: false });
		});
		ps_ensure_both_grids_have_rows(frm);
	} catch (e) {
		if (typeof console !== 'undefined' && console.warn) {
			console.warn('ps_enforce_planning_sheet_grids failed', e);
		}
	} finally {
		frm._ps_enforcing_grids = false;
	}
}

function ps_apply_both_grids(frm) {
	ps_enforce_planning_sheet_grids(frm);
}

function apply_process_code_visibility(frm) {
	ps_enforce_planning_sheet_grids(frm);
}

function ps_install_setup_visible_columns_hook(frm, tableField) {
	const grid = frm.fields_dict[tableField] && frm.fields_dict[tableField].grid;
	if (!grid || grid._ps_setup_visible_hooked) {
		return;
	}
	const orig = grid.setup_visible_columns;
	if (typeof orig !== 'function') {
		return;
	}
	grid._ps_setup_visible_hooked = true;
	grid.setup_visible_columns = function psPlanningSetupVisibleColumns() {
		const logicalOrder = ps_build_logical_field_order(frm);
		const order = ps_resolve_order_for_table(tableField, logicalOrder);
		const gc = ps_get_grid_columns_module();
		if (order.length && gc && typeof gc.sync_grid_to_column_order === 'function') {
			cg_sync_before_setup(grid, order, gc);
		}
		const ret = orig.apply(this, arguments);
		if (order.length && gc && typeof gc.mirror_grid_docfields_to_rows === 'function') {
			gc.mirror_grid_docfields_to_rows(grid);
		}
		return ret;
	};
}

function cg_sync_before_setup(grid, order, gc) {
	try {
		gc.sync_grid_to_column_order(grid, order);
		const showSet = {};
		order.forEach((fn) => {
			showSet[fn] = 1;
		});
		(grid.docfields || []).forEach((df) => {
			if (!df || !df.fieldname) {
				return;
			}
			const show = !!showSet[df.fieldname];
			df.in_list_view = show ? 1 : 0;
			df.hidden = 0;
		});
	} catch (e) {
		/* ignore */
	}
}

function ps_install_grid_refresh_guards(frm) {
	if (!frm || !frm.fields_dict) {
		return;
	}
	const gc = ps_get_grid_columns_module();
	if (!gc || typeof gc.install_refresh_column_guard !== 'function') {
		return;
	}
	PS_GRID_TABLE_FIELDS.forEach((t) => {
		ps_bind_planning_grid_user_settings_hook(frm, t);
		ps_install_setup_visible_columns_hook(frm, t);
		gc.install_refresh_column_guard(frm, t, function psColumnOrderForGuard() {
			const logicalOrder = ps_build_logical_field_order(frm);
			return ps_resolve_order_for_table(t, logicalOrder);
		});
	});
}

function ps_stabilize_planning_grids_after_refresh(frm) {
	ps_enforce_planning_sheet_grids(frm);
	if (typeof planning_sheet_apply_stock_grid_ui === 'function') {
		planning_sheet_apply_stock_grid_ui(frm, { skip_reapply: true });
	}
	if (typeof register_planning_sheet_stock_check_button === 'function') {
		register_planning_sheet_stock_check_button(frm, { grids_only: true });
	}
}

/** After create / regenerate / reload_doc — enforce columns once doc is in memory. */
function ps_after_planning_sheet_reload(frm) {
	if (!frm) {
		return;
	}
	schedule_apply_process_code_visibility(frm, 50);
}

function schedule_apply_process_code_visibility(frm, delay, options) {
	if (!frm) {
		return;
	}
	const run = function () {
		if (!frm.fields_dict || !frm.fields_dict.items || !frm.fields_dict.items.grid) {
			return;
		}
		ps_enforce_planning_sheet_grids(frm);
		if (typeof planning_sheet_apply_stock_grid_ui === 'function') {
			planning_sheet_apply_stock_grid_ui(frm);
		}
	};
	const wait = delay != null ? delay : 80;
	const gc = ps_get_grid_columns_module();
	if (gc && typeof gc.debounce === 'function') {
		gc.debounce(frm, 'ps_enforce_grids', run, wait);
		return;
	}
	setTimeout(run, wait);
}

production_entry.planning_sheet_process_grid = {
	apply: apply_process_code_visibility,
	apply_both: ps_apply_both_grids,
	enforce: ps_enforce_planning_sheet_grids,
	schedule: schedule_apply_process_code_visibility,
	stabilize: ps_stabilize_planning_grids_after_refresh,
	after_reload: ps_after_planning_sheet_reload,
	ensure_rows: ps_ensure_both_grids_have_rows,
	install_guards: ps_install_grid_refresh_guards,
	item_process_prefix: ps_item_process_prefix,
	canonical_order: PS_CANONICAL_FABRIC_ORDER,
};
