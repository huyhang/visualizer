"""Production entrypoint: ``gunicorn -w 1 visualizer.gpu_worker.wsgi:application``.

**Exactly one gunicorn worker process.** Each process starts its own runner
thread, and two runners would put two jobs on the GPU at once -- the one thing
the queue exists to prevent. Concurrency for HTTP comes from ``--threads``.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .app import create_app
from .config import config_from_env
from .contract import Contract
from .fetch import Fetcher
from .images import Images, TokenSigner, load_signing_key
from .pipelines import NotBuiltPipelines
from .probes import SystemProbes
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
    runner = Runner(store, NotBuiltPipelines(), contract, sign=signer.sign)
    runner.start()
    return create_app(config, store, runner, SystemProbes(config), contract, images)


application = build()
