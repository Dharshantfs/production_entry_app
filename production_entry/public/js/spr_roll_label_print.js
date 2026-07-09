// Shared roll label print — same Print Format as desk SPR (site Roll Production Label).
frappe.provide("production_entry.spr_roll_label_print");

production_entry.spr_roll_label_print = production_entry.spr_roll_label_print || {};

production_entry.spr_roll_label_print.open = function (sprName, rowName) {
	const spr = (sprName || "").trim();
	const row = (rowName || "").trim();
	if (!spr || !row) {
		frappe.msgprint(__("SPR and roll row are required to print the label."));
		return;
	}
	const fmt =
		(frappe.boot && frappe.boot.spr_roll_label_print_format) ||
		window.SPR_ROLL_LABEL_PRINT_FORMAT ||
		"Roll Production Label";
	const url =
		"/printview?doctype=" +
		encodeURIComponent("Shaft Production Run") +
		"&name=" +
		encodeURIComponent(spr) +
		"&format=" +
		encodeURIComponent(fmt) +
		"&no_letterhead=1&_row_name=" +
		encodeURIComponent(row);
	window.open(url, "_blank");
};
