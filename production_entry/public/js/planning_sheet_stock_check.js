/* Planning Sheet — bag process stock check (Manual / Auto with mandatory confirm). */

const PLANNING_BAG_FG_PREFIXES = new Set([
	'200', '201', '202', '203',
	'211', '212', '213', '214', '215', '216', '217',
	'221', '222', '223', '224',
	'231', '233', '241', '242',
]);

function planning_sheet_item_process_prefix(item_code) {
	const ic = (item_code || '').trim();
	if (!ic) return '';
	const m = ic.match(/^(\d{3})/);
	if (m) return m[1];
	const dash = ic.indexOf('-');
	if (dash > 0) return ic.substring(0, dash).substring(0, 3);
	return '';
}

function planning_sheet_has_bag_fg(frm) {
	const rows = [...(frm.doc.items || []), ...(frm.doc.planned_items || [])];
	for (const r of rows) {
		const pref = planning_sheet_item_process_prefix(r.item_code);
		if (PLANNING_BAG_FG_PREFIXES.has(pref)) return true;
	}
	return false;
}

function planning_sheet_toggle_stock_mode_field(frm) {
	const show = planning_sheet_has_bag_fg(frm);
	if (frm.fields_dict.custom_stock_check_mode) {
		frm.toggle_display('custom_stock_check_mode', show);
	}
}

function planning_sheet_stock_esc(v) {
	return frappe.utils.escape_html(v == null ? '' : String(v));
}

function planning_sheet_stock_format_qty(qty, uom) {
	const q = flt(qty);
	const u = (uom || '').trim();
	return u ? `${q} ${planning_sheet_stock_esc(u)}` : String(q);
}

function planning_sheet_stock_batches_html(batches) {
	if (!batches || !batches.length) {
		return `<div class="text-muted small">${__('No batch stock found across warehouses.')}</div>`;
	}
	let rows = batches.map((b) => `
		<tr>
			<td>${planning_sheet_stock_esc(b.batch_no)}</td>
			<td class="text-right">${flt(b.qty)}</td>
			<td>${planning_sheet_stock_esc(b.warehouse)}</td>
			<td>${planning_sheet_stock_esc(b.company_name || b.company)}</td>
		</tr>
	`).join('');
	return `
		<table class="table table-bordered table-condensed table-sm" style="margin:4px 0 0;font-size:11px;">
			<thead><tr>
				<th>${__('Batch')}</th><th>${__('Qty')}</th><th>${__('Warehouse')}</th><th>${__('Company')}</th>
			</tr></thead>
			<tbody>${rows}</tbody>
		</table>`;
}

function planning_sheet_stock_build_inquiry_html(ctx, mode) {
	const isAuto = (mode || ctx.stock_check_mode || 'Manual') === 'Auto';
	let html = `
		<p class="text-muted small">
			${__('Mode')}: <strong>${isAuto ? __('Auto') : __('Manual')}</strong>
			&nbsp;|&nbsp; ${__('Eligible rows')}: ${ctx.eligible_count || 0}
			&nbsp;|&nbsp; ${__('Sufficient')}: ${ctx.sufficient_count || 0}
		</p>`;
	for (const grp of (ctx.groups || [])) {
		html += `<div class="stock-check-so-group" style="margin-bottom:12px;">
			<h6 style="margin:8px 0 4px;">${__('SO line')}: ${planning_sheet_stock_esc(grp.sales_order_item)}</h6>`;
		for (const line of (grp.lines || [])) {
			const rowId = planning_sheet_stock_esc(line.planning_table_row);
			const statusCls = line.sufficient ? 'text-success' : 'text-danger';
			const statusTxt = line.sufficient ? __('Sufficient') : __('Short');
			const locked = cint(line.stock_locked);
			const checked = isAuto && line.sufficient ? 'checked' : '';
			const disabled = isAuto ? 'disabled' : (locked ? 'disabled' : '');
			const pick = line.proposed_batch || {};
			html += `
			<div class="stock-check-row border rounded p-2 mb-2" data-row="${rowId}">
				<div class="row">
					<div class="col-sm-1">${isAuto ? '' : `<input type="checkbox" class="stock-check-select" data-row="${rowId}" ${checked} ${disabled}/>`}</div>
					<div class="col-sm-11">
						<strong>${planning_sheet_stock_esc(line.item_code)}</strong>
						<span class="badge badge-secondary">${planning_sheet_stock_esc(line.process)}</span>
						${locked ? `<span class="badge badge-info">${__('Stock')}</span>` : ''}
						<br>
						<span class="small">${planning_sheet_stock_esc(line.item_name)}</span><br>
						${__('Required')}: <strong>${planning_sheet_stock_format_qty(line.required_qty, line.uom)}</strong>
						&nbsp;|&nbsp; ${__('Available (all sites)')}: <strong>${flt(line.available_qty)}</strong>
						&nbsp;|&nbsp; <span class="${statusCls}">${statusTxt}</span>
						${pick.batch_no ? `<br><span class="small text-muted">${__('Proposed')}: ${planning_sheet_stock_esc(pick.batch_no)} @ ${planning_sheet_stock_esc(pick.warehouse)} (${planning_sheet_stock_esc(pick.company_name || pick.company)})</span>` : ''}
						${planning_sheet_stock_batches_html(line.batches)}
						${!isAuto && (line.batches || []).length > 1 ? `
							<div class="small" style="margin-top:4px;">
								<label>${__('Pick batch')}</label>
								<select class="form-control input-sm stock-check-batch-pick" data-row="${rowId}">
									${(line.batches || []).map((b) => {
										const sel = pick.batch_no === b.batch_no && pick.warehouse === b.warehouse ? 'selected' : '';
										const label = `${b.batch_no} | ${flt(b.qty)} | ${b.warehouse} | ${b.company_name || b.company}`;
										return `<option value="${planning_sheet_stock_esc(b.batch_no)}" data-warehouse="${planning_sheet_stock_esc(b.warehouse)}" data-company="${planning_sheet_stock_esc(b.company)}" ${sel}>${planning_sheet_stock_esc(label)}</option>`;
									}).join('')}
								</select>
							</div>` : ''}
					</div>
				</div>
			</div>`;
		}
		html += '</div>';
	}
	return html;
}

function planning_sheet_stock_collect_selections($wrapper) {
	const selections = [];
	$wrapper.find('.stock-check-select:checked').each(function () {
		const rowId = $(this).data('row');
		const pick = $wrapper.find(`.stock-check-batch-pick[data-row="${rowId}"]`);
		let batch_no = '';
		let warehouse = '';
		let company = '';
		if (pick.length) {
			const opt = pick.find('option:selected');
			batch_no = opt.val() || '';
			warehouse = opt.data('warehouse') || '';
			company = opt.data('company') || '';
		}
		selections.push({ planning_table_row: rowId, batch_no, warehouse, company });
	});
	return selections;
}

function planning_sheet_stock_show_confirm_dialog(frm, preview, mode, selections, inquiryDialog) {
	const lines = preview.preview_lines || [];
	if (!lines.length) {
		frappe.msgprint(__('No rows selected for stock assignment.'));
		return;
	}
	let tableRows = '';
	for (const pl of lines) {
		const pick = pl.proposed_batch || {};
		const cascade = (pl.cascade || []).map((c) => c.item_code).join(', ');
		tableRows += `
			<tr class="${pl.can_apply ? '' : 'text-muted'}">
				<td>${pl.can_apply ? __('Yes') : __('No')}</td>
				<td>${planning_sheet_stock_esc(pl.item_code)} (${planning_sheet_stock_esc(pl.process)})</td>
				<td>${planning_sheet_stock_format_qty(pl.required_qty, pl.uom)}</td>
				<td>${planning_sheet_stock_esc(pick.batch_no || '—')}</td>
				<td>${planning_sheet_stock_esc(pick.warehouse || '—')}</td>
				<td>${planning_sheet_stock_esc(pick.company_name || pick.company || '—')}</td>
				<td class="small">${planning_sheet_stock_esc(cascade || '—')}</td>
			</tr>`;
	}
	const confirm = new frappe.ui.Dialog({
		title: __('Confirm Stock Assignment'),
		size: 'large',
		fields: [{
			fieldtype: 'HTML',
			fieldname: 'summary',
			options: `
				<p>${__('Review company, warehouse, and batch before saving. Downstream BOM rows will also be set to Stock.')}</p>
				<table class="table table-bordered table-condensed">
					<thead><tr>
						<th>${__('Apply')}</th><th>${__('Item')}</th><th>${__('Required')}</th>
						<th>${__('Batch')}</th><th>${__('Warehouse')}</th><th>${__('Company')}</th><th>${__('Cascade')}</th>
					</tr></thead>
					<tbody>${tableRows}</tbody>
				</table>`,
		}],
		primary_action_label: __('Confirm & Apply Stock'),
		primary_action() {
			if (!preview.can_apply_any) {
				frappe.msgprint({
					title: __('Cannot apply'),
					message: __('One or more rows have insufficient stock for the required quantity.'),
					indicator: 'orange',
				});
				return;
			}
			const method = mode === 'auto'
				? 'production_entry.production_planning.planning_stock_check.apply_planning_sheet_stock_auto'
				: 'production_entry.production_planning.planning_stock_check.apply_planning_sheet_stock_selections';
			const args = {
				planning_sheet_name: frm.doc.name,
				confirmed: 1,
			};
			if (mode !== 'auto') {
				args.selections_json = JSON.stringify(selections);
			}
			frappe.call({
				method,
				args,
				freeze: true,
				freeze_message: __('Applying Stock movement...'),
				callback(r) {
					if (r.exc) return;
					const m = r.message || {};
					confirm.hide();
					if (inquiryDialog) inquiryDialog.hide();
					frappe.show_alert({
						message: __('Stock applied on {0} row(s).', [m.count || 0]),
						indicator: 'green',
					});
					frm.reload_doc();
				},
			});
		},
		secondary_action_label: __('Go Back'),
		secondary_action() {
			confirm.hide();
		},
	});
	confirm.show();
}

function open_planning_sheet_stock_check_dialog(frm) {
	if (!frm || !frm.doc || !frm.doc.name) return;
	frappe.call({
		method: 'production_entry.production_planning.planning_stock_check.get_planning_sheet_stock_check_context',
		args: { planning_sheet_name: frm.doc.name },
		freeze: true,
		freeze_message: __('Loading stock availability...'),
		callback(r) {
			if (r.exc) return;
			const ctx = r.message || {};
			const mode = frm.doc.custom_stock_check_mode || ctx.stock_check_mode || 'Manual';
			const d = new frappe.ui.Dialog({
				title: __('Check Stock — Bag BOM'),
				size: 'extra-large',
				fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
			});
			const render = () => {
				d.fields_dict.body.$wrapper.html(planning_sheet_stock_build_inquiry_html(ctx, mode));
			};
			render();
			d.set_primary_action(mode === 'Auto' ? __('Review eligible rows') : __('Review & Set Stock'), () => {
				const isAuto = mode === 'Auto';
				const selections = isAuto ? [] : planning_sheet_stock_collect_selections(d.fields_dict.body.$wrapper);
				if (!isAuto && !selections.length) {
					frappe.msgprint(__('Select at least one row.'));
					return;
				}
				frappe.call({
					method: 'production_entry.production_planning.planning_stock_check.preview_planning_sheet_stock_apply',
					args: {
						planning_sheet_name: frm.doc.name,
						selections_json: JSON.stringify(selections),
						mode: isAuto ? 'auto' : 'manual',
					},
					freeze: true,
					callback(res) {
						if (res.exc) return;
						planning_sheet_stock_show_confirm_dialog(frm, res.message || {}, isAuto ? 'auto' : 'manual', selections, d);
					},
				});
			});
			d.add_custom_action(__('Clear Stock'), () => {
				frappe.confirm(
					__('Reset all Stock rows on this sheet back to Transfer/Despatch?'),
					() => {
						frappe.call({
							method: 'production_entry.production_planning.planning_stock_check.clear_planning_sheet_stock',
							args: {
								planning_sheet_name: frm.doc.name,
								planning_table_rows_json: '[]',
								confirmed: 1,
							},
							freeze: true,
							callback(res) {
								if (res.exc) return;
								const m = res.message || {};
								d.hide();
								frappe.show_alert({
									message: __('Cleared Stock on {0} row(s).', [m.count || 0]),
									indicator: 'green',
								});
								frm.reload_doc();
							},
						});
					}
				);
			});
			d.show();
		},
	});
}

function register_planning_sheet_stock_check_button(frm) {
	if (!frm || !frm.doc || !frm.doc.name) return;
	planning_sheet_toggle_stock_mode_field(frm);
	if (!planning_sheet_has_bag_fg(frm)) return;
	try {
		frm.remove_custom_button(__('Check Stock'), __('Actions'));
	} catch (e) { /* ignore */ }
	frm.add_custom_button(__('Check Stock'), () => open_planning_sheet_stock_check_dialog(frm), __('Actions'));
}

frappe.ui.form.on('Planning sheet', {
	refresh(frm) {
		register_planning_sheet_stock_check_button(frm);
	},
	custom_stock_check_mode() {
		/* mode saved on form; dialog reads frm.doc on open */
	},
});
