from __future__ import annotations

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute() -> None:
    parent_fields = [
        "items",
        "operations",
        "scrap_items",
        "quantity",
        "with_operations",
        "transfer_material_against",
        "routing",
        "operating_cost",
        "base_operating_cost",
        "raw_material_cost",
        "base_raw_material_cost",
        "scrap_material_cost",
        "base_scrap_material_cost",
        "total_cost",
        "base_total_cost",
        "process_loss_qty",
    ]

    child_fields = [
        "item_code",
        "item_name",
        "bom_no",
        "source_warehouse",
        "description",
        "qty",
        "uom",
        "stock_qty",
        "stock_uom",
        "conversion_factor",
        "rate",
        "base_rate",
        "amount",
        "base_amount",
        "qty_consumed_per_unit",
        "allow_alternative_item",
        "include_item_in_manufacturing",
        "sourced_by_supplier",
        "do_not_explode",
    ]

    scrap_item_fields = [
        "item_code",
        "item_name",
        "stock_qty",
        "rate",
        "amount",
        "stock_uom",
        "base_rate",
        "base_amount",
    ]

    operation_fields = [
        "sequence_id",
        "operation",
        "workstation_type",
        "workstation",
        "time_in_mins",
        "fixed_time",
        "hour_rate",
        "base_hour_rate",
        "operating_cost",
        "base_operating_cost",
        "batch_size",
        "set_cost_based_on_bom_qty",
        "cost_per_unit",
        "base_cost_per_unit",
        "description",
    ]

    for fieldname in parent_fields:
        make_property_setter("BOM", fieldname, "allow_on_submit", 1, "Check")

    for fieldname in child_fields:
        make_property_setter("BOM Item", fieldname, "allow_on_submit", 1, "Check")

    for fieldname in scrap_item_fields:
        make_property_setter("BOM Scrap Item", fieldname, "allow_on_submit", 1, "Check")

    for fieldname in operation_fields:
        make_property_setter("BOM Operation", fieldname, "allow_on_submit", 1, "Check")

    frappe.clear_cache(doctype="BOM")
    frappe.clear_cache(doctype="BOM Item")
    frappe.clear_cache(doctype="BOM Scrap Item")
    frappe.clear_cache(doctype="BOM Operation")
