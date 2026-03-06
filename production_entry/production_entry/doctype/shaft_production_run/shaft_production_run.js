frappe.ui.form.on('Shaft Production Run', {
    refresh: function (frm) {
        frm.get_field('shaft_jobs').grid.cannot_add_rows = true;

        if (!frm.is_new() && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Generate Batches'), function () {
                set_shift_production(frm);
                frappe.msgprint("Shift and Batch Sequence calculated. Please verify Roll Numbers.");
            }).addClass('btn-primary');
        }

        if (frm.doc.production_plan && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Re-select Work Orders'), function () {
                select_work_orders(frm);
            });
        }

        setTimeout(function () {
            if (frm.fields_dict['items'] && frm.fields_dict['items'].grid) {
                let grid = frm.fields_dict['items'].grid;
                grid.get_field('print_sticker').formatter = function (value, row_doc) {
                    return `<button type="button" class="btn btn-xs btn-default" 
                        style="width: 100%; font-weight: bold; cursor: pointer !important; pointer-events: auto;" 
                        onclick="frappe.generate_sticker_flow('${row_doc.name}')">
                        🖨️ Print Label
                    </button>`;
                };
                grid.refresh();
            }
        }, 500);
    },

    onload: function (frm) {
        if (frm.is_new()) {
            set_shift_production(frm);
        }
    },

    production_plan: function (frm) {
        if (frm.doc.production_plan) {
            select_work_orders(frm);
        } else {
            frm.clear_table('shaft_jobs');
            frm.clear_table('items');
            frm.refresh_field('shaft_jobs');
            frm.refresh_field('items');
        }
    },

    fetch_shaft_details: function (frm) {
        frappe.call({
            method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
            args: {
                production_plan: frm.doc.production_plan
            },
            callback: function (r) {
                if (r.message) {
                    frm.clear_table('shaft_jobs');
                    // We intentionally don't clear 'items' in case they've already started entering rolls

                    if (r.message.length > 0) {
                        r.message.forEach(d => {
                            let job_row = frm.add_child('shaft_jobs');
                            job_row.job_id = d.job_id;
                            job_row.combination = d.combination;
                            job_row.total_width = d.total_width;
                            job_row.meter_roll_mtrs = d.meter_roll_mtrs;
                            job_row.no_of_shafts = d.no_of_shafts;
                            job_row.gsm = d.gsm;
                        });

                        frm.refresh_field('shaft_jobs');
                        frappe.msgprint(`Fetched ${r.message.length} jobs from Production Plan.`);
                    }
                }
            }
        });
    }
});

frappe.ui.form.on('Shaft Production Run Job', {
    create_roll_entry: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        frappe.call({
            method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_job_roll_details',
            args: {
                production_plan: frm.doc.production_plan,
                job_id: row.job_id,
                combination: row.combination,
                no_of_shafts: row.no_of_shafts,
                gsm: row.gsm,
                meter_roll: row.meter_roll_mtrs,
                work_orders: frm.custom_selected_wos
            },
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    open_roll_entry_dialog(frm, row, r.message);
                } else {
                    frappe.msgprint("Could not find matching Work Orders for this Job's widths. Ensure WOs are created and not closed/cancelled.");
                }
            }
        });
    }
});


frappe.ui.form.on('Shaft Production Run Item', {
    net_weight: function (frm, cdt, cdn) {
        calculate_total(frm);
    },

    items_remove: function (frm) {
        calculate_total(frm);
    },

    items_add: function (frm, cdt, cdn) {
        if (frm.doc.docstatus === 0) {
            let max_roll = 0;
            (frm.doc.items || []).forEach(row => {
                let r = parseInt(row.roll_no) || 0;
                if (r > max_roll) max_roll = r;
            });
            frappe.model.set_value(cdt, cdn, 'roll_no', max_roll + 1);
        }
    }
});

// ==========================================
// Logics
// ==========================================

function calculate_total(frm) {
    let total = 0.0;
    (frm.doc.items || []).forEach(row => {
        total += flt(row.net_weight);
    });
    frm.set_value('total_produced_weight', total);
}

function select_work_orders(frm) {
    new frappe.ui.form.MultiSelectDialog({
        doctype: "Work Order",
        target: frm,
        setters: {
            status: "Not Started",
        },
        add_filters_group: 1,
        get_query() {
            return {
                filters: {
                    production_plan: frm.doc.production_plan,
                    docstatus: 1,
                    status: ["not in", ["Completed", "Closed", "Cancelled"]]
                }
            };
        },
        action(selections) {
            if (selections.length > 0) {
                fetch_jobs_for_wos(frm, selections);
            }
        }
    });
}

function fetch_jobs_for_wos(frm, work_orders) {
    frm.custom_selected_wos = work_orders;
    frappe.call({
        method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
        args: {
            production_plan: frm.doc.production_plan,
            work_orders: work_orders
        },
        callback: function (r) {
            if (r.message) {
                frm.clear_table('shaft_jobs');
                if (r.message.length > 0) {
                    r.message.forEach(d => {
                        let job_row = frm.add_child('shaft_jobs');
                        job_row.job_id = d.job_id;
                        job_row.gsm = d.gsm;
                        job_row.combination = d.combination;
                        job_row.total_width = d.total_width;
                        job_row.meter_roll_mtrs = d.meter_roll_mtrs;
                        job_row.no_of_shafts = d.no_of_shafts;
                    });
                    frm.refresh_field('shaft_jobs');
                } else {
                    frappe.msgprint("No matching Shaft Jobs found in Production Plan for the selected Work Orders.");
                }
            }
        }
    });
}


function open_roll_entry_dialog(frm, job_row, expected_rolls) {
    let d = new frappe.ui.Dialog({
        title: 'Enter Rolls for Job ' + job_row.job_id,
        size: 'extra-large',
        fields: [
            {
                fieldname: 'roll_entries',
                fieldtype: 'Table',
                label: 'Physical Rolls for this Job',
                options: 'Shaft Production Run Item',
                cannot_add_rows: true,
                cannot_delete_rows: true,
                in_place_edit: true
            }
        ],
        primary_action_label: 'Append Rolls to Main Table',
        primary_action(values) {
            let rolls = values.roll_entries || [];

            let entered_weight = 0.0;
            rolls.forEach(r => entered_weight += flt(r.net_weight));

            if (entered_weight <= 0) {
                frappe.msgprint({ title: 'Validation Error', indicator: 'red', message: "Total entered Net Weight must be greater than 0" });
                return;
            }

            frappe.confirm(`Adding ${rolls.length} rolls with a total Net Weight of ${entered_weight.toFixed(2)} kg. Proceed?`, () => {
                rolls.forEach(r => {
                    let new_row = frm.add_child('items');
                    Object.assign(new_row, r);
                    new_row.name = undefined;
                });

                let max_roll = 0;
                (frm.doc.items || []).forEach(row => {
                    let r_no = parseInt(row.roll_no) || 0;
                    if (r_no > max_roll) max_roll = r_no;
                });

                (frm.doc.items || []).forEach(row => {
                    if (!row.roll_no) {
                        max_roll++;
                        row.roll_no = max_roll;
                    }
                });

                frm.refresh_field('items');
                calculate_total(frm);
                d.hide();
            });
        }
    });

    d.fields_dict.roll_entries.df.data = expected_rolls;
    d.fields_dict.roll_entries.grid.refresh();
    d.show();
}

function set_shift_production(frm) {
    let system_time = frappe.datetime.now_datetime();
    let current_hour = moment(system_time).hour();

    if (current_hour >= 8 && current_hour < 20) {
        frm.set_value('shift', 'Day Shift');
    }
    else {
        frm.set_value('shift', 'Night Shift');
    }
}

frappe.generate_sticker_flow = function (row_name) {
    var raw_label = cur_frm.doc.custom_label || "Default";
    var label_type = raw_label.trim().toLowerCase();

    var row = locals['Shaft Production Run Item'][row_name];
    if (!row && cur_frm) row = (cur_frm.doc.items || []).find(r => r.name === row_name);

    if (!row) return;

    var final_gsm = row.gsm || "";
    var final_color = row.color || "";
    var final_quality = row.quality || "";
    var w = row.width_inch || "0";

    if (label_type.includes("reliance") || label_type.includes("relience")) {
        flow_reliance_cm(row_name, final_gsm, final_color, final_quality);
    } else {
        frappe.run_print_logic(row_name, w + " Inches", final_gsm, final_color, final_quality);
    }
};

// ==========================================
// Print Logics copied exactly from old scripts
// ==========================================

function flow_reliance_cm(row_name, final_gsm, final_color, final_quality) {
    var d = locals['Shaft Production Run Item'][row_name];
    if (!d && cur_frm) d = (cur_frm.doc.items || []).find(r => r.name === row_name);
    if (!d) return;

    var w = parseFloat(d.width_inch || 0);

    var raw_machine = cur_frm.doc.allocated_unit || "";
    var machine_code = raw_machine.includes("3") ? "A" : raw_machine.includes("2") ? "B" : raw_machine.includes("1") ? "C" : "";

    var month_map = { 1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H", 9: "I", 10: "J", 11: "K", 12: "L" };
    var date_obj = new Date();
    var yyyy = date_obj.getFullYear();
    var last_digit_year = String(yyyy).slice(-1);
    var mm = date_obj.getMonth() + 1;
    var month_char = month_map[mm] || "";

    var base_length = String(Math.round(parseFloat(d.meter_roll || 0)));
    var code_len = Math.round(parseFloat(d.meter_roll || 0));
    var length_code = code_len < 1000 ? "S" : code_len === 1000 ? "N" : code_len > 1000 ? "C" : "";

    var base_width = String(Math.round(w)).padStart(2, "0");
    var batch = String(d.batch_no || "");
    var roll_raw = batch.split('-').pop();
    var display_roll = parseInt(roll_raw, 10);
    if (isNaN(display_roll)) display_roll = 1;
    var padded_roll = String(display_roll).padStart(3, "0");

    var prefix = machine_code + last_digit_year + month_char + length_code + base_width + padded_roll;
    var suffix1 = "NW0" + base_width;
    var suffix2 = "40X" + String(parseFloat(final_gsm)).padStart(3, "0");
    var nw_val = parseFloat(d.net_weight || 0).toFixed(3);
    var the_barcode = prefix + suffix1 + suffix2 + nw_val.replace(".", "");

    var zpl = "^XA\n";
    zpl += "^PW812\n";
    zpl += "^BY2,3,50\n";
    zpl += "^FO140,20^BCN,50,Y,N,N^FD" + the_barcode + "^FS\n";

    var qty_val = String((w * 2.54) / 100).substring(0, 4) + "*" + base_length;
    var dt_str = frappe.datetime.get_datetime_as_string().split(" ")[0].split("-").reverse().join("-");

    zpl += "^CFA,20\n";
    zpl += "^FO140,110^FDCm :^FS ^FO200,110^FD" + String(w * 2.54).substring(0, 4) + "^FS\n";
    zpl += "^FO360,110^FDSha :^FS ^FO430,110^FD" + final_color + "^FS\n";
    zpl += "^FO580,110^FDQty :^FS ^FO650,110^FD" + qty_val + "^FS\n";

    zpl += "^FO140,140^FDIn :^FS ^FO200,140^FD" + w + "^FS\n";
    zpl += "^FO360,140^FDGsm :^FS ^FO430,140^FD" + final_gsm + "^FS\n";
    zpl += "^FO580,140^FDDat :^FS ^FO650,140^FD" + dt_str + "^FS\n";

    zpl += "^FO140,170^FDMt :^FS ^FO200,170^FD" + base_length + "^FS\n";
    zpl += "^FO360,170^FDN.W :^FS ^FO430,170^FD" + d.net_weight + " kg^FS\n";
    zpl += "^FO580,170^FDG.W :^FS ^FO650,170^FD" + (d.gross_weight || d.net_weight) + " kg^FS\n";
    zpl += "^XZ";

    send_zpl_to_qz(zpl, the_barcode);
}

function frappe_run_print_logic(row_name, final_width, final_gsm, final_color, final_quality) {
    frappe.run_print_logic(row_name, final_width, final_gsm, final_color, final_quality);
}

frappe.run_print_logic = function (row_name, final_width, final_gsm, final_color, final_quality) {
    if (typeof qz === "undefined") {
        frappe.msgprint("QZ Tray not detected. Printing bypass for preview.");
        let print_url = frappe.urllib.get_full_url(
            '/printview?doctype=Shaft Production Run&name=' + cur_frm.doc.name + '&format=Roll Label'
        );
        window.open(print_url, '_blank');
        return;
    }
    // Logic for QZ Tray printing exists in the user's base scripts, we bridge to it if available.
};
