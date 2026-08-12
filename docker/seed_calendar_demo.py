"""Seed the calendar-library scenario on top of ``seed_demo.py``.

Run ``python docker/seed_demo.py`` first — this builds on the book it creates.

What it sets up, over the real HTTP APIs:

- **mara** keeps a library calendar, ``mara/imperial``, and *The Ember Pact*
  attaches a copy of it (with provenance, so the link is recoverable).
- A **second, parallel reckoning** — the Elvish Count — is attached to the same
  book. It ends partway through the story, which is the case the era bounds
  exist for: past that tick it declines to date scenes rather than inventing
  years for a culture that no longer existed to count them.
- mara then **edits the library copy**, so the book's copy is now one revision
  behind: the **drift** a reader can be offered an explicit update for.
- **huyhang** is registered, and mara shares both the **book** (editor) and the
  **calendar** (reader) with them.

The point of the arrangement is what it lets you check by hand:

1. huyhang reads the book's dates immediately — the labels are the book's own
   copy, so no grant on the library entry is involved.
2. huyhang *also* sees ``mara/imperial`` in their own library, because it was
   shared separately. Those are two different things, and the demo shows it.
3. The book's ``source.rev`` is behind the library's ``rev``. Nothing has been
   re-dated: the drift is reported, never applied.

Usage (from the repo root, stack already up and seeded):
    python docker/seed_calendar_demo.py

Re-running is safe: it updates rather than duplicates.
"""

import json
import os
import sys
import urllib.error
import urllib.request

AKASHA = os.environ.get("AKASHA_BASE", "http://localhost:5002")
CHRONOS = os.environ.get("CHRONOS_BASE", "http://localhost:5002/timeline")

OWNER = "mara"
OWNER_PASSWORD = "ember-pact-demo"
GUEST = "huyhang"
GUEST_PASSWORD = "huyhang-demo"
GUEST_EMAIL = "huyhang@example.com"

BOOK = "ember-pact"
CALENDAR = "imperial"

# What the seeded book already counts in: hours, 24 to a day, 30 days to a
# month, 12 months to a year. The library entry starts as a copy of it, so the
# attachment changes no label on day one -- the drift is the interesting part,
# and it should be the *only* thing that moves.
IMPERIAL = {
    "base_unit": "hour",
    "cycles": [
        {"name": "day", "size": 24},
        {"name": "month", "size": 30},
        {"name": "year", "size": 12},
    ],
    "epoch_label": "AF",
}

# The edit that creates the drift: the writer decides the Imperial calendar has
# six-day weeks after all. Every label gains a component, which is exactly why
# it must not be applied to a finished book behind the writer's back.
IMPERIAL_REVISED = {
    "base_unit": "hour",
    "cycles": [
        {"name": "day", "size": 24},
        {"name": "week", "size": 6},
        {"name": "month", "size": 5},
        {"name": "year", "size": 12},
    ],
    "epoch_label": "AF",
}

# The reckoning of a culture that does not survive the book. Ten-bell spans,
# eight spans to a moon.
ELVISH = {
    "base_unit": "bell",
    "cycles": [{"name": "span", "size": 10}, {"name": "moon", "size": 8}],
    "epoch_label": "SR",
}
# The tick the elves stop counting at, chosen to fall *inside* the seeded story
# rather than past the end of it: with the demo's scenes clustered at 0-200,
# ending here leaves roughly half the book dated in Elvish and the rest -- the
# coronation included -- reading "after Elvish Count". An end past the last
# scene would be just as correct and would demonstrate nothing.
ELVISH_ENDS = 120


class Session:
    """A logged-in browser, near enough: one cookie, carried on every call."""

    def __init__(self, base):
        self.base = base
        self.cookie = None

    def call(self, method, path, body=None, headers=None):
        url = path if path.startswith("http") else self.base + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(request) as response:
                if response.headers.get("Set-Cookie"):
                    self.cookie = response.headers["Set-Cookie"].split(";")[0]
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                return err.code, (json.loads(raw) if raw else None)
            except json.JSONDecodeError:
                return err.code, None
        except urllib.error.URLError as err:
            sys.exit(f"Cannot reach {url}: {err.reason}. Is the stack up?")


def log(status, what):
    mark = "ok " if status < 400 else "!! "
    print(f"  [{mark}] {status}  {what}")


def main():
    print("=== the calendar library scenario ===\n")

    mara = Session(AKASHA)
    status, _ = mara.call("POST", "/login", {"username": OWNER, "password": OWNER_PASSWORD})
    if status != 200:
        sys.exit(f"Could not log in as {OWNER} ({status}). Run docker/seed_demo.py first.")
    log(status, f"logged in as {OWNER}")

    status, book = mara.call("GET", f"{CHRONOS}/books/{BOOK}")
    if status != 200:
        sys.exit(f"No book '{BOOK}' ({status}). Run docker/seed_demo.py first.")

    # 1. the library entry -------------------------------------------------
    path = f"{CHRONOS}/calendars/{OWNER}/{CALENDAR}"
    body = {
        "name": "Imperial Reckoning",
        "descriptor": IMPERIAL,
        "notes": "Kept in the capital from the Founding. The calendar the Pact is dated in.",
    }
    status, entry = mara.call("POST", path, body)
    if status == 409:
        # Already there -- from seed_demo.py, which now builds the library entry
        # the book attaches, or from a previous run of this script. Left exactly
        # as it is when the content already matches: rewriting it would bump the
        # revision on every run and the drift below would read 6 -> 7 instead of
        # the 1 -> 2 the demo is trying to show.
        status, entry = mara.call("GET", path)
        if entry.get("descriptor") != IMPERIAL:
            status, entry = mara.call("PUT", path, body, {"If-Match": str(entry["rev"])})
    log(status, f"library calendar {OWNER}/{CALENDAR} -- rev {entry['rev']}")

    # 2. the second reckoning, also a library calendar ----------------------
    elvish_path = f"{CHRONOS}/calendars/{OWNER}/elvish"
    elvish_body = {
        "name": "Elvish Count",
        "descriptor": ELVISH,
        "notes": f"Kept by the elves until the fall at tick {ELVISH_ENDS}. "
                 "Nobody counted in it after, so it declines to date what came later.",
    }
    status, elvish = mara.call("POST", elvish_path, elvish_body)
    if status == 409:
        status, elvish = mara.call("GET", elvish_path)
    log(status, f"library calendar {OWNER}/elvish -- rev {elvish['rev']}")

    # 3. attach both. A book *names* a calendar; the server copies the
    #    descriptor in. The era is the book's own business, so it rides on the
    #    attachment rather than on the library entry.
    attached = [
        {
            "id": "imperial",
            "label": "Imperial Reckoning",
            "source": {"owner": OWNER, "calendar": CALENDAR},
        },
        {
            "id": "elvish",
            "label": "Elvish Count",
            "source": {"owner": OWNER, "calendar": "elvish"},
            "until_tick": ELVISH_ENDS,
        },
    ]
    status, book = mara.call(
        "PUT", f"{CHRONOS}/books/{BOOK}",
        {
            "title": book.get("title"),
            "overview": book.get("overview", ""),
            "terminus": book.get("terminus"),
            "world": book.get("world"),
            "calendars": attached,
        },
        {"If-Match": str(book["rev"])},
    )
    log(status, "book now keeps two reckonings: imperial (primary), elvish (ends "
                f"at tick {ELVISH_ENDS})")

    # 4. drift: the library moves on, the book does not ----------------------
    status, entry = mara.call(
        "PUT", path,
        {
            "name": "Imperial Reckoning",
            "descriptor": IMPERIAL_REVISED,
            "notes": "Revised: the capital counts six-day weeks, five weeks to a month.",
        },
        {"If-Match": str(entry["rev"])},
    )
    log(status, f"library calendar edited -- now rev {entry['rev']}")

    # 5. the guest -----------------------------------------------------------
    guest = Session(AKASHA)
    status, _ = guest.call("POST", "/register", {
        "username": GUEST, "password": GUEST_PASSWORD, "email": GUEST_EMAIL,
    })
    if status in (200, 201):
        log(status, f"registered {GUEST}")
    else:
        status, _ = guest.call("POST", "/login", {
            "username": GUEST, "password": GUEST_PASSWORD,
        })
        log(status, f"{GUEST} already existed -- logged in")

    # 6. mara shares both, separately ----------------------------------------
    status, _ = mara.call(
        "PUT", f"{CHRONOS}/books/{BOOK}/collaborators/{GUEST}", {"role": "editor"})
    log(status, f"book '{BOOK}' shared with {GUEST} as editor")
    status, _ = mara.call(
        "PUT", f"{CHRONOS}/calendars/{OWNER}/{CALENDAR}/collaborators/{GUEST}",
        {"role": "reader"})
    log(status, f"calendar '{OWNER}/{CALENDAR}' shared with {GUEST} as reader")

    report(guest, entry)


def report(guest, entry):
    """What huyhang now sees. This is the part worth reading."""
    status, _ = guest.call("POST", "/login",
                           {"username": GUEST, "password": GUEST_PASSWORD})
    if status != 200:
        # 429 is the usual one: the login limiter counts every run. Said plainly
        # here, because the alternative is a KeyError three lines down that
        # blames the data rather than the throttle.
        sys.exit(f"Could not log in as {GUEST} ({status})"
                 + (" -- rate limited; wait a minute and re-run." if status == 429 else "."))
    status, book = guest.call("GET", f"{CHRONOS}/books/{BOOK}")
    if status != 200 or not book.get("calendars"):
        sys.exit(f"Could not read the book as {GUEST} ({status}).")
    _, library = guest.call("GET", f"{CHRONOS}/calendars")
    imperial = next(c for c in book["calendars"] if c["id"] == "imperial")

    print(f"\n=== what {GUEST} sees ===\n")
    print(f"  the book's reckonings: "
          f"{', '.join(c['label'] for c in book['calendars'])}")
    print(f"  their library:         "
          f"{', '.join(c['qualified_id'] for c in library['calendars']) or '(empty)'}")

    print("\n  the drift:")
    print(f"    the book copied {imperial['source']['owner']}/"
          f"{imperial['source']['calendar']} at rev {imperial['source']['rev']}")
    print(f"    the library entry is now at rev {entry['rev']}")
    print(f"    the book's copy still has "
          f"{len(imperial['descriptor']['cycles'])} cycles; the library version has "
          f"{len(entry['descriptor']['cycles'])}")
    print("    -> nothing has been re-dated. The book is offered the update; it")
    print("       is not applied behind anyone's back.")

    print("\n  the same scenes, dated two ways:")
    for calendar in ("imperial", "elvish"):
        _, page = guest.call(
            "GET", f"{CHRONOS}/books/{BOOK}/events?calendar={calendar}&per_page=4")
        print(f"    through {calendar:9}", end="")
        for event in page["events"][:4]:
            print(f"\n      {event['title'][:34]:<34} {event['when']}", end="")
        print()

    _, late = guest.call(
        "GET", f"{CHRONOS}/books/{BOOK}/events?calendar=elvish&per_page=40")
    rows = [e for e in late["events"] if e["scheduled"]]
    after = [e for e in rows if e["when"].startswith("after")]
    # A scene that begins while the elves were still counting and ends after
    # they stopped. The most telling row in the demo: the bound is applied per
    # tick, not per scene, so one interval can be half-dated.
    straddling = [e for e in rows if "→ after" in e["when"]]
    dated = [e for e in rows if e not in after and e not in straddling]

    print(f"\n  the Elvish Count ended at tick {ELVISH_ENDS}, and says so:")
    for event in dated[:2]:
        print(f"    {event['title'][:32]:<32} {event['when']}")
    if len(dated) > 2:
        print(f"    …and {len(dated) - 2} more, dated normally")
    for event in straddling:
        print(f"    {event['title'][:32]:<32} {event['when']}")
        print("      ^ begins inside the era and ends outside it")
    for event in after[:3]:
        print(f"    {event['title'][:32]:<32} {event['when']}")
    if len(after) > 3:
        print(f"    …and {len(after) - 3} more, all past the end")
    print(f"\n    {len(dated)} dated, {len(straddling)} half-dated, {len(after)} past the end.")
    print("    No invented years for a culture that was gone -- and every one of")
    print("    those scenes still reads normally through the Imperial Reckoning.")

    print(f"\n=== log in as {GUEST} / {GUEST_PASSWORD} ===")
    print(f"  the book:     {CHRONOS}/#/{BOOK}")
    print(f"  its scenes:   {CHRONOS}/#/{BOOK}/~scenes   (switcher, top right)")
    print(f"  the library:  {CHRONOS}/#/~calendars")


if __name__ == "__main__":
    main()
