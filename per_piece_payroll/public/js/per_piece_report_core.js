(function () {
	var state = {
		workspaceMode: "entry",
		currentTab: "data_entry",
		rows: [],
		columns: [],
		filterOptions: {
			employees: [],
			item_groups: [],
			products: [],
			process_types: [],
			sales_orders: [],
		},
		adjustments: {},
		advanceBalances: {},
		advanceRows: [],
		advanceMonths: [],
		excludedEmployees: {},
		paymentAdjustments: {},
		paymentExcludedEmployees: {},
		workflowHistoryDate: {
			data_entry: { from: "", to: "" },
			salary_creation: { from: "", to: "" },
			payment_manage: { from: "", to: "" },
		},
		workflowStatusFilter: {
			data_entry: { booking: "", payment: "" },
			salary_creation: { booking: "", payment: "" },
			payment_manage: { booking: "", payment: "" },
		},
		entryRows: [],
		entryMeta: {},
		employeeSummaryDetail: false,
		pageSize: 20,
		pageByTab: {},
		historyPageByTab: {},
		forcedEntryNo: "",
		paymentPrefill: null,
		summaryPrintMeta: {
			heading: "Per Piece Salary Summary",
			subtitle: "",
			company: "",
			date_range: "",
		},
		lastTabRender: { mode: "dom", columns: [], rows: [] },
	};

	function el(id) {
		return document.getElementById(id);
	}
	function esc(v) {
		var d = document.createElement("div");
		d.textContent = v == null ? "" : String(v);
		return d.innerHTML;
	}
	function num(v) {
		var n = Number(v || 0);
		return isNaN(n) ? 0 : n;
	}
	function whole(v) {
		return Math.max(0, Math.round(num(v) * 100) / 100);
	}
	function fmt(v) {
		return num(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
	}
	function isGuestSession() {
		try {
			if (
				typeof frappe !== "undefined" &&
				frappe.session &&
				String(frappe.session.user || "") === "Guest"
			)
				return true;
		} catch (e) {
			/* ignore session lookup errors */
		}
		return document.cookie.indexOf("sid=Guest") >= 0;
	}
	function redirectToLogin() {
		if (window.location.pathname === "/login") return;
		var next =
			window.location.pathname +
			(window.location.search || "") +
			(window.location.hash || "");
		window.location.href =
			"/login?redirect-to=" + encodeURIComponent(next || "/per-piece-report");
	}
	function ensureLoggedInOrRedirect() {
		if (!isGuestSession()) return false;
		var msgEl = el("pp-msg");
		if (msgEl) msgEl.textContent = "Please login to access this report. Redirecting...";
		window.setTimeout(redirectToLogin, 120);
		return true;
	}
	function entrySequenceNo(name) {
		var txt = String(name || "").trim();
		var m = txt.match(/-(\d+)\s*$/);
		return m ? parseInt(m[1], 10) || 0 : 0;
	}
	function compareEntryNoDesc(a, b) {
		var as = entrySequenceNo(a);
		var bs = entrySequenceNo(b);
		if (as !== bs) return bs - as;
		return String(b || "").localeCompare(String(a || ""));
	}
	function lineRate(rate, qty, amount) {
		var r = num(rate);
		var q = num(qty);
		var a = num(amount);
		if (r > 0) return r;
		if (q > 0) return a / q;
		return 0;
	}
	function applyReportRateProcessFix(rows) {
		var master = state && state.entryMeta ? state.entryMeta.masterProcessRows || [] : [];
		if (!master.length || !rows || !rows.length) return;
		var grouped = {};
		master.forEach(function (item) {
			var product = String((item && item.item) || "").trim();
			var processType = String((item && item.process_type) || "").trim();
			if (!product || !processType) return;
			var key = product + "||" + processType;
			if (!grouped[key]) grouped[key] = [];
			grouped[key].push({
				employee: String((item && item.employee) || "").trim(),
				process_size: String((item && item.process_size) || "").trim() || "No Size",
				rate: num(item && item.rate),
			});
		});
		(rows || []).forEach(function (row) {
			var product = String((row && row.product) || "").trim();
			var processType = String((row && row.process_type) || "").trim();
			if (!product || !processType) return;
			var key = product + "||" + processType;
			var candidates = grouped[key] || [];
			if (!candidates.length) return;
			var employee = String((row && row.employee) || "").trim();
			var exactEmp = employee
				? candidates.filter(function (x) {
						return String(x.employee || "") === employee;
				  })
				: [];
			var scoped = exactEmp.length ? exactEmp : candidates;
			var rowSize = String((row && row.process_size) || "").trim() || "No Size";
			var chosen = null;
			if (rowSize && rowSize !== "No Size") {
				chosen =
					scoped.find(function (x) {
						return String(x.process_size || "").trim() === rowSize;
					}) || null;
			}
			if (!chosen && scoped.length === 1) {
				chosen = scoped[0];
			}
			if (!chosen && rowSize === "No Size") {
				var sizeMap = {};
				scoped.forEach(function (x) {
					sizeMap[String(x.process_size || "No Size")] = 1;
				});
				if (Object.keys(sizeMap).length === 1) chosen = scoped[0];
			}
			if (!chosen) return;
			var existingRate = num(row && row.rate);
			var correctedRate = num(chosen.rate);
			if (
				(!row.process_size || String(row.process_size).trim() === "No Size") &&
				chosen.process_size &&
				existingRate <= 0
			) {
				row.process_size = chosen.process_size;
			}
			// Never overwrite saved/manual rate. Only backfill missing rate.
			if (correctedRate > 0 && existingRate <= 0) {
				row.rate = correctedRate;
			}
			var qty = num(row && row.qty);
			var finalRate = num(row && row.rate);
			if (qty > 0 && finalRate > 0) {
				var correctedAmount = whole(qty * finalRate);
				var existingAmount = num(row && row.amount);
				if (existingAmount <= 0) {
					row.amount = correctedAmount;
				}
			}
		});
	}
	function normalizeReportStatusValues(rows) {
		(rows || []).forEach(function (row) {
			if (!row) return;
			var amount = num(row.amount);
			if (amount < 0) amount = 0;

			var jvName = String(row.jv_entry_no || "").trim();
			var jvStatusRaw = String(row.jv_status || "").trim();
			var jvStatus = jvStatusRaw === "Accounted" ? "Posted" : jvStatusRaw || "Pending";
			var isJVPosted = !!jvName && jvStatus === "Posted";

			var booked = num(row.booked_amount);
			if (booked < 0) booked = 0;
			if (!isJVPosted) booked = 0;
			if (isJVPosted && booked <= 0) booked = amount;
			if (booked > amount) booked = amount;

			var paid = num(row.paid_amount);
			if (paid < 0) paid = 0;
			if (paid > booked) paid = booked;

			var unpaid = num(row.unpaid_amount);
			var calculatedUnpaid = Math.max(booked - paid, 0);
			if (unpaid < 0 || unpaid > booked || Math.abs(unpaid - calculatedUnpaid) > 0.01) {
				unpaid = calculatedUnpaid;
			}
			var unbooked = isJVPosted ? 0 : Math.max(amount - booked, 0);

			var bookingStatus = isJVPosted ? "Booked" : "UnBooked";
			var paymentStatus = "Unpaid";
			if (booked > 0) {
				if (unpaid <= 0.005) paymentStatus = "Paid";
				else if (paid > 0.005) paymentStatus = "Partly Paid";
			}

			row.jv_status = jvStatus;
			row.booking_status = bookingStatus;
			row.payment_status = paymentStatus;
			row.amount = whole(amount);
			row.booked_amount = whole(booked);
			row.paid_amount = whole(paid);
			row.unpaid_amount = whole(unpaid);
			row.unbooked_amount = whole(unbooked);
		});
	}
	function parseDecimalInput(v) {
		var raw = String(v == null ? "" : v)
			.replace(/,/g, "")
			.trim();
		if (!raw) return 0;
		var n = Number(raw);
		return isNaN(n) ? 0 : Math.max(0, Math.round(n * 100) / 100);
	}
	function baseProcessSizeOptions() {
		return ["No Size", "Single", "Double", "King", "Supper King"];
	}
	function getProcessSortRank(product, processType, processSize) {
		var p = String(product || "").trim();
		var t = String(processType || "").trim();
		var s = String(processSize || "").trim() || "No Size";
		if (!t) return 999999;
		var rows = (state.entryMeta && state.entryMeta.masterProcessRows) || [];
		var best = 999999;
		var bestType = 999999;
		rows.forEach(function (r, i) {
			var rp = String((r && r.item) || "").trim();
			var rt = String((r && r.process_type) || "").trim();
			var rs = String((r && r.process_size) || "").trim() || "No Size";
			var rank = parseInt((r && r.idx) || 0, 10);
			if (!rank || rank < 0) rank = i + 1;
			if (p && rp === p && rt === t && rs === s) best = Math.min(best, rank);
			if (p && rp === p && rt === t) bestType = Math.min(bestType, rank);
			if (!p && rt === t && rs === s) best = Math.min(best, rank + 10000);
			if (!p && rt === t) bestType = Math.min(bestType, rank + 10000);
		});
		if (best < 999999) return best;
		if (bestType < 999999) return bestType;
		return 999999;
	}
	function compareByProcessSequence(a, b, productHintA, productHintB) {
		var pa = String(productHintA || (a && a.product) || "").trim();
		var pb = String(productHintB || (b && b.product) || "").trim();
		var ra = getProcessSortRank(pa, a && a.process_type, a && a.process_size);
		var rb = getProcessSortRank(pb, b && b.process_type, b && b.process_size);
		if (ra !== rb) return ra - rb;
		var ta = String((a && a.process_type) || "");
		var tb = String((b && b.process_type) || "");
		if (ta !== tb) return ta.localeCompare(tb);
		var sa = String((a && a.process_size) || "No Size");
		var sb = String((b && b.process_size) || "No Size");
		return sa.localeCompare(sb);
	}
	function isStatusField(fieldname) {
		var f = String(fieldname || "");
		return f === "jv_status" || f === "booking_status" || f === "payment_status";
	}
	function isAmountField(fieldname) {
		var f = String(fieldname || "");
		if (!f) return false;
		if (f === "qty" || f === "rate" || f === "_row_count" || f === "month_no") return false;
		if (f.indexOf("m_") === 0) return true;
		if (f.indexOf("amount") >= 0) return true;
		if (f === "opening_balance" || f === "closing_balance" || f === "advance_balance")
			return true;
		return false;
	}
	function statusBadgeHtml(value) {
		var txt = String(value || "").trim();
		if (!txt) return "";
		var k = txt.toLowerCase();
		var cls = "pp-status-neutral";
		if (k === "paid" || k === "posted" || k === "booked") cls = "pp-status-good";
		else if (k === "partly paid" || k === "partly booked") cls = "pp-status-warn";
		else if (k === "unpaid" || k === "unbooked" || k === "pending") cls = "pp-status-bad";
		else if (k === "cancelled" || k === "canceled") cls = "pp-status-neutral";
		return "<span class='pp-status-badge " + cls + "'>" + esc(txt) + "</span>";
	}
	function getSearchTerm() {
		var input = el("pp-search-any");
		return String((input && input.value) || "")
			.trim()
			.toLowerCase();
	}
	function filterRowsByColumns(rows, columns) {
		var term = getSearchTerm();
		if (!term) return rows || [];
		return (rows || []).filter(function (r) {
			var parts = [];
			(columns || []).forEach(function (c) {
				var v = r[c.fieldname];
				if (v === undefined || v === null) return;
				parts.push(String(v));
			});
			return parts.join(" ").toLowerCase().indexOf(term) >= 0;
		});
	}
	function filterRowsByKeys(rows, keys) {
		var term = getSearchTerm();
		if (!term) return rows || [];
		return (rows || []).filter(function (r) {
			var parts = [];
			(keys || []).forEach(function (k) {
				var v = r[k];
				if (v === undefined || v === null) return;
				parts.push(String(v));
			});
			return parts.join(" ").toLowerCase().indexOf(term) >= 0;
		});
	}
	function filterRenderedTablesBySearch() {
		var term = getSearchTerm();
		var wrap = el("pp-table-wrap");
		if (!wrap) return;
		wrap.querySelectorAll("table.pp-table tbody tr").forEach(function (tr) {
			if (!term) {
				tr.style.display = "";
				return;
			}
			var txt = String(tr.textContent || "").toLowerCase();
			tr.style.display = txt.indexOf(term) >= 0 ? "" : "none";
		});
	}
	function avgRate(q, a) {
		q = num(q);
		a = num(a);
		return q ? a / q : 0;
	}
	function employeeLabel(row) {
		if (!row) return "";
		return (row.name1 || row.employee || "").trim();
	}
	function currentCompanyLabel() {
		var jv = el("pp-jv-company");
		var pay = el("pp-pay-company");
		var company = (jv && jv.value) || (pay && pay.value) || "";
		if (company) return String(company);
		var row = (state.rows || [])[0] || {};
		return String(row.company || "");
	}
	function currentDateRangeLabel() {
		var from = (el("pp-from-date") && el("pp-from-date").value) || "";
		var to = (el("pp-to-date") && el("pp-to-date").value) || "";
		if (from && to) return from + " to " + to;
		return from || to || "";
	}
	function getCurrentTabLabel() {
		var btn = document.querySelector(".pp-tab.active");
		if (btn) return String(btn.textContent || "").trim();
		return String(state.currentTab || "");
	}
	function setSummaryHeading(text) {
		var titleEl = document.querySelector("#pp-summary-modal .pp-modal-title");
		if (titleEl) titleEl.textContent = text || "Per Piece Salary Summary";
	}
	function summaryHeaderHtml(heading, subtitleText) {
		var company = currentCompanyLabel();
		var dateRange = currentDateRangeLabel();
		var html =
			"<div class='pp-inline-summary-header' style='margin-bottom:12px;border-bottom:2px solid #cbd5e1;padding-bottom:8px;'>";
		html +=
			"<div style='font-size:22px;font-weight:800;color:#0f172a;'>" +
			esc(company || "Company") +
			"</div>";
		if (dateRange) {
			html +=
				"<div style='font-size:12px;color:#64748b;margin-top:2px;'>Date: " +
				esc(dateRange) +
				"</div>";
		}
		html += "</div>";
		return html;
	}
	function setSummaryModal(heading, subtitleText, bodyHtml) {
		var modal = el("pp-summary-modal");
		var subtitle = el("pp-summary-subtitle");
		var content = el("pp-summary-content");
		if (!modal || !subtitle || !content) return;
		setSummaryHeading(heading || "Per Piece Salary Summary");
		subtitle.textContent = subtitleText || "";
		content.innerHTML = bodyHtml || "";
		state.summaryPrintMeta = {
			heading: heading || "Per Piece Salary Summary",
			subtitle: subtitleText || "",
			company: currentCompanyLabel(),
			date_range: currentDateRangeLabel(),
		};
		modal.style.display = "flex";
	}

	window.PerPieceReportCore = {
		state: state,
		el: el,
		esc: esc,
		num: num,
		whole: whole,
		fmt: fmt,
		isGuestSession: isGuestSession,
		redirectToLogin: redirectToLogin,
		ensureLoggedInOrRedirect: ensureLoggedInOrRedirect,
		entrySequenceNo: entrySequenceNo,
		compareEntryNoDesc: compareEntryNoDesc,
		lineRate: lineRate,
		applyReportRateProcessFix: applyReportRateProcessFix,
		normalizeReportStatusValues: normalizeReportStatusValues,
		parseDecimalInput: parseDecimalInput,
		baseProcessSizeOptions: baseProcessSizeOptions,
		getProcessSortRank: getProcessSortRank,
		compareByProcessSequence: compareByProcessSequence,
		isStatusField: isStatusField,
		isAmountField: isAmountField,
		statusBadgeHtml: statusBadgeHtml,
		getSearchTerm: getSearchTerm,
		filterRowsByColumns: filterRowsByColumns,
		filterRowsByKeys: filterRowsByKeys,
		filterRenderedTablesBySearch: filterRenderedTablesBySearch,
		avgRate: avgRate,
		employeeLabel: employeeLabel,
		currentCompanyLabel: currentCompanyLabel,
		currentDateRangeLabel: currentDateRangeLabel,
		getCurrentTabLabel: getCurrentTabLabel,
		setSummaryHeading: setSummaryHeading,
		summaryHeaderHtml: summaryHeaderHtml,
		setSummaryModal: setSummaryModal,
	};
})();
