/** Movement type cell label for order tables. */
export function formatMovementCell(row) {
  if (!row) return "—";
  const d = row.movement_display || row.movement_type || "";
  if (!d) return "—";
  return d;
}
