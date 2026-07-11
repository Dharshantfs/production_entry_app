/* global frappe, __ */

const QC_DOCTYPE = "Quality Checking";
const TESTING_TYPES = {
	gsm: "GSM Testing",
	tensile: "Tensile Testing",
};

function cint(v) {
	const n = parseInt(v, 10);
	return Number.isFinite(n) ? n : 0;
}

function sprJobIds(doc) {
	const jobs = doc?.shaft_jobs || [];
	return (jobs || [])
		.map((j) => String(j.job_id || j.job || "").trim())
		.filter(Boolean);
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
	const ids = sprJobIds(doc);
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

async function loadSprDoc(sprName) {
	const res = await frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Shaft Production Run", name: sprName },
	});
	return res.message || {};
}

function pickSprJobRow(spr, jobId) {
	const jid = String(jobId || "").trim();
	return (spr.shaft_jobs || []).find((j) => String(j.job_id || j.job || "").trim() === jid) || null;
}

function latestRollForSprJob(spr, jobId) {
	const jid = String(jobId || "").trim();
	let best = null;
	let bestSuffix = -1;
	for (const row of spr.items || []) {
		if (String(row.job || "").trim() !== jid) {
			continue;
		}
		const batch = String(row.batch_no || "");
		const suffix = batch.includes("/") ? cint(batch.split("/").pop()) : cint(row.roll_no);
		if (suffix >= bestSuffix) {
			bestSuffix = suffix;
			best = row;
		}
	}
	return best;
}

async function openQualityCheckingDoc(sprName, testType, jobId) {
	if (!(await frappe.db.exists("DocType", QC_DOCTYPE))) {
		frappe.msgprint(
			__(
				"Quality Checking app is not installed on this site. Install the quality-check custom app."
			)
		);
		return;
	}

	const testingType = TESTING_TYPES[testType] || testType;
	const spr = await loadSprDoc(sprName);
	const jobRow = pickSprJobRow(spr, jobId);
	const latestRoll = latestRollForSprJob(spr, jobId);

	const existing = await frappe.db.get_list(QC_DOCTYPE, {
		filters: {
			shaft_production_run: sprName,
			testing_type: testingType,
			docstatus: 0,
		},
		fields: ["name"],
		limit: 1,
		order_by: "modified desc",
	});
	if (existing?.[0]?.name) {
		frappe.set_route("Form", QC_DOCTYPE, existing[0].name);
		return;
	}

	const defaults = {
		shaft_production_run: sprName,
		testing_type: testingType,
		unit: spr.custom_unit || spr.unit || "",
		shift: spr.shift || "",
		order_code: spr.custom_order_code || spr.order_code || "",
		quality: jobRow?.quality || latestRoll?.quality || "",
		color: jobRow?.color || latestRoll?.color || "",
		batch_no: latestRoll?.batch_no || "",
		roll_no: cint(latestRoll?.roll_no) || 0,
	};

	await new Promise((resolve, reject) => {
		frappe.model.with_doctype(QC_DOCTYPE, () => {
			try {
				const doc = frappe.model.get_new_doc(QC_DOCTYPE);
				Object.assign(doc, defaults);
				frappe.set_route("Form", QC_DOCTYPE, doc.name);
				resolve();
			} catch (e) {
				reject(e);
			}
		});
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
	await openQualityCheckingDoc(sprName, testType, resolvedJob);
}

frappe.provide("production_entry.spr_quality_check");

production_entry.spr_quality_check.openSprGsmTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "gsm", jobId);
production_entry.spr_quality_check.openSprTensileTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "tensile", jobId);
