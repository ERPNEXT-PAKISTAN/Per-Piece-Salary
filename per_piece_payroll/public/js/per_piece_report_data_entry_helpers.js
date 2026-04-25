(function () {
	function create(deps) {
		var state = deps.state;
		var num = deps.num;
		var whole = deps.whole;
		var callApi = deps.callApi;
		var rebuildEntryMetaLookups = deps.rebuildEntryMetaLookups;
		var renderDataEntryTab = deps.renderDataEntryTab;

		function getAutoEntryProduct() {
			var productOptions = state.entryMeta.productOptions || [];
			return productOptions.length === 1
				? String((productOptions[0] && productOptions[0].value) || "").trim()
				: "";
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
					if (currentItemGroup && itemGroup && itemGroup !== currentItemGroup)
						return false;
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
			((state.entryMeta.productProcessMap || {})[product] || []).forEach(function (entry) {
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
			var employeeName = String(
				(state.entryMeta.employeeNameMap || {})[employee] || ""
			).trim();
			(state.entryRows || []).forEach(function (row) {
				row.employee = employee;
				if (employeeName) row.name1 = employeeName;
			});
		}

		function applyEntryItemDefaults(row) {
			if (!row) return;
			var productName = String(row.product || "").trim();
			var processRows = (
				(state.entryMeta.productProcessMap || {})[productName] || []
			).slice();
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
			if (
				meta.employee &&
				(!String(row.employee || "").trim() ||
					String(row.employee || "").trim() === selectedEmployee)
			) {
				row.employee = String(meta.employee || "").trim();
				row.name1 = String(
					meta.employee_name ||
						(state.entryMeta.employeeNameMap || {})[row.employee] ||
						""
				).trim();
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
					name1: String(
						(item && item.employee_name) ||
							(state.entryMeta.employeeNameMap || {})[finalEmployee] ||
							""
					).trim(),
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
				item: itemName,
			})
				.then(function (rows) {
					var list = (rows || []).filter(function (r) {
						return String((r && r.item) || "").trim() === itemName;
					});
					if (list.length) {
						var keep = (state.entryMeta.masterProcessRows || []).filter(function (r) {
							return String((r && r.item) || "").trim() !== itemName;
						});
						state.entryMeta.masterProcessRows = keep.concat(list);
						if (!state.entryMeta.item_group) {
							state.entryMeta.item_group = String(
								(list[0] && list[0].item_group) || ""
							).trim();
						}
						state.entryRows = list.map(function (item) {
							var itemEmployee = String((item && item.employee) || "").trim();
							var fallbackEmployee = String(state.entryMeta.employee || "").trim();
							var finalEmployee = itemEmployee || fallbackEmployee;
							return {
								employee: finalEmployee,
								name1: String(
									(item && item.employee_name) ||
										(state.entryMeta.employeeNameMap || {})[finalEmployee] ||
										""
								).trim(),
								sales_order: "",
								product: String((item && item.item) || "").trim(),
								process_type: String((item && item.process_type) || "").trim(),
								process_size:
									String((item && item.process_size) || "").trim() || "No Size",
								qty: 0,
								rate: whole(item && item.rate),
								rate_manual: false,
							};
						});
					}
					state.entryMeta.item_fetch_inflight = 0;
					rebuildEntryMetaLookups();
					syncEntryRowsToItemGroup();
					if (forceRender) renderDataEntryTab();
				})
				.catch(function () {
					state.entryMeta.item_fetch_inflight = 0;
					if (forceRender) renderDataEntryTab();
				});
		}

		function newEntryRow() {
			var employee = String(state.entryMeta.employee || "").trim();
			var row = {
				employee: employee,
				name1: String((state.entryMeta.employeeNameMap || {})[employee] || "").trim(),
				sales_order: "",
				product: "",
				process_type: "",
				process_size: "No Size",
				qty: 0,
				rate: 0,
				rate_manual: false,
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

		return {
			getAutoEntryProduct: getAutoEntryProduct,
			getCurrentGroupItems: getCurrentGroupItems,
			getEntryProcessOptions: getEntryProcessOptions,
			entryRowIsBlank: entryRowIsBlank,
			syncEntryEmployeeToRows: syncEntryEmployeeToRows,
			applyEntryItemDefaults: applyEntryItemDefaults,
			syncEntryRowsToItemGroup: syncEntryRowsToItemGroup,
			populateEntryRowsFromItemGroup: populateEntryRowsFromItemGroup,
			loadSelectedItemProcessRows: loadSelectedItemProcessRows,
			newEntryRow: newEntryRow,
			ensureEntryRows: ensureEntryRows,
			entryAmount: entryAmount,
		};
	}

	window.PerPieceDataEntryHelpers = {
		create: create,
	};
})();
