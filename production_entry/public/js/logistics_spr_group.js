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
		const blockedTransfer = members.find((m) => !m.can_transfer);
		const blockedDespatch = members.find((m) => !m.can_despatch);
		const despatchStatus =
			members.map((m) => String(m.despatch_status || "").trim()).find(Boolean) || "";
		const clubbingSheet =
			members.map((m) => String(m.clubbing_sheet || "").trim()).find(Boolean) || lead.clubbing_sheet || "";
		const loadingSequence =
			members.map((m) => String(m.loading_sequence || "").trim()).find(Boolean) || lead.loading_sequence || "";
		const clubLoadOrder =
			members.map((m) => Number(m.club_load_order) || 0).find((n) => n > 0) || lead.club_load_order || 0;
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
			despatch_status: despatchStatus,
			clubbing_sheet: clubbingSheet,
			loading_sequence: loadingSequence,
			club_load_order: clubLoadOrder,
			transfer_block_reason: blockedTransfer?.transfer_block_reason || "",
			despatch_block_reason:
				blockedDespatch?.despatch_block_reason || blockedDespatch?.despatch_status || despatchStatus || "",
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
				clubbing_sheet: member.clubbing_sheet || groupRow.clubbing_sheet || "",
				loading_sequence: member.loading_sequence || groupRow.loading_sequence || "",
				club_load_order: member.club_load_order || groupRow.club_load_order || 0,
				despatch_customer: member.despatch_customer || groupRow.despatch_customer || "",
				despatch_sales_order: member.despatch_sales_order || groupRow.despatch_sales_order || "",
			});
		});
	});
	return lines;
}
