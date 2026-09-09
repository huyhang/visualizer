# three.js r180, vendored

Upstream: <https://github.com/mrdoob/three.js/tree/r180> — MIT, `LICENSE.txt`
carried beside these files unmodified.

Vendored rather than loaded from a CDN because Akasha is a private,
self-hosted wiki: a page that fetches a renderer from someone else's server
tells that server who is reading which article, which is the same objection
that makes `gltf.py` refuse a model with an external `uri`. It also means the
viewer keeps working on a NAS with no outbound route.

## What differs from upstream

Nothing but module specifiers. Each file below is byte-identical to the
r180 tag except that its `import ... from` statements were repointed at the
copies sitting beside it:

| Rewritten | To |
| --- | --- |
| `'three'` | `'./three.module.min.js'` |
| `'../utils/BufferGeometryUtils.js'` | `'./BufferGeometryUtils.js'` |

Doc-comment examples inside these files still name `three/addons/...` and a CDN
host. Those are documentation, not imports, and were deliberately left alone.

## Files

| File | Why it is here |
| --- | --- |
| `three.module.min.js` | the renderer |
| `three.core.min.js` | **required** — `three.module.min.js` imports it; omitting it 404s the whole entrypoint |
| `OrbitControls.js` | orbits the camera around a fixed scene, and supplies `autoRotate` |
| `GLTFLoader.js` | parses the `.glb` the gate has already validated |
| `BufferGeometryUtils.js` | `GLTFLoader` imports `toTrianglesDrawMode` from it |

`tests/akasha/test_vendored_three.py` holds this arrangement in place: it fails
if an upgrade reintroduces a bare specifier or a remote URL in an import, or
drops a file another one imports.
