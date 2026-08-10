# What the Chronos UI cannot do yet

*Audited 2026-08-10 against the routes the app actually registers and the calls
`static/js/api.js` actually makes. Not a wish list — every gap below is a
capability the JSON API already has, tested, that the browser has no way to
reach.*

Chronos is an API first, with a visualiser layered on top. The visualiser grew
read-only and is being made editable [one surface at a
time](design.md#2-principles-consistent-with-the-existing-codebase), so the
interesting question is not "what is missing from the product" but **"where does
a writer with no terminal hit a wall?"**

Of the **26 content routes** the app registers, **19 are reachable from the UI**
and **7 are not**.

**There is no longer a blocking gap.** A writer can now create a book, write its
scenes, thread them into a plotline and mark the book's ending without leaving
the browser — see [the flow, end to end](#the-flow-end-to-end). What remains is
housekeeping and sharing.

---

## Significant: the book exists but stays incomplete

| Missing from the UI | The API it would call | What it costs |
| --- | --- | --- |
| **Delete a scene** | `DELETE /books/{book}/events/{event}` | The scene form writes immediately, so abandoning a plotline edit afterwards leaves an orphan scene. It stays *findable* — the Add-scene picker lists every scene in the book — but there is no way to remove it. |
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

For completeness, the 19 reachable routes: listing, reading, **creating** and
**updating** books; **designating the terminus**; the story graph; listing, reading, creating
and updating scenes; the full plotline lifecycle (create, read, update, delete);
and the five visualiser helpers (`/ui/plotlines`, `/ui/ticks`, `/ui/entities`,
`/ui/entity/...`, `/ui/plotline-preview`).

### The flow, end to end

What a writer with no terminal can now do from a standing start:

1. **Register**, and land on *Your books* — which offers **+ New book** rather
   than an apology.
2. **Create a book**, choosing there and then whether ticks are plain numbers or
   a calendar of named cycles. The choice is shown back in plain language
   (*"Ticks are hours: 24 hours to a day, 30 days to a month"*) rather than left
   to be inferred from the form — and it is no longer a one-time choice: **✎**
   beside the book's title reopens the same form to rename it or swap the
   calendar.
3. **Write the cast** in Akasha (never blocked — see below).
4. **+ New plotline**, and inside it **Add scene → Write a new scene**, choosing
   characters, items and places from the real canon.
5. **✦ Mark a scene as the ending**, which is what turns the third story rule
   from invisible into reported.
6. Watch the findings appear as scenes are dragged, and save.

Steps 2 and 5 are what this document previously called blocking.

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

## What this unblocks

A `getting-started.md` — "build the Ember Pact yourself, and watch the three
continuity problems appear" — was **deferred until the blocking gap closed**, so
that the guide would not have to open with a `curl` line: the audience for it is
precisely the audience that bounces off a terminal. That guide is now writable,
and is the natural next piece of work.

The remaining eight gaps are all *housekeeping* (rename, delete, tidy up an
orphan scene) or *sharing* (collaborators). None of them stops a story being
written, which is why none is marked blocking.

### Planned: a calendar library

The one gap with a design behind it rather than just an absence. A book's
calendar is chosen once, inline, at creation. The intended next step is a
library of **named, reusable calendars** that can be attached to many books and
swapped afterwards — shared by **copying the descriptor into the book** and
recording where it came from, not by pointing at a shared record. Copying keeps
`codec_for` pure and I/O-free, keeps `GET /books` from becoming N+1, and stops
one writer's edit from silently re-labelling another writer's book; provenance is
what still allows an explicit, previewable *"the library version changed —
update?"*.

The browser side is already shaped for it: `static/js/calendars.js` holds the
descriptor vocabulary with no DOM in it, and `calendarfield.js` reduces the whole
question to `value() -> descriptor | null`, with its sources held as a list. A
library picker joins that list; nothing that consumes a calendar has to know.

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
