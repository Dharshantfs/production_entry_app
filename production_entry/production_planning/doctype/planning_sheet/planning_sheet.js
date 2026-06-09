const PS_KNOWN_PREFIXES = new Set([
	'100', '102', '103', '104', '105', '106', '107', '108', '109', '110',
	'200', '201', '202', '203',
	'211', '212', '213', '214', '216', '217',
	'221', '222', '223', '224', '231', '233', '241', '242', '225', '226',
	'251', '252', '253', '254', '255',
]);

/** Always visible in grid list view — never use hidden=1 (breaks header/body alignment). */
const PS_CORE_GRID_FIELDS = new Set([
	'item_code', 'item_name', 'qty', 'uom', 'unit',
]);

const PS_BASE_FIELDS = [
	'meter', 'meter_per_roll', 'no_of_rolls', 'weight_per_roll', 'width_inch',
	'gsm', 'quality', 'color', 'custom_quality',
	'custom_parent_fabric', 'custom_parent_child_trace_id',
	'custom_item_planned_date', 'planned_date', 'custom_plan_code', 'plan_name',
	'custom_movement_type', 'so_item', 'sales_order_item',
	'total_weight', 'warehouse', 'allocated_to_unit', 'work_order',
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
	if (!ic) return '';
	if (ic.toUpperCase().startsWith('PB') || ic.toUpperCase().startsWith('PB-')) {
		return 'PB';
	}
	if (ic.indexOf('-') >= 0) {
		const segments = ic.split('-');
		for (let i = 0; i < segments.length; i += 1) {
			const segDigits = segments[i].replace(/\D/g, '');
			if (segDigits.length >= 3) {
				const sp = segDigits.substring(0, 3);
				if (PS_KNOWN_PREFIXES.has(sp)) return sp;
			}
		}
	}
	const m = ic.match(/^(\d{3})/);
	if (m && PS_KNOWN_PREFIXES.has(m[1])) return m[1];
	return '';
}

function ps_fields_for_process(code) {
	const out = new Set(PS_BASE_FIELDS);
	if (!code || code === 'PB') {
		if (code === 'PB') {
			PS_PB_FIELDS.forEach((f) => out.add(f));
		}
		return out;
	}
	if (code === '100' || code === '102' || code === '103') {
		return out;
	}
	if (code === '104') {
		PS_LAM_104_FIELDS.forEach((f) => out.add(f));
		return out;
	}
	if (code === '105') {
		PS_PRINT_105_FIELDS.forEach((f) => out.add(f));
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

function ps_build_allowed_fieldnames(frm) {
	const allowed = new Set(PS_CORE_GRID_FIELDS);
	const codes = ps_collect_active_process_codes(frm);
	if (!codes.size) {
		PS_BASE_FIELDS.forEach((f) => allowed.add(f));
		return allowed;
	}
	codes.forEach((code) => {
		ps_fields_for_process(code).forEach((f) => allowed.add(f));
	});
	return allowed;
}

function ps_apply_grid_columns(frm, table_fieldname) {
	const fd = frm.fields_dict[table_fieldname];
	if (!fd || !fd.grid) return;
	const grid = fd.grid;
	const metaDoctype = grid.doctype;
	const allowed = ps_build_allowed_fieldnames(frm);

	(frappe.meta.get_docfields(metaDoctype) || []).forEach((df) => {
		if (!df || df.fieldtype === 'Column Break' || df.fieldtype === 'Section Break') {
			return;
		}
		const show = PS_CORE_GRID_FIELDS.has(df.fieldname) || allowed.has(df.fieldname);
		try {
			grid.update_docfield_property(df.fieldname, 'hidden', 0);
			grid.update_docfield_property(df.fieldname, 'in_list_view', show ? 1 : 0);
		} catch (e) {
			/* ignore */
		}
	});

	try {
		if (grid.visible_columns) delete grid.visible_columns;
	} catch (e) {
		/* ignore */
	}
	if (typeof grid.setup_visible_columns === 'function') {
		grid.setup_visible_columns();
	}
	if (typeof grid.refresh_header === 'function') {
		grid.refresh_header();
	}
	try {
		if (typeof grid.refresh === 'function') {
			grid.refresh();
		}
	} catch (e) {
		/* ignore */
	}
}

function apply_process_code_visibility(frm) {
	if (!frm || !frm.fields_dict) return;
	['items', 'planned_items'].forEach((t) => ps_apply_grid_columns(frm, t));
}

frappe.ui.form.on('Planning sheet', {
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
		setTimeout(() => apply_process_code_visibility(frm), 100);
	},

	onload_post_render(frm) {
		setTimeout(() => apply_process_code_visibility(frm), 200);
	},

	validate(frm) {
		apply_process_code_visibility(frm);
	},

	items_add(frm) {
		setTimeout(() => apply_process_code_visibility(frm), 50);
	},
	items_remove(frm) {
		setTimeout(() => apply_process_code_visibility(frm), 50);
	},
	planned_items_add(frm) {
		setTimeout(() => apply_process_code_visibility(frm), 50);
	},
	planned_items_remove(frm) {
		setTimeout(() => apply_process_code_visibility(frm), 50);
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
