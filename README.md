# visualizer

## document-server

A small Flask + MongoDB service for storing and searching JSON documents.

### Design

Code lives in `src/visualizer/document-server/`. Because that directory name is
hyphenated (not a valid Python package name), the modules are imported as flat
top-level modules from that source root — hence `gunicorn wsgi:app`.

- `store.py` — `DocumentStore`, the only seam to MongoDB. It receives its Mongo
  client via the constructor (inversion of control), so tests inject an
  in-memory client and production injects a real one.
- `app.py` — `create_app(store)` factory + routes.
- `validation.py` — pure, DB-free validation helpers.
- `config.py` / `wsgi.py` — production wiring only.

Tests live in `tests/document-server/` and run against an in-memory MongoDB
(`mongomock`).

### Run

The `document-server` and `mongo` services live in the shared compose file at
`docker/docker-compose.yml` (alongside the janusgraph stack). The
`document-server` reuses the existing miniconda image (`docker/Dockerfile`) —
its `janusgraph_env` conda environment (see `docker/environment.yaml`) provides
flask, pymongo and gunicorn — and only overrides the run command to launch
gunicorn. To bring up just the document server:

```bash
docker compose -f docker/docker-compose.yml up --build -d document-server mongo
# app on http://localhost:5002, mongo internal-only
```

Omit the service names to bring up everything (graph + document server).

MongoDB has **no published port** — it is reachable only from inside the docker
network (by the `document-server` container), never from the host.

### API

Every call names a database and collection; single-document calls also name a
document id. A document body must be a JSON object.

| Method | Path | Purpose |
| --- | --- | --- |
| POST   | `/databases/<db>/collections/<col>` | create the database + collection (409 if exists) |
| POST   | `/databases/<db>/collections/<col>/documents/<id>` | create document (404 if db/collection missing, 409 if id exists) |
| GET    | `/databases/<db>/collections/<col>/documents/<id>` | get (404 if missing) |
| PUT    | `/databases/<db>/collections/<col>/documents/<id>` | replace (404 if missing) |
| DELETE | `/databases/<db>/collections/<col>/documents/<id>` | delete (404 if missing) |
| GET    | `/databases/<db>/collections/<col>/search?key=&text=` | search |

**Collections are explicit.** A database and collection must be created (via the
first `POST` above) before documents can be added to them — creating a document
in a database or collection that does not exist returns `404`. Creating the
collection also creates its database.

Search: `key` returns documents that contain that exact **top-level** key;
`text` returns documents whose content contains the text (case-insensitive
substring); giving both returns only documents that satisfy both. At least one
of `key`/`text` is required.

### Examples — querying the Lord of the Rings data

These use the database `middle-earth` and the collection `lord-of-the-rings`.
The app is published on the host at `http://localhost:5002`. For brevity, set:

```bash
BASE="http://localhost:5002/databases/middle-earth/collections/lord-of-the-rings"
```

**Create the database and collection first** (required before adding documents):

```bash
curl -X POST "$BASE"
# {"collection":"lord-of-the-rings","database":"middle-earth"}
# a second call returns 409 (already exists)
```

**Create the four characters** (each document is a JSON object; the id comes
from the URL). Posting to a database/collection that doesn't exist yet returns
`404`:

```bash
curl -X POST "$BASE/documents/aragorn" -H 'Content-Type: application/json' \
  -d '{"name":"Aragorn","race":"Man","title":"King of Gondor","weapon":"Anduril"}'
curl -X POST "$BASE/documents/frodo" -H 'Content-Type: application/json' \
  -d '{"name":"Frodo Baggins","race":"Hobbit","role":"Ring-bearer","home":"the Shire"}'
curl -X POST "$BASE/documents/legolas" -H 'Content-Type: application/json' \
  -d '{"name":"Legolas","race":"Elf","weapon":"bow","realm":"Mirkwood"}'
curl -X POST "$BASE/documents/gimli" -H 'Content-Type: application/json' \
  -d '{"name":"Gimli","race":"Dwarf","axe":"battle axe","father":"Gloin"}'
```

**Get one document by id:**

```bash
curl -s "$BASE/documents/frodo"
# {"document":{"home":"the Shire","name":"Frodo Baggins","race":"Hobbit","role":"Ring-bearer"},"id":"frodo"}
```

**Search by key** — key matching is exact and top-level only. Aragorn and
Legolas have a `weapon` key; Gimli's is spelled `axe`, so he is excluded:

```bash
curl -s "$BASE/search?key=weapon"
# {"count":2,"results":[{"document":{...,"name":"Aragorn","weapon":"Anduril"},"id":"aragorn"},
#                       {"document":{...,"name":"Legolas","weapon":"bow"},"id":"legolas"}]}
```

**Search by text** — documents whose content contains "Shire" (case-insensitive):

```bash
curl -s "$BASE/search?text=Shire"
# {"count":1,"results":[{"document":{"home":"the Shire","name":"Frodo Baggins",...},"id":"frodo"}]}
```

**Search by key AND text** — has a `weapon` key *and* mentions "bow":

```bash
curl -s "$BASE/search?key=weapon&text=bow"
# {"count":1,"results":[{"document":{"name":"Legolas",...,"weapon":"bow"},"id":"legolas"}]}
```

If your text has spaces or special characters, let curl encode it:

```bash
curl -s -G "$BASE/search" --data-urlencode "text=the Shire"
```

**Update (full replace)** — Aragorn takes his throne name (replace semantics:
fields not present are dropped):

```bash
curl -X PUT "$BASE/documents/aragorn" -H 'Content-Type: application/json' \
  -d '{"name":"Aragorn","alias":"Elessar","race":"Man"}'
```

**Delete:**

```bash
curl -X DELETE "$BASE/documents/gimli"   # 204 No Content; a later GET returns 404
```

**Read the data straight from MongoDB** (it has no host port, so query it from
inside the container). Note the bracket notation because the collection name is
hyphenated:

```bash
docker compose -f docker/docker-compose.yml exec -T mongo \
  mongosh --quiet middle-earth \
  --eval 'db["lord-of-the-rings"].find().toArray()'
```

The same queries in Python with `requests`:

```python
import requests

base = "http://localhost:5002/databases/middle-earth/collections/lord-of-the-rings"

requests.post(base)  # create the database + collection (idempotent-ish: 409 if it already exists)
requests.post(f"{base}/documents/frodo",
              json={"name": "Frodo Baggins", "race": "Hobbit", "home": "the Shire"})

print(requests.get(f"{base}/documents/frodo").json())
print(requests.get(f"{base}/search", params={"key": "weapon"}).json())
print(requests.get(f"{base}/search", params={"text": "Shire"}).json())
```

### Tests

Database tests use an in-memory MongoDB (`mongomock`); no server is contacted.

```bash
pip install -e ".[dev]"
pytest
```

# Example in python
```python
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal

# referencing the service directly by its name (janusgraph, as defined in the docker compose file)
connection = DriverRemoteConnection('ws://janusgraph:8182/gremlin', 'g')
g = traversal().withRemote(connection)
g.V().count().next()
```

```bash
docker compose up --build
```