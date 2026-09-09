"""The vendored renderer stays vendored.

Akasha ships three.js rather than fetching it, for the same reason `gltf.py`
refuses a model with an external `uri`: a page that pulls a renderer off
someone else's server tells that server who is reading which article. An
upgrade that reintroduces a bare specifier or a CDN URL would undo that
silently -- the page would still work, on a machine with a route to the
internet. So the arrangement is asserted rather than trusted.
"""

import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

_VENDOR = (
    Path(__file__).resolve().parents[2]
    / "src" / "visualizer" / "akasha" / "static" / "js" / "vendor" / "three"
)

# Real import/export statements only. The addons carry usage examples in their
# doc comments that name `three/addons/...` and a CDN host; those are
# documentation and were deliberately left as upstream wrote them.
# `\s*` not `\s+`: minified code writes `}from"./three.core.min.js"` with no
# space at all, and requiring one made this miss every import in the builds.
_STATEMENT = re.compile(
    r"""(?:^|\n)[ \t]*(?:import|export)\b[^;]*?\bfrom\s*['"]([^'"]+)['"]""",
    re.MULTILINE | re.DOTALL,
)

_EXPECTED = {
    "three.module.min.js",
    "three.core.min.js",
    "OrbitControls.js",
    "GLTFLoader.js",
    "BufferGeometryUtils.js",
}


def _modules():
    return sorted(_VENDOR.glob("*.js"))


def _imports(path: Path):
    return _STATEMENT.findall(path.read_text())


def test_every_file_the_viewer_needs_is_present():
    assert {path.name for path in _modules()} == _EXPECTED


def test_the_core_build_is_here_because_the_module_build_imports_it():
    """Shipping three.module.min.js alone 404s the entire JS entrypoint."""
    assert "./three.core.min.js" in _imports(_VENDOR / "three.module.min.js")
    assert (_VENDOR / "three.core.min.js").exists()


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_import_reaches_off_this_machine(path):
    for specifier in _imports(path):
        assert not specifier.startswith(("http:", "https:", "//")), specifier


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_import_is_a_bare_specifier(path):
    """`from 'three'` needs an import map or a bundler. Akasha has neither, so
    a bare specifier here is a page that does not load."""
    for specifier in _imports(path):
        assert specifier.startswith("."), f"{path.name} imports {specifier!r}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_every_import_resolves_to_a_file_that_exists(path):
    for specifier in _imports(path):
        assert (path.parent / specifier).resolve().exists(), specifier


def test_the_licence_travels_with_the_code():
    licence = (_VENDOR / "LICENSE.txt").read_text()
    assert "MIT" in licence
    assert "three.js authors" in licence


def test_the_readme_records_the_pin_and_the_divergence():
    """A vendored dependency nobody can date is one nobody will upgrade."""
    readme = (_VENDOR / "README.md").read_text()
    assert "r180" in readme
    assert "./three.module.min.js" in readme


# -- the bundle actually runs -------------------------------------------------


def _node_binary():
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel
    except ImportError:
        return None
    executable = "node.exe" if sys.platform == "win32" else "node"
    candidate = Path(nodejs_wheel.__file__).parent / "bin" / executable
    return str(candidate) if candidate.exists() else None


def _minimal_glb():
    """A real cube: eight positions in a BIN chunk, indexed into triangles.

    Built here rather than shared with the diorama generator under ``docker/``.
    That script builds voxel grids with palettes and face culling; this needs
    the smallest file three.js will actually load, and a fixture that explains
    itself in one screen is worth more than one import fewer.
    """
    corners = [
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
    ]
    faces = [
        (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
        (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0),
    ]
    positions = b"".join(struct.pack("<3f", *corner) for corner in corners)
    indices = b"".join(struct.pack("<3H", *face) for face in faces)
    binary = positions + indices
    binary += b"\x00" * (-len(binary) % 4)

    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [
            {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}
        ]}],
        "materials": [{"pbrMetallicRoughness": {
            "baseColorFactor": [0.4, 0.45, 0.6, 1.0], "metallicFactor": 0.0}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(corners),
             "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]},
            {"bufferView": 1, "componentType": 5123, "count": len(faces) * 3,
             "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions),
             "target": 34962},
            {"buffer": 0, "byteOffset": len(positions),
             "byteLength": len(indices), "target": 34963},
        ],
        "buffers": [{"byteLength": len(binary)}],
    }
    raw = json.dumps(document).encode()
    raw += b" " * (-len(raw) % 4)
    body = struct.pack("<II", len(raw), 0x4E4F534A) + raw
    body += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


_DRIVER = """globalThis.self = globalThis;
import * as THREE from "./three.module.min.js";
import { GLTFLoader } from "./GLTFLoader.js";
import { OrbitControls } from "./OrbitControls.js";
import { readFileSync } from "node:fs";
const bytes = readFileSync(new URL("./model.glb", import.meta.url));
const buffer = bytes.buffer.slice(
  bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
new GLTFLoader().parse(buffer, "", (gltf) => {
  let vertices = 0, meshes = 0;
  gltf.scene.traverse((n) => {
    if (n.isMesh) { meshes++; vertices += n.geometry.getAttribute("position").count; }
  });
  const size = new THREE.Box3().setFromObject(gltf.scene).getSize(new THREE.Vector3());
  console.log(JSON.stringify({revision: THREE.REVISION, meshes, vertices,
    orbit: typeof OrbitControls, size: [size.x, size.y, size.z]}));
}, (e) => { console.error(String(e)); process.exit(1); });
"""


def test_the_vendored_bundle_loads_and_agrees_with_the_gate(tmp_path):
    """The end the gate cannot see.

    ``gltf.py`` counts vertices by summing accessors; three.js counts them by
    building the geometry. If those disagreed, the caps would be guarding a
    different file from the one that renders. So a model the gate accepted is
    loaded by the vendored renderer here, and the two counts are compared.

    The driver sets ``self`` first: three reaches for that browser global when
    decoding textures, and node has none. Nothing to do with the vendoring.
    """
    from visualizer.akasha.gltf import validate_glb

    node = _node_binary()
    if node is None:
        pytest.skip('no node available -- `pip install -e ".[dev]"` provides one')

    model = _minimal_glb()
    facts = validate_glb(model)

    for path in _VENDOR.glob("*.js"):
        shutil.copy(path, tmp_path / path.name)
    (tmp_path / "package.json").write_text('{"type": "module"}')
    (tmp_path / "model.glb").write_bytes(model)
    (tmp_path / "driver.mjs").write_text(_DRIVER)

    done = subprocess.run(
        [node, str(tmp_path / "driver.mjs")],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr
    loaded = json.loads(done.stdout)

    assert loaded["revision"] == "180"
    assert loaded["orbit"] == "function"
    assert loaded["meshes"] == facts.meshes
    assert loaded["vertices"] == facts.vertices, "the gate and the renderer disagree"
    assert loaded["size"] == [1, 1, 1]


def test_every_vendored_file_is_actually_served(client):
    """The top-level module check globs `static/js/*.js` and never descends, so
    the renderer could be present on disk and 404 over HTTP. That is the exact
    shape of the bug this vendoring is guarding against."""
    for path in [*_modules(), _VENDOR / "LICENSE.txt"]:
        resp = client.get(f"/static/js/vendor/three/{path.name}")
        assert resp.status_code == 200, path.name
