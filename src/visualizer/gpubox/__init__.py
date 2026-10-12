"""The stack's side of the GPU box: a client for the AI worker that runs there.

The worker itself is a separate program on the RTX 3090 box (its contract is
``docs/gpu_worker/``). This package is everything the NAS stack needs to use
it -- configuration, the HTTP client, error mapping and the "is it awake?"
check -- shared by every service that submits jobs, so none of them talks HTTP
to the box itself.
"""

from .availability import STATES, SUBMITTABLE, availability, describe
from .client import WorkerClient, WorkerConfig, worker_config_from_env, worker_from_env
from .errors import (
    ERRORS_BY_CODE,
    JOB_FAILURE_CODES,
    WorkerBusy,
    WorkerError,
    WorkerJobNotFound,
    WorkerRejected,
    WorkerUnavailable,
)

__all__ = [
    "ERRORS_BY_CODE",
    "JOB_FAILURE_CODES",
    "STATES",
    "SUBMITTABLE",
    "WorkerBusy",
    "WorkerClient",
    "WorkerConfig",
    "WorkerError",
    "WorkerJobNotFound",
    "WorkerRejected",
    "WorkerUnavailable",
    "availability",
    "describe",
    "worker_config_from_env",
    "worker_from_env",
]
