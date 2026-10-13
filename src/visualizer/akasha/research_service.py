"""Research, end to end on Akasha's side: ask, follow, import, review.

    submit  -> a job record, and the question sent to the GPU box
    refresh -> the box's progress; when it is done, the result imported
               into research-inbox as drafts (once, however many tabs poll)
    accept  -> the draft and its sources moved into research / sources
    reject  -> the draft and its new sources deleted (soft: history stays)

Plus the image candidates a draft carries: previewed and imported through the
box, which alone fetches from the web. Importing goes through the ordinary
media pipeline (size caps, derivatives, metadata stripping) and keeps the
image's source URL and license.

The rules about *what* lands *where* are in ``research_import``; this module
reads and writes around them. Routes authorise; this module assumes they have.
"""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit

from werkzeug.security import generate_password_hash

from visualizer.auth import ALL_PERMS, READ, WRITE, AuthStore

from .errors import (
    CollectionAlreadyExists,
    DocumentNotFound,
    DraftNotPending,
    MediaNotFound,
    ResearchBusy,
    ResearchJobNotFound,
    ResearchUnavailable,
)
from .labels import derive_title
from .media_service import MediaService
from .research import Researcher, validate_request
from .research_import import (
    BOT,
    INBOX,
    RESEARCH,
    SOURCES,
    InvalidResult,
    normalize_url,
    plan_accept,
    plan_import,
    validate_result,
)
from .research_jobs import ResearchJobStore
from .store import DocumentStore

MAX_ACTIVE_PER_WRITER = 3
MAX_ACTIVE = 10
MAX_KNOWN_ARTICLES = 200


def job_view(job: dict) -> dict:
    details = job.get("details") or {}
    pending = job.get("review") == "pending" and job.get("draft")
    return {
        "id": job["_id"],
        "world": job["world"],
        "requester": job["requester"],
        "question": job["question"],
        "state": job["state"],
        "progress": job.get("progress"),
        "error": job.get("error"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "draft": f"{INBOX}/{job['draft']}" if pending else None,
        "review": job.get("review"),
        "accepted": job.get("accepted"),
        "verification": (details.get("verification") or {}).get("status"),
    }


class ResearchService:
    def __init__(self, store: DocumentStore, auth_store: AuthStore,
                 researcher: Researcher, jobs: ResearchJobStore | None,
                 media_service: MediaService | None, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.store = store
        self.auth_store = auth_store
        self.researcher = researcher
        self.jobs = jobs
        self.media_service = media_service
        self._clock = clock

    # -- asking ----------------------------------------------------------------

    def submit(self, world: str, writer: str, payload) -> dict:
        request = validate_request(payload)
        jobs = self._jobs()
        self.store.list_collections(world)   # the world must exist (404 if not)
        if jobs.count_active(writer) >= MAX_ACTIVE_PER_WRITER:
            raise ResearchBusy(f"You already have {MAX_ACTIVE_PER_WRITER} research "
                               "jobs running. Wait for one to finish.", retry_after=60)
        if jobs.count_active() >= MAX_ACTIVE:
            raise ResearchBusy("Too many research jobs are running. Try again shortly.",
                               retry_after=60)
        request["known_articles"] = self._known_articles(world)
        job = jobs.create(world=world, requester=writer, question=request["question"],
                          request=request)
        try:
            remote = self.researcher.submit(request, job["_id"])
        except Exception:
            # Nothing reached the box (or it refused): leave no job behind.
            jobs.delete(job["_id"])
            raise
        # Here "done" means imported and "failed" carries an error, so a job the
        # box has already finished stays running until the first poll settles it.
        state = remote["state"] if remote["state"] in ("queued", "running") else "running"
        return job_view(jobs.update(job["_id"], state=state,
                                    worker_job=remote["id"],
                                    progress=remote.get("progress")))

    def refresh(self, world: str, job_id: str) -> dict:
        """The job as it stands, asking the box if it is still running."""
        job = self._job(world, job_id)
        if job["state"] not in ("queued", "running"):
            return job_view(job)
        try:
            remote = self.researcher.status(job["worker_job"])
        except ResearchJobNotFound:
            return job_view(self._fail(job, "expired", "The GPU box no longer has "
                                       "this job; its result expired before import."))
        except ResearchUnavailable:
            return job_view(job)     # asleep or busy: report what we last knew
        state = remote["state"]
        if state in ("queued", "running"):
            return job_view(self._jobs().update(job["_id"], state=state,
                                                progress=remote.get("progress")))
        if state == "failed":
            error = remote.get("error") or {}
            return job_view(self._fail(job, error.get("code", "internal"),
                                       error.get("message", "The research job failed.")))
        if state == "cancelled":
            return job_view(self._jobs().update(job["_id"], state="cancelled",
                                                progress=None))
        if self._jobs().claim_import(job["_id"]):
            return job_view(self._import(job, remote.get("result")))
        return job_view(self._job(world, job_id))   # another request is importing

    def cancel(self, world: str, job_id: str) -> dict:
        job = self._job(world, job_id)
        if job["state"] not in ("queued", "running"):
            return job_view(job)
        try:
            self.researcher.cancel(job["worker_job"])
        except ResearchJobNotFound:
            pass
        return job_view(self._jobs().update(job["_id"], state="cancelled", progress=None))

    def recent(self, world: str) -> list[dict]:
        return [job_view(job) for job in self._jobs().recent(world)]

    # -- importing -------------------------------------------------------------

    def _import(self, job: dict, result) -> dict:
        created: list[tuple[str, str]] = []
        try:
            valid = validate_result(result)
            self._ensure_collection(job["world"], INBOX, owner=None)
            self._ensure_bot(job["world"])
            plan = plan_import(
                valid, question=job["question"], job_id=job["_id"],
                accepted_sources=self._source_urls(job["world"]),
                taken=self._ids(job["world"], INBOX) | self._ids(job["world"], RESEARCH))
            for slug, document in plan.new_sources:
                self.store.create(job["world"], INBOX, slug, document, author=BOT)
                created.append((INBOX, slug))
            self.store.create(job["world"], INBOX, plan.draft_slug, plan.draft,
                              author=BOT)
        except InvalidResult as err:
            self._undo(job["world"], created)
            return self._fail(job, "invalid_result",
                              f"The GPU box sent a malformed result ({err}).")
        except Exception:  # noqa: BLE001 -- any failure must undo and mark the job
            self._undo(job["world"], created)
            return self._fail(job, "import_failed",
                              "The result could not be stored in Akasha.")
        return self._jobs().update(job["_id"], state="done", progress=None,
                                   draft=plan.draft_slug, details=plan.details,
                                   review="pending")

    def _undo(self, world: str, created: list[tuple[str, str]]) -> None:
        for collection, slug in reversed(created):
            try:
                self.store.delete(world, collection, slug, author=BOT)
            except DocumentNotFound:
                pass

    # -- the inbox -------------------------------------------------------------

    def inbox(self, world: str) -> list[dict]:
        drafts = []
        for job in self._jobs().pending_review(world):
            try:
                document = self.store.get(world, INBOX, job["draft"])["document"]
            except DocumentNotFound:
                continue   # deleted through the ordinary API meanwhile
            details = job.get("details") or {}
            drafts.append({
                "draft": f"{INBOX}/{job['draft']}",
                "title": document.get("title") or derive_title(job["draft"]),
                "question": job["question"],
                "requester": job["requester"],
                "job": job["_id"],
                "created_at": job["created_at"],
                "verification": (details.get("verification") or {}).get("status"),
                "facts": len(details.get("facts") or []),
                "images": len(details.get("images") or []),
            })
        return drafts

    def draft(self, world: str, slug: str) -> dict:
        job = self._pending(world, slug)
        article = self.store.get(world, INBOX, slug)
        details = job.get("details") or {}
        return {
            "draft": f"{INBOX}/{slug}",
            "article": article,
            "job": job_view(job),
            "facts": details.get("facts") or [],
            "dropped_facts": details.get("dropped_facts") or [],
            "sources": details.get("sources") or [],
            "images": [{"index": n, "url": image["url"], "caption": image["caption"],
                        "license": image["license"], "source": image["source"],
                        "imported": image.get("imported")}
                       for n, image in enumerate(details.get("images") or [])],
            "verification": details.get("verification"),
            "links": details.get("links") or [],
        }

    def accept(self, world: str, slug: str, writer: str) -> dict:
        job = self._pending(world, slug)
        draft = self.store.get(world, INBOX, slug)["document"]
        inbox_sources = {}
        for ref in draft.get("sources") or []:
            collection, _, source_slug = ref.partition("/")
            if collection == INBOX:
                try:
                    inbox_sources[source_slug] = self.store.get(
                        world, INBOX, source_slug)["document"]
                except DocumentNotFound:
                    pass
        plan = plan_accept(
            draft, inbox_sources, writer=writer,
            accepted_at=self._clock().isoformat(),
            accepted_sources=self._source_urls(world),
            taken_research=self._ids(world, RESEARCH),
            taken_sources=self._ids(world, SOURCES), draft_slug=slug)

        self._ensure_collection(world, SOURCES, owner=writer)
        self._ensure_collection(world, RESEARCH, owner=writer)
        for _, target, document in plan.moves:
            self.store.create(world, SOURCES, target, document, author=writer)
            self.auth_store.grant_owner(writer, world, SOURCES, target, list(ALL_PERMS))
        self.store.create(world, RESEARCH, plan.article_slug, plan.article, author=writer)
        self.auth_store.grant_owner(writer, world, RESEARCH, plan.article_slug,
                                    list(ALL_PERMS))
        for source_slug in list(inbox_sources):
            self._delete(world, INBOX, source_slug, writer)
        self._delete(world, INBOX, slug, writer)
        accepted = f"{RESEARCH}/{plan.article_slug}"
        self._jobs().update(job["_id"], review="accepted", accepted=accepted)
        return {"article": accepted,
                "sources": [f"{SOURCES}/{target}" for _, target, _ in plan.moves],
                "relinked": [f"{SOURCES}/{target}" for target in plan.relinked.values()]}

    def reject(self, world: str, slug: str, writer: str) -> None:
        job = self._pending(world, slug)
        try:
            draft = self.store.get(world, INBOX, slug)["document"]
        except DocumentNotFound:
            draft = {}
        for ref in draft.get("sources") or []:
            collection, _, source_slug = ref.partition("/")
            if collection == INBOX:
                self._delete(world, INBOX, source_slug, writer)
        self._delete(world, INBOX, slug, writer)
        self._jobs().update(job["_id"], review="rejected")

    # -- images ----------------------------------------------------------------

    def image(self, world: str, slug: str, index: int, size: str) -> tuple[bytes, str]:
        candidate = self._candidate(world, slug, index)[1]
        return self.researcher.fetch_image(candidate["url"], candidate["fetch_token"],
                                           size)

    def import_image(self, world: str, slug: str, index: int, writer: str) -> dict:
        if self.media_service is None:
            raise ResearchUnavailable("This Akasha has no media library to import into.")
        job, candidate = self._candidate(world, slug, index)
        data, _ = self.researcher.fetch_image(candidate["url"], candidate["fetch_token"],
                                              "full")
        record = self.media_service.upload(
            world, writer, _filename(candidate["url"]), data,
            candidate["caption"] or "An image found by research",
            source_url=candidate["url"], license=candidate["license"])
        self._jobs().mark_image_imported(job["_id"], index, record["id"])
        return record

    # -- plumbing --------------------------------------------------------------

    def _jobs(self) -> ResearchJobStore:
        if self.jobs is None:
            raise ResearchUnavailable("Research is not set up on this Akasha.")
        return self.jobs

    def _job(self, world: str, job_id: str) -> dict:
        job = self._jobs().get(world, job_id)
        if job is None:
            raise ResearchJobNotFound(f"No research job '{job_id}' in this world.")
        return job

    def _pending(self, world: str, slug: str) -> dict:
        job = self._jobs().by_draft(world, slug)
        if job is None:
            raise DocumentNotFound(f"'{slug}' is not a research draft in this world.")
        if job.get("review") != "pending":
            raise DraftNotPending(f"This draft was already {job.get('review')}.")
        return job

    def _candidate(self, world: str, slug: str, index: int):
        job = self._pending(world, slug)
        images = (job.get("details") or {}).get("images") or []
        if not 0 <= index < len(images):
            raise MediaNotFound(f"This draft has no image candidate {index}.")
        return job, images[index]

    def _fail(self, job: dict, code: str, message: str) -> dict:
        return self._jobs().update(job["_id"], state="failed", progress=None,
                                   error={"code": code, "message": message})

    def _ids(self, world: str, collection: str) -> set[str]:
        if collection not in self.store.list_collections(world):
            return set()
        return set(self.store.document_ids(world, collection))

    def _source_urls(self, world: str) -> dict[str, str]:
        """normalised URL -> slug, for every accepted source in the world."""
        if SOURCES not in self.store.list_collections(world):
            return {}
        return {normalize_url(doc["document"]["url"]): doc["id"]
                for doc in self.store.list_documents(world, SOURCES)
                if isinstance(doc["document"].get("url"), str)}

    def _known_articles(self, world: str) -> list[dict]:
        """Refs and titles -- never bodies -- research first, then the rest."""
        collections = [c for c in self.store.list_collections(world)
                       if c not in (INBOX, SOURCES)]
        collections.sort(key=lambda c: c != RESEARCH)
        known = []
        for collection in collections:
            for doc in self.store.list_documents(world, collection):
                title = doc["document"].get("title")
                known.append({"ref": f"{world}/{collection}/{doc['id']}",
                              "title": (title if isinstance(title, str) and title.strip()
                                        else derive_title(doc["id"]))[:300]})
                if len(known) == MAX_KNOWN_ARTICLES:
                    return known
        return known

    def _ensure_collection(self, world: str, collection: str, owner: str | None) -> None:
        if collection in self.store.list_collections(world):
            return
        try:
            self.store.create_collection(world, collection)
        except CollectionAlreadyExists:
            return
        if owner is not None:
            self.auth_store.grant_owner(owner, world, collection, None, list(ALL_PERMS))

    def _ensure_bot(self, world: str) -> None:
        """The account drafts are written as: reserved, and unable to log in.

        Its grant is the design's least privilege -- read and write on the
        inbox only -- and documents who may put things there.
        """
        if self.auth_store.get_user(BOT) is None:
            self.auth_store.create_user(
                BOT, generate_password_hash(secrets.token_urlsafe(32)), active=False)
        self.auth_store.grant_owner(BOT, world, INBOX, None, [READ, WRITE])

    def _delete(self, world: str, collection: str, slug: str, author: str) -> None:
        try:
            self.store.delete(world, collection, slug, author=author)
        except DocumentNotFound:
            pass


def _filename(url: str) -> str:
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1]).strip()
    return (name or "research-image")[:200]
