"""What the stack tells a writer about the GPU box, for every state it can be in."""

import copy

import pytest

from visualizer.gpubox import (
    STATES,
    SUBMITTABLE,
    WorkerRejected,
    WorkerUnavailable,
    availability,
    describe,
)

from .spec import SPEC

EXAMPLES = SPEC["paths"]["/health"]["get"]["responses"]["200"]["content"][
    "application/json"]["examples"]
HEALTHY = EXAMPLES["healthy"]["value"]


def health(**changes):
    """The documented healthy report, with dotted-path overrides."""
    report = copy.deepcopy(HEALTHY)
    for path, value in changes.items():
        node = report
        *parents, leaf = path.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return report


class Worker:
    def __init__(self, result):
        self.result = result

    def health(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize("report,kind,state", [
    (health(), "research", "cold"),     # nothing loaded in the documented example
    (health(ollama__loaded=["qwen3:30b"]), "research", "ready"),
    (health(ollama__loaded=["qwen3:30b"]), "review", "ready"),
    (health(gpu__busy=True), "research", "busy"),
    (health(queue__queued=20, queue__max=20), "research", "queue_full"),
    (health(gpu__busy=True, queue__queued=20), "research", "queue_full"),
    (health(searxng__status="down", ok=False), "research", "degraded"),
    (health(searxng__status="down", ok=False), "review", "cold"),
    (health(ollama__status="down", ok=False), "review", "degraded"),
    (health(api_version="2"), "research", "incompatible"),
])
def test_each_report_reads_as_one_state(report, kind, state):
    assert describe(report, kind)["state"] == state


def test_research_needs_search_but_review_does_not():
    report = health(searxng__status="down", ok=False)
    assert "SearXNG" in describe(report, "research")["message"]
    assert describe(report, "review")["can_submit"]


def test_every_missing_dependency_is_named():
    report = health(ollama__status="down", searxng__status="down", ok=False)
    message = describe(report, "research")["message"]
    assert "Ollama" in message and "SearXNG" in message and "are down" in message


def test_a_report_that_is_not_one_is_incompatible():
    assert describe("<html>", "research")["state"] == "incompatible"


def test_unknown_job_kinds_are_a_bug():
    with pytest.raises(ValueError):
        describe(HEALTHY, "portraits")


@pytest.mark.parametrize("worker,state", [
    (None, "off"),
    (Worker(WorkerUnavailable("asleep")), "unreachable"),
    (Worker(WorkerRejected("bad token", code="unauthorized")), "misconfigured"),
    (Worker(HEALTHY), "cold"),
])
def test_asking_the_box(worker, state):
    assert availability(worker, "research")["state"] == state


def test_the_second_checker_and_model_are_reported():
    asleep = EXAMPLES["macAsleep"]["value"]
    answer = describe(asleep, "research")
    assert answer["verifier"] == "down"
    assert answer["model"] == asleep["ollama"]["models"]["research"]
    assert answer["can_submit"], "the Mac is optional; its absence blocks nothing"


@pytest.mark.parametrize("report", [
    health(), health(gpu__busy=True), health(api_version="9"),
    health(ollama__status="down", ok=False),
    health(queue__queued=99, queue__max=1),
])
def test_every_answer_has_the_same_shape(report):
    for kind in ("research", "review"):
        answer = describe(report, kind)
        assert set(answer) == {"state", "can_submit", "message", "model", "verifier"}
        assert answer["state"] in STATES
        assert answer["can_submit"] is (answer["state"] in SUBMITTABLE)
        assert answer["message"]
