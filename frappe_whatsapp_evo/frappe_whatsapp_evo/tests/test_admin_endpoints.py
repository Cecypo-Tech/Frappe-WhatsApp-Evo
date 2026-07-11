import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

from frappe_whatsapp_evo.frappe_whatsapp_evo import api


def _add_line(instance_name, **kwargs):
	settings = frappe.get_single("Evolution API Settings")
	settings.append(
		"evo_lines",
		{
			"base_url": "https://evo.example.com",
			"instance_name": instance_name,
			"api_key": "test-api-key",
			**kwargs,
		},
	)
	settings.save(ignore_permissions=True)


class TestAdminEndpoints(IntegrationTestCase):
	def tearDown(self):
		settings = frappe.get_single("Evolution API Settings")
		settings.evo_lines = [r for r in settings.evo_lines if not r.instance_name.startswith("TEST-")]
		settings.save(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries

	def test_get_available_lines_returns_enabled_lines(self):
		_add_line("TEST-ADMIN-OPEN")
		_add_line("TEST-ADMIN-DISABLED", disabled=1)

		lines = api.get_available_lines()

		self.assertIn("TEST-ADMIN-OPEN", lines)
		self.assertNotIn("TEST-ADMIN-DISABLED", lines)

	@patch("frappe_whatsapp_evo.frappe_whatsapp_evo.client.EvolutionAPIClient.get_connection_state")
	def test_test_connection_writes_result_to_correct_row(self, mock_get_state):
		mock_get_state.return_value = {"instance": {"state": "open"}}
		_add_line("TEST-ADMIN-CONN")

		result = api.test_connection("TEST-ADMIN-CONN")

		self.assertEqual(result["instance"]["state"], "open")
		settings = frappe.get_single("Evolution API Settings")
		row = next(r for r in settings.evo_lines if r.instance_name == "TEST-ADMIN-CONN")
		self.assertTrue(row.last_tested_on)
		self.assertIn("open", row.last_connection_state)

	def test_test_connection_unknown_line_throws(self):
		with self.assertRaises(frappe.ValidationError):
			api.test_connection("TEST-DOES-NOT-EXIST")

	@patch("frappe_whatsapp_evo.frappe_whatsapp_evo.client.EvolutionAPIClient.get_qr_code")
	def test_get_qr_code_blocked_for_non_system_manager(self, mock_get_qr_code):
		_add_line("TEST-ADMIN-QR")

		with self.assertRaises(frappe.PermissionError):
			with self.set_user("test1@example.com"):
				api.get_qr_code("TEST-ADMIN-QR")

		mock_get_qr_code.assert_not_called()

	# Positive-path coverage (System Manager CAN still call an admin endpoint) is
	# already provided by test_test_connection_writes_result_to_correct_row above,
	# which runs as the implicit Administrator/System Manager test user and passes.
	# A duplicate happy-path test here would be redundant.
