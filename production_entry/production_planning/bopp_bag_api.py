# -*- coding: utf-8 -*-
"""
BOPP Box Bag (process 233) — Board + Order Table API functions.

Item code format: 7465-2C-511-233B001QCC0M
  7465 = design code
  2C   = no of design colours (2 colours, encoded as digit+C)
  511  = bag size id (Bag Series)
  233  = process code (BOPP Box Bag)
  B    = quality letter
  001  = colour code (3 digits)
  Q    = fabric GSM letter-encoded
  C    = lam GSM letter-encoded
  C    = bopp GSM letter-encoded
  0    = extra (0=nothing, P=plain, M=metallic, C=cooler)
  M    = finishing (M=Matte, G=Glossy)

Total GSM = fabric_gsm + lam_gsm + bopp_gsm
"""
import re
import frappe
from frappe.utils import flt, cint

from production_entry.production_planning.planning_doctypes import (
    BOX_BAG_UNIT_L1,
    BOX_BAG_UNIT_L2,
    BOX_BAG_UNASSIGNED_UNIT,
    SLITTING_UNIT,
    LAMINATION_UNIT,
    PRINTED_BOPP_FILM_UNIT,
)

BOPP_BAG_UNITS = (BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L2, BOX_BAG_UNASSIGNED_UNIT)

_BOPP_FINISHING_MAP = {
    "PP": "Plain",
    "MM": "Metallic / Matte",
    "MG": "Metallic / Glossy",
    "CM": "Cooler / Matte",
    "CG": "Cooler / Glossy",
    "PM": "Plain / Matte",
    "PG": "Plain / Glossy",
    "0M": "Matte",
    "0G": "Glossy",
    "M":  "Matte",
    "G":  "Glossy",
}

# Letter-encoded GSM values (same table used by 221/107/104 etc.)
_GSM_LETTER_MAP = {
    "A": 10, "B": 20, "C": 15, "D": 40, "E": 50, "F": 60,
    "G": 70, "H": 80, "I": 90, "J": 100, "K": 110, "L": 120,
    "M": 130, "N": 140, "O": 150, "P": 160, "Q": 100, "R": 180,
    "S": 190, "T": 200,
}


def _decode_gsm_char(ch):
    """Decode a single letter or digit to GSM integer."""
    if not ch:
        return 0
    ch = str(ch).strip().upper()
    if ch.isdigit():
        return int(ch) * 10
    return _GSM_LETTER_MAP.get(ch, 0)


def _bopp_finishing_label(code):
    return _BOPP_FINISHING_MAP.get(str(code or "").strip().upper(), str(code or "").strip())


def _parse_bopp_bag_item_code(item_code):
    """
    Parse BOPP Box Bag item code: DESIGN-NCOLOURS-BAGSIZE-233QCCCFLLBBXF
    Example: 7465-2C-511-233B001QCC0M

    Returns dict with all parsed fields + total_gsm.
    """
    result = {
        "design_code": "",
        "num_colors": "",          # digit portion of the 2C segment
        "bag_size_id": "",
        "process": "233",
        "quality_letter": "",
        "colour_code": "",
        "fabric_gsm": 0,
        "lam_gsm": 0,
        "bopp_gsm": 0,
        "total_gsm": 0,
        "extra_code": "",
        "finishing_code": "",
        "finishing_label": "",
    }
    ic = str(item_code or "").strip()
    if not ic:
        return result

    parts = ic.split("-")

    # Find which segment contains "233"
    tail = ""
    if len(parts) >= 2:
        result["design_code"] = parts[0].strip()

        # Check if second segment is the nColours token (e.g. "2C")
        seg1 = parts[1].strip()
        m = re.match(r'^(\d+)[Cc]$', seg1)
        if m and len(parts) >= 4:
            result["num_colors"] = m.group(1)
            result["bag_size_id"] = parts[2].strip()
            tail = "-".join(parts[3:]).strip()
        elif len(parts) >= 3:
            # no num_colors token — segments: design-size-233xxx
            result["bag_size_id"] = seg1
            tail = "-".join(parts[2:]).strip()
        else:
            tail = "-".join(parts[1:]).strip()
    else:
        tail = ic

    # Find "233" in the tail
    idx = tail.find("233")
    if idx < 0:
        return result

    after = tail[idx + 3:]   # e.g. B001QCC0M
    if len(after) >= 1:
        result["quality_letter"] = after[0]
    if len(after) >= 4:
        result["colour_code"] = after[1:4]
    if len(after) >= 5:
        result["fabric_gsm"] = _decode_gsm_char(after[4])
    if len(after) >= 6:
        result["lam_gsm"] = _decode_gsm_char(after[5])
    if len(after) >= 7:
        result["bopp_gsm"] = _decode_gsm_char(after[6])
    if len(after) >= 9:
        result["extra_code"] = after[7]
        result["finishing_code"] = after[7:9].upper()
        result["finishing_label"] = _bopp_finishing_label(after[7:9])
    elif len(after) >= 8:
        result["extra_code"] = after[7]
        result["finishing_code"] = after[7].upper()
        result["finishing_label"] = _bopp_finishing_label(after[7])

    result["total_gsm"] = result["fabric_gsm"] + result["lam_gsm"] + result["bopp_gsm"]
    return result


def _force_bopp_bag_unit_on_sheet(planning_sheet_name=None):
    """Ensure all 233-process rows on Planning Table have a box bag unit assigned."""
    if not frappe.db.has_column("Planning Table", "unit"):
        return
    conditions = """
        (item_code LIKE '233%%' OR item_code LIKE '%%-233%%')
        AND IFNULL(unit, '') NOT IN (%s, %s, %s)
    """
    params = list(BOPP_BAG_UNITS)
    if planning_sheet_name:
        conditions += " AND parent = %s"
        params.append(planning_sheet_name)

    frappe.db.sql(
        f"""UPDATE `tabPlanning Table`
        SET unit = %s
        WHERE {conditions}
        """,
        [BOX_BAG_UNASSIGNED_UNIT] + params,
    )


def _sync_bopp_pb_rows_from_107(planning_sheet_name):
    """
    For each 107 planning row on this sheet that belongs to a 233 SO line,
    look at the 107 item's BOM and extract any PB-* child into the Planning Table.
    """
    if not planning_sheet_name:
        return
    if not frappe.db.exists("Planning sheet", planning_sheet_name):
        return

    from production_entry.production_planning.scheduler_api import (
        _item_process_prefix,
        _is_printed_bopp_item_code,
        _get_pt_parentfield,
    )

    ps = frappe.get_doc("Planning sheet", planning_sheet_name)
    if not ps.get("sales_order"):
        return
    so_doc = frappe.get_doc("Sales Order", ps.sales_order)
    so_items_233 = {
        str(it.name): it for it in (so_doc.items or [])
        if _item_process_prefix(str(it.item_code or "")) == "233"
    }
    if not so_items_233:
        return

    parent_field = _get_pt_parentfield()

    # Fetch 107 rows on the sheet that are linked to 233 SO lines
    rows_107 = frappe.db.sql(
        """SELECT name, item_code, sales_order_item, so_item, qty, uom
           FROM `tabPlanning Table`
           WHERE parent = %s
             AND (item_code LIKE '107%%' OR item_code LIKE '%%-107%%')
        """,
        (planning_sheet_name,),
        as_dict=True,
    ) or []

    for prow in rows_107:
        soi_key = str(prow.get("sales_order_item") or prow.get("so_item") or "")
        # Only proceed if this 107 row belongs to a 233 SO line
        if soi_key not in so_items_233:
            continue

        item_107 = str(prow.get("item_code") or "").strip()

        # Find PB child in BOM of the 107 item
        bom_name = frappe.db.get_value(
            "BOM",
            {"item": item_107, "is_active": 1, "is_default": 1, "docstatus": 1},
            "name",
        )
        if not bom_name:
            bom_name = frappe.db.get_value(
                "BOM",
                {"item": item_107, "is_active": 1, "docstatus": 1},
                "name",
                order_by="modified desc",
            )
        if not bom_name:
            continue

        bom = frappe.get_doc("BOM", bom_name)
        pb_items = [
            r for r in (bom.items or [])
            if _is_printed_bopp_item_code(str(r.item_code or ""))
        ]
        if not pb_items:
            continue

        pb_row = pb_items[0]
        pb_ic = str(pb_row.item_code or "").strip()
        pb_item_name = frappe.db.get_value("Item", pb_ic, "item_name") or pb_ic

        # Check if already exists
        existing = frappe.db.sql(
            """SELECT name FROM `tabPlanning Table`
               WHERE parent = %s AND item_code = %s
                 AND (IFNULL(sales_order_item,'') = %s OR IFNULL(so_item,'') = %s)
               LIMIT 1""",
            (planning_sheet_name, pb_ic, soi_key, soi_key),
            as_dict=True,
        )
        if existing:
            continue

        so_it = so_items_233[soi_key]
        so_fg_ic = str(so_it.item_code or "").strip()
        from production_entry.production_planning.scheduler_api import _parent_child_trace_id_from_item_code
        trace_id = _parent_child_trace_id_from_item_code(so_fg_ic)

        # Insert PB row
        new_row = {
            "item_code": pb_ic,
            "item_name": pb_item_name,
            "qty": flt(prow.get("qty") or 0),
            "uom": prow.get("uom") or "Kg",
            "unit": PRINTED_BOPP_FILM_UNIT,
            "sales_order_item": soi_key,
            "so_item": soi_key,
            "custom_parent_child_trace_id": trace_id,
        }
        try:
            ps.append(parent_field, dict(new_row))
        except Exception:
            pass

    try:
        ps.flags.ignore_permissions = True
        ps.save()
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_sync_bopp_pb_rows_from_107")


def _sync_bopp_bag_planning_rows(planning_sheet_name):
    """
    BOPP Box Bag (233) BOM child sync:
      233 → 103 (Slitting)
      103 → 100 (Fabric for Slitting)
      233 → 107 (BOPP Laminated Fabric)
      107 → 100 (Fabric for Lam)
      107 → PB  (Printed BOPP Film)

    Also writes total_gsm into the gsm field of the 233 parent row.
    """
    if not planning_sheet_name:
        return

    from production_entry.production_planning.scheduler_api import (
        _sync_bom_child_rows_from_planning_rows,
        _item_process_prefix,
    )

    _sync_bom_child_rows_from_planning_rows(
        planning_sheet_name,
        ("233",),
        "103",
        SLITTING_UNIT,
        process_label="BOPP bag slitting (233 → 103)",
    )
    _sync_bom_child_rows_from_planning_rows(
        planning_sheet_name,
        ("103",),
        "100",
        so_parent_processes=("233",),
        process_label="BOPP bag fabric via slitting (103 → 100)",
    )
    _sync_bom_child_rows_from_planning_rows(
        planning_sheet_name,
        ("233",),
        "107",
        LAMINATION_UNIT,
        process_label="BOPP bag laminated fabric (233 → 107)",
    )
    _sync_bom_child_rows_from_planning_rows(
        planning_sheet_name,
        ("107",),
        "100",
        so_parent_processes=("233",),
        process_label="BOPP bag fabric via lam (107 → 100)",
    )
    # PB (Printed BOPP Film) extraction: 233→107 BOM contains PB-* children.
    # We do this inline because _sync_bom_child_rows_from_planning_rows doesn't match PB- prefixes.
    _sync_bopp_pb_rows_from_107(planning_sheet_name)

    # Write total_gsm into the gsm field of 233 parent rows
    _update_bopp_bag_gsm_on_sheet(planning_sheet_name)

    try:
        _force_bopp_bag_unit_on_sheet(planning_sheet_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_sync_bopp_bag_planning_rows:_force_bopp_bag_unit_on_sheet")


def _update_bopp_bag_gsm_on_sheet(planning_sheet_name):
    """For each 233-process row, parse item code and write fabric+lam+bopp total into gsm field."""
    if not planning_sheet_name:
        return
    rows = frappe.db.sql(
        """SELECT name, item_code FROM `tabPlanning Table`
           WHERE parent = %s
             AND (item_code LIKE '233%%' OR item_code LIKE '%%-233%%')""",
        (planning_sheet_name,),
        as_dict=True,
    ) or []
    for row in rows:
        parsed = _parse_bopp_bag_item_code(row.get("item_code") or "")
        total = parsed.get("total_gsm") or 0
        if total <= 0:
            continue
        updates = {"gsm": total}

        # Resolve quality and color names
        quality_name = ""
        color_name = ""
        try:
            from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
                _quality_name_by_code,
                _color_name_by_code,
            )
            if parsed["quality_letter"]:
                quality_name = _quality_name_by_code(parsed["quality_letter"]) or parsed["quality_letter"]
            if parsed["colour_code"]:
                color_name = _color_name_by_code(parsed["colour_code"]) or parsed["colour_code"]
        except Exception:
            quality_name = parsed["quality_letter"]
            color_name = parsed["colour_code"]

        if frappe.db.has_column("Planning Table", "custom_lam_gsm"):
            updates["custom_lam_gsm"] = parsed.get("lam_gsm") or 0
        if frappe.db.has_column("Planning Table", "custom_bopp_gsm"):
            updates["custom_bopp_gsm"] = parsed.get("bopp_gsm") or 0
        if frappe.db.has_column("Planning Table", "custom_no_of_design_colours"):
            nc = parsed.get("num_colors") or ""
            if nc:
                updates["custom_no_of_design_colours"] = nc + "C"
        
        # Validation fixes: Quality, Color, and Bag Size
        if quality_name:
            if frappe.db.has_column("Planning Table", "quality"):
                updates["quality"] = quality_name
            if frappe.db.has_column("Planning Table", "custom_quality"):
                updates["custom_quality"] = quality_name
        if color_name:
            if frappe.db.has_column("Planning Table", "color"):
                updates["color"] = color_name
        if parsed.get("bag_size_id"):
            if frappe.db.has_column("Planning Table", "sheet_size"):
                updates["sheet_size"] = parsed["bag_size_id"]
            if frappe.db.has_column("Planning Table", "bag_size"):
                updates["bag_size"] = parsed["bag_size_id"]

        frappe.db.set_value("Planning Table", row["name"], updates, update_modified=False)

    # Same update on Planning sheet Item table if it exists
    if frappe.db.exists("DocType", "Planning sheet Item"):
        ps_rows = frappe.db.sql(
            """SELECT name, item_code FROM `tabPlanning sheet Item`
               WHERE parent = %s
                 AND (item_code LIKE '233%%' OR item_code LIKE '%%-233%%')""",
            (planning_sheet_name,),
            as_dict=True,
        ) or []
        for row in ps_rows:
            parsed = _parse_bopp_bag_item_code(row.get("item_code") or "")
            total = parsed.get("total_gsm") or 0
            if total <= 0:
                continue
            updates = {"gsm": total}

            # Resolve quality and color names
            quality_name = ""
            color_name = ""
            try:
                from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
                    _quality_name_by_code,
                    _color_name_by_code,
                )
                if parsed["quality_letter"]:
                    quality_name = _quality_name_by_code(parsed["quality_letter"]) or parsed["quality_letter"]
                if parsed["colour_code"]:
                    color_name = _color_name_by_code(parsed["colour_code"]) or parsed["colour_code"]
            except Exception:
                quality_name = parsed["quality_letter"]
                color_name = parsed["colour_code"]

            if frappe.db.has_column("Planning sheet Item", "custom_lam_gsm"):
                updates["custom_lam_gsm"] = parsed.get("lam_gsm") or 0
            if frappe.db.has_column("Planning sheet Item", "custom_bopp_gsm"):
                updates["custom_bopp_gsm"] = parsed.get("bopp_gsm") or 0
            if frappe.db.has_column("Planning sheet Item", "custom_no_of_design_colours"):
                nc = parsed.get("num_colors") or ""
                if nc:
                    updates["custom_no_of_design_colours"] = nc + "C"
            
            # Validation fixes: Quality, Color, and Bag Size
            if quality_name:
                if frappe.db.has_column("Planning sheet Item", "quality"):
                    updates["quality"] = quality_name
                if frappe.db.has_column("Planning sheet Item", "custom_quality"):
                    updates["custom_quality"] = quality_name
            if color_name:
                if frappe.db.has_column("Planning sheet Item", "color"):
                    updates["color"] = color_name
            if parsed.get("bag_size_id"):
                if frappe.db.has_column("Planning sheet Item", "sheet_size"):
                    updates["sheet_size"] = parsed["bag_size_id"]
                if frappe.db.has_column("Planning sheet Item", "bag_size"):
                    updates["bag_size"] = parsed["bag_size_id"]

            frappe.db.set_value("Planning sheet Item", row["name"], updates, update_modified=False)


@frappe.whitelist()
def get_bopp_bag_order_table_data(
    date=None,
    start_date=None,
    end_date=None,
    planned_only=1,
):
    """BOPP Box Bag board rows (process 233) for the Box Bag Order Table."""
    from production_entry.production_planning.scheduler_api import (
        _get_color_chart_data_impl,
        _item_process_prefix,
        _normalize_filter_date,
        _transfer_payload_for_chart_row,
        PLANNING_MOVEMENT_TYPE_FIELD,
    )
    from production_entry.production_planning.box_bag_api import _bag_series_size_map

    try:
        _force_bopp_bag_unit_on_sheet()
    except Exception:
        pass

    raw = _get_color_chart_data_impl(
        date=date,
        start_date=start_date,
        end_date=end_date,
        plan_name="__all__",
        mode=None,
        planned_only=cint(planned_only),
        board_process_scope="box_bag_only",
    )

    # Hard-filter: only process 233
    raw = [
        r for r in (raw or [])
        if _item_process_prefix(str(r.get("item_code") or r.get("itemCode") or "")) == "233"
    ]

    bag_sizes = _bag_series_size_map()

    out = []
    for row in raw:
        ic = str(row.get("item_code") or row.get("itemCode") or "").strip()
        parsed = _parse_bopp_bag_item_code(ic)
        item_name = str(row.get("item_name") or "").strip()
        planning_sheet = str(row.get("planningSheet") or row.get("planning_sheet") or row.get("parent") or "").strip()

        # Resolve quality and color names
        quality_name = ""
        color_name = ""
        try:
            from production_entry.production_planning.doctype.planning_sheet.planning_sheet import (
                _quality_name_by_code,
                _color_name_by_code,
            )
            if parsed["quality_letter"]:
                quality_name = _quality_name_by_code(parsed["quality_letter"]) or parsed["quality_letter"]
            if parsed["colour_code"]:
                color_name = _color_name_by_code(parsed["colour_code"]) or parsed["colour_code"]
        except Exception:
            quality_name = parsed["quality_letter"]
            color_name = parsed["colour_code"]

        bag_size_id = parsed["bag_size_id"]
        bag_size_inches = bag_sizes.get(bag_size_id, "")

        design_code = parsed["design_code"]
        design_name = ""
        design_attachment = ""
        so_name = ""
        if planning_sheet:
            try:
                so_name = str(frappe.db.get_value("Planning sheet", planning_sheet, "sales_order") or "").strip()
            except Exception:
                pass

        # Fetch design attachment from Planning Table row
        pt_item_name = str(row.get("itemName") or row.get("item_name") or row.get("name") or "").strip()
        if pt_item_name:
            try:
                if frappe.db.has_column("Planning Table", "custom_design_attachment"):
                    design_attachment = str(frappe.db.get_value("Planning Table", pt_item_name, "custom_design_attachment") or "").strip()
            except Exception:
                pass

        if design_code and so_name and not design_name:
            try:
                so_doc = frappe.get_doc("Sales Order", so_name)
                for it in so_doc.items or []:
                    sic = str(it.item_code or "").strip()
                    if sic.startswith(design_code + "-"):
                        design_name = str(it.item_name or "").strip()
                        break
            except Exception:
                pass
        if not design_name:
            design_name = item_name

        unit = str(row.get("unit") or "").strip()
        if unit not in BOPP_BAG_UNITS:
            unit = BOX_BAG_UNASSIGNED_UNIT

        planned_qty = flt(row.get("qty") or row.get("quantity") or 0)
        achieved_qty = flt(row.get("actual_production_weight_kgs") or row.get("produced_qty") or 0)
        length = flt(row.get("length") or row.get("meter") or 0)

        pp_id = str(row.get("pp_id") or row.get("production_plan") or "").strip()
        pp_docstatus = row.get("pp_docstatus") or 0
        wo_name = ""
        wo_open = False
        wo_terminal = False
        spr_name = str(row.get("spr_name") or "").strip()
        spr_docstatus = row.get("spr_docstatus") or 0

        if pp_id:
            try:
                wos = frappe.get_all(
                    "Work Order",
                    filters={"production_plan": pp_id, "docstatus": ["<", 2]},
                    fields=["name", "status"],
                    order_by="creation desc",
                    limit_page_length=5,
                ) or []
                for w in wos:
                    wo_name = w.name
                    wo_status = str(w.get("status") or "").strip()
                    wo_open = wo_status in ("Not Started", "In Process", "Open")
                    wo_terminal = wo_status in ("Completed", "Stopped", "Cancelled")
                    break
            except Exception:
                pass

        enriched = {
            "itemName": pt_item_name,
            "item_code": ic,
            "item_name": item_name,
            "planningSheet": planning_sheet,
            "plannedDate": row.get("plannedDate") or row.get("planned_date") or "",
            "partyCode": row.get("partyCode") or row.get("party_code") or row.get("order_code") or "",
            "customer": row.get("customer") or row.get("customer_name") or "",
            "customer_name": row.get("customer_name") or row.get("customer") or "",
            "unit": unit,
            "design_code": design_code,
            "design_name": design_name,
            "design_attachment": design_attachment,
            "num_colors": parsed["num_colors"],
            "bag_size_id": bag_size_id,
            "bag_size_inches": bag_size_inches,
            "quality": quality_name or row.get("quality") or "",
            "color": color_name or row.get("color") or "",
            "colour_code": parsed["colour_code"],
            "fabric_gsm": parsed["fabric_gsm"],
            "lam_gsm": parsed["lam_gsm"],
            "bopp_gsm": parsed["bopp_gsm"],
            "total_gsm": parsed["total_gsm"],
            "gsm": parsed["total_gsm"],
            "extra_code": parsed["extra_code"],
            "finishing_code": parsed["finishing_code"],
            "finishing": parsed["finishing_label"] or parsed["finishing_code"],
            "length": length,
            "planned_quantity": planned_qty,
            "achieved_quantity": achieved_qty,
            "per_day_production": flt(row.get("per_day_production") or 0),
            "pp_id": pp_id,
            "pp_docstatus": pp_docstatus,
            "wo_name": wo_name,
            "wo_open": wo_open,
            "wo_terminal": wo_terminal,
            "spr_name": spr_name,
            "spr_docstatus": spr_docstatus,
            "salesOrderItem": row.get("salesOrderItem") or row.get("sales_order_item") or "",
            "process": "233",
            "process_label": "233 BOPP Box Bag",
            "movement_type": row.get(PLANNING_MOVEMENT_TYPE_FIELD) or row.get("movement_type") or "",
        }

        try:
            transfer_data = _transfer_payload_for_chart_row(row, wo_terminal, spr_docstatus)
            enriched.update(transfer_data)
        except Exception:
            pass

        out.append(enriched)

    return out
