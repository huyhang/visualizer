"""Delegated research: Akasha asks, the GPU box researches, Akasha decides.

``Researcher`` is the seam, shaped like Logos's ``WritingAdvisor``: injected
into the app factory, with a default that keeps the NAS-only stack exactly as
it was. Akasha never fetches a web page and never talks to a model; it submits
a question to the worker on the GPU box and, later, imports what comes back
into a research inbox as unverified drafts -- nothing becomes canon without the
writer accepting it.

This module is the seam and the request rules; ``research_service`` builds the
jobs and the inbox on it. The worker's contract is ``docs/gpu_worker/``.
"""

import re
from typing import Protocol

from visualizer.gpubox import (
    WorkerBusy,
    WorkerError,
    WorkerImageUnavailable,
    WorkerJobNotFound,
    WorkerNotAwaitingApproval,
    availability,
)

from .errors import (
    InvalidResearchRequest,
    ResearchBusy,
    ResearchConflict,
    ResearchImageUnavailable,
    ResearchJobNotFound,
    ResearchUnavailable,
)

_LANGUAGE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
_FIELDS = {"question", "languages", "max_sources", "include_images", "verify",
           "approve_plan"}
MAX_QUERIES = 6
MAX_FEEDBACK = 2000
MAX_EXCLUDED = 50


def validate_request(payload) -> dict:
    """A writer's research request, checked and with defaults filled in.

    The same rules the worker's contract sets, so a bad request is refused here
    with a clear message rather than travelling to the box to be refused there.
    ``known_articles`` is not the writer's to send: Akasha adds it.
    """
    if not isinstance(payload, dict):
        raise InvalidResearchRequest("A research request must be a JSON object.")
    unknown = sorted(set(payload) - _FIELDS)
    if unknown:
        raise InvalidResearchRequest(f"Unknown fields: {', '.join(unknown)}.")
    question = payload.get("question")
    if not isinstance(question, str) or not 3 <= len(question.strip()) <= 500:
        raise InvalidResearchRequest("The question must be 3-500 characters.")
    languages = payload.get("languages", ["en"])
    if (not isinstance(languages, list) or not 1 <= len(languages) <= 5
            or len(set(languages)) != len(languages)
            or not all(isinstance(lang, str) and _LANGUAGE.match(lang)
                       for lang in languages)):
        raise InvalidResearchRequest(
            "languages must be 1-5 language codes, such as [\"en\", \"zh\"].")
    max_sources = payload.get("max_sources", 8)
    if not isinstance(max_sources, int) or isinstance(max_sources, bool) \
            or not 1 <= max_sources <= 15:
        raise InvalidResearchRequest("max_sources must be a whole number from 1 to 15.")
    include_images = payload.get("include_images", False)
    if not isinstance(include_images, bool):
        raise InvalidResearchRequest("include_images must be true or false.")
    verify = payload.get("verify", "auto")
    if verify not in ("auto", "required", "off"):
        raise InvalidResearchRequest("verify must be auto, required or off.")
    approve_plan = payload.get("approve_plan", False)
    if not isinstance(approve_plan, bool):
        raise InvalidResearchRequest("approve_plan must be true or false.")
    return {"question": question.strip(), "languages": languages,
            "max_sources": max_sources, "include_images": include_images,
            "verify": verify, "approve_plan": approve_plan}


def validate_plan(payload) -> list[dict]:
    """The search queries a writer approved, checked: what the box will run."""
    if not isinstance(payload, dict) or set(payload) != {"queries"}:
        raise InvalidResearchRequest('A plan approval is {"queries": [...]}.')
    queries = payload["queries"]
    if not isinstance(queries, list) or len(queries) > MAX_QUERIES:
        raise InvalidResearchRequest(f"queries must be a list of at most {MAX_QUERIES}.")
    approved = []
    for n, query in enumerate(queries):
        if not isinstance(query, dict) or set(query) != {"q", "language"}:
            raise InvalidResearchRequest(f"queries[{n}] must be {{q, language}}.")
        text = query["q"].strip() if isinstance(query["q"], str) else ""
        if not 1 <= len(text) <= 200:
            raise InvalidResearchRequest(f"queries[{n}].q must be 1-200 characters.")
        if not isinstance(query["language"], str) or not _LANGUAGE.match(
                query["language"]):
            raise InvalidResearchRequest(
                f"queries[{n}].language must be a language code, such as \"en\".")
        approved.append({"q": text, "language": query["language"]})
    return approved


def validate_refinement(payload) -> tuple[str, list[str], dict]:
    """(feedback, source refs to exclude, request fields to change) for a refine.

    The question stays the draft's own; the fields changed are checked again
    with the rest of the request by ``validate_request``.
    """
    if not isinstance(payload, dict):
        raise InvalidResearchRequest("A refinement must be a JSON object.")
    allowed = {"feedback", "exclude_sources"} | (_FIELDS - {"question"})
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise InvalidResearchRequest(f"Unknown fields: {', '.join(unknown)}.")
    feedback = payload.get("feedback")
    if not isinstance(feedback, str) or not 1 <= len(feedback.strip()) <= MAX_FEEDBACK:
        raise InvalidResearchRequest(f"feedback must be 1-{MAX_FEEDBACK} characters.")
    excluded = payload.get("exclude_sources", [])
    if (not isinstance(excluded, list) or len(excluded) > MAX_EXCLUDED
            or not all(isinstance(ref, str) for ref in excluded)):
        raise InvalidResearchRequest(
            f"exclude_sources must be a list of at most {MAX_EXCLUDED} source refs.")
    changes = {k: payload[k] for k in _FIELDS - {"question"} if k in payload}
    return feedback.strip(), list(dict.fromkeys(excluded)), changes


class Researcher(Protocol):
    """Runs research jobs somewhere else and reports on them; never writes canon."""

    # True only when the models run on hardware the writer controls.
    private: bool

    def availability(self) -> dict:
        """Whether research can be requested right now, and what to tell the writer."""

    def submit(self, request: dict, ref: str) -> dict:
        """Queue a research job; ``ref`` is Akasha's own job id. Returns the job."""

    def status(self, job_id: str) -> dict:
        """The job as it stands: queued, running (with its stage), or finished."""

    def cancel(self, job_id: str) -> dict:
        """Stop a queued or running job. Finished jobs come back unchanged."""

    def approve_plan(self, job_id: str, queries: list[dict]) -> dict:
        """Let a job waiting on its search plan run, with ``queries``."""

    def fetch_image(self, url: str, token: str, size: str = "full") -> tuple[bytes, str]:
        """An image candidate's (bytes, content type), fetched by the box."""


class UnavailableResearcher:
    """The default: no GPU box, so research is off and says so."""

    private = True

    def availability(self) -> dict:
        return availability(None, "research")

    def submit(self, request: dict, ref: str) -> dict:
        raise self._off()

    def status(self, job_id: str) -> dict:
        raise self._off()

    def cancel(self, job_id: str) -> dict:
        raise self._off()

    def approve_plan(self, job_id: str, queries: list[dict]) -> dict:
        raise self._off()

    def fetch_image(self, url: str, token: str, size: str = "full") -> tuple[bytes, str]:
        raise self._off()

    @staticmethod
    def _off() -> ResearchUnavailable:
        return ResearchUnavailable("Research is off: no GPU box is configured.")


class RemoteResearcher:
    """Research on the GPU-box worker, through the stack's shared client.

    ``worker`` is a ``visualizer.gpubox.WorkerClient`` in production, or its
    ``FakeWorker`` in tests and on the dev server.
    """

    private = True  # the worker's models run on our own hardware

    def __init__(self, worker):
        self.worker = worker

    def availability(self) -> dict:
        return availability(self.worker, "research")

    def submit(self, request: dict, ref: str) -> dict:
        return self._ask(self.worker.submit, "research", request,
                         service="akasha", ref=ref)

    def status(self, job_id: str) -> dict:
        return self._ask(self.worker.status, job_id)

    def cancel(self, job_id: str) -> dict:
        return self._ask(self.worker.cancel, job_id)

    def approve_plan(self, job_id: str, queries: list[dict]) -> dict:
        return self._ask(self.worker.approve_plan, job_id, queries)

    def fetch_image(self, url: str, token: str, size: str = "full") -> tuple[bytes, str]:
        return self._ask(self.worker.fetch_image, url, token, size)

    @staticmethod
    def _ask(call, *args, **kwargs):
        """One worker call, its failures restated in Akasha's own errors."""
        try:
            return call(*args, **kwargs)
        except WorkerImageUnavailable as err:
            raise ResearchImageUnavailable(err.message) from err
        except WorkerNotAwaitingApproval as err:
            raise ResearchConflict(err.message) from err
        except WorkerBusy as err:
            raise ResearchBusy(err.message, retry_after=err.retry_after) from err
        except WorkerJobNotFound as err:
            raise ResearchJobNotFound(err.message) from err
        except WorkerError as err:
            # Unreachable, a dependency down, or a request the box refused (a bad
            # token, a bug): to the writer all of them mean "not right now", and
            # /research/availability says which.
            raise ResearchUnavailable(err.message) from err
