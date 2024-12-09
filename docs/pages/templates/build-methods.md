---
title: Build Methods
permalink: /build-methods/
layout: default
---

There are three ways you can build your Aurora site:

1. Full build
2. Incremental build
3. Interactive, incremental build

## Full Build

A full build generates your entire website.

Your site is saved in `_site`, ready for serving.

To build your site, navigate to the root directory of your project (the folder with the `config.py` file in it), and run:

<pre><code class="language-bash">aurora build</code></pre>

Your site will be saved in and ready to serve from the `_site` directory.

## Incremental Build

An incremental build generates only the files that have changed since the last build. This is faster than a full build.

If you have not fully built your site before, the incremental build will fully build your site first. Then, subsequent runs will only build the files that have changed since the last build.

For example, suppose you have 1,000 pages on your site. You have already built your site, and now you change one file. With the incremental build, option, only the page you changed -- and its dependencies -- will be regenerated.

Incremental builds are designed to speed up the build process, particularly for large sites with thousands or tens of thousands of pages.

To run an incremental build, navigate to the root directory of your project and run:

<pre><code class="language-bash">aurora build --incremental</code></pre>

<p class="callout-tip"><b>Tip</b>: Incremental builds support CSV and JSON data files.</p>

## Interactive, Incremental Build

An interactive, incremental build generates your full site. It starts a web server through which you can preview pages. When you make a change to any file, the changed file -- and its dependencies -- are re-built and made available over the server. Any open browser tabs that are viewing the site will automatically refresh to show the changes.

This mode is intended for development. With interactive, incremental building, you can see changes to your site as you make them, without having to wait for your full site to build, and without having to manually refresh your browser.

To run an interactive, incremental build, navigate to the root directory of your project and run:

<pre><code class="language-bash">aurora serve</code></pre>

A server will start on `http://localhost:8000`. Open this URL in your browser to view your site.

<p class="callout-note"><b>Note</b>: The interactive server should not be used in production.</p>
