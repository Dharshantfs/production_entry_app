/**
 * One-off / legacy. Old versions of this file rewrote set_route to "Production Table", which
 * caused Page not found. Canonical routing uses:
 *   production-table, lamination-order-table
 * See: production_entry/public/js/ProductionScheduler.vue (goToPlan).
 */
console.log("patch_scheduler_all.js: no-op; do not run old inversions.");
