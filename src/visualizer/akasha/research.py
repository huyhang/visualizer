"""Delegated research: Akasha asks, the GPU box researches, Akasha decides.

``Researcher`` is the seam, shaped like Logos's ``WritingAdvisor``: injected
into the app factory, with a default that keeps the NAS-only stack exactly as
it was. Akasha never fetches a web page and never talks to a model; it submits
a question to the worker on the GPU box and, later, imports what comes back
into a research inbox as unverified drafts -- nothing becomes canon without the
writer accepting it.

So far this is the plumbing: availability, and the job calls the inbox will be
built on. The worker's contract is ``docs/gpu_worker/``.
"""

from typing import Protocol

from visualizer.gpubox import (
    WorkerBusy,
    WorkerError,
    WorkerJobNotFound,
    availability,
)

from .errors import ResearchBusy, ResearchJobNotFound, ResearchUnavailable


class Researcher(Protocol):
    """Runs research jobs somewhere else and reports on them; never writes canon."""

    # True only when the models run on hardware the writer controls.
    private: bool

    def availability(self) -> dict:
        """Whether research can be requested right now, and what to tell the writer."""

    def submit(self, request: dict, ref: str) -> dict:
        """Queue a research job; ``ref`` is Akasha's own job id. Returns the job."""

    def status(self, job_id: str) -> dict:
        """The job as it stands: queued, running (with its stage), or finished."""

    def cancel(self, job_id: str) -> dict:
        """Stop a queued or running job. Finished jobs come back unchanged."""


class UnavailableResearcher:
    """The default: no GPU box, so research is off and says so."""

    private = True

    def availability(self) -> dict:
        return availability(None, "research")

    def submit(self, request: dict, ref: str) -> dict:
        raise self._off()

    def status(self, job_id: str) -> dict:
        raise self._off()

    def cancel(self, job_id: str) -> dict:
        raise self._off()

    @staticmethod
    def _off() -> ResearchUnavailable:
        return ResearchUnavailable("Research is off: no GPU box is configured.")


class RemoteResearcher:
    """Research on the GPU-box worker, through the stack's shared client.

    ``worker`` is a ``visualizer.gpubox.WorkerClient`` in production, or its
    ``FakeWorker`` in tests and on the dev server.
    """

    private = True  # the worker's models run on our own hardware

    def __init__(self, worker):
        self.worker = worker

    def availability(self) -> dict:
        return availability(self.worker, "research")

    def submit(self, request: dict, ref: str) -> dict:
        return self._ask(self.worker.submit, "research", request,
                         service="akasha", ref=ref)

    def status(self, job_id: str) -> dict:
        return self._ask(self.worker.status, job_id)

    def cancel(self, job_id: str) -> dict:
        return self._ask(self.worker.cancel, job_id)

    @staticmethod
    def _ask(call, *args, **kwargs) -> dict:
        """One worker call, its failures restated in Akasha's own errors."""
        try:
            return call(*args, **kwargs)
        except WorkerBusy as err:
            raise ResearchBusy(err.message, retry_after=err.retry_after) from err
        except WorkerJobNotFound as err:
            raise ResearchJobNotFound(err.message) from err
        except WorkerError as err:
            # Unreachable, a dependency down, or a request the box refused (a bad
            # token, a bug): to the writer all of them mean "not right now", and
            # /research/availability says which.
            raise ResearchUnavailable(err.message) from err
