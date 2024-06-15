![Banner](banner.png)

<div align="center">

[![version](https://badge.fury.io/py/aurora-ssg.svg)](https://badge.fury.io/py/aurora-ssg)
[![downloads](https://img.shields.io/pypi/dm/aurora-ssg)](https://pypistats.org/packages/aurora-ssg)
[![license](https://img.shields.io/pypi/l/aurora-ssg)](https://github.com/capjamesg/aurora-ssg/blob/main/LICENSE.md)
[![python-version](https://img.shields.io/pypi/pyversions/aurora-ssg)](https://badge.fury.io/py/aurora-ssg)
</div>

# Aurora

Aurora is a static site generator implemented in Python.

## Demos

### Static Generation (1k+ pages)

https://github.com/capjamesg/aurora/assets/37276661/59e4f3e6-f470-46bd-8812-0b475be40e88

### Incremental Static Regeneration

https://github.com/capjamesg/aurora/assets/37276661/39f62bd8-cf5f-4d15-a325-7d433b7ceeb0

## Get Started

### Install Aurora

First, install Aurora:

```bash
pip3 install aurora-ssg
```

### Create a Site

To create a new site, run the following command:

```bash
aurora new my-site
```

This will create a folder called `my-site` with everything you need to start your Aurora site.

To navigate to your site, run:

```bash
cd my-site
```

Aurora sites contain a few directories by default:

- `_layouts`: Store templates for your site.
- `assets`: Store static files like images, CSS, and JavaScript.
- `posts`: Store blog posts (optional).
- `pages`: Store static pages to generate.

A new Aurora site will come with a `pages/index.html` file that you can edit to get started.

### Build Your Site (Static)

You can build your site into a static site by running the `aurora build` command.

Aurora works relative to the directory you are in.

To build your site, navigate run the following command:

```bash
aurora build
```

This will generate your site in a `_site` directory.

### Build Your Site (Dynamic)

For development purposes, you can run Aurora with a watcher that will automatically rebuild your site when you make changes to any page in your website.

To run Aurora in watch mode, run the following command:

```bash
aurora serve
```

Your site will be built in the `_site` directory. Any time you make a change to your templates, the `_site` directory will be updated to reflect those changes.

### Development Setup

If you are interested in contributing to Aurora, you will need a local development setup.

To set up your development environment, run the following commands:

```bash
git clone https://github.com/capjamesg/aurora
cd aurora
pip3 install -e .
```

This will install Aurora in editable mode. In editable mode, you can make changes to the code and see them reflected in your local installation.

## Aurora Site Structure

By default, an Aurora site has the following structure in the root directory:

- `pages`: Where all pages used to generate your site are stored.
- `pages/_layouts`: Where you can store layouts for use in generating your website.
- `pages/_data`: Where you can store JSON data files for use in generating pages. See the "Render Collections of Data" section later in this document for information on how to use this directory to generate pages from data files.
- `pages/posts`: Where you can store all of your blog posts, if you use your site as a blog. The posts directory is processed with additional logic to automatically generate date archive and category archive pages, if applicable.

Any file in `pages` or a folder you make in `pages` (not including `_layouts` and `_data`) will be rendered on your website. For example, if you create a `pages/interests/coffee.html` file, this will generate a page called `_site/pages/interests/coffee/index.html`.

## Configuration

You need a `config.py` file in the directory in which you will build your Aurora site. This file is automatically generated when you run `aurora new [site-name]`.

This configuration file defines a few values that Aurora will use when processing your website.

Here is the default `config.py` file, with accompanying comments:

```python
import os

BASE_URLS = {
    "local": os.getcwd(),
}

SITE_ENV = os.environ.get("SITE_ENV", "local")
BASE_URL = BASE_URLS[SITE_ENV]
ROOT_DIR = "pages" # where your site pages are
LAYOUTS_BASE_DIR = "_layouts" # where your site layouts are stored
SITE_DIR = "_site" # the directory in which your site will be saved
REGISTERED_HOOKS = {} # used to register hooks (see `Build Hooks (Advanced)` documentation below for details)
```

The `BASE_URLS` dictionary is used to define the base URL for your site. This is useful if you want to maintain multiple environments for your site (e.g., local, staging, production).

Here is an example configuration of a site that has a local and staging environment:

```python
BASE_URLS = {
    "production": "https://jamesg.blog",
    "staging": "https://staging.jamesg.blog",
    "local": os.getcwd(),
}
```

## Render Collections of Data 

You can render data from JSON files as web pages with Aurora. This is useful if you have a JSON collection of data, such as a list of coffee shop reviews, that you want to turn into posts without creating corresponding markdown files.

To create a collection, add a new file to your site's `pages/_data` directory. This file should have a `.json` extension.

Within the file, create a list that contains JSON objects, like this:

```json
[
    {"slug": "rosslyn-coffee", "layout": "coffee", "title": "Rosslyn Coffee in London is terrific."}
]
```

This file is called `pages/_data/coffee.json`.

Every entry must have a `layout` key. This corresponds with the name of the template that will be used to render the page. For example, the `coffee` layout will be rendered using the `pages/_layouts/coffee.html` template.

Every entry must also have a `slug` key. This corresponds with the name of the page that will be generated. In the case above, one file will be created in the `_site` output directory: `_site/coffee/rosslyn-coffee/index.html`.

## Build Hooks (Advanced)

You can define custom functions that are run before a file is processed by Aurora. You can use this feature to save metadata about a page that can then be consumed by a template.

These functions are called "hooks".

To define a hook, you need to:

1. Write a hook function with the right type signature, and;
2. Add the hook function to the `HOOKS` dictionary in your `config.py` file.

For example, you could define a function that saves the word count of a page:

```python
def word_count_hook(file_name: str, page_state: dict, site_state: dict):
    if "posts/" not in file_name:
        return page_state

    page_state["word_count"] = len(page_state["content"].split())
    return page_state
```

Suppose this is saved in a file called `hooks.py`.

This function would make a `page.word_count` available in the page on which it is run.

Hooks **must** return the `page_state` dictionary, otherwise the page cannot be processed correctly.

To register a hook, create an entry in the `REGISTERED_HOOKS` dictionary in your `config.py` file:

```python
REGISTERED_HOOKS = {
    "hooks": ["word_count_hook"],
}
```

Above, `hooks` corresponds to the name of the Python file with our hook, relative to the directory in which `aurora build` is run. (NB: `aurora build` should always be run in the root directory of your Aurora site.) `word_count_hook` is the name of the function we defined in `hooks.py`.

You can define as many hooks as you want.

To register multiple hooks in the same file, use the syntax:

```python
REGISTERED_HOOKS = {
    "hook_file_name": ["hook1", "hook2", "hook3"],
}
```

## Performance

In a test on a website with 1,763 files and multiple layers of inheritance, Aurora built the website in under two seconds. The files in this test were a combination of blog posts, static pages, and programmatic archives for blog posts (date pages, category pages).

In a test rendering 4,000 markdown files with a single layer of inheritance in each template, Aurora built the website in between 0.9 and 1.2 seconds.

## Users

The following sites are built with Aurora:

- [James' Coffee Blog](https://jamesg.blog) (1,500+ pages)

Have you made a website with Aurora? File a PR and add it to the list!

## License

This project is licensed under an [MIT license](LICENSE).
