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
			freeze_message: __('Loading jobs from Work Orders...'),
			callback: function (r) {
				frm.clear_table('shaft_jobs');
				(r.message || []).forEach(function (row) {
					let c = frm.add_child('shaft_jobs');
					c.job_id = row.job_id;
					c.total_weight = row.total_weight;
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
							[
								'work_order',
								'item_code',
								'item_name',
								'quality',
								'gsm',
								'planned_qty',
								'job',
								'batch_no',
								'party_code',
								'roll_no',
								'meter_roll',
								'net_weight',
								'gross_weight',
								'width_inch',
								'color',
							].forEach(function (k) {
								if (row[k] !== undefined && row[k] !== null) {
									it[k] = row[k];
								}
							});
						});
						frm.refresh_field('items');
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
	},
});

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
