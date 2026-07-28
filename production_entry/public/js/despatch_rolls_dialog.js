// Shared printable roll list dialog (Delivery Note items, Clubbing Sheet, etc.)

function jsb_show_despatch_rolls_dialog(args) {
	const rolls = args.rolls || [];
	const itemCode = args.item_code || "";
	const deliveryNote = args.delivery_note || "";
	const salesOrder = args.sales_order || "";
	const subtitle = salesOrder
		? __("SO: {0}", [salesOrder])
		: itemCode
			? __("Item: {0}", [itemCode])
			: "";
	const docRef = deliveryNote ? __("DN: {0}", [deliveryNote]) : subtitle;

	let html =
		"<style>" +
		".rolls-view { font-family: Arial, sans-serif !important; color: #000 !important; background: #fff !important; padding: 0; }" +
		".printable-area { width: 100%; max-width: 800px; margin: 0 auto; }" +
		".company-header-table { width: 100%; border-collapse: collapse; border: 2px solid #2e7d32; margin-bottom: 10px; table-layout: fixed; }" +
		".company-header-table td { padding: 10px; text-align: center; vertical-align: middle; }" +
		".company-header-table img { height: 60px; width: auto; margin-bottom: 5px; }" +
		".company-header-table h1 { font-size: 22px; font-weight: 900; margin: 0; text-transform: uppercase; color: #000; }" +
		".company-header-table .doc-title { font-size: 11px; font-weight: bold; text-transform: uppercase; border-top: 1px solid #ccc; margin-top: 5px; padding-top: 5px; }" +
		".info-row-table { width: 100%; border-collapse: collapse; margin-bottom: 10px; table-layout: fixed; }" +
		".info-row-table td { border: 1px solid #555 !important; padding: 0; text-align: center; }" +
		".info-box { height: 100%; display: block; }" +
		".info-label { background: #f57f17 !important; color: #fff !important; font-size: 8px; font-weight: 700; text-transform: uppercase; padding: 2px 5px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }" +
		".info-value { font-size: 11px; font-weight: 700; padding: 4px 5px; }" +
		".dt-table { width: 100%; border-collapse: collapse; border: 1px solid #000 !important; font-size: 10px; }" +
		".dt-table th { background: #ffb74d !important; border: 1px solid #000 !important; padding: 6px; font-weight: 700; text-transform: uppercase; -webkit-print-color-adjust: exact; print-color-adjust: exact; }" +
		".dt-table td { border: 1px solid #000 !important; padding: 5px 6px; text-align: center; vertical-align: middle; }" +
		".dt-table tfoot td { background: #c8e6c9 !important; border: 1px solid #000 !important; font-weight: bold; color: #1b5e20 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }" +
		".tr { text-align: right !important; }" +
		".fb { font-weight: 700 !important; }" +
		"@media print { .modal-header, .modal-footer { display: none !important; } .printable-area { width: 100% !important; margin: 0 !important; padding: 0 !important; } body { background: #fff !important; } }" +
		"</style>";

	html += '<div class="rolls-view printable-area" id="printable-rolls-area">';
	html +=
		'<table class="company-header-table"><tr><td>' +
		'<img src="/private/files/JSB LOGO63b225.png" alt="JSB Logo"><br>' +
		"<h1>Jayashree Spun Bond</h1>" +
		'<div class="doc-title">' +
		__("Despatch Roll List") +
		(docRef ? " | " + docRef : "") +
		"</div>" +
		"</td></tr></table>";

	html +=
		'<table class="info-row-table"><tr>' +
		'<td><div class="info-box"><div class="info-label">' +
		__("Date") +
		'</div><div class="info-value">' +
		frappe.datetime.nowdate() +
		"</div></div></td>" +
		'<td><div class="info-box"><div class="info-label">' +
		(salesOrder ? __("Order Code") : __("Item Code")) +
		'</div><div class="info-value">' +
		(salesOrder || itemCode || "—") +
		"</div></div></td>" +
		'<td><div class="info-box"><div class="info-label">' +
		__("No. of Rolls") +
		'</div><div class="info-value">' +
		rolls.length +
		"</div></div></td>" +
		'<td><div class="info-box"><div class="info-label">' +
		__("Report Type") +
		'</div><div class="info-value">' +
		(deliveryNote ? __("Delivery Note") : __("Order-Wise")) +
		"</div></div></td>" +
		"</tr></table>";

	html +=
		'<table class="dt-table"><thead><tr>' +
		"<th>#</th><th>" +
		__("Batch No") +
		"</th><th>" +
		__("Quality") +
		"</th><th>" +
		__("Color") +
		"</th><th>" +
		__("GSM") +
		"</th><th>" +
		__("Width (Inches)") +
		"</th><th>" +
		__("Mtrs") +
		"</th><th>" +
		__("Net Wt") +
		"</th><th>" +
		__("Gross Wt") +
		"</th></tr></thead><tbody>";

	let totalMtr = 0;
	let totalNet = 0;
	let totalGross = 0;
	for (let i = 0; i < rolls.length; i++) {
		const r = rolls[i];
		const mtr = flt(r.meter_roll || r.meter_per_roll || r.custom_meter || 0);
		const net = flt(r.net_weight);
		const gross = flt(r.gross_weight || r.net_weight + 2);
		const width =
			r.width_inch ||
			r.custom_width_inch ||
			(r.width_mm ? (flt(r.width_mm) / 25.4).toFixed(1) : "");
		totalMtr += mtr;
		totalNet += net;
		totalGross += gross;
		html +=
			"<tr>" +
			"<td>" +
			(i + 1) +
			"</td>" +
			'<td class="fb">' +
			(r.batch_no || "") +
			"</td>" +
			"<td>" +
			(r.quality || r.custom_quality || "") +
			"</td>" +
			"<td>" +
			(r.color || r.custom_color || "") +
			"</td>" +
			"<td>" +
			(r.gsm || r.custom_gsm || "") +
			"</td>" +
			"<td>" +
			(width || "-") +
			"</td>" +
			'<td class="tr">' +
			mtr.toFixed(1) +
			"</td>" +
			'<td class="tr">' +
			net.toFixed(2) +
			"</td>" +
			'<td class="tr">' +
			gross.toFixed(2) +
			"</td>" +
			"</tr>";
	}

	html +=
		"</tbody><tfoot><tr>" +
		'<td colspan="6" class="tr fb">' +
		__("TOTAL CONSOLIDATED DESPATCH") +
		"</td>" +
		'<td class="tr">' +
		totalMtr.toFixed(1) +
		"</td>" +
		'<td class="tr">' +
		totalNet.toFixed(2) +
		"</td>" +
		'<td class="tr">' +
		totalGross.toFixed(2) +
		"</td>" +
		"</tr></tfoot></table></div>";

	const dialogTitle = salesOrder
		? __("Rolls for Sales Order: {0}", [salesOrder])
		: __("Rolls for Item: {0}", [itemCode || "—"]);

	const d = new frappe.ui.Dialog({
		title: dialogTitle,
		fields: [{ fieldtype: "HTML", fieldname: "rolls_html", options: html }],
		size: "extra-large",
		primary_action_label: __("Print for Despatch"),
		primary_action() {
			const printWindow = window.open("", "_blank");
			printWindow.document.write("<html><head><title>Roll List</title>");
			printWindow.document.write(
				"<style>@page { size: A4 portrait; margin: 10mm; }</style>"
			);
			printWindow.document.write(html);
			printWindow.document.write("</body></html>");
			printWindow.document.close();
			setTimeout(() => {
				printWindow.print();
				printWindow.close();
			}, 500);
		},
	});
	d.show();
}
