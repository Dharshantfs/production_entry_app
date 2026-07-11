/* global frappe, __ */

const SPR_QC_API =
	"production_entry.production_planning.doctype.shaft_production_run.shaft_production_run";

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}

function sprJobIds(frmOrSpr) {
	const jobs = frmOrSpr?.doc?.shaft_jobs || frmOrSpr?.shaft_jobs || [];
	return (jobs || [])
		.map((j) => String(j.job_id || j.job || "").trim())
		.filter(Boolean);
}

function pickSprJobId(frm) {
	const ids = sprJobIds(frm);
	if (!ids.length) {
		return Promise.resolve("");
	}
	if (ids.length === 1) {
		return Promise.resolve(ids[0]);
	}
	return new Promise((resolve) => {
		frappe.prompt(
			[
				{
					fieldtype: "Select",
					fieldname: "job_id",
					label: __("Job"),
					options: ids.map((id) => ({ value: id, label: id })),
					reqd: 1,
				},
			],
			(values) => resolve(values.job_id || ids[0]),
			__("Quality Check — choose job"),
			__("Continue")
		);
	});
}

async function openRollProductionEntryForJob(sprName, jobId, testType) {
	const res = await frappe.call({
		method: `${SPR_QC_API}.get_or_create_roll_entry_for_job`,
		args: {
			shaft_production_run: sprName,
			job_id: jobId,
		},
	});
	const msg = res.message || {};
	if (msg.existing) {
		frappe.set_route("Form", "Roll Production Entry", msg.existing);
		return;
	}
	await new Promise((resolve, reject) => {
		frappe.model.with_doctype("Roll Production Entry", () => {
			try {
				const doc = frappe.model.get_new_doc("Roll Production Entry");
				doc.shaft_production_run = sprName;
				if (msg.production_plan) {
					doc.production_plan = msg.production_plan;
				}
				if (msg.job_id) {
					doc.job_id = msg.job_id;
				}
				(msg.items || []).forEach((item) => {
					const row = frappe.model.add_child(doc, "items");
					Object.assign(row, item);
				});
				if (testType) {
					doc.__spr_quality_test_type = testType;
				}
				frappe.set_route("Form", "Roll Production Entry", doc.name);
				resolve();
			} catch (e) {
				reject(e);
			}
		});
	});
}

async function resolveJobIdForSpr(sprName, jobId) {
	if (jobId) {
		return jobId;
	}
	const res = await frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Shaft Production Run", name: sprName },
	});
	const doc = res.message || {};
	const ids = sprJobIds({ doc });
	if (!ids.length) {
		return "";
	}
	if (ids.length === 1) {
		return ids[0];
	}
	return new Promise((resolve) => {
		frappe.prompt(
			[
				{
					fieldtype: "Select",
					fieldname: "job_id",
					label: __("Job"),
					options: ids.map((id) => ({ value: id, label: id })),
					reqd: 1,
				},
			],
			(values) => resolve(values.job_id || ids[0]),
			__("Quality Check — choose job"),
			__("Continue")
		);
	});
}

async function openSprQualityCheck(sprName, testType, jobId) {
	const resolvedJob = await resolveJobIdForSpr(sprName, jobId);
	const hook =
		window.__spr_quality_check &&
		typeof window.__spr_quality_check[testType] === "function"
			? window.__spr_quality_check[testType]
			: null;
	if (hook) {
		return hook(sprName, resolvedJob);
	}
	if (!resolvedJob) {
		frappe.msgprint(__("No jobs on this SPR — add a job first."));
		return;
	}
	await openRollProductionEntryForJob(sprName, resolvedJob, testType);
}

async function openSprQualityCheckFromForm(frm, testType) {
	if (!frm?.doc?.name) {
		frappe.msgprint(__("Save Shaft Production Run first."));
		return;
	}
	const jobId = await pickSprJobId(frm);
	if (!jobId) {
		frappe.msgprint(__("No jobs on this SPR."));
		return;
	}
	await openSprQualityCheck(frm.doc.name, testType, jobId);
}

function registerSprQualityCheckButtons(frm) {
	if (!frm || frm.is_new() || cint(frm.doc.docstatus) > 0) {
		return;
	}
	const group = __("Quality Check");
	if (typeof frm.remove_custom_button === "function") {
		try {
			frm.remove_custom_button(__("Start GSM Testing"), group);
		} catch (e) {}
		try {
			frm.remove_custom_button(__("Start Tensile Testing"), group);
		} catch (e) {}
	}
	frm.add_custom_button(
		__("Start GSM Testing"),
		() => openSprQualityCheckFromForm(frm, "gsm"),
		group
	);
	frm.add_custom_button(
		__("Start Tensile Testing"),
		() => openSprQualityCheckFromForm(frm, "tensile"),
		group
	);
}

frappe.provide("production_entry.spr_quality_check");

production_entry.spr_quality_check.openSprGsmTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "gsm", jobId);
production_entry.spr_quality_check.openSprTensileTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "tensile", jobId);
production_entry.spr_quality_check.registerSprQualityCheckButtons = registerSprQualityCheckButtons;

frappe.ui.form.on("Shaft Production Run", {
	refresh(frm) {
		registerSprQualityCheckButtons(frm);
	},
});
