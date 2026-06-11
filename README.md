# Frappe Whatsapp Evo

Simple Evolution API integration for Frappe/ERPNext v16.

## Features

- Store Evolution API base URL, instance name, and API key in a single settings DocType.
- Test the configured instance using Evolution API's connection state endpoint.
- Send WhatsApp text messages through `message/sendText/{instance}`.
- Send media messages through `message/sendMedia/{instance}`.
- Register a Frappe webhook URL on the Evolution API instance.
- Log incoming and outgoing payloads in `WhatsApp Evo Message`.

## Installation

```bash
cd /home/frappeuser/bench16
bench get-app /home/frappeuser/bench16/apps/frappe_whatsapp_evo
bench --site your-site install-app frappe_whatsapp_evo
bench --site your-site migrate
```

If the app is already present in `apps.txt`, install it directly:

```bash
bench --site your-site install-app frappe_whatsapp_evo
bench --site your-site migrate
```

## Setup

1. Open **Evolution API Settings**.
2. Enter the Evolution API base URL, instance name, and API key.
3. Save, then click **Test Connection**.
4. Click **Configure Webhook** only if this Frappe app should own the Evolution API webhook for the instance.

The webhook endpoint is:

```text
/api/method/frappe_whatsapp_evo.api.webhook
```

The settings form generates a secret token and appends it to the webhook URL configured on Evolution API.

If the Evolution API instance already sends webhooks to another system, do not overwrite it unless that is intended. Use the existing system to forward events to Frappe, or place a small webhook fan-out/proxy in front of both systems.

## API

Send a text message:

```python
frappe.call(
    "frappe_whatsapp_evo.api.send_text",
    to="254700000000",
    message="Hello from Frappe",
)
```

Send a media message:

```python
frappe.call(
    "frappe_whatsapp_evo.api.send_media",
    to="254700000000",
    media="https://example.com/invoice.pdf",
    mediatype="document",
    mimetype="application/pdf",
    filename="invoice.pdf",
    caption="Invoice attached",
)
```

## License

MIT
