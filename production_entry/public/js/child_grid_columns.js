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
	'Column Break', 'Section Break', 'Tab Break', 'HTML',
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

/** Frappe meta.field_order may be array, JSON string, or object — normalize before iteration. */
function cg_meta_field_order(metaDoctype) {
	const meta = frappe.get_meta(metaDoctype);
	if (!meta) {
		return [];
	}
	const fo = meta.field_order;
	if (Array.isArray(fo)) {
		return fo;
	}
	if (typeof fo === 'string') {
		try {
			const parsed = JSON.parse(fo);
			if (Array.isArray(parsed)) {
				return parsed;
			}
		} catch (e) {
			/* ignore */
		}
	}
	if (fo && typeof fo === 'object') {
		const keys = Object.keys(fo).filter((k) => /^\d+$/.test(k)).sort((a, b) => Number(a) - Number(b));
		if (keys.length) {
			return keys.map((k) => fo[k]);
		}
		return Object.values(fo);
	}
	return (frappe.meta.get_docfields(metaDoctype) || [])
		.map((df) => df && df.fieldname)
		.filter(Boolean);
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
	const order = cg_meta_field_order(metaDoctype);
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

/** Return docfields array reordered to preferredOrder (unknown fields trail at end). */
function cg_reorder_docfields_array(docfields, preferredOrder) {
	const source = (docfields || []).slice();
	if (!source.length || !preferredOrder || !preferredOrder.length) {
		return source;
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
	return ordered;
}

/** Reorder grid.docfields so visible columns follow preferredOrder (Frappe header uses this order). */
function cg_reorder_grid_docfields(grid, metaDoctype, preferredOrder) {
	if (!grid || !preferredOrder || !preferredOrder.length) {
		return;
	}
	if (!(grid.docfields || []).length) {
		return;
	}
	grid.docfields = cg_reorder_docfields_array(grid.docfields, preferredOrder);
}

/**
 * Row body cells iterate gr.docfields — must match grid.docfields order or values sit under wrong headers.
 */
function cg_reorder_all_row_docfields(grid, preferredOrder) {
	if (!grid || !preferredOrder || !preferredOrder.length) {
		return;
	}
	(grid.grid_rows || []).forEach((gr) => {
		if (!gr) {
			return;
		}
		if (gr.docfields && gr.docfields.length) {
			gr.docfields = cg_reorder_docfields_array(gr.docfields, preferredOrder);
		}
		if (gr.grid && gr.grid.docfields && gr.grid.docfields.length) {
			gr.grid.docfields = cg_reorder_docfields_array(gr.grid.docfields, preferredOrder);
		}
	});
}

function cg_visible_column_count(grid) {
	if (!grid) {
		return 0;
	}
	if (grid.visible_columns && grid.visible_columns.length) {
		return grid.visible_columns.length;
	}
	return (grid.docfields || []).filter((df) => df && df.in_list_view && !cg_skip_field(df)).length;
}

function cg_sync_row_docfields(grid, showSet) {
	if (!grid || !showSet) {
		return;
	}
	(grid.grid_rows || []).forEach((gr) => {
		if (!gr) {
			return;
		}
		[gr.docfields, gr.grid && gr.grid.docfields].forEach((docfields) => {
			if (!docfields || !docfields.length) {
				return;
			}
			docfields.forEach((df) => {
				if (!df || !df.fieldname || cg_skip_field(df)) {
					return;
				}
				const show = !!showSet[df.fieldname];
				df.in_list_view = show ? 1 : 0;
				df.hidden = 0;
			});
		});
	});
}

function cg_refresh_grid_body(grid) {
	if (!grid) {
		return;
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
	const $scroller = $w.find('.form-grid-container').first();
	const $body = $w.find('.dt-scrollable, .form-grid .grid-body').first();
	const $head = $w.find('.grid-heading-row, .dt-row-header, .dt-header').first();
	const sl = ($scroller.length ? $scroller.scrollLeft() : $body.scrollLeft()) || 0;
	if ($scroller.length) {
		if (Math.abs(($scroller.scrollLeft() || 0) - sl) > 0.5) {
			$scroller.scrollLeft(sl);
		}
	}
	if ($body.length && $head.length) {
		if (Math.abs(($head.scrollLeft() || 0) - sl) > 0.5) {
			$head.scrollLeft(sl);
		}
		if (Math.abs(($body.scrollLeft() || 0) - sl) > 0.5) {
			$body.scrollLeft(sl);
		}
	}
}

/** frm.doc has child rows but the grid body is empty — reload field from doc. */
function cg_ensure_grid_rows_from_doc(frm, tableFieldname) {
	if (!frm || !tableFieldname) {
		return false;
	}
	const docRows = frm.doc && frm.doc[tableFieldname];
	if (!docRows || !docRows.length) {
		return false;
	}
	const fd = frm.fields_dict && frm.fields_dict[tableFieldname];
	const grid = fd && fd.grid;
	if (!grid) {
		return false;
	}
	if ((grid.grid_rows || []).length > 0) {
		return false;
	}
	try {
		frm._cg_repopulating_grid = tableFieldname;
		frm.refresh_field(tableFieldname);
		return true;
	} catch (e) {
		return false;
	} finally {
		setTimeout(function () {
			if (frm._cg_repopulating_grid === tableFieldname) {
				delete frm._cg_repopulating_grid;
			}
		}, 300);
	}
}

function cg_repopulate_grid_if_empty(grid, fd) {
	const frm = grid && (grid.frm || (fd && fd.frm));
	const fieldname = (grid && grid.df && grid.df.fieldname) || (fd && fd.df && fd.df.fieldname);
	if (!frm || !fieldname) {
		return false;
	}
	return cg_ensure_grid_rows_from_doc(frm, fieldname);
}

/** Tear down row DOM / datatable so the next refresh rebuilds from current grid.docfields. */
function cg_teardown_grid_rows(grid) {
	if (!grid) {
		return;
	}
	try {
		if (grid.datatable && typeof grid.datatable.destroy === 'function') {
			grid.datatable.destroy();
		}
		grid.datatable = null;
	} catch (e) {
		/* ignore */
	}
	try {
		(grid.grid_rows || []).forEach((gr) => {
			if (gr && typeof gr.remove === 'function') {
				gr.remove();
			}
		});
		grid.grid_rows = [];
	} catch (e) {
		/* ignore */
	}
	try {
		if (grid.wrapper) {
			grid.wrapper.find('.grid-body .rows').empty();
		}
	} catch (e) {
		/* ignore */
	}
}

function cg_realign_grid(grid, fd, options, columnOrder) {
	if (!grid) {
		return;
	}
	const opts = options || {};
	const fullRefresh = opts.fullRefresh === true;
	const order =
		columnOrder ||
		(grid.docfields || [])
			.filter((df) => df && df.in_list_view && !cg_skip_field(df))
			.map((df) => df.fieldname);
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
	if (cg_visible_column_count(grid) < 1) {
		return;
	}
	try {
		if (typeof grid.refresh_header === 'function') {
			grid.refresh_header();
		}
	} catch (e) {
		/* ignore */
	}
	// fullRefresh teardown breaks Frappe child grids (rows never rebuild from frm.doc).
	// Planning sheet uses column reorder + body refresh only; SPR never passes fullRefresh.
	if (false && fullRefresh) {
		try {
			if (order.length) {
				cg_reorder_grid_docfields(grid, null, order);
			}
			cg_teardown_grid_rows(grid);
			if (typeof grid.setup_visible_columns === 'function') {
				grid.setup_visible_columns();
			}
			if (typeof grid.refresh_header === 'function') {
				grid.refresh_header();
			}
			if (typeof grid.refresh === 'function') {
				grid.refresh();
			} else {
				cg_refresh_grid_body(grid);
			}
			const repopulated = cg_repopulate_grid_if_empty(grid, fd);
			if (order.length) {
				cg_reorder_all_row_docfields(grid, order);
			}
			const showSet = {};
			(grid.docfields || []).forEach((df) => {
				if (df && df.fieldname && df.in_list_view && !cg_skip_field(df)) {
					showSet[df.fieldname] = 1;
				}
			});
			if (Object.keys(showSet).length) {
				cg_sync_row_docfields(grid, showSet);
				cg_refresh_grid_body(grid);
			}
			if (repopulated && order.length) {
				setTimeout(function () {
					try {
						cg_reorder_all_row_docfields(grid, order);
						cg_sync_row_docfields(grid, showSet);
						cg_refresh_grid_body(grid);
						cg_sync_header_scroll(fd);
					} catch (e) {
						/* ignore */
					}
				}, 80);
			}
		} catch (e) {
			cg_refresh_grid_body(grid);
			cg_repopulate_grid_if_empty(grid, fd);
		}
	} else {
		if (order.length) {
			cg_reorder_all_row_docfields(grid, order);
			const showSet = {};
			order.forEach((fn) => {
				showSet[fn] = 1;
			});
			cg_sync_row_docfields(grid, showSet);
		}
		cg_refresh_grid_body(grid);
	}
	cg_sync_header_scroll(fd);
	if (fd && fd.$wrapper && fd.$wrapper.length) {
		requestAnimationFrame(function () {
			cg_sync_header_scroll(fd);
		});
	}
}

production_entry.grid_columns = {
	SKIP_FIELD_TYPES: CG_SKIP_FIELD_TYPES,

	reset_all_list_view: cg_reset_all_list_view,

	ordered_show_fields: cg_ordered_show_fields,

	teardown_grid_rows: cg_teardown_grid_rows,

	/**
	 * @param {object} frm - Frappe form
	 * @param {string} tableFieldname - parent child table fieldname
	 * @param {string} metaDoctype - child doctype name
	 * @param {string[]} showFieldnames - fieldnames to show; array order is preserved when provided
	 * @param {object} [options] - { fullRefresh: true } for Planning sheet grids only
	 */
	apply(frm, tableFieldname, metaDoctype, showFieldnames, options) {
		try {
			if (frm && frm._cg_repopulating_grid === tableFieldname) {
				return;
			}
			const fd = frm && frm.fields_dict && frm.fields_dict[tableFieldname];
			if (!fd || !fd.grid || !metaDoctype) {
				return;
			}
			const grid = fd.grid;
			try {
				delete grid.user_settings;
				grid.visible_columns = null;
				(grid.grid_rows || []).forEach((gr) => {
					if (gr && gr.grid) {
						delete gr.grid.user_settings;
					}
				});
			} catch (e) {
				/* ignore */
			}
			const preferred = (showFieldnames || []).filter((fn) => cg_field_exists(metaDoctype, fn));
			if (!preferred.length) {
				return;
			}
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
			// Sync each visible docfield on the grid instance (header + row templates use these).
			ordered.forEach((fn) => {
				const gdf = (grid.docfields || []).find((d) => d && d.fieldname === fn);
				const mdf = frappe.meta.get_docfield(metaDoctype, fn);
				if (gdf && mdf) {
					gdf.in_list_view = 1;
					gdf.hidden = 0;
				}
			});
			(grid.docfields || []).forEach((df) => {
				if (!df || cg_skip_field(df) || showSet[df.fieldname]) {
					return;
				}
				df.in_list_view = 0;
			});
			cg_reorder_all_row_docfields(grid, ordered);
			cg_sync_row_docfields(grid, showSet);
			cg_realign_grid(grid, fd, { fullRefresh: false }, ordered);
			cg_ensure_grid_rows_from_doc(frm, tableFieldname);
		} catch (e) {
			if (typeof console !== 'undefined' && console.warn) {
				console.warn('grid_columns.apply failed', tableFieldname, e);
			}
		}
	},

	ensure_rows_from_doc(frm, tableFieldname) {
		return cg_ensure_grid_rows_from_doc(frm, tableFieldname);
	},

	realign(frm, tableFieldname, options, columnOrder) {
		const fd = frm && frm.fields_dict && frm.fields_dict[tableFieldname];
		if (!fd || !fd.grid) {
			return;
		}
		const order =
			columnOrder ||
			(fd.grid.docfields || [])
				.filter((df) => df && df.in_list_view && !cg_skip_field(df))
				.map((df) => df.fieldname);
		cg_realign_grid(fd.grid, fd, options, order);
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
