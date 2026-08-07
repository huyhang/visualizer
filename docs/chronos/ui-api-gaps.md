# What the Chronos UI cannot do yet

*Audited 2026-08-06 against the routes the app actually registers and the calls
`static/js/api.js` actually makes. Not a wish list — every gap below is a
capability the JSON API already has, tested, that the browser has no way to
reach.*

Chronos is an API first, with a visualiser layered on top. The visualiser grew
read-only and is being made editable [one surface at a
time](design.md#2-principles-consistent-with-the-existing-codebase), so the
interesting question is not "what is missing from the product" but **"where does
a writer with no terminal hit a wall?"**

Of the **26 content routes** the app registers, **16 are reachable from the UI**
and **10 are not**.

---

## Blocking: the flow cannot start

| Missing from the UI | The API it would call |
| --- | --- |
| **Create a book** | `POST /books/{book}` |

This is the only true dead end. A new writer logs in, lands on *Your books*,
reads *"You have no readable books yet"* — and there is no button. Everything
downstream is reachable once a book exists, so this single gap is what stops a
[getting-started guide](#why-this-matters-now) from being written.

There is a fiddly part hiding inside it. A book carries a **calendar**
(`base_unit`, `cycles`, `epoch_label`, see [design §4.1](design.md)), and that
descriptor decides what a tick *means*: what the timeline rail groups by, and
what the scene form's live label reads back as you type. A "+ New book" control
needs at least a plain-numbers-versus-calendar choice — a bare title field would
quietly commit every book to `IdentityCodec` forever, since there is also no way
to change a calendar afterwards.

## Significant: the book exists but stays incomplete

| Missing from the UI | The API it would call | What it costs |
| --- | --- | --- |
| **Set the terminus** | `POST /books/{book}/terminus/{event}` | One of the three story rules becomes undemonstrable. `verdictNotes` deliberately stays silent when no terminus is set (otherwise every thread in the book carries the same complaint), so a UI-only writer never learns the concept exists. |
| **Delete a scene** | `DELETE /books/{book}/events/{event}` | The scene form writes immediately, so abandoning a plotline edit afterwards leaves an orphan scene. It stays *findable* — the Add-scene picker lists every scene in the book — but there is no way to remove it. |
| **Rename a book, change its calendar** | `PUT /books/{book}` | A calendar chosen at creation is permanent from the browser. |
| **Delete a book** | `DELETE /books/{book}` | No way to clean up an experiment. |

## Present in the API, absent from the UI

| Missing from the UI | The API it would call | Notes |
| --- | --- | --- |
| **Whole-book report** | `GET /books/{book}/validate` | Never called by any view. Findings are shown per thread instead, so a book card reading `conflicted` has nowhere to click through to. |
| **Collaborators** | `PUT` / `DELETE /books/{book}/collaborators/{user}` | Sharing a book is entirely API-only. |
| **Absorb a continuation** | `POST /books/{book}/plotlines/{plotline}/inline` | Reachable only indirectly, through the delete-with-dependents dialog. |
| **Scene neighbourhood** | `GET /books/{book}/events/{event}/plotlines` | Not even wrapped in `api.js`. The connected-plots graph covers the same ground visually, so this may never need a UI. |

---

## What the UI *does* cover

For completeness, the 16 reachable routes: listing and reading books; the story
graph; listing, reading, creating and updating scenes; the full plotline
lifecycle (create, read, update, delete); and the five visualiser helpers
(`/ui/plotlines`, `/ui/ticks`, `/ui/entities`, `/ui/entity/...`,
`/ui/plotline-preview`).

## Not a gap: Akasha

A book is only half the story — its scenes reference characters, items and
places, and Chronos [refuses to invent them](README.md). None of that is
blocked:

- Akasha's **New article** flow takes a database, collection, title and slug,
  and `ensureCollection` creates the database and collection implicitly. No
  namespace has to exist first.
- Creating a collection *or* a document calls `grant_owner`, so the writer
  immediately holds read on what they made — which is why Chronos's article
  picker returns their own cast rather than an empty list.

So the cast and the places can be written entirely in the browser today.

---

## Why this matters now

A `getting-started.md` — "build the Ember Pact yourself, and watch the three
continuity problems appear" — is planned and **deferred until these gaps close**.
The deliberate choice was to fix the UI rather than publish a guide with a
`curl` line in it: the audience for that guide is precisely the audience that
bounces off a terminal.

The natural first slice is **"+ New book"** plus **"Mark as the ending"**.
Together they turn that guide from impossible into writable, and both are pure
front-end work — the endpoints exist, are covered by tests, and book creation
already grants the creator ownership.

## Re-checking this list

It will go stale; nothing enforces it (the [contract
test](../../tests/chronos/test_contract.py) holds `openapi.json` to the routes,
not the UI to either). To regenerate the route half:

```bash
python - <<'EOF'
import re, pathlib, mongomock
from werkzeug.security import generate_password_hash
from visualizer.auth import AuthStore
from visualizer.chronos.store import StoryStore
from visualizer.chronos.entity_gate import FakeEntityGate
from visualizer.chronos.app import create_app

cl = mongomock.MongoClient()
auth = AuthStore(cl); auth.create_user("m", generate_password_hash("p"))
app = create_app(StoryStore(cl), FakeEntityGate(), auth, secret_key="s")

SKIP = {"/static/<path:filename>", "/login", "/logout", "/register",
        "/auth/me", "/change-password", "/health", "/"}
for rule in sorted(app.url_map.iter_rules(), key=str):
    if str(rule) in SKIP:
        continue
    for method in sorted(rule.methods & {"GET", "POST", "PUT", "DELETE"}):
        print(f"{method:<6} {rule}")
EOF
```

Then cross-reference against `src/visualizer/chronos/static/js/api.js`. Mind one
trap: a naive `api\.(\w+)\(` grep reports `getEntity` as unused, because
`entities.js` splits the call across two lines. Allow whitespace:
`api\s*\.\s*(\w+)\s*\(`.
