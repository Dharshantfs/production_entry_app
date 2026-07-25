/**
 * TEMP HOTFIX — Client Script on DocType "Clubbing Sheet"
 *
 * Use this when Get Items shows:
 *   "Could not add items — reload the page (Ctrl+Shift+R)."
 *
 * That message means an OLD Client Script is still running and
 * frm.events.process_selections is missing.
 *
 * Steps:
 * 1. Desk → Client Script → New (or edit existing Clubbing one)
 * 2. DocType: Clubbing Sheet | Enabled: Yes
 * 3. Paste THIS entire file and Save
 * 4. Hard refresh Clubbing Sheet (Ctrl+Shift+R)
 * 5. Get Planning Items → select rows → Get Items
 *
 * Later: disable this after app JS v20260725a+ is deployed, and
 * disable any older Clubbing Sheet Client Script that still has
 * the "Could not add items" message.
 */
frappe.ui.form.on('Clubbing Sheet', {
	refresh(frm) {
		const run = function (frm2, selections) {
			frm2 = frm2 || frm;
			selections = selections || [];
			if (typeof window._jsb_club_process_selections === 'function') {
				window._jsb_club_process_selections(frm2, selections, null);
				return;
			}
			frappe.call({
				method: 'production_entry.production_planning.clubbing_api.get_planning_orders_for_clubbing',
				freeze: true,
				callback(r) {
					const all = r.message || [];
					const picked = all.filter(
						(o) =>
							selections.includes(o.name) ||
							selections.includes(o.planning_table_row)
					);
					if (!picked.length) {
						frappe.msgprint(__('No matching Planning Table rows for selection.'));
						return;
					}
					picked.forEach((so) => {
						const row = frm2.add_child('items');
						const rd = locals[row.doctype][row.name];
						rd.customer = so.customer;
						rd.customer_name = so.customer_name || so.customer;
						rd.sales_order = so.sales_order || '';
						rd.party_code = so.party_code || so.custom_party_code || '';
						rd.weight_kgs = flt(so.weight_kgs || so.total_qty);
						rd.no_of_rolls = flt(so.no_of_rolls);
						rd.party_location = so.city || '';
						rd.custom_planning_table_row = so.planning_table_row || so.name || '';
						rd.custom_planning_sheet = so.planning_sheet || '';
					});
					frm2.refresh_field('items');
					try {
						frm2.trigger('recalculate_load_type');
					} catch (e) {
						/* ignore if not defined */
					}
				},
			});
		};

		if (!frm.events) frm.events = {};
		frm.events.process_selections = run;
		if (frm.cscript) frm.cscript.process_selections = run;
		if (frm.script_manager && frm.script_manager.events) {
			frm.script_manager.events.process_selections = [run];
		}
	},

	process_selections(frm, selections) {
		if (typeof window._jsb_club_process_selections === 'function') {
			window._jsb_club_process_selections(frm, selections, null);
			return;
		}
		if (frm.events && typeof frm.events.process_selections === 'function') {
			frm.events.process_selections(frm, selections);
		}
	},
});
