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


def _sizeof(document) -> int:
    return len(BSON.encode(document))
