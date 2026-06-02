from . import __version__ as app_version

app_name = "production_entry"
app_title = "Production Planning"
app_publisher = "Your Company"
app_description = "Production Planning and Queuing System for Manufacturing Units"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "info@yourcompany.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# Scheduler board / Color Chart Vue (production_scheduler POC merged here)
app_include_css = [
	"/assets/production_entry/css/scheduler.css",
	"/assets/production_entry/css/planning_order_tables.css",
]
app_include_js = "scheduler.bundle.js"

# include js, css files in header of web template
# web_include_css = "/assets/production_entry/css/production_entry.css"
# web_include_js = "/assets/production_entry/js/production_entry.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "production_entry/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Planning sheet": [
        "public/js/production_entry.js",
        "public/js/planning_sheet_custom.js",
    ],
    "Shaft Production Run": "public/js/shaft_production_run.js",
    "Roll Production Entry": "public/js/roll_production_entry.js",
    "Transfer Approval": "public/js/transfer_approval_form.js",
    "Stock Entry": "public/js/stock_entry_transfer.js",
}
doctype_list_js = {
	"Transfer Approval": "public/js/transfer_approval_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "production_entry.install.before_install"
# Install/migrate hooks MUST live in install.py — not setup.py (setuptools build file at app root).
after_install = "production_entry.install.after_install"
after_migrate = ["production_entry.install.after_migrate"]

# Desk Notifications
# -------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "production_entry.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Stock Entry": "production_entry.stock_entry_override.SPRStockEntryOverride",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Sales Order": {
        "on_submit": "production_entry.production_planning.scheduler_api.auto_create_planning_sheet",
    },
    "Planning sheet": {
        "before_validate": "production_entry.production_planning.scheduler_hooks.planning_sheet_before_validate",
        "validate": "production_entry.production_planning.scheduler_hooks.planning_sheet_validate_combined",
        "before_save": "production_entry.production_planning.scheduler_hooks.planning_sheet_allocate_unit",
        "on_update": "production_entry.production_planning.scheduler_hooks.planning_sheet_on_update",
        "on_submit": "production_entry.production_planning.scheduler_hooks.planning_sheet_update_queue",
        "before_cancel": "production_entry.production_planning.scheduler_hooks.planning_sheet_before_cancel",
    },
    "Production Plan": {
        "validate": "production_entry.production_planning.scheduler_api.normalize_production_plan_multi_uom_rm_requirements",
        "before_save": "production_entry.production_planning.scheduler_api.normalize_production_plan_multi_uom_rm_requirements",
        "on_submit": "production_entry.production_planning.scheduler_api.on_production_plan_submitted",
    },
    "Work Order": {
        "before_validate": [
            "production_entry.production_planning.scheduler_api.sync_work_order_custom_production_plan",
            "production_entry.production_planning.scheduler_api.normalize_work_order_pending_status",
        ],
    },
    "Shaft Production Run": {
        "before_validate": "production_entry.production_planning.scheduler_api.normalize_linked_work_orders_for_spr",
        "before_submit": "production_entry.production_planning.scheduler_api.normalize_linked_work_orders_for_spr",
    },
    "Stock Entry": {
        "on_submit": "production_entry.production_planning.transfer_logistics.stock_entry_on_submit",
    },
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "production_entry.production_planning.doctype.planning_sheet.planning_sheet.daily_capacity_reset"
    ],
    "hourly": [
        "production_entry.production_planning.doctype.planning_sheet.planning_sheet.update_production_queue"
    ]
}

# Testing
# -------

# before_tests = "production_entry.install.before_tests"

# Overriding Methods
# ------------------------------
# Route legacy production_scheduler API names to the canonical implementation (255/108 BOM sync).
override_whitelisted_methods = {
	"production_scheduler.api.regenerate_planning_sheet": "production_entry.production_planning.scheduler_api.regenerate_planning_sheet",
	"production_scheduler.api.create_planning_sheet_from_so": "production_entry.production_planning.scheduler_api.create_planning_sheet_from_so",
	"production_scheduler.api.sync_bom_children_for_planning_sheet": "production_entry.production_planning.scheduler_api.sync_bom_children_for_planning_sheet",
	"production_scheduler.api.make_planning_sheet_from_sales_order": "production_entry.production_planning.scheduler_api.make_planning_sheet_from_sales_order",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "production_entry.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

user_data_fields = [
    {
        "doctype": "{doctype_1}",
        "filter_by": "{filter_by}",
        "redact_fields": ["{field_1}", "{field_2}"],
        "partial": 1,
    },
    {
        "doctype": "{doctype_2}",
        "filter_by": "{filter_by}",
        "partial": 1,
    },
    {
        "doctype": "{doctype_3}",
        "strict": False,
    },
    {
        "doctype": "{doctype_4}"
    }
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"production_entry.auth.validate"
# ]
