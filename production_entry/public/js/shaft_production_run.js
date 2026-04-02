frappe.ui.form.on('Shaft Production Run', {
	production_plan: function (frm) {
		if (!frm.doc.production_plan) {
			frm.clear_table('shaft_jobs');
			frm.clear_table('items');
			frm.refresh_field('shaft_jobs');
			frm.refresh_field('items');
			return;
		}

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

				frappe.call({
					method:
						'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_item_rows_for_production_plan',
					args: { production_plan: frm.doc.production_plan },
					freeze: true,
					freeze_message: __('Loading roll lines from Work Orders...'),
					callback: function (r2) {
						frm.clear_table('items');
						(r2.message || []).forEach(function (row) {
							let it = frm.add_child('items');
							Object.keys(row).forEach(function (k) {
								if (row[k] !== undefined && row[k] !== null) {
									it[k] = row[k];
								}
							});
						});
						frm.refresh_field('items');
						schedule_spr_item_row_styles(frm);
					},
				});
			},
		});
	},

	refresh: function (frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Create Roll Production Entry'), function () {
				create_roll_production_entry(frm);
			}).addClass('btn-primary');
		}
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

frappe.ui.form.on('Shaft Production Run Item', {
	net_weight: function (frm) {
		schedule_spr_item_row_styles(frm);
	},
	gross_weight: function (frm) {
		schedule_spr_item_row_styles(frm);
	},
	gsm: function (frm) {
		schedule_spr_item_row_styles(frm);
	},
});

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

function create_roll_production_entry(frm) {
	frappe.call({
		method:
			'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.get_or_create_roll_entry',
		args: {
			shaft_production_run: frm.doc.name,
		},
		freeze: true,
		freeze_message: __('Fetching all job details...'),
		callback: function (r) {
			if (r.message) {
				if (r.message.existing) {
					frappe.set_route('Form', 'Roll Production Entry', r.message.existing);
				} else {
					let data = r.message;
					frappe.new_doc('Roll Production Entry', {
						shaft_production_run: frm.doc.name,
						production_plan: data.production_plan,
						items: data.items,
					});
				}
			}
		},
	});
}
