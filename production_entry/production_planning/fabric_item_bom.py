"""Shared fabric (process 100) item + BOM helpers for SPR Trail Order."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt

from production_entry.production_planning.scheduler_api import get_master_code, get_mix_item_details


def _cstr(v) -> str:
	return str(v or "").strip()


def _hsn_for_gsm(gsm: float) -> str:
	g = flt(gsm)
	if 15 <= g <= 24:
		return "56031100"
	if 25 <= g <= 70:
		return "56031200"
	if 71 <= g <= 150:
		return "56031300"
	if g > 150:
		return "56031400"
	return "56031100"


def _quality_key(quality: str) -> str:
	return _cstr(quality).upper()


def _color_key(color: str) -> str:
	return _cstr(color).upper()


def _load_quality_mix_map() -> dict[str, list[float]]:
	out: dict[str, list[float]] = {}
	try:
		rows = frappe.get_all(
			"Quality Master",
			fields=["quality_name", "pp_kgs", "filler_kgs", "ppa_kgs", "antistatic_kgs"],
		)
		for r in rows or []:
			key = _quality_key(r.get("quality_name"))
			if not key:
				continue
			out[key] = [
				flt(r.get("pp_kgs")),
				flt(r.get("filler_kgs")),
				flt(r.get("ppa_kgs")),
				flt(r.get("antistatic_kgs")),
			]
	except Exception:
		pass
	return out


def _load_color_masterbatch_map() -> dict[str, str]:
	out: dict[str, str] = {}
	try:
		rows = frappe.get_all("Colour Master", fields=["colour_name", "item_code"])
		for r in rows or []:
			key = _color_key(r.get("colour_name"))
			code = _cstr(r.get("item_code"))
			if key and code:
				out[key] = code
	except Exception:
		pass
	return out


def _load_color_ldr_map() -> dict[str, float]:
	out: dict[str, float] = {}
	try:
		rows = frappe.get_all("Colour Master", fields=["colour_name", "masterbatch_ldr_"])
		for r in rows or []:
			key = _color_key(r.get("colour_name"))
			if key:
				out[key] = flt(r.get("masterbatch_ldr_") or 1.1) or 1.1
	except Exception:
		pass
	return out


def _resolve_pp_item(quality: str, gsm: float, is_rice_bag_customer: bool = False) -> str:
	q = _quality_key(quality)
	g = flt(gsm)
	if q in {"DELUXE", "ULTRA", "SUPER ECO", "ECOGREEN", "ECO SPECIAL", "ECO SPL"}:
		return "PP - 1002012"
	if q == "LIFESTYLE":
		return "PP - 1002012" if g > 30 else "PP - 1002003"
	if q == "CLASSIC":
		return "PP - 1002012" if g > 30 else "PP - 1002003"
	if q in {"BRONZE", "SILVER", "GOLD", "PLATINUM", "PREMIUM"}:
		if g > 30:
			return "PP - 1002012"
		if 20 <= g <= 30:
			return "PP - 1002003"
		return "PP - 1002002"
	if q == "PLATINUM" and is_rice_bag_customer:
		return "PP - 1002002"
	return "PP - 1002001"


def _resolve_filler_item(quality: str, is_rice_bag_customer: bool = False) -> str:
	q = _quality_key(quality)
	if q in {"DELUXE", "ULTRA", "SUPER ECO", "ECOGREEN", "ECO SPECIAL", "ECO SPL", "LIFESTYLE", "CLASSIC"}:
		return "FL - 1003013"
	if q in {"BRONZE", "SILVER", "GOLD", "PLATINUM", "PREMIUM"}:
		return "FL - 1003013"
	if q == "PLATINUM" and is_rice_bag_customer:
		return "FL - 1003009"
	return "FL - 1003011"


def resolve_fabric_item_code(quality, color, gsm, width_inch) -> dict:
	"""Build process-100 fabric item code from masters."""
	details = get_mix_item_details(quality, color, gsm, str(width_inch))
	if not details:
		frappe.throw(_("Could not resolve fabric item code for quality {0}, color {1}.").format(quality, color))
	row = details[0]
	return {
		"item_code": row.get("item_code"),
		"item_name": row.get("item_name"),
		"width_inch": row.get("width_inch"),
		"width_mm": row.get("width_mm"),
		"gsm": int(flt(gsm)),
	}


@frappe.whitelist()
def ensure_fabric_item(company, quality, color, gsm, width_inch, default_warehouse=None):
	"""Create fabric Item if missing (mix-roll style fields)."""
	resolved = resolve_fabric_item_code(quality, color, gsm, width_inch)
	item_code = _cstr(resolved.get("item_code"))
	if not item_code:
		frappe.throw(_("Item code could not be resolved."))
	if frappe.db.exists("Item", item_code):
		return {"item_code": item_code, "created": 0, **resolved}

	company = _cstr(company) or frappe.defaults.get_global_default("company")
	wh = _cstr(default_warehouse) or "Finished Goods - JSB-1ZT"
	g = flt(gsm)
	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = resolved.get("item_name") or item_code
	item.item_group = "Products"
	item.stock_uom = "Kg"
	item.sales_uom = "Kg"
	item.weight_uom = "Kg"
	item.is_stock_item = 1
	item.valuation_method = "FIFO"
	item.valuation_rate = 100
	item.has_batch_no = 1
	item.default_material_request_type = "Material Transfer"
	item.append("item_defaults", {"company": company, "default_warehouse": wh})
	tax_template = frappe.db.get_value("Item Tax Template", {"name": ["like", "%GST 5%"]}, "name")
	if tax_template:
		item.append("taxes", {"item_tax_template": tax_template, "tax_category": ""})
	meta = frappe.get_meta("Item")
	hsn = _hsn_for_gsm(g)
	if meta.has_field("gst_hsn_code"):
		item.gst_hsn_code = hsn
	elif meta.has_field("hsn_code"):
		item.hsn_code = hsn
	if meta.has_field("custom_quality"):
		item.custom_quality = quality
	if meta.has_field("custom_color"):
		item.custom_color = color
	if meta.has_field("custom_gsm"):
		item.custom_gsm = g
	if meta.has_field("custom_width_inch"):
		item.custom_width_inch = resolved.get("width_inch")
	item.insert(ignore_permissions=True)
	return {"item_code": item_code, "created": 1, **resolved}


def _existing_bom_name(item_code: str) -> str | None:
	for filt in (
		{"item": item_code, "is_active": 1, "is_default": 1, "docstatus": 1},
		{"item": item_code, "is_active": 1, "docstatus": 1},
		{"item": item_code, "is_active": 1},
	):
		name = frappe.db.get_value("BOM", filt, "name")
		if name:
			return name
	return None


def _build_bom_lines(quality, color, gsm, color_code: str = "", is_rice_bag_customer: bool = False):
	q_key = _quality_key(quality)
	c_key = _color_key(color)
	mix_map = _load_quality_mix_map()
	mb_map = _load_color_masterbatch_map()
	ldr_map = _load_color_ldr_map()

	if not color_code:
		color_code = get_master_code(
			"Colour Master",
			color,
			["custom_color_code", "color_code", "short_code", "colour_code", "code"],
		)
	color_code = _cstr(color_code).zfill(3)[:3]

	mapped_mb = _cstr(mb_map.get(c_key))
	mb_item = mapped_mb if mapped_mb and frappe.db.exists("Item", mapped_mb) else f"MB - 1001{color_code}"
	if not frappe.db.exists("Item", mb_item):
		frappe.throw(_("Masterbatch item {0} not found for color {1}.").format(mb_item, color))

	ldr_percent = flt(ldr_map.get(c_key, 1.1) or 1.1) or 1.1
	pp_item = _resolve_pp_item(quality, gsm, is_rice_bag_customer=is_rice_bag_customer)
	fl_item = _resolve_filler_item(quality, is_rice_bag_customer=is_rice_bag_customer)
	ppa_item = "SA - 1004001"
	anti_item = "SA - 1004002"
	for rm in (pp_item, ppa_item, anti_item):
		if not frappe.db.exists("Item", rm):
			frappe.throw(_("Raw material {0} not found. Create it before fabric BOM.").format(rm))

	ratios = mix_map.get(q_key, [100.0, 35.0, 0.2, 0.2])
	parts_pp = flt(ratios[0] if len(ratios) > 0 else 100.0)
	parts_fl = flt(ratios[1] if len(ratios) > 1 else 35.0)
	parts_ppa = flt(ratios[2] if len(ratios) > 2 else 0.2)
	parts_anti = flt(ratios[3] if len(ratios) > 3 else 0.2)
	base_tot = parts_pp + parts_fl
	mb_weight = (base_tot * ldr_percent) / 100.0
	total_batch = base_tot + parts_ppa + parts_anti + mb_weight
	if total_batch <= 0:
		frappe.throw(_("Quality Master ratios for {0} produce zero batch weight.").format(quality))
	factor = 1.0 / total_batch

	lines = [
		{"item_code": pp_item, "qty": round(parts_pp * factor, 5), "uom": "Kg"},
	]
	fl_qty = round(parts_fl * factor, 5)
	if fl_qty > 0 and frappe.db.exists("Item", fl_item):
		lines.append({"item_code": fl_item, "qty": fl_qty, "uom": "Kg"})
	lines.extend(
		[
			{"item_code": ppa_item, "qty": round(parts_ppa * factor, 5), "uom": "Kg"},
			{"item_code": anti_item, "qty": round(parts_anti * factor, 5), "uom": "Kg"},
			{"item_code": mb_item, "qty": round(mb_weight * factor, 5), "uom": "Kg"},
		]
	)
	return lines, ldr_percent


def ensure_nonwoven_fabric_bom(
	item_code,
	company,
	quality,
	color,
	gsm=None,
	is_rice_bag_customer: bool = False,
):
	"""Create/submit default fabric BOM when missing."""
	item_code = _cstr(item_code)
	if not item_code or not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found.").format(item_code))
	company = _cstr(company) or frappe.defaults.get_global_default("company")

	existing = _existing_bom_name(item_code)
	if existing:
		if frappe.db.get_value("BOM", existing, "docstatus") == 0:
			try:
				frappe.get_doc("BOM", existing).submit()
			except Exception:
				pass
		return existing

	if gsm is None:
		ic = item_code
		try:
			gsm = int(flt(ic[9:12])) if len(ic) >= 12 else 0
		except Exception:
			gsm = 0

	lines, ldr_percent = _build_bom_lines(quality, color, gsm, is_rice_bag_customer=is_rice_bag_customer)
	bom = frappe.new_doc("BOM")
	bom.company = company
	bom.item = item_code
	bom.quantity = 1.0
	bom.is_default = 1
	bom.is_active = 1
	bom.currency = "INR"
	bom.rm_cost_as_per = "Valuation Rate"
	bom_meta = frappe.get_meta("BOM")
	if bom_meta.has_field("custom_ldr_"):
		bom.custom_ldr_ = ldr_percent
	for ln in lines:
		bom.append("items", {"item_code": ln["item_code"], "qty": ln["qty"], "uom": ln.get("uom") or "Kg"})
	bom.insert(ignore_permissions=True)
	bom.submit()
	return bom.name


@frappe.whitelist()
def preview_fabric_bom(item_code, company=None, quality=None, color=None, gsm=None):
	"""Return BOM line preview for UI."""
	item_code = _cstr(item_code)
	if not item_code:
		frappe.throw(_("Item code is required"))
	bom_name = _existing_bom_name(item_code)
	if bom_name:
		lines = []
		for row in frappe.get_all(
			"BOM Item",
			filters={"parent": bom_name},
			fields=["item_code", "qty", "uom"],
			order_by="idx asc",
		):
			lines.append(
				{
					"item_code": row.item_code,
					"item_name": frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code,
					"qty": flt(row.qty),
					"uom": row.uom or "Kg",
				}
			)
		ldr = frappe.db.get_value("BOM", bom_name, "custom_ldr_") if frappe.get_meta("BOM").has_field("custom_ldr_") else None
		return {"bom": bom_name, "lines": lines, "ldr_percent": flt(ldr)}

	if not quality or not color:
		frappe.throw(_("Quality and color are required to preview BOM when no BOM exists yet."))
	lines, ldr_percent = _build_bom_lines(quality, color, gsm or 0)
	out = []
	for ln in lines:
		out.append(
			{
				"item_code": ln["item_code"],
				"item_name": frappe.db.get_value("Item", ln["item_code"], "item_name") or ln["item_code"],
				"qty": ln["qty"],
				"uom": ln.get("uom") or "Kg",
			}
		)
	return {"bom": None, "lines": out, "ldr_percent": ldr_percent}


def _recipe_payload_to_bom_lines(pp_rows, fl_rows, ad_rows, mb_rows, mb_ldr):
	"""Normalize Smart-BOM-style recipe rows to per-1-Kg BOM lines."""
	pp_rows = [r for r in (pp_rows or []) if _cstr(r.get("item_code")) and flt(r.get("qty")) > 0]
	fl_rows = [r for r in (fl_rows or []) if _cstr(r.get("item_code")) and flt(r.get("qty")) > 0]
	ad_rows = [r for r in (ad_rows or []) if _cstr(r.get("item_code")) and flt(r.get("qty")) > 0]
	mb_rows = [r for r in (mb_rows or []) if _cstr(r.get("item_code"))]

	if not pp_rows:
		frappe.throw(_("At least one PP row with quantity is required."))

	pp_total = sum(flt(r.get("qty")) for r in pp_rows)
	fl_total = sum(flt(r.get("qty")) for r in fl_rows)
	ad_total = sum(flt(r.get("qty")) for r in ad_rows)
	ldr_percent = flt(mb_ldr) or 0
	mb_kgs = ((pp_total + fl_total) * ldr_percent) / 100.0 if ldr_percent > 0 else 0
	grand = pp_total + fl_total + ad_total + mb_kgs
	if grand <= 0:
		frappe.throw(_("Total recipe weight must be greater than zero."))
	factor = 1.0 / grand

	lines = []
	for r in pp_rows:
		lines.append(
			{
				"item_code": _cstr(r.get("item_code")),
				"qty": round(flt(r.get("qty")) * factor, 5),
				"uom": "Kg",
			}
		)
	for r in fl_rows:
		lines.append(
			{
				"item_code": _cstr(r.get("item_code")),
				"qty": round(flt(r.get("qty")) * factor, 5),
				"uom": "Kg",
			}
		)
	for r in ad_rows:
		lines.append(
			{
				"item_code": _cstr(r.get("item_code")),
				"qty": round(flt(r.get("qty")) * factor, 5),
				"uom": "Kg",
			}
		)
	if mb_kgs > 0:
		mb_code = _cstr(mb_rows[0].get("item_code")) if mb_rows else ""
		if not mb_code:
			frappe.throw(_("Masterbatch item is required when LDR is set."))
		if not frappe.db.exists("Item", mb_code):
			frappe.throw(_("Masterbatch item {0} not found.").format(mb_code))
		lines.append({"item_code": mb_code, "qty": round(mb_kgs * factor, 5), "uom": "Kg"})
	return lines, ldr_percent


def _bom_lines_for_response(lines):
	out = []
	for ln in lines:
		ic = ln["item_code"]
		out.append(
			{
				"item_code": ic,
				"item_name": frappe.db.get_value("Item", ic, "item_name") or ic,
				"qty": flt(ln["qty"]),
				"uom": ln.get("uom") or "Kg",
			}
		)
	return out


@frappe.whitelist()
def create_fabric_bom_from_recipe(
	item_code,
	company,
	quality,
	color,
	gsm=None,
	recipe_payload=None,
	force_new=0,
):
	"""Create/submit fabric BOM from Smart-BOM-style recipe payload (per 1 Kg FG)."""
	item_code = _cstr(item_code)
	if not item_code or not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} not found.").format(item_code))
	company = _cstr(company) or frappe.defaults.get_global_default("company")
	payload = frappe.parse_json(recipe_payload) if isinstance(recipe_payload, str) else (recipe_payload or {})
	lines, ldr_percent = _recipe_payload_to_bom_lines(
		payload.get("pp_rows"),
		payload.get("fl_rows"),
		payload.get("ad_rows"),
		payload.get("mb_rows"),
		payload.get("mb_ldr"),
	)

	if not cint(force_new):
		existing = _existing_bom_name(item_code)
		if existing:
			existing_lines = frappe.get_all(
				"BOM Item",
				filters={"parent": existing},
				fields=["item_code", "qty", "uom"],
				order_by="idx asc",
			)
			ldr = frappe.db.get_value("BOM", existing, "custom_ldr_") if frappe.get_meta("BOM").has_field("custom_ldr_") else None
			out = []
			for row in existing_lines:
				out.append(
					{
						"item_code": row.item_code,
						"item_name": frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code,
						"qty": flt(row.qty),
						"uom": row.uom or "Kg",
					}
				)
			return {"bom": existing, "lines": out, "ldr_percent": flt(ldr)}

	for old in frappe.get_all(
		"BOM",
		filters={"item": item_code, "is_default": 1, "docstatus": ["<", 2]},
		pluck="name",
	):
		try:
			frappe.db.set_value("BOM", old, "is_default", 0, update_modified=False)
		except Exception:
			pass

	bom = frappe.new_doc("BOM")
	bom.company = company
	bom.item = item_code
	bom.quantity = 1.0
	bom.is_default = 1
	bom.is_active = 1
	bom.currency = "INR"
	bom.rm_cost_as_per = "Valuation Rate"
	bom_meta = frappe.get_meta("BOM")
	if bom_meta.has_field("custom_ldr_"):
		bom.custom_ldr_ = ldr_percent
	for ln in lines:
		bom.append("items", {"item_code": ln["item_code"], "qty": ln["qty"], "uom": ln.get("uom") or "Kg"})
	bom.insert(ignore_permissions=True)
	bom.submit()
	return {"bom": bom.name, "lines": _bom_lines_for_response(lines), "ldr_percent": ldr_percent}
