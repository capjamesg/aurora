---
title: Templating with Jinja2
layout: default
permalink: /templating/
---

# Templating with Jinja2

Aurora supports using [jinja2](https://jinja.palletsprojects.com/en/3.1.x/) to create template logic.

jinja2 is a popular Python templating engine with support for variable interpolation, conditionals, loops, and more.

You can use jinja2 in any HTML or markdown document in your Aurora project.

Here is an example of a Jinja2 template that defines a blog home page:

```html
---
title: Blog
layout: default
permalink: /blog/
---

<h1>Blog</h1>

{% for post in site.posts %}
    <h2>{{ post.title }}</h2>
    <p>{{ post.content }}</p>
{% endfor %}
```
