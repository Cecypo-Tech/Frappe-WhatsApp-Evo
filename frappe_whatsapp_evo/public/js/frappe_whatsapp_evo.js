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
		method: "frappe_whatsapp_evo.api.get_send_context",
		args: {
			doctype: frm.doctype,
			name: frm.docname,
		},
		freeze: true,
		freeze_message: __("Preparing WhatsApp message..."),
		callback: function (r) {
			const context = r.message || {};
			if (!(context.lines || []).length) {
				frappe.msgprint({
					title: __("No WhatsApp Line Available"),
					indicator: "orange",
					message: __("There are no enabled Evo Lines you have access to. Ask an administrator to add or enable one."),
				});
				return;
			}
			frappe.whatsapp_evo.render_send_dialog(frm, context);
		},
	});
};

frappe.whatsapp_evo.render_send_dialog = function (frm, context) {
	const lines = context.lines || [];
	const recipients = context.recipients || {};
	const printFormats = context.print_formats || [];

	// Label and number together: two contacts can share a display name.
	const candidates = (recipients.candidates || []).map((c) => ({
		...c,
		option: `${c.label} - ${c.mobile_no}`,
	}));
	const options = candidates.map((c) => c.option);

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
				options: options,
				default: options[0],
				description: options.length
					? __("Numbers found on this document, its contacts and its customer.")
					: __("No number found on this document. Pick a contact or type one below."),
				change: function () {
					let choice = dialog.get_value("recipient");
					let match = candidates.find((c) => c.option === choice);
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
				get_query: function () {
					// Restrict the search to this document's party.
					if (!recipients.party_doctype || !recipients.party) return {};
					return {
						query: "frappe.contacts.doctype.contact.contact.contact_query",
						filters: {
							link_doctype: recipients.party_doctype,
							link_name: recipients.party,
						},
					};
				},
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
				default: recipients.mobile_no || "",
				reqd: 1,
			},
			{
				fieldtype: "Section Break",
			},
			{
				label: __("Message"),
				fieldname: "message",
				fieldtype: "Small Text",
				default: (context.preview || {}).message || "",
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
				options: printFormats,
				default: printFormats[0],
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

	dialog.show();
};
