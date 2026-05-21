/** Movement type cell label for order tables. */
export function formatMovementCell(row) {
  if (!row) return "—";
  let d = row.movement_display || row.movement_type || "";
  if (!d) return "—";
  if (d === "Transport" || String(d).startsWith("Transport ")) {
    d = String(d).replace(/^Transport/, "Transfer");
  }
  return d;
}
