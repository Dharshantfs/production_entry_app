/**
 * Planning Sheet child-grid columns by item_code process prefix.
 * Uses in_list_view only (via child_grid_columns.js) — never hidden=1 on data fields.
 */
frappe.provide('production_entry.planning_sheet_process_grid');

const PS_KNOWN_PREFIXES = new Set([
	'100', '102', '103', '104', '105', '106', '107', '108', '109', '110',
	'200', '201', '202', '203',
	'211', '212', '213', '214', '216', '217',
	'221', '222', '223', '224', '231', '233', '241', '242', '225', '226',
	'251', '252', '253', '254', '255',
]);

const PS_GRID_TABLE_FIELDS = ['items', 'planned_items'];

const PS_GRID_META_BY_FIELD = {
	items: 'Planning sheet Item',
	planned_items: 'Planning Table',
};

/** Always visible — never toggle off. */
const PS_CORE_GRID_FIELDS = new Set(['item_code', 'item_name', 'qty', 'uom', 'unit']);

/** Fabric 100 / 102 / 103 — canonical grid column order. */
const PS_ORDER_FABRIC_BASE = [
	'item_code', 'item_name', 'qty', 'uom', 'gsm', 'quality', 'color', 'width_inch', 'unit',
	'planned_date', 'custom_parent_child_trace_id', 'custom_parent_fabric',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
];

const PS_FIELD_ORDER_BY_PROCESS = {
	100: PS_ORDER_FABRIC_BASE,
	102: PS_ORDER_FABRIC_BASE,
	103: PS_ORDER_FABRIC_BASE,
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
};

const PS_BASE_FIELDS = [
	'item_code', 'item_name', 'qty', 'uom', 'unit',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'width_inch',
	'gsm', 'quality', 'color', 'custom_quality',
	'custom_parent_fabric', 'custom_parent_child_trace_id',
	'custom_item_planned_date', 'planned_date', 'custom_plan_code', 'plan_name',
	'custom_movement_type', 'order_sheet', 'spr_name',
];

const PS_PRINT_105_FIELDS = [
	'custom_design_code', 'custom_design_name', 'custom_design_colour',
	'custom_design_attachment', 'custom_printing_shift', 'custom_printing_arrangement_seq',
];

const PS_BOPP_STACK_FIELDS = [
	'custom_lam_gsm', 'custom_bopp_gsm', 'custom_finishing', 'custom_white_tint',
	'custom_design_code', 'custom_design_name', 'custom_design_colour',
	'custom_design_attachment', 'custom_lamination_shift',
	'custom_lam_side', 'custom_lam_side_',
];

const PS_SLITTING_FIELDS = ['custom_slitting_shift'];

const PS_SHEET_CUT_FIELDS = [
	'sheet_size', 'custom_no_of_sheets', 'custom_sheet_cutting_shift',
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
	logicalOrder.forEach((fn) => {
		const resolved = ps_resolve_field_for_table(table_fieldname, fn);
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
		PS_SLITTING_FIELDS.forEach((f) => out.add(f));
		return out;
	}
	if (code === '251' || code === '252' || code === '253' || code === '254') {
		PS_SHEET_CUT_FIELDS.forEach((f) => out.add(f));
		PS_PRINT_105_FIELDS.forEach((f) => out.add(f));
		if (code === '253' || code === '254') {
			out.add('custom_lam_gsm');
			out.add('custom_bopp_gsm');
		}
		return out;
	}
	if (
		code === '200' || code === '201' || code === '202' || code === '203'
		|| code === '211' || code === '212' || code === '213' || code === '214'
		|| code === '216' || code === '217'
		|| code === '221' || code === '222' || code === '223' || code === '224'
		|| code === '231' || code === '233' || code === '241' || code === '242'
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
	const fabricCodes = new Set(['100', '102', '103', '104', '105']);
	const activeFabric = Array.from(codes).filter((c) => fabricCodes.has(c));
	if (activeFabric.length) {
		return ps_merge_process_field_orders(activeFabric);
	}
	if (!codes.size) {
		return PS_ORDER_FABRIC_BASE.slice();
	}
	const allowed = new Set();
	codes.forEach((code) => {
		ps_fields_for_process(code).forEach((f) => allowed.add(f));
	});
	return Array.from(allowed);
}

function ps_build_show_fieldnames(frm, table_fieldname) {
	const logicalOrder = ps_build_logical_field_order(frm);
	const codes = ps_collect_active_process_codes(frm);
	const fabricOnly = !codes.size || Array.from(codes).every((c) => PS_FIELD_ORDER_BY_PROCESS[c]);
	if (fabricOnly) {
		return ps_resolve_order_for_table(table_fieldname, logicalOrder);
	}
	const metaDoctype = PS_GRID_META_BY_FIELD[table_fieldname];
	const allowed = new Set();
	Array.from(codes).forEach((code) => {
		ps_fields_for_process(code).forEach((f) => allowed.add(f));
	});
	if (!codes.size) {
		PS_BASE_FIELDS.forEach((f) => allowed.add(f));
	}
	PS_CORE_GRID_FIELDS.forEach((f) => allowed.add(f));
	const showSet = {};
	Array.from(allowed).forEach((fn) => {
		const resolved = ps_resolve_field_for_table(table_fieldname, fn);
		if (frappe.meta.get_docfield(metaDoctype, resolved)) {
			showSet[resolved] = 1;
		}
	});
	const gc = ps_get_grid_columns_module();
	if (gc && typeof gc.ordered_show_fields === 'function') {
		const ordered = gc.ordered_show_fields(metaDoctype, showSet, Object.keys(showSet));
		return ordered.length ? ordered : ps_resolve_order_for_table(table_fieldname, PS_ORDER_FABRIC_BASE);
	}
	return Object.keys(showSet);
}

function ps_wrap_planning_grids(frm) {
	if (!frm || !frm.fields_dict) {
		return;
	}
	PS_GRID_TABLE_FIELDS.forEach((tableField) => {
		const fd = frm.fields_dict[tableField];
		if (fd && fd.$wrapper && fd.$wrapper.length) {
			fd.$wrapper.addClass('ps-grid-wrap');
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
	gc.apply(frm, tableFieldname, metaDoctype, showFields);
}

function apply_process_code_visibility(frm) {
	if (!frm || !frm.fields_dict || frm._ps_applying_grid_visibility) {
		return;
	}
	frm._ps_applying_grid_visibility = true;
	try {
		ps_wrap_planning_grids(frm);
		PS_GRID_TABLE_FIELDS.forEach((t) => ps_apply_grid_columns(frm, t));
	} catch (e) {
		if (typeof console !== 'undefined' && console.warn) {
			console.warn('apply_process_code_visibility failed', e);
		}
	} finally {
		frm._ps_applying_grid_visibility = false;
	}
}

function schedule_apply_process_code_visibility(frm, delay) {
	if (!frm) {
		return;
	}
	const gc = ps_get_grid_columns_module();
	const run = function () {
		if (!frm.fields_dict || !frm.fields_dict.items || !frm.fields_dict.items.grid) {
			return;
		}
		apply_process_code_visibility(frm);
		if (typeof planning_sheet_apply_stock_grid_ui === 'function') {
			planning_sheet_apply_stock_grid_ui(frm);
		}
	};
	if (gc && typeof gc.debounce === 'function') {
		gc.debounce(frm, 'ps_visibility', run, delay != null ? delay : 120);
		return;
	}
	setTimeout(run, delay != null ? delay : 120);
}

production_entry.planning_sheet_process_grid = {
	apply: apply_process_code_visibility,
	schedule: schedule_apply_process_code_visibility,
	item_process_prefix: ps_item_process_prefix,
};
