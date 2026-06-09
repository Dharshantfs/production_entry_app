const PS_KNOWN_PREFIXES = new Set([
	'100', '102', '103', '104', '105', '106', '107', '108', '109', '110',
	'200', '201', '202', '203',
	'211', '212', '213', '214', '216', '217',
	'221', '222', '223', '224', '231', '233', '241', '242', '225', '226',
	'251', '252', '253', '254', '255',
]);

const PS_GRID_META_BY_FIELD = {
	items: 'Planning sheet Item',
	planned_items: 'Planning Table',
};

/** Fabric 100 / 102 / 103 — canonical grid column order. */
const PS_ORDER_FABRIC_BASE = [
	'item_code', 'item_name', 'qty', 'uom', 'gsm', 'quality', 'color', 'width_inch', 'unit',
	'planned_date', 'custom_parent_child_trace_id', 'custom_parent_fabric',
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'order_sheet', 'spr_name',
];

/** Explicit grid column order per process code (logical field keys; resolved per child table). */
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
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'width_inch',
	'gsm', 'quality', 'color', 'custom_quality',
	'custom_parent_fabric', 'custom_parent_child_trace_id',
	'custom_item_planned_date', 'planned_date', 'custom_plan_code', 'plan_name',
	'custom_movement_type', 'so_item', 'sales_order_item',
	'total_weight', 'warehouse', 'allocated_to_unit', 'work_order', 'order_sheet', 'spr_name',
];

const PS_LAM_104_FIELDS = [
	'custom_lam_gsm', 'custom_lam_side', 'custom_lam_side_',
	'custom_lamination_order_code', 'custom_lamination_order_code_',
	'custom_lamination_shift',
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
		// Design-prefixed 105/106 FG (e.g. 6003-1051131811201395) — match server _item_process_prefix.
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
		if (p) codes.add(p);
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
	// Other processes: union fields, keep meta field_order via child_grid_columns fallback.
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
	// Non-fabric processes: allowed set + meta field_order (legacy).
	const metaDoctype = PS_GRID_META_BY_FIELD[table_fieldname];
	const allowed = new Set();
	Array.from(codes).forEach((code) => {
		ps_fields_for_process(code).forEach((f) => allowed.add(f));
	});
	if (!codes.size) {
		PS_BASE_FIELDS.forEach((f) => allowed.add(f));
	}
	const showSet = {};
	Array.from(allowed).forEach((fn) => {
		const resolved = ps_resolve_field_for_table(table_fieldname, fn);
		if (frappe.meta.get_docfield(metaDoctype, resolved)) {
			showSet[resolved] = 1;
		}
	});
	const gc = production_entry && production_entry.grid_columns;
	if (gc && typeof gc.ordered_show_fields === 'function') {
		return gc.ordered_show_fields(metaDoctype, showSet);
	}
	return Object.keys(showSet);
}

function ps_apply_grid_columns(frm, table_fieldname) {
	const metaDoctype = PS_GRID_META_BY_FIELD[table_fieldname];
	const gc = production_entry && production_entry.grid_columns;
	if (!metaDoctype || !gc || typeof gc.apply !== 'function') {
		return;
	}
	const showFields = ps_build_show_fieldnames(frm, table_fieldname);
	gc.apply(frm, table_fieldname, metaDoctype, showFields);
}

function apply_process_code_visibility(frm) {
	if (!frm || !frm.fields_dict) {
		return;
	}
	['items', 'planned_items'].forEach((t) => ps_apply_grid_columns(frm, t));
}

function schedule_apply_process_code_visibility(frm, delay) {
	const gc = production_entry && production_entry.grid_columns;
	if (gc && typeof gc.debounce === 'function') {
		gc.debounce(frm, 'ps_visibility', () => apply_process_code_visibility(frm), delay);
		return;
	}
	setTimeout(() => apply_process_code_visibility(frm), delay != null ? delay : 80);
}

frappe.ui.form.on('Planning sheet', {
	onload(frm) {
		apply_process_code_visibility(frm);
	},

	refresh(frm) {
		apply_process_code_visibility(frm);
		if (!frm.is_new()) {
			frm.add_custom_button(__('Meter to Kgs (All Bag BOM)'), function () {
				frappe.call({
					method: 'production_entry.production_planning.scheduler_api.convert_meter_to_kgs_for_box_bag_bom',
					args: { planning_sheet_name: frm.doc.name },
					freeze: true,
					callback(r) {
						if (!r.exc) {
							const msg = r.message || {};
							frappe.show_alert({
								message: __('Converted {0} line(s).', [msg.updated || 0]),
								indicator: 'green',
							});
							if (msg.warning) {
								frappe.msgprint({
									title: __('Meter to Kg'),
									message: msg.warning,
									indicator: 'orange',
								});
							}
							frm.reload_doc();
						}
					},
				});
			}, __('Actions'));
			if (typeof register_planning_sheet_stock_check_button === 'function') {
				register_planning_sheet_stock_check_button(frm);
			}
		}
		schedule_apply_process_code_visibility(frm, 100);
	},

	onload_post_render(frm) {
		schedule_apply_process_code_visibility(frm, 0);
	},

	validate(frm) {
		apply_process_code_visibility(frm);
	},

	items_add(frm) {
		schedule_apply_process_code_visibility(frm, 50);
	},
	items_remove(frm) {
		schedule_apply_process_code_visibility(frm, 50);
	},
	planned_items_add(frm) {
		schedule_apply_process_code_visibility(frm, 50);
	},
	planned_items_remove(frm) {
		schedule_apply_process_code_visibility(frm, 50);
	},

	/** Legacy hook name used by planning_sheet_custom.js */
	toggle_221_fields(frm) {
		apply_process_code_visibility(frm);
	},
});

function trigger_toggle(frm, cdt, cdn) {
	apply_process_code_visibility(frm);
	if (cdt && cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (row.item_code && (
			row.item_code.includes('-221') || row.item_code.startsWith('221')
			|| row.item_code.includes('-224') || row.item_code.startsWith('224')
			|| row.item_code.includes('-222') || row.item_code.startsWith('222')
			|| row.item_code.includes('-223') || row.item_code.startsWith('223')
			|| row.item_code.includes('-211') || row.item_code.startsWith('211')
			|| row.item_code.includes('-212') || row.item_code.startsWith('212')
			|| row.item_code.includes('-213') || row.item_code.startsWith('213')
			|| row.item_code.includes('-231') || row.item_code.startsWith('231')
			|| row.item_code.includes('-233') || row.item_code.startsWith('233')
			|| row.item_code.includes('-241') || row.item_code.startsWith('241')
			|| row.item_code.includes('-242') || row.item_code.startsWith('242')
		)) {
			const parts = row.item_code.split('-');
			if (parts.length > 1) {
				const dc = parts[0];
				if (row.custom_design_code !== dc) {
					frappe.model.set_value(cdt, cdn, 'custom_design_code', dc);
				} else {
					fetch_design_name(frm, cdt, cdn);
				}
			}
		}
	}
}

function fetch_design_name(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	if (row.custom_design_code) {
		frappe.call({
			method: 'production_entry.production_planning.scheduler_api._design_master_extra_fields',
			args: { design_code: row.custom_design_code },
			callback(r) {
				if (r.message && r.message.custom_design_name) {
					frappe.model.set_value(cdt, cdn, 'custom_design_name', r.message.custom_design_name);
				}
			},
		});
	}
}

frappe.ui.form.on('Planning sheet Item', {
	item_code: trigger_toggle,
	custom_design_code: fetch_design_name,
});

frappe.ui.form.on('Planning Table', {
	item_code: trigger_toggle,
	custom_design_code: fetch_design_name,
});
