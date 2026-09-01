"""Seed the running stack with a small demo story that has real problems in it.

Creates, over the real HTTP APIs (no direct DB writes):

- akasha: the canon -- characters, items, locations as articles.
- chronos: the book "The Ember Pact" with two parallel calendars, six events,
  five plotlines -- three of which share one ending via `continues_into` -- and
  the goals those threads serve, one resting on two others. The calendars are a
  fictional one and Earth's, over the same scenes: the Harbor Exchange is Year
  1, Month 1, Day 3 in the Imperial Reckoning and February 29, 2024 on Earth,
  and it is tick 48 either way.

Three of those plotlines are sound. The fourth -- "The Witness's Tale" -- is
deliberately broken, so a fresh seed leaves the book **conflicted** and you can
see all three continuity checks firing at once:

  1. temporal conflict  -- Aldric is at Highkeep and Emberport at the same time
  2. ordering violation -- the thread lists a later scene before an earlier one
  3. convergence failure -- the thread never reaches the terminus

Run it, then look at `GET /books/ember-pact/validate`.

Usage (from the repo root, stack already up):
    python docker/seed_demo.py          # seed; leaves the book CONFLICTED
    python docker/seed_demo.py --fix    # repair all three; leaves it CONSISTENT
    python docker/seed_demo.py --mixed  # also add "The Cartographer's Doubt", a
                                        # thread mixing scheduled + undated scenes
    python docker/seed_demo.py --periods  # also add "The Long Survey", a thread
                                          # spanning several months/years (shows the
                                          # visualiser's nested year/month rail).
                                          # Runs past the terminus, so it adds one
                                          # (soft) convergence finding by design.
    python docker/seed_demo.py --solo     # also add "The Coronation Bell", a
                                          # thread that meets no other thread at
                                          # all -- a second lane of its own on the
                                          # story map, beside "The Long Survey".
                                          # Flags combine, e.g. --fix --periods --solo.

Re-running is safe: existing records are updated rather than duplicated.
"""

import json
import os
import sys
import urllib.error
import urllib.request

# Defaults target the single-origin stack (docker-compose.nas.yml): akasha at
# `/`, chronos under `/timeline`, both on one port. Override via env to point at
# a split/dev deployment, e.g. CHRONOS_BASE=http://localhost:5003.
DOCS = os.environ.get("AKASHA_BASE", "http://localhost:5002")
CHRONOS = os.environ.get("CHRONOS_BASE", "http://localhost:5002/timeline")

USER = "mara"
PASSWORD = "ember-pact-demo"
EMAIL = "mara@example.com"

DB = "ember-pact"
BOOK = "ember-pact"
# The library entry the book attaches. Named for the reckoning, not the book:
# it outlives any one story, which is the whole point of the library.
CALENDAR_ID = "imperial"

CALENDAR = {
    "base_unit": "hour",
    "cycles": [
        {"name": "day", "size": 24},
        {"name": "month", "size": 30},
        {"name": "year", "size": 12},
    ],
    "epoch_label": "AF",
}

# The second reckoning over the same scenes: Earth, for the story's parallel
# thread here. Its tick is an hour because the book's tick is an hour -- both
# calendars read one tick line, and Earth has to advance at its pace.
EARTH_CALENDAR_ID = "earth"
EARTH_CALENDAR = {"kind": "gregorian", "tick_unit": "hour"}

# Where this story meets Earth's timeline. Chosen so the Harbor Exchange at tick
# 48 lands on February 29 -- the one date no fixed-cycle calendar can produce,
# and the clearest way to see the two reckonings are not the same arithmetic.
# It belongs to the book, not to the library entry above: another story could
# attach the same Earth calendar a thousand years away.
EARTH_ORIGIN = "2024-02-27T00:00Z"


def calendar_attachments():
    """The two readings this book keeps of its one tick line."""
    return [
        {
            "id": CALENDAR_ID,
            "label": "Imperial Reckoning",
            "source": {"owner": USER, "calendar": CALENDAR_ID},
        },
        {
            "id": EARTH_CALENDAR_ID,
            "label": "Earth",
            "source": {"owner": USER, "calendar": EARTH_CALENDAR_ID},
            "origin": EARTH_ORIGIN,
        },
    ]

# Each entity is a full article: a reserved ``title`` and wikitext ``body`` (with
# [[col/id|label]] cross-links, resolved relative to the article's own
# collection), plus a few infobox facts (plain scalar fields). This is exactly
# the shape the editor reads back -- see static/js/article.js.
CHARACTERS = {
    "aldric": {
        "title": "Sir Aldric",
        "role": "Knight",
        "allegiance": "The Crown",
        "carries": "The Ember Seal",
        "body": (
            "Sir Aldric is a sworn knight of [[locations/highkeep|Highkeep]], "
            "entrusted with carrying [[items/ember-seal|the Ember Seal]] safely to "
            "the coronation.\n\n"
            "He rides out at dawn while the succession is still in dispute, and "
            "hands the Seal to the spy [[lyra|Lyra Vane]] at "
            "[[locations/emberport|Emberport]] before making for "
            "[[locations/throne-hall|the Throne Hall]]."
        ),
    },
    "lyra": {
        "title": "Lyra Vane",
        "role": "Spy",
        "cover": "Dockhand",
        "body": (
            "Lyra Vane works the shadows of [[locations/emberport|Emberport]], "
            "taking a dockhand's berth to watch the harbour unseen.\n\n"
            "She receives [[items/ember-seal|the Ember Seal]] from "
            "[[aldric|Sir Aldric]] and carries the secret of the true succession "
            "toward [[locations/throne-hall|the coronation]]."
        ),
    },
    "corwin": {
        "title": "Magister Corwin",
        "role": "Magister",
        "scheme": "Contest the succession",
        "body": (
            "Magister Corwin is a scholar of law and ambition who drafts a writ to "
            "contest the succession from within [[locations/highkeep|Highkeep]].\n\n"
            "His gambit converges on the same ending as the others: "
            "[[locations/throne-hall|the Throne Hall]], where "
            "[[items/ember-seal|the Ember Seal]] is finally pressed to the charter."
        ),
    },
}
ITEMS = {
    "ember-seal": {
        "title": "The Ember Seal",
        "type": "Royal artifact",
        "function": "Makes a succession lawful",
        "body": (
            "The Ember Seal is the royal sigil that makes a succession lawful; "
            "without its impression the charter is only ink.\n\n"
            "Carried by [[characters/aldric|Sir Aldric]], passed to "
            "[[characters/lyra|Lyra Vane]], and contested by "
            "[[characters/corwin|Magister Corwin]], the Seal is the object every "
            "thread of the story turns upon."
        ),
    }
}
LOCATIONS = {
    "highkeep": {
        "title": "Highkeep",
        "type": "Fortress",
        "body": (
            "Highkeep is the mountain fortress from which "
            "[[characters/aldric|Sir Aldric]] departs, and where "
            "[[characters/corwin|Magister Corwin]] drafts his contesting writ.\n\n"
            "The road from its gates leads down to [[emberport|Emberport]] and, in "
            "time, to [[throne-hall|the Throne Hall]]."
        ),
    },
    "emberport": {
        "title": "Emberport",
        "type": "Harbour city",
        "body": (
            "Emberport is a harbour city of crowded quays and market awnings. "
            "[[characters/lyra|Lyra Vane]] works its docks under cover, and it is "
            "here that [[characters/aldric|Sir Aldric]] hands her "
            "[[items/ember-seal|the Ember Seal]].\n\n"
            "A disputed sighting later places Aldric at these quays while he is, in "
            "truth, still on the road from [[highkeep|Highkeep]] -- the seed of the "
            "story's continuity conflict."
        ),
    },
    "throne-hall": {
        "title": "The Throne Hall",
        "type": "Great hall",
        "body": (
            "The Throne Hall is where the realm crowns its heir and "
            "[[items/ember-seal|the Ember Seal]] is pressed to the charter at last."
            "\n\n"
            "Every sound thread -- [[characters/aldric|the knight's]], "
            "[[characters/lyra|the spy's]], and [[characters/corwin|the "
            "magister's]] -- converges here at the coronation."
        ),
    },
}

# id, title, location, start, end, characters, items, description
EVENTS = [
    ("aldric-departs", "Aldric Departs", "highkeep", 0, 24, ["aldric"], [],
     "Sir Aldric rides out from Highkeep at dawn, the Ember Seal's charge unspoken."),
    ("lyra-infiltrates", "Lyra Infiltrates", "emberport", 0, 48, ["lyra"], [],
     "Lyra slips into Emberport's harbour district and takes work as a dockhand."),
    ("meet-at-emberport", "The Harbor Exchange", "emberport", 48, 72,
     ["aldric", "lyra"], ["ember-seal"],
     "Aldric and Lyra exchange the Ember Seal beneath the harbour market awnings."),
    ("corwin-plots", "Corwin Plots", "highkeep", 96, 120, ["corwin"], [],
     "Magister Corwin drafts the writ that will contest the succession."),
    ("the-coronation", "The Coronation", "throne-hall", 200, 210,
     ["aldric", "lyra", "corwin"], ["ember-seal"],
     "The realm crowns its heir; the Ember Seal is pressed to the charter at last."),
]

# The disputed sighting. Broken on purpose: it overlaps Aldric's ride (hours
# 0-24 at Highkeep) while placing him at Emberport.
SIGHTING_BROKEN = ("aldric-at-emberport", "Aldric Seen At Emberport", "emberport", 10, 30,
                   ["aldric"], [],
                   "A witness places Aldric at the quay -- while he is still riding.")
# Moving it later resolves the overlap.
SIGHTING_FIXED = (*SIGHTING_BROKEN[:3], 30, 40, *SIGHTING_BROKEN[5:])

# The shared ending, written once. The knight's and spy's threads continue into
# it rather than repeating it -- add a scene here and both threads get it.
# (Order matters: the trunk must exist before anything continues into it.)
# What the book is trying to bring about. Goals are records of their own, and
# threads name them by id -- so two threads pursuing one goal say so by pointing
# at the same thing, and the book can be asked whether it delivers what it set
# out to. (id, title, description, depends_on, achieved_at).
#
# The chain is the interesting part: the charter cannot be sealed until the Seal
# has changed hands and the traitor is out, and both of those land at the harbour
# (hours 48-72), well before the coronation (hour 200) -- so this book's goals
# are achieved in an order that holds up. Move the exchange after the coronation
# and chronos says so.
GOALS = [
    ("seal-delivered", "Deliver the Ember Seal",
     ("The Seal has to reach Emberport and change hands before it can be "
      "pressed to anything."), [], "meet-at-emberport"),
    ("traitor-exposed", "Expose the traitor",
     "Lyra's whole errand: find out who in the harbour is selling the crown.",
     [], "meet-at-emberport"),
    ("charter-sealed", "See the Seal pressed to the charter",
     "The book's ending, stated as an intention.",
     ["seal-delivered", "traitor-exposed"], "the-coronation"),
    ("crown-reached", "Reach the coronation alive",
     "Aldric's own stake in it.", ["seal-delivered"], "the-coronation"),
    ("succession-contested", "Contest the succession",
     "Corwin means the crowning to be argued, not merely watched.",
     [], "the-coronation"),
    # Deliberately left with no scene: a goal named before the scene that pays it
    # off is written is the ordinary state of a book in progress, and chronos
    # reports it as a note rather than a fault.
    ("who-was-where", "Establish who was where",
     "The witness's account -- still unwritten.", [], None),
]

SOUND_PLOTLINES = [
    ("trunk", "The Road to the Crown", ["charter-sealed"],
     ["meet-at-emberport", "the-coronation"], None),
    ("knights-road", "The Knight's Road",
     ["seal-delivered", "crown-reached"],
     ["aldric-departs"], "trunk"),
    ("spys-shadow", "The Spy's Shadow", ["traitor-exposed"],
     ["lyra-infiltrates"], "trunk"),
    # This one joins only at the very end, so it keeps its own full path.
    ("magisters-gambit", "The Magister's Gambit", ["succession-contested"],
     ["corwin-plots", "the-coronation"], None),
]

# Out of order (hour 48-72 listed before hour 10-30) AND stops short of the
# terminus -- two more findings on top of the temporal conflict.
WITNESS_BROKEN = ("witness-tale", "The Witness's Tale", ["who-was-where"],
                  ["meet-at-emberport", "aldric-at-emberport"], None)
WITNESS_FIXED = (*WITNESS_BROKEN[:3], ["aldric-at-emberport"], "trunk")

TERMINUS = "the-coronation"

# -- optional: a mixed-timing thread for experimentation (enabled with --mixed) --
# Some scenes are scheduled, some have no timing yet, so the visualiser's vertical
# timeline shows both dated nodes and "unscheduled" ones (with inferred windows).
# It uses its OWN character, so it can never temporally conflict with the main
# cast, and converges on the terminus, so it leaves the book's status unchanged.
CARTOGRAPHER = {
    "title": "Mira the Cartographer",
    "role": "Cartographer",
    "body": (
        "Mira surveys the disputed march between [[locations/highkeep|Highkeep]] "
        "and [[locations/emberport|Emberport]], mapping roads the crown has "
        "forgotten."
    ),
}

# Same 8-field shape as EVENTS; start=end=None means the scene is unscheduled.
MIXED_EVENTS = [
    ("cartographer-sets-out", "The Cartographer Sets Out", "highkeep", 0, 12,
     ["mira-the-cartographer"], [],
     "Mira leaves Highkeep at dawn to survey the disputed march."),
    ("a-rumor-in-the-market", "A Rumor in the Market", "emberport", None, None,
     ["mira-the-cartographer"], [],
     "In the Emberport market Mira hears of an unmarked road -- when, no one agrees."),
    ("crossing-the-fens", "Crossing the Fens", "emberport", 48, 72,
     ["mira-the-cartographer"], ["ember-seal"],
     "Mira crosses the fens with the survey in hand."),
    ("the-unmarked-road", "The Unmarked Road", "highkeep", None, None,
     ["mira-the-cartographer"], [],
     "The road Mira was warned of -- its timing still a mystery."),
]

# Ends on the shared terminus so the thread converges (ordering stays clean).
MIXED_GOALS = [
    ("lands-mapped", "Map the disputed lands",
     "The march between Highkeep and Emberport, drawn properly at last.",
     [], "crossing-the-fens"),
    ("survey-delivered", "Reach the coronation with the survey",
     "A map is worth nothing in a saddlebag.", ["lands-mapped"], "the-coronation"),
]

MIXED_PLOTLINE = ("cartographers-doubt", "The Cartographer's Doubt",
                  ["lands-mapped", "survey-delivered"],
                  ["cartographer-sets-out", "a-rumor-in-the-market", "crossing-the-fens",
                   "the-unmarked-road", "the-coronation"], None)

# -- optional: a thread spanning several periods (enabled with --periods) --------
# Scenes stepping into Year 1/Month 2 and Year 2/Month 1, so the visualiser's rail
# shows its nested year -> month grouping (not just a single band). Also uses Mira,
# so no temporal conflict. Ticks follow the CALENDAR above: day=24, month=720
# (30d), year=8640 (12mo) -- Y1 M1 D15 -> 336, Y1 M2 D5 -> 816, Y2 M1 D2 -> 8664.
# NOTE: it deliberately runs *past* the coronation, so it cannot end at the
# terminus -- it adds one soft convergence finding (by design), independent of --fix.
LONG_SURVEY_EVENTS = [
    ("survey-first-light", "Survey: First Light", "highkeep", 336, 348,
     ["mira-the-cartographer"], [],
     "Mira records the first true survey line from Highkeep."),
    ("survey-second-month", "Survey: The Second Month", "emberport", 816, 828,
     ["mira-the-cartographer"], [],
     "A month on, Mira reworks the coast at Emberport."),
    ("survey-a-year-on", "Survey: A Year On", "highkeep", 8664, 8676,
     ["mira-the-cartographer"], [],
     "A full year later, Mira returns to close the map."),
]

LONG_SURVEY_GOALS = [
    ("realm-charted", "Chart the realm across the seasons",
     "One map, three visits, a year apart.", [], "survey-a-year-on"),
]

LONG_SURVEY_PLOTLINE = ("the-long-survey", "The Long Survey",
                        ["realm-charted"],
                        ["survey-first-light", "survey-second-month", "survey-a-year-on"],
                        None)

# -- optional: a second thread that meets nobody (enabled with --solo) ----------
# A subplot running the whole length of the book without ever touching the main
# cast: it shares only the terminus, and the story map deliberately does not count
# the terminus as a meeting (every thread ends there, so counting it would make
# every thread "connected"). So this is a thread the map draws in a lane of its
# own, alongside "The Long Survey" -- and the two make the pair worth looking at:
#
#   The Long Survey     solo AND never reaches the ending (a convergence finding)
#   The Coronation Bell solo and perfectly well-formed (no findings at all)
#
# Its scenes are interleaved in time with the main cast's rather than sitting
# before or after them, which is the thing to look at on the map: two threads
# that never touch, whose scenes still take their turn down the same time axis.
# Its own character, so it cannot temporally conflict with anyone.
BELLFOUNDER = {
    "title": "Elin the Bellfounder",
    "role": "Bellfounder",
    "commission": "The coronation bell",
    "body": (
        "Elin casts bells in the foundry below [[locations/highkeep|Highkeep]], and "
        "has been given until the coronation to hang a new one in "
        "[[locations/throne-hall|the Throne Hall]].\n\n"
        "She never meets [[characters/aldric|Sir Aldric]] or "
        "[[characters/lyra|Lyra Vane]], and knows nothing of "
        "[[items/ember-seal|the Ember Seal]] -- her thread runs the length of the "
        "book beside theirs and touches it only at the end."
    ),
}

SOLO_EVENTS = [
    ("bell-the-commission", "The Commission", "highkeep", 12, 20,
     ["elin-the-bellfounder"], [],
     "Elin is given until the coronation to cast and hang a new bell."),
    ("bell-the-pour", "The Pour", "highkeep", 60, 68,
     ["elin-the-bellfounder"], [],
     "The melt goes into the mould at dawn; nothing can be corrected after this."),
    ("bell-the-flaw", "The Flaw", "emberport", 120, 128,
     ["elin-the-bellfounder"], [],
     "A hairline crack, found late, that only Elin can hear."),
    ("bell-the-hanging", "The Hanging", "throne-hall", 168, 176,
     ["elin-the-bellfounder"], [],
     "The bell goes up the night before, flaw and all."),
]

SOLO_GOALS = [
    ("bell-hung", "Hang a bell worth the crowning",
     "Cast, flawed, and hung anyway -- Elin's whole book.", [], "bell-the-hanging"),
]

SOLO_PLOTLINE = ("the-coronation-bell", "The Coronation Bell",
                 ["bell-hung"],
                 ["bell-the-commission", "bell-the-pour", "bell-the-flaw",
                  "bell-the-hanging", "the-coronation"], None)


class Client:
    """Cookie-preserving JSON HTTP client (one session across both services)."""

    def __init__(self):
        self._cookie = None

    def request(self, method, url, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self._cookie:
            req.add_header("Cookie", self._cookie)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode()
                cookie = resp.headers.get("Set-Cookie")
                if cookie:
                    self._cookie = cookie.split(";")[0]
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as err:
            raw = err.read().decode()
            try:
                return err.code, json.loads(raw)
            except json.JSONDecodeError:
                return err.code, {"error": raw[:200]}

    def post(self, url, body=None):
        return self.request("POST", url, body if body is not None else {})

    def get(self, url):
        return self.request("GET", url)

    def put(self, url, body):
        return self.request("PUT", url, body)

    def upsert(self, url, body):
        """Create, or replace if it already exists -- so re-runs are safe."""
        status, result = self.post(url, body)
        if status == 409:
            return self.put(url, body)
        return status, result


def ref(collection, id_):
    return {"database": DB, "collection": collection, "id": id_}


def event_payload(spec):
    eid, title, loc, start, end, chars, items, desc = spec
    payload = {
        "title": title,
        "location": ref("locations", loc),
        "characters": [ref("characters", c) for c in chars],
        "items": [ref("items", i) for i in items],
        "description": desc,
    }
    # Ticks are both-or-neither: start=end=None marks an *unscheduled* scene (one
    # with no timing yet), which Chronos keeps out of the timing checks.
    if start is not None and end is not None:
        payload["start_tick"] = start
        payload["end_tick"] = end
    return eid, payload


def step(label):
    print(f"\n=== {label} ===")


def show(status, label, detail=""):
    mark = "ok " if status < 400 else "ERR"
    print(f"  [{mark}] {status}  {label}{(' -- ' + detail) if detail else ''}")


# -- seeding -----------------------------------------------------------------


def login(client):
    step("account")
    status, _ = client.post(
        f"{DOCS}/register", {"username": USER, "password": PASSWORD, "email": EMAIL}
    )
    show(status, f"register '{USER}'", "already exists (fine)" if status == 409 else "")
    status, _ = client.post(f"{DOCS}/login", {"username": USER, "password": PASSWORD})
    show(status, "login to akasha")
    if status != 200:
        sys.exit("login failed -- cannot seed")
    status, _ = client.get(f"{CHRONOS}/books")
    show(status, "same session accepted by chronos")


def seed_entities(client):
    step("akasha: the canon (entities chronos will reference)")
    for collection, entries in (
        ("characters", CHARACTERS), ("items", ITEMS), ("locations", LOCATIONS)
    ):
        client.post(f"{DOCS}/databases/{DB}/collections/{collection}")
        for slug, document in entries.items():
            status, _ = client.upsert(
                f"{DOCS}/databases/{DB}/collections/{collection}/documents/{slug}",
                document,
            )
            show(status, f"{collection}/{slug}", document.get("title", ""))


LIBRARY_CALENDARS = [
    (CALENDAR_ID, "Imperial Reckoning", CALENDAR,
     "Hours, days, months, years, counted from the Founding (AF)."),
    (EARTH_CALENDAR_ID, "Earth", EARTH_CALENDAR,
     "Gregorian dates, for the thread that runs beside our own world."),
]


def seed_calendar(client):
    """Put the story's calendars in the library, where calendars live.

    A book chooses a calendar rather than describing one, so these have to exist
    before the book can point at them. It is also the reusable half: the same
    entries are offered to every other book this writer starts.
    """
    step("chronos: the calendars, in the library")
    for calendar_id, name, descriptor, notes in LIBRARY_CALENDARS:
        status, body = client.upsert(f"{CHRONOS}/calendars/{USER}/{calendar_id}", {
            "name": name,
            "descriptor": descriptor,
            "notes": notes,
        })
        show(status, f"calendar '{USER}/{calendar_id}'",
             body.get("name", "") if body else "")


def seed_book_and_events(client):
    step("chronos: the book and its scenes")
    # The book *names* the calendar; the server copies the descriptor in. There
    # is no inline spelling to choose here -- the API refuses one.
    status, body = client.upsert(f"{CHRONOS}/books/{BOOK}", {
        "title": "The Ember Pact",
        "calendars": calendar_attachments(),
    })
    show(status, f"book '{BOOK}'")
    for spec in [*EVENTS, SIGHTING_BROKEN]:
        eid, payload = event_payload(spec)
        status, body = client.upsert(f"{CHRONOS}/books/{BOOK}/events/{eid}", payload)
        show(status, f"event {eid}", body.get("start_label", "") if body else "")


def demo_hard_rule(client):
    step("a HARD rule: referencing something that doesn't exist is REJECTED")
    status, body = client.post(f"{CHRONOS}/books/{BOOK}/events/ghost-event", {
        "location": ref("locations", "highkeep"),
        "start_tick": 0, "end_tick": 1,
        "characters": [ref("characters", "nobody-here")],
    })
    show(status, "event referencing a non-existent character",
         body.get("code", "") if body else "")


def seed_goals(client, goals, heading=None):
    """Upsert goals. Must run *after* the scenes and *before* the threads.

    Both halves of that are enforced by the API rather than by convention: a
    goal may only be achieved at a scene that exists, and a thread may only
    serve a goal that exists. Ordering them correctly here is the difference
    between a demo that seeds and one that prints two 400s.
    """
    if heading:
        step(heading)
    for gid, title, description, depends_on, achieved_at in goals:
        status, body = client.upsert(f"{CHRONOS}/books/{BOOK}/goals/{gid}", {
            "title": title,
            "description": description,
            "depends_on": depends_on,
            "achieved_at": achieved_at,
        })
        detail = ""
        if status < 400 and body:
            detail = body["status"]["state"]
            if depends_on:
                detail += f", after {', '.join(depends_on)}"
        show(status, f"goal {gid}", detail)


def seed_plotlines(client, witness):
    step("chronos: plotlines (the shared ending lives once, in 'trunk')")
    for pid, title, goals, evs, into in [*SOUND_PLOTLINES, witness]:
        body = {"title": title, "goals": goals, "events": evs}
        if into:
            body["continues_into"] = into
        status, result = client.upsert(f"{CHRONOS}/books/{BOOK}/plotlines/{pid}", body)
        detail = f"-> {into}" if into else "(own full path)"
        if status < 400:
            detail += f"  ordering={result['status']['ordering']['state']}"
        show(status, f"plotline {pid}", detail)
    status, _ = client.post(f"{CHRONOS}/books/{BOOK}/terminus/{TERMINUS}")
    show(status, f"terminus = {TERMINUS}")


def ensure_cartographer(client):
    """Upsert the fresh character both optional threads use, so they can never
    temporally conflict with the main cast. Idempotent (safe if both run)."""
    status, _ = client.upsert(
        f"{DOCS}/databases/{DB}/collections/characters/documents/mira-the-cartographer",
        CARTOGRAPHER,
    )
    show(status, "characters/mira-the-cartographer", CARTOGRAPHER["title"])


def seed_thread(client, event_specs, plotline, goals=()):
    """Upsert a thread's scenes, then its goals, then the plotline itself --
    reporting each scene's timing and the plotline's ordering / terminus
    verdicts. The order is the API's, not a preference (see ``seed_goals``)."""
    for spec in event_specs:
        eid, payload = event_payload(spec)
        status, body = client.upsert(f"{CHRONOS}/books/{BOOK}/events/{eid}", payload)
        when = ""
        if body:
            when = body.get("start_label") if body.get("scheduled") else "unscheduled"
        show(status, f"event {eid}", when or "")

    seed_goals(client, goals)

    pid, title, goal_ids, evs, into = plotline
    body = {"title": title, "goals": goal_ids, "events": evs}
    if into:
        body["continues_into"] = into
    status, result = client.upsert(f"{CHRONOS}/books/{BOOK}/plotlines/{pid}", body)
    detail = ""
    if status < 400:
        st = result["status"]
        detail = (f"ordering={st['ordering']['state']}, "
                  f"ends_at_terminus={st['ends_at_terminus']['state']}")
    show(status, f"plotline {pid}", detail)


def seed_experiment(client):
    step("chronos: a mixed-timing thread to experiment with (--mixed)")
    ensure_cartographer(client)
    seed_thread(client, MIXED_EVENTS, MIXED_PLOTLINE, MIXED_GOALS)


def ensure_bellfounder(client):
    """Upsert the character the solo thread belongs to. Idempotent."""
    status, _ = client.upsert(
        f"{DOCS}/databases/{DB}/collections/characters/documents/elin-the-bellfounder",
        BELLFOUNDER,
    )
    show(status, "characters/elin-the-bellfounder", BELLFOUNDER["title"])


def seed_solo(client):
    step("chronos: a second thread that meets nobody (--solo)")
    ensure_bellfounder(client)
    seed_thread(client, SOLO_EVENTS, SOLO_PLOTLINE, SOLO_GOALS)


def seed_periods(client):
    step("chronos: a multi-period thread for the nested year/month rail (--periods)")
    ensure_cartographer(client)
    # Runs past the terminus by design, so expect ends_at_terminus=conflicted.
    seed_thread(client, LONG_SURVEY_EVENTS, LONG_SURVEY_PLOTLINE, LONG_SURVEY_GOALS)


# -- reporting ---------------------------------------------------------------


def report(client):
    step("the continuity report: GET /books/ember-pact/validate")
    _, r = client.get(f"{CHRONOS}/books/{BOOK}/validate")
    print(f"  book status: {r['status'].upper()}\n")

    print(f"  temporal conflicts ({len(r['temporal_conflicts'])}):")
    for c in r["temporal_conflicts"] or ["  (none)"]:
        if isinstance(c, str):
            print(f"    {c}")
        else:
            e = c["evidence"]
            print(f"    - {c['message']}")
            print(f"      {e['characters'][0]}: {e['locations'][0]} {e['ticks'][0]} "
                  f"vs {e['locations'][1]} {e['ticks'][1]}")

    print(f"\n  ordering problems ({len(r['ordering'])}):")
    for o in r["ordering"] or ["  (none)"]:
        if isinstance(o, str):
            print(f"    {o}")
        else:
            print(f"    - [{o['plotline']}] {o['message']}  ({o['evidence']['reason']})")

    conv = r["convergence"]
    print(f"\n  threads reaching the terminus '{conv['terminus']}': "
          f"{'all of them' if conv['ok'] else 'NO'}")
    for f in conv["failures"]:
        print(f"    - [{f['plotline']}] {f['reason']} (stops at '{f.get('last_event')}')")

    # One scene, both reckonings. Same ticks either way -- which is the point:
    # nothing above this line could tell you which calendar it was computed in.
    print("\n  the Harbor Exchange, read both ways:")
    for calendar in (CALENDAR_ID, EARTH_CALENDAR_ID):
        _, scene = client.get(
            f"{CHRONOS}/books/{BOOK}/events/meet-at-emberport?calendar={calendar}"
        )
        print(f"    {calendar:9} {scene['start_label']}  (ticks {scene['start_tick']}"
              f" -> {scene['end_tick']})")


def next_steps(fixed, mixed, periods, solo=False):
    step("what to try next")
    base = f"{CHRONOS}/books/{BOOK}"
    print(f"  curl -b cookies.txt {base}                      # one-glance status")
    print(f"  curl -b cookies.txt {base}/validate             # the full report")
    print(f"  curl -b cookies.txt {base}/graph                # how threads connect")
    print(f"  curl -b cookies.txt '{base}/events?calendar=earth'  # the same scenes, dated on Earth")
    print(f"  curl -b cookies.txt {base}/events/meet-at-emberport/plotlines")
    print(f"  curl -b cookies.txt {base}/plotlines/witness-tale?expand=events")
    if fixed:
        print("\n  Re-run without --fix to break it again.")
    else:
        print("\n  Run with --fix to repair all three problems and see it go green:")
        print("    python docker/seed_demo.py --fix")
    if mixed:
        print(f"  curl -b cookies.txt {base}/plotlines/cartographers-doubt?expand=events"
              "  # the mixed-timing thread")
    else:
        print("\n  Add a thread that mixes scheduled and undated scenes with --mixed:")
        print("    python docker/seed_demo.py --mixed")
    if periods:
        print(f"  curl -b cookies.txt {base}/plotlines/the-long-survey?expand=events"
              "  # the multi-period thread")
    else:
        print("\n  Add a thread spanning several months/years (nested rail) with --periods:")
        print("    python docker/seed_demo.py --periods")
    if solo:
        print(f"  {CHRONOS}/#/{BOOK}/~map/the-coronation-bell,the-long-survey"
              "  # the two threads that meet nobody")
    else:
        print("\n  Add a second thread that meets no other thread with --solo:")
        print("    python docker/seed_demo.py --solo")


def main():
    fix = "--fix" in sys.argv
    mixed = "--mixed" in sys.argv
    periods = "--periods" in sys.argv
    solo = "--solo" in sys.argv
    client = Client()
    login(client)
    seed_entities(client)
    seed_calendar(client)
    seed_book_and_events(client)
    demo_hard_rule(client)
    seed_goals(client, GOALS, "chronos: the goals this book is trying to reach")
    seed_plotlines(client, WITNESS_BROKEN)

    if mixed:
        seed_experiment(client)
    if periods:
        seed_periods(client)
    if solo:
        seed_solo(client)

    if fix:
        step("repairing the story")
        eid, payload = event_payload(SIGHTING_FIXED)
        status, _ = client.put(f"{CHRONOS}/books/{BOOK}/events/{eid}", payload)
        show(status, "moved the sighting to hours 30-40 (no longer overlaps the ride)")
        pid, title, goals, evs, into = WITNESS_FIXED
        status, _ = client.put(
            f"{CHRONOS}/books/{BOOK}/plotlines/{pid}",
            {"title": title, "goals": goals, "events": evs, "continues_into": into},
        )
        show(status, "pointed the witness thread at the trunk so it reaches the terminus")

    report(client)
    next_steps(fix, mixed, periods, solo)
    print(f"\nExplore: {CHRONOS}/books/{BOOK}   |   articles UI: {DOCS}/")


if __name__ == "__main__":
    main()
