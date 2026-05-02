import frappe
from frappe import _
from frappe.utils import flt


class RollProductionEntry(frappe.model.document.Document):

    def validate(self):
        self.calculate_weights()
        self.validate_mandatory_fields()

    def on_submit(self):
        self.create_manufacturing_entries()
        self.update_work_order_statuses()

    def on_cancel(self):
        self.cancel_manufacturing_entries()

    # ─────────────────────────────────────────
    # VALIDATE
    # ─────────────────────────────────────────

    def validate_mandatory_fields(self):
        for i, row in enumerate(self.items, start=1):
            if not row.roll_no:
                frappe.throw(_('Row {0}: Roll No is mandatory').format(i))
            if not row.meter_per_roll:
                frappe.throw(_('Row {0}: Meter/Roll is mandatory').format(i))
            if not row.wo_id:
                frappe.throw(_('Row {0}: WO ID is mandatory').format(i))

    def calculate_weights(self):
        """Auto-calculate net weight from GSM, width, meter/roll."""
        for row in self.items:
            if row.gsm and row.width_inches and row.meter_per_roll:
                width_m = flt(row.width_inches) * 0.0254
                row.net_weight = round(
                    flt(row.gsm) * width_m * flt(row.meter_per_roll) / 1000, 3
                )

    # ─────────────────────────────────────────
    # SUBMIT
    # ─────────────────────────────────────────

    def create_manufacturing_entries(self):
        """
        Group items by WO ID.
        Create one Stock Entry (Manufacture) per WO.
        """
        # Group rows by WO
        wo_groups = {}
        for row in self.items:
            if not row.wo_id:
                continue
            if row.wo_id not in wo_groups:
                wo_groups[row.wo_id] = []
            wo_groups[row.wo_id].append(row)

        created_entries = []

        for wo_id, rows in wo_groups.items():
            wo_doc = frappe.get_doc('Work Order', wo_id)
            total_qty = sum(flt(r.net_weight) for r in rows)

            if total_qty <= 0:
                frappe.msgprint(_('Skipping WO {0} — net weight is 0').format(wo_id), alert=True)
                continue

            se = frappe.new_doc('Stock Entry')
            se.stock_entry_type = 'Manufacture'
            se.work_order = wo_id
            se.production_item = wo_doc.production_item
            se.fg_completed_qty = total_qty
            se.from_bom = 1
            se.bom_no = wo_doc.bom_no
            se.use_multi_level_bom = wo_doc.use_multi_level_bom
            se.wip_warehouse = wo_doc.wip_warehouse
            se.to_warehouse = wo_doc.fg_warehouse

            # Link back to Roll Production Entry and SPR
            se.roll_production_entry = self.name
            se.shaft_production_run = self.shaft_production_run

            # Add one FG row per roll
            for row in rows:
                se.append('items', {
                    'item_code': row.item_code,
                    'item_name': row.item_name,
                    'qty': flt(row.net_weight),
                    'uom': 'Kg',
                    'batch_no': row.batch_no,
                    'serial_no': row.roll_no,
                    't_warehouse': wo_doc.fg_warehouse,
                    'is_finished_item': 1,
                })

            # Pull raw material consumption from BOM
            se.get_items()

            se.insert()
            se.submit()
            created_entries.append(se.name)

            frappe.msgprint(
                _('✅ Manufacturing Entry {0} created for WO {1}').format(se.name, wo_id),
                alert=True
            )

        if created_entries:
            self.db_set('manufacturing_entries', ', '.join(created_entries))
            frappe.msgprint(
                _('Created {0} Manufacturing Entries: {1}').format(
                    len(created_entries), ', '.join(created_entries)
                )
            )

    def update_work_order_statuses(self):
        """Mark WO as Completed if produced qty >= planned qty."""
        wo_ids = list(set(row.wo_id for row in self.items if row.wo_id))

        for wo_id in wo_ids:
            wo_doc = frappe.get_doc('Work Order', wo_id)
            total_produced = frappe.db.sql("""
                SELECT IFNULL(SUM(fg_completed_qty), 0)
                FROM `tabStock Entry`
                WHERE work_order = %s
                  AND stock_entry_type = 'Manufacture'
                  AND docstatus = 1
            """, wo_id)[0][0]

            if flt(total_produced) >= flt(wo_doc.qty):
                wo_doc.db_set('status', 'Completed')
                frappe.msgprint(
                    _('✅ Work Order {0} marked as Completed').format(wo_id),
                    alert=True
                )

    # ─────────────────────────────────────────
    # CANCEL
    # ─────────────────────────────────────────

    def cancel_manufacturing_entries(self):
        """Cancel all linked manufacturing entries."""
        wo_ids = list(set(row.wo_id for row in self.items if row.wo_id))

        for wo_id in wo_ids:
            entries = frappe.get_all(
                'Stock Entry',
                filters={
                    'work_order': wo_id,
                    'roll_production_entry': self.name,
                    'docstatus': 1
                },
                fields=['name']
            )
            for entry in entries:
                se = frappe.get_doc('Stock Entry', entry.name)
                se.cancel()
                frappe.msgprint(
                    _('Cancelled Manufacturing Entry {0}').format(entry.name),
                    alert=True
                )
