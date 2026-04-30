(function () {
	function create(deps) {
		var state = deps.state;
		var el = deps.el;
		var num = deps.num;
		var whole = deps.whole;
		var fmt = deps.fmt;
		var esc = deps.esc;
		var callApi = deps.callApi;
		var callGetList = deps.callGetList;
		var setOptions = deps.setOptions;
		var getReportArgs = deps.getReportArgs;
		var getWorkflowHistoryRange = deps.getWorkflowHistoryRange;
		var parseEntryNoList = deps.parseEntryNoList;
		var getPaymentRows = deps.getPaymentRows;
		var getPaymentPostingRows = deps.getPaymentPostingRows;
		var getAdjustedEmployeeRows = deps.getAdjustedEmployeeRows;
		var setJVAmounts = deps.setJVAmounts;
		var setPaymentAmounts = deps.setPaymentAmounts;
		var confirmActionModal = deps.confirmActionModal;
		var notifyActionResult = deps.notifyActionResult;
		var renderJournalEntryInline = deps.renderJournalEntryInline;
		var showJournalEntrySummary = deps.showJournalEntrySummary;
		var showResult = deps.showResult;
		var prettyError = deps.prettyError;
		var errText = deps.errText;
		var resetEntryFiltersToAll = deps.resetEntryFiltersToAll;
		var loadReport = deps.loadReport;

		function loadJVEntryOptions() {
			var select = el("pp-jv-existing");
			if (!select) return;
			var posted = {};
			(state.rows || []).forEach(function (r) {
				if (r && r.jv_entry_no && r.jv_status === "Posted") {
					posted[r.jv_entry_no] = true;
				}
			});
			var options = Object.keys(posted)
				.sort()
				.reverse()
				.map(function (name) {
					return { name: name };
				});
			setOptions(select, options, "name", "name", "Select Posted JV");
			// Keep placeholder by default; user explicitly picks JV to view/cancel.
			select.value = "";
		}

		function loadPaymentJVEntryOptions() {
			var select = el("pp-pay-existing");
			if (!select) return;
			var posted = {};
			(state.rows || []).forEach(function (r) {
				if (r && r.payment_jv_no) posted[r.payment_jv_no] = true;
			});
			var options = Object.keys(posted)
				.sort()
				.reverse()
				.map(function (name) {
					return { name: name };
				});
			setOptions(select, options, "name", "name", "Select Payment JV");
			// Keep placeholder by default; user explicitly picks Payment JV.
			select.value = "";
		}

		function selectPreferred(selectEl, rows, preferredKeywords) {
			if (!selectEl || !rows || !rows.length) return;
			var current = selectEl.value || "";
			if (
				current &&
				rows.some(function (r) {
					return r.name === current;
				})
			) {
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
			selectPreferred(selectEl, rows, [
				"payroll payable",
				"salary payable",
				"payable",
				"salary",
				"employee",
			]);
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
				setOptions(
					el("pp-jv-expense-account"),
					[],
					"name",
					"name",
					"Select Salary Account"
				);
				setOptions(
					el("pp-jv-allowance-account"),
					[],
					"name",
					"name",
					"Select Allowance Account"
				);
				setOptions(
					el("pp-jv-payable-account"),
					[],
					"name",
					"name",
					"Select Payable Account"
				);
				setOptions(
					el("pp-jv-advance-account"),
					[],
					"name",
					"name",
					"Select Advance Account"
				);
				setOptions(
					el("pp-jv-deduction-account"),
					[],
					"name",
					"name",
					"Select Deduction Account"
				);
				return;
			}
			callGetList("Account", ["name"], {
				company: company,
				is_group: 0,
				root_type: "Expense",
			})
				.then(function (rows) {
					rows = rows || [];
					setOptions(
						el("pp-jv-expense-account"),
						rows,
						"name",
						"name",
						"Select Salary Account"
					);
					selectPreferred(el("pp-jv-expense-account"), rows, [
						"salary",
						"wages",
						"expense",
						"allowance",
					]);
					setOptions(
						el("pp-jv-allowance-account"),
						rows,
						"name",
						"name",
						"Select Allowance Account"
					);
					selectPreferred(el("pp-jv-allowance-account"), rows, [
						"allowance",
						"salary",
						"expense",
					]);
				})
				.catch(function (e) {
					console.error(e);
				});
			callGetList("Account", ["name"], {
				company: company,
				is_group: 0,
				account_type: "Payable",
			})
				.then(function (rows) {
					rows = rows || [];
					setOptions(
						el("pp-jv-payable-account"),
						rows,
						"name",
						"name",
						"Select Payable Account"
					);
					selectPreferredPayable(el("pp-jv-payable-account"), rows);
				})
				.catch(function (e) {
					console.error(e);
				});
			callGetList("Account", ["name"], { company: company, is_group: 0, root_type: "Asset" })
				.then(function (rows) {
					rows = rows || [];
					setOptions(
						el("pp-jv-advance-account"),
						rows,
						"name",
						"name",
						"Select Advance Account"
					);
					selectPreferred(el("pp-jv-advance-account"), rows, [
						"employee advance",
						"advance",
						"employee",
						"receivable",
					]);
				})
				.catch(function (e) {
					console.error(e);
				});
			Promise.all([
				callGetList("Account", ["name"], {
					company: company,
					is_group: 0,
					root_type: "Liability",
				}),
				callGetList("Account", ["name"], {
					company: company,
					is_group: 0,
					root_type: "Expense",
				}),
			])
				.then(function (parts) {
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
					merged.sort(function (a, b) {
						return String(a.name || "").localeCompare(String(b.name || ""));
					});
					setOptions(
						el("pp-jv-deduction-account"),
						merged,
						"name",
						"name",
						"Select Deduction Account"
					);
					selectPreferred(el("pp-jv-deduction-account"), merged, [
						"salary",
						"wages",
						"expense",
						"deduction",
						"eobi",
						"payable",
						"allowance",
						"employee",
					]);
				})
				.catch(function (e) {
					console.error(e);
				});
		}

		function loadPaymentAccountsForCompany() {
			var company = el("pp-pay-company").value || "";
			if (!company) {
				setOptions(
					el("pp-pay-payable-account"),
					[],
					"name",
					"name",
					"Select Payable Account"
				);
				setOptions(
					el("pp-pay-paid-from-account"),
					[],
					"name",
					"name",
					"Select Bank/Cash Account"
				);
				return;
			}
			callGetList("Account", ["name"], {
				company: company,
				is_group: 0,
				account_type: "Payable",
			})
				.then(function (rows) {
					rows = rows || [];
					setOptions(
						el("pp-pay-payable-account"),
						rows,
						"name",
						"name",
						"Select Payable Account"
					);
					var salaryPayable = el("pp-jv-payable-account").value || "";
					if (
						salaryPayable &&
						rows.some(function (r) {
							return r.name === salaryPayable;
						})
					) {
						el("pp-pay-payable-account").value = salaryPayable;
					} else {
						selectPreferredPayable(el("pp-pay-payable-account"), rows);
					}
				})
				.catch(function (e) {
					console.error(e);
				});
			Promise.all([
				callGetList("Account", ["name"], {
					company: company,
					is_group: 0,
					account_type: "Bank",
				}),
				callGetList("Account", ["name"], {
					company: company,
					is_group: 0,
					account_type: "Cash",
				}),
			])
				.then(function (parts) {
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
					merged.sort(function (a, b) {
						return String(a.name || "").localeCompare(String(b.name || ""));
					});
					setOptions(
						el("pp-pay-paid-from-account"),
						merged,
						"name",
						"name",
						"Select Bank/Cash Account"
					);
					selectPreferred(el("pp-pay-paid-from-account"), merged, ["cash", "bank"]);
				})
				.catch(function (e) {
					console.error(e);
				});
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
			Object.keys(state.adjustments || {})
				.sort()
				.forEach(function (emp) {
					var a = state.adjustments[emp] || {};
					var ar = adjustedMap[emp] || {};
					lines.push(
						[
							String(emp || "").trim(),
							whole(a.allowance),
							whole(a.advance_deduction),
							whole(a.other_deduction),
							whole(ar.advance_balance || a.advance_balance || 0),
						].join("::")
					);
				});
			args.employee_adjustments = lines.join(";;");
			args.exclude_employees = Object.keys(state.excludedEmployees || {})
				.filter(function (k) {
					return !!state.excludedEmployees[k];
				})
				.join(",");
			args.employee_wise = 1;
			var selectedEntries = parseEntryNoList(
				(el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || ""
			);
			var singleJVEntry = (el("pp-jv-entry-filter") && el("pp-jv-entry-filter").value) || "";
			if (String(singleJVEntry || "").trim()) {
				selectedEntries = [String(singleJVEntry || "").trim()];
			}
			if (args.entry_no && selectedEntries.indexOf(String(args.entry_no)) < 0)
				selectedEntries.unshift(String(args.entry_no));
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
			var selectedEntries = parseEntryNoList(
				(el("pp-pay-entry-multi") && el("pp-pay-entry-multi").value) || ""
			);
			var singlePayEntry =
				(el("pp-pay-entry-filter") && el("pp-pay-entry-filter").value) || "";
			if (String(singlePayEntry || "").trim()) {
				selectedEntries = [String(singlePayEntry || "").trim()];
			}
			if (args.entry_no && selectedEntries.indexOf(String(args.entry_no)) < 0)
				selectedEntries.unshift(String(args.entry_no));
			args.entry_nos = selectedEntries.join(",");
			args.dry_run = dryRun ? 1 : 0;
			return args;
		}

		function previewJV() {
			var result = el("pp-jv-result");
			result.style.color = "#334155";
			result.textContent = "Generating preview...";
			callApi("per_piece_payroll.api.create_per_piece_salary_jv", getJVArgs(true))
				.then(function (msg) {
					setJVAmounts(msg.net_payable_amount, msg.net_payable_amount, msg.gross_amount);
					var html =
						"<strong>Preview</strong><br>" +
						"Rows: " +
						esc(msg.rows) +
						" | Qty: " +
						esc(msg.total_qty) +
						" | Base: " +
						esc(fmt(msg.base_amount)) +
						" | Allowance: " +
						esc(fmt(msg.allowance_amount)) +
						" | Gross: " +
						esc(fmt(msg.gross_amount)) +
						" | Advance Deduction: " +
						esc(fmt(msg.advance_deduction_amount)) +
						" | Other Deduction: " +
						esc(fmt(msg.other_deduction_amount)) +
						" | Net Payable: " +
						esc(fmt(msg.net_payable_amount));
					if (msg.employee_summary && msg.employee_summary.length) {
						html +=
							"<br><br><table class='pp-table'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Base</th><th>Allowance</th><th>Advance Balance</th><th>Advance Deduction</th><th>Other Deduction</th><th>Net</th><th>Remarks</th></tr></thead><tbody>";
						msg.employee_summary.forEach(function (r) {
							html +=
								"<tr><td>" +
								esc(r.name1 || r.employee || "") +
								"</td><td class='num'>" +
								esc(fmt(r.qty)) +
								"</td><td class='num'>" +
								esc(fmt(r.rate)) +
								"</td><td class='num'>" +
								esc(fmt(r.amount)) +
								"</td><td class='num'>" +
								esc(fmt(r.allowance)) +
								"</td><td class='num'>" +
								esc(fmt(r.advance_balance)) +
								"</td><td class='num'>" +
								esc(fmt(r.advance_deduction)) +
								"</td><td class='num'>" +
								esc(fmt(r.other_deduction)) +
								"</td><td class='num'>" +
								esc(fmt(r.net_amount)) +
								"</td><td>" +
								esc(r.remarks || "") +
								"</td></tr>";
						});
						html += "</tbody></table>";
					}
					result.style.color = "#0f766e";
					result.innerHTML = html;
				})
				.catch(function (e) {
					showResult(result, "error", "Preview Not Available", prettyError(errText(e)));
					console.error(e);
				});
		}

		function previewPaymentJV() {
			var result = el("pp-pay-result");
			if (!getPaymentPostingRows().length) {
				showResult(
					result,
					"error",
					"Nothing To Preview",
					"Only employees with Unpaid or Partly Paid status are shown here. Set payment amount greater than 0."
				);
				return;
			}
			result.style.color = "#334155";
			result.textContent = "Generating payment preview...";
			callApi(
				"per_piece_payroll.api.create_per_piece_salary_payment_jv",
				getPaymentJVArgs(true)
			)
				.then(function (msg) {
					setPaymentAmounts(msg.debit_amount, msg.credit_amount, msg.unpaid_amount);
					var html =
						"<strong>Payment Preview</strong><br>" +
						"Booked: " +
						esc(fmt(msg.booked_amount)) +
						" | Paid: " +
						esc(fmt(msg.paid_amount)) +
						" | Unpaid: " +
						esc(fmt(msg.unpaid_amount)) +
						" | Requested: " +
						esc(fmt(msg.requested_amount)) +
						" | This JV: " +
						esc(fmt(msg.payment_amount));
					var previewRows = (msg.employee_summary || []).filter(function (r) {
						return num(r.unpaid_amount) > 0 || num(r.to_pay_amount) > 0;
					});
					if (previewRows.length) {
						html +=
							"<br><br><table class='pp-table'><thead><tr><th>Employee</th><th>Booked</th><th>Paid</th><th>Unpaid</th><th>Requested</th><th>To Pay</th></tr></thead><tbody>";
						previewRows.forEach(function (r) {
							html +=
								"<tr><td>" +
								esc(r.name1 || r.employee || "") +
								"</td><td class='num'>" +
								esc(fmt(r.booked_amount)) +
								"</td><td class='num'>" +
								esc(fmt(r.paid_amount)) +
								"</td><td class='num'>" +
								esc(fmt(r.unpaid_amount)) +
								"</td><td class='num'>" +
								esc(fmt(r.requested_amount)) +
								"</td><td class='num'>" +
								esc(fmt(r.to_pay_amount)) +
								"</td></tr>";
						});
						html += "</tbody></table>";
					}
					result.style.color = "#0f766e";
					result.innerHTML = html;
				})
				.catch(function (e) {
					showResult(
						result,
						"error",
						"Payment Preview Not Available",
						prettyError(errText(e))
					);
					console.error(e);
				});
		}

		function createPaymentJV() {
			if (!getPaymentPostingRows().length) {
				showResult(
					el("pp-pay-result"),
					"error",
					"Nothing To Post",
					"No unpaid or partly paid employee amount selected for payment JV."
				);
				return;
			}
			confirmActionModal(
				"Post Payment JV",
				"Post Payment JV for selected employee amounts?",
				"Post JV"
			).then(function (ok) {
				if (!ok) return;
				var result = el("pp-pay-result");
				result.style.color = "#334155";
				result.textContent = "Posting payment JV...";
				callApi(
					"per_piece_payroll.api.create_per_piece_salary_payment_jv",
					getPaymentJVArgs(false)
				)
					.then(function (msg) {
						setPaymentAmounts(msg.debit_amount, msg.credit_amount, 0);
						var link =
							"<a href='/app/journal-entry/" +
							encodeURIComponent(msg.journal_entry) +
							"' target='_blank'>" +
							esc(msg.journal_entry) +
							"</a>";
						result.style.color = "#0f766e";
						result.innerHTML =
							"Payment JV Posted: " +
							link +
							"<br>Amount: " +
							esc(fmt(msg.payment_amount)) +
							" <button type='button' class='btn btn-xs btn-info pp-view-jv' data-jv='" +
							esc(msg.journal_entry) +
							"'>View Debit/Credit</button>";
						notifyActionResult(
							"success",
							"Payment JV Posted",
							"Payment JV has been posted successfully.",
							msg.journal_entry
						);
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
					})
					.catch(function (e) {
						showResult(
							result,
							"error",
							"Payment Post Failed",
							prettyError(errText(e))
						);
						notifyActionResult(
							"error",
							"Payment JV Failed",
							prettyError(errText(e)),
							""
						);
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
			callApi("per_piece_payroll.api.cancel_per_piece_salary_payment_jv", {
				journal_entry: jv,
			})
				.then(function (msg) {
					result.style.color = "#0f766e";
					result.innerHTML =
						"Payment JV " +
						esc(msg.action || "cancelled") +
						": " +
						esc(msg.journal_entry) +
						"<br>Rows updated: " +
						esc(msg.rows_updated || 0) +
						" | Amount reversed: " +
						esc(fmt(msg.amount_reversed || 0));
					state.paymentAdjustments = {};
					state.paymentExcludedEmployees = {};
					loadReport();
				})
				.catch(function (e) {
					showResult(result, "error", "Payment Cancel Failed", prettyError(errText(e)));
					console.error(e);
				});
		}

		function createJV() {
			confirmActionModal(
				"Post Salary JV",
				"Post JV Entry for current unposted rows?",
				"Post JV"
			).then(function (ok) {
				if (!ok) return;
				var result = el("pp-jv-result");
				result.style.color = "#334155";
				result.textContent = "Posting JV entry...";
				callApi("per_piece_payroll.api.create_per_piece_salary_jv", getJVArgs(false))
					.then(function (msg) {
						setJVAmounts(
							msg.net_payable_amount,
							msg.net_payable_amount,
							msg.gross_amount
						);
						var link =
							"<a href='/app/journal-entry/" +
							encodeURIComponent(msg.journal_entry) +
							"' target='_blank'>" +
							esc(msg.journal_entry) +
							"</a>";
						result.style.color = "#0f766e";
						result.innerHTML =
							"JV Posted: " +
							link +
							"<br>Rows: " +
							esc(msg.rows) +
							" | Gross: " +
							esc(fmt(msg.gross_amount)) +
							" | Net Payable: " +
							esc(fmt(msg.net_payable_amount)) +
							" | Advance Deduction: " +
							esc(fmt(msg.advance_deduction_amount)) +
							" | Other Deduction: " +
							esc(fmt(msg.other_deduction_amount)) +
							" <button type='button' class='btn btn-xs btn-info pp-view-jv' data-jv='" +
							esc(msg.journal_entry) +
							"'>View Debit/Credit</button>";
						notifyActionResult(
							"success",
							"Salary JV Posted",
							"Salary JV has been posted successfully.",
							msg.journal_entry
						);
						renderJournalEntryInline(result, msg.journal_entry);
						result.querySelectorAll(".pp-view-jv").forEach(function (btn) {
							btn.addEventListener("click", function () {
								var jv = btn.getAttribute("data-jv") || "";
								if (jv) showJournalEntrySummary(jv);
							});
						});
						resetEntryFiltersToAll();
						loadReport();
					})
					.catch(function (e) {
						showResult(result, "error", "JV Post Failed", prettyError(errText(e)));
						notifyActionResult(
							"error",
							"Salary JV Failed",
							prettyError(errText(e)),
							""
						);
						console.error(e);
					});
			});
		}

		function recalculateSelectedEntry() {
			var selectedEntries = parseEntryNoList(
				(el("pp-jv-entry-multi") && el("pp-jv-entry-multi").value) || ""
			);
			var singleEntry = String(
				(el("pp-jv-entry-filter") && el("pp-jv-entry-filter").value) || ""
			).trim();
			var selectedHistory = Object.keys(state.entryMeta.selected_salary_history || {})
				.filter(function (k) {
					return !!state.entryMeta.selected_salary_history[k];
				})
				.sort();
			selectedHistory.forEach(function (name) {
				if (selectedEntries.indexOf(name) < 0) selectedEntries.push(name);
			});
			if (singleEntry && selectedEntries.indexOf(singleEntry) < 0) {
				selectedEntries.unshift(singleEntry);
			}
			if (!selectedEntries.length) {
				showResult(
					el("pp-jv-result"),
					"error",
					"No Entry Selected",
					"Select one or more entries first in Salary Creation."
				);
				return;
			}

			confirmActionModal(
				"Recalculate Selected Entry",
				"Recalculate booked/net/payment amounts for selected entries?",
				"Recalculate"
			).then(function (ok) {
				if (!ok) return;
				var result = el("pp-jv-result");
				if (result) {
					result.style.color = "#334155";
					result.textContent = "Recalculating selected entries...";
				}
				callApi("per_piece_payroll.api.recalculate_selected_entries", {
					entry_nos: selectedEntries.join(","),
					entry_no: singleEntry || "",
					force_from_amount: 1,
				})
					.then(function (msg) {
						if (!msg || msg.ok === false) {
							showResult(
								result,
								"error",
								"Recalculate Failed",
								(msg && msg.message) || "Unknown error"
							);
							return;
						}
						var details =
							"Entries: " +
							esc((msg.entries || []).join(", ")) +
							"<br>Forced rows updated: " +
							esc(msg.forced_rows_updated || 0) +
							" / " +
							esc(msg.forced_rows_checked || 0) +
							"<br>Normalized rows updated: " +
							esc(msg.normalized_rows_updated || 0) +
							" / " +
							esc(msg.normalized_rows_checked || 0) +
							"<br>Financial rows updated: " +
							esc(msg.financial_rows_updated || 0) +
							" / " +
							esc(msg.financial_rows_checked || 0);
						showResult(result, "success", "Recalculation Completed", details);
						loadReport();
					})
					.catch(function (e) {
						showResult(result, "error", "Recalculate Failed", prettyError(errText(e)));
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
			callApi("per_piece_payroll.api.cancel_per_piece_salary_jv", { journal_entry: jv })
				.then(function (msg) {
					result.style.color = "#0f766e";
					result.innerHTML =
						"JV " +
						esc(msg.action || "cancelled") +
						": " +
						esc(msg.journal_entry) +
						"<br>Rows reset: " +
						esc(msg.rows_cleared || 0);
					loadReport();
				})
				.catch(function (e) {
					showResult(result, "error", "JV Cancel Failed", prettyError(errText(e)));
					console.error(e);
				});
		}

		return {
			loadJVEntryOptions: loadJVEntryOptions,
			loadPaymentJVEntryOptions: loadPaymentJVEntryOptions,
			selectPreferred: selectPreferred,
			selectPreferredPayable: selectPreferredPayable,
			loadCompanies: loadCompanies,
			loadAccountsForCompany: loadAccountsForCompany,
			loadPaymentAccountsForCompany: loadPaymentAccountsForCompany,
			getJVArgs: getJVArgs,
			getPaymentJVArgs: getPaymentJVArgs,
			previewJV: previewJV,
			previewPaymentJV: previewPaymentJV,
			createPaymentJV: createPaymentJV,
			cancelPaymentJV: cancelPaymentJV,
			createJV: createJV,
			recalculateSelectedEntry: recalculateSelectedEntry,
			cancelJVEntry: cancelJVEntry,
		};
	}

	window.PerPieceWorkflow = { create: create };
})();
