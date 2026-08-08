# Design: Authenticated Wikipedia-style Editor + Versioning

This document is the agreed design for a mobile-friendly, browser-based editor
on top of the existing `akasha`, plus document versioning and
version comparison. It is the reference for the implementation; the running code
is the source of truth for anything this doc drifts from.

## Goals

- Only an authenticated user may use the editor.
- Simple but sleek, with a user-selectable light/dark theme.
- CRUD entities as the caller's grants allow; browse everything they can read.
- A linking mechanism: while reading, tapping a reference loads that article;
  while editing, the same convention makes it easy to reference another article.
- The server supports versioning and an intuitive comparison of any two
  retained versions.
- Articles read/edit like a Wikipedia page, never like raw JSON.

## Principles (consistent with the existing codebase)

- **Inversion of control.** New persistence is a Mongo *seam* injected into
  `create_app`, exactly like `DocumentStore`/`AuthStore`. New logic is expressed
  as **pure, DB-free, unit-testable** modules like `authz.py`/`validation.py`.
- **No new build toolchain.** The editor is **vanilla JS + CSS** served as
  static assets by Flask. No npm/webpack/Node — nothing added to the slim NAS
  image, nothing to break in Container Manager, and no runtime CDN dependency
  (works on a LAN-only NAS).
- **Reuse the existing auth + grant model unchanged.** Every new endpoint goes
  through the same `_authorize(...)` / `is_allowed(...)` path. No new permission
  concepts.
- **Small, modular routes.** New endpoints live in focused registration
  functions so `app.py` stays a thin orchestrator.
- **Optimise what is perceptible, and only after measuring.** The bar is
  milliseconds at a realistic size, not a complexity class — measure before
  changing anything, and weight the cost by how often the call actually fires.
  Work that is already imperceptible is finished; leave it alone rather than
  spending the simplicity budget on it. Stated in full, with the numbers that
  produced it, in [chronos/design.md §2](../chronos/design.md#2-principles-consistent-with-the-existing-codebase).

## Data model

Documents remain flat JSON objects, with two additional constraints and two
internal fields.

- **Flat rule (new, validated on create *and* update):** each value is a
  **scalar** (`str`, `int`, `float`, `bool`, `null`) **or a flat array of
  scalars**. No nested objects, no arrays of arrays/objects. This keeps the
  editor form and the diff intuitive. Violations return `400`.
- **`_rev` (internal):** an integer optimistic-concurrency counter, starts at
  `1` on create, `$inc`-remented on every successful write.
- **`_history` (internal):** a capped array of the last *N* snapshots (default
  `N = 20`, configurable via `VERSIONS_KEEP`). Each snapshot is
  `{rev, op, author, timestamp, document}` where `op ∈ {create, update, delete}`
  and `document` is the full body at that rev (deletes store a tombstone).

`_id`, `_rev`, and `_history` are Mongo-internal: they are **stripped from the
normal public read** and surfaced only where relevant (`rev` alongside a read;
`_history` only through the version/diff endpoints).

### Why embed history (NAS constraint)

The NAS runs a **single standalone `mongod`**, which has **no multi-document
transactions** (those require a replica set). Writing the document and a
snapshot to two places therefore cannot be atomic. Embedding the capped history
on the document means a single atomic `find_one_and_update` does **OCC guard +
field update + rev bump + snapshot append + keep-last-N prune** in one write:

```python
find_one_and_update(
    {"_id": id, "_rev": expected},                 # OCC guard
    {"$set": <new fields>,
     "$inc": {"_rev": 1},
     "$push": {"_history": {"$each": [snapshot], "$slice": -N}}},  # keep last N
    return_document=AFTER)
```

All operators (`find_one_and_update`, `$inc`, `$push`/`$slice`) work on
**MongoDB 4.4** too, so this is safe on the AVX-less-CPU fallback the README
documents. With flat docs and `N = 20`, embedded history is tiny (well under the
16 MB BSON limit).

## Optimistic concurrency control (OCC)

Concurrent updates to the same article are **last-write-wins** in the current
code — a silent lost-update bug. The design replaces that with OCC:

- Every read returns the document's `rev`; the editor holds it.
- Mutating routes accept the expected rev via an **`If-Match`** header (with a
  `_rev` query-param fallback for curl; `*` means unconditional). It is
  **optional but enforced when present**: the browser editor always sends it (so
  it gets full OCC + conflict detection), while raw API/curl callers may omit it
  and get simple last-write-wins — this keeps the documented scriptable API
  backward-compatible. `GET` returns the rev both in the body and as an `ETag`.
- The store's update/delete are conditional on `_rev` (see the atomic write
  above). Three outcomes:
  - document does not exist → `DocumentNotFound` (404)
  - exists but `_rev` mismatches → `RevisionConflict` (409)
  - matches → succeeds; the returned new `_rev` **is** the version number
    recorded, so version numbering is race-free by construction.

**Conflict UX:** on a 409 the editor re-fetches the current document, runs the
diff engine between *the user's in-progress edit* and *the current server
version*, and shows a "this article changed while you were editing" panel with
that diff, offering **Reload theirs**, **Keep mine (overwrite)** (re-submit with
the fresh rev), or a field-by-field manual merge.

## Backend API additions

All new endpoints are authenticated and authorized through the existing
`_authorize` / `is_allowed` path; reads require `read`, writes `write`, deletes
`delete`. Reserved (`_`-prefixed) databases stay non-addressable.

### Browse (grant-filtered, like search already is)

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/databases` | databases the user can see, each with `{title, collections, articles}` |
| GET | `/databases/<db>/collections` | collections under `db`, with `{title, articles, can_write, can_delete}` |
| GET | `/databases/<db>/collections/<col>/documents?filter=&page=&per_page=` | one page of `read`-able articles + `{page, pages, total, can_write, can_delete}` |
| GET | `/recent?limit=` | most recently written readable articles, newest first |
| GET | `/databases/<db>/collections/<col>/deleted` | tombstones + `restore_rev` + `can_restore`, so recovery is browsable |
| DELETE | `/databases/<db>/collections/<col>?purge=` | drop a collection you own once no live article is left; drops the database too if it was the last |
| DELETE | `/databases/<db>` | drop a database with no collections left |

Each level answers with enough to **render a page**, not just a list of names:
how much is inside, and whether the caller may add to it — so the browser can
show counts and never draw a button that would only earn a `403`.

Visibility is computed by a pure `browsing` helper over the user's grants and
the raw listing, so it is unit-testable without Mongo. So are the filter,
ordering and paging: `browse_articles(rows, query, page, per_page)` is the same
shape as `chronos.browsing._browse`, and clamps an out-of-range page to the last
one rather than erroring — which is what happens when a filter narrows the list
under someone who was on page 4. The filter matches every typed word against the
whole article (slug, title and field values), so the box on a collection page is
the full-text search the API always had.

**Readable names.** A namespace is addressed by its slug and always will be, so
`labels.derive_title` renders one for display instead: `ember-pact` -> "Ember
Pact", `lord-of-the-rings` -> "Lord of the Rings", and a name that already has a
capital is returned untouched (title-casing `McTavish` would ruin it). Nothing is
stored, so it needs no migration and applies to everything that already exists.

It is derived **server-side** and shipped as `title` beside `name` — the browser
prints what it is given rather than deriving its own subtly different version.
That matters because both the SPA and the Jinja pages need it, and this way there
is one implementation rather than the pair that `terms.py`/`terms.js` has to keep
in step. Templates get it as the `| title_of` filter.

Counting is grant-aware but not expensive: a user holding a collection-wide
`read` gets one `count_documents`, and only someone with document-scoped grants
pays for a per-id check — and then over ids alone, not whole documents.

**Recovering a deleted article.** A delete is soft, so nothing is destroyed —
but a tombstone is hidden from every listing, search and suggestion, which for a
while meant an article could only be recovered by already knowing the slug you
had lost. Two routes back, both reading the history the tombstone still carries:

- Its **own address** still answers. The read 404s, so the page asks for
  `/versions`; a newest snapshot with `op: delete` means it was deleted rather
  than never written, and the page says by whom and when and offers *Restore*.
  This is the route a stale `[[link]]` and the Chronos `MISSING_ENTITY` finding
  both lead to, which is why it had to work.
- Its **category page** carries a collapsed drawer listing what was deleted from
  it, for when the slug is the thing you have forgotten. Loaded on demand, so a
  category with nothing deleted pays nothing.

Which version comes back is `history.last_live_snapshot` — the newest snapshot
that still holds a body, skipping the tombstone. It returns `None` when pruning
has aged out every body, and the UI says *history pruned* rather than offering a
button that would 404.

**Deleting a namespace** distinguishes two kinds of "not empty". A **live**
article always refuses: emptying a collection is the article endpoint's job, not
a side effect of tidying. A **tombstone** holds no article, only the version
history of one that was deleted — so it refuses by default, and goes only when
the caller passes `?purge=1`, having been told how many there are. Without that
escape hatch a collection that had ever held anything could never be removed,
because deletes are soft; with it, the one irreversible act in akasha is behind
a dialog that names what it costs.

Dropping the last collection drops the database, so an abandoned "new article"
cannot strand a namespace nobody can reach — and it is also the only way a
database goes, since MongoDB does not keep one with no collections in it.
`DELETE /databases/<db>` is a safety net for a shell left by an older version;
it is gated on nothing but login, exactly like *creating* a namespace, because
an empty database holds nothing to protect and emptying it was already
owner-only. The browse response carries `empty` so the UI can tell "there is
nothing here" apart from "there is nothing here *you* may read", and only offers
the button for the first.

### Suggest (link type-ahead)

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/suggest?q=<prefix>&db=&col=` | top-N `{slug, title, database, collection}` the caller can `read`, ranked current-collection → current-db → rest, with a light recency boost |

### Versions, diff, restore

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `…/documents/<id>/versions` | list retained snapshot metadata (rev, op, author, timestamp) — no bodies |
| GET | `…/documents/<id>/versions/<n>` | one snapshot |
| GET | `…/documents/<id>/diff?from=<a>&to=<b>` | structured comparison of two retained versions (404 if a version was pruned) |
| POST | `…/documents/<id>/restore/<n>` | re-submit snapshot `n`'s body as a **new** rev (append-only; goes through OCC + versioning) |

### CSRF

The JSON document/browse/version routes stay CSRF-exempt and rely on the
existing **`SameSite=Lax`** session cookie, which browsers already refuse to
send on cross-site `POST`/`PUT`/`DELETE` — a solid CSRF defense for a JSON API.
Keeping the routes exempt preserves the documented, scriptable curl API
unchanged. The server-rendered `/admin` and auth forms keep their existing
Flask-WTF `csrf_token` protection.

## Pure modules (no Mongo/Flask, unit-tested)

- `validation.py` — extend `validate_document` with the flat/scalar-or-flat-array
  rule.
- `diff.py` — `diff_documents(old, new)` → structured field diff
  (added/removed/changed), with a **word-level inline diff** on changed string
  values (via stdlib `difflib`); added/removed elements for arrays.
- `history.py` — build a snapshot record and apply keep-last-N pruning.
- `browsing.py` — `visible_databases/collections(grants, listing)` grant filters,
  `can_write_in_collection` / `can_delete_collection` (the permission hints the
  browse responses carry), and the article-list transform:
  `matches_all_words`, `browse_articles`, `most_recent`.

Linking token parsing, wikitext rendering, and shortest-token computation are
**frontend** concerns (see below); the backend only resolves reads and powers
`/suggest`.

## Frontend — vanilla-JS editor (replaces home `/`)

Served at `/` behind `@login_required` via a thin Jinja shell that loads static
ES modules. Talks only to the JSON API with the session cookie (+ CSRF token on
writes). Existing `/login`, `/register`, and server-rendered `/admin` are
unchanged.

### The Wikipedia illusion (presentation only — no backend model change)

A flat document maps onto an article:

| Document part | Article element |
| --- | --- |
| the doc `id` | the page **slug** (its link target) |
| a `title` field | the display **heading** |
| a `body` field (long string) | the **article prose** (wikitext) |
| every other field | a row in the **infobox** |
| a flat array field | an infobox row rendered as **chips/tags** |

`title`/`body` are ordinary string fields (no schema change). Docs created via
the raw API without them degrade gracefully — the slug is the heading and all
fields show as infobox facts.

### Body markup: wikitext-like subset

A pure renderer parses a MediaWiki-style subset to **sanitized** HTML:
`'''bold'''`, `''italic''`, `== headings ==`, `* lists`, and
`[[link]]` / `[[link|label]]`. Only the known subset and our own link chips are
emitted; everything else is escaped (prevents stored XSS). The same renderer is
used in three places: article read view, live edit preview, and the version diff
view (so a body diff reads as formatted prose, Wikipedia-style).

### Linking

- **Convention:** `[[db/collection/id]]`, with shorthands `[[collection/id]]`
  (same db) and `[[id]]` (same collection).
- **Read:** links render as tappable chips showing the **target's title** (lazy
  fetched), `[[slug|label]]` uses the label; unresolvable/forbidden links render
  dimmed ("red links").
- **Edit:** typing `[[` (or an "Insert link" toolbar button) opens a
  **type-ahead** over `/suggest` (all readable articles, nearest-first). Picking
  a target inserts the **shortest unambiguous token** relative to the current
  article, with the title pre-filled as the label. If nothing matches, a
  **"Create '…'"** option opens a quick create flow (defaults to the current
  collection, gated by `write`), creates the stub (v1), and inserts the link.
- The same picker is available for infobox field values (a fact can be a link or
  an array of links).

### Versions & compare workflow

- A normal read shows the current version; the user never specifies a version.
- A **History** panel lists retained versions newest-first. Each older row has a
  one-tap **"Compare with current"** (UI resolves `diff?from=rev-1&to=rev`);
  arbitrary pairs are also selectable. Pruned versions are greyed out.
- **Restore** re-submits an old body as a new rev.
- Diff renders field-by-field: **added** (green), **removed** (red), **changed**
  (amber, inline word diff on strings); arrays show added/removed elements. Side
  by side on desktop, stacked on mobile.

### Theme & layout

- Light/dark **user-selectable** toggle, persisted in `localStorage`, defaulting
  to `prefers-color-scheme`; reuses the CSS-variable palette from `base.html`.
- Mobile-first single column with a browser drawer; two-pane on desktop.
- A hidden **"Advanced"** toggle reveals a raw flat-field editor for power users;
  it edits the same document through the same validation/OCC/versioning path.
- Small ES modules, one responsibility each: `api.js`, `browser.js`,
  `viewer.js`, `editor.js`, `links.js`, `wikitext.js`, `history.js`, `theme.js`.

### Browsing: a route per level

The hash router covers every level of the hierarchy, not just the leaf:

    #/                  pick a database        (cards + "recently edited")
    #/<db>              pick a collection      (cards)
    #/<db>/<col>        the article list       (filter, order, pages)
    #/<db>/<col>/<id>   one article
    #/_search           search a collection in detail

Giving each level a page is what makes the rest possible: somewhere to browse,
and somewhere for a **"New …" button that already knows where it is** to live.
Creating is therefore *scoped* — the collection page's "New article" asks only
for a title; the header's asks for the rest with dropdowns of what already
exists, never a blank box you must fill from memory. (`_search` cannot collide
with a real database: the API reserves every `_`-prefixed name.)

Nothing is created as a side effect of opening a dialog. A new article's
collection is created on **save** (`pendingCollection`), routed through the
caller rather than the editor — which knows about articles, not namespaces — so
backing out leaves nothing behind. Cancelling then returns to the database page,
since the collection's own page does not exist yet.

### The tree navigates; the category page enumerates

Keeping those apart is what makes the sidebar work at any size. The tree holds
itself to one invariant — **it never renders more than 20 articles under a
category, whatever is typed** — and hands off to the category page the moment
that stops being enough, so the length of the sidebar is a property of the
design rather than of the world.

Above ~30 articles a category grows a filter box, and it matches **names only**
(`?match=name`), unlike the full-text filter on the page itself. A narrow column
has nowhere to show *why* a body match matched, so those read as mystery hits,
and one common word would return half the world. When more match than fit, the
server has already ordered them best-first — exact name, prefix, word start,
anywhere (`browsing.match_rank`) — so the twenty shown are the twenty most
likely meant, rather than twenty A-names. The overflow row **carries the query
across**, opening the page already filtered and widened to the whole article.

It is also a real tree for the keyboard: `role="tree"`/`treeitem`,
`aria-expanded`, a roving tabindex, and arrows to move, expand and collapse.

The rest of its manners: it remembers what was expanded, refreshes one branch
rather than rebuilding from the root, unfolds to reveal an article opened from a
link, and never truncates silently. Counts are corrected from the listing that
just loaded, and always count *articles* — the badge meaning collections at one
level and articles at the next was a small lie the eye had to decode. One glyph
per level (filled square, outline square, dot) so the three depths read as three
kinds of thing rather than three amounts of indentation. Search results appear
*above* the tree instead of replacing it, because looking something up should
not cost you the place you had unfolded to, and the sidebar itself is
drag-resizable, remembered like the theme.

New view modules: `views.js` (breadcrumbs, heading, cards, pager, `timeAgo`),
`namespaces.js`, `articles.js`, `create.js`, `search.js`.

## Configuration

`VERSIONS_KEEP` (default `20`) is read **only** in `config.py`
(`get_versions_keep()`), passed into `create_app(..., versions_keep=...)`, and
injected down to `DocumentStore` / the pure `history` prune. Tests inject the
int directly (no env), exactly like `secret_key`. Set it in `docker/.env`; both
compose files pass `VERSIONS_KEEP: ${VERSIONS_KEEP:-20}`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `VERSIONS_KEEP` | max version snapshots retained per article (older pruned) | `20` |

## Testing

- Pure modules (`validation`, `diff`, `history`, `browsing`) → direct unit
  tests, no Mongo.
- `DocumentStore` → mongomock + injected fixed clock: OCC interleave (read v5
  twice, update once, second update 409s), versioning append + keep-last-N,
  `list_*`.
- Endpoints → Flask test-client tests mirroring `test_api.py`, covering authz
  (401/403), grant-filtered browsing/suggest, version/diff/restore, and CSRF.

## Deployment impact

Additive: static files bundle into the existing image; no new services, no Mongo
port change; single standalone `mongod` unchanged (embedded history needs no
replica set); LAN-friendly (no CDN); reverse-proxy ready; no websockets. Only
new config is the optional `VERSIONS_KEEP`.
