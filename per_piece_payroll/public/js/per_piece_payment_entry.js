frappe.ui.form.on("Per Piece Payment Entry", {
	refresh(frm) {
		if (Number(frm.doc.docstatus || 0) !== 0) {
			return;
		}

		if (String(frm.doc.jv_status || "") === "Cancelled") {
			frm.add_custom_button(__("Reprocess Payment"), () => {
				frappe.confirm(
					__("Reset this payment entry to Draft so it can be posted again?"),
					() => {
						frappe.call({
							method: "per_piece_payroll.api.reopen_per_piece_payment_entry",
							args: {
								payment_entry: frm.doc.name,
							},
							callback: function (r) {
								if (r && r.message && r.message.ok) {
									frappe.show_alert({
										message: __("Payment entry reopened for reprocessing."),
										indicator: "green",
									});
									frm.reload_doc();
								}
							},
						});
					}
				);
			});
		}
	},
});
