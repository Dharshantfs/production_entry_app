/**
 * Group transfer/despatch eligible rows by SPR (+ order + customer).
 * Merged production-table items sharing one SPR become a single dialog row.
 */

export function sprGroupKey(row) {
	const spr = String(row?.spr_name || "").trim();
	if (!spr) return "";
	const party = String(row?.party_code || "").trim();
	const customer = String(row?.customer_name || "").trim();
	return `${spr}::${party}::${customer}`;
}

export function rowSelectionId(row) {
	if (row?._isSprGroup) return row._groupKey;
	return row?.planning_table_row || "";
}

export function groupRowsBySpr(rawRows) {
	const rows = Array.isArray(rawRows) ? rawRows : [];
	const groups = new Map();
	const singles = [];

	rows.forEach((row) => {
		const gk = sprGroupKey(row);
		if (!gk) {
			singles.push(row);
			return;
		}
		if (!groups.has(gk)) groups.set(gk, []);
		groups.get(gk).push(row);
	});

	const out = [];
	groups.forEach((members, gk) => {
		if (members.length === 1) {
			out.push(members[0]);
			return;
		}
		const lead = members[0];
		const itemCodes = [...new Set(members.map((m) => String(m.item_code || "").trim()).filter(Boolean))];
		const canTransfer = members.every((m) => m.can_transfer);
		const canDespatch = members.every((m) => m.can_despatch);
		const blockReason =
			members.find((m) => m.transfer_block_reason)?.transfer_block_reason ||
			members.find((m) => m.despatch_block_reason)?.despatch_block_reason ||
			"";
		out.push({
			...lead,
			_isSprGroup: true,
			_groupKey: `sprgrp:${gk}`,
			_members: members,
			planning_table_row: `sprgrp:${gk}`,
			item_code: itemCodes.length > 3 ? `${itemCodes.length} items` : itemCodes.join(", "),
			item_codes: itemCodes,
			item_count: itemCodes.length,
			can_transfer: canTransfer,
			can_despatch: canDespatch,
			transfer_block_reason: canTransfer ? "" : blockReason,
			despatch_block_reason: canDespatch ? "" : blockReason,
		});
	});
	singles.forEach((r) => out.push(r));
	return out;
}

/** Map batch item_code back to the planning row member for submit lines. */
export function resolveMemberForBatch(groupRow, batch) {
	const ic = String(batch?.item_code || "").trim();
	if (groupRow?._isSprGroup && Array.isArray(groupRow._members)) {
		if (ic) {
			const hit = groupRow._members.find((m) => String(m.item_code || "").trim() === ic);
			if (hit) return hit;
		}
		return groupRow._members[0];
	}
	return groupRow;
}

export function buildLogisticsSubmitLines(selection, mode) {
	const lines = [];
	const canField = mode === "despatch" ? "can_despatch" : "can_transfer";
	Object.values(selection || {}).forEach((s) => {
		const groupRow = s.row;
		(s.batches || []).forEach((b) => {
			const member = resolveMemberForBatch(groupRow, b);
			if (member && member[canField] === false) return;
			lines.push({
				planning_table_row: member.planning_table_row,
				planning_sheet: member.planning_sheet,
				party_code: member.party_code,
				customer_name: member.customer_name,
				item_code: b.item_code || member.item_code,
				unit: member.unit,
				spr_name: member.spr_name || groupRow.spr_name,
				batch_no: b.batch_no,
				net_weight: b.net_weight || b.qty,
				qty: Math.max(parseFloat(b.qty) || 0, 1),
				uom: "Kg",
			});
		});
	});
	return lines;
}
