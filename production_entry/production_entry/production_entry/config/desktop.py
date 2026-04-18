# -*- coding: utf-8 -*-
from frappe import _


def get_data():
	return [
		{
			"module_name": "Production Planning",
			"type": "module",
			"label": _("Production Planning"),
			"color": "grey",
			"icon": "octicon octicon-calendar",
			"description": _("Planning sheets, production board, color chart, and queue."),
		}
	]
