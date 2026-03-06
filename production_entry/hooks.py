
app_name = "production_entry"
app_title = "Production Entry"
app_publisher = "Your Company"
app_description = "Integrated Production Entry for Multi-Width Fabric Manufacturing"
app_icon = "octicon octicon-checklist"
app_color = "blue"
app_email = "info@yourcompany.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/production_entry/css/production_entry.css"
# app_include_js = "/assets/production_entry/js/production_entry.js"

doctype_js = {}

doc_events = {}

scheduler_events = {}
after_install = "production_entry.production_entry.setup_custom_fields.execute"
after_migrate = "production_entry.production_entry.setup_custom_fields.execute"
