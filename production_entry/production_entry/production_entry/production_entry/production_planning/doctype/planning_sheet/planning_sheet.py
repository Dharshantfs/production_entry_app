# -*- coding: utf-8 -*-
# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime, getdate, add_days
import re

from production_entry.production_planning.planning_doctypes import (
    PLANNING_SHEET as PLANNING_SHEET_DOCTYPE,
    PLANNING_SHEET_SUBMIT_LINKS_WORK_ORDERS_ONLY,
    normalize_planning_unit_for_select,
)


def get_item_default_warehouse(item_code, company):
    """Resolve default warehouse for an item without querying a removed `tabItem.default_warehouse` column.

    ERPNext stores per-company defaults on **Item Default**; older setups may still have `Item.default_warehouse`.
    """
    if not item_code or not company:
        return None
    wh = frappe.db.get_value(
        "Item Default",
        {"parent": item_code, "company": company},
        "default_warehouse",
    )
    if wh:
        return wh
    try:
        meta = frappe.get_meta("Item")
        if meta.has_field("default_warehouse"):
            return frappe.db.get_value("Item", item_code, "default_warehouse")
    except Exception:
        pass
    return frappe.db.get_value("Company", company, "default_warehouse")


def get_default_bom_for_item(item_code, company=None):
    """Resolve an active submitted BOM for Production Plan `po_items` (BOM No is mandatory in ERPNext).

    Prefers default BOM for the company, then any active BOM for the item.
    """
    if not item_code:
        return None
    try:
        from erpnext.manufacturing.doctype.bom.bom import get_default_bom

        try:
            name = get_default_bom(item_code, company)
        except TypeError:
            name = get_default_bom(item_code)
        if name:
            return name
    except Exception:
        pass
    base_filters = {"item": item_code, "docstatus": 1, "is_active": 1}
    if company:
        rows = frappe.get_all(
            "BOM",
            filters={**base_filters, "company": company},
            fields=["name"],
            order_by="is_default desc, modified desc",
            limit_page_length=1,
        )
        if rows:
            return rows[0].name
    rows = frappe.get_all(
        "BOM",
        filters=base_filters,
        fields=["name"],
        order_by="is_default desc, modified desc",
        limit_page_length=1,
    )
    return rows[0].name if rows else None


# Class name must equal DocType name with spaces removed (Frappe get_controller), e.g. "Planning sheet" -> Planningsheet.
class Planningsheet(Document):
    def _validate_links(self):
        """Run before Document's link check: Frappe calls _validate_links() before validate()/hooks."""
        if not self.flags.get("ignore_links") and self._action != "cancel":
            self._fix_planned_items_source_item_links()
            # Whites → UNASSIGNED; colors → Unit 1–4 by width before Select normalization.
            self._recompute_line_units_from_width_and_color()
            # Runs before super(): insert() also validates links before before_validate.
            self._normalize_child_table_units()
        super()._validate_links()

    def _recompute_line_units_from_width_and_color(self):
        """Only white orders stay UNASSIGNED; other colors get machine unit from width (and resolved color)."""
        if cint(self.docstatus) != 0:
            return
        from production_entry.production_planning.scheduler_api import (
            compute_default_production_unit,
            _get_color_by_code,
            _item_process_prefix,
            resolve_color_name_for_planning_row,
        )

        linked_psi_names = set()
        for pr in self.get("planned_items") or []:
            si = (getattr(pr, "source_item", None) or "").strip()
            if si:
                linked_psi_names.add(si)

        for table_key in ("items", "planned_items"):
            for row in self.get(table_key) or []:
                if getattr(row, "planned_date", None) and str(row.planned_date).strip():
                    continue
                # Board row drives unit for linked legacy line — do not overwrite Planning sheet Item from width.
                if table_key == "items":
                    psi_name = (getattr(row, "name", None) or "").strip()
                    if psi_name and psi_name in linked_psi_names:
                        continue
                color = (getattr(row, "color", None) or "").strip()
                resolved = resolve_color_name_for_planning_row(
                    getattr(row, "item_code", None),
                    getattr(row, "item_name", None),
                    color,
                )
                if resolved and not color:
                    row.color = resolved
                    color = resolved
                elif not color:
                    color = resolved or ""
                width = flt(getattr(row, "width_inch", None))
                # Hard rule: process 103 always belongs to Slitting Unit and color from Colour Master code.
                item_code = str(getattr(row, "item_code", None) or "").strip()
                process_prefix = _item_process_prefix(item_code)
                if process_prefix == "103":
                    digits = "".join(ch for ch in item_code if ch.isdigit())
                    code = digits[6:9] if len(digits) >= 9 else ""
                    mapped = _get_color_by_code(code) if code else ""
                    if mapped:
                        row.color = mapped
                        color = mapped
                    row.unit = "Slitting Unit"
                    continue
                row.unit = compute_default_production_unit(color, width, getattr(row, "item_code", None))

    def _sync_linked_planning_units(self):
        """Keep legacy `items` and board `planned_items` units aligned when linked by `source_item`.

        Desk often POSTs a stale value for the grid the user did not edit. Compare to DB so we detect
        which side changed: only board changed → copy to legacy; only legacy changed → copy to board;
        both changed → prefer legacy (same as user editing the snapshot grid first).
        """
        if cint(self.docstatus) != 0:
            return
        items_by_name = {((getattr(r, "name", None) or "").strip()): r for r in (self.get("items") or []) if getattr(r, "name", None)}
        for pr in self.get("planned_items") or []:
            si = (getattr(pr, "source_item", None) or "").strip()
            if not si or si not in items_by_name:
                continue
            leg = items_by_name[si]
            # Hard lock for process 103 across linked rows.
            item_code = str(getattr(pr, "item_code", None) or getattr(leg, "item_code", None) or "").strip()
            from production_entry.production_planning.scheduler_api import _get_color_by_code, _item_process_prefix
            if _item_process_prefix(item_code) == "103":
                digits = "".join(ch for ch in item_code if ch.isdigit())
                code = digits[6:9] if len(digits) >= 9 else ""
                mapped = _get_color_by_code(code) if code else ""
                if mapped:
                    pr.color = mapped
                    leg.color = mapped
                pr.unit = "Slitting Unit"
                leg.unit = "Slitting Unit"
                continue
            nu = normalize_planning_unit_for_select(getattr(leg, "unit", None))
            bu = normalize_planning_unit_for_select(getattr(pr, "unit", None))
            if nu == bu:
                continue

            pr_name = (getattr(pr, "name", None) or "").strip()
            leg_db_n = None
            pr_db_n = None
            if frappe.db.exists("Planning sheet Item", si):
                leg_db_n = normalize_planning_unit_for_select(
                    frappe.db.get_value("Planning sheet Item", si, "unit")
                )
            if pr_name and frappe.db.exists("Planning Table", pr_name):
                pr_db_n = normalize_planning_unit_for_select(
                    frappe.db.get_value("Planning Table", pr_name, "unit")
                )

            leg_changed = leg_db_n is None or nu != leg_db_n
            board_changed = pr_db_n is None or bu != pr_db_n

            if leg_changed and not board_changed:
                pr.unit = nu
            elif board_changed and not leg_changed:
                leg.unit = bu
            elif leg_changed and board_changed:
                pr.unit = nu
                leg.unit = nu
            else:
                pr.unit = nu
                leg.unit = nu

    def _normalize_child_table_units(self):
        for row in self.get("planned_items") or []:
            row.unit = normalize_planning_unit_for_select(getattr(row, "unit", None))
        for row in self.get("items") or []:
            row.unit = normalize_planning_unit_for_select(getattr(row, "unit", None))

    def validate(self):
        """Validate planning sheet before saving"""
        self._sync_linked_planning_units()
        self.validate_items()
        self.calculate_totals()
        self.parse_item_details()
        self._sync_line_plan_codes()

    def _sync_line_plan_codes(self):
        """Fill Planning sheet Item / board row Plan Code from active plan + date + unit (color chart alignment)."""
        from production_entry.production_planning.scheduler_api import update_sheet_plan_codes

        update_sheet_plan_codes(self, include_legacy=True)

    def _fix_planned_items_source_item_links(self):
        """Ensure planned_items.source_item points to Planning sheet Item, not a Planning Table row id.

        Board rows and legacy rows share similar autonames; desk / splits sometimes store the wrong id in
        the Link field, which causes LinkValidationError on save.
        """

        def _resolve_to_planning_sheet_item(stored):
            """Follow Planning Table.source_item chain until a valid Planning sheet Item name or give up."""
            cur = (stored or "").strip()
            for _ in range(6):
                if not cur:
                    return None
                if frappe.db.exists("Planning sheet Item", cur):
                    return cur
                if frappe.db.exists("Planning Table", cur):
                    cur = frappe.db.get_value("Planning Table", cur, "source_item") or ""
                    continue
                return None
            return None

        planned = list(self.planned_items or [])
        if not planned:
            return

        legacy = sorted(
            list(self.get("items") or []),
            key=lambda x: (cint(x.idx), getattr(x, "name", None) or ""),
        )
        planned_sorted = sorted(
            planned,
            key=lambda x: (cint(x.idx), getattr(x, "name", None) or ""),
        )
        can_pos_map = len(legacy) == len(planned_sorted) and bool(legacy)

        for pos, row in enumerate(planned_sorted):
            si = (row.source_item or "").strip()
            if not si:
                continue
            if frappe.db.exists("Planning sheet Item", si):
                continue

            resolved = _resolve_to_planning_sheet_item(si)

            row_id = (row.name or "").strip()
            if not resolved and row_id:
                resolved = _resolve_to_planning_sheet_item(row_id)

            if resolved:
                row.source_item = resolved
                continue

            if can_pos_map and pos < len(legacy):
                ln = legacy[pos].name
                if ln and frappe.db.exists("Planning sheet Item", ln):
                    row.source_item = ln
                    continue

            row.source_item = None
    
    def before_save(self):
        """Allocate unit before saving"""
        if not self.allocated_unit:
            self.allocate_unit_to_sheet()
    
    def on_submit(self):
        """Update queue and create Production Plans on submit (WOs are created on PP submit)."""
        self.update_queue_position()
        self.create_production_docs()
        self.planning_status = "Finalized"

    def _resolve_company_for_production_docs(self):
        """Planning sheet JSON may not include `company`; never use bare self.company (AttributeError)."""
        co = self.get("company")
        if co:
            return co
        if self.sales_order:
            co = frappe.db.get_value("Sales Order", self.sales_order, "company")
            if co:
                return co
        co = frappe.defaults.get_user_default("Company")
        if co:
            return co
        return frappe.db.get_single_value("Global Defaults", "default_company")

    def _production_plan_header_fields_from_planning_sheet(self):
        """Optional Production Plan header fields so list views are not blank (custom fields vary per site)."""
        out = {}
        pp = "Production Plan"
        cust = self.get("customer")
        if not cust and self.sales_order:
            cust = frappe.db.get_value("Sales Order", self.sales_order, "customer")
        if cust and frappe.db.has_column(pp, "customer"):
            out["customer"] = cust
        if frappe.db.has_column(pp, "custom_planning_sheet"):
            out["custom_planning_sheet"] = self.name
        plan_label = (self.get("custom_plan_name") or self.get("plan_name") or "").strip()
        if plan_label and frappe.db.has_column(pp, "custom_plan_name"):
            out["custom_plan_name"] = plan_label
        code = (self.get("custom_plan_code") or "").strip()
        if code and frappe.db.has_column(pp, "custom_plan_code"):
            out["custom_plan_code"] = code
        return out

    def _try_link_work_order_from_existing_production_plan(self, item, pp_name):
        """
        If this Planning sheet row already belongs to an existing Production Plan, set work_order
        from WO(production_plan, production_plan_item) — no second PP insert.
        Returns True if work_order was set or PP matched.
        """
        if not pp_name or not frappe.db.exists("Production Plan", pp_name):
            return False
        pp = frappe.get_doc("Production Plan", pp_name)
        so_item = item.get("so_item") or item.get("sales_order_item")
        ppi_name = None
        for ppi in pp.get("po_items") or []:
            if (ppi.get("item_code") or "") != (item.item_code or ""):
                continue
            if (ppi.get("sales_order_item") or "") != (so_item or ""):
                continue
            ppi_name = ppi.name
            break
        if not ppi_name:
            return False
        wo_name = frappe.db.get_value(
            "Work Order",
            {
                "production_plan": pp.name,
                "production_plan_item": ppi_name,
                "docstatus": ["<", 2],
            },
            "name",
        )
        if not wo_name:
            rows = frappe.db.sql(
                """
                SELECT name FROM `tabWork Order`
                WHERE production_plan = %s AND docstatus < 2
                ORDER BY creation DESC
                LIMIT 1
                """,
                pp.name,
            )
            wo_name = rows[0][0] if rows else None
        if wo_name:
            item.work_order = wo_name
            return True
        return False

    def link_work_orders_for_production_plan(self, pp_name):
        """After a Production Plan is submitted, attach Work Orders to Planning sheet Item rows that use that PP."""
        from production_entry.production_planning.scheduler_api import (
            _get_item_level_production_plan,
            _production_plan_usable,
            _resolve_existing_production_plan_for_planning_sheet,
        )

        pp_name = (pp_name or "").strip()
        if not pp_name or not frappe.db.exists("Production Plan", pp_name):
            return False
        if cint(frappe.db.get_value("Production Plan", pp_name, "docstatus")) != 1:
            return False
        sheet_level_pp = _resolve_existing_production_plan_for_planning_sheet(self.name)
        updated = False
        for item in self.items:
            item_pp = _get_item_level_production_plan(item.name)
            pp_for_row = _production_plan_usable(item_pp) or sheet_level_pp
            if pp_for_row != pp_name:
                continue
            if self._try_link_work_order_from_existing_production_plan(item, pp_for_row):
                frappe.db.set_value(
                    "Planning sheet Item",
                    item.name,
                    "work_order",
                    item.work_order,
                    update_modified=False,
                )
                updated = True
        return updated

    def create_production_docs(self):
        """Link Work Orders from existing Production Plan(s). Optionally create PP per line only in legacy mode."""
        from production_entry.production_planning.scheduler_api import (
            _get_item_level_production_plan,
            _production_plan_usable,
            _resolve_existing_production_plan_for_planning_sheet,
        )

        company = self._resolve_company_for_production_docs()
        if not company:
            frappe.throw(
                _("Set Company on Planning sheet or link a Sales Order with Company before submitting."),
                title=_("Company missing"),
            )

        sheet_level_pp = _resolve_existing_production_plan_for_planning_sheet(self.name)
        links_only = PLANNING_SHEET_SUBMIT_LINKS_WORK_ORDERS_ONLY

        for item in self.items:
            item_pp = _get_item_level_production_plan(item.name)
            pp_for_row = _production_plan_usable(item_pp) or sheet_level_pp

            if pp_for_row:
                if self._try_link_work_order_from_existing_production_plan(item, pp_for_row):
                    continue
                ds = frappe.db.get_value("Production Plan", pp_for_row, "docstatus")
                if cint(ds) == 0:
                    # Draft PP: Work Orders do not exist yet. Skip this line; user can submit each PP in any order.
                    # WO links are filled when each PP is submitted (see on_production_plan_submitted) or on re-save.
                    continue
                if cint(ds) == 1:
                    frappe.throw(
                        _(
                            "Production Plan {0} is submitted but no Work Order matched this line "
                            "(item {1}). Check item code and Sales Order line on the Production Plan."
                        ).format(pp_for_row, item.item_code or ""),
                        title=_("Work Order not found for line"),
                    )
                frappe.throw(
                    _("Production Plan {0} is not in a valid state to link Work Orders.").format(pp_for_row),
                    title=_("Production Plan state"),
                )

            if links_only:
                frappe.throw(
                    _(
                        "No Production Plan linked to this Planning sheet or row. "
                        "Link Production Plan(s) on the sheet and lines, submit the Production Plan "
                        "(Work Orders are created from the Production Plan), then finalize this Planning sheet."
                    ),
                    title=_("Production Plan required"),
                )

            bom_no = get_default_bom_for_item(item.item_code, company)
            if not bom_no:
                frappe.throw(
                    _(
                        "No active default BOM found for item {0}. Set a default BOM on the BOM master before finalizing the Planning sheet."
                    ).format(item.item_code),
                    title=_("BOM No required"),
                )
            # Legacy: create one Production Plan per Planning sheet item (avoid when PLANNING_SHEET_SUBMIT_LINKS_WORK_ORDERS_ONLY is True)
            pp_dict = {
                "doctype": "Production Plan",
                "naming_series": "PP-",
                "company": company,
                "get_items_from": "Sales Order",
                "posting_date": getdate(),
                "custom_unit": self.allocated_unit,
                "po_items": [
                    {
                        "sales_order": self.sales_order,
                        "sales_order_item": item.so_item,
                        "item_code": item.item_code,
                        "bom_no": bom_no,
                        "planned_qty": item.qty,
                        "warehouse": item.warehouse or get_item_default_warehouse(item.item_code, company)
                    }
                ],
            }
            pp_dict.update(self._production_plan_header_fields_from_planning_sheet())
            pp = frappe.get_doc(pp_dict)
            pp.insert()
            pp.submit()

            ppi_name = (pp.po_items[0].name if pp.get("po_items") else None)
            wo_name = None
            if ppi_name:
                wo_name = frappe.db.get_value(
                    "Work Order",
                    {
                        "production_plan": pp.name,
                        "production_plan_item": ppi_name,
                        "docstatus": ["<", 2],
                    },
                    "name",
                )
            if not wo_name:
                rows = frappe.db.sql(
                    """
                    SELECT name FROM `tabWork Order`
                    WHERE production_plan = %s AND docstatus < 2
                    ORDER BY creation DESC
                    LIMIT 1
                    """,
                    pp.name,
                )
                wo_name = rows[0][0] if rows else None
            if wo_name:
                item.work_order = wo_name

        self.db_update()

    def validate_items(self):
        """Validate that items are present"""
        if not self.planned_items:
            frappe.throw("Please add at least one item to the Planning Sheet")
    
    @frappe.whitelist()
    def make_consolidated_production_entry(self):
        """Generate a single step Production Entry for all Work Orders in this Planning Sheet"""
        self.check_permission("write")
        
        entry_results = []
        for item in self.items:
            if not item.work_order:
                continue
            
            wo = frappe.get_doc("Work Order", item.work_order)
            if wo.status in ["Completed", "Closed"]:
                continue
            
            try:
                # Calculate what's left to produce
                pending_qty = flt(wo.qty) - flt(wo.produced_qty)
                if pending_qty <= 0:
                    continue
                
                # Logic to determine production qty (for now full pending)
                # In a real scenario, this would be passed from a dialog
                prod_qty = pending_qty
                
                # Create Stock Entry for Manufacture
                from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
                se = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", prod_qty))
                se.insert()
                se.submit()
                
                entry_results.append(f"Created Entry {se.name} for {item.item_code}")
                
            except Exception as e:
                frappe.log_error(f"Production Entry Error for {item.work_order}: {str(e)}")
                entry_results.append(f"Error for {item.item_code}: {str(e)}")
        
        return entry_results

    
    def calculate_totals(self):
        """Calculate total quantity and weight"""
        total_qty = 0
        total_weight = 0
        
        for item in self.planned_items:
            # Calculate weight per item if not already set
            if not item.total_weight and item.weight_per_roll and item.no_of_rolls:
                item.total_weight = flt(item.weight_per_roll) * flt(item.no_of_rolls)
            
            total_qty += flt(item.qty)
            total_weight += flt(item.total_weight)
        
        self.total_quantity = total_qty
        self.total_weight = total_weight
        
        # Calculate estimated production days
        if self.allocated_unit and self.total_weight:
            capacity = get_unit_daily_capacity(self.allocated_unit)
            if capacity:
                self.estimated_production_days = flt(self.total_weight / capacity, 2)
    
    def parse_item_details(self):
        """Parse item name to extract quality and color"""
        for item in self.planned_items:
            if item.item_name and not item.quality:
                quality, color = extract_quality_and_color(item.item_name)
                item.quality = quality
                item.color = color
    
    def allocate_unit_to_sheet(self):
        """Allocate unit based on quality, GSM and capacity"""
        # Quality rules
        UNIT_1 = ["SUPER PLATINUM", "PLATINUM", "PREMIUM", "GOLD", "SUPER CLASSIC"]
        UNIT_2 = ["GOLD", "SILVER", "BRONZE", "CLASSIC", "ECO SPECIAL", "ECO SPL"]
        UNIT_3 = ["SUPER PLATINUM", "PLATINUM", "PREMIUM", "GOLD", "SILVER", "BRONZE"]
        
        # Collect all items data
        items_data = []
        for item in self.planned_items:
            items_data.append({
                "quality": item.quality.upper() if item.quality else "",
                "gsm": flt(item.gsm),
                "weight": flt(item.total_weight)
            })
        
        if not items_data:
            return
        
        # Get dominant quality (most common)
        quality_counts = {}
        total_weight = 0
        avg_gsm = 0
        
        for item_data in items_data:
            qual = item_data["quality"]
            if qual:
                quality_counts[qual] = quality_counts.get(qual, 0) + item_data["weight"]
            total_weight += item_data["weight"]
            avg_gsm += item_data["gsm"] * item_data["weight"]
        
        avg_gsm = avg_gsm / total_weight if total_weight > 0 else 0
        dominant_quality = max(quality_counts, key=quality_counts.get) if quality_counts else ""
        
        # Allocate unit based on rules
        allocated_unit = None
        
        if avg_gsm > 50 and dominant_quality in UNIT_1:
            allocated_unit = "Unit 1"
        elif avg_gsm > 20 and dominant_quality in UNIT_2:
            allocated_unit = "Unit 2"
        elif avg_gsm > 10 and dominant_quality in UNIT_3:
            allocated_unit = "Unit 3"
        elif avg_gsm > 10:
            allocated_unit = "Unit 4"
        
        # Check capacity and assign to best available unit
        if allocated_unit:
            capacity_info = frappe.db.get_value("Unit Capacity", 
                                               allocated_unit,
                                               ["day_shift_capacity_kg", "night_shift_capacity_kg", "current_queue_weight"],
                                               as_dict=True)
            
            if capacity_info:
                self.allocated_unit = allocated_unit
                self.unit_capacity_day = capacity_info.day_shift_capacity_kg
                self.unit_capacity_night = capacity_info.night_shift_capacity_kg
                
                # Update item allocation
                for item in self.planned_items:
                    item.allocated_to_unit = allocated_unit
        
        return allocated_unit
    
    def update_queue_position(self):
        """Update queue position based on delivery date and priority"""
        if not self.allocated_unit:
            return
        
        # Get all finalized planning sheets for this unit
        existing_sheets = frappe.get_all(
            PLANNING_SHEET_DOCTYPE,
            filters={
                "allocated_unit": self.allocated_unit,
                "planning_status": ["in", ["Finalized", "In Production"]],
                "docstatus": 1,
                "name": ["!=", self.name],
            },
            fields=["name", "queue_position", "dod"],
            order_by="queue_position asc",
        )
        
        # Calculate new queue position
        if existing_sheets:
            max_position = max([sheet.queue_position or 0 for sheet in existing_sheets])
            self.queue_position = max_position + 1
        else:
            self.queue_position = 1
        
        # Update unit capacity
        update_unit_capacity_usage(self.allocated_unit)


# Utility Functions

def _quality_name_by_code(q_code: str) -> str:
    """Resolve quality name by code from Quality Master."""
    if not q_code:
        return ""
    q_code = str(q_code).strip()
    for fn in ("custom_quality_code", "quality_code", "short_code", "code"):
        try:
            v = frappe.db.get_value("Quality Master", {fn: q_code}, "name")
            if v:
                return str(v).strip().upper()
        except Exception:
            continue
    return ""


def _color_name_by_code(c_code: str) -> str:
    """Resolve color name by code from Colour Master."""
    if not c_code:
        return ""
    c_code = str(c_code).strip()

    def _norm_tokens(v: str):
        s = str(v or "").strip()
        if not s:
            return set()
        d = "".join(ch for ch in s if ch.isdigit())
        out = {s}
        if d:
            out.add(d)
            out.add(d.lstrip("0") or "0")
            out.add((d.lstrip("0") or "0").zfill(3))
            if len(d) >= 3:
                out.add(d[-3:])
        return {x.strip() for x in out if str(x or "").strip()}

    wanted = _norm_tokens(c_code)
    for fn in ("colour_code", "custom_colour_code", "custom_color_code", "color_code", "short_code", "code"):
        try:
            row = frappe.db.get_value(
                "Colour Master",
                {fn: c_code},
                ["name", "colour_name", "custom_colour_name", "color_name", "colour", "color"],
                as_dict=True,
            )
            if row:
                return str(
                    row.get("colour_name")
                    or row.get("custom_colour_name")
                    or row.get("color_name")
                    or row.get("colour")
                    or row.get("color")
                    or row.get("name")
                    or ""
                ).strip().upper()
        except Exception:
            continue
    # Fallback: compare normalized tokens to support messy code formats.
    try:
        cols = set(frappe.db.get_table_columns("Colour Master") or [])
        code_cols = [c for c in ("colour_code", "custom_colour_code", "custom_color_code", "color_code", "short_code", "code") if c in cols]
        name_cols = [c for c in ("colour_name", "custom_colour_name", "color_name", "colour", "color") if c in cols]
        if code_cols:
            rows = frappe.get_all("Colour Master", fields=list(dict.fromkeys(["name"] + code_cols + name_cols)), limit_page_length=0) or []
            for rr in rows:
                row_tokens = set()
                for c in code_cols:
                    row_tokens |= _norm_tokens(rr.get(c))
                if not row_tokens.intersection(wanted):
                    continue
                for ncol in ("colour_name", "custom_colour_name", "color_name", "colour", "color", "name"):
                    v = str(rr.get(ncol) or "").strip()
                    if v:
                        return v.upper()
    except Exception:
        pass
    return ""


def extract_quality_and_color(item_name, item_code=None):
    """Extract quality and color (prefer item-code index + masters, fallback item-name parse)."""
    QUAL_LIST = ["SUPER PLATINUM", "SUPER CLASSIC", "SUPER ECO", "ECO SPECIAL", 
                 "ECO GREEN", "ECO SPL", "LIFE STYLE", "LIFESTYLE", "PREMIUM", 
                 "PLATINUM", "CLASSIC", "DELUXE", "BRONZE", "SILVER", "ULTRA", 
                 "GOLD", "UV"]
    QUAL_LIST.sort(key=len, reverse=True)
    
    COL_LIST = ["GOLDEN YELLOW", "BRIGHT WHITE", "SUPER WHITE", "BLACK", "RED", 
                "BLUE", "GREEN", "MILKY WHITE", "SUNSHINE WHITE", "BLEACH WHITE", 
                "LEMON YELLOW", "BRIGHT ORANGE", "DARK ORANGE", "BABY PINK", 
                "DARK PINK", "CRIMSON RED", "LIGHT MAROON", "DARK MAROON", 
                "MEDICAL BLUE", "PEACOCK BLUE", "RELIANCE GREEN", "PARROT GREEN", 
                "ROYAL BLUE", "NAVY BLUE", "LIGHT GREY", "DARK GREY", 
                "CHOCOLATE BROWN", "LIGHT BEIGE", "DARK BEIGE", "PURPLE", "WHITE MIX", 
                "BLACK MIX", "COLOR MIX", "BEIGE MIX", "WHITE"]
    COL_LIST.sort(key=len, reverse=True)
    
    quality = ""
    color = ""
    item_upper = (item_name or "").upper()

    # 1) Prefer item_code index decoding for all process codes:
    #    quality code -> [3:6], color code -> [6:9]
    ic = str(item_code or "").strip()
    digits = "".join(ch for ch in ic if ch.isdigit())
    if len(digits) >= 9:
        q_code = digits[3:6]
        c_code = digits[6:9]
        quality = _quality_name_by_code(q_code) or quality
        color = _color_name_by_code(c_code) or color
    
    # Extract quality
    for qual in QUAL_LIST:
        if qual in item_upper:
            quality = qual
            break
    
    # Extract color
    for col in COL_LIST:
        if col in item_upper:
            color = col
            break
    
    return (quality or "").strip().upper(), (color or "").strip().upper()


def get_unit_daily_capacity(unit_name):
    """Get total daily capacity for a unit"""
    capacity = frappe.db.get_value("Unit Capacity", 
                                   unit_name, 
                                   ["day_shift_capacity_kg", "night_shift_capacity_kg"],
                                   as_dict=True)
    
    if capacity:
        return flt(capacity.day_shift_capacity_kg) + flt(capacity.night_shift_capacity_kg)
    return 0


def update_unit_capacity_usage(unit_name):
    """Update current queue weight and available capacity"""
    # Get all finalized sheets for this unit
    sheets = frappe.get_all(
        PLANNING_SHEET_DOCTYPE,
        filters={
            "allocated_unit": unit_name,
            "planning_status": ["in", ["Finalized", "In Production"]],
            "docstatus": 1,
        },
        fields=["total_weight"],
    )
    
    total_queue_weight = sum([flt(sheet.total_weight) for sheet in sheets])
    
    # Update unit capacity
    unit_capacity = frappe.get_doc("Unit Capacity", unit_name)
    unit_capacity.current_queue_weight = total_queue_weight
    unit_capacity.queue_count = len(sheets)
    
    total_capacity = flt(unit_capacity.day_shift_capacity_kg) + flt(unit_capacity.night_shift_capacity_kg)
    unit_capacity.available_capacity = total_capacity - total_queue_weight
    unit_capacity.last_updated = now_datetime()
    
    unit_capacity.save(ignore_permissions=True)


# Scheduled Tasks

def daily_capacity_reset():
    """Reset capacity counters daily"""
    units = frappe.get_all("Unit Capacity", filters={"is_active": 1})
    
    for unit in units:
        update_unit_capacity_usage(unit.name)


def update_production_queue():
    """Update production queue hourly"""
    # Get all units
    units = frappe.get_all("Unit Capacity", filters={"is_active": 1}, pluck="name")
    
    for unit in units:
        # Get all sheets in production
        sheets = frappe.get_all(
            PLANNING_SHEET_DOCTYPE,
            filters={
                "allocated_unit": unit,
                "planning_status": "In Production",
                "docstatus": 1,
            },
            fields=["name", "total_weight", "estimated_production_days"],
        )
        
        # Check if any sheets are completed (logic can be enhanced)
        for sheet in sheets:
            # This is a placeholder - implement actual completion logic
            pass
# ------------------------------------------------------------
# AUTOMATED PLANNING SHEET CREATION (SALES ORDER HOOK)
# ------------------------------------------------------------

def auto_create_planning_sheet(doc, method=None):
    """Called on Sales Order Submit to create a Planning Sheet automatically."""
    try:
        # Avoid double creation
        if frappe.db.exists("Planning Sheet", {"sales_order": doc.name, "docstatus": ["<", 2]}):
            return

        ps = frappe.new_doc("Planning Sheet")
        ps.sales_order = doc.name
        ps.customer = doc.customer
        ps.ordered_date = doc.transaction_date
        ps.delivery_date = doc.delivery_date
        ps.planning_status = "Draft"
        
        # Populate Items
        for item in doc.items:
            ps.append("planned_items", {
                "sales_order_item": item.name,
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty": item.qty,
                "uom": item.uom,
                "gsm": item.get("gsm") or 0,
                "width_inch": item.get("width_inch") or 0
            })

        # Fix MandatoryError: quality
        if not ps.get("quality"):
            ps.quality = "Standard"

        ps.flags.ignore_permissions = True
        ps.insert()
        frappe.db.commit()
        
        frappe.msgprint(f"Planning Sheet <b>{ps.name}</b> created and synced from Sales Order.")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Auto Create Planning Sheet Failed")

@frappe.whitelist()
def sync_to_planning_table(doc, method=None):
    """Sync Production Plan data back to Planning Table if needed."""
    pass


# Whitelisted Methods

@frappe.whitelist()
def get_unit_queue_status(unit_name):
    """Get current queue status for a unit"""
    sheets = frappe.get_all(
        PLANNING_SHEET_DOCTYPE,
        filters={
            "allocated_unit": unit_name,
            "planning_status": ["in", ["Finalized", "In Production"]],
            "docstatus": 1,
        },
        fields=["name", "customer", "total_weight", "queue_position", "dod", "planning_status"],
        order_by="queue_position asc",
    )
    
    capacity = frappe.db.get_value("Unit Capacity", unit_name, 
                                   ["current_queue_weight", "available_capacity", 
                                    "day_shift_capacity_kg", "night_shift_capacity_kg"],
                                   as_dict=True)
    
    return {
        "sheets": sheets,
        "capacity": capacity
    }


@frappe.whitelist()
def get_quality_based_recommendation(quality, gsm):
    """Get unit recommendation based on quality and GSM"""
    UNIT_1 = ["SUPER PLATINUM", "PLATINUM", "PREMIUM", "GOLD", "SUPER CLASSIC"]
    UNIT_2 = ["GOLD", "SILVER", "BRONZE", "CLASSIC", "ECO SPECIAL", "ECO SPL"]
    UNIT_3 = ["SUPER PLATINUM", "PLATINUM", "PREMIUM", "GOLD", "SILVER", "BRONZE"]
    
    quality_upper = quality.upper() if quality else ""
    gsm_value = flt(gsm)
    
    recommended_unit = None
    
    if gsm_value > 50 and quality_upper in UNIT_1:
        recommended_unit = "Unit 1"
    elif gsm_value > 20 and quality_upper in UNIT_2:
        recommended_unit = "Unit 2"
    elif gsm_value > 10 and quality_upper in UNIT_3:
        recommended_unit = "Unit 3"
    elif gsm_value > 10:
        recommended_unit = "Unit 4"
    
    return recommended_unit


# Validation Hook
def validate_planning_sheet(doc, method):
    """Called from hooks on validate"""
    doc.validate()

# Unit Allocation Hook
def allocate_unit(doc, method):
    """Called from hooks before save"""
    doc.before_save()

# Queue Update Hook
def update_queue(doc, method):
    """Called from hooks on submit"""
    doc.on_submit()

