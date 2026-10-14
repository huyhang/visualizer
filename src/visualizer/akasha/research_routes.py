"""Research on the GPU box, as JSON routes: ask, follow, review, import images.

Everything lives under the world it is about --
``/databases/<world>/research/...`` -- and is authorised against that world's
``research-inbox``, so a writer who may work in a world may research for it:

- asking, approving a job's search plan, refining a draft, and importing an
  image into a draft: write on the inbox;
- following jobs and reading the inbox: read on the inbox;
- accepting a draft: write on the inbox, and on ``research`` and ``sources``,
  where accepting puts things;
- rejecting a draft, or closing one as done: write on the inbox;
- saving a note composed from drafts: write on the inbox and on ``sources``,
  and create on ``research`` for a new note or write on the note updated.

``/research/availability`` is world-free: it is about the box, not a world.
"""

from flask import Flask, Response, jsonify, request
from flask_login import current_user, login_required

from .access import authorize
from .errors import InvalidResearchRequest
from .media_routes import present_media
from .research import Researcher
from .research_import import INBOX, RESEARCH, SOURCES
from .research_service import ResearchService

_BASE = "/databases/<database>/research"
_DRAFT = _BASE + "/inbox/<draft>"


def register_research_routes(app: Flask, researcher: Researcher,
                             service: ResearchService, auth_store, csrf) -> None:
    @app.get("/research/availability")
    @csrf.exempt
    @login_required
    def research_availability():
        """Off, asleep, busy or ready -- answered from a cached health check, so
        calling it on every page view costs nothing while the box sleeps."""
        return jsonify({**researcher.availability(), "private": researcher.private})

    # -- jobs ------------------------------------------------------------------

    @app.post(_BASE + "/jobs")
    @csrf.exempt
    @login_required
    def submit_research(database):
        authorize(auth_store, "POST", database, INBOX)
        job = service.submit(database, current_user.username,
                             request.get_json(silent=True))
        return jsonify(job), 202

    @app.get(_BASE + "/jobs")
    @csrf.exempt
    @login_required
    def list_research_jobs(database):
        authorize(auth_store, "GET", database, INBOX)
        limit = request.args.get("limit", type=int)
        if "limit" in request.args and limit is None:
            raise InvalidResearchRequest("limit must be a whole number.")
        return jsonify({"jobs": service.recent(database, limit)})

    @app.get(_BASE + "/jobs/<job_id>")
    @csrf.exempt
    @login_required
    def get_research_job(database, job_id):
        """Poll this: it asks the box how the job is going, and imports the
        result into the inbox the first time it finds it done."""
        authorize(auth_store, "GET", database, INBOX)
        return jsonify(service.refresh(database, job_id))

    @app.post(_BASE + "/jobs/<job_id>/plan")
    @csrf.exempt
    @login_required
    def approve_research_plan(database, job_id):
        """Let a job asked with ``approve_plan`` go on, with its search queries
        as proposed or edited. To turn the plan down, cancel the job."""
        authorize(auth_store, "POST", database, INBOX)
        return jsonify(service.approve_plan(database, job_id,
                                            request.get_json(silent=True)))

    @app.delete(_BASE + "/jobs/<job_id>")
    @csrf.exempt
    @login_required
    def cancel_research_job(database, job_id):
        authorize(auth_store, "PUT", database, INBOX)
        return jsonify(service.cancel(database, job_id))

    # -- the inbox -------------------------------------------------------------

    @app.get(_BASE + "/inbox")
    @csrf.exempt
    @login_required
    def research_inbox(database):
        authorize(auth_store, "GET", database, INBOX)
        return jsonify({"drafts": service.inbox(database)})

    @app.get(_DRAFT)
    @csrf.exempt
    @login_required
    def research_draft(database, draft):
        authorize(auth_store, "GET", database, INBOX, draft)
        return jsonify(service.draft(database, draft))

    @app.post(_DRAFT + "/accept")
    @csrf.exempt
    @login_required
    def accept_research_draft(database, draft):
        authorize(auth_store, "PUT", database, INBOX, draft)
        authorize(auth_store, "POST", database, RESEARCH)
        authorize(auth_store, "POST", database, SOURCES)
        return jsonify(service.accept(database, draft, current_user.username))

    @app.post(_DRAFT + "/refine")
    @csrf.exempt
    @login_required
    def refine_research_draft(database, draft):
        """Research the draft again with feedback; the result replaces it."""
        authorize(auth_store, "PUT", database, INBOX, draft)
        job = service.refine(database, draft, current_user.username,
                             request.get_json(silent=True))
        return jsonify(job), 202

    @app.post(_DRAFT + "/reject")
    @csrf.exempt
    @login_required
    def reject_research_draft(database, draft):
        authorize(auth_store, "PUT", database, INBOX, draft)
        service.reject(database, draft, current_user.username)
        return "", 204

    @app.post(_DRAFT + "/done")
    @csrf.exempt
    @login_required
    def close_research_draft(database, draft):
        """The writer has taken what they wanted from this draft into notes."""
        authorize(auth_store, "PUT", database, INBOX, draft)
        service.done(database, draft, current_user.username)
        return "", 204

    # -- notes -----------------------------------------------------------------

    @app.post(_BASE + "/notes")
    @csrf.exempt
    @login_required
    def save_research_note(database):
        """A note composed from drafts: a new one, or an update of one."""
        payload = request.get_json(silent=True)
        target = payload.get("note") if isinstance(payload, dict) else None
        authorize(auth_store, "PUT", database, INBOX)
        authorize(auth_store, "POST", database, SOURCES)
        if isinstance(target, str):
            authorize(auth_store, "PUT", database, RESEARCH, target)
        else:
            authorize(auth_store, "POST", database, RESEARCH)
        saved = service.save_note(database, current_user.username, payload)
        return jsonify(saved), 200 if isinstance(target, str) else 201

    # -- image candidates ------------------------------------------------------

    @app.get(_DRAFT + "/images/<int:index>")
    @csrf.exempt
    @login_required
    def research_draft_image(database, draft, index):
        """The candidate's bytes, fetched by the box: ``?size=preview`` (the
        default, at most 360 px) to look at, ``?size=full`` for the original."""
        authorize(auth_store, "GET", database, INBOX, draft)
        size = request.args.get("size", "preview")
        if size not in ("preview", "full"):
            raise InvalidResearchRequest("size must be preview or full.")
        data, content_type = service.image(database, draft, index, size)
        response = Response(data, mimetype=content_type)
        # Candidates don't change; the box fetches each from the web once a day.
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response

    @app.post(_DRAFT + "/images/<int:index>/import")
    @csrf.exempt
    @login_required
    def import_research_image(database, draft, index):
        authorize(auth_store, "PUT", database, INBOX, draft)
        record = service.import_image(database, draft, index, current_user.username)
        # Shown exactly as the media library shows its own uploads.
        return jsonify(present_media(record, database, can_manage=True)), 201
