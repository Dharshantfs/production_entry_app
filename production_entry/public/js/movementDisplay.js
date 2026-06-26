/** Movement type cell label for order tables. */

function normalizeMovementLabel(mt) {
  let d = String(mt || "").trim();
  if (!d) return "";
  if (d === "Transport" || d.startsWith("Transport ")) {
    d = d.replace(/^Transport/, "Transfer");
  }
  return d;
}

function movementLabelFromItem(item) {
  if (!item) return "";
  const raw =
    item.movement_display ||
    item.movement_type ||
    item.custom_movement_type ||
    "";
  const base = normalizeMovementLabel(raw);
  if (base) return base;
  // movement_display may include destination detail — keep short label for merge summary.
  const mtOnly = normalizeMovementLabel(item.movement_type || item.custom_movement_type);
  return mtOnly;
}

/** Combine movement types for merged rows: one label if all same, else "Transfer, Despatch". */
export function formatMergedMovementFromItems(items) {
  const types = [];
  const seen = new Set();
  (items || []).forEach((it) => {
    const label = movementLabelFromItem(it);
    if (!label) return;
    const key = label.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    types.push(label);
  });
  if (!types.length) return "—";
  if (types.length === 1) return types[0];
  return types.join(", ");
}

export function formatMovementCell(row) {
  if (!row) return "—";
  if (Array.isArray(row.items) && row.items.length) {
    return formatMergedMovementFromItems(row.items);
  }
  const label = movementLabelFromItem(row);
  return label || "—";
}
