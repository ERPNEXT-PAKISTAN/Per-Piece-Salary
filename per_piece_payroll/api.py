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


def rebuild_salary_summary_rows(entry_names: list[str] | None = None) -> dict:
	entries = [str(x or "").strip() for x in (entry_names or []) if str(x or "").strip()]
	if not entries or not frappe.db.exists("DocType", "Per Piece Salary Summary Row"):
		return {"ok": True, "entries": 0}

	rows = frappe.get_all(
		"Per Piece",
		filters={"parent": ["in", entries], "parenttype": "Per Piece Salary", "parentfield": "perpiece"},
		fields=[
			"parent",
			"employee",
			"name1",
			"amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_amount",
			"booked_amount",
			"paid_amount",
			"unpaid_amount",
			"payment_status",
		],
		order_by="parent asc, idx asc",
		limit_page_length=200000,
	)
	grouped: dict[str, dict[str, dict]] = {}
	for r in rows or []:
		entry = str((r or {}).get("parent") or "").strip()
		emp = str((r or {}).get("employee") or "").strip()
		if not entry or not emp:
			continue
		grouped.setdefault(entry, {})
		if emp not in grouped[entry]:
			grouped[entry][emp] = {
				"employee": emp,
				"employee_name": str((r or {}).get("name1") or "").strip(),
				"salary_amount": 0.0,
				"allowance": 0.0,
				"advance_deduction": 0.0,
				"other_deduction": 0.0,
				"net_salary": 0.0,
				"booked_amount": 0.0,
				"paid_amount": 0.0,
				"unpaid_amount": 0.0,
			}
		item = grouped[entry][emp]
		amount = flt((r or {}).get("amount"))
		allow = flt((r or {}).get("allowance"))
		adv = flt((r or {}).get("advance_deduction"))
		oth = flt((r or {}).get("other_deduction"))
		net = flt((r or {}).get("net_amount"))
		booked = flt((r or {}).get("booked_amount"))
		paid = max(flt((r or {}).get("paid_amount")), 0.0)
		unpaid = max(flt((r or {}).get("unpaid_amount")), 0.0)
		if net <= 0:
			net = max(amount + allow - adv - oth, 0.0)
		if booked <= 0:
			booked = net
		item["salary_amount"] += amount
		item["allowance"] += allow
		item["advance_deduction"] += adv
		item["other_deduction"] += oth
		item["net_salary"] += net
		item["booked_amount"] += booked
		item["paid_amount"] += paid
		item["unpaid_amount"] += unpaid

	for entry in entries:
		frappe.db.delete(
			"Per Piece Salary Summary Row",
			{"parent": entry, "parenttype": "Per Piece Salary", "parentfield": "salary_summary_rows"},
		)
		entry_rows = list((grouped.get(entry) or {}).values())
		entry_rows.sort(
			key=lambda x: (str(x.get("employee_name") or "").lower(), str(x.get("employee") or ""))
		)
		for idx, row in enumerate(entry_rows, 1):
			paid_amount = round(max(flt(row.get("paid_amount")), 0.0), 2)
			unpaid_amount = round(max(flt(row.get("unpaid_amount")), 0.0), 2)
			status = (
				"Paid" if unpaid_amount <= 0.005 else ("Partly Paid" if paid_amount > 0.005 else "Unpaid")
			)
			doc = frappe.get_doc(
				{
					"doctype": "Per Piece Salary Summary Row",
					"parent": entry,
					"parenttype": "Per Piece Salary",
					"parentfield": "salary_summary_rows",
					"idx": idx,
					"salary_entry": entry,
					"employee": row.get("employee"),
					"employee_name": row.get("employee_name"),
					"salary_amount": round(flt(row.get("salary_amount")), 2),
					"allowance": round(flt(row.get("allowance")), 2),
					"advance_deduction": round(flt(row.get("advance_deduction")), 2),
					"other_deduction": round(flt(row.get("other_deduction")), 2),
					"net_salary": round(flt(row.get("net_salary")), 2),
					"booked_amount": round(flt(row.get("booked_amount")), 2),
					"paid_amount": paid_amount,
					"unpaid_amount": unpaid_amount,
					"payment_status": status,
				}
			)
			doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "entries": len(entries)}


def rebuild_salary_batch(batch_name: str) -> dict:
	batch = str(batch_name or "").strip()
	if not batch or not frappe.db.exists("Per Piece Salary Batch", batch):
		return {"ok": False, "batch": batch}
	if not frappe.db.exists("DocType", "Per Piece Salary Batch Summary Row"):
		return {"ok": True, "batch": batch, "entries": 0}
	batch_doc = frappe.get_doc("Per Piece Salary Batch", batch)

	entry_rows = frappe.get_all(
		"Per Piece Salary Batch Entry",
		filters={"parent": batch, "parenttype": "Per Piece Salary Batch", "parentfield": "entries"},
		fields=["salary_entry"],
		order_by="idx asc",
		limit_page_length=5000,
	)
	entry_names = [
		str((r or {}).get("salary_entry") or "").strip()
		for r in entry_rows
		if str((r or {}).get("salary_entry") or "").strip()
	]
	if not entry_names:
		batch_doc.set("summary_rows", [])
		batch_doc.total_salary_amount = 0
		batch_doc.total_allowance = 0
		batch_doc.total_advance_deduction = 0
		batch_doc.total_other_deduction = 0
		batch_doc.total_net_salary = 0
		batch_doc.total_paid_amount = 0
		batch_doc.total_unpaid_amount = 0
		batch_doc.save(ignore_permissions=True)
		return {"ok": True, "batch": batch, "entries": 0}

	emp_map: dict[str, dict] = {}
	entry_totals: dict[str, dict] = {
		e: {"salary": 0.0, "allow": 0.0, "adv": 0.0, "other": 0.0, "net": 0.0, "paid": 0.0, "unpaid": 0.0}
		for e in entry_names
	}

	summary_rows = frappe.get_all(
		"Per Piece Salary Summary Row",
		filters={
			"parent": ["in", entry_names],
			"parenttype": "Per Piece Salary",
			"parentfield": "salary_summary_rows",
		},
		fields=[
			"parent",
			"employee",
			"employee_name",
			"salary_amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_salary",
			"paid_amount",
			"unpaid_amount",
		],
		limit_page_length=200000,
		order_by="parent asc, idx asc",
	)
	if not summary_rows:
		# Fallback for older data where salary_summary_rows were not yet generated.
		perpiece_rows = frappe.get_all(
			"Per Piece",
			filters={
				"parent": ["in", entry_names],
				"parenttype": "Per Piece Salary",
				"parentfield": "perpiece",
			},
			fields=[
				"parent",
				"employee",
				"name1",
				"amount",
				"allowance",
				"advance_deduction",
				"other_deduction",
				"net_amount",
				"booked_amount",
				"paid_amount",
				"unpaid_amount",
			],
			limit_page_length=200000,
			order_by="parent asc, idx asc",
		)
		for r in perpiece_rows or []:
			summary_rows.append(
				{
					"parent": r.get("parent"),
					"employee": r.get("employee"),
					"employee_name": r.get("name1"),
					"salary_amount": r.get("amount"),
					"allowance": r.get("allowance"),
					"advance_deduction": r.get("advance_deduction"),
					"other_deduction": r.get("other_deduction"),
					"net_salary": r.get("net_amount") or r.get("booked_amount") or r.get("amount"),
					"paid_amount": r.get("paid_amount"),
					"unpaid_amount": r.get("unpaid_amount"),
				}
			)
	for r in summary_rows or []:
		entry = str((r or {}).get("parent") or "").strip()
		emp = str((r or {}).get("employee") or "").strip()
		if not emp:
			continue
		if emp not in emp_map:
			emp_map[emp] = {
				"employee": emp,
				"employee_name": str((r or {}).get("employee_name") or "").strip(),
				"salary_amount": 0.0,
				"allowance": 0.0,
				"advance_deduction": 0.0,
				"other_deduction": 0.0,
				"net_salary": 0.0,
				"paid_amount": 0.0,
				"unpaid_amount": 0.0,
			}
		item = emp_map[emp]
		item["salary_amount"] += flt((r or {}).get("salary_amount"))
		item["allowance"] += flt((r or {}).get("allowance"))
		item["advance_deduction"] += flt((r or {}).get("advance_deduction"))
		item["other_deduction"] += flt((r or {}).get("other_deduction"))
		item["net_salary"] += flt((r or {}).get("net_salary"))
		item["paid_amount"] += flt((r or {}).get("paid_amount"))
		item["unpaid_amount"] += flt((r or {}).get("unpaid_amount"))
		if entry in entry_totals:
			entry_totals[entry]["salary"] += flt((r or {}).get("salary_amount"))
			entry_totals[entry]["allow"] += flt((r or {}).get("allowance"))
			entry_totals[entry]["adv"] += flt((r or {}).get("advance_deduction"))
			entry_totals[entry]["other"] += flt((r or {}).get("other_deduction"))
			entry_totals[entry]["net"] += flt((r or {}).get("net_salary"))
			entry_totals[entry]["paid"] += flt((r or {}).get("paid_amount"))
			entry_totals[entry]["unpaid"] += flt((r or {}).get("unpaid_amount"))

	batch_doc.set("summary_rows", [])
	for idx, emp in enumerate(sorted(emp_map.keys()), 1):
		v = emp_map[emp]
		batch_doc.append(
			"summary_rows",
			{
				"idx": idx,
				"employee": v["employee"],
				"employee_name": v["employee_name"],
				"salary_amount": round(v["salary_amount"], 2),
				"allowance": round(v["allowance"], 2),
				"advance_deduction": round(v["advance_deduction"], 2),
				"other_deduction": round(v["other_deduction"], 2),
				"net_salary": round(v["net_salary"], 2),
				"paid_amount": round(v["paid_amount"], 2),
				"unpaid_amount": round(v["unpaid_amount"], 2),
			},
		)

	# update batch entry row totals on same parent doc instance to avoid stale overwrite
	for entry_row in batch_doc.get("entries") or []:
		e = str(
			(
				entry_row.get("salary_entry")
				if isinstance(entry_row, dict)
				else getattr(entry_row, "salary_entry", "")
			)
			or ""
		).strip()
		t = entry_totals.get(e) or {}
		if isinstance(entry_row, dict):
			entry_row["total_salary"] = round(flt(t.get("salary")), 2)
			entry_row["allowance"] = round(flt(t.get("allow")), 2)
			entry_row["advance_deduction"] = round(flt(t.get("adv")), 2)
			entry_row["other_deduction"] = round(flt(t.get("other")), 2)
			entry_row["net_salary"] = round(flt(t.get("net")), 2)
			entry_row["paid_amount"] = round(flt(t.get("paid")), 2)
			entry_row["unpaid_amount"] = round(flt(t.get("unpaid")), 2)
		else:
			entry_row.total_salary = round(flt(t.get("salary")), 2)
			entry_row.allowance = round(flt(t.get("allow")), 2)
			entry_row.advance_deduction = round(flt(t.get("adv")), 2)
			entry_row.other_deduction = round(flt(t.get("other")), 2)
			entry_row.net_salary = round(flt(t.get("net")), 2)
			entry_row.paid_amount = round(flt(t.get("paid")), 2)
			entry_row.unpaid_amount = round(flt(t.get("unpaid")), 2)

	tot_salary = sum(flt(v.get("salary_amount")) for v in emp_map.values())
	tot_allow = sum(flt(v.get("allowance")) for v in emp_map.values())
	tot_adv = sum(flt(v.get("advance_deduction")) for v in emp_map.values())
	tot_other = sum(flt(v.get("other_deduction")) for v in emp_map.values())
	tot_net = sum(flt(v.get("net_salary")) for v in emp_map.values())
	tot_paid = sum(flt(v.get("paid_amount")) for v in emp_map.values())
	tot_unpaid = sum(flt(v.get("unpaid_amount")) for v in emp_map.values())
	batch_doc.total_salary_amount = round(tot_salary, 2)
	batch_doc.total_allowance = round(tot_allow, 2)
	batch_doc.total_advance_deduction = round(tot_adv, 2)
	batch_doc.total_other_deduction = round(tot_other, 2)
	batch_doc.total_net_salary = round(tot_net, 2)
	batch_doc.total_paid_amount = round(tot_paid, 2)
	batch_doc.total_unpaid_amount = round(tot_unpaid, 2)
	batch_doc.save(ignore_permissions=True)
	return {"ok": True, "batch": batch, "entries": len(entry_names)}


def rebuild_batches_for_entries(entry_names: list[str] | None = None) -> dict:
	names = [str(x or "").strip() for x in (entry_names or []) if str(x or "").strip()]
	if not names or not frappe.db.has_column("Per Piece Salary", "salary_batch"):
		return {"ok": True, "batches": 0}
	batches = frappe.get_all(
		"Per Piece Salary", filters={"name": ["in", names]}, fields=["salary_batch"], limit_page_length=5000
	)
	batch_names = sorted(
		{
			str((r or {}).get("salary_batch") or "").strip()
			for r in (batches or [])
			if str((r or {}).get("salary_batch") or "").strip()
		}
	)
	for b in batch_names:
		rebuild_salary_batch(b)
	return {"ok": True, "batches": len(batch_names)}


@frappe.whitelist()
def create_salary_batch(
	entry_nos=None, batch_name: str | None = None, company: str | None = None, remarks: str | None = None
):
	entries = _parse_entry_names(entry_nos)
	if not entries:
		frappe.throw("Please provide at least one Per Piece Salary entry.")
	if not frappe.db.exists("DocType", "Per Piece Salary Batch"):
		frappe.throw("Per Piece Salary Batch doctype is not available. Run migrate first.")
	doc = frappe.new_doc("Per Piece Salary Batch")
	if company:
		doc.company = str(company or "").strip()
	if remarks:
		doc.remarks = str(remarks or "").strip()
	doc.posting_date = frappe.utils.nowdate()
	doc.insert(ignore_permissions=True)
	if batch_name:
		doc.db_set("name", str(batch_name).strip(), update_modified=False)
		doc.reload()

	doc.set("entries", [])
	for idx, entry in enumerate(entries, 1):
		if not frappe.db.exists("Per Piece Salary", entry):
			continue
		pps = (
			frappe.db.get_value(
				"Per Piece Salary", entry, ["po_number", "delivery_note", "company"], as_dict=True
			)
			or {}
		)
		doc.append(
			"entries",
			{
				"idx": idx,
				"salary_entry": entry,
				"po_number": str(pps.get("po_number") or ""),
				"delivery_note": str(pps.get("delivery_note") or ""),
			},
		)
		if frappe.db.has_column("Per Piece Salary", "salary_batch"):
			frappe.db.set_value("Per Piece Salary", entry, "salary_batch", doc.name, update_modified=False)
		if not doc.company and pps.get("company"):
			doc.company = str(pps.get("company") or "")

	doc.save(ignore_permissions=True)
	rebuild_salary_summary_rows(entries)
	rebuild_salary_batch(doc.name)
	return {"ok": True, "batch": doc.name, "entries": entries}


@frappe.whitelist()
def get_salary_batch_entries(batch_name: str):
	batch = str(batch_name or "").strip()
	if not batch:
		return {"ok": False, "message": "Batch name is required."}
	if not frappe.db.exists("Per Piece Salary Batch", batch):
		return {"ok": False, "message": f"Batch not found: {batch}"}
	rows = frappe.get_all(
		"Per Piece Salary Batch Entry",
		filters={"parent": batch, "parenttype": "Per Piece Salary Batch", "parentfield": "entries"},
		fields=[
			"salary_entry",
			"po_number",
			"delivery_note",
			"total_salary",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_salary",
			"paid_amount",
			"unpaid_amount",
		],
		order_by="idx asc",
		limit_page_length=5000,
	)
	doc = (
		frappe.db.get_value(
			"Per Piece Salary Batch",
			batch,
			[
				"name",
				"company",
				"posting_date",
				"remarks",
				"total_salary_amount",
				"total_allowance",
				"total_advance_deduction",
				"total_other_deduction",
				"total_net_salary",
				"total_paid_amount",
				"total_unpaid_amount",
			],
			as_dict=True,
		)
		or {}
	)
	return {"ok": True, "batch": doc, "entries": rows}


def _create_payment_entry_snapshot(
	entry_names: list[str] | None,
	before_paid: dict[str, float] | None,
	jv_name: str | None = None,
	remarks: str | None = None,
) -> str:
	entry_list = [str(x or "").strip() for x in (entry_names or []) if str(x or "").strip()]
	if not entry_list or not frappe.db.exists("DocType", "Per Piece Payment Entry"):
		return ""

	before_map = before_paid or {}
	after_rows = frappe.get_all(
		"Per Piece",
		filters={"parent": ["in", entry_list], "parenttype": "Per Piece Salary", "parentfield": "perpiece"},
		fields=[
			"name",
			"parent",
			"employee",
			"name1",
			"amount",
			"net_amount",
			"booked_amount",
			"paid_amount",
			"unpaid_amount",
		],
		order_by="parent asc, idx asc",
		limit_page_length=200000,
	)
	if not after_rows:
		return ""

	parent_docs = {
		d.name: d
		for d in frappe.get_all(
			"Per Piece Salary",
			filters={"name": ["in", entry_list]},
			fields=["name", "company"],
			limit_page_length=5000,
		)
	}
	doc = frappe.new_doc("Per Piece Payment Entry")
	doc.posting_date = frappe.utils.nowdate()
	doc.salary_entries_json = json.dumps(entry_list, separators=(",", ":"))
	doc.journal_entry = str(jv_name or "").strip()
	doc.remarks = str(remarks or "").strip()

	total_payment = 0.0
	for row in after_rows:
		row_name = str((row or {}).get("name") or "").strip()
		paid_before = max(flt(before_map.get(row_name, 0.0)), 0.0)
		paid_after = max(flt((row or {}).get("paid_amount")), 0.0)
		payment_amount = round(max(paid_after - paid_before, 0.0), 2)
		if payment_amount <= 0.005:
			continue
		parent_name = str((row or {}).get("parent") or "").strip()
		if not doc.company:
			doc.company = str((parent_docs.get(parent_name) or {}).get("company") or "").strip()
		net_amount = flt((row or {}).get("net_amount"))
		booked_amount = flt((row or {}).get("booked_amount"))
		base_amount = flt((row or {}).get("amount"))
		net_salary = net_amount if net_amount > 0 else (booked_amount if booked_amount > 0 else base_amount)
		doc.append(
			"rows",
			{
				"salary_entry": parent_name,
				"employee": str((row or {}).get("employee") or "").strip(),
				"employee_name": str((row or {}).get("name1") or "").strip(),
				"salary_row": row_name,
				"net_salary": round(max(net_salary, 0.0), 2),
				"paid_amount_before": round(paid_before, 2),
				"unpaid_amount_before": round(
					max(flt((row or {}).get("unpaid_amount")) + payment_amount, 0.0), 2
				),
				"payment_amount": payment_amount,
				"paid_amount_after": round(paid_after, 2),
				"unpaid_amount_after": round(max(flt((row or {}).get("unpaid_amount")), 0.0), 2),
			},
		)
		total_payment += payment_amount

	if not doc.rows:
		return ""

	doc.total_payment_amount = round(total_payment, 2)
	doc.insert(ignore_permissions=True)
	return str(doc.name)


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


def _collect_entry_names_from_context(
	kwargs: dict | None = None,
	out: dict | None = None,
	*,
	jv_payment: bool = False,
) -> list[str]:
	kwargs = kwargs or {}
	out = out or {}
	names: list[str] = []
	names.extend(_parse_entry_names(kwargs.get("entry_nos")))
	names.extend(_parse_entry_names(kwargs.get("entry_no")))
	names.extend(_parse_entry_names(kwargs.get("entry_name")))
	names.extend(_parse_entry_names(out.get("entry_nos")))
	names.extend(_parse_entry_names(out.get("entry_no")))
	names.extend(_parse_entry_names(out.get("name")))

	# Fallback path: derive entry names from posted/cancelled JV when payload has no entry list.
	if not names:
		jv = (
			kwargs.get("journal_entry")
			or kwargs.get("jv_entry_no")
			or out.get("jv_entry_no")
			or out.get("journal_entry")
		)
		if jv:
			names.extend(_get_entries_for_jv(jv, payment=jv_payment))

	seen: set[str] = set()
	result: list[str] = []
	for n in names:
		key = str(n or "").strip()
		if not key or key in seen:
			continue
		seen.add(key)
		result.append(key)
	return result


def _extract_jv_name_from_context(kwargs: dict | None = None, out: dict | None = None) -> str:
	kwargs = kwargs or {}
	out = out or {}
	candidates = [
		out.get("journal_entry"),
		out.get("jv_entry_no"),
		out.get("payment_jv_no"),
		out.get("name"),
		kwargs.get("journal_entry"),
		kwargs.get("jv_entry_no"),
	]
	for v in candidates:
		name = str(v or "").strip()
		if name and name.startswith("ACC-JV-"):
			return name
	return ""


def _append_payment_ref_text(existing: str, jv_name: str, amount: float) -> str:
	jv = str(jv_name or "").strip()
	if not jv:
		return existing or ""
	amt = round(flt(amount), 2)
	if amt <= 0:
		return existing or ""
	existing_txt = str(existing or "").strip()
	ref = f"{jv}::{amt}"
	if not existing_txt:
		return ref
	return existing_txt + ";;" + ref


def _force_link_payment_jv_to_paid_rows(
	entry_names: list[str] | tuple[str] | str | None,
	before_paid_map: dict[str, float] | None,
	jv_name: str,
) -> int:
	names = _parse_entry_names(entry_names)
	if not names:
		return 0
	jv = str(jv_name or "").strip()
	if not jv:
		return 0
	before_paid_map = before_paid_map or {}
	rows = frappe.get_all(
		"Per Piece",
		filters={
			"parent": ["in", names],
			"parenttype": "Per Piece Salary",
			"parentfield": "perpiece",
		},
		fields=["name", "paid_amount", "payment_jv_no", "payment_refs"],
		limit_page_length=200000,
	)
	updated = 0
	for row in rows or []:
		row_name = str((row or {}).get("name") or "").strip()
		if not row_name:
			continue
		before_paid = flt(before_paid_map.get(row_name))
		after_paid = flt((row or {}).get("paid_amount"))
		delta = round(after_paid - before_paid, 2)
		if delta <= 0:
			continue
		cur_jv = str((row or {}).get("payment_jv_no") or "").strip()
		cur_refs = str((row or {}).get("payment_refs") or "")
		new_refs = _append_payment_ref_text(cur_refs, jv, delta)
		update_data = {}
		if cur_jv != jv:
			update_data["payment_jv_no"] = jv
		if new_refs != cur_refs:
			update_data["payment_refs"] = new_refs
		if update_data:
			frappe.db.set_value("Per Piece", row_name, update_data, update_modified=False)
			updated += 1
	return updated


def recalculate_per_piece_salary_totals(entry_names: list[str] | tuple[str] | str | None) -> None:
	names = _parse_entry_names(entry_names)
	if not names:
		return

	def has_col(fieldname: str) -> bool:
		try:
			return bool(frappe.db.has_column("Per Piece Salary", fieldname))
		except Exception:
			return False

	has_total_booked = has_col("total_booked_amount")
	has_total_paid = has_col("total_paid_amount")
	has_total_unpaid = has_col("total_unpaid_amount")
	has_total_allowance_amount = has_col("total_allowance_amount")
	has_total_allowance = has_col("total_allowance")
	has_total_advance_amount = has_col("total_advance_deduction_amount")
	has_total_advance = has_col("total_advance_deduction")
	has_total_other_amount = has_col("total_other_deduction_amount")
	has_total_other = has_col("total_other_deduction")
	has_total_net_salary = has_col("total_net_salary")
	has_total_net_amount = has_col("total_net_amount")

	parent_map: dict[str, dict] = {
		name: {
			"total_qty": 0.0,
			"total_amount": 0.0,
			"total_booked_amount": 0.0,
			"total_paid_amount": 0.0,
			"total_unpaid_amount": 0.0,
			"total_allowance_amount": 0.0,
			"total_allowance": 0.0,
			"total_advance_deduction_amount": 0.0,
			"total_advance_deduction": 0.0,
			"total_other_deduction_amount": 0.0,
			"total_other_deduction": 0.0,
			"total_net_salary": 0.0,
			"total_net_amount": 0.0,
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
		fields=[
			"parent",
			"qty",
			"amount",
			"booked_amount",
			"paid_amount",
			"unpaid_amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_amount",
		],
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
		parent_map[parent]["total_allowance_amount"] += flt((row or {}).get("allowance"))
		parent_map[parent]["total_allowance"] += flt((row or {}).get("allowance"))
		parent_map[parent]["total_advance_deduction_amount"] += flt((row or {}).get("advance_deduction"))
		parent_map[parent]["total_advance_deduction"] += flt((row or {}).get("advance_deduction"))
		parent_map[parent]["total_other_deduction_amount"] += flt((row or {}).get("other_deduction"))
		parent_map[parent]["total_other_deduction"] += flt((row or {}).get("other_deduction"))
		parent_map[parent]["total_net_salary"] += flt((row or {}).get("net_amount"))
		parent_map[parent]["total_net_amount"] += flt((row or {}).get("net_amount"))

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
		if has_total_allowance_amount:
			update_data["total_allowance_amount"] = flt(t.get("total_allowance_amount"))
		if has_total_allowance:
			update_data["total_allowance"] = flt(t.get("total_allowance"))
		if has_total_advance_amount:
			update_data["total_advance_deduction_amount"] = flt(t.get("total_advance_deduction_amount"))
		if has_total_advance:
			update_data["total_advance_deduction"] = flt(t.get("total_advance_deduction"))
		if has_total_other_amount:
			update_data["total_other_deduction_amount"] = flt(t.get("total_other_deduction_amount"))
		if has_total_other:
			update_data["total_other_deduction"] = flt(t.get("total_other_deduction"))
		if has_total_net_salary:
			update_data["total_net_salary"] = flt(t.get("total_net_salary"))
		if has_total_net_amount:
			update_data["total_net_amount"] = flt(t.get("total_net_amount"))
		frappe.db.set_value("Per Piece Salary", name, update_data, update_modified=False)


@frappe.whitelist()
def backfill_parent_totals_from_child(entry_nos=None, entry_no=None):
	names: list[str] = []
	names.extend(_parse_entry_names(entry_nos))
	names.extend(_parse_entry_names(entry_no))
	if not names:
		names = frappe.get_all("Per Piece Salary", pluck="name", limit_page_length=500000) or []
	recalculate_per_piece_salary_totals(names)
	return {"ok": True, "entries": len(names)}


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
			"employee",
			"amount",
			"booked_amount",
			"allowance",
			"advance_deduction",
			"other_deduction",
			"net_amount",
			"paid_amount",
			"unpaid_amount",
			"payment_status",
			"jv_entry_no",
			"jv_status",
		],
		limit_page_length=200000,
	)

	# Rebuild employee financial splits from posted salary JV remarks when available.
	rows_by_entry_emp: dict[tuple[str, str], list[dict]] = {}
	jv_names: set[str] = set()
	for r in rows or []:
		entry = str((r or {}).get("parent") or "").strip()
		emp = str((r or {}).get("employee") or "").strip()
		if entry and emp:
			rows_by_entry_emp.setdefault((entry, emp), []).append(r)
		jv = str((r or {}).get("jv_entry_no") or "").strip()
		jv_status = str((r or {}).get("jv_status") or "").strip()
		if jv and jv_status in ("Posted", "Accounted"):
			jv_names.add(jv)

	jv_emp_fin: dict[str, dict[str, dict[str, float]]] = {}
	if jv_names:
		for je in frappe.get_all(
			"Journal Entry",
			filters={"name": ["in", list(jv_names)], "docstatus": 1},
			fields=["name"],
			limit_page_length=5000,
		):
			jv_name = str((je or {}).get("name") or "").strip()
			if not jv_name:
				continue
			jv_emp_fin[jv_name] = {}
			for acc in frappe.get_all(
				"Journal Entry Account",
				filters={"parent": jv_name},
				fields=["party", "user_remark", "credit_in_account_currency", "credit"],
				limit_page_length=50000,
			):
				credit = flt(acc.get("credit_in_account_currency")) or flt(acc.get("credit"))
				if credit <= 0:
					continue
				party = str(acc.get("party") or "").strip()
				remark = str(acc.get("user_remark") or "").strip()
				emp = ""
				kind = ""
				if remark.startswith("Advance Recovery - "):
					kind = "advance_deduction"
					emp = remark.replace("Advance Recovery - ", "", 1).strip()
				elif remark.startswith("Salary Deduction - "):
					kind = "other_deduction"
					emp = remark.replace("Salary Deduction - ", "", 1).strip()
				elif remark.startswith("Net Salary - "):
					kind = "net_amount"
					emp = remark.replace("Net Salary - ", "", 1).split("|", 1)[0].strip()
				elif party and remark.startswith("Advance Recovery - "):
					kind = "advance_deduction"
					emp = party
				elif party and remark.startswith("Salary Deduction - "):
					kind = "other_deduction"
					emp = party
				elif party and remark.startswith("Net Salary - "):
					kind = "net_amount"
					emp = party
				if not emp or not kind:
					continue
				fin = jv_emp_fin[jv_name].setdefault(
					emp,
					{"advance_deduction": 0.0, "other_deduction": 0.0, "net_amount": 0.0},
				)
				fin[kind] = flt(fin.get(kind)) + flt(credit)

	# Apply JV-based employee totals to rows (proportional by base amount).
	jv_rebuilt = 0
	for (_entry, emp), emp_rows in rows_by_entry_emp.items():
		if not emp_rows:
			continue
		jv_name = str((emp_rows[0] or {}).get("jv_entry_no") or "").strip()
		if not jv_name or jv_name not in jv_emp_fin:
			continue
		fin = (jv_emp_fin.get(jv_name) or {}).get(emp) or {}
		emp_amount = sum(flt((x or {}).get("amount")) for x in emp_rows)
		adv_total = max(flt(fin.get("advance_deduction")), 0.0)
		other_total = max(flt(fin.get("other_deduction")), 0.0)
		net_total = max(flt(fin.get("net_amount")), 0.0)
		if net_total <= 0:
			net_total = max(emp_amount - adv_total - other_total, 0.0)
		allow_total = max(net_total - emp_amount + adv_total + other_total, 0.0)
		den = emp_amount if emp_amount > 0 else float(len(emp_rows))
		for row in emp_rows:
			amount = flt((row or {}).get("amount"))
			share = (amount / den) if den > 0 else 0.0
			if emp_amount <= 0:
				share = 1.0 / float(len(emp_rows) or 1)
			adv = round(adv_total * share, 2)
			other = round(other_total * share, 2)
			allow = round(allow_total * share, 2)
			net = round(max(amount + allow - adv - other, 0.0), 2)
			paid = max(flt((row or {}).get("paid_amount")), 0.0)
			if paid > net:
				paid = net
			unpaid = round(max(net - paid, 0.0), 2)
			status = "Unpaid" if net <= 0 or paid <= 0 else ("Paid" if unpaid <= 0 else "Partly Paid")
			new_vals = {
				"allowance": allow,
				"advance_deduction": adv,
				"other_deduction": other,
				"net_amount": net,
				"booked_amount": net,
				"unpaid_amount": unpaid,
				"payment_status": status,
			}
			cur_vals = {
				"allowance": round(flt((row or {}).get("allowance")), 2),
				"advance_deduction": round(flt((row or {}).get("advance_deduction")), 2),
				"other_deduction": round(flt((row or {}).get("other_deduction")), 2),
				"net_amount": round(flt((row or {}).get("net_amount")), 2),
				"booked_amount": round(flt((row or {}).get("booked_amount")), 2),
				"unpaid_amount": round(flt((row or {}).get("unpaid_amount")), 2),
				"payment_status": str((row or {}).get("payment_status") or ""),
			}
			if cur_vals != new_vals:
				frappe.db.set_value("Per Piece", row.get("name"), new_vals, update_modified=False)
				jv_rebuilt += 1

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
	return {
		"ok": True,
		"rows_checked": len(rows or []),
		"rows_updated": updated,
		"rows_rebuilt_from_jv": jv_rebuilt,
	}


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
def get_payment_entry_basis(entry_no: str):
	entry = str(entry_no or "").strip()
	if not entry:
		return {"entry_no": "", "rows": [], "totals": {}}

	summary_rows = []
	if frappe.db.exists("DocType", "Per Piece Salary Summary Row"):
		summary_rows = frappe.get_all(
			"Per Piece Salary Summary Row",
			filters={"parent": entry, "parenttype": "Per Piece Salary", "parentfield": "salary_summary_rows"},
			fields=[
				"employee",
				"employee_name",
				"salary_amount",
				"allowance",
				"advance_deduction",
				"other_deduction",
				"net_salary",
				"booked_amount",
				"paid_amount",
				"unpaid_amount",
				"payment_status",
			],
			order_by="idx asc",
			limit_page_length=5000,
		)
	rows = []
	if summary_rows:
		for r in summary_rows:
			rows.append(
				{
					"employee": r.get("employee"),
					"name1": r.get("employee_name"),
					"amount": r.get("salary_amount"),
					"net_amount": r.get("net_salary"),
					"booked_amount": r.get("booked_amount"),
					"paid_amount": r.get("paid_amount"),
					"unpaid_amount": r.get("unpaid_amount"),
					"payment_status": r.get("payment_status"),
				}
			)
	else:
		rows = frappe.get_all(
			"Per Piece",
			filters={
				"parent": entry,
				"parenttype": "Per Piece Salary",
				"parentfield": "perpiece",
			},
			fields=[
				"employee",
				"name1",
				"amount",
				"booked_amount",
				"net_amount",
				"paid_amount",
				"unpaid_amount",
				"payment_status",
			],
			order_by="idx asc",
			limit_page_length=200000,
		)

	by_emp: dict[str, dict[str, float | str]] = {}
	for r in rows or []:
		emp = str((r or {}).get("employee") or "").strip()
		if not emp:
			continue
		if emp not in by_emp:
			by_emp[emp] = {
				"employee": emp,
				"name1": str((r or {}).get("name1") or "").strip(),
				"booked_amount": 0.0,
				"paid_amount": 0.0,
				"unpaid_amount": 0.0,
				"payment_status": "Unpaid",
			}
		base = by_emp[emp]
		net = flt((r or {}).get("net_amount"))
		booked = flt((r or {}).get("booked_amount"))
		amount = flt((r or {}).get("amount"))
		row_booked = net if net > 0 else (booked if booked > 0 else amount)
		row_paid = max(flt((r or {}).get("paid_amount")), 0.0)
		if row_paid > row_booked:
			row_paid = row_booked
		row_unpaid = flt((r or {}).get("unpaid_amount"))
		if row_unpaid < 0 or row_unpaid > row_booked:
			row_unpaid = max(row_booked - row_paid, 0.0)
		base["booked_amount"] = flt(base.get("booked_amount")) + row_booked
		base["paid_amount"] = flt(base.get("paid_amount")) + row_paid
		base["unpaid_amount"] = flt(base.get("unpaid_amount")) + row_unpaid

	out_rows = []
	total_booked = 0.0
	total_paid = 0.0
	total_unpaid = 0.0
	for emp in sorted(by_emp.keys()):
		r = by_emp[emp]
		booked = round(flt(r.get("booked_amount")), 2)
		paid = round(min(flt(r.get("paid_amount")), booked), 2)
		unpaid = round(max(flt(r.get("unpaid_amount")), 0.0), 2)
		if unpaid <= 0.005 and booked > 0:
			status = "Paid"
		elif paid > 0.005:
			status = "Partly Paid"
		else:
			status = "Unpaid"
		# Hide fully-paid rows from Payment Entry load basis.
		if unpaid > 0.005 or status != "Paid":
			out_rows.append(
				{
					"employee": emp,
					"name1": str(r.get("name1") or ""),
					"booked_amount": booked,
					"paid_amount": paid,
					"unpaid_amount": unpaid,
					"payment_status": status,
					"payment_amount": round(unpaid, 2),
				}
			)
		total_booked += booked
		total_paid += paid
		total_unpaid += unpaid

	return {
		"entry_no": entry,
		"rows": out_rows,
		"totals": {
			"booked": round(total_booked, 2),
			"paid": round(total_paid, 2),
			"unpaid": round(total_unpaid, 2),
		},
	}


@frappe.whitelist()
def create_per_piece_salary_entry(**kwargs):
	out = _run_legacy_api_script(CREATE_ENTRY_SERVER_SCRIPT, kwargs)
	names = _collect_entry_names_from_context(kwargs, out, jv_payment=False)
	recalculate_per_piece_salary_totals(names)
	rebuild_salary_summary_rows(names)
	rebuild_batches_for_entries(names)
	return out


@frappe.whitelist()
def create_per_piece_salary_jv(**kwargs):
	out = _run_legacy_api_script(CREATE_JV_SERVER_SCRIPT, kwargs)
	names = _collect_entry_names_from_context(kwargs, out, jv_payment=False)
	recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	rebuild_salary_summary_rows(names)
	rebuild_batches_for_entries(names)
	return out


@frappe.whitelist()
def cancel_per_piece_salary_jv(**kwargs):
	jv = kwargs.get("journal_entry")
	names = _get_entries_for_jv(jv, payment=False)
	out = _run_legacy_api_script(CANCEL_JV_SERVER_SCRIPT, kwargs)
	recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	rebuild_salary_summary_rows(names)
	rebuild_batches_for_entries(names)
	return out


@frappe.whitelist()
def create_per_piece_salary_payment_jv(**kwargs):
	names = _collect_entry_names_from_context(kwargs, None, jv_payment=True)
	_normalize_entry_booked_amounts(names)
	before_rows = frappe.get_all(
		"Per Piece",
		filters={
			"parent": ["in", names or [""]],
			"parenttype": "Per Piece Salary",
			"parentfield": "perpiece",
		},
		fields=["name", "paid_amount"],
		limit_page_length=200000,
	)
	before_paid = {
		str((r or {}).get("name") or "").strip(): flt((r or {}).get("paid_amount"))
		for r in (before_rows or [])
	}
	out = _run_legacy_api_script(CREATE_PAYMENT_JV_SERVER_SCRIPT, kwargs)
	names = _collect_entry_names_from_context(kwargs, out, jv_payment=True)
	jv_name = _extract_jv_name_from_context(kwargs, out)
	_force_link_payment_jv_to_paid_rows(names, before_paid, jv_name)
	try:
		remarks = kwargs.get("payment_remark") or kwargs.get("remark") or ""
		_create_payment_entry_snapshot(names, before_paid, jv_name=jv_name, remarks=str(remarks or ""))
	except Exception:
		# Never block existing posting flow on snapshot write errors.
		frappe.log_error(frappe.get_traceback(), "Per Piece Payment Entry Snapshot Failed")
	recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	rebuild_salary_summary_rows(names)
	rebuild_batches_for_entries(names)
	return out


@frappe.whitelist()
def get_per_piece_payment_entries(entry_no: str | None = None, limit: int = 50):
	limit_n = max(1, min(int(limit or 50), 500))
	filters: dict[str, object] = {}
	if entry_no:
		filters["salary_entries_json"] = ["like", f"%{str(entry_no).strip()}%"]
	docs = frappe.get_all(
		"Per Piece Payment Entry",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"company",
			"journal_entry",
			"total_payment_amount",
			"salary_entries_json",
		],
		order_by="posting_date desc, creation desc",
		limit_page_length=limit_n,
	)
	for d in docs:
		try:
			entries = json.loads(str(d.get("salary_entries_json") or "[]"))
		except Exception:
			entries = []
		if not isinstance(entries, list):
			entries = []
		entries = [str(x or "").strip() for x in entries if str(x or "").strip()]
		d["salary_entries"] = entries
		d["rows"] = frappe.db.count("Per Piece Payment Entry Row", {"parent": d.get("name")})
	return docs


@frappe.whitelist()
def get_per_piece_payment_entry_detail(payment_entry: str):
	name = str(payment_entry or "").strip()
	if not name:
		return {"name": "", "rows": [], "totals": {}}
	if not frappe.db.exists("Per Piece Payment Entry", name):
		return {"name": name, "rows": [], "totals": {}}
	doc = frappe.get_doc("Per Piece Payment Entry", name)
	out_rows = []
	t_booked = 0.0
	t_paid = 0.0
	t_unpaid = 0.0
	t_pay = 0.0
	for row in doc.get("rows") or []:
		net_salary = round(max(flt(row.get("net_salary")), 0.0), 2)
		paid_before = round(max(flt(row.get("paid_amount_before")), 0.0), 2)
		unpaid_before = round(max(flt(row.get("unpaid_amount_before")), 0.0), 2)
		payment_amount = round(max(flt(row.get("payment_amount")), 0.0), 2)
		paid_after = round(max(flt(row.get("paid_amount_after")), 0.0), 2)
		unpaid_after = round(max(flt(row.get("unpaid_amount_after")), 0.0), 2)
		status = "Paid" if unpaid_after <= 0.005 else ("Partly Paid" if paid_after > 0.005 else "Unpaid")
		out_rows.append(
			{
				"salary_entry": str(row.get("salary_entry") or "").strip(),
				"employee": str(row.get("employee") or "").strip(),
				"name1": str(row.get("employee_name") or "").strip(),
				"net_salary": net_salary,
				"paid_amount_before": paid_before,
				"unpaid_amount_before": unpaid_before,
				"payment_amount": payment_amount,
				"paid_amount_after": paid_after,
				"unpaid_amount_after": unpaid_after,
				"status": status,
			}
		)
		t_booked += net_salary
		t_paid += paid_after
		t_unpaid += unpaid_after
		t_pay += payment_amount
	return {
		"name": name,
		"journal_entry": str(doc.get("journal_entry") or "").strip(),
		"posting_date": str(doc.get("posting_date") or "").strip(),
		"company": str(doc.get("company") or "").strip(),
		"rows": out_rows,
		"totals": {
			"booked": round(t_booked, 2),
			"paid": round(t_paid, 2),
			"unpaid": round(t_unpaid, 2),
			"payment": round(t_pay, 2),
		},
	}


@frappe.whitelist()
def recalculate_selected_entries(entry_nos=None, entry_no=None):
	names: list[str] = []
	names.extend(_parse_entry_names(entry_nos))
	names.extend(_parse_entry_names(entry_no))
	if not names:
		return {"ok": False, "message": "No entry selected."}

	# Force reset is destructive for allowance/deduction splits.
	# Default must stay OFF unless explicitly requested.
	raw_force = frappe.form_dict.get("force_from_amount")
	force_mode = False if raw_force in (None, "", "null") else int(flt(raw_force or 0)) == 1
	forced = {"rows_checked": 0, "rows_updated": 0}
	if force_mode:
		forced = _force_reset_entry_amounts(names)
	norm = _normalize_entry_booked_amounts(names)
	fin = recalculate_per_piece_child_financials(names)
	recalculate_per_piece_salary_totals(names)
	rebuild_salary_summary_rows(names)
	rebuild_batches_for_entries(names)
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
	rebuild_salary_summary_rows(names)
	rebuild_batches_for_entries(names)
	return out
