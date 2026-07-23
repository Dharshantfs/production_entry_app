# -*- coding: utf-8 -*-
"""Clubbing Sheet helpers (Planning-first order list + Madurai distances).

Used by site Clubbing Sheet Client Script via:
  production_entry.production_planning.clubbing_api.get_planning_orders_for_clubbing
  production_entry.production_planning.clubbing_api.get_distances_from_madurai

Avoids Frappe Server Script RestrictedPython limits (no frappe.parse_json).
"""

from __future__ import annotations

import json

import frappe
import requests
from frappe import _
from frappe.utils import cint, cstr, flt


def _cstr(v):
	return cstr(v or "").strip()


@frappe.whitelist()
def get_planning_orders_for_clubbing():
	"""List Planning sheet orders that have Despatch movement rows, not already clubbed.

	Returns one row per Planning sheet (order), with:
	- party_code / sales_order from Planning sheet (SO is shown for reference + city)
	- city from Sales Order shipping Address
	- weight / rolls summed from Planning Table Despatch lines
	"""
	assigned_so = set()
	assigned_party = set()
	if frappe.db.exists("DocType", "Clubbing Sheet Item"):
		for r in frappe.db.sql(
			"""
			select distinct sales_order, party_code
			from `tabClubbing Sheet Item`
			where ifnull(docstatus, 0) < 2
			""",
			as_dict=True,
		) or []:
			if r.sales_order:
				assigned_so.add(_cstr(r.sales_order))
			if r.party_code:
				assigned_party.add(_cstr(r.party_code).upper())

	# Planning sheet + Despatch Planning Table only
	rows = frappe.db.sql(
		"""
		select
			ps.name as planning_sheet,
			ps.party_code,
			ps.customer,
			coalesce(c.customer_name, ps.customer) as customer_name,
			ps.sales_order,
			ps.total_weight as sheet_total_weight,
			ps.total_quantity as sheet_total_quantity,
			ps.planning_status,
			sum(ifnull(pt.no_of_rolls, 0)) as no_of_rolls,
			sum(ifnull(pt.total_weight, 0)) as pt_weight,
			count(pt.name) as despatch_line_count
		from `tabPlanning sheet` ps
		inner join `tabPlanning Table` pt on pt.parent = ps.name
		left join `tabCustomer` c on c.name = ps.customer
		where ifnull(ps.docstatus, 0) < 2
		  and ifnull(ps.planning_status, '') != 'Cancelled'
		  and ifnull(pt.custom_movement_type, '') = 'Despatch'
		group by ps.name
		order by ps.modified desc
		limit 2000
		""",
		as_dict=True,
	)

	so_names = list({_cstr(r.sales_order) for r in rows if r.sales_order})
	city_by_so = {}
	if so_names:
		addrs = frappe.db.sql(
			"""
			select so.name as so_name, ifnull(addr.city, '') as city
			from `tabSales Order` so
			left join `tabAddress` addr on addr.name = so.shipping_address_name
			where so.name in %(names)s
			""",
			{"names": so_names},
			as_dict=True,
		)
		for a in addrs or []:
			city_by_so[_cstr(a.so_name)] = _cstr(a.city)

	# Skip already stamped with a club (if column exists)
	has_club_col = frappe.db.has_column("Planning Table", "custom_clubbing_sheet")

	out = []
	for r in rows:
		so = _cstr(r.sales_order)
		party = _cstr(r.party_code)
		if so and so in assigned_so:
			continue
		if party and party.upper() in assigned_party:
			continue
		if has_club_col:
			already = frappe.db.sql(
				"""
				select 1 from `tabPlanning Table`
				where parent = %s
				  and ifnull(custom_movement_type, '') = 'Despatch'
				  and ifnull(custom_clubbing_sheet, '') != ''
				limit 1
				""",
				r.planning_sheet,
			)
			if already:
				continue

		weight = flt(r.pt_weight) or flt(r.sheet_total_weight) or flt(r.sheet_total_quantity)
		name = so or party or r.planning_sheet
		out.append(
			{
				"name": name,
				"planning_sheet": r.planning_sheet,
				"party_code": party,
				"customer": _cstr(r.customer),
				"customer_name": _cstr(r.customer_name or r.customer),
				"sales_order": so,
				"city": city_by_so.get(so, ""),
				"custom_party_code": party,
				"total_qty": weight,
				"no_of_rolls": flt(r.no_of_rolls),
				"weight_kgs": weight,
				"despatch_line_count": cint(r.despatch_line_count),
				"source": "planning_sheet",
			}
		)

	return out


def _google_api_key():
	key = ""
	if frappe.db.exists("DocType", "JSB Integrations"):
		key = frappe.db.get_single_value("JSB Integrations", "google_api_key") or ""
		if not key:
			try:
				key = frappe.utils.password.get_decrypted_password(
					"JSB Integrations", "JSB Integrations", "google_api_key"
				) or ""
			except Exception:
				key = ""
	if not key:
		key = frappe.conf.get("google_maps_api_key") or ""
	return _cstr(key)


@frappe.whitelist()
def get_distances_from_madurai(cities=None):
	"""Return {city: km} from Madurai via Google Routes API. Key from JSB Integrations."""
	if isinstance(cities, str):
		try:
			cities = json.loads(cities)
		except Exception:
			cities = [cities] if cities else []
	if not cities:
		cities = []
	cities = [_cstr(c) for c in cities if _cstr(c)]
	if not cities:
		return {}

	key = _google_api_key()
	if not key:
		frappe.throw(_("Set Google API Key in JSB Integrations"))

	body = {
		"origins": [{"waypoint": {"address": "Madurai, Tamil Nadu, India"}}],
		"destinations": [{"waypoint": {"address": f"{c}, India"}} for c in cities],
		"travelMode": "DRIVE",
		"routingPreference": "TRAFFIC_UNAWARE",
	}
	url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
	headers = {
		"Content-Type": "application/json",
		"X-Goog-Api-Key": key,
		"X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,status",
	}

	try:
		resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
	except Exception as e:
		frappe.throw(_("Routes API call failed: {0}").format(cstr(e)))

	if resp.status_code != 200:
		frappe.throw(_("Routes API HTTP {0}: {1}").format(resp.status_code, (resp.text or "")[:200]))

	data = resp.json()
	distance_map = {}
	if isinstance(data, list):
		for el in data:
			idx = el.get("destinationIndex")
			meters = el.get("distanceMeters")
			if idx is not None and meters is not None and idx < len(cities):
				distance_map[cities[idx]] = int(round(flt(meters) / 1000.0))

	return distance_map
