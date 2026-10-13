"""The worker's HTTP API: ``/v1/health``, ``/v1/jobs`` and ``/v1/images``.

Every request needs the bearer token. Every error, including Flask's own 404s
and 405s, comes back in the contract's one error shape. Nothing here runs a
job: ``POST`` queues it and wakes the ``Runner``, and the ``GET``s read the store.
``/v1/images`` is the one synchronous call: it fetches a signed image candidate
there and then.
"""

import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from flask import Flask, Response, request
from werkzeug.exceptions import HTTPException

from .config import WorkerConfig
from .contract import Contract
from .fetch import FetchError
from .images import Images
from .runner import Runner
from .store import JobStore

LOG = logging.getLogger("visualizer.gpu_worker")

API_VERSION = "1"
# Per the contract: research requests are small, review requests carry a chapter.
SIZE_LIMITS = {"research": 64 * 1024, "review": 1024 * 1024}
QUEUE_RETRY_AFTER = 30

_STATUS_CODES = {400: "invalid_request", 401: "unauthorized", 404: "not_found",
                 405: "invalid_request", 409: "idempotency_conflict",
                 413: "payload_too_large", 429: "queue_full",
                 502: "image_unavailable", 503: "unavailable"}


def _error(status: int, message: str, *, retryable: bool = False,
           headers: dict | None = None) -> Response:
    body = {"error": {"code": _STATUS_CODES[status], "message": message,
                      "retryable": retryable}}
    return Response(json.dumps(body), status, headers=headers,
                    content_type="application/json")


def _json(payload, status: int = 200, headers: dict | None = None) -> Response:
    return Response(json.dumps(payload), status, headers=headers,
                    content_type="application/json")


def body_hash(body: dict) -> str:
    """Stable across key order, so a retried request matches its first attempt."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_app(config: WorkerConfig, store: JobStore, runner: Runner, probes,
               contract: Contract, images: Images, *,
               clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> Flask:
    app = Flask(__name__)
    # The largest request any job kind may send, plus room for the envelope.
    app.config["MAX_CONTENT_LENGTH"] = max(SIZE_LIMITS.values()) + 4096
    expected = f"Bearer {config.token}".encode()

    @app.before_request
    def require_token():
        given = request.headers.get("Authorization", "").encode()
        if not hmac.compare_digest(given, expected):
            return _error(401, "Missing or invalid bearer token")
        return None

    @app.errorhandler(HTTPException)
    def http_error(err: HTTPException):
        status = err.code if err.code in _STATUS_CODES else 400
        if status == 413:
            return _error(413, "Request over the size limit")
        return _error(status, err.name)

    @app.get("/v1/health")
    def health():
        report = probes.snapshot()
        counts = store.counts()
        return _json({
            "ok": (report["ollama"]["status"] == "up"
                   and report["searxng"]["status"] == "up"),
            "api_version": API_VERSION,
            **report,
            "queue": {**counts, "max": config.queue_max},
        })

    @app.post("/v1/jobs")
    def create_job():
        raw = request.get_data(cache=False)
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return _error(400, "The body is not valid JSON")
        problem = contract.job_problem(body)
        if problem:
            return _error(400, f"Schema violation: {problem}")
        kind = body["kind"]
        if len(raw) > SIZE_LIMITS[kind]:
            return _error(413, f"A {kind} request is at most {SIZE_LIMITS[kind]} bytes")
        key = request.headers.get("Idempotency-Key")
        if key is not None and not 1 <= len(key) <= 128:
            return _error(400, "Idempotency-Key must be 1-128 characters")

        digest = body_hash(body)
        if key is not None:
            known = store.by_key(key)
            if known is not None:
                job, known_digest = known
                if known_digest != digest:
                    return _error(409, "Idempotency-Key reused with a different body")
                return _json({"job": job}, 200)

        now = clock()
        store.sweep(now)
        if store.counts()["queued"] >= config.queue_max:
            return _error(429, f"{config.queue_max} jobs already queued",
                          retryable=True,
                          headers={"Retry-After": str(QUEUE_RETRY_AFTER)})
        job, created = store.create(kind, body["request"], digest, key, now)
        if not created:   # the same key, raced in by a concurrent retry
            return _json({"job": job}, 200)
        LOG.info("job %s queued (kind=%s, service=%s)", job["id"], kind,
                 body["client"]["service"])
        runner.wake()
        return _json({"job": job}, 202, headers={"Location": f"/v1/jobs/{job['id']}"})

    @app.get("/v1/jobs/<job_id>")
    def get_job(job_id):
        job = store.get(job_id)
        if job is None:
            return _error(404, "Unknown or expired job")
        return _json({"job": job})

    @app.delete("/v1/jobs/<job_id>")
    def cancel_job(job_id):
        job = store.cancel(job_id, clock())
        if job is None:
            return _error(404, "Unknown or expired job")
        return _json({"job": job})

    @app.post("/v1/images")
    def fetch_image():
        try:
            body = json.loads(request.get_data(cache=False))
        except (ValueError, UnicodeDecodeError):
            return _error(400, "The body is not valid JSON")
        problem = contract.image_problem(body)
        if problem:
            return _error(400, f"Schema violation: {problem}")
        if not images.signer.verify(body["url"], body["token"]):
            return _error(400, "The token does not match the URL")
        size = body.get("size", "full")
        try:
            data, content_type = images.fetch(body["url"], size)
        except FetchError as err:
            LOG.info("image fetch failed (%s)", err.reason)
            return _error(502, err.message)
        # The size, not the URL: what was looked up says what was researched.
        LOG.info("image fetched (size=%s, bytes=%d)", size, len(data))
        return Response(data, 200, content_type=content_type)

    return app
