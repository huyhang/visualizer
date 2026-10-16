# visualizer

A small self-hosted stack for building and keeping track of fictional worlds.
Four Flask + MongoDB services that ship and run together: they hold **what
exists** in your world, **what happens** in it, **where it happens**, and the
prose that turns all of that into a novel.

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

All four run in **one process behind a single origin** (port `5002`): akasha at
`/`, chronos at `/timeline`, prithvi at `/prithvi`, logos at `/logos` — one
login, one reverse-proxy entry.

| Service | Path | What it does | Docs |
| --- | --- | --- | --- |
| **akasha** | `/` | A Wikipedia-style article store and editor: characters, items, locations, lore — with linking, images, versioning and diffs. Has a web UI. | [README](docs/akasha/README.md) · [editor design](docs/akasha/editor-design.md) · [image design](docs/akasha/media-design.md) |
| **chronos** | `/timeline` | A plotline & timeline API for fiction writers: books, events and plotlines, checked for continuity errors, with a plotline visualiser and editor. | [README](docs/chronos/README.md) · [getting started](docs/chronos/getting-started.md) · [plain-language overview](docs/chronos/OVERVIEW.md) · [design](docs/chronos/design.md) |
| **prithvi** | `/prithvi` | An SVG map per region of a world, with Akasha articles pinned to points on it. Has a web UI: upload a map, place and move pins, and read a pin's article beside the map. | [README](docs/prithvi/README.md) · [openapi](docs/prithvi/openapi.json) |
| **logos** | `/logos` | A versioned manuscript editor and book-like reader with named drafts, Akasha lookup, private writing feedback, recovery, search, and PDF/EPUB publishing. | [README](docs/logos/README.md) · [permissions](docs/logos/permissions.md) · [openapi](docs/logos/openapi.json) |
| **mongo** | *internal* | Shared storage. Deliberately not published to the host. | — |

They are named for what they hold: **Akasha** (the aether said to record all
things) is the canon; **Chronos** (time) is the sequence of events through it;
**Prithvi** (earth) is the ground those events happen on; **Logos** (the word) is
what you finally write.

**How they fit together.** Characters, items and locations are articles in
Akasha. None of the others invents one — they *reference* articles, and the
timeline and the maps refuse a reference to something that doesn't exist. So
there is one canon, checked against. Logos turns a Chronos book into ordered
manuscript volumes and links its prose back to the scenes it realises; a mention
of a vanished article is reported rather than refused, so drafting is never
blocked by canon you haven't written yet.

**One process, one origin.** In production the apps are served by a single
gunicorn behind one origin (port `5002`) — akasha at `/`, chronos at
`/timeline`, prithvi at `/prithvi`, logos at `/logos` — composed with Werkzeug's
`DispatcherMiddleware` (`visualizer.wsgi:application`, see
[`src/visualizer/gateway.py`](src/visualizer/gateway.py)). They already share one
MongoDB, one `_auth` store and one `SECRET_KEY`, and every cross-service question
is asked in-process (no service-to-service HTTP): chronos and prithvi read
akasha, logos reads both, and chronos asks logos whether prose depends on what it
is about to delete. Co-mounting them changes nothing about how they work — it
just gives **one reverse-proxy rule, one cookie and no CORS**, which is exactly
what the Synology reverse-proxy deployment wants.
It's a *front door*, not a merge: each app keeps its own factory and test suite,
and the per-service entrypoints (`visualizer.akasha.wsgi` and its siblings) still
run a single service on its own port for development. The service nav's
`AKASHA_URL`, `CHRONOS_URL`, `PRITHVI_URL`, `LOGOS_URL` and `TUTORIALS_URL`
default to the relative paths `/`, `/timeline`, `/prithvi`, `/logos` and
`/tutorials`; set them if a proxy serves the services on different hosts. The
apps take them as one `ServiceLinks` value (`src/visualizer/service_links.py`).

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
- **http://localhost:5002/logos/** — the manuscript workspace: write with local
  recovery and a private writing coach, keep alternate chapter drafts, compare
  them, organise volumes and sections, and look up or link selected Akasha
  entities without leaving the page.
  The existing focused/full reader, search, private notes, progress sync and
  whole-series PDF/EPUB publication remain available.
- **http://localhost:5002/health** — akasha liveness; **/timeline/health**,
  **/prithvi/health** and **/logos/health** — the others.
- **http://localhost:5002/admin/observability** — administrators only: NAS
  capacity, per-writer usage and API health. See **Observability** below.

Each service's README documents its own configuration and API. For a NAS
install — including HTTPS, updating to a new commit, and backups — see
[Deploy on a Synology NAS](docs/synology-deployment.md). To try it on a Mac
with Docker Desktop and no GPU box, step by step, see
[Run it on a Mac](docs/simple-docker-local-deployment-guide.md).

### Observability

Because the stack runs on a NAS, the admin console answers one question up
front: **how long until the volume fills, and who is filling it.** No extra
containers and no new dependencies — the data lives in a reserved `_ops`
database beside `_auth`, `_chronos` and `_logos`.

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
plotlines, dated in two calendars at once: the fictional Imperial Reckoning and
Earth's, where the Harbor Exchange falls on February 29, 2024. Switch between
them and no scene moves. **Three of the threads are sound; the fourth is broken
on purpose**, so you can see the continuity checks actually fire:

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
  logos/             manuscript volumes, sections, rich text, history
  documents.py       the revision mechanics the story services share
  stack.py           all four apps wired over one MongoDB (wsgi.py serves it)
  devserver.py       that stack without Docker or MongoDB, for local testing
  gpubox/            the client for the AI worker on the GPU box (and a fake one)
  gpu_worker/        that worker itself -- deployed to the box, never the NAS
  static/js/         the few ES modules the *browser* services load
frontend/            compiled surfaces (React + TypeScript + Vite): Akasha's research studio, Logos's writing page, Chronos's workspace
tests/               one suite per service (in-memory MongoDB)
docker/              Dockerfiles, the compose stack, demo seed + backup scripts
docs/                per-service READMEs, design documents, NAS deployment
```

**The shared frontend module.** Each service is its own Flask app with its own
`static/` folder, and the hand-written pages use no bundler, so anything both browsers need used to
be copied — and the copies drifted (an article and the scene referencing it
stopped deriving the same id from the same title). `visualizer/static/js` holds
one copy, and [`shared_assets.py`](src/visualizer/shared_assets.py) has each app
serve it *beneath its own static path*, so one relative specifier —
`./shared/slug.js` — resolves from either tree and at any mount: akasha at `/`,
chronos at `/timeline`, or either standalone on its own port. Keep the directory
small and dependency-free; a module there cannot import from either service.

**Compiled surfaces (`frontend/`).** Akasha's research studio is the first page
built with a toolchain: React, TypeScript and Vite, with Radix for accessible
popovers and dialogs and TanStack Query for polling. Vite compiles it into
`src/visualizer/akasha/static/studio/` (git-ignored), and Flask serves the
result like any other static file. Logos's writing page followed, in
`frontend/src/logos/`, on [Tiptap](https://tiptap.dev) for the editor; it
compiles into `src/visualizer/logos/static/writer/` the same way, with its own
Vite config because each app serves only its own static folder. Chronos's
workspace (`/timeline/?ui=next`, beside the classic visualiser, which stays the
default) is the third, in `frontend/src/chronos/`, compiled into
`src/visualizer/chronos/static/workspace/`. All three share the design-system
components in `frontend/src/components/ui/`. The Docker images compile them in
a Node build stage, so the NAS image still has no Node at run time and no page
loads anything from a CDN. The same conventions hold there: each API is one
injected interface (`ResearchApi`, `LogosApi`, `ChronosApi`), the rules are
pure modules (`frontend/src/logic/`, `frontend/src/logos/logic/`,
`frontend/src/chronos/logic/`), and components get what they need as props or,
for the page's own dependencies, from the one injected context that carries
them (`WriterDeps`, `ChronosDeps`). Other surfaces can move here one at a time.

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

The frontend has its own tools, run from `frontend/` with Node 20.19+ or
22.12+:

```bash
npm ci                # once
npm run build         # compile all three pages into their apps' static folders (each page says if you haven't)
npm run watch         # ...and keep compiling the studio while you edit; reload to see changes
npm run watch:logos   # ...or the writing page
npm run watch:chronos # ...or the Chronos workspace
npm run check         # typecheck, lint, formatting, and the vitest suite
npm run format        # prettier, the frontend's equivalent of ruff
```

`docker/smoke_research_studio_ui.py` drives the whole studio in a real browser
(Playwright) against a running stack, and `docker/smoke_logos_editor_ui.py`
does the same for the writing page's Editor; with no GPU box, run them against
`python -m visualizer.devserver --fake-gpubox --seed --port 5099` and
`BASE=http://127.0.0.1:5099`. `docker/smoke_logos_writer.py` needs no server.

### Run the stack without Docker

```bash
python -m visualizer.devserver           # http://127.0.0.1:5050 — log in as mara / ember-pact-demo
python -m visualizer.devserver --seed    # ...and load the demo story into all four services
python -m visualizer.devserver --fresh   # discard the saved data and start empty
python -m visualizer.devserver --fake-gpubox busy   # research and LLM review against a fake GPU box
```

The same wiring gunicorn serves (`visualizer.stack`), over an in-memory MongoDB
(`mongomock`), with auto-reload and the interactive debugger. Its data is saved
to `instance/devserver.json` whenever it stops or reloads, and restored on the
next start. It uses port 5050 and its own session cookie, so it runs beside the
Docker stack on 5002. `--mongo-uri` points it at a real MongoDB instead. Two
limits: it is mongomock, so anything the tests don't cover may behave
differently, and PDF export needs WeasyPrint's native libraries (Pango) on your
machine.

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
