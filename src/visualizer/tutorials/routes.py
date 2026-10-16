"""The tutorials' three pages: the hub, a lesson, and the glossary.

Each view asks ``views.py`` what to show and hands that to a template; none of
them reads a file or decides anything. All three are public -- they hold no
one's data -- so someone can read how the app works before they have an
account.
"""

from __future__ import annotations

from flask import Flask, abort, render_template, url_for

from .catalog import LessonCatalog
from .inline import render_inline
from .lessons import term_slug
from .shots import PHONE_BELOW, shot_path
from .views import glossary_view, hub_view, lesson_view

# The endpoints that are the tutorials' own pages, and so light their tab. The
# shared sign-in pages this app also serves are not among them.
PAGES = frozenset({"index", "lesson", "glossary"})


def is_tutorial_page(endpoint: str | None) -> bool:
    return endpoint in PAGES


def register_routes(app: Flask, catalog: LessonCatalog, shots) -> None:
    defined = {term.slug for term in catalog.glossary()}

    def term_href(word: str) -> str | None:
        slug = term_slug(word)
        return f"{url_for('glossary')}#{slug}" if slug in defined else None

    @app.context_processor
    def _drawing():
        return {
            "marks": lambda text: render_inline(text, term_href),
            "shot_path": shot_path,
            "phone_below": PHONE_BELOW,
        }

    @app.get("/")
    def index():
        return render_template("tutorials/hub.html", hub=hub_view(catalog, shots))

    @app.get("/glossary")
    def glossary():
        return render_template("tutorials/glossary.html", terms=glossary_view(catalog))

    @app.get("/<slug>")
    def lesson(slug: str):
        view = lesson_view(slug, catalog, shots)
        if view is None:
            abort(404)
        return render_template("tutorials/lesson.html", view=view)

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("tutorials/not_found.html"), 404
