import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import set_encrypted_password

from frappe_whatsapp_evo.patches.migrate_evolution_settings_to_line import execute


class TestMigrateEvolutionSettingsPatch(IntegrationTestCase):
	def tearDown(self):
		settings = frappe.get_single("Evolution API Settings")
		settings.evo_lines = [r for r in settings.evo_lines if r.instance_name != "legacy-instance"]
		settings.save(ignore_permissions=True)
		frappe.db.sql(
			"delete from `tabSingles` where doctype='Evolution API Settings' and field in %(fields)s",
			{"fields": ["base_url", "instance_name", "timeout", "default_country_code", "webhook_url"]},
		)
		frappe.db.delete("__Auth", {"doctype": "Evolution API Settings", "name": "Evolution API Settings"})
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries

	def _seed_legacy_single_values(self):
		frappe.db.sql("delete from `tabSingles` where doctype='Evolution API Settings'")
		rows = [
			("base_url", "https://legacy.example.com"),
			("instance_name", "legacy-instance"),
			("timeout", "45"),
			("default_country_code", "254"),
			("webhook_url", "https://frappe.example.com/api/method/frappe_whatsapp_evo.api.webhook?token=legacy-token"),
		]
		for field, value in rows:
			frappe.db.sql(
				"insert into `tabSingles` (doctype, field, value) values (%(doctype)s, %(field)s, %(value)s)",
				{"doctype": "Evolution API Settings", "field": field, "value": value},
			)
		set_encrypted_password("Evolution API Settings", "Evolution API Settings", "legacy-api-key", "api_key")
		set_encrypted_password("Evolution API Settings", "Evolution API Settings", "legacy-webhook-secret", "webhook_secret")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- patch reads via a fresh query

	def test_creates_line_from_legacy_single_values(self):
		self._seed_legacy_single_values()

		execute()

		settings = frappe.get_single("Evolution API Settings")
		row = next((r for r in settings.evo_lines if r.instance_name == "legacy-instance"), None)
		self.assertIsNotNone(row)
		self.assertEqual(row.base_url, "https://legacy.example.com")
		self.assertEqual(row.timeout, 45)
		self.assertEqual(row.default_country_code, "254")
		self.assertFalse(row.disabled)
		self.assertEqual(row.get_password("api_key"), "legacy-api-key")
		self.assertEqual(row.get_password("webhook_secret"), "legacy-webhook-secret")

	def test_idempotent_does_not_duplicate_on_second_run(self):
		self._seed_legacy_single_values()
		execute()
		execute()

		settings = frappe.get_single("Evolution API Settings")
		matches = [r for r in settings.evo_lines if r.instance_name == "legacy-instance"]
		self.assertEqual(len(matches), 1)

	def test_noop_when_no_legacy_values_present(self):
		frappe.db.sql("delete from `tabSingles` where doctype='Evolution API Settings'")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries

		execute()  # must not throw

		settings = frappe.get_single("Evolution API Settings")
		self.assertFalse(any(r.instance_name == "legacy-instance" for r in settings.evo_lines))
