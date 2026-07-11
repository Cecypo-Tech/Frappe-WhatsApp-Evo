import frappe
from frappe.tests import IntegrationTestCase

from frappe_whatsapp_evo.frappe_whatsapp_evo.client import EvolutionAPIClient, normalize_phone


class TestNormalizePhone(IntegrationTestCase):
	def test_strips_leading_zero_and_prepends_country_code_kenya(self):
		# 07xx and 01xx numbers are the common short local formats in Kenya.
		self.assertEqual(normalize_phone("0725548065", "254"), "254725548065")
		self.assertEqual(normalize_phone("0112345678", "254"), "254112345678")

	def test_generic_across_country_codes_india(self):
		self.assertEqual(normalize_phone("09876543210", "91"), "919876543210")

	def test_plus_prefixed_number_untouched_by_country_code(self):
		self.assertEqual(normalize_phone("+254725548065", "254"), "254725548065")

	def test_00_prefixed_number_untouched_by_country_code(self):
		self.assertEqual(normalize_phone("00254725548065", "254"), "254725548065")

	def test_no_default_country_code_leaves_digits_as_is(self):
		self.assertEqual(normalize_phone("0725548065", None), "0725548065")


class TestEvolutionAPIClient(IntegrationTestCase):
	def test_constructor_requires_explicit_line(self):
		with self.assertRaises(TypeError):
			EvolutionAPIClient()

	def test_constructor_reads_fields_from_given_line(self):
		settings = frappe.get_single("Evolution API Settings")
		row = settings.append(
			"evo_lines",
			{
				"base_url": "https://evo.example.com/",
				"instance_name": "TEST-CLIENT-LINE",
				"api_key": "test-api-key",
				"timeout": 15,
				"default_country_code": "254",
			},
		)
		settings.save(ignore_permissions=True)
		row = next(r for r in settings.evo_lines if r.instance_name == "TEST-CLIENT-LINE")

		client = EvolutionAPIClient(row)
		self.assertEqual(client.base_url, "https://evo.example.com")
		self.assertEqual(client.instance_name, "TEST-CLIENT-LINE")
		self.assertEqual(client.api_key, "test-api-key")
		self.assertEqual(client.timeout, 15)

		settings.evo_lines = [r for r in settings.evo_lines if r.instance_name != "TEST-CLIENT-LINE"]
		settings.save(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries
