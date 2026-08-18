"""Seed a book built to exercise the story map, over the real HTTP APIs.

`seed_demo.py` seeds a small, deliberately broken book -- five threads, six
scenes -- which is the right size for reading the continuity report and far too
small to say anything about the map. This one seeds the other end: **The Salt
Road**, a sound book of ten threads and ~90 scenes that weave through six shared
scenes before a single ending.

It exists to make each of the map's behaviours visible on real data:

  ten threads          more than the twelve-hue palette needs, so you can see
                       colour paired with stroke rather than colliding
  six junctions        threads that genuinely meet, at scenes shared by three or
                       four of them -- what the map is *for*
  long solitary runs   every thread walks 3-4 scenes alone between junctions, so
                       roughly two thirds of the rows fold away by default
  a tangled name order what the book calls its threads has nothing to do with who
                       meets whom, so the adaptive lane order has work to do

Every thread has its own viewpoint character, so no two are ever in two places at
once and the book stays CONSISTENT -- the map is the point here, not the report.

Usage (from the repo root, stack already up):
    python docker/seed_story_map.py

Re-running is safe: records are updated rather than duplicated.
"""

import os
import sys

from seed_demo import CALENDAR, CALENDAR_ID, Client, login, show, step

CHRONOS = os.environ.get("CHRONOS_BASE", "http://localhost:5002/timeline")
DOCS = os.environ.get("AKASHA_BASE", "http://localhost:5002")

USER = "mara"  # the same writer seed_demo.py creates, so one login sees both books
DB = "salt-road"
BOOK = "salt-road"
TERMINUS = "the-reckoning"

# -- the weave ---------------------------------------------------------------
#
# Six shared scenes, at fixed times, each one a place several threads pass
# through. Everything else in the book is one thread walking alone between them.

JUNCTIONS = {
    "the-muster":       ("The Muster",       "saltgate",    100),
    "the-ford":         ("The Ford",         "bitter-ford", 300),
    "the-night-market": ("The Night Market", "saltgate",    500),
    "the-ambush":       ("The Ambush",       "the-scarps",  700),
    "the-high-pass":    ("The High Pass",    "the-pass",    900),
    "the-parley":       ("The Parley",       "tessel",     1100),
}

# (plotline id, title, viewpoint character, home location, first junction, second)
#
# The ids are what the book orders its threads by, and they are named for the
# story rather than for the weave -- which is exactly the point. Alphabetically
# "the-assayer" and "the-widow" are as far apart as two threads get, and they
# meet twice.
THREADS = [
    ("the-assayer",    "The Assayer",    "kesh",    "saltgate",    "the-muster", "the-night-market"),
    ("the-widow",      "The Widow",      "iona",    "saltgate",    "the-muster", "the-ambush"),
    ("the-outrider",   "The Outrider",   "bel",     "the-scarps",  "the-muster", "the-ford"),
    ("the-smuggler",   "The Smuggler",   "corr",    "bitter-ford", "the-ford",   "the-ambush"),
    ("the-cartwright", "The Cartwright", "hadda",   "bitter-ford", "the-ford",   "the-high-pass"),
    ("the-physician",  "The Physician",  "sabra",   "tessel",      "the-night-market", "the-high-pass"),
    ("the-envoy",      "The Envoy",      "denet",   "tessel",      "the-night-market", "the-parley"),
    ("the-quartermaster", "The Quartermaster", "olm", "the-scarps", "the-ambush", "the-parley"),
    ("the-cipher",     "The Cipher",     "wren",    "the-pass",    "the-high-pass", "the-parley"),
    ("the-boy",        "The Boy",        "tam",     "saltgate",    "the-night-market", "the-parley"),
]

LOCATIONS = {
    "saltgate": ("Saltgate", "Walled town",
                 "The last walled town before the flats, and where the salt road begins."),
    "bitter-ford": ("Bitter Ford", "River crossing",
                    "A shallow, brackish crossing that the road cannot avoid."),
    "the-scarps": ("The Scarps", "Broken country",
                   "Broken red country where the road runs narrow and the outriders earn their keep."),
    "the-pass": ("The High Pass", "Mountain pass",
                 "Snow to the knee by autumn, and the only way through the range."),
    "tessel": ("Tessel", "Free city",
               "A free city at the far end of the road, where the caravan's fate is argued."),
}

CHARACTERS = {
    "kesh":  ("Kesh Ammar", "Assayer", "Weighs the salt, and knows to the grain what the caravan is worth."),
    "iona":  ("Iona Vell", "Widow", "Holds her late husband's share of the caravan, and every debt against it."),
    "bel":   ("Bel Anwar", "Outrider", "Rides a day ahead of the column, and is trusted by nobody who stays behind."),
    "corr":  ("Corr", "Smuggler", "Moves what the caravan is not carrying, in the parts of it nobody counts."),
    "hadda": ("Hadda Iss", "Cartwright", "Keeps ninety wagons rolling with what she can cut from a hillside."),
    "sabra": ("Sabra Nuun", "Physician", "The only surgeon on the road, and the only one who knows who is dying."),
    "denet": ("Denet Ro", "Envoy", "Carries the charter that says whose road this is."),
    "olm":   ("Olm", "Quartermaster", "Decides who eats, which on this road is the same as deciding who arrives."),
    "wren":  ("Wren", "Cipher", "Reads the caravan's letters before their owners do."),
    "tam":   ("Tam", "Runner", "Twelve years old, and the fastest way to get a message down the column."),
}

# What each thread does alone, between the scenes where it meets the others. The
# templates are stitched with the character's own name, so a folded run reads as
# that thread's story and not as filler.
SOLO_BEFORE = [
    ("{name} Counts the Load", "{name} goes down the column before dawn, counting what is really on the wagons."),
    ("A Debt Called In", "Someone finds {name} in the dark with a claim that will not wait for Tessel."),
    ("The Road Out", "{name} watches Saltgate drop below the horizon and does not say what that costs."),
]
SOLO_BETWEEN = [
    ("What {name} Saw", "{name} keeps to the wagons and turns over what happened back there."),
    ("The Weight of It", "The road climbs, the water sours, and {name} makes a decision alone."),
    ("A Letter, Unsent", "{name} writes it out twice and burns both."),
    ("Night Watch", "{name} takes a watch nobody asked them to take."),
]
SOLO_AFTER = [
    ("{name} Turns Back", "Half a day back down the road, {name} looks for what was left behind."),
    ("The Last Camp", "The fires are small and close together; {name} sits at the edge of one."),
]


def ref(collection, id_):
    return {"database": DB, "collection": collection, "id": id_}


def seed_canon(client):
    step("akasha: the canon for The Salt Road")
    for collection in ("characters", "locations"):
        client.post(f"{DOCS}/databases/{DB}/collections/{collection}")
    for slug, (title, role, body) in CHARACTERS.items():
        status, _ = client.upsert(
            f"{DOCS}/databases/{DB}/collections/characters/documents/{slug}",
            {"title": title, "role": role, "body": body},
        )
        show(status, f"characters/{slug}", title)
    for slug, (title, kind, body) in LOCATIONS.items():
        status, _ = client.upsert(
            f"{DOCS}/databases/{DB}/collections/locations/documents/{slug}",
            {"title": title, "type": kind, "body": body},
        )
        show(status, f"locations/{slug}", title)


def seed_book(client):
    step("chronos: the book")
    status, _ = client.upsert(f"{CHRONOS}/books/{BOOK}", {
        "title": "The Salt Road",
        "overview": (
            "Ninety wagons, ten people who each think the caravan is theirs, and "
            "one road to Tessel. Seeded to show the story map: the threads meet "
            "six times and walk alone in between."
        ),
        "calendars": [{
            "id": "imperial",
            "label": "Imperial Reckoning",
            "source": {"owner": USER, "calendar": CALENDAR_ID},
        }],
    })
    show(status, f"book '{BOOK}'")


def put_event(client, eid, title, location, start, end, characters, description):
    status, _ = client.upsert(f"{CHRONOS}/books/{BOOK}/events/{eid}", {
        "title": title,
        "location": ref("locations", location),
        "characters": [ref("characters", c) for c in characters],
        "items": [],
        "description": description,
        "start_tick": start,
        "end_tick": end,
    })
    return status


def seed_junctions(client):
    """The scenes more than one thread passes through -- the map's whole subject."""
    step("chronos: the six shared scenes")
    for eid, (title, location, tick) in JUNCTIONS.items():
        cast = [t[2] for t in THREADS if eid in (t[4], t[5])]
        status = put_event(
            client, eid, title, location, tick, tick + 8, cast,
            f"{len(cast)} threads of the caravan's story pass through this scene.",
        )
        show(status, f"event {eid}", f"{len(cast)} threads, tick {tick}")

    cast = [t[2] for t in THREADS]
    status = put_event(
        client, TERMINUS, "The Reckoning", "tessel", 2000, 2024, cast,
        "In Tessel the charter is read out, and every thread of this story ends here.",
    )
    show(status, f"event {TERMINUS}", "the terminus — all ten threads")


def solo_events(thread):
    """This thread's scenes between the junctions, as (id, title, tick, text)."""
    pid, _title, char, home, first, second = thread
    name = CHARACTERS[char][0].split()[0]
    t1 = JUNCTIONS[first][2]
    t2 = JUNCTIONS[second][2]
    out = []

    def add(kind, index, template, offset):
        title, body = template
        out.append((
            f"{pid}-{kind}-{index}",
            title.format(name=name),
            offset,
            body.format(name=name),
            home,
        ))

    # Before the first junction, between the two, and after the second -- placed
    # in the gaps so every thread stays in tick order and nobody is ever in two
    # places at once.
    for i, template in enumerate(SOLO_BEFORE):
        add("a", i, template, t1 - 80 + i * 20)
    for i, template in enumerate(SOLO_BETWEEN):
        add("b", i, template, t1 + 20 + i * 20)
    for i, template in enumerate(SOLO_AFTER):
        add("c", i, template, t2 + 20 + i * 20)
    return out


def seed_threads(client):
    step("chronos: ten threads, each walking alone between the junctions")
    for thread in THREADS:
        pid, title, char, _home, first, second = thread
        solo = solo_events(thread)
        for eid, ev_title, tick, body, location in solo:
            put_event(client, eid, ev_title, location, tick, tick + 8, [char], body)

        before = [e[0] for e in solo if "-a-" in e[0]]
        between = [e[0] for e in solo if "-b-" in e[0]]
        after = [e[0] for e in solo if "-c-" in e[0]]
        events = [*before, first, *between, second, *after, TERMINUS]

        # One goal per thread, created before the thread that serves it: a
        # plotline may only name goals the book has. Each is achieved at the
        # terminus every thread reaches, so the map's ten threads add ten
        # sound goals rather than ten findings.
        goal_id = f"{pid}-arrives"
        who = CHARACTERS[char][0].split()[0]
        status, _ = client.upsert(f"{CHRONOS}/books/{BOOK}/goals/{goal_id}", {
            "title": f"Get {who} to Tessel",
            "achieved_at": TERMINUS,
        })
        show(status, f"goal {goal_id}")

        status, result = client.upsert(f"{CHRONOS}/books/{BOOK}/plotlines/{pid}", {
            "title": title,
            "goals": [goal_id],
            "events": events,
        })
        detail = ""
        if status < 400:
            state = result["status"]
            detail = (f"{len(events)} scenes, ordering={state['ordering']['state']}, "
                      f"ends_at_terminus={state['ends_at_terminus']['state']}")
        show(status, f"plotline {pid}", detail)

    status, _ = client.post(f"{CHRONOS}/books/{BOOK}/terminus/{TERMINUS}")
    show(status, f"terminus = {TERMINUS}")


def seed_calendar(client):
    step("chronos: the calendar, in the library")
    status, _ = client.upsert(f"{CHRONOS}/calendars/{USER}/{CALENDAR_ID}", {
        "name": "Imperial Reckoning",
        "descriptor": CALENDAR,
        "notes": "Hours, days, months, years, counted from the Founding (AF).",
    })
    show(status, f"calendar '{USER}/{CALENDAR_ID}'")


def report(client):
    step("what the map has to work with")
    _, graph = client.get(f"{CHRONOS}/books/{BOOK}/graph")
    if not graph or "plotlines" not in graph:
        print("  could not read the graph")
        return
    lanes = graph["plotlines"]
    shared = [n for n in graph["nodes"]
              if sum(n["id"] in p["effective_events"] for p in lanes) > 1]
    print(f"  threads: {len(lanes)}   scenes: {len(graph['nodes'])}   "
          f"shared scenes: {len(shared)}")
    print(f"  book order (what the map re-orders): {', '.join(p['id'] for p in lanes)}")

    _, status = client.get(f"{CHRONOS}/books/{BOOK}")
    print(f"  book status: {(status or {}).get('status', '?').upper()}")

    step("what to try")
    print(f"  {CHRONOS}/#/{BOOK}/~map")
    print("      every thread at once — most rows folded into solitary stretches")
    print(f"  {CHRONOS}/#/{BOOK}/~map/the-assayer,the-widow,the-boy")
    print("      three threads that meet twice — a link you can share")
    print(f"  {CHRONOS}/#/{BOOK}/the-cipher/connected")
    print("      the old connected-plots link, which now lands on the map")


def main():
    client = Client()
    login(client)
    seed_canon(client)
    seed_calendar(client)
    seed_book(client)
    seed_junctions(client)
    seed_threads(client)
    report(client)
    print(f"\nExplore: {CHRONOS}/#/{BOOK}/~map")


if __name__ == "__main__":
    sys.exit(main())
