// Shared SPR label + doc helpers — desk SPR form and GSM Production Entry use the same paths.
frappe.provide("production_entry.spr_label");

const _WASTAGE_LABEL_FN_CANDIDATES = [
	"print_wastage_label_flow",
	"generate_wastage_sticker_flow",
	"print_patty_wastage_label",
];

const _WASTAGE_CHILD_DOCTYPES = {
	custom_running_patty_wastage: "Running Patty Wastage Row",
	custom_roll_waste: "Roll Waste Row",
};

function _sprLocals() {
	if (typeof locals !== "undefined" && locals) {
		return locals;
	}
	if (typeof window !== "undefined") {
		window.locals = window.locals || {};
		return window.locals;
	}
	return {};
}

function _promisifyModel(method, ...args) {
	return new Promise((resolve) => {
		if (!frappe.model || typeof frappe.model[method] !== "function") {
			resolve();
			return;
		}
		frappe.model[method](...args, () => resolve());
	});
}

function _docMissingChildTables(doc, requireTables) {
	if (!doc || !requireTables || !requireTables.length) {
		return false;
	}
	return requireTables.some((fieldname) => fieldname && !Array.isArray(doc[fieldname]));
}

production_entry.spr_label.load_spr_doc = async function (sprName, options = {}) {
	const spr = String(sprName || "").trim();
	if (!spr) {
		return null;
	}
	const forceRefresh = !!(options && options.forceRefresh);
	const requireTables = (options && options.requireTables) || [];
	let doc = null;
	if (!forceRefresh) {
		try {
			doc = frappe.get_doc("Shaft Production Run", spr);
		} catch (e) {
			doc = null;
		}
		if (doc && Array.isArray(doc.items) && !_docMissingChildTables(doc, requireTables)) {
			return doc;
		}
	}
	await _promisifyModel("with_doc", "Shaft Production Run", spr);
	try {
		doc = frappe.get_doc("Shaft Production Run", spr);
	} catch (e) {
		doc = null;
	}
	if (doc && Array.isArray(doc.items) && !forceRefresh && !_docMissingChildTables(doc, requireTables)) {
		return doc;
	}
	const res = await frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Shaft Production Run", name: spr },
	});
	doc = res.message || null;
	if (!doc) {
		return null;
	}
	const loc = _sprLocals();
	if (!loc["Shaft Production Run"]) {
		loc["Shaft Production Run"] = {};
	}
	loc["Shaft Production Run"][spr] = doc;
	return doc;
};

production_entry.spr_label.find_child_row = function (doc, rowName, preferredField) {
	const child = String(rowName || "").trim();
	if (!doc || !child) {
		return null;
	}
	const preferred = String(preferredField || "").trim();
	if (preferred && Array.isArray(doc[preferred])) {
		const hit = doc[preferred].find((r) => r && r.name === child);
		if (hit) {
			return { row: hit, tableField: preferred };
		}
	}
	for (const [fieldname, rows] of Object.entries(doc)) {
		if (!Array.isArray(rows)) {
			continue;
		}
		const hit = rows.find((r) => r && r.name === child);
		if (hit) {
			return { row: hit, tableField: fieldname };
		}
	}
	return null;
};

production_entry.spr_label.sync_child_row_locals = function (doc, rowName, tableField) {
	const loc = _sprLocals();
	const found = production_entry.spr_label.find_child_row(doc, rowName, tableField);
	if (!found) {
		return null;
	}
	const childDoctype =
		_WASTAGE_CHILD_DOCTYPES[found.tableField] ||
		(tableField === "custom_roll_waste" ? "Roll Waste Row" : "Running Patty Wastage Row");
	if (!loc[childDoctype]) {
		loc[childDoctype] = {};
	}
	loc[childDoctype][rowName] = found.row;
	if (doc && found.tableField && !Array.isArray(doc[found.tableField])) {
		doc[found.tableField] = [];
	}
	if (doc && found.tableField) {
		const rows = doc[found.tableField];
		if (!rows.find((r) => r && r.name === rowName)) {
			rows.push(found.row);
		}
	}
	return found.row;
};

production_entry.spr_label.sync_item_row_locals = function (doc, rowName) {
	const loc = _sprLocals();
	if (!loc["Shaft Production Run Item"]) {
		loc["Shaft Production Run Item"] = {};
	}
	const row = (doc.items || []).find((r) => r.name === rowName);
	if (row) {
		loc["Shaft Production Run Item"][rowName] = row;
	}
	return row || null;
};

production_entry.spr_label.build_frm = function (doc) {
	return { doc, doctype: "Shaft Production Run" };
};

/** Same flow as desk Shaft Production Run Item → print_sticker. */
production_entry.spr_label.print_roll = async function (sprName, rowName) {
	const spr = String(sprName || "").trim();
	const row = String(rowName || "").trim();
	if (!spr || !row) {
		frappe.msgprint(__("SPR and roll row are required to print the label."));
		return;
	}
	await _promisifyModel("with_doctype", "Shaft Production Run Item");
	const doc = await production_entry.spr_label.load_spr_doc(spr);
	if (!doc) {
		frappe.msgprint(__("Could not load SPR for label print."));
		return;
	}
	const itemRow = production_entry.spr_label.sync_item_row_locals(doc, row);
	if (!itemRow) {
		frappe.msgprint(__("Roll row not found on SPR."));
		return;
	}
	const frm = production_entry.spr_label.build_frm(doc);
	if (typeof frappe.generate_sticker_flow === "function") {
		frappe.generate_sticker_flow(row, frm);
		return;
	}
	if (
		production_entry.spr_roll_label_print &&
		typeof production_entry.spr_roll_label_print.open === "function"
	) {
		production_entry.spr_roll_label_print.open(spr, row);
		return;
	}
	frappe.msgprint(__("Label print helper not loaded."));
};

/** Running patty / roll waste labels — desk SPR flow with GSM-safe doc load. */
production_entry.spr_label.print_wastage = async function (sprName, childRowName, tableField, rowData) {
	const spr = String(sprName || "").trim();
	const child = String(childRowName || "").trim();
	tableField = tableField || "custom_running_patty_wastage";
	if (!spr || !child) {
		frappe.msgprint(__("SPR and wastage row are required."));
		return;
	}
	const doc = await production_entry.spr_label.load_spr_doc(spr, {
		forceRefresh: true,
		requireTables: [tableField],
	});
	if (!doc) {
		frappe.msgprint(__("Could not load SPR for wastage label print."));
		return;
	}
	let wastageRow = production_entry.spr_label.sync_child_row_locals(doc, child, tableField);
	if (!wastageRow && rowData && typeof rowData === "object") {
		wastageRow = rowData;
	}
	const frm = production_entry.spr_label.build_frm(doc);
	if (wastageRow && typeof frappe.print_wastage_row_direct === "function") {
		frappe.print_wastage_row_direct(wastageRow, frm, tableField);
		return;
	}
	for (const fnName of _WASTAGE_LABEL_FN_CANDIDATES) {
		if (typeof frappe[fnName] === "function") {
			frappe[fnName](child, frm, tableField);
			return;
		}
	}
	if (wastageRow && typeof frappe.print_wastage_row_direct === "function") {
		frappe.print_wastage_row_direct(wastageRow, frm, tableField);
		return;
	}
	frappe.msgprint(
		__(
			"Wastage label print is not available here. Open the SPR form and use Print Label on the wastage row."
		)
	);
};
