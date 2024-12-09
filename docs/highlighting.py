from pygments import highlight
from pygments.lexers import PythonLexer, HtmlLexer, CssLexer
from pygments.formatters import HtmlFormatter
from bs4 import BeautifulSoup

languages = {
    "python": PythonLexer(),
    "html": HtmlLexer(),
    "text": HtmlLexer(),
    "css": CssLexer()
}

def highlight_code(file_name, page_state, _, page_contents):
    if ".txt" in file_name or ".xml" in file_name or "styles.html" in file_name:
        return page_contents
        
    soup = BeautifulSoup(page_contents, 'lxml')

    for pre in soup.find_all('pre'):
        code = pre.find('code')
        try:
            language = code['class'][0].split("language-")[1]
            code = highlight(code.text, languages[language], HtmlFormatter())
        except:
            continue
        
        pre.replace_with(BeautifulSoup(code, 'html.parser'))

    if soup.find('article', {'class': 'post'}):
        # add id to all h2s, h3s, etc.
        for h2 in soup.find_all(['h2', 'h3', 'h4', 'h5', 'h6']):
            h2['id'] = h2.text.lower().replace(" ", "-")

        # surround h2 with a link
        for h2 in soup.find_all(['h2', 'h3', 'h4', 'h5', 'h6']):
            link = soup.new_tag('a', href=f"#{h2['id']}")
            link.string = h2.text  # Set the link text to the h2's current text
            h2.clear()
            h2.append(link)

    # for each "sup", add class=f-1
    for i, sup in enumerate(soup.find_all('sup')):
        sup['id'] = f"f-{i+1}"

    # get all footnote-definition and add [↩] link to end
    for footnote in soup.find_all('div', {'class': 'footnote-definition'}):
        link = soup.new_tag('a', href=f"#f-{footnote['id']}")
        link.string = "[↩]"
        footnote.append(link)

    css = HtmlFormatter().get_style_defs('.highlight')
    css = f"<style>{css}</style>"

    # this happens for bookmarks
    if not soup.find("body"):
        return ""
    
    body = soup.find('body')
    body.insert(0, BeautifulSoup(css, 'html.parser'))

    return str(soup)


def generate_table_of_contents(file_name, page_state, site_state):
    page = BeautifulSoup(page_state["page"].contents, 'html.parser')
    h2s = page.find_all('h2')
    toc = []
    for h2 in h2s:
        toc.append({
            "text": h2.text,
            "id": h2.text.lower().replace(" ", "-"),
            "children": []
        })
        h3s = h2.find_next_siblings('h3')
        for h3 in h3s:
            # if h3 is a child of another h3, skip it
            if h3.find_previous_sibling('h2') != h2:
                continue
            toc[-1]["children"].append({
                "text": h3.text,
                "id": h3.text.lower().replace(" ", "-"),
            })
    page_state["page"].toc = toc

    return page_state