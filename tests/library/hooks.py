def retrieve_visitor_count(file_name, page_state, _):
    page_state["visitors"] = 100

    return page_state


def add_made_by_file(state):
    with open("_site/made-by.txt", "w") as f:
        f.write("Made by the library team.")

    return state


def capitalize(text):
    return text.upper()
