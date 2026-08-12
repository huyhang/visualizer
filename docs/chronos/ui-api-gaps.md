# What the Chronos UI cannot do yet

*Audited 2026-08-11 against the routes the app actually registers and the calls
`static/js/api.js` actually makes. Not a wish list — every gap below is a
capability the JSON API already has, tested, that the browser has no way to
reach.*

Chronos is an API first, with a visualiser layered on top. The visualiser grew
read-only and is being made editable [one surface at a
time](design.md#2-principles-consistent-with-the-existing-codebase), so the
interesting question is not "what is missing from the product" but **"where does
a writer with no terminal hit a wall?"**

Of the **34 content routes** the app registers, **29 are reachable from the UI**
and **5 are not**. (The count grew by the seven calendar-library routes, all of
which the UI reaches.)

**There is no longer a blocking gap, and no housekeeping one either.** A writer
can create a book, write its scenes, thread them into a plotline, mark the
book's ending, and now also *tidy up*: delete a scene, delete a thread, delete
the whole book — see [the flow, end to end](#the-flow-end-to-end). What remains
is **sharing** and one **report**.

---

## Present in the API, absent from the UI

| Missing from the UI | The API it would call | Notes |
| --- | --- | --- |
| **Whole-book report** | `GET /books/{book}/validate` | Never called by any view. Findings are shown per thread instead, so a book card reading `conflicted` has nowhere to click through to. |
| **Collaborators** | `PUT` / `DELETE /books/{book}/collaborators/{user}` | Sharing a book is entirely API-only. |
| **Absorb a continuation** | `POST /books/{book}/plotlines/{plotline}/inline` | Reachable only indirectly, through the delete-with-dependents dialog. |
| **Scene neighbourhood** | `GET /books/{book}/events/{event}/plotlines` | Not even wrapped in `api.js`. The connected-plots graph covers the same ground visually, so this may never need a UI. |

---

## What the UI *does* cover

For completeness, the 22 reachable routes: listing, reading, **creating**,
**updating** and **deleting** books — including the Akasha **world** their cast
is drawn from and their **overview**; **designating the terminus**; the story
graph; listing, reading, creating, updating and **deleting** scenes; the full
plotline lifecycle (create, read, update, delete); the five book-scoped
visualiser helpers (`/ui/plotlines`, `/ui/ticks`, `/ui/entities`,
`/ui/entity/...`, `/ui/plotline-preview`); and the one that is **not**
book-scoped, `/ui/worlds`, because it answers a question asked while a book is
being created.

### The flow, end to end

What a writer with no terminal can now do from a standing start:

1. **Register**, and land on *Your books* — which offers **+ New book** rather
   than an apology.
2. **Create a book**, choosing the **world** its cast comes from (offered from
   the Akasha databases you can read, and chosen for you when there is only
   one — without it a book with no scenes has nothing to point its pickers at)
   and whether ticks are plain numbers or
   a calendar of named cycles. The calendar choice is shown back in plain language
   (*"Ticks are hours: 24 hours to a day, 30 days to a month"*) rather than left
   to be inferred from the form — and it is no longer a one-time choice: **✎**
   beside the book's title reopens the same form to rename it or swap the
   calendar.
3. **Write the cast** in Akasha (never blocked — see below).
4. **+ New plotline**, and inside it **Add scene → Write a new scene**, choosing
   characters, items and places from the real canon. A scene that turns out to
   be missing from the *middle* goes in with **⤵** on the row above it, or
   **Insert at the start**, rather than being appended and dragged up.
5. **✦ Mark a scene as the ending**, which is what turns the third story rule
   from invisible into reported.
6. Watch the findings appear as scenes are dragged, and save.
7. **Keep house.** **Scenes** in the book header opens the scene library — every
   scene in the book, filtered and paged, written, edited or removed there. A
   scene a thread still uses names the threads before it goes; the book's ending
   refuses until another is designated; and a scene that is some thread's *only*
   scene is refused outright, because dropping it would leave a plotline with an
   empty path that no later save would accept.
8. **Delete the experiment**, from the same **✎** that renames the book — with
   the real counts of what goes with it, and the book's id to type.

Steps 2 and 5 are what this document previously called blocking; steps 7 and 8
are what it called housekeeping.

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

[**getting-started.md**](getting-started.md) — "build the Ember Pact yourself,
and watch the three continuity problems appear" — was **deferred until the
blocking gap closed**, so that the guide would not have to open with a `curl`
line: the audience for it is precisely the audience that bounces off a terminal.
It is now written, opens with *Register*, and ends where a guide should, with the
reader deleting the book they built.

The remaining five gaps are *sharing a book* (collaborators) and *reporting* (the
whole-book verdict). None of them stops a story being written or tidied up,
which is why none is marked blocking. Note that sharing a **calendar** is now in
the UI even though sharing a *book* is not — the library needed it, since a
library nobody can share is only half a library.

### Built: the calendar library

*This section previously described a plan. It is now implemented — see
[the calendar library](README.md#the-calendar-library).*

A book's calendar used to be chosen once, inline, at creation. There is now a
library of **named, reusable calendars** (`#/~calendars`) that attach to many
books, and a book may keep **several at once** — parallel cultures reckoning one
canonical tick line — with a switcher to read its scenes through any of them.

It landed on the design that was written here: attaching **copies the descriptor
into the book** and records where it came from, rather than pointing at a shared
record. Copying keeps `codec_for` pure and I/O-free, keeps `GET /books` from
becoming N+1, stops one writer's edit from silently re-labelling another
writer's book, and — the consequence that only became obvious once sharing was
real — means anyone who can read a book can read its *dates*, with no grant on
the library entry at all. Provenance (`source`, owner-qualified) is what still
allows an explicit, previewable *"the library version changed — update?"*.

Two things the plan did not anticipate:

- **Identity is `(owner, id)`, not `id`.** Calendar names are generic, so a
  global namespace would have made the first writer to register "imperial" its
  owner for everybody — and would have leaked the existence of calendars a
  writer cannot read.
- **Calendars begin and end.** `from_tick`/`until_tick` on an attachment, applied
  by a small `EraCodec` decorator, so a destroyed culture's reckoning stops
  dating the scenes that outlived it instead of inventing years for them.

The browser side was already shaped for it, as predicted: `calendars.js` held the
descriptor vocabulary with no DOM in it, and `calendarfield.js` reduced the whole
question to `value() -> descriptor | null` with its sources held as a list. The
library picker joined that list as one more `MODES` entry, and nothing that
consumes a calendar had to change.

## Re-checking this list

It will go stale; nothing enforces it (the [contract
test](../../tests/chronos/test_contract.py) holds `openapi.json` to the routes,
not the UI to either). To regenerate the route half:

```bash
python - <<'EOF'
import re, pathlib, mongomock
from werkzeug.security import generate_password_hash
from visualizer.auth import AuthStore
from visualizer.chronos.store import CalendarStore, StoryStore
from visualizer.chronos.entity_gate import FakeEntityGate
from visualizer.chronos.app import create_app

cl = mongomock.MongoClient()
auth = AuthStore(cl); auth.create_user("m", generate_password_hash("p"))
app = create_app(StoryStore(cl), FakeEntityGate(), auth, secret_key="s",
                 calendar_store=CalendarStore(cl))

SKIP = {"/static/<path:filename>", "/static/js/shared/<path:filename>",
        "/login", "/logout", "/register",
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
