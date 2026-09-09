"""MongoDB/GridFS persistence for Akasha's world-scoped media library."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import gridfs

from .errors import MediaNotFound
from .image_processing import ProcessedImage

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

    def create(
        self, world: str, uploader: str, alt: str, image: ProcessedImage
    ) -> dict:
        media_id = self._id_factory()
        blobs: dict[str, object] = {}
        by_digest: dict[str, object] = {}
        try:
            for name in ("original", "display", "thumbnail"):
                variant = getattr(image, name)
                # A derivative may *be* the original: the processor declines to
                # build one that would cost more bytes than it saves. Store
                # those bytes once and point both variants at the same file.
                if variant.sha256 not in by_digest:
                    by_digest[variant.sha256] = self._files.put(
                        variant.data,
                        filename=image.filename,
                        content_type=variant.mime_type,
                        metadata={"media_id": media_id, "variant": name},
                    )
                blobs[name] = by_digest[variant.sha256]
            record = {
                "_id": media_id,
                "world": world,
                "uploader": uploader,
                "filename": image.filename,
                "alt": alt,
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "created_at": self._clock().isoformat(),
                "variants": {
                    name: {
                        "file_id": blobs[name],
                        "mime_type": getattr(image, name).mime_type,
                        "width": getattr(image, name).width,
                        "height": getattr(image, name).height,
                        "bytes": len(getattr(image, name).data),
                        "sha256": getattr(image, name).sha256,
                    }
                    for name in blobs
                },
            }
            self._records.insert_one(record)
        except Exception:
            for file_id in by_digest.values():
                self._files.delete(file_id)
            raise
        return self._public(record)

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
        variants = record.get("variants", {})
        return {
            "id": record["_id"],
            "world": record["world"],
            "uploader": record["uploader"],
            "filename": record["filename"],
            "alt": record["alt"],
            "format": record["format"],
            "width": record["width"],
            "height": record["height"],
            "created_at": record["created_at"],
            "variants": {
                name: {key: value for key, value in details.items() if key != "file_id"}
                for name, details in variants.items()
            },
        }
