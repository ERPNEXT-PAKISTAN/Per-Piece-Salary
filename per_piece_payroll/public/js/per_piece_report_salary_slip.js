(function () {
	function create(deps) {
		var state = deps.state;
		var el = deps.el;
		var esc = deps.esc;
		var num = deps.num;
		var fmt = deps.fmt;
		var avgRate = deps.avgRate;
		var callApi = deps.callApi;
		var compareByProcessSequence = deps.compareByProcessSequence;
		var getRowsByHeaderFilters = deps.getRowsByHeaderFilters;
		var currentDateRangeLabel = deps.currentDateRangeLabel;
		var summaryHeaderHtml = deps.summaryHeaderHtml;
		var setSummaryModal = deps.setSummaryModal;
		var prettyError = deps.prettyError;
		var errText = deps.errText;

		function buildSalarySlipGroupDetail(group) {
			if (!group) return null;
			var processTotals = {};
			var itemTotals = {};
			(group.rows || []).forEach(function (r) {
				var processKey =
					String(r.process_type || "") + "||" + String(r.process_size || "No Size");
				if (!processTotals[processKey]) {
					processTotals[processKey] = {
						process_type: r.process_type || "",
						process_size: r.process_size || "No Size",
						qty: 0,
						amount: 0,
						rate: 0,
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
						rate: 0,
					};
				}
				itemTotals[itemKey].qty += num(r.qty);
				itemTotals[itemKey].amount += num(r.amount);
			});
			return {
				processRows: Object.keys(processTotals)
					.map(function (key) {
						var item = processTotals[key];
						item.rate = avgRate(item.qty, item.amount);
						return item;
					})
					.sort(function (a, b) {
						return compareByProcessSequence(a, b, "", "");
					}),
				itemRows: Object.keys(itemTotals)
					.sort()
					.map(function (key) {
						var item = itemTotals[key];
						item.rate = avgRate(item.qty, item.amount);
						return item;
					}),
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
			((group && group.rows) || []).forEach(function (row) {
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
			((group && group.rows) || []).forEach(function (row) {
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
					closing_advance_balance: openingNoJV,
				});
			}
			return Promise.all(
				jvNames.map(function (jvName) {
					return getJournalEntryDoc(jvName);
				})
			).then(function (docs) {
				var advanceDeduction = 0;
				var otherDeduction = 0;
				var netAmount = 0;
				docs.forEach(function (doc) {
					if (!doc || Number(doc.docstatus) !== 1) return;
					((doc && doc.accounts) || []).forEach(function (acc) {
						var party = String(acc.party || "").trim();
						var credit = num(acc.credit_in_account_currency || acc.credit);
						var remark = String(acc.user_remark || "");
						if (credit <= 0) return;
						var isAdvance = remark.indexOf("Advance Recovery - " + employee) === 0;
						var isDeduction = remark.indexOf("Salary Deduction - " + employee) === 0;
						var isNet = remark.indexOf("Net Salary - " + employee) === 0;
						var matchesParty = party === employee;
						if (
							isAdvance ||
							(matchesParty && remark.indexOf("Advance Recovery - ") === 0)
						) {
							advanceDeduction += credit;
						} else if (
							isDeduction ||
							(matchesParty && remark.indexOf("Salary Deduction - ") === 0)
						) {
							otherDeduction += credit;
						} else if (
							isNet ||
							(matchesParty && remark.indexOf("Net Salary - ") === 0)
						) {
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
				var postedAllowance = Math.max(
					netAmount - postedBaseAmount + advanceDeduction + otherDeduction,
					0
				);
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
					closing_advance_balance: closingAdvanceProjected,
				};
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
						rows: [],
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
					unpaid_amount: num(r.unpaid_amount),
				});
			});
			return Object.keys(map)
				.sort()
				.map(function (key) {
					var item = map[key];
					item.rate = avgRate(item.qty, item.amount);
					return item;
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
				setSummaryModal(
					"Salary Slip Detail",
					employee || "",
					"<div style='color:#b91c1c;'>No salary detail found for current filters.</div>"
				);
				return;
			}
			var scopedRows = (group.rows || []).filter(function (r) {
				if (!selectedEntry) return true;
				return String(r.per_piece_salary || "") === selectedEntry;
			});
			if (!scopedRows.length) {
				setSummaryModal(
					"Salary Slip Detail",
					employee || "",
					"<div style='color:#b91c1c;'>No rows found for selected salary entry.</div>"
				);
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
				rows: scopedRows,
			};
			setSummaryModal(
				"Salary Slip Detail",
				employee || "",
				"<div style='color:#334155;'>Loading salary slip...</div>"
			);
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
			var subtitleText = employeeTitle + (selectedEntry ? " | Entry: " + selectedEntry : "");
			getSalarySlipFinancials(scopedGroup)
				.then(function (financials) {
					var html = summaryHeaderHtml("Salary Slip Detail", subtitleText);
					html += "<div style='text-align:center;margin:2px 0 14px 0;'>";
					html +=
						"<div style='font-size:30px;font-weight:800;color:#0f172a;line-height:1.1;'>" +
						esc(employeeTitle || "Employee") +
						"</div>";
					html +=
						"<div style='font-size:15px;font-weight:700;color:#334155;margin-top:6px;'>" +
						esc(
							mode === "product"
								? "Product wise Detail Report"
								: "Detail Salary Slip"
						) +
						"</div>";
					if (slipRange)
						html +=
							"<div style='font-size:14px;font-weight:700;color:#475569;margin-top:4px;'>Date: " +
							esc(slipRange) +
							"</div>";
					html += "</div>";
					html +=
						"<div class='pp-summary-chips'>" +
						"<span class='pp-summary-chip'>Employee: " +
						esc(scopedGroup.employee || "-") +
						"</span>" +
						"<span class='pp-summary-chip'>Entries: " +
						esc(scopedGroup.source_count || 0) +
						"</span>" +
						"<span class='pp-summary-chip'>Qty: " +
						esc(fmt(scopedGroup.qty)) +
						"</span>" +
						"<span class='pp-summary-chip'>Rate: " +
						esc(fmt(scopedGroup.rate)) +
						"</span>" +
						"<span class='pp-summary-chip'>Amount: " +
						esc(fmt(scopedGroup.amount)) +
						"</span>" +
						"</div>";

					if (mode === "product") {
						var productDetailMap = {};
						scopedRows.forEach(function (r) {
							var k = [
								String(r.po_number || ""),
								String(r.product || ""),
								String(r.process_type || ""),
								String(r.process_size || "No Size"),
							].join("||");
							if (!productDetailMap[k]) {
								productDetailMap[k] = {
									po_number: r.po_number || "",
									product: r.product || "",
									process_type: r.process_type || "",
									process_size: r.process_size || "No Size",
									qty: 0,
									amount: 0,
									rate: 0,
								};
							}
							productDetailMap[k].qty += num(r.qty);
							productDetailMap[k].amount += num(r.amount);
						});
						var productDetailRows = Object.keys(productDetailMap)
							.map(function (k) {
								var row = productDetailMap[k];
								row.rate = avgRate(row.qty, row.amount);
								return row;
							})
							.sort(function (a, b) {
								var poa = String(a.po_number || "");
								var pob = String(b.po_number || "");
								if (poa !== pob) return poa.localeCompare(pob);
								var pa = String(a.product || "");
								var pb = String(b.product || "");
								if (pa !== pb) return pa.localeCompare(pb);
								return compareByProcessSequence(a, b, pa, pb);
							});
						html += "<h4 style='margin:10px 0 6px 0;'>Product wise Detail Report</h4>";
						html +=
							"<table class='pp-table'><thead><tr><th>PO Number</th><th>Product</th><th>Process</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
						var byPoProduct = {};
						productDetailRows.forEach(function (r) {
							var po = String(r.po_number || "").trim() || "(Blank)";
							var product = String(r.product || "").trim() || "(Blank)";
							if (!byPoProduct[po]) byPoProduct[po] = {};
							if (!byPoProduct[po][product]) byPoProduct[po][product] = [];
							byPoProduct[po][product].push(r);
						});
						Object.keys(byPoProduct)
							.sort()
							.forEach(function (po) {
								var poQty = 0;
								var poAmount = 0;
								html +=
									"<tr class='pp-group-head'><td colspan='7'>PO Number: " +
									esc(po) +
									"</td></tr>";
								Object.keys(byPoProduct[po] || {})
									.sort()
									.forEach(function (product) {
										var rowsByProduct = byPoProduct[po][product] || [];
										var productQty = 0;
										var productAmount = 0;
										rowsByProduct.forEach(function (r) {
											var q = num(r.qty);
											var a = num(r.amount);
											productQty += q;
											productAmount += a;
											poQty += q;
											poAmount += a;
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
												esc(fmt(r.rate)) +
												"</td><td class='num pp-amt-col'>" +
												esc(fmt(a)) +
												"</td></tr>";
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
									"</td></tr>";
							});
						html +=
							"<tr class='pp-year-total'><td>Total</td><td></td><td></td><td></td><td class='num'>" +
							esc(fmt(scopedGroup.qty)) +
							"</td><td class='num'>" +
							esc(fmt(scopedGroup.rate)) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(scopedGroup.amount)) +
							"</td></tr>";
						html += "</tbody></table>";
					} else {
						var mergedMap = {};
						scopedRows.forEach(function (r) {
							var item = String(r.product || "").trim() || "(Blank)";
							var pkey =
								String(r.po_number || "") +
								"||" +
								item +
								"||" +
								String(r.process_type || "") +
								"||" +
								String(r.process_size || "No Size");
							if (!mergedMap[pkey])
								mergedMap[pkey] = {
									po_number: r.po_number || "",
									product: item,
									process_type: r.process_type || "",
									process_size: r.process_size || "No Size",
									qty: 0,
									amount: 0,
								};
							mergedMap[pkey].qty += num(r.qty);
							mergedMap[pkey].amount += num(r.amount);
						});
						var mergedRows = Object.keys(mergedMap)
							.map(function (k) {
								var row = mergedMap[k];
								row.rate = avgRate(row.qty, row.amount);
								return row;
							})
							.sort(function (a, b) {
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
						html +=
							"<h4 style='margin:10px 0 6px 0;'>Item Wise Summary (with Process)</h4>";
						html +=
							"<table class='pp-table'><thead><tr><th>PO Number</th><th>Item</th><th>Process</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
						Object.keys(byItem)
							.sort()
							.forEach(function (itemKey) {
								var itemParts = String(itemKey || "").split("||");
								var itemPo = itemParts[0] || "";
								var item = itemParts.slice(1).join("||") || "(Blank)";
								var iQty = 0;
								var iAmount = 0;
								(byItem[itemKey] || []).forEach(function (r) {
									iQty += num(r.qty);
									iAmount += num(r.amount);
									html +=
										"<tr><td>" +
										esc(itemPo) +
										"</td><td>" +
										esc(item) +
										"</td><td>" +
										esc(r.process_type || "") +
										"</td><td>" +
										esc(r.process_size || "No Size") +
										"</td><td class='num'>" +
										esc(fmt(r.qty)) +
										"</td><td class='num'>" +
										esc(fmt(r.rate)) +
										"</td><td class='num pp-amt-col'>" +
										esc(fmt(r.amount)) +
										"</td></tr>";
								});
								html +=
									"<tr class='pp-year-total'><td>" +
									esc(itemPo) +
									"</td><td>" +
									esc(item) +
									" Total</td><td></td><td></td><td class='num'>" +
									esc(fmt(iQty)) +
									"</td><td class='num'>" +
									esc(fmt(avgRate(iQty, iAmount))) +
									"</td><td class='num pp-amt-col'>" +
									esc(fmt(iAmount)) +
									"</td></tr>";
							});
						html +=
							"<tr class='pp-year-total'><td>Grand Total</td><td></td><td></td><td></td><td class='num'>" +
							esc(fmt(scopedGroup.qty)) +
							"</td><td class='num'>" +
							esc(fmt(scopedGroup.rate)) +
							"</td><td class='num pp-amt-col'>" +
							esc(fmt(scopedGroup.amount)) +
							"</td></tr>";
						html += "</tbody></table>";
					}

					html += "<h4 style='margin:12px 0 6px 0;'>Financial Summary</h4>";
					html +=
						"<div style='border:1px solid #cbd5e1;border-radius:10px;background:#f8fafc;padding:12px 14px;margin-top:8px;font-family:Calibri,Tahoma,Arial,sans-serif;font-weight:400;'>";
					html += "<div style='display:flex;gap:18px;flex-wrap:wrap;'>";
					html +=
						"<div style='flex:1;min-width:220px;border-right:1px solid #d6dee8;padding-right:12px;'>";
					html +=
						"<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>Booked Salary</span><span>" +
						esc(fmt(financials.booked_salary_amount)) +
						"</span></div>";
					html +=
						"<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>UnBooked Salary</span><span>" +
						esc(fmt(financials.unbooked_salary_amount)) +
						"</span></div>";
					html +=
						"<div style='margin:4px 0;padding-bottom:6px;border-bottom:1px solid #d6dee8;display:flex;justify-content:space-between;gap:10px;'><span>Net Salary Booked</span><span>" +
						esc(fmt(financials.net_amount)) +
						"</span></div>";
					html +=
						"<div style='margin:10px 0 0 0;display:flex;justify-content:space-between;gap:10px;'><span>Paid</span><span>" +
						esc(fmt(financials.paid_amount)) +
						"</span></div>";
					html +=
						"<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>Unpaid</span><span>" +
						esc(fmt(financials.unpaid_amount)) +
						"</span></div>";
					html += "</div>";
					html +=
						"<div style='flex:1;min-width:220px;border-right:1px solid #d6dee8;padding-right:12px;'>";
					html +=
						"<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span>Allowance</span><span>" +
						esc(fmt(financials.allowance)) +
						"</span></div>";
					html +=
						"<div style='margin:4px 0;padding-bottom:6px;border-bottom:1px solid #d6dee8;display:flex;justify-content:space-between;gap:10px;'><span>Other Deduction</span><span>" +
						esc(fmt(financials.other_deduction)) +
						"</span></div>";
					html += "</div>";
					html += "<div style='flex:1;min-width:240px;'>";
					html +=
						"<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span style='color:#92400e;'>Opening Advance</span><span style='color:#92400e;'>" +
						esc(fmt(financials.opening_advance_balance)) +
						"</span></div>";
					html +=
						"<div style='margin:4px 0;padding-bottom:6px;border-bottom:1px solid #d6dee8;display:flex;justify-content:space-between;gap:10px;'><span style='color:#92400e;'>Advance Deduction</span><span style='color:#92400e;'>" +
						esc(fmt(financials.advance_deduction)) +
						"</span></div>";
					html +=
						"<div style='margin:4px 0;display:flex;justify-content:space-between;gap:10px;'><span style='color:#166534;'>Closing Advance</span><span style='color:#166534;'>" +
						esc(fmt(financials.closing_advance_balance)) +
						"</span></div>";
					html += "</div>";
					html += "</div>";
					html += "</div>";
					html +=
						"<table style='width:100%;margin-top:22px;border-collapse:collapse;table-layout:fixed;'><tr>" +
						"<td style='width:33.33%;padding-top:20px;vertical-align:top;text-align:center;'><span class='pp-sign-line' style='margin:0 auto;'>Created By</span></td>" +
						"<td style='width:33.33%;padding-top:20px;vertical-align:top;text-align:center;'><span class='pp-sign-line' style='margin:0 auto;'>Approved By</span></td>" +
						"<td style='width:33.33%;padding-top:20px;vertical-align:top;text-align:center;'><span class='pp-sign-line' style='margin:0 auto;'>Received By</span></td>" +
						"</tr></table>";
					setSummaryModal("Salary Slip Detail", subtitleText, html);
				})
				.catch(function (e) {
					setSummaryModal(
						"Salary Slip Detail",
						subtitleText,
						"<div style='color:#b91c1c;'>Failed to load salary slip: " +
							esc(prettyError(errText(e))) +
							"</div>"
					);
				});
		}

		function showSalaryEntryWisePrints(employee) {
			var groups = buildSalarySlipGroups(getRowsByHeaderFilters(state.rows || []));
			var group = null;
			groups.forEach(function (g) {
				if (!group && String(g.employee || "") === String(employee || "")) group = g;
			});
			if (!group) {
				setSummaryModal(
					"Entry Wise Prints",
					employee || "",
					"<div style='color:#b91c1c;'>No salary rows found.</div>"
				);
				return;
			}
			var entryMap = {};
			(group.rows || []).forEach(function (r) {
				var entry = String(r.per_piece_salary || "").trim();
				if (!entry) return;
				if (!entryMap[entry])
					entryMap[entry] = {
						per_piece_salary: entry,
						from_date: r.from_date || "",
						to_date: r.to_date || "",
						qty: 0,
						amount: 0,
					};
				entryMap[entry].qty += num(r.qty);
				entryMap[entry].amount += num(r.amount);
				if (
					r.from_date &&
					(!entryMap[entry].from_date ||
						String(r.from_date) < String(entryMap[entry].from_date))
				)
					entryMap[entry].from_date = r.from_date;
				if (
					r.to_date &&
					(!entryMap[entry].to_date ||
						String(r.to_date) > String(entryMap[entry].to_date))
				)
					entryMap[entry].to_date = r.to_date;
			});
			var entries = Object.keys(entryMap)
				.sort(function (a, b) {
					return String(b).localeCompare(String(a));
				})
				.map(function (k) {
					return entryMap[k];
				});
			if (!entries.length) {
				setSummaryModal(
					"Entry Wise Prints",
					employee || "",
					"<div style='color:#b91c1c;'>No salary entries found.</div>"
				);
				return;
			}
			var html =
				"<table class='pp-table'><thead><tr><th>Entry No</th><th>From Date</th><th>To Date</th><th>Qty</th><th>Amount</th><th>Print Detail</th><th>Print Product</th></tr></thead><tbody>";
			entries.forEach(function (r) {
				html +=
					"<tr><td>" +
					esc(r.per_piece_salary) +
					"</td><td>" +
					esc(r.from_date || "") +
					"</td><td>" +
					esc(r.to_date || "") +
					"</td><td class='num'>" +
					esc(fmt(r.qty)) +
					"</td><td class='num pp-amt-col'>" +
					esc(fmt(r.amount)) +
					"</td><td><button type='button' class='btn btn-xs btn-primary pp-salary-entry-print' data-mode='detail' data-employee='" +
					esc(employee || "") +
					"' data-entry='" +
					esc(r.per_piece_salary) +
					"'>Print</button></td><td><button type='button' class='btn btn-xs btn-primary pp-salary-entry-print' data-mode='product' data-employee='" +
					esc(employee || "") +
					"' data-entry='" +
					esc(r.per_piece_salary) +
					"'>Print</button></td></tr>";
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

		return {
			buildSalarySlipGroupDetail: buildSalarySlipGroupDetail,
			getJournalEntryDoc: getJournalEntryDoc,
			getSalarySlipFinancials: getSalarySlipFinancials,
			buildSalarySlipGroups: buildSalarySlipGroups,
			showSalarySlipPrint: showSalarySlipPrint,
			showSalaryEntryWisePrints: showSalaryEntryWisePrints,
		};
	}

	window.PerPieceSalarySlip = { create: create };
})();
