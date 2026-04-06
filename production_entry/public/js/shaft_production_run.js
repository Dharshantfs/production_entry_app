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
		}, 600);
		[0, 200, 600, 1200].forEach(function (ms) {
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
				if (d.customer) {
					frm.set_value('customer', d.customer);
				}
				if (d.custom_unit !== undefined && d.custom_unit !== null && d.custom_unit !== '') {
					frm.set_value('custom_unit', d.custom_unit);
				}
				if (d.custom_order_code !== undefined && d.custom_order_code !== null && d.custom_order_code !== '') {
					frm.set_value('custom_order_code', d.custom_order_code);
				}
				if (d.custom_party_code !== undefined && d.custom_party_code !== null && String(d.custom_party_code).trim() !== '') {
					const v = String(d.custom_party_code).trim();
					const field = frm.get_field('custom_label');
					const raw = field && field.df && field.df.options ? field.df.options : '';
					const opts = raw
						? raw
								.split('\n')
								.map(function (s) {
									return s.trim();
								})
								.filter(Boolean)
						: [];
					let pick = opts.indexOf(v) >= 0 ? v : null;
					if (!pick) {
						const low = v.toLowerCase();
						for (let i = 0; i < opts.length; i++) {
							if (opts[i].toLowerCase() === low) {
								pick = opts[i];
								break;
							}
						}
					}
					if (pick) {
						frm.set_value('custom_label', pick);
					}
				}
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
		spr_patch_items_grid_refresh(frm);
		update_shaft_job_achieved_from_items(frm);
		spr_register_spr_page_buttons(frm);
		[400, 800, 1500, 3000].forEach(function (ms) {
			setTimeout(function () {
				spr_register_spr_page_buttons(frm);
			}, ms);
		});
		spr_inject_gsm_legend(frm);
		schedule_spr_item_row_styles(frm);
		if (frm.doc && cint(frm.doc.docstatus) === 1) {
			spr_schedule_item_row_styles_after_doc_write(frm);
		}
	},

	after_save: function (frm) {
		spr_register_spr_page_buttons_after_save(frm);
		schedule_spr_item_row_styles(frm);
		spr_schedule_item_row_styles_after_doc_write(frm);
	},

	on_submit: function (frm) {
		schedule_spr_item_row_styles(frm);
		spr_schedule_item_row_styles_after_doc_write(frm);
	},

	items: {
		items_add: function (frm) {
			update_shaft_job_achieved_from_items(frm);
			schedule_spr_item_row_styles(frm);
		},
		items_remove: function (frm) {
			update_shaft_job_achieved_from_items(frm);
			schedule_spr_item_row_styles(frm);
		},
	},
});

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

/** Default WO qty (Kg): net/shaft from Available Jobs × shafts, else segment/PP fallbacks. */
function sprManualDefaultWoQty(line, noShafts) {
	const n = cint(noShafts);
	const nps = line.net_per_shaft_kg != null ? flt(line.net_per_shaft_kg) : null;
	if (nps != null && nps > 0) {
		return nps * n;
	}
	const fs =
		line.first_segment_planned_kg != null && line.first_segment_planned_kg !== ''
			? flt(line.first_segment_planned_kg)
			: null;
	if (fs != null && fs > 0) {
		return fs * n;
	}
	const pq = flt(line.planned_qty);
	return pq > 0 ? pq : 1;
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
						fieldname: 'spr_manual_pp_hint',
						fieldtype: 'HTML',
						options:
							'<p class="text-muted small" style="margin-bottom:8px;">' +
							__('Production Plan: {0}', [ppName || '—']) +
							'</p>',
					},
					{
						fieldname: 'no_of_shafts',
						fieldtype: 'Int',
						label: __('Number of shafts'),
						reqd: 1,
						default: 1,
					},
					{
						fieldname: 'line_select_html',
						fieldtype: 'HTML',
						label: __('Select items (manufacturing qty = net/shaft × shafts when Available Jobs match width)'),
						options: '<div class="spr-manual-lines-wrap"></div>',
					},
				],
				primary_action_label: __('Create Work Order(s)'),
				primary_action: function () {
					const no_of_shafts = cint(d.get_value('no_of_shafts'));
					if (no_of_shafts < 1) {
						frappe.msgprint(__('Number of shafts must be at least 1.'));
						return;
					}
					const items = [];
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
						});
					});
					if (!items.length) {
						frappe.msgprint(__('Select at least one line with valid Meter/Roll and Work Order qty.'));
						return;
					}
					d.hide();
					frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_create_manual_jobs_multi',
						args: {
							shaft_production_run: frm.doc.name,
							no_of_shafts: no_of_shafts,
							items: items,
						},
						freeze: true,
						freeze_message: __('Creating Work Order(s)...'),
						callback: function (r2) {
							const m = r2.message || {};
							const wos = (m.work_orders || []).join(', ');
							frappe.show_alert({
								message: __('Work Order(s) {0} (job {1}).', [wos || '', m.job_id || '']),
								indicator: 'green',
							});
							frm.reload_doc();
						},
					});
				},
			});

			function renderManualLinesTable() {
				const n = cint(d.get_value('no_of_shafts'));
				const wrap = d.$wrapper.find('.spr-manual-lines-wrap');
				if (!wrap.length) {
					return;
				}
				let html =
					'<table class="table table-bordered table-condensed" style="font-size:12px;margin-bottom:0;">';
				html +=
					'<thead><tr><th style="width:36px;"></th><th>' +
					__('Item / PP row') +
					'</th><th>' +
					__('Width (in)') +
					'</th><th>' +
					__('Meter/Roll') +
					'</th><th>' +
					__('Net/shaft (Kg)') +
					'</th><th>' +
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
					const defQ = sprManualDefaultWoQty(line, n);
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
					html += '<td style="max-width:220px;word-break:break-all;">' + frappe.utils.escape_html(label) + '</td>';
					html += '<td>' + wIn.toFixed(1) + '</td>';
					html +=
						'<td><input type="number" class="input-with-feedback spr-manual-meter-roll" data-idx="' +
						idx +
						'" value="500" step="0.1" style="width:100px" placeholder="500"/></td>';
					html += '<td>' + frappe.utils.escape_html(npsLabel) + '</td>';
					html +=
						'<td><input type="number" class="input-with-feedback spr-manual-qty" data-idx="' +
						idx +
						'" value="' +
						defQ.toFixed(3) +
						'" step="0.001" style="width:100px"/></td>';
					html += '</tr>';
				});
				html += '</tbody></table>';
				wrap.html(html);
			}

			d.show();
			renderManualLinesTable();
			const ns = d.fields_dict.no_of_shafts;
			if (ns && ns.$input) {
				ns.$input.on('change input', function () {
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
					return j.label || j.job_id;
				})
				.join('\n');
			const jobByLabel = {};
			jobs.forEach(function (j) {
				jobByLabel[j.label || j.job_id] = j;
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
									frm.reload_doc().then(function () {
								if (!cur_frm || !cur_frm.doc || !cur_frm.doc.items) {
									return;
								}
								
								// Loop through each item and calculate manually
								cur_frm.doc.items.forEach(function (row, idx) {
									if (!row || !row.name) {
										return;
									}
									
									const cdt = 'Shaft Production Run Item';
									const cdn = row.name;
									
									// DIRECTLY calculate net_weight inline (don't wait for handlers)
									let width = flt(row.width_inch);
									let gw = flt(row.gross_weight);
									
									// Calculate net_weight only from width + gross_weight (no GSM/meter_roll dependency)
									if (width > 0 && gw > 0) {
										let width_in_meter = width * 0.0254;
										// Use GSM if available, else use sticker_gsm as fallback
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
										
										let calc_net = flt(gw - core_weight, 3);
										// If calculated net is 0 or negative, fallback to gross_weight
										row.net_weight = (calc_net > 0) ? calc_net : flt(gw);
									} else {
										// No width or gross_weight - use 0
										row.net_weight = 0;
									}
									
									// Now calculate produced_gsm using net_weight
									let nw = flt(row.net_weight) || flt(row.gross_weight) || 0;
									let wi = flt(row.width_inch) || 0;
									let mr = flt(row.meter_roll) || 0;
									
									// DEBUG: log values to console
									console.log('Row ' + idx + ': nw=' + nw + ' wi=' + wi + ' mr=' + mr + ' gsm_calc=' + (nw > 0 && wi > 0 && mr > 0 ? ((nw * 1000) / (wi * mr * 0.0254)) : 'invalid'));
									
									// Calculate GSM only if we have valid values. If meter_roll is 0, result is 0
									if (nw > 0 && wi > 0 && mr > 0) {
										row.produced_gsm = Math.round((nw * 1000) / (wi * mr * 0.0254) * 100) / 100;
									} else {
										row.produced_gsm = 0;
									}
								});
								
								// Refresh grid to show updated values via grid API
								let grid = cur_frm.fields_dict.items.grid;
								if (grid) {
									grid.df.data = cur_frm.doc.items;
									grid.refresh();
								} else {
									cur_frm.refresh_field('items');
								}
								
								// Now save the calculated net_weight and produced_gsm to database
								cur_frm.save().then(function() {
									// Apply row styling and colors after save
									setTimeout(function () {
										apply_spr_item_row_styles(cur_frm);
										schedule_spr_item_row_styles(cur_frm);
									}, 100);
								});
									});
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
						const net = s.net_kg_per_shaft != null ? flt(s.net_kg_per_shaft).toFixed(3) : '—';
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
						tw.toFixed(4),
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
						spr_update_produced_gsm(frm, 'Shaft Production Run Item', row.name);
					});
					update_shaft_job_achieved_from_items(frm);
					schedule_spr_item_row_styles(frm);
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
		spr_update_produced_gsm(frm, cdt, cdn);
		update_shaft_job_achieved_from_items(frm);
	},
	gross_weight: function (frm, cdt, cdn) {
		spr_update_produced_gsm(frm, cdt, cdn);
		update_shaft_job_achieved_from_items(frm);
	},
	gsm: function (frm) {
		schedule_spr_item_row_styles(frm);
	},
	width_inch: function (frm, cdt, cdn) {
		spr_update_produced_gsm(frm, cdt, cdn);
	},
	meter_roll: function (frm, cdt, cdn) {
		spr_update_produced_gsm(frm, cdt, cdn);
	},
	produced_length_mtrs: function (frm, cdt, cdn) {
		spr_update_produced_gsm(frm, cdt, cdn);
	},
	produced_gsm: function (frm) {
		apply_spr_item_row_styles(frm);
		schedule_spr_item_row_styles(frm);
		[0, 50, 120, 250, 500, 900].forEach(function (ms) {
			setTimeout(function () {
				apply_spr_item_row_styles(frm);
			}, ms);
		});
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
	/** Print roll label (after Save Row). Set Print Format name on site: spr_roll_label_print_format in hooks or use default. */
	print_sticker: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!cint(row.row_ready_for_print) || !cint(row.row_locked)) {
			frappe.msgprint(__('Save Row first to lock the line and enable the label.'));
			return;
		}
		const fmt =
			(frappe.boot.spr_roll_label_print_format || window.SPR_ROLL_LABEL_PRINT_FORMAT || 'Roll Production Label') + '';
		const args = {
			doctype: frm.doctype,
			name: frm.doc.name,
			format: fmt,
			no_letterhead: 1,
		};
		if (row && row.name) {
			args._row_name = row.name;
		}
		const qs = $.param(args);
		window.open(frappe.urllib.get_full_url('/printview?' + qs), '_blank');
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
	
	// Get length: prefer produced_length_mtrs, fallback to meter_roll
	let mr = flt(row.meter_roll);
	if (frappe.meta.get_docfield('Shaft Production Run Item', 'produced_length_mtrs')) {
		const pl = flt(row.produced_length_mtrs);
		if (pl > 0) {
			mr = pl;
		}
	}
	
	// Calculate GSM only if all required values are present
	// Formula: (net_weight * 1000) / (width_inch * length_mtrs * 0.0254)
	let pgsm = 0;
	if (nw > 0 && wi > 0 && mr > 0) {
		pgsm = Math.round((nw * 1000) / (wi * mr * 0.0254) * 100) / 100;
	}
	
	frappe.model.set_value(cdt, cdn, 'produced_gsm', pgsm);
	apply_spr_item_row_styles(frm);
	schedule_spr_item_row_styles(frm);
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
	if (!frappe.meta.get_docfield('Shaft Production Run Job', 'custom_total_achieved_weight')) {
		return;
	}
	const sums = {};
	(frm.doc.items || []).forEach(function (it) {
		const k = sprNormalizeJobKey(it.job);
		if (!k) {
			return;
		}
		sums[k] = (sums[k] || 0) + flt(it.net_weight);
	});
	(frm.doc.shaft_jobs || []).forEach(function (sj) {
		const jid = sprShaftJobRowKey(sj);
		const v = jid && sums[jid] !== undefined ? sums[jid] : 0;
		const next = flt(v);
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
		// If produced_length_mtrs not set, check for fallback (meter_roll or ordered_length)
		const mr = flt(doc.meter_roll);
		const ol = flt(doc.ordered_length);
		return mr <= 0 && ol <= 0;  // Only incomplete if both fallbacks are missing
	}
	// If produced_length_mtrs is set but <= 0, still allow fallback
	if (flt(pl) <= 0) {
		const mr = flt(doc.meter_roll);
		const ol = flt(doc.ordered_length);
		return mr <= 0 && ol <= 0;  // Only incomplete if both fallbacks are missing
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
	
	// Get length: prefer produced_length_mtrs, fallback to meter_roll
	let mr = flt(doc.meter_roll);
	if (frappe.meta.get_docfield('Shaft Production Run Item', 'produced_length_mtrs')) {
		const pl = flt(doc.produced_length_mtrs);
		if (pl > 0) {
			mr = pl;
		}
	}
	
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
			console.warn('Could not resolve row for item at index', idx, doc);
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
