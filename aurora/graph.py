import logging
import os
import sys

if not os.path.exists("config.py"):
    raise Exception("config.py not found")

import csv
import datetime
import hashlib
import json
import re
from copy import deepcopy

import chardet
import orjson
import pyromark
import tqdm
from frontmatter import loads
from bs4 import BeautifulSoup
from jinja2 import (
    Environment,
    FileSystemBytecodeCache,
    FileSystemLoader,
    Template,
    meta,
    nodes,
)
from jinja2.visitor import NodeVisitor
from toposort import toposort_flatten
from yaml.reader import ReaderError
from collections import defaultdict

from .date_helpers import (
    archive_date,
    date_to_xml_string,
    list_archive_date,
    long_date,
    month_number_to_written_month,
    year,
)

module_dir = os.getcwd()
os.chdir(module_dir)
sys.path.append(module_dir)
state_to_write = {}
original_file_to_permalink = {}
normalized_collection_permalinks = {}

# print all logs
logging.basicConfig(level=logging.INFO)

from config import (
    BASE_URL,
    HOOKS,
    LAYOUTS_BASE_DIR,
    ROOT_DIR,
    SITE_DIR,
    SITE_STATE,
    SITE_ENV,
)

ALLOWED_EXTENSIONS = ["html", "md", "css", "js", "txt", "xml"]

saved_pages = set()
permalinks = defaultdict(list)
all_data_files = {}
all_pages = []
all_opened_pages = {}
all_page_contents = {}
collections_to_files = {}
all_dependencies = {}
all_parsed_pages = {}
dates = set()
years = {}
reverse_deps = {}
collection_permalinks_to_idx = {}
layout_permalinks_to_idx = {}

# ensures a single template cannot have more than 10 levels of inheritance
INHERITANCE_LIMIT = 10

DATA_FILES_DIR = os.path.join(ROOT_DIR, "_data")

EVALUATED_REGISTERED_TEMPLATE_GENERATION_HOOKS = {}
EVALUATED_POST_TEMPLATE_GENERATION_HOOKS = {}
EVALUATED_POST_BUILD_HOOKS = {}


class Post:
    def __init__(self, front_matter):
        self.__dict__.update(front_matter)

    def __getattr__(self, name):
        return self.__dict__.get(name)

    def serialize_as_json(self):
        """Serialize the Post object as JSON."""
        return orjson.dumps(self.__dict__).decode()


for file_name, hooks in HOOKS.get("pre_template_generation", {}).items():
    EVALUATED_REGISTERED_TEMPLATE_GENERATION_HOOKS[file_name] = [
        getattr(__import__(file_name), func) for func in hooks
    ]

for file_name, hooks in HOOKS.get("post_template_generation", {}).items():
    EVALUATED_POST_TEMPLATE_GENERATION_HOOKS[file_name] = [
        getattr(__import__(file_name), func) for func in hooks
    ]

for file_name, hooks in HOOKS.get("post_build", {}).items():
    EVALUATED_POST_BUILD_HOOKS[file_name] = [
        getattr(__import__(file_name), func) for func in hooks
    ]

today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
state = {
    "posts": [],
    "backlinks": defaultdict(list),
    "root_url": BASE_URL,
    "build_date": today.strftime("%m-%d"),
    "pages": [],
    "build_timestamp": datetime.datetime.now().isoformat(),
    "environment": SITE_ENV,
}

file_extensions = {}

state.update(SITE_STATE)

JINJA2_ENV = Environment(
    loader=FileSystemLoader(ROOT_DIR),
    bytecode_cache=FileSystemBytecodeCache(),
)


JINJA2_ENV.filters["long_date"] = long_date
JINJA2_ENV.filters["date_to_xml_string"] = date_to_xml_string
JINJA2_ENV.filters["archive_date"] = archive_date
JINJA2_ENV.filters["list_archive_date"] = list_archive_date
JINJA2_ENV.filters["month_number_to_written_month"] = month_number_to_written_month
JINJA2_ENV.filters["year"] = year

for file_name, hooks in HOOKS.get("template_filters", {}).items():
    for hook in hooks:
        JINJA2_ENV.filters[hook] = getattr(__import__(file_name), hook)

md = pyromark.Markdown(
    options=(
        pyromark.Options.ENABLE_FOOTNOTES
        | pyromark.Options.ENABLE_SMART_PUNCTUATION
        | pyromark.Options.ENABLE_HEADING_ATTRIBUTES
    )
)


def read_file(file_name, mode="r") -> str:
    """
    Read a file and return its contents.
    """
    try:
        with open(file_name, mode) as file:
            return file.read()
    except UnicodeDecodeError as e:
        raw_data = open(file_name, "rb").read()
        result = chardet.detect(raw_data)
        encoding = result["encoding"]

        with open(file_name, "rb") as file:
            return file.read().decode(encoding)
    except Exception as e:
        print(f"Error reading {file_name}")
        raise e


def slugify(value: str) -> str:
    """
    Turn a string into a slug for use in saving data to a file.
    """
    return value.lower().strip().replace(" ", "-")


class VariableVisitor(NodeVisitor):
    """
    Find all variables in a jinja2 template.
    """

    def __init__(self):
        self.variables = set()

    def visit_Name(self, node, *args, **kwargs) -> None:
        self.variables.add(node.name)
        self.generic_visit(node, *args, **kwargs)

    def visit_Getattr(self, node, *args, **kwargs) -> None:
        current_node = node
        variable_chain = []
        while isinstance(current_node, nodes.Getattr):
            variable_chain.append(current_node.attr)
            current_node = current_node.node
        if isinstance(current_node, nodes.Name):
            variable_chain.append(current_node.name)
        full_variable = ".".join(reversed(variable_chain))
        self.variables.add(full_variable)
        self.generic_visit(node, *args, **kwargs)


def get_file_dependencies_and_evaluated_contents(
    file_name: str, contents: Template
) -> tuple:
    """
    Get all dependencies of a file. Dependencies are:

    1. Other files that are included in the file, and;
    2. Variables whose values are defined by the site generator (i.e. `site.*`).
    """
    template = JINJA2_ENV.parse(all_page_contents[file_name])

    includes = []
    included_variables = []

    for node in meta.find_referenced_templates(template):
        includes.append(node)

    visitor = VariableVisitor()
    visitor.visit(template)

    for var in visitor.variables:
        included_variables.append(var)

    dependencies = set()

    for include in includes:
        if isinstance(include, str):
            dependencies.add(os.path.join(ROOT_DIR, include))
        else:
            dependencies.add(os.path.join(ROOT_DIR, include.template.value))

    for variable in included_variables:
        variable = variable.replace("site.", "")

        for collection in collections_to_files:
            if collections_to_files.get(collection):
                dependencies.update(collections_to_files[collection])

        if variable in state:
            dependencies.add(variable)

    parsed_content = all_page_contents[file_name]

    if not parsed_content.get("slug"):
        parsed_content["slug"] = file_name.split("/")[-1].replace(".html", "")

    parsed_content["contents"] = md.html(parsed_content.content)

    parsed_content["url"] = f"{BASE_URL}/{file_name.replace(ROOT_DIR + '/posts/', '')}"

    if parsed_content.metadata.get("permalink") and parsed_content.metadata["permalink"].startswith("/"):
        parsed_content["has_user_assigned_permalink"] = True
        parsed_content["permalink"] = f"/{parsed_content.metadata['permalink'].strip('/')}/"

    parsed_content[
        "permalink"
    ] = f"/{parsed_content.metadata.get('permalink', parsed_content['slug']).strip('/')}/"

    if "categories" not in parsed_content:
        parsed_content["categories"] = []

    slug = file_name.split("/")[-1].replace(".html", "")

    slug = slug.replace("posts/", "")

    if slug[0].isdigit():
        date_slug = re.search(r"\d{4}-\d{2}-\d{2}", slug)

        if date_slug:
            date_slug = date_slug.group(0)
            if not parsed_content.get("post"):
                parsed_content["post"] = {}
            if not parsed_content.get("page"):
                parsed_content["page"] = {}
            parsed_content["post"]["date"] = datetime.datetime.strptime(
                date_slug, "%Y-%m-%d"
            )
            # if "hms" in post metadata, add to post date
            if parsed_content.get("hms") and parsed_content["hms"].count(":") == 2:
                parsed_content["post"]["date"] = parsed_content["post"]["date"].replace(
                    hour=int(parsed_content["hms"].split(":")[0]),
                    minute=int(parsed_content["hms"].split(":")[1]),
                    second=int(parsed_content["hms"].split(":")[2]),
                )

            parsed_content["post"]["date_without_year"] = parsed_content["post"][
                "date"
            ].strftime("%m-%d")
            parsed_content["date_without_year"] = parsed_content["post"][
                "date_without_year"
            ]

            parsed_content["post"]["full_date"] = parsed_content["post"][
                "date"
            ].strftime("%B %d, %Y")
            parsed_content["date"] = parsed_content["post"]["date"]

            parsed_content["page"]["date"] = parsed_content["post"]["date"]

            if "description" not in parsed_content:
                parsed_content["description"] = md.html(
                    parsed_content.content.split("\n")[0]
                )
            date_slug = date_slug.replace("-", "/")
            slug_without_date = re.sub(r"\d{4}-\d{2}-\d{2}-", "", slug)

            parsed_content["post"][
                "url"
            ] = f"{BASE_URL}/{date_slug}/{slug_without_date.replace('.html', '').replace('.md', '')}/"

    if "layout" in parsed_content:
        dependencies.add(
            f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{parsed_content['layout']}.html"
        )
        if not state.get(parsed_content["layout"] + "s"):
            state[parsed_content["layout"] + "s"] = []

        if not layout_permalinks_to_idx.get(parsed_content["permalink"]):
            state[parsed_content["layout"] + "s"].append(parsed_content)
            layout_permalinks_to_idx[parsed_content["permalink"]] = (
                len(state[parsed_content["layout"] + "s"]) - 1
            )
        else:
            if (
                len(state[parsed_content["layout"] + "s"])
                > layout_permalinks_to_idx[parsed_content["permalink"]]
            ):
                state[parsed_content["layout"] + "s"][
                    layout_permalinks_to_idx[parsed_content["permalink"]]
                ] = parsed_content

    if "collection" in parsed_content:
        collection_normalized = parsed_content["collection"].lower()
        if not state.get(collection_normalized):
            state[collection_normalized] = []

        if not normalized_collection_permalinks.get(collection_normalized):
            normalized_collection_permalinks[collection_normalized] = []

        # if permalink in collection_permalinks_to_idx, replace
        if collection_permalinks_to_idx.get(parsed_content["permalink"]):
            state[collection_normalized][
                collection_permalinks_to_idx[parsed_content["permalink"]]
            ] = parsed_content
        else:
            state[collection_normalized].append(parsed_content)

        collection_permalinks_to_idx[parsed_content["permalink"]] = state[
            collection_normalized
        ].index(parsed_content)

    return dependencies, parsed_content


def make_any_nonexistent_directories(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def interpolate_front_matter(front_matter: dict, state: dict, runtime = None) -> dict:
    """Evaluate front matter with Jinja2 to allow logic in front matter."""
    # Keep track of already interpolated keys to prevent double interpolation
    interpolated_keys = set()
    
    for key in front_matter.keys():
        if (
            isinstance(front_matter[key], str)
            and "{" in front_matter[key]
            and key != "contents"
            and (not front_matter.get("defer_title_evaluation") or runtime == "category")
            and key not in interpolated_keys  # Only interpolate if key hasn't been processed
        ):
            try:
                front_matter[key] = JINJA2_ENV.from_string(front_matter[key]).render(
                    page=front_matter.get("page", front_matter), site=state
                )
                interpolated_keys.add(key)  # Mark this key as interpolated
            except:
                print(f"Error evaluating {front_matter[key]}. ERROR.")
                continue

    return front_matter


def recursively_build_page_template_with_front_matter(
    file_name: str,
    front_matter: dict,
    state: dict,
    current_contents: str = "",
    level: int = 0,
    original_page: dict = None,
) -> str:
    """
    Recursively build a page template with front matter.

    This function is called recursively until there is no layout key in the front matter.
    """
    if level > 10:
        logging.critical(
            f"{file_name} has more than ten levels of recursion. Template will be marked as empty."
        )
        return ""

    if front_matter and "layout" in front_matter.metadata:
        layout = front_matter.metadata["layout"]
        layout_path = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{layout}.html"

        # Always use a deep copy of the current front matter for this recursion
        current_page_metadata = deepcopy(front_matter.metadata)

        # Interpolate front matter before creating page object
        current_page_metadata = interpolate_front_matter(current_page_metadata, state)

        # Create page object with interpolated front matter
        page_fm = type("Page", (object,), current_page_metadata)()

        current_contents = loads(
            all_opened_pages[layout_path].render(
                page=page_fm,
                site=state,
                content=current_contents,
                post=Post(current_page_metadata),
            )
        ).content

        layout_front_matter = all_parsed_pages[layout_path]

        # Pass the current page metadata for the next recursion
        layout_front_matter["page"] = current_page_metadata
        layout_front_matter["post"] = current_page_metadata

        return recursively_build_page_template_with_front_matter(
            file_name, layout_front_matter, state, current_contents.strip(), level + 1, current_page_metadata
        )

    return current_contents


def render_page(file: str, skip_hooks=False) -> None:
    """
    Render a page with the Aurora static site generator.
    """

    original_file = file

    # # skip if json
    if file.endswith(".json"):
        return

    try:
        contents = all_opened_pages[file]
    except Exception as e:
        print(f"Error reading {file}")
        # raise e
        return

    page_state = state.copy()

    has_user_assigned_permalink = False

    if all_parsed_pages[file].get("skip"):
        return

    slug = file.split("/")[-1].replace(".html", "")

    slug = slug.replace("posts/", "")

    has_user_assigned_permalink = all_parsed_pages[file].metadata.get(
        "has_user_assigned_permalink"
    )

    page_state["page"] = all_parsed_pages[file].metadata
    page_state["post"] = all_parsed_pages[file].metadata
    
    if not page_state["page"].get("permalink"):
        page_state["page"]["permalink"] = page_state.get("permalink", slug)  # .strip("/")

    page_state["page"]["generated_on"] = datetime.datetime.now()

    if slug[0].isdigit():
        date_slug = re.search(r"\d{4}-\d{2}-\d{2}", slug)
        if date_slug:
            date_slug = date_slug.group(0)
            page_state["post"]["date"] = datetime.datetime.strptime(
                date_slug, "%Y-%m-%d"
            )
            if page_state["post"].get("hms") and page_state["post"]["hms"].count(":") == 2:
                page_state["post"]["date"] = page_state["post"]["date"].replace(
                    hour=int(page_state["post"]["hms"].split(":")[0]),
                    minute=int(page_state["post"]["hms"].split(":")[1]),
                    second=int(page_state["post"]["hms"].split(":")[2]),
                )
            page_state["post"]["full_date"] = page_state["post"]["date"].strftime(
                "%B %d, %Y"
            )
            page_state["date"] = page_state["post"]["date"]
            page_state["full_date"] = page_state["post"]["full_date"]
            if "description" not in page_state["post"]:
                page_state["post"]["description"] = all_parsed_pages[
                    file
                ].content.split("\n")[0]
        page_state["is_article"] = True

    if page_state.get("date"):
        date = page_state["date"]
        slug = re.sub(r"\d{4}-\d{2}-\d{2}-", "", file)
        slug = slug.replace("pages/posts/", "").replace(".md", "").replace(".html", "")
        page_state["page"]["slug"] = slug
        page_state["page"]["url"] = f"{BASE_URL}/{date.strftime('%Y/%m/%d')}/{slug}/"
    else:
        page_state["page"]["url"] = f"{BASE_URL}/{slug}/"

    page_state["url"] = page_state["page"]["url"]

    if file == "pages/templates/index.html":
        page_state["url"] = BASE_URL
        page_state["page"]["url"] = BASE_URL
        page_state["page"]["permalink"] = BASE_URL

    if not page_state.get("categories"):
        page_state["categories"] = []

    state["categories"] = []

    page_state["page"]["generated_from"] = file

    if page_state.get("page"):
        page_state["page"] = type("Page", (object,), page_state["page"])()
        page_state["post"] = Post(page_state["page"].__dict__)

    for hook, hooks in EVALUATED_REGISTERED_TEMPLATE_GENERATION_HOOKS.items():
        for hook in hooks:
            page_state = hook(file, page_state, state)

    try:
        if file.endswith(".md"):
            contents = md.html(loads(all_opened_pages[file]).content)
        elif isinstance(contents, str):
            # this happens for data files only, where content does not exist
            contents = ""
        else:
            contents = loads(contents.render(page=page_state, site=state)).content
    except Exception as e:
        # print(f"Error rendering {file}")
        return

    page_state["page"].template = file

    rendered = recursively_build_page_template_with_front_matter(
        file, all_parsed_pages[file], page_state, contents
    )

    if not skip_hooks:
        for _, hooks in EVALUATED_POST_TEMPLATE_GENERATION_HOOKS.items():
            for hook in hooks:
                rendered = hook(file, page_state, state, rendered)

    file = file.replace(ROOT_DIR + "/", "")

    if page_state.get("date"):
        file = os.path.join(date.strftime("%Y/%m/%d"), f"{slug}", "index.html")

    if file.endswith(".md"):
        file = file[:-3] + ".html"

    permalink = file

    # if permalink is _site/templates/index.html, make it _site/index.html
    if file == "templates/index.html":
        path = os.path.join(SITE_DIR, "index.html")
        if os.path.exists(path):
            os.remove(path)
        with open(path, "w") as f:
            f.write(rendered)

        return

    if file.startswith("templates/") and any(
        file.endswith(ext) for ext in [".html", ".md"]
    ):
        if hasattr(page_state["page"], "permalink"):
            permalink = os.path.join(
                page_state["page"].permalink.strip("/"), "index.html"
            )
        else:
            permalink = file.replace("templates/", "")
    elif has_user_assigned_permalink:
        permalink = os.path.join(page_state["page"].permalink.strip("/"), "index.html")
    else:
        permalink = file.replace("templates/", "")

    permalink_without_index = permalink.split("index.html")[0]
    final_url = f"{BASE_URL}/{permalink_without_index.rstrip('/')}/"

    if final_url not in saved_pages:
        # if has collections
        state["pages"].append(
            {
                "url": final_url,
                "file": file,
                "rendered_html": contents,
                "noindex": True
                if hasattr(page_state.get("page"), "noindex")
                else False,
                "private": True
                if hasattr(page_state.get("page"), "private")
                else False,
                "title": (
                    page_state["page"].title
                    if page_state.get("page") and hasattr(page_state["page"], "title")
                    else ""
                ),
                "collections": (
                    page_state["page"].collections
                    if hasattr(page_state["page"], "collections")
                    else ""
                ),
                "modified": os.path.getctime(original_file) if os.path.exists(original_file) else 0,
            }
        )
        saved_pages.add(final_url)

    permalinks[permalink].append(file)

    permalink = os.path.join(SITE_DIR, permalink)

    if permalink.endswith(".html"):
        make_any_nonexistent_directories(os.path.dirname(permalink))
    else:
        make_any_nonexistent_directories(os.path.join(SITE_DIR))

    state_to_write[permalink] = rendered
    original_file_to_permalink[permalink] = original_file


def generate_date_page_given_year_month_date(
    ymd_slug, posts, current_date_of_archive, granularity
) -> None:
    ymd_path = os.path.join(SITE_DIR, ymd_slug)

    make_any_nonexistent_directories(ymd_path)

    date_archive_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/date.html"

    if not all_opened_pages.get(date_archive_layout):
        return

    date_archive_contents = all_opened_pages[date_archive_layout]

    date_archive_state = state.copy()
    date_archive_state["date"] = current_date_of_archive

    page = deepcopy(all_parsed_pages[date_archive_layout])
    page["date"] = current_date_of_archive
    date_archive_state["date_type"] = granularity

    date_archive_state["posts"] = [all_parsed_pages[post].metadata for post in posts]

    # order by date
    date_archive_state["posts"] = sorted(
        date_archive_state["posts"],
        key=lambda x: x["date"],
        reverse=True,
    )

    fm = interpolate_front_matter(page, date_archive_state)

    rendered_page = date_archive_contents.render(
        date_archive_state,
        site=state,
        posts=date_archive_state["posts"],
        page=date_archive_state,
    )

    if not date_archive_state.get("page"):
        date_archive_state["page"] = {}

    date_archive_state["page"]["template"] = date_archive_layout

    rendered_page = recursively_build_page_template_with_front_matter(
        ymd_path, fm, date_archive_state, loads(rendered_page).content
    )

    with open(
        os.path.join(ymd_path, "index.html"),
        "wb",
        buffering=500,
    ) as f:
        f.write(rendered_page.encode())


def generate_paginated_page_for_collection(
    collection: str, per_page: int, template: str
) -> None:
    """
    Generate paginated pages for a collection.
    """

    if not state.get(collection):
        return

    print(f"Generating paginated pages for {collection}")

    collection = state[collection]

    if not collection:
        return

    all_keys_contain_dates = all(i.metadata.get("date") for i in collection)

    # if all keys have dates
    if all_keys_contain_dates:
        collection = sorted(
            collection, key=lambda x: x.metadata.get("date"), reverse=True
        )
    else:
        collection = sorted(
            collection, key=lambda x: x.metadata.get("title"), reverse=True
        )

    for i in tqdm.tqdm(range(0, len(collection), per_page)):
        page = i // per_page + 1
        paginated_collection = collection[i : i + per_page]

        print(f"Generating paginated page {page} for {collection}")

        if page == 1:
            paginated_collection_path = os.path.join(SITE_DIR, f"{template}/index.html")
        else:
            paginated_collection_path = os.path.join(
                SITE_DIR, f"{template}/{page}/index.html"
            )

        make_any_nonexistent_directories(os.path.dirname(paginated_collection_path))

        paginated_collection_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{template}.html"

        paginated_collection_contents = all_opened_pages[paginated_collection_layout]

        paginated_collection_state = state.copy()
        paginated_collection_state[collection[0]["layout"]] = paginated_collection
        paginated_collection_state["current_page"] = paginated_collection
        paginated_collection_state["page_number"] = page

        page = deepcopy(all_parsed_pages[paginated_collection_layout])
        page[collection[0]["layout"]] = paginated_collection

        fm = interpolate_front_matter(page, paginated_collection_state)

        rendered_page = paginated_collection_contents.render(
            paginated_collection_state,
            site=state,
            posts=paginated_collection,
            page=paginated_collection_state,
        )

        if not paginated_collection_state.get("page"):
            paginated_collection_state["page"] = {}

        paginated_collection_state["page"]["template"] = paginated_collection_layout

        rendered_page = recursively_build_page_template_with_front_matter(
            paginated_collection_path,
            fm,
            paginated_collection_state,
            loads(rendered_page).content,
        )

        with open(
            paginated_collection_path,
            "wb",
            buffering=500,
        ) as f:
            f.write(rendered_page.encode())


def process_date_archives() -> None:
    """
    Generate date archives for all posts.

    For example, if there are posts on 2022-01-01 and 2022-01-02, generate:

    - /2022/index.html
    - /2022/01/index.html
    - /2022/01/01/index.html
    """

    posts = [
        key
        for key in all_opened_pages.keys()
        if key.startswith(os.path.join(ROOT_DIR, "posts"))
    ]

    dates = set()
    years = {}

    for post in posts:
        if not hasattr(all_parsed_pages[post], "metadata"):
            continue

        if not all_parsed_pages[post].metadata.get("date"):
            continue

        date = all_parsed_pages[post].metadata["date"]
        dates.add(date)
        if date.year not in years:
            years[date.year] = {}
        if date.month not in years[date.year]:
            years[date.year][date.month] = {}
        if date.day not in years[date.year][date.month]:
            years[date.year][date.month][date.day] = []
        years[date.year][date.month][date.day].append(post)

    for year in years:
        make_any_nonexistent_directories(os.path.join(SITE_DIR, str(year)))

        for month in years[year]:
            make_any_nonexistent_directories(
                os.path.join(SITE_DIR, str(year), str(month))
            )

            for day in years[year][month]:
                ymd_slug = f"{year}/{str(month).zfill(2)}/{str(day).zfill(2)}"

                generate_date_page_given_year_month_date(
                    ymd_slug,
                    years[year][month][day],
                    datetime.datetime(year, month, day),
                    "day",
                )

            all_posts_in_month = [
                post for day in years[year][month] for post in years[year][month][day]
            ]

            generate_date_page_given_year_month_date(
                f"{year}/{str(month).zfill(2)}",
                all_posts_in_month,
                datetime.datetime(year, month, 1),
                "month",
            )

        all_posts_in_year = [
            post
            for month in years[year]
            for day in years[year][month]
            for post in years[year][month][day]
        ]

        generate_date_page_given_year_month_date(
            str(year), all_posts_in_year, datetime.datetime(year, 1, 1), "year"
        )

        print(f"Generated date archives for {year}")

    state["years"] = years


def process_archives(name: str, state_key_associated_with_name: str, path: str):
    """
    Generate category archives for all posts.

    For example, if you have a post with the `category` key set to `writing`, generate:

    - /writing/index.html
    """
    categories = set()

    for post in state["posts"]:
        if not post.get(state_key_associated_with_name):
            continue

        for category in post[state_key_associated_with_name]:
            categories.add(category)

    for category in categories:
        make_any_nonexistent_directories(
            os.path.join(SITE_DIR, path, slugify(category))
        )

        archive_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{name}.html"
        archive_contents = all_opened_pages[archive_layout]

        archive_state = state.copy()
        archive_state[name] = category
        page = deepcopy(all_parsed_pages[archive_layout])
        page[name] = category
        archive_state["posts"] = [
            post
            for post in state["posts"]
            if category in post.get(state_key_associated_with_name, [])
        ]

        print(f"Generating archive for {category}")

        page["category"] = category

        fm = interpolate_front_matter(page, archive_state, "category")

        fm["url"] = f"{BASE_URL}/{path}/{slugify(category)}/"

        rendered_page = archive_contents.render(
            archive_state,
            site=state,
            posts=archive_state["posts"],
            page=archive_state,
        )

        if not archive_state.get("page"):
            archive_state["page"] = {}

        archive_state["page"]["template"] = archive_layout

        rendered_page = recursively_build_page_template_with_front_matter(
            archive_layout,
            fm,
            archive_state,
            loads(rendered_page).content,
        )

        with open(
            os.path.join(SITE_DIR, path, slugify(category), "index.html"),
            "wb",
            buffering=500,
        ) as f:
            f.write(rendered_page.encode())


def copy_asset_to_site(assets: list) -> None:
    """
    Copy an asset from the `assets` directory to the `_site/assets` directory.
    """
    assets = [asset.replace("./assets/", "") for asset in assets]

    for a in assets:
        print(f"Copying {a} to _site/assets/{a}")
        make_any_nonexistent_directories(os.path.join(SITE_DIR, "assets"))
        asset = read_file(os.path.join("assets", a), "rb")
        with open(os.path.join(SITE_DIR, "assets", a), "wb") as f2:
            f2.write(asset)


def get_state_from_last_build() -> dict:
    """
    Get the state from the last build.
    """
    try:
        data = json.load(open("state.json", "r"))
    except Exception as e:
        print("Error reading state.json. Running a full build.")
        return {}

    return data


def calculate_dependencies_from_saved_state(all_dependencies: dict) -> list:
    """
    Read the saved state and compute dependencies of files that have changed since the last build.
    """
    deps = []

    last_build = datetime.datetime.strptime(
        get_state_from_last_build().get("last_build"), "%Y-%m-%dT%H:%M:%S.%f"
    )

    for root, dirs, files in os.walk(ROOT_DIR):
        # add if has changed since last build
        for file in files:
            path = os.path.join(root, file)
            # must be of parsable extension
            if os.path.splitext(file)[-1].replace(".", "") not in ALLOWED_EXTENSIONS:
                continue

            if os.path.getmtime(path) > last_build.timestamp():
                print(
                    f"Detected change in {path}. Rebuilding this page and its dependencies."
                )

                dependencies_of_dependencies = [
                    i for i in all_dependencies if path in all_dependencies[i]
                ] + [path]
                deps.extend(dependencies_of_dependencies)

    return deps


def load_data_from_data_files(deps: list, data_file_integrity: dict) -> list:
    """
    Read all data files and create YAML file that can be used to generate pages.
    """

    changed_files = []

    for data_file in all_data_files:
        data_dir = data_file.replace(".json", "").replace(".csv", "")
        collections_to_files[data_dir] = []
        idx = 0
        print(f"Loading data from {data_file}...")

        for record in tqdm.tqdm(all_data_files[data_file]):
            if not record.get("slug"):
                # print(
                #     f"Note: {data_file} {record} does not have a 'slug' key. Assigning substitute ID."
                # )
                record["slug"] = str(idx)
                idx += 1

            if not record.get("layout"):
                record["layout"] = data_dir

            slug = record.get("slug")
            path = os.path.join(data_dir, "index.html")

            record_as_string = orjson.dumps(record).decode()

            if (
                data_file_integrity.get(slug)
                != hashlib.sha1(record_as_string.encode()).hexdigest()
            ):
                changed_files.append(path)
                data_file_integrity[slug] = hashlib.sha1(
                    record_as_string.encode()
                ).hexdigest()

            try:
                contents = "---\n" + record_as_string + "\n---\n"
                loaded_contents = loads(contents)
                loaded_contents["skip"] = data_dir in SITE_STATE.get(
                    "disable_collection_single_page_generation", {}
                )
                if "body" in loaded_contents:
                    loaded_contents["content"] = loaded_contents["body"]
                    del loaded_contents["body"]
                all_opened_pages[path] = contents
                all_page_contents[path] = loaded_contents
                all_parsed_pages[path] = loaded_contents
                collections_to_files[data_dir].append(path)
            except ReaderError as e:
                print(
                    f"Error reading {data_file} {record}. This page will not be generated.",
                )
                # delete from all_page_contents
                all_page_contents.pop(path, None)
                all_opened_pages.pop(path, None)
                all_opened_pages.pop(path, None)
                continue

    return changed_files


def get_data_files_in_folder(folder: str) -> list:
    folder = os.path.abspath(folder)  # Convert to absolute path once
    files = []
    for entry in os.listdir(folder):
        path = os.path.join(folder, entry)
        if os.path.isdir(path):
            files.extend(get_data_files_in_folder(path))
        elif os.path.isfile(path) and path.endswith('.json'):
            files.append(path)
    return files


def main(deps: list = [], watch: bool = False, incremental: bool = False) -> None:
    """
    The Aurora runtime.

    Aurora can be run in two ways:

    - `aurora build` to build the site once, and;
    - `aurora serve` to watch for changes in the `pages` directory and rebuild the site in real time.
    """

    global state
    global all_dependencies

    data_file_integrity = {}

    start = datetime.datetime.now()

    if os.path.exists(DATA_FILES_DIR):
        for file in get_data_files_in_folder(DATA_FILES_DIR):
            # remove base /Users/james/src/airport-pianos/pages/
            file = file.replace(os.path.abspath(DATA_FILES_DIR) + "/", "")
            # if dir, recurse
            file_contents = read_file(os.path.join(DATA_FILES_DIR, file))

            if os.path.splitext(file)[-1].replace(".", "") == "json":
                all_data_files[file] = orjson.loads(file_contents)
                if isinstance(all_data_files[file], dict):
                    all_data_files[file] = [
                        {k: v for k, v in all_data_files[file].items()}
                    ]
                state[file.replace(".json", "")] = all_data_files[file]
            elif os.path.splitext(file)[-1].replace(".", "") == "csv":
                all_data_files[file] = list(csv.DictReader(file_contents.split("\n")))
                state[file.replace(".csv", "")] = all_data_files[file]
            else:
                logging.debug(
                    f"Unsupported data file format: {file}", level=logging.CRITICAL
                )
                print(f"Unsupported data file format: {file}")

    if not os.path.exists(SITE_DIR):
        os.makedirs(SITE_DIR)
    else:
        if not deps and not incremental:
            for root, _, files in os.walk(SITE_DIR):
                for file in files:
                    os.remove(os.path.join(root, file))

    for root, _, files in os.walk(ROOT_DIR):
        for file in files:
            ext = os.path.splitext(file)[-1].replace(".", "")
            if ext not in ALLOWED_EXTENSIONS:
                continue

            all_pages.append(os.path.join(root, file))

    for page in all_pages:
        if deps and page not in deps and not incremental:
            continue

        contents = read_file(page)

        try:
            if page.endswith(".md"):
                all_opened_pages[page] = contents
            else:
                all_opened_pages[page] = JINJA2_ENV.from_string(contents)

            all_page_contents[page] = loads(contents)

            if SITE_STATE.get("enable_backlinks"):
                page_links = BeautifulSoup(
                    pyromark.html(contents), "html.parser"
                ).find_all("a", href=True)

                # if in posts/, assign permalink
                if page.startswith("pages/posts/"):
                    # permalink should be YYYY-MM-DD-slug.md turned into /YYYY/MM/DD/slug/
                    yyyy_mm_dd = re.search(r"\d{4}-\d{2}-\d{2}", page)
                    if yyyy_mm_dd:
                        yyyy_mm_dd = yyyy_mm_dd.group(0)
                        slug = page.split(yyyy_mm_dd)[1].replace(".md", "")[1:]
                        yyyy_mm_dd_slug = f"{yyyy_mm_dd.replace('-', '/')}/{slug}"

                    # all_page_contents[page].metadata[
                    #     "permalink"
                    # ] = f"/{yyyy_mm_dd_slug.strip('/')}/"

                all_page_contents[page].metadata["outgoing_links"] = page_links
        except Exception as e:
            # logging.debug(f"Error reading {page}", level=logging.CRITICAL)
            # pass
            raise e

    if SITE_STATE.get("enable_backlinks"):
        for page in all_opened_pages:
            for link in all_page_contents[page].metadata.get("outgoing_links", []):
                state["backlinks"][link["href"]].append(
                    {
                        "url": all_page_contents[page].metadata.get("permalink"),
                        "title": all_page_contents[page].metadata.get("title", ""),
                    }
                )

    # sort all_opened_pages alpha
    all_opened_pages_sorted = list(sorted(all_page_contents.items()))
    # reverse so that we can get next and previous
    all_opened_pages_sorted.reverse()

    for i, page in enumerate(all_opened_pages_sorted):
        # add next and previous page
        if i < len(all_opened_pages_sorted) - 1:
            all_page_contents[page[0]].metadata["previous"] = {
                "url": all_opened_pages_sorted[i + 1][1].metadata.get("permalink", ""),
                "title": all_opened_pages_sorted[i + 1][1].metadata.get("title", ""),
            }

            previous_in_same_category = None
            # look at all posts before i
            for j in range(i + 1, len(all_opened_pages_sorted)):
                # print(f"Comparing {all_opened_pages_sorted[j][1].metadata.get('categories', [])} with {page[1].metadata.get('categories', [])}")
                if all_opened_pages_sorted[j][1].metadata.get("categories", []) == page[
                    1
                ].metadata.get("categories"):
                    previous_in_same_category = all_opened_pages_sorted[j][1]
                    break

            if previous_in_same_category:
                # print(f"Setting previous in same category for {page[1].metadata.get('title')} as {previous_in_same_category.metadata.get('title')} where next is {next_in_same_category.metadata.get('title') if next_in_same_category else None}")
                all_page_contents[page[0]].metadata["previous_in_same_category"] = {
                    "url": previous_in_same_category.metadata.get("permalink", ""),
                    "title": previous_in_same_category.metadata.get("title", ""),
                }

        if i > 0:
            all_page_contents[page[0]].metadata["next"] = {
                "url": all_opened_pages_sorted[i - 1][1].metadata.get("permalink", ""),
                "title": all_opened_pages_sorted[i - 1][1].metadata.get("title", ""),
            }

            next_in_same_category = None

            for j in range(i - 1, -1, -1):
                if all_opened_pages_sorted[j][1].metadata.get("categories", []) == page[
                    1
                ].metadata.get("categories"):
                    next_in_same_category = all_opened_pages_sorted[j][1]
                    break

            if next_in_same_category:
                all_page_contents[page[0]].metadata["next_in_same_category"] = {
                    "url": next_in_same_category.metadata.get("permalink", ""),
                    "title": next_in_same_category.metadata.get("title", ""),
                }

    if deps:
        deps = set(deps)
        new_deps = []

        while deps:
            dep = deps.pop()
            new_deps.append(dep)
            if dep in reverse_deps:
                deps.update(reverse_deps[dep])

        deps = new_deps

    if incremental:
        data = get_state_from_last_build()

        if data != {}:
            data_file_integrity = data.get("data_file_integrity", {})
            changed_files = load_data_from_data_files(deps, data_file_integrity)
            deps.extend(changed_files)
            deps.extend(calculate_dependencies_from_saved_state(all_dependencies))

            if len(deps) == 0:
                print("No changes detected. Exiting.")
                return
        else:
            load_data_from_data_files(deps, data_file_integrity)
    else:
        load_data_from_data_files(deps, data_file_integrity)

    for page, contents in all_opened_pages.items():
        # if incremental, only recompute dependencies for changed files
        if deps and page not in deps and not incremental:
            continue

        dependencies, parsed_page = get_file_dependencies_and_evaluated_contents(
            page, contents
        )
        all_dependencies[page] = dependencies
        all_parsed_pages[page] = parsed_page

        for dependency in dependencies:
            if dependency not in reverse_deps:
                reverse_deps[dependency] = set()
            reverse_deps[dependency].add(page)

        if page.startswith("posts/"):
            state["posts"].append(parsed_page)

    posts = [
        key
        for key in all_opened_pages.keys()
        if key.startswith(os.path.join(ROOT_DIR, "/posts"))
    ]

    for post in posts:
        if not hasattr(all_parsed_pages[post], "metadata"):
            continue

        if all_parsed_pages[post].metadata.get("date"):
            date = all_parsed_pages[post].metadata["date"]
            dates.add(date)
            if date.year not in years:
                years[date.year] = {}
            if date.month not in years[date.year]:
                years[date.year][date.month] = {}
            if date.day not in years[date.year][date.month]:
                years[date.year][date.month][date.day] = []
            years[date.year][date.month][date.day].append(post)

    state["years"] = years

    state["posts"] = sorted(
        state["posts"],
        # if post has "hms", sort by slug date then hms; otherwise, sort by slug
        key=lambda x: (
            "-".join(x.metadata["slug"].split("-")[:3]) + "-" + x.metadata.get("hms", "")
            if x.metadata.get("hms")
            else x["slug"]
        ),
        reverse=True,
    )

    all_dependencies = {
        k: v for k, v in all_dependencies.items() if not k.startswith("pages/_")
    }

    dependencies = (
        deps
        if incremental and len(deps) > 0
        else list(toposort_flatten(all_dependencies))
    )

    dependencies = [
        dependency
        for dependency in dependencies
        if not dependency.startswith("pages/_")
    ]

    if watch:
        iterator = dependencies
    else:
        iterator = tqdm.tqdm(dependencies)

    iterator_set = set(iterator)

    print("Generating pages in memory...")

    for file in iterator:
        if os.path.isdir(file):
            for root, _, files in os.walk(file):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file_path not in iterator_set:
                        render_page(file_path, skip_hooks=watch)
        else:
            render_page(file, skip_hooks=watch)

    print("Saving files to disk...")

    if not incremental:
        for root, _, files in os.walk("assets"):
            for file in files:
                path = os.path.join(SITE_DIR, root)
                if not os.path.exists(path):
                    os.makedirs(path)
                contents = read_file(os.path.join(root, file), "rb")

                with open(os.path.join(SITE_DIR, root, file), "wb") as f2:
                    f2.write(contents)

    if incremental and deps:
        for file in tqdm.tqdm(state_to_write):
            if original_file_to_permalink.get(file) in deps:
                with open(file, "wb", buffering=1000) as f:
                    f.write(state_to_write[file].encode())
    else:
        for file in tqdm.tqdm(state_to_write):
            with open(file, "wb", buffering=1000) as f:
                f.write(state_to_write[file].encode())

    if any(k.startswith("pages/") for k in all_dependencies):
        if "skip_date_archive_page_generation" not in SITE_STATE:
            process_date_archives()
        if "skip_category_page_generation" not in SITE_STATE:
            process_archives(
                SITE_STATE.get("category_template", "category"),
                "categories",
                SITE_STATE.get("category_slug_root", "category"),
            )
        if "skip_tag_page_generation" not in SITE_STATE:
            process_archives(
                SITE_STATE.get("tag_template", "tag"),
                "tags",
                SITE_STATE.get("tag_slug_root", "tag"),
            )

    for collection_name, attributes in SITE_STATE.get("paginators", {}).items():
        generate_paginated_page_for_collection(
            collection_name, attributes["per_page"], attributes["template"]
        )

    for hooks in EVALUATED_POST_BUILD_HOOKS.values():
        for hook in hooks:
            hook(state)

    if incremental:
        to_save = {
            "last_build": state["build_timestamp"],
            "data_file_integrity": data_file_integrity,
        }

        json.dump(to_save, open("state.json", "w"))

    print(
        f"Built site in \033[94m{(datetime.datetime.now() - start).total_seconds():.3f}s\033[0m ✨\n"
    )

    if watch:
        from livereload import Server

        srv = Server()

        for permalink, files in permalinks.items():
            if len(files) > 1:
                yellow = "\033[93m"
                print(
                    f"{yellow}Warning: {permalink} has multiple files: {files}{yellow}"
                )

        # logging.disable(logging.INFO)

        print("Live reload mode enabled.\nWatching for changes...\n")
        print("View your site at \033[92mhttp://localhost:8000\033[0m")
        print("Press Ctrl+C to stop.")

        srv.watch(ROOT_DIR, lambda: main(deps=[srv.watcher.filepath], incremental=True))
        srv.watch("./assets", lambda: copy_asset_to_site([srv.watcher.filepath]))
        srv.serve(root=SITE_DIR, liveport=35729, port=8000, debug=False)
    else:
        for permalink, files in permalinks.items():
            if len(files) > 1:
                yellow = "\033[93m"
                print(
                    f"{yellow}Warning: {permalink} has multiple files: {files}{yellow}"
                )
