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
    BOX_BAG_UNIT_L4_SCREEN,
    BOX_BAG_UNASSIGNED_UNIT,
    SLITTING_UNIT,
    LAMINATION_UNIT,
    PRINTED_BOPP_FILM_UNIT,
)

BOPP_BAG_UNITS = (BOX_BAG_UNIT_L1, BOX_BAG_UNIT_L2, BOX_BAG_UNIT_L4_SCREEN, BOX_BAG_UNASSIGNED_UNIT)
BOPP_BOX_BAG_PROCESS_CODES = ("222", "223", "231", "232", "233", "241", "242", "225", "226")
BOPP_BOX_BAG_SYNC_PARENT_PROCESSES = ("231", "232", "233", "241", "242")
BOPP_BOX_BAG_PARENT_PROCESSES = ("221",) + BOPP_BOX_BAG_PROCESS_CODES

_BOPP_FINISHING_MAP = {
    "PP": "PLAIN / PLAIN",
    "0P": "0/PLAIN",
    "OP": "0/PLAIN",
    "MM": "METALLIC / MATTE",
    "MG": "METALLIC / GLOSSY",
    "CM": "COOLER / MATTE",
    "CG": "COOLER / GLOSSY",
    "PM": "PLAIN / MATTE",
    "PG": "PLAIN / GLOSSY",
    "0M": "MATTE",
    "0G": "GLOSSY",
    "M":  "MATTE",
    "G":  "GLOSSY",
    "P":  "PLAIN",
    "0":  "PLAIN",
}

def _decode_fabric_gsm_char(ch):
    """Decode a single letter or digit to Fabric GSM integer."""
    if not ch:
        return 0
    ch = str(ch).strip().upper()
    if ch.isdigit():
        return int(ch) * 10
    try:
        from production_entry.production_planning.scheduler_api import LAMINATION_FABRIC_GSM_CODES
        rev = {v: k for k, v in LAMINATION_FABRIC_GSM_CODES.items()}
        if ch in rev:
            return int(rev[ch])
    except Exception:
        pass
    return (ord(ch) - ord('A') + 1) * 10

def _decode_lam_bopp_gsm_char(ch):
    """Decode a single letter or digit to Lam/BOPP GSM integer."""
    if not ch:
        return 0
    ch = str(ch).strip().upper()
    if ch.isdigit():
        return int(ch) * 10
    try:
        from production_entry.production_planning.scheduler_api import LAMINATION_BOPP_GSM_CODES
        rev = {v: k for k, v in LAMINATION_BOPP_GSM_CODES.items()}
        if ch in rev:
            return int(rev[ch])
    except Exception:
        pass
    return 15


def _bopp_finishing_label(code):
    return _BOPP_FINISHING_MAP.get(str(code or "").strip().upper(), str(code or "").strip())


def _bopp_process_label(process_code):
    p = str(process_code or "").strip()
    if p == "231":
        return "231 colored bopp box bag"
    if p == "232":
        return "232 colored bopp screen printed box bag"
    if p == "241":
        return "241 mettalic box bag"
    if p == "242":
        return "242 cooler box bag"
    if p == "225":
        return "225 pre-flexo laminated printed box bag"
    if p == "226":
        return "226 custom flexo laminated printed box bag"
    if p == "222":
        return "222 flexo printed box bag"
    if p == "223":
        return "223 flexo printed box bag"
    return "233 BOPP Box Bag"


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

    # Find which segment contains any BOPP box bag process code (222/231/233/241/242).
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

    process = ""
    idx = -1
    for proc in BOPP_BOX_BAG_PROCESS_CODES:
        at = tail.find(proc)
        if at >= 0 and (idx < 0 or at < idx):
            idx = at
            process = proc
    if idx < 0:
        return result
    result["process"] = process

    after = tail[idx + 3:]   # e.g. B001QCC0M
    if len(after) >= 1:
        result["quality_letter"] = after[0]
    if len(after) >= 4:
        result["colour_code"] = after[1:4]
    if len(after) >= 5:
        result["fabric_gsm"] = _decode_fabric_gsm_char(after[4])
    if len(after) >= 6:
        result["lam_gsm"] = _decode_lam_bopp_gsm_char(after[5])
    if len(after) >= 7:
        result["bopp_gsm"] = _decode_lam_bopp_gsm_char(after[6])
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
    """Ensure all 222/231/233/241/242 rows on Planning Table have a box bag unit assigned."""
    if not frappe.db.has_column("Planning Table", "unit"):
        return
    proc_like = " OR ".join(
        [f"item_code LIKE '{p}%%' OR item_code LIKE '%%-{p}%%'" for p in BOPP_BOX_BAG_PROCESS_CODES]
    )
    conditions = f"""
        ({proc_like})
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


def _sync_bopp_pb_rows_from_107_for_fg_parents(planning_sheet_name, fg_parent_processes):
    """
    For each 107 planning row linked to SO lines whose FG is in fg_parent_processes,
    extract PB-* BOM children into the Planning Table.
    """
    if not planning_sheet_name:
        return
    if not frappe.db.exists("Planning sheet", planning_sheet_name):
        return

    from production_entry.production_planning.scheduler_api import (
        _item_process_prefix,
        _is_printed_bopp_item_code,
        _get_pt_parentfield,
        _printed_bopp_planning_fields_from_item_code,
        MOVEMENT_TRANSFER,
        _set_movement_type_if_supported,
    )

    fg_set = tuple(str(p).strip() for p in (fg_parent_processes or ()) if str(p).strip())
    if not fg_set:
        return

    ps = frappe.get_doc("Planning sheet", planning_sheet_name)
    if not ps.get("sales_order"):
        return
    so_doc = frappe.get_doc("Sales Order", ps.sales_order)
    so_items_bopp = {
        str(it.name): it for it in (so_doc.items or [])
        if _item_process_prefix(str(it.item_code or "")) in fg_set
    }
    if not so_items_bopp:
        return

    parent_field = _get_pt_parentfield()

    # Fetch 107 rows on the sheet that are linked to BOPP box-bag SO lines (from document, not DB!)
    rows_107 = []
    for prow in (ps.get(parent_field) or []):
        ic = str(prow.get("item_code") or "").strip()
        if ic.startswith("107") or "-107" in ic:
            rows_107.append(prow)

    for prow in rows_107:
        soi_key = str(prow.get("sales_order_item") or prow.get("so_item") or "")
        # Only proceed if this 107 row belongs to a BOPP box-bag SO line
        if soi_key not in so_items_bopp:
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

        # Check if already exists in DB
        existing_db = frappe.db.sql(
            """SELECT name FROM `tabPlanning Table`
               WHERE parent = %s AND item_code = %s
                 AND (IFNULL(sales_order_item,'') = %s OR IFNULL(so_item,'') = %s)
               LIMIT 1""",
            (planning_sheet_name, pb_ic, soi_key, soi_key),
            as_dict=True,
        )
        # Check if already exists in memory
        existing_mem = any(
            str(r.get("item_code") or "").strip() == pb_ic and
            str(r.get("sales_order_item") or r.get("so_item") or "") == soi_key
            for r in (ps.get(parent_field) or [])
        )
        if existing_db or existing_mem:
            continue

        so_it = so_items_bopp[soi_key]
        so_fg_ic = str(so_it.item_code or "").strip()
        from production_entry.production_planning.scheduler_api import _parent_child_trace_id_from_item_code

        trace_id = _parent_child_trace_id_from_item_code(so_fg_ic)
        # PB Kg qty is set when user clicks **Meter to Kgs (All Bag BOM)** on the planning sheet.
        pb_qty = flt(prow.get("qty") or 0)

        # Insert PB row (Planning Table + Planning sheet Item)
        new_row = {
            "item_code": pb_ic,
            "item_name": pb_item_name,
            "qty": pb_qty,
            "uom": prow.get("uom") or "Kg",
            "unit": PRINTED_BOPP_FILM_UNIT,
            "sales_order_item": soi_key,
            "so_item": soi_key,
            "custom_parent_child_trace_id": trace_id,
            "quality": "PRINTED BOPP",
        }
        pb_patch = _printed_bopp_planning_fields_from_item_code(pb_ic, pb_item_name, soi_key) or {}
        new_row.update(pb_patch)
        _set_movement_type_if_supported(new_row, MOVEMENT_TRANSFER, "Planning Table")
        try:
            if hasattr(ps, "items") or ps.meta.has_field("items"):
                ps.append("items", dict(new_row))
            ps.append(parent_field, dict(new_row))
        except Exception:
            pass

    try:
        ps.flags.ignore_permissions = True
        ps.save()
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_sync_bopp_pb_rows_from_107_for_fg_parents")


def _sync_bopp_pb_rows_from_107(planning_sheet_name):
    """PB rows for BOPP box-bag FG parents (231/233/241/242)."""
    _sync_bopp_pb_rows_from_107_for_fg_parents(planning_sheet_name, BOPP_BOX_BAG_PARENT_PROCESSES)


def _sync_bopp_bag_planning_rows(planning_sheet_name):
    """
    BOPP Box Bag (222/231/233/241/242/225/226): loop 103/108/110 from FG BOM and
    child expansions are handled by _sync_box_bag_loop_bom_chain in scheduler_api.
    Here: stamp total GSM on parent rows and assign box bag units.
    """
    if not planning_sheet_name:
        return

    _update_bopp_bag_gsm_on_sheet(planning_sheet_name)

    try:
        _force_bopp_bag_unit_on_sheet(planning_sheet_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_sync_bopp_bag_planning_rows:_force_bopp_bag_unit_on_sheet")


def _update_bopp_bag_gsm_on_sheet(planning_sheet_name):
    """For each 222/231/233/241/242 row, parse item code and write fabric+lam+bopp total into gsm field."""
    if not planning_sheet_name:
        return
    so_name = str(frappe.db.get_value("Planning sheet", planning_sheet_name, "sales_order") or "").strip()
    rows = [
        r
        for r in (
            frappe.db.sql(
                """SELECT name, item_code, sales_order_item, so_item, unit FROM `tabPlanning Table`
                   WHERE parent = %s""",
                (planning_sheet_name,),
                as_dict=True,
            )
            or []
        )
        if _parse_bopp_bag_item_code(r.get("item_code") or "").get("process") in BOPP_BOX_BAG_PROCESS_CODES
    ]
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
        
        # Finishing
        if parsed.get("finishing_label") or parsed.get("finishing_code"):
            fin = parsed.get("finishing_label") or parsed.get("finishing_code")
            if frappe.db.has_column("Planning Table", "custom_finishing"):
                updates["custom_finishing"] = fin
            if frappe.db.has_column("Planning Table", "finishing"):
                updates["finishing"] = fin

        # Design Master info
        dc = parsed.get("design_code")
        if dc:
            try:
                from production_entry.production_planning.scheduler_api import _design_master_extra_fields, _pb_design_name_from_sales_order_item, _printing_design_attachment_from_sales_order_item
                dm_info = _design_master_extra_fields(dc)
                
                soi_name = str(row.get("sales_order_item") or row.get("so_item") or "").strip()
                if not soi_name and so_name:
                    so_doc = frappe.get_doc("Sales Order", so_name)
                    for it in so_doc.items or []:
                        if str(it.item_code or "").startswith(dc + "-"):
                            soi_name = it.name
                            break
                            
                design_name = dm_info.get("custom_design_name")
                design_attachment = dm_info.get("custom_design_attachment")
                
                if soi_name:
                    if not design_name:
                        design_name = _pb_design_name_from_sales_order_item(soi_name)
                    if not design_attachment:
                        design_attachment = _printing_design_attachment_from_sales_order_item(soi_name)

                if frappe.db.has_column("Planning Table", "custom_design_code"):
                    updates["custom_design_code"] = dc
                if design_name and frappe.db.has_column("Planning Table", "custom_design_name"):
                    updates["custom_design_name"] = design_name
                if design_attachment and frappe.db.has_column("Planning Table", "custom_design_attachment"):
                    updates["custom_design_attachment"] = design_attachment
                if frappe.db.has_column("Planning Table", "custom_design_colour") and dm_info.get("custom_design_colour"):
                    updates["custom_design_colour"] = dm_info.get("custom_design_colour")
            except Exception:
                pass

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
            if frappe.db.has_column("Planning Table", "bag_size"):
                updates["bag_size"] = parsed["bag_size_id"]
                
        # Force Unit
        if frappe.db.has_column("Planning Table", "unit"):
            cur_unit = row.get("unit") or ""
            from production_entry.production_planning.bopp_bag_api import BOPP_BAG_UNITS, BOX_BAG_UNASSIGNED_UNIT
            if cur_unit not in BOPP_BAG_UNITS:
                updates["unit"] = BOX_BAG_UNASSIGNED_UNIT

        frappe.db.set_value("Planning Table", row["name"], updates, update_modified=False)

    # Same update on Planning sheet Item table if it exists
    if not frappe.db.exists("DocType", "Planning sheet Item"):
        return

    psi_rows = [
        r
        for r in (
            frappe.db.sql(
                """SELECT name, item_code, sales_order_item, so_item, unit FROM `tabPlanning sheet Item`
                   WHERE parent = %s""",
                (planning_sheet_name,),
                as_dict=True,
            )
            or []
        )
        if _parse_bopp_bag_item_code(r.get("item_code") or "").get("process") in BOPP_BOX_BAG_PROCESS_CODES
    ]
    
    for row in (psi_rows or []):
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
        
        # Finishing
        if parsed.get("finishing_label") or parsed.get("finishing_code"):
            fin = parsed.get("finishing_label") or parsed.get("finishing_code")
            if frappe.db.has_column("Planning sheet Item", "custom_finishing"):
                updates["custom_finishing"] = fin
            if frappe.db.has_column("Planning sheet Item", "finishing"):
                updates["finishing"] = fin

        # Design Master info
        dc = parsed.get("design_code")
        if dc:
            try:
                from production_entry.production_planning.scheduler_api import _design_master_extra_fields, _pb_design_name_from_sales_order_item, _printing_design_attachment_from_sales_order_item
                dm_info = _design_master_extra_fields(dc)
                
                soi_name = str(row.get("sales_order_item") or row.get("so_item") or "").strip()
                if not soi_name and so_name:
                    so_doc = frappe.get_doc("Sales Order", so_name)
                    for it in so_doc.items or []:
                        if str(it.item_code or "").startswith(dc + "-"):
                            soi_name = it.name
                            break
                            
                design_name = dm_info.get("custom_design_name")
                design_attachment = dm_info.get("custom_design_attachment")
                
                if soi_name:
                    if not design_name:
                        design_name = _pb_design_name_from_sales_order_item(soi_name)
                    if not design_attachment:
                        design_attachment = _printing_design_attachment_from_sales_order_item(soi_name)

                if frappe.db.has_column("Planning sheet Item", "custom_design_code"):
                    updates["custom_design_code"] = dc
                if design_name and frappe.db.has_column("Planning sheet Item", "custom_design_name"):
                    updates["custom_design_name"] = design_name
                if design_attachment and frappe.db.has_column("Planning sheet Item", "custom_design_attachment"):
                    updates["custom_design_attachment"] = design_attachment
                if frappe.db.has_column("Planning sheet Item", "custom_design_colour") and dm_info.get("custom_design_colour"):
                    updates["custom_design_colour"] = dm_info.get("custom_design_colour")
            except Exception:
                pass
        
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
            if frappe.db.has_column("Planning sheet Item", "bag_size"):
                updates["bag_size"] = parsed["bag_size_id"]
                
        # Force Unit
        if frappe.db.has_column("Planning sheet Item", "unit"):
            cur_unit = row.get("unit") or ""
            from production_entry.production_planning.bopp_bag_api import BOPP_BAG_UNITS, BOX_BAG_UNASSIGNED_UNIT
            if cur_unit not in BOPP_BAG_UNITS:
                updates["unit"] = BOX_BAG_UNASSIGNED_UNIT

        frappe.db.set_value("Planning sheet Item", row["name"], updates, update_modified=False)


@frappe.whitelist()
def get_bopp_bag_order_table_data(
    date=None,
    start_date=None,
    end_date=None,
    planned_only=1,
):
    """BOPP Box Bag board rows (222/231/233/241/242) for the Box Bag Order Table."""
    from production_entry.production_planning.board_access import (
        board_slug_for_api,
        enforce_board_read,
        request_board_slug,
    )
    from production_entry.production_planning.scheduler_api import (
        _get_color_chart_data_impl,
        _item_process_prefix,
        _normalize_filter_date,
        _transfer_payload_for_chart_row,
        PLANNING_MOVEMENT_TYPE_FIELD,
    )
    from production_entry.production_planning.box_bag_api import _bag_series_size_map

    enforce_board_read(
        request_board_slug(board_slug_for_api("get_bopp_bag_order_table_data")),
        date=date,
        start_date=start_date,
        end_date=end_date,
    )

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

    # Hard-filter: only BOPP box-bag process rows.
    raw = [
        r for r in (raw or [])
        if _item_process_prefix(str(r.get("item_code") or r.get("itemCode") or "")) in BOPP_BOX_BAG_PROCESS_CODES
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
        spr_name = str(row.get("spr_name") or "").strip()
        from production_entry.production_planning.box_bag_api import (
            _spr_achieved_bag_pcs_total,
            _spr_total_achieved_meters_from_bundle,
        )
        achieved_bag_pcs = _spr_achieved_bag_pcs_total(spr_name)
        if achieved_bag_pcs > 0:
            achieved_qty = achieved_bag_pcs
        total_achieved_meters = _spr_total_achieved_meters_from_bundle(spr_name)

        pp_id = str(row.get("pp_id") or row.get("production_plan") or "").strip()
        pp_docstatus = row.get("pp_docstatus") or 0
        wo_name = ""
        wo_open = False
        wo_terminal = False
        spr_docstatus = row.get("spr_docstatus") or 0

        if not pp_id:
            # Fallback for Box Bag legacy orders: try to fetch by Sales Order + Item
            so_name = str(row.get("salesOrder") or "").strip()
            if so_name and ic:
                try:
                    pp_wos = frappe.db.sql("""
                        SELECT pp.name as pp_id, wo.name as wo_name, wo.status 
                        FROM `tabProduction Plan` pp
                        JOIN `tabWork Order` wo ON wo.production_plan = pp.name
                        WHERE pp.docstatus < 2 AND wo.sales_order = %s AND wo.production_item = %s
                    """, (so_name, ic), as_dict=True)
                    if pp_wos:
                        pp_id = pp_wos[0].pp_id
                        wo_name = pp_wos[0].wo_name
                        wo_status = str(pp_wos[0].status or "").strip()
                        wo_open = wo_status in ("Not Started", "In Process", "Open")
                        wo_terminal = wo_status in ("Completed", "Stopped", "Cancelled")
                except Exception:
                    pass

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
            "total_achieved_meters": total_achieved_meters,
            "per_day_production": flt(row.get("per_day_production") or 0),
            "pp_id": pp_id,
            "pp_docstatus": pp_docstatus,
            "wo_name": wo_name,
            "wo_open": wo_open,
            "wo_terminal": wo_terminal,
            "spr_name": spr_name,
            "spr_docstatus": spr_docstatus,
            "salesOrderItem": row.get("salesOrderItem") or row.get("sales_order_item") or "",
            "process": parsed.get("process") or "233",
            "process_label": _bopp_process_label(parsed.get("process") or "233"),
            "movement_type": row.get(PLANNING_MOVEMENT_TYPE_FIELD) or row.get("movement_type") or "",
        }

        try:
            transfer_data = _transfer_payload_for_chart_row(row, wo_terminal, spr_docstatus)
            enriched.update(transfer_data)
        except Exception:
            pass

        out.append(enriched)

    return out
