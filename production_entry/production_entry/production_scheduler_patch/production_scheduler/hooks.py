# Revert: Restoring stable version of Production Scheduler
app_name = "production_scheduler"
app_title = "Production Scheduler"
app_publisher = "Admin"
app_description = "Production Scheduler App"
app_email = "admin@example.com"
app_license = "mit"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/production_scheduler/css/production_scheduler.css"
app_include_js = "production_scheduler.bundle.js"



doc_events = {
    "Sales Order": {
        "on_submit": "production_scheduler.api.auto_create_planning_sheet"
    },
    "Planning sheet": {
        "before_validate": "production_scheduler.api.normalize_planning_sheet_customer_link",
        "validate": "production_scheduler.api.validate_planning_sheet_duplicates",
        "before_cancel": "production_scheduler.api.ensure_child_table_schema_for_planning_cancel",
    },
    "Work Order": {
        "before_validate": "production_scheduler.api.normalize_work_order_pending_status"
    },
    "Shaft Production Run": {
        "before_validate": "production_scheduler.api.normalize_linked_work_orders_for_spr",
        "before_submit": "production_scheduler.api.normalize_linked_work_orders_for_spr"
    }
}
