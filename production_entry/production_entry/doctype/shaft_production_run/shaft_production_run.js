frappe.ui.form.on('Shaft Production Run', {
    setup: function (frm) {
        frm.set_df_property('filter_job_id', 'fieldtype', 'Select');
        frm.set_df_property('filter_job_id', 'options', ['All']);
    },
    refresh: function (frm) {
        if (frm.doc.production_plan) {
            frm.add_custom_button(__('Select Work Orders'), function () {
                select_work_orders(frm);
            }, __('Actions'));
        }

        update_job_filter_options(frm);
        setup_grid_filter(frm);

        if (frm.doc.docstatus === 0) {
            frm.get_field('shaft_jobs').grid.add_custom_button(__('Add Manual Job'), function () {
                add_manual_job_dialog(frm);
            });
            // Disable manual row addition to the grid itself to force use of buttons/fetch
            frm.get_field('shaft_jobs').grid.cannot_add_rows = true;
        }

        if (frm.is_new()) {
            set_shift_production(frm);
        }
    },

    production_plan: function (frm) {
        if (frm.doc.production_plan) {
            fetch_shaft_details(frm);
        }
    },

    filter_job_id: function (frm) {
        apply_grid_filter(frm);
    }
});

function fetch_shaft_details(frm) {
    frappe.call({
        method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
        args: {
            production_plan: frm.doc.production_plan
        },
        callback: function (r) {
            if (r.message) {
                var jobs = r.message.jobs || [];
                var label_type = r.message.label_type || "Default";

                frm.clear_table('shaft_jobs');
                if (jobs.length > 0) {
                    jobs.forEach(function (d) {
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

                    frm.set_value('custom_label', label_type);
                    frm.refresh_field('shaft_jobs');
                    update_job_filter_options(frm);
                    frappe.msgprint(`Fetched ${jobs.length} jobs from Production Plan. Label Type set to ${label_type}.`);
                }
            }
        }
    });
}

frappe.ui.form.on('Shaft Production Run Job', {
    create_roll_entry: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (frm.is_new()) {
            frappe.confirm("Create Entry requires the document to be saved first. Save now?", () => {
                frm.save().then(() => {
                    execute_create_roll_entry(frm, row);
                });
            });
        } else {
            if (frm.is_dirty()) {
                frm.save().then(() => {
                    execute_create_roll_entry(frm, row);
                });
            } else {
                execute_create_roll_entry(frm, row);
            }
        }
    }
});

function execute_create_roll_entry(frm, row) {
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
            net_weight: row.net_weight,
            work_orders: wos.length > 0 ? JSON.stringify(wos) : null,
            parent_spr: frm.doc.name
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                var rolls_to_add = r.message;
                var max_roll = 0;

                // Clean up empty default rows safely
                var items = frm.doc.items || [];
                for (var i = items.length - 1; i >= 0; i--) {
                    var r_row = items[i];
                    if (!r_row.work_order && !r_row.item_code) {
                        frm.get_field('items').grid.grid_rows[i].remove();
                    } else {
                        var rn = parseInt(r_row.roll_no) || 0;
                        if (rn > max_roll) max_roll = rn;
                    }
                }

                rolls_to_add.forEach(function (d) {
                    var child = frm.add_child('items');
                    frappe.model.set_value(child.doctype, child.name, 'job', d.job);
                    frappe.model.set_value(child.doctype, child.name, 'work_order', d.work_order);
                    frappe.model.set_value(child.doctype, child.name, 'item_code', d.item_code);
                    frappe.model.set_value(child.doctype, child.name, 'planned_qty', d.planned_qty);
                    frappe.model.set_value(child.doctype, child.name, 'width_inch', d.width_inch);
                    frappe.model.set_value(child.doctype, child.name, 'gsm', d.gsm);
                    frappe.model.set_value(child.doctype, child.name, 'meter_roll', d.meter_roll);
                    frappe.model.set_value(child.doctype, child.name, 'net_weight', d.net_weight);
                    frappe.model.set_value(child.doctype, child.name, 'quality', d.quality);
                    frappe.model.set_value(child.doctype, child.name, 'color', d.color);
                    frappe.model.set_value(child.doctype, child.name, 'uom', d.uom);
                    frappe.model.set_value(child.doctype, child.name, 'wo_status', d.wo_status);

                    max_roll++;
                    frappe.model.set_value(child.doctype, child.name, 'roll_no', max_roll);
                });

                frm.refresh_field('items');
                update_job_filter_options(frm);
                apply_grid_filter(frm);
                frm.set_value('filter_job_id', row.job_id);

                if (typeof calculate_total === "function") {
                    calculate_total(frm);
                }

                setTimeout(function () {
                    frm.save().then(function () {
                        frm.call({
                            doc: frm.doc,
                            method: 'generate_batch_numbers',
                            callback: function (r) {
                                if (r.message && !r.exc) {
                                    frappe.model.sync(r.message);
                                    frm.refresh();
                                    frappe.msgprint({
                                        title: 'Success',
                                        message: 'Successfully added ' + rolls_to_add.length + ' rolls for Job ' + row.job_id + '.',
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

frappe.ui.form.on('Shaft Production Run Item', {
    net_weight: function (frm, cdt, cdn) {
        calculate_total(frm);
    },
    items_remove: function (frm) {
        calculate_total(frm);
    },
    print_sticker: function (frm, cdt, cdn) {
        frappe.generate_sticker_flow(cdn, frm);
    }
});

function calculate_total(frm) {
    var total = 0.0;
    (frm.doc.items || []).forEach(function (row) {
        total += flt(row.net_weight);
    });
    frm.set_value('total_produced_weight', total);
}

function update_job_filter_options(frm) {
    var options = ["All"];
    (frm.doc.shaft_jobs || []).forEach(function (j) {
        if (j.job_id && !options.includes(String(j.job_id))) {
            options.push(String(j.job_id));
        }
    });

    frm.set_df_property('filter_job_id', 'fieldtype', 'Select');
    frm.set_df_property('filter_job_id', 'options', options.join('\n'));

    if (!frm.doc.filter_job_id) {
        frm.set_value('filter_job_id', 'All');
    }
}

function add_manual_job_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: 'Add Manual Job',
        fields: [
            {
                label: 'Select Items',
                fieldname: 'items',
                fieldtype: 'MultiSelect',
                get_data: function () {
                    return frappe.db.get_link_options('Item', '', { 'is_stock_item': 1 });
                },
                reqd: 1
            },
            {
                label: 'Meter / Roll',
                fieldname: 'meter_roll',
                fieldtype: 'Float',
                default: 800,
                reqd: 1
            },
            {
                label: 'Number of Shafts',
                fieldname: 'no_of_shafts',
                fieldtype: 'Int',
                default: 4,
                reqd: 1
            }
        ],
        primary_action_label: 'Create Job',
        primary_action(values) {
            let selected_items = values.items.split(',').map(i => i.trim());
            let max_id = 0;
            (frm.doc.shaft_jobs || []).forEach(j => {
                let id = parseInt(j.job_id) || 0;
                if (id > max_id) max_id = id;
            });
            let new_job_id = String(max_id + 1);

            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Item',
                    filters: { name: ['in', selected_items] },
                    fields: ['name', 'item_name', 'item_code', 'custom_gsm', 'item_group']
                },
                callback: function (r) {
                    if (r.message) {
                        let items_data = r.message;
                        let gsm = 0;
                        let widths = [];
                        items_data.forEach(item => {
                            let details = extract_details_enhanced(item.item_name || item.item_code, item.item_code);
                            if (details.gsm) gsm = details.gsm;
                            if (details.width_inch) widths.push(details.width_inch);
                        });

                        let h_val = widths.join('\" + ') + '\"';
                        let total_width = widths.reduce((a, b) => a + b, 0);

                        let job_row = frm.add_child('shaft_jobs');
                        job_row.job_id = new_job_id;
                        job_row.gsm = gsm;
                        job_row.combination = h_val;
                        job_row.total_width = total_width;
                        job_row.meter_roll_mtrs = values.meter_roll;
                        job_row.no_of_shafts = values.no_of_shafts;
                        job_row.is_manual = 1;
                        job_row.manual_items = JSON.stringify(selected_items);

                        selected_items.forEach(item_code => {
                            frappe.call({
                                method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.create_manual_work_order',
                                args: {
                                    production_plan: frm.doc.production_plan,
                                    item_code: item_code,
                                    qty: values.meter_roll * values.no_of_shafts
                                }
                            });
                        });

                        frm.refresh_field('shaft_jobs');
                        update_job_filter_options(frm);
                        d.hide();
                        frappe.show_alert({ message: __('Manual Job Added Successfully'), indicator: 'green' });
                    }
                }
            });
        }
    });
    d.show();
}

function setup_grid_filter(frm) {
    if (frm.get_field('items')) {
        var grid = frm.get_field('items').grid;
        var old_refresh = grid.refresh;
        grid.refresh = function () {
            old_refresh.apply(grid, arguments);
            apply_grid_filter(frm);
        };
        frm.fields_dict['items'].grid.on_grid_refresh = function () {
            apply_grid_filter(frm);
        };
    }
}

function apply_grid_filter(frm) {
    var filter = frm.doc.filter_job_id || "All";
    var grid = frm.get_field('items').grid;
    if (!grid || !grid.wrapper) return;

    var job_colors = {};
    var color_palette = ['#2980b9', '#27ae60', '#8e44ad', '#f39c12', '#c0392b', '#16a085', '#2c3e50'];
    var color_idx = 0;

    $(grid.wrapper).find('.grid-row').each(function () {
        var name = $(this).attr('data-name');
        var row = (frm.doc.items || []).find(r => r.name === name);
        if (!row) return;

        if (!job_colors[row.job]) {
            job_colors[row.job] = color_palette[color_idx % color_palette.length];
            color_idx++;
        }
        $(this).css('border-left', '5px solid ' + job_colors[row.job]);

        if (filter !== "All" && String(row.job) !== String(filter)) {
            $(this).hide();
        } else {
            $(this).show();
        }
    });

    if (filter !== "All") {
        $(grid.wrapper).find('.grid-footer').hide();
    } else {
        $(grid.wrapper).find('.grid-footer').show();
    }
}

function select_work_orders(frm) {
    var d = new frappe.ui.form.MultiSelectDialog({
        doctype: "Work Order",
        target: frm,
        setters: {
            production_plan: frm.doc.production_plan
        },
        add_filters_group: 1,
        columns: ["status", "production_plan", "item_code", "qty"],
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
        }
    });
}

function fetch_jobs_for_wos(frm, work_orders) {
    frappe.call({
        method: 'production_entry.production_entry.doctype.shaft_production_run.shaft_production_run.get_shaft_jobs',
        args: {
            production_plan: frm.doc.production_plan,
            work_orders: work_orders
        },
        callback: function (r) {
            if (r.message) {
                var jobs = r.message.jobs || [];
                var label_type = r.message.label_type || "Default";

                frm.clear_table('shaft_jobs');
                if (jobs.length > 0) {
                    jobs.forEach(function (d) {
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
                    frm.set_value('custom_label', label_type);
                    frm.refresh_field('shaft_jobs');
                }
            }
        }
    });
}

function set_shift_production(frm) {
    var current_hour = new Date().getHours();
    if (current_hour >= 8 && current_hour < 20) {
        frm.set_value('shift', 'Day Shift');
    } else {
        frm.set_value('shift', 'Night Shift');
    }
}

frappe.generate_sticker_flow = function (row_name, frm) {
    var f = frm || cur_frm;
    var row = locals['Shaft Production Run Item'][row_name] || (f.doc.items || []).find(function (r) { return r.name === row_name; });
    if (!row) return;

    frappe.db.get_value('Item', row.item_code, 'item_name', function (r) {
        var item_name = (r && r.item_name) || "";
        trigger_print_with_details(row_name, item_name, f);
    });
};

function trigger_print_with_details(row_name, item_name, frm) {
    var doc = frm.doc;
    var raw_label = doc.custom_label || "Default";
    var label_type = raw_label.trim().toLowerCase();
    var row = locals['Shaft Production Run Item'][row_name] || (doc.items || []).find(function (r) { return r.name === row_name; });
    if (!row) return;

    var details = extract_details_enhanced(item_name, row.item_code);
    var final_gsm = row.gsm || details.gsm || "";
    var final_color = row.color || details.color || "";
    var final_quality = row.quality || details.quality || "";

    if (label_type.includes("reliance") || label_type.includes("relience")) {
        flow_reliance_cm(row_name, final_gsm, final_color, final_quality, frm);
    } else {
        var w = row.width_inch || details.width_inch || "0";
        frappe.run_print_logic(row_name, w + " Inches", final_gsm, final_color, final_quality, frm);
    }
}

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
        var known_qualities = ["SUPER PLATINUM", "SUPER CLASSIC", "LIFE STYLE", "ECO SPECIAL", "ECO GREEN", "SUPER ECO", "DELUXE", "PREMIUM", "PLATINUM", "GOLD", "SILVER", "BRONZE", "CLASSIC", "ULTRA", "UV"];
        known_qualities.sort(function (a, b) { return b.length - a.length; });
        for (var i = 0; i < known_qualities.length; i++) {
            var q = known_qualities[i];
            if (new RegExp('\\b' + q + '\\b', 'i').test(name_upper)) { res.quality = q; break; }
        }
        if (res.quality) {
            var qp = name_upper.indexOf(res.quality.toUpperCase());
            if (qp !== -1) {
                var aq = name.substring(qp + res.quality.length).trim();
                aq = aq.split(/\s*\d+\s*GSM/i)[0].trim();
                aq = aq.replace(/^[\s,:-]+|[\s,:-]+$/g, "");
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

function flow_reliance_cm(row_name, gsm, color, quality, frm) {
    var row = locals['Shaft Production Run Item'][row_name] || (frm.doc.items || []).find(r => r.name === row_name);
    var item_code = row ? (row.item_code || "") : "";
    var width_mm = (item_code.length >= 4) ? parseFloat(item_code.slice(-4)) : 0;
    var width_cm = (width_mm > 0) ? (width_mm / 10) : 0;

    frappe.prompt([{
        label: 'Verify Width (CM) for ' + (item_code || 'this row'),
        fieldname: 'width_cm',
        fieldtype: 'Float',
        default: width_cm,
        reqd: 1
    }], function (values) {
        frappe.run_print_logic(row_name, values.width_cm + " CM", gsm, color, quality, frm);
    }, 'Confirm Reliance Size (' + row.roll_no + ')', 'Preview Label');
}

frappe.run_print_logic = function (row_name, final_width_display, final_gsm, final_color, final_quality, frm) {
    var row = locals['Shaft Production Run Item'][row_name] || (frm.doc.items || []).find(r => r.name === row_name);
    if (!row) return;

    var d = {
        company: "JAYASHREE SPUN BOND",
        quality: final_quality || "NON WOVEN FABRIC",
        gsm: final_gsm,
        color: final_color,
        width_val: final_width_display,
        item_code: row.item_code || "",
        barcode_data: row.batch_no || "",
        length: row.meter_roll || "0",
        gw: (flt(row.gross_weight) || flt(row.net_weight)).toFixed(2),
        nw: flt(row.net_weight).toFixed(2),
        batch_no: row.batch_no || "",
        roll_no: row.roll_no || ""
    };

    var htmlContent = get_grid_format(d, (frm.doc.custom_label || "Default").toLowerCase());
    var printWindow = window.open('', '_blank', 'height=650,width=500');
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
        sub2 = d.quality;
    } else if (isPlainCC) {
        sub1 = d.quality;
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
