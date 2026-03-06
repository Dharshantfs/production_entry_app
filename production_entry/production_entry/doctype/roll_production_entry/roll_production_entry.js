frappe.ui.form.on('Roll Production Entry', {
    refresh: function (frm) {
        render_job_sections(frm);
        calculate_total(frm);

        if (!frm.is_new() && frm.doc.docstatus === 0) {
            frm.page.set_primary_action(__('Submit Production'), function () {
                if (frm.is_dirty()) {
                    frappe.show_alert({ message: 'Saving...', indicator: 'orange' });
                    frm.save(null, () => trigger_submission(frm));
                } else {
                    trigger_submission(frm);
                }
            });
        }

        if (!frm.is_new()) {
            frm.add_custom_button('♻️ Reset Width', function () {
                frm.set_value('custom_batch_width', 0);
                frappe.msgprint("Width reset.");
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

        // Add "Submit Roll" button if status is not Completed
        if (frm.doc.status !== "Completed" && !frm.is_dirty() && frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Submit Roll'), function () {
                frappe.confirm('Create Stock Entries for all rolls?', () => {
                    frappe.call({
                        method: "production_entry.production_entry.doctype.roll_production_entry.roll_production_entry.create_stock_entries_for_roll",
                        args: { doc_name: frm.doc.name },
                        freeze: true,
                        freeze_message: "Processing...",
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.msgprint("Stock Entries created and submitted successfully!");
                                frm.reload_doc();
                                trigger_bulk_label_print(frm);
                            }
                        }
                    });
                });
            }).addClass('btn-primary');
        }
    },

    onload: function (frm) {
        render_job_sections(frm);
        // Trigger only for new entries to prevent overwriting historical data
        if (frm.is_new()) {
            set_shift_production(frm);
        }
    },

    // TRIGGER: When the Item Name on the MAIN form is populated
    production_item_name: function (frm) {
        if (frm.doc.production_item_name && frm.doc.items) {
            // Update all existing rows in the child table
            frm.doc.items.forEach(row => {
                extract_specs_to_row(frm, row.doctype, row.name);
            });
            frm.refresh_field('items');
        }
    }
});

frappe.ui.form.on('Roll Production Entry Item', {
    print_sticker: function (frm, cdt, cdn) {
        frappe.generate_sticker_flow(cdn);
    },
    meter_per_roll: function (frm, cdt, cdn) {
        render_job_sections(frm);
    },
    width_inch: function (frm, cdt, cdn) {
        validate_total_width(frm);
        render_job_sections(frm);
    },
    net_weight: function (frm, cdt, cdn) {
        if (frm.doc.docstatus === 0) calculate_total(frm);
        render_job_sections(frm);
    },
    gross_weight: function (frm, cdt, cdn) {
        render_job_sections(frm);
    },
    items_remove: function (frm) {
        if (frm.doc.docstatus === 0) calculate_total(frm);
        validate_total_width(frm);
        render_job_sections(frm);
    },
    items_add: function (frm, cdt, cdn) {
        extract_specs_to_row(frm, cdt, cdn);

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


// =================================================================
// EXTRACTION & FLOW LOGIC
// =================================================================

function validate_total_width(frm) {
    if (!frm.doc.custom_batch_width) return;
    let shaft_totals = {};
    (frm.doc.items || []).forEach(row => {
        let s_num = row.shaft_number || 1;
        if (!shaft_totals[s_num]) shaft_totals[s_num] = 0;
        shaft_totals[s_num] += flt(row.width_inch);
    });
    for (let s_num in shaft_totals) {
        if (shaft_totals[s_num] > frm.doc.custom_batch_width) {
            frappe.msgprint(__('Shaft ' + s_num + ' width (' + shaft_totals[s_num] + ') exceeds limit (' + frm.doc.custom_batch_width + ')'));
            break;
        }
    }
}

function trigger_bulk_label_print(frm) {
    let print_url = frappe.urllib.get_full_url(
        '/printview?doctype=Roll Production Entry&name=' + frm.doc.name + '&format=Roll Label'
    );
    window.open(print_url, '_blank');
}

function set_shift_production(frm) {
    // Fetches the official ERPNext system time
    let system_time = frappe.datetime.now_datetime();
    let current_hour = moment(system_time).hour();

    // PRODUCTION LOGIC:
    // 8:00 AM (8) to 7:59 PM (19) is Day Shift
    // 8:00 PM (20) to 7:59 AM (7) is Night Shift
    if (current_hour >= 8 && current_hour < 20) {
        frm.set_value('shift', 'Day Shift');
    }
    else {
        frm.set_value('shift', 'Night Shift');
    }

    // Refresh the field to ensure any dependent UI logic updates
    frm.refresh_field('shift');
}

/**
 * Helper Function: Extracts GSM and Width from the parent Item Name
 * Matches formats like: "80 GSM" and "63.0"" or "63.0''"
 */
function extract_specs_to_row(frm, cdt, cdn) {
    let item_name = frm.doc.production_item_name || "";
    if (!item_name) return;

    // Regex for GSM: Finds digits before the word GSM
    let gsm_match = item_name.match(/(\d+)\s*GSM/i);

    // Regex for Width: Finds digits/decimals followed by " or ''
    let width_match = item_name.match(/(\d+(\.\d+)?)\s*("|'')/);

    if (gsm_match) {
        frappe.model.set_value(cdt, cdn, 'gsm', gsm_match[1]);
    }

    if (width_match) {
        frappe.model.set_value(cdt, cdn, 'width_inch', width_match[1]);
    }
}

frappe.generate_sticker_flow = function (row_name) {
    var raw_label = cur_frm.doc.custom_label || "Default";
    var label_type = raw_label.trim().toLowerCase();

    var row = locals['Roll Production Entry Item'][row_name];
    if (!row && cur_frm) row = (cur_frm.doc.items || []).find(r => r.name === row_name);

    var item_name = cur_frm.doc.production_item_name || cur_frm.doc.item_name || "";
    var item_code = cur_frm.doc.production_item || "";

    // Pass both name and code for accurate extraction
    var details = extract_details_enhanced(item_name, item_code);

    var final_gsm = details.gsm || "";
    var final_color = details.color || "";
    var final_quality = details.quality || "";

    if (label_type.includes("reliance") || label_type.includes("relience")) {
        flow_reliance_cm(row_name, final_gsm, final_color, final_quality);
    } else {
        // Use extracted width in inch, fallback to 0
        var w = details.width_inch || "0";
        frappe.run_print_logic(row_name, w + " Inches", final_gsm, final_color, final_quality);
    }
};

// Quality Master: 3-digit quality code (item_code digits 4-6) → quality name
var QUALITY_MASTER = {
    "100": "PREMIUM", "101": "PLATINUM", "102": "SUPER PLATINUM",
    "103": "GOLD", "104": "SILVER", "105": "BRONZE",
    "106": "CLASSIC", "107": "SUPER CLASSIC", "108": "LIFE STYLE",
    "109": "ECO SPECIAL", "110": "ECO GREEN", "111": "SUPER ECO",
    "112": "ULTRA", "113": "DELUXE", "114": "UV"
};

function extract_details_enhanced(name, code) {
    if (!name) return {};
    var res = { gsm: null, color: null, width_inch: null, quality: null };
    var name_upper = name.toUpperCase();

    if (code && code.length === 16 && /^\d+$/.test(code)) {
        // === ITEM CODE PATH (16 digits: PPP QQQ CCC GSM WWWW) ===

        // 1. Quality: digits 4-6 (index 3,4,5)
        var qual_code = code.substring(3, 6);
        if (QUALITY_MASTER[qual_code]) res.quality = QUALITY_MASTER[qual_code];

        // 2. GSM: digits 10-12 (index 9,10,11)
        var code_gsm = parseInt(code.substring(9, 12));
        if (code_gsm > 0) res.gsm = String(code_gsm);

        // 3. Width: digits 13-16 (index 12-15) in mm → inch
        var code_width_mm = parseFloat(code.substring(12, 16));
        if (code_width_mm > 0) res.width_inch = Math.round(code_width_mm / 25.4);

        // 4. Color: text AFTER quality name in item name, before GSM number
        if (res.quality) {
            var qual_pos = name_upper.indexOf(res.quality.toUpperCase());
            if (qual_pos !== -1) {
                var after_qual = name.substring(qual_pos + res.quality.length).trim();
                after_qual = after_qual.replace(/\s*\d+\s*GSM.*/i, "").trim();
                if (after_qual) res.color = after_qual;
            }
        }
        // Fallback: FABRIC...GSM pattern
        if (!res.color) {
            var mc = name.match(/FABRIC\s+(.*?)\s+\d+\s*GSM/i);
            if (mc) res.color = mc[1].replace(new RegExp(res.quality || '', 'gi'), '').trim();
        }

    } else {
        // === FALLBACK PATH (non-standard or missing code) ===
        var known_qualities = ["SUPER PLATINUM", "SUPER CLASSIC", "LIFE STYLE", "ECO SPECIAL",
            "ECO GREEN", "SUPER ECO", "DELUXE", "PREMIUM", "PLATINUM", "GOLD",
            "SILVER", "BRONZE", "CLASSIC", "ULTRA", "UV"];
        known_qualities.sort((a, b) => b.length - a.length);
        for (let q of known_qualities) {
            var qb = new RegExp('\\b' + q + '\\b', 'i');
            if (qb.test(name_upper)) { res.quality = q; break; }
        }

        // Color: after quality in name (before GSM)
        if (res.quality) {
            var qp = name_upper.indexOf(res.quality.toUpperCase());
            if (qp !== -1) {
                var aq = name.substring(qp + res.quality.length).trim();
                aq = aq.replace(/\s*\d+\s*GSM.*/i, "").trim();
                if (aq) res.color = aq;
            }
        }
        if (!res.color) {
            var mc2 = name.match(/FABRIC\s+(.*?)\s+\d+\s*GSM/i);
            if (mc2) res.color = mc2[1].replace(new RegExp(res.quality || '', 'gi'), '').trim();
        }

        // GSM fallback
        if (!res.gsm) {
            var mg = name.match(/(\d+)\s*GSM/i);
            if (mg) res.gsm = mg[1];
        }
        // Width fallback
        if (!res.width_inch) {
            var mw = name.match(/(\d+(\.\d+)?)\s*("|inch|in|'')/i);
            if (mw) res.width_inch = mw[1];
        }
    }

    return res;
}


function flow_reliance_cm(row_name, gsm, color, quality) {
    var saved_val = cur_frm.doc.custom_batch_width || 0;
    if (saved_val > 0) {
        frappe.run_print_logic(row_name, saved_val + " CM", gsm, color, quality);
    } else {
        var item_code = cur_frm.doc.production_item || "";
        // Reliance logic: use last 4 digits as mm, then /10 for cm
        var width_mm = (item_code.length >= 4) ? parseFloat(item_code.slice(-4)) : 0;
        var width_cm = (width_mm > 0) ? (width_mm / 10) : 0;

        frappe.prompt([{ label: 'Verify Width (CM)', fieldname: 'width_cm', fieldtype: 'Float', default: width_cm, reqd: 1 }],
            (values) => {
                cur_frm.set_value('custom_batch_width', values.width_cm);
                frappe.run_print_logic(row_name, values.width_cm + " CM", gsm, color, quality);
            }, 'Confirm Reliance Size', 'Preview Label');
    }
}

// =================================================================
// PRINT LOGIC (BARCODE = ONLY BATCH NO)
// =================================================================
frappe.run_print_logic = function (row_name, final_width_display, final_gsm, final_color, final_quality) {
    var row = locals['Roll Production Entry Item'][row_name];
    if (!row && cur_frm) row = (cur_frm.doc.items || []).find(r => r.name === row_name);
    if (!row) return;

    var d = {
        company: "JAYASHREE SPUN BOND",
        quality: final_quality || "NON WOVEN FABRIC",
        gsm: final_gsm,
        color: final_color,
        width_val: final_width_display,
        party_code: cur_frm.doc.party_code || "",
        item_code: cur_frm.doc.production_item || "",
        barcode_data: row.batch_no || "",
        length: row.meter_per_roll || row.qty || "0",
        gw: (row.gross_wt || row.gross_weight || 0).toFixed(2),
        nw: (row.net_wt || row.net_weight || 0).toFixed(2),
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

// =================================================================
// LAYOUT TEMPLATE (DYNAMIC BY TYPE)
// =================================================================
function get_grid_format(d, type) {
    type = (type || "default").trim().toLowerCase();

    // Determine template type
    var isReliance = type.includes("reliance") || type.includes("relience");
    var isPerfect = type.includes("perfect");
    var isPlainCC = type.includes("plain cc");
    var isPlain = type.includes("plain") && !isPlainCC;
    var isDefault = !isReliance && !isPerfect && !isPlainCC && !isPlain;

    // Header & Subheader Config
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

    // Row Definitions
    var rows = [];

    // ROW 2: GSM & COLOR
    rows.push(`
        <tr>
            <td><span class="lbl">GSM:</span><span class="val">${d.gsm}</span></td>
            <td><span class="lbl">COLOR:</span><span class="val">${d.color}</span></td>
        </tr>
    `);

    // ROW 3: LENGTH & WIDTH/SIZE
    var lenLabel = "Mtrs / Roll";

    var lenVal = d.length + " Mtrs";

    var widthLabel = "width_inch";
    var widthVal = d.width_val;

    if (isPerfect) {
        // Perfect has NO width field
        rows.push(`
            <tr>
                <td colspan="2"><span class="lbl">${lenLabel}:</span><span class="val">${lenVal}</span></td>
            </tr>
        `);
    } else {
        rows.push(`
            <tr>
                <td><span class="lbl">${lenLabel}:</span><span class="val">${lenVal}</span></td>
                <td><span class="lbl">${widthLabel}:</span><span class="val">${widthVal}</span></td>
            </tr>
        `);
    }

    // ROW 4: WEIGHTS
    var wtUnit = " Kgs";
    rows.push(`
        <tr>
            <td><span class="lbl">NET WT:</span><span class="val">${d.nw}${wtUnit}</span></td>
            <td><span class="lbl">GROSS WT:</span><span class="val">${d.gw}${wtUnit}</span></td>
        </tr>
    `);

    return `
    <html>
    <head>
        <title>Label Preview</title>
        <style>
            @media print { .btn-panel { display: none !important; } @page { size: 4in 4in; margin: 0; } body { margin: 0; } }
            body { font-family: 'Arial', sans-serif; margin: 0; padding: 0; text-align: center; background: #eee; }
            .btn-panel { padding: 10px; background: #eee; }
            .sticker { 
                width: 4in; 
                height: 4in; 
                margin: 20px auto; 
                border: 2px solid black; 
                background: white; 
                box-sizing: border-box; 
                display: flex;
                flex-direction: column;
            }
            table { width: 100%; border-collapse: collapse; table-layout: fixed; }
            td { border: 1px solid black; padding: 4px; vertical-align: top; overflow: hidden; }
            
            .header { text-align: center; height: 18mm; vertical-align: middle; padding: 2px 0; }
            .company { font-size: 20px; font-weight: 900; letter-spacing: 0.3px; line-height: 1.1; }
            .email { font-size: 11px; font-weight: bold; color: #333; margin: 1px 0; }
            .subheader { font-size: 12px; font-weight: bold; color: black; }
            .lbl { font-size: 10px; font-weight: bold; color: #444; display: block; }
            .val { font-size: 15px; font-weight: 900; color: #000; display: block; }
            
            .barcode-container { 
                flex-grow: 1;
                display: flex;
                flex-direction: column; 
                justify-content: center;
                align-items: center;
                padding: 5px;
                border-top: 1px solid black;
            }
            #barcode { 
                max-width: 95%; 
                height: 70px; 
            }
            .footer-info { 
                font-size: 13px; 
                font-weight: bold; 
                margin-top: 10px;
                padding-bottom: 5px;
            }
        </style>
    </head>
    <body>
        <div class="btn-panel">
            <button onclick="window.print()" style="padding:10px 20px; font-weight:bold; cursor:pointer;">PRINT</button>
            <button onclick="window.close()" style="padding:10px 20px; margin-left:10px;">CLOSE</button>
        </div>
        <div class="sticker">
            <table>
                <tr>
                    <td colspan="2" class="header">
                        <div class="company">${header}</div>
                        <div class="${isDefault ? 'email' : 'subheader'}">${sub1}</div>
                        ${sub2 ? `<div class="subheader">${sub2}</div>` : ''}
                    </td>
                </tr>
                <tr><td colspan="2" style="text-align:center;"><span class="lbl">ITEM:</span><span class="val">${d.item_code}</span></td></tr>
                ${rows.join('')}
            </table>
            <div class="barcode-container">
                <svg id="barcode"></svg>
                <div class="footer-info">
                    BATCH: ${d.batch_no} | ROLL: ${d.roll_no}
                </div>
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.0/dist/JsBarcode.all.min.js"></script>
        <script>
            JsBarcode("#barcode", "${d.barcode_data}", {
                format: "CODE128",
                displayValue: false,
                height: 70,
                width: 2.0,
                margin: 0
            });
        </script>
    </body>
    </html>`;
}

// =================================================================
// HELPERS
// =================================================================
function trigger_submission(frm) {
    frappe.dom.freeze('Syncing...');
    frappe.call({
        method: 'production_entry.production_entry.doctype.roll_production_entry.roll_production_entry.execute_production',
        args: { roll_entry: frm.doc.name },
        callback: function (r) {
            frappe.dom.unfreeze();
            if (r.message && r.message.success) {
                frappe.msgprint({ title: __('Success'), message: r.message.stock_entry, indicator: 'green' });
                frm.reload_doc();
            }
        },
        error: () => frappe.dom.unfreeze()
    });
}

function calculate_total(frm) {
    let total_qty = 0;
    (frm.doc.items || []).forEach(row => {
        total_qty += flt(row.net_weight || row.net_wt || 0);
    });
    frm.set_value('actual_qty', total_qty);
}

function render_job_sections(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        // Remove headers if grid is empty
        if (frm.fields_dict['items'] && frm.fields_dict['items'].grid && frm.fields_dict['items'].grid.wrapper) {
            let grid_wrapper = frm.fields_dict['items'].grid.wrapper;
            grid_wrapper.find('.job-section-header').remove();
        }
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

    if (!frm.fields_dict['items'] || !frm.fields_dict['items'].grid) return;

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

