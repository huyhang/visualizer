"""Health probes read the box without ever raising; config refuses bad settings."""

import io
import subprocess
import urllib.error

import pytest

from tests.gpubox.spec import validator
from visualizer.gpu_worker.config import WorkerConfig, config_from_env
from visualizer.gpu_worker.probes import SystemProbes, gpu_section, parse_nvidia_smi

GIB = 1024 ** 3


# -- the GPU -----------------------------------------------------------------


@pytest.mark.parametrize("used,total,ollama,busy", [
    (812, 24576, 0, False),          # idle
    (20000, 24576, 19000, False),    # Ollama holds it: that's us, not "busy"
    (20000, 24576, 0, True),         # someone else (ComfyUI) holds it
    (None, None, 0, False),          # no nvidia-smi: unknown, not busy
])
def test_busy_means_someone_else_has_the_gpu(used, total, ollama, busy):
    assert gpu_section(used, total, ollama)["busy"] is busy


@pytest.mark.parametrize("output,expected", [
    ("812, 24576\n", (812, 24576)),
    ("812, 24576\n4, 24576\n", (812, 24576)),
    ("", (None, None)),
    ("[N/A], [N/A]", (None, None)),
])
def test_reading_nvidia_smi(output, expected):
    assert parse_nvidia_smi(output) == expected


# -- the surroundings, faked -------------------------------------------------


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener(answers):
    """urlopen standing in for the box: url -> bytes, or an exception to raise."""
    def open_(url, timeout):
        for prefix, answer in answers.items():
            if url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return Reply(answer)
        raise urllib.error.URLError("connection refused")
    return open_


def smi(stdout="812, 24576\n", returncode=0):
    def run(*args, **kwargs):
        if isinstance(stdout, Exception):
            raise stdout
        return subprocess.CompletedProcess(args, returncode, stdout=stdout)
    return run


CONFIG = WorkerConfig(token="t" * 32)
PS = (b'{"models": [{"name": "qwen3:30b", "size_vram": %d}]}' % (19 * GIB))


def full_health(snapshot):
    return {"ok": True, "api_version": "1", **snapshot,
            "queue": {"queued": 0, "running": 0, "max": 20}}


def test_a_healthy_box(monkeypatch):
    probes = SystemProbes(CONFIG, run=smi("20000, 24576\n"), opener=opener({
        "http://127.0.0.1:11434/api/ps": PS,
        "http://127.0.0.1:8888/healthz": b"OK",
    }))
    snapshot = probes.snapshot()
    validator("Health").validate(full_health(snapshot))
    assert snapshot["ollama"]["status"] == "up"
    assert snapshot["ollama"]["loaded"] == ["qwen3:30b"]
    assert snapshot["searxng"]["status"] == "up"
    assert snapshot["gpu"] == {"busy": False, "vram_used_mb": 20000,
                               "vram_total_mb": 24576}
    assert snapshot["verifier"]["status"] == "not_configured"


def test_a_box_whose_dependencies_are_down():
    probes = SystemProbes(CONFIG, run=smi(FileNotFoundError("nvidia-smi")),
                          opener=opener({}))
    snapshot = probes.snapshot()
    validator("Health").validate(full_health(snapshot))
    assert snapshot["ollama"] == {"status": "down", "loaded": [],
                                  "models": {"review": "qwen3:30b",
                                             "research": "qwen3:30b"}}
    assert snapshot["searxng"]["status"] == "down"
    assert snapshot["gpu"] == {"busy": False, "vram_used_mb": None,
                               "vram_total_mb": None}


@pytest.mark.parametrize("answer,status", [
    (urllib.error.HTTPError("u", 404, "Not Found", {}, None), "up"),
    (urllib.error.HTTPError("u", 502, "Bad Gateway", {}, None), "down"),
    (TimeoutError(), "down"),
])
def test_searxng_counts_as_up_if_anything_answers(answer, status):
    probes = SystemProbes(CONFIG, run=smi(), opener=opener({
        "http://127.0.0.1:8888/healthz": answer}))
    assert probes.snapshot()["searxng"]["status"] == status


@pytest.mark.parametrize("answer,status", [(b'{"models": []}', "up"),
                                           (TimeoutError(), "down")])
def test_the_optional_verifier(answer, status):
    config = WorkerConfig(token="t" * 32, verifier_url="http://m1max:11434")
    probes = SystemProbes(config, run=smi(), opener=opener({
        "http://m1max:11434/api/tags": answer}))
    verifier = probes.snapshot()["verifier"]
    assert verifier == {"status": status, "models": {
        "research": "bespoke-minicheck", "review": "gemma3:27b-it-qat"}}


def test_a_failing_nvidia_smi_is_unknown_not_fatal():
    probes = SystemProbes(CONFIG, run=smi("", returncode=9), opener=opener({}))
    assert probes.snapshot()["gpu"]["vram_total_mb"] is None


# -- configuration -----------------------------------------------------------


@pytest.mark.parametrize("environ,complaint", [
    ({}, "WORKER_TOKEN is required"),
    ({"WORKER_TOKEN": "changeme"}, "at least 16"),
    ({"WORKER_TOKEN": "t" * 32, "QUEUE_MAX": "lots"}, "integer"),
    ({"WORKER_TOKEN": "t" * 32, "RESULT_TTL_HOURS": "0"}, "at least 1"),
])
def test_bad_settings_stop_the_worker_at_startup(environ, complaint):
    with pytest.raises(RuntimeError, match=complaint):
        config_from_env(environ)


def test_settings_from_the_environment():
    config = config_from_env({
        "WORKER_TOKEN": "t" * 32, "OLLAMA_URL": "http://127.0.0.1:11434/",
        "QUEUE_MAX": "5", "VERIFIER_URL": "  ", "RESEARCH_MODEL": "qwen3:32b"})
    assert config.ollama_url == "http://127.0.0.1:11434"
    assert config.queue_max == 5
    assert config.verifier_url is None
    assert config.research_model == "qwen3:32b"
    assert config.review_model == "qwen3:30b"
