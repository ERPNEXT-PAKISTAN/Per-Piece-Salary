(function () {
	function create(deps) {
		var el = deps.el;
		var esc = deps.esc;
		var isGuestSession = deps.isGuestSession;
		var redirectToLogin = deps.redirectToLogin;

		function errText(e) {
			if (!e) return "Unknown error";
			if (typeof e === "string") return e;
			if (e._server_messages) {
				try {
					var msgs = JSON.parse(e._server_messages);
					if (Array.isArray(msgs) && msgs.length) {
						var first = String(msgs[0] || "");
						if (first) return first.replace(/<[^>]*>/g, "");
					}
				} catch (x) {
					/* ignore server message parse errors */
				}
			}
			if (e._error_message) return String(e._error_message);
			if (e.message && typeof e.message === "string") return e.message;
			if (e.exc && typeof e.exc === "string") return e.exc;
			if (Array.isArray(e.exc) && e.exc.length) {
				var raw = String(e.exc[0] || "");
				var m = raw.match(/ValidationError:\s*([^\n]+)/);
				if (m && m[1]) return m[1];
				return raw;
			}
			return "Request failed";
		}

		function prettyError(msg) {
			var text = String(msg || "");
			if (text.indexOf("No unposted rows found for selected filters.") >= 0) {
				return "No unbooked salary rows found for current filters. Change date/filter or use Salary Status tab.";
			}
			if (text.indexOf("No booked salary rows found for selected filters.") >= 0) {
				return "No booked salary rows are available for payment in current filters.";
			}
			return text;
		}

		function showResult(resultEl, kind, title, msg) {
			if (!resultEl) return;
			var color = kind === "error" ? "#b91c1c" : "#0f766e";
			var bg = kind === "error" ? "#fef2f2" : "#f0fdf4";
			resultEl.style.color = color;
			resultEl.innerHTML =
				"<div style='border:1px solid " +
				color +
				";background:" +
				bg +
				";border-radius:8px;padding:8px 10px;'><strong>" +
				esc(title || "") +
				"</strong><div style='margin-top:4px;'>" +
				esc(msg || "") +
				"</div></div>";
		}

		function setActionIcon(kind, glyph) {
			var icon = el("pp-action-icon");
			if (!icon) return;
			icon.className =
				"pp-action-icon " +
				(kind === "success"
					? "pp-action-icon-success"
					: kind === "error"
					? "pp-action-icon-error"
					: "pp-action-icon-info");
			icon.textContent = glyph || (kind === "success" ? "✓" : kind === "error" ? "!" : "i");
		}

		function showActionModal(options) {
			var modal = el("pp-action-modal");
			if (!modal) return;
			var opts = options || {};
			if (el("pp-action-title"))
				el("pp-action-title").textContent = String(opts.title || "Action");
			if (el("pp-action-sub"))
				el("pp-action-sub").textContent = String(opts.sub || "Please confirm.");
			if (el("pp-action-message"))
				el("pp-action-message").textContent = String(opts.message || "");
			if (el("pp-action-meta")) el("pp-action-meta").textContent = String(opts.meta || "");
			setActionIcon(opts.kind || "info", opts.glyph || "");
			var buttons = el("pp-action-buttons");
			if (buttons) {
				buttons.innerHTML = "";
				(opts.buttons || []).forEach(function (btn) {
					var b = document.createElement("button");
					b.type = "button";
					b.className = "btn " + String(btn.className || "btn-default");
					b.textContent = String(btn.label || "OK");
					b.addEventListener("click", function () {
						if (typeof btn.onClick === "function") btn.onClick();
					});
					buttons.appendChild(b);
				});
			}
			modal.style.display = "flex";
		}

		function hideActionModal() {
			var modal = el("pp-action-modal");
			if (modal) modal.style.display = "none";
		}

		function confirmActionModal(title, message, okLabel) {
			return new Promise(function (resolve) {
				showActionModal({
					kind: "info",
					title: title || "Confirm Action",
					sub: "site1.frappe.io",
					message: message || "Please confirm.",
					buttons: [
						{
							label: "Cancel",
							className: "btn-default",
							onClick: function () {
								hideActionModal();
								resolve(false);
							},
						},
						{
							label: okLabel || "OK",
							className: "btn-primary",
							onClick: function () {
								hideActionModal();
								resolve(true);
							},
						},
					],
				});
			});
		}

		function notifyActionResult(kind, title, message, jvNo) {
			showActionModal({
				kind: kind === "error" ? "error" : "success",
				title: title || (kind === "error" ? "Failed" : "Success"),
				sub: "site1.frappe.io",
				message: message || "",
				meta: jvNo ? "JV No: " + jvNo : "",
				buttons: [{ label: "Close", className: "btn-default", onClick: hideActionModal }],
			});
		}

		function getCsrfToken() {
			if (typeof frappe !== "undefined" && frappe.csrf_token) return frappe.csrf_token;
			var match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
			return match ? decodeURIComponent(match[1]) : "";
		}

		function encodeArgs(args) {
			return Object.keys(args || {})
				.map(function (k) {
					var value = args[k];
					if (value === undefined || value === null) value = "";
					return encodeURIComponent(k) + "=" + encodeURIComponent(value);
				})
				.join("&");
		}

		function callApi(method, args) {
			var payload = encodeArgs(args || {});
			var mutateMethods = {
				"per_piece_payroll.api.create_per_piece_salary_entry": true,
				"per_piece_payroll.api.create_per_piece_salary_jv": true,
				"per_piece_payroll.api.cancel_per_piece_salary_jv": true,
				"per_piece_payroll.api.create_per_piece_salary_payment_jv": true,
				"per_piece_payroll.api.cancel_per_piece_salary_payment_jv": true,
			};
			var mutate = !!mutateMethods[method];
			var usePost = mutate || payload.length > 1500;
			var url = "/api/method/" + method;
			var fetchOptions = { credentials: "same-origin", method: usePost ? "POST" : "GET" };

			if (usePost) {
				fetchOptions.headers = {
					"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
				};
				var csrf = getCsrfToken();
				if (csrf) fetchOptions.headers["X-Frappe-CSRF-Token"] = csrf;
				fetchOptions.body = payload;
			} else if (payload) {
				url += "?" + payload;
			}

			return fetch(url, fetchOptions)
				.catch(function (networkErr) {
					throw {
						_error_message:
							"Network error: unable to connect to server. Please refresh and try again.",
						message:
							networkErr && networkErr.message
								? networkErr.message
								: "Network request failed",
						network_error: 1,
					};
				})
				.then(function (res) {
					return res
						.json()
						.catch(function () {
							return {};
						})
						.then(function (body) {
							var bodyErrText = String(
								(body && body._error_message) || (body && body.exception) || ""
							);
							var permissionDenied =
								bodyErrText.indexOf("PermissionError") >= 0 ||
								bodyErrText.toLowerCase().indexOf("not permitted") >= 0;
							if (
								(res.status === 401 || res.status === 403 || permissionDenied) &&
								isGuestSession()
							) {
								redirectToLogin();
							}
							if (!res.ok || body.exc || body.exception || body._error_message) {
								throw body;
							}
							return body.message;
						});
				});
		}

		function callGetList(doctype, fields, filters, limit) {
			return callApi("frappe.client.get_list", {
				doctype: doctype,
				fields: JSON.stringify(fields || ["name"]),
				filters: JSON.stringify(filters || {}),
				order_by: "name asc",
				limit_page_length: limit || 500,
			});
		}

		function setOptions(selectEl, rows, valueKey, labelKey, firstLabel) {
			if (!selectEl) return;
			selectEl.innerHTML = "";
			var first = document.createElement("option");
			first.value = "";
			first.textContent = firstLabel || "Select";
			selectEl.appendChild(first);
			(rows || []).forEach(function (r) {
				var opt = document.createElement("option");
				opt.value = r[valueKey];
				opt.textContent = r[labelKey] || r[valueKey];
				selectEl.appendChild(opt);
			});
		}

		return {
			errText: errText,
			prettyError: prettyError,
			showResult: showResult,
			setActionIcon: setActionIcon,
			showActionModal: showActionModal,
			hideActionModal: hideActionModal,
			confirmActionModal: confirmActionModal,
			notifyActionResult: notifyActionResult,
			getCsrfToken: getCsrfToken,
			encodeArgs: encodeArgs,
			callApi: callApi,
			callGetList: callGetList,
			setOptions: setOptions,
		};
	}

	window.PerPieceReportUtils = { create: create };
})();
