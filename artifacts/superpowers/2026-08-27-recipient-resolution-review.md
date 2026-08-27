# frappe_whatsapp_evo — review and plan (2026-08-27)

## Review findings

All verified against `dev.localhost` with rolled-back transactions.

### Blocker 1 — `get_contact_info` crashes on Customer/Supplier/Lead with no linked Contact
`api.py:317` filters on `links`, a child table, not a column:
```
get_contact_info('Customer', 'Customer A')
  -> OperationalError (1054, "Unknown column 'links' in 'WHERE'")
```
"Send via WA" returns 500 on those records. The `%name%` substring match is
also wrong: `CUST-001` would match `CUST-0010`.

### Blocker 2 — `get_contact_info` / `get_message_preview` leak data
No permission check. As a user with zero roles who cannot read the invoice:
```
can read Sales Invoice? False
  get_contact_info    -> {'mobile_no': '+254712555000'}
  get_message_preview -> {'party': 'Mike Jones', 'amount': 696.0, ...}
```
The PDF path is safe — `frappe.get_print` raises PermissionError on its own.

### Major 3 — send endpoints do not check the referenced document
`send_text` / `send_media` / `send_whatsapp_with_media` accept any
`reference_doctype`/`reference_name`. `_insert_message_log` then posts a
Comment with `ignore_permissions=True`, so comments can be forged on
documents the caller cannot read.

### Major 4 — the party is never consulted
With `contact_person` cleared on INV-00020, the customer's number is present in
three places and none are found:
```
customer mobile_no       : +254712555000
customer primary contact : Mike Jones-Mike Jones
linked contact mobile    : +254712555000
>> get_contact_info -> {'mobile_no': ''}
```
Step 3 only looks for a Contact linked to the Sales Invoice itself, which
never exists in ERPNext.

### Minor 5 — dialog Contact field is unfiltered
Searches every Contact rather than those linked to the document's party.

### Minor 6 — only `mobile_no` is read
Contact also carries `phone` and the `phone_nos` child table
(`phone`, `is_primary_phone`, `is_primary_mobile_no`).

### Nit 7 — webhook token compare is not constant-time
`api.py:441` uses `==`; `hmac.compare_digest` is a drop-in.

## Plan

1. New `recipients.py`: party resolution + ranked candidate collection.
   Rank: document contact_person > document fields > party primary contact >
   other linked contacts > party's own mobile_no. Dedupe on digits.
2. `get_contact_info` returns `{mobile_no, candidates[], party_doctype, party}`;
   `mobile_no` stays the top pick for backwards compatibility.
3. Permission gate on get_contact_info, get_message_preview, send_text,
   send_media, send_whatsapp_with_media.
4. `hmac.compare_digest` for the webhook token.
5. Dialog: Recipient select built from candidates, Contact link filtered to the
   party via `frappe.contacts.doctype.contact.contact.contact_query`.
6. Tests per item.

## Verification
- `bench --site dev.localhost run-tests --app frappe_whatsapp_evo`
- Re-run the probes above; the crash, both leaks and the empty resolution
  must all be gone.
