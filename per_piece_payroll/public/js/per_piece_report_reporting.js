(function () {
	function create(deps) {
		var state = deps.state;
		var el = deps.el;
		var num = deps.num;
		var fmt = deps.fmt;
		var esc = deps.esc;
		var avgRate = deps.avgRate;
		var isAmountField = deps.isAmountField;
		var employeeLabel = deps.employeeLabel;
		var summaryHeaderHtml = deps.summaryHeaderHtml;
		var setSummaryModal = deps.setSummaryModal;
		var compareByProcessSequence = deps.compareByProcessSequence;
		var getAdjustedEmployeeRows = deps.getAdjustedEmployeeRows;
		var showDataEntryEmployeeDetails = deps.showDataEntryEmployeeDetails;
		var showSalarySlipPrint = deps.showSalarySlipPrint;
		var showSalaryEntryWisePrints = deps.showSalaryEntryWisePrints;
		var currentCompanyLabel = deps.currentCompanyLabel;
		var currentDateRangeLabel = deps.currentDateRangeLabel;
		var getCurrentTabLabel = deps.getCurrentTabLabel;
		var setSummaryHeading = deps.setSummaryHeading;

		function showPerPieceSummary(docName) {
			var rows = (state.rows || []).filter(function (r) {
				return String(r.per_piece_salary || "") === String(docName || "");
			});
			var modal = el("pp-summary-modal");
			var subtitle = el("pp-summary-subtitle");
			var content = el("pp-summary-content");
			if (!modal || !subtitle || !content) return;

			if (!docName) return;
			if (!rows.length) {
				subtitle.textContent = docName;
				content.innerHTML =
					"<div style='color:#b91c1c;'>No rows available for this entry under selected filters.</div>";
				modal.style.display = "flex";
				return;
			}

			var first = rows[0] || {};
			var totalQty = 0;
			var totalAmount = 0;
			var totalBooked = 0;
			var totalPaid = 0;
			var totalUnpaid = 0;
			rows.forEach(function (r) {
				totalQty += num(r.qty);
				totalAmount += num(r.amount);
				totalBooked += num(r.booked_amount);
				totalPaid += num(r.paid_amount);
				totalUnpaid += num(r.unpaid_amount);
			});

			var subtitleText =
				docName + " | " + (first.from_date || "") + " to " + (first.to_date || "");
			var html =
				summaryHeaderHtml("Per Piece Entry Detail", subtitleText) +
				"<div class='pp-summary-chips'>" +
				"<span class='pp-summary-chip'>PO: " +
				esc(first.po_number || "-") +
				"</span>" +
				"<span class='pp-summary-chip'>Item Group: " +
				esc(first.item_group || "-") +
				"</span>" +
				"<span class='pp-summary-chip'>Rows: " +
				esc(rows.length) +
				"</span>" +
				"<span class='pp-summary-chip'>Qty: " +
				esc(fmt(totalQty)) +
				"</span>" +
				"<span class='pp-summary-chip'>Amount: " +
				esc(fmt(totalAmount)) +
				"</span>" +
				"<span class='pp-summary-chip'>Booked: " +
				esc(fmt(totalBooked)) +
				"</span>" +
				"<span class='pp-summary-chip'>Paid: " +
				esc(fmt(totalPaid)) +
				"</span>" +
				"<span class='pp-summary-chip'>Unpaid: " +
				esc(fmt(totalUnpaid)) +
				"</span>" +
				"</div>";

			html +=
				"<table class='pp-table'><thead><tr>" +
				"<th>Employee</th><th>PO Number</th><th>Product</th><th>Sales Order</th><th>Process</th><th>Process Size</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Booking</th><th>Payment</th>" +
				"</tr></thead><tbody>";
			rows.forEach(function (r) {
				html +=
					"<tr>" +
					"<td>" +
					esc(employeeLabel(r) || "") +
					"</td>" +
					"<td>" +
					esc(r.po_number || first.po_number || "") +
					"</td>" +
					"<td>" +
					esc(r.product || "") +
					"</td>" +
					"<td>" +
					esc(r.sales_order || "") +
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
					esc(fmt(r.rate)) +
					"</td>" +
					"<td class='num'>" +
					esc(fmt(r.amount)) +
					"</td>" +
					"<td>" +
					esc(r.booking_status || "") +
					"</td>" +
					"<td>" +
					esc(r.payment_status || "") +
					"</td>" +
					"</tr>";
			});
			html += "</tbody></table>";
			setSummaryModal("Per Piece Entry Detail", subtitleText, html);
		}

		function showPOSummary(poNumber, action) {
			var rows = (state.rows || []).filter(function (r) {
				return String(r.po_number || "") === String(poNumber || "");
			});
			var modal = el("pp-summary-modal");
			var subtitle = el("pp-summary-subtitle");
			var content = el("pp-summary-content");
			if (!modal || !subtitle || !content || !poNumber) return;

			if (!rows.length) {
				subtitle.textContent = "PO Number: " + poNumber;
				content.innerHTML =
					"<div style='color:#b91c1c;'>No rows available for this PO under selected filters.</div>";
				modal.style.display = "flex";
				return;
			}

			var totalQty = 0;
			var totalAmount = 0;
			var processMap = {};
			var productMap = {};
			var employeeMap = {};
			rows.forEach(function (r) {
				totalQty += num(r.qty);
				totalAmount += num(r.amount);

				var processKey = String(r.process_type || "") || "(Blank)";
				if (!processMap[processKey]) {
					processMap[processKey] = {
						process_type: r.process_type || "",
						qty: 0,
						rate: 0,
						amount: 0,
						product_map: {},
					};
				}
				processMap[processKey].qty += num(r.qty);
				processMap[processKey].amount += num(r.amount);
				var productKey = String(r.product || "") || "(Blank)";
				if (!processMap[processKey].product_map[productKey]) {
					processMap[processKey].product_map[productKey] = {
						product: r.product || "",
						qty: 0,
						amount: 0,
						rows: [],
					};
				}
				processMap[processKey].product_map[productKey].qty += num(r.qty);
				processMap[processKey].product_map[productKey].amount += num(r.amount);
				processMap[processKey].product_map[productKey].rows.push({
					per_piece_salary: r.per_piece_salary || "",
					employee: employeeLabel(r) || "",
					process_type: r.process_type || "",
					sales_order: r.sales_order || "",
					process_size: r.process_size || "No Size",
					qty: num(r.qty),
					rate: num(r.rate),
					amount: num(r.amount),
				});

				if (!productMap[productKey]) {
					productMap[productKey] = {
						product: r.product || "",
						qty: 0,
						rate: 0,
						amount: 0,
						process_map: {},
					};
				}
				productMap[productKey].qty += num(r.qty);
				productMap[productKey].amount += num(r.amount);
				if (!productMap[productKey].process_map[processKey]) {
					productMap[productKey].process_map[processKey] = {
						process_type: r.process_type || "",
						qty: 0,
						amount: 0,
						rows: [],
					};
				}
				productMap[productKey].process_map[processKey].qty += num(r.qty);
				productMap[productKey].process_map[processKey].amount += num(r.amount);
				productMap[productKey].process_map[processKey].rows.push({
					sales_order: r.sales_order || "",
					process_size: r.process_size || "No Size",
					qty: num(r.qty),
					rate: num(r.rate),
					amount: num(r.amount),
				});

				var employeeKey = String(r.employee || "") + "||" + String(r.name1 || "");
				if (!employeeMap[employeeKey]) {
					employeeMap[employeeKey] = {
						employee: r.employee || "",
						name1: r.name1 || r.employee || "",
						qty: 0,
						amount: 0,
					};
				}
				employeeMap[employeeKey].qty += num(r.qty);
				employeeMap[employeeKey].amount += num(r.amount);
			});

			var processRows = Object.keys(processMap)
				.map(function (key) {
					var item = processMap[key];
					item.rate = avgRate(item.qty, item.amount);
					item.products = Object.keys(item.product_map || {})
						.sort()
						.map(function (productKey) {
							var productItem = item.product_map[productKey];
							productItem.rate = avgRate(productItem.qty, productItem.amount);
							productItem.rows.sort(function (a, b) {
								return String(b.per_piece_salary || "").localeCompare(
									String(a.per_piece_salary || "")
								);
							});
							return productItem;
						});
					return item;
				})
				.sort(function (a, b) {
					return compareByProcessSequence(a, b, "", "");
				});
			var productRows = Object.keys(productMap)
				.sort()
				.map(function (key) {
					var item = productMap[key];
					item.rate = avgRate(item.qty, item.amount);
					item.processes = Object.keys(item.process_map || {})
						.map(function (processKey) {
							var processItem = item.process_map[processKey];
							processItem.rate = avgRate(processItem.qty, processItem.amount);
							return processItem;
						})
						.sort(function (a, b) {
							return compareByProcessSequence(
								a,
								b,
								item.product || "",
								item.product || ""
							);
						});
					return item;
				});
			var employeeRows = Object.keys(employeeMap)
				.sort()
				.map(function (key) {
					var item = employeeMap[key];
					item.rate = avgRate(item.qty, item.amount);
					return item;
				});

			var subtitleText = "PO Number: " + poNumber;
			var html =
				summaryHeaderHtml("PO Summary Detail", subtitleText) +
				"<div class='pp-summary-chips'>" +
				"<span class='pp-summary-chip' style='font-weight:700;background:#dbeafe;border-color:#93c5fd;'>PO Number: " +
				esc(poNumber) +
				"</span>" +
				"<span class='pp-summary-chip'>Entries: " +
				esc(rows.length) +
				"</span>" +
				"<span class='pp-summary-chip'>Qty: " +
				esc(fmt(totalQty)) +
				"</span>" +
				"<span class='pp-summary-chip'>Amount: " +
				esc(fmt(totalAmount)) +
				"</span>" +
				"</div>";

			if (action !== "print_product") {
				processRows.forEach(function (r) {
					html +=
						"<h4 style='margin:12px 0 6px 0;'>Process: " +
						esc(r.process_type || "(Blank)") +
						"</h4>";
					html +=
						"<table class='pp-table'><thead><tr><th>Product</th><th>Sales Order</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
					(r.products || []).forEach(function (productItem) {
						(productItem.rows || []).forEach(function (detailRow) {
							html +=
								"<tr>" +
								"<td>" +
								esc(productItem.product || "") +
								"</td>" +
								"<td>" +
								esc(detailRow.sales_order || "") +
								"</td>" +
								"<td>" +
								esc(detailRow.process_size || "No Size") +
								"</td>" +
								"<td class='num'>" +
								esc(fmt(detailRow.qty)) +
								"</td>" +
								"<td class='num'>" +
								esc(fmt(detailRow.rate)) +
								"</td>" +
								"<td class='num pp-amt-col'>" +
								esc(fmt(detailRow.amount)) +
								"</td>" +
								"</tr>";
						});
					});
					html +=
						"<tr class='pp-year-total'><td colspan='3'>Process Total</td><td class='num'>" +
						esc(fmt(r.qty)) +
						"</td><td class='num'>" +
						esc(fmt(r.rate)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(r.amount)) +
						"</td></tr>";
					html += "</tbody></table>";
				});
			}

			if (action !== "print_process") {
				html += "<h4 style='margin:14px 0 6px 0;'>Product Heading / Process Table</h4>";
				productRows.forEach(function (r) {
					html +=
						"<h4 style='margin:12px 0 6px 0;'>Product: " +
						esc(r.product || "(Blank)") +
						"</h4>";
					html +=
						"<table class='pp-table'><thead><tr><th>Process</th><th>Sales Order</th><th>Size</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
					(r.processes || []).forEach(function (processItem) {
						(processItem.rows || []).forEach(function (detailRow) {
							html +=
								"<tr>" +
								"<td>" +
								esc(processItem.process_type || "") +
								"</td>" +
								"<td>" +
								esc(detailRow.sales_order || "") +
								"</td>" +
								"<td>" +
								esc(detailRow.process_size || "No Size") +
								"</td>" +
								"<td class='num'>" +
								esc(fmt(detailRow.qty)) +
								"</td>" +
								"<td class='num'>" +
								esc(fmt(detailRow.rate)) +
								"</td>" +
								"<td class='num pp-amt-col'>" +
								esc(fmt(detailRow.amount)) +
								"</td>" +
								"</tr>";
						});
					});
					html +=
						"<tr class='pp-year-total'><td colspan='3'>Product Total</td><td class='num'>" +
						esc(fmt(r.qty)) +
						"</td><td class='num'>" +
						esc(fmt(r.rate)) +
						"</td><td class='num pp-amt-col'>" +
						esc(fmt(r.amount)) +
						"</td></tr>";
					html += "</tbody></table>";
				});
			}

			html += "<h4 style='margin:12px 0 6px 0;'>All Process Grand Total</h4>";
			html +=
				"<table class='pp-table'><thead><tr><th>Label</th><th>Total Qty</th><th>Total Amount</th></tr></thead><tbody>";
			html +=
				"<tr class='pp-year-total'><td>Grand Total</td><td class='num'>" +
				esc(fmt(totalQty)) +
				"</td><td class='num pp-amt-col'>" +
				esc(fmt(totalAmount)) +
				"</td></tr>";
			html += "</tbody></table>";

			html += "<h4 style='margin:12px 0 6px 0;'>Employee Summary</h4>";
			html +=
				"<table class='pp-table'><thead><tr><th>Employee</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>";
			employeeRows.forEach(function (r) {
				html +=
					"<tr><td>" +
					esc(r.name1 || r.employee || "") +
					"</td><td class='num'>" +
					esc(fmt(r.qty)) +
					"</td><td class='num'>" +
					esc(fmt(r.rate)) +
					"</td><td class='num pp-amt-col'>" +
					esc(fmt(r.amount)) +
					"</td></tr>";
			});
			html +=
				"<tr class='pp-year-total'><td>Total</td><td class='num'>" +
				esc(fmt(totalQty)) +
				"</td><td></td><td class='num pp-amt-col'>" +
				esc(fmt(totalAmount)) +
				"</td></tr>";
			html += "</tbody></table>";

			setSummaryModal("PO Summary Detail", subtitleText, html);
			if (
				action === "print" ||
				action === "pdf" ||
				action === "print_process" ||
				action === "print_product"
			) {
				setTimeout(function () {
					printSummaryModal();
				}, 50);
			}
		}

		function showSalaryEmployeeDetail(employee) {
			var modal = el("pp-summary-modal");
			var subtitle = el("pp-summary-subtitle");
			var content = el("pp-summary-content");
			if (!modal || !subtitle || !content || !employee) return;

			var rows = getAdjustedEmployeeRows();
			var row = null;
			rows.forEach(function (r) {
				if (!row && String(r.employee || "") === String(employee || "")) row = r;
			});

			if (!row) {
				subtitle.textContent = employee;
				content.innerHTML =
					"<div style='color:#b91c1c;'>No employee detail available under current filters.</div>";
				modal.style.display = "flex";
				return;
			}

			var detailQty = 0;
			var detailAmount = 0;
			(row.source_entries || []).forEach(function (src) {
				detailQty += num(src.qty);
				detailAmount += num(src.amount);
			});

			var subtitleText = (employeeLabel(row) || employee) + " | Salary Detail";
			var html =
				summaryHeaderHtml("Salary Creation Detail", subtitleText) +
				"<div class='pp-summary-chips'>" +
				"<span class='pp-summary-chip'>Employee: " +
				esc(row.employee || "-") +
				"</span>" +
				"<span class='pp-summary-chip'>Qty: " +
				esc(fmt(row.qty)) +
				"</span>" +
				"<span class='pp-summary-chip'>Base Amount: " +
				esc(fmt(row.amount)) +
				"</span>" +
				"<span class='pp-summary-chip'>Advance Balance: " +
				esc(fmt(row.advance_balance)) +
				"</span>" +
				"<span class='pp-summary-chip'>Advance Deduction: " +
				esc(fmt(row.advance_deduction)) +
				"</span>" +
				"<span class='pp-summary-chip'>Allowance: " +
				esc(fmt(row.allowance)) +
				"</span>" +
				"<span class='pp-summary-chip'>Other Deduction: " +
				esc(fmt(row.other_deduction)) +
				"</span>" +
				"<span class='pp-summary-chip'>Net Amount: " +
				esc(fmt(row.net_amount)) +
				"</span>" +
				"<span class='pp-summary-chip'>Entries: " +
				esc(row.source_count || 0) +
				"</span>" +
				"</div>";

			if (!(row.source_entries || []).length) {
				html +=
					"<div style='color:#475569;'>No source entries found for this employee in current salary selection.</div>";
				setSummaryModal("Salary Creation Detail", subtitleText, html);
				return;
			}

			html +=
				"<table class='pp-table'><thead><tr>" +
				"<th>Per Piece Salary</th><th>PO Number</th><th>Sales Order</th><th>Qty</th><th>Amount</th><th>View</th>" +
				"</tr></thead><tbody>";
			(row.source_entries || []).forEach(function (src) {
				html +=
					"<tr>" +
					"<td>" +
					esc(src.per_piece_salary || "") +
					"</td>" +
					"<td>" +
					esc(src.po_number || "") +
					"</td>" +
					"<td>" +
					esc(src.sales_order || "") +
					"</td>" +
					"<td class='num'>" +
					esc(fmt(src.qty)) +
					"</td>" +
					"<td class='num pp-amt-col'>" +
					esc(fmt(src.amount)) +
					"</td>" +
					"<td><button type='button' class='btn btn-xs btn-default pp-salary-entry-detail' data-doc='" +
					encodeURIComponent(String(src.per_piece_salary || "")) +
					"'>View Items</button></td>" +
					"</tr>";
			});
			html +=
				"<tr class='pp-year-total'>" +
				"<td>Total Entries: " +
				esc(row.source_count || 0) +
				"</td>" +
				"<td></td>" +
				"<td></td>" +
				"<td class='num'>" +
				esc(fmt(detailQty)) +
				"</td>" +
				"<td class='num pp-amt-col'>" +
				esc(fmt(detailAmount)) +
				"</td>" +
				"<td></td>" +
				"</tr>";
			html += "</tbody></table>";
			content.innerHTML = html;
			content.querySelectorAll(".pp-salary-entry-detail").forEach(function (btn) {
				btn.addEventListener("click", function () {
					var docName = decodeURIComponent(btn.getAttribute("data-doc") || "");
					if (!docName) return;
					showPerPieceSummary(docName);
				});
			});
			setSummaryHeading("Salary Creation Detail");
			subtitle.textContent = subtitleText;
			state.summaryPrintMeta = {
				heading: "Salary Creation Detail",
				subtitle: subtitleText,
				company: currentCompanyLabel(),
				date_range: currentDateRangeLabel(),
			};
			modal.style.display = "flex";
		}

		function hidePerPieceSummary() {
			var modal = el("pp-summary-modal");
			if (modal) modal.style.display = "none";
		}

		function printSummaryModal() {
			var title = el("pp-summary-subtitle")
				? el("pp-summary-subtitle").textContent || ""
				: "";
			var body = el("pp-summary-content") ? el("pp-summary-content").innerHTML || "" : "";
			if (!body) return;
			var tempWrap = document.createElement("div");
			tempWrap.innerHTML = body;
			var inlineHeader = tempWrap.querySelector(".pp-inline-summary-header");
			if (inlineHeader && inlineHeader.parentNode)
				inlineHeader.parentNode.removeChild(inlineHeader);
			body = tempWrap.innerHTML;
			var meta = state.summaryPrintMeta || {};
			var heading = meta.heading || "Per Piece Salary Summary";
			var company = meta.company || currentCompanyLabel() || "";
			var dateRange = meta.date_range || currentDateRangeLabel() || "";
			var win = window.open("", "_blank", "width=1200,height=800");
			if (!win) return;
			win.document.open();
			win.document.write(
				"<!DOCTYPE html><html><head><title>" +
					esc(title) +
					"</title>" +
					"<style>" +
					"body{font-family:Arial,sans-serif;padding:18px;color:#111827;}" +
					"h1{font-size:20px;margin:0 0 4px 0;} .sub{font-size:12px;color:#475569;margin-bottom:12px;}" +
					".pp-table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:14px;}" +
					".pp-table th,.pp-table td{border:1px solid #cbd5e1;padding:6px 8px;}" +
					".pp-table th{background:#dbeafe !important;text-align:left;-webkit-print-color-adjust:exact;print-color-adjust:exact;}" +
					".pp-table td.num{text-align:right;font-variant-numeric:tabular-nums;}" +
					".pp-table td.pp-amt-col{font-weight:700;}" +
					".pp-year-total td{background:#ecfccb !important;font-weight:700;-webkit-print-color-adjust:exact;print-color-adjust:exact;}" +
					".pp-summary-chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;}" +
					".pp-summary-chip{border:1px solid #cbd5e1;border-radius:999px;padding:4px 8px;font-size:12px;}" +
					"h4{margin:12px 0 6px 0;font-size:14px;background:#fef3c7 !important;border:1px solid #cbd5e1;padding:6px 8px;-webkit-print-color-adjust:exact;print-color-adjust:exact;}" +
					"</style></head><body>" +
					"<h1>" +
					esc(company || "Company") +
					"</h1>" +
					"<div class='sub'><strong>" +
					esc(heading) +
					"</strong>" +
					(title ? " | " + esc(title) : "") +
					(dateRange ? " | Date: " + esc(dateRange) : "") +
					"</div>" +
					body +
					"</body></html>"
			);
			win.document.close();
			win.focus();
			win.print();
		}

		function printCurrentTabReport() {
			var snap = state.lastTabRender || {};
			var heading = getCurrentTabLabel() || "Report";
			var dateRange = currentDateRangeLabel();
			var company = currentCompanyLabel();
			var tableHtml = "";

			if (snap.mode === "table" && (snap.columns || []).length) {
				tableHtml = "<table class='pp-table'><thead><tr>";
				(snap.columns || []).forEach(function (c) {
					tableHtml += "<th>" + esc(c.label || "") + "</th>";
				});
				tableHtml += "</tr></thead><tbody>";
				(snap.rows || []).forEach(function (r) {
					var rowClass = "";
					if (r && r._group_header) rowClass = " class='pp-group-head'";
					else if (r && r._is_total) rowClass = " class='pp-year-total'";
					tableHtml += "<tr" + rowClass + ">";
					(snap.columns || []).forEach(function (c, idx) {
						if (r && r._group_header) {
							if (idx === 0)
								tableHtml += "<td>" + esc(r._group_label || "") + "</td>";
							else tableHtml += "<td></td>";
							return;
						}
						var v = r ? r[c.fieldname] : "";
						var classes = [];
						if (c.numeric) classes.push("num");
						if (isAmountField(c.fieldname)) classes.push("pp-amt-col");
						var cls = classes.length ? " class='" + classes.join(" ") + "'" : "";
						tableHtml +=
							"<td" + cls + ">" + esc(c.numeric ? fmt(v) : v || "") + "</td>";
					});
					tableHtml += "</tr>";
				});
				tableHtml += "</tbody></table>";
			} else {
				var wrap = el("pp-table-wrap");
				tableHtml = wrap ? wrap.innerHTML || "<div>No data</div>" : "<div>No data</div>";
			}

			var win = window.open("", "_blank", "width=1200,height=800");
			if (!win) return;
			win.document.open();
			win.document.write(
				"<!DOCTYPE html><html><head><title>" +
					esc(heading) +
					"</title>" +
					"<style>" +
					"body{font-family:Arial,sans-serif;padding:18px;color:#111827;}" +
					"h1{font-size:20px;margin:0 0 4px 0;} .sub{font-size:12px;color:#475569;margin-bottom:12px;}" +
					".pp-table{width:100%;border-collapse:collapse;font-size:12px;}" +
					".pp-table th,.pp-table td{border:1px solid #cbd5e1;padding:6px 8px;}" +
					".pp-table th{background:#dbeafe !important;text-align:left;-webkit-print-color-adjust:exact;print-color-adjust:exact;}" +
					".pp-table td.num{text-align:right;font-variant-numeric:tabular-nums;}" +
					".pp-table td.pp-amt-col{font-weight:700;}" +
					".pp-year-total td{background:#ecfccb !important;font-weight:700;-webkit-print-color-adjust:exact;print-color-adjust:exact;}" +
					".pp-group-head td{background:#e2e8f0 !important;font-weight:700;-webkit-print-color-adjust:exact;print-color-adjust:exact;}" +
					"</style></head><body>" +
					"<h1>" +
					esc(company || "Company") +
					"</h1>" +
					"<div class='sub'><strong>" +
					esc(heading) +
					"</strong>" +
					(dateRange ? " | Date: " + esc(dateRange) : "") +
					"</div>" +
					tableHtml +
					"</body></html>"
			);
			win.document.close();
			win.focus();
			win.print();
		}

		return {
			showPerPieceSummary: showPerPieceSummary,
			showPOSummary: showPOSummary,
			showSalaryEmployeeDetail: showSalaryEmployeeDetail,
			hidePerPieceSummary: hidePerPieceSummary,
			printSummaryModal: printSummaryModal,
			printCurrentTabReport: printCurrentTabReport,
		};
	}

	window.PerPieceReporting = { create: create };
})();
