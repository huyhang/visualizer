"""Who is consuming the storage.

The charging rule, decided up front: **the owner is charged for the current
document; each author is charged for the version snapshots they wrote.** With
twenty snapshots retained per article, history is usually most of the bytes, so
charging all of it to the owner would credit the growth to the wrong person.
Owns and authored always sum back to exactly what is on disk.

The rule itself is pure -- ``attribute`` takes plain records and returns plain
records, with no database anywhere near it. Reading the documents is a separate,
injected seam, so the interesting logic is tested against literal fixtures and
the boring traversal is tested once on its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Protocol

from bson import BSON

from visualizer.auth.store import DATABASE_RESOURCE
from visualizer.chronos.store import CHRONOS_DB
from visualizer.logos.store import (
    EXPORT_JOBS,
    LOGOS_DB,
    OUTLINE_REVISIONS,
    OUTLINES,
    PUBLICATION_COVERS,
    PUBLICATION_REVISIONS,
    PUBLICATIONS,
    READER_ITEMS,
    READER_SETTINGS,
    READING_POSITIONS,
    SEARCH_BLOCKS,
    SECTION_REVISIONS,
    SECTIONS,
    VOLUME_REVISIONS,
    VOLUMES,
)
from visualizer.prithvi.store import (
    MAP_IDENTITY,
    MAP_REVISIONS,
    MAPS,
    PIN_IDENTITY,
    PIN_REVISIONS,
    PINS,
    PRITHVI_DB,
)

# Shown when nothing in the grant graph or the document itself names an owner.
UNATTRIBUTED = "(unattributed)"

# Chronos collections keyed by book, and the one keyed by owner.
_BOOK_SCOPED = ("books", "plotlines", "events", "goals")
_CALENDARS = "calendars"

# Databases the article sweep must never walk into.
_MONGO_SYSTEM = frozenset({"admin", "config", "local"})

_DELETE = "delete"


@dataclass(frozen=True)
class StoredDocument:
    """One stored record, reduced to what attribution needs."""

    resource: tuple
    total_bytes: int
    history: tuple[tuple[str | None, int], ...] = ()
    created_by: str | None = None


@dataclass(frozen=True)
class WriterUsage:
    writer: str
    owns: int
    authored: int
    records: int

    @property
    def total(self) -> int:
        return self.owns + self.authored


class DocumentSource(Protocol):
    def documents(self) -> Iterator[StoredDocument]: ...


def owner_index(grants: Iterable[dict]) -> dict[tuple, str]:
    """Map each owned resource to its canonical owner.

    Ownership means holding ``delete``. Where several people do, a self-granted
    delete wins -- that is the auto-grant the creator receives -- and the
    remaining ties break alphabetically so the answer is stable between runs
    rather than dependent on document order.
    """
    candidates: dict[tuple, list[tuple[bool, str]]] = {}
    for grant in grants:
        if _DELETE not in grant.get("perms", ()):
            continue
        resource = _resource_of(grant)
        if resource is None:
            continue
        self_granted = grant.get("granted_by") == grant["username"]
        candidates.setdefault(resource, []).append((not self_granted, grant["username"]))
    return {resource: min(holders)[1] for resource, holders in candidates.items()}


def attribute(
    documents: Iterable[StoredDocument], owners: dict[tuple, str]
) -> list[WriterUsage]:
    """Charge every stored byte to a writer. Sorted by total, largest first."""
    owns: dict[str, int] = {}
    authored: dict[str, int] = {}
    records: dict[str, int] = {}
    for document in documents:
        history_total = sum(size for _, size in document.history)
        # Snapshots live inside the document, so the "current" body is whatever
        # is left once history is removed. Clamped because the container
        # overhead of the history array itself is not charged to anyone.
        current = max(0, document.total_bytes - history_total)
        owner = _owner_for(document, owners)
        owns[owner] = owns.get(owner, 0) + current
        records[owner] = records.get(owner, 0) + 1
        for author, size in document.history:
            name = author or UNATTRIBUTED
            authored[name] = authored.get(name, 0) + size
    return sorted(
        (
            WriterUsage(
                writer=writer,
                owns=owns.get(writer, 0),
                authored=authored.get(writer, 0),
                records=records.get(writer, 0),
            )
            for writer in set(owns) | set(authored)
        ),
        key=lambda usage: (-usage.total, usage.writer),
    )


def _owner_for(document: StoredDocument, owners: dict[tuple, str]) -> str:
    """Grant-holder, else whoever created it, else its first author."""
    named = owners.get(document.resource) or document.created_by
    if named:
        return named
    for author, _ in document.history:
        if author:
            return author
    return UNATTRIBUTED


def _resource_of(grant: dict) -> tuple | None:
    """The resource key a grant confers ownership of, if it names one exactly."""
    kind = grant.get("resource_type") or DATABASE_RESOURCE
    database = grant.get("database")
    collection = grant.get("collection")
    doc_id = grant.get("doc_id")
    if kind == DATABASE_RESOURCE and database and collection and doc_id:
        return ("article", database, collection, doc_id)
    if kind == "book" and database and collection is None and doc_id is None:
        return ("book", database)
    return None


class UsageScan:
    """Ties the document sweep, the grant graph and storage together.

    Thin on purpose: the rules live in ``owner_index`` and ``attribute``, both
    pure. This only decides when a day's worth of them gets written down.
    """

    def __init__(self, source: DocumentSource, grants, store):
        """:param grants: callable returning every grant, e.g. ``AuthStore.all_grants``."""
        self._source = source
        self._grants = grants
        self._store = store

    def run(self, moment) -> list[WriterUsage]:
        owners = owner_index(self._grants())
        rows = attribute(self._source.documents(), owners)
        self._store.save_storage(
            moment,
            [
                {
                    "writer": row.writer,
                    "owns": row.owns,
                    "authored": row.authored,
                    "records": row.records,
                }
                for row in rows
            ],
        )
        return rows


class MongoDocumentSource:
    """Walks every stored document and measures it with the BSON encoder.

    MongoDB can size documents server-side with ``$bsonSize``, which would avoid
    transferring them -- but that operator does not exist in the in-memory
    client the tests run against, and branching production behaviour on which
    database library is present is worse than the bandwidth. This runs hourly on
    a background thread and never on a request, so the cost lands where nobody
    is waiting on it.
    """

    def __init__(self, client):
        self._client = client

    def documents(self) -> Iterator[StoredDocument]:
        yield from self._articles()
        yield from self._chronos()
        yield from self._prithvi()
        yield from self._logos()

    def _articles(self) -> Iterator[StoredDocument]:
        for database in self._client.list_database_names():
            # Reserved databases start with "_" (``_auth``, ``_chronos``,
            # ``_ops``); chronos is measured separately below.
            if database.startswith("_") or database in _MONGO_SYSTEM:
                continue
            for collection in self._client[database].list_collection_names():
                for stored in self._client[database][collection].find():
                    yield _article(database, collection, stored)

    def _chronos(self) -> Iterator[StoredDocument]:
        database = self._client[CHRONOS_DB]
        for name in _BOOK_SCOPED:
            for stored in database[name].find():
                yield StoredDocument(
                    resource=("book", stored.get("book")),
                    total_bytes=_sizeof(stored),
                    created_by=stored.get("created_by"),
                )
        for stored in database[_CALENDARS].find():
            yield StoredDocument(
                resource=("calendar", stored.get("owner")),
                total_bytes=_sizeof(stored),
                created_by=stored.get("owner") or stored.get("created_by"),
            )

    def _prithvi(self) -> Iterator[StoredDocument]:
        database = self._client[PRITHVI_DB]
        yield from _rejoined(
            database[MAPS], database[MAP_REVISIONS], "map", MAP_IDENTITY
        )
        yield from _rejoined(
            database[PINS], database[PIN_REVISIONS], "pin", PIN_IDENTITY
        )

    def _logos(self) -> Iterator[StoredDocument]:
        """Manuscript bytes are charged to the Chronos book they belong to.

        A volume is not a thing anyone shares or owns separately -- the book is
        -- so charging prose to the book puts a manuscript and the timeline it
        was written from on the same line of the usage page.
        """
        database = self._client[LOGOS_DB]
        for heads, revisions in (
            (OUTLINES, OUTLINE_REVISIONS),
            (VOLUMES, VOLUME_REVISIONS),
            (SECTIONS, SECTION_REVISIONS),
            (PUBLICATIONS, PUBLICATION_REVISIONS),
        ):
            yield from _rejoined_by_book(database[heads], database[revisions])
        for name in (PUBLICATION_COVERS, SEARCH_BLOCKS):
            for stored in database[name].find():
                yield StoredDocument(
                    resource=("book", stored.get("book") or stored.get("_id")),
                    total_bytes=_sizeof(stored),
                )
        # A rendered PDF waiting to be collected is the largest thing one
        # account can park in the database, so it is charged to that account.
        for stored in database[EXPORT_JOBS].find():
            yield StoredDocument(
                resource=("reader", stored.get("owner")),
                total_bytes=_sizeof(stored),
                created_by=stored.get("owner"),
            )
        for name in (READER_ITEMS, READER_SETTINGS, READING_POSITIONS):
            for stored in database[name].find():
                username = stored.get("username") or stored.get("_id")
                yield StoredDocument(
                    resource=("reader", username),
                    total_bytes=_sizeof(stored),
                    created_by=username,
                )


def _article(database: str, collection: str, stored: dict) -> StoredDocument:
    history = tuple(
        (snapshot.get("author"), _sizeof(snapshot))
        for snapshot in stored.get("_history", ())
    )
    return StoredDocument(
        resource=("article", database, collection, stored["_id"]),
        total_bytes=_sizeof(stored),
        history=history,
    )


def _rejoined(heads, revisions, kind: str, identity) -> Iterator[StoredDocument]:
    """One row per map or pin, with its separately stored revisions folded in.

    Prithvi keeps each revision in its own document rather than inside the
    record, because a map's revision is a whole SVG. Attribution's model is one
    row per thing whose history it subtracts to find the current body, so the
    sweep re-joins them here: the map counts once, its head is what its owner
    "owns", and each revision's bytes are charged to whoever wrote it.
    """
    history: dict[str, list[tuple[str | None, int]]] = {}
    for revision in revisions.find():
        history.setdefault(revision["resource_key"], []).append(
            (revision.get("author"), _sizeof(revision))
        )
    for head in heads.find():
        entries = tuple(history.get(head["_id"], ()))
        yield StoredDocument(
            resource=(kind, *(head[field] for field in identity)),
            total_bytes=_sizeof(head) + sum(size for _, size in entries),
            history=entries,
            created_by=head.get("created_by"),
        )


def _rejoined_by_book(heads, revisions) -> Iterator[StoredDocument]:
    """``_rejoined``, but every record charged to its Chronos book."""
    history: dict[str, list[tuple[str | None, int]]] = {}
    for revision in revisions.find():
        history.setdefault(revision["resource_key"], []).append(
            (revision.get("author"), _sizeof(revision))
        )
    for head in heads.find():
        entries = tuple(history.get(head["_id"], ()))
        yield StoredDocument(
            resource=("book", head["book"]),
            total_bytes=_sizeof(head) + sum(size for _, size in entries),
            history=entries,
            created_by=head.get("created_by"),
        )


def _sizeof(document) -> int:
    return len(BSON.encode(document))
