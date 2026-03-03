from __future__ import annotations

import frappe

from per_piece_payroll.per_piece_setup import apply


@frappe.whitelist()
def apply_per_piece_payroll_setup() -> list[str]:
    return apply()
