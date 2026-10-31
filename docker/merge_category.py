"""Fold one Akasha category into another in the same world. Run once, by hand.

Akasha used to make ``Characters`` beside ``characters`` -- MongoDB names are
case-sensitive -- and a world that has both has its cast split between two
categories that read the same. This moves every article of the first into the
second and leaves nothing pointing at the old name:

- **Articles** move with their version history and their tombstones, under the
  same ids. An id taken in both is not merged: the run stops and lists it, for
  a human to rename one of the two first.
- **Links.** ``[[Characters/aldric]]`` in the world, and
  ``[[world/Characters/aldric]]`` anywhere, are rewritten -- in every article's
  current text and in its retained history, so restoring an old version does
  not bring back a link to a category that is gone. A bare ``[[aldric]]``
  needs nothing: it moves with its neighbours.
- **Sharing.** Whoever could open a moved article keeps exactly that access to
  it. A grant on one article follows it. Where the old category gave someone
  something the new one does not, they get that on each moved article --
  never the new category as a whole, which would open articles nobody shared
  with them. The one thing a merge cannot keep is a door *closed*: grants only
  allow, so someone who can read the new category but not the old one will
  see the moved articles. The run lists each such person before anything is
  written.

Chronos scenes, Prithvi pins and Logos -- its prose, and the articles linked
to a section -- can name an article too. This
script does not rewrite those: it looks, and if any of them points into the
old category it stops and says where, rather than leave them dangling.

MongoDB is not published to the host, so run it inside the app container, and
take a backup first (``docker/backup.sh``):

    docker exec -i visualizer-app-1 python - WORLD FROM INTO < docker/merge_category.py
    docker exec -i visualizer-app-1 python - WORLD FROM INTO --apply < docker/merge_category.py

e.g. ``ember-pact Characters characters``. Without ``--apply`` it only says
what it would do. Run it while nobody is editing: an article saved from a page
opened before the move would write the old links back. If it is interrupted,
run it again -- every step picks up where it stopped.
"""

import re
import sys

from visualizer.akasha.config import get_mongo_client
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.auth.authz import DATABASE_RESOURCE, effective_perms, role_for_perms
from visualizer.chronos.store import CHRONOS_DB
from visualizer.logos.richtext import REFERENCE_TYPES
from visualizer.logos.store import DRAFT_REVISIONS, LOGOS_DB, SECTION_REVISIONS
from visualizer.prithvi.store import PINS, PRITHVI_DB

# ``list_database_names`` includes MongoDB's own; they are not Akasha's.
MONGO_SYSTEM = frozenset({"admin", "config", "local"})

# The same token the editor renders (static/js/wikitext.js), read the same way
# (static/js/links.js): "db/col/id", "col/id" or "id", then an optional "|label".
_LINK = re.compile(r"\[\[([^\]]+)\]\]")


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    names = [a for a in argv if a != "--apply"]
    if len(names) != 3:
        print(__doc__)
        return 2
    world, source, target = names
    report = merge(get_mongo_client(), world, source, target, apply=apply)
    for line in report.lines:
        print(line)
    if report.blocked:
        print("\nnothing written: settle the above first.")
        return 1
    if not apply:
        print("\nnothing written. Re-run with --apply to merge.")
    return 0


class Report:
    def __init__(self):
        self.lines: list[str] = []
        self.blocked = False

    def say(self, line: str) -> None:
        self.lines.append(line)

    def stop(self, line: str) -> None:
        self.lines.append(line)
        self.blocked = True


def merge(client, world: str, source: str, target: str, *, apply: bool) -> Report:
    """Move ``source`` into ``target`` in ``world``; what it did, or would do."""
    report = Report()
    documents = DocumentStore(client)
    auth = AuthStore(client)

    if source == target:
        report.stop(f"??    '{source}' and '{target}' are the same category")
        return report
    if world not in documents.list_databases():
        report.stop(f"??    there is no world '{world}'")
        return report
    collections = documents.list_collections(world)
    if source not in collections:
        report.stop(f"??    '{world}' has no category '{source}' -- nothing to merge")
        return report
    if target not in collections:
        report.stop(f"??    '{world}' has no category '{target}' to merge into")
        return report

    moving = list(client[world][source].find())
    into = client[world][target]
    landed = []
    for doc in moving:
        there = into.find_one({"_id": doc["_id"]})
        if there is None:
            continue
        if there == relinked(doc, world, world, source, target):
            landed.append(doc["_id"])     # a run that stopped half way moved it
        else:
            report.stop(f"??    '{doc['_id']}' is in both '{source}' and '{target}'; rename one")
    for place in _references_elsewhere(client, world, source):
        report.stop(f"??    {place} names an article in '{source}'; change it first")
    if report.blocked:
        return report

    ids = [doc["_id"] for doc in moving]
    retired = _merge_grants(auth, world, source, target, ids, report, apply)

    verb = "moved" if apply else "would move"
    for doc in moving:
        if apply:
            if doc["_id"] not in landed:
                into.insert_one(relinked(doc, world, world, source, target))
            gone = client[world][source].delete_one({"_id": doc["_id"], "_rev": doc.get("_rev")})
            if gone.deleted_count == 0:
                # Saved since it was read: the copy just made is stale, and
                # leaving it would make the next run see the id in both.
                into.delete_one({"_id": doc["_id"], "_rev": doc.get("_rev")})
                report.stop(f"??    '{doc['_id']}' changed during the run; run it again")
                return report
        state = "deleted article" if doc.get("_deleted") else "article"
        report.say(_line(apply, f"{state} '{doc['_id']}' {verb} to '{target}'"))

    _relink_everywhere(client, world, source, target, report, apply)

    if apply:
        if report.blocked:
            return report
        for grant_id in retired:
            auth.delete_grant(grant_id)
        documents.delete_collection(world, source)
        report.say(f"ok    '{source}' removed from '{world}'")
    else:
        report.say(f"--    '{source}' would be removed from '{world}'")
    return report


# -- links -------------------------------------------------------------------


def relink(text: str, home: str, world: str, source: str, target: str) -> str:
    """``text`` with every link into ``world/source`` pointed at ``target``.

    ``home`` is the world of the article the text belongs to, which is what a
    two-part ``[[col/id]]`` is read against.
    """

    def swap(match):
        address, bar, label = match.group(1).partition("|")
        parts = [part.strip() for part in address.split("/") if part.strip()]
        if len(parts) >= 3 and parts[0] == world and parts[1] == source:
            parts[1] = target
        elif len(parts) == 2 and home == world and parts[0] == source:
            parts[0] = target
        else:
            return match.group(0)
        return "[[" + "/".join(parts) + bar + label + "]]"

    return _LINK.sub(swap, text)


def relinked(doc: dict, home: str, world: str, source: str, target: str) -> dict:
    """A stored article with its links rewritten, history included."""

    def fix(value):
        if isinstance(value, str):
            return relink(value, home, world, source, target)
        if isinstance(value, list):
            return [fix(item) for item in value]
        return value

    def fields(body: dict) -> dict:
        return {k: (v if k.startswith("_") else fix(v)) for k, v in body.items()}

    out = fields(doc)
    if "_history" in doc:
        out["_history"] = [
            {**snap, "document": fields(snap["document"])} if snap.get("document") else snap
            for snap in doc["_history"]
        ]
    return out


def _relink_everywhere(client, world, source, target, report, apply) -> None:
    """Rewrite links in every article of every world, not only the moved ones."""
    verb = "rewrote" if apply else "would rewrite"
    for database in sorted(client.list_database_names()):
        if database.startswith("_") or database in MONGO_SYSTEM:
            continue
        for collection in sorted(client[database].list_collection_names()):
            if collection.startswith("system.") or (database, collection) == (world, source):
                continue
            for doc in client[database][collection].find():
                fixed = relinked(doc, database, world, source, target)
                if fixed == doc:
                    continue
                if apply:
                    done = client[database][collection].replace_one(
                        {"_id": doc["_id"], "_rev": doc.get("_rev")}, fixed
                    )
                    if done.matched_count == 0:
                        report.stop(
                            f"??    '{database}/{collection}/{doc['_id']}' changed "
                            f"during the run; run it again"
                        )
                        continue
                report.say(_line(apply, f"{verb} links in '{database}/{collection}/{doc['_id']}'"))


# -- sharing -----------------------------------------------------------------


def _merge_grants(auth, world, source, target, ids, report, apply) -> list[str]:
    """Give everyone the access to the moved articles they had before.

    Returns the grants on ``source`` to delete once the articles have moved --
    not before, so a run that stops half way still knows what each one gave.
    """
    grants = [
        g for g in auth.all_grants()
        if g["resource_type"] == DATABASE_RESOURCE and g["database"] in (world, None)
    ]
    retired = []
    for who in sorted({g["username"] for g in grants}):
        theirs = [g for g in grants if g["username"] == who]
        on_source = [
            g for g in theirs if g["database"] == world and g["collection"] == source
        ]
        rest = [g for g in theirs if g not in on_source]
        # An article with a grant of its own is governed by that one: it follows.
        own = set()
        for grant in on_source:
            if grant["doc_id"] is not None:
                own.add(grant["doc_id"])
                _ensure(auth, who, world, target, grant["doc_id"], grant["perms"],
                        grant["granted_by"], apply)
                report.say(_line(apply, f"{who}'s grant on '{grant['doc_id']}' follows it"))
        # The rest were governed by whatever reached the category as a whole.
        before = effective_perms(theirs, world, source, None)
        after = effective_perms(rest, world, target, None)
        others = [doc_id for doc_id in ids if doc_id not in own]
        if before != after and others:
            if before:
                by = next((g["granted_by"] for g in on_source if g["doc_id"] is None), None)
                for doc_id in others:
                    _ensure(auth, who, world, target, doc_id, sorted(before), by, apply)
                report.say(_line(
                    apply, f"{who} keeps {role_for_perms(before)} on the {len(others)} "
                    f"moved articles ('{target}' gives them "
                    f"{role_for_perms(after) if after else 'nothing'})",
                ))
            else:
                # Grants only ever allow, so nothing can keep these closed.
                report.say(
                    f"!!    {who} has no access to '{source}' but is "
                    f"{role_for_perms(after)} on '{target}': will see its "
                    f"{len(others)} moved articles"
                )
        retired += [g["id"] for g in on_source]
    return retired


def _ensure(auth, who, world, collection, doc_id, perms, granted_by, apply) -> None:
    """``who`` holds ``perms`` on ``world/collection/doc_id``, once."""
    if not apply:
        return
    if any(g["username"] == who for g in auth.grants_on(world, collection, doc_id)):
        auth.grant_owner(who, world, collection, doc_id, list(perms))
    else:
        auth.add_grant(who, world, collection, doc_id, list(perms), granted_by=granted_by or who)


def _line(apply: bool, text: str) -> str:
    return f"{'ok   ' if apply else '--   '} {text}"


# -- the other services ------------------------------------------------------


def _references_elsewhere(client, world, source) -> list[str]:
    """Where Chronos, Prithvi or Logos names an article in ``world/source``."""
    places = []
    for event in client[CHRONOS_DB]["events"].find():
        refs = [event.get("location"), *(event.get("characters") or []),
                *(event.get("items") or [])]
        if any(_points_at(ref, world, source) for ref in refs):
            places.append(f"Chronos scene '{event.get('id')}' in book '{event.get('book')}'")
    for pin in client[PRITHVI_DB][PINS].find(
        {"world": world, "collection": source, "deleted": False}
    ):
        places.append(f"Prithvi pin for '{pin['article_id']}' on map '{pin['map']}'")
    seen = set()
    for name in (SECTION_REVISIONS, DRAFT_REVISIONS):
        for revision in client[LOGOS_DB][name].find():
            where = (revision.get("book"), revision.get("section"))
            body = revision.get("body") or {}
            linked = body.get("articles") or [] if isinstance(body, dict) else []
            if where not in seen and (
                _mentions(body, world, source)
                or any(_points_at(ref, world, source) for ref in linked)
            ):
                seen.add(where)
                places.append(f"Logos section '{where[1]}' in book '{where[0]}'")
    return places


def _points_at(ref, world, source) -> bool:
    return isinstance(ref, dict) and ref.get("database") == world and ref.get("collection") == source


def _mentions(node, world, source) -> bool:
    if isinstance(node, dict):
        if node.get("type") in REFERENCE_TYPES and _points_at(node.get("ref"), world, source):
            return True
        return any(_mentions(v, world, source) for v in node.values())
    if isinstance(node, list):
        return any(_mentions(v, world, source) for v in node)
    return False


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
