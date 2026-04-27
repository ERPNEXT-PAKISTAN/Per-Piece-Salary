from __future__ import annotations

import json

import frappe

from per_piece_payroll.per_piece_setup import apply


def after_install() -> None:
	apply()
	ensure_workspace()


def after_migrate() -> None:
	apply()
	ensure_workspace()


def ensure_workspace() -> None:
	"""Create/update app workspace with key entry/reporting links (v15/v16)."""
	if not frappe.db.exists("DocType", "Workspace"):
		return

	workspace_name = "Per Piece Payroll"
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
		{"id": "header_links", "type": "header", "data": {"text": "Links", "col": 12}},
		{"id": "links", "type": "links", "data": {"links_name": "Entry Workspace", "col": 6}},
		{
			"id": "links_2",
			"type": "links",
			"data": {"links_name": "Reporting Workspace", "col": 6},
		},
	]

	if frappe.db.exists("Workspace", workspace_name):
		doc = frappe.get_doc("Workspace", workspace_name)
	else:
		doc = frappe.new_doc("Workspace")
		doc.label = workspace_name

	doc.title = workspace_name
	doc.module = module_name
	doc.app = "per_piece_payroll"
	doc.icon = "money-coins-1"
	doc.public = 1
	doc.is_hidden = 0
	doc.type = "Workspace"
	doc.content = json.dumps(content, separators=(",", ":"))

	doc.set("shortcuts", [])
	for row in shortcuts:
		doc.append("shortcuts", row)

	doc.set("links", [])
	for row in links:
		doc.append("links", row)

	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)

	frappe.clear_cache()
