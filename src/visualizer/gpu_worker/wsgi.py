"""Production entrypoint: ``gunicorn -w 1 visualizer.gpu_worker.wsgi:application``.

**Exactly one gunicorn worker process.** Each process starts its own runner
thread, and two runners would put two jobs on the GPU at once -- the one thing
the queue exists to prevent. Concurrency for HTTP comes from ``--threads``.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .app import create_app
from .config import WorkerConfig, config_from_env
from .contract import Contract
from .fetch import Fetcher
from .images import Images, TokenSigner, load_signing_key
from .models import OllamaClient, SearxClient, Verifier
from .probes import SystemProbes
from .research import ResearchPipeline
from .review import ReviewPipeline
from .runner import Runner
from .store import JobStore


def build():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = config_from_env()
    contract = Contract(config.contract_path)
    store = JobStore(config.db_path, ttl=timedelta(hours=config.result_ttl_hours))
    store.recover(datetime.now(UTC))
    signer = TokenSigner(load_signing_key(
        config.signing_key, Path(config.db_path).parent / "signing.key"))
    fetcher = Fetcher(timeout=config.fetch_timeout, max_bytes=config.fetch_max_bytes)
    images = Images(signer, fetcher, config.image_max_bytes)
    runner = Runner(store, build_pipelines(config, fetcher), contract, sign=signer.sign)
    runner.start()
    return create_app(config, store, runner, SystemProbes(config), contract, images)


class LocalPipelines:
    """Research and review, on the box's own models."""

    def __init__(self, research: ResearchPipeline, review: ReviewPipeline):
        self._research = research
        self._review = review

    def research(self, request, ctx):
        return self._research.run(request, ctx)

    def review(self, request, ctx):
        return self._review.run(request, ctx)


def build_pipelines(config: WorkerConfig, fetcher: Fetcher) -> LocalPipelines:
    ollama = OllamaClient(config.ollama_url, timeout=config.llm_timeout,
                          num_ctx=config.num_ctx)
    verifier = None
    if config.verifier_url:
        verifier = Verifier(
            OllamaClient(config.verifier_url, timeout=config.verifier_timeout,
                         num_ctx=config.num_ctx, name="the second checker"),
            config.verifier_research_model, config.verifier_review_model)
    search = SearxClient(config.searxng_url, timeout=config.fetch_timeout)
    return LocalPipelines(
        ResearchPipeline(ollama, search, fetcher, verifier, model=config.research_model),
        ReviewPipeline(ollama, verifier, model=config.review_model))


application = build()
