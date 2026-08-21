#!/bin/sh
# Nightly backup of the stack's MongoDB — every service, one dump.
#
# Why a logical dump rather than copying the volume: `mongodump` is consistent
# while the database is running, and copying the files under a live mongod gives
# you a torn snapshot that may not restore. The volume lives in DSM's hidden
# `@docker` folder anyway, where Hyper Backup and File Station cannot reach it;
# this writes to an ordinary shared folder so they can.
#
# On a Synology NAS: Control Panel → Task Scheduler → Create → Scheduled Task →
# User-defined script. Run it as **root**, daily, and tick "Send run details by
# email" → "only when the script terminates abnormally", so silence means it
# worked. `docker` is often missing from Task Scheduler's PATH, hence the lookup
# below.
#
# Restore (destructive — replaces the collections in the archive):
#     docker cp <archive> visualizer-mongo-1:/tmp/r.archive
#     docker exec visualizer-mongo-1 mongorestore --archive=/tmp/r.archive --gzip --drop
#
# Rehearse a restore without touching live data (do this occasionally — it is
# what separates a backup from a folder of files you hope are backups):
#     docker run -d --rm --name restore-test mongo:7
#     docker cp <archive> restore-test:/tmp/r.archive
#     docker exec restore-test mongorestore --archive=/tmp/r.archive --gzip
#     docker exec restore-test mongosh --quiet --eval \
#       'db.getSiblingDB("_chronos").books.countDocuments({})'
#     docker exec restore-test mongosh --quiet --eval \
#       'db.getSiblingDB("_prithvi").maps.countDocuments({})'
#     docker rm -f restore-test

set -eu

# Overridable so the same script runs on a laptop or in a test.
DEST=${VISUALIZER_BACKUP_DIR:-/volume1/backups/visualizer}
KEEP=${VISUALIZER_BACKUP_KEEP:-14}
CONTAINER=${VISUALIZER_MONGO_CONTAINER:-visualizer-mongo-1}

DOCKER=$(command -v docker || echo /usr/local/bin/docker)
STAMP=$(date +%Y-%m-%d-%H%M%S)
OUT="$DEST/visualizer-$STAMP.archive"

mkdir -p "$DEST"

# --gzip compresses inside the archive; the file is a mongodump archive, not a
# plain .gz, so do not try to gunzip it — mongorestore --gzip reads it.
$DOCKER exec "$CONTAINER" mongodump --quiet --archive=/tmp/vis.archive --gzip
$DOCKER cp "$CONTAINER":/tmp/vis.archive "$OUT"
$DOCKER exec "$CONTAINER" rm -f /tmp/vis.archive

# Fail loudly rather than quietly rotating good backups out behind an empty one.
[ -s "$OUT" ] || { echo "backup is empty: $OUT" >&2; exit 1; }

# Prune oldest first, keeping $KEEP. Avoids `xargs -r`, which is not portable
# to every DSM shell.
ls -1t "$DEST"/visualizer-*.archive 2>/dev/null | tail -n +$((KEEP + 1)) \
  | while read -r old; do rm -f "$old"; done

echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
