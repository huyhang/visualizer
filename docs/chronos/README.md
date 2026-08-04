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
- **Want the contract?** See [openapi.json](../openapi.json).

> **Mostly an API.** Books and events are created and edited over the JSON API
> below. There is now a **read-only visualiser** served at `/`: pick a book,
> browse its plotlines (name-ordered, word-filtered, paginated), and open one to
> see its events as cards on a vertical timeline — with the Akasha articles they
> reference shown inline. Those referenced articles are fetched through Chronos
> (so the browser stays same-origin) and are subject to **both** book-read and
> the article's own Akasha read grant. It never writes. A full `/graph` viewer is
> still planned (design §12).

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

| Service | Host port | Purpose |
| --- | --- | --- |
| `akasha` | 5002 | articles: characters, items, locations |
| `chronos` | 5003 | books, plotlines, events |
| `mongo` | *(internal only)* | shared storage |

Check both are alive:

```bash
curl -s localhost:5002/health   # {"status":"ok"}
curl -s localhost:5003/health   # {"service":"chronos","status":"ok"}
```

**Configuration** (environment variables, set in `docker/.env`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | signs session cookies — **required**. Use the *same* value as Akasha so one session covers both. | none (must be set) |
| `MONGO_URI` | MongoDB connection string | `mongodb://mongo:27017` |
| `SESSION_COOKIE_SECURE` | mark the session cookie HTTPS-only (enable behind an HTTPS reverse proxy) | `false` |

Chronos stores everything in a reserved `_chronos` database, which the
Akasha API deliberately refuses to expose.

> **Run locally without Docker** (needs a reachable MongoDB):
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
| **Terminus** | The single event every plotline in the book must end at. |
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

A book reports `status: "consistent"` or `"conflicted"`. Draft freely; reconcile
when you're ready.

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
PUT    /books/<book>                                 update title/terminus/calendar
DELETE /books/<book>                                 delete book + its contents
POST   /books/<book>/terminus/<event>                designate the terminus
GET    /books/<book>/validate                        full invariant report
GET    /books/<book>/graph                           the whole story graph

POST   /books/<book>/plotlines/<plotline>            create
GET    /books/<book>/plotlines/<plotline>[?expand=events]
PUT    /books/<book>/plotlines/<plotline>            replace (reorder / edit goals)
POST   /books/<book>/plotlines/<plotline>/inline     absorb its continuation chain
DELETE /books/<book>/plotlines/<plotline>[?inline=true]   block if depended on, unless inlining

POST   /books/<book>/events/<event>                  create
GET    /books/<book>/events/<event>
PUT    /books/<book>/events/<event>
DELETE /books/<book>/events/<event>[?detach=true]    detach removes it from plotlines first
GET    /books/<book>/events/<event>/plotlines[?relation=converging|diverging|through]

PUT    /books/<book>/collaborators/<user>            invite / set role (owners only)
DELETE /books/<book>/collaborators/<user>            remove (owners only)
```

### Shared endings

Threads that merge would otherwise repeat the whole shared tail in every
plotline — and inserting one scene into the ending would mean editing them all.
Instead a plotline can store just its own segment and name where it continues:

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
  "_links": { "self": "…", "expanded": "…", "validate": "…", "graph": "…" },
  "_schema": "/openapi.json#/components/schemas/Plotline"
}
```

Top-level fields are stored and editable; `status`, `_links`, `_schema` and
`rev` are server-computed — send only the stored fields back on a `PUT`.

### Where threads meet

`GET /books/<book>/events/<event>/plotlines` answers "which plotlines converge
into / diverge out of *this* event", with titles, times and a prose summary.
**Convergence** means in-degree > 1 (more than one distinct *predecessor*);
**divergence** means out-degree > 1. Two plotlines arriving from the same prior
event are not a convergence — the merge already happened upstream.

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
curl -X PUT localhost:5003/books/ember-pact/collaborators/finn \
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
| `timeline`, `conflicts`, `ordering`, `book_rules`, `reports`, `calendar`, `validation`, `models` | **pure logic** — no I/O, no Flask; where correctness lives |
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
