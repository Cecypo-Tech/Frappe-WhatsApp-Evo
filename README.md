# Frappe Whatsapp Evo

Simple Evolution API integration for Frappe/ERPNext v16.

## Requirements

You must have a running instance of the [Evolution API](https://github.com/evolution-api/evolution-api) to use this integration.

> [!WARNING]
> **Using the Evolution API carries a high risk of WhatsApp account suspension or permanent bans.**
> Because it is an unofficial integration that reverse-engineers WhatsApp Web, it violates WhatsApp's Terms of Service. Bans often happen without prior warning, especially during routine Meta protocol updates.

## Features

- Store Evolution API base URL, instance name, and API key in a single settings DocType.
- Test the configured instance using Evolution API's connection state endpoint.
- Send WhatsApp text messages through `message/sendText/{instance}`.
- Send media messages through `message/sendMedia/{instance}`.
- Register a Frappe webhook URL on the Evolution API instance.
- Log incoming and outgoing payloads in `WhatsApp Evo Message`.

## Screenshots

![Evolution API Settings](https://i.imgur.com/8INGulk.png)

![Send WhatsApp Dialog](https://i.imgur.com/RYHXoOT.png)

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

## Disclaimer

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## License

MIT
