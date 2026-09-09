# Akasha media library

Akasha stores private raster images and voxel dioramas in one reusable library
scoped to a world. Bytes live in GridFS; an article references them through
stable ids in its flat `body`, `gallery`, and `profile_image` fields, so
placement, captions, gallery order, and profile selection are part of normal
article history.

Both kinds are the same *asset* to the store — the sections below describe
images first, because dioramas inherit almost all of it and the last section
covers only what differs.

## Storage and processing

`MediaStore` is the injected MongoDB boundary. Each record names its world,
uploader, filename, format, dimensions, alternative text and three GridFS
blobs: the original, a bounded display copy and a thumbnail. The existing
`mongodump` backup therefore includes images without another volume or backup
procedure.

`ImageProcessor` accepts JPEG, PNG and static WebP. It verifies decoded content,
enforces both encoded-byte and decoded-pixel limits, corrects display orientation
and produces the two derived sizes. Upload limits come from environment-backed
configuration and are injected; processing and persistence do not read global
configuration.

The archived copy keeps every pixel of the upload but not the metadata attached
to it. `metadata.py` edits the container — dropping Exif (including GPS), XMP,
IPTC and PNG text chunks while keeping colour-critical records such as ICC
profiles and JFIF density — so nothing is decoded or re-compressed. This is what
the full-size view serves, so anything left in it would be published to every
reader of the article. An upload with nothing to remove is stored byte for byte.

Two rules keep the derived copies honest. A lossless WebP stays lossless, rather
than taking Pillow's lossy default. And a derivative is only kept when it is
smaller than what it derives from: resampling drawn artwork invents gradients a
small palette used to cover, which made thumbnails of the demo art twice the
size of the originals. Where a derivative loses that comparison the original is
served under its name and reports its own dimensions, and the store keeps one
copy of bytes that two variants share.

Uploading from the first draft in a not-yet-created category creates that
category before storing the image. Cancelling afterward leaves the upload in
the world library rather than silently destroying user data.

## Placement and reading

The editor inserts a line-level directive containing media id, alignment,
percentage width and a placement-specific caption. The reader turns a valid
directive into a semantic `figure`; malformed input remains inert text. Widths
are constrained to 10–100%, left and right placements allow text flow on wide
screens, and all placements become full-width on small screens.

The article uses the display variant. Clicking it opens an accessible modal
with the original and caption, initially fitted to the viewport and toggleable
to its natural size.

Every image inserted or uploaded while editing is also attached to the article.
The `gallery` field is an ordered flat array of `media-id|caption` strings; the
caption belongs to that article and may contain additional `|` characters.

Both image fields are reserved *conditionally*. Field names in this store belong
to the writer, so an article that has always listed its wings under `gallery`
keeps that list: the reader claims either name only when its contents parse as
image references, and treats it as an ordinary infobox fact otherwise. Nothing
is rejected for being inconsistent — a body image missing from the gallery still
renders, an unattached profile choice is simply not shown — because the editor
is what maintains the invariant and a stricter API would refuse documents that
predate the feature.

The editor can also attach an existing library image without inserting it in prose,
reorder attachments, and choose one attachment as `profile_image`. The profile
is rendered above the infobox at its natural aspect ratio with a height cap and
is excluded from the gallery grid at the bottom.

## Access and lifecycle

Existing Akasha grants remain the only content permissions. Upload requires
write access to the article context. A world reader sees the whole library; a
narrower collaborator sees their own uploads and images used in articles they
can read. Image delivery applies the same rule. The uploader or world owner may
edit alternative text or delete the image.

`GET …/media?orphans=1` names the visible images nothing points at any more, in
a current revision or a retained one. It deliberately matches the delete rule
rather than counting live articles only: an "orphan" that history still holds
would be offered for removal and then refuse to go.

Normal deletion scans body placements, gallery attachments and profile choices
across current articles and retained revisions, and refuses while any reference
remains. Forced deletion is explicit, reports every affected article revision,
and leaves a visible placeholder. This scan is deliberately the source of truth:
a separately maintained reference count could drift on the standalone MongoDB
deployment, which has no multi-document transaction joining an article update
to media metadata.

## Voxel dioramas

A diorama is a library entry like an image: same world scoping, same grants,
same reference scan guarding deletion, same storage accounting. What differs is
what it holds — a `.glb` and an optional poster — and that it carries a
presentation manifest the reader can edit without touching the geometry.

Sharing the library rather than sitting beside it is the whole design. A second
store would have meant a second answer to who may upload, who may see, what
blocks a delete and who is charged for the bytes; instead `assets.py` describes
an asset generically and `media_store.py` never reads a fact it stores.

### The gate

`gltf.py` decides what may be stored, before anything reaches a renderer. Three
questions, in order: is the file structurally what it claims (declared length
equals the bytes present, chunks fit inside them, only the two chunk types glTF
defines); does it reach outside itself (a `uri` on any buffer or image is
refused, because a stored model that fetches when opened would report who read
which article); and is it bounded (counts, texture sizes, and a vertex total
summed from the accessors rather than believed from a header).

Models needing extensions the viewer cannot honour — Draco, meshopt, basisu —
are refused rather than rendered wrong: losing the geometry silently is a worse
outcome than never loading.

`tests/akasha/test_vendored_three.py` closes the loop the gate cannot see by
loading a model through the actual vendored renderer and asserting three.js
counts the same vertices the gate did. If those drifted, the caps would be
guarding a different file from the one that renders.

### Geometry and presentation

Geometry is in the `.glb` and never changes; camera, rotation, and local lights
live in a versioned manifest under the same record. Re-aiming is
`PUT …/media/{id}/manifest` — a few numbers, not a multi-megabyte re-upload —
and the model's measured facts are carried across untouched because they
describe a file that did not change.

The writer reaches it from the full-size view, beside Pause and Reset:
**Adjust camera & lights** reopens the same form with the file input gone and
every value as it was, and the scene behind the dialog re-aims on save rather
than making the reader close and reopen to see the change. That placement is
the point — the camera is what is being judged, and the lightbox is the only
place the scene is large enough to judge it. The same button is in the image
library dialog for anyone already in the editor. Saving sends the manifest *and a re-shot poster*, because
moving the camera and retaking the still it was seen through are one act — the
route accepts multipart for exactly that, and JSON for scripts that have no
camera to photograph. The replaced poster's bytes are deleted once the record
points at the new ones, so a swap does not quietly leave storage behind.

Manifest values are refused rather than clamped. A form that turns a typed 250
into 100 has told the writer their input was accepted when it was replaced.
Azimuth is the exception and wraps, since 370° and 10° name the same camera.

### The poster cannot go stale

There is no GL in a Python process, so the server cannot render a preview. The
editor captures one from the scene it has already drawn, at save time, through
the camera the manifest describes — so the still and the manifest are made from
each other and cannot fall out of step. A diorama without a poster is fine: the
viewer simply builds the scene when it scrolls into view.

### Contexts are rationed

Every live scene holds a WebGL context and browsers cap those at roughly eight
to sixteen, silently dropping the oldest past the limit. Viewers therefore mount
on an `IntersectionObserver` and a pool of four retires the least recently seen
scene, so a long article decides which figure goes quiet rather than the
browser deciding for it. `dispose()` returns geometry, materials, textures,
controls and the renderer; without it every reopened lightbox leaks a context
and the symptom appears somewhere else on the page.

### three.js is vendored

`static/js/vendor/three/`, pinned at r180 with its licence, its README stating
the one divergence (bare specifiers repointed at the files beside them), and a
test that fails if an upgrade reintroduces a bare specifier or a remote URL.
`three.core.min.js` is included because `three.module.min.js` imports it —
omitting it 404s the entire JS entrypoint. The renderer is loaded by dynamic
import, so an article with no diorama in it never fetches the runtime.
