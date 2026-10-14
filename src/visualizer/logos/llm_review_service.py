"""LLM review, end to end on Logos's side: ask, follow, work through the issues.

    references -> what a review of this draft would send, and leave out
    submit     -> a review record, and the chapter sent to the GPU box
    refresh    -> the box's progress; when it is done, its issues stored
                  (once, however many tabs poll)
    set_status -> an issue marked open, dismissed or resolved

Issues are presented against the draft as it is *now*: one whose block is gone,
or whose quote is no longer in its block, is ``stale`` -- the writer has
already changed what it was about -- and a review of an older revision says
it is ``outdated``. An issue the writer dismissed in an earlier review of the
section starts out dismissed, saying so (``dismissed_before``). Routes
authorise; this module assumes they have.
"""

import json

from .errors import (
    InvalidReviewRequest,
    LlmReviewBusy,
    LlmReviewNotFound,
    LlmReviewUnavailable,
    LogosError,
)
from .llm_review import (
    CHECKS,
    Reviewer,
    assemble_references,
    validate_review_request,
)
from .llm_review_jobs import ISSUE_STATUSES, REMOTE, LlmReviewStore
from .richtext import article_refs, block_text

MAX_ACTIVE_PER_WRITER = 3
MAX_ACTIVE = 10
# The worker refuses review requests over 1 MB; leave room for the envelope.
MAX_REQUEST_BYTES = 1024 * 1024 - 4096
TITLES = {"continuity": "Continuity", "anachronism": "Possible anachronism",
          "prose": "Prose"}


class MalformedResult(Exception):
    """The box's review result does not have the shape the contract promises."""


def _local_state(remote_state: str) -> str:
    """"done" here means the issues are stored, so a job the box has finished
    stays running until a poll stores them."""
    return remote_state if remote_state in REMOTE else "running"


class LlmReviewService:
    def __init__(self, manuscripts, sections, drafts, articles, auth_store,
                 reviewer: Reviewer, reviews: LlmReviewStore | None):
        self.manuscripts = manuscripts
        self.sections = sections
        self.drafts = drafts
        self.articles = articles
        self.auth_store = auth_store
        self.reviewer = reviewer
        self.reviews = reviews

    # -- asking ----------------------------------------------------------------

    def references(self, book: str, volume: str, section: str, writer: str,
                   payload) -> dict:
        """What a review would send besides the chapter: nothing is submitted."""
        settings = validate_review_request(payload)
        target = self._target(book, volume, section, settings["draft"], writer)
        sent, skipped = self._references(book, target, writer, settings)
        return {"draft": target["draft"], "draft_rev": target["rev"],
                "references": [{k: r[k] for k in ("ref", "kind", "title")}
                               | {"chars": len(r["text"])} for r in sent],
                "skipped": skipped}

    def submit(self, book: str, volume: str, section: str, writer: str,
               payload) -> dict:
        settings = validate_review_request(payload)
        reviews = self._reviews()
        target = self._target(book, volume, section, settings["draft"], writer)
        blocks = [{"id": block["id"], "text": text}
                  for block in target["document"].get("content", [])
                  if (text := block_text(block)).strip()]
        if not blocks:
            raise InvalidReviewRequest("Nothing to review: this draft has no text.")
        if reviews.count_active(writer) >= MAX_ACTIVE_PER_WRITER:
            raise LlmReviewBusy(f"You already have {MAX_ACTIVE_PER_WRITER} reviews "
                                "running. Wait for one to finish.", retry_after=60)
        if reviews.count_active() >= MAX_ACTIVE:
            raise LlmReviewBusy("Too many reviews are running. Try again shortly.",
                                retry_after=60)
        sent, skipped = self._references(book, target, writer, settings)
        request = {"chapter": {"title": target["title"][:300], "blocks": blocks},
                   "references": sent, "dialect": settings["dialect"],
                   "checks": settings["checks"], "verify": settings["verify"]}
        if len(json.dumps(request).encode()) > MAX_REQUEST_BYTES:
            raise InvalidReviewRequest(
                "This chapter is too long to review in one go; split it.")
        record = reviews.create(
            book=book, volume=volume, section=section, draft=target["draft"],
            draft_rev=target["rev"], requester=writer,
            settings={k: settings[k] for k in ("checks", "dialect", "verify")},
            references=[{k: r[k] for k in ("ref", "kind", "title")} for r in sent],
            skipped=skipped)
        try:
            remote = self.reviewer.submit(request, record["_id"])
        except Exception:
            # Nothing reached the box (or it refused): leave no review behind.
            reviews.delete(record["_id"])
            raise
        record = reviews.update(record["_id"], state=_local_state(remote["state"]),
                                worker_job=remote["id"],
                                progress=remote.get("progress"))
        return self._view(record, target)

    # -- following -------------------------------------------------------------

    def refresh(self, book: str, volume: str, section: str, review_id: str,
                writer: str) -> dict:
        """The review as it stands, asking the box if it is still running."""
        record = self._record(book, volume, section, review_id)
        if record["state"] in REMOTE:
            record = self._poll(record)
        return self._view(record, self._current(record, writer))

    def _poll(self, record: dict) -> dict:
        reviews = self._reviews()
        try:
            remote = self.reviewer.status(record["worker_job"])
        except LlmReviewNotFound:
            return self._fail(record, "expired", "The GPU box no longer has this "
                              "review; its result expired before it was stored.")
        except (LlmReviewUnavailable, LlmReviewBusy):
            return record      # asleep or busy: report what we last knew
        state = remote["state"]
        if state in REMOTE:
            return reviews.update(record["_id"], state=state,
                                  progress=remote.get("progress"))
        if state == "failed":
            error = remote.get("error") or {}
            return self._fail(record, error.get("code", "internal"),
                              error.get("message", "The review failed."))
        if state == "cancelled":
            return reviews.update(record["_id"], state="cancelled", progress=None)
        if not reviews.claim_import(record["_id"]):
            return reviews.update(record["_id"])   # another request is storing it
        try:
            issues = _issues(remote.get("result"))
        except MalformedResult:
            return self._fail(record, "invalid_result",
                              "The GPU box sent a malformed review.")
        _carry_dismissals(issues, reviews.dismissed(record["book"], record["volume"],
                                                    record["section"]))
        result = remote["result"]
        stored = reviews.update(
            record["_id"], state="done", progress=None, issues=issues,
            verification=_verification(result.get("verification")),
            model=str(result.get("model") or "")[:100] or None,
            generated_at=str(result.get("generated_at") or "")[:40] or None)
        reviews.prune(record["book"], record["volume"], record["section"])
        return stored

    def cancel(self, book: str, volume: str, section: str, review_id: str,
               writer: str) -> dict:
        record = self._record(book, volume, section, review_id)
        if record["state"] in REMOTE:
            try:
                self.reviewer.cancel(record["worker_job"])
            except LlmReviewNotFound:
                pass
            record = self._reviews().update(record["_id"], state="cancelled",
                                            progress=None)
        return self._view(record, self._current(record, writer))

    def recent(self, book: str, volume: str, section: str, writer: str) -> list[dict]:
        self.sections.get(book, volume, section)     # 404 for a missing section
        return [self._summary(record) for record in
                self._reviews().recent(book, volume, section)]

    # -- working through the issues --------------------------------------------

    def set_status(self, book: str, volume: str, section: str, review_id: str,
                   issue_id: str, writer: str, payload) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"status"} \
                or payload["status"] not in ISSUE_STATUSES:
            raise InvalidReviewRequest(
                f"Set an issue's status to one of {', '.join(ISSUE_STATUSES)}.")
        record = self._record(book, volume, section, review_id)
        index = next((n for n, issue in enumerate(record.get("issues") or [])
                      if issue["id"] == issue_id), None)
        if index is None:
            raise LlmReviewNotFound(f"This review has no issue '{issue_id}'.")
        record = self._reviews().set_issue_status(record["_id"], index,
                                                  payload["status"])
        current = self._current(record, writer)
        return _issue_view(record["issues"][index], current)

    # -- plumbing --------------------------------------------------------------

    def _reviews(self) -> LlmReviewStore:
        if self.reviews is None:
            raise LlmReviewUnavailable("LLM review is not set up on this Logos.")
        return self.reviews

    def _record(self, book: str, volume: str, section: str, review_id: str) -> dict:
        record = self._reviews().get(book, volume, section, review_id)
        if record is None:
            raise LlmReviewNotFound(f"No review '{review_id}' of this section.")
        return record

    def _fail(self, record: dict, code: str, message: str) -> dict:
        return self._reviews().update(record["_id"], state="failed", progress=None,
                                      error={"code": code, "message": message})

    def _target(self, book: str, volume: str, section: str, draft: str | None,
                writer: str) -> dict:
        """The draft to review (the primary by default), with what describes it."""
        current = self.sections.get(book, volume, section)
        draft_id = draft or current["primary_draft_id"]
        found = self.drafts.get(book, volume, section, draft_id, writer)
        title = current.get("title") or current["kind"].title()
        return {"draft": draft_id, "rev": found["rev"], "document": found["document"],
                "title": title}

    def _current(self, record: dict, writer: str) -> dict | None:
        """The reviewed draft as it is now, or None if it is gone."""
        try:
            return self._target(record["book"], record["volume"], record["section"],
                                record["draft"], writer)
        except LogosError:   # deleted since: every issue is then stale
            return None

    def _references(self, book: str, target: dict, writer: str, settings: dict):
        world = self.manuscripts.require(book).get("world")
        return assemble_references(
            self.articles, self.auth_store.grants_for(writer), world,
            article_refs(target["document"]), settings["include"])

    def _summary(self, record: dict) -> dict:
        issues = record.get("issues") or []
        return {**_head(record), "issue_count": len(issues),
                "open": sum(issue["status"] == "open" for issue in issues)}

    def _view(self, record: dict, current: dict | None) -> dict:
        issues = record.get("issues")
        return {
            **_head(record),
            "references": record["references"],
            "skipped": record["skipped"],
            "outdated": current is None or current["rev"] != record["draft_rev"],
            "issues": None if issues is None else
            [_issue_view(issue, current) for issue in issues],
        }


def _head(record: dict) -> dict:
    return {
        "id": record["_id"],
        "book": record["book"], "volume": record["volume"],
        "section": record["section"], "draft": record["draft"],
        "draft_rev": record["draft_rev"], "requester": record["requester"],
        "state": record["state"], "progress": record.get("progress"),
        "error": record.get("error"), "created_at": record["created_at"],
        "updated_at": record["updated_at"], **record["settings"],
        "verification": record.get("verification"), "model": record.get("model"),
        "generated_at": record.get("generated_at"),
    }


def _issue_view(issue: dict, current: dict | None) -> dict:
    """An issue, in the finding shape the rule-based advisor already uses
    (``category``, ``title``, ``excerpt``, ``replacement``) plus its own."""
    blocks = {block["id"]: block_text(block)
              for block in (current or {}).get("document", {}).get("content", [])}
    stale = issue["quote"] not in blocks.get(issue["block"], "")
    return {**issue, "dismissed_before": issue.get("dismissed_before"),
            "category": issue["check"], "title": TITLES[issue["check"]],
            "excerpt": issue["quote"], "replacement": None, "stale": stale}


def _issues(result) -> list[dict]:
    """The issues of a review result, checked; ``MalformedResult`` if not."""
    if not isinstance(result, dict) or not isinstance(result.get("issues"), list):
        raise MalformedResult("no issues")
    issues = []
    for n, raw in enumerate(result["issues"][:500], 1):
        if not isinstance(raw, dict) or raw.get("check") not in CHECKS:
            raise MalformedResult("malformed issue")
        text = {name: raw.get(name) for name in ("block", "quote", "message")}
        if not all(isinstance(value, str) and value for value in text.values()):
            raise MalformedResult("malformed issue")
        suggestion, reference = raw.get("suggestion"), raw.get("reference")
        issues.append({
            "id": f"i{n}", "check": raw["check"],
            "severity": raw.get("severity") if raw.get("severity") in (
                "info", "warning") else "info",
            "confidence": raw.get("confidence") if raw.get("confidence") in (
                "possible", "likely") else "possible",
            "block": text["block"][:64], "quote": text["quote"][:1000],
            "message": text["message"][:2000],
            "suggestion": suggestion[:2000] if isinstance(suggestion, str) else None,
            "reference": reference[:400] if isinstance(reference, str) else None,
            "verified": raw.get("verified") is True or None,
            "status": "open",
            "dismissed_before": None,
        })
    return issues


def _carry_dismissals(issues: list[dict], dismissed: list[tuple[str, dict]]) -> None:
    """Start an issue dismissed if the writer dismissed it in an earlier review of
    the section, noting which -- so a second review doesn't raise again what the
    writer has already said no to. Only dismissals carry: a resolved issue that
    comes back was not resolved after all."""
    for issue in issues:
        earlier = next((review_id for review_id, old in dismissed
                        if _same_issue(issue, old)), None)
        if earlier is not None:
            issue.update(status="dismissed", dismissed_before=earlier)


def _same_issue(new: dict, old: dict) -> bool:
    """The same check on the same block about overlapping words: a model seldom
    quotes exactly the same span twice."""
    return (new["check"] == old["check"] and new["block"] == old["block"]
            and (new["quote"] in old["quote"] or old["quote"] in new["quote"]))


def _verification(value) -> dict | None:
    if not isinstance(value, dict) or value.get("status") not in (
            "checked", "skipped", "off"):
        return None
    return {"status": value["status"], "model": value.get("model"),
            "checked": value.get("checked", 0), "removed": value.get("removed", 0)}
