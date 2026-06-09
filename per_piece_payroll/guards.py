from __future__ import annotations

import frappe
from frappe.utils import flt


def protect_per_piece_salary_mutations(doc, method=None) -> None:
	"""Prevent updates to booked/submitted Per Piece Salary entries."""
	if getattr(doc, "doctype", None) != "Per Piece Salary":
		return
	_sync_parent_totals(doc)
	if doc.is_new():
		return

	old_doc = doc.get_doc_before_save()
	if not old_doc:
		old_doc = frappe.get_doc("Per Piece Salary", doc.name)

	if int(old_doc.docstatus or 0) == 1:
		if _has_material_change(old_doc, doc):
			frappe.throw(
				"Submitted Per Piece Salary entries are locked. "
				"Create a new entry for updated rate/qty instead of editing posted history."
			)
		return


def clear_per_piece_salary_batch_links(doc, method=None) -> None:
	"""Remove direct salary links before a batch is deleted.

	Frappe checks static Link fields after on_trash runs. Clearing the
	Per Piece Salary.salary_batch field here allows the batch delete to proceed.
	"""
	if getattr(doc, "doctype", None) != "Per Piece Salary Batch":
		return

	batch_name = _as_str(getattr(doc, "name", ""))
	if not batch_name or not frappe.db.has_column("Per Piece Salary", "salary_batch"):
		return

	linked_entries = frappe.get_all(
		"Per Piece Salary",
		filters={"salary_batch": batch_name},
		pluck="name",
		limit_page_length=5000,
	)
	for entry_name in linked_entries or []:
		frappe.db.set_value(
			"Per Piece Salary",
			entry_name,
			"salary_batch",
			"",
			update_modified=False,
		)


def sync_per_piece_salary_batch_links(doc, method=None) -> None:
	"""Keep Per Piece Salary.salary_batch aligned with batch child rows.

	This runs on batch save so removed rows are unlinked and retained rows stay linked.
	"""
	if getattr(doc, "doctype", None) != "Per Piece Salary Batch":
		return
	if getattr(frappe.flags, "in_per_piece_salary_batch_sync", False):
		return

	batch_name = _as_str(getattr(doc, "name", ""))
	if not batch_name or not frappe.db.has_column("Per Piece Salary", "salary_batch"):
		return

	current_entries = {
		_as_str(getattr(row, "salary_entry", "") if not isinstance(row, dict) else row.get("salary_entry"))
		for row in (doc.get("entries") or [])
	}
	current_entries.discard("")

	linked_entries = set(
		frappe.get_all(
			"Per Piece Salary",
			filters={"salary_batch": batch_name},
			pluck="name",
			limit_page_length=5000,
		)
		or []
	)

	for entry_name in sorted(linked_entries - current_entries):
		frappe.db.set_value(
			"Per Piece Salary",
			entry_name,
			"salary_batch",
			"",
			update_modified=False,
		)

	for entry_name in sorted(current_entries):
		frappe.db.set_value(
			"Per Piece Salary",
			entry_name,
			"salary_batch",
			batch_name,
			update_modified=False,
		)

	from per_piece_payroll.api import rebuild_salary_batch

	frappe.flags.in_per_piece_salary_batch_sync = True
	try:
		rebuild_salary_batch(batch_name)
	finally:
		frappe.flags.in_per_piece_salary_batch_sync = False
def _has_material_change(old_doc, new_doc) -> bool:
	tracked_parent_fields = (
		"from_date",
		"to_date",
		"po_number",
		"item_group",
		"item",
		"employee",
		"load_by_item",
	)
	for fieldname in tracked_parent_fields:
		if _as_str(old_doc.get(fieldname)) != _as_str(new_doc.get(fieldname)):
			return True

	return _row_signature(old_doc) != _row_signature(new_doc)


def _row_signature(doc) -> list[tuple]:
	rows: list[tuple] = []
	for row in doc.get("perpiece") or []:
		rows.append(
			(
				_as_str(row.get("name")),
				_as_str(row.get("employee")),
				_as_str(row.get("name1")),
				_as_str(row.get("product")),
				_as_str(row.get("process_type")),
				_as_str(row.get("process_size")),
				_as_str(row.get("sales_order")),
				round(flt(row.get("qty")), 6),
				round(flt(row.get("rate")), 6),
				round(flt(row.get("amount")), 6),
			)
		)
	rows.sort()
	return rows


def _as_str(value) -> str:
	return str(value or "").strip()


def _sync_parent_totals(doc) -> None:
	rows = doc.get("perpiece") or []
	total_qty = 0.0
	total_amount = 0.0
	total_booked = 0.0
	total_paid = 0.0
	total_unpaid = 0.0
	for row in rows:
		total_qty += flt(row.get("qty"))
		total_amount += flt(row.get("amount"))
		booked = flt(row.get("booked_amount"))
		paid = flt(row.get("paid_amount"))
		unpaid = flt(row.get("unpaid_amount"))
		total_booked += booked
		total_paid += paid
		total_unpaid += unpaid
	doc.total_qty = total_qty
	doc.total_amount = total_amount
	if hasattr(doc, "total_booked_amount"):
		doc.total_booked_amount = total_booked
	if hasattr(doc, "total_paid_amount"):
		doc.total_paid_amount = total_paid
	if hasattr(doc, "total_unpaid_amount"):
		doc.total_unpaid_amount = total_unpaid
