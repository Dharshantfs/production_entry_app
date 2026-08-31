/**
 * Work Order — Start / Finish / Return.
 * Fabric rolls (100… 16-digit) are picked by batch. PP, filler, dana auto-transfer from RM store.
 */

const MANUAL_FG_PREFIXES = ['102', '103', '104', '105', '106', '107', '109', '251', '252'];

function wo_item_process_code(itemCode) {
	const raw = cstr(itemCode || '').trim().toUpperCase();
	if (!raw) return '';

	// Design-first codes like 002-105..., 002-106..., ABC-252...
	if (raw.includes('-')) {
		const parts = raw.split('-', 2);
		if (parts.length === 2) {
			const tailDigits = cstr(parts[1]).replace(/\D/g, '');
			if (tailDigits.length >= 3) return tailDigits.slice(0, 3);
		}
	}

	// Pure numeric / mixed prefixed codes (e.g. 109..., 251..., 252...)
	const digits = raw.replace(/\D/g, '');
	return digits.length >= 3 ? digits.slice(0, 3) : '';
}

function wo_is_fabric_roll_item(itemCode) {
	const ic = cstr(itemCode || '').trim().toUpperCase();
	if (!ic) return false;
	if (ic.startsWith('PP') || ic.startsWith('FL') || ic.startsWith('MB')) return false;
	if (ic.indexOf('DANA') >= 0) return false;
	if (!ic.startsWith('100') || ic.startsWith('1000')) return false;
	const digits = ic.replace(/\D/g, '');
	if (digits.length >= 15) return true;
	return ic.length >= 9 && /^\d{9,}/.test(ic);
}

function wo_fg_needs_fabric_picks(frm) {
	const proc = wo_item_process_code(frm.doc.production_item || '');
	return !!proc && MANUAL_FG_PREFIXES.includes(proc);
}

// Expose for console checks after Client Script save + hard refresh (Ctrl+F5).
if (typeof frappe !== 'undefined') {
	frappe.production_entry_wo = frappe.production_entry_wo || {};
	frappe.production_entry_wo.wo_item_process_code = wo_item_process_code;
	frappe.production_entry_wo.wo_is_fabric_roll_item = wo_is_fabric_roll_item;
	frappe.production_entry_wo.wo_fg_needs_fabric_picks = wo_fg_needs_fabric_picks;
}

function wo_fabric_rm_rows(frm) {
	const rows = frm.doc.required_items || [];
	const out = [];
	for (let i = 0; i < rows.length; i++) {
		const r = rows[i];
		const ic = cstr(r.item_code || '');
		if (!wo_is_fabric_roll_item(ic) || flt(r.required_qty) <= 0) {
			continue;
		}
		const req = flt(r.required_qty);
		const tr = flt(r.transferred_qty);
		const remaining_qty = Math.max(0, req - tr);
		if (remaining_qty <= 0) {
			continue;
		}
		out.push({
			item_code: r.item_code,
			required_qty: req,
			transferred_qty: tr,
			remaining_qty: remaining_qty,
			source_warehouse: r.source_warehouse,
			stock_uom: r.stock_uom,
			idx: r.idx,
		});
	}
	return out;
}

/**
 * Load all Batch rows for an item (e.g. 38 rows). Uses frappe.client.get_list + list filters
 * (object filters on Link fields can miss rows on some versions). Paginates until exhausted.
 */
async function wo_load_batches_for_item(item_code) {
	const ic = cstr(item_code).trim();
	const pageSize = 500;
	const all = [];
	const seen = {};
	let limit_start = 0;

	for (;;) {
		const r = await frappe.call({
			method: 'frappe.client.get_list',
			args: {
				doctype: 'Batch',
				filters: [
					['item', '=', ic],
					['disabled', '=', 0],
				],
				fields: ['name', 'batch_qty'],
				order_by: 'name asc',
				limit_start: limit_start,
				limit_page_length: pageSize,
			},
		});
		const rows = r.message || [];
		for (let i = 0; i < rows.length; i++) {
			const row = rows[i];
			const nm = cstr(row.name);
			if (nm && !seen[nm]) {
				seen[nm] = 1;
				all.push(row);
			}
		}
		if (rows.length < pageSize) {
			break;
		}
		limit_start += pageSize;
		if (limit_start > 200000) {
			break;
		}
	}
	return all;
}

function wo_escape_html(s) {
	const t = cstr(s == null ? '' : s);
	if (frappe.utils && typeof frappe.utils.escape_html === 'function') {
		return frappe.utils.escape_html(t);
	}
	return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

/**
 * Dialog: pick batches + qty per 100* RM line; returns Promise<array picks>.
 *
 * Picks are stored in `livePicks` closure object (updated live on checkbox / qty change).
 * Submit reads `livePicks` — does NOT traverse DOM — so there is no DOM-lookup failure.
 */
function wo_open_fabric_batch_pick_dialog(frm) {
	const fabric_rows = wo_fabric_rm_rows(frm);
	if (!fabric_rows.length) {
		return Promise.resolve([]);
	}

	return new Promise(function (resolve) {
		/*
		 * livePicks: { "ITEM_CODE|||BATCH_NO": qty }
		 * Updated by every checkbox check/uncheck and every qty input change.
		 */
		const livePicks = {};

		function lp_key(item_code, batch_no) {
			return cstr(item_code).trim() + '|||' + cstr(batch_no).trim();
		}
		function lp_set(item_code, batch_no, qty) {
			const k = lp_key(item_code, batch_no);
			if (flt(qty) > 0) {
				livePicks[k] = flt(qty);
			} else {
				delete livePicks[k];
			}
		}
		function lp_sum_for_item(item_code) {
			const prefix = cstr(item_code).trim() + '|||';
			let s = 0;
			for (const k in livePicks) {
				if (k.indexOf(prefix) === 0) s += livePicks[k];
			}
			return s;
		}
		function lp_all_picks() {
			const out = [];
			for (const k in livePicks) {
				const idx = k.indexOf('|||');
				if (idx < 0) continue;
				const item_code = k.slice(0, idx);
				const batch_no = k.slice(idx + 3);
				const q = livePicks[k];
				if (item_code && batch_no && q > 0) {
					out.push({ item_code: item_code, batch_no: batch_no, qty: q });
				}
			}
			return out;
		}

		/* ---- build static HTML shell (tables filled async below) ---- */
		let body =
			'<div class="wo-fabric-pick" style="max-height:72vh;overflow-y:auto;padding-right:4px">' +
			'<p class="text-muted small">' +
			__(
				'Tick complete fabric rolls. Total can be more or less than BOM remaining. PP and other raw materials transfer automatically.'
			) +
			'</p>';

		fabric_rows.forEach(function (row, idx) {
			const wh = cstr(row.source_warehouse || frm.doc.source_warehouse || '');
			const req = flt(row.required_qty);
			const tr = flt(row.transferred_qty);
			const rem = flt(row.remaining_qty);
			body +=
				'<div style="margin-bottom:1rem;border-bottom:1px solid #ddd;padding-bottom:0.5rem">' +
				'<h5 style="margin:0 0 0.25rem 0">' + wo_escape_html(row.item_code) + '</h5>' +
				'<p class="small text-muted" style="margin:0">' +
				__('BOM required') +
				': <b>' +
				String(req) +
				'</b> &nbsp;|&nbsp; ' +
				__('Already to WIP') +
				': <b>' +
				String(tr) +
				'</b> &nbsp;|&nbsp; ' +
				__('Remaining') +
				': <b>' +
				String(rem) +
				'</b><br/>' +
				__('Source WH') +
				': ' +
				wo_escape_html(wh) +
				'</p>' +
				'<p class="small" id="wo-sum-p-' +
				idx +
				'">' +
				__('Total selected') +
				': <b id="wo-sum-' +
				idx +
				'">0</b> &nbsp;' +
				'<span class="text-muted">(' +
				__('BOM remaining') +
				' ' +
				String(rem) +
				')</span>' +
				'</p>' +
				'<div id="wo-loading-' +
				idx +
				'" class="text-muted small">' +
				__('Loading batches…') +
				'</div>' +
				'<p id="wo-cnt-' +
				idx +
				'" class="small text-muted" style="display:none"></p>' +
				'<input type="text" id="wo-search-' +
				idx +
				'" class="form-control input-sm" placeholder="' +
				__('Search batch number…') +
				'" style="display:none;margin-bottom:0.35rem;max-width:18rem" />' +
				'<table id="wo-tbl-' +
				idx +
				'" class="table table-bordered table-condensed" style="display:none;margin-top:0.25rem">' +
				'<thead><tr>' +
				'<th style="width:2.5rem">' +
				__('Use') +
				'</th>' +
				'<th>' +
				__('Batch No') +
				'</th>' +
				'<th>' +
				__('Batch master qty') +
				'</th>' +
				'<th>' +
				__('Use qty') +
				'</th>' +
				'</tr></thead>' +
				'<tbody id="wo-tbody-' +
				idx +
				'"></tbody>' +
				'</table>' +
				'</div>';
		});
		body += '</div>';

		/* ---- dialog ---- */
		const d = new frappe.ui.Dialog({
			title: __('Select fabric batches for WO transfer'),
			fields: [{ fieldtype: 'HTML', fieldname: 'wo_fabric_html' }],
			size: 'extra-large',
			primary_action_label: __('Start Transfer'),
			primary_action: function () {
				const payload = lp_all_picks();
				if (!payload.length) {
					frappe.msgprint(__('Tick the fabric rolls to send to WIP, then Start Transfer.'));
					return;
				}
				d.hide();
				resolve(payload);
			},
			secondary_action_label: __('Cancel'),
			secondary_action: function () {
				d.hide();
				resolve(null);
			},
		});

		/* Inject HTML into the field wrapper */
		var $fw = d.get_field('wo_fabric_html').$wrapper;
		$fw.html(body);

		/* ---- async batch load per RM row ---- */
		fabric_rows.forEach(function (row, idx) {
			const ic = cstr(row.item_code).trim();

			wo_load_batches_for_item(ic).then(function (batches) {
				var $loading = $fw.find('#wo-loading-' + idx);
				var $cnt     = $fw.find('#wo-cnt-' + idx);
				var $tbl     = $fw.find('#wo-tbl-' + idx);
				var $tbody   = $fw.find('#wo-tbody-' + idx);

				$loading.hide();

				if (!batches.length) {
					$cnt.text(__('No active Batch records found for this item.')).show();
					$tbl.show();
					return;
				}

				$cnt.text(__('Loaded') + ' ' + String(batches.length) + ' ' + __('batches')).show();
				$fw.find('#wo-search-' + idx).show().on('input', function () {
					const term = String($(this).val() || '').toLowerCase();
					$tbody.find('tr').each(function () {
						const bn = String($(this).attr('data-bn') || '').toLowerCase();
						$(this).toggle(!term || bn.indexOf(term) >= 0);
					});
				});

				batches.forEach(function (b) {
					const bn  = cstr(b.name).trim();
					const bq  = flt(b.batch_qty);
					const $tr = $('<tr></tr>').attr('data-bn', bn).attr('data-mq', String(bq));

					const $chk = $('<input type="checkbox" />');
					const $qty = $('<input type="number" step="0.001" min="0" class="form-control" style="max-width:8rem" />');
					$qty.attr('placeholder', __('Qty'));

					/* checkbox: auto-fill qty and update livePicks */
					$chk.on('change', function () {
						if ($chk.prop('checked')) {
							const fillQty = bq > 0 ? bq : 0;
							$qty.val(fillQty > 0 ? String(fillQty) : '');
							lp_set(ic, bn, fillQty);
						} else {
							$qty.val('');
							lp_set(ic, bn, 0);
						}
						$fw.find('#wo-sum-' + idx).text(String(flt(lp_sum_for_item(ic), 3)));
					});

					/* qty input: update livePicks; typing qty implies Use without forcing checkbox first */
					$qty.on('input change', function () {
						const v = flt($qty.val());
						if (v > 0 && !$chk.prop('checked')) {
							$chk.prop('checked', true);
						}
						lp_set(ic, bn, $chk.prop('checked') ? v : 0);
						$fw.find('#wo-sum-' + idx).text(String(flt(lp_sum_for_item(ic), 3)));
					});

					$tr.append(
						$('<td></td>').append($chk),
						$('<td></td>').text(bn),
						$('<td></td>').text(String(bq)),
						$('<td></td>').append($qty)
					);
					$tbody.append($tr);
				});

				$tbl.show();
			});
		});

		d.show();
	});
}

function wo_call_auto_material_transfer(frm, fabric_batch_picks) {
	const picks = fabric_batch_picks || [];
	const args = { work_order: frm.doc.name };
	if (picks.length) {
		const json = JSON.stringify(picks);
		args.fabric_picks_json = json;
		args.fabric_batch_picks = json;
		args.fbp = json;
		args.fabric_batch_picks_list = picks;
		args.wo_transfer_payload = JSON.stringify({
			work_order: frm.doc.name,
			fabric_batch_picks: picks,
		});
	}

	console.log('[WO Start] picks count =', picks.length);

	/* frappe.call puts all keys inside POST "args" JSON — Server Script usually receives that
	   even when top-level fabric_* fields are blocked. Plain $.ajax form fields are often dropped. */
	return new Promise(function (resolve, reject) {
		frappe.call({
			method: 'production_entry.production_planning.work_order_transfer.auto_material_transfer',
			args: args,
			callback: function (r) {
				try {
					if (!r) {
						reject({ message: __('Empty response from server') });
						return;
					}
					let raw = r.message;
					if (typeof raw === 'string') {
						try {
							raw = JSON.parse(raw);
						} catch (e) {
							raw = { success: true, message: raw };
						}
					}
					if (raw && typeof raw === 'object' && raw.success === undefined && raw.message) {
						raw = { success: true, message: raw.message };
					}
					if (!raw || typeof raw !== 'object') {
						raw = { success: false, message: __('Unexpected response') };
					}
					resolve({ message: raw });
				} catch (e) {
					reject({ message: String(e.message || e) });
				}
			},
			error: function (r) {
				let em = '';
				try {
					const rj = (r && r.responseJSON) || r || {};
					em = cstr(rj.message || rj.exception || '');
					if (!em && rj._server_messages) {
						const arr = JSON.parse(rj._server_messages);
						if (Array.isArray(arr) && arr[0]) {
							const o = JSON.parse(arr[0]);
							em = cstr(o.message || '');
						}
					}
					if (!em && rj.exc) {
						const parsed = JSON.parse(rj.exc);
						if (Array.isArray(parsed) && parsed[0]) {
							const o = JSON.parse(parsed[0]);
							em = cstr(o.message || '');
						}
					}
				} catch (e2) {
					em = '';
				}
				if (!em) {
					em = __('Request failed');
				}
				reject({ message: em });
			},
		});
	});
}

frappe.ui.form.on('Work Order', {
	refresh: function (frm) {
		if (frm.doc.docstatus !== 1) return;

		setTimeout(function () {
			if (frm.page.remove_inner_button) {
				frm.page.remove_inner_button('Start');
				frm.page.remove_inner_button('Finish');
			}
			$('button[data-label="Start"]').hide();
			$('button[data-label="Finish"]').hide();
		}, 200);

		const is_closed = frm.doc.status === 'Completed' || frm.doc.status === 'Stopped';

		if (!is_closed && (frm.doc.material_transferred_for_manufacturing || 0) < frm.doc.qty) {
			if (!frm.custom_buttons || !frm.custom_buttons[__('Start Production')]) {
				frm
					.add_custom_button(
						__('Start Production'),
						function () {
							const run_transfer = function (picks) {
								frappe.dom.freeze(__('Starting...'));
								wo_call_auto_material_transfer(frm, picks || [])
									.then(function (r) {
										frappe.dom.unfreeze();
										const msg = (r && r.message) || {};
										const ok = msg.success === true || msg.success === 1;
										if (ok) {
											const m = msg.message || __('Started');
											if (String(m).indexOf('Skipped:') === 0) {
												frappe.msgprint({
													message: m,
													title: __('Action needed'),
													indicator: 'orange',
												});
											} else {
												frappe.msgprint({ message: cstr(m), indicator: 'green' });
											}
											frm.reload_doc();
										} else {
											frappe.msgprint({
												message: cstr(msg.message || msg.exc || __('Transfer did not complete')),
												indicator: 'red',
												title: __('Work Order'),
											});
										}
									})
									.catch(function (err) {
										frappe.dom.unfreeze();
										const em =
											(err && err.message) ||
											(err && err._server_messages && __('Server error — see Error Log'));
										if (em) {
											frappe.msgprint({ message: em, indicator: 'red' });
										}
									});
							};

							if (wo_fg_needs_fabric_picks(frm) && wo_fabric_rm_rows(frm).length) {
								wo_open_fabric_batch_pick_dialog(frm).then(function (picks) {
									if (picks === null) return;
									run_transfer(picks);
								});
							} else {
								run_transfer(null);
							}
						},
						__('WO')
					)
					.addClass('btn-primary');
			}
		}

		if (!is_closed && (frm.doc.material_transferred_for_manufacturing || 0) > 0) {
			if (!frm.custom_buttons || !frm.custom_buttons[__('Finish Production')]) {
				frm
					.add_custom_button(__('Finish Production'), function () {
						create_roll_entry_balance(frm);
					}, __('WO'))
					.addClass('btn-danger');
			}
		}

		if (
			!is_closed &&
			frm.doc.material_transferred_for_manufacturing > frm.doc.produced_qty &&
			(!frm.custom_buttons || !frm.custom_buttons[__('Return Unused & Close')])
		) {
			frm.add_custom_button(
				__('Return Unused & Close'),
				function () {
					frappe.confirm(
						__(
							'This will return unused material and <b>STOP</b> the Work Order.<br>Are you sure?'
						),
						function () {
							frappe.dom.freeze(__('Closing Order...'));
							frappe
								.call({
									method: 'return_unused_material',
									args: { work_order: frm.doc.name },
								})
								.then(function (r) {
									frappe.dom.unfreeze();
									const msg = r.message || {};
									if (msg.success) {
										frappe.msgprint(msg.message);
										frm.reload_doc();
									}
								})
								.catch(function () {
									frappe.dom.unfreeze();
								});
						}
					);
				},
				__('WO')
			).addClass('btn-warning');
		}
	},
});

async function create_roll_entry_balance(frm) {
	frappe.dom.freeze(__('Calculations...'));
	try {
		const wo_data = await frappe.db.get_doc('Work Order', frm.doc.name);
		const balance_qty = flt(wo_data.qty) - flt(wo_data.produced_qty);

		if (balance_qty <= 0) {
			frappe.dom.unfreeze();
			frappe.msgprint(__('Production Completed.'));
			return;
		}

		let found_unit = null;
		const potential_fields = ['unit', 'custom_unit', 'production_unit', 'custom_unit_no'];
		for (const field of potential_fields) {
			if (wo_data[field]) {
				found_unit = wo_data[field];
				break;
			}
		}
		if (!found_unit) {
			for (const [key, value] of Object.entries(wo_data)) {
				if (typeof value === 'string' && value.includes('Unit') && value.length < 10) {
					found_unit = value;
					break;
				}
			}
		}
		if (!found_unit) found_unit = 'Unit 1';

		frappe.model.with_doctype('Roll Production Entry', function () {
			const doc = frappe.model.get_new_doc('Roll Production Entry');
			doc.work_order = wo_data.name;
			doc.production_item = wo_data.production_item;
			doc.planned_qty = balance_qty;
			doc.wip_warehouse = wo_data.wip_warehouse;
			doc.fg_warehouse = wo_data.fg_warehouse;
			doc.company = wo_data.company;
			const party = wo_data.custom_party_code || wo_data.party_code;
			if (party) {
				doc.custom_party_code = party;
				doc.party_code = party;
			}
			doc.unit = found_unit;
			doc.custom_unit = found_unit;

			frappe.dom.unfreeze();
			frappe.set_route('Form', 'Roll Production Entry', doc.name);
		});
	} catch (e) {
		frappe.dom.unfreeze();
		frappe.msgprint(__('Error: {0}', [e.message || String(e)]));
	}
}
