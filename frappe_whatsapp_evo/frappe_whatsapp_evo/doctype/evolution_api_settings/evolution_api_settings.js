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
							frappe.msgprint({
								title: __("Connection State"),
								message: `<pre>${frappe.utils.escape_html(JSON.stringify(r.message, null, 2))}</pre>`,
							});
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
						if (r.message) {
							frappe.msgprint({
								title: __("Evolution API Instances"),
								message: `<pre>${frappe.utils.escape_html(JSON.stringify(r.message, null, 2))}</pre>`,
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
									frappe.msgprint({
										title: __("Webhook Configured"),
										message: `<pre>${frappe.utils.escape_html(JSON.stringify(r.message, null, 2))}</pre>`,
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
