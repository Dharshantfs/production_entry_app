frappe.ui.form.on('Shaft Production Run', {
	setup: function (frm) {
		frm.add_custom_button(
			__('Manual job'),
			function () {
				spr_open_manual_job_dialog(frm);
			},
			__('Actions')
		);
		frm.add_custom_button(
			__('Bundle packaging'),
			function () {
				spr_open_bundle_packaging_dialog(frm);
			},
			__('Actions')
		);
	},

	onload: function (frm) {
		setTimeout(function () {
			spr_patch_items_grid_refresh(frm);
		}, 0);
		setTimeout(function () {
			spr_patch_items_grid_refresh(frm);
		}, 400);
		[0, 200, 600, 1200].forEach(function (ms) {
			setTimeout(function () {
				schedule_spr_item_row_styles(frm);
			}, ms);
		});
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
		schedule_spr_item_row_styles(frm);
	},

	after_save: function (frm) {
		schedule_spr_item_row_styles(frm);
	},

	on_submit: function (frm) {
		schedule_spr_item_row_styles(frm);
		[0, 150, 500, 1200].forEach(function (ms) {
			setTimeout(function () {
				schedule_spr_item_row_styles(frm);
			}, ms);
		});
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
					if (!line) {
						frappe.msgprint(__('Select a valid line.'));
						return;
					}
					if (no_of_shafts < 1) {
						frappe.msgprint(__('Number of shafts must be at least 1.'));
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
				const net = flt(line.existing_net_weight_kg);
				el.html(
					'<div>' +
						__('Width: {0} in · Planned net on SPR for this item: {1} Kg', [
							flt(line.width_inch),
							net.toFixed(2),
						]) +
						'</div>'
				);
			}
			d.show();
			updateInfo();
			if (d.fields_dict.pp_line && d.fields_dict.pp_line.$input) {
				d.fields_dict.pp_line.$input.on('change', updateInfo);
			}
		},
	});
}

/** Actions → Bundle packaging: pick roll line, set gross + sticker row (Kg / inch). */
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
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_get_bundle_packaging_lines',
		args: { shaft_production_run: frm.doc.name },
		freeze: true,
		freeze_message: __('Loading roll lines...'),
		callback: function (r) {
			const packLines = r.message || [];
			if (!packLines.length) {
				frappe.msgprint(
					__('No roll lines yet. Use Create Roll Entry on a shaft job to add lines to Items.')
				);
				return;
			}
			const byLabel = {};
			packLines.forEach(function (l) {
				byLabel[l.label] = l;
			});
			const opts = packLines
				.map(function (l) {
					return l.label;
				})
				.join('\n');
			const d = new frappe.ui.Dialog({
				title: __('Bundle packaging'),
				fields: [
					{
						fieldname: 'roll_line',
						fieldtype: 'Select',
						label: __('Roll line'),
						options: opts,
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
					const line = byLabel[values.roll_line];
					const n = cint(values.no_of_packaging);
					const whole = flt(values.whole_gross_kg);
					if (!line) {
						frappe.msgprint(__('Select a roll line.'));
						return;
					}
					if (n < 1 || whole <= 0) {
						frappe.msgprint(__('Enter a valid packaging count and whole gross weight.'));
						return;
					}
					d.hide();
					frappe.call({
						method:
							'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_apply_bundle_packaging',
						args: {
							shaft_production_run: frm.doc.name,
							spr_item_row_name: line.name,
							no_of_packaging: n,
							whole_gross_kg: whole,
						},
						freeze: true,
						freeze_message: __('Applying bundle packaging...'),
						callback: function (r2) {
							const m = r2.message || {};
							frappe.show_alert({
								message: __(
									'Applied: single gross {0} Kg, total width {1} in, bundle net {2} Kg.',
									[
										String(m.single_roll_gross_kg != null ? m.single_roll_gross_kg : ''),
										String(m.total_width_inch != null ? m.total_width_inch : ''),
										String(m.sticker_bundle_weight_kg != null ? m.sticker_bundle_weight_kg : ''),
									]
								),
								indicator: 'green',
							});
							frm.reload_doc();
						},
					});
				},
			});
			function recalc() {
				const line = byLabel[d.get_value('roll_line')];
				const n = cint(d.get_value('no_of_packaging'));
				const whole = flt(d.get_value('whole_gross_kg'));
				const el = d.$wrapper.find('.spr-bundle-calc');
				if (!line || !el.length) {
					return;
				}
				const single = n > 0 ? whole / n : 0;
				const tw = flt(line.width_inch) * n;
				const bnet = flt(line.net_weight) * n;
				el.html(
					__('Single gross: {0} Kg · Total width: {1} in · Bundle net (sticker): {2} Kg', [
						single.toFixed(2),
						tw.toFixed(4),
						bnet.toFixed(2),
					])
				);
			}
			d.show();
			recalc();
			['roll_line', 'no_of_packaging', 'whole_gross_kg'].forEach(function (fn) {
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
		schedule_spr_item_row_styles(frm);
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
	const den = w * ln * 0.254;
	const val = den > 0 ? Math.round((wgt * 10000) / den * 100) / 100 : 0;
	frappe.model.set_value(cdt, cdn, 'produced_gsm', val);
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
		frappe.model.set_value(sj.doctype, sj.name, 'custom_total_achieved_weight', flt(v));
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
	if (hooked) {
		frm._spr_items_grid_patched = true;
	}
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

function sprEffectiveProducedGsm(doc) {
	const p = flt(doc.produced_gsm);
	if (p > 0) {
		return p;
	}
	const nw = flt(doc.net_weight);
	const gw = flt(doc.gross_weight);
	const wgt = nw > 0 ? nw : gw;
	if (wgt <= 0) {
		return 0;
	}
	const w = flt(doc.width_inch);
	let ln = flt(doc.meter_roll);
	if (doc.produced_length_mtrs !== undefined && doc.produced_length_mtrs !== null && doc.produced_length_mtrs !== '') {
		ln = flt(doc.produced_length_mtrs);
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
	const sprItemsCssVer = '7';
	if (window.__sprspr_items_css_ver === sprItemsCssVer) {
		return;
	}
	window.__sprspr_items_css_ver = sprItemsCssVer;
	window.__sprspr_style = true;
	$('head style[data-spr-items]').remove();
	/* |Sticker GSM − Produced GSM|: <1 green, 1–2 golden yellow, 2–3 orange, 3+ red; incomplete compare → neutral gray */
	const css = `
		.spr-items-wrap .grid-row.spr-gsm-band-0,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-0,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-0,
		.fieldname-items .grid-row.spr-gsm-band-0 { background-color: #bbf7d0 !important; }
		.spr-items-wrap .grid-row.spr-gsm-band-1,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-1,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-1,
		.fieldname-items .grid-row.spr-gsm-band-1 { background-color: #eab308 !important; }
		.spr-items-wrap .grid-row.spr-gsm-band-2,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-2,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-2,
		.fieldname-items .grid-row.spr-gsm-band-2 { background-color: #fb923c !important; }
		.spr-items-wrap .grid-row.spr-gsm-band-3,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-band-3,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-band-3,
		.fieldname-items .grid-row.spr-gsm-band-3 { background-color: #fecaca !important; }
		.spr-items-wrap .grid-row.spr-gsm-pending,
		.form-group[data-fieldname="items"] .grid-row.spr-gsm-pending,
		.frappe-control[data-fieldname="items"] .grid-row.spr-gsm-pending,
		.fieldname-items .grid-row.spr-gsm-pending { background-color: #f3f4f6 !important; }
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] .static-value,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] .row-index,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] .col,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] input,
		.spr-items-wrap .grid-row[class*="spr-gsm-band"] select,
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
	`;
	$('head').append(`<style data-spr-items="7">${css}</style>`);
}

/** Apply row_locked / row_ready_for_print to grid DOM (Print Label only after Save Row). */
function spr_apply_items_row_lock_ui(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) {
		return;
	}
	const items = frm.doc.items || [];
	items.forEach(function (doc, idx) {
		const $row = sprResolveItemsRowElement(frm, doc, grid, idx);
		if (!$row || !$row.length) {
			return;
		}
		const locked = cint(doc.row_locked);
		const labelReady = cint(doc.row_ready_for_print) && locked;
		$row.addClass('spr-spr-row');
		$row.toggleClass('spr-spr-row-locked', !!locked);
		$row.toggleClass('spr-spr-row-label-ready', !!labelReady);
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
	$el.find('td, .col, .static-value, .editable-row, .row-index').each(function () {
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
	$row.find('td, .col, .static-value, .editable-row, .row-index').each(function () {
		clear(this);
	});
}

function sprEnsureItemsGridObserver(frm) {
	if (frm._spr_items_mo) {
		return;
	}
	const $w = frm.fields_dict.items && frm.fields_dict.items.$wrapper;
	if (!$w || !$w.length) {
		return;
	}
	let timer = null;
	frm._spr_items_mo = new MutationObserver(function () {
		if (timer) {
			clearTimeout(timer);
		}
		timer = setTimeout(function () {
			apply_spr_item_row_styles(frm);
		}, 80);
	});
	frm._spr_items_mo.observe($w[0], { childList: true, subtree: true });
}

function schedule_spr_item_row_styles(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	if (frm.fields_dict.items.$wrapper && frm.fields_dict.items.$wrapper.length) {
		frm.fields_dict.items.$wrapper.addClass('spr-items-wrap');
	}
	sprEnsureItemsGridObserver(frm);
	ensure_spr_item_stylesheet();
	[0, 50, 150, 400, 900].forEach(function (ms) {
		setTimeout(function () {
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
	return $row;
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

	items.forEach(function (doc, idx) {
		let $row = sprResolveItemsRowElement(frm, doc, grid, idx);
		if (!$row || !$row.length) {
			return;
		}
		const sticker = sprStickerGsmFromDoc(doc);
		const effProd = sprEffectiveProducedGsm(doc);
		const rowLocked = cint(doc.row_locked);
		$row.removeClass(baseClasses);
		sprClearRowBg($row);
		const hasGsmCompare = sticker > 0 && effProd > 0;
		if (hasGsmCompare) {
			const diff = Math.abs(effProd - sticker);
			let band = 3;
			if (diff < 1) {
				band = 0;
			} else if (diff < 2) {
				band = 1;
			} else if (diff < 3) {
				band = 2;
			}
			$row.addClass(bandClasses[band]);
			sprApplyGsmRowVisual($row, band);
		} else if (rowLocked) {
			$row.addClass('spr-gsm-band-0');
			sprApplyGsmRowVisual($row, 0);
		} else {
			$row.addClass('spr-gsm-pending');
			sprApplyGsmRowVisual($row, 'pending');
		}
	});
	spr_apply_items_row_lock_ui(frm);
}
