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
you have been granted (admins see everything).

**Browse & read.** The left panel is a lazy-loading tree of *databases →
collections → articles*. Open an article to read it rendered as a page: a title
heading, the prose body, and an **infobox** of the remaining fields on the side.
The search box at the top finds articles by title across everything you can read.

**Follow links.** Words wrapped in `[[…]]` render as tappable links to other
articles; clicking one opens it. Links to articles that don't exist (or that you
can't read) show as dimmed "red links".

**Create & edit.** Hit **New** (or **Edit** on an open article) to get:

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

**Delete.** Removing an article hides it but keeps its version history; you can
recreate the same id later.

**Theme, text size & mobile.** Toggle light/dark with the ◐ button, and cycle the
text size (Normal → Large → Larger → Largest) with the **A** button — both are
remembered per browser. On a phone the browser tree collapses into a drawer (☰).

**Admin.** Admins get an **Admin** link to `/admin` to manage users (role,
enable/disable, delete) and edit anyone's grants.

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
  admin; there is no built-in/default admin to guess.
- **Grants (allow-only, most-specific-wins).** A user's access is the union of
  their grants; each grant is scoped at the **database**, **collection**, or
  **article** level and lists permissions (`read`, `write`, `delete`). A narrower
  grant overrides a broader one. Anything not granted is denied. Admins bypass
  all grant checks.
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

```python
print(s.get(f"{BASE}/databases").json())
# {'databases': ['middle-earth', ...]}

print(s.get(f"{BASE}/databases/middle-earth/collections").json())
# {'database': 'middle-earth', 'collections': ['lord-of-the-rings']}

print(s.get(f"{col}/documents").json())
# {'documents': [{'id': 'aragorn', 'title': 'Aragorn', 'rev': 2, ...}, ...]}
# supports ?limit= and ?after=<id> for paging
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

Every document call names a database and collection; single-document calls also
name a document id. Bodies must be flat JSON objects. All endpoints require an
authenticated session.

| Method | Path | Purpose |
| --- | --- | --- |
| POST   | `/register` | create an account (`{username, password}`; 409 if taken) |
| POST   | `/login` | start a session (`{username, password}`) |
| POST   | `/logout` | end the session |
| GET    | `/auth/me` | the current user (`{username, role}`) |
| GET    | `/databases` | list readable databases |
| GET    | `/databases/<db>/collections` | list readable collections |
| POST   | `/databases/<db>/collections/<col>` | create the database + collection (409 if exists) |
| GET    | `/databases/<db>/collections/<col>/documents` | list readable articles (`?limit=&after=`) |
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

Writes accept an optional `If-Match: "<rev>"` header (or `?_rev=<rev>`) for
optimistic concurrency; a stale value returns `409`.

---

## Deploy on a Synology NAS

> Before exposing this beyond localhost, read [`SECURITY.md`](../../SECURITY.md) —
> it lists the security measures in place and the hardening still required
> (TLS, MongoDB auth, rate limiting, non-root container, and more).

The same `docker/docker-compose.nas.yml` runs on a Synology NAS with **Container
Manager** (any "+" model). MongoDB 7 needs a CPU with AVX; on one without, change
`mongo:7` to `mongo:4.4` in the compose file.

1. Put the repo on the NAS and set `SECRET_KEY` in `docker/.env` (as above).
2. In Container Manager create a **Project** pointing at
   `docker/docker-compose.nas.yml` (or run the `docker compose … up --build -d`
   command). The app is published on host port **5002** (DSM uses 5000/5001).

**HTTPS (recommended).** Terminate TLS with Synology's built-in reverse proxy —
**Control Panel → Login Portal → Advanced → Reverse Proxy** — pointing an HTTPS
hostname at `http://localhost:5002`, bind a Let's Encrypt certificate to it, then
add `SESSION_COOKIE_SECURE=true` to `docker/.env` and redeploy so the session
cookie is only ever sent over HTTPS. (With that set, logging in over plain HTTP
won't work — use the `https://` address.)

---

## Development & tests

Environment setup is shared by both services — see
[**Development & tests** in the repo README](../../README.md#development--tests).
This service's tests live in `tests/akasha/`:

```bash
pytest -q tests/akasha     # in-memory MongoDB (mongomock); no server needed
ruff check src/visualizer/akasha
```
