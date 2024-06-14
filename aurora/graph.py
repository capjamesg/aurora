import os
import sys

if not os.path.exists("config.py"):
    raise Exception("config.py not found")

import datetime
import re
import time
from copy import deepcopy

import orjson
import pyromark
import tqdm
from jinja2 import (Environment, FileSystemBytecodeCache, FileSystemLoader,
                    Template, meta, nodes)
from jinja2.visitor import NodeVisitor
from ryaml_python_frontmatter import loads
from toposort import toposort, toposort_flatten
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .date_helpers import (archive_date, date_to_xml_string, list_archive_date,
                           long_date, month_number_to_written_month)

module_dir = os.getcwd()
os.chdir(module_dir)
sys.path.append(module_dir)

from config import (BASE_URL, LAYOUTS_BASE_DIR, REGISTERED_HOOKS, ROOT_DIR,
                    SITE_DIR, SITE_ENV)

DATA_FILES_DIR = os.path.join(ROOT_DIR, "_data")

for hook in REGISTERED_HOOKS:
    REGISTERED_HOOKS[hook] = [
        getattr(__import__(hook), func) for func in REGISTERED_HOOKS[hook]
    ]

today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
state = {
    "posts": [],
    "site": {"root_url": BASE_URL},
    "build_date": today.strftime("%m-%d"),
    "pages": [],
}
start = datetime.datetime.now()

if not os.path.exists(SITE_DIR):
    os.makedirs(SITE_DIR)
else:
    # remove all files in _site
    for root, dirs, files in os.walk(SITE_DIR):
        for file in files:
            os.remove(os.path.join(root, file))

JINJA2_ENV = Environment(
    loader=FileSystemLoader(ROOT_DIR), bytecode_cache=FileSystemBytecodeCache()
)

state_to_write = {}


def slugify(value: str) -> str:
    """
    Turn a string into a slug for use in saving data to a file.
    """
    return value.lower().replace(" ", "-")


class Watcher(FileSystemEventHandler):
    def on_modified(self, event):
        print(f"Detected change in {event.src_path}. Rebuilding.")
        # file_name = event.src_path
        # file_name = file_name.replace(os.getcwd() + "/", "")
        # file_dependencies = all_dependencies[file_name]
        # file_dependencies.add(file_name)

        main()  # deps=file_dependencies)


class VariableVisitor(NodeVisitor):
    """
    Find all variables in a jinja2 template.
    """

    def __init__(self):
        self.variables = set()

    def visit_Name(self, node, *args, **kwargs):
        self.variables.add(node.name)
        self.generic_visit(node, *args, **kwargs)

    def visit_Getattr(self, node, *args, **kwargs):
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


JINJA2_ENV.filters["long_date"] = long_date
JINJA2_ENV.filters["date_to_xml_string"] = date_to_xml_string
JINJA2_ENV.filters["archive_date"] = archive_date
JINJA2_ENV.filters["list_archive_date"] = list_archive_date
JINJA2_ENV.filters["month_number_to_written_month"] = month_number_to_written_month

ALLOWED_EXTENSIONS = ["html", "md", "css", "js", "txt", "xml"]

all_data_files = {}

for file in os.listdir(DATA_FILES_DIR):
    with open(os.path.join(DATA_FILES_DIR, file), "r") as f:
        all_data_files[file] = orjson.loads(f.read())
        state[file.replace(".orjson", "")] = all_data_files[file]

all_pages = []

for root, dirs, files in os.walk(ROOT_DIR):
    for file in files:
        ext = os.path.splitext(file)[-1].replace(".", "")
        if ext not in ALLOWED_EXTENSIONS:
            continue

        all_pages.append(os.path.join(root, file))

all_opened_pages = {}
all_page_contents = {}

for page in all_pages:
    with open(page, "r") as f:
        contents = f.read()
        try:
            if page.endswith(".md"):
                all_opened_pages[page] = contents
            else:
                all_opened_pages[page] = JINJA2_ENV.from_string(contents)

            all_page_contents[page] = loads(contents)
        except Exception as e:
            print(f"Error reading {page}")
            pass

for data_file in all_data_files:
    data_dir = data_file.replace(".json", "")
    for record in all_data_files[data_file]:
        contents = "---\n" + orjson.dumps(record).decode() + "\n---\n"
        all_opened_pages[
            os.path.join(ROOT_DIR, data_dir, record.get("slug"))
        ] = JINJA2_ENV.from_string(contents)
        all_page_contents[os.path.join(ROOT_DIR, data_dir, record.get("slug"))] = loads(
            contents
        )

all_dependencies = {}
all_parsed_pages = {}


def get_file_dependencies_and_evaluated_contents(
    file_name: str, contents: Template
) -> tuple:
    """
    Get all dependencies of a file. Dependencies are:

    1. Other files that are included in the file, and;
    2. Variables whose values are defined by the site generator (i.e. `site.*`).
    """
    template = JINJA2_ENV.parse(contents)

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
        if not variable.startswith("site."):
            continue

        variable = variable.replace("site.", "")
        dependencies.add(f"{ROOT_DIR}/{variable}")

    parsed_content = all_page_contents[file_name]

    parsed_content["slug"] = file_name.split("/")[-1].replace(".html", "")
    parsed_content["contents"] = pyromark.markdown(parsed_content.content)

    parsed_content["url"] = f"{BASE_URL}/{file_name.replace(ROOT_DIR + '/posts/', '')}"

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
                parsed_content["description"] = pyromark.markdown(
                    parsed_content.content.split("\n")[0]
                )
            date_slug = date_slug.replace("-", "/")
            slug_without_date = re.sub(r"\d{4}-\d{2}-\d{2}-", "", slug)

            parsed_content[
                "url"
            ] = f"{BASE_URL}/{date_slug}/{slug_without_date.replace('.html', '').replace('.md', '')}/"

    if "layout" in parsed_content:
        dependencies.add(
            f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{parsed_content['layout']}.html"
        )
        if not state.get(parsed_content["layout"] + "s"):
            state[parsed_content["layout"] + "s"] = []

        state[parsed_content["layout"] + "s"].append(parsed_content)

    if "collection" in parsed_content:
        collection_normalized = parsed_content["collection"].lower()
        if not state.get(collection_normalized):
            state[collection_normalized] = []

        state[collection_normalized].append(parsed_content)

    return dependencies, parsed_content


for page, contents in all_opened_pages.items():
    dependencies, parsed_page = get_file_dependencies_and_evaluated_contents(
        page, contents
    )
    all_dependencies[page] = dependencies
    all_parsed_pages[page] = parsed_page

    if page.startswith("posts/"):
        state["posts"].append(parsed_page)

posts = [key for key in all_opened_pages.keys() if key.startswith(ROOT_DIR + "/posts")]

dates = set()
years = {}

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
    key=lambda x: x["slug"],
    reverse=True,
)


sorted_files = toposort(all_dependencies)


def make_any_nonexistent_directories(path):
    if not os.path.exists(path):
        os.makedirs(path)


def interpolate_front_matter(front_matter: dict, state: dict):
    """Evaluate front matter with Jinja2 to allow logic in front matter."""
    if "title" in front_matter.metadata:
        title = front_matter.metadata["title"]

        title = JINJA2_ENV.from_string(str(title)).render(
            page=front_matter.metadata, site=state
        )
        front_matter.metadata["title"] = title

    return front_matter


def recursively_build_page_template_with_front_matter(
    front_matter: dict, state: dict, current_contents: str = ""
):
    """
    Recursively build a page template with front matter.

    This function is called recursively until there is no layout key in the front matter.
    """

    if front_matter and "layout" in front_matter.metadata:
        layout = front_matter.metadata["layout"]
        layout_path = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{layout}.html"
        print(front_matter.metadata.get("title"))

        page_fm = type(
            "Page", (object,), front_matter.metadata.get("page", front_matter.metadata)
        )()

        current_contents = loads(
            all_opened_pages[layout_path].render(
                page=page_fm,
                site=state,
                content=current_contents,
                post=front_matter.metadata,
            )
        ).content

        layout_front_matter = all_parsed_pages[layout_path]

        # combine current front matter so that we can access it in the layout
        if "page" in layout_front_matter.metadata:
            layout_front_matter["page"] = {
                **layout_front_matter.metadata["page"],
                **front_matter.metadata,
            }
        else:
            layout_front_matter["page"] = front_matter.metadata

        return recursively_build_page_template_with_front_matter(
            layout_front_matter, state, current_contents.strip()
        )

    return current_contents


def render_page(file: str) -> None:
    """
    Render a page with the Aurora static site generator.
    """
    try:
        contents = all_opened_pages[file]
    except:
        print(f"Error reading {file}")
        return

    page_state = state.copy()

    if all_parsed_pages[file]:
        slug = file.split("/")[-1].replace(".html", "")

        slug = slug.replace("posts/", "")

        page_state["page"] = all_parsed_pages[file].metadata
        page_state["post"] = all_parsed_pages[file].metadata
        if not page_state["page"].get("permalink"):
            page_state["page"]["permalink"] = slug.strip("/")

        page_state["page"]["generated_on"] = datetime.datetime.now()

        if slug[0].isdigit():
            date_slug = re.search(r"\d{4}-\d{2}-\d{2}", slug)
            if date_slug:
                date_slug = date_slug.group(0)
                page_state["post"]["date"] = datetime.datetime.strptime(
                    date_slug, "%Y-%m-%d"
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
            slug = (
                slug.replace("pages/posts/", "").replace(".md", "").replace(".html", "")
            )
            page_state["page"]["slug"] = slug
            page_state["page"][
                "url"
            ] = f"{BASE_URL}/{date.strftime('%Y/%m/%d')}/{slug}/"
        else:
            page_state["page"]["url"] = f"{BASE_URL}/{slug}/"

        page_state["url"] = page_state["page"]["url"]

    if not page_state.get("categories"):
        page_state["categories"] = []

    state["categories"] = []
    state["stream"] = []

    if page_state.get("page"):
        page_state["page"] = type("Page", (object,), page_state["page"])()
        page_state["post"] = type("Post", (object,), page_state["post"])()

    # run hooks on page_state
    for hook, hooks in REGISTERED_HOOKS.items():
        for hook in hooks:
            page_state = hook(file, page_state, state)

    try:
        if file.endswith(".md"):
            contents = pyromark.markdown(loads(all_opened_pages[file]).content)
        else:
            contents = loads(contents.render(page=page_state, site=state)).content
    except Exception as e:
        print(f"Error rendering {file}")
        return

    rendered = recursively_build_page_template_with_front_matter(
        all_parsed_pages[file], page_state, contents
    )

    file = file.replace(ROOT_DIR + "/", "")

    if page_state.get("date"):
        file = f"{date.strftime('%Y/%m/%d')}/{slug}/index.html"

    if file.endswith(".md"):
        file = file[:-3] + ".html"

    permalink = file

    # if permalink is _site/templates/index.html, make it _site/index.html
    if file == "templates/index.html":
        if os.path.exists(os.path.join(SITE_DIR, "index.html")):
            os.remove(os.path.join(SITE_DIR, "index.html"))
        with open(os.path.join(SITE_DIR, "index.html"), "w") as f:
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
    else:
        permalink = file.replace("templates/", "")

    if permalink.endswith(".html"):
        make_any_nonexistent_directories(
            os.path.dirname(os.path.join(SITE_DIR, permalink))
        )
    else:
        make_any_nonexistent_directories(os.path.join(SITE_DIR))

    permalink = os.path.join(SITE_DIR, permalink)

    state_to_write[permalink] = rendered

    state["pages"].append({"url": f"{BASE_URL}/{permalink}", "file": file})


def process_date_archives() -> None:
    """
    Generate date archives for all posts.

    For example, if there are posts on 2022-01-01 and 2022-01-02, generate:

    - /2022/index.html
    - /2022/01/index.html
    - /2022/01/01/index.html
    """
    posts = [
        key for key in all_opened_pages.keys() if key.startswith(ROOT_DIR + "/posts")
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
                # ymd path str(year), str(month), str(day), should ahve leading zeros
                ymd = f"{year}/{str(month).zfill(2)}/{str(day).zfill(2)}"
                ymd_path = os.path.join(SITE_DIR, ymd)

                make_any_nonexistent_directories(ymd_path)

                date_archive_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/date_archive.html"
                date_archive_contents = all_opened_pages[date_archive_layout]

                date_archive_state = state.copy()
                current_date = datetime.datetime(year, month, day)
                date_archive_state["date"] = current_date

                page = deepcopy(all_parsed_pages[date_archive_layout])
                page["date"] = current_date

                date_archive_state["posts"] = [
                    all_parsed_pages[post].metadata
                    for post in posts
                    if all_parsed_pages[post].metadata.get("date") == current_date
                ]

                fm = interpolate_front_matter(page, date_archive_state)

                rendered_page = date_archive_contents.render(
                    date_archive_state,
                    site=date_archive_state,
                    posts=date_archive_state["posts"],
                    page=date_archive_state,
                )

                rendered_page = recursively_build_page_template_with_front_matter(
                    fm, date_archive_state, loads(rendered_page).content
                )

                with open(
                    os.path.join(ymd_path, "index.html"),
                    "wb",
                    buffering=500,
                ) as f:
                    f.write(rendered_page.encode())


def process_category_archives():
    """
    Generate category archives for all posts.

    For example, if you have a post with the `category` key set to `writing`, generate:

    - /writing/index.html
    """
    categories = set()
    for post in state["posts"]:
        if not post.get("categories"):
            continue

        for category in post["categories"]:
            categories.add(category)

    for category in categories:
        make_any_nonexistent_directories(os.path.join(SITE_DIR, slugify(category)))

        category_archive_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/category.html"
        category_archive_contents = all_opened_pages[category_archive_layout]

        category_archive_state = state.copy()
        category_archive_state["category"] = category
        page = deepcopy(all_parsed_pages[category_archive_layout])
        page["category"] = category
        category_archive_state["posts"] = [
            post for post in state["posts"] if category in post.get("categories", [])
        ]

        fm = interpolate_front_matter(page, category_archive_state)

        rendered_page = category_archive_contents.render(
            category_archive_state,
            site=category_archive_state,
            posts=category_archive_state["posts"],
            page=category_archive_state,
        )

        rendered_page = recursively_build_page_template_with_front_matter(
            fm, category_archive_state, loads(rendered_page).content
        )

        with open(
            os.path.join(SITE_DIR, slugify(category), "index.html"), "wb", buffering=500
        ) as f:
            f.write(rendered_page.encode())


def main(deps: list = None, watch: bool = False) -> None:
    """
    The Aurora runtime.

    Aurora can be run in two ways:

    - `aurora build` to build the site once, and;
    - `aurora serve` to watch for changes in the `pages` directory and rebuild the site in real time.
    """

    dependencies = list(toposort_flatten(all_dependencies)) if not deps else deps

    dependencies = [
        dependency
        for dependency in dependencies
        if not dependency.startswith("pages/_")
    ]

    for file in tqdm.tqdm(dependencies):
        if os.path.isdir(file):
            for root, dirs, files in os.walk(file):
                for file in files:
                    render_page(os.path.join(root, file))
        else:
            render_page(file)

    for file in state_to_write:
        with open(file, "wb", buffering=1000) as f:
            f.write(state_to_write[file].encode())

    process_date_archives()
    process_category_archives()

    print(f"Built site in {datetime.datetime.now() - start}")

    if watch:
        observer = Observer()
        observer.schedule(Watcher(), path="pages", recursive=True)
        observer.start()

        print("Watching for changes...")
        print("View your site at ", os.path.join(os.getcwd(), SITE_DIR, "index.html"))
        print("Press Ctrl+C to stop.")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
