from __future__ import annotations

import json
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
		ignore_permissions=True,
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

	dn_rows = frappe.get_all(
		"Delivery Note",
		filters={"name": dn_name, "docstatus": 1},
		fields=["name"],
		limit_page_length=1,
		ignore_permissions=True,
	)
	if not dn_rows:
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
			ignore_permissions=True,
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


@frappe.whitelist()
def get_delivery_note_process_rows(delivery_note: str) -> list[dict]:
	dn_name = (delivery_note or "").strip()
	if not dn_name:
		return []

	dn_items = get_delivery_note_items(dn_name)
	if not dn_items:
		return []

	# Expand each DN item to one row per process configured on Item.
	entry_rows: list[dict] = []
	for dn_item in dn_items:
		item_code = str(dn_item.get("item_code") or "").strip()
		if not item_code:
			continue
		item_qty = flt(dn_item.get("qty"))
		sales_order = str(dn_item.get("against_sales_order") or "").strip()
		process_rows = get_item_process_rows(item=item_code) or []
		if not process_rows:
			process_rows = [
				{
					"item": item_code,
					"employee": "",
					"employee_name": "",
					"process_type": "",
					"process_size": "No Size",
					"rate": 0,
				}
			]

		for process_row in process_rows:
			entry_rows.append(
				{
					"employee": str(process_row.get("employee") or "").strip(),
					"name1": str(process_row.get("employee_name") or "").strip(),
					"sales_order": sales_order,
					"product": item_code,
					"process_type": str(process_row.get("process_type") or "").strip(),
					"process_size": str(process_row.get("process_size") or "").strip() or "No Size",
					"qty": item_qty,
					"rate": flt(process_row.get("rate")),
				}
			)

	return entry_rows


@frappe.whitelist()
def get_salary_entry_financials(entry_names: str | list[str] | None = None) -> dict:
	def _to_names(raw) -> list[str]:
		if raw is None:
			return []
		if isinstance(raw, list):
			items = raw
		elif isinstance(raw, str):
			txt = raw.strip()
			if not txt:
				return []
			if txt.startswith("["):
				try:
					items = json.loads(txt)
				except Exception:
					items = txt.split(",")
			else:
				items = txt.split(",")
		else:
			items = [raw]
		out: list[str] = []
		seen: set[str] = set()
		for it in items:
			name = str(it or "").strip()
			if not name or name in seen:
				continue
			out.append(name)
			seen.add(name)
		return out[:500]

	entries = _to_names(entry_names)
	if not entries:
		return {"data": {}}

	per_piece_rows = frappe.get_all(
		"Per Piece",
		filters={"parent": ["in", entries], "parenttype": "Per Piece Salary"},
		fields=[
			"parent",
			"employee",
			"amount",
			"booked_amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_amount",
		],
		limit_page_length=200000,
		ignore_permissions=True,
	)

	by_entry: dict[str, dict] = {}
	for row in per_piece_rows:
		entry = str(row.get("parent") or "").strip()
		if not entry:
			continue
		emp = str(row.get("employee") or "").strip()
		amount = flt(row.get("amount"))
		booked = flt(row.get("booked_amount"))
		allowance = flt(row.get("allowance"))
		advance_deduction = flt(row.get("advance_deduction"))
		other_deduction = flt(row.get("other_deduction"))
		net_amount = flt(row.get("net_amount"))
		no_splits = (
			abs(allowance) <= 0.005 and abs(advance_deduction) <= 0.005 and abs(other_deduction) <= 0.005
		)
		# Legacy correction path: if no deductions/allowances were saved for this row,
		# financial values should match Data Entry base amount.
		if no_splits and amount > 0:
			if booked <= 0 or booked + 0.005 < amount:
				booked = amount
			if net_amount <= 0 or net_amount + 0.005 < amount:
				net_amount = amount
		if booked > 0 and net_amount <= 0:
			net_amount = booked
		if net_amount <= 0:
			net_amount = max(amount + allowance - advance_deduction - other_deduction, 0)
		if entry not in by_entry:
			by_entry[entry] = {
				"salary_amount": 0.0,
				"allowance_amount": 0.0,
				"advance_deduction_amount": 0.0,
				"other_deduction_amount": 0.0,
				"net_salary": 0.0,
				"by_employee": {},
			}
		target = by_entry[entry]
		target["salary_amount"] += amount
		target["allowance_amount"] += allowance
		target["advance_deduction_amount"] += advance_deduction
		target["other_deduction_amount"] += other_deduction
		target["net_salary"] += net_amount
		if emp:
			emp_row = target["by_employee"].setdefault(
				emp,
				{
					"salary_amount": 0.0,
					"allowance_amount": 0.0,
					"advance_deduction_amount": 0.0,
					"other_deduction_amount": 0.0,
					"net_amount": 0.0,
				},
			)
			emp_row["salary_amount"] += amount
			emp_row["allowance_amount"] += allowance
			emp_row["advance_deduction_amount"] += advance_deduction
			emp_row["other_deduction_amount"] += other_deduction
			emp_row["net_amount"] += net_amount

	for _entry, fin in by_entry.items():
		for _emp, emp_row in (fin.get("by_employee") or {}).items():
			salary_amount = flt(emp_row.get("salary_amount"))
			adv = flt(emp_row.get("advance_deduction_amount"))
			other = flt(emp_row.get("other_deduction_amount"))
			net = flt(emp_row.get("net_amount"))
			allow = flt(emp_row.get("allowance_amount"))
			if net <= 0:
				net = max(salary_amount + allow - adv - other, 0)
			emp_row["salary_amount"] = salary_amount
			emp_row["advance_deduction_amount"] = adv
			emp_row["other_deduction_amount"] = other
			emp_row["allowance_amount"] = allow
			emp_row["net_amount"] = net

	return {"data": by_entry}


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


def _parse_entry_names(value) -> list[str]:
	seen: set[str] = set()
	out: list[str] = []
	if value is None:
		return out
	if isinstance(value, list | tuple | set):
		parts = [str(v or "").strip() for v in value]
	else:
		text = str(value or "")
		text = text.replace(";;", ",")
		parts = [p.strip() for p in text.split(",")]
	for part in parts:
		if not part or part in seen:
			continue
		seen.add(part)
		out.append(part)
	return out


def _get_entries_for_jv(journal_entry: str, payment: bool = False) -> list[str]:
	jv = str(journal_entry or "").strip()
	if not jv:
		return []
	filters = {
		"parenttype": "Per Piece Salary",
		"parentfield": "perpiece",
	}
	if payment:
		matches = frappe.get_all(
			"Per Piece",
			filters={"payment_jv_no": jv, **filters},
			pluck="parent",
			limit_page_length=50000,
		)
		like_matches = frappe.get_all(
			"Per Piece",
			filters={"payment_refs": ["like", f"%{jv}%"], **filters},
			pluck="parent",
			limit_page_length=50000,
		)
		entries = list(matches or []) + list(like_matches or [])
	else:
		entries = frappe.get_all(
			"Per Piece",
			filters={"jv_entry_no": jv, **filters},
			pluck="parent",
			limit_page_length=50000,
		)
	seen: set[str] = set()
	out: list[str] = []
	for name in entries or []:
		key = str(name or "").strip()
		if not key or key in seen:
			continue
		seen.add(key)
		out.append(key)
	return out


def recalculate_per_piece_salary_totals(entry_names: list[str] | tuple[str] | str | None) -> None:
	names = _parse_entry_names(entry_names)
	if not names:
		return

	meta = frappe.get_meta("Per Piece Salary")
	has_total_booked = meta.has_field("total_booked_amount")
	has_total_paid = meta.has_field("total_paid_amount")
	has_total_unpaid = meta.has_field("total_unpaid_amount")

	parent_map: dict[str, dict] = {
		name: {
			"total_qty": 0.0,
			"total_amount": 0.0,
			"total_booked_amount": 0.0,
			"total_paid_amount": 0.0,
			"total_unpaid_amount": 0.0,
		}
		for name in names
	}

	rows = frappe.get_all(
		"Per Piece",
		filters={
			"parent": ["in", names],
			"parenttype": "Per Piece Salary",
			"parentfield": "perpiece",
		},
		fields=["parent", "qty", "amount", "booked_amount", "paid_amount", "unpaid_amount"],
		limit_page_length=50000,
	)
	for row in rows or []:
		parent = str((row or {}).get("parent") or "").strip()
		if not parent or parent not in parent_map:
			continue
		parent_map[parent]["total_qty"] += flt((row or {}).get("qty"))
		parent_map[parent]["total_amount"] += flt((row or {}).get("amount"))
		parent_map[parent]["total_booked_amount"] += flt((row or {}).get("booked_amount"))
		parent_map[parent]["total_paid_amount"] += flt((row or {}).get("paid_amount"))
		parent_map[parent]["total_unpaid_amount"] += flt((row or {}).get("unpaid_amount"))

	for name in names:
		if not frappe.db.exists("Per Piece Salary", name):
			continue
		t = parent_map.get(name) or {}
		update_data = {
			"total_qty": flt(t.get("total_qty")),
			"total_amount": flt(t.get("total_amount")),
		}
		if has_total_booked:
			update_data["total_booked_amount"] = flt(t.get("total_booked_amount"))
		if has_total_paid:
			update_data["total_paid_amount"] = flt(t.get("total_paid_amount"))
		if has_total_unpaid:
			update_data["total_unpaid_amount"] = flt(t.get("total_unpaid_amount"))
		frappe.db.set_value("Per Piece Salary", name, update_data, update_modified=False)


def recalculate_per_piece_child_financials(
	entry_names: list[str] | tuple[str] | str | None = None,
) -> dict:
	names = _parse_entry_names(entry_names)
	filters: dict[str, object] = {
		"parenttype": "Per Piece Salary",
		"parentfield": "perpiece",
	}
	if names:
		filters["parent"] = ["in", names]

	rows = frappe.get_all(
		"Per Piece",
		filters=filters,
		fields=[
			"name",
			"parent",
			"amount",
			"booked_amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_amount",
		],
		limit_page_length=200000,
	)
	updated = 0
	for row in rows or []:
		amount = flt((row or {}).get("amount"))
		booked = flt((row or {}).get("booked_amount"))
		allowance = flt((row or {}).get("allowance"))
		advance = flt((row or {}).get("advance_deduction"))
		other = flt((row or {}).get("other_deduction"))
		net = flt((row or {}).get("net_amount"))

		# Backfill legacy rows where financial splits were not persisted.
		if net <= 0:
			if booked > 0:
				net = booked
				if allowance <= 0 and advance <= 0 and other <= 0:
					allowance = max(net - amount, 0)
			else:
				net = max(amount + allowance - advance - other, 0)

		new_vals = {
			"allowance": round(allowance, 2),
			"advance_deduction": round(max(advance, 0), 2),
			"other_deduction": round(max(other, 0), 2),
			"net_amount": round(max(net, 0), 2),
		}
		cur_vals = {
			"allowance": round(flt((row or {}).get("allowance")), 2),
			"advance_deduction": round(flt((row or {}).get("advance_deduction")), 2),
			"other_deduction": round(flt((row or {}).get("other_deduction")), 2),
			"net_amount": round(flt((row or {}).get("net_amount")), 2),
		}
		if cur_vals != new_vals:
			frappe.db.set_value("Per Piece", row.get("name"), new_vals, update_modified=False)
			updated += 1

	if names:
		recalculate_per_piece_salary_totals(names)
	return {"ok": True, "rows_checked": len(rows or []), "rows_updated": updated}


def _normalize_entry_booked_amounts(
	entry_names: list[str] | tuple[str] | str | None = None,
) -> dict:
	"""Fix legacy rows where no deductions were saved but booked/net got reduced."""
	names = _parse_entry_names(entry_names)
	if not names:
		return {"ok": True, "rows_checked": 0, "rows_updated": 0}

	rows = frappe.get_all(
		"Per Piece",
		filters={
			"parent": ["in", names],
			"parenttype": "Per Piece Salary",
			"parentfield": "perpiece",
		},
		fields=[
			"name",
			"parent",
			"amount",
			"booked_amount",
			"paid_amount",
			"unpaid_amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_amount",
			"jv_status",
		],
		limit_page_length=200000,
	)

	updated = 0
	for row in rows or []:
		amount = flt((row or {}).get("amount"))
		booked = flt((row or {}).get("booked_amount"))
		paid = flt((row or {}).get("paid_amount"))
		unpaid = flt((row or {}).get("unpaid_amount"))
		allowance = flt((row or {}).get("allowance"))
		advance = flt((row or {}).get("advance_deduction"))
		other = flt((row or {}).get("other_deduction"))
		net = flt((row or {}).get("net_amount"))
		jv_status = str((row or {}).get("jv_status") or "").strip()

		no_split = abs(allowance) <= 0.005 and abs(advance) <= 0.005 and abs(other) <= 0.005
		needs_fix = (
			no_split
			and amount > 0
			and jv_status in ("Posted", "Accounted")
			and (booked + 0.005 < amount or net + 0.005 < amount)
		)
		if not needs_fix:
			continue

		new_booked = amount
		new_net = amount
		new_paid = max(min(paid, new_booked), 0.0)
		new_unpaid = max(new_booked - new_paid, 0.0)
		if new_unpaid <= 0.005:
			new_status = "Paid"
		elif new_paid > 0.005:
			new_status = "Partly Paid"
		else:
			new_status = "Unpaid"

		new_vals = {
			"booked_amount": round(new_booked, 2),
			"net_amount": round(new_net, 2),
			"paid_amount": round(new_paid, 2),
			"unpaid_amount": round(new_unpaid, 2),
			"payment_status": new_status,
		}
		cur_vals = {
			"booked_amount": round(booked, 2),
			"net_amount": round(net, 2),
			"paid_amount": round(paid, 2),
			"unpaid_amount": round(unpaid, 2),
			"payment_status": str((row or {}).get("payment_status") or ""),
		}
		if cur_vals != new_vals:
			frappe.db.set_value("Per Piece", row.get("name"), new_vals, update_modified=False)
			updated += 1

	if names and updated:
		recalculate_per_piece_salary_totals(names)
	return {"ok": True, "rows_checked": len(rows or []), "rows_updated": updated}


def _force_reset_entry_amounts(
	entry_names: list[str] | tuple[str] | str | None = None,
) -> dict:
	"""Force selected entries to use Data Entry base amount as Net/Booked amount."""
	names = _parse_entry_names(entry_names)
	if not names:
		return {"ok": True, "rows_checked": 0, "rows_updated": 0}

	rows = frappe.get_all(
		"Per Piece",
		filters={
			"parent": ["in", names],
			"parenttype": "Per Piece Salary",
			"parentfield": "perpiece",
		},
		fields=[
			"name",
			"amount",
			"booked_amount",
			"paid_amount",
			"unpaid_amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_amount",
			"payment_status",
		],
		limit_page_length=200000,
	)

	updated = 0
	for row in rows or []:
		amount = flt((row or {}).get("amount"))
		paid = max(flt((row or {}).get("paid_amount")), 0.0)
		new_booked = max(amount, 0.0)
		if paid > new_booked:
			paid = new_booked
		new_unpaid = max(new_booked - paid, 0.0)
		if new_unpaid <= 0.005:
			new_status = "Paid"
		elif paid > 0.005:
			new_status = "Partly Paid"
		else:
			new_status = "Unpaid"

		new_vals = {
			"allowance": 0.0,
			"advance_deduction": 0.0,
			"other_deduction": 0.0,
			"net_amount": round(new_booked, 2),
			"booked_amount": round(new_booked, 2),
			"paid_amount": round(paid, 2),
			"unpaid_amount": round(new_unpaid, 2),
			"payment_status": new_status,
		}
		cur_vals = {
			"allowance": round(flt((row or {}).get("allowance")), 2),
			"advance_deduction": round(flt((row or {}).get("advance_deduction")), 2),
			"other_deduction": round(flt((row or {}).get("other_deduction")), 2),
			"net_amount": round(flt((row or {}).get("net_amount")), 2),
			"booked_amount": round(flt((row or {}).get("booked_amount")), 2),
			"paid_amount": round(flt((row or {}).get("paid_amount")), 2),
			"unpaid_amount": round(flt((row or {}).get("unpaid_amount")), 2),
			"payment_status": str((row or {}).get("payment_status") or ""),
		}
		if cur_vals != new_vals:
			frappe.db.set_value("Per Piece", row.get("name"), new_vals, update_modified=False)
			updated += 1

	if names and updated:
		recalculate_per_piece_salary_totals(names)
	return {"ok": True, "rows_checked": len(rows or []), "rows_updated": updated}


@frappe.whitelist()
def get_per_piece_salary_report(**kwargs):
	names: list[str] = []
	names.extend(_parse_entry_names(kwargs.get("entry_nos")))
	names.extend(_parse_entry_names(kwargs.get("entry_no")))
	_normalize_entry_booked_amounts(names)
	return _run_legacy_api_script(GET_REPORT_SERVER_SCRIPT, kwargs)


@frappe.whitelist()
def create_per_piece_salary_entry(**kwargs):
	out = _run_legacy_api_script(CREATE_ENTRY_SERVER_SCRIPT, kwargs)
	names: list[str] = []
	if isinstance(out, dict):
		names.extend(_parse_entry_names(out.get("name")))
	names.extend(_parse_entry_names(kwargs.get("entry_name")))
	recalculate_per_piece_salary_totals(names)
	return out


@frappe.whitelist()
def create_per_piece_salary_jv(**kwargs):
	out = _run_legacy_api_script(CREATE_JV_SERVER_SCRIPT, kwargs)
	names: list[str] = []
	names.extend(_parse_entry_names(kwargs.get("entry_nos")))
	names.extend(_parse_entry_names(kwargs.get("entry_no")))
	recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	return out


@frappe.whitelist()
def cancel_per_piece_salary_jv(**kwargs):
	jv = kwargs.get("journal_entry")
	names = _get_entries_for_jv(jv, payment=False)
	out = _run_legacy_api_script(CANCEL_JV_SERVER_SCRIPT, kwargs)
	recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	return out


@frappe.whitelist()
def create_per_piece_salary_payment_jv(**kwargs):
	names: list[str] = []
	names.extend(_parse_entry_names(kwargs.get("entry_nos")))
	names.extend(_parse_entry_names(kwargs.get("entry_no")))
	_normalize_entry_booked_amounts(names)
	out = _run_legacy_api_script(CREATE_PAYMENT_JV_SERVER_SCRIPT, kwargs)
	recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	return out


@frappe.whitelist()
def recalculate_selected_entries(entry_nos=None, entry_no=None):
	names: list[str] = []
	names.extend(_parse_entry_names(entry_nos))
	names.extend(_parse_entry_names(entry_no))
	if not names:
		return {"ok": False, "message": "No entry selected."}

	# Keep force mode ON by default so older cached frontend builds still
	# run the correct correction behavior for selected entries.
	raw_force = frappe.form_dict.get("force_from_amount")
	force_mode = True if raw_force in (None, "", "null") else int(flt(raw_force or 0)) == 1
	forced = {"rows_checked": 0, "rows_updated": 0}
	if force_mode:
		forced = _force_reset_entry_amounts(names)
	norm = _normalize_entry_booked_amounts(names)
	fin = recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	return {
		"ok": True,
		"entries": names,
		"force_mode": force_mode,
		"forced_rows_checked": forced.get("rows_checked", 0),
		"forced_rows_updated": forced.get("rows_updated", 0),
		"normalized_rows_checked": norm.get("rows_checked", 0),
		"normalized_rows_updated": norm.get("rows_updated", 0),
		"financial_rows_checked": fin.get("rows_checked", 0),
		"financial_rows_updated": fin.get("rows_updated", 0),
	}


@frappe.whitelist()
def cancel_per_piece_salary_payment_jv(**kwargs):
	jv = kwargs.get("journal_entry")
	names = _get_entries_for_jv(jv, payment=True)
	out = _run_legacy_api_script(CANCEL_PAYMENT_JV_SERVER_SCRIPT, kwargs)
	recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	return out
