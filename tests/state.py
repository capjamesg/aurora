import os
import shutil

TEST_FOLDER = os.path.join(os.getcwd(), "tests/library")
BASE_SITE_DIRECTORY = os.path.join(TEST_FOLDER, "_site")
FIXTURES_DIRECTORY = os.path.join(os.getcwd(), "tests/fixtures")

os.chdir(TEST_FOLDER)

fixtures = {}

for file in os.listdir(FIXTURES_DIRECTORY):
    with open(os.path.join(FIXTURES_DIRECTORY, file)) as f:
        fixtures[file] = f.read()

from aurora.graph import main as build_site


def test_build_site():
    build_site()
    assert os.path.exists("_site")


def test_config_file_presence():
    assert os.path.exists("config.py")


def test_rendered_page_from_data_file():
    with open(
        os.path.join(BASE_SITE_DIRECTORY, "books/the-great-gatsby/index.html")
    ) as f:
        data = f.read()

    assert data.strip() == fixtures["book.html"].strip()


def test_rendered_page_from_data_file_without_slug():
    with open(os.path.join(BASE_SITE_DIRECTORY, "reviews/0/index.html")) as f:
        data = f.read()

    assert data.strip() == fixtures["review.html"].strip()


def test_rendered_page_from_template():
    # also tests title interpolation
    with open(os.path.join(BASE_SITE_DIRECTORY, "index.html")) as f:
        data = f.read()

    assert data.strip() == fixtures["index.html"].strip()


def test_permalink_front_matter():
    assert os.path.exists(os.path.join(BASE_SITE_DIRECTORY, "books/index.html"))


def test_rendered_page_with_logic():
    # this also tests:
    # - inheritance working (inheriting from `default`)
    # - title interpolation working
    with open(os.path.join(BASE_SITE_DIRECTORY, "books/index.html")) as f:
        data = f.read()

    assert data.replace(" ", "").replace("\n", "") == fixtures[
        "book_list.html"
    ].replace(" ", "").replace("\n", "")


def test_asset_copying():
    with open(os.path.join(BASE_SITE_DIRECTORY, "assets/styles.css")) as f:
        data = f.read()

    assert data.strip() == fixtures["styles.css"].strip()


def test_asset_copying_in_folders():
    with open(os.path.join(BASE_SITE_DIRECTORY, "assets/meta/robots.txt")) as f:
        data = f.read()

    assert data.strip() == fixtures["robots.txt"].strip()


def test_generate_blog_post():
    with open(
        os.path.join(BASE_SITE_DIRECTORY, "2024/01/01/first-post/index.html")
    ) as f:
        data = f.read()

    assert data.strip() == fixtures["post.html"].strip()


def test_new_site_generation():
    os.system("aurora new test-site")
    assert os.path.exists("test-site")
    assert os.path.exists("test-site/assets")
    assert os.path.exists("test-site/pages")
    assert os.path.exists("test-site/pages/_layouts")
    assert os.path.exists("test-site/pages/_data")
    assert os.path.exists("test-site/pages/posts")
    assert os.path.exists("test-site/pages/templates/index.html")

    with open("test-site/config.py") as f:
        data = f.read()

    assert data.strip() == fixtures["new_site_config.py"].strip()

    shutil.rmtree("test-site")


def test_pre_generation_hook():
    # this page uses {{ page.visitors }}, which is computed in a pre-generation hook
    with open(os.path.join(BASE_SITE_DIRECTORY, "about/index.html")) as f:
        data = f.read()

    assert data.strip() == fixtures["about.html"].strip()


def test_post_build_hook():
    # check for presence of site/made-by.txt
    assert os.path.exists(os.path.join(BASE_SITE_DIRECTORY, "made-by.txt"))


def test_year_date_archive_generation():
    with open(os.path.join(BASE_SITE_DIRECTORY, "2024/index.html")) as f:
        data = f.read()

    assert data.strip().replace(" ", "").replace("\n", "") == fixtures[
        "date_archive.html"
    ].strip().replace(" ", "").replace("\n", "")

def test_year_month_date_archive_generation():
    with open(os.path.join(BASE_SITE_DIRECTORY, "2024/01/01/index.html")) as f:
        data = f.read()

    assert data.strip().replace(" ", "").replace("\n", "") == fixtures[
        "date_archive.html"
    ].strip().replace(" ", "").replace("\n", "")
    
def test_year_month_daydate_archive_generation():
    with open(os.path.join(BASE_SITE_DIRECTORY, "2024/01/01/index.html")) as f:
        data = f.read()

    assert data.strip().replace(" ", "").replace("\n", "") == fixtures[
        "date_archive.html"
    ].strip().replace(" ", "").replace("\n", "")

def test_tag_archive_generation():
    with open(os.path.join(BASE_SITE_DIRECTORY, "tag/announcements/index.html")) as f:
        data = f.read()

    assert data.strip().replace(" ", "").replace("\n", "") == fixtures[
        "tag_archive.html"
    ].strip().replace(" ", "").replace("\n", "")

def test_collection_pagination():
    with open(os.path.join(BASE_SITE_DIRECTORY, "rooms/index.html")) as f:
        data = f.read()

    assert data.strip().replace(" ", "").replace("\n", "") == fixtures[
        "collection_pagination.html"
    ].strip().replace(" ", "").replace("\n", "")

def check_for_presence_of_state_file_after_build():
    assert os.path.exists("state.json")

def test_incremental_regeneration():
    generated_files = os.listdir("_site")

    os.system("aurora build --incremental")

    new_generated_files = os.listdir("_site")

    assert set(generated_files) == set(new_generated_files)