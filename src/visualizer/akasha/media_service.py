"""Application services for uploads and article-to-image references."""

from collections.abc import Callable

from .errors import MediaInUse
from .image_processing import ImageProcessor
from .media import document_image_ids, validate_alt_text
from .media_store import MediaStore


class ArticleMediaReferences:
    """Read image references from articles without changing their store."""

    def __init__(self, client, find_ids: Callable[[dict | None], set[str]] = document_image_ids):
        self._client = client
        self._find_ids = find_ids

    def visible_ids(self, world: str, may_read: Callable[[str, str], bool]) -> set[str]:
        visible = set()
        for collection, stored in self._documents(world):
            if stored.get("_deleted") or not may_read(collection, stored["_id"]):
                continue
            visible.update(self._find_ids(stored))
        return visible

    def references(self, world: str, media_id: str) -> list[dict]:
        found = []
        for collection, stored in self._documents(world):
            current_rev = stored.get("_rev", 1)
            if not stored.get("_deleted") and media_id in self._find_ids(stored):
                found.append(
                    {
                        "collection": collection,
                        "article": stored["_id"],
                        "revision": current_rev,
                        "current": True,
                    }
                )
            for snapshot in stored.get("_history", ()):
                document = snapshot.get("document") or {}
                if snapshot.get("rev") == current_rev and not stored.get("_deleted"):
                    continue
                if media_id in self._find_ids(document):
                    found.append(
                        {
                            "collection": collection,
                            "article": stored["_id"],
                            "revision": snapshot.get("rev"),
                            "current": False,
                        }
                    )
        return found

    def _documents(self, world: str):
        database = self._client[world]
        for collection in database.list_collection_names():
            for stored in database[collection].find():
                yield collection, stored


class MediaService:
    def __init__(
        self,
        store: MediaStore,
        processor: ImageProcessor,
        references: ArticleMediaReferences,
    ):
        self.store = store
        self.processor = processor
        self.references = references

    def upload(self, world, uploader, filename, data, alt) -> dict:
        image = self.processor.process(data, filename)
        return self.store.create(world, uploader, validate_alt_text(alt), image)

    def update_alt(self, world, media_id, alt) -> dict:
        return self.store.update_alt(world, media_id, validate_alt_text(alt))

    def delete(self, world, media_id, force: bool = False) -> list[dict]:
        references = self.references.references(world, media_id)
        if references and not force:
            raise MediaInUse(
                f"Image '{media_id}' is used by {len(references)} article version(s).",
                references,
            )
        self.store.delete(world, media_id)
        return references
