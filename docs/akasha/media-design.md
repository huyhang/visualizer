# Akasha image library

Akasha stores private raster images in a reusable library scoped to one world.
The original bytes and generated variants live in GridFS. An article references
them through stable ids in its flat `body`, `gallery`, and `profile_image`
fields, so placement, captions, gallery order, and profile selection are part of
normal article history.

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
caption belongs to that article and may contain additional `|` characters. The
editor can also attach an existing library image without inserting it in prose,
reorder attachments, and choose one attachment as `profile_image`. The profile
is rendered above the infobox at its natural aspect ratio with a height cap and
is excluded from the gallery grid at the bottom.

## Access and lifecycle

Existing Akasha grants remain the only content permissions. Upload requires
write access to the article context. A world reader sees the whole library; a
narrower collaborator sees their own uploads and images used in articles they
can read. Image delivery applies the same rule. The uploader or world owner may
edit alternative text or delete the image.

Normal deletion scans body placements, gallery attachments and profile choices
across current articles and retained revisions, and refuses while any reference
remains. Forced deletion is explicit, reports every affected article revision,
and leaves a visible placeholder. This scan is deliberately the source of truth:
a separately maintained reference count could drift on the standalone MongoDB
deployment, which has no multi-document transaction joining an article update
to media metadata.
