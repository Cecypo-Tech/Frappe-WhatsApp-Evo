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

	def test_send_media_disabled_line_blocked(self):
		_add_line("TEST-SEND-MEDIA-DISABLED", disabled=1)

		with self.assertRaises(frappe.ValidationError):
			api.send_media(
				to="0725548065",
				media="aGVsbG8=",
				mediatype="image",
				mimetype="image/png",
				filename="hi.png",
				line="TEST-SEND-MEDIA-DISABLED",
			)

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


class TestSendWithMediaPdfFailure(IntegrationTestCase):
	"""A print format that cannot render must not reach the user as a traceback."""

	def setUp(self):
		self.note = frappe.get_doc(
			{"doctype": "Note", "title": f"_WA PDF {frappe.generate_hash(length=8)}", "public": 1}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Note", self.note.name, force=True, ignore_permissions=True)
		settings = frappe.get_single("Evolution API Settings")
		settings.evo_lines = [r for r in settings.evo_lines if not r.instance_name.startswith("TEST-")]
		settings.save(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- test fixture must be visible to later queries

	@patch("frappe.get_print")
	def test_pdf_failure_raises_a_readable_error(self, mock_get_print):
		# What wkhtmltopdf actually surfaces when an <img> cannot be loaded.
		mock_get_print.side_effect = OSError("wkhtmltopdf reported an error:\nExit with code 1")
		_add_line("TEST-PDF-FAIL")

		with self.assertRaises(frappe.ValidationError) as caught:
			api.send_whatsapp_with_media(
				to="0725548065",
				message="hi",
				doctype="Note",
				name=self.note.name,
				line="TEST-PDF-FAIL",
				attach_type="PDF",
			)

		message = str(caught.exception)
		self.assertIn("Could not generate the PDF", message)
		self.assertIn("Nothing was sent", message)

	@patch("frappe.get_print")
	def test_pdf_failure_is_recorded_as_a_failed_message(self, mock_get_print):
		mock_get_print.side_effect = OSError("wkhtmltopdf reported an error:\nExit with code 1")
		_add_line("TEST-PDF-LOG")

		with self.assertRaises(frappe.ValidationError):
			api.send_whatsapp_with_media(
				to="0725548065",
				message="hi",
				doctype="Note",
				name=self.note.name,
				line="TEST-PDF-LOG",
				attach_type="PDF",
			)

		log = frappe.get_all(
			"WhatsApp Evo Message",
			filters={"reference_doctype": "Note", "reference_name": self.note.name},
			fields=["status", "error"],
		)
		self.assertEqual(len(log), 1)
		self.assertEqual(log[0].status, "Failed")
		self.assertIn("PDF generation failed", log[0].error)

	@patch("frappe.get_print")
	def test_unusable_line_fails_before_the_pdf_is_rendered(self, mock_get_print):
		"""Rendering a PDF is expensive; an unusable line should fail first."""
		_add_line("TEST-PDF-DISABLED", disabled=1)

		with self.assertRaises(frappe.ValidationError):
			api.send_whatsapp_with_media(
				to="0725548065",
				message="hi",
				doctype="Note",
				name=self.note.name,
				line="TEST-PDF-DISABLED",
				attach_type="PDF",
			)

		mock_get_print.assert_not_called()

