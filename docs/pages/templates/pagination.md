---
title: Pagination
layout: default
permalink: /pagination/
---

# Pagination

You can generate pagination pages for collections.

This is ideal if you have a collection with many items that you want to split into multiple pages for ease of navigation.

## Usage

To set up pagination, first [create a collection](/collections/).

Then, create a new layout in your `_layouts` directory. This layout will be used to generate the pagination pages.

This page can access the `page.___` variable, where `___` is the name of the collection (i.e. `page.books` would reference the `page.books` collection). This variable is an array of all the items in a given page in the collection.

To see the current page number, reference the `page.page_number` variable.

Finally, add a `paginators` key to the `SITE_STATE` value in your `config.py` file:

<pre><code class="language-python">SITE_STATE = {
    "paginators": {
        "books": {
            "per_page": 10,
            "template": "books"
        }
    }
}</code></pre>