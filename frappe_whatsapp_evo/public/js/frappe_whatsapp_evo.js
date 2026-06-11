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
	let dialog = new frappe.ui.Dialog({
		title: __("Send via WA"),
		fields: [
			{
				label: __("Contact"),
				fieldname: "contact",
				fieldtype: "Link",
				options: "Contact",
				change: function () {
					let contact = dialog.get_value("contact");
					if (contact) {
						frappe.db.get_value("Contact", contact, "mobile_no", (r) => {
							if (r && r.mobile_no) {
								dialog.set_value("mobile_no", r.mobile_no);
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
			dialog.disable_primary_action();
			frappe.call({
				method: "frappe_whatsapp_evo.api.send_whatsapp_with_media",
				args: {
					to: values.mobile_no,
					message: values.message,
					doctype: frm.doctype,
					name: frm.docname,
					attach_type: values.attach_type === "None" ? null : values.attach_type,
					print_format: values.print_format,
				},
				freeze: true,
				freeze_message: __("Sending WhatsApp message..."),
				callback: function (r) {
					dialog.hide();
					frappe.msgprint({
						title: __("Success"),
						message: __("WhatsApp message sent successfully."),
						indicator: "green",
					});
				},
				error: function (r) {
					dialog.enable_primary_action();
				},
			});
		},
	});

	// Fetch default contact info
	frappe.call({
		method: "frappe_whatsapp_evo.api.get_contact_info",
		args: {
			doctype: frm.doctype,
			name: frm.docname,
		},
		callback: function (r) {
			if (r.message && r.message.mobile_no) {
				dialog.set_value("mobile_no", r.message.mobile_no);
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
