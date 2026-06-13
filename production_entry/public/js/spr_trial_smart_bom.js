/* Trail Order — fabric Smart BOM recipe dialog (process 100: PP / Filler / SA / MB). */
(function () {
	const QUALITY_TIERS = [
		'SUPER ECO', 'ECO SPECIAL', 'ECO SPL', 'ECOGREEN', 'DELUXE', 'ULTRA',
		'PLATINUM', 'PREMIUM', 'LIFESTYLE', 'CLASSIC', 'SILVER', 'GOLD', 'BRONZE',
	];

	let item_name_to_code = {};
	let item_code_to_name = {};
	let categorized = { pp: [], fl: [], sa: [], mb: [] };

	function extractTier(q) {
		const qu = (q || '').toUpperCase();
		for (let i = 0; i < QUALITY_TIERS.length; i++) {
			if (qu.includes(QUALITY_TIERS[i])) return QUALITY_TIERS[i];
		}
		return qu;
	}

	function isPremiumQuality(q) {
		return ((q || '') + '').toUpperCase().includes('PREMIUM');
	}

	function resolveItemCodeAny(val) {
		const s = (val || '').toString().trim();
		if (!s) return '';
		if (item_name_to_code[s]) return item_name_to_code[s];
		const parts = s.split(' - ');
		if (parts.length >= 2 && item_name_to_code[parts[0].trim()]) {
			return item_name_to_code[parts[0].trim()];
		}
		return s;
	}

	function collectRows(d, itemFields, qtyFields, v) {
		const rows = [];
		for (let i = 0; i < itemFields.length; i++) {
			const itemName = v && v[itemFields[i]] !== undefined ? v[itemFields[i]] : d.get_value(itemFields[i]);
			const qty = parseFloat(v && v[qtyFields[i]] !== undefined ? v[qtyFields[i]] : d.get_value(qtyFields[i])) || 0;
			if (itemName && qty > 0) {
				rows.push({ item_code: resolveItemCodeAny(itemName), qty: qty });
			}
		}
		return rows;
	}

	function getFilteredPP(q, gsm) {
		const tier = extractTier(q);
		const g = parseFloat(gsm) || 0;
		const HIGH_END = ['DELUXE', 'ULTRA', 'SUPER ECO', 'ECOGREEN', 'ECO SPECIAL', 'ECO SPL'];
		let kwList;
		if (HIGH_END.some(function (x) { return tier.includes(x); })) {
			kwList = ['POLYMAXX', 'RELIANCE', 'EXXON', 'BASELL'];
		} else if (g > 30) {
			kwList = ['POLYMAXX', 'RELIANCE', 'EXXON', 'BASELL'];
		} else if (g >= 20) {
			kwList = ['RELIANCE', 'EXXON', 'BASELL'];
		} else {
			kwList = ['EXXON', 'BASELL'];
		}
		const result = [];
		kwList.forEach(function (kw) {
			const found = categorized.pp.find(function (n) { return n.toUpperCase().includes(kw); });
			if (found && result.indexOf(found) === -1) result.push(found);
		});
		categorized.pp.filter(function (n) { return n.toUpperCase().includes('DANA'); }).forEach(function (d) {
			if (result.indexOf(d) === -1) result.push(d);
		});
		categorized.pp.filter(function (n) { return result.indexOf(n) === -1; }).forEach(function (r) {
			result.push(r);
		});
		return result;
	}

	function getFilteredFiller(q) {
		if (isPremiumQuality(q)) return [];
		const target_code = '1003013';
		let target = null;
		Object.keys(item_code_to_name).forEach(function (code) {
			if (!target && code.includes(target_code) && categorized.fl.indexOf(item_code_to_name[code]) !== -1) {
				target = item_code_to_name[code];
			}
		});
		if (!target) target = categorized.fl[0] || '';
		const rest = categorized.fl.filter(function (n) { return n !== target; });
		return target ? [target].concat(rest) : categorized.fl.slice();
	}

	function refreshTrialItemCache() {
		return frappe.call({
			method: 'frappe.client.get_list',
			args: {
				doctype: 'Item',
				filters: {
					item_group: ['in', ['Raw Material', 'In Process Item', 'Sub-assembly', 'Consumable', 'General', 'Products', 'Finished Goods']],
				},
				fields: ['item_code', 'item_name'],
				limit_page_length: 10000,
			},
		}).then(function (res) {
			categorized = { pp: [], fl: [], sa: [], mb: [] };
			item_name_to_code = {};
			item_code_to_name = {};
			(res.message || []).forEach(function (d) {
				if (!d || !d.item_code) return;
				const name = d.item_name || d.item_code;
				const ic_u = (d.item_code || '').toUpperCase();
				const name_u = (name || '').toUpperCase();
				item_name_to_code[name] = d.item_code;
				item_name_to_code[d.item_code] = d.item_code;
				if (d.item_name) {
					item_name_to_code[d.item_code + ' - ' + d.item_name] = d.item_code;
				}
				item_code_to_name[d.item_code] = name;
				const is_dana = name_u.includes('DANA');
				if (ic_u.startsWith('PP') || ic_u.startsWith('1002') || is_dana) {
					categorized.pp.push(name);
				} else if (ic_u.startsWith('FL') || ic_u.startsWith('1003')) {
					categorized.fl.push(name);
				} else if (ic_u.startsWith('SA') || ic_u.startsWith('1004') || ic_u.includes('PPA')) {
					categorized.sa.push(name);
				} else if (ic_u.startsWith('MB') || ic_u.startsWith('1001')) {
					categorized.mb.push(name);
				}
			});
		});
	}

	async function openTrialFabricRecipeDialog(ctx, line, onSaved) {
		if (!line || !line.item_code) {
			frappe.msgprint(__('Select a trial line first.'));
			return;
		}
		await refreshTrialItemCache();

		const quality = line.quality || '';
		const color = line.color || '';
		const gsm = cint(line.gsm) || 0;
		const premium = isPremiumQuality(quality);

		let kgs = { pp_kgs: 100, filler_kgs: 35, ppa_kgs: 0.2, antistatic_kgs: 0.2 };
		try {
			const qm = await frappe.db.get_value('Quality Master', { quality_name: quality }, ['pp_kgs', 'filler_kgs', 'ppa_kgs', 'antistatic_kgs']);
			if (qm && qm.message) kgs = qm.message;
		} catch (e) { /* ignore */ }

		let mb_def = '';
		let ldr_def = 3;
		if (color) {
			try {
				const cm = await frappe.db.get_value('Colour Master', color, ['item_code', 'masterbatch_ldr_']);
				if (cm && cm.message) {
					mb_def = cm.message.item_code || mb_def;
					ldr_def = flt(cm.message.masterbatch_ldr_) || ldr_def;
				}
			} catch (e) { /* ignore */ }
		}

		let existing_data = null;
		if (line.bom) {
			try {
				const r = await frappe.call({ method: 'frappe.client.get', args: { doctype: 'BOM', name: line.bom } });
				existing_data = r.message;
			} catch (e) { /* ignore */ }
		} else {
			try {
				const pr = await frappe.call({
					method: 'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_preview_trial_fabric_bom',
					args: { item_code: line.item_code, company: ctx.company, quality: quality, color: color, gsm: gsm },
				});
				const payload = pr.message || {};
				if (payload.bom) {
					const r = await frappe.call({ method: 'frappe.client.get', args: { doctype: 'BOM', name: payload.bom } });
					existing_data = r.message;
				}
			} catch (e) { /* ignore */ }
		}

		let sel_pp = [];
		let sel_fl = [];
		let sel_sa = [];
		let pp_rats = [];
		let fl_rats = [];
		let sel_mb_ic = mb_def;
		let sel_ldr = ldr_def;

		if (existing_data && existing_data.items) {
			let tot_pp = 0;
			let tot_fl = 0;
			const temp_pp = [];
			const temp_fl = [];
			existing_data.items.forEach(function (it) {
				const name = item_code_to_name[it.item_code] || it.item_code;
				const ic_u = (it.item_code || '').toUpperCase();
				if (ic_u.startsWith('PP') || ic_u.startsWith('1002')) {
					temp_pp.push({ it: it, name: name });
					tot_pp += flt(it.qty);
				} else if (ic_u.startsWith('FL') || ic_u.startsWith('1003')) {
					temp_fl.push({ it: it, name: name });
					tot_fl += flt(it.qty);
				} else if (categorized.sa.indexOf(name) !== -1) {
					sel_sa.push(name);
				} else if (ic_u.startsWith('MB') || ic_u.startsWith('1001')) {
					sel_mb_ic = it.item_code;
				}
			});
			temp_pp.forEach(function (d) {
				sel_pp.push(d.name);
				pp_rats.push(tot_pp ? d.it.qty / tot_pp : 0);
			});
			temp_fl.forEach(function (d) {
				sel_fl.push(d.name);
				fl_rats.push(tot_fl ? d.it.qty / tot_fl : 0);
			});
			if (existing_data.custom_ldr_) sel_ldr = flt(existing_data.custom_ldr_);
		}

		const pp_opts = getFilteredPP(quality, gsm);
		const fl_opts = premium ? [] : getFilteredFiller(quality);
		let def_qty_pp = flt(kgs.pp_kgs);
		let def_qty_pp2 = 0;
		if (sel_pp.length) {
			def_qty_pp = parseFloat((flt(kgs.pp_kgs) * pp_rats[0]).toFixed(3));
			if (sel_pp.length > 1) def_qty_pp2 = parseFloat((flt(kgs.pp_kgs) * pp_rats[1]).toFixed(3));
		}
		let def_qty_fl = premium ? 0 : flt(kgs.filler_kgs);
		let def_qty_fl2 = 0;
		if (sel_fl.length) {
			def_qty_fl = parseFloat((flt(kgs.filler_kgs) * fl_rats[0]).toFixed(3));
			if (sel_fl.length > 1) def_qty_fl2 = parseFloat((flt(kgs.filler_kgs) * fl_rats[1]).toFixed(3));
		}

		const d = new frappe.ui.Dialog({
			title: __('Set fabric recipe: {0}', [line.item_code]),
			fields: [
				{
					fieldtype: 'HTML',
					fieldname: 'info',
					options:
						'<div style="padding:10px;background:#f0f4ff;border-radius:6px;margin-bottom:4px;">' +
						'<b>' + frappe.utils.escape_html(line.item_code) + '</b><br>' +
						'<span style="color:#555">' +
						__('Quality: {0} | GSM: {1} | Color: {2}', [quality, gsm, color || '—']) +
						'</span></div>',
				},
				{ fieldtype: 'Section Break', label: __('PP') },
				{ label: __('PP Item'), fieldname: 'item_pp', fieldtype: 'Autocomplete', options: pp_opts, reqd: 1, default: sel_pp[0] || pp_opts[0] || '' },
				{ label: __('PP KGs'), fieldname: 'qty_pp', fieldtype: 'Float', default: def_qty_pp, reqd: 1 },
				{ fieldtype: 'HTML', fieldname: 'add_pp_html', options: '<button type="button" class="btn btn-xs btn-default" id="trial_add_pp_btn">+ ' + __('Add PP Row') + '</button>' },
				{ label: __('PP Item 2'), fieldname: 'item_pp2', fieldtype: 'Autocomplete', options: pp_opts.slice(1), hidden: sel_pp.length > 1 ? 0 : 1, default: sel_pp[1] || '' },
				{ label: __('PP KGs 2'), fieldname: 'qty_pp2', fieldtype: 'Float', hidden: sel_pp.length > 1 ? 0 : 1, default: def_qty_pp2 },
				{ fieldtype: 'Section Break', label: __('Filler') },
				{ label: __('Filler Item'), fieldname: 'item_fl', fieldtype: 'Autocomplete', options: fl_opts, reqd: premium ? 0 : 1, default: premium ? '' : (sel_fl[0] || fl_opts[0] || '') },
				{ label: __('Filler KGs'), fieldname: 'qty_fl', fieldtype: 'Float', default: def_qty_fl, reqd: premium ? 0 : 1 },
				{ fieldtype: 'HTML', fieldname: 'add_fl_html', options: '<button type="button" class="btn btn-xs btn-default" id="trial_add_fl_btn">+ ' + __('Add Filler Row') + '</button>' },
				{ label: __('Filler Item 2'), fieldname: 'item_fl2', fieldtype: 'Autocomplete', options: fl_opts.slice(1), hidden: sel_fl.length > 1 ? 0 : 1, default: sel_fl[1] || '' },
				{ label: __('Filler KGs 2'), fieldname: 'qty_fl2', fieldtype: 'Float', hidden: sel_fl.length > 1 ? 0 : 1, default: def_qty_fl2 },
				{ fieldtype: 'Section Break', label: __('Additives') },
				{ label: __('PPA Item'), fieldname: 'item_ad1', fieldtype: 'Autocomplete', options: categorized.sa, default: sel_sa[0] || categorized.sa[0] || '' },
				{ label: __('PPA KGs'), fieldname: 'qty_ad1', fieldtype: 'Float', default: flt(kgs.ppa_kgs) },
				{ label: __('Antistatic Item'), fieldname: 'item_ad2', fieldtype: 'Autocomplete', options: categorized.sa, default: sel_sa[1] || categorized.sa[1] || categorized.sa[0] || '' },
				{ label: __('Antistatic KGs'), fieldname: 'qty_ad2', fieldtype: 'Float', default: flt(kgs.antistatic_kgs) },
				{ fieldtype: 'Section Break', label: __('Masterbatch') },
				{
					label: __('MB Item'),
					fieldname: 'item_mb',
					fieldtype: 'Autocomplete',
					options: categorized.mb,
					default: item_code_to_name[sel_mb_ic] || sel_mb_ic,
					reqd: 1,
					onchange: async function () {
						const mb_name = d.get_value('item_mb');
						const mb_code = item_name_to_code[mb_name] || mb_name;
						if (mb_code) {
							const res = await frappe.db.get_value('Colour Master', { item_code: mb_code }, 'masterbatch_ldr_');
							if (res && res.message && res.message.masterbatch_ldr_ !== undefined) {
								d.set_value('qty_mb', res.message.masterbatch_ldr_);
							}
						}
					},
				},
				{ label: __('MB LDR %'), fieldname: 'qty_mb', fieldtype: 'Float', default: sel_ldr, reqd: 1 },
			],
			primary_action_label: __('Save BOM'),
			primary_action: function (v) {
				const pp_rows = collectRows(d, ['item_pp', 'item_pp2'], ['qty_pp', 'qty_pp2'], v);
				const fl_rows = collectRows(d, ['item_fl', 'item_fl2'], ['qty_fl', 'qty_fl2'], v);
				const ad_rows = collectRows(d, ['item_ad1', 'item_ad2'], ['qty_ad1', 'qty_ad2'], v);
				const mb_rows = [{ item_code: resolveItemCodeAny(v.item_mb), share: 1 }];
				if (!pp_rows.length || (!fl_rows.length && !premium)) {
					frappe.msgprint(__('At least one PP and one Filler row are required (except PREMIUM).'));
					return;
				}
				d.hide();
				frappe.call({
					method: 'production_entry.production_planning.doctype.shaft_production_run.shaft_production_run.spr_create_trial_fabric_bom',
					args: {
						item_code: line.item_code,
						company: ctx.company,
						quality: quality,
						color: color,
						gsm: gsm,
						force_new: 1,
						recipe_payload: JSON.stringify({
							pp_rows: pp_rows,
							fl_rows: fl_rows,
							ad_rows: ad_rows,
							mb_rows: mb_rows,
							mb_ldr: parseFloat(v.qty_mb) || 0,
						}),
					},
					freeze: true,
					freeze_message: __('Saving BOM...'),
					callback: function (r) {
						const payload = r.message || {};
						if (typeof onSaved === 'function') {
							onSaved(payload);
						}
						frappe.show_alert({
							message: __('BOM saved: {0}', [payload.bom || '']),
							indicator: 'green',
						});
					},
				});
			},
		});

		d.show();
		let pp_visible = sel_pp.length > 1 ? 2 : 1;
		let fl_visible = sel_fl.length > 1 ? 2 : 1;
		d.$wrapper.on('click', '#trial_add_pp_btn', function () {
			if (pp_visible >= 2) return;
			pp_visible = 2;
			d.set_df_property('item_pp2', 'hidden', 0);
			d.set_df_property('qty_pp2', 'hidden', 0);
		});
		d.$wrapper.on('click', '#trial_add_fl_btn', function () {
			if (fl_visible >= 2) return;
			fl_visible = 2;
			d.set_df_property('item_fl2', 'hidden', 0);
			d.set_df_property('qty_fl2', 'hidden', 0);
		});
	}

	window.sprTrialFabricRecipe = {
		openDialog: openTrialFabricRecipeDialog,
	};
})();
