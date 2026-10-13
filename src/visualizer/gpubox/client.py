"""The stack's one way to reach the GPU-box worker.

Akasha and Logos share a single ``WorkerClient``: one base URL, one token, one
"is it awake?" cache. Each wraps it in its own seam (Akasha's ``Researcher``,
eventually Logos's review advisor) and neither ever talks to Ollama or SearXNG,
which stay on the box behind the worker.

Standard library only (``urllib``), so the NAS image gains no dependency for a
feature most deployments will never switch on. The transport is injectable for
tests; everything above it is plain request/response handling.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPException
from urllib.parse import quote

from .errors import (
    ERRORS_BY_CODE,
    WorkerBusy,
    WorkerError,
    WorkerJobNotFound,
    WorkerRejected,
    WorkerUnavailable,
)

API_PREFIX = "/v1"
DEFAULT_TIMEOUT = 10.0
# The health call gates whether a button is drawn, so it must not hang a page.
HEALTH_TIMEOUT = 2.0
# ...and is cached, failures included: a sleeping box should cost one short
# wait per interval, not one per page view.
HEALTH_TTL = 30.0
# A research result with its sources is tens of kilobytes; anything near this
# is a misbehaving worker, and the NAS should not buffer it.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
# Images are the exception: the worker sends up to its IMAGE_MAX_BYTES (20 MB
# by default, Akasha's own upload cap), and downloads them first, which is slow.
IMAGE_MAX_BYTES = 24 * 1024 * 1024
IMAGE_TIMEOUT = 45.0

# (method, url, headers, body, timeout, max_bytes=None) -> (status, headers, body)
Send = Callable[..., tuple[int, dict, bytes]]


@dataclass(frozen=True)
class WorkerConfig:
    url: str
    token: str
    timeout: float = DEFAULT_TIMEOUT


def worker_config_from_env(environ=os.environ) -> WorkerConfig | None:
    """``GPU_WORKER_URL`` / ``GPU_WORKER_TOKEN``, or None when no box is configured.

    An empty URL is the normal case and means "off". A URL without a token is a
    half-finished configuration, and is refused at startup rather than
    discovered as a 401 on someone's first click.
    """
    url = (environ.get("GPU_WORKER_URL") or "").strip()
    if not url:
        return None
    if not url.startswith(("https://", "http://")):
        raise RuntimeError(f"GPU_WORKER_URL must be an http(s) URL, got {url!r}.")
    token = (environ.get("GPU_WORKER_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("GPU_WORKER_URL is set but GPU_WORKER_TOKEN is not.")
    raw = (environ.get("GPU_WORKER_TIMEOUT") or "").strip()
    try:
        timeout = float(raw) if raw else DEFAULT_TIMEOUT
    except ValueError:
        raise RuntimeError(f"GPU_WORKER_TIMEOUT must be a number, got {raw!r}.") from None
    if timeout <= 0:
        raise RuntimeError("GPU_WORKER_TIMEOUT must be positive.")
    return WorkerConfig(url=url, token=token, timeout=timeout)


def worker_from_env(environ=os.environ) -> "WorkerClient | None":
    config = worker_config_from_env(environ)
    return WorkerClient(config) if config else None


def urllib_send(method, url, headers, body, timeout, max_bytes=None):
    """The real transport. HTTP errors come back as statuses; nothing else does."""
    limit = max_bytes or MAX_RESPONSE_BYTES
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), _bounded(response, limit)
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), _bounded(err, limit)
    except (urllib.error.URLError, TimeoutError, ConnectionError, HTTPException) as err:
        raise WorkerUnavailable("The GPU box is asleep or unreachable.") from err


def _bounded(stream, limit: int) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise WorkerUnavailable("The GPU box sent an oversized reply.")
    return data


class WorkerClient:
    """HTTP client for the worker's v1 job API."""

    def __init__(self, config: WorkerConfig, *, send: Send | None = None,
                 clock: Callable[[], float] = time.monotonic):
        base = config.url.rstrip("/")
        self.base_url = base if base.endswith(API_PREFIX) else base + API_PREFIX
        self._token = config.token
        self._timeout = config.timeout
        self._send = send or urllib_send
        self._clock = clock
        self._health_lock = threading.Lock()
        self._health_cache: tuple[float, dict | WorkerError] | None = None

    # -- the API -------------------------------------------------------------

    def health(self) -> dict:
        """The worker's own report on itself, at most ``HEALTH_TTL`` seconds old.

        Raises the cached ``WorkerError`` while a failure is still fresh. The
        lock is held across the call on purpose: when the box is asleep, the
        first request waits and the rest read its answer.
        """
        with self._health_lock:
            now = self._clock()
            if self._health_cache and self._health_cache[0] > now:
                cached = self._health_cache[1]
                if isinstance(cached, WorkerError):
                    raise cached.with_traceback(None)
                return cached
            try:
                result = self._call("GET", "/health", timeout=HEALTH_TIMEOUT)
            except WorkerError as err:
                self._health_cache = (now + HEALTH_TTL, err)
                raise
            self._health_cache = (now + HEALTH_TTL, result)
            return result

    def submit(self, kind: str, request: dict, *, service: str, ref: str) -> dict:
        """Queue a job and return it. ``ref`` is the caller's own job id.

        Sent as the ``Idempotency-Key`` too, so a retry after a dropped reply
        returns the job the first attempt created instead of queueing another.
        """
        body = {"kind": kind, "request": request,
                "client": {"service": service, "ref": ref}}
        return self._call("POST", "/jobs", body=body,
                          headers={"Idempotency-Key": ref})["job"]

    def status(self, job_id: str) -> dict:
        return self._call("GET", f"/jobs/{quote(job_id, safe='')}")["job"]

    def cancel(self, job_id: str) -> dict:
        return self._call("DELETE", f"/jobs/{quote(job_id, safe='')}")["job"]

    def approve_plan(self, job_id: str, queries: list[dict]) -> dict:
        """Queue a job parked in ``awaiting_approval`` again, with ``queries``."""
        return self._call("POST", f"/jobs/{quote(job_id, safe='')}/plan",
                          body={"queries": queries})["job"]

    def fetch_image(self, url: str, token: str, size: str = "full") -> tuple[bytes, str]:
        """(bytes, content type) of an image a research result found.

        ``token`` is that candidate's ``fetch_token``: the worker fetches only
        URLs it signed itself, so this can never be pointed somewhere else.
        """
        status, headers, raw = self._exchange(
            "POST", "/images", body={"url": url, "token": token, "size": size},
            accept="image/*", timeout=IMAGE_TIMEOUT, max_bytes=IMAGE_MAX_BYTES)
        content_type = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
        if 200 <= status < 300:
            if not content_type.startswith("image/"):
                raise WorkerUnavailable("The GPU box sent something other than an image.")
            return raw, content_type.split(";")[0].strip()
        raise _error(status, headers, _json(raw))

    # -- plumbing ------------------------------------------------------------

    def _call(self, method: str, path: str, *, body: dict | None = None,
              headers: dict | None = None, timeout: float | None = None) -> dict:
        status, reply_headers, raw = self._exchange(method, path, body=body,
                                                    headers=headers, timeout=timeout)
        payload = _json(raw)
        if 200 <= status < 300:
            if not isinstance(payload, dict):
                raise WorkerUnavailable("The GPU box sent a malformed reply.")
            return payload
        raise _error(status, reply_headers, payload)

    def _exchange(self, method: str, path: str, *, body: dict | None = None,
                  headers: dict | None = None, accept: str = "application/json",
                  timeout: float | None = None, max_bytes: int | None = None):
        all_headers = {"Authorization": f"Bearer {self._token}",
                       "Accept": accept, **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            all_headers["Content-Type"] = "application/json"
        return self._send(method, self.base_url + path, all_headers, data,
                          timeout or self._timeout, max_bytes=max_bytes)


def _json(raw: bytes):
    try:
        return json.loads(raw) if raw else None
    except (ValueError, UnicodeDecodeError):
        return None


def _error(status: int, headers: dict, payload) -> WorkerError:
    """The documented error, or the closest thing to it the status implies."""
    detail = payload.get("error") if isinstance(payload, dict) else None
    detail = detail if isinstance(detail, dict) else {}
    code = detail.get("code")
    message = str(detail.get("message") or f"The GPU box answered HTTP {status}.")
    cls = ERRORS_BY_CODE.get(code) or _by_status(status)
    if cls is WorkerBusy:
        return WorkerBusy(message, code=code, retry_after=_retry_after(headers))
    return cls(message, code=code)


def _by_status(status: int) -> type[WorkerError]:
    if status == 429:
        return WorkerBusy
    if status == 404:
        return WorkerJobNotFound
    if status >= 500:
        return WorkerUnavailable
    return WorkerRejected


def _retry_after(headers: dict) -> int | None:
    value = {k.lower(): v for k, v in headers.items()}.get("retry-after")
    try:
        return max(1, int(value)) if value is not None else None
    except ValueError:
        return None
