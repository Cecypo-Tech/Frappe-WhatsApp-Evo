import frappe
from frappe.model.document import Document


class EvolutionAPISettings(Document):
	def validate(self):
		if self.base_url:
			self.base_url = self.base_url.strip().rstrip("/")
		if self.instance_name:
			self.instance_name = self.instance_name.strip()
		if not self.timeout:
			self.timeout = 30
		if not self.webhook_secret:
			self.webhook_secret = frappe.generate_hash(length=32)

		self.webhook_url = self.get_webhook_url()

	def get_webhook_url(self):
		token = self.webhook_secret
		if self.name and self.webhook_secret == "*****":
			token = self.get_password("webhook_secret")

		query = f"?token={token}" if token else ""
		return frappe.utils.get_url(f"/api/method/frappe_whatsapp_evo.api.webhook{query}")
