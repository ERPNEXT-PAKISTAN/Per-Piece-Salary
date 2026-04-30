import json
from pathlib import Path

import frappe

GET_REPORT_SERVER_SCRIPT = """# Server Script: API
# Script Type: API
# API Method: get_per_piece_salary_report

def normalize_param(value):
    if isinstance(value, list):
        value = value[0] if value else None
    return (str(value or "").strip()) or None

def normalize_date(value):
    value = normalize_param(value)
    if not value:
        return None
    return frappe.utils.getdate(value)

def to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def to_int(value, default_value):
    try:
        return int(value or default_value)
    except Exception:
        return int(default_value)

def cleanup_canceled_jv_links():
    linked_rows = frappe.get_all(
        "Per Piece",
        filters={"jv_entry_no": ["!=", ""]},
        fields=["name", "jv_entry_no"],
    )
    if not linked_rows:
        return

    jv_names = sorted(set(row.get("jv_entry_no") for row in linked_rows if row.get("jv_entry_no")))
    if not jv_names:
        return

    jv_map = {}
    for je in frappe.get_all("Journal Entry", filters={"name": ["in", jv_names]}, fields=["name", "docstatus"]):
        jv_map[je.get("name")] = je.get("docstatus")

    for row in linked_rows:
        jv_no = row.get("jv_entry_no")
        docstatus = jv_map.get(jv_no)
        if docstatus is None or docstatus == 2:
            row_name = row.get("name")
            frappe.db.set_value("Per Piece", row_name, "jv_entry_no", "", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "jv_status", "Pending", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "jv_line_remark", "", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "booked_amount", 0, update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "allowance", 0, update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "advance_deduction", 0, update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "other_deduction", 0, update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "net_amount", 0, update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "paid_amount", 0, update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "unpaid_amount", 0, update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "payment_status", "Unpaid", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "payment_jv_no", "", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "payment_refs", "", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "payment_line_remark", "", update_modified=False)

def parse_payment_refs(text):
    out = []
    raw = str(text or "").strip()
    if not raw:
        return out
    for part in raw.split(";;"):
        bits = part.split("::")
        if len(bits) < 2:
            continue
        jv_no = str(bits[0] or "").strip()
        try:
            amount = float(bits[1] or 0)
        except Exception:
            amount = 0.0
        if jv_no and amount > 0:
            out.append({"jv": jv_no, "amount": amount})
    return out

def serialize_payment_refs(refs):
    parts = []
    for ref in refs or []:
        jv_no = str((ref or {}).get("jv") or "").strip()
        amount = to_float((ref or {}).get("amount"))
        if jv_no and amount > 0:
            parts.append(jv_no + "::" + str(round(amount, 2)))
    return ";;".join(parts)

def compact_list_for_remark(values, limit=8):
    unique = []
    seen = {}
    for value in values or []:
        txt = str(value or "").strip()
        if not txt:
            continue
        if seen.get(txt):
            continue
        seen[txt] = 1
        unique.append(txt)
    if not unique:
        return "-"
    if len(unique) <= limit:
        return ", ".join(unique)
    remaining = len(unique) - limit
    return ", ".join(unique[:limit]) + " +" + str(remaining)

def cleanup_canceled_payment_links():
    rows = frappe.get_all(
        "Per Piece",
        filters={"parenttype": "Per Piece Salary", "parentfield": "perpiece"},
        fields=["name", "amount", "booked_amount", "payment_jv_no", "payment_refs"],
    )
    if not rows:
        return

    jv_names = []
    for row in rows:
        refs = parse_payment_refs(row.get("payment_refs"))
        for ref in refs:
            jv_names.append(ref.get("jv"))
        if row.get("payment_jv_no"):
            jv_names.append(row.get("payment_jv_no"))
    jv_names = sorted(set([j for j in jv_names if j]))
    if not jv_names:
        return

    jv_map = {}
    for je in frappe.get_all("Journal Entry", filters={"name": ["in", jv_names]}, fields=["name", "docstatus"]):
        jv_map[je.get("name")] = je.get("docstatus")

    for row in rows:
        row_name = row.get("name")
        booked = max(to_float(row.get("booked_amount")), 0.0)
        if booked <= 0:
            booked = max(to_float(row.get("amount")), 0.0)
            if booked > 0:
                frappe.db.set_value("Per Piece", row_name, "booked_amount", round(booked, 2), update_modified=False)
        refs = parse_payment_refs(row.get("payment_refs"))
        active_refs = []
        for ref in refs:
            if jv_map.get(ref.get("jv")) == 1:
                active_refs.append(ref)

        paid = 0.0
        last_jv = ""
        for ref in active_refs:
            paid = paid + max(to_float(ref.get("amount")), 0.0)
            last_jv = ref.get("jv") or last_jv
        if booked > 0 and paid > booked:
            paid = booked
        unpaid = max(booked - paid, 0.0)

        if booked <= 0:
            status = "Unpaid"
        elif paid <= 0:
            status = "Unpaid"
        elif unpaid <= 0:
            status = "Paid"
        else:
            status = "Partly Paid"

        frappe.db.set_value("Per Piece", row_name, "paid_amount", round(paid, 2), update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "unpaid_amount", round(unpaid, 2), update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "payment_status", status, update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "payment_refs", serialize_payment_refs(active_refs), update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "payment_jv_no", last_jv if paid > 0 else "", update_modified=False)
        if paid <= 0:
            frappe.db.set_value("Per Piece", row_name, "payment_line_remark", "", update_modified=False)

def get_employee_advance_balances(employee_list, upto_date):
    balances = {}
    for emp in employee_list:
        balances[emp] = 0.0

    if not employee_list:
        return balances
    if not frappe.db.exists("DocType", "Employee Advance"):
        return balances

    rows = frappe.db.sql(
        \"\"\"
        SELECT
            employee,
            SUM(IFNULL(paid_amount, 0) - IFNULL(claimed_amount, 0) - IFNULL(return_amount, 0)) AS closing_balance
        FROM `tabEmployee Advance`
        WHERE
            docstatus = 1
            AND employee IN %(employees)s
            AND (%(upto_date)s IS NULL OR posting_date <= %(upto_date)s)
        GROUP BY employee
        \"\"\",
        {"employees": tuple(employee_list), "upto_date": upto_date},
        as_dict=True,
    )

    for row in rows:
        emp = row.get("employee")
        if not emp:
            continue
        balances[emp] = round(max(to_float(row.get("closing_balance")), 0.0), 2)
    return balances

def get_all_employee_advance_rows(upto_date):
    out = []
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    end_date = frappe.utils.getdate(upto_date) if upto_date else frappe.utils.getdate(frappe.utils.nowdate())
    end_year = int(end_date.year)
    end_month = int(end_date.month)

    def shift_month(year, month, delta):
        total = (year * 12 + (month - 1)) + delta
        return [int(total // 12), int(total % 12 + 1)]

    months = []
    for delta in range(-5, 1):
        shifted = shift_month(end_year, end_month, delta)
        yy = shifted[0]
        mm = shifted[1]
        key = str(yy).zfill(4) + "-" + str(mm).zfill(2)
        label = month_names[mm - 1] + "-" + str(yy)[-2:]
        months.append({"key": key, "label": label})

    first_month = months[0]["key"] if months else (str(end_year).zfill(4) + "-" + str(end_month).zfill(2))
    first_month_date = frappe.utils.getdate(first_month + "-01")
    to_date_value = end_date

    name_map = {}
    branch_map = {}
    if frappe.db.exists("DocType", "Employee"):
        for emp_row in frappe.get_all("Employee", fields=["name", "employee_name", "branch"], order_by="name asc"):
            key = emp_row.get("name")
            if key:
                name_map[key] = emp_row.get("employee_name") or key
                branch_map[key] = emp_row.get("branch") or ""

    account_roots = frappe.db.sql(
        \"\"\"
        SELECT name, lft, rgt
        FROM `tabAccount`
        WHERE
            docstatus < 2
            AND (
                LOWER(name) LIKE %(kw1)s
                OR LOWER(IFNULL(account_name, '')) LIKE %(kw1)s
                OR LOWER(name) LIKE %(kw2)s
                OR LOWER(IFNULL(account_name, '')) LIKE %(kw2)s
            )
        \"\"\",
        {"kw1": "%employee advances%", "kw2": "%employee advance%"},
        as_dict=True,
    )

    account_map = {}
    for root in account_roots:
        lft = root.get("lft")
        rgt = root.get("rgt")
        if lft is None or rgt is None:
            continue
        children = frappe.db.sql(
            \"\"\"
            SELECT name
            FROM `tabAccount`
            WHERE lft >= %(lft)s AND rgt <= %(rgt)s
            \"\"\",
            {"lft": lft, "rgt": rgt},
            as_dict=True,
        )
        for child in children:
            name = child.get("name")
            if name:
                account_map[name] = 1

    month_key_map = {}
    for mm in months:
        month_key_map[mm.get("key")] = 1

    def build_rows_from_map(source_map):
        built = []
        for emp in sorted(source_map.keys()):
            rec = source_map.get(emp) or {}
            opening = to_float(rec.get("opening_balance"))
            running = opening
            has_activity = abs(opening) >= 0.01
            for mm in months:
                value = to_float((rec.get("month_values") or {}).get(mm.get("key")))
                running = running + value
                if abs(value) >= 0.01:
                    has_activity = True
            closing = round(running, 2)
            if abs(closing) >= 0.01:
                has_activity = True
            if not has_activity:
                continue
            built.append(
                {
                    "employee": emp,
                    "name1": rec.get("name1") or emp,
                    "branch": rec.get("branch") or "",
                    "opening_balance": round(opening, 2),
                    "month_values": rec.get("month_values") or {},
                    "closing_balance": closing,
                    "advance_balance": closing,
                }
            )
        return built

    def build_map_from_gl(gl_rows):
        adv_map = {}
        for rr in gl_rows or []:
            emp = rr.get("party")
            if not emp:
                continue

            if emp not in adv_map:
                month_vals = {}
                for mm in months:
                    month_vals[mm.get("key")] = 0.0
                adv_map[emp] = {
                    "employee": emp,
                    "name1": name_map.get(emp) or emp,
                    "branch": branch_map.get(emp) or "",
                    "opening_balance": 0.0,
                    "month_values": month_vals,
                }

            posting_date = frappe.utils.getdate(rr.get("posting_date"))
            amt = to_float(rr.get("debit")) - to_float(rr.get("credit"))

            if posting_date and posting_date < first_month_date:
                adv_map[emp]["opening_balance"] = round(to_float(adv_map[emp]["opening_balance"]) + amt, 2)
                continue

            key = ""
            if posting_date:
                key = str(int(posting_date.year)).zfill(4) + "-" + str(int(posting_date.month)).zfill(2)
            if key and month_key_map.get(key):
                adv_map[emp]["month_values"][key] = round(to_float(adv_map[emp]["month_values"].get(key)) + amt, 2)
        return adv_map

    def build_map_from_employee_advance(fallback_rows):
        fallback_map = {}
        for rr in fallback_rows or []:
            emp = rr.get("employee")
            if not emp:
                continue
            if emp not in fallback_map:
                month_vals = {}
                for mm in months:
                    month_vals[mm.get("key")] = 0.0
                fallback_map[emp] = {
                    "employee": emp,
                    "name1": name_map.get(emp) or emp,
                    "branch": branch_map.get(emp) or "",
                    "opening_balance": 0.0,
                    "month_values": month_vals,
                }

            posting_date = frappe.utils.getdate(rr.get("posting_date"))
            amt = to_float(rr.get("paid_amount")) - to_float(rr.get("claimed_amount")) - to_float(rr.get("return_amount"))
            if posting_date and posting_date < first_month_date:
                fallback_map[emp]["opening_balance"] = round(to_float(fallback_map[emp]["opening_balance"]) + amt, 2)
                continue

            key = ""
            if posting_date:
                key = str(int(posting_date.year)).zfill(4) + "-" + str(int(posting_date.month)).zfill(2)
            if key and month_key_map.get(key):
                fallback_map[emp]["month_values"][key] = round(
                    to_float(fallback_map[emp]["month_values"].get(key)) + amt,
                    2,
                )
        return fallback_map

    def merge_maps(primary_map, fallback_map):
        merged = {}
        all_employees = {}
        for emp in primary_map.keys():
            all_employees[emp] = 1
        for emp in fallback_map.keys():
            all_employees[emp] = 1

        for emp in all_employees.keys():
            primary = primary_map.get(emp) or {}
            fallback = fallback_map.get(emp) or {}
            primary_months = primary.get("month_values") or {}
            fallback_months = fallback.get("month_values") or {}
            month_vals = {}
            for mm in months:
                key = mm.get("key")
                pval = to_float(primary_months.get(key))
                fval = to_float(fallback_months.get(key))
                month_vals[key] = pval if abs(pval) >= 0.01 else fval
            opening_primary = to_float(primary.get("opening_balance"))
            opening_fallback = to_float(fallback.get("opening_balance"))
            merged[emp] = {
                "employee": emp,
                "name1": primary.get("name1") or fallback.get("name1") or name_map.get(emp) or emp,
                "branch": primary.get("branch") or fallback.get("branch") or branch_map.get(emp) or "",
                "opening_balance": opening_primary if abs(opening_primary) >= 0.01 else opening_fallback,
                "month_values": month_vals,
            }
        return merged

    account_names = sorted(account_map.keys())
    gl_map = {}
    if account_names:
        gl_rows = frappe.get_all(
            "GL Entry",
            filters={
                "docstatus": 1,
                "is_cancelled": 0,
                "party_type": "Employee",
                "account": ["in", account_names],
                "posting_date": ["<=", to_date_value],
            },
            fields=["party", "posting_date", "debit", "credit"],
            order_by="posting_date asc, creation asc",
            limit_page_length=200000,
        )
        gl_map = build_map_from_gl(gl_rows)

    fallback_map = {}
    if frappe.db.exists("DocType", "Employee Advance"):
        fallback_rows = frappe.get_all(
            "Employee Advance",
            filters={"docstatus": 1, "posting_date": ["<=", to_date_value]},
            fields=["employee", "posting_date", "paid_amount", "claimed_amount", "return_amount"],
            order_by="posting_date asc, creation asc",
            limit_page_length=200000,
        )
        fallback_map = build_map_from_employee_advance(fallback_rows)

    merged_map = merge_maps(gl_map, fallback_map)
    out = build_rows_from_map(merged_map if merged_map else (gl_map if gl_map else fallback_map))
    return {"rows": out, "months": months}

args = dict(frappe.form_dict or {})

from_date = normalize_date(args.get("from_date"))
to_date = normalize_date(args.get("to_date"))
if from_date and to_date and from_date > to_date:
    frappe.throw("From Date cannot be after To Date.")

employee = normalize_param(args.get("employee"))
company = normalize_param(args.get("company"))
product = normalize_param(args.get("product"))
process_type = normalize_param(args.get("process_type"))
sales_order = normalize_param(args.get("sales_order"))
item_group = normalize_param(args.get("item_group"))
delivery_note = normalize_param(args.get("delivery_note"))
po_number = normalize_param(args.get("po_number"))
entry_no = normalize_param(args.get("entry_no"))
max_rows = to_int(args.get("max_rows"), 0)
if max_rows < 0:
    max_rows = 0
if max_rows > 200000:
    max_rows = 200000
max_days = to_int(args.get("max_days"), 0)
if max_days < 0:
    max_days = 0
if max_days > 3650:
    max_days = 3650
get_options = str(args.get("get_options") or "").lower() in ("1", "true", "yes")

if to_date and max_days > 0:
    min_from = frappe.utils.add_days(to_date, -max_days + 1)
    if (not from_date) or (from_date < min_from):
        from_date = min_from

all_advance_result = get_all_employee_advance_rows(to_date)
all_advance_rows = all_advance_result.get("rows") or []
all_advance_months = all_advance_result.get("months") or []
all_advance_balances = {}
for adv in all_advance_rows:
    emp = adv.get("employee")
    if emp:
        all_advance_balances[emp] = to_float(adv.get("advance_balance"))

cleanup_canceled_jv_links()
cleanup_canceled_payment_links()

company_options = []
if frappe.db.exists("DocType", "Company"):
    for company_row in frappe.get_all("Company", fields=["name"], order_by="name asc", limit_page_length=5000):
        company_name = str((company_row or {}).get("name") or "").strip()
        if company_name:
            company_options.append(company_name)
company_options = sorted(set(company_options))

parent_filters = {"docstatus": ["<", 2]}
if from_date:
    parent_filters["to_date"] = [">=", from_date]
if to_date:
    parent_filters["from_date"] = ["<=", to_date]
if po_number:
    parent_filters["po_number"] = po_number
if company and frappe.get_meta("Per Piece Salary").has_field("company"):
    parent_filters["company"] = company
if delivery_note and frappe.get_meta("Per Piece Salary").has_field("delivery_note"):
    parent_filters["delivery_note"] = delivery_note
if entry_no:
    parent_filters["name"] = entry_no

parents = frappe.get_all(
    "Per Piece Salary",
    filters=parent_filters,
    fields=["name", "from_date", "to_date", "po_number", "item_group", "delivery_note", "company", "total_qty", "total_amount"],
    order_by="from_date desc, creation desc",
    limit_page_length=(max_rows * 2 if max_rows > 0 else 200000),
)

if not parents:
    frappe.response["message"] = {
        "columns": [],
        "data": [],
        "employees": [],
        "products": [],
        "process_types": [],
        "sales_orders": [],
        "item_groups": [],
        "companies": company_options,
        "advance_balances": all_advance_balances,
        "advance_rows": all_advance_rows,
        "advance_months": all_advance_months,
    }
else:
    parent_names = [p["name"] for p in parents]
    option_rows = frappe.get_all(
        "Per Piece",
        filters={"parent": ["in", parent_names], "parenttype": "Per Piece Salary", "parentfield": "perpiece"},
        fields=["employee", "product", "process_type", "process_size", "sales_order"],
    )

    employees = sorted(set((row.get("employee") or "").strip() for row in option_rows if row.get("employee")))
    products = sorted(set((row.get("product") or "").strip() for row in option_rows if row.get("product")))
    process_types = sorted(
        set((row.get("process_type") or "").strip() for row in option_rows if row.get("process_type"))
    )
    sales_order_set = set((row.get("sales_order") or "").strip() for row in option_rows if row.get("sales_order"))
    if frappe.db.exists("DocType", "Sales Order"):
        so_rows = frappe.get_all(
            "Sales Order",
            filters={"docstatus": ["<", 2]},
            fields=["name"],
            order_by="transaction_date desc, modified desc",
            limit_page_length=5000,
        )
        for so_row in so_rows:
            so_name = str((so_row or {}).get("name") or "").strip()
            if so_name:
                sales_order_set.add(so_name)
    sales_orders = sorted(sales_order_set)
    product_names = [p for p in products if p]
    item_group_map = {}
    if product_names:
        item_rows = frappe.get_all(
            "Item",
            filters={"name": ["in", product_names]},
            fields=["name", "item_group"],
            limit_page_length=max(len(product_names), 500),
        )
        for item_row in item_rows:
            item_name = item_row.get("name")
            if item_name:
                item_group_map[item_name] = item_row.get("item_group") or ""
    item_groups = sorted(
        set(
            [str((p or {}).get("item_group") or "").strip() for p in parents if (p or {}).get("item_group")]
            + [str(v or "").strip() for v in item_group_map.values() if v]
        )
    )
    companies = sorted(
        set(
            [str((p or {}).get("company") or "").strip() for p in parents if (p or {}).get("company")]
        )
    )
    for company_name in company_options:
        if company_name:
            companies.append(company_name)
    companies = sorted(set(companies))
    advance_balances = all_advance_balances

    if get_options:
        frappe.response["message"] = {
            "columns": [],
            "data": [],
            "employees": employees,
            "products": products,
            "process_types": process_types,
            "sales_orders": sales_orders,
            "item_groups": item_groups,
            "companies": companies,
            "advance_balances": advance_balances,
            "advance_rows": all_advance_rows,
            "advance_months": all_advance_months,
        }
    else:
        child_filters = {
            "parent": ["in", parent_names],
            "parenttype": "Per Piece Salary",
            "parentfield": "perpiece",
        }
        if employee:
            child_filters["employee"] = employee
        if product:
            child_filters["product"] = product
        if process_type:
            child_filters["process_type"] = process_type
        if sales_order:
            child_filters["sales_order"] = sales_order

        children = frappe.get_all(
            "Per Piece",
            filters=child_filters,
            fields=[
                "name",
                "parent",
                "idx",
                "employee",
                "name1",
                "product",
                "process_type",
                "process_size",
                "sales_order",
                "delivery_note",
                "qty",
                "rate",
                "amount",
                "jv_entry_no",
                "jv_status",
                "jv_line_remark",
                "booked_amount",
                "paid_amount",
                "unpaid_amount",
                "payment_status",
                "payment_jv_no",
                "payment_line_remark",
            ],
            order_by="parent asc, idx asc",
            limit_page_length=(max_rows if max_rows > 0 else 200000),
        )

        parent_map = {p["name"]: p for p in parents}
        data = []
        for child in children:
            parent = parent_map.get(child["parent"])
            if not parent:
                continue
            row_item_group = (parent.get("item_group") or item_group_map.get(child.get("product")) or "").strip()
            if item_group and row_item_group != item_group:
                continue
            jv_status_value = "Posted" if child.get("jv_status") == "Accounted" else (child.get("jv_status") or "Pending")
            is_booked = bool((child.get("jv_entry_no") or "") and ((child.get("jv_status") or "") in ("Posted", "Accounted")))
            booking_status_value = "Booked" if is_booked else "UnBooked"
            booked_amount_value = to_float(child.get("booked_amount")) if is_booked else 0.0
            if is_booked and booked_amount_value <= 0:
                booked_amount_value = to_float(child.get("amount"))
            paid_amount_value = max(to_float(child.get("paid_amount")), 0.0)
            if booked_amount_value > 0 and paid_amount_value > booked_amount_value:
                paid_amount_value = booked_amount_value
            unpaid_amount_value = to_float(child.get("unpaid_amount"))
            if unpaid_amount_value <= 0:
                unpaid_amount_value = max(booked_amount_value - paid_amount_value, 0.0)
            payment_status_value = child.get("payment_status") or ""
            if not payment_status_value:
                if booked_amount_value <= 0:
                    payment_status_value = "Unpaid"
                elif unpaid_amount_value <= 0:
                    payment_status_value = "Paid"
                elif paid_amount_value > 0:
                    payment_status_value = "Partly Paid"
                else:
                    payment_status_value = "Unpaid"
            data.append(
                {
                    "row_id": child.get("name"),
                    "per_piece_salary": parent.get("name"),
                    "from_date": parent.get("from_date"),
                    "to_date": parent.get("to_date"),
                    "po_number": parent.get("po_number"),
                    "company": parent.get("company"),
                    "item_group": row_item_group,
                    "delivery_note": child.get("delivery_note") or parent.get("delivery_note") or "",
                    "total_qty": parent.get("total_qty"),
                    "total_amount": parent.get("total_amount"),
                    "employee": child.get("employee"),
                    "name1": child.get("name1"),
                    "product": child.get("product"),
                    "process_type": child.get("process_type"),
                    "process_size": child.get("process_size") or "No Size",
                    "sales_order": child.get("sales_order"),
                    "qty": child.get("qty"),
                    "rate": child.get("rate"),
                    "amount": child.get("amount"),
                    "jv_status": jv_status_value,
                    "jv_entry_no": child.get("jv_entry_no"),
                    "jv_line_remark": child.get("jv_line_remark"),
                    "booking_status": booking_status_value,
                    "booked_amount": booked_amount_value,
                    "paid_amount": paid_amount_value,
                    "unpaid_amount": unpaid_amount_value,
                    "payment_status": payment_status_value,
                    "payment_jv_no": child.get("payment_jv_no"),
                    "payment_refs": child.get("payment_refs"),
                    "payment_line_remark": child.get("payment_line_remark"),
                    "advance_balance": advance_balances.get(child.get("employee"), 0.0),
                }
            )

        columns = [
            {"label": "Per Piece Salary", "fieldname": "per_piece_salary", "fieldtype": "Link", "options": "Per Piece Salary", "width": 170},
            {"label": "From Date", "fieldname": "from_date", "fieldtype": "Date", "width": 95},
            {"label": "To Date", "fieldname": "to_date", "fieldtype": "Date", "width": 95},
            {"label": "PO Number", "fieldname": "po_number", "fieldtype": "Data", "width": 110},
            {"label": "Item Group", "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
            {"label": "Delivery Note", "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 150},
            {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
            {"label": "Employee First Name", "fieldname": "name1", "fieldtype": "Data", "width": 140},
            {"label": "Product", "fieldname": "product", "fieldtype": "Link", "options": "Item", "width": 140},
            {"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
            {"label": "Process Type", "fieldname": "process_type", "fieldtype": "Data", "width": 120},
            {"label": "Process Size", "fieldname": "process_size", "fieldtype": "Data", "width": 110},
            {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "precision": 2, "width": 80},
            {"label": "Rate", "fieldname": "rate", "fieldtype": "Float", "precision": 2, "width": 80},
            {"label": "Amount", "fieldname": "amount", "fieldtype": "Float", "precision": 2, "width": 100},
            {"label": "Advance Balance", "fieldname": "advance_balance", "fieldtype": "Float", "precision": 2, "width": 120},
            {"label": "JV Status", "fieldname": "jv_status", "fieldtype": "Data", "width": 95},
            {"label": "JV Entry", "fieldname": "jv_entry_no", "fieldtype": "Link", "options": "Journal Entry", "width": 150},
            {"label": "JV Remark", "fieldname": "jv_line_remark", "fieldtype": "Data", "width": 250},
            {"label": "Booking Status", "fieldname": "booking_status", "fieldtype": "Data", "width": 100},
            {"label": "Booked Amount", "fieldname": "booked_amount", "fieldtype": "Float", "precision": 2, "width": 110},
            {"label": "Payment Status", "fieldname": "payment_status", "fieldtype": "Data", "width": 110},
            {"label": "Paid Amount", "fieldname": "paid_amount", "fieldtype": "Float", "precision": 2, "width": 100},
            {"label": "Unpaid Amount", "fieldname": "unpaid_amount", "fieldtype": "Float", "precision": 2, "width": 110},
            {"label": "Payment JV", "fieldname": "payment_jv_no", "fieldtype": "Link", "options": "Journal Entry", "width": 150},
            {"label": "Payment Remark", "fieldname": "payment_line_remark", "fieldtype": "Data", "width": 220},
        ]

        frappe.response["message"] = {
            "columns": columns,
            "data": data,
            "employees": employees,
            "products": products,
            "process_types": process_types,
            "sales_orders": sales_orders,
            "item_groups": item_groups,
            "companies": companies,
            "advance_balances": advance_balances,
            "advance_rows": all_advance_rows,
            "advance_months": all_advance_months,
            "max_rows": max_rows,
            "max_days": max_days,
            "truncated": 1 if (max_rows > 0 and len(children) >= max_rows) else 0,
        }
"""


CREATE_ENTRY_SERVER_SCRIPT = """# Server Script: API
# Script Type: API
# API Method: create_per_piece_salary_entry

def normalize_param(value):
    if isinstance(value, list):
        value = value[0] if value else None
    return (str(value or "").strip()) or None

def normalize_date(value):
    value = normalize_param(value)
    if not value:
        return None
    return frappe.utils.getdate(value)

def to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def round2(value):
    return round(to_float(value), 2)

def parse_payment_refs(text):
  out = []
  raw = str(text or "").strip()
  if not raw:
    return out
  for part in raw.split(";;"):
    bits = part.split("::")
    if len(bits) < 2:
      continue
    jv_no = str(bits[0] or "").strip()
    try:
      amount = float(bits[1] or 0)
    except Exception:
      amount = 0.0
    if jv_no and amount > 0:
      out.append({"jv": jv_no, "amount": amount})
  return out

def serialize_payment_refs(refs):
  parts = []
  for ref in refs or []:
    jv_no = str((ref or {}).get("jv") or "").strip()
    amount = to_float((ref or {}).get("amount"))
    if jv_no and amount > 0:
      parts.append(jv_no + "::" + str(round(amount, 2)))
  return ";;".join(parts)

def cleanup_canceled_links_for_entry(entry_name):
  if not entry_name:
    return

  rows = frappe.get_all(
    "Per Piece",
    filters={"parent": entry_name, "parenttype": "Per Piece Salary", "parentfield": "perpiece"},
    fields=[
      "name",
      "amount",
      "jv_entry_no",
      "jv_status",
      "booked_amount",
      "paid_amount",
      "unpaid_amount",
      "payment_status",
      "payment_jv_no",
      "payment_refs",
      "payment_line_remark",
    ],
  )
  if not rows:
    return

  jv_names = []
  for row in rows:
    if row.get("jv_entry_no"):
      jv_names.append(row.get("jv_entry_no"))
    if row.get("payment_jv_no"):
      jv_names.append(row.get("payment_jv_no"))
    for ref in parse_payment_refs(row.get("payment_refs")):
      if ref.get("jv"):
        jv_names.append(ref.get("jv"))

  jv_names = sorted(set([j for j in jv_names if j]))
  jv_map = {}
  if jv_names:
    for je in frappe.get_all("Journal Entry", filters={"name": ["in", jv_names]}, fields=["name", "docstatus"]):
      jv_map[je.get("name")] = int(je.get("docstatus") or 0)

  for row in rows:
    row_name = row.get("name")
    jv_no = str(row.get("jv_entry_no") or "").strip()
    is_salary_booked = bool(jv_no and jv_map.get(jv_no) == 1)

    if not is_salary_booked:
      frappe.db.set_value("Per Piece", row_name, "jv_entry_no", "", update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "jv_status", "Pending", update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "booked_amount", 0, update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "allowance", 0, update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "advance_deduction", 0, update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "other_deduction", 0, update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "net_amount", 0, update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "paid_amount", 0, update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "unpaid_amount", 0, update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "payment_status", "Unpaid", update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "payment_jv_no", "", update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "payment_refs", "", update_modified=False)
      frappe.db.set_value("Per Piece", row_name, "payment_line_remark", "", update_modified=False)
      continue

    booked = max(to_float(row.get("booked_amount")), 0.0)
    if booked <= 0:
      booked = max(to_float(row.get("amount")), 0.0)

    refs = parse_payment_refs(row.get("payment_refs"))
    active_refs = []
    for ref in refs:
      if jv_map.get(ref.get("jv")) == 1:
        active_refs.append(ref)

    paid = 0.0
    last_jv = ""
    for ref in active_refs:
      paid = paid + max(to_float(ref.get("amount")), 0.0)
      last_jv = ref.get("jv") or last_jv

    payment_jv_no = str(row.get("payment_jv_no") or "").strip()
    if payment_jv_no and jv_map.get(payment_jv_no) != 1:
      payment_jv_no = ""

    if booked > 0 and paid > booked:
      paid = booked
    unpaid = max(booked - paid, 0.0)

    if booked <= 0:
      status = "Unpaid"
    elif paid <= 0:
      status = "Unpaid"
    elif unpaid <= 0:
      status = "Paid"
    else:
      status = "Partly Paid"

    frappe.db.set_value("Per Piece", row_name, "booked_amount", round(booked, 2), update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "paid_amount", round(paid, 2), update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "unpaid_amount", round(unpaid, 2), update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "payment_status", status, update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "payment_refs", serialize_payment_refs(active_refs), update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "payment_jv_no", (payment_jv_no or last_jv) if paid > 0 else "", update_modified=False)
    if paid <= 0:
      frappe.db.set_value("Per Piece", row_name, "payment_line_remark", "", update_modified=False)

def parse_rows(raw_value):
    out = []
    text = normalize_param(raw_value) or ""
    if not text:
        return out
    for line in text.split(";;"):
        parts = line.split("::")
        if len(parts) < 6:
            continue
        emp = normalize_param(parts[0])
        name1 = normalize_param(parts[1]) or ""
        product = normalize_param(parts[2]) or ""
        process_type = normalize_param(parts[3]) or ""
        process_size = "No Size"
        sales_order = None
        delivery_note = None
        qty_index = 4
        rate_index = 5
        if len(parts) >= 7:
            process_size = normalize_param(parts[4]) or "No Size"
            qty_index = 5
            rate_index = 6
        if len(parts) >= 8:
            sales_order = normalize_param(parts[7])
        if len(parts) >= 9:
            delivery_note = normalize_param(parts[8])
        qty = max(round2(parts[qty_index]), 0.0)
        rate = max(round2(parts[rate_index]), 0.0)
        amount = round2(qty * rate)
        if qty <= 0:
            continue
        out.append(
            {
                "employee": emp,
                "name1": name1,
                "product": product,
                "process_type": process_type,
                "process_size": process_size,
                "sales_order": sales_order,
                "delivery_note": delivery_note,
                "qty": qty,
                "rate": rate,
                "amount": amount,
            }
        )
    return out

args = dict(frappe.form_dict or {})
from_date = normalize_date(args.get("from_date"))
to_date = normalize_date(args.get("to_date"))
po_number = normalize_param(args.get("po_number"))
item_group = normalize_param(args.get("item_group"))
item = normalize_param(args.get("item"))
delivery_note = normalize_param(args.get("delivery_note"))
company = normalize_param(args.get("company"))
selected_items = normalize_param(args.get("selected_items"))
load_by_item = normalize_param(args.get("load_by_item")) or "1"
employee = normalize_param(args.get("employee"))
entry_name = normalize_param(args.get("entry_name"))
rows = parse_rows(args.get("rows"))

# Fallback: if parent Delivery Note was not posted explicitly, infer it from row payload.
if not delivery_note:
    for row in rows:
        row_delivery_note = normalize_param(row.get("delivery_note"))
        if row_delivery_note:
            delivery_note = row_delivery_note
            break

if not from_date or not to_date:
    frappe.throw("From Date and To Date are required.")
if from_date > to_date:
    frappe.throw("From Date cannot be after To Date.")
if not po_number:
    frappe.throw("PO Number is required.")
if not rows:
    frappe.throw("Enter at least one row with Qty.")

if not company:
    company = (
        normalize_param(frappe.defaults.get_user_default("Company"))
        or normalize_param(frappe.db.get_single_value("Global Defaults", "default_company"))
    )

if entry_name:
    if not frappe.db.exists("Per Piece Salary", entry_name):
        frappe.throw("Per Piece Salary not found: " + str(entry_name))

    # Clean stale Journal Entry links first when cancellation was done from Desk.
    cleanup_canceled_links_for_entry(entry_name)

    doc = frappe.get_doc("Per Piece Salary", entry_name)
    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Per Piece Salary can be edited.")
    existing_rows = frappe.get_all(
        "Per Piece",
        filters={"parent": doc.name, "parenttype": "Per Piece Salary", "parentfield": "perpiece"},
        fields=["name", "jv_entry_no", "booked_amount", "paid_amount", "payment_refs"],
    )
    for rr in existing_rows:
        if rr.get("jv_entry_no") or to_float(rr.get("booked_amount")) > 0 or to_float(rr.get("paid_amount")) > 0 or normalize_param(rr.get("payment_refs")):
            frappe.throw("This entry is already booked/paid and cannot be edited from Data Enter.")
    action = "updated"
else:
    doc = frappe.new_doc("Per Piece Salary")
    action = "created"

doc.from_date = from_date
doc.to_date = to_date
doc.po_number = po_number
doc.item_group = item_group
if frappe.get_meta("Per Piece Salary").has_field("delivery_note"):
    doc.delivery_note = delivery_note
if frappe.get_meta("Per Piece Salary").has_field("company"):
    doc.company = company
if frappe.get_meta("Per Piece Salary").has_field("item"):
    doc.item = item
if frappe.get_meta("Per Piece Salary").has_field("selected_items"):
    doc.selected_items = selected_items
if frappe.get_meta("Per Piece Salary").has_field("load_by_item"):
    doc.load_by_item = 1 if str(load_by_item) == "1" else 0
if frappe.get_meta("Per Piece Salary").has_field("employee"):
    doc.employee = employee
doc.set("perpiece", [])
child_meta = frappe.get_meta("Per Piece")

total_qty = 0.0
total_amount = 0.0
for row in rows:
    total_qty = total_qty + row.get("qty", 0)
    total_amount = total_amount + row.get("amount", 0)
    child_row = {
        "employee": row.get("employee"),
        "name1": row.get("name1"),
        "product": row.get("product"),
        "process_type": row.get("process_type"),
        "process_size": row.get("process_size") or "No Size",
        "sales_order": row.get("sales_order"),
        "qty": row.get("qty"),
        "rate": row.get("rate"),
        "amount": row.get("amount"),
    }
    if child_meta.has_field("po_number"):
        child_row["po_number"] = po_number
    if child_meta.has_field("item_group"):
        child_row["item_group"] = item_group
    if child_meta.has_field("delivery_note"):
        child_row["delivery_note"] = row.get("delivery_note") or delivery_note
    doc.append("perpiece", child_row)

try:
    doc.total_qty = round2(total_qty)
except Exception:
    pass
try:
    doc.total_amount = round2(total_amount)
except Exception:
    pass

if entry_name:
    doc.save(ignore_permissions=True)
else:
    doc.insert(ignore_permissions=True)

frappe.response["message"] = {
    "ok": True,
    "name": doc.name,
    "action": action,
    "rows": len(rows),
    "total_qty": round2(total_qty),
    "total_amount": round2(total_amount),
}
"""


CREATE_JV_SERVER_SCRIPT = """# Server Script: API
# Script Type: API
# API Method: create_per_piece_salary_jv

def normalize_param(value):
    if isinstance(value, list):
        value = value[0] if value else None
    return (str(value or "").strip()) or None

def normalize_date(value):
    value = normalize_param(value)
    if not value:
        return None
    return frappe.utils.getdate(value)

def to_bool(value):
    return str(value or "").lower() in ("1", "true", "yes", "on")

def to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def round_amount(value):
    return float(round(to_float(value), 2))

def parse_excluded_employees(raw_value):
    out = []
    seen = {}
    text = normalize_param(raw_value) or ""
    if not text:
        return out
    text = text.replace("\\n", ",")
    for value in text.split(","):
        emp = normalize_param(value)
        if emp and emp not in seen:
            seen[emp] = 1
            out.append(emp)
    return out

def parse_adjustments(raw_value):
    out = {}
    text = normalize_param(raw_value) or ""
    if not text:
        return out
    for row in text.split(";;"):
        parts = row.split("::")
        if len(parts) < 4:
            continue
        emp = normalize_param(parts[0])
        if not emp:
            continue
        out[emp] = {
            "allowance": round_amount(parts[1]),
            "advance_deduction": round_amount(parts[2]),
            "other_deduction": round_amount(parts[3]),
            "advance_balance": round_amount(parts[4]) if len(parts) > 4 else 0.0,
        }
    return out

def parse_name_list(raw_value):
    out = []
    seen = {}
    text = normalize_param(raw_value) or ""
    if not text:
        return out
    text = text.replace("\\n", ",").replace(";", ",")
    for part in text.split(","):
        val = normalize_param(part)
        if not val or seen.get(val):
            continue
        seen[val] = 1
        out.append(val)
    return out

def cleanup_canceled_jv_links():
    linked_rows = frappe.get_all(
        "Per Piece",
        filters={"jv_entry_no": ["!=", ""]},
        fields=["name", "jv_entry_no"],
    )
    if not linked_rows:
        return

    jv_names = sorted(set(row.get("jv_entry_no") for row in linked_rows if row.get("jv_entry_no")))
    if not jv_names:
        return

    jv_map = {}
    for je in frappe.get_all("Journal Entry", filters={"name": ["in", jv_names]}, fields=["name", "docstatus"]):
        jv_map[je.get("name")] = je.get("docstatus")

    for row in linked_rows:
        jv_no = row.get("jv_entry_no")
        docstatus = jv_map.get(jv_no)
        if docstatus is None or docstatus == 2:
            row_name = row.get("name")
            frappe.db.set_value("Per Piece", row_name, "jv_entry_no", "", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "jv_status", "Pending", update_modified=False)
            frappe.db.set_value("Per Piece", row_name, "jv_line_remark", "", update_modified=False)

def get_employee_advance_balances(employee_list, upto_date):
    balances = {}
    for emp in employee_list:
        balances[emp] = 0.0
    if not employee_list:
        return balances
    if not frappe.db.exists("DocType", "Employee Advance"):
        return balances

    rows = frappe.db.sql(
        \"\"\"
        SELECT
            employee,
            SUM(IFNULL(paid_amount, 0) - IFNULL(claimed_amount, 0) - IFNULL(return_amount, 0)) AS closing_balance
        FROM `tabEmployee Advance`
        WHERE
            docstatus = 1
            AND employee IN %(employees)s
            AND (%(upto_date)s IS NULL OR posting_date <= %(upto_date)s)
        GROUP BY employee
        \"\"\",
        {"employees": tuple(employee_list), "upto_date": upto_date},
        as_dict=True,
    )
    for row in rows:
        emp = row.get("employee")
        if not emp:
            continue
        balances[emp] = round(max(to_float(row.get("closing_balance")), 0.0), 2)
    return balances

def build_line_remark(row):
    qty = round(to_float(row.get("qty")), 2)
    rate = round(to_float(row.get("rate")), 2)
    po = row.get("po_number") or "-"
    process_type = row.get("process_type") or "-"
    employee_name = row.get("name1") or row.get("employee") or "-"
    return "Emp " + str(employee_name) + ", Qty " + str(qty) + " x Rate " + str(rate) + ", PO " + str(po) + ", Process " + str(process_type)

def compact_list_for_remark(values, limit=8):
    unique = []
    seen = {}
    for value in values or []:
        txt = str(value or "").strip()
        if not txt:
            continue
        if seen.get(txt):
            continue
        seen[txt] = 1
        unique.append(txt)
    if not unique:
        return "-"
    if len(unique) <= limit:
        return ", ".join(unique)
    remaining = len(unique) - limit
    return ", ".join(unique[:limit]) + " +" + str(remaining)

args = dict(frappe.form_dict or {})

from_date = normalize_date(args.get("from_date"))
to_date = normalize_date(args.get("to_date"))
if not from_date or not to_date:
    frappe.throw("From Date and To Date are required.")
if from_date > to_date:
    frappe.throw("From Date cannot be after To Date.")

company = normalize_param(args.get("company"))
posting_date = normalize_date(args.get("posting_date")) or to_date
expense_account = normalize_param(args.get("expense_account"))
allowance_account = normalize_param(args.get("allowance_account"))
payable_account = normalize_param(args.get("payable_account"))
advance_account = normalize_param(args.get("advance_account"))
deduction_account = normalize_param(args.get("deduction_account"))
header_remark = normalize_param(args.get("header_remark"))
employee = normalize_param(args.get("employee"))
product = normalize_param(args.get("product"))
process_type = normalize_param(args.get("process_type"))
po_number = normalize_param(args.get("po_number"))
entry_no = normalize_param(args.get("entry_no"))
entry_nos = parse_name_list(args.get("entry_nos"))
if entry_no and entry_no not in entry_nos:
    entry_nos.append(entry_no)
entry_no_count = len(entry_nos)
entry_no_list = tuple(entry_nos) if entry_nos else ("",)
employee_wise = to_bool(args.get("employee_wise"))
dry_run = to_bool(args.get("dry_run"))
excluded_employees = parse_excluded_employees(args.get("exclude_employees"))
adjustments = parse_adjustments(args.get("employee_adjustments"))

if not company and not dry_run:
    frappe.throw("Company is required.")
if not expense_account and not dry_run:
    frappe.throw("Salary Account is required.")
if not payable_account and not dry_run:
    frappe.throw("Payable Account is required.")

cleanup_canceled_jv_links()

rows = frappe.db.sql(
    \"\"\"
    SELECT
        pp.name AS child_name,
        pps.name AS entry_no,
        pp.employee,
        pp.name1,
        pp.qty,
        pp.rate,
        pp.amount,
        pp.process_type,
        pps.po_number,
        COALESCE(pp.delivery_note, pps.delivery_note, '') AS delivery_note
    FROM `tabPer Piece` pp
    INNER JOIN `tabPer Piece Salary` pps ON pps.name = pp.parent
    WHERE
        pps.docstatus < 2
        AND pp.parenttype = 'Per Piece Salary'
        AND pp.parentfield = 'perpiece'
        AND pps.to_date >= %(from_date)s
        AND pps.from_date <= %(to_date)s
        AND (%(employee)s IS NULL OR %(employee)s = '' OR pp.employee = %(employee)s)
        AND (%(product)s IS NULL OR %(product)s = '' OR pp.product = %(product)s)
        AND (%(process_type)s IS NULL OR %(process_type)s = '' OR pp.process_type = %(process_type)s)
        AND (%(po_number)s IS NULL OR %(po_number)s = '' OR pps.po_number = %(po_number)s)
        AND (%(entry_no)s IS NULL OR %(entry_no)s = '' OR pps.name = %(entry_no)s)
        AND (%(entry_no_count)s = 0 OR pps.name IN %(entry_no_list)s)
        AND IFNULL(pp.jv_entry_no, '') = ''
        AND IFNULL(pp.jv_status, 'Pending') NOT IN ('Posted', 'Accounted')
    ORDER BY pps.from_date ASC, pps.name ASC, pp.idx ASC
    \"\"\",
    {
        "from_date": from_date,
        "to_date": to_date,
        "employee": employee,
        "product": product,
        "process_type": process_type,
        "po_number": po_number,
        "entry_no": entry_no,
        "entry_no_count": entry_no_count,
        "entry_no_list": entry_no_list,
    },
    as_dict=True,
)

if excluded_employees:
    rows = [row for row in rows if (normalize_param(row.get("employee")) or "") not in excluded_employees]

if not rows:
    frappe.throw("No unposted rows found for selected filters.")

total_qty = 0.0
employee_totals = {}
missing_employee_rows = 0
for row in rows:
    qty = to_float(row.get("qty"))
    amount = to_float(row.get("amount"))
    line_remark = build_line_remark(row)
    row["line_remark"] = line_remark

    total_qty = total_qty + qty

    emp = row.get("employee")
    if emp:
        if emp not in employee_totals:
            employee_totals[emp] = {
                "qty": 0.0,
                "amount": 0.0,
                "name1": row.get("name1"),
                "allowance": 0.0,
                "advance_balance": 0.0,
                "advance_deduction": 0.0,
                "other_deduction": 0.0,
                "gross_amount": 0.0,
                "net_amount": 0.0,
                "line_remarks": [],
            }
        employee_totals[emp]["qty"] = employee_totals[emp]["qty"] + qty
        employee_totals[emp]["amount"] = employee_totals[emp]["amount"] + amount
        if line_remark and line_remark not in employee_totals[emp]["line_remarks"] and len(employee_totals[emp]["line_remarks"]) < 10:
            employee_totals[emp]["line_remarks"].append(line_remark)
    elif employee_wise:
        missing_employee_rows = missing_employee_rows + 1

if employee_wise and missing_employee_rows:
    frappe.throw("Some rows have blank Employee. Fix employee values before employee-wise JV.")

employee_advance_balances = get_employee_advance_balances(sorted(employee_totals.keys()), to_date)

total_base_amount = 0.0
total_allowance = 0.0
total_gross_amount = 0.0
total_advance_deduction = 0.0
total_other_deduction = 0.0
total_net_payable = 0.0

for emp in employee_totals:
    entry = employee_totals[emp]
    adj = adjustments.get(emp) or {}
    allowance = max(round_amount(adj.get("allowance")), 0.0)
    advance_balance_override = max(round_amount(adj.get("advance_balance")), 0.0)
    advance_balance = max(to_float(employee_advance_balances.get(emp)), 0.0)
    if advance_balance_override > 0:
        advance_balance = advance_balance_override
    advance_deduction = max(round_amount(adj.get("advance_deduction")), 0.0)
    other_deduction = max(round_amount(adj.get("other_deduction")), 0.0)

    gross_amount = entry["amount"] + allowance
    if advance_deduction > advance_balance:
        advance_deduction = advance_balance
    if advance_deduction > gross_amount:
        advance_deduction = gross_amount
    if other_deduction > gross_amount - advance_deduction:
        other_deduction = gross_amount - advance_deduction
    net_amount = gross_amount - advance_deduction - other_deduction

    entry["allowance"] = allowance
    entry["advance_balance"] = advance_balance
    entry["advance_deduction"] = advance_deduction
    entry["other_deduction"] = other_deduction
    entry["gross_amount"] = gross_amount
    entry["net_amount"] = net_amount

    total_base_amount = total_base_amount + entry["amount"]
    total_allowance = total_allowance + allowance
    total_gross_amount = total_gross_amount + gross_amount
    total_advance_deduction = total_advance_deduction + advance_deduction
    total_other_deduction = total_other_deduction + other_deduction
    total_net_payable = total_net_payable + net_amount

if total_gross_amount <= 0:
    frappe.throw("Total amount is zero. Nothing to post.")

if total_net_payable < 0:
    frappe.throw("Net payable cannot be negative.")

preview_items = []
for emp in sorted(employee_totals.keys()):
    entry = employee_totals[emp]
    rate = 0
    if entry["qty"]:
        rate = entry["amount"] / entry["qty"]
    preview_items.append(
        {
            "employee": emp,
            "name1": entry.get("name1"),
            "qty": round(entry["qty"], 2),
            "rate": round(rate, 2),
            "amount": round(entry["amount"], 2),
            "allowance": round(entry["allowance"], 2),
            "advance_balance": round(entry["advance_balance"], 2),
            "advance_deduction": round(entry["advance_deduction"], 2),
            "other_deduction": round(entry["other_deduction"], 2),
            "net_amount": round(entry["net_amount"], 2),
            "remarks": "; ".join(entry.get("line_remarks") or []),
        }
    )

if dry_run:
    frappe.response["message"] = {
        "ok": True,
        "mode": "preview",
        "rows": len(rows),
        "total_qty": round(total_qty, 2),
        "base_amount": round(total_base_amount, 2),
        "allowance_amount": round(total_allowance, 2),
        "gross_amount": round(total_gross_amount, 2),
        "advance_deduction_amount": round(total_advance_deduction, 2),
        "other_deduction_amount": round(total_other_deduction, 2),
        "net_payable_amount": round(total_net_payable, 2),
        "debit_amount": round(total_gross_amount, 2),
        "credit_amount": round(total_gross_amount, 2),
        "employee_wise": employee_wise,
        "employee_summary": preview_items,
    }
else:
    if total_allowance > 0 and not allowance_account:
        allowance_account = expense_account
    if total_advance_deduction > 0 and not advance_account:
        frappe.throw("Advance Account is required when Advance Deduction is entered.")
    if total_other_deduction > 0 and not deduction_account:
        frappe.throw("Deduction Account is required when Other Deduction is entered.")

    payable_account_type = frappe.db.get_value("Account", payable_account, "account_type") if payable_account else None
    advance_account_type = frappe.db.get_value("Account", advance_account, "account_type") if advance_account else None
    deduction_account_type = frappe.db.get_value("Account", deduction_account, "account_type") if deduction_account else None

    if payable_account_type in ("Receivable", "Payable") and not employee_wise:
        frappe.throw("Payable account requires party-wise entries. Enable Employee-wise JV.")
    if total_advance_deduction > 0 and advance_account_type in ("Receivable", "Payable") and not employee_wise:
        frappe.throw("Advance account requires party-wise entries. Enable Employee-wise JV.")
    if total_other_deduction > 0 and deduction_account_type in ("Receivable", "Payable") and not employee_wise:
        frappe.throw("Deduction account requires party-wise entries. Enable Employee-wise JV.")

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = posting_date
    entry_numbers = compact_list_for_remark([row.get("entry_no") for row in rows])
    po_numbers = compact_list_for_remark([row.get("po_number") for row in rows])
    dc_numbers = compact_list_for_remark([row.get("delivery_note") for row in rows])
    remarks = [
        "PPE Per Piece Salary",
        "DE: " + str(entry_numbers),
        "PO No " + str(po_numbers),
        "DC No " + str(dc_numbers),
    ]
    if header_remark:
        remarks.append(header_remark)
    je.user_remark = " | ".join(remarks)

    if total_base_amount > 0:
        je.append(
            "accounts",
            {
                "account": expense_account,
                "debit_in_account_currency": total_base_amount,
                "user_remark": "Base Salary",
            },
        )

    if total_allowance > 0:
        je.append(
            "accounts",
            {
                "account": allowance_account or expense_account,
                "debit_in_account_currency": total_allowance,
                "user_remark": "Allowance",
            },
        )

    if employee_wise:
        for emp in sorted(employee_totals.keys()):
            entry = employee_totals[emp]
            row_amount = entry["net_amount"]
            if row_amount <= 0:
                continue
            credit_row = {
                "account": payable_account,
                "credit_in_account_currency": row_amount,
            }
            if payable_account_type in ("Receivable", "Payable"):
                credit_row["party_type"] = "Employee"
                credit_row["party"] = emp
            line_notes = "; ".join(entry.get("line_remarks") or [])
            remark = "Net Salary - " + str(emp)
            if line_notes:
                remark = remark + " | " + line_notes
            credit_row["user_remark"] = remark
            je.append("accounts", credit_row)
    else:
        je.append(
            "accounts",
            {
                "account": payable_account,
                "credit_in_account_currency": total_net_payable,
                "user_remark": "Net Salary Payable",
            },
        )

    if total_advance_deduction > 0:
        if employee_wise:
            for emp in sorted(employee_totals.keys()):
                entry = employee_totals[emp]
                row_amount = entry["advance_deduction"]
                if row_amount <= 0:
                    continue
                credit_row = {
                    "account": advance_account,
                    "credit_in_account_currency": row_amount,
                    "user_remark": "Advance Recovery - " + str(emp),
                }
                if advance_account_type in ("Receivable", "Payable"):
                    credit_row["party_type"] = "Employee"
                    credit_row["party"] = emp
                je.append("accounts", credit_row)
        else:
            je.append(
                "accounts",
                {
                    "account": advance_account,
                    "credit_in_account_currency": total_advance_deduction,
                    "user_remark": "Advance Recovery",
                },
            )

    if total_other_deduction > 0:
        if employee_wise:
            for emp in sorted(employee_totals.keys()):
                entry = employee_totals[emp]
                row_amount = entry["other_deduction"]
                if row_amount <= 0:
                    continue
                credit_row = {
                    "account": deduction_account,
                    "credit_in_account_currency": row_amount,
                    "user_remark": "Salary Deduction - " + str(emp),
                }
                if deduction_account_type in ("Receivable", "Payable"):
                    credit_row["party_type"] = "Employee"
                    credit_row["party"] = emp
                je.append("accounts", credit_row)
        else:
            je.append(
                "accounts",
                {
                    "account": deduction_account,
                    "credit_in_account_currency": total_other_deduction,
                    "user_remark": "Salary Deduction",
                },
            )

    je.insert(ignore_permissions=True)
    je.submit()

    rows_by_employee = {}
    for row in rows:
        emp = normalize_param(row.get("employee")) or ""
        if emp not in rows_by_employee:
            rows_by_employee[emp] = []
        rows_by_employee[emp].append(row)

    for emp in rows_by_employee:
        emp_rows = rows_by_employee.get(emp) or []
        if not emp_rows:
            continue
        emp_base = 0.0
        for rr in emp_rows:
            emp_base = emp_base + max(to_float(rr.get("amount")), 0.0)
        emp_net = max(to_float((employee_totals.get(emp) or {}).get("net_amount")), 0.0)
        emp_allowance = max(to_float((employee_totals.get(emp) or {}).get("allowance")), 0.0)
        emp_advance = max(to_float((employee_totals.get(emp) or {}).get("advance_deduction")), 0.0)
        emp_other = max(to_float((employee_totals.get(emp) or {}).get("other_deduction")), 0.0)

        running = 0.0
        running_allowance = 0.0
        running_advance = 0.0
        running_other = 0.0
        for idx, rr in enumerate(emp_rows):
            child_name = rr.get("child_name")
            if not child_name:
                continue
            row_base = max(to_float(rr.get("amount")), 0.0)
            if idx == len(emp_rows) - 1:
                booked = max(emp_net - running, 0.0)
                row_allowance = max(emp_allowance - running_allowance, 0.0)
                row_advance = max(emp_advance - running_advance, 0.0)
                row_other = max(emp_other - running_other, 0.0)
            else:
                if emp_base > 0:
                    row_ratio = row_base / emp_base
                    booked = round(row_ratio * emp_net, 2)
                    row_allowance = round(row_ratio * emp_allowance, 2)
                    row_advance = round(row_ratio * emp_advance, 2)
                    row_other = round(row_ratio * emp_other, 2)
                else:
                    booked = round(emp_net / len(emp_rows), 2)
                    row_allowance = round(emp_allowance / len(emp_rows), 2)
                    row_advance = round(emp_advance / len(emp_rows), 2)
                    row_other = round(emp_other / len(emp_rows), 2)
                running = running + booked
                running_allowance = running_allowance + row_allowance
                running_advance = running_advance + row_advance
                running_other = running_other + row_other
            booked = round(max(booked, 0.0), 2)
            row_allowance = round(max(row_allowance, 0.0), 2)
            row_advance = round(max(row_advance, 0.0), 2)
            row_other = round(max(row_other, 0.0), 2)
            row_net = booked

            frappe.db.set_value("Per Piece", child_name, "jv_entry_no", je.name, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "jv_status", "Posted", update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "jv_line_remark", rr.get("line_remark"), update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "booked_amount", booked, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "allowance", row_allowance, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "advance_deduction", row_advance, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "other_deduction", row_other, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "net_amount", row_net, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "paid_amount", 0, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "unpaid_amount", booked, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_status", "Unpaid", update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_jv_no", "", update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_refs", "", update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_line_remark", "", update_modified=False)

    frappe.response["message"] = {
        "ok": True,
        "mode": "created",
        "journal_entry": je.name,
        "journal_entry_docstatus": je.docstatus,
        "rows": len(rows),
        "total_qty": round(total_qty, 2),
        "base_amount": round(total_base_amount, 2),
        "allowance_amount": round(total_allowance, 2),
        "gross_amount": round(total_gross_amount, 2),
        "advance_deduction_amount": round(total_advance_deduction, 2),
        "other_deduction_amount": round(total_other_deduction, 2),
        "net_payable_amount": round(total_net_payable, 2),
        "debit_amount": round(total_gross_amount, 2),
        "credit_amount": round(total_gross_amount, 2),
        "employee_wise": employee_wise,
    }
"""


CANCEL_JV_SERVER_SCRIPT = """# Server Script: API
# Script Type: API
# API Method: cancel_per_piece_salary_jv

def normalize_param(value):
    if isinstance(value, list):
        value = value[0] if value else None
    return (str(value or "").strip()) or None

args = dict(frappe.form_dict or {})
journal_entry = normalize_param(args.get("journal_entry"))

if not journal_entry:
    frappe.throw("Journal Entry is required.")
if not frappe.db.exists("Journal Entry", journal_entry):
    frappe.throw("Journal Entry not found: " + str(journal_entry))

je = frappe.get_doc("Journal Entry", journal_entry)
previous_docstatus = je.docstatus

if je.docstatus == 1:
    je.flags.ignore_permissions = True
    je.cancel()
elif je.docstatus == 0:
    frappe.delete_doc("Journal Entry", je.name, ignore_permissions=True)
elif je.docstatus == 2:
    pass

rows = frappe.get_all("Per Piece", filters={"jv_entry_no": journal_entry}, fields=["name"])
for row in rows:
    frappe.db.set_value("Per Piece", row.get("name"), "jv_entry_no", "", update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "jv_status", "Pending", update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "jv_line_remark", "", update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "booked_amount", 0, update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "allowance", 0, update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "advance_deduction", 0, update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "other_deduction", 0, update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "net_amount", 0, update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "paid_amount", 0, update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "unpaid_amount", 0, update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "payment_status", "Unpaid", update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "payment_jv_no", "", update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "payment_refs", "", update_modified=False)
    frappe.db.set_value("Per Piece", row.get("name"), "payment_line_remark", "", update_modified=False)

frappe.response["message"] = {
    "ok": True,
    "journal_entry": journal_entry,
    "action": "cancelled" if previous_docstatus == 1 else ("deleted" if previous_docstatus == 0 else "already_cancelled"),
    "rows_cleared": len(rows),
}
"""


CREATE_PAYMENT_JV_SERVER_SCRIPT = """# Server Script: API
# Script Type: API
# API Method: create_per_piece_salary_payment_jv

def normalize_param(value):
    if isinstance(value, list):
        value = value[0] if value else None
    return (str(value or "").strip()) or None

def normalize_date(value):
    value = normalize_param(value)
    if not value:
        return None
    return frappe.utils.getdate(value)

def to_bool(value):
    return str(value or "").lower() in ("1", "true", "yes", "on")

def to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def round2(value):
    return round(to_float(value), 2)

def parse_payment_items(raw_value):
    out = {}
    text = normalize_param(raw_value) or ""
    if not text:
        return out
    for row in text.split(";;"):
        bits = row.split("::")
        if len(bits) < 2:
            continue
        emp = normalize_param(bits[0])
        if not emp:
            continue
        amount = max(round2(bits[1]), 0.0)
        if amount > 0:
            out[emp] = amount
    return out

def parse_name_list(raw_value):
    out = []
    seen = {}
    text = normalize_param(raw_value) or ""
    if not text:
        return out
    text = text.replace("\\n", ",").replace(";", ",")
    for part in text.split(","):
        val = normalize_param(part)
        if not val or seen.get(val):
            continue
        seen[val] = 1
        out.append(val)
    return out

def parse_payment_refs(text):
    out = []
    raw = str(text or "").strip()
    if not raw:
        return out
    for part in raw.split(";;"):
        bits = part.split("::")
        if len(bits) < 2:
            continue
        jv_no = str(bits[0] or "").strip()
        amount = round2(bits[1])
        if jv_no and amount > 0:
            out.append({"jv": jv_no, "amount": amount})
    return out

def serialize_payment_refs(refs):
    parts = []
    for ref in refs or []:
        jv_no = str((ref or {}).get("jv") or "").strip()
        amount = round2((ref or {}).get("amount"))
        if jv_no and amount > 0:
            parts.append(jv_no + "::" + str(amount))
    return ";;".join(parts)

def compact_list_for_remark(values, limit=8):
    unique = []
    seen = {}
    for value in values or []:
        txt = str(value or "").strip()
        if not txt:
            continue
        if seen.get(txt):
            continue
        seen[txt] = 1
        unique.append(txt)
    if not unique:
        return "-"
    if len(unique) <= limit:
        return ", ".join(unique)
    remaining = len(unique) - limit
    return ", ".join(unique[:limit]) + " +" + str(remaining)

def cleanup_canceled_payment_links():
    rows = frappe.get_all(
        "Per Piece",
        filters={"parenttype": "Per Piece Salary", "parentfield": "perpiece"},
        fields=["name", "amount", "booked_amount", "payment_jv_no", "payment_refs"],
    )
    if not rows:
        return

    names = []
    for row in rows:
        for ref in parse_payment_refs(row.get("payment_refs")):
            names.append(ref.get("jv"))
        if row.get("payment_jv_no"):
            names.append(row.get("payment_jv_no"))
    names = sorted(set([n for n in names if n]))
    if not names:
        return

    jv_map = {}
    for je in frappe.get_all("Journal Entry", filters={"name": ["in", names]}, fields=["name", "docstatus"]):
        jv_map[je.get("name")] = je.get("docstatus")

    for row in rows:
        row_name = row.get("name")
        booked = max(round2(row.get("booked_amount")), 0.0)
        if booked <= 0:
            booked = max(round2(row.get("amount")), 0.0)
            if booked > 0:
                frappe.db.set_value("Per Piece", row_name, "booked_amount", round2(booked), update_modified=False)
        refs = parse_payment_refs(row.get("payment_refs"))
        active_refs = []
        for ref in refs:
            if jv_map.get(ref.get("jv")) == 1:
                active_refs.append(ref)
        paid = 0.0
        last_jv = ""
        for ref in active_refs:
            paid = paid + max(round2(ref.get("amount")), 0.0)
            last_jv = ref.get("jv") or last_jv
        if booked > 0 and paid > booked:
            paid = booked
        unpaid = max(booked - paid, 0.0)
        if booked <= 0 or paid <= 0:
            status = "Unpaid"
        elif unpaid <= 0:
            status = "Paid"
        else:
            status = "Partly Paid"
        frappe.db.set_value("Per Piece", row_name, "paid_amount", round2(paid), update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "unpaid_amount", round2(unpaid), update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "payment_status", status, update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "payment_refs", serialize_payment_refs(active_refs), update_modified=False)
        frappe.db.set_value("Per Piece", row_name, "payment_jv_no", last_jv if paid > 0 else "", update_modified=False)
        if paid <= 0:
            frappe.db.set_value("Per Piece", row_name, "payment_line_remark", "", update_modified=False)

args = dict(frappe.form_dict or {})

from_date = normalize_date(args.get("from_date"))
to_date = normalize_date(args.get("to_date"))
if not from_date or not to_date:
    frappe.throw("From Date and To Date are required.")
if from_date > to_date:
    frappe.throw("From Date cannot be after To Date.")

company = normalize_param(args.get("company"))
posting_date = normalize_date(args.get("posting_date")) or to_date
payable_account = normalize_param(args.get("payable_account"))
paid_from_account = normalize_param(args.get("paid_from_account"))
header_remark = normalize_param(args.get("header_remark"))
employee = normalize_param(args.get("employee"))
product = normalize_param(args.get("product"))
process_type = normalize_param(args.get("process_type"))
po_number = normalize_param(args.get("po_number"))
entry_no = normalize_param(args.get("entry_no"))
entry_nos = parse_name_list(args.get("entry_nos"))
if entry_no and entry_no not in entry_nos:
    entry_nos.append(entry_no)
entry_no_count = len(entry_nos)
entry_no_list = tuple(entry_nos) if entry_nos else ("",)
dry_run = to_bool(args.get("dry_run"))
payment_items = parse_payment_items(args.get("payment_items"))

cleanup_canceled_payment_links()

rows = frappe.db.sql(
    \"\"\"
    SELECT
        pp.name AS child_name,
        pps.name AS entry_no,
        pp.employee,
        pp.name1,
        pp.amount,
        pp.booked_amount,
        pp.paid_amount,
        pp.unpaid_amount,
        pp.payment_refs,
        pp.jv_entry_no AS salary_jv_no,
        pps.po_number,
        COALESCE(pp.delivery_note, pps.delivery_note, '') AS delivery_note
    FROM `tabPer Piece` pp
    INNER JOIN `tabPer Piece Salary` pps ON pps.name = pp.parent
    WHERE
        pps.docstatus < 2
        AND pp.parenttype = 'Per Piece Salary'
        AND pp.parentfield = 'perpiece'
        AND pps.to_date >= %(from_date)s
        AND pps.from_date <= %(to_date)s
        AND (%(employee)s IS NULL OR %(employee)s = '' OR pp.employee = %(employee)s)
        AND (%(product)s IS NULL OR %(product)s = '' OR pp.product = %(product)s)
        AND (%(process_type)s IS NULL OR %(process_type)s = '' OR pp.process_type = %(process_type)s)
        AND (%(po_number)s IS NULL OR %(po_number)s = '' OR pps.po_number = %(po_number)s)
        AND (%(entry_no)s IS NULL OR %(entry_no)s = '' OR pps.name = %(entry_no)s)
        AND (%(entry_no_count)s = 0 OR pps.name IN %(entry_no_list)s)
        AND IFNULL(pp.jv_entry_no, '') != ''
        AND IFNULL(pp.jv_status, 'Pending') IN ('Posted', 'Accounted')
    ORDER BY pps.from_date ASC, pps.name ASC, pp.idx ASC
    \"\"\",
    {
        "from_date": from_date,
        "to_date": to_date,
        "employee": employee,
        "product": product,
        "process_type": process_type,
        "po_number": po_number,
        "entry_no": entry_no,
        "entry_no_count": entry_no_count,
        "entry_no_list": entry_no_list,
    },
    as_dict=True,
)

if not rows:
    frappe.throw("No booked salary rows found for selected filters.")

employee_summary = {}
for row in rows:
    emp = normalize_param(row.get("employee"))
    if not emp:
        continue
    if emp not in employee_summary:
        employee_summary[emp] = {
            "employee": emp,
            "name1": row.get("name1"),
            "booked_amount": 0.0,
            "paid_amount": 0.0,
            "unpaid_amount": 0.0,
        }
    booked = max(round2(row.get("booked_amount")), 0.0)
    if booked <= 0:
        booked = max(round2(row.get("amount")), 0.0)
    paid = max(round2(row.get("paid_amount")), 0.0)
    unpaid = max(round2(row.get("unpaid_amount")), max(booked - paid, 0.0))
    if unpaid <= 0:
        continue
    employee_summary[emp]["booked_amount"] = employee_summary[emp]["booked_amount"] + booked
    employee_summary[emp]["paid_amount"] = employee_summary[emp]["paid_amount"] + paid
    employee_summary[emp]["unpaid_amount"] = employee_summary[emp]["unpaid_amount"] + unpaid

preview = []
total_booked = 0.0
total_paid = 0.0
total_unpaid = 0.0
total_request = 0.0
total_to_pay = 0.0

for emp in sorted(employee_summary.keys()):
    entry = employee_summary[emp]
    booked = round2(entry.get("booked_amount"))
    paid = round2(entry.get("paid_amount"))
    unpaid = round2(entry.get("unpaid_amount"))
    requested = max(round2(payment_items.get(emp)), 0.0)
    to_pay = min(unpaid, requested)
    total_booked = total_booked + booked
    total_paid = total_paid + paid
    total_unpaid = total_unpaid + unpaid
    total_request = total_request + requested
    total_to_pay = total_to_pay + to_pay
    preview.append(
        {
            "employee": emp,
            "name1": entry.get("name1"),
            "booked_amount": booked,
            "paid_amount": paid,
            "unpaid_amount": unpaid,
            "requested_amount": requested,
            "to_pay_amount": to_pay,
        }
    )

if dry_run:
    frappe.response["message"] = {
        "ok": True,
        "mode": "preview",
        "rows": len(rows),
        "employee_summary": preview,
        "booked_amount": round2(total_booked),
        "paid_amount": round2(total_paid),
        "unpaid_amount": round2(total_unpaid),
        "requested_amount": round2(total_request),
        "payment_amount": round2(total_to_pay),
        "debit_amount": round2(total_to_pay),
        "credit_amount": round2(total_to_pay),
    }
else:
    if not company:
        frappe.throw("Company is required.")
    if not payable_account:
        frappe.throw("Payable Account is required.")
    if not paid_from_account:
        frappe.throw("Paid From Account is required.")
    if total_to_pay <= 0:
        frappe.throw("Enter payment amount for one or more employees.")

    payable_account_type = frappe.db.get_value("Account", payable_account, "account_type") if payable_account else None

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = posting_date
    entry_numbers = compact_list_for_remark([row.get("entry_no") for row in rows])
    salary_jv_numbers = compact_list_for_remark([row.get("salary_jv_no") for row in rows])
    po_numbers = compact_list_for_remark([row.get("po_number") for row in rows])
    dc_numbers = compact_list_for_remark([row.get("delivery_note") for row in rows])
    head = (
        "PPE Per Piece Salary"
        + " | DE: "
        + str(entry_numbers)
        + " | JV No "
        + str(salary_jv_numbers)
        + " | PO No "
        + str(po_numbers)
        + " | DC No "
        + str(dc_numbers)
    )
    if header_remark:
        head = head + " | " + header_remark
    je.user_remark = head

    for item in preview:
        amount = max(round2(item.get("to_pay_amount")), 0.0)
        if amount <= 0:
            continue
        employee_name = item.get("name1") or item.get("employee") or "-"
        booked_snapshot = round2(item.get("booked_amount"))
        paid_snapshot = round2(item.get("paid_amount"))
        unpaid_snapshot = round2(item.get("unpaid_amount"))
        debit_row = {
            "account": payable_account,
            "debit_in_account_currency": amount,
            "user_remark": (
                "Salary Paid - "
                + str(employee_name)
                + " ("
                + str(item.get("employee"))
                + ")"
                + " | B:"
                + str(booked_snapshot)
                + " | PD:"
                + str(paid_snapshot)
                + " | U:"
                + str(unpaid_snapshot)
                + " | PAY:"
                + str(round2(amount))
            ),
        }
        if payable_account_type in ("Receivable", "Payable"):
            debit_row["party_type"] = "Employee"
            debit_row["party"] = item.get("employee")
        je.append("accounts", debit_row)

    je.append(
        "accounts",
        {
            "account": paid_from_account,
            "credit_in_account_currency": round2(total_to_pay),
            "user_remark": "Salary Payment - Bank/Cash",
        },
    )

    je.insert(ignore_permissions=True)
    je.submit()

    rows_by_emp = {}
    for row in rows:
        emp = normalize_param(row.get("employee")) or ""
        if emp not in rows_by_emp:
            rows_by_emp[emp] = []
        rows_by_emp[emp].append(row)

    for item in preview:
        emp = item.get("employee")
        remaining = max(round2(item.get("to_pay_amount")), 0.0)
        if remaining <= 0:
            continue
        emp_rows = rows_by_emp.get(emp) or []
        for row in emp_rows:
            if remaining <= 0:
                break
            child_name = row.get("child_name")
            if not child_name:
                continue
            booked = max(round2(row.get("booked_amount")), 0.0)
            if booked <= 0:
                booked = max(round2(row.get("amount")), 0.0)
                if booked > 0:
                    frappe.db.set_value("Per Piece", child_name, "booked_amount", booked, update_modified=False)
            paid = max(round2(row.get("paid_amount")), 0.0)
            unpaid = max(round2(row.get("unpaid_amount")), max(booked - paid, 0.0))
            if unpaid <= 0:
                continue

            pay_now = min(unpaid, remaining)
            if pay_now <= 0:
                continue
            remaining = remaining - pay_now
            new_paid = min(booked, round2(paid + pay_now))
            new_unpaid = max(round2(booked - new_paid), 0.0)
            if booked <= 0 or new_paid <= 0:
                status = "Unpaid"
            elif new_unpaid <= 0:
                status = "Paid"
            else:
                status = "Partly Paid"

            refs = parse_payment_refs(row.get("payment_refs"))
            refs.append({"jv": je.name, "amount": round2(pay_now)})

            frappe.db.set_value("Per Piece", child_name, "paid_amount", round2(new_paid), update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "unpaid_amount", round2(new_unpaid), update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_status", status, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_jv_no", je.name, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_refs", serialize_payment_refs(refs), update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "payment_line_remark", "Salary Paid JV " + str(je.name), update_modified=False)

    frappe.response["message"] = {
        "ok": True,
        "mode": "created",
        "journal_entry": je.name,
        "journal_entry_docstatus": je.docstatus,
        "payment_amount": round2(total_to_pay),
        "debit_amount": round2(total_to_pay),
        "credit_amount": round2(total_to_pay),
        "employee_summary": preview,
    }
"""


CANCEL_PAYMENT_JV_SERVER_SCRIPT = """# Server Script: API
# Script Type: API
# API Method: cancel_per_piece_salary_payment_jv

def normalize_param(value):
    if isinstance(value, list):
        value = value[0] if value else None
    return (str(value or "").strip()) or None

def to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def parse_payment_refs(text):
    out = []
    raw = str(text or "").strip()
    if not raw:
        return out
    for part in raw.split(";;"):
        bits = part.split("::")
        if len(bits) < 2:
            continue
        jv_no = str(bits[0] or "").strip()
        amount = to_float(bits[1])
        if jv_no and amount > 0:
            out.append({"jv": jv_no, "amount": round(amount, 2)})
    return out

def serialize_payment_refs(refs):
    parts = []
    for ref in refs or []:
        jv_no = str((ref or {}).get("jv") or "").strip()
        amount = round(to_float((ref or {}).get("amount")), 2)
        if jv_no and amount > 0:
            parts.append(jv_no + "::" + str(amount))
    return ";;".join(parts)

args = dict(frappe.form_dict or {})
journal_entry = normalize_param(args.get("journal_entry"))

if not journal_entry:
    frappe.throw("Journal Entry is required.")
if not frappe.db.exists("Journal Entry", journal_entry):
    frappe.throw("Journal Entry not found: " + str(journal_entry))

je = frappe.get_doc("Journal Entry", journal_entry)
previous_docstatus = je.docstatus
if je.docstatus == 1:
    je.flags.ignore_permissions = True
    je.cancel()
elif je.docstatus == 0:
    frappe.delete_doc("Journal Entry", je.name, ignore_permissions=True)
elif je.docstatus == 2:
    pass

rows = frappe.get_all(
    "Per Piece",
    filters={"payment_refs": ["like", "%" + journal_entry + "::%"]},
    fields=["name", "amount", "booked_amount", "payment_refs"],
)

rows_updated = 0
amount_reversed = 0.0
for row in rows:
    row_name = row.get("name")
    booked = max(round(to_float(row.get("booked_amount")), 2), 0.0)
    if booked <= 0:
        booked = max(round(to_float(row.get("amount")), 2), 0.0)
        if booked > 0:
            frappe.db.set_value("Per Piece", row_name, "booked_amount", booked, update_modified=False)
    refs = parse_payment_refs(row.get("payment_refs"))
    active_refs = []
    removed = 0.0
    for ref in refs:
        if ref.get("jv") == journal_entry:
            removed = removed + max(to_float(ref.get("amount")), 0.0)
        else:
            active_refs.append(ref)
    if removed <= 0:
        continue
    amount_reversed = amount_reversed + removed

    paid = 0.0
    last_jv = ""
    for ref in active_refs:
        paid = paid + max(to_float(ref.get("amount")), 0.0)
        last_jv = ref.get("jv") or last_jv
    if booked > 0 and paid > booked:
        paid = booked
    unpaid = max(booked - paid, 0.0)
    if booked <= 0 or paid <= 0:
        status = "Unpaid"
    elif unpaid <= 0:
        status = "Paid"
    else:
        status = "Partly Paid"

    frappe.db.set_value("Per Piece", row_name, "paid_amount", round(paid, 2), update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "unpaid_amount", round(unpaid, 2), update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "payment_status", status, update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "payment_refs", serialize_payment_refs(active_refs), update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "payment_jv_no", last_jv if paid > 0 else "", update_modified=False)
    frappe.db.set_value("Per Piece", row_name, "payment_line_remark", ("Salary Paid JV " + str(last_jv)) if paid > 0 else "", update_modified=False)
    rows_updated = rows_updated + 1

frappe.response["message"] = {
    "ok": True,
    "journal_entry": journal_entry,
    "action": "cancelled" if previous_docstatus == 1 else ("deleted" if previous_docstatus == 0 else "already_cancelled"),
    "rows_updated": rows_updated,
    "amount_reversed": round(amount_reversed, 2),
}
"""


SCRIPT_REPORT_SCRIPT = """from_date = frappe.utils.getdate(filters.get("from_date")) if filters.get("from_date") else None
to_date = frappe.utils.getdate(filters.get("to_date")) if filters.get("to_date") else None

if from_date and to_date and from_date > to_date:
    frappe.throw("From Date cannot be after To Date.")

def to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0

def get_employee_advance_balances(employee_list, upto_date):
    balances = {}
    for emp in employee_list:
        balances[emp] = 0.0
    if not employee_list:
        return balances
    if not frappe.db.exists("DocType", "Employee Advance"):
        return balances
    rows = frappe.db.sql(
        \"\"\"
        SELECT
            employee,
            SUM(IFNULL(paid_amount, 0) - IFNULL(claimed_amount, 0) - IFNULL(return_amount, 0)) AS closing_balance
        FROM `tabEmployee Advance`
        WHERE
            docstatus = 1
            AND employee IN %(employees)s
            AND (%(upto_date)s IS NULL OR posting_date <= %(upto_date)s)
        GROUP BY employee
        \"\"\",
        {"employees": tuple(employee_list), "upto_date": upto_date},
        as_dict=True,
    )
    for row in rows:
        emp = row.get("employee")
        if emp:
            balances[emp] = round(max(to_float(row.get("closing_balance")), 0.0), 2)
    return balances

columns = [
    {"fieldname": "per_piece_salary", "label": "Per Piece Salary", "fieldtype": "Link", "options": "Per Piece Salary", "width": 170},
    {"fieldname": "from_date", "label": "From Date", "fieldtype": "Date", "width": 95},
    {"fieldname": "to_date", "label": "To Date", "fieldtype": "Date", "width": 95},
    {"fieldname": "po_number", "label": "PO Number", "fieldtype": "Data", "width": 110},
    {"fieldname": "item_group", "label": "Item Group", "fieldtype": "Link", "options": "Item Group", "width": 120},
    {"fieldname": "delivery_note", "label": "Delivery Note", "fieldtype": "Link", "options": "Delivery Note", "width": 150},
    {"fieldname": "employee", "label": "Employee", "fieldtype": "Link", "options": "Employee", "width": 120},
    {"fieldname": "name1", "label": "Employee First Name", "fieldtype": "Data", "width": 140},
    {"fieldname": "product", "label": "Product", "fieldtype": "Link", "options": "Item", "width": 140},
    {"fieldname": "process_type", "label": "Process Type", "fieldtype": "Data", "width": 120},
    {"fieldname": "process_size", "label": "Process Size", "fieldtype": "Data", "width": 110},
    {"fieldname": "qty", "label": "Qty", "fieldtype": "Float", "precision": 2, "width": 80},
    {"fieldname": "rate", "label": "Rate", "fieldtype": "Float", "precision": 2, "width": 80},
    {"fieldname": "amount", "label": "Amount", "fieldtype": "Float", "precision": 2, "width": 100},
    {"fieldname": "advance_balance", "label": "Advance Balance", "fieldtype": "Float", "precision": 2, "width": 120},
    {"fieldname": "jv_status", "label": "JV Status", "fieldtype": "Data", "width": 90},
    {"fieldname": "jv_entry_no", "label": "JV Entry", "fieldtype": "Link", "options": "Journal Entry", "width": 150},
    {"fieldname": "jv_line_remark", "label": "JV Remark", "fieldtype": "Data", "width": 250},
    {"fieldname": "booking_status", "label": "Booking Status", "fieldtype": "Data", "width": 100},
    {"fieldname": "booked_amount", "label": "Booked Amount", "fieldtype": "Float", "precision": 2, "width": 110},
    {"fieldname": "payment_status", "label": "Payment Status", "fieldtype": "Data", "width": 110},
    {"fieldname": "paid_amount", "label": "Paid Amount", "fieldtype": "Float", "precision": 2, "width": 100},
    {"fieldname": "unpaid_amount", "label": "Unpaid Amount", "fieldtype": "Float", "precision": 2, "width": 110},
    {"fieldname": "payment_jv_no", "label": "Payment JV", "fieldtype": "Link", "options": "Journal Entry", "width": 150},
    {"fieldname": "payment_line_remark", "label": "Payment Remark", "fieldtype": "Data", "width": 200},
]

parent_filters = {"docstatus": ["<", 2]}
if filters.get("from_date"):
    parent_filters["to_date"] = [">=", filters.get("from_date")]
if filters.get("to_date"):
    parent_filters["from_date"] = ["<=", filters.get("to_date")]
if filters.get("delivery_note"):
    parent_filters["delivery_note"] = filters.get("delivery_note")

parents = frappe.get_all(
    "Per Piece Salary",
    filters=parent_filters,
    fields=["name", "from_date", "to_date", "po_number", "item_group", "delivery_note"],
    order_by="from_date desc, creation desc",
)

result = []
if parents:
    parent_names = [p["name"] for p in parents]
    child_filters = {"parent": ["in", parent_names], "parenttype": "Per Piece Salary", "parentfield": "perpiece"}
    for fieldname in ("employee", "product", "process_type", "jv_status", "payment_status"):
        if filters.get(fieldname):
            child_filters[fieldname] = filters.get(fieldname)
    if filters.get("item_group"):
        parent_names = [p["name"] for p in parents if (p.get("item_group") or "") == filters.get("item_group")]
        child_filters["parent"] = ["in", parent_names or [""]]

    children = frappe.get_all(
        "Per Piece",
        filters=child_filters,
        fields=["parent", "idx", "employee", "name1", "product", "process_type", "process_size", "delivery_note", "qty", "rate", "amount", "jv_status", "jv_entry_no", "jv_line_remark", "booked_amount", "paid_amount", "unpaid_amount", "payment_status", "payment_jv_no", "payment_line_remark"],
        order_by="parent asc, idx asc",
    )

    employee_list = sorted(set((c.get("employee") or "").strip() for c in children if c.get("employee")))
    advance_balances = get_employee_advance_balances(employee_list, to_date)

    parent_map = {p["name"]: p for p in parents}
    for child in children:
        parent = parent_map.get(child["parent"])
        if not parent:
            continue
        jv_status_value = "Posted" if child.get("jv_status") == "Accounted" else (child.get("jv_status") or "Pending")
        booking_status_value = "Booked" if ((child.get("jv_entry_no") or "") and ((child.get("jv_status") or "") in ("Posted", "Accounted"))) else "UnBooked"
        booked_amount_value = to_float(child.get("booked_amount"))
        if booking_status_value != "Booked":
            booked_amount_value = 0.0
        if booking_status_value == "Booked" and booked_amount_value <= 0:
            booked_amount_value = to_float(child.get("amount"))
        paid_amount_value = max(to_float(child.get("paid_amount")), 0.0)
        if booked_amount_value > 0 and paid_amount_value > booked_amount_value:
            paid_amount_value = booked_amount_value
        unpaid_amount_value = to_float(child.get("unpaid_amount"))
        if unpaid_amount_value <= 0:
            unpaid_amount_value = max(booked_amount_value - paid_amount_value, 0.0)
        payment_status_value = child.get("payment_status") or ""
        if not payment_status_value:
            if booked_amount_value <= 0:
                payment_status_value = "Unpaid"
            elif unpaid_amount_value <= 0:
                payment_status_value = "Paid"
            elif paid_amount_value > 0:
                payment_status_value = "Partly Paid"
            else:
                payment_status_value = "Unpaid"
        result.append(
            {
                "per_piece_salary": parent.get("name"),
                "from_date": parent.get("from_date"),
                "to_date": parent.get("to_date"),
                "po_number": parent.get("po_number"),
                "item_group": parent.get("item_group"),
                "delivery_note": child.get("delivery_note") or parent.get("delivery_note") or "",
                "employee": child.get("employee"),
                "name1": child.get("name1"),
                "product": child.get("product"),
                "process_type": child.get("process_type"),
                "process_size": child.get("process_size") or "No Size",
                "qty": child.get("qty"),
                "rate": child.get("rate"),
                "amount": child.get("amount"),
                "advance_balance": advance_balances.get(child.get("employee"), 0.0),
                "jv_status": jv_status_value,
                "jv_entry_no": child.get("jv_entry_no"),
                "jv_line_remark": child.get("jv_line_remark"),
                "booking_status": booking_status_value,
                "booked_amount": booked_amount_value,
                "paid_amount": paid_amount_value,
                "unpaid_amount": unpaid_amount_value,
                "payment_status": payment_status_value,
                "payment_jv_no": child.get("payment_jv_no"),
                "payment_refs": child.get("payment_refs"),
                "payment_line_remark": child.get("payment_line_remark"),
            }
        )

data = (columns, result)
"""


SCRIPT_REPORT_JS = """frappe.query_reports["Per Piece Salary Report"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
        { fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
        { fieldname: "delivery_note", label: __("Delivery Note"), fieldtype: "Link", options: "Delivery Note" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "product", label: __("Product"), fieldtype: "Link", options: "Item" },
        { fieldname: "process_type", label: __("Process Type"), fieldtype: "Data" },
        { fieldname: "jv_status", label: __("JV Status"), fieldtype: "Select", options: "\\nPending\\nPosted" },
        { fieldname: "payment_status", label: __("Payment Status"), fieldtype: "Select", options: "\\nUnpaid\\nPartly Paid\\nPaid" },
    ],
};
"""


QUERY_REPORT_QUERY = """SELECT
    pps.name AS per_piece_salary,
    pps.from_date,
    pps.to_date,
    pps.po_number,
    pps.item_group,
    COALESCE(pp.delivery_note, pps.delivery_note) AS delivery_note,
    pp.employee,
    pp.name1,
    pp.product,
    pp.process_type,
    COALESCE(pp.process_size, 'No Size') AS process_size,
    pp.qty,
    pp.rate,
    pp.amount,
    (
        SELECT SUM(IFNULL(ea.paid_amount, 0) - IFNULL(ea.claimed_amount, 0) - IFNULL(ea.return_amount, 0))
        FROM `tabEmployee Advance` ea
        WHERE
            ea.docstatus = 1
            AND ea.employee = pp.employee
            AND (pps.to_date IS NULL OR ea.posting_date <= pps.to_date)
    ) AS advance_balance,
    IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) AS jv_status,
    pp.jv_entry_no,
    pp.jv_line_remark,
    IF(IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted', 'Booked', 'UnBooked') AS booking_status,
    IF(
        IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted',
        IF(
            IFNULL(pp.booked_amount, 0) > 0,
            LEAST(IFNULL(pp.booked_amount, 0), IFNULL(pp.amount, 0)),
            IFNULL(pp.amount, 0)
        ),
        0
    ) AS booked_amount,
    IF(
        IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted',
        IFNULL(pp.payment_status, 'Unpaid'),
        'Unpaid'
    ) AS payment_status,
    IF(
        IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted',
        LEAST(
            IFNULL(pp.paid_amount, 0),
            IF(
                IFNULL(pp.booked_amount, 0) > 0,
                LEAST(IFNULL(pp.booked_amount, 0), IFNULL(pp.amount, 0)),
                IFNULL(pp.amount, 0)
            )
        ),
        0
    ) AS paid_amount,
    IF(
        IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted',
        GREATEST(
            IF(
                IFNULL(pp.booked_amount, 0) > 0,
                LEAST(IFNULL(pp.booked_amount, 0), IFNULL(pp.amount, 0)),
                IFNULL(pp.amount, 0)
            ) - LEAST(
                IFNULL(pp.paid_amount, 0),
                IF(
                    IFNULL(pp.booked_amount, 0) > 0,
                    LEAST(IFNULL(pp.booked_amount, 0), IFNULL(pp.amount, 0)),
                    IFNULL(pp.amount, 0)
                )
            ),
            0
        ),
        0
    ) AS unpaid_amount,
    pp.payment_jv_no,
    pp.payment_line_remark
FROM `tabPer Piece Salary` pps
LEFT JOIN `tabPer Piece` pp
    ON pp.parent = pps.name
    AND pp.parenttype = 'Per Piece Salary'
    AND pp.parentfield = 'perpiece'
WHERE pps.docstatus < 2
    AND (%(from_date)s IS NULL OR %(from_date)s = '' OR pps.to_date >= %(from_date)s)
    AND (%(to_date)s IS NULL OR %(to_date)s = '' OR pps.from_date <= %(to_date)s)
    AND (%(item_group)s IS NULL OR %(item_group)s = '' OR pps.item_group = %(item_group)s)
    AND (%(delivery_note)s IS NULL OR %(delivery_note)s = '' OR COALESCE(pp.delivery_note, pps.delivery_note) = %(delivery_note)s)
    AND (%(employee)s IS NULL OR %(employee)s = '' OR pp.employee = %(employee)s)
    AND (%(product)s IS NULL OR %(product)s = '' OR pp.product = %(product)s)
    AND (%(process_type)s IS NULL OR %(process_type)s = '' OR pp.process_type = %(process_type)s)
    AND (%(jv_status)s IS NULL OR %(jv_status)s = '' OR IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = %(jv_status)s)
    AND (%(payment_status)s IS NULL OR %(payment_status)s = '' OR IFNULL(pp.payment_status, 'Unpaid') = %(payment_status)s)
ORDER BY pps.from_date DESC, pps.creation DESC, pp.idx ASC
"""


QUERY_REPORT_JS = """frappe.query_reports["Per Piece Query Report Simple"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
        { fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
        { fieldname: "delivery_note", label: __("Delivery Note"), fieldtype: "Link", options: "Delivery Note" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        { fieldname: "product", label: __("Product"), fieldtype: "Link", options: "Item" },
        { fieldname: "process_type", label: __("Process Type"), fieldtype: "Data" },
        { fieldname: "jv_status", label: __("JV Status"), fieldtype: "Select", options: "\\nPending\\nPosted" },
        { fieldname: "payment_status", label: __("Payment Status"), fieldtype: "Select", options: "\\nUnpaid\\nPartly Paid\\nPaid" },
    ],
};
"""


CLIENT_SCRIPT_SCRIPT = """const REPORT_ROUTE = "/per-piece-report";
const CHILD_TABLE_FIELD = "perpiece";
const DECIMALS = 2;
const PROCESS_SIZE_DEFAULT = "No Size";

function calculateRowAmount(row) {
    const qty = flt(row.qty, DECIMALS);
    const rate = flt(row.rate, DECIMALS);
    row.amount = flt(qty * rate, DECIMALS);
}

function validateDateRange(frm) {
    if (!frm.doc.from_date || !frm.doc.to_date) return;
    if (frappe.datetime.get_diff(frm.doc.to_date, frm.doc.from_date) < 0) {
        frappe.throw(__("From Date cannot be after To Date."));
    }
}

function isLoadByItem(frm) {
    const raw = frm.doc.load_by_item;
    return raw === undefined || raw === null || raw === 1 || String(raw) === "1";
}

function isSubmittedDoc(frm) {
  return Number(frm.doc.docstatus || 0) === 1;
}

function setProductQuery(frm) {
    const byItem = isLoadByItem(frm);
    const getProductQuery = () => {
        const filters = { disabled: 0 };
        if (frm.doc.item_group) {
            filters.item_group = frm.doc.item_group;
        }
        if (byItem && frm.doc.item) {
            filters.name = frm.doc.item;
        }
        return { filters };
    };
    const getItemQuery = () => {
        const filters = { disabled: 0 };
        if (frm.doc.item_group) {
            filters.item_group = frm.doc.item_group;
        }
        return { filters };
    };

    frm.set_query("product", CHILD_TABLE_FIELD, getProductQuery);
    frm.set_query("item", () => getItemQuery());

    if (
        frm.fields_dict &&
        frm.fields_dict[CHILD_TABLE_FIELD] &&
        frm.fields_dict[CHILD_TABLE_FIELD].grid
    ) {
        frm.fields_dict[CHILD_TABLE_FIELD].grid.get_field("product").get_query = getProductQuery;
    }
}

function setDeliveryNoteQuery(frm) {
    frm.set_query("delivery_note", () => {
        return { filters: { docstatus: 1 } };
    });
}

function loadRowsFromDeliveryNote(frm, forceReplace = false) {
    const deliveryNote = (frm.doc.delivery_note || "").trim();
    if (!deliveryNote) {
        return Promise.resolve([]);
    }

    const rows = frm.doc[CHILD_TABLE_FIELD] || [];
    const hasMeaningfulRows = rows.some((row) => !isBlankChildRow(row));
    if (hasMeaningfulRows && !forceReplace) {
        return Promise.resolve([]);
    }

    return Promise.resolve(
        frappe.call({
            method: "per_piece_payroll.api.get_delivery_note_process_rows",
            args: { delivery_note: deliveryNote },
        })
    )
        .then((response) => {
            const dnRows = (response && response.message) || [];
            if (!dnRows.length) {
                frappe.show_alert({
                    message: __("No items found in Delivery Note {0}", [deliveryNote]),
                    indicator: "orange",
                });
                return [];
            }

            frm.clear_table(CHILD_TABLE_FIELD);
            dnRows.forEach((src) => {
                const row = frm.add_child(CHILD_TABLE_FIELD);
                row.employee = src.employee || frm.doc.employee || "";
                row.name1 = src.name1 || frm.__per_piece_parent_employee_name || "";
                row.product = src.product || "";
                row.process_type = src.process_type || "";
                row.process_size = src.process_size || PROCESS_SIZE_DEFAULT;
                row.sales_order = src.sales_order || "";
                row.delivery_note = deliveryNote;
                row.qty = flt(src.qty, DECIMALS);
                row.rate = flt(src.rate, DECIMALS);
                row.amount = flt(row.qty * row.rate, DECIMALS);
                row.from_date = frm.doc.from_date || null;
                row.to_date = frm.doc.to_date || null;
                row.po_number = frm.doc.po_number || null;
                row.item_group = frm.doc.item_group || null;
            });

            frm.refresh_field(CHILD_TABLE_FIELD);
            frm.trigger("sync_parent_to_child");
            frm.trigger("recalc_amount_and_total");
            frappe.show_alert({
                message: __("Loaded {0} row(s) from {1}", [dnRows.length, deliveryNote]),
                indicator: "green",
            });
            return dnRows;
        })
        .catch(() => {
            frappe.show_alert({
                message: __("Failed to load Delivery Note {0}", [deliveryNote]),
                indicator: "red",
            });
            return [];
        });
}

function loadItemsForGroup(frm) {
    const byItem = isLoadByItem(frm);
    const selectedItem = (frm.doc.item || "").trim();
    const itemGroup = (frm.doc.item_group || "").trim();
    if (byItem) {
        if (!selectedItem) {
            frm.__per_piece_group_items = [];
            return Promise.resolve([]);
        }
        return Promise.resolve(frappe.call({
                method: "per_piece_payroll.api.get_item_process_rows",
                args: { item: selectedItem },
            }))
            .then((response) => {
                const rows = (response && response.message) || [];
                frm.__per_piece_group_items = itemGroup
                    ? rows.filter((row) => (row.item_group || "").trim() === itemGroup)
                    : rows;
                return frm.__per_piece_group_items;
            })
            .catch(() => {
                frm.__per_piece_group_items = [];
                return [];
            });
    }
    if (!itemGroup) {
        frm.__per_piece_group_items = [];
        return Promise.resolve([]);
    }
    return Promise.resolve(frappe.call({
            method: "per_piece_payroll.api.get_item_process_rows",
            args: { item_group: itemGroup },
        }))
        .then((response) => {
            frm.__per_piece_group_items = (response && response.message) || [];
            return frm.__per_piece_group_items;
        })
        .catch(() => {
            frm.__per_piece_group_items = [];
            return [];
        });
}

function loadProcessRowsForItem(frm, itemName) {
    const product = (itemName || "").trim();
    if (!product) return Promise.resolve([]);

    if (!frm.__per_piece_item_process_map) {
        frm.__per_piece_item_process_map = {};
    }
    if (frm.__per_piece_item_process_map[product]) {
        return Promise.resolve(frm.__per_piece_item_process_map[product]);
    }

    return Promise.resolve(frappe.call({
            method: "per_piece_payroll.api.get_item_process_rows",
            args: { item: product },
        }))
        .then((response) => {
            frm.__per_piece_item_process_map[product] = (response && response.message) || [];
            return frm.__per_piece_item_process_map[product];
        })
        .catch(() => {
            frm.__per_piece_item_process_map[product] = [];
            return [];
        });
}

function getAutoGroupProduct(frm) {
    const rows = frm.__per_piece_group_items || [];
    const items = [...new Set(rows.map((row) => (row && row.item) || "").filter(Boolean))];
    return items.length === 1 ? items[0] : "";
}

function isBlankChildRow(row) {
    if (!row) return true;
    return !(
        (row.employee || "").trim() ||
        (row.name1 || "").trim() ||
        (row.product || "").trim() ||
        flt(row.qty, DECIMALS) ||
        flt(row.rate, DECIMALS) ||
        flt(row.amount, DECIMALS)
    );
}

function isGroupProductAllowed(frm, product) {
    const productName = (product || "").trim();
    const byItem = isLoadByItem(frm);
    const selectedItem = (frm.doc.item || "").trim();
    if (byItem && selectedItem) {
        return !productName || productName === selectedItem;
    }
    const itemGroup = (frm.doc.item_group || "").trim();
    if (!productName || !itemGroup) return true;
    const rows = frm.__per_piece_group_items || [];
    if (!rows.length) return false;
    return rows.some((row) => (row && row.item) === productName);
}

function resetRowProductFields(frm, row) {
    if (!row) return;
    const cdt = row.doctype;
    const cdn = row.name;
    const tasks = [
        frappe.model.set_value(cdt, cdn, "product", ""),
        frappe.model.set_value(cdt, cdn, "process_type", ""),
        frappe.model.set_value(cdt, cdn, "process_size", PROCESS_SIZE_DEFAULT),
        frappe.model.set_value(cdt, cdn, "rate", 0),
        frappe.model.set_value(cdt, cdn, "amount", 0),
    ];
    return Promise.all(tasks).then(() => {
        const freshRow = locals[cdt] && locals[cdt][cdn] ? locals[cdt][cdn] : row;
        calculateRowAmount(freshRow);
        frm.trigger("recalc_amount_and_total");
    }, () => {
        const freshRow = locals[cdt] && locals[cdt][cdn] ? locals[cdt][cdn] : row;
        calculateRowAmount(freshRow);
        frm.trigger("recalc_amount_and_total");
    });
}

function loadParentEmployeeName(frm) {
    const employee = (frm.doc.employee || "").trim();
    if (!employee) {
        frm.__per_piece_parent_employee_name = "";
        return Promise.resolve("");
    }
    if (frm.__per_piece_parent_employee === employee && frm.__per_piece_parent_employee_name) {
        return Promise.resolve(frm.__per_piece_parent_employee_name);
    }

    return Promise.resolve(
        frappe.db.get_value("Employee", employee, "employee_name")
    ).then((response) => {
        const message = (response && response.message) || {};
        frm.__per_piece_parent_employee = employee;
        frm.__per_piece_parent_employee_name = message.employee_name || "";
        return frm.__per_piece_parent_employee_name;
    }).catch(() => {
        frm.__per_piece_parent_employee = employee;
        frm.__per_piece_parent_employee_name = "";
        return "";
    });
}

function applyParentEmployeeToRows(frm) {
    const employee = (frm.doc.employee || "").trim();
    const employeeName = (frm.__per_piece_parent_employee_name || "").trim();
    if (!employee) return;
    const rows = frm.doc[CHILD_TABLE_FIELD] || [];
    rows.forEach((row) => {
        row.employee = employee;
        if (employeeName) {
            row.name1 = employeeName;
        }
    });
}

function populateRowsFromGroup(frm, forceReload = false) {
    const items = frm.__per_piece_group_items || [];
    let rows = frm.doc[CHILD_TABLE_FIELD] || [];
    if (!items.length) return Promise.resolve();

    if (forceReload && rows.length) {
        frm.clear_table(CHILD_TABLE_FIELD);
        rows = frm.doc[CHILD_TABLE_FIELD] || [];
    }
    const hasMeaningfulRows = rows.some((row) => !isBlankChildRow(row));
    if (hasMeaningfulRows) return Promise.resolve();

    frm.clear_table(CHILD_TABLE_FIELD);

    items.forEach((item) => {
        const row = frm.add_child(CHILD_TABLE_FIELD);
        row.employee = item.employee || frm.doc.employee || "";
        row.name1 = item.employee_name || frm.__per_piece_parent_employee_name || "";
        row.product = item.item || "";
        row.process_type = item.process_type || "";
        row.process_size = item.process_size || PROCESS_SIZE_DEFAULT;
        row.rate = flt(item.rate, DECIMALS);
        row.__manual_rate = 0;
        row.qty = 0;
        row.amount = 0;
        row.from_date = frm.doc.from_date || null;
        row.to_date = frm.doc.to_date || null;
        row.po_number = frm.doc.po_number || null;
        row.item_group = frm.doc.item_group || null;
        row.delivery_note = frm.doc.delivery_note || null;
    });

    frm.refresh_field(CHILD_TABLE_FIELD);
    frm.trigger("recalc_amount_and_total");
    return Promise.resolve();
}

function resolveProcessRow(processRows, row) {
    if (!processRows || !processRows.length) return null;

    const currentType = (row.process_type || "").trim();
    const currentSize = (row.process_size || "").trim();
    const currentEmployee = (row.employee || "").trim();

    let matches = processRows.slice();
    if (currentType) {
        const typed = matches.filter((entry) => (entry.process_type || "").trim() === currentType);
        if (typed.length) matches = typed;
    }
    if (currentSize) {
        const sized = matches.filter(
            (entry) => ((entry.process_size || PROCESS_SIZE_DEFAULT).trim() === currentSize)
        );
        if (sized.length) matches = sized;
    }
    if (currentEmployee) {
        const employeeMatched = matches.filter(
            (entry) => (entry.employee || "").trim() === currentEmployee
        );
        if (employeeMatched.length) matches = employeeMatched;
    }

    return matches[0] || processRows[0];
}

function syncRowsToItemGroup(frm) {
    const rows = frm.doc[CHILD_TABLE_FIELD] || [];
    const autoProduct = getAutoGroupProduct(frm);
    const tasks = [];

    rows.forEach((row) => {
        if (row.product && !isGroupProductAllowed(frm, row.product)) {
            tasks.push(
                resetRowProductFields(frm, row).then(() => {
                    if (autoProduct) {
                        return frappe.model
                            .set_value(row.doctype, row.name, "product", autoProduct)
                            .then(() => applyItemDefaults(frm, row.doctype, row.name));
                    }
                })
            );
            return;
        }

        if (!row.product && autoProduct) {
            tasks.push(
                frappe.model
                    .set_value(row.doctype, row.name, "product", autoProduct)
                    .then(() => applyItemDefaults(frm, row.doctype, row.name))
            );
            return;
        }

        if (row.product) {
            tasks.push(applyItemDefaults(frm, row.doctype, row.name));
        }
    });

    return Promise.all(tasks).then(() => {
        frm.refresh_field(CHILD_TABLE_FIELD);
        frm.trigger("recalc_amount_and_total");
    }, () => {
        frm.refresh_field(CHILD_TABLE_FIELD);
        frm.trigger("recalc_amount_and_total");
    });
}

function applyItemDefaults(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row) return Promise.resolve();

    if (!row.process_size) {
        frappe.model.set_value(cdt, cdn, "process_size", PROCESS_SIZE_DEFAULT);
    }

    if (!row.product) {
        calculateRowAmount(row);
        frm.trigger("recalc_amount_and_total");
        return Promise.resolve();
    }

    return loadProcessRowsForItem(frm, row.product)
        .then((processRows) => {
            const processRow = resolveProcessRow(processRows, row);
            if (!processRow) return;
            if (processRow.process_type) {
                frappe.model.set_value(cdt, cdn, "process_type", processRow.process_type);
            }
            if (processRow.employee) {
                frappe.model.set_value(cdt, cdn, "employee", processRow.employee);
                frappe.model.set_value(cdt, cdn, "name1", processRow.employee_name || "");
            }
            frappe.model.set_value(
                cdt,
                cdn,
                "process_size",
                processRow.process_size || PROCESS_SIZE_DEFAULT
            );
            const itemRate = flt(processRow.rate, DECIMALS);
            // Keep saved/manual rate stable; only auto-fill when row rate is empty.
            if (itemRate > 0 && flt(row.rate, DECIMALS) <= 0) {
                frappe.model.set_value(cdt, cdn, "rate", itemRate);
            }
        })
        .then(() => {
            const updatedRow = locals[cdt][cdn] || row;
            calculateRowAmount(updatedRow);
            frappe.model.set_value(cdt, cdn, "amount", updatedRow.amount);
            frm.trigger("recalc_amount_and_total");
        }, () => {
            const updatedRow = locals[cdt][cdn] || row;
            calculateRowAmount(updatedRow);
            frappe.model.set_value(cdt, cdn, "amount", updatedRow.amount);
            frm.trigger("recalc_amount_and_total");
        });
}

frappe.ui.form.on("Per Piece Salary", {
    onload(frm) {
    if (isSubmittedDoc(frm)) {
      setProductQuery(frm);
      setDeliveryNoteQuery(frm);
      return;
    }
        if (frm.doc.load_by_item === undefined || frm.doc.load_by_item === null || frm.doc.load_by_item === "") {
            frm.set_value("load_by_item", 1);
        }
        setProductQuery(frm);
        setDeliveryNoteQuery(frm);
        loadParentEmployeeName(frm).then(() => {
            return loadItemsForGroup(frm);
        }).then(() => {
            if ((frm.doc.delivery_note || "").trim()) {
                return loadRowsFromDeliveryNote(frm, false);
            }
            populateRowsFromGroup(frm);
            frm.trigger("sync_parent_to_child");
            return syncRowsToItemGroup(frm);
        });
    },

    refresh(frm) {
        setProductQuery(frm);
        setDeliveryNoteQuery(frm);
        const btn = frm.add_custom_button(__("Per Piece Salary Report"), () => {
            window.open(REPORT_ROUTE, "_blank");
        });
        btn.addClass("btn-primary");
        if (!isSubmittedDoc(frm)) {
            frm.add_custom_button(__("Load From Delivery Note"), () => {
                loadRowsFromDeliveryNote(frm, true);
            }, __("Actions"));
        }
    },

    validate(frm) {
      if (isSubmittedDoc(frm)) return;
        validateDateRange(frm);
        frm.trigger("sync_parent_to_child");
        frm.trigger("recalc_amount_and_total");
    },

    from_date(frm) {
      if (isSubmittedDoc(frm)) return;
        validateDateRange(frm);
        frm.trigger("sync_parent_to_child");
    },

    to_date(frm) {
      if (isSubmittedDoc(frm)) return;
        validateDateRange(frm);
        frm.trigger("sync_parent_to_child");
    },

    po_number(frm) {
      if (isSubmittedDoc(frm)) return;
        frm.trigger("sync_parent_to_child");
    },

    delivery_note(frm) {
      if (isSubmittedDoc(frm)) return;
        frm.trigger("sync_parent_to_child");
        if ((frm.doc.delivery_note || "").trim()) {
            loadRowsFromDeliveryNote(frm, false);
        }
    },

    employee(frm) {
      if (isSubmittedDoc(frm)) return;
        loadParentEmployeeName(frm).then(() => {
            frm.trigger("sync_parent_to_child");
            frm.refresh_field(CHILD_TABLE_FIELD);
        });
    },

    item_group(frm) {
      if (isSubmittedDoc(frm)) return;
        setProductQuery(frm);
        if (frm.doc.item) {
            frm.set_value("item", "");
        }
        frm.__per_piece_item_process_map = {};
        frm.refresh_field("item");
        loadItemsForGroup(frm).then(() => {
            populateRowsFromGroup(frm, true);
            frm.refresh_field(CHILD_TABLE_FIELD);
            return syncRowsToItemGroup(frm);
        });
    },

    item(frm) {
      if (isSubmittedDoc(frm)) return;
        setProductQuery(frm);
        loadItemsForGroup(frm).then(() => {
            populateRowsFromGroup(frm, true);
            frm.refresh_field(CHILD_TABLE_FIELD);
            return syncRowsToItemGroup(frm);
        });
    },

    load_by_item(frm) {
      if (isSubmittedDoc(frm)) return;
        setProductQuery(frm);
        loadItemsForGroup(frm).then(() => {
            populateRowsFromGroup(frm, true);
            frm.refresh_field(CHILD_TABLE_FIELD);
            return syncRowsToItemGroup(frm);
        });
    },

    sync_parent_to_child(frm) {
      if (isSubmittedDoc(frm)) return;
        const rows = frm.doc[CHILD_TABLE_FIELD] || [];
        if (!rows.length) return;

        const fromDate = frm.doc.from_date || null;
        const toDate = frm.doc.to_date || null;
        const poNumber = frm.doc.po_number || null;
        const itemGroup = frm.doc.item_group || null;
        const deliveryNote = frm.doc.delivery_note || null;

        applyParentEmployeeToRows(frm);
        rows.forEach((row) => {
            row.from_date = fromDate;
            row.to_date = toDate;
            row.po_number = poNumber;
            row.item_group = itemGroup;
            row.delivery_note = deliveryNote;
            if (!row.process_size) {
                row.process_size = PROCESS_SIZE_DEFAULT;
            }
            calculateRowAmount(row);
        });

        frm.refresh_field(CHILD_TABLE_FIELD);
        frm.trigger("recalc_amount_and_total");
    },

	    recalc_amount_and_total(frm) {
	      if (isSubmittedDoc(frm)) return;
	        const rows = frm.doc[CHILD_TABLE_FIELD] || [];
	        let totalAmount = 0;
	        let totalQty = 0;
	        let totalBookedAmount = 0;
	        let totalPaidAmount = 0;
	        let totalUnpaidAmount = 0;
	        let totalAllowance = 0;
	        let totalAdvanceDeduction = 0;
	        let totalOtherDeduction = 0;
	        let totalNetAmount = 0;

	        rows.forEach((row) => {
	            if (!row.process_size) {
	                row.process_size = PROCESS_SIZE_DEFAULT;
	            }
	            calculateRowAmount(row);
	            totalAmount += flt(row.amount, DECIMALS);
	            totalQty += flt(row.qty, DECIMALS);
	            totalBookedAmount += flt(row.booked_amount, DECIMALS);
	            totalPaidAmount += flt(row.paid_amount, DECIMALS);
	            totalUnpaidAmount += flt(row.unpaid_amount, DECIMALS);
	            totalAllowance += flt(row.allowance, DECIMALS);
	            totalAdvanceDeduction += flt(row.advance_deduction, DECIMALS);
	            totalOtherDeduction += flt(row.other_deduction, DECIMALS);
	            totalNetAmount += flt(row.net_amount, DECIMALS);
	        });

	        frm.refresh_field(CHILD_TABLE_FIELD);
	        frm.set_value("total_amount", flt(totalAmount, DECIMALS));
	        frm.set_value("total_qty", flt(totalQty, DECIMALS));
	        if (frm.fields_dict.total_booked_amount) {
	            frm.set_value("total_booked_amount", flt(totalBookedAmount, DECIMALS));
	        }
	        if (frm.fields_dict.total_paid_amount) {
	            frm.set_value("total_paid_amount", flt(totalPaidAmount, DECIMALS));
	        }
	        if (frm.fields_dict.total_unpaid_amount) {
	            frm.set_value("total_unpaid_amount", flt(totalUnpaidAmount, DECIMALS));
	        }
	        if (frm.fields_dict.total_allowance) {
	            frm.set_value("total_allowance", flt(totalAllowance, DECIMALS));
	        }
	        if (frm.fields_dict.total_allowance_amount) {
	            frm.set_value("total_allowance_amount", flt(totalAllowance, DECIMALS));
	        }
	        if (frm.fields_dict.total_advance_deduction) {
	            frm.set_value("total_advance_deduction", flt(totalAdvanceDeduction, DECIMALS));
	        }
	        if (frm.fields_dict.total_advance_deduction_amount) {
	            frm.set_value("total_advance_deduction_amount", flt(totalAdvanceDeduction, DECIMALS));
	        }
	        if (frm.fields_dict.total_other_deduction) {
	            frm.set_value("total_other_deduction", flt(totalOtherDeduction, DECIMALS));
	        }
	        if (frm.fields_dict.total_other_deduction_amount) {
	            frm.set_value("total_other_deduction_amount", flt(totalOtherDeduction, DECIMALS));
	        }
	        if (frm.fields_dict.total_net_amount) {
	            frm.set_value("total_net_amount", flt(totalNetAmount, DECIMALS));
	        }
	        if (frm.fields_dict.total_net_salary) {
	            frm.set_value("total_net_salary", flt(totalNetAmount, DECIMALS));
	        }
	    },

    perpiece_add(frm) {
      if (isSubmittedDoc(frm)) return;
        frm.trigger("sync_parent_to_child");
        loadItemsForGroup(frm).then(() => syncRowsToItemGroup(frm));
    },

    perpiece_remove(frm) {
      if (isSubmittedDoc(frm)) return;
        frm.trigger("recalc_amount_and_total");
    },
});

frappe.ui.form.on("Per Piece", {
    form_render(frm, cdt, cdn) {
      if (isSubmittedDoc(frm)) return;
        const row = locals[cdt][cdn];
        row.from_date = frm.doc.from_date || null;
        row.to_date = frm.doc.to_date || null;
        row.po_number = frm.doc.po_number || null;
        row.item_group = frm.doc.item_group || null;
        row.delivery_note = frm.doc.delivery_note || null;
        if (!row.process_size) {
            frappe.model.set_value(cdt, cdn, "process_size", PROCESS_SIZE_DEFAULT);
        }
        loadItemsForGroup(frm).then(() => {
            const autoProduct = getAutoGroupProduct(frm);
            if (!row.product && autoProduct) {
                frappe.model
                    .set_value(cdt, cdn, "product", autoProduct)
                    .then(() => applyItemDefaults(frm, cdt, cdn));
                return;
            }
            calculateRowAmount(row);
            frm.trigger("recalc_amount_and_total");
        });
    },

    product(frm, cdt, cdn) {
      if (isSubmittedDoc(frm)) return;
        const row = locals[cdt][cdn];
        if (row) {
            row.__manual_rate = 0;
            row.rate = 0;
        }
        applyItemDefaults(frm, cdt, cdn);
    },

    process_type(frm, cdt, cdn) {
      if (isSubmittedDoc(frm)) return;
        const row = locals[cdt][cdn];
        if (row) {
            row.__manual_rate = 0;
            row.rate = 0;
        }
        applyItemDefaults(frm, cdt, cdn);
    },

    qty(frm, cdt, cdn) {
      if (isSubmittedDoc(frm)) return;
        const row = locals[cdt][cdn];
        calculateRowAmount(row);
        frappe.model.set_value(cdt, cdn, "amount", row.amount);
        frm.trigger("recalc_amount_and_total");
    },

    rate(frm, cdt, cdn) {
      if (isSubmittedDoc(frm)) return;
        const row = locals[cdt][cdn];
        if (row) row.__manual_rate = 1;
        calculateRowAmount(row);
        frappe.model.set_value(cdt, cdn, "amount", row.amount);
        frm.trigger("recalc_amount_and_total");
    },

    process_size(frm, cdt, cdn) {
      if (isSubmittedDoc(frm)) return;
        const row = locals[cdt][cdn];
        if (!row.process_size) {
            frappe.model.set_value(cdt, cdn, "process_size", PROCESS_SIZE_DEFAULT);
        }
    },
});
"""


def _update_doc(doctype: str, name: str, updates: dict, results: list[str]) -> None:
	if not frappe.db.exists(doctype, name):
		results.append(f"Skipped: {doctype} '{name}' does not exist")
		return

	doc = frappe.get_doc(doctype, name)
	changed = False
	for fieldname, value in updates.items():
		if doc.get(fieldname) != value:
			doc.set(fieldname, value)
			changed = True

	if changed:
		doc.save(ignore_permissions=True)
		results.append(f"Updated: {doctype} '{name}'")
	else:
		results.append(f"No change: {doctype} '{name}'")


def _upsert_doc(doctype: str, name: str, updates: dict, results: list[str]) -> None:
	if frappe.db.exists(doctype, name):
		_update_doc(doctype, name, updates, results)
		return

	doc = frappe.new_doc(doctype)
	doc.name = name
	for fieldname, value in updates.items():
		doc.set(fieldname, value)
	doc.insert(ignore_permissions=True)
	results.append(f"Created: {doctype} '{name}'")


def _ensure_custom_field(
	fieldname: str,
	label: str,
	fieldtype: str,
	options: str | None,
	insert_after: str,
	results: list[str],
	doctype: str = "Per Piece",
	read_only: int = 1,
	in_list_view: int = 1,
	default: str | None = None,
	reqd: int = 0,
	no_copy: int = 1,
	allow_fieldtype_override: int = 0,
) -> None:
	# If field already exists directly on DocType, do not create/update Custom Field.
	try:
		meta = frappe.get_meta(doctype)
		if meta.has_field(fieldname):
			inline_exists = False
			try:
				doc = frappe.get_doc("DocType", doctype)
				inline_exists = any(
					str((f or {}).get("fieldname") or "").strip() == fieldname for f in (doc.fields or [])
				)
			except Exception:
				inline_exists = False
			if inline_exists:
				results.append(f"No change: Inline DocField '{doctype}.{fieldname}' already present")
				return
	except Exception:
		pass

	existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
	payload = {
		"dt": doctype,
		"fieldname": fieldname,
		"label": label,
		"fieldtype": fieldtype,
		"insert_after": insert_after,
		"read_only": read_only,
		"in_list_view": in_list_view,
		"no_copy": no_copy,
		"reqd": reqd,
	}
	if options is not None:
		payload["options"] = options
	if default is not None:
		payload["default"] = default

	if existing:
		doc = frappe.get_doc("Custom Field", existing)
		force_override = bool(allow_fieldtype_override and doc.get("fieldtype") != fieldtype)
		if force_override:
			for key, value in payload.items():
				frappe.db.set_value("Custom Field", existing, key, value, update_modified=False)
			results.append(f"Updated (force): Custom Field '{doctype}.{fieldname}'")
			return

		changed = False
		skipped_fieldtype = False
		for key, value in payload.items():
			if key == "fieldtype" and doc.get("fieldtype") != value and not allow_fieldtype_override:
				skipped_fieldtype = True
				continue
			if doc.get(key) != value:
				doc.set(key, value)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
			if skipped_fieldtype:
				results.append(f"Updated (except fieldtype): Custom Field '{doctype}.{fieldname}'")
			else:
				results.append(f"Updated: Custom Field '{doctype}.{fieldname}'")
		else:
			if skipped_fieldtype:
				results.append(f"Skipped fieldtype update: Custom Field '{doctype}.{fieldname}'")
			else:
				results.append(f"No change: Custom Field '{doctype}.{fieldname}'")
	else:
		doc = frappe.new_doc("Custom Field")
		for key, value in payload.items():
			doc.set(key, value)
		doc.insert(ignore_permissions=True)
		results.append(f"Created: Custom Field '{doctype}.{fieldname}'")


def _delete_custom_field(doctype: str, fieldname: str, results: list[str]) -> None:
	existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
	if not existing:
		results.append(f"No change: Custom Field '{doctype}.{fieldname}' already absent")
		return
	frappe.delete_doc("Custom Field", existing, ignore_permissions=True, force=1)
	results.append(f"Deleted: Custom Field '{doctype}.{fieldname}'")


def _ensure_inline_fields_on_custom_doctype(
	doctype: str,
	field_specs: list[dict],
	results: list[str],
) -> bool:
	"""Ensure fields exist directly in DocType.fields when the DocType itself is custom.

	Returns True when inline DocField strategy was applied, False otherwise.
	"""
	if not frappe.db.exists("DocType", doctype):
		return False
	doc = frappe.get_doc("DocType", doctype)
	if not int(doc.get("custom") or 0):
		return False

	existing = {str((f or {}).get("fieldname") or "").strip(): f for f in (doc.fields or [])}
	changed = False
	for spec in field_specs:
		fn = str((spec or {}).get("fieldname") or "").strip()
		if not fn:
			continue
		if fn in existing:
			# keep important properties aligned
			f = existing[fn]
			for k in ("label", "fieldtype", "read_only", "in_list_view", "no_copy", "precision"):
				if k in spec and str(f.get(k) or "") != str(spec.get(k) or ""):
					f.set(k, spec.get(k))
					changed = True
			continue
		doc.append("fields", spec)
		changed = True
		results.append(f"Created inline DocField: {doctype}.{fn}")

	if changed:
		doc.save(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)
		results.append(f"Updated: DocType '{doctype}' inline fields")
	else:
		results.append(f"No change: DocType '{doctype}' inline fields")
	return True


def _delete_inline_field_from_custom_doctype(doctype: str, fieldname: str, results: list[str]) -> None:
	if not frappe.db.exists("DocType", doctype):
		results.append(f"No change: DocType '{doctype}' not found for inline delete")
		return
	doc = frappe.get_doc("DocType", doctype)
	if not int(doc.get("custom") or 0):
		results.append(f"No change: DocType '{doctype}' is not custom (inline delete skipped)")
		return
	fields = list(doc.fields or [])
	next_fields = [f for f in fields if str((f or {}).get("fieldname") or "") != fieldname]
	if len(next_fields) == len(fields):
		results.append(f"No change: Inline DocField '{doctype}.{fieldname}' already absent")
		return
	doc.fields = next_fields
	doc.save(ignore_permissions=True)
	frappe.clear_cache(doctype=doctype)
	results.append(f"Deleted inline DocField: {doctype}.{fieldname}")


def _ensure_per_piece_salary_total_fields(results: list[str]) -> None:
	specs = [
		{
			"fieldname": "total_booked_amount",
			"label": "Total Booked Amount",
			"fieldtype": "Float",
			"precision": "2",
			"read_only": 1,
			"in_list_view": 0,
			"no_copy": 1,
		},
		{
			"fieldname": "total_paid_amount",
			"label": "Total Paid Amount",
			"fieldtype": "Float",
			"precision": "2",
			"read_only": 1,
			"in_list_view": 0,
			"no_copy": 1,
		},
		{
			"fieldname": "total_unpaid_amount",
			"label": "Total Unpaid Amount",
			"fieldtype": "Float",
			"precision": "2",
			"read_only": 1,
			"in_list_view": 0,
			"no_copy": 1,
		},
	]

	used_inline = _ensure_inline_fields_on_custom_doctype("Per Piece Salary", specs, results)
	if used_inline:
		for spec in specs:
			_delete_custom_field("Per Piece Salary", spec["fieldname"], results)
		for old_fn in (
			"total_allowance_amount",
			"total_advance_deduction_amount",
			"total_other_deduction_amount",
			"total_net_salary",
		):
			_delete_custom_field("Per Piece Salary", old_fn, results)
			_delete_inline_field_from_custom_doctype("Per Piece Salary", old_fn, results)
		return

	# Non-custom/base DocType fallback: keep as Custom Fields
	for spec in specs:
		_ensure_custom_field(
			spec["fieldname"],
			spec["label"],
			spec["fieldtype"],
			None,
			"total_amount",
			results,
			doctype="Per Piece Salary",
			read_only=int(spec.get("read_only") or 0),
			in_list_view=int(spec.get("in_list_view") or 0),
			no_copy=int(spec.get("no_copy") or 0),
		)
	# User keeps these totals directly in DocType; do not keep duplicate Custom Fields.
	_delete_custom_field("Per Piece Salary", "total_allowance", results)
	_delete_custom_field("Per Piece Salary", "total_advance_deduction", results)
	_delete_custom_field("Per Piece Salary", "total_other_deduction", results)
	_delete_custom_field("Per Piece Salary", "total_net_amount", results)
	_delete_custom_field("Per Piece Salary", "total_allowance_amount", results)


def _ensure_inline_per_piece_and_salary_fields(results: list[str]) -> None:
	per_piece_specs = [
		{
			"fieldname": "jv_status",
			"label": "JV Status",
			"fieldtype": "Select",
			"options": "Pending\nPosted",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "jv_entry_no",
			"label": "JV Entry No",
			"fieldtype": "Link",
			"options": "Journal Entry",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "jv_line_remark",
			"label": "JV Line Remark",
			"fieldtype": "Small Text",
			"read_only": 1,
			"in_list_view": 0,
			"no_copy": 1,
		},
		{
			"fieldname": "booked_amount",
			"label": "Booked Amount",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
			"precision": "2",
		},
		{
			"fieldname": "allowance",
			"label": "Allowance",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
			"precision": "2",
		},
		{
			"fieldname": "advance_deduction",
			"label": "Advance Deduction",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
			"precision": "2",
		},
		{
			"fieldname": "other_deduction",
			"label": "Other Deduction",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
			"precision": "2",
		},
		{
			"fieldname": "net_amount",
			"label": "Net Amount",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
			"precision": "2",
		},
		{
			"fieldname": "paid_amount",
			"label": "Paid Amount",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
			"precision": "2",
		},
		{
			"fieldname": "unpaid_amount",
			"label": "Unpaid Amount",
			"fieldtype": "Float",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
			"precision": "2",
		},
		{
			"fieldname": "payment_status",
			"label": "Payment Status",
			"fieldtype": "Select",
			"options": "Unpaid\nPartly Paid\nPaid",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "payment_jv_no",
			"label": "Payment JV",
			"fieldtype": "Link",
			"options": "Journal Entry",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "payment_refs",
			"label": "Payment Refs",
			"fieldtype": "Small Text",
			"read_only": 1,
			"in_list_view": 0,
			"no_copy": 1,
		},
		{
			"fieldname": "payment_line_remark",
			"label": "Payment Remark",
			"fieldtype": "Small Text",
			"read_only": 1,
			"in_list_view": 0,
			"no_copy": 1,
		},
		{
			"fieldname": "sales_order",
			"label": "Sales Order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"read_only": 0,
			"in_list_view": 1,
			"no_copy": 0,
		},
		{
			"fieldname": "delivery_note",
			"label": "Delivery Note",
			"fieldtype": "Link",
			"options": "Delivery Note",
			"read_only": 1,
			"in_list_view": 1,
			"no_copy": 0,
		},
	]
	per_piece_salary_specs = [
		{
			"fieldname": "pp_filters_section_break",
			"label": "",
			"fieldtype": "Section Break",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "item_group",
			"label": "Item Group",
			"fieldtype": "Link",
			"options": "Item Group",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "pp_filters_col_break_1",
			"label": "",
			"fieldtype": "Column Break",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "item",
			"label": "Item",
			"fieldtype": "Link",
			"options": "Item",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "delivery_note",
			"label": "Delivery Note",
			"fieldtype": "Link",
			"options": "Delivery Note",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "pp_filters_col_break_2",
			"label": "",
			"fieldtype": "Column Break",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "employee",
			"label": "Employee",
			"fieldtype": "Link",
			"options": "Employee",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "company",
			"label": "Company",
			"fieldtype": "Link",
			"options": "Company",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "pp_filters_col_break_3",
			"label": "",
			"fieldtype": "Column Break",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
		{
			"fieldname": "load_by_item",
			"label": "Load By Item",
			"fieldtype": "Check",
			"read_only": 0,
			"in_list_view": 0,
			"no_copy": 0,
		},
	]

	per_piece_used_inline = _ensure_inline_fields_on_custom_doctype("Per Piece", per_piece_specs, results)
	if per_piece_used_inline:
		for spec in per_piece_specs:
			_delete_custom_field("Per Piece", spec["fieldname"], results)

	per_piece_salary_used_inline = _ensure_inline_fields_on_custom_doctype(
		"Per Piece Salary", per_piece_salary_specs, results
	)
	if per_piece_salary_used_inline:
		for spec in per_piece_salary_specs:
			_delete_custom_field("Per Piece Salary", spec["fieldname"], results)


def _ensure_field_property_setter(
	doctype: str,
	fieldname: str,
	property_name: str,
	value: str,
	property_type: str,
	results: list[str],
) -> None:
	try:
		meta = frappe.get_meta(doctype)
	except Exception:
		results.append(f"Skipped: Property Setter for {doctype}.{fieldname} ({property_name})")
		return
	if not meta.has_field(fieldname):
		results.append(f"Skipped: Field {doctype}.{fieldname} not found")
		return

	existing = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": doctype,
			"doctype_or_field": "DocField",
			"field_name": fieldname,
			"property": property_name,
		},
		"name",
	)

	payload = {
		"doc_type": doctype,
		"doctype_or_field": "DocField",
		"field_name": fieldname,
		"property": property_name,
		"property_type": property_type,
		"value": value,
	}

	if existing:
		doc = frappe.get_doc("Property Setter", existing)
		changed = False
		for key, val in payload.items():
			if str(doc.get(key) or "") != str(val or ""):
				doc.set(key, val)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
			results.append(f"Updated: Property Setter {doctype}.{fieldname}.{property_name}")
		else:
			results.append(f"No change: Property Setter {doctype}.{fieldname}.{property_name}")
	else:
		doc = frappe.new_doc("Property Setter")
		for key, val in payload.items():
			doc.set(key, val)
		doc.insert(ignore_permissions=True)
		results.append(f"Created: Property Setter {doctype}.{fieldname}.{property_name}")


def _ensure_doctype_property_setter(
	doctype: str,
	property_name: str,
	value: str,
	property_type: str,
	results: list[str],
) -> None:
	existing = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": doctype,
			"doctype_or_field": "DocType",
			"field_name": doctype,
			"property": property_name,
		},
		"name",
	)

	payload = {
		"doc_type": doctype,
		"doctype_or_field": "DocType",
		"field_name": doctype,
		"property": property_name,
		"property_type": property_type,
		"value": value,
	}

	if existing:
		doc = frappe.get_doc("Property Setter", existing)
		changed = False
		for key, val in payload.items():
			if str(doc.get(key) or "") != str(val or ""):
				doc.set(key, val)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
			results.append(f"Updated: Property Setter {doctype}.{property_name}")
		else:
			results.append(f"No change: Property Setter {doctype}.{property_name}")
	else:
		doc = frappe.new_doc("Property Setter")
		for key, val in payload.items():
			doc.set(key, val)
		doc.insert(ignore_permissions=True)
		results.append(f"Created: Property Setter {doctype}.{property_name}")


def _migrate_jv_status(results: list[str]) -> None:
	old_count = frappe.db.count("Per Piece", {"jv_status": "Accounted"})
	if not old_count:
		results.append("No change: JV Status values already aligned")
		return
	frappe.db.sql("UPDATE `tabPer Piece` SET jv_status = 'Posted' WHERE jv_status = 'Accounted'")
	results.append("Updated: Migrated " + str(old_count) + " row(s) from JV Status Accounted to Posted")


def _ensure_per_piece_field_links(results: list[str]) -> None:
	# Older setups had fetch_from pointing to removed Item fields, which blocks insert/save.
	changed = False
	for fieldname in ("process_type", "process_size", "rate"):
		custom_field_name = frappe.db.get_value(
			"Custom Field",
			{"dt": "Per Piece", "fieldname": fieldname},
			"name",
		)
		if custom_field_name:
			custom_fetch_from = frappe.db.get_value("Custom Field", custom_field_name, "fetch_from") or ""
			if str(custom_fetch_from).strip():
				frappe.db.set_value(
					"Custom Field", custom_field_name, "fetch_from", "", update_modified=False
				)
				changed = True
		docfield_name = frappe.db.get_value(
			"DocField",
			{"parent": "Per Piece", "parenttype": "DocType", "fieldname": fieldname},
			"name",
		)
		if not docfield_name:
			continue
		fetch_from_val = frappe.db.get_value("DocField", docfield_name, "fetch_from") or ""
		if str(fetch_from_val).strip():
			frappe.db.set_value("DocField", docfield_name, "fetch_from", "", update_modified=False)
			changed = True
	if changed:
		frappe.clear_cache(doctype="Per Piece")
		results.append("Updated: Cleared invalid Fetch From on Per Piece process/rate fields")
	else:
		results.append("No change: Per Piece process field links already valid")


def _update_print_format(results: list[str]) -> None:
	if not frappe.db.exists("Print Format", "Per Piece Print"):
		results.append("Skipped: Print Format 'Per Piece Print' does not exist")
		return

	doc = frappe.get_doc("Print Format", "Per Piece Print")
	changed = False
	landscape_css = (
		"@media print {\n"
		"  @page { size: A4 landscape; margin: 8mm; }\n"
		"  .print-format table { font-size: 10px; }\n"
		"  .print-format td, .print-format th { padding: 3px 5px !important; }\n"
		"}\n"
		".pp-print-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;}\n"
		".pp-print-company{font-size:22px;font-weight:700;}\n"
		".pp-print-meta{font-size:12px;line-height:1.6;}\n"
		".pp-print-table{width:100%;border-collapse:collapse;margin-top:8px;}\n"
		".pp-print-table th,.pp-print-table td{border:1px solid #111;padding:4px 6px;}\n"
		".pp-print-table th{background:#f1f5f9;}\n"
		".pp-print-total td{font-weight:700;background:#f8fafc;}\n"
		".pp-print-sign{margin-top:20px;width:100%;border-collapse:collapse;}\n"
		".pp-print-sign td{padding-top:30px;width:33.33%;text-align:center;}\n"
		".pp-sign-line{border-top:1px solid #111;padding-top:6px;display:inline-block;min-width:160px;}\n"
	)
	current_css = doc.css or ""
	if landscape_css.strip() not in current_css:
		doc.css = current_css + ("\n" if current_css else "") + landscape_css
		changed = True
	html = """
<div class="print-format">
  <div class="pp-print-head">
    <div>
      <div class="pp-print-company">{{ frappe.defaults.get_user_default("Company") or "" }}</div>
      <div style="font-size:16px;font-weight:700;margin-top:4px;">Per Piece Salary</div>
    </div>
    <div class="pp-print-meta">
      <div><strong>PO Number:</strong> {{ doc.po_number or "-" }}</div>
      <div><strong>From Date:</strong> {{ frappe.format(doc.from_date, {"fieldtype":"Date"}) if doc.from_date else "-" }}</div>
      <div><strong>To Date:</strong> {{ frappe.format(doc.to_date, {"fieldtype":"Date"}) if doc.to_date else "-" }}</div>
    </div>
  </div>

  <table class="pp-print-table">
    <thead>
      <tr>
        <th>Employee</th>
        <th>Name</th>
        <th>Product</th>
        <th>Process Type</th>
        <th>Process Size</th>
        <th>Qty</th>
        <th>Rate</th>
        <th>Amount</th>
      </tr>
    </thead>
    <tbody>
      {% set ns = namespace(qty=0, amount=0) %}
      {% for row in doc.perpiece %}
      {% set ns.qty = ns.qty + (row.qty or 0) %}
      {% set ns.amount = ns.amount + (row.amount or 0) %}
      <tr>
        <td>{{ row.employee or "" }}</td>
        <td>{{ row.name1 or "" }}</td>
        <td>{{ row.product or "" }}</td>
        <td>{{ row.process_type or "" }}</td>
        <td>{{ row.process_size or "No Size" }}</td>
        <td style="text-align:right;">{{ frappe.format(row.qty, {"fieldtype":"Float","precision":2}) }}</td>
        <td style="text-align:right;">{{ frappe.format(row.rate, {"fieldtype":"Float","precision":2}) }}</td>
        <td style="text-align:right;">{{ frappe.format(row.amount, {"fieldtype":"Currency"}) }}</td>
      </tr>
      {% endfor %}
      <tr class="pp-print-total">
        <td colspan="5">Total</td>
        <td style="text-align:right;">{{ frappe.format(ns.qty, {"fieldtype":"Float","precision":2}) }}</td>
        <td></td>
        <td style="text-align:right;">{{ frappe.format(ns.amount, {"fieldtype":"Currency"}) }}</td>
      </tr>
    </tbody>
  </table>

  <table class="pp-print-sign">
    <tr>
      <td><span class="pp-sign-line">Created By</span></td>
      <td><span class="pp-sign-line">Approved By</span></td>
      <td><span class="pp-sign-line">Received By</span></td>
    </tr>
  </table>
</div>
""".strip()
	if (doc.html or "").strip() != html:
		doc.custom_format = 1
		doc.print_format_builder = 0
		doc.html = html
		doc.format_data = "[]"
		changed = True
	if changed:
		doc.save(ignore_permissions=True)
		results.append("Updated: Print Format 'Per Piece Print'")
	else:
		results.append("No change: Print Format 'Per Piece Print'")


def _update_web_page(results: list[str]) -> None:
	web_page_html = _resolve_per_piece_web_page_html(results)
	_upsert_doc(
		"Web Page",
		"per-piece-report",
		{
			"title": "Per Piece Salary Report",
			"route": "per-piece-report",
			"published": 1,
			"content_type": "HTML",
			"main_section_html": web_page_html,
		},
		results,
	)


def _resolve_per_piece_web_page_html(results: list[str]) -> str:
	html_path = Path(
		frappe.get_app_path(
			"per_piece_payroll",
			"public",
			"html",
			"per_piece_report_main_section.html",
		)
	)
	if html_path.exists():
		return html_path.read_text(encoding="utf-8")
	frappe.throw(f"Required web page template file missing: {html_path}")


def _delete_doc_if_exists(doctype: str, name: str, results: list[str]) -> None:
	if not frappe.db.exists(doctype, name):
		results.append(f"No change: {doctype} '{name}' already absent")
		return
	try:
		frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		results.append(f"Deleted: {doctype} '{name}'")
	except Exception:
		# Fallback: disable if hard delete fails due to dependencies
		if doctype == "Web Page":
			frappe.db.set_value(doctype, name, "published", 0, update_modified=False)
			results.append(f"Disabled: {doctype} '{name}' (delete failed)")
		elif doctype == "Client Script":
			frappe.db.set_value(doctype, name, "enabled", 0, update_modified=False)
			results.append(f"Disabled: {doctype} '{name}' (delete failed)")
		elif doctype == "Server Script":
			frappe.db.set_value(doctype, name, "disabled", 1, update_modified=False)
			results.append(f"Disabled: {doctype} '{name}' (delete failed)")
		else:
			raise


def _cleanup_legacy_ui_docs(results: list[str]) -> None:
	# Legacy Web Page + UI scripts are replaced by app-backed Desk pages and app methods.
	_delete_doc_if_exists("Web Page", "per-piece-report", results)
	for name in (
		"get_per_piece_salary_report",
		"create_per_piece_salary_entry",
		"create_per_piece_salary_jv",
		"cancel_per_piece_salary_jv",
		"create_per_piece_salary_payment_jv",
		"cancel_per_piece_salary_payment_jv",
	):
		_delete_doc_if_exists("Server Script", name, results)
	_delete_doc_if_exists("Client Script", "Per Piece Salary Auto Load", results)
	_delete_doc_if_exists("Client Script", "Per Piece Salary Update Child", results)


def _ensure_core_doctypes(results: list[str]) -> None:
	required = ["Per Piece", "Per Piece Salary"]
	missing = [d for d in required if not frappe.db.exists("DocType", d)]
	if not missing:
		return

	fixture_path = frappe.get_app_path("per_piece_payroll", "per_piece_payroll", "fixtures", "doctype.json")
	try:
		fixture_rows = json.loads(frappe.safe_decode(open(fixture_path, "rb").read()))
	except Exception:
		results.append("Skipped: Could not read doctype fixture for core doctypes")
		return

	row_map = {}
	for row in fixture_rows or []:
		if (row or {}).get("doctype") == "DocType" and (row or {}).get("name") in required:
			row_map[row.get("name")] = row

	for doctype_name in required:
		if frappe.db.exists("DocType", doctype_name):
			continue
		raw = row_map.get(doctype_name)
		if not raw:
			results.append(f"Skipped: Doctype fixture row not found for '{doctype_name}'")
			continue

		doc = json.loads(json.dumps(raw))
		for k in [
			"_user_tags",
			"_comments",
			"_assign",
			"_liked_by",
			"_last_update",
			"modified",
			"modified_by",
			"creation",
			"owner",
		]:
			if k in doc:
				del doc[k]
		doc["name"] = doctype_name
		doc["module"] = "Per Piece Payroll"

		for table_key in ["fields", "permissions", "links", "actions", "states"]:
			rows = doc.get(table_key) or []
			for child in rows:
				if not isinstance(child, dict):
					continue
				for ck in [
					"_user_tags",
					"_comments",
					"_assign",
					"_liked_by",
					"_last_update",
					"modified",
					"modified_by",
					"creation",
					"owner",
					"parent",
					"parentfield",
					"parenttype",
					"idx",
					"name",
					"docstatus",
				]:
					if ck in child:
						del child[ck]

		try:
			frappe.get_doc(doc).insert(ignore_permissions=True, ignore_links=True)
			results.append(f"Created: DocType '{doctype_name}' from fixture")
		except Exception:
			results.append(f"Failed: Could not create DocType '{doctype_name}' from fixture")


def _ensure_item_process_size_doctype_and_field(results: list[str]) -> None:
	child_doctype = "PRD Process and Sizes"
	if not frappe.db.exists("DocType", child_doctype):
		doc = {
			"doctype": "DocType",
			"name": child_doctype,
			"module": "Per Piece Payroll",
			"custom": 1,
			"istable": 1,
			"editable_grid": 1,
			"track_changes": 0,
			"autoname": "hash",
			"engine": "InnoDB",
			"fields": [
				{
					"fieldname": "employee",
					"label": "Employee",
					"fieldtype": "Link",
					"options": "Employee",
					"in_list_view": 1,
					"reqd": 0,
				},
				{
					"fieldname": "process_type",
					"label": "Process Type",
					"fieldtype": "Select",
					"options": "Cutting\nStitching\nQuilting\nPacking\nChecking",
					"in_list_view": 1,
					"reqd": 0,
				},
				{
					"fieldname": "process_size",
					"label": "Process Size",
					"fieldtype": "Select",
					"options": "No Size\nSingle\nDouble\nKing\nSupper King",
					"in_list_view": 1,
					"default": "No Size",
					"reqd": 0,
				},
				{
					"fieldname": "rate",
					"label": "Rate",
					"fieldtype": "Float",
					"in_list_view": 1,
					"default": "0",
					"reqd": 0,
				},
			],
			"permissions": [
				{
					"role": "System Manager",
					"read": 1,
					"write": 1,
					"create": 1,
					"delete": 1,
					"print": 1,
					"export": 1,
					"share": 1,
					"report": 1,
				}
			],
		}
		try:
			frappe.get_doc(doc).insert(ignore_permissions=True)
			results.append("Created: DocType 'PRD Process and Sizes'")
		except Exception:
			results.append("Failed: Could not create DocType 'PRD Process and Sizes'")
			return
	else:
		results.append("No change: DocType 'PRD Process and Sizes'")

	item_table_exists = frappe.db.exists(
		"DocField", {"parent": "Item", "fieldname": "custom_prd_process_and_sizes"}
	)
	if item_table_exists:
		results.append("No change: DocField 'Item.custom_prd_process_and_sizes'")
	else:
		_ensure_custom_field(
			"custom_prd_process_and_sizes",
			"PRD Process and Sizes",
			"Table",
			"PRD Process and Sizes",
			"item_group",
			results,
			doctype="Item",
			read_only=0,
			in_list_view=0,
			no_copy=0,
			allow_fieldtype_override=1,
		)

	process_employee_exists = frappe.db.exists(
		"DocField", {"parent": "PRD Process and Sizes", "fieldname": "employee"}
	)
	if process_employee_exists:
		results.append("No change: DocField 'PRD Process and Sizes.employee'")
	else:
		_ensure_custom_field(
			"employee",
			"Employee",
			"Link",
			"Employee",
			"rate",
			results,
			doctype="PRD Process and Sizes",
			read_only=0,
			in_list_view=1,
			no_copy=0,
		)


def apply() -> list[str]:
	results: list[str] = []

	_ensure_core_doctypes(results)
	_ensure_item_process_size_doctype_and_field(results)
	if not frappe.db.exists("DocType", "Per Piece") or not frappe.db.exists("DocType", "Per Piece Salary"):
		results.append("Skipped: Required DocTypes are still missing (Per Piece, Per Piece Salary)")
		return results

	_ensure_custom_field(
		"jv_status", "JV Status", "Select", "Pending\nPosted", "amount", results, default="Pending"
	)
	_ensure_custom_field("jv_entry_no", "JV Entry No", "Link", "Journal Entry", "jv_status", results)
	_ensure_custom_field(
		"jv_line_remark", "JV Line Remark", "Small Text", None, "jv_entry_no", results, in_list_view=0
	)
	_ensure_custom_field("booked_amount", "Booked Amount", "Float", None, "jv_line_remark", results)
	_ensure_custom_field("allowance", "Allowance", "Float", None, "booked_amount", results)
	_ensure_custom_field("advance_deduction", "Advance Deduction", "Float", None, "allowance", results)
	_ensure_custom_field("other_deduction", "Other Deduction", "Float", None, "advance_deduction", results)
	_ensure_custom_field("net_amount", "Net Amount", "Float", None, "other_deduction", results)
	_ensure_custom_field("paid_amount", "Paid Amount", "Float", None, "booked_amount", results)
	_ensure_custom_field("unpaid_amount", "Unpaid Amount", "Float", None, "paid_amount", results)
	_ensure_custom_field(
		"payment_status",
		"Payment Status",
		"Select",
		"Unpaid\nPartly Paid\nPaid",
		"unpaid_amount",
		results,
		default="Unpaid",
	)
	_ensure_custom_field("payment_jv_no", "Payment JV", "Link", "Journal Entry", "payment_status", results)
	_ensure_custom_field(
		"payment_refs", "Payment Refs", "Small Text", None, "payment_jv_no", results, in_list_view=0
	)
	_ensure_custom_field(
		"payment_line_remark", "Payment Remark", "Small Text", None, "payment_refs", results, in_list_view=0
	)
	_ensure_custom_field(
		"sales_order",
		"Sales Order",
		"Link",
		"Sales Order",
		"process_type",
		results,
		doctype="Per Piece",
		read_only=0,
		in_list_view=1,
		no_copy=0,
		allow_fieldtype_override=1,
	)
	_ensure_custom_field(
		"delivery_note",
		"Delivery Note",
		"Link",
		"Delivery Note",
		"sales_order",
		results,
		doctype="Per Piece",
		read_only=1,
		in_list_view=1,
		no_copy=0,
		allow_fieldtype_override=1,
	)
	_ensure_custom_field(
		"pp_filters_section_break",
		"",
		"Section Break",
		None,
		"po_number",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"item_group",
		"Item Group",
		"Link",
		"Item Group",
		"pp_filters_section_break",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"pp_filters_col_break_1",
		"",
		"Column Break",
		None,
		"item_group",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"item",
		"Item",
		"Link",
		"Item",
		"pp_filters_col_break_1",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"delivery_note",
		"Delivery Note",
		"Link",
		"Delivery Note",
		"item",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"pp_filters_col_break_2",
		"",
		"Column Break",
		None,
		"delivery_note",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"employee",
		"Employee",
		"Link",
		"Employee",
		"pp_filters_col_break_2",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"company",
		"Company",
		"Link",
		"Company",
		"employee",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"pp_filters_col_break_3",
		"",
		"Column Break",
		None,
		"company",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
	)
	_ensure_custom_field(
		"load_by_item",
		"Load By Item",
		"Check",
		None,
		"pp_filters_col_break_3",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
		default="1",
	)
	_ensure_inline_per_piece_and_salary_fields(results)
	_ensure_per_piece_salary_total_fields(results)
	_delete_custom_field("Per Piece Salary", "total_allowance", results)
	_delete_custom_field("Per Piece Salary", "total_advance_deduction", results)
	_delete_custom_field("Per Piece Salary", "total_other_deduction", results)
	_delete_custom_field("Per Piece Salary", "total_net_amount", results)
	_delete_custom_field("Item", "custom_process_type", results)
	_delete_custom_field("Item", "custom_process_size", results)
	_delete_custom_field("Item", "custom_rate_per_piece", results)
	_delete_custom_field("Per Piece Salary", "voucher_no", results)
	_delete_custom_field("Per Piece Salary", "selected_items", results)
	_delete_custom_field("Per Piece Salary", "pp_filter_col_break", results)
	_ensure_doctype_property_setter(
		"Per Piece Salary",
		"autoname",
		"format:PPE-DE-{YYYY}-{#####}",
		"Data",
		results,
	)
	_ensure_doctype_property_setter("Per Piece Salary", "allow_rename", "0", "Check", results)
	_ensure_field_property_setter("Per Piece Salary", "po_number", "reqd", "1", "Check", results)
	_ensure_per_piece_field_links(results)
	_migrate_jv_status(results)

	_cleanup_legacy_ui_docs(results)
	_upsert_doc(
		"Report",
		"Per Piece Salary Report",
		{
			"ref_doctype": "Per Piece Salary",
			"report_type": "Script Report",
			"is_standard": "No",
			"module": "Payroll",
			"report_script": SCRIPT_REPORT_SCRIPT,
			"javascript": SCRIPT_REPORT_JS,
			"disabled": 0,
		},
		results,
	)
	_upsert_doc(
		"Report",
		"Per Piece Query Report Simple",
		{
			"ref_doctype": "Per Piece Salary",
			"report_type": "Query Report",
			"is_standard": "No",
			"module": "Payroll",
			"query": QUERY_REPORT_QUERY,
			"javascript": QUERY_REPORT_JS,
			"disabled": 0,
		},
		results,
	)
	# Web page route is intentionally removed; Desk pages load app file-backed payload directly.
	_update_print_format(results)

	frappe.clear_cache()
	frappe.db.commit()
	return results
