"""Application services for uploads and article-to-image references."""

from collections.abc import Callable

from .assets import DIORAMA, AssetBlob
from .diorama import validate_manifest
from .diorama_processing import DioramaProcessor
from .errors import InvalidDiorama, MediaInUse
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

    def referenced_ids(self, world: str) -> set[str]:
        """Every media id any article still points at, live or retained.

        Retained revisions count because they are what blocks a delete: an
        "orphan" that history still holds would be listed as removable and then
        refuse to go, which is a worse answer than not listing it.
        """
        found = set()
        for _, stored in self._documents(world):
            if not stored.get("_deleted"):
                found |= self._find_ids(stored)
            for snapshot in stored.get("_history", ()):
                found |= self._find_ids(snapshot.get("document") or {})
        return found

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
        dioramas: DioramaProcessor | None = None,
    ):
        self.store = store
        self.processor = processor
        self.references = references
        # Left out, the world simply has no diorama support -- the routes ask
        # before offering it, so an install can run images-only.
        self.dioramas = dioramas

    def upload(self, world, uploader, filename, data, alt) -> dict:
        image = self.processor.process(data, filename)
        return self.store.create(
            world, uploader, validate_alt_text(alt), image.as_asset()
        )

    def upload_diorama(
        self, world, uploader, filename, model, alt, manifest, poster=None
    ) -> dict:
        processed = self._diorama_processor().process(model, filename, manifest, poster)
        return self.store.create(
            world, uploader, validate_alt_text(alt), processed.as_asset()
        )

    def update_manifest(self, world, media_id, manifest, poster=None) -> dict:
        """Re-aim the camera without re-uploading the geometry.

        The model's measured facts are carried across untouched: they describe
        the file, and the file has not changed.

        A poster may come with it, and the editor always sends one, because a
        still taken through the old camera stops being a picture of the scene
        the moment the camera moves. Re-aiming and re-shooting are one act.
        """
        record = self.store.get(world, media_id)
        if record.get("kind") != DIORAMA:
            raise InvalidDiorama("That library entry is not a diorama.")
        updated = self.store.update_facts(
            world,
            media_id,
            {"model": record.get("model", {}), "manifest": validate_manifest(manifest)},
        )
        if poster:
            rendered = self.processor.process(poster, "poster.webp").display
            updated = self.store.replace_variant(
                world, media_id, "poster",
                AssetBlob(
                    data=rendered.data,
                    mime_type=rendered.mime_type,
                    sha256=rendered.sha256,
                    facts={"width": rendered.width, "height": rendered.height},
                ),
            )
        return updated

    def _diorama_processor(self) -> DioramaProcessor:
        if self.dioramas is None:
            raise InvalidDiorama("This world does not accept dioramas.")
        return self.dioramas

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


def build_media_service(client, images: ImageProcessor, limits) -> MediaService:
    """Compose the world media library from its seams.

    Both entrypoints call this rather than repeating the wiring: the standalone
    `akasha/wsgi.py` and the combined gateway have to be the *same* app, and the
    surest way to make them differ is to build them twice.
    """
    return MediaService(
        MediaStore(client),
        images,
        ArticleMediaReferences(client),
        DioramaProcessor(images, limits),
    )
