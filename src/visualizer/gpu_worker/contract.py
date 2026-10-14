"""The API contract, enforced at runtime by the worker that publishes it.

The worker validates what it is sent, and what its pipelines produce, against
``docs/gpu_worker/openapi.json`` itself rather than a hand-copied imitation, so
the two cannot drift. The document is found through ``WORKER_CONTRACT`` (set by
the Docker image) or, in a checkout, beside this package's repository root.

Messages name *where* a payload broke the contract and *which* rule -- never the
offending value, which may be a writer's unpublished prose.
"""

import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

_URI = "urn:visualizer:gpu-worker-openapi"
KINDS = ("research", "review", "discussion")


def default_contract_path() -> Path:
    configured = os.environ.get("WORKER_CONTRACT")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "docs" / "gpu_worker" / "openapi.json"


class Contract:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_contract_path()
        self.spec = json.loads(self.path.read_text())
        registry = Registry().with_resource(
            _URI, Resource(contents=self.spec, specification=DRAFT202012)
        )
        self._validators = {
            name: Draft202012Validator(
                {"$ref": f"{_URI}#/components/schemas/{name}"}, registry=registry
            )
            for name in ("ResearchJobCreate", "ReviewJobCreate",
                         "DiscussionJobCreate", "ResearchResult", "ReviewResult",
                         "DiscussionResult", "ImageFetch", "PlanApproval")
        }

    def job_problem(self, body) -> str | None:
        """Why a ``POST /jobs`` body breaks the contract, or None if it doesn't."""
        if not isinstance(body, dict):
            return "the body must be a JSON object"
        kind = body.get("kind")
        if kind not in KINDS:
            return "kind: must be 'research', 'review' or 'discussion'"
        return self._problem(f"{kind.capitalize()}JobCreate", body)

    def image_problem(self, body) -> str | None:
        """Why a ``POST /images`` body breaks the contract, or None."""
        return self._problem("ImageFetch", body)

    def plan_problem(self, body) -> str | None:
        """Why a plan -- approved by a caller, or proposed by a pipeline --
        breaks the contract, or None."""
        return self._problem("PlanApproval", body)

    def result_problem(self, kind: str, result) -> str | None:
        """Why a pipeline's result would break the contract, or None."""
        return self._problem(f"{kind.capitalize()}Result", result)

    def _problem(self, schema: str, payload) -> str | None:
        error = best_match(self._validators[schema].iter_errors(payload))
        if error is None:
            return None
        where = ".".join(str(part) for part in error.absolute_path) or "the body"
        return f"{where}: fails '{error.validator}'"
