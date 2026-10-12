"""What can go wrong talking to the GPU-box worker, as the stack sees it.

The worker's error ``code``s (see ``docs/gpu_worker/README.md``) collapse into
four outcomes a caller acts on differently: try again later, wait for the
queue, give up on a job, or fix a bug. Plain exceptions rather than a service's
domain errors: Akasha and Logos each translate them into their own, with their
own HTTP status and wording.
"""


class WorkerError(Exception):
    """Anything that went wrong reaching or using the worker."""

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


class WorkerUnavailable(WorkerError):
    """The box is asleep or unreachable, timed out, or a dependency is down.

    Always worth retrying later. Network failures and malformed replies land
    here too: from the caller's side they mean the same thing.
    """


class WorkerBusy(WorkerError):
    """The worker's queue is full."""

    def __init__(self, message: str, *, code: str | None = None,
                 retry_after: int | None = None):
        super().__init__(message, code=code)
        self.retry_after = retry_after


class WorkerJobNotFound(WorkerError):
    """The job is unknown to the worker -- never created, or its result expired."""


class WorkerRejected(WorkerError):
    """The worker refused the request: a bad token, or a bug on our side.

    Never retried. A 401 means ``GPU_WORKER_TOKEN`` does not match the box; the
    other codes mean the stack sent something the contract does not allow.
    """


# Every code the worker's API can answer an HTTP request with. A job that
# *fails* carries one of JOB_FAILURE_CODES inside the job instead -- those are
# a job's outcome, read from ``status()``, not an error raised by the call.
ERRORS_BY_CODE: dict[str, type[WorkerError]] = {
    "invalid_request": WorkerRejected,
    "unauthorized": WorkerRejected,
    "not_found": WorkerJobNotFound,
    "idempotency_conflict": WorkerRejected,
    "payload_too_large": WorkerRejected,
    "queue_full": WorkerBusy,
    "unavailable": WorkerUnavailable,
}
JOB_FAILURE_CODES = frozenset({"timeout", "unavailable", "no_sources", "internal"})
