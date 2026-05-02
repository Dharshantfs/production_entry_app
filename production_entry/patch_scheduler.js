/**
 * One-off / legacy. Do not replace production-table or lamination-order-table with
 * titled page names: Frappe routes using "Production Table" break as /desk/Production%20Table.
 * Canonical: production_entry/public/js/ProductionScheduler.vue (goToPlan uses
 * production-table and lamination-order-table slugs).
 */
console.log("patch_scheduler.js: no-op; do not run old inversions. Use canonical public/js/ProductionScheduler.vue.");
