frappe.ui.form.on('Shaft Production Run', {
	setup: function (frm) {
		frm.add_custom_button(
			__('Manual job'),
			function () {
				frm.scroll_to_field('shaft_jobs');
			},
			__('Actions')
		);
		frm.add_custom_button(
			__('Bundle packaging'),
			function () {
				frm.scroll_to_field('bundle_stickers');
			},
			__('Actions')
		);
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
		update_shaft_job_achieved_from_items(frm);
		schedule_spr_item_row_styles(frm);
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
		schedule_spr_item_row_styles(frm);
	},
	gross_weight: function (frm) {
		schedule_spr_item_row_styles(frm);
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
	produced_gsm: function (frm) {
		schedule_spr_item_row_styles(frm);
	},
});

function spr_update_produced_gsm(frm, cdt, cdn) {
	if (!frappe.meta.get_docfield('Shaft Production Run Item', 'produced_gsm')) {
		return;
	}
	const row = locals[cdt][cdn];
	const nw = flt(row.net_weight);
	const w = flt(row.width_inch);
	const ln = flt(row.meter_roll);
	const den = w * ln * 0.254;
	const val = den > 0 ? Math.round((nw * 10000) / den * 100) / 100 : 0;
	frappe.model.set_value(cdt, cdn, 'produced_gsm', val);
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

function update_shaft_job_achieved_from_items(frm) {
	if (!frappe.meta.get_docfield('Shaft Production Run Job', 'custom_total_achieved_weight')) {
		return;
	}
	const sums = {};
	(frm.doc.items || []).forEach(function (it) {
		if (it.job === undefined || it.job === null || it.job === '') {
			return;
		}
		const k = String(it.job);
		sums[k] = (sums[k] || 0) + flt(it.net_weight);
	});
	(frm.doc.shaft_jobs || []).forEach(function (sj) {
		const jid = String(sj.job_id);
		const v = sums[jid] !== undefined ? sums[jid] : 0;
		frappe.model.set_value(sj.doctype, sj.name, 'custom_total_achieved_weight', v);
	});
}

function ensure_spr_item_stylesheet() {
	if (window.__sprspr_style) {
		return;
	}
	window.__sprspr_style = true;
	const css = `
		.grid-body .grid-row.spr-gsm-diff-0 { background-color: #bbf7d0 !important; }
		.grid-body .grid-row.spr-gsm-diff-0 .static-value,
		.grid-body .grid-row.spr-gsm-diff-0 .row-index { color: #000 !important; }
		.grid-body .grid-row.spr-gsm-diff-1 { background-color: #fdba74 !important; }
		.grid-body .grid-row.spr-gsm-diff-1 .static-value,
		.grid-body .grid-row.spr-gsm-diff-1 .row-index { color: #000 !important; }
		.grid-body .grid-row.spr-gsm-diff-2 { background-color: #fbbf24 !important; }
		.grid-body .grid-row.spr-gsm-diff-2 .static-value,
		.grid-body .grid-row.spr-gsm-diff-2 .row-index,
		.grid-body .grid-row.spr-gsm-diff-2 input { color: #000 !important; }
		.grid-body .grid-row.spr-gsm-diff-3 { background-color: #fecaca !important; }
		.grid-body .grid-row.spr-gsm-diff-3 .static-value,
		.grid-body .grid-row.spr-gsm-diff-3 .row-index { color: #000 !important; }
		.grid-body .grid-row.spr-prod { background-color: #ecfdf5 !important; }
		.grid-body .grid-row.spr-open { background-color: #f9fafb !important; }
	`;
	$('head').append(`<style data-spr-items="1">${css}</style>`);
}

function schedule_spr_item_row_styles(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
		return;
	}
	ensure_spr_item_stylesheet();
	setTimeout(function () {
		apply_spr_item_row_styles(frm);
	}, 200);
}

function apply_spr_item_row_styles(frm) {
	const grid = frm.fields_dict.items.grid;
	if (!grid || !grid.grid_rows) {
		return;
	}
	const diffClasses = ['spr-gsm-diff-0', 'spr-gsm-diff-1', 'spr-gsm-diff-2', 'spr-gsm-diff-3'];
	grid.grid_rows.forEach(function (grow) {
		const $row = grow.row;
		if (!$row || !$row.length) {
			return;
		}
		const doc = grow.doc;
		if (!doc) {
			return;
		}
		const sticker = flt(doc.gsm);
		const prod = flt(doc.produced_gsm);
		const net = flt(doc.net_weight);
		const gross = flt(doc.gross_weight);
		const produced = net > 0 || gross > 0;
		$row.removeClass(
			'spr-prod spr-open spr-gsm-diff-0 spr-gsm-diff-1 spr-gsm-diff-2 spr-gsm-diff-3'
		);
		const hasGsmCompare = sticker > 0 && (prod > 0 || net > 0);
		if (hasGsmCompare) {
			const diff = Math.abs(prod - sticker);
			let band = 3;
			if (diff < 1) {
				band = 0;
			} else if (diff < 2) {
				band = 1;
			} else if (diff < 3) {
				band = 2;
			}
			$row.addClass(diffClasses[band]);
			return;
		}
		if (produced) {
			$row.addClass('spr-prod');
		} else {
			$row.addClass('spr-open');
		}
	});
}
