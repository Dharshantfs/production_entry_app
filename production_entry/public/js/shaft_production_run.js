frappe.ui.form.on('Shaft Production Run', {
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
		schedule_spr_item_row_styles(frm);
	},

	items: {
		items_add: function (frm) {
			schedule_spr_item_row_styles(frm);
		},
		items_remove: function (frm) {
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
				(frm.doc.items || []).forEach(function (row) {
					spr_update_produced_gsm(frm, 'Shaft Production Run Item', row.name);
				});
				schedule_spr_item_row_styles(frm);
				frappe.show_alert({
					message: __('Added {0} roll line(s) for job {1}.', [lines.length, job_id]),
					indicator: 'green',
				});
			},
		});
	},
});

frappe.ui.form.on('Shaft Production Run Item', {
	net_weight: function (frm, cdt, cdn) {
		spr_update_produced_gsm(frm, cdt, cdn);
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

function ensure_spr_item_stylesheet() {
	if (window.__sprspr_style) {
		return;
	}
	window.__sprspr_style = true;
	const css = `
		.grid-body .grid-row.spr-prod { background-color: #ecfdf5 !important; }
		.grid-body .grid-row.spr-open { background-color: #f9fafb !important; }
		.grid-body .grid-row.spr-gsm-a { box-shadow: inset 4px 0 0 #6366f1; }
		.grid-body .grid-row.spr-gsm-b { box-shadow: inset 4px 0 0 #f97316; }
		.grid-body .grid-row.spr-gsm-c { box-shadow: inset 4px 0 0 #22c55e; }
		.grid-body .grid-row.spr-gsm-d { box-shadow: inset 4px 0 0 #a855f7; }
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
	grid.grid_rows.forEach(function (grow) {
		const $row = grow.row;
		if (!$row || !$row.length) {
			return;
		}
		const doc = grow.doc;
		if (!doc) {
			return;
		}
		const net = flt(doc.net_weight);
		const gross = flt(doc.gross_weight);
		const produced = net > 0 || gross > 0;
		const gsm = cint(doc.gsm);
		$row.removeClass('spr-prod spr-open spr-gsm-a spr-gsm-b spr-gsm-c spr-gsm-d');
		if (produced) {
			$row.addClass('spr-prod');
		} else {
			$row.addClass('spr-open');
		}
		const band = Math.floor((gsm || 0) / 30) % 4;
		const bandClass = ['spr-gsm-a', 'spr-gsm-b', 'spr-gsm-c', 'spr-gsm-d'][band];
		if (bandClass) {
			$row.addClass(bandClass);
		}
	});
}
