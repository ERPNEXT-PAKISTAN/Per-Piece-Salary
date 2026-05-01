(function () {
	function create(deps) {
		var state = deps.state;
		var el = deps.el;
		var esc = deps.esc;
		var num = deps.num;
		var whole = deps.whole;
		var fmt = deps.fmt;
		var isStatusField = deps.isStatusField;
		var isAmountField = deps.isAmountField;
		var statusBadgeHtml = deps.statusBadgeHtml;
		var employeeLabel = deps.employeeLabel;
		var setSummaryHeading = deps.setSummaryHeading;
		var getCurrentTabLabel = deps.getCurrentTabLabel;
		var filterRenderedTablesBySearch = deps.filterRenderedTablesBySearch;
		var getSearchTerm = deps.getSearchTerm;
		var avgRate = deps.avgRate;
		var getAdjustedEmployeeRows = deps.getAdjustedEmployeeRows;
		var normalizeExcludedEmployees = deps.normalizeExcludedEmployees;
		var normalizeAdjustmentsForEmployees = deps.normalizeAdjustmentsForEmployees;
		var getAdjustedTotals = deps.getAdjustedTotals;
		var getPaymentActiveRows = deps.getPaymentActiveRows;
		var normalizePaymentExcludedEmployees = deps.normalizePaymentExcludedEmployees;
		var normalizePaymentAdjustments = deps.normalizePaymentAdjustments;
		var getPaymentTotals = deps.getPaymentTotals;
		var setWorkflowHistoryRange = deps.setWorkflowHistoryRange;
		var switchWorkspaceMode = deps.switchWorkspaceMode;
		var setPageForCurrentTab = deps.setPageForCurrentTab;
		var loadReport = deps.loadReport;
		var renderCurrentTab = deps.renderCurrentTab;
		var getPaymentPostingRows = deps.getPaymentPostingRows;
		var showPerPieceSummary = deps.showPerPieceSummary;
		var showPOSummary = deps.showPOSummary;
		var showDataEntryEmployeeDetails = deps.showDataEntryEmployeeDetails;
		var showSalaryEmployeeDetail = deps.showSalaryEmployeeDetail;
		var showSalarySlipPrint = deps.showSalarySlipPrint;
		var showSalarySlipByEntry = deps.showSalarySlipByEntry;
		var showSalaryEntryWisePrints = deps.showSalaryEntryWisePrints;
		var parseDecimalInput = deps.parseDecimalInput;
		var buildSalarySlipGroups = deps.buildSalarySlipGroups;

		function renderTable(columns, rows) {
			var wrap = el("pp-table-wrap");
			if (!wrap) return;
			var html = "<table class='pp-table'><thead><tr>";
			columns.forEach(function (c) {
				html += "<th>" + esc(c.label) + "</th>";
			});
			html += "</tr></thead><tbody>";
			rows.forEach(function (r) {
				var ptype = String(r.period_type || "");
				var rowClass = "";
				if (r && r._group_header) rowClass = " class='pp-group-head'";
				else if (ptype === "Subtotal" || ptype === "Year" || !!r._is_total)
					rowClass = " class='pp-year-total'";
				html += "<tr" + rowClass + ">";
				columns.forEach(function (c) {
					if (r && r._group_header) {
						if (c === columns[0]) html += "<td>" + esc(r._group_label || "") + "</td>";
						else html += "<td></td>";
						return;
					}
					var val = r[c.fieldname];
					if (
						(c.fieldname === "jv_entry_no" || c.fieldname === "payment_jv_no") &&
						val
					) {
						html +=
							"<td><a target='_blank' href='/app/journal-entry/" +
							encodeURIComponent(val) +
							"'>" +
							esc(val) +
							"</a></td>";
					} else if (c.po_action && r.po_number) {
						var poBtnClass = "btn-primary";
						if (String(c.po_action || "") === "view") poBtnClass = "btn-info";
						html +=
							"<td><button type='button' class='btn btn-xs " +
							poBtnClass +
							" pp-po-action' data-action='" +
							esc(c.po_action) +
							"' data-po='" +
							encodeURIComponent(String(r.po_number || "")) +
							"'>" +
							esc(c.label) +
							"</button></td>";
					} else if (c.po_summary_link && val) {
						html +=
							"<td><button type='button' class='btn btn-xs btn-default pp-po-summary' style='font-weight:700;' data-po='" +
							encodeURIComponent(String(val)) +
							"'>" +
							esc(val) +
							"</button></td>";
					} else if (c.summary_link && val) {
						html +=
							"<td><button type='button' class='btn btn-xs btn-default pp-doc-summary' data-doc='" +
							encodeURIComponent(String(val)) +
							"'>" +
							esc(val) +
							"</button></td>";
					} else if (isStatusField(c.fieldname)) {
						html += "<td>" + statusBadgeHtml(val || "") + "</td>";
					} else {
						var classes = [];
						if (c.numeric) classes.push("num");
						if (isAmountField(c.fieldname)) classes.push("pp-amt-col");
						var cls = classes.length ? " class='" + classes.join(" ") + "'" : "";
						html +=
							"<td" + cls + ">" + esc(c.numeric ? fmt(val) : val || "") + "</td>";
					}
				});
				html += "</tr>";
			});
			var hasExistingTotal = (rows || []).some(function (r) {
				return !!(r && r._is_total);
			});
			if (!hasExistingTotal) {
				var sums = {};
				var firstLabelDone = false;
				columns.forEach(function (c) {
					if (c && c.fieldname) sums[c.fieldname] = 0;
				});
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
			var byPO = {};
			detailRows.forEach(function (r) {
				var po = String((r && r.po_number) || "").trim() || "(Blank)";
				var product = String((r && r.product) || "").trim() || "(Blank)";
				if (!byPO[po]) byPO[po] = {};
				if (!byPO[po][product]) byPO[po][product] = [];
				byPO[po][product].push(r);
			});
			var grandQty = 0;
			var grandAmount = 0;
			var html =
				"<table class='pp-table'><thead><tr><th>PO Number</th><th>Item</th><th>Process</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Grand Total</th></tr></thead><tbody>";
			Object.keys(byPO)
				.sort()
				.forEach(function (po) {
					var poQty = 0;
					var poAmount = 0;
					html +=
						"<tr class='pp-group-head'><td colspan='8'>PO Number: " +
						esc(po) +
						"</td></tr>";

					Object.keys(byPO[po] || {})
						.sort()
						.forEach(function (product) {
							var list = byPO[po][product] || [];
							var productQty = 0;
							var productAmount = 0;

							html +=
								"<tr class='pp-group-head'><td></td><td colspan='7'>Item: " +
								esc(product) +
								"</td></tr>";
							list.sort(function (a, b) {
								var processCmp = String(a.process_type || "").localeCompare(
									String(b.process_type || "")
								);
								if (processCmp !== 0) return processCmp;
								return String(a.process_size || "No Size").localeCompare(
									String(b.process_size || "No Size")
								);
							}).forEach(function (r) {
								var q = num(r.qty);
								var a = num(r.amount);
								productQty += q;
								productAmount += a;
								poQty += q;
								poAmount += a;
								grandQty += q;
								grandAmount += a;
								html +=
									"<tr><td>" +
									esc(po) +
									"</td><td>" +
									esc(product) +
									"</td><td>" +
									esc(r.process_type || "") +
									"</td><td>" +
									esc(r.process_size || "No Size") +
									"</td><td class='num'>" +
									esc(fmt(q)) +
									"</td><td class='num'>" +
									esc(fmt(num(r.rate))) +
									"</td><td class='num pp-amt-col'>" +
									esc(fmt(a)) +
									"</td><td></td></tr>";
							});

							html +=
								"<tr class='pp-year-total'><td>" +
								esc(po) +
								"</td><td>" +
								esc(product) +
								" Sub Total</td><td></td><td></td><td class='num'>" +
								esc(fmt(productQty)) +
								"</td><td class='num'>" +
								esc(fmt(avgRate(productQty, productAmount))) +
								"</td><td class='num pp-amt-col'>" +
								esc(fmt(productAmount)) +
								"</td><td class='num pp-amt-col'>" +
								esc(fmt(productAmount)) +
								"</td></tr>";
						});

					html +=
						"<tr class='pp-year-total'><td>" +
						esc(po) +
						"</td><td>PO Sub Total</td><td></td><td></td><td class='num'>" +
						esc(fmt(poQty)) +
						"</td><td class='num'>" +
						esc(fmt(avgRate(poQty, poAmount))) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(poAmount)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(poAmount)) +
						"</td></tr>";
				});
			html +=
				"<tr class='pp-year-total'><td></td><td>Grand Total</td><td></td><td></td><td class='num'>" +
				esc(fmt(grandQty)) +
				"</td><td class='num'>" +
				esc(fmt(avgRate(grandQty, grandAmount))) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(grandAmount)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(grandAmount)) +
				"</td></tr>";
			html += "</tbody></table>";

			var byEmployee = {};
			detailRows.forEach(function (r) {
				var emp = String((r && (r.name1 || r.employee)) || "").trim() || "(Blank)";
				if (!byEmployee[emp]) byEmployee[emp] = { employee: emp, qty: 0, amount: 0 };
				byEmployee[emp].qty += num(r.qty);
				byEmployee[emp].amount += num(r.amount);
			});
			html += "<div style='margin-top:10px;'><strong>Employee-wise Summary</strong></div>";
			html +=
				"<table class='pp-table' style='margin-top:6px;'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
			Object.keys(byEmployee)
				.sort()
				.forEach(function (emp) {
					var row = byEmployee[emp];
					html +=
						"<tr><td>" +
						esc(row.employee) +
						"</td><td class='num'>" +
						esc(fmt(row.qty)) +
						"</td><td class='num'>" +
						esc(fmt(avgRate(row.qty, row.amount))) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(row.amount)) +
						"</td></tr>";
				});
			html +=
				"<tr class='pp-year-total'><td>Total</td><td class='num'>" +
				esc(fmt(grandQty)) +
				"</td><td class='num'>" +
				esc(fmt(avgRate(grandQty, grandAmount))) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(grandAmount)) +
				"</td></tr>";
			html += "</tbody></table>";
			wrap.innerHTML = html;
		}

		function renderSalaryTable(rows) {
			var wrap = el("pp-table-wrap");
			if (!wrap) return;
			var html =
				"<table class='pp-table'><thead><tr>" +
				"<th>Use In JV</th><th>Employee</th><th>Qty</th><th>Rate</th><th>Salary Amount</th>" +
				"<th>Advance Balance</th><th>Advance Deduction</th><th>Allowance</th><th>Other Deduction</th><th>Net Salary</th>" +
				"</tr></thead><tbody>";
			rows.forEach(function (r) {
				var emp = r.employee || "";
				var label = employeeLabel(r) || "(Blank)";
				var checked = state.excludedEmployees[emp] ? "" : " checked";
				html +=
					"<tr>" +
					"<td><input class='pp-include-emp' type='checkbox' data-employee='" +
					esc(emp) +
					"'" +
					checked +
					"></td>" +
					"<td><button type='button' class='btn btn-xs btn-default pp-salary-emp-detail' data-employee='" +
					esc(emp) +
					"'>" +
					esc(label) +
					"</button></td>" +
					"<td class='num'>" +
					esc(fmt(r.qty)) +
					"</td>" +
					"<td class='num'>" +
					esc(fmt(r.rate)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.advance_balance)) +
					"</td>" +
					"<td><input class='pp-adj-input' type='text' inputmode='decimal' autocomplete='off' data-employee='" +
					esc(emp) +
					"' data-field='advance_deduction' value='" +
					esc(whole(r.advance_deduction)) +
					"'></td>" +
					"<td><input class='pp-adj-input' type='text' inputmode='decimal' autocomplete='off' data-employee='" +
					esc(emp) +
					"' data-field='allowance' value='" +
					esc(whole(r.allowance)) +
					"'></td>" +
					"<td><input class='pp-adj-input' type='text' inputmode='decimal' autocomplete='off' data-employee='" +
					esc(emp) +
					"' data-field='other_deduction' value='" +
					esc(whole(r.other_deduction)) +
					"'></td>" +
					"<td class='num pp-net-cell pp-amt-col' data-employee='" +
					esc(emp) +
					"'>" +
					esc(fmt(r.net_amount)) +
					"</td>" +
					"</tr>";
			});
			var tQty = 0,
				tRate = 0,
				tAmount = 0,
				tAdvanceBal = 0,
				tAdvanceDed = 0,
				tAllowance = 0,
				tOtherDed = 0,
				tNet = 0;
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
			html +=
				"<tr class='pp-year-total'>" +
				"<td></td>" +
				"<td>Total</td>" +
				"<td class='num' id='pp-salary-total-qty'>" +
				esc(fmt(tQty)) +
				"</td>" +
				"<td class='num' id='pp-salary-total-rate'>" +
				esc(fmt(tRate)) +
				"</td>" +
				"<td class='num pp-amt-col' id='pp-salary-total-amount'>" +
				esc(fmt(tAmount)) +
				"</td>" +
				"<td class='num pp-amt-col' id='pp-salary-total-advance-balance'>" +
				esc(fmt(tAdvanceBal)) +
				"</td>" +
				"<td class='num pp-amt-col' id='pp-salary-total-advance-deduction'>" +
				esc(fmt(tAdvanceDed)) +
				"</td>" +
				"<td class='num pp-amt-col' id='pp-salary-total-allowance'>" +
				esc(fmt(tAllowance)) +
				"</td>" +
				"<td class='num pp-amt-col' id='pp-salary-total-other-deduction'>" +
				esc(fmt(tOtherDed)) +
				"</td>" +
				"<td class='num pp-amt-col' id='pp-salary-total-net'>" +
				esc(fmt(tNet)) +
				"</td>" +
				"</tr>";
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
				function refreshSalaryFooterTotals() {
					var totals = {
						qty: 0,
						rate: 0,
						amount: 0,
						advance_balance: 0,
						advance_deduction: 0,
						allowance: 0,
						other_deduction: 0,
						net_amount: 0,
					};
					getAdjustedEmployeeRows().forEach(function (r) {
						totals.qty += num(r.qty);
						totals.rate += num(r.rate);
						totals.amount += num(r.amount);
						totals.advance_balance += num(r.advance_balance);
						totals.advance_deduction += num(r.advance_deduction);
						totals.allowance += num(r.allowance);
						totals.other_deduction += num(r.other_deduction);
						totals.net_amount += num(r.net_amount);
					});
					var setText = function (id, value) {
						var node = el(id);
						if (node) node.textContent = fmt(value);
					};
					setText("pp-salary-total-qty", totals.qty);
					setText("pp-salary-total-rate", totals.rate);
					setText("pp-salary-total-amount", totals.amount);
					setText("pp-salary-total-advance-balance", totals.advance_balance);
					setText("pp-salary-total-advance-deduction", totals.advance_deduction);
					setText("pp-salary-total-allowance", totals.allowance);
					setText("pp-salary-total-other-deduction", totals.other_deduction);
					setText("pp-salary-total-net", totals.net_amount);
				}

				function onAdjustInput() {
					var emp = input.getAttribute("data-employee") || "";
					var field = input.getAttribute("data-field") || "";
					if (!state.adjustments[emp]) {
						state.adjustments[emp] = {
							advance_balance: 0,
							advance_deduction: 0,
							allowance: 0,
							other_deduction: 0,
						};
					}
					state.adjustments[emp][field] = parseDecimalInput(input.value);
					var rowMap = {};
					getAdjustedEmployeeRows().forEach(function (r) {
						rowMap[r.employee || ""] = r;
					});
					var updated = rowMap[emp];
					wrap.querySelectorAll(".pp-net-cell").forEach(function (cell) {
						if ((cell.getAttribute("data-employee") || "") === emp) {
							cell.textContent = fmt(updated ? updated.net_amount : 0);
						}
					});
					refreshSalaryFooterTotals();
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
			var html =
				"<table class='pp-table'><thead><tr>" +
				"<th>Employee</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Booked</th><th>UnBooked</th><th>Paid</th><th>Unpaid</th><th>Booking Status</th><th>Payment Status</th><th>Action</th>" +
				"</tr></thead><tbody>";
			rows.forEach(function (r) {
				var canBookEmp = num(r.unbooked_amount) > 0;
				var canPayEmp = num(r.unpaid_amount) > 0;
				var empAction = "";
				if (canBookEmp) {
					empAction +=
						"<button type='button' class='btn btn-xs btn-primary pp-go-book-emp' data-employee='" +
						esc(r.employee || "") +
						"'>Book</button> ";
				}
				if (canPayEmp) {
					empAction +=
						"<button type='button' class='btn btn-xs btn-success pp-go-pay-emp' data-employee='" +
						esc(r.employee || "") +
						"'>Pay</button>";
				}
				if (!empAction) empAction = "<span style='color:#64748b;'>Done</span>";
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
					esc(fmt(r.amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.booked_amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.unbooked_amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.paid_amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.unpaid_amount)) +
					"</td>" +
					"<td>" +
					statusBadgeHtml(r.booking_status || "") +
					"</td>" +
					"<td>" +
					statusBadgeHtml(r.payment_status || "") +
					"</td>" +
					"<td>" +
					empAction +
					"</td>" +
					"</tr>";
				if (showDetail && (r.source_entries || []).length) {
					var detailHtml =
						"<table class='pp-table' style='margin:4px 0 0 0;'><thead><tr><th>Per Piece Salary</th><th>From Date</th><th>To Date</th><th>PO Number</th><th>Sales Order</th><th>Qty</th><th>Amount</th><th>Booked</th><th>UnBooked</th><th>Paid</th><th>Unpaid</th><th>Booking</th><th>Payment</th><th>Action</th></tr></thead><tbody>";
					(r.source_entries || []).forEach(function (src) {
						var canBook = num(src.unbooked_amount) > 0;
						var canPay = num(src.unpaid_amount) > 0;
						var entryAction = "";
						if (canBook) {
							entryAction +=
								"<button type='button' class='btn btn-xs btn-primary pp-go-book-entry' data-entry='" +
								encodeURIComponent(String(src.per_piece_salary || "")) +
								"' data-employee='" +
								encodeURIComponent(String(r.employee || "")) +
								"'>Book</button> ";
						}
						if (canPay) {
							entryAction +=
								"<button type='button' class='btn btn-xs btn-success pp-go-pay-entry' data-entry='" +
								encodeURIComponent(String(src.per_piece_salary || "")) +
								"' data-employee='" +
								encodeURIComponent(String(r.employee || "")) +
								"' data-unpaid='" +
								esc(src.unpaid_amount) +
								"'>Pay</button>";
						}
						if (!entryAction) entryAction = "<span style='color:#64748b;'>Done</span>";
						detailHtml +=
							"<tr><td>" +
							esc(src.per_piece_salary || "") +
							"</td><td>" +
							esc(src.from_date || "") +
							"</td><td>" +
							esc(src.to_date || "") +
							"</td><td>" +
							esc(src.po_number || "") +
							"</td><td>" +
							esc(src.sales_order || "") +
							"</td><td class='num'>" +
							esc(fmt(src.qty)) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(src.amount)) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(src.booked_amount)) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(src.unbooked_amount)) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(src.paid_amount)) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(src.unpaid_amount)) +
							"</td><td>" +
							statusBadgeHtml(src.booking_status || "") +
							"</td><td>" +
							statusBadgeHtml(src.payment_status || "") +
							"</td><td>" +
							entryAction +
							"</td></tr>";
					});
					detailHtml +=
						"<tr class='pp-year-total'><td>Total Entries: " +
						esc(r.source_count || 0) +
						"</td><td></td><td></td><td></td><td></td><td class='num'>" +
						esc(fmt(r.qty)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(r.amount)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(r.booked_amount)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(r.unbooked_amount)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(r.paid_amount)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(r.unpaid_amount)) +
						"</td><td></td><td></td><td></td></tr>";
					detailHtml += "</tbody></table>";
					html +=
						"<tr class='pp-entry-detail-row'><td colspan='11'>" +
						detailHtml +
						"</td></tr>";
				}
			});
			var totals = {
				qty: 0,
				rate: 0,
				amount: 0,
				booked_amount: 0,
				unbooked_amount: 0,
				paid_amount: 0,
				unpaid_amount: 0,
			};
			(rows || []).forEach(function (r) {
				totals.qty += num(r.qty);
				totals.rate += num(r.rate);
				totals.amount += num(r.amount);
				totals.booked_amount += num(r.booked_amount);
				totals.unbooked_amount += num(r.unbooked_amount);
				totals.paid_amount += num(r.paid_amount);
				totals.unpaid_amount += num(r.unpaid_amount);
			});
			html +=
				"<tr class='pp-year-total'><td>Total</td><td class='num'>" +
				esc(fmt(totals.qty)) +
				"</td><td class='num'>" +
				esc(fmt(totals.rate)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.amount)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.booked_amount)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.unbooked_amount)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.paid_amount)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.unpaid_amount)) +
				"</td><td></td><td></td><td></td></tr>";
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
					state.paymentAdjustments[emp] = {
						payment_amount: 0,
						unpaid_amount: num(row.unpaid_amount),
					};
				}
				state.paymentAdjustments[emp].unpaid_amount = num(row.unpaid_amount);
				state.paymentAdjustments[emp].payment_amount = Math.min(
					target,
					Math.max(0, num(row.unpaid_amount))
				);
			}

			function focusWorkflow(tabName, employee, entryNo, targetPayAmount) {
				state.forcedEntryNo = entryNo ? String(entryNo).trim() : "";
				if (el("pp-entry-no")) {
					el("pp-entry-no").value = state.forcedEntryNo || "";
				}
				document.querySelectorAll(".pp-tab").forEach(function (x) {
					x.classList.remove("active");
				});
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
					if (el("pp-jv-entry-filter"))
						el("pp-jv-entry-filter").value = state.forcedEntryNo || "";
					if (el("pp-jv-entry-multi"))
						el("pp-jv-entry-multi").value = state.forcedEntryNo || "";
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
					if (el("pp-pay-entry-filter"))
						el("pp-pay-entry-filter").value = state.forcedEntryNo || "";
					if (el("pp-pay-entry-multi"))
						el("pp-pay-entry-multi").value = state.forcedEntryNo || "";
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
					focusWorkflow(
						"salary_creation",
						decodeURIComponent(btn.getAttribute("data-employee") || ""),
						decodeURIComponent(btn.getAttribute("data-entry") || "")
					);
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

		function renderSalarySlipTable(rows) {
			var wrap = el("pp-table-wrap");
			if (!wrap) return;
			var groups = buildSalarySlipGroups(rows);
			if (!groups.length) {
				wrap.innerHTML =
					"<div style='padding:10px;color:#475569;'>No salary slip rows found for current filters.</div>";
				return;
			}
			var html =
				"<table class='pp-table'><thead><tr>" +
				"<th>Employee</th><th>Entries</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Booked</th><th>Paid</th><th>Unpaid</th><th>Booking Status</th><th>Payment Status</th><th>Action</th>" +
				"</tr></thead><tbody>";
			var totals = { entries: 0, qty: 0, rate: 0, amount: 0, booked: 0, paid: 0, unpaid: 0 };
			groups.forEach(function (g) {
				var gBooked = 0,
					gPaid = 0,
					gUnpaid = 0;
				(g.rows || []).forEach(function (r) {
					gBooked += num(r.booked_amount);
					gPaid += num(r.paid_amount);
					gUnpaid += num(r.unpaid_amount);
				});
				var gBookingStatus =
					gBooked > 0
						? gBooked + 0.0001 >= num(g.amount)
							? "Booked"
							: "Partly Booked"
						: "UnBooked";
				var gPaymentStatus =
					gPaid > 0 ? (gUnpaid <= 0.0001 ? "Paid" : "Partly Paid") : "Unpaid";
				var action =
					"<button type='button' class='btn btn-primary btn-xs pp-salary-slip-print' data-mode='detail' data-employee='" +
					encodeURIComponent(String(g.employee || "")) +
					"'>Print Detail Slip</button> " +
					"<button type='button' class='btn btn-primary btn-xs pp-salary-slip-print' data-mode='product' data-employee='" +
					encodeURIComponent(String(g.employee || "")) +
					"'>Print Product Slip</button> " +
					"<button type='button' class='btn btn-primary btn-xs pp-salary-slip-print' data-mode='order' data-employee='" +
					encodeURIComponent(String(g.employee || "")) +
					"'>Salary Slip by Order</button> " +
					"<button type='button' class='btn btn-primary btn-xs pp-salary-slip-entry-prints' data-employee='" +
					encodeURIComponent(String(g.employee || "")) +
					"'>Entry Wise Print</button>";
				html +=
					"<tr>" +
					"<td>" +
					esc(g.name1 || g.employee || "") +
					"</td>" +
					"<td class='num'>" +
					esc(fmt(g.source_count || 0)) +
					"</td>" +
					"<td class='num'>" +
					esc(fmt(g.qty)) +
					"</td>" +
					"<td class='num'>" +
					esc(fmt(g.rate)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(g.amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(gBooked)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(gPaid)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(gUnpaid)) +
					"</td>" +
					"<td>" +
					statusBadgeHtml(gBookingStatus) +
					"</td>" +
					"<td>" +
					statusBadgeHtml(gPaymentStatus) +
					"</td>" +
					"<td>" +
					action +
					"</td>" +
					"</tr>";
				totals.entries += num(g.source_count);
				totals.qty += num(g.qty);
				totals.rate += num(g.rate);
				totals.amount += num(g.amount);
				totals.booked += gBooked;
				totals.paid += gPaid;
				totals.unpaid += gUnpaid;
			});
			html +=
				"<tr class='pp-year-total'><td>Total</td><td class='num'>" +
				esc(fmt(totals.entries)) +
				"</td><td class='num'>" +
				esc(fmt(totals.qty)) +
				"</td><td class='num'>" +
				esc(fmt(totals.rate)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.amount)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.booked)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.paid)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totals.unpaid)) +
				"</td><td></td><td></td><td></td></tr>";
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
					var activeSalaryBtn3 = document.querySelector(
						".pp-tab[data-tab='salary_creation']"
					);
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
					var activePayBtn3 = document.querySelector(
						".pp-tab[data-tab='payment_manage']"
					);
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
						if (!targetRow && String(row.employee || "") === String(onlyEmp || ""))
							targetRow = row;
					});
					if (targetRow && targetPay > 0) {
						if (!state.paymentAdjustments[onlyEmp]) {
							state.paymentAdjustments[onlyEmp] = {
								payment_amount: 0,
								unpaid_amount: num(targetRow.unpaid_amount),
							};
						}
						state.paymentAdjustments[onlyEmp].unpaid_amount = num(
							targetRow.unpaid_amount
						);
						state.paymentAdjustments[onlyEmp].payment_amount = Math.min(
							targetPay,
							Math.max(0, num(targetRow.unpaid_amount))
						);
					}
					setPageForCurrentTab(1);
					loadReport();
				});
			});
		}

		function renderSalarySlipByDCTable(rows) {
			var wrap = el("pp-table-wrap");
			if (!wrap) return;
			var map = {};
			(rows || []).forEach(function (r) {
				var entryNo = String(r.per_piece_salary || "").trim();
				if (!entryNo) return;
				var dcNo = String(r.delivery_note || "").trim();
				var empId = String(r.employee || "").trim();
				var empName = String(r.name1 || "").trim() || empId;
				var key = entryNo + "||" + dcNo + "||" + empId;
				if (!map[key]) {
					map[key] = {
						entry_no: entryNo,
						delivery_note: dcNo,
						employee: empId,
						employee_name: empName,
						from_date: r.from_date || "",
						to_date: r.to_date || "",
						net_salary: 0,
						row_count: 0,
					};
				}
				var rowFrom = String(r.from_date || "").trim();
				var rowTo = String(r.to_date || "").trim();
				if (rowFrom && (!map[key].from_date || rowFrom < map[key].from_date))
					map[key].from_date = rowFrom;
				if (rowTo && (!map[key].to_date || rowTo > map[key].to_date))
					map[key].to_date = rowTo;
				var amount = num(r.amount);
				var adv = num(r.advance_deduction);
				var allow = num(r.allowance);
				var other = num(r.other_deduction);
				var net = num(r.net_amount);
				if (!net) net = Math.max(amount - adv + allow - other, 0);
				map[key].net_salary += net;
				map[key].row_count += 1;
			});
			var entries = Object.keys(map)
				.map(function (k) {
					return map[k];
				})
				.sort(function (a, b) {
					var ea = String(a.entry_no || "");
					var eb = String(b.entry_no || "");
					if (ea !== eb) return eb.localeCompare(ea);
					var da = String(a.delivery_note || "");
					var db = String(b.delivery_note || "");
					if (da !== db) return db.localeCompare(da);
					return String(a.employee_name || "").localeCompare(
						String(b.employee_name || "")
					);
				});
			if (!entries.length) {
				wrap.innerHTML =
					"<div style='padding:10px;color:#475569;'>No Salary Slip by DC rows found for current filters.</div>";
				return;
			}
			var html =
				"<table class='pp-table'><thead><tr>" +
				"<th>From Date</th><th>To Date</th><th>DC No.</th><th>Entry No</th><th>Employee</th><th>Net Salary</th><th>Print</th>" +
				"</tr></thead><tbody>";
			var totalNet = 0;
			entries.forEach(function (r) {
				totalNet += num(r.net_salary);
				html +=
					"<tr><td>" +
					esc(r.from_date || "") +
					"</td><td>" +
					esc(r.to_date || "") +
					"</td><td>" +
					esc(r.delivery_note || "") +
					"</td><td>" +
					esc(r.entry_no || "") +
					"</td><td>" +
					esc(r.employee_name || r.employee || "") +
					"</td><td class='num pp-amt-col'>" +
					esc(fmt(r.net_salary)) +
					"</td><td><button type='button' class='btn btn-primary btn-xs pp-salary-slip-dc-print' data-entry='" +
					encodeURIComponent(String(r.entry_no || "")) +
					"' data-dc='" +
					encodeURIComponent(String(r.delivery_note || "")) +
					"' data-employee='" +
					encodeURIComponent(String(r.employee || "")) +
					"'>Print</button></td></tr>";
			});
			html +=
				"<tr class='pp-year-total'><td colspan='5'>Total</td><td class='num pp-amt-col'>" +
				esc(fmt(totalNet)) +
				"</td><td></td></tr>";
			html += "</tbody></table>";
			wrap.innerHTML = html;
			wrap.querySelectorAll(".pp-salary-slip-dc-print").forEach(function (btn) {
				btn.addEventListener("click", function () {
					var entryNo = decodeURIComponent(btn.getAttribute("data-entry") || "");
					var dcNo = decodeURIComponent(btn.getAttribute("data-dc") || "");
					var employee = decodeURIComponent(btn.getAttribute("data-employee") || "");
					showSalarySlipByEntry(entryNo, dcNo, employee);
				});
			});
		}

		function renderPaymentTable(rows) {
			var wrap = el("pp-table-wrap");
			if (!wrap) return;
			var html =
				"<table class='pp-table'><thead><tr>" +
				"<th>Use In Payment</th><th>Employee</th><th>Net Salary</th><th>Paid Amount</th><th>Unpaid Amount</th><th>Payment Amount</th><th>Status</th>" +
				"</tr></thead><tbody>";
			rows.forEach(function (r) {
				var emp = r.employee || "";
				var checked = state.paymentExcludedEmployees[emp] ? "" : " checked";
				html +=
					"<tr>" +
					"<td><input class='pp-pay-include' type='checkbox' data-employee='" +
					esc(emp) +
					"'" +
					checked +
					"></td>" +
					"<td>" +
					esc(employeeLabel(r) || emp || "(Blank)") +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.booked_amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.paid_amount)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(r.unpaid_amount)) +
					"</td>" +
					"<td><input class='pp-pay-amount pp-pay-input' type='number' min='0' step='0.01' inputmode='decimal' data-employee='" +
					esc(emp) +
					"' value='" +
					esc(whole(r.payment_amount)) +
					"'></td>" +
					"<td>" +
					statusBadgeHtml(r.payment_status || "") +
					"</td>" +
					"</tr>";
			});
			var tBooked = 0,
				tPaid = 0,
				tUnpaid = 0,
				tPay = 0;
			rows.forEach(function (r) {
				tBooked += num(r.booked_amount);
				tPaid += num(r.paid_amount);
				tUnpaid += num(r.unpaid_amount);
				tPay += num(r.payment_amount);
			});
			html +=
				"<tr class='pp-year-total'>" +
				"<td></td>" +
				"<td>Total</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(tBooked)) +
				"</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(tPaid)) +
				"</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(tUnpaid)) +
				"</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(tPay)) +
				"</td>" +
				"<td></td>" +
				"</tr>";
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
					if (!state.paymentAdjustments[emp])
						state.paymentAdjustments[emp] = { payment_amount: 0, unpaid_amount: 0 };
					state.paymentAdjustments[emp].payment_amount = amount;
					var totals = getPaymentTotals();
					el("pp-totals").innerHTML =
						"<span>Booked: " +
						fmt(totals.booked) +
						"</span>" +
						"<span>Paid: " +
						fmt(totals.paid) +
						"</span>" +
						"<span>Unpaid: " +
						fmt(totals.unpaid) +
						"</span>" +
						"<span>Payment This JV: " +
						fmt(totals.payment) +
						"</span>";
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

		return {
			renderTable: renderTable,
			renderPoDetailPrintTab: renderPoDetailPrintTab,
			renderSalaryTable: renderSalaryTable,
			renderEmployeeSummaryTable: renderEmployeeSummaryTable,
			renderSalarySlipTable: renderSalarySlipTable,
			renderSalarySlipByDCTable: renderSalarySlipByDCTable,
			renderPaymentTable: renderPaymentTable,
			setJVAmounts: setJVAmounts,
			refreshJVAmountsFromAdjustments: refreshJVAmountsFromAdjustments,
			setPaymentAmounts: setPaymentAmounts,
			refreshPaymentAmounts: refreshPaymentAmounts,
		};
	}

	window.PerPieceViews = { create: create };
})();
