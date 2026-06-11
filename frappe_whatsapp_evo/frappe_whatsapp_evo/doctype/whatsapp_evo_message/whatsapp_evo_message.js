frappe.ui.form.on("WhatsApp Evo Message", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.direction === "Outgoing" && !["Sent", "PENDING", "SUCCESS"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Send"), () => {
				frappe.call({
					method: "frappe_whatsapp_evo.api.send_message_doc",
					args: {
						name: frm.doc.name,
					},
					freeze: true,
					freeze_message: __("Sending WhatsApp message..."),
					callback() {
						frm.reload_doc();
					},
				});
			});
		}
	},
});
