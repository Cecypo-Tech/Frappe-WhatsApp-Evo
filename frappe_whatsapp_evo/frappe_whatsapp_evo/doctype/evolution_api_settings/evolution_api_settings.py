import frappe
from frappe import _
from frappe.model.document import Document


class EvolutionAPISettings(Document):
	def validate(self):
		self.validate_lines()
		self.validate_line_restrictions()

	def validate_lines(self):
		seen_instance_names = set()
		for row in self.evo_lines:
			if row.base_url:
				row.base_url = row.base_url.strip().rstrip("/")
			if row.instance_name:
				row.instance_name = row.instance_name.strip()

			if not row.instance_name:
				frappe.throw(_("Row #{0}: Instance Name is required for every Evo Line").format(row.idx))

			if row.instance_name in seen_instance_names:
				frappe.throw(
					_(
						'Row #{0}: Instance Name "{1}" is used by more than one Evo Line. '
						"Instance names must be unique."
					).format(row.idx, row.instance_name)
				)
			seen_instance_names.add(row.instance_name)

			if not row.timeout:
				row.timeout = 30
			if not row.webhook_secret:
				row.webhook_secret = frappe.generate_hash(length=32)

			row.webhook_url = row.get_webhook_url()

	def validate_line_restrictions(self):
		valid_instance_names = {row.instance_name for row in self.evo_lines}
		for restriction in self.line_restrictions:
			if restriction.line:
				restriction.line = restriction.line.strip()
			if restriction.line not in valid_instance_names:
				frappe.throw(
					_('Row #{0}: "{1}" does not match any Evo Line Instance Name').format(
						restriction.idx, restriction.line
					)
				)


def find_line(instance_name: str):
	"""Return the Evo Line row with this instance_name, no disabled/permission checks."""
	settings = frappe.get_single("Evolution API Settings")
	row = next((r for r in settings.evo_lines if r.instance_name == instance_name), None)
	if not row:
		frappe.throw(_('No Evo Line found with Instance Name "{0}"').format(instance_name))
	return row


def get_line(instance_name: str):
	"""Return the Evo Line row, enforcing disabled + line restrictions for the current session user."""
	row = find_line(instance_name)
	if row.disabled:
		frappe.throw(_('Evo Line "{0}" is disabled').format(instance_name))
	if not is_line_permitted(instance_name, frappe.session.user):
		frappe.throw(_('You are not permitted to use Evo Line "{0}"').format(instance_name), frappe.PermissionError)
	return row


def is_line_permitted(instance_name: str, user: str) -> bool:
	settings = frappe.get_single("Evolution API Settings")
	allowed_users = [r.user for r in settings.line_restrictions if r.line == instance_name]
	return not allowed_users or user in allowed_users


def get_available_lines_for_user(user: str | None = None) -> list[str]:
	user = user or frappe.session.user
	settings = frappe.get_single("Evolution API Settings")
	restricted_lines = {r.line for r in settings.line_restrictions}
	allowed_restricted_lines = {r.line for r in settings.line_restrictions if r.user == user}
	return [
		row.instance_name
		for row in settings.evo_lines
		if not row.disabled
		and row.instance_name
		and (row.instance_name not in restricted_lines or row.instance_name in allowed_restricted_lines)
	]
