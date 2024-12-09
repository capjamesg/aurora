---
title: Date, Category, and Tag Archives
layout: default
permalink: /archives/
---

Aurora has support built-in for generating date, category, and tag archives. These are useful for blogs.

## Date Archives

Aurora automatically generates date archives for blog posts. You do not need to configure any setting to use this feature.

Date archives are generated as follows:

- `https://example.com/2024/`: All posts published in 2024.
- `https://example.com/2024/01/`: All posts published in January 2024.
- `https://example.com/2024/01/01/`: All posts published on January 1, 2024.

## Category and Tag Archives

Aurora automatically generates category and tag archives.

These archives are generated if you specify `category` and/or `tag` attributes in your blog post front matters.

Category archives are generated as follows:

- `https://example.com/category/<name>`: All posts with the specified category.

Tag archives are generated as follows:

- `https://example.com/tag/<name>`: All posts with the specified tag.

### Customize Category and Tag Paths

You can change the default category and tag path roots.

To do so, update the `SITE_STATE` value in your config.py configuration to include:

<pre><code class="language-python">SITE_STATE = {
    "category_slug_root": "categories",
    "tag_slug_root": "tags",
}</code></pre>

The above example would change the category and tag paths to:

- `https://example.com/categories/<name>`: All posts with the specified category.
- `https://example.com/tags/<name>`: All posts with the specified tag.