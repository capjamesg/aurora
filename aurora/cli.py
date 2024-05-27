import os

import click

from . import __version__
from .graph import main as build_site


@click.group()
def main():
    pass


@click.command()
@click.option("--version", is_flag=True)
def version():
    print("Aurora version:", __version__)


@click.command("new")
@click.option(
    "--name", prompt="Site name", help="The name of the site.", default="site"
)
def new(name):
    if os.path.exists(name):
        print("Site already exists.")
        return

    os.makedirs(name)
    os.chdir(name)
    os.makedirs("pages")
    os.makedirs("_layouts")
    os.makedirs("posts")
    os.makedirs("assets")

    with open("pages/index.html", "w") as f:
        f.write("Hello, world!")

    with open("config.py", "w") as f:
        f.write(
            """import os

BASE_URLS = {
    "local": os.getcwd(),
}

SITE_ENV = os.environ.get("SITE_ENV", "local")
BASE_URL = BASE_URLS[SITE_ENV]
ROOT_DIR = "pages"
LAYOUTS_BASE_DIR = "_layouts"
SITE_DIR = "_site"
"""
        )

    print(f"Site {name} created.")


@click.command("build")
def build():
    build_site()
    print("Done! ✨")


@click.command("serve")
def serve():
    build_site(watch=True)


main.add_command(new)
main.add_command(version)
main.add_command(build)
main.add_command(serve)
