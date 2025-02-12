import os

BASE_URLS = {
    "local": "http://localhost:8000/",
    "production": "https://jamesg.blog/aurora/",
}

SITE_ENV = os.environ.get("SITE_ENV", "local")
BASE_URL = BASE_URLS[SITE_ENV]
ROOT_DIR = "pages"
LAYOUTS_BASE_DIR = "_layouts"
SITE_DIR = "_site"
HOOKS = {
    "post_template_generation": {"highlighting": ["highlight_code"]},
    "pre_template_generation": {"highlighting": ["generate_table_of_contents"]},
}
SITE_STATE = {}
