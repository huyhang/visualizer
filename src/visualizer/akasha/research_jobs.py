"""Research job records, in the reserved ``_research`` database.

One record per question asked: who asked, in which world, how the box is
getting on, and -- once the result is imported -- which draft it became and
the nested detail an Akasha document cannot hold (facts with their
second-check verdicts, dropped facts, image candidates and their signed fetch
tokens). The record outlives the box's copy of the result, which expires.

The ``_research`` name is reserved like ``_auth``: Akasha's document API
refuses every database whose name starts with an underscore.
"""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime

ACTIVE = ("submitting", "queued", "running", "importing")


class ResearchJobStore:
    def __init__(self, client, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._jobs = client["_research"]["jobs"]
        self._clock = clock
        self._jobs.create_index([("world", 1), ("created_at", -1)])
        self._jobs.create_index([("world", 1), ("draft", 1)])
        self._jobs.create_index([("state", 1), ("requester", 1)])

    def _now(self) -> str:
        return self._clock().isoformat()

    def create(self, *, world: str, requester: str, question: str, request: dict) -> dict:
        now = self._now()
        record = {"_id": "rj_" + secrets.token_hex(8), "world": world,
                  "requester": requester, "question": question, "request": request,
                  "state": "submitting", "worker_job": None, "progress": None,
                  "error": None, "created_at": now, "updated_at": now,
                  "draft": None, "details": None, "review": None, "accepted": None}
        self._jobs.insert_one(record)
        return record

    def get(self, world: str, job_id: str) -> dict | None:
        return self._jobs.find_one({"_id": job_id, "world": world})

    def by_draft(self, world: str, draft: str) -> dict | None:
        return self._jobs.find_one({"world": world, "draft": draft})

    def recent(self, world: str, limit: int = 50) -> list[dict]:
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
            {"_id": job_id, "state": {"$in": ["queued", "running"]}},
            {"$set": {"state": "importing", "updated_at": self._now()}})
        return claimed.modified_count == 1

    def count_active(self, requester: str | None = None) -> int:
        query = {"state": {"$in": list(ACTIVE)}}
        if requester is not None:
            query["requester"] = requester
        return self._jobs.count_documents(query)

    def delete(self, job_id: str) -> None:
        self._jobs.delete_one({"_id": job_id})

    def mark_image_imported(self, job_id: str, index: int, media_id: str) -> None:
        self._jobs.update_one({"_id": job_id},
                              {"$set": {f"details.images.{index}.imported": media_id,
                                        "updated_at": self._now()}})
