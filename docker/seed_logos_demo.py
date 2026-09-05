"""Write the Ember Pact as a novel, over the real HTTP API.

Run ``python docker/seed_demo.py`` first. This hangs a manuscript off the book
that script creates and writes it from the scenes already on that timeline; it
invents neither, and says so rather than guessing if either is missing.

What it produces is a small but complete two-volume series, so the parts of
Logos that only show up at scale are actually visible:

* **Two volumes**, because a Chronos book is a *series* -- chapter numbering
  restarts in volume two, and both are numbered from their place in the outline.
* **Every section kind**: a prologue and an epilogue that stay unnumbered while
  the chapters between them number 1, 2, 3, 4, and a glossary built as a list.
* **Every chapter attached to a real scene**, including the disputed sighting
  that ``seed_demo.py`` deliberately leaves in conflict -- so the manuscript has
  prose written from a scene the timeline itself flags.
* **Prose that mentions the canon**: characters, the Seal and the three
  locations, as soft references. Delete one of those articles in Akasha and the
  report here lists the chapters that mention it, without touching the prose.
* **Private reader data for Mara**: paragraph notes, bookmarks, series
  checklists, and section checklists in both volumes, ready to inspect in Full
  view.

Usage (from the repo root, stack already up and seeded):
    python docker/seed_logos_demo.py

Re-running is safe, and is itself the demonstration: every write names the
revision it replaces, because Logos -- unlike its siblings -- refuses an
unconditional write to prose.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

AKASHA = os.environ.get("AKASHA_BASE", "http://localhost:5002")
CHRONOS = os.environ.get("CHRONOS_BASE", "http://localhost:5002/timeline")
LOGOS = os.environ.get("LOGOS_BASE", "http://localhost:5002/logos")

USER = "mara"
PASSWORD = "ember-pact-demo"
BOOK = "ember-pact"
WORLD = "ember-pact"


# -- building blocks ---------------------------------------------------------


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def who(article, label):
    """A soft mention of a character in the canon."""
    return {
        "type": "mention",
        "ref": {"database": WORLD, "collection": "characters", "id": article},
        "text": label,
    }


def where(article, label):
    return {
        "type": "article_link",
        "ref": {"database": WORLD, "collection": "locations", "id": article},
        "text": label,
    }


def thing(article, label):
    return {
        "type": "article_link",
        "ref": {"database": WORLD, "collection": "items", "id": article},
        "text": label,
    }


def para(node_id, *nodes):
    return {"type": "paragraph", "id": node_id, "content": list(nodes)}


def heading(node_id, level, value):
    return {"type": "heading", "id": node_id, "level": level,
            "content": [text(value)]}


def terms(node_id, *entries):
    """A glossary, as a bullet list of term/definition pairs."""
    return {
        "type": "bullet_list",
        "id": node_id,
        "content": [
            {
                "type": "list_item",
                "content": [text(term, "strong"), text(" — " + definition)],
            }
            for term, definition in entries
        ],
    }


def document(*blocks):
    return {"version": 1, "type": "doc", "content": list(blocks)}


def section(section_id, kind, title, overview, events, *blocks):
    return {
        "id": section_id,
        "body": {
            "kind": kind,
            "title": title,
            "overview": overview,
            "event_ids": list(events),
            "document": document(*blocks),
        },
    }


# -- the manuscript ----------------------------------------------------------

VOLUME_ONE = {
    "id": "the-ember-seal",
    "body": {
        "title": "The Ember Seal",
        "overview": "Volume one: the Seal leaves Highkeep and changes hands.",
    },
    "sections": [
        section(
            "before-the-pact", "prologue", "Before the Pact",
            "The bargain, three generations earlier.",
            (),
            para(
                "pro-1",
                text("The Ember was not given. It was "),
                text("bargained for", "em"),
                text(", and the price was left unnamed in the charter — which is "
                     "how a kingdom agrees to something it does not wish to read "
                     "aloud."),
            ),
            para(
                "pro-2",
                text("Three generations later the price had not been forgotten. "
                     "It had only stopped being anybody's turn to pay it."),
            ),
        ),
        section(
            "the-road-from-highkeep", "chapter", "The Road from Highkeep",
            "Aldric rides out before the succession is settled.",
            ("aldric-departs",),
            para(
                "c1-1",
                text("Winter came early to "),
                where("highkeep", "Highkeep"),
                text(" that year, and the road south was empty before dawn — "
                     "which suited the errand, since nobody had agreed it should "
                     "be made."),
            ),
            para(
                "c1-2",
                who("aldric", "Sir Aldric"),
                text(" rode out with "),
                thing("ember-seal", "the Ember Seal"),
                text(" against his ribs, wrapped twice in oilcloth. He had been "
                     "given no letter and no escort. Both omissions were "
                     "instructions."),
            ),
            para(
                "c1-3",
                text("Behind him the keep argued about the succession with the "
                     "doors shut. Ahead of him the road did not care who was "
                     "crowned. He preferred the road."),
            ),
        ),
        section(
            "a-berth-in-the-harbour", "chapter", "A Berth in the Harbour",
            "Lyra takes work on the quay to watch it.",
            ("lyra-infiltrates",),
            para(
                "c2-1",
                who("lyra", "Lyra Vane"),
                text(" took a dockhand's berth at "),
                where("emberport", "Emberport"),
                text(" for eleven copper a week, which was four less than the "
                     "work was worth and exactly what an unremarkable person "
                     "would accept."),
            ),
            para(
                "c2-2",
                text("The harbour told her things the keep never would. Who paid "
                     "in crown silver and who paid in foreign coin. Which "
                     "captains sailed light and swore they were loaded. Where a "
                     "man might stand for an hour without being asked his "
                     "business."),
            ),
            para(
                "c2-3",
                text("By the second week she had the shape of it. By the third "
                     "she had a name, and wished she did not."),
            ),
        ),
        section(
            "the-witness", "chapter", "The Witness",
            "An account that cannot be true. Written from the disputed sighting.",
            ("aldric-at-emberport",),
            para(
                "c3-1",
                text("A cooper's boy swore he saw the knight on the quay at the "
                     "turn of the tide, cloak and all, plain as the harbour "
                     "wall."),
            ),
            para(
                "c3-2",
                text("This was impossible. "),
                who("aldric", "Aldric"),
                text(" was two days' ride inland with the mountains still ahead "
                     "of him. The boy was neither lying nor mistaken about "
                     "having seen "),
                text("someone", "em"),
                text("."),
            ),
            para(
                "c3-3",
                text("Both facts were written down. Only one of them could be "
                     "kept, and nobody yet knew which."),
            ),
        ),
        section(
            "the-harbour-exchange", "chapter", "The Harbour Exchange",
            "The Seal changes hands beneath the market awnings.",
            ("meet-at-emberport",),
            para(
                "c4-1",
                text("They met under the awnings where the fish market backed on "
                     "to the rope-walk, because it was the one place in "),
                where("emberport", "Emberport"),
                text(" where two people could stand close and be assumed to be "
                     "haggling."),
            ),
            para(
                "c4-2",
                text("The oilcloth went from his hand to hers inside the space of "
                     "a sentence about the price of salt cod. Neither of them "
                     "looked down at it."),
            ),
            para(
                "c4-3",
                text("\"They will say you stole it,\" she said."),
            ),
            para(
                "c4-4",
                text("\"They will say you did,\" said "),
                who("aldric", "Aldric"),
                text(", "),
                text("\"which is better, because you are harder to find.\"", "em"),
            ),
        ),
        section(
            "what-the-tide-took", "epilogue", "What the Tide Took",
            "Closing the volume on the harbour.",
            (),
            para(
                "epi-1",
                text("The tide went out that night and took the oilcloth with it, "
                     "empty, which is the only part of the story everyone later "
                     "agreed on."),
            ),
        ),
    ],
}

VOLUME_TWO = {
    "id": "the-charter",
    "body": {
        "title": "The Charter",
        "overview": "Volume two: the writ, the hall, and what the Seal makes lawful.",
    },
    "sections": [
        section(
            "the-writ", "chapter", "The Writ",
            "Corwin drafts the contest from inside the keep.",
            ("corwin-plots",),
            para(
                "v2c1-1",
                who("corwin", "Magister Corwin"),
                text(" did not need the Seal. He needed the "),
                text("absence", "em"),
                text(" of it, for one afternoon, in front of the right people."),
            ),
            para(
                "v2c1-2",
                text("He drafted the writ in his own hand, three times, and burned "
                     "the first two — not because they were wrong but because "
                     "they were "),
                text("clever", "em"),
                text(", and a clever document invites a clever reply."),
            ),
            para(
                "v2c1-3",
                text("The third was merely correct. It was the most dangerous "
                     "thing he had ever written."),
            ),
        ),
        section(
            "the-throne-hall", "chapter", "The Throne Hall",
            "The crowning, and the charter.",
            ("the-coronation",),
            para(
                "v2c2-1",
                text("The realm crowned its heir on a grey morning in "),
                where("throne-hall", "the Throne Hall"),
                text(", with the doors open, which had not been done in living "
                     "memory and was itself an argument."),
            ),
            para(
                "v2c2-2",
                text("The writ was read. It was answered. Then "),
                thing("ember-seal", "the Ember Seal"),
                text(" was pressed to the charter, and the wax took, and the "
                     "thing was done."),
            ),
            para(
                "v2c2-3",
                text("Afterwards nobody could agree who had handed it up."),
            ),
        ),
        section(
            "names-and-terms", "glossary", "Names and Terms",
            "For readers coming to the series cold.",
            (),
            heading("g-h1", 2, "People, places and one object"),
            terms(
                "g-list",
                ("The Ember Seal",
                 ("the royal sigil that makes a succession lawful; without its "
                  "impression the charter is only ink")),
                ("Highkeep",
                 "the marcher fortress the Seal leaves at the start of volume one"),
                ("Emberport",
                 "the harbour town where the Seal changes hands"),
                ("The Throne Hall",
                 ("where the charter is sealed, and where every thread of the "
                  "series ends")),
                ("Magister",
                 "a scholar of law entitled to be heard at a crowning"),
            ),
        ),
    ],
}

VOLUMES = [VOLUME_ONE, VOLUME_TWO]

# Spread across every section of both volumes, so Full view has something to
# show wherever you land, and so the combinations worth eyeballing all appear:
# two notes on one section, a note and a bookmark on different paragraphs of the
# same section, a bookmark in each volume, and checklists at both scopes with
# some items already ticked.
READER_ITEMS = [
    {
        "kind": "note",
        "volume": "the-ember-seal",
        "section": "before-the-pact",
        "block": "pro-1",
        "text": "Echo the unnamed price when the charter returns in volume two.",
    },
    {
        "kind": "note",
        "volume": "the-ember-seal",
        "section": "a-berth-in-the-harbour",
        "block": "c2-3",
        "text": "The berth is paid for twice. Deliberate — Aldric is being watched.",
    },
    {
        "kind": "note",
        "volume": "the-ember-seal",
        "section": "the-witness",
        "block": "c3-2",
        "text": "Continuity check: resolve the impossible Emberport sighting later.",
    },
    {
        "kind": "note",
        "volume": "the-ember-seal",
        "section": "the-harbour-exchange",
        "block": "c4-1",
        "text": "Pacing: the handoff wants one fewer beat before the oilcloth passes.",
    },
    {
        "kind": "note",
        "volume": "the-ember-seal",
        "section": "the-harbour-exchange",
        "block": "c4-4",
        "text": "Second note on this chapter, so the panel shows more than one.",
    },
    {
        "kind": "note",
        "volume": "the-charter",
        "section": "the-writ",
        "block": "v2c1-2",
        "text": "Corwin's draft echoes the prologue charter language. Intentional.",
    },
    {
        "kind": "note",
        "volume": "the-charter",
        "section": "the-throne-hall",
        "block": "v2c2-2",
        "text": "Verify that the sealing action agrees with the established canon.",
    },
    {
        "kind": "bookmark",
        "volume": "the-ember-seal",
        "section": "the-road-from-highkeep",
        "block": "c1-2",
        "text": "Aldric leaves with the Seal",
    },
    {
        "kind": "bookmark",
        "volume": "the-ember-seal",
        "section": "the-harbour-exchange",
        "block": "c4-2",
        "text": "The handoff",
    },
    {
        "kind": "bookmark",
        "volume": "the-ember-seal",
        "section": "the-witness",
        "block": "c3-1",
        "text": "The cooper's boy speaks",
    },
    {
        "kind": "bookmark",
        "volume": "the-ember-seal",
        "section": "what-the-tide-took",
        "block": "epi-1",
        "text": "What the tide took",
    },
    {
        "kind": "bookmark",
        "volume": "the-charter",
        "section": "the-throne-hall",
        "block": "v2c2-2",
        "text": "The charter is sealed",
    },
    {
        "kind": "checklist",
        "scope": "book",
        "text": "Proofread the entire series before export.",
        "done": False,
    },
    {
        "kind": "checklist",
        "scope": "book",
        "text": "Export the EPUB and proof the title page.",
        "done": True,
    },
    {
        "kind": "checklist",
        "scope": "book",
        "text": "Confirm the volume titles and front matter for publication.",
        "done": True,
    },
    {
        "kind": "checklist",
        "scope": "section",
        "volume": "the-ember-seal",
        "section": "the-harbour-exchange",
        "text": "Tighten the exchange dialogue.",
        "done": False,
    },
    {
        "kind": "checklist",
        "scope": "section",
        "volume": "the-ember-seal",
        "section": "the-witness",
        "text": "Decide which account of the sighting survives.",
        "done": True,
    },
    {
        "kind": "checklist",
        "scope": "section",
        "volume": "the-ember-seal",
        "section": "the-witness",
        "text": "Reread the boy's voice against chapter one.",
        "done": False,
    },
    {
        "kind": "checklist",
        "scope": "section",
        "volume": "the-charter",
        "section": "names-and-terms",
        "text": "Verify every glossary term against the manuscript.",
        "done": False,
    },
]


# -- the wire ----------------------------------------------------------------


class Session:
    """A logged-in browser, near enough: one cookie jar, carried throughout."""

    def __init__(self):
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def call(self, method, url, body=None, headers=None):
        data = None
        request_headers = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in request_headers.items():
            request.add_header(key, value)
        try:
            with self._opener.open(request, timeout=20) as response:
                return response.status, _decode(response)
        except urllib.error.HTTPError as error:
            return error.code, _decode(error)


def _decode(response):
    body = response.read()
    if not body:
        return None
    if response.headers.get_content_type() == "application/json":
        return json.loads(body.decode())
    return body.decode(errors="replace")


def show(status, what, note=""):
    mark = "ok " if status < 400 else "!! "
    print(f"{mark}{status}  {what}{'  -- ' + note if note else ''}")


def put_or_create(session, url, body, what):
    """Create it, or -- if it is already there -- replace it at its current rev.

    Logos refuses a write that does not name the revision it replaces, so the
    update path has to read first. That is the point of the demo, not an
    inconvenience to be worked around.
    """
    status, created = session.call("POST", url, body)
    if status == 201:
        show(status, f"create {what}")
        return created
    if status != 409:
        show(status, f"create {what}", json.dumps(created))
        return None
    status, current = session.call("GET", url)
    if status != 200:
        show(status, f"read {what} before replacing it", json.dumps(current))
        return None
    status, updated = session.call(
        "PUT", url, body, headers={"If-Match": f'"{current["rev"]}"'}
    )
    show(status, f"replace {what} (was rev {current['rev']})")
    return updated if status == 200 else None


def write_volume(session, volume):
    base = f"{LOGOS}/books/{BOOK}/volumes/{volume['id']}"
    if put_or_create(session, base, volume["body"], f"volume '{volume['id']}'") is None:
        return False
    for entry in volume["sections"]:
        put_or_create(
            session,
            f"{base}/sections/{entry['id']}",
            entry["body"],
            f"  {entry['body']['kind']:9s} '{entry['id']}'",
        )
    return True


def seed_reader_items(session):
    """Add the demo account's private items once, without duplicating reruns."""
    url = f"{LOGOS}/books/{BOOK}/me/items"
    status, payload = session.call("GET", url)
    if status != 200:
        show(status, "read private reader items", json.dumps(payload))
        return False

    existing = payload["items"]
    for item in READER_ITEMS:
        label = f"{item['kind']} '{item['text']}'"
        if any(_item_matches(current, item) for current in existing):
            show(200, f"keep private {label}")
            continue
        status, created = session.call("POST", url, item)
        show(status, f"create private {label}")
        if status != 201:
            return False
        existing.append(created)
    return True


# What makes a seeded item "the same one" on a re-run. Deliberately not every
# field: `done` and a bookmark's label are yours to change, and a re-run that
# compared them would treat a ticked box as a missing item and seed a duplicate.
_ITEM_IDENTITY = {
    "note": ("kind", "volume", "section", "block", "text"),
    "bookmark": ("kind", "volume", "section", "block"),
    "checklist": ("kind", "scope", "volume", "section", "text"),
}


def _item_matches(current, expected):
    fields = _ITEM_IDENTITY[expected["kind"]]
    return all(current.get(field) == expected.get(field) for field in fields)


def main():
    session = Session()
    status, body = session.call(
        "POST", f"{AKASHA}/login", {"username": USER, "password": PASSWORD}
    )
    show(status, f"log in as {USER}")
    if status != 200:
        sys.exit(f"cannot log in -- run seed_demo.py first ({body})")

    status, _ = session.call("GET", f"{CHRONOS}/books/{BOOK}")
    if status != 200:
        sys.exit(f"no Chronos book '{BOOK}' -- run seed_demo.py first")
    show(status, f"found the Chronos book '{BOOK}'")

    for volume in VOLUMES:
        if not write_volume(session, volume):
            sys.exit(f"could not write volume '{volume['id']}'")

    if not seed_reader_items(session):
        sys.exit(f"could not write private reader items for '{USER}'")

    status, manuscript = session.call("GET", f"{LOGOS}/books/{BOOK}")
    if status == 200:
        print()
        for entry in manuscript["volumes"]:
            chapters = [s for s in entry["sections"] if s["kind"] == "chapter"]
            print(
                f"  volume {entry['number']}. {entry['title']} — "
                f"{len(chapters)} chapters, {entry['section_count']} sections, "
                f"{entry['word_count']} words"
            )
        print(f"  {manuscript['word_count']} words in the series")

    status, report = session.call("GET", f"{LOGOS}/books/{BOOK}/report")
    dangling = report["sections_with_missing_refs"] if status == 200 else []
    if dangling:
        print()
        print(f"  {len(dangling)} section(s) mention an article that is missing:")
        for row in dangling:
            names = ", ".join(ref["id"] for ref in row["missing_refs"])
            print(f"    {row['volume']}/{row['section']}: {names}")

    print()
    print(f"manuscript: {LOGOS}/books/{BOOK}")
    for volume in VOLUMES:
        print(f"read:       {LOGOS}/books/{BOOK}/volumes/{volume['id']}/manuscript")
    print(f"report:     {LOGOS}/books/{BOOK}/report")
    print(f"login:      {USER} / {PASSWORD}")


if __name__ == "__main__":
    main()
