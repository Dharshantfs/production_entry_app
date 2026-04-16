const SPR_DEBUG_LOGS = false;
function sprLog() {
	if (!SPR_DEBUG_LOGS || !window.console || !console.log) return;
	console.log.apply(console, arguments);
}

/** Net weight (kg) to 2 decimals — matches roll line precision, manual sums, and Total Produced Weight. */
function spr_round_net_weight_kg(v) {
	return Math.round(flt(v) * 100) / 100;
}

function sprScheduleTotalProducedSync(frm, opts) {
	if (!frm) return;
	if (frm.__spr_total_sync_timer) {
		clearTimeout(frm.__spr_total_sync_timer);
	}
	frm.__spr_total_sync_timer = setTimeout(function () {
		spr_sync_total_produced_weight(frm, opts || {});
		frm.__spr_total_sync_timer = null;
	}, 120);
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
			}).catch(function () {
				frm.__spr_auto_save_in_progress = false;
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
		setTimeout(function () {
			spr_patch_items_grid_refresh(frm);
		}, 0);
		setTimeout(function () {
			spr_patch_items_grid_refresh(frm);
		}, 400);
		setTimeout(function () {
			spr_register_spr_page_buttons(frm);
		}, 0);
		setTimeout(function () {
			spr_register_spr_page_buttons(frm);
		}, 500);
		[0, 400].forEach(function (ms) {
			setTimeout(function () {
				spr_inject_gsm_legend(frm);
				schedule_spr_item_row_styles(frm);
			}, ms);
		});
		if (frm.doc && cint(frm.doc.docstatus) === 1) {
			spr_schedule_item_row_styles_after_doc_write(frm);
		}
	},

	production_plan: function (frm) {
		if (!frm.doc.production_plan) {
			frm.clear_table('shaft_jobs');
			frm.clear_table('items');
			frm.refresh_field('shaft_jobs');
			frm.refresh_field('items');
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
				if (d.customer) {
					sprLog('[SPR] Setting customer:', d.customer);
					frm.set_value('customer', d.customer);
				}
				if (d.custom_unit) {
					sprLog('[SPR] Setting custom_unit:', d.custom_unit);
					frm.set_value('custom_unit', d.custom_unit);
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
				// Note: custom_party_code is only in the child table, not the header, so don't set it here
			},
		});

		frappe.call({
			method:
				'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_job_rows_for_production_plan',
			args: { production_plan: frm.doc.production_plan },
			freeze: true,
			freeze_message: __('Loading shaft jobs from Production Plan...'),
			callback: function (r) {
				frm.clear_table('shaft_jobs');
				(r.message || []).forEach(function (row) {
					let c = frm.add_child('shaft_jobs');
					Object.keys(row).forEach(function (k) {
						if (row[k] !== undefined && row[k] !== null) {
							c[k] = row[k];
						}
					});
				});
				frm.refresh_field('shaft_jobs');
				frm.clear_table('items');
				frm.refresh_field('items');
				fetch_and_show_pp_wo_summary(frm);
			},
			error: function () {
				frm.clear_table('items');
				frm.refresh_field('items');
				fetch_and_show_pp_wo_summary(frm);
			},
		});
	},

	refresh: function (frm) {
		// Enforce read-only UI controls dynamically since we removed them from JSON to allow backend save
		frm.set_df_property('total_produced_weight', 'read_only', 1);
		try {
			frm.set_df_property('net_weight', 'precision', 2, null, 'items');
		} catch (e) {
			/* ignore desk variants */
		}

		sprLog('[SPR REFRESH] === REFRESH HOOK START ===');
		
		spr_sync_total_planned_qty_from_jobs(frm, { silent: true });
		sprLog('[SPR REFRESH] After total_planned_qty sync');
		
		sprScheduleTotalProducedSync(frm, { silent: true });
		sprLog('[SPR REFRESH] After total_produced_weight sync (scheduled)');
		
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
		schedule_spr_item_row_styles(frm);
		if (frm.doc && cint(frm.doc.docstatus) === 1) {
			spr_schedule_item_row_styles_after_doc_write(frm);
		}
		
		sprLog('[SPR REFRESH] === REFRESH HOOK END ===');
	},

	before_submit: function (frm) {
		if (!frm || !frm.doc) {
			return;
		}
		if (cint(frm.doc.docstatus) !== 0) {
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
		spr_register_spr_page_buttons_after_save(frm);
		schedule_spr_item_row_styles(frm);
		spr_schedule_item_row_styles_after_doc_write(frm);
	},

	on_submit: function (frm) {
		schedule_spr_item_row_styles(frm);
		spr_schedule_item_row_styles_after_doc_write(frm);
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
			update_shaft_job_achieved_from_items(frm);
			sprLog('[SPR DEBUG] items_add: schedule total_produced_weight sync with', (frm.doc.items || []).length, 'items');
			sprScheduleTotalProducedSync(frm);
			schedule_spr_item_row_styles(frm);
		},
		items_remove: function (frm) {
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
				? 'Allowed deviation: ±{0}%. Enter a reason and confirm approval to submit, or adjust roll weights.'
				: 'Allowed deviation: ±{0}%. Enter a reason and confirm approval to save, or adjust roll weights.',
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

/**
 * Register toolbar + Tools menu. Frappe rebuilds the header on Save/refresh — remove then re-add
 * every time so buttons do not disappear (do not use a one-shot _spr_page_buttons_ok guard).
 * Also registers custom buttons — they survive some toolbar rebuilds better than inner_group alone.
 */
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
	}
	if (canRemoveCustom && typeof frm.add_custom_button === 'function') {
		try {
			frm.add_custom_button(__('Manual job'), function () {
				spr_open_manual_job_dialog(frm);
			});
		} catch (e) {}
		try {
			frm.add_custom_button(__('Bundle packaging'), function () {
				spr_open_bundle_packaging_dialog(frm);
			});
		} catch (e) {}
	}
	if (!frm.page || typeof frm.page.add_inner_button !== 'function') {
		return;
	}
	const tg = __('Tools');
	const rm = frm.page.remove_inner_button;
	if (typeof rm === 'function') {
		[__('Manual job'), __('Bundle packaging')].forEach(function (lbl) {
			try {
				rm.call(frm.page, lbl);
			} catch (e) {}
		});
		[__('SPR — Manual job'), __('SPR — Bundle packaging')].forEach(function (lbl) {
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
		frm.page.add_inner_button(__('Manual job'), function () {
			spr_open_manual_job_dialog(frm);
		});
	});
	addInner(function () {
		frm.page.add_inner_button(__('Bundle packaging'), function () {
			spr_open_bundle_packaging_dialog(frm);
		});
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

/** Actions → Manual job: multi-select PP lines; WO qty defaults to net/shaft × shafts from Available Jobs. */
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
						label: __('Combination widths (in)'),
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
							__('WO qty default = net/roll Kg × rolls × shafts') +
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
					__('Width (in)') +
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
						' · ' +
						String(line.item_name || '').substring(0, 28) +
						' · ' +
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
							__('No unused PP line found for GSM {0} width {1} in.', [comboGsm, targetWidth]),
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

/** Actions → Bundle packaging: Job + Width from Available Jobs / roll widths; gross applied to all matching rolls. */
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
						label: __('Width / segment (in) — pick one row from the table above'),
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
				],
				primary_action_label: __('Apply'),
				primary_action: function (values) {
					const jp = jobByLabel[values.job_pick];
					const w = flt(values.width_inch);
					const n = cint(values.no_of_packaging);
					const whole = flt(values.whole_gross_kg);
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
						},
						freeze: true,
						freeze_message: __('Applying bundle packaging...'),
						callback: function (r2) {
							const m = r2.message || {};
							frappe.show_alert({
								message: __(
									'Updated {0} roll(s). Single gross {1} Kg, sticker width {2} in, bundle net {3} Kg.',
									[
										String(m.updated_rolls != null ? m.updated_rolls : ''),
										String(m.single_roll_gross_kg != null ? m.single_roll_gross_kg : ''),
										String(m.total_width_inch != null ? m.total_width_inch : ''),
										String(m.sticker_bundle_weight_kg != null ? m.sticker_bundle_weight_kg : ''),
									]
								),
								indicator: 'green',
							});
							
							// Reload document and trigger calculations for all items
							const reloadPromise = frm.reload_doc();
							function triggerCalculationsAfterReload() {
								// Trigger net_weight and produced_gsm calculation for all affected items
								if (frm.doc.items) {
									let has_changes = false;
									frm.doc.items.forEach(function (item) {
										if (item.gross_weight > 0) {
											let width = flt(item.width_inch);
											let current_net = item.net_weight || 0;
											
											let net_val = 0;
											if (width > 0) {
												let core_weight = width * (1.3 / 63);
												net_val = spr_round_net_weight_kg(flt(item.gross_weight) - core_weight);
											}
											
											if (Math.abs(current_net - net_val) > 0.01 && net_val > 0) {
												frappe.model.set_value(item.doctype, item.name, 'net_weight', net_val);
												has_changes = true;
											}
										}
										try {
											if (typeof spr_update_produced_gsm === 'function') {
												spr_update_produced_gsm(frm, 'Shaft Production Run Item', item.name);
											}
										} catch(e) {}
									});
									if (has_changes) {
										try { update_shaft_job_achieved_from_items(frm); } catch(e) {}
										setTimeout(function() { frm.save(); }, 500);
									}
								}
								frm.refresh_field('items');
								// Sync total_produced_weight from items net_weight sum (real-time calculation)
								spr_sync_total_produced_weight(frm);
								try { schedule_spr_item_row_styles(frm); } catch(e) {}
								[0, 100, 300, 600].forEach(function (ms) {
									setTimeout(function () {
										try { apply_spr_item_row_styles(frm); } catch(e) {}
									}, ms);
								});
							}
							
							// Wait for reload to complete if it's a promise, otherwise trigger immediately
							if (reloadPromise && typeof reloadPromise.then === 'function') {
								reloadPromise.then(triggerCalculationsAfterReload);
							} else {
								setTimeout(triggerCalculationsAfterReload, 300);
							}
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
					let html =
						'<table class="table table-bordered table-condensed" style="font-size:11px;margin:4px 0;"><thead><tr><th>' +
						__('Width') +
						'</th><th>' +
						__('Net/shaft (Kg)') +
						'</th><th>' +
						__('WO item') +
						'</th></tr></thead><tbody>';
					segs.forEach(function (s) {
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
					wf.df.options = segs
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
					wf.df.options = arr
						.map(function (x) {
							return String(x);
						})
						.join('\n');
				}
				wf.refresh();
				const firstW =
					segs.length > 0 ? flt(segs[0].width_inch) : arr.length > 0 ? flt(arr[0]) : 0;
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
					__('Single gross: {0} Kg · Sticker width (selected width × pkg): {1} in', [
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
		frappe.call({
			method:
				'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.build_spr_roll_result_lines_for_job',
			args: {
				shaft_production_run: frm.doc.name,
				job_id: String(job_id),
			},
			freeze: true,
			freeze_message: __('Creating roll lines for this job...'),
			callback: function (r) {
				const lines = r.message || [];
				remove_spr_items_for_job(frm, job_id);
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
					(frm.doc.items || []).forEach(function (row) {
						spr_update_produced_gsm_with_retry(frm, 'Shaft Production Run Item', row.name);
					});
					update_shaft_job_achieved_from_items(frm);
					sprScheduleTotalProducedSync(frm);
					schedule_spr_item_row_styles(frm);
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
									if (nums[i].batch_no) {
										frappe.model.set_value(row.doctype, row.name, 'batch_no', nums[i].batch_no);
									}
									if (nums[i].roll_no !== undefined && nums[i].roll_no !== null) {
										frappe.model.set_value(row.doctype, row.name, 'roll_no', nums[i].roll_no);
									}
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
	},
});

frappe.ui.form.on('Shaft Production Run Item', {
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
	},
	produced_length_mtrs: function (frm, cdt, cdn) {
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
	},
	meter_roll_mtrs: function (frm, cdt, cdn) {
		spr_update_produced_gsm_with_retry(frm, cdt, cdn);
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
			frm.refresh_field('items');
			spr_schedule_item_row_styles_after_doc_write(frm);
			[0, 50, 200, 500].forEach(function (ms) {
				setTimeout(function () {
					spr_apply_items_row_lock_ui(frm);
					apply_spr_item_row_styles(frm);
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
			frm.refresh_field('items');
			spr_schedule_item_row_styles_after_doc_write(frm);
			[0, 50, 200].forEach(function (ms) {
				setTimeout(function () {
					spr_apply_items_row_lock_ui(frm);
					apply_spr_item_row_styles(frm);
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

function spr_update_produced_gsm(frm, cdt, cdn) {
	if (!frappe.meta.get_docfield('Shaft Production Run Item', 'produced_gsm')) {
		return;
	}
	const row = locals[cdt][cdn];
	
	// Get weight: prefer net_weight, fallback to gross_weight
	let nw = flt(row.net_weight);
	if (nw <= 0) {
		nw = flt(row.gross_weight);
	}
	
	// Get width (required)
	const wi = flt(row.width_inch);
	
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

function update_shaft_job_achieved_from_items(frm) {
	if (frm && frm.doc && cint(frm.doc.docstatus) !== 0) {
		return;
	}
	if (!frappe.meta.get_docfield('Shaft Production Run Job', 'custom_total_achieved_weight')) {
		return;
	}
	const sums = {};
	(frm.doc.items || []).forEach(function (it) {
		const k = sprNormalizeJobKey(it.job);
		if (!k) {
			return;
		}
		sums[k] = (sums[k] || 0) + spr_round_net_weight_kg(it.net_weight);
	});
	(frm.doc.shaft_jobs || []).forEach(function (sj) {
		const jid = sprShaftJobRowKey(sj);
		const v = jid && sums[jid] !== undefined ? sums[jid] : 0;
		const next = spr_round_net_weight_kg(v);
		const cur = flt(sj.custom_total_achieved_weight);
		// Avoid set_value when unchanged — set_value marks the form dirty and causes "Not Saved" after a successful save.
		if (Math.abs(cur - next) > 0.005) {
			frappe.model.set_value(sj.doctype, sj.name, 'custom_total_achieved_weight', next);
		}
	});
}

function spr_patch_items_grid_refresh(frm) {
	if (frm._spr_items_grid_patched) {
		return;
	}
	const fd = frm.fields_dict && frm.fields_dict.items;
	if (!fd || !fd.grid) {
		return;
	}
	const grid = fd.grid;
	let hooked = false;
	function schedule() {
		[0, 80, 200, 450].forEach(function (ms) {
			setTimeout(function () {
				apply_spr_item_row_styles(frm);
			}, ms);
		});
	}
	function wrap(method) {
		const orig = grid[method];
		if (typeof orig !== 'function') {
			return;
		}
		const bound = orig.bind(grid);
		grid[method] = function () {
			const ret = bound.apply(grid, arguments);
			schedule();
			return ret;
		};
		hooked = true;
	}
	wrap('refresh');
	wrap('render');
	if (grid.wrapper && grid.wrapper.length && !frm._spr_items_grid_click_patched) {
		frm._spr_items_grid_click_patched = true;
		grid.wrapper.on('click', '.grid-row, .dt-row, .grid-form-row', function () {
			setTimeout(function () {
				apply_spr_item_row_styles(frm);
			}, 50);
		});
		grid.wrapper.on('focusin', function () {
			schedule_spr_item_row_styles(frm);
		});
		grid.wrapper.on('change input blur', 'input, textarea, select', function () {
			if (frm._spr_grid_input_debounce) {
				clearTimeout(frm._spr_grid_input_debounce);
			}
			frm._spr_grid_input_debounce = setTimeout(function () {
				frm._spr_grid_input_debounce = null;
				schedule_spr_item_row_styles(frm);
			}, 120);
		});
	}
	if (hooked) {
		frm._spr_items_grid_patched = true;
	}
}

/** Legend for |Sticker GSM − Produced GSM| bands (above Roll Production Results grid). */
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
		'<span style="display:inline-block;background:#eab308;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">1 – 2</span> ' +
		'<span style="display:inline-block;background:#fb923c;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">2 – 3</span> ' +
		'<span style="display:inline-block;background:#fecaca;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">≥ 3</span> ' +
		'<span style="display:inline-block;background:#f3f4f6;padding:2px 8px;margin:2px 4px 2px 0;border-radius:2px;">' +
		__('Awaiting produced GSM / incomplete') +
		'</span>' +
		'</div>';
	fd.$wrapper.before(html);
}

/** Sticker / planned GSM: field or parsed from item_code (same rule as server parse_item_code). */
function sprStickerGsmFromDoc(doc) {
	let g = flt(doc.gsm);
	if (g > 0) {
		return g;
	}
	const ic = (doc.item_code || '') + '';
	if (ic.length >= 16) {
		const n = parseInt(ic.substring(9, 12), 10);
		if (!isNaN(n) && n > 0) {
			return n;
		}
	}
	return 0;
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
	
	// Get width (required)
	const wi = flt(doc.width_inch);
	
	const mr = sprResolveLengthMeters(doc);
	
	// Formula: (net_weight * 1000) / (width_inch * length_mtrs * 0.0254)
	if (nw > 0 && wi > 0 && mr > 0) {
		return Math.round((nw * 1000) / (wi * mr * 0.0254) * 100) / 100;
	}
	return 0;
}

function ensure_spr_item_stylesheet() {
	if (!window.__sprspr_lock_style) {
		window.__sprspr_lock_style = true;
		const lockCss = `
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]),
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]),
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) {
			pointer-events: none;
			opacity: 0.94;
		}
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) input,
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) textarea,
		.form-group[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) select,
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) input,
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) textarea,
		.frappe-control[data-fieldname="items"] .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) select,
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) input,
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) textarea,
		.fieldname-items .grid-row.spr-spr-row-locked .col:not([data-fieldname="print_sticker"]):not([data-fieldname="edit_row"]):not([data-fieldname="save_row"]) select {
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
		.fieldname-items .grid-row:not(.spr-spr-row-label-ready) .col[data-fieldname="print_sticker"] a {
			opacity: 0 !important;
			visibility: hidden !important;
			pointer-events: none !important;
		}
	`;
		$('head').append(`<style data-spr-row-lock="1">${lockCss}</style>`);
	}
	const sprItemsCssVer = '16';
	if (window.__sprspr_items_css_ver === sprItemsCssVer) {
		return;
	}
	window.__sprspr_items_css_ver = sprItemsCssVer;
	window.__sprspr_style = true;
	$('head style[data-spr-items]').remove();
	/* |Sticker GSM (gsm) − Produced GSM (produced_gsm)|: <1 green, 1–2 yellow, 2–3 orange, 3+ red */
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
	const $w = frm.fields_dict.items && frm.fields_dict.items.$wrapper;
	if (!$w || !$w.length) {
		return;
	}
	const node = $w[0];
	if (frm._spr_items_mo) {
		const ok =
			frm._spr_items_mo_target &&
			typeof document !== 'undefined' &&
			document.contains(frm._spr_items_mo_target) &&
			frm._spr_items_mo_target === node;
		if (ok) {
			return;
		}
		try {
			frm._spr_items_mo.disconnect();
		} catch (e) {}
		frm._spr_items_mo = null;
		frm._spr_items_mo_target = null;
	}
	let timer = null;
	frm._spr_items_mo = new MutationObserver(function () {
		if (timer) {
			clearTimeout(timer);
		}
		timer = setTimeout(function () {
			apply_spr_item_row_styles(frm);
		}, 40);
	});
	frm._spr_items_mo_target = node;
	frm._spr_items_mo.observe(node, { childList: true, subtree: true });
}

function schedule_spr_item_row_styles(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	if (frm.fields_dict.items.$wrapper && frm.fields_dict.items.$wrapper.length) {
		frm.fields_dict.items.$wrapper.addClass('spr-items-wrap');
		frm.fields_dict.items.$wrapper.toggleClass('spr-doc-submitted', frm.doc && cint(frm.doc.docstatus) === 1);
	}
	sprEnsureItemsGridObserver(frm);
	ensure_spr_item_stylesheet();
	[0, 50, 150, 400, 900].forEach(function (ms) {
		setTimeout(function () {
			apply_spr_item_row_styles(frm);
		}, ms);
	});
}

/** After Save / Submit the grid DOM is rebuilt (and read-only when submitted). Re-apply GSM bands for several seconds. */
function spr_schedule_item_row_styles_after_doc_write(frm) {
	if (!frm || !frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	if (frm.fields_dict.items.$wrapper && frm.fields_dict.items.$wrapper.length) {
		frm.fields_dict.items.$wrapper.addClass('spr-items-wrap');
		frm.fields_dict.items.$wrapper.toggleClass('spr-doc-submitted', frm.doc && cint(frm.doc.docstatus) === 1);
	}
	sprEnsureItemsGridObserver(frm);
	ensure_spr_item_stylesheet();
	[0, 80, 200, 500, 1000, 1800, 3000, 5000, 8000, 12000, 16000, 20000, 25000, 30000].forEach(function (ms) {
		setTimeout(function () {
			if (!frm || !frm.fields_dict || !frm.fields_dict.items) {
				return;
			}
			apply_spr_item_row_styles(frm);
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
	const grid = frm.fields_dict.items.grid;
	if (!grid) {
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
}


// ===== TOTAL PRODUCED WEIGHT CALCULATION =====

function spr_compute_total_produced_weight(frm) {
	if (!frm || !frm.doc) {
		return 0;
	}
	const items = frm.doc.items || [];
	let total = 0;
	for (let i = 0; i < items.length; i++) {
		total += spr_round_net_weight_kg(items[i].net_weight);
	}
	return spr_round_net_weight_kg(total);
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
	const current = spr_round_net_weight_kg(frm.doc.total_produced_weight);

	if (Math.abs(current - calculated) > 0.001) {
		if (settings.silent) {
			frm.doc.total_produced_weight = calculated;
			frm.refresh_field('total_produced_weight');
		} else {
			frm.set_value('total_produced_weight', calculated);
		}
	}
}
