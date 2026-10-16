# Run it on a Mac with Docker Desktop (no GPU box)

This is the shortest path to a working stack on your own Mac: articles, timelines,
maps and manuscripts, all in your browser at `http://localhost:5002`. No AI is
involved. You don't need a GPU box, an API key, Python, Node or MongoDB on the
Mac; Docker builds and runs everything.

For a Synology NAS, see [Deploy on a Synology NAS](synology-deployment.md)
instead.

## What you get, and what stays off

| | Without a GPU box |
| --- | --- |
| **Akasha**: articles, links, images, dioramas, history and diffs | Works |
| **Chronos**: books, events, plotlines and continuity checks | Works |
| **Prithvi**: maps with pinned articles | Works |
| **Logos**: manuscripts, drafts, the Writing Coach, PDF and EPUB | Works. The Writing Coach is local rules, not AI. |
| **Akasha research studio** (AI research drafts) | Off. The **✦ Research** button doesn't appear, and `/studio/<world>` says research is off. |
| **Logos LLM review** (an API) | Off. It reports that no GPU box is configured. |

Research stays off as long as `GPU_WORKER_URL` is unset, which is the default.
Nothing else needs it.

## What you need

- **A Mac** with Apple Silicon or Intel. Every image used here runs natively on
  both.
- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)**,
  installed and running (the whale icon in the menu bar). Its default resources
  are enough. If PDF export of a very long book fails, give it more memory in
  **Settings → Resources**.
- **About 3 GB of disk** for the images and build cache, plus your data.
- **git**, to get the code and update it later. If `git --version` in Terminal
  asks to install the Command Line Tools, let it. They also provide the
  `python3` used by the optional demo data below.

## 1. Get the code

In Terminal:

```bash
git clone https://github.com/huyhang/visualizer.git
cd visualizer
```

Every command below runs from this `visualizer` folder.

## 2. Create the secret

The app signs login cookies with a secret key. Make one and store it in
`docker/.env`, which git ignores, so updates never overwrite it:

```bash
echo "SECRET_KEY=$(openssl rand -hex 32)" > docker/.env
```

That's the only setting needed. Leave `GPU_WORKER_URL` out of this file; its
absence is what keeps AI off.

## 3. Build and start

```bash
docker compose -f docker/docker-compose.nas.yml up --build -d
```

The first run takes a few minutes. It downloads base images, installs the
Python dependencies and compiles the research studio's web page. Later starts
take seconds.

Check that both containers are up (the database should say `healthy`):

```bash
docker compose -f docker/docker-compose.nas.yml ps
```

Then check each service answers:

```bash
curl -s localhost:5002/health            # {"status":"ok"}
curl -s localhost:5002/timeline/health   # {"service":"chronos","status":"ok"}
curl -s localhost:5002/prithvi/health    # {"service":"prithvi","status":"ok"}
curl -s localhost:5002/logos/health      # {"service":"logos","status":"ok"}
```

## 4. Open it and create your account

Go to **http://localhost:5002/** and **Register**. The first account created
becomes the administrator. Then create a world and start writing.

| Address | What it is |
| --- | --- |
| `http://localhost:5002/` | Akasha: worlds and articles (and the shared login) |
| `http://localhost:5002/timeline` | Chronos: books and plotlines |
| `http://localhost:5002/prithvi` | Prithvi: maps |
| `http://localhost:5002/logos` | Logos: manuscripts |

## 5. Optional: load the demo story

Four scripts fill the stack with "The Ember Pact", a small story with a cast,
scenes, plotlines, a map and a manuscript. They use only the Python that
ships with the Command Line Tools. Run them in this order:

```bash
python3 docker/seed_demo.py
python3 docker/seed_story_map.py
python3 docker/seed_prithvi_demo.py
python3 docker/seed_logos_demo.py
```

The demo belongs to its own account: log in as **mara**, password
**ember-pact-demo**. If you run the scripts before registering, mara is the
first account and becomes the administrator. The book is left with continuity
problems on purpose; `python3 docker/seed_demo.py --fix` repairs them.

## Everyday use

The stack comes back by itself whenever Docker Desktop starts, unless you
stopped it yourself. To have it there after a reboot, turn on
**Settings → General → Start Docker Desktop when you sign in**.

```bash
# Stop, keeping everything
docker compose -f docker/docker-compose.nas.yml stop

# Start again
docker compose -f docker/docker-compose.nas.yml start

# Follow the app's log
docker compose -f docker/docker-compose.nas.yml logs -f app
```

Docker Desktop's **Containers** page shows the same project, named
`visualizer`, with stop and start buttons.

### Updating

```bash
git pull
docker compose -f docker/docker-compose.nas.yml up --build -d
docker image prune -f      # removes the previous build's leftover image
```

`--build` matters: without it Docker keeps running the old code. Your data and
`docker/.env` are untouched by an update.

## Back up and restore

All your work lives in one MongoDB database, in a Docker volume named
`visualizer_mongo-data` (or in a folder of your choosing, if `MONGO_DATA` in
`docker/.env` names one; see the Synology guide's "Keeping the data in a folder
you can see"). Copy it with a dump, not by copying files:

```bash
VISUALIZER_BACKUP_DIR=~/visualizer-backups sh docker/backup.sh
```

This writes `~/visualizer-backups/visualizer-<date>.archive` and keeps the
newest 14. Time Machine then backs up that folder like any other.

Restoring replaces what's in the database with the archive's contents:

```bash
docker cp ~/visualizer-backups/visualizer-<date>.archive visualizer-mongo-1:/tmp/r.archive
docker exec visualizer-mongo-1 mongorestore --archive=/tmp/r.archive --gzip --drop
```

## Remove it

```bash
# Remove the containers, keeping your data for next time
docker compose -f docker/docker-compose.nas.yml down

# Remove the containers AND delete all your data (cannot be undone)
docker compose -f docker/docker-compose.nas.yml down -v
```

## Troubleshooting

**`SECRET_KEY is required — set it in docker/.env`.** The file is missing or
empty. Run step 2 again from the `visualizer` folder.

**`Cannot connect to the Docker daemon`.** Docker Desktop isn't running. Open
it and wait for the whale icon to settle.

**`port is already allocated` (5002 is taken).** Something else uses port 5002.
Pick another port, say 5003, in a file of your own, `docker/compose.local.yml`
(git ignores it):

```yaml
services:
  app:
    ports: !override
      - "5003:5000"
```

Then add it to every command, e.g.
`docker compose -f docker/docker-compose.nas.yml -f docker/compose.local.yml up --build -d`,
and browse to `http://localhost:5003/`.

**Logging in works, but you're immediately logged out again.**
`SESSION_COOKIE_SECURE=true` is set in `docker/.env`. That setting is for
HTTPS deployments. Remove it for `http://localhost`, then run the `up` command
from step 3 again.

**The build fails while downloading packages.** A VPN or corporate proxy is
blocking Docker's downloads. Set the proxy in Docker Desktop's
**Settings → Resources → Proxies**, or retry off the VPN.

**You want the AI features after all.** That needs the GPU box described in
[`docs/gpu_worker`](gpu_worker/README.md); then set `GPU_WORKER_URL` and
`GPU_WORKER_TOKEN` in `docker/.env` and run step 3 again.

Before making the stack reachable from other machines, read
[`SECURITY.md`](../SECURITY.md).
