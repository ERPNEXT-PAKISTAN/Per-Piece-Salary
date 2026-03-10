import json

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

    account_names = sorted(account_map.keys())
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

        adv_map = {}
        for rr in gl_rows:
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

        for emp in sorted(adv_map.keys()):
            rec = adv_map.get(emp) or {}
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
            out.append(
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
        return {"rows": out, "months": months}

    if frappe.db.exists("DocType", "Employee Advance"):
        fallback_rows = frappe.get_all(
            "Employee Advance",
            filters={"docstatus": 1, "posting_date": ["<=", to_date_value]},
            fields=["employee", "posting_date", "paid_amount", "claimed_amount", "return_amount"],
            order_by="posting_date asc, creation asc",
            limit_page_length=200000,
        )

        fallback_map = {}
        for rr in fallback_rows:
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

        if not out:
            for emp in sorted(fallback_map.keys()):
                rec = fallback_map.get(emp) or {}
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
                out.append(
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

    return {"rows": out, "months": months}

args = dict(frappe.form_dict or {})

from_date = normalize_date(args.get("from_date"))
to_date = normalize_date(args.get("to_date"))
if from_date and to_date and from_date > to_date:
    frappe.throw("From Date cannot be after To Date.")

employee = normalize_param(args.get("employee"))
product = normalize_param(args.get("product"))
process_type = normalize_param(args.get("process_type"))
item_group = normalize_param(args.get("item_group"))
max_rows = to_int(args.get("max_rows"), 2000)
if max_rows < 100:
    max_rows = 100
if max_rows > 20000:
    max_rows = 20000
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

parent_filters = {"docstatus": ["<", 2]}
if from_date:
    parent_filters["to_date"] = [">=", from_date]
if to_date:
    parent_filters["from_date"] = ["<=", to_date]

parents = frappe.get_all(
    "Per Piece Salary",
    filters=parent_filters,
    fields=["name", "from_date", "to_date", "po_number", "item_group", "total_qty", "total_amount"],
    order_by="from_date desc, creation desc",
    limit_page_length=max(max_rows * 2, 1000),
)

if not parents:
    frappe.response["message"] = {
        "columns": [],
        "data": [],
        "employees": [],
        "products": [],
        "process_types": [],
        "item_groups": [],
        "advance_balances": all_advance_balances,
        "advance_rows": all_advance_rows,
        "advance_months": all_advance_months,
    }
else:
    parent_names = [p["name"] for p in parents]
    option_rows = frappe.get_all(
        "Per Piece",
        filters={"parent": ["in", parent_names], "parenttype": "Per Piece Salary", "parentfield": "perpiece"},
        fields=["employee", "product", "process_type", "process_size"],
    )

    employees = sorted(set((row.get("employee") or "").strip() for row in option_rows if row.get("employee")))
    products = sorted(set((row.get("product") or "").strip() for row in option_rows if row.get("product")))
    process_types = sorted(
        set((row.get("process_type") or "").strip() for row in option_rows if row.get("process_type"))
    )
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
    advance_balances = all_advance_balances

    if get_options:
        frappe.response["message"] = {
            "columns": [],
            "data": [],
            "employees": employees,
            "products": products,
            "process_types": process_types,
            "item_groups": item_groups,
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
            limit_page_length=max_rows,
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
            booking_status_value = "Booked" if ((child.get("jv_entry_no") or "") and ((child.get("jv_status") or "") in ("Posted", "Accounted"))) else "UnBooked"
            booked_amount_value = to_float(child.get("booked_amount"))
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
            data.append(
                {
                    "row_id": child.get("name"),
                    "per_piece_salary": parent.get("name"),
                    "from_date": parent.get("from_date"),
                    "to_date": parent.get("to_date"),
                    "po_number": parent.get("po_number"),
                    "item_group": row_item_group,
                    "total_qty": parent.get("total_qty"),
                    "total_amount": parent.get("total_amount"),
                    "employee": child.get("employee"),
                    "name1": child.get("name1"),
                    "product": child.get("product"),
                    "process_type": child.get("process_type"),
                    "process_size": child.get("process_size") or "No Size",
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
            {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
            {"label": "Employee First Name", "fieldname": "name1", "fieldtype": "Data", "width": 140},
            {"label": "Product", "fieldname": "product", "fieldtype": "Link", "options": "Item", "width": 140},
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
            "item_groups": item_groups,
            "advance_balances": advance_balances,
            "advance_rows": all_advance_rows,
            "advance_months": all_advance_months,
            "max_rows": max_rows,
            "max_days": max_days,
            "truncated": 1 if len(children) >= max_rows else 0,
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
        qty_index = 4
        rate_index = 5
        if len(parts) >= 7:
            process_size = normalize_param(parts[4]) or "No Size"
            qty_index = 5
            rate_index = 6
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
selected_items = normalize_param(args.get("selected_items"))
load_by_item = normalize_param(args.get("load_by_item")) or "1"
employee = normalize_param(args.get("employee"))
entry_name = normalize_param(args.get("entry_name"))
rows = parse_rows(args.get("rows"))

if not from_date or not to_date:
    frappe.throw("From Date and To Date are required.")
if from_date > to_date:
    frappe.throw("From Date cannot be after To Date.")
if not po_number:
    frappe.throw("PO Number is required.")
if not rows:
    frappe.throw("Enter at least one row with Qty.")

if entry_name:
    if not frappe.db.exists("Per Piece Salary", entry_name):
        frappe.throw("Per Piece Salary not found: " + str(entry_name))
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
if frappe.get_meta("Per Piece Salary").has_field("item"):
    doc.item = item
if frappe.get_meta("Per Piece Salary").has_field("selected_items"):
    doc.selected_items = selected_items
if frappe.get_meta("Per Piece Salary").has_field("load_by_item"):
    doc.load_by_item = 1 if str(load_by_item) == "1" else 0
if frappe.get_meta("Per Piece Salary").has_field("employee"):
    doc.employee = employee
doc.set("perpiece", [])

total_qty = 0.0
total_amount = 0.0
for row in rows:
    total_qty = total_qty + row.get("qty", 0)
    total_amount = total_amount + row.get("amount", 0)
    doc.append(
        "perpiece",
        {
            "employee": row.get("employee"),
            "name1": row.get("name1"),
            "product": row.get("product"),
            "process_type": row.get("process_type"),
            "process_size": row.get("process_size") or "No Size",
            "qty": row.get("qty"),
            "rate": row.get("rate"),
            "amount": row.get("amount"),
        },
    )

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
        }
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
    return "Qty " + str(qty) + " x Rate " + str(rate) + ", PO " + str(po) + ", Process " + str(process_type)

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
        pp.employee,
        pp.name1,
        pp.qty,
        pp.rate,
        pp.amount,
        pp.process_type,
        pps.po_number
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
        AND IFNULL(pp.jv_entry_no, '') = ''
        AND IFNULL(pp.jv_status, 'Pending') != 'Posted'
    ORDER BY pps.from_date ASC, pps.name ASC, pp.idx ASC
    \"\"\",
    {
        "from_date": from_date,
        "to_date": to_date,
        "employee": employee,
        "product": product,
        "process_type": process_type,
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
    advance_balance = max(to_float(employee_advance_balances.get(emp)), 0.0)
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
    remarks = ["Per Piece Salary JV from " + str(from_date) + " to " + str(to_date)]
    if header_remark:
        remarks.append(header_remark)
    remarks.append("Gross " + str(round(total_gross_amount, 2)) + ", Net " + str(round(total_net_payable, 2)))
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

        running = 0.0
        for idx, rr in enumerate(emp_rows):
            child_name = rr.get("child_name")
            if not child_name:
                continue
            if idx == len(emp_rows) - 1:
                booked = max(emp_net - running, 0.0)
            else:
                if emp_base > 0:
                    booked = round((max(to_float(rr.get("amount")), 0.0) / emp_base) * emp_net, 2)
                else:
                    booked = round(emp_net / len(emp_rows), 2)
                running = running + booked
            booked = round(max(booked, 0.0), 2)

            frappe.db.set_value("Per Piece", child_name, "jv_entry_no", je.name, update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "jv_status", "Posted", update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "jv_line_remark", rr.get("line_remark"), update_modified=False)
            frappe.db.set_value("Per Piece", child_name, "booked_amount", booked, update_modified=False)
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
dry_run = to_bool(args.get("dry_run"))
payment_items = parse_payment_items(args.get("payment_items"))

cleanup_canceled_payment_links()

rows = frappe.db.sql(
    \"\"\"
    SELECT
        pp.name AS child_name,
        pp.employee,
        pp.name1,
        pp.amount,
        pp.booked_amount,
        pp.paid_amount,
        pp.unpaid_amount,
        pp.payment_refs
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
        AND IFNULL(pp.jv_entry_no, '') != ''
        AND IFNULL(pp.jv_status, 'Pending') = 'Posted'
    ORDER BY pps.from_date ASC, pps.name ASC, pp.idx ASC
    \"\"\",
    {
        "from_date": from_date,
        "to_date": to_date,
        "employee": employee,
        "product": product,
        "process_type": process_type,
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
    head = "Per Piece Salary Payment JV from " + str(from_date) + " to " + str(to_date)
    if header_remark:
        head = head + " | " + header_remark
    head = head + " | Amount " + str(round2(total_to_pay))
    je.user_remark = head

    for item in preview:
        amount = max(round2(item.get("to_pay_amount")), 0.0)
        if amount <= 0:
            continue
        debit_row = {
            "account": payable_account,
            "debit_in_account_currency": amount,
            "user_remark": "Salary Paid - " + str(item.get("employee")),
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
        {"employees": tuple(employee_list), "upto_date": to_date},
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

parents = frappe.get_all(
    "Per Piece Salary",
    filters=parent_filters,
    fields=["name", "from_date", "to_date", "po_number", "item_group"],
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
        fields=["parent", "idx", "employee", "name1", "product", "process_type", "process_size", "qty", "rate", "amount", "jv_status", "jv_entry_no", "jv_line_remark", "booked_amount", "paid_amount", "unpaid_amount", "payment_status", "payment_jv_no", "payment_line_remark"],
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
            AND (%(to_date)s IS NULL OR %(to_date)s = '' OR ea.posting_date <= %(to_date)s)
    ) AS advance_balance,
    IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) AS jv_status,
    pp.jv_entry_no,
    pp.jv_line_remark,
    IF(IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted', 'Booked', 'UnBooked') AS booking_status,
    IF(
        IFNULL(pp.booked_amount, 0) > 0,
        IFNULL(pp.booked_amount, 0),
        IF(IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted', IFNULL(pp.amount, 0), 0)
    ) AS booked_amount,
    IFNULL(pp.payment_status, 'Unpaid') AS payment_status,
    IFNULL(pp.paid_amount, 0) AS paid_amount,
    IF(
        IFNULL(pp.unpaid_amount, 0) > 0,
        IFNULL(pp.unpaid_amount, 0),
        GREATEST(
            IF(
                IFNULL(pp.booked_amount, 0) > 0,
                IFNULL(pp.booked_amount, 0),
                IF(IFNULL(pp.jv_entry_no, '') != '' AND IF(IFNULL(pp.jv_status, 'Pending') = 'Accounted', 'Posted', IFNULL(pp.jv_status, 'Pending')) = 'Posted', IFNULL(pp.amount, 0), 0)
            ) - IFNULL(pp.paid_amount, 0),
            0
        )
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
        row.qty = 0;
        row.amount = 0;
        row.from_date = frm.doc.from_date || null;
        row.to_date = frm.doc.to_date || null;
        row.po_number = frm.doc.po_number || null;
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
            if (itemRate > 0) {
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
        if (frm.doc.load_by_item === undefined || frm.doc.load_by_item === null || frm.doc.load_by_item === "") {
            frm.set_value("load_by_item", 1);
        }
        setProductQuery(frm);
        loadParentEmployeeName(frm).then(() => {
            return loadItemsForGroup(frm);
        }).then(() => {
            populateRowsFromGroup(frm);
            frm.trigger("sync_parent_to_child");
            return syncRowsToItemGroup(frm);
        });
    },

    refresh(frm) {
        setProductQuery(frm);
        const btn = frm.add_custom_button(__("Per Piece Salary Report"), () => {
            window.open(REPORT_ROUTE, "_blank");
        });
        btn.addClass("btn-primary");
    },

    validate(frm) {
        validateDateRange(frm);
        frm.trigger("sync_parent_to_child");
        frm.trigger("recalc_amount_and_total");
    },

    from_date(frm) {
        validateDateRange(frm);
        frm.trigger("sync_parent_to_child");
    },

    to_date(frm) {
        validateDateRange(frm);
        frm.trigger("sync_parent_to_child");
    },

    po_number(frm) {
        frm.trigger("sync_parent_to_child");
    },

    employee(frm) {
        loadParentEmployeeName(frm).then(() => {
            frm.trigger("sync_parent_to_child");
            frm.refresh_field(CHILD_TABLE_FIELD);
        });
    },

    item_group(frm) {
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
        setProductQuery(frm);
        loadItemsForGroup(frm).then(() => {
            populateRowsFromGroup(frm, true);
            frm.refresh_field(CHILD_TABLE_FIELD);
            return syncRowsToItemGroup(frm);
        });
    },

    load_by_item(frm) {
        setProductQuery(frm);
        loadItemsForGroup(frm).then(() => {
            populateRowsFromGroup(frm, true);
            frm.refresh_field(CHILD_TABLE_FIELD);
            return syncRowsToItemGroup(frm);
        });
    },

    sync_parent_to_child(frm) {
        const rows = frm.doc[CHILD_TABLE_FIELD] || [];
        if (!rows.length) return;

        const fromDate = frm.doc.from_date || null;
        const toDate = frm.doc.to_date || null;
        const poNumber = frm.doc.po_number || null;

        applyParentEmployeeToRows(frm);
        rows.forEach((row) => {
            row.from_date = fromDate;
            row.to_date = toDate;
            row.po_number = poNumber;
            if (!row.process_size) {
                row.process_size = PROCESS_SIZE_DEFAULT;
            }
            calculateRowAmount(row);
        });

        frm.refresh_field(CHILD_TABLE_FIELD);
        frm.trigger("recalc_amount_and_total");
    },

    recalc_amount_and_total(frm) {
        const rows = frm.doc[CHILD_TABLE_FIELD] || [];
        let totalAmount = 0;
        let totalQty = 0;

        rows.forEach((row) => {
            if (!row.process_size) {
                row.process_size = PROCESS_SIZE_DEFAULT;
            }
            calculateRowAmount(row);
            totalAmount += flt(row.amount, DECIMALS);
            totalQty += flt(row.qty, DECIMALS);
        });

        frm.refresh_field(CHILD_TABLE_FIELD);
        frm.set_value("total_amount", flt(totalAmount, DECIMALS));
        frm.set_value("total_qty", flt(totalQty, DECIMALS));
    },

    perpiece_add(frm) {
        frm.trigger("sync_parent_to_child");
        loadItemsForGroup(frm).then(() => syncRowsToItemGroup(frm));
    },

    perpiece_remove(frm) {
        frm.trigger("recalc_amount_and_total");
    },
});

frappe.ui.form.on("Per Piece", {
    form_render(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        row.from_date = frm.doc.from_date || null;
        row.to_date = frm.doc.to_date || null;
        row.po_number = frm.doc.po_number || null;
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
        applyItemDefaults(frm, cdt, cdn);
    },

    qty(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        calculateRowAmount(row);
        frappe.model.set_value(cdt, cdn, "amount", row.amount);
        frm.trigger("recalc_amount_and_total");
    },

    rate(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        calculateRowAmount(row);
        frappe.model.set_value(cdt, cdn, "amount", row.amount);
        frm.trigger("recalc_amount_and_total");
    },

    process_size(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.process_size) {
            frappe.model.set_value(cdt, cdn, "process_size", PROCESS_SIZE_DEFAULT);
        }
    },
});
"""


WEB_PAGE_HTML = """
<div class="pp-wrap">
  <div class="pp-filters">
    <label>From Date <input type="date" id="pp-from-date" /></label>
    <label>To Date <input type="date" id="pp-to-date" /></label>
    <label>Employee <select id="pp-employee"><option value="">All</option></select></label>
    <label>Item Group <select id="pp-item-group"><option value="">All</option></select></label>
    <label>Product <select id="pp-product"><option value="">All</option></select></label>
    <label>Process Type <select id="pp-process-type"><option value="">All</option></select></label>
    <label>PO Number <select id="pp-po-number"><option value="">All</option></select></label>
    <label>Entry No <select id="pp-entry-no"><option value="">All</option></select></label>
    <label>Search <input type="text" id="pp-search-any" placeholder="Type any word..." /></label>
    <label>Max Rows
      <select id="pp-max-rows">
        <option value="1000">1,000</option>
        <option value="2000" selected>2,000</option>
        <option value="5000">5,000</option>
        <option value="10000">10,000</option>
      </select>
    </label>
    <label>Max Days (0=All) <input type="number" id="pp-max-days" min="0" step="1" value="0" /></label>
    <button id="pp-load-btn" class="btn btn-primary" type="button">Load Report</button>
  </div>

  <div class="pp-tabs">
    <button type="button" class="pp-tab active" data-tab="all">All Report</button>
    <button type="button" class="pp-tab" data-tab="data_entry">Data Enter</button>
    <button type="button" class="pp-tab" data-tab="salary_creation">Salary Creation</button>
    <button type="button" class="pp-tab" data-tab="jv_created">JV Entry Created</button>
    <button type="button" class="pp-tab" data-tab="payment_manage">Payment Entry Create</button>
    <button type="button" class="pp-tab" data-tab="advances">Advances</button>
    <button type="button" class="pp-tab" data-tab="employee_summary">Employee Summary</button>
    <button type="button" class="pp-tab" data-tab="month_year_salary">Month/Year Salary</button>
    <button type="button" class="pp-tab" data-tab="month_paid_unpaid">Month Paid/Unpaid</button>
    <button type="button" class="pp-tab" data-tab="simple_month_amount">Simple Month Wise</button>
    <button type="button" class="pp-tab" data-tab="product">Product Summary</button>
    <button type="button" class="pp-tab" data-tab="process_product">Process/Product Summary</button>
    <button type="button" class="pp-tab" data-tab="per_piece_salary">Per Piece Salary</button>
    <button type="button" class="pp-tab" data-tab="po_number">PO Number</button>
  </div>

  <div id="pp-msg" class="pp-msg"></div>
  <div id="pp-table-wrap" class="pp-table-wrap"></div>
  <div id="pp-totals" class="pp-totals"></div>
  <div id="pp-pagination" class="pp-pagination"></div>

  <div class="pp-jv-card" id="pp-salary-jv-card">
    <h4>Salary Creation Tab (Book Salary To Payable)</h4>
    <div class="pp-jv-grid">
      <label>Company <select id="pp-jv-company"><option value="">Select Company</option></select></label>
      <label>Posting Date <input type="date" id="pp-jv-posting-date" /></label>
      <label>Salary Account <select id="pp-jv-expense-account"><option value="">Select Salary Account</option></select></label>
      <label>Allowance Account <select id="pp-jv-allowance-account"><option value="">Select Allowance Account</option></select></label>
      <label>Payable Account <select id="pp-jv-payable-account"><option value="">Select Payable Account</option></select></label>
      <label>Advance Account <select id="pp-jv-advance-account"><option value="">Select Advance Account</option></select></label>
      <label>Deduction Account <select id="pp-jv-deduction-account"><option value="">Select Deduction Account</option></select></label>
      <label>JV Remark <input type="text" id="pp-jv-remark" placeholder="Optional" /></label>
      <label>Debit Amount <input type="text" id="pp-jv-debit-amount" readonly /></label>
      <label>Credit Amount <input type="text" id="pp-jv-credit-amount" readonly /></label>
      <label>JV Gross Total <input type="text" id="pp-jv-gross-amount" readonly /></label>
      <label class="pp-jv-check"><input type="checkbox" id="pp-jv-employee-wise" /> Employee-wise Credit JV</label>
    </div>
    <div class="pp-jv-actions">
      <button id="pp-jv-preview-btn" class="btn btn-default" type="button">Quick Preview JV</button>
      <button id="pp-jv-create-btn" class="btn btn-primary" type="button">Post JV Entry</button>
      <select id="pp-jv-existing"><option value="">Select Posted JV</option></select>
      <button id="pp-jv-cancel-btn" class="btn btn-danger" type="button">Cancel JV Entry</button>
    </div>
    <div id="pp-jv-result" class="pp-jv-result"></div>
  </div>

  <div class="pp-jv-card" id="pp-payment-jv-card">
    <h4>Payment Entry Create for Employees (Pay Booked Salary)</h4>
    <div class="pp-jv-grid">
      <label>Company <select id="pp-pay-company"><option value="">Select Company</option></select></label>
      <label>Posting Date <input type="date" id="pp-pay-posting-date" /></label>
      <label>Payable Account <select id="pp-pay-payable-account"><option value="">Select Payable Account</option></select></label>
      <label>Paid From Account <select id="pp-pay-paid-from-account"><option value="">Select Bank/Cash Account</option></select></label>
      <label>Payment Remark <input type="text" id="pp-pay-remark" placeholder="Optional" /></label>
      <label>Payment Debit Amount <input type="text" id="pp-pay-debit-amount" readonly /></label>
      <label>Payment Credit Amount <input type="text" id="pp-pay-credit-amount" readonly /></label>
      <label>Total Unpaid <input type="text" id="pp-pay-unpaid-amount" readonly /></label>
    </div>
    <div class="pp-jv-actions">
      <button id="pp-pay-preview-btn" class="btn btn-default" type="button">Quick Preview Payment JV</button>
      <button id="pp-pay-create-btn" class="btn btn-primary" type="button">Post Payment JV</button>
      <select id="pp-pay-existing"><option value="">Select Payment JV</option></select>
      <button id="pp-pay-cancel-btn" class="btn btn-danger" type="button">Cancel Payment JV</button>
    </div>
    <div id="pp-pay-result" class="pp-jv-result"></div>
  </div>

  <div id="pp-created-list-wrap" class="pp-entry-list"></div>

  <div id="pp-summary-modal" class="pp-modal" style="display:none;">
    <div class="pp-modal-card">
      <div class="pp-modal-head">
        <div>
          <div class="pp-modal-title">Per Piece Salary Summary</div>
          <div class="pp-modal-sub" id="pp-summary-subtitle"></div>
        </div>
        <button type="button" class="btn btn-default" id="pp-summary-close">Close</button>
      </div>
      <div id="pp-summary-content" class="pp-modal-body"></div>
    </div>
  </div>
</div>

<style>
  .pp-wrap { padding: 16px; background: #f8fbff; border-radius: 12px; }
  .pp-filters { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
  .pp-filters label { display: flex; flex-direction: column; gap: 4px; min-width: 180px; font-size: 12px; color: #334155; }
  .pp-filters input, .pp-filters select { border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 10px; font-size: 13px; }
  .pp-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
  .pp-tab { border: 1px solid #bfdbfe; background: #eff6ff; color: #1e3a8a; border-radius: 8px; padding: 6px 10px; font-size: 12px; }
  .pp-tab.active { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
  .pp-msg { margin: 8px 0; color: #475569; font-size: 12px; }
  .pp-table-wrap { overflow: auto; background: #fff; border: 1px solid #dbeafe; border-radius: 8px; }
  .pp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .pp-table th, .pp-table td { border: 1px solid #e2e8f0; padding: 7px 9px; }
  .pp-table th { background: #eff6ff; color: #1e3a8a; position: sticky; top: 0; z-index: 2; }
  .pp-table tr.pp-year-total td { background: #f1f5f9; font-weight: 700; color: #0f172a; }
  .pp-table tbody tr:hover td { background: #f8fafc; }
  .pp-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .pp-table td.pp-amt-col { font-weight: 700; color: #0f172a; }
  .pp-status-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; border: 1px solid transparent; }
  .pp-status-good { background: #dcfce7; color: #166534; border-color: #86efac; }
  .pp-status-warn { background: #fef3c7; color: #92400e; border-color: #fde68a; }
  .pp-status-bad { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
  .pp-status-neutral { background: #e2e8f0; color: #334155; border-color: #cbd5e1; }
  .pp-table input.pp-adj-input { width: 120px; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 6px; font-size: 12px; }
  .pp-totals { margin-top: 8px; font-size: 13px; font-weight: 600; color: #0f766e; display: flex; gap: 16px; }
  .pp-jv-card { margin-top: 14px; background: #fff; border: 1px solid #dbeafe; border-radius: 10px; padding: 12px; }
  .pp-jv-card h4 { margin: 0 0 10px 0; }
  .pp-entry-card { margin-top: 10px; background: #f8fafc; border: 1px dashed #93c5fd; border-radius: 10px; padding: 14px; }
  .pp-entry-actions { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
  .pp-entry-list { margin-top: 10px; font-size: 12px; color: #475569; }
  .pp-pay-input { width: 120px; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 6px; font-size: 12px; }
  .pp-entry-card .pp-table th, .pp-entry-card .pp-table td { vertical-align: middle; }
  .pp-entry-card .pp-table .pp-pay-input { width: 100%; min-width: 0; max-width: none; box-sizing: border-box; }
  .pp-entry-card .pp-table .pp-entry-view { background: #f8fafc; color: #334155; }
  .pp-pagination { margin-top: 10px; display: flex; gap: 8px; align-items: center; justify-content: flex-end; font-size: 12px; color: #334155; }
  .pp-pagination .btn[disabled] { opacity: 0.5; cursor: not-allowed; }
  .pp-jv-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
  .pp-jv-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #334155; }
  .pp-jv-grid input, .pp-jv-grid select { border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 10px; font-size: 13px; }
  .pp-jv-check { flex-direction: row !important; align-items: center; justify-content: flex-start; margin-top: 20px; }
  .pp-jv-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .pp-jv-actions select { min-width: 220px; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 10px; font-size: 13px; background: #fff; }
  .pp-jv-result { margin-top: 8px; font-size: 13px; }
  .pp-modal { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); z-index: 1200; align-items: center; justify-content: center; padding: 20px; }
  .pp-modal-card { width: min(1040px, 96vw); max-height: 90vh; overflow: auto; background: #f8fbff; border: 1px solid #bfdbfe; border-radius: 14px; box-shadow: 0 20px 40px rgba(2, 6, 23, 0.25); }
  .pp-modal-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid #dbeafe; background: linear-gradient(135deg, #eff6ff, #f8fafc); }
  .pp-modal-title { font-size: 18px; font-weight: 700; color: #0f172a; }
  .pp-modal-sub { font-size: 12px; color: #475569; margin-top: 2px; }
  .pp-modal-body { padding: 14px 16px 16px 16px; }
  .pp-summary-chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .pp-summary-chip { background: #e0f2fe; color: #0c4a6e; border: 1px solid #bae6fd; border-radius: 999px; padding: 4px 10px; font-size: 12px; font-weight: 600; }
</style>

<script>
(function () {
  var state = {
    currentTab: "all",
    rows: [],
    columns: [],
    filterOptions: { employees: [], item_groups: [], products: [], process_types: [] },
    adjustments: {},
    advanceBalances: {},
    advanceRows: [],
    advanceMonths: [],
    excludedEmployees: {},
    paymentAdjustments: {},
    paymentExcludedEmployees: {},
    entryRows: [],
    entryMeta: {},
    pageSize: 20,
    pageByTab: {}
  };

  function el(id) { return document.getElementById(id); }
  function esc(v) { var d = document.createElement("div"); d.textContent = v == null ? "" : String(v); return d.innerHTML; }
  function num(v) { var n = Number(v || 0); return isNaN(n) ? 0 : n; }
  function whole(v) { return Math.max(0, Math.round(num(v) * 100) / 100); }
  function fmt(v) { return num(v).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
  function baseProcessSizeOptions() {
    return ["No Size", "Single", "Double", "King", "Supper King"];
  }
  function isStatusField(fieldname) {
    var f = String(fieldname || "");
    return f === "jv_status" || f === "booking_status" || f === "payment_status";
  }
  function isAmountField(fieldname) {
    var f = String(fieldname || "");
    if (!f) return false;
    if (f === "qty" || f === "rate" || f === "_row_count" || f === "month_no") return false;
    if (f.indexOf("m_") === 0) return true;
    if (f.indexOf("amount") >= 0) return true;
    if (f === "opening_balance" || f === "closing_balance" || f === "advance_balance") return true;
    return false;
  }
  function statusBadgeHtml(value) {
    var txt = String(value || "").trim();
    if (!txt) return "";
    var k = txt.toLowerCase();
    var cls = "pp-status-neutral";
    if (k === "paid" || k === "posted" || k === "booked") cls = "pp-status-good";
    else if (k === "partly paid" || k === "partly booked") cls = "pp-status-warn";
    else if (k === "unpaid" || k === "unbooked" || k === "pending") cls = "pp-status-bad";
    else if (k === "cancelled" || k === "canceled") cls = "pp-status-neutral";
    return "<span class='pp-status-badge " + cls + "'>" + esc(txt) + "</span>";
  }
  function getSearchTerm() {
    var input = el("pp-search-any");
    return String((input && input.value) || "").trim().toLowerCase();
  }
  function filterRowsByColumns(rows, columns) {
    var term = getSearchTerm();
    if (!term) return rows || [];
    return (rows || []).filter(function (r) {
      var parts = [];
      (columns || []).forEach(function (c) {
        var v = r[c.fieldname];
        if (v === undefined || v === null) return;
        parts.push(String(v));
      });
      return parts.join(" ").toLowerCase().indexOf(term) >= 0;
    });
  }
  function filterRowsByKeys(rows, keys) {
    var term = getSearchTerm();
    if (!term) return rows || [];
    return (rows || []).filter(function (r) {
      var parts = [];
      (keys || []).forEach(function (k) {
        var v = r[k];
        if (v === undefined || v === null) return;
        parts.push(String(v));
      });
      return parts.join(" ").toLowerCase().indexOf(term) >= 0;
    });
  }
  function filterRenderedTablesBySearch() {
    var term = getSearchTerm();
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    wrap.querySelectorAll("table.pp-table tbody tr").forEach(function (tr) {
      if (!term) {
        tr.style.display = "";
        return;
      }
      var txt = String(tr.textContent || "").toLowerCase();
      tr.style.display = txt.indexOf(term) >= 0 ? "" : "none";
    });
  }
  function avgRate(q, a) { q = num(q); a = num(a); return q ? (a / q) : 0; }
  function employeeLabel(row) {
    if (!row) return "";
    return (row.name1 || row.employee || "").trim();
  }
  function advanceMonthField(key) {
    return "adv_" + String(key || "").replace("-", "_");
  }
  function errText(e) {
    if (!e) return "Unknown error";
    if (typeof e === "string") return e;
    if (e._server_messages) {
      try {
        var msgs = JSON.parse(e._server_messages);
        if (Array.isArray(msgs) && msgs.length) {
          var first = String(msgs[0] || "");
          if (first) return first.replace(/<[^>]*>/g, "");
        }
      } catch (x) {}
    }
    if (e._error_message) return String(e._error_message);
    if (e.message && typeof e.message === "string") return e.message;
    if (e.exc && typeof e.exc === "string") return e.exc;
    if (Array.isArray(e.exc) && e.exc.length) {
      var raw = String(e.exc[0] || "");
      var m = raw.match(/ValidationError:\\s*([^\\n]+)/);
      if (m && m[1]) return m[1];
      return raw;
    }
    return "Request failed";
  }

  function prettyError(msg) {
    var text = String(msg || "");
    if (text.indexOf("No unposted rows found for selected filters.") >= 0) {
      return "No unbooked salary rows found for current filters. Change date/filter or use JV Entry Created tab.";
    }
    if (text.indexOf("No booked salary rows found for selected filters.") >= 0) {
      return "No booked salary rows are available for payment in current filters.";
    }
    return text;
  }

  function showResult(resultEl, kind, title, msg) {
    if (!resultEl) return;
    var color = kind === "error" ? "#b91c1c" : "#0f766e";
    var bg = kind === "error" ? "#fef2f2" : "#f0fdf4";
    resultEl.style.color = color;
    resultEl.innerHTML = "<div style='border:1px solid " + color + ";background:" + bg + ";border-radius:8px;padding:8px 10px;'><strong>" + esc(title || "") + "</strong><div style='margin-top:4px;'>" + esc(msg || "") + "</div></div>";
  }

  function getCsrfToken() {
    if (typeof frappe !== "undefined" && frappe.csrf_token) return frappe.csrf_token;
    var match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function encodeArgs(args) {
    return Object.keys(args || {}).map(function (k) {
      var value = args[k];
      if (value === undefined || value === null) value = "";
      return encodeURIComponent(k) + "=" + encodeURIComponent(value);
    }).join("&");
  }

  function callApi(method, args) {
    var payload = encodeArgs(args || {});
    var mutateMethods = {
      "create_per_piece_salary_entry": true,
      "create_per_piece_salary_jv": true,
      "cancel_per_piece_salary_jv": true,
      "create_per_piece_salary_payment_jv": true,
      "cancel_per_piece_salary_payment_jv": true
    };
    var mutate = !!mutateMethods[method];
    var usePost = mutate || payload.length > 1500;
    var url = "/api/method/" + method;
    var fetchOptions = { credentials: "same-origin", method: usePost ? "POST" : "GET" };

    if (usePost) {
      fetchOptions.headers = { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" };
      var csrf = getCsrfToken();
      if (csrf) fetchOptions.headers["X-Frappe-CSRF-Token"] = csrf;
      fetchOptions.body = payload;
    } else if (payload) {
      url += "?" + payload;
    }

    return fetch(url, fetchOptions)
      .catch(function (networkErr) {
        throw {
          _error_message: "Network error: unable to connect to server. Please refresh and try again.",
          message: (networkErr && networkErr.message) ? networkErr.message : "Network request failed",
          network_error: 1
        };
      })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          if (!res.ok || body.exc || body.exception || body._error_message) {
            throw body;
          }
          return body.message;
        });
      });
  }

  function callGetList(doctype, fields, filters, limit) {
    return callApi("frappe.client.get_list", {
      doctype: doctype,
      fields: JSON.stringify(fields || ["name"]),
      filters: JSON.stringify(filters || {}),
      order_by: "name asc",
      limit_page_length: limit || 500
    });
  }

  function setOptions(selectEl, rows, valueKey, labelKey, firstLabel) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    var first = document.createElement("option");
    first.value = "";
    first.textContent = firstLabel || "Select";
    selectEl.appendChild(first);
    (rows || []).forEach(function (r) {
      var opt = document.createElement("option");
      opt.value = r[valueKey];
      opt.textContent = r[labelKey] || r[valueKey];
      selectEl.appendChild(opt);
    });
  }

  function refreshTopProductOptions() {
    var productSelect = el("pp-product");
    if (!productSelect) return;
    var selectedItemGroup = String((el("pp-item-group") && el("pp-item-group").value) || "").trim();
    var currentProduct = String(productSelect.value || "").trim();
    var productMap = {};
    var productRows = [];
    var productMetaMap = (state.entryMeta && state.entryMeta.productMetaMap) || {};

    function canUseProduct(productName, itemGroup) {
      if (!productName) return false;
      if (!selectedItemGroup) return true;
      if (itemGroup) return String(itemGroup).trim() === selectedItemGroup;
      return false;
    }

    (state.entryMeta.masterProcessRows || []).forEach(function (item) {
      var productName = String((item && item.item) || "").trim();
      var itemGroup = String((item && item.item_group) || "").trim();
      if (!canUseProduct(productName, itemGroup) || productMap[productName]) return;
      productMap[productName] = true;
      productRows.push({ value: productName, label: productName });
    });

    (state.rows || []).forEach(function (row) {
      var productName = String((row && row.product) || "").trim();
      var itemGroup = String((row && row.item_group) || "").trim();
      if (!canUseProduct(productName, itemGroup) || productMap[productName]) return;
      productMap[productName] = true;
      productRows.push({ value: productName, label: productName });
    });

    (state.filterOptions.products || []).forEach(function (productNameRaw) {
      var productName = String(productNameRaw || "").trim();
      var meta = productMetaMap[productName] || {};
      var itemGroup = String(meta.item_group || "").trim();
      if (!canUseProduct(productName, itemGroup) || productMap[productName]) return;
      productMap[productName] = true;
      productRows.push({ value: productName, label: productName });
    });

    productRows.sort(function (a, b) {
      return String(a.label || "").localeCompare(String(b.label || ""));
    });
    setOptions(productSelect, productRows, "value", "label", "All");
    if (currentProduct && productMap[currentProduct]) {
      productSelect.value = currentProduct;
    } else if (selectedItemGroup) {
      productSelect.value = "";
    }
  }

  function getReportArgs() {
    var fromVal = el("pp-from-date").value || "";
    var toVal = el("pp-to-date").value || "";
    if (fromVal && toVal && fromVal > toVal) {
      var tmp = fromVal;
      fromVal = toVal;
      toVal = tmp;
      el("pp-from-date").value = fromVal;
      el("pp-to-date").value = toVal;
    }
    return {
      from_date: fromVal,
      to_date: toVal,
      employee: el("pp-employee").value || "",
      item_group: el("pp-item-group") ? (el("pp-item-group").value || "") : "",
      product: el("pp-product").value || "",
      process_type: el("pp-process-type").value || "",
      po_number: el("pp-po-number") ? (el("pp-po-number").value || "") : "",
      entry_no: el("pp-entry-no") ? (el("pp-entry-no").value || "") : "",
      max_rows: el("pp-max-rows") ? (el("pp-max-rows").value || "2000") : "2000",
      max_days: el("pp-max-days") ? (el("pp-max-days").value || "0") : "0"
    };
  }

  function refreshHeaderFilterOptions() {
    var poSelect = el("pp-po-number");
    var entrySelect = el("pp-entry-no");
    if (!poSelect || !entrySelect) return;
    var currentPo = poSelect.value || "";
    var currentEntry = entrySelect.value || "";
    var poMap = {};
    var entryMap = {};
    (state.rows || []).forEach(function (r) {
      var po = String(r.po_number || "").trim();
      var entry = String(r.per_piece_salary || "").trim();
      if (po) poMap[po] = true;
      if (entry) entryMap[entry] = true;
    });
    var poRows = Object.keys(poMap).sort().map(function (v) { return { value: v, label: v }; });
    var entryRows = Object.keys(entryMap).sort().map(function (v) { return { value: v, label: v }; });
    setOptions(poSelect, poRows, "value", "label", "All");
    setOptions(entrySelect, entryRows, "value", "label", "All");
    if (currentPo && poMap[currentPo]) poSelect.value = currentPo;
    if (currentEntry && entryMap[currentEntry]) entrySelect.value = currentEntry;
  }

  function getRowsByHeaderFilters(rows) {
    var po = el("pp-po-number") ? String(el("pp-po-number").value || "").trim() : "";
    var entry = el("pp-entry-no") ? String(el("pp-entry-no").value || "").trim() : "";
    return (rows || []).filter(function (r) {
      if (po && String(r.po_number || "") !== po) return false;
      if (entry && String(r.per_piece_salary || "") !== entry) return false;
      return true;
    });
  }

  function parseDateOnly(value) {
    if (!value) return null;
    var d = new Date(String(value) + "T00:00:00");
    if (isNaN(d.getTime())) return null;
    return d;
  }

  function pad2(v) {
    var n = parseInt(v, 10) || 0;
    return n < 10 ? ("0" + n) : String(n);
  }

  function ymd(d) {
    if (!d) return "";
    return String(d.getFullYear()) + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }

  function buildLast6Months(toDate) {
    var monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var end = parseDateOnly(toDate);
    if (!end) end = new Date();
    var out = [];
    for (var i = 5; i >= 0; i--) {
      var dt = new Date(end.getFullYear(), end.getMonth() - i, 1);
      var key = String(dt.getFullYear()) + "-" + pad2(dt.getMonth() + 1);
      var label = monthNames[dt.getMonth()] + "-" + String(dt.getFullYear()).slice(-2);
      out.push({ key: key, label: label });
    }
    return out;
  }

  function loadAdvancesFromGL() {
    var args = getReportArgs();
    var toDate = args.to_date || ymd(new Date());
    var selectedEmployee = args.employee || "";
    var months = buildLast6Months(toDate);
    var monthMap = {};
    months.forEach(function (m) { monthMap[m.key] = true; });
    var firstMonthDate = (months[0] && months[0].key ? months[0].key : toDate.slice(0, 7)) + "-01";

    function getAccountCandidates() {
      var p1 = callGetList("Account", ["name"], [["docstatus", "<", 2], ["name", "like", "%Employee Advance%"]], 2000).catch(function () { return []; });
      var p2 = callGetList("Account", ["name"], [["docstatus", "<", 2], ["account_name", "like", "%Employee Advance%"]], 2000).catch(function () { return []; });
      return Promise.all([p1, p2]).then(function (parts) {
        var map = {};
        (parts[0] || []).forEach(function (r) { if (r && r.name) map[r.name] = true; });
        (parts[1] || []).forEach(function (r) { if (r && r.name) map[r.name] = true; });
        return Object.keys(map);
      });
    }

    return getAccountCandidates().then(function (accounts) {
      if (!accounts || !accounts.length) {
        state.advanceRows = [];
        state.advanceMonths = months;
        state.advanceBalances = {};
        return;
      }

      var glFilters = [
        ["docstatus", "=", 1],
        ["party_type", "=", "Employee"],
        ["is_cancelled", "=", 0],
        ["posting_date", "<=", toDate],
        ["account", "in", accounts],
      ];
      if (selectedEmployee) glFilters.push(["party", "=", selectedEmployee]);

      return Promise.all([
        callGetList("GL Entry", ["party", "posting_date", "debit", "credit"], glFilters, 20000),
        callGetList("Employee", ["name", "employee_name", "branch"], {}, 20000).catch(function () { return []; }),
      ]).then(function (allRows) {
        var glRows = allRows[0] || [];
        var empRows = allRows[1] || [];
        var empMap = {};
        empRows.forEach(function (e) {
          if (!e || !e.name) return;
          empMap[e.name] = {
            name1: e.employee_name || e.name,
            branch: e.branch || "",
          };
        });

        var advMap = {};
        glRows.forEach(function (g) {
          var emp = String(g.party || "").trim();
          if (!emp) return;
          if (selectedEmployee && emp !== selectedEmployee) return;

          if (!advMap[emp]) {
            var monthValues = {};
            months.forEach(function (m) { monthValues[m.key] = 0; });
            advMap[emp] = {
              employee: emp,
              name1: (empMap[emp] && empMap[emp].name1) || emp,
              branch: (empMap[emp] && empMap[emp].branch) || "",
              opening_balance: 0,
              month_values: monthValues,
              closing_balance: 0,
              advance_balance: 0,
            };
          }

          var postDate = String(g.posting_date || "").slice(0, 10);
          if (!postDate) return;
          var amount = num(g.debit) - num(g.credit);

          if (postDate < firstMonthDate) {
            advMap[emp].opening_balance += amount;
          } else if (postDate <= toDate) {
            var key = postDate.slice(0, 7);
            if (monthMap[key]) advMap[emp].month_values[key] += amount;
          }
        });

        var rows = [];
        Object.keys(advMap).sort().forEach(function (emp) {
          var rec = advMap[emp];
          var running = num(rec.opening_balance);
          months.forEach(function (m) { running += num(rec.month_values[m.key]); });
          rec.opening_balance = Math.round(num(rec.opening_balance) * 100) / 100;
          rec.closing_balance = Math.round(running * 100) / 100;
          rec.advance_balance = rec.closing_balance;
          if (Math.abs(rec.closing_balance) < 0.01 && Math.abs(rec.opening_balance) < 0.01) return;
          rows.push(rec);
        });

        var balMap = {};
        rows.forEach(function (r) { balMap[r.employee] = num(r.advance_balance); });
        state.advanceRows = rows;
        state.advanceMonths = months;
        state.advanceBalances = balMap;
      });
    });
  }

  function loadFilterOptions() {
    return callApi("get_per_piece_salary_report", { get_options: 1 }).then(function (m) {
      var currentEmployee = el("pp-employee") ? (el("pp-employee").value || "") : "";
      var currentItemGroup = el("pp-item-group") ? (el("pp-item-group").value || "") : "";
      var currentProcessType = el("pp-process-type") ? (el("pp-process-type").value || "") : "";
      state.filterOptions = {
        employees: (m && m.employees) || [],
        item_groups: (m && m.item_groups) || [],
        products: (m && m.products) || [],
        process_types: (m && m.process_types) || []
      };
      var emps = (state.filterOptions.employees || []).map(function (v) { return { value: v, label: v }; });
      var itemGroups = (state.filterOptions.item_groups || []).map(function (v) { return { value: v, label: v }; });
      var ptypes = (m && m.process_types || []).map(function (v) { return { value: v, label: v }; });
      state.advanceBalances = (m && m.advance_balances) || {};
      state.advanceRows = (m && m.advance_rows) || [];
      state.advanceMonths = (m && m.advance_months) || [];
      setOptions(el("pp-employee"), emps, "value", "label", "All");
      setOptions(el("pp-item-group"), itemGroups, "value", "label", "All");
      setOptions(el("pp-process-type"), ptypes, "value", "label", "All");
      if (el("pp-employee")) el("pp-employee").value = currentEmployee;
      if (el("pp-item-group")) el("pp-item-group").value = currentItemGroup;
      if (el("pp-process-type")) el("pp-process-type").value = currentProcessType;
      refreshTopProductOptions();
      setOptions(el("pp-po-number"), [], "value", "label", "All");
      setOptions(el("pp-entry-no"), [], "value", "label", "All");
      rebuildEntryMetaLookups();
    });
  }

  function loadDataEntryMasters() {
    var employeePromise = callGetList("Employee", ["name", "employee_name"], {}, 2000)
      .then(function (rows) {
        state.entryMeta.masterEmployeeOptions = (rows || []).map(function (r) {
          return { value: r.name, label: (r.employee_name || r.name) + " (" + r.name + ")" };
        });
        (rows || []).forEach(function (r) {
          if (!state.entryMeta.employeeNameMap) state.entryMeta.employeeNameMap = {};
          if (r.name && r.employee_name) state.entryMeta.employeeNameMap[r.name] = r.employee_name;
        });
      })
      .catch(function () {});

    var itemGroupPromise = callGetList("Item Group", ["name"], {}, 2000)
      .then(function (rows) {
        state.entryMeta.masterItemGroupOptions = (rows || []).map(function (r) {
          return { value: r.name, label: r.name };
        });
      })
      .catch(function () {});

    var itemPromise = callApi("per_piece_payroll.api.get_item_process_rows", {})
      .then(function (rows) {
        state.entryMeta.masterProcessRows = rows || [];
      })
      .catch(function () {});

    return Promise.all([employeePromise, itemGroupPromise, itemPromise]).then(function () {
      rebuildEntryMetaLookups();
      refreshTopProductOptions();
    });
  }

  function rebuildEntryMetaLookups() {
    var employeeSet = {};
    var itemGroupSet = {};
    var productSet = {};
    var processSet = {};
    var processSizeSet = {};
    var employeeNameMap = {};
    var productMetaMap = {};
    var productProcessMap = {};
    var currentItemGroup = String(state.entryMeta.item_group || "").trim();
    var loadByItem = state.entryMeta.load_by_item !== false;
    var selectedItem = String(state.entryMeta.item || "").trim();
    var selectedMap = {};
    if (loadByItem && selectedItem) selectedMap[selectedItem] = true;
    var hasSelected = Object.keys(selectedMap).length > 0;

    (state.entryMeta.masterEmployeeOptions || []).forEach(function (opt) {
      if (opt && opt.value) {
        employeeSet[String(opt.value)] = true;
        var text = String(opt.label || "");
        var nameOnly = text.replace(/\\s*\\([^)]*\\)\\s*$/, "").trim();
        if (nameOnly) employeeNameMap[String(opt.value)] = nameOnly;
      }
    });
    (state.entryMeta.masterItemGroupOptions || []).forEach(function (opt) {
      if (opt && opt.value) itemGroupSet[String(opt.value)] = true;
    });
    (baseProcessSizeOptions() || []).forEach(function (value) {
      if (value) processSizeSet[String(value)] = true;
    });
    (state.entryMeta.masterProcessRows || []).forEach(function (item) {
      var itemName = String((item && item.item) || "").trim();
      var itemGroup = String((item && item.item_group) || "").trim();
      var employee = String((item && item.employee) || "").trim();
      var employeeName = String((item && item.employee_name) || "").trim();
      var processType = String((item && item.process_type) || "").trim();
      var processSize = String((item && item.process_size) || "").trim() || "No Size";
      var rate = num(item && item.rate);
      if (!itemName) return;
      if (itemGroup) itemGroupSet[itemGroup] = true;
      if (employee) {
        employeeSet[employee] = true;
        if (employeeName) employeeNameMap[employee] = employeeName;
      }
      if (!productProcessMap[itemName]) productProcessMap[itemName] = [];
      productProcessMap[itemName].push({
        item_group: itemGroup,
        employee: employee,
        employee_name: employeeName,
        process_type: processType,
        process_size: processSize,
        rate: rate,
      });
      if (!productMetaMap[itemName]) {
        productMetaMap[itemName] = {
          item_group: itemGroup,
          employee: employee,
          employee_name: employeeName,
          process_type: processType,
          process_size: processSize,
          rate: rate,
        };
      }
      if ((!currentItemGroup || itemGroup === currentItemGroup) && (!hasSelected || selectedMap[itemName])) {
        productSet[itemName] = true;
      }
      if (processType) processSet[processType] = true;
      if (processSize) processSizeSet[processSize] = true;
    });

    (state.filterOptions.employees || []).forEach(function (v) { if (v) employeeSet[String(v)] = true; });
    (state.filterOptions.item_groups || []).forEach(function (v) { if (v) itemGroupSet[String(v)] = true; });
    (state.filterOptions.products || []).forEach(function (v) {
      var productName = String(v || "").trim();
      if (!productName) return;
      var meta = productMetaMap[productName] || {};
      if (!currentItemGroup || !meta.item_group || meta.item_group === currentItemGroup) {
        productSet[productName] = true;
      }
    });
    (state.filterOptions.process_types || []).forEach(function (v) { if (v) processSet[String(v)] = true; });

    (state.rows || []).forEach(function (r) {
      var emp = String(r.employee || "").trim();
      var name1 = String(r.name1 || "").trim();
      var itemGroup = String(r.item_group || "").trim();
      var product = String(r.product || "").trim();
      var processType = String(r.process_type || "").trim();
      var processSize = String(r.process_size || "").trim() || "No Size";
      var rate = num(r.rate);

      if (emp) {
        employeeSet[emp] = true;
        if (name1) employeeNameMap[emp] = name1;
      }
      if (itemGroup) itemGroupSet[itemGroup] = true;
      if (product && (!currentItemGroup || !itemGroup || itemGroup === currentItemGroup) && (!hasSelected || selectedMap[product])) productSet[product] = true;
      if (processType) processSet[processType] = true;
      if (processSize) processSizeSet[processSize] = true;
      if (product) {
        if (!productMetaMap[product]) productMetaMap[product] = {};
        if (itemGroup && !productMetaMap[product].item_group) productMetaMap[product].item_group = itemGroup;
        if (processType && !productMetaMap[product].process_type) productMetaMap[product].process_type = processType;
        if (processSize && !productMetaMap[product].process_size) productMetaMap[product].process_size = processSize;
        if (rate > 0 && !productMetaMap[product].rate) productMetaMap[product].rate = rate;
      }
    });

    state.entryMeta.employeeOptions = Object.keys(employeeSet).sort().map(function (emp) {
      var label = employeeNameMap[emp] ? (employeeNameMap[emp] + " (" + emp + ")") : emp;
      return { value: emp, label: label };
    });
    state.entryMeta.itemGroupOptions = Object.keys(itemGroupSet).sort().map(function (group) {
      return { value: group, label: group };
    });
    state.entryMeta.productOptions = Object.keys(productSet).sort().map(function (p) {
      return { value: p, label: p };
    });
    state.entryMeta.processOptions = Object.keys(processSet).sort().map(function (p) {
      return { value: p, label: p };
    });
    state.entryMeta.processSizeOptions = Object.keys(processSizeSet).sort(function (a, b) {
      var order = baseProcessSizeOptions();
      var ai = order.indexOf(a);
      var bi = order.indexOf(b);
      if (ai < 0 && bi < 0) return String(a).localeCompare(String(b));
      if (ai < 0) return 1;
      if (bi < 0) return -1;
      return ai - bi;
    }).map(function (value) {
      return { value: value, label: value };
    });
    state.entryMeta.employeeNameMap = employeeNameMap;
    state.entryMeta.productMetaMap = productMetaMap;
    state.entryMeta.productProcessMap = productProcessMap;
  }

  function groupRows(rows, keys, builder) {
    var map = {};
    function cleanGroupAmount(v) {
      var out = Math.round(num(v) * 100) / 100;
      return Math.abs(out) < 0.005 ? 0 : out;
    }
    function resolveBookedPaidUnpaid(row) {
      var amount = num(row.amount);
      var bookingStatus = String(row.booking_status || "");
      var jvPosted = !!((row.jv_entry_no || "") && String(row.jv_status || "") === "Posted");
      var isBooked = bookingStatus === "Booked" || jvPosted;
      var bookedVal = isBooked ? amount : 0;

      if (bookingStatus === "Partly Booked") {
        var rawBooked = num(row.booked_amount);
        if (rawBooked < 0) rawBooked = 0;
        if (rawBooked > amount) rawBooked = amount;
        bookedVal = rawBooked;
      }

      var paidVal = num(row.paid_amount);
      if (paidVal < 0) paidVal = 0;
      if (paidVal > bookedVal) paidVal = bookedVal;

      var unpaidVal = num(row.unpaid_amount);
      if (unpaidVal <= 0 || unpaidVal > bookedVal) {
        unpaidVal = Math.max(bookedVal - paidVal, 0);
      }

      return {
        booked: cleanGroupAmount(bookedVal),
        paid: cleanGroupAmount(paidVal),
        unpaid: cleanGroupAmount(unpaidVal),
        is_booked: isBooked
      };
    }
    (rows || []).forEach(function (r) {
      var key = keys.map(function (k) { return (r[k] || ""); }).join("||");
      if (!map[key]) map[key] = builder(r);
      if (map[key].booked_amount === undefined) map[key].booked_amount = 0;
      if (map[key].unbooked_amount === undefined) map[key].unbooked_amount = 0;
      if (map[key].paid_amount === undefined) map[key].paid_amount = 0;
      if (map[key].unpaid_amount === undefined) map[key].unpaid_amount = 0;
      if (map[key]._row_count === undefined) map[key]._row_count = 0;
      if (map[key]._booked_count === undefined) map[key]._booked_count = 0;
      if (map[key]._paid_count === undefined) map[key]._paid_count = 0;
      if (map[key]._unpaid_count === undefined) map[key]._unpaid_count = 0;
      if (map[key]._partly_count === undefined) map[key]._partly_count = 0;

      map[key]._row_count += 1;
      map[key].qty = num(map[key].qty) + num(r.qty);
      map[key].amount = num(map[key].amount) + num(r.amount);
      var amounts = resolveBookedPaidUnpaid(r);
      var bookedVal = amounts.booked;
      var paidVal = amounts.paid;
      var unpaidVal = amounts.unpaid;

      map[key].booked_amount = num(map[key].booked_amount) + bookedVal;
      map[key].unbooked_amount = cleanGroupAmount(num(map[key].unbooked_amount) + Math.max(num(r.amount) - bookedVal, 0));
      map[key].paid_amount = num(map[key].paid_amount) + paidVal;
      map[key].unpaid_amount = num(map[key].unpaid_amount) + unpaidVal;

      var isBooked = amounts.is_booked;
      if (isBooked) map[key]._booked_count += 1;
      var payStatus = String(r.payment_status || "Unpaid");
      if (payStatus === "Paid") map[key]._paid_count += 1;
      else if (payStatus === "Partly Paid") map[key]._partly_count += 1;
      else map[key]._unpaid_count += 1;
    });
    return Object.keys(map).sort().map(function (k) {
      map[k].amount = cleanGroupAmount(map[k].amount);
      map[k].booked_amount = cleanGroupAmount(map[k].booked_amount);
      map[k].paid_amount = cleanGroupAmount(map[k].paid_amount);
      map[k].unpaid_amount = cleanGroupAmount(map[k].unpaid_amount);
      map[k].rate = avgRate(map[k].qty, map[k].amount);
      map[k].unbooked_amount = cleanGroupAmount(Math.max(num(map[k].amount) - num(map[k].booked_amount), 0));
      if (map[k]._booked_count === map[k]._row_count) map[k].booking_status = "Booked";
      else if (map[k]._booked_count === 0) map[k].booking_status = "UnBooked";
      else map[k].booking_status = "Partly Booked";

      if (map[k]._paid_count === map[k]._row_count) map[k].payment_status = "Paid";
      else if (map[k]._unpaid_count === map[k]._row_count) map[k].payment_status = "Unpaid";
      else map[k].payment_status = "Partly Paid";
      return map[k];
    });
  }

  function buildEmployeeSummaryRows(rows) {
    return groupRows(rows, ["employee", "name1"], function (r) {
      return { employee: r.employee || "", name1: r.name1 || "", qty: 0, amount: 0, rate: 0 };
    });
  }

  function monthFieldFromKey(key) {
    return "m_" + String(key || "").replace("-", "_");
  }

  function monthLabelFromKey(key) {
    var monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var k = String(key || "");
    if (!k || k.length < 7) return k;
    var yy = k.slice(2, 4);
    var mm = parseInt(k.slice(5, 7), 10) || 0;
    return (monthNames[mm - 1] || k.slice(5, 7)) + "-" + yy;
  }

  function monthsInFilterRange() {
    var args = getReportArgs();
    var fromDate = parseDateOnly(args.from_date || "");
    var toDate = parseDateOnly(args.to_date || "");
    if (!fromDate || !toDate) return [];
    if (fromDate > toDate) {
      var temp = fromDate;
      fromDate = toDate;
      toDate = temp;
    }
    var out = [];
    var y = fromDate.getFullYear();
    var m = fromDate.getMonth();
    var ey = toDate.getFullYear();
    var em = toDate.getMonth();
    while (y < ey || (y === ey && m <= em)) {
      var key = String(y) + "-" + pad2(m + 1);
      out.push({ key: key, label: monthLabelFromKey(key) });
      m += 1;
      if (m > 11) {
        m = 0;
        y += 1;
      }
    }
    return out;
  }

  function buildSimpleMonthColumns(rows) {
    var map = {};
    (monthsInFilterRange() || []).forEach(function (m) {
      map[m.key] = { key: m.key, label: m.label };
    });
    (rows || []).forEach(function (r) {
      var dt = parseDateOnly(r.to_date || r.from_date);
      if (!dt) return;
      var key = String(dt.getFullYear()) + "-" + pad2(dt.getMonth() + 1);
      if (!map[key]) map[key] = { key: key, label: monthLabelFromKey(key) };
    });
    return Object.keys(map).sort().map(function (k) { return map[k]; });
  }

  function buildSimpleMonthRows(rows, monthCols) {
    var map = {};
    function clean(v) {
      var out = Math.round(num(v) * 100) / 100;
      return Math.abs(out) < 0.005 ? 0 : out;
    }

    (rows || []).forEach(function (r) {
      var emp = String(r.employee || "").trim();
      var name = String(r.name1 || "").trim() || emp;
      if (!emp && !name) return;
      var keyEmp = emp || name;
      if (!map[keyEmp]) {
        map[keyEmp] = { employee: emp, name1: name || keyEmp };
        (monthCols || []).forEach(function (m) {
          map[keyEmp][monthFieldFromKey(m.key)] = 0;
        });
      }
      var dt = parseDateOnly(r.to_date || r.from_date);
      if (!dt) return;
      var monthKey = String(dt.getFullYear()) + "-" + pad2(dt.getMonth() + 1);
      var field = monthFieldFromKey(monthKey);
      if (map[keyEmp][field] === undefined) map[keyEmp][field] = 0;
      map[keyEmp][field] = clean(num(map[keyEmp][field]) + num(r.amount));
    });

    return Object.keys(map).sort(function (a, b) {
      var an = String(map[a].name1 || a);
      var bn = String(map[b].name1 || b);
      if (an < bn) return -1;
      if (an > bn) return 1;
      return 0;
    }).map(function (k) { return map[k]; });
  }

  function buildEmployeeMonthYearRows(rows) {
    var monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var monthMap = {};
    var subtotalMap = {};
    function cleanAmount(v) {
      var out = Math.round(num(v) * 100) / 100;
      return Math.abs(out) < 0.005 ? 0 : out;
    }

    function ensureStats(target) {
      if (target._row_count === undefined) target._row_count = 0;
      if (target._booked_count === undefined) target._booked_count = 0;
      if (target._paid_count === undefined) target._paid_count = 0;
      if (target._unpaid_count === undefined) target._unpaid_count = 0;
      if (target._partly_count === undefined) target._partly_count = 0;
    }

    function resolveAmounts(row) {
      var amount = num(row.amount);
      var bookingStatus = String(row.booking_status || "");
      var jvPosted = !!((row.jv_entry_no || "") && String(row.jv_status || "") === "Posted");
      var isBooked = bookingStatus === "Booked" || jvPosted;
      var bookedVal = isBooked ? amount : 0;

      if (bookingStatus === "Partly Booked") {
        var rawBooked = num(row.booked_amount);
        if (rawBooked < 0) rawBooked = 0;
        if (rawBooked > amount) rawBooked = amount;
        bookedVal = rawBooked;
      }

      var paidVal = num(row.paid_amount);
      if (paidVal < 0) paidVal = 0;
      if (paidVal > bookedVal) paidVal = bookedVal;

      var unpaidVal = num(row.unpaid_amount);
      if (unpaidVal <= 0 || unpaidVal > bookedVal) {
        unpaidVal = Math.max(bookedVal - paidVal, 0);
      }

      return {
        booked: cleanAmount(bookedVal),
        paid: cleanAmount(paidVal),
        unpaid: cleanAmount(unpaidVal),
        is_booked: isBooked
      };
    }

    function addStats(target, row, bookedVal, paidVal, unpaidVal) {
      ensureStats(target);
      target._row_count += 1;
      target.qty = num(target.qty) + num(row.qty);
      target.amount = num(target.amount) + num(row.amount);
      target.booked_amount = num(target.booked_amount) + bookedVal;
      var unbookedVal = num(row.amount) - bookedVal;
      if (unbookedVal < 0) unbookedVal = 0;
      target.unbooked_amount = cleanAmount(num(target.unbooked_amount) + unbookedVal);
      target.paid_amount = num(target.paid_amount) + paidVal;
      target.unpaid_amount = num(target.unpaid_amount) + unpaidVal;

      var isBooked = (String(row.booking_status || "") === "Booked") || ((row.jv_entry_no || "") && String(row.jv_status || "") === "Posted");
      if (isBooked) target._booked_count += 1;

      var payStatus = String(row.payment_status || "Unpaid");
      if (payStatus === "Paid") target._paid_count += 1;
      else if (payStatus === "Partly Paid") target._partly_count += 1;
      else target._unpaid_count += 1;
    }

    function finalizeStats(target) {
      target.amount = cleanAmount(target.amount);
      target.booked_amount = cleanAmount(target.booked_amount);
      target.paid_amount = cleanAmount(target.paid_amount);
      target.unpaid_amount = cleanAmount(target.unpaid_amount);
      target.rate = avgRate(target.qty, target.amount);
      var unbooked = num(target.amount) - num(target.booked_amount);
      if (unbooked < 0) unbooked = 0;
      target.unbooked_amount = cleanAmount(unbooked);
      if (target._booked_count === target._row_count) target.booking_status = "Booked";
      else if (target._booked_count === 0) target.booking_status = "UnBooked";
      else target.booking_status = "Partly Booked";

      if (target._paid_count === target._row_count) target.payment_status = "Paid";
      else if (target._unpaid_count === target._row_count) target.payment_status = "Unpaid";
      else target.payment_status = "Partly Paid";
    }

    (rows || []).forEach(function (r) {
      var emp = String(r.employee || "").trim();
      if (!emp) return;
      var name = String(r.name1 || "").trim() || emp;
      var dt = parseDateOnly(r.to_date || r.from_date);
      if (!dt) return;
      var yy = String(dt.getFullYear());
      var mmNo = dt.getMonth() + 1;
      var mm = pad2(mmNo);
      var mmLabel = monthNames[mmNo - 1] + "-" + yy.slice(-2);

      var resolved = resolveAmounts(r);
      var bookedVal = resolved.booked;
      var paidVal = resolved.paid;
      var unpaidVal = resolved.unpaid;

      var monthKey = emp + "||" + name + "||" + yy + "||" + mm;
      if (!monthMap[monthKey]) {
        monthMap[monthKey] = {
          employee: emp,
          name1: name,
          year: yy,
          month: mmLabel,
          month_year: mmLabel,
          month_no: mmNo,
          period_key: yy + "-" + mm,
          period_type: "Month",
          qty: 0,
          rate: 0,
          amount: 0,
          booked_amount: 0,
          unbooked_amount: 0,
          paid_amount: 0,
          unpaid_amount: 0,
        };
      }
      addStats(monthMap[monthKey], r, bookedVal, paidVal, unpaidVal);

      var subtotalKey = yy + "||" + mm;
      if (!subtotalMap[subtotalKey]) {
        subtotalMap[subtotalKey] = {
          employee: "",
          name1: "Month Sub Total",
          year: yy,
          month: mmLabel,
          month_year: mmLabel + " Sub Total",
          month_no: mmNo,
          period_key: yy + "-" + mm,
          period_type: "Subtotal",
          qty: 0,
          rate: 0,
          amount: 0,
          booked_amount: 0,
          unbooked_amount: 0,
          paid_amount: 0,
          unpaid_amount: 0,
        };
      }
      addStats(subtotalMap[subtotalKey], r, bookedVal, paidVal, unpaidVal);
    });

    var monthRows = Object.keys(monthMap).map(function (k) {
      finalizeStats(monthMap[k]);
      return monthMap[k];
    });

    monthRows.sort(function (a, b) {
      if (String(a.year || "") < String(b.year || "")) return -1;
      if (String(a.year || "") > String(b.year || "")) return 1;
      if (num(a.month_no) < num(b.month_no)) return -1;
      if (num(a.month_no) > num(b.month_no)) return 1;
      var an = String(a.name1 || a.employee || "");
      var bn = String(b.name1 || b.employee || "");
      if (an < bn) return -1;
      if (an > bn) return 1;
      return 0;
    });

    var subtotalByPeriod = {};
    Object.keys(subtotalMap).forEach(function (k) {
      finalizeStats(subtotalMap[k]);
      var row = subtotalMap[k];
      subtotalByPeriod[row.period_key] = row;
    });

    var out = [];
    var lastPeriodKey = "";
    monthRows.forEach(function (r) {
      var key = r.period_key;
      if (lastPeriodKey && key !== lastPeriodKey && subtotalByPeriod[lastPeriodKey]) {
        out.push(subtotalByPeriod[lastPeriodKey]);
      }
      out.push(r);
      lastPeriodKey = key;
    });
    if (lastPeriodKey && subtotalByPeriod[lastPeriodKey]) {
      out.push(subtotalByPeriod[lastPeriodKey]);
    }

    return out;
  }

  function buildMonthPaidUnpaidRows(rows) {
    var monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var map = {};
    (rows || []).forEach(function (r) {
      var dt = parseDateOnly(r.to_date || r.from_date);
      if (!dt) return;
      var yy = String(dt.getFullYear());
      var mmNo = dt.getMonth() + 1;
      var mm = pad2(mmNo);
      var key = yy + "-" + mm;
      if (!map[key]) {
        map[key] = {
          month_year: monthNames[mmNo - 1] + "-" + yy.slice(-2),
          period_key: key,
          booked_amount: 0,
          paid_amount: 0,
          unpaid_amount: 0
        };
      }
      map[key].booked_amount += num(r.booked_amount);
      map[key].paid_amount += num(r.paid_amount);
      map[key].unpaid_amount += num(r.unpaid_amount);
    });

    return Object.keys(map).sort().map(function (k) {
      var row = map[k];
      row.booked_amount = Math.round(num(row.booked_amount) * 100) / 100;
      row.paid_amount = Math.round(num(row.paid_amount) * 100) / 100;
      row.unpaid_amount = Math.round(num(row.unpaid_amount) * 100) / 100;
      return row;
    });
  }

  function buildAdvanceRows(rows) {
    var map = {};
    var selectedEmployee = (el("pp-employee") && el("pp-employee").value) ? String(el("pp-employee").value) : "";
    var months = state.advanceMonths || [];

    (state.advanceRows || []).forEach(function (r) {
      var emp = String(r.employee || "").trim();
      if (!emp) return;
      if (selectedEmployee && emp !== selectedEmployee) return;
      if (!map[emp]) {
        map[emp] = {
          employee: emp,
          name1: r.name1 || (state.entryMeta.employeeNameMap || {})[emp] || emp,
          branch: r.branch || "",
          opening_balance: num(r.opening_balance),
          closing_balance: num(r.closing_balance || r.advance_balance),
          advance_balance: num(r.advance_balance)
        };
      } else if (!map[emp].name1 && r.name1) {
        map[emp].name1 = r.name1 || map[emp].name1;
      } else {
        map[emp].advance_balance = num(r.advance_balance);
      }
      months.forEach(function (m) {
        var key = m && m.key ? m.key : "";
        if (!key) return;
        var field = advanceMonthField(key);
        map[emp][field] = num((r.month_values || {})[key]);
      });
    });

    return Object.keys(map).sort().map(function (emp) {
      return {
        employee: emp,
        name1: map[emp].name1 || emp,
        branch: map[emp].branch || "",
        opening_balance: num(map[emp].opening_balance),
        closing_balance: num(map[emp].closing_balance || map[emp].advance_balance),
        advance_balance: num(map[emp].advance_balance),
        _raw: map[emp],
      };
    });
  }

  function getUnpostedRows() {
    return getRowsByHeaderFilters(state.rows || []).filter(function (r) {
      var status = r && r.jv_status ? String(r.jv_status) : "Pending";
      var hasJV = !!(r && r.jv_entry_no);
      return !hasJV && status !== "Posted";
    });
  }

  function getBookedRows() {
    return getRowsByHeaderFilters(state.rows || []).filter(function (r) {
      var status = r && r.jv_status ? String(r.jv_status) : "Pending";
      var hasJV = !!(r && r.jv_entry_no);
      return hasJV && status === "Posted";
    });
  }

  function buildPaymentEmployeeRows(rows) {
    var map = {};
    (rows || []).forEach(function (r) {
      var emp = String(r.employee || "");
      if (!emp) return;
      if (!map[emp]) {
        map[emp] = {
          employee: emp,
          name1: r.name1 || "",
          booked_amount: 0,
          paid_amount: 0,
          unpaid_amount: 0,
          payment_status: "Unpaid"
        };
      }
      var booked = num(r.booked_amount || r.amount);
      var paid = num(r.paid_amount);
      var unpaid = num(r.unpaid_amount);
      if (!unpaid && booked >= paid) unpaid = booked - paid;
      map[emp].booked_amount += booked;
      map[emp].paid_amount += paid;
      map[emp].unpaid_amount += Math.max(unpaid, 0);
    });
    return Object.keys(map).sort().map(function (k) {
      var row = map[k];
      if (row.unpaid_amount <= 0 && row.booked_amount > 0) row.payment_status = "Paid";
      else if (row.paid_amount > 0 && row.unpaid_amount > 0) row.payment_status = "Partly Paid";
      else row.payment_status = "Unpaid";
      return row;
    });
  }

  function normalizePaymentAdjustments() {
    var previous = state.paymentAdjustments || {};
    var next = {};
    buildPaymentEmployeeRows(getBookedRows()).forEach(function (r) {
      var key = r.employee || "";
      var old = previous[key] || {};
      var hasOld = Object.prototype.hasOwnProperty.call(old, "payment_amount");
      var amount = hasOld ? whole(old.payment_amount) : whole(r.unpaid_amount);
      if (amount > num(r.unpaid_amount)) amount = whole(r.unpaid_amount);
      next[key] = { payment_amount: amount, unpaid_amount: num(r.unpaid_amount) };
    });
    state.paymentAdjustments = next;
  }

  function normalizePaymentExcludedEmployees() {
    var next = {};
    buildPaymentEmployeeRows(getBookedRows()).forEach(function (r) {
      var key = r.employee || "";
      if (state.paymentExcludedEmployees[key]) next[key] = true;
    });
    state.paymentExcludedEmployees = next;
  }

  function getPaymentRows() {
    return buildPaymentEmployeeRows(getBookedRows()).map(function (r) {
      var key = r.employee || "";
      var adj = state.paymentAdjustments[key] || {};
      var pay = whole(adj.payment_amount);
      if (pay > num(r.unpaid_amount)) pay = whole(r.unpaid_amount);
      return {
        employee: r.employee,
        name1: r.name1,
        booked_amount: num(r.booked_amount),
        paid_amount: num(r.paid_amount),
        unpaid_amount: num(r.unpaid_amount),
        payment_status: r.payment_status,
        payment_amount: pay
      };
    });
  }

  function isPaymentOpenRow(r) {
    var unpaid = num(r && r.unpaid_amount);
    var status = String((r && r.payment_status) || "Unpaid");
    if (status === "Paid" && unpaid <= 0) return false;
    return unpaid > 0 || status === "Unpaid" || status === "Partly Paid";
  }

  function getPaymentActiveRows() {
    return getPaymentRows().filter(isPaymentOpenRow);
  }

  function getPaymentPostingRows() {
    return getPaymentActiveRows().filter(function (r) {
      return !state.paymentExcludedEmployees[r.employee || ""] && num(r.payment_amount) > 0;
    });
  }

  function getPaymentTotals() {
    var totals = { booked: 0, paid: 0, unpaid: 0, payment: 0, debit: 0, credit: 0 };
    getPaymentActiveRows().forEach(function (r) {
      if (!state.paymentExcludedEmployees[r.employee || ""]) {
        totals.booked += num(r.booked_amount);
        totals.paid += num(r.paid_amount);
        totals.unpaid += num(r.unpaid_amount);
      }
    });
    getPaymentPostingRows().forEach(function (r) { totals.payment += num(r.payment_amount); });
    totals.debit = totals.payment;
    totals.credit = totals.payment;
    return totals;
  }

  function normalizeAdjustmentsForEmployees() {
    var previous = state.adjustments || {};
    var next = {};
    buildEmployeeSummaryRows(getUnpostedRows()).forEach(function (r) {
      var key = r.employee || "";
      var old = previous[key] || {};
      var rowBalance = num(r.advance_balance);
      var mapBalance = num((state.advanceBalances || {})[key]);
      var closingBalance = mapBalance || rowBalance || num(old.advance_balance);
      next[key] = {
        advance_balance: closingBalance,
        advance_deduction: whole(old.advance_deduction),
        allowance: whole(old.allowance),
        other_deduction: whole(old.other_deduction)
      };
    });
    state.adjustments = next;
  }

  function normalizeExcludedEmployees() {
    var next = {};
    buildEmployeeSummaryRows(getUnpostedRows()).forEach(function (r) {
      var key = r.employee || "";
      if (state.excludedEmployees[key]) next[key] = true;
    });
    state.excludedEmployees = next;
  }

  function withAdjustments(summaryRow) {
    var key = summaryRow.employee || "";
    var a = state.adjustments[key] || {};
    var salaryAmount = num(summaryRow.amount);
    var allowance = whole(a.allowance);
    var advanceBalance = Math.max(0, num(a.advance_balance));
    var advanceDeduction = whole(a.advance_deduction);
    var otherDeduction = whole(a.other_deduction);
    var gross = salaryAmount + allowance;
    if (advanceDeduction > advanceBalance) advanceDeduction = advanceBalance;
    if (advanceDeduction > gross) advanceDeduction = gross;
    if (otherDeduction > (gross - advanceDeduction)) otherDeduction = gross - advanceDeduction;
    var netAmount = gross - advanceDeduction - otherDeduction;
    return {
      employee: summaryRow.employee || "",
      name1: summaryRow.name1 || "",
      qty: num(summaryRow.qty),
      rate: avgRate(summaryRow.qty, summaryRow.amount),
      amount: salaryAmount,
      allowance: allowance,
      advance_balance: advanceBalance,
      advance_deduction: advanceDeduction,
      other_deduction: otherDeduction,
      gross_amount: gross,
      net_amount: netAmount
    };
  }

  function getAdjustedEmployeeRows() {
    return buildEmployeeSummaryRows(getUnpostedRows()).map(withAdjustments);
  }

  function getPostingEmployeeRows() {
    return getAdjustedEmployeeRows().filter(function (r) {
      return !state.excludedEmployees[r.employee || ""];
    });
  }

  function getAdjustedTotals() {
    var totals = {
      qty: 0,
      base_amount: 0,
      allowance_amount: 0,
      gross_amount: 0,
      advance_deduction_amount: 0,
      other_deduction_amount: 0,
      net_payable_amount: 0,
      jv_gross_amount: 0,
      debit_amount: 0,
      credit_amount: 0
    };
    getPostingEmployeeRows().forEach(function (r) {
      totals.qty += num(r.qty);
      totals.base_amount += num(r.amount);
      totals.allowance_amount += num(r.allowance);
      totals.gross_amount += num(r.gross_amount);
      totals.advance_deduction_amount += num(r.advance_deduction);
      totals.other_deduction_amount += num(r.other_deduction);
      totals.net_payable_amount += num(r.net_amount);
    });
    totals.jv_gross_amount = totals.gross_amount;
    totals.debit_amount = totals.net_payable_amount;
    totals.credit_amount = totals.net_payable_amount;
    return totals;
  }

  function renderTable(columns, rows) {
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    var html = "<table class='pp-table'><thead><tr>";
    columns.forEach(function (c) { html += "<th>" + esc(c.label) + "</th>"; });
    html += "</tr></thead><tbody>";
    rows.forEach(function (r) {
      var ptype = String(r.period_type || "");
      var rowClass = (ptype === "Subtotal" || ptype === "Year" || !!r._is_total) ? " class='pp-year-total'" : "";
      html += "<tr" + rowClass + ">";
      columns.forEach(function (c) {
        var val = r[c.fieldname];
        if ((c.fieldname === "jv_entry_no" || c.fieldname === "payment_jv_no") && val) {
          html += "<td><a target='_blank' href='/app/journal-entry/" + encodeURIComponent(val) + "'>" + esc(val) + "</a></td>";
        } else if (c.summary_link && val) {
          html += "<td><button type='button' class='btn btn-xs btn-default pp-doc-summary' data-doc='" + encodeURIComponent(String(val)) + "'>" + esc(val) + "</button></td>";
        } else if (isStatusField(c.fieldname)) {
          html += "<td>" + statusBadgeHtml(val || "") + "</td>";
        } else {
          var classes = [];
          if (c.numeric) classes.push("num");
          if (isAmountField(c.fieldname)) classes.push("pp-amt-col");
          var cls = classes.length ? " class='" + classes.join(" ") + "'" : "";
          html += "<td" + cls + ">" + esc(c.numeric ? fmt(val) : (val || "")) + "</td>";
        }
      });
      html += "</tr>";
    });
    var hasExistingTotal = (rows || []).some(function (r) { return !!(r && r._is_total); });
    if (!hasExistingTotal) {
      var sums = {};
      var firstLabelDone = false;
      columns.forEach(function (c) { if (c && c.fieldname) sums[c.fieldname] = 0; });
      (rows || []).forEach(function (r) {
        if (!r) return;
        var ptype = String(r.period_type || "");
        if (ptype === "Subtotal" || ptype === "Year") return;
        columns.forEach(function (c) {
          if (!c || !c.numeric) return;
          sums[c.fieldname] = num(sums[c.fieldname]) + num(r[c.fieldname]);
        });
      });
      html += "<tr class='pp-year-total'>";
      columns.forEach(function (c) {
        if (!c) {
          html += "<td></td>";
          return;
        }
        if (!firstLabelDone && !c.numeric) {
          html += "<td>Total</td>";
          firstLabelDone = true;
          return;
        }
        if (c.numeric) {
          var cls = "num";
          if (isAmountField(c.fieldname)) cls += " pp-amt-col";
          html += "<td class='" + cls + "'>" + esc(fmt(sums[c.fieldname])) + "</td>";
          return;
        }
        html += "<td></td>";
      });
      html += "</tr>";
    }
    html += "</tbody></table>";
    wrap.innerHTML = html;

    wrap.querySelectorAll(".pp-doc-summary").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var docName = decodeURIComponent(btn.getAttribute("data-doc") || "");
        showPerPieceSummary(docName);
      });
    });
  }

  function renderSalaryTable(rows) {
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    var html = "<table class='pp-table'><thead><tr>"
      + "<th>Use In JV</th><th>Employee</th><th>Qty</th><th>Rate</th><th>Salary Amount</th>"
      + "<th>Advance Balance</th><th>Advance Deduction</th><th>Allowance</th><th>Other Deduction</th><th>Net Amount</th>"
      + "</tr></thead><tbody>";
    rows.forEach(function (r) {
      var emp = r.employee || "";
      var label = employeeLabel(r) || "(Blank)";
      var checked = state.excludedEmployees[emp] ? "" : " checked";
      html += "<tr>"
        + "<td><input class='pp-include-emp' type='checkbox' data-employee='" + esc(emp) + "'" + checked + "></td>"
        + "<td>" + esc(label) + "</td>"
        + "<td class='num'>" + esc(fmt(r.qty)) + "</td>"
        + "<td class='num'>" + esc(fmt(r.rate)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.advance_balance)) + "</td>"
        + "<td><input class='pp-adj-input' type='number' min='0' step='0.01' inputmode='decimal' data-employee='" + esc(emp) + "' data-field='advance_deduction' value='" + esc(whole(r.advance_deduction)) + "'></td>"
        + "<td><input class='pp-adj-input' type='number' min='0' step='0.01' inputmode='decimal' data-employee='" + esc(emp) + "' data-field='allowance' value='" + esc(whole(r.allowance)) + "'></td>"
        + "<td><input class='pp-adj-input' type='number' min='0' step='0.01' inputmode='decimal' data-employee='" + esc(emp) + "' data-field='other_deduction' value='" + esc(whole(r.other_deduction)) + "'></td>"
        + "<td class='num pp-net-cell pp-amt-col' data-employee='" + esc(emp) + "'>" + esc(fmt(r.net_amount)) + "</td>"
        + "</tr>";
    });
    var tQty = 0, tRate = 0, tAmount = 0, tAdvanceBal = 0, tAdvanceDed = 0, tAllowance = 0, tOtherDed = 0, tNet = 0;
    rows.forEach(function (r) {
      tQty += num(r.qty);
      tRate += num(r.rate);
      tAmount += num(r.amount);
      tAdvanceBal += num(r.advance_balance);
      tAdvanceDed += num(r.advance_deduction);
      tAllowance += num(r.allowance);
      tOtherDed += num(r.other_deduction);
      tNet += num(r.net_amount);
    });
    html += "<tr class='pp-year-total'>"
      + "<td></td>"
      + "<td>Total</td>"
      + "<td class='num'>" + esc(fmt(tQty)) + "</td>"
      + "<td class='num'>" + esc(fmt(tRate)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tAmount)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tAdvanceBal)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tAdvanceDed)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tAllowance)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tOtherDed)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tNet)) + "</td>"
      + "</tr>";
    html += "</tbody></table>";
    wrap.innerHTML = html;

    wrap.querySelectorAll(".pp-include-emp").forEach(function (input) {
      input.addEventListener("change", function () {
        var emp = input.getAttribute("data-employee") || "";
        if (input.checked) delete state.excludedEmployees[emp];
        else state.excludedEmployees[emp] = true;
        renderCurrentTab();
      });
    });

    wrap.querySelectorAll(".pp-adj-input").forEach(function (input) {
      function onAdjustInput() {
        var emp = input.getAttribute("data-employee") || "";
        var field = input.getAttribute("data-field") || "";
        if (!state.adjustments[emp]) {
          state.adjustments[emp] = { advance_balance: 0, advance_deduction: 0, allowance: 0, other_deduction: 0 };
        }
        state.adjustments[emp][field] = whole(input.value);
        var rowMap = {};
        getAdjustedEmployeeRows().forEach(function (r) { rowMap[r.employee || ""] = r; });
        var updated = rowMap[emp];
        wrap.querySelectorAll(".pp-net-cell").forEach(function (cell) {
          if ((cell.getAttribute("data-employee") || "") === emp) {
            cell.textContent = fmt(updated ? updated.net_amount : 0);
          }
        });
        var t = getAdjustedTotals();
        el("pp-totals").innerHTML = "<span>Gross: " + fmt(t.gross_amount) + "</span>"
          + "<span>Advance Deduction: " + fmt(t.advance_deduction_amount) + "</span>"
          + "<span>Other Deduction: " + fmt(t.other_deduction_amount) + "</span>"
          + "<span>Net Payable: " + fmt(t.net_payable_amount) + "</span>";
        refreshJVAmountsFromAdjustments();
      }
      input.addEventListener("input", onAdjustInput);
      input.addEventListener("change", onAdjustInput);
    });
  }

  function renderPaymentTable(rows) {
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    var html = "<table class='pp-table'><thead><tr>"
      + "<th>Use In Payment</th><th>Employee</th><th>Booked Amount</th><th>Paid Amount</th><th>Unpaid Amount</th><th>Payment Amount</th><th>Status</th>"
      + "</tr></thead><tbody>";
    rows.forEach(function (r) {
      var emp = r.employee || "";
      var checked = state.paymentExcludedEmployees[emp] ? "" : " checked";
      html += "<tr>"
        + "<td><input class='pp-pay-include' type='checkbox' data-employee='" + esc(emp) + "'" + checked + "></td>"
        + "<td>" + esc(employeeLabel(r) || emp || "(Blank)") + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.booked_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.paid_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.unpaid_amount)) + "</td>"
        + "<td><input class='pp-pay-amount pp-pay-input' type='number' min='0' step='0.01' inputmode='decimal' data-employee='" + esc(emp) + "' value='" + esc(whole(r.payment_amount)) + "'></td>"
        + "<td>" + statusBadgeHtml(r.payment_status || "") + "</td>"
        + "</tr>";
    });
    var tBooked = 0, tPaid = 0, tUnpaid = 0, tPay = 0;
    rows.forEach(function (r) {
      tBooked += num(r.booked_amount);
      tPaid += num(r.paid_amount);
      tUnpaid += num(r.unpaid_amount);
      tPay += num(r.payment_amount);
    });
    html += "<tr class='pp-year-total'>"
      + "<td></td>"
      + "<td>Total</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tBooked)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tPaid)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tUnpaid)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(tPay)) + "</td>"
      + "<td></td>"
      + "</tr>";
    html += "</tbody></table>";
    wrap.innerHTML = html;

    wrap.querySelectorAll(".pp-pay-include").forEach(function (input) {
      input.addEventListener("change", function () {
        var emp = input.getAttribute("data-employee") || "";
        if (input.checked) delete state.paymentExcludedEmployees[emp];
        else state.paymentExcludedEmployees[emp] = true;
        renderCurrentTab();
      });
    });

    wrap.querySelectorAll(".pp-pay-amount").forEach(function (input) {
      function onPayInput() {
        var emp = input.getAttribute("data-employee") || "";
        var amount = whole(input.value);
        if (!state.paymentAdjustments[emp]) state.paymentAdjustments[emp] = { payment_amount: 0, unpaid_amount: 0 };
        state.paymentAdjustments[emp].payment_amount = amount;
        var totals = getPaymentTotals();
        el("pp-totals").innerHTML = "<span>Booked: " + fmt(totals.booked) + "</span>"
          + "<span>Paid: " + fmt(totals.paid) + "</span>"
          + "<span>Unpaid: " + fmt(totals.unpaid) + "</span>"
          + "<span>Payment This JV: " + fmt(totals.payment) + "</span>";
        refreshPaymentAmounts();
      }
      input.addEventListener("input", onPayInput);
      input.addEventListener("change", onPayInput);
    });
  }

  function setJVAmounts(debit, credit, gross) {
    el("pp-jv-debit-amount").value = fmt(debit || 0);
    el("pp-jv-credit-amount").value = fmt(credit || 0);
    el("pp-jv-gross-amount").value = fmt(gross || 0);
  }

  function refreshJVAmountsFromAdjustments() {
    var totals = getAdjustedTotals();
    setJVAmounts(totals.debit_amount, totals.credit_amount, totals.jv_gross_amount);
  }

  function setPaymentAmounts(debit, credit, unpaid) {
    el("pp-pay-debit-amount").value = fmt(debit || 0);
    el("pp-pay-credit-amount").value = fmt(credit || 0);
    el("pp-pay-unpaid-amount").value = fmt(unpaid || 0);
  }

  function refreshPaymentAmounts() {
    var totals = getPaymentTotals();
    setPaymentAmounts(totals.debit, totals.credit, totals.unpaid);
  }

  function uniqueSalaryDocs() {
    var map = {};
    (state.rows || []).forEach(function (r) {
      var key = String(r.per_piece_salary || "");
      if (!key) return;
      if (!map[key]) {
        map[key] = {
          name: key,
          from_date: r.from_date || "",
          to_date: r.to_date || "",
          po_number: r.po_number || "",
          item_group: r.item_group || "",
          total_amount: 0
        };
      }
      map[key].total_amount += num(r.amount);
    });
    return Object.keys(map).sort().map(function (k) { return map[k]; });
  }

  function setPageForCurrentTab(page) {
    var tab = String(state.currentTab || "all");
    var p = parseInt(page || 1, 10);
    if (!p || p < 1) p = 1;
    state.pageByTab[tab] = p;
  }

  function paginateRows(rows) {
    var allRows = rows || [];
    var tab = String(state.currentTab || "all");
    var pageSize = Math.max(parseInt(state.pageSize || 20, 10) || 20, 1);
    var totalPages = Math.max(1, Math.ceil(allRows.length / pageSize));
    var page = parseInt(state.pageByTab[tab] || 1, 10);
    if (!page || page < 1) page = 1;
    if (page > totalPages) page = totalPages;
    state.pageByTab[tab] = page;
    var start = (page - 1) * pageSize;
    var end = Math.min(start + pageSize, allRows.length);
    return {
      rows: allRows.slice(start, end),
      total: allRows.length,
      page: page,
      totalPages: totalPages,
      start: start + 1,
      end: end
    };
  }

  function renderPagination(meta) {
    var wrap = el("pp-pagination");
    if (!wrap) return;
    if (!meta || meta.total <= 0) {
      wrap.innerHTML = "";
      return;
    }
    var prevDisabled = meta.page <= 1 ? " disabled" : "";
    var nextDisabled = meta.page >= meta.totalPages ? " disabled" : "";
    wrap.innerHTML = "<span>Rows " + esc(meta.start) + "-" + esc(meta.end) + " of " + esc(meta.total) + "</span>"
      + "<button type='button' class='btn btn-default btn-xs' id='pp-page-prev'" + prevDisabled + ">Previous</button>"
      + "<span>Page " + esc(meta.page) + " / " + esc(meta.totalPages) + "</span>"
      + "<button type='button' class='btn btn-default btn-xs' id='pp-page-next'" + nextDisabled + ">Next</button>";
    var prev = el("pp-page-prev");
    var next = el("pp-page-next");
    if (prev) {
      prev.addEventListener("click", function () {
        setPageForCurrentTab((meta.page || 1) - 1);
        renderCurrentTab();
      });
    }
    if (next) {
      next.addEventListener("click", function () {
        setPageForCurrentTab((meta.page || 1) + 1);
        renderCurrentTab();
      });
    }
  }

  function showPerPieceSummary(docName) {
    var rows = (state.rows || []).filter(function (r) {
      return String(r.per_piece_salary || "") === String(docName || "");
    });
    var modal = el("pp-summary-modal");
    var subtitle = el("pp-summary-subtitle");
    var content = el("pp-summary-content");
    if (!modal || !subtitle || !content) return;

    if (!docName) return;
    if (!rows.length) {
      subtitle.textContent = docName;
      content.innerHTML = "<div style='color:#b91c1c;'>No rows available for this entry under selected filters.</div>";
      modal.style.display = "flex";
      return;
    }

    var first = rows[0] || {};
    var totalQty = 0;
    var totalAmount = 0;
    var totalBooked = 0;
    var totalPaid = 0;
    var totalUnpaid = 0;
    rows.forEach(function (r) {
      totalQty += num(r.qty);
      totalAmount += num(r.amount);
      totalBooked += num(r.booked_amount);
      totalPaid += num(r.paid_amount);
      totalUnpaid += num(r.unpaid_amount);
    });

    subtitle.textContent = docName + " | " + (first.from_date || "") + " to " + (first.to_date || "");
    var html = ""
      + "<div class='pp-summary-chips'>"
      + "<span class='pp-summary-chip'>PO: " + esc(first.po_number || "-") + "</span>"
      + "<span class='pp-summary-chip'>Item Group: " + esc(first.item_group || "-") + "</span>"
      + "<span class='pp-summary-chip'>Rows: " + esc(rows.length) + "</span>"
      + "<span class='pp-summary-chip'>Qty: " + esc(fmt(totalQty)) + "</span>"
      + "<span class='pp-summary-chip'>Amount: " + esc(fmt(totalAmount)) + "</span>"
      + "<span class='pp-summary-chip'>Booked: " + esc(fmt(totalBooked)) + "</span>"
      + "<span class='pp-summary-chip'>Paid: " + esc(fmt(totalPaid)) + "</span>"
      + "<span class='pp-summary-chip'>Unpaid: " + esc(fmt(totalUnpaid)) + "</span>"
      + "</div>";

    html += "<table class='pp-table'><thead><tr>"
      + "<th>Employee</th><th>Product</th><th>Process</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Booking</th><th>Payment</th>"
      + "</tr></thead><tbody>";
    rows.forEach(function (r) {
      html += "<tr>"
        + "<td>" + esc(employeeLabel(r) || "") + "</td>"
        + "<td>" + esc(r.product || "") + "</td>"
        + "<td>" + esc(r.process_type || "") + "</td>"
        + "<td>" + esc(r.process_size || "No Size") + "</td>"
        + "<td class='num'>" + esc(fmt(r.qty)) + "</td>"
        + "<td class='num'>" + esc(fmt(r.rate)) + "</td>"
        + "<td class='num'>" + esc(fmt(r.amount)) + "</td>"
        + "<td>" + esc(r.booking_status || "") + "</td>"
        + "<td>" + esc(r.payment_status || "") + "</td>"
        + "</tr>";
    });
    html += "</tbody></table>";
    content.innerHTML = html;
    modal.style.display = "flex";
  }

  function hidePerPieceSummary() {
    var modal = el("pp-summary-modal");
    if (modal) modal.style.display = "none";
  }

  function setCreatedListHtml(html) {
    var wrap = el("pp-created-list-wrap");
    if (!wrap) return;
    wrap.innerHTML = html || "";
    wrap.querySelectorAll(".pp-view-jv").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var jv = btn.getAttribute("data-jv") || "";
        if (!jv) return;
        showJournalEntrySummary(jv);
      });
    });
  }

  function uniqueJournalEntries(fieldname) {
    var map = {};
    (state.rows || []).forEach(function (r) {
      var jv = String((r && r[fieldname]) || "").trim();
      if (!jv) return;
      if (!map[jv]) map[jv] = { name: jv, amount: 0, rows: 0 };
      map[jv].amount += num(fieldname === "payment_jv_no" ? r.paid_amount : r.booked_amount);
      map[jv].rows += 1;
    });
    return Object.keys(map).sort().map(function (k) { return map[k]; });
  }

  function showJournalEntrySummary(jvName) {
    var modal = el("pp-summary-modal");
    var subtitle = el("pp-summary-subtitle");
    var content = el("pp-summary-content");
    if (!modal || !subtitle || !content || !jvName) return;
    subtitle.textContent = "Journal Entry: " + jvName;
    content.innerHTML = "<div style='color:#334155;'>Loading JV detail...</div>";
    modal.style.display = "flex";
    callApi("frappe.client.get", { doctype: "Journal Entry", name: jvName }).then(function (doc) {
      if (!doc) {
        content.innerHTML = "<div style='color:#b91c1c;'>JV not found.</div>";
        return;
      }
      var totalDr = 0;
      var totalCr = 0;
      var html = "<div class='pp-summary-chips'>"
        + "<span class='pp-summary-chip'>Voucher: " + esc(doc.voucher_type || "Journal Entry") + "</span>"
        + "<span class='pp-summary-chip'>Posting Date: " + esc(doc.posting_date || "-") + "</span>"
        + "<span class='pp-summary-chip'>Company: " + esc(doc.company || "-") + "</span>"
        + "<span class='pp-summary-chip'>Docstatus: " + esc(String(doc.docstatus || 0)) + "</span>"
        + "</div>";
      html += "<table class='pp-table'><thead><tr><th>Account</th><th>Party</th><th>Debit</th><th>Credit</th><th>Remark</th></tr></thead><tbody>";
      (doc.accounts || []).forEach(function (a) {
        var dr = num(a.debit_in_account_currency || a.debit || 0);
        var cr = num(a.credit_in_account_currency || a.credit || 0);
        totalDr += dr;
        totalCr += cr;
        var party = "";
        if (a.party_type || a.party) party = String(a.party_type || "") + (a.party ? (": " + a.party) : "");
        html += "<tr>"
          + "<td>" + esc(a.account || "") + "</td>"
          + "<td>" + esc(party) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(dr)) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(cr)) + "</td>"
          + "<td>" + esc(a.user_remark || "") + "</td>"
          + "</tr>";
      });
      html += "<tr class='pp-year-total'><td>Total</td><td></td><td class='num pp-amt-col'>" + esc(fmt(totalDr)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totalCr)) + "</td><td></td></tr>";
      html += "</tbody></table>";
      content.innerHTML = html;
    }).catch(function (e) {
      content.innerHTML = "<div style='color:#b91c1c;'>Unable to load JV detail: " + esc(prettyError(errText(e))) + "</div>";
    });
  }

  function renderJournalEntryInline(resultEl, jvName) {
    if (!resultEl || !jvName) return;
    callApi("frappe.client.get", { doctype: "Journal Entry", name: jvName }).then(function (doc) {
      if (!doc) return;
      var totalDr = 0;
      var totalCr = 0;
      var html = "<br><br><strong>Posted JV Quick Preview</strong>";
      html += "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Account</th><th>Party</th><th>Debit</th><th>Credit</th></tr></thead><tbody>";
      (doc.accounts || []).forEach(function (a) {
        var dr = num(a.debit_in_account_currency || a.debit || 0);
        var cr = num(a.credit_in_account_currency || a.credit || 0);
        totalDr += dr;
        totalCr += cr;
        var party = "";
        if (a.party_type || a.party) party = String(a.party_type || "") + (a.party ? (": " + a.party) : "");
        html += "<tr><td>" + esc(a.account || "") + "</td><td>" + esc(party) + "</td><td class='num pp-amt-col'>" + esc(fmt(dr)) + "</td><td class='num pp-amt-col'>" + esc(fmt(cr)) + "</td></tr>";
      });
      html += "<tr class='pp-year-total'><td>Total</td><td></td><td class='num pp-amt-col'>" + esc(fmt(totalDr)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totalCr)) + "</td></tr></tbody></table>";
      resultEl.innerHTML += html;
    }).catch(function (_e) {});
  }

  function renderCreatedEntriesPanel(tab) {
    if (tab === "data_entry") {
      setCreatedListHtml("");
      return;
    }
    if (tab === "salary_creation") {
      var jvRows = uniqueJournalEntries("jv_entry_no");
      if (!jvRows.length) {
        setCreatedListHtml("<div style='margin-top:8px;color:#64748b;'>No booking JV created in selected filter.</div>");
        return;
      }
      var html = "<div style='margin-top:10px;'><strong>Created Booking JV Entries</strong></div>"
        + "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>JV Entry</th><th>Booked Amount</th><th>Rows</th><th>View</th><th>Open</th></tr></thead><tbody>";
      jvRows.forEach(function (r) {
        html += "<tr><td>" + esc(r.name) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td><td class='num'>" + esc(r.rows) + "</td><td><button type='button' class='btn btn-xs btn-default pp-view-jv' data-jv='" + esc(r.name) + "'>View Debit/Credit</button></td><td><a target='_blank' href='/app/journal-entry/" + encodeURIComponent(r.name) + "'>Open</a></td></tr>";
      });
      html += "</tbody></table>";
      setCreatedListHtml(html);
      return;
    }
    if (tab === "payment_manage") {
      var payRows = uniqueJournalEntries("payment_jv_no");
      if (!payRows.length) {
        setCreatedListHtml("<div style='margin-top:8px;color:#64748b;'>No payment JV created in selected filter.</div>");
        return;
      }
      var phtml = "<div style='margin-top:10px;'><strong>Created Payment JV Entries</strong></div>"
        + "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Payment JV</th><th>Paid Amount</th><th>Rows</th><th>View</th><th>Open</th></tr></thead><tbody>";
      payRows.forEach(function (r) {
        phtml += "<tr><td>" + esc(r.name) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td><td class='num'>" + esc(r.rows) + "</td><td><button type='button' class='btn btn-xs btn-default pp-view-jv' data-jv='" + esc(r.name) + "'>View Debit/Credit</button></td><td><a target='_blank' href='/app/journal-entry/" + encodeURIComponent(r.name) + "'>Open</a></td></tr>";
      });
      phtml += "</tbody></table>";
      setCreatedListHtml(phtml);
      return;
    }
    setCreatedListHtml("");
  }

  function getAutoEntryProduct() {
    var productOptions = state.entryMeta.productOptions || [];
    return productOptions.length === 1 ? String((productOptions[0] && productOptions[0].value) || "").trim() : "";
  }

  function getCurrentGroupItems() {
    var loadByItem = state.entryMeta.load_by_item !== false;
    var selectedItem = String(state.entryMeta.item || "").trim();
    var currentItemGroup = String(state.entryMeta.item_group || "").trim();
    return (state.entryMeta.masterProcessRows || []).filter(function (item) {
      var itemName = String((item && item.item) || "").trim();
      if (!itemName) return false;
      var itemGroup = String((item && item.item_group) || "").trim();
      if (loadByItem) {
        if (!selectedItem) return false;
        if (itemName !== selectedItem) return false;
        if (currentItemGroup && itemGroup && itemGroup !== currentItemGroup) return false;
      } else {
        if (!currentItemGroup) return false;
        if (itemGroup !== currentItemGroup) return false;
      }
      return true;
    });
  }

  function entryRowIsBlank(row) {
    if (!row) return true;
    return !(
      String(row.employee || "").trim() ||
      String(row.name1 || "").trim() ||
      String(row.product || "").trim() ||
      num(row.qty) ||
      num(row.rate) ||
      entryAmount(row)
    );
  }

  function syncEntryEmployeeToRows() {
    var employee = String(state.entryMeta.employee || "").trim();
    if (!employee) return;
    var employeeName = String(((state.entryMeta.employeeNameMap || {})[employee]) || "").trim();
    (state.entryRows || []).forEach(function (row) {
      row.employee = employee;
      if (employeeName) row.name1 = employeeName;
    });
  }

  function applyEntryItemDefaults(row) {
    if (!row) return;
    var productName = String(row.product || "").trim();
    var processRows = ((state.entryMeta.productProcessMap || {})[productName] || []).slice();
    var meta = (state.entryMeta.productMetaMap || {})[productName] || {};
    if (!productName) {
      row.process_type = "";
      row.process_size = "No Size";
      row.rate = 0;
      return;
    }
    if (processRows.length) {
      var currentType = String(row.process_type || "").trim();
      var currentSize = String(row.process_size || "").trim();
      var matches = processRows.slice();
      if (currentType) {
        var typed = matches.filter(function (entry) {
          return String(entry.process_type || "").trim() === currentType;
        });
        if (typed.length) matches = typed;
      }
      if (currentSize) {
        var sized = matches.filter(function (entry) {
          return String(entry.process_size || "No Size").trim() === currentSize;
        });
        if (sized.length) matches = sized;
      }
      var currentEmployee = String(row.employee || "").trim();
      if (currentEmployee) {
        var employeeMatched = matches.filter(function (entry) {
          return String(entry.employee || "").trim() === currentEmployee;
        });
        if (employeeMatched.length) matches = employeeMatched;
      }
      meta = matches[0] || processRows[0];
    }
    var selectedEmployee = String(state.entryMeta.employee || "").trim();
    if (meta.employee && (!String(row.employee || "").trim() || String(row.employee || "").trim() === selectedEmployee)) {
      row.employee = String(meta.employee || "").trim();
      row.name1 = String(meta.employee_name || (state.entryMeta.employeeNameMap || {})[row.employee] || "").trim();
    }
    if (meta.process_type) row.process_type = meta.process_type;
    row.process_size = meta.process_size || "No Size";
    if (num(meta.rate) > 0) row.rate = whole(meta.rate);
  }

  function syncEntryRowsToItemGroup() {
    var currentItemGroup = String(state.entryMeta.item_group || "").trim();
    var productMetaMap = state.entryMeta.productMetaMap || {};
    var allowedMap = {};
    (state.entryMeta.productOptions || []).forEach(function (opt) {
      var value = String((opt && opt.value) || "").trim();
      if (value) allowedMap[value] = true;
    });
    var autoProduct = getAutoEntryProduct();

    (state.entryRows || []).forEach(function (row) {
      var productName = String(row.product || "").trim();
      if (currentItemGroup && productName) {
        var meta = productMetaMap[productName] || {};
        var rowGroup = String(meta.item_group || "").trim();
        if (!allowedMap[productName] || (rowGroup && rowGroup !== currentItemGroup)) {
          row.product = "";
          row.process_type = "";
          row.process_size = "No Size";
          row.rate = 0;
          productName = "";
        }
      }

      if (!productName && autoProduct) {
        row.product = autoProduct;
        productName = autoProduct;
      }

      if (productName) {
        applyEntryItemDefaults(row);
      } else if (!row.process_size) {
        row.process_size = "No Size";
      }
    });
  }

  function populateEntryRowsFromItemGroup(forceReload) {
    var groupItems = getCurrentGroupItems();
    if (!groupItems.length) return;
    if (forceReload) {
      state.entryRows = [];
    }
    ensureEntryRows();
    var hasMeaningfulRows = (state.entryRows || []).some(function (row) {
      return !entryRowIsBlank(row);
    });
    if (hasMeaningfulRows) return;
    state.entryRows = groupItems.map(function (item) {
      var itemEmployee = String((item && item.employee) || "").trim();
      var fallbackEmployee = String(state.entryMeta.employee || "").trim();
      var finalEmployee = itemEmployee || fallbackEmployee;
      var row = {
        employee: finalEmployee,
        name1: String((item && item.employee_name) || ((state.entryMeta.employeeNameMap || {})[finalEmployee]) || "").trim(),
        product: String((item && item.item) || "").trim(),
        process_type: String((item && item.process_type) || "").trim(),
        process_size: String((item && item.process_size) || "").trim() || "No Size",
        qty: 0,
        rate: whole(item && item.rate),
      };
      return row;
    });
  }

  function newEntryRow() {
    var employee = String(state.entryMeta.employee || "").trim();
    var row = {
      employee: employee,
      name1: String(((state.entryMeta.employeeNameMap || {})[employee]) || "").trim(),
      product: "",
      process_type: "",
      process_size: "No Size",
      qty: 0,
      rate: 0
    };
    var autoProduct = getAutoEntryProduct();
    if (autoProduct) {
      row.product = autoProduct;
      applyEntryItemDefaults(row);
    }
    return row;
  }

  function ensureEntryRows() {
    if (!state.entryRows || !state.entryRows.length) state.entryRows = [newEntryRow()];
  }

  function entryAmount(row) {
    return num(row.qty) * num(row.rate);
  }

  function renderDataEntryTab() {
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    if (!state.entryMeta.from_date) state.entryMeta.from_date = el("pp-from-date").value || "";
    if (!state.entryMeta.to_date) state.entryMeta.to_date = el("pp-to-date").value || "";
    if (state.entryMeta.po_number === undefined) state.entryMeta.po_number = "";
    if (state.entryMeta.item_group === undefined) state.entryMeta.item_group = el("pp-item-group") ? (el("pp-item-group").value || "") : "";
    if (state.entryMeta.item === undefined) state.entryMeta.item = "";
    if (state.entryMeta.employee === undefined) state.entryMeta.employee = el("pp-employee") ? (el("pp-employee").value || "") : "";
    if (state.entryMeta.load_by_item === undefined) state.entryMeta.load_by_item = true;
    if (state.entryMeta.edit_name === undefined) state.entryMeta.edit_name = "";
    ensureEntryRows();
    rebuildEntryMetaLookups();
    populateEntryRowsFromItemGroup();
    var docs = uniqueSalaryDocs();
    var employeeOptions = state.entryMeta.employeeOptions || [];
    var itemGroupOptions = state.entryMeta.itemGroupOptions || [];
    var productOptions = state.entryMeta.productOptions || [];
    var processOptions = state.entryMeta.processOptions || [];
    var employeeNameMap = state.entryMeta.employeeNameMap || {};
    var itemOptions = [];
    (state.entryMeta.masterProcessRows || []).forEach(function (r) {
      var rowGroup = String((r && r.item_group) || "").trim();
      var selectedGroup = String(state.entryMeta.item_group || "").trim();
      if (selectedGroup && rowGroup !== selectedGroup) return;
      var itemName = String((r && r.item) || "").trim();
      if (itemName) itemOptions.push(itemName);
    });
    var itemMap = {};
    itemOptions.forEach(function (name) {
      var key = String(name || "").trim();
      if (key) itemMap[key] = true;
    });
    itemOptions = Object.keys(itemMap).sort().map(function (name) { return { value: name, label: name }; });
    var editing = !!(state.entryMeta.edit_name || "");
    syncEntryEmployeeToRows();
    syncEntryRowsToItemGroup();

    function selectHtml(options, value, idx, field) {
      var htmlParts = [];
      var selectedValue = String(value || "");
      var exists = false;
      htmlParts.push("<select class='pp-pay-input pp-entry-in' data-idx='" + idx + "' data-field='" + field + "'>");
      htmlParts.push("<option value=''>Select</option>");
      (options || []).forEach(function (opt) {
        var selected = String(opt.value || "") === selectedValue ? " selected" : "";
        if (selected) exists = true;
        htmlParts.push("<option value='" + esc(opt.value || "") + "'" + selected + ">" + esc(opt.label || opt.value || "") + "</option>");
      });
      if (selectedValue && !exists) {
        htmlParts.push("<option value='" + esc(selectedValue) + "' selected>" + esc(selectedValue) + "</option>");
      }
      htmlParts.push("</select>");
      return htmlParts.join("");
    }

    function readonlyHtml(value) {
      return "<input class='pp-pay-input pp-entry-view' readonly tabindex='-1' value='" + esc(value || "") + "'>";
    }

    function docsSelectHtml(selectedName) {
      var parts = [];
      parts.push("<select id='pp-entry-edit-name'>");
      parts.push("<option value=''>New Entry</option>");
      docs.forEach(function (d) {
        var selected = String(d.name || "") === String(selectedName || "") ? " selected" : "";
        parts.push("<option value='" + esc(d.name) + "'" + selected + ">" + esc(d.name + " | " + (d.po_number || "-")) + "</option>");
      });
      parts.push("</select>");
      return parts.join("");
    }

    function itemGroupSelectHtml(selectedValue) {
      var parts = [];
      var current = String(selectedValue || "");
      var exists = false;
      parts.push("<select id='pp-entry-item-group'>");
      parts.push("<option value=''>All Item Groups</option>");
      (itemGroupOptions || []).forEach(function (opt) {
        var optValue = String((opt && opt.value) || "");
        var selected = optValue === current ? " selected" : "";
        if (selected) exists = true;
        parts.push("<option value='" + esc(optValue) + "'" + selected + ">" + esc((opt && opt.label) || optValue) + "</option>");
      });
      if (current && !exists) {
        parts.push("<option value='" + esc(current) + "' selected>" + esc(current) + "</option>");
      }
      parts.push("</select>");
      return parts.join("");
    }

    function employeeSelectHtml(selectedValue) {
      var parts = [];
      var current = String(selectedValue || "");
      var exists = false;
      parts.push("<select id='pp-entry-employee'>");
      parts.push("<option value=''>All Employees</option>");
      (employeeOptions || []).forEach(function (opt) {
        var optValue = String((opt && opt.value) || "");
        var selected = optValue === current ? " selected" : "";
        if (selected) exists = true;
        parts.push("<option value='" + esc(optValue) + "'" + selected + ">" + esc((opt && opt.label) || optValue) + "</option>");
      });
      if (current && !exists) {
        parts.push("<option value='" + esc(current) + "' selected>" + esc(current) + "</option>");
      }
      parts.push("</select>");
      return parts.join("");
    }

    function itemSelectHtml(selectedValue) {
      var current = String(selectedValue || "");
      var exists = false;
      var parts = [];
      parts.push("<select id='pp-entry-item'>");
      parts.push("<option value=''>All Items</option>");
      (itemOptions || []).forEach(function (opt) {
        var val = String((opt && opt.value) || "");
        var selected = val === current ? " selected" : "";
        if (selected) exists = true;
        parts.push("<option value='" + esc(val) + "'" + selected + ">" + esc((opt && opt.label) || val) + "</option>");
      });
      if (current && !exists) {
        parts.push("<option value='" + esc(current) + "' selected>" + esc(current) + "</option>");
      }
      parts.push("</select>");
      return parts.join("");
    }

    var html = "<div class='pp-entry-card'>"
      + "<strong>Data Enter (" + (editing ? "Edit Existing Per Piece Salary" : "Create Per Piece Salary") + ")</strong>"
      + "<div style='margin-top:6px;color:#475569;font-size:12px;'>PO Number is mandatory. Use Edit controls to fix draft entry mistakes.</div>"
      + "<div class='pp-jv-grid' style='margin-top:10px;'>"
      + "<label>Edit Entry " + docsSelectHtml(state.entryMeta.edit_name || "") + "</label>"
      + "<label>From Date <input type='date' id='pp-entry-from-date' value='" + esc(state.entryMeta.from_date || "") + "'></label>"
      + "<label>To Date <input type='date' id='pp-entry-to-date' value='" + esc(state.entryMeta.to_date || "") + "'></label>"
      + "<label>Employee " + employeeSelectHtml(state.entryMeta.employee || "") + "</label>"
      + "<label>Item Group " + itemGroupSelectHtml(state.entryMeta.item_group || "") + "</label>"
      + "<label>Item " + itemSelectHtml(state.entryMeta.item || "") + "</label>"
      + "<label>PO Number * <input type='text' id='pp-entry-po-number' required placeholder='Required' value='" + esc(state.entryMeta.po_number || "") + "'></label>"
      + "<label><span style='display:block;margin-bottom:6px;'>Load By Item</span><input type='checkbox' id='pp-entry-load-by-item'" + (state.entryMeta.load_by_item ? " checked" : "") + "></label>"
      + "</div>"
      + "<div class='pp-entry-actions'>"
      + "<button id='pp-entry-load-doc' class='btn btn-default' type='button'>Load Entry</button>"
      + "<button id='pp-entry-new-doc' class='btn btn-default' type='button'>New Entry</button>"
      + "<button id='pp-entry-add-row' class='btn btn-default' type='button'>Add Row</button>"
      + "<button id='pp-entry-reset' class='btn btn-default' type='button'>Reset Rows</button>"
      + "<button id='pp-entry-save' class='btn btn-primary' type='button'>" + (editing ? "Update Per Piece Salary" : "Save Per Piece Salary") + "</button>"
      + "</div>"
      + "<div id='pp-entry-result' class='pp-jv-result'></div>"
      + "<table class='pp-table' style='margin-top:8px;'><thead><tr><th>Employee</th><th>Employee First Name</th><th>Product</th><th>Process Type</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Action</th></tr></thead><tbody>";
    state.entryRows.forEach(function (r, idx) {
      var name1 = r.name1 || (employeeNameMap[r.employee || ""] || "");
      html += "<tr>"
        + "<td>" + selectHtml(employeeOptions, r.employee || "", idx, "employee") + "</td>"
        + "<td><input class='pp-pay-input pp-entry-in' data-idx='" + idx + "' data-field='name1' value='" + esc(name1) + "'></td>"
        + "<td>" + selectHtml(productOptions, r.product || "", idx, "product") + "</td>"
        + "<td>" + selectHtml(processOptions, r.process_type || "", idx, "process_type") + "</td>"
        + "<td>" + readonlyHtml(r.process_size || "No Size") + "</td>"
        + "<td><input class='pp-pay-input pp-entry-in' type='number' min='0' step='0.01' inputmode='decimal' data-idx='" + idx + "' data-field='qty' value='" + esc(whole(r.qty)) + "'></td>"
        + "<td><input class='pp-pay-input pp-entry-in' type='number' min='0' step='0.01' inputmode='decimal' data-idx='" + idx + "' data-field='rate' value='" + esc(whole(r.rate)) + "'></td>"
        + "<td class='num'>" + esc(fmt(entryAmount(r))) + "</td>"
        + "<td><button class='btn btn-xs btn-danger pp-entry-del' data-idx='" + idx + "' type='button'>Delete</button></td>"
        + "</tr>";
    });
    var eQty = 0, eRate = 0, eAmount = 0;
    state.entryRows.forEach(function (r) {
      eQty += num(r.qty);
      eRate += num(r.rate);
      eAmount += entryAmount(r);
    });
    html += "<tr class='pp-year-total'>"
      + "<td>Total</td><td></td><td></td><td></td><td></td>"
      + "<td class='num'>" + esc(fmt(eQty)) + "</td>"
      + "<td class='num'>" + esc(fmt(eRate)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(eAmount)) + "</td>"
      + "<td></td>"
      + "</tr>";
    html += "</tbody></table>";
    if (docs.length) {
      html += "<div class='pp-entry-list'><strong>Recent Docs:</strong></div>";
      html += "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Per Piece Salary</th><th>From Date</th><th>To Date</th><th>Item Group</th><th>PO Number</th><th>Total Amount</th><th>Edit</th><th>Open</th></tr></thead><tbody>";
      docs.slice(0, 10).forEach(function (d) {
        html += "<tr><td>" + esc(d.name) + "</td><td>" + esc(d.from_date) + "</td><td>" + esc(d.to_date) + "</td><td>" + esc(d.item_group || "") + "</td><td>" + esc(d.po_number) + "</td><td class='num pp-amt-col'>" + esc(fmt(d.total_amount)) + "</td><td><button type='button' class='btn btn-xs btn-default pp-entry-edit-doc' data-name='" + esc(d.name) + "'>Edit</button></td><td><a target='_blank' href='/app/per-piece-salary/" + encodeURIComponent(d.name) + "'>Open</a></td></tr>";
      });
      html += "</tbody></table>";
    }
    html += "</div>";
    wrap.innerHTML = html;

    var saveBtn = el("pp-entry-save");
    if (saveBtn) saveBtn.addEventListener("click", saveDataEntry);
    var fromInput = el("pp-entry-from-date");
    if (fromInput) fromInput.addEventListener("change", function () { state.entryMeta.from_date = fromInput.value || ""; });
    var toInput = el("pp-entry-to-date");
    if (toInput) toInput.addEventListener("change", function () { state.entryMeta.to_date = toInput.value || ""; });
    var poInput = el("pp-entry-po-number");
    if (poInput) poInput.addEventListener("change", function () { state.entryMeta.po_number = poInput.value || ""; });
    var employeeInput = el("pp-entry-employee");
    if (employeeInput) {
      employeeInput.addEventListener("change", function () {
        state.entryMeta.employee = employeeInput.value || "";
        syncEntryEmployeeToRows();
        renderDataEntryTab();
      });
    }
    var itemGroupInput = el("pp-entry-item-group");
    if (itemGroupInput) {
      itemGroupInput.addEventListener("change", function () {
        state.entryMeta.item_group = itemGroupInput.value || "";
        var itemOk = false;
        (itemOptions || []).forEach(function (opt) {
          if (String((opt && opt.value) || "") === String(state.entryMeta.item || "")) itemOk = true;
        });
        if (!itemOk) state.entryMeta.item = "";
        rebuildEntryMetaLookups();
        populateEntryRowsFromItemGroup(true);
        syncEntryRowsToItemGroup();
        renderDataEntryTab();
      });
    }
    var loadByItemInput = el("pp-entry-load-by-item");
    if (loadByItemInput) {
      loadByItemInput.addEventListener("change", function () {
        state.entryMeta.load_by_item = !!loadByItemInput.checked;
        rebuildEntryMetaLookups();
        populateEntryRowsFromItemGroup(true);
        syncEntryRowsToItemGroup();
        renderDataEntryTab();
      });
    }
    var itemInput = el("pp-entry-item");
    if (itemInput) {
      itemInput.addEventListener("change", function () {
        state.entryMeta.item = itemInput.value || "";
        rebuildEntryMetaLookups();
        populateEntryRowsFromItemGroup(true);
        syncEntryRowsToItemGroup();
        renderDataEntryTab();
      });
    }
    var loadDocBtn = el("pp-entry-load-doc");
    if (loadDocBtn) loadDocBtn.addEventListener("click", function () {
      var selected = (el("pp-entry-edit-name") && el("pp-entry-edit-name").value) || "";
      loadEntryDocForEdit(selected);
    });
    var newDocBtn = el("pp-entry-new-doc");
    if (newDocBtn) newDocBtn.addEventListener("click", function () {
      state.entryMeta.edit_name = "";
      state.entryMeta.from_date = el("pp-from-date").value || "";
      state.entryMeta.to_date = el("pp-to-date").value || "";
      state.entryMeta.employee = el("pp-employee") ? (el("pp-employee").value || "") : "";
      state.entryMeta.item_group = el("pp-item-group") ? (el("pp-item-group").value || "") : "";
      state.entryMeta.item = "";
      state.entryMeta.load_by_item = true;
      state.entryMeta.po_number = "";
      rebuildEntryMetaLookups();
      state.entryRows = [];
      populateEntryRowsFromItemGroup();
      if (!state.entryRows.length) state.entryRows = [newEntryRow()];
      renderDataEntryTab();
    });
    var addBtn = el("pp-entry-add-row");
    if (addBtn) addBtn.addEventListener("click", function () {
      state.entryRows.push(newEntryRow());
      renderDataEntryTab();
    });
    var resetBtn = el("pp-entry-reset");
    if (resetBtn) resetBtn.addEventListener("click", function () {
      state.entryRows = [newEntryRow()];
      renderDataEntryTab();
    });

    wrap.querySelectorAll(".pp-entry-in").forEach(function (input) {
      function onEntryInput() {
        var idx = parseInt(input.getAttribute("data-idx") || "0", 10);
        var field = input.getAttribute("data-field") || "";
        if (!state.entryRows[idx]) return;
        if (field === "qty" || field === "rate") {
          state.entryRows[idx][field] = whole(input.value);
        } else {
          state.entryRows[idx][field] = input.value || "";
        }
        if (field === "employee") {
          state.entryRows[idx].name1 = (state.entryMeta.employeeNameMap || {})[state.entryRows[idx].employee || ""] || "";
        }
        if (field === "product" || field === "process_type") {
          var row = state.entryRows[idx];
          applyEntryItemDefaults(row);
        }
        renderDataEntryTab();
      }
      input.addEventListener("change", onEntryInput);
    });

    wrap.querySelectorAll(".pp-entry-del").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var idx = parseInt(btn.getAttribute("data-idx") || "0", 10);
        state.entryRows = state.entryRows.filter(function (_r, i) { return i !== idx; });
        ensureEntryRows();
        renderDataEntryTab();
      });
    });

    wrap.querySelectorAll(".pp-entry-edit-doc").forEach(function (btn) {
      btn.addEventListener("click", function () {
        loadEntryDocForEdit(btn.getAttribute("data-name") || "");
      });
    });
  }

  function loadEntryDocForEdit(entryName) {
    var result = el("pp-entry-result");
    if (!entryName) {
      showResult(result, "error", "Select Entry", "Choose a Per Piece Salary entry to load.");
      return;
    }
    if (result) {
      result.style.color = "#334155";
      result.textContent = "Loading entry...";
    }
    callApi("frappe.client.get", { doctype: "Per Piece Salary", name: entryName }).then(function (doc) {
      if (!doc) {
        showResult(result, "error", "Load Failed", "Entry not found.");
        return;
      }
      if (Number(doc.docstatus || 0) !== 0) {
        showResult(result, "error", "Cannot Edit", "Only Draft entries can be edited in this tab.");
        return;
      }
      state.entryMeta.edit_name = doc.name || "";
      state.entryMeta.from_date = doc.from_date || "";
      state.entryMeta.to_date = doc.to_date || "";
      state.entryMeta.employee = doc.employee || "";
      state.entryMeta.item_group = doc.item_group || "";
      state.entryMeta.item = doc.item || "";
      state.entryMeta.load_by_item = doc.load_by_item === undefined ? true : !!Number(doc.load_by_item);
      state.entryMeta.po_number = doc.po_number || "";
      state.entryRows = (doc.perpiece || []).map(function (r) {
        return {
          employee: r.employee || "",
          name1: r.name1 || "",
          product: r.product || "",
          process_type: r.process_type || "",
          process_size: r.process_size || "No Size",
          qty: whole(r.qty),
          rate: whole(r.rate)
        };
      });
      ensureEntryRows();
      renderDataEntryTab();
      showResult(el("pp-entry-result"), "success", "Entry Loaded", "Now update rows and click Update Per Piece Salary.");
    }).catch(function (e) {
      showResult(result, "error", "Load Failed", prettyError(errText(e)));
      console.error(e);
    });
  }

  function saveDataEntry() {
    var result = el("pp-entry-result");
    var fromDate = (el("pp-entry-from-date").value || state.entryMeta.from_date || "");
    var toDate = (el("pp-entry-to-date").value || state.entryMeta.to_date || "");
    var employee = (el("pp-entry-employee") && el("pp-entry-employee").value) || state.entryMeta.employee || "";
    var itemGroup = (el("pp-entry-item-group") && el("pp-entry-item-group").value) || state.entryMeta.item_group || "";
    var loadByItem = !!state.entryMeta.load_by_item;
    var selectedItemSingle = (el("pp-entry-item") && el("pp-entry-item").value) || state.entryMeta.item || "";
    var po = (el("pp-entry-po-number").value || state.entryMeta.po_number || "");
    var editName = state.entryMeta.edit_name || "";
    if (!po) {
      showResult(result, "error", "PO Number Required", "Enter PO Number before saving.");
      return;
    }
    if (loadByItem && !selectedItemSingle) {
      showResult(result, "error", "Item Required", "Select Item or uncheck Load By Item.");
      return;
    }
    var lines = [];
    (state.entryRows || []).forEach(function (r) {
      var qty = whole(r.qty);
      if (qty <= 0) return;
      lines.push([
        String(r.employee || "").trim(),
        String(r.name1 || "").trim(),
        String(r.product || "").trim(),
        String(r.process_type || "").trim(),
        String(r.process_size || "No Size").trim(),
        qty,
        whole(r.rate)
      ].join("::"));
    });
    if (!lines.length) {
      showResult(result, "error", "Cannot Save", "Enter at least one row with Qty.");
      return;
    }
    result.style.color = "#334155";
    result.textContent = editName ? "Updating data entry..." : "Saving data entry...";
    callApi("create_per_piece_salary_entry", {
      entry_name: editName,
      from_date: fromDate,
      to_date: toDate,
      employee: employee,
      item_group: itemGroup,
      item: selectedItemSingle,
      selected_items: selectedItemSingle ? String(selectedItemSingle) : "",
      load_by_item: loadByItem ? 1 : 0,
      po_number: po,
      rows: lines.join(";;")
    }).then(function (msg) {
      var link = "<a target='_blank' href='/app/per-piece-salary/" + encodeURIComponent(msg.name) + "'>" + esc(msg.name) + "</a>";
      result.style.color = "#0f766e";
      result.innerHTML = (msg.action === "updated" ? "Updated: " : "Saved: ") + link + " | Rows: " + esc(msg.rows) + " | Qty: " + esc(fmt(msg.total_qty)) + " | Amount: " + esc(fmt(msg.total_amount));
      if (msg.action === "updated") {
        state.entryMeta.edit_name = msg.name;
      } else {
        state.entryRows = [newEntryRow()];
        state.entryMeta.edit_name = "";
        state.entryMeta.po_number = "";
      }
      loadReport();
    }).catch(function (e) {
      showResult(result, "error", "Save Failed", prettyError(errText(e)));
      console.error(e);
    });
  }

  function toggleWorkflowCards() {
    var salaryCard = el("pp-salary-jv-card");
    var paymentCard = el("pp-payment-jv-card");
    if (!salaryCard || !paymentCard) return;
    salaryCard.style.display = state.currentTab === "salary_creation" ? "" : "none";
    paymentCard.style.display = state.currentTab === "payment_manage" ? "" : "none";
  }

  function renderCurrentTab() {
    var rows = getRowsByHeaderFilters(state.rows || []);
    var cols = [];
    var outRows = [];
    var paged = null;
    var skipColumnSearch = false;
    toggleWorkflowCards();

    if (state.currentTab === "all") {
      cols = [
        { fieldname: "per_piece_salary", label: "Per Piece Salary" },
        { fieldname: "from_date", label: "From Date" },
        { fieldname: "to_date", label: "To Date" },
        { fieldname: "po_number", label: "PO Number" },
        { fieldname: "item_group", label: "Item Group" },
        { fieldname: "name1", label: "Employee" },
        { fieldname: "product", label: "Product" },
        { fieldname: "process_type", label: "Process Type" },
        { fieldname: "process_size", label: "Process Size" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" },
        { fieldname: "jv_entry_no", label: "Booking JV" },
        { fieldname: "payment_jv_no", label: "Payment JV" },
      ];
      outRows = rows;
    } else if (state.currentTab === "data_entry") {
      renderDataEntryTab();
      filterRenderedTablesBySearch();
      el("pp-totals").innerHTML = "";
      renderPagination(null);
      el("pp-msg").textContent = "Enter and save Per Piece Salary here";
      renderCreatedEntriesPanel("data_entry");
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    } else if (state.currentTab === "salary_creation") {
      outRows = getAdjustedEmployeeRows();
      paged = paginateRows(outRows);
      renderSalaryTable(paged.rows);
      filterRenderedTablesBySearch();
      var t = getAdjustedTotals();
      el("pp-totals").innerHTML = "<span>Gross: " + fmt(t.gross_amount) + "</span>"
        + "<span>Advance Deduction: " + fmt(t.advance_deduction_amount) + "</span>"
        + "<span>Other Deduction: " + fmt(t.other_deduction_amount) + "</span>"
        + "<span>Net Payable: " + fmt(t.net_payable_amount) + "</span>";
      el("pp-msg").textContent = outRows.length + " employee row(s) for salary creation";
      renderPagination(paged);
      renderCreatedEntriesPanel("salary_creation");
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    } else if (state.currentTab === "jv_created") {
      cols = [
        { fieldname: "name1", label: "Employee" },
        { fieldname: "booked_amount", label: "Booked Amount", numeric: true },
        { fieldname: "paid_amount", label: "Paid Amount", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid Amount", numeric: true },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = buildPaymentEmployeeRows(getBookedRows());
    } else if (state.currentTab === "payment_manage") {
      outRows = getPaymentActiveRows();
      paged = paginateRows(outRows);
      renderPaymentTable(paged.rows);
      filterRenderedTablesBySearch();
      var p = getPaymentTotals();
      el("pp-totals").innerHTML = "<span>Booked: " + fmt(p.booked) + "</span>"
        + "<span>Paid: " + fmt(p.paid) + "</span>"
        + "<span>Unpaid: " + fmt(p.unpaid) + "</span>"
        + "<span>Payment This JV: " + fmt(p.payment) + "</span>";
      el("pp-msg").textContent = outRows.length + " employee row(s) pending payment (paid rows hidden)";
      renderPagination(paged);
      renderCreatedEntriesPanel("payment_manage");
      refreshPaymentAmounts();
      refreshJVAmountsFromAdjustments();
      return;
    } else if (state.currentTab === "advances") {
      var advanceMonths = state.advanceMonths || [];
      cols = [
        { fieldname: "name1", label: "Employee Name" },
        { fieldname: "employee", label: "Employee ID" },
        { fieldname: "branch", label: "Branch" },
        { fieldname: "opening_balance", label: "Opening Balance", numeric: true }
      ];
      advanceMonths.forEach(function (m) {
        cols.push({ fieldname: advanceMonthField(m.key), label: m.label, numeric: true });
      });
      cols.push({ fieldname: "closing_balance", label: "Closing Balance", numeric: true });
      outRows = buildAdvanceRows(rows);
    } else if (state.currentTab === "employee_summary") {
      cols = [
        { fieldname: "name1", label: "Employee" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "unbooked_amount", label: "UnBooked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = groupRows(rows, ["employee", "name1"], function (r) {
        return { employee: r.employee, name1: r.name1, qty: 0, amount: 0, rate: 0, booked_amount: 0, unbooked_amount: 0, paid_amount: 0, unpaid_amount: 0 };
      });
    } else if (state.currentTab === "month_year_salary") {
      cols = [
        { fieldname: "name1", label: "Employee" },
        { fieldname: "month_year", label: "Month / Year" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "unbooked_amount", label: "UnBooked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true }
      ];
      outRows = buildEmployeeMonthYearRows(rows);
    } else if (state.currentTab === "month_paid_unpaid") {
      cols = [
        { fieldname: "month_year", label: "Month / Year" },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true }
      ];
      outRows = buildMonthPaidUnpaidRows(rows);
    } else if (state.currentTab === "simple_month_amount") {
      var simpleMonths = buildSimpleMonthColumns(rows);
      cols = [{ fieldname: "name1", label: "Employee" }];
      simpleMonths.forEach(function (m) {
        cols.push({ fieldname: monthFieldFromKey(m.key), label: m.label, numeric: true });
      });
      cols.push({ fieldname: "total_amount", label: "Total", numeric: true });
      outRows = buildSimpleMonthRows(rows, simpleMonths);
      outRows = filterRowsByColumns(outRows, cols);
      skipColumnSearch = true;
      var totalRow = { name1: "Total", total_amount: 0, _is_total: 1 };
      simpleMonths.forEach(function (m) {
        totalRow[monthFieldFromKey(m.key)] = 0;
      });
      outRows.forEach(function (r) {
        var rowTotal = 0;
        simpleMonths.forEach(function (m) {
          var f = monthFieldFromKey(m.key);
          var val = num(r[f]);
          rowTotal += val;
          totalRow[f] += val;
        });
        r.total_amount = rowTotal;
        totalRow.total_amount += rowTotal;
      });
      outRows.push(totalRow);
    } else if (state.currentTab === "product") {
      cols = [
        { fieldname: "product", label: "Product" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = groupRows(rows, ["product"], function (r) { return { product: r.product, qty: 0, amount: 0, rate: 0, booked_amount: 0, paid_amount: 0, unpaid_amount: 0 }; });
    } else if (state.currentTab === "process_product") {
      cols = [
        { fieldname: "process_type", label: "Process Type" },
        { fieldname: "product", label: "Product" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = groupRows(rows, ["process_type", "product"], function (r) {
        return { process_type: r.process_type, product: r.product, qty: 0, amount: 0, rate: 0, booked_amount: 0, paid_amount: 0, unpaid_amount: 0 };
      });
    } else if (state.currentTab === "per_piece_salary") {
      cols = [
        { fieldname: "per_piece_salary", label: "Entry No", summary_link: true },
        { fieldname: "_row_count", label: "Lines", numeric: true },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "unbooked_amount", label: "UnBooked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = groupRows(rows, ["per_piece_salary"], function (r) {
        return { per_piece_salary: r.per_piece_salary, qty: 0, amount: 0, rate: 0, booked_amount: 0, unbooked_amount: 0, paid_amount: 0, unpaid_amount: 0 };
      });
    } else if (state.currentTab === "po_number") {
      cols = [
        { fieldname: "po_number", label: "PO Number" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "unbooked_amount", label: "UnBooked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = groupRows(rows, ["po_number"], function (r) {
        return { po_number: r.po_number || "(Blank)", qty: 0, amount: 0, rate: 0, booked_amount: 0, unbooked_amount: 0, paid_amount: 0, unpaid_amount: 0 };
      });
    }

    if (!skipColumnSearch) {
      outRows = filterRowsByColumns(outRows, cols);
    }
    paged = paginateRows(outRows);
    renderTable(cols, paged.rows);
    renderPagination(paged);

    if (state.currentTab === "jv_created") {
      var jb = 0, jp = 0, ju = 0;
      outRows.forEach(function (r) {
        jb += num(r.booked_amount);
        jp += num(r.paid_amount);
        ju += num(r.unpaid_amount);
      });
      el("pp-totals").innerHTML = "<span>Total Booked: " + fmt(jb) + "</span><span>Total Paid: " + fmt(jp) + "</span><span>Total Unpaid: " + fmt(ju) + "</span>";
      el("pp-msg").textContent = outRows.length + " employee row(s) in booked JV";
      renderCreatedEntriesPanel("jv_created");
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    }
    if (state.currentTab === "advances") {
      var advanceMonths = state.advanceMonths || [];
      var totalAdvance = 0;
      var totalOpening = 0;
      var monthTotals = {};
      advanceMonths.forEach(function (m) {
        monthTotals[m.key] = 0;
      });
      outRows.forEach(function (r) {
        totalOpening += num(r.opening_balance);
        totalAdvance += num(r.closing_balance || r.advance_balance);
        advanceMonths.forEach(function (m) {
          monthTotals[m.key] += num(r[advanceMonthField(m.key)]);
        });
      });
      var totalsHtml = "<span>Opening: " + fmt(totalOpening) + "</span>";
      advanceMonths.forEach(function (m) {
        totalsHtml += "<span>" + esc(m.label) + ": " + fmt(monthTotals[m.key]) + "</span>";
      });
      totalsHtml += "<span>Closing: " + fmt(totalAdvance) + "</span>";
      el("pp-totals").innerHTML = totalsHtml;
      el("pp-msg").textContent = outRows.length + " employee row(s) in advances as on selected To Date (from Employee Advance/GL closing)";
      renderCreatedEntriesPanel(state.currentTab);
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    }

    var totalQty = 0, totalAmount = 0;
    if (state.currentTab === "month_year_salary") {
      outRows.forEach(function (r) {
        if (String(r.period_type || "") !== "Month") return;
        totalQty += num(r.qty);
        totalAmount += num(r.amount);
      });
      el("pp-totals").innerHTML = "<span>Monthly Qty Total: " + fmt(totalQty) + "</span><span>Monthly Amount Total: " + fmt(totalAmount) + "</span>";
      el("pp-msg").textContent = outRows.length + " row(s) including month-wise and yearly totals";
      renderCreatedEntriesPanel(state.currentTab);
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    }
    if (state.currentTab === "month_paid_unpaid") {
      var mb = 0, mp = 0, mu = 0;
      outRows.forEach(function (r) {
        mb += num(r.booked_amount);
        mp += num(r.paid_amount);
        mu += num(r.unpaid_amount);
      });
      el("pp-totals").innerHTML = "<span>Total Booked: " + fmt(mb) + "</span><span>Total Paid: " + fmt(mp) + "</span><span>Total Unpaid: " + fmt(mu) + "</span>";
      el("pp-msg").textContent = outRows.length + " month row(s) in month-wise paid/unpaid report";
      renderCreatedEntriesPanel(state.currentTab);
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    }
    if (state.currentTab === "simple_month_amount") {
      var simpleCols = buildSimpleMonthColumns(rows);
      var monthTotals = {};
      var grand = 0;
      simpleCols.forEach(function (m) { monthTotals[m.key] = 0; });
      outRows.forEach(function (r) {
        if (r && r._is_total) return;
        simpleCols.forEach(function (m) {
          var amount = num(r[monthFieldFromKey(m.key)]);
          monthTotals[m.key] += amount;
          grand += amount;
        });
      });
      var totalsHtml = "";
      simpleCols.forEach(function (m) {
        totalsHtml += "<span>" + esc(m.label) + ": " + fmt(monthTotals[m.key]) + "</span>";
      });
      totalsHtml += "<span>Total Amount: " + fmt(grand) + "</span>";
      el("pp-totals").innerHTML = totalsHtml;
      el("pp-msg").textContent = outRows.length + " employee row(s) in simple month-wise amount report";
      renderCreatedEntriesPanel(state.currentTab);
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    }
    outRows.forEach(function (r) { totalQty += num(r.qty); totalAmount += num(r.amount); });
    el("pp-totals").innerHTML = "<span>Total Qty: " + fmt(totalQty) + "</span><span>Total Amount: " + fmt(totalAmount) + "</span>";
    el("pp-msg").textContent = outRows.length + " row(s)";
    renderCreatedEntriesPanel(state.currentTab);
    refreshJVAmountsFromAdjustments();
    refreshPaymentAmounts();
  }

  function loadReport() {
    setPageForCurrentTab(1);
    el("pp-msg").textContent = "Loading...";
    callApi("get_per_piece_salary_report", getReportArgs()).then(function (msg) {
      state.rows = (msg && msg.data) || [];
      state.columns = (msg && msg.columns) || [];
      refreshHeaderFilterOptions();
      return loadAdvancesFromGL().catch(function (e) {
        console.error(e);
        state.advanceBalances = (msg && msg.advance_balances) || {};
        state.advanceRows = (msg && msg.advance_rows) || [];
        state.advanceMonths = (msg && msg.advance_months) || [];
      }).then(function () {
        rebuildEntryMetaLookups();
        refreshTopProductOptions();
        normalizeExcludedEmployees();
        normalizeAdjustmentsForEmployees();
        normalizePaymentExcludedEmployees();
        normalizePaymentAdjustments();
        renderCurrentTab();
        loadJVEntryOptions();
        loadPaymentJVEntryOptions();
        if (msg && Number(msg.truncated || 0) === 1) {
          el("pp-msg").textContent = (el("pp-msg").textContent || "") + " | Showing first " + esc(msg.max_rows || 0) + " rows (increase Max Rows or narrow date range).";
        }
      });
    }).catch(function (e) {
      el("pp-msg").textContent = "Error loading report";
      var result = el("pp-jv-result");
      if (result) {
        result.style.color = "#b91c1c";
        result.textContent = errText(e);
      }
      console.error(e);
    });
  }

  function loadJVEntryOptions() {
    var select = el("pp-jv-existing");
    if (!select) return;
    var posted = {};
    (state.rows || []).forEach(function (r) {
      if (r && r.jv_entry_no && r.jv_status === "Posted") {
        posted[r.jv_entry_no] = true;
      }
    });
    var options = Object.keys(posted).sort().reverse().map(function (name) { return { name: name }; });
    setOptions(select, options, "name", "name", "Select Posted JV");
    if (options.length) select.value = options[0].name;
  }

  function loadPaymentJVEntryOptions() {
    var select = el("pp-pay-existing");
    if (!select) return;
    var posted = {};
    (state.rows || []).forEach(function (r) {
      if (r && r.payment_jv_no) posted[r.payment_jv_no] = true;
    });
    var options = Object.keys(posted).sort().reverse().map(function (name) { return { name: name }; });
    setOptions(select, options, "name", "name", "Select Payment JV");
    if (options.length) select.value = options[0].name;
  }

  function selectPreferred(selectEl, rows, preferredKeywords) {
    if (!selectEl || !rows || !rows.length) return;
    var current = selectEl.value || "";
    if (current && rows.some(function (r) { return r.name === current; })) {
      selectEl.value = current;
      return;
    }
    var target = "";
    if (preferredKeywords && preferredKeywords.length) {
      preferredKeywords.forEach(function (k) {
        if (target) return;
        var keyword = String(k || "").toLowerCase();
        rows.forEach(function (r) {
          if (target) return;
          var lower = String(r.name || "").toLowerCase();
          if (lower.indexOf(keyword) === 0) target = r.name;
        });
      });
      preferredKeywords.forEach(function (k) {
        if (target) return;
        var keyword = String(k || "").toLowerCase();
        rows.forEach(function (r) {
          if (target) return;
          var lower = String(r.name || "").toLowerCase();
          if (lower.indexOf(keyword) >= 0) target = r.name;
        });
      });
    }
    if (!target) target = rows[0].name;
    selectEl.value = target;
  }

  function selectPreferredPayable(selectEl, rows) {
    selectPreferred(selectEl, rows, ["payroll payable", "salary payable", "payable", "salary", "employee"]);
  }

  function loadCompanies() {
    return callGetList("Company", ["name"], {}).then(function (rows) {
      rows = rows || [];
      setOptions(el("pp-jv-company"), rows, "name", "name", "Select Company");
      setOptions(el("pp-pay-company"), rows, "name", "name", "Select Company");
      if (rows.length) {
        el("pp-jv-company").value = rows[0].name;
        el("pp-pay-company").value = rows[0].name;
        loadAccountsForCompany();
        loadPaymentAccountsForCompany();
      }
    });
  }

  function loadAccountsForCompany() {
    var company = el("pp-jv-company").value || "";
    if (!company) {
      setOptions(el("pp-jv-expense-account"), [], "name", "name", "Select Salary Account");
      setOptions(el("pp-jv-allowance-account"), [], "name", "name", "Select Allowance Account");
      setOptions(el("pp-jv-payable-account"), [], "name", "name", "Select Payable Account");
      setOptions(el("pp-jv-advance-account"), [], "name", "name", "Select Advance Account");
      setOptions(el("pp-jv-deduction-account"), [], "name", "name", "Select Deduction Account");
      return;
    }
    callGetList("Account", ["name"], { company: company, is_group: 0, root_type: "Expense" }).then(function (rows) {
      rows = rows || [];
      setOptions(el("pp-jv-expense-account"), rows, "name", "name", "Select Salary Account");
      selectPreferred(el("pp-jv-expense-account"), rows, ["salary", "wages", "expense", "allowance"]);
      setOptions(el("pp-jv-allowance-account"), rows, "name", "name", "Select Allowance Account");
      selectPreferred(el("pp-jv-allowance-account"), rows, ["allowance", "salary", "expense"]);
    }).catch(function (e) { console.error(e); });
    callGetList("Account", ["name"], { company: company, is_group: 0, account_type: "Payable" }).then(function (rows) {
      rows = rows || [];
      setOptions(el("pp-jv-payable-account"), rows, "name", "name", "Select Payable Account");
      selectPreferredPayable(el("pp-jv-payable-account"), rows);
    }).catch(function (e) { console.error(e); });
    callGetList("Account", ["name"], { company: company, is_group: 0, root_type: "Asset" }).then(function (rows) {
      rows = rows || [];
      setOptions(el("pp-jv-advance-account"), rows, "name", "name", "Select Advance Account");
      selectPreferred(el("pp-jv-advance-account"), rows, ["employee advance", "advance", "employee", "receivable"]);
    }).catch(function (e) { console.error(e); });
    callGetList("Account", ["name"], { company: company, is_group: 0, root_type: "Liability" }).then(function (rows) {
      rows = rows || [];
      setOptions(el("pp-jv-deduction-account"), rows, "name", "name", "Select Deduction Account");
      selectPreferred(el("pp-jv-deduction-account"), rows, ["allowance", "salary", "deduction", "payable", "employee"]);
    }).catch(function (e) { console.error(e); });
  }

  function loadPaymentAccountsForCompany() {
    var company = el("pp-pay-company").value || "";
    if (!company) {
      setOptions(el("pp-pay-payable-account"), [], "name", "name", "Select Payable Account");
      setOptions(el("pp-pay-paid-from-account"), [], "name", "name", "Select Bank/Cash Account");
      return;
    }
    callGetList("Account", ["name"], { company: company, is_group: 0, account_type: "Payable" }).then(function (rows) {
      rows = rows || [];
      setOptions(el("pp-pay-payable-account"), rows, "name", "name", "Select Payable Account");
      var salaryPayable = el("pp-jv-payable-account").value || "";
      if (salaryPayable && rows.some(function (r) { return r.name === salaryPayable; })) {
        el("pp-pay-payable-account").value = salaryPayable;
      } else {
        selectPreferredPayable(el("pp-pay-payable-account"), rows);
      }
    }).catch(function (e) { console.error(e); });
    callGetList("Account", ["name"], { company: company, is_group: 0, root_type: "Asset" }).then(function (rows) {
      rows = rows || [];
      setOptions(el("pp-pay-paid-from-account"), rows, "name", "name", "Select Bank/Cash Account");
      selectPreferred(el("pp-pay-paid-from-account"), rows, ["cash", "bank"]);
    }).catch(function (e) { console.error(e); });
  }

  function getJVArgs(dryRun) {
    var args = getReportArgs();
    args.company = el("pp-jv-company").value || "";
    args.posting_date = el("pp-jv-posting-date").value || args.to_date || "";
    args.expense_account = el("pp-jv-expense-account").value || "";
    args.allowance_account = el("pp-jv-allowance-account").value || "";
    args.payable_account = el("pp-jv-payable-account").value || "";
    args.advance_account = el("pp-jv-advance-account").value || "";
    args.deduction_account = el("pp-jv-deduction-account").value || "";
    args.header_remark = el("pp-jv-remark").value || "";
    var lines = [];
    Object.keys(state.adjustments || {}).sort().forEach(function (emp) {
      var a = state.adjustments[emp] || {};
      lines.push([
        String(emp || "").trim(),
        whole(a.allowance),
        whole(a.advance_deduction),
        whole(a.other_deduction)
      ].join("::"));
    });
    args.employee_adjustments = lines.join(";;");
    args.exclude_employees = Object.keys(state.excludedEmployees || {}).filter(function (k) { return !!state.excludedEmployees[k]; }).join(",");
    args.employee_wise = 1;
    args.dry_run = dryRun ? 1 : 0;
    return args;
  }

  function getPaymentJVArgs(dryRun) {
    var args = getReportArgs();
    args.company = el("pp-pay-company").value || "";
    args.posting_date = el("pp-pay-posting-date").value || args.to_date || "";
    args.payable_account = el("pp-pay-payable-account").value || "";
    args.paid_from_account = el("pp-pay-paid-from-account").value || "";
    args.header_remark = el("pp-pay-remark").value || "";
    var lines = [];
    getPaymentRows().forEach(function (r) {
      var emp = r.employee || "";
      if (!emp) return;
      if (state.paymentExcludedEmployees[emp]) return;
      var amount = whole((state.paymentAdjustments[emp] || {}).payment_amount);
      if (amount <= 0) return;
      lines.push(String(emp).trim() + "::" + String(amount));
    });
    args.payment_items = lines.join(";;");
    args.dry_run = dryRun ? 1 : 0;
    return args;
  }

  function previewJV() {
    var result = el("pp-jv-result");
    result.style.color = "#334155";
    result.textContent = "Generating preview...";
    callApi("create_per_piece_salary_jv", getJVArgs(true)).then(function (msg) {
      setJVAmounts(msg.net_payable_amount, msg.net_payable_amount, msg.gross_amount);
      var html = "<strong>Preview</strong><br>"
        + "Rows: " + esc(msg.rows) + " | Qty: " + esc(msg.total_qty)
        + " | Base: " + esc(fmt(msg.base_amount))
        + " | Allowance: " + esc(fmt(msg.allowance_amount))
        + " | Gross: " + esc(fmt(msg.gross_amount))
        + " | Advance Deduction: " + esc(fmt(msg.advance_deduction_amount))
        + " | Other Deduction: " + esc(fmt(msg.other_deduction_amount))
        + " | Net Payable: " + esc(fmt(msg.net_payable_amount));
      if (msg.employee_summary && msg.employee_summary.length) {
        html += "<br><br><table class='pp-table'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Base</th><th>Allowance</th><th>Advance Balance</th><th>Advance Deduction</th><th>Other Deduction</th><th>Net</th><th>Remarks</th></tr></thead><tbody>";
        msg.employee_summary.forEach(function (r) {
          html += "<tr><td>" + esc(r.name1 || r.employee || "") + "</td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num'>" + esc(fmt(r.rate)) + "</td><td class='num'>" + esc(fmt(r.amount)) + "</td><td class='num'>" + esc(fmt(r.allowance)) + "</td><td class='num'>" + esc(fmt(r.advance_balance)) + "</td><td class='num'>" + esc(fmt(r.advance_deduction)) + "</td><td class='num'>" + esc(fmt(r.other_deduction)) + "</td><td class='num'>" + esc(fmt(r.net_amount)) + "</td><td>" + esc(r.remarks || "") + "</td></tr>";
        });
        html += "</tbody></table>";
      }
      result.style.color = "#0f766e";
      result.innerHTML = html;
    }).catch(function (e) {
      showResult(result, "error", "Preview Not Available", prettyError(errText(e)));
      console.error(e);
    });
  }

  function previewPaymentJV() {
    var result = el("pp-pay-result");
    if (!getPaymentPostingRows().length) {
      showResult(result, "error", "Nothing To Preview", "Only employees with Unpaid or Partly Paid status are shown here. Set payment amount greater than 0.");
      return;
    }
    result.style.color = "#334155";
    result.textContent = "Generating payment preview...";
    callApi("create_per_piece_salary_payment_jv", getPaymentJVArgs(true)).then(function (msg) {
      setPaymentAmounts(msg.debit_amount, msg.credit_amount, msg.unpaid_amount);
      var html = "<strong>Payment Preview</strong><br>"
        + "Booked: " + esc(fmt(msg.booked_amount))
        + " | Paid: " + esc(fmt(msg.paid_amount))
        + " | Unpaid: " + esc(fmt(msg.unpaid_amount))
        + " | Requested: " + esc(fmt(msg.requested_amount))
        + " | This JV: " + esc(fmt(msg.payment_amount));
      var previewRows = (msg.employee_summary || []).filter(function (r) {
        return num(r.unpaid_amount) > 0 || num(r.to_pay_amount) > 0;
      });
      if (previewRows.length) {
        html += "<br><br><table class='pp-table'><thead><tr><th>Employee</th><th>Booked</th><th>Paid</th><th>Unpaid</th><th>Requested</th><th>To Pay</th></tr></thead><tbody>";
        previewRows.forEach(function (r) {
          html += "<tr><td>" + esc(r.name1 || r.employee || "") + "</td><td class='num'>" + esc(fmt(r.booked_amount)) + "</td><td class='num'>" + esc(fmt(r.paid_amount)) + "</td><td class='num'>" + esc(fmt(r.unpaid_amount)) + "</td><td class='num'>" + esc(fmt(r.requested_amount)) + "</td><td class='num'>" + esc(fmt(r.to_pay_amount)) + "</td></tr>";
        });
        html += "</tbody></table>";
      }
      result.style.color = "#0f766e";
      result.innerHTML = html;
    }).catch(function (e) {
      showResult(result, "error", "Payment Preview Not Available", prettyError(errText(e)));
      console.error(e);
    });
  }

  function createPaymentJV() {
    if (!getPaymentPostingRows().length) {
      showResult(el("pp-pay-result"), "error", "Nothing To Post", "No unpaid or partly paid employee amount selected for payment JV.");
      return;
    }
    if (!confirm("Post Payment JV for selected employee amounts?")) return;
    var result = el("pp-pay-result");
    result.style.color = "#334155";
    result.textContent = "Posting payment JV...";
    callApi("create_per_piece_salary_payment_jv", getPaymentJVArgs(false)).then(function (msg) {
      setPaymentAmounts(msg.debit_amount, msg.credit_amount, 0);
      var link = "<a href='/app/journal-entry/" + encodeURIComponent(msg.journal_entry) + "' target='_blank'>" + esc(msg.journal_entry) + "</a>";
      result.style.color = "#0f766e";
      result.innerHTML = "Payment JV Posted: " + link + "<br>Amount: " + esc(fmt(msg.payment_amount))
        + " <button type='button' class='btn btn-xs btn-default pp-view-jv' data-jv='" + esc(msg.journal_entry) + "'>View Debit/Credit</button>";
      renderJournalEntryInline(result, msg.journal_entry);
      result.querySelectorAll(".pp-view-jv").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var jv = btn.getAttribute("data-jv") || "";
          if (jv) showJournalEntrySummary(jv);
        });
      });
      loadReport();
    }).catch(function (e) {
      showResult(result, "error", "Payment Post Failed", prettyError(errText(e)));
      console.error(e);
    });
  }

  function cancelPaymentJV() {
    var jv = el("pp-pay-existing").value || "";
    if (!jv) {
      alert("Select a Payment JV first.");
      return;
    }
    if (!confirm("Cancel selected Payment JV and reverse paid amounts?")) return;
    var result = el("pp-pay-result");
    result.style.color = "#334155";
    result.textContent = "Cancelling payment JV...";
    callApi("cancel_per_piece_salary_payment_jv", { journal_entry: jv }).then(function (msg) {
      result.style.color = "#0f766e";
      result.innerHTML = "Payment JV " + esc(msg.action || "cancelled") + ": " + esc(msg.journal_entry) + "<br>Rows updated: " + esc(msg.rows_updated || 0) + " | Amount reversed: " + esc(fmt(msg.amount_reversed || 0));
      loadReport();
    }).catch(function (e) {
      showResult(result, "error", "Payment Cancel Failed", prettyError(errText(e)));
      console.error(e);
    });
  }

  function createJV() {
    if (!confirm("Post JV Entry for current unposted rows?")) return;
    var result = el("pp-jv-result");
    result.style.color = "#334155";
    result.textContent = "Posting JV entry...";
    callApi("create_per_piece_salary_jv", getJVArgs(false)).then(function (msg) {
      setJVAmounts(msg.net_payable_amount, msg.net_payable_amount, msg.gross_amount);
      var link = "<a href='/app/journal-entry/" + encodeURIComponent(msg.journal_entry) + "' target='_blank'>" + esc(msg.journal_entry) + "</a>";
      result.style.color = "#0f766e";
      result.innerHTML = "JV Posted: " + link
        + "<br>Rows: " + esc(msg.rows)
        + " | Gross: " + esc(fmt(msg.gross_amount))
        + " | Net Payable: " + esc(fmt(msg.net_payable_amount))
        + " | Advance Deduction: " + esc(fmt(msg.advance_deduction_amount))
        + " | Other Deduction: " + esc(fmt(msg.other_deduction_amount))
        + " <button type='button' class='btn btn-xs btn-default pp-view-jv' data-jv='" + esc(msg.journal_entry) + "'>View Debit/Credit</button>";
      renderJournalEntryInline(result, msg.journal_entry);
      result.querySelectorAll(".pp-view-jv").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var jv = btn.getAttribute("data-jv") || "";
          if (jv) showJournalEntrySummary(jv);
        });
      });
      loadReport();
    }).catch(function (e) {
      showResult(result, "error", "JV Post Failed", prettyError(errText(e)));
      console.error(e);
    });
  }

  function cancelJVEntry() {
    var jv = el("pp-jv-existing").value || "";
    if (!jv) {
      alert("Select a posted JV Entry first.");
      return;
    }
    if (!confirm("Cancel selected JV Entry and clear links from Per Piece rows?")) return;
    var result = el("pp-jv-result");
    result.style.color = "#334155";
    result.textContent = "Cancelling JV entry...";
    callApi("cancel_per_piece_salary_jv", { journal_entry: jv }).then(function (msg) {
      result.style.color = "#0f766e";
      result.innerHTML = "JV " + esc(msg.action || "cancelled") + ": " + esc(msg.journal_entry) + "<br>Rows reset: " + esc(msg.rows_cleared || 0);
      loadReport();
    }).catch(function (e) {
      showResult(result, "error", "JV Cancel Failed", prettyError(errText(e)));
      console.error(e);
    });
  }

  function initTabs() {
    document.querySelectorAll(".pp-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        btn.classList.add("active");
        state.currentTab = btn.getAttribute("data-tab");
        setPageForCurrentTab(1);
        renderCurrentTab();
      });
    });
  }

  function setDefaultDates() {
    var now = new Date();
    var to = now.toISOString().slice(0, 10);
    var fromDate = new Date(now);
    fromDate.setDate(1);
    var from = fromDate.toISOString().slice(0, 10);
    el("pp-from-date").value = from;
    el("pp-to-date").value = to;
    el("pp-jv-posting-date").value = to;
    el("pp-pay-posting-date").value = to;
    el("pp-jv-employee-wise").checked = true;
    el("pp-jv-employee-wise").disabled = true;
  }

  setDefaultDates();
  initTabs();
  Promise.all([loadFilterOptions(), loadDataEntryMasters()]).then(loadReport).catch(function (e) {
    var message = prettyError(errText(e));
    el("pp-msg").textContent = "Load failed: " + message;
    var result = el("pp-jv-result");
    if (result) showResult(result, "error", "Initial Load Failed", message);
    console.error(e);
  });
  loadCompanies().catch(function (e) {
    console.error(e);
    var result = el("pp-jv-result");
    if (result) showResult(result, "error", "Company Load Failed", prettyError(errText(e)));
  });

  el("pp-jv-company").addEventListener("change", function () {
    loadAccountsForCompany();
    el("pp-pay-company").value = el("pp-jv-company").value || "";
    loadPaymentAccountsForCompany();
  });
  el("pp-pay-company").addEventListener("change", loadPaymentAccountsForCompany);
  el("pp-jv-payable-account").addEventListener("change", function () {
    var value = el("pp-jv-payable-account").value || "";
    if (value) el("pp-pay-payable-account").value = value;
  });
  el("pp-load-btn").addEventListener("click", function () { setPageForCurrentTab(1); loadReport(); });
  if (el("pp-item-group")) {
    el("pp-item-group").addEventListener("change", function () {
      refreshTopProductOptions();
      renderCurrentTab();
    });
  }
  if (el("pp-po-number")) {
    el("pp-po-number").addEventListener("change", function () { setPageForCurrentTab(1); renderCurrentTab(); });
  }
  if (el("pp-entry-no")) {
    el("pp-entry-no").addEventListener("change", function () { setPageForCurrentTab(1); renderCurrentTab(); });
  }
  if (el("pp-search-any")) {
    el("pp-search-any").addEventListener("input", function () { setPageForCurrentTab(1); renderCurrentTab(); });
  }
  el("pp-jv-preview-btn").addEventListener("click", previewJV);
  el("pp-jv-create-btn").addEventListener("click", createJV);
  el("pp-jv-cancel-btn").addEventListener("click", cancelJVEntry);
  el("pp-pay-preview-btn").addEventListener("click", previewPaymentJV);
  el("pp-pay-create-btn").addEventListener("click", createPaymentJV);
  el("pp-pay-cancel-btn").addEventListener("click", cancelPaymentJV);
  if (el("pp-summary-close")) {
    el("pp-summary-close").addEventListener("click", hidePerPieceSummary);
  }
  if (el("pp-summary-modal")) {
    el("pp-summary-modal").addEventListener("click", function (ev) {
      if (ev.target && ev.target.id === "pp-summary-modal") hidePerPieceSummary();
    });
  }
})();
</script>
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
	for fieldname in ("process_type", "process_size"):
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
		results.append("Updated: Cleared invalid Fetch From on Per Piece process fields")
	else:
		results.append("No change: Per Piece process field links already valid")


def _update_print_format(results: list[str]) -> None:
	if not frappe.db.exists("Print Format", "Per Piece Print"):
		results.append("Skipped: Print Format 'Per Piece Print' does not exist")
		return

	doc = frappe.get_doc("Print Format", "Per Piece Print")
	data = json.loads(doc.format_data or "[]")
	changed = False
	for row in data:
		if row.get("fieldname") == "productions":
			row["fieldname"] = "perpiece"
			row["label"] = "Per Piece"
			changed = True
	landscape_css = (
		"@media print {\n"
		"  @page { size: A4 landscape; margin: 8mm; }\n"
		"  .print-format table { font-size: 10px; }\n"
		"  .print-format td, .print-format th { padding: 3px 5px !important; }\n"
		"}\n"
	)
	current_css = doc.css or ""
	if landscape_css.strip() not in current_css:
		doc.css = current_css + ("\n" if current_css else "") + landscape_css
		changed = True
	if changed:
		doc.format_data = json.dumps(data, ensure_ascii=True)
		doc.save(ignore_permissions=True)
		results.append("Updated: Print Format 'Per Piece Print'")
	else:
		results.append("No change: Print Format 'Per Piece Print'")


def _update_web_page(results: list[str]) -> None:
	_upsert_doc(
		"Web Page",
		"per-piece-report",
		{
			"title": "Per Piece Salary Report",
			"route": "per-piece-report",
			"published": 1,
			"content_type": "HTML",
			"main_section_html": WEB_PAGE_HTML,
		},
		results,
	)


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
		"process_size",
		"Process Size",
		"Data",
		"",
		"process_type",
		results,
		doctype="Per Piece",
		read_only=1,
		in_list_view=1,
		default="No Size",
		no_copy=0,
		allow_fieldtype_override=1,
	)
	_ensure_custom_field(
		"item_group",
		"Item Group",
		"Link",
		"Item Group",
		"po_number",
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
		"item_group",
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
		"item",
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
		"employee",
		results,
		doctype="Per Piece Salary",
		read_only=0,
		in_list_view=0,
		no_copy=0,
		default="1",
	)
	_delete_custom_field("Item", "custom_process_type", results)
	_delete_custom_field("Item", "custom_process_size", results)
	_delete_custom_field("Item", "custom_rate_per_piece", results)
	_delete_custom_field("Per Piece Salary", "selected_items", results)
	_delete_custom_field("Per Piece Salary", "pp_filter_col_break", results)
	_delete_custom_field("Per Piece Salary", "pp_filters_section_break", results)
	_delete_custom_field("Per Piece Salary", "pp_filters_col_break_1", results)
	_delete_custom_field("Per Piece Salary", "pp_filters_col_break_2", results)
	_delete_custom_field("Per Piece Salary", "pp_filters_col_break_3", results)
	_ensure_field_property_setter("Per Piece Salary", "po_number", "reqd", "1", "Check", results)
	_ensure_per_piece_field_links(results)
	_migrate_jv_status(results)

	_upsert_doc(
		"Server Script",
		"get_per_piece_salary_report",
		{"script": GET_REPORT_SERVER_SCRIPT, "disabled": 0, "allow_guest": 0},
		results,
	)
	_upsert_doc(
		"Server Script",
		"create_per_piece_salary_entry",
		{
			"script_type": "API",
			"api_method": "create_per_piece_salary_entry",
			"module": "Payroll",
			"disabled": 0,
			"allow_guest": 0,
			"script": CREATE_ENTRY_SERVER_SCRIPT,
			"enable_rate_limit": 0,
			"rate_limit_count": 10,
			"rate_limit_seconds": 86400,
		},
		results,
	)
	_upsert_doc(
		"Server Script",
		"create_per_piece_salary_jv",
		{
			"script_type": "API",
			"api_method": "create_per_piece_salary_jv",
			"module": "Payroll",
			"disabled": 0,
			"allow_guest": 0,
			"script": CREATE_JV_SERVER_SCRIPT,
			"enable_rate_limit": 0,
			"rate_limit_count": 5,
			"rate_limit_seconds": 86400,
		},
		results,
	)
	_upsert_doc(
		"Server Script",
		"cancel_per_piece_salary_jv",
		{
			"script_type": "API",
			"api_method": "cancel_per_piece_salary_jv",
			"module": "Payroll",
			"disabled": 0,
			"allow_guest": 0,
			"script": CANCEL_JV_SERVER_SCRIPT,
			"enable_rate_limit": 0,
			"rate_limit_count": 5,
			"rate_limit_seconds": 86400,
		},
		results,
	)
	_upsert_doc(
		"Server Script",
		"create_per_piece_salary_payment_jv",
		{
			"script_type": "API",
			"api_method": "create_per_piece_salary_payment_jv",
			"module": "Payroll",
			"disabled": 0,
			"allow_guest": 0,
			"script": CREATE_PAYMENT_JV_SERVER_SCRIPT,
			"enable_rate_limit": 0,
			"rate_limit_count": 5,
			"rate_limit_seconds": 86400,
		},
		results,
	)
	_upsert_doc(
		"Server Script",
		"cancel_per_piece_salary_payment_jv",
		{
			"script_type": "API",
			"api_method": "cancel_per_piece_salary_payment_jv",
			"module": "Payroll",
			"disabled": 0,
			"allow_guest": 0,
			"script": CANCEL_PAYMENT_JV_SERVER_SCRIPT,
			"enable_rate_limit": 0,
			"rate_limit_count": 5,
			"rate_limit_seconds": 86400,
		},
		results,
	)
	_upsert_doc(
		"Client Script",
		"Per Piece Salary Update Child",
		{
			"dt": "Per Piece Salary",
			"enabled": 1,
			"view": "Form",
			"script": CLIENT_SCRIPT_SCRIPT,
		},
		results,
	)
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
	_update_web_page(results)
	_update_print_format(results)

	frappe.clear_cache()
	frappe.db.commit()
	return results
