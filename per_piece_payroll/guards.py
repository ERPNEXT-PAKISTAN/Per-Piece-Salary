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

	if _has_booked_or_paid_rows(old_doc) and _has_material_change(old_doc, doc):
		frappe.throw(
			"This Per Piece Salary contains booked/paid rows and cannot be changed. "
			"Create a new entry for new rates/qty."
		)


def _has_booked_or_paid_rows(doc) -> bool:
	for row in doc.get("perpiece") or []:
		if _is_locked_row(row):
			return True
	return False


def _is_locked_row(row) -> bool:
	if (row.get("jv_entry_no") or "").strip():
		return True
	if flt(row.get("booked_amount")) > 0:
		return True
	if flt(row.get("paid_amount")) > 0:
		return True
	if (row.get("payment_refs") or "").strip():
		return True
	return False


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
