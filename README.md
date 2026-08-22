# visualizer

A small self-hosted stack for building and keeping track of fictional worlds.
Three Flask + MongoDB services that ship and run together: one holds **what
exists** in your world, one holds **what happens** in it, and one holds **where
it happens**.

They share one MongoDB, one login, and one permission model, and are designed to
run comfortably on a home NAS.

> **Vibe-coded with Claude.** This project was built in conversation with
> Anthropic's Claude (via Claude Code): the design was argued out and decided
> interactively, and the model wrote the implementation, the tests and these
> docs under that direction. It's a personal tool for me and a few fellow
> novelists — not a hardened product. Two things follow. Read
> [`SECURITY.md`](SECURITY.md) before exposing it beyond your own network; and
> where the prose and the code disagree, believe the **test suite** — it runs
> against every service and is the honest account of what actually works.

---

## Services

All three run in **one process behind a single origin** (port `5002`): akasha at
`/`, chronos at `/timeline`, prithvi at `/prithvi` — one login, one
reverse-proxy entry.

| Service | Path | What it does | Docs |
| --- | --- | --- | --- |
| **akasha** | `/` | A Wikipedia-style article store and editor: characters, items, locations, lore — with linking, versioning and diffs. Has a web UI. | [README](docs/akasha/README.md) · [design](docs/akasha/editor-design.md) |
| **chronos** | `/timeline` | A plotline & timeline API for fiction writers: books, events and plotlines, checked for continuity errors, with a plotline visualiser and editor. | [README](docs/chronos/README.md) · [getting started](docs/chronos/getting-started.md) · [plain-language overview](docs/chronos/OVERVIEW.md) · [design](docs/chronos/design.md) |
| **prithvi** | `/prithvi` | An SVG map per region of a world, with Akasha articles pinned to points on it. Has a web UI: upload a map, place and move pins, and read a pin's article beside the map. | [README](docs/prithvi/README.md) · [openapi](docs/prithvi/openapi.json) |
| **mongo** | *internal* | Shared storage. Deliberately not published to the host. | — |

They are named for what they hold: **Akasha** (the aether said to record all
things) is the canon; **Chronos** (time) is the sequence of events through it;
**Prithvi** (earth) is the ground those events happen on.

**How they fit together.** Characters, items and locations are articles in
Akasha. Neither of the others invents one — they *reference* articles, and
refuse a reference to something that doesn't exist. So there is one canon, and
both the timeline and the maps are checked against it.

**One process, one origin.** In production the apps are served by a single
gunicorn behind one origin (port `5002`) — akasha at `/`, chronos at
`/timeline`, prithvi at `/prithvi` — composed with Werkzeug's
`DispatcherMiddleware` (`visualizer.wsgi:application`, see
[`src/visualizer/gateway.py`](src/visualizer/gateway.py)). They already share one
MongoDB, one `_auth` store and one `SECRET_KEY`, and both chronos and prithvi
call akasha in-process (no service-to-service HTTP), so co-mounting them changes
nothing about how they work — it just gives **one reverse-proxy rule, one cookie
and no CORS**, which is exactly what the Synology reverse-proxy deployment wants.
It's a *front door*, not a merge: each app keeps its own factory and test suite,
and the per-service entrypoints (`visualizer.akasha.wsgi` and its siblings) still
run a single service on its own port for development. The header's `AKASHA_URL`,
`CHRONOS_URL` and `PRITHVI_URL` default to the relative paths `/`, `/timeline`
and `/prithvi`; set them if a proxy serves the services on different hosts.

---

## Run it

```bash
# 1. Set the cookie-signing secret (git-ignored, auto-loaded by compose).
#    One value, shared by every service, so a single login covers them all.
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > docker/.env

# 2. Build and start the stack (one app container + mongo)
docker compose -f docker/docker-compose.nas.yml up --build -d
```

- **http://localhost:5002/** — the article editor. **Register the first account;
  it becomes the administrator.**
- **http://localhost:5002/timeline** — the plotline visualiser: browse your
  threads, see where they contradict each other, and reorder them.
- **http://localhost:5002/prithvi/** — the map browser: upload an SVG for a
  world you can write, pin articles to it, and click a pin to read its
  article beside the map. The API is under `…/prithvi/worlds/{world}/maps`,
  and a map with its pins drawn on is at `…/maps/{map}/render.svg`.
- **http://localhost:5002/health** — akasha liveness; **/timeline/health** and
  **/prithvi/health** — the other two.
- **http://localhost:5002/admin/observability** — administrators only: NAS
  capacity, per-writer usage and API health. See **Observability** below.

Each service's README documents its own configuration and API. For a NAS
install — including HTTPS, updating to a new commit, and backups — see
[Deploy on a Synology NAS](docs/synology-deployment.md).

### Observability

Because the stack runs on a NAS, the admin console answers one question up
front: **how long until the volume fills, and who is filling it.** No extra
containers and no new dependencies — the data lives in a reserved `_ops`
database beside `_auth` and `_chronos`.

- **Capacity** — free disk, memory and MongoDB's own footprint, plus a
  projected fill date from the observed growth rate. A banner appears in the
  admin console when a threshold is crossed.
- **Per-writer usage** — storage is charged to the owner for the current
  document and to each author for the version snapshots they wrote, so the two
  columns add up to exactly what is on disk. Shown alongside request counts,
  p95 latency and server errors.
- **API health** — hourly p50–p95 latency and errors per hour, per route, with
  a table view of every plotted value and a log of recent slow or failed
  requests.

Nothing is measured inside a request: handlers only increment counters in
memory, and a background thread writes hourly totals every few minutes.
Requests are labelled with Flask *route templates*, never real paths, so
document ids never reach telemetry.

Pause it from the page itself — that stops recording, the storage sweep and the
capacity sample; history already collected is kept and expires on its own.
`MONITORING_ENABLED=false` in `docker/.env` disables it at boot instead.

> Before exposing any of this beyond localhost, read [`SECURITY.md`](SECURITY.md)
> — it lists what protections exist and what hardening is still required.

### Try it with sample data

`docker/seed_demo.py` builds a small story ("The Ember Pact") across both
services over their real HTTP APIs — a cast of characters, six scenes, and four
plotlines. **Three of the threads are sound; the fourth is broken on purpose**,
so you can see the continuity checks actually fire:

```bash
python docker/seed_demo.py        # stack must already be up
```

It prints chronos's verdict, and the book is left **conflicted** with all three
checks reporting:

```
  book status: CONFLICTED

  temporal conflicts (1):
    - 'aldric-at-emberport' and 'aldric-departs' place a character in two places at once.
      aldric: emberport [10, 30] vs highkeep [0, 24]

  ordering problems (1):
    - [witness-tale] 'meet-at-emberport' does not end before 'aldric-at-emberport' begins.

  threads reaching the terminus 'the-coronation': NO
    - [witness-tale] does not end at terminus (stops at 'aldric-at-emberport')
```

Inspect it yourself, then watch it go green:

```bash
curl -s -c /tmp/c -X POST localhost:5002/login -H 'Content-Type: application/json' \
  -d '{"username":"mara","password":"ember-pact-demo"}'

curl -s -b /tmp/c localhost:5002/timeline/books/ember-pact/validate   # the full report
curl -s -b /tmp/c localhost:5002/timeline/books/ember-pact/graph      # how the threads connect

python docker/seed_demo.py --fix                             # repair; status -> CONSISTENT
```

Note that **none of those problems blocked a write** — chronos records what you
tell it and reports what doesn't add up. Re-running the script is safe, and
without `--fix` it breaks the story again.

---

## Repository layout

```
src/visualizer/
  akasha/   articles, auth, grants, versioning, web UI
  chronos/           books, plotlines, events, story graph
  prithvi/           SVG maps, pins onto articles, sanitization
  documents.py       the revision mechanics chronos and prithvi share
  static/js/         the few ES modules the *browser* services load
tests/               one suite per service (in-memory MongoDB)
docker/              Dockerfiles, the compose stack, demo seed + backup scripts
docs/                per-service READMEs, design documents, NAS deployment
```

**The shared frontend module.** Each service is its own Flask app with its own
`static/` folder, and there is no bundler, so anything both browsers need used to
be copied — and the copies drifted (an article and the scene referencing it
stopped deriving the same id from the same title). `visualizer/static/js` holds
one copy, and [`shared_assets.py`](src/visualizer/shared_assets.py) has each app
serve it *beneath its own static path*, so one relative specifier —
`./shared/slug.js` — resolves from either tree and at any mount: akasha at `/`,
chronos at `/timeline`, or either standalone on its own port. Keep the directory
small and dependency-free; a module there cannot import from either service.

Every service follows the same conventions: **inversion of control** (every
database or network boundary is a seam injected into an app factory) and **pure,
DB-free logic modules** for the interesting rules, so the bulk of the test suite
needs no server and no mocks.

---

## Development & tests

Work on **Python 3.11** — the version the containers run — and install the
project editable with its dev tools:

```bash
# create + activate a 3.11 environment — either works:
python3.11 -m venv .venv && source .venv/bin/activate
# or:  conda create -y -n visualizer python=3.11 && conda activate visualizer

pip install -e ".[dev]"     # the package + pytest, ruff, mongomock, jsonschema
```

> **This repo already has one:** the conda env named **`visualizer`**
> (Python 3.11) — `conda activate visualizer`. Use it rather than a base/system
> interpreter: those may be on 3.10 and can be missing project dependencies
> (e.g. `networkx`), so tests can pass or fail for the wrong reasons.

Then, from the repo root:

```bash
pytest        # every suite, entirely against an in-memory MongoDB — no server needed
ruff check    # lint
```

The editable install puts `visualizer` on the path, so no `PYTHONPATH` is needed.

---

## Licence

**[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)**,
with one additional permission. See [`LICENSE`](LICENSE) for the full text.

The short version: use it, change it, run it on your own machine or your NAS,
share it with the people you write with. Don't sell it, and don't run it as a
paid service.

**What you write with it is not covered at all.** Your worlds, articles,
timelines, maps and manuscripts are yours, including the ones you sell — the
noncommercial terms are about the software, not about your novel. That
permission is spelled out at the top of `LICENSE` because a writing tool whose
licence left a professional novelist guessing would be a bad writing tool.

This is *source-available*, not open source: it does not meet the OSI
definition, and it is not MIT or Apache. Everything it depends on is
permissively licensed (Flask, PyMongo, NetworkX, and friends), so nothing here
is anyone else's copyleft to honour.
