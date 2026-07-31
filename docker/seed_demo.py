"""Seed the running stack with a small demo story that has real problems in it.

Creates, over the real HTTP APIs (no direct DB writes):

- document-server: the canon -- characters, items, locations as articles.
- chronos: the book "The Ember Pact" with a fictional calendar, six events, and
  four plotlines.

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

Re-running is safe: existing records are updated rather than duplicated.
"""

import json
import sys
import urllib.error
import urllib.request

DOCS = "http://localhost:5002"
CHRONOS = "http://localhost:5003"

USER = "mara"
PASSWORD = "ember-pact-demo"
EMAIL = "mara@example.com"

DB = "ember-pact"
BOOK = "ember-pact"

CALENDAR = {
    "base_unit": "hour",
    "cycles": [
        {"name": "day", "size": 24},
        {"name": "month", "size": 30},
        {"name": "year", "size": 12},
    ],
    "epoch_label": "AF",
}

CHARACTERS = {
    "aldric": "Sir Aldric",
    "lyra": "Lyra Vane",
    "corwin": "Magister Corwin",
}
ITEMS = {"ember-seal": "The Ember Seal"}
LOCATIONS = {
    "highkeep": "Highkeep",
    "emberport": "Emberport",
    "throne-hall": "The Throne Hall",
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

SOUND_PLOTLINES = [
    ("knights-road", "The Knight's Road",
     ["Deliver the Ember Seal", "Reach the coronation alive"],
     ["aldric-departs", "meet-at-emberport", "the-coronation"]),
    ("spys-shadow", "The Spy's Shadow", ["Expose the traitor"],
     ["lyra-infiltrates", "meet-at-emberport", "the-coronation"]),
    ("magisters-gambit", "The Magister's Gambit", ["Contest the succession"],
     ["corwin-plots", "the-coronation"]),
]

# Out of order (hour 48-72 listed before hour 10-30) AND stops short of the
# terminus -- two more findings on top of the temporal conflict.
WITNESS_BROKEN = ("witness-tale", "The Witness's Tale", ["Establish who was where"],
                  ["meet-at-emberport", "aldric-at-emberport"])
WITNESS_FIXED = (*WITNESS_BROKEN[:3],
                 ["aldric-at-emberport", "meet-at-emberport", "the-coronation"])

TERMINUS = "the-coronation"


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
    return eid, {
        "title": title,
        "location": ref("locations", loc),
        "start_tick": start,
        "end_tick": end,
        "characters": [ref("characters", c) for c in chars],
        "items": [ref("items", i) for i in items],
        "description": desc,
    }


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
    show(status, "login to document-server")
    if status != 200:
        sys.exit("login failed -- cannot seed")
    status, _ = client.get(f"{CHRONOS}/books")
    show(status, "same session accepted by chronos")


def seed_entities(client):
    step("document-server: the canon (entities chronos will reference)")
    for collection, entries in (
        ("characters", CHARACTERS), ("items", ITEMS), ("locations", LOCATIONS)
    ):
        client.post(f"{DOCS}/databases/{DB}/collections/{collection}")
        for slug, title in entries.items():
            status, _ = client.upsert(
                f"{DOCS}/databases/{DB}/collections/{collection}/documents/{slug}",
                {"title": title},
            )
            show(status, f"{collection}/{slug}", title)


def seed_book_and_events(client):
    step("chronos: the book and its scenes")
    status, body = client.upsert(
        f"{CHRONOS}/books/{BOOK}", {"title": "The Ember Pact", "calendar": CALENDAR}
    )
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


def seed_plotlines(client, witness):
    step("chronos: plotlines")
    for pid, title, goals, evs in [*SOUND_PLOTLINES, witness]:
        status, body = client.upsert(
            f"{CHRONOS}/books/{BOOK}/plotlines/{pid}",
            {"title": title, "goals": goals, "events": evs},
        )
        ordering = body["status"]["ordering"]["state"] if status < 400 else "?"
        show(status, f"plotline {pid}", f"ordering={ordering}")
    status, _ = client.post(f"{CHRONOS}/books/{BOOK}/terminus/{TERMINUS}")
    show(status, f"terminus = {TERMINUS}")


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


def next_steps(fixed):
    step("what to try next")
    base = f"{CHRONOS}/books/{BOOK}"
    print(f"  curl -b cookies.txt {base}                      # one-glance status")
    print(f"  curl -b cookies.txt {base}/validate             # the full report")
    print(f"  curl -b cookies.txt {base}/graph                # how threads connect")
    print(f"  curl -b cookies.txt {base}/events/meet-at-emberport/plotlines")
    print(f"  curl -b cookies.txt {base}/plotlines/witness-tale?expand=events")
    if fixed:
        print("\n  Re-run without --fix to break it again.")
    else:
        print("\n  Run with --fix to repair all three problems and see it go green:")
        print("    python docker/seed_demo.py --fix")


def main():
    fix = "--fix" in sys.argv
    client = Client()
    login(client)
    seed_entities(client)
    seed_book_and_events(client)
    demo_hard_rule(client)
    seed_plotlines(client, WITNESS_BROKEN)

    if fix:
        step("repairing the story")
        eid, payload = event_payload(SIGHTING_FIXED)
        status, _ = client.put(f"{CHRONOS}/books/{BOOK}/events/{eid}", payload)
        show(status, "moved the sighting to hours 30-40 (no longer overlaps the ride)")
        pid, title, goals, evs = WITNESS_FIXED
        status, _ = client.put(f"{CHRONOS}/books/{BOOK}/plotlines/{pid}",
                               {"title": title, "goals": goals, "events": evs})
        show(status, "reordered the witness thread and carried it to the terminus")

    report(client)
    next_steps(fix)
    print(f"\nExplore: {CHRONOS}/books/{BOOK}   |   articles UI: {DOCS}/")


if __name__ == "__main__":
    main()
