from . import __version__ as app_version

app_name = "frappe_whatsapp_evo"
app_title = "Frappe Whatsapp Evo"
app_publisher = "Cecypo.Tech"
app_description = "Simple Evolution API integration for Frappe/ERPNext v16"
app_email = "support@cecypo.tech"
app_license = "MIT"
frappe_version = ">=16.0.0 <17.0.0"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_whatsapp_evo/css/frappe_whatsapp_evo.css"
app_include_js = "/assets/frappe_whatsapp_evo/js/frappe_whatsapp_evo.js"

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
