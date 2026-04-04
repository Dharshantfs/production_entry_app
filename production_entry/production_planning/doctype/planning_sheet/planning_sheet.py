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
            # Runs before super(): insert() also validates links before before_validate.
            self._normalize_child_table_units()
        super()._validate_links()

    def _normalize_child_table_units(self):
        for row in self.get("planned_items") or []:
            row.unit = normalize_planning_unit_for_select(getattr(row, "unit", None))
        for row in self.get("items") or []:
            row.unit = normalize_planning_unit_for_select(getattr(row, "unit", None))

    def validate(self):
        """Validate planning sheet before saving"""
        self.validate_items()
        self.calculate_totals()
        self.parse_item_details()

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
        """Update queue and create Production Plans + Work Orders on submit"""
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
    
    def create_production_docs(self):
        """Build separate Production Plans and Work Orders for each item to handle mixing details"""
        company = self._resolve_company_for_production_docs()
        if not company:
            frappe.throw(
                _("Set Company on Planning sheet or link a Sales Order with Company before submitting."),
                title=_("Company missing"),
            )
        for item in self.items:
            bom_no = get_default_bom_for_item(item.item_code, company)
            if not bom_no:
                frappe.throw(
                    _(
                        "No active default BOM found for item {0}. Set a default BOM on the BOM master before finalizing the Planning sheet."
                    ).format(item.item_code),
                    title=_("BOM No required"),
                )
            # Create Production Plan
            pp = frappe.get_doc({
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
                ]
            })
            pp.insert()
            pp.submit()
            
            # Create Work Order(s) from PP (ERPNext v15+ exposes make_work_order, not make_work_orders)
            if hasattr(pp, "make_work_order"):
                pp.make_work_order()
            elif hasattr(pp, "make_work_orders"):
                pp.make_work_orders()
            
            # Map WO name back to item
            wo_name = frappe.db.get_value("Work Order", {"production_plan": pp.name, "production_plan_item": pp.po_items[0].name}, "name")
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

def extract_quality_and_color(item_name):
    """Extract quality and color from item name"""
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
                "CHOCOLATE BROWN", "LIGHT BEIGE", "DARK BEIGE", "WHITE MIX", 
                "BLACK MIX", "COLOR MIX", "BEIGE MIX", "WHITE"]
    COL_LIST.sort(key=len, reverse=True)
    
    quality = ""
    color = ""
    item_upper = item_name.upper()
    
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
    
    return quality, color


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
        
        frappe.msgprint(f"âœ… Planning Sheet <b>{ps.name}</b> created and synced from Sales Order for April 1st Alignment.")
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

