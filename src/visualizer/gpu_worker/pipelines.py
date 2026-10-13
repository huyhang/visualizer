"""What a pipeline is, and the ones the worker ships with today.

A pipeline turns one job's request into one result. It reports progress through
the ``JobContext`` it is given -- which is also where cancellation and the time
limit reach it, as ``Cancelled`` / ``TimedOut`` raised from ``progress()`` -- and
signals the two expected failures with the exceptions below. Anything else it
raises becomes a generic ``internal`` failure.

Exception messages are shown to the writer and written to logs, so they must
never contain request or result content -- say *what* failed, not *on what*.
"""

from typing import Protocol


class PipelineUnavailable(Exception):
    """A dependency (Ollama, SearXNG, the verifier when required) stopped mid-job."""


class NoSources(Exception):
    """Research found nothing it could use."""


class NotBuilt(Exception):
    """This kind of job has no pipeline yet."""


class JobContext(Protocol):
    def progress(self, stage: str, message: str | None = None) -> None:
        """Report a stage; raises if the job was cancelled or ran out of time."""


class Pipelines(Protocol):
    def research(self, request: dict, ctx: JobContext) -> dict:
        """A ``ResearchResult`` for a ``ResearchRequest``."""

    def review(self, request: dict, ctx: JobContext) -> dict:
        """A ``ReviewResult`` for a ``ReviewRequest``."""


class NotBuiltPipelines:
    """Today's pipelines: every job fails, honestly, saying it isn't built yet.

    The API, queue and health checks around them are real, so the box can be
    deployed and the stack's side tested end to end before research exists.
    """

    def research(self, request: dict, ctx: JobContext) -> dict:
        ctx.progress("planning")
        raise NotBuilt("The research pipeline is not built yet")

    def review(self, request: dict, ctx: JobContext) -> dict:
        ctx.progress("reviewing")
        raise NotBuilt("The review pipeline is not built yet")
