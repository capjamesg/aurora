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
HOOKS = {
    "pre_template_generation": {"hooks": ["retrieve_visitor_count"]},
    "post_build": {"hooks": ["add_made_by_file"]},
    "template_filters": {"hooks": ["capitalize"]},
}
SITE_STATE = {
    "category_slug_root": "category",
    "tag_slug_root": "tag",
}
