import frappe
from frappe.utils.password import get_decrypted_password


def execute():
	"""Move the pre-multi-line Evolution API Settings single's field values into
	the first Evo Line row, so existing installs keep working after upgrade.

	Must run post_model_sync: it needs the Evo Line doctype and the evo_lines
	table field to already exist in the schema.
	"""
	if not frappe.db.exists("DocType", "Evolution API Settings") or not frappe.db.exists("DocType", "Evo Line"):
		return

	legacy_fields = [
		"base_url",
		"instance_name",
		"timeout",
		"default_country_code",
		"webhook_url",
		"last_webhook_response",
		"last_tested_on",
		"last_connection_state",
	]
	rows = frappe.db.sql(
		"""select field, value from `tabSingles`
		where doctype = 'Evolution API Settings' and field in %(fields)s""",
		{"fields": legacy_fields},
		as_dict=True,
	)
	values = {row.field: row.value for row in rows}
	if not values.get("instance_name"):
		return

	settings = frappe.get_single("Evolution API Settings")
	if any(r.instance_name == values.get("instance_name") for r in settings.evo_lines):
		return

	api_key = get_decrypted_password(
		"Evolution API Settings", "Evolution API Settings", "api_key", raise_exception=False
	)
	webhook_secret = get_decrypted_password(
		"Evolution API Settings", "Evolution API Settings", "webhook_secret", raise_exception=False
	)

	settings.append(
		"evo_lines",
		{
			"base_url": values.get("base_url"),
			"instance_name": values.get("instance_name"),
			"api_key": api_key,
			"timeout": frappe.utils.cint(values.get("timeout")) or 30,
			"default_country_code": values.get("default_country_code"),
			"disabled": 0,
			"webhook_secret": webhook_secret,
			"webhook_url": values.get("webhook_url"),
			"last_webhook_response": values.get("last_webhook_response"),
			"last_tested_on": values.get("last_tested_on"),
			"last_connection_state": values.get("last_connection_state"),
		},
	)
	settings.save(ignore_permissions=True)
