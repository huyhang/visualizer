"""Production entrypoint: ``gunicorn -w 1 visualizer.gpu_worker.wsgi:application``.

**Exactly one gunicorn worker process.** Each process starts its own runner
thread, and two runners would put two jobs on the GPU at once -- the one thing
the queue exists to prevent. Concurrency for HTTP comes from ``--threads``.
"""

import logging
from datetime import UTC, datetime, timedelta

from .app import create_app
from .config import config_from_env
from .contract import Contract
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
    runner = Runner(store, NotBuiltPipelines(), contract)
    runner.start()
    return create_app(config, store, runner, SystemProbes(config), contract)


application = build()
