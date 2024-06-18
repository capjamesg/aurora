import logging
import os
import sys

if not os.path.exists("config.py"):
    raise Exception("config.py not found")

import datetime
import re
from copy import deepcopy

import csv
import orjson
import pyromark
from yaml.reader import ReaderError
import tqdm
from frontmatter import loads
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

from .date_helpers import (
    archive_date,
    date_to_xml_string,
    list_archive_date,
    long_date,
    month_number_to_written_month,
)

module_dir = os.getcwd()
os.chdir(module_dir)
sys.path.append(module_dir)
state_to_write = {}
original_file_to_permalink = {}

# print all logs
logging.basicConfig(level=logging.INFO)


from config import BASE_URL, LAYOUTS_BASE_DIR, ROOT_DIR, SITE_DIR, SITE_STATE, HOOKS

ALLOWED_EXTENSIONS = ["html", "md", "css", "js", "txt", "xml"]

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

# ensures a single template cannot have more than 10 levels of inheritance
INHERITANCE_LIMIT = 10

DATA_FILES_DIR = os.path.join(ROOT_DIR, "_data")

EVALUATED_REGISTERED_TEMPLATE_GENERATION_HOOKS = {}
EVALUATED_POST_BUILD_HOOKS = {}

for file_name, hooks in HOOKS.get("pre_template_generation", {}).items():
    EVALUATED_REGISTERED_TEMPLATE_GENERATION_HOOKS[file_name] = [
        getattr(__import__(file_name), func) for func in hooks
    ]

for file_name, hooks in HOOKS.get("post_build", {}).items():
    EVALUATED_POST_BUILD_HOOKS[file_name] = [
        getattr(__import__(file_name), func) for func in hooks
    ]

today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
state = {
    "posts": [],
    "root_url": BASE_URL,
    "build_date": today.strftime("%m-%d"),
    "pages": [],
}

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

for file_name, hooks in HOOKS.get("template_filters", {}).items():
    for hook in hooks:
        JINJA2_ENV.filters[hook] = getattr(__import__(file_name), hook)


def slugify(value: str) -> str:
    """
    Turn a string into a slug for use in saving data to a file.
    """
    return value.lower().replace(" ", "-")


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
        if not variable.startswith("site."):
            continue

        variable = variable.replace("site.", "")

        for collection in collections_to_files:
            if collections_to_files.get(collection):
                dependencies.update(collections_to_files[collection])

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

            parsed_content["url"] = (
                f"{BASE_URL}/{date_slug}/{slug_without_date.replace('.html', '').replace('.md', '')}/"
            )

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


def make_any_nonexistent_directories(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def interpolate_front_matter(front_matter: dict, state: dict) -> dict:
    """Evaluate front matter with Jinja2 to allow logic in front matter."""

    for key in front_matter.keys():
        if (
            isinstance(front_matter[key], str)
            and "{" in front_matter[key]
            and key != "contents"
        ):
            item = front_matter[key]

            item = JINJA2_ENV.from_string(item).render(
                page=front_matter.get("page"), site=state
            )
            front_matter[key] = item

    return front_matter


def recursively_build_page_template_with_front_matter(
    file_name: str,
    front_matter: dict,
    state: dict,
    current_contents: str = "",
    level: int = 0,
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

        front_matter.metadata["page"] = interpolate_front_matter(
            front_matter.metadata, state
        )

        # if "Aurora" in title
        #
        # print(front_matter.metadata.get("title"))

        page_fm = type(
            "Page", (object,), front_matter.metadata.get("page", front_matter.metadata)
        )()

        if hasattr(page_fm, "page"):
            page_fm = type("Page", (object,), page_fm.page)()


        current_contents = loads(
            all_opened_pages[layout_path].render(
                page=page_fm,
                site=state,
                content=current_contents,
                post=type("Post", (object,), front_matter.metadata.get("page", {}))()
            )
        ).content

        layout_front_matter = all_parsed_pages[layout_path]

        layout_front_matter["page"] = front_matter.metadata
        layout_front_matter["post"] = front_matter.metadata

        return recursively_build_page_template_with_front_matter(
            file_name, layout_front_matter, state, current_contents.strip(), level + 1
        )

    return current_contents

def render_page(file: str) -> None:
    """
    Render a page with the Aurora static site generator.
    """

    original_file = file

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

    if file == "pages/templates/index.html":
        page_state["url"] = BASE_URL
        page_state["page"]["url"] = BASE_URL
        page_state["page"]["permalink"] = BASE_URL

    if not page_state.get("categories"):
        page_state["categories"] = []

    state["categories"] = []
    state["stream"] = []

    if page_state.get("page"):
        page_state["page"] = type("Page", (object,), page_state["page"])()
        page_state["post"] = type("Post", (object,), page_state["post"])()

    for hook, hooks in EVALUATED_REGISTERED_TEMPLATE_GENERATION_HOOKS.items():
        for hook in hooks:
            page_state = hook(file, page_state, state)

    try:
        if file.endswith(".md"):
            contents = pyromark.markdown(loads(all_opened_pages[file]).content)
        elif isinstance(contents, str):
            # this happens for data files only, where content is in the
            contents = ""
        else:
            contents = loads(contents.render(page=page_state, site=state)).content
    except Exception as e:
        print(f"Error rendering {file}")
        return

    rendered = recursively_build_page_template_with_front_matter(
        file, all_parsed_pages[file], page_state, contents
    )

    file = file.replace(ROOT_DIR + "/", "")

    if page_state.get("date"):
        file = f"{date.strftime('%Y/%m/%d')}/{slug}/index.html"

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
    else:
        permalink = file.replace("templates/", "")

    permalink = os.path.join(SITE_DIR, permalink)

    if permalink.endswith(".html"):
        make_any_nonexistent_directories(os.path.dirname(permalink))
    else:
        make_any_nonexistent_directories(os.path.join(SITE_DIR))

    state_to_write[permalink] = rendered
    original_file_to_permalink[permalink] = original_file

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
                # ymd path str(year), str(month), str(day), should have leading zeros
                ymd = f"{year}/{str(month).zfill(2)}/{str(day).zfill(2)}"
                ymd_path = os.path.join(SITE_DIR, ymd)

                make_any_nonexistent_directories(ymd_path)

                date_archive_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/date.html"

                if not all_opened_pages.get(date_archive_layout):
                    continue

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
                    site=state,
                    posts=date_archive_state["posts"],
                    page=date_archive_state,
                )

                rendered_page = recursively_build_page_template_with_front_matter(
                    ymd_path, fm, date_archive_state, loads(rendered_page).content
                )

                with open(
                    os.path.join(ymd_path, "index.html"),
                    "wb",
                    buffering=500,
                ) as f:
                    f.write(rendered_page.encode())


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
        make_any_nonexistent_directories(os.path.join(SITE_DIR, path, slugify(category)))

        archive_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{name}.html"
        archive_contents = all_opened_pages[archive_layout]

        archive_state = state.copy()
        archive_state[name] = category
        page = deepcopy(all_parsed_pages[archive_layout])
        page[name] = category
        archive_state["posts"] = [
            post for post in state["posts"] if category in post.get(state_key_associated_with_name, [])
        ]

        fm = interpolate_front_matter(page, archive_state)

        rendered_page = archive_contents.render(
            archive_state,
            site=state,
            posts=archive_state["posts"],
            page=archive_state,
        )

        rendered_page = recursively_build_page_template_with_front_matter(
            archive_layout,
            fm,
            archive_state,
            loads(rendered_page).content,
        )

        with open(
            os.path.join(SITE_DIR, path, slugify(category), "index.html"), "wb", buffering=500
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
        with open(os.path.join("assets", a), "rb") as f:
            with open(os.path.join(SITE_DIR, "assets", a), "wb") as f2:
                f2.write(f.read())


def main(deps: list = [], watch: bool = False) -> None:
    """
    The Aurora runtime.

    Aurora can be run in two ways:

    - `aurora build` to build the site once, and;
    - `aurora serve` to watch for changes in the `pages` directory and rebuild the site in real time.
    """

    start = datetime.datetime.now()

    if not os.path.exists(SITE_DIR):
        os.makedirs(SITE_DIR)
    else:
        if not deps:
            for root, dirs, files in os.walk(SITE_DIR):
                for file in files:
                    os.remove(os.path.join(root, file))

    if os.path.exists(DATA_FILES_DIR):
        for file in os.listdir(DATA_FILES_DIR):
            if deps and file not in deps:
                continue

            if os.path.splitext(file)[-1].replace(".", "") == "json":
                with open(os.path.join(DATA_FILES_DIR, file), "r") as f:
                    all_data_files[file] = orjson.loads(f.read())
                    state[file.replace(".json", "")] = all_data_files[file]
            elif os.path.splitext(file)[-1].replace(".", "") == "csv":
                with open(os.path.join(DATA_FILES_DIR, file), "r") as f:
                    all_data_files[file] = list(csv.DictReader(f))
                    state[file.replace(".csv", "")] = all_data_files[file]
            else:
                logging.debug(
                    f"Unsupported data file format: {file}", level=logging.CRITICAL
                )

    for root, dirs, files in os.walk(ROOT_DIR):
        for file in files:
            ext = os.path.splitext(file)[-1].replace(".", "")
            if ext not in ALLOWED_EXTENSIONS:
                continue

            all_pages.append(os.path.join(root, file))

    for page in all_pages:
        if deps and page not in deps:
            continue

        with open(page, "r") as f:
            contents = f.read()
            try:
                if page.endswith(".md"):
                    all_opened_pages[page] = contents
                else:
                    all_opened_pages[page] = JINJA2_ENV.from_string(contents)

                all_page_contents[page] = loads(contents)
            except Exception as e:
                logging.debug(f"Error reading {page}", level=logging.CRITICAL)
                pass

    for data_file in all_data_files:
        data_dir = data_file.replace(".json", "").replace(".csv", "")
        collections_to_files[data_dir] = []
        idx = 0
        for record in tqdm.tqdm(all_data_files[data_file]):
            if not record.get("slug"):
                record["slug"] = str(idx)
                idx += 1
                # logging.debug(
                #     f"Error: {data_file} {record} does not have a 'slug' key. This page will not be generated.",
                #     level=logging.CRITICAL,
                # )
                # continue
                #

            if (
                deps
                and os.path.join(ROOT_DIR, data_dir, record.get("slug"), "index.html")
                not in deps
            ):
                continue

            if not record.get("layout"):
                record["layout"] = data_dir

            slug = record.get("slug")
            path = os.path.join(ROOT_DIR, data_dir, slug, "index.html")

            try:
                contents = "---\n" + orjson.dumps(record).decode() + "\n---\n"
                all_opened_pages[path] = ""
                # construct an object called Metadata that can be set
                record = {"metadata": record, "content": ""}

                metadata = type("Document", (object,), record)
                all_page_contents[path] = loads(contents)
                collections_to_files[data_dir].append(path)
            except ReaderError as e:
                logging.debug(
                    f"Error reading {data_file} {record}. This page will not be generated.",
                    level=logging.CRITICAL,
                )
                # delete from all_page_contents
                all_page_contents.pop(path, None)
                all_opened_pages.pop(path, None)
                continue

    for page, contents in all_opened_pages.items():
        if deps and page not in deps:
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

    if deps:
        deps = set(deps)
        new_deps = []

        while deps:
            dep = deps.pop()
            new_deps.append(dep)
            if dep in reverse_deps:
                deps.update(reverse_deps[dep])

        deps = new_deps

    posts = [
        key for key in all_opened_pages.keys() if key.startswith(ROOT_DIR + "/posts")
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
        key=lambda x: x["slug"],
        reverse=True,
    )

    dependencies = list(toposort_flatten(all_dependencies)) if not deps else deps

    dependencies = [
        dependency
        for dependency in dependencies
        if not dependency.startswith("pages/_")
    ]

    if watch:
        iterator = dependencies
    else:
        iterator = tqdm.tqdm(dependencies)

    for file in iterator:
        if os.path.isdir(file):
            for root, dirs, files in os.walk(file):
                for file in files:
                    render_page(os.path.join(root, file))
        else:
            render_page(file)

    if deps:
        for file in state_to_write:
            if original_file_to_permalink.get(file) in deps:
                with open(file, "wb", buffering=1000) as f:
                    f.write(state_to_write[file].encode())
    else:
        for root, dirs, files in os.walk("assets"):
            for file in files:
                path = os.path.join(SITE_DIR, root)
                if not os.path.exists(path):
                    os.makedirs(path)
                with open(os.path.join(root, file), "rb") as f:
                    with open(os.path.join(SITE_DIR, root, file), "wb") as f2:
                        f2.write(f.read())

        for file in state_to_write:
            with open(file, "wb", buffering=1000) as f:
                f.write(state_to_write[file].encode())

        process_date_archives()
        process_archives(SITE_STATE.get("category_template", "category"), "categories", SITE_STATE.get("category_slug_root", "category"))
        process_archives(SITE_STATE.get("tag_template", "tag"), "tags", SITE_STATE.get("tag_slug_root", "tag"))

    for key, hooks in EVALUATED_POST_BUILD_HOOKS.items():
        for hook in hooks:
            hook(state)

    print(
        f"Built site in \033[94m{(datetime.datetime.now() - start).total_seconds():.3f}s\033[0m ✨\n"
    )

    if watch:
        from livereload import Server

        srv = Server()

        # logging.disable(logging.INFO)

        print("Live reload mode enabled.\nWatching for changes...\n")
        print("View your site at \033[92mhttp://localhost:8000\033[0m")
        print("Press Ctrl+C to stop.")

        srv.watch(ROOT_DIR, lambda: main(deps=[srv.watcher.filepath]))
        srv.watch("./assets", lambda: copy_asset_to_site([srv.watcher.filepath]))
        srv.serve(root=SITE_DIR, liveport=35729, port=8000, debug=False)
