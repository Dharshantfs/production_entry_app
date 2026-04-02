frappe.ui.form.on('Roll Production Entry', {
	refresh: function (frm) {
		render_job_sections(frm);

		// Recalculate net weight when meter/roll changes
		frm.fields_dict['items'].grid.wrapper.on('change', 'input[data-fieldname="meter_per_roll"]', function () {
			recalculate_weights(frm);
		});
	},

	onload: function (frm) {
		render_job_sections(frm);
	},
});

frappe.ui.form.on('Roll Production Entry Item', {
	meter_per_roll: function (frm, cdt, cdn) {
		calculate_row_weight(frm, cdt, cdn);
	},
	gsm: function (frm, cdt, cdn) {
		calculate_row_weight(frm, cdt, cdn);
	},
	width_inches: function (frm, cdt, cdn) {
		calculate_row_weight(frm, cdt, cdn);
	},
});

function calculate_row_weight(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (row.gsm && row.width_inches && row.meter_per_roll) {
		// Net weight (kg) = GSM × width(m) × length(m) / 1000
		let width_m = flt(row.width_inches) * 0.0254;
		let net_weight = flt(row.gsm) * width_m * flt(row.meter_per_roll) / 1000;
		frappe.model.set_value(cdt, cdn, 'net_weight', Math.round(net_weight * 1000) / 1000);
	}
}

function render_job_sections(frm) {
	if (!frm.doc.items || frm.doc.items.length === 0) return;

	// Group items by job_no
	let jobs = {};
	frm.doc.items.forEach(function (row) {
		let job = row.job_no || 'Unknown';
		if (!jobs[job]) {
			jobs[job] = {
				shaft_combination: row.shaft_combination || '',
				planned_qty: row.planned_qty || 0,
				rows: [],
			};
		}
		jobs[job].rows.push(row);
	});

	// Inject visual job headers above the grid
	let grid_wrapper = frm.fields_dict['items'].grid.wrapper;

	// Remove old job headers if any
	grid_wrapper.find('.job-section-header').remove();

	// Show job summary above grid
	let summary_html = '<div class="job-section-header" style="margin-bottom:10px;">';
	Object.keys(jobs).forEach(function (job_no) {
		let job = jobs[job_no];
		summary_html += `
            <div style="background:#f0f4ff;border-left:4px solid #5e64ff;
                        padding:8px 12px;margin-bottom:6px;border-radius:4px;">
                <strong>📋 Job ${job_no}</strong>
                &nbsp;|&nbsp; Shaft: <b>${job.shaft_combination}</b>
                &nbsp;|&nbsp; Planned Qty: <b>${job.planned_qty} kg</b>
                &nbsp;|&nbsp; Rolls: <b>${job.rows.length}</b>
            </div>`;
	});
	summary_html += '</div>';

	grid_wrapper.before(summary_html);
}

function recalculate_weights(frm) {
	frm.doc.items.forEach(function (row) {
		if (row.gsm && row.width_inches && row.meter_per_roll) {
			let width_m = flt(row.width_inches) * 0.0254;
			let net_weight = flt(row.gsm) * width_m * flt(row.meter_per_roll) / 1000;
			frappe.model.set_value(
				row.doctype,
				row.name,
				'net_weight',
				Math.round(net_weight * 1000) / 1000
			);
		}
	});
}
