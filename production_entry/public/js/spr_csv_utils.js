/** Helpers for Planning Table `spr_name` stored as comma-separated Shaft Production Run ids. */

export function parseSprIds(raw) {
  if (raw == null || raw === "") return [];
  return String(raw)
    .split(/[,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function mergeSprCsv(existing, addId) {
  const add = String(addId || "").trim();
  const base = parseSprIds(existing);
  if (!add) return base.join(", ");
  const seen = new Set();
  const out = [];
  for (const x of base) {
    if (x && !seen.has(x)) {
      seen.add(x);
      out.push(x);
    }
  }
  if (!seen.has(add)) {
    out.push(add);
  }
  return out.join(", ");
}

/**
 * Which SPR form to open: first draft when spr_docstatus is 0 (any draft in list);
 * otherwise the last id (most recently appended run).
 */
export async function resolveSprNavigationTarget(rawCsv, aggregatedDocstatus) {
  const ids = parseSprIds(rawCsv);
  if (!ids.length) return "";
  if (Number(aggregatedDocstatus) !== 0) return ids[ids.length - 1];
  for (const id of ids) {
    try {
      const r = await frappe.call({
        method: "frappe.client.get",
        args: { doctype: "Shaft Production Run", name: id },
      });
      if (r?.message && Number(r.message.docstatus) === 0) return id;
    } catch (_) {
      /* try next */
    }
  }
  return ids[ids.length - 1];
}
