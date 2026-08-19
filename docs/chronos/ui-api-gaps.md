# What the Chronos UI cannot do yet

*Audited 2026-08-17 against the routes the app actually registers and the calls
`static/js/api.js` actually makes. Not a wish list — every gap below is a
capability the JSON API already has, tested, that the browser has no way to
reach.*

Chronos is an API first, with a visualiser layered on top. The visualiser grew
read-only and is being made editable [one surface at a
time](design.md#2-principles-consistent-with-the-existing-codebase), so the
question this document asks is not "what is missing from the product" but
**"where does a writer with no terminal hit a wall?"**

Of the **43 content routes** the app registers, **39 are called from a browser**
and **4 are not**. Two of the four are the gaps below; the other two are
uncalled **by design**, because in each case a *listing* already carries
everything the single-record read would return:

- `GET /books/{book}/validate` — the whole-book report is in the UI, built
  instead on `GET /books/{book}/ui/issues`: the same rules, shaped for a reader
  rather than a machine. See [the book's report](README.md#the-books-report).
- `GET /calendars/{owner}/{calendar}` — likewise: the library listing returns
  each entry in full.

`GET /books/{book}/goals/{goal}` used to be on that list, on the grounds that
the goals page needs every goal anyway. The peek panel changed the arithmetic:
it opens a goal beside a thread, the plotline table, the report or the story
map, none of which hold the book's goals — so fetching thirty to draw one was
the same trade in reverse. The UI now calls both.

One wrinkle in "from the UI": the six collaborator routes (three for books,
three for calendars) are reached from **Akasha's Account page**, not from
anything Chronos serves — except sharing a calendar, which the library does call
directly. They are counted as reachable because the question this document asks
is whether a writer without a terminal hits a wall, and they do not.

**Neither remaining gap is blocking, and neither is housekeeping.** A whole story
can be written, checked, shared and deleted from the browser.

---

## Present in the API, absent from the UI

| Missing from the UI | The API it would call | Notes |
| --- | --- | --- |
| **Absorb a continuation** | `POST /books/{book}/plotlines/{plotline}/inline` | The *capability* is reachable — the delete-with-dependents dialog absorbs a thread via `DELETE …?inline=true` — but this route, which absorbs without deleting, is called by nothing. A writer who wants to flatten a continuation and keep both threads has no way to say so. |
| **Scene neighbourhood** | `GET /books/{book}/events/{event}/plotlines` | Not even wrapped in `api.js`. The connected-plots graph covers the same ground visually, so this may never need a UI. |

---

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

A closed gap leaves this document rather than accumulating in it — the reasoning
belongs with the thing that was built. Sharing is in
[`sharing.py`](../../src/visualizer/sharing.py) and [akasha's
sharing](../akasha/sharing.md); the calendar library and the book's report are in
[the chronos README](README.md); why the report folds per-thread findings instead
of reading `/validate` is in
[`book_health.py`](../../src/visualizer/chronos/book_health.py).
