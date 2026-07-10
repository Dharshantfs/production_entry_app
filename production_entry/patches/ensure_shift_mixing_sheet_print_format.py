# -*- coding: utf-8 -*-
"""Excel-style Print Format for Shift Mixing Sheet."""

import frappe

PRINT_HTML = r"""
<style>
.sms-print { font-family: Arial, Helvetica, sans-serif; font-size: 10px; color: #000; }
.sms-print h1 { text-align: center; font-size: 18px; margin: 0 0 4px; letter-spacing: 1px; }
.sms-meta { text-align: center; font-size: 11px; margin-bottom: 10px; }
.sms-meta span { margin: 0 10px; }
.sms-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.sms-table th, .sms-table td {
  border: 1px solid #000;
  padding: 3px 2px;
  text-align: center;
  vertical-align: middle;
  word-wrap: break-word;
}
.sms-hg-pp { background: #b4d7f0; font-weight: 700; }
.sms-hg-filler { background: #c6e0b4; font-weight: 700; }
.sms-hg-colour { background: #ffe699; font-weight: 700; }
.sms-hg-mod { background: #f4b084; font-weight: 700; }
.sms-hg-time { background: #d9e1f2; font-weight: 700; }
.sms-h2 { background: #f2f2f2; font-weight: 700; font-size: 9px; }
.sms-sno { width: 28px; background: #fff; font-weight: 600; }
.sms-num { font-variant-numeric: tabular-nums; }
.sms-consumed { background: #e8f5e9; }
.sms-set-title { font-weight: 700; margin: 14px 0 6px; font-size: 11px; }
.sms-foot { margin-top: 12px; font-size: 10px; }
</style>

{% set ctx = doc.get_mixing_print_context() %}

<div class="sms-print">
  <h1>MIXING SHEET</h1>
  <div class="sms-meta">
    <span><b>{{ doc.name }}</b></span>
    <span>{{ frappe.utils.formatdate(doc.run_date) }}</span>
    <span>{{ doc.shift or '' }}</span>
    <span>{{ doc.custom_unit or '' }}</span>
    {% if ctx.mixing_type %}<span>{{ ctx.mixing_type }}</span>{% endif %}
    {% if doc.order_code %}<span>Order: {{ doc.order_code }}</span>{% endif %}
  </div>

  {% if not ctx.sets %}
  <p>No mixing grid saved yet.</p>
  {% endif %}

  {% for set_block in ctx.sets %}
  <div class="sms-set-title">Raw Material Set {{ set_block.index }}</div>

  {% if ctx.is_printing %}
  {% set p = set_block.printing %}
  <table class="sms-table">
    <thead>
      <tr>
        <th class="sms-sno" rowspan="2">S.NO</th>
        <th class="sms-hg-pp" colspan="1">{{ p.ink_label or 'BOPP Ink' }}</th>
        {% if p.materials.EthylAcetate %}<th class="sms-hg-filler" colspan="1">Ethyl Acetate</th>{% endif %}
        {% if p.materials.Toluene %}<th class="sms-hg-filler" colspan="1">Toluene</th>{% endif %}
        {% if p.materials.IsoButanol %}<th class="sms-hg-filler" colspan="1">Iso Butanol</th>{% endif %}
        <th class="sms-hg-time" rowspan="2">TIME</th>
      </tr>
      <tr class="sms-h2">
        <th>kg</th>
        {% if p.materials.EthylAcetate %}<th>kg</th>{% endif %}
        {% if p.materials.Toluene %}<th>kg</th>{% endif %}
        {% if p.materials.IsoButanol %}<th>kg</th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for row in p.rows %}
      <tr class="{% if row.consumed %}sms-consumed{% endif %}">
        <td class="sms-sno">{{ loop.index }}</td>
        <td class="sms-num">{{ row.ink }}</td>
        {% if p.materials.EthylAcetate %}<td class="sms-num">{{ row.ethyl_acetate }}</td>{% endif %}
        {% if p.materials.Toluene %}<td class="sms-num">{{ row.toluene }}</td>{% endif %}
        {% if p.materials.IsoButanol %}<td class="sms-num">{{ row.iso_butanol }}</td>{% endif %}
        <td>{{ row.time }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {% else %}
  <table class="sms-table">
    <thead>
      <tr>
        <th class="sms-sno" rowspan="2">S.NO</th>
        <th class="sms-hg-pp" colspan="{{ ctx.pp_columns|length }}">POLYPROPYLENE</th>
        <th class="sms-hg-filler" colspan="{{ ctx.filler_columns|length }}">FILLER</th>
        <th class="sms-hg-colour" colspan="{{ ctx.colour_columns|length }}">COLOURS</th>
        <th class="sms-hg-mod" rowspan="2">MODIFIER</th>
        <th class="sms-hg-time" rowspan="2">TIME</th>
      </tr>
      <tr class="sms-h2">
        {% for key, label in ctx.pp_columns %}<th>{{ label }}</th>{% endfor %}
        {% for key, label in ctx.filler_columns %}<th>{{ label }}</th>{% endfor %}
        {% for key, label in ctx.colour_columns %}<th>{{ label }}</th>{% endfor %}
      </tr>
    </thead>
    <tbody>
      {% for row in set_block.rows %}
      <tr class="{% if row.consumed %}sms-consumed{% endif %}">
        <td class="sms-sno">{{ loop.index }}</td>
        {% for key, label in ctx.pp_columns %}
        <td class="sms-num">{{ row.pp.get(key, '') }}</td>
        {% endfor %}
        {% for key, label in ctx.filler_columns %}
        <td class="sms-num">{{ row.filler.get(key, '') }}</td>
        {% endfor %}
        {% for key, label in ctx.colour_columns %}
        <td class="sms-num">{{ row.colours.get(key, '') }}</td>
        {% endfor %}
        <td class="sms-num">{{ row.modifier }}</td>
        <td>{{ row.time }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  {% endfor %}

  <div class="sms-foot">
    {% if doc.completed_by %}Completed by: {{ doc.completed_by }}{% endif %}
    {% if doc.completed_on %} &nbsp;|&nbsp; {{ frappe.utils.format_datetime(doc.completed_on) }}{% endif %}
  </div>
</div>
"""


def execute():
	name = "Shift Mixing Sheet Excel"
	if frappe.db.exists("Print Format", name):
		frappe.db.set_value(
			"Print Format",
			name,
			{
				"doc_type": "Shift Mixing Sheet",
				"html": PRINT_HTML,
				"print_format_type": "Jinja",
				"custom_format": 1,
				"disabled": 0,
			},
			update_modified=True,
		)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": name,
				"doc_type": "Shift Mixing Sheet",
				"module": "Production Planning",
				"print_format_type": "Jinja",
				"standard": "No",
				"custom_format": 1,
				"html": PRINT_HTML,
			}
		)
		doc.insert(ignore_permissions=True)

	# Default print format on DocType (Customize Form meta)
	if frappe.db.exists("DocType", "Shift Mixing Sheet"):
		frappe.db.set_value(
			"DocType",
			"Shift Mixing Sheet",
			"default_print_format",
			name,
			update_modified=False,
		)

	frappe.clear_cache(doctype="Shift Mixing Sheet")
	frappe.db.commit()
