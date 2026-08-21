# Deploy on a Synology NAS

Everything specific to running the stack on DSM: first install, HTTPS, updating
to a new commit, backups, and where the data actually lives. Every service and
their shared MongoDB come from one compose file, so this covers the whole stack
rather than any one service in particular.

> Before exposing this beyond your own network, read
> [`SECURITY.md`](../SECURITY.md) — it lists the protections in place and the
> hardening still required (TLS, MongoDB auth, rate limiting, non-root
> container, and more).

---

## First install

`docker/docker-compose.nas.yml` runs as-is on any "+" model with **Container
Manager**. MongoDB 7 needs a CPU with AVX; on one without (some Celeron models),
change `mongo:7` to `mongo:4.4` in the compose file.

1. **Put the repo on the NAS.** Anywhere you like — a shared folder such as
   `/volume1/docker/visualizer` is conventional. Cloning with git rather than
   copying the files makes [updating](#updating-to-a-new-commit) a one-liner.
2. **Set the cookie-signing secret** in `docker/.env`. One value, shared by all
   the services, so a single login covers them:
   ```bash
   echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > docker/.env
   ```
   `docker/.env` is git-ignored, so it survives every update.
3. **Create the project.** In Container Manager, **Project → Create**, pointing
   at `docker/docker-compose.nas.yml`. Or over SSH:
   ```bash
   sudo docker compose -f docker/docker-compose.nas.yml up --build -d
   ```

The app publishes host port **5002** (DSM itself uses 5000/5001). MongoDB has no
published port — it is reachable only inside the Docker network.

Check every part is alive:

```bash
curl -s localhost:5002/health            # {"status":"ok"}                  akasha
curl -s localhost:5002/timeline/health   # {"service":"chronos",...}        chronos
curl -s localhost:5002/prithvi/health    # {"service":"prithvi",...}        prithvi
```

Then open **http://<nas>:5002/** and register — **the first account becomes the
administrator.**

## HTTPS

Terminate TLS with Synology's own reverse proxy rather than in the container:
**Control Panel → Login Portal → Advanced → Reverse Proxy**, pointing an HTTPS
hostname at `http://localhost:5002`, with a Let's Encrypt certificate bound to
it. One rule covers every service — that is the reason they share an origin.

Then add `SESSION_COOKIE_SECURE=true` to `docker/.env` and redeploy, so the
session cookie is only ever sent over HTTPS. With that set, logging in over plain
HTTP stops working — use the `https://` address.

---

## Updating to a new commit

Take a backup first if the update is anything but trivial — see
[Backups](#backups). Then, over SSH:

```bash
cd /volume1/docker/visualizer          # wherever the repo lives
sudo git status                        # confirm nothing local would conflict
sudo git pull
sudo docker compose -f docker/docker-compose.nas.yml up --build -d
```

That is the whole update. `--build` is the part that matters: without it compose
reuses the existing image and your new code never runs.

What happens, and what doesn't:

- **Only the app container is replaced.** Compose rebuilds `visualizer-app`,
  recreates that container, and leaves `visualizer-mongo-1` running with its
  volume attached. Downtime is the few seconds the app takes to restart.
- **Your data is untouched.** It lives in the `visualizer_mongo-data` volume,
  which compose neither rebuilds nor recreates.
- **Your secret is untouched.** `docker/.env` is git-ignored, so `git pull` never
  overwrites `SECRET_KEY`. (Replacing it would not lose data, but it would
  invalidate every existing session and log everyone out.)
- **Nothing migrates.** No part of the stack runs a schema step on start — the
  containers simply serve the new code against the existing documents.

Verify, using the health checks above, and then by loading a page you changed.

**From the GUI instead.** Container Manager's **Project → Action → Build** does
the rebuild-and-restart half, but not the `git pull`; the files on disk have to
be updated first, by SSH or File Station. There is no way to pull from within
Container Manager.

**Reclaiming space.** Each rebuild leaves the previous image behind, and a NAS
volume fills up quietly:

```bash
sudo docker image prune -f        # dangling images only — safe
```

**Rolling back.** Check out the previous commit and rebuild:

```bash
sudo git log --oneline -5         # find the sha you were on
sudo git checkout <sha>
sudo docker compose -f docker/docker-compose.nas.yml up --build -d
```

Code rolls back cleanly. Data does not roll back with it — if the newer version
wrote something the older one cannot read, restore a dump from before the update
as well.

---

## Backups

Every service shares one MongoDB, so one dump covers everything — articles,
books, plotlines, events, maps, pins, accounts and grants.

It lives in a Docker **named volume**, `visualizer_mongo-data`, which on DSM sits
under `/volume1/@docker/volumes/…` — a hidden system folder that File Station and
Hyper Backup cannot see. (`sudo docker volume inspect visualizer_mongo-data`
prints the exact path; the `/volume1` part changes if Container Manager was
installed on another volume.) Don't back it up by copying those files: under a
running `mongod` you get a torn snapshot that may not restore.

Use [`docker/backup.sh`](../docker/backup.sh) instead. It runs `mongodump` —
consistent while the database is live — into an ordinary shared folder that Hyper
Backup *can* reach, and prunes to the last 14 nights:

1. **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined
   script.**
2. User **root**, daily at a quiet hour.
3. Paste the contents of `docker/backup.sh` (or call it by path if the repo lives
   on the NAS). Override `VISUALIZER_BACKUP_DIR` if `/volume1/backups/visualizer`
   isn't where you want it, and `VISUALIZER_MONGO_CONTAINER` if Container Manager
   named the container something other than `visualizer-mongo-1` — check its
   container list.
4. Tick **Send run details by email → only when the script terminates
   abnormally**, so silence means it worked.

Then point **Hyper Backup** at that folder for versioning and an offsite copy.
Snapshot Replication is a good complement for fast rollback, but it is
crash-consistent rather than application-consistent — the dump stays the primary.

Restoring, and rehearsing a restore against a throwaway container without
touching live data, are both documented in the script's header comments. Rehearse
occasionally: it is what separates a backup from a folder of files you hope are
backups.

---

## Observability

`http://<nas>:5002/admin/observability` (administrators only) is where you find
out whether the NAS needs more room. It leads with a projected fill date derived
from observed growth, then breaks the usage down by writer, by route and by
hour. No extra containers: the data sits in a reserved `_ops` database in the
MongoDB you already run, and expires on its own.

Free space is read from `MONITORING_DATA_PATH`, which the compose file points at
`/data/mongo` — the `mongo-data` volume, mounted read-only into the app
container purely so it can be measured. Pointing it anywhere else measures the
wrong disk.

Expect it to cost a few tens of megabytes a year. Requests are not measured
individually: handlers only touch memory, and a background thread writes hourly
totals every five minutes, so a busy hour is a handful of writes rather than one
per request.

**Pausing.** Use the button on the page. It stops recording, the hourly storage
sweep and the capacity sample; history already collected is kept and ages out on
its own. The setting is durable, so it survives a restart. To disable it before
the first boot instead, set `MONITORING_ENABLED=false` in `docker/.env`.

**Memory readings need Linux.** Disk, MongoDB size and everything else work
anywhere; the memory meter reads `/proc/meminfo` and shows an em dash where that
does not exist. On the NAS it does.

---

## Where things live

| What | Where |
| --- | --- |
| Repo + compose file | wherever you cloned it, e.g. `/volume1/docker/visualizer` |
| `SECRET_KEY` and other config | `docker/.env` (git-ignored) |
| MongoDB data | Docker volume `visualizer_mongo-data`, under `/volume1/@docker/volumes/…` |
| Backups | wherever `VISUALIZER_BACKUP_DIR` points, default `/volume1/backups/visualizer` |
| Containers | `visualizer-app-1`, `visualizer-mongo-1` |
| Published port | `5002` → every service (akasha at `/`, chronos at `/timeline`, prithvi at `/prithvi`) |
| Observability data | Mongo `_ops` (`request_hours`, `storage_days`, `problems`, `capacity`, `settings`) |
