import re

import frappe
import requests
from frappe import _


def normalize_phone(number: str, default_country_code: str | None = None) -> str:
	if not number:
		frappe.throw(_("Phone number is required"))

	raw = str(number).strip()
	if "@" in raw:
		raw = raw.split("@", 1)[0]

	digits = re.sub(r"\D", "", raw)
	if not digits:
		frappe.throw(_("Phone number must contain digits"))

	if raw.startswith("+"):
		return digits

	if digits.startswith("00"):
		return digits[2:]

	default_country_code = re.sub(r"\D", "", default_country_code or "")
	if default_country_code and digits.startswith("0"):
		return f"{default_country_code}{digits[1:]}"

	return digits


def get_password_value(doc, fieldname: str) -> str | None:
	try:
		return doc.get_password(fieldname)
	except Exception:
		return doc.get(fieldname)


def get_message_id(response: dict | None) -> str | None:
	if not isinstance(response, dict):
		return None

	key = response.get("key")
	if isinstance(key, dict) and key.get("id"):
		return key.get("id")

	return response.get("messageId") or response.get("id")


def redact_secrets(value):
	if isinstance(value, dict):
		return {
			key: "*****" if key.lower() in {"apikey", "api_key", "authorization", "token"} else redact_secrets(item)
			for key, item in value.items()
		}
	if isinstance(value, list):
		return [redact_secrets(item) for item in value]
	return value


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

	def request(self, method: str, path: str, payload: dict | None = None) -> dict:
		path = path.lstrip("/")
		url = f"{self.base_url}/{path}"
		headers = {
			"Content-Type": "application/json",
			"apikey": self.api_key,
		}

		try:
			response = requests.request(method, url, json=payload, headers=headers, timeout=self.timeout)
		except requests.RequestException as exc:
			frappe.log_error(message=str(exc), title="Evolution API Request Error")
			frappe.throw(_("Evolution API request failed: {0}").format(str(exc)))

		response_text = response.text or ""
		try:
			data = response.json() if response_text else {}
		except ValueError:
			data = {"response_text": response_text}

		if response.status_code >= 400:
			frappe.log_error(
				message=frappe.as_json(
					{
						"url": url,
						"status_code": response.status_code,
						"response": data,
					}
				),
				title="Evolution API HTTP Error",
			)
			detail = data.get("message") or data.get("error") or data.get("response_text") or response_text
			message = _("Evolution API returned HTTP {0} for /{1}").format(response.status_code, path)
			if detail:
				message = f"{message}<br><pre>{frappe.utils.escape_html(str(detail)[:1000])}</pre>"
			frappe.throw(message)

		return data

	def request_or_error(self, method: str, path: str, payload: dict | None = None) -> tuple[dict | None, str | None]:
		try:
			return self.request(method, path, payload), None
		except Exception as exc:
			return None, str(exc)

	def fetch_instances(self) -> dict:
		return self.request("GET", "/instance/fetchInstances")

	def get_current_webhook(self) -> dict:
		return self.request("GET", f"/webhook/find/{self.get_route_instance_name()}")

	def get_route_instance_name(self) -> str:
		identifier = self.instance_identifier
		instances = self.fetch_instances()
		if not isinstance(instances, list):
			return identifier

		for row in instances:
			instance = row.get("instance") if isinstance(row, dict) and isinstance(row.get("instance"), dict) else row
			if not isinstance(instance, dict):
				continue

			names = [instance.get("name"), instance.get("instanceName")]
			identifiers = [
				instance.get("name"),
				instance.get("instanceName"),
				instance.get("id"),
				instance.get("instanceId"),
				instance.get("token"),
			]

			if identifier in [value for value in identifiers if value]:
				return next((value for value in names if value), identifier)

		return identifier

	def get_connection_state(self) -> dict:
		return self.request("GET", f"/instance/connectionState/{self.get_route_instance_name()}")

	def get_qr_code(self) -> dict:
		return self.request("GET", f"/instance/connect/{self.get_route_instance_name()}")

	def send_text(self, to: str, message: str, delay: int | None = None, link_preview: bool = True) -> dict:
		if not message:
			frappe.throw(_("Message is required"))

		payload = {
			"number": normalize_phone(to, self.settings.default_country_code),
			"text": message,
			"linkPreview": bool(link_preview),
		}
		if delay is not None:
			payload["delay"] = int(delay)

		return self.request("POST", f"/message/sendText/{self.get_route_instance_name()}", payload)

	def send_media(
		self,
		to: str,
		media: str,
		mediatype: str,
		mimetype: str,
		filename: str,
		caption: str | None = None,
		delay: int | None = None,
	) -> dict:
		if not media:
			frappe.throw(_("Media URL or base64 content is required"))
		if mediatype not in {"image", "video", "document"}:
			frappe.throw(_("Media Type must be image, video, or document"))

		payload = {
			"number": normalize_phone(to, self.settings.default_country_code),
			"mediatype": mediatype,
			"mimetype": mimetype,
			"caption": caption or "",
			"media": media,
			"fileName": filename,
		}
		if delay is not None:
			payload["delay"] = int(delay)

		return self.request("POST", f"/message/sendMedia/{self.get_route_instance_name()}", payload)

	def set_webhook(self, url: str, events: list[str] | None = None, webhook_base64: bool = True) -> dict:
		route = f"/webhook/set/{self.get_route_instance_name()}"
		events = events or ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "SEND_MESSAGE", "CONNECTION_UPDATE"]

		# 1. Check if already configured correctly
		try:
			current = self.get_current_webhook()
			if isinstance(current, dict) and current.get("url") == url and current.get("enabled"):
				return current
		except Exception:
			pass

		# 2. Try various payloads
		payloads = self.get_webhook_payloads(url, events, webhook_base64)
		errors = []
		for payload in payloads:
			try:
				result = self.request("POST", route, payload)
				if result is not None:
					return result
			except Exception as exc:
				errors.append(str(exc))

		# 3. Final check (maybe a "failed" request actually worked)
		try:
			current = self.get_current_webhook()
			if isinstance(current, dict) and current.get("url") == url:
				return current
		except Exception:
			pass

		frappe.throw(_("Evolution API rejected all supported webhook payloads:<br>{0}").format("<br>".join(errors)))

	def get_webhook_payloads(
		self, url: str, events: list[str] | None = None, webhook_base64: bool = True
	) -> list[dict]:
		events = events or ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "SEND_MESSAGE", "CONNECTION_UPDATE"]
		return [
			{
				"enabled": True,
				"url": url,
				"webhookByEvents": True,
				"webhookBase64": False,
				"events": ["MESSAGES_UPSERT"],
			},
			{
				"enabled": True,
				"url": url,
				"webhookByEvents": False,
				"webhookBase64": bool(webhook_base64),
				"events": events,
			},
			{
				"enabled": True,
				"url": url,
				"webhookByEvents": False,
				"webhookBase64": bool(webhook_base64),
				"events": ["MESSAGES_UPSERT"],
			},
			{
				"enabled": True,
				"url": url,
				"webhook_by_events": False,
				"webhook_base64": bool(webhook_base64),
				"events": ["MESSAGES_UPSERT"],
			},
			{
				"enabled": True,
				"url": url,
				"webhookByEvents": True,
				"webhookBase64": False,
				"events": ["MESSAGES_UPSERT"],
			},
			{
				"url": url,
				"enabled": True,
				"events": ["MESSAGES_UPSERT"],
			},
			{
				"url": url,
				"events": ["MESSAGES_UPSERT"],
			},
			{
				"webhook": {
					"enabled": True,
					"url": url,
					"webhookByEvents": False,
					"webhookBase64": bool(webhook_base64),
					"events": ["MESSAGES_UPSERT"],
				}
			},
		]
