from __future__ import annotations

import json

import frappe

from per_piece_payroll.per_piece_setup import apply

LEGACY_SERVER_SCRIPTS = (
	"get_per_piece_salary_report",
	"create_per_piece_salary_entry",
	"create_per_piece_salary_jv",
	"cancel_per_piece_salary_jv",
	"create_per_piece_salary_payment_jv",
	"cancel_per_piece_salary_payment_jv",
)

LEGACY_CLIENT_SCRIPTS = (
	"Per Piece Salary Auto Load",
	"Per Piece Salary Update Child",
)


def after_install() -> None:
	ensure_payment_doctypes()
	apply()
	ensure_workspace()
	cleanup_legacy_ui_scripts()


def after_migrate() -> None:
	ensure_payment_doctypes()
	apply()
	ensure_workspace()
	cleanup_legacy_ui_scripts()


def cleanup_legacy_ui_scripts() -> None:
	"""Force-remove legacy UI scripts so per_piece logic stays app-backed only."""
	if LEGACY_SERVER_SCRIPTS:
		frappe.db.sql(
			"""
			DELETE FROM `tabServer Script`
			WHERE name IN %(names)s
			""",
			{"names": tuple(LEGACY_SERVER_SCRIPTS)},
		)
	if LEGACY_CLIENT_SCRIPTS:
		frappe.db.sql(
			"""
			DELETE FROM `tabClient Script`
			WHERE name IN %(names)s
			""",
			{"names": tuple(LEGACY_CLIENT_SCRIPTS)},
		)
	frappe.db.commit()


def _upsert_field(doc, fieldname: str, spec: dict) -> None:
	for row in doc.fields or []:
		if row.fieldname == fieldname:
			for k, v in spec.items():
				setattr(row, k, v)
			return
	doc.append("fields", {"fieldname": fieldname, **spec})


def _delete_custom_field_if_exists(doctype: str, fieldname: str) -> None:
	existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
	if existing:
		frappe.delete_doc("Custom Field", existing, ignore_permissions=True, force=1)


def ensure_payment_doctypes() -> None:
	"""Create/upgrade payment transaction doctypes used by Per Piece payment stage."""

	def ensure_salary_summary_child() -> None:
		name = "Per Piece Salary Summary Row"
		if frappe.db.exists("DocType", name):
			doc = frappe.get_doc("DocType", name)
		else:
			doc = frappe.new_doc("DocType")
			doc.name = name
		doc.module = "Per Piece Payroll"
		doc.custom = 1
		doc.istable = 1
		_upsert_field(
			doc,
			"salary_entry",
			{"label": "Salary Entry", "fieldtype": "Link", "options": "Per Piece Salary", "in_list_view": 1},
		)
		_upsert_field(
			doc,
			"employee",
			{"label": "Employee", "fieldtype": "Link", "options": "Employee", "in_list_view": 1},
		)
		_upsert_field(
			doc, "employee_name", {"label": "Employee Name", "fieldtype": "Data", "in_list_view": 1}
		)
		_upsert_field(
			doc,
			"salary_amount",
			{"label": "Salary Amount", "fieldtype": "Float", "precision": "2", "in_list_view": 1},
		)
		_upsert_field(doc, "allowance", {"label": "Allowance", "fieldtype": "Float", "precision": "2"})
		_upsert_field(
			doc, "advance_deduction", {"label": "Advance Deduction", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc, "other_deduction", {"label": "Other Deduction", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc,
			"net_salary",
			{"label": "Net Salary", "fieldtype": "Float", "precision": "2", "in_list_view": 1},
		)
		_upsert_field(
			doc, "booked_amount", {"label": "Booked Amount", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(doc, "paid_amount", {"label": "Paid Amount", "fieldtype": "Float", "precision": "2"})
		_upsert_field(
			doc, "unpaid_amount", {"label": "Unpaid Amount", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(doc, "payment_status", {"label": "Payment Status", "fieldtype": "Data"})
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

	def ensure_salary_parent_field() -> None:
		if not frappe.db.exists("DocType", "Per Piece Salary"):
			return
		_delete_custom_field_if_exists("Per Piece Salary", "salary_summary_rows")
		doc = frappe.get_doc("DocType", "Per Piece Salary")
		_upsert_field(
			doc,
			"salary_summary_rows",
			{
				"label": "Salary Summary Rows",
				"fieldtype": "Table",
				"options": "Per Piece Salary Summary Row",
			},
		)
		doc.save(ignore_permissions=True)

	def ensure_batch_child_entry() -> None:
		name = "Per Piece Salary Batch Entry"
		if frappe.db.exists("DocType", name):
			doc = frappe.get_doc("DocType", name)
		else:
			doc = frappe.new_doc("DocType")
			doc.name = name
		doc.module = "Per Piece Payroll"
		doc.custom = 1
		doc.istable = 1
		_upsert_field(
			doc,
			"salary_entry",
			{"label": "Salary Entry", "fieldtype": "Link", "options": "Per Piece Salary", "in_list_view": 1},
		)
		_upsert_field(doc, "po_number", {"label": "PO Number", "fieldtype": "Data", "in_list_view": 1})
		_upsert_field(doc, "delivery_note", {"label": "Delivery Note", "fieldtype": "Data"})
		_upsert_field(doc, "total_salary", {"label": "Total Salary", "fieldtype": "Float", "precision": "2"})
		_upsert_field(doc, "allowance", {"label": "Allowance", "fieldtype": "Float", "precision": "2"})
		_upsert_field(
			doc, "advance_deduction", {"label": "Advance Deduction", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc, "other_deduction", {"label": "Other Deduction", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc,
			"net_salary",
			{"label": "Net Salary", "fieldtype": "Float", "precision": "2", "in_list_view": 1},
		)
		_upsert_field(doc, "paid_amount", {"label": "Paid Amount", "fieldtype": "Float", "precision": "2"})
		_upsert_field(
			doc, "unpaid_amount", {"label": "Unpaid Amount", "fieldtype": "Float", "precision": "2"}
		)
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

	def ensure_batch_child_summary() -> None:
		name = "Per Piece Salary Batch Summary Row"
		if frappe.db.exists("DocType", name):
			doc = frappe.get_doc("DocType", name)
		else:
			doc = frappe.new_doc("DocType")
			doc.name = name
		doc.module = "Per Piece Payroll"
		doc.custom = 1
		doc.istable = 1
		_upsert_field(
			doc,
			"employee",
			{"label": "Employee", "fieldtype": "Link", "options": "Employee", "in_list_view": 1},
		)
		_upsert_field(
			doc, "employee_name", {"label": "Employee Name", "fieldtype": "Data", "in_list_view": 1}
		)
		_upsert_field(
			doc, "salary_amount", {"label": "Salary Amount", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(doc, "allowance", {"label": "Allowance", "fieldtype": "Float", "precision": "2"})
		_upsert_field(
			doc, "advance_deduction", {"label": "Advance Deduction", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc, "other_deduction", {"label": "Other Deduction", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc,
			"net_salary",
			{"label": "Net Salary", "fieldtype": "Float", "precision": "2", "in_list_view": 1},
		)
		_upsert_field(doc, "paid_amount", {"label": "Paid Amount", "fieldtype": "Float", "precision": "2"})
		_upsert_field(
			doc, "unpaid_amount", {"label": "Unpaid Amount", "fieldtype": "Float", "precision": "2"}
		)
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

	def ensure_batch_parent() -> None:
		name = "Per Piece Salary Batch"
		if frappe.db.exists("DocType", name):
			doc = frappe.get_doc("DocType", name)
		else:
			doc = frappe.new_doc("DocType")
			doc.name = name
			doc.autoname = "naming_series:"
			doc.naming_rule = 'By "Naming Series" field'
			doc.append(
				"fields",
				{
					"fieldname": "naming_series",
					"label": "Series",
					"fieldtype": "Data",
					"default": "PPE-BATCH-.YYYY.-",
					"reqd": 1,
				},
			)
		doc.module = "Per Piece Payroll"
		doc.custom = 1
		doc.istable = 0
		_upsert_field(
			doc, "posting_date", {"label": "Posting Date", "fieldtype": "Date", "default": "Today", "reqd": 1}
		)
		_upsert_field(doc, "company", {"label": "Company", "fieldtype": "Link", "options": "Company"})
		_upsert_field(doc, "remarks", {"label": "Remarks", "fieldtype": "Small Text"})
		_upsert_field(
			doc,
			"total_salary_amount",
			{"label": "Total Salary Amount", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(
			doc,
			"total_allowance",
			{"label": "Total Allowance", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(
			doc,
			"total_advance_deduction",
			{"label": "Total Advance Deduction", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(
			doc,
			"total_other_deduction",
			{"label": "Total Other Deduction", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(
			doc,
			"total_net_salary",
			{"label": "Total Net Salary", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(
			doc,
			"total_paid_amount",
			{"label": "Total Paid Amount", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(
			doc,
			"total_unpaid_amount",
			{"label": "Total Unpaid Amount", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(
			doc, "entries_section", {"label": "Linked Salary Entries", "fieldtype": "Section Break"}
		)
		_upsert_field(
			doc,
			"entries",
			{"label": "Entries", "fieldtype": "Table", "options": "Per Piece Salary Batch Entry"},
		)
		_upsert_field(doc, "summary_section", {"label": "Employee Summary", "fieldtype": "Section Break"})
		_upsert_field(
			doc,
			"summary_rows",
			{"label": "Summary Rows", "fieldtype": "Table", "options": "Per Piece Salary Batch Summary Row"},
		)
		for role in ("System Manager", "HR Manager", "HR User", "Stock User"):
			if not any((p.role == role and p.permlevel == 0) for p in (doc.permissions or [])):
				doc.append(
					"permissions",
					{
						"role": role,
						"read": 1,
						"write": 1,
						"create": 1,
						"delete": 1,
						"print": 1,
						"email": 1,
						"export": 1,
						"report": 1,
					},
				)
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

	def ensure_salary_batch_link_field() -> None:
		if not frappe.db.exists("DocType", "Per Piece Salary"):
			return
		_delete_custom_field_if_exists("Per Piece Salary", "salary_batch")
		doc = frappe.get_doc("DocType", "Per Piece Salary")
		_upsert_field(
			doc,
			"salary_batch",
			{
				"label": "Salary Batch",
				"fieldtype": "Link",
				"options": "Per Piece Salary Batch",
			},
		)
		doc.save(ignore_permissions=True)

	def ensure_parent() -> None:
		name = "Per Piece Payment Entry"
		if frappe.db.exists("DocType", name):
			doc = frappe.get_doc("DocType", name)
		else:
			doc = frappe.new_doc("DocType")
			doc.name = name
			doc.track_changes = 1
			doc.autoname = "naming_series:"
			doc.naming_rule = 'By "Naming Series" field'
			doc.append(
				"fields",
				{
					"fieldname": "naming_series",
					"label": "Series",
					"fieldtype": "Data",
					"default": "PPE-PAY-.YYYY.-",
					"reqd": 1,
				},
			)
		_upsert_field(
			doc,
			"posting_date",
			{"label": "Posting Date", "fieldtype": "Date", "default": "Today", "reqd": 1},
		)
		_upsert_field(doc, "company", {"label": "Company", "fieldtype": "Link", "options": "Company"})
		_upsert_field(
			doc,
			"salary_entries_json",
			{"label": "Salary Entries JSON", "fieldtype": "Small Text", "read_only": 1},
		)
		_upsert_field(
			doc,
			"journal_entry",
			{"label": "Payment JV", "fieldtype": "Link", "options": "Journal Entry", "read_only": 1},
		)
		_upsert_field(
			doc,
			"total_payment_amount",
			{"label": "Total Payment Amount", "fieldtype": "Float", "precision": "2", "read_only": 1},
		)
		_upsert_field(doc, "remarks", {"label": "Remarks", "fieldtype": "Small Text"})
		_upsert_field(
			doc,
			"rows_section",
			{"label": "Rows", "fieldtype": "Section Break"},
		)
		_upsert_field(
			doc,
			"rows",
			{"label": "Rows", "fieldtype": "Table", "options": "Per Piece Payment Entry Row"},
		)

		for role in ("System Manager", "HR Manager", "HR User", "Stock User"):
			if not any((p.role == role and p.permlevel == 0) for p in (doc.permissions or [])):
				doc.append(
					"permissions",
					{
						"role": role,
						"read": 1,
						"write": 1,
						"create": 1,
						"delete": 1,
						"print": 1,
						"email": 1,
						"export": 1,
						"report": 1,
					},
				)
		doc.module = "Per Piece Payroll"
		doc.custom = 1
		doc.istable = 0
		doc.track_changes = 1
		doc.autoname = "naming_series:"
		doc.naming_rule = 'By "Naming Series" field'
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

	def ensure_child() -> None:
		name = "Per Piece Payment Entry Row"
		if frappe.db.exists("DocType", name):
			doc = frappe.get_doc("DocType", name)
		else:
			doc = frappe.new_doc("DocType")
			doc.name = name
		doc.module = "Per Piece Payroll"
		doc.custom = 1
		doc.istable = 1
		_upsert_field(
			doc,
			"salary_entry",
			{"label": "Salary Entry", "fieldtype": "Link", "options": "Per Piece Salary", "in_list_view": 1},
		)
		_upsert_field(
			doc,
			"employee",
			{"label": "Employee", "fieldtype": "Link", "options": "Employee", "in_list_view": 1},
		)
		_upsert_field(doc, "employee_name", {"label": "Employee Name", "fieldtype": "Data"})
		_upsert_field(doc, "salary_row", {"label": "Salary Row", "fieldtype": "Data"})
		_upsert_field(
			doc,
			"net_salary",
			{"label": "Net Salary", "fieldtype": "Float", "precision": "2", "in_list_view": 1},
		)
		_upsert_field(
			doc, "paid_amount_before", {"label": "Paid Before", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc, "unpaid_amount_before", {"label": "Unpaid Before", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc,
			"payment_amount",
			{"label": "Payment Amount", "fieldtype": "Float", "precision": "2", "in_list_view": 1},
		)
		_upsert_field(
			doc, "paid_amount_after", {"label": "Paid After", "fieldtype": "Float", "precision": "2"}
		)
		_upsert_field(
			doc, "unpaid_amount_after", {"label": "Unpaid After", "fieldtype": "Float", "precision": "2"}
		)
		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

	ensure_salary_summary_child()
	ensure_salary_parent_field()
	ensure_batch_child_entry()
	ensure_batch_child_summary()
	ensure_batch_parent()
	ensure_salary_batch_link_field()
	ensure_child()
	ensure_parent()
	frappe.db.commit()


def ensure_workspace() -> None:
	"""Create/update app workspace with key entry/reporting links (v15/v16)."""
	if not frappe.db.exists("DocType", "Workspace"):
		return

	module_name = "Per Piece Payroll"

	shortcuts = [
		{"type": "Page", "link_to": "per-piece-entry", "label": "Per Piece Entry"},
		{
			"type": "Page",
			"link_to": "per-piece-reporting",
			"label": "Per Piece Reporting",
		},
		{
			"type": "DocType",
			"link_to": "Per Piece Salary",
			"doc_view": "List",
			"label": "Per Piece Salary",
		},
		{
			"type": "DocType",
			"link_to": "Per Piece Payment Entry",
			"doc_view": "List",
			"label": "Per Piece Payment Entry",
		},
		{
			"type": "Report",
			"link_to": "Per Piece Salary Report",
			"label": "Per Piece Salary Report",
		},
		{
			"type": "Report",
			"link_to": "Per Piece Query Report Simple",
			"label": "Per Piece Query Report Simple",
		},
	]

	links = [
		{"type": "Card Break", "label": "Entry Workspace"},
		{"type": "Link", "label": "Per Piece Entry", "link_type": "Page", "link_to": "per-piece-entry"},
		{
			"type": "Link",
			"label": "Per Piece Salary",
			"link_type": "DocType",
			"link_to": "Per Piece Salary",
		},
		{
			"type": "Link",
			"label": "Per Piece Payment Entry",
			"link_type": "DocType",
			"link_to": "Per Piece Payment Entry",
		},
		{"type": "Card Break", "label": "Reporting Workspace"},
		{
			"type": "Link",
			"label": "Per Piece Reporting",
			"link_type": "Page",
			"link_to": "per-piece-reporting",
		},
		{
			"type": "Link",
			"label": "Per Piece Salary Report",
			"link_type": "Report",
			"link_to": "Per Piece Salary Report",
			"is_query_report": 1,
		},
		{
			"type": "Link",
			"label": "Per Piece Query Report Simple",
			"link_type": "Report",
			"link_to": "Per Piece Query Report Simple",
			"is_query_report": 1,
		},
	]

	content = [
		{"id": "header_shortcuts", "type": "header", "data": {"text": "Quick Access", "col": 12}},
		{"id": "shortcuts", "type": "shortcut", "data": {"shortcut_name": "Per Piece Entry", "col": 3}},
		{"id": "shortcuts_2", "type": "shortcut", "data": {"shortcut_name": "Per Piece Reporting", "col": 3}},
		{"id": "shortcuts_3", "type": "shortcut", "data": {"shortcut_name": "Per Piece Salary", "col": 3}},
		{
			"id": "shortcuts_4",
			"type": "shortcut",
			"data": {"shortcut_name": "Per Piece Salary Report", "col": 3},
		},
		{
			"id": "shortcuts_5",
			"type": "shortcut",
			"data": {"shortcut_name": "Per Piece Payment Entry", "col": 3},
		},
		{"id": "header_links", "type": "header", "data": {"text": "Links", "col": 12}},
		{"id": "links", "type": "links", "data": {"links_name": "Entry Workspace", "col": 6}},
		{
			"id": "links_2",
			"type": "links",
			"data": {"links_name": "Reporting Workspace", "col": 6},
		},
	]

	def upsert_workspace(
		workspace_name: str,
		title: str,
		icon: str,
		workspace_shortcuts: list[dict],
		workspace_links: list[dict],
		workspace_content: list[dict],
	) -> None:
		if frappe.db.exists("Workspace", workspace_name):
			doc = frappe.get_doc("Workspace", workspace_name)
		else:
			doc = frappe.new_doc("Workspace")
			doc.label = workspace_name

		doc.title = title
		doc.module = module_name
		doc.app = "per_piece_payroll"
		doc.icon = icon
		doc.public = 1
		doc.is_hidden = 0
		doc.type = "Workspace"
		doc.content = json.dumps(workspace_content, separators=(",", ":"))

		doc.set("shortcuts", [])
		for row in workspace_shortcuts:
			doc.append("shortcuts", row)

		doc.set("links", [])
		for row in workspace_links:
			doc.append("links", row)

		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

	upsert_workspace(
		workspace_name="Per Piece Payroll",
		title="Per Piece Payroll",
		icon="money-coins-1",
		workspace_shortcuts=shortcuts,
		workspace_links=links,
		workspace_content=content,
	)

	create_shortcuts = [
		{"type": "Page", "link_to": "per-piece-entry", "label": "Create Per Piece Salary"},
		{"type": "Page", "link_to": "per-piece-reporting", "label": "Per Piece Reporting"},
		{
			"type": "DocType",
			"link_to": "Per Piece Salary",
			"doc_view": "List",
			"label": "Per Piece Salary List",
		},
		{
			"type": "DocType",
			"link_to": "Per Piece Payment Entry",
			"doc_view": "List",
			"label": "Per Piece Payment Entry List",
		},
	]
	create_links = [
		{"type": "Card Break", "label": "Create Per Piece Salary"},
		{
			"type": "Link",
			"label": "Create Per Piece Salary",
			"link_type": "Page",
			"link_to": "per-piece-entry",
		},
		{
			"type": "Link",
			"label": "Per Piece Reporting",
			"link_type": "Page",
			"link_to": "per-piece-reporting",
		},
		{
			"type": "Link",
			"label": "Per Piece Salary List",
			"link_type": "DocType",
			"link_to": "Per Piece Salary",
		},
		{
			"type": "Link",
			"label": "Per Piece Payment Entry List",
			"link_type": "DocType",
			"link_to": "Per Piece Payment Entry",
		},
	]
	create_content = [
		{
			"id": "header_shortcuts",
			"type": "header",
			"data": {"text": "Create Per Piece Salary", "col": 12},
		},
		{
			"id": "shortcuts",
			"type": "shortcut",
			"data": {"shortcut_name": "Create Per Piece Salary", "col": 4},
		},
		{
			"id": "shortcuts_2",
			"type": "shortcut",
			"data": {"shortcut_name": "Per Piece Reporting", "col": 4},
		},
		{
			"id": "shortcuts_3",
			"type": "shortcut",
			"data": {"shortcut_name": "Per Piece Salary List", "col": 4},
		},
		{
			"id": "shortcuts_4",
			"type": "shortcut",
			"data": {"shortcut_name": "Per Piece Payment Entry List", "col": 4},
		},
		{
			"id": "header_links",
			"type": "header",
			"data": {"text": "Links", "col": 12},
		},
		{"id": "links", "type": "links", "data": {"links_name": "Create Per Piece Salary", "col": 12}},
	]

	upsert_workspace(
		workspace_name="Create Per Piece Salary",
		title="Create Per Piece Salary",
		icon="calculator",
		workspace_shortcuts=create_shortcuts,
		workspace_links=create_links,
		workspace_content=create_content,
	)

	frappe.clear_cache()
