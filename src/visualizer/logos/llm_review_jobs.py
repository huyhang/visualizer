"""LLM review records, beside the manuscript in Logos's own database.

One record per review asked for: which draft of which section, at which
revision, who asked and with what settings, which references were sent (refs
and titles -- never their text) and which were left out, how the box is getting
on, and finally the issues, each with the writer's status for it.

Nothing else from the manuscript is kept: the chapter goes to the box and is
not stored here, and the box erases it when the job ends. The issues' quotes
are the writer's own words, so these records go when the book does
(``LogosStore.purge_book``) and when their requester's account does
(``LogosStore.purge_user``), and only the newest ``KEEP_PER_SECTION`` finished
reviews of a section are kept.
"""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from .store import LLM_REVIEWS, LOGOS_DB

ACTIVE = ("submitting", "queued", "running", "importing")
REMOTE = ("queued", "running")
FINISHED = ("done", "failed", "cancelled")
KEEP_PER_SECTION = 10
ISSUE_STATUSES = ("open", "dismissed", "resolved")


class LlmReviewStore:
    def __init__(self, client, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._reviews = client[LOGOS_DB][LLM_REVIEWS]
        self._clock = clock
        self._reviews.create_index([("book", 1), ("volume", 1), ("section", 1),
                                    ("created_at", -1)])
        self._reviews.create_index([("state", 1), ("requester", 1)])

    def _now(self) -> str:
        return self._clock().isoformat()

    def create(self, *, book: str, volume: str, section: str, draft: str,
               draft_rev: int, requester: str, settings: dict,
               references: list[dict], skipped: list[dict]) -> dict:
        now = self._now()
        record = {"_id": "lr_" + secrets.token_hex(8), "book": book, "volume": volume,
                  "section": section, "draft": draft, "draft_rev": draft_rev,
                  "requester": requester, "settings": settings,
                  "references": references, "skipped": skipped,
                  "state": "submitting", "worker_job": None, "progress": None,
                  "error": None, "created_at": now, "updated_at": now,
                  "issues": None, "verification": None, "model": None,
                  "generated_at": None}
        self._reviews.insert_one(record)
        return record

    def get(self, book: str, volume: str, section: str, review_id: str) -> dict | None:
        return self._reviews.find_one({"_id": review_id, "book": book,
                                       "volume": volume, "section": section})

    def recent(self, book: str, volume: str, section: str) -> list[dict]:
        return list(self._reviews.find({"book": book, "volume": volume,
                                        "section": section})
                    .sort("created_at", -1).limit(KEEP_PER_SECTION + len(ACTIVE)))

    def update(self, review_id: str, **fields) -> dict:
        fields["updated_at"] = self._now()
        self._reviews.update_one({"_id": review_id}, {"$set": fields})
        return self._reviews.find_one({"_id": review_id})

    def claim_import(self, review_id: str) -> bool:
        """Move a review to ``importing`` -- true for exactly one caller."""
        claimed = self._reviews.update_one(
            {"_id": review_id, "state": {"$in": list(REMOTE)}},
            {"$set": {"state": "importing", "updated_at": self._now()}})
        return claimed.modified_count == 1

    def count_active(self, requester: str | None = None) -> int:
        query = {"state": {"$in": list(ACTIVE)}}
        if requester is not None:
            query["requester"] = requester
        return self._reviews.count_documents(query)

    def delete(self, review_id: str) -> None:
        self._reviews.delete_one({"_id": review_id})

    def set_issue_status(self, review_id: str, index: int, status: str) -> dict:
        return self.update(review_id, **{f"issues.{index}.status": status})

    def prune(self, book: str, volume: str, section: str) -> int:
        """Delete all but the newest ``KEEP_PER_SECTION`` finished reviews."""
        finished = self._reviews.find(
            {"book": book, "volume": volume, "section": section,
             "state": {"$in": list(FINISHED)}}, {"_id": 1}).sort("created_at", -1)
        stale = [record["_id"] for record in list(finished)[KEEP_PER_SECTION:]]
        if stale:
            self._reviews.delete_many({"_id": {"$in": stale}})
        return len(stale)
