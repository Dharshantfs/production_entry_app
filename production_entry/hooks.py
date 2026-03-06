
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

doctype_js = {
    "Production Entry": "public/js/production_entry.js"
}

doc_events = {
	"Production Entry": {
		"on_submit": "production_entry.production_entry.doctype.production_entry.production_entry.on_submit"
	}
}

scheduler_events = {
	"daily": [
		"production_entry.production_entry.doctype.production_entry.production_entry.daily_cleanup"
	]
}
