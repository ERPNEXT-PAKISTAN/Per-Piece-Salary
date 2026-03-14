from __future__ import annotations

import frappe
from frappe.utils import flt

from per_piece_payroll.per_piece_setup import apply


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
