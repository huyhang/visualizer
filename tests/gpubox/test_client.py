"""WorkerClient: what it sends, how it reads every documented reply, what it caches."""

import json
import socket
import threading
import time

import pytest
from werkzeug.serving import make_server
from werkzeug.wrappers import Request, Response

from visualizer.gpubox import (
    ERRORS_BY_CODE,
    JOB_FAILURE_CODES,
    WorkerBusy,
    WorkerClient,
    WorkerConfig,
    WorkerImageUnavailable,
    WorkerJobNotFound,
    WorkerRejected,
    WorkerUnavailable,
    worker_config_from_env,
)
from visualizer.gpubox import client as client_module
from visualizer.gpubox.client import HEALTH_TIMEOUT, HEALTH_TTL

from .spec import SPEC, error_codes, validator

URL = "https://gpubox.example.ts.net:8443"
HEALTHY = SPEC["paths"]["/health"]["get"]["responses"]["200"]["content"][
    "application/json"]["examples"]["healthy"]["value"]
QUEUED = SPEC["paths"]["/jobs"]["post"]["responses"]["202"]["content"][
    "application/json"]["example"]
RESEARCH_REQUEST = SPEC["paths"]["/jobs"]["post"]["requestBody"]["content"][
    "application/json"]["examples"]["research"]["value"]["request"]
DOCUMENTED_ERRORS = [
    (name, response["content"]["application/json"]["example"])
    for name, response in SPEC["components"]["responses"].items()
]
STATUS_OF = {"InvalidRequest": 400, "Unauthorized": 401, "NotFound": 404,
             "IdempotencyConflict": 409, "PayloadTooLarge": 413,
             "QueueFull": 429, "Unavailable": 503, "ImageUnavailable": 502,
             "NotAwaitingApproval": 409}


class Replay:
    """A transport that records each request and answers from a script."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, method, url, headers, body, timeout, max_bytes=None):
        self.requests.append({"method": method, "url": url, "headers": headers,
                              "body": json.loads(body) if body else None,
                              "timeout": timeout, "max_bytes": max_bytes})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, payload, *rest = reply
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return status, (rest[0] if rest else {}), raw


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_client(send, **kwargs):
    return WorkerClient(WorkerConfig(url=URL, token="s3cret"), send=send, **kwargs)


# -- configuration -----------------------------------------------------------


@pytest.mark.parametrize("environ", [{}, {"GPU_WORKER_URL": ""},
                                     {"GPU_WORKER_URL": "   "}])
def test_no_url_means_no_worker(environ):
    assert worker_config_from_env(environ) is None


@pytest.mark.parametrize("environ,complaint", [
    ({"GPU_WORKER_URL": URL}, "GPU_WORKER_TOKEN"),
    ({"GPU_WORKER_URL": "gpubox:8443", "GPU_WORKER_TOKEN": "t"}, "http"),
    ({"GPU_WORKER_URL": URL, "GPU_WORKER_TOKEN": "t",
      "GPU_WORKER_TIMEOUT": "soon"}, "number"),
    ({"GPU_WORKER_URL": URL, "GPU_WORKER_TOKEN": "t",
      "GPU_WORKER_TIMEOUT": "0"}, "positive"),
])
def test_a_half_finished_configuration_is_refused_at_startup(environ, complaint):
    with pytest.raises(RuntimeError, match=complaint):
        worker_config_from_env(environ)


def test_configuration_from_the_environment():
    config = worker_config_from_env({"GPU_WORKER_URL": f" {URL} ",
                                     "GPU_WORKER_TOKEN": " t ",
                                     "GPU_WORKER_TIMEOUT": "2.5"})
    assert config == WorkerConfig(url=URL, token="t", timeout=2.5)


@pytest.mark.parametrize("url", [URL, URL + "/", URL + "/v1", URL + "/v1/"])
def test_the_api_prefix_is_added_exactly_once(url):
    client = WorkerClient(WorkerConfig(url=url, token="t"))
    assert client.base_url == URL + "/v1"


# -- requests ----------------------------------------------------------------


def test_submit_sends_a_contract_valid_job_with_its_idempotency_key():
    send = Replay((202, QUEUED))
    job = make_client(send).submit("research", RESEARCH_REQUEST,
                                   service="akasha", ref="akasha-job-6f1c2e")
    assert job == QUEUED["job"]
    (sent,) = send.requests
    assert (sent["method"], sent["url"]) == ("POST", URL + "/v1/jobs")
    assert sent["headers"]["Authorization"] == "Bearer s3cret"
    assert sent["headers"]["Idempotency-Key"] == "akasha-job-6f1c2e"
    validator("JobCreate").validate(sent["body"])
    assert sent["body"]["client"] == {"service": "akasha", "ref": "akasha-job-6f1c2e"}


def test_job_ids_are_escaped_into_the_path():
    send = Replay((200, QUEUED), (200, QUEUED))
    client = make_client(send)
    client.status("j/../x")
    client.cancel("j 1")
    assert send.requests[0]["url"] == URL + "/v1/jobs/j%2F..%2Fx"
    assert [r["method"] for r in send.requests] == ["GET", "DELETE"]
    assert send.requests[1]["url"] == URL + "/v1/jobs/j%201"


# -- replies -----------------------------------------------------------------


def test_every_documented_error_code_is_handled():
    assert set(ERRORS_BY_CODE) | JOB_FAILURE_CODES == error_codes()
    assert {example["error"]["code"] for _, example in DOCUMENTED_ERRORS} == set(
        ERRORS_BY_CODE)


@pytest.mark.parametrize("name,example", DOCUMENTED_ERRORS)
def test_each_documented_error_becomes_its_exception(name, example):
    send = Replay((STATUS_OF[name], example))
    with pytest.raises(ERRORS_BY_CODE[example["error"]["code"]]) as raised:
        make_client(send).status("j_1")
    assert raised.value.code == example["error"]["code"]
    assert raised.value.message == example["error"]["message"]


def test_a_full_queue_says_when_to_come_back():
    example = dict(DOCUMENTED_ERRORS)["QueueFull"]
    send = Replay((429, example, {"Retry-After": "12"}))
    with pytest.raises(WorkerBusy) as raised:
        make_client(send).submit("research", RESEARCH_REQUEST, service="akasha",
                                 ref="r1")
    assert raised.value.retry_after == 12


@pytest.mark.parametrize("status,body,expected", [
    (502, b"<html>Bad Gateway</html>", WorkerUnavailable),
    (500, b"", WorkerUnavailable),
    (404, b"", WorkerJobNotFound),
    (429, b"", WorkerBusy),
    (418, b"teapot", WorkerRejected),
])
def test_undocumented_errors_fall_back_on_the_status(status, body, expected):
    with pytest.raises(expected):
        make_client(Replay((status, body))).status("j_1")


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b""])
def test_a_malformed_success_is_treated_as_unavailable(body):
    with pytest.raises(WorkerUnavailable):
        make_client(Replay((200, body))).status("j_1")


# -- images ------------------------------------------------------------------

IMAGE_REQUEST = SPEC["paths"]["/images"]["post"]["requestBody"]["content"][
    "application/json"]["examples"]["preview"]["value"]


def test_fetching_an_image_sends_its_token_and_returns_its_bytes():
    send = Replay((200, b"\x89PNG...", {"Content-Type": "image/png"}))
    data, content_type = make_client(send).fetch_image(
        IMAGE_REQUEST["url"], IMAGE_REQUEST["token"], "preview")
    assert (data, content_type) == (b"\x89PNG...", "image/png")
    (sent,) = send.requests
    assert (sent["method"], sent["url"]) == ("POST", URL + "/v1/images")
    assert sent["headers"]["Accept"] == "image/*"
    assert sent["max_bytes"] == client_module.IMAGE_MAX_BYTES
    validator("ImageFetch").validate(sent["body"])


def test_an_image_the_box_could_not_get():
    example = dict(DOCUMENTED_ERRORS)["ImageUnavailable"]
    with pytest.raises(WorkerImageUnavailable) as raised:
        make_client(Replay((502, example))).fetch_image("https://x/y.jpg", "t")
    assert raised.value.message == example["error"]["message"]


def test_a_success_that_is_not_an_image_is_refused():
    send = Replay((200, {"job": {}}, {"Content-Type": "application/json"}))
    with pytest.raises(WorkerUnavailable, match="other than an image"):
        make_client(send).fetch_image("https://x/y.jpg", "t")


# -- the health cache --------------------------------------------------------


def test_health_is_short_and_cached():
    clock = Clock()
    send = Replay((200, HEALTHY), (200, HEALTHY))
    client = make_client(send, clock=clock)
    assert client.health() == HEALTHY
    clock.now += HEALTH_TTL - 1
    assert client.health() == HEALTHY
    assert len(send.requests) == 1
    assert send.requests[0]["timeout"] == HEALTH_TIMEOUT
    clock.now += 2
    client.health()
    assert len(send.requests) == 2


def test_a_sleeping_box_costs_one_wait_per_interval_not_one_per_page():
    clock = Clock()
    send = Replay(WorkerUnavailable("asleep"), (200, HEALTHY))
    client = make_client(send, clock=clock)
    for _ in range(3):
        with pytest.raises(WorkerUnavailable):
            client.health()
    assert len(send.requests) == 1
    clock.now += HEALTH_TTL + 1
    assert client.health() == HEALTHY


# -- the real transport ------------------------------------------------------


@pytest.fixture
def box():
    """A real HTTP server on localhost standing in for the worker."""

    @Request.application
    def app(request):
        if request.headers.get("Authorization") != "Bearer s3cret":
            return Response(json.dumps(dict(DOCUMENTED_ERRORS)["Unauthorized"]),
                            401, content_type="application/json")
        if request.path == "/v1/slow":
            time.sleep(1.0)
        if request.path == "/v1/huge":
            return Response(b"x" * 500, 200)
        return Response(json.dumps(HEALTHY), 200, content_type="application/json")

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_real_http_round_trip(box):
    assert WorkerClient(WorkerConfig(url=box, token="s3cret")).health() == HEALTHY


def test_a_wrong_token_is_rejected_not_retried(box):
    with pytest.raises(WorkerRejected) as raised:
        WorkerClient(WorkerConfig(url=box, token="wrong")).health()
    assert raised.value.code == "unauthorized"


def test_a_slow_box_times_out_as_unavailable(box):
    client = WorkerClient(WorkerConfig(url=box, token="s3cret", timeout=0.2))
    with pytest.raises(WorkerUnavailable):
        client._call("GET", "/slow")


def test_an_oversized_reply_is_not_buffered(box, monkeypatch):
    monkeypatch.setattr(client_module, "MAX_RESPONSE_BYTES", 100)
    with pytest.raises(WorkerUnavailable, match="oversized"):
        WorkerClient(WorkerConfig(url=box, token="s3cret"))._call("GET", "/huge")


def test_nothing_listening_is_unavailable():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with pytest.raises(WorkerUnavailable, match="asleep or unreachable"):
        WorkerClient(WorkerConfig(url=f"http://127.0.0.1:{port}", token="t")).health()
