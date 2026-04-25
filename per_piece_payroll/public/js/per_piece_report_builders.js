(function () {
	function create(deps) {
		var state = deps.state;
		var el = deps.el;
		var num = deps.num;
		var avgRate = deps.avgRate;
		var compareByProcessSequence = deps.compareByProcessSequence;
		var parseDateOnly = deps.parseDateOnly;
		var pad2 = deps.pad2;
		var getReportArgs = deps.getReportArgs;
		var advanceMonthField = deps.advanceMonthField;

		function groupRows(rows, keys, builder) {
			var map = {};
			function cleanGroupAmount(v) {
				var out = Math.round(num(v) * 100) / 100;
				return Math.abs(out) < 0.005 ? 0 : out;
			}
			function resolveBookedPaidUnpaid(row) {
				var amount = num(row.amount);
				var bookingStatus = String(row.booking_status || "");
				var jvPosted = !!(
					(row.jv_entry_no || "") &&
					String(row.jv_status || "") === "Posted"
				);
				var isBooked = bookingStatus === "Booked" || jvPosted;
				var bookedVal = isBooked ? amount : 0;
				if (!jvPosted) {
					isBooked = false;
					bookedVal = 0;
				}

				var paidVal = num(row.paid_amount);
				if (paidVal < 0) paidVal = 0;
				if (paidVal > bookedVal) paidVal = bookedVal;

				var unpaidVal = num(row.unpaid_amount);
				if (unpaidVal <= 0 || unpaidVal > bookedVal) {
					unpaidVal = Math.max(bookedVal - paidVal, 0);
				}

				return {
					booked: cleanGroupAmount(bookedVal),
					paid: cleanGroupAmount(paidVal),
					unpaid: cleanGroupAmount(unpaidVal),
					is_booked: isBooked,
				};
			}
			(rows || []).forEach(function (r) {
				var key = keys
					.map(function (k) {
						return r[k] || "";
					})
					.join("||");
				if (!map[key]) map[key] = builder(r);
				if (map[key].booked_amount === undefined) map[key].booked_amount = 0;
				if (map[key].unbooked_amount === undefined) map[key].unbooked_amount = 0;
				if (map[key].paid_amount === undefined) map[key].paid_amount = 0;
				if (map[key].unpaid_amount === undefined) map[key].unpaid_amount = 0;
				if (map[key]._row_count === undefined) map[key]._row_count = 0;
				if (map[key]._booked_count === undefined) map[key]._booked_count = 0;
				if (map[key]._paid_count === undefined) map[key]._paid_count = 0;
				if (map[key]._unpaid_count === undefined) map[key]._unpaid_count = 0;
				if (map[key]._partly_count === undefined) map[key]._partly_count = 0;

				map[key]._row_count += 1;
				map[key].qty = num(map[key].qty) + num(r.qty);
				map[key].amount = num(map[key].amount) + num(r.amount);
				var amounts = resolveBookedPaidUnpaid(r);
				var bookedVal = amounts.booked;
				var paidVal = amounts.paid;
				var unpaidVal = amounts.unpaid;

				map[key].booked_amount = num(map[key].booked_amount) + bookedVal;
				map[key].unbooked_amount = cleanGroupAmount(
					num(map[key].unbooked_amount) + Math.max(num(r.amount) - bookedVal, 0)
				);
				map[key].paid_amount = num(map[key].paid_amount) + paidVal;
				map[key].unpaid_amount = num(map[key].unpaid_amount) + unpaidVal;

				var isBooked = amounts.is_booked;
				if (isBooked) map[key]._booked_count += 1;
				var payStatus = String(r.payment_status || "Unpaid");
				if (payStatus === "Paid") map[key]._paid_count += 1;
				else if (payStatus === "Partly Paid") map[key]._partly_count += 1;
				else map[key]._unpaid_count += 1;
			});
			return Object.keys(map)
				.sort()
				.map(function (k) {
					map[k].amount = cleanGroupAmount(map[k].amount);
					map[k].booked_amount = cleanGroupAmount(map[k].booked_amount);
					map[k].paid_amount = cleanGroupAmount(map[k].paid_amount);
					map[k].unpaid_amount = cleanGroupAmount(map[k].unpaid_amount);
					map[k].rate = avgRate(map[k].qty, map[k].amount);
					map[k].unbooked_amount = cleanGroupAmount(
						Math.max(num(map[k].amount) - num(map[k].booked_amount), 0)
					);
					if (map[k]._booked_count === map[k]._row_count)
						map[k].booking_status = "Booked";
					else if (map[k]._booked_count === 0) map[k].booking_status = "UnBooked";
					else map[k].booking_status = "Partly Booked";

					if (map[k]._paid_count === map[k]._row_count) map[k].payment_status = "Paid";
					else if (map[k]._unpaid_count === map[k]._row_count)
						map[k].payment_status = "Unpaid";
					else map[k].payment_status = "Partly Paid";
					return map[k];
				});
		}

		function buildEmployeeSummaryRows(rows) {
			var map = {};
			(rows || []).forEach(function (r) {
				var employee = String(r.employee || "").trim();
				var name1 = String(r.name1 || "").trim();
				var key = employee + "||" + name1;
				if (!map[key]) {
					map[key] = {
						employee: employee,
						name1: name1,
						qty: 0,
						amount: 0,
						rate: 0,
						source_count: 0,
						source_entries: [],
					};
				}
				map[key].qty += num(r.qty);
				map[key].amount += num(r.amount);
				map[key].source_count += 1;
				map[key].source_entries.push({
					per_piece_salary: r.per_piece_salary || "",
					po_number: r.po_number || "",
					sales_order: r.sales_order || "",
					qty: num(r.qty),
					amount: num(r.amount),
				});
			});
			return Object.keys(map)
				.sort()
				.map(function (key) {
					var row = map[key];
					row.rate = avgRate(row.qty, row.amount);
					return row;
				});
		}

		function buildEmployeeSummaryReportRows(rows) {
			var map = {};
			function clean(v) {
				var out = Math.round(num(v) * 100) / 100;
				return Math.abs(out) < 0.005 ? 0 : out;
			}
			(rows || []).forEach(function (r) {
				var employee = String(r.employee || "").trim();
				var name1 = String(r.name1 || "").trim();
				var key = employee + "||" + name1;
				if (!map[key]) {
					map[key] = {
						employee: employee,
						name1: name1,
						qty: 0,
						amount: 0,
						rate: 0,
						booked_amount: 0,
						unbooked_amount: 0,
						paid_amount: 0,
						unpaid_amount: 0,
						_booked_count: 0,
						_paid_count: 0,
						_unpaid_count: 0,
						_row_count: 0,
						source_count: 0,
						source_entries: [],
					};
				}
				var item = map[key];
				item.qty += num(r.qty);
				item.amount += num(r.amount);
				item._row_count += 1;

				var amount = num(r.amount);
				var bookingStatus = String(r.booking_status || "");
				var jvPosted = !!((r.jv_entry_no || "") && String(r.jv_status || "") === "Posted");
				var isBooked = bookingStatus === "Booked" || jvPosted;
				var bookedVal = isBooked ? amount : 0;
				if (!jvPosted) {
					isBooked = false;
					bookedVal = 0;
				}
				var paidVal = num(r.paid_amount);
				if (paidVal < 0) paidVal = 0;
				if (paidVal > bookedVal) paidVal = bookedVal;
				var unpaidVal = num(r.unpaid_amount);
				if (unpaidVal <= 0 || unpaidVal > bookedVal) {
					unpaidVal = Math.max(bookedVal - paidVal, 0);
				}

				item.booked_amount += clean(bookedVal);
				item.unbooked_amount += clean(Math.max(amount - bookedVal, 0));
				item.paid_amount += clean(paidVal);
				item.unpaid_amount += clean(unpaidVal);
				if (bookedVal > 0) item._booked_count += 1;
				if (String(r.payment_status || "") === "Paid") item._paid_count += 1;
				else item._unpaid_count += 1;

				item.source_count += 1;
				item.source_entries.push({
					per_piece_salary: r.per_piece_salary || "",
					from_date: r.from_date || "",
					to_date: r.to_date || "",
					po_number: r.po_number || "",
					sales_order: r.sales_order || "",
					booking_status: r.booking_status || (isBooked ? "Booked" : "UnBooked"),
					payment_status: r.payment_status || "Unpaid",
					booked_amount: clean(bookedVal),
					unbooked_amount: clean(Math.max(amount - bookedVal, 0)),
					paid_amount: clean(paidVal),
					unpaid_amount: clean(unpaidVal),
					qty: num(r.qty),
					amount: num(r.amount),
				});
			});
			return Object.keys(map)
				.sort()
				.map(function (key) {
					var item = map[key];
					item.rate = avgRate(item.qty, item.amount);
					if (item._booked_count === item._row_count) item.booking_status = "Booked";
					else if (item._booked_count > 0) item.booking_status = "Partly Booked";
					else item.booking_status = "UnBooked";
					if (item._paid_count === item._row_count) item.payment_status = "Paid";
					else if (item._paid_count > 0 && item._unpaid_count > 0)
						item.payment_status = "Partly Paid";
					else item.payment_status = "Unpaid";
					return item;
				});
		}

		function buildEmployeeItemWiseReportRows(rows) {
			var byEmployee = {};
			var employeeOrder = [];
			(rows || []).forEach(function (r) {
				var emp = String(r.employee || "").trim();
				var name = String(r.name1 || "").trim() || emp || "Unknown Employee";
				var key = emp + "||" + name;
				if (!byEmployee[key]) {
					byEmployee[key] = {
						employee: emp,
						name1: name,
						details: [],
						subtotal: { qty: 0, amount: 0 },
					};
					employeeOrder.push(key);
				}
				byEmployee[key].details.push({
					per_piece_salary: r.per_piece_salary || "",
					po_number: r.po_number || "",
					product: r.product || "",
					process_type: r.process_type || "",
					process_size: r.process_size || "No Size",
					qty: num(r.qty),
					rate: num(r.rate),
					amount: num(r.amount),
					booking_status: r.booking_status || "",
					payment_status: r.payment_status || "",
					jv_entry_no: r.jv_entry_no || "",
					payment_jv_no: r.payment_jv_no || "",
				});
				byEmployee[key].subtotal.qty += num(r.qty);
				byEmployee[key].subtotal.amount += num(r.amount);
			});

			employeeOrder.sort(function (a, b) {
				var an = String((byEmployee[a] && byEmployee[a].name1) || a);
				var bn = String((byEmployee[b] && byEmployee[b].name1) || b);
				return an.localeCompare(bn);
			});

			var out = [];
			employeeOrder.forEach(function (key) {
				var group = byEmployee[key];
				out.push({
					_group_header: 1,
					_group_label:
						"Employee: " +
						(group.name1 || group.employee || "Unknown") +
						(group.employee ? " (" + group.employee + ")" : ""),
				});
				(group.details || [])
					.sort(function (a, b) {
						var ce = String(b.per_piece_salary || "").localeCompare(
							String(a.per_piece_salary || "")
						);
						if (ce !== 0) return ce;
						var pi = String(a.product || "").localeCompare(String(b.product || ""));
						if (pi !== 0) return pi;
						return compareByProcessSequence(a, b, a.product || "", b.product || "");
					})
					.forEach(function (d) {
						out.push(d);
					});
				out.push({
					_is_total: 1,
					per_piece_salary: "Employee Sub Total",
					qty: group.subtotal.qty,
					rate: avgRate(group.subtotal.qty, group.subtotal.amount),
					amount: group.subtotal.amount,
				});
			});
			return out;
		}

		function normalizeBookedAmounts(row) {
			var amount = num(row && row.amount);
			var bookedVal = num(row && row.booked_amount);
			if (bookedVal < 0) bookedVal = 0;
			if (bookedVal > amount) bookedVal = amount;
			var paidVal = num(row && row.paid_amount);
			if (paidVal < 0) paidVal = 0;
			if (paidVal > bookedVal) paidVal = bookedVal;
			var unpaidVal = num(row && row.unpaid_amount);
			if (unpaidVal < 0 || unpaidVal > bookedVal)
				unpaidVal = Math.max(bookedVal - paidVal, 0);
			var unbookedVal = Math.max(amount - bookedVal, 0);
			return {
				amount: amount,
				booked_amount: bookedVal,
				paid_amount: paidVal,
				unpaid_amount: unpaidVal,
				unbooked_amount: unbookedVal,
			};
		}

		function buildProductSummaryDetailRows(rows) {
			var byProduct = {};
			var productOrder = [];
			(rows || []).forEach(function (r) {
				var product = String(r.product || "").trim() || "No Product";
				if (!byProduct[product]) {
					byProduct[product] = {
						details: [],
						subtotal: {
							qty: 0,
							amount: 0,
							unbooked_amount: 0,
							booked_amount: 0,
							paid_amount: 0,
							unpaid_amount: 0,
						},
					};
					productOrder.push(product);
				}
				var amt = normalizeBookedAmounts(r);
				byProduct[product].details.push({
					per_piece_salary: r.per_piece_salary || "",
					product: product,
					process_type: r.process_type || "",
					process_size: r.process_size || "No Size",
					qty: num(r.qty),
					rate: num(r.rate),
					amount: amt.amount,
					unbooked_amount: amt.unbooked_amount,
					booked_amount: amt.booked_amount,
					paid_amount: amt.paid_amount,
					unpaid_amount: amt.unpaid_amount,
					booking_status: r.booking_status || "",
					payment_status: r.payment_status || "",
				});
				byProduct[product].subtotal.qty += num(r.qty);
				byProduct[product].subtotal.amount += amt.amount;
				byProduct[product].subtotal.unbooked_amount += amt.unbooked_amount;
				byProduct[product].subtotal.booked_amount += amt.booked_amount;
				byProduct[product].subtotal.paid_amount += amt.paid_amount;
				byProduct[product].subtotal.unpaid_amount += amt.unpaid_amount;
			});

			productOrder.sort();
			var out = [];
			productOrder.forEach(function (product) {
				var group = byProduct[product];
				out.push({ _group_header: 1, _group_label: "Product: " + product });
				(group.details || [])
					.sort(function (a, b) {
						var ce = String(b.per_piece_salary || "").localeCompare(
							String(a.per_piece_salary || "")
						);
						if (ce !== 0) return ce;
						return compareByProcessSequence(a, b, a.product || "", b.product || "");
					})
					.forEach(function (d) {
						out.push(d);
					});
				out.push({
					_is_total: 1,
					per_piece_salary: "Product Sub Total",
					product: product,
					qty: group.subtotal.qty,
					rate: avgRate(group.subtotal.qty, group.subtotal.amount),
					amount: group.subtotal.amount,
					unbooked_amount: group.subtotal.unbooked_amount,
					booked_amount: group.subtotal.booked_amount,
					paid_amount: group.subtotal.paid_amount,
					unpaid_amount: group.subtotal.unpaid_amount,
				});
			});
			return out;
		}

		function buildProcessSummaryRows(rows) {
			var byProcess = {};
			var processOrder = [];
			(rows || []).forEach(function (r) {
				var processType = String(r.process_type || "").trim() || "No Process";
				if (!byProcess[processType]) {
					byProcess[processType] = {
						details: [],
						subtotal: {
							qty: 0,
							amount: 0,
							unbooked_amount: 0,
							booked_amount: 0,
							paid_amount: 0,
							unpaid_amount: 0,
						},
					};
					processOrder.push(processType);
				}
				var amt = normalizeBookedAmounts(r);
				byProcess[processType].details.push({
					per_piece_salary: r.per_piece_salary || "",
					process_type: processType,
					process_size: r.process_size || "No Size",
					qty: num(r.qty),
					rate: num(r.rate),
					amount: amt.amount,
					unbooked_amount: amt.unbooked_amount,
					booked_amount: amt.booked_amount,
					paid_amount: amt.paid_amount,
					unpaid_amount: amt.unpaid_amount,
					booking_status: r.booking_status || "",
					payment_status: r.payment_status || "",
				});
				byProcess[processType].subtotal.qty += num(r.qty);
				byProcess[processType].subtotal.amount += amt.amount;
				byProcess[processType].subtotal.unbooked_amount += amt.unbooked_amount;
				byProcess[processType].subtotal.booked_amount += amt.booked_amount;
				byProcess[processType].subtotal.paid_amount += amt.paid_amount;
				byProcess[processType].subtotal.unpaid_amount += amt.unpaid_amount;
			});

			processOrder.sort();
			var out = [];
			processOrder.forEach(function (processType) {
				var group = byProcess[processType];
				out.push({ _group_header: 1, _group_label: "Process: " + processType });
				(group.details || [])
					.sort(function (a, b) {
						var ce = String(b.per_piece_salary || "").localeCompare(
							String(a.per_piece_salary || "")
						);
						if (ce !== 0) return ce;
						return compareByProcessSequence(a, b, "", "");
					})
					.forEach(function (d) {
						out.push(d);
					});
				out.push({
					_is_total: 1,
					per_piece_salary: "Process Sub Total",
					process_type: processType,
					qty: group.subtotal.qty,
					rate: avgRate(group.subtotal.qty, group.subtotal.amount),
					amount: group.subtotal.amount,
					unbooked_amount: group.subtotal.unbooked_amount,
					booked_amount: group.subtotal.booked_amount,
					paid_amount: group.subtotal.paid_amount,
					unpaid_amount: group.subtotal.unpaid_amount,
				});
			});
			return out;
		}

		function monthFieldFromKey(key) {
			return "m_" + String(key || "").replace("-", "_");
		}

		function monthLabelFromKey(key) {
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
			var k = String(key || "");
			if (!k || k.length < 7) return k;
			var yy = k.slice(2, 4);
			var mm = parseInt(k.slice(5, 7), 10) || 0;
			return (monthNames[mm - 1] || k.slice(5, 7)) + "-" + yy;
		}

		function monthsInFilterRange() {
			var args = getReportArgs();
			var fromDate = parseDateOnly(args.from_date || "");
			var toDate = parseDateOnly(args.to_date || "");
			if (!fromDate || !toDate) return [];
			if (fromDate > toDate) {
				var temp = fromDate;
				fromDate = toDate;
				toDate = temp;
			}
			var out = [];
			var y = fromDate.getFullYear();
			var m = fromDate.getMonth();
			var ey = toDate.getFullYear();
			var em = toDate.getMonth();
			while (y < ey || (y === ey && m <= em)) {
				var key = String(y) + "-" + pad2(m + 1);
				out.push({ key: key, label: monthLabelFromKey(key) });
				m += 1;
				if (m > 11) {
					m = 0;
					y += 1;
				}
			}
			return out;
		}

		function buildSimpleMonthColumns(rows) {
			var map = {};
			(monthsInFilterRange() || []).forEach(function (m) {
				map[m.key] = { key: m.key, label: m.label };
			});
			(rows || []).forEach(function (r) {
				var dt = parseDateOnly(r.to_date || r.from_date);
				if (!dt) return;
				var key = String(dt.getFullYear()) + "-" + pad2(dt.getMonth() + 1);
				if (!map[key]) map[key] = { key: key, label: monthLabelFromKey(key) };
			});
			return Object.keys(map)
				.sort()
				.map(function (k) {
					return map[k];
				});
		}

		function buildSimpleMonthRows(rows, monthCols) {
			var map = {};
			function clean(v) {
				var out = Math.round(num(v) * 100) / 100;
				return Math.abs(out) < 0.005 ? 0 : out;
			}

			(rows || []).forEach(function (r) {
				var emp = String(r.employee || "").trim();
				var name = String(r.name1 || "").trim() || emp;
				if (!emp && !name) return;
				var keyEmp = emp || name;
				if (!map[keyEmp]) {
					map[keyEmp] = { employee: emp, name1: name || keyEmp };
					(monthCols || []).forEach(function (m) {
						map[keyEmp][monthFieldFromKey(m.key)] = 0;
					});
				}
				var dt = parseDateOnly(r.to_date || r.from_date);
				if (!dt) return;
				var monthKey = String(dt.getFullYear()) + "-" + pad2(dt.getMonth() + 1);
				var field = monthFieldFromKey(monthKey);
				if (map[keyEmp][field] === undefined) map[keyEmp][field] = 0;
				map[keyEmp][field] = clean(num(map[keyEmp][field]) + num(r.amount));
			});

			return Object.keys(map)
				.sort(function (a, b) {
					var an = String(map[a].name1 || a);
					var bn = String(map[b].name1 || b);
					if (an < bn) return -1;
					if (an > bn) return 1;
					return 0;
				})
				.map(function (k) {
					return map[k];
				});
		}

		function buildEmployeeMonthYearRows(rows) {
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
			var monthMap = {};
			var subtotalMap = {};
			function cleanAmount(v) {
				var out = Math.round(num(v) * 100) / 100;
				return Math.abs(out) < 0.005 ? 0 : out;
			}

			function ensureStats(target) {
				if (target._row_count === undefined) target._row_count = 0;
				if (target._booked_count === undefined) target._booked_count = 0;
				if (target._paid_count === undefined) target._paid_count = 0;
				if (target._unpaid_count === undefined) target._unpaid_count = 0;
				if (target._partly_count === undefined) target._partly_count = 0;
			}

			function resolveAmounts(row) {
				var amount = num(row.amount);
				var bookingStatus = String(row.booking_status || "");
				var jvPosted = !!(
					(row.jv_entry_no || "") &&
					String(row.jv_status || "") === "Posted"
				);
				var isBooked = bookingStatus === "Booked" || jvPosted;
				var bookedVal = isBooked ? amount : 0;
				if (!jvPosted) {
					isBooked = false;
					bookedVal = 0;
				}

				var paidVal = num(row.paid_amount);
				if (paidVal < 0) paidVal = 0;
				if (paidVal > bookedVal) paidVal = bookedVal;

				var unpaidVal = num(row.unpaid_amount);
				if (unpaidVal <= 0 || unpaidVal > bookedVal) {
					unpaidVal = Math.max(bookedVal - paidVal, 0);
				}

				return {
					booked: cleanAmount(bookedVal),
					paid: cleanAmount(paidVal),
					unpaid: cleanAmount(unpaidVal),
					is_booked: isBooked,
				};
			}

			function addStats(target, row, bookedVal, paidVal, unpaidVal) {
				ensureStats(target);
				target._row_count += 1;
				target.qty = num(target.qty) + num(row.qty);
				target.amount = num(target.amount) + num(row.amount);
				target.booked_amount = num(target.booked_amount) + bookedVal;
				var unbookedVal = num(row.amount) - bookedVal;
				if (unbookedVal < 0) unbookedVal = 0;
				target.unbooked_amount = cleanAmount(num(target.unbooked_amount) + unbookedVal);
				target.paid_amount = num(target.paid_amount) + paidVal;
				target.unpaid_amount = num(target.unpaid_amount) + unpaidVal;

				var isBooked =
					String(row.booking_status || "") === "Booked" ||
					((row.jv_entry_no || "") && String(row.jv_status || "") === "Posted");
				if (isBooked) target._booked_count += 1;

				var payStatus = String(row.payment_status || "Unpaid");
				if (payStatus === "Paid") target._paid_count += 1;
				else if (payStatus === "Partly Paid") target._partly_count += 1;
				else target._unpaid_count += 1;
			}

			function finalizeStats(target) {
				target.amount = cleanAmount(target.amount);
				target.booked_amount = cleanAmount(target.booked_amount);
				target.paid_amount = cleanAmount(target.paid_amount);
				target.unpaid_amount = cleanAmount(target.unpaid_amount);
				target.rate = avgRate(target.qty, target.amount);
				var unbooked = num(target.amount) - num(target.booked_amount);
				if (unbooked < 0) unbooked = 0;
				target.unbooked_amount = cleanAmount(unbooked);
				if (target._booked_count === target._row_count) target.booking_status = "Booked";
				else if (target._booked_count === 0) target.booking_status = "UnBooked";
				else target.booking_status = "Partly Booked";

				if (target._paid_count === target._row_count) target.payment_status = "Paid";
				else if (target._unpaid_count === target._row_count)
					target.payment_status = "Unpaid";
				else target.payment_status = "Partly Paid";
			}

			(rows || []).forEach(function (r) {
				var emp = String(r.employee || "").trim();
				if (!emp) return;
				var name = String(r.name1 || "").trim() || emp;
				var dt = parseDateOnly(r.to_date || r.from_date);
				if (!dt) return;
				var yy = String(dt.getFullYear());
				var mmNo = dt.getMonth() + 1;
				var mm = pad2(mmNo);
				var mmLabel = monthNames[mmNo - 1] + "-" + yy.slice(-2);

				var resolved = resolveAmounts(r);
				var bookedVal = resolved.booked;
				var paidVal = resolved.paid;
				var unpaidVal = resolved.unpaid;

				var monthKey = emp + "||" + name + "||" + yy + "||" + mm;
				if (!monthMap[monthKey]) {
					monthMap[monthKey] = {
						employee: emp,
						name1: name,
						year: yy,
						month: mmLabel,
						month_year: mmLabel,
						month_no: mmNo,
						period_key: yy + "-" + mm,
						period_type: "Month",
						qty: 0,
						rate: 0,
						amount: 0,
						booked_amount: 0,
						unbooked_amount: 0,
						paid_amount: 0,
						unpaid_amount: 0,
					};
				}
				addStats(monthMap[monthKey], r, bookedVal, paidVal, unpaidVal);

				var subtotalKey = yy + "||" + mm;
				if (!subtotalMap[subtotalKey]) {
					subtotalMap[subtotalKey] = {
						employee: "",
						name1: "Month Sub Total",
						year: yy,
						month: mmLabel,
						month_year: mmLabel + " Sub Total",
						month_no: mmNo,
						period_key: yy + "-" + mm,
						period_type: "Subtotal",
						qty: 0,
						rate: 0,
						amount: 0,
						booked_amount: 0,
						unbooked_amount: 0,
						paid_amount: 0,
						unpaid_amount: 0,
					};
				}
				addStats(subtotalMap[subtotalKey], r, bookedVal, paidVal, unpaidVal);
			});

			var monthRows = Object.keys(monthMap).map(function (k) {
				finalizeStats(monthMap[k]);
				return monthMap[k];
			});

			monthRows.sort(function (a, b) {
				if (String(a.year || "") < String(b.year || "")) return -1;
				if (String(a.year || "") > String(b.year || "")) return 1;
				if (num(a.month_no) < num(b.month_no)) return -1;
				if (num(a.month_no) > num(b.month_no)) return 1;
				var an = String(a.name1 || a.employee || "");
				var bn = String(b.name1 || b.employee || "");
				if (an < bn) return -1;
				if (an > bn) return 1;
				return 0;
			});

			var subtotalByPeriod = {};
			Object.keys(subtotalMap).forEach(function (k) {
				finalizeStats(subtotalMap[k]);
				var row = subtotalMap[k];
				subtotalByPeriod[row.period_key] = row;
			});

			var out = [];
			var lastPeriodKey = "";
			monthRows.forEach(function (r) {
				var key = r.period_key;
				if (lastPeriodKey && key !== lastPeriodKey && subtotalByPeriod[lastPeriodKey]) {
					out.push(subtotalByPeriod[lastPeriodKey]);
				}
				out.push(r);
				lastPeriodKey = key;
			});
			if (lastPeriodKey && subtotalByPeriod[lastPeriodKey]) {
				out.push(subtotalByPeriod[lastPeriodKey]);
			}

			return out;
		}

		function buildMonthPaidUnpaidRows(rows) {
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
			var map = {};
			(rows || []).forEach(function (r) {
				var dt = parseDateOnly(r.to_date || r.from_date);
				if (!dt) return;
				var yy = String(dt.getFullYear());
				var mmNo = dt.getMonth() + 1;
				var mm = pad2(mmNo);
				var key = yy + "-" + mm;
				if (!map[key]) {
					map[key] = {
						month_year: monthNames[mmNo - 1] + "-" + yy.slice(-2),
						period_key: key,
						booked_amount: 0,
						paid_amount: 0,
						unpaid_amount: 0,
					};
				}
				map[key].booked_amount += num(r.booked_amount);
				map[key].paid_amount += num(r.paid_amount);
				map[key].unpaid_amount += num(r.unpaid_amount);
			});

			return Object.keys(map)
				.sort()
				.reverse()
				.map(function (k) {
					var row = map[k];
					row.booked_amount = Math.round(num(row.booked_amount) * 100) / 100;
					row.paid_amount = Math.round(num(row.paid_amount) * 100) / 100;
					row.unpaid_amount = Math.round(num(row.unpaid_amount) * 100) / 100;
					return row;
				});
		}

		function buildAdvanceRows(rows) {
			var map = {};
			var selectedEmployee =
				el("pp-employee") && el("pp-employee").value
					? String(el("pp-employee").value)
					: "";
			var months = state.advanceMonths || [];

			(state.advanceRows || []).forEach(function (r) {
				var emp = String(r.employee || "").trim();
				if (!emp) return;
				if (selectedEmployee && emp !== selectedEmployee) return;
				if (!map[emp]) {
					map[emp] = {
						employee: emp,
						name1: r.name1 || (state.entryMeta.employeeNameMap || {})[emp] || emp,
						branch: r.branch || "",
						opening_balance: num(r.opening_balance),
						closing_balance: num(r.closing_balance || r.advance_balance),
						advance_balance: num(r.advance_balance),
					};
				} else if (!map[emp].name1 && r.name1) {
					map[emp].name1 = r.name1 || map[emp].name1;
				} else {
					map[emp].advance_balance = num(r.advance_balance);
				}
				months.forEach(function (m) {
					var key = m && m.key ? m.key : "";
					if (!key) return;
					var field = advanceMonthField(key);
					map[emp][field] = num((r.month_values || {})[key]);
				});
			});

			return Object.keys(map)
				.sort()
				.map(function (emp) {
					return {
						employee: emp,
						name1: map[emp].name1 || emp,
						branch: map[emp].branch || "",
						opening_balance: num(map[emp].opening_balance),
						closing_balance: num(map[emp].closing_balance || map[emp].advance_balance),
						advance_balance: num(map[emp].advance_balance),
						_raw: map[emp],
					};
				});
		}

		return {
			groupRows: groupRows,
			buildEmployeeSummaryRows: buildEmployeeSummaryRows,
			buildEmployeeSummaryReportRows: buildEmployeeSummaryReportRows,
			buildEmployeeItemWiseReportRows: buildEmployeeItemWiseReportRows,
			normalizeBookedAmounts: normalizeBookedAmounts,
			buildProductSummaryDetailRows: buildProductSummaryDetailRows,
			buildProcessSummaryRows: buildProcessSummaryRows,
			monthFieldFromKey: monthFieldFromKey,
			monthLabelFromKey: monthLabelFromKey,
			monthsInFilterRange: monthsInFilterRange,
			buildSimpleMonthColumns: buildSimpleMonthColumns,
			buildSimpleMonthRows: buildSimpleMonthRows,
			buildEmployeeMonthYearRows: buildEmployeeMonthYearRows,
			buildMonthPaidUnpaidRows: buildMonthPaidUnpaidRows,
			buildAdvanceRows: buildAdvanceRows,
		};
	}

	window.PerPieceBuilders = { create: create };
})();
