/**
 * Strict child-grid column control for Frappe editable grids.
 * Prevents header/body column misalignment when toggling visible fields.
 *
 * Rules:
 * - Child doctype JSON should set every field in_list_view: 0 (JS owns columns).
 * - Never set hidden=1 on grid fields — only toggle in_list_view.
 * - Always reset all columns, apply ordered show list, then realign header + body.
 */
frappe.provide('production_entry.grid_columns');

const CG_SKIP_FIELD_TYPES = new Set([
	'Column Break', 'Section Break', 'Tab Break', 'HTML', 'Button',
]);

function cg_skip_field(df) {
	return !df || CG_SKIP_FIELD_TYPES.has(df.fieldtype);
}

function cg_reset_all_list_view(grid, metaDoctype) {
	(frappe.meta.get_docfields(metaDoctype) || []).forEach((df) => {
		if (cg_skip_field(df)) {
			return;
		}
		try {
			grid.update_docfield_property(df.fieldname, 'hidden', 0);
			grid.update_docfield_property(df.fieldname, 'in_list_view', 0);
		} catch (e) {
			/* ignore */
		}
	});
}

function cg_field_exists(metaDoctype, fn) {
	const df = frappe.meta.get_docfield(metaDoctype, fn);
	return !!df && !cg_skip_field(df);
}

function cg_ordered_show_fields(metaDoctype, showSet, preferredOrder) {
	const show = [];
	const seen = {};
	if (preferredOrder && preferredOrder.length) {
		preferredOrder.forEach((fn) => {
			if (!showSet[fn] || seen[fn] || !cg_field_exists(metaDoctype, fn)) {
				return;
			}
			show.push(fn);
			seen[fn] = 1;
		});
	}
	const meta = frappe.get_meta(metaDoctype);
	const order = (meta && meta.field_order) || [];
	order.forEach((fn) => {
		if (!showSet[fn] || seen[fn] || !cg_field_exists(metaDoctype, fn)) {
			return;
		}
		show.push(fn);
		seen[fn] = 1;
	});
	Object.keys(showSet || {}).forEach((fn) => {
		if (seen[fn] || !cg_field_exists(metaDoctype, fn)) {
			return;
		}
		show.push(fn);
	});
	return show;
}

/** Reorder grid.docfields so visible columns follow preferredOrder (Frappe uses docfields iteration order). */
function cg_reorder_grid_docfields(grid, metaDoctype, preferredOrder) {
	if (!grid || !preferredOrder || !preferredOrder.length) {
		return;
	}
	const source = (grid.docfields || []).slice();
	if (!source.length) {
		return;
	}
	const byName = {};
	source.forEach((df) => {
		if (df && df.fieldname) {
			byName[df.fieldname] = df;
		}
	});
	const ordered = [];
	const seen = {};
	preferredOrder.forEach((fn) => {
		if (byName[fn] && !seen[fn]) {
			ordered.push(byName[fn]);
			seen[fn] = 1;
		}
	});
	source.forEach((df) => {
		if (df && df.fieldname && !seen[df.fieldname]) {
			ordered.push(df);
			seen[df.fieldname] = 1;
		}
	});
	grid.docfields = ordered;
}

function cg_refresh_grid_body(grid) {
	if (!grid) {
		return;
	}
	try {
		if (typeof grid.refresh === 'function') {
			grid.refresh();
			return;
		}
	} catch (e) {
		/* fall through */
	}
	try {
		(grid.grid_rows || []).forEach((gr) => {
			if (gr && typeof gr.refresh === 'function') {
				gr.refresh();
			}
		});
	} catch (e) {
		/* ignore */
	}
}

function cg_sync_header_scroll(fd) {
	if (!fd || !fd.$wrapper || !fd.$wrapper.length) {
		return;
	}
	const $w = fd.$wrapper;
	const $body = $w.find('.dt-scrollable, .form-grid .grid-body').first();
	const $head = $w.find('.grid-heading-row, .dt-row-header, .dt-header').first();
	if (!$body.length || !$head.length) {
		return;
	}
	const sl = $body.scrollLeft() || 0;
	if (Math.abs(($head.scrollLeft() || 0) - sl) > 0.5) {
		$head.scrollLeft(sl);
	}
}

function cg_realign_grid(grid, fd) {
	if (!grid) {
		return;
	}
	try {
		if (grid.visible_columns) {
			delete grid.visible_columns;
		}
	} catch (e) {
		/* ignore */
	}
	try {
		if (typeof grid.setup_visible_columns === 'function') {
			grid.setup_visible_columns();
		}
	} catch (e) {
		/* ignore */
	}
	try {
		if (typeof grid.refresh_header === 'function') {
			grid.refresh_header();
		}
	} catch (e) {
		/* ignore */
	}
	cg_refresh_grid_body(grid);
	cg_sync_header_scroll(fd);
}

production_entry.grid_columns = {
	SKIP_FIELD_TYPES: CG_SKIP_FIELD_TYPES,

	reset_all_list_view: cg_reset_all_list_view,

	ordered_show_fields: cg_ordered_show_fields,

	/**
	 * @param {object} frm - Frappe form
	 * @param {string} tableFieldname - parent child table fieldname
	 * @param {string} metaDoctype - child doctype name
	 * @param {string[]} showFieldnames - fieldnames to show; array order is preserved when provided
	 */
	apply(frm, tableFieldname, metaDoctype, showFieldnames) {
		const fd = frm && frm.fields_dict && frm.fields_dict[tableFieldname];
		if (!fd || !fd.grid || !metaDoctype) {
			return;
		}
		const grid = fd.grid;
		const preferred = (showFieldnames || []).filter((fn) => cg_field_exists(metaDoctype, fn));
		const showSet = {};
		preferred.forEach((fn) => {
			showSet[fn] = 1;
		});

		cg_reset_all_list_view(grid, metaDoctype);
		cg_reorder_grid_docfields(grid, metaDoctype, preferred);
		const ordered = cg_ordered_show_fields(metaDoctype, showSet, preferred);
		ordered.forEach((fn) => {
			try {
				grid.update_docfield_property(fn, 'hidden', 0);
				grid.update_docfield_property(fn, 'in_list_view', 1);
			} catch (e) {
				/* ignore */
			}
		});
		cg_realign_grid(grid, fd);
	},

	realign(frm, tableFieldname) {
		const fd = frm && frm.fields_dict && frm.fields_dict[tableFieldname];
		if (!fd || !fd.grid) {
			return;
		}
		cg_realign_grid(fd.grid, fd);
	},

	sync_header_scroll(frm, tableFieldname) {
		const fd = frm && frm.fields_dict && frm.fields_dict[tableFieldname];
		cg_sync_header_scroll(fd);
	},

	debounce(frm, key, fn, delay) {
		const timerKey = '_cg_debounce_' + key;
		if (frm[timerKey]) {
			clearTimeout(frm[timerKey]);
		}
		frm[timerKey] = setTimeout(() => {
			frm[timerKey] = null;
			fn();
		}, delay != null ? delay : 80);
	},
};
