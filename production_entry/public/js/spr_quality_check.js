/* global frappe, __ */

const QC_DOCTYPE = "Quality Checking";
const TESTING_TYPES = {
	// Legacy callers map to Round (same flow as before GSM testing)
	gsm: "Round Cutting GSM Test",
	round_gsm: "Round Cutting GSM Test",
	patty_gsm: "Patty Cutting GSM Test",
	tensile: "Tensile Testing",
};

const TEMPLATE_WIDTH_FIELDS = [
	"cutting_template_width",
	"custom_cutting_template_width",
];
const TEMPLATE_HEIGHT_FIELDS = [
	"cutting_template_height",
	"custom_cutting_template_height",
];

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

async function promptSprJobId(ids, title) {
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
			title || __("Quality Check — choose job"),
			__("Continue")
		);
	});
}

async function resolveJobIdForSpr(sprName, jobId) {
	const res = await frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Shaft Production Run", name: sprName },
	});
	const doc = res.message || {};
	const preferred = String(jobId || "").trim();
	if (preferred && rollsForSprJob(doc, preferred).length) {
		return preferred;
	}
	const rollJobIds = sprJobIdsWithRolls(doc);
	const shaftJobIds = sprJobIds(doc);
	const ids = rollJobIds.length ? rollJobIds : shaftJobIds;
	if (!ids.length) {
		return "";
	}
	if (preferred && ids.includes(preferred)) {
		return preferred;
	}
	return promptSprJobId(ids);
}

async function loadSprDoc(sprName) {
	const res = await frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Shaft Production Run", name: sprName },
	});
	return res.message || {};
}

function sprItemJobId(row) {
	return String(row?.job || row?.job_id || "").trim();
}

function sprJobIdsMatch(a, b) {
	const left = String(a || "").trim();
	const right = String(b || "").trim();
	if (!left || !right) {
		return false;
	}
	return left === right;
}

function pickSprJobRow(spr, jobId) {
	const jid = String(jobId || "").trim();
	return (
		(spr.shaft_jobs || []).find((j) => sprJobIdsMatch(j.job_id || j.job, jid)) || null
	);
}

function rollSuffix(row) {
	const batch = String(row?.batch_no || "");
	if (batch.includes("/")) {
		return cint(batch.split("/").pop());
	}
	return cint(row?.roll_no);
}

function rollsForSprJob(spr, jobId) {
	const jid = String(jobId || "").trim();
	return (spr.items || []).filter((row) => {
		if (!sprJobIdsMatch(sprItemJobId(row), jid)) {
			return false;
		}
		if (cint(row.is_wasted) || cint(row.is_bundle_row)) {
			return false;
		}
		return Boolean(String(row.batch_no || "").trim() || cint(row.roll_no));
	});
}

function sprJobIdsWithRolls(spr) {
	const ids = new Set();
	for (const row of spr.items || []) {
		if (cint(row.is_wasted) || cint(row.is_bundle_row)) {
			continue;
		}
		if (!String(row.batch_no || "").trim() && !cint(row.roll_no)) {
			continue;
		}
		const jid = sprItemJobId(row);
		if (jid) {
			ids.add(jid);
		}
	}
	return [...ids];
}

async function promptRollForSprJob(spr, jobId) {
	const rolls = rollsForSprJob(spr, jobId);
	if (!rolls.length) {
		return null;
	}
	if (rolls.length === 1) {
		return rolls[0];
	}
	const options = rolls.map((row) => {
		const batch = String(row.batch_no || "").trim();
		const suffix = rollSuffix(row);
		const label = batch || `Roll ${suffix || row.idx || ""}`;
		return { value: batch || String(row.name || row.idx || suffix), label };
	});
	return new Promise((resolve) => {
		frappe.prompt(
			[
				{
					fieldtype: "Select",
					fieldname: "batch_no",
					label: __("Batch"),
					options,
					reqd: 1,
				},
			],
			(values) => {
				const picked =
					rolls.find((r) => String(r.batch_no || "").trim() === values.batch_no) ||
					rolls.find((r) => String(r.name || "") === values.batch_no);
				resolve(picked || rolls[0]);
			},
			__("Select Batch"),
			__("Continue")
		);
	});
}

async function findExistingQcDraft(sprName, testingType, selectedRoll) {
	const batchNo = String(selectedRoll?.batch_no || "").trim();
	const rollNo = cint(selectedRoll?.roll_no) || rollSuffix(selectedRoll);
	const baseFilters = {
		shaft_production_run: sprName,
		testing_type: testingType,
		docstatus: 0,
	};
	if (batchNo) {
		const byBatch = await frappe.db.get_list(QC_DOCTYPE, {
			filters: { ...baseFilters, batch_no: batchNo },
			fields: ["name"],
			limit: 1,
			order_by: "modified desc",
		});
		if (byBatch?.[0]?.name) {
			return byBatch[0].name;
		}
	}
	if (rollNo) {
		const byRoll = await frappe.db.get_list(QC_DOCTYPE, {
			filters: { ...baseFilters, roll_no: rollNo },
			fields: ["name"],
			limit: 1,
			order_by: "modified desc",
		});
		if (byRoll?.[0]?.name) {
			return byRoll[0].name;
		}
	}
	return "";
}

function qcMetaHasField(fieldname) {
	try {
		const meta = frappe.get_meta(QC_DOCTYPE);
		const fields = (meta && meta.fields) || [];
		return !!fields.find((f) => f.fieldname === fieldname);
	} catch {
		return false;
	}
}

function firstSprField(spr, candidates) {
	for (const fn of candidates) {
		const v = spr?.[fn];
		if (v !== undefined && v !== null && String(v).trim() !== "") {
			return { fieldname: fn, value: v };
		}
	}
	return null;
}

function applyPattyTemplateDefaults(defaults, spr) {
	const isPatty =
		String(defaults.testing_type || "").toLowerCase().includes("patty");
	if (!isPatty) {
		return;
	}
	const w = firstSprField(spr, TEMPLATE_WIDTH_FIELDS);
	if (w) {
		for (const fn of TEMPLATE_WIDTH_FIELDS) {
			if (qcMetaHasField(fn)) {
				defaults[fn] = w.value;
				break;
			}
		}
	}
	const h = firstSprField(spr, TEMPLATE_HEIGHT_FIELDS);
	if (h) {
		for (const fn of TEMPLATE_HEIGHT_FIELDS) {
			if (qcMetaHasField(fn)) {
				defaults[fn] = h.value;
				break;
			}
		}
	}
}

async function openQualityCheckingDoc(sprName, testType, jobId, rollRow) {
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
	const selectedRoll = rollRow || (await promptRollForSprJob(spr, jobId));
	if (!selectedRoll) {
		frappe.msgprint(__("No rolls found for this job."));
		return;
	}

	const existingName = await findExistingQcDraft(sprName, testingType, selectedRoll);
	if (existingName) {
		frappe.set_route("Form", QC_DOCTYPE, existingName);
		return;
	}

	const defaults = {
		shaft_production_run: sprName,
		testing_type: testingType,
		unit: spr.custom_unit || spr.unit || "",
		shift: spr.shift || "",
		order_code: spr.custom_order_code || spr.order_code || "",
		quality: selectedRoll?.quality || jobRow?.quality || "",
		color: selectedRoll?.color || jobRow?.color || "",
		batch_no: selectedRoll?.batch_no || "",
		roll_no: cint(selectedRoll?.roll_no) || rollSuffix(selectedRoll) || 0,
	};
	applyPattyTemplateDefaults(defaults, spr);

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
	const spr = await loadSprDoc(sprName);
	const selectedRoll = await promptRollForSprJob(spr, resolvedJob);
	if (!selectedRoll) {
		frappe.msgprint(__("No rolls found for this job."));
		return;
	}
	await openQualityCheckingDoc(sprName, testType, resolvedJob, selectedRoll);
}

frappe.provide("production_entry.spr_quality_check");

production_entry.spr_quality_check.openSprGsmTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "round_gsm", jobId);
production_entry.spr_quality_check.openSprRoundCuttingGsmTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "round_gsm", jobId);
production_entry.spr_quality_check.openSprPattyCuttingGsmTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "patty_gsm", jobId);
production_entry.spr_quality_check.openSprTensileTesting = (sprName, jobId) =>
	openSprQualityCheck(sprName, "tensile", jobId);
