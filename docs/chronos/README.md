# chronos

A Flask + MongoDB API service that helps fiction writers manage the **plotlines**
of their work: who did what, where, and when — and how those threads split,
weave, and finally come together. One of two services in the
[visualizer](../../README.md) stack.

Chronos ships alongside [`akasha`](../Akasha/README.md) and
shares its MongoDB and its login. Characters, items and locations live there as articles;
Chronos references them and refuses to invent them.

- **Want to build something?** Follow
  [getting-started.md](getting-started.md) — construct the demo story by hand in
  the browser, break it on purpose, and watch all three continuity checks fire.
  No terminal after the first `docker compose up`.
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
> others, and the book page opens a **story map**: tick any number of the book's
> threads and see them drawn together as a branch/merge (git-graph) diagram, laid
> out by time and colour-coded per thread. Each scene is one legible line until
> you click it, when it enlarges in place and the diagram reflows around it; the
> stretches a thread walks alone fold into a band you can unfold. The selection
> rides in the URL, so a map of three threads is a link. **Connected plots** is
> now a preset of that map rather than a screen of its own — opening it from a
> plotline preselects that thread and every thread it meets (i.e. shares a
> *non-terminus* event with). See design §12.
>
> **A whole story can now be written from the UI** — create a book (calendar and
> all), write its scenes, thread them into plotlines, and mark the scene every
> thread must reach. See [Starting a book](#starting-a-book-in-the-ui) and
> [Editing plotlines](#editing-plotlines-in-the-ui). A book can be renamed and
> its calendar swapped afterwards, and **sharing a book** is done from Akasha's
> [Account page](../akasha/sharing.md) alongside everything else you own.

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
| **Plotline** | An **ordered** list of events plus the goals it serves, named by id. Order is the contract. May `continues_into` another plotline so a shared ending is stored once — optionally `continues_into_at` a named scene partway down it. |
| **Goal** | Something the book is trying to bring about. A record of its own: it may rest on other goals (`depends_on`) and name the scene that delivers it (`achieved_at`). See [Goals](#goals). |
| **Book** | A collection of plotlines with one designated **Terminus**. |
| **Overview** | Free prose on a book or a plotline, saying what it is about. Optional, read by no rule, empty rather than null when unwritten, and capped at 10 000 characters — it is returned whole in every listing. |
| **Terminus** | The single event every plotline in the book must end at. |
| **Trunk** | Not a distinct type — the conventional name for the plotline that holds a **shared ending** other threads `continues_into` (see [Shared endings](#shared-endings)). |
| **EntityRef** | A pointer to a Akasha article — `{database, collection, id}`. Must already exist. |

Events, plotlines, goals and terminus are **scoped to one book**; ids are unique
within their book. Two plotlines may share an event — that is how threads
converge and diverge — and two may serve the same goal, which is how they say
they are pulling in the same direction.

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

A book carries one or more **calendars** that format ticks into readable labels:

```jsonc
"calendars": [
  {"id": "imperial",
   "label": "Imperial Reckoning",
   "descriptor": {
     "base_unit": "hour",
     "cycles": [{"name":"day","size":24},{"name":"month","size":30},{"name":"year","size":12}],
     "epoch_label": "AF"}}
]
```

Tick `200` then reads `Year 1, Month 1, Day 9, 08:00 AF` in responses.

**Several at once.** A world may count time more than one way, so a book may
attach more than one reckoning and read the same scenes through any of them:
`?calendar=<id>` on every read that formats a tick. This changes **labels and
nothing else** — no tick moves, no ordering changes, no verdict differs, because
every rule in Chronos runs on integers and cannot see the choice. Naming a
calendar the book has not attached is a `404 CALENDAR_NOT_FOUND` rather than a
silent fallback: a stale bookmark should say so, not mislabel a whole page.

**A parallel Earth.** A story that also happens here can attach a Gregorian
calendar. The library entry says only how long a tick is:

```jsonc
{"kind": "gregorian", "tick_unit": "hour"}
```

and the *book* says which Earth moment its tick `0` was, because that is the
story's own alignment — two books may share this calendar and sit centuries
apart:

```jsonc
{"id": "earth", "label": "Earth",
 "source": {"owner": "mara", "calendar": "earth"},
 "origin": "2024-02-27T00:00Z"}
```

Tick `48` then reads `February 29, 2024, 00:00 UTC`. Months are Earth's own —
28, 29, 30 or 31 days, with the leap rule and its century exception — so
`{"year": 2024, "month": 2}` spans 29 days and the same date in 2023 spans 28.
Only the labels vary in length; a tick stays exactly one day, hour or minute.

A `day`-counting calendar takes a bare date for its origin (`2024-02-27`);
anything finer takes a time and a fixed UTC offset (`Z`, or `-08:00`) and must
begin on a whole tick. The offset says which wall clock these dates are told by;
named timezones and daylight saving are not supported, because they would make
some dates name two ticks and others none.

Years run in both directions and read as `44 BCE` before year 1. What crosses
the wire is still a map of plain integers — 44 BCE is `{"year": -43}` — so a
date is the same shape in every calendar.

**Calendars that begin and end.** An attachment may carry `from_tick` /
`until_tick` — the span its culture actually kept it. A tick outside the span
formats as `before …` / `after …` rather than being given a date in a calendar
nobody was keeping. The bound is half-open, like every other interval here.

Ticks are also offset by `from_tick`, so an invented reckoning founded mid-story
reads Year 1 at its own beginning. Not Earth: its `origin` already says where it
sits, so an era only bounds it, and a scene keeps the Earth date the writer
anchored it to.

Reusable calendars live in a **library** (`/calendars`) and are *copied* into a
book when attached — see [the calendar library](#the-calendar-library).

**Scheduling by date.** A scene's timeframe may be given as a date instead of a
tick, in whichever calendar `?calendar=` names:

```jsonc
POST /books/ember-pact/events/dawn?calendar=imperial
{"location": {…},
 "start_date": {"year": 3, "month": 4, "day": 12},
 "end_date":   {"year": 3, "month": 4, "day": 12}}
```

which stores `start_tick: 19704, end_tick: 19728`. Four rules:

- Components are keyed by the calendar's **own unit names** and run from the
  largest down. Cycles are 1-indexed, the base unit 0-indexed, and the top cycle
  is open-ended (`Year 0` and below are the ticks before the epoch).
- **A date names a period.** Omitting the finer units is how you say "some time
  that day": the start takes the period's first tick and the end the first tick
  *after* it, so the same date at both ends spans exactly that day. `{"year": 3}`
  alone is the whole of Year 3.
- A **gap** (`{year, day}`) or a digit outside its cycle (`Day 31` of a 30-day
  month) is a `400 INVALID_TIMEFRAME`, not a guess. So is a date in a calendar
  whose era was not being kept then.
- Dates and ticks are alternatives, never a mixture: sending both is a `400`.
  Only ticks are stored, and nothing records which spelling was used.

`POST /books/{book}/ui/dates` resolves a date to ticks without writing anything
(the scene form's live echo), and `GET /books/{book}/ui/ticks` returns
`components` — the same date as numbers — which is how a form fills its date
fields in from a stored tick.

> **Note:** the older single `"calendar": {…}` field is still accepted on writes
> and still returned on reads (as the primary attachment's descriptor). A body
> may send one spelling or the other, never both.
>
> Parsing a formatted *label string* back into a tick is still unsupported —
> send components, or an integer tick.

---

## The two rule classes

This is the most important thing to understand about Chronos's behaviour.

**Hard rules — the write is rejected.** These are referential: they are about
whether the data makes structural sense.

| Rule | Response |
| --- | --- |
| An `EntityRef` doesn't exist in Akasha | `422 ENTITY_NOT_FOUND` |
| `start_tick > end_tick`, a non-integer tick, or only one of the two given | `400 INVALID_TIMEFRAME` |
| Empty event list, unknown event id, unknown goal id, unknown `continues_into` target | `400 INVALID_PLOTLINE` |
| A `continues_into_at` that is not on the target's path, or has no `continues_into` | `400 INVALID_PLOTLINE` |
| A `continues_into` chain that loops | `422 PLOTLINE_CYCLE` |
| A goal depending on a goal that is not in the book, or achieved at a scene that is not | `400 INVALID_GOAL` |
| A `depends_on` chain that loops | `422 GOAL_CYCLE` |
| Deleting a goal threads serve, or other goals rest on | `409 GOAL_IN_USE` |
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
| **Goals** — one the story never reaches, or one achieved before what it rests on; and the notes: nobody pursuing it, no scene yet | `validate.goals`, goal `status`, book `status`, the report |

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
PUT    /books/<book>                                 update title/overview/terminus/calendars
DELETE /books/<book>                                 delete book + its contents; refused while Logos holds prose
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
DELETE /books/<book>/events/<event>[?detach=true]    detach removes it from plotlines first; refused while a Logos section is written from it
GET    /books/<book>/events/<event>/plotlines[?relation=converging|diverging|through]

GET    /books/<book>/goals                           every goal, read against the book
POST   /books/<book>/goals/<goal>                    create
GET    /books/<book>/goals/<goal>
PUT    /books/<book>/goals/<goal>                    replace
DELETE /books/<book>/goals/<goal>[?detach=true]      detach unpicks what points at it

GET    /books/<book>/collaborators                   who can see it (owners only)
PUT    /books/<book>/collaborators/<user>            invite / set role (owners only);
                                                     also shares the book's `world`
                                                     as a reader, if you own it
DELETE /books/<book>/collaborators/<user>            remove (owners only)

GET    /calendars                                    your library + anything shared with you
POST   /calendars/<owner>/<cal>                      create (owner must be you)
GET    /calendars/<owner>/<cal>
PUT    /calendars/<owner>/<cal>                      replace
DELETE /calendars/<owner>/<cal>                      books that copied it are untouched
GET    /calendars/<owner>/<cal>/collaborators        who can see it (owners only)
PUT    /calendars/<owner>/<cal>/collaborators/<user> share (owners only)
DELETE /calendars/<owner>/<cal>/collaborators/<user> stop sharing (owners only)
```

Every read that formats a tick also takes `?calendar=<id>` — which of the book's
attached reckonings to write its dates in.

The visualiser adds a few book-scoped helpers of its own. They compute nothing
the rules above do not — they exist so the browser can stay same-origin and ask
one question per screen:

```
GET    /books/<book>/ui/plotlines    filtered, name-ordered, paginated table
GET    /books/<book>/ui/issues       the book's problems, grouped for reading
POST   /books/<book>/ui/plotline-preview   judge a candidate thread; writes nothing
GET    /books/<book>/ui/ticks        what the calendar calls these ticks (label + components)
POST   /books/<book>/ui/dates        which ticks these dates name; writes nothing
GET    /books/<book>/ui/entities     type-ahead over referenceable Akasha articles
GET    /books/<book>/ui/entity/<db>/<collection>/<id>   read one article
```

`…/ui/ticks` and `…/ui/dates` are inverses, and between them they are the whole
reason the browser needs no calendar arithmetic of its own.

`…/ui/issues` and `…/validate` answer the same question for different readers.
`/validate` is the machine's answer: ids, one list per category, the first
ordering violation on each thread. `…/ui/issues` is the writer's: the same rules
run thread by thread and folded into one list, so a problem two threads can see
is one entry naming both, phrased in the same words the plotline view uses and
grouped by kind. See [the report](#the-books-report).

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

**Joining partway down.** Not every thread catches the trunk at its first scene
— one that has been away comes back to a story already under way. Add
`continues_into_at` to say *where* it joins, and everything before that scene is not
inherited:

```
trunk         [meet-at-emberport, the-vigil, the-coronation]
late-arrival  [rides-hard]         continues_into: trunk, continues_into_at: the-vigil
                                   effective: rides-hard, the-vigil, the-coronation
```

Leave it out and the thread joins at the head, exactly as before. The scene is
named by id, so a trunk gaining a scene above the junction doesn't quietly move
it, and it may be any scene on the trunk's *resolved* path — including one the
trunk itself inherits.

The chain rules are hard: the target must exist (`400`), `continues_into_at` must be
a scene on its resolved path and needs a target to qualify (`400`), and the
chain must not loop (`422 PLOTLINE_CYCLE`). If the trunk later drops the scene a
thread joined at, that thread's `status.continuation` reports it as
`anchor_missing` — the *anchor* being the scene a join points at — rather than
guessing a new junction, which would either hand back the trunk's opening or
lose a scene.

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
  "goals": ["seal-delivered", "crown-reached"],   // stored: goal ids
  "goal_refs": [                               // ... and what they are called
    {"id": "seal-delivered", "title": "Deliver the Ember Seal", "achieved": true},
    {"id": "crown-reached", "title": "Reach the coronation alive", "achieved": true}
  ],
  "events": ["aldric-departs"],                // stored: this thread's own segment
  "continues_into": "trunk",                   // ... then it joins the shared ending
  "continues_into_at": null,                        // ... at its first scene (a scene id joins later)
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

### Goals

A goal is what a thread is *for*. It used to be a word typed on a plotline;
it is a record now, so two threads pursuing the same thing point at the same
object, a goal can rest on another, and the book can be asked whether it
actually delivers what it set out to.

```bash
curl -s -b /tmp/c -X POST localhost:5002/timeline/books/ember-pact/goals/charter-sealed \
  -H 'Content-Type: application/json' -d '{
    "title": "See the Seal pressed to the charter",
    "depends_on": ["seal-delivered", "traitor-exposed"],
    "achieved_at": "the-coronation"
  }'
```

Two fields carry the weight. **`depends_on`** names the goals that must be met
first, which is what makes goals a graph instead of a list of labels.
**`achieved_at`** names the scene that delivers this one — the single point where
a goal touches the timeline, and the reason chronos can say anything about it
beyond "you wrote this down". Both are optional-ish: a goal with no dependencies
rests on nothing, and a goal with no scene yet is simply one you have not written
the payoff for.

Everything else comes back computed, so one read draws the whole picture:

```jsonc
{
  "kind": "goal",
  "id": "charter-sealed",
  "name": "See the Seal pressed to the charter",
  "depends_on": ["seal-delivered", "traitor-exposed"],
  "dependencies": [ {"id": "seal-delivered", "title": "…", "achieved": true}, … ],
  "required_by": [],                       // what would be stranded without it
  "plotlines": [ {"id": "trunk", "title": "The Road to the Crown"} ],
  "achieved_at": "the-coronation",
  "achieved_scene": {"id": "the-coronation", "title": "The Coronation", "when": "…"},
  "depth": 1,                              // how far down the graph, for the diagram
  "status": {"state": "achieved", "findings": []}
}
```

**What is refused.** A dependency or an achieving scene that is not in this book
(`400 INVALID_GOAL`), a dependency chain that loops (`422 GOAL_CYCLE`), and a
thread naming a goal the book does not have (`400 INVALID_PLOTLINE`). Deleting a
goal that threads serve or goals rest on is `409 GOAL_IN_USE` and names them;
`?detach=true` unpicks those references first. So is deleting the scene a goal is
achieved at — `?detach=true` clears the anchor instead.

**What is reported.** Two contradictions: a goal achieved at a scene no thread
pursuing it ever passes through, and a goal achieved *before* something it
depends on. Both count towards the book's `status`, like any other conflict.
Everything else is a note — nobody pursuing it yet, no scene yet, a prerequisite
not yet placed — because a book three chapters in has plenty of those and
nothing wrong with it.

A thread may serve **no** goals at all. That is a note too: you are allowed to
draft a thread before you know what it is for.

### Goals in the UI

`#/<book>/~goals`, or the **Goals** button on the book page. The dependency
diagram is drawn top-down — a goal sits below everything it rests on, so reading
downward is reading the order things have to happen in — over a card per goal
saying what rests on it, which threads pursue it, where it lands, and what is
wrong. Selecting one is a URL (`#/<book>/~goals/<goal>`), so a particular goal is
a link. The plotline editor picks goals from this list rather than taking free
text, and can write a new one without leaving the thread you were editing.

**Reading a goal without leaving.** A goal chip — on a thread, in the plotline
table, in the report, on the story map — opens the goal in the **peek panel**
beside what you were reading, the same slot a referenced article or a scene from
another thread opens in. The chips *inside* the panel open the goals they name
in the same slot, so following a chain of prerequisites never navigates; the
`See in Goals →` link at the foot is the one deliberate way out, to the diagram
the panel cannot draw. Losing your place in a thread — or a filter, a selection,
a scroll position — to find out what a goal is was a steep price for an answer
that fits in a panel.

**Where the goals are.** A goal touches the timeline at exactly one point: the
scene that delivers it. So it draws as one mark, on that scene:

- **On a thread's timeline**, the delivering scene's rail dot is ringed and its
  row carries a goal chip.
- **On the story map**, the same — and because the map puts threads on one axis
  and time on the other, a goal lands in the column of whichever thread owns the
  scene. That is how you see a goal one thread pursues being paid off by
  another. A goal landing inside a folded run is marked on the band standing in
  for it, rather than disappearing with the rows the fold hid.
- **On the dependency diagram**, each goal box carries the date under the scene
  it lands on. The diagram is laid out by dependency, not by time, so a
  prerequisite dated *later* than the goal below it is a story that cannot
  happen — visible at a glance, and reported as `GOAL_OUT_OF_ORDER` besides.

Goals that are *not* on the graph you are looking at — no scene named yet, or a
scene on a thread this view is not showing — are named in a strip above it, each
saying which. A thread pursuing four goals and marking one would otherwise read
as a thread with one goal.

Two controls keep a dense book readable. A scene that delivers more than a
couple of goals shows the first few and folds the rest behind **+N more**, which
opens them in place — three on a thread, two on a map row, where space is
tighter. And the story map has a **Hide goals** switch: marks answer "where does
this book pay off?", which is one of the questions a map is read for and not the
only one, so following how threads weave is a click away from an uncluttered
drawing. Switched off, the marks are not merely hidden — nothing is placed, and
the rows are the height they were before goals existed.

**Goals are calendar-aware**, in the only way a goal can be: it has no date of
its own and borrows the one belonging to the scene that delivers it. Every
surface that dates a goal reads it through the book's chosen reckoning — the
goals page and the plotline table have the calendar switcher for that — and no
date is ever computed in the browser.

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

Now, the calendar. Any of:

- **No calendar.** Ticks are bare integers; a scene at tick `240` reads back as
  `240`. Pick a scale and stay consistent.
- **From your library.** One of the calendars you keep under **Calendars** on
  the shelf. If the library is empty, **＋ New calendar** builds one without
  leaving the form — into the library, because that is where every calendar
  lives. A book *names* a calendar; it cannot describe one of its own, and the
  API refuses a book body that carries a descriptor (`400 INVALID_BOOK`).

  A calendar itself is a base unit plus the cycles that nest over it, smallest
  first, and an optional era. As you build it the form reads it back in plain
  language — *"Ticks are hours: 24 hours to a day, 30 days to a month, 12 months
  to a year."* — so the thing you are committing to is legible before you commit
  to it. Presets cover the common shapes.

**+ Add another calendar** attaches a second reckoning over the same scenes, and
a switcher appears above the book to read through either. Each extra one gets a
name, an id, and optionally the span of ticks its culture kept it for — so an
elvish count that ends when the elves do stops dating the scenes after it, rather
than inventing years nobody counted.

That matters because the calendar decides what a tick *means* everywhere
downstream — what the timeline rail groups by, what the scene form reads back as
you type.

**Changing it later.** The **✎** beside a book's title on its plotline table
reopens the same form to rename the book, edit its overview or swap its calendar.
This is safe by construction rather than by care: ticks are canonical integers
and a calendar only translates them, so a swap re-labels the book without moving
a single scene, and no conflict, ordering or convergence verdict can change as a
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

### The calendar library

**Calendars** on the shelf opens a library of named reckonings — build one once
and attach it to any book. A calendar's identity is `(owner, id)`, not the slug
alone, and that is deliberate: names like *imperial*, *lunar* and *elvish* are
generic enough that two writers will independently reach for the same one. A
single global namespace would let whoever registered the word first own it for
everybody, and would tell the second writer that a calendar they cannot read
exists. So two libraries may each hold an `imperial`; shared calendars are shown
owner-qualified (`mara/imperial`) beside your own.

**Attaching copies.** A book takes its own copy of the descriptor rather than
pointing at the library record. Four things follow, and they are the reason for
the choice:

- Formatting a tick stays pure and I/O-free, so `GET /books` never becomes one
  query per book.
- Anyone who can read a book can read its **dates** — the labels are the book's
  own bytes. No grant on the library entry is needed, or offered.
- Editing a library calendar never silently re-dates somebody's finished story.
- Deleting one leaves every book that used it working; only the provenance
  pointer goes dangling, the same posture Chronos takes toward a deleted Akasha
  article.

What copying gives up is automatic propagation, and `source` — an
owner-qualified `{owner, calendar, rev}` — is what buys it back: a book can be
offered an explicit *"the library version changed — update?"*, previewable, and
never applied behind the writer's back.

**Sharing** a calendar (**⇥** on its card) grants another writer read, or edit.
It then appears in their library next to any calendar of their own that happens
to share its name — two distinct records, told apart by owner.

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
  here would be a lie. Each expanded scene says which it is (`owned`). **Joins
  at** beside the continuation picks the scene where the two threads meet, and
  the greyed-out list shortens to what is actually inherited.

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

### The book's report

**Report** in the book's header — and the **conflicted** pill on its card, which
is a link now — opens `#/<book>/~issues`: everything wrong across every plotline
in the book, on one page.

It exists because the marks were only ever per thread. A book that said
*conflicted* had nowhere to click through to, a writer with six threads had to
open all six to find out which were broken, and a contradiction between two of
them showed up twice with nothing to say it was one problem.

Four things it does that a per-thread view cannot:

- **One problem, once.** A conflict reported on both its scenes and on every
  thread either scene sits on becomes a single entry that *names* those threads.
  The number a thread contributes here is the number its row in the table
  already prints — held to it by a test, because the two are computed
  differently and a writer sees them on adjacent screens.
- **Grouped by kind**, in a fixed order, so the page answers "what sorts of
  thing are wrong" before it answers "where". The headings come from the server
  along with the wording, for the same reason the per-scene findings do: one
  vocabulary, so the report and the timeline cannot end up calling the same rule
  two different things.
- **Problems and notes are separated.** *Problems* are the contradictions —
  exactly what a book's `status` is computed from, so a book this page calls
  conflicted is a book whose card says conflicted. *Worth knowing* holds the
  rest: a scene still waiting for a time is a draft state, not a fault, and
  counting it as one would leave every book in progress red.
- **Things no thread can carry** get said at last: a book with no ending
  designated, a thread that stops short of it, a thread with no scenes, a
  continuation chain that cannot be followed — and any scene written but never
  threaded, which every per-thread pass is blind to by construction.

Each entry names the scene it is about (findings are phrased from a scene's
point of view — *"this scene has not ended when…"* — and only read correctly
beside it) and goes there: to that scene on that thread
(`#/<book>/<plotline>/at/<event>`, which scrolls to it and flashes it), or to a
peek card for the scene at the other end of the problem, which often lives on a
thread you were not looking at. The people and places a message names are chips
beside it, so you can open the article and check what the message claims.

Under the entries, **By plotline** — every thread with its share of the
problems, most first, and clicking one narrows the report to it. That number is
deliberately *not* the plotline table's **Health** column: Health counts
contradictions among the scenes on a thread, while this also counts the
whole-thread verdicts (never reaching the ending, no scenes at all) that the
table has never shown. Two questions, so the column is labelled for the one it
answers. **Worth knowing** folds away, and stays folded, for a book being
drafted with more undated scenes than problems.

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
> `GET /activity` (design §7.5) is not implemented. `GET /collaborators` now is
> — the browser needed a way to ask who could already see a book.

### Grants and the shared store

Chronos and Akasha share one `_auth` store. Grants are namespaced by a
`resource_type` discriminator (`"book"` vs `"database"`) that must match
**exactly**, so a book named `x` never confers access to a Akasha
database named `x`. Grants written before this field are read as `"database"`.

---

## Seed a demo story

`docker/seed_demo.py` builds a book ("The Ember Pact") over the real HTTP APIs —
entities, two calendars, six events, four plotlines, a terminus — and
demonstrates both rule classes.

The two calendars are the point of the switcher: the Imperial Reckoning, whose
months are a fixed 30 days, and Earth, anchored so that tick `48` — the Harbor
Exchange — is `February 29, 2024`. Reading the book through either one leaves
every tick, every ordering and every verdict exactly where it was.

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
| `timeline`, `conflicts`, `ordering`, `book_rules`, `reports`, `plotline_health`, `book_health`, `browsing`, `calendar`, `validation`, `models` | **pure logic** — no I/O, no Flask; where correctness lives |
| `documents.ScopedDocuments` | the composite key, `_rev` concurrency and author stamp both stores share |
| `store.StoryStore` | persistence seam for books/plotlines/events, scoped to a book |
| `store.CalendarStore` | persistence seam for the calendar library, scoped to an owner |
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
