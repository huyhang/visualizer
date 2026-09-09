"""The GLB gate.

Every test here is a file someone could actually send. The renderer is not the
validator, so anything that reaches three.js has already been believed by this
module -- which makes the hostile cases the point of the file, not an appendix.
"""

import json
import struct
from io import BytesIO

import pytest
from PIL import Image

from visualizer.akasha.errors import DioramaTooLarge, InvalidDiorama
from visualizer.akasha.gltf import GlbLimits, validate_glb

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def _pad(payload: bytes) -> bytes:
    return payload + b" " * (-len(payload) % 4)


def _glb(document, binary=b"", *, magic=b"glTF", version=2, declared=None,
         chunks=None):
    """Assemble a .glb. Every field is overridable so a test can corrupt one."""
    body = b""
    if chunks is None:
        raw = _pad(json.dumps(document).encode())
        chunks = [(JSON_CHUNK, raw)]
        if binary:
            chunks.append((BIN_CHUNK, _pad(binary)))
    for kind, payload in chunks:
        body += struct.pack("<II", len(payload), kind) + payload
    total = 12 + len(body) if declared is None else declared
    return struct.pack("<4sII", magic, version, total) + body


def _cube(vertices=8, meshes=1, primitives=1):
    return {
        "asset": {"version": "2.0"},
        "accessors": [{"count": vertices, "type": "VEC3", "componentType": 5126}],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}}] * primitives}
        ] * meshes,
        "nodes": [{"mesh": 0}],
        "materials": [{"name": "stone"}],
    }


def _png(size=(8, 8)):
    out = BytesIO()
    Image.new("RGB", size, (90, 90, 110)).save(out, "PNG")
    return out.getvalue()


# -- the happy path ----------------------------------------------------------


def test_a_plain_model_is_accepted_and_described():
    facts = validate_glb(_glb(_cube(vertices=1200)))
    assert facts.vertices == 1200
    assert (facts.nodes, facts.meshes, facts.materials, facts.primitives) == (1, 1, 1, 1)
    assert facts.images == 0
    assert facts.has_binary_chunk is False
    assert facts.byte_length > 12


def test_an_embedded_texture_is_accepted():
    texture = _png()
    document = _cube()
    document["bufferViews"] = [{"buffer": 0, "byteOffset": 0, "byteLength": len(texture)}]
    document["images"] = [{"bufferView": 0, "mimeType": "image/png"}]
    facts = validate_glb(_glb(document, texture))
    assert facts.images == 1
    assert facts.has_binary_chunk is True


def test_a_renderable_extension_is_allowed():
    document = _cube()
    document["extensionsRequired"] = ["KHR_materials_unlit"]
    document["extensionsUsed"] = ["KHR_materials_unlit"]
    assert validate_glb(_glb(document)).extensions == ("KHR_materials_unlit",)


# -- the container lies ------------------------------------------------------


def test_an_empty_upload_is_refused():
    with pytest.raises(InvalidDiorama):
        validate_glb(b"")


def test_something_that_is_not_a_glb_is_refused():
    with pytest.raises(InvalidDiorama):
        validate_glb(b"PK\x03\x04" + b"\x00" * 64)


def test_a_truncated_header_is_refused():
    with pytest.raises(InvalidDiorama):
        validate_glb(b"glTF\x02\x00")


def test_glTF_1_is_refused():
    with pytest.raises(InvalidDiorama, match="2.0"):
        validate_glb(_glb(_cube(), version=1))


def test_a_file_that_misreports_its_own_length_is_refused():
    """The cheapest way to walk a naive reader past the bytes that arrived."""
    with pytest.raises(InvalidDiorama, match="bytes but"):
        validate_glb(_glb(_cube(), declared=1 << 30))


def test_a_chunk_running_past_the_end_is_refused():
    raw = _pad(json.dumps(_cube()).encode())
    body = struct.pack("<II", len(raw) + 4096, JSON_CHUNK) + raw
    with pytest.raises(InvalidDiorama, match="past the end"):
        validate_glb(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)


def test_an_unaligned_chunk_length_is_refused():
    raw = json.dumps(_cube()).encode() + b"x"  # deliberately not a multiple of 4
    with pytest.raises(InvalidDiorama, match="aligned"):
        validate_glb(_glb(None, chunks=[(JSON_CHUNK, raw)]))


def test_an_unknown_chunk_type_is_refused():
    """An allowlist: an unrecognised chunk is content nothing has inspected."""
    raw = _pad(json.dumps(_cube()).encode())
    payload = _pad(b"a stowaway")
    with pytest.raises(InvalidDiorama, match="chunk type"):
        validate_glb(_glb(None, chunks=[(JSON_CHUNK, raw), (0xDEADBEEF, payload)]))


def test_a_second_binary_chunk_is_refused():
    raw = _pad(json.dumps(_cube()).encode())
    with pytest.raises(InvalidDiorama, match="at most one BIN"):
        validate_glb(_glb(None, chunks=[
            (JSON_CHUNK, raw), (BIN_CHUNK, _pad(b"one")), (BIN_CHUNK, _pad(b"two")),
        ]))


def test_a_binary_chunk_before_the_json_is_refused():
    raw = _pad(json.dumps(_cube()).encode())
    with pytest.raises(InvalidDiorama, match="must come first"):
        validate_glb(_glb(None, chunks=[(BIN_CHUNK, _pad(b"early")), (JSON_CHUNK, raw)]))


def test_a_file_with_no_json_chunk_is_refused():
    """Caught as a BIN arriving first, which is the same disqualification."""
    with pytest.raises(InvalidDiorama, match="JSON chunk"):
        validate_glb(_glb(None, chunks=[(BIN_CHUNK, _pad(b"only binary"))]))


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'"a string"', b"\xff\xfe\x00"])
def test_unreadable_json_is_refused(raw):
    with pytest.raises(InvalidDiorama):
        validate_glb(_glb(None, chunks=[(JSON_CHUNK, _pad(raw))]))


# -- the model reaches outside itself ----------------------------------------


@pytest.mark.parametrize("section", ["buffers", "images"])
@pytest.mark.parametrize(
    "uri",
    [
        "https://example.invalid/tracker.bin",
        "//example.invalid/tracker.bin",
        "file:///etc/passwd",
        "data:application/octet-stream;base64,AAAA",
        "../../secret.bin",
    ],
)
def test_a_uri_on_a_buffer_or_image_is_refused(section, uri):
    """Opening an article must not become a request to somebody else's server.

    Even a data: URI is refused -- it is a second, unvalidated payload channel
    that never passes through the chunk walk above.
    """
    document = _cube()
    document[section] = [{"uri": uri}]
    with pytest.raises(InvalidDiorama, match="outside the file"):
        validate_glb(_glb(document))


# -- the model needs something we cannot render ------------------------------


@pytest.mark.parametrize(
    "extension",
    ["KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu"],
)
def test_an_extension_the_viewer_cannot_honour_is_refused(extension):
    """Rendering it wrong and losing the geometry silently is the worse outcome."""
    document = _cube()
    document["extensionsRequired"] = [extension]
    with pytest.raises(InvalidDiorama, match="cannot render"):
        validate_glb(_glb(document))


# -- the model is unbounded --------------------------------------------------


def test_bytes_are_capped():
    limits = GlbLimits(max_bytes=64)
    with pytest.raises(DioramaTooLarge, match="at most 64 bytes"):
        validate_glb(_glb(_cube()), limits)


def test_the_json_chunk_is_capped():
    document = _cube()
    document["extras"] = {"padding": "x" * 4000}
    with pytest.raises(DioramaTooLarge, match="JSON is at most"):
        validate_glb(_glb(document), GlbLimits(max_json_bytes=1024))


@pytest.mark.parametrize(
    "limits,match",
    [
        (GlbLimits(max_nodes=0), "nodes"),
        (GlbLimits(max_meshes=0), "meshes"),
        (GlbLimits(max_materials=0), "materials"),
        (GlbLimits(max_primitives=0), "primitives"),
        (GlbLimits(max_vertices=10), "vertices"),
    ],
)
def test_every_count_has_a_cap(limits, match):
    with pytest.raises(DioramaTooLarge, match=match):
        validate_glb(_glb(_cube(vertices=500)), limits)


def test_vertices_are_summed_from_the_accessors_not_believed_from_a_header():
    """A header saying 'four vertices' over a million-vertex accessor is exactly
    the file this cap exists to stop."""
    document = _cube(vertices=1_500_000)
    document["extras"] = {"vertexCount": 4}
    facts = validate_glb(_glb(document))
    assert facts.vertices == 1_500_000
    with pytest.raises(DioramaTooLarge, match="vertices"):
        validate_glb(_glb(document), GlbLimits(max_vertices=1_000_000))


def test_vertices_are_summed_across_every_primitive_of_every_mesh():
    facts = validate_glb(_glb(_cube(vertices=100, meshes=3, primitives=4)))
    assert facts.primitives == 12
    assert facts.vertices == 1200


# -- the model's textures ----------------------------------------------------


def test_a_texture_reading_past_the_binary_chunk_is_refused():
    document = _cube()
    document["bufferViews"] = [{"buffer": 0, "byteOffset": 0, "byteLength": 4096}]
    document["images"] = [{"bufferView": 0}]
    with pytest.raises(InvalidDiorama, match="past the end"):
        validate_glb(_glb(document, b"tiny"))


@pytest.mark.parametrize("view", [None, "zero", 99, -1])
def test_a_texture_naming_no_readable_bufferview_is_refused(view):
    document = _cube()
    document["bufferViews"] = [{"byteOffset": 0, "byteLength": 4}]
    document["images"] = [{"bufferView": view}]
    with pytest.raises(InvalidDiorama, match="bufferView"):
        validate_glb(_glb(document, b"abcd"))


def test_a_texture_that_is_not_an_image_is_refused():
    payload = b"not an image at all"
    document = _cube()
    document["bufferViews"] = [{"byteOffset": 0, "byteLength": len(payload)}]
    document["images"] = [{"bufferView": 0}]
    with pytest.raises(InvalidDiorama, match="not a readable image"):
        validate_glb(_glb(document, payload))


def test_an_oversized_texture_is_refused():
    texture = _png((64, 64))
    document = _cube()
    document["bufferViews"] = [{"byteOffset": 0, "byteLength": len(texture)}]
    document["images"] = [{"bufferView": 0}]
    with pytest.raises(DioramaTooLarge, match="on a side"):
        validate_glb(_glb(document, texture), GlbLimits(max_texture_side=32))


def test_a_texture_decompression_bomb_is_refused_by_pillows_own_guard():
    """The pixel count is read from the header; nothing decodes it."""
    Image.MAX_IMAGE_PIXELS, previous = 64, Image.MAX_IMAGE_PIXELS
    try:
        texture = _png((256, 256))
        document = _cube()
        document["bufferViews"] = [{"byteOffset": 0, "byteLength": len(texture)}]
        document["images"] = [{"bufferView": 0}]
        with pytest.raises(DioramaTooLarge):
            validate_glb(_glb(document, texture))
    finally:
        Image.MAX_IMAGE_PIXELS = previous


def test_the_texture_count_is_capped():
    texture = _png()
    document = _cube()
    document["bufferViews"] = [{"byteOffset": 0, "byteLength": len(texture)}]
    document["images"] = [{"bufferView": 0}] * 4
    with pytest.raises(DioramaTooLarge, match="textures"):
        validate_glb(_glb(document, texture), GlbLimits(max_images=2))


# -- malformed shapes that must not become a 500 -----------------------------


@pytest.mark.parametrize(
    "document",
    [
        {"nodes": "not a list"},
        {"meshes": [{"primitives": "not a list"}]},
        {"meshes": [{"primitives": ["not an object"]}]},
        {"images": ["not an object"], "bufferViews": [{"byteLength": 0}]},
        {"extensionsRequired": "not a list"},
        {"accessors": "not a list"},
    ],
)
def test_a_malformed_document_is_refused_rather_than_crashing(document):
    with pytest.raises((InvalidDiorama, DioramaTooLarge)):
        validate_glb(_glb({"asset": {"version": "2.0"}, **document}))
