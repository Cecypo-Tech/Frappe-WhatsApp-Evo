# Multi-Line Evo API Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-instance `Evolution API Settings` doctype with support for multiple named WhatsApp "lines" (Evo Line child rows), each independently configurable, disableable, and user-restricted, with a line picker wired into the send dialog and server-side permission enforcement.

**Architecture:** `Evolution API Settings` stays a Single doctype but becomes a thin wrapper around a `Table` field (`evo_lines`) whose rows are a new child doctype `Evo Line`. Each `Evo Line` row carries everything `Evolution API Settings` used to hold directly (base_url, instance_name, api_key, timeout, default_country_code, webhook_secret/url, status fields) plus `disabled`. User restrictions are **not** nested inside `Evo Line` — Frappe does not support a Table field inside a doctype that is itself a child table ("grandchild tables"; confirmed against Frappe v16 core, `base_document.py`'s `_init_child` unconditionally blanks a child row's own table-field registry). Instead, `Evolution API Settings` gets a second, sibling Table field `line_restrictions` (child doctype `Evo Line Restriction`, rows: `line` + `user`), and restriction lookups filter that flat list by `instance_name`. `EvolutionAPIClient` is constructed from a specific `Evo Line` row instead of the global single. All send/admin endpoints resolve a line by `instance_name` and enforce `disabled`/line-restriction server-side. The webhook endpoint identifies the line by matching the incoming token against each row's `webhook_secret`.

**Tech Stack:** Frappe Framework v16 (Python 3 backend, vanilla `frappe.ui` JS frontend), MariaDB/Postgres via Frappe ORM, `frappe.tests.IntegrationTestCase` for tests.

## Global Constraints

- Site under test: `dev.localhost` (has `frappe_whatsapp_evo` installed). All `bench` commands below use `--site dev.localhost`.
- App path: `/home/kushal/frappe-bench/apps/frappe_whatsapp_evo` (repo root for all file paths below, which are given relative to this root).
- Module name for all new doctypes: `Frappe Whatsapp Evo` (matches existing `modules.txt`).
- No new friendly "Line Name" field — `instance_name` is used as both technical identifier and dropdown label (per approved spec).
- A line with no matching `line_restrictions` rows means "all users allowed" — this must hold both in the UI dropdown filter and in server-side enforcement.
- Never log secrets (`api_key`, `webhook_secret`) in plaintext — reuse the existing `redact_secrets()` helper in `client.py` wherever API responses are surfaced.
- Every new whitelisted method must work for a non-Administrator `System Manager` session the same as it did before (no permission regressions on the existing single-line flow).

---

### Task 1: Data model — Evo Line, Evo Line Restriction, Evolution API Settings restructure

**Note on this revision:** the original brief for this task nested a `limited_to_users` Table field inside `Evo Line`. Frappe does not support a Table field inside a doctype that is itself a child table ("grandchild tables") — `_init_child` in `frappe/model/base_document.py` unconditionally blanks a child row's own table-field registry (`child._table_fieldnames = TABLE_DOCTYPES_FOR_CHILD_TABLES` where that constant is always `{}`), regardless of what the child's own meta declares, and this is deliberate policy ("child tables don't have child tables"), confirmed against this bench's Frappe v16.20.0. So user restrictions are modeled as a second, sibling Table field on `Evolution API Settings` instead of nesting inside `Evo Line`.

**Files:**
- Create: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line_restriction/__init__.py`
- Create: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line_restriction/evo_line_restriction.json`
- Create: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line_restriction/evo_line_restriction.py`
- Create: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line/__init__.py`
- Create: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line/evo_line.json`
- Create: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line/evo_line.py`
- Modify: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/evolution_api_settings.json` (full rewrite)
- Modify: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/evolution_api_settings.py` (full rewrite)
- Test: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/test_evolution_api_settings.py`

**Interfaces:**
- Produces (used by Tasks 2-6): `frappe_whatsapp_evo.frappe_whatsapp_evo.doctype.evolution_api_settings.evolution_api_settings`:
  - `find_line(instance_name: str) -> Document` — returns the `Evo Line` row or throws `frappe.throw` (`ValidationError`) if not found. No disabled/permission checks (used by admin endpoints).
  - `get_line(instance_name: str) -> Document` — calls `find_line`, then throws if `row.disabled`, then throws `frappe.PermissionError` if the current session user isn't permitted. Used by send endpoints.
  - `is_line_permitted(instance_name: str, user: str) -> bool` — `True` if no `line_restrictions` row matches `instance_name`, or `user` is one of the ones that do. **Takes `instance_name`, not a row** — it looks up `Evolution API Settings.line_restrictions` itself.
  - `get_available_lines_for_user(user: str | None = None) -> list[str]` — enabled + permitted `instance_name`s for `user` (defaults to `frappe.session.user`).
- Produces (used by Task 2): `Evo Line.get_webhook_url(self) -> str` — instance method on the child doc, NOT an auto-firing hook (Frappe does not call custom `validate()` on child rows automatically — only mandatory/select/length checks run automatically for children; the parent's own `validate()` must loop rows itself and call this method explicitly).

- [ ] **Step 1: Create the `Evo Line Restriction` child doctype**

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line_restriction/__init__.py`:
```python
```
(empty file, matches convention of other doctype `__init__.py` files in this app)

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line_restriction/evo_line_restriction.json`:
```json
{
 "actions": [],
 "allow_rename": 1,
 "creation": "2026-07-11 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "line",
  "user"
 ],
 "fields": [
  {
   "description": "Must match an existing Evo Line's Instance Name.",
   "fieldname": "line",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Line",
   "reqd": 1
  },
  {
   "fieldname": "user",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "User",
   "options": "User",
   "reqd": 1
  }
 ],
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-07-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Frappe Whatsapp Evo",
 "name": "Evo Line Restriction",
 "naming_rule": "Random",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line_restriction/evo_line_restriction.py`:
```python
from frappe.model.document import Document


class EvoLineRestriction(Document):
	pass
```

- [ ] **Step 2: Create the `Evo Line` child doctype**

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line/__init__.py`:
```python
```
(empty file)

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line/evo_line.json`:
```json
{
 "actions": [],
 "allow_rename": 1,
 "creation": "2026-07-10 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "connection_section",
  "base_url",
  "instance_name",
  "column_break_connection",
  "api_key",
  "timeout",
  "default_country_code",
  "disabled",
  "webhook_section",
  "webhook_secret",
  "webhook_url",
  "column_break_webhook",
  "last_webhook_response",
  "status_section",
  "last_tested_on",
  "column_break_status",
  "last_connection_state"
 ],
 "fields": [
  {
   "fieldname": "connection_section",
   "fieldtype": "Section Break",
   "label": "Connection"
  },
  {
   "description": "Base URL for the Evolution API server, for example https://evo.example.com",
   "fieldname": "base_url",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Base URL",
   "reqd": 1
  },
  {
   "description": "Evolution API instance name already running on the VPS. Must be unique across all Evo Lines.",
   "fieldname": "instance_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Instance Name",
   "reqd": 1
  },
  {
   "fieldname": "column_break_connection",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "api_key",
   "fieldtype": "Password",
   "label": "API Key / Instance Token",
   "reqd": 1
  },
  {
   "default": "30",
   "fieldname": "timeout",
   "fieldtype": "Int",
   "label": "Timeout (Seconds)"
  },
  {
   "description": "Optional country code used when a number starts with 0. Example: 254.",
   "fieldname": "default_country_code",
   "fieldtype": "Data",
   "label": "Default Country Code"
  },
  {
   "default": "0",
   "description": "Disabled lines are hidden from the send dialog and cannot send or receive messages.",
   "fieldname": "disabled",
   "fieldtype": "Check",
   "in_list_view": 1,
   "label": "Disabled"
  },
  {
   "fieldname": "webhook_section",
   "fieldtype": "Section Break",
   "label": "Webhook"
  },
  {
   "description": "Secret appended to the webhook URL and verified by Frappe.",
   "fieldname": "webhook_secret",
   "fieldtype": "Password",
   "label": "Webhook Secret"
  },
  {
   "fieldname": "webhook_url",
   "fieldtype": "Small Text",
   "label": "Webhook URL",
   "read_only": 1
  },
  {
   "fieldname": "column_break_webhook",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "last_webhook_response",
   "fieldtype": "JSON",
   "label": "Last Webhook Response",
   "read_only": 1
  },
  {
   "fieldname": "status_section",
   "fieldtype": "Section Break",
   "label": "Status"
  },
  {
   "fieldname": "last_tested_on",
   "fieldtype": "Datetime",
   "label": "Last Tested On",
   "read_only": 1
  },
  {
   "fieldname": "column_break_status",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "last_connection_state",
   "fieldtype": "JSON",
   "label": "Last Connection State",
   "read_only": 1
  }
 ],
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-07-10 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Frappe Whatsapp Evo",
 "name": "Evo Line",
 "naming_rule": "Random",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line/evo_line.py`:
```python
import frappe
from frappe.model.document import Document


class EvoLine(Document):
	def get_webhook_url(self) -> str:
		token = self.webhook_secret
		if self.name and self.webhook_secret == "*****":
			token = self.get_password("webhook_secret")

		query = f"?token={token}" if token else ""
		return frappe.utils.get_url(f"/api/method/frappe_whatsapp_evo.api.webhook{query}")
```

- [ ] **Step 3: Rewrite `Evolution API Settings` to wrap `evo_lines` + `line_restrictions`**

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/evolution_api_settings.json`:
```json
{
 "actions": [],
 "allow_rename": 1,
 "creation": "2026-06-11 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "lines_section",
  "evo_lines",
  "restrictions_section",
  "line_restrictions"
 ],
 "fields": [
  {
   "fieldname": "lines_section",
   "fieldtype": "Section Break",
   "label": "Evo Lines"
  },
  {
   "description": "Each row is an independent Evolution API connection (\"line\"). Add one row per WhatsApp number/instance.",
   "fieldname": "evo_lines",
   "fieldtype": "Table",
   "label": "Evo Lines",
   "options": "Evo Line"
  },
  {
   "fieldname": "restrictions_section",
   "fieldtype": "Section Break",
   "label": "Line Restrictions"
  },
  {
   "description": "Restrict which users can use a given line by adding rows here (Line must match an Evo Line's Instance Name). A line with no matching rows is open to all users.",
   "fieldname": "line_restrictions",
   "fieldtype": "Table",
   "label": "Line Restrictions",
   "options": "Evo Line Restriction"
  }
 ],
 "index_web_pages_for_search": 1,
 "issingle": 1,
 "links": [],
 "modified": "2026-07-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Frappe Whatsapp Evo",
 "name": "Evolution API Settings",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/evolution_api_settings.py`:
```python
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
```

- [ ] **Step 4: Write the failing tests**

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/test_evolution_api_settings.py`:
```python
import frappe
from frappe.tests import IntegrationTestCase

from frappe_whatsapp_evo.frappe_whatsapp_evo.doctype.evolution_api_settings.evolution_api_settings import (
	find_line,
	get_available_lines_for_user,
	get_line,
	is_line_permitted,
)


def _add_line(instance_name, **kwargs):
	settings = frappe.get_single("Evolution API Settings")
	row = settings.append(
		"evo_lines",
		{
			"base_url": "https://evo.example.com",
			"instance_name": instance_name,
			"api_key": "test-api-key",
			**kwargs,
		},
	)
	settings.save(ignore_permissions=True)
	return row.name


def _restrict_line(instance_name, user):
	settings = frappe.get_single("Evolution API Settings")
	settings.append("line_restrictions", {"line": instance_name, "user": user})
	settings.save(ignore_permissions=True)


class TestEvolutionAPISettings(IntegrationTestCase):
	def tearDown(self):
		settings = frappe.get_single("Evolution API Settings")
		settings.line_restrictions = [r for r in settings.line_restrictions if not r.line.startswith("TEST-")]
		settings.evo_lines = [r for r in settings.evo_lines if not r.instance_name.startswith("TEST-")]
		settings.save(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries

	def test_duplicate_instance_name_rejected(self):
		_add_line("TEST-DUP")
		settings = frappe.get_single("Evolution API Settings")
		settings.append(
			"evo_lines",
			{"base_url": "https://evo2.example.com", "instance_name": "TEST-DUP", "api_key": "another-key"},
		)
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)

	def test_webhook_secret_autogenerated_and_url_computed(self):
		_add_line("TEST-WEBHOOK")
		settings = frappe.get_single("Evolution API Settings")
		row = next(r for r in settings.evo_lines if r.instance_name == "TEST-WEBHOOK")
		self.assertTrue(row.webhook_secret)
		self.assertIn("frappe_whatsapp_evo.api.webhook", row.webhook_url)

	def test_find_line_missing_throws(self):
		with self.assertRaises(frappe.ValidationError):
			find_line("TEST-DOES-NOT-EXIST")

	def test_get_line_disabled_throws(self):
		_add_line("TEST-DISABLED", disabled=1)
		with self.assertRaises(frappe.ValidationError):
			get_line("TEST-DISABLED")

	def test_line_restriction_must_match_existing_instance_name(self):
		settings = frappe.get_single("Evolution API Settings")
		settings.append("line_restrictions", {"line": "TEST-NO-SUCH-LINE", "user": "Administrator"})
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)

	def test_is_line_permitted_open_when_no_restrictions(self):
		_add_line("TEST-OPEN")
		self.assertTrue(is_line_permitted("TEST-OPEN", "someone@example.com"))

	def test_is_line_permitted_restricted(self):
		_add_line("TEST-RESTRICTED")
		_restrict_line("TEST-RESTRICTED", "Administrator")

		self.assertTrue(is_line_permitted("TEST-RESTRICTED", "Administrator"))
		self.assertFalse(is_line_permitted("TEST-RESTRICTED", "someone-else@example.com"))

	def test_get_available_lines_for_user_excludes_disabled_and_restricted(self):
		_add_line("TEST-AVAIL-OPEN")
		_add_line("TEST-AVAIL-DISABLED", disabled=1)
		_add_line("TEST-AVAIL-RESTRICTED")
		_restrict_line("TEST-AVAIL-RESTRICTED", "Administrator")

		available = get_available_lines_for_user("someone-else@example.com")
		self.assertIn("TEST-AVAIL-OPEN", available)
		self.assertNotIn("TEST-AVAIL-DISABLED", available)
		self.assertNotIn("TEST-AVAIL-RESTRICTED", available)

		available_for_admin = get_available_lines_for_user("Administrator")
		self.assertIn("TEST-AVAIL-RESTRICTED", available_for_admin)
```

- [ ] **Step 5: Run `bench migrate` to sync the new/changed doctypes, then run the tests**

Run:
```bash
cd /home/kushal/frappe-bench
bench --site dev.localhost migrate
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.doctype.evolution_api_settings.test_evolution_api_settings
```
Expected: migrate completes without error (new `tabEvo Line` / `tabEvo Line Restriction` tables created, old single fields no longer read by the JSON); all 8 tests in the module PASS.

- [ ] **Step 6: Commit**

```bash
git add frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line_restriction frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evo_line frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings
git commit -m "feat(evo-lines): add Evo Line/Evo Line Restriction child doctypes, restructure Evolution API Settings"
```

---

### Task 2: `client.py` — `EvolutionAPIClient` takes a line row

**Files:**
- Modify: `frappe_whatsapp_evo/frappe_whatsapp_evo/client.py:62-76`
- Test: `frappe_whatsapp_evo/frappe_whatsapp_evo/tests/__init__.py` (create, empty)
- Test: `frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_client.py`

**Interfaces:**
- Consumes: none new (this task only touches `client.py`; `Evo Line` rows from Task 1 are constructed ad hoc in the test).
- Produces (used by Tasks 3-5): `EvolutionAPIClient(line)` — constructor now takes one required positional arg, an `Evo Line` document/row (must have `.base_url`, `.instance_name`, `.api_key` (Password), `.timeout`, `.default_country_code`). No more implicit `frappe.get_single("Evolution API Settings")` fallback.

- [ ] **Step 1: Write the failing test**

`frappe_whatsapp_evo/frappe_whatsapp_evo/tests/__init__.py`:
```python
```
(empty file)

`frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_client.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify current failures**

Run:
```bash
cd /home/kushal/frappe-bench
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_client
```
Expected: `TestNormalizePhone` tests PASS already (logic untouched). `TestEvolutionAPIClient.test_constructor_requires_explicit_line` FAILS (constructor currently accepts zero args). `test_constructor_reads_fields_from_given_line` currently passes `settings` as a positional but the attribute names already match, so this may already pass — that's fine, it locks in current behavior before the signature change.

- [ ] **Step 3: Update the constructor**

In `frappe_whatsapp_evo/frappe_whatsapp_evo/client.py`, replace lines 62-76:
```python
class EvolutionAPIClient:
	def __init__(self, settings=None):
		self.settings = settings or frappe.get_single("Evolution API Settings")
		self.base_url = (self.settings.base_url or "").strip().rstrip("/")
		self.instance_identifier = (self.settings.instance_name or "").strip()
		self.instance_name = self.instance_identifier
		self.api_key = get_password_value(self.settings, "api_key")
		self.timeout = int(self.settings.timeout or 30)

		if not self.base_url:
			frappe.throw(_("Evolution API Base URL is required"))
		if not self.instance_identifier:
			frappe.throw(_("Evolution API Instance Name is required"))
		if not self.api_key:
			frappe.throw(_("Evolution API Key is required"))
```
with:
```python
class EvolutionAPIClient:
	def __init__(self, line):
		self.settings = line
		self.base_url = (line.base_url or "").strip().rstrip("/")
		self.instance_identifier = (line.instance_name or "").strip()
		self.instance_name = self.instance_identifier
		self.api_key = get_password_value(line, "api_key")
		self.timeout = int(line.timeout or 30)

		if not self.base_url:
			frappe.throw(_("Evolution API Base URL is required"))
		if not self.instance_identifier:
			frappe.throw(_("Evolution API Instance Name is required"))
		if not self.api_key:
			frappe.throw(_("Evolution API Key is required"))
```
(`self.settings` is kept as the attribute name — all other methods on the class already read `self.settings.default_country_code`, so no other lines in this file need to change.)

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_client
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frappe_whatsapp_evo/frappe_whatsapp_evo/client.py frappe_whatsapp_evo/frappe_whatsapp_evo/tests
git commit -m "refactor(evo-lines): EvolutionAPIClient takes an explicit Evo Line row"
```

---

### Task 3: `api.py` — line-scoped sending with server-side permission enforcement

**Files:**
- Modify: `frappe_whatsapp_evo/frappe_whatsapp_evo/api.py` (imports, `_insert_message_log`, `send_text`, `send_media`, `send_whatsapp_with_media`, `send_message_doc`)
- Test: `frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_send.py`

**Interfaces:**
- Consumes: `find_line`, `get_line`, `is_line_permitted` from Task 1; `EvolutionAPIClient(line)` from Task 2.
- Produces (used by Task 8 frontend): `send_text(to, message, line, delay=None, link_preview=True, reference_doctype=None, reference_name=None)`, `send_media(to, media, mediatype, mimetype, filename, line, caption=None, delay=None, reference_doctype=None, reference_name=None)`, `send_whatsapp_with_media(to, message, doctype, name, line, attach_type=None, print_format=None)` — all now require `line` (an `instance_name` string). `send_message_doc(name)` keeps its old signature; it resolves `line` internally from `doc.instance_name`.

- [ ] **Step 1: Write the failing tests**

`frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_send.py`:
```python
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
			"default_country_code": "254",
			**kwargs,
		},
	)
	settings.save(ignore_permissions=True)


def _restrict_line(instance_name, user):
	settings = frappe.get_single("Evolution API Settings")
	settings.append("line_restrictions", {"line": instance_name, "user": user})
	settings.save(ignore_permissions=True)


class TestSendPermissions(IntegrationTestCase):
	def tearDown(self):
		settings = frappe.get_single("Evolution API Settings")
		settings.line_restrictions = [r for r in settings.line_restrictions if not r.line.startswith("TEST-")]
		settings.evo_lines = [r for r in settings.evo_lines if not r.instance_name.startswith("TEST-")]
		settings.save(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries

	@patch("frappe_whatsapp_evo.frappe_whatsapp_evo.client.EvolutionAPIClient.send_text")
	def test_send_text_open_line_succeeds(self, mock_send_text):
		mock_send_text.return_value = {"status": "PENDING", "key": {"id": "wamid.1"}}
		_add_line("TEST-SEND-OPEN")

		result = api.send_text(to="0725548065", message="hi", line="TEST-SEND-OPEN")

		self.assertTrue(result["message_log"])
		mock_send_text.assert_called_once()
		log = frappe.get_doc("WhatsApp Evo Message", result["message_log"])
		self.assertEqual(log.to_number, "254725548065")
		self.assertEqual(log.instance_name, "TEST-SEND-OPEN")
		log.delete(ignore_permissions=True)

	def test_send_text_restricted_line_blocks_unlisted_user(self):
		_add_line("TEST-SEND-RESTRICTED")
		_restrict_line("TEST-SEND-RESTRICTED", "Administrator")

		with self.assertRaises(frappe.PermissionError):
			with self.set_user("Guest"):
				api.send_text(to="0725548065", message="hi", line="TEST-SEND-RESTRICTED")

	def test_send_text_disabled_line_blocked(self):
		_add_line("TEST-SEND-DISABLED", disabled=1)

		with self.assertRaises(frappe.ValidationError):
			api.send_text(to="0725548065", message="hi", line="TEST-SEND-DISABLED")

	@patch("frappe_whatsapp_evo.frappe_whatsapp_evo.client.EvolutionAPIClient.send_text")
	def test_send_message_doc_resolves_line_from_stored_instance_name(self, mock_send_text):
		mock_send_text.return_value = {"status": "PENDING", "key": {"id": "wamid.2"}}
		_add_line("TEST-RESEND-LINE")

		doc = frappe.get_doc(
			{
				"doctype": "WhatsApp Evo Message",
				"direction": "Outgoing",
				"status": "Draft",
				"message_type": "text",
				"to_number": "254725548065",
				"message": "resend me",
				"instance_name": "TEST-RESEND-LINE",
			}
		)
		doc.insert(ignore_permissions=True)

		try:
			api.send_message_doc(doc.name)
			doc.reload()
			self.assertEqual(doc.status, "Sent")
		finally:
			# send_message_doc's send_text call inserts a second log doc via
			# _insert_message_log - clean up both by instance_name.
			frappe.db.delete("WhatsApp Evo Message", {"instance_name": "TEST-RESEND-LINE"})
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_send
```
Expected: FAIL — `send_text()` doesn't accept a `line` kwarg yet (`TypeError`), and `set_user` context manager call will error before reaching assertions.

- [ ] **Step 3: Update `api.py`**

Replace the import block (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:8-13`):
```python
from frappe_whatsapp_evo.frappe_whatsapp_evo.client import (
	EvolutionAPIClient,
	get_message_id,
	normalize_phone,
	redact_secrets,
)
```
with:
```python
from frappe_whatsapp_evo.frappe_whatsapp_evo.client import (
	EvolutionAPIClient,
	get_message_id,
	normalize_phone,
	redact_secrets,
)
from frappe_whatsapp_evo.frappe_whatsapp_evo.doctype.evolution_api_settings.evolution_api_settings import (
	find_line,
	get_line,
)
```

Replace `_insert_message_log`'s `instance_name` default (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:99`), from:
```python
			"instance_name": instance_name or (get_settings().instance_name if frappe.db.exists("DocType", "Evolution API Settings") else None),
```
to:
```python
			"instance_name": instance_name,
```

Replace `send_text` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:190-224`):
```python
@frappe.whitelist()
def send_text(
	to: str,
	message: str,
	line: str,
	delay: int | None = None,
	link_preview: bool = True,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
):
	row = get_line(line)
	client = EvolutionAPIClient(row)
	try:
		result = client.send_text(to, message, delay=delay, link_preview=frappe.utils.cint(link_preview))
	except Exception as exc:
		_insert_message_log(
			direction="Outgoing",
			status="Failed",
			to=to,
			message=message,
			error=str(exc),
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			instance_name=row.instance_name,
		)
		raise

	doc = _insert_message_log(
		direction="Outgoing",
		status=result.get("status") or "Sent",
		to=normalize_phone(to, row.default_country_code),
		message=message,
		response_json=result,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		instance_name=row.instance_name,
	)
	return {"message_log": doc.name, "response": result}
```

Replace `send_media` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:227-276`):
```python
@frappe.whitelist()
def send_media(
	to: str,
	media: str,
	mediatype: str,
	mimetype: str,
	filename: str,
	line: str,
	caption: str | None = None,
	delay: int | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
):
	row = get_line(line)
	client = EvolutionAPIClient(row)
	try:
		result = client.send_media(
			to=to,
			media=media,
			mediatype=mediatype,
			mimetype=mimetype,
			filename=filename,
			caption=caption,
			delay=delay,
		)
	except Exception as exc:
		_insert_message_log(
			direction="Outgoing",
			status="Failed",
			to=to,
			message=caption,
			message_type=mediatype,
			media_url=media,
			error=str(exc),
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			instance_name=row.instance_name,
		)
		raise

	doc = _insert_message_log(
		direction="Outgoing",
		status=result.get("status") or "Sent",
		to=normalize_phone(to, row.default_country_code),
		message=caption,
		message_type=mediatype,
		media_url=media,
		response_json=result,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		instance_name=row.instance_name,
	)
	return {"message_log": doc.name, "response": result}
```

Replace `send_whatsapp_with_media` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:352-386`):
```python
@frappe.whitelist()
def send_whatsapp_with_media(
	to: str,
	message: str,
	doctype: str,
	name: str,
	line: str,
	attach_type: str = None,  # "PDF" or None
	print_format: str = None,
):
	"""Send WhatsApp message with optional PDF attachment."""
	if not attach_type or attach_type == "None":
		return send_text(to=to, message=message, line=line, reference_doctype=doctype, reference_name=name)

	if attach_type == "PDF":
		media_content = frappe.get_print(doctype, name, print_format=print_format, as_pdf=True)
		filename = f"{name.replace('/', '-')}.pdf"
		mimetype = "application/pdf"
		mediatype = "document"
	else:
		return send_text(to=to, message=message, line=line, reference_doctype=doctype, reference_name=name)

	b64_data = base64.b64encode(media_content).decode("utf-8")

	return send_media(
		to=to,
		media=b64_data,
		mediatype=mediatype,
		mimetype=mimetype,
		filename=filename,
		caption=message,
		line=line,
		reference_doctype=doctype,
		reference_name=name,
	)
```

Replace `send_message_doc` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:389-419`):
```python
@frappe.whitelist()
def send_message_doc(name: str):
	doc = frappe.get_doc("WhatsApp Evo Message", name)
	doc.check_permission("write")

	if doc.direction != "Outgoing":
		frappe.throw(_("Only outgoing messages can be sent"))
	if doc.status in {"Sent", "PENDING", "SUCCESS"}:
		frappe.throw(_("This message has already been sent"))
	if not doc.instance_name:
		frappe.throw(_("This message has no Evo Line recorded and cannot be resent"))

	if doc.message_type == "text":
		result = send_text(
			to=doc.to_number,
			message=doc.message,
			line=doc.instance_name,
			reference_doctype=doc.reference_doctype,
			reference_name=doc.reference_name,
		)
	else:
		result = send_media(
			to=doc.to_number,
			media=doc.media_url,
			mediatype=doc.message_type,
			mimetype=doc.mimetype,
			filename=doc.filename,
			caption=doc.message,
			line=doc.instance_name,
			reference_doctype=doc.reference_doctype,
			reference_name=doc.reference_name,
		)

	doc.db_set("status", "Sent", update_modified=False)
	return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_send
```
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frappe_whatsapp_evo/frappe_whatsapp_evo/api.py frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_send.py
git commit -m "feat(evo-lines): enforce line resolution and permissions on send endpoints"
```

---

### Task 4: `api.py` — per-line admin endpoints + `get_available_lines`

**Files:**
- Modify: `frappe_whatsapp_evo/frappe_whatsapp_evo/api.py` (`get_settings`/`_set_single_value` removal, `get_webhook_url` removal, `fetch_instances`, `get_qr_code`, `diagnose_webhook_routes`, `test_connection`, `configure_webhook`, plus new `get_available_lines`)
- Test: `frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_admin_endpoints.py`

**Interfaces:**
- Consumes: `find_line`, `get_available_lines_for_user` from Task 1.
- Produces (used by Task 7 frontend): `get_available_lines() -> list[str]` (whitelisted, no args, returns lines for `frappe.session.user`). `test_connection(line)`, `configure_webhook(line)`, `fetch_instances(line)`, `get_qr_code(line)`, `diagnose_webhook_routes(line)` — all now require `line` (`instance_name` string).

- [ ] **Step 1: Write the failing tests**

`frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_admin_endpoints.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_admin_endpoints
```
Expected: FAIL — `get_available_lines` doesn't exist yet; `test_connection` doesn't accept a positional `line` arg yet.

- [ ] **Step 3: Update `api.py`**

Remove `_set_single_value` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:20-21`) — replace:
```python
def _set_single_value(fieldname: str, value):
	frappe.db.set_single_value("Evolution API Settings", fieldname, value)
```
with nothing (delete these lines).

Leave `get_settings()` and the module-level `get_webhook_url()` (lines 16-17 and 24-28) untouched for now — they are still used by `_validate_webhook_request()`/`webhook()`, which Task 5 rewrites. Task 5 removes them once their last callers are gone.

Replace `fetch_instances` / `get_qr_code` / `diagnose_webhook_routes` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:133-163`):
```python
@frappe.whitelist()
def get_available_lines():
	from frappe_whatsapp_evo.frappe_whatsapp_evo.doctype.evolution_api_settings.evolution_api_settings import (
		get_available_lines_for_user,
	)

	return get_available_lines_for_user()


@frappe.whitelist()
def fetch_instances(line: str):
	return EvolutionAPIClient(find_line(line)).fetch_instances()


@frappe.whitelist()
def get_qr_code(line: str):
	return EvolutionAPIClient(find_line(line)).get_qr_code()


@frappe.whitelist()
def diagnose_webhook_routes(line: str):
	client = EvolutionAPIClient(find_line(line))
	instance = client.get_route_instance_name()
	paths = [
		f"/webhook/get/{instance}",
		f"/webhook/find/{instance}",
		f"/webhook/{instance}",
		f"/instance/webhook/{instance}",
		f"/webhook/status/{instance}",
	]
	results = []
	for path in paths:
		result, error = client.request_or_error("GET", path)
		results.append({
			"path": path,
			"ok": result is not None,
			"result": redact_secrets(result) if result is not None else None,
			"error": error,
		})
	return {"instance": instance, "results": results}
```
(`get_available_lines_for_user` is imported locally inside this function rather than added to the top-level import block, so this task doesn't need to re-touch the import statement Task 3 already edited — there is no circular import concern since `evolution_api_settings.py` never imports `api.py`.)

Replace `test_connection` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:166-174`):
```python
@frappe.whitelist()
def test_connection(line: str):
	row = find_line(line)
	client = EvolutionAPIClient(row)
	result = client.get_connection_state()

	frappe.db.set_value("Evo Line", row.name, "last_connection_state", frappe.as_json(result))
	frappe.db.set_value("Evo Line", row.name, "last_tested_on", frappe.utils.now_datetime())

	return result
```

Replace `configure_webhook` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:177-187`):
```python
@frappe.whitelist()
def configure_webhook(line: str):
	row = find_line(line)
	client = EvolutionAPIClient(row)
	url = row.webhook_url
	result = client.set_webhook(url)
	safe_result = redact_secrets(result)

	frappe.db.set_value("Evo Line", row.name, "last_webhook_response", frappe.as_json(safe_result))

	return {"webhook_url": url, "response": safe_result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_admin_endpoints
```
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frappe_whatsapp_evo/frappe_whatsapp_evo/api.py frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_admin_endpoints.py
git commit -m "feat(evo-lines): make admin endpoints per-line, add get_available_lines"
```

---

### Task 5: `api.py` — webhook token routing

**Files:**
- Modify: `frappe_whatsapp_evo/frappe_whatsapp_evo/api.py` (`_validate_webhook_request`, `webhook`)
- Test: `frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_webhook.py`

**Interfaces:**
- Consumes: none new from other tasks.
- Produces: `_find_line_by_webhook_token(token: str) -> Document | None` (module-private helper in `api.py`). `_validate_webhook_request()` now returns the matched `Evo Line` row instead of `None`, and `webhook()` uses it for `default_country_code` and `instance_name` instead of the old global single.

- [ ] **Step 1: Write the failing tests**

`frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_webhook.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_webhook
```
Expected: FAIL — `_validate_webhook_request()` currently returns `None` and validates against the (now nonexistent) single-level `webhook_secret`.

- [ ] **Step 3: Update `api.py`**

Remove the now-unused `from urllib.parse import urlencode` import at the top of the file, and remove `get_settings()` and the module-level `get_webhook_url()` (left in place by Task 4 — `frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:16-17` and `:24-28`):
```python
def get_settings():
	return frappe.get_single("Evolution API Settings")


def get_webhook_url() -> str:
	settings = get_settings()
	token = settings.get_password("webhook_secret") if settings.webhook_secret else None
	query = f"?{urlencode({'token': token})}" if token else ""
	return frappe.utils.get_url(f"/api/method/frappe_whatsapp_evo.api.webhook{query}")
```
Delete both — nothing calls them once this task's rewrite below lands.

Replace `_validate_webhook_request` and the top of `webhook` (`frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:422-452`):
```python
def _find_line_by_webhook_token(token: str | None):
	if not token:
		return None
	settings = frappe.get_single("Evolution API Settings")
	for row in settings.evo_lines:
		secret = row.get_password("webhook_secret") if row.webhook_secret else None
		if secret and secret == token:
			return row
	return None


def _validate_webhook_request():
	token = (
		frappe.form_dict.get("token")
		or frappe.get_request_header("X-Webhook-Secret")
		or frappe.get_request_header("X-Evolution-Webhook-Secret")
	)
	row = _find_line_by_webhook_token(token)
	if not row:
		frappe.throw(_("Invalid webhook token"), frappe.PermissionError)
	return row


@frappe.whitelist(allow_guest=True)
def webhook():
	line = _validate_webhook_request()

	payload = frappe.local.form_dict
	if frappe.request and frappe.request.data:
		try:
			payload = json.loads(frappe.request.data)
		except ValueError:
			payload = dict(frappe.local.form_dict)

	event = payload.get("event")
	extracted = _extract_message_payload(payload)
	data = extracted["data"]
	remote_number = (
		normalize_phone(extracted["remote_jid"] or "", line.default_country_code)
		if extracted["remote_jid"]
		else None
	)
	direction = "Outgoing" if extracted["from_me"] else "Incoming"
```

Leave the rest of `webhook()` (the `existing` / else branch, `frappe_whatsapp_evo/frappe_whatsapp_evo/api.py:455-479` in the old file) unchanged except the `_insert_message_log` call's `instance_name` argument, which changes from:
```python
				instance_name=instance_name,
```
to:
```python
				instance_name=line.instance_name,
```
(the old `instance_name = payload.get("instance")` line is deleted — the payload's own `instance` field is no longer trusted for routing or logging).

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_webhook
```
Expected: both tests PASS.

- [ ] **Step 5: Run the full backend test suite so far**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo
```
Expected: all tests across every module added in Tasks 1-5 PASS.

- [ ] **Step 6: Commit**

```bash
git add frappe_whatsapp_evo/frappe_whatsapp_evo/api.py frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_webhook.py
git commit -m "feat(evo-lines): route incoming webhooks by matching secret token to a line"
```

---

### Task 6: Migration patch

**Files:**
- Create: `frappe_whatsapp_evo/patches/__init__.py`
- Create: `frappe_whatsapp_evo/patches/migrate_evolution_settings_to_line.py`
- Modify: `frappe_whatsapp_evo/patches.txt` (full rewrite)
- Test: `frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_migrate_evolution_settings_patch.py`

**Interfaces:**
- Consumes: none from other tasks (operates on raw `tabSingles`/`__Auth` rows and the `Evo Line` schema from Task 1).
- Produces: `frappe_whatsapp_evo.patches.migrate_evolution_settings_to_line.execute()` — idempotent, registered in `patches.txt` under `[post_model_sync]` (must run **after** schema sync, since it needs the `Evo Line` doctype and the `evo_lines` field to already exist — see note in Step 3).

- [ ] **Step 1: Write the failing test**

`frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_migrate_evolution_settings_patch.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_migrate_evolution_settings_patch
```
Expected: FAIL with `ModuleNotFoundError: No module named 'frappe_whatsapp_evo.patches'`.

- [ ] **Step 3: Write the patch**

`frappe_whatsapp_evo/patches/__init__.py`:
```python
```
(empty file)

`frappe_whatsapp_evo/patches/migrate_evolution_settings_to_line.py`:
```python
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
	if not values.get("base_url") and not values.get("instance_name"):
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
```

`frappe_whatsapp_evo/patches.txt` (full rewrite — the section headers matter: without them, every line in this file is treated as `pre_model_sync` for backward-compat parsing, which would run this patch **before** `Evo Line`/`evo_lines` exist and crash):
```
[pre_model_sync]

[post_model_sync]
frappe_whatsapp_evo.patches.migrate_evolution_settings_to_line
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
bench --site dev.localhost run-tests --app frappe_whatsapp_evo --module frappe_whatsapp_evo.frappe_whatsapp_evo.tests.test_migrate_evolution_settings_patch
```
Expected: all 3 tests PASS.

- [ ] **Step 5: Run `bench migrate` end-to-end to confirm the patch is registered and runs cleanly**

Run:
```bash
bench --site dev.localhost migrate
```
Expected: no errors; patch log shows `frappe_whatsapp_evo.patches.migrate_evolution_settings_to_line` executed (or skipped as already-run/no-op if there's no legacy data on this site).

- [ ] **Step 6: Commit**

```bash
git add frappe_whatsapp_evo/patches frappe_whatsapp_evo/patches.txt frappe_whatsapp_evo/frappe_whatsapp_evo/tests/test_migrate_evolution_settings_patch.py
git commit -m "feat(evo-lines): migrate legacy single-instance settings into an Evo Line row"
```

---

### Task 7: `evolution_api_settings.js` — per-line action buttons

**Files:**
- Modify: `frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/evolution_api_settings.js` (full rewrite)

**Interfaces:**
- Consumes: `frappe_whatsapp_evo.api.test_connection(line)`, `configure_webhook(line)`, `fetch_instances(line)`, `get_qr_code(line)` from Task 4 (all require `line` as an `instance_name` string).
- Produces: none consumed by other tasks (leaf UI file).

This task has no automated test (desk-form JS) — verification is manual, per the checklist in Task 9.

- [ ] **Step 1: Rewrite the file to prompt for a line before each action**

`frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/evolution_api_settings.js`:
```javascript
frappe.ui.form.on("Evolution API Settings", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Test Connection"), () => {
			pick_line(frm, (line) => {
				frappe.call({
					method: "frappe_whatsapp_evo.api.test_connection",
					args: { line },
					freeze: true,
					freeze_message: __("Testing Evolution API connection..."),
					callback(r) {
						if (r.message) {
							const state = (r.message.instance && r.message.instance.state) || r.message.state;
							if (state === "open") {
								frappe.show_alert({
									message: __("Connection successful! Instance is open."),
									indicator: "green",
								});
							} else if (state) {
								frappe.msgprint({
									title: __("Connection State"),
									indicator: (state === "connecting" || state === "qr") ? "orange" : "red",
									message: __("Instance connection state is: <strong>{0}</strong>", [state]),
								});
							} else {
								frappe.show_alert({
									message: __("Connection tested successfully."),
									indicator: "green",
								});
							}
							frm.reload_doc();
						}
					},
				});
			});
		});

		frm.add_custom_button(__("Fetch Instances"), () => {
			pick_line(frm, (line) => {
				frappe.call({
					method: "frappe_whatsapp_evo.api.fetch_instances",
					args: { line },
					freeze: true,
					freeze_message: __("Fetching Evolution API instances..."),
					callback(r) {
						if (r.message && Array.isArray(r.message)) {
							const instances = r.message;
							if (instances.length === 0) {
								frappe.msgprint({
									title: __("Evolution API Instances"),
									message: __("No instances found on the Evolution API server."),
								});
								return;
							}
							let html = `<p>${__("Successfully fetched {0} instances:", [instances.length])}</p>`;
							html += '<table class="table table-bordered table-striped" style="margin-top: 10px;">';
							html += `<thead><tr>
								<th>${__("Instance Name")}</th>
								<th>${__("Status")}</th>
							</tr></thead><tbody>`;
							instances.forEach(row => {
								const inst = (row && typeof row.instance === "object") ? row.instance : row;
								if (!inst) return;
								const name = inst.name || inst.instanceName || inst.instanceId || __("Unknown");
								const status = inst.status || inst.connectionStatus || row.connectionStatus || inst.state || __("N/A");
								let status_badge = "";
								if (status === "open" || status === "CONNECTED") {
									status_badge = `<span class="indicator green">${status}</span>`;
								} else if (status === "connecting" || status === "CONNECTING" || status === "qr" || status === "QRCODE") {
									status_badge = `<span class="indicator orange">${status}</span>`;
								} else {
									status_badge = `<span class="indicator red">${status}</span>`;
								}
								html += `<tr>
									<td><strong>${frappe.utils.escape_html(name)}</strong></td>
									<td>${status_badge}</td>
								</tr>`;
							});
							html += '</tbody></table>';

							frappe.msgprint({
								title: __("Evolution API Instances"),
								message: html,
								wide: true,
							});
						} else {
							frappe.show_alert({
								message: __("No instances found or response format unrecognized."),
								indicator: "orange",
							});
						}
					},
				});
			});
		});

		frm.add_custom_button(__("Get QR Code"), () => {
			pick_line(frm, (line) => {
				frappe.call({
					method: "frappe_whatsapp_evo.api.get_qr_code",
					args: { line },
					freeze: true,
					freeze_message: __("Fetching QR code from Evolution API..."),
					callback(r) {
						if (!r.message) return;

						const resp = r.message;
						const qrcode = resp.qrcode || resp;
						const base64 = qrcode.base64 || resp.base64 || "";
						const code = qrcode.code || resp.code || "";
						const pairingCode = qrcode.pairingCode || resp.pairingCode || "";

						if (!base64) {
							const state = resp.instance && resp.instance.state;
							if (state === "open") {
								frappe.show_alert({
									message: __("WhatsApp is already connected — no QR code needed."),
									indicator: "green",
								});
							} else {
								frappe.msgprint({
									title: __("QR Code"),
									indicator: "orange",
									message: __("No QR code returned. Instance state: <strong>{0}</strong>", [state || __("unknown")]),
								});
							}
							return;
						}

						const imgSrc = base64.startsWith("data:") ? base64 : `data:image/png;base64,${base64}`;
						let html = `<div style="text-align:center;">
							<p>${__("Scan this QR code with your WhatsApp app to connect.")}</p>
							<img src="${imgSrc}" style="max-width:300px;width:100%;border:1px solid #ddd;border-radius:4px;" />`;
						if (pairingCode) {
							html += `<p style="margin-top:12px;">${__("Pairing Code:")} <strong>${frappe.utils.escape_html(pairingCode)}</strong></p>`;
						}
						html += `</div>`;

						frappe.msgprint({
							title: __("Scan QR Code"),
							message: html,
							wide: false,
						});
					},
				});
			});
		});

		frm.add_custom_button(__("Configure Webhook"), () => {
			pick_line(frm, (line) => {
				frappe.confirm(
					__(
						"Evolution API normally stores one webhook configuration per instance. This may replace an existing webhook used by another system. Continue?"
					),
					() => {
						frappe.call({
							method: "frappe_whatsapp_evo.api.configure_webhook",
							args: { line },
							freeze: true,
							freeze_message: __("Configuring Evolution API webhook..."),
							callback(r) {
								if (r.message) {
									frappe.show_alert({
										message: __("Webhook configured successfully!"),
										indicator: "green",
									});
									frm.reload_doc();
								}
							},
						});
					}
				);
			});
		});
	},
});

function pick_line(frm, callback) {
	const rows = (frm.doc.evo_lines || []).filter((r) => r.instance_name);
	if (rows.length === 0) {
		frappe.msgprint({
			title: __("No Evo Lines"),
			indicator: "orange",
			message: __("Add at least one Evo Line before using this action."),
		});
		return;
	}
	if (rows.length === 1) {
		callback(rows[0].instance_name);
		return;
	}
	frappe.prompt(
		[
			{
				label: __("Evo Line"),
				fieldname: "line",
				fieldtype: "Select",
				options: rows.map((r) => r.instance_name),
				default: rows[0].instance_name,
				reqd: 1,
			},
		],
		(values) => callback(values.line),
		__("Select Evo Line")
	);
}
```

- [ ] **Step 2: Manual verification**

Run:
```bash
bench --site dev.localhost migrate
bench --site dev.localhost clear-cache
```
Then in the browser: open **Evolution API Settings**, add two Evo Line rows with distinct `instance_name`s, save, and click "Test Connection" — confirm the "Select Evo Line" prompt appears with both instance names, and picking one calls the endpoint with that line (check Network tab payload includes `line: "<chosen instance_name>"`). Remove one row (down to a single line) and confirm the button now skips the prompt and calls immediately.

- [ ] **Step 3: Commit**

```bash
git add frappe_whatsapp_evo/frappe_whatsapp_evo/doctype/evolution_api_settings/evolution_api_settings.js
git commit -m "feat(evo-lines): prompt for a line before running per-instance settings actions"
```

---

### Task 8: "Send via WA" dialog — line dropdown

**Files:**
- Modify: `frappe_whatsapp_evo/public/js/frappe_whatsapp_evo.js` (full rewrite)

**Interfaces:**
- Consumes: `frappe_whatsapp_evo.api.get_available_lines()` (Task 4) and `frappe_whatsapp_evo.api.send_whatsapp_with_media(..., line)` (Task 3).
- Produces: none consumed by other tasks (leaf UI file).

No automated test (desk dialog JS) — verified manually in Step 2.

- [ ] **Step 1: Rewrite the dialog to fetch and require a line first**

`frappe_whatsapp_evo/public/js/frappe_whatsapp_evo.js`:
```javascript
frappe.provide("frappe.whatsapp_evo");

$(document).on("app_ready", function () {
	frappe.router.on("change", () => {
		let route = frappe.get_route();
		if (route && route[0] === "Form") {
			let doctype = route[1];
			let docname = route[2];

			// Skip for configuration and message logs themselves
			if (["Evolution API Settings", "WhatsApp Evo Message"].includes(doctype)) {
				return;
			}

			frappe.ui.form.on(doctype, {
				refresh: function (frm) {
					if (frm.is_new()) return;

					frm.page.add_menu_item(__("Send via WA"), function () {
						frappe.whatsapp_evo.show_send_dialog(frm);
					});
				},
			});
		}
	});
});

frappe.whatsapp_evo.show_send_dialog = function (frm) {
	frappe.call({
		method: "frappe_whatsapp_evo.api.get_available_lines",
		callback: function (r) {
			const lines = r.message || [];
			if (lines.length === 0) {
				frappe.msgprint({
					title: __("No WhatsApp Line Available"),
					indicator: "orange",
					message: __("There are no enabled Evo Lines you have access to. Ask an administrator to add or enable one."),
				});
				return;
			}
			frappe.whatsapp_evo.render_send_dialog(frm, lines);
		},
	});
};

frappe.whatsapp_evo.render_send_dialog = function (frm, lines) {
	let dialog = new frappe.ui.Dialog({
		title: __("Send via WA"),
		fields: [
			{
				label: __("Line"),
				fieldname: "line",
				fieldtype: "Select",
				options: lines,
				default: lines[0],
				reqd: 1,
			},
			{
				label: __("Contact"),
				fieldname: "contact",
				fieldtype: "Link",
				options: "Contact",
				change: function () {
					let contact = dialog.get_value("contact");
					if (contact) {
						frappe.db.get_value("Contact", contact, "mobile_no", (r) => {
							if (r && r.mobile_no) {
								dialog.set_value("mobile_no", r.mobile_no);
							}
						});
					}
				},
			},
			{
				label: __("Mobile Number"),
				fieldname: "mobile_no",
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldtype: "Section Break",
			},
			{
				label: __("Message"),
				fieldname: "message",
				fieldtype: "Small Text",
				reqd: 1,
			},
			{
				label: __("Attachment Type"),
				fieldname: "attach_type",
				fieldtype: "Select",
				options: ["None", "PDF"],
				default: "PDF",
			},
			{
				label: __("Print Format"),
				fieldname: "print_format",
				fieldtype: "Select",
				options: [],
				depends_on: "eval:doc.attach_type != 'None'",
			},
		],
		primary_action_label: __("Send"),
		primary_action: function (values) {
			dialog.hide();
			frappe.show_alert({
				message: __("Sending WhatsApp message..."),
				indicator: "blue"
			}, 3);
			frappe.call({
				method: "frappe_whatsapp_evo.api.send_whatsapp_with_media",
				args: {
					to: values.mobile_no,
					message: values.message,
					line: values.line,
					doctype: frm.doctype,
					name: frm.docname,
					attach_type: values.attach_type === "None" ? null : values.attach_type,
					print_format: values.print_format,
				},
				callback: function (r) {
					if (!r.exc) {
						frappe.show_alert({
							message: __("WhatsApp message sent successfully."),
							indicator: "green"
						}, 5);
					}
				},
				error: function (r) {
					frappe.show_alert({
						message: __("Failed to send WhatsApp message."),
						indicator: "red"
					}, 5);
				},
			});
		},
	});

	// Fetch default contact info
	frappe.call({
		method: "frappe_whatsapp_evo.api.get_contact_info",
		args: {
			doctype: frm.doctype,
			name: frm.docname,
		},
		callback: function (r) {
			if (r.message && r.message.mobile_no) {
				dialog.set_value("mobile_no", r.message.mobile_no);
			}
		},
	});

	// Fetch message preview
	frappe.call({
		method: "frappe_whatsapp_evo.api.get_message_preview",
		args: {
			doctype: frm.doctype,
			name: frm.docname,
		},
		callback: function (r) {
			if (r.message && r.message.message) {
				dialog.set_value("message", r.message.message);
			}
		},
	});

	// Populate Print Formats
	frappe.db.get_list("Print Format", {
		filters: { doc_type: frm.doctype },
		fields: ["name"],
	}).then((r) => {
		if (r && r.length > 0) {
			let options = r.map((pf) => pf.name);
			dialog.set_df_property("print_format", "options", options);
			dialog.set_value("print_format", options[0]);
		}
	});

	dialog.show();
};
```

- [ ] **Step 2: Manual verification**

Run:
```bash
bench --site dev.localhost migrate
bench build --app frappe_whatsapp_evo
bench --site dev.localhost clear-cache
```
Then in the browser, on any non-excluded doctype form (e.g. a Contact or Sales Invoice): open the menu → "Send via WA".
- With 2+ enabled lines you have access to: confirm the "Line" dropdown shows all of them, defaulting to the first.
- With exactly 1 accessible line: confirm the dropdown still shows, preselected, no extra click needed.
- Temporarily add `line_restrictions` rows restricting all lines to a different user, or disable all lines, reload, and confirm the dialog does not open and an orange message explains why.
- Send a text message and confirm the created `WhatsApp Evo Message` has `instance_name` set to the chosen line, and the phone number was normalized correctly (e.g. entering `0725548065` against a line with `default_country_code=254` stores `to_number = 254725548065`).

- [ ] **Step 3: Commit**

```bash
git add frappe_whatsapp_evo/public/js/frappe_whatsapp_evo.js
git commit -m "feat(evo-lines): add line picker to the Send via WA dialog"
```

---

### Task 9: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite**

Run:
```bash
cd /home/kushal/frappe-bench
bench --site dev.localhost run-tests --app frappe_whatsapp_evo
```
Expected: all tests from Tasks 1-6 PASS, zero failures/errors.

- [ ] **Step 2: Run a clean migrate to confirm patch + schema ordering is correct end-to-end**

Run:
```bash
bench --site dev.localhost migrate
```
Expected: completes without error. If this is the first migrate after upgrading a site that had real data in the old single-doctype fields, confirm (via the Evolution API Settings form) that a matching Evo Line row now exists with the original base_url/instance_name/api_key/webhook_secret intact and the connection still tests successfully.

- [ ] **Step 3: Manual QA pass on the full flow in the browser**

Using the checklist from Tasks 7 and 8 (per-line admin buttons, dialog line dropdown with 0/1/2+ lines, disabled-line exclusion, restricted-line exclusion, phone normalization), plus:
- Disable a line that a previously-sent `WhatsApp Evo Message` references, open that message, click "Send" (resend) — confirm it fails with a clear error instead of silently succeeding.
- Re-enable the line and confirm resend now works.

- [ ] **Step 4: Update the design spec status (optional but recommended)**

If any implementation-time deviations from `docs/superpowers/specs/2026-07-10-multi-line-evo-api-settings-design.md` were made (e.g. the `pick_line` prompt-based approach in Task 7 instead of literal per-row grid buttons), add a short "Implementation notes" section to the bottom of that spec file documenting the deviation and why.

- [ ] **Step 5: Final commit**

```bash
git status
git add -A
git commit -m "chore(evo-lines): final verification pass for multi-line Evo API settings"
```
(Only commit if `git status` shows uncommitted changes beyond what Tasks 1-8 already committed — e.g. the spec update from Step 4.)
