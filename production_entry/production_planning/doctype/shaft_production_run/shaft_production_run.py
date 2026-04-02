import frappe
from frappe import _
from frappe.utils import flt


class ShaftProductionRun(frappe.model.document.Document):
    pass


@frappe.whitelist()
def get_job_rows_for_production_plan(production_plan):
    """
    Build rows for the Jobs child table from Work Orders linked to this Production Plan.
    One row per distinct production_plan_item (job) with total planned qty as weight.
    """
    if not production_plan:
        return []

    if not frappe.db.exists("Production Plan", production_plan):
        frappe.throw(_("Production Plan {0} not found").format(production_plan))

    rows = frappe.db.sql(
        """
        SELECT
            wo.production_plan_item AS job_no,
            SUM(wo.qty) AS total_weight
        FROM `tabWork Order` wo
        WHERE wo.production_plan = %(pp)s
          AND wo.docstatus < 2
          AND IFNULL(wo.production_plan_item, '') != ''
        GROUP BY wo.production_plan_item
        ORDER BY MIN(wo.creation)
        """,
        {"pp": production_plan},
        as_dict=True,
    )

    out = []
    for r in rows:
        out.append(
            {
                "job_no": r.job_no,
                "total_weight": flt(r.total_weight),
            }
        )
    return out


@frappe.whitelist()
def get_or_create_roll_entry(shaft_production_run):
    """
    Check if Roll Production Entry exists for this SPR.
    If yes → return its name to open.
    If no  → fetch all jobs + WOs and return pre-filled data.
    """

    # Check existing
    existing = frappe.db.get_value(
        'Roll Production Entry',
        {'shaft_production_run': shaft_production_run, 'docstatus': ['!=', 2]},
        'name'
    )
    if existing:
        return {'existing': existing}

    # Get Production Plan from SPR
    pp_name = get_pp_from_spr(shaft_production_run)
    if not pp_name:
        frappe.throw(_('Could not find Production Plan linked to {0}').format(shaft_production_run))

    spr_doc = frappe.get_doc('Shaft Production Run', shaft_production_run)

    items = []

    # Loop through all jobs in SPR
    for job in spr_doc.jobs:
        job_no = job.job_no

        # Get shaft combination for this job from Production Plan
        shaft_combination = get_shaft_combination(pp_name, job_no)

        # Get planned qty (total weight) for this job
        planned_qty = job.total_weight if hasattr(job, 'total_weight') else 0

        # Get all Work Orders for this job
        work_orders = get_work_orders_for_job(pp_name, job_no)

        for wo in work_orders:
            wo_doc = frappe.get_doc('Work Order', wo['name'])
            item_code = wo_doc.production_item
            item_name = frappe.db.get_value('Item', item_code, 'item_name')
            gsm, width_inch = parse_item_code(item_code)

            items.append({
                'job_no': job_no,
                'shaft_combination': shaft_combination,
                'planned_qty': planned_qty,
                'wo_id': wo['name'],
                'item_code': item_code,
                'item_name': item_name,
                'gsm': gsm,
                'width_inches': width_inch,
                'order_code': get_order_code(wo_doc),
                # These will be filled manually by user:
                'batch_no': '',
                'roll_no': '',
                'meter_per_roll': 0,
                'net_weight': 0,
                'gross_weight': 0,
            })

    return {
        'production_plan': pp_name,
        'items': items
    }


def get_pp_from_spr(spr_name):
    """Extract Production Plan name from SPR."""
    # First try direct field
    pp_field = frappe.db.get_value('Shaft Production Run', spr_name, 'production_plan')
    if pp_field:
        return pp_field
    # Fallback: strip 'SPR-' prefix
    if spr_name.startswith('SPR-'):
        return spr_name[4:]
    return None


def get_shaft_combination(pp_name, job_no):
    """Fetch shaft combination string (e.g. 46+46+26) from Production Plan child table."""
    result = frappe.db.get_value(
        'Production Plan Shaft Detail',   # ← change to your actual child table name
        {'parent': pp_name, 'job_no': job_no},
        'shaft_combination'
    )
    return result or ''


def get_work_orders_for_job(pp_name, job_no):
    """Get all Work Orders for a specific PP + job."""
    return frappe.db.sql("""
        SELECT
            wo.name,
            wo.production_item,
            wo.qty as planned_qty,
            wo.produced_qty,
            wo.status
        FROM `tabWork Order` wo
        WHERE wo.production_plan = %(pp_name)s
          AND wo.production_plan_item = %(job_no)s
          AND wo.docstatus != 2
        ORDER BY wo.name
    """, {'pp_name': pp_name, 'job_no': job_no}, as_dict=True)


def parse_item_code(item_code):
    """
    Parse GSM and width from item code.
    Format: PPPQQQCCCGGGWWWW (16 chars)
    Example: 1001091010801065
      100 = process code  (0:3)
      109 = quality code  (3:6)
      101 = color code    (6:9)
      080 = GSM           (9:12)
      1065 = width in mm  (12:16)
    """
    try:
        if len(item_code) >= 16:
            gsm = int(item_code[9:12])
            width_mm = int(item_code[12:16])
            width_inch = round(width_mm / 25.4, 1)
            return gsm, width_inch
    except Exception:
        pass
    return 0, 0


def get_order_code(wo_doc):
    """Get order code from Work Order."""
    return (
        getattr(wo_doc, 'order_code', '') or
        getattr(wo_doc, 'sales_order', '') or ''
    )
