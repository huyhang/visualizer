# Logos

Logos is the manuscript service. A Chronos book is a novel series; Logos gives
that series ordered, numbered volumes, and gives each volume an ordered sequence
of prose sections.

Writing is API-first and stays that way: there is no editor UI. Reading has a
browser. In the combined deployment Logos is mounted at `/logos`: `/logos/`
opens the reader, and the paths in [`openapi.json`](openapi.json) are relative
to that mount.

## The reader

A read-only page over the existing reads. It opens a manuscript one volume at a
time and preserves the document's headings, lists, marks, links and stable block
ids. Two modes, remembered per browser:

- **Focused**, the default: the volume's structure and prose, and nothing else.
- **Full view**: the same prose, beside the Chronos scenes each section names in
  its `event_ids` — a title and a timeframe in the book's own calendar, and no
  more. It does not expand neighbouring scenes, plotlines or Akasha articles.

Focused is a guarantee rather than an intention. It is the only mode the page
loads in unless you have asked otherwise, and in it the reader issues no request
to `…/ui/scenes` at all, so nothing from another service can reach the page. In
Full view the scene ids come from the sections themselves; the endpoint takes no
parameter through which the browser could widen the set. A scene a section still
names but Chronos no longer has is shown as removed rather than dropped.

Akasha mentions and article links render as ordinary prose in both modes. The
browser builds DOM nodes from the validated rich-text vocabulary and never
inserts manuscript content as HTML; a link whose URL is not http, https or
site-relative renders as its own words instead. Prose written with a node type
this reader does not know degrades to a note on that section rather than a
guess.

The toolbar above the prose holds two buttons: the mode switch, whose tooltip
says what that mode shows, and **Reading settings**. The settings are a dialog
rather than a strip of controls you read past on the way to every chapter:

| | |
| --- | --- |
| Reading flow | the whole volume, or one section at a time |
| Typeface | serif or sans |
| Line spacing | normal or relaxed |
| Column width | narrow, medium or wide |
| Alignment | left or justified |

All five are remembered per browser and never touch the manuscript. "Reset
reading" restores those five. Theme and text size are *not* here: they are
shared across all four services and the header already owns them, so nothing in
this reader can undo a choice made in Articles.

A **contents** panel lists the volume's sections. Above 1100px it is a column
beside the prose; below that it collapses to a disclosure the reader opens when
they want it. Reading one section at a time also gives previous/next links, puts
the section in the address bar so a section is linkable, and marks the current
entry in the contents — reading the whole volume does not, because scrolling
past a heading is not the same claim as being on a section.

`LOGOS_URL` tells the shared navigation where the reader is. It defaults to
`/logos` in the combined stack and `http://localhost:5005` standalone.

## The model

- A manuscript belongs to an existing Chronos book. It copies nothing from it —
  not the title, not the world, not the permissions. Creating the first volume is
  what brings a manuscript into being; there is no "create manuscript" call.
- A **volume** has a stable id, a title, an optional overview, and a number
  derived from its position.
- A **section** is a `prologue`, `chapter`, `epilogue` or `glossary`. A volume may
  hold many chapters but at most one of each of the others. Chapters are numbered
  from chapter order; the other kinds are unnumbered.
- A section may name the Chronos events it realises, and stores one structured
  rich-text document.

Numbers, counts and links are computed on every read rather than stored, so
reordering cannot leave a stale number behind. `overview` is an editorial note,
not manuscript prose, and is not counted in word totals.

## The prose

A document is a list of blocks: paragraphs, headings, and bullet or ordered
lists. **Every block carries a stable `id`** that survives reordering and
re-editing, so an editor — or a comment anchored to a paragraph — keeps pointing
at the same prose after the text around it changes.

Inside a block: text with `em`, `strong`, `strike` and `code` marks, hard breaks,
external links, and `mention` / `article_link` references to Akasha articles.
Every node type is validated exhaustively and unknown fields are refused, so what
comes back is always the shape documented in the contract.

One section is capped at 4 MiB and one million characters of visible text, which
leaves ample room under MongoDB's per-document ceiling even with rich-text
structure around it.

## Editing and recovery

`PUT` replaces a whole volume or section. There is no paragraph-level write.

**Every mutation of an existing resource requires `If-Match`**, carrying the
revision from its last read; without one the request is refused with
`428 PRECONDITION_REQUIRED`, and a stale one gets `409 REVISION_CONFLICT`. This
is deliberately stricter than Chronos and Prithvi, which accept unconditional
writes: prose is the one thing in this stack that a lost update destroys beyond
reconstruction.

Section revisions are retained and restorable — 20 by default, set with
`LOGOS_SECTION_REVISIONS_KEEP`. Restoring never rewinds history: it writes a new
revision holding the older document, and revalidates it on the way in, so
restoring prose that names a since-deleted Chronos event is refused rather than
quietly reintroducing a dangling reference.

## References out

Two directions, deliberately different.

A Chronos **event** a section realises is a *hard* reference. Naming one that
does not exist is refused, and Chronos refuses to delete one a live section is
written from — `detach=true` does not override that, because detaching would
silently edit prose.

An Akasha **article** a paragraph mentions is *soft*. The prose keeps it, and
reads report it under `missing_refs`; `GET /books/{book}/report` lists every
section holding one. This mirrors how Chronos reports a deleted article and how
Prithvi hides a pin, and it means you can draft a scene mentioning a character
before you have written that character's article.

## Ownership and deletion

Logos reads the Chronos book grant directly. There is no second sharing model and
no migration for books that already exist — see
[`permissions.md`](permissions.md).

Deleting a Chronos book is blocked while its manuscript holds content; the
manuscript must be deleted explicitly first, and that is the only operation in
Logos that removes retained history. Deleting a non-empty manuscript or volume
requires `cascade=true`, so prose cannot disappear through an incidental parent
delete.

See [`openapi.json`](openapi.json) for the complete contract.
