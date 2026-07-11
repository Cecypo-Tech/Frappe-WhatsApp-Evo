import os

from . import __version__ as app_version

app_name = "frappe_whatsapp_evo"
app_title = "Frappe Whatsapp Evo"
app_publisher = "Cecypo.Tech"
app_description = "Simple Evolution API integration for Frappe/ERPNext v16"
app_email = "support@cecypo.tech"
app_license = "MIT"
frappe_version = ">=16.0.0 <17.0.0"


def _asset_version(relative_path: str) -> str:
	"""Cache-bust an unbundled app_include_js/app_include_css path.

	Frappe only appends a content hash to paths containing ".bundle." (see
	frappe.utils.jinja_globals.bundled_asset) — a plain /assets path like
	ours is served unchanged. nginx's default config sends
	Cache-Control: max-age=31536000 for everything under /assets, so
	without this, browsers that already fetched this file keep running it
	forever and never see updates. Keying off the file's own mtime means
	the URL changes automatically on every edit, with nothing to remember.
	"""
	full_path = os.path.join(os.path.dirname(__file__), "public", relative_path)
	try:
		return str(int(os.path.getmtime(full_path)))
	except OSError:
		return app_version


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_whatsapp_evo/css/frappe_whatsapp_evo.css"
app_include_js = f"/assets/frappe_whatsapp_evo/js/frappe_whatsapp_evo.js?v={_asset_version('js/frappe_whatsapp_evo.js')}"

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}

# Installation
# ------------

# before_install = "frappe_whatsapp_evo.install.before_install"
# after_install = "frappe_whatsapp_evo.install.after_install"

# Fixtures
# --------

fixtures = []

# Testing
# -------

# before_tests = "frappe_whatsapp_evo.install.before_tests"
