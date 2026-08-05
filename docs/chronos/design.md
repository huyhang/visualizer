# Design: Chronos — a plotline & timeline API for fiction writers

This document is the proposed design for **Chronos**, a new API service that lets
fiction writers model the *plotlines* of their work: who did what, where, and
when, and how those threads weave, split, and finally come together. It is a
sibling to the existing `akasha` and deliberately reuses its
conventions. Nothing here is implemented yet; this doc is the thing to agree on
before code exists.

Where this doc and the eventual code disagree, the code wins — but the
**principles** below are non-negotiable, because they are what make the service
testable.

---

## 1. Goals

- Model the four domain concepts precisely: **Event**, **Plotline**, **Book**,
  and the special **Terminus** event.
- Enforce the domain's hard rules as **invariants**, checked at write time and
  re-checkable on demand:
  - a character cannot be in two places at overlapping times (*temporal
    conflict*);
  - within a plotline, each event ends strictly before the next begins
    (*ordering*);
  - every plotline in a book converges into one shared final event (the
    *terminus*).
- Reference characters, items, and locations as **entities that must already
  exist in Akasha** — Chronos never invents them.
- Be **easy to test**: all domain logic is pure and DB-free; every I/O boundary
  is an injected seam, exactly as `DocumentStore`/`AuthStore` are today.

### Non-goals (for this design)

- No writing/prose editor UI. Chronos is an HTTP/JSON API first; a UI can come
  later on top of it, the way the editor was layered onto `akasha`.
- No real-world calendar semantics. Time is abstract (see §4).
- No automatic *resolution* of conflicts — Chronos **detects and reports**;
  the writer decides what to change.

> **Update (as built).** The "UI comes later" non-goal has partly happened: a
> **read-only** plotline visualiser now ships with the service (book → filtered
> plotline table → a plotline's events as cards on a vertical timeline, with the
> referenced Akasha articles shown inline). It is still read-only — all writing
> goes through the JSON API. And rather than a second port, the two services are
> served behind **one origin** in production: a single gunicorn co-mounts them
> with Werkzeug's `DispatcherMiddleware` (`visualizer.wsgi:application`), akasha
> at `/` and chronos at `/timeline` — one reverse-proxy rule, one cookie, no
> CORS. See the root [README](../../README.md#services) and `visualizer/gateway.py`.

---

## 2. Principles (consistent with the existing codebase)

These mirror `docs/akasha/editor-design.md` on purpose — a reader who knows
`akasha` should feel at home.

- **Inversion of control.** Every boundary — persistence, the Akasha entity
  lookup, the clock — is an interface injected into an application factory
  (`create_app(...)`). Production wires real adapters; tests wire fakes. No
  module reaches for the environment, the wall clock, or a live socket on its
  own.
- **Pure domain logic.** The interesting rules (overlap, ordering, convergence)
  live in **DB-free, Flask-free functions** that take plain data and return
  plain data — the `authz.py` / `validation.py` pattern. They are where the
  correctness lives, and they are unit-testable in isolation with zero mocks.
- **Small, modular units.** Routes are thin; services orchestrate; stores do
  I/O; pure modules decide. Each function does one thing and is short enough to
  read at a glance.
- **Reuse the existing auth + grant model.** Chronos authenticates the same way
  `akasha` does and expresses access with the same allow-only,
  most-specific-wins grants (`authz.is_allowed`), just over a
  `book → plotline → event` hierarchy instead of `database → collection →
  document`.
- **Optimistic concurrency, reused.** Books, plotlines, and events all carry a
  `_rev` and take an `If-Match` precondition, identical to documents today.

---

## 3. Domain model

```
Book
 ├── has many ──► Plotline ──── ordered list of ──► Event (shared across plotlines)
 │                   │                                 │
 │                   ├── set of Goals                  ├── characters: [EntityRef]
 │                   └── ends at ──────────────────►   ├── items:      [EntityRef]
 │                                                      ├── location:    EntityRef
 └── designates one Terminus (an Event) ───────────►   ├── start_tick, end_tick
    all plotlines must end at it                        └── description (long text)
```

### 3.1 EntityRef — the link to Akasha

A character, item, or location is **not** stored in Chronos. It is a *reference*
to a document that must already exist in `akasha`. A reference reuses
that service's addressing verbatim:

```jsonc
{ "database": "middle-earth", "collection": "characters", "id": "aragorn" }
```

Chronos validates every reference on write through the **`EntityGate`** seam
(§6). A reference to a missing (or unreadable) document is rejected — this is the
"MUST exist in the document database" rule, enforced in one place.

### 3.2 Event

The atom of the model. An Event is a claim that *these characters, holding these
items, did the following at this location, over this timeframe*.

| Field         | Type                 | Notes                                          |
| ------------- | -------------------- | ---------------------------------------------- |
| `id`          | slug                 | unique within its book                         |
| `title`       | string               | optional short display name; defaults to `id`  |
| `characters`  | set of `EntityRef`   | each must exist; may be empty                   |
| `items`       | set of `EntityRef`   | each must exist; may be empty                   |
| `location`    | one `EntityRef`      | must exist; required                            |
| `start_tick`  | integer              | see §4; `start_tick <= end_tick`                |
| `end_tick`    | integer              | see §4                                          |
| `description` | string (long)        | free prose; unbounded                          |

Events are **scoped to a book**. Sharing across plotlines happens *within* a
book (a plotline references events by id); events are not shared across books.

### 3.3 Plotline

An **ordered list of event ids**, plus a set of **goals**.

| Field            | Type              | Notes                                                    |
| ---------------- | ----------------- | -------------------------------------------------------- |
| `id`             | slug              | unique within its book                                    |
| `title`          | string            | optional short display name; defaults to `id`             |
| `events`         | ordered `[id]`    | this plotline's **own segment**; order is meaningful      |
| `goals`          | set of strings    | required to be non-empty                                  |
| `continues_into` | plotline `id`     | optional; the thread carries on into that plotline        |

The order is the contract: if event **A** precedes event **B** in the list,
then **A must end strictly before B begins** (§5.2). Two plotlines may list the
same event (**convergence**/**divergence**); the shared event is one object, so
edits to it are seen by every plotline that uses it.

**Continuations — writing a shared ending once.** Because every plotline must
reach the terminus, threads that merge would otherwise repeat the whole shared
tail. That is not just verbose: inserting one scene into the ending means
editing *every* thread, and a thread you forget silently drifts — exactly the
class of continuity bug Chronos exists to catch.

So a plotline may name a `continues_into` target. Its **effective path** is its
own events followed by the effective path of that target, transitively:

```
trunk             [meet-at-emberport, the-coronation]
knights-road      [aldric-departs]    → continues_into: trunk
spys-shadow       [lyra-infiltrates]  → continues_into: trunk
```

Every rule — ordering (§5.2), convergence (§5.3), the story graph (§7.4) — runs
on the **effective** path, so a thread stored as a segment is indistinguishable
from one written out in full. Ordering therefore also checks the *junction*: the
segment's last event must end before the continuation's first event begins. Reads
return both: `events` (what is stored, and what you send back) and
`effective_events` (the resolved path).

Two structural rules, both **hard** (unlike the story-logic ones), because an
unresolvable chain has no effective path at all and would break every later read:

- `continues_into` must name a plotline in the same book → `400 INVALID_PLOTLINE`
- the chain must not loop → `422 PLOTLINE_CYCLE`
- deleting a plotline others continue into → `409 PLOTLINE_IN_USE`, unless
  `?inline=true` absorbs it into each dependent first (the same shape as
  `EVENT_IN_USE` / `?detach=true` for events, §7.2)

The inverse operation is **`POST …/plotlines/<id>/inline`**: it copies the
resolved path into the thread's own `events` and clears `continues_into`, so the
thread keeps its exact story but stops depending on another plotline. It is a
no-op when there is nothing to absorb, and refuses on a broken chain rather than
inlining a partial path.

Note the acyclicity argument in §5.3 covers *event* edges, which are ordered by
tick; plotline links are a separate graph and need this explicit guard. The
resolver is cycle-tolerant by design — it reports a loop rather than recursing —
so a read never hangs on data that is already bad.

### 3.4 Book & Terminus

A **Book** is a collection of plotlines with one designated **Terminus**.

| Field            | Type            | Notes                                            |
| ---------------- | --------------- | ------------------------------------------------ |
| `id`             | slug            | unique                                           |
| `title`          | string          | display name                                     |
| `plotlines`      | set of `[id]`   | the plotlines belonging to this book             |
| `terminus`       | event `id`      | the single event every plotline must end at      |
| `calendar`       | descriptor      | optional; selects the `TimeCodec` (§4.1)         |

The **Terminus** is just an Event that is designated as the book's convergence
point. The book-level invariant (§5.3) is: **every plotline's last event is the
terminus.** Convergence *elsewhere* and divergence are allowed and surfaced
descriptively (§7.4) — only convergence *at the terminus* is required.

---

## 4. Time model — abstract integer ticks

Every Event has a **signed integer** **`start_tick`** and **`end_tick`** on a
per-book timeline, with `start_tick <= end_tick`. A tick is an abstract,
monotonically increasing unit — the story decides what it means (a minute, a
day, an age). Ticks are *signed* so pre-epoch events (flashbacks, ancient
history, "before the Founding") are simply negative — no special case in the
math.

Why integers rather than dates:

- **Comparison and overlap are trivial and exact** — no timezone, calendar, or
  BCE/era edge cases, which matters for fiction set outside the real world.
- **It keeps the pure logic pure.** Overlap and ordering become integer
  arithmetic that unit-tests with literal numbers.
- A story can map ticks to human labels for display without Chronos caring.

Intervals are treated as **half-open `[start_tick, end_tick)`**. This makes
"one event ends exactly as the next begins" *not* an overlap — which is exactly
the boundary the plotline ordering rule wants (end **strictly before** start).

### 4.2 Unscheduled scenes and inferred windows

A writer sketching a thread usually knows the *order* of scenes long before
their *timing*. Requiring exact ticks up front would make Chronos block drafting
— the one thing §8.1 promises it never does. So both ticks are **optional**:
give both or neither (a half-known timeframe is rejected, `400`, because it
would multiply the cases every rule handles for little gain).

An **unscheduled** scene has no interval, so:

- it is **skipped by temporal-conflict detection** — it cannot contradict what
  has no time;
- it is **skipped by ordering** — the scheduled scenes on either side of it are
  still compared, so a gap hides nothing;
- convergence is unaffected (that rule is about ids, not times).

**Unscheduled is a draft state, not a fault.** `/validate` lists these scenes
under `unscheduled`, and they do **not** make a book `conflicted` — a
permanently-red book would train the writer to ignore the report.

**Inferred windows.** Because a plotline already encodes order, the *scheduled*
scenes around an undated one constrain it: it must start after its nearest
scheduled predecessor ends and end before its nearest scheduled successor
begins. Constraints from every thread the scene appears in compound (latest
lower bound, earliest upper bound). `scheduling.py` computes this purely; the
result rides along on the event and in `/validate`.

That turns "I haven't decided" into guidance, and it catches something no other
rule can: when the neighbours leave **no room at all** (`earliest > latest`) the
scene has no valid time. That *is* a contradiction, so an
`IMPOSSIBLE_WINDOW` does make the book `conflicted`. Note it is genuinely
additive — the neighbours may sit in *different* plotlines, in which case no
single thread is out of order and the ordering check sees nothing wrong.

### 4.1 Translating ticks — a pure `TimeCodec` at the edges

Writers think in "Year 3, Month 4, Day 12," not `10567`. The mechanism that
bridges the two keeps ticks **canonical** and confines translation to the API
boundary: **parse on the way in, format on the way out.** Storage and every
invariant/graph module see only `int` — they never know a calendar exists.

Each **Book** carries a small `calendar` descriptor that selects a **`TimeCodec`**
— a pure strategy object whose two methods round-trip:

```python
class TimeCodec(Protocol):
    def format(self, tick: int) -> str: ...   # 10567 -> "Year 2, Month 3, Day 21, 07:00 AF"
    def parse(self, label: str) -> int: ...    # inverse; raises InvalidTimeframe on garbage
    # invariant, and the key property test: parse(format(t)) == t
```

Three implementations satisfy the same interface (strategy / IoC); the book's
descriptor picks one via a pure `codec_for(book)` factory:

- **`IdentityCodec` (default).** No calendar defined → ticks display as raw
  integers. The feature is opt-in; the simple case stays simple.
- **`MixedRadixCodec` (fictional calendars).** The descriptor is a base unit
  plus nested cycles, so *any* invented calendar works (13-month years,
  10-day weeks):

  ```jsonc
  { "base_unit": "hour",
    "cycles": [ {"name": "day",   "size": 24},    // 24 hours / day
                {"name": "month", "size": 30},    // 30 days / month
                {"name": "year",  "size": 12} ],  // 12 months / year
    "epoch_label": "AF" }
  ```

  `format` is repeated `divmod` (mixed-radix decomposition); `parse` is the
  inverse composition.
- **`GregorianCodec` (optional).** For real-world settings, back the same
  interface with `datetime`.

**Where it plugs in** — only the request/response edge of the service layer:

- **Input:** a route may accept raw `start_tick`/`end_tick` *or* `start`/`end`
  label strings; the service calls `codec_for(book).parse(...)` **first**,
  before any validation or storage. Only ticks are persisted.
- **Output:** event reads and the `/validate` / `/graph` responses may include a
  computed `start_label`/`end_label` alongside the raw ticks, formatted at
  serialization time. The book also exposes its `calendar`, so a client can
  format on its own.

Because `TimeCodec` is pure and constructed from plain book data, it unit-tests
in isolation (a literal descriptor + the `parse(format(t)) == t` round-trip),
and it never leaks into the invariant logic.

**Two notes.** (1) The base unit is a one-time choice — changing it later means
rescaling stored ticks — so pick a *fine* base unit (e.g. minutes) up front;
integer ticks are cheap. (2) Optional **anchors** (naming specific ticks, e.g.
`tick 0 = "The Sundering"`) let a helper render relative phrasing ("14 days
before The Sundering"); it's a separable layer over the same tick line, and
several calendars can map that one canonical line for different in-world
reckonings.

---

## 5. The invariants (the pure heart of the service)

Each invariant is a **pure function** in its own module. Services call these
after loading the minimum data the check needs. Because the functions take plain
data, the tricky cases are unit tests, not integration tests.

### 5.1 Temporal conflict — `conflicts.py`

> A character cannot be in two events at **different locations** with
> **overlapping** timeframes.

Two intervals overlap iff `start_a < end_b and start_b < end_a` (half-open).
Same-location overlaps are allowed (two sub-scenes at one place); only
*different*-location overlaps for a *shared* character are conflicts.

```python
def find_temporal_conflicts(candidate: Event, others: Iterable[Event]) -> list[Conflict]:
    """Pure: return every ``other`` that puts one of ``candidate``'s characters
    in a different location during an overlapping timeframe."""
```

- **Input** is just the candidate event plus the other events that share at
  least one of its characters — the service fetches that set through the store
  seam; the function itself touches no DB.
- **Enforced** whenever an event's characters, location, or timeframe change
  (create/update). Also available book-wide via the validate endpoint (§7.3).
- Complexity is a non-issue: a character appears in a handful of events, so the
  candidate is compared against a small set.

### 5.2 Plotline ordering — `ordering.py`

> If A is ordered before B in a plotline, A must end before B begins.

```python
def validate_order(events_in_order: list[Event]) -> Violation | None:
    """Pure: return the first adjacent pair where end(prev) > start(next),
    or None if the whole list is non-overlappingly ordered."""
```

Consistent with the half-open interval model (§4), *touching* is allowed:
`end(prev) == start(next)` is fine (prev no longer occupies `end`, next begins
there), and only `end(prev) > start(next)` is a violation. Checking **adjacent**
pairs is sufficient for the full pairwise rule: if `end(Aᵢ) <= start(Aᵢ₊₁)` for
every consecutive pair, then because `start ≤ end` within each event, starts are
non-decreasing and `end(Aᵢ) <= start(Aⱼ)` for all `i < j`. So an O(n) scan proves
the O(n²) property — a small, testable fact worth stating.

- **Enforced** on plotline create/update (reorder, add, remove events).

### 5.3 Convergence & the terminus — `book_rules.py`

> All plotlines in a book converge into a single Terminus event.

```python
def validate_convergence(plotlines: list[Plotline], terminus_id: str) -> ConvergenceReport:
    """Pure: check that every plotline is non-empty and its LAST event is
    ``terminus_id``. Report each plotline that fails, and why."""
```

- **Enforced** when a book's terminus is set, when a plotline is added to a
  book, and when a plotline is reordered such that its last event changes.
- **Acyclicity is free.** Because every plotline edge goes from a lower tick to
  a strictly higher one (§5.2), the union of all plotline orderings — the story
  graph — can never contain a cycle. Time only moves forward, so the graph is a
  DAG by construction; no separate cycle check is needed.

### Where each invariant is enforced

| Write                              | Temporal (5.1) | Ordering (5.2) | Convergence (5.3) | EntityRef exists |
| ---------------------------------- | :------------: | :------------: | :---------------: | :--------------: |
| Create / update **Event**          |       ✓        |      re-check* |         —         |        ✓         |
| Create / update **Plotline**       |       —        |       ✓        |         ✓         |        —         |
| Set **Terminus** / add plotline    |       —        |       —        |         ✓         |        —         |

\* Editing an event's timeframe can break the ordering of any plotline that
contains it, so those plotlines are re-evaluated as part of the event write.

A ✓ marks what is **evaluated** on that write — but evaluation has two outcomes,
and the split is fixed (it does **not** depend on whether a book has
collaborators):

- **Referential** (`EntityRef exists`, plus `start ≤ end` and non-empty
  plotline/goals from §9) — **hard**: the write is rejected.
- **Story-logic** (temporal, ordering, convergence) — **soft**: the write
  succeeds and the finding is recorded in the book's `status` and `/validate`
  (§8.1). It never blocks a save.

---

## 6. Architecture — layers and seams

Four layers, dependencies pointing inward. Only the outermost touches Flask;
only the store/gate touch a database or the network.

```
 ┌──────────────────────────────────────────────────────────────┐
 │  Routes  (app.py)          thin Flask; auth + HTTP only        │
 │    └─ inject ─► Services   orchestration + invariant calls     │
 │                   ├─ inject ─► StoryStore  (seam) ─► DB         │
 │                   └─ inject ─► EntityGate  (seam) ─► doc-server │
 │                                                                 │
 │  Pure logic  (conflicts / ordering / book_rules / validation)  │
 │    ── called by Services; depend on nothing ──                 │
 └──────────────────────────────────────────────────────────────┘
```

### 6.1 Seam: `StoryStore`

The single seam between Chronos and its own persistence — the `DocumentStore`
analogue. It is **plain CRUD plus two targeted queries** the invariants need;
it holds **no domain rules** (those are pure functions the services call).

```python
class StoryStore(Protocol):
    # Books / plotlines / events: create, get, update (OCC via _rev), delete, list.
    def create_event(self, book_id, event_id, event, *, author) -> dict: ...
    def get_event(self, book_id, event_id) -> dict: ...
    # ... symmetric CRUD for plotlines and books ...

    # Targeted reads that keep invariant checks cheap and DB-agnostic:
    def events_involving(self, book_id, character_refs) -> list[dict]:
        """Events in the book that reference any of these characters (for §5.1)."""
    def get_events(self, book_id, event_ids) -> list[dict]:
        """Fetch an ordered plotline's events in one call (for §5.2)."""
```

Everything above the seam is written against this interface, so the persistence
choice (§9) never leaks into the services or the pure logic. Tests inject an
in-memory fake `StoryStore`.

### 6.2 Seam: `EntityGate`

The boundary to `akasha` — how Chronos honors "entities must exist."

```python
class EntityGate(Protocol):
    def exists(self, ref: EntityRef) -> bool: ...
    def exist(self, refs: Iterable[EntityRef]) -> list[EntityRef]:
        """Return the subset that do NOT exist (empty == all good)."""
```

Two adapters, same interface:

- **In-process** (recommended when Chronos and `akasha` share a Mongo):
  wrap a `DocumentStore` and call `.get(...)`. No network, and tests can inject
  the very same fake store.
- **HTTP** (when they're separate services): call `GET
  /databases/<db>/collections/<col>/documents/<id>`, authenticating as the
  caller so the document's read grants are honored — a missing *or unreadable*
  entity is treated the same: "does not exist for you."

Because it's a seam, tests inject a fake that answers from a set literal — no
Akasha needed to test Chronos's rules.

### 6.3 Services

Thin orchestrators, one per aggregate, each injected with the two seams. A
representative flow (create event) shows the shape — load, validate purely,
persist:

```python
class EventService:
    def __init__(self, store: StoryStore, entities: EntityGate): ...

    def create(self, book_id, event_id, payload, *, author) -> dict:
        event = validate_event_payload(payload)                 # pure (§ validation)
        missing = self.entities.exist(event.all_refs())         # EntityGate seam
        if missing: raise EntityNotFound(missing)
        neighbours = self.store.events_involving(               # StoryStore seam
            book_id, event.character_refs())
        conflicts = find_temporal_conflicts(event, neighbours)  # pure (§5.1)
        if conflicts: raise TemporalConflict(conflicts)
        return self.store.create_event(book_id, event_id, event, author=author)
```

Every method reads like this: a few named steps, each either a pure check or a
seam call. Nothing here knows whether the store is Mongo or a graph, or whether
the entity check is a function call or an HTTP round-trip.

### 6.4 Routes & the app factory

`create_app(story_store, entity_gate, auth_store, secret_key, ...)` mirrors the
Akasha factory: injected dependencies, focused
`_register_*_routes(...)` helpers so `app.py` stays a thin orchestrator, and a
single `@app.errorhandler(ChronosError)` translating domain errors to JSON +
status (§10). Auth uses the existing Flask-Login + grant path, unchanged, over
the `book → plotline → event` scope.

---

## 7. API surface

REST, shaped like `akasha` so callers see one house style. All routes
are authenticated and grant-checked; writes accept an `If-Match` `_rev`
precondition and return an `ETag`.

### 7.1 Books

```
POST   /books/<book>                 create a book (creator becomes owner)
GET    /books/<book>                 read (title, plotline ids, terminus, status, rev)
PUT    /books/<book>                 update (title, terminus, plotline set)
DELETE /books/<book>                 delete
GET    /books                        list books the caller can read
POST   /books/<book>/terminus/<event>   designate the terminus (re-checks §5.3)
```

The read includes a computed `status: "consistent" | "conflicted"` — the
one-glance answer to "does my book currently satisfy the story-logic invariants?"
(the full breakdown is `/validate`). See §8 for how it is maintained.

### 7.2 Plotlines & Events (scoped to a book)

```
POST   /books/<book>/plotlines/<plotline>   create (goals + ordered events; §5.2, §5.3)
GET    /books/<book>/plotlines/<plotline>
PUT    /books/<book>/plotlines/<plotline>   replace (reorder / edit goals)
DELETE /books/<book>/plotlines/<plotline>

POST   /books/<book>/events/<event>         create (§5.1 + EntityRefs exist)
GET    /books/<book>/events/<event>
PUT    /books/<book>/events/<event>         update (§5.1 + re-check dependent plotlines)
DELETE /books/<book>/events/<event>[?detach=true]   block if referenced, unless detaching
```

**Deleting a referenced event.** Referential integrity is a *hard* rule (§8.1),
so a delete is **blocked by default** when any plotline still lists the event —
`409 EVENT_IN_USE`, whose body names the referencing plotlines (with titles) so
the writer knows what to detach. An opt-in **`?detach=true`** first removes the
event from every plotline that lists it, then deletes it — a single deliberate
action; cascade is never implicit. Detaching may change those plotlines'
ordering/convergence, but since those are soft (§8.1) it only updates their
`status`, never fails the delete. Deleting the book's **terminus** is always
blocked (even with `?detach=true`) — `409 TERMINUS_IN_USE`, "designate a new
terminus first" — because a book with no terminus violates the core invariant
(§5.3).

#### Plotline output — self-describing by design

`GET …/plotlines/<id>` returns the **stored record**, a **computed `status`**,
and a **`_links`** block so the response explains itself (see §7.6). It is lean
by default; `?expand=events` inlines event summaries (labels via §4.1, plus
`shared_with` / `is_convergence` / `is_terminus` markers).

```jsonc
GET /books/ember-pact/plotlines/knights-road          // 200, ETag: "3"
{
  "kind": "plotline",                                 // type discriminator
  "id": "knights-road",
  "book": "ember-pact",
  "goals": ["Deliver the Ember Seal", "Reach the coronation alive"],
  "events": ["aldric-departs", "meet-at-emberport", "the-coronation"],
  "rev": 3,

  "status": {                                          // computed, readOnly
    "ordering":         {"state": "ok"},
    "ends_at_terminus": {"state": "ok"},
    "span": {"start_tick": 0, "end_tick": 210,
             "start_label": "Year 1, Month 1, Day 1, 00:00 AF",
             "end_label":   "Year 1, Month 1, Day 9, 18:00 AF"}
    // when a rule fails, that verdict uses the shared "finding" shape:
    // "ordering": {"state":"conflicted", "code":"ORDERING_VIOLATION",
    //   "message":"'meet-at-emberport' ends after 'lyra-infiltrates' begins.",
    //   "evidence":{"before":"meet-at-emberport","after":"lyra-infiltrates",
    //               "reason":"end(72) !< start(0)"},
    //   "doc":"docs/chronos/design.md#52"}
  },

  "_links": {
    "self":     "/books/ember-pact/plotlines/knights-road",
    "book":     "/books/ember-pact",
    "expanded": "/books/ember-pact/plotlines/knights-road?expand=events",
    "validate": "/books/ember-pact/validate",
    "graph":    "/books/ember-pact/graph",
    "events":   ["/books/ember-pact/events/aldric-departs", "…"]
  },
  "_schema": "/openapi.json#/components/schemas/Plotline"
}
```

**Field reference**

| Field                     | Type                | Kind      | Meaning                                                        |
| ------------------------- | ------------------- | --------- | ------------------------------------------------------------- |
| `kind`                    | `"plotline"`        | stored    | type discriminator                                            |
| `id`                      | slug                | stored    | unique within the book                                        |
| `book`                    | slug                | stored    | owning book id                                                |
| `goals`                   | `[string]`          | stored    | non-empty set of goals (§3.3)                                 |
| `events`                  | ordered `[id]`      | stored    | the thread; **order is the contract** (§5.2)                  |
| `rev`                     | int                 | stored    | OCC counter; echo as `If-Match` on write                      |
| `status.ordering`         | verdict             | computed  | strictly ordered? (§5.2) — `{state, …}`                       |
| `status.ends_at_terminus` | verdict             | computed  | last event == book terminus? (§5.3)                           |
| `status.span`             | object              | computed  | tick range + labels (§4.1)                                    |
| `_links`                  | object              | computed  | next actions (self, book, expand, validate, graph, events)   |
| `_schema`                 | string              | computed  | JSON-Schema pointer for this shape                           |

Computed fields are **`readOnly`**: they are never accepted on `PUT`/`POST`.

### 7.3 On-demand validation

```
GET    /books/<book>/validate
```

Runs **all** invariants across the whole book and returns a structured report —
green when the book is internally consistent, otherwise a list of every
temporal conflict, out-of-order plotline, and non-converging plotline. This is
the writer's "is my story physically possible yet?" button and is a pure
aggregation over the same functions used at write time.

### 7.4 Convergence / divergence view

```
GET    /books/<book>/graph
```

Returns the story graph — events as nodes; "precedes" edges from consecutive
plotline members — annotated with **divergence** points (out-degree > 1: an
event with more than one distinct *successor*) and **convergence** points
(in-degree > 1: an event with more than one distinct *predecessor*), and
highlighting the terminus. Note two plotlines that share the same next event do
*not* form a divergence, and two that arrive from the same prior event do not
form a convergence — the split/merge is counted by distinct neighbors, not by
plotline count. Descriptive, not enforcing: useful for visualizing how threads
split and rejoin.

**Event neighborhood** — the same view focused on a single event, answering
"which plotlines converge into / diverge out of *this* event?":

```
GET /books/<book>/events/<event>/plotlines[?relation=converging|diverging|through]
```

It is the event-local slice of the story graph. Incoming edges grouped by
predecessor give **convergence**; outgoing edges grouped by successor give
**divergence**. The output is written to *read*, not just parse: every id
carries a `title`, times are codec-formatted (§4.1), and a one-word `role` plus
a prose `summary` say what is happening. All of it is computed in the presenter
(§6.4) over the same structural data — nothing extra is stored.

```jsonc
GET /books/ember-pact/events/meet-at-emberport/plotlines
{
  "event": { "id": "meet-at-emberport", "title": "The Harbor Exchange",
             "when": "Year 1, Month 1, Day 3 → Day 4 AF", "location": "Emberport" },
  "role": "convergence",                         // convergence | divergence |
                                                 // convergence+divergence | interior | origin | terminus
  "summary": "Two plotlines converge here — The Knight's Road (from “Aldric Departs”) and The Spy's Shadow (from “Lyra Infiltrates”) — then continue together to “The Coronation”.",
  "through": [ {"id": "knights-road", "title": "The Knight's Road"},
               {"id": "spys-shadow",  "title": "The Spy's Shadow"} ],
  "converging": {
    "is_convergence": true,                      // >1 distinct predecessor
    "summary": "2 threads arrive from 2 different events.",
    "incoming": [                                // sorted by predecessor start_tick
      { "from": {"id": "aldric-departs",   "title": "Aldric Departs",   "when": "Day 1"},
        "plotlines": [{"id": "knights-road", "title": "The Knight's Road"}] },
      { "from": {"id": "lyra-infiltrates", "title": "Lyra Infiltrates", "when": "Day 1–3"},
        "plotlines": [{"id": "spys-shadow", "title": "The Spy's Shadow"}] }
    ]
  },
  "diverging": {
    "is_divergence": false,                      // all threads share one successor
    "summary": "All threads continue together.",
    "outgoing": [
      { "to": {"id": "the-coronation", "title": "The Coronation", "when": "Day 9"},
        "plotlines": [ {"id": "knights-road", "title": "The Knight's Road"},
                       {"id": "spys-shadow",  "title": "The Spy's Shadow"} ] }
    ]
  },
  "is_terminus": false,
  "is_origin": false,
  "_links": { "self": "…/events/meet-at-emberport/plotlines",
              "event": "…/events/meet-at-emberport", "graph": "…/graph" }
}
```

Definitions (so the flags are unambiguous): **convergence at E** = E is entered
by more than one distinct predecessor edge; **divergence from E** = E is left
toward more than one distinct successor. `?relation=` returns just the matching
block. Computed from the same `DiGraph` the `book_rules` module already builds —
`in_edges(E)` / `out_edges(E)` grouped by the plotline id on each edge — so it
is pure, testable, and O(degree of E); no new machinery.

For terminals and CLI readers, an optional `Accept: text/plain` (or
`?format=text`) renders the same data as a branch/merge diagram:

```
The Harbor Exchange — convergence   (Year 1, Month 1, Day 3, Emberport)
  ← The Knight's Road   from “Aldric Departs”   (Day 1)
  ← The Spy's Shadow    from “Lyra Infiltrates” (Day 1–3)
  → both continue to “The Coronation”           (Day 9)
```

### 7.5 Collaborators (book owners only)

```
GET    /books/<book>/collaborators                    list collaborators + roles
PUT    /books/<book>/collaborators/<user>             invite / set a role
DELETE /books/<book>/collaborators/<user>             remove
GET    /books/<book>/activity                          recent changes, by author
```

These are authorized by the `share` permission (§8), which the creator holds at
book scope. They are thin wrappers over the existing grant store — inviting a
collaborator *is* adding a grant at `book`/`plotline` scope.

### 7.6 Making responses easy to understand (developer experience)

Responses are built to explain themselves, so an API consumer rarely needs to
guess:

- **Stored vs computed is unmistakable.** Editable fields sit at the top level;
  derived fields live under `status` / `_links` / `_schema` and are `readOnly`.
  A client can round-trip a `GET` into a `PUT` by sending back only the stored
  fields.
- **`_links` make the next call discoverable.** Bare ids (like `events`) are
  also surfaced as URLs, and options like `?expand=events`, `/validate`, and
  `/graph` are advertised — the API teaches itself from any response.
- **One "finding" vocabulary everywhere.** A failed `status` verdict, a
  `/validate` entry, and an error body (§10) share the same
  `{state|error, code, message, evidence, doc}` shape and the same `code`s.
  Learn it once; it reads the same across every endpoint. The `doc` pointer
  deep-links the concept back to this design.
- **A published, tested contract.** A hand-authored **OpenAPI 3 / JSON Schema**
  is served at **`/openapi.json`** with a single-file **Redoc** UI at
  **`/docs`** (no build toolchain — consistent with the vanilla-JS, LAN-only
  ethos). Every response's `_schema` points into it. A **contract test**
  validates real `create_app` responses against the published schema so the two
  can never drift. The scaffold lives at `docs/openapi.json` (Plotline schema
  first); see §11.
- **One source of shape.** A pure `presenters.py` (the `_to_public` analogue)
  is the single place each response dict is built, so the code, the schema, and
  the examples all trace to one definition and stay in lockstep.

---

## 8. Collaboration — many authors on one book

Collaboration changes three things. Nothing here alters the layering or the
seams — it changes *how* story-logic rules report and *who* may share.

### 8.1 Consistency: story-logic invariants are computed, not blocking

**Decision: the model is all-soft, always** — story-logic findings are computed
warnings for *every* book, solo or shared; there is no collaborator-based mode
switch. Collaboration is what makes this *necessary*, but it applies uniformly.

The story-logic invariants are **cross-document** — temporal conflict spans
events; convergence spans plotlines — and standalone `mongod` has **no
multi-document transactions**, so a check-then-write has a real time-of-check /
time-of-use race once two people write at once. Rather than fight that, split
the rules by what a *single* write can verify atomically:

- **Referential / structural** (event ids exist, plotline & goals non-empty,
  EntityRefs exist, `start ≤ end`) — single-document-checkable, so they are
  **hard** (`400`/`422`).
- **Story-logic** (temporal, ordering, convergence) — **the write always
  succeeds; the finding is recorded.** The book carries a computed `status`
  (§7.1) and `/validate` lists exactly what is wrong.

This is a feature, not a concession: a writer should not have a save rejected
because *someone else's* concurrent edit — or their own draft-in-progress —
created the conflict; they should see it and reconcile. It matches the design's
philosophy ("detect and report; the writer decides"), reads the same solo or
collaborative, and sidesteps the transaction gap entirely. The `status` /
`/validate` computation is a read-time snapshot, which suits this perfectly.

**If a rule ever needs to be hard-enforced instead**, the mechanism is already
in place without redesign: make the **Book the consistency boundary** — a
book-level `_rev` bumped on every structural write, validated against a fresh
read and retried on conflict (the existing OCC path) — optionally behind a
per-book `strict` flag. On standalone `mongod` this serializes-by-retry rather
than being truly atomic; the clean escape hatch (no code change above the seam)
is a **Mongo replica set** (even single-node), which unlocks real
multi-document transactions if this ever outgrows the home NAS. See §9 for why
we do *not* reach for a second datastore to get this.

### 8.2 Authorization: sharing moves from admin-only to owner-delegated

The grant model already allows many users on one resource and fine-grained
`book → plotline → event` scoping, so per-collaborator access carries over free.
Two changes:

- **A `share` permission.** Today only a global admin edits grants. A book
  **owner** (the creator, granted all perms at book scope) must be able to
  invite collaborators on *their* book without being an admin. Adding `share`
  to the permission set — and requiring it for the §7.5 routes — delegates this
  cleanly, with no other authz change.
- **Roles as perm presets.** `owner` / `editor` / `reader` are just bundles over
  the existing `read`/`write`/`delete` (+`share`) at book scope — no new
  concept, just convenience.

**Shared `_auth`, namespaced by resource type.** Chronos and `akasha`
use the **same `_auth` store** (one identity, one login, one grant model — see
§12), so their grants share one `_auth.grants` collection and one matcher. They
are kept apart by a **`resource_type` discriminator** on every grant —
`"database"` for Akasha, `"book"` for Chronos — rather than by separate
scope keys. Both reuse the same three positional scope fields; only the
discriminator distinguishes them:

```jsonc
{"resource_type": "database", "database": "ember-pact", "collection": "characters",
 "doc_id": "aldric", "perms": ["read"]}          // Akasha
{"resource_type": "book",     "database": "ember-pact", "collection": null,
 "doc_id": null,   "perms": ["read","write"]}    // chronos (book scope)
```

`resource_type` is matched **exactly and is never a wildcard**, unlike the scope
fields. That is the load-bearing rule: without it a Chronos book named `x` would
be indistinguishable from a Akasha *database-wide* grant on `x`, and
creating the book would silently confer blanket access to that database (a bug
this design originally had). A grant with no `resource_type` predates the field
and is read as `"database"`, so existing Akasha grants keep working
unchanged.

Two consequences worth stating: anything that *edits* grants must also scope by
resource type — the idempotent collaborator invite removes only `book` grants,
never a user's Akasha grants — and the new `share` permission simply
joins the shared permission set.

### 8.3 Attribution & concurrent edits

- **Attribution comes for free.** The reused `_history` snapshots already stamp
  `author` per revision; `/books/<book>/activity` (§7.5) aggregates them into a
  per-book feed so collaborators see each other's moves.
- **Same-record edits reuse the editor's OCC + diff.** `If-Match`/`_rev` already
  prevents silent lost updates; the document editor already detects a concurrent
  save and shows a diff. Chronos reuses that machinery. Deliberately
  **turn-based** (each saves their own edits, conflicts shown on save) — live
  simultaneous editing would mean WebSockets/CRDTs, a poor fit for the NAS.

---

## 9. Persistence — one seam, two viable backends

Per the design decision, the domain is written entirely against the
`StoryStore` seam (§6.1), so the backend is swappable and does **not** shape the
services or the pure logic. Here are the two realistic choices, with a
recommendation.

### Option A — MongoDB only (recommended to start)

Store books/plotlines/events as documents in a reserved `_chronos` database
(the `_auth` pattern), edges embedded as ordered id arrays on the plotline doc.

- **Pros:** one datastore, one ops story; reuses `DocumentStore`'s exact
  OCC/`_rev`/soft-delete machinery; **`mongomock` gives fast, hermetic tests**;
  entity checks can be a same-process `DocumentStore` call (no network). The
  graph algorithms (convergence, the descriptive graph view) are small walks
  over one book — and they live in the *pure* modules, which this codebase
  actively prefers to test in isolation anyway.
- **Cons:** graph traversals are app-level code rather than a query. At the
  scale of a single novel (hundreds of events), this is negligible.

### Option B — a graph database for the graph + Mongo for entities

Events are vertices, `PRECEDES` edges carry the plotline id; convergence /
divergence / reachability / terminus become native graph traversals. When this
was written the repo carried an unused JanusGraph service in `docker/`, which
made it the obvious candidate.

- **Pros:** graph queries are native and scale to very large or cross-book
  graphs; the model *is* a graph, so it's a natural fit.
- **Cons:** a second query language and a second datastore to run, seed, and —
  importantly — **fake in tests** (there's no `mongomock` equivalent for it),
  which cuts against the fast-unit-test philosophy. The temporal-conflict query
  also needs a character→events index that Mongo gives more directly.

### Recommendation

**Option A (Mongo-only) is the decision.** It matches every existing pattern,
keeps tests hermetic and fast, and is more than sufficient for book-sized
graphs. Because all graph logic sits behind the `StoryStore` seam and in pure
functions, **adopting a graph database later is a new adapter, not a rewrite** —
swap the injected store, leave services and rules untouched. Reach for Option B
only if a concrete need appears (huge graphs, cross-book queries, graph
analytics).

> **Since decided:** the JanusGraph service, its `graph_schema/` config and the
> miniconda dev image have been **removed from the repo** — they were unused and
> the graph work is done in-process with NetworkX (below). Option B is retained
> here as rationale, not as something wired up.

### Graph queries: NetworkX as an in-process compute layer

The graph-shaped questions (does every event reach the terminus? which events
are divergence/convergence points? is the graph acyclic?) are answered by
loading a book's edges from Mongo and building a `networkx.DiGraph` **inside the
pure `book_rules` module** — not by a graph datastore. NetworkX is pure-Python
(no server, no container, no system deps — it fits the "works on a LAN-only NAS"
ethos), and it turns hand-rolled walks into readable, proven algorithms
(`descendants`, `ancestors`, `all_simple_paths`, `transitive_reduction`,
`is_directed_acyclic_graph`) that back `/validate` and `/graph`. Because
book graphs are tiny, its pure-Python speed is a non-issue and its expressiveness
is pure upside. It stays trivially unit-testable: build a `DiGraph` from literal
edges and assert.

### Why not a second datastore (SQLite, embedded graph DBs)?

A second store was considered and rejected. Mongo is **already present and
guaranteed** (Chronos always ships with `akasha`), so a second store
adds cost without a matching benefit:

- **The one real draw is transactions.** SQLite (and embedded graph DBs like
  Kùzu) offer ACID, which *could* hard-enforce the cross-document story
  invariants that standalone `mongod` cannot (§8.1). But we chose the **soft
  (computed-warning)** model for those, which removes that need — and *if* hard
  enforcement is ever required, a **single-node Mongo replica set** delivers
  real multi-document transactions **while keeping one store**, beating SQLite
  on simplicity.
- **A second store reintroduces dual-write drift** — two systems to keep
  consistent, back up, and monitor — the very thing "Mongo-only" was chosen to
  avoid. Entities *must* live in `akasha` (Mongo) regardless, so a
  SQLite Chronos would straddle two stores permanently.
- **SQLite's coarse write locking** (one writer DB-wide) and its **broken
  locking over network filesystems** are minor here (local Docker volume, few
  writers) but are pure downside versus reusing the Mongo that is already there.

Net: **Mongo (durable store) + NetworkX (compute)**, with a Mongo replica set as
the escape hatch if transactions are ever needed — no SQLite, no embedded graph
DB.

---

## 10. Error taxonomy

A `ChronosError(status_code, message)` base mirrors `AkashaError`, so
one error handler serializes everything. Subclasses:

| Error                | Status | Raised when                                                        |
| -------------------- | :----: | ------------------------------------------------------------------ |
| `InvalidTimeframe`   |  400   | `start_tick > end_tick`, or a tick isn't an integer                |
| `InvalidPlotline`    |  400   | empty event list, empty goals, unknown event id referenced         |
| `EntityNotFound`     |  422   | an EntityRef doesn't exist (or isn't readable) in `akasha` |
| `TemporalConflict`   |  409   | a write would put a character in two places at once (§5.1)         |
| `OrderingViolation`  |  422   | a plotline's events aren't strictly, non-overlappingly ordered (§5.2)|
| `TerminusViolation`  |  422   | a plotline in the book doesn't end at the terminus (§5.3)          |
| `EventInUse`         |  409   | deleting an event a plotline still lists, without `?detach=true` (§7.2) |
| `TerminusInUse`      |  409   | deleting the book's terminus before a new one is designated (§7.2) |
| `BookNotFound` / `PlotlineNotFound` / `EventNotFound` | 404 | addressing something absent               |
| `RevisionConflict`   |  409   | `If-Match`/`_rev` is stale (reused OCC)                            |

`409`s (conflicts) and `422`s (invariant violations) carry a machine-readable
body listing the specific offending events/plotlines, so a UI can point the
writer straight at the problem.

Under the **all-soft model** (§8.1), the story-logic rows (`TemporalConflict`,
`OrderingViolation`, `TerminusViolation`) are *not* raised on write for any book
— the write succeeds and the same machine-readable payloads appear in the
`/validate` report and the book's `status` instead. The referential rows
(`EntityNotFound`, `InvalidTimeframe`, `InvalidPlotline`) are always hard.

---

## 11. Testing strategy

The layering exists to make this cheap:

- **Pure logic (the bulk of the tests).** `conflicts`, `ordering`, and
  `book_rules` are tested with literal events and integer ticks — no DB, no
  Flask, no mocks. Overlap boundaries, adjacent-only ordering, terminus
  mismatches, the empty-set cases.
- **Services.** Tested with a fake `StoryStore` and a fake `EntityGate` (both
  set-backed), asserting orchestration: that a create rejects a missing entity,
  that an event edit re-validates dependent plotlines, that OCC preconditions
  flow through.
- **Routes / integration.** Tested against the real `create_app` with a
  `mongomock` `StoryStore` (Option A) and a fake gate — status codes, auth/grant
  enforcement, `ETag`/`If-Match`, and the shape of the `/validate` and `/graph`
  reports.
- **Contract.** A test validates real route responses against the published
  JSON Schema in `docs/openapi.json` (e.g. the Plotline example and a live
  `GET …/plotlines/<id>` both conform), so the contract and the code cannot
  drift (§7.6).
- **Cross-service grant isolation.** Because both services share one `_auth`
  store, tests assert a `book` grant never satisfies a `database` request (and
  vice versa) **using the same name for both**, that inviting a collaborator
  leaves their Akasha grants alone, and that legacy grants without a
  `resource_type` still work (§8.2). Same-name collision is the case that
  matters; tests that use distinct names pass either way and prove nothing.

---

## 12. Open decisions & future work

- ~~**Hard vs soft per rule.**~~ **Decided:** all-soft, always — story-logic
  invariants are computed warnings for every book, referential ones always hard,
  no per-book/per-rule toggle and no collaborator-based mode switch (§8.1). A
  per-book `strict` flag remains a no-redesign future option if demand appears.
- ~~**Auth store sharing.**~~ **Decided:** share the `_auth` store — one
  identity, one login, one grant model across both services. Chronos grants sit
  in the same `grants` collection and are kept apart by a `resource_type`
  discriminator (`"book"` vs `"database"`) that is matched exactly, so a book
  and a database of the same name never confer each other's access; the `share`
  permission joins the shared set (§8.2). (Justified by constraint #1: Chronos
  always ships with Akasha.)
- ~~**Deleting a referenced event.**~~ **Decided:** block by default
  (`409 EVENT_IN_USE`, names the referencing plotlines); opt-in `?detach=true`
  removes it from those plotlines first, then deletes; deleting the terminus is
  always blocked until a new one is designated (`409 TERMINUS_IN_USE`) (§7.2).
- ~~**Cross-book event reuse.**~~ **Decided:** no — events stay **book-scoped**.
  Every core invariant is defined within one book (temporal conflict, ordering,
  per-book terminus + free acyclicity), so sharing events across independent
  timelines has no well-defined meaning. The genuinely shared canon —
  characters, items, locations — is already shared via `EntityRef` into
  Akasha (§3.1). If a series/universe is ever wanted, the clean path is
  a future **"Series"** grouping *above* Book (sharing the entity canon, perhaps
  cross-referencing termini) with events still book-local — not cross-book
  events; that would first require defining cross-timeline conflict semantics and
  a multi-book graph/terminus model.
- **The `/graph` view as a real visualization.** *Deferred (future work).* The
  API is deliberately visualization-ready — `/graph` (nodes + labeled edges +
  convergence/divergence/terminus), the event-neighborhood endpoint, titles +
  codec-formatted `when` on every node, and `status`/`/validate` for coloring.
  A future viewer renders `/graph` laid out by tick and colored by `status`,
  built the same vanilla-JS + SVG way as the document editor (no build
  toolchain, LAN-friendly). Nothing in the current design needs to change for it.
