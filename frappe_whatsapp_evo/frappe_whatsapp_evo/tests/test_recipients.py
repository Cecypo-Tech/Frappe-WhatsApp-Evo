"""Tests for recipient resolution and the permission gates around it.

Two things are pinned here. First, that resolution actually walks out to the
document's party - the number is almost never on the transaction itself, and
the old lookup returned "" for the common case. Second, that a user who cannot
read a document cannot pull its phone numbers or totals out of the whitelisted
endpoints.
"""

import frappe
from frappe.tests import IntegrationTestCase

from frappe_whatsapp_evo.frappe_whatsapp_evo import api
from frappe_whatsapp_evo.frappe_whatsapp_evo.recipients import (
	digits,
	get_party,
	get_recipient_candidates,
)

CUSTOMER = "_WA Test Customer"
PRIMARY_MOBILE = "+254712000001"
SECOND_MOBILE = "+254712000002"
CUSTOMER_MOBILE = "+254712000003"


def _make_contact(first_name: str, mobile: str, customer: str) -> str:
	"""Create a Contact carrying `mobile`.

	The number must go through `phone_nos`: Contact.mobile_no is derived from
	that child table on save, so a value assigned to the column directly is
	discarded.
	"""
	contact = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"phone_nos": [{"phone": mobile, "is_primary_mobile_no": 1}],
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		}
	).insert(ignore_permissions=True)
	return contact.name


class TestRecipientResolution(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Individual"}
			).insert(ignore_permissions=True)

		cls.primary = _make_contact("_WAPrimary", PRIMARY_MOBILE, CUSTOMER)
		cls.second = _make_contact("_WASecond", SECOND_MOBILE, CUSTOMER)
		frappe.db.set_value("Customer", CUSTOMER, "customer_primary_contact", cls.primary)
		frappe.db.set_value("Customer", CUSTOMER, "mobile_no", CUSTOMER_MOBILE)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- fixtures must survive per-test rollback

	@classmethod
	def tearDownClass(cls):
		for name in (cls.primary, cls.second):
			frappe.delete_doc("Contact", name, force=True, ignore_permissions=True)
		frappe.delete_doc("Customer", CUSTOMER, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- undo the committed fixtures
		super().tearDownClass()

	def numbers(self, doctype, name):
		return [c["mobile_no"] for c in get_recipient_candidates(doctype, name)]

	def test_customer_resolves_its_own_contacts(self):
		self.assertIn(PRIMARY_MOBILE, self.numbers("Customer", CUSTOMER))

	def test_primary_contact_outranks_other_contacts(self):
		found = self.numbers("Customer", CUSTOMER)
		self.assertLess(found.index(PRIMARY_MOBILE), found.index(SECOND_MOBILE))

	def test_every_linked_contact_is_offered(self):
		self.assertIn(SECOND_MOBILE, self.numbers("Customer", CUSTOMER))

	def test_party_own_number_is_included_last(self):
		found = self.numbers("Customer", CUSTOMER)
		self.assertIn(CUSTOMER_MOBILE, found)
		self.assertGreater(found.index(CUSTOMER_MOBILE), found.index(PRIMARY_MOBILE))

	def test_candidates_are_labelled_and_sourced(self):
		top = get_recipient_candidates("Customer", CUSTOMER)[0]
		self.assertIn("_WAPrimary", top["label"])
		self.assertEqual(top["source"], "Primary Contact")
		self.assertEqual(top["contact"], self.primary)

	def test_duplicate_numbers_are_collapsed(self):
		"""The same number spelled differently must appear once."""
		dupe = _make_contact("_WADupe", PRIMARY_MOBILE.replace("+", "00"), CUSTOMER)
		try:
			found = self.numbers("Customer", CUSTOMER)
			self.assertEqual(len([n for n in found if digits(n) == digits(PRIMARY_MOBILE)]), 1)
		finally:
			frappe.delete_doc("Contact", dupe, force=True, ignore_permissions=True)

	def test_customer_with_no_contacts_returns_empty_not_error(self):
		"""The old lookup filtered on `links`, a child table, and raised
		OperationalError (1054, "Unknown column 'links'")."""
		lonely = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_WA Lonely", "customer_type": "Individual"}
		).insert(ignore_permissions=True)
		try:
			self.assertEqual(get_recipient_candidates("Customer", lonely.name), [])
			self.assertEqual(api.get_contact_info("Customer", lonely.name)["mobile_no"], "")
		finally:
			frappe.delete_doc("Customer", lonely.name, force=True, ignore_permissions=True)

	def test_get_contact_info_keeps_the_flat_mobile_no_key(self):
		out = api.get_contact_info("Customer", CUSTOMER)
		self.assertEqual(out["mobile_no"], out["candidates"][0]["mobile_no"])
		self.assertEqual(out["party_doctype"], "Customer")
		self.assertEqual(out["party"], CUSTOMER)


class TestGetParty(IntegrationTestCase):
	def test_party_doctype_is_its_own_party(self):
		doc = frappe._dict(doctype="Customer", name="ACME", get=lambda f, d=None: None)
		self.assertEqual(get_party(doc), ("Customer", "ACME"))

	def test_customer_link_field(self):
		doc = frappe._dict(doctype="Sales Invoice", name="INV-1", customer="ACME")
		self.assertEqual(get_party(doc), ("Customer", "ACME"))

	def test_supplier_link_field(self):
		doc = frappe._dict(doctype="Purchase Invoice", name="PINV-1", supplier="SUPP")
		self.assertEqual(get_party(doc), ("Supplier", "SUPP"))

	def test_explicit_party_type_pair_wins(self):
		doc = frappe._dict(doctype="Payment Entry", name="PE-1", party_type="Supplier", party="SUPP")
		self.assertEqual(get_party(doc), ("Supplier", "SUPP"))

	def test_document_with_no_party(self):
		doc = frappe._dict(doctype="Note", name="N-1")
		self.assertEqual(get_party(doc), (None, None))


class TestEndpointPermissions(IntegrationTestCase):
	"""A user who cannot read a document must not reach its data through these."""

	EMAIL = "_wa-no-roles@example.com"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("User", cls.EMAIL):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.EMAIL,
					"first_name": "_WA NoRoles",
					"send_welcome_email": 0,
					"user_type": "System User",
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- fixture must survive per-test rollback

	@classmethod
	def tearDownClass(cls):
		frappe.delete_doc("User", cls.EMAIL, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- undo the committed fixture
		super().tearDownClass()

	def setUp(self):
		self.note = frappe.get_doc(
			{"doctype": "Note", "title": f"_WA Perm {frappe.generate_hash(length=8)}", "public": 0}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.delete_doc("Note", self.note.name, force=True, ignore_permissions=True)

	def test_get_contact_info_is_denied(self):
		frappe.set_user(self.EMAIL)
		self.assertFalse(frappe.has_permission("Note", "read", doc=self.note.name))
		with self.assertRaises(frappe.PermissionError):
			api.get_contact_info("Note", self.note.name)

	def test_get_message_preview_is_denied(self):
		frappe.set_user(self.EMAIL)
		with self.assertRaises(frappe.PermissionError):
			api.get_message_preview("Note", self.note.name)

	def test_send_with_unreadable_reference_is_denied(self):
		"""Blocked before any line lookup or outbound call."""
		frappe.set_user(self.EMAIL)
		with self.assertRaises(frappe.PermissionError):
			api.send_whatsapp_with_media(
				to="254712000000",
				message="hi",
				doctype="Note",
				name=self.note.name,
				line="TEST-NOT-USED",
			)

	def test_send_text_with_unreadable_reference_is_denied(self):
		frappe.set_user(self.EMAIL)
		with self.assertRaises(frappe.PermissionError):
			api.send_text(
				to="254712000000",
				message="hi",
				line="TEST-NOT-USED",
				reference_doctype="Note",
				reference_name=self.note.name,
			)

	def test_administrator_is_unaffected(self):
		self.assertIn("mobile_no", api.get_contact_info("Note", self.note.name))


class TestSendContext(IntegrationTestCase):
	"""The dialog opens on one round trip instead of four."""

	def setUp(self):
		self.note = frappe.get_doc(
			{"doctype": "Note", "title": f"_WA Ctx {frappe.generate_hash(length=8)}", "public": 1}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.delete_doc("Note", self.note.name, force=True, ignore_permissions=True)

	def test_returns_everything_the_dialog_needs(self):
		context = api.get_send_context("Note", self.note.name)

		self.assertEqual(
			sorted(context.keys()), ["lines", "preview", "print_formats", "recipients"]
		)
		self.assertIn("mobile_no", context["recipients"])
		self.assertIn("candidates", context["recipients"])
		self.assertIn("message", context["preview"])
		self.assertIsInstance(context["print_formats"], list)

	def test_print_formats_are_scoped_to_the_doctype(self):
		names = api.get_send_context("Note", self.note.name)["print_formats"]
		for name in names:
			self.assertEqual(frappe.db.get_value("Print Format", name, "doc_type"), "Note")

	def test_disabled_print_formats_are_not_offered(self):
		pf = frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": "_WA Disabled Format",
				"doc_type": "Note",
				"print_format_type": "Jinja",
				"html": "<div>x</div>",
				"disabled": 1,
			}
		).insert(ignore_permissions=True)
		try:
			self.assertNotIn(pf.name, api.get_send_context("Note", self.note.name)["print_formats"])
		finally:
			frappe.delete_doc("Print Format", pf.name, force=True, ignore_permissions=True)

	def test_is_denied_without_read_permission(self):
		email = TestEndpointPermissions.EMAIL
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "_WA NoRoles",
					"send_welcome_email": 0,
					"user_type": "System User",
				}
			).insert(ignore_permissions=True)
		private = frappe.get_doc(
			{"doctype": "Note", "title": f"_WA Priv {frappe.generate_hash(length=8)}", "public": 0}
		).insert(ignore_permissions=True)
		try:
			frappe.set_user(email)
			with self.assertRaises(frappe.PermissionError):
				api.get_send_context("Note", private.name)
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("Note", private.name, force=True, ignore_permissions=True)

