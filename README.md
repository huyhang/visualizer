# visualizer

## document-server

A small Flask + MongoDB service for storing and searching JSON documents,
secured with user accounts and fine-grained access control, plus a
server-rendered browser GUI for registration and administration.

### Design

Code is a proper Python package at `src/visualizer/document_server/`; modules
import each other with relative imports (`from .store import DocumentStore`).
With `src` on the path, the WSGI entrypoint is
`visualizer.document_server.wsgi:app`.

- `store.py` — `DocumentStore`, the only seam to MongoDB for documents. It
  receives its Mongo client via the constructor (inversion of control), so tests
  inject an in-memory client and production injects a real one.
- `auth_store.py` — `AuthStore`, the same-pattern seam for user accounts and
  access-control grants. Lives in a reserved `_auth` database that the document
  API can never address.
- `authz.py` — pure, DB-free access-control resolution (grant matching,
  most-specific-wins, permission ↔ HTTP-method mapping).
- `auth.py` — Flask-Login wiring, session routes (`/login`, `/register`,
  `/logout`), the `admin_required` guard, and the admin bootstrap.
- `app.py` — `create_app(store, auth_store)` factory; document routes (each
  authenticated and authorized), admin routes, and the GUI pages.
- `validation.py` — pure, DB-free document validation helpers.
- `templates/` — Jinja templates for the browser GUI (`login`, `register`,
  `index`, `admin`).
- `config.py` / `wsgi.py` — production wiring only.

Tests live in `tests/document_server/` and run against an in-memory MongoDB
(`mongomock`).

### Authentication & access control

Every document endpoint requires an authenticated session; requests without one
get `401` (API) or a redirect to the login page (browser).

- **Accounts & roles.** Users register with a username + password (hashed with
  `werkzeug.security`). Each account is either `admin` or `user` and is
  `active`/disabled. The **first account ever registered** (via `/register`)
  becomes the admin; every account after it is a plain user. There is no
  default/bootstrap admin, so no built-in credentials exist to guess.
- **Grants (fine-grained, allow-only).** A user's access is the union of their
  grants. Each grant is scoped at the database, collection, **or** individual
  article level and lists permissions (`read`, `write`, `delete`):

  | Grant scope | Example | Effect |
  | --- | --- | --- |
  | Database | `middle-earth` / — / — | everything under that database |
  | Collection | `middle-earth` / `lotr` / — | every article in that collection |
  | Article | `middle-earth` / `lotr` / `aragorn` | that one article |

  Resolution is **most-specific-wins**: an article-level grant overrides a
  broader collection/database grant on that article (so you can grant full
  access to one collection but only specific articles in another). There are no
  deny rules — anything not granted is denied. Admins bypass all grant checks.
- **Ownership.** Creating a database/collection or an article auto-grants the
  creator full permissions on it.
- **Search is filtered**, not just gated: results you cannot `read` are removed
  from the response.
- **Admin GUI.** Admins manage users (role, enable/disable, delete) and edit any
  user's grants at `/admin`. The last remaining admin cannot be demoted,
  disabled, or deleted.

### TODO — production hardening

Not yet implemented; required before exposing the service beyond localhost:

- [ ] **Rate limiting on `/login`** (and ideally `/register`) to blunt password
  brute-forcing and account-enumeration attempts. Consider `Flask-Limiter` with a
  per-IP + per-username limit and a shared backend (e.g. Redis) so limits hold
  across gunicorn workers.
- [ ] **SSL/HTTPS.** Session cookies are currently served over plain HTTP; without
  TLS they can be intercepted. Terminate TLS (a reverse proxy such as nginx/Caddy,
  or a managed load balancer) and then set `SESSION_COOKIE_SECURE=True` and
  `SESSION_COOKIE_HTTPONLY=True` (httponly is already Flask's default) so cookies
  are only sent over HTTPS. Redirect HTTP → HTTPS.

### Run

The `document-server` and `mongo` services live in the shared compose file at
`docker/docker-compose.yml` (alongside the janusgraph stack). The
`document-server` reuses the existing miniconda image (`docker/Dockerfile`) —
its `janusgraph_env` conda environment (see `docker/environment.yaml`) provides
flask, pymongo and gunicorn — and only overrides the run command to launch
gunicorn. To bring up just the document server:

```bash
docker compose -f docker/docker-compose.yml up --build -d document-server mongo
# app on http://localhost:5002, mongo internal-only
```

Omit the service names to bring up everything (graph + document server).

MongoDB has **no published port** — it is reachable only from inside the docker
network (by the `document-server` container), never from the host.

**Configuration** (environment variables on the `document-server` service):

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | signs session cookies — **required**; compose refuses to start without it. Sourced from `docker/.env` (git-ignored), which compose auto-loads. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. | none (must be set) |
| `SESSION_COOKIE_SECURE` | mark the session cookie HTTPS-only — enable when served over HTTPS (e.g. behind a reverse proxy) | `false` |
| `MONGO_URI` | MongoDB connection string | `mongodb://mongo:27017` |

Open **http://localhost:5002/** in a browser and **register the first account —
it becomes the admin**. Everyone else self-registers at **/register** as a plain
user, and the admin grants them access at **/admin**.

### Deploy on a Synology NAS

For constrained hosts there's a standalone, lightweight stack —
`docker/docker-compose.nas.yml` (just `document-server` + `mongo`, built from the
slim `docker/Dockerfile.docserver` instead of the miniconda image, with
`restart: unless-stopped`).

1. **Requirements.** A model with **Container Manager** (any "+" model, e.g. the
   DS1621+). MongoDB 7 needs a CPU with **AVX** (the DS1621+'s Ryzen V1500B has
   it); on a CPU without AVX, change `mongo:7` to `mongo:4.4` in the compose file.
2. **Get the repo onto the NAS** (Git or a shared folder) — the image builds from
   the repo root.
3. **Set the secret** in `docker/.env` (git-ignored, auto-loaded):
   `SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")`.
   If you'll serve over HTTPS, also add `SESSION_COOKIE_SECURE=true`.
4. **Deploy** — in Container Manager create a *Project* pointing at
   `docker/docker-compose.nas.yml`, or on the CLI:
   ```bash
   docker compose -f docker/docker-compose.nas.yml up --build -d
   ```
   The app is published on host port **5002** (DSM uses 5000/5001 — don't reuse
   those).

#### Enabling HTTPS (strongly recommended)

The app speaks plain HTTP on port 5002; session cookies must not travel
unencrypted. Terminate TLS with Synology's built-in reverse proxy — no code or
extra containers needed.

1. **Have a hostname.** You need a domain that resolves to the NAS. The easiest
   is a free Synology DDNS name: **Control Panel → External Access → DDNS → Add**
   (e.g. `myvault.synology.me`). A custom domain works too.
2. **Get a certificate.** **Control Panel → Security → Certificate → Add → Add a
   new certificate → Get a certificate from Let's Encrypt.** Enter your hostname
   and email. (Let's Encrypt validation needs ports 80/443 reachable from the
   internet; if you only use this on your LAN, you can instead use a self-signed
   cert or your own CA — the browser will warn but TLS still works.)
3. **Create the reverse-proxy rule.** **Control Panel → Login Portal → Advanced →
   Reverse Proxy → Create:**
   - **Source** — Protocol `HTTPS`, Hostname `myvault.synology.me`, Port `443`.
   - **Destination** — Protocol `HTTP`, Hostname `localhost`, Port `5002`.
   - Under **Custom Header**, click **Create → WebSocket** (harmless, and future-proofs it).
4. **Bind the certificate** to that hostname: **Control Panel → Security →
   Certificate → Settings**, and set your Let's Encrypt cert for the reverse-proxy
   hostname.
5. **Turn on secure cookies.** Add `SESSION_COOKIE_SECURE=true` to `docker/.env`
   and redeploy so the session cookie is only ever sent over HTTPS:
   ```bash
   docker compose -f docker/docker-compose.nas.yml up -d
   ```
6. **Use the HTTPS URL only.** Reach the app at `https://myvault.synology.me`
   (port 443), not the raw `http://<nas-ip>:5002`. Optionally firewall off port
   5002 from outside the NAS (**Control Panel → Security → Firewall**) so the app
   is *only* reachable through the TLS proxy.

> With `SESSION_COOKIE_SECURE=true`, logging in over plain HTTP will appear to
> "not work" (the browser drops the Secure cookie) — that's expected; use the
> `https://` address.

### API

Every call names a database and collection; single-document calls also name a
document id. A document body must be a JSON object. **All document endpoints
require an authenticated session** (see the auth endpoints below); unauthenticated
API calls return `401`, and calls lacking the needed grant return `403`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST   | `/register` | create an account (`{username, password}`; 409 if taken) |
| POST   | `/login` | start a session (`{username, password}`; sets the session cookie) |
| POST   | `/logout` | end the session |
| GET    | `/auth/me` | the current user (`{username, role}`) |
| POST   | `/databases/<db>/collections/<col>` | create the database + collection (409 if exists) |
| POST   | `/databases/<db>/collections/<col>/documents/<id>` | create document (404 if db/collection missing, 409 if id exists) |
| GET    | `/databases/<db>/collections/<col>/documents/<id>` | get (404 if missing) |
| PUT    | `/databases/<db>/collections/<col>/documents/<id>` | replace (404 if missing) |
| DELETE | `/databases/<db>/collections/<col>/documents/<id>` | delete (404 if missing) |
| GET    | `/databases/<db>/collections/<col>/search?key=&text=` | search |

**Collections are explicit.** A database and collection must be created (via the
first `POST` above) before documents can be added to them — creating a document
in a database or collection that does not exist returns `404`. Creating the
collection also creates its database.

Search: `key` returns documents that contain that exact **top-level** key;
`text` returns documents whose content contains the text (case-insensitive
substring); giving both returns only documents that satisfy both. At least one
of `key`/`text` is required.

### Examples — querying the Lord of the Rings data

These use the database `middle-earth` and the collection `lord-of-the-rings`.
The app is published on the host at `http://localhost:5002`. For brevity, set:

```bash
BASE="http://localhost:5002/databases/middle-earth/collections/lord-of-the-rings"
```

**Authenticate first.** Every call below needs a session. On a fresh deployment,
register the first account (it becomes the admin), then log in, keeping the
session cookie in a jar that later `curl` calls reuse via `-b`/`-c`:

```bash
curl -X POST http://localhost:5002/register \
  -H 'Content-Type: application/json' -d '{"username":"huy","password":"<your-password>"}'
curl -c cookies.txt -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"username":"huy","password":"<your-password>"}'
```

For brevity the remaining examples omit authentication — prepend `-b cookies.txt`
to each `curl` (or, in the shell, define
`curl() { command curl -b cookies.txt "$@"; }` for the session).

**Create the database and collection first** (required before adding documents;
the creator gets full access to it):

```bash
curl -X POST "$BASE"
# {"collection":"lord-of-the-rings","database":"middle-earth"}
# a second call returns 409 (already exists)
```

**Create the four characters** (each document is a JSON object; the id comes
from the URL). Posting to a database/collection that doesn't exist yet returns
`404`:

```bash
curl -X POST "$BASE/documents/aragorn" -H 'Content-Type: application/json' \
  -d '{"name":"Aragorn","race":"Man","title":"King of Gondor","weapon":"Anduril"}'
curl -X POST "$BASE/documents/frodo" -H 'Content-Type: application/json' \
  -d '{"name":"Frodo Baggins","race":"Hobbit","role":"Ring-bearer","home":"the Shire"}'
curl -X POST "$BASE/documents/legolas" -H 'Content-Type: application/json' \
  -d '{"name":"Legolas","race":"Elf","weapon":"bow","realm":"Mirkwood"}'
curl -X POST "$BASE/documents/gimli" -H 'Content-Type: application/json' \
  -d '{"name":"Gimli","race":"Dwarf","axe":"battle axe","father":"Gloin"}'
```

**Get one document by id:**

```bash
curl -s "$BASE/documents/frodo"
# {"document":{"home":"the Shire","name":"Frodo Baggins","race":"Hobbit","role":"Ring-bearer"},"id":"frodo"}
```

**Search by key** — key matching is exact and top-level only. Aragorn and
Legolas have a `weapon` key; Gimli's is spelled `axe`, so he is excluded:

```bash
curl -s "$BASE/search?key=weapon"
# {"count":2,"results":[{"document":{...,"name":"Aragorn","weapon":"Anduril"},"id":"aragorn"},
#                       {"document":{...,"name":"Legolas","weapon":"bow"},"id":"legolas"}]}
```

**Search by text** — documents whose content contains "Shire" (case-insensitive):

```bash
curl -s "$BASE/search?text=Shire"
# {"count":1,"results":[{"document":{"home":"the Shire","name":"Frodo Baggins",...},"id":"frodo"}]}
```

**Search by key AND text** — has a `weapon` key *and* mentions "bow":

```bash
curl -s "$BASE/search?key=weapon&text=bow"
# {"count":1,"results":[{"document":{"name":"Legolas",...,"weapon":"bow"},"id":"legolas"}]}
```

If your text has spaces or special characters, let curl encode it:

```bash
curl -s -G "$BASE/search" --data-urlencode "text=the Shire"
```

**Update (full replace)** — Aragorn takes his throne name (replace semantics:
fields not present are dropped):

```bash
curl -X PUT "$BASE/documents/aragorn" -H 'Content-Type: application/json' \
  -d '{"name":"Aragorn","alias":"Elessar","race":"Man"}'
```

**Delete:**

```bash
curl -X DELETE "$BASE/documents/gimli"   # 204 No Content; a later GET returns 404
```

**Read the data straight from MongoDB** (it has no host port, so query it from
inside the container). Note the bracket notation because the collection name is
hyphenated:

```bash
docker compose -f docker/docker-compose.yml exec -T mongo \
  mongosh --quiet middle-earth \
  --eval 'db["lord-of-the-rings"].find().toArray()'
```

The same queries in Python with `requests`:

```python
import requests

base = "http://localhost:5002/databases/middle-earth/collections/lord-of-the-rings"

# A Session keeps the auth cookie across calls. On a fresh deployment the first
# registered account becomes the admin.
s = requests.Session()
s.post("http://localhost:5002/register", json={"username": "huy", "password": "secret"})
s.post("http://localhost:5002/login", json={"username": "huy", "password": "secret"})

s.post(base)  # create the database + collection (idempotent-ish: 409 if it already exists)
s.post(f"{base}/documents/frodo",
       json={"name": "Frodo Baggins", "race": "Hobbit", "home": "the Shire"})

print(s.get(f"{base}/documents/frodo").json())
print(s.get(f"{base}/search", params={"key": "weapon"}).json())
print(s.get(f"{base}/search", params={"text": "Shire"}).json())
```

### Tests

Database tests use an in-memory MongoDB (`mongomock`); no server is contacted.

```bash
pip install -e ".[dev]"
pytest
```

# Example in python
```python
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal

# referencing the service directly by its name (janusgraph, as defined in the docker compose file)
connection = DriverRemoteConnection('ws://janusgraph:8182/gremlin', 'g')
g = traversal().withRemote(connection)
g.V().count().next()
```

```bash
docker compose up --build
```