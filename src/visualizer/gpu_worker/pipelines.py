"""What a pipeline is: the protocol, its context, its expected failures.

A pipeline turns one job's request into one result. It reports progress through
the ``JobContext`` it is given -- which is also where cancellation and the time
limit reach it, as ``Cancelled`` / ``TimedOut`` raised from ``progress()`` -- and
signals the expected failures with the exceptions below, each of which the
runner records under its own code. Anything else it raises becomes a generic
``internal`` failure.

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


class ModelOutputError(Exception):
    """The model answered, but not in the shape it was asked for, even on retry."""


class AwaitingApproval(Exception):
    """Research planned and was asked to stop there: ``plan`` awaits the caller.

    Not a failure. The runner parks the job in ``awaiting_approval``; approving
    queues it again with the queries in its request, and the pipeline starts
    over from searching.
    """

    def __init__(self, plan: dict):
        super().__init__("The plan awaits approval")
        self.plan = plan


class JobContext(Protocol):
    def progress(self, stage: str, message: str | None = None) -> None:
        """Report a stage; raises if the job was cancelled or ran out of time."""


class Pipelines(Protocol):
    def research(self, request: dict, ctx: JobContext) -> dict:
        """A ``ResearchResult`` for a ``ResearchRequest``."""

    def review(self, request: dict, ctx: JobContext) -> dict:
        """A ``ReviewResult`` for a ``ReviewRequest``."""

    def discussion(self, request: dict, ctx: JobContext) -> dict:
        """A ``DiscussionResult`` for a ``DiscussionRequest``."""


class NotBuiltPipelines:
    """Every job fails, honestly, saying it isn't built: a placeholder for tests
    that exercise the worker around its pipelines, not the pipelines themselves.
    """

    def research(self, request: dict, ctx: JobContext) -> dict:
        ctx.progress("planning")
        raise NotBuilt("The research pipeline is not built yet")

    def review(self, request: dict, ctx: JobContext) -> dict:
        ctx.progress("reviewing")
        raise NotBuilt("The review pipeline is not built yet")

    def discussion(self, request: dict, ctx: JobContext) -> dict:
        ctx.progress("replying")
        raise NotBuilt("The discussion pipeline is not built yet")
