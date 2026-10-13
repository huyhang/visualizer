"""Fixtures for the GPU worker: a real app, store and runner; fake surroundings.

The runner is driven by hand (``run_next()``) rather than on its thread, so a
test decides exactly when a job runs. Pipelines and probes are stand-ins built
from the contract's own examples.
"""

import copy
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from visualizer.gpu_worker.app import create_app
from visualizer.gpu_worker.config import WorkerConfig
from visualizer.gpu_worker.contract import Contract
from visualizer.gpu_worker.fetch import Fetched, FetchError
from visualizer.gpu_worker.images import Images, TokenSigner
from visualizer.gpu_worker.runner import Runner
from visualizer.gpu_worker.store import JobStore

SPEC = json.loads((Path(__file__).resolve().parents[2] / "docs" / "gpu_worker"
                   / "openapi.json").read_text())
TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def example(path, name):
    """A named example value from the spec, by operation."""
    method, route, where = path
    node = SPEC["paths"][route][method]
    if where == "request":
        return copy.deepcopy(node["requestBody"]["content"]["application/json"]
                             ["examples"][name]["value"])
    return copy.deepcopy(node["responses"]["200"]["content"]["application/json"]
                         ["examples"][name]["value"])


RESEARCH_JOB = example(("post", "/jobs", "request"), "research")
REVIEW_JOB = example(("post", "/jobs", "request"), "review")
RESEARCH_RESULT = example(("get", "/jobs/{job_id}", "response"),
                          "researchDone")["job"]["result"]
REVIEW_RESULT = example(("get", "/jobs/{job_id}", "response"),
                        "reviewDone")["job"]["result"]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


class CannedPipelines:
    """Returns the contract's example results, after reporting some stages.

    ``behaviour`` lets a test make the next run raise or return something else.
    """

    def __init__(self):
        self.behaviour = None
        self.calls = []

    def research(self, request, ctx):
        return self._run("research", request, ctx,
                         ["planning", "searching", "writing"], RESEARCH_RESULT)

    def review(self, request, ctx):
        return self._run("review", request, ctx, ["reviewing"], REVIEW_RESULT)

    def _run(self, kind, request, ctx, stages, result):
        self.calls.append((kind, request))
        for stage in stages:
            ctx.progress(stage, f"{stage}…")
        if self.behaviour is not None:
            return self.behaviour(request, ctx)
        return copy.deepcopy(result)


class StaticProbes:
    def __init__(self, **sections):
        self.sections = {
            "ollama": {"status": "up",
                       "models": {"review": "qwen3:30b", "research": "qwen3:30b"},
                       "loaded": ["qwen3:30b"]},
            "searxng": {"status": "up"},
            "gpu": {"busy": False, "vram_used_mb": 812, "vram_total_mb": 24576},
            "verifier": {"status": "not_configured",
                         "models": {"research": None, "review": None}},
            **sections,
        }

    def snapshot(self):
        return copy.deepcopy(self.sections)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def contract():
    return Contract()


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.sqlite3", ttl=timedelta(hours=24))


@pytest.fixture
def pipelines():
    return CannedPipelines()


@pytest.fixture
def probes():
    return StaticProbes()


@pytest.fixture
def config(tmp_path):
    return WorkerConfig(token=TOKEN, db_path=str(tmp_path / "jobs.sqlite3"),
                        queue_max=3)


def picture(width=800, height=600, fmt="PNG", mode="RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height), (90, 120, 160)).save(buffer, fmt)
    return buffer.getvalue()


class StubFetcher:
    """Stands in for the web: url -> bytes, or a FetchError to raise."""

    def __init__(self, pages=None):
        self.pages = pages or {}
        self.asked = []

    def fetch(self, url, *, accept=None, max_bytes=None):
        self.asked.append(url)
        page = self.pages.get(url)
        if page is None:
            raise FetchError("status", "The source answered 404")
        if isinstance(page, FetchError):
            raise page
        body, content_type = page if isinstance(page, tuple) else (page, "image/png")
        if max_bytes and len(body) > max_bytes:
            raise FetchError("too_large", "Larger than the limit")
        return Fetched(url=url, content_type=content_type, charset=None, body=body)


@pytest.fixture
def signer():
    return TokenSigner(b"k" * 32)


@pytest.fixture
def web():
    return StubFetcher()


@pytest.fixture
def images(signer, web):
    return Images(signer, web, max_bytes=20 * 1024 * 1024)


@pytest.fixture
def runner(store, pipelines, contract, clock, signer):
    return Runner(store, pipelines, contract, sign=signer.sign, clock=clock)


@pytest.fixture
def app(config, store, runner, probes, contract, images, clock):
    application = create_app(config, store, runner, probes, contract, images,
                             clock=clock)
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def submit(client, body=None, key=None):
    headers = dict(AUTH)
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post("/v1/jobs", json=body or RESEARCH_JOB, headers=headers)
