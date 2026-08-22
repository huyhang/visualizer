# Prithvi

Where the world's things are. Prithvi holds SVG maps for [Akasha](../akasha/README.md)
worlds and pins Akasha articles to points on them. It has a map browser at
`/prithvi` — upload a drawing, place and move pins, read a pin's article without
leaving the map — over the same JSON API, which remains the whole contract and
the only way anything is written.

*Prithvi — the Sanskrit earth — is the ground the story walks on.*

## The model

Three sentences carry most of the design.

**A map belongs to a world.** A world is an Akasha database, and a map is named
inside it, so two worlds may each have a `capital` and neither takes the name
from the other. A world may have as many maps as it likes: a continent, a city,
one floor of a keep.

**A pin *is* an article on a map.** Its identity is the article's own address —
collection and id — which has three consequences worth stating: one article has
at most one position per map, the same article may appear on several maps, and a
pin pointing at another world cannot be expressed, because the world in the path
is the map's.

**Coordinates are the drawing's own.** A pin is an `(x, y)` in the SVG's
`viewBox` units, checked against that rectangle on every write. Which is why the
`viewBox` is frozen for as long as a map has pins: change the rectangle and every
stored coordinate silently means somewhere else. Redraw all you like — a new SVG
with the same box replaces the old one, and a map with no pins on it may be
reshaped freely.

## Permissions

There is nothing here to share. A map's permissions **are** its world's Akasha
grants:

| You hold on the world | You can |
| --- | --- |
| `read` | list and read maps, and see the pins whose articles you may read |
| `write` | upload and redraw maps, and place, move, restore and remove pins |
| `delete` | delete a whole map |

Two consequences. Access to a *collection* inside a world is not access to that
world's maps — the grant has to be on the world itself. And a reader shut out of
one article does not see its pin: not in a listing, not on the rendered map, and
not by asking for it directly, where the answer is `404` rather than `403`,
because "forbidden" would confirm that something is pinned there.

**Where a world grant comes from.** Creating a world's first category claims the
world, the same way creating a category claims the category — so a writer can
map their own world without anyone's help. From there a world is an ordinary
shareable thing: it has a tab on the account page, and
`/account/sharing/world/{world}/collaborators` behaves like every other kind.
Sharing it hands over its maps and their pins in the same motion, because there
is no separate map permission to hand over. Sharing a Chronos *book* also shares
its `world`, always as a reader — a timeline is not much use if you cannot open
the articles it points at.

A world made before that rule existed has no owner. Run
`docker/backfill_world_owners.py` once; it gives each world to the writer who
already owns every category in it, and lists the ambiguous ones for a human.

## The map browser

Open `/prithvi/` — `http://localhost:5002/prithvi/` in the combined stack, or
the **Maps** tab in the header shared with Articles and Timeline.

**Worlds → maps → one map.** The landing page lists the Akasha worlds you can
read; opening one shows its maps; opening a map draws it with its pins. Every
list shows the readable title with the slug beneath it, because the slug is the
permanent address and worth being able to see.

**Placing a pin.** With `write` on the world, the left pane lists the articles
in that world you can read and that are not pinned here yet. Choose one, then
click anywhere inside the map's `viewBox`; clicks outside it do nothing, which
is the same rectangle the API validates against. Drag a pin to move it. Select a
pin and **Remove pin** takes it off.

**Draft, then Save.** Placing, dragging and removing change a local draft only —
the header counts the unsaved changes. **Save** issues the writes (deletes,
then moves, then creates), each carrying the revision it was loaded at, so a
concurrent edit is refused rather than silently overwritten; on a conflict the
page reloads the server's pins and says so. **Discard** throws the draft away.
Leaving the page with unsaved changes asks first.

**Reading a pin.** Anyone with `read` on the world can open the map and click a
pin. The article appears beside it — title, an excerpt, a few fields and a link
into Articles. Pins whose article you cannot read are not on the map at all, and
asking for one directly answers exactly as if it did not exist.

**Zoom and pan.** 50%–400%, by wheel or the toolbar; the map is fitted to the
pane at 100% and the pointer stays put as you zoom. Drag the background to pan.
The **A** control cycles the same four text sizes as the other two services.

**Deleting a map** needs `delete` on the world and asks for confirmation. Each
of these controls appears only if your grants allow it — a button that only the
server would refuse is worse than no button.

## Uploading a map

The body of the request is the drawing, as `image/svg+xml`. It must declare a
`viewBox` — a `width` and `height` will not do, since a display size is not a
coordinate space, and guessing one would invent the units every pin is later
measured in.

What comes back is the map *without* the drawing, plus a receipt of what the
sanitizer removed:

```json
{
  "world": "ember-pact", "id": "western-realms", "rev": 1,
  "view_box": [0, 0, 1200, 720], "scale": null,
  "sanitization": {"removed_elements": {"script": 1}, "removed_attributes": {}}
}
```

Uploads are rebuilt from an allowlist rather than scrubbed of known-bad parts,
so scripting, animation, stylesheets, foreign content and remote references are
gone by construction. Filter primitives are kept, because hill shading is a
blurred alpha channel lit from one side and dropping filters would flatten every
relief map. See [`SECURITY.md`](../../SECURITY.md) for the whole rule.

## Revisions

Every change is a revision, and `If-Match` is required on all of them — absent is
`428`, stale is `409`. Recent revisions are retained: five per map, twenty per
pin, both configurable. A map revision is a whole drawing, which is why it is
capped lower and why revisions are stored beside their record rather than inside
it; five megabytes of SVG multiplied by its history would run into MongoDB's
16 MiB per-document ceiling.

Deleting leaves a tombstone and **frees the name**. Creating the same map or pin
again revives it as the next revision, so the ordinary cycle — place a pin,
remove it, place it again — is just `POST`, `DELETE`, `POST`. `restore` is there
for the other case: when you wanted the old contents back rather than a fresh
start.

## Scale

A map may record how far across it is:

```json
{"across": 400, "unit": "leagues"}
```

Nothing in this service reads it. It is here because code is cheap to add later
and measurements are not: a scale backfilled onto a map drawn six months ago
means someone deciding, again, how wide that coastline was meant to be. When
Chronos grows from asking *were they in two places at once?* to *could they have
got there in time?*, this is the number that makes the second question
answerable.

## A worked example

```bash
# One login covers the whole stack.
curl -sc /tmp/jar -X POST localhost:5002/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"mara","password":"…"}'

BASE=localhost:5002/prithvi/worlds/ember-pact/maps/western-realms

# Upload the drawing.
curl -sb /tmp/jar -X POST $BASE \
  -H 'Content-Type: image/svg+xml' --data-binary @western-realms.svg

# Say how big the world is.
curl -sb /tmp/jar -X PUT $BASE/scale -H 'If-Match: "1"' \
  -H 'Content-Type: application/json' -d '{"across":400,"unit":"leagues"}'

# Pin an article, then move it.
curl -sb /tmp/jar -X POST $BASE/pins/locations/highkeep \
  -H 'Content-Type: application/json' -d '{"x":355,"y":215}'
curl -sb /tmp/jar -X PUT $BASE/pins/locations/highkeep -H 'If-Match: "1"' \
  -H 'Content-Type: application/json' -d '{"x":361,"y":220}'

# Open this in a browser; each pin links to its article.
echo "$BASE/render.svg"
```

The complete contract is [`openapi.json`](openapi.json), held to the route table
by a contract test.

## Configuration

| Variable | Default | What it does |
| --- | ---: | --- |
| `PRITHVI_MAX_SVG_BYTES` | `5242880` | Largest accepted upload |
| `PRITHVI_MAP_REVISIONS_KEEP` | `5` | Retained revisions per map |
| `PRITHVI_PIN_REVISIONS_KEEP` | `20` | Retained revisions per pin |

`PRITHVI_URL` names where a browser reaches this service, for the **Maps** link
in all three headers: `/prithvi` under the combined stack, `http://localhost:5004`
when prithvi runs on its own port.

Everything else — Mongo, the secret, cookie flags, rate-limit storage — is the
stack's, read from the same environment as the other services.

## Notes for the next person

- `PrithviStore` is the only thing that knows about Mongo, and it is thin: the
  revision mechanics live in [`visualizer/documents.py`](../../src/visualizer/documents.py),
  shared with Chronos, so this service did not grow a second implementation of
  optimistic concurrency.
- `svg.py`, `validation.py`, `models.py` and `rendering.py` are pure. Most of the
  suite never starts a Flask app.
- Every service method that can return a pin takes a `may_read` predicate as a
  **required** argument. That is deliberate: whether a pin is visible depends on
  a grant over the article, and putting the rule in the service means a route
  added later cannot forget to apply it.
- There is a demo: `docker/seed_prithvi_demo.py` uploads
  `docker/ember_pact_map.svg` and pins Highkeep on it, through the real API.
