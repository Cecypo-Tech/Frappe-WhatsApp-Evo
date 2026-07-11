import json

import frappe
from frappe.tests import IntegrationTestCase

from frappe_whatsapp_evo.frappe_whatsapp_evo import api


def _add_line(instance_name, webhook_secret, **kwargs):
	settings = frappe.get_single("Evolution API Settings")
	settings.append(
		"evo_lines",
		{
			"base_url": "https://evo.example.com",
			"instance_name": instance_name,
			"api_key": "test-api-key",
			"webhook_secret": webhook_secret,
			"default_country_code": "254",
			**kwargs,
		},
	)
	settings.save(ignore_permissions=True)


class TestWebhookRouting(IntegrationTestCase):
	def tearDown(self):
		settings = frappe.get_single("Evolution API Settings")
		settings.evo_lines = [r for r in settings.evo_lines if not r.instance_name.startswith("TEST-")]
		settings.save(ignore_permissions=True)
		frappe.db.delete("WhatsApp Evo Message", {"instance_name": ["like", "TEST-%"]})
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries

	def test_matches_line_by_token_not_payload_instance(self):
		_add_line("TEST-WEBHOOK-A", "secret-a")
		_add_line("TEST-WEBHOOK-B", "secret-b")

		# frappe.form_dict is a LocalProxy directly onto frappe.local.form_dict,
		# so mutating it in place is sufficient to simulate the incoming request.
		frappe.form_dict.token = "secret-b"
		try:
			row = api._validate_webhook_request()
		finally:
			frappe.form_dict.clear()

		# token belongs to line B even though nothing in the payload says so
		self.assertEqual(row.instance_name, "TEST-WEBHOOK-B")

	def test_unmatched_token_rejected(self):
		_add_line("TEST-WEBHOOK-C", "secret-c")

		frappe.form_dict.token = "wrong-token"
		try:
			with self.assertRaises(frappe.PermissionError):
				api._validate_webhook_request()
		finally:
			frappe.form_dict.clear()
