"""Give existing worlds the owner they never had. Run once, after upgrading.

Creating a world's first collection now claims the world as well, but every
world made before that change has no owner: its collections do, and nobody holds
the scope above them. Until that is fixed those worlds cannot be shared, and
Prithvi will refuse to put a map in them.

The rule here is the most conservative reading of "you own what you made": a
world goes to the one writer who already holds ``delete`` on **every** category
in it. Where that is ambiguous -- two part-owners, or a world where nobody owns
everything -- nothing is written and the world is listed for a human to settle
in the admin console. Guessing at a whole canon's owner is not this script's
business.

MongoDB is not published to the host, so run it inside the app container --
which is also where the package and its settings already are:

    docker exec -i visualizer-app-1 python - < docker/backfill_world_owners.py
    docker exec -i visualizer-app-1 python - < docker/backfill_world_owners.py --apply

Without ``--apply`` it only says what it would do. Re-running is safe: a world
that already has an owner is left alone.
"""

import sys

from visualizer.akasha.config import get_mongo_client
from visualizer.akasha.store import DocumentStore
from visualizer.auth import ALL_PERMS, DELETE, AuthStore

# ``list_databases`` hides the reserved ``_``-prefixed ones; MongoDB's own three
# are not Akasha's and it has no reason to know about them.
MONGO_SYSTEM = frozenset({"admin", "config", "local"})


def main(apply: bool) -> int:
    client = get_mongo_client()
    documents = DocumentStore(client)
    auth = AuthStore(client)

    settled, claimed, unclear = [], [], []
    for world in sorted(documents.list_databases()):
        if world in MONGO_SYSTEM:
            continue
        if _owner_of(auth, world, None, None):
            settled.append(world)
            continue
        candidate = _owns_every_collection(auth, documents, world)
        if candidate is None:
            unclear.append(world)
            continue
        claimed.append((world, candidate))
        if apply:
            auth.grant_owner(candidate, world, None, None, list(ALL_PERMS))

    _report(settled, claimed, unclear, apply)
    return 1 if unclear else 0


def _owner_of(auth: AuthStore, database, collection, doc_id) -> set[str]:
    """Everyone holding ``delete`` at exactly this scope."""
    return {
        grant["username"]
        for grant in auth.grants_on(database, collection, doc_id)
        if DELETE in (grant.get("perms") or ())
    }


def _owns_every_collection(auth, documents, world) -> str | None:
    """The single writer who owns all of a world's categories, if there is one."""
    collections = documents.list_collections(world)
    if not collections:
        return None
    owners = [_owner_of(auth, world, name, None) for name in collections]
    common = set.intersection(*owners) if owners else set()
    return next(iter(common)) if len(common) == 1 else None


def _report(settled, claimed, unclear, apply: bool) -> None:
    verb = "granted" if apply else "would grant"
    for world in settled:
        print(f"ok    {world}  already has an owner")
    for world, username in claimed:
        print(f"{'ok   ' if apply else '--   '} {world}  {verb} to {username}")
    for world in unclear:
        print(
            f"??    {world}  no single writer owns every category; "
            f"grant it by hand in the admin console"
        )
    if claimed and not apply:
        print("\nnothing written. Re-run with --apply to make these grants.")


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))
