frappe.pages["per-piece-payroll"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Per Piece Payroll"),
		single_column: true,
	});

	const route = "/per-piece-report";
	const container = $(
		'<div class="per-piece-payroll-desk-page" style="padding: 0; margin: 0;"></div>',
	).appendTo(page.main);
	const frame = $(
		'<iframe title="Per Piece Payroll" style="width: 100%; min-height: 760px; border: 0; border-radius: 8px; background: #fff;"></iframe>',
	).appendTo(container);
	frame.attr("src", route);

	const resizeFrame = function () {
		const top = container.offset() ? container.offset().top : 200;
		const available = window.innerHeight - top - 24;
		frame.css("height", Math.max(available, 760) + "px");
	};

	page.set_secondary_action(__("Open Full Page"), function () {
		window.open(route, "_blank");
	});

	$(window).on("resize.per_piece_payroll_page", resizeFrame);
	resizeFrame();
};

frappe.pages["per-piece-payroll"].on_page_leave = function () {
	$(window).off("resize.per_piece_payroll_page");
};

