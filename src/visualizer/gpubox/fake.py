"""A stand-in GPU box: ``WorkerClient``'s calls, answered in memory.

For tests and the dev server (``--fake-gpubox``), so the research and review
UIs can be built and exercised before the box exists. Two promises:

- **It obeys the contract.** Every reply validates against
  ``docs/gpu_worker/openapi.json``, and every quote it returns appears verbatim
  in the source or block it cites -- the rule the real worker enforces.
- **Every state is reachable.** Its ``mode`` names an availability state, and
  ``availability()`` reports exactly that state for it; ``fail_next()`` makes a
  job fail with any documented code.

Its output is labelled fake on purpose ("[Fake] …", example.org sources), so
demo data can never be mistaken for research. Its image candidates carry real
signed tokens and ``fetch_image`` checks them, returning a generated picture;
a candidate URL containing ``/gone`` behaves like an image that vanished.

A research job asked with ``approve_plan`` stops after planning, exactly like
the real one, until ``approve_plan()``; its plan expires after ``PLAN_TTL``. A
``refine`` request gets a result that keeps the previous sources it was not
told to exclude and adds one new one, so a caller's re-import can be tested.
"""

import base64
import hashlib
import hmac
import io
import itertools
import secrets
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from .errors import (
    JOB_FAILURE_CODES,
    WorkerBusy,
    WorkerImageUnavailable,
    WorkerJobNotFound,
    WorkerNotAwaitingApproval,
    WorkerRejected,
    WorkerUnavailable,
)

MODEL = "fake-model"
VERIFIER_MODEL = "fake-minicheck"
QUEUE_MAX = 20
RESULT_TTL = timedelta(hours=24)
PLAN_TTL = timedelta(hours=24)

# The availability state each mode produces (``off`` is the absence of a worker).
MODES = ("ready", "cold", "busy", "degraded", "queue_full", "unreachable",
         "misconfigured", "incompatible")
VERIFIERS = ("up", "down", "not_configured")

_RESEARCH_STAGES = ("planning", "searching", "fetching", "extracting",
                    "verifying", "writing")
_STAGE_MESSAGES = {
    "loading_model": "Loading the model",
    "planning": "Planning search queries",
    "searching": "Searching",
    "fetching": "Reading 2 of 2 sources",
    "extracting": "Extracting facts and quotes",
    "verifying": "Checking every quote against its page",
    "writing": "Writing the draft",
    "reviewing": "Reviewing the chapter",
    "second_check": "Second-checking on the verifier",
}


class FakeWorker:
    def __init__(self, mode: str = "ready", *, verifier: str = "up",
                 stage_seconds: float = 0.0,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        if verifier not in VERIFIERS:
            raise ValueError(f"verifier must be one of {VERIFIERS}, got {verifier!r}")
        self.verifier = verifier
        self.stage_seconds = stage_seconds
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._by_ref: dict[str, str] = {}
        self._ids = itertools.count(1)
        self._fail_next: str | None = None
        self._key = secrets.token_bytes(32)
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        """Put the box in ``mode``. ``cold`` unloads the model; the first job
        that runs loads it again, after which the box reports ``ready``."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self._model_loaded = mode != "cold"

    def fail_next(self, code: str) -> None:
        """Make the next submitted job fail with ``code``."""
        if code not in JOB_FAILURE_CODES:
            raise ValueError(f"not a job failure code: {code!r}")
        self._fail_next = code

    # -- WorkerClient's calls ------------------------------------------------

    def health(self) -> dict:
        self._reachable()
        with self._lock:
            states = [self._state(j)[0] for j in self._jobs.values()]
        loaded = [MODEL] if self._model_loaded else []
        named = self.verifier != "not_configured"
        return {
            "ok": self.mode != "degraded",
            "api_version": "2" if self.mode == "incompatible" else "1",
            "ollama": {"status": "up",
                       "models": {"review": MODEL, "research": MODEL},
                       "loaded": loaded},
            "searxng": {"status": "down" if self.mode == "degraded" else "up"},
            "gpu": {"busy": self.mode == "busy",
                    "vram_used_mb": 20480 if self.mode == "busy" else 812,
                    "vram_total_mb": 24576},
            # Unlike the real box, fake jobs don't wait for each other; the
            # counts still say how many are in each state.
            "queue": {"queued": QUEUE_MAX if self.mode == "queue_full"
                      else states.count("queued"),
                      "running": states.count("running"), "max": QUEUE_MAX},
            "verifier": {"status": self.verifier,
                         "models": {"research": VERIFIER_MODEL if named else None,
                                    "review": VERIFIER_MODEL if named else None}},
        }

    def submit(self, kind: str, request: dict, *, service: str, ref: str) -> dict:
        self._reachable()
        if self.mode == "queue_full":
            raise WorkerBusy(f"{QUEUE_MAX} jobs already queued", code="queue_full",
                             retry_after=30)
        _check(kind, request)
        body = {"kind": kind, "request": request, "service": service}
        with self._lock:
            if ref in self._by_ref:
                job = self._jobs[self._by_ref[ref]]
                if job["body"] != body:
                    raise WorkerRejected("Idempotency-Key reused with a different body",
                                         code="idempotency_conflict")
                return self._view(job)
            job_id = f"fake_{next(self._ids):06d}"
            job = {"id": job_id, "kind": kind, "request": request, "body": body,
                   "started": self._clock(), "created_at": self._now(),
                   "cancelled_after": None,
                   "fail": self._fail_next, "needs_load": not self._model_loaded,
                   "plan": (_proposed_plan(request) if kind == "research"
                            and request.get("approve_plan") else None),
                   "approved_at": None}
            self._fail_next = None
            self._jobs[job_id] = job
            self._by_ref[ref] = job_id
            return self._view(job)

    def status(self, job_id: str) -> dict:
        self._reachable()
        with self._lock:
            return self._view(self._require(job_id))

    def cancel(self, job_id: str) -> dict:
        self._reachable()
        with self._lock:
            job = self._require(job_id)
            if self._state(job)[0] in ("queued", "running", "awaiting_approval"):
                job["cancelled_after"] = self._work(job)
            return self._view(job)

    def approve_plan(self, job_id: str, queries: list[dict]) -> dict:
        self._reachable()
        if (not isinstance(queries, list) or len(queries) > 6
                or not all(isinstance(q, dict) and isinstance(q.get("q"), str)
                           and 1 <= len(q["q"]) <= 200
                           and isinstance(q.get("language"), str) for q in queries)):
            raise WorkerRejected("queries must be at most 6 {q, language}",
                                 code="invalid_request")
        with self._lock:
            job = self._require(job_id)
            state = self._state(job)[0]
            if state != "awaiting_approval":
                raise WorkerNotAwaitingApproval(
                    f"The job is {state}, not awaiting approval",
                    code="not_awaiting_approval")
            job["plan"] = [dict(q) for q in queries]
            job["approved_at"] = self._clock()
            return self._view(job)

    def fetch_image(self, url: str, token: str, size: str = "full") -> tuple[bytes, str]:
        self._reachable()
        if not hmac.compare_digest(self._sign(url), token or ""):
            raise WorkerRejected("The token does not match the URL",
                                 code="invalid_request")
        if "/gone" in url:
            raise WorkerImageUnavailable("The source answered 404",
                                         code="image_unavailable")
        return _picture(*((48, 36) if size == "preview" else (640, 480))), "image/png"

    def _sign(self, url: str) -> str:
        digest = hmac.new(self._key, b"image-v1:" + url.encode(), hashlib.sha256)
        return base64.urlsafe_b64encode(digest.digest()).decode().rstrip("=")

    # -- the simulation ------------------------------------------------------

    def _reachable(self) -> None:
        if self.mode == "unreachable":
            raise WorkerUnavailable("The GPU box is asleep or unreachable.")
        if self.mode == "misconfigured":
            raise WorkerRejected("Missing or invalid bearer token", code="unauthorized")

    def _require(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            raise WorkerJobNotFound(f"No job {job_id!r}", code="not_found")
        return job

    def _stages(self, job: dict) -> list[str]:
        """The order the real pipelines use: the second check runs before
        research writes its article, so the article only uses facts that
        survived it, and after a review, on the issues it found."""
        stages = ["loading_model"] if job["needs_load"] else []
        checked = self._second_check(job) == "checked"
        if job["kind"] == "research":
            stages += list(_RESEARCH_STAGES[:-1])
            stages += ["second_check"] if checked else []
            stages.append(_RESEARCH_STAGES[-1])
        else:
            stages += ["reviewing"] + (["second_check"] if checked else [])
        return stages

    def _second_check(self, job: dict) -> str:
        """checked | skipped | off | fail, for this job and this verifier."""
        verify = job["request"].get("verify", "auto")
        if verify == "off" or self.verifier == "not_configured":
            return "off"
        if self.verifier == "down":
            return "fail" if verify == "required" else "skipped"
        return "checked"

    def _pause(self, job: dict) -> float | None:
        """Seconds of work after which the job waits for its plan, or None."""
        if job["plan"] is None:
            return None
        stages = self._stages(job)
        return (2 + stages.index("planning")) * self.stage_seconds

    def _work(self, job: dict) -> float:
        """Seconds of work done: elapsed time, less any wait for approval."""
        elapsed = self._clock() - job["started"]
        pause = self._pause(job)
        if pause is None:
            return elapsed
        if job["approved_at"] is None:
            return min(elapsed, pause)
        return pause + (self._clock() - job["approved_at"])

    def _state(self, job: dict) -> tuple[str, str | None, float]:
        """(state, stage, seconds of work) for a job, from elapsed time alone.

        One interval queued, one per stage, then finished -- with a wait for
        approval after planning when the job asked for one. Deriving it rather
        than storing it means no background thread and no timers to clean up.
        """
        work = self._work(job)
        stages = self._stages(job)
        total = (1 + len(stages)) * self.stage_seconds
        if job["cancelled_after"] is not None and job["cancelled_after"] < total:
            return "cancelled", None, job["cancelled_after"]
        pause = self._pause(job)
        if pause is not None and job["approved_at"] is None \
                and self._clock() - job["started"] >= pause:
            waited = self._clock() - job["started"] - pause
            if waited >= PLAN_TTL.total_seconds():
                return "plan_expired", None, pause
            return "awaiting_approval", None, pause
        elapsed = work
        if elapsed >= total:
            return "finished", None, total
        if self.stage_seconds and elapsed < self.stage_seconds:
            return "queued", None, elapsed
        index = int(elapsed // self.stage_seconds) - 1 if self.stage_seconds else 0
        return "running", stages[max(0, index)], elapsed

    def _view(self, job: dict) -> dict:
        state, stage, seconds = self._state(job)
        created = job["created_at"]
        started = created + timedelta(seconds=self.stage_seconds)
        view = {"id": job["id"], "kind": job["kind"], "state": state,
                "position": None, "progress": None,
                "created_at": _iso(created), "started_at": None,
                "finished_at": None, "expires_at": None,
                "result": None, "error": None, "plan": self._plan_view(job, seconds)}
        if state == "queued":
            view["position"] = 1
            return view
        if state == "awaiting_approval":
            view["started_at"] = _iso(started)
            return view
        if state == "plan_expired":
            pause = created + timedelta(seconds=seconds)
            finished = pause + PLAN_TTL
            view.update(state="failed", started_at=_iso(started),
                        finished_at=_iso(finished),
                        expires_at=_iso(finished + RESULT_TTL),
                        error={"code": "plan_expired", "retryable": False,
                               "message": _FAILURE_MESSAGES["plan_expired"]})
            view["plan"]["expires_at"] = None
            return view
        if state == "running":
            if stage != "loading_model":
                self._model_loaded = True   # past loading, the model is in VRAM
            view.update(started_at=_iso(started),
                        progress={"stage": stage, "message": _STAGE_MESSAGES[stage]})
            return view
        waited = 0.0   # the time spent waiting for approval was not work
        if job["approved_at"] is not None and seconds > self._pause(job):
            waited = job["approved_at"] - job["started"] - self._pause(job)
        finished = created + timedelta(seconds=seconds + waited)
        # A job cancelled while still queued never started.
        if seconds >= self.stage_seconds:
            view["started_at"] = _iso(min(started, finished))
        view["finished_at"] = _iso(finished)
        if state == "finished":
            self._model_loaded = True
            self._finish(job, view, finished)
        return view

    def _plan_view(self, job: dict, work: float) -> dict | None:
        pause = self._pause(job)
        if pause is None or work < pause:
            return None
        approved = job["approved_at"] is not None
        expires = job["created_at"] + timedelta(seconds=pause) + PLAN_TTL
        return {"queries": [dict(q) for q in job["plan"]], "approved": approved,
                "expires_at": None if approved else _iso(expires)}

    def _finish(self, job: dict, view: dict, finished: datetime) -> None:
        failure = job["fail"] or ("unavailable" if self._second_check(job) == "fail"
                                  else None)
        view["expires_at"] = _iso(finished + RESULT_TTL)
        if failure:
            view["state"] = "failed"
            view["error"] = {"code": failure, "retryable": failure != "no_sources",
                             "message": _FAILURE_MESSAGES[failure]}
            return
        view["state"] = "done"
        if view["plan"] is not None:
            view["plan"]["expires_at"] = None
        if job["kind"] == "research":
            view["result"] = _research_result(job["request"], self._verification(job),
                                              finished, self._sign)
        else:
            view["result"] = _review_result(job["request"], self._verification(job),
                                            finished)

    def _verification(self, job: dict) -> dict:
        outcome = self._second_check(job)
        if outcome == "checked":
            return {"status": "checked", "model": VERIFIER_MODEL, "reason": None}
        if outcome == "skipped":
            return {"status": "skipped", "model": None,
                    "reason": "verifier_unavailable"}
        reason = ("caller_off" if job["request"].get("verify") == "off"
                  else "not_configured")
        return {"status": "off", "model": None, "reason": reason}


_FAILURE_MESSAGES = {
    "timeout": "The job exceeded its time limit",
    "unavailable": "A dependency stopped responding during the job",
    "no_sources": "No usable sources were found",
    "internal": "The worker hit an unexpected error",
    "plan_expired": "Nobody approved the search plan in time",
}


def _check(kind: str, request: dict) -> None:
    """The few rules a caller is most likely to break, refused as the worker would."""
    def invalid(message):
        return WorkerRejected(message, code="invalid_request")

    if kind not in ("research", "review"):
        raise invalid(f"Unknown job kind {kind!r}")
    if not isinstance(request, dict):
        raise invalid("A job request must be an object")
    if kind == "research":
        question = request.get("question")
        if not isinstance(question, str) or not 3 <= len(question) <= 500:
            raise invalid("question must be 3-500 characters")
        refine = request.get("refine")
        if refine is not None and not (
                isinstance(refine, dict) and isinstance(refine.get("feedback"), str)
                and refine["feedback"].strip()
                and isinstance(refine.get("previous"), dict)):
            raise invalid("refine needs feedback and the previous draft")
    else:
        blocks = (request.get("chapter") or {}).get("blocks")
        if not blocks or not all(isinstance(b, dict) and b.get("id") for b in blocks):
            raise invalid("chapter.blocks must be a non-empty list of {id, text}")
        if not isinstance(request.get("references"), list):
            raise invalid("references must be a list")


# -- canned results ----------------------------------------------------------


def _proposed_plan(request: dict) -> list[dict]:
    question = request["question"].strip()
    language = (request.get("languages") or ["en"])[0]
    return [{"q": f"[fake] {question}"[:200], "language": language},
            {"q": f"[fake] {question} history"[:200], "language": language}]


def _research_sources(request: dict, slug: str) -> list[tuple[str, str]]:
    """(url, title) of the pages a fake result cites.

    Two invented ones; when refining, the previous sources not excluded, then
    one new one -- what a real refinement re-reads and adds.
    """
    question = request["question"].strip()
    refine = request.get("refine")
    if not refine:
        return [(f"https://example.org/fake-research/{slug}/{n}",
                 f"[Fake] Source {n} on {question}") for n in (1, 2)]
    excluded = set(refine.get("exclude_urls") or [])
    kept = [(s["url"], s["title"] or "[Fake] A previous source")
            for s in refine["previous"].get("sources") or [] if s["url"] not in excluded]
    return kept + [(f"https://example.org/fake-research/{slug}/refined",
                    f"[Fake] A new source on {question}, after feedback")]


def _research_result(request: dict, verification: dict, at: datetime,
                     sign: Callable[[str], str]) -> dict:
    question = request["question"].strip()
    slug = quote("-".join(question.lower().split())[:60], safe="-")
    language = (request.get("languages") or ["en"])[0]
    pages = _research_sources(request, slug)
    quotes = [f"the first passage the fake worker invented about {question}",
              f"a second invented passage, also about {question}"]
    quotes += [f"invented passage {n} about {question}"
               for n in range(3, len(pages) + 1)]
    sources = [
        {"key": f"s{n}", "url": url, "title": title, "site": "example.org",
         "language": language, "retrieved_at": _iso(at), "excerpts": [quotes[n - 1]]}
        for n, (url, title) in enumerate(pages, 1)
    ]
    checked = verification["status"] == "checked"
    facts = [
        {"text": f"[Fake] A first finding about {question}.",
         "citations": [{"source": "s1", "quote": quotes[0]}],
         "check": {"status": "supported" if checked else "unchecked"}},
        {"text": f"[Fake] A second finding about {question}, only partly supported.",
         "citations": [{"source": "s2", "quote": quotes[1]}],
         "check": {"status": "partial" if checked else "unchecked"}},
    ][:len(sources)]
    facts += [{"text": f"[Fake] Finding {n} about {question}.",
               "citations": [{"source": f"s{n}", "quote": quotes[n - 1]}],
               "check": {"status": "supported" if checked else "unchecked"}}
              for n in range(3, len(sources) + 1)]
    dropped = [{"text": "[Fake] A finding whose quote was not on its page.",
                "reason": "quote_not_found"}]
    removed = 0
    if checked:
        dropped.append({"text": "[Fake] A finding the second check did not support.",
                        "reason": "unsupported"})
        removed = 1
    images = []
    if request.get("include_images"):
        found = [(f"https://example.org/fake-research/{slug}/image.jpg",
                  f"[Fake] An image about {question}", "CC0 (fake)"),
                 # One that will have vanished by the time anyone imports it.
                 (f"https://example.org/fake-research/{slug}/gone.jpg",
                  "[Fake] An image that has since vanished", None)]
        images = [{"url": url, "source": "s1", "caption": caption,
                   "license": license_, "fetch_token": sign(url)}
                  for url, caption, license_ in found]
    refined = "Refined after the writer's feedback. " if request.get("refine") else ""
    return {
        "article": {
            "title": question[:1].upper() + question[1:],
            "body": ("This draft came from the fake GPU worker, not from research. "
                     + refined + " ".join(
                         f"{fact['text']} [[cite:{fact['citations'][0]['source']}]]"
                         for fact in facts)),
            "topic": "fake",
            "facts": facts,
            "links": [a["ref"] for a in request.get("known_articles", [])][:2],
            "image_candidates": images,
        },
        "sources": sources,
        "dropped_facts": dropped,
        "verification": {**verification, "checked": len(facts) + removed if checked
                         else 0, "removed": removed},
        "model": MODEL,
        "generated_at": _iso(at),
    }


def _review_result(request: dict, verification: dict, at: datetime) -> dict:
    checked = verification["status"] == "checked"
    blocks = [b for b in request["chapter"]["blocks"] if _excerpt(b.get("text", ""))]
    by_kind = {}
    for reference in request["references"]:
        by_kind.setdefault(reference.get("kind"), reference)
    based_on = {"continuity": by_kind.get("canon"),
                "anachronism": by_kind.get("research") or by_kind.get("watchlist"),
                "prose": None}
    issues = []
    for check in request.get("checks") or ["continuity", "anachronism", "prose"]:
        if not blocks or (check != "prose" and based_on[check] is None):
            continue
        block = blocks[len(issues) % len(blocks)]
        reference = based_on[check]
        issues.append({
            "check": check,
            "severity": "info" if check == "prose" else "warning",
            "confidence": "possible",
            "block": block["id"],
            "quote": _excerpt(block["text"]),
            "message": f"[Fake] A {check} issue the fake worker made up.",
            "suggestion": "[Fake] A suggestion, also made up.",
            "reference": reference["ref"] if reference else None,
            "verified": True if checked else None,
        })
    return {
        "issues": issues,
        "verification": {**verification, "checked": len(issues) if checked else 0,
                         "removed": 0},
        "model": MODEL,
        "generated_at": _iso(at),
    }


def _excerpt(text: str, limit: int = 40) -> str:
    """A verbatim stretch of ``text``, cut at a word boundary."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit)
    return text[: cut if cut > 0 else limit]


def _picture(width: int, height: int) -> bytes:
    """A small, real PNG, so what imports it exercises real image handling."""
    from PIL import Image  # the stack's own dependency; only the fake needs it here

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (178, 84, 48)).save(buffer, "PNG")
    return buffer.getvalue()


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
