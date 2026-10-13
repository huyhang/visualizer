"""LLM review on the GPU box: Logos asks, the box reads, the writer decides.

``Reviewer`` is the seam, shaped like Akasha's ``Researcher`` and injected into
the app factory; the default keeps the NAS-only stack exactly as it was. Logos
never talks to a model. It sends the GPU-box worker one draft of one chapter
as plain-text blocks, with the Akasha articles that chapter depends on, and
stores what comes back -- issues anchored to a block and a verbatim quote --
for the writer to work through. The worker's contract is ``docs/gpu_worker/``.

Which articles go with the chapter is decided here, in ``assemble_references``,
because it is a decision about the writer's world, not about the model:

- **deviations** (every article in the book world's ``deviations``
  collection) go first: the writer saying "this is on purpose", which the box
  must never report against, so they are never the ones cut;
- the **anachronism watchlist** (the world's ``watchlist`` collection);
- the articles the chapter **mentions or links**, in reading order, then any
  the writer adds: ``research`` ones only once ``status: verified`` -- an
  unchecked AI draft must never become the standard prose is held to --
  and never anything from ``research-inbox`` or ``sources``;
- only what the writer asking may read, and at most what the box reads:
  ``MAX_REFERENCES`` references of ``REFERENCE_CHARS`` characters each.

Everything left out is reported with its reason, so the writer can see what
the review did not know.
"""

import re
from typing import Protocol

from visualizer.akasha.labels import derive_title
from visualizer.gpubox import WorkerBusy, WorkerError, WorkerJobNotFound, availability

from .errors import (
    InvalidReviewRequest,
    LlmReviewBusy,
    LlmReviewNotFound,
    LlmReviewUnavailable,
)
from .validation import validate_identifier

CHECKS = ("continuity", "anachronism", "prose")
VERIFY = ("auto", "required", "off")
DIALECTS = ("en-US", "en-GB")
# The box reads this many references, each cut to this length (gpu_worker/review.py).
MAX_REFERENCES = 40
REFERENCE_CHARS = 1500
MAX_INCLUDED = 20
DEVIATIONS = "deviations"
WATCHLIST = "watchlist"
RESEARCH = "research"
NEVER_SENT = {"research-inbox": "unreviewed_research", "sources": "source"}
# Bookkeeping fields of research articles: provenance, not facts. Dropped and
# partial facts especially must not reach the box as if they were reference.
_NOT_FACTS = {"status", "sources", "research_job", "generated_by", "generated_at",
              "verified_by", "verified_at", "drafted_by", "question", "verification",
              "dropped_facts", "partial_facts", "kind", "url", "excerpts"}
_REF = re.compile(r"^[^/\s]+/[^/\s]+/[^/\s]+$")
_FIELDS = {"draft", "checks", "dialect", "verify", "include"}


def parse_ref(value) -> dict:
    if not isinstance(value, str) or not _REF.match(value):
        raise InvalidReviewRequest(
            f"Not an article ref (database/collection/id): {value!r}.")
    database, collection, article = value.split("/")
    return {"database": database, "collection": collection, "id": article}


def ref_string(ref: dict) -> str:
    return f"{ref['database']}/{ref['collection']}/{ref['id']}"


def validate_review_request(payload) -> dict:
    """A writer's review request, checked, with defaults filled in."""
    payload = {} if payload is None else payload
    if not isinstance(payload, dict):
        raise InvalidReviewRequest("A review request must be a JSON object.")
    unknown = sorted(set(payload) - _FIELDS)
    if unknown:
        raise InvalidReviewRequest(f"Unknown fields: {', '.join(unknown)}.")
    draft = payload.get("draft")
    if draft is not None:
        draft = validate_identifier(draft, "draft")
    checks = payload.get("checks", list(CHECKS))
    if (not isinstance(checks, list) or not checks or len(set(checks)) != len(checks)
            or not all(check in CHECKS for check in checks)):
        raise InvalidReviewRequest(f"checks must be some of {', '.join(CHECKS)}.")
    dialect = payload.get("dialect", "en-US")
    if dialect not in DIALECTS:
        raise InvalidReviewRequest("dialect must be en-US or en-GB.")
    verify = payload.get("verify", "auto")
    if verify not in VERIFY:
        raise InvalidReviewRequest("verify must be auto, required or off.")
    include = payload.get("include", [])
    if not isinstance(include, list) or len(include) > MAX_INCLUDED:
        raise InvalidReviewRequest(
            f"include must be a list of at most {MAX_INCLUDED} article refs.")
    return {"draft": draft, "checks": checks, "dialect": dialect, "verify": verify,
            "include": [parse_ref(ref) for ref in dict.fromkeys(include)]}


def reference_text(document: dict) -> str:
    """An article as the box reads it: its facts as "Field: value", then its body."""
    lines = []
    for key, value in document.items():
        if key in ("title", "body") or key in _NOT_FACTS or key.startswith("_"):
            continue
        if isinstance(value, bool) or not isinstance(value, (str, int, float, list)):
            continue
        if isinstance(value, list):
            if not value or not all(isinstance(v, (str, int, float)) for v in value):
                continue
            value = ", ".join(str(v) for v in value)
        if str(value).strip():
            lines.append(f"{derive_title(key)}: {value}")
    body = document.get("body")
    if isinstance(body, str) and body.strip():
        lines.append(body.strip())
    return "\n".join(lines)[:REFERENCE_CHARS]


def assemble_references(articles, grants: list[dict], world: str | None,
                        mentioned: list[dict], included: list[dict]):
    """(references to send, refs left out with why), in the order described above."""
    wanted: list[tuple[str, dict]] = []
    skipped: list[dict] = []
    if world:
        for collection, kind in ((DEVIATIONS, "deviation"), (WATCHLIST, "watchlist")):
            wanted += [(kind, ref) for ref in
                       articles.collection_refs(world, collection, grants)]
    queued = {ref_string(ref) for _, ref in wanted}
    for ref in mentioned + included:
        name = ref_string(ref)
        if name in queued:
            continue
        queued.add(name)
        if ref["collection"] in NEVER_SENT:
            skipped.append({"ref": name, "reason": NEVER_SENT[ref["collection"]]})
            continue
        wanted.append(("research" if ref["collection"] == RESEARCH else "canon", ref))

    found = articles.review_articles([ref for _, ref in wanted], grants)
    sent = []
    for kind, ref in wanted:
        name = ref_string(ref)
        article = found.get((ref["database"], ref["collection"], ref["id"]))
        if article is None or not _REF.match(name):
            # Missing and unreadable are one reason: which it is is not ours to say.
            skipped.append({"ref": name, "reason": "unavailable"})
        elif kind == "research" and article["document"].get("status") != "verified":
            skipped.append({"ref": name, "reason": "unverified"})
        elif len(sent) >= MAX_REFERENCES:
            skipped.append({"ref": name, "reason": "over_limit"})
        else:
            sent.append({"ref": name, "kind": kind, "title": article["title"][:300],
                         "text": reference_text(article["document"])})
    return sent, skipped


class Reviewer(Protocol):
    """Runs LLM reviews somewhere else and reports on them; never edits prose."""

    # True only when the models run on hardware the writer controls.
    private: bool

    def availability(self) -> dict:
        """Whether a review can be requested right now, and what to tell the writer."""

    def submit(self, request: dict, ref: str) -> dict:
        """Queue a review job; ``ref`` is Logos's own review id. Returns the job."""

    def status(self, job_id: str) -> dict:
        """The job as it stands: queued, running (with its stage), or finished."""

    def cancel(self, job_id: str) -> dict:
        """Stop a queued or running job. Finished jobs come back unchanged."""


class UnavailableReviewer:
    """The default: no GPU box, so LLM review is off and says so."""

    private = True

    def availability(self) -> dict:
        return availability(None, "review")

    def submit(self, request: dict, ref: str) -> dict:
        raise self._off()

    def status(self, job_id: str) -> dict:
        raise self._off()

    def cancel(self, job_id: str) -> dict:
        raise self._off()

    @staticmethod
    def _off() -> LlmReviewUnavailable:
        return LlmReviewUnavailable("LLM review is off: no GPU box is configured.")


class RemoteReviewer:
    """LLM review on the GPU-box worker, through the stack's shared client.

    ``worker`` is a ``visualizer.gpubox.WorkerClient`` in production, or its
    ``FakeWorker`` in tests and on the dev server.
    """

    private = True  # the worker's models run on our own hardware

    def __init__(self, worker):
        self.worker = worker

    def availability(self) -> dict:
        return availability(self.worker, "review")

    def submit(self, request: dict, ref: str) -> dict:
        return self._ask(self.worker.submit, "review", request, service="logos",
                         ref=ref)

    def status(self, job_id: str) -> dict:
        return self._ask(self.worker.status, job_id)

    def cancel(self, job_id: str) -> dict:
        return self._ask(self.worker.cancel, job_id)

    @staticmethod
    def _ask(call, *args, **kwargs):
        """One worker call, its failures restated in Logos's own errors."""
        try:
            return call(*args, **kwargs)
        except WorkerBusy as err:
            raise LlmReviewBusy(err.message, retry_after=err.retry_after) from err
        except WorkerJobNotFound as err:
            raise LlmReviewNotFound(err.message) from err
        except WorkerError as err:
            # Asleep, a dependency down, or a request the box refused: to the
            # writer all mean "not right now"; availability says which.
            raise LlmReviewUnavailable(err.message) from err
