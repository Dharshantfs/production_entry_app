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

function cg_grid_header_matches_rows(grid) {
	if (!grid) {
		return true;
	}
	const headerOrder = (grid.docfields || [])
		.filter((df) => df && df.in_list_view && !cg_skip_field(df))
		.map((df) => df.fieldname);
	const gr = (grid.grid_rows || [])[0];
	if (!gr) {
		return true;
	}
	const rowOrder = (gr.docfields || [])
		.filter((df) => df && df.in_list_view && !cg_skip_field(df))
		.map((df) => df.fieldname);
	return headerOrder.length === rowOrder.length
		&& headerOrder.every((fn, i) => rowOrder[i] === fn);
}

/** Rebuild data column DOM only — never empty full row wrapper (removes checkbox/index). */
function cg_remount_grid_rows(grid) {
	if (!grid || !(grid.grid_rows || []).length) {
		return;
	}
	(grid.grid_rows || []).forEach((gr) => {
		if (!gr || !gr.wrapper || !gr.wrapper.length) {
			return;
		}
		try {
			gr.wrapper.find('[data-fieldname]').each(function () {
				const $col = $(this).closest('.col, .grid-static-col');
				if ($col.length) {
					$col.remove();
				}
			});
			if (gr.columns && typeof gr.columns === 'object') {
				Object.keys(gr.columns).forEach((k) => {
					try {
						const col = gr.columns[k];
						if (col && col.$wrapper) {
							col.$wrapper.remove();
						}
					} catch (e) {
						/* ignore */
					}
				});
				gr.columns = {};
			}
			const visible = (gr.docfields || []).filter((df) => df && df.in_list_view && !cg_skip_field(df));
			if (typeof gr.make_column === 'function') {
				visible.forEach((df) => {
					try {
						gr.make_column(df);
					} catch (e) {
						/* ignore */
					}
				});
			}
			if (typeof gr.refresh === 'function') {
				gr.refresh();
			}
		} catch (e) {
			/* ignore */
		}
	});
}

function cg_sync_header_scroll(fd) {
	if (!fd || !fd.$wrapper || !fd.$wrapper.length) {
		return;
	}
	const $w = fd.$wrapper;
	const $scroller = $w.find('.form-grid-container').first();
	const $body = $w.find('.dt-scrollable, .form-grid .grid-body').first();
	const $head = $w.find('.grid-heading-row, .dt-row-header, .dt-header').first();
	if ($scroller.length) {
		return;
	}
	if (!$body.length || !$head.length) {
		return;
	}
	const bodySl = $body.scrollLeft() || 0;
	const headSl = $head.scrollLeft() || 0;
	if (Math.abs(headSl - bodySl) > 0.5) {
		$head.scrollLeft(bodySl);
	}
}

function cg_grid_rows_look_broken(grid) {
	if (!grid) {
		return true;
	}
	const rows = grid.grid_rows || [];
	if (!rows.length) {
		return true;
	}
	return rows.some((gr) => {
		if (!gr || !gr.wrapper || !gr.wrapper.length) {
			return true;
		}
		const expected = (gr.docfields || []).filter((df) => df && df.in_list_view && !cg_skip_field(df)).length;
		if (!expected) {
			return false;
		}
		const dataCols = gr.wrapper.find('[data-fieldname]').length;
		return dataCols < expected;
	});
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
	const gridLen = (grid.grid_rows || []).length;
	const needsReload = gridLen === 0 || gridLen < docRows.length;
	if (!needsReload) {
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

function cg_build_show_set_from_order(order) {
	const showSet = {};
	(order || []).forEach((fn) => {
		showSet[fn] = 1;
	});
	return showSet;
}

function cg_sync_grid_to_column_order(grid, order) {
	if (!grid || !order || !order.length) {
		return;
	}
	cg_reorder_grid_docfields(grid, null, order);
	cg_reorder_all_row_docfields(grid, order);
	cg_sync_row_docfields(grid, cg_build_show_set_from_order(order));
}

function cg_mirror_grid_docfields_to_rows(grid) {
	if (!grid || !(grid.grid_rows || []).length) {
		return;
	}
	const masterOrder = (grid.docfields || []).map((df) => df && df.fieldname).filter(Boolean);
	(grid.grid_rows || []).forEach((gr) => {
		if (!gr) {
			return;
		}
		const rowByName = {};
		(gr.docfields || []).forEach((df) => {
			if (df && df.fieldname) {
				rowByName[df.fieldname] = df;
			}
		});
		(grid.docfields || []).forEach((gdf) => {
			if (!gdf || !gdf.fieldname) {
				return;
			}
			const rdf = rowByName[gdf.fieldname];
			if (rdf) {
				rdf.in_list_view = gdf.in_list_view;
				rdf.hidden = gdf.hidden;
			}
		});
		if (masterOrder.length) {
			gr.docfields = cg_reorder_docfields_array(gr.docfields || [], masterOrder);
		}
	});
}

function cg_needs_column_fix(grid) {
	if (!grid) {
		return false;
	}
	return !cg_grid_header_matches_rows(grid) || cg_grid_rows_look_broken(grid);
}

/** Sync row docfields to header order; remount DOM only when still misaligned. */
function cg_fix_row_columns(grid, showSet, order) {
	if (!grid || !order || !order.length) {
		return false;
	}
	cg_sync_grid_to_column_order(grid, order);
	cg_mirror_grid_docfields_to_rows(grid);
	if (!cg_needs_column_fix(grid)) {
		cg_sync_row_docfields(grid, showSet);
		cg_refresh_grid_body(grid);
		return false;
	}
	cg_remount_grid_rows(grid);
	cg_mirror_grid_docfields_to_rows(grid);
	cg_sync_row_docfields(grid, showSet);
	cg_refresh_grid_body(grid);
	return cg_needs_column_fix(grid);
}

function cg_realign_grid(grid, fd, options, columnOrder) {
	if (!grid) {
		return;
	}
	const order =
		columnOrder ||
		(grid.docfields || [])
			.filter((df) => df && df.in_list_view && !cg_skip_field(df))
			.map((df) => df.fieldname);
	const showSet = cg_build_show_set_from_order(order);
	if (order.length) {
		cg_sync_grid_to_column_order(grid, order);
	}
	try {
		if (grid.visible_columns) {
			delete grid.visible_columns;
		}
		delete grid.user_settings;
		grid.user_defined_columns = null;
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
	try {
		if (typeof grid.refresh === 'function') {
			grid.refresh();
		} else {
			cg_refresh_grid_body(grid);
		}
	} catch (e) {
		cg_refresh_grid_body(grid);
	}
	let needsFullRebuild = false;
	if ((grid.grid_rows || []).length > 0 && order.length) {
		needsFullRebuild = cg_fix_row_columns(grid, showSet, order);
	} else if (order.length) {
		cg_sync_grid_to_column_order(grid, order);
	}
	try {
		if (typeof grid.refresh_header === 'function') {
			grid.refresh_header();
		}
	} catch (e) {
		/* ignore */
	}
	const frm = grid.frm || (fd && fd.frm);
	const tableField = (fd && fd.df && fd.df.fieldname) || (grid.df && grid.df.fieldname) || '';
	if (frm && tableField && needsFullRebuild && !frm._cg_repopulating_grid) {
		try {
			frm._cg_repopulating_grid = tableField;
			cg_teardown_grid_rows(grid);
			frm.refresh_field(tableField);
			setTimeout(function () {
				delete frm._cg_repopulating_grid;
				const fd2 = frm.fields_dict && frm.fields_dict[tableField];
				const g2 = fd2 && fd2.grid;
				if (g2 && order.length) {
					cg_sync_grid_to_column_order(g2, order);
					cg_mirror_grid_docfields_to_rows(g2);
					if (typeof g2.setup_visible_columns === 'function') {
						g2.setup_visible_columns();
					}
					if (typeof g2.refresh_header === 'function') {
						g2.refresh_header();
					}
					cg_fix_row_columns(g2, showSet, order);
					if (typeof g2.refresh_header === 'function') {
						g2.refresh_header();
					}
					cg_sync_header_scroll(fd2);
				}
			}, 120);
		} catch (e) {
			delete frm._cg_repopulating_grid;
		}
	} else if (frm && tableField) {
		const docRows = frm.doc && frm.doc[tableField];
		const gridLen = (grid.grid_rows || []).length;
		if (docRows && docRows.length && gridLen === 0) {
			cg_ensure_grid_rows_from_doc(frm, tableField);
		}
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
			const ordered = preferred.slice();
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
			cg_realign_grid(grid, fd, options, ordered);
			if (cg_needs_column_fix(grid) && ordered.length) {
				cg_fix_row_columns(grid, showSet, ordered);
				if (typeof grid.refresh_header === 'function') {
					grid.refresh_header();
				}
				cg_sync_header_scroll(fd);
			} else if (ordered.length && (grid.grid_rows || []).length) {
				cg_mirror_grid_docfields_to_rows(grid);
				cg_sync_row_docfields(grid, showSet);
			}
			if (
				options &&
				options.fullRefresh &&
				ordered.length &&
				(grid.grid_rows || []).length
			) {
				cg_remount_grid_rows(grid);
				cg_mirror_grid_docfields_to_rows(grid);
				cg_sync_row_docfields(grid, showSet);
				cg_refresh_grid_body(grid);
				if (typeof grid.refresh_header === 'function') {
					grid.refresh_header();
				}
				cg_sync_header_scroll(fd);
			}
			const docRows = frm.doc && frm.doc[tableFieldname];
			if (docRows && docRows.length && !(grid.grid_rows || []).length) {
				cg_ensure_grid_rows_from_doc(frm, tableFieldname);
			}
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

	/**
	 * After Frappe grid.refresh() rebuilds rows from meta order, re-sync row docfields to match headers.
	 */
	install_refresh_column_guard(frm, tableFieldname, columnOrderGetter) {
		const fd = frm && frm.fields_dict && frm.fields_dict[tableFieldname];
		const grid = fd && fd.grid;
		if (!grid || grid._cg_refresh_guard || typeof columnOrderGetter !== 'function') {
			return;
		}
		grid._cg_refresh_guard = true;
		const origRefresh = grid.refresh && grid.refresh.bind(grid);
		if (typeof origRefresh !== 'function') {
			return;
		}
		grid.refresh = function cgGuardedGridRefresh() {
			const order = columnOrderGetter() || [];
			if (order.length) {
				cg_sync_grid_to_column_order(grid, order);
			}
			const ret = origRefresh.apply(this, arguments);
			try {
				if (order.length && (grid.grid_rows || []).length > 0) {
					cg_fix_row_columns(grid, cg_build_show_set_from_order(order), order);
					if (typeof grid.refresh_header === 'function') {
						grid.refresh_header();
					}
					cg_sync_header_scroll(fd);
				}
			} catch (e) {
				/* ignore */
			}
			return ret;
		};
	},

	sync_grid_to_column_order: cg_sync_grid_to_column_order,

	mirror_grid_docfields_to_rows: cg_mirror_grid_docfields_to_rows,

	header_matches_rows: cg_grid_header_matches_rows,

	remount_grid_rows: cg_remount_grid_rows,
};
