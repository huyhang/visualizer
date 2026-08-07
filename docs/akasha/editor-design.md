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
| GET | `/databases` | databases the user can see (admin: all) |
| GET | `/databases/<db>/collections` | collections the user can see under `db` |
| GET | `/databases/<db>/collections/<col>/documents?limit=&after=` | paginated `read`-able doc ids + title preview |

Visibility is computed by a pure `browsing` helper over the user's grants and
the raw listing, so it is unit-testable without Mongo.

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
- `browsing.py` — `visible_databases/collections(grants, listing)` grant filters.

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
