import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

class RollProductionEntry(Document):
    def validate(self):
        self.validate_mandatory_fields()

    def on_submit(self):
        self.create_manufacturing_entries()
        self.update_work_order_statuses()

    def on_cancel(self):
        self.cancel_manufacturing_entries()

    def validate_mandatory_fields(self):
        for i, row in enumerate(self.items, start=1):
            if not row.roll_no:
                frappe.throw(_('Row {0}: Roll No is mandatory').format(i))
            if not row.meter_per_roll:
                frappe.throw(_('Row {0}: Meter/Roll is mandatory').format(i))
            if not row.wo_id:
                frappe.throw(_('Row {0}: Work Order is mandatory').format(i))


    def parse_item_code(self, row):
        """Positions 9-11: GSM, 12-15: Width in mm"""
        item_code = row.item_code
        if item_code and len(item_code) >= 16:
            try:
                row.gsm = int(item_code[9:12])
                row.width_inches = round(int(item_code[12:16]) / 25.4, 2)
            except (ValueError, IndexError):
                pass

    def create_manufacturing_entries(self):
        """
        Group rows by WO and create one Stock Entry (Manufacture) per WO.
        Each roll = one FG item row in Stock Entry.
        """
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
            
            # Tracking links
            se.custom_shaft_production_run = self.shaft_production_run
            se.custom_roll_production_entry = self.name

            # 1. Pull default items (Raw Materials + 1 default FG row)
            se.get_items() 

            # 2. Remove the default FG row(s) to replace with our roll-specific ones
            filtered_items = [i for i in se.items if not i.is_finished_item]
            se.set('items', filtered_items)

            # 3. Add our roll-specific FG rows
            for row in rows:
                se.append('items', {
                    'item_code': row.item_code,
                    'qty': flt(row.net_weight),
                    'uom': 'Kg',
                    'batch_no': row.batch_no,
                    't_warehouse': wo_doc.fg_warehouse,
                    'is_finished_item': 1,
                    'description': f"Roll No: {row.roll_no}"
                })

            se.insert()
            se.submit()
            created_entries.append(se.name)

        if created_entries:
            self.db_set('manufacturing_entries', ', '.join(created_entries))

    def update_work_order_statuses(self):
        """Check if WO produced_qty >= planned qty → mark WO as Completed"""
        wo_ids = list(set(row.wo_id for row in self.items if row.wo_id))
        for wo_id in wo_ids:
            wo_doc = frappe.get_doc('Work Order', wo_id)
            # Fetch latest produced_qty from DB
            produced = frappe.db.get_value('Work Order', wo_id, 'produced_qty')
            if flt(produced) >= flt(wo_doc.qty):
                wo_doc.db_set('status', 'Completed')

    def cancel_manufacturing_entries(self):
        """Cancel all linked Stock Entries."""
        entries = frappe.get_all('Stock Entry', filters={
            'custom_roll_production_entry': self.name,
            'docstatus': 1
        })
        for entry in entries:
            se = frappe.get_doc('Stock Entry', entry.name)
            se.cancel()
