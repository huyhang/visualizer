"""Research job records, in the reserved ``_research`` database.

One record per question asked: who asked, in which world, how the box is
getting on, and -- once the result is imported -- which draft it became and
the nested detail an Akasha document cannot hold (facts with their
second-check verdicts, dropped facts, image candidates and their signed fetch
tokens). The record outlives the box's copy of the result, which expires.

A job asked from the studio's "Dig deeper" names the job it grew from as
its ``parent``, so a line of inquiry can be drawn as a tree; a refinement
inherits its draft's parent and so keeps that place. Saving material into a
note records the note on the job (``notes``), while the draft stays open.

A refinement is a job of its own with ``refines`` naming the draft it
revises; when it replaces that draft, the old job's review becomes
``superseded`` and ``superseded_by`` points at the new one. Several records
can name one draft slug over time, so ``by_draft`` reads the newest.

The ``_research`` name is reserved like ``_auth``: Akasha's document API
refuses every database whose name starts with an underscore.
"""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime

DEFAULT_RECENT = 50
MAX_RECENT = 200
ACTIVE = ("submitting", "queued", "running", "awaiting_approval", "importing")
# Whose state is the box's to report: worth asking about, and claimable for import.
REMOTE = ("queued", "running", "awaiting_approval")


class ResearchJobStore:
    def __init__(self, client, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._jobs = client["_research"]["jobs"]
        self._clock = clock
        self._jobs.create_index([("world", 1), ("created_at", -1)])
        self._jobs.create_index([("world", 1), ("draft", 1)])
        self._jobs.create_index([("state", 1), ("requester", 1)])

    def _now(self) -> str:
        return self._clock().isoformat()

    def create(self, *, world: str, requester: str, question: str, request: dict,
               refines: str | None = None, parent: str | None = None) -> dict:
        now = self._now()
        record = {"_id": "rj_" + secrets.token_hex(8), "world": world,
                  "requester": requester, "question": question, "request": request,
                  "state": "submitting", "worker_job": None, "progress": None,
                  "plan": None, "error": None, "created_at": now, "updated_at": now,
                  "draft": None, "details": None, "review": None, "accepted": None,
                  "refines": refines, "superseded_by": None, "parent": parent,
                  "notes": []}
        self._jobs.insert_one(record)
        return record

    def get(self, world: str, job_id: str) -> dict | None:
        return self._jobs.find_one({"_id": job_id, "world": world})

    def by_draft(self, world: str, draft: str) -> dict | None:
        """The newest job to have made ``draft``: slugs are reused once freed."""
        found = self._jobs.find({"world": world, "draft": draft}).sort(
            "created_at", -1).limit(1)
        return next(iter(found), None)

    def refining(self, world: str, draft: str) -> dict | None:
        """The refinement of ``draft`` still under way, if there is one."""
        return self._jobs.find_one({"world": world, "refines": draft,
                                    "state": {"$in": list(ACTIVE)}})

    def recent(self, world: str, limit: int = DEFAULT_RECENT) -> list[dict]:
        return list(self._jobs.find({"world": world}).sort("created_at", -1).limit(limit))

    def pending_review(self, world: str) -> list[dict]:
        return list(self._jobs.find({"world": world, "review": "pending"})
                    .sort("created_at", -1))

    def update(self, job_id: str, **fields) -> dict:
        fields["updated_at"] = self._now()
        self._jobs.update_one({"_id": job_id}, {"$set": fields})
        return self._jobs.find_one({"_id": job_id})

    def claim_import(self, job_id: str) -> bool:
        """Move a job to ``importing`` -- true for exactly one caller.

        Two browser tabs polling the same finished job would otherwise both
        import it and leave two drafts.
        """
        claimed = self._jobs.update_one(
            {"_id": job_id, "state": {"$in": list(REMOTE)}},
            {"$set": {"state": "importing", "updated_at": self._now()}})
        return claimed.modified_count == 1

    def count_active(self, requester: str | None = None) -> int:
        query = {"state": {"$in": list(ACTIVE)}}
        if requester is not None:
            query["requester"] = requester
        return self._jobs.count_documents(query)

    def delete(self, job_id: str) -> None:
        self._jobs.delete_one({"_id": job_id})

    def add_note(self, job_id: str, note: str) -> None:
        """Record that material from this job's draft went into ``note``."""
        self._jobs.update_one({"_id": job_id},
                              {"$addToSet": {"notes": note},
                               "$set": {"updated_at": self._now()}})

    def mark_image_imported(self, job_id: str, index: int, media_id: str) -> None:
        self._jobs.update_one({"_id": job_id},
                              {"$set": {f"details.images.{index}.imported": media_id,
                                        "updated_at": self._now()}})
