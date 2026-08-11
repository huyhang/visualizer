# chronos

A Flask + MongoDB API service that helps fiction writers manage the **plotlines**
of their work: who did what, where, and when — and how those threads split,
weave, and finally come together. One of two services in the
[visualizer](../../README.md) stack.

Chronos ships alongside [`akasha`](../Akasha/README.md) and
shares its MongoDB and its login. Characters, items and locations live there as articles;
Chronos references them and refuses to invent them.

- **New to the concepts?** Read [OVERVIEW.md](OVERVIEW.md) — the same ideas in
  plain language, no code.
- **Want the rationale?** Read [design.md](design.md) — the
  full design and the decisions behind it.
- **Want the contract?** See [openapi.json](openapi.json).
- **Wondering what the UI can't do yet?** See
  [ui-api-gaps.md](ui-api-gaps.md) — the audited list of API capabilities the
  browser has no way to reach.

> **An API with a visualiser on top.** Served at `/`: pick a book, browse its
> plotlines (name-ordered, word-filtered, paginated), and open one to see its
> events as cards on a vertical timeline — with the Akasha articles they
> reference shown inline. Those referenced articles are fetched through Chronos
> (so the browser stays same-origin) and are subject to **both** book-read and
> the article's own Akasha read grant.
>
> The timeline also flags where a thread **joins, departs, or is shared with**
> others, and from any plotline you can open **Connected plots** — a branch/merge
> (git-graph) diagram of just the threads that meet it (i.e. share a *non-terminus*
> event), laid out by time and colour-coded per thread. A full whole-book **story
> map** over the same `/graph` data is still planned (design §12).
>
> **A whole story can now be written from the UI** — create a book (calendar and
> all), write its scenes, thread them into plotlines, and mark the scene every
> thread must reach. See [Starting a book](#starting-a-book-in-the-ui) and
> [Editing plotlines](#editing-plotlines-in-the-ui). A book can be renamed and
> its calendar swapped afterwards; collaborators and deletion are still
> API-only.

---

## Run it

Chronos is one of three containers (`akasha`, `chronos`, `mongo`)
defined in `docker/docker-compose.nas.yml`. MongoDB has **no published port** —
it is reachable only inside the Docker network.

```bash
# 1. Set the cookie-signing secret (git-ignored, auto-loaded by compose).
#    Both services must share it, so one login works across both.
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > docker/.env

# 2. Build and start
docker compose -f docker/docker-compose.nas.yml up --build -d
```

Both services run in one process behind a single origin (port `5002`): akasha at
`/`, chronos at `/timeline`.

| Path | Purpose |
| --- | --- |
| `5002/` | akasha — articles: characters, items, locations |
| `5002/timeline` | chronos — books, plotlines, events (+ the visualiser) |
| `mongo` | *(internal only)* — shared storage |

Check both are alive:

```bash
curl -s localhost:5002/health            # {"status":"ok"}
curl -s localhost:5002/timeline/health   # {"service":"chronos","status":"ok"}
```

**Configuration** (environment variables, set in `docker/.env`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | signs session cookies — **required**. Use the *same* value as Akasha so one session covers both. | none (must be set) |
| `MONGO_URI` | MongoDB connection string | `mongodb://mongo:27017` |
| `SESSION_COOKIE_SECURE` | mark the session cookie HTTPS-only (enable behind an HTTPS reverse proxy) | `false` |

Chronos stores everything in a reserved `_chronos` database, which the
Akasha API deliberately refuses to expose.

> **Run locally without Docker** (needs a reachable MongoDB). Either run the
> combined app on one port —
> ```bash
> SECRET_KEY=dev MONGO_URI=mongodb://localhost:27017 \
>   gunicorn -b localhost:5002 visualizer.wsgi:application   # akasha at /, chronos at /timeline
> ```
> — or run chronos standalone on its own port for API work:
> ```bash
> SECRET_KEY=dev MONGO_URI=mongodb://localhost:27017 \
>   gunicorn -b localhost:5003 visualizer.chronos.wsgi:app
> ```

---

## Concepts

| Term | What it is |
| --- | --- |
| **Event** | Characters + items, at one location, over a timeframe, with a description. The atom of the model. |
| **Plotline** | An **ordered** list of events plus a non-empty set of goals. Order is the contract. May `continues_into` another plotline so a shared ending is stored once. |
| **Book** | A collection of plotlines with one designated **Terminus**. |
| **Overview** | Free prose on a book or a plotline, saying what it is about. Optional, read by no rule, empty rather than null when unwritten, and capped at 10 000 characters — it is returned whole in every listing. |
| **Terminus** | The single event every plotline in the book must end at. |
| **Trunk** | Not a distinct type — the conventional name for the plotline that holds a **shared ending** other threads `continues_into` (see [Shared endings](#shared-endings)). |
| **EntityRef** | A pointer to a Akasha article — `{database, collection, id}`. Must already exist. |

Events, plotlines and terminus are **scoped to one book**; ids are unique within
their book. Two plotlines may share an event — that is how threads converge and
diverge.

### Time

### Drafting without timing

Both ticks are **optional** — give both or neither. Omitting them records an
**unscheduled** scene, so a writer can sketch a whole thread in order and fill
in the clock later. Unscheduled scenes are skipped by conflict and ordering
checks (they have no interval), and they appear in `/validate` under
`unscheduled` as a to-do list — they do **not** make a book conflicted.

Chronos also infers the **window** each undated scene must fall into, from its
scheduled plotline neighbours:

```jsonc
"window": {"earliest": 24, "latest": 96,
           "earliest_label": "Year 1, Month 1, Day 2, 00:00 AF",
           "latest_label":   "Year 1, Month 1, Day 5, 00:00 AF",
           "impossible": false}
```

If the neighbours leave **no room** (`impossible: true`, `IMPOSSIBLE_WINDOW`)
that *is* a contradiction and the book goes conflicted — and it catches cases
ordering can't, where the constraining scenes live in different threads.

Every event has an integer `start_tick` and `end_tick` on a per-book timeline,
`start_tick <= end_tick`. Ticks are **signed**, so flashbacks are negative.
Intervals are **half-open `[start, end)`** — touching is not overlapping.

A book may carry a `calendar` that formats ticks into readable labels:

```jsonc
"calendar": {
  "base_unit": "hour",
  "cycles": [{"name":"day","size":24},{"name":"month","size":30},{"name":"year","size":12}],
  "epoch_label": "AF"
}
```

Tick `200` then reads `Year 1, Month 1, Day 9, 08:00 AF` in responses.

> **Note:** the calendar currently formats **output only**. Writes must send
> integer ticks; posting a label string is not yet supported.

---

## The two rule classes

This is the most important thing to understand about Chronos's behaviour.

**Hard rules — the write is rejected.** These are referential: they are about
whether the data makes structural sense.

| Rule | Response |
| --- | --- |
| An `EntityRef` doesn't exist in Akasha | `422 ENTITY_NOT_FOUND` |
| `start_tick > end_tick`, a non-integer tick, or only one of the two given | `400 INVALID_TIMEFRAME` |
| Empty event list, empty goals, unknown event id, unknown `continues_into` target | `400 INVALID_PLOTLINE` |
| A `continues_into` chain that loops | `422 PLOTLINE_CYCLE` |
| Deleting a plotline others continue into | `409 PLOTLINE_IN_USE` |
| Deleting an event a plotline still lists | `409 EVENT_IN_USE` |
| Deleting the book's terminus | `409 TERMINUS_IN_USE` |
| Stale `If-Match` / `_rev` | `409 REVISION_CONFLICT` |

**Soft rules — the write succeeds and the problem is reported.** These are
story-logic: they are about whether the *story* holds together. They never block
a save, for any book, solo or shared.

| Rule | Where it shows up |
| --- | --- |
| **Temporal conflict** — a character in two *different* locations at overlapping times | `GET /books/<book>/validate`, book `status` |
| **Ordering** — a plotline's events not in non-overlapping order | plotline `status.ordering` |
| **Convergence** — a plotline not ending at the terminus | plotline `status.ends_at_terminus` |
| **Missing article** — a scene naming a character, item or location that has been deleted from Akasha | `validate.missing_entities`, book `status`, the scene's findings |

A book reports `status: "consistent"` or `"conflicted"`. Draft freely; reconcile
when you're ready.

The last one is the only rule that can start failing without anyone touching the
timeline: Akasha holds no back-reference to Chronos, so deleting an article says
nothing about the scenes that name it. Writes still refuse an unknown reference,
so a dangling one is always an article removed *after* the scene was written —
and Akasha's deletes are soft, so restoring the article clears the report.

---

## API

All routes require authentication (log in at `POST /login` on either service;
the session cookie works on both). Writes accept an `If-Match` revision
precondition and return an `ETag`.

```
GET    /health                                       liveness (no auth)

GET    /books                                        books you can read
POST   /books/<book>                                 create (you become owner)
GET    /books/<book>                                 read (incl. computed status)
PUT    /books/<book>                                 update title/overview/terminus/calendar
DELETE /books/<book>                                 delete book + its contents
POST   /books/<book>/terminus/<event>                designate the terminus
GET    /books/<book>/validate                        full invariant report
GET    /books/<book>/graph                           the whole story graph

POST   /books/<book>/plotlines/<plotline>            create
GET    /books/<book>/plotlines/<plotline>[?expand=events]
PUT    /books/<book>/plotlines/<plotline>            replace (reorder / edit goals)
POST   /books/<book>/plotlines/<plotline>/inline     absorb its continuation chain
DELETE /books/<book>/plotlines/<plotline>[?inline=true]   block if depended on, unless inlining

GET    /books/<book>/events                          the book's scenes, in story order
POST   /books/<book>/events/<event>                  create
GET    /books/<book>/events/<event>
PUT    /books/<book>/events/<event>
DELETE /books/<book>/events/<event>[?detach=true]    detach removes it from plotlines first
GET    /books/<book>/events/<event>/plotlines[?relation=converging|diverging|through]

PUT    /books/<book>/collaborators/<user>            invite / set role (owners only)
DELETE /books/<book>/collaborators/<user>            remove (owners only)
```

The visualiser adds a few book-scoped helpers of its own. They compute nothing
the rules above do not — they exist so the browser can stay same-origin and ask
one question per screen:

```
GET    /books/<book>/ui/plotlines    filtered, name-ordered, paginated table
POST   /books/<book>/ui/plotline-preview   judge a candidate thread; writes nothing
GET    /books/<book>/ui/entities     type-ahead over referenceable Akasha articles
GET    /books/<book>/ui/entity/<db>/<collection>/<id>   read one article
```

### Shared endings

Threads that merge would otherwise repeat the whole shared tail in every
plotline — and inserting one scene into the ending would mean editing them all.
Instead a plotline can store just its own segment and name the plotline it
continues into. That shared-tail plotline is called the **trunk** — it is not a
special type, just an ordinary plotline the others point at:

```
trunk         [meet-at-emberport, the-coronation]
knights-road  [aldric-departs]     continues_into: trunk
spys-shadow   [lyra-infiltrates]   continues_into: trunk
```

Every rule runs on the resolved **effective path**, so these threads still
converge on the terminus and still appear in the graph with the junction edge.
Reads give you both `events` (stored, send this back on a write) and
`effective_events` (resolved). Edit `trunk` once and every thread on it follows.

The two chain rules are hard: the target must exist (`400`), and the chain must
not loop (`422 PLOTLINE_CYCLE`).

**Breaking a thread off the trunk.** `POST …/plotlines/<id>/inline` copies the
resolved path into the thread's own `events` and clears `continues_into` — it
keeps the exact story and just drops the dependency. It's a no-op when there's
nothing to absorb, so it's safe to repeat. (Clearing `continues_into` with a
plain `PUT` also detaches, but leaves the thread stopping at its own segment,
which then won't reach the terminus.)

**Deleting a shared trunk** is blocked with `409 PLOTLINE_IN_USE` while other
threads continue into it — a dangling `continues_into` has no effective path.
`?inline=true` absorbs it into each dependent first, so their stories survive.

### Reading a plotline

Lean by default; `?expand=events` inlines event summaries with titles, calendar
labels, and convergence markers into `effective_events`.

```jsonc
{
  "kind": "plotline",
  "id": "knights-road",
  "title": "The Knight's Road",
  "overview": "Aldric carries the seal north, and learns what it is for.",
  "book": "ember-pact",
  "goals": ["Deliver the Ember Seal", "Reach the coronation alive"],
  "events": ["aldric-departs"],                // stored: this thread's own segment
  "continues_into": "trunk",                   // ... then it joins the shared ending
  "effective_events": ["aldric-departs", "meet-at-emberport", "the-coronation"],
  "rev": 1,
  "status": {                                  // computed, read-only
    "ordering":         {"state": "ok"},
    "ends_at_terminus": {"state": "ok"},
    "continuation":     {"state": "ok"},
    "span": {"start_tick": 0, "end_tick": 210, "start_label": "…", "end_label": "…"}
  },
  "_links": { "self": "…", "expanded": "…", "validate": "…", "graph": "…" }
}
```

Top-level fields are stored and editable; `status`, `_links` and
`rev` are server-computed — send only the stored fields back on a `PUT`.

### Where threads meet

`GET /books/<book>/events/<event>/plotlines` answers "which plotlines converge
into / diverge out of *this* event", with titles, times and a prose summary.
**Convergence** means in-degree > 1 (more than one distinct *predecessor*);
**divergence** means out-degree > 1. Two plotlines arriving from the same prior
event are not a convergence — the merge already happened upstream.

### Starting a book in the UI

*Your books* offers **+ New book** to any logged-in writer — a book is the one
thing needing no prior grant, since creating it is what makes you its owner.

The form asks for a title, an id (derived from the title until you take it over,
and permanent thereafter), an optional **overview**, the **world** its cast comes
from, and — the part worth pausing on — **how this book counts time**.

**Overview.** What the book is about, in the writer's own words. No rule reads
it; it exists so that a shelf of books says more than a row of titles. Plotlines
have one too, shown under the thread's name in the table and matched by the
filter box, so two similarly-titled threads can be told apart without opening
either.

**World.** Which Akasha database holds this book's characters, items and places.
The chooser offers only worlds you can read, and picks for you when there is
only one. It is a *default, not a fence*: an `EntityRef` still names its own
database, so a scene may reach into another world deliberately — this is simply
what the article pickers search first.

It exists because the scope used to be **inferred** from the scenes a book
already had, which is no help to a book that has none: a new book's picker
searched a database named after the book, found nothing, and advised the writer
to go and create articles that were sitting right there. Books written before
the field existed still infer their scope from their scenes, so nothing needed
migrating.

Now, the calendar. Either:

- **Plain numbers.** Ticks are bare integers; a scene at tick `240` reads back as
  `240`. Pick a scale and stay consistent.
- **A calendar.** A base unit plus the cycles that nest over it, smallest first,
  and an optional era. As you type, the form reads the descriptor back in plain
  language — *"Ticks are hours: 24 hours to a day, 30 days to a month, 12 months
  to a year."* — so the thing you are committing to is legible before you commit
  to it. Presets cover the common shapes.

That matters because the calendar decides what a tick *means* everywhere
downstream — what the timeline rail groups by, what the scene form reads back as
you type.

**Changing it later.** The **✎** beside a book's title on its plotline table
reopens the same form to rename the book, edit its overview or swap its calendar.
This is safe by construction rather than by care: ticks are canonical integers
and a calendar formats output only, so a swap re-labels the book without moving a
single scene, and no conflict, ordering or convergence verdict can change as a
result.

One thing the form has to do that the route does not advertise: `PUT
/books/<book>` **replaces** the stored book rather than patching it, so a body
carrying only the changed field silently erases the others. The form always
resends title, overview, calendar *and* terminus together.
[One test pins that](../../tests/chronos/test_api.py) from both directions at the
API, and [another reads the two editors](../../tests/chronos/test_ui_assets.py)
to check their payloads still name every stored field — because the fields
easiest to drop are the ones nothing recomputes and no verdict mentions, so
losing one raises nothing at all.

**Deleting a book.** The same form carries **Delete book**, for owners only. It
takes the book's plotlines and scenes with it, hard, with no history to restore
from — so the confirmation names the real counts ("3 plotlines and 17 scenes")
and asks you to type the book's id. The articles its scenes reference belong to
Akasha and are untouched. The grants naming the book are swept along with it:
ids may be reused, and a grant left behind would silently hand the next book of
that name to the previous owner.

A malformed calendar is refused at the write (`400 INVALID_BOOK`) rather than
stored and left to break every later read.

**Marking the ending.** The terminus — the one scene every plotline in the book
must reach — is set from the plotline editor: **✦** on any scene you own. It is a
book-level write, so it lands immediately rather than waiting on the editor's
Save, and replacing an existing terminus asks first, because it silently
re-judges every other thread in the book. Until a terminus is set, the
convergence rule stays deliberately quiet.

### Editing plotlines in the UI

A plotline view has an **Edit plotline** button (and the book's table a **New
plotline** one) for anyone with `write` on the book — `GET /books/<book>` now
reports `permissions`, so the UI knows before it offers.

The editor opens as a modal over whatever you were reading — editing a thread is
a detour, and closing it puts you back on the same table page, same filter. Drag
the scenes into the order you want (or focus one and press ↑ / ↓, which also
works without a mouse), add or remove them, rename the thread, adjust its goals,
point it at a thread to continue into — then **Save**, which is one `PUT`
carrying `If-Match`. A save that would overwrite someone else's edit is refused
(409) rather than winning silently, and Cancel costs nothing.

Two things make it more than a list editor:

- **Conflicts appear as you drag.** Every change is sent to
  `POST /books/<book>/ui/plotline-preview`, which presents the *candidate*
  thread exactly as saving it would — resolved path, per-scene findings, status
  — without writing. The result says `kind: "plotline-preview"` and carries no
  `rev` or `self` link, because the thread it describes may not exist yet. So the same rules that judge a saved thread judge the draft,
  and no rule is reimplemented in the browser. Findings still never block a save
  (§8.1): the marks tell you what does not add up; you decide.
- **Inherited scenes are locked.** A thread that `continues_into` another shows
  that thread's scenes greyed out: they are stored elsewhere, so reordering them
  here would be a lie. Each expanded scene says which it is (`owned`).

Scenes themselves can be written and corrected from the same screen — **Add
scene → Write a new scene**, or ✎ on a scene you already have (fixing a scene's
timing is usually how you fix a conflict). Characters, items and places are
chosen from a picker that searches the real Akasha canon through
`GET /books/<book>/ui/entities`, filtered to articles you may read: Chronos still
refuses to invent them. Each field searches its own kind of article, so a
character cannot be filed as a place.

A plotline needs at least one of its **own** scenes, so a thread that is nothing
but a continuation of another cannot be expressed; the form says so rather than
letting you hit a 422. Deleting a thread that others continue into is refused
until you agree to absorb it into them (the `?inline=true` path), which keeps
their stories intact.

### Errors

Every error shares one shape, so learning it once covers all of them:

```jsonc
{"error": "…human readable…", "code": "ENTITY_NOT_FOUND", "evidence": {"missing": [...]}}
```

The same `code`/`evidence` vocabulary appears in `status` verdicts and
`/validate`.

---

## Collaboration

Creating a book makes you its **owner**. Owners invite others:

```bash
curl -X PUT localhost:5002/timeline/books/ember-pact/collaborators/finn \
  -H 'Content-Type: application/json' -d '{"role":"editor"}'
```

Roles are presets over the shared permission model: `reader` (read),
`editor` (read+write), `owner` (read+write+delete). Invites are idempotent.

Concurrent edits to the *same* record are guarded by `If-Match`/`_rev`
(last-write-wins is prevented). Conflicts *between* records are reported, not
blocked — see the soft rules above.

> **Divergences from the design, as built:** ownership is inferred from holding
> `delete` at book scope rather than a dedicated `share` permission, and
> `GET /collaborators` and `GET /activity` (design §7.5) are not implemented.

### Grants and the shared store

Chronos and Akasha share one `_auth` store. Grants are namespaced by a
`resource_type` discriminator (`"book"` vs `"database"`) that must match
**exactly**, so a book named `x` never confers access to a Akasha
database named `x`. Grants written before this field are read as `"database"`.

---

## Seed a demo story

`docker/seed_demo.py` builds a book ("The Ember Pact") over the real HTTP APIs —
entities, a calendar, six events, four plotlines, a terminus — and demonstrates
both rule classes.

```bash
python docker/seed_demo.py        # seed; leaves the book CONFLICTED
python docker/seed_demo.py --fix  # repair everything; leaves it CONSISTENT
```

Three plotlines are sound. The fourth, **"The Witness's Tale"**, is broken
deliberately so a fresh seed trips **all three soft checks at once**:

| Problem | Why | Reported as |
| --- | --- | --- |
| Aldric is at Highkeep (hours 0–24) *and* Emberport (hours 10–30) | overlapping times, different places | `temporal_conflicts` |
| The thread lists hour 48–72 before hour 10–30 | out of order | `ordering` |
| The thread stops at the disputed sighting | never reaches the terminus | `convergence.failures` |

The script also shows a **hard** rule for contrast: an event referencing a
character that doesn't exist is refused with `422 ENTITY_NOT_FOUND`. Everything
else is written successfully — the story problems are reported, not blocked.

`--fix` moves the sighting to hours 30–40 and carries the thread through to the
terminus, and the book turns `consistent`. Re-running is safe (records are
updated, not duplicated), and re-running without `--fix` breaks it again.

Log in as `mara` / `ember-pact-demo` to explore the result.

---

## Backups

Chronos shares one MongoDB with akasha, so backups are a stack-level concern:
`docker/backup.sh` plus a DSM scheduled task, documented under
[Synology deployment → Backups](../synology-deployment.md#backups).

---

## Development & tests

Use the repo's **`visualizer` conda env (Python 3.11)** — see the root
[README](../../README.md#development--tests). Then from the repo root:

```bash
pytest -q tests/chronos     # in-memory MongoDB (mongomock); no server needed
ruff check src/visualizer/chronos
```

### Layout

Dependencies point inward; only the outer edge touches Flask, only the seams
touch a database.

| Module | Role |
| --- | --- |
| `timeline`, `conflicts`, `ordering`, `book_rules`, `reports`, `plotline_health`, `browsing`, `calendar`, `validation`, `models` | **pure logic** — no I/O, no Flask; where correctness lives |
| `store.StoryStore` | persistence seam (Mongo, OCC, injected clock) |
| `entity_gate.EntityGate` | the boundary to Akasha (`InProcessEntityGate`, `FakeEntityGate`) |
| `services` | orchestration: load → validate purely → persist → present |
| `presenters` | the single source of every response shape |
| `app`, `wsgi` | Flask factory (injected seams) and entrypoint |

`book_rules` builds each book's story graph with **NetworkX** in-process — no
graph database. Book graphs are tiny, so this is cheap, and it keeps one
datastore (design §9).

Tests mirror the layers: pure-logic units, store/gate, service orchestration
with fakes, HTTP integration, an OpenAPI **contract** test, and cross-service
**grant isolation** tests.
