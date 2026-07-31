# visualizer

A small self-hosted stack for building and keeping track of fictional worlds.
Two Flask + MongoDB services that ship and run together: one holds **what exists**
in your world, the other holds **what happens** in it.

Both share one MongoDB, one login, and one permission model, and both are
designed to run comfortably on a home NAS.

---

## Services

| Service | Port | What it does | Docs |
| --- | --- | --- | --- |
| **akasha** | 5002 | A Wikipedia-style article store and editor: characters, items, locations, lore — with linking, versioning and diffs. Has a web UI. | [README](docs/akasha/README.md) · [design](docs/akasha/editor-design.md) |
| **chronos** | 5003 | A plotline & timeline API for fiction writers: books, events and plotlines, checked for continuity errors. API only, no UI yet. | [README](docs/chronos/README.md) · [plain-language overview](docs/chronos/OVERVIEW.md) · [design](docs/chronos/design.md) |
| **mongo** | *internal* | Shared storage. Deliberately not published to the host. | — |

The two are named for what they hold: **Akasha** (the aether said to record all
things) is the canon; **Chronos** (time) is the sequence of events through it.

**How they fit together.** Characters, items and locations are articles in
Akasha. Chronos never invents them — it *references* them, and refuses a
reference to something that doesn't exist. So there is one canon, and the
timeline is checked against it.

---

## Run it

```bash
# 1. Set the cookie-signing secret (git-ignored, auto-loaded by compose).
#    One value, shared by both services, so a single login covers them.
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > docker/.env

# 2. Build and start all three containers
docker compose -f docker/docker-compose.nas.yml up --build -d
```

- **http://localhost:5002/** — the article editor. **Register the first account;
  it becomes the administrator.**
- **http://localhost:5003/health** — chronos liveness (it has no UI).

Each service's README documents its own configuration, API and deployment
notes. For a NAS install, see
[Deploy on a Synology NAS](docs/akasha/README.md#deploy-on-a-synology-nas).

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

curl -s -b /tmp/c localhost:5003/books/ember-pact/validate   # the full report
curl -s -b /tmp/c localhost:5003/books/ember-pact/graph      # how the threads connect

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
tests/               one suite per service (in-memory MongoDB)
docker/              Dockerfiles, the compose stack, demo seed script
docs/                per-service READMEs and design documents
```

Both services follow the same conventions: **inversion of control** (every
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
pytest        # both suites, entirely against an in-memory MongoDB — no server needed
ruff check    # lint
```

The editable install puts `visualizer` on the path, so no `PYTHONPATH` is needed.
