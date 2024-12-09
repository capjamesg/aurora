---
title: Data Collections
permalink: /collections/
layout: default
---

Data collections are groups of data on a website.

You can use collections to create lists of content items (i.e. all of the bookmarks on your website).

You can create a data collection by:

1. Loading data from a JSON file
2. Loading data from a CSV file
3. Specifying a `collections` value on any page on your website

<h2>Create a Collection</h2>
<h3>JSON</h3>
<p>
    To create a collection from a JSON file, add a new file to your site&#39;s
    <code>pages/_data</code> directory. This file should have a
    <code>.json</code> extension.
</p>
<p>Within the file, create a list that contains JSON objects, like this:</p>
<pre><code class="language-python">[
    {
        "slug": "rosslyn-coffee",
        "layout": "coffee",
        "title": "Rosslyn Coffee in London is terrific."
    }
]
</code></pre>
<p>
    This file is called
    <code>pages/_data/coffee.json</code>.
</p>
<p>
    Every entry <b>must</b> have a <code>layout</code> key. This corresponds
    with the name of the template that will be used to render the page. For
    example, the <code>coffee</code> layout will be rendered using the
    <code>pages/_layouts/coffee.html</code> template.
</p>
<p>
    Every entry <b>must</b> also have a <code>slug</code> key. This corresponds
    with the name of the page that will be generated. In the case above, one
    file will be created in the <code>_site</code> output directory:
    <code>_site/coffee/rosslyn-coffee/index.html</code>.
</p>
<h3>CSV</h3>
<p>
    To create a collection from a CSV file, add a new file to your site&#39;s
    <code>pages/_data</code> directory. This file should have a
    <code>.csv</code> extension.
</p>
<p>Here is an example CSV file:</p>
<pre><code class="language-python">slug,layout,title
rosslyn-coffee,coffee,Rosslyn Coffee in London is terrific.
</code></pre>
<p class="callout">
    Your CSV file must have a header row that contains the keys for each entry.
</p>
<p>
    This file is called
    <code>pages/_data/coffee.csv</code>.
</p>
<p>
    Every entry <b>must</b> have a <code>layout</code> key. This corresponds
    with the name of the template that will be used to render the page. For
    example, the <code>coffee</code> layout will be rendered using the
    <code>pages/_layouts/coffee.html</code> template.
</p>
<p>
    Every entry <b>must</b> also have a <code>slug</code> key. This corresponds
    with the name of the page that will be generated. In the case above, one
    file will be created in the <code>_site</code> output directory:
    <code>_site/coffee/rosslyn-coffee/index.html</code>.
</p>

# Specify a Collections Attribute

If you want to group multiple existing files together, you can specify a `collections` attribute on any page on your website.

To do so, use the following syntax:

<pre><code class="language-python">---
title: My Page
collections: coffee
---</code></pre>

You can then access the collection like so:

<pre><code class="language-python">{% raw %}{% for item in coffee %}{% endraw %}
    {{ item.title }}
{% raw %}{% endfor %}{% endraw %}</code></pre>
