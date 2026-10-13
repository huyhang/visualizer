"""Research on the GPU box: what the "Research…" button asks before drawing itself.

Only availability so far. Submitting, polling and the research inbox build on
the same ``Researcher`` once the import side exists.
"""

from flask import Flask, jsonify
from flask_login import login_required

from .research import Researcher


def register_research_routes(app: Flask, researcher: Researcher, csrf) -> None:
    @app.get("/research/availability")
    @csrf.exempt
    @login_required
    def research_availability():
        """Off, asleep, busy or ready -- answered from a cached health check, so
        calling it on every page view costs nothing while the box sleeps."""
        return jsonify({**researcher.availability(), "private": researcher.private})
