"""Runs queued jobs one at a time, because the box has one GPU.

A single background thread claims the oldest queued job, hands it to its
pipeline, and records how it ended. Two promises from the contract are kept
here rather than trusted to each pipeline:

- **the result fits the contract** -- one that doesn't fails the job instead of
  reaching a caller;
- **review quotes are real** -- an issue whose ``quote`` is not verbatim in the
  block it names is dropped, as the API documentation says;
- **image candidates are signed** -- every one gets its ``fetch_token`` here,
  overwriting anything a pipeline set, so none can go out unsigned or forged.

Only job metadata is ever logged: id, kind, outcome and timing.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .contract import Contract
from .pipelines import (
    AwaitingApproval,
    ModelOutputError,
    NoSources,
    NotBuilt,
    Pipelines,
    PipelineUnavailable,
)
from .store import JobStore

LOG = logging.getLogger("visualizer.gpu_worker")

TIME_LIMITS = {"research": timedelta(minutes=15), "review": timedelta(minutes=5),
               "discussion": timedelta(minutes=2)}
SWEEP_EVERY = timedelta(minutes=1)


class Cancelled(Exception):
    """The job was cancelled while its pipeline ran."""


class TimedOut(Exception):
    """The job ran past its time limit."""


class Context:
    """What a running pipeline sees of its job."""

    def __init__(self, store: JobStore, job_id: str, deadline: datetime,
                 clock: Callable[[], datetime]):
        self._store = store
        self._job_id = job_id
        self._deadline = deadline
        self._clock = clock

    def progress(self, stage: str, message: str | None = None) -> None:
        self.check()
        self._store.set_progress(self._job_id, stage, message)

    def check(self) -> None:
        if self._store.state(self._job_id) == "cancelled":
            raise Cancelled()
        if self._clock() >= self._deadline:
            raise TimedOut()


def _failure(code: str, message: str, retryable: bool) -> dict:
    return {"code": code, "message": message, "retryable": retryable}


class Runner:
    def __init__(self, store: JobStore, pipelines: Pipelines, contract: Contract, *,
                 sign: Callable[[str], str],
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 poll_seconds: float = 2.0):
        self.store = store
        self.pipelines = pipelines
        self.contract = contract
        self._sign = sign
        self._clock = clock
        self._poll = poll_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sweep: datetime | None = None

    # -- the loop ------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="gpu-worker-runner",
                                        daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def wake(self) -> None:
        """A job was queued: don't wait out the poll interval."""
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sweep_if_due()
            if not self.run_next():
                self._wake.wait(self._poll)
                self._wake.clear()

    def _sweep_if_due(self) -> None:
        now = self._clock()
        if self._last_sweep is None or now - self._last_sweep >= SWEEP_EVERY:
            self.store.sweep(now)
            self._last_sweep = now

    # -- one job -------------------------------------------------------------

    def run_next(self) -> bool:
        """Run the oldest queued job to its end. False when there was none."""
        claimed = self.store.claim_next(self._clock())
        if claimed is None:
            return False
        job_id, kind, request = claimed
        started = self._clock()
        LOG.info("job %s started (kind=%s)", job_id, kind)
        ctx = Context(self.store, job_id, started + TIME_LIMITS[kind], self._clock)
        state, result, error = self._execute(kind, request, ctx)
        if state == "awaiting_approval":
            self.store.await_approval(job_id, result, self._clock())
        elif state is not None:
            self.store.finish(job_id, state, self._clock(), result=result, error=error)
        seconds = (self._clock() - started).total_seconds()
        LOG.info("job %s %s after %.1fs%s", job_id, state or "cancelled", seconds,
                 f" ({error['code']})" if error else "")
        return True

    def _execute(self, kind: str, request: dict, ctx: Context):
        """(state, result, error) -- state None when the job was cancelled.

        A job parked for approval comes back as ``awaiting_approval`` with its
        plan in place of a result.
        """
        try:
            result = getattr(self.pipelines, kind)(request, ctx)
            ctx.check()
        except Cancelled:
            return None, None, None
        except AwaitingApproval as parked:
            if self.contract.plan_problem(parked.plan) is not None:
                LOG.error("job pipeline proposed a plan outside the contract")
                return "failed", None, _failure(
                    "internal", "The pipeline proposed a plan outside the contract",
                    False)
            return "awaiting_approval", parked.plan, None
        except TimedOut:
            return "failed", None, _failure(
                "timeout", "The job exceeded its time limit", True)
        except PipelineUnavailable as err:
            return "failed", None, _failure("unavailable", str(err), True)
        except NoSources as err:
            return "failed", None, _failure(
                "no_sources", str(err) or "No usable sources were found", False)
        except (NotBuilt, ModelOutputError) as err:
            return "failed", None, _failure("internal", str(err), False)
        except Exception as err:  # noqa: BLE001 -- any pipeline bug ends the job
            # The type only: an exception's message could quote the request.
            LOG.error("job pipeline raised %s", type(err).__name__)
            return "failed", None, _failure(
                "internal", "The worker hit an unexpected error", False)
        if kind == "review":
            result = _drop_unanchored_issues(result, request)
        elif kind == "research":
            result = _signed_candidates(result, self._sign)
        if self.contract.result_problem(kind, result) is not None:
            LOG.error("job pipeline returned a result outside the contract")
            return "failed", None, _failure(
                "internal", "The pipeline produced a result outside the contract",
                False)
        return "done", result, None


def _signed_candidates(result, sign: Callable[[str], str]):
    """Give every image candidate a token for its own URL, and only that."""
    try:
        candidates = result["article"]["image_candidates"]
    except (KeyError, TypeError):
        return result   # malformed: the contract check will say so
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and isinstance(candidate.get("url"), str):
                candidate["fetch_token"] = sign(candidate["url"])
    return result


def _drop_unanchored_issues(result, request: dict):
    """Keep only review issues whose quote really is in the block they name."""
    if not isinstance(result, dict) or not isinstance(result.get("issues"), list):
        return result
    texts = {block["id"]: block["text"] for block in request["chapter"]["blocks"]}
    kept = [issue for issue in result["issues"]
            if isinstance(issue, dict) and issue.get("quote")
            and issue["quote"] in texts.get(issue.get("block"), "")]
    return {**result, "issues": kept}
