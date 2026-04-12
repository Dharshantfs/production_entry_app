// Custom Script for Shaft Production Run form
frappe.ui.form.on('Shaft Production Run', {
    onload: function(frm) {
        // Check if we navigated here from Production Table (flag set before routing)
        if (frappe.flags.spr_show_wo_popup && frm.doc.production_plan) {
            const ppId = frappe.flags.spr_show_wo_popup;
            frappe.flags.spr_show_wo_popup = null; // clear immediately
            setTimeout(() => {
                show_linked_work_orders(ppId);
            }, 1200);
        }
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

    refresh: function(frm) {
        enforce_total_weight_precision(frm);

        // Auto-fill production_plan if it's new and not already set
        if (frm.is_new() && !frm.doc.production_plan) {
            const urlParams = new URLSearchParams(window.location.search);
            const pp_id = urlParams.get('pp_id') || frappe.session_context?.production_plan;
            if (pp_id) {
                frm.set_value('production_plan', pp_id);
            }
        }

        // If PP already exists on a new form, ensure Available Jobs are pulled from PP shaft details.
        if (frm.doc.production_plan) {
            const hasPlaceholderRows = has_only_placeholder_rows(frm);
            load_available_jobs_from_pp(frm, { force: frm.is_new() || hasPlaceholderRows });
        }

        // For saved (non-new) reopened forms, show WO popup with delay
        if (frm.doc.production_plan && !frm.is_new()) {
            setTimeout(() => {
                show_linked_work_orders(frm.doc.production_plan);
            }, 1500);
        }
        frappe.route_options = null;
    },

    production_plan: function(frm) {
        if (frm.doc.production_plan) {
            load_available_jobs_from_pp(frm, { force: true });
            show_linked_work_orders(frm.doc.production_plan);
        } else if (frm.doc.shaft_jobs && frm.doc.shaft_jobs.length) {
            frm.clear_table('shaft_jobs');
            frm.refresh_field('shaft_jobs');
        }
    }
});

function should_skip_auto_fill(frm, force) {
    if (!frm.doc.production_plan) {
        return true;
    }

    if (frm.__spr_jobs_loading) {
        return true;
    }

    // Do not overwrite existing rows unless explicitly forced.
    if (!force && frm.doc.shaft_jobs && frm.doc.shaft_jobs.length > 0) {
        return true;
    }

    return false;
}

function has_only_placeholder_rows(frm) {
    const rows = frm.doc.shaft_jobs || [];
    if (!rows.length) {
        return true;
    }

    return rows.every((row) => {
        const netWeight = row.net_weight_shaft_kgs || row.net_weight_shaft || row.net_weight || '';
        const totalWeight = flt(row.total_weight_kgs || row.total_weight || 0);
        const workOrders = row.work_orders || row.work_order || '';
        const combination = row.combination || row.shaft || '';
        return !netWeight && totalWeight === 0 && !workOrders && !combination;
    });
}

function set_row_value(row, candidates, value) {
    for (const key of candidates) {
        if (Object.prototype.hasOwnProperty.call(row, key)) {
            row[key] = value;
            return;
        }
    }

    // Fallback: assign first candidate even if key is not pre-seeded on row object.
    if (candidates.length) {
        row[candidates[0]] = value;
    }
}

function enforce_total_weight_precision(frm) {
    if (!frm || !frm.fields_dict || !frm.fields_dict.shaft_jobs || !frm.fields_dict.shaft_jobs.grid) {
        return;
    }

    const grid = frm.fields_dict.shaft_jobs.grid;
    ["total_weight", "total_weight_kgs", "custom_total_weight_kgs"].forEach((fieldname) => {
        try {
            grid.update_docfield_property(fieldname, "precision", 2);
        } catch (e) {
            // Ignore if this field does not exist in current site schema.
        }
    });
}

function load_available_jobs_from_pp(frm, opts = {}) {
    const force = !!opts.force;
    if (should_skip_auto_fill(frm, force)) {
        return;
    }

    frm.__spr_jobs_loading = true;

    frappe.call({
        method: 'production_scheduler.api.get_spr_shaft_jobs_from_pp',
        args: {
            pp_id: frm.doc.production_plan
        },
        freeze: false,
        callback: function(r) {
            frm.__spr_jobs_loading = false;
            const payload = r.message || {};

            if (payload.status !== 'ok') {
                if (payload.message) {
                    frappe.show_alert({
                        indicator: 'orange',
                        message: payload.message
                    }, 5);
                }
                return;
            }

            const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
            if (!jobs.length) {
                return;
            }

            frm.clear_table('shaft_jobs');

            jobs.forEach((job, idx) => {
                const row = frm.add_child('shaft_jobs');
                set_row_value(row, ['job_id', 'job', 'job_no'], job.job_id || String(idx + 1));
                set_row_value(row, ['gsm'], job.gsm || '');
                set_row_value(row, ['combination', 'shaft', 'shaft_details'], job.combination || '');
                set_row_value(row, ['total_width', 'width', 'total_width_inches'], flt(job.total_width || 0));
                set_row_value(row, ['meter_roll_mtrs', 'roll_mtrs', 'meter_roll', 'roll'], flt(job.meter_roll_mtrs || 0));
                set_row_value(row, ['no_of_shafts', 'no_of_sh', 'no_of_sf'], cint(job.no_of_shafts || 0));
                set_row_value(row, ['net_weight_shaft_kgs', 'net_weight_shaft', 'net_weight'], job.net_weight_shaft_kgs || '');
                set_row_value(row, ['total_weight_kgs', 'total_weight', 'weight'], flt(job.total_weight_kgs || 0, 2));
                set_row_value(row, ['order_code', 'party_code', 'custom_order_code'], job.order_code || '');
                set_row_value(row, ['work_orders', 'work_order', 'wo_no'], job.work_orders || '');
            });

            (frm.doc.shaft_jobs || []).forEach((row) => {
                if (row.total_weight !== undefined) row.total_weight = flt(row.total_weight || 0, 2);
                if (row.total_weight_kgs !== undefined) row.total_weight_kgs = flt(row.total_weight_kgs || 0, 2);
                if (row.custom_total_weight_kgs !== undefined) row.custom_total_weight_kgs = flt(row.custom_total_weight_kgs || 0, 2);
            });

            frm.refresh_field('shaft_jobs');
            frm.__spr_jobs_loaded_pp = frm.doc.production_plan;

            frappe.show_alert({
                indicator: 'green',
                message: `Fetched ${jobs.length} jobs from Production Plan.`
            }, 4);

            // Log debug data to browser console to discover actual PP field names
            if (payload._debug) {
                console.log('=== PP SHAFT DEBUG DATA ===', JSON.stringify(payload._debug, null, 2));
            }

            // Show WO popup after jobs are loaded (reliable timing)
            if (frm.doc.production_plan) {
                setTimeout(() => {
                    show_linked_work_orders(frm.doc.production_plan);
                }, 500);
            }

            if (!frm.doc.customer && payload.customer) {
                frm.set_value('customer', payload.customer);
            }

            if (!frm.doc.custom_order_code && payload.order_code) {
                frm.set_value('custom_order_code', payload.order_code);
            }
        },
        error: function() {
            frm.__spr_jobs_loading = false;
        }
    });
}

function show_linked_work_orders(pp_id) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Work Order',
            filters: {
                'production_plan': pp_id,
                'docstatus': ['<', 2]  // Draft or Submitted (not Cancelled)
            },
            fields: [
                'name',
                'production_item',
                'qty',
                'produced_qty',
                'status',
                'docstatus'
            ],
            order_by: 'creation asc'
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                show_wo_status_popup(r.message, pp_id);
            }
        }
    });
}

function show_wo_status_popup(work_orders, pp_id) {
    // Build HTML table for WO list
    let table_html = `
        <table class="table table-striped table-sm">
            <thead>
                <tr style="background-color: #f5f5f5;">
                    <th>WO #</th>
                    <th>Item</th>
                    <th>Status</th>
                    <th>Target Qty</th>
                    <th>Produced Qty</th>
                    <th>Pending Qty</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    let total_target = 0;
    let total_produced = 0;
    let total_pending = 0;
    
    work_orders.forEach(wo => {
        const target_qty = flt(wo.qty);
        const produced_qty = flt(wo.produced_qty);
        const pending_qty = target_qty - produced_qty;
        
        total_target += target_qty;
        total_produced += produced_qty;
        total_pending += pending_qty;
        
        const status_badge = get_wo_status_badge(wo.status);
        
        table_html += `
            <tr>
                <td><strong>${wo.name}</strong></td>
                <td>${wo.production_item || '-'}</td>
                <td>${status_badge}</td>
                <td class="text-right">${format_number(target_qty, 2)}</td>
                <td class="text-right">${format_number(produced_qty, 2)}</td>
                <td class="text-right"><strong>${format_number(pending_qty, 2)}</strong></td>
            </tr>
        `;
    });
    
    table_html += `
            </tbody>
            <tfoot>
                <tr style="background-color: #f0f0f0; font-weight: bold;">
                    <td colspan="3">TOTAL</td>
                    <td class="text-right">${format_number(total_target, 2)}</td>
                    <td class="text-right">${format_number(total_produced, 2)}</td>
                    <td class="text-right">${format_number(total_pending, 2)}</td>
                </tr>
            </tfoot>
        </table>
    `;
    
    // Show dialog
    let d = new frappe.ui.Dialog({
        title: `📋 Work Orders for PP: ${pp_id}`,
        width: 900,
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'wo_list',
                options: table_html
            }
        ],
        primary_action_label: 'Close',
        primary_action(dialog) {
            dialog.hide();
        }
    });
    
    d.show();
}

function get_wo_status_badge(status) {
    const status_map = {
        'Not Started': '<span class="badge badge-secondary">Not Started</span>',
        'In Progress': '<span class="badge badge-primary">In Progress</span>',
        'Completed': '<span class="badge badge-success">Completed</span>',
        'Cancelled': '<span class="badge badge-danger">Cancelled</span>'
    };
    return status_map[status] || `<span class="badge badge-light">${status}</span>`;
}

function format_number(num, decimals) {
    return (flt(num) || 0).toFixed(decimals);
}

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
        const devPct = (Math.abs(act - pq) / pq) * 100;
        if (devPct > tol + 1e-9) {
            out.push({
                job: row.job,
                roll_no: row.roll_no,
                planned: pq,
                actual: act,
                dev_pct: devPct,
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
                flt(v.planned).toFixed(3) +
                '</td><td class="text-right">' +
                flt(v.actual).toFixed(3) +
                '</td><td class="text-right">' +
                flt(v.dev_pct).toFixed(2) +
                '%</td></tr>'
            );
        })
        .join('');
    const html =
        '<p class="text-muted">' +
        __(forSubmit
            ? 'Allowed deviation: ±{0}%. Enter a reason and confirm approval to submit, or adjust roll weights.'
            : 'Allowed deviation: ±{0}%. Enter a reason and confirm approval to save, or adjust roll weights.', [tol]) +
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
