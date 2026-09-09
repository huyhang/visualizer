"""Decide whether a ``.glb`` is one Akasha will store and a browser will render.

**The browser renderer is intentionally not the validator.** By the time three.js
sees a file it is already in someone's page, already downloaded, and already
costing whatever it costs; a malformed or hostile model has to be refused before
that. So this reads the container itself and answers three questions:

*Is it structurally what it claims to be?* The header's declared length must
match the bytes actually present, every chunk must fit inside them, and only the
two chunk types glTF defines may appear. A file that lies about its own size is
the cheapest way to smuggle a payload past a naive reader.

*Does it reach outside itself?* glTF lets buffers and images carry a ``uri``.
A stored model that fetches from a URL when opened is an exfiltration channel --
it would tell a third party who read which article, and when. Both are refused
outright; everything must be embedded.

*Is it bounded?* Counts and sizes are capped, and the vertex total is summed
from the accessors rather than believed from a header, because the header is
written by whoever made the file.

Pure: bytes and limits in, facts or an exception out. No Flask, no Mongo, no
network, and no decode of anything except embedded textures -- which go through
Pillow with its decompression-bomb guard armed.
"""

import json
import struct
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from .errors import DioramaTooLarge, InvalidDiorama

_MAGIC = b"glTF"
_JSON_CHUNK = 0x4E4F534A  # 'JSON'
_BIN_CHUNK = 0x004E4942   # 'BIN\0'

# Extensions the viewer can actually honour. Anything else named in
# `extensionsRequired` is refused rather than silently rendered wrong: Draco,
# meshopt and basisu all need a decoder we do not ship, and a model that quietly
# loses its geometry is worse than one that never loaded.
_RENDERABLE_EXTENSIONS = frozenset({
    "KHR_materials_unlit",
    "KHR_materials_emissive_strength",
    "KHR_texture_transform",
})


@dataclass(frozen=True)
class GlbLimits:
    """Caps on a stored model. Injected so deployment can tighten them."""

    max_bytes: int = 24 * 1024 * 1024
    max_json_bytes: int = 4 * 1024 * 1024
    max_nodes: int = 2000
    max_meshes: int = 1000
    max_materials: int = 256
    max_primitives: int = 5000
    max_vertices: int = 2_000_000
    max_images: int = 32
    max_texture_side: int = 4096
    max_texture_pixels: int = 16_777_216


@dataclass(frozen=True)
class GlbFacts:
    """What the file turned out to contain, once it was believed."""

    byte_length: int
    nodes: int
    meshes: int
    materials: int
    primitives: int
    vertices: int
    images: int
    has_binary_chunk: bool
    extensions: tuple[str, ...] = field(default=())


def validate_glb(data: bytes, limits: GlbLimits | None = None) -> GlbFacts:
    """Return the model's facts, or raise explaining what disqualified it."""
    limits = limits or GlbLimits()
    _check_size(data, limits)
    chunks = _chunks(data, limits)
    document = _parse_json(chunks["json"], limits)
    binary = chunks.get("bin", b"")

    _reject_external_uris(document)
    _reject_unrenderable_extensions(document)
    counts = _count_geometry(document, limits)
    images = _validate_embedded_images(document, binary, limits)

    return GlbFacts(
        byte_length=len(data),
        nodes=counts["nodes"],
        meshes=counts["meshes"],
        materials=counts["materials"],
        primitives=counts["primitives"],
        vertices=counts["vertices"],
        images=images,
        has_binary_chunk="bin" in chunks,
        extensions=tuple(sorted(document.get("extensionsUsed", []) or [])),
    )


def _check_size(data: bytes, limits: GlbLimits) -> None:
    if not data:
        raise InvalidDiorama("Choose a model to upload.")
    if len(data) > limits.max_bytes:
        raise DioramaTooLarge(
            f"A model is at most {limits.max_bytes} bytes."
        )
    if len(data) < 12:
        raise InvalidDiorama("The upload is too short to be a glTF binary.")


def _chunks(data: bytes, limits: GlbLimits) -> dict[str, bytes]:
    magic, version, declared = struct.unpack_from("<4sII", data, 0)
    if magic != _MAGIC:
        raise InvalidDiorama("The upload is not a glTF binary (.glb).")
    if version != 2:
        raise InvalidDiorama(f"Only glTF 2.0 is supported, not version {version}.")
    # A file that misreports its own length is how a reader gets walked past the
    # end of what was actually sent.
    if declared != len(data):
        raise InvalidDiorama(
            f"The file says it is {declared} bytes but {len(data)} arrived."
        )

    found: dict[str, bytes] = {}
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise InvalidDiorama("A chunk header runs past the end of the file.")
        length, kind = struct.unpack_from("<II", data, offset)
        if length % 4:
            raise InvalidDiorama("A chunk length is not 4-byte aligned.")
        start = offset + 8
        end = start + length
        if end > len(data):
            raise InvalidDiorama("A chunk runs past the end of the file.")
        if kind == _JSON_CHUNK:
            if found:
                raise InvalidDiorama("The JSON chunk must come first, and once.")
            found["json"] = data[start:end]
        elif kind == _BIN_CHUNK:
            if "json" not in found:
                raise InvalidDiorama("The JSON chunk must come first, and once.")
            if "bin" in found:
                raise InvalidDiorama("A glTF binary has at most one BIN chunk.")
            found["bin"] = data[start:end]
        else:
            # An allowlist, not a skip: an unknown chunk is content nothing in
            # this system has inspected.
            raise InvalidDiorama(f"Unsupported chunk type 0x{kind:08x}.")
        offset = end
    if "json" not in found:
        raise InvalidDiorama("The file has no glTF JSON chunk.")
    if len(found["json"]) > limits.max_json_bytes:
        raise DioramaTooLarge(
            f"The model's JSON is at most {limits.max_json_bytes} bytes."
        )
    return found


def _parse_json(raw: bytes, limits: GlbLimits) -> dict:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidDiorama("The model's glTF JSON is not readable.") from exc
    if not isinstance(document, dict):
        raise InvalidDiorama("The model's glTF JSON is not an object.")
    return document


def _reject_external_uris(document: dict) -> None:
    """No buffer or image may point outside the file.

    This is the finding that matters most: an external ``uri`` turns opening an
    article into a request to somebody else's server.
    """
    for section in ("buffers", "images"):
        for index, entry in enumerate(_listing(document, section)):
            if isinstance(entry, dict) and entry.get("uri") is not None:
                raise InvalidDiorama(
                    f"{section[:-1].capitalize()} {index} points outside the file; "
                    "everything must be embedded."
                )


def _reject_unrenderable_extensions(document: dict) -> None:
    required = document.get("extensionsRequired") or []
    if not isinstance(required, list):
        raise InvalidDiorama("'extensionsRequired' must be a list.")
    unknown = sorted({str(name) for name in required} - _RENDERABLE_EXTENSIONS)
    if unknown:
        raise InvalidDiorama(
            "This model requires extensions the viewer cannot render: "
            + ", ".join(unknown)
        )


def _count_geometry(document: dict, limits: GlbLimits) -> dict[str, int]:
    nodes = len(_listing(document, "nodes"))
    meshes = _listing(document, "meshes")
    materials = len(_listing(document, "materials"))
    accessors = _listing(document, "accessors")

    primitives = 0
    vertices = 0
    for mesh in meshes:
        for primitive in _listing(mesh if isinstance(mesh, dict) else {}, "primitives"):
            primitives += 1
            if not isinstance(primitive, dict):
                raise InvalidDiorama("A mesh primitive is not an object.")
            position = (primitive.get("attributes") or {}).get("POSITION")
            # Summed from the accessors rather than read from a header: the
            # header is written by whoever made the file.
            if isinstance(position, int) and 0 <= position < len(accessors):
                accessor = accessors[position]
                if isinstance(accessor, dict):
                    vertices += int(accessor.get("count") or 0)

    for label, value, cap in (
        ("nodes", nodes, limits.max_nodes),
        ("meshes", len(meshes), limits.max_meshes),
        ("materials", materials, limits.max_materials),
        ("primitives", primitives, limits.max_primitives),
        ("vertices", vertices, limits.max_vertices),
    ):
        if value > cap:
            raise DioramaTooLarge(f"A model has at most {cap} {label} (found {value}).")
    return {
        "nodes": nodes,
        "meshes": len(meshes),
        "materials": materials,
        "primitives": primitives,
        "vertices": vertices,
    }


def _validate_embedded_images(document: dict, binary: bytes, limits: GlbLimits) -> int:
    images = _listing(document, "images")
    if len(images) > limits.max_images:
        raise DioramaTooLarge(
            f"A model carries at most {limits.max_images} textures "
            f"(found {len(images)})."
        )
    views = _listing(document, "bufferViews")
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            raise InvalidDiorama(f"Texture {index} is not an object.")
        view_index = image.get("bufferView")
        if not isinstance(view_index, int) or not 0 <= view_index < len(views):
            raise InvalidDiorama(f"Texture {index} names no readable bufferView.")
        view = views[view_index]
        if not isinstance(view, dict):
            raise InvalidDiorama(f"Texture {index} names no readable bufferView.")
        start = int(view.get("byteOffset") or 0)
        length = int(view.get("byteLength") or 0)
        if start < 0 or length < 0 or start + length > len(binary):
            raise InvalidDiorama(
                f"Texture {index} reads past the end of the model's binary chunk."
            )
        _check_texture(index, binary[start:start + length], limits)
    return len(images)


def _check_texture(index: int, data: bytes, limits: GlbLimits) -> None:
    try:
        with Image.open(BytesIO(data)) as probe:
            width, height = probe.size
    except Image.DecompressionBombError as exc:
        raise DioramaTooLarge(f"Texture {index} is a decompression bomb.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidDiorama(f"Texture {index} is not a readable image.") from exc
    if max(width, height) > limits.max_texture_side:
        raise DioramaTooLarge(
            f"Texture {index} is {width}x{height}; the limit is "
            f"{limits.max_texture_side} on a side."
        )
    if width * height > limits.max_texture_pixels:
        raise DioramaTooLarge(
            f"Texture {index} has more than {limits.max_texture_pixels} pixels."
        )


def _listing(document: dict, key: str) -> list:
    """A top-level glTF array, or an empty one. A non-list is a malformed file."""
    value = document.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidDiorama(f"'{key}' must be a list.")
    return value
