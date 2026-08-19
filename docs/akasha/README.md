# akasha

A small Flask + MongoDB service for storing, linking and versioning JSON
documents, secured with user accounts and fine-grained access control. It is the
**canon** half of the [visualizer](../../README.md) stack: the record of what
exists in your world.

> *Akasha* — the Sanskrit term for the aether said to hold a record of all
> things. Formerly called `document-server`.

There are two ways to use it:

- **The web UI** — a mobile-friendly, Wikipedia-style **article editor** (the
  app's home page) for browsing, reading, creating, editing, deleting and
  cross-linking documents, with a light/dark theme and per-article version
  history you can diff and restore.
- **The HTTP/JSON API** — the same capabilities from code. Examples below use
  Python + [`requests`](https://requests.readthedocs.io/).

Both share one login, one permission model, and one document store. See
[`editor-design.md`](editor-design.md) for the full design, and the
[repo README](../../README.md) for the stack as a whole.

> **Companion service — `chronos`.** A plotline & timeline API for fiction
> writers, deployed alongside this one on port 5003 and sharing its MongoDB and
> login. Characters, items and locations are articles *here*; chronos references
> them to build books, plotlines and events, and checks the story for continuity
> errors. See [`chronos/README.md`](../chronos/README.md) (setup + API),
> [`chronos/OVERVIEW.md`](../chronos/OVERVIEW.md) (plain language), and
> [`chronos/design.md`](../chronos/design.md) (design).

---

## Run it

The service is two containers — `akasha` (the app) and `mongo` —
defined in `docker/docker-compose.nas.yml`. MongoDB has **no published port**; it
is reachable only from inside the Docker network, never from the host.

```bash
# 1. Set the cookie-signing secret (git-ignored, auto-loaded by compose)
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > docker/.env

# 2. Build and start
docker compose -f docker/docker-compose.nas.yml up --build -d

# App on http://localhost:5002
```

Then open **http://localhost:5002/** and **register the first account — it
becomes the administrator**. Everyone after them registers as a plain user whom
the admin grants access.

**Configuration** (environment variables, set in `docker/.env`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | signs session cookies — **required**; compose refuses to start without it. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. | none (must be set) |
| `MONGO_URI` | MongoDB connection string | `mongodb://mongo:27017` |
| `VERSIONS_KEEP` | max version snapshots kept per article (older pruned) | `20` |
| `SESSION_COOKIE_SECURE` | mark the session cookie HTTPS-only (enable behind an HTTPS reverse proxy) | `false` |
| `MONITORING_ENABLED` | record per-writer usage, latency and errors at boot (the admin page can pause it at runtime) | `true` |
| `MONITORING_DATA_PATH` | path whose free space represents the NAS data volume | `/data` |
| `MONITORING_FLUSH_SECONDS` | how often accumulated telemetry is written out (minimum 10) | `300` |
| `MONITORING_SCAN_SECONDS` | how often storage attribution and host capacity are re-measured (minimum 60) | `3600` |

Useful commands: `docker compose -f docker/docker-compose.nas.yml logs -f
Akasha` (logs) and `... down` (stop; add `-v` to also wipe the data
volume).

> **Run locally without Docker** (after `pip install -e ".[dev]"` in a 3.11
> environment — see [Development & tests](#development--tests) — and with a
> MongoDB you can reach):
> ```bash
> SECRET_KEY=dev MONGO_URI=mongodb://localhost:27017 \
>   gunicorn -b localhost:5002 visualizer.akasha.wsgi:app
> ```

---

## Using the web UI

Everything below is gated by your permissions — you only ever see and edit what
you have been granted. This includes admins: the admin role governs account and
access *management*, not content access, so an admin sees another user's articles
only where they have explicitly granted themselves (or been granted) access.

> **A note on names.** The UI speaks to a novelist: a **world** holds
> **categories** (characters, locations, lore…) of **articles**. The API keeps
> MongoDB's words for the same three things — *database → collection →
> document* — because that triple is the addressing scheme behind every link,
> grant and chronos reference. The mapping is one table, in
> [`terms.py`](../../src/visualizer/akasha/terms.py).
>
> Individual worlds and categories are printed readably too: `ember-pact` shows
> as **Ember Pact**, `lord-of-the-rings` as **Lord of the Rings**. The title is
> *derived* from the slug ([`labels.py`](../../src/visualizer/akasha/labels.py)) —
> nothing is stored, so it applies to everything that already exists, and a name
> that already has capitals is left exactly as you spelled it. The slug stays
> beside it on cards and in URLs, because that is what `[[links]]` point at.

**Browse & read.** Every level has a page of its own. The home page is a grid of
your worlds with what is in each, plus the articles you edited most recently;
opening one shows its categories; opening a category shows a filtered,
paginated list of its articles. The left panel is the same hierarchy as a
lazy-loading tree — a shortcut, not the only way in: clicking a *name* opens
that level's page, while the twisty beside it unfolds in place.

Open an article to read it rendered as a page: a title heading, the prose body,
and an **infobox** of the remaining fields on the side.

**Find things.** The sidebar box is a type-ahead over titles, showing which world
and category each match came from. The filter on a category page is a *full-text*
search of that category — it matches words from anywhere in an article, not just
its name. **Search inside articles →** opens a detailed search that can also find
every article carrying a given field.

**Follow links.** Words wrapped in `[[…]]` render as tappable links to other
articles; clicking one opens it. Links to articles that don't exist (or that you
can't read) show as dimmed "red links".

**Create.** The **New** button on each page already knows where you are: on a
category page it asks only for a title, on a world page it makes a category, and
on the home page it makes a world. The one in the header offers dropdowns of what
already exists, pre-filled from wherever you were — you never retype a name that
is sitting in a list beside you. A new article's category is created when the
article is **saved**, so backing out of the editor leaves nothing behind.

**Edit.** **Edit** on an open article (or a **New** that you carried through)
gives you:

- a **Title** field,
- a **body editor** using a wikitext subset — `'''bold'''`, `''italic''`,
  `== Heading ==`, `* list item`, and `[[links]]` — with a formatting toolbar and
  a **Preview** toggle,
- an **Insert link** button (or just type `[[`) that opens a type-ahead over all
  articles you can read; picking one inserts the correct link automatically, and
  if nothing matches you can **create the target on the fly**,
- an **infobox editor** to add/rename/remove fields (a value with commas becomes
  a list of chips), and
- a hidden **Advanced** toggle to edit the raw fields directly.

**History, compare & restore.** The **History** tab lists an article's retained
versions. Each one offers **Compare with current** (a field-by-field diff with
word-level highlighting on prose) and **Restore** (re-applies that version as a
new revision). If someone else saved while you were editing, the editor detects
it on save and shows you the differences so nothing is silently overwritten.

**Delete & restore.** Removing an article hides it from every listing, search
and link, but keeps its version history — it is never destroyed by a delete. Two
ways back: the article's own address still answers, offering **Restore** and
saying who removed it and when; and its category page carries a collapsed
**"N articles deleted"** drawer listing everything removed from it, with a
Restore beside each. A row says *history pruned* when the version cap has
finally aged out every body (nothing is left to bring back), and *not yours to
restore* when you may read it but not write it. A **category** can be deleted from its own page once
no article is left in it — and if it still holds the history of articles deleted
from it, the dialog says so and how much, because discarding that is the one
thing here you cannot undo. Deleting the last category in a world deletes the
world too.

**Rename.** There is no rename, by design: an article's slug and its
world/category names *are* its address, pointed at by every `[[link]]`, every
grant and every chronos reference. To rename, create under the new name, repoint
what referred to it, and delete the old — which is why the new-article dialog
warns that the slug is permanent.

**Theme, text size & mobile.** Toggle light/dark with the ◐ button, and cycle the
text size (Normal → Large → Larger → Largest) with the **A** button — both are
remembered per browser. On a phone the browser tree collapses into a drawer (☰).

**Admin.** Admins get an **Admin** link to `/admin` to manage users (role,
enable/disable, delete) and edit anyone's grants. From there an admin can also:

- **Create accounts directly** without waiting for self-registration. Leave the
  password blank and a strong **temporary password** is generated and shown once
  to hand over; the new user must change it on first login.
- **Switch registration between *open* and *invite-only*.** In invite-only mode
  the registration page is disabled and accounts exist only when an admin creates
  them (existing users can still log in). The very first account can always be
  registered so a fresh deployment can bootstrap its admin.

Note admins are **not** exempt from grants (see above) — to read another user's
content an admin grants themselves access like anyone else.

---

## Data model

Documents are **flat** JSON objects: each value is a scalar
(`str`/`int`/`float`/`bool`/`null`) or a flat array of scalars. Nested objects
and nested arrays are rejected — this keeps the editor and the version diff
simple.

The UI presents a document as an article using two conventional fields:

| Field | Becomes |
| --- | --- |
| `title` | the article heading |
| `body` | the article prose (wikitext) |
| any other field | an infobox fact (arrays render as chips) |

Both are optional — a document created via the API with neither still reads fine
(the id is used as the heading and every field shows in the infobox).

**Link syntax** (inside any string value, usually `body`):

| Token | Points at |
| --- | --- |
| `[[aragorn]]` | article `aragorn` in the *same* collection |
| `[[characters/rand]]` | `rand` in another collection of the *same* database |
| `[[middle-earth/lord-of-the-rings/frodo]]` | fully-qualified |
| `[[aragorn\|the King]]` | same target, custom link text |

---

## Access control

- **Accounts & roles.** Register with a username + password (hashed). Each
  account is `admin` or `user`. The **first account ever registered** becomes the
  admin; there is no built-in/default admin to guess. Registration can be set to
  **invite-only** by an admin, in which case accounts are created only from the
  admin console. Passwords must meet a strength policy (NIST 800-63B: at least 12
  characters, screened against common passwords).
- **Grants (allow-only, most-specific-wins).** A user's access is the union of
  their grants; each grant is scoped at the **database**, **collection**, or
  **article** level and lists permissions (`read`, `write`, `delete`). A narrower
  grant overrides a broader one. Anything not granted is denied. The **admin role
  is not exempt**: admins manage accounts and grants, but read/write content only
  where explicitly granted.
- **Ownership.** Creating a database/collection or an article auto-grants its
  creator full permissions on it.
- **Filtering, not just gating.** Browse, search and suggest results omit
  anything you can't read.

Unauthenticated API calls get `401`; authenticated calls lacking the needed grant
get `403`.

---

## Using it from Python

All examples use a `requests.Session`, which keeps the login cookie across calls.
The service is at `http://localhost:5002`.

### Log in

```python
import requests

BASE = "http://localhost:5002"
s = requests.Session()

# On a fresh deployment, the first registered account becomes the admin.
# Registration requires a valid email; it does not log you in, so log in after.
s.post(f"{BASE}/register",
       json={"username": "huy", "password": "secret", "email": "huy@example.com"})
s.post(f"{BASE}/login", json={"username": "huy", "password": "secret"})

print(s.get(f"{BASE}/auth/me").json())   # {'username': 'huy', 'role': 'admin'}
```

### Create a collection and articles

A database + collection must exist before you can add documents to it. The body
is a flat JSON object; the id comes from the URL.

```python
col = f"{BASE}/databases/middle-earth/collections/lord-of-the-rings"

s.post(col)  # create the database + collection (409 if it already exists)

r = s.post(f"{col}/documents/aragorn", json={
    "title": "Aragorn",
    "body": ("'''Aragorn''' is heir of Isildur and King of Gondor. "
             "He travels with [[frodo]] and the wizard [[gandalf]]."),
    "race": "Man",
    "weapon": "Andúril",
    "titles": ["Strider", "Elessar", "King of Gondor"],   # a flat array
})
print(r.status_code, r.json())
# 201 {'id': 'aragorn', 'document': {...}, 'rev': 1}
```

### Read one article

`GET` returns the current body plus its revision (`rev`), also exposed as an
`ETag` header.

```python
doc = s.get(f"{col}/documents/aragorn").json()
print(doc["id"], doc["rev"], doc["document"]["title"])
# aragorn 1 Aragorn
```

### Update safely (optimistic concurrency)

Send the revision you based your edit on via `If-Match`. If someone else changed
the article in the meantime, your write is rejected with `409` instead of
silently clobbering theirs.

```python
doc = s.get(f"{col}/documents/aragorn").json()
rev = doc["rev"]

r = s.put(f"{col}/documents/aragorn",
          json={**doc["document"], "weapon": "Andúril, Flame of the West"},
          headers={"If-Match": str(rev)})
print(r.status_code, r.json()["rev"])   # 200 2

# Re-using the now-stale rev is refused:
r = s.put(f"{col}/documents/aragorn", json={"title": "x"},
          headers={"If-Match": str(rev)})
print(r.status_code)                     # 409

# Omitting If-Match is allowed (last-write-wins) for quick scripts.
```

### Browse

Each level says how much is inside it and what you may do there, so a browser
can draw a page rather than just a list of names.

```python
print(s.get(f"{BASE}/databases").json())
# {'databases': [{'name': 'middle-earth', 'title': 'Middle Earth',
#                 'collections': 3, 'articles': 61}, ...]}
# `title` is a readable rendering of `name`, never a replacement for it — every
# path, link and grant still uses the slug.

print(s.get(f"{BASE}/databases/middle-earth/collections").json())
# {'database': 'middle-earth',
#  'collections': [{'name': 'lord-of-the-rings', 'articles': 42,
#                   'can_write': True, 'can_delete': True}]}

# One page of articles, ordered by title. `filter` matches every word against
# the whole article — title, slug and field values — so it finds a character by
# a word from their body. Counts and permissions are per-caller.
print(s.get(f"{col}/documents", params={"filter": "isildur", "page": 1, "per_page": 25}).json())
# {'documents': [{'id': 'aragorn', 'title': 'Aragorn', 'rev': 2,
#                 'updated': '2026-08-07T20:49:23+00:00', 'author': 'huy', ...}],
#  'page': 1, 'per_page': 25, 'total': 1, 'pages': 1,
#  'can_write': True, 'can_delete': True}
# An out-of-range page is clamped to the last one rather than erroring.

# The most recently written articles across every readable namespace.
print(s.get(f"{BASE}/recent", params={"limit": 8}).json())
# {'documents': [{'id': 'aragorn', 'database': 'middle-earth', ...}, ...]}
```

### Remove a namespace

Only if you own it, and only once no *live* article is left — this is for tidying
away a collection made by mistake, not a bulk delete. A tombstone is the harder
case: it holds no article, only the version history of one that was deleted, so
it blocks the drop until you say explicitly that the history may go.

```python
s.delete(col)              # 409 while any live article is in it
s.delete(col)              # 409 again if it holds the history of deleted ones
s.delete(col, params={"purge": 1})   # 200 — that history is discarded

# {'database': ..., 'collection': ..., 'purged': 3, 'database_removed': True}
# `database_removed` is true when this was the last collection: MongoDB drops a
# database with the last collection in it, so that is also how a database goes.
# `DELETE /databases/<db>` exists for a shell left behind by an older version;
# on a live MongoDB you will not find one, because it cleans up after itself.
```

### Suggest (link type-ahead)

```python
print(s.get(f"{BASE}/suggest", params={"q": "arag"}).json())
# {'suggestions': [{'slug': 'aragorn', 'title': 'Aragorn',
#                   'database': 'middle-earth', 'collection': 'lord-of-the-rings'}]}
```

### Search

`key` matches an exact top-level key; `text` is a case-insensitive substring over
the content; giving both requires both. At least one is required.

```python
print(s.get(f"{col}/search", params={"key": "weapon"}).json())
print(s.get(f"{col}/search", params={"text": "Gondor"}).json())
# {'results': [{'id': 'aragorn', 'document': {...}, 'rev': 2}], 'count': 1}
```

### Version history, diff & restore

```python
doc = f"{col}/documents/aragorn"

# Metadata for every retained version, newest first
print(s.get(f"{doc}/versions").json())
# {'id': 'aragorn', 'versions': [{'rev': 2, 'op': 'update', 'author': 'huy',
#                                 'timestamp': '...'}, {'rev': 1, ...}]}

# A single version's full body
print(s.get(f"{doc}/versions/1").json())

# A structured diff between two revisions
print(s.get(f"{doc}/diff", params={"from": 1, "to": 2}).json()["diff"])
# {'fields': [{'key': 'weapon', 'status': 'changed', 'inline': [...]}, ...]}

# Restore rev 1 as a brand-new revision (append-only; never a rewind)
print(s.post(f"{doc}/restore/1").json()["rev"])   # 3
```

### Delete

```python
rev = s.get(doc).json()["rev"]
r = s.delete(doc, headers={"If-Match": str(rev)})
print(r.status_code)                 # 204
print(s.get(doc).status_code)        # 404 (history is kept; the id can be recreated)
```

---

## API reference

The published contract is **[`openapi.json`](openapi.json)** — OpenAPI 3, with a
schema and an example for every response. A [contract
test](../../tests/akasha/test_contract.py) holds it to the code: every route the
app registers must be documented, every documented route must exist, and real
responses are validated against the schemas they claim. The table below is the
short version.

Every document call names a database and collection; single-document calls also
name a document id. Bodies must be flat JSON objects. All endpoints require an
authenticated session (except `/health`).

| Method | Path | Purpose |
| --- | --- | --- |
| POST   | `/register` | create an account (`{username, password}`; 409 if taken) |
| POST   | `/login` | start a session (`{username, password}`) |
| POST   | `/logout` | end the session |
| GET    | `/auth/me` | the current user (`{username, role}`) |
| GET    | `/databases` | readable databases, each with `title` (derived from the name), and its collection/article counts |
| GET    | `/databases/<db>/collections` | readable collections, each with `title`, counts and `can_write`/`can_delete`, plus `empty` (whether the database really holds nothing, as opposed to nothing *you* may read) |
| POST   | `/databases/<db>/collections/<col>` | create the database + collection (409 if exists) |
| DELETE | `/databases/<db>/collections/<col>?purge=` | drop a collection you own once no live article is left (409 otherwise); `purge=1` also discards the history of deleted ones. Takes the database with it if it was the last one |
| DELETE | `/databases/<db>` | drop a database with no collections left (409 otherwise) |
| GET    | `/databases/<db>/collections/<col>/documents` | one page of readable articles (`?filter=&page=&per_page=`), plus `deleted` (tombstones the owner would lose) |
| GET    | `/recent?limit=` | most recently written readable articles, newest first |
| GET    | `/databases/<db>/collections/<col>/deleted` | tombstones in a collection: what was deleted, by whom, and the `restore_rev` a restore would re-apply (`null` when history has been pruned to deletions alone) |
| POST   | `/databases/<db>/collections/<col>/documents/<id>` | create an article (404 if namespace missing, 409 if id exists) |
| GET    | `…/documents/<id>` | read (404 if missing); returns `rev` + `ETag` |
| PUT    | `…/documents/<id>` | replace (404 if missing; 409 if `If-Match` rev is stale) |
| DELETE | `…/documents/<id>` | delete (soft; 409 if `If-Match` rev is stale) |
| GET    | `…/documents/<id>/versions` | retained version metadata (newest first) |
| GET    | `…/documents/<id>/versions/<n>` | one version snapshot |
| GET    | `…/documents/<id>/diff?from=&to=` | structured diff of two versions |
| POST   | `…/documents/<id>/restore/<n>` | restore version `n` as a new revision |
| GET    | `/databases/<db>/collections/<col>/search?key=&text=` | search |
| GET    | `/suggest?q=&db=&col=` | link type-ahead over readable articles |
| GET    | `…/collections/<col>/collaborators` | who can access this collection (owner only) |
| PUT    | `…/collections/<col>/collaborators/<user>` | share it as `reader`/`editor`/`owner` |
| DELETE | `…/collections/<col>/collaborators/<user>` | stop sharing it |
| GET    | `…/documents/<id>/collaborators` | the same three, scoped to one article |
| PUT    | `…/documents/<id>/collaborators/<user>` | |
| DELETE | `…/documents/<id>/collaborators/<user>` | |
| GET    | `/account/contacts` | your saved collaborator roster |
| POST   | `/account/email` | change your own email |
| GET    | `/health` | liveness; the only route needing no session |

Writes accept an optional `If-Match: "<rev>"` header (or `?_rev=<rev>`) for
optimistic concurrency; a stale value returns `409`.

---

## Observability

`/admin/observability` (administrators only) answers three questions: how long
the NAS volume lasts, who is filling it, and whether the API is healthy. There
is no extra container and no new dependency — the data lives in a reserved
`_ops` database beside `_auth` and `_chronos`, and expires on its own.

**Storage is charged twice over, and the halves reconcile.** The owner of a
document is charged for its current body; each author is charged for the version
snapshots they wrote. With twenty snapshots retained per article, history is
usually most of the bytes, so charging all of it to the owner would credit the
growth to the wrong person. Owns plus authored always equals what is on disk.

Ownership means holding `delete`. Where several people do, a self-granted
delete wins — that is the auto-grant a creator receives — and remaining ties
break alphabetically so the answer is stable between runs. Failing that the
charge falls to `created_by`, then to the first author, then to
`(unattributed)`.

**Nothing is measured inside a request.** Handlers increment counters in
process memory behind a lock; a background thread writes hourly totals every
`MONITORING_FLUSH_SECONDS` and re-measures storage and host capacity every
`MONITORING_SCAN_SECONDS`. Requests are labelled with Flask route templates,
never real paths, so document ids never reach telemetry. `/health` and static
assets are excluded.

| What | Kept |
| --- | --- |
| Hourly request totals — count, latency histogram, bytes, per route and writer | ~400 days, expired by a TTL index |
| Daily storage attribution per writer | ~400 days, expired by a TTL index |
| Slow (>1s) and failed requests, with route, writer, duration and error | newest 500 rows |
| Host capacity — disk, memory, MongoDB size | latest sample only |

Latency is stored as bucket counts rather than retained samples, so a
percentile resolves to a bucket bound (`≤ 250 ms`) rather than an exact value.
That is what makes the write a single atomic increment MongoDB can merge, so
concurrent workers cannot lose each other's counts.

Pausing from the page stops recording, the storage sweep and the capacity
sample; collected history is kept and ages out normally. The switch is durable
(`_ops.settings`), cached for thirty seconds so it costs no round trip per
request, and fails safe — if it cannot be read, the last known value stands
rather than an error reaching the request.

The page has no client-side code and does not refresh itself. Reload it to
update.

---

## Deploy on a Synology NAS

Install, HTTPS, updating to a new commit, and backups are stack-level concerns —
one compose file brings up both services and their shared MongoDB — so they live
in one place: **[Synology deployment](../synology-deployment.md)**.

---

## Development & tests

Environment setup is shared by both services — see
[**Development & tests** in the repo README](../../README.md#development--tests).
This service's tests live in `tests/akasha/`:

```bash
pytest -q tests/akasha     # in-memory MongoDB (mongomock); no server needed
ruff check src/visualizer/akasha
```
