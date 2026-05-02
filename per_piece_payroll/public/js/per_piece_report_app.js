(function () {
	var core = window.PerPieceReportCore || {};
	var state = core.state || {};
	var el =
		core.el ||
		function (id) {
			return document.getElementById(id);
		};
	var esc =
		core.esc ||
		function (v) {
			var d = document.createElement("div");
			d.textContent = v == null ? "" : String(v);
			return d.innerHTML;
		};
	var num =
		core.num ||
		function (v) {
			var n = Number(v || 0);
			return isNaN(n) ? 0 : n;
		};
	var whole =
		core.whole ||
		function (v) {
			return Math.max(0, Math.round(num(v) * 100) / 100);
		};
	var fmt =
		core.fmt ||
		function (v) {
			return num(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
		};
	var isGuestSession =
		core.isGuestSession ||
		function () {
			return false;
		};
	var redirectToLogin = core.redirectToLogin || function () {};
	var ensureLoggedInOrRedirect =
		core.ensureLoggedInOrRedirect ||
		function () {
			return false;
		};
	var entrySequenceNo =
		core.entrySequenceNo ||
		function (name) {
			return 0;
		};
	var compareEntryNoDesc =
		core.compareEntryNoDesc ||
		function (a, b) {
			return 0;
		};
	var lineRate =
		core.lineRate ||
		function (rate, qty, amount) {
			return 0;
		};
	var applyReportRateProcessFix = core.applyReportRateProcessFix || function () {};
	var normalizeReportStatusValues = core.normalizeReportStatusValues || function () {};
	var parseDecimalInput =
		core.parseDecimalInput ||
		function (v) {
			return 0;
		};
	var baseProcessSizeOptions =
		core.baseProcessSizeOptions ||
		function () {
			return ["No Size"];
		};
	var getProcessSortRank =
		core.getProcessSortRank ||
		function () {
			return 999999;
		};
	var compareByProcessSequence =
		core.compareByProcessSequence ||
		function () {
			return 0;
		};
	var isStatusField =
		core.isStatusField ||
		function () {
			return false;
		};
	var isAmountField =
		core.isAmountField ||
		function () {
			return false;
		};
	var statusBadgeHtml =
		core.statusBadgeHtml ||
		function (v) {
			return String(v || "");
		};
	var getSearchTerm =
		core.getSearchTerm ||
		function () {
			return "";
		};
	var filterRowsByColumns =
		core.filterRowsByColumns ||
		function (rows) {
			return rows || [];
		};
	var filterRowsByKeys =
		core.filterRowsByKeys ||
		function (rows) {
			return rows || [];
		};
	var filterRenderedTablesBySearch = core.filterRenderedTablesBySearch || function () {};
	var avgRate =
		core.avgRate ||
		function () {
			return 0;
		};
	var employeeLabel =
		core.employeeLabel ||
		function (row) {
			return "";
		};
	var currentCompanyLabel =
		core.currentCompanyLabel ||
		function () {
			return "";
		};
	var currentDateRangeLabel =
		core.currentDateRangeLabel ||
		function () {
			return "";
		};
	var getCurrentTabLabel =
		core.getCurrentTabLabel ||
		function () {
			return "";
		};
	var setSummaryHeading = core.setSummaryHeading || function () {};
	var summaryHeaderHtml =
		core.summaryHeaderHtml ||
		function () {
			return "";
		};
	var setSummaryModal = core.setSummaryModal || function () {};

	function advanceMonthField(key) {
		return "adv_" + String(key || "").replace("-", "_");
	}
	var utils =
		(window.PerPieceReportUtils &&
			window.PerPieceReportUtils.create({
				el: el,
				esc: esc,
				isGuestSession: isGuestSession,
				redirectToLogin: redirectToLogin,
			})) ||
		{};

	var errText =
		utils.errText ||
		function (e) {
			return String((e && e.message) || "Request failed");
		};
	var prettyError =
		utils.prettyError ||
		function (m) {
			return String(m || "");
		};
	var showResult = utils.showResult || function () {};
	var setActionIcon = utils.setActionIcon || function () {};
	var showActionModal = utils.showActionModal || function () {};
	var hideActionModal = utils.hideActionModal || function () {};
	var confirmActionModal =
		utils.confirmActionModal ||
		function () {
			return Promise.resolve(false);
		};
	var notifyActionResult = utils.notifyActionResult || function () {};
	var getCsrfToken =
		utils.getCsrfToken ||
		function () {
			return "";
		};
	var encodeArgs =
		utils.encodeArgs ||
		function () {
			return "";
		};
	var callApi =
		utils.callApi ||
		function () {
			return Promise.reject(new Error("callApi unavailable"));
		};
	var callGetList =
		utils.callGetList ||
		function () {
			return Promise.resolve([]);
		};
	var setOptions = utils.setOptions || function () {};

	var salarySlip =
		(window.PerPieceSalarySlip &&
			window.PerPieceSalarySlip.create({
				state: state,
				el: el,
				esc: esc,
				num: num,
				fmt: fmt,
				avgRate: avgRate,
				callApi: callApi,
				compareByProcessSequence: compareByProcessSequence,
				getRowsByHeaderFilters: getRowsByHeaderFilters,
				currentDateRangeLabel: currentDateRangeLabel,
				summaryHeaderHtml: summaryHeaderHtml,
				setSummaryModal: setSummaryModal,
				prettyError: prettyError,
				errText: errText,
			})) ||
		{};

	var buildSalarySlipGroupDetail =
		salarySlip.buildSalarySlipGroupDetail ||
		function () {
			return null;
		};
	var getJournalEntryDoc =
		salarySlip.getJournalEntryDoc ||
		function () {
			return Promise.resolve(null);
		};
	var getSalarySlipFinancials =
		salarySlip.getSalarySlipFinancials ||
		function () {
			return Promise.resolve({});
		};
	var buildSalarySlipGroups =
		salarySlip.buildSalarySlipGroups ||
		function () {
			return [];
		};
	var showSalarySlipPrint = salarySlip.showSalarySlipPrint || function () {};
	var showSalarySlipByEntry = salarySlip.showSalarySlipByEntry || function () {};
	var showSalaryEntryWisePrints = salarySlip.showSalaryEntryWisePrints || function () {};

	function refreshTopProductOptions() {
		var productSelect = el("pp-product");
		if (!productSelect) return;
		var selectedItemGroup = String(
			(el("pp-item-group") && el("pp-item-group").value) || ""
		).trim();
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

		// Fallback: if selected Item Group has no products in report/process caches,
		// load directly from Item master for that Item Group.
		if (selectedItemGroup && !productRows.length) {
			callGetList(
				"Item",
				["name"],
				[
					["disabled", "=", 0],
					["item_group", "=", selectedItemGroup],
				],
				2000
			)
				.then(function (rows) {
					var masterRows = (rows || [])
						.map(function (r) {
							var n = String((r && r.name) || "").trim();
							return n ? { value: n, label: n } : null;
						})
						.filter(function (r) {
							return !!r;
						});
					masterRows.sort(function (a, b) {
						return String(a.label || "").localeCompare(String(b.label || ""));
					});
					setOptions(productSelect, masterRows, "value", "label", "All");
					if (
						currentProduct &&
						masterRows.some(function (r) {
							return r.value === currentProduct;
						})
					) {
						productSelect.value = currentProduct;
					}
				})
				.catch(function () {});
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
		} catch (e) {
			/* ignore storage errors */
		}
		return {
			from_date: fromVal,
			to_date: toVal,
			company: el("pp-company") ? el("pp-company").value || "" : "",
			employee: el("pp-employee").value || "",
			item_group: el("pp-item-group") ? el("pp-item-group").value || "" : "",
			delivery_note: el("pp-delivery-note")
				? String(el("pp-delivery-note").value || "").trim()
				: "",
			product: el("pp-product").value || "",
			process_type: el("pp-process-type").value || "",
			sales_order: el("pp-sales-order") ? el("pp-sales-order").value || "" : "",
			booking_status: el("pp-booking-status") ? el("pp-booking-status").value || "" : "",
			payment_status: el("pp-payment-status") ? el("pp-payment-status").value || "" : "",
			po_number: el("pp-po-number") ? el("pp-po-number").value || "" : "",
			entry_no: el("pp-entry-no") ? el("pp-entry-no").value || "" : "",
			max_rows: "0",
			max_days: "0",
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
		var poRows = Object.keys(poMap)
			.sort()
			.reverse()
			.map(function (v) {
				return { value: v, label: v };
			});
		var entryRows = Object.keys(entryMap)
			.sort()
			.reverse()
			.map(function (v) {
				return { value: v, label: v };
			});
		setOptions(poSelect, poRows, "value", "label", "All");
		setOptions(entrySelect, entryRows, "value", "label", "All");
		if (currentPo && poMap[currentPo]) poSelect.value = currentPo;
		if (currentEntry && entryMap[currentEntry]) entrySelect.value = currentEntry;
	}

	function getRowsByHeaderFilters(rows, options) {
		var opts = options || {};
		var po = el("pp-po-number") ? String(el("pp-po-number").value || "").trim() : "";
		var deliveryNote = el("pp-delivery-note")
			? String(el("pp-delivery-note").value || "").trim()
			: "";
		var salesOrder = el("pp-sales-order")
			? String(el("pp-sales-order").value || "").trim()
			: "";
		var entry = String(state.forcedEntryNo || "").trim();
		var booking = el("pp-booking-status")
			? String(el("pp-booking-status").value || "").trim()
			: "";
		var payment = el("pp-payment-status")
			? String(el("pp-payment-status").value || "").trim()
			: "";
		var company = el("pp-company") ? String(el("pp-company").value || "").trim() : "";
		var from = String((el("pp-from-date") && el("pp-from-date").value) || "").trim();
		var to = String((el("pp-to-date") && el("pp-to-date").value) || "").trim();
		if (!entry && el("pp-entry-no")) entry = String(el("pp-entry-no").value || "").trim();
		if (opts.ignore_entry_filter) entry = "";
		if (opts.ignore_po_filter) po = "";
		if (opts.ignore_delivery_note_filter) deliveryNote = "";
		if (opts.ignore_sales_order_filter) salesOrder = "";
		if (opts.ignore_date_filter) {
			from = "";
			to = "";
		}
		if (opts.ignore_status_filter) {
			booking = "";
			payment = "";
		}
		if (opts.ignore_company_filter) {
			company = "";
		}
		return (rows || []).filter(function (r) {
			var rowFrom = String((r && r.from_date) || "").trim();
			var rowTo = String((r && r.to_date) || "").trim();
			if (from && rowFrom && rowFrom < from) return false;
			if (to && rowTo && rowTo > to) return false;
			if (po && String(r.po_number || "") !== po) return false;
			if (deliveryNote && String(r.delivery_note || "").trim() !== deliveryNote)
				return false;
			if (salesOrder && String(r.sales_order || "") !== salesOrder) return false;
			if (entry && String(r.per_piece_salary || "") !== entry) return false;
			if (company && String(r.company || "").trim() !== company) return false;
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
		return n < 10 ? "0" + n : String(n);
	}

	function ymd(d) {
		if (!d) return "";
		return String(d.getFullYear()) + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
	}

	function buildLast6Months(toDate) {
		var monthNames = [
			"Jan",
			"Feb",
			"Mar",
			"Apr",
			"May",
			"Jun",
			"Jul",
			"Aug",
			"Sep",
			"Oct",
			"Nov",
			"Dec",
		];
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
			payment: String(src.payment || "").trim(),
		};
	}

	function setWorkflowStatusFilter(tabName, bookingStatus, paymentStatus) {
		var key = String(tabName || "").trim();
		if (!state.workflowStatusFilter[key])
			state.workflowStatusFilter[key] = { booking: "", payment: "" };
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
		months.forEach(function (m) {
			monthMap[m.key] = true;
		});
		var firstMonthDate =
			(months[0] && months[0].key ? months[0].key : toDate.slice(0, 7)) + "-01";

		function getAccountCandidates() {
			var p1 = callGetList(
				"Account",
				["name"],
				[["name", "like", "%Employee Advance%"]],
				2000
			).catch(function () {
				return [];
			});
			var p2 = callGetList(
				"Account",
				["name"],
				[["account_name", "like", "%Employee Advance%"]],
				2000
			).catch(function () {
				return [];
			});
			return Promise.all([p1, p2]).then(function (parts) {
				var map = {};
				(parts[0] || []).forEach(function (r) {
					if (r && r.name) map[r.name] = true;
				});
				(parts[1] || []).forEach(function (r) {
					if (r && r.name) map[r.name] = true;
				});
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
					months.forEach(function (m) {
						monthValues[m.key] = 0;
					});
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
				var amount = num(amountFn(g));

				if (postDate < firstMonthDate) {
					advMap[emp].opening_balance += amount;
				} else if (postDate <= toDate) {
					var key = postDate.slice(0, 7);
					if (monthMap[key]) advMap[emp].month_values[key] += amount;
				}
			});

			var rows = [];
			Object.keys(advMap)
				.sort()
				.forEach(function (emp) {
					var rec = advMap[emp];
					var running = num(rec.opening_balance);
					months.forEach(function (m) {
						running += num(rec.month_values[m.key]);
					});
					rec.opening_balance = Math.round(num(rec.opening_balance) * 100) / 100;
					rec.closing_balance = Math.round(running * 100) / 100;
					rec.advance_balance = rec.closing_balance;
					if (
						Math.abs(rec.closing_balance) < 0.01 &&
						Math.abs(rec.opening_balance) < 0.01
					)
						return;
					rows.push(rec);
				});

			var balMap = {};
			rows.forEach(function (r) {
				balMap[r.employee] = num(r.advance_balance);
			});
			state.advanceRows = rows;
			state.advanceMonths = months;
			state.advanceBalances = balMap;
		}

		return Promise.all([
			callGetList("Employee", ["name", "employee_name", "branch"], {}, 20000).catch(
				function () {
					return [];
				}
			),
			callGetList(
				"Employee Advance",
				["employee", "posting_date", "paid_amount", "claimed_amount", "return_amount"],
				selectedEmployee
					? [
							["docstatus", "=", 1],
							["posting_date", "<=", toDate],
							["employee", "=", selectedEmployee],
					  ]
					: [
							["docstatus", "=", 1],
							["posting_date", "<=", toDate],
					  ],
				20000
			).catch(function () {
				return [];
			}),
		]).then(function (initialParts) {
			var empRows = initialParts[0] || [];
			var advanceDocs = initialParts[1] || [];
			empRows.forEach(function (e) {
				if (!e || !e.name) return;
				empMap[e.name] = {
					name1: e.employee_name || e.name,
					branch: e.branch || "",
				};
			});

			return getAccountCandidates().then(function (accounts) {
				if (!accounts || !accounts.length) {
					if (advanceDocs.length) {
						buildAdvanceState(advanceDocs, function (g) {
							return (
								num(g.paid_amount) - num(g.claimed_amount) - num(g.return_amount)
							);
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

				return callGetList(
					"GL Entry",
					["party", "posting_date", "debit", "credit"],
					glFilters,
					20000
				).then(function (glRows) {
					if (glRows && glRows.length) {
						buildAdvanceState(glRows || [], function (g) {
							return num(g.debit) - num(g.credit);
						});
						return;
					}
					if (advanceDocs.length) {
						buildAdvanceState(advanceDocs, function (g) {
							return (
								num(g.paid_amount) - num(g.claimed_amount) - num(g.return_amount)
							);
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
		return callApi("per_piece_payroll.api.get_per_piece_salary_report", {
			get_options: 1,
		}).then(function (m) {
			var currentEmployee = el("pp-employee") ? el("pp-employee").value || "" : "";
			var currentCompany = el("pp-company") ? el("pp-company").value || "" : "";
			var currentItemGroup = el("pp-item-group") ? el("pp-item-group").value || "" : "";
			var currentProcessType = el("pp-process-type")
				? el("pp-process-type").value || ""
				: "";
			var currentSalesOrder = el("pp-sales-order") ? el("pp-sales-order").value || "" : "";
			state.filterOptions = {
				employees: (m && m.employees) || [],
				item_groups: (m && m.item_groups) || [],
				products: (m && m.products) || [],
				process_types: (m && m.process_types) || [],
				sales_orders: (m && m.sales_orders) || [],
				companies: (m && m.companies) || [],
			};
			var companies = (state.filterOptions.companies || []).map(function (v) {
				return { value: v, label: v };
			});
			var emps = (state.filterOptions.employees || []).map(function (v) {
				return { value: v, label: v };
			});
			var itemGroups = (state.filterOptions.item_groups || []).map(function (v) {
				return { value: v, label: v };
			});
			var ptypes = ((m && m.process_types) || []).map(function (v) {
				return { value: v, label: v };
			});
			var salesOrders = (state.filterOptions.sales_orders || []).map(function (v) {
				return { value: v, label: v };
			});
			salesOrders.sort(function (a, b) {
				return compareEntryNoDesc(a && a.value, b && b.value);
			});
			state.advanceBalances = (m && m.advance_balances) || {};
			state.advanceRows = (m && m.advance_rows) || [];
			state.advanceMonths = (m && m.advance_months) || [];
			setOptions(el("pp-company"), companies, "value", "label", "All");
			setOptions(el("pp-employee"), emps, "value", "label", "All");
			setOptions(el("pp-item-group"), itemGroups, "value", "label", "All");
			setOptions(el("pp-process-type"), ptypes, "value", "label", "All");
			setOptions(el("pp-sales-order"), salesOrders, "value", "label", "All");
			if (el("pp-company")) el("pp-company").value = currentCompany;
			if (el("pp-employee")) el("pp-employee").value = currentEmployee;
			if (el("pp-item-group")) el("pp-item-group").value = currentItemGroup;
			if (el("pp-process-type")) el("pp-process-type").value = currentProcessType;
			if (el("pp-sales-order")) el("pp-sales-order").value = currentSalesOrder;
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
					return {
						value: r.name,
						label: (r.employee_name || r.name) + " (" + r.name + ")",
					};
				});
				(rows || []).forEach(function (r) {
					if (!state.entryMeta.employeeNameMap) state.entryMeta.employeeNameMap = {};
					if (r.name && r.employee_name)
						state.entryMeta.employeeNameMap[r.name] = r.employee_name;
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
		return callApi("per_piece_payroll.api.get_per_piece_salary_report", {
			from_date: "2000-01-01",
			to_date: "2099-12-31",
		})
			.then(function (msg) {
				state.entryMeta.recentRows = (msg && msg.data) || [];
				applyReportRateProcessFix(state.entryMeta.recentRows);
				normalizeReportStatusValues(state.entryMeta.recentRows);
			})
			.catch(function () {
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
				var nameOnly = text.replace(/\s*\([^)]*\)\s*$/, "").trim();
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
			if (
				(!currentItemGroup || itemGroup === currentItemGroup) &&
				(!hasSelected || selectedMap[itemName])
			) {
				productSet[itemName] = true;
			}
			if (processType) processSet[processType] = true;
			if (processSize) processSizeSet[processSize] = true;
		});

		(state.filterOptions.employees || []).forEach(function (v) {
			if (v) employeeSet[String(v)] = true;
		});
		(state.filterOptions.item_groups || []).forEach(function (v) {
			if (v) itemGroupSet[String(v)] = true;
		});
		(state.filterOptions.products || []).forEach(function (v) {
			var productName = String(v || "").trim();
			if (!productName) return;
			var meta = productMetaMap[productName] || {};
			if (!currentItemGroup || !meta.item_group || meta.item_group === currentItemGroup) {
				productSet[productName] = true;
			}
		});
		(state.filterOptions.process_types || []).forEach(function (v) {
			if (v) processSet[String(v)] = true;
		});

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
			if (
				product &&
				(!currentItemGroup || !itemGroup || itemGroup === currentItemGroup) &&
				(!hasSelected || selectedMap[product])
			)
				productSet[product] = true;
			if (processType) processSet[processType] = true;
			if (processSize) processSizeSet[processSize] = true;
			if (product) {
				if (!productMetaMap[product]) productMetaMap[product] = {};
				if (itemGroup && !productMetaMap[product].item_group)
					productMetaMap[product].item_group = itemGroup;
				if (processType && !productMetaMap[product].process_type)
					productMetaMap[product].process_type = processType;
				if (processSize && !productMetaMap[product].process_size)
					productMetaMap[product].process_size = processSize;
				if (rate > 0 && !productMetaMap[product].rate) productMetaMap[product].rate = rate;
			}
		});

		var employeeOrdered = [];
		(state.entryMeta.masterEmployeeOptions || []).forEach(function (opt) {
			var emp = String((opt && opt.value) || "").trim();
			if (emp && employeeSet[emp]) employeeOrdered.push(emp);
		});
		Object.keys(employeeSet)
			.sort()
			.forEach(function (emp) {
				if (employeeOrdered.indexOf(emp) < 0) employeeOrdered.push(emp);
			});

		var itemGroupOrdered = [];
		(state.entryMeta.masterItemGroupOptions || []).forEach(function (opt) {
			var group = String((opt && opt.value) || "").trim();
			if (group && itemGroupSet[group]) itemGroupOrdered.push(group);
		});
		Object.keys(itemGroupSet)
			.sort()
			.forEach(function (group) {
				if (itemGroupOrdered.indexOf(group) < 0) itemGroupOrdered.push(group);
			});

		var productOrdered = [];
		(state.entryMeta.masterProcessRows || []).forEach(function (item) {
			var product = String((item && item.item) || "").trim();
			if (product && productSet[product] && productOrdered.indexOf(product) < 0)
				productOrdered.push(product);
		});
		Object.keys(productSet)
			.sort()
			.forEach(function (product) {
				if (productOrdered.indexOf(product) < 0) productOrdered.push(product);
			});

		var processOrdered = [];
		(state.entryMeta.masterProcessRows || []).forEach(function (item) {
			var process = String((item && item.process_type) || "").trim();
			if (process && processSet[process] && processOrdered.indexOf(process) < 0)
				processOrdered.push(process);
		});
		Object.keys(processSet)
			.sort()
			.forEach(function (process) {
				if (processOrdered.indexOf(process) < 0) processOrdered.push(process);
			});

		state.entryMeta.employeeOptions = employeeOrdered.map(function (emp) {
			var label = employeeNameMap[emp] ? employeeNameMap[emp] + " (" + emp + ")" : emp;
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
		state.entryMeta.processSizeOptions = Object.keys(processSizeSet)
			.sort(function (a, b) {
				var order = baseProcessSizeOptions();
				var ai = order.indexOf(a);
				var bi = order.indexOf(b);
				if (ai < 0 && bi < 0) return String(a).localeCompare(String(b));
				if (ai < 0) return 1;
				if (bi < 0) return -1;
				return ai - bi;
			})
			.map(function (value) {
				return { value: value, label: value };
			});
		state.entryMeta.employeeNameMap = employeeNameMap;
		state.entryMeta.productMetaMap = productMetaMap;
		state.entryMeta.productProcessMap = productProcessMap;
	}

	var builders =
		(window.PerPieceBuilders &&
			window.PerPieceBuilders.create({
				state: state,
				el: el,
				num: num,
				avgRate: avgRate,
				compareByProcessSequence: compareByProcessSequence,
				parseDateOnly: parseDateOnly,
				pad2: pad2,
				getReportArgs: getReportArgs,
				advanceMonthField: advanceMonthField,
			})) ||
		{};

	var groupRows =
		builders.groupRows ||
		function () {
			return [];
		};
	var buildEmployeeSummaryRows =
		builders.buildEmployeeSummaryRows ||
		function () {
			return [];
		};
	var buildEmployeeSummaryReportRows =
		builders.buildEmployeeSummaryReportRows ||
		function () {
			return [];
		};
	var buildEmployeeItemWiseReportRows =
		builders.buildEmployeeItemWiseReportRows ||
		function () {
			return [];
		};
	var normalizeBookedAmounts =
		builders.normalizeBookedAmounts ||
		function (row) {
			return row || {};
		};
	var buildProductSummaryDetailRows =
		builders.buildProductSummaryDetailRows ||
		function () {
			return [];
		};
	var buildProcessSummaryRows =
		builders.buildProcessSummaryRows ||
		function () {
			return [];
		};
	var monthFieldFromKey =
		builders.monthFieldFromKey ||
		function (k) {
			return String(k || "");
		};
	var monthLabelFromKey =
		builders.monthLabelFromKey ||
		function (k) {
			return String(k || "");
		};
	var monthsInFilterRange =
		builders.monthsInFilterRange ||
		function () {
			return [];
		};
	var buildSimpleMonthColumns =
		builders.buildSimpleMonthColumns ||
		function () {
			return [];
		};
	var buildSimpleMonthRows =
		builders.buildSimpleMonthRows ||
		function () {
			return [];
		};
	var buildEmployeeMonthYearRows =
		builders.buildEmployeeMonthYearRows ||
		function () {
			return [];
		};
	var buildMonthPaidUnpaidRows =
		builders.buildMonthPaidUnpaidRows ||
		function () {
			return [];
		};
	var buildAdvanceRows =
		builders.buildAdvanceRows ||
		function () {
			return [];
		};

	function getNetBookedAmountForRow(r) {
		// Payment base must stay entry-specific and equal finalized Net Salary.
		var net = Math.max(num((r && r.net_amount) || 0), 0);
		if (net > 0) return net;
		// Legacy safeguard: when row has no deductions/allowances, booked should equal amount.
		var amount = Math.max(num((r && r.amount) || 0), 0);
		var booked = Math.max(num((r && r.booked_amount) || 0), 0);
		var hasAllowance = r && Object.prototype.hasOwnProperty.call(r, "allowance");
		var hasAdvance = r && Object.prototype.hasOwnProperty.call(r, "advance_deduction");
		var hasOther = r && Object.prototype.hasOwnProperty.call(r, "other_deduction");
		var allowance = Math.abs(num((r && r.allowance) || 0));
		var advance = Math.abs(num((r && r.advance_deduction) || 0));
		var other = Math.abs(num((r && r.other_deduction) || 0));
		var noSplits =
			hasAllowance &&
			hasAdvance &&
			hasOther &&
			allowance <= 0.005 &&
			advance <= 0.005 &&
			other <= 0.005;
		if (noSplits && amount > 0 && (booked <= 0 || booked + 0.005 < amount)) {
			return amount;
		}
		if (booked > 0) return booked;
		return amount;
	}

	var stateCalc =
		(window.PerPieceState &&
			window.PerPieceState.create({
				state: state,
				el: el,
				esc: esc,
				num: num,
				whole: whole,
				avgRate: avgRate,
				statusBadgeHtml: statusBadgeHtml,
				entrySequenceNo: entrySequenceNo,
				compareEntryNoDesc: compareEntryNoDesc,
				getRowsByHeaderFilters: getRowsByHeaderFilters,
				filterRowsByDateRange: filterRowsByDateRange,
				getWorkflowHistoryRange: getWorkflowHistoryRange,
				setOptions: setOptions,
				buildEmployeeSummaryRows: buildEmployeeSummaryRows,
				getBookedAmountForPaymentRow: getNetBookedAmountForRow,
			})) ||
		{};

	var getUnpostedRows =
		stateCalc.getUnpostedRows ||
		function () {
			return [];
		};
	var getBookedRows =
		stateCalc.getBookedRows ||
		function () {
			return [];
		};
	var buildPaymentEmployeeRows =
		stateCalc.buildPaymentEmployeeRows ||
		function () {
			return [];
		};
	var normalizePaymentAdjustments = stateCalc.normalizePaymentAdjustments || function () {};
	var normalizePaymentExcludedEmployees =
		stateCalc.normalizePaymentExcludedEmployees || function () {};
	var getPaymentRows =
		stateCalc.getPaymentRows ||
		function () {
			return [];
		};
	var isPaymentOpenRow =
		stateCalc.isPaymentOpenRow ||
		function () {
			return false;
		};
	var getPaymentActiveRows =
		stateCalc.getPaymentActiveRows ||
		function () {
			return [];
		};
	var getPaymentPostingRows =
		stateCalc.getPaymentPostingRows ||
		function () {
			return [];
		};
	var getUnbookedEntryOptions =
		stateCalc.getUnbookedEntryOptions ||
		function () {
			return [];
		};
	var getUnpaidEntryOptions =
		stateCalc.getUnpaidEntryOptions ||
		function () {
			return [];
		};
	var getEntrySummary =
		stateCalc.getEntrySummary ||
		function () {
			return null;
		};
	var refreshWorkflowEntrySelectors = stateCalc.refreshWorkflowEntrySelectors || function () {};
	var resetEntryFiltersToAll = stateCalc.resetEntryFiltersToAll || function () {};
	var parseEntryNoList =
		stateCalc.parseEntryNoList ||
		function () {
			return [];
		};
	var getSelectedEntryNosForTab =
		stateCalc.getSelectedEntryNosForTab ||
		function () {
			return [];
		};
	var filterRowsBySelectedEntries =
		stateCalc.filterRowsBySelectedEntries ||
		function (rows) {
			return rows || [];
		};
	var getPaymentTotals =
		stateCalc.getPaymentTotals ||
		function () {
			return { booked: 0, paid: 0, unpaid: 0, payment: 0, debit: 0, credit: 0 };
		};
	var normalizeAdjustmentsForEmployees =
		stateCalc.normalizeAdjustmentsForEmployees || function () {};
	var normalizeExcludedEmployees = stateCalc.normalizeExcludedEmployees || function () {};
	var withAdjustments =
		stateCalc.withAdjustments ||
		function (row) {
			return row || {};
		};
	var getAdjustedEmployeeRows =
		stateCalc.getAdjustedEmployeeRows ||
		function () {
			return [];
		};
	var getPostingEmployeeRows =
		stateCalc.getPostingEmployeeRows ||
		function () {
			return [];
		};
	var getAdjustedTotals =
		stateCalc.getAdjustedTotals ||
		function () {
			return {
				qty: 0,
				base_amount: 0,
				allowance_amount: 0,
				gross_amount: 0,
				advance_deduction_amount: 0,
				other_deduction_amount: 0,
				net_payable_amount: 0,
				jv_gross_amount: 0,
				debit_amount: 0,
				credit_amount: 0,
			};
		};

	var views =
		(window.PerPieceViews &&
			window.PerPieceViews.create({
				state: state,
				el: el,
				esc: esc,
				num: num,
				whole: whole,
				fmt: fmt,
				isStatusField: isStatusField,
				isAmountField: isAmountField,
				statusBadgeHtml: statusBadgeHtml,
				employeeLabel: employeeLabel,
				setSummaryHeading: setSummaryHeading,
				getCurrentTabLabel: getCurrentTabLabel,
				filterRenderedTablesBySearch: filterRenderedTablesBySearch,
				getSearchTerm: getSearchTerm,
				avgRate: avgRate,
				getAdjustedEmployeeRows: getAdjustedEmployeeRows,
				normalizeExcludedEmployees: normalizeExcludedEmployees,
				normalizeAdjustmentsForEmployees: normalizeAdjustmentsForEmployees,
				getAdjustedTotals: getAdjustedTotals,
				getPaymentActiveRows: getPaymentActiveRows,
				normalizePaymentExcludedEmployees: normalizePaymentExcludedEmployees,
				normalizePaymentAdjustments: normalizePaymentAdjustments,
				getPaymentTotals: getPaymentTotals,
				setWorkflowHistoryRange: setWorkflowHistoryRange,
				switchWorkspaceMode: switchWorkspaceMode,
				setPageForCurrentTab: setPageForCurrentTab,
				loadReport: loadReport,
				renderCurrentTab: renderCurrentTab,
				getPaymentPostingRows: getPaymentPostingRows,
				showPerPieceSummary: function () {
					return showPerPieceSummary.apply(null, arguments);
				},
				showPOSummary: function () {
					return showPOSummary.apply(null, arguments);
				},
				showDataEntryEmployeeDetails: function () {
					return showDataEntryEmployeeDetails.apply(null, arguments);
				},
				showSalaryEmployeeDetail: function () {
					return showSalaryEmployeeDetail.apply(null, arguments);
				},
				showSalarySlipPrint: showSalarySlipPrint,
				showSalarySlipByEntry: showSalarySlipByEntry,
				showSalaryEntryWisePrints: showSalaryEntryWisePrints,
				parseDecimalInput: parseDecimalInput,
				buildSalarySlipGroups: buildSalarySlipGroups,
			})) ||
		{};

	var renderTable = views.renderTable || function () {};
	var renderPoDetailPrintTab = views.renderPoDetailPrintTab || function () {};
	var renderSalaryTable = views.renderSalaryTable || function () {};
	var renderEmployeeSummaryTable = views.renderEmployeeSummaryTable || function () {};
	var renderSalarySlipTable = views.renderSalarySlipTable || function () {};
	var renderSalarySlipByDCTable = views.renderSalarySlipByDCTable || function () {};
	var renderPaymentTable = views.renderPaymentTable || function () {};
	var setJVAmounts = views.setJVAmounts || function () {};
	var refreshJVAmountsFromAdjustments = views.refreshJVAmountsFromAdjustments || function () {};
	var setPaymentAmounts = views.setPaymentAmounts || function () {};
	var refreshPaymentAmounts = views.refreshPaymentAmounts || function () {};

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
					delivery_note: r.delivery_note || "",
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
					payment_status: "Unpaid",
				};
			}
			if (
				!String(map[key].delivery_note || "").trim() &&
				String(r.delivery_note || "").trim()
			) {
				map[key].delivery_note = r.delivery_note;
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
			if (unpaidVal < 0 || unpaidVal > bookedVal)
				unpaidVal = Math.max(bookedVal - paidVal, 0);
			map[key].booked_amount += bookedVal;
			map[key].unbooked_amount += isBooked ? 0 : Math.max(amount - bookedVal, 0);
			map[key].paid_amount += paidVal;
			map[key].unpaid_amount += unpaidVal;
			map[key]._row_count += 1;
			if (isBooked) map[key]._booked_count += 1;
		});
		return Object.keys(map)
			.sort(compareEntryNoDesc)
			.map(function (k) {
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
				delivery_note: r.delivery_note || "",
				sales_order: r.sales_order || "",
				product: r.product || "",
				process_type: r.process_type || "",
				process_size: r.process_size || "No Size",
				qty: num(r.qty),
				rate: num(r.rate),
				amount: num(r.amount),
				booking_status: r.booking_status || "UnBooked",
				payment_status: r.payment_status || "Unpaid",
			});
		});
		return rows;
	}

	function filterDataEntryDocsByDate(docs) {
		var fromInput = el("pp-entry-history-from");
		var toInput = el("pp-entry-history-to");
		var bookingInput = el("pp-entry-history-booking-status");
		var paymentInput = el("pp-entry-history-payment-status");
		var fromDate = fromInput
			? fromInput.value || ""
			: (state.workflowHistoryDate.data_entry || {}).from || "";
		var toDate = toInput
			? toInput.value || ""
			: (state.workflowHistoryDate.data_entry || {}).to || "";
		var status = getWorkflowStatusFilter("data_entry");
		var bookingStatus = bookingInput ? bookingInput.value || "" : status.booking;
		var paymentStatus = paymentInput ? paymentInput.value || "" : status.payment;
		return filterDocsByStatus(
			filterRowsByDateRange(docs || [], fromDate, toDate),
			bookingStatus,
			paymentStatus
		);
	}

	function getRecentDocEmployeeSummary(docName) {
		var map = {};
		getRecentDocDetails(docName).forEach(function (r) {
			var emp =
				String(r.employee || "").trim() || String(r.employee_id || "").trim() || "(Blank)";
			if (!map[emp]) {
				map[emp] = {
					employee: emp,
					po_number: r.po_number || "",
					qty: 0,
					amount: 0,
					booked: 0,
					paid: 0,
					unpaid: 0,
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
		return Object.keys(map)
			.sort()
			.map(function (k) {
				var item = map[k];
				item.rate = avgRate(item.qty, item.amount);
				item.booking_status =
					item.booked > 0 ? (item.unpaid > 0 ? "Partly Booked" : "Booked") : "UnBooked";
				item.payment_status =
					item.paid > 0 ? (item.unpaid > 0 ? "Partly Paid" : "Paid") : "Unpaid";
				return item;
			});
	}

	function showDataEntryEmployeeDetails(docName, employee) {
		var targetEmp = String(employee || "").trim();
		var rows = getRecentDocDetails(docName).filter(function (r) {
			return String(r.employee || "").trim() === targetEmp;
		});
		if (!rows.length) {
			setSummaryModal(
				"Data Entry Detail",
				targetEmp,
				"<div style='color:#b91c1c;'>No detail rows found.</div>"
			);
			return;
		}
		var qty = 0;
		var amount = 0;
		var html =
			"<table class='pp-table'><thead><tr><th>Employee</th><th>PO Number</th><th>Delivery Note</th><th>Sales Order</th><th>Product</th><th>Process Type</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>JV Status</th><th>Pay Status</th></tr></thead><tbody>";
		rows.forEach(function (r) {
			qty += num(r.qty);
			amount += num(r.amount);
			html +=
				"<tr>" +
				"<td>" +
				esc(r.employee || "") +
				"</td>" +
				"<td>" +
				esc(r.po_number || "") +
				"</td>" +
				"<td>" +
				esc(r.delivery_note || "") +
				"</td>" +
				"<td>" +
				esc(r.sales_order || "") +
				"</td>" +
				"<td>" +
				esc(r.product || "") +
				"</td>" +
				"<td>" +
				esc(r.process_type || "") +
				"</td>" +
				"<td>" +
				esc(r.process_size || "No Size") +
				"</td>" +
				"<td class='num'>" +
				esc(fmt(r.qty)) +
				"</td>" +
				"<td class='num'>" +
				esc(fmt(lineRate(r.rate, r.qty, r.amount))) +
				"</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(r.amount)) +
				"</td>" +
				"<td>" +
				statusBadgeHtml(r.booking_status || "") +
				"</td>" +
				"<td>" +
				statusBadgeHtml(r.payment_status || "") +
				"</td>" +
				"</tr>";
		});
		html +=
			"<tr class='pp-year-total'><td>Total</td><td></td><td></td><td></td><td></td><td></td><td></td><td class='num'>" +
			esc(fmt(qty)) +
			"</td><td class='num'>" +
			esc(fmt(avgRate(qty, amount))) +
			"</td><td class='num pp-amt-col'>" +
			esc(fmt(amount)) +
			"</td><td></td><td></td></tr>";
		html += "</tbody></table>";
		setSummaryModal("Data Entry Detail", targetEmp + " | " + docName, html);
	}

	function showDataEntryEnteredRows(docName) {
		var rows = getRecentDocDetails(docName);
		if (!rows.length) {
			setSummaryModal(
				"Data Entry Rows",
				docName || "",
				"<div style='color:#b91c1c;'>No rows found for this entry.</div>"
			);
			return;
		}
		var qty = 0;
		var amount = 0;
		var html =
			"<table class='pp-table'><thead><tr><th>Employee</th><th>PO Number</th><th>Delivery Note</th><th>Sales Order</th><th>Product</th><th>Process Type</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
		rows.forEach(function (r) {
			qty += num(r.qty);
			amount += num(r.amount);
			html +=
				"<tr>" +
				"<td>" +
				esc(r.employee || "") +
				"</td>" +
				"<td>" +
				esc(r.po_number || "") +
				"</td>" +
				"<td>" +
				esc(r.delivery_note || "") +
				"</td>" +
				"<td>" +
				esc(r.sales_order || "") +
				"</td>" +
				"<td>" +
				esc(r.product || "") +
				"</td>" +
				"<td>" +
				esc(r.process_type || "") +
				"</td>" +
				"<td>" +
				esc(r.process_size || "No Size") +
				"</td>" +
				"<td class='num'>" +
				esc(fmt(r.qty)) +
				"</td>" +
				"<td class='num'>" +
				esc(fmt(lineRate(r.rate, r.qty, r.amount))) +
				"</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(r.amount)) +
				"</td>" +
				"</tr>";
		});
		html +=
			"<tr class='pp-year-total'><td>Total</td><td></td><td></td><td></td><td></td><td></td><td></td><td class='num'>" +
			esc(fmt(qty)) +
			"</td><td class='num'>" +
			esc(fmt(avgRate(qty, amount))) +
			"</td><td class='num pp-amt-col'>" +
			esc(fmt(amount)) +
			"</td></tr>";
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
			end: end,
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
			end: end,
		};
	}

	function historyPagerHtml(meta) {
		if (!meta || meta.total <= 0 || meta.totalPages <= 1) return "";
		var prevDisabled = meta.page <= 1 ? " disabled" : "";
		var nextDisabled = meta.page >= meta.totalPages ? " disabled" : "";
		return (
			"<div class='pp-pagination' style='justify-content:flex-end;margin-top:6px;'>" +
			"<span>Rows " +
			esc(meta.start) +
			"-" +
			esc(meta.end) +
			" of " +
			esc(meta.total) +
			"</span>" +
			"<button type='button' class='btn btn-default btn-xs pp-history-prev' data-key='" +
			esc(meta.key) +
			"'" +
			prevDisabled +
			">Previous</button>" +
			"<span>Page " +
			esc(meta.page) +
			" / " +
			esc(meta.totalPages) +
			"</span>" +
			"<button type='button' class='btn btn-default btn-xs pp-history-next' data-key='" +
			esc(meta.key) +
			"'" +
			nextDisabled +
			">Next</button>" +
			"</div>"
		);
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
		wrap.innerHTML =
			"<span>Rows " +
			esc(meta.start) +
			"-" +
			esc(meta.end) +
			" of " +
			esc(meta.total) +
			"</span>" +
			"<button type='button' class='btn btn-default btn-xs' id='pp-page-prev'" +
			prevDisabled +
			">Previous</button>" +
			"<span>Page " +
			esc(meta.page) +
			" / " +
			esc(meta.totalPages) +
			"</span>" +
			"<button type='button' class='btn btn-default btn-xs' id='pp-page-next'" +
			nextDisabled +
			">Next</button>";
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

	var reporting =
		(window.PerPieceReporting &&
			window.PerPieceReporting.create({
				state: state,
				el: el,
				num: num,
				fmt: fmt,
				esc: esc,
				avgRate: avgRate,
				isAmountField: isAmountField,
				employeeLabel: employeeLabel,
				summaryHeaderHtml: summaryHeaderHtml,
				setSummaryModal: setSummaryModal,
				compareByProcessSequence: compareByProcessSequence,
				getAdjustedEmployeeRows: getAdjustedEmployeeRows,
				showDataEntryEmployeeDetails: showDataEntryEmployeeDetails,
				showSalarySlipPrint: showSalarySlipPrint,
				showSalaryEntryWisePrints: showSalaryEntryWisePrints,
				currentCompanyLabel: currentCompanyLabel,
				currentDateRangeLabel: currentDateRangeLabel,
				getCurrentTabLabel: getCurrentTabLabel,
				setSummaryHeading: setSummaryHeading,
			})) ||
		{};

	var showPerPieceSummary = reporting.showPerPieceSummary || function () {};
	var showPOSummary = reporting.showPOSummary || function () {};
	var showSalaryEmployeeDetail = reporting.showSalaryEmployeeDetail || function () {};
	var hidePerPieceSummary = reporting.hidePerPieceSummary || function () {};
	var printSummaryModal = reporting.printSummaryModal || function () {};
	var printCurrentTabReport = reporting.printCurrentTabReport || function () {};

	function setCreatedListHtml(html) {
		var wrap = el("pp-created-list-wrap");
		if (!wrap) return;
		wrap.innerHTML = html || "";
		function getSelectedSalaryHistoryEntries() {
			return Object.keys(state.entryMeta.selected_salary_history || {})
				.filter(function (k) {
					return !!state.entryMeta.selected_salary_history[k];
				})
				.sort(compareEntryNoDesc);
		}
		function goToPaymentForEntries(entries) {
			var selected = (entries || []).filter(Boolean);
			if (!selected.length) return;
			state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
			if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
			if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo;
			if (el("pp-pay-entry-filter")) el("pp-pay-entry-filter").value = state.forcedEntryNo;
			if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = selected.join(", ");
			if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = "";
			setWorkflowHistoryRange("payment_manage", "", "");
			setWorkflowStatusFilter("payment_manage", "", "");
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
			var activePayBtn = document.querySelector(".pp-tab[data-tab='payment_manage']");
			if (activePayBtn) activePayBtn.classList.add("active");
			state.paymentExcludedEmployees = {};
			state.paymentAdjustments = {};
			state.paymentEntryBasis = null;
			setPageForCurrentTab(1);
			loadReport();
		}
		wrap.querySelectorAll(".pp-view-jv").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var jvRaw = String(btn.getAttribute("data-jv") || "").trim();
				var jv = jvRaw;
				if (jvRaw.indexOf(",") >= 0) {
					jv = String(jvRaw.split(",")[0] || "").trim();
					showResult(
						el("pp-jv-result"),
						"info",
						"Multiple JV Found",
						"Showing first JV from list: " + esc(jv)
					);
				}
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
				var entriesCsv = btn.getAttribute("data-entries") || "";
				var batchEntry = btn.getAttribute("data-batch") || "";
				if (!docName) return;
				showSalaryCreationEntrySummary(docName, false, {
					entries_csv: entriesCsv,
					batch_entry: batchEntry,
				});
			});
		});
		wrap.querySelectorAll(".pp-print-salary-create").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var docName = btn.getAttribute("data-entry") || "";
				var entriesCsv = btn.getAttribute("data-entries") || "";
				var batchEntry = btn.getAttribute("data-batch") || "";
				if (!docName) return;
				showSalaryCreationEntrySummary(docName, true, {
					entries_csv: entriesCsv,
					batch_entry: batchEntry,
				});
			});
		});
		wrap.querySelectorAll(".pp-go-pay-salary-entry").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var entriesCsv = String(btn.getAttribute("data-entries") || "").trim();
				var selected = entriesCsv
					.split(",")
					.map(function (x) {
						return String(x || "").trim();
					})
					.filter(Boolean);
				if (!selected.length) {
					var entry = String(btn.getAttribute("data-entry") || "").trim();
					if (entry) selected = [entry];
				}
				if (!selected.length) return;
				state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
				if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
				if (el("pp-pay-entry-filter"))
					el("pp-pay-entry-filter").value = state.forcedEntryNo;
				if (el("pp-pay-entry-multi")) el("pp-pay-entry-multi").value = selected.join(", ");
				setWorkflowHistoryRange("payment_manage", "", "");
				setWorkflowStatusFilter("payment_manage", "", "");
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
				var activePayBtn4 = document.querySelector(".pp-tab[data-tab='payment_manage']");
				if (activePayBtn4) activePayBtn4.classList.add("active");
				state.paymentExcludedEmployees = {};
				state.paymentAdjustments = {};
				state.paymentEntryBasis = null;
				setPageForCurrentTab(1);
				loadReport();
			});
		});
		wrap.querySelectorAll(".pp-salary-history-book").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var entriesCsv = String(btn.getAttribute("data-entries") || "").trim();
				var selected = entriesCsv
					.split(",")
					.map(function (x) {
						return String(x || "").trim();
					})
					.filter(Boolean);
				if (!selected.length) {
					var entry = String(btn.getAttribute("data-entry") || "").trim();
					if (entry) selected = [entry];
				}
				if (!selected.length) return;
				state.forcedEntryNo = selected.length === 1 ? selected[0] : "";
				if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
				if (el("pp-jv-entry-filter")) el("pp-jv-entry-filter").value = state.forcedEntryNo;
				if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = selected.join(", ");
				setWorkflowHistoryRange("salary_creation", "", "");
				switchWorkspaceMode("entry", true);
				state.currentTab = "salary_creation";
				document.querySelectorAll(".pp-tab").forEach(function (x) {
					x.classList.remove("active");
				});
				var activeSalaryBtn4 = document.querySelector(
					".pp-tab[data-tab='salary_creation']"
				);
				if (activeSalaryBtn4) activeSalaryBtn4.classList.add("active");
				state.excludedEmployees = {};
				setPageForCurrentTab(1);
				loadReport();
			});
		});
		wrap.querySelectorAll(".pp-salary-history-select").forEach(function (box) {
			box.addEventListener("change", function () {
				state.entryMeta.selected_salary_history =
					state.entryMeta.selected_salary_history || {};
				var entriesCsv = String(box.getAttribute("data-entries") || "").trim();
				var names = entriesCsv
					? entriesCsv
							.split(",")
							.map(function (x) {
								return String(x || "").trim();
							})
							.filter(Boolean)
					: [String(box.getAttribute("data-entry") || "").trim()].filter(Boolean);
				if (!names.length) return;
				names.forEach(function (name) {
					state.entryMeta.selected_salary_history[name] = !!box.checked;
				});
				var countEl = el("pp-salary-history-selected-count");
				if (countEl) {
					var count = Object.keys(state.entryMeta.selected_salary_history).filter(
						function (k) {
							return !!state.entryMeta.selected_salary_history[k];
						}
					).length;
					countEl.textContent = String(count);
				}
			});
		});
		if (el("pp-salary-history-select-page")) {
			el("pp-salary-history-select-page").addEventListener("click", function () {
				state.entryMeta.selected_salary_history =
					state.entryMeta.selected_salary_history || {};
				wrap.querySelectorAll(".pp-salary-history-select").forEach(function (box) {
					var entriesCsv = String(box.getAttribute("data-entries") || "").trim();
					var names = entriesCsv
						? entriesCsv
								.split(",")
								.map(function (x) {
									return String(x || "").trim();
								})
								.filter(Boolean)
						: [String(box.getAttribute("data-entry") || "").trim()].filter(Boolean);
					if (!names.length) return;
					box.checked = true;
					names.forEach(function (name) {
						state.entryMeta.selected_salary_history[name] = true;
					});
				});
				var countEl = el("pp-salary-history-selected-count");
				if (countEl) {
					var count = Object.keys(state.entryMeta.selected_salary_history).filter(
						function (k) {
							return !!state.entryMeta.selected_salary_history[k];
						}
					).length;
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
				var selected = getSelectedSalaryHistoryEntries();
				if (!selected.length) {
					var jvResult = el("pp-jv-result");
					if (jvResult)
						showResult(
							jvResult,
							"error",
							"No Entry Selected",
							"Select one or more salary entries first."
						);
					return;
				}
				goToPaymentForEntries(selected);
			});
		}
		if (el("pp-salary-history-create-batch")) {
			el("pp-salary-history-create-batch").addEventListener("click", function () {
				var selected = getSelectedSalaryHistoryEntries();
				if (!selected.length) {
					showResult(
						el("pp-jv-result"),
						"error",
						"No Entry Selected",
						"Select one or more salary entries first."
					);
					return;
				}
				var batchInput = el("pp-salary-history-batch-name");
				var batchName = batchInput ? String(batchInput.value || "").trim() : "";
				showResult(
					el("pp-jv-result"),
					"info",
					"Creating Batch",
					"Creating salary batch for selected entries..."
				);
				callApi("per_piece_payroll.api.create_salary_batch", {
					entry_nos: selected.join(","),
					batch_name: batchName || "",
					company: (el("pp-company") && el("pp-company").value) || "",
					remarks: "Created from Salary Creation selected entries",
				})
					.then(function (resp) {
						var batch = String((resp && resp.batch) || "").trim();
						if (batchInput && batch) batchInput.value = batch;
						showResult(
							el("pp-jv-result"),
							"success",
							"Batch Created",
							"Batch: <strong>" +
								esc(batch) +
								"</strong> | Entries: " +
								esc(selected.length)
						);
					})
					.catch(function (e) {
						showResult(
							el("pp-jv-result"),
							"error",
							"Create Batch Failed",
							prettyError(errText(e))
						);
					});
			});
		}
		if (el("pp-salary-history-open-batch")) {
			el("pp-salary-history-open-batch").addEventListener("click", function () {
				var batchInput = el("pp-salary-history-batch-name");
				var batchName = batchInput ? String(batchInput.value || "").trim() : "";
				if (!batchName) {
					showResult(
						el("pp-jv-result"),
						"error",
						"Batch Required",
						"Enter batch name first."
					);
					return;
				}
				window.open(
					"/app/per-piece-salary-batch/" + encodeURIComponent(batchName),
					"_blank"
				);
			});
		}
		if (el("pp-salary-history-pay-batch")) {
			el("pp-salary-history-pay-batch").addEventListener("click", function () {
				var batchInput = el("pp-salary-history-batch-name");
				var batchName = batchInput ? String(batchInput.value || "").trim() : "";
				if (!batchName) {
					showResult(
						el("pp-jv-result"),
						"error",
						"Batch Required",
						"Enter batch name first."
					);
					return;
				}
				callApi("per_piece_payroll.api.get_salary_batch_entries", {
					batch_name: batchName,
				})
					.then(function (resp) {
						if (!resp || resp.ok === false) {
							throw new Error(
								(resp && resp.message) || "Unable to load batch entries."
							);
						}
						var entries = (resp.entries || [])
							.map(function (r) {
								return String((r && r.salary_entry) || "").trim();
							})
							.filter(Boolean);
						if (!entries.length) {
							throw new Error("No salary entries found in this batch.");
						}
						goToPaymentForEntries(entries);
					})
					.catch(function (e) {
						showResult(
							el("pp-jv-result"),
							"error",
							"Pay Batch Failed",
							prettyError(errText(e))
						);
					});
			});
		}
		if (el("pp-jv-history-from")) {
			el("pp-jv-history-from").addEventListener("change", function () {
				setWorkflowHistoryRange(
					"salary_creation",
					el("pp-jv-history-from").value || "",
					(el("pp-jv-history-to") && el("pp-jv-history-to").value) || ""
				);
				state.historyPageByTab.salary_creation_history = 1;
				renderCreatedEntriesPanel("salary_creation");
			});
		}
		if (el("pp-jv-history-to")) {
			el("pp-jv-history-to").addEventListener("change", function () {
				setWorkflowHistoryRange(
					"salary_creation",
					(el("pp-jv-history-from") && el("pp-jv-history-from").value) || "",
					el("pp-jv-history-to").value || ""
				);
				state.historyPageByTab.salary_creation_history = 1;
				renderCreatedEntriesPanel("salary_creation");
			});
		}
		if (el("pp-jv-history-booking-status")) {
			el("pp-jv-history-booking-status").addEventListener("change", function () {
				setWorkflowStatusFilter(
					"salary_creation",
					el("pp-jv-history-booking-status").value || "",
					(el("pp-jv-history-payment-status") &&
						el("pp-jv-history-payment-status").value) ||
						""
				);
				state.historyPageByTab.salary_creation_history = 1;
				renderCreatedEntriesPanel("salary_creation");
			});
		}
		if (el("pp-jv-history-payment-status")) {
			el("pp-jv-history-payment-status").addEventListener("change", function () {
				setWorkflowStatusFilter(
					"salary_creation",
					(el("pp-jv-history-booking-status") &&
						el("pp-jv-history-booking-status").value) ||
						"",
					el("pp-jv-history-payment-status").value || ""
				);
				state.historyPageByTab.salary_creation_history = 1;
				renderCreatedEntriesPanel("salary_creation");
			});
		}
		if (el("pp-pay-history-from")) {
			el("pp-pay-history-from").addEventListener("change", function () {
				setWorkflowHistoryRange(
					"payment_manage",
					el("pp-pay-history-from").value || "",
					(el("pp-pay-history-to") && el("pp-pay-history-to").value) || ""
				);
				state.historyPageByTab.payment_manage_history = 1;
				renderCreatedEntriesPanel("payment_manage");
			});
		}
		if (el("pp-pay-history-to")) {
			el("pp-pay-history-to").addEventListener("change", function () {
				setWorkflowHistoryRange(
					"payment_manage",
					(el("pp-pay-history-from") && el("pp-pay-history-from").value) || "",
					el("pp-pay-history-to").value || ""
				);
				state.historyPageByTab.payment_manage_history = 1;
				renderCreatedEntriesPanel("payment_manage");
			});
		}
		if (el("pp-pay-history-booking-status")) {
			el("pp-pay-history-booking-status").addEventListener("change", function () {
				setWorkflowStatusFilter(
					"payment_manage",
					el("pp-pay-history-booking-status").value || "",
					(el("pp-pay-history-payment-status") &&
						el("pp-pay-history-payment-status").value) ||
						""
				);
				state.historyPageByTab.payment_manage_history = 1;
				renderCreatedEntriesPanel("payment_manage");
			});
		}
		if (el("pp-pay-history-payment-status")) {
			el("pp-pay-history-payment-status").addEventListener("change", function () {
				setWorkflowStatusFilter(
					"payment_manage",
					(el("pp-pay-history-booking-status") &&
						el("pp-pay-history-booking-status").value) ||
						"",
					el("pp-pay-history-payment-status").value || ""
				);
				state.historyPageByTab.payment_manage_history = 1;
				renderCreatedEntriesPanel("payment_manage");
			});
		}
		wrap.querySelectorAll(".pp-view-payment-create").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var jvName = btn.getAttribute("data-jv") || "";
				var entryScope = btn.getAttribute("data-entry-scope") || "";
				if (!jvName) return;
				showPaymentEntrySummary(jvName, false, entryScope);
			});
		});
		wrap.querySelectorAll(".pp-print-payment-create").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var jvName = btn.getAttribute("data-jv") || "";
				var entryScope = btn.getAttribute("data-entry-scope") || "";
				if (!jvName) return;
				showPaymentEntrySummary(jvName, true, entryScope);
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
				renderCreatedEntriesPanel(state.currentTab);
			});
		});
		wrap.querySelectorAll(".pp-history-next").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var key = String(btn.getAttribute("data-key") || "");
				if (!key) return;
				state.historyPageByTab[key] =
					(parseInt(state.historyPageByTab[key] || 1, 10) || 1) + 1;
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
		return Object.keys(map)
			.sort()
			.map(function (k) {
				return map[k];
			});
	}

	function getSalaryFinancialCache() {
		if (!state.entryMeta) state.entryMeta = {};
		if (!state.entryMeta.salaryFinancialByEntry) state.entryMeta.salaryFinancialByEntry = {};
		if (!state.entryMeta.salaryFinancialPending) state.entryMeta.salaryFinancialPending = {};
		return state.entryMeta.salaryFinancialByEntry;
	}

	function getSalaryBatchCache() {
		if (!state.entryMeta) state.entryMeta = {};
		if (!state.entryMeta.salaryBatchByEntry) state.entryMeta.salaryBatchByEntry = {};
		if (!state.entryMeta.salaryBatchPending) state.entryMeta.salaryBatchPending = {};
		return state.entryMeta.salaryBatchByEntry;
	}

	function ensureSalaryBatchLinks(entryNames) {
		var names = (entryNames || [])
			.map(function (n) {
				return String(n || "").trim();
			})
			.filter(function (n) {
				return !!n;
			});
		if (!names.length) return Promise.resolve(false);
		var cache = getSalaryBatchCache();
		var missing = names.filter(function (entry) {
			return typeof cache[entry] === "undefined";
		});
		if (!missing.length) return Promise.resolve(false);
		return callApi("per_piece_payroll.api.get_salary_batch_links", {
			entry_names: missing,
		})
			.then(function (rows) {
				var data = (rows && rows.data) || {};
				Object.keys(data || {}).forEach(function (key0) {
					var key = String(key0 || "").trim();
					if (!key) return;
					var r = data[key] || {};
					cache[key] = {
						salary_batch: String((r && r.salary_batch) || "").trim(),
						delivery_note: String((r && r.delivery_note) || "").trim(),
						po_number: String((r && r.po_number) || "").trim(),
					};
				});
				missing.forEach(function (m) {
					if (typeof cache[m] === "undefined") cache[m] = {};
				});
				return true;
			})
			.catch(function () {
				return false;
			});
	}

	function computeSalaryEntryFinancial(entryName) {
		var entry = String(entryName || "").trim();
		if (!entry) return Promise.resolve(null);
		var rows = getSalaryCreationEntryRows(
			entry,
			state.entryMeta.recentRows || state.rows || []
		);
		if (!rows.length) return Promise.resolve(null);
		return getSalaryEntryAdjustmentMap(rows).then(function (adjustmentMap) {
			var fin = {
				entry: entry,
				salary_amount: 0,
				allowance_amount: 0,
				advance_deduction_amount: 0,
				other_deduction_amount: 0,
				net_salary: 0,
				by_employee: {},
			};
			rows.forEach(function (r) {
				var emp = String(r.employee || "").trim();
				var adj = adjustmentMap[emp] || {};
				var salaryAmount = num(r.amount);
				var advanceDeduction = num(adj.advance_deduction);
				var otherDeduction = num(adj.other_deduction);
				var netAmount = num(adj.net_amount);
				if (netAmount <= 0)
					netAmount = Math.max(salaryAmount - advanceDeduction - otherDeduction, 0);
				var allowance = Math.max(
					netAmount - salaryAmount + advanceDeduction + otherDeduction,
					0
				);
				fin.salary_amount += salaryAmount;
				fin.allowance_amount += allowance;
				fin.advance_deduction_amount += advanceDeduction;
				fin.other_deduction_amount += otherDeduction;
				fin.net_salary += netAmount;
				fin.by_employee[emp] = {
					salary_amount: salaryAmount,
					allowance_amount: allowance,
					advance_deduction_amount: advanceDeduction,
					other_deduction_amount: otherDeduction,
					net_amount: netAmount,
				};
			});
			return fin;
		});
	}

	function ensureSalaryFinancials(entryNames) {
		var names = (entryNames || [])
			.map(function (n) {
				return String(n || "").trim();
			})
			.filter(function (n) {
				return !!n;
			});
		if (!names.length) return Promise.resolve(false);
		var cache = getSalaryFinancialCache();
		var missing = names.filter(function (entry) {
			return !cache[entry];
		});
		if (!missing.length) return Promise.resolve(false);
		return callApi("per_piece_payroll.api.get_salary_entry_financials", {
			entry_names: missing,
		})
			.then(function (resp) {
				var data = (resp && resp.data) || {};
				Object.keys(data || {}).forEach(function (entry) {
					cache[entry] = data[entry];
				});
				return true;
			})
			.catch(function (_e) {
				return Promise.all(
					missing.map(function (entry) {
						return computeSalaryEntryFinancial(entry)
							.then(function (fin) {
								if (fin) cache[entry] = fin;
							})
							.catch(function (_e2) {});
					})
				).then(function () {
					return true;
				});
			});
	}

	function primeSalaryFinancialsForTab(tab) {
		var current = String(tab || "");
		var entryMap = {};
		if (current === "salary_creation") {
			uniqueCreatedSalaryDocs().forEach(function (d) {
				var name = String((d && d.name) || "").trim();
				if (name) entryMap[name] = 1;
			});
		} else if (current === "payment_manage") {
			(getBookedRows() || []).forEach(function (r) {
				var entry = String((r && r.per_piece_salary) || "").trim();
				var jv = String((r && r.jv_entry_no) || "").trim();
				if (entry && jv) entryMap[entry] = 1;
			});
		}
		var names = Object.keys(entryMap);
		if (!names.length) return;
		Promise.all([ensureSalaryFinancials(names), ensureSalaryBatchLinks(names)]).then(function (
			out
		) {
			var updated = !!((out && out[0]) || (out && out[1]));
			if (!updated) return;
			if (state.currentTab !== current) return;
			normalizePaymentAdjustments();
			renderCurrentTab();
		});
	}

	function uniqueCreatedSalaryDocs() {
		var map = {};
		var salaryFinancial = getSalaryFinancialCache();
		var salaryBatchCache = getSalaryBatchCache();
		var sourceRows = (state.entryMeta && state.entryMeta.recentRows) || state.rows || [];
		(sourceRows || []).forEach(function (r) {
			var docName = String((r && r.per_piece_salary) || "").trim();
			if (!docName) return;
			if (!map[docName]) {
				var cachedMeta = salaryBatchCache[docName] || {};
				map[docName] = {
					name: docName,
					po_number: String((r && r.po_number) || "").trim(),
					salary_batch: String((cachedMeta && cachedMeta.salary_batch) || "").trim(),
					jv_entry_no: "",
					payment_jv_no: "",
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
					_partly_paid_count: 0,
					_salary_jvs: {},
					_payment_jvs: {},
				};
			}
			var rowSalaryJv = String((r && r.jv_entry_no) || "").trim();
			if (rowSalaryJv) {
				rowSalaryJv
					.split(",")
					.map(function (x) {
						return String(x || "").trim();
					})
					.filter(Boolean)
					.forEach(function (jv) {
						map[docName]._salary_jvs[jv] = 1;
					});
			}
			if (!map[docName].salary_batch) {
				var rowBatch = String((r && r.salary_batch) || "").trim();
				var cacheBatch = String(
					(salaryBatchCache[docName] || {}).salary_batch || ""
				).trim();
				map[docName].salary_batch = rowBatch || cacheBatch || "";
			}
			var rf = String((r && r.from_date) || "").trim();
			var rt = String((r && r.to_date) || "").trim();
			if (rf && (!map[docName].from_date || rf < map[docName].from_date))
				map[docName].from_date = rf;
			if (rt && (!map[docName].to_date || rt > map[docName].to_date))
				map[docName].to_date = rt;
			map[docName].amount += num(r.amount);
			map[docName].booked_amount += getNetBookedAmountForRow(r);
			map[docName].rows += 1;
			var payJv = String((r && r.payment_jv_no) || "").trim();
			if (payJv) {
				payJv
					.split(",")
					.map(function (x) {
						return String(x || "").trim();
					})
					.filter(Boolean)
					.forEach(function (jv) {
						map[docName]._payment_jvs[jv] = 1;
					});
			}
			if (String(r.booking_status || "") === "Booked") map[docName]._booked_count += 1;
			var payStatus = String(r.payment_status || "");
			if (payStatus === "Paid") map[docName]._paid_count += 1;
			else if (payStatus === "Partly Paid") map[docName]._partly_paid_count += 1;
		});
		Object.keys(map).forEach(function (k) {
			var it = map[k];
			var fin = salaryFinancial[k] || null;
			if (fin) {
				it.allowance_amount = num(fin.allowance_amount);
				it.advance_deduction_amount = num(fin.advance_deduction_amount);
				it.other_deduction_amount = num(fin.other_deduction_amount);
				it.net_salary = num(fin.net_salary);
				it.booked_amount = num(fin.net_salary);
			} else {
				var salaryAmount = num(it.amount);
				var netAmount = num(it.booked_amount) > 0 ? num(it.booked_amount) : salaryAmount;
				it.allowance_amount = Math.max(netAmount - salaryAmount, 0);
				it.advance_deduction_amount = Math.max(salaryAmount - netAmount, 0);
				it.other_deduction_amount = 0;
				it.net_salary = netAmount;
			}
			it.booking_status =
				it._booked_count >= it.rows
					? "Booked"
					: it._booked_count > 0
					? "Partly Booked"
					: "UnBooked";
			if (it._paid_count >= it.rows) it.payment_status = "Paid";
			else if (it._paid_count > 0 || it._partly_paid_count > 0)
				it.payment_status = "Partly Paid";
			else it.payment_status = "Unpaid";
			it.jv_entry_no = Object.keys(it._salary_jvs || {}).join(", ");
			it.payment_jv_no = Object.keys(it._payment_jvs || {}).join(", ");
		});
		return Object.keys(map)
			.sort()
			.reverse()
			.map(function (k) {
				return map[k];
			});
	}

	function uniqueCreatedSalaryBatchDocs() {
		var docs = uniqueCreatedSalaryDocs();
		var grouped = {};
		docs.forEach(function (d) {
			var batch = String((d && d.salary_batch) || "").trim();
			var key = batch || "__NO_BATCH__";
			if (!grouped[key]) {
				grouped[key] = {
					batch_entry: batch,
					salary_entries: [],
					po_numbers: {},
					delivery_notes: {},
					jv_entries: {},
					payment_jvs: {},
					amount: 0,
					allowance_amount: 0,
					advance_deduction_amount: 0,
					other_deduction_amount: 0,
					net_salary: 0,
					booking_status: "UnBooked",
					payment_status: "Unpaid",
				};
			}
			var g = grouped[key];
			g.salary_entries.push(String(d.name || "").trim());
			if (d.po_number) g.po_numbers[String(d.po_number)] = 1;
			if (d.delivery_note) g.delivery_notes[String(d.delivery_note)] = 1;
			if (d.jv_entry_no) g.jv_entries[String(d.jv_entry_no)] = 1;
			if (d.payment_jv_no) g.payment_jvs[String(d.payment_jv_no)] = 1;
			g.amount += num(d.amount);
			g.allowance_amount += num(d.allowance_amount);
			g.advance_deduction_amount += num(d.advance_deduction_amount);
			g.other_deduction_amount += num(d.other_deduction_amount);
			g.net_salary += num(d.net_salary);
			if (String(d.booking_status || "") === "Booked") g.booking_status = "Booked";
			if (String(d.payment_status || "") === "Partly Paid") g.payment_status = "Partly Paid";
			if (String(d.payment_status || "") === "Paid" && g.payment_status !== "Partly Paid")
				g.payment_status = "Paid";
		});
		return Object.keys(grouped)
			.map(function (k) {
				var g = grouped[k];
				g.salary_entries = (g.salary_entries || [])
					.filter(Boolean)
					.sort(compareEntryNoDesc);
				g.salary_entry =
					g.salary_entries.length === 1
						? g.salary_entries[0]
						: g.salary_entries.length + " entries";
				g.po_number = Object.keys(g.po_numbers || {}).join(", ");
				g.delivery_note = Object.keys(g.delivery_notes || {}).join(", ");
				g.jv_entry_no = Object.keys(g.jv_entries || {}).join(", ");
				g.payment_jv_no = Object.keys(g.payment_jvs || {}).join(", ");
				g.name = g.salary_entries[0] || "";
				g._entries_csv = (g.salary_entries || []).join(",");
				return g;
			})
			.sort(function (a, b) {
				return compareEntryNoDesc((a && a.name) || "", (b && b.name) || "");
			});
	}

	function renderJvLinks(jvCsv) {
		var list = String(jvCsv || "")
			.split(",")
			.map(function (x) {
				return String(x || "").trim();
			})
			.filter(Boolean);
		if (!list.length) return "";
		return list
			.map(function (jv) {
				return (
					"<a target='_blank' href='/app/journal-entry/" +
					encodeURIComponent(jv) +
					"'>" +
					esc(jv) +
					"</a>"
				);
			})
			.join("<br>");
	}

	function setSalaryHistoryCell(entryName, col, value) {
		document
			.querySelectorAll(
				".pp-salary-history-cell[data-entry='" +
					String(entryName || "").replace(/'/g, "\\'") +
					"'][data-col='" +
					String(col || "").replace(/'/g, "\\'") +
					"']"
			)
			.forEach(function (cell) {
				cell.textContent = fmt(value);
			});
	}

	function setSalaryHistoryTotalsRow(values) {
		var mapping = {
			salary: "pp-salary-history-total-salary",
			allowance: "pp-salary-history-total-allowance",
			advance: "pp-salary-history-total-advance",
			other: "pp-salary-history-total-other",
			net: "pp-salary-history-total-net",
		};
		Object.keys(mapping).forEach(function (k) {
			var node = el(mapping[k]);
			if (node) node.textContent = fmt(num(values && values[k]));
		});
	}

	function hydrateSalaryHistoryFinancials(rows) {
		var list = rows || [];
		if (!list.length) return;
		if (String(state.currentTab || "") !== "salary_creation") return;
		var totals = { salary: 0, allowance: 0, advance: 0, other: 0, net: 0 };
		list.forEach(function (r) {
			var entry = String((r && r.name) || "").trim();
			if (!entry) return;
			var vals = {
				salary: num(r.amount),
				allowance: num(r.allowance_amount),
				advance: num(r.advance_deduction_amount),
				other: num(r.other_deduction_amount),
				net: num(r.net_salary),
			};
			setSalaryHistoryCell(entry, "salary", vals.salary);
			setSalaryHistoryCell(entry, "allowance", vals.allowance);
			setSalaryHistoryCell(entry, "advance", vals.advance);
			setSalaryHistoryCell(entry, "other", vals.other);
			setSalaryHistoryCell(entry, "net", vals.net);
			totals.salary += vals.salary;
			totals.allowance += vals.allowance;
			totals.advance += vals.advance;
			totals.other += vals.other;
			totals.net += vals.net;
		});
		if (String(state.currentTab || "") !== "salary_creation") return;
		setSalaryHistoryTotalsRow(totals);
		normalizePaymentAdjustments();
	}

	function parsePaymentRefsJs(text) {
		var refs = [];
		String(text || "")
			.split(";;")
			.forEach(function (part) {
				var bits = String(part || "").split("::");
				if (bits.length < 2) return;
				var jv = String(bits[0] || "").trim();
				var amount = num(bits[1]);
				if (jv && amount > 0) refs.push({ jv: jv, amount: amount });
			});
		return refs;
	}

	function getDoctypeTotalsForEntry(entryName) {
		var target = String(entryName || "").trim();
		var totals = {
			amount: 0,
			booked_amount: 0,
			paid_amount: 0,
			unpaid_amount: 0,
			rows: 0,
		};
		if (!target) return totals;
		var seen = {};
		(state.rows || []).forEach(function (r) {
			if (String(r.per_piece_salary || "").trim() !== target) return;
			var rowKey =
				String(r.row_id || "").trim() ||
				[
					String(r.per_piece_salary || "").trim(),
					String(r.employee || "").trim(),
					String(r.product || "").trim(),
					String(r.process_type || "").trim(),
					String(r.process_size || "").trim(),
					String(r.sales_order || "").trim(),
					String(r.delivery_note || "").trim(),
					String(r.qty || "").trim(),
					String(r.rate || "").trim(),
				].join("::");
			if (seen[rowKey]) return;
			seen[rowKey] = 1;
			var booked = Math.max(num(getNetBookedAmountForRow(r)), 0);
			var paid = Math.max(num(r.paid_amount), 0);
			if (paid > booked) paid = booked;
			var unpaid = Math.max(booked - paid, 0);
			totals.amount += num(r.amount);
			totals.booked_amount += booked;
			totals.paid_amount += paid;
			totals.unpaid_amount += unpaid;
			totals.rows += 1;
		});
		return totals;
	}

	function getDoctypeTotalsForEntries(entryNames) {
		var totals = {
			amount: 0,
			booked_amount: 0,
			paid_amount: 0,
			unpaid_amount: 0,
			rows: 0,
		};
		(entryNames || []).forEach(function (name) {
			var t = getDoctypeTotalsForEntry(name);
			totals.amount += num(t.amount);
			totals.booked_amount += num(t.booked_amount);
			totals.paid_amount += num(t.paid_amount);
			totals.unpaid_amount += num(t.unpaid_amount);
			totals.rows += num(t.rows);
		});
		return totals;
	}

	function getDoctypeEmployeeTotalsForEntry(entryName) {
		var target = String(entryName || "").trim();
		var out = {};
		if (!target) return out;
		var seen = {};
		(state.rows || []).forEach(function (r) {
			if (String(r.per_piece_salary || "").trim() !== target) return;
			var rowId = String(r.row_id || "").trim();
			var key =
				rowId ||
				[
					target,
					String(r.employee || ""),
					String(r.idx || ""),
					String(r.qty || ""),
					String(r.rate || ""),
					String(r.amount || ""),
				].join("::");
			if (seen[key]) return;
			seen[key] = 1;
			var emp = String(r.employee || "").trim();
			if (!emp) return;
			if (!out[emp]) {
				out[emp] = {
					name1: r.name1 || emp,
					amount: 0,
					booked_amount: 0,
					paid_amount: 0,
					unpaid_amount: 0,
				};
			}
			var booked = Math.max(num(getNetBookedAmountForRow(r)), 0);
			var paid = Math.max(num(r.paid_amount), 0);
			if (paid > booked) paid = booked;
			var unpaid = Math.max(booked - paid, 0);
			out[emp].amount += num(r.amount);
			out[emp].booked_amount += booked;
			out[emp].paid_amount += paid;
			out[emp].unpaid_amount += unpaid;
		});
		return out;
	}

	function getPaymentJVEmployeeAmounts(jvName) {
		var target = String(jvName || "").trim();
		if (!target) return Promise.resolve({ by_employee: {}, by_employee_detail: {}, total: 0 });
		if (!state.entryMeta) state.entryMeta = {};
		if (!state.entryMeta.paymentJVEmployeeAmounts)
			state.entryMeta.paymentJVEmployeeAmounts = {};
		if (state.entryMeta.paymentJVEmployeeAmounts[target]) {
			return Promise.resolve(state.entryMeta.paymentJVEmployeeAmounts[target]);
		}
		return getJournalEntryDoc(target)
			.then(function (doc) {
				var byEmployee = {};
				var byEmployeeDetail = {};
				var total = 0;
				((doc && doc.accounts) || []).forEach(function (acc) {
					var debit = num(acc.debit_in_account_currency || acc.debit || 0);
					if (debit <= 0) return;
					total += debit;
					var emp = String(acc.party || "").trim();
					if (!emp) {
						var remarkText = String(acc.user_remark || "").trim();
						var m = remarkText.match(/\(([^)]+)\)\s*$/);
						if (m && m[1]) emp = String(m[1] || "").trim();
					}
					if (!emp) return;
					byEmployee[emp] = num(byEmployee[emp]) + debit;
					var remark = String(acc.user_remark || "").trim();
					var b = null,
						pd = null,
						u = null,
						pay = null;
					var mb = remark.match(/\|\s*B:([-0-9.]+)/i);
					var mpd = remark.match(/\|\s*PD:([-0-9.]+)/i);
					var mu = remark.match(/\|\s*U:([-0-9.]+)/i);
					var mpay = remark.match(/\|\s*PAY:([-0-9.]+)/i);
					if (mb) b = num(mb[1]);
					if (mpd) pd = num(mpd[1]);
					if (mu) u = num(mu[1]);
					if (mpay) pay = num(mpay[1]);
					if (!byEmployeeDetail[emp]) {
						byEmployeeDetail[emp] = {
							booked_amount: 0,
							paid_amount: 0,
							unpaid_amount: 0,
							payment_amount: 0,
						};
					}
					if (b != null) byEmployeeDetail[emp].booked_amount += b;
					if (pd != null) byEmployeeDetail[emp].paid_amount += pd;
					if (u != null) byEmployeeDetail[emp].unpaid_amount += u;
					byEmployeeDetail[emp].payment_amount += pay != null ? pay : debit;
				});
				var out = {
					by_employee: byEmployee,
					by_employee_detail: byEmployeeDetail,
					total: total,
				};
				state.entryMeta.paymentJVEmployeeAmounts[target] = out;
				return out;
			})
			.catch(function () {
				return { by_employee: {}, by_employee_detail: {}, total: 0 };
			});
	}

	function uniqueCreatedPaymentDocs() {
		return [];
	}

	function hydratePaymentHistoryAmounts(_rows) {}

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
					jv_entry_no: String(r.jv_entry_no || "").trim(),
				};
			}
			map[emp].qty += num(r.qty);
			map[emp].amount += num(r.amount);
			if (!map[emp].jv_entry_no && r.jv_entry_no)
				map[emp].jv_entry_no = String(r.jv_entry_no || "").trim();
		});
		return Object.keys(map)
			.sort()
			.map(function (emp) {
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
		return Promise.all(
			jvNames.map(function (jvName) {
				return getJournalEntryDoc(jvName);
			})
		).then(function (docs) {
			var byEmp = {};
			function ensureEmp(emp) {
				if (!byEmp[emp])
					byEmp[emp] = { advance_deduction: 0, other_deduction: 0, net_amount: 0 };
				return byEmp[emp];
			}
			docs.forEach(function (doc) {
				((doc && doc.accounts) || []).forEach(function (acc) {
					var credit = num(acc.credit_in_account_currency || acc.credit);
					if (credit <= 0) return;
					var party = String(acc.party || "").trim();
					var remark = String(acc.user_remark || "").trim();
					var advanceMatch = remark.match(/^Advance Recovery - (.+)$/);
					var deductionMatch = remark.match(/^Salary Deduction - (.+)$/);
					var netMatch = remark.match(/^Net Salary - (.+?)(\s*\||$)/);
					var emp =
						party ||
						(advanceMatch && advanceMatch[1]) ||
						(deductionMatch && deductionMatch[1]) ||
						(netMatch && netMatch[1]) ||
						"";
					emp = String(emp || "").trim();
					if (!emp) return;
					var target = ensureEmp(emp);
					if (advanceMatch || (party && remark.indexOf("Advance Recovery - ") === 0))
						target.advance_deduction += credit;
					else if (
						deductionMatch ||
						(party && remark.indexOf("Salary Deduction - ") === 0)
					)
						target.other_deduction += credit;
					else if (netMatch || (party && remark.indexOf("Net Salary - ") === 0))
						target.net_amount += credit;
				});
			});
			return byEmp;
		});
	}

	function showSalaryCreationEntrySummary(entryName, printNow, opts) {
		var targetEntry = String(entryName || "").trim();
		if (!targetEntry) return;
		var entriesCsv = String((opts && opts.entries_csv) || "").trim();
		var batchEntry = String((opts && opts.batch_entry) || "").trim();
		setSummaryModal(
			"Salary Creation Detail",
			targetEntry,
			"<div style='color:#334155;'>Loading salary creation detail...</div>"
		);
		callApi("per_piece_payroll.api.get_salary_creation_detail", {
			entry_no: targetEntry,
			entry_nos: entriesCsv,
			batch_entry: batchEntry,
		})
			.then(function (detail) {
				if (!detail || detail.ok === false) {
					throw new Error(
						(detail && detail.message) || "Failed to load salary creation detail"
					);
				}
				var rows = detail.rows || [];
				if (!rows.length) {
					setSummaryModal(
						"Salary Creation Detail",
						targetEntry,
						"<div style='color:#b91c1c;'>No salary rows available for this entry.</div>"
					);
					return;
				}
				var totalQty = 0;
				var totalRate = 0;
				var totalAmount = 0;
				var totalAdvanceBal = 0;
				var totalAdvanceDed = 0;
				var totalAllowance = 0;
				var totalOtherDed = 0;
				var totalNet = 0;
				var gross = 0;
				var html = summaryHeaderHtml("Salary Creation Detail", targetEntry);
				html +=
					"<div class='pp-summary-chips'>" +
					"<span class='pp-summary-chip'>PO Number: " +
					esc((detail && detail.po_number) || "-") +
					"</span>" +
					"<span class='pp-summary-chip'>Delivery Note: " +
					esc((detail && detail.delivery_note) || "-") +
					"</span>" +
					"<span class='pp-summary-chip'>From: " +
					esc((detail && detail.from_date) || "-") +
					"</span>" +
					"<span class='pp-summary-chip'>To: " +
					esc((detail && detail.to_date) || "-") +
					"</span>" +
					"<span class='pp-summary-chip'>Rows: " +
					esc(rows.length) +
					"</span>" +
					"</div>";
				html +=
					"<table class='pp-table'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Salary Amount</th><th>Advance Balance</th><th>Advance Deduction</th><th>Allowance</th><th>Other Deduction</th><th>Net Amount</th></tr></thead><tbody>";
				rows.forEach(function (r) {
					var advanceDeduction = num(r.advance_deduction);
					var otherDeduction = num(r.other_deduction);
					var allowance = num(r.allowance);
					var salaryAmount = num(r.salary_amount);
					var netAmount = num(r.net_amount);
					var advanceBalance = Math.max(
						num((state.advanceBalances || {})[r.employee]) + advanceDeduction,
						0
					);
					totalQty += num(r.qty);
					totalRate += num(r.rate);
					totalAmount += salaryAmount;
					totalAdvanceBal += advanceBalance;
					totalAdvanceDed += advanceDeduction;
					totalAllowance += allowance;
					totalOtherDed += otherDeduction;
					totalNet += netAmount;
					gross += salaryAmount + allowance;
					html +=
						"<tr>" +
						"<td>" +
						esc(r.name1 || r.employee || "") +
						"</td>" +
						"<td class='num'>" +
						esc(fmt(r.qty)) +
						"</td>" +
						"<td class='num'>" +
						esc(fmt(r.rate)) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(salaryAmount)) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(advanceBalance)) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(advanceDeduction)) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(allowance)) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(otherDeduction)) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(netAmount)) +
						"</td>" +
						"</tr>";
				});
				html +=
					"<tr class='pp-year-total'>" +
					"<td>Total</td>" +
					"<td class='num'>" +
					esc(fmt(totalQty)) +
					"</td>" +
					"<td class='num'>" +
					esc(fmt(totalRate)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(totalAmount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(totalAdvanceBal)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(totalAdvanceDed)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(totalAllowance)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(totalOtherDed)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(totalNet)) +
					"</td>" +
					"</tr>";
				html += "</tbody></table>";
				html +=
					"<div class='pp-summary-chips'>" +
					"<span class='pp-summary-chip'>Gross: " +
					esc(fmt(gross)) +
					"</span>" +
					"<span class='pp-summary-chip'>Advance Deduction: " +
					esc(fmt(totalAdvanceDed)) +
					"</span>" +
					"<span class='pp-summary-chip'>Other Deduction: " +
					esc(fmt(totalOtherDed)) +
					"</span>" +
					"<span class='pp-summary-chip'>Net Payable: " +
					esc(fmt(totalNet)) +
					"</span>" +
					"</div>";
				setSummaryModal("Salary Creation Detail", targetEntry, html);
				if (printNow) {
					setTimeout(function () {
						printSummaryModal();
					}, 60);
				}
			})
			.catch(function (e) {
				setSummaryModal(
					"Salary Creation Detail",
					entryName || "",
					"<div style='color:#b91c1c;'>Unable to load salary creation detail: " +
						esc(prettyError(errText(e))) +
						"</div>"
				);
			});
	}

	function showPaymentEntrySummary(paymentEntryName, printNow, _entryScopeRaw) {
		var target = String(paymentEntryName || "").trim();
		if (!target) return;
		setSummaryModal(
			"Payment Entry Detail",
			target,
			"<div style='color:#334155;'>Loading payment detail...</div>"
		);
		callApi("per_piece_payroll.api.get_per_piece_payment_entry_detail", {
			payment_entry: target,
		}).then(function (detail) {
			var rows = (detail && detail.rows) || [];

			if (!rows.length) {
				setSummaryModal(
					"Payment Entry Detail",
					target,
					"<div style='color:#b91c1c;'>No payment rows available for this payment entry under selected filters.</div>"
				);
				return;
			}
			var totalBooked = 0;
			var totalPaid = 0;
			var totalUnpaid = 0;
			var totalPayment = 0;
			var html =
				summaryHeaderHtml("Payment Entry Detail", target) +
				"<div class='pp-summary-chips'>" +
				"<span class='pp-summary-chip'>Payment Entry: " +
				esc(target) +
				"</span>" +
				"<span class='pp-summary-chip'>Employees: " +
				esc(rows.length) +
				"</span>" +
				"</div>";
			html +=
				"<table class='pp-table'><thead><tr><th>Employee</th><th>Entry Number</th><th>Net Salary</th><th>Paid Before</th><th>Unpaid Before</th><th>Payment Amount</th><th>Paid After</th><th>Unpaid After</th><th>Status</th></tr></thead><tbody>";
			rows.forEach(function (r) {
				totalBooked += num(r.net_salary);
				totalPaid += num(r.paid_amount_after);
				totalUnpaid += num(r.unpaid_amount_after);
				totalPayment += num(r.payment_amount);
				html +=
					"<tr>" +
					"<td>" +
					esc(r.name1 || r.employee || "") +
					"</td>" +
					"<td>" +
					esc(r.salary_entry || "") +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.net_salary)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.paid_amount_before)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.unpaid_amount_before)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.payment_amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.paid_amount_after)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.unpaid_amount_after)) +
					"</td>" +
					"<td>" +
					statusBadgeHtml(r.status || "") +
					"</td>" +
					"</tr>";
			});
			html +=
				"<tr class='pp-year-total'><td>Total</td><td></td><td class='num pp-amt-col'>" +
				esc(fmt(totalBooked)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totalPaid)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totalUnpaid)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totalPayment)) +
				"</td><td></td><td></td><td></td></tr>";
			html += "</tbody></table>";
			setSummaryModal("Payment Entry Detail", target, html);
			if (printNow) {
				setTimeout(function () {
					printSummaryModal();
				}, 60);
			}
		});
	}

	function showJournalEntrySummary(jvName) {
		var modal = el("pp-summary-modal");
		var subtitle = el("pp-summary-subtitle");
		var content = el("pp-summary-content");
		if (!modal || !subtitle || !content || !jvName) return;
		subtitle.textContent = "Journal Entry: " + jvName;
		content.innerHTML = "<div style='color:#334155;'>Loading JV detail...</div>";
		modal.style.display = "flex";
		callApi("frappe.client.get", { doctype: "Journal Entry", name: jvName })
			.then(function (doc) {
				if (!doc) {
					content.innerHTML = "<div style='color:#b91c1c;'>JV not found.</div>";
					return;
				}
				var totalDr = 0;
				var totalCr = 0;
				var html =
					"<div class='pp-summary-chips'>" +
					"<span class='pp-summary-chip'>Voucher: " +
					esc(doc.voucher_type || "Journal Entry") +
					"</span>" +
					"<span class='pp-summary-chip'>Posting Date: " +
					esc(doc.posting_date || "-") +
					"</span>" +
					"<span class='pp-summary-chip'>Company: " +
					esc(doc.company || "-") +
					"</span>" +
					"<span class='pp-summary-chip'>Docstatus: " +
					esc(String(doc.docstatus || 0)) +
					"</span>" +
					"</div>";
				html +=
					"<table class='pp-table'><thead><tr><th>Account</th><th>Party</th><th>Debit</th><th>Credit</th><th>Remark</th></tr></thead><tbody>";
				(doc.accounts || []).forEach(function (a) {
					var dr = num(a.debit_in_account_currency || a.debit || 0);
					var cr = num(a.credit_in_account_currency || a.credit || 0);
					totalDr += dr;
					totalCr += cr;
					var party = "";
					if (a.party_type || a.party)
						party = String(a.party_type || "") + (a.party ? ": " + a.party : "");
					html +=
						"<tr>" +
						"<td>" +
						esc(a.account || "") +
						"</td>" +
						"<td>" +
						esc(party) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(dr)) +
						"</td>" +
						"<td class='num pp-amt-col'>" +
						esc(fmt(cr)) +
						"</td>" +
						"<td>" +
						esc(a.user_remark || "") +
						"</td>" +
						"</tr>";
				});
				html +=
					"<tr class='pp-year-total'><td>Total</td><td></td><td class='num pp-amt-col'>" +
					esc(fmt(totalDr)) +
					"</td><td class='num pp-amt-col'>" +
					esc(fmt(totalCr)) +
					"</td><td></td></tr>";
				html += "</tbody></table>";
				content.innerHTML = html;
			})
			.catch(function (e) {
				content.innerHTML =
					"<div style='color:#b91c1c;'>Unable to load JV detail: " +
					esc(prettyError(errText(e))) +
					"</div>";
			});
	}

	function renderJournalEntryInline(resultEl, jvName) {
		if (!resultEl || !jvName) return;
		callApi("frappe.client.get", { doctype: "Journal Entry", name: jvName })
			.then(function (doc) {
				if (!doc) return;
				var totalDr = 0;
				var totalCr = 0;
				var html = "<br><br><strong>Posted JV Quick Preview</strong>";
				html +=
					"<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Account</th><th>Party</th><th>Debit</th><th>Credit</th></tr></thead><tbody>";
				(doc.accounts || []).forEach(function (a) {
					var dr = num(a.debit_in_account_currency || a.debit || 0);
					var cr = num(a.credit_in_account_currency || a.credit || 0);
					totalDr += dr;
					totalCr += cr;
					var party = "";
					if (a.party_type || a.party)
						party = String(a.party_type || "") + (a.party ? ": " + a.party : "");
					html +=
						"<tr><td>" +
						esc(a.account || "") +
						"</td><td>" +
						esc(party) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(dr)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(cr)) +
						"</td></tr>";
				});
				html +=
					"<tr class='pp-year-total'><td>Total</td><td></td><td class='num pp-amt-col'>" +
					esc(fmt(totalDr)) +
					"</td><td class='num pp-amt-col'>" +
					esc(fmt(totalCr)) +
					"</td></tr></tbody></table>";
				resultEl.innerHTML += html;
			})
			.catch(function (_e) {});
	}

	function renderCreatedEntriesPanel(tab) {
		if (tab === "data_entry") {
			setCreatedListHtml("");
			return;
		}
		if (tab === "salary_creation") {
			var salaryHistoryFrom = String(
				(el("pp-jv-history-from") && el("pp-jv-history-from").value) ||
					getWorkflowHistoryRange("salary_creation").from ||
					""
			).trim();
			var salaryHistoryTo = String(
				(el("pp-jv-history-to") && el("pp-jv-history-to").value) ||
					getWorkflowHistoryRange("salary_creation").to ||
					""
			).trim();
			var salaryStatus = getWorkflowStatusFilter("salary_creation");
			var salaryBooking = String(
				(el("pp-jv-history-booking-status") && el("pp-jv-history-booking-status").value) ||
					salaryStatus.booking ||
					""
			).trim();
			var salaryPayment = String(
				(el("pp-jv-history-payment-status") && el("pp-jv-history-payment-status").value) ||
					salaryStatus.payment ||
					""
			).trim();
			setWorkflowHistoryRange("salary_creation", salaryHistoryFrom, salaryHistoryTo);
			setWorkflowStatusFilter("salary_creation", salaryBooking, salaryPayment);
			var salaryDocs = filterDocsByStatus(
				filterRowsByDateRange(
					uniqueCreatedSalaryBatchDocs(),
					salaryHistoryFrom,
					salaryHistoryTo
				),
				salaryBooking,
				salaryPayment
			);
			var salaryFilterHeader =
				"<div style='margin-top:10px;'><strong>Created Salary Entries</strong></div>" +
				"<div class='pp-jv-grid' style='margin-top:6px;'>" +
				"<label>History From <input type='date' id='pp-jv-history-from' value='" +
				esc(salaryHistoryFrom || "") +
				"' /></label>" +
				"<label>History To <input type='date' id='pp-jv-history-to' value='" +
				esc(salaryHistoryTo || "") +
				"' /></label>" +
				"<label>Booking Status <select id='pp-jv-history-booking-status'>" +
				"<option value=''>All</option><option value='Booked'" +
				(salaryBooking === "Booked" ? " selected" : "") +
				">Booked</option><option value='UnBooked'" +
				(salaryBooking === "UnBooked" ? " selected" : "") +
				">UnBooked</option><option value='Partly Booked'" +
				(salaryBooking === "Partly Booked" ? " selected" : "") +
				">Partly Booked</option>" +
				"</select></label>" +
				"<label>Payment Status <select id='pp-jv-history-payment-status'>" +
				"<option value=''>All</option><option value='Paid'" +
				(salaryPayment === "Paid" ? " selected" : "") +
				">Paid</option><option value='Unpaid'" +
				(salaryPayment === "Unpaid" ? " selected" : "") +
				">Unpaid</option><option value='Partly Paid'" +
				(salaryPayment === "Partly Paid" ? " selected" : "") +
				">Partly Paid</option>" +
				"</select></label>" +
				"</div>";
			if (!salaryDocs.length) {
				setCreatedListHtml(
					salaryFilterHeader +
						"<div style='margin-top:8px;color:#64748b;'>No booking JV created in selected filter.</div>"
				);
				return;
			}
			var salaryPage = paginateHistoryRows("salary_creation_history", salaryDocs, 10);
			var html = "";
			if (salaryPage.rows.length) {
				state.entryMeta.selected_salary_history =
					state.entryMeta.selected_salary_history || {};
				var selectedHistory = state.entryMeta.selected_salary_history;
				var selectedCount = Object.keys(selectedHistory).filter(function (k) {
					return !!selectedHistory[k];
				}).length;
				var tSalary = 0,
					tAllow = 0,
					tAdv = 0,
					tOther = 0,
					tNet = 0;
				html += salaryFilterHeader;
				html +=
					"<div class='pp-entry-actions' style='margin-top:6px;'>" +
					"<button type='button' class='btn btn-default btn-xs' id='pp-salary-history-select-page'>Select Page</button>" +
					"<button type='button' class='btn btn-default btn-xs' id='pp-salary-history-clear-selected'>Clear Selected</button>" +
					"<button type='button' class='btn btn-success btn-xs' id='pp-salary-history-pay-selected'>Pay Selected Entry</button>" +
					"<span style='color:#334155;font-size:12px;'>Selected Entries: <strong id='pp-salary-history-selected-count'>" +
					esc(selectedCount) +
					"</strong></span>" +
					"</div>";
				html +=
					"<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Select</th><th>Batch Entry</th><th>DE No</th><th>PO No</th><th>Delivery No</th><th>JV Salary</th><th>JV Payment</th><th>Total Salary</th><th>Allowance</th><th>Advance Deduction</th><th>Other Deduction</th><th>Net Salary</th><th>Book</th><th>Pay</th><th>Salary View</th><th>JV View</th></tr></thead><tbody>";
				(salaryPage.rows || []).forEach(function (r) {
					tSalary += num(r.amount);
					tAllow += num(r.allowance_amount);
					tAdv += num(r.advance_deduction_amount);
					tOther += num(r.other_deduction_amount);
					tNet += num(r.net_salary);
					var entriesCsv = String(r._entries_csv || r.name || "").trim();
					var entryKeys = entriesCsv
						.split(",")
						.map(function (x) {
							return String(x || "").trim();
						})
						.filter(Boolean);
					var checked = entryKeys.some(function (k) {
						return !!selectedHistory[k];
					});
					var bookedDone =
						String(r.booking_status || "") === "Booked"
							? "<span style='color:#64748b;'>Done</span>"
							: "<button type='button' class='btn btn-xs btn-primary pp-salary-history-book' data-entry='" +
							  esc(entryKeys[0] || "") +
							  "' data-entries='" +
							  esc(entriesCsv) +
							  "'>Book</button>";
					var payAction =
						String(r.payment_status || "") === "Paid"
							? "<span style='color:#64748b;'>Done</span>"
							: "<button type='button' class='btn btn-xs btn-success pp-go-pay-salary-entry' data-entry='" +
							  esc(entryKeys[0] || "") +
							  "' data-entries='" +
							  esc(entriesCsv) +
							  "'>Pay</button>";
					html +=
						"<tr>" +
						"<td><input type='checkbox' class='pp-salary-history-select' data-entry='" +
						esc(entryKeys[0] || "") +
						"' data-entries='" +
						esc(entriesCsv) +
						"'" +
						(checked ? " checked" : "") +
						"></td>" +
						"<td>" +
						(r.batch_entry
							? "<a target='_blank' href='/app/per-piece-salary-batch/" +
							  encodeURIComponent(r.batch_entry) +
							  "'>" +
							  esc(r.batch_entry) +
							  "</a>"
							: "") +
						"</td>" +
						"<td><a target='_blank' href='/app/per-piece-salary/" +
						encodeURIComponent(entryKeys[0] || "") +
						"'>" +
						esc((entryKeys || []).join(", ")) +
						"</a></td>" +
						"<td>" +
						esc(r.po_number || "") +
						"</td>" +
						"<td>" +
						esc(r.delivery_note || "") +
						"</td>" +
						"<td>" +
						renderJvLinks(r.jv_entry_no || "") +
						"</td>" +
						"<td>" +
						renderJvLinks(r.payment_jv_no || "") +
						"</td>" +
						"<td class='num pp-amt-col pp-salary-history-cell' data-entry='" +
						esc(r.name) +
						"' data-col='salary'>" +
						esc(fmt(r.amount)) +
						"</td>" +
						"<td class='num pp-amt-col pp-salary-history-cell' data-entry='" +
						esc(r.name) +
						"' data-col='allowance'>" +
						esc(fmt(r.allowance_amount)) +
						"</td>" +
						"<td class='num pp-amt-col pp-salary-history-cell' data-entry='" +
						esc(r.name) +
						"' data-col='advance'>" +
						esc(fmt(r.advance_deduction_amount)) +
						"</td>" +
						"<td class='num pp-amt-col pp-salary-history-cell' data-entry='" +
						esc(r.name) +
						"' data-col='other'>" +
						esc(fmt(r.other_deduction_amount)) +
						"</td>" +
						"<td class='num pp-amt-col pp-salary-history-cell' data-entry='" +
						esc(r.name) +
						"' data-col='net'>" +
						esc(fmt(r.net_salary)) +
						"</td>" +
						"<td>" +
						bookedDone +
						"</td>" +
						"<td>" +
						payAction +
						"</td>" +
						"<td><button type='button' class='btn btn-xs btn-info pp-view-salary-create' data-entry='" +
						esc(entryKeys[0] || "") +
						"' data-entries='" +
						esc(entriesCsv) +
						"' data-batch='" +
						esc(r.batch_entry || "") +
						"'>View</button></td>" +
						"<td>" +
						(r.jv_entry_no
							? "<button type='button' class='btn btn-xs btn-info pp-view-jv' data-jv='" +
							  esc(r.jv_entry_no) +
							  "'>View Debit/Credit</button>"
							: "") +
						"</td>" +
						"</tr>";
				});
				html +=
					"<tr class='pp-year-total'><td></td><td>Total</td><td></td><td></td><td></td><td></td><td></td><td id='pp-salary-history-total-salary' class='num pp-amt-col'>" +
					esc(fmt(tSalary)) +
					"</td><td id='pp-salary-history-total-allowance' class='num pp-amt-col'>" +
					esc(fmt(tAllow)) +
					"</td><td id='pp-salary-history-total-advance' class='num pp-amt-col'>" +
					esc(fmt(tAdv)) +
					"</td><td id='pp-salary-history-total-other' class='num pp-amt-col'>" +
					esc(fmt(tOther)) +
					"</td><td id='pp-salary-history-total-net' class='num pp-amt-col'>" +
					esc(fmt(tNet)) +
					"</td><td></td><td></td><td></td><td></td><td></td></tr>";
				html += "</tbody></table>";
				html += historyPagerHtml(salaryPage);
			}
			setCreatedListHtml(html);
			if (salaryPage && salaryPage.rows && salaryPage.rows.length) {
				hydrateSalaryHistoryFinancials(salaryPage.rows);
			}
			return;
		}
		if (tab === "payment_manage") {
			var paymentHistoryFrom = String(
				(el("pp-pay-history-from") && el("pp-pay-history-from").value) ||
					getWorkflowHistoryRange("payment_manage").from ||
					""
			).trim();
			var paymentHistoryTo = String(
				(el("pp-pay-history-to") && el("pp-pay-history-to").value) ||
					getWorkflowHistoryRange("payment_manage").to ||
					""
			).trim();
			var paymentStatus = getWorkflowStatusFilter("payment_manage");
			var payBooking = String(
				(el("pp-pay-history-booking-status") &&
					el("pp-pay-history-booking-status").value) ||
					paymentStatus.booking ||
					""
			).trim();
			var payPayment = String(
				(el("pp-pay-history-payment-status") &&
					el("pp-pay-history-payment-status").value) ||
					paymentStatus.payment ||
					""
			).trim();
			setWorkflowHistoryRange("payment_manage", paymentHistoryFrom, paymentHistoryTo);
			setWorkflowStatusFilter("payment_manage", payBooking, payPayment);
			var phtmlHeader =
				"<div style='margin-top:10px;'><strong>Created Payment JV Entries</strong></div>" +
				"<div class='pp-jv-grid' style='margin-top:6px;'>" +
				"<label>History From <input type='date' id='pp-pay-history-from' value='" +
				esc(paymentHistoryFrom || "") +
				"' /></label>" +
				"<label>History To <input type='date' id='pp-pay-history-to' value='" +
				esc(paymentHistoryTo || "") +
				"' /></label>" +
				"<label>Booking Status <select id='pp-pay-history-booking-status'>" +
				"<option value=''>All</option><option value='Booked'" +
				(payBooking === "Booked" ? " selected" : "") +
				">Booked</option><option value='UnBooked'" +
				(payBooking === "UnBooked" ? " selected" : "") +
				">UnBooked</option><option value='Partly Booked'" +
				(payBooking === "Partly Booked" ? " selected" : "") +
				">Partly Booked</option>" +
				"</select></label>" +
				"<label>Payment Status <select id='pp-pay-history-payment-status'>" +
				"<option value=''>All</option><option value='Paid'" +
				(payPayment === "Paid" ? " selected" : "") +
				">Paid</option><option value='Unpaid'" +
				(payPayment === "Unpaid" ? " selected" : "") +
				">Unpaid</option><option value='Partly Paid'" +
				(payPayment === "Partly Paid" ? " selected" : "") +
				">Partly Paid</option>" +
				"</select></label>" +
				"</div>";
			setCreatedListHtml(
				phtmlHeader +
					"<div style='margin-top:8px;color:#334155;'>Loading payment entries...</div>"
			);
			callApi("per_piece_payroll.api.get_per_piece_payment_entries", { limit: 500 })
				.then(function (docs) {
					var payRows = filterRowsByDateRange(
						docs || [],
						paymentHistoryFrom,
						paymentHistoryTo
					);
					if (!payRows.length) {
						setCreatedListHtml(
							phtmlHeader +
								"<div style='margin-top:8px;color:#64748b;'>No payment entries created in selected filter.</div>"
						);
						return;
					}
					var payPage = paginateHistoryRows("payment_manage_history", payRows, 10);
					var tPayAmt = 0,
						tRows = 0;
					var phtml =
						phtmlHeader +
						"<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Payment Entry</th><th>Batch Entry</th><th>Salary Entries</th><th>JV Payment</th><th>Status</th><th>Payment Amount</th><th>Rows</th><th>View</th><th>Print</th><th>Open</th></tr></thead><tbody>";
					(payPage.rows || []).forEach(function (r) {
						tPayAmt += num(r.total_payment_amount);
						tRows += num(r.rows || 0);
						var jvName = String(r.journal_entry || "").trim();
						var batchNames = (r.salary_batch_entries || []).filter(Boolean);
						phtml +=
							"<tr><td>" +
							esc(r.name || "") +
							"</td><td>" +
							batchNames
								.map(function (b) {
									return (
										"<a target='_blank' href='/app/per-piece-salary-batch/" +
										encodeURIComponent(b) +
										"'>" +
										esc(b) +
										"</a>"
									);
								})
								.join(", ") +
							"</td><td>" +
							esc((r.salary_entries || []).join(", ")) +
							"</td><td>" +
							(jvName
								? "<a target='_blank' href='/app/journal-entry/" +
								  encodeURIComponent(jvName) +
								  "'>" +
								  esc(jvName) +
								  "</a>"
								: "") +
							"</td><td>" +
							esc(String(r.jv_status || "")) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(r.total_payment_amount)) +
							"</td><td class='num'>" +
							esc(r.rows || 0) +
							"</td><td><button type='button' class='btn btn-xs btn-info pp-view-payment-create' data-jv='" +
							esc(r.name || "") +
							"'>View</button></td><td><button type='button' class='btn btn-xs btn-primary pp-print-payment-create' data-jv='" +
							esc(r.name || "") +
							"'>Print</button></td><td>" +
							(jvName
								? "<a target='_blank' href='/app/journal-entry/" +
								  encodeURIComponent(jvName) +
								  "'>Open</a>"
								: "") +
							"</td></tr>";
					});
					phtml +=
						"<tr class='pp-year-total'><td>Total</td><td></td><td></td><td></td><td></td><td class='num pp-amt-col'>" +
						esc(fmt(tPayAmt)) +
						"</td><td class='num'>" +
						esc(fmt(tRows)) +
						"</td><td></td><td></td><td></td></tr>";
					phtml += "</tbody></table>" + historyPagerHtml(payPage);
					setCreatedListHtml(phtml);
				})
				.catch(function (e) {
					setCreatedListHtml(
						phtmlHeader +
							"<div style='margin-top:8px;color:#b91c1c;'>Failed to load payment entries: " +
							esc(prettyError(errText(e))) +
							"</div>"
					);
				});
			return;
		}
		setCreatedListHtml("");
	}

	var dataEntryHelpers =
		(window.PerPieceDataEntryHelpers &&
			window.PerPieceDataEntryHelpers.create({
				state: state,
				num: num,
				whole: whole,
				callApi: callApi,
				rebuildEntryMetaLookups: rebuildEntryMetaLookups,
				renderDataEntryTab: function () {
					renderDataEntryTab();
				},
			})) ||
		{};

	var getAutoEntryProduct =
		dataEntryHelpers.getAutoEntryProduct ||
		function () {
			return "";
		};
	var getCurrentGroupItems =
		dataEntryHelpers.getCurrentGroupItems ||
		function () {
			return [];
		};
	var getEntryProcessOptions =
		dataEntryHelpers.getEntryProcessOptions ||
		function () {
			return [];
		};
	var entryRowIsBlank =
		dataEntryHelpers.entryRowIsBlank ||
		function () {
			return true;
		};
	var syncEntryEmployeeToRows = dataEntryHelpers.syncEntryEmployeeToRows || function () {};
	var applyEntryItemDefaults = dataEntryHelpers.applyEntryItemDefaults || function () {};
	var syncEntryRowsToItemGroup = dataEntryHelpers.syncEntryRowsToItemGroup || function () {};
	var populateEntryRowsFromItemGroup =
		dataEntryHelpers.populateEntryRowsFromItemGroup || function () {};
	var loadSelectedItemProcessRows =
		dataEntryHelpers.loadSelectedItemProcessRows || function () {};
	var newEntryRow =
		dataEntryHelpers.newEntryRow ||
		function () {
			return {};
		};
	var ensureEntryRows = dataEntryHelpers.ensureEntryRows || function () {};
	var entryAmount =
		dataEntryHelpers.entryAmount ||
		function () {
			return 0;
		};

	var entryUI =
		(window.PerPieceEntryUI &&
			window.PerPieceEntryUI.create({
				state: state,
				el: el,
				esc: esc,
				num: num,
				whole: whole,
				fmt: fmt,
				lineRate: lineRate,
				parseDecimalInput: parseDecimalInput,
				parseDateOnly: parseDateOnly,
				ymd: ymd,
				callApi: callApi,
				callGetList: callGetList,
				setOptions: setOptions,
				uniqueSalaryDocs: uniqueSalaryDocs,
				filterDataEntryDocsByDate: filterDataEntryDocsByDate,
				statusBadgeHtml: statusBadgeHtml,
				employeeLabel: employeeLabel,
				entrySequenceNo: entrySequenceNo,
				compareEntryNoDesc: compareEntryNoDesc,
				getRowsByHeaderFilters: getRowsByHeaderFilters,
				filterRowsByDateRange: filterRowsByDateRange,
				getWorkflowHistoryRange: getWorkflowHistoryRange,
				errText: errText,
				prettyError: prettyError,
				showResult: showResult,
				notifyActionResult: notifyActionResult,
				refreshHeaderFilterOptions: refreshHeaderFilterOptions,
				refreshWorkflowEntrySelectors: refreshWorkflowEntrySelectors,
				resetEntryFiltersToAll: resetEntryFiltersToAll,
				setWorkflowHistoryRange: setWorkflowHistoryRange,
				defaultDateWindow: defaultDateWindow,
				rebuildEntryMetaLookups: rebuildEntryMetaLookups,
				paginateHistoryRows: paginateHistoryRows,
				historyPagerHtml: historyPagerHtml,
				getWorkflowStatusFilter: getWorkflowStatusFilter,
				setWorkflowStatusFilter: setWorkflowStatusFilter,
				showPerPieceSummary: showPerPieceSummary,
				showDataEntryEnteredRows: showDataEntryEnteredRows,
				switchWorkspaceMode: switchWorkspaceMode,
				setPageForCurrentTab: setPageForCurrentTab,
				loadReport: loadReport,
				renderCreatedEntriesPanel: renderCreatedEntriesPanel,
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
			})) ||
		{};

	var renderDataEntryTab = entryUI.renderDataEntryTab || function () {};
	var loadEntryDocForEdit =
		entryUI.loadEntryDocForEdit ||
		function () {
			return Promise.resolve();
		};
	var saveDataEntry = entryUI.saveDataEntry || function () {};

	function toggleWorkflowCards() {
		var salaryCard = el("pp-salary-jv-card");
		var paymentCard = el("pp-payment-jv-card");
		if (!salaryCard || !paymentCard) return;
		salaryCard.style.display = state.currentTab === "salary_creation" ? "block" : "none";
		paymentCard.style.display = state.currentTab === "payment_manage" ? "block" : "none";
	}

	function toggleEntryScreenMode() {
		var wrap = document.querySelector(".pp-wrap");
		if (!wrap) return;
		var tab = String(state.currentTab || "");
		var isEntryScreen =
			tab === "data_entry" || tab === "salary_creation" || tab === "payment_manage";
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

	function ensureWorkflowCardsPosition() {
		var tableWrap = el("pp-table-wrap");
		var salaryCard = el("pp-salary-jv-card");
		var paymentCard = el("pp-payment-jv-card");
		if (!tableWrap || !salaryCard || !paymentCard) return;
		var parent = tableWrap.parentNode;
		if (!parent) return;
		parent.insertBefore(salaryCard, tableWrap);
		parent.insertBefore(paymentCard, tableWrap);
	}

	function renderCurrentTab() {
		var currentTabName = String(state.currentTab || "");
		if (currentTabName === "salary_creation" || currentTabName === "payment_manage") {
			primeSalaryFinancialsForTab(currentTabName);
		}
		var headerFilterOpts = {};
		if (
			currentTabName === "data_entry" ||
			currentTabName === "salary_creation" ||
			currentTabName === "payment_manage"
		) {
			headerFilterOpts.ignore_date_filter = true;
			headerFilterOpts.ignore_po_filter = true;
			headerFilterOpts.ignore_entry_filter = true;
		}
		var rows = getRowsByHeaderFilters(state.rows || [], headerFilterOpts);
		var cols = [];
		var outRows = [];
		var paged = null;
		var skipColumnSearch = false;
		ensureWorkflowCardsPosition();
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
				{ fieldname: "delivery_note", label: "Delivery Note" },
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
				return String(b.per_piece_salary || "").localeCompare(
					String(a.per_piece_salary || "")
				);
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
					{ fieldname: "net_amount", label: "Net Amount", numeric: true },
				],
				rows: outRows,
			};
			filterRenderedTablesBySearch();
			var t = getAdjustedTotals();
			el("pp-totals").innerHTML =
				"<span>Gross: " +
				fmt(t.gross_amount) +
				"</span>" +
				"<span>Advance Deduction: " +
				fmt(t.advance_deduction_amount) +
				"</span>" +
				"<span>Other Deduction: " +
				fmt(t.other_deduction_amount) +
				"</span>" +
				"<span>Net Payable: " +
				fmt(t.net_payable_amount) +
				"</span>";
			var msg = outRows.length + " employee row(s) for salary creation";
			if (state.forcedEntryNo) {
				var s = getEntrySummary(state.forcedEntryNo);
				if (s) {
					msg +=
						" | Entry " +
						state.forcedEntryNo +
						" | Date " +
						(s.from_date || "-") +
						" to " +
						(s.to_date || "-") +
						" | Booking " +
						s.booking_status +
						" | Payment " +
						s.payment_status;
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
				{ fieldname: "payment_status", label: "Payment Status" },
			];
			outRows = buildPaymentEmployeeRows(getBookedRows());
		} else if (state.currentTab === "payment_manage") {
			outRows = (getPaymentRows() || []).filter(function (r) {
				var booked = num(r && r.booked_amount);
				var paid = num(r && r.paid_amount);
				var unpaid = num(r && r.unpaid_amount);
				if (!(unpaid >= 0)) unpaid = Math.max(booked - paid, 0);
				var status = String((r && r.payment_status) || "")
					.trim()
					.toLowerCase();
				var fullyPaidByAmount = booked > 0.0001 && Math.max(booked - paid, 0) <= 0.005;
				if (unpaid <= 0.005 && (status === "paid" || fullyPaidByAmount)) return false;
				return true;
			});
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
					{ fieldname: "payment_status", label: "Payment Status" },
				],
				rows: outRows.map(function (r) {
					return {
						name1: r.name1 || r.employee || "",
						booked_amount: r.booked_amount,
						paid_amount: r.paid_amount,
						unpaid_amount: r.unpaid_amount,
						payment_amount: r.payment_amount,
						payment_status: r.payment_status,
					};
				}),
			};
			filterRenderedTablesBySearch();
			var p = getPaymentTotals();
			el("pp-totals").innerHTML =
				"<span>Booked: " +
				fmt(p.booked) +
				"</span>" +
				"<span>Paid: " +
				fmt(p.paid) +
				"</span>" +
				"<span>Unpaid: " +
				fmt(p.unpaid) +
				"</span>" +
				"<span>Payment This JV: " +
				fmt(p.payment) +
				"</span>";
			var pmsg = outRows.length + " employee row(s) pending payment (paid rows hidden)";
			if (state.forcedEntryNo) {
				var ps = getEntrySummary(state.forcedEntryNo);
				if (ps) {
					pmsg +=
						" | Entry " +
						state.forcedEntryNo +
						" | Date " +
						(ps.from_date || "-") +
						" to " +
						(ps.to_date || "-") +
						" | Booking " +
						ps.booking_status +
						" | Payment " +
						ps.payment_status;
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
				{ fieldname: "closing_balance", label: "Closing Balance", numeric: true },
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
					{ fieldname: "payment_status", label: "Payment Status" },
				],
				rows: outRows,
			};
			filterRenderedTablesBySearch();
			el("pp-msg").textContent = outRows.length + " row(s)";
			renderPagination(paged);
			var est = { qty: 0, amount: 0 };
			outRows.forEach(function (r) {
				est.qty += num(r.qty);
				est.amount += num(r.amount);
			});
			el("pp-totals").innerHTML =
				"<span>Total Qty: " +
				fmt(est.qty) +
				"</span><span>Total Amount: " +
				fmt(est.amount) +
				"</span>";
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
			el("pp-totals").innerHTML =
				"<span>Total Qty: " +
				fmt(slipTotals.qty) +
				"</span><span>Total Amount: " +
				fmt(slipTotals.amount) +
				"</span>";
			renderCreatedEntriesPanel("salary_slip");
			refreshJVAmountsFromAdjustments();
			refreshPaymentAmounts();
			return;
		} else if (state.currentTab === "salary_slip_dc") {
			outRows = rows;
			paged = paginateRows(outRows);
			renderSalarySlipByDCTable(paged.rows);
			state.lastTabRender = { mode: "dom", columns: [], rows: [] };
			filterRenderedTablesBySearch();
			el("pp-msg").textContent =
				"Delivery Note and Entry wise salary slip summary from current filters";
			renderPagination(paged);
			var dcTotals = { net_salary: 0 };
			outRows.forEach(function (r) {
				var amount = num(r.amount);
				var adv = num(r.advance_deduction);
				var allow = num(r.allowance);
				var other = num(r.other_deduction);
				var net = num(r.net_amount);
				if (!net) net = Math.max(amount - adv + allow - other, 0);
				dcTotals.net_salary += net;
			});
			el("pp-totals").innerHTML =
				"<span>Total Net Salary: " + fmt(dcTotals.net_salary) + "</span>";
			renderCreatedEntriesPanel("salary_slip_dc");
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
				{ fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
			];
			outRows = buildEmployeeMonthYearRows(rows);
		} else if (state.currentTab === "month_paid_unpaid") {
			cols = [
				{ fieldname: "month_year", label: "Month / Year" },
				{ fieldname: "booked_amount", label: "Booked", numeric: true },
				{ fieldname: "paid_amount", label: "Paid", numeric: true },
				{ fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
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
				{ fieldname: "payment_status", label: "Payment Status" },
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
				{ fieldname: "payment_status", label: "Payment Status" },
			];
			outRows = buildProcessSummaryRows(rows || []);
		} else if (state.currentTab === "per_piece_salary") {
			cols = [
				{ fieldname: "per_piece_salary", label: "Entry No" },
				{ fieldname: "po_number", label: "PO Number" },
				{ fieldname: "delivery_note", label: "Delivery Note" },
				{ fieldname: "product", label: "Item" },
				{ fieldname: "process_type", label: "Process" },
				{ fieldname: "process_size", label: "Size" },
				{ fieldname: "qty", label: "Qty", numeric: true },
				{ fieldname: "rate", label: "Rate", numeric: true },
				{ fieldname: "amount", label: "Amount", numeric: true },
				{ fieldname: "booking_status", label: "Booking Status" },
				{ fieldname: "payment_status", label: "Payment Status" },
				{ fieldname: "jv_entry_no", label: "Salary JV No" },
				{ fieldname: "payment_jv_no", label: "Payment JV No" },
			];
			outRows = buildEmployeeItemWiseReportRows(rows || []);
		} else if (state.currentTab === "po_number") {
			cols = [
				{ fieldname: "po_number", label: "PO Number", po_summary_link: true },
				{ fieldname: "po_view", label: "View", po_action: "view" },
				{
					fieldname: "po_print_process",
					label: "Print Process Wise",
					po_action: "print_process",
				},
				{
					fieldname: "po_print_product",
					label: "Print Product Wise",
					po_action: "print_product",
				},
				{ fieldname: "qty", label: "Qty", numeric: true },
				{ fieldname: "rate", label: "Rate", numeric: true },
				{ fieldname: "amount", label: "Amount", numeric: true },
				{ fieldname: "booked_amount", label: "Booked", numeric: true },
				{ fieldname: "unbooked_amount", label: "UnBooked", numeric: true },
				{ fieldname: "paid_amount", label: "Paid", numeric: true },
				{ fieldname: "unpaid_amount", label: "Unpaid", numeric: true },
				{ fieldname: "booking_status", label: "Booking Status" },
				{ fieldname: "payment_status", label: "Payment Status" },
			];
			outRows = groupRows(rows, ["po_number"], function (r) {
				return {
					po_number: r.po_number || "(Blank)",
					qty: 0,
					amount: 0,
					rate: 0,
					booked_amount: 0,
					unbooked_amount: 0,
					paid_amount: 0,
					unpaid_amount: 0,
				};
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
			outRows.forEach(function (r) {
				pdQty += num(r.qty);
				pdAmount += num(r.amount);
			});
			el("pp-totals").innerHTML =
				"<span>Total Qty: " +
				fmt(pdQty) +
				"</span><span>Total Amount: " +
				fmt(pdAmount) +
				"</span>";
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
			var jb = 0,
				jp = 0,
				ju = 0;
			outRows.forEach(function (r) {
				jb += num(r.booked_amount);
				jp += num(r.paid_amount);
				ju += num(r.unpaid_amount);
			});
			el("pp-totals").innerHTML =
				"<span>Total Booked: " +
				fmt(jb) +
				"</span><span>Total Paid: " +
				fmt(jp) +
				"</span><span>Total Unpaid: " +
				fmt(ju) +
				"</span>";
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

		var totalQty = 0,
			totalAmount = 0;
		if (state.currentTab === "month_year_salary") {
			outRows.forEach(function (r) {
				if (String(r.period_type || "") !== "Month") return;
				totalQty += num(r.qty);
				totalAmount += num(r.amount);
			});
			el("pp-totals").innerHTML =
				"<span>Monthly Qty Total: " +
				fmt(totalQty) +
				"</span><span>Monthly Amount Total: " +
				fmt(totalAmount) +
				"</span>";
			el("pp-msg").textContent =
				outRows.length + " row(s) including month-wise and yearly totals";
			renderCreatedEntriesPanel(state.currentTab);
			refreshJVAmountsFromAdjustments();
			refreshPaymentAmounts();
			return;
		}
		if (state.currentTab === "month_paid_unpaid") {
			var mb = 0,
				mp = 0,
				mu = 0;
			outRows.forEach(function (r) {
				mb += num(r.booked_amount);
				mp += num(r.paid_amount);
				mu += num(r.unpaid_amount);
			});
			el("pp-totals").innerHTML =
				"<span>Total Booked: " +
				fmt(mb) +
				"</span><span>Total Paid: " +
				fmt(mp) +
				"</span><span>Total Unpaid: " +
				fmt(mu) +
				"</span>";
			el("pp-msg").textContent =
				outRows.length + " month row(s) in month-wise paid/unpaid report";
			renderCreatedEntriesPanel(state.currentTab);
			refreshJVAmountsFromAdjustments();
			refreshPaymentAmounts();
			return;
		}
		if (state.currentTab === "simple_month_amount") {
			var simpleCols = buildSimpleMonthColumns(rows);
			var monthTotals = {};
			var grand = 0;
			simpleCols.forEach(function (m) {
				monthTotals[m.key] = 0;
			});
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
			el("pp-msg").textContent =
				outRows.length + " employee row(s) in simple month-wise amount report";
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
		el("pp-totals").innerHTML =
			"<span>Total Qty: " +
			fmt(totalQty) +
			"</span><span>Total Amount: " +
			fmt(totalAmount) +
			"</span>";
		el("pp-msg").textContent = outRows.length + " row(s)";
		renderCreatedEntriesPanel(state.currentTab);
		refreshJVAmountsFromAdjustments();
		refreshPaymentAmounts();
	}

	function loadReport() {
		setPageForCurrentTab(1);
		el("pp-msg").textContent = "Loading...";
		// Keep workspace cards in sync immediately, even before API completes.
		ensureWorkflowCardsPosition();
		toggleWorkflowCards();
		toggleEntryScreenMode();
		var args = getReportArgs();
		if (
			state.currentTab === "data_entry" ||
			state.currentTab === "salary_creation" ||
			state.currentTab === "payment_manage"
		) {
			args.from_date = "2000-01-01";
			args.to_date = "2099-12-31";
			args.employee = "";
			args.company = "";
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
		callApi("per_piece_payroll.api.get_per_piece_salary_report", args)
			.then(function (msg) {
				state.rows = (msg && msg.data) || [];
				state.paymentEntryBasis = null;
				if (state.entryMeta) {
					state.entryMeta.salaryFinancialByEntry = {};
					state.entryMeta.salaryFinancialPending = {};
				}
				var selectedPayEntry = "";
				if (state.currentTab === "payment_manage") {
					selectedPayEntry = String(
						state.forcedEntryNo ||
							(el("pp-pay-entry-filter") && el("pp-pay-entry-filter").value) ||
							""
					).trim();
				}
				applyReportRateProcessFix(state.rows);
				normalizeReportStatusValues(state.rows);
				state.columns = (msg && msg.columns) || [];
				refreshHeaderFilterOptions();
				var basisPromise = Promise.resolve();
				if (selectedPayEntry) {
					basisPromise = callApi("per_piece_payroll.api.get_payment_entry_basis", {
						entry_no: selectedPayEntry,
					})
						.then(function (basisMsg) {
							if (
								basisMsg &&
								String(basisMsg.entry_no || "").trim() === selectedPayEntry
							) {
								state.paymentEntryBasis = basisMsg;
							}
						})
						.catch(function (e) {
							console.error(e);
							state.paymentEntryBasis = null;
						});
				}
				// Fast first paint: render current tab immediately with current dataset.
				return basisPromise.then(function () {
					rebuildEntryMetaLookups();
					refreshTopProductOptions();
					normalizeExcludedEmployees();
					normalizeAdjustmentsForEmployees();
					normalizePaymentExcludedEmployees();
					normalizePaymentAdjustments();
					renderCurrentTab();
					loadJVEntryOptions();
					loadPaymentJVEntryOptions();

					// Background hydrate for heavy datasets (recent docs + advances), then refresh.
					return loadAllRowsForRecentDocs()
						.then(function () {
							return loadAdvancesFromGL();
						})
						.catch(function (e) {
							console.error(e);
							state.advanceBalances = (msg && msg.advance_balances) || {};
							state.advanceRows = (msg && msg.advance_rows) || [];
							state.advanceMonths = (msg && msg.advance_months) || [];
						})
						.then(function () {
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
				});
			})
			.catch(function (e) {
				el("pp-msg").textContent = "Error loading report";
				var result = el("pp-jv-result");
				if (result) {
					result.style.color = "#b91c1c";
					result.textContent = errText(e);
				}
				// Still render selected tab/cards with last-known data so UI controls remain visible.
				try {
					renderCurrentTab();
				} catch (renderErr) {
					console.error(renderErr);
				}
				console.error(e);
			});
	}

	var workflow =
		(window.PerPieceWorkflow &&
			window.PerPieceWorkflow.create({
				state: state,
				el: el,
				num: num,
				whole: whole,
				fmt: fmt,
				esc: esc,
				callApi: callApi,
				callGetList: callGetList,
				setOptions: setOptions,
				getReportArgs: getReportArgs,
				getWorkflowHistoryRange: getWorkflowHistoryRange,
				parseEntryNoList: parseEntryNoList,
				getPaymentRows: getPaymentRows,
				getPaymentPostingRows: getPaymentPostingRows,
				getAdjustedEmployeeRows: getAdjustedEmployeeRows,
				setJVAmounts: setJVAmounts,
				setPaymentAmounts: setPaymentAmounts,
				confirmActionModal: confirmActionModal,
				notifyActionResult: notifyActionResult,
				renderJournalEntryInline: renderJournalEntryInline,
				showJournalEntrySummary: showJournalEntrySummary,
				showResult: showResult,
				prettyError: prettyError,
				errText: errText,
				resetEntryFiltersToAll: resetEntryFiltersToAll,
				loadReport: function () {
					loadReport();
				},
			})) ||
		{};

	var loadJVEntryOptions = workflow.loadJVEntryOptions || function () {};
	var loadPaymentJVEntryOptions = workflow.loadPaymentJVEntryOptions || function () {};
	var selectPreferred = workflow.selectPreferred || function () {};
	var selectPreferredPayable = workflow.selectPreferredPayable || function () {};
	var loadCompanies =
		workflow.loadCompanies ||
		function () {
			return Promise.resolve();
		};
	var loadAccountsForCompany = workflow.loadAccountsForCompany || function () {};
	var loadPaymentAccountsForCompany = workflow.loadPaymentAccountsForCompany || function () {};
	var getJVArgs =
		workflow.getJVArgs ||
		function () {
			return {};
		};
	var getPaymentJVArgs =
		workflow.getPaymentJVArgs ||
		function () {
			return {};
		};
	var previewJV = workflow.previewJV || function () {};
	var previewPaymentJV = workflow.previewPaymentJV || function () {};
	var createPaymentJV = workflow.createPaymentJV || function () {};
	var cancelPaymentJV = workflow.cancelPaymentJV || function () {};
	var createJV = workflow.createJV || function () {};
	var recalculateSelectedEntry = workflow.recalculateSelectedEntry || function () {};
	var cancelJVEntry = workflow.cancelJVEntry || function () {};

	function isEntryTab(tabName) {
		return (
			["data_entry", "salary_creation", "payment_manage"].indexOf(
				String(tabName || "").trim()
			) >= 0
		);
	}

	function switchWorkspaceMode(mode, skipReload) {
		state.workspaceMode = mode === "entry" ? "entry" : "reporting";
		var filters = document.querySelector(".pp-filters");
		if (filters) filters.style.display = state.workspaceMode === "entry" ? "none" : "";
		if (el("pp-workspace-reporting"))
			el("pp-workspace-reporting").classList.toggle(
				"active",
				state.workspaceMode === "reporting"
			);
		if (el("pp-workspace-entry"))
			el("pp-workspace-entry").classList.toggle("active", state.workspaceMode === "entry");
		document.querySelectorAll(".pp-tab").forEach(function (btn) {
			var ws = String(btn.getAttribute("data-workspace") || "reporting");
			btn.style.display = ws === state.workspaceMode ? "" : "none";
		});
		if (state.workspaceMode === "entry" && !isEntryTab(state.currentTab))
			state.currentTab = "data_entry";
		if (state.workspaceMode === "reporting" && isEntryTab(state.currentTab))
			state.currentTab = "all";
		document.querySelectorAll(".pp-tab").forEach(function (x) {
			x.classList.remove("active");
		});
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
				document.querySelectorAll(".pp-tab").forEach(function (x) {
					x.classList.remove("active");
				});
				btn.classList.add("active");
				state.currentTab = btn.getAttribute("data-tab");
				setPageForCurrentTab(1);
				loadReport();
			});
		});
		var boot = window.PER_PIECE_BOOT || {};
		var bootWorkspace =
			String(boot.workspace || "entry").trim() === "reporting" ? "reporting" : "entry";
		var bootTab = String(boot.tab || "").trim();
		try {
			delete window.PER_PIECE_BOOT;
		} catch (e) {
			window.PER_PIECE_BOOT = null;
		}
		if (bootTab) state.currentTab = bootTab;
		switchWorkspaceMode(bootWorkspace, true);
	}

	function setDefaultDates() {
		var win = defaultDateWindow();
		var from = win.from;
		var to = win.to;
		try {
			state.employeeSummaryDetail =
				(window.localStorage.getItem("pp_employee_summary_detail") || "") === "1";
		} catch (e) {
			/* ignore storage errors */
		}
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

	if (ensureLoggedInOrRedirect()) return;

	setDefaultDates();
	initTabs();
	Promise.all([loadFilterOptions(), loadDataEntryMasters()])
		.then(loadReport)
		.catch(function (e) {
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
	el("pp-load-btn").addEventListener("click", function () {
		setPageForCurrentTab(1);
		loadReport();
	});
	if (el("pp-sync-status-btn")) {
		el("pp-sync-status-btn").addEventListener("click", function () {
			var msgEl = el("pp-msg");
			if (msgEl) msgEl.textContent = "Force syncing status from JV links...";
			callApi("per_piece_payroll.api.force_sync_per_piece_status", {})
				.then(function (res) {
					var checked = num(res && res.rows_checked);
					var updated = num(res && res.rows_updated);
					if (msgEl)
						msgEl.textContent =
							"Status sync done. Checked: " +
							fmt(checked) +
							" | Updated: " +
							fmt(updated);
					loadReport();
				})
				.catch(function (e) {
					var err = prettyError(errText(e));
					// Fallback for servers where Python API method is not deployed yet.
					if (String(err).indexOf("force_sync_per_piece_status") >= 0) {
						callApi("per_piece_payroll.api.get_per_piece_salary_report", {
							from_date: "2000-01-01",
							to_date: "2099-12-31",
						})
							.then(function () {
								if (msgEl)
									msgEl.textContent =
										"Fallback sync done via report refresh. Please update app code on server for full sync API.";
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
	if (el("pp-company")) {
		el("pp-company").addEventListener("change", function () {
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
	}
	if (el("pp-booking-status")) {
		el("pp-booking-status").addEventListener("change", function () {
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
	}
	if (el("pp-payment-status")) {
		el("pp-payment-status").addEventListener("change", function () {
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
	}
	if (el("pp-po-number")) {
		el("pp-po-number").addEventListener("change", function () {
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
	}
	if (el("pp-sales-order")) {
		el("pp-sales-order").addEventListener("change", function () {
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
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
			state.adjustments = {};
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
			state.adjustments = {};
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
			var current = parseEntryNoList(
				(el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || ""
			);
			var addOne = String(
				(el("pp-jv-entry-filter") && el("pp-jv-entry-filter").value) || ""
			).trim();
			if (!addOne) return;
			if (current.indexOf(addOne) < 0) current.push(addOne);
			if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = current.join(", ");
			state.forcedEntryNo = current.length === 1 ? current[0] : "";
			state.excludedEmployees = {};
			state.adjustments = {};
			if (el("pp-entry-no")) el("pp-entry-no").value = state.forcedEntryNo;
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
	}
	if (el("pp-jv-entry-remove")) {
		el("pp-jv-entry-remove").addEventListener("click", function () {
			var current = parseEntryNoList(
				(el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || ""
			);
			var removeOne = String(
				(el("pp-jv-entry-filter") && el("pp-jv-entry-filter").value) || ""
			).trim();
			if (!removeOne) return;
			current = current.filter(function (x) {
				return x !== removeOne;
			});
			if (el("pp-jv-entry-multi")) el("pp-jv-entry-multi").value = current.join(", ");
			state.forcedEntryNo = current.length === 1 ? current[0] : "";
			state.excludedEmployees = {};
			state.adjustments = {};
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
			setWorkflowHistoryRange(
				"salary_creation",
				el("pp-jv-history-from").value || "",
				(el("pp-jv-history-to") && el("pp-jv-history-to").value) || ""
			);
			state.historyPageByTab.salary_creation_history = 1;
			renderCreatedEntriesPanel("salary_creation");
		});
	}
	if (el("pp-jv-history-to")) {
		el("pp-jv-history-to").addEventListener("change", function () {
			setWorkflowHistoryRange(
				"salary_creation",
				(el("pp-jv-history-from") && el("pp-jv-history-from").value) || "",
				el("pp-jv-history-to").value || ""
			);
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
			var current = parseEntryNoList(
				(el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || ""
			);
			var addOne = String(
				(el("pp-pay-entry-filter") && el("pp-pay-entry-filter").value) || ""
			).trim();
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
			var current = parseEntryNoList(
				(el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || ""
			);
			var removeOne = String(
				(el("pp-pay-entry-filter") && el("pp-pay-entry-filter").value) || ""
			).trim();
			if (!removeOne) return;
			current = current.filter(function (x) {
				return x !== removeOne;
			});
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
			setWorkflowHistoryRange(
				"payment_manage",
				el("pp-pay-history-from").value || "",
				(el("pp-pay-history-to") && el("pp-pay-history-to").value) || ""
			);
			state.historyPageByTab.payment_manage_history = 1;
			renderCreatedEntriesPanel("payment_manage");
		});
	}
	if (el("pp-pay-history-to")) {
		el("pp-pay-history-to").addEventListener("change", function () {
			setWorkflowHistoryRange(
				"payment_manage",
				(el("pp-pay-history-from") && el("pp-pay-history-from").value) || "",
				el("pp-pay-history-to").value || ""
			);
			state.historyPageByTab.payment_manage_history = 1;
			renderCreatedEntriesPanel("payment_manage");
		});
	}
	if (el("pp-search-any")) {
		el("pp-search-any").addEventListener("input", function () {
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
	}
	if (el("pp-employee-summary-detail")) {
		el("pp-employee-summary-detail").addEventListener("change", function () {
			state.employeeSummaryDetail = !!el("pp-employee-summary-detail").checked;
			try {
				window.localStorage.setItem(
					"pp_employee_summary_detail",
					state.employeeSummaryDetail ? "1" : "0"
				);
			} catch (e) {
				/* ignore storage errors */
			}
			setPageForCurrentTab(1);
			renderCurrentTab();
		});
	}
	el("pp-jv-preview-btn").addEventListener("click", previewJV);
	if (el("pp-jv-recalc-entry-btn")) {
		el("pp-jv-recalc-entry-btn").addEventListener("click", recalculateSelectedEntry);
	}
	el("pp-jv-create-btn").addEventListener("click", createJV);
	el("pp-jv-cancel-btn").addEventListener("click", cancelJVEntry);
	el("pp-pay-preview-btn").addEventListener("click", previewPaymentJV);
	el("pp-pay-create-btn").addEventListener("click", createPaymentJV);
	el("pp-pay-cancel-btn").addEventListener("click", cancelPaymentJV);
	if (el("pp-pay-backfill-batch")) {
		el("pp-pay-backfill-batch").addEventListener("click", function () {
			var selected = parseEntryNoList(
				(el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || ""
			);
			var hasSelected = selected && selected.length;
			var question = hasSelected
				? "Backfill selected entries into Salary Batch?"
				: "No selected entries. Backfill ALL old booked entries into Salary Batch?";
			if (!confirm(question)) return;
			showResult(
				el("pp-pay-result"),
				"info",
				"Backfill Running",
				hasSelected
					? "Backfilling selected entries..."
					: "Backfilling all old booked entries..."
			);
			callApi("per_piece_payroll.api.backfill_auto_salary_batches", {
				entry_nos: hasSelected ? selected.join(",") : "",
			})
				.then(function (resp) {
					if (!resp || resp.ok === false) {
						throw new Error((resp && resp.message) || "Backfill failed.");
					}
					showResult(
						el("pp-pay-result"),
						"success",
						"Backfill Completed",
						"Entries: " +
							esc(resp.entries || 0) +
							" | Batches touched: " +
							esc(resp.batches || 0) +
							" | Links created: " +
							esc(resp.entries_linked || 0)
					);
					loadReport();
				})
				.catch(function (e) {
					showResult(
						el("pp-pay-result"),
						"error",
						"Backfill Failed",
						prettyError(errText(e))
					);
				});
		});
	}
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
