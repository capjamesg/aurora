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
    os.chdir("pages")
    os.makedirs("_layouts")
    os.makedirs("_data")
    os.makedirs("posts")
    os.makedirs("assets")

    with open("index.html", "w") as f:
        f.write("Hello, world!")

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
REGISTERED_HOOKS = {}
SITE_STATE = {}
"""
        )

    print(f"Site {name} created.")


@click.command("build")
def build():
    from .graph import main as build_site

    # import cProfile
    # cProfile.runctx("build_site()", globals(), locals(), filename="profile.prof")
    print("Building site...")
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
