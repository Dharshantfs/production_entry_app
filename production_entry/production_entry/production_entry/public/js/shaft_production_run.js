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
				console.log('[SPR] get_production_plan_details response:', d);
				console.log('[SPR] response keys:', Object.keys(d));
				
				// Set all returned fields
				if (d.customer) {
					console.log('[SPR] Setting customer:', d.customer);
					frm.set_value('customer', d.customer);
				}
				if (d.custom_unit) {
					console.log('[SPR] Setting custom_unit:', d.custom_unit);
					frm.set_value('custom_unit', d.custom_unit);
				}
				if ('custom_order_code' in d) {
					console.log('[SPR] Setting custom_order_code:', d.custom_order_code);
					frm.set_value('custom_order_code', d.custom_order_code || '');
				}
				if ('custom_label' in d) {
					console.log('[SPR] Setting custom_label:', d.custom_label);
					frm.set_value('custom_label', d.custom_label || '');
				}
				if ('custom_total_planned_qty' in d) {
					console.log('[SPR] Setting custom_total_planned_qty:', d.custom_total_planned_qty);
					frm.set_value('custom_total_planned_qty', flt(d.custom_total_planned_qty || 0));
				}
				if ('custom_party_code' in d) {
					console.log('[SPR] Setting custom_party_code:', d.custom_party_code);
					frm.set_value('custom_party_code', d.custom_party_code || '');
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

/** Actions → Manual job: pick PP line, # shafts; server creates WO + manual shaft_jobs row. */
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
			if (!lines.length) {
				frappe.msgprint(
					__('No Production Plan lines found. Set Production Plan and ensure it has planned items.')
				);
				return;
			}
			const byLabel = {};
			const optLines = [];
			lines.forEach(function (l) {
				const label =
					l.item_code +
					' | ' +
					flt(l.width_inch) +
					' in | ' +
					String(l.production_plan_item || '');
				byLabel[label] = l;
				optLines.push(label);
			});
			const opts = optLines.join('\n');
			const d = new frappe.ui.Dialog({
				title: __('Manual job'),
				fields: [
					{
						fieldname: 'pp_line',
						fieldtype: 'Select',
						label: __('Production Plan line'),
						options: opts,
						reqd: 1,
					},
					{
						fieldname: 'info_html',
						fieldtype: 'HTML',
						label: ' ',
						options: '<div class="text-muted spr-manual-info"></div>',
					},
					{
						fieldname: 'wo_planned_qty',
						fieldtype: 'Float',
						label: __('Work Order qty (Kg — manufacturing / planned)'),
						reqd: 1,
						description: __(
							'Defaults from Production Plan or first combination segment from Available Jobs. Edit if needed.'
						),
					},
					{
						fieldname: 'no_of_shafts',
						fieldtype: 'Int',
						label: __('Number of shafts'),
						reqd: 1,
						default: 1,
					},
				],
				primary_action_label: __('Create Work Order'),
				primary_action: function (values) {
					const line = byLabel[values.pp_line];
					const no_of_shafts = cint(values.no_of_shafts);
					const woPlanned = flt(values.wo_planned_qty);
					if (!line) {
						frappe.msgprint(__('Select a valid line.'));
						return;
					}
					if (no_of_shafts < 1) {
						frappe.msgprint(__('Number of shafts must be at least 1.'));
						return;
					}
					if (!(woPlanned > 0)) {
						frappe.msgprint(__('Enter a Work Order qty greater than zero.'));
						return;
					}
					d.hide();
					frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_create_manual_job',
						args: {
							shaft_production_run: frm.doc.name,
							item_code: line.item_code,
							production_plan_item: line.production_plan_item,
							no_of_shafts: no_of_shafts,
							wo_qty: woPlanned,
						},
						freeze: true,
						freeze_message: __('Creating Work Order...'),
						callback: function (r2) {
							const m = r2.message || {};
							frappe.show_alert({
								message: __('Work Order {0} created (job {1}).', [m.work_order || '', m.job_id || '']),
								indicator: 'green',
							});
							frm.reload_doc();
						},
					});
				},
			});
			function updateInfo() {
				const line = byLabel[d.get_value('pp_line')];
				const el = d.$wrapper.find('.spr-manual-info');
				if (!line || !el.length) {
					return;
				}
				const netOnSpr = flt(line.existing_net_weight_kg);
				const firstSeg =
					line.first_segment_planned_kg != null && line.first_segment_planned_kg !== ''
						? flt(line.first_segment_planned_kg)
						: null;
				const ppQty = flt(line.planned_qty);
				const defaultWo = firstSeg != null && firstSeg > 0 ? firstSeg : ppQty > 0 ? ppQty : 1;
				if (d.fields_dict.wo_planned_qty) {
					const cur = d.get_value('wo_planned_qty');
					if (cur === null || cur === undefined || flt(cur) <= 0) {
						d.set_value('wo_planned_qty', defaultWo);
					}
				}
				let html =
					'<div>' +
					__('Width: {0} in', [flt(line.width_inch)]) +
					' · ';
				if (firstSeg != null) {
					html +=
						__('First combination segment planned (Available Jobs): {0} Kg', [
							firstSeg.toFixed(3),
						]) +
						' · ';
				}
				html +=
					__('Production Plan line qty: {0} Kg · Net on SPR rolls (this item): {1} Kg', [
						ppQty.toFixed(3),
						netOnSpr.toFixed(2),
					]) +
					'</div>';
				el.html(html);
			}
			d.show();
			updateInfo();
			if (d.fields_dict.pp_line && d.fields_dict.pp_line.$input) {
				d.fields_dict.pp_line.$input.on('change', updateInfo);
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
								'Choose the job from Available Jobs, then the width (in). The same single-roll gross is applied to every roll line for that job with that width. Sticker width uses Total Width from Available Jobs × number of packaging.'
							) +
							'</p>',
					},
					{
						fieldname: 'job_pick',
						fieldtype: 'Select',
						label: __('Job (Available Jobs)'),
						options: jobOpts,
						reqd: 1,
					},
					{
						fieldname: 'width_inch',
						fieldtype: 'Select',
						label: __('Width (in) for this job'),
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
												net_val = flt(item.gross_weight) - core_weight;
												net_val = flt(net_val, 3);
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
				if (!jp || !wf) {
					return;
				}
				const arr = widthsByJob[jp.job_id] || [];
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
				wf.refresh();
				d.set_value('width_inch', String(arr[0]));
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
				const jobW = flt(jp.total_width_available);
				const single = n > 0 ? whole / n : 0;
				const tw = jobW > 0 ? jobW * n : flt(wsel) * n;
				el.html(
					__('Single gross: {0} Kg · Sticker width (Available Jobs width × pkg): {1} in', [
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
		// CRITICAL: Calculate net_weight from gross_weight FIRST
		const row = locals[cdt][cdn];
		const net_val = calculate_net_weight_from_gross(row);
		
		// Set net_weight directly on row
		row.net_weight = net_val;
		
		// Refresh grid to display net_weight immediately
		frm.refresh_field('items');
		
		// Now calculate produced_gsm if meter_roll is present
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
	/** Print roll label (after Save Row). Calls custom print flow. */
	print_sticker: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!cint(row.row_ready_for_print) || !cint(row.row_locked)) {
			frappe.msgprint(__('Save Row first to lock the line and enable the label.'));
			return;
		}
		// Redirect to custom sticker generation flow
		frappe.generate_sticker_flow(row.name, frm);
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

function calculate_net_weight_from_gross(row) {
	// Calculate core_weight to get net_weight = gross_weight - core_weight
	const gw = flt(row.gross_weight) || 0;
	if (gw === 0) return 0;
	
	const width_inch = flt(row.width_inch) || 0;
	const gsm_val = flt(row.gsm) || flt(row.sticker_gsm) || 90;
	const width_in_meter = width_inch * 0.0254;
	const raw_weight = (gsm_val * width_in_meter * gw) / 1000.0;
	
	// Standard widths: [63, 85, 90, 118, 126]
	const standard_widths = [63, 85, 90, 118, 126];
	const is_standard = standard_widths.some(w => Math.abs(width_inch - w) < 0.01);
	
	let core_weight = 0;
	if (is_standard) {
		let base_weight_of_core = 1.3;
		if (raw_weight >= 50 && raw_weight <= 100) {
			base_weight_of_core = 1.8;
		} else if (raw_weight > 100) {
			base_weight_of_core = 2.5;
		}
		const numeric_core_width = flt(row.custom_core_width_mm) || 1600;
		core_weight = (base_weight_of_core / 1600.0) * numeric_core_width;
	} else {
		// Non-standard width proration
		let core_width, prorate;
		if (width_inch < 63) {
			core_width = 63; prorate = 1.30;
		} else if (width_inch < 85) {
			core_width = 85; prorate = 1.75;
		} else if (width_inch < 90) {
			core_width = 90; prorate = 1.86;
		} else if (width_inch < 118) {
			core_width = 118; prorate = 2.43;
		} else {
			core_width = 126; prorate = 2.60;
		}
		core_weight = (width_inch / core_width) * prorate;
	}
	
	const calc_net = gw - core_weight;
	return calc_net > 0 ? Math.round(calc_net * 100) / 100 : gw;
}

function spr_update_produced_gsm(frm, cdt, cdn) {
	if (!frappe.meta.get_docfield('Shaft Production Run Item', 'produced_gsm')) {
		return;
	}
	const row = locals[cdt][cdn];
	if (sprRollProducedLengthIncomplete(row)) {
		frappe.model.set_value(cdt, cdn, 'produced_gsm', 0);
		apply_spr_item_row_styles(frm);
		schedule_spr_item_row_styles(frm);
		return;
	}
	const nw = flt(row.net_weight);
	const gw = flt(row.gross_weight);
	const wgt = nw > 0 ? nw : gw;
	const w = flt(row.width_inch);
	let ln = flt(row.meter_roll);
	if (frappe.meta.get_docfield('Shaft Production Run Item', 'produced_length_mtrs')) {
		const pl = row.produced_length_mtrs;
		if (pl !== undefined && pl !== null && pl !== '') {
			ln = flt(pl);
		}
	}
	if (ln <= 0) {
		ln = flt(row.ordered_length);
	}
	if (ln <= 0) {
		ln = flt(row.custom_ordered_length);
	}
	const den = w * ln * 0.254;
	const val = den > 0 ? Math.round((wgt * 10000) / den * 100) / 100 : 0;
	frappe.model.set_value(cdt, cdn, 'produced_gsm', val);
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
	// Undefined = field not in row payload yet — do not force "incomplete" (restores band colours after save/reload).
	if (pl === undefined) {
		return false;
	}
	if (pl === null || pl === '') {
		return true;
	}
	return flt(pl) <= 0;
}

/** Same formula as spr_update_produced_gsm — use when produced_gsm not yet written (avoids all-white rows). */
function sprEffectiveProducedGsm(doc) {
	let p = flt(doc.produced_gsm);
	if (p > 0) {
		return p;
	}
	if (sprRollProducedLengthIncomplete(doc)) {
		return 0;
	}
	const nw = flt(doc.net_weight);
	const gw = flt(doc.gross_weight);
	const wgt = nw > 0 ? nw : gw;
	const w = flt(doc.width_inch);
	let ln = flt(doc.meter_roll);
	if (frappe.meta.get_docfield('Shaft Production Run Item', 'produced_length_mtrs')) {
		const pl = doc.produced_length_mtrs;
		if (pl !== undefined && pl !== null && pl !== '') {
			ln = flt(pl);
		}
	}
	if (ln <= 0) {
		ln = flt(doc.ordered_length);
	}
	if (ln <= 0) {
		ln = flt(doc.custom_ordered_length);
	}
	const den = w * ln * 0.254;
	return den > 0 ? Math.round((wgt * 10000) / den * 100) / 100 : 0;
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
	[0, 80, 200, 500, 1000, 1800, 3000, 5000, 8000, 12000, 16000, 20000].forEach(function (ms) {
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
		let $row = sprFindItemsRowDomByDocname(frm, doc);
		if (!$row || !$row.length) {
			if ($domRows && $domRows.length > idx) {
				$row = $($domRows.get(idx));
			}
		}
		if (!$row || !$row.length) {
			$row = sprResolveItemsRowWrapper(frm, doc, grid, idx);
		}
		if (!$row || !$row.length) {
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
// ===== CUSTOM PRINT STICKER FLOW =====

// Overwrite the print button behavior
frappe.generate_sticker_flow = function (row_name, frm) {
    var f = frm || cur_frm;
    var row = (locals['Shaft Production Run Item'] || {})[row_name] || (f.doc.items || []).find(function (r) { return r.name === row_name; }) || (f.doc.roll_wise_entry || []).find(function (r) { return r.name === row_name; });
    if (!row) return;

    frappe.db.get_value('Item', row.item_code, 'item_name', function (r) {
        var item_name = (r && r.item_name) || "";
        trigger_print_with_details(row_name, item_name, f);
    });
};

/** Scandinavian 6x4: skip "Select Fields to Print" and open label directly. */
function is_scandinavian_skip_custom_dialog(row, frm) {
    var f = frm || cur_frm;
    var lt = String(((f.doc || {}).custom_label || "Default")).toLowerCase();
    var customer_id = String(
        row.custom_customer ||
        row.custom_custom_customer ||
        row.customer ||
        ((f.doc || {}).custom_customer) ||
        ((f.doc || {}).customer) ||
        ""
    ).trim();
    return (
        lt.includes("customer 4x6") ||
        lt.includes("scandinavian") ||
        customer_id === "EXP-0071"
    );
}

function trigger_print_with_details(row_name, item_name, frm) {
    var doc = frm.doc;
    var raw_label = doc.custom_label || "Default";
    var label_type = raw_label.trim().toLowerCase();
    var row = (locals['Shaft Production Run Item'] || {})[row_name] || (doc.items || []).find(function (r) { return r.name === row_name; }) || (doc.roll_wise_entry || []).find(function (r) { return r.name === row_name; });
    if (!row) return;

    var details = extract_details_enhanced(item_name, row.item_code);
    var final_gsm = row.gsm || details.gsm || "";
    var final_color = row.color || details.color || "";
    var final_quality = row.quality || details.quality || "";

    if (label_type.includes("reliance") || label_type.includes("relience")) {
        flow_reliance_cm(row_name, final_gsm, final_color, final_quality, frm);
    } else if (label_type.includes("custom")) {
        var w_custom = row.width_inch || details.width_inch || "0";
        if (is_scandinavian_skip_custom_dialog(row, frm)) {
            frappe.run_print_logic(row_name, w_custom + " Inches", final_gsm, final_color, final_quality, frm);
        } else {
            flow_customized_label(row_name, final_gsm, final_color, final_quality, frm, w_custom);
        }
    } else {
        var w = row.width_inch || details.width_inch || "0";
        frappe.run_print_logic(row_name, w + " Inches", final_gsm, final_color, final_quality, frm);
    }
}

var QUALITY_MASTER = {
    "100": "PREMIUM", "101": "PLATINUM", "102": "SUPER PLATINUM",
    "103": "GOLD", "104": "SILVER", "105": "BRONZE",
    "106": "CLASSIC", "107": "SUPER CLASSIC", "108": "LIFE STYLE",
    "109": "ECO SPECIAL", "110": "ECO GREEN", "111": "SUPER ECO",
    "112": "ULTRA", "113": "DELUXE", "114": "UV"
};

function extract_details_enhanced(name, code) {
    var res = { gsm: null, color: null, width_inch: null, quality: null };
    var name_upper = (name || "").toUpperCase();

    if (code && code.length === 16 && /^\d+$/.test(code)) {
        var qual_code = code.substring(3, 6);
        if (QUALITY_MASTER[qual_code]) res.quality = QUALITY_MASTER[qual_code];
        var code_gsm = parseInt(code.substring(9, 12));
        if (code_gsm > 0) res.gsm = String(code_gsm);
        var code_width_mm = parseFloat(code.substring(12, 16));
        if (code_width_mm > 0) res.width_inch = Math.round(code_width_mm / 25.4);
        if (res.quality && name) {
            var qual_pos = name_upper.indexOf(res.quality.toUpperCase());
            if (qual_pos !== -1) {
                var after_qual = name.substring(qual_pos + res.quality.length).trim();
                after_qual = after_qual.replace(/\s*\d+\s*GSM.*/i, "").trim();
                if (after_qual) res.color = after_qual;
            }
        }
    } else if (name) {
        var known_qualities = ["SUPER PLATINUM", "SUPER CLASSIC", "LIFE STYLE", "ECO SPECIAL", "ECO GREEN", "SUPER ECO", "DELUXE", "PREMIUM", "PLATINUM", "GOLD", "SILVER", "BRONZE", "CLASSIC", "ULTRA", "UV"];
        known_qualities.sort(function (a, b) { return b.length - a.length; });
        for (var i = 0; i < known_qualities.length; i++) {
            var q = known_qualities[i];
            if (new RegExp('\\b' + q + '\\b', 'i').test(name_upper)) { res.quality = q; break; }
        }
        if (res.quality) {
            var qp = name_upper.indexOf(res.quality.toUpperCase());
            if (qp !== -1) {
                var aq = name.substring(qp + res.quality.length).trim();
                aq = aq.split(/\s*\d+\s*GSM/i)[0].trim();
                aq = aq.replace(/^[\s,:-]+|[\s,:-]+$/g, "");
                if (aq) res.color = aq;
            }
        }
        var mg = name.match(/(\d+)\s*GSM/i);
        if (mg) res.gsm = mg[1];
        var mw = name.match(/(\d+(\.\d+)?)\s*("|inch|in|'')/i);
        if (mw) res.width_inch = mw[1];
    }
    return res;
}

function flow_reliance_cm(row_name, gsm, color, quality, frm) {
    var f = frm || cur_frm;
    var row = (locals['Shaft Production Run Item'] || {})[row_name] || (f.doc.items || []).find(function(r) { return r.name === row_name; }) || (f.doc.roll_wise_entry || []).find(function(r) { return r.name === row_name; });
    var item_code = row ? (row.item_code || "") : "";
    var width_mm = (item_code.length >= 4) ? parseFloat(item_code.slice(-4)) : 0;
    var width_cm = (width_mm > 0) ? (width_mm / 10) : 0;

    frappe.prompt([{
        label: 'Verify Width (CM) for ' + (item_code || 'this row'),
        fieldname: 'width_cm',
        fieldtype: 'Float',
        default: width_cm,
        reqd: 1
    }], function (values) {
        frappe.run_print_logic(row_name, values.width_cm + " CM", gsm, color, quality, frm);
    }, 'Confirm Reliance Size (' + row.roll_no + ')', 'Preview Label');
}

function flow_customized_label(row_name, gsm, color, quality, frm, width_inch) {
    var dialog = new frappe.ui.Dialog({
        title: 'Select Fields to Print',
        fields: [
            { fieldtype: 'Section Break', label: 'Header Fields' },
            { fieldtype: 'Check', fieldname: 'show_company', label: 'Company Name', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_email', label: 'Company Email', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_customer', label: 'Customer Name', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_quality', label: 'Quality', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_order_code', label: 'Order Code', default: 1 },
            { fieldtype: 'Section Break', label: 'Body Fields' },
            { fieldtype: 'Check', fieldname: 'show_gsm', label: 'GSM', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_width', label: 'Width', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_length', label: 'Length', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_gw', label: 'Gross Weight', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_nw', label: 'Net Weight', default: 1 },
            { fieldtype: 'Section Break', label: 'Bottom Fields' },
            { fieldtype: 'Check', fieldname: 'show_batch', label: 'Batch No (Bottom)', default: 1 },
            { fieldtype: 'Check', fieldname: 'show_barcode', label: 'Barcode', default: 1 }
        ],
        primary_action_label: 'Print Label',
        primary_action: function(values) {
            dialog.hide();
            frappe.run_print_logic(row_name, width_inch + " Inches", gsm, color, quality, frm, values);
        }
    });
    dialog.show();
}

frappe.run_print_logic = function (row_name, final_width_display, final_gsm, final_color, final_quality, frm, custom_fields) {
    var f = frm || cur_frm;
    var row = (locals['Shaft Production Run Item'] || {})[row_name] || (f.doc.items || []).find(function(r) { return r.name === row_name; }) || (f.doc.roll_wise_entry || []).find(function(r) { return r.name === row_name; });
    if (!row) return;
    var normalized_custom_fields = normalize_custom_fields(custom_fields);
    var label_type = String(((f.doc || {}).custom_label || "Default")).toLowerCase();
    var customer_id_for_4x6 = String(
        row.custom_customer ||
        row.custom_custom_customer ||
        row.customer ||
        ((f.doc || {}).custom_customer) ||
        ((f.doc || {}).customer) ||
        ""
    ).trim();
    var is_customer_4x6 = (
        label_type.includes("customer 4x6") ||
        label_type.includes("scandinavian") ||
        customer_id_for_4x6 === "EXP-0071"
    );

    var proceed_run = function(customer_name) {
        var d = {
            company: "JAYASHREE SPUN BOND",
            quality: final_quality || "NON WOVEN FABRIC",
            gsm: final_gsm,
            color: final_color,
            width_val: final_width_display,
            item_code: row.item_code || "",
            barcode_data: row.batch_no || "",
            length: row.custom_produced_length_mtrs || "0",
            gw: (flt(row.gross_weight) || flt(row.net_weight)).toFixed(2),
            nw: flt(row.net_weight).toFixed(2),
            batch_no: row.batch_no || "",
            roll_no: row.roll_no || "",
            party_code: row.party_code || "",
            customer_name: customer_name || ""
        };

        if (is_customer_4x6) {
            build_customer_4x6_data(row, d, function (label_data) {
                var html4x6 = get_customer_4x6_format(label_data);
                var pw = window.open('', '_blank', 'width=920,height=520');
                if (pw) {
                    pw.document.write(html4x6);
                    pw.document.close();
                }
            });
            return;
        }

        var htmlContent = get_grid_format(d, label_type, normalized_custom_fields);
        var printWindow = window.open('', '_blank', 'height=650,width=500');
        if (printWindow) {
            printWindow.document.write(htmlContent);
            printWindow.document.close();
        }
    };

    var custom_customer_id = String(
        row.custom_customer ||
        row.custom_custom_customer ||
        row.customer ||
        ((f.doc || {}).custom_customer) ||
        ((f.doc || {}).customer) ||
        ""
    ).trim();
    if (custom_customer_id) {
        fetch_customer_display_name(custom_customer_id, function (name) {
            proceed_run(name);
        });
    } else if (row.party_code) {
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Customer',
                filters: { name: String(row.party_code).trim() },
                fieldname: 'customer_name'
            },
            callback: function(r) {
                if (r && r.message && r.message.customer_name) {
                    proceed_run(r.message.customer_name);
                } else {
                    frappe.call({
                        method: 'frappe.client.get_value',
                        args: {
                            doctype: 'Sales Order',
                            filters: { name: row.party_code },
                            fieldname: ['customer_name', 'customer']
                        },
                        callback: function(r2) {
                            if (r2 && r2.message && r2.message.customer_name) {
                                proceed_run(r2.message.customer_name);
                            } else if (r2 && r2.message && r2.message.customer) {
                                fetch_customer_display_name(r2.message.customer, function (name) {
                                    proceed_run(name);
                                });
                            } else {
                                proceed_run(String(row.party_code || "").trim());
                            }
                        }
                    });
                }
            }
        });
    } else {
        proceed_run("");
    }
};

function fetch_customer_display_name(customer_id, callback) {
    customer_id = String(customer_id || "").trim();
    if (!customer_id) {
        callback("");
        return;
    }
    function finish(display) {
        callback(String(display || "").trim() || customer_id);
    }
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Customer',
            filters: { name: customer_id },
            fieldname: ['customer_name']
        },
        callback: function (r) {
            var msg = (r && r.message) || {};
            var nm = String(msg.customer_name || "").trim();
            if (nm) {
                finish(nm);
                return;
            }
            frappe.call({
                method: 'frappe.client.get',
                args: { doctype: 'Customer', name: customer_id },
                callback: function (r2) {
                    var doc = (r2 && r2.message) || {};
                    var from_doc = String(doc.customer_name || "").trim();
                    finish(from_doc || customer_id);
                },
                error: function () {
                    finish(customer_id);
                }
            });
        },
        error: function () {
            finish(customer_id);
        }
    });
}

function round_width_mm_to_5(wmm) {
    var n = flt(wmm);
    if (n <= 0) return 0;
    return Math.round(n / 5) * 5;
}

function scandinavian_raw_width_mm(row) {
    var wmm = flt(row.width);
    if (wmm > 0) return wmm;
    var win = flt(row.width_inch);
    if (win > 0) return win * 25.4;
    return 0;
}

function compute_scandinavian_m2(row, length_m_str) {
    var L = flt(length_m_str);
    if (L <= 0) return "";
    var width_mm_r = round_width_mm_to_5(scandinavian_raw_width_mm(row));
    if (width_mm_r <= 0) return "";
    var width_m = width_mm_r / 1000;
    var m2 = width_m * L;
    return String(Math.round(m2));
}

function scandinavian_width_mm_display(row) {
    var w = round_width_mm_to_5(scandinavian_raw_width_mm(row));
    return w > 0 ? String(w) : "";
}

function scandinavian_order_code(row) {
    return String(
        row.party_code ||
        row.custom_party_code ||
        row.sales_order ||
        row.order_code ||
        ""
    ).trim();
}

function resolve_sales_order_docname(order_code, callback) {
    var code = String(order_code || "").trim();
    if (!code) {
        callback(null);
        return;
    }
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Sales Order',
            filters: { custom_party_code: code },
            fields: ['name'],
            limit_page_length: 1
        },
        callback: function (r) {
            var msg = (r && r.message) || [];
            if (msg.length > 0 && msg[0].name) {
                callback(msg[0].name);
                return;
            }
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Sales Order',
                    filters: { name: code },
                    fields: ['name'],
                    limit_page_length: 1
                },
                callback: function (r2) {
                    var msg2 = (r2 && r2.message) || [];
                    if (msg2.length > 0 && msg2[0].name) {
                        callback(msg2[0].name);
                    } else {
                        callback(null);
                    }
                },
                error: function () {
                    callback(null);
                }
            });
        },
        error: function () {
            callback(null);
        }
    });
}

function strip_html_simple(s) {
    return String(s || "")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

function scandinavian_treatment_display(raw) {
    var s = String(raw || "").toLowerCase().replace(/\s+/g, " ").trim();
    if (!s) return "";
    if (s.indexOf("hydrophilic") !== -1) return "HI";
    if (s.indexOf("hydrophobic") !== -1) return "HO";
    if (s.indexOf("fire retardant") !== -1 || s.indexOf("fire-retardant") !== -1) return "FR";
    if (/\buv\b/.test(s)) return "UV";
    return String(raw || "").trim();
}

function scandinavian_from_so_line(line, so_doc, fallbacks) {
    line = line || {};
    var article_no = String(
        line.custom_purchase_no ||
        line.item_code ||
        ""
    ).trim();
    var article_name = String(
        line.custom_purchase_quality_name ||
        strip_html_simple(line.description) ||
        line.item_name ||
        ""
    ).trim();
    var tracking = "";
    if (so_doc) {
        tracking = String(so_doc.po_no || "").trim();
    }
    if (!tracking) {
        tracking = fallbacks.tracking_no;
    }
    return {
        article_no: article_no,
        article_name: article_name,
        tracking_no: tracking,
        basis_weight: fallbacks.basis_weight,
        rolls_in_package: fallbacks.rolls_in_package,
        length_per_roll: fallbacks.length_per_roll,
        width_mm: fallbacks.width_mm,
        m2_in_package: fallbacks.m2_in_package,
        kg_per_package: fallbacks.kg_per_package,
        treatment: fallbacks.treatment,
        customer_company: fallbacks.customer_company,
        customer_address: fallbacks.customer_address,
        customer_contact: fallbacks.customer_contact
    };
}

function build_customer_4x6_data(row, base_data, callback) {
    var order_code = scandinavian_order_code(row);
    var length_per_roll = String(row.custom_produced_length_mtrs || "").trim();
    var width_mm_disp = scandinavian_width_mm_display(row);
    var m2_calc = compute_scandinavian_m2(row, length_per_roll);
    var fallbacks = {
        article_no: "",
        article_name: "",
        tracking_no: String(row.po_no || "").trim(),
        basis_weight: String(base_data.gsm || "").trim(),
        rolls_in_package: "1",
        length_per_roll: length_per_roll,
        width_mm: width_mm_disp,
        m2_in_package: m2_calc,
        kg_per_package: String(base_data.nw || "").trim(),
        treatment: String(base_data.quality || "").trim(),
        customer_company: "Scandinavian Nonwoven AB",
        customer_address: "Alevagen 1 - S-291 62 Kristianstad - Sweden",
        customer_contact: "Tel: +46 44 203960 - info@nonwoven.se - www.nonwoven.se"
    };

    if (!order_code) {
        callback(fallbacks);
        return;
    }

    resolve_sales_order_docname(order_code, function (so_name) {
        if (!so_name) {
            callback(fallbacks);
            return;
        }

        function finish_from_list(so_items) {
            var match = null;
            var list = so_items || [];
            for (var i = 0; i < list.length; i++) {
                if (String(list[i].item_code || "") === String(row.item_code || "")) {
                    match = list[i];
                    break;
                }
            }
            if (!match && list.length > 0) {
                match = list[0];
            }
            frappe.call({
                method: 'frappe.client.get_value',
                args: { doctype: 'Sales Order', filters: { name: so_name }, fieldname: 'po_no' },
                callback: function (gv) {
                    var pseudoSo = { po_no: (gv && gv.message && gv.message.po_no) || '' };
                    callback(scandinavian_from_so_line(match, pseudoSo, fallbacks));
                },
                error: function () {
                    callback(scandinavian_from_so_line(match, null, fallbacks));
                }
            });
        }

        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Sales Order', name: so_name },
            callback: function (r) {
                var so = r && r.message;
                if (!so) {
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'Sales Order Item',
                            filters: { parent: so_name },
                            fields: [
                                'item_code', 'item_name', 'description',
                                'custom_purchase_no', 'custom_purchase_quality_name'
                            ],
                            limit_page_length: 200
                        },
                        callback: function (r2) {
                            finish_from_list((r2 && r2.message) || []);
                        },
                        error: function () {
                            callback(fallbacks);
                        }
                    });
                    return;
                }
                var items = so.items || [];
                var match = null;
                for (var j = 0; j < items.length; j++) {
                    if (String(items[j].item_code || "") === String(row.item_code || "")) {
                        match = items[j];
                        break;
                    }
                }
                if (!match && items.length > 0) {
                    match = items[0];
                }
                callback(scandinavian_from_so_line(match, so, fallbacks));
            },
            error: function () {
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Sales Order Item',
                        filters: { parent: so_name },
                        fields: [
                            'item_code', 'item_name', 'description',
                            'custom_purchase_no', 'custom_purchase_quality_name'
                        ],
                        limit_page_length: 200
                    },
                    callback: function (r2) {
                        finish_from_list((r2 && r2.message) || []);
                    },
                    error: function () {
                        callback(fallbacks);
                    }
                });
            }
        });
    });
}

function get_grid_format(d, type, custom_fields) {
    type = (type || "default").trim().toLowerCase();
    var isReliance = type.includes("reliance") || type.includes("relience");
    var isPerfect = type.includes("perfect");
    var isPlainCC = type.includes("plain cc");
    var isPlain = type.includes("plain") && !isPlainCC;
    var isCustom = type.includes("custom");
    var isDefault = !isReliance && !isPerfect && !isPlainCC && !isPlain && !isCustom;

    var header = "";
    var sub1 = "";
    var sub2 = "";

    var fields = custom_fields || {
        show_company: 1, show_email: 1, show_customer: 1, show_quality: 1, show_order_code: 1,
        show_gsm: 1, show_width: 1, show_length: 1, show_gw: 1, show_nw: 1,
        show_batch: 1, show_barcode: 1
    };

    var qualityText = fields.show_quality ? String(d.quality || "").trim() : "";
    var orderCodeText = fields.show_order_code ? String(d.party_code || "").trim() : "";
    var qualityAndOrder = [qualityText, orderCodeText].filter(function (s) { return !!s; }).join(" / ");

    if (isDefault || isCustom) {
        header = fields.show_company ? "JayaShree Spun Bond" : "";
        sub1 = fields.show_email ? "enquiry@jayashreespunbond.com" : "";
        sub2 = qualityAndOrder;
    } else if (isPlainCC) {
        header = fields.show_company ? "Non Woven Fabrics" : "";
        sub1 = qualityAndOrder;
        sub2 = "";
    } else {
        header = fields.show_company ? "Non Woven Fabrics" : "";
        sub1 = qualityAndOrder;
        sub2 = "";
    }

    var rows = [];
    var customer_header_row = "";
    if (isCustom && fields.show_customer && d.customer_name) {
        customer_header_row = '<div class="customer-sub">' + escape_html(d.customer_name) + '</div>';
    }
    if (fields.show_gsm) {
        rows.push('<tr><td><span class="lbl">GSM</span></td><td class="colon">:</td><td><span class="val">' + d.gsm + '</span></td></tr>');
    }

    var widthUnit = " Inches";
    var wValLower = String(d.width_val || "").toLowerCase();
    if (wValLower.includes("inches") || wValLower.includes("inch") || wValLower.includes("cm") || wValLower.includes('"')) {
        widthUnit = ""; 
    }
    if (fields.show_width) {
        rows.push('<tr><td><span class="lbl">Width</span></td><td class="colon">:</td><td><span class="val">' + d.width_val + widthUnit + '</span></td></tr>');
    }

    var lengthUnit = " Mtrs";
    var lValStr = String(d.length || "");
    if (lValStr.toLowerCase().includes("mtr")) lengthUnit = "";
    if (fields.show_length) {
        rows.push('<tr><td><span class="lbl">Length</span></td><td class="colon">:</td><td><span class="val">' + d.length + lengthUnit + '</span></td></tr>');
    }

    if (fields.show_gw) {
        rows.push('<tr><td><span class="lbl">Gross Weight</span></td><td class="colon">:</td><td><span class="val">' + d.gw + ' Kgs</span></td></tr>');
    }
    if (fields.show_nw) {
        rows.push('<tr><td><span class="lbl">Net Weight</span></td><td class="colon">:</td><td><span class="val">' + d.nw + ' Kgs</span></td></tr>');
    }

    var btmRow = "";
    if (fields.show_batch) {
        btmRow = '<div class="btm-row"><span class="lbl">BATCH No : <span class="batch-val">' + d.batch_no + '</span></span></div>';
    }

    var rowCount = rows.length;
    var isCompact = !isCustom && rowCount > 5;
    var hasCustomerHeader = !!customer_header_row;
    var hasHeaderContent = !!(header || sub1 || sub2 || customer_header_row);
    var hasBatch = !!(fields.show_batch && d.batch_no);
    var hasBarcode = !!fields.show_barcode;

    var labelStyle, headerSize, tdPad, lblSize, valSize, batchLblSize, batchValSize, barcodeH, barcodeFontSize, barcodeWidth, headerPadBot, subheaderSize, emailSize, innerMargin, innerPad, headerMarginBot, barcodeContPad, btmPadTop, btmMargin, colonSize, customerSubSize, customerSubMarginTop, customerSubMarginBottom, tableMarginY, tableJustify, headerBorderStyle, headerDisplay, btmDisplay, barcodeDisplay, tableHeight;

    if (isCompact) {
        labelStyle = 'font-size: 0.95em;';
        headerSize = 'font-size: 22px;';
        emailSize = '11px';
        subheaderSize = '15px';
        headerPadBot = '3px';
        headerMarginBot = '3px';
        innerMargin = '5px';
        innerPad = '5px 8px';
        tdPad = '3px 0';
        colonSize = '14px';
        lblSize = '15px';
        valSize = '15px';
        btmPadTop = '4px';
        btmMargin = '1px 0';
        batchLblSize = '14px';
        batchValSize = '16px';
        barcodeContPad = '2px 0 1px 0';
        barcodeH = '50px';
        barcodeFontSize = 11;
        barcodeWidth = 1.9;
        customerSubSize = '13px';
        customerSubMarginTop = '1px';
        customerSubMarginBottom = '0px';
        tableMarginY = '1px';
        tableJustify = rowCount <= 2 ? 'center' : 'flex-start';
        tableHeight = '100%';
    } else {
        labelStyle = 'font-size: 1.05em;';
        headerSize = 'font-size: 24px;';
        emailSize = '12px';
        subheaderSize = (isCustom && hasCustomerHeader) ? '15px' : '17px';
        headerPadBot = (isCustom && hasCustomerHeader) ? '3px' : '4px';
        headerMarginBot = (isCustom && hasCustomerHeader) ? '3px' : '4px';
        innerMargin = '6px';
        innerPad = (isCustom && hasCustomerHeader) ? '5px 9px' : '6px 10px';
        tdPad = (isCustom && hasCustomerHeader) ? '4px 0' : '5px 0';
        colonSize = '15px';
        lblSize = (isCustom && hasCustomerHeader) ? '15px' : '16px';
        valSize = (isCustom && hasCustomerHeader) ? '15px' : '16px';
        btmPadTop = (isCustom && hasCustomerHeader) ? '5px' : '6px';
        btmMargin = '2px 0';
        batchLblSize = (isCustom && hasCustomerHeader) ? '15px' : '16px';
        batchValSize = (isCustom && hasCustomerHeader) ? '17px' : '18px';
        barcodeContPad = (isCustom && hasCustomerHeader) ? '2px 0 1px 0' : '3px 0 2px 0';
        barcodeH = (isCustom && hasCustomerHeader) ? '52px' : '55px';
        barcodeFontSize = 12;
        barcodeWidth = 2.0;
        customerSubSize = (isCustom && hasCustomerHeader) ? '14px' : '15px';
        customerSubMarginTop = '1px';
        customerSubMarginBottom = '1px';
        tableMarginY = (isCustom && hasCustomerHeader) ? '1px' : '2px';
        tableJustify = rowCount <= 2 ? 'center' : 'flex-start';
        tableHeight = 'auto';
    }
    headerBorderStyle = hasHeaderContent ? '2px solid #333' : 'none';
    headerDisplay = hasHeaderContent ? 'block' : 'none';
    btmDisplay = hasBatch ? 'flex' : 'none';
    barcodeDisplay = hasBarcode ? 'flex' : 'none';

    var missingSections = (hasHeaderContent ? 0 : 1) + (hasBatch ? 0 : 1) + (hasBarcode ? 0 : 1);
    if (missingSections > 0) {
        tdPad = (parseInt(tdPad, 10) + missingSections) + 'px 0';
        lblSize = (parseInt(lblSize, 10) + (missingSections > 1 ? 1 : 0)) + 'px';
        valSize = (parseInt(valSize, 10) + (missingSections > 1 ? 1 : 0)) + 'px';
        tableJustify = 'center';
        tableHeight = '100%';
    }

    return '<html><head><title>Label Preview</title><style>' +
        '@media print { .btn-panel { display: none !important; } @page { size: 4in 4in; margin: 0; } body { margin: 0; } }' +
        'body { font-family: "Arial", sans-serif; margin: 0; padding: 0; text-align: center; background: #eee; ' + labelStyle + ' }' +
        '.btn-panel { padding: 10px; background: #eee; }' +
        '.sticker { width: 4in; height: 4in; margin: 20px auto; border: 2px solid black; background: white; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; }' +
        '.inner-border { border: 2px solid black; margin: ' + innerMargin + '; padding: ' + innerPad + '; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; overflow: hidden; }' +
        '.header { text-align: center; display: ' + headerDisplay + '; border-bottom: ' + headerBorderStyle + '; padding-bottom: ' + headerPadBot + '; margin-bottom: ' + headerMarginBot + '; }' +
        '.company { ' + headerSize + ' font-weight: 900; letter-spacing: 0.5px; margin-bottom: 1px; }' +
        '.email { font-size: ' + emailSize + '; font-weight: bold; color: #444; margin-bottom: 1px; }' +
        '.customer-sub { font-size: ' + customerSubSize + '; font-weight: 900; color: #111; letter-spacing: 0.3px; margin-top: ' + customerSubMarginTop + '; margin-bottom: ' + customerSubMarginBottom + '; }' +
        '.subheader { font-size: ' + subheaderSize + '; font-weight: 900; color: black; letter-spacing: 0.5px; margin-top: 1px; }' +
        '.table-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: ' + tableJustify + '; margin: ' + tableMarginY + ' 0; }' +
        'table { width: 100%; height: ' + tableHeight + '; border-collapse: collapse; margin: 0 auto; }' +
        'td { padding: ' + tdPad + '; vertical-align: middle; border: none; text-align: left; }' +
        'td:nth-child(1) { width: 44%; padding-left: 8px; }' +
        'td.colon { width: 5%; text-align: center; font-weight: bold; font-size: ' + colonSize + '; }' +
        'td:nth-child(3) { width: 51%; padding-left: 4px; }' +
        '.lbl { font-size: ' + lblSize + '; font-weight: 900; color: #333; }' +
        '.val { font-size: ' + valSize + '; font-weight: 900; color: #000; }' +
        '.btm-row { display: ' + btmDisplay + '; justify-content: center; align-items: center; border-top: 2px dashed #666; padding-top: ' + btmPadTop + '; margin: ' + btmMargin + '; }' +
        '.btm-row .lbl { font-size: ' + batchLblSize + '; }' +
        '.btm-row .batch-val { font-weight: 900; color: #000; font-size: ' + batchValSize + '; }' +
        '.barcode-container { display: ' + barcodeDisplay + '; justify-content: center; align-items: center; padding: ' + barcodeContPad + '; }' +
        '#barcode { max-width: 100%; height: ' + barcodeH + '; }' +
        '</style></head><body>' +
        '<div class="btn-panel"><button onclick="window.print()" style="padding:10px 20px; font-weight:bold; cursor:pointer;">PRINT</button><button onclick="window.close()" style="padding:10px 20px; margin-left:10px;">CLOSE</button></div>' +
        '<div class="sticker"><div class="inner-border">' +
        '<div class="header">' +
            (header ? '<div class="company">' + header + '</div>' : '') +
            (sub1 ? '<div class="email">' + sub1 + '</div>' : '') +
            customer_header_row +
            (sub2 ? '<div class="subheader">' + sub2 + '</div>' : '') +
        '</div>' +
        '<div class="table-container"><table>' + rows.join('') + '</table></div>' +
        btmRow +
        '<div class="barcode-container"><svg id="barcode"><\/svg><\/div>' +
        '<\/div><\/div>' +
        '<script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.0/dist/JsBarcode.all.min.js"><\/script>' +
        (hasBarcode ? ('<script>JsBarcode("#barcode", "' + d.barcode_data + '", { format: "CODE128", displayValue: true, fontSize: ' + barcodeFontSize + ', textMargin: 1, height: ' + parseInt(barcodeH) + ', width: ' + barcodeWidth + ', margin: 0 });<\/script>') : '') +
        '<\/body><\/html>';
}

function get_customer_4x6_format(d) {
    return '<html><head><title>Customer Label 6x4</title><style>' +
        '@media print { .btn-panel { display:none !important; } @page { size: 6in 4in; margin: 0; } body { margin: 0; } }' +
        'html, body { font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; background: #eee; }' +
        'body { min-height: 100vh; box-sizing: border-box; }' +
        '.btn-panel { padding: 10px; background: #eee; text-align: center; }' +
        '.label { width: 6in; height: 4in; min-width: 6in; min-height: 4in; max-width: 6in; max-height: 4in; margin: 14px auto; background: #fff; box-sizing: border-box; border: 2px solid #000; padding: 8px 12px 6px; display: flex; flex-direction: column; justify-content: space-between; overflow: hidden; flex-shrink: 0; }' +
        '.top-block { flex: 0 0 auto; }' +
        '.top-block > p:nth-child(1) { margin: 0 0 2px; }' +
        '.top-block > p:nth-child(2) { margin: 0 0 6px; }' +
        '.top-block > p:nth-child(3) { margin: 5px 0 3px; }' +
        '.top-block > p:nth-child(4) { margin: 0 0 8px; }' +
        '.line-label { font-size: 14px; font-weight: 400; margin: 0; }' +
        '.line-value { font-size: 40px; font-weight: 700; margin: 0; line-height: 0.98; letter-spacing: -0.5px; }' +
        '.line-caption { font-size: 14px; margin: 0; }' +
        '.line-text { font-size: 18px; font-weight: 700; margin: 0; line-height: 1.1; }' +
        '.mid-wrap { flex: 1 1 0; min-height: 0; width: 100%; display: flex; flex-direction: column; justify-content: stretch; align-items: stretch; }' +
        '.row-dual { display: grid; grid-template-columns: 1fr 1fr; column-gap: 16px; width: 100%; margin-top: 2px; margin-bottom: 4px; align-items: start; }' +
        '.row-dual .cell-right .k, .row-dual .cell-right .v { text-align: right; }' +
        '.grid-spec { flex: 1 1 auto; width: 100%; min-height: 0; display: grid; grid-template-columns: 1fr 1fr 1fr; grid-template-rows: 1fr 1fr; column-gap: 16px; row-gap: 2px; align-content: stretch; justify-items: stretch; }' +
        '.cell { display: flex; flex-direction: column; justify-content: center; padding: 3px 0; min-height: 0; }' +
        '.cell .k { font-size: 13px; font-weight: 400; margin: 0; line-height: 1.1; }' +
        '.cell .v { font-size: 23px; font-weight: 700; line-height: 1.05; margin-top: 2px; min-height: 1.05em; }' +
        '.cell-mid { text-align: center; align-items: center; }' +
        '.cell-mid .k, .cell-mid .v { text-align: center; }' +
        '.cell-right { text-align: right; align-items: flex-end; }' +
        '.cell-right .k, .cell-right .v { text-align: right; }' +
        '.footer { flex: 0 0 auto; padding-top: 2px; }' +
        '.cust-name { text-align: center; font-size: 17px; font-weight: 700; margin: 0; }' +
        '.cust-addr { text-align: center; font-size: 11px; margin-top: 2px; text-decoration: underline; }' +
        '.cust-contact { text-align: center; font-size: 10px; margin-top: 2px; line-height: 1.2; }' +
        '</style></head><body>' +
        '<div class="btn-panel"><button onclick="window.print()" style="padding:10px 20px; font-weight:bold; cursor:pointer;">PRINT</button><button onclick="window.close()" style="padding:10px 20px; margin-left:10px;">CLOSE</button></div>' +
        '<div class="label">' +
        '<div class="top-block">' +
        '<p class="line-label">Article No</p>' +
        '<p class="line-value">' + escape_html(d.article_no) + '</p>' +
        '<p class="line-caption">Article</p>' +
        '<p class="line-text">' + escape_html(d.article_name) + '</p>' +
        '</div>' +
        '<div class="mid-wrap">' +
        '<div class="row-dual">' +
        '<div class="cell"><div class="k">Tracking No</div><div class="v">' + escape_html(d.tracking_no) + '</div></div>' +
        '<div class="cell cell-right"><div class="k">Length per roll (m)</div><div class="v">' + escape_html(d.length_per_roll) + '</div></div>' +
        '</div>' +
        '<div class="grid-spec">' +
        '<div class="cell"><div class="k">Basis Weight (g/m²)</div><div class="v">' + escape_html(d.basis_weight) + '</div></div>' +
        '<div class="cell cell-mid"><div class="k">Rolls in package</div><div class="v">' + escape_html(d.rolls_in_package) + '</div></div>' +
        '<div class="cell cell-right"><div class="k">Width (mm)</div><div class="v">' + escape_html(d.width_mm) + '</div></div>' +
        '<div class="cell"><div class="k">m² in package</div><div class="v">' + escape_html(d.m2_in_package) + '</div></div>' +
        '<div class="cell cell-mid"><div class="k">Kg per package</div><div class="v">' + escape_html(d.kg_per_package) + '</div></div>' +
        '<div class="cell cell-right"><div class="k">Treatment</div><div class="v">' + escape_html(scandinavian_treatment_display(d.treatment)) + '</div></div>' +
        '</div>' +
        '</div>' +
        '<div class="footer">' +
        '<div class="cust-name">' + escape_html(d.customer_company) + '</div>' +
        '<div class="cust-addr">' + escape_html(d.customer_address) + '</div>' +
        '<div class="cust-contact">' + escape_html(d.customer_contact) + '</div>' +
        '</div>' +
        '</div>' +
        '</body></html>';
}

function escape_html(s) {
    if (s === null || s === undefined) return "";
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function normalize_custom_fields(custom_fields) {
    var defaults = {
        show_company: 1, show_email: 1, show_customer: 1, show_quality: 1, show_order_code: 1,
        show_gsm: 1, show_width: 1, show_length: 1, show_gw: 1, show_nw: 1,
        show_batch: 1, show_barcode: 1
    };
    if (!custom_fields) return defaults;

    var as_bool = function(v, default_value) {
        if (v === undefined || v === null || v === "") return !!default_value;
        if (typeof v === "boolean") return v;
        if (typeof v === "number") return v === 1;
        var s = String(v).trim().toLowerCase();
        return s === "1" || s === "true" || s === "yes" || s === "on";
    };

    return {
        show_company: as_bool(custom_fields.show_company, 1),
        show_email: as_bool(custom_fields.show_email, 1),
        show_customer: as_bool(custom_fields.show_customer, 1),
        show_quality: as_bool(custom_fields.show_quality, 1),
        show_order_code: as_bool(custom_fields.show_order_code, 1),
        show_gsm: as_bool(custom_fields.show_gsm, 1),
        show_width: as_bool(custom_fields.show_width, 1),
        show_length: as_bool(custom_fields.show_length, 1),
        show_gw: as_bool(custom_fields.show_gw, 1),
        show_nw: as_bool(custom_fields.show_nw, 1),
        show_batch: as_bool(custom_fields.show_batch, 1),
        show_barcode: as_bool(custom_fields.show_barcode, 1)
    };
}