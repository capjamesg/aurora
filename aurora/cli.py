import os

import click

from . import __version__


@click.group()
def main():
    pass


@click.command()
@click.option("--version", is_flag=True)
def version():
    print("Aurora version:", __version__)


@click.command("new")
@click.argument("name")
def new(name):
    cli_dir = os.path.dirname(os.path.realpath(__file__))
    if os.path.exists(name):
        print("Site already exists.")
        return

    os.makedirs(name)
    os.chdir(name)
    os.makedirs("pages")
    os.makedirs("assets")
    os.chdir("pages")
    os.makedirs("_layouts")
    os.makedirs("_data")
    os.makedirs("posts")

    with open("index.html", "w") as f:
        with open(os.path.join(cli_dir, "templates", "index.html")) as index:
            f.write(index.read())

    os.chdir("..")

    with open("config.py", "w") as f:
        f.write(
            """import os

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
"""
        )

    print(f"Site {name} created. ✨")
    print("Run cd/into the site directory.")
    print("Then, `aurora build` to build the site.")
    print("You can also `aurora serve` to start a local server.")


@click.command("build")
def build():
    from .graph import main as build_site

    # import cProfile
    # cProfile.runctx("build_site()", globals(), locals(), filename="profile.prof")
    # print("Building site...")
    build_site()
    print("Done! ✨")


@click.command("serve")
def serve():
    from .graph import main as build_site

    build_site(watch=True)


main.add_command(new)
main.add_command(version)
main.add_command(build)
main.add_command(serve)
