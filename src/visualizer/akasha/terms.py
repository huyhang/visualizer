"""What the screen calls the store's three levels.

The API, the URLs and the payloads speak MongoDB -- ``database`` ->
``collection`` -> ``document`` -- and always will. Those names are not
decoration, they are the addressing scheme: the same triple keys every grant,
every wikilink (``[[db/col/id]]``) and every chronos ``EntityRef``. Renaming
them would be a migration with nothing to show for it.

The *screen*, though, is read by a novelist, who has a world with categories of
articles in it. This module is the seam between the two vocabularies, so
changing what the UI calls things is one edit here rather than a hunt through
every view.

``static/js/terms.js`` carries the same table for the browser, and
``tests/akasha/test_terms.py`` keeps the two from drifting apart.

Deliberately *not* applied to the admin console: it manages grants against the
API's scopes, so the API's words are the ones that make it legible.
"""

TERMS = {
    "database": {
        "one": "world",
        "many": "worlds",
        "One": "World",
        "Many": "Worlds",
    },
    "collection": {
        "one": "category",
        "many": "categories",
        "One": "Category",
        "Many": "Categories",
    },
    "document": {
        "one": "article",
        "many": "articles",
        "One": "Article",
        "Many": "Articles",
    },
}
