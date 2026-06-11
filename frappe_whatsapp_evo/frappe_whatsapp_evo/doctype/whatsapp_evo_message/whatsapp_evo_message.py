from frappe.model.document import Document


class WhatsAppEvoMessage(Document):
	def before_insert(self):
		if not self.status:
			self.status = "Draft"
