/* global frappe, __ */

const BREAKDOWN_API = "production_entry.production_planning.shift_breakdown_api";

function _esc(s) {
	return frappe.utils.escape_html(String(s ?? ""));
}

function _args(ctx) {
	return {
		run_date: ctx.run_date || "",
		shift: ctx.shift || "",
		custom_unit: ctx.custom_unit || "",
		gsm_shift_session: ctx.gsm_shift_session || "",
		breakdown_name: ctx.breakdown_name || "",
	};
}

function _allBreakdownHtml(rows) {
	if (!rows.length) {
		return `<div class="gbd-empty">${__("No breakdowns recorded for this shift yet.")}</div>`;
	}
	const body = rows
		.map(
			(r, i) => `<tr class="${r.open ? "gbd-open" : ""}">
			<td>${i + 1}</td>
			<td>${_esc(r.stop_clock || r.stop_time || "")}</td>
			<td>${_esc(r.on_clock || r.on_time || (r.open ? __("Open") : ""))}</td>
			<td>${_esc(r.reason || "")}</td>
			<td>${_esc(r.remarks || "")}</td>
		</tr>`
		)
		.join("");
	return `<table class="table table-bordered table-sm gbd-table">
		<thead><tr>
			<th>#</th>
			<th>${__("Stop Time")}</th>
			<th>${__("On Time")}</th>
			<th>${__("Reason")}</th>
			<th>${__("Remarks")}</th>
		</tr></thead>
		<tbody>${body}</tbody>
	</table>`;
}

function _dialogHtml(payload, mode) {
	const rows = payload.rows || [];
	const openRow = payload.open_row;
	let action = "";
	if (mode === "stop-form") {
		action = `<div class="gbd-action">
			<div class="gbd-clock">${__("Machine Stop Time")}: <strong id="gbd-stop-clock"></strong></div>
			<p class="text-muted">${__("Select the reason and enter remarks, then save.")}</p>
		</div>`;
	} else if (openRow) {
		action = `<div class="gbd-action">
			<p>${__("Machine is stopped since")} <strong>${_esc(openRow.stop_clock || openRow.stop_time)}</strong>
			— ${_esc(openRow.reason || "")}</p>
			<button type="button" class="btn btn-primary" id="gbd-machine-on">${__("Machine On")}</button>
		</div>`;
	} else {
		action = `<div class="gbd-action">
			<button type="button" class="btn btn-danger" id="gbd-machine-stop">${__("Machine Stop")}</button>
		</div>`;
	}
	return `<style>
		.gbd-wrap { display:flex; flex-direction:column; gap:14px; }
		.gbd-action { padding:12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; }
		.gbd-clock { font-size:15px; margin-bottom:8px; }
		.gbd-section { font-weight:700; font-size:13px; color:#334155; }
		.gbd-table { margin:0; font-size:12px; }
		.gbd-table .gbd-open { background:#fff7ed; }
		.gbd-empty { padding:16px; text-align:center; color:#64748b; }
	</style>
	<div class="gbd-wrap">
		${action}
		<div>
			<div class="gbd-section">${__("All Breakdown")}</div>
			${_allBreakdownHtml(rows)}
		</div>
	</div>`;
}

export async function openGsmBreakdownDialog(opts = {}) {
	const ctx = {
		run_date: opts.run_date || opts.runDate || "",
		shift: opts.shift || "",
		custom_unit: (opts.custom_unit || opts.headerUnit || "").trim(),
		gsm_shift_session: opts.gsm_shift_session || opts.shiftSessionId || "",
		breakdown_name: "",
	};
	if (!ctx.custom_unit) {
		frappe.msgprint(__("Select a unit first."));
		return;
	}
	if (!ctx.run_date || !ctx.shift) {
		frappe.msgprint(__("Set Run Date and Shift first."));
		return;
	}

	const load = async () => {
		const res = await frappe.call({
			method: `${BREAKDOWN_API}.get_shift_breakdown`,
			args: _args(ctx),
		});
		const msg = res.message || {};
		ctx.breakdown_name = msg.name || ctx.breakdown_name;
		return msg;
	};

	let payload = await load();
	let mode = payload.open_row ? "on" : "idle";

	const reasonOptions = (payload.reasons || []).join("\n");
	const d = new frappe.ui.Dialog({
		title: `${__("Breakdown")} — ${ctx.run_date} · ${ctx.shift} · ${ctx.custom_unit}`,
		size: "large",
		fields: [
			{ fieldname: "body_html", fieldtype: "HTML" },
			{
				fieldname: "reason",
				label: __("Reason"),
				fieldtype: "Select",
				options: reasonOptions,
				hidden: 1,
				reqd: 0,
			},
			{
				fieldname: "remarks",
				label: __("Remarks"),
				fieldtype: "Small Text",
				hidden: 1,
			},
		],
	});

	const render = () => {
		d.fields_dict.body_html.$wrapper.html(_dialogHtml(payload, mode));
		const showForm = mode === "stop-form";
		d.set_df_property("reason", "hidden", showForm ? 0 : 1);
		d.set_df_property("remarks", "hidden", showForm ? 0 : 1);
		if (showForm) {
			d.get_primary_btn().show().text(__("Save Stop"));
			const clock = new Date();
			const hh = String(clock.getHours()).padStart(2, "0");
			const mm = String(clock.getMinutes()).padStart(2, "0");
			d.fields_dict.body_html.$wrapper.find("#gbd-stop-clock").text(`${hh}:${mm}`);
		} else {
			d.get_primary_btn().hide();
		}
		d.fields_dict.body_html.$wrapper.find("#gbd-machine-stop").on("click", () => {
			mode = "stop-form";
			render();
		});
		d.fields_dict.body_html.$wrapper.find("#gbd-machine-on").on("click", async () => {
			d.get_primary_btn().prop("disabled", true);
			try {
				const res = await frappe.call({
					method: `${BREAKDOWN_API}.record_machine_on`,
					args: _args(ctx),
				});
				payload = res.message || payload;
				ctx.breakdown_name = payload.name || ctx.breakdown_name;
				mode = payload.open_row ? "on" : "idle";
				frappe.show_alert({
					message: __("Machine On recorded at {0}", [payload.recorded_on || ""]),
					indicator: "green",
				});
				render();
			} finally {
				d.get_primary_btn().prop("disabled", false);
			}
		});
	};

	d.set_primary_action(__("Save Stop"), async () => {
		const reason = d.get_value("reason");
		if (!reason) {
			frappe.msgprint(__("Select a breakdown reason."));
			return;
		}
		d.get_primary_btn().prop("disabled", true);
		try {
			const res = await frappe.call({
				method: `${BREAKDOWN_API}.record_machine_stop`,
				args: {
					..._args(ctx),
					reason,
					remarks: d.get_value("remarks") || "",
				},
			});
			payload = res.message || payload;
			ctx.breakdown_name = payload.name || ctx.breakdown_name;
			mode = payload.open_row ? "on" : "idle";
			d.set_value("reason", "");
			d.set_value("remarks", "");
			frappe.show_alert({
				message: __("Machine Stop recorded at {0}", [payload.recorded_stop || ""]),
				indicator: "orange",
			});
			render();
		} finally {
			d.get_primary_btn().prop("disabled", false);
		}
	});

	d.show();
	render();
}

frappe.provide("production_entry.gsm_breakdown");
production_entry.gsm_breakdown.openGsmBreakdownDialog = openGsmBreakdownDialog;
