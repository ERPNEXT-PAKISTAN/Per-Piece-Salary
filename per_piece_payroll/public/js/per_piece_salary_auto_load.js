const REPORT_ROUTE = "/per-piece-report";
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
		return Promise.resolve(
			frappe.call({
				method: "per_piece_payroll.api.get_item_process_rows",
				args: { item: selectedItem },
			})
		)
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
	return Promise.resolve(
		frappe.call({
			method: "per_piece_payroll.api.get_item_process_rows",
			args: { item_group: itemGroup },
		})
	)
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

	return Promise.resolve(
		frappe.call({
			method: "per_piece_payroll.api.get_item_process_rows",
			args: { item: product },
		})
	)
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
	return Promise.all(tasks).then(
		() => {
			const freshRow = locals[cdt] && locals[cdt][cdn] ? locals[cdt][cdn] : row;
			calculateRowAmount(freshRow);
			frm.trigger("recalc_amount_and_total");
		},
		() => {
			const freshRow = locals[cdt] && locals[cdt][cdn] ? locals[cdt][cdn] : row;
			calculateRowAmount(freshRow);
			frm.trigger("recalc_amount_and_total");
		}
	);
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

	return Promise.resolve(frappe.db.get_value("Employee", employee, "employee_name"))
		.then((response) => {
			const message = (response && response.message) || {};
			frm.__per_piece_parent_employee = employee;
			frm.__per_piece_parent_employee_name = message.employee_name || "";
			return frm.__per_piece_parent_employee_name;
		})
		.catch(() => {
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
			(entry) => (entry.process_size || PROCESS_SIZE_DEFAULT).trim() === currentSize
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

	return Promise.all(tasks).then(
		() => {
			frm.refresh_field(CHILD_TABLE_FIELD);
			frm.trigger("recalc_amount_and_total");
		},
		() => {
			frm.refresh_field(CHILD_TABLE_FIELD);
			frm.trigger("recalc_amount_and_total");
		}
	);
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
		.then(
			() => {
				const updatedRow = locals[cdt][cdn] || row;
				calculateRowAmount(updatedRow);
				frappe.model.set_value(cdt, cdn, "amount", updatedRow.amount);
				frm.trigger("recalc_amount_and_total");
			},
			() => {
				const updatedRow = locals[cdt][cdn] || row;
				calculateRowAmount(updatedRow);
				frappe.model.set_value(cdt, cdn, "amount", updatedRow.amount);
				frm.trigger("recalc_amount_and_total");
			}
		);
}

frappe.ui.form.on("Per Piece Salary", {
	onload(frm) {
		if (isSubmittedDoc(frm)) {
			setProductQuery(frm);
			setDeliveryNoteQuery(frm);
			return;
		}
		if (
			frm.doc.load_by_item === undefined ||
			frm.doc.load_by_item === null ||
			frm.doc.load_by_item === ""
		) {
			frm.set_value("load_by_item", 1);
		}
		setProductQuery(frm);
		setDeliveryNoteQuery(frm);
		loadParentEmployeeName(frm)
			.then(() => {
				return loadItemsForGroup(frm);
			})
			.then(() => {
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
			frm.add_custom_button(
				__("Load From Delivery Note"),
				() => {
					loadRowsFromDeliveryNote(frm, true);
				},
				__("Actions")
			);
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
