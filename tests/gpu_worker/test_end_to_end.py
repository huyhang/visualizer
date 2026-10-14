"""The stack's client against the real worker, over real HTTP.

Each side is tested on its own against the contract; this is the test that the
two actually agree when they talk. The worker runs on a local socket with its
real API, store and runner -- only its pipelines and probes are stand-ins --
and is driven through the very code the NAS uses: ``visualizer.gpubox``'s
client, Akasha's ``RemoteResearcher``, and finally the whole stack.
"""

import copy
import io
import threading
import time
from datetime import timedelta

import pytest
from PIL import Image
from werkzeug.serving import make_server
from werkzeug.test import Client

from tests.gpubox.spec import validator
from visualizer.akasha.errors import (
    ResearchBusy,
    ResearchJobNotFound,
    ResearchUnavailable,
)
from visualizer.akasha.research import RemoteResearcher
from visualizer.gpu_worker.app import create_app
from visualizer.gpu_worker.config import WorkerConfig
from visualizer.gpu_worker.contract import Contract
from visualizer.gpu_worker.images import Images, TokenSigner
from visualizer.gpu_worker.pipelines import NotBuiltPipelines
from visualizer.gpu_worker.runner import Runner
from visualizer.gpu_worker.store import JobStore
from visualizer.gpubox import WorkerClient, availability
from visualizer.gpubox import WorkerConfig as ClientConfig

from .conftest import (
    DISCUSSION_JOB,
    RESEARCH_JOB,
    REVIEW_JOB,
    TOKEN,
    CannedPipelines,
    StaticProbes,
    StubFetcher,
    picture,
)

QUESTION = RESEARCH_JOB["request"]


@pytest.fixture
def box(tmp_path):
    """Start a worker on a local socket; returns a function that does so."""
    started = []

    def start(pipelines=None, *, run_jobs=True, queue_max=20, probes=None,
              web=None):
        config = WorkerConfig(token=TOKEN, queue_max=queue_max)
        contract = Contract()
        store = JobStore(tmp_path / f"jobs-{len(started)}.sqlite3",
                         ttl=timedelta(hours=24))
        signer = TokenSigner(b"e2e-key" * 5)
        runner = Runner(store, pipelines or CannedPipelines(), contract,
                        sign=signer.sign, poll_seconds=0.02)
        app = create_app(config, store, runner, probes or StaticProbes(), contract,
                         Images(signer, web or StubFetcher(), 20 * 1024 * 1024))
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if run_jobs:
            runner.start()
        started.append((server, runner))
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for server, runner in started:
        runner.stop()
        server.shutdown()


def client_for(url, token=TOKEN):
    return WorkerClient(ClientConfig(url=url, token=token, timeout=5))


def until_finished(read, job_id, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = read(job_id)
        if job["state"] not in ("queued", "running"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} still unfinished after {seconds}s")


# -- what Akasha asks before drawing the button ------------------------------


def test_availability_over_the_wire(box):
    worker = client_for(box())
    validator("Health").validate(worker.health())
    assert availability(worker, "research")["state"] == "ready"


def test_a_cold_or_busy_box_is_reported_as_such(box):
    probes = StaticProbes()
    probes.sections["ollama"]["loaded"] = []
    probes.sections["gpu"]["busy"] = True
    worker = client_for(box(probes=probes))
    assert availability(worker, "research")["state"] == "busy"


def test_a_token_the_box_does_not_know_reads_as_misconfigured(box):
    url = box()
    assert availability(client_for(url, token="x" * 32), "research")["state"] == \
        "misconfigured"
    with pytest.raises(ResearchUnavailable):
        RemoteResearcher(client_for(url, token="x" * 32)).submit(QUESTION, "a-1")


# -- a research job, as Akasha will run one ----------------------------------


def test_a_research_job_from_akasha_to_result(box):
    researcher = RemoteResearcher(client_for(box()))
    job = researcher.submit(QUESTION, "akasha-job-1")
    validator("Job").validate(job)
    done = until_finished(researcher.status, job["id"])
    validator("Job").validate(done)
    assert done["state"] == "done"
    validator("ResearchResult").validate(done["result"])
    assert researcher.submit(QUESTION, "akasha-job-1")["id"] == job["id"], \
        "a retry with the same Akasha job id returns the same worker job"


def test_a_review_job_from_logos_to_result(box):
    worker = client_for(box())
    job = worker.submit("review", REVIEW_JOB["request"], service="logos",
                        ref="logos-job-1")
    done = until_finished(worker.status, job["id"])
    validator("ReviewResult").validate(done["result"])
    blocks = {b["id"]: b["text"] for b in REVIEW_JOB["request"]["chapter"]["blocks"]}
    for issue in done["result"]["issues"]:
        assert issue["quote"] in blocks[issue["block"]]


def test_a_discussion_job_from_logos_to_result(box):
    worker = client_for(box())
    job = worker.submit("discussion", DISCUSSION_JOB["request"], service="logos",
                        ref="logos-discussion-1")
    done = until_finished(worker.status, job["id"])
    validator("Job").validate(done)
    validator("DiscussionResult").validate(done["result"])


def test_the_shipped_worker_fails_jobs_honestly(box):
    researcher = RemoteResearcher(client_for(box(NotBuiltPipelines())))
    done = until_finished(researcher.status,
                          researcher.submit(QUESTION, "akasha-job-1")["id"])
    assert done["state"] == "failed"
    assert done["error"]["message"] == "The research pipeline is not built yet"


def test_an_image_candidate_from_a_result_can_be_fetched(box):
    image_url = "https://example.org/tea-bowl.jpg"   # the spec example's candidate
    original = picture(640, 480)
    worker = client_for(box(web=StubFetcher({image_url: original})))
    job = worker.submit("research", QUESTION, service="akasha", ref="a-1")
    done = until_finished(worker.status, job["id"])
    (candidate,) = done["result"]["article"]["image_candidates"]
    data, content_type = worker.fetch_image(candidate["url"], candidate["fetch_token"])
    assert (data, content_type) == (original, "image/png")
    preview, preview_type = worker.fetch_image(candidate["url"],
                                               candidate["fetch_token"], "preview")
    assert preview_type == "image/jpeg"
    with Image.open(io.BytesIO(preview)) as shown:
        assert shown.size == (360, 270)


# -- the edges ---------------------------------------------------------------


def test_a_full_queue_reaches_akasha_as_busy(box):
    researcher = RemoteResearcher(client_for(box(run_jobs=False, queue_max=1)))
    researcher.submit(QUESTION, "akasha-job-1")
    with pytest.raises(ResearchBusy) as raised:
        researcher.submit(QUESTION, "akasha-job-2")
    assert raised.value.retry_after == 30


def test_cancelling_from_akasha(box):
    researcher = RemoteResearcher(client_for(box(run_jobs=False)))
    job = researcher.submit(QUESTION, "akasha-job-1")
    assert researcher.cancel(job["id"])["state"] == "cancelled"
    assert researcher.status(job["id"])["state"] == "cancelled"


def test_an_unknown_job_reaches_akasha_as_not_found(box):
    with pytest.raises(ResearchJobNotFound):
        RemoteResearcher(client_for(box())).status("j_never")


def test_a_changed_request_under_the_same_id_is_refused(box):
    researcher = RemoteResearcher(client_for(box(run_jobs=False)))
    researcher.submit(QUESTION, "akasha-job-1")
    changed = copy.deepcopy(QUESTION)
    changed["question"] = "Tang-dynasty hairpins"
    with pytest.raises(ResearchUnavailable, match="different body"):
        researcher.submit(changed, "akasha-job-1")


# -- the whole chain ---------------------------------------------------------


def test_from_the_writers_browser_to_the_box(box, monkeypatch):
    """Akasha's own route, through the stack's wiring, to the worker and back."""
    import mongomock.gridfs

    from visualizer.stack import build_application

    # Akasha keeps images in GridFS, which mongomock only fakes once asked to.
    mongomock.gridfs.enable_gridfs_integration()
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("MONITORING_ENABLED", "false")
    monkeypatch.setenv("GPU_WORKER_URL", box())
    monkeypatch.setenv("GPU_WORKER_TOKEN", TOKEN)
    browser = Client(build_application(mongomock.MongoClient()))
    browser.post("/register", json={"username": "w", "password": "Correct-horse-9",
                                    "email": "w@example.com"})
    browser.post("/login", json={"username": "w", "password": "Correct-horse-9"})
    body = browser.get("/research/availability").get_json()
    assert (body["state"], body["model"], body["private"]) == (
        "ready", "qwen3:30b", True)
