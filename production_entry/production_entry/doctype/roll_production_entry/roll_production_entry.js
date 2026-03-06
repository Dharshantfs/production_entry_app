frappe.ui.form.on('Roll Production Entry', {
    refresh: function (frm) {
        render_job_sections(frm);
    },

    onload: function (frm) {
        render_job_sections(frm);
    },

    validate: function (frm) {
        // Ensure manual net weight is not zero for any row
        frm.doc.items.forEach(row => {
            if (!row.net_weight || row.net_weight <= 0) {
                // We warn but don't block if they just want to save draft
            }
        });
    }
});

frappe.ui.form.on('Roll Production Entry Item', {
    meter_per_roll: function (frm, cdt, cdn) {
        render_job_sections(frm);
    },
    gsm: function (frm, cdt, cdn) {
        render_job_sections(frm);
    },
    width_inches: function (frm, cdt, cdn) {
        render_job_sections(frm);
    },
    net_weight: function (frm, cdt, cdn) {
        render_job_sections(frm);
    },
    gross_weight: function (frm, cdt, cdn) {
        render_job_sections(frm);
    }
});

function render_job_sections(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        // Remove headers if grid is empty
        let grid_wrapper = frm.fields_dict['items'].grid.wrapper;
        grid_wrapper.find('.job-section-header').remove();
        return;
    }

    // Group items by job_no
    let jobs = {};
    let total_rolls = 0;
    let total_net = 0;
    let total_gross = 0;
    let total_planned = 0;

    frm.doc.items.forEach(function (row) {
        let job = row.job_no || 'Unknown';
        if (!jobs[job]) {
            jobs[job] = {
                shaft_combination: row.shaft_combination || '',
                planned_qty: flt(row.planned_qty) || 0,
                rows: []
            };
            total_planned += flt(row.planned_qty);
        }
        jobs[job].rows.push(row);
        total_rolls++;
        total_net += flt(row.net_weight);
        total_gross += flt(row.gross_weight);
    });

    // Inject visual job headers and totals above the grid
    let grid_wrapper = frm.fields_dict['items'].grid.wrapper;

    // Remove old job headers if any
    grid_wrapper.find('.job-section-header').remove();

    // Show summary and totals
    let summary_html = '<div class="job-section-header" style="margin-bottom:20px; font-family: \'Inter\', sans-serif;">';

    // ── PREMIUM TOTALS BAR (Matching preview aesthetic) ──
    summary_html += `
        <div style="display:flex; gap:24px; margin-bottom:20px; padding:16px 24px; background:#ffffff; 
                    border-radius:10px; border:1px solid #dde1e7; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="flex:1;">
                <div style="font-size:11px; font-weight:600; color:#6b7280; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:4px;">Total Rolls</div>
                <div style="font-size:18px; font-weight:700; color:#2c5eff;">${total_rolls}</div>
            </div>
            <div style="flex:1; border-left:1px solid #f0f0f0; padding-left:24px;">
                <div style="font-size:11px; font-weight:600; color:#6b7280; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:4px;">Total Net (kg)</div>
                <div style="font-size:18px; font-weight:700; color:#16a34a;">${total_net.toFixed(2)}</div>
            </div>
            <div style="flex:1; border-left:1px solid #f0f0f0; padding-left:24px;">
                <div style="font-size:11px; font-weight:600; color:#6b7280; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:4px;">Total Gross (kg)</div>
                <div style="font-size:18px; font-weight:700; color:#1a1d23;">${total_gross.toFixed(2)}</div>
            </div>
            <div style="flex:1; border-left:1px solid #f0f0f0; padding-left:24px;">
                <div style="font-size:11px; font-weight:600; color:#6b7280; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:4px;">Total Planned</div>
                <div style="font-size:18px; font-weight:700; color:#6b7280;">${total_planned.toFixed(2)} kg</div>
            </div>
        </div>
    `;

    // ── JOB SECTIONS ──
    const job_colors = {
        '1': '#2c5eff', '2': '#7c3aed', '3': '#0891b2',
        '4': '#be185d', '5': '#065f46'
    };
    const job_bgs = {
        '1': '#eef2ff', '2': '#f5f3ff', '3': '#ecfeff',
        '4': '#fdf2f8', '5': '#ecfdf5'
    };

    Object.keys(jobs).sort().forEach(function (job_no, idx) {
        let job = jobs[job_no];
        let color = job_colors[job_no] || job_colors[(idx % 5) + 1];
        let bg = job_bgs[job_no] || job_bgs[(idx % 5) + 1];

        summary_html += `
            <div style="background:${bg}; border-left:4px solid ${color};
                        padding:12px 20px; margin-bottom:8px; border-radius:8px;
                        display:flex; align-items:center; gap:16px;">
                
                <div style="width:30px; height:30px; background:${color}; color:#fff; 
                            border-radius:6px; display:flex; align-items:center; justify-content:center;
                            font-weight:700; font-family:monospace; font-size:14px;">
                    J${job_no}
                </div>

                <div style="flex:1;">
                    <div style="font-weight:700; font-size:13px; color:#1a1d23;">Job: ${job_no}</div>
                    <div style="font-size:12px; color:#6b7280;">
                        Shaft: <strong style="color:#222;">${job.shaft_combination}</strong>
                        &nbsp;&nbsp;·&nbsp;&nbsp;
                        Entries: <strong style="color:#222;">${job.rows.length}</strong>
                    </div>
                </div>

                <div style="background:#fff; border:1px solid #dde1e7; padding:4px 12px; border-radius:12px; font-size:11px; font-weight:600;">
                    Planned: ${job.planned_qty || 0} kg
                </div>
            </div>`;
    });
    summary_html += '</div>';

    grid_wrapper.before(summary_html);
}
