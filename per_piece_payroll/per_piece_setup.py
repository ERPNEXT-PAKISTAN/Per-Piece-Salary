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
product = normalize_param(args.get("product"))
process_type = normalize_param(args.get("process_type"))
item_group = normalize_param(args.get("item_group"))
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

parent_filters = {"docstatus": ["<", 2]}
if from_date:
    parent_filters["to_date"] = [">=", from_date]
if to_date:
    parent_filters["from_date"] = ["<=", to_date]
if po_number:
    parent_filters["po_number"] = po_number
if entry_no:
    parent_filters["name"] = entry_no

parents = frappe.get_all(
    "Per Piece Salary",
    filters=parent_filters,
    fields=["name", "from_date", "to_date", "po_number", "item_group", "total_qty", "total_amount"],
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
        fields=["employee", "product", "process_type", "process_size", "sales_order"],
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
                "sales_order",
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
                    "item_group": row_item_group,
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
            "item_groups": item_groups,
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
        qty_index = 4
        rate_index = 5
        if len(parts) >= 7:
            process_size = normalize_param(parts[4]) or "No Size"
            qty_index = 5
            rate_index = 6
        if len(parts) >= 8:
            sales_order = normalize_param(parts[7])
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

  # If JV(s) were canceled directly from Journal Entry screen, unlink stale refs first.
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
            "sales_order": row.get("sales_order"),
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
    head = "Per Piece Salary Payment JV from " + str(from_date) + " to " + str(to_date)
    if header_remark:
        head = head + " | " + header_remark
    head = head + " | Amount " + str(round2(total_to_pay))
    je.user_remark = head

    for item in preview:
        amount = max(round2(item.get("to_pay_amount")), 0.0)
        if amount <= 0:
            continue
        employee_name = item.get("name1") or item.get("employee") or "-"
        debit_row = {
            "account": payable_account,
            "debit_in_account_currency": amount,
            "user_remark": "Salary Paid - " + str(employee_name) + " (" + str(item.get("employee")) + ")",
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
      return;
    }
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
      if (isSubmittedDoc(frm)) return;
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


WEB_PAGE_HTML = """
<div class="pp-wrap">
  <div class="pp-filters">
    <label>From Date <input type="date" id="pp-from-date" /></label>
    <label>To Date <input type="date" id="pp-to-date" /></label>
    <label>Employee <select id="pp-employee"><option value="">All</option></select></label>
    <label>Booking Status <select id="pp-booking-status"><option value="">All</option><option value="Booked">Booked</option><option value="UnBooked">UnBooked</option><option value="Partly Booked">Partly Booked</option></select></label>
    <label>Payment Status <select id="pp-payment-status"><option value="">All</option><option value="Paid">Paid</option><option value="Unpaid">Unpaid</option><option value="Partly Paid">Partly Paid</option></select></label>
    <label>Item Group <select id="pp-item-group"><option value="">All</option></select></label>
    <label>Product <select id="pp-product"><option value="">All</option></select></label>
    <label>Process Type <select id="pp-process-type"><option value="">All</option></select></label>
    <label>PO Number <select id="pp-po-number"><option value="">All</option></select></label>
    <label>Entry No <select id="pp-entry-no"><option value="">All</option></select></label>
    <label>Search <input type="text" id="pp-search-any" placeholder="Type any word..." /></label>
    <label id="pp-employee-summary-detail-wrap" style="display:none;">Detail <input type="checkbox" id="pp-employee-summary-detail" /></label>
    <button id="pp-load-btn" class="btn btn-primary" type="button">Load Report</button>
    <button id="pp-sync-status-btn" class="btn btn-default" type="button">Force Sync Status</button>
    <button id="pp-print-tab-btn" class="btn btn-default" type="button">Print Tab</button>
  </div>

  <div class="pp-workspace-switch">
    <button type="button" class="btn btn-default pp-workspace-btn active" id="pp-workspace-entry">Entry Workspace</button>
    <button type="button" class="btn btn-default pp-workspace-btn" id="pp-workspace-reporting">Reporting Workspace</button>
  </div>

  <div class="pp-tabs">
    <button type="button" class="pp-tab active" data-workspace="entry" data-tab="data_entry">Data Enter</button>
    <button type="button" class="pp-tab" data-workspace="entry" data-tab="salary_creation">Salary Creation</button>
    <button type="button" class="pp-tab" data-workspace="entry" data-tab="payment_manage">Payment Entry</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="all">History</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="jv_created">Salary Status</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="month_paid_unpaid">Month Paid/Unpaid</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="advances">Advances</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="employee_summary">Employee Summary</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="per_piece_salary">Employee item-wise</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="salary_slip">Salary Slip</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="po_number">PO Summary</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="po_detail_all">PO Detail Print</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="month_year_salary">Month/Year Salary</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="simple_month_amount">Month-wise</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="product">Product Summary</button>
    <button type="button" class="pp-tab" data-workspace="reporting" data-tab="process_product">Process Summary</button>
  </div>

  <div id="pp-msg" class="pp-msg"></div>
  <div id="pp-table-wrap" class="pp-table-wrap"></div>
  <div id="pp-totals" class="pp-totals"></div>
  <div id="pp-pagination" class="pp-pagination"></div>

  <div class="pp-jv-card" id="pp-salary-jv-card">
    <h4>Salary Creation Tab (Book Salary To Payable)</h4>
    <div class="pp-jv-grid">
      <label>Entry Filter (Unbooked) <select id="pp-jv-entry-filter"><option value="">All Unbooked Entries</option></select></label>
      <label>Selected Entries <input type="text" id="pp-jv-entry-multi" placeholder="Entry1, Entry2, Entry3" /></label>
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
      <button id="pp-jv-entry-clear" class="btn btn-default" type="button">Clear Entry Filter</button>
      <button id="pp-jv-entry-add" class="btn btn-default" type="button">Add Filter Entry</button>
      <button id="pp-jv-entry-remove" class="btn btn-default" type="button">Remove Filter Entry</button>
      <button id="pp-jv-entry-refresh" class="btn btn-default" type="button">Refresh Entries</button>
      <button id="pp-jv-preview-btn" class="btn btn-default" type="button">Quick Preview JV</button>
      <button id="pp-jv-create-btn" class="btn btn-primary" type="button">Post JV Entry</button>
      <select id="pp-jv-existing"><option value="">Select Posted JV</option></select>
      <button id="pp-jv-cancel-btn" class="btn btn-danger" type="button">Cancel JV Entry</button>
    </div>
    <div id="pp-jv-entry-meta" class="pp-msg" style="margin-top:6px;"></div>
    <div id="pp-jv-result" class="pp-jv-result"></div>
  </div>

  <div class="pp-jv-card" id="pp-payment-jv-card">
    <h4>Payment Entry Create for Employees (Pay Booked Salary)</h4>
    <div class="pp-jv-grid">
      <label>Entry Filter (Unpaid) <select id="pp-pay-entry-filter"><option value="">All Unpaid Entries</option></select></label>
      <label>Selected Entries <input type="text" id="pp-pay-entry-multi" placeholder="Entry1, Entry2, Entry3" /></label>
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
      <button id="pp-pay-entry-clear" class="btn btn-default" type="button">Clear Entry Filter</button>
      <button id="pp-pay-entry-add" class="btn btn-default" type="button">Add Filter Entry</button>
      <button id="pp-pay-entry-remove" class="btn btn-default" type="button">Remove Filter Entry</button>
      <button id="pp-pay-entry-refresh" class="btn btn-default" type="button">Refresh Entries</button>
      <button id="pp-pay-preview-btn" class="btn btn-default" type="button">Quick Preview Payment JV</button>
      <button id="pp-pay-create-btn" class="btn btn-primary" type="button">Post Payment JV</button>
      <select id="pp-pay-existing"><option value="">Select Payment JV</option></select>
      <button id="pp-pay-cancel-btn" class="btn btn-danger" type="button">Cancel Payment JV</button>
    </div>
    <div id="pp-pay-entry-meta" class="pp-msg" style="margin-top:6px;"></div>
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
        <div style="display:flex;gap:8px;align-items:center;">
          <button type="button" class="btn btn-default" id="pp-summary-print">Print</button>
          <button type="button" class="btn btn-default" id="pp-summary-close">Close</button>
        </div>
      </div>
      <div id="pp-summary-content" class="pp-modal-body"></div>
    </div>
  </div>

  <div id="pp-action-modal" class="pp-modal" style="display:none;">
    <div class="pp-modal-card pp-action-card">
      <div class="pp-modal-head">
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="pp-action-logo" id="pp-action-logo">TCPL</div>
          <div>
            <div class="pp-modal-title" id="pp-action-title">Confirm Action</div>
            <div class="pp-modal-sub" id="pp-action-sub">Please confirm to continue.</div>
          </div>
        </div>
        <button type="button" class="btn btn-default" id="pp-action-close">Close</button>
      </div>
      <div class="pp-modal-body">
        <div id="pp-action-icon" class="pp-action-icon pp-action-icon-info">i</div>
        <div id="pp-action-message" style="font-size:14px;color:#334155;margin:8px 0 12px 0;"></div>
        <div id="pp-action-meta" style="font-size:13px;color:#0f766e;font-weight:600;margin-bottom:12px;"></div>
        <div id="pp-action-buttons" style="display:flex;gap:8px;justify-content:flex-end;"></div>
      </div>
    </div>
  </div>
</div>

<style>
  .pp-wrap { padding: 16px; background: #f8fbff; border-radius: 12px; }
  .pp-filters { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
  .pp-filters label { display: flex; flex-direction: column; gap: 4px; min-width: 180px; font-size: 12px; color: #334155; }
  .pp-filters input, .pp-filters select { border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 10px; font-size: 13px; }
  .pp-workspace-switch { display: flex; gap: 8px; margin: 6px 0 8px 0; }
  .pp-workspace-btn { color: #fff !important; border-color: transparent !important; font-weight: 600; }
  #pp-workspace-entry { background: #0f766e !important; }
  #pp-workspace-reporting { background: #1d4ed8 !important; }
  #pp-workspace-entry.active { background: #065f46 !important; color: #fff !important; border-color: #064e3b !important; }
  #pp-workspace-reporting.active { background: #1e40af !important; color: #fff !important; border-color: #1e3a8a !important; }
  .pp-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
  .pp-tab { border: 1px solid #bfdbfe; background: #eff6ff; color: #1e3a8a; border-radius: 8px; padding: 6px 10px; font-size: 12px; }
  .pp-tab.active { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
  .pp-msg { margin: 8px 0; color: #475569; font-size: 12px; }
  .pp-table-wrap { overflow: auto; background: #fff; border: 1px solid #dbeafe; border-radius: 8px; }
  .pp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .pp-table th, .pp-table td { border: 1px solid #e2e8f0; padding: 7px 9px; }
  .pp-table th { background: #eff6ff; color: #1e3a8a; position: sticky; top: 0; z-index: 2; }
  .pp-table tr.pp-year-total td { background: #f1f5f9; font-weight: 700; color: #0f172a; }
  .pp-table tr.pp-group-head td { background: #e2e8f0; font-weight: 700; color: #0f172a; }
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
  .pp-wrap.pp-entry-screen .pp-filters { display: none; }
  .pp-wrap.pp-entry-screen .pp-tabs { margin-top: 0; }
  .pp-wrap.pp-entry-screen #pp-msg { margin-top: 2px; }
  .pp-action-card { width: min(560px, 95vw); }
  .pp-action-logo {
    width: 36px; height: 36px; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 800; color: #fff; background: linear-gradient(135deg, #1d4ed8, #0f766e);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.28);
  }
  .pp-action-icon {
    width: 42px; height: 42px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center;
    font-size: 22px; font-weight: 800; line-height: 1;
  }
  .pp-action-icon-success { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
  .pp-action-icon-error { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
  .pp-action-icon-info { background: #e0f2fe; color: #0c4a6e; border: 1px solid #7dd3fc; }
</style>

<script>
(function () {
  var state = {
    workspaceMode: "entry",
    currentTab: "data_entry",
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
    workflowHistoryDate: {
      data_entry: { from: "", to: "" },
      salary_creation: { from: "", to: "" },
      payment_manage: { from: "", to: "" }
    },
    workflowStatusFilter: {
      data_entry: { booking: "", payment: "" },
      salary_creation: { booking: "", payment: "" },
      payment_manage: { booking: "", payment: "" }
    },
    entryRows: [],
    entryMeta: {},
    employeeSummaryDetail: false,
    pageSize: 20,
    pageByTab: {},
    historyPageByTab: {},
    forcedEntryNo: "",
    paymentPrefill: null,
    summaryPrintMeta: { heading: "Per Piece Salary Summary", subtitle: "", company: "", date_range: "" },
    lastTabRender: { mode: "dom", columns: [], rows: [] }
  };

  function el(id) { return document.getElementById(id); }
  function esc(v) { var d = document.createElement("div"); d.textContent = v == null ? "" : String(v); return d.innerHTML; }
  function num(v) { var n = Number(v || 0); return isNaN(n) ? 0 : n; }
  function whole(v) { return Math.max(0, Math.round(num(v) * 100) / 100); }
  function fmt(v) { return num(v).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
  function entrySequenceNo(name) {
    var txt = String(name || "").trim();
    var m = txt.match(/-(\\d+)\\s*$/);
    return m ? (parseInt(m[1], 10) || 0) : 0;
  }
  function compareEntryNoDesc(a, b) {
    var as = entrySequenceNo(a);
    var bs = entrySequenceNo(b);
    if (as !== bs) return bs - as;
    return String(b || "").localeCompare(String(a || ""));
  }
  function lineRate(rate, qty, amount) {
    var r = num(rate);
    var q = num(qty);
    var a = num(amount);
    if (r > 0) return r;
    if (q > 0) return a / q;
    return 0;
  }
  function applyReportRateProcessFix(rows) {
    var master = state && state.entryMeta ? (state.entryMeta.masterProcessRows || []) : [];
    if (!master.length || !rows || !rows.length) return;
    var grouped = {};
    master.forEach(function (item) {
      var product = String((item && item.item) || "").trim();
      var processType = String((item && item.process_type) || "").trim();
      if (!product || !processType) return;
      var key = product + "||" + processType;
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push({
        employee: String((item && item.employee) || "").trim(),
        process_size: String((item && item.process_size) || "").trim() || "No Size",
        rate: num(item && item.rate)
      });
    });
    (rows || []).forEach(function (row) {
      var product = String((row && row.product) || "").trim();
      var processType = String((row && row.process_type) || "").trim();
      if (!product || !processType) return;
      var key = product + "||" + processType;
      var candidates = grouped[key] || [];
      if (!candidates.length) return;
      var employee = String((row && row.employee) || "").trim();
      var exactEmp = employee ? candidates.filter(function (x) { return String(x.employee || "") === employee; }) : [];
      var scoped = exactEmp.length ? exactEmp : candidates;
      var rowSize = String((row && row.process_size) || "").trim() || "No Size";
      var chosen = null;
      if (rowSize && rowSize !== "No Size") {
        chosen = scoped.find(function (x) { return String(x.process_size || "").trim() === rowSize; }) || null;
      }
      if (!chosen && scoped.length === 1) {
        chosen = scoped[0];
      }
      if (!chosen && rowSize === "No Size") {
        var sizeMap = {};
        scoped.forEach(function (x) { sizeMap[String(x.process_size || "No Size")] = 1; });
        if (Object.keys(sizeMap).length === 1) chosen = scoped[0];
      }
      if (!chosen) return;
      var existingRate = num(row && row.rate);
      var correctedRate = num(chosen.rate);
      if ((!row.process_size || String(row.process_size).trim() === "No Size") && chosen.process_size && existingRate <= 0) {
        row.process_size = chosen.process_size;
      }
      // Never overwrite saved/manual rate. Only backfill missing rate.
      if (correctedRate > 0 && existingRate <= 0) {
        row.rate = correctedRate;
      }
      var qty = num(row && row.qty);
      var finalRate = num(row && row.rate);
      if (qty > 0 && finalRate > 0) {
        var correctedAmount = whole(qty * finalRate);
        var existingAmount = num(row && row.amount);
        if (existingAmount <= 0) {
          row.amount = correctedAmount;
        }
      }
    });
  }
  function normalizeReportStatusValues(rows) {
    (rows || []).forEach(function (row) {
      if (!row) return;
      var amount = num(row.amount);
      if (amount < 0) amount = 0;

      var jvName = String((row.jv_entry_no || "")).trim();
      var jvStatusRaw = String((row.jv_status || "")).trim();
      var jvStatus = jvStatusRaw === "Accounted" ? "Posted" : (jvStatusRaw || "Pending");
      var isJVPosted = !!jvName && (jvStatus === "Posted");

      var booked = num(row.booked_amount);
      if (booked < 0) booked = 0;
      if (!isJVPosted) booked = 0;
      if (isJVPosted && booked <= 0) booked = amount;
      if (booked > amount) booked = amount;

      var paid = num(row.paid_amount);
      if (paid < 0) paid = 0;
      if (paid > booked) paid = booked;

      var unpaid = num(row.unpaid_amount);
      var calculatedUnpaid = Math.max(booked - paid, 0);
      if (unpaid < 0 || unpaid > booked || Math.abs(unpaid - calculatedUnpaid) > 0.01) {
        unpaid = calculatedUnpaid;
      }
      var unbooked = isJVPosted ? 0 : Math.max(amount - booked, 0);

      var bookingStatus = isJVPosted ? "Booked" : "UnBooked";
      var paymentStatus = "Unpaid";
      if (booked > 0) {
        if (unpaid <= 0.005) paymentStatus = "Paid";
        else if (paid > 0.005) paymentStatus = "Partly Paid";
      }

      row.jv_status = jvStatus;
      row.booking_status = bookingStatus;
      row.payment_status = paymentStatus;
      row.amount = whole(amount);
      row.booked_amount = whole(booked);
      row.paid_amount = whole(paid);
      row.unpaid_amount = whole(unpaid);
      row.unbooked_amount = whole(unbooked);
    });
  }
  function parseDecimalInput(v) {
    var raw = String(v == null ? "" : v).replace(/,/g, "").trim();
    if (!raw) return 0;
    var n = Number(raw);
    return isNaN(n) ? 0 : Math.max(0, Math.round(n * 100) / 100);
  }
  function baseProcessSizeOptions() {
    return ["No Size", "Single", "Double", "King", "Supper King"];
  }
  function getProcessSortRank(product, processType, processSize) {
    var p = String(product || "").trim();
    var t = String(processType || "").trim();
    var s = String(processSize || "").trim() || "No Size";
    if (!t) return 999999;
    var rows = (state.entryMeta && state.entryMeta.masterProcessRows) || [];
    var best = 999999;
    var bestType = 999999;
    rows.forEach(function (r, i) {
      var rp = String((r && r.item) || "").trim();
      var rt = String((r && r.process_type) || "").trim();
      var rs = String((r && r.process_size) || "").trim() || "No Size";
      var rank = parseInt((r && r.idx) || 0, 10);
      if (!rank || rank < 0) rank = i + 1;
      if (p && rp === p && rt === t && rs === s) best = Math.min(best, rank);
      if (p && rp === p && rt === t) bestType = Math.min(bestType, rank);
      if (!p && rt === t && rs === s) best = Math.min(best, rank + 10000);
      if (!p && rt === t) bestType = Math.min(bestType, rank + 10000);
    });
    if (best < 999999) return best;
    if (bestType < 999999) return bestType;
    return 999999;
  }
  function compareByProcessSequence(a, b, productHintA, productHintB) {
    var pa = String(productHintA || (a && a.product) || "").trim();
    var pb = String(productHintB || (b && b.product) || "").trim();
    var ra = getProcessSortRank(pa, a && a.process_type, a && a.process_size);
    var rb = getProcessSortRank(pb, b && b.process_type, b && b.process_size);
    if (ra !== rb) return ra - rb;
    var ta = String((a && a.process_type) || "");
    var tb = String((b && b.process_type) || "");
    if (ta !== tb) return ta.localeCompare(tb);
    var sa = String((a && a.process_size) || "No Size");
    var sb = String((b && b.process_size) || "No Size");
    return sa.localeCompare(sb);
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
  function currentCompanyLabel() {
    var jv = el("pp-jv-company");
    var pay = el("pp-pay-company");
    var company = (jv && jv.value) || (pay && pay.value) || "";
    if (company) return String(company);
    var row = (state.rows || [])[0] || {};
    return String(row.company || "");
  }
  function currentDateRangeLabel() {
    var from = (el("pp-from-date") && el("pp-from-date").value) || "";
    var to = (el("pp-to-date") && el("pp-to-date").value) || "";
    if (from && to) return from + " to " + to;
    return from || to || "";
  }
  function getCurrentTabLabel() {
    var btn = document.querySelector(".pp-tab.active");
    if (btn) return String(btn.textContent || "").trim();
    return String(state.currentTab || "");
  }
  function setSummaryHeading(text) {
    var titleEl = document.querySelector("#pp-summary-modal .pp-modal-title");
    if (titleEl) titleEl.textContent = text || "Per Piece Salary Summary";
  }
  function summaryHeaderHtml(heading, subtitleText) {
    var company = currentCompanyLabel();
    var dateRange = currentDateRangeLabel();
    var html = "<div class='pp-inline-summary-header' style='margin-bottom:12px;border-bottom:2px solid #cbd5e1;padding-bottom:8px;'>";
    html += "<div style='font-size:22px;font-weight:800;color:#0f172a;'>" + esc(company || "Company") + "</div>";
    if (dateRange) {
      html += "<div style='font-size:12px;color:#64748b;margin-top:2px;'>Date: " + esc(dateRange) + "</div>";
    }
    html += "</div>";
    return html;
  }
  function setSummaryModal(heading, subtitleText, bodyHtml) {
    var modal = el("pp-summary-modal");
    var subtitle = el("pp-summary-subtitle");
    var content = el("pp-summary-content");
    if (!modal || !subtitle || !content) return;
    setSummaryHeading(heading || "Per Piece Salary Summary");
    subtitle.textContent = subtitleText || "";
    content.innerHTML = bodyHtml || "";
    state.summaryPrintMeta = {
      heading: heading || "Per Piece Salary Summary",
      subtitle: subtitleText || "",
      company: currentCompanyLabel(),
      date_range: currentDateRangeLabel()
    };
    modal.style.display = "flex";
  }
  function buildSalarySlipGroupDetail(group) {
    if (!group) return null;
    var processTotals = {};
    var itemTotals = {};
    (group.rows || []).forEach(function (r) {
      var processKey = String(r.process_type || "") + "||" + String(r.process_size || "No Size");
      if (!processTotals[processKey]) {
        processTotals[processKey] = {
          process_type: r.process_type || "",
          process_size: r.process_size || "No Size",
          qty: 0,
          amount: 0,
          rate: 0
        };
      }
      processTotals[processKey].qty += num(r.qty);
      processTotals[processKey].amount += num(r.amount);
      var itemKey = String(r.product || "") || "(Blank)";
      if (!itemTotals[itemKey]) {
        itemTotals[itemKey] = {
          product: r.product || "",
          qty: 0,
          amount: 0,
          rate: 0
        };
      }
      itemTotals[itemKey].qty += num(r.qty);
      itemTotals[itemKey].amount += num(r.amount);
    });
    return {
      processRows: Object.keys(processTotals).map(function (key) {
        var item = processTotals[key];
        item.rate = avgRate(item.qty, item.amount);
        return item;
      }).sort(function (a, b) {
        return compareByProcessSequence(a, b, "", "");
      }),
      itemRows: Object.keys(itemTotals).sort().map(function (key) {
        var item = itemTotals[key];
        item.rate = avgRate(item.qty, item.amount);
        return item;
      })
    };
  }
  function getJournalEntryDoc(name) {
    var jvName = String(name || "").trim();
    if (!jvName) return Promise.resolve(null);
    state.jvDocCache = state.jvDocCache || {};
    if (Object.prototype.hasOwnProperty.call(state.jvDocCache, jvName)) {
      return Promise.resolve(state.jvDocCache[jvName]);
    }
    return callApi("frappe.client.get", { doctype: "Journal Entry", name: jvName })
      .then(function (doc) {
        state.jvDocCache[jvName] = doc || null;
        return state.jvDocCache[jvName];
      })
      .catch(function () {
        state.jvDocCache[jvName] = null;
        return null;
      });
  }
  function getSalarySlipFinancials(group) {
    var employee = group && group.employee ? String(group.employee) : "";
    var amount = num(group && group.amount);
    var paidAmount = 0;
    var bookedAmount = 0;
    var unbookedAmount = 0;
    var postedAmount = 0;
    (group && group.rows || []).forEach(function (row) {
      var status = String(row.jv_status || "");
      var hasJV = !!String(row.jv_entry_no || "").trim();
      if (hasJV && status === "Posted") {
        bookedAmount += num(row.amount);
        paidAmount += num(row.paid_amount);
        postedAmount += num(row.amount);
      } else {
        unbookedAmount += num(row.amount);
      }
    });
    var closingAdvance = num((state.advanceBalances || {})[employee]);
    var jvMap = {};
    (group && group.rows || []).forEach(function (row) {
      var jvName = String(row.jv_entry_no || "").trim();
      if (!jvName) return;
      if (String(row.jv_status || "") !== "Posted") return;
      jvMap[jvName] = 1;
    });
    var jvNames = Object.keys(jvMap);
    if (!jvNames.length) {
      var openingNoJV = closingAdvance;
      return Promise.resolve({
        current_period_salary: amount,
        booked_salary_amount: 0,
        unbooked_salary_amount: unbookedAmount || amount,
        opening_advance_balance: openingNoJV,
        advance_deduction: 0,
        allowance: 0,
        other_deduction: 0,
        gross_amount: 0,
        net_amount: 0,
        paid_amount: 0,
        unpaid_amount: 0,
        closing_advance_balance: openingNoJV
      });
    }
    return Promise.all(jvNames.map(function (jvName) {
      return getJournalEntryDoc(jvName);
    })).then(function (docs) {
      var advanceDeduction = 0;
      var otherDeduction = 0;
      var netAmount = 0;
      docs.forEach(function (doc) {
        if (!doc || Number(doc.docstatus) !== 1) return;
        (doc && doc.accounts || []).forEach(function (acc) {
          var party = String(acc.party || "").trim();
          var credit = num(acc.credit_in_account_currency || acc.credit);
          var remark = String(acc.user_remark || "");
          if (credit <= 0) return;
          var isAdvance = remark.indexOf("Advance Recovery - " + employee) === 0;
          var isDeduction = remark.indexOf("Salary Deduction - " + employee) === 0;
          var isNet = remark.indexOf("Net Salary - " + employee) === 0;
          var matchesParty = party === employee;
          if (isAdvance || (matchesParty && remark.indexOf("Advance Recovery - ") === 0)) {
            advanceDeduction += credit;
          } else if (isDeduction || (matchesParty && remark.indexOf("Salary Deduction - ") === 0)) {
            otherDeduction += credit;
          } else if (isNet || (matchesParty && remark.indexOf("Net Salary - ") === 0)) {
            netAmount += credit;
          }
        });
      });
      advanceDeduction = Math.max(0, advanceDeduction);
      otherDeduction = Math.max(0, otherDeduction);
      var postedBaseAmount = Math.max(0, postedAmount);
      if (netAmount <= 0) {
        netAmount = Math.max(postedBaseAmount - advanceDeduction - otherDeduction, 0);
      }
      var postedAllowance = Math.max(netAmount - postedBaseAmount + advanceDeduction + otherDeduction, 0);
      var grossAmount = bookedAmount + postedAllowance;
      var openingAdvance = closingAdvance + advanceDeduction;
      var closingAdvanceProjected = openingAdvance - advanceDeduction;
      var adjustedUnpaid = Math.max(netAmount - paidAmount, 0);
      return {
        current_period_salary: amount,
        booked_salary_amount: bookedAmount,
        unbooked_salary_amount: unbookedAmount,
        opening_advance_balance: openingAdvance,
        advance_deduction: advanceDeduction,
        allowance: postedAllowance,
        other_deduction: otherDeduction,
        gross_amount: grossAmount,
        net_amount: netAmount,
        paid_amount: paidAmount,
        unpaid_amount: adjustedUnpaid,
        closing_advance_balance: closingAdvanceProjected
      };
    });
  }
  function showSalarySlipPrint(employee, options) {
    options = options || {};
    var mode = String(options.mode || "detail");
    var selectedEntry = String(options.entry || "").trim();
    var groups = buildSalarySlipGroups(getRowsByHeaderFilters(state.rows || []));
    var group = null;
    groups.forEach(function (g) {
      if (!group && String(g.employee || "") === String(employee || "")) group = g;
    });
    if (!group) {
      setSummaryModal("Salary Slip Detail", employee || "", "<div style='color:#b91c1c;'>No salary detail found for current filters.</div>");
      return;
    }
    var scopedRows = (group.rows || []).filter(function (r) {
      if (!selectedEntry) return true;
      return String(r.per_piece_salary || "") === selectedEntry;
    });
    if (!scopedRows.length) {
      setSummaryModal("Salary Slip Detail", employee || "", "<div style='color:#b91c1c;'>No rows found for selected salary entry.</div>");
      return;
    }
    var scopedQty = 0;
    var scopedAmount = 0;
    scopedRows.forEach(function (r) {
      scopedQty += num(r.qty);
      scopedAmount += num(r.amount);
    });
    var scopedGroup = {
      employee: group.employee || "",
      name1: group.name1 || "",
      qty: scopedQty,
      amount: scopedAmount,
      source_count: scopedRows.length,
      rate: avgRate(scopedQty, scopedAmount),
      rows: scopedRows
    };
    setSummaryModal("Salary Slip Detail", employee || "", "<div style='color:#334155;'>Loading salary slip...</div>");
    var detail = buildSalarySlipGroupDetail(scopedGroup);
    var slipFrom = "";
    var slipTo = "";
    scopedRows.forEach(function (r) {
      var rowFrom = String(r.from_date || "").trim();
      var rowTo = String(r.to_date || "").trim();
      if (rowFrom && (!slipFrom || rowFrom < slipFrom)) slipFrom = rowFrom;
      if (rowTo && (!slipTo || rowTo > slipTo)) slipTo = rowTo;
    });
    var slipRange = "";
    if (slipFrom && slipTo) slipRange = slipFrom + " to " + slipTo;
    else slipRange = slipFrom || slipTo || currentDateRangeLabel();
    var employeeTitle = scopedGroup.name1 || scopedGroup.employee || "";
    var subtitleText = employeeTitle + (selectedEntry ? (" | Entry: " + selectedEntry) : "");
    getSalarySlipFinancials(scopedGroup).then(function (financials) {
      var html = summaryHeaderHtml("Salary Slip Detail", subtitleText);
      html += "<div style='text-align:center;margin:2px 0 14px 0;'>";
      html += "<div style='font-size:30px;font-weight:800;color:#0f172a;line-height:1.1;'>" + esc(employeeTitle || "Employee") + "</div>";
      html += "<div style='font-size:15px;font-weight:700;color:#334155;margin-top:6px;'>" + esc(mode === "product" ? "Product wise Detail Report" : "Detail Salary Slip") + "</div>";
      if (slipRange) {
        html += "<div style='font-size:14px;font-weight:700;color:#475569;margin-top:4px;'>Date: " + esc(slipRange) + "</div>";
      }
      html += "</div>";
      html += "<div class='pp-summary-chips'>"
        + "<span class='pp-summary-chip'>Employee: " + esc(scopedGroup.employee || "-") + "</span>"
        + "<span class='pp-summary-chip'>Entries: " + esc(scopedGroup.source_count || 0) + "</span>"
        + "<span class='pp-summary-chip'>Qty: " + esc(fmt(scopedGroup.qty)) + "</span>"
        + "<span class='pp-summary-chip'>Rate: " + esc(fmt(scopedGroup.rate)) + "</span>"
        + "<span class='pp-summary-chip'>Amount: " + esc(fmt(scopedGroup.amount)) + "</span>"
        + "</div>";

      if (mode === "product") {
        var productDetailMap = {};
        scopedRows.forEach(function (r) {
          var k = [String(r.po_number || ""), String(r.product || ""), String(r.process_type || ""), String(r.process_size || "No Size")].join("||");
          if (!productDetailMap[k]) {
            productDetailMap[k] = { po_number: r.po_number || "", product: r.product || "", process_type: r.process_type || "", process_size: r.process_size || "No Size", qty: 0, amount: 0, rate: 0 };
          }
          productDetailMap[k].qty += num(r.qty);
          productDetailMap[k].amount += num(r.amount);
        });
        var productDetailRows = Object.keys(productDetailMap).map(function (k) {
          var row = productDetailMap[k];
          row.rate = avgRate(row.qty, row.amount);
          return row;
        }).sort(function (a, b) {
          var poa = String(a.po_number || "");
          var pob = String(b.po_number || "");
          if (poa !== pob) return poa.localeCompare(pob);
          var pa = String(a.product || "");
          var pb = String(b.product || "");
          if (pa !== pb) return pa.localeCompare(pb);
          return compareByProcessSequence(a, b, pa, pb);
        });
        html += "<h4 style='margin:10px 0 6px 0;'>Product wise Detail Report</h4>";
        html += "<table class='pp-table'><thead><tr><th>PO Number</th><th>Product</th><th>Process</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
        productDetailRows.forEach(function (r) {
          html += "<tr><td>" + esc(r.po_number || "") + "</td><td>" + esc(r.product || "") + "</td><td>" + esc(r.process_type || "") + "</td><td>" + esc(r.process_size || "No Size") + "</td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num'>" + esc(fmt(r.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td></tr>";
        });
        html += "<tr class='pp-year-total'><td>Total</td><td></td><td></td><td></td><td class='num'>" + esc(fmt(scopedGroup.qty)) + "</td><td class='num'>" + esc(fmt(scopedGroup.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(scopedGroup.amount)) + "</td></tr>";
        html += "</tbody></table>";
      } else {
        var mergedMap = {};
        scopedRows.forEach(function (r) {
          var item = String(r.product || "").trim() || "(Blank)";
          var pkey = String(r.po_number || "") + "||" + item + "||" + String(r.process_type || "") + "||" + String(r.process_size || "No Size");
          if (!mergedMap[pkey]) {
            mergedMap[pkey] = {
              po_number: r.po_number || "",
              product: item,
              process_type: r.process_type || "",
              process_size: r.process_size || "No Size",
              qty: 0,
              amount: 0
            };
          }
          mergedMap[pkey].qty += num(r.qty);
          mergedMap[pkey].amount += num(r.amount);
        });
        var mergedRows = Object.keys(mergedMap).map(function (k) {
          var row = mergedMap[k];
          row.rate = avgRate(row.qty, row.amount);
          return row;
        }).sort(function (a, b) {
          var poa = String(a.po_number || "");
          var pob = String(b.po_number || "");
          if (poa !== pob) return poa.localeCompare(pob);
          var pa = String(a.product || "");
          var pb = String(b.product || "");
          if (pa !== pb) return pa.localeCompare(pb);
          return compareByProcessSequence(a, b, pa, pb);
        });
        var byItem = {};
        mergedRows.forEach(function (r) {
          var item = (r.po_number || "") + "||" + (r.product || "(Blank)");
          if (!byItem[item]) byItem[item] = [];
          byItem[item].push(r);
        });
        html += "<h4 style='margin:10px 0 6px 0;'>Item Wise Summary (with Process)</h4>";
        html += "<table class='pp-table'><thead><tr><th>PO Number</th><th>Item</th><th>Process</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
        Object.keys(byItem).sort().forEach(function (itemKey) {
          var itemParts = String(itemKey || "").split("||");
          var itemPo = itemParts[0] || "";
          var item = itemParts.slice(1).join("||") || "(Blank)";
          var iQty = 0;
          var iAmount = 0;
          (byItem[itemKey] || []).forEach(function (r) {
            iQty += num(r.qty);
            iAmount += num(r.amount);
            html += "<tr><td>" + esc(itemPo) + "</td><td>" + esc(item) + "</td><td>" + esc(r.process_type || "") + "</td><td>" + esc(r.process_size || "No Size") + "</td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num'>" + esc(fmt(r.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td></tr>";
          });
          html += "<tr class='pp-year-total'><td>" + esc(itemPo) + "</td><td>" + esc(item) + " Total</td><td></td><td></td><td class='num'>" + esc(fmt(iQty)) + "</td><td class='num'>" + esc(fmt(avgRate(iQty, iAmount))) + "</td><td class='num pp-amt-col'>" + esc(fmt(iAmount)) + "</td></tr>";
        });
        html += "<tr class='pp-year-total'><td>Grand Total</td><td></td><td></td><td></td><td class='num'>" + esc(fmt(scopedGroup.qty)) + "</td><td class='num'>" + esc(fmt(scopedGroup.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(scopedGroup.amount)) + "</td></tr>";
        html += "</tbody></table>";
      }

      html += "<h4 style='margin:12px 0 6px 0;'>Financial Summary</h4>";
      html += "<div style='border:1px solid #cbd5e1;border-radius:10px;background:#f8fafc;padding:12px 14px;margin-top:8px;font-family:Calibri,Tahoma,Arial,sans-serif;font-weight:400;'>";
      html += "<div style='display:flex;gap:18px;flex-wrap:wrap;'>";
      html += "<div style='flex:1;min-width:220px;border-right:1px solid #d6dee8;padding-right:12px;'>";
      html += "<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>Booked Salary</span><span>" + esc(fmt(financials.booked_salary_amount)) + "</span></div>";
      html += "<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>UnBooked Salary</span><span>" + esc(fmt(financials.unbooked_salary_amount)) + "</span></div>";
      html += "<div style='margin:4px 0;padding-bottom:6px;border-bottom:1px solid #d6dee8;display:flex;justify-content:space-between;gap:10px;'><span>Net Salary Booked</span><span>" + esc(fmt(financials.net_amount)) + "</span></div>";
      html += "<div style='margin:10px 0 0 0;display:flex;justify-content:space-between;gap:10px;'><span>Paid</span><span>" + esc(fmt(financials.paid_amount)) + "</span></div>";
      html += "<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>Unpaid</span><span>" + esc(fmt(financials.unpaid_amount)) + "</span></div>";
      html += "</div>";
      html += "<div style='flex:1;min-width:220px;border-right:1px solid #d6dee8;padding-right:12px;'>";
      html += "<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>Allowance</span><span>" + esc(fmt(financials.allowance)) + "</span></div>";
      html += "<div style='margin:4px 0;padding-bottom:6px;border-bottom:1px solid #d6dee8;display:flex;justify-content:space-between;gap:10px;'><span>Other Deduction</span><span>" + esc(fmt(financials.other_deduction)) + "</span></div>";
      html += "</div>";
      html += "<div style='flex:1;min-width:240px;'>";
      html += "<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span style='color:#92400e;'>Opening Advance</span><span style='color:#92400e;'>" + esc(fmt(financials.opening_advance_balance)) + "</span></div>";
      html += "<div style='margin:4px 0;padding-bottom:6px;border-bottom:1px solid #d6dee8;display:flex;justify-content:space-between;gap:10px;'><span style='color:#92400e;'>Advance Deduction</span><span style='color:#92400e;'>" + esc(fmt(financials.advance_deduction)) + "</span></div>";
      html += "<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span style='color:#166534;'>Closing Advance</span><span style='color:#166534;'>" + esc(fmt(financials.closing_advance_balance)) + "</span></div>";
      html += "</div>";
      html += "</div>";
      html += "</div>";
      html += "<table style='width:100%;margin-top:22px;border-collapse:collapse;table-layout:fixed;'><tr>"
        + "<td style='width:33.33%;padding-top:20px;vertical-align:top;text-align:center;'><span class='pp-sign-line' style='margin:0 auto;'>Created By</span></td>"
        + "<td style='width:33.33%;padding-top:20px;vertical-align:top;text-align:center;'><span class='pp-sign-line' style='margin:0 auto;'>Approved By</span></td>"
        + "<td style='width:33.33%;padding-top:20px;vertical-align:top;text-align:center;'><span class='pp-sign-line' style='margin:0 auto;'>Received By</span></td>"
        + "</tr></table>";
      setSummaryModal("Salary Slip Detail", subtitleText, html);
    }).catch(function (e) {
      setSummaryModal("Salary Slip Detail", subtitleText, "<div style='color:#b91c1c;'>Failed to load salary slip: " + esc(prettyError(errText(e))) + "</div>");
    });
  }

  function showSalaryEntryWisePrints(employee) {
    var groups = buildSalarySlipGroups(getRowsByHeaderFilters(state.rows || []));
    var group = null;
    groups.forEach(function (g) {
      if (!group && String(g.employee || "") === String(employee || "")) group = g;
    });
    if (!group) {
      setSummaryModal("Entry Wise Prints", employee || "", "<div style='color:#b91c1c;'>No salary rows found.</div>");
      return;
    }
    var entryMap = {};
    (group.rows || []).forEach(function (r) {
      var entry = String(r.per_piece_salary || "").trim();
      if (!entry) return;
      if (!entryMap[entry]) {
        entryMap[entry] = { per_piece_salary: entry, from_date: r.from_date || "", to_date: r.to_date || "", qty: 0, amount: 0 };
      }
      entryMap[entry].qty += num(r.qty);
      entryMap[entry].amount += num(r.amount);
      if (r.from_date && (!entryMap[entry].from_date || String(r.from_date) < String(entryMap[entry].from_date))) entryMap[entry].from_date = r.from_date;
      if (r.to_date && (!entryMap[entry].to_date || String(r.to_date) > String(entryMap[entry].to_date))) entryMap[entry].to_date = r.to_date;
    });
    var entries = Object.keys(entryMap).sort(function (a, b) { return String(b).localeCompare(String(a)); }).map(function (k) { return entryMap[k]; });
    if (!entries.length) {
      setSummaryModal("Entry Wise Prints", employee || "", "<div style='color:#b91c1c;'>No salary entries found.</div>");
      return;
    }
    var html = "<table class='pp-table'><thead><tr><th>Entry No</th><th>From Date</th><th>To Date</th><th>Qty</th><th>Amount</th><th>Print Detail</th><th>Print Product</th></tr></thead><tbody>";
    entries.forEach(function (r) {
      html += "<tr><td>" + esc(r.per_piece_salary) + "</td><td>" + esc(r.from_date || "") + "</td><td>" + esc(r.to_date || "") + "</td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td><td><button type='button' class='btn btn-xs btn-primary pp-salary-entry-print' data-mode='detail' data-employee='" + esc(employee || "") + "' data-entry='" + esc(r.per_piece_salary) + "'>Print</button></td><td><button type='button' class='btn btn-xs btn-primary pp-salary-entry-print' data-mode='product' data-employee='" + esc(employee || "") + "' data-entry='" + esc(r.per_piece_salary) + "'>Print</button></td></tr>";
    });
    html += "</tbody></table>";
    setSummaryModal("Entry Wise Prints", employee || "", html);
    setTimeout(function () {
      var modalContent = el("pp-summary-content");
      if (!modalContent) return;
      modalContent.querySelectorAll(".pp-salary-entry-print").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var mode = String(btn.getAttribute("data-mode") || "detail");
          var emp = String(btn.getAttribute("data-employee") || "");
          var entry = String(btn.getAttribute("data-entry") || "");
          showSalarySlipPrint(emp, { mode: mode, entry: entry });
        });
      });
    }, 0);
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
      return "No unbooked salary rows found for current filters. Change date/filter or use Salary Status tab.";
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
  function setActionIcon(kind, glyph) {
    var icon = el("pp-action-icon");
    if (!icon) return;
    icon.className = "pp-action-icon " + (kind === "success" ? "pp-action-icon-success" : (kind === "error" ? "pp-action-icon-error" : "pp-action-icon-info"));
    icon.textContent = glyph || (kind === "success" ? "✓" : (kind === "error" ? "!" : "i"));
  }
  function showActionModal(options) {
    var modal = el("pp-action-modal");
    if (!modal) return;
    var opts = options || {};
    if (el("pp-action-title")) el("pp-action-title").textContent = String(opts.title || "Action");
    if (el("pp-action-sub")) el("pp-action-sub").textContent = String(opts.sub || "Please confirm.");
    if (el("pp-action-message")) el("pp-action-message").textContent = String(opts.message || "");
    if (el("pp-action-meta")) el("pp-action-meta").textContent = String(opts.meta || "");
    setActionIcon(opts.kind || "info", opts.glyph || "");
    var buttons = el("pp-action-buttons");
    if (buttons) {
      buttons.innerHTML = "";
      (opts.buttons || []).forEach(function (btn) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "btn " + String(btn.className || "btn-default");
        b.textContent = String(btn.label || "OK");
        b.addEventListener("click", function () {
          if (typeof btn.onClick === "function") btn.onClick();
        });
        buttons.appendChild(b);
      });
    }
    modal.style.display = "flex";
  }
  function hideActionModal() {
    var modal = el("pp-action-modal");
    if (modal) modal.style.display = "none";
  }
  function confirmActionModal(title, message, okLabel) {
    return new Promise(function (resolve) {
      showActionModal({
        kind: "info",
        title: title || "Confirm Action",
        sub: "site1.frappe.io",
        message: message || "Please confirm.",
        buttons: [
          { label: "Cancel", className: "btn-default", onClick: function () { hideActionModal(); resolve(false); } },
          { label: okLabel || "OK", className: "btn-primary", onClick: function () { hideActionModal(); resolve(true); } }
        ]
      });
    });
  }
  function notifyActionResult(kind, title, message, jvNo) {
    showActionModal({
      kind: kind === "error" ? "error" : "success",
      title: title || (kind === "error" ? "Failed" : "Success"),
      sub: "site1.frappe.io",
      message: message || "",
      meta: jvNo ? ("JV No: " + jvNo) : "",
      buttons: [{ label: "Close", className: "btn-default", onClick: hideActionModal }]
    });
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
    try {
      window.localStorage.setItem("pp_last_from_date", fromVal || "");
      window.localStorage.setItem("pp_last_to_date", toVal || "");
    } catch (e) {}
    return {
      from_date: fromVal,
      to_date: toVal,
      employee: el("pp-employee").value || "",
      item_group: el("pp-item-group") ? (el("pp-item-group").value || "") : "",
      product: el("pp-product").value || "",
      process_type: el("pp-process-type").value || "",
      booking_status: el("pp-booking-status") ? (el("pp-booking-status").value || "") : "",
      payment_status: el("pp-payment-status") ? (el("pp-payment-status").value || "") : "",
      po_number: el("pp-po-number") ? (el("pp-po-number").value || "") : "",
      entry_no: el("pp-entry-no") ? (el("pp-entry-no").value || "") : "",
      max_rows: "0",
      max_days: "0"
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
    var poRows = Object.keys(poMap).sort().reverse().map(function (v) { return { value: v, label: v }; });
    var entryRows = Object.keys(entryMap).sort().reverse().map(function (v) { return { value: v, label: v }; });
    setOptions(poSelect, poRows, "value", "label", "All");
    setOptions(entrySelect, entryRows, "value", "label", "All");
    if (currentPo && poMap[currentPo]) poSelect.value = currentPo;
    if (currentEntry && entryMap[currentEntry]) entrySelect.value = currentEntry;
  }

  function getRowsByHeaderFilters(rows, options) {
    var opts = options || {};
    var po = el("pp-po-number") ? String(el("pp-po-number").value || "").trim() : "";
    var entry = String(state.forcedEntryNo || "").trim();
    var booking = el("pp-booking-status") ? String(el("pp-booking-status").value || "").trim() : "";
    var payment = el("pp-payment-status") ? String(el("pp-payment-status").value || "").trim() : "";
    var from = String((el("pp-from-date") && el("pp-from-date").value) || "").trim();
    var to = String((el("pp-to-date") && el("pp-to-date").value) || "").trim();
    if (!entry && el("pp-entry-no")) entry = String(el("pp-entry-no").value || "").trim();
    if (opts.ignore_entry_filter) entry = "";
    if (opts.ignore_po_filter) po = "";
    if (opts.ignore_date_filter) {
      from = "";
      to = "";
    }
    if (opts.ignore_status_filter) {
      booking = "";
      payment = "";
    }
    return (rows || []).filter(function (r) {
      var rowFrom = String((r && r.from_date) || "").trim();
      var rowTo = String((r && r.to_date) || "").trim();
      if (from && rowFrom && rowFrom < from) return false;
      if (to && rowTo && rowTo > to) return false;
      if (po && String(r.po_number || "") !== po) return false;
      if (entry && String(r.per_piece_salary || "") !== entry) return false;
      if (booking && String(r.booking_status || "").trim() !== booking) return false;
      if (payment && String(r.payment_status || "").trim() !== payment) return false;
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

  function filterRowsByDateRange(rows, fromDate, toDate) {
    var from = String(fromDate || "").trim();
    var to = String(toDate || "").trim();
    if (!from && !to) return (rows || []).slice();
    return (rows || []).filter(function (r) {
      var rowFrom = String((r && r.from_date) || "").trim();
      var rowTo = String((r && r.to_date) || "").trim();
      if (!rowFrom) rowFrom = rowTo;
      if (!rowTo) rowTo = rowFrom;
      if (from && rowTo && rowTo < from) return false;
      if (to && rowFrom && rowFrom > to) return false;
      return true;
    });
  }

  function getWorkflowHistoryRange(tabName) {
    var key = String(tabName || "").trim();
    var src = (state.workflowHistoryDate && state.workflowHistoryDate[key]) || {};
    return { from: String(src.from || "").trim(), to: String(src.to || "").trim() };
  }

  function setWorkflowHistoryRange(tabName, fromDate, toDate) {
    var key = String(tabName || "").trim();
    if (!state.workflowHistoryDate[key]) state.workflowHistoryDate[key] = { from: "", to: "" };
    state.workflowHistoryDate[key].from = String(fromDate || "").trim();
    state.workflowHistoryDate[key].to = String(toDate || "").trim();
  }

  function getWorkflowStatusFilter(tabName) {
    var key = String(tabName || "").trim();
    var src = (state.workflowStatusFilter && state.workflowStatusFilter[key]) || {};
    return {
      booking: String(src.booking || "").trim(),
      payment: String(src.payment || "").trim()
    };
  }

  function setWorkflowStatusFilter(tabName, bookingStatus, paymentStatus) {
    var key = String(tabName || "").trim();
    if (!state.workflowStatusFilter[key]) state.workflowStatusFilter[key] = { booking: "", payment: "" };
    state.workflowStatusFilter[key].booking = String(bookingStatus || "").trim();
    state.workflowStatusFilter[key].payment = String(paymentStatus || "").trim();
  }

  function filterDocsByStatus(docs, bookingStatus, paymentStatus) {
    var b = String(bookingStatus || "").trim();
    var p = String(paymentStatus || "").trim();
    return (docs || []).filter(function (row) {
      if (b && String((row && row.booking_status) || "").trim() !== b) return false;
      if (p && String((row && row.payment_status) || "").trim() !== p) return false;
      return true;
    });
  }

  function loadAdvancesFromGL() {
    var args = getReportArgs();
    var toDate = args.to_date || ymd(new Date());
    var selectedEmployee = args.employee || "";
    var months = buildLast6Months(toDate);
    var monthMap = {};
    var empMap = {};
    months.forEach(function (m) { monthMap[m.key] = true; });
    var firstMonthDate = (months[0] && months[0].key ? months[0].key : toDate.slice(0, 7)) + "-01";

    function getAccountCandidates() {
      var p1 = callGetList("Account", ["name"], [["name", "like", "%Employee Advance%"]], 2000).catch(function () { return []; });
      var p2 = callGetList("Account", ["name"], [["account_name", "like", "%Employee Advance%"]], 2000).catch(function () { return []; });
      return Promise.all([p1, p2]).then(function (parts) {
        var map = {};
        (parts[0] || []).forEach(function (r) { if (r && r.name) map[r.name] = true; });
        (parts[1] || []).forEach(function (r) { if (r && r.name) map[r.name] = true; });
        return Object.keys(map);
      });
    }

    function buildAdvanceState(transactionRows, amountFn) {
      var advMap = {};
      (transactionRows || []).forEach(function (g) {
        var emp = String(g.employee || g.party || "").trim();
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
            advance_balance: 0
          };
        }

        var postDate = String(g.posting_date || "").slice(0, 10);
        if (!postDate) return;
        var amount = num(amountFn(g));

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
    }

    return Promise.all([
      callGetList("Employee", ["name", "employee_name", "branch"], {}, 20000).catch(function () { return []; }),
      callGetList("Employee Advance", ["employee", "posting_date", "paid_amount", "claimed_amount", "return_amount"], selectedEmployee ? [["docstatus", "=", 1], ["posting_date", "<=", toDate], ["employee", "=", selectedEmployee]] : [["docstatus", "=", 1], ["posting_date", "<=", toDate]], 20000).catch(function () { return []; })
    ]).then(function (initialParts) {
      var empRows = initialParts[0] || [];
      var advanceDocs = initialParts[1] || [];
      empRows.forEach(function (e) {
        if (!e || !e.name) return;
        empMap[e.name] = {
          name1: e.employee_name || e.name,
          branch: e.branch || ""
        };
      });

      return getAccountCandidates().then(function (accounts) {
        if (!accounts || !accounts.length) {
          if (advanceDocs.length) {
            buildAdvanceState(advanceDocs, function (g) {
              return num(g.paid_amount) - num(g.claimed_amount) - num(g.return_amount);
            });
            return;
          }
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

        return callGetList("GL Entry", ["party", "posting_date", "debit", "credit"], glFilters, 20000).then(function (glRows) {
          if (glRows && glRows.length) {
            buildAdvanceState(glRows || [], function (g) {
              return num(g.debit) - num(g.credit);
            });
            return;
          }
          if (advanceDocs.length) {
            buildAdvanceState(advanceDocs, function (g) {
              return num(g.paid_amount) - num(g.claimed_amount) - num(g.return_amount);
            });
            return;
          }
          state.advanceRows = [];
          state.advanceMonths = months;
          state.advanceBalances = {};
        });
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

  function loadAllRowsForRecentDocs() {
    return callApi("get_per_piece_salary_report", {
      from_date: "2000-01-01",
      to_date: "2099-12-31"
    }).then(function (msg) {
      state.entryMeta.recentRows = (msg && msg.data) || [];
      applyReportRateProcessFix(state.entryMeta.recentRows);
      normalizeReportStatusValues(state.entryMeta.recentRows);
    }).catch(function () {
      state.entryMeta.recentRows = (state.rows || []).slice();
      applyReportRateProcessFix(state.entryMeta.recentRows);
      normalizeReportStatusValues(state.entryMeta.recentRows);
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

    var employeeOrdered = [];
    (state.entryMeta.masterEmployeeOptions || []).forEach(function (opt) {
      var emp = String((opt && opt.value) || "").trim();
      if (emp && employeeSet[emp]) employeeOrdered.push(emp);
    });
    Object.keys(employeeSet).sort().forEach(function (emp) {
      if (employeeOrdered.indexOf(emp) < 0) employeeOrdered.push(emp);
    });

    var itemGroupOrdered = [];
    (state.entryMeta.masterItemGroupOptions || []).forEach(function (opt) {
      var group = String((opt && opt.value) || "").trim();
      if (group && itemGroupSet[group]) itemGroupOrdered.push(group);
    });
    Object.keys(itemGroupSet).sort().forEach(function (group) {
      if (itemGroupOrdered.indexOf(group) < 0) itemGroupOrdered.push(group);
    });

    var productOrdered = [];
    (state.entryMeta.masterProcessRows || []).forEach(function (item) {
      var product = String((item && item.item) || "").trim();
      if (product && productSet[product] && productOrdered.indexOf(product) < 0) productOrdered.push(product);
    });
    Object.keys(productSet).sort().forEach(function (product) {
      if (productOrdered.indexOf(product) < 0) productOrdered.push(product);
    });

    var processOrdered = [];
    (state.entryMeta.masterProcessRows || []).forEach(function (item) {
      var process = String((item && item.process_type) || "").trim();
      if (process && processSet[process] && processOrdered.indexOf(process) < 0) processOrdered.push(process);
    });
    Object.keys(processSet).sort().forEach(function (process) {
      if (processOrdered.indexOf(process) < 0) processOrdered.push(process);
    });

    state.entryMeta.employeeOptions = employeeOrdered.map(function (emp) {
      var label = employeeNameMap[emp] ? (employeeNameMap[emp] + " (" + emp + ")") : emp;
      return { value: emp, label: label };
    });
    state.entryMeta.itemGroupOptions = itemGroupOrdered.map(function (group) {
      return { value: group, label: group };
    });
    state.entryMeta.productOptions = productOrdered.map(function (p) {
      return { value: p, label: p };
    });
    state.entryMeta.processOptions = processOrdered.map(function (p) {
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
      if (!jvPosted) {
        isBooked = false;
        bookedVal = 0;
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
    var map = {};
    (rows || []).forEach(function (r) {
      var employee = String(r.employee || "").trim();
      var name1 = String(r.name1 || "").trim();
      var key = employee + "||" + name1;
      if (!map[key]) {
        map[key] = {
          employee: employee,
          name1: name1,
          qty: 0,
          amount: 0,
          rate: 0,
          source_count: 0,
          source_entries: []
        };
      }
      map[key].qty += num(r.qty);
      map[key].amount += num(r.amount);
      map[key].source_count += 1;
      map[key].source_entries.push({
        per_piece_salary: r.per_piece_salary || "",
        po_number: r.po_number || "",
        sales_order: r.sales_order || "",
        qty: num(r.qty),
        amount: num(r.amount)
      });
    });
    return Object.keys(map).sort().map(function (key) {
      var row = map[key];
      row.rate = avgRate(row.qty, row.amount);
      return row;
    });
  }

  function buildEmployeeSummaryReportRows(rows) {
    var map = {};
    function clean(v) {
      var out = Math.round(num(v) * 100) / 100;
      return Math.abs(out) < 0.005 ? 0 : out;
    }
    (rows || []).forEach(function (r) {
      var employee = String(r.employee || "").trim();
      var name1 = String(r.name1 || "").trim();
      var key = employee + "||" + name1;
      if (!map[key]) {
        map[key] = {
          employee: employee,
          name1: name1,
          qty: 0,
          amount: 0,
          rate: 0,
          booked_amount: 0,
          unbooked_amount: 0,
          paid_amount: 0,
          unpaid_amount: 0,
          _booked_count: 0,
          _paid_count: 0,
          _unpaid_count: 0,
          _row_count: 0,
          source_count: 0,
          source_entries: []
        };
      }
      var item = map[key];
      item.qty += num(r.qty);
      item.amount += num(r.amount);
      item._row_count += 1;

      var amount = num(r.amount);
      var bookingStatus = String(r.booking_status || "");
      var jvPosted = !!((r.jv_entry_no || "") && String(r.jv_status || "") === "Posted");
      var isBooked = bookingStatus === "Booked" || jvPosted;
      var bookedVal = isBooked ? amount : 0;
      if (!jvPosted) {
        isBooked = false;
        bookedVal = 0;
      }
      var paidVal = num(r.paid_amount);
      if (paidVal < 0) paidVal = 0;
      if (paidVal > bookedVal) paidVal = bookedVal;
      var unpaidVal = num(r.unpaid_amount);
      if (unpaidVal <= 0 || unpaidVal > bookedVal) {
        unpaidVal = Math.max(bookedVal - paidVal, 0);
      }

      item.booked_amount += clean(bookedVal);
      item.unbooked_amount += clean(Math.max(amount - bookedVal, 0));
      item.paid_amount += clean(paidVal);
      item.unpaid_amount += clean(unpaidVal);
      if (bookedVal > 0) item._booked_count += 1;
      if (String(r.payment_status || "") === "Paid") item._paid_count += 1;
      else item._unpaid_count += 1;

      item.source_count += 1;
      item.source_entries.push({
        per_piece_salary: r.per_piece_salary || "",
        from_date: r.from_date || "",
        to_date: r.to_date || "",
        po_number: r.po_number || "",
        sales_order: r.sales_order || "",
        booking_status: r.booking_status || (isBooked ? "Booked" : "UnBooked"),
        payment_status: r.payment_status || "Unpaid",
        booked_amount: clean(bookedVal),
        unbooked_amount: clean(Math.max(amount - bookedVal, 0)),
        paid_amount: clean(paidVal),
        unpaid_amount: clean(unpaidVal),
        qty: num(r.qty),
        amount: num(r.amount)
      });
    });
    return Object.keys(map).sort().map(function (key) {
      var item = map[key];
      item.rate = avgRate(item.qty, item.amount);
      if (item._booked_count === item._row_count) item.booking_status = "Booked";
      else if (item._booked_count > 0) item.booking_status = "Partly Booked";
      else item.booking_status = "UnBooked";
      if (item._paid_count === item._row_count) item.payment_status = "Paid";
      else if (item._paid_count > 0 && item._unpaid_count > 0) item.payment_status = "Partly Paid";
      else item.payment_status = "Unpaid";
      return item;
    });
  }

  function buildEmployeeItemWiseReportRows(rows) {
    var byEmployee = {};
    var employeeOrder = [];
    (rows || []).forEach(function (r) {
      var emp = String(r.employee || "").trim();
      var name = String(r.name1 || "").trim() || emp || "Unknown Employee";
      var key = emp + "||" + name;
      if (!byEmployee[key]) {
        byEmployee[key] = {
          employee: emp,
          name1: name,
          details: [],
          subtotal: { qty: 0, amount: 0 }
        };
        employeeOrder.push(key);
      }
      byEmployee[key].details.push({
        per_piece_salary: r.per_piece_salary || "",
        po_number: r.po_number || "",
        product: r.product || "",
        process_type: r.process_type || "",
        process_size: r.process_size || "No Size",
        qty: num(r.qty),
        rate: num(r.rate),
        amount: num(r.amount),
        booking_status: r.booking_status || "",
        payment_status: r.payment_status || "",
        jv_entry_no: r.jv_entry_no || "",
        payment_jv_no: r.payment_jv_no || ""
      });
      byEmployee[key].subtotal.qty += num(r.qty);
      byEmployee[key].subtotal.amount += num(r.amount);
    });

    employeeOrder.sort(function (a, b) {
      var an = String((byEmployee[a] && byEmployee[a].name1) || a);
      var bn = String((byEmployee[b] && byEmployee[b].name1) || b);
      return an.localeCompare(bn);
    });

    var out = [];
    employeeOrder.forEach(function (key) {
      var group = byEmployee[key];
      out.push({
        _group_header: 1,
        _group_label: "Employee: " + (group.name1 || group.employee || "Unknown") + (group.employee ? (" (" + group.employee + ")") : "")
      });
      (group.details || []).sort(function (a, b) {
        var ce = String(b.per_piece_salary || "").localeCompare(String(a.per_piece_salary || ""));
        if (ce !== 0) return ce;
        var pi = String(a.product || "").localeCompare(String(b.product || ""));
        if (pi !== 0) return pi;
        return compareByProcessSequence(a, b, a.product || "", b.product || "");
      }).forEach(function (d) {
        out.push(d);
      });
      out.push({
        _is_total: 1,
        per_piece_salary: "Employee Sub Total",
        qty: group.subtotal.qty,
        rate: avgRate(group.subtotal.qty, group.subtotal.amount),
        amount: group.subtotal.amount
      });
    });
    return out;
  }

  function normalizeBookedAmounts(row) {
    var amount = num(row && row.amount);
    var bookedVal = num(row && row.booked_amount);
    if (bookedVal < 0) bookedVal = 0;
    if (bookedVal > amount) bookedVal = amount;
    var paidVal = num(row && row.paid_amount);
    if (paidVal < 0) paidVal = 0;
    if (paidVal > bookedVal) paidVal = bookedVal;
    var unpaidVal = num(row && row.unpaid_amount);
    if (unpaidVal < 0 || unpaidVal > bookedVal) unpaidVal = Math.max(bookedVal - paidVal, 0);
    var unbookedVal = Math.max(amount - bookedVal, 0);
    return {
      amount: amount,
      booked_amount: bookedVal,
      paid_amount: paidVal,
      unpaid_amount: unpaidVal,
      unbooked_amount: unbookedVal
    };
  }

  function buildProductSummaryDetailRows(rows) {
    var byProduct = {};
    var productOrder = [];
    (rows || []).forEach(function (r) {
      var product = String(r.product || "").trim() || "No Product";
      if (!byProduct[product]) {
        byProduct[product] = {
          details: [],
          subtotal: { qty: 0, amount: 0, unbooked_amount: 0, booked_amount: 0, paid_amount: 0, unpaid_amount: 0 }
        };
        productOrder.push(product);
      }
      var amt = normalizeBookedAmounts(r);
      byProduct[product].details.push({
        per_piece_salary: r.per_piece_salary || "",
        product: product,
        process_type: r.process_type || "",
        process_size: r.process_size || "No Size",
        qty: num(r.qty),
        rate: num(r.rate),
        amount: amt.amount,
        unbooked_amount: amt.unbooked_amount,
        booked_amount: amt.booked_amount,
        paid_amount: amt.paid_amount,
        unpaid_amount: amt.unpaid_amount,
        booking_status: r.booking_status || "",
        payment_status: r.payment_status || ""
      });
      byProduct[product].subtotal.qty += num(r.qty);
      byProduct[product].subtotal.amount += amt.amount;
      byProduct[product].subtotal.unbooked_amount += amt.unbooked_amount;
      byProduct[product].subtotal.booked_amount += amt.booked_amount;
      byProduct[product].subtotal.paid_amount += amt.paid_amount;
      byProduct[product].subtotal.unpaid_amount += amt.unpaid_amount;
    });

    productOrder.sort();
    var out = [];
    productOrder.forEach(function (product) {
      var group = byProduct[product];
      out.push({ _group_header: 1, _group_label: "Product: " + product });
      (group.details || []).sort(function (a, b) {
        var ce = String(b.per_piece_salary || "").localeCompare(String(a.per_piece_salary || ""));
        if (ce !== 0) return ce;
        return compareByProcessSequence(a, b, a.product || "", b.product || "");
      }).forEach(function (d) { out.push(d); });
      out.push({
        _is_total: 1,
        per_piece_salary: "Product Sub Total",
        product: product,
        qty: group.subtotal.qty,
        rate: avgRate(group.subtotal.qty, group.subtotal.amount),
        amount: group.subtotal.amount,
        unbooked_amount: group.subtotal.unbooked_amount,
        booked_amount: group.subtotal.booked_amount,
        paid_amount: group.subtotal.paid_amount,
        unpaid_amount: group.subtotal.unpaid_amount
      });
    });
    return out;
  }

  function buildProcessSummaryRows(rows) {
    var byProcess = {};
    var processOrder = [];
    (rows || []).forEach(function (r) {
      var processType = String(r.process_type || "").trim() || "No Process";
      if (!byProcess[processType]) {
        byProcess[processType] = {
          details: [],
          subtotal: { qty: 0, amount: 0, unbooked_amount: 0, booked_amount: 0, paid_amount: 0, unpaid_amount: 0 }
        };
        processOrder.push(processType);
      }
      var amt = normalizeBookedAmounts(r);
      byProcess[processType].details.push({
        per_piece_salary: r.per_piece_salary || "",
        process_type: processType,
        process_size: r.process_size || "No Size",
        qty: num(r.qty),
        rate: num(r.rate),
        amount: amt.amount,
        unbooked_amount: amt.unbooked_amount,
        booked_amount: amt.booked_amount,
        paid_amount: amt.paid_amount,
        unpaid_amount: amt.unpaid_amount,
        booking_status: r.booking_status || "",
        payment_status: r.payment_status || ""
      });
      byProcess[processType].subtotal.qty += num(r.qty);
      byProcess[processType].subtotal.amount += amt.amount;
      byProcess[processType].subtotal.unbooked_amount += amt.unbooked_amount;
      byProcess[processType].subtotal.booked_amount += amt.booked_amount;
      byProcess[processType].subtotal.paid_amount += amt.paid_amount;
      byProcess[processType].subtotal.unpaid_amount += amt.unpaid_amount;
    });

    processOrder.sort();
    var out = [];
    processOrder.forEach(function (processType) {
      var group = byProcess[processType];
      out.push({ _group_header: 1, _group_label: "Process: " + processType });
      (group.details || []).sort(function (a, b) {
        var ce = String(b.per_piece_salary || "").localeCompare(String(a.per_piece_salary || ""));
        if (ce !== 0) return ce;
        return compareByProcessSequence(a, b, "", "");
      }).forEach(function (d) { out.push(d); });
      out.push({
        _is_total: 1,
        per_piece_salary: "Process Sub Total",
        process_type: processType,
        qty: group.subtotal.qty,
        rate: avgRate(group.subtotal.qty, group.subtotal.amount),
        amount: group.subtotal.amount,
        unbooked_amount: group.subtotal.unbooked_amount,
        booked_amount: group.subtotal.booked_amount,
        paid_amount: group.subtotal.paid_amount,
        unpaid_amount: group.subtotal.unpaid_amount
      });
    });
    return out;
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
      if (!jvPosted) {
        isBooked = false;
        bookedVal = 0;
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

    return Object.keys(map).sort().reverse().map(function (k) {
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
    var range = getWorkflowHistoryRange("salary_creation");
    return filterRowsBySelectedEntries(filterRowsByDateRange(
      getRowsByHeaderFilters(state.rows || [], { ignore_date_filter: true }),
      range.from,
      range.to
    ), "salary_creation").filter(function (r) {
      var status = r && r.jv_status ? String(r.jv_status) : "Pending";
      var hasJV = !!String((r && r.jv_entry_no) || "").trim();
      return !hasJV && status !== "Posted";
    });
  }

  function getBookedRows() {
    var range = getWorkflowHistoryRange("payment_manage");
    return filterRowsBySelectedEntries(filterRowsByDateRange(
      getRowsByHeaderFilters(state.rows || [], { ignore_date_filter: true }),
      range.from,
      range.to
    ), "payment_manage").filter(function (r) {
      var status = r && r.jv_status ? String(r.jv_status) : "Pending";
      var hasJV = !!String((r && r.jv_entry_no) || "").trim();
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

  function getUnbookedEntryOptions() {
    var map = {};
    var range = getWorkflowHistoryRange("salary_creation");
    filterRowsByDateRange(
      getRowsByHeaderFilters(state.rows || [], { ignore_entry_filter: true, ignore_date_filter: true }),
      range.from,
      range.to
    ).forEach(function (r) {
      var entry = String((r && r.per_piece_salary) || "").trim();
      if (!entry) return;
      var status = String((r && r.jv_status) || "");
      var hasJV = !!String((r && r.jv_entry_no) || "").trim();
      if (!hasJV || status !== "Posted") map[entry] = 1;
    });
    return Object.keys(map).sort(compareEntryNoDesc).map(function (name) {
      return { value: name, label: name };
    });
  }

  function getUnpaidEntryOptions() {
    var map = {};
    var range = getWorkflowHistoryRange("payment_manage");
    filterRowsByDateRange(
      getRowsByHeaderFilters(state.rows || [], { ignore_entry_filter: true, ignore_date_filter: true }),
      range.from,
      range.to
    ).forEach(function (r) {
      var entry = String((r && r.per_piece_salary) || "").trim();
      if (!entry) return;
      var unpaid = num((r && r.unpaid_amount) || 0);
      var payStatus = String((r && r.payment_status) || "Unpaid");
      var hasBooked = !!String((r && r.jv_entry_no) || "").trim() && String((r && r.jv_status) || "") === "Posted";
      if (hasBooked && (unpaid > 0.0001 || payStatus === "Unpaid" || payStatus === "Partly Paid")) map[entry] = 1;
    });
    return Object.keys(map).sort(compareEntryNoDesc).map(function (name) {
      return { value: name, label: name };
    });
  }

  function getEntrySummary(entryNo) {
    var entry = String(entryNo || "").trim();
    if (!entry) return null;
    var src = getRowsByHeaderFilters(state.rows || []).filter(function (r) {
      return String((r && r.per_piece_salary) || "").trim() === entry;
    });
    if (!src.length) return null;
    var rowCount = 0, bookedCount = 0, paidCount = 0, unpaidCount = 0;
    var amount = 0, booked = 0, paid = 0, unpaid = 0, unbooked = 0;
    var fromDate = "", toDate = "";
    src.forEach(function (r) {
      rowCount += 1;
      var a = num(r.amount);
      var isBooked = String(r.booking_status || "") === "Booked" || (!!String(r.jv_entry_no || "").trim() && String(r.jv_status || "") === "Posted");
      var b = num(r.booked_amount);
      if (b < 0) b = 0;
      if (!isBooked) b = 0;
      if (isBooked && b <= 0) b = a;
      var p = num(r.paid_amount);
      if (p < 0) p = 0;
      if (p > b) p = b;
      var u = num(r.unpaid_amount);
      if (u < 0 || u > b) u = Math.max(b - p, 0);
      amount += a;
      booked += b;
      paid += p;
      unpaid += u;
      unbooked += isBooked ? 0 : Math.max(a - b, 0);
      if (isBooked) bookedCount += 1;
      if (u <= 0.005 && b > 0) paidCount += 1;
      else unpaidCount += 1;
      var f = String(r.from_date || "").trim();
      var t = String(r.to_date || "").trim();
      if (f && (!fromDate || f < fromDate)) fromDate = f;
      if (t && (!toDate || t > toDate)) toDate = t;
    });
    var bookingStatus = bookedCount === rowCount ? "Booked" : (bookedCount > 0 ? "Partly Booked" : "UnBooked");
    var paymentStatus = booked <= 0 ? "Unpaid" : (unpaid <= 0.005 ? "Paid" : (paid > 0.005 ? "Partly Paid" : "Unpaid"));
    return {
      entry_no: entry,
      from_date: fromDate,
      to_date: toDate,
      amount: amount,
      booked_amount: booked,
      unbooked_amount: unbooked,
      paid_amount: paid,
      unpaid_amount: unpaid,
      booking_status: bookingStatus,
      payment_status: paymentStatus
    };
  }

  function refreshWorkflowEntrySelectors() {
    var jvSelect = el("pp-jv-entry-filter");
    var paySelect = el("pp-pay-entry-filter");
    var currentForced = String(state.forcedEntryNo || "").trim();
    if (jvSelect) {
      var rows = getUnbookedEntryOptions();
      var current = String(jvSelect.value || "");
      setOptions(jvSelect, rows, "value", "label", "All Unbooked Entries");
      if (currentForced && rows.some(function (r) { return r.value === currentForced; })) jvSelect.value = currentForced;
      else if (current && rows.some(function (r) { return r.value === current; })) jvSelect.value = current;
    }
    if (paySelect) {
      var rows2 = getUnpaidEntryOptions();
      var current2 = String(paySelect.value || "");
      setOptions(paySelect, rows2, "value", "label", "All Unpaid Entries");
      if (currentForced && rows2.some(function (r) { return r.value === currentForced; })) paySelect.value = currentForced;
      else if (current2 && rows2.some(function (r) { return r.value === current2; })) paySelect.value = current2;
    }
    var jvMeta = el("pp-jv-entry-meta");
    var jvEntry = jvSelect ? String(jvSelect.value || "").trim() : "";
    if (jvMeta) {
      if (!jvEntry) jvMeta.innerHTML = "Booking Status: " + statusBadgeHtml("Mixed") + " | Payment Status: " + statusBadgeHtml("Mixed");
      else {
        var s = getEntrySummary(jvEntry);
        if (!s) jvMeta.textContent = "";
        else jvMeta.innerHTML = "Entry: " + esc(jvEntry) + " | Date: " + esc((s.from_date || "-") + " to " + (s.to_date || "-"))
          + " | Booking: " + statusBadgeHtml(s.booking_status || "")
          + " | Payment: " + statusBadgeHtml(s.payment_status || "");
      }
    }
    var payMeta = el("pp-pay-entry-meta");
    var payEntry = paySelect ? String(paySelect.value || "").trim() : "";
    if (payMeta) {
      if (!payEntry) payMeta.innerHTML = "Booking Status: " + statusBadgeHtml("Mixed") + " | Payment Status: " + statusBadgeHtml("Mixed");
      else {
        var ps = getEntrySummary(payEntry);
        if (!ps) payMeta.textContent = "";
        else payMeta.innerHTML = "Entry: " + esc(payEntry) + " | Date: " + esc((ps.from_date || "-") + " to " + (ps.to_date || "-"))
          + " | Booking: " + statusBadgeHtml(ps.booking_status || "")
          + " | Payment: " + statusBadgeHtml(ps.payment_status || "");
      }
    }
  }

  function resetEntryFiltersToAll() {
    state.forcedEntryNo = "";
    if (el("pp-entry-no")) el("pp-entry-no").value = "";
    if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = "";
    if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = "";
    if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = "";
    if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = "";
  }

  function parseEntryNoList(text) {
    var seen = {};
    var out = [];
    String(text || "").split(",").forEach(function (part) {
      var v = String(part || "").trim();
      if (!v || seen[v]) return;
      seen[v] = 1;
      out.push(v);
    });
    return out;
  }

  function getSelectedEntryNosForTab(tabName) {
    var raw = "";
    if (tabName === "salary_creation") raw = (el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || "";
    else if (tabName === "payment_manage") raw = (el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || "";
    var list = parseEntryNoList(raw);
    if (!list.length && state.forcedEntryNo) list = [String(state.forcedEntryNo).trim()];
    return list;
  }

  function filterRowsBySelectedEntries(rows, tabName) {
    var list = getSelectedEntryNosForTab(tabName);
    if (!list.length) return (rows || []).slice();
    var set = {};
    list.forEach(function (name) { set[String(name || "").trim()] = 1; });
    return (rows || []).filter(function (r) {
      var entry = String((r && r.per_piece_salary) || "").trim();
      return !!set[entry];
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
      source_count: num(summaryRow.source_count),
      source_entries: (summaryRow.source_entries || []).slice(),
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
      var rowClass = "";
      if (r && r._group_header) rowClass = " class='pp-group-head'";
      else if (ptype === "Subtotal" || ptype === "Year" || !!r._is_total) rowClass = " class='pp-year-total'";
      html += "<tr" + rowClass + ">";
      columns.forEach(function (c) {
        if (r && r._group_header) {
          if (c === columns[0]) html += "<td>" + esc(r._group_label || "") + "</td>";
          else html += "<td></td>";
          return;
        }
        var val = r[c.fieldname];
        if ((c.fieldname === "jv_entry_no" || c.fieldname === "payment_jv_no") && val) {
          html += "<td><a target='_blank' href='/app/journal-entry/" + encodeURIComponent(val) + "'>" + esc(val) + "</a></td>";
        } else if (c.po_action && r.po_number) {
          var poBtnClass = "btn-primary";
          if (String(c.po_action || "") === "view") poBtnClass = "btn-info";
          html += "<td><button type='button' class='btn btn-xs " + poBtnClass + " pp-po-action' data-action='" + esc(c.po_action) + "' data-po='" + encodeURIComponent(String(r.po_number || "")) + "'>" + esc(c.label) + "</button></td>";
        } else if (c.po_summary_link && val) {
          html += "<td><button type='button' class='btn btn-xs btn-default pp-po-summary' style='font-weight:700;' data-po='" + encodeURIComponent(String(val)) + "'>" + esc(val) + "</button></td>";
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
    wrap.querySelectorAll(".pp-po-summary").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var poNumber = decodeURIComponent(btn.getAttribute("data-po") || "");
        showPOSummary(poNumber);
      });
    });
    wrap.querySelectorAll(".pp-po-action").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var poNumber = decodeURIComponent(btn.getAttribute("data-po") || "");
        var action = btn.getAttribute("data-action") || "view";
        showPOSummary(poNumber, action);
      });
    });
  }

  function renderPoDetailPrintTab(rows) {
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    var detailRows = rows || [];
    var byProduct = {};
    detailRows.forEach(function (r) {
      var product = String((r && r.product) || "").trim() || "(Blank)";
      if (!byProduct[product]) byProduct[product] = [];
      byProduct[product].push(r);
    });
    var grandQty = 0;
    var grandAmount = 0;
    var html = "<table class='pp-table'><thead><tr><th>PO Number</th><th>Item</th><th>Process</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Grand Total</th></tr></thead><tbody>";
    Object.keys(byProduct).sort().forEach(function (product) {
      var list = byProduct[product] || [];
      var subQty = 0;
      var subAmount = 0;
      html += "<tr class='pp-group-head'><td colspan='8'>" + esc(product) + "</td></tr>";
      list.sort(function (a, b) {
        var poCmp = String(a.po_number || "").localeCompare(String(b.po_number || ""));
        if (poCmp !== 0) return poCmp;
        return String(a.process_type || "").localeCompare(String(b.process_type || ""));
      }).forEach(function (r) {
        var q = num(r.qty);
        var a = num(r.amount);
        subQty += q;
        subAmount += a;
        grandQty += q;
        grandAmount += a;
        html += "<tr><td>" + esc(r.po_number || "") + "</td><td>" + esc(r.product || "") + "</td><td>" + esc(r.process_type || "") + "</td><td>" + esc(r.process_size || "No Size") + "</td><td class='num'>" + esc(fmt(q)) + "</td><td class='num'>" + esc(fmt(num(r.rate))) + "</td><td class='num pp-amt-col'>" + esc(fmt(a)) + "</td><td></td></tr>";
      });
      html += "<tr class='pp-year-total'><td></td><td>Sub Total</td><td></td><td></td><td class='num'>" + esc(fmt(subQty)) + "</td><td class='num'>" + esc(fmt(avgRate(subQty, subAmount))) + "</td><td class='num pp-amt-col'>" + esc(fmt(subAmount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(subAmount)) + "</td></tr>";
    });
    html += "<tr class='pp-year-total'><td></td><td>Grand Total</td><td></td><td></td><td class='num'>" + esc(fmt(grandQty)) + "</td><td class='num'>" + esc(fmt(avgRate(grandQty, grandAmount))) + "</td><td class='num pp-amt-col'>" + esc(fmt(grandAmount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(grandAmount)) + "</td></tr>";
    html += "</tbody></table>";

    var byEmployee = {};
    detailRows.forEach(function (r) {
      var emp = String((r && (r.name1 || r.employee)) || "").trim() || "(Blank)";
      if (!byEmployee[emp]) byEmployee[emp] = { employee: emp, qty: 0, amount: 0 };
      byEmployee[emp].qty += num(r.qty);
      byEmployee[emp].amount += num(r.amount);
    });
    html += "<div style='margin-top:10px;'><strong>Employee-wise Summary</strong></div>";
    html += "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
    Object.keys(byEmployee).sort().forEach(function (emp) {
      var row = byEmployee[emp];
      html += "<tr><td>" + esc(row.employee) + "</td><td class='num'>" + esc(fmt(row.qty)) + "</td><td class='num'>" + esc(fmt(avgRate(row.qty, row.amount))) + "</td><td class='num pp-amt-col'>" + esc(fmt(row.amount)) + "</td></tr>";
    });
    html += "<tr class='pp-year-total'><td>Total</td><td class='num'>" + esc(fmt(grandQty)) + "</td><td class='num'>" + esc(fmt(avgRate(grandQty, grandAmount))) + "</td><td class='num pp-amt-col'>" + esc(fmt(grandAmount)) + "</td></tr>";
    html += "</tbody></table>";
    wrap.innerHTML = html;
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
        + "<td><button type='button' class='btn btn-xs btn-default pp-salary-emp-detail' data-employee='" + esc(emp) + "'>" + esc(label) + "</button></td>"
        + "<td class='num'>" + esc(fmt(r.qty)) + "</td>"
        + "<td class='num'>" + esc(fmt(r.rate)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.advance_balance)) + "</td>"
        + "<td><input class='pp-adj-input' type='text' inputmode='decimal' autocomplete='off' data-employee='" + esc(emp) + "' data-field='advance_deduction' value='" + esc(whole(r.advance_deduction)) + "'></td>"
        + "<td><input class='pp-adj-input' type='text' inputmode='decimal' autocomplete='off' data-employee='" + esc(emp) + "' data-field='allowance' value='" + esc(whole(r.allowance)) + "'></td>"
        + "<td><input class='pp-adj-input' type='text' inputmode='decimal' autocomplete='off' data-employee='" + esc(emp) + "' data-field='other_deduction' value='" + esc(whole(r.other_deduction)) + "'></td>"
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

    wrap.querySelectorAll(".pp-salary-emp-detail").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showSalaryEmployeeDetail(btn.getAttribute("data-employee") || "");
      });
    });

    wrap.querySelectorAll(".pp-adj-input").forEach(function (input) {
      function onAdjustInput() {
        var emp = input.getAttribute("data-employee") || "";
        var field = input.getAttribute("data-field") || "";
        if (!state.adjustments[emp]) {
          state.adjustments[emp] = { advance_balance: 0, advance_deduction: 0, allowance: 0, other_deduction: 0 };
        }
        state.adjustments[emp][field] = parseDecimalInput(input.value);
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

  function renderEmployeeSummaryTable(rows) {
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    var showDetail = !!state.employeeSummaryDetail;
    var html = "<table class='pp-table'><thead><tr>"
      + "<th>Employee</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Booked</th><th>UnBooked</th><th>Paid</th><th>Unpaid</th><th>Booking Status</th><th>Payment Status</th><th>Action</th>"
      + "</tr></thead><tbody>";
    rows.forEach(function (r) {
      var canBookEmp = num(r.unbooked_amount) > 0;
      var canPayEmp = num(r.unpaid_amount) > 0;
      var empAction = "";
      if (canBookEmp) {
        empAction += "<button type='button' class='btn btn-xs btn-primary pp-go-book-emp' data-employee='" + esc(r.employee || "") + "'>Book</button> ";
      }
      if (canPayEmp) {
        empAction += "<button type='button' class='btn btn-xs btn-success pp-go-pay-emp' data-employee='" + esc(r.employee || "") + "'>Pay</button>";
      }
      if (!empAction) empAction = "<span style='color:#64748b;'>Done</span>";
      html += "<tr>"
        + "<td>" + esc(r.name1 || r.employee || "") + "</td>"
        + "<td class='num'>" + esc(fmt(r.qty)) + "</td>"
        + "<td class='num'>" + esc(fmt(r.rate)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.booked_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.unbooked_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.paid_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.unpaid_amount)) + "</td>"
        + "<td>" + statusBadgeHtml(r.booking_status || "") + "</td>"
        + "<td>" + statusBadgeHtml(r.payment_status || "") + "</td>"
        + "<td>" + empAction + "</td>"
        + "</tr>";
      if (showDetail && (r.source_entries || []).length) {
        var detailHtml = "<table class='pp-table' style='margin:4px 0 0 0;'><thead><tr><th>Per Piece Salary</th><th>From Date</th><th>To Date</th><th>PO Number</th><th>Sales Order</th><th>Qty</th><th>Amount</th><th>Booked</th><th>UnBooked</th><th>Paid</th><th>Unpaid</th><th>Booking</th><th>Payment</th><th>Action</th></tr></thead><tbody>";
        (r.source_entries || []).forEach(function (src) {
          var canBook = num(src.unbooked_amount) > 0;
          var canPay = num(src.unpaid_amount) > 0;
          var entryAction = "";
          if (canBook) {
            entryAction += "<button type='button' class='btn btn-xs btn-primary pp-go-book-entry' data-entry='" + encodeURIComponent(String(src.per_piece_salary || "")) + "' data-employee='" + encodeURIComponent(String(r.employee || "")) + "'>Book</button> ";
          }
          if (canPay) {
            entryAction += "<button type='button' class='btn btn-xs btn-success pp-go-pay-entry' data-entry='" + encodeURIComponent(String(src.per_piece_salary || "")) + "' data-employee='" + encodeURIComponent(String(r.employee || "")) + "' data-unpaid='" + esc(src.unpaid_amount) + "'>Pay</button>";
          }
          if (!entryAction) entryAction = "<span style='color:#64748b;'>Done</span>";
          detailHtml += "<tr><td>" + esc(src.per_piece_salary || "") + "</td><td>" + esc(src.from_date || "") + "</td><td>" + esc(src.to_date || "") + "</td><td>" + esc(src.po_number || "") + "</td><td>" + esc(src.sales_order || "") + "</td><td class='num'>" + esc(fmt(src.qty)) + "</td><td class='num pp-amt-col'>" + esc(fmt(src.amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(src.booked_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(src.unbooked_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(src.paid_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(src.unpaid_amount)) + "</td><td>" + statusBadgeHtml(src.booking_status || "") + "</td><td>" + statusBadgeHtml(src.payment_status || "") + "</td><td>" + entryAction + "</td></tr>";
        });
        detailHtml += "<tr class='pp-year-total'><td>Total Entries: " + esc(r.source_count || 0) + "</td><td></td><td></td><td></td><td></td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.booked_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.unbooked_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.paid_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.unpaid_amount)) + "</td><td></td><td></td><td></td></tr>";
        detailHtml += "</tbody></table>";
        html += "<tr class='pp-entry-detail-row'><td colspan='11'>" + detailHtml + "</td></tr>";
      }
    });
    var totals = { qty: 0, rate: 0, amount: 0, booked_amount: 0, unbooked_amount: 0, paid_amount: 0, unpaid_amount: 0 };
    (rows || []).forEach(function (r) {
      totals.qty += num(r.qty);
      totals.rate += num(r.rate);
      totals.amount += num(r.amount);
      totals.booked_amount += num(r.booked_amount);
      totals.unbooked_amount += num(r.unbooked_amount);
      totals.paid_amount += num(r.paid_amount);
      totals.unpaid_amount += num(r.unpaid_amount);
    });
    html += "<tr class='pp-year-total'><td>Total</td><td class='num'>" + esc(fmt(totals.qty)) + "</td><td class='num'>" + esc(fmt(totals.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.booked_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.unbooked_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.paid_amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.unpaid_amount)) + "</td><td></td><td></td><td></td></tr>";
    html += "</tbody></table>";
    wrap.innerHTML = html;

    function applyPaymentPrefill(employee, amount) {
      var emp = String(employee || "").trim();
      var target = Math.max(0, num(amount));
      if (!emp || target <= 0) return;
      var row = null;
      getPaymentActiveRows().forEach(function (r) {
        if (!row && String(r.employee || "") === emp) row = r;
      });
      if (!row) return;
      if (!state.paymentAdjustments[emp]) {
        state.paymentAdjustments[emp] = { payment_amount: 0, unpaid_amount: num(row.unpaid_amount) };
      }
      state.paymentAdjustments[emp].unpaid_amount = num(row.unpaid_amount);
      state.paymentAdjustments[emp].payment_amount = Math.min(target, Math.max(0, num(row.unpaid_amount)));
    }

    function focusWorkflow(tabName, employee, entryNo, targetPayAmount) {
      state.forcedEntryNo = entryNo ? String(entryNo).trim() : "";
      if (el("pp-entry-no")) {
        el("pp-entry-no").value = state.forcedEntryNo || "";
      }
      document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
      var targetBtn = document.querySelector(".pp-tab[data-tab='" + tabName + "']");
      if (targetBtn) targetBtn.classList.add("active");
      state.currentTab = tabName;
      setPageForCurrentTab(1);

      if (tabName === "salary_creation") {
        setWorkflowHistoryRange("salary_creation", "", "");
        var empMap = {};
        getAdjustedEmployeeRows().forEach(function (row) {
          var emp = row.employee || "";
          if (!emp) return;
          if (employee && emp !== employee) empMap[emp] = true;
        });
        state.excludedEmployees = empMap;
        if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo || "";
        if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = state.forcedEntryNo || "";
        setPageForCurrentTab(1);
        loadReport();
        return;
      }

      if (tabName === "payment_manage") {
        setWorkflowHistoryRange("payment_manage", "", "");
        var payMap = {};
        getPaymentActiveRows().forEach(function (row) {
          var emp = row.employee || "";
          if (!emp) return;
          if (employee && emp !== employee) payMap[emp] = true;
        });
        state.paymentExcludedEmployees = payMap;
        if (targetPayAmount && num(targetPayAmount) > 0) {
          applyPaymentPrefill(employee, targetPayAmount);
        }
        if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = state.forcedEntryNo || "";
        if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = state.forcedEntryNo || "";
        setPageForCurrentTab(1);
        loadReport();
        return;
      }
      loadReport();
    }

    wrap.querySelectorAll(".pp-go-book-emp").forEach(function (btn) {
      btn.addEventListener("click", function () {
        focusWorkflow("salary_creation", btn.getAttribute("data-employee") || "", "");
      });
    });
    wrap.querySelectorAll(".pp-go-pay-emp").forEach(function (btn) {
      btn.addEventListener("click", function () {
        focusWorkflow("payment_manage", btn.getAttribute("data-employee") || "", "");
      });
    });
    wrap.querySelectorAll(".pp-go-book-entry").forEach(function (btn) {
      btn.addEventListener("click", function () {
        focusWorkflow("salary_creation", decodeURIComponent(btn.getAttribute("data-employee") || ""), decodeURIComponent(btn.getAttribute("data-entry") || ""));
      });
    });
    wrap.querySelectorAll(".pp-go-pay-entry").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var emp = decodeURIComponent(btn.getAttribute("data-employee") || "");
        var entryNo = decodeURIComponent(btn.getAttribute("data-entry") || "");
        var amount = num(btn.getAttribute("data-unpaid") || 0);
        focusWorkflow("payment_manage", emp, entryNo, amount);
      });
    });
  }

  function buildSalarySlipGroups(rows) {
    var map = {};
    (rows || []).forEach(function (r) {
      var employee = String(r.employee || "").trim();
      var name1 = String(r.name1 || "").trim() || employee || "(Blank)";
      var key = employee + "||" + name1;
      if (!map[key]) {
        map[key] = {
          employee: employee,
          name1: name1,
          qty: 0,
          amount: 0,
          source_count: 0,
          rows: []
        };
      }
      map[key].qty += num(r.qty);
      map[key].amount += num(r.amount);
      map[key].source_count += 1;
      map[key].rows.push({
        per_piece_salary: r.per_piece_salary || "",
        po_number: r.po_number || "",
        sales_order: r.sales_order || "",
        jv_entry_no: r.jv_entry_no || "",
        from_date: r.from_date || "",
        to_date: r.to_date || "",
        product: r.product || "",
        process_type: r.process_type || "",
        process_size: r.process_size || "No Size",
        jv_status: r.jv_status || "",
        booking_status: r.booking_status || "",
        payment_status: r.payment_status || "",
        qty: num(r.qty),
        rate: num(r.rate),
        amount: num(r.amount),
        booked_amount: num(r.booked_amount),
        paid_amount: num(r.paid_amount),
        unpaid_amount: num(r.unpaid_amount)
      });
    });
    return Object.keys(map).sort().map(function (key) {
      var item = map[key];
      item.rate = avgRate(item.qty, item.amount);
      return item;
    });
  }

  function renderSalarySlipTable(rows) {
    var wrap = el("pp-table-wrap");
    if (!wrap) return;
    var groups = buildSalarySlipGroups(rows);
    if (!groups.length) {
      wrap.innerHTML = "<div style='padding:10px;color:#475569;'>No salary slip rows found for current filters.</div>";
      return;
    }
    var html = "<table class='pp-table'><thead><tr>"
      + "<th>Employee</th><th>Entries</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Booked</th><th>Paid</th><th>Unpaid</th><th>Booking Status</th><th>Payment Status</th><th>Action</th>"
      + "</tr></thead><tbody>";
    var totals = { entries: 0, qty: 0, rate: 0, amount: 0, booked: 0, paid: 0, unpaid: 0 };
    groups.forEach(function (g) {
      var gBooked = 0, gPaid = 0, gUnpaid = 0;
      (g.rows || []).forEach(function (r) {
        gBooked += num(r.booked_amount);
        gPaid += num(r.paid_amount);
        gUnpaid += num(r.unpaid_amount);
      });
      var gBookingStatus = gBooked > 0 ? (gBooked + 0.0001 >= num(g.amount) ? "Booked" : "Partly Booked") : "UnBooked";
      var gPaymentStatus = gPaid > 0 ? (gUnpaid <= 0.0001 ? "Paid" : "Partly Paid") : "Unpaid";
      var action = "<button type='button' class='btn btn-primary btn-xs pp-salary-slip-print' data-mode='detail' data-employee='" + encodeURIComponent(String(g.employee || "")) + "'>Print Detail Slip</button> "
        + "<button type='button' class='btn btn-primary btn-xs pp-salary-slip-print' data-mode='product' data-employee='" + encodeURIComponent(String(g.employee || "")) + "'>Print Product Slip</button> "
        + "<button type='button' class='btn btn-primary btn-xs pp-salary-slip-entry-prints' data-employee='" + encodeURIComponent(String(g.employee || "")) + "'>Entry Wise Print</button>";
      html += "<tr>"
        + "<td>" + esc(g.name1 || g.employee || "") + "</td>"
        + "<td class='num'>" + esc(fmt(g.source_count || 0)) + "</td>"
        + "<td class='num'>" + esc(fmt(g.qty)) + "</td>"
        + "<td class='num'>" + esc(fmt(g.rate)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(g.amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(gBooked)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(gPaid)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(gUnpaid)) + "</td>"
        + "<td>" + statusBadgeHtml(gBookingStatus) + "</td>"
        + "<td>" + statusBadgeHtml(gPaymentStatus) + "</td>"
        + "<td>" + action + "</td>"
        + "</tr>";
      totals.entries += num(g.source_count);
      totals.qty += num(g.qty);
      totals.rate += num(g.rate);
      totals.amount += num(g.amount);
      totals.booked += gBooked;
      totals.paid += gPaid;
      totals.unpaid += gUnpaid;
    });
    html += "<tr class='pp-year-total'><td>Total</td><td class='num'>" + esc(fmt(totals.entries)) + "</td><td class='num'>" + esc(fmt(totals.qty)) + "</td><td class='num'>" + esc(fmt(totals.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.amount)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.booked)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.paid)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totals.unpaid)) + "</td><td></td><td></td><td></td></tr>";
    html += "</tbody></table>";
    wrap.innerHTML = html;
    wrap.querySelectorAll(".pp-doc-summary").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var docName = decodeURIComponent(btn.getAttribute("data-doc") || "");
        showPerPieceSummary(docName);
      });
    });
    wrap.querySelectorAll(".pp-salary-slip-print").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var employee = decodeURIComponent(btn.getAttribute("data-employee") || "");
        var mode = String(btn.getAttribute("data-mode") || "detail");
        showSalarySlipPrint(employee, { mode: mode });
      });
    });
    wrap.querySelectorAll(".pp-salary-slip-entry-prints").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var employee = decodeURIComponent(btn.getAttribute("data-employee") || "");
        showSalaryEntryWisePrints(employee);
      });
    });
    wrap.querySelectorAll(".pp-go-book-entry").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var entryNo = decodeURIComponent(btn.getAttribute("data-entry") || "");
        state.forcedEntryNo = entryNo;
        if (el("pp-entry-no")) el("pp-entry-no").value = entryNo || "";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='salary_creation']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "salary_creation";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activeSalaryBtn3 = document.querySelector(".pp-tab[data-tab='salary_creation']");
        if (activeSalaryBtn3) activeSalaryBtn3.classList.add("active");
        setWorkflowHistoryRange("salary_creation", "", "");
        var onlyEmp = decodeURIComponent(btn.getAttribute("data-employee") || "");
        var empMap = {};
        getAdjustedEmployeeRows().forEach(function (row) {
          var emp = row.employee || "";
          if (!emp) return;
          if (onlyEmp && emp !== onlyEmp) empMap[emp] = true;
        });
        state.excludedEmployees = empMap;
        setPageForCurrentTab(1);
        loadReport();
      });
    });
    wrap.querySelectorAll(".pp-go-pay-entry").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var entryNo = decodeURIComponent(btn.getAttribute("data-entry") || "");
        state.forcedEntryNo = entryNo;
        if (el("pp-entry-no")) el("pp-entry-no").value = entryNo || "";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "payment_manage";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activePayBtn3 = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (activePayBtn3) activePayBtn3.classList.add("active");
        setWorkflowHistoryRange("payment_manage", "", "");
        var onlyEmp = decodeURIComponent(btn.getAttribute("data-employee") || "");
        var targetPay = num(btn.getAttribute("data-unpaid") || 0);
        var payMap = {};
        getPaymentActiveRows().forEach(function (row) {
          var emp = row.employee || "";
          if (!emp) return;
          if (onlyEmp && emp !== onlyEmp) payMap[emp] = true;
        });
        state.paymentExcludedEmployees = payMap;
        var targetRow = null;
        getPaymentActiveRows().forEach(function (row) {
          if (!targetRow && String(row.employee || "") === String(onlyEmp || "")) targetRow = row;
        });
        if (targetRow && targetPay > 0) {
          if (!state.paymentAdjustments[onlyEmp]) {
            state.paymentAdjustments[onlyEmp] = { payment_amount: 0, unpaid_amount: num(targetRow.unpaid_amount) };
          }
          state.paymentAdjustments[onlyEmp].unpaid_amount = num(targetRow.unpaid_amount);
          state.paymentAdjustments[onlyEmp].payment_amount = Math.min(targetPay, Math.max(0, num(targetRow.unpaid_amount)));
        }
        setPageForCurrentTab(1);
        loadReport();
      });
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

  function uniqueSalaryDocs(sourceRows) {
    var map = {};
    var rows = sourceRows || state.rows || [];
    (rows || []).forEach(function (r) {
      var key = String(r.per_piece_salary || "");
      if (!key) return;
      if (!map[key]) {
        map[key] = {
          name: key,
          from_date: r.from_date || "",
          to_date: r.to_date || "",
          po_number: r.po_number || "",
          item_group: r.item_group || "",
          total_amount: 0,
          unbooked_amount: 0,
          booked_amount: 0,
          paid_amount: 0,
          unpaid_amount: 0,
          _row_count: 0,
          _booked_count: 0,
          _paid_count: 0,
          _unpaid_count: 0,
          booking_status: "UnBooked",
          payment_status: "Unpaid"
        };
      }
      map[key].total_amount += num(r.amount);
      var amount = num(r.amount);
      var hasJV = !!String(r.jv_entry_no || "").trim();
      var jvStatus = String(r.jv_status || "");
      var isBooked = hasJV && jvStatus === "Posted";
      var bookedVal = num(r.booked_amount);
      if (bookedVal < 0) bookedVal = 0;
      if (!isBooked) bookedVal = 0;
      if (isBooked && bookedVal <= 0) bookedVal = amount;
      var paidVal = num(r.paid_amount);
      if (paidVal < 0) paidVal = 0;
      if (paidVal > bookedVal) paidVal = bookedVal;
      var unpaidVal = num(r.unpaid_amount);
      if (unpaidVal < 0 || unpaidVal > bookedVal) unpaidVal = Math.max(bookedVal - paidVal, 0);
      map[key].booked_amount += bookedVal;
      map[key].unbooked_amount += isBooked ? 0 : Math.max(amount - bookedVal, 0);
      map[key].paid_amount += paidVal;
      map[key].unpaid_amount += unpaidVal;
      map[key]._row_count += 1;
      if (isBooked) map[key]._booked_count += 1;
    });
    return Object.keys(map).sort(compareEntryNoDesc).map(function (k) {
      var d = map[k];
      if (d._booked_count === d._row_count) d.booking_status = "Booked";
      else if (d._booked_count > 0) d.booking_status = "Partly Booked";
      else d.booking_status = "UnBooked";

      if (num(d.booked_amount) <= 0) d.payment_status = "Unpaid";
      else if (num(d.unpaid_amount) <= 0.005) d.payment_status = "Paid";
      else if (num(d.paid_amount) > 0.005) d.payment_status = "Partly Paid";
      else d.payment_status = "Unpaid";
      return d;
    });
  }

  function getRecentDocDetails(docName) {
    var rows = [];
    var target = String(docName || "").trim();
    if (!target) return rows;
    var sourceRows = (state.entryMeta && state.entryMeta.recentRows) || state.rows || [];
    (sourceRows || []).forEach(function (r) {
      if (String(r.per_piece_salary || "").trim() !== target) return;
      rows.push({
        employee: r.name1 || r.employee || "",
        employee_id: r.employee || "",
        po_number: r.po_number || "",
        sales_order: r.sales_order || "",
        product: r.product || "",
        process_type: r.process_type || "",
        process_size: r.process_size || "No Size",
        qty: num(r.qty),
        rate: num(r.rate),
        amount: num(r.amount),
        booking_status: r.booking_status || "UnBooked",
        payment_status: r.payment_status || "Unpaid"
      });
    });
    return rows;
  }

  function filterDataEntryDocsByDate(docs) {
    var fromInput = el("pp-entry-history-from");
    var toInput = el("pp-entry-history-to");
    var bookingInput = el("pp-entry-history-booking-status");
    var paymentInput = el("pp-entry-history-payment-status");
    var fromDate = fromInput ? (fromInput.value || "") : ((state.workflowHistoryDate.data_entry || {}).from || "");
    var toDate = toInput ? (toInput.value || "") : ((state.workflowHistoryDate.data_entry || {}).to || "");
    var status = getWorkflowStatusFilter("data_entry");
    var bookingStatus = bookingInput ? (bookingInput.value || "") : status.booking;
    var paymentStatus = paymentInput ? (paymentInput.value || "") : status.payment;
    return filterDocsByStatus(filterRowsByDateRange((docs || []), fromDate, toDate), bookingStatus, paymentStatus);
  }

  function getRecentDocEmployeeSummary(docName) {
    var map = {};
    getRecentDocDetails(docName).forEach(function (r) {
      var emp = String(r.employee || "").trim() || String(r.employee_id || "").trim() || "(Blank)";
      if (!map[emp]) {
        map[emp] = {
          employee: emp,
          po_number: r.po_number || "",
          qty: 0,
          amount: 0,
          booked: 0,
          paid: 0,
          unpaid: 0
        };
      }
      map[emp].qty += num(r.qty);
      map[emp].amount += num(r.amount);
      var b = String(r.booking_status || "");
      var p = String(r.payment_status || "");
      if (b === "Booked") map[emp].booked += 1;
      if (p === "Paid") map[emp].paid += 1;
      if (p === "Unpaid") map[emp].unpaid += 1;
    });
    return Object.keys(map).sort().map(function (k) {
      var item = map[k];
      item.rate = avgRate(item.qty, item.amount);
      item.booking_status = item.booked > 0 ? (item.unpaid > 0 ? "Partly Booked" : "Booked") : "UnBooked";
      item.payment_status = item.paid > 0 ? (item.unpaid > 0 ? "Partly Paid" : "Paid") : "Unpaid";
      return item;
    });
  }

  function showDataEntryEmployeeDetails(docName, employee) {
    var targetEmp = String(employee || "").trim();
    var rows = getRecentDocDetails(docName).filter(function (r) {
      return String(r.employee || "").trim() === targetEmp;
    });
    if (!rows.length) {
      setSummaryModal("Data Entry Detail", targetEmp, "<div style='color:#b91c1c;'>No detail rows found.</div>");
      return;
    }
    var qty = 0;
    var amount = 0;
    var html = "<table class='pp-table'><thead><tr><th>Employee</th><th>PO Number</th><th>Sales Order</th><th>Product</th><th>Process Type</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>JV Status</th><th>Pay Status</th></tr></thead><tbody>";
    rows.forEach(function (r) {
      qty += num(r.qty);
      amount += num(r.amount);
      html += "<tr>"
        + "<td>" + esc(r.employee || "") + "</td>"
        + "<td>" + esc(r.po_number || "") + "</td>"
        + "<td>" + esc(r.sales_order || "") + "</td>"
        + "<td>" + esc(r.product || "") + "</td>"
        + "<td>" + esc(r.process_type || "") + "</td>"
        + "<td>" + esc(r.process_size || "No Size") + "</td>"
        + "<td class='num'>" + esc(fmt(r.qty)) + "</td>"
        + "<td class='num'>" + esc(fmt(lineRate(r.rate, r.qty, r.amount))) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td>"
        + "<td>" + statusBadgeHtml(r.booking_status || "") + "</td>"
        + "<td>" + statusBadgeHtml(r.payment_status || "") + "</td>"
        + "</tr>";
    });
    html += "<tr class='pp-year-total'><td>Total</td><td></td><td></td><td></td><td></td><td></td><td class='num'>" + esc(fmt(qty)) + "</td><td class='num'>" + esc(fmt(avgRate(qty, amount))) + "</td><td class='num pp-amt-col'>" + esc(fmt(amount)) + "</td><td></td><td></td></tr>";
    html += "</tbody></table>";
    setSummaryModal("Data Entry Detail", targetEmp + " | " + docName, html);
  }

  function showDataEntryEnteredRows(docName) {
    var rows = getRecentDocDetails(docName);
    if (!rows.length) {
      setSummaryModal("Data Entry Rows", docName || "", "<div style='color:#b91c1c;'>No rows found for this entry.</div>");
      return;
    }
    var qty = 0;
    var amount = 0;
    var html = "<table class='pp-table'><thead><tr><th>Employee</th><th>PO Number</th><th>Sales Order</th><th>Product</th><th>Process Type</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
    rows.forEach(function (r) {
      qty += num(r.qty);
      amount += num(r.amount);
      html += "<tr>"
        + "<td>" + esc(r.employee || "") + "</td>"
        + "<td>" + esc(r.po_number || "") + "</td>"
        + "<td>" + esc(r.sales_order || "") + "</td>"
        + "<td>" + esc(r.product || "") + "</td>"
        + "<td>" + esc(r.process_type || "") + "</td>"
        + "<td>" + esc(r.process_size || "No Size") + "</td>"
        + "<td class='num'>" + esc(fmt(r.qty)) + "</td>"
        + "<td class='num'>" + esc(fmt(lineRate(r.rate, r.qty, r.amount))) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td>"
        + "</tr>";
    });
    html += "<tr class='pp-year-total'><td>Total</td><td></td><td></td><td></td><td></td><td></td><td class='num'>" + esc(fmt(qty)) + "</td><td class='num'>" + esc(fmt(avgRate(qty, amount))) + "</td><td class='num pp-amt-col'>" + esc(fmt(amount)) + "</td></tr>";
    html += "</tbody></table>";
    setSummaryModal("Data Entry Rows", docName || "", html);
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
    if (tab === "salary_creation" || tab === "payment_manage") pageSize = 10;
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

  function paginateHistoryRows(key, rows, pageSize) {
    var allRows = rows || [];
    var size = Math.max(parseInt(pageSize || 10, 10) || 10, 1);
    var totalPages = Math.max(1, Math.ceil(allRows.length / size));
    var page = parseInt((state.historyPageByTab || {})[key] || 1, 10);
    if (!page || page < 1) page = 1;
    if (page > totalPages) page = totalPages;
    if (!state.historyPageByTab) state.historyPageByTab = {};
    state.historyPageByTab[key] = page;
    var start = (page - 1) * size;
    var end = Math.min(start + size, allRows.length);
    return {
      key: key,
      rows: allRows.slice(start, end),
      total: allRows.length,
      page: page,
      totalPages: totalPages,
      start: start + 1,
      end: end
    };
  }

  function historyPagerHtml(meta) {
    if (!meta || meta.total <= 0 || meta.totalPages <= 1) return "";
    var prevDisabled = meta.page <= 1 ? " disabled" : "";
    var nextDisabled = meta.page >= meta.totalPages ? " disabled" : "";
    return "<div class='pp-pagination' style='justify-content:flex-end;margin-top:6px;'>"
      + "<span>Rows " + esc(meta.start) + "-" + esc(meta.end) + " of " + esc(meta.total) + "</span>"
      + "<button type='button' class='btn btn-default btn-xs pp-history-prev' data-key='" + esc(meta.key) + "'" + prevDisabled + ">Previous</button>"
      + "<span>Page " + esc(meta.page) + " / " + esc(meta.totalPages) + "</span>"
      + "<button type='button' class='btn btn-default btn-xs pp-history-next' data-key='" + esc(meta.key) + "'" + nextDisabled + ">Next</button>"
      + "</div>";
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

    var subtitleText = docName + " | " + (first.from_date || "") + " to " + (first.to_date || "");
    var html = summaryHeaderHtml("Per Piece Entry Detail", subtitleText)
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
      + "<th>Employee</th><th>PO Number</th><th>Product</th><th>Sales Order</th><th>Process</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Booking</th><th>Payment</th>"
      + "</tr></thead><tbody>";
    rows.forEach(function (r) {
      html += "<tr>"
        + "<td>" + esc(employeeLabel(r) || "") + "</td>"
        + "<td>" + esc(r.po_number || first.po_number || "") + "</td>"
        + "<td>" + esc(r.product || "") + "</td>"
        + "<td>" + esc(r.sales_order || "") + "</td>"
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
    setSummaryModal("Per Piece Entry Detail", subtitleText, html);
  }

  function showPOSummary(poNumber, action) {
    var rows = (state.rows || []).filter(function (r) {
      return String(r.po_number || "") === String(poNumber || "");
    });
    var modal = el("pp-summary-modal");
    var subtitle = el("pp-summary-subtitle");
    var content = el("pp-summary-content");
    if (!modal || !subtitle || !content || !poNumber) return;

    if (!rows.length) {
      subtitle.textContent = "PO Number: " + poNumber;
      content.innerHTML = "<div style='color:#b91c1c;'>No rows available for this PO under selected filters.</div>";
      modal.style.display = "flex";
      return;
    }

    var totalQty = 0;
    var totalAmount = 0;
    var processMap = {};
    var productMap = {};
    var employeeMap = {};
    rows.forEach(function (r) {
      totalQty += num(r.qty);
      totalAmount += num(r.amount);

      var processKey = String(r.process_type || "") || "(Blank)";
      if (!processMap[processKey]) {
        processMap[processKey] = {
          process_type: r.process_type || "",
          qty: 0,
          rate: 0,
          amount: 0,
          product_map: {}
        };
      }
      processMap[processKey].qty += num(r.qty);
      processMap[processKey].amount += num(r.amount);
      var productKey = String(r.product || "") || "(Blank)";
      if (!processMap[processKey].product_map[productKey]) {
        processMap[processKey].product_map[productKey] = {
          product: r.product || "",
          qty: 0,
          amount: 0,
          rows: []
        };
      }
      processMap[processKey].product_map[productKey].qty += num(r.qty);
      processMap[processKey].product_map[productKey].amount += num(r.amount);
      processMap[processKey].product_map[productKey].rows.push({
        per_piece_salary: r.per_piece_salary || "",
        employee: employeeLabel(r) || "",
        process_type: r.process_type || "",
        sales_order: r.sales_order || "",
        process_size: r.process_size || "No Size",
        qty: num(r.qty),
        rate: num(r.rate),
        amount: num(r.amount)
      });

      if (!productMap[productKey]) {
        productMap[productKey] = {
          product: r.product || "",
          qty: 0,
          rate: 0,
          amount: 0,
          process_map: {}
        };
      }
      productMap[productKey].qty += num(r.qty);
      productMap[productKey].amount += num(r.amount);
      if (!productMap[productKey].process_map[processKey]) {
        productMap[productKey].process_map[processKey] = {
          process_type: r.process_type || "",
          qty: 0,
          amount: 0,
          rows: []
        };
      }
      productMap[productKey].process_map[processKey].qty += num(r.qty);
      productMap[productKey].process_map[processKey].amount += num(r.amount);
      productMap[productKey].process_map[processKey].rows.push({
        sales_order: r.sales_order || "",
        process_size: r.process_size || "No Size",
        qty: num(r.qty),
        rate: num(r.rate),
        amount: num(r.amount)
      });

      var employeeKey = String(r.employee || "") + "||" + String(r.name1 || "");
      if (!employeeMap[employeeKey]) {
        employeeMap[employeeKey] = {
          employee: r.employee || "",
          name1: r.name1 || r.employee || "",
          qty: 0,
          amount: 0
        };
      }
      employeeMap[employeeKey].qty += num(r.qty);
      employeeMap[employeeKey].amount += num(r.amount);
    });

    var processRows = Object.keys(processMap).map(function (key) {
      var item = processMap[key];
      item.rate = avgRate(item.qty, item.amount);
      item.products = Object.keys(item.product_map || {}).sort().map(function (productKey) {
        var productItem = item.product_map[productKey];
        productItem.rate = avgRate(productItem.qty, productItem.amount);
        productItem.rows.sort(function (a, b) {
          return String(b.per_piece_salary || "").localeCompare(String(a.per_piece_salary || ""));
        });
        return productItem;
      });
      return item;
    }).sort(function (a, b) {
      return compareByProcessSequence(a, b, "", "");
    });
    var productRows = Object.keys(productMap).sort().map(function (key) {
      var item = productMap[key];
      item.rate = avgRate(item.qty, item.amount);
      item.processes = Object.keys(item.process_map || {}).map(function (processKey) {
        var processItem = item.process_map[processKey];
        processItem.rate = avgRate(processItem.qty, processItem.amount);
        return processItem;
      }).sort(function (a, b) {
        return compareByProcessSequence(a, b, item.product || "", item.product || "");
      });
      return item;
    });
    var employeeRows = Object.keys(employeeMap).sort().map(function (key) {
      var item = employeeMap[key];
      item.rate = avgRate(item.qty, item.amount);
      return item;
    });

    var subtitleText = "PO Number: " + poNumber;
    var html = summaryHeaderHtml("PO Summary Detail", subtitleText) + "<div class='pp-summary-chips'>"
      + "<span class='pp-summary-chip' style='font-weight:700;background:#dbeafe;border-color:#93c5fd;'>PO Number: " + esc(poNumber) + "</span>"
      + "<span class='pp-summary-chip'>Entries: " + esc(rows.length) + "</span>"
      + "<span class='pp-summary-chip'>Qty: " + esc(fmt(totalQty)) + "</span>"
      + "<span class='pp-summary-chip'>Amount: " + esc(fmt(totalAmount)) + "</span>"
      + "</div>";

    if (action !== "print_product") {
      processRows.forEach(function (r) {
        html += "<h4 style='margin:12px 0 6px 0;'>Process: " + esc(r.process_type || "(Blank)") + "</h4>";
        html += "<table class='pp-table'><thead><tr><th>Product</th><th>Sales Order</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
        (r.products || []).forEach(function (productItem) {
          (productItem.rows || []).forEach(function (detailRow) {
            html += "<tr>"
              + "<td>" + esc(productItem.product || "") + "</td>"
              + "<td>" + esc(detailRow.sales_order || "") + "</td>"
              + "<td>" + esc(detailRow.process_size || "No Size") + "</td>"
              + "<td class='num'>" + esc(fmt(detailRow.qty)) + "</td>"
              + "<td class='num'>" + esc(fmt(detailRow.rate)) + "</td>"
              + "<td class='num pp-amt-col'>" + esc(fmt(detailRow.amount)) + "</td>"
              + "</tr>";
          });
        });
        html += "<tr class='pp-year-total'><td colspan='3'>Process Total</td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num'>" + esc(fmt(r.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td></tr>";
        html += "</tbody></table>";
      });
    }

    if (action !== "print_process") {
      html += "<h4 style='margin:14px 0 6px 0;'>Product Heading / Process Table</h4>";
      productRows.forEach(function (r) {
        html += "<h4 style='margin:12px 0 6px 0;'>Product: " + esc(r.product || "(Blank)") + "</h4>";
        html += "<table class='pp-table'><thead><tr><th>Process</th><th>Sales Order</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
        (r.processes || []).forEach(function (processItem) {
          (processItem.rows || []).forEach(function (detailRow) {
            html += "<tr>"
              + "<td>" + esc(processItem.process_type || "") + "</td>"
              + "<td>" + esc(detailRow.sales_order || "") + "</td>"
              + "<td>" + esc(detailRow.process_size || "No Size") + "</td>"
              + "<td class='num'>" + esc(fmt(detailRow.qty)) + "</td>"
              + "<td class='num'>" + esc(fmt(detailRow.rate)) + "</td>"
              + "<td class='num pp-amt-col'>" + esc(fmt(detailRow.amount)) + "</td>"
              + "</tr>";
          });
        });
        html += "<tr class='pp-year-total'><td colspan='3'>Product Total</td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num'>" + esc(fmt(r.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td></tr>";
        html += "</tbody></table>";
      });
    }

    html += "<h4 style='margin:12px 0 6px 0;'>All Process Grand Total</h4>";
    html += "<table class='pp-table'><thead><tr><th>Label</th><th>Total Qty</th><th>Total Amount</th></tr></thead><tbody>";
    html += "<tr class='pp-year-total'><td>Grand Total</td><td class='num'>" + esc(fmt(totalQty)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totalAmount)) + "</td></tr>";
    html += "</tbody></table>";

    html += "<h4 style='margin:12px 0 6px 0;'>Employee Summary</h4>";
    html += "<table class='pp-table'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
    employeeRows.forEach(function (r) {
      html += "<tr><td>" + esc(r.name1 || r.employee || "") + "</td><td class='num'>" + esc(fmt(r.qty)) + "</td><td class='num'>" + esc(fmt(r.rate)) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td></tr>";
    });
    html += "<tr class='pp-year-total'><td>Total</td><td class='num'>" + esc(fmt(totalQty)) + "</td><td></td><td class='num pp-amt-col'>" + esc(fmt(totalAmount)) + "</td></tr>";
    html += "</tbody></table>";

    setSummaryModal("PO Summary Detail", subtitleText, html);
    if (action === "print" || action === "pdf" || action === "print_process" || action === "print_product") {
      setTimeout(function () {
        printSummaryModal();
      }, 50);
    }
  }

  function showSalaryEmployeeDetail(employee) {
    var modal = el("pp-summary-modal");
    var subtitle = el("pp-summary-subtitle");
    var content = el("pp-summary-content");
    if (!modal || !subtitle || !content || !employee) return;

    var rows = getAdjustedEmployeeRows();
    var row = null;
    rows.forEach(function (r) {
      if (!row && String(r.employee || "") === String(employee || "")) row = r;
    });

    if (!row) {
      subtitle.textContent = employee;
      content.innerHTML = "<div style='color:#b91c1c;'>No employee detail available under current filters.</div>";
      modal.style.display = "flex";
      return;
    }

    var detailQty = 0;
    var detailAmount = 0;
    (row.source_entries || []).forEach(function (src) {
      detailQty += num(src.qty);
      detailAmount += num(src.amount);
    });

    var subtitleText = (employeeLabel(row) || employee) + " | Salary Detail";
    var html = summaryHeaderHtml("Salary Creation Detail", subtitleText)
      + "<div class='pp-summary-chips'>"
      + "<span class='pp-summary-chip'>Employee: " + esc(row.employee || "-") + "</span>"
      + "<span class='pp-summary-chip'>Qty: " + esc(fmt(row.qty)) + "</span>"
      + "<span class='pp-summary-chip'>Base Amount: " + esc(fmt(row.amount)) + "</span>"
      + "<span class='pp-summary-chip'>Advance Balance: " + esc(fmt(row.advance_balance)) + "</span>"
      + "<span class='pp-summary-chip'>Advance Deduction: " + esc(fmt(row.advance_deduction)) + "</span>"
      + "<span class='pp-summary-chip'>Allowance: " + esc(fmt(row.allowance)) + "</span>"
      + "<span class='pp-summary-chip'>Other Deduction: " + esc(fmt(row.other_deduction)) + "</span>"
      + "<span class='pp-summary-chip'>Net Amount: " + esc(fmt(row.net_amount)) + "</span>"
      + "<span class='pp-summary-chip'>Entries: " + esc(row.source_count || 0) + "</span>"
      + "</div>";

    if (!(row.source_entries || []).length) {
      html += "<div style='color:#475569;'>No source entries found for this employee in current salary selection.</div>";
      setSummaryModal("Salary Creation Detail", subtitleText, html);
      return;
    }

    html += "<table class='pp-table'><thead><tr>"
      + "<th>Per Piece Salary</th><th>PO Number</th><th>Sales Order</th><th>Qty</th><th>Amount</th><th>View</th>"
      + "</tr></thead><tbody>";
    (row.source_entries || []).forEach(function (src) {
      html += "<tr>"
        + "<td>" + esc(src.per_piece_salary || "") + "</td>"
        + "<td>" + esc(src.po_number || "") + "</td>"
        + "<td>" + esc(src.sales_order || "") + "</td>"
        + "<td class='num'>" + esc(fmt(src.qty)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(src.amount)) + "</td>"
        + "<td><button type='button' class='btn btn-xs btn-default pp-salary-entry-detail' data-doc='" + encodeURIComponent(String(src.per_piece_salary || "")) + "'>View Items</button></td>"
        + "</tr>";
    });
    html += "<tr class='pp-year-total'>"
      + "<td>Total Entries: " + esc(row.source_count || 0) + "</td>"
      + "<td></td>"
      + "<td></td>"
      + "<td class='num'>" + esc(fmt(detailQty)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(detailAmount)) + "</td>"
      + "<td></td>"
      + "</tr>";
    html += "</tbody></table>";
    content.innerHTML = html;
    content.querySelectorAll(".pp-salary-entry-detail").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var docName = decodeURIComponent(btn.getAttribute("data-doc") || "");
        if (!docName) return;
        showPerPieceSummary(docName);
      });
    });
    setSummaryHeading("Salary Creation Detail");
    subtitle.textContent = subtitleText;
    state.summaryPrintMeta = {
      heading: "Salary Creation Detail",
      subtitle: subtitleText,
      company: currentCompanyLabel(),
      date_range: currentDateRangeLabel()
    };
    modal.style.display = "flex";
  }

  function hidePerPieceSummary() {
    var modal = el("pp-summary-modal");
    if (modal) modal.style.display = "none";
  }

  function printSummaryModal() {
    var title = el("pp-summary-subtitle") ? el("pp-summary-subtitle").textContent || "" : "";
    var body = el("pp-summary-content") ? el("pp-summary-content").innerHTML || "" : "";
    if (!body) return;
    var tempWrap = document.createElement("div");
    tempWrap.innerHTML = body;
    var inlineHeader = tempWrap.querySelector(".pp-inline-summary-header");
    if (inlineHeader && inlineHeader.parentNode) inlineHeader.parentNode.removeChild(inlineHeader);
    body = tempWrap.innerHTML;
    var meta = state.summaryPrintMeta || {};
    var heading = meta.heading || "Per Piece Salary Summary";
    var company = meta.company || currentCompanyLabel() || "";
    var dateRange = meta.date_range || currentDateRangeLabel() || "";
    var win = window.open("", "_blank", "width=1200,height=800");
    if (!win) return;
    win.document.open();
    win.document.write(
      "<!DOCTYPE html><html><head><title>" + esc(title) + "</title>"
      + "<style>"
      + "body{font-family:Arial,sans-serif;padding:18px;color:#111827;}"
      + "h1{font-size:20px;margin:0 0 4px 0;} .sub{font-size:12px;color:#475569;margin-bottom:12px;}"
      + ".pp-table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:14px;}"
      + ".pp-table th,.pp-table td{border:1px solid #cbd5e1;padding:6px 8px;}"
      + ".pp-table th{background:#dbeafe !important;text-align:left;-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
      + ".pp-table td.num{text-align:right;font-variant-numeric:tabular-nums;}"
      + ".pp-table td.pp-amt-col{font-weight:700;}"
      + ".pp-year-total td{background:#ecfccb !important;font-weight:700;-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
      + ".pp-summary-chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;}"
      + ".pp-summary-chip{border:1px solid #cbd5e1;border-radius:999px;padding:4px 8px;font-size:12px;}"
      + "h4{margin:12px 0 6px 0;font-size:14px;background:#fef3c7 !important;border:1px solid #cbd5e1;padding:6px 8px;-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
      + "</style></head><body>"
      + "<h1>" + esc(company || "Company") + "</h1>"
      + "<div class='sub'><strong>" + esc(heading) + "</strong>" + (title ? " | " + esc(title) : "") + (dateRange ? " | Date: " + esc(dateRange) : "") + "</div>"
      + body
      + "</body></html>"
    );
    win.document.close();
    win.focus();
    win.print();
  }

  function printCurrentTabReport() {
    var snap = state.lastTabRender || {};
    var heading = getCurrentTabLabel() || "Report";
    var dateRange = currentDateRangeLabel();
    var company = currentCompanyLabel();
    var tableHtml = "";

    if (snap.mode === "table" && (snap.columns || []).length) {
      tableHtml = "<table class='pp-table'><thead><tr>";
      (snap.columns || []).forEach(function (c) {
        tableHtml += "<th>" + esc(c.label || "") + "</th>";
      });
      tableHtml += "</tr></thead><tbody>";
      (snap.rows || []).forEach(function (r) {
        var rowClass = "";
        if (r && r._group_header) rowClass = " class='pp-group-head'";
        else if (r && r._is_total) rowClass = " class='pp-year-total'";
        tableHtml += "<tr" + rowClass + ">";
        (snap.columns || []).forEach(function (c, idx) {
          if (r && r._group_header) {
            if (idx === 0) tableHtml += "<td>" + esc(r._group_label || "") + "</td>";
            else tableHtml += "<td></td>";
            return;
          }
          var v = r ? r[c.fieldname] : "";
          var classes = [];
          if (c.numeric) classes.push("num");
          if (isAmountField(c.fieldname)) classes.push("pp-amt-col");
          var cls = classes.length ? " class='" + classes.join(" ") + "'" : "";
          tableHtml += "<td" + cls + ">" + esc(c.numeric ? fmt(v) : (v || "")) + "</td>";
        });
        tableHtml += "</tr>";
      });
      tableHtml += "</tbody></table>";
    } else {
      var wrap = el("pp-table-wrap");
      tableHtml = wrap ? (wrap.innerHTML || "<div>No data</div>") : "<div>No data</div>";
    }

    var win = window.open("", "_blank", "width=1200,height=800");
    if (!win) return;
    win.document.open();
    win.document.write(
      "<!DOCTYPE html><html><head><title>" + esc(heading) + "</title>"
      + "<style>"
      + "body{font-family:Arial,sans-serif;padding:18px;color:#111827;}"
      + "h1{font-size:20px;margin:0 0 4px 0;} .sub{font-size:12px;color:#475569;margin-bottom:12px;}"
      + ".pp-table{width:100%;border-collapse:collapse;font-size:12px;}"
      + ".pp-table th,.pp-table td{border:1px solid #cbd5e1;padding:6px 8px;}"
      + ".pp-table th{background:#dbeafe !important;text-align:left;-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
      + ".pp-table td.num{text-align:right;font-variant-numeric:tabular-nums;}"
      + ".pp-table td.pp-amt-col{font-weight:700;}"
      + ".pp-year-total td{background:#ecfccb !important;font-weight:700;-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
      + ".pp-group-head td{background:#e2e8f0 !important;font-weight:700;-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
      + "</style></head><body>"
      + "<h1>" + esc(company || "Company") + "</h1>"
      + "<div class='sub'><strong>" + esc(heading) + "</strong>" + (dateRange ? (" | Date: " + esc(dateRange)) : "") + "</div>"
      + tableHtml
      + "</body></html>"
    );
    win.document.close();
    win.focus();
    win.print();
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
    wrap.querySelectorAll(".pp-view-entry").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var docName = btn.getAttribute("data-entry") || "";
        if (!docName) return;
        showPerPieceSummary(docName);
      });
    });
    wrap.querySelectorAll(".pp-view-salary-create").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var docName = btn.getAttribute("data-entry") || "";
        if (!docName) return;
        showSalaryCreationEntrySummary(docName, false);
      });
    });
    wrap.querySelectorAll(".pp-print-salary-create").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var docName = btn.getAttribute("data-entry") || "";
        if (!docName) return;
        showSalaryCreationEntrySummary(docName, true);
      });
    });
    wrap.querySelectorAll(".pp-go-pay-salary-entry").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var entry = String(btn.getAttribute("data-entry") || "").trim();
        if (!entry) return;
        state.forcedEntryNo = entry;
        if (el("pp-entry-no")) el("pp-entry-no").value = entry;
        if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = entry;
        if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = entry;
        setWorkflowHistoryRange("payment_manage", "", "");
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "payment_manage";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activePayBtn4 = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (activePayBtn4) activePayBtn4.classList.add("active");
        state.paymentExcludedEmployees = {};
        setPageForCurrentTab(1);
        loadReport();
      });
    });
    wrap.querySelectorAll(".pp-salary-history-book").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var entry = String(btn.getAttribute("data-entry") || "").trim();
        if (!entry) return;
        state.forcedEntryNo = entry;
        if (el("pp-entry-no")) el("pp-entry-no").value = entry;
        if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = entry;
        if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = entry;
        setWorkflowHistoryRange("salary_creation", "", "");
        switchWorkspaceMode("entry", true);
        state.currentTab = "salary_creation";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activeSalaryBtn4 = document.querySelector(".pp-tab[data-tab='salary_creation']");
        if (activeSalaryBtn4) activeSalaryBtn4.classList.add("active");
        state.excludedEmployees = {};
        setPageForCurrentTab(1);
        loadReport();
      });
    });
    wrap.querySelectorAll(".pp-salary-history-select").forEach(function (box) {
      box.addEventListener("change", function () {
        state.entryMeta.selected_salary_history = state.entryMeta.selected_salary_history || {};
        var name = String(box.getAttribute("data-entry") || "").trim();
        if (!name) return;
        state.entryMeta.selected_salary_history[name] = !!box.checked;
        var countEl = el("pp-salary-history-selected-count");
        if (countEl) {
          var count = Object.keys(state.entryMeta.selected_salary_history).filter(function (k) { return !!state.entryMeta.selected_salary_history[k]; }).length;
          countEl.textContent = String(count);
        }
      });
    });
    if (el("pp-salary-history-select-page")) {
      el("pp-salary-history-select-page").addEventListener("click", function () {
        state.entryMeta.selected_salary_history = state.entryMeta.selected_salary_history || {};
        wrap.querySelectorAll(".pp-salary-history-select").forEach(function (box) {
          var name = String(box.getAttribute("data-entry") || "").trim();
          if (!name) return;
          box.checked = true;
          state.entryMeta.selected_salary_history[name] = true;
        });
        var countEl = el("pp-salary-history-selected-count");
        if (countEl) {
          var count = Object.keys(state.entryMeta.selected_salary_history).filter(function (k) { return !!state.entryMeta.selected_salary_history[k]; }).length;
          countEl.textContent = String(count);
        }
      });
    }
    if (el("pp-salary-history-clear-selected")) {
      el("pp-salary-history-clear-selected").addEventListener("click", function () {
        state.entryMeta.selected_salary_history = {};
        renderCreatedEntriesPanel("salary_creation");
      });
    }
    if (el("pp-salary-history-pay-selected")) {
      el("pp-salary-history-pay-selected").addEventListener("click", function () {
        var selected = Object.keys(state.entryMeta.selected_salary_history || {}).filter(function (k) { return !!state.entryMeta.selected_salary_history[k]; }).sort(compareEntryNoDesc);
        if (!selected.length) {
          var jvResult = el("pp-jv-result");
          if (jvResult) showResult(jvResult, "error", "No Entry Selected", "Select one or more salary entries first.");
          return;
        }
        state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
        if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
        if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo;
        if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = state.forcedEntryNo;
        if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = selected.join(", ");
        if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = "";
        setWorkflowHistoryRange("payment_manage", "", "");
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "payment_manage";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activePayBtn5 = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (activePayBtn5) activePayBtn5.classList.add("active");
        state.paymentExcludedEmployees = {};
        setPageForCurrentTab(1);
        loadReport();
      });
    }
    if (el("pp-jv-history-from")) {
      el("pp-jv-history-from").addEventListener("change", function () {
        setWorkflowHistoryRange("salary_creation", el("pp-jv-history-from").value || "", (el("pp-jv-history-to") && el("pp-jv-history-to").value) || "");
        state.historyPageByTab.salary_creation_history = 1;
        renderCreatedEntriesPanel("salary_creation");
      });
    }
    if (el("pp-jv-history-to")) {
      el("pp-jv-history-to").addEventListener("change", function () {
        setWorkflowHistoryRange("salary_creation", (el("pp-jv-history-from") && el("pp-jv-history-from").value) || "", el("pp-jv-history-to").value || "");
        state.historyPageByTab.salary_creation_history = 1;
        renderCreatedEntriesPanel("salary_creation");
      });
    }
    if (el("pp-jv-history-booking-status")) {
      el("pp-jv-history-booking-status").addEventListener("change", function () {
        setWorkflowStatusFilter("salary_creation", el("pp-jv-history-booking-status").value || "", (el("pp-jv-history-payment-status") && el("pp-jv-history-payment-status").value) || "");
        state.historyPageByTab.salary_creation_history = 1;
        renderCreatedEntriesPanel("salary_creation");
      });
    }
    if (el("pp-jv-history-payment-status")) {
      el("pp-jv-history-payment-status").addEventListener("change", function () {
        setWorkflowStatusFilter("salary_creation", (el("pp-jv-history-booking-status") && el("pp-jv-history-booking-status").value) || "", el("pp-jv-history-payment-status").value || "");
        state.historyPageByTab.salary_creation_history = 1;
        renderCreatedEntriesPanel("salary_creation");
      });
    }
    if (el("pp-pay-history-from")) {
      el("pp-pay-history-from").addEventListener("change", function () {
        setWorkflowHistoryRange("payment_manage", el("pp-pay-history-from").value || "", (el("pp-pay-history-to") && el("pp-pay-history-to").value) || "");
        state.historyPageByTab.payment_manage_history = 1;
        renderCreatedEntriesPanel("payment_manage");
      });
    }
    if (el("pp-pay-history-to")) {
      el("pp-pay-history-to").addEventListener("change", function () {
        setWorkflowHistoryRange("payment_manage", (el("pp-pay-history-from") && el("pp-pay-history-from").value) || "", el("pp-pay-history-to").value || "");
        state.historyPageByTab.payment_manage_history = 1;
        renderCreatedEntriesPanel("payment_manage");
      });
    }
    if (el("pp-pay-history-booking-status")) {
      el("pp-pay-history-booking-status").addEventListener("change", function () {
        setWorkflowStatusFilter("payment_manage", el("pp-pay-history-booking-status").value || "", (el("pp-pay-history-payment-status") && el("pp-pay-history-payment-status").value) || "");
        state.historyPageByTab.payment_manage_history = 1;
        renderCreatedEntriesPanel("payment_manage");
      });
    }
    if (el("pp-pay-history-payment-status")) {
      el("pp-pay-history-payment-status").addEventListener("change", function () {
        setWorkflowStatusFilter("payment_manage", (el("pp-pay-history-booking-status") && el("pp-pay-history-booking-status").value) || "", el("pp-pay-history-payment-status").value || "");
        state.historyPageByTab.payment_manage_history = 1;
        renderCreatedEntriesPanel("payment_manage");
      });
    }
    wrap.querySelectorAll(".pp-view-payment-create").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var jvName = btn.getAttribute("data-jv") || "";
        if (!jvName) return;
        showPaymentEntrySummary(jvName, false);
      });
    });
    wrap.querySelectorAll(".pp-print-payment-create").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var jvName = btn.getAttribute("data-jv") || "";
        if (!jvName) return;
        showPaymentEntrySummary(jvName, true);
      });
    });
    wrap.querySelectorAll(".pp-history-prev").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = String(btn.getAttribute("data-key") || "");
        if (!key) return;
        state.historyPageByTab[key] = Math.max(1, (parseInt(state.historyPageByTab[key] || 1, 10) || 1) - 1);
        renderCreatedEntriesPanel(state.currentTab);
      });
    });
    wrap.querySelectorAll(".pp-history-next").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = String(btn.getAttribute("data-key") || "");
        if (!key) return;
        state.historyPageByTab[key] = (parseInt(state.historyPageByTab[key] || 1, 10) || 1) + 1;
        renderCreatedEntriesPanel(state.currentTab);
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

  function uniqueCreatedSalaryDocs() {
    var map = {};
    (state.rows || []).forEach(function (r) {
      var docName = String((r && r.per_piece_salary) || "").trim();
      if (!docName || !String((r && r.jv_entry_no) || "").trim()) return;
        if (!map[docName]) {
          map[docName] = {
            name: docName,
            po_number: String((r && r.po_number) || "").trim(),
            jv_entry_no: String((r && r.jv_entry_no) || "").trim(),
          from_date: String((r && r.from_date) || "").trim(),
          to_date: String((r && r.to_date) || "").trim(),
          amount: 0,
          booked_amount: 0,
            allowance_amount: 0,
            advance_deduction_amount: 0,
            other_deduction_amount: 0,
            net_salary: 0,
            rows: 0,
            _booked_count: 0,
            _paid_count: 0,
            _partly_paid_count: 0
          };
        }
      var rf = String((r && r.from_date) || "").trim();
      var rt = String((r && r.to_date) || "").trim();
      if (rf && (!map[docName].from_date || rf < map[docName].from_date)) map[docName].from_date = rf;
      if (rt && (!map[docName].to_date || rt > map[docName].to_date)) map[docName].to_date = rt;
      map[docName].amount += num(r.amount);
      map[docName].booked_amount += num(r.booked_amount);
      map[docName].rows += 1;
      if (String(r.booking_status || "") === "Booked") map[docName]._booked_count += 1;
      var payStatus = String(r.payment_status || "");
      if (payStatus === "Paid") map[docName]._paid_count += 1;
      else if (payStatus === "Partly Paid") map[docName]._partly_paid_count += 1;
    });
    Object.keys(map).forEach(function (k) {
      var it = map[k];
      var salaryAmount = num(it.amount);
      var netAmount = num(it.booked_amount) > 0 ? num(it.booked_amount) : salaryAmount;
      it.allowance_amount = Math.max(netAmount - salaryAmount, 0);
      it.advance_deduction_amount = Math.max(salaryAmount - netAmount, 0);
      it.other_deduction_amount = 0;
      it.net_salary = netAmount;
      it.booking_status = it._booked_count >= it.rows ? "Booked" : (it._booked_count > 0 ? "Partly Booked" : "UnBooked");
      if (it._paid_count >= it.rows) it.payment_status = "Paid";
      else if (it._paid_count > 0 || it._partly_paid_count > 0) it.payment_status = "Partly Paid";
      else it.payment_status = "Unpaid";
    });
    return Object.keys(map).sort().reverse().map(function (k) { return map[k]; });
  }

  function parsePaymentRefsJs(text) {
    var refs = [];
    String(text || "").split(";;").forEach(function (part) {
      var bits = String(part || "").split("::");
      if (bits.length < 2) return;
      var jv = String(bits[0] || "").trim();
      var amount = num(bits[1]);
      if (jv && amount > 0) refs.push({ jv: jv, amount: amount });
    });
    return refs;
  }

  function uniqueCreatedPaymentDocs() {
    var map = {};
    (state.rows || []).forEach(function (r) {
      var refs = parsePaymentRefsJs(r.payment_refs || "");
      if (!refs.length && r.payment_jv_no) {
        refs = [{ jv: String(r.payment_jv_no || "").trim(), amount: num(r.paid_amount) }];
      }
      refs.forEach(function (ref) {
        if (!ref.jv) return;
        if (!map[ref.jv]) {
          map[ref.jv] = {
            name: ref.jv,
            from_date: String((r && r.from_date) || "").trim(),
            to_date: String((r && r.to_date) || "").trim(),
            amount: 0,
            rows: 0,
            salary_map: {},
            _booked_count: 0,
            _paid_count: 0,
            _partly_paid_count: 0
          };
        }
        var pf = String((r && r.from_date) || "").trim();
        var pt = String((r && r.to_date) || "").trim();
        if (pf && (!map[ref.jv].from_date || pf < map[ref.jv].from_date)) map[ref.jv].from_date = pf;
        if (pt && (!map[ref.jv].to_date || pt > map[ref.jv].to_date)) map[ref.jv].to_date = pt;
        map[ref.jv].amount += num(ref.amount);
        map[ref.jv].rows += 1;
        if (String(r.booking_status || "") === "Booked") map[ref.jv]._booked_count += 1;
        var payStatus = String(r.payment_status || "");
        if (payStatus === "Paid") map[ref.jv]._paid_count += 1;
        else if (payStatus === "Partly Paid") map[ref.jv]._partly_paid_count += 1;
        var salaryName = String(r.per_piece_salary || "").trim();
        if (salaryName) map[ref.jv].salary_map[salaryName] = 1;
      });
    });
    return Object.keys(map).sort().reverse().map(function (k) {
      var item = map[k];
      item.salary_entries = Object.keys(item.salary_map || {}).sort().reverse();
      item.booking_status = item._booked_count >= item.rows ? "Booked" : (item._booked_count > 0 ? "Partly Booked" : "UnBooked");
      if (item._paid_count >= item.rows) item.payment_status = "Paid";
      else if (item._paid_count > 0 || item._partly_paid_count > 0) item.payment_status = "Partly Paid";
      else item.payment_status = "Unpaid";
      return item;
    });
  }

  function getSalaryCreationEntryRows(entryName, sourceRows) {
    var target = String(entryName || "").trim();
    var map = {};
    (sourceRows || state.entryMeta.recentRows || state.rows || []).forEach(function (r) {
      if (String(r.per_piece_salary || "").trim() !== target) return;
      var emp = String(r.employee || "").trim();
      if (!emp) return;
      if (!map[emp]) {
        map[emp] = {
          employee: emp,
          name1: r.name1 || emp,
          qty: 0,
          amount: 0,
          jv_entry_no: String(r.jv_entry_no || "").trim()
        };
      }
      map[emp].qty += num(r.qty);
      map[emp].amount += num(r.amount);
      if (!map[emp].jv_entry_no && r.jv_entry_no) map[emp].jv_entry_no = String(r.jv_entry_no || "").trim();
    });
    return Object.keys(map).sort().map(function (emp) {
      var item = map[emp];
      item.rate = avgRate(item.qty, item.amount);
      return item;
    });
  }

  function getSalaryEntryAdjustmentMap(entryRows) {
    var jvMap = {};
    (entryRows || []).forEach(function (r) {
      var jvName = String(r.jv_entry_no || "").trim();
      if (jvName) jvMap[jvName] = 1;
    });
    var jvNames = Object.keys(jvMap);
    if (!jvNames.length) return Promise.resolve({});
    return Promise.all(jvNames.map(function (jvName) {
      return getJournalEntryDoc(jvName);
    })).then(function (docs) {
      var byEmp = {};
      function ensureEmp(emp) {
        if (!byEmp[emp]) byEmp[emp] = { advance_deduction: 0, other_deduction: 0, net_amount: 0 };
        return byEmp[emp];
      }
      docs.forEach(function (doc) {
        (doc && doc.accounts || []).forEach(function (acc) {
          var credit = num(acc.credit_in_account_currency || acc.credit);
          if (credit <= 0) return;
          var party = String(acc.party || "").trim();
          var remark = String(acc.user_remark || "").trim();
          var advanceMatch = remark.match(/^Advance Recovery - (.+)$/);
          var deductionMatch = remark.match(/^Salary Deduction - (.+)$/);
          var netMatch = remark.match(/^Net Salary - (.+?)(\\s*\\||$)/);
          var emp = party || (advanceMatch && advanceMatch[1]) || (deductionMatch && deductionMatch[1]) || (netMatch && netMatch[1]) || "";
          emp = String(emp || "").trim();
          if (!emp) return;
          var target = ensureEmp(emp);
          if (advanceMatch || (party && remark.indexOf("Advance Recovery - ") === 0)) target.advance_deduction += credit;
          else if (deductionMatch || (party && remark.indexOf("Salary Deduction - ") === 0)) target.other_deduction += credit;
          else if (netMatch || (party && remark.indexOf("Net Salary - ") === 0)) target.net_amount += credit;
        });
      });
      return byEmp;
    });
  }

  function showSalaryCreationEntrySummary(entryName, printNow) {
    var sourceRows = state.entryMeta.recentRows || state.rows || [];
    var rows = getSalaryCreationEntryRows(entryName, sourceRows);
    if (!rows.length) {
      setSummaryModal("Salary Creation Detail", entryName || "", "<div style='color:#b91c1c;'>No salary rows available for this entry under selected filters.</div>");
      return;
    }
    var first = (sourceRows || []).filter(function (r) {
      return String(r.per_piece_salary || "").trim() === String(entryName || "").trim();
    })[0] || {};
    setSummaryModal("Salary Creation Detail", entryName || "", "<div style='color:#334155;'>Loading salary creation detail...</div>");
    getSalaryEntryAdjustmentMap(rows).then(function (adjustmentMap) {
      var totalQty = 0;
      var totalRate = 0;
      var totalAmount = 0;
      var totalAdvanceBal = 0;
      var totalAdvanceDed = 0;
      var totalAllowance = 0;
      var totalOtherDed = 0;
      var totalNet = 0;
      var gross = 0;
      var html = summaryHeaderHtml("Salary Creation Detail", entryName || "");
      html += "<div class='pp-summary-chips'>"
        + "<span class='pp-summary-chip'>PO Number: " + esc(first.po_number || "-") + "</span>"
        + "<span class='pp-summary-chip'>From: " + esc(first.from_date || "-") + "</span>"
        + "<span class='pp-summary-chip'>To: " + esc(first.to_date || "-") + "</span>"
        + "<span class='pp-summary-chip'>Rows: " + esc(rows.length) + "</span>"
        + "</div>";
      html += "<table class='pp-table'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Salary Amount</th><th>Advance Balance</th><th>Advance Deduction</th><th>Allowance</th><th>Other Deduction</th><th>Net Amount</th></tr></thead><tbody>";
      rows.forEach(function (r) {
        var adj = adjustmentMap[String(r.employee || "").trim()] || {};
        var advanceDeduction = num(adj.advance_deduction);
        var otherDeduction = num(adj.other_deduction);
        var netAmount = num(adj.net_amount);
        if (netAmount <= 0) netAmount = Math.max(num(r.amount) - advanceDeduction - otherDeduction, 0);
        var allowance = Math.max(netAmount - num(r.amount) + advanceDeduction + otherDeduction, 0);
        var advanceBalance = Math.max(num((state.advanceBalances || {})[r.employee]) + advanceDeduction, 0);
        totalQty += num(r.qty);
        totalRate += num(r.rate);
        totalAmount += num(r.amount);
        totalAdvanceBal += advanceBalance;
        totalAdvanceDed += advanceDeduction;
        totalAllowance += allowance;
        totalOtherDed += otherDeduction;
        totalNet += netAmount;
        gross += num(r.amount) + allowance;
        html += "<tr>"
          + "<td>" + esc(r.name1 || r.employee || "") + "</td>"
          + "<td class='num'>" + esc(fmt(r.qty)) + "</td>"
          + "<td class='num'>" + esc(fmt(r.rate)) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(advanceBalance)) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(advanceDeduction)) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(allowance)) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(otherDeduction)) + "</td>"
          + "<td class='num pp-amt-col'>" + esc(fmt(netAmount)) + "</td>"
          + "</tr>";
      });
      html += "<tr class='pp-year-total'>"
        + "<td>Total</td>"
        + "<td class='num'>" + esc(fmt(totalQty)) + "</td>"
        + "<td class='num'>" + esc(fmt(totalRate)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(totalAmount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(totalAdvanceBal)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(totalAdvanceDed)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(totalAllowance)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(totalOtherDed)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(totalNet)) + "</td>"
        + "</tr>";
      html += "</tbody></table>";
      html += "<div class='pp-summary-chips'>"
        + "<span class='pp-summary-chip'>Gross: " + esc(fmt(gross)) + "</span>"
        + "<span class='pp-summary-chip'>Advance Deduction: " + esc(fmt(totalAdvanceDed)) + "</span>"
        + "<span class='pp-summary-chip'>Other Deduction: " + esc(fmt(totalOtherDed)) + "</span>"
        + "<span class='pp-summary-chip'>Net Payable: " + esc(fmt(totalNet)) + "</span>"
        + "</div>";
      setSummaryModal("Salary Creation Detail", entryName || "", html);
      if (printNow) {
        setTimeout(function () { printSummaryModal(); }, 60);
      }
    }).catch(function (e) {
      setSummaryModal("Salary Creation Detail", entryName || "", "<div style='color:#b91c1c;'>Unable to load salary creation detail: " + esc(prettyError(errText(e))) + "</div>");
    });
  }

  function showPaymentEntrySummary(jvName, printNow) {
    var target = String(jvName || "").trim();
    if (!target) return;
    var map = {};
    (state.rows || []).forEach(function (r) {
      var matchedAmount = 0;
      parsePaymentRefsJs(r.payment_refs || "").forEach(function (ref) {
        if (String(ref.jv || "").trim() === target) matchedAmount += num(ref.amount);
      });
      if (!matchedAmount && String(r.payment_jv_no || "").trim() === target) {
        matchedAmount = num(r.paid_amount);
      }
      if (matchedAmount <= 0) return;
      var emp = String(r.employee || "").trim();
      if (!emp) return;
      if (!map[emp]) {
        map[emp] = {
          employee: emp,
          name1: r.name1 || emp,
          booked_amount: 0,
          paid_amount: 0,
          unpaid_amount: 0,
          payment_amount: 0,
          salary_map: {}
        };
      }
      map[emp].booked_amount += num(r.booked_amount);
      map[emp].paid_amount += num(r.paid_amount);
      map[emp].unpaid_amount += num(r.unpaid_amount);
      map[emp].payment_amount += matchedAmount;
      if (r.per_piece_salary) map[emp].salary_map[String(r.per_piece_salary || "").trim()] = 1;
    });
    var rows = Object.keys(map).sort().map(function (emp) {
      var item = map[emp];
      item.status = item.unpaid_amount <= 0 ? "Paid" : (item.paid_amount > 0 ? "Partly Paid" : "Unpaid");
      item.salary_entries = Object.keys(item.salary_map || {}).sort().reverse();
      return item;
    });
    if (!rows.length) {
      setSummaryModal("Payment Entry Detail", target, "<div style='color:#b91c1c;'>No payment rows available for this payment entry under selected filters.</div>");
      return;
    }
    var totalBooked = 0;
    var totalPaid = 0;
    var totalUnpaid = 0;
    var totalPayment = 0;
    var html = summaryHeaderHtml("Payment Entry Detail", target)
      + "<div class='pp-summary-chips'>"
      + "<span class='pp-summary-chip'>Payment Entry: " + esc(target) + "</span>"
      + "<span class='pp-summary-chip'>Employees: " + esc(rows.length) + "</span>"
      + "</div>";
    html += "<table class='pp-table'><thead><tr><th>Employee</th><th>Salary Entries</th><th>Booked Amount</th><th>Paid Amount</th><th>Unpaid Amount</th><th>Payment Amount</th><th>Status</th></tr></thead><tbody>";
    rows.forEach(function (r) {
      totalBooked += num(r.booked_amount);
      totalPaid += num(r.paid_amount);
      totalUnpaid += num(r.unpaid_amount);
      totalPayment += num(r.payment_amount);
      html += "<tr>"
        + "<td>" + esc(r.name1 || r.employee || "") + "</td>"
        + "<td>" + esc((r.salary_entries || []).join(", ")) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.booked_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.paid_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.unpaid_amount)) + "</td>"
        + "<td class='num pp-amt-col'>" + esc(fmt(r.payment_amount)) + "</td>"
        + "<td>" + statusBadgeHtml(r.status || "") + "</td>"
        + "</tr>";
    });
    html += "<tr class='pp-year-total'><td>Total</td><td></td><td class='num pp-amt-col'>" + esc(fmt(totalBooked)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totalPaid)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totalUnpaid)) + "</td><td class='num pp-amt-col'>" + esc(fmt(totalPayment)) + "</td><td></td></tr>";
    html += "</tbody></table>";
    setSummaryModal("Payment Entry Detail", target, html);
    if (printNow) {
      setTimeout(function () { printSummaryModal(); }, 60);
    }
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
      var salaryHistoryFrom = String((el("pp-jv-history-from") && el("pp-jv-history-from").value) || (getWorkflowHistoryRange("salary_creation").from) || "").trim();
      var salaryHistoryTo = String((el("pp-jv-history-to") && el("pp-jv-history-to").value) || (getWorkflowHistoryRange("salary_creation").to) || "").trim();
      var salaryStatus = getWorkflowStatusFilter("salary_creation");
      var salaryBooking = String((el("pp-jv-history-booking-status") && el("pp-jv-history-booking-status").value) || salaryStatus.booking || "").trim();
      var salaryPayment = String((el("pp-jv-history-payment-status") && el("pp-jv-history-payment-status").value) || salaryStatus.payment || "").trim();
      setWorkflowHistoryRange("salary_creation", salaryHistoryFrom, salaryHistoryTo);
      setWorkflowStatusFilter("salary_creation", salaryBooking, salaryPayment);
      var salaryDocs = filterDocsByStatus(filterRowsByDateRange(uniqueCreatedSalaryDocs(), salaryHistoryFrom, salaryHistoryTo), salaryBooking, salaryPayment);
      if (!salaryDocs.length) {
        setCreatedListHtml("<div style='margin-top:8px;color:#64748b;'>No booking JV created in selected filter.</div>");
        return;
      }
      var salaryPage = paginateHistoryRows("salary_creation_history", salaryDocs, 10);
      var html = "";
      if (salaryPage.rows.length) {
        state.entryMeta.selected_salary_history = state.entryMeta.selected_salary_history || {};
        var selectedHistory = state.entryMeta.selected_salary_history;
        var selectedCount = Object.keys(selectedHistory).filter(function (k) { return !!selectedHistory[k]; }).length;
        var tSalary = 0, tAllow = 0, tAdv = 0, tOther = 0, tNet = 0;
        html += "<div style='margin-top:10px;'><strong>Created Salary Entries</strong></div>";
        html += "<div class='pp-jv-grid' style='margin-top:6px;'>"
          + "<label>History From <input type='date' id='pp-jv-history-from' value='" + esc(salaryHistoryFrom || "") + "' /></label>"
          + "<label>History To <input type='date' id='pp-jv-history-to' value='" + esc(salaryHistoryTo || "") + "' /></label>"
          + "<label>Booking Status <select id='pp-jv-history-booking-status'>"
          + "<option value=''>All</option><option value='Booked'" + (salaryBooking === "Booked" ? " selected" : "") + ">Booked</option><option value='UnBooked'" + (salaryBooking === "UnBooked" ? " selected" : "") + ">UnBooked</option><option value='Partly Booked'" + (salaryBooking === "Partly Booked" ? " selected" : "") + ">Partly Booked</option>"
          + "</select></label>"
          + "<label>Payment Status <select id='pp-jv-history-payment-status'>"
          + "<option value=''>All</option><option value='Paid'" + (salaryPayment === "Paid" ? " selected" : "") + ">Paid</option><option value='Unpaid'" + (salaryPayment === "Unpaid" ? " selected" : "") + ">Unpaid</option><option value='Partly Paid'" + (salaryPayment === "Partly Paid" ? " selected" : "") + ">Partly Paid</option>"
          + "</select></label>"
          + "</div>";
        html += "<div class='pp-entry-actions' style='margin-top:6px;'>"
          + "<button type='button' class='btn btn-default btn-xs' id='pp-salary-history-select-page'>Select Page</button>"
          + "<button type='button' class='btn btn-default btn-xs' id='pp-salary-history-clear-selected'>Clear Selected</button>"
          + "<button type='button' class='btn btn-success btn-xs' id='pp-salary-history-pay-selected'>Pay Selected Entry</button>"
          + "<span style='color:#334155;font-size:12px;'>Selected Entries: <strong id='pp-salary-history-selected-count'>" + esc(selectedCount) + "</strong></span>"
          + "</div>";
        html += "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Select</th><th>Salary Entry</th><th>PO Number</th><th>JV Entry</th><th>Total Salary</th><th>Allowance</th><th>Adv Deduction</th><th>Oth Deduction</th><th>Net Salary</th><th>Book</th><th>Pay</th><th>Salary View</th><th>JV View</th></tr></thead><tbody>";
        (salaryPage.rows || []).forEach(function (r) {
          tSalary += num(r.amount);
          tAllow += num(r.allowance_amount);
          tAdv += num(r.advance_deduction_amount);
          tOther += num(r.other_deduction_amount);
          tNet += num(r.net_salary);
          var checked = selectedHistory[r.name] ? " checked" : "";
          var bookedDone = String(r.booking_status || "") === "Booked" ? "<span style='color:#64748b;'>Done</span>" : "<button type='button' class='btn btn-xs btn-primary pp-salary-history-book' data-entry='" + esc(r.name) + "'>Book</button>";
          var payAction = String(r.payment_status || "") === "Paid" ? "<span style='color:#64748b;'>Done</span>" : ("<button type='button' class='btn btn-xs btn-success pp-go-pay-salary-entry' data-entry='" + esc(r.name) + "'>Pay</button>");
          html += "<tr>"
            + "<td><input type='checkbox' class='pp-salary-history-select' data-entry='" + esc(r.name) + "'" + checked + "></td>"
            + "<td><a target='_blank' href='/app/per-piece-salary/" + encodeURIComponent(r.name) + "'>" + esc(r.name) + "</a></td>"
            + "<td>" + esc(r.po_number || "") + "</td>"
            + "<td>" + (r.jv_entry_no ? ("<a target='_blank' href='/app/journal-entry/" + encodeURIComponent(r.jv_entry_no) + "'>" + esc(r.jv_entry_no) + "</a>") : "") + "</td>"
            + "<td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td>"
            + "<td class='num pp-amt-col'>" + esc(fmt(r.allowance_amount)) + "</td>"
            + "<td class='num pp-amt-col'>" + esc(fmt(r.advance_deduction_amount)) + "</td>"
            + "<td class='num pp-amt-col'>" + esc(fmt(r.other_deduction_amount)) + "</td>"
            + "<td class='num pp-amt-col'>" + esc(fmt(r.net_salary)) + "</td>"
            + "<td>" + bookedDone + "</td>"
            + "<td>" + payAction + "</td>"
            + "<td><button type='button' class='btn btn-xs btn-info pp-view-salary-create' data-entry='" + esc(r.name) + "'>View</button></td>"
            + "<td>" + (r.jv_entry_no ? ("<button type='button' class='btn btn-xs btn-info pp-view-jv' data-jv='" + esc(r.jv_entry_no) + "'>View Debit/Credit</button>") : "") + "</td>"
            + "</tr>";
        });
        html += "<tr class='pp-year-total'><td></td><td>Total</td><td></td><td></td><td class='num pp-amt-col'>" + esc(fmt(tSalary)) + "</td><td class='num pp-amt-col'>" + esc(fmt(tAllow)) + "</td><td class='num pp-amt-col'>" + esc(fmt(tAdv)) + "</td><td class='num pp-amt-col'>" + esc(fmt(tOther)) + "</td><td class='num pp-amt-col'>" + esc(fmt(tNet)) + "</td><td></td><td></td><td></td><td></td></tr>";
        html += "</tbody></table>";
        html += historyPagerHtml(salaryPage);
      }
      setCreatedListHtml(html);
      return;
    }
    if (tab === "payment_manage") {
      var paymentHistoryFrom = String((el("pp-pay-history-from") && el("pp-pay-history-from").value) || (getWorkflowHistoryRange("payment_manage").from) || "").trim();
      var paymentHistoryTo = String((el("pp-pay-history-to") && el("pp-pay-history-to").value) || (getWorkflowHistoryRange("payment_manage").to) || "").trim();
      var paymentStatus = getWorkflowStatusFilter("payment_manage");
      var payBooking = String((el("pp-pay-history-booking-status") && el("pp-pay-history-booking-status").value) || paymentStatus.booking || "").trim();
      var payPayment = String((el("pp-pay-history-payment-status") && el("pp-pay-history-payment-status").value) || paymentStatus.payment || "").trim();
      setWorkflowHistoryRange("payment_manage", paymentHistoryFrom, paymentHistoryTo);
      setWorkflowStatusFilter("payment_manage", payBooking, payPayment);
      var payRows = filterDocsByStatus(filterRowsByDateRange(uniqueCreatedPaymentDocs(), paymentHistoryFrom, paymentHistoryTo), payBooking, payPayment);
      if (!payRows.length) {
        setCreatedListHtml("<div style='margin-top:8px;color:#64748b;'>No payment JV created in selected filter.</div>");
        return;
      }
      var payPage = paginateHistoryRows("payment_manage_history", payRows, 10);
      var tPayAmt = 0, tPayRows = 0;
      var phtml = "<div style='margin-top:10px;'><strong>Created Payment JV Entries</strong></div>"
        + "<div class='pp-jv-grid' style='margin-top:6px;'>"
        + "<label>History From <input type='date' id='pp-pay-history-from' value='" + esc(paymentHistoryFrom || "") + "' /></label>"
        + "<label>History To <input type='date' id='pp-pay-history-to' value='" + esc(paymentHistoryTo || "") + "' /></label>"
        + "<label>Booking Status <select id='pp-pay-history-booking-status'>"
        + "<option value=''>All</option><option value='Booked'" + (payBooking === "Booked" ? " selected" : "") + ">Booked</option><option value='UnBooked'" + (payBooking === "UnBooked" ? " selected" : "") + ">UnBooked</option><option value='Partly Booked'" + (payBooking === "Partly Booked" ? " selected" : "") + ">Partly Booked</option>"
        + "</select></label>"
        + "<label>Payment Status <select id='pp-pay-history-payment-status'>"
        + "<option value=''>All</option><option value='Paid'" + (payPayment === "Paid" ? " selected" : "") + ">Paid</option><option value='Unpaid'" + (payPayment === "Unpaid" ? " selected" : "") + ">Unpaid</option><option value='Partly Paid'" + (payPayment === "Partly Paid" ? " selected" : "") + ">Partly Paid</option>"
        + "</select></label>"
        + "</div>"
        + "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Payment Entry</th><th>Salary Entries</th><th>Paid Amount</th><th>Rows</th><th>View</th><th>Print</th><th>Open</th></tr></thead><tbody>";
      (payPage.rows || []).forEach(function (r) {
        tPayAmt += num(r.amount);
        tPayRows += num(r.rows);
        phtml += "<tr><td>" + esc(r.name) + "</td><td>" + esc((r.salary_entries || []).join(", ")) + "</td><td class='num pp-amt-col'>" + esc(fmt(r.amount)) + "</td><td class='num'>" + esc(r.rows) + "</td><td><button type='button' class='btn btn-xs btn-info pp-view-payment-create' data-jv='" + esc(r.name) + "'>View</button></td><td><button type='button' class='btn btn-xs btn-primary pp-print-payment-create' data-jv='" + esc(r.name) + "'>Print</button></td><td><a target='_blank' href='/app/journal-entry/" + encodeURIComponent(r.name) + "'>Open</a></td></tr>";
      });
      phtml += "<tr class='pp-year-total'><td>Total</td><td></td><td class='num pp-amt-col'>" + esc(fmt(tPayAmt)) + "</td><td class='num'>" + esc(fmt(tPayRows)) + "</td><td></td><td></td><td></td></tr>";
      phtml += "</tbody></table>" + historyPagerHtml(payPage);
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

  function getEntryProcessOptions(productName) {
    var product = String(productName || "").trim();
    var options = [];
    (((state.entryMeta.productProcessMap || {})[product]) || []).forEach(function (entry) {
      var process = String((entry && entry.process_type) || "").trim();
      if (process && options.indexOf(process) < 0) options.push(process);
    });
    return options.map(function (process) {
      return { value: process, label: process };
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
      row.rate_manual = false;
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
    // Keep saved/manual rate stable; only auto-fill when row rate is empty.
    if (num(row.rate) <= 0 && num(meta.rate) > 0) row.rate = whole(meta.rate);
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
          row.rate_manual = false;
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
        sales_order: "",
        product: String((item && item.item) || "").trim(),
        process_type: String((item && item.process_type) || "").trim(),
        process_size: String((item && item.process_size) || "").trim() || "No Size",
        qty: 0,
        rate: whole(item && item.rate),
        rate_manual: false,
      };
      return row;
    });
  }

  function loadSelectedItemProcessRows(selectedItem, forceRender) {
    var itemName = String(selectedItem || "").trim();
    if (!itemName || state.entryMeta.load_by_item === false) return;
    if (state.entryMeta.item_fetch_inflight) return;
    state.entryMeta.item_fetch_inflight = 1;
    callApi("per_piece_payroll.api.get_item_process_rows", {
      item: itemName
    }).then(function (rows) {
      var list = (rows || []).filter(function (r) {
        return String((r && r.item) || "").trim() === itemName;
      });
      if (list.length) {
        var keep = (state.entryMeta.masterProcessRows || []).filter(function (r) {
          return String((r && r.item) || "").trim() !== itemName;
        });
        state.entryMeta.masterProcessRows = keep.concat(list);
        if (!state.entryMeta.item_group) {
          state.entryMeta.item_group = String((list[0] && list[0].item_group) || "").trim();
        }
        state.entryRows = list.map(function (item) {
          var itemEmployee = String((item && item.employee) || "").trim();
          var fallbackEmployee = String(state.entryMeta.employee || "").trim();
          var finalEmployee = itemEmployee || fallbackEmployee;
          return {
            employee: finalEmployee,
            name1: String((item && item.employee_name) || ((state.entryMeta.employeeNameMap || {})[finalEmployee]) || "").trim(),
            sales_order: "",
            product: String((item && item.item) || "").trim(),
            process_type: String((item && item.process_type) || "").trim(),
            process_size: String((item && item.process_size) || "").trim() || "No Size",
            qty: 0,
            rate: whole(item && item.rate),
            rate_manual: false
          };
        });
      }
      state.entryMeta.item_fetch_inflight = 0;
      rebuildEntryMetaLookups();
      syncEntryRowsToItemGroup();
      if (forceRender) renderDataEntryTab();
    }).catch(function () {
      state.entryMeta.item_fetch_inflight = 0;
      if (forceRender) renderDataEntryTab();
    });
  }

  function newEntryRow() {
    var employee = String(state.entryMeta.employee || "").trim();
    var row = {
      employee: employee,
      name1: String(((state.entryMeta.employeeNameMap || {})[employee]) || "").trim(),
      sales_order: "",
      product: "",
      process_type: "",
      process_size: "No Size",
      qty: 0,
      rate: 0,
      rate_manual: false
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
    if (!state.entryMeta.from_date) state.entryMeta.from_date = defaultDateWindow().from;
    if (!state.entryMeta.to_date) state.entryMeta.to_date = defaultDateWindow().to;
    if (state.entryMeta.po_number === undefined) state.entryMeta.po_number = "";
    if (state.entryMeta.item_group === undefined) state.entryMeta.item_group = el("pp-item-group") ? (el("pp-item-group").value || "") : "";
    if (state.entryMeta.item === undefined) state.entryMeta.item = "";
    if (state.entryMeta.employee === undefined) state.entryMeta.employee = el("pp-employee") ? (el("pp-employee").value || "") : "";
    if (state.entryMeta.load_by_item === undefined) state.entryMeta.load_by_item = true;
    if (state.entryMeta.skip_auto_populate_once === undefined) state.entryMeta.skip_auto_populate_once = false;
    if (state.entryMeta.edit_name === undefined) state.entryMeta.edit_name = "";
    ensureEntryRows();
    rebuildEntryMetaLookups();
    if (state.entryMeta.skip_auto_populate_once) {
      state.entryMeta.skip_auto_populate_once = false;
    } else {
      populateEntryRowsFromItemGroup();
    }
    var selectedItemAuto = String(state.entryMeta.item || "").trim();
    if (state.entryMeta.load_by_item !== false && selectedItemAuto) {
      var selectedRows = getCurrentGroupItems();
      var hasOnlyPlaceholder = selectedRows.length > 0 && selectedRows.every(function (r) {
        return !String((r && r.process_type) || "").trim() && num((r && r.rate) || 0) <= 0;
      });
      if (!selectedRows.length || hasOnlyPlaceholder) {
        loadSelectedItemProcessRows(selectedItemAuto, true);
      }
    }
    var docs = filterDataEntryDocsByDate(uniqueSalaryDocs((state.entryMeta && state.entryMeta.recentRows) || state.rows || []));
    var employeeOptions = state.entryMeta.employeeOptions || [];
    var itemGroupOptions = state.entryMeta.itemGroupOptions || [];
    var productOptions = state.entryMeta.productOptions || [];
    var employeeNameMap = state.entryMeta.employeeNameMap || {};
    var itemOptions = [];
    (state.entryMeta.masterProcessRows || []).forEach(function (r) {
      var rowGroup = String((r && r.item_group) || "").trim();
      var selectedGroup = String(state.entryMeta.item_group || "").trim();
      if (selectedGroup && rowGroup !== selectedGroup) return;
      var itemName = String((r && r.item) || "").trim();
      if (itemName && itemOptions.indexOf(itemName) < 0) itemOptions.push(itemName);
    });
    itemOptions = itemOptions.map(function (name) { return { value: name, label: name }; });
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
      + "<table class='pp-table' style='margin-top:8px;'><thead><tr><th>Employee</th><th>Employee First Name</th><th>Sales Order</th><th>Product</th><th>Process Type</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Action</th></tr></thead><tbody>";
    state.entryRows.forEach(function (r, idx) {
      var name1 = r.name1 || (employeeNameMap[r.employee || ""] || "");
      html += "<tr>"
        + "<td>" + selectHtml(employeeOptions, r.employee || "", idx, "employee") + "</td>"
        + "<td><input class='pp-pay-input pp-entry-in' data-idx='" + idx + "' data-field='name1' value='" + esc(name1) + "'></td>"
        + "<td><input class='pp-pay-input pp-entry-in' data-idx='" + idx + "' data-field='sales_order' value='" + esc(r.sales_order || "") + "'></td>"
        + "<td>" + selectHtml(productOptions, r.product || "", idx, "product") + "</td>"
        + "<td>" + selectHtml(getEntryProcessOptions(r.product || ""), r.process_type || "", idx, "process_type") + "</td>"
        + "<td>" + readonlyHtml(r.process_size || "No Size") + "</td>"
        + "<td><input class='pp-pay-input pp-entry-in pp-entry-qty' type='number' min='0' step='0.01' inputmode='decimal' data-idx='" + idx + "' data-field='qty' value='" + esc(whole(r.qty)) + "'></td>"
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
      + "<td>Total</td><td></td><td></td><td></td><td></td><td></td>"
      + "<td class='num'>" + esc(fmt(eQty)) + "</td>"
      + "<td class='num'>" + esc(fmt(eRate)) + "</td>"
      + "<td class='num pp-amt-col'>" + esc(fmt(eAmount)) + "</td>"
      + "<td></td>"
      + "</tr>";
    html += "</tbody></table>";
    if (docs.length) {
      state.entryMeta.selected_docs = state.entryMeta.selected_docs || {};
      var selectedDocs = state.entryMeta.selected_docs;
      var docsPage = paginateHistoryRows("data_entry_docs", docs, 10);
      var selectedCount = Object.keys(selectedDocs).filter(function (k) { return !!selectedDocs[k]; }).length;
      html += "<div class='pp-entry-list'><strong>Recent Docs:</strong></div>";
      html += "<div class='pp-jv-grid' style='margin-top:6px;margin-bottom:6px;'>"
        + "<label>History From <input type='date' id='pp-entry-history-from' value='" + esc((state.workflowHistoryDate.data_entry || {}).from || "") + "'></label>"
        + "<label>History To <input type='date' id='pp-entry-history-to' value='" + esc((state.workflowHistoryDate.data_entry || {}).to || "") + "'></label>"
        + "<label>Booking Status <select id='pp-entry-history-booking-status'>"
        + "<option value=''>All</option><option value='Booked'" + (getWorkflowStatusFilter("data_entry").booking === "Booked" ? " selected" : "") + ">Booked</option><option value='UnBooked'" + (getWorkflowStatusFilter("data_entry").booking === "UnBooked" ? " selected" : "") + ">UnBooked</option><option value='Partly Booked'" + (getWorkflowStatusFilter("data_entry").booking === "Partly Booked" ? " selected" : "") + ">Partly Booked</option>"
        + "</select></label>"
        + "<label>Payment Status <select id='pp-entry-history-payment-status'>"
        + "<option value=''>All</option><option value='Paid'" + (getWorkflowStatusFilter("data_entry").payment === "Paid" ? " selected" : "") + ">Paid</option><option value='Unpaid'" + (getWorkflowStatusFilter("data_entry").payment === "Unpaid" ? " selected" : "") + ">Unpaid</option><option value='Partly Paid'" + (getWorkflowStatusFilter("data_entry").payment === "Partly Paid" ? " selected" : "") + ">Partly Paid</option>"
        + "</select></label>"
        + "</div>";
      html += "<div class='pp-entry-actions' style='margin-top:4px;'>"
        + "<button type='button' class='btn btn-default btn-xs' id='pp-entry-doc-select-page'>Select Page</button>"
        + "<button type='button' class='btn btn-default btn-xs' id='pp-entry-doc-clear-select'>Clear Selected</button>"
        + "<button type='button' class='btn btn-primary btn-xs' id='pp-entry-doc-book-selected'>Book Selected</button>"
        + "<button type='button' class='btn btn-success btn-xs' id='pp-entry-doc-pay-selected'>Pay Selected</button>"
        + "<span style='color:#334155;font-size:12px;'>Selected Entries: <strong id='pp-entry-doc-selected-count'>" + esc(selectedCount) + "</strong></span>"
        + "</div>";
      html += "<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Select</th><th>Entry No</th><th>From Date</th><th>To Date</th><th>PO Number</th><th>JV Status</th><th>Pay Status</th><th>Total Amount</th><th>Book</th><th>Pay</th><th>View Detail</th><th>View Entered</th><th>Edit</th><th>Open</th></tr></thead><tbody>";
      var docsTotalAmount = 0;
      (docsPage.rows || []).forEach(function (d) {
        docsTotalAmount += num(d.total_amount);
        var canBook = String(d.booking_status || "") !== "Booked";
        var canPay = String(d.payment_status || "") !== "Paid";
        var bookBtn = canBook ? ("<button type='button' class='btn btn-xs btn-primary pp-entry-book-doc' data-name='" + esc(d.name) + "'>Book</button>") : "<span style='color:#64748b;'>Done</span>";
        var payBtn = canPay ? ("<button type='button' class='btn btn-xs btn-success pp-entry-pay-doc' data-name='" + esc(d.name) + "' data-unpaid='" + esc(d.unpaid_amount) + "'>Pay</button>") : "<span style='color:#64748b;'>Done</span>";
        var checked = selectedDocs[d.name] ? " checked" : "";
        html += "<tr><td><input type='checkbox' class='pp-entry-doc-select' data-name='" + esc(d.name) + "'" + checked + "></td><td>" + esc(d.name) + "</td><td>" + esc(d.from_date) + "</td><td>" + esc(d.to_date) + "</td><td>" + esc(d.po_number) + "</td><td>" + statusBadgeHtml(d.booking_status || "UnBooked") + "</td><td>" + statusBadgeHtml(d.payment_status || "Unpaid") + "</td><td class='num pp-amt-col'>" + esc(fmt(d.total_amount)) + "</td><td>" + bookBtn + "</td><td>" + payBtn + "</td><td><button type='button' class='btn btn-xs btn-info pp-entry-view-doc-detail' data-name='" + esc(d.name) + "'>View Detail</button></td><td><button type='button' class='btn btn-xs btn-primary pp-entry-view-entered' data-name='" + esc(d.name) + "'>View Entered</button></td><td><button type='button' class='btn btn-xs btn-default pp-entry-edit-doc' data-name='" + esc(d.name) + "'>Edit</button></td><td><a target='_blank' href='/app/per-piece-salary/" + encodeURIComponent(d.name) + "'>Open</a></td></tr>";
      });
      html += "<tr class='pp-year-total'><td></td><td>Total</td><td></td><td></td><td></td><td></td><td></td><td class='num pp-amt-col'>" + esc(fmt(docsTotalAmount)) + "</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>";
      html += "</tbody></table>";
      html += historyPagerHtml(docsPage);
    }
    html += "</div>";
    wrap.innerHTML = html;

    var saveBtn = el("pp-entry-save");
    if (saveBtn) saveBtn.addEventListener("click", saveDataEntry);
    var fromInput = el("pp-entry-from-date");
    if (fromInput) fromInput.addEventListener("change", function () { state.entryMeta.from_date = fromInput.value || ""; });
    var toInput = el("pp-entry-to-date");
    if (toInput) toInput.addEventListener("change", function () { state.entryMeta.to_date = toInput.value || ""; });
    var historyFromInput = el("pp-entry-history-from");
    if (historyFromInput) {
      historyFromInput.addEventListener("change", function () {
        setWorkflowHistoryRange("data_entry", historyFromInput.value || "", (state.workflowHistoryDate.data_entry || {}).to || "");
        state.historyPageByTab.data_entry_docs = 1;
        renderDataEntryTab();
      });
    }
    var historyToInput = el("pp-entry-history-to");
    if (historyToInput) {
      historyToInput.addEventListener("change", function () {
        setWorkflowHistoryRange("data_entry", (state.workflowHistoryDate.data_entry || {}).from || "", historyToInput.value || "");
        state.historyPageByTab.data_entry_docs = 1;
        renderDataEntryTab();
      });
    }
    var historyBookingInput = el("pp-entry-history-booking-status");
    if (historyBookingInput) {
      historyBookingInput.addEventListener("change", function () {
        setWorkflowStatusFilter("data_entry", historyBookingInput.value || "", getWorkflowStatusFilter("data_entry").payment || "");
        state.historyPageByTab.data_entry_docs = 1;
        renderDataEntryTab();
      });
    }
    var historyPaymentInput = el("pp-entry-history-payment-status");
    if (historyPaymentInput) {
      historyPaymentInput.addEventListener("change", function () {
        setWorkflowStatusFilter("data_entry", getWorkflowStatusFilter("data_entry").booking || "", historyPaymentInput.value || "");
        state.historyPageByTab.data_entry_docs = 1;
        renderDataEntryTab();
      });
    }
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
        var selectedItem = String(state.entryMeta.item || "").trim();
        if (selectedItem && state.entryMeta.load_by_item !== false) {
          loadSelectedItemProcessRows(selectedItem, true);
          return;
        }
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
      var win = defaultDateWindow();
      state.entryMeta.edit_name = "";
      state.entryMeta.from_date = win.from;
      state.entryMeta.to_date = win.to;
      state.entryMeta.employee = "";
      state.entryMeta.item_group = "";
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
        if (field === "rate") {
          state.entryRows[idx].rate_manual = true;
        }
        if (field === "employee") {
          state.entryRows[idx].name1 = (state.entryMeta.employeeNameMap || {})[state.entryRows[idx].employee || ""] || "";
        }
        if (field === "product" || field === "process_type") {
          var row = state.entryRows[idx];
          row.rate_manual = false;
          row.rate = 0;
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

    wrap.querySelectorAll(".pp-entry-qty").forEach(function (input) {
      input.addEventListener("keydown", function (ev) {
        if (ev.key !== "Tab") return;
        ev.preventDefault();
        var idx = parseInt(input.getAttribute("data-idx") || "0", 10);
        if (state.entryRows[idx]) state.entryRows[idx].qty = whole(input.value);
        var qtyInputs = Array.prototype.slice.call(wrap.querySelectorAll(".pp-entry-qty"));
        var currentIndex = qtyInputs.indexOf(input);
        if (currentIndex < 0) return;
        var nextIndex = ev.shiftKey ? currentIndex - 1 : currentIndex + 1;
        if (nextIndex < 0) nextIndex = 0;
        if (nextIndex >= qtyInputs.length) nextIndex = qtyInputs.length - 1;
        state.entryMeta.focus_qty_index = nextIndex;
        renderDataEntryTab();
      });
    });

    if (state.entryMeta.focus_qty_index !== undefined && state.entryMeta.focus_qty_index !== null) {
      var focusIndex = parseInt(state.entryMeta.focus_qty_index, 10);
      state.entryMeta.focus_qty_index = null;
      var qtyInputs = Array.prototype.slice.call(wrap.querySelectorAll(".pp-entry-qty"));
      var target = qtyInputs[focusIndex];
      if (target) {
        target.focus();
        target.select();
      }
    }

    wrap.querySelectorAll(".pp-entry-edit-doc").forEach(function (btn) {
      btn.addEventListener("click", function () {
        loadEntryDocForEdit(btn.getAttribute("data-name") || "");
      });
    });
    wrap.querySelectorAll(".pp-entry-view-doc-detail").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showPerPieceSummary(btn.getAttribute("data-name") || "");
      });
    });
    wrap.querySelectorAll(".pp-entry-view-entered").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showDataEntryEnteredRows(btn.getAttribute("data-name") || "");
      });
    });
    wrap.querySelectorAll(".pp-entry-doc-select").forEach(function (box) {
      box.addEventListener("change", function () {
        var name = String(box.getAttribute("data-name") || "").trim();
        if (!name) return;
        state.entryMeta.selected_docs = state.entryMeta.selected_docs || {};
        state.entryMeta.selected_docs[name] = !!box.checked;
        var countEl = el("pp-entry-doc-selected-count");
        if (countEl) {
          var c = Object.keys(state.entryMeta.selected_docs).filter(function (k) { return !!state.entryMeta.selected_docs[k]; }).length;
          countEl.textContent = String(c);
        }
      });
    });
    var clearSelectedBtn = el("pp-entry-doc-clear-select");
    if (clearSelectedBtn) {
      clearSelectedBtn.addEventListener("click", function () {
        state.entryMeta.selected_docs = {};
        renderDataEntryTab();
      });
    }
    var selectPageBtn = el("pp-entry-doc-select-page");
    if (selectPageBtn) {
      selectPageBtn.addEventListener("click", function () {
        state.entryMeta.selected_docs = state.entryMeta.selected_docs || {};
        wrap.querySelectorAll(".pp-entry-doc-select").forEach(function (box) {
          var name = String(box.getAttribute("data-name") || "").trim();
          if (!name) return;
          box.checked = true;
          state.entryMeta.selected_docs[name] = true;
        });
        var countEl = el("pp-entry-doc-selected-count");
        if (countEl) {
          var c = Object.keys(state.entryMeta.selected_docs).filter(function (k) { return !!state.entryMeta.selected_docs[k]; }).length;
          countEl.textContent = String(c);
        }
      });
    }
    var bookSelectedBtn = el("pp-entry-doc-book-selected");
    if (bookSelectedBtn) {
      bookSelectedBtn.addEventListener("click", function () {
        var selected = Object.keys(state.entryMeta.selected_docs || {}).filter(function (k) { return !!state.entryMeta.selected_docs[k]; }).sort(compareEntryNoDesc);
        if (!selected.length) {
          showResult(el("pp-entry-result"), "error", "No Entry Selected", "Select one or more entries from Recent Docs first.");
          return;
        }
        state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
        if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
        if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo;
        if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = state.forcedEntryNo;
        if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = selected.join(", ");
        if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = "";
        setWorkflowHistoryRange("salary_creation", "", "");
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='salary_creation']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "salary_creation";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activeSalaryBtn = document.querySelector(".pp-tab[data-tab='salary_creation']");
        if (activeSalaryBtn) activeSalaryBtn.classList.add("active");
        state.excludedEmployees = {};
        setPageForCurrentTab(1);
        loadReport();
      });
    }
    var paySelectedBtn = el("pp-entry-doc-pay-selected");
    if (paySelectedBtn) {
      paySelectedBtn.addEventListener("click", function () {
        var selected = Object.keys(state.entryMeta.selected_docs || {}).filter(function (k) { return !!state.entryMeta.selected_docs[k]; }).sort(compareEntryNoDesc);
        if (!selected.length) {
          showResult(el("pp-entry-result"), "error", "No Entry Selected", "Select one or more entries from Recent Docs first.");
          return;
        }
        state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
        if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
        if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = state.forcedEntryNo;
        if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo;
        if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = selected.join(", ");
        if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = "";
        setWorkflowHistoryRange("payment_manage", "", "");
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "payment_manage";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activePayBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (activePayBtn) activePayBtn.classList.add("active");
        state.paymentExcludedEmployees = {};
        setPageForCurrentTab(1);
        loadReport();
      });
    }
    wrap.querySelectorAll(".pp-entry-book-doc").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var entry = String(btn.getAttribute("data-name") || "").trim();
        state.forcedEntryNo = entry;
        if (el("pp-entry-no")) el("pp-entry-no").value = entry;
        if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = entry;
        if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = entry;
        if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = "";
        setWorkflowHistoryRange("salary_creation", "", "");
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='salary_creation']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "salary_creation";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activeSalaryBtn2 = document.querySelector(".pp-tab[data-tab='salary_creation']");
        if (activeSalaryBtn2) activeSalaryBtn2.classList.add("active");
        state.excludedEmployees = {};
        setPageForCurrentTab(1);
        loadReport();
      });
    });
    wrap.querySelectorAll(".pp-entry-pay-doc").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var entry = String(btn.getAttribute("data-name") || "").trim();
        state.forcedEntryNo = entry;
        if (el("pp-entry-no")) el("pp-entry-no").value = entry;
        if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = entry;
        if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = entry;
        if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = "";
        setWorkflowHistoryRange("payment_manage", "", "");
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var targetBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (targetBtn) targetBtn.classList.add("active");
        switchWorkspaceMode("entry", true);
        state.currentTab = "payment_manage";
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        var activePayBtn2 = document.querySelector(".pp-tab[data-tab='payment_manage']");
        if (activePayBtn2) activePayBtn2.classList.add("active");
        state.paymentExcludedEmployees = {};
        setPageForCurrentTab(1);
        loadReport();
      });
    });
    wrap.querySelectorAll(".pp-history-prev").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = String(btn.getAttribute("data-key") || "");
        if (!key) return;
        state.historyPageByTab[key] = Math.max(1, (parseInt(state.historyPageByTab[key] || 1, 10) || 1) - 1);
        renderDataEntryTab();
      });
    });
    wrap.querySelectorAll(".pp-history-next").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = String(btn.getAttribute("data-key") || "");
        if (!key) return;
        state.historyPageByTab[key] = (parseInt(state.historyPageByTab[key] || 1, 10) || 1) + 1;
        renderDataEntryTab();
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
        var stableRate = lineRate(r.rate, r.qty, r.amount);
        return {
          employee: r.employee || "",
          name1: r.name1 || "",
          sales_order: r.sales_order || "",
          product: r.product || "",
          process_type: r.process_type || "",
          process_size: r.process_size || "No Size",
          qty: whole(r.qty),
          rate: whole(stableRate),
          rate_manual: true
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

    // Always capture the latest typed row values from DOM before save.
    var wrap = el("pp-table-wrap");
    if (wrap) {
      wrap.querySelectorAll(".pp-entry-in").forEach(function (input) {
        var idx = parseInt(input.getAttribute("data-idx") || "0", 10);
        var field = input.getAttribute("data-field") || "";
        if (!state.entryRows[idx]) return;
        if (field === "qty" || field === "rate") {
          state.entryRows[idx][field] = whole(input.value);
          if (field === "rate") state.entryRows[idx].rate_manual = true;
        } else {
          state.entryRows[idx][field] = input.value || "";
        }
      });
    }

    if (!po) {
      showResult(result, "error", "PO Number Required", "Enter PO Number before saving.");
      return;
    }
    var hasManualProductRows = (state.entryRows || []).some(function (r) {
      return whole(r.qty) > 0 && !!String(r.product || "").trim();
    });
    if (loadByItem && !selectedItemSingle && hasManualProductRows) {
      // Allow direct/manual row entry without forcing top item filter selection.
      loadByItem = false;
      state.entryMeta.load_by_item = false;
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
        whole(r.rate),
        String(r.sales_order || "").trim()
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
      resetEntryFiltersToAll();
      state.entryRows = [newEntryRow()];
      state.entryMeta.edit_name = "";
      state.entryMeta.employee = "";
      state.entryMeta.item_group = "";
      state.entryMeta.item = "";
      state.entryMeta.po_number = "";
      state.entryMeta.load_by_item = true;
      state.entryMeta.skip_auto_populate_once = true;
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

  function toggleEntryScreenMode() {
    var wrap = document.querySelector(".pp-wrap");
    if (!wrap) return;
    var tab = String(state.currentTab || "");
    var isEntryScreen = tab === "data_entry" || tab === "salary_creation" || tab === "payment_manage";
    if (isEntryScreen) wrap.classList.add("pp-entry-screen");
    else wrap.classList.remove("pp-entry-screen");
  }

  function toggleEmployeeSummaryDetailControl() {
    var wrap = el("pp-employee-summary-detail-wrap");
    var input = el("pp-employee-summary-detail");
    if (!wrap || !input) return;
    wrap.style.display = state.currentTab === "employee_summary" ? "" : "none";
    input.checked = !!state.employeeSummaryDetail;
  }

  function renderCurrentTab() {
    var currentTabName = String(state.currentTab || "");
    var headerFilterOpts = {};
    if (currentTabName === "data_entry" || currentTabName === "salary_creation" || currentTabName === "payment_manage") {
      headerFilterOpts.ignore_date_filter = true;
      headerFilterOpts.ignore_po_filter = true;
      headerFilterOpts.ignore_entry_filter = true;
    }
    var rows = getRowsByHeaderFilters(state.rows || [], headerFilterOpts);
    var cols = [];
    var outRows = [];
    var paged = null;
    var skipColumnSearch = false;
    toggleWorkflowCards();
    toggleEmployeeSummaryDetailControl();
    toggleEntryScreenMode();
    refreshWorkflowEntrySelectors();

    if (state.currentTab === "all") {
      cols = [
        { fieldname: "per_piece_salary", label: "Entry No" },
        { fieldname: "from_date", label: "From Date" },
        { fieldname: "to_date", label: "To Date" },
        { fieldname: "po_number", label: "PO Number" },
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
      outRows.sort(function (a, b) {
        return String(b.per_piece_salary || "").localeCompare(String(a.per_piece_salary || ""));
      });
    } else if (state.currentTab === "data_entry") {
      renderDataEntryTab();
      state.lastTabRender = { mode: "dom", columns: [], rows: [] };
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
      state.lastTabRender = {
        mode: "table",
        columns: [
          { fieldname: "name1", label: "Employee" },
          { fieldname: "qty", label: "Qty", numeric: true },
          { fieldname: "rate", label: "Rate", numeric: true },
          { fieldname: "amount", label: "Salary Amount", numeric: true },
          { fieldname: "advance_balance", label: "Advance Balance", numeric: true },
          { fieldname: "advance_deduction", label: "Advance Deduction", numeric: true },
          { fieldname: "allowance", label: "Allowance", numeric: true },
          { fieldname: "other_deduction", label: "Other Deduction", numeric: true },
          { fieldname: "net_amount", label: "Net Amount", numeric: true }
        ],
        rows: outRows
      };
      filterRenderedTablesBySearch();
      var t = getAdjustedTotals();
      el("pp-totals").innerHTML = "<span>Gross: " + fmt(t.gross_amount) + "</span>"
        + "<span>Advance Deduction: " + fmt(t.advance_deduction_amount) + "</span>"
        + "<span>Other Deduction: " + fmt(t.other_deduction_amount) + "</span>"
        + "<span>Net Payable: " + fmt(t.net_payable_amount) + "</span>";
      var msg = outRows.length + " employee row(s) for salary creation";
      if (state.forcedEntryNo) {
        var s = getEntrySummary(state.forcedEntryNo);
        if (s) {
          msg += " | Entry " + state.forcedEntryNo + " | Date " + (s.from_date || "-") + " to " + (s.to_date || "-")
            + " | Booking " + s.booking_status + " | Payment " + s.payment_status;
        }
      }
      el("pp-msg").textContent = msg;
      renderPagination(paged);
      renderCreatedEntriesPanel("salary_creation");
      refreshWorkflowEntrySelectors();
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
      state.lastTabRender = {
        mode: "table",
        columns: [
          { fieldname: "name1", label: "Employee" },
          { fieldname: "booked_amount", label: "Booked", numeric: true },
          { fieldname: "paid_amount", label: "Paid", numeric: true },
          { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
          { fieldname: "payment_amount", label: "Payment Amount", numeric: true },
          { fieldname: "payment_status", label: "Payment Status" }
        ],
        rows: outRows.map(function (r) {
          return {
            name1: r.name1 || r.employee || "",
            booked_amount: r.booked_amount,
            paid_amount: r.paid_amount,
            unpaid_amount: r.unpaid_amount,
            payment_amount: r.payment_amount,
            payment_status: r.payment_status
          };
        })
      };
      filterRenderedTablesBySearch();
      var p = getPaymentTotals();
      el("pp-totals").innerHTML = "<span>Booked: " + fmt(p.booked) + "</span>"
        + "<span>Paid: " + fmt(p.paid) + "</span>"
        + "<span>Unpaid: " + fmt(p.unpaid) + "</span>"
        + "<span>Payment This JV: " + fmt(p.payment) + "</span>";
      var pmsg = outRows.length + " employee row(s) pending payment (paid rows hidden)";
      if (state.forcedEntryNo) {
        var ps = getEntrySummary(state.forcedEntryNo);
        if (ps) {
          pmsg += " | Entry " + state.forcedEntryNo + " | Date " + (ps.from_date || "-") + " to " + (ps.to_date || "-")
            + " | Booking " + ps.booking_status + " | Payment " + ps.payment_status;
        }
      }
      el("pp-msg").textContent = pmsg;
      renderPagination(paged);
      renderCreatedEntriesPanel("payment_manage");
      refreshWorkflowEntrySelectors();
      refreshPaymentAmounts();
      refreshJVAmountsFromAdjustments();
      return;
    } else if (state.currentTab === "advances") {
      cols = [
        { fieldname: "name1", label: "Employee Name" },
        { fieldname: "employee", label: "Employee ID" },
        { fieldname: "branch", label: "Branch" },
        { fieldname: "closing_balance", label: "Closing Balance", numeric: true }
      ];
      outRows = buildAdvanceRows(rows);
    } else if (state.currentTab === "employee_summary") {
      outRows = buildEmployeeSummaryReportRows(rows);
      paged = paginateRows(outRows);
      renderEmployeeSummaryTable(paged.rows);
      state.lastTabRender = {
        mode: "table",
        columns: [
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
        ],
        rows: outRows
      };
      filterRenderedTablesBySearch();
      el("pp-msg").textContent = outRows.length + " row(s)";
      renderPagination(paged);
      var est = { qty: 0, amount: 0 };
      outRows.forEach(function (r) {
        est.qty += num(r.qty);
        est.amount += num(r.amount);
      });
      el("pp-totals").innerHTML = "<span>Total Qty: " + fmt(est.qty) + "</span><span>Total Amount: " + fmt(est.amount) + "</span>";
      renderCreatedEntriesPanel("employee_summary");
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    } else if (state.currentTab === "salary_slip") {
      outRows = rows;
      paged = paginateRows(outRows);
      renderSalarySlipTable(paged.rows);
      state.lastTabRender = { mode: "dom", columns: [], rows: [] };
      filterRenderedTablesBySearch();
      el("pp-msg").textContent = "Employee salary slip detail from current filters";
      renderPagination(paged);
      var slipTotals = { qty: 0, amount: 0 };
      outRows.forEach(function (r) {
        slipTotals.qty += num(r.qty);
        slipTotals.amount += num(r.amount);
      });
      el("pp-totals").innerHTML = "<span>Total Qty: " + fmt(slipTotals.qty) + "</span><span>Total Amount: " + fmt(slipTotals.amount) + "</span>";
      renderCreatedEntriesPanel("salary_slip");
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
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
        { fieldname: "per_piece_salary", label: "Entry No", summary_link: true },
        { fieldname: "product", label: "Product" },
        { fieldname: "process_type", label: "Process" },
        { fieldname: "process_size", label: "Size" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "unbooked_amount", label: "Unbooked", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = buildProductSummaryDetailRows(rows || []);
    } else if (state.currentTab === "process_product") {
      cols = [
        { fieldname: "per_piece_salary", label: "Entry No", summary_link: true },
        { fieldname: "process_type", label: "Process" },
        { fieldname: "process_size", label: "Size" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "unbooked_amount", label: "Unbooked", numeric: true },
        { fieldname: "booked_amount", label: "Booked", numeric: true },
        { fieldname: "paid_amount", label: "Paid", numeric: true },
        { fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" }
      ];
      outRows = buildProcessSummaryRows(rows || []);
    } else if (state.currentTab === "per_piece_salary") {
      cols = [
        { fieldname: "per_piece_salary", label: "Entry No" },
        { fieldname: "po_number", label: "PO Number" },
        { fieldname: "product", label: "Item" },
        { fieldname: "process_type", label: "Process" },
        { fieldname: "process_size", label: "Size" },
        { fieldname: "qty", label: "Qty", numeric: true },
        { fieldname: "rate", label: "Rate", numeric: true },
        { fieldname: "amount", label: "Amount", numeric: true },
        { fieldname: "booking_status", label: "Booking Status" },
        { fieldname: "payment_status", label: "Payment Status" },
        { fieldname: "jv_entry_no", label: "Salary JV No" },
        { fieldname: "payment_jv_no", label: "Payment JV No" }
      ];
      outRows = buildEmployeeItemWiseReportRows(rows || []);
    } else if (state.currentTab === "po_number") {
      cols = [
        { fieldname: "po_number", label: "PO Number", po_summary_link: true },
        { fieldname: "po_view", label: "View", po_action: "view" },
        { fieldname: "po_print_process", label: "Print Process Wise", po_action: "print_process" },
        { fieldname: "po_print_product", label: "Print Product Wise", po_action: "print_product" },
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
      outRows.sort(function (a, b) {
        return String(b.po_number || "").localeCompare(String(a.po_number || ""));
      });
    } else if (state.currentTab === "po_detail_all") {
      outRows = (rows || []).slice();
      renderPoDetailPrintTab(outRows);
      state.lastTabRender = { mode: "dom", columns: [], rows: [] };
      filterRenderedTablesBySearch();
      renderPagination(null);
      var pdQty = 0;
      var pdAmount = 0;
      outRows.forEach(function (r) { pdQty += num(r.qty); pdAmount += num(r.amount); });
      el("pp-totals").innerHTML = "<span>Total Qty: " + fmt(pdQty) + "</span><span>Total Amount: " + fmt(pdAmount) + "</span>";
      el("pp-msg").textContent = outRows.length + " row(s) in PO Detail Print";
      renderCreatedEntriesPanel(state.currentTab);
      refreshJVAmountsFromAdjustments();
      refreshPaymentAmounts();
      return;
    }

    if (!skipColumnSearch) {
      outRows = filterRowsByColumns(outRows, cols);
    }
    state.lastTabRender = { mode: "table", columns: cols.slice(), rows: outRows.slice() };
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
      var totalAdvance = 0;
      outRows.forEach(function (r) {
        totalAdvance += num(r.closing_balance || r.advance_balance);
      });
      el("pp-totals").innerHTML = "<span>Total Closing: " + fmt(totalAdvance) + "</span>";
      el("pp-msg").textContent = outRows.length + " employee row(s) in advances";
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
    outRows.forEach(function (r) {
      if (!r || r._group_header || r._is_total) return;
      totalQty += num(r.qty);
      totalAmount += num(r.amount);
    });
    el("pp-totals").innerHTML = "<span>Total Qty: " + fmt(totalQty) + "</span><span>Total Amount: " + fmt(totalAmount) + "</span>";
    el("pp-msg").textContent = outRows.length + " row(s)";
    renderCreatedEntriesPanel(state.currentTab);
    refreshJVAmountsFromAdjustments();
    refreshPaymentAmounts();
  }

  function loadReport() {
    setPageForCurrentTab(1);
    el("pp-msg").textContent = "Loading...";
    var args = getReportArgs();
    if (state.currentTab === "data_entry" || state.currentTab === "salary_creation" || state.currentTab === "payment_manage") {
      args.from_date = "2000-01-01";
      args.to_date = "2099-12-31";
      args.employee = "";
      args.item_group = "";
      args.product = "";
      args.process_type = "";
      args.booking_status = "";
      args.payment_status = "";
      args.po_number = "";
      args.entry_no = "";
    } else if (String(args.entry_no || "").trim()) {
      // When a specific entry is selected in reporting, do not hide it behind date filter.
      args.from_date = "2000-01-01";
      args.to_date = "2099-12-31";
    }
    callApi("get_per_piece_salary_report", args).then(function (msg) {
      state.rows = (msg && msg.data) || [];
      applyReportRateProcessFix(state.rows);
      normalizeReportStatusValues(state.rows);
      state.columns = (msg && msg.columns) || [];
      refreshHeaderFilterOptions();
      return loadAllRowsForRecentDocs().then(function () {
        return loadAdvancesFromGL();
      }).catch(function (e) {
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
    Promise.all([
      callGetList("Account", ["name"], { company: company, is_group: 0, root_type: "Liability" }),
      callGetList("Account", ["name"], { company: company, is_group: 0, root_type: "Expense" })
    ]).then(function (parts) {
      var rows = []
        .concat((parts && parts[0]) || [])
        .concat((parts && parts[1]) || []);
      var seen = {};
      var merged = [];
      rows.forEach(function (r) {
        var name = String((r && r.name) || "").trim();
        if (!name || seen[name]) return;
        seen[name] = true;
        merged.push({ name: name });
      });
      merged.sort(function (a, b) { return String(a.name || "").localeCompare(String(b.name || "")); });
      setOptions(el("pp-jv-deduction-account"), merged, "name", "name", "Select Deduction Account");
      selectPreferred(el("pp-jv-deduction-account"), merged, ["deduction", "eobi", "payable", "allowance", "salary", "expense", "employee"]);
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
    Promise.all([
      callGetList("Account", ["name"], { company: company, is_group: 0, account_type: "Bank" }),
      callGetList("Account", ["name"], { company: company, is_group: 0, account_type: "Cash" })
    ]).then(function (parts) {
      var rows = []
        .concat((parts && parts[0]) || [])
        .concat((parts && parts[1]) || []);
      var seen = {};
      var merged = [];
      rows.forEach(function (r) {
        var name = String((r && r.name) || "").trim();
        if (!name || seen[name]) return;
        seen[name] = true;
        merged.push({ name: name });
      });
      merged.sort(function (a, b) { return String(a.name || "").localeCompare(String(b.name || "")); });
      setOptions(el("pp-pay-paid-from-account"), merged, "name", "name", "Select Bank/Cash Account");
      selectPreferred(el("pp-pay-paid-from-account"), merged, ["cash", "bank"]);
    }).catch(function (e) { console.error(e); });
  }

  function getJVArgs(dryRun) {
    var args = getReportArgs();
    var range = getWorkflowHistoryRange("salary_creation");
    args.from_date = range.from || "2000-01-01";
    args.to_date = range.to || "2099-12-31";
    args.employee = "";
    args.item_group = "";
    args.product = "";
    args.process_type = "";
    args.po_number = "";
    args.company = el("pp-jv-company").value || "";
    args.posting_date = el("pp-jv-posting-date").value || args.to_date || "";
    args.expense_account = el("pp-jv-expense-account").value || "";
    args.allowance_account = el("pp-jv-allowance-account").value || "";
    args.payable_account = el("pp-jv-payable-account").value || "";
    args.advance_account = el("pp-jv-advance-account").value || "";
    args.deduction_account = el("pp-jv-deduction-account").value || "";
    args.header_remark = el("pp-jv-remark").value || "";
    var lines = [];
    var adjustedRows = getAdjustedEmployeeRows();
    var adjustedMap = {};
    adjustedRows.forEach(function (r) {
      adjustedMap[String(r.employee || "")] = r;
    });
    Object.keys(state.adjustments || {}).sort().forEach(function (emp) {
      var a = state.adjustments[emp] || {};
      var ar = adjustedMap[emp] || {};
      lines.push([
        String(emp || "").trim(),
        whole(a.allowance),
        whole(a.advance_deduction),
        whole(a.other_deduction),
        whole(ar.advance_balance || a.advance_balance || 0)
      ].join("::"));
    });
    args.employee_adjustments = lines.join(";;");
    args.exclude_employees = Object.keys(state.excludedEmployees || {}).filter(function (k) { return !!state.excludedEmployees[k]; }).join(",");
    args.employee_wise = 1;
    var selectedEntries = parseEntryNoList((el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || "");
    if (args.entry_no && selectedEntries.indexOf(String(args.entry_no)) < 0) selectedEntries.unshift(String(args.entry_no));
    args.entry_nos = selectedEntries.join(",");
    args.dry_run = dryRun ? 1 : 0;
    return args;
  }

  function getPaymentJVArgs(dryRun) {
    var args = getReportArgs();
    var range = getWorkflowHistoryRange("payment_manage");
    args.from_date = range.from || "2000-01-01";
    args.to_date = range.to || "2099-12-31";
    args.employee = "";
    args.item_group = "";
    args.product = "";
    args.process_type = "";
    args.po_number = "";
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
    var selectedEntries = parseEntryNoList((el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || "");
    if (args.entry_no && selectedEntries.indexOf(String(args.entry_no)) < 0) selectedEntries.unshift(String(args.entry_no));
    args.entry_nos = selectedEntries.join(",");
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
    confirmActionModal("Post Payment JV", "Post Payment JV for selected employee amounts?", "Post JV").then(function (ok) {
      if (!ok) return;
      var result = el("pp-pay-result");
      result.style.color = "#334155";
      result.textContent = "Posting payment JV...";
      callApi("create_per_piece_salary_payment_jv", getPaymentJVArgs(false)).then(function (msg) {
        setPaymentAmounts(msg.debit_amount, msg.credit_amount, 0);
        var link = "<a href='/app/journal-entry/" + encodeURIComponent(msg.journal_entry) + "' target='_blank'>" + esc(msg.journal_entry) + "</a>";
        result.style.color = "#0f766e";
        result.innerHTML = "Payment JV Posted: " + link + "<br>Amount: " + esc(fmt(msg.payment_amount))
          + " <button type='button' class='btn btn-xs btn-info pp-view-jv' data-jv='" + esc(msg.journal_entry) + "'>View Debit/Credit</button>";
        notifyActionResult("success", "Payment JV Posted", "Payment JV has been posted successfully.", msg.journal_entry);
        renderJournalEntryInline(result, msg.journal_entry);
        result.querySelectorAll(".pp-view-jv").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var jv = btn.getAttribute("data-jv") || "";
            if (jv) showJournalEntrySummary(jv);
          });
        });
        state.paymentAdjustments = {};
        state.paymentExcludedEmployees = {};
        resetEntryFiltersToAll();
        loadReport();
      }).catch(function (e) {
        showResult(result, "error", "Payment Post Failed", prettyError(errText(e)));
        notifyActionResult("error", "Payment JV Failed", prettyError(errText(e)), "");
        console.error(e);
      });
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
      state.paymentAdjustments = {};
      state.paymentExcludedEmployees = {};
      loadReport();
    }).catch(function (e) {
      showResult(result, "error", "Payment Cancel Failed", prettyError(errText(e)));
      console.error(e);
    });
  }

  function createJV() {
    confirmActionModal("Post Salary JV", "Post JV Entry for current unposted rows?", "Post JV").then(function (ok) {
      if (!ok) return;
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
          + " <button type='button' class='btn btn-xs btn-info pp-view-jv' data-jv='" + esc(msg.journal_entry) + "'>View Debit/Credit</button>";
        notifyActionResult("success", "Salary JV Posted", "Salary JV has been posted successfully.", msg.journal_entry);
        renderJournalEntryInline(result, msg.journal_entry);
        result.querySelectorAll(".pp-view-jv").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var jv = btn.getAttribute("data-jv") || "";
            if (jv) showJournalEntrySummary(jv);
          });
        });
        resetEntryFiltersToAll();
        loadReport();
      }).catch(function (e) {
        showResult(result, "error", "JV Post Failed", prettyError(errText(e)));
        notifyActionResult("error", "Salary JV Failed", prettyError(errText(e)), "");
        console.error(e);
      });
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

  function isEntryTab(tabName) {
    return ["data_entry", "salary_creation", "payment_manage"].indexOf(String(tabName || "").trim()) >= 0;
  }

  function switchWorkspaceMode(mode, skipReload) {
    state.workspaceMode = (mode === "entry") ? "entry" : "reporting";
    var filters = document.querySelector(".pp-filters");
    if (filters) filters.style.display = state.workspaceMode === "entry" ? "none" : "";
    if (el("pp-workspace-reporting")) el("pp-workspace-reporting").classList.toggle("active", state.workspaceMode === "reporting");
    if (el("pp-workspace-entry")) el("pp-workspace-entry").classList.toggle("active", state.workspaceMode === "entry");
    document.querySelectorAll(".pp-tab").forEach(function (btn) {
      var ws = String(btn.getAttribute("data-workspace") || "reporting");
      btn.style.display = ws === state.workspaceMode ? "" : "none";
    });
    if (state.workspaceMode === "entry" && !isEntryTab(state.currentTab)) state.currentTab = "data_entry";
    if (state.workspaceMode === "reporting" && isEntryTab(state.currentTab)) state.currentTab = "all";
    document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
    var activeBtn = document.querySelector(".pp-tab[data-tab='" + state.currentTab + "']");
    if (activeBtn) activeBtn.classList.add("active");
    if (!skipReload) {
      setPageForCurrentTab(1);
      loadReport();
    }
  }

  function initTabs() {
    if (el("pp-workspace-reporting")) {
      el("pp-workspace-reporting").addEventListener("click", function () {
        switchWorkspaceMode("reporting", false);
      });
    }
    if (el("pp-workspace-entry")) {
      el("pp-workspace-entry").addEventListener("click", function () {
        switchWorkspaceMode("entry", false);
      });
    }

    document.querySelectorAll(".pp-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var ws = String(btn.getAttribute("data-workspace") || "reporting");
        state.workspaceMode = ws === "entry" ? "entry" : "reporting";
        switchWorkspaceMode(state.workspaceMode, true);
        document.querySelectorAll(".pp-tab").forEach(function (x) { x.classList.remove("active"); });
        btn.classList.add("active");
        state.currentTab = btn.getAttribute("data-tab");
        setPageForCurrentTab(1);
        loadReport();
      });
    });
    switchWorkspaceMode("entry", true);
  }

  function setDefaultDates() {
    var win = defaultDateWindow();
    var from = win.from;
    var to = win.to;
    try {
      state.employeeSummaryDetail = (window.localStorage.getItem("pp_employee_summary_detail") || "") === "1";
    } catch (e) {}
    el("pp-from-date").value = from;
    el("pp-to-date").value = to;
    // Workflow tabs are independent from main report date filters.
    setWorkflowHistoryRange("data_entry", "", "");
    setWorkflowHistoryRange("salary_creation", "", "");
    setWorkflowHistoryRange("payment_manage", "", "");
    setWorkflowStatusFilter("data_entry", "", "");
    setWorkflowStatusFilter("salary_creation", "", "");
    setWorkflowStatusFilter("payment_manage", "", "");
    if (el("pp-jv-history-from")) el("pp-jv-history-from").value = "";
    if (el("pp-jv-history-to")) el("pp-jv-history-to").value = "";
    if (el("pp-pay-history-from")) el("pp-pay-history-from").value = "";
    if (el("pp-pay-history-to")) el("pp-pay-history-to").value = "";
    el("pp-jv-posting-date").value = to;
    el("pp-pay-posting-date").value = to;
    el("pp-jv-employee-wise").checked = true;
    el("pp-jv-employee-wise").disabled = true;
  }

  function defaultDateWindow() {
    var now = new Date();
    var to = now.toISOString().slice(0, 10);
    var start = new Date(now.getTime());
    start.setDate(start.getDate() - 16);
    var from = start.toISOString().slice(0, 10);
    return { from: from, to: to };
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
  if (el("pp-sync-status-btn")) {
    el("pp-sync-status-btn").addEventListener("click", function () {
      var msgEl = el("pp-msg");
      if (msgEl) msgEl.textContent = "Force syncing status from JV links...";
      callApi("per_piece_payroll.api.force_sync_per_piece_status", {}).then(function (res) {
        var checked = num(res && res.rows_checked);
        var updated = num(res && res.rows_updated);
        if (msgEl) msgEl.textContent = "Status sync done. Checked: " + fmt(checked) + " | Updated: " + fmt(updated);
        loadReport();
      }).catch(function (e) {
        var err = prettyError(errText(e));
        // Fallback for servers where Python API method is not deployed yet.
        if (String(err).indexOf("force_sync_per_piece_status") >= 0) {
          callApi("get_per_piece_salary_report", { from_date: "2000-01-01", to_date: "2099-12-31" })
            .then(function () {
              if (msgEl) msgEl.textContent = "Fallback sync done via report refresh. Please update app code on server for full sync API.";
              loadReport();
            })
            .catch(function () {
              if (msgEl) msgEl.textContent = "Status sync failed: " + err;
            });
          return;
        }
        if (msgEl) msgEl.textContent = "Status sync failed: " + err;
      });
    });
  }
  if (el("pp-print-tab-btn")) {
    el("pp-print-tab-btn").addEventListener("click", printCurrentTabReport);
  }
  if (el("pp-item-group")) {
    el("pp-item-group").addEventListener("change", function () {
      refreshTopProductOptions();
      renderCurrentTab();
    });
  }
  if (el("pp-booking-status")) {
    el("pp-booking-status").addEventListener("change", function () { setPageForCurrentTab(1); renderCurrentTab(); });
  }
  if (el("pp-payment-status")) {
    el("pp-payment-status").addEventListener("change", function () { setPageForCurrentTab(1); renderCurrentTab(); });
  }
  if (el("pp-po-number")) {
    el("pp-po-number").addEventListener("change", function () { setPageForCurrentTab(1); renderCurrentTab(); });
  }
  if (el("pp-entry-no")) {
    el("pp-entry-no").addEventListener("change", function () {
      var v = String(el("pp-entry-no").value || "").trim();
      state.forcedEntryNo = v;
      if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = v;
      if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = v;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-jv-entry-filter")) {
    el("pp-jv-entry-filter").addEventListener("change", function () {
      var v = String(el("pp-jv-entry-filter").value || "").trim();
      state.forcedEntryNo = v;
      state.excludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = v;
      if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = v;
      if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = v;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-jv-entry-multi")) {
    el("pp-jv-entry-multi").addEventListener("change", function () {
      var list = parseEntryNoList(el("pp-jv-entry-multi").value || "");
      var single = list.length === 1 ? list[0] : "";
      state.forcedEntryNo = single;
      state.excludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = single;
      if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = single;
      if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = single;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-jv-entry-clear")) {
    el("pp-jv-entry-clear").addEventListener("click", function () {
      resetEntryFiltersToAll();
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-jv-entry-add")) {
    el("pp-jv-entry-add").addEventListener("click", function () {
      var current = parseEntryNoList((el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || "");
      var addOne = String((el("pp-jv-entry-filter") && el("pp-jv-entry-filter").value) || "").trim();
      if (!addOne) return;
      if (current.indexOf(addOne) < 0) current.push(addOne);
      if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = current.join(", ");
      state.forcedEntryNo = current.length === 1 ? current[0] : "";
      state.excludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-jv-entry-remove")) {
    el("pp-jv-entry-remove").addEventListener("click", function () {
      var current = parseEntryNoList((el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || "");
      var removeOne = String((el("pp-jv-entry-filter") && el("pp-jv-entry-filter").value) || "").trim();
      if (!removeOne) return;
      current = current.filter(function (x) { return x !== removeOne; });
      if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = current.join(", ");
      state.forcedEntryNo = current.length === 1 ? current[0] : "";
      state.excludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
      if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo;
      if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = state.forcedEntryNo;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-jv-entry-refresh")) {
    el("pp-jv-entry-refresh").addEventListener("click", function () {
      setPageForCurrentTab(1);
      loadReport();
    });
  }
  if (el("pp-jv-history-from")) {
    el("pp-jv-history-from").addEventListener("change", function () {
      setWorkflowHistoryRange("salary_creation", el("pp-jv-history-from").value || "", (el("pp-jv-history-to") && el("pp-jv-history-to").value) || "");
      state.historyPageByTab.salary_creation_history = 1;
      renderCreatedEntriesPanel("salary_creation");
    });
  }
  if (el("pp-jv-history-to")) {
    el("pp-jv-history-to").addEventListener("change", function () {
      setWorkflowHistoryRange("salary_creation", (el("pp-jv-history-from") && el("pp-jv-history-from").value) || "", el("pp-jv-history-to").value || "");
      state.historyPageByTab.salary_creation_history = 1;
      renderCreatedEntriesPanel("salary_creation");
    });
  }
  if (el("pp-pay-entry-filter")) {
    el("pp-pay-entry-filter").addEventListener("change", function () {
      var v = String(el("pp-pay-entry-filter").value || "").trim();
      state.forcedEntryNo = v;
      state.paymentExcludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = v;
      if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = v;
      if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = v;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-pay-entry-multi")) {
    el("pp-pay-entry-multi").addEventListener("change", function () {
      var list = parseEntryNoList(el("pp-pay-entry-multi").value || "");
      var single = list.length === 1 ? list[0] : "";
      state.forcedEntryNo = single;
      state.paymentExcludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = single;
      if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = single;
      if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = single;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-pay-entry-clear")) {
    el("pp-pay-entry-clear").addEventListener("click", function () {
      resetEntryFiltersToAll();
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-pay-entry-add")) {
    el("pp-pay-entry-add").addEventListener("click", function () {
      var current = parseEntryNoList((el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || "");
      var addOne = String((el("pp-pay-entry-filter") && el("pp-pay-entry-filter").value) || "").trim();
      if (!addOne) return;
      if (current.indexOf(addOne) < 0) current.push(addOne);
      if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = current.join(", ");
      state.forcedEntryNo = current.length === 1 ? current[0] : "";
      state.paymentExcludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-pay-entry-remove")) {
    el("pp-pay-entry-remove").addEventListener("click", function () {
      var current = parseEntryNoList((el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || "");
      var removeOne = String((el("pp-pay-entry-filter") && el("pp-pay-entry-filter").value) || "").trim();
      if (!removeOne) return;
      current = current.filter(function (x) { return x !== removeOne; });
      if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = current.join(", ");
      state.forcedEntryNo = current.length === 1 ? current[0] : "";
      state.paymentExcludedEmployees = {};
      if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
      if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = state.forcedEntryNo;
      if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo;
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
  }
  if (el("pp-pay-entry-refresh")) {
    el("pp-pay-entry-refresh").addEventListener("click", function () {
      setPageForCurrentTab(1);
      loadReport();
    });
  }
  if (el("pp-pay-history-from")) {
    el("pp-pay-history-from").addEventListener("change", function () {
      setWorkflowHistoryRange("payment_manage", el("pp-pay-history-from").value || "", (el("pp-pay-history-to") && el("pp-pay-history-to").value) || "");
      state.historyPageByTab.payment_manage_history = 1;
      renderCreatedEntriesPanel("payment_manage");
    });
  }
  if (el("pp-pay-history-to")) {
    el("pp-pay-history-to").addEventListener("change", function () {
      setWorkflowHistoryRange("payment_manage", (el("pp-pay-history-from") && el("pp-pay-history-from").value) || "", el("pp-pay-history-to").value || "");
      state.historyPageByTab.payment_manage_history = 1;
      renderCreatedEntriesPanel("payment_manage");
    });
  }
  if (el("pp-search-any")) {
    el("pp-search-any").addEventListener("input", function () { setPageForCurrentTab(1); renderCurrentTab(); });
  }
  if (el("pp-employee-summary-detail")) {
    el("pp-employee-summary-detail").addEventListener("change", function () {
      state.employeeSummaryDetail = !!el("pp-employee-summary-detail").checked;
      try {
        window.localStorage.setItem("pp_employee_summary_detail", state.employeeSummaryDetail ? "1" : "0");
      } catch (e) {}
      setPageForCurrentTab(1);
      renderCurrentTab();
    });
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
  if (el("pp-summary-print")) {
    el("pp-summary-print").addEventListener("click", printSummaryModal);
  }
  if (el("pp-summary-modal")) {
    el("pp-summary-modal").addEventListener("click", function (ev) {
      if (ev.target && ev.target.id === "pp-summary-modal") hidePerPieceSummary();
    });
  }
  if (el("pp-action-close")) {
    el("pp-action-close").addEventListener("click", hideActionModal);
  }
  if (el("pp-action-modal")) {
    el("pp-action-modal").addEventListener("click", function (ev) {
      if (ev.target && ev.target.id === "pp-action-modal") hideActionModal();
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
		"sales_order",
		"Sales Order",
		"Link",
		"Sales Order",
		"process_size",
		results,
		doctype="Per Piece",
		read_only=0,
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
		"pp_filters_col_break_2",
		"",
		"Column Break",
		None,
		"item",
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
		"pp_filters_col_break_3",
		"",
		"Column Break",
		None,
		"employee",
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
	_delete_custom_field("Item", "custom_process_type", results)
	_delete_custom_field("Item", "custom_process_size", results)
	_delete_custom_field("Item", "custom_rate_per_piece", results)
	_delete_custom_field("Per Piece Salary", "voucher_no", results)
	_delete_custom_field("Per Piece Salary", "selected_items", results)
	_delete_custom_field("Per Piece Salary", "pp_filter_col_break", results)
	_ensure_doctype_property_setter(
		"Per Piece Salary",
		"autoname",
		"format:Date-{YY}-{MM}-PO-{po_number}-{#####}",
		"Data",
		results,
	)
	_ensure_doctype_property_setter("Per Piece Salary", "allow_rename", "0", "Check", results)
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
