"""The worker's settings, read from the environment once at startup.

The only module here that reads ``os.environ``; everything else is handed a
``WorkerConfig``. Names match ``docker/gpubox/worker.env.example``.
"""

import os
from dataclasses import dataclass

# A placeholder or a typo, not a secret: refuse it rather than run open.
MIN_TOKEN_LENGTH = 16


@dataclass(frozen=True)
class WorkerConfig:
    token: str
    db_path: str = "/data/jobs.sqlite3"
    contract_path: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    searxng_url: str = "http://127.0.0.1:8888"
    research_model: str = "qwen3:30b"
    review_model: str = "qwen3:30b"
    queue_max: int = 20
    result_ttl_hours: int = 24
    verifier_url: str | None = None
    verifier_research_model: str = "bespoke-minicheck"
    verifier_review_model: str = "gemma3:27b"
    # Health must answer within the stack's 2 s budget, so each probe gets less.
    probe_timeout: float = 1.5


def config_from_env(environ=os.environ) -> WorkerConfig:
    def text(name, default=None):
        value = (environ.get(name) or "").strip()
        return value or default

    def positive(name, default):
        raw = text(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            raise RuntimeError(f"{name} must be an integer, got {raw!r}.") from None
        if value < 1:
            raise RuntimeError(f"{name} must be at least 1.")
        return value

    token = text("WORKER_TOKEN")
    if token is None:
        raise RuntimeError("WORKER_TOKEN is required (openssl rand -hex 32).")
    if len(token) < MIN_TOKEN_LENGTH:
        raise RuntimeError(
            f"WORKER_TOKEN must be at least {MIN_TOKEN_LENGTH} characters."
        )
    defaults = WorkerConfig(token=token)
    return WorkerConfig(
        token=token,
        db_path=text("WORKER_DB", defaults.db_path),
        contract_path=text("WORKER_CONTRACT"),
        ollama_url=text("OLLAMA_URL", defaults.ollama_url).rstrip("/"),
        searxng_url=text("SEARXNG_URL", defaults.searxng_url).rstrip("/"),
        research_model=text("RESEARCH_MODEL", defaults.research_model),
        review_model=text("REVIEW_MODEL", defaults.review_model),
        queue_max=positive("QUEUE_MAX", defaults.queue_max),
        result_ttl_hours=positive("RESULT_TTL_HOURS", defaults.result_ttl_hours),
        verifier_url=(text("VERIFIER_URL") or "").rstrip("/") or None,
        verifier_research_model=text("VERIFIER_RESEARCH_MODEL",
                                     defaults.verifier_research_model),
        verifier_review_model=text("VERIFIER_REVIEW_MODEL",
                                   defaults.verifier_review_model),
    )
