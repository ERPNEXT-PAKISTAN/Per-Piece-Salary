window.per_piece_payroll = window.per_piece_payroll || {};

frappe.pages["per-piece-reporting"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Per Piece Reporting"),
		single_column: true,
	});

	wrapper.per_piece_native_page = new window.per_piece_payroll.PerPieceNativePage(wrapper, {
		workspace: "reporting",
		tab: "all",
		title: __("Per Piece Reporting"),
	});

	frappe.breadcrumbs.add("Per Piece Payroll");
};

window.per_piece_payroll.PerPieceNativePage = class PerPieceNativePage {
	constructor(wrapper, options) {
		this.wrapper = wrapper;
		this.page = wrapper.page;
		this.options = options || {};
		this.styleId = "pp-native-reporting-style";
		this.load();
	}

	async load() {
		this.$root = $(this.wrapper).find(".layout-main-section");
		this.$root.html(`<div class="text-muted">${__("Loading Per Piece Reporting...")}</div>`);

		try {
			const response = await frappe.call({
				method: "per_piece_payroll.api.get_per_piece_report_page_payload",
				args: {},
			});
			const payload = response.message || {};
			this.render(payload.html || "");
		} catch (error) {
			this.$root.html(
				`<div class="text-danger">${__("Failed to load page content.")}</div>`
			);
			console.error(error);
		}
	}

	render(html) {
		if (!html) {
			this.$root.html(`<div class="text-warning">${__("No page content found.")}</div>`);
			return;
		}

		const host = document.createElement("div");
		host.className = "pp-native-host";
		host.innerHTML = html;
		window.PER_PIECE_BOOT = {
			workspace: this.options.workspace || "reporting",
			tab: this.options.tab || "all",
		};

		const scripts = Array.from(host.querySelectorAll("script"));
		scripts.forEach((s) => s.remove());

		this.$root.empty();
		this.$root[0].appendChild(host);

		scripts.forEach((oldScript) => {
			const script = document.createElement("script");
			script.type = oldScript.type || "text/javascript";
			if (oldScript.src) {
				script.src = oldScript.src;
			}
			if (oldScript.defer) {
				script.defer = true;
			}
			if (oldScript.async) {
				script.async = true;
			}
			script.text = oldScript.text || oldScript.textContent || "";
			host.appendChild(script);
		});

		this.applyWorkspaceState(0);
	}

	applyWorkspaceState(attempt) {
		if (attempt > 20) {
			return;
		}
		const reportingWorkspace = document.getElementById("pp-workspace-reporting");
		if (!reportingWorkspace) {
			setTimeout(() => this.applyWorkspaceState(attempt + 1), 250);
			return;
		}

		this.injectWorkspaceStyle();
	}

	injectWorkspaceStyle() {
		if (document.getElementById(this.styleId)) {
			return;
		}
		const style = document.createElement("style");
		style.id = this.styleId;
		style.textContent = `
			#pp-workspace-entry { display: none !important; }
			.pp-tab[data-workspace='entry'] { display: none !important; }
		`;
		document.head.appendChild(style);
	}
};
