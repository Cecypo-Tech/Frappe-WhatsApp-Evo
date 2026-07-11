import base64
import json
from urllib.parse import urlencode

import frappe
from frappe import _

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


def get_settings():
	return frappe.get_single("Evolution API Settings")


def _set_single_value(fieldname: str, value):
	frappe.db.set_single_value("Evolution API Settings", fieldname, value)


def get_webhook_url() -> str:
	settings = get_settings()
	token = settings.get_password("webhook_secret") if settings.webhook_secret else None
	query = f"?{urlencode({'token': token})}" if token else ""
	return frappe.utils.get_url(f"/api/method/frappe_whatsapp_evo.api.webhook{query}")


def _as_json(value) -> str:
	if isinstance(value, str):
		return value
	return frappe.as_json(value)


def _extract_text(data: dict) -> str | None:
	message = data.get("message") if isinstance(data.get("message"), dict) else {}
	if message.get("conversation"):
		return message.get("conversation")

	for key in ("extendedTextMessage", "imageMessage", "videoMessage", "documentMessage"):
		value = message.get(key)
		if isinstance(value, dict):
			return value.get("text") or value.get("caption") or value.get("fileName")

	return data.get("text") or data.get("messageText")


def _extract_message_payload(payload: dict) -> dict:
	data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
	key = data.get("key") if isinstance(data.get("key"), dict) else {}
	remote_jid = key.get("remoteJid") or data.get("remoteJid") or data.get("from")
	from_me = bool(key.get("fromMe") or data.get("fromMe"))
	message_id = key.get("id") or data.get("id") or data.get("messageId")

	return {
		"data": data,
		"remote_jid": remote_jid,
		"from_me": from_me,
		"message_id": message_id,
		"text": _extract_text(data),
	}


def _insert_message_log(
	direction: str,
	status: str,
	to: str | None = None,
	from_number: str | None = None,
	message: str | None = None,
	message_type: str = "text",
	media_url: str | None = None,
	response_json: dict | None = None,
	raw_payload: dict | None = None,
	error: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	webhook_event: str | None = None,
	instance_name: str | None = None,
):
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Evo Message",
			"direction": direction,
			"status": status,
			"to_number": to,
			"from_number": from_number,
			"message": message,
			"message_type": message_type,
			"media_url": media_url,
			"evolution_message_id": get_message_id(response_json) if response_json else None,
			"response_json": _as_json(response_json) if response_json else None,
			"raw_payload": _as_json(raw_payload) if raw_payload else None,
			"error": error,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"webhook_event": webhook_event,
			"instance_name": instance_name,
		}
	)
	doc.insert(ignore_permissions=True)

	if direction == "Outgoing" and reference_doctype and reference_name:
		try:
			recipient = to or ""
			if status == "Failed":
				comment_text = f"❌ <b>WhatsApp message to {recipient} failed:</b><br>{error or ''}"
			else:
				msg_text = message or ""
				attachment_info = f" ({message_type})" if message_type != "text" else ""
				comment_text = f"💬 <b>WhatsApp message sent to {recipient}{attachment_info}:</b><br>{msg_text}"

			comment = frappe.new_doc("Comment")
			comment.update(
				{
					"comment_type": "Comment",
					"reference_doctype": reference_doctype,
					"reference_name": reference_name,
					"comment_email": frappe.session.user or "Administrator",
					"comment_by": frappe.session.user_fullname or "System",
					"content": comment_text,
				}
			)
			comment.insert(ignore_permissions=True)
		except Exception:
			# Prevent logging failure from blocking the primary transaction
			frappe.log_error(title="WA Message Comment Logging Failed")

	return doc


@frappe.whitelist()
def fetch_instances():
	return EvolutionAPIClient().fetch_instances()


@frappe.whitelist()
def get_qr_code():
	return EvolutionAPIClient().get_qr_code()


@frappe.whitelist()
def diagnose_webhook_routes():
	client = EvolutionAPIClient()
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


@frappe.whitelist()
def test_connection():
	client = EvolutionAPIClient()
	result = client.get_connection_state()

	_set_single_value("last_connection_state", frappe.as_json(result))
	_set_single_value("last_tested_on", frappe.utils.now_datetime())

	return result


@frappe.whitelist()
def configure_webhook():
	client = EvolutionAPIClient()
	url = get_webhook_url()
	result = client.set_webhook(url)
	safe_result = redact_secrets(result)

	_set_single_value("webhook_url", url)
	_set_single_value("last_webhook_response", frappe.as_json(safe_result))

	return {"webhook_url": url, "response": safe_result}


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


@frappe.whitelist()
def get_contact_info(doctype: str, name: str):
	"""Try to find a mobile number for the given document."""
	doc = frappe.get_doc(doctype, name)
	
	# 1. Direct fields
	for fieldname in ["mobile_no", "phone", "contact_mobile", "contact_phone", "whatsapp_no"]:
		val = doc.get(fieldname)
		if val:
			return {"mobile_no": val}

	# 2. Check for contact_person
	if doc.get("contact_person"):
		contact = frappe.get_doc("Contact", doc.contact_person)
		if contact.mobile_no:
			return {"mobile_no": contact.mobile_no}

	# 3. Check for linked Contact
	contact_name = frappe.db.get_value("Dynamic Link", 
		{"link_doctype": doctype, "link_name": name, "parenttype": "Contact"}, 
		"parent"
	)
	if contact_name:
		mobile = frappe.db.get_value("Contact", contact_name, "mobile_no")
		if mobile:
			return {"mobile_no": mobile}

	# 4. Fallback for Customer/Supplier/Lead
	if doctype in ["Customer", "Supplier", "Lead"]:
		contact_name = frappe.db.get_value("Contact", {"links": ["like", f"%{name}%"]}, "name")
		if contact_name:
			mobile = frappe.db.get_value("Contact", contact_name, "mobile_no")
			if mobile:
				return {"mobile_no": mobile}

	return {"mobile_no": ""}


@frappe.whitelist()
def get_message_preview(doctype: str, name: str):
	"""Generate a smart preview message for the document."""
	doc = frappe.get_doc(doctype, name)
	
	# Field Heuristics
	party = next((doc.get(f) for f in ["customer_name", "party_name", "supplier_name", "lead_name"] if doc.get(f)), "")
	amount = next((doc.get(f) for f in ["grand_total", "total", "amount"] if doc.get(f)), 0.0)
	date = next((doc.get(f) for f in ["transaction_date", "posting_date"] if doc.get(f)), doc.creation)
	currency = doc.get("currency") or frappe.db.get_default("currency") or ""
	
	# Format values
	formatted_amount = frappe.format(amount, {"fieldtype": "Currency", "options": currency})
	formatted_date = frappe.format(date, {"fieldtype": "Date"})
	
	# Construct Message
	greeting = _("Hello {0},").format(party) if party else _("Hello,")
	doc_title = _(doctype)
	
	message = f"{greeting}\n\n"
	message += _("Please find attached {0} *{1}* dated {2}.").format(doc_title, name, formatted_date)
	if amount:
		message += f"\n" + _("Total Amount: *{0}*").format(formatted_amount)
	
	message += f"\n\n" + _("Regards,") + f"\n{frappe.session.user_fullname or 'System'}"
	
	return {
		"message": message,
		"party": party,
		"amount": amount,
		"date": formatted_date,
		"currency": currency
	}


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


def _validate_webhook_request():
	settings = get_settings()
	expected = settings.get_password("webhook_secret") if settings.webhook_secret else None
	if not expected:
		return

	received = (
		frappe.form_dict.get("token")
		or frappe.get_request_header("X-Webhook-Secret")
		or frappe.get_request_header("X-Evolution-Webhook-Secret")
	)
	if received != expected:
		frappe.throw(_("Invalid webhook token"), frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def webhook():
	_validate_webhook_request()

	payload = frappe.local.form_dict
	if frappe.request and frappe.request.data:
		try:
			payload = json.loads(frappe.request.data)
		except ValueError:
			payload = dict(frappe.local.form_dict)

	event = payload.get("event")
	instance_name = payload.get("instance")
	extracted = _extract_message_payload(payload)
	data = extracted["data"]
	remote_number = normalize_phone(extracted["remote_jid"] or "", get_settings().default_country_code) if extracted["remote_jid"] else None
	direction = "Outgoing" if extracted["from_me"] else "Incoming"

	existing = None
	if extracted["message_id"]:
		existing = frappe.db.exists("WhatsApp Evo Message", {"evolution_message_id": extracted["message_id"]})

	if existing:
		doc = frappe.get_doc("WhatsApp Evo Message", existing)
		if event == "MESSAGES_UPDATE":
			update_status = (data.get("update") or {}).get("status") or data.get("status")
			doc.status = update_status or "Updated"
		doc.raw_payload = _as_json(payload)
		doc.webhook_event = event
		doc.save(ignore_permissions=True)
	else:
		doc = _insert_message_log(
			direction=direction,
			status="Received" if direction == "Incoming" else data.get("status") or "Sent",
			to=None if direction == "Incoming" else remote_number,
			from_number=remote_number if direction == "Incoming" else None,
			message=extracted["text"],
			message_type=data.get("messageType") or "text",
			raw_payload=payload,
			webhook_event=event,
			instance_name=instance_name,
		)
		doc.db_set("evolution_message_id", extracted["message_id"], update_modified=False)

	frappe.db.commit()
	return {"ok": True, "message_log": doc.name}
