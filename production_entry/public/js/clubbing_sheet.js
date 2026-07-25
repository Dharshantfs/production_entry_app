function show_rolls_dialog_JSB(frm, args) {
    let rolls = args.rolls;
    let so_name = args.sales_order;

    let html = '<style>' +
        '.rolls-view { font-family: Arial, sans-serif !important; color: #000 !important; background: #fff !important; padding: 0; }' +
        '.printable-area { width: 100%; max-width: 800px; margin: 0 auto; }' +
        '.company-header-table { width: 100%; border-collapse: collapse; border: 2px solid #2e7d32; margin-bottom: 10px; table-layout: fixed; }' +
        '.company-header-table td { padding: 10px; text-align: center; vertical-align: middle; }' +
        '.company-header-table img { height: 60px; width: auto; margin-bottom: 5px; }' +
        '.company-header-table h1 { font-size: 22px; font-weight: 900; margin: 0; text-transform: uppercase; color: #000; }' +
        '.company-header-table .doc-title { font-size: 11px; font-weight: bold; text-transform: uppercase; border-top: 1px solid #ccc; margin-top: 5px; padding-top: 5px; }' +
        '.info-row-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; table-layout: fixed; }' +
        '.info-row-table td { border: 1px solid #555 !important; padding: 0; text-align: center; }' +
        '.info-box { height: 100%; display: block; }' +
        '.info-label { background: #f57f17 !important; color: #fff !important; font-size: 8px; font-weight: 700; text-transform: uppercase; padding: 2px 5px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }' +
        '.info-value { font-size: 11px; font-weight: 700; padding: 4px 5px; }' +
        '.dt-table { width: 100%; border-collapse: collapse; border: 1px solid #000 !important; font-size: 10px; }' +
        '.dt-table th { background: #ffb74d !important; border: 1px solid #000 !important; padding: 6px; font-weight: 700; text-transform: uppercase; -webkit-print-color-adjust: exact; print-color-adjust: exact; }' +
        '.dt-table td { border: 1px solid #000 !important; padding: 5px 6px; text-align: center; vertical-align: middle; }' +
        '.dt-table tfoot td { background: #c8e6c9 !important; border: 1px solid #000 !important; font-weight: bold; color: #1b5e20 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }' +
        '.tr { text-align: right !important; }' +
        '.fb { font-weight: 700 !important; }' +
        '@media print { .modal-header, .modal-footer { display: none !important; } .printable-area { width: 100% !important; margin: 0 !important; padding: 0 !important; } body { background: #fff !important; } }' +
        '</style>';

    html += '<div class="rolls-view printable-area" id="printable-rolls-area">';
    html += '<table class="company-header-table"><tr><td>' +
        '<img src="/private/files/JSB LOGO63b225.png" alt="JSB Logo"><br>' +
        '<h1>Jayashree Spun Bond</h1>' +
        '<div class="doc-title">Despatch Roll List | SO: ' + so_name + '</div>' +
        '</td></tr></table>';

    html += '<table class="info-row-table"><tr>' +
        '<td><div class="info-box"><div class="info-label">Date</div><div class="info-value">' + frappe.datetime.nowdate() + '</div></div></td>' +
        '<td><div class="info-box"><div class="info-label">Order Code</div><div class="info-value">' + so_name + '</div></div></td>' +
        '<td><div class="info-box"><div class="info-label">No. of Rolls</div><div class="info-value">' + rolls.length + '</div></div></td>' +
        '<td><div class="info-box"><div class="info-label">Report Type</div><div class="info-value">Order-Wise</div></div></td>' +
        '</tr></table>';

    html += '<table class="dt-table"><thead><tr>' +
        '<th>#</th><th>Batch No</th><th>Quality</th><th>Color</th><th>GSM</th><th>Size (")</th>' +
        '<th>Mtrs</th><th>Net Wt</th><th>Gross Wt</th>' +
        '</tr></thead><tbody>';

    let total_mtr = 0, total_net = 0, total_gross = 0;
    for (let i = 0; i < rolls.length; i++) {
        let r = rolls[i];
        let mtr = flt(r.meter_roll || r.meter_per_roll);
        let net = flt(r.net_weight);
        let gross = flt(r.gross_weight || (r.net_weight + 2));
        total_mtr += mtr;
        total_net += net;
        total_gross += gross;
        html += '<tr>' +
            '<td>' + (i + 1) + '</td>' +
            '<td class="fb">' + (r.batch_no || '') + '</td>' +
            '<td>' + (r.quality || '') + '</td>' +
            '<td>' + (r.color || '') + '</td>' +
            '<td>' + (r.gsm || '') + '</td>' +
            '<td>' + (r.width_inch || (r.width_mm ? (flt(r.width_mm) / 25.4).toFixed(1) : '-')) + '</td>' +
            '<td class="tr">' + mtr.toFixed(1) + '</td>' +
            '<td class="tr">' + net.toFixed(2) + '</td>' +
            '<td class="tr">' + gross.toFixed(2) + '</td>' +
            '</tr>';
    }

    html += '</tbody><tfoot><tr>' +
        '<td colspan="6" class="tr fb">TOTAL CONSOLIDATED DESPATCH</td>' +
        '<td class="tr">' + total_mtr.toFixed(1) + '</td>' +
        '<td class="tr">' + total_net.toFixed(2) + '</td>' +
        '<td class="tr">' + total_gross.toFixed(2) + '</td>' +
        '</tr></tfoot></table></div>';

    let d = new frappe.ui.Dialog({
        title: __('Rolls for Sales Order: {0}', [so_name]),
        fields: [{ fieldtype: 'HTML', fieldname: 'rolls_html', options: html }],
        size: 'extra-large',
        primary_action_label: __('Print for Despatch'),
        primary_action: function () {
            let print_window = window.open('', '_blank');
            print_window.document.write('<html><head><title>Roll List</title>');
            print_window.document.write('<style>@page { size: A4 portrait; margin: 10mm; }</style>');
            print_window.document.write(html);
            print_window.document.write('</body></html>');
            print_window.document.close();
            setTimeout(() => {
                print_window.print();
                print_window.close();
            }, 500);
        }
    });
    d.show();
}

const ROUTE_BELTS = [
    ["madurai", "virudhunagar", "sivakasi", "tuticorin"],
    ["madurai", "karur", "coimbatore"],
    ["madurai", "karur", "erode", "salem"],
    ["madurai", "dindigul", "karur", "salem"],
    ["madurai", "pondicherry", "vellore", "kanchipuram", "chennai"],
    ["madurai", "trivandrum", "changanacherry"],
    ["madurai", "kollam", "kayankulam", "pathanamthitta", "kottayam"],
    ["madurai", "coimbatore", "palakkad", "trissur", "ernakulam"],
    ["madurai", "coimbatore", "pallakad", "trissur", "malappuram", "kozhikode", "mahe", "kannur", "kasargod", "mangaluru", "uduppi"],
    ["madurai", "mysore", "hassan", "shimoga", "dawangeree"],
    ["madurai", "salem", "hosur", "bangalore", "dawangeree"],
    ["madurai", "mysore", "bangalore"],
    ["madurai", "bangalore", "tumkur", "hospet", "koppal"],
    ["madurai", "ananthapur", "kurnool", "hyderabad", "karimnagar"],
    ["madurai", "ananthapur", "kurnool", "hyderabad", "nizambad"],
    ["madurai", "kurnool", "hyderabad", "warangal"],
    ["madurai", "vizag", "bhuvaneswar", "cuttack"],
    ["madurai", "brahmbur", "bhubaneswar", "cuttack"],
    ["madurai", "guntur", "vijayawada", "kakinada"],
    ["madurai", "kakinada", "vizag"],
    ["madurai", "kuppam", "palamaner", "bangalore"],
    ["madurai", "bangalore", "hospete", "vijayapura"],
    ["madurai", "bangalore", "belgaum", "goa"],
    ["madurai", "bangalore", "hospete", "vijayapura", "satara", "pune", "mumbai"]
];

const MADURAI_DISTANCES = {
    "Madurai": 0, "Melur": 30, "Usilampatti": 45, "Manamadurai": 60, "Sivaganga": 55,
    "Dindigul": 65, "Virudhunagar": 65, "Theni": 70, "Srivilliputhur": 75, "Aruppukottai": 80,
    "Sivakasi": 80, "Periyakulam": 85, "Tiruppathur": 90, "Oddanchatram": 95, "Sattur": 95,
    "Cumbum": 90, "Pudukkottai": 100, "Rajapalayam": 100, "Paramakudi": 130, "Kovilpatti": 130,
    "Palani": 120, "Ramanathapuram": 115, "Kodaikanal": 115, "Thenkasi": 115, "Tenkasi": 115,
    "Courtallam": 120, "Sankarankoil": 125, "Kumily": 130, "Gudalur": 130, "Munnar": 140,
    "Idukki": 145, "Karur": 140, "Tiruchirappalli": 135, "Trichy": 135, "Tirunelveli": 155,
    "Thoothukudi": 160, "Tuticorin": 160, "Perambalur": 160, "Ariyalur": 175, "Thanjavur": 175,
    "Pollachi": 180, "Kottayam": 185, "Namakkal": 200, "Alappuzha": 200, "Alleppey": 200,
    "Thodupuzha": 205, "Padmanabhapuram": 205, "Coimbatore": 210, "Tirupur": 215, "Kumbakonam": 215,
    "Ernakulam": 220, "Kochi": 220, "Cochin": 220, "Salem": 220, "Nagercoil": 230, "Erode": 240,
    "Pala": 195, "Changanacherry": 195, "Pathanamthitta": 215, "Kollam": 250, "Quilon": 250,
    "Palakkad": 250, "Mayiladuthurai": 250, "Kanyakumari": 250, "Nilgiris": 265, "Ooty": 265,
    "Nagapattinam": 280, "Thrissur": 280, "Thiruvananthapuram": 290, "Trivandrum": 290,
    "Malappuram": 320, "Dharmapuri": 320, "Wayanad": 345, "Cuddalore": 365, "Kozhikode": 360,
    "Calicut": 360, "Villupuram": 370, "Mysuru": 370, "Mysore": 370, "Hosur": 385,
    "Pondicherry": 395, "Puducherry": 395, "Hassan": 395, "Vellore": 410, "Kanchipuram": 440,
    "Chengalpattu": 420, "Kannur": 430, "Bengaluru": 445, "Bangalore": 445, "Chennai": 455,
    "Tumkur": 475, "Mangaluru": 490, "Mangalore": 490, "Shimoga": 485, "Davangere": 510,
    "Udupi": 530, "Guntur": 650, "Vijayawada": 680, "Hyderabad": 770, "Warangal": 850,
    "Vizag": 970, "Bhubaneswar": 1650, "Cuttack": 1680, "Krishnagiri": 355, "Pune": 1250, "Mumbai": 1450,
    "Karaikudi": 95
};

function get_distance_from_madurai(city) {
    if (!city) return 0;
    if (MADURAI_DISTANCES[city] !== undefined) return MADURAI_DISTANCES[city];
    let lower = city.toLowerCase();
    for (let key in MADURAI_DISTANCES) {
        if (key.toLowerCase() === lower) return MADURAI_DISTANCES[key];
    }
    for (let key in MADURAI_DISTANCES) {
        if (lower.includes(key.toLowerCase()) || key.toLowerCase().includes(lower)) {
            return MADURAI_DISTANCES[key];
        }
    }
    return 0;
}

const PLANNING_ORDERS_API = 'production_entry.production_planning.clubbing_api.get_planning_orders_for_clubbing';
const DISTANCES_API = 'production_entry.production_planning.clubbing_api.get_distances_from_madurai';
window.JSB_CLUB_PICKER_VER = 'v20260725c';

/** Add selected Planning rows into Clubbing Sheet items. Defined early so old Client Scripts can call it. */
window._jsb_club_process_selections = function (frm, selections, orders_cache) {
	const apply_picked = function (all) {
		let picked = (all || []).filter(o =>
			selections.includes(o.name) ||
			selections.includes(o.planning_table_row)
		);
		if (!picked.length) {
			frappe.msgprint(__('No matching Planning Table rows for selection.'));
			return;
		}

		let item_meta = frappe.get_meta('Clubbing Sheet Item') || {};
		let has_field = (fn) => !!(item_meta.fields || []).find(f => f.fieldname === fn);

		let rows = [];
		picked.forEach(so => {
			let row = frm.add_child('items');
			let rd = locals[row.doctype][row.name];
			rd.customer = so.customer;
			rd.customer_name = so.customer_name || so.customer;
			rd.sales_order = so.sales_order || '';
			rd.party_code = so.party_code || so.custom_party_code || '';
			rd.weight_kgs = flt(so.weight_kgs || so.total_qty);
			rd.no_of_rolls = flt(so.no_of_rolls);
			rd.party_location = so.city || '';
			rd.custom_planning_table_row = so.planning_table_row || so.name || '';
			rd.custom_planning_sheet = so.planning_sheet || '';
			if (has_field('planning_table_row')) {
				rd.planning_table_row = so.planning_table_row || so.name || '';
			}
			if (has_field('planning_sheet')) {
				rd.planning_sheet = so.planning_sheet || '';
			}
			if (has_field('quality')) rd.quality = so.quality || '';
			if (has_field('color')) rd.color = so.color || '';
			if (has_field('gsm')) rd.gsm = so.gsm || 0;
			if (has_field('custom_quality')) rd.custom_quality = so.quality || '';
			if (has_field('custom_color')) rd.custom_color = so.color || '';
			if (has_field('custom_gsm')) rd.custom_gsm = so.gsm || 0;
			if (has_field('planned_date')) rd.planned_date = so.planned_date || '';
			if (has_field('custom_planned_date')) rd.custom_planned_date = so.planned_date || '';
			if (has_field('width_inch')) rd.width_inch = so.width_inch || so.inch || 0;
			if (has_field('custom_width_inch')) rd.custom_width_inch = so.width_inch || so.inch || 0;
			rows.push(rd);
		});
		frm.refresh_field('items');
		frm.doc.total_weight = rows.reduce((s, r) => s + flt(r.weight_kgs), 0);
		frm.refresh_field('total_weight');

		let cities = [...new Set(rows.map(r => r.party_location).filter(Boolean))];

		function applyAndSave(distanceMap) {
			rows.forEach(row => {
				let dist = distanceMap[row.party_location];
				row.distance_from_madurai = dist !== undefined ? dist : get_distance_from_madurai(row.party_location);
			});
			frm.trigger('recalculate_load_type');
			frm.refresh_field('items');
		}

		if (!cities.length) {
			frm.trigger('recalculate_load_type');
			return;
		}

		frappe.call({
			method: DISTANCES_API,
			args: { cities: cities },
			callback: (res) => applyAndSave(res.message || {}),
			error: () => {
				let fallback = {};
				cities.forEach(c => fallback[c] = get_distance_from_madurai(c));
				applyAndSave(fallback);
			}
		});
	};

	if (orders_cache && orders_cache.length) {
		apply_picked(orders_cache);
		return;
	}

	frappe.call({
		method: PLANNING_ORDERS_API,
		freeze: true,
		callback: function (r) {
			apply_picked(r.message || []);
		}
	});
};

function jsb_club_wire_process_selections(frm) {
	const handler = function (frm2, selections, planned_date) {
		window._jsb_club_process_selections(frm2 || frm, selections, null);
	};
	if (frm.script_manager && frm.script_manager.events) {
		frm.script_manager.events.process_selections = [handler];
	}
	if (!frm.events) frm.events = {};
	frm.events.process_selections = handler;
	if (frm.cscript) {
		frm.cscript.process_selections = handler;
	}
}

function jsb_club_bind_picker_button(frm) {
	const openOnce = function (e) {
		if (e && e.preventDefault) {
			e.preventDefault();
			e.stopImmediatePropagation();
		}
		try {
			jsb_club_open_despatch_picker(frm);
		} catch (err) {
			console.error('[Clubbing] open picker failed', err);
			frappe.msgprint(__('Could not open order picker: {0}', [err.message || String(err)]));
		}
		return false;
	};
	jsb_club_wire_process_selections(frm);

	// One form button only — hide duplicate toolbar button that caused double popup
	['get_sales_orders', 'get_sales_orders_dialog'].forEach(function (fn) {
		if (frm.fields_dict && frm.fields_dict[fn]) {
			frm.set_df_property(fn, 'hidden', 0);
		}
	});
	try {
		frm.remove_custom_button(__('Get Planning Items'));
	} catch (e) { /* ignore */ }

	if (frm.script_manager && frm.script_manager.events) {
		frm.script_manager.events.get_sales_orders = [openOnce];
		frm.script_manager.events.get_sales_orders_dialog = [openOnce];
	}
	if (!frm.events) frm.events = {};
	frm.events.get_sales_orders = openOnce;
	frm.events.get_sales_orders_dialog = openOnce;
	if (frm.cscript) {
		frm.cscript.get_sales_orders = openOnce;
		frm.cscript.get_sales_orders_dialog = openOnce;
	}

	['get_sales_orders', 'get_sales_orders_dialog'].forEach(function (fname) {
		try {
			const fld = frm.get_field(fname);
			if (!fld || !fld.$wrapper) return;
			const $btn = fld.$wrapper.find('button, .btn').first();
			if (!$btn.length) return;
			$btn.off('click.jsbclub').on('click.jsbclub', openOnce);
		} catch (e2) { /* ignore */ }
	});
}

function jsb_club_open_despatch_picker(frm) {
	if (!frm) return;

	// Hard single-open: if dialog already up, focus it — never open a second
	if (window._jsb_club_dialog && window._jsb_club_dialog.$wrapper && window._jsb_club_dialog.$wrapper.is(':visible')) {
		return;
	}
	const now = Date.now();
	if (window._jsb_club_picker_last && (now - window._jsb_club_picker_last) < 1200) {
		return;
	}
	window._jsb_club_picker_last = now;

	if (typeof window._jsb_club_picker_impl !== 'function') {
		frappe.msgprint(__(
			'Clubbing picker missing. Paste latest PASTE_clubbing_client_script.js into Client Script and Save.'
		));
		return;
	}
	window._jsb_club_picker_impl(frm);
}

frappe.ui.form.on('Clubbing Sheet', {
    refresh: function (frm) {
        jsb_club_bind_picker_button(frm);
        // One delayed rebind in case DocType custom buttons render late
        setTimeout(function () { jsb_club_bind_picker_button(frm); }, 300);

        if (!frm.doc.__islocal && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Submit'), function () {
                frm.trigger('submit_with_trip_id');
            }, __('Actions'));
        }

        frm.trigger('show_load_type_indicator');
        frm.trigger('toggle_loading_sequence_visibility');
        frm.trigger('set_vehicle_no_options');
    },

    vehicle_feet: function (frm) {
        frm.trigger('set_vehicle_no_options');
        frm.set_value('vehicle_no', '');
    },

    set_vehicle_no_options: function (frm) {
        if (!frm.doc.vehicle_feet) {
            frm.set_df_property('vehicle_no', 'options', []);
            return;
        }
        const VEHICLE_MAP = {
            "20": ["TN 64 T 2207", "TN 64 U 0093", "TN 64 V 2054", "TN 64 AE 1904", "TN 64 AE 1976"],
            "21": ["TN 64 V 3522", "TN 64 V 4066", "TN 64 V 4258"],
            "22": ["TN 64 V 3016", "TN 64 V 3619", "TN 64 V 3083", "TN 64 V 8409", "TN 64 V 8437"],
            "24": ["TN 64 W 9289", "TN 64 W 9767", "TN 64 X 4926", "TN 64 X 4944", "TN 64 X 6939", "TN 64 Y 1944", "TN 64 Y 1982", "TN 64 Y 1993", "TN 64 Y 8719", "TN 64 Y 8731", "TN 64 Y 8782", "TN 64 Z 1720", "TN 64 Z 1748"],
            "32": ["TN 64 V 8852", "TN 64 W 8825"],
            "Bolero": ["TN 64 W 6736"]
        };
        let feet_str = frm.doc.vehicle_feet.toString();
        if (VEHICLE_MAP[feet_str]) {
            frm.set_df_property('vehicle_no', 'options', [""].concat(VEHICLE_MAP[feet_str]));
            return;
        }
        let match = feet_str.match(/\d+/);
        if (match && VEHICLE_MAP[match[0]]) {
            frm.set_df_property('vehicle_no', 'options', [""].concat(VEHICLE_MAP[match[0]]));
        } else {
            frm.set_df_property('vehicle_no', 'options', []);
        }
    },

    submit_with_trip_id: function (frm) {
        if (!frm.doc.trip_id) {
            frappe.prompt(
                [{ fieldname: 'trip_id', fieldtype: 'Data', label: 'Trip ID', reqd: 1 }],
                (values) => {
                    frappe.model.set_value(frm.doctype, frm.docname, 'trip_id', values.trip_id);
                    frm.save().then(() => {
                        frappe.ui.form.save(frm, 'Submit');
                    });
                },
                __('Enter Trip ID to Submit'),
                __('Submit')
            );
        } else {
            frappe.confirm(
                __('Submit this Clubbing Sheet with Trip ID: <b>') + frm.doc.trip_id + '</b>?',
                () => frappe.ui.form.save(frm, 'Submit')
            );
        }
    },

    get_sales_orders: function (frm) {
        jsb_club_open_despatch_picker(frm);
    },

    get_sales_orders_dialog: function (frm) {
        jsb_club_open_despatch_picker(frm);
    },

    show_load_type_indicator: function (frm) {
        frm.page.wrapper.find('.form-message.blue, .form-message.orange, .form-message.red').remove();

        let customer_weights = {};
        let selected_cities = new Set();
        (frm.doc.items || []).forEach(i => {
            if (i.customer) {
                customer_weights[i.customer] = (customer_weights[i.customer] || 0) + flt(i.weight_kgs);
            }
            if (i.party_location) {
                selected_cities.add(i.party_location.trim().toLowerCase());
            }
        });

        let customers = Object.keys(customer_weights);
        let full_load_customers = customers.filter(c => customer_weights[c] >= 5000);

        let is_valid = true;
        if (selected_cities.size > 0) {
            is_valid = false;
            for (let belt of ROUTE_BELTS) {
                let all_in_belt = true;
                for (let city of selected_cities) {
                    if (!belt.includes(city)) {
                        all_in_belt = false;
                        break;
                    }
                }
                if (all_in_belt) {
                    is_valid = true;
                    break;
                }
            }
        }

        if (!is_valid && !frm.doc.ignore_route_conflict) {
            frm.set_intro(__("ROUTE CONFLICT — cities do not fall on one forward route/belt. Check Ignore Route Conflict to override."), "red");
        } else if (full_load_customers.length > 0 && customers.length > 1) {
            frm.set_intro(__("FULL LOAD VIOLATION — Customer {0} has {1} kgs (>= 5000). Must be dedicated vehicle.", [full_load_customers[0], customer_weights[full_load_customers[0]]]), "red");
        } else if (frm.doc.load_type === "Full Load") {
            frm.set_intro(__("Full Load — dedicated vehicle."), "blue");
        } else if (frm.doc.load_type === "Part Load") {
            frm.set_intro(customers.length > 1 ? __("Part Load — multiple orders clubbed.") : __("Part Load — needs clubbing."), "orange");
        }
    },

    load_type: function (frm) {
        frm.trigger('show_load_type_indicator');
        frm.trigger('toggle_loading_sequence_visibility');
        frm.trigger('calculate_loading_sequence');
    },

    toggle_loading_sequence_visibility: function (frm) {
        let show = (frm.doc.load_type === 'Part Load' || frm.doc.load_type === 'Full Load');
        frm.get_field('items').grid.set_column_disp('loading_sequence', show);
    },

    recalculate_load_type: function (frm) {
        let customer_weights = {};
        let selected_cities = new Set();
        (frm.doc.items || []).forEach(i => {
            if (i.customer) {
                customer_weights[i.customer] = (customer_weights[i.customer] || 0) + flt(i.weight_kgs);
            }
            if (i.party_location) {
                selected_cities.add(i.party_location.trim().toLowerCase());
            }
        });

        let customers = Object.keys(customer_weights);
        let has_full_load_order = Object.values(customer_weights).some(w => w >= 5000);

        let is_valid = true;
        if (selected_cities.size > 0) {
            is_valid = false;
            for (let belt of ROUTE_BELTS) {
                let all_in_belt = true;
                for (let city of selected_cities) {
                    if (!belt.includes(city)) {
                        all_in_belt = false;
                        break;
                    }
                }
                if (all_in_belt) {
                    is_valid = true;
                    break;
                }
            }
        }

        if (!is_valid && !frm.doc.ignore_route_conflict) {
            frm.set_value('load_type', '');
        } else if (has_full_load_order) {
            frm.set_value('load_type', 'Full Load');
        } else if (customers.length >= 1) {
            frm.set_value('load_type', 'Part Load');
        } else {
            frm.set_value('load_type', '');
        }

        frm.trigger('show_load_type_indicator');
        frm.trigger('toggle_loading_sequence_visibility');
        frm.trigger('calculate_loading_sequence');
    },

    jsb_pick_despatch_planning_rows: function (frm) {
        window._jsb_club_picker_impl(frm);
    },
});

// Actual dialog — also exposed so Get Sales Orders works even if trigger chain is empty
window._jsb_club_picker_impl = function (frm) {
        // Never stack two dialogs (app JS + Client Script both calling open)
        if (window._jsb_club_dialog && window._jsb_club_dialog.$wrapper && window._jsb_club_dialog.$wrapper.is(':visible')) {
            return;
        }
        try {
            $('.modal.jsb-club-picker, .jsb-club-picker').closest('.modal').modal('hide');
        } catch (e0) { /* ignore */ }

        let d = new frappe.ui.Dialog({
            title: __('Select Planning Despatch Rows') + ' · ' + (window.JSB_CLUB_PICKER_VER || ''),
            size: 'extra-large',
            fields: [
                { fieldtype: 'Section Break', label: __('Filters') },
                { fieldtype: 'Date', fieldname: 'planned_date', label: __('Planned Date'), reqd: 0 },
                { fieldtype: 'Column Break' },
                { fieldtype: 'Data', fieldname: 'search_order', label: __('Order ID'), onchange: () => refresh_list() },
                { fieldtype: 'Section Break' },
                { fieldtype: 'Data', fieldname: 'search_customer', label: __('Customer'), onchange: () => refresh_list() },
                { fieldtype: 'Column Break' },
                { fieldtype: 'Data', fieldname: 'search_city', label: __('City / Route'), onchange: () => refresh_list() },
                { fieldtype: 'Section Break' },
                { fieldtype: 'Data', fieldname: 'search_party', label: __('Party Code'), onchange: () => refresh_list() },
                { fieldtype: 'Column Break' },
                { fieldtype: 'Button', fieldname: 'btn_reload', label: __('Reload') },
                { fieldtype: 'Section Break' },
                { fieldtype: 'HTML', fieldname: 'list_area' }
            ],
            primary_action_label: __('Get Items'),
            primary_action(values) {
                let selected = Array.from(selected_orders);
                if (selected.length === 0) {
                    frappe.msgprint(__('Please select at least one planning row'));
                    return;
                }
                d.hide();
                window._jsb_club_dialog = null;
                try {
                    window._jsb_club_process_selections(frm, selected, orders);
                } catch (err) {
                    console.error('[Clubbing] Get Items failed', err);
                    frappe.msgprint(__('Could not add items: {0}', [err.message || String(err)]));
                }
            }
        });

        window._jsb_club_dialog = d;
        d.$wrapper.addClass('jsb-club-picker');
        if (!document.getElementById('jsb-club-picker-css')) {
            let style = document.createElement('style');
            style.id = 'jsb-club-picker-css';
            style.textContent = `
                .jsb-club-picker .modal-content { border-radius: 14px; border: 1px solid #cbd5e1; box-shadow: 0 18px 50px rgba(15,23,42,.18); overflow: hidden; }
                .jsb-club-picker .modal-header { background: linear-gradient(180deg,#0f172a,#1e293b); color: #fff; border-bottom: none; padding: 14px 18px; }
                .jsb-club-picker .modal-title { color: #fff !important; font-weight: 700; letter-spacing: .02em; }
                .jsb-club-picker .modal-header .btn-modal-close { color: #fff; opacity: .85; }
                .jsb-club-picker .modal-body { background: #f8fafc; padding: 14px 16px 8px; }
                .jsb-club-picker .form-control { border: 1.5px solid #94a3b8; border-radius: 10px; background: #fff; min-height: 34px; }
                .jsb-club-picker .form-control:focus { border-color: #0284c7; box-shadow: 0 0 0 3px rgba(2,132,199,.18); }
                .jsb-club-picker .btn[data-fieldname="btn_reload"] { border-radius: 10px !important; border: 1.5px solid #0ea5e9 !important; background: #e0f2fe !important; color: #0369a1 !important; font-weight: 700 !important; padding: 6px 14px !important; }
                .jsb-club-picker .modal-footer .btn-primary { border-radius: 10px !important; border: none !important; background: #0f172a !important; font-weight: 700 !important; padding: 8px 18px !important; }
                .jsb-club-picker-wrap { max-height: 440px; overflow: auto; border: 1.5px solid #94a3b8; border-radius: 12px; background: #fff; }
                .jsb-club-picker-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
                .jsb-club-picker-table thead th { position: sticky; top: 0; z-index: 1; background: #0f172a; color: #e2e8f0; font-size: 10px; letter-spacing: .04em; text-transform: uppercase; padding: 10px 8px; border-bottom: 1px solid #334155; white-space: nowrap; }
                .jsb-club-picker-table tbody td { padding: 9px 8px; border-bottom: 1px solid #e2e8f0; vertical-align: middle; }
                .jsb-club-picker-table tbody tr:hover { background: #f0f9ff; }
                .jsb-club-picker-table .jsb-pill { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #e0f2fe; color: #0369a1; font-weight: 700; font-size: 11px; }
                .jsb-club-picker-table .jsb-attr { font-weight: 700; color: #0f172a; }
                .jsb-club-picker-hint { margin: 0 0 10px; color: #475569; font-size: 12px; }
            `;
            document.head.appendChild(style);
        }

        let orders = [];
        let selected_orders = new Set();

        d.$wrapper.on('change', '.so-checkbox', function () {
            let name = $(this).data('name');
            if (!name) return;
            if ($(this).prop('checked')) selected_orders.add(name);
            else selected_orders.delete(name);
        });

        d.$wrapper.on('change', '.so-select-all', function () {
            let is_checked = $(this).prop('checked');
            d.$wrapper.find('.so-checkbox').each(function () {
                $(this).prop('checked', is_checked);
                let name = $(this).data('name');
                if (!name) return;
                if (is_checked) selected_orders.add(name);
                else selected_orders.delete(name);
            });
        });

        let refresh_list = () => {
            let s_order = (d.get_value('search_order') || '').toLowerCase();
            let s_cust = (d.get_value('search_customer') || '').toLowerCase();
            let s_city = (d.get_value('search_city') || '').toLowerCase();
            let s_party = (d.get_value('search_party') || '').toLowerCase();

            let filtered = orders.filter(o =>
                (!s_order || (o.name || '').toLowerCase().includes(s_order) || (o.party_code || '').toLowerCase().includes(s_order) || (o.sales_order || '').toLowerCase().includes(s_order) || (o.planning_sheet || '').toLowerCase().includes(s_order) || (o.item_code || '').toLowerCase().includes(s_order) || (o.quality || '').toLowerCase().includes(s_order) || (o.color || '').toLowerCase().includes(s_order)) &&
                (!s_cust || (o.customer || '').toLowerCase().includes(s_cust) || (o.customer_name || '').toLowerCase().includes(s_cust)) &&
                (!s_city || (o.city || '').toLowerCase().includes(s_city)) &&
                (!s_party || (o.custom_party_code || o.party_code || '').toLowerCase().includes(s_party))
            );

            let inchVal = (o) => {
                let v = flt(o.width_inch || o.inch || 0);
                return v > 0 ? v : '—';
            };

            let html = `
                <p class="jsb-club-picker-hint">${__('Quality · Color · GSM · Width(Inch) — tick the exact Planning lines.')} <b>${window.JSB_CLUB_PICKER_VER || ''}</b></p>
                <div class="jsb-club-picker-wrap">
                <table class="jsb-club-picker-table">
                    <thead>
                        <tr>
                            <th style="width: 36px; text-align: center;"><input type="checkbox" class="so-select-all"></th>
                            <th>${__('Order')}</th>
                            <th>${__('Item')}</th>
                            <th>${__('Quality')}</th>
                            <th>${__('Color')}</th>
                            <th>${__('GSM')}</th>
                            <th>${__('Width (Inch)')}</th>
                            <th>${__('Planned')}</th>
                            <th>${__('City')}</th>
                            <th class="text-right">${__('Wt / Rolls')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${filtered.length === 0 ? `<tr><td colspan="10" class="text-center text-muted" style="padding:24px;">${__('No Despatch planning rows')}</td></tr>` :
                filtered.map(o => `
                            <tr>
                                <td style="text-align: center;"><input type="checkbox" class="so-checkbox" data-name="${frappe.utils.escape_html(o.name)}" ${selected_orders.has(o.name) ? 'checked' : ''}></td>
                                <td><b>${frappe.utils.escape_html(o.party_code || o.sales_order || o.name)}</b><br><span class="text-muted small">${frappe.utils.escape_html(o.sales_order || '')}</span><br><span class="text-muted small">${frappe.utils.escape_html(o.planning_sheet || '')}</span></td>
                                <td><span class="text-muted small">${frappe.utils.escape_html(o.item_code || '')}</span></td>
                                <td class="jsb-attr">${frappe.utils.escape_html(o.quality || '—')}</td>
                                <td class="jsb-attr">${frappe.utils.escape_html(o.color || '—')}</td>
                                <td class="jsb-attr">${o.gsm || '—'}</td>
                                <td class="jsb-attr">${inchVal(o)}</td>
                                <td>${frappe.utils.escape_html(o.planned_date || '')}</td>
                                <td><span class="jsb-pill">${frappe.utils.escape_html(o.city || '—')}</span></td>
                                <td class="text-right">${o.total_qty || 0}<br><span class="text-muted small">${o.no_of_rolls || 0} rolls</span></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                </div>`;
            d.get_field('list_area').$wrapper.html(html);
        };

        let load_orders = () => {
            selected_orders.clear();
            frappe.call({
                method: PLANNING_ORDERS_API,
                args: {
                    planned_date: d.get_value('planned_date') || '',
                    party_code: d.get_value('search_party') || d.get_value('search_order') || '',
                    customer: d.get_value('search_customer') || '',
                    city: d.get_value('search_city') || ''
                },
                freeze: true,
                freeze_message: __('Loading Despatch planning rows...'),
                callback: (r) => {
                    orders = r.message || [];
                    refresh_list();
                }
            });
        };

        d.fields_dict.planned_date.$input.on('change', () => load_orders());
        if (d.fields_dict.btn_reload && d.fields_dict.btn_reload.$input) {
            d.fields_dict.btn_reload.$input.on('click', () => load_orders());
        }
        load_orders();
        d.show();
        d.$wrapper.on('hidden.bs.modal', function () {
            window._jsb_club_dialog = null;
            window._jsb_club_picker_lock = false;
            frm._jsb_club_picker_open = false;
        });
};

frappe.ui.form.on('Clubbing Sheet', {
    process_selections: function (frm, selections, planned_date) {
        window._jsb_club_process_selections(frm, selections, null);
    },

    total_weight: function (frm) {
        frm.trigger('show_load_type_indicator');
    },

    calculate_loading_sequence: function (frm) {
        let items = frm.doc.items || [];
        if (!items.length) {
            frm.refresh_field('items');
            return;
        }

        let all_belt_cities = new Set();
        ROUTE_BELTS.forEach(belt => belt.forEach(c => all_belt_cities.add(c)));

        function get_city(item) {
            return (item.party_location || '').trim().toLowerCase();
        }

        let known_cities = new Set();
        items.forEach(item => {
            let city = get_city(item);
            if (!city) return;
            for (let bc of all_belt_cities) {
                if (city === bc || city.includes(bc) || bc.includes(city)) {
                    known_cities.add(city);
                    break;
                }
            }
        });

        let active_belt = null;
        for (let belt of ROUTE_BELTS) {
            let all_match = true;
            for (let city of known_cities) {
                let found = false;
                for (let bc of belt) {
                    if (city === bc || city.includes(bc) || bc.includes(city)) { found = true; break; }
                }
                if (!found) { all_match = false; break; }
            }
            if (all_match && known_cities.size > 0) {
                active_belt = belt;
                break;
            }
        }
        if (!active_belt) {
            let max_matches = 0;
            for (let belt of ROUTE_BELTS) {
                let count = 0;
                for (let city of known_cities) {
                    for (let bc of belt) {
                        if (city === bc || city.includes(bc) || bc.includes(city)) { count++; break; }
                    }
                }
                if (count > max_matches) { max_matches = count; active_belt = belt; }
            }
        }

        function get_sort_key(item) {
            let city = get_city(item);
            if (active_belt) {
                for (let idx = 0; idx < active_belt.length; idx++) {
                    let bc = active_belt[idx];
                    if (city === bc || city.includes(bc) || bc.includes(city)) {
                        return [1, idx];
                    }
                }
            }
            let dist = flt(item.distance_from_madurai) || get_distance_from_madurai(item.party_location);
            return [0, dist];
        }

        items.sort((a, b) => {
            let ka = get_sort_key(a), kb = get_sort_key(b);
            if (ka[0] !== kb[0]) return kb[0] - ka[0];
            return kb[1] - ka[1];
        });

        if (frm.doc.load_type === 'Full Load') {
            items.forEach(item => { item.loading_sequence = 'Full Load'; });
        } else {
            let n = items.length;
            if (n === 1) {
                items[0].loading_sequence = 'Full Load';
            } else if (n === 2) {
                items[0].loading_sequence = 'Inside';
                items[1].loading_sequence = 'Outside';
            } else {
                items[0].loading_sequence = 'Inside';
                items[n - 1].loading_sequence = 'Outside';
                let center_num = 1;
                for (let i = 1; i < n - 1; i++) {
                    items[i].loading_sequence = 'Center ' + center_num;
                    center_num++;
                }
            }
        }

        items.forEach((item, idx) => { item.idx = idx + 1; });
        frm.refresh_field('items');
    }
});

frappe.ui.form.on('Clubbing Sheet Item', {
    view_rolls: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let order_code = row.party_code || row.order_code || row.sales_order;
        let alt_code = row.sales_order || row.party_code;

        if (!order_code) {
            frappe.msgprint(__('Order reference missing. Cannot view rolls.'));
            return;
        }

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Shaft Production Run',
                filters: [
                    ['custom_order_code', 'in', [order_code, alt_code].filter(Boolean)],
                    ['docstatus', '=', 1]
                ],
                fields: ['name', 'custom_unit', 'custom_order_code']
            },
            callback: function (rp) {
                let runs = rp.message || [];
                if (!runs.length) {
                    frappe.msgprint(__('No production records found for this order.'));
                    return;
                }

                let fetch_promises = runs.map(run => new Promise((resolve_fetch) => {
                    frappe.call({
                        method: 'frappe.client.get',
                        args: { doctype: 'Shaft Production Run', name: run.name },
                        callback: (res) => {
                            let doc = res.message || {};
                            let matched_items = (doc.items || []).filter(item => {
                                let item_order = item.party_code || item.custom_order_code;
                                return (item_order === order_code || item_order === alt_code) && flt(item.net_weight) > 0;
                            });
                            matched_items.forEach(item => {
                                item.parent_run = doc.name;
                                item.run_date = doc.run_date || doc.posting_date;
                            });
                            resolve_fetch(matched_items);
                        }
                    });
                }));

                Promise.all(fetch_promises).then((all_item_batches) => {
                    let rolls = [].concat(...all_item_batches);
                    if (!rolls.length) {
                        frappe.msgprint(__('No weighed rolls found for this order.'));
                        return;
                    }
                    show_rolls_dialog_JSB(frm, { rolls: rolls, sales_order: order_code });
                });
            }
        });
    },

    items_remove: function (frm) {
        frm.trigger('recalculate_load_type');
    }
});
