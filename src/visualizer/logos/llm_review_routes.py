"""LLM review on the GPU box, as JSON routes: preview, ask, follow, triage, discuss.

Every route but availability lives under the section it reviews --
``.../sections/<section>/reviews`` -- and needs write on the book, like the
other writer-only aids in ``review_routes``: a review is private feedback on
unpublished prose, not something a reader of the book is shown.

``/llm-review/availability`` is book-free: it is about the box.
"""

from flask import jsonify, request
from flask_login import current_user, login_required

from .llm_review import Reviewer
from .llm_review_service import LlmReviewService
from .routing import SECTION, authorize, json_body

REVIEWS = SECTION + "/reviews"
REVIEW = REVIEWS + "/<review_id>"
ISSUE = REVIEW + "/issues/<issue_id>"


def register_llm_review_routes(app, csrf, auth_store, reviewer: Reviewer,
                               service: LlmReviewService) -> None:
    @app.get("/llm-review/availability")
    @csrf.exempt
    @login_required
    def llm_review_availability():
        """Off, asleep, busy or ready -- from a cached health check, so asking on
        every page view costs nothing while the box sleeps."""
        return jsonify({**reviewer.availability(), "private": reviewer.private})

    @app.get(REVIEWS + "/references")
    @csrf.exempt
    @login_required
    def llm_review_references(book, volume, section):
        """What a review would send with the chapter, and what it would leave
        out and why. ``?draft=`` and repeated ``?include=`` as for a review."""
        authorize(auth_store, "write", book)
        payload = {"include": request.args.getlist("include")}
        if request.args.get("draft"):
            payload["draft"] = request.args["draft"]
        return jsonify(service.references(book, volume, section,
                                          current_user.username, payload))

    @app.post(REVIEWS)
    @csrf.exempt
    @login_required
    def submit_llm_review(book, volume, section):
        authorize(auth_store, "write", book)
        review = service.submit(book, volume, section, current_user.username,
                                json_body())
        return jsonify(review), 202

    @app.get(REVIEWS)
    @csrf.exempt
    @login_required
    def list_llm_reviews(book, volume, section):
        authorize(auth_store, "write", book)
        return jsonify({"reviews": service.recent(book, volume, section,
                                                  current_user.username)})

    @app.get(REVIEW)
    @csrf.exempt
    @login_required
    def get_llm_review(book, volume, section, review_id):
        """Poll this: it asks the box how the review is going, and stores the
        issues the first time it finds it done."""
        authorize(auth_store, "write", book)
        return jsonify(service.refresh(book, volume, section, review_id,
                                       current_user.username))

    @app.delete(REVIEW)
    @csrf.exempt
    @login_required
    def cancel_llm_review(book, volume, section, review_id):
        authorize(auth_store, "write", book)
        return jsonify(service.cancel(book, volume, section, review_id,
                                      current_user.username))

    @app.get(ISSUE)
    @csrf.exempt
    @login_required
    def get_llm_review_issue(book, volume, section, review_id, issue_id):
        """Poll this while the editor replies: it asks the box, and adds the
        reply to the discussion the first time it finds it done."""
        authorize(auth_store, "write", book)
        return jsonify(service.issue(book, volume, section, review_id, issue_id,
                                     current_user.username))

    @app.post(ISSUE + "/messages")
    @csrf.exempt
    @login_required
    def discuss_llm_review_issue(book, volume, section, review_id, issue_id):
        authorize(auth_store, "write", book)
        issue = service.discuss(book, volume, section, review_id, issue_id,
                                current_user.username, json_body())
        return jsonify(issue), 202

    @app.put(ISSUE)
    @csrf.exempt
    @login_required
    def set_llm_review_issue(book, volume, section, review_id, issue_id):
        authorize(auth_store, "write", book)
        return jsonify(service.set_status(book, volume, section, review_id, issue_id,
                                          current_user.username, json_body()))
