const SPR_DEBUG_LOGS = false;
function sprLog() {
	if (!SPR_DEBUG_LOGS || !window.console || !console.log) return;
	console.log.apply(console, arguments);
}

/** Net weight (kg) to 2 decimals — matches roll line precision, manual sums, and Total Produced Weight. */
function spr_round_net_weight_kg(v) {
	return Math.round(flt(v) * 100) / 100;
}

/** Child tables on SPR that must keep header/body columns aligned after show/hide or save. */
const SPR_SPR_CHILD_TABLE_FIELDS = ['items', 'shaft_jobs', 'bundle_calculation'];

/** Process 100 roll results: default visible grid columns (no manual column picker each Create Entry). */
const SPR_FABRIC100_ITEMS_GRID_SHOW = [
	'work_order',
	'item_code',
	'batch_no',
	'party_code',
	'quality',
	'color',
	'gsm',
	'planned_qty',
	'meter_roll',
	'produced_length_mtrs',
	'width_inch',
	'custom_core_width_mm',
	'core_width',
	'custom_diameter_inches',
	'diameter',
	'net_weight',
	'gross_weight',
	'produced_gsm',
	'save_row',
	'print_sticker',
	'edit_row',
];

const SPR_FABRIC100_ITEMS_GRID_HIDE = [
	'item_name',
	'job',
	'roll_no',
	'uom',
	'custom_cbm_cubic_meters',
	'cbm',
	'custom_polybag_kgs',
	'polybag_kgs',
	'row_ready_for_print',
	'row_locked',
	'row_printed',
	'custom_fabric_gsm',
	'custom_lam_gsm',
	'custom_sheet_size',
	'custom_planned_sheets_pcs',
	'custom_total_produced_sheets',
	'custom_planned_bag_pcs',
	'custom_achieved_bag_pcs',
];

function spr_set_grid_col_hidden(grid, fieldname, hidden) {
	if (!grid || !fieldname) {
		return;
	}
	const hideVal = hidden ? 1 : 0;
	try {
		if (typeof grid.update_docfield_property === 'function') {
			grid.update_docfield_property(fieldname, 'hidden', hideVal);
		}
	} catch (e) {
		/* ignore */
	}
}

/** Keep grid header horizontally aligned with body when DataTable scrolls or columns toggle. */
function spr_sync_grid_header_body_scroll(fd) {
	if (!fd || !fd.$wrapper || !fd.$wrapper.length) {
		return;
	}
	const $w = fd.$wrapper;
	const $bodyScroll = $w.find('.dt-scrollable, .form-grid .grid-body').first();
	const $head = $w.find('.grid-heading-row, .dt-row-header, .dt-header').first();
	if (!$bodyScroll.length || !$head.length) {
		return;
	}
	const sl = $bodyScroll.scrollLeft();
	if (Math.abs(($head.scrollLeft() || 0) - sl) > 0.5) {
		$head.scrollLeft(sl);
	}
}

/**
 * Sync header/body scroll and visible columns only — never call grid.refresh() here
 * (refresh inside refresh caused an infinite loop and froze the SPR form).
 */
function spr_sync_grid_columns_visible(frm, fieldname) {
	const fd = frm && frm.fields_dict && frm.fields_dict[fieldname];
	if (!fd || !fd.grid) {
		return;
	}
	const grid = fd.grid;
	try {
		if (grid.visible_columns) {
			grid.visible_columns = null;
		}

		// Force fields to be in list view right before setup_visible_columns
		if (fieldname === 'shaft_jobs') {
			const jobFields = ['job_id', 'gsm', 'quality', 'combination', 'total_width', 'meter_roll_mtrs', 'net_weight', 'total_weight', 'custom_total_achieved_weight', 'custom_total_achieved_meter', 'no_of_shafts', 'no_of_rolls', 'party_code', 'work_orders', 'is_manual', 'manual_items', 'create_roll_entry'];
			jobFields.forEach(f => {
				let df = frappe.meta.get_docfield('Shaft Production Run Job', f);
				if (df) df.in_list_view = 1;
			});
		} else if (fieldname === 'bundle_calculation') {
			const cfg = spr_get_bundle_list_view_config(frm);
			cfg.show.forEach(function (f) {
				const df = frappe.meta.get_docfield('Bundle Calculation', f);
				if (df) {
					df.in_list_view = 1;
				}
				try {
					grid.update_docfield_property(f, 'hidden', 0);
					grid.update_docfield_property(f, 'in_list_view', 1);
				} catch (e) {
					/* ignore */
				}
			});
			cfg.hide.forEach(function (f) {
				const df = frappe.meta.get_docfield('Bundle Calculation', f);
				if (df) {
					df.in_list_view = 0;
				}
				try {
					grid.update_docfield_property(f, 'hidden', 1);
					grid.update_docfield_property(f, 'in_list_view', 0);
				} catch (e) {
					/* ignore */
				}
			});
		} else if (fieldname === 'items') {
			const cfg = spr_get_items_list_view_config(frm);
			cfg.show.forEach(function (f) {
				const df = frappe.meta.get_docfield('Shaft Production Run Item', f);
				if (df) {
					df.in_list_view = 1;
				}
				try {
					grid.update_docfield_property(f, 'hidden', 0);
					grid.update_docfield_property(f, 'in_list_view', 1);
				} catch (e) {
					/* ignore */
				}
			});
			cfg.hide.forEach(function (f) {
				const df = frappe.meta.get_docfield('Shaft Production Run Item', f);
				if (df) {
					df.in_list_view = 0;
				}
				try {
					grid.update_docfield_property(f, 'hidden', 1);
					grid.update_docfield_property(f, 'in_list_view', 0);
				} catch (e) {
					/* ignore */
				}
			});
		}

		if (typeof grid.setup_visible_columns === 'function') {
			grid.setup_visible_columns();
		}
		spr_sync_grid_header_body_scroll(fd);
		const $w = fd.$wrapper;
		if ($w && $w.length && !$w.data('spr-scroll-sync')) {
			$w.data('spr-scroll-sync', 1);
			$w.on('scroll.sprGridAlign', '.dt-scrollable, .form-grid .grid-body', function () {
				spr_sync_grid_header_body_scroll(fd);
			});
		}
	} catch (e) {
		/* ignore desk variants */
	}
}

/** Debounced GSM row colours + light column sync (safe after save / create entry / grid render). */
function spr_schedule_grid_ui_debounced(frm, opts) {
	if (!frm) {
		return;
	}
	const settings = opts || {};
	if (frm._spr_ui_debounce_timer) {
		clearTimeout(frm._spr_ui_debounce_timer);
	}
	frm._spr_ui_debounce_timer = setTimeout(function () {
		frm._spr_ui_debounce_timer = null;
		if (!frm.fields_dict || !frm.fields_dict.items) {
			return;
		}
		if (settings.styles !== false) {
			apply_spr_item_row_styles(frm);
		}
		if (settings.columns !== false) {
			SPR_SPR_CHILD_TABLE_FIELDS.forEach(function (fn) {
				spr_sync_grid_columns_visible(frm, fn);
			});
		}
	}, settings.delay != null ? settings.delay : 220);
}

function spr_after_child_table_refresh(frm) {
	spr_schedule_grid_ui_debounced(frm, { delay: 380 });
	if (typeof requestAnimationFrame === 'function') {
		requestAnimationFrame(function () {
			requestAnimationFrame(function () {
				if (!frm || !frm.fields_dict) {
					return;
				}
				SPR_SPR_CHILD_TABLE_FIELDS.forEach(function (fn) {
					spr_sync_grid_columns_visible(frm, fn);
				});
			});
		});
	}
}

/** When PP / operator selects a unit, default the matching process checkbox on (still user-clearable). */
function sprApplyLaminationUnitDefaults(frm, unitVal) {
	if (!frm || !frm.doc) {
		return;
	}
	const u = (unitVal != null ? String(unitVal) : String(frm.doc.custom_unit || '')).trim();
	const meta = frappe.meta;
	const hasField = (f) => !!meta.get_docfield('Shaft Production Run', f);
	if (u === 'TNSPL - LAMINATION UNIT' || u === 'Lamination Unit') {
		if (hasField('custom_is_lamination') && !cint(frm.doc.custom_is_lamination)) {
			frm.set_value('custom_is_lamination', 1);
		}
	} else if (u === 'TSNPL - L3 REWINDING MACHINE' || u === 'JSB - L4 REWINDING MACHINE' || u === 'JSB - L5 REWINDING MACHINE') {
		if (hasField('custom_is_rewinding') && !cint(frm.doc.custom_is_rewinding)) {
			frm.set_value('custom_is_rewinding', 1);
		}
	} else if (u === 'JVE - SHEET CUTTING MACHINE') {
		if (hasField('custom_is_sheet_cutting') && !cint(frm.doc.custom_is_sheet_cutting)) {
			frm.set_value('custom_is_sheet_cutting', 1);
		}
	} else if (u === 'VR - 1200MM BOPP PRINTING MACHINE') {
		if (hasField('custom_is_bopp_film') && !cint(frm.doc.custom_is_bopp_film)) {
			frm.set_value('custom_is_bopp_film', 1);
		}
	}
}

function sprSumProducedLengthMeters(it) {
	if (!it) {
		return 0;
	}
	const aliases = [
		'produced_length_mtrs',
		'custom_produced_length_mtrs',
	];
	for (let i = 0; i < aliases.length; i++) {
		const v = flt(it[aliases[i]]);
		if (v > 0) {
			return v;
		}
	}
	return 0;
}

const SPR_LAM_GSM_SUFFIX_MAP = {
	A: 10,
	B: 12,
	B1: 13,
	C: 15,
	D: 20,
	E: 30,
	F: 13,
};

function sprRollProcessPrefix(frm) {
	if (!frm || !frm.doc) {
		return '';
	}
	const rows = frm.doc.items || [];
	for (let i = 0; i < rows.length; i++) {
		const code = String((rows[i] && rows[i].item_code) || '').trim().toUpperCase();
		if (!code) {
			continue;
		}
		if (code.startsWith('104') || code.startsWith('107')) {
			return code.substring(0, 3);
		}
		const m107 = code.match(/^[A-Z0-9]+-107(?=[A-Z0-9])/);
		if (m107) {
			return '107';
		}
		const m104 = code.match(/^[A-Z0-9]+-104(?=[A-Z0-9])/);
		if (m104) {
			return '104';
		}
		if (code.length >= 3) {
			const prefix = code.substring(0, 3);
			if (prefix === '100' || prefix === '104' || prefix === '107') {
				return prefix;
			}
		}
	}
	return '';
}

function sprStickerGsmFromItemCode(itemCode) {
	const code = ((itemCode || '') + '').trim();
	// Printed BOPP (PB-*) does not carry sticker GSM in numeric process-code slots.
	// Avoid deriving bogus GSM like "5" from arbitrary substrings.
	if (!code || code.toUpperCase().startsWith('PB')) {
		return 0;
	}
	// Parse only numeric process-style item codes (e.g. 104xxx..., 102xxx..., 251xxx...).
	if (!/^\d+$/.test(code)) {
		return 0;
	}
	if (code.length < 12) {
		return 0;
	}
	const n = parseInt(code.substring(9, 12), 10);
	return !isNaN(n) && n > 0 ? n : 0;
}

function spr_count_created_roll_lines(frm) {
	if (!frm || !frm.doc) {
		return 0;
	}
	return (frm.doc.items || []).filter((r) => String((r && r.item_code) || '').trim()).length;
}

function spr_sync_no_of_rolls_created(frm, opts) {
	if (!frm || !frm.doc) {
		return;
	}
	if (cint(frm.doc.docstatus) !== 0) {
		return;
	}
	if (!frappe.meta.get_docfield('Shaft Production Run', 'custom_no_of_rolls_created')) {
		return;
	}
	const settings = opts || {};
	const cnt = spr_count_created_roll_lines(frm);
	const cur = cint(frm.doc.custom_no_of_rolls_created || 0);
	if (cur === cnt) {
		return;
	}
	if (settings.silent) {
		frm.doc.custom_no_of_rolls_created = cnt;
		frm.refresh_field('custom_no_of_rolls_created');
	} else {
		frm.set_value('custom_no_of_rolls_created', cnt);
	}
}

function sprLaminationGsmFromItemCode(itemCode) {
	const code = ((itemCode || '') + '').trim().toUpperCase();
	if (!code || code.indexOf('-') === -1) {
		return 0;
	}
	const suffix = code.split('-').pop().trim();
	return SPR_LAM_GSM_SUFFIX_MAP[suffix] || 0;
}

function sprScheduleTotalProducedSync(frm, opts) {
	if (!frm) return;
	// Server validate() already syncs bundle/header totals on save — skip desk resync briefly to avoid dirty loop (blocks Submit).
	if (frm._spr_just_saved && Date.now() - frm._spr_just_saved < 4000) {
		return;
	}
	if (frm.__spr_total_sync_timer) {
		clearTimeout(frm.__spr_total_sync_timer);
	}
	frm.__spr_total_sync_timer = setTimeout(function () {
		if (sprIsBundlePackagingMode(frm)) {
			sprSyncBundleProducedSheets(frm, opts || {});
		}
		spr_sync_total_produced_weight(frm, opts || {});
		frm.__spr_total_sync_timer = null;
	}, 120);
}

function spr_assign_bundle_row_metric(br, fieldname, value, silent) {
	if (Math.abs(flt(br[fieldname]) - flt(value)) <= 1e-6) {
		return;
	}
	if (silent || !br.name) {
		br[fieldname] = flt(value);
		return;
	}
	frappe.model.set_value('Bundle Calculation', br.name, fieldname, flt(value));
}

/** Sum roll-line Produced Sheets / net weight into bundle rows; consumed mtrs into SPR header (sheet cutting). */
function sprSyncBundleProducedSheets(frm, opts) {
	if (!frm || !sprIsBundlePackagingMode(frm)) {
		return;
	}
	const bundles = frm.doc.bundle_calculation || [];
	if (!bundles.length) {
		return;
	}
	const items = frm.doc.items || [];
	bundles.forEach(function (br, idx) {
		const rowId = String(br.name || '').trim() || 'idx' + String(idx);
		const prefix = rowId + '::';
		const ic = String(br.item_code || '').trim();
		const wo = String(br.work_order || '').trim();
		const nBundles = cint(br.no_of_bundles);
		const nBoxes = cint(br.no_of_boxes);
		const nRows = sprIsBag(frm) && nBundles < 1 ? nBoxes : nBundles;
		let sumPcs = 0;
		let sumBagPcs = 0;
		let sumNw = 0;
		let prefixHits = 0;
		items.forEach(function (it) {
			const job = String(it.job || '');
			if (job.indexOf(prefix) === 0) {
				prefixHits += 1;
				sumPcs += flt(it.custom_total_produced_sheets);
				sumBagPcs += flt(it.custom_achieved_bag_pcs);
				sumNw += spr_round_net_weight_kg(it.net_weight);
			}
		});
		if (!prefixHits) {
			items.forEach(function (it) {
				if (String(it.item_code || '').trim() !== ic || String(it.work_order || '').trim() !== wo) {
					return;
				}
				const jn = parseInt(String(it.job || ''), 10);
				if (isNaN(jn)) {
					return;
				}
				if (nRows > 0 && (jn < 1 || jn > nRows)) {
					return;
				}
				sumPcs += flt(it.custom_total_produced_sheets);
				sumBagPcs += flt(it.custom_achieved_bag_pcs);
				sumNw += spr_round_net_weight_kg(it.net_weight);
			});
		}
		const silent = !!(opts && opts.silent);
		spr_assign_bundle_row_metric(br, 'total_produced_sheets', sumPcs, silent);
		spr_assign_bundle_row_metric(br, 'total_achieved_weight', sumNw, silent);
		if (frappe.meta.get_docfield('Bundle Calculation', 'total_produced_bag_pcs')) {
			spr_assign_bundle_row_metric(br, 'total_produced_bag_pcs', sumBagPcs, silent);
		}
	});
	let consumedHdr = 0;
	bundles.forEach(function (br) {
		consumedHdr += flt(br.total_consumed_meter);
	});
	if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_achieved_meter')) {
		const cur = flt(frm.doc.custom_total_achieved_meter);
		if (Math.abs(cur - consumedHdr) > 1e-6) {
			const silent = !!(opts && opts.silent);
			if (silent || cint(frm.doc.docstatus) !== 0) {
				frm.doc.custom_total_achieved_meter = consumedHdr;
				if (silent) {
					frm.refresh_field('custom_total_achieved_meter');
				}
			} else {
				frm.set_value('custom_total_achieved_meter', consumedHdr);
			}
		}
	}
	if (!(opts && opts.silent)) {
		frm.refresh_field('bundle_calculation');
	}
}

function sprRecalcBundlePlannedPcs(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}
	let tpb = 0;
	if (sprIsBag(frm)) {
		const nBoxes = cint(row.no_of_boxes);
		const pcs = cint(row.pcs_per_packet);
		if (nBoxes > 0 && pcs > 0) {
			tpb = nBoxes * pcs;
		} else {
			tpb = cint(row.pkts_per_bundle) * pcs;
		}
	} else {
		tpb = cint(row.pkts_per_bundle) * cint(row.pcs_per_packet);
	}
	frappe.model.set_value(cdt, cdn, 'total_pcs_per_bundle', tpb > 0 ? tpb : 0);
}

function sprAutoSaveAfterCreateEntry(frm) {
	if (!frm || frm.is_new() || frm.doc.docstatus !== 0) return;
	if (!frm.is_dirty || !frm.is_dirty()) return;
	// Debounce auto-save bursts when Create Entry appends many rows.
	if (frm.__spr_auto_save_timer) {
		clearTimeout(frm.__spr_auto_save_timer);
	}
	frm.__spr_auto_save_timer = setTimeout(function () {
		if (frm.__spr_auto_save_in_progress) return;
		if (!frm.is_dirty || !frm.is_dirty()) return;
		frm.__spr_auto_save_in_progress = true;
		const p = frm.save();
		if (p && typeof p.then === 'function') {
			p.then(function () {
				frm.__spr_auto_save_in_progress = false;
				spr_schedule_grid_ui_debounced(frm, { delay: 400 });
			}).catch(function (err) {
				frm.__spr_auto_save_in_progress = false;
				frappe.msgprint({
					title: __('Save failed'),
					indicator: 'red',
					message: err && err.message ? err.message : __('Could not save Shaft Production Run.'),
				});
			});
		} else {
			frm.__spr_auto_save_in_progress = false;
		}
		frm.__spr_auto_save_timer = null;
	}, 1200);
}

/** Sum job-level planned weights into header when shaft rows have explicit totals; keep PP/WO value when jobs are blank. */
function spr_sync_total_planned_qty_from_jobs(frm, opts) {
	if (!frm || !frm.doc) {
		return;
	}
	if (cint(frm.doc.docstatus) !== 0) {
		return;
	}
	if (!frappe.meta.get_docfield('Shaft Production Run', 'custom_total_planned_qty')) {
		return;
	}
	const settings = opts || {};
	const jobs = frm.doc.shaft_jobs || [];
	let sum = 0;
	let any = false;
	jobs.forEach(function (r) {
		const tw = flt(r.total_weight || r.total_weight_kgs || 0);
		if (tw > 0) {
			sum += tw;
			any = true;
		}
	});
	if (!any) {
		return;
	}
	const rounded = Math.round(sum * 100) / 100;
	const cur = flt(frm.doc.custom_total_planned_qty);
	if (Math.abs(cur - rounded) > 1e-6) {
		if (settings.silent) {
			frm.doc.custom_total_planned_qty = rounded;
			frm.refresh_field('custom_total_planned_qty');
		} else {
			frm.set_value('custom_total_planned_qty', rounded);
		}
	}
}

frappe.ui.form.on('Shaft Production Run', {
	setup: function (frm) {
		// Buttons registered in refresh — see spr_register_spr_page_buttons (Frappe skips duplicate labels if setup runs too early)
	},

	onload: function (frm) {
		function spr_onload_refresh_layout() {
			if (!frm || !frm.doc) {
				return;
			}
			sprToggleSheetCuttingUi(frm);
			sprToggleLaminationRollUi(frm);
			['shaft_jobs', 'items', 'bundle_stickers', 'bundle_calculation', 'fabric_batch_picks'].forEach(function (fld) {
				if (frm.fields_dict && frm.fields_dict[fld]) {
					try {
						frm.refresh_field(fld);
					} catch (e) {}
				}
			});
			spr_patch_items_grid_refresh(frm);
			spr_register_spr_page_buttons(frm);
			spr_inject_gsm_legend(frm);
			schedule_spr_item_row_styles(frm);
		}
		setTimeout(spr_onload_refresh_layout, 0);
		setTimeout(spr_onload_refresh_layout, 350);
		setTimeout(spr_onload_refresh_layout, 900);
		setTimeout(function () {
			sprEnsureBundleRowsFromPp(frm);
		}, 400);
		if (frm.doc && cint(frm.doc.docstatus) === 1) {
			spr_schedule_item_row_styles_after_doc_write(frm);
		}
	},

	production_plan: function (frm) {
		if (!frm.doc.production_plan) {
			if (frappe.meta.get_docfield('Shaft Production Run', 'company')) {
				frm.set_value('company', '');
			}
			frm.clear_table('shaft_jobs');
			frm.clear_table('bundle_calculation');
			frm.clear_table('items');
			frm.refresh_field('shaft_jobs');
			frm.refresh_field('bundle_calculation');
			frm.refresh_field('items');
			sprToggleSheetCuttingUi(frm);
			return;
		}

		// Do not keep old roll lines when switching PP (also blocks client scripts that fill later)
		frm.clear_table('items');
		frm.refresh_field('items');

		if (!frm.doc.run_date) {
			frm.set_value('run_date', frappe.datetime.get_today());
		}

		frappe.call({
			method:
				'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_production_plan_details',
			args: { production_plan: frm.doc.production_plan },
			callback: function (r) {
				const d = r.message || {};
				sprLog('[SPR] get_production_plan_details response:', d);
				sprLog('[SPR] response keys:', Object.keys(d));
				
				// Set all returned fields that exist on the form
				if (d.company && frappe.meta.get_docfield('Shaft Production Run', 'company')) {
					sprLog('[SPR] Setting company:', d.company);
					frm.set_value('company', d.company);
				}
				if (d.customer) {
					sprLog('[SPR] Setting customer:', d.customer);
					frm.set_value('customer', d.customer);
				}
				if (d.custom_unit) {
					sprLog('[SPR] Setting custom_unit:', d.custom_unit);
					frm.set_value('custom_unit', d.custom_unit);
					sprApplyLaminationUnitDefaults(frm, d.custom_unit);
				}
				if ('custom_order_code' in d) {
					sprLog('[SPR] Setting custom_order_code:', d.custom_order_code);
					frm.set_value('custom_order_code', d.custom_order_code || '');
				}
				if ('custom_label' in d) {
					sprLog('[SPR] Setting custom_label:', d.custom_label);
					frm.set_value('custom_label', d.custom_label || '');
				}
				if ('custom_total_planned_qty' in d) {
					sprLog('[SPR] Setting custom_total_planned_qty:', d.custom_total_planned_qty);
					frm.set_value('custom_total_planned_qty', flt(d.custom_total_planned_qty || 0));
				}
				if ('custom_total_planned_pcs' in d && frappe.meta.get_docfield('Shaft Production Run', 'custom_total_planned_pcs')) {
					frm.set_value('custom_total_planned_pcs', flt(d.custom_total_planned_pcs || 0));
				}
				if (d.custom_is_sheet_cutting) {
					frm.set_value('custom_is_sheet_cutting', 1);
				}
				if (d.custom_is_box_bag) {
					frm.set_value('custom_is_box_bag', 1);
				}
				sprToggleSheetCuttingUi(frm);
				if (sprIsBundlePackagingMode(frm) || (d.bundle_rows && d.bundle_rows.length)) {
					sprLoadBundleCalculationFromPp(frm, d.bundle_rows);
				} else {
					sprLoadShaftJobsFromPp(frm);
				}
				// Note: custom_party_code is only in the child table, not the header, so don't set it here
			},
		});
	},

	custom_unit: function (frm) {
		sprApplyLaminationUnitDefaults(frm);
		sprToggleLaminationRollUi(frm);
		sprToggleSheetCuttingUi(frm);
	},
	custom_is_sheet_cutting: function (frm) {
		sprToggleSheetCuttingUi(frm);
	},
	custom_is_box_bag: function (frm) {
		sprToggleSheetCuttingUi(frm);
		if (sprIsBag(frm) && frm.doc.production_plan && !(frm.doc.bundle_calculation || []).length) {
			sprLoadBundleCalculationFromPp(frm, null);
		}
	},
	custom_is_lamination: function (frm) {
		sprToggleLaminationRollUi(frm);
		schedule_spr_item_row_styles(frm);
	},

	refresh: function (frm) {
		// Enforce read-only UI controls dynamically since we removed them from JSON to allow backend save
		try {
			frm.set_df_property('company', 'read_only', 1);
		} catch (e) {
			/* field may not exist until migrate */
		}
		frm.set_df_property('total_produced_weight', 'read_only', 1);
		try {
			frm.set_df_property('custom_total_achieved_meter', 'read_only', 1);
		} catch (e) {
			/* field may not exist until migrate */
		}
		try {
			frm.set_df_property('net_weight', 'precision', 2, null, 'items');
		} catch (e) {
			/* ignore desk variants */
		}

		sprLog('[SPR REFRESH] === REFRESH HOOK START ===');
		
		spr_sync_total_planned_qty_from_jobs(frm, { silent: true });
		sprLog('[SPR REFRESH] After total_planned_qty sync');
		spr_sync_no_of_rolls_created(frm, { silent: true });
		
		sprScheduleTotalProducedSync(frm, { silent: true });
		sprLog('[SPR REFRESH] After total_produced_weight sync (scheduled)');
		try {
			update_shaft_job_achieved_from_items(frm);
		} catch (e) {
			/* ignore */
		}
		sprToggleLaminationRollUi(frm);
		sprToggleSheetCuttingUi(frm);
		if (
			sprIsBundlePackagingMode(frm) &&
			frm.doc.production_plan &&
			!(frm.doc.bundle_calculation || []).length &&
			(!frm.is_dirty || !frm.is_dirty())
		) {
			sprLoadBundleCalculationFromPp(frm, null);
		}
		spr_apply_fabric100_item_grid_columns(frm);

		spr_patch_items_grid_refresh(frm);
		spr_register_spr_page_buttons(frm);
		
		// Keep one lightweight retry only (old code had 4 retries, causing UI lag on large grids).
		setTimeout(function () {
			sprScheduleTotalProducedSync(frm, { silent: true });
		}, 400);
		
		setTimeout(function () {
			spr_register_spr_page_buttons(frm);
		}, 700);
		
		spr_inject_gsm_legend(frm);
		spr_hide_duplicate_produced_gsm_columns(frm);
		spr_schedule_grid_ui_debounced(frm, { delay: 280 });
		
		sprLog('[SPR REFRESH] === REFRESH HOOK END ===');
	},

	before_submit: function (frm) {
		if (!frm || !frm.doc) {
			return;
		}
		if (cint(frm.doc.docstatus) !== 0) {
			return;
		}
		// Bag / sheet-cutting bundle runs post PCS (not kg) — skip net-weight tolerance gate.
		if (sprIsBag(frm) || sprIsSheetCutting(frm)) {
			return;
		}
		if (!frappe.meta.get_docfield('Shaft Production Run', 'tolerance_override_approved')) {
			return;
		}
		const violations = spr_collect_planned_tolerance_violations(frm);
		if (!violations.length) {
			return;
		}
		if (cint(frm.doc.tolerance_override_approved) && (frm.doc.tolerance_override_reason || '').trim()) {
			return;
		}
		frappe.validated = false;
		if (window.sprTolDialogOpen) {
			return;
		}
		spr_show_tolerance_override_dialog(frm, violations, { forSubmit: true });
	},

	after_save: function (frm) {
		frm._spr_just_saved = Date.now();
		spr_register_spr_page_buttons_after_save(frm);
		spr_sync_no_of_rolls_created(frm, { silent: true });
		spr_schedule_grid_ui_debounced(frm, { delay: 200 });
	},

	on_submit: function (frm) {
		spr_schedule_grid_ui_debounced(frm, { delay: 200 });
		if (frm.doc && frm.doc.production_plan) {
			frappe.call({
				method:
					'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_resync_production_plan_progress',
				args: { production_plan: frm.doc.production_plan },
				freeze: false,
			});
		}
	},

	items: {
		items_add: function (frm) {
			sprLog('[SPR DEBUG] items_add fired');
			spr_sync_no_of_rolls_created(frm);
			update_shaft_job_achieved_from_items(frm);
			sprLog('[SPR DEBUG] items_add: schedule total_produced_weight sync with', (frm.doc.items || []).length, 'items');
			sprScheduleTotalProducedSync(frm);
			schedule_spr_item_row_styles(frm);
		},
		items_remove: function (frm) {
			spr_sync_no_of_rolls_created(frm);
			update_shaft_job_achieved_from_items(frm);
			schedule_spr_item_row_styles(frm);
		},
	},
});

/** Allowed deviation of roll net/gross vs planned_qty (%). Match server `spr_net_weight_tolerance_percent` in site_config (default 5). */
function spr_net_weight_tolerance_percent() {
	return 5.0;
}

function spr_effective_roll_weight_kg(row) {
	if (!row) {
		return 0;
	}
	let w = flt(row.net_weight);
	if (w > 0) {
		return w;
	}
	return flt(row.gross_weight);
}

function spr_collect_planned_tolerance_violations(frm) {
	const tol = spr_net_weight_tolerance_percent();
	if (!(tol > 0)) {
		return [];
	}
	if (!frappe.meta.get_docfield('Shaft Production Run Item', 'planned_qty')) {
		return [];
	}
	const out = [];
	(frm.doc.items || []).forEach(function (row) {
		const pq = flt(row.planned_qty);
		if (!(pq > 0)) {
			return;
		}
		const act = spr_effective_roll_weight_kg(row);
		if (!(act > 0)) {
			return;
		}
		const dev_pct = (Math.abs(act - pq) / pq) * 100;
		if (dev_pct > tol + 1e-9) {
			out.push({
				job: row.job,
				roll_no: row.roll_no,
				planned: pq,
				actual: act,
				dev_pct: dev_pct,
			});
		}
	});
	return out;
}

function spr_escape_html(s) {
	return String(s === undefined || s === null ? '' : s)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

function spr_show_tolerance_override_dialog(frm, violations, opts) {
	opts = opts || {};
	const forSubmit = !!opts.forSubmit;
	window.sprTolDialogOpen = true;
	const tol = spr_net_weight_tolerance_percent();
	const rows = violations
		.map(function (v) {
			return (
				'<tr><td>' +
				spr_escape_html(v.job) +
				'</td><td>' +
				spr_escape_html(v.roll_no != null && v.roll_no !== '' ? v.roll_no : '—') +
				'</td><td class="text-right">' +
				flt(v.planned).toFixed(2) +
				'</td><td class="text-right">' +
				flt(v.actual).toFixed(2) +
				'</td><td class="text-right">' +
				flt(v.dev_pct).toFixed(2) +
				'%</td></tr>'
			);
		})
		.join('');
	const html =
		'<p class="text-muted">' +
		__(
			forSubmit
				? 'Allowed deviation: &plusmn;{0}%. Enter a reason and confirm approval to submit, or adjust roll weights.'
				: 'Allowed deviation: &plusmn;{0}%. Enter a reason and confirm approval to save, or adjust roll weights.',
			[tol]
		) +
		'</p><table class="table table-bordered table-condensed" style="font-size:12px;"><thead><tr><th>' +
		__('Job') +
		'</th><th>' +
		__('Roll') +
		'</th><th>' +
		__('Planned (Kg)') +
		'</th><th>' +
		__('Net/Gross (Kg)') +
		'</th><th>' +
		__('Variance') +
		'</th></tr></thead><tbody>' +
		rows +
		'</tbody></table>';

	const d = new frappe.ui.Dialog({
		title: __('Tolerance — approval required'),
		onhide: function () {
			window.sprTolDialogOpen = false;
		},
		fields: [
			{ fieldname: 'h', fieldtype: 'HTML', options: html },
			{
				fieldname: 'reason',
				fieldtype: 'Small Text',
				label: __('Reason for override'),
				reqd: 1,
			},
			{
				fieldname: 'approved',
				fieldtype: 'Check',
				label: __('I approve this deviation'),
				default: 0,
			},
		],
		primary_action_label: forSubmit ? __('Submit with approval') : __('Save with approval'),
		primary_action: function () {
			const reason = (d.get_value('reason') || '').trim();
			if (!reason) {
				frappe.msgprint(__('Reason is required.'));
				return;
			}
			if (!cint(d.get_value('approved'))) {
				frappe.msgprint(__('Confirm approval to continue.'));
				return;
			}
			d.hide();
			frm.set_value('tolerance_override_reason', reason);
			frm.set_value('tolerance_override_approved', 1);
			if (forSubmit) {
				frm.save('Submit');
			} else {
				frm.save();
			}
		},
	});
	d.show();
}

function spr_open_fabric_batch_pick_dialog(frm) {
	if (!frm || frm.is_new()) {
		frappe.msgprint(__('Save the SPR first, then select fabric batches.'));
		return;
	}
	if (cint(frm.doc.docstatus) !== 0) {
		frappe.msgprint(__('This SPR is submitted. Fabric batch picks cannot be changed.'));
		return;
	}
	if (!frappe.meta.get_docfield('Shaft Production Run', 'fabric_batch_picks')) {
		frappe.msgprint(
			__(
				'Fabric batch fields are not installed yet. Run bench migrate on the server (SPR Fabric Batch Pick + Manual fabric batches).'
			)
		);
		return;
	}
	frappe.dom.freeze(__('Loading batches...'));
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_get_fabric_batch_pick_context',
		args: { spr_name: frm.doc.name },
		callback: function (r) {
			frappe.dom.unfreeze();
			const ctx = r.message || {};
			if (!ctx.needs_picks) {
				const bagHint = cint(ctx.is_bag_spr)
					? __(' Bag FG was recognized, but no batch-tracked BOM raw materials were found on linked Work Order(s). Check BOM / Item has_batch_no on fabric (100*) or slitting (103*) lines.')
					: __(' No bag / fabric Work Order with batch-tracked BOM items was recognized. Ensure Is Bag is checked, roll lines are saved with Work Order, and FG item code is a bag process (221, 224, 211–217, 200–203).');
				frappe.msgprint(
					__(
						'No RM batch selection is required for this SPR.{0}',
						[bagHint]
					)
				);
				return;
			}
			spr_show_fabric_batch_pick_dialog(frm, ctx);
		},
		error: function () {
			frappe.dom.unfreeze();
		},
	});
}

function spr_show_fabric_batch_pick_dialog(frm, ctx) {
	const picksByKey = {};
	(ctx.current_picks || []).forEach(function (p) {
		const k = (p.work_order || '') + '|' + (p.item_code || '') + '|' + (p.batch_no || '');
		picksByKey[k] = flt(p.qty);
	});
	let bodyHtml = '<div class="spr-batch-dlg" style="max-height:460px;overflow:auto">';
	(ctx.lines || []).forEach(function (ln) {
		bodyHtml +=
			'<h4 style="margin-top:0.75rem">' +
			spr_escape_html(ln.work_order || '') +
			' — FG ' +
			spr_escape_html(ln.fg_item || '') +
			(ln.fg_process ? ' (' + spr_escape_html(String(ln.fg_process)) + ')' : '') +
			' — ' +
			__('SPR total') +
			' ' +
			spr_escape_html(String(ln.total_fg_kg || '')) +
			' Kg</h4>';
		bodyHtml +=
			'<p class="text-muted small">' + __('WIP warehouse') + ': ' + spr_escape_html(ln.wip_warehouse || '') + '</p>';
		if (ln.bom_stack && ln.bom_stack.length) {
			bodyHtml +=
				'<table class="table table-bordered table-condensed" style="margin-bottom:0.5rem;max-width:36rem"><thead><tr>' +
				'<th>' +
				__('Step') +
				'</th><th>' +
				__('Process') +
				'</th></tr></thead><tbody>';
			(ln.bom_stack || []).forEach(function (st) {
				bodyHtml +=
					'<tr><td>' +
					spr_escape_html(st.label || st.role || '') +
					'</td><td>' +
					spr_escape_html(st.process || '') +
					(st.item_code ? ' — ' + spr_escape_html(st.item_code) : '') +
					'</td></tr>';
			});
			bodyHtml += '</tbody></table>';
		}
		(ln.raw_materials || []).forEach(function (rm) {
			const procTag = rm.process_code ? ' [' + spr_escape_html(String(rm.process_code)) + ']' : '';
			bodyHtml +=
				'<h5 style="margin-top:0.5rem">' +
				spr_escape_html(rm.item_code || '') +
				procTag +
				' — ' +
				spr_escape_html(rm.item_name || '') +
				'</h5>';
			bodyHtml +=
				'<p class="small">' +
				__('Required') +
				': <b>' +
				String(flt(rm.required_qty)) +
				'</b> Kg &nbsp;|&nbsp; ' +
				spr_escape_html(rm.quality || '') +
				' &nbsp;|&nbsp; ' +
				spr_escape_html(rm.colour || '') +
				' &nbsp;|&nbsp; GSM ' +
				String(flt(rm.gsm)) +
				' &nbsp;|&nbsp; W ' +
				String(flt(rm.width_inch)) +
				'"</p>';
		bodyHtml +=
			'<table class="table table-bordered table-condensed"><thead><tr>' +
			'<th style="width:2rem">' +
			__('Use') +
			'</th><th>' +
			__('Batch No') +
			'</th><th>' +
			__('Warehouse') +
			'</th><th>' +
			__('Avail (Kg)') +
			'</th><th>' +
			__('Use (Kg)') +
			'</th></tr></thead><tbody>';
		const batches = rm.batches || [];
		batches.forEach(function (b) {
			const bn = String(b.batch_no || '');
			const bwh = String(b.warehouse || '');
			const key = (ln.work_order || '') + '|' + (rm.item_code || '') + '|' + bn;
			const defq = picksByKey[key] != null ? picksByKey[key] : '';
			const mx = flt(b.qty);
			const inWip = bwh === (ln.wip_warehouse || '');
			const whBadge = inWip
				? '<span style="color:green;font-size:0.8em">' + spr_escape_html(bwh) + '</span>'
				: '<span style="color:#888;font-size:0.8em">' + spr_escape_html(bwh) + '</span>';
			bodyHtml +=
				'<tr data-wo="' +
				spr_escape_html(ln.work_order || '') +
				'" data-item="' +
				spr_escape_html(rm.item_code || '') +
				'" data-batch="' +
				spr_escape_html(bn) +
				'">' +
				'<td><input type="checkbox" class="spr-bch-use" /></td>' +
				'<td>' +
				spr_escape_html(bn) +
				'</td><td>' +
				whBadge +
				'</td><td>' +
				String(mx) +
				'</td><td><input type="number" class="input-with-feedback form-control spr-bch-qty" step="0.001" min="0" data-max="' +
				String(mx) +
				'" value="' +
				(defq !== '' && defq > 0 ? String(defq) : '') +
				'" style="max-width:9rem" /></td></tr>';
		});
		if (!batches.length) {
			bodyHtml +=
				'<tr><td colspan="5">' + __('No batch stock found for this item.') + '</td></tr>';
		}
			bodyHtml += '</tbody></table>';
		});
	});
	bodyHtml += '</div>';

	const d = new frappe.ui.Dialog({
		title: __('Select RM batches for WO consumption'),
		fields: [{ fieldtype: 'HTML', fieldname: 'spr_batch_html' }],
		size: 'extra-large',
		primary_action_label: __('Save picks'),
		primary_action: function () {
			const out = [];
			let qtyErr = '';
			d.$wrapper.find('tr[data-batch]').each(function () {
				const $tr = $(this);
				const use = $tr.find('.spr-bch-use').prop('checked');
				const q = flt($tr.find('.spr-bch-qty').val());
				const mx = flt($tr.find('.spr-bch-qty').attr('data-max'));
				if (!use && q <= 0) {
					return;
				}
				if (q <= 0) {
					return;
				}
				if (mx > 0 && q - mx > 1e-6) {
					qtyErr = __('Use quantity cannot exceed available stock for one of the selected batches.');
					return false;
				}
				out.push({
					work_order: $tr.attr('data-wo'),
					item_code: $tr.attr('data-item'),
					batch_no: $tr.attr('data-batch'),
					qty: q,
				});
			});
			if (qtyErr) {
				frappe.msgprint(qtyErr);
				return;
			}
			frappe.call({
				method:
					'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_save_fabric_batch_picks',
				args: { spr_name: frm.doc.name, picks_json: JSON.stringify(out) },
				freeze: true,
				freeze_message: __('Saving...'),
				callback: function () {
					d.hide();
					frm.reload_doc();
					frappe.show_alert({
						message: __('RM batch picks saved. You can Submit the SPR.'),
						indicator: 'green',
					});
				},
			});
		},
	});
	const $w = d.fields_dict.spr_batch_html.$wrapper;
	$w.html(bodyHtml);
	$w.on('change', '.spr-bch-use', function () {
		const $tr = $(this).closest('tr');
		const $q = $tr.find('.spr-bch-qty');
		if ($(this).prop('checked') && (!($q.val() || '') || flt($q.val()) <= 0)) {
			const mx = flt($q.attr('data-max'));
			$q.val(mx > 0 ? String(mx) : '');
		}
	});
	d.show();
}

/**
 * Register toolbar + Tools menu. Frappe rebuilds the header on Save/refresh — remove then re-add
 * every time so buttons do not disappear (do not use a one-shot _spr_page_buttons_ok guard).
 * Also registers custom buttons — they survive some toolbar rebuilds better than inner_group alone.
 */
function spr_bundle_packaging_toggle_label(enabled) {
	return enabled
		? __('Bundle SE on Submit: ON')
		: __('Bundle SE on Submit: OFF');
}

function spr_toggle_bundle_packaging_on_submit(frm) {
	if (!frm || !frm.doc || !frm.doc.name) {
		return;
	}
	if (cint(frm.doc.docstatus) !== 0) {
		frappe.msgprint(__('Save as draft to change bundle packaging mode.'));
		return;
	}
	if (!frappe.meta.get_docfield('Shaft Production Run', 'custom_use_bundle_packaging_on_submit')) {
		frappe.msgprint(__('Run bench migrate to enable the bundle packaging submit toggle.'));
		return;
	}
	const cur = cint(frm.doc.custom_use_bundle_packaging_on_submit);
	const next = cur ? 0 : 1;
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_set_bundle_packaging_on_submit',
		args: {
			shaft_production_run: frm.doc.name,
			enabled: next,
		},
		freeze: true,
		callback(r) {
			const msg = (r.message && r.message.mode_label) || spr_bundle_packaging_toggle_label(next);
			if (frm.doc.custom_use_bundle_packaging_on_submit !== next) {
				frm.set_value('custom_use_bundle_packaging_on_submit', next);
			}
			frappe.show_alert({ message: msg, indicator: next ? 'green' : 'blue' }, 6);
			spr_register_spr_page_buttons(frm);
		},
	});
}

function spr_button_text($btn) {
	return String(($btn && $btn.text && $btn.text()) || '')
		.replace(/\s+/g, ' ')
		.trim();
}

function spr_move_existing_top_buttons_to_tools(frm) {
	if (!frm || !frm.page || typeof frm.page.add_inner_button !== 'function') {
		return;
	}
	const tg = __('Tools');
	const labels = [
		__('View Party Stock'),
		__('Bora Weight'),
		__('Mixing Sheet'),
	];
	const $buttons = frm.page.wrapper
		? frm.page.wrapper.find('.page-actions button, .custom-actions button, .standard-actions button')
		: $();
	labels.forEach(function (label) {
		const lbl = String(label || '').trim();
		if (!lbl) return;
		const $btn = $buttons
			.filter(function () {
				return spr_button_text($(this)) === lbl;
			})
			.first();
		if (!$btn.length || $btn.data('spr-moved-to-tools')) {
			return;
		}
		try {
			if (typeof frm.page.remove_inner_button === 'function') {
				frm.page.remove_inner_button(lbl, tg);
				frm.page.remove_inner_button(lbl, 'Tools');
			}
		} catch (e) {}
		try {
			frm.page.add_inner_button(
				lbl,
				function () {
					$btn.trigger('click');
				},
				tg
			);
			$btn.data('spr-moved-to-tools', 1).hide();
		} catch (e) {}
	});
}

function spr_register_spr_page_buttons(frm) {
	if (!frm) {
		return;
	}
	const canRemoveCustom = typeof frm.remove_custom_button === 'function';
	if (canRemoveCustom) {
		try {
			frm.remove_custom_button(__('Manual job'));
		} catch (e) {}
		try {
			frm.remove_custom_button(__('Bundle packaging'));
		} catch (e) {}
		try {
			frm.remove_custom_button(__('Bundle SE on Submit: ON'));
		} catch (e) {}
		try {
			frm.remove_custom_button(__('Bundle SE on Submit: OFF'));
		} catch (e) {}
		try {
			frm.remove_custom_button(__('Select RM batches'));
		} catch (e) {}
	}
	if (!frm.page || typeof frm.page.add_inner_button !== 'function') {
		return;
	}
	const tg = __('Tools');
	const rm = frm.page.remove_inner_button;
	if (typeof rm === 'function') {
		[
			__('Manual job'),
			__('Bundle packaging'),
			__('Bundle SE on Submit: ON'),
			__('Bundle SE on Submit: OFF'),
			__('Select RM batches'),
		].forEach(function (lbl) {
			try {
				rm.call(frm.page, lbl);
			} catch (e) {}
		});
		[
			__('SPR — Manual job'),
			__('SPR — Bundle packaging'),
			__('SPR — Select RM batches'),
			spr_bundle_packaging_toggle_label(0),
			spr_bundle_packaging_toggle_label(1),
		].forEach(function (lbl) {
			try {
				rm.call(frm.page, lbl, tg);
			} catch (e) {}
			try {
				rm.call(frm.page, lbl, 'Tools');
			} catch (e) {}
		});
	}
	function addInner(fn) {
		try {
			fn();
		} catch (e) {}
	}
	addInner(function () {
		if (
			frappe.meta.get_docfield('Shaft Production Run', 'custom_use_bundle_packaging_on_submit') &&
			cint(frm.doc.docstatus) === 0
		) {
			const bundleOn = cint(frm.doc.custom_use_bundle_packaging_on_submit);
			frm.page.add_inner_button(
				spr_bundle_packaging_toggle_label(bundleOn),
				function () {
					spr_toggle_bundle_packaging_on_submit(frm);
				},
				tg
			);
		}
	});
	addInner(function () {
		frm.page.add_inner_button(
			__('SPR — Manual job'),
			function () {
				spr_open_manual_job_dialog(frm);
			},
			tg
		);
	});
	addInner(function () {
		frm.page.add_inner_button(
			__('SPR — Bundle packaging'),
			function () {
				spr_open_bundle_packaging_dialog(frm);
			},
			tg
		);
	});
	addInner(function () {
		if (cint(frm.doc.docstatus) === 0 && sprIsBundlePackagingMode(frm) && frm.doc.production_plan) {
			frm.page.add_inner_button(
				__('Reload bundle from PP'),
				function () {
					frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_refresh_bundle_calculation_from_pp',
						args: { shaft_production_run: frm.doc.name },
						freeze: true,
						callback: function (r) {
							if (!r.exc) {
								frm.reload_doc();
								frappe.show_alert({
									message: __('Loaded {0} bundle row(s) from Production Plan.', [
										(r.message && r.message.rows) || 0,
									]),
									indicator: 'green',
								});
							}
						},
					});
				},
				tg
			);
		}
	});
	addInner(function () {
		if (
			frappe.meta.get_docfield('Shaft Production Run', 'fabric_batch_picks') &&
			cint(frm.doc.docstatus) === 0
		) {
			frm.page.add_inner_button(
				__('SPR — Select RM batches'),
				function () {
					spr_open_fabric_batch_pick_dialog(frm);
				},
				tg
			);
		}
	});
	setTimeout(function () {
		spr_move_existing_top_buttons_to_tools(frm);
	}, 80);
	setTimeout(function () {
		spr_move_existing_top_buttons_to_tools(frm);
	}, 500);
}

/** After Save the toolbar is rebuilt asynchronously — retry so Manual job / Bundle packaging stay visible. */
function spr_register_spr_page_buttons_after_save(frm) {
	spr_register_spr_page_buttons(frm);
	[120, 300, 600, 1200, 2000, 3500, 5000].forEach(function (ms) {
		setTimeout(function () {
			spr_register_spr_page_buttons(frm);
		}, ms);
	});
}

/** Default WO qty (Kg): net per roll × rolls per shaft × number of shafts (deck positions). */
function sprManualDefaultWoQty(line, noShafts, noRolls) {
	const shafts = cint(noShafts);
	const rolls = cint(noRolls);
	const s = shafts > 0 ? shafts : 1;
	const r = rolls > 0 ? rolls : 1;
	const nps = line.net_per_shaft_kg != null ? flt(line.net_per_shaft_kg) : null;
	if (nps != null && nps > 0) {
		return nps * r * s;
	}
	const fs =
		line.first_segment_planned_kg != null && line.first_segment_planned_kg !== ''
			? flt(line.first_segment_planned_kg)
			: null;
	if (fs != null && fs > 0) {
		return fs * r * s;
	}
	const pq = flt(line.planned_qty);
	return pq > 0 ? pq : 1;
}

function sprManualNormalizeWidthToken(token) {
	const raw = String(token || '')
		.replace(/inch|inches|in/gi, '')
		.replace(/["']/g, '')
		.trim();
	if (!raw) return 0;
	return flt(raw);
}

function sprManualParseCombination(text) {
	return String(text || '')
		.split('+')
		.map(function (part) {
			return sprManualNormalizeWidthToken(part);
		})
		.filter(function (w) {
			return w > 0;
		});
}

/** Actions ΓåÆ Manual job: multi-select PP lines; WO qty defaults to net/shaft × shafts from Available Jobs. */
function spr_open_manual_job_dialog(frm) {
	if (frm.is_new() || !frm.doc.name) {
		frappe.msgprint(__('Save the Shaft Production Run first.'));
		return;
	}
	if (frm.doc.docstatus && frm.doc.docstatus !== 0) {
		frappe.msgprint(__('This document is submitted and cannot be edited.'));
		return;
	}
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_get_manual_job_catalog',
		args: { shaft_production_run: frm.doc.name },
		freeze: true,
		freeze_message: __('Loading Production Plan lines...'),
		callback: function (r) {
			const payload = r.message || {};
			const lines = payload.lines || [];
			const ppName = payload.production_plan || '';
			if (!lines.length) {
				frappe.msgprint(
					__('No Production Plan lines found. Set Production Plan and ensure it has planned items.')
				);
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __('Manual job'),
				fields: [
					{
						fieldname: 'spr_manual_ui_style',
						fieldtype: 'HTML',
						options:
							'<style>' +
							'.spr-manual-shell{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px;margin-bottom:10px;}' +
							'.spr-manual-shell b{font-weight:600;color:#0f172a;}' +
							'.spr-manual-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 10px;}' +
							'.spr-manual-summary{margin-left:auto;font-size:12px;color:#334155;background:#eef2ff;border:1px solid #c7d2fe;border-radius:999px;padding:4px 10px;}' +
							'.spr-manual-table-wrap{overflow:auto;border:1px solid #dbe2ea;border-radius:12px;background:#fff;max-height:360px;}' +
							'.spr-manual-table{font-size:12px;margin:0;min-width:1020px;table-layout:fixed;}' +
							'.spr-manual-table thead th{position:sticky;top:0;background:#f1f5f9;z-index:1;border-bottom:1px solid #cbd5e1;color:#334155;}' +
							'.spr-manual-table tbody tr:hover{background:#f8fafc;}' +
							'.spr-manual-row-selected{background:#ecfeff !important;}' +
							'.spr-manual-table input[type=number],.spr-manual-table select{height:28px;font-size:12px;}' +
							'</style>',
					},
					{
						fieldname: 'spr_manual_pp_hint',
						fieldtype: 'HTML',
						options:
							'<div class="spr-manual-shell">' +
							'<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">' +
							'<div><b>' +
							__('Manual Work Order Planner') +
							'</b><div class="text-muted small">' +
							__('Choose shafts/roll logic, then confirm rows below.') +
							'</div></div>' +
							'<div class="text-muted small">' +
							__('Production Plan: {0}', [ppName || '—']) +
							'</div></div></div>',
					},
					{
						fieldname: 'no_of_shafts',
						fieldtype: 'Int',
						label: __('Number of shafts (deck positions)'),
						reqd: 1,
						default: 1,
					},
					{
						fieldname: 'no_of_rolls',
						fieldtype: 'Int',
						label: __('Number of rolls (per shaft)'),
						reqd: 1,
						default: 1,
					},
					{
						fieldname: 'combination_gsm',
						fieldtype: 'Int',
						label: __('Combination GSM'),
					},
					{
						fieldname: 'combination_input',
						fieldtype: 'Data',
						label: __('Combination widths (Inches)'),
						description: __('Example: 34+34+42. Same GSM only. One segment = one roll per shaft.'),
					},
					{
						fieldname: 'combination_status_html',
						fieldtype: 'HTML',
						options: '<div class="text-muted small spr-manual-combination-status"></div>',
					},
					{
						fieldname: 'line_select_html',
						fieldtype: 'HTML',
						label: __('Select items'),
						options:
							'<div class="spr-manual-toolbar">' +
							'<button type="button" class="btn btn-xs btn-default spr-manual-select-all">' +
							__('Select all') +
							'</button>' +
							'<button type="button" class="btn btn-xs btn-default spr-manual-select-none">' +
							__('Clear') +
							'</button>' +
							'<span class="spr-manual-summary spr-manual-selection-summary">—</span>' +
							'</div>' +
							'<div class="spr-manual-lines-wrap"></div>' +
							'<p class="text-muted small" style="margin-top:6px;">' +
							__('WO qty default = net/roll Kg x rolls x shafts') +
							'</p>',
					},
				],
				primary_action_label: __('Create Work Order(s)'),
				primary_action: function () {
					const no_of_shafts = cint(d.get_value('no_of_shafts'));
					const no_of_rolls = cint(d.get_value('no_of_rolls'));
					if (no_of_shafts < 1) {
						frappe.msgprint(__('Number of shafts must be at least 1.'));
						return;
					}
					if (no_of_rolls < 1) {
						frappe.msgprint(__('Number of rolls per shaft must be at least 1.'));
						return;
					}
					const items = [];
					const comboRaw = String(d.get_value('combination_input') || '').trim();
					const comboMode = !!comboRaw;
					lines.forEach(function (line, idx) {
						const cb = d.$wrapper.find('.spr-manual-inc[data-idx="' + idx + '"]');
						if (!cb.length || !cb.is(':checked')) {
							return;
						}
						const q = flt(d.$wrapper.find('.spr-manual-qty[data-idx="' + idx + '"]').val());
						const mr = flt(d.$wrapper.find('.spr-manual-meter-roll[data-idx="' + idx + '"]').val());
						if (!(q > 0)) {
							frappe.msgprint(__('Enter valid Work Order qty for selected line.'));
							return;
						}
						if (!(mr > 0)) {
							frappe.msgprint(__('Enter valid Meter/Roll for selected line.'));
							return;
						}
						items.push({
							item_code: line.item_code,
							production_plan_item: line.production_plan_item,
							wo_qty: q,
							meter_roll: mr,
							roll_count_per_shaft: comboMode ? cint(line.__combo_roll_count_per_shaft || 1) : cint(d.get_value('no_of_rolls')) || 1,
							selected_reuse_work_order:
								d.$wrapper.find('.spr-manual-reuse-wo[data-idx="' + idx + '"]').val() || '',
						});
					});
					if (!items.length) {
						frappe.msgprint(__('Select at least one line with valid Meter/Roll and Work Order qty.'));
						return;
					}
					const finalItems = [];
					if (comboMode) {
						const byItem = new Map();
						items.forEach(function (it) {
							const key = [
								it.item_code || '',
								it.selected_reuse_work_order || '',
							].join('::');
							if (!byItem.has(key)) {
								byItem.set(key, {
									item_code: it.item_code,
									production_plan_item: it.production_plan_item,
									wo_qty: 0,
									meter_roll: it.meter_roll,
									roll_count_per_shaft: 0,
									selected_reuse_work_order: it.selected_reuse_work_order || '',
								});
							}
							const agg = byItem.get(key);
							agg.wo_qty += flt(it.wo_qty);
							agg.roll_count_per_shaft += cint(it.roll_count_per_shaft || 1);
						});
						byItem.forEach(function (v) {
							finalItems.push(v);
						});
					} else {
						Array.prototype.push.apply(finalItems, items);
					}
					const runManualCreate = function () {
						d.hide();
						frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_create_manual_jobs_multi',
						args: {
							shaft_production_run: frm.doc.name,
							no_of_shafts: no_of_shafts,
							no_of_rolls: cint(d.get_value('no_of_rolls')) || 1,
							items: finalItems,
							combination_input: comboRaw,
						},
						freeze: true,
						freeze_message: __('Creating / fetching Work Order(s)...'),
						callback: function (r2) {
							const m = r2.message || {};
							const wos = (m.work_orders || []).join(', ');
							const reused = (m.reused_work_orders || []).join(', ');
							const msg = reused
								? __('Work Order(s) {0} (job {1}). Reused unused manual WO(s): {2}.', [
										wos || '',
										m.job_id || '',
										reused,
								  ])
								: __('Work Order(s) {0} (job {1}).', [wos || '', m.job_id || '']);
							frappe.show_alert({
								message: msg,
								indicator: 'green',
							});
							frm.reload_doc();
						},
					});
					};
					// Important: server APIs read DB state. Save latest row/job deletions first so
					// manual WO reuse does not create a new WO from stale pre-delete links.
					if (frm.is_dirty && frm.is_dirty()) {
						const p = frm.save();
						if (p && typeof p.then === 'function') {
							p.then(function () {
								runManualCreate();
							}).catch(function () {
								frappe.msgprint(__('Could not save latest SPR changes. Please save and try Manual job again.'));
							});
						} else {
							setTimeout(runManualCreate, 250);
						}
						return;
					}
					runManualCreate();
				},
			});

			function renderManualLinesTable() {
				const nShafts = cint(d.get_value('no_of_shafts'));
				const nRolls = cint(d.get_value('no_of_rolls')) || 1;
				const wrap = d.$wrapper.find('.spr-manual-lines-wrap');
				if (!wrap.length) {
					return;
				}
				let html =
					'<div class="spr-manual-table-wrap">' +
					'<table class="table table-bordered table-condensed spr-manual-table">';
				html +=
					'<thead><tr><th style="width:36px;"></th><th>' +
					__('Item / PP row') +
					'</th><th style="width:110px;">' +
					__('Order Code') +
					'</th><th style="width:70px;">' +
					__('Width (Inches)') +
					'</th><th style="width:110px;">' +
					__('Meter/Roll') +
					'</th><th style="width:95px;">' +
					__('Net/roll (Kg)') +
					'</th><th style="width:190px;">' +
					__('Reuse WO') +
					'</th><th style="width:110px;">' +
					__('WO qty (Kg)') +
					'</th></tr></thead><tbody>';
				lines.forEach(function (line, idx) {
					const wIn = flt(line.width_inch);
					const nps =
						line.net_per_shaft_kg != null && line.net_per_shaft_kg !== ''
							? flt(line.net_per_shaft_kg)
							: null;
					const npsLabel =
						nps != null && nps > 0
							? nps.toFixed(2) +
							  (line.matched_job_id
								  ? ' (' + __('job') + ' ' + String(line.matched_job_id) + ')'
								  : '')
							: '—';
					const defQ = sprManualDefaultWoQty(line, nShafts, nRolls);
					const label =
						String(line.item_code || '') +
						' - ' +
						String(line.item_name || '').substring(0, 28) +
						' - ' +
						String(line.production_plan_item || '');
					html += '<tr>';
					html +=
						'<td style="text-align:center;"><input type="checkbox" class="spr-manual-inc" data-idx="' +
						idx +
						'" checked /></td>';
					html +=
						'<td style="max-width:360px;white-space:normal;word-break:break-word;">' +
						frappe.utils.escape_html(label) +
						'</td>';
					html += '<td>' + frappe.utils.escape_html(line.order_code || '') + '</td>';
					html += '<td>' + wIn.toFixed(1) + '</td>';
					html +=
						'<td><input type="number" class="input-with-feedback spr-manual-meter-roll" data-idx="' +
						idx +
						'" value="500" step="0.1" style="width:100px" placeholder="500"/></td>';
					html += '<td>' + frappe.utils.escape_html(npsLabel) + '</td>';
					const reuseWos = Array.isArray(line.reusable_work_orders) ? line.reusable_work_orders : [];
					let woSelect =
						'<select class="input-with-feedback spr-manual-reuse-wo" data-idx="' +
						idx +
						'" style="width:170px"><option value="">' +
						frappe.utils.escape_html(__('Auto (reuse latest unused)')) +
						'</option><option value="__NEW__">' +
						frappe.utils.escape_html(__('Create New WO')) +
						'</option>';
					reuseWos.forEach(function (wo) {
						woSelect +=
							'<option value="' +
							frappe.utils.escape_html(String(wo)) +
							'">' +
							frappe.utils.escape_html(String(wo)) +
							'</option>';
					});
					woSelect += '</select>';
					html += '<td style="white-space:nowrap;">' + woSelect + '</td>';
					html +=
						'<td><input type="number" class="input-with-feedback spr-manual-qty" data-idx="' +
						idx +
						'" value="' +
						defQ.toFixed(2) +
						'" step="0.001" style="width:100px"/></td>';
					html += '</tr>';
				});
				html += '</tbody></table></div>';
				wrap.html(html);
				applyManualCombinationSelection();
				updateManualSelectionSummary();
			}

			function updateManualSelectionSummary() {
				const checked = d.$wrapper.find('.spr-manual-inc:checked');
				let totalQty = 0;
				d.$wrapper.find('.spr-manual-table tbody tr').removeClass('spr-manual-row-selected');
				checked.each(function () {
					const idx = cint($(this).attr('data-idx'));
					const q = flt(d.$wrapper.find('.spr-manual-qty[data-idx="' + idx + '"]').val());
					totalQty += q > 0 ? q : 0;
					$(this).closest('tr').addClass('spr-manual-row-selected');
				});
				d.$wrapper.find('.spr-manual-selection-summary').text(
					__('Selected: {0} row(s) | WO Qty: {1} Kg', [checked.length, totalQty.toFixed(2)])
				);
			}

			function setManualCombinationStatus(message, colorClass) {
				const wrap = d.$wrapper.find('.spr-manual-combination-status');
				if (!wrap.length) return;
				const cls = colorClass || 'text-muted';
				wrap.html(
					message
						? '<span class="' + cls + '">' + frappe.utils.escape_html(message) + '</span>'
						: ''
				);
			}

			function syncManualCombinationMode() {
				const comboRaw = String(d.get_value('combination_input') || '').trim();
				const hasCombo = !!comboRaw;
				const nr = d.fields_dict.no_of_rolls;
				if (nr && nr.$input) {
					nr.$input.prop('disabled', hasCombo);
				}
				if (hasCombo && cint(d.get_value('no_of_rolls')) !== 1) {
					d.set_value('no_of_rolls', 1);
					return true;
				}
				return false;
			}

			function applyManualCombinationSelection() {
				const comboRaw = String(d.get_value('combination_input') || '').trim();
				if (!comboRaw) {
					setManualCombinationStatus('');
					return;
				}
				const comboGsm = cint(d.get_value('combination_gsm'));
				if (comboGsm < 1) {
					setManualCombinationStatus(__('Enter Combination GSM to auto-select widths.'), 'text-warning');
					return;
				}
				const widths = sprManualParseCombination(comboRaw);
				if (!widths.length) {
					setManualCombinationStatus(__('Enter widths like 34+34+42.'), 'text-warning');
					return;
				}
				const picks = [];
				const countsByIdx = {};
				for (let i = 0; i < widths.length; i++) {
					const targetWidth = flt(widths[i]);
					let matchIdx = -1;
					for (let j = 0; j < lines.length; j++) {
						const line = lines[j];
						if (cint(line.gsm) !== comboGsm) continue;
						if (Math.abs(flt(line.width_inch) - targetWidth) > 0.05) continue;
						matchIdx = j;
						break;
					}
					if (matchIdx === -1) {
						setManualCombinationStatus(
							__('No unused PP line found for GSM {0} width {1} Inches.', [comboGsm, targetWidth]),
							'text-danger'
						);
						return;
					}
					picks.push(matchIdx);
					countsByIdx[matchIdx] = (countsByIdx[matchIdx] || 0) + 1;
				}

				d.$wrapper.find('.spr-manual-inc').prop('checked', false);
				lines.forEach(function (line) {
					delete line.__combo_roll_count_per_shaft;
				});
				Object.keys(countsByIdx).forEach(function (idxStr) {
					const idx = cint(idxStr);
					const rollCount = cint(countsByIdx[idx] || 1);
					lines[idx].__combo_roll_count_per_shaft = rollCount;
					d.$wrapper.find('.spr-manual-inc[data-idx="' + idx + '"]').prop('checked', true);
					d.$wrapper
						.find('.spr-manual-qty[data-idx="' + idx + '"]')
						.val(sprManualDefaultWoQty(lines[idx], cint(d.get_value('no_of_shafts')) || 1, rollCount).toFixed(2));
				});
				setManualCombinationStatus(
					__('Selected {0} segment(s) for GSM {1}: {2}', [
						picks.length,
						comboGsm,
						widths.join(' + '),
					]),
					'text-success'
				);
			}

			d.show();
			try {
				d.$wrapper.find('.modal-dialog').css('max-width', '1100px');
			} catch (e) {}
			renderManualLinesTable();
			d.$wrapper.on('click', '.spr-manual-select-all', function () {
				d.$wrapper.find('.spr-manual-inc').prop('checked', true);
				updateManualSelectionSummary();
			});
			d.$wrapper.on('click', '.spr-manual-select-none', function () {
				d.$wrapper.find('.spr-manual-inc').prop('checked', false);
				updateManualSelectionSummary();
			});
			d.$wrapper.on('change input', '.spr-manual-inc, .spr-manual-qty', function () {
				updateManualSelectionSummary();
			});
			const ns = d.fields_dict.no_of_shafts;
			if (ns && ns.$input) {
				ns.$input.on('change input', function () {
					if (syncManualCombinationMode()) return;
					renderManualLinesTable();
				});
			}
			const nr = d.fields_dict.no_of_rolls;
			if (nr && nr.$input) {
				nr.$input.on('change input', function () {
					if (syncManualCombinationMode()) return;
					renderManualLinesTable();
				});
			}
			const cg = d.fields_dict.combination_gsm;
			if (cg && cg.$input) {
				cg.$input.on('change input', function () {
					if (syncManualCombinationMode()) return;
					renderManualLinesTable();
				});
			}
			const ci = d.fields_dict.combination_input;
			if (ci && ci.$input) {
				ci.$input.on('change input', function () {
					if (syncManualCombinationMode()) return;
					renderManualLinesTable();
				});
			}
		},
	});
}

/** Actions ΓåÆ Bundle packaging: Job + Width from Available Jobs / roll widths; gross applied to all matching rolls. */
function spr_open_bundle_packaging_dialog(frm) {
	if (frm.is_new() || !frm.doc.name) {
		frappe.msgprint(__('Save the Shaft Production Run first.'));
		return;
	}
	if (frm.doc.docstatus && frm.doc.docstatus !== 0) {
		frappe.msgprint(__('This document is submitted and cannot be edited.'));
		return;
	}
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_get_bundle_packaging_catalog',
		args: { shaft_production_run: frm.doc.name },
		freeze: true,
		freeze_message: __('Loading jobs...'),
		callback: function (r) {
			const cat = r.message || {};
			const jobs = cat.jobs || [];
			const widthsByJob = cat.widths_by_job || {};
			if (!jobs.length) {
				frappe.msgprint(__('Add Available Jobs (shaft jobs) first.'));
				return;
			}
			const jobOpts = jobs
				.map(function (j) {
					return j.job_id;
				})
				.join('\n');
			const jobByLabel = {};
			jobs.forEach(function (j) {
				jobByLabel[j.job_id] = j;
			});
			const d = new frappe.ui.Dialog({
				title: __('Bundle packaging'),
				fields: [
					{
						fieldname: 'spr_bundle_hint',
						fieldtype: 'HTML',
						options:
							'<p class="text-muted small" style="margin-bottom:10px;">' +
							__(
								'Step 1: pick Job ID. Step 2: pick width for that segment (combination widths and WO items are shown below). Same single-roll gross applies to all roll lines for that job and width. Sticker width = selected width × number of packaging.'
							) +
							'</p>',
					},
					{
						fieldname: 'job_pick',
						fieldtype: 'Select',
						label: __('Job ID (Available Jobs)'),
						options: jobOpts,
						reqd: 1,
					},
					{
						fieldname: 'job_detail_html',
						fieldtype: 'HTML',
						options: '<div class="spr-bundle-job-detail text-muted small"></div>',
					},
					{
						fieldname: 'width_inch',
						fieldtype: 'Select',
						label: __('Width / segment (Inches) - pick one row from the table above'),
						options: '',
						reqd: 1,
					},
					{
						fieldname: 'calc_html',
						fieldtype: 'HTML',
						options: '<div class="spr-bundle-calc text-muted small"></div>',
					},
					{
						fieldname: 'no_of_packaging',
						fieldtype: 'Int',
						label: __('Number of packaging'),
						reqd: 1,
						default: 1,
					},
					{
						fieldname: 'whole_gross_kg',
						fieldtype: 'Float',
						label: __('Whole gross (Kg)'),
						reqd: 1,
					},
					{
						fieldname: 'produced_length_mtrs',
						fieldtype: 'Float',
						label: __('Produced length (Mtrs)'),
						reqd: 1,
					},
				],
				primary_action_label: __('Apply'),
				primary_action: function (values) {
					const jp = jobByLabel[values.job_pick];
					const w = flt(values.width_inch);
					const n = cint(values.no_of_packaging);
					const whole = flt(values.whole_gross_kg);
					const producedLength = flt(values.produced_length_mtrs);
					if (!jp || !jp.job_id) {
						frappe.msgprint(__('Select a job.'));
						return;
					}
					if (w <= 0) {
						frappe.msgprint(__('Select a width.'));
						return;
					}
					if (n < 1 || whole <= 0) {
						frappe.msgprint(__('Enter a valid packaging count and whole gross weight.'));
						return;
					}
					if (producedLength <= 0) {
						frappe.msgprint(__('Enter valid produced length.'));
						return;
					}
					d.hide();
					frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_apply_bundle_packaging_for_job_width',
						args: {
							shaft_production_run: frm.doc.name,
							job_id: jp.job_id,
							width_inch: w,
							no_of_packaging: n,
							whole_gross_kg: whole,
							produced_length_mtrs: producedLength,
						},
						freeze: true,
						freeze_message: __('Applying bundle packaging...'),
						callback: function (r2) {
							const m = r2.message || {};
							frappe.show_alert({
								message: __(
									'Updated {0} roll(s). Remaining unpacked: {4}. Single gross {1} Kg, sticker width {2} Inches, bundle net {3} Kg.',
									[
										String(m.updated_rolls != null ? m.updated_rolls : ''),
										String(m.single_roll_gross_kg != null ? m.single_roll_gross_kg : ''),
										String(m.total_width_inch != null ? m.total_width_inch : ''),
										String(m.sticker_bundle_weight_kg != null ? m.sticker_bundle_weight_kg : ''),
										String(m.remaining_unpacked_rolls != null ? m.remaining_unpacked_rolls : ''),
									]
								),
								indicator: 'green',
							});
							// Keep UI stable: single reload only (avoid heavy loops that cause hanging).
							frm.reload_doc();
						},
					});
				},
			});
			function refreshWidthOptions() {
				const jp = jobByLabel[d.get_value('job_pick')];
				const wf = d.fields_dict.width_inch;
				const det = d.$wrapper.find('.spr-bundle-job-detail');
				if (!jp || !wf) {
					return;
				}
				const segs = jp.segments || [];
				const arr = widthsByJob[jp.job_id] || [];
				if (segs.length) {
					const uniqueSegs = [];
					const seenWidths = new Set();
					segs.forEach(function (s) {
						const w = flt(s.width_inch);
						if (w <= 0) return;
						const key = (Math.round(w * 1000) / 1000).toString();
						if (seenWidths.has(key)) return;
						seenWidths.add(key);
						uniqueSegs.push(s);
					});
					let html =
						'<table class="table table-bordered table-condensed" style="font-size:11px;margin:4px 0;"><thead><tr><th>' +
						__('Width') +
						'</th><th>' +
						__('Net/shaft (Kg)') +
						'</th><th>' +
						__('WO item') +
						'</th></tr></thead><tbody>';
					uniqueSegs.forEach(function (s) {
						const net = s.net_kg_per_shaft != null ? flt(s.net_kg_per_shaft).toFixed(2) : '—';
						const ic = [s.item_code || '', (s.item_name || '').substring(0, 28)].join(' ').trim();
						html +=
							'<tr><td>' +
							flt(s.width_inch).toFixed(1) +
							'</td><td>' +
							net +
							'</td><td>' +
							frappe.utils.escape_html(ic) +
							'</td></tr>';
					});
					html += '</tbody></table>';
					det.html(html);
					wf.df.options = uniqueSegs
						.map(function (s) {
							return String(flt(s.width_inch));
						})
						.join('\n');
				} else {
					const comb = jp.combination_text || '';
					det.html(
						comb
							? '<p class="small">' + frappe.utils.escape_html(comb) + '</p>'
							: '<p class="small text-muted">' + __('No segment breakdown — use width list.') + '</p>'
					);
					if (!arr.length) {
						wf.df.options = '';
						wf.refresh();
						return;
					}
					const uniqueArr = [];
					const seenArr = new Set();
					arr.forEach(function (x) {
						const w = flt(x);
						if (w <= 0) return;
						const key = (Math.round(w * 1000) / 1000).toString();
						if (seenArr.has(key)) return;
						seenArr.add(key);
						uniqueArr.push(x);
					});
					wf.df.options = uniqueArr
						.map(function (x) {
							return String(x);
						})
						.join('\n');
				}
				wf.refresh();
				const firstW =
					wf.df.options ? flt(String(wf.df.options).split('\n')[0]) : 0;
				if (firstW > 0) {
					d.set_value('width_inch', String(firstW));
				}
			}
			function recalc() {
				const jp = jobByLabel[d.get_value('job_pick')];
				const wsel = d.get_value('width_inch');
				const n = cint(d.get_value('no_of_packaging'));
				const whole = flt(d.get_value('whole_gross_kg'));
				const el = d.$wrapper.find('.spr-bundle-calc');
				if (!jp || !el.length) {
					return;
				}
				const single = n > 0 ? whole / n : 0;
				const tw = flt(wsel) * n;
				el.html(
					__('Single gross: {0} Kg - Sticker width (selected width x pkg): {1} Inches', [
						single.toFixed(2),
						tw.toFixed(2),
					])
				);
			}
			d.show();
			refreshWidthOptions();
			recalc();
			if (d.fields_dict.job_pick && d.fields_dict.job_pick.$input) {
				d.fields_dict.job_pick.$input.on('change', function () {
					refreshWidthOptions();
					recalc();
				});
			}
			['width_inch', 'no_of_packaging', 'whole_gross_kg'].forEach(function (fn) {
				const f = d.fields_dict[fn];
				if (f && f.$input) {
					f.$input.on('change input', recalc);
				}
			});
		},
	});
}

frappe.ui.form.on('Bundle Calculation', {
	pkts_per_bundle: function (frm, cdt, cdn) {
		sprRecalcBundlePlannedPcs(frm, cdt, cdn);
	},
	pcs_per_packet: function (frm, cdt, cdn) {
		sprRecalcBundlePlannedPcs(frm, cdt, cdn);
	},
	total_consumed_meter: function (frm) {
		if (sprIsSheetCutting(frm)) {
			sprSyncBundleProducedSheets(frm, { silent: true });
		}
	},
	create_bundle_entry: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!sprIsBundlePackagingMode(frm)) {
			frappe.msgprint(__('Bundle Create Entry is only for sheet-cutting / bag SPR'));
			return;
		}
		if (frm.is_new() || !frm.doc.name) {
			frappe.msgprint(__('Save the Shaft Production Run before creating roll lines.'));
			return;
		}
		const nBundles = cint(row.no_of_bundles);
		const nBoxes = cint(row.no_of_boxes);
		const nRows = sprIsBag(frm) && nBundles < 1 ? nBoxes : nBundles;
		if (nRows < 1) {
			frappe.msgprint(__('No of Bundles / No of Boxes must be at least 1'));
			return;
		}
		const args = { shaft_production_run: frm.doc.name };
		if (row.name) {
			args.bundle_row_name = row.name;
		} else {
			const rows = frm.doc.bundle_calculation || [];
			args.bundle_row_idx = rows.indexOf(row);
		}
		frappe.call({
			method:
				'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.build_spr_bundle_result_lines_for_row',
			args: args,
			freeze: true,
			freeze_message: __('Creating roll lines for this bundle...'),
			callback: function (r) {
				const lines = r.message || [];
				lines.forEach(function (line) {
					const it = frm.add_child('items');
					Object.keys(line).forEach(function (k) {
						if (line[k] !== undefined && line[k] !== null) {
							it[k] = line[k];
						}
					});
					if (line.quality) {
						it.quality = line.quality;
					}
					if (line.color) {
						it.color = line.color;
					}
					if (line.gsm != null && line.gsm !== '') {
						it.gsm = cint(line.gsm);
					}
					if (line.custom_sheet_size) {
						it.custom_sheet_size = line.custom_sheet_size;
					}
					if (line.custom_planned_sheets_pcs != null) {
						it.custom_planned_sheets_pcs = flt(line.custom_planned_sheets_pcs);
					}
					if (line.custom_planned_bag_pcs != null) {
						it.custom_planned_bag_pcs = flt(line.custom_planned_bag_pcs);
					}
				});
				frm.refresh_field('items');
				sprToggleSheetCuttingRollUi(frm);
				const n = lines.length;
				const startIdx = n > 0 ? (frm.doc.items || []).length - n : 0;

				function maxRollBeforeNew() {
					let maxRoll = 0;
					const all = frm.doc.items || [];
					for (let i = 0; i < startIdx; i++) {
						const prev = all[i];
						if (prev.batch_no && String(prev.batch_no).indexOf('/') !== -1) {
							const parts = String(prev.batch_no).split('/');
							const p = parts[parts.length - 1];
							const num = parseInt(p, 10);
							if (!isNaN(num)) {
								maxRoll = Math.max(maxRoll, num);
							}
						}
						if (prev.roll_no !== undefined && prev.roll_no !== null && prev.roll_no !== '') {
							const num = parseInt(String(prev.roll_no), 10);
							if (!isNaN(num)) {
								maxRoll = Math.max(maxRoll, num);
							}
						}
					}
					return maxRoll;
				}

				function finishCreateEntry() {
					sprSyncBundleProducedSheets(frm, { silent: true });
					sprScheduleTotalProducedSync(frm);
					const totalRows = (frm.doc.items || []).length;
					const start = Math.max(0, totalRows - n);
					for (let i = start; i < totalRows; i++) {
						const it = (frm.doc.items || [])[i];
						if (it && it.name) {
							spr_update_produced_gsm_with_retry(frm, 'Shaft Production Run Item', it.name);
						}
					}
					if (totalRows <= 250) {
						schedule_spr_item_row_styles(frm);
					}
					spr_schedule_grid_ui_debounced(frm, { delay: 300 });
					spr_after_child_table_refresh(frm);
					sprAutoSaveAfterCreateEntry(frm);
					frappe.show_alert({
						message: __('Added {0} roll line(s) for bundle.', [lines.length]),
						indicator: 'green',
					});
				}

				if (n > 0) {
					frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_next_spr_batch_numbers',
						args: {
							shaft_production_run: frm.doc.name,
							count: n,
							start_roll_no: maxRollBeforeNew() + 1,
						},
						callback: function (br) {
							const batches = br.message || [];
							const all = frm.doc.items || [];
							for (let i = 0; i < n; i++) {
								const it = all[startIdx + i];
								if (!it) {
									continue;
								}
								if (batches[i]) {
									it.batch_no = batches[i].batch_no || batches[i];
									if (batches[i].roll_no != null) {
										it.roll_no = batches[i].roll_no;
									}
								}
							}
							frm.refresh_field('items');
							finishCreateEntry();
						},
						error: finishCreateEntry,
					});
				} else {
					finishCreateEntry();
				}
			},
		});
	},
});

frappe.ui.form.on('Shaft Production Run Job', {
	create_roll_entry: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const job_id = row.job_id;
		if (!job_id) {
			frappe.msgprint(__('Job ID is required'));
			return;
		}
		if (frm.is_new() || !frm.doc.name) {
			frappe.msgprint(__('Save the Shaft Production Run before creating roll lines.'));
			return;
		}
		function invokeBuildRollLines(laminationRollsPerCombo, laminationExactRollLines, appendMode, exactRollLines) {
			const args = {
				shaft_production_run: frm.doc.name,
				job_id: String(job_id),
			};
			const lrc = cint(laminationRollsPerCombo);
			if (lrc > 0) {
				args.lamination_rolls_per_combination = lrc;
			}
			const lex = cint(laminationExactRollLines);
			if (lex > 0) {
				args.lamination_exact_roll_lines = lex;
			}
			const ex = cint(exactRollLines);
			if (ex > 0) {
				args.exact_roll_lines = ex;
			}
			frappe.call({
			method:
				'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.build_spr_roll_result_lines_for_job',
			args: args,
			freeze: true,
			freeze_message: __('Creating roll lines for this job...'),
			callback: function (r) {
				const lines = r.message || [];
				if (!appendMode) {
					remove_spr_items_for_job(frm, job_id);
				}
				lines.forEach(function (line) {
					let it = frm.add_child('items');
					Object.keys(line).forEach(function (k) {
						if (line[k] !== undefined && line[k] !== null) {
							it[k] = line[k];
						}
					});
				});
				frm.refresh_field('items');
				const n = lines.length;
				const startIdx = n > 0 ? (frm.doc.items || []).length - n : 0;

				function maxRollBeforeNew() {
					let maxRoll = 0;
					const all = frm.doc.items || [];
					for (let i = 0; i < startIdx; i++) {
						const row = all[i];
						if (row.batch_no && String(row.batch_no).indexOf('/') !== -1) {
							const parts = String(row.batch_no).split('/');
							const p = parts[parts.length - 1];
							const num = parseInt(p, 10);
							if (!isNaN(num)) {
								maxRoll = Math.max(maxRoll, num);
							}
						}
						if (row.roll_no !== undefined && row.roll_no !== null && row.roll_no !== '') {
							const num = parseInt(String(row.roll_no), 10);
							if (!isNaN(num)) {
								maxRoll = Math.max(maxRoll, num);
							}
						}
					}
					return maxRoll;
				}

				function finishCreateEntry() {
					update_shaft_job_achieved_from_items(frm);
					sprScheduleTotalProducedSync(frm);
					spr_apply_fabric100_item_grid_columns(frm);
					spr_after_child_table_refresh(frm);
					sprAutoSaveAfterCreateEntry(frm);
					frappe.show_alert({
						message: __('Added {0} roll line(s) for job {1}.', [lines.length, job_id]),
						indicator: 'green',
					});
				}

				if (n > 0) {
					frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_next_spr_batch_numbers',
						args: {
							shaft_production_run: frm.doc.name,
							count: n,
							client_max_roll: maxRollBeforeNew(),
							run_date: frm.doc.run_date,
							custom_unit: frm.doc.custom_unit,
							shift: frm.doc.shift,
						},
						callback: function (r2) {
							const nums = r2.message || [];
							const fresh = frm.doc.items || [];
							for (let i = 0; i < nums.length; i++) {
								const row = fresh[startIdx + i];
								if (row && nums[i]) {
									// Direct assignment is much faster than model.set_value (which triggers grid events per row).
									if (nums[i].batch_no) row.batch_no = nums[i].batch_no;
									if (nums[i].roll_no !== undefined && nums[i].roll_no !== null) row.roll_no = nums[i].roll_no;
								}
							}
							frm.refresh_field('items');
							finishCreateEntry();
						},
						error: function () {
							finishCreateEntry();
						},
					});
				} else {
					finishCreateEntry();
				}
			},
		});
		}

		const rollPromptMeta = sprRollPromptMeta(frm, row);
		if (rollPromptMeta) {
			frappe.prompt(
				[
					{
						fieldname: 'roll_lines_to_add',
						fieldtype: 'Int',
						label: __('Roll lines to add'),
						reqd: 1,
						default: cint(rollPromptMeta.defaultLines) || 1,
						description: rollPromptMeta.description,
					},
				],
				function (values) {
					const n = cint(values.roll_lines_to_add);
					if (n < 1) {
						frappe.msgprint(__('Enter at least 1 roll line.'));
						return;
					}
				if (sprUsesLaminationRollPrompt(frm)) {
					invokeBuildRollLines(0, n, true, 0);
				} else if (sprUsesPrintingRollPrompt(frm)) {
					invokeBuildRollLines(0, 0, true, n);
				} else {
					// Slitting, Rewinding, Sheet Cutting, BOPP Film — exact roll lines
					invokeBuildRollLines(0, 0, true, n);
				}
				},
				rollPromptMeta.title,
				__('Add')
			);
			return;
		}
		invokeBuildRollLines(0, 0, false);
	},
});

frappe.ui.form.on('Shaft Production Run Item', {
	custom_total_produced_sheets: function (frm) {
		sprSyncBundleProducedSheets(frm);
	},
	net_weight: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const rounded = spr_round_net_weight_kg(row.net_weight);
		if (Math.abs(flt(row.net_weight) - rounded) > 1e-6) {
			frappe.model.set_value(cdt, cdn, 'net_weight', rounded);
			return;
		}
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
		update_shaft_job_achieved_from_items(frm);
		// Avoid hard grid refresh while typing; it can reset in-cell editor values.
		schedule_spr_item_row_styles(frm);
		sprScheduleTotalProducedSync(frm);
	},
	gross_weight: function (frm, cdt, cdn) {
		// Calculate net_weight instantly when gross_weight changes
		const row = locals[cdt][cdn];
		let width = flt(row.width_inch);
		let gw = flt(row.gross_weight);
		if (gw <= 0) {
			// Operator cleared gross weight: clear dependent computed values immediately.
			frappe.model.set_value(cdt, cdn, 'net_weight', 0);
			frappe.model.set_value(cdt, cdn, 'produced_gsm', 0);
			update_shaft_job_achieved_from_items(frm);
			sprScheduleTotalProducedSync(frm);
			schedule_spr_item_row_styles(frm);
			return;
		}
		
		if (width > 0 && gw > 0) {
			let width_in_meter = width * 0.0254;
			let gsm_val = flt(row.gsm) || flt(row.sticker_gsm) || 90;
			let raw_weight = (gsm_val * width_in_meter * gw) / 1000;
			const standard_widths = [63, 85, 90, 118, 126];
			let is_standard = standard_widths.some(w => Math.abs(width - w) < 0.01);
			
			let core_weight = 0;
			if (is_standard) {
				let base_weight_of_core = 1.3;
				if (raw_weight >= 50 && raw_weight <= 100) {
					base_weight_of_core = 1.8;
				} else if (raw_weight > 100) {
					base_weight_of_core = 2.5;
				}
				let numeric_core_width = parseFloat(row.custom_core_width_mm) || 1600;
				core_weight = (base_weight_of_core / 1600) * numeric_core_width;
			} else {
				let core_width, prorate;
				if (width < 63) { core_width = 63; prorate = 1.30; }
				else if (width < 85) { core_width = 85; prorate = 1.75; }
				else if (width < 90) { core_width = 90; prorate = 1.86; }
				else if (width < 118) { core_width = 118; prorate = 2.43; }
				else { core_width = 126; prorate = 2.60; }
				core_weight = (width / core_width) * prorate;
			}
			
			let calc_net = gw - core_weight;
			let net_val = calc_net > 0 ? calc_net : gw;
			net_val = spr_round_net_weight_kg(net_val);
			frappe.model.set_value(cdt, cdn, 'net_weight', net_val);

			// Also calculate produced_gsm immediately
			let mr = sprResolveLengthMeters(row) || 0;
			let newGsm = 0;
			if (net_val > 0 && width > 0 && mr > 0) {
				newGsm = Math.round((net_val * 1000) / (width * mr * 0.0254) * 100) / 100;
			}
			frappe.model.set_value(cdt, cdn, 'produced_gsm', newGsm);
		}

		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
		update_shaft_job_achieved_from_items(frm);
		sprScheduleTotalProducedSync(frm);
	},
	gsm: function (frm) {
		schedule_spr_item_row_styles(frm);
	},
	width_inch: function (frm, cdt, cdn) {
		// Recalculate produced_gsm when width changes
		const row = locals[cdt][cdn];
		let nw = flt(row.net_weight) || 0;
		let wi = flt(row.width_inch) || 0;
		let mr = sprResolveLengthMeters(row) || 0;
		
		let newGsm = 0;
		if (nw > 0 && wi > 0 && mr > 0) {
			newGsm = Math.round((nw * 1000) / (wi * mr * 0.0254) * 100) / 100;
		}
		
		frappe.model.set_value(cdt, cdn, 'produced_gsm', newGsm);
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
	},
	meter_roll: function (frm, cdt, cdn) {
		// Recalculate produced_gsm when meter_roll changes
		const row = locals[cdt][cdn];
		let nw = flt(row.net_weight) || 0;
		let wi = flt(row.width_inch) || 0;
		let mr = sprResolveLengthMeters(row) || 0;
		
		let newGsm = 0;
		if (nw > 0 && wi > 0 && mr > 0) {
			newGsm = Math.round((nw * 1000) / (wi * mr * 0.0254) * 100) / 100;
		}
		
		frappe.model.set_value(cdt, cdn, 'produced_gsm', newGsm);
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
		try {
			update_shaft_job_achieved_from_items(frm);
		} catch (e) {}
	},
	produced_length_mtrs: function (frm, cdt, cdn) {
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
		try {
			update_shaft_job_achieved_from_items(frm);
		} catch (e) {}
	},
	meter_roll_mtrs: function (frm, cdt, cdn) {
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
		try {
			update_shaft_job_achieved_from_items(frm);
		} catch (e) {}
	},
	ordered_length: function (frm, cdt, cdn) {
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
	},
	ordered_length_mtrs: function (frm, cdt, cdn) {
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
	},
	custom_ordered_length: function (frm, cdt, cdn) {
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
	},
	produced_gsm: function (frm) {
		// Keep this lightweight to avoid typing lag in grid editors.
		schedule_spr_item_row_styles(frm);
	},
	
	/**
	 * OVERRIDE: Ensure net_weight calculation runs ONLY based on gross_weight & core_weight
	 * NOT dependent on meter_roll (which may be empty when bundle packaging sets gross_weight)
	 * This handler runs AFTER any old conflicting scripts to guarantee correct behavior
	 */
	custom_net_weight_trigger: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		let width = flt(row.width_inch);
		let gw = flt(row.gross_weight);
		
		// Net weight calculation should ONLY depend on gross_weight & width, NOT meter_roll
		if (width > 0 && gw > 0) {
			let width_in_meter = width * 0.0254;
			let gsm_val = flt(row.gsm) || flt(row.sticker_gsm) || 90;
			let raw_weight = (gsm_val * width_in_meter * gw) / 1000;
			const standard_widths = [63, 85, 90, 118, 126];
			let is_standard = standard_widths.some(w => Math.abs(width - w) < 0.01);
			
			let core_weight = 0;
			if (is_standard) {
				let base_weight_of_core = 1.3;
				if (raw_weight >= 50 && raw_weight <= 100) {
					base_weight_of_core = 1.8;
				} else if (raw_weight > 100) {
					base_weight_of_core = 2.5;
				}
				let numeric_core_width = parseFloat(row.custom_core_width_mm) || 1600;
				core_weight = (base_weight_of_core / 1600) * numeric_core_width;
			} else {
				let core_width, prorate;
				if (width < 63) { core_width = 63; prorate = 1.30; }
				else if (width < 85) { core_width = 85; prorate = 1.75; }
				else if (width < 90) { core_width = 90; prorate = 1.86; }
				else if (width < 118) { core_width = 118; prorate = 2.43; }
				else { core_width = 126; prorate = 2.60; }
				core_weight = (width / core_width) * prorate;
			}
			
			let calc_net = gw - core_weight;
			let net_val = calc_net > 0 ? calc_net : gw;
			row.net_weight = spr_round_net_weight_kg(net_val);
		}
	},
	
	/**
	 * FINAL: Calculate produced_gsm only when ALL three values are ready
	 * This runs last to ensure net_weight is already set
	 */
	final_produced_gsm_calc: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		let nw = flt(row.net_weight) || 0;
		let wi = flt(row.width_inch) || 0;
		let mr = sprResolveLengthMeters(row) || 0;
		
		if (nw > 0 && wi > 0 && mr > 0) {
			let newGsm = Math.round((nw * 1000) / (wi * mr * 0.0254) * 100) / 100;
			frappe.model.set_value(cdt, cdn, 'produced_gsm', newGsm);
		} else {
			frappe.model.set_value(cdt, cdn, 'produced_gsm', 0);
		}
	},
	/**
	 * Save this roll line, lock it for editing, and reveal Print Label.
	 * Until Save Row: Print Label stays hidden (see spr_apply_items_row_lock_ui).
	 */
	save_row: function (frm, cdt, cdn) {
		if (frm.is_new()) {
			frappe.msgprint(__('Save the Shaft Production Run first.'));
			return;
		}
		if (frm.doc.docstatus && frm.doc.docstatus !== 0) {
			frappe.show_alert({ message: __('Submitted document cannot be edited from Save Row.'), indicator: 'orange' });
			return;
		}
		const row = locals[cdt][cdn];
		if (cint(row.row_locked)) {
			frappe.show_alert({ message: __('This row is already locked. Click Edit Row to change.'), indicator: 'blue' });
			return;
		}
		update_shaft_job_achieved_from_items(frm);
		frappe.model.set_value(cdt, cdn, 'row_locked', 1);
		if (frappe.meta.get_docfield(cdt, 'row_ready_for_print')) {
			frappe.model.set_value(cdt, cdn, 'row_ready_for_print', 1);
		}
		const save_promise = frm.save();
		function afterSprRowSave() {
			spr_schedule_item_row_styles_after_doc_write(frm);
			[0, 50, 200, 500].forEach(function (ms) {
				setTimeout(function () {
					spr_apply_items_row_lock_ui(frm);
					spr_schedule_grid_ui_debounced(frm, { delay: 0 });
				}, ms);
			});
			frappe.show_alert({ message: __('Row saved. Print Label is available.'), indicator: 'green' });
		}
		if (save_promise && typeof save_promise.then === 'function') {
			save_promise.then(afterSprRowSave);
		} else {
			setTimeout(afterSprRowSave, 400);
		}
	},
	/** Print roll label (after Save Row). */
	print_sticker: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!cint(row.row_ready_for_print) || !cint(row.row_locked)) {
			frappe.msgprint(__('Save Row first to lock the line and enable the label.'));
			return;
		}
		// Button control only - user manages label format
		frappe.msgprint(__('Production Label ready to print'));
	},
	/** Unlock this row for editing; hide Print Label until Save Row again. */
	edit_row: function (frm, cdt, cdn) {
		if (frm.is_new() || (frm.doc.docstatus && frm.doc.docstatus !== 0)) {
			return;
		}
		frappe.model.set_value(cdt, cdn, 'row_locked', 0);
		if (frappe.meta.get_docfield(cdt, 'row_ready_for_print')) {
			frappe.model.set_value(cdt, cdn, 'row_ready_for_print', 0);
		}
		const save_promise = frm.save();
		function afterSprEditSave() {
			spr_schedule_item_row_styles_after_doc_write(frm);
			[0, 50, 200].forEach(function (ms) {
				setTimeout(function () {
					spr_apply_items_row_lock_ui(frm);
					spr_schedule_grid_ui_debounced(frm, { delay: 0 });
				}, ms);
			});
			frappe.show_alert({ message: __('Row unlocked for editing.'), indicator: 'blue' });
		}
		if (save_promise && typeof save_promise.then === 'function') {
			save_promise.then(afterSprEditSave);
		} else {
			setTimeout(afterSprEditSave, 400);
		}
	},
});

function sprResolveWidthInchForGsm(frm, row) {
	const wi = flt(row && row.width_inch);
	if (wi > 0 && wi < 500) {
		return wi;
	}
	return 0;
}

function spr_update_produced_gsm(frm, cdt, cdn) {
	if (!frappe.meta.get_docfield('Shaft Production Run Item', 'produced_gsm')) {
		return;
	}
	const row = locals[cdt][cdn];

	// Keep sticker GSM aligned to item-code rule: positions 9..11.
	const stickerGsm = sprStickerGsmFromItemCode(row.item_code);
	if (stickerGsm > 0) {
		if (flt(row.gsm) !== stickerGsm) {
			frappe.model.set_value(cdt, cdn, 'gsm', stickerGsm);
		}
		if (frappe.meta.get_docfield('Shaft Production Run Item', 'custom_sticker_gsm') && flt(row.custom_sticker_gsm) !== stickerGsm) {
			frappe.model.set_value(cdt, cdn, 'custom_sticker_gsm', stickerGsm);
		}
	}

	// Keep lamination GSM aligned to item-code suffix map (e.g. "-C" => 15).
	if (frappe.meta.get_docfield('Shaft Production Run Item', 'custom_lam_gsm')) {
		const lamGsm = sprLaminationGsmFromItemCode(row.item_code);
		if (lamGsm > 0 && flt(row.custom_lam_gsm) !== lamGsm) {
			frappe.model.set_value(cdt, cdn, 'custom_lam_gsm', lamGsm);
		}
	}
	
	// Get weight: prefer net_weight, fallback to gross_weight
	let nw = flt(row.net_weight);
	if (nw <= 0) {
		nw = flt(row.gross_weight);
	}
	
	const wi = sprResolveWidthInchForGsm(frm, row);

	const mr = sprResolveLengthMeters(row);
	
	// Calculate GSM only if all required values are present
	// Formula: (net_weight * 1000) / (width_inch * length_mtrs * 0.0254)
	let pgsm = 0;
	if (nw > 0 && wi > 0 && mr > 0) {
		pgsm = Math.round((nw * 1000) / (wi * mr * 0.0254) * 100) / 100;
	}
	
	frappe.model.set_value(cdt, cdn, 'produced_gsm', pgsm);
	// Avoid full grid refresh on every keypress (causes lag and cursor jumps).
	apply_spr_item_row_styles(frm);
	schedule_spr_item_row_styles(frm);
}

function spr_update_produced_gsm_with_retry(frm, cdt, cdn) {
	[0, 80, 220].forEach(function (ms) {
		setTimeout(function () {
			try {
				spr_update_produced_gsm(frm, cdt, cdn);
			} catch (e) {
				// Ignore transient timing issues while rows are being populated.
			}
		}, ms);
	});
}

function sprResolveLengthMeters(doc) {
	const aliases = [
		'produced_length_mtrs',
		'meter_roll',
		'meter_roll_mtrs',
		'custom_meter_roll_mtrs',
		'ordered_length',
		'ordered_length_mtrs',
		'custom_ordered_length',
		'roll_mtrs',
		'roll',
	];
	for (let i = 0; i < aliases.length; i++) {
		const v = flt(doc[aliases[i]]);
		if (v > 0) {
			return v;
		}
	}
	return 0;
}

function fetch_and_show_pp_wo_summary(frm) {
	if (!frm.doc.production_plan) {
		return;
	}
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_production_plan_wo_summary',
		args: { production_plan: frm.doc.production_plan },
		callback: function (r) {
			show_pp_work_order_summary_dialog(r.message || []);
		},
		error: function () {
			show_pp_work_order_summary_dialog([]);
		},
	});
}

function show_pp_work_order_summary_dialog(rows) {
	const esc =
		frappe.utils && frappe.utils.escape_html
			? frappe.utils.escape_html
			: function (t) {
					return $('<div>').text(t || '').html();
				};
	let html;
	if (rows && rows.length) {
		let body =
			'<thead><tr><th>' +
			__('Work Order') +
			'</th><th>' +
			__('Status') +
			'</th><th>' +
			__('Order Qty') +
			'</th><th>' +
			__('Pending Qty') +
			'</th></tr></thead><tbody>';
		rows.forEach(function (r) {
			body +=
				'<tr><td>' +
				esc(r.work_order || '') +
				'</td><td>' +
				esc(r.status || '') +
				'</td><td>' +
				flt(r.order_qty, 3) +
				'</td><td>' +
				flt(r.pending_qty, 3) +
				'</td></tr>';
		});
		body += '</tbody>';
		html =
			'<div class="table-responsive"><table class="table table-bordered table-condensed">' +
			body +
			'</table></div>';
	} else {
		html =
			'<p class="text-muted">' +
			__('No Work Orders linked to this Production Plan.') +
			'</p>';
	}
	// Next tick so dialog is not blocked by freeze/refresh from the previous call chain
	setTimeout(function () {
		try {
			const d = new frappe.ui.Dialog({
				title: __('Production Plan — Work Orders'),
				fields: [{ fieldtype: 'HTML', fieldname: 'wo_table', options: html }],
				primary_action_label: __('OK'),
				primary_action: function () {
					d.hide();
				},
			});
			d.show();
		} catch (e) {
			frappe.msgprint({
				title: __('Production Plan — Work Orders'),
				message: html,
				indicator: 'blue',
				wide: true,
			});
		}
	}, 200);
}

function remove_spr_items_for_job(frm, job_id) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) {
		return;
	}
	const names = (frm.doc.items || [])
		.filter(function (d) {
			return String(d.job) === String(job_id);
		})
		.map(function (d) {
			return d.name;
		});
	names.forEach(function (name) {
		const gr = grid.grid_rows_by_docname && grid.grid_rows_by_docname[name];
		if (gr && gr.remove) {
			gr.remove();
			return;
		}
		const idx = (frm.doc.items || []).findIndex(function (d) {
			return d.name === name;
		});
		if (idx !== -1 && grid.grid_rows && grid.grid_rows[idx]) {
			grid.grid_rows[idx].remove();
		}
	});
}

function sprNormalizeJobKey(v) {
	if (v === undefined || v === null) {
		return '';
	}
	const s = String(v).trim();
	return s;
}

function sprShaftJobRowKey(sj) {
	if (!sj) {
		return '';
	}
	const id = sj.job_id;
	if (id !== undefined && id !== null && String(id).trim() !== '') {
		return sprNormalizeJobKey(id);
	}
	return sprNormalizeJobKey(sj.job_no);
}

function sprUsesLaminationRollPrompt(frm) {
	return frm && frm.doc && cint(frm.doc.custom_is_lamination);
}

function sprUsesSlittingRollPrompt(frm) {
	return frm && frm.doc && cint(frm.doc.custom_is_slitting);
}

function sprUsesRewindingRollPrompt(frm) {
	return frm && frm.doc && cint(frm.doc.custom_is_rewinding);
}

function sprUsesSheetCuttingRollPrompt(frm) {
	return sprIsSheetCutting(frm);
}

function sprIsBag(frm) {
	if (!frm || !frm.doc) {
		return false;
	}
	return cint(frm.doc.custom_is_box_bag);
}

function sprIsBundlePackagingMode(frm) {
	return sprIsSheetCutting(frm) || sprIsBag(frm);
}

function sprIsSheetCutting(frm) {
	if (!frm || !frm.doc) {
		return false;
	}
	if (cint(frm.doc.custom_is_sheet_cutting)) {
		return true;
	}
	const u = String(frm.doc.custom_unit || '').trim();
	return u === 'JVE - SHEET CUTTING MACHINE';
}

function sprLoadShaftJobsFromPp(frm) {
	if (!frm || !frm.doc || !frm.doc.production_plan) {
		return;
	}
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_job_rows_for_production_plan',
		args: { production_plan: frm.doc.production_plan },
		freeze: true,
		freeze_message: __('Loading shaft jobs from Production Plan...'),
		callback: function (r) {
			frm.clear_table('shaft_jobs');
			(r.message || []).forEach(function (row) {
				const c = frm.add_child('shaft_jobs');
				Object.keys(row).forEach(function (k) {
					if (row[k] !== undefined && row[k] !== null) {
						c[k] = row[k];
					}
				});
			});
			frm.refresh_field('shaft_jobs');
			frm.clear_table('items');
			frm.refresh_field('items');
			spr_after_child_table_refresh(frm);
			fetch_and_show_pp_wo_summary(frm);
		},
		error: function () {
			frm.clear_table('items');
			frm.refresh_field('items');
			spr_after_child_table_refresh(frm);
			fetch_and_show_pp_wo_summary(frm);
		},
	});
}

function sprLoadBundleCalculationFromPp(frm, presetRows) {
	if (!frm || !frm.doc || !frm.doc.production_plan) {
		return;
	}
	frm.clear_table('shaft_jobs');
	frm.refresh_field('shaft_jobs');
	function applyRows(rows) {
		frm.clear_table('bundle_calculation');
		(rows || []).forEach(function (row) {
			const c = frm.add_child('bundle_calculation');
			Object.keys(row).forEach(function (k) {
				if (row[k] !== undefined && row[k] !== null) {
					c[k] = row[k];
				}
			});
			if (sprIsBag(frm)) {
				const bz = row.bag_size || row.sheet_cutting_size || '';
				if (bz) {
					c.bag_size = bz;
					c.sheet_cutting_size = bz;
				}
			}
		});
		frm.refresh_field('bundle_calculation');
		sprToggleBundleCalculationGrid(frm);
		sprSyncBundleProducedSheets(frm, { silent: true });
		frm.clear_table('items');
		frm.refresh_field('items');
		spr_after_child_table_refresh(frm);
		fetch_and_show_pp_wo_summary(frm);
	}
	if (presetRows && presetRows.length) {
		applyRows(presetRows);
		return;
	}
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_bundle_calculation_rows_for_production_plan',
		args: {
			production_plan: frm.doc.production_plan,
			order_code: frm.doc.custom_order_code || '',
			order_meter: 0,
		},
		freeze: true,
		freeze_message: __('Loading bundle calculation from Production Plan...'),
		callback: function (r) {
			applyRows(r.message || []);
		},
		error: function () {
			applyRows([]);
		},
	});
}

function sprToggleSheetCuttingUi(frm) {
	if (!frm) {
		return;
	}
	const isBundleMode = sprIsBundlePackagingMode(frm);
	const isBag = sprIsBag(frm);
	try {
		frm.set_df_property('section_break_9', 'hidden', isBundleMode ? 1 : 0);
		frm.set_df_property('shaft_jobs', 'hidden', isBundleMode ? 1 : 0);
	} catch (e) {
		/* ignore */
	}
	try {
		if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_planned_qty')) {
			frm.set_df_property('custom_total_planned_qty', 'hidden', isBag ? 1 : 0);
		}
		if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_planned_pcs')) {
			frm.set_df_property('custom_total_planned_pcs', 'hidden', isBag ? 0 : 1);
		}
		if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_achieved_pcs')) {
			frm.set_df_property('custom_total_achieved_pcs', 'hidden', isBag ? 0 : 1);
		}
		if (frappe.meta.get_docfield('Shaft Production Run', 'total_produced_weight')) {
			frm.set_df_property(
				'total_produced_weight',
				'label',
				isBag ? __('Total Produced Bag PCS') : __('Total Produced Weight (KG)')
			);
			frm.set_df_property('total_produced_weight', 'precision', isBag ? 0 : 2);
		}
	} catch (e) {
		/* ignore */
	}
	sprToggleSheetCuttingRollUi(frm);
}

function sprEnsureBundleRowsFromPp(frm) {
	if (!frm || !frm.doc || !frm.doc.production_plan || !sprIsBag(frm)) {
		return;
	}
	if ((frm.doc.bundle_calculation || []).length) {
		return;
	}
	sprLoadBundleCalculationFromPp(frm, null);
}

function spr_force_sheet_cutting_item_grid_columns(grid) {
	if (!grid) {
		return;
	}
	const show = [
		'quality',
		'color',
		'gsm',
		'custom_sheet_size',
		'custom_planned_sheets_pcs',
		'custom_total_produced_sheets',
		'custom_planned_bag_pcs',
		'custom_achieved_bag_pcs',
	];
	show.forEach(function (fn) {
		try {
			if (typeof grid.update_docfield_property === 'function') {
				grid.update_docfield_property(fn, 'hidden', 0);
				grid.update_docfield_property(fn, 'in_list_view', 1);
			}
		} catch (e) {
			/* ignore */
		}
	});
}

function spr_bundle_bag_size_col() {
	return frappe.meta.get_docfield('Bundle Calculation', 'bag_size')
		? 'bag_size'
		: 'sheet_cutting_size';
}

function spr_get_bundle_list_view_config(frm) {
	if (sprIsBag(frm)) {
		const bagCol = spr_bundle_bag_size_col();
		return {
			show: [
				'item_code',
				bagCol,
				'no_of_boxes',
				'pcs_per_packet',
				'total_pcs_per_bundle',
				'work_order',
				'order_code',
				'create_bundle_entry',
				'total_consumed_meter',
				'total_produced_bag_pcs',
			],
			hide: [
				bagCol === 'bag_size' ? 'sheet_cutting_size' : 'bag_size',
				'no_of_bundles',
				'pkts_per_bundle',
				'job',
				'total_produced_sheets',
				'total_achieved_weight',
			],
		};
	}
	if (sprIsSheetCutting(frm)) {
		return {
			show: [
				'item_code',
				'sheet_cutting_size',
				'no_of_bundles',
				'pkts_per_bundle',
				'pcs_per_packet',
				'total_pcs_per_bundle',
				'work_order',
				'order_code',
				'job',
				'create_bundle_entry',
				'total_consumed_meter',
				'total_produced_sheets',
				'total_achieved_weight',
			],
			hide: ['bag_size', 'no_of_boxes', 'total_produced_bag_pcs'],
		};
	}
	return { show: [], hide: [] };
}

function sprToggleBundleCalculationGrid(frm) {
	if (!frm || !frm.fields_dict || !frm.fields_dict.bundle_calculation) {
		return;
	}
	const grid = frm.fields_dict.bundle_calculation.grid;
	if (!grid) {
		return;
	}
	const isBag = sprIsBag(frm);
	if (isBag && typeof grid.update_docfield_property === 'function') {
		grid.update_docfield_property('bag_size', 'label', __('Bag Size'));
		grid.update_docfield_property('sheet_cutting_size', 'label', __('Bag Size (alt)'));
		grid.update_docfield_property('pcs_per_packet', 'label', __('Pcs per Box'));
		grid.update_docfield_property('total_pcs_per_bundle', 'label', __('Total Planned Pcs'));
	}
	spr_sync_grid_columns_visible(frm, 'bundle_calculation');
}

function sprToggleSheetCuttingRollUi(frm) {
	const isSc = sprIsSheetCutting(frm);
	const isBag = sprIsBag(frm);
	const useBundlePcsCols = isSc || isBag;
	const hideWidthCol = isSc || isBag ? 1 : 0;
	const fd = frm && frm.fields_dict ? frm.fields_dict.items : null;
	const grid = fd && fd.grid;
	if (grid) {
		if (isSc) {
			spr_set_grid_col_hidden(grid, 'quality', 0);
			spr_set_grid_col_hidden(grid, 'color', 0);
			spr_set_grid_col_hidden(grid, 'gsm', 0);
			spr_set_grid_col_hidden(grid, 'custom_fabric_gsm', 1);
			spr_set_grid_col_hidden(grid, 'custom_lam_gsm', 1);
			spr_force_sheet_cutting_item_grid_columns(grid);
		}
		if (isBag && typeof grid.update_docfield_property === 'function') {
			grid.update_docfield_property('custom_sheet_size', 'label', __('Bag Size'));
			grid.update_docfield_property('custom_planned_bag_pcs', 'label', __('Planned Bag PCS'));
			grid.update_docfield_property('custom_achieved_bag_pcs', 'label', __('Achieved Bag PCS'));
		}
		spr_set_grid_col_hidden(grid, 'width_inch', hideWidthCol);
		spr_sync_grid_columns_visible(frm, 'items');
	}
	sprToggleBundleCalculationGrid(frm);
	if (useBundlePcsCols) {
		spr_schedule_grid_ui_debounced(frm, { delay: 200 });
	}
}

function sprUsesBoppFilmRollPrompt(frm) {
	return frm && frm.doc && cint(frm.doc.custom_is_bopp_film);
}

function sprUsesPrintingRollPrompt(frm) {
	return frm && frm.doc && cint(frm.doc.custom_is_printing);
}

function sprRollPromptMeta(frm, row) {
	const fromPp = cint((row && row.no_of_rolls) || 0);
	const noOfRollsCreated = cint((frm && frm.doc && frm.doc.custom_no_of_rolls_created) || 0);
	const defaultLines = noOfRollsCreated > 0 ? noOfRollsCreated : (fromPp > 0 ? fromPp : 1);
	const unitText = String((frm && frm.doc && (frm.doc.custom_unit || frm.doc.unit || frm.doc.workstation || "")) || "").toLowerCase();
	const isPrintingJob = unitText.includes("printing") || unitText.includes("105");
	if (sprUsesSlittingRollPrompt(frm)) {
		return {
			title: __('Slitting — add roll lines'),
			description: __('Defaults to No. of Rolls from Production Plan for this job.'),
			defaultLines: defaultLines,
		};
	}
	if (sprUsesLaminationRollPrompt(frm)) {
		return {
			title: __('Lamination — add roll lines'),
			description: __('Adds exactly this many new roll lines for the selected job.'),
			defaultLines: defaultLines,
		};
	}
	if (sprUsesRewindingRollPrompt(frm)) {
		return {
			title: __('Rewinding — add roll lines'),
			description: __('Adds exactly this many new roll lines for the selected rewinding job.'),
			defaultLines: defaultLines,
		};
	}
	if (sprUsesSheetCuttingRollPrompt(frm)) {
		return {
			title: __('Sheet Cutting — add roll lines'),
			description: __('Adds exactly this many new roll lines for the selected sheet cutting job.'),
			defaultLines: defaultLines,
		};
	}
	if (sprUsesBoppFilmRollPrompt(frm)) {
		return {
			title: isPrintingJob ? __('Printing — add roll lines') : __('BOPP Film — add roll lines'),
			description: isPrintingJob ? __('Adds exactly this many new roll lines for the selected printing job.') : __('Adds exactly this many new roll lines for the selected BOPP printing job.'),
			defaultLines: defaultLines,
		};
	}
	if (sprUsesPrintingRollPrompt(frm)) {
		return {
			title: __('Printing — add roll lines'),
			description: __('Adds exactly this many new roll lines for the selected printing job.'),
			defaultLines: defaultLines,
		};
	}
	return null;
}

/** Hide duplicate Produced GSM custom fields (site Customize may add a second column). */
function spr_hide_duplicate_produced_gsm_columns(frm) {
	const grid = frm && frm.fields_dict && frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) {
		return;
	}
	const hideNames = ['custom_produced_gsm', 'produced_gsm_copy'];
	hideNames.forEach(function (fn) {
		if (frappe.meta.get_docfield('Shaft Production Run Item', fn)) {
			spr_set_grid_col_hidden(grid, fn, 1);
		}
	});
	try {
		(frappe.get_meta('Shaft Production Run Item').fields || []).forEach(function (df) {
			if (
				df.fieldname &&
				df.fieldname !== 'produced_gsm' &&
				String(df.label || '').trim() === 'Produced GSM'
			) {
				spr_set_grid_col_hidden(grid, df.fieldname, 1);
			}
		});
	} catch (e) {
		/* ignore */
	}
}

function sprHasFabric100Rows(frm) {
	return (frm && frm.doc && (frm.doc.items || [])).some(function (row) {
		const ic = String((row && row.item_code) || '').trim().toUpperCase();
		return ic.startsWith('100') || /^[A-Z0-9]+-100/.test(ic);
	});
}

function sprIsFabric100Run(frm) {
	return sprRollProcessPrefix(frm) === '100' || sprHasFabric100Rows(frm);
}

function spr_get_items_list_view_config(frm) {
	if (sprIsFabric100Run(frm)) {
		return { show: SPR_FABRIC100_ITEMS_GRID_SHOW, hide: SPR_FABRIC100_ITEMS_GRID_HIDE };
	}
	if (sprIsBag(frm)) {
		return {
			show: [
				'batch_no',
				'party_code',
				'item_code',
				'custom_sheet_size',
				'gsm',
				'produced_gsm',
				'custom_planned_bag_pcs',
				'custom_achieved_bag_pcs',
				'meter_roll',
				'produced_length_mtrs',
				'net_weight',
				'gross_weight',
				'save_row',
				'work_order',
			],
			hide: [
				'width_inch',
				'custom_planned_sheets_pcs',
				'custom_total_produced_sheets',
				'quality',
				'color',
				'planned_qty',
			],
		};
	}
	if (sprIsSheetCutting(frm)) {
		return {
			show: [
				'batch_no',
				'party_code',
				'item_code',
				'custom_sheet_size',
				'quality',
				'color',
				'gsm',
				'produced_gsm',
				'custom_planned_sheets_pcs',
				'custom_total_produced_sheets',
				'net_weight',
				'gross_weight',
				'save_row',
				'work_order',
			],
			hide: [
				'width_inch',
				'meter_roll',
				'produced_length_mtrs',
				'custom_planned_bag_pcs',
				'custom_achieved_bag_pcs',
				'planned_qty',
			],
		};
	}
	return {
		show: [
			'planned_qty',
			'batch_no',
			'party_code',
			'meter_roll',
			'produced_length_mtrs',
			'produced_gsm',
			'gross_weight',
			'save_row',
			'quality',
			'color',
			'width_inch',
			'gsm',
			'custom_production_label',
			'edit_row',
			'work_order',
			'item_code',
			'item_name',
			'job',
			'net_weight',
			'custom_core_width_mm',
			'core_width',
			'custom_diameter_inches',
			'diameter',
			'custom_cbm_cubic_meters',
			'cbm',
			'custom_qc_approval_label',
			'qc_approval_label',
			'custom_planned_bag_pcs',
			'custom_achieved_bag_pcs',
			'row_ready_for_print',
			'row_locked',
			'row_printed',
			'custom_polybag_kgs',
			'polybag_kgs',
			'print_sticker',
		],
		hide: [],
	};
}

function spr_apply_fabric100_item_grid_columns(frm) {
	if (!sprIsFabric100Run(frm)) {
		return;
	}
	const grid = frm && frm.fields_dict && frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) {
		return;
	}
	const cfg = spr_get_items_list_view_config(frm);
	cfg.show.forEach(function (fn) {
		spr_set_grid_col_hidden(grid, fn, 0);
	});
	cfg.hide.forEach(function (fn) {
		spr_set_grid_col_hidden(grid, fn, 1);
	});
	spr_sync_grid_columns_visible(frm, 'items');
}

function sprToggleLaminationRollUi(frm) {
	const processPrefix = sprRollProcessPrefix(frm);
	const isLaminationProcess = processPrefix === '104' || processPrefix === '107';
	const showLamCols = isLaminationProcess || sprUsesLaminationRollPrompt(frm);
	const hasFabric100 = sprHasFabric100Rows(frm);
	// Fabric 100 rows always show planned qty; hide only on pure 104/107 lamination runs without fabric lines.
	const hidePlanned = showLamCols && !hasFabric100 ? 1 : 0;
	const hideLamCols = showLamCols ? 0 : 1;
	const fd = frm && frm.fields_dict ? frm.fields_dict.items : null;
	const grid = fd && fd.grid;
	if (grid) {
		spr_set_grid_col_hidden(grid, 'planned_qty', hidePlanned);
		spr_set_grid_col_hidden(grid, 'custom_fabric_gsm', hideLamCols);
		spr_set_grid_col_hidden(grid, 'custom_lam_gsm', hideLamCols);
		if (showLamCols) {
			spr_set_grid_col_hidden(grid, 'width_inch', 0);
			spr_set_grid_col_hidden(grid, 'meter_roll', 0);
			spr_set_grid_col_hidden(grid, 'produced_length_mtrs', 0);
		}
		spr_hide_duplicate_produced_gsm_columns(frm);
		spr_sync_grid_columns_visible(frm, 'items');
	}
	const $legend = fd && fd.$wrapper ? fd.$wrapper.prev('.spr-gsm-legend') : null;
	if ($legend && $legend.length) {
		$legend.toggle(showLamCols);
	}
}

function update_shaft_job_achieved_from_items(frm) {
	if (frm && frm.doc && cint(frm.doc.docstatus) !== 0) {
		return;
	}
	const hasW = frappe.meta.get_docfield('Shaft Production Run Job', 'custom_total_achieved_weight');
	const hasM = frappe.meta.get_docfield('Shaft Production Run Job', 'custom_total_achieved_meter');
	const hasHdrM = frappe.meta.get_docfield('Shaft Production Run', 'custom_total_achieved_meter');
	if (!hasW && !hasM && !hasHdrM) {
		return;
	}
	const weightByJob = {};
	const meterByJob = {};
	let meterTotal = 0;
	(frm.doc.items || []).forEach(function (it) {
		const pm = sprSumProducedLengthMeters(it);
		meterTotal += pm;
		const k = sprNormalizeJobKey(it.job);
		if (!k) {
			return;
		}
		if (hasW) {
			weightByJob[k] = (weightByJob[k] || 0) + spr_round_net_weight_kg(it.net_weight);
		}
		if (hasM) {
			meterByJob[k] = (meterByJob[k] || 0) + pm;
		}
	});
	let jobGridDirty = false;
	if (hasW) {
		(frm.doc.shaft_jobs || []).forEach(function (sj) {
			const jid = sprShaftJobRowKey(sj);
			const next = spr_round_net_weight_kg(jid && weightByJob[jid] !== undefined ? weightByJob[jid] : 0);
			const cur = flt(sj.custom_total_achieved_weight);
			if (Math.abs(cur - next) > 0.005) {
				frappe.model.set_value(sj.doctype, sj.name, 'custom_total_achieved_weight', next);
				jobGridDirty = true;
			}
		});
	}
	if (hasM) {
		(frm.doc.shaft_jobs || []).forEach(function (sj) {
			const jid = sprShaftJobRowKey(sj);
			const next = flt(jid && meterByJob[jid] !== undefined ? meterByJob[jid] : 0, 2);
			const cur = flt(sj.custom_total_achieved_meter);
			if (Math.abs(cur - next) > 0.005) {
				frappe.model.set_value(sj.doctype, sj.name, 'custom_total_achieved_meter', next);
				jobGridDirty = true;
			}
		});
	}
	if (jobGridDirty) {
		try { frm.refresh_field('shaft_jobs'); } catch (e) {}
	}
	if (hasHdrM) {
		const curH = flt(frm.doc.custom_total_achieved_meter);
		const nextH = flt(meterTotal, 2);
		if (Math.abs(curH - nextH) > 0.005) {
			frm.set_value('custom_total_achieved_meter', nextH);
		}
	}
}

function spr_patch_child_grid_refresh(frm, fieldname) {
	if (!frm || !fieldname) {
		return;
	}
	const patchKey = '_spr_grid_patched_' + fieldname;
	if (frm[patchKey]) {
		return;
	}
	const fd = frm.fields_dict && frm.fields_dict[fieldname];
	if (!fd || !fd.grid) {
		return;
	}
	const grid = fd.grid;
	let hooked = false;
	function afterGridPaint() {
		if (fieldname === 'items') {
			spr_schedule_grid_ui_debounced(frm, { delay: 160, columns: false });
		} else {
			spr_sync_grid_columns_visible(frm, fieldname);
		}
	}
	function wrap(method) {
		const orig = grid[method];
		if (typeof orig !== 'function') {
			return;
		}
		const bound = orig.bind(grid);
		grid[method] = function () {
			const ret = bound.apply(grid, arguments);
			afterGridPaint();
			return ret;
		};
		hooked = true;
	}
	wrap('refresh');
	wrap('render');
	if (fieldname === 'items' && grid.wrapper && grid.wrapper.length && !frm._spr_items_grid_click_patched) {
		frm._spr_items_grid_click_patched = true;
		grid.wrapper.on('change input blur', 'input, textarea, select', function () {
			if (frm._spr_grid_input_debounce) {
				clearTimeout(frm._spr_grid_input_debounce);
			}
			frm._spr_grid_input_debounce = setTimeout(function () {
				frm._spr_grid_input_debounce = null;
				spr_schedule_grid_ui_debounced(frm, { delay: 280, columns: false });
			}, 200);
		});
	}
	if (hooked) {
		frm[patchKey] = true;
	}
}

function spr_patch_items_grid_refresh(frm) {
	SPR_SPR_CHILD_TABLE_FIELDS.forEach(function (fn) {
		spr_patch_child_grid_refresh(frm, fn);
	});
}

/** Legend for |Sticker GSM vs Produced GSM| bands (above Roll Production Results grid). */
function spr_inject_gsm_legend(frm) {
	const fd = frm.fields_dict && frm.fields_dict.items;
	if (!fd || !fd.$wrapper || !fd.$wrapper.length) {
		return;
	}
	if (fd.$wrapper.prev('.spr-gsm-legend').length) {
		return;
	}
	const html =
		'<div class="spr-gsm-legend alert alert-secondary" style="margin-bottom:8px;font-size:12px;line-height:1.5;">' +
		'<strong>' +
		__('Roll lines — GSM difference (Sticker GSM vs Produced GSM)') +
		'</strong><br>' +
		'<span style="display:inline-block;background:#bbf7d0;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">|diff| &lt; 1</span> ' +
		'<span style="display:inline-block;background:#eab308;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">1 - 2</span> ' +
		'<span style="display:inline-block;background:#fb923c;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">2 - 3</span> ' +
		'<span style="display:inline-block;background:#fecaca;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">&ge; 3</span> ' +
		'<span style="display:inline-block;background:#f3f4f6;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">' +
		__('Awaiting produced GSM / incomplete') +
		'</span>' +
		'</div>';
	fd.$wrapper.before(html);
	sprToggleLaminationRollUi(frm);
}

/** Sticker / planned GSM: field or parsed from item_code (same rule as server parse_item_code). */
function sprStickerGsmFromDoc(doc) {
	const fromCode = sprStickerGsmFromItemCode(doc && doc.item_code);
	if (fromCode > 0) {
		return fromCode;
	}
	const g = flt(doc && doc.gsm);
	return g > 0 ? g : 0;
}

/** True when produced length is missing or zero — do not infer GSM from ordered meter_roll (legend: incomplete / grey). */
function sprRollProducedLengthIncomplete(doc) {
	if (!frappe.meta.get_docfield('Shaft Production Run Item', 'produced_length_mtrs')) {
		return false;
	}
	const pl = doc.produced_length_mtrs;
	if (pl === undefined) {
		return false;
	}
	if (pl === null || pl === '') {
		return sprResolveLengthMeters(doc) <= 0;
	}
	// If produced_length_mtrs is set but <= 0, still allow fallback
	if (flt(pl) <= 0) {
		return sprResolveLengthMeters(doc) <= 0;
	}
	return false;
}

/** Same formula as spr_update_produced_gsm — use when produced_gsm not yet written (avoids all-white rows). */
function sprEffectiveProducedGsm(doc) {
	let p = flt(doc.produced_gsm);
	if (p > 0) {
		return p;
	}
	
	// Get weight: prefer net_weight, fallback to gross_weight
	let nw = flt(doc.net_weight);
	if (nw <= 0) {
		nw = flt(doc.gross_weight);
	}
	
	const wi = flt(doc.width_inch);
	const wiOk = wi > 0 && wi < 500 ? wi : 0;

	const mr = sprResolveLengthMeters(doc);

	if (nw > 0 && wiOk > 0 && mr > 0) {
		return Math.round((nw * 1000) / (wiOk * mr * 0.0254) * 100) / 100;
	}
	return 0;
}

function ensure_spr_item_stylesheet() {
	if (!window.__sprspr_lock_style) {
		window.__sprspr_lock_style = true;
		const lockCss = `
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]),
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]),
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) {
			pointer-events: none;
			opacity: 0.94;
		}
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) input,
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) textarea,
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) select,
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) input,
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) textarea,
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) select,
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) input,
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) textarea,
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="custom_approval_label"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) select {
			pointer-events: none !important;
			background-color: transparent !important;
		}
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col[data-fieldname="save_row"] button,
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col[data-fieldname="save_row"] button,
		.fieldname-items .grid-row.spr-spr-row-locked .col[data-fieldname="save_row"] button {
			display: none !important;
		}
		.form-group[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] button,
		.form-group[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] .btn,
		.form-group[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] a,
		.frappe-control[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] button,
		.frappe-control[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] .btn,
		.frappe-control[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] a,
		.fieldname-items .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] button,
		.fieldname-items .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] .btn,
		.fieldname-items .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] a,
		.form-group[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] button,
		.form-group[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] .btn,
		.form-group[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] a,
		.frappe-control[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] button,
		.frappe-control[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] .btn,
		.frappe-control[data-fieldname="items"] .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] a,
		.fieldname-items .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] button,
		.fieldname-items .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] .btn,
		.fieldname-items .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="custom_approval_label"] a {
			opacity: 0 !important;
			visibility: hidden !important;
			pointer-events: none !important;
		}
	`;
		$('head').append(`<style data-spr-row-lock="1">${lockCss}</style>`);
	}
	const sprItemsCssVer = '18';
	if (window.__sprspr_items_css_ver === sprItemsCssVer) {
		return;
	}
	window.__sprspr_items_css_ver = sprItemsCssVer;
	window.__sprspr_style = true;
	$('head style[data-spr-items]').remove();
	/* |Sticker GSM (gsm) vs Produced GSM (produced_gsm)|: <1 green, 1-2 yellow, 2-3 orange, 3+ red */
	const css = `
		.spr-items-wrap .spr-gsm-band-0 { background-color: #bbf7d0 !important; }
		.spr-items-wrap .spr-gsm-band-1 { background-color: #eab308 !important; }
		.spr-items-wrap .spr-gsm-band-2 { background-color: #fb923c !important; }
		.spr-items-wrap .spr-gsm-band-3 { background-color: #fecaca !important; }
		.spr-items-wrap .spr-gsm-pending { background-color: #f3f4f6 !important; }
		.spr-items-wrap .spr-gsm-band-0 .grid-form-row, .spr-items-wrap .spr-gsm-band-0 .form-in-grid,
		.spr-items-wrap .spr-gsm-band-0 .form-section, .spr-items-wrap .spr-gsm-band-0 .frappe-control { background-color: #bbf7d0 !important; }
		.spr-items-wrap .spr-gsm-band-1 .grid-form-row, .spr-items-wrap .spr-gsm-band-1 .form-in-grid,
		.spr-items-wrap .spr-gsm-band-1 .form-section, .spr-items-wrap .spr-gsm-band-1 .frappe-control { background-color: #eab308 !important; }
		.spr-items-wrap .spr-gsm-band-2 .grid-form-row, .spr-items-wrap .spr-gsm-band-2 .form-in-grid,
		.spr-items-wrap .spr-gsm-band-2 .form-section, .spr-items-wrap .spr-gsm-band-2 .frappe-control { background-color: #fb923c !important; }
		.spr-items-wrap .spr-gsm-band-3 .grid-form-row, .spr-items-wrap .spr-gsm-band-3 .form-in-grid,
		.spr-items-wrap .spr-gsm-band-3 .form-section, .spr-items-wrap .spr-gsm-band-3 .frappe-control { background-color: #fecaca !important; }
		.spr-items-wrap .spr-gsm-pending .grid-form-row, .spr-items-wrap .spr-gsm-pending .form-in-grid,
		.spr-items-wrap .spr-gsm-pending .form-section, .spr-items-wrap .spr-gsm-pending .frappe-control { background-color: #f3f4f6 !important; }
		.spr-items-wrap .spr-gsm-band-0 + .grid-form-row { background-color: #bbf7d0 !important; }
		.spr-items-wrap .spr-gsm-band-1 + .grid-form-row { background-color: #eab308 !important; }
		.spr-items-wrap .spr-gsm-band-2 + .grid-form-row { background-color: #fb923c !important; }
		.spr-items-wrap .spr-gsm-band-3 + .grid-form-row { background-color: #fecaca !important; }
		.spr-items-wrap .spr-gsm-pending + .grid-form-row { background-color: #f3f4f6 !important; }
		.spr-items-wrap .grid-row.spr-gsm-band-0, .spr-items-wrap .dt-row.spr-gsm-band-0,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-0, .form-group[data-fieldname="items"] .dt-row.spr-gsm-band-0,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-0, .frappe-control[data-fieldname="items"] .dt-row.spr-gsm-band-0,
		.fieldname-items .grid-row.spr-gsm-band-0, .fieldname-items .dt-row.spr-gsm-band-0 { background-color: #bbf7d0 !important; }
		.spr-items-wrap .grid-row.spr-gsm-band-1, .spr-items-wrap .dt-row.spr-gsm-band-1,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-1, .form-group[data-fieldname="items"] .dt-row.spr-gsm-band-1,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-1, .frappe-control[data-fieldname="items"] .dt-row.spr-gsm-band-1,
		.fieldname-items .grid-row.spr-gsm-band-1, .fieldname-items .dt-row.spr-gsm-band-1 { background-color: #eab308 !important; }
		.spr-items-wrap .grid-row.spr-gsm-band-2, .spr-items-wrap .dt-row.spr-gsm-band-2,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-2, .form-group[data-fieldname="items"] .dt-row.spr-gsm-band-2,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-2, .frappe-control[data-fieldname="items"] .dt-row.spr-gsm-band-2,
		.fieldname-items .grid-row.spr-gsm-band-2, .fieldname-items .dt-row.spr-gsm-band-2 { background-color: #fb923c !important; }
		.spr-items-wrap .grid-row.spr-gsm-band-3, .spr-items-wrap .dt-row.spr-gsm-band-3,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-3, .form-group[data-fieldname="items"] .dt-row.spr-gsm-band-3,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-3, .frappe-control[data-fieldname="items"] .dt-row.spr-gsm-band-3,
		.fieldname-items .grid-row.spr-gsm-band-3, .fieldname-items .dt-row.spr-gsm-band-3 { background-color: #fecaca !important; }
		.spr-items-wrap .grid-row.spr-gsm-pending, .spr-items-wrap .dt-row.spr-gsm-pending,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-pending, .form-group[data-fieldname="items"] .dt-row.spr-gsm-pending,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-pending, .frappe-control[data-fieldname="items"] .dt-row.spr-gsm-pending,
		.fieldname-items .grid-row.spr-gsm-pending, .fieldname-items .dt-row.spr-gsm-pending { background-color: #f3f4f6 !important; }
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] .static-value,
		.spr-items-wrap .dt-row[class*="spr-gsm-band"] .static-value,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] .row-index,
		.spr-items-wrap .dt-row[class*="spr-gsm-band"] .row-index,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] .col,
		.spr-items-wrap .dt-row[class*="spr-gsm-band"] .col,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] input,
		.spr-items-wrap .dt-row[class*="spr-gsm-band"] input,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] select,
		.spr-items-wrap .dt-row[class*="spr-gsm-band"] select,
		.form-group[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] .static-value,
		.form-group[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] .row-index,
		.form-group[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] .col,
		.form-group[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] input,
		.form-group[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] select,
		.form-group[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] textarea,
		.form-group[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] a,
		.frappe-control[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] .static-value,
		.frappe-control[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] .row-index,
		.frappe-control[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] .col,
		.frappe-control[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] input,
		.frappe-control[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] select,
		.frappe-control[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] textarea,
		.frappe-control[data-fieldname="items"] .grid-row[class*="spr-gsm-band"] a,
		.fieldname-items .grid-row[class*="spr-gsm-band"] .static-value,
		.fieldname-items .grid-row[class*="spr-gsm-band"] .row-index,
		.fieldname-items .grid-row[class*="spr-gsm-band"] input,
		.fieldname-items .grid-row[class*="spr-gsm-band"] select {
			color: #111827 !important;
		}
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-pending .static-value,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-pending .row-index,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-pending .static-value,
		.fieldname-items .grid-row.spr-gsm-pending .static-value {
			color: #4b5563 !important;
		}
		.spr-items-wrap .dt-row.spr-gsm-band-0 .dt-cell, .spr-items-wrap .dt-row.spr-gsm-band-0 td { background-color: #bbf7d0 !important; }
		.spr-items-wrap .dt-row.spr-gsm-band-1 .dt-cell, .spr-items-wrap .dt-row.spr-gsm-band-1 td { background-color: #eab308 !important; }
		.spr-items-wrap .dt-row.spr-gsm-band-2 .dt-cell, .spr-items-wrap .dt-row.spr-gsm-band-2 td { background-color: #fb923c !important; }
		.spr-items-wrap .dt-row.spr-gsm-band-3 .dt-cell, .spr-items-wrap .dt-row.spr-gsm-band-3 td { background-color: #fecaca !important; }
		.spr-items-wrap .dt-row.spr-gsm-pending .dt-cell, .spr-items-wrap .dt-row.spr-gsm-pending td { background-color: #f3f4f6 !important; }
		/* Selected / active row (editing) — Frappe defaults to white; keep GSM band visible */
		.spr-items-wrap .dt-row.selected.spr-gsm-band-0, .spr-items-wrap .dt-row.active.spr-gsm-band-0,
		.form-group[data-fieldname="items"] .dt-row.selected.spr-gsm-band-0,
		.frappe-control[data-fieldname="items"] .dt-row.selected.spr-gsm-band-0,
		.fieldname-items .dt-row.selected.spr-gsm-band-0,
		.spr-items-wrap .grid-row.selected.spr-gsm-band-0, .spr-items-wrap .grid-row.grid-row-open.spr-gsm-band-0 { background-color: #bbf7d0 !important; }
		.spr-items-wrap .dt-row.selected.spr-gsm-band-1, .spr-items-wrap .dt-row.active.spr-gsm-band-1,
		.form-group[data-fieldname="items"] .dt-row.selected.spr-gsm-band-1,
		.frappe-control[data-fieldname="items"] .dt-row.selected.spr-gsm-band-1,
		.fieldname-items .dt-row.selected.spr-gsm-band-1,
		.spr-items-wrap .grid-row.selected.spr-gsm-band-1, .spr-items-wrap .grid-row.grid-row-open.spr-gsm-band-1 { background-color: #eab308 !important; }
		.spr-items-wrap .dt-row.selected.spr-gsm-band-2, .spr-items-wrap .dt-row.active.spr-gsm-band-2,
		.form-group[data-fieldname="items"] .dt-row.selected.spr-gsm-band-2,
		.frappe-control[data-fieldname="items"] .dt-row.selected.spr-gsm-band-2,
		.fieldname-items .dt-row.selected.spr-gsm-band-2,
		.spr-items-wrap .grid-row.selected.spr-gsm-band-2, .spr-items-wrap .grid-row.grid-row-open.spr-gsm-band-2 { background-color: #fb923c !important; }
		.spr-items-wrap .dt-row.selected.spr-gsm-band-3, .spr-items-wrap .dt-row.active.spr-gsm-band-3,
		.form-group[data-fieldname="items"] .dt-row.selected.spr-gsm-band-3,
		.frappe-control[data-fieldname="items"] .dt-row.selected.spr-gsm-band-3,
		.fieldname-items .dt-row.selected.spr-gsm-band-3,
		.spr-items-wrap .grid-row.selected.spr-gsm-band-3, .spr-items-wrap .grid-row.grid-row-open.spr-gsm-band-3 { background-color: #fecaca !important; }
		.spr-items-wrap .dt-row.selected.spr-gsm-pending, .spr-items-wrap .grid-row.selected.spr-gsm-pending { background-color: #f3f4f6 !important; }
		/* Submitted / read-only child table: rows are often plain tbody tr */
		.spr-items-wrap tbody tr.spr-gsm-band-0 td, .spr-items-wrap tbody tr.spr-gsm-band-0 th { background-color: #bbf7d0 !important; }
		.spr-items-wrap tbody tr.spr-gsm-band-1 td, .spr-items-wrap tbody tr.spr-gsm-band-1 th { background-color: #eab308 !important; }
		.spr-items-wrap tbody tr.spr-gsm-band-2 td, .spr-items-wrap tbody tr.spr-gsm-band-2 th { background-color: #fb923c !important; }
		.spr-items-wrap tbody tr.spr-gsm-band-3 td, .spr-items-wrap tbody tr.spr-gsm-band-3 th { background-color: #fecaca !important; }
		.spr-items-wrap tbody tr.spr-gsm-pending td, .spr-items-wrap tbody tr.spr-gsm-pending th { background-color: #f3f4f6 !important; }
		.form-readonly .spr-items-wrap .dt-row.spr-gsm-band-0, .form-readonly .spr-items-wrap .grid-row.spr-gsm-band-0,
		.form-readonly .spr-items-wrap tbody tr.spr-gsm-band-0 td { background-color: #bbf7d0 !important; }
		.form-readonly .spr-items-wrap .dt-row.spr-gsm-band-1, .form-readonly .spr-items-wrap .grid-row.spr-gsm-band-1,
		.form-readonly .spr-items-wrap tbody tr.spr-gsm-band-1 td { background-color: #eab308 !important; }
		.form-readonly .spr-items-wrap .dt-row.spr-gsm-band-2, .form-readonly .spr-items-wrap .grid-row.spr-gsm-band-2,
		.form-readonly .spr-items-wrap tbody tr.spr-gsm-band-2 td { background-color: #fb923c !important; }
		.form-readonly .spr-items-wrap .dt-row.spr-gsm-band-3, .form-readonly .spr-items-wrap .grid-row.spr-gsm-band-3,
		.form-readonly .spr-items-wrap tbody tr.spr-gsm-band-3 td { background-color: #fecaca !important; }
		.form-readonly .spr-items-wrap .dt-row.spr-gsm-pending, .form-readonly .spr-items-wrap .grid-row.spr-gsm-pending,
		.form-readonly .spr-items-wrap tbody tr.spr-gsm-pending td { background-color: #f3f4f6 !important; }
		.spr-items-wrap.spr-doc-submitted .dt-row.spr-gsm-band-0, .spr-items-wrap.spr-doc-submitted .grid-row.spr-gsm-band-0,
		.spr-items-wrap.spr-doc-submitted tbody tr.spr-gsm-band-0 td { background-color: #bbf7d0 !important; }
		.spr-items-wrap.spr-doc-submitted .dt-row.spr-gsm-band-1, .spr-items-wrap.spr-doc-submitted .grid-row.spr-gsm-band-1,
		.spr-items-wrap.spr-doc-submitted tbody tr.spr-gsm-band-1 td { background-color: #eab308 !important; }
		.spr-items-wrap.spr-doc-submitted .dt-row.spr-gsm-band-2, .spr-items-wrap.spr-doc-submitted .grid-row.spr-gsm-band-2,
		.spr-items-wrap.spr-doc-submitted tbody tr.spr-gsm-band-2 td { background-color: #fb923c !important; }
		.spr-items-wrap.spr-doc-submitted .dt-row.spr-gsm-band-3, .spr-items-wrap.spr-doc-submitted .grid-row.spr-gsm-band-3,
		.spr-items-wrap.spr-doc-submitted tbody tr.spr-gsm-band-3 td { background-color: #fecaca !important; }
		.spr-items-wrap.spr-doc-submitted .dt-row.spr-gsm-pending, .spr-items-wrap.spr-doc-submitted .grid-row.spr-gsm-pending,
		.spr-items-wrap.spr-doc-submitted tbody tr.spr-gsm-pending td { background-color: #f3f4f6 !important; }
		/* Header/body column alignment — hidden cols must not reserve width */
		.spr-items-wrap .form-grid,
		.spr-items-wrap .grid-heading-row,
		.spr-items-wrap .grid-body,
		.spr-items-wrap .datatable {
			width: 100%;
			box-sizing: border-box;
		}
		.spr-items-wrap .grid-heading-row {
			overflow: hidden;
		}
		.form-group[data-fieldname="items"] .grid-heading-row .grid-static-col.hidden,
		.form-group[data-fieldname="items"] .grid-row .col.hidden,
		.frappe-control[data-fieldname="items"] .grid-heading-row .grid-static-col.hidden,
		.frappe-control[data-fieldname="items"] .grid-row .col.hidden,
		.fieldname-items .grid-heading-row .grid-static-col.hidden,
		.fieldname-items .grid-row .col.hidden,
		.form-group[data-fieldname="shaft_jobs"] .grid-heading-row .grid-static-col.hidden,
		.form-group[data-fieldname="shaft_jobs"] .grid-row .col.hidden,
		.form-group[data-fieldname="bundle_calculation"] .grid-heading-row .grid-static-col.hidden,
		.form-group[data-fieldname="bundle_calculation"] .grid-row .col.hidden,
		.spr-items-wrap .dt-cell.hidden,
		.spr-items-wrap .dt-cell--hide {
			display: none !important;
			width: 0 !important;
			min-width: 0 !important;
			max-width: 0 !important;
			padding: 0 !important;
			margin: 0 !important;
			border: none !important;
			overflow: hidden !important;
		}
	`;
	$('head').append(`<style data-spr-items="${sprItemsCssVer}">${css}</style>`);
}

/** Apply row_locked / row_ready_for_print to grid DOM (Print Label only after Save Row). */
function spr_apply_items_row_lock_ui(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) {
		return;
	}
	const items = frm.doc.items || [];
	const $domRows = sprGetItemsDatatableBodyRows(frm);
	items.forEach(function (doc, idx) {
		let $wrap = sprFindItemsRowDomByDocname(frm, doc);
		if (!$wrap || !$wrap.length) {
			if ($domRows && $domRows.length > idx) {
				$wrap = $($domRows.get(idx));
			}
		}
		if (!$wrap || !$wrap.length) {
			$wrap = sprResolveItemsRowWrapper(frm, doc, grid, idx);
		}
		if (!$wrap || !$wrap.length) {
			return;
		}
		const locked = cint(doc.row_locked);
		const labelReady = cint(doc.row_ready_for_print) && locked;
		const $inner = $wrap.find('.grid-row').first();
		$wrap.addClass('spr-spr-row');
		$wrap.toggleClass('spr-spr-row-locked', !!locked);
		$wrap.toggleClass('spr-spr-row-label-ready', !!labelReady);
		if ($inner.length) {
			$inner.addClass('spr-spr-row');
			$inner.toggleClass('spr-spr-row-locked', !!locked);
			$inner.toggleClass('spr-spr-row-label-ready', !!labelReady);
		}
	});
}

const SPR_GSM_BG = ['#bbf7d0', '#eab308', '#fb923c', '#fecaca'];
/** Neutral row when GSM compare not yet possible (no blue). */
const SPR_GSM_PENDING_BG = '#f3f4f6';

function sprSetRowBgImportant($el, color) {
	if (!$el || !$el.length) {
		return;
	}
	const set = function (node) {
		if (node && node.style) {
			node.style.setProperty('background-color', color, 'important');
		}
	};
	$el.each(function () {
		set(this);
	});
	$el.find(
		'td, .col, .static-value, .editable-row, .row-index, .dt-cell, .form-in-grid, .form-section, .frappe-control, .control-input, .control-value'
	).each(function () {
		set(this);
	});
}

function sprApplyGsmRowVisual($row, bandOrPending) {
	if (!$row || !$row.length) {
		return;
	}
	if (bandOrPending === 'pending') {
		sprSetRowBgImportant($row, SPR_GSM_PENDING_BG);
		return;
	}
	const n = Number(bandOrPending);
	if (n >= 0 && n < SPR_GSM_BG.length) {
		sprSetRowBgImportant($row, SPR_GSM_BG[n]);
	}
}

function sprClearRowBg($row) {
	if (!$row || !$row.length) {
		return;
	}
	const clear = function (node) {
		if (node && node.style) {
			node.style.removeProperty('background-color');
		}
	};
	$row.each(function () {
		clear(this);
	});
	$row.find(
		'td, .col, .static-value, .editable-row, .row-index, .dt-cell, .form-in-grid, .form-section, .frappe-control, .control-input, .control-value'
	).each(function () {
		clear(this);
	});
}

function sprEnsureItemsGridObserver(frm) {
	/* MutationObserver removed — it re-fired on every GSM colour paint and froze the form. */
}

function schedule_spr_item_row_styles(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	if (frm.fields_dict.items.$wrapper && frm.fields_dict.items.$wrapper.length) {
		frm.fields_dict.items.$wrapper.addClass('spr-items-wrap');
		frm.fields_dict.items.$wrapper.toggleClass('spr-doc-submitted', frm.doc && cint(frm.doc.docstatus) === 1);
	}
	ensure_spr_item_stylesheet();
	spr_schedule_grid_ui_debounced(frm, { delay: 120 });
}

/** After save/submit when grid DOM is rebuilt — short debounced re-apply only. */
function spr_schedule_item_row_styles_after_doc_write(frm) {
	if (!frm || !frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	if (frm.fields_dict.items.$wrapper && frm.fields_dict.items.$wrapper.length) {
		frm.fields_dict.items.$wrapper.addClass('spr-items-wrap');
		frm.fields_dict.items.$wrapper.toggleClass('spr-doc-submitted', frm.doc && cint(frm.doc.docstatus) === 1);
	}
	ensure_spr_item_stylesheet();
	[0, 350, 1200].forEach(function (ms) {
		setTimeout(function () {
			if (!frm || !frm.fields_dict || !frm.fields_dict.items) {
				return;
			}
			spr_schedule_grid_ui_debounced(frm, { delay: 0 });
		}, ms);
	});
}

function sprResolveItemsRowElement(frm, doc, grid, idx) {
	let $row = null;
	const byName = doc && doc.name && grid.grid_rows_by_docname && grid.grid_rows_by_docname[doc.name];
	if (byName) {
		if (byName.row && byName.row.length) {
			$row = byName.row;
		} else if (byName.wrapper && byName.wrapper.length) {
			$row = byName.wrapper;
		}
	}
	const $wrap = frm.fields_dict.items.$wrapper;
	if ((!$row || !$row.length) && $wrap && $wrap.length && doc && doc.name) {
		$row = $wrap.find('.grid-row[data-docname="' + doc.name + '"]');
		if (!$row.length) {
			$row = $wrap.find('.grid-row[data-name="' + doc.name + '"]');
		}
		if (!$row.length) {
			$row = $wrap.find('[data-name="' + doc.name + '"]').closest('.grid-row, .grid-form-row, tr');
		}
		if (!$row.length) {
			$row = $wrap
				.find('.form-in-grid [data-name="' + doc.name + '"]')
				.closest('.grid-row, tr, .dt-row');
		}
	}
	const $fb =
		$wrap && $wrap.length
			? $wrap.find(
					'.grid-body .grid-row, .form-grid .grid-row, .form-grid .rows .grid-row, .datatable .dt-row, tbody tr[data-idx]'
				)
			: $();
	if ((!$row || !$row.length) && $fb.length > idx) {
		$row = $($fb.get(idx));
	}
	// Frappe DataTable child grid: rows are often .dt-row only (no grid-row / docname on row)
	if ((!$row || !$row.length) && $wrap && $wrap.length) {
		const $dtOnly = $wrap.find('.datatable .dt-row:not(.dt-row-filter)');
		if ($dtOnly.length > idx) {
			$row = $($dtOnly.get(idx));
		}
	}
	return $row;
}

/**
 * All visible DataTable body rows in order. Prefer this over grid.grid_rows[idx] — Frappe often only
 * wires row 0 there while rows 1+ still exist in the DOM (causes only-first-row coloring).
 */
function sprGetItemsDatatableBodyRows(frm) {
	const $wrap = frm.fields_dict.items && frm.fields_dict.items.$wrapper;
	if (!$wrap || !$wrap.length) {
		return null;
	}
	const selectors = [
		'.datatable-body .dt-row',
		'.dt-scrollable .datatable-body .dt-row',
		'.dt-scrollable .dt-row',
		'.datatable .dt-row:not(.dt-row-filter)',
		'.dt-row:not(.dt-row-filter)',
	];
	let $rows = $();
	for (let i = 0; i < selectors.length; i++) {
		const $f = $wrap.find(selectors[i]);
		if ($f.length) {
			$rows = $f;
			break;
		}
	}
	if (!$rows.length) {
		$rows = $wrap.find('tbody tr[data-idx], .grid-body .grid-row').not('.grid-form-row');
	}
	if (!$rows.length) {
		return null;
	}
	$rows = $rows.filter(function () {
		const $t = $(this);
		if ($t.hasClass('dt-row-header') || $t.closest('.dt-row-header').length) {
			return false;
		}
		if ($t.closest('thead').length) {
			return false;
		}
		return true;
	});
	return $rows.length ? $rows : null;
}

/** DataTable / grid: row index matches `items` child order on cloud (grid_rows_by_docname often incomplete). */
function sprGetPrimaryItemsRowTarget(frm, idx) {
	const $wrap = frm.fields_dict.items && frm.fields_dict.items.$wrapper;
	if (!$wrap || !$wrap.length) {
		return null;
	}
	let $dt = $wrap.find('.datatable .dt-row:not(.dt-row-filter)');
	if (!$dt.length) {
		$dt = $wrap.find('.dt-scrollable .dt-row:not(.dt-row-filter)');
	}
	if (!$dt.length) {
		$dt = $wrap.find('.dt-row:not(.dt-row-filter)');
	}
	if ($dt.length > idx) {
		return $($dt.get(idx));
	}
	const $gr = $wrap.find('.grid-body .grid-row').not('.grid-form-row');
	if ($gr.length > idx) {
		return $($gr.get(idx));
	}
	return null;
}

/**
 * Prefer Frappe GridRow at index (matches child table order; works when DataTable only mounts row 0 in DOM).
 * Then docname lookup, then DOM fallbacks.
 */
function sprResolveItemsRowWrapper(frm, doc, grid, idx) {
	let gr = null;
	if (grid && grid.grid_rows && grid.grid_rows[idx] !== undefined) {
		gr = grid.grid_rows[idx];
	}
	if (gr) {
		if (gr.wrapper && gr.wrapper.length) {
			return gr.wrapper;
		}
		if (gr.row && gr.row.length) {
			return gr.row;
		}
	}
	gr = doc && doc.name && grid.grid_rows_by_docname && grid.grid_rows_by_docname[doc.name];
	if (gr) {
		if (gr.wrapper && gr.wrapper.length) {
			return gr.wrapper;
		}
		if (gr.row && gr.row.length) {
			return gr.row;
		}
	}
	const $byIdx = sprGetPrimaryItemsRowTarget(frm, idx);
	if ($byIdx && $byIdx.length) {
		return $byIdx;
	}
	return sprResolveItemsRowElement(frm, doc, grid, idx);
}

/** Resolve the visible row node for a child row (Frappe 16 DataTable uses .dt-row; index order can diverge). */
function sprFindItemsRowDomByDocname(frm, doc) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (grid && grid.grid_rows && grid.grid_rows.length) {
		for (let i = 0; i < grid.grid_rows.length; i++) {
			const gr = grid.grid_rows[i];
			if (!gr || !gr.doc || gr.doc.name !== doc.name) {
				continue;
			}
			if (gr.wrapper && gr.wrapper.length) {
				return gr.wrapper;
			}
			if (gr.row && gr.row.length) {
				return gr.row;
			}
		}
	}
	const grByName = doc && doc.name && grid && grid.grid_rows_by_docname && grid.grid_rows_by_docname[doc.name];
	if (grByName) {
		if (grByName.wrapper && grByName.wrapper.length) {
			return grByName.wrapper;
		}
		if (grByName.row && grByName.row.length) {
			return grByName.row;
		}
	}
	const $wrap = frm.fields_dict.items && frm.fields_dict.items.$wrapper;
	if (!$wrap || !$wrap.length || !doc || !doc.name) {
		return null;
	}
	const name = String(doc.name);
	const $byDom = $wrap.find('.datatable .dt-row, .dt-row, .grid-row, tbody tr[data-idx]').filter(function () {
		const $t = $(this);
		return $t.attr('data-docname') === name || $t.attr('data-name') === name;
	});
	return $byDom.length ? $byDom.first() : null;
}

function sprCollectItemRowTargets(frm, doc, idx, $primaryRow, $wrap) {
	if (!$wrap || !$wrap.length) {
		$wrap = frm.fields_dict.items && frm.fields_dict.items.$wrapper;
	}
	let $targets = $();
	if ($primaryRow && $primaryRow.length) {
		$targets = $targets.add($primaryRow);
		const $ed = $primaryRow.closest('.editable-row');
		if ($ed && $ed.length) {
			$targets = $targets.add($ed);
		}
	}
	if (!doc || !doc.name || !$wrap || !$wrap.length) {
		return $targets;
	}
	const $byDoc = $wrap.find('.grid-row, .dt-row').filter(function () {
		const $t = $(this);
		return $t.attr('data-docname') === doc.name || $t.attr('data-name') === doc.name;
	});
	$targets = $targets.add($byDoc);
	const $formRows = $wrap.find('.grid-form-row').filter(function () {
		return $(this).find('[data-name="' + doc.name + '"]').length > 0;
	});
	$targets = $targets.add($formRows);
	const $fig = $wrap.find('.form-in-grid').filter(function () {
		return $(this).find('[data-name="' + doc.name + '"]').length > 0;
	});
	$fig.each(function () {
		const $p = $(this).closest('.grid-form-row, .grid-row, tr, .dt-row');
		if ($p.length) {
			$targets = $targets.add($p);
		}
	});
	return $targets;
}

function apply_spr_item_row_styles(frm) {
	if (frm._spr_applying_row_styles) {
		return;
	}
	frm._spr_applying_row_styles = true;
	const grid = frm.fields_dict.items.grid;
	if (!grid) {
		frm._spr_applying_row_styles = false;
		return;
	}
	const bandClasses = ['spr-gsm-band-0', 'spr-gsm-band-1', 'spr-gsm-band-2', 'spr-gsm-band-3'];
	const baseClasses =
		'spr-gsm-band-0 spr-gsm-band-1 spr-gsm-band-2 spr-gsm-band-3 spr-gsm-pending';
	const items = frm.doc.items || [];
	const $domRows = sprGetItemsDatatableBodyRows(frm);
	const $wrap = frm.fields_dict.items.$wrapper;

	items.forEach(function (doc, idx) {
		// Try multiple resolution methods to find row element for DataTable / Frappe grids
		let $row = null;
		
		// Method 1: Try by docname first (works when grid_rows_by_docname is populated)
		if (!$row || !$row.length) {
			$row = sprFindItemsRowDomByDocname(frm, doc);
		}
		
		
		// Method 2: Use DOM rows array by index (DataTable body rows in order)
		if ((!$row || !$row.length) && $domRows && $domRows.length > idx) {
			$row = $($domRows.get(idx));
		}
		
		// Method 3: Try wrapper resolution by index
		if (!$row || !$row.length) {
			$row = sprResolveItemsRowWrapper(frm, doc, grid, idx);
		}
		
		// Method 4: Direct selector search if other methods fail
		if ((!$row || !$row.length) && $wrap && $wrap.length && doc && doc.name) {
			$row = $wrap
				.find('.dt-row, .grid-row, tbody tr')
				.filter(function (i) {
					return i === idx || $(this).attr('data-docname') === doc.name || $(this).attr('data-name') === doc.name;
				})
				.first();
		}
		
		if (!$row || !$row.length) {
			sprLog('Could not resolve row for item at index', idx, doc);
			return;
		}
		
		const $targets = sprCollectItemRowTargets(frm, doc, idx, $row, $wrap);
		// Roll Production Results: Sticker GSM vs produced (field or computed from net/gross × width × length)
		const sticker = sprStickerGsmFromDoc(doc);
		const produced = sprEffectiveProducedGsm(doc);
		$targets.removeClass(baseClasses);
		$targets.each(function () {
			sprClearRowBg($(this));
		});
		if (sticker > 0 && produced > 0) {
			const diff = Math.abs(produced - sticker);
			let band = 3;
			if (diff < 1) {
				band = 0;
			} else if (diff < 2) {
				band = 1;
			} else if (diff < 3) {
				band = 2;
			}
			$targets.addClass(bandClasses[band]);
			$targets.each(function () {
				sprApplyGsmRowVisual($(this), band);
			});
		} else {
			$targets.addClass('spr-gsm-pending');
			$targets.each(function () {
				sprApplyGsmRowVisual($(this), 'pending');
			});
		}
	});
	spr_apply_items_row_lock_ui(frm);
	frm._spr_applying_row_styles = false;
}


// ===== TOTAL PRODUCED WEIGHT CALCULATION =====

function spr_compute_total_produced_weight(frm) {
	if (!frm || !frm.doc) {
		return 0;
	}
	if (sprIsBag(frm)) {
		const bundles = frm.doc.bundle_calculation || [];
		let t = 0;
		for (let i = 0; i < bundles.length; i++) {
			t += flt(bundles[i].total_produced_bag_pcs);
		}
		return flt(t);
	}
	if (sprIsSheetCutting(frm)) {
		const bundles = frm.doc.bundle_calculation || [];
		let t = 0;
		for (let i = 0; i < bundles.length; i++) {
			t += flt(bundles[i].total_achieved_weight);
		}
		return spr_round_net_weight_kg(t);
	}
	const items = frm.doc.items || [];
	let total = 0;
	for (let i = 0; i < items.length; i++) {
		total += spr_round_net_weight_kg(items[i].net_weight);
	}
	return spr_round_net_weight_kg(total);
}

function spr_sync_bag_pcs_headers(frm, opts) {
	if (!frm || !frm.doc || !sprIsBag(frm)) {
		return;
	}
	const settings = opts || {};
	const bundles = frm.doc.bundle_calculation || [];
	let achieved = 0;
	bundles.forEach(function (br) {
		achieved += flt(br.total_produced_bag_pcs);
	});
	achieved = flt(achieved);
	if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_achieved_pcs')) {
		const curAch = flt(frm.doc.custom_total_achieved_pcs);
		if (Math.abs(curAch - achieved) > 0.5) {
			if (settings.silent) {
				frm.doc.custom_total_achieved_pcs = achieved;
				frm.refresh_field('custom_total_achieved_pcs');
			} else {
				frm.set_value('custom_total_achieved_pcs', achieved);
			}
		}
	}
}

function spr_sync_total_produced_weight(frm, opts) {
	if (!frm || !frm.doc) {
		return;
	}
	if (cint(frm.doc.docstatus) !== 0) {
		return;
	}
	const settings = opts || {};
	const calculated = spr_compute_total_produced_weight(frm);
	const current = sprIsBag(frm) ? flt(frm.doc.total_produced_weight) : spr_round_net_weight_kg(frm.doc.total_produced_weight);
	const tolerance = sprIsBag(frm) ? 0.5 : 0.001;

	if (Math.abs(current - calculated) > tolerance) {
		if (settings.silent) {
			frm.doc.total_produced_weight = calculated;
			if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_produced_weight')) {
				frm.doc.custom_total_produced_weight = calculated;
			}
			frm.refresh_field('total_produced_weight');
			if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_produced_weight')) {
				frm.refresh_field('custom_total_produced_weight');
			}
		} else {
			frm.set_value('total_produced_weight', calculated);
			if (frappe.meta.get_docfield('Shaft Production Run', 'custom_total_produced_weight')) {
				frm.set_value('custom_total_produced_weight', calculated);
			}
		}
	}
	if (sprIsBag(frm)) {
		spr_sync_bag_pcs_headers(frm, settings);
	}
}
