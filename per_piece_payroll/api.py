from __future__ import annotations

from pathlib import Path

import frappe
from frappe.utils import flt

from per_piece_payroll.per_piece_setup import (
	CANCEL_JV_SERVER_SCRIPT,
	CANCEL_PAYMENT_JV_SERVER_SCRIPT,
	CREATE_ENTRY_SERVER_SCRIPT,
	CREATE_JV_SERVER_SCRIPT,
	CREATE_PAYMENT_JV_SERVER_SCRIPT,
	GET_REPORT_SERVER_SCRIPT,
	apply,
)


@frappe.whitelist()
def apply_per_piece_payroll_setup() -> list[str]:
	return apply()


@frappe.whitelist()
def get_item_process_rows(item_group: str | None = None, item: str | None = None) -> list[dict]:
	filters: dict[str, object] = {"disabled": 0}
	if item:
		filters["name"] = item
	elif item_group:
		filters["item_group"] = item_group

	items = frappe.get_all(
		"Item",
		filters=filters,
		fields=[
			"name",
			"item_name",
			"item_group",
		],
		order_by="name asc",
		limit_page_length=5000,
	)

	employee_ids: set[str] = set()
	for item_row in items:
		item_doc = frappe.get_doc("Item", item_row["name"])
		process_rows = item_doc.get("custom_prd_process_and_sizes") or []
		for row in process_rows:
			employee = (row.get("employee") or "").strip()
			if employee:
				employee_ids.add(employee)

	employee_name_map: dict[str, str] = {}
	if employee_ids:
		employee_rows = frappe.get_all(
			"Employee",
			filters={"name": ["in", list(employee_ids)]},
			fields=["name", "employee_name"],
			limit_page_length=5000,
		)
		for employee_row in employee_rows:
			employee_name_map[str(employee_row.get("name") or "")] = str(
				employee_row.get("employee_name") or ""
			).strip()

	output: list[dict] = []
	for item_row in items:
		item_doc = frappe.get_doc("Item", item_row["name"])
		process_rows = item_doc.get("custom_prd_process_and_sizes") or []

		if process_rows:
			for row in process_rows:
				employee = (row.get("employee") or "").strip()
				output.append(
					{
						"item": item_row["name"],
						"item_name": item_row.get("item_name") or item_row["name"],
						"item_group": item_row.get("item_group") or "",
						"employee": employee,
						"employee_name": employee_name_map.get(employee, ""),
						"process_type": row.get("process_type") or "",
						"process_size": row.get("process_size") or "No Size",
						"rate": flt(row.get("rate")),
						"source": "item_process_table",
					}
				)
			continue

		output.append(
			{
				"item": item_row["name"],
				"item_name": item_row.get("item_name") or item_row["name"],
				"item_group": item_row.get("item_group") or "",
				"employee": "",
				"employee_name": "",
				"process_type": "",
				"process_size": "No Size",
				"rate": flt(0),
				"source": "item",
			}
		)

	return output


@frappe.whitelist()
def force_sync_per_piece_status() -> dict:
	def _round2(v) -> float:
		return round(float(v or 0), 2)

	def _to_float(v) -> float:
		try:
			return float(v or 0)
		except Exception:
			return 0.0

	rows = frappe.get_all(
		"Per Piece",
		filters={"docstatus": ["<", 2]},
		fields=[
			"name",
			"amount",
			"jv_status",
			"jv_entry_no",
			"booked_amount",
			"paid_amount",
			"unpaid_amount",
			"payment_status",
			"payment_jv_no",
			"payment_refs",
			"payment_line_remark",
		],
		limit_page_length=200000,
	)
	if not rows:
		return {"ok": True, "rows_checked": 0, "rows_updated": 0}

	jv_names = {
		str(r.get("jv_entry_no") or "").strip() for r in rows if str(r.get("jv_entry_no") or "").strip()
	}
	pay_jv_names = {
		str(r.get("payment_jv_no") or "").strip() for r in rows if str(r.get("payment_jv_no") or "").strip()
	}
	all_jv_names = sorted(jv_names | pay_jv_names)

	jv_status_map: dict[str, int] = {}
	if all_jv_names:
		for je in frappe.get_all(
			"Journal Entry",
			filters={"name": ["in", all_jv_names]},
			fields=["name", "docstatus"],
			limit_page_length=50000,
		):
			jv_status_map[str(je.get("name") or "")] = int(je.get("docstatus") or 0)

	updated = 0
	for row in rows:
		name = row.get("name")
		amount = max(_round2(row.get("amount")), 0.0)
		jv_no = str(row.get("jv_entry_no") or "").strip()
		jv_state = jv_status_map.get(jv_no, 0) if jv_no else 0
		is_booked = bool(jv_no and jv_state == 1)

		new_jv_no = jv_no if is_booked else ""
		new_jv_status = "Posted" if is_booked else "Pending"
		new_booked = amount if is_booked else 0.0

		paid = max(_round2(row.get("paid_amount")), 0.0)
		pay_jv_no = str(row.get("payment_jv_no") or "").strip()
		pay_jv_state = jv_status_map.get(pay_jv_no, 0) if pay_jv_no else 0
		if pay_jv_no and pay_jv_state != 1:
			pay_jv_no = ""

		if not is_booked:
			paid = 0.0
			unpaid = 0.0
			pay_jv_no = ""
			pay_status = "Unpaid"
			pay_refs = ""
			pay_remark = ""
		else:
			if paid > new_booked:
				paid = new_booked
			unpaid = max(_round2(new_booked - paid), 0.0)
			if unpaid <= 0.005:
				pay_status = "Paid"
			elif paid > 0.005:
				pay_status = "Partly Paid"
			else:
				pay_status = "Unpaid"
			pay_refs = row.get("payment_refs") or ""
			pay_remark = row.get("payment_line_remark") or ""

		changed = False
		current = {
			"jv_entry_no": str(row.get("jv_entry_no") or "").strip(),
			"jv_status": str(row.get("jv_status") or "").strip() or "Pending",
			"booked_amount": _round2(row.get("booked_amount")),
			"paid_amount": _round2(row.get("paid_amount")),
			"unpaid_amount": _round2(row.get("unpaid_amount")),
			"payment_status": str(row.get("payment_status") or "").strip() or "Unpaid",
			"payment_jv_no": str(row.get("payment_jv_no") or "").strip(),
			"payment_refs": row.get("payment_refs") or "",
			"payment_line_remark": row.get("payment_line_remark") or "",
		}
		target = {
			"jv_entry_no": new_jv_no,
			"jv_status": new_jv_status,
			"booked_amount": _round2(new_booked),
			"paid_amount": _round2(paid),
			"unpaid_amount": _round2(unpaid),
			"payment_status": pay_status,
			"payment_jv_no": pay_jv_no,
			"payment_refs": pay_refs,
			"payment_line_remark": pay_remark,
		}
		for k in target:
			if str(current[k]) != str(target[k]):
				changed = True
				break
		if changed:
			for k, v in target.items():
				frappe.db.set_value("Per Piece", name, k, v, update_modified=False)
			updated += 1

	# Keep parent totals aligned with child sums.
	frappe.db.sql(
		"""
		UPDATE `tabPer Piece Salary` pps
		LEFT JOIN (
			SELECT parent, ROUND(SUM(IFNULL(qty, 0)), 2) AS total_qty, ROUND(SUM(IFNULL(amount, 0)), 2) AS total_amount
			FROM `tabPer Piece`
			WHERE parenttype='Per Piece Salary' AND parentfield='perpiece'
			GROUP BY parent
		) agg ON agg.parent = pps.name
		SET
			pps.total_qty = IFNULL(agg.total_qty, 0),
			pps.total_amount = IFNULL(agg.total_amount, 0)
		WHERE pps.docstatus < 2
		"""
	)
	frappe.db.commit()
	return {"ok": True, "rows_checked": len(rows), "rows_updated": updated}


@frappe.whitelist()
def get_per_piece_report_page_payload() -> dict:
	html_path = Path(
		frappe.get_app_path(
			"per_piece_payroll",
			"public",
			"html",
			"per_piece_report_main_section.html",
		)
	)
	main_section_html = ""
	if html_path.exists():
		main_section_html = html_path.read_text(encoding="utf-8")
	else:
		# Fallback only if file is unexpectedly missing
		main_section_html = frappe.db.get_value("Web Page", "per-piece-report", "main_section_html") or ""
	if not main_section_html:
		frappe.throw("Web Page 'per-piece-report' is missing main_section_html.")
	return {"html": main_section_html}


@frappe.whitelist()
def search_delivery_notes(txt: str | None = None, limit: int | str | None = None) -> list[dict]:
	if not frappe.has_permission("Delivery Note", ptype="read"):
		frappe.throw("Insufficient Permission for Delivery Note", frappe.PermissionError)

	search_txt = (txt or "").strip()
	try:
		limit_n = int(limit or 20)
	except Exception:
		limit_n = 20
	limit_n = max(1, min(limit_n, 100))

	filters: list[list] = [["docstatus", "=", 1]]
	if search_txt:
		filters.append(["name", "like", f"%{search_txt}%"])

	rows = frappe.get_all(
		"Delivery Note",
		filters=filters,
		fields=["name", "posting_date", "customer"],
		order_by="posting_date desc, name desc",
		limit_page_length=limit_n,
	)
	out: list[dict] = []
	for row in rows:
		name = str(row.get("name") or "").strip()
		if not name:
			continue
		posting_date = str(row.get("posting_date") or "").strip()
		customer = str(row.get("customer") or "").strip()
		label_parts = [name]
		if posting_date:
			label_parts.append(posting_date)
		if customer:
			label_parts.append(customer)
		out.append(
			{
				"name": name,
				"posting_date": posting_date,
				"customer": customer,
				"label": " | ".join(label_parts),
			}
		)
	return out


@frappe.whitelist()
def get_delivery_note_items(delivery_note: str) -> list[dict]:
	dn_name = (delivery_note or "").strip()
	if not dn_name:
		return []

	if not frappe.has_permission("Delivery Note", ptype="read"):
		frappe.throw("Insufficient Permission for Delivery Note", frappe.PermissionError)

	if not frappe.db.exists("Delivery Note", dn_name):
		return []

	docstatus = int(frappe.db.get_value("Delivery Note", dn_name, "docstatus") or 0)
	if docstatus != 1:
		return []

	rows = frappe.get_all(
		"Delivery Note Item",
		filters={"parent": dn_name, "parenttype": "Delivery Note"},
		fields=["item_code", "item_name", "qty", "against_sales_order"],
		order_by="idx asc",
		limit_page_length=5000,
		ignore_permissions=True,
	)

	item_codes = sorted(
		{str(r.get("item_code") or "").strip() for r in rows if str(r.get("item_code") or "").strip()}
	)
	item_group_map: dict[str, str] = {}
	if item_codes:
		for item_row in frappe.get_all(
			"Item",
			filters={"name": ["in", item_codes]},
			fields=["name", "item_group"],
			limit_page_length=5000,
		):
			item_group_map[str(item_row.get("name") or "").strip()] = str(
				item_row.get("item_group") or ""
			).strip()

	out: list[dict] = []
	for row in rows:
		item_code = str(row.get("item_code") or "").strip()
		if not item_code:
			continue
		out.append(
			{
				"delivery_note": dn_name,
				"item_code": item_code,
				"item_name": str(row.get("item_name") or "").strip() or item_code,
				"item_group": item_group_map.get(item_code, ""),
				"qty": flt(row.get("qty")),
				"against_sales_order": str(row.get("against_sales_order") or "").strip(),
			}
		)
	return out


def _run_legacy_api_script(script_text: str, kwargs: dict | None = None):
	kwargs = kwargs or {}
	old_form_dict = getattr(frappe.local, "form_dict", frappe._dict())
	old_message = frappe.response.get("message")
	try:
		frappe.local.form_dict = frappe._dict(kwargs)
		frappe.response["message"] = None
		exec_scope = {"frappe": frappe, "__builtins__": __builtins__}
		exec(compile(script_text, "<legacy_per_piece_api>", "exec"), exec_scope, exec_scope)
		return frappe.response.get("message")
	finally:
		frappe.local.form_dict = old_form_dict
		if old_message is None:
			frappe.response.pop("message", None)
		else:
			frappe.response["message"] = old_message


@frappe.whitelist()
def get_per_piece_salary_report(**kwargs):
	return _run_legacy_api_script(GET_REPORT_SERVER_SCRIPT, kwargs)


@frappe.whitelist()
def create_per_piece_salary_entry(**kwargs):
	return _run_legacy_api_script(CREATE_ENTRY_SERVER_SCRIPT, kwargs)


@frappe.whitelist()
def create_per_piece_salary_jv(**kwargs):
	return _run_legacy_api_script(CREATE_JV_SERVER_SCRIPT, kwargs)


@frappe.whitelist()
def cancel_per_piece_salary_jv(**kwargs):
	return _run_legacy_api_script(CANCEL_JV_SERVER_SCRIPT, kwargs)


@frappe.whitelist()
def create_per_piece_salary_payment_jv(**kwargs):
	return _run_legacy_api_script(CREATE_PAYMENT_JV_SERVER_SCRIPT, kwargs)


@frappe.whitelist()
def cancel_per_piece_salary_payment_jv(**kwargs):
	return _run_legacy_api_script(CANCEL_PAYMENT_JV_SERVER_SCRIPT, kwargs)
