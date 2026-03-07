frappe.ui.form.on('Shaft Production Run', {
    refresh: function (frm) {
        frm.get_field('shaft_jobs').grid.cannot_add_rows = true;

        if (!frm.is_new() && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Generate Batches'), function () {
                set_shift_production(frm);
                frm.call({
                    doc: frm.doc,
                    method: 'generate_batch_numbers',
                    callback: function (r) {
                        if (!r.exc) {
                            frm.refresh_field('items');
                            frappe.msgprint("Shift and Batch Sequence calculated. Please verify Roll Numbers.");
                        }
                    }
                });
            }).addClass('btn-primary');
        }

        if (frm.doc.production_plan && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Re-select Work Orders'), function () {
                select_work_orders(frm);
            });
        }

        setTimeout(function () {
            if (frm.fields_dict['items'] && frm.fields_dict['items'].grid) {
                var grid = frm.fields_dict['items'].grid;
                grid.get_field('print_sticker').formatter = function (value, row_doc) {
                    return '<button type="button" class="btn btn-xs btn-default" ' +
                        'style="width: 100%; font-weight: bold; cursor: pointer !important; pointer-events: auto;" ' +
                        'onclick="frappe.generate_sticker_flow(\'' + row_doc.name + '\')"> ' +
                        'Print Label ' +
                        '</button>';
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
                        r.message.forEach(function (d) {
                            var job_row = frm.add_child('shaft_jobs');
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
        var row = locals[cdt][cdn];

        var wos = [];
        if (row.work_orders && row.work_orders.trim() !== "") {
            wos = row.work_orders.split(',').map(s => s.trim()).filter(s => s);
        }

        frappe.call({
            method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_job_roll_details',
            args: {
                production_plan: frm.doc.production_plan,
                job_id: row.job_id,
                combination: row.combination,
                no_of_shafts: parseInt(row.no_of_shafts) || 1,
                gsm: parseFloat(row.gsm) || 0,
                meter_roll: parseFloat(row.meter_roll_mtrs) || 0,
                net_weight: row.net_weight, // Pass the formula string (e.g. 74.78 + 74.78 + 42.27 = 191.83)
                work_orders: wos.length > 0 ? JSON.stringify(wos) : null
            },
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    var rolls_to_add = r.message;
                    var max_roll = 0;

                    // Clean up empty default rows
                    var valid_rows = [];
                    (frm.doc.items || []).forEach(function (r_row) {
                        if (r_row.work_order || r_row.item_code) {
                            valid_rows.push(r_row);
                            var rn = parseInt(r_row.roll_no) || 0;
                            if (rn > max_roll) max_roll = rn;
                        }
                    });

                    if (valid_rows.length === 0) {
                        frm.clear_table('items');
                    } else if (valid_rows.length < (frm.doc.items || []).length) {
                        // Remove invalid rows physically from memory so Frappe doesn't validate them
                        frm.doc.items = valid_rows;
                    }

                    rolls_to_add.forEach(function (r_info) {
                        var new_row = frm.add_child('items');
                        max_roll++;
                        new_row.job = r_info.job;
                        new_row.work_order = r_info.work_order;
                        new_row.item_code = r_info.item_code;
                        new_row.planned_qty = r_info.planned_qty;
                        new_row.width_inch = r_info.width_inch;
                        new_row.gsm = r_info.gsm;
                        new_row.uom = r_info.uom;
                        new_row.color = r_info.color;
                        new_row.quality = r_info.quality;
                        new_row.meter_roll = r_info.meter_roll;
                        new_row.net_weight = r_info.net_weight;
                        new_row.gross_weight = r_info.gross_weight;
                        new_row.roll_no = max_roll;
                    });

                    frm.refresh_field('items');

                    if (typeof calculate_total === "function") {
                        calculate_total(frm);
                    }

                    // Force a save to validate and generate batches
                    setTimeout(function () {
                        frm.save().then(function () {
                            frm.call({
                                doc: frm.doc,
                                method: 'generate_batch_numbers',
                                callback: function (r) {
                                    if (!r.exc) {
                                        frm.refresh_field('items');
                                        frappe.msgprint({
                                            title: 'Success',
                                            message: 'Successfully added ' + rolls_to_add.length + ' rolls for Job ' + row.job_id + ' to the Produced Rolls table and generated batch numbers.',
                                            indicator: 'green'
                                        });
                                    }
                                }
                            });
                        });
                    }, 500);
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
            var max_roll = 0;
            (frm.doc.items || []).forEach(function (row) {
                var r = parseInt(row.roll_no) || 0;
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
    var total = 0.0;
    (frm.doc.items || []).forEach(function (row) {
        total += flt(row.net_weight);
    });
    frm.set_value('total_produced_weight', total);
}

function select_work_orders(frm) {
    var d = new frappe.ui.form.MultiSelectDialog({
        doctype: "Work Order",
        target: frm,
        setters: {
            production_plan: frm.doc.production_plan
        },
        add_filters_group: 1,
        get_query() {
            return {
                filters: {
                    production_plan: frm.doc.production_plan,
                    docstatus: 1,
                    status: ["not in", ["Cancelled", "Closed"]]
                }
            };
        },
        primary_action(selections) {
            if (selections && selections.length > 0) {
                fetch_jobs_for_wos(frm, selections);
                d.dialog.hide();
            } else {
                frappe.msgprint("Please select at least one Work Order.");
            }
        },
        action(selections) {
            // Fallback for different framework versions
            if (selections && selections.length > 0) {
                fetch_jobs_for_wos(frm, selections);
                d.dialog.hide();
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
                        var job_row = frm.add_child('shaft_jobs');
                        job_row.job_id = d.job_id;
                        job_row.gsm = d.gsm;
                        job_row.combination = d.combination;
                        job_row.total_width = d.total_width;
                        job_row.meter_roll_mtrs = d.meter_roll_mtrs;
                        job_row.net_weight = d.net_weight;
                        job_row.total_weight = d.total_weight;
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


// Popup dialog removed by user request, rows now fill automatically.

function set_shift_production(frm) {
    var current_hour = new Date().getHours();

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
    if (!row && cur_frm) row = (cur_frm.doc.items || []).find(function (r) { return r.name === row_name; });
    if (!row) return;

    var item_code = row.item_code || "";
    // In our system, the item name isn't directly on the row, we might need to get it from the Item link if missing
    // But we'll try to extract from code first.
    var details = extract_details_enhanced("", item_code);

    var final_gsm = row.gsm || details.gsm || "";
    var final_color = row.color || details.color || "";
    var final_quality = row.quality || details.quality || "";

    if (label_type.includes("reliance") || label_type.includes("relience")) {
        flow_reliance_cm(row_name, final_gsm, final_color, final_quality);
    } else {
        var w = row.width_inch || details.width_inch || "0";
        frappe.run_print_logic(row_name, w + " Inches", final_gsm, final_color, final_quality);
    }
};

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
        var known_qualities = ["SUPER PLATINUM", "SUPER CLASSIC", "LIFE STYLE", "ECO SPECIAL",
            "ECO GREEN", "SUPER ECO", "DELUXE", "PREMIUM", "PLATINUM", "GOLD",
            "SILVER", "BRONZE", "CLASSIC", "ULTRA", "UV"];
        known_qualities.sort(function (a, b) { return b.length - a.length; });
        for (var i = 0; i < known_qualities.length; i++) {
            var q = known_qualities[i];
            var qb = new RegExp('\\b' + q + '\\b', 'i');
            if (qb.test(name_upper)) { res.quality = q; break; }
        }
        if (res.quality) {
            var qp = name_upper.indexOf(res.quality.toUpperCase());
            if (qp !== -1) {
                var aq = name.substring(qp + res.quality.length).trim();
                aq = aq.replace(/\s*\d+\s*GSM.*/i, "").trim();
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

function flow_reliance_cm(row_name, gsm, color, quality) {
    var saved_val = cur_frm.doc.custom_batch_width || 0;
    if (saved_val > 0) {
        frappe.run_print_logic(row_name, saved_val + " CM", gsm, color, quality);
    } else {
        var row = locals['Shaft Production Run Item'][row_name];
        if (!row && cur_frm) row = (cur_frm.doc.items || []).find(function (r) { return r.name === row_name; });
        var item_code = row ? (row.item_code || "") : "";

        var width_mm = (item_code.length >= 4) ? parseFloat(item_code.slice(-4)) : 0;
        var width_cm = (width_mm > 0) ? (width_mm / 10) : 0;

        frappe.prompt([{ label: 'Verify Width (CM)', fieldname: 'width_cm', fieldtype: 'Float', default: width_cm, reqd: 1 }],
            function (values) {
                cur_frm.set_value('custom_batch_width', values.width_cm);
                frappe.run_print_logic(row_name, values.width_cm + " CM", gsm, color, quality);
            }, 'Confirm Reliance Size', 'Preview Label');
    }
}

frappe.run_print_logic = function (row_name, final_width_display, final_gsm, final_color, final_quality) {
    var row = locals['Shaft Production Run Item'][row_name];
    if (!row && cur_frm) row = (cur_frm.doc.items || []).find(function (r) { return r.name === row_name; });
    if (!row) return;

    var d = {
        company: "JAYASHREE SPUN BOND",
        quality: final_quality || "NON WOVEN FABRIC",
        gsm: final_gsm,
        color: final_color,
        width_val: final_width_display,
        party_code: "", // Could be fetched from WO if needed
        item_code: row.item_code || "",
        barcode_data: row.batch_no || "",
        length: row.meter_roll || "0",
        gw: (row.gross_weight || row.net_weight || 0).toFixed(2),
        nw: (row.net_weight || 0).toFixed(2),
        batch_no: row.batch_no || "",
        roll_no: row.roll_no || ""
    };

    var htmlContent = get_grid_format(d, (cur_frm.doc.custom_label || "").toLowerCase());
    var printWindow = window.open('', 'PRINT', 'height=650,width=500');
    if (printWindow) {
        printWindow.document.write(htmlContent);
        printWindow.document.close();
    }
};

function get_grid_format(d, type) {
    type = (type || "default").trim().toLowerCase();
    var isReliance = type.includes("reliance") || type.includes("relience");
    var isPerfect = type.includes("perfect");
    var isPlainCC = type.includes("plain cc");
    var isPlain = type.includes("plain") && !isPlainCC;
    var isDefault = !isReliance && !isPerfect && !isPlainCC && !isPlain;

    var header = "Non Woven Fabrics";
    var sub1 = d.quality;
    var sub2 = "";

    if (isDefault) {
        header = "JayaShree Spun Bond";
        sub1 = "\u2709 info@jayashreespunbond.com";
        sub2 = d.quality + (d.party_code ? (" | " + d.party_code) : "");
    } else if (isPlainCC) {
        sub1 = d.quality + (d.party_code ? (" | " + d.party_code) : "");
    }

    var rows = [];
    rows.push('<tr><td><span class="lbl">GSM:</span><span class="val">' + d.gsm + '</span></td><td><span class="lbl">COLOR:</span><span class="val">' + d.color + '</span></td></tr>');

    if (isPerfect) {
        rows.push('<tr><td colspan="2"><span class="lbl">Mtrs / Roll:</span><span class="val">' + d.length + ' Mtrs</span></td></tr>');
    } else {
        rows.push('<tr><td><span class="lbl">Mtrs / Roll:</span><span class="val">' + d.length + ' Mtrs</span></td><td><span class="lbl">WIDTH:</span><span class="val">' + d.width_val + '</span></td></tr>');
    }

    rows.push('<tr><td><span class="lbl">NET WT:</span><span class="val">' + d.nw + ' Kgs</span></td><td><span class="lbl">GROSS WT:</span><span class="val">' + d.gw + ' Kgs</span></td></tr>');

    return '<html><head><title>Label Preview</title><style>' +
        '@media print { .btn-panel { display: none !important; } @page { size: 4in 4in; margin: 0; } body { margin: 0; } }' +
        'body { font-family: "Arial", sans-serif; margin: 0; padding: 0; text-align: center; background: #eee; }' +
        '.btn-panel { padding: 10px; background: #eee; }' +
        '.sticker { width: 4in; height: 4in; margin: 20px auto; border: 2px solid black; background: white; box-sizing: border-box; display: flex; flex-direction: column; }' +
        'table { width: 100%; border-collapse: collapse; table-layout: fixed; }' +
        'td { border: 1px solid black; padding: 4px; vertical-align: top; overflow: hidden; }' +
        '.header { text-align: center; height: 18mm; vertical-align: middle; padding: 2px 0; }' +
        '.company { font-size: 20px; font-weight: 900; letter-spacing: 0.3px; line-height: 1.1; }' +
        '.email { font-size: 11px; font-weight: bold; color: #333; margin: 1px 0; }' +
        '.subheader { font-size: 12px; font-weight: bold; color: black; }' +
        '.lbl { font-size: 10px; font-weight: bold; color: #444; display: block; }' +
        '.val { font-size: 15px; font-weight: 900; color: #000; display: block; }' +
        '.barcode-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 5px; border-top: 1px solid black; }' +
        '#barcode { max-width: 95%; height: 70px; }' +
        '.footer-info { font-size: 13px; font-weight: bold; margin-top: 10px; padding-bottom: 5px; }' +
        '</style></head><body>' +
        '<div class="btn-panel"><button onclick="window.print()" style="padding:10px 20px; font-weight:bold; cursor:pointer;">PRINT</button><button onclick="window.close()" style="padding:10px 20px; margin-left:10px;">CLOSE</button></div>' +
        '<div class="sticker"><table><tr><td colspan="2" class="header"><div class="company">' + header + '</div><div class="' + (isDefault ? 'email' : 'subheader') + '">' + sub1 + '</div>' + (sub2 ? '<div class="subheader">' + sub2 + '</div>' : '') + '</td></tr>' +
        '<tr><td colspan="2" style="text-align:center;"><span class="lbl">ITEM:</span><span class="val">' + d.item_code + '</span></td></tr>' +
        rows.join('') + '</table>' +
        '<div class="barcode-container"><svg id="barcode"></svg><div class="footer-info">BATCH: ' + d.batch_no + ' | ROLL: ' + d.roll_no + '</div></div></div>' +
        '<script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.0/dist/JsBarcode.all.min.js"></script>' +
        '<script>JsBarcode("#barcode", "' + d.barcode_data + '", { format: "CODE128", displayValue: false, height: 70, width: 2.0, margin: 0 });</script>' +
        '</body></html>';
}
