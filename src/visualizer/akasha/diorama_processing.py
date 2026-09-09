"""Turn an uploaded model and its optional poster into a library asset.

Two things arrive: a ``.glb`` that has to survive ``gltf.validate_glb``, and a
still image to show before the scene is running. The poster is put through the
ordinary ``ImageProcessor`` rather than a second, diorama-shaped image
validator -- it is an image, and everything that path already does (content
sniffing, pixel caps, metadata stripping, bounded derivatives) is what a poster
needs too.

The poster is optional, and the editor supplies it by capturing the preview it
has already rendered. That is the whole answer to a poster going stale: it is
produced from the same scene, at the same moment, as the manifest it ships
with. Nothing here renders anything -- there is no GL in a Python process.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath

from .assets import DIORAMA, Asset, AssetBlob
from .diorama import validate_manifest
from .gltf import GlbLimits, validate_glb
from .image_processing import ImageProcessor

MODEL_MIME = "model/gltf-binary"


@dataclass(frozen=True)
class ProcessedDiorama:
    filename: str
    facts: dict
    variants: dict[str, AssetBlob]

    def as_asset(self) -> Asset:
        return Asset(
            kind=DIORAMA,
            filename=self.filename,
            facts=self.facts,
            variants=self.variants,
        )


class DioramaProcessor:
    """Validates a model and its poster; limits arrive by injection."""

    def __init__(self, images: ImageProcessor, limits: GlbLimits | None = None):
        self._images = images
        self.limits = limits or GlbLimits()

    @property
    def max_bytes(self) -> int:
        return self.limits.max_bytes

    def process(
        self,
        model: bytes,
        filename: str | None,
        manifest,
        poster: bytes | None = None,
    ) -> ProcessedDiorama:
        facts = validate_glb(model, self.limits)
        variants = {
            "model": AssetBlob(
                data=model,
                mime_type=MODEL_MIME,
                sha256=_digest(model),
                facts={"bytes": facts.byte_length},
            )
        }
        if poster:
            # Only the bounded copy is kept. A poster is a thumbnail by
            # purpose, so archiving the photographer's original would store
            # bytes nothing will ever serve.
            rendered = self._images.process(poster, "poster.webp").display
            variants["poster"] = AssetBlob(
                data=rendered.data,
                mime_type=rendered.mime_type,
                sha256=rendered.sha256,
                facts={"width": rendered.width, "height": rendered.height},
            )
        return ProcessedDiorama(
            filename=_safe_name(filename),
            facts={
                # Kept apart on purpose: `model` is measured from the file and
                # never edited, `manifest` is the part a writer changes without
                # re-uploading anything.
                "model": {
                    "vertices": facts.vertices,
                    "nodes": facts.nodes,
                    "meshes": facts.meshes,
                    "materials": facts.materials,
                    "primitives": facts.primitives,
                    "textures": facts.images,
                    "bytes": facts.byte_length,
                    "extensions": list(facts.extensions),
                },
                "manifest": validate_manifest(manifest),
            },
            variants=variants,
        )


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _safe_name(filename: str | None) -> str:
    if not filename:
        return "diorama.glb"
    name = PurePath(str(filename).replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:200] or "diorama.glb"
