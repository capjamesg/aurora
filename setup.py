import re

import setuptools
from setuptools import find_packages

with open("./aurora/__init__.py", "r") as f:
    content = f.read()
    # from https://www.py4u.net/discuss/139845
    version = re.search(r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]', content).group(1)

with open("README.md", "r", encoding="UTF-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="aurora-ssg",
    version=version,
    author="capjamesg",
    author_email="readers@jamesg.blog",
    description="A fast static site generator implemented in Python.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/capjamesg/aurora",
    install_requires=[
        "jinja2",
        "livereload",
        "toposort",
        "pyromark",
        "python-frontmatter",
        "requests",
        "progress",
        "click",
        "orjson",
        "tqdm",
        "python-dateutil",
    ],
    include_package_data=True,
    package_data={"": ["templates/index.html"]},
    packages=find_packages(exclude=("tests",)),
    entry_points={
        "console_scripts": [
            "aurora = aurora.cli:main",
        ],
    },
    extras_require={
        "dev": [
            "flake8",
            "black==24.4.2",
            "isort",
            "twine",
            "pytest",
            "wheel",
            "mkdocs-material",
            "mkdocs",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
