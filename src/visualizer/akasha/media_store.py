"""MongoDB/GridFS persistence for Akasha's world-scoped media library.

Holds *assets*: images and dioramas alike. What distinguishes them lives in
``assets.py`` and in each kind's own module; nothing here reads a fact it
stores, which is why a new kind costs this file nothing.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import gridfs

from .assets import IMAGE, Asset
from .errors import MediaNotFound

MEDIA_DB = "_akasha_media"
MEDIA_COLLECTION = "media"
BLOB_BUCKET = "blobs"
BLOB_FILES = f"{BLOB_BUCKET}.files"
BLOB_CHUNKS = f"{BLOB_BUCKET}.chunks"


def _default_clock() -> datetime:
    return datetime.now(UTC)


class MediaStore:
    def __init__(
        self,
        client,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ):
        self._db = client[MEDIA_DB]
        self._records = self._db[MEDIA_COLLECTION]
        self._records.create_index([("world", 1), ("created_at", -1)])
        self._files = gridfs.GridFS(self._db, collection=BLOB_BUCKET)
        self._clock = clock or _default_clock
        self._id_factory = id_factory or (lambda: uuid4().hex)

    def create(self, world: str, uploader: str, alt: str, asset: Asset) -> dict:
        media_id = self._id_factory()
        blobs: dict[str, object] = {}
        by_digest: dict[str, object] = {}
        try:
            for name, blob in asset.variants.items():
                # Two variants may be the same bytes: the image processor
                # declines a derivative that would cost more than it saves, and
                # a diorama's poster is one file however many places show it.
                if blob.sha256 not in by_digest:
                    by_digest[blob.sha256] = self._files.put(
                        blob.data,
                        filename=asset.filename,
                        content_type=blob.mime_type,
                        metadata={"media_id": media_id, "variant": name},
                    )
                blobs[name] = by_digest[blob.sha256]
            record = {
                "_id": media_id,
                "world": world,
                "uploader": uploader,
                "kind": asset.kind,
                "filename": asset.filename,
                "alt": alt,
                "facts": dict(asset.facts),
                "created_at": self._clock().isoformat(),
                "variants": {
                    name: {
                        "file_id": blobs[name],
                        "mime_type": blob.mime_type,
                        "bytes": len(blob.data),
                        "sha256": blob.sha256,
                        "facts": dict(blob.facts),
                    }
                    for name, blob in asset.variants.items()
                },
            }
            self._records.insert_one(record)
        except Exception:
            for file_id in by_digest.values():
                self._files.delete(file_id)
            raise
        return self._public(record)

    def replace_variant(self, world: str, media_id: str, name: str, blob) -> dict:
        """Swap one variant's bytes, keeping the rest of the record.

        Used when a diorama is re-aimed: the poster has to be retaken or it
        would go on showing a camera angle that no longer exists.
        """
        record = self._record(world, media_id)
        variants = record.get("variants", {})
        previous = variants.get(name, {}).get("file_id")
        file_id = self._files.put(
            blob.data,
            filename=record["filename"],
            content_type=blob.mime_type,
            metadata={"media_id": media_id, "variant": name},
        )
        variants[name] = {
            "file_id": file_id,
            "mime_type": blob.mime_type,
            "bytes": len(blob.data),
            "sha256": blob.sha256,
            "facts": dict(blob.facts),
        }
        self._records.update_one(
            {"_id": media_id, "world": world}, {"$set": {"variants": variants}}
        )
        # Only after the record points elsewhere, and only if nothing else
        # still points at it -- variants may share one file.
        still_used = any(
            details.get("file_id") == previous for details in variants.values()
        )
        if previous is not None and not still_used:
            try:
                self._files.delete(previous)
            except gridfs.errors.NoFile:
                pass
        return self.get(world, media_id)

    def update_facts(self, world: str, media_id: str, facts: dict) -> dict:
        """Replace an asset's kind-level facts -- a diorama's manifest, edited."""
        result = self._records.update_one(
            {"_id": media_id, "world": world}, {"$set": {"facts": dict(facts)}}
        )
        if result.matched_count == 0:
            raise MediaNotFound(f"Image '{media_id}' does not exist in '{world}'.")
        return self.get(world, media_id)

    def list(self, world: str) -> list[dict]:
        return [
            self._public(record)
            for record in self._records.find({"world": world}).sort("created_at", -1)
        ]

    def get(self, world: str, media_id: str) -> dict:
        record = self._record(world, media_id)
        return self._public(record)

    def update_alt(self, world: str, media_id: str, alt: str) -> dict:
        result = self._records.update_one(
            {"_id": media_id, "world": world}, {"$set": {"alt": alt}}
        )
        if result.matched_count == 0:
            raise MediaNotFound(f"Image '{media_id}' does not exist in '{world}'.")
        return self.get(world, media_id)

    def read_variant(self, world: str, media_id: str, variant: str) -> tuple[bytes, dict]:
        record = self._record(world, media_id)
        details = record.get("variants", {}).get(variant)
        if details is None:
            raise MediaNotFound(f"Image variant '{variant}' does not exist.")
        try:
            data = self._files.get(details["file_id"]).read()
        except gridfs.errors.NoFile:
            raise MediaNotFound(f"Image variant '{variant}' does not exist.") from None
        return data, {**details, "filename": record["filename"]}

    def delete(self, world: str, media_id: str) -> None:
        record = self._record(world, media_id)
        # Variants can share one file when a derivative was declined, so delete
        # the distinct ids rather than one per variant name.
        for file_id in {d["file_id"] for d in record.get("variants", {}).values()}:
            try:
                self._files.delete(file_id)
            except gridfs.errors.NoFile:
                pass
        self._records.delete_one({"_id": media_id, "world": world})

    def _record(self, world: str, media_id: str) -> dict:
        record = self._records.find_one({"_id": media_id, "world": world})
        if record is None:
            raise MediaNotFound(f"Image '{media_id}' does not exist in '{world}'.")
        return record

    @staticmethod
    def _public(record: dict) -> dict:
        """The API view. Kind facts are spread to the top level rather than
        nested, so an image keeps reporting `format`/`width`/`height` exactly
        where it always did and a diorama adds its own alongside."""
        return {
            "id": record["_id"],
            "world": record["world"],
            "uploader": record["uploader"],
            "kind": record.get("kind", IMAGE),
            "filename": record["filename"],
            "alt": record["alt"],
            "created_at": record["created_at"],
            **_facts(record, ("format", "width", "height")),
            "variants": {
                name: {
                    "mime_type": details.get("mime_type"),
                    "bytes": details.get("bytes"),
                    "sha256": details.get("sha256"),
                    **_facts(details, ("width", "height")),
                }
                for name, details in record.get("variants", {}).items()
            },
        }


def _facts(document: dict, legacy_keys: tuple[str, ...]) -> dict:
    """This document's facts, whichever shape it was written in.

    Records predating the diorama work keep their facts at the top level rather
    than under ``facts``. Both are read so an existing library keeps rendering
    without a migration; only the newer shape is ever written.
    """
    facts = document.get("facts")
    if isinstance(facts, dict):
        return dict(facts)
    return {key: document[key] for key in legacy_keys if key in document}
