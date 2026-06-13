frappe.ui.form.on("Evolution API Settings", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), () => {
				frappe.call({
					method: "frappe_whatsapp_evo.api.test_connection",
					freeze: true,
					freeze_message: __("Testing Evolution API connection..."),
					callback(r) {
						if (r.message) {
							const state = (r.message.instance && r.message.instance.state) || r.message.state;
							if (state === "open") {
								frappe.show_alert({
									message: __("Connection successful! Instance is open."),
									indicator: "green",
								});
							} else if (state) {
								frappe.msgprint({
									title: __("Connection State"),
									indicator: (state === "connecting" || state === "qr") ? "orange" : "red",
									message: __("Instance connection state is: <strong>{0}</strong>", [state]),
								});
							} else {
								frappe.show_alert({
									message: __("Connection tested successfully."),
									indicator: "green",
								});
							}
							frm.reload_doc();
						}
					},
				});
			});

			frm.add_custom_button(__("Fetch Instances"), () => {
				frappe.call({
					method: "frappe_whatsapp_evo.api.fetch_instances",
					freeze: true,
					freeze_message: __("Fetching Evolution API instances..."),
					callback(r) {
						if (r.message && Array.isArray(r.message)) {
							const instances = r.message;
							if (instances.length === 0) {
								frappe.msgprint({
									title: __("Evolution API Instances"),
									message: __("No instances found on the Evolution API server."),
								});
								return;
							}
							let html = `<p>${__("Successfully fetched {0} instances:", [instances.length])}</p>`;
							html += '<table class="table table-bordered table-striped" style="margin-top: 10px;">';
							html += `<thead><tr>
								<th>${__("Instance Name")}</th>
								<th>${__("Status")}</th>
							</tr></thead><tbody>`;
							instances.forEach(row => {
								const inst = (row && typeof row.instance === "object") ? row.instance : row;
								if (!inst) return;
								const name = inst.name || inst.instanceName || inst.instanceId || __("Unknown");
								const status = inst.status || inst.connectionStatus || row.connectionStatus || inst.state || __("N/A");
								let status_badge = "";
								if (status === "open" || status === "CONNECTED") {
									status_badge = `<span class="indicator green">${status}</span>`;
								} else if (status === "connecting" || status === "CONNECTING" || status === "qr" || status === "QRCODE") {
									status_badge = `<span class="indicator orange">${status}</span>`;
								} else {
									status_badge = `<span class="indicator red">${status}</span>`;
								}
								html += `<tr>
									<td><strong>${frappe.utils.escape_html(name)}</strong></td>
									<td>${status_badge}</td>
								</tr>`;
							});
							html += '</tbody></table>';

							frappe.msgprint({
								title: __("Evolution API Instances"),
								message: html,
								wide: true,
							});
						} else {
							frappe.show_alert({
								message: __("No instances found or response format unrecognized."),
								indicator: "orange",
							});
						}
					},
				});
			});

			frm.add_custom_button(__("Configure Webhook"), () => {
				frappe.confirm(
					__(
						"Evolution API normally stores one webhook configuration per instance. This may replace an existing webhook used by another system. Continue?"
					),
					() => {
						frappe.call({
							method: "frappe_whatsapp_evo.api.configure_webhook",
							freeze: true,
							freeze_message: __("Configuring Evolution API webhook..."),
							callback(r) {
								if (r.message) {
									frappe.show_alert({
										message: __("Webhook configured successfully!"),
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
