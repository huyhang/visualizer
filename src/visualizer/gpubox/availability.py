"""Turn the worker's health report into what a "Research…" button should say.

Pure apart from the one ``health()`` call, and shared so that Akasha's research
button and Logos's review panel can never describe the same box differently.
The answer is deliberately small -- a state, whether submitting makes sense, a
sentence for the writer, and the two facts worth showing (which model, whether
results will be second-checked) -- not the box's VRAM figures.
"""

from .errors import WorkerError, WorkerRejected

API_VERSION = "1"

# In the order they are checked: the first that applies is the answer.
STATES = (
    "off",            # no GPU box configured at all
    "unreachable",    # asleep, powered off, or off the tailnet
    "misconfigured",  # the box refused our token
    "incompatible",   # the box speaks a different API version
    "degraded",       # a dependency this job kind needs is down
    "queue_full",     # nothing more can be queued right now
    "busy",           # the GPU is held by other work; jobs will wait
    "cold",           # ready, but the first job will load the model first
    "ready",
)
SUBMITTABLE = frozenset({"busy", "cold", "ready"})

# What each job kind needs from the box besides the worker itself.
_NEEDS = {"research": ("ollama", "searxng"), "review": ("ollama",)}
_DEPENDENCY_NAMES = {"ollama": "the model server (Ollama)",
                     "searxng": "web search (SearXNG)"}

_MESSAGES = {
    "off": "No GPU box is configured for this stack.",
    "unreachable": "The GPU box is asleep or unreachable.",
    "misconfigured": "The GPU box refused this stack's token; check GPU_WORKER_TOKEN.",
    "queue_full": "The GPU box's queue is full. Try again shortly.",
    "busy": "The GPU is busy with other work, such as image generation. "
            "A new job will wait its turn.",
    "cold": "Ready. The first job loads the model, so it starts 10–30 seconds later.",
    "ready": "Ready.",
}


def availability(worker, kind: str) -> dict:
    """Ask ``worker`` (None when unconfigured) whether ``kind`` jobs can run."""
    if worker is None:
        return _answer("off")
    try:
        health = worker.health()
    except WorkerRejected:
        return _answer("misconfigured")
    except WorkerError:
        return _answer("unreachable")
    return describe(health, kind)


def describe(health: dict, kind: str) -> dict:
    """The pure half: classify one health report for one job kind."""
    if kind not in _NEEDS:
        raise ValueError(f"Unknown job kind {kind!r}.")
    if not isinstance(health, dict) or health.get("api_version") != API_VERSION:
        version = health.get("api_version") if isinstance(health, dict) else None
        return _answer("incompatible", message=(
            f"The GPU box speaks API version {version!r}; this stack needs "
            f"{API_VERSION!r}."))

    model = (_section(health, "ollama").get("models") or {}).get(kind)
    verifier = _section(health, "verifier").get("status")
    extra = {"model": model, "verifier": verifier}

    down = [name for name in _NEEDS[kind]
            if _section(health, name).get("status") != "up"]
    if down:
        return _answer("degraded", message=(
            "On the GPU box, " + " and ".join(_DEPENDENCY_NAMES[n] for n in down)
            + (" is" if len(down) == 1 else " are") + " down."), **extra)

    queue = _section(health, "queue")
    if queue.get("queued", 0) >= queue.get("max", float("inf")):
        return _answer("queue_full", **extra)
    if _section(health, "gpu").get("busy"):
        return _answer("busy", **extra)
    if model not in (_section(health, "ollama").get("loaded") or []):
        return _answer("cold", **extra)
    return _answer("ready", **extra)


def _section(health: dict, name: str) -> dict:
    value = health.get(name)
    return value if isinstance(value, dict) else {}


def _answer(state: str, *, message: str | None = None, model: str | None = None,
            verifier: str | None = None) -> dict:
    return {
        "state": state,
        "can_submit": state in SUBMITTABLE,
        "message": message or _MESSAGES[state],
        "model": model,
        "verifier": verifier,
    }
