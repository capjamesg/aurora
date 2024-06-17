import os

BASE_URLS = {
    "local": os.getcwd(),
    "production": "https://example.com",
}

SITE_ENV = os.environ.get("SITE_ENV", "local")
BASE_URL = BASE_URLS[SITE_ENV]
ROOT_DIR = "pages"
LAYOUTS_BASE_DIR = "_layouts"
SITE_DIR = "_site"
HOOKS = {}
SITE_STATE = {}
