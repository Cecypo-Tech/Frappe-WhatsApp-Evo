# Multi-Line Evo API Settings — Design

## Problem

`Evolution API Settings` is a Frappe Single doctype: it can only ever hold one
Evolution API connection (one WhatsApp number/instance). Every backend
function (`EvolutionAPIClient`, `get_settings()`, the webhook handler, the
"Send via WA" dialog) is hard-wired to that one record.

We need to support multiple WhatsApp "lines" (multiple Evolution API
instances/numbers) configured in one place, with:
- the ability to disable a line without deleting it
- the ability to restrict a line to specific users ("Limited to Users"),
  defaulting to open access when no users are listed
- a line picker in the "Send via WA" dialog
- correct phone number normalization per line's country code (e.g.
  `0725548065` + default country code `254` → `254725548065`; the same
  generic rule must work for any country, e.g. `91` for India)
- a compact 2-column line edit form

## Data model

> **Revision (2026-07-11):** during implementation, Task 1 discovered that
> Frappe does not support a Table field nested inside a doctype that is
> itself a child table ("grandchild tables") — confirmed against this
> bench's Frappe v16.20.0: `_init_child` in `frappe/model/base_document.py`
> unconditionally blanks a child row's own table-field registry
> (`child._table_fieldnames = TABLE_DOCTYPES_FOR_CHILD_TABLES`, a constant
> that is always `{}`), regardless of what the child doctype's own meta
> declares. The comment at that call site is explicit: "child tables don't
> have child tables." Since `Evo Line` is itself a child row of
> `Evolution API Settings.evo_lines`, its originally-planned nested
> `limited_to_users` table could never be populated or read through the
> normal Document API. The sections below reflect the corrected design:
> user restrictions moved out to a second, sibling table
> (`line_restrictions`) directly on `Evolution API Settings`, filtered by
> `instance_name` instead of read off the line row. Nothing else in this
> spec changed.

### `Evolution API Settings` (existing Single doctype)

Stops holding connection/webhook/status fields directly. Becomes a thin
wrapper around two table fields:

- `evo_lines` — Table, options `Evo Line`
- `line_restrictions` — Table, options `Evo Line Restriction`

### `Evo Line` (new child doctype, `istable=1`)

All fields formerly on `Evolution API Settings`, moved down to the row level,
plus a `disabled` flag and the new user-restriction table:

Connection section (2 columns):
- `base_url` (Data, reqd)
- `instance_name` (Data, reqd, must be unique across all rows in the parent's
  `evo_lines` table — validated in `Evolution API Settings.validate()`)
- *(column break)*
- `api_key` (Password, reqd)
- `timeout` (Int, default 30)
- `default_country_code` (Data)
- `disabled` (Check)

Webhook section (2 columns):
- `webhook_secret` (Password, auto-generated if empty, same as today)
- `webhook_url` (Small Text, read-only, computed from this row's secret)
- *(column break)*
- `last_webhook_response` (JSON, read-only)

Status section (2 columns):
- `last_tested_on` (Datetime, read-only)
- *(column break)*
- `last_connection_state` (JSON, read-only)

`Evo Line` no longer has an Access section or `limited_to_users` field (see
revision note above) — that responsibility moved to `Evolution API
Settings.line_restrictions`.

### `Evo Line Restriction` (new child doctype, `istable=1`)

A flat, sibling table on `Evolution API Settings` (not nested inside `Evo
Line`) — one row per (line, user) restriction pair:

- `line` — Data, reqd. Must match an existing `Evo Line.instance_name`
  (validated in `Evolution API Settings.validate()`).
- `user` — Link, options `User`, reqd

A line with no matching `line_restrictions` rows is open to all users.

## Backend changes

### Line resolution

A shared resolution helper (in `evolution_api_settings.py`, used by `api.py`)
takes an `instance_name` and:
1. Loads the single `Evolution API Settings` doc.
2. Finds the `Evo Line` row with that `instance_name`.
3. Throws if not found, or if `disabled`.
4. Throws `frappe.PermissionError` if any `line_restrictions` row matches
   this `instance_name` and `frappe.session.user` is not one of the users
   listed for it.
5. Returns the row.

This runs **server-side** inside every whitelisted entry point that acts on a
line — `send_text`, `send_media`, `send_message_doc`, `test_connection`,
`configure_webhook`, `fetch_instances`, `get_qr_code`,
`diagnose_webhook_routes` — so permission can't be bypassed by calling the
API directly with an arbitrary line name.

### `EvolutionAPIClient`

Constructor takes an `Evo Line` row (instead of defaulting to
`frappe.get_single("Evolution API Settings")`). All per-request state
(`base_url`, `instance_name`, `api_key`, `timeout`, `default_country_code`)
comes from that row.

### `get_available_lines()` (new whitelisted method)

Returns enabled lines the current user is permitted to use (no matching
`line_restrictions` row, or user is one of the ones listed for that line),
as `{value, label}` pairs using `instance_name` for both (no separate
friendly-name field). Used to populate the dropdown in the "Send via WA"
dialog.

### Phone normalization

`normalize_phone()` in `client.py` is unchanged — it already strips a single
leading `0` and prepends `default_country_code` generically:

```
digits.startswith("0") → f"{default_country_code}{digits[1:]}"
```

This already produces `254725548065` from `0725548065` + `254`, and the same
rule applies unmodified for any other country code (e.g. `91`). The only
change is that the `default_country_code` passed in now comes from the
resolved `Evo Line` row instead of the global single.

### `_insert_message_log`

Already accepts an `instance_name` parameter — no signature change needed,
just pass through the resolved line's `instance_name`.

## Webhook routing

- Each line's `webhook_url` is computed with `?token=<that row's
  webhook_secret>`, same pattern as today but per-row.
- Incoming webhook: `_validate_webhook_request()` searches all `Evo Line`
  rows for one whose `webhook_secret` matches the received token. That row is
  the authoritative line — used for `default_country_code` and message
  logging. The payload's own `instance` field is not trusted for security,
  only used for display/logging convenience.
- If no row matches the token, the webhook request is rejected
  (`frappe.PermissionError`), same as today's "invalid webhook token"
  behavior.

## Frontend changes

### `Evolution API Settings` form (`evolution_api_settings.js`)

- The per-instance action buttons (Test Connection, Fetch Instances, Get QR
  Code, Configure Webhook) move to being scoped to a specific `Evo Line` row
  — invoked with that row's `instance_name` so results are written back to
  the correct row (via `frappe.db.set_value` on the child row, then
  `frm.reload_doc()`).

### "Send via WA" dialog (`frappe_whatsapp_evo.js`)

- New required `line` Select field, populated by calling
  `get_available_lines()` when the dialog opens.
- If exactly one line is available, it's preselected as the default value;
  the field remains visible for consistency with the multi-line case.
- If zero lines are available to the current user, show an error
  (`frappe.msgprint` / `frappe.throw`-style alert) instead of opening the
  dialog.
- `primary_action` passes `line: values.line` through to
  `send_whatsapp_with_media`, which passes it to `send_text`/`send_media`.

### `WhatsApp Evo Message` resend button (`whatsapp_evo_message.js`)

- No JS change needed for line selection: `send_message_doc(name)` resolves
  the line server-side from the doc's existing `instance_name` field. If that
  line is now disabled, missing, or the current user isn't permitted, the
  call throws a clear error surfaced to the user.

## Migration

A Frappe patch (run once, before/during doctype schema sync so the old
single-doc fields are still readable) reads the existing
`Evolution API Settings` single's field values (`base_url`, `instance_name`,
`api_key`, `timeout`, `default_country_code`, `webhook_secret`,
`webhook_url`, `last_webhook_response`, `last_tested_on`,
`last_connection_state`) and creates one `Evo Line` row from them: enabled,
no user restriction. This preserves the working connection for existing
installs across the upgrade. Registered in `patches.txt`.

## Testing / verification

- `normalize_phone`: regression tests for the `07`/`01`-style leading-zero
  case with `default_country_code="254"`, and a second country code (e.g.
  `"91"`) to confirm the rule is generic, not hardcoded.
- `Evo Line` validation: duplicate `instance_name` across rows raises a
  validation error.
- Line resolution: disabled line is excluded/rejected; `line_restrictions`
  correctly filters `get_available_lines()` and is enforced (not just
  hidden) when calling `send_text`/`send_media` directly as a non-permitted
  user.
- Webhook: a request with a token matching line B's `webhook_secret` is
  attributed to line B regardless of what the payload's `instance` field
  says; a request with an unmatched token is rejected.
- Manual UI pass: open "Send via WA" dialog with 0/1/2+ accessible lines and
  confirm dropdown behavior matches spec; disable a line and confirm it
  disappears from the dropdown and resend of a message tied to it fails with
  a clear error.

## Out of scope

- Renaming `Evolution API Settings` to a non-Single doctype (rejected in
  favor of keeping it as a Single wrapping the `evo_lines` table).
- A separate friendly "Line Name" label distinct from `instance_name`
  (explicitly declined — `instance_name` is used as both).
- Any change to how `Evo Line` rows are edited in the desk UI beyond column
  layout (standard Frappe child table grid + row-edit form).
