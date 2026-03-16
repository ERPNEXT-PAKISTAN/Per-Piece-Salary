app_name = "per_piece_payroll"
app_title = "Per Piece Payroll"
app_publisher = "TCPL"
app_description = "Per Piece Payroll and Salary Management"
app_email = "admin@tcpl.local"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext", "hrms"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "per_piece_payroll",
# 		"logo": "/assets/per_piece_payroll/logo.png",
# 		"title": "Per Piece Payroll",
# 		"route": "/per_piece_payroll",
# 		"has_permission": "per_piece_payroll.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/per_piece_payroll/css/per_piece_payroll.css"
# app_include_js = "/assets/per_piece_payroll/js/per_piece_payroll.js"

# include js, css files in header of web template
# web_include_css = "/assets/per_piece_payroll/css/per_piece_payroll.css"
# web_include_js = "/assets/per_piece_payroll/js/per_piece_payroll.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "per_piece_payroll/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "per_piece_payroll/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "per_piece_payroll.utils.jinja_methods",
# 	"filters": "per_piece_payroll.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "per_piece_payroll.install.before_install"
after_install = "per_piece_payroll.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "per_piece_payroll.uninstall.before_uninstall"
# after_uninstall = "per_piece_payroll.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "per_piece_payroll.utils.before_app_install"
# after_app_install = "per_piece_payroll.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "per_piece_payroll.utils.before_app_uninstall"
# after_app_uninstall = "per_piece_payroll.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "per_piece_payroll.notifications.get_notification_config"

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

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Per Piece Salary": {
		"validate": "per_piece_payroll.guards.protect_per_piece_salary_mutations",
		"before_update_after_submit": "per_piece_payroll.guards.protect_per_piece_salary_mutations",
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"per_piece_payroll.tasks.all"
# 	],
# 	"daily": [
# 		"per_piece_payroll.tasks.daily"
# 	],
# 	"hourly": [
# 		"per_piece_payroll.tasks.hourly"
# 	],
# 	"weekly": [
# 		"per_piece_payroll.tasks.weekly"
# 	],
# 	"monthly": [
# 		"per_piece_payroll.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "per_piece_payroll.install.before_tests"

# run setup on every migrate to keep scripts/fields synced
after_migrate = ["per_piece_payroll.install.after_migrate"]

fixtures = [
	{
		"dt": "DocType",
		"filters": [["name", "in", ["Per Piece Salary", "Per Piece"]]],
	},
	{
		"dt": "Custom Field",
		"filters": [
			["dt", "in", ["Per Piece", "Per Piece Salary", "Item"]],
			[
				"fieldname",
				"in",
				[
					"jv_status",
					"jv_entry_no",
					"jv_line_remark",
					"booked_amount",
					"paid_amount",
					"unpaid_amount",
					"payment_status",
					"payment_jv_no",
					"payment_refs",
					"payment_line_remark",
					"process_size",
					"item_group",
					"employee",
				],
			],
		],
	},
	{
		"dt": "Property Setter",
		"filters": [
			["doc_type", "=", "Per Piece Salary"],
			["field_name", "=", "po_number"],
			["property", "=", "reqd"],
		],
	},
	{
		"dt": "Server Script",
		"filters": [
			[
				"name",
				"in",
				[
					"get_per_piece_salary_report",
					"create_per_piece_salary_entry",
					"create_per_piece_salary_jv",
					"cancel_per_piece_salary_jv",
					"create_per_piece_salary_payment_jv",
					"cancel_per_piece_salary_payment_jv",
				],
			]
		],
	},
	{
		"dt": "Client Script",
		"filters": [["name", "in", ["Per Piece Salary Update Child"]]],
	},
	{
		"dt": "Report",
		"filters": [["name", "in", ["Per Piece Salary Report", "Per Piece Query Report Simple"]]],
	},
	{
		"dt": "Print Format",
		"filters": [["name", "in", ["Per Piece Print"]]],
	},
	{
		"dt": "Web Page",
		"filters": [["name", "in", ["per-piece-report"]]],
	},
	{
		"dt": "Custom HTML Block",
		"filters": [["name", "in", ["Advances"]]],
	},
]

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "per_piece_payroll.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "per_piece_payroll.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["per_piece_payroll.utils.before_request"]
# after_request = ["per_piece_payroll.utils.after_request"]

# Job Events
# ----------
# before_job = ["per_piece_payroll.utils.before_job"]
# after_job = ["per_piece_payroll.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"per_piece_payroll.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
