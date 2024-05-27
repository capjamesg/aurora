import os
import sys

if not os.path.exists("config.py"):
    raise Exception("config.py not found")

import datetime
import optparse
import re
import time

import pyromark
from frontmatter import loads
from jinja2 import (Environment, FileSystemLoader, environment, exceptions,
                    meta, nodes)
from jinja2.visitor import NodeVisitor
from progress.bar import IncrementalBar
from toposort import toposort, toposort_flatten
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .date_helpers import (archive_date, date_to_xml_string, list_archive_date,
                           long_date, month_number_to_written_month)

module_dir = os.getcwd()
os.chdir(module_dir)
# add to path
sys.path.append(module_dir)
from config import (BASE_URL, LAYOUTS_BASE_DIR, REGISTERED_HOOKS, ROOT_DIR,
                    SITE_DIR, SITE_ENV)

# for hook in registered hook, get all funcs
for hook in REGISTERED_HOOKS:
    REGISTERED_HOOKS[hook] = [
        getattr(__import__(hook), func) for func in REGISTERED_HOOKS[hook]
    ]

# get date of today w/ no time
today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
state = {
    "posts": [],
    "site": {"root_url": BASE_URL},
    "build_date": today.strftime("%m-%d"),
}
start = datetime.datetime.now()

if not os.path.exists(SITE_DIR):
    os.makedirs(SITE_DIR)
else:
    # remove all files in _site
    for root, dirs, files in os.walk(SITE_DIR):
        for file in files:
            os.remove(os.path.join(root, file))

JINJA2_ENV = Environment(loader=FileSystemLoader(ROOT_DIR), cache_size=2000)


def slugify(value):
    return value.lower().replace(" ", "-")


class VariableVisitor(NodeVisitor):
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

all_pages = []

for root, dirs, files in os.walk(ROOT_DIR):
    for file in files:
        all_pages.append(os.path.join(root, file))

all_opened_pages = {}

for page in all_pages:
    with open(page, "r") as f:
        try:
            if page.endswith(".md"):
                all_opened_pages[page] = f.read()
            else:
                all_opened_pages[page] = JINJA2_ENV.from_string(f.read())
        except:
            print(f"Error reading {page}")
            pass


all_dependencies = {}
all_parsed_pages = {}


def get_file_dependencies_and_evaluated_contents(file_name, contents):
    if isinstance(contents, str):
        template = JINJA2_ENV.parse(contents)
    else:
        # TODO: Make this more efficient
        with open(file_name, "r") as f:
            template = JINJA2_ENV.parse(f.read())

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

    parsed_content = None

    rendered_template = contents

    try:
        if (
            isinstance(rendered_template, environment.Template)
            and not file_name.startswith("pages/_layouts")
            and not file_name.startswith("pages/_includes")
            and not file_name.startswith("pages/templates")
        ):
            state["categories"] = []
            state["stream"] = []
            rendered_template = rendered_template.render(page=state, site=state)
        else:
            # open file and render
            with open(file_name, "r") as f:
                rendered_template = f.read()

        parsed_content = loads(rendered_template)
        parsed_content["slug"] = file_name.split("/")[-1].replace(".html", "")
        # if no categories, add
        # ADD ROOT URL
        parsed_content["contents"] = pyromark.markdown(parsed_content.content)
        parsed_content[
            "url"
        ] = f"{BASE_URL}/{file_name.replace(ROOT_DIR + '/posts/', '')}"
        if "categories" not in parsed_content:
            parsed_content["categories"] = []
        # slug = parsed_content.get("slug")
        # extract date slug w/ regex
        slug = file_name.split("/")[-1].replace(".html", "")

        slug = slug.replace("posts/", "")

        if slug:
            date_slug = re.search(r"\d{4}-\d{2}-\d{2}", slug)
            if date_slug:
                # print(date_slug)
                date_slug = date_slug.group(0)
                if not parsed_content.get("post"):
                    parsed_content["post"] = {}
                if not parsed_content.get("page"):
                    parsed_content["page"] = {}
                parsed_content["post"]["date"] = datetime.datetime.strptime(
                    date_slug, "%Y-%m-%d"
                )
                # date_without_year
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
                # add page.date
                parsed_content["page"]["date"] = parsed_content["post"]["date"]
                # add description
                if "description" not in parsed_content:
                    parsed_content["description"] = pyromark.markdown(
                        parsed_content.content.split("\n")[0]
                    )

        if "layout" in parsed_content:
            dependencies.add(
                f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{parsed_content['layout']}.html"
            )
            # if layout is post, add to state global
            # if parsed_content["layout"] == "post":
            if not state.get(parsed_content["layout"] + "s"):
                state[parsed_content["layout"] + "s"] = []

            state[parsed_content["layout"] + "s"].append(parsed_content)
    except exceptions.UndefinedError as e:
        raise e
    except Exception as e:
        # raise e
        print(f"Error parsing {file_name}")
        pass

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

# get all dates
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
    # sort by file name
    state["posts"],
    key=lambda x: x["slug"],
    reverse=True,
)


sorted_files = toposort(all_dependencies)


def make_any_nonexistent_directories(path):
    if not os.path.exists(path):
        os.makedirs(path)


# this needs to be a recursive function that builds up the page template
# every page has a --- front matter block with a layout key
# the layout key is the name of the layout to use
# the layout is a jinja2 template that is in _layouts
# the layout is rendered with the page content as the content variable
# this needs to happen recursively until there is no layout key in the front matter
def recursively_build_page_template_with_front_matter(
    front_matter, state, current_contents=""
):
    if front_matter and "layout" in front_matter.metadata:
        layout = front_matter.metadata["layout"]
        layout_path = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/{layout}.html"
        current_contents = loads(
            all_opened_pages[layout_path].render(
                state, content=current_contents, page=front_matter.metadata
            )
        ).content

        layout_front_matter = all_parsed_pages[layout_path]

        return recursively_build_page_template_with_front_matter(
            layout_front_matter, state, current_contents.strip()
        )

    return current_contents


def render_page(file):
    try:
        contents = all_opened_pages[file]
    except:
        print(f"Error reading {file}")
        return

    # print(f"Rendering {file}")

    page_state = state.copy()

    if all_parsed_pages[file]:
        slug = file.split("/")[-1].replace(".html", "")

        slug = slug.replace("posts/", "")

        # print(all_parsed_pages[file], )

        page_state["page"] = all_parsed_pages[file].metadata
        page_state["post"] = all_parsed_pages[file].metadata
        if not page_state["page"].get("permalink"):
            page_state["page"]["permalink"] = slug.strip("/")
        page_state["page"]["generated_on"] = datetime.datetime.now()

        if slug:
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
                # generate description using first paragraph
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
        if file.endswith(".md") and file.startswith("pages/posts"):
            contents = pyromark.markdown(loads(contents).content)
        elif file.endswith(".md"):
            contents = pyromark.markdown(contents)
        else:
            contents = loads(contents.render(page=page_state, site=state)).content
    except Exception as e:
        print(f"Error rendering {file}")
        print(e)
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
        # delete index.html dir
        if os.path.exists(os.path.join(SITE_DIR, "index.html")):
            os.remove(os.path.join(SITE_DIR, "index.html"))
        with open(os.path.join(SITE_DIR, "index.html"), "w") as f:
            f.write(rendered)

        return

    # print(f"Rendering {permalink}")

    if file.startswith("templates/"):
        if hasattr(page_state["page"], "permalink"):
            permalink = os.path.join(
                page_state["page"].permalink.strip("/"), "index.html"
            )
            print(f"Permalink: {permalink}")
        else:
            permalink = file.replace("templates/", "")

    make_any_nonexistent_directories(os.path.dirname(os.path.join(SITE_DIR, permalink)))

    permalink = os.path.join(SITE_DIR, permalink)

    try:
        with open(permalink, "w") as f:
            f.write(rendered)
    except Exception as e:
        print(f"Error writing {permalink}")
        print(e)


def process_date_archives():
    # print len of all posts
    # get all keys in all_opened_pages starting with ROOT_DIR + posts
    posts = [
        key for key in all_opened_pages.keys() if key.startswith(ROOT_DIR + "/posts")
    ]

    # get all dates
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

    for year in years:
        make_any_nonexistent_directories(os.path.join(SITE_DIR, str(year)))

        for month in years[year]:
            make_any_nonexistent_directories(
                os.path.join(SITE_DIR, str(year), str(month))
            )

            for day in years[year][month]:
                make_any_nonexistent_directories(
                    os.path.join(SITE_DIR, str(year), str(month), str(day))
                )

                date_archive_state = state.copy()
                date_archive_state["date"] = datetime.datetime(year, month, day)
                date_archive_state["posts"] = [
                    all_parsed_pages[post].metadata
                    for post in posts
                    if hasattr(all_parsed_pages[post], "metadata")
                    and all_parsed_pages[post].metadata.get("date")
                    == datetime.datetime(year, month, day)
                ]
                # render _layouts/date_archive.html
                date_archive_layout = f"{ROOT_DIR}/{LAYOUTS_BASE_DIR}/date_archive.html"
                date_archive_contents = all_opened_pages[date_archive_layout]
                rendered_page = date_archive_contents.render(
                    date_archive_state,
                    site=date_archive_state,
                    posts=date_archive_state["posts"],
                    page=date_archive_state,
                )

                rendered_page = recursively_build_page_template_with_front_matter(
                    all_parsed_pages[date_archive_layout],
                    date_archive_state,
                    loads(rendered_page).content,
                )

                with open(
                    os.path.join(
                        SITE_DIR, str(year), str(month), str(day), "index.html"
                    ),
                    "w",
                ) as f:
                    f.write(rendered_page)


def process_category_archives():
    # get all categories
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
        category_archive_state["posts"] = [
            post for post in state["posts"] if category in post.get("categories", [])
        ]

        rendered_page = category_archive_contents.render(
            category_archive_state,
            site=category_archive_state,
            posts=category_archive_state["posts"],
            page=category_archive_state,
        )

        rendered_page = recursively_build_page_template_with_front_matter(
            all_parsed_pages[category_archive_layout],
            category_archive_state,
            loads(rendered_page).content,
        )

        with open(os.path.join(SITE_DIR, slugify(category), "index.html"), "w") as f:
            f.write(rendered_page)


def main(deps=None, watch=False):
    # remove _layouts from all_dependencies
    dependencies = list(toposort_flatten(all_dependencies)) if not deps else deps

    # filter if starts with pages/_
    # because templates do not need to be directly rendered
    dependencies = [
        dependency
        for dependency in dependencies
        if not dependency.startswith("pages/_")
    ]

    for file in IncrementalBar("Building website...").iter(dependencies):
        if not os.path.exists(file):
            continue

        if os.path.isdir(file):
            for root, dirs, files in os.walk(file):
                for file in files:
                    render_page(os.path.join(root, file))
        else:
            render_page(file)

    process_date_archives()
    process_category_archives()

    class Watcher(FileSystemEventHandler):
        def on_modified(self, event):
            print(f"Detected change in {event.src_path}. Rebuilding.")
            file_name = event.src_path
            file_name = file_name.replace(os.getcwd() + "/", "")
            file_dependencies = all_dependencies[file_name]
            file_dependencies.add(file_name)

            main(deps=file_dependencies)

    if watch:
        observer = Observer()
        observer.schedule(Watcher(), path="pages", recursive=True)
        observer.start()

        print("Watching for changes in pages directory")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
