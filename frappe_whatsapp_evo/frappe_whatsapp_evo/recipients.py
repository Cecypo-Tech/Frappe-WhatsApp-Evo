"""Work out who a document should be messaged on WhatsApp.

The number a user wants is almost never on the document itself. On a Sales
Invoice it lives on the customer's Contact, and `contact_person` is only
populated when somebody filled it in. So this walks outward from the document
to its party and collects every number it can reach, best first, rather than
returning a single guess that is usually empty.

Nothing here checks permissions - callers must already have established that
the session user may read the document being resolved.
"""

import re

import frappe

# Fields that can carry a number directly on a transaction. `contact_mobile` is
# ERPNext's own resolved value, so it outranks the more generic ones.
DOCUMENT_PHONE_FIELDS = (
	"contact_mobile",
	"whatsapp_no",
	"mobile_no",
	"contact_phone",
	"phone",
)

# Doctypes that are a party in their own right, rather than pointing at one.
PARTY_DOCTYPES = ("Customer", "Supplier", "Lead", "Contact")

# Link field -> the doctype it points at, in the order we prefer them.
PARTY_LINK_FIELDS = (
	("customer", "Customer"),
	("supplier", "Supplier"),
	("lead", "Lead"),
)

PRIMARY_CONTACT_FIELDS = {
	"Customer": "customer_primary_contact",
	"Supplier": "supplier_primary_contact",
}


def digits(number: str | None) -> str:
	"""Reduce a number to digits only, for comparing two spellings of one number."""
	return re.sub(r"\D", "", str(number or ""))


def get_party(doc) -> tuple[str | None, str | None]:
	"""Return the (doctype, name) of the party this document belongs to."""
	if doc.doctype in PARTY_DOCTYPES:
		return doc.doctype, doc.name

	# Payment Entry, Journal Entry and friends carry an explicit pair.
	if doc.get("party_type") and doc.get("party"):
		return doc.get("party_type"), doc.get("party")

	for fieldname, party_doctype in PARTY_LINK_FIELDS:
		if doc.get(fieldname):
			return party_doctype, doc.get(fieldname)

	return None, None


def get_contact_numbers(contact_name: str) -> list[tuple[str, str]]:
	"""Return (number, kind) pairs for a Contact, mobiles first.

	A Contact keeps its numbers in three places: the `mobile_no` and `phone`
	columns, and the `phone_nos` child table. Landlines are included but rank
	below mobiles, because a WhatsApp number is far more likely to be a mobile.
	"""
	contact = frappe.db.get_value("Contact", contact_name, ["name", "mobile_no", "phone"], as_dict=True)
	if not contact:
		return []

	rows = frappe.get_all(
		"Contact Phone",
		filters={"parent": contact_name, "parenttype": "Contact"},
		fields=["phone", "is_primary_mobile_no", "is_primary_phone"],
		order_by="idx asc",
	)

	mobiles, phones = [], []
	if contact.mobile_no:
		mobiles.append(contact.mobile_no)
	if contact.phone:
		phones.append(contact.phone)
	for row in rows:
		(mobiles if row.is_primary_mobile_no else phones).append(row.phone)

	return [(n, "Mobile") for n in mobiles if n] + [(n, "Phone") for n in phones if n]


def _add(candidates: list[dict], seen: set[str], number: str | None, label: str, source: str, contact=None):
	"""Append a candidate unless the same digits are already present.

	Earlier callers win, so the ranking below is what decides which spelling of
	a duplicated number the user is shown.
	"""
	key = digits(number)
	if not key or key in seen:
		return
	seen.add(key)
	candidates.append({"mobile_no": str(number).strip(), "label": label, "source": source, "contact": contact})


def get_recipient_candidates(doctype: str, name: str, doc=None) -> list[dict]:
	"""Return every number reachable from this document, best first.

	`doc` lets a caller that has already loaded the document pass it in rather
	than paying for a second fetch.
	"""
	doc = doc or frappe.get_doc(doctype, name)
	candidates: list[dict] = []
	seen: set[str] = set()

	# 1. The person actually named on this document.
	if doc.get("contact_person"):
		display = frappe.db.get_value("Contact", doc.get("contact_person"), "full_name") or doc.get(
			"contact_person"
		)
		for number, kind in get_contact_numbers(doc.get("contact_person")):
			_add(candidates, seen, number, f"{display} ({kind})", "Document Contact", doc.get("contact_person"))

	party_doctype, party = get_party(doc)

	# 2. Numbers already resolved onto the document itself.
	#
	# Skipped when the document *is* the party: Customer.mobile_no is a
	# denormalised copy of its primary contact's number, so treating it as a
	# document field would rank it above the contact it came from and label it
	# "Mobile No" instead of naming the person. Step 5 picks it up instead.
	if doc.doctype not in PARTY_DOCTYPES:
		meta = frappe.get_meta(doctype)
		for fieldname in DOCUMENT_PHONE_FIELDS:
			if meta.has_field(fieldname) and doc.get(fieldname):
				_add(candidates, seen, doc.get(fieldname), meta.get_label(fieldname), "Document Field")

	if not party:
		return candidates

	party_label = frappe.db.get_value(party_doctype, party, "name") or party

	# 3. The party's designated primary contact.
	primary_field = PRIMARY_CONTACT_FIELDS.get(party_doctype)
	primary_contact = None
	if primary_field and frappe.get_meta(party_doctype).has_field(primary_field):
		primary_contact = frappe.db.get_value(party_doctype, party, primary_field)
	if primary_contact:
		display = frappe.db.get_value("Contact", primary_contact, "full_name") or primary_contact
		for number, kind in get_contact_numbers(primary_contact):
			_add(candidates, seen, number, f"{display} ({kind}, Primary)", "Primary Contact", primary_contact)

	# 4. Every other Contact linked to the party.
	linked = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": party_doctype, "link_name": party, "parenttype": "Contact"},
		pluck="parent",
		order_by="creation asc",
	)
	for contact_name in linked:
		if contact_name == primary_contact:
			continue
		display = frappe.db.get_value("Contact", contact_name, "full_name") or contact_name
		for number, kind in get_contact_numbers(contact_name):
			_add(candidates, seen, number, f"{display} ({kind})", "Linked Contact", contact_name)

	# 5. The party record's own number, as a last resort.
	if frappe.get_meta(party_doctype).has_field("mobile_no"):
		number = frappe.db.get_value(party_doctype, party, "mobile_no")
		_add(candidates, seen, number, f"{party_label} ({party_doctype})", "Party")

	return candidates
