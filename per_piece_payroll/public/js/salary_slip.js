function escapeHtml(value) {
	return String(value == null ? "" : value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

function formatNumber(value) {
	return frappe.format(
		value || 0,
		{ fieldtype: "Float", precision: 2 },
		{ always_show_decimals: true }
	);
}

function renderOvertimeReport(frm, rows) {
	const wrapper =
		frm.fields_dict.custom_overtime_report && frm.fields_dict.custom_overtime_report.$wrapper;
	if (!wrapper) {
		return;
	}

	wrapper.empty();

	const data = Array.isArray(rows) ? rows : [];
	if (!frm.doc.employee || !frm.doc.start_date || !frm.doc.end_date) {
		wrapper.html(
			'<div class="text-muted" style="padding: 12px 0;">Select employee, start date, and end date to load overtime.</div>'
		);
		return;
	}

	if (!data.length) {
		wrapper.html(
			'<div class="text-muted" style="padding: 12px 0;">No overtime found for the selected period.</div>'
		);
		return;
	}

	const body = data
		.map((row) => {
			return `
				<tr>
					<td>${escapeHtml(row.date || "")}</td>
					<td>${escapeHtml(row.overtime_no || "")}</td>
					<td style="text-align:right;">${formatNumber(row.qty)}</td>
					<td style="text-align:right;">${formatNumber(row.hours)}</td>
					<td style="text-align:right;">${formatNumber(row.hourly_rate)}</td>
					<td style="text-align:right;">${formatNumber(row.amount)}</td>
				</tr>
			`;
		})
		.join("");

	wrapper.append(`
		<div id="salary_slip_overtime_table" style="padding-top: 8px; overflow-x: auto;">
			<table class="table table-bordered" style="margin-bottom: 0;">
				<thead>
					<tr>
						<th>Date</th>
						<th>OT No</th>
						<th style="text-align:right;">Qty</th>
						<th style="text-align:right;">Hours</th>
						<th style="text-align:right;">Hourly Rate</th>
						<th style="text-align:right;">Amount</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`);
}

function setOvertimeTotals(frm, rows) {
	const data = Array.isArray(rows) ? rows : [];
	const totalHours = data.reduce((sum, row) => sum + flt(row.hours), 0);
	const totalQty = data.reduce((sum, row) => sum + flt(row.qty), 0);

	if (flt(frm.doc.custom_total_overtime_hours) !== totalHours) {
		frm.set_value("custom_total_overtime_hours", totalHours);
	}
	if (flt(frm.doc.custom_total_overtime_qty) !== totalQty) {
		frm.set_value("custom_total_overtime_qty", totalQty);
	}
}

function clearOvertimeDisplay(frm) {
	setOvertimeTotals(frm, []);
	renderOvertimeReport(frm, []);
}

function loadOvertimeDisplay(frm) {
	if (!frm.fields_dict.custom_overtime_report) {
		return;
	}

	if (!frm.doc.employee || !frm.doc.start_date || !frm.doc.end_date) {
		clearOvertimeDisplay(frm);
		return;
	}

	frappe.call({
		method: "get_overtime_report",
		args: {
			employee: frm.doc.employee,
			start_date: frm.doc.start_date,
			end_date: frm.doc.end_date,
		},
		callback: function (response) {
			const rows = response.message || [];
			setOvertimeTotals(frm, rows);
			renderOvertimeReport(frm, rows);
		},
		error: function () {
			const wrapper =
				frm.fields_dict.custom_overtime_report &&
				frm.fields_dict.custom_overtime_report.$wrapper;
			if (wrapper) {
				wrapper.html(
					'<div class="text-danger" style="padding: 12px 0;">Unable to load overtime report.</div>'
				);
			}
		},
	});
}

frappe.ui.form.on("Salary Slip", {
	refresh(frm) {
		loadOvertimeDisplay(frm);
	},
	employee(frm) {
		loadOvertimeDisplay(frm);
	},
	start_date(frm) {
		loadOvertimeDisplay(frm);
	},
	end_date(frm) {
		loadOvertimeDisplay(frm);
	},
});
