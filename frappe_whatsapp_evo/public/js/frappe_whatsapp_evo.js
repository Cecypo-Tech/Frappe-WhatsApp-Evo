frappe.provide("frappe.whatsapp_evo");

$(document).on("app_ready", function () {
	frappe.router.on("change", () => {
		let route = frappe.get_route();
		if (route && route[0] === "Form") {
			let doctype = route[1];
			let docname = route[2];

			// Skip for configuration and message logs themselves
			if (["Evolution API Settings", "WhatsApp Evo Message"].includes(doctype)) {
				return;
			}

			frappe.ui.form.on(doctype, {
				refresh: function (frm) {
					if (frm.is_new()) return;

					frm.page.add_menu_item(__("Send via WA"), function () {
						frappe.whatsapp_evo.show_send_dialog(frm);
					});
				},
			});
		}
	});
});

frappe.whatsapp_evo.show_send_dialog = function (frm) {
	frappe.call({
		method: "frappe_whatsapp_evo.api.get_available_lines",
		callback: function (r) {
			const lines = r.message || [];
			if (lines.length === 0) {
				frappe.msgprint({
					title: __("No WhatsApp Line Available"),
					indicator: "orange",
					message: __("There are no enabled Evo Lines you have access to. Ask an administrator to add or enable one."),
				});
				return;
			}
			frappe.whatsapp_evo.render_send_dialog(frm, lines);
		},
	});
};

frappe.whatsapp_evo.render_send_dialog = function (frm, lines) {
	let dialog = new frappe.ui.Dialog({
		title: __("Send via WA"),
		fields: [
			{
				label: __("Line"),
				fieldname: "line",
				fieldtype: "Select",
				options: lines,
				default: lines[0],
				reqd: 1,
			},
			{
				label: __("Recipient"),
				fieldname: "recipient",
				fieldtype: "Select",
				options: [],
				description: __("Numbers found on this document, its contacts and its customer."),
				change: function () {
					let choice = dialog.get_value("recipient");
					// The label is the visible option; the number lives alongside it.
					let match = (dialog.wa_candidates || []).find((c) => c.option === choice);
					if (match) {
						dialog.set_value("mobile_no", match.mobile_no);
					}
				},
			},
			{
				label: __("Or pick another contact"),
				fieldname: "contact",
				fieldtype: "Link",
				options: "Contact",
				change: function () {
					let contact = dialog.get_value("contact");
					if (contact) {
						frappe.db.get_value("Contact", contact, ["mobile_no", "phone"], (r) => {
							if (r && (r.mobile_no || r.phone)) {
								dialog.set_value("mobile_no", r.mobile_no || r.phone);
							}
						});
					}
				},
			},
			{
				label: __("Mobile Number"),
				fieldname: "mobile_no",
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldtype: "Section Break",
			},
			{
				label: __("Message"),
				fieldname: "message",
				fieldtype: "Small Text",
				reqd: 1,
			},
			{
				label: __("Attachment Type"),
				fieldname: "attach_type",
				fieldtype: "Select",
				options: ["None", "PDF"],
				default: "PDF",
			},
			{
				label: __("Print Format"),
				fieldname: "print_format",
				fieldtype: "Select",
				options: [],
				depends_on: "eval:doc.attach_type != 'None'",
			},
		],
		primary_action_label: __("Send"),
		primary_action: function (values) {
			dialog.hide();
			frappe.show_alert({
				message: __("Sending WhatsApp message..."),
				indicator: "blue"
			}, 3);
			frappe.call({
				method: "frappe_whatsapp_evo.api.send_whatsapp_with_media",
				args: {
					to: values.mobile_no,
					message: values.message,
					line: values.line,
					doctype: frm.doctype,
					name: frm.docname,
					attach_type: values.attach_type === "None" ? null : values.attach_type,
					print_format: values.print_format,
				},
				callback: function (r) {
					if (!r.exc) {
						frappe.show_alert({
							message: __("WhatsApp message sent successfully."),
							indicator: "green"
						}, 5);
					}
				},
				error: function (r) {
					frappe.show_alert({
						message: __("Failed to send WhatsApp message."),
						indicator: "red"
					}, 5);
				},
			});
		},
	});

	// Fetch candidate recipients, best first
	frappe.call({
		method: "frappe_whatsapp_evo.api.get_contact_info",
		args: {
			doctype: frm.doctype,
			name: frm.docname,
		},
		callback: function (r) {
			if (!r.message) return;

			let candidates = r.message.candidates || [];
			// Distinguish two contacts that share a display name.
			dialog.wa_candidates = candidates.map((c) => ({
				...c,
				option: `${c.label} - ${c.mobile_no}`,
			}));

			let options = dialog.wa_candidates.map((c) => c.option);
			dialog.set_df_property("recipient", "options", options);
			if (options.length) {
				dialog.set_value("recipient", options[0]);
			} else {
				dialog.set_df_property(
					"recipient",
					"description",
					__("No number found on this document. Pick a contact or type one below.")
				);
			}

			if (r.message.mobile_no) {
				dialog.set_value("mobile_no", r.message.mobile_no);
			}

			// Restrict the contact search to this document's party.
			if (r.message.party_doctype && r.message.party) {
				dialog.fields_dict.contact.get_query = function () {
					return {
						query: "frappe.contacts.doctype.contact.contact.contact_query",
						filters: {
							link_doctype: r.message.party_doctype,
							link_name: r.message.party,
						},
					};
				};
			}
		},
	});

	// Fetch message preview
	frappe.call({
		method: "frappe_whatsapp_evo.api.get_message_preview",
		args: {
			doctype: frm.doctype,
			name: frm.docname,
		},
		callback: function (r) {
			if (r.message && r.message.message) {
				dialog.set_value("message", r.message.message);
			}
		},
	});

	// Populate Print Formats
	frappe.db.get_list("Print Format", {
		filters: { doc_type: frm.doctype },
		fields: ["name"],
	}).then((r) => {
		if (r && r.length > 0) {
			let options = r.map((pf) => pf.name);
			dialog.set_df_property("print_format", "options", options);
			dialog.set_value("print_format", options[0]);
		}
	});

	dialog.show();
};
