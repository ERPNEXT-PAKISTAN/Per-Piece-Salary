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
