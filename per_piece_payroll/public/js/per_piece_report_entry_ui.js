(function () {
	function create(deps) {
		var state = deps.state;
		var el = deps.el;
		var esc = deps.esc;
		var num = deps.num;
		var whole = deps.whole;
		var fmt = deps.fmt;
		var lineRate = deps.lineRate;
		var parseDecimalInput = deps.parseDecimalInput;
		var parseDateOnly = deps.parseDateOnly;
		var ymd = deps.ymd;
		var callApi = deps.callApi;
		var callGetList = deps.callGetList;
		var setOptions = deps.setOptions;
		var uniqueSalaryDocs = deps.uniqueSalaryDocs;
		var filterDataEntryDocsByDate = deps.filterDataEntryDocsByDate;
		var statusBadgeHtml = deps.statusBadgeHtml;
		var employeeLabel = deps.employeeLabel;
		var entrySequenceNo = deps.entrySequenceNo;
		var compareEntryNoDesc = deps.compareEntryNoDesc;
		var getRowsByHeaderFilters = deps.getRowsByHeaderFilters;
		var filterRowsByDateRange = deps.filterRowsByDateRange;
		var getWorkflowHistoryRange = deps.getWorkflowHistoryRange;
		var errText = deps.errText;
		var prettyError = deps.prettyError;
		var showResult = deps.showResult;
		var notifyActionResult = deps.notifyActionResult;
		var refreshHeaderFilterOptions = deps.refreshHeaderFilterOptions;
		var refreshWorkflowEntrySelectors = deps.refreshWorkflowEntrySelectors;
		var resetEntryFiltersToAll = deps.resetEntryFiltersToAll;
		var setPageForCurrentTab = deps.setPageForCurrentTab;
		var loadReport = deps.loadReport;
		var renderCreatedEntriesPanel = deps.renderCreatedEntriesPanel;
		var defaultDateWindow = deps.defaultDateWindow;
		var rebuildEntryMetaLookups = deps.rebuildEntryMetaLookups;
		var paginateHistoryRows = deps.paginateHistoryRows;
		var historyPagerHtml = deps.historyPagerHtml;
		var getWorkflowStatusFilter = deps.getWorkflowStatusFilter;
		var setWorkflowStatusFilter = deps.setWorkflowStatusFilter;
		var setWorkflowHistoryRange = deps.setWorkflowHistoryRange;
		var showPerPieceSummary = deps.showPerPieceSummary;
		var showDataEntryEnteredRows = deps.showDataEntryEnteredRows;
		var switchWorkspaceMode = deps.switchWorkspaceMode;
		var getCurrentGroupItems = deps.getCurrentGroupItems;
		var getEntryProcessOptions = deps.getEntryProcessOptions;
		var entryRowIsBlank = deps.entryRowIsBlank;
		var syncEntryEmployeeToRows = deps.syncEntryEmployeeToRows;
		var applyEntryItemDefaults = deps.applyEntryItemDefaults;
		var syncEntryRowsToItemGroup = deps.syncEntryRowsToItemGroup;
		var populateEntryRowsFromItemGroup = deps.populateEntryRowsFromItemGroup;
		var loadSelectedItemProcessRows = deps.loadSelectedItemProcessRows;
		var newEntryRow = deps.newEntryRow;
		var ensureEntryRows = deps.ensureEntryRows;
		var entryAmount = deps.entryAmount;

		function renderDataEntryTab() {
			var wrap = el("pp-table-wrap");
			if (!wrap) return;
			if (!state.entryMeta.from_date) state.entryMeta.from_date = defaultDateWindow().from;
			if (!state.entryMeta.to_date) state.entryMeta.to_date = defaultDateWindow().to;
			if (state.entryMeta.po_number === undefined) state.entryMeta.po_number = "";
			if (state.entryMeta.item_group === undefined)
				state.entryMeta.item_group = el("pp-item-group")
					? el("pp-item-group").value || ""
					: "";
			if (state.entryMeta.item === undefined) state.entryMeta.item = "";
			if (state.entryMeta.delivery_note === undefined) state.entryMeta.delivery_note = "";
			if (state.entryMeta.deliveryNoteOptions === undefined)
				state.entryMeta.deliveryNoteOptions = [];
			if (state.entryMeta.employee === undefined)
				state.entryMeta.employee = el("pp-employee") ? el("pp-employee").value || "" : "";
			if (state.entryMeta.load_by_item === undefined) state.entryMeta.load_by_item = true;
			if (state.entryMeta.skip_auto_populate_once === undefined)
				state.entryMeta.skip_auto_populate_once = false;
			if (state.entryMeta.skip_sync_to_item_group_once === undefined)
				state.entryMeta.skip_sync_to_item_group_once = false;
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
				var hasOnlyPlaceholder =
					selectedRows.length > 0 &&
					selectedRows.every(function (r) {
						return (
							!String((r && r.process_type) || "").trim() &&
							num((r && r.rate) || 0) <= 0
						);
					});
				if (!selectedRows.length || hasOnlyPlaceholder) {
					loadSelectedItemProcessRows(selectedItemAuto, true);
				}
			}
			var HISTORY_SOURCE_LIMIT = 2000;
			var HISTORY_DOC_LIMIT = 120;
			var historySource = (
				(state.entryMeta && state.entryMeta.recentRows) ||
				state.rows ||
				[]
			).slice(0, HISTORY_SOURCE_LIMIT);
			var docs = filterDataEntryDocsByDate(uniqueSalaryDocs(historySource))
				.slice()
				.sort(function (a, b) {
					return compareEntryNoDesc(String(a && a.name), String(b && b.name));
				})
				.slice(0, HISTORY_DOC_LIMIT);
			var employeeOptions = state.entryMeta.employeeOptions || [];
			var itemGroupOptions = state.entryMeta.itemGroupOptions || [];
			var productOptions = state.entryMeta.productOptions || [];
			var salesOrderOptions = (state.filterOptions.sales_orders || [])
				.map(function (v) {
					return { value: String(v || "").trim(), label: String(v || "").trim() };
				})
				.filter(function (r) {
					return !!r.value;
				});
			var employeeNameMap = state.entryMeta.employeeNameMap || {};
			var itemOptions = [];
			(state.entryMeta.masterProcessRows || []).forEach(function (r) {
				var rowGroup = String((r && r.item_group) || "").trim();
				var selectedGroup = String(state.entryMeta.item_group || "").trim();
				if (selectedGroup && rowGroup !== selectedGroup) return;
				var itemName = String((r && r.item) || "").trim();
				if (itemName && itemOptions.indexOf(itemName) < 0) itemOptions.push(itemName);
			});
			itemOptions = itemOptions.map(function (name) {
				return { value: name, label: name };
			});
			var editing = !!(state.entryMeta.edit_name || "");
			syncEntryEmployeeToRows();
			if (state.entryMeta.skip_sync_to_item_group_once) {
				state.entryMeta.skip_sync_to_item_group_once = false;
			} else {
				syncEntryRowsToItemGroup();
			}

			function selectHtml(options, value, idx, field) {
				var htmlParts = [];
				var selectedValue = String(value || "");
				var exists = false;
				htmlParts.push(
					"<select class='pp-pay-input pp-entry-in' data-idx='" +
						idx +
						"' data-field='" +
						field +
						"'>"
				);
				htmlParts.push("<option value=''>Select</option>");
				(options || []).forEach(function (opt) {
					var selected = String(opt.value || "") === selectedValue ? " selected" : "";
					if (selected) exists = true;
					htmlParts.push(
						"<option value='" +
							esc(opt.value || "") +
							"'" +
							selected +
							">" +
							esc(opt.label || opt.value || "") +
							"</option>"
					);
				});
				if (selectedValue && !exists) {
					htmlParts.push(
						"<option value='" +
							esc(selectedValue) +
							"' selected>" +
							esc(selectedValue) +
							"</option>"
					);
				}
				htmlParts.push("</select>");
				return htmlParts.join("");
			}

			function datalistInputHtml(options, value, idx, field, listPrefix) {
				var htmlParts = [];
				var selectedValue = String(value || "");
				var listId = String(listPrefix || "pp-datalist") + "-" + String(idx);
				htmlParts.push(
					"<input class='pp-pay-input pp-entry-in' data-idx='" +
						idx +
						"' data-field='" +
						field +
						"' list='" +
						listId +
						"' value='" +
						esc(selectedValue) +
						"' placeholder='Type or select'>"
				);
				htmlParts.push("<datalist id='" + listId + "'>");
				(options || []).forEach(function (opt) {
					var v = String((opt && opt.value) || "").trim();
					if (!v) return;
					htmlParts.push(
						"<option value='" +
							esc(v) +
							"'>" +
							esc((opt && opt.label) || v) +
							"</option>"
					);
				});
				htmlParts.push("</datalist>");
				return htmlParts.join("");
			}

			function readonlyHtml(value) {
				return (
					"<input class='pp-pay-input pp-entry-view' readonly tabindex='-1' value='" +
					esc(value || "") +
					"'>"
				);
			}

			function entrySalesOrderOptions(row) {
				var selectedGroup = String(state.entryMeta.item_group || "").trim();
				var selectedItem = String(state.entryMeta.item || "").trim();
				var rowProduct = String((row && row.product) || "").trim();
				var byItem = state.entryMeta.load_by_item !== false;
				var optMap = {};
				var options = [];

				function addOption(value) {
					var key = String(value || "").trim();
					if (!key || optMap[key]) return;
					optMap[key] = true;
					options.push({ value: key, label: key });
				}

				function rowMatches(sourceRow) {
					if (!sourceRow) return false;
					var so = String(sourceRow.sales_order || "").trim();
					if (!so) return false;
					var srcGroup = String(sourceRow.item_group || "").trim();
					var srcProduct = String(sourceRow.product || "").trim();
					if (selectedGroup && srcGroup && srcGroup !== selectedGroup) return false;
					if (byItem && selectedItem && srcProduct && srcProduct !== selectedItem)
						return false;
					if (rowProduct && srcProduct && srcProduct !== rowProduct) return false;
					return true;
				}

				(state.entryMeta.recentRows || state.rows || []).forEach(function (sourceRow) {
					if (!rowMatches(sourceRow)) return;
					addOption(sourceRow.sales_order);
				});

				(salesOrderOptions || []).forEach(function (opt) {
					addOption(opt && opt.value);
				});

				options.sort(function (a, b) {
					return compareEntryNoDesc(a && a.value, b && b.value);
				});
				return options;
			}

			function docsSelectHtml(selectedName) {
				var parts = [];
				parts.push("<select id='pp-entry-edit-name'>");
				parts.push("<option value=''>New Entry</option>");
				docs.forEach(function (d) {
					var selected =
						String(d.name || "") === String(selectedName || "") ? " selected" : "";
					parts.push(
						"<option value='" +
							esc(d.name) +
							"'" +
							selected +
							">" +
							esc(d.name + " | " + (d.po_number || "-")) +
							"</option>"
					);
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
					parts.push(
						"<option value='" +
							esc(optValue) +
							"'" +
							selected +
							">" +
							esc((opt && opt.label) || optValue) +
							"</option>"
					);
				});
				if (current && !exists) {
					parts.push(
						"<option value='" +
							esc(current) +
							"' selected>" +
							esc(current) +
							"</option>"
					);
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
					parts.push(
						"<option value='" +
							esc(optValue) +
							"'" +
							selected +
							">" +
							esc((opt && opt.label) || optValue) +
							"</option>"
					);
				});
				if (current && !exists) {
					parts.push(
						"<option value='" +
							esc(current) +
							"' selected>" +
							esc(current) +
							"</option>"
					);
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
					parts.push(
						"<option value='" +
							esc(val) +
							"'" +
							selected +
							">" +
							esc((opt && opt.label) || val) +
							"</option>"
					);
				});
				if (current && !exists) {
					parts.push(
						"<option value='" +
							esc(current) +
							"' selected>" +
							esc(current) +
							"</option>"
					);
				}
				parts.push("</select>");
				return parts.join("");
			}

			function deliveryNoteDatalistHtml(selectedValue) {
				var parts = [];
				var current = String(selectedValue || "");
				parts.push(
					"<input type='text' id='pp-entry-delivery-note' list='pp-entry-delivery-note-list' placeholder='Type Delivery Note no...' value='" +
						esc(current) +
						"'>"
				);
				parts.push("<datalist id='pp-entry-delivery-note-list'>");
				(state.entryMeta.deliveryNoteOptions || []).forEach(function (opt) {
					var dn = String((opt && opt.name) || "").trim();
					if (!dn) return;
					var label = String((opt && opt.label) || dn);
					parts.push("<option value='" + esc(label) + "'>" + esc(label) + "</option>");
				});
				parts.push("</datalist>");
				return parts.join("");
			}

			function normalizeDeliveryNoteValue(raw) {
				var text = String(raw || "").trim();
				if (!text) return "";
				// Accept either exact DN or label-like text: "DN-NAME | date | customer"
				return String(text.split("|")[0] || "")
					.trim()
					.replace(/\s+/g, " ");
			}

			function renderDeliveryNoteOptions(rows) {
				state.entryMeta.deliveryNoteOptions = rows || [];
				var listEl = el("pp-entry-delivery-note-list");
				if (!listEl) return;
				listEl.innerHTML = "";
				(state.entryMeta.deliveryNoteOptions || []).forEach(function (opt) {
					var dn = String((opt && opt.name) || "").trim();
					if (!dn) return;
					var node = document.createElement("option");
					var label = String((opt && opt.label) || dn);
					node.value = label;
					node.textContent = label;
					listEl.appendChild(node);
				});
			}

			function scheduleDeliveryNoteSearch(query) {
				var q = String(query || "").trim();
				if (state.entryMeta.delivery_note_search_timer) {
					clearTimeout(state.entryMeta.delivery_note_search_timer);
				}
				state.entryMeta.delivery_note_search_timer = setTimeout(function () {
					searchDeliveryNotes(q);
				}, 220);
			}

			function searchDeliveryNotes(query) {
				return callApi("per_piece_payroll.api.search_delivery_notes", {
					txt: String(query || "").trim(),
					limit: 40,
				})
					.then(function (rows) {
						renderDeliveryNoteOptions(rows || []);
					})
					.catch(function () {});
			}

			function resolveDeliveryNoteName(inputValue) {
				var typed = normalizeDeliveryNoteValue(inputValue);
				if (!typed) return Promise.resolve("");
				return callApi("per_piece_payroll.api.search_delivery_notes", {
					txt: typed,
					limit: 15,
				})
					.then(function (rows) {
						var list = rows || [];
						if (!list.length) return "";
						var typedLc = typed.toLowerCase();
						var exact = list.find(function (row) {
							return String((row && row.name) || "").toLowerCase() === typedLc;
						});
						if (exact) return String(exact.name || "").trim();
						var startsWith = list.find(function (row) {
							return (
								String((row && row.name) || "")
									.toLowerCase()
									.indexOf(typedLc) === 0
							);
						});
						if (startsWith) return String(startsWith.name || "").trim();
						return String((list[0] && list[0].name) || "").trim();
					})
					.catch(function () {
						return "";
					});
			}

			function buildRowsFromDeliveryItems(deliveryNote, items) {
				var builtRows = [];
				(items || []).forEach(function (it) {
					var itemCode = String((it && it.item_code) || "").trim();
					if (!itemCode) return;
					var itemQty = whole((it && it.qty) || 0);
					var salesOrder = String((it && it.against_sales_order) || "").trim();
					var processRows = (state.entryMeta.masterProcessRows || []).filter(function (
						r
					) {
						return String((r && r.item) || "").trim() === itemCode;
					});
					if (!processRows.length) {
						processRows = [
							{
								item: itemCode,
								item_group: String((it && it.item_group) || "").trim(),
								employee: "",
								employee_name: "",
								process_type: "",
								process_size: "No Size",
								rate: 0,
							},
						];
					}
					processRows.forEach(function (pr) {
						var itemEmployee = String((pr && pr.employee) || "").trim();
						var fallbackEmployee = String(state.entryMeta.employee || "").trim();
						var finalEmployee = itemEmployee || fallbackEmployee;
						builtRows.push({
							employee: finalEmployee,
							name1: String(
								(pr && pr.employee_name) ||
									(state.entryMeta.employeeNameMap || {})[finalEmployee] ||
									""
							).trim(),
							sales_order: salesOrder,
							product: itemCode,
							process_type: String((pr && pr.process_type) || "").trim(),
							process_size:
								String((pr && pr.process_size) || "").trim() || "No Size",
							qty: itemQty,
							rate: whole(pr && pr.rate),
							rate_manual: false,
						});
					});
				});
				if (!builtRows.length) return false;
				state.entryMeta.delivery_note = deliveryNote;
				state.entryMeta.load_by_item = false;
				state.entryMeta.item = "";
				state.entryMeta.item_group = "";
				state.entryMeta.skip_auto_populate_once = true;
				state.entryMeta.skip_sync_to_item_group_once = true;
				state.entryRows = builtRows;
				if (!String(state.entryMeta.po_number || "").trim())
					state.entryMeta.po_number = deliveryNote;
				renderDataEntryTab();
				showResult(
					el("pp-entry-result"),
					"success",
					"Delivery Note Loaded",
					deliveryNote + ": " + String(items.length || 0) + " items loaded."
				);
				return true;
			}

			function loadFromDeliveryNote() {
				if (state.entryMeta.delivery_note_loading) return;
				var typedDn = normalizeDeliveryNoteValue(
					(el("pp-entry-delivery-note") && el("pp-entry-delivery-note").value) ||
						state.entryMeta.delivery_note ||
						""
				);
				if (!typedDn) {
					showResult(
						el("pp-entry-result"),
						"error",
						"Delivery Note Required",
						"Type/select a Delivery Note first."
					);
					return;
				}
				state.entryMeta.delivery_note_loading = true;
				var loadBtn = el("pp-entry-load-dn");
				if (loadBtn) loadBtn.disabled = true;
				showResult(
					el("pp-entry-result"),
					"success",
					"Loading Delivery Note",
					"Loading items from " + typedDn + "..."
				);
				state.entryMeta.delivery_note = typedDn;
				var inputEl = el("pp-entry-delivery-note");
				if (inputEl) inputEl.value = typedDn;
				callApi("per_piece_payroll.api.get_delivery_note_process_rows", {
					delivery_note: typedDn,
				})
					.then(function (rows) {
						var rawRows = rows || [];
						if (rawRows.length) {
							state.entryMeta.delivery_note = typedDn;
							state.entryMeta.load_by_item = false;
							state.entryMeta.item = "";
							state.entryMeta.item_group = "";
							state.entryMeta.skip_auto_populate_once = true;
							state.entryMeta.skip_sync_to_item_group_once = true;
							state.entryRows = rawRows.map(function (row) {
								return {
									employee: String(row.employee || "").trim(),
									name1: String(row.name1 || "").trim(),
									sales_order: String(row.sales_order || "").trim(),
									product: String(row.product || "").trim(),
									process_type: String(row.process_type || "").trim(),
									process_size:
										String(row.process_size || "").trim() || "No Size",
									qty: whole(row.qty),
									rate: whole(row.rate),
									rate_manual: false,
								};
							});
							if (!String(state.entryMeta.po_number || "").trim())
								state.entryMeta.po_number = typedDn;
							renderDataEntryTab();
							showResult(
								el("pp-entry-result"),
								"success",
								"Delivery Note Loaded",
								typedDn +
									": " +
									String(rawRows.length || 0) +
									" process rows loaded."
							);
							return;
						}
						return resolveDeliveryNoteName(typedDn).then(function (resolvedDn) {
							var deliveryNote = String(resolvedDn || "").trim();
							if (!deliveryNote || deliveryNote === typedDn) {
								showResult(
									el("pp-entry-result"),
									"error",
									"No Item Found",
									"No items found in Delivery Note " + typedDn + "."
								);
								return;
							}
							state.entryMeta.delivery_note = deliveryNote;
							var input = el("pp-entry-delivery-note");
							if (input) input.value = deliveryNote;
							return callApi(
								"per_piece_payroll.api.get_delivery_note_process_rows",
								{
									delivery_note: deliveryNote,
								}
							).then(function (rows) {
								var rawRows = rows || [];
								if (!rawRows.length) {
									showResult(
										el("pp-entry-result"),
										"error",
										"No Item Found",
										"No items found in Delivery Note " + deliveryNote + "."
									);
									return;
								}
								state.entryMeta.delivery_note = deliveryNote;
								state.entryMeta.load_by_item = false;
								state.entryMeta.item = "";
								state.entryMeta.item_group = "";
								state.entryMeta.skip_auto_populate_once = true;
								state.entryMeta.skip_sync_to_item_group_once = true;
								state.entryRows = rawRows.map(function (row) {
									return {
										employee: String(row.employee || "").trim(),
										name1: String(row.name1 || "").trim(),
										sales_order: String(row.sales_order || "").trim(),
										product: String(row.product || "").trim(),
										process_type: String(row.process_type || "").trim(),
										process_size:
											String(row.process_size || "").trim() || "No Size",
										qty: whole(row.qty),
										rate: whole(row.rate),
										rate_manual: false,
									};
								});
								if (!String(state.entryMeta.po_number || "").trim()) {
									state.entryMeta.po_number = deliveryNote;
								}
								renderDataEntryTab();
								showResult(
									el("pp-entry-result"),
									"success",
									"Delivery Note Loaded",
									deliveryNote +
										": " +
										String(rawRows.length || 0) +
										" process rows loaded."
								);
							});
						});
					})
					.catch(function (e) {
						showResult(
							el("pp-entry-result"),
							"error",
							"Load Failed",
							prettyError(errText(e))
						);
					})
					.finally(function () {
						state.entryMeta.delivery_note_loading = false;
						if (loadBtn) loadBtn.disabled = false;
					});
			}

			var html =
				"<div class='pp-entry-card'>" +
				"<div class='pp-entry-title'><strong>Data Enter (" +
				(editing ? "Edit Existing Per Piece Salary" : "Create Per Piece Salary") +
				")</strong></div>" +
				"<div class='pp-entry-subtitle'>PO Number is mandatory. Use Edit controls to fix draft entry mistakes.</div>" +
				"<div class='pp-entry-section pp-entry-section-filters'>" +
				"<div class='pp-entry-section-head'>Section 1: Filters And Controls</div>" +
				"<div class='pp-jv-grid' style='margin-top:10px;'>" +
				"<label>Edit Entry " +
				docsSelectHtml(state.entryMeta.edit_name || "") +
				"</label>" +
				"<label>From Date <input type='date' id='pp-entry-from-date' value='" +
				esc(state.entryMeta.from_date || "") +
				"'></label>" +
				"<label>To Date <input type='date' id='pp-entry-to-date' value='" +
				esc(state.entryMeta.to_date || "") +
				"'></label>" +
				"<label>Employee " +
				employeeSelectHtml(state.entryMeta.employee || "") +
				"</label>" +
				"<label>Item Group " +
				itemGroupSelectHtml(state.entryMeta.item_group || "") +
				"</label>" +
				"<label>Item " +
				itemSelectHtml(state.entryMeta.item || "") +
				"</label>" +
				"<label>Load from Delivery Note " +
				deliveryNoteDatalistHtml(state.entryMeta.delivery_note || "") +
				"</label>" +
				"<label>PO Number * <input type='text' id='pp-entry-po-number' required placeholder='Required' value='" +
				esc(state.entryMeta.po_number || "") +
				"'></label>" +
				"<label><span style='display:block;margin-bottom:6px;'>Load By Item</span><input type='checkbox' id='pp-entry-load-by-item'" +
				(state.entryMeta.load_by_item ? " checked" : "") +
				"></label>" +
				"</div>" +
				"<div class='pp-entry-actions'>" +
				"<button id='pp-entry-load-doc' class='btn btn-default' type='button'>Load Entry</button>" +
				"<button id='pp-entry-load-dn' class='btn btn-default' type='button'>Load From Delivery Note</button>" +
				"<button id='pp-entry-new-doc' class='btn btn-default' type='button'>New Entry</button>" +
				"<button id='pp-entry-add-row' class='btn btn-default' type='button'>Add Row</button>" +
				"<button id='pp-entry-reset' class='btn btn-default' type='button'>Reset Rows</button>" +
				"<button id='pp-entry-save' class='btn btn-primary' type='button'>" +
				(editing ? "Update Per Piece Salary" : "Save Per Piece Salary") +
				"</button>" +
				"</div>" +
				"<div id='pp-entry-result' class='pp-jv-result'></div>" +
				"</div>" +
				"<div class='pp-entry-section pp-entry-section-lines'>" +
				"<div class='pp-entry-section-head'>Section 2: Item Lines</div>" +
				"<table class='pp-table' style='margin-top:8px;'><thead><tr><th>Employee</th><th>Employee First Name</th><th>Sales Order</th><th>Product</th><th>Process Type</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Action</th></tr></thead><tbody>";
			state.entryRows.forEach(function (r, idx) {
				var name1 = r.name1 || employeeNameMap[r.employee || ""] || "";
				html +=
					"<tr>" +
					"<td>" +
					selectHtml(employeeOptions, r.employee || "", idx, "employee") +
					"</td>" +
					"<td><input class='pp-pay-input pp-entry-in' data-idx='" +
					idx +
					"' data-field='name1' value='" +
					esc(name1) +
					"'></td>" +
					"<td>" +
					datalistInputHtml(
						entrySalesOrderOptions(r),
						r.sales_order || "",
						idx,
						"sales_order",
						"pp-entry-sales-order-list"
					) +
					"</td>" +
					"<td>" +
					selectHtml(productOptions, r.product || "", idx, "product") +
					"</td>" +
					"<td>" +
					selectHtml(
						getEntryProcessOptions(r.product || ""),
						r.process_type || "",
						idx,
						"process_type"
					) +
					"</td>" +
					"<td>" +
					readonlyHtml(r.process_size || "No Size") +
					"</td>" +
					"<td><input class='pp-pay-input pp-entry-in pp-entry-qty' type='number' min='0' step='0.01' inputmode='decimal' data-idx='" +
					idx +
					"' data-field='qty' value='" +
					esc(whole(r.qty)) +
					"'></td>" +
					"<td><input class='pp-pay-input pp-entry-in' type='number' min='0' step='0.01' inputmode='decimal' data-idx='" +
					idx +
					"' data-field='rate' value='" +
					esc(whole(r.rate)) +
					"'></td>" +
					"<td class='num'>" +
					esc(fmt(entryAmount(r))) +
					"</td>" +
					"<td><button class='btn btn-xs btn-danger pp-entry-del' data-idx='" +
					idx +
					"' type='button'>Delete</button></td>" +
					"</tr>";
			});
			var eQty = 0,
				eRate = 0,
				eAmount = 0;
			state.entryRows.forEach(function (r) {
				eQty += num(r.qty);
				eRate += num(r.rate);
				eAmount += entryAmount(r);
			});
			html +=
				"<tr class='pp-year-total'>" +
				"<td>Total</td><td></td><td></td><td></td><td></td><td></td>" +
				"<td class='num'>" +
				esc(fmt(eQty)) +
				"</td>" +
				"<td class='num'>" +
				esc(fmt(eRate)) +
				"</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(eAmount)) +
				"</td>" +
				"<td></td>" +
				"</tr>";
			html += "</tbody></table>";
			html += "</div>";
			html +=
				"<div class='pp-entry-section pp-entry-section-history'>" +
				"<div class='pp-entry-section-head'>Section 3: Recent Docs</div>" +
				"<div class='pp-entry-list'><strong>Recent Docs:</strong></div>";
			state.entryMeta.selected_docs = state.entryMeta.selected_docs || {};
			var selectedDocs = state.entryMeta.selected_docs;
			var docsPage = paginateHistoryRows("data_entry_docs", docs, 10);
			var selectedCount = Object.keys(selectedDocs).filter(function (k) {
				return !!selectedDocs[k];
			}).length;
			html +=
				"<div class='pp-jv-grid' style='margin-top:6px;margin-bottom:6px;'>" +
				"<label>History From <input type='date' id='pp-entry-history-from' value='" +
				esc((state.workflowHistoryDate.data_entry || {}).from || "") +
				"'></label>" +
				"<label>History To <input type='date' id='pp-entry-history-to' value='" +
				esc((state.workflowHistoryDate.data_entry || {}).to || "") +
				"'></label>" +
				"<label>Booking Status <select id='pp-entry-history-booking-status'>" +
				"<option value=''>All</option><option value='Booked'" +
				(getWorkflowStatusFilter("data_entry").booking === "Booked" ? " selected" : "") +
				">Booked</option><option value='UnBooked'" +
				(getWorkflowStatusFilter("data_entry").booking === "UnBooked" ? " selected" : "") +
				">UnBooked</option><option value='Partly Booked'" +
				(getWorkflowStatusFilter("data_entry").booking === "Partly Booked"
					? " selected"
					: "") +
				">Partly Booked</option>" +
				"</select></label>" +
				"<label>Payment Status <select id='pp-entry-history-payment-status'>" +
				"<option value=''>All</option><option value='Paid'" +
				(getWorkflowStatusFilter("data_entry").payment === "Paid" ? " selected" : "") +
				">Paid</option><option value='Unpaid'" +
				(getWorkflowStatusFilter("data_entry").payment === "Unpaid" ? " selected" : "") +
				">Unpaid</option><option value='Partly Paid'" +
				(getWorkflowStatusFilter("data_entry").payment === "Partly Paid"
					? " selected"
					: "") +
				">Partly Paid</option>" +
				"</select></label>" +
				"</div>";
			html +=
				"<div class='pp-entry-actions' style='margin-top:4px;'>" +
				"<button type='button' class='btn btn-default btn-xs' id='pp-entry-doc-select-page'>Select Page</button>" +
				"<button type='button' class='btn btn-default btn-xs' id='pp-entry-doc-clear-select'>Clear Selected</button>" +
				"<button type='button' class='btn btn-primary btn-xs' id='pp-entry-doc-book-selected'>Book Selected</button>" +
				"<button type='button' class='btn btn-success btn-xs' id='pp-entry-doc-pay-selected'>Pay Selected</button>" +
				"<span style='color:#334155;font-size:12px;'>Selected Entries: <strong id='pp-entry-doc-selected-count'>" +
				esc(selectedCount) +
				"</strong></span>" +
				"</div>";
			if (docs.length) {
				html +=
					"<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Select</th><th>Entry No</th><th>From Date</th><th>To Date</th><th>PO Number</th><th>JV Status</th><th>Pay Status</th><th>Total Amount</th><th>Book</th><th>Pay</th><th>View Detail</th><th>View Entered</th><th>Edit</th><th>Open</th></tr></thead><tbody>";
				var docsTotalAmount = 0;
				(docsPage.rows || []).forEach(function (d) {
					docsTotalAmount += num(d.total_amount);
					var canBook = String(d.booking_status || "") !== "Booked";
					var canPay = String(d.payment_status || "") !== "Paid";
					var bookBtn = canBook
						? "<button type='button' class='btn btn-xs btn-primary pp-entry-book-doc' data-name='" +
						  esc(d.name) +
						  "'>Book</button>"
						: "<span style='color:#64748b;'>Done</span>";
					var payBtn = canPay
						? "<button type='button' class='btn btn-xs btn-success pp-entry-pay-doc' data-name='" +
						  esc(d.name) +
						  "' data-unpaid='" +
						  esc(d.unpaid_amount) +
						  "'>Pay</button>"
						: "<span style='color:#64748b;'>Done</span>";
					var checked = selectedDocs[d.name] ? " checked" : "";
					html +=
						"<tr><td><input type='checkbox' class='pp-entry-doc-select' data-name='" +
						esc(d.name) +
						"'" +
						checked +
						"></td><td>" +
						esc(d.name) +
						"</td><td>" +
						esc(d.from_date) +
						"</td><td>" +
						esc(d.to_date) +
						"</td><td>" +
						esc(d.po_number) +
						"</td><td>" +
						statusBadgeHtml(d.booking_status || "UnBooked") +
						"</td><td>" +
						statusBadgeHtml(d.payment_status || "Unpaid") +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(d.total_amount)) +
						"</td><td>" +
						bookBtn +
						"</td><td>" +
						payBtn +
						"</td><td><button type='button' class='btn btn-xs btn-info pp-entry-view-doc-detail' data-name='" +
						esc(d.name) +
						"'>View Detail</button></td><td><button type='button' class='btn btn-xs btn-primary pp-entry-view-entered' data-name='" +
						esc(d.name) +
						"'>View Entered</button></td><td><button type='button' class='btn btn-xs btn-default pp-entry-edit-doc' data-name='" +
						esc(d.name) +
						"'>Edit</button></td><td><a target='_blank' href='/app/per-piece-salary/" +
						encodeURIComponent(d.name) +
						"'>Open</a></td></tr>";
				});
				html +=
					"<tr class='pp-year-total'><td></td><td>Total</td><td></td><td></td><td></td><td></td><td></td><td class='num pp-amt-col'>" +
					esc(fmt(docsTotalAmount)) +
					"</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>";
				html += "</tbody></table>";
				html += historyPagerHtml(docsPage);
			} else {
				html += "<div class='pp-entry-list'>No matching recent docs.</div>";
			}
			html += "</div>";
			html += "</div>";
			wrap.innerHTML = html;

			var saveBtn = el("pp-entry-save");
			if (saveBtn) saveBtn.addEventListener("click", saveDataEntry);
			var fromInput = el("pp-entry-from-date");
			if (fromInput)
				fromInput.addEventListener("change", function () {
					state.entryMeta.from_date = fromInput.value || "";
				});
			var toInput = el("pp-entry-to-date");
			if (toInput)
				toInput.addEventListener("change", function () {
					state.entryMeta.to_date = toInput.value || "";
				});
			var historyFromInput = el("pp-entry-history-from");
			if (historyFromInput) {
				historyFromInput.addEventListener("change", function () {
					setWorkflowHistoryRange(
						"data_entry",
						historyFromInput.value || "",
						(state.workflowHistoryDate.data_entry || {}).to || ""
					);
					state.historyPageByTab.data_entry_docs = 1;
					renderDataEntryTab();
				});
			}
			var historyToInput = el("pp-entry-history-to");
			if (historyToInput) {
				historyToInput.addEventListener("change", function () {
					setWorkflowHistoryRange(
						"data_entry",
						(state.workflowHistoryDate.data_entry || {}).from || "",
						historyToInput.value || ""
					);
					state.historyPageByTab.data_entry_docs = 1;
					renderDataEntryTab();
				});
			}
			var historyBookingInput = el("pp-entry-history-booking-status");
			if (historyBookingInput) {
				historyBookingInput.addEventListener("change", function () {
					setWorkflowStatusFilter(
						"data_entry",
						historyBookingInput.value || "",
						getWorkflowStatusFilter("data_entry").payment || ""
					);
					state.historyPageByTab.data_entry_docs = 1;
					renderDataEntryTab();
				});
			}
			var historyPaymentInput = el("pp-entry-history-payment-status");
			if (historyPaymentInput) {
				historyPaymentInput.addEventListener("change", function () {
					setWorkflowStatusFilter(
						"data_entry",
						getWorkflowStatusFilter("data_entry").booking || "",
						historyPaymentInput.value || ""
					);
					state.historyPageByTab.data_entry_docs = 1;
					renderDataEntryTab();
				});
			}
			var poInput = el("pp-entry-po-number");
			if (poInput)
				poInput.addEventListener("change", function () {
					state.entryMeta.po_number = poInput.value || "";
				});
			var employeeInput = el("pp-entry-employee");
			if (employeeInput) {
				employeeInput.addEventListener("change", function () {
					state.entryMeta.employee = employeeInput.value || "";
					syncEntryEmployeeToRows();
					renderDataEntryTab();
				});
			}

			function runEntryFilterRebuild() {
				rebuildEntryMetaLookups();
				populateEntryRowsFromItemGroup(true);
				syncEntryRowsToItemGroup();
				renderDataEntryTab();
			}

			function scheduleEntryFilterRebuild(delayMs) {
				if (state.entryMeta.filter_change_timer) {
					clearTimeout(state.entryMeta.filter_change_timer);
				}
				state.entryMeta.filter_change_timer = setTimeout(function () {
					runEntryFilterRebuild();
				}, delayMs || 120);
			}

			var itemGroupInput = el("pp-entry-item-group");
			if (itemGroupInput) {
				itemGroupInput.addEventListener("change", function () {
					state.entryMeta.item_group = itemGroupInput.value || "";
					var itemOk = false;
					(itemOptions || []).forEach(function (opt) {
						if (
							String((opt && opt.value) || "") === String(state.entryMeta.item || "")
						)
							itemOk = true;
					});
					if (!itemOk) state.entryMeta.item = "";
					scheduleEntryFilterRebuild(130);
				});
			}
			var loadByItemInput = el("pp-entry-load-by-item");
			if (loadByItemInput) {
				loadByItemInput.addEventListener("change", function () {
					state.entryMeta.load_by_item = !!loadByItemInput.checked;
					scheduleEntryFilterRebuild(120);
				});
			}
			var itemInput = el("pp-entry-item");
			if (itemInput) {
				itemInput.addEventListener("change", function () {
					state.entryMeta.item = itemInput.value || "";
					var selectedItem = String(state.entryMeta.item || "").trim();
					if (selectedItem && state.entryMeta.load_by_item !== false) {
						if (state.entryMeta.item_change_timer) {
							clearTimeout(state.entryMeta.item_change_timer);
						}
						state.entryMeta.item_change_timer = setTimeout(function () {
							loadSelectedItemProcessRows(selectedItem, true);
						}, 160);
						return;
					}
					scheduleEntryFilterRebuild(100);
				});
			}
			var loadDocBtn = el("pp-entry-load-doc");
			if (loadDocBtn)
				loadDocBtn.addEventListener("click", function () {
					var selected =
						(el("pp-entry-edit-name") && el("pp-entry-edit-name").value) || "";
					loadEntryDocForEdit(selected);
				});
			var deliveryNoteInput = el("pp-entry-delivery-note");
			if (deliveryNoteInput) {
				deliveryNoteInput.addEventListener("input", function () {
					state.entryMeta.delivery_note = normalizeDeliveryNoteValue(
						deliveryNoteInput.value || ""
					);
					scheduleDeliveryNoteSearch(deliveryNoteInput.value || "");
				});
				deliveryNoteInput.addEventListener("change", function () {
					var normalized = normalizeDeliveryNoteValue(deliveryNoteInput.value || "");
					state.entryMeta.delivery_note = normalized;
					deliveryNoteInput.value = normalized;
				});
				deliveryNoteInput.addEventListener("blur", function () {
					var normalized = normalizeDeliveryNoteValue(deliveryNoteInput.value || "");
					state.entryMeta.delivery_note = normalized;
					deliveryNoteInput.value = normalized;
				});
				if (!(state.entryMeta.deliveryNoteOptions || []).length) searchDeliveryNotes("");
			}
			var loadDnBtn = el("pp-entry-load-dn");
			if (loadDnBtn) {
				loadDnBtn.addEventListener("click", function () {
					loadFromDeliveryNote();
				});
			}
			var newDocBtn = el("pp-entry-new-doc");
			if (newDocBtn)
				newDocBtn.addEventListener("click", function () {
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
			if (addBtn)
				addBtn.addEventListener("click", function () {
					state.entryRows.push(newEntryRow());
					renderDataEntryTab();
				});
			var resetBtn = el("pp-entry-reset");
			if (resetBtn)
				resetBtn.addEventListener("click", function () {
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
						state.entryRows[idx].name1 =
							(state.entryMeta.employeeNameMap || {})[
								state.entryRows[idx].employee || ""
							] || "";
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
					state.entryRows = state.entryRows.filter(function (_r, i) {
						return i !== idx;
					});
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
					var qtyInputs = Array.prototype.slice.call(
						wrap.querySelectorAll(".pp-entry-qty")
					);
					var currentIndex = qtyInputs.indexOf(input);
					if (currentIndex < 0) return;
					var nextIndex = ev.shiftKey ? currentIndex - 1 : currentIndex + 1;
					if (nextIndex < 0) nextIndex = 0;
					if (nextIndex >= qtyInputs.length) nextIndex = qtyInputs.length - 1;
					state.entryMeta.focus_qty_index = nextIndex;
					renderDataEntryTab();
				});
			});

			if (
				state.entryMeta.focus_qty_index !== undefined &&
				state.entryMeta.focus_qty_index !== null
			) {
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
						var c = Object.keys(state.entryMeta.selected_docs).filter(function (k) {
							return !!state.entryMeta.selected_docs[k];
						}).length;
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
						var c = Object.keys(state.entryMeta.selected_docs).filter(function (k) {
							return !!state.entryMeta.selected_docs[k];
						}).length;
						countEl.textContent = String(c);
					}
				});
			}
			var bookSelectedBtn = el("pp-entry-doc-book-selected");
			if (bookSelectedBtn) {
				bookSelectedBtn.addEventListener("click", function () {
					var selected = Object.keys(state.entryMeta.selected_docs || {})
						.filter(function (k) {
							return !!state.entryMeta.selected_docs[k];
						})
						.sort(compareEntryNoDesc);
					if (!selected.length) {
						showResult(
							el("pp-entry-result"),
							"error",
							"No Entry Selected",
							"Select one or more entries from Recent Docs first."
						);
						return;
					}
					state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
					if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
					if (el("pp-jv-entry-filter"))
						el("pp-jv-entry-filter").value = state.forcedEntryNo;
					if (el("pp-pay-entry-filter"))
						el("pp-pay-entry-filter").value = state.forcedEntryNo;
					if (el("pp-jv-entry-multi"))
						el("pp-jv-entry-multi").value = selected.join(", ");
					if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = "";
					setWorkflowHistoryRange("salary_creation", "", "");
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var targetBtn = document.querySelector(".pp-tab[data-tab='salary_creation']");
					if (targetBtn) targetBtn.classList.add("active");
					switchWorkspaceMode("entry", true);
					state.currentTab = "salary_creation";
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var activeSalaryBtn = document.querySelector(
						".pp-tab[data-tab='salary_creation']"
					);
					if (activeSalaryBtn) activeSalaryBtn.classList.add("active");
					state.excludedEmployees = {};
					setPageForCurrentTab(1);
					loadReport();
				});
			}
			var paySelectedBtn = el("pp-entry-doc-pay-selected");
			if (paySelectedBtn) {
				paySelectedBtn.addEventListener("click", function () {
					var selected = Object.keys(state.entryMeta.selected_docs || {})
						.filter(function (k) {
							return !!state.entryMeta.selected_docs[k];
						})
						.sort(compareEntryNoDesc);
					if (!selected.length) {
						showResult(
							el("pp-entry-result"),
							"error",
							"No Entry Selected",
							"Select one or more entries from Recent Docs first."
						);
						return;
					}
					state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
					if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
					if (el("pp-pay-entry-filter"))
						el("pp-pay-entry-filter").value = state.forcedEntryNo;
					if (el("pp-jv-entry-filter"))
						el("pp-jv-entry-filter").value = state.forcedEntryNo;
					if (el("pp-pay-entry-multi"))
						el("pp-pay-entry-multi").value = selected.join(", ");
					if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = "";
					setWorkflowHistoryRange("payment_manage", "", "");
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var targetBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
					if (targetBtn) targetBtn.classList.add("active");
					switchWorkspaceMode("entry", true);
					state.currentTab = "payment_manage";
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var activePayBtn = document.querySelector(
						".pp-tab[data-tab='payment_manage']"
					);
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
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var targetBtn = document.querySelector(".pp-tab[data-tab='salary_creation']");
					if (targetBtn) targetBtn.classList.add("active");
					switchWorkspaceMode("entry", true);
					state.currentTab = "salary_creation";
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var activeSalaryBtn2 = document.querySelector(
						".pp-tab[data-tab='salary_creation']"
					);
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
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var targetBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
					if (targetBtn) targetBtn.classList.add("active");
					switchWorkspaceMode("entry", true);
					state.currentTab = "payment_manage";
					document.querySelectorAll(".pp-tab").forEach(function (x) {
						x.classList.remove("active");
					});
					var activePayBtn2 = document.querySelector(
						".pp-tab[data-tab='payment_manage']"
					);
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
					state.historyPageByTab[key] = Math.max(
						1,
						(parseInt(state.historyPageByTab[key] || 1, 10) || 1) - 1
					);
					renderDataEntryTab();
				});
			});
			wrap.querySelectorAll(".pp-history-next").forEach(function (btn) {
				btn.addEventListener("click", function () {
					var key = String(btn.getAttribute("data-key") || "");
					if (!key) return;
					state.historyPageByTab[key] =
						(parseInt(state.historyPageByTab[key] || 1, 10) || 1) + 1;
					renderDataEntryTab();
				});
			});
		}

		function loadEntryDocForEdit(entryName) {
			var result = el("pp-entry-result");
			if (!entryName) {
				showResult(
					result,
					"error",
					"Select Entry",
					"Choose a Per Piece Salary entry to load."
				);
				return;
			}
			if (result) {
				result.style.color = "#334155";
				result.textContent = "Loading entry...";
			}
			callApi("frappe.client.get", { doctype: "Per Piece Salary", name: entryName })
				.then(function (doc) {
					if (!doc) {
						showResult(result, "error", "Load Failed", "Entry not found.");
						return;
					}
					if (Number(doc.docstatus || 0) !== 0) {
						showResult(
							result,
							"error",
							"Cannot Edit",
							"Only Draft entries can be edited in this tab."
						);
						return;
					}
					state.entryMeta.edit_name = doc.name || "";
					state.entryMeta.from_date = doc.from_date || "";
					state.entryMeta.to_date = doc.to_date || "";
					state.entryMeta.employee = doc.employee || "";
					state.entryMeta.item_group = doc.item_group || "";
					state.entryMeta.item = doc.item || "";
					state.entryMeta.load_by_item =
						doc.load_by_item === undefined ? true : !!Number(doc.load_by_item);
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
							rate_manual: true,
						};
					});
					ensureEntryRows();
					renderDataEntryTab();
					showResult(
						el("pp-entry-result"),
						"success",
						"Entry Loaded",
						"Now update rows and click Update Per Piece Salary."
					);
				})
				.catch(function (e) {
					showResult(result, "error", "Load Failed", prettyError(errText(e)));
					console.error(e);
				});
		}

		function saveDataEntry() {
			var result = el("pp-entry-result");
			var fromDate = el("pp-entry-from-date").value || state.entryMeta.from_date || "";
			var toDate = el("pp-entry-to-date").value || state.entryMeta.to_date || "";
			var employee =
				(el("pp-entry-employee") && el("pp-entry-employee").value) ||
				state.entryMeta.employee ||
				"";
			var itemGroup =
				(el("pp-entry-item-group") && el("pp-entry-item-group").value) ||
				state.entryMeta.item_group ||
				"";
			var loadByItem = !!state.entryMeta.load_by_item;
			var selectedItemSingle =
				(el("pp-entry-item") && el("pp-entry-item").value) || state.entryMeta.item || "";
			var po = el("pp-entry-po-number").value || state.entryMeta.po_number || "";
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
				showResult(
					result,
					"error",
					"PO Number Required",
					"Enter PO Number before saving."
				);
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
				showResult(
					result,
					"error",
					"Item Required",
					"Select Item or uncheck Load By Item."
				);
				return;
			}
			var lines = [];
			(state.entryRows || []).forEach(function (r) {
				var qty = whole(r.qty);
				if (qty <= 0) return;
				lines.push(
					[
						String(r.employee || "").trim(),
						String(r.name1 || "").trim(),
						String(r.product || "").trim(),
						String(r.process_type || "").trim(),
						String(r.process_size || "No Size").trim(),
						qty,
						whole(r.rate),
						String(r.sales_order || "").trim(),
					].join("::")
				);
			});
			if (!lines.length) {
				showResult(result, "error", "Cannot Save", "Enter at least one row with Qty.");
				return;
			}
			result.style.color = "#334155";
			result.textContent = editName ? "Updating data entry..." : "Saving data entry...";
			callApi("per_piece_payroll.api.create_per_piece_salary_entry", {
				entry_name: editName,
				from_date: fromDate,
				to_date: toDate,
				employee: employee,
				item_group: itemGroup,
				item: selectedItemSingle,
				selected_items: selectedItemSingle ? String(selectedItemSingle) : "",
				load_by_item: loadByItem ? 1 : 0,
				po_number: po,
				rows: lines.join(";;"),
			})
				.then(function (msg) {
					var link =
						"<a target='_blank' href='/app/per-piece-salary/" +
						encodeURIComponent(msg.name) +
						"'>" +
						esc(msg.name) +
						"</a>";
					result.style.color = "#0f766e";
					result.innerHTML =
						(msg.action === "updated" ? "Updated: " : "Saved: ") +
						link +
						" | Rows: " +
						esc(msg.rows) +
						" | Qty: " +
						esc(fmt(msg.total_qty)) +
						" | Amount: " +
						esc(fmt(msg.total_amount));
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
				})
				.catch(function (e) {
					showResult(result, "error", "Save Failed", prettyError(errText(e)));
					console.error(e);
				});
		}

		return {
			renderDataEntryTab: renderDataEntryTab,
			loadEntryDocForEdit: loadEntryDocForEdit,
			saveDataEntry: saveDataEntry,
		};
	}

	window.PerPieceEntryUI = { create: create };
})();
