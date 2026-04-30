(function () {
	function create(deps) {
		var state = deps.state;
		var el = deps.el;
		var esc = deps.esc;
		var num = deps.num;
		var whole = deps.whole;
		var avgRate = deps.avgRate;
		var statusBadgeHtml = deps.statusBadgeHtml;
		var entrySequenceNo = deps.entrySequenceNo;
		var compareEntryNoDesc = deps.compareEntryNoDesc;
		var getRowsByHeaderFilters = deps.getRowsByHeaderFilters;
		var filterRowsByDateRange = deps.filterRowsByDateRange;
		var getWorkflowHistoryRange = deps.getWorkflowHistoryRange;
		var setOptions = deps.setOptions;
		var buildEmployeeSummaryRows = deps.buildEmployeeSummaryRows;
		var getBookedAmountForPaymentRow =
			deps.getBookedAmountForPaymentRow ||
			function (r) {
				return num((r && r.booked_amount) || (r && r.amount));
			};

		function getUnpostedRows() {
			var range = getWorkflowHistoryRange("salary_creation");
			return filterRowsBySelectedEntries(
				filterRowsByDateRange(
					getRowsByHeaderFilters(state.rows || [], { ignore_date_filter: true }),
					range.from,
					range.to
				),
				"salary_creation"
			).filter(function (r) {
				var status = r && r.jv_status ? String(r.jv_status) : "Pending";
				var hasJV = !!String((r && r.jv_entry_no) || "").trim();
				return !hasJV && status !== "Posted";
			});
		}

		function getBookedRows() {
			var selected = getSelectedEntryNosForTab("payment_manage");
			var baseRows = [];
			if (selected.length) {
				// Payment must follow selected salary entry number(s) exactly,
				// without accidental header/date filters clipping rows.
				baseRows = filterRowsBySelectedEntries(state.rows || [], "payment_manage");
			} else {
				var range = getWorkflowHistoryRange("payment_manage");
				baseRows = filterRowsBySelectedEntries(
					filterRowsByDateRange(
						getRowsByHeaderFilters(state.rows || [], { ignore_date_filter: true }),
						range.from,
						range.to
					),
					"payment_manage"
				);
			}
			return baseRows.filter(function (r) {
				var status = String((r && r.jv_status) || "");
				var hasJV = !!String((r && r.jv_entry_no) || "").trim();
				var booking = String((r && r.booking_status) || "");
				var booked = num((r && r.booked_amount) || 0);
				return (hasJV && status === "Posted") || booking === "Booked" || booked > 0.0001;
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
						payment_status: "Unpaid",
					};
				}
				var booked = Math.max(num(getBookedAmountForPaymentRow(r)), 0);
				map[emp].booked_amount += booked;
				var paid = Math.max(num(r.paid_amount), 0);
				map[emp].paid_amount += paid;
			});
			return Object.keys(map)
				.sort()
				.map(function (k) {
					var row = map[k];
					if (row.paid_amount > row.booked_amount) row.paid_amount = row.booked_amount;
					row.unpaid_amount = Math.max(row.booked_amount - row.paid_amount, 0);
					if (row.unpaid_amount <= 0 && row.booked_amount > 0)
						row.payment_status = "Paid";
					else if (row.paid_amount > 0 && row.unpaid_amount > 0)
						row.payment_status = "Partly Paid";
					else row.payment_status = "Unpaid";
					return row;
				});
		}

		function normalizePaymentAdjustments() {
			var next = {};
			var selected = getSelectedEntryNosForTab("payment_manage");
			var basisRows = null;
			if (
				selected.length === 1 &&
				state.paymentEntryBasis &&
				String(state.paymentEntryBasis.entry_no || "").trim() ===
					String(selected[0] || "").trim() &&
				Array.isArray(state.paymentEntryBasis.rows)
			) {
				basisRows = state.paymentEntryBasis.rows.map(function (r) {
					return {
						employee: String((r && r.employee) || ""),
						unpaid_amount: num((r && r.unpaid_amount) || 0),
					};
				});
			}
			(basisRows || buildPaymentEmployeeRows(getBookedRows())).forEach(function (r) {
				var key = r.employee || "";
				var amount = whole(r.unpaid_amount);
				next[key] = { payment_amount: amount, unpaid_amount: num(r.unpaid_amount) };
			});
			state.paymentAdjustments = next;
		}

		function normalizePaymentExcludedEmployees() {
			var next = {};
			var selected = getSelectedEntryNosForTab("payment_manage");
			var basisRows = null;
			if (
				selected.length === 1 &&
				state.paymentEntryBasis &&
				String(state.paymentEntryBasis.entry_no || "").trim() ===
					String(selected[0] || "").trim() &&
				Array.isArray(state.paymentEntryBasis.rows)
			) {
				basisRows = state.paymentEntryBasis.rows.map(function (r) {
					return { employee: String((r && r.employee) || "") };
				});
			}
			(basisRows || buildPaymentEmployeeRows(getBookedRows())).forEach(function (r) {
				var key = r.employee || "";
				if (state.paymentExcludedEmployees[key]) next[key] = true;
			});
			state.paymentExcludedEmployees = next;
		}

		function getPaymentRows() {
			var selected = getSelectedEntryNosForTab("payment_manage");
			var basis = state.paymentEntryBasis || null;
			if (
				selected.length === 1 &&
				basis &&
				String(basis.entry_no || "").trim() === String(selected[0] || "").trim() &&
				Array.isArray(basis.rows) &&
				basis.rows.length
			) {
				return basis.rows
					.map(function (r) {
						var emp = String((r && r.employee) || "");
						var booked = num((r && r.booked_amount) || 0);
						var paid = num((r && r.paid_amount) || 0);
						var unpaid = num((r && r.unpaid_amount) || 0);
						var key = emp || "";
						var adj = state.paymentAdjustments[key] || {};
						var pay = whole(adj.payment_amount);
						if (pay > unpaid) pay = whole(unpaid);
						return {
							employee: emp,
							name1: (r && r.name1) || "",
							booked_amount: booked,
							paid_amount: paid,
							unpaid_amount: unpaid,
							payment_status: String((r && r.payment_status) || "Unpaid"),
							payment_amount: pay,
						};
					})
					.filter(isPaymentOpenRow);
			}

			return buildPaymentEmployeeRows(getBookedRows())
				.map(function (r) {
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
						payment_amount: pay,
					};
				})
				.filter(isPaymentOpenRow);
		}

		function isPaymentOpenRow(r) {
			var unpaid = num(r && r.unpaid_amount);
			var paid = num(r && r.paid_amount);
			var booked = num(r && r.booked_amount);
			var rawStatus = String((r && r.payment_status) || "Unpaid");
			var status = rawStatus.trim().toLowerCase();
			var isPaidByStatus = status === "paid";
			var isFullyPaidByAmount = booked > 0.0001 && Math.max(booked - paid, 0) <= 0.005;
			if (unpaid <= 0.005 && (isPaidByStatus || isFullyPaidByAmount)) return false;
			return unpaid > 0.005 || status === "unpaid" || status === "partly paid";
		}

		function getPaymentActiveRows() {
			return getPaymentRows().filter(isPaymentOpenRow);
		}

		function getPaymentPostingRows() {
			return getPaymentRows().filter(function (r) {
				return (
					isPaymentOpenRow(r) &&
					!state.paymentExcludedEmployees[r.employee || ""] &&
					num(r.payment_amount) > 0
				);
			});
		}

		function getUnbookedEntryOptions() {
			var map = {};
			var range = getWorkflowHistoryRange("salary_creation");
			filterRowsByDateRange(
				getRowsByHeaderFilters(state.rows || [], {
					ignore_entry_filter: true,
					ignore_date_filter: true,
				}),
				range.from,
				range.to
			).forEach(function (r) {
				var entry = String((r && r.per_piece_salary) || "").trim();
				if (!entry) return;
				var status = String((r && r.jv_status) || "");
				var hasJV = !!String((r && r.jv_entry_no) || "").trim();
				if (!hasJV || status !== "Posted") map[entry] = 1;
			});
			return Object.keys(map)
				.sort(compareEntryNoDesc)
				.map(function (name) {
					return { value: name, label: name };
				});
		}

		function getUnpaidEntryOptions() {
			var map = {};
			var range = getWorkflowHistoryRange("payment_manage");
			filterRowsByDateRange(
				getRowsByHeaderFilters(state.rows || [], {
					ignore_entry_filter: true,
					ignore_date_filter: true,
				}),
				range.from,
				range.to
			).forEach(function (r) {
				var entry = String((r && r.per_piece_salary) || "").trim();
				if (!entry) return;
				var unpaid = num((r && r.unpaid_amount) || 0);
				var payStatus = String((r && r.payment_status) || "Unpaid");
				var hasBooked =
					num((r && r.booked_amount) || 0) > 0.0001 ||
					String((r && r.booking_status) || "") === "Booked" ||
					(!!String((r && r.jv_entry_no) || "").trim() &&
						String((r && r.jv_status) || "") === "Posted");
				if (
					hasBooked &&
					(unpaid > 0.0001 || payStatus === "Unpaid" || payStatus === "Partly Paid")
				)
					map[entry] = 1;
			});
			return Object.keys(map)
				.sort(compareEntryNoDesc)
				.map(function (name) {
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
			var rowCount = 0,
				bookedCount = 0,
				paidCount = 0,
				unpaidCount = 0;
			var amount = 0,
				booked = 0,
				paid = 0,
				unpaid = 0,
				unbooked = 0;
			var fromDate = "",
				toDate = "";
			src.forEach(function (r) {
				rowCount += 1;
				var a = num(r.amount);
				var isBooked =
					String(r.booking_status || "") === "Booked" ||
					(!!String(r.jv_entry_no || "").trim() &&
						String(r.jv_status || "") === "Posted");
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
			var bookingStatus =
				bookedCount === rowCount
					? "Booked"
					: bookedCount > 0
					? "Partly Booked"
					: "UnBooked";
			var paymentStatus =
				booked <= 0
					? "Unpaid"
					: unpaid <= 0.005
					? "Paid"
					: paid > 0.005
					? "Partly Paid"
					: "Unpaid";
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
				payment_status: paymentStatus,
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
				if (
					currentForced &&
					rows.some(function (r) {
						return r.value === currentForced;
					})
				)
					jvSelect.value = currentForced;
				else if (
					current &&
					rows.some(function (r) {
						return r.value === current;
					})
				)
					jvSelect.value = current;
			}
			if (paySelect) {
				var rows2 = getUnpaidEntryOptions();
				var current2 = String(paySelect.value || "");
				setOptions(paySelect, rows2, "value", "label", "All Unpaid Entries");
				if (
					currentForced &&
					rows2.some(function (r) {
						return r.value === currentForced;
					})
				)
					paySelect.value = currentForced;
				else if (
					current2 &&
					rows2.some(function (r) {
						return r.value === current2;
					})
				)
					paySelect.value = current2;
			}
			var jvMeta = el("pp-jv-entry-meta");
			var jvEntry = jvSelect ? String(jvSelect.value || "").trim() : "";
			if (jvMeta) {
				if (!jvEntry)
					jvMeta.innerHTML =
						"Booking Status: " +
						statusBadgeHtml("All") +
						" | Payment Status: " +
						statusBadgeHtml("All");
				else {
					var s = getEntrySummary(jvEntry);
					if (!s) jvMeta.textContent = "";
					else
						jvMeta.innerHTML =
							"Entry: " +
							esc(jvEntry) +
							" | Date: " +
							esc((s.from_date || "-") + " to " + (s.to_date || "-")) +
							" | Booking: " +
							statusBadgeHtml(s.booking_status || "") +
							" | Payment: " +
							statusBadgeHtml(s.payment_status || "");
				}
			}
			var payMeta = el("pp-pay-entry-meta");
			var payEntry = paySelect ? String(paySelect.value || "").trim() : "";
			if (payMeta) {
				if (!payEntry)
					payMeta.innerHTML =
						"Booking Status: " +
						statusBadgeHtml("All") +
						" | Payment Status: " +
						statusBadgeHtml("All");
				else {
					var ps = getEntrySummary(payEntry);
					if (!ps) payMeta.textContent = "";
					else
						payMeta.innerHTML =
							"Entry: " +
							esc(payEntry) +
							" | Date: " +
							esc((ps.from_date || "-") + " to " + (ps.to_date || "-")) +
							" | Booking: " +
							statusBadgeHtml(ps.booking_status || "") +
							" | Payment: " +
							statusBadgeHtml(ps.payment_status || "");
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
			String(text || "")
				.split(",")
				.forEach(function (part) {
					var v = String(part || "").trim();
					if (!v || seen[v]) return;
					seen[v] = 1;
					out.push(v);
				});
			return out;
		}

		function getSelectedEntryNosForTab(tabName) {
			var raw = "";
			var single = "";
			if (tabName === "salary_creation")
				raw = (el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || "";
			else if (tabName === "payment_manage")
				raw = (el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || "";
			if (tabName === "salary_creation")
				single = (el("pp-jv-entry-filter") && el("pp-jv-entry-filter").value) || "";
			else if (tabName === "payment_manage")
				single = (el("pp-pay-entry-filter") && el("pp-pay-entry-filter").value) || "";
			var list = parseEntryNoList(raw);
			var forced = String(state.forcedEntryNo || "").trim();
			if (forced) {
				// Explicit row action (Pay/Book) must win over any stale selector values.
				return [forced];
			}
			// Single selector must win to avoid stale multi-entry list mixing entries.
			if (String(single || "").trim()) {
				list = [String(single || "").trim()];
			}
			return list;
		}

		function filterRowsBySelectedEntries(rows, tabName) {
			var list = getSelectedEntryNosForTab(tabName);
			if (!list.length) return (rows || []).slice();
			var set = {};
			list.forEach(function (name) {
				set[String(name || "").trim()] = 1;
			});
			return (rows || []).filter(function (r) {
				var entry = String((r && r.per_piece_salary) || "").trim();
				return !!set[entry];
			});
		}

		function getPaymentTotals() {
			var totals = { booked: 0, paid: 0, unpaid: 0, payment: 0, debit: 0, credit: 0 };
			getPaymentRows().forEach(function (r) {
				if (!state.paymentExcludedEmployees[r.employee || ""]) {
					totals.booked += num(r.booked_amount);
					totals.paid += num(r.paid_amount);
					totals.unpaid += num(r.unpaid_amount);
				}
			});
			getPaymentPostingRows().forEach(function (r) {
				totals.payment += num(r.payment_amount);
			});
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
					other_deduction: whole(old.other_deduction),
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
			if (otherDeduction > gross - advanceDeduction)
				otherDeduction = gross - advanceDeduction;
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
				net_amount: netAmount,
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
				credit_amount: 0,
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

		return {
			getUnpostedRows: getUnpostedRows,
			getBookedRows: getBookedRows,
			buildPaymentEmployeeRows: buildPaymentEmployeeRows,
			normalizePaymentAdjustments: normalizePaymentAdjustments,
			normalizePaymentExcludedEmployees: normalizePaymentExcludedEmployees,
			getPaymentRows: getPaymentRows,
			isPaymentOpenRow: isPaymentOpenRow,
			getPaymentActiveRows: getPaymentActiveRows,
			getPaymentPostingRows: getPaymentPostingRows,
			getUnbookedEntryOptions: getUnbookedEntryOptions,
			getUnpaidEntryOptions: getUnpaidEntryOptions,
			getEntrySummary: getEntrySummary,
			refreshWorkflowEntrySelectors: refreshWorkflowEntrySelectors,
			resetEntryFiltersToAll: resetEntryFiltersToAll,
			parseEntryNoList: parseEntryNoList,
			getSelectedEntryNosForTab: getSelectedEntryNosForTab,
			filterRowsBySelectedEntries: filterRowsBySelectedEntries,
			getPaymentTotals: getPaymentTotals,
			normalizeAdjustmentsForEmployees: normalizeAdjustmentsForEmployees,
			normalizeExcludedEmployees: normalizeExcludedEmployees,
			withAdjustments: withAdjustments,
			getAdjustedEmployeeRows: getAdjustedEmployeeRows,
			getPostingEmployeeRows: getPostingEmployeeRows,
			getAdjustedTotals: getAdjustedTotals,
		};
	}

	window.PerPieceState = { create: create };
})();
