import frappe
from frappe.model.document import Document


class EvoLine(Document):
	def get_webhook_url(self) -> str:
		token = self.webhook_secret
		if self.name and self.webhook_secret == "*****":
			token = self.get_password("webhook_secret")

		query = f"?token={token}" if token else ""
		return frappe.utils.get_url(f"/api/method/frappe_whatsapp_evo.api.webhook{query}")
