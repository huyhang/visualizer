"""Put the Ember Pact on a map, over the real HTTP API.

Run ``python docker/seed_demo.py`` first -- this pins the locations that script
writes, and refuses to invent any.

One prerequisite is worth understanding rather than working around. Akasha hands
out grants at *collection* and *article* scope, and Prithvi asks for one at
**world** scope, because a map belongs to the world rather than to any category
inside it. So a writer who owns every collection in ``ember-pact`` still cannot
put a map in it until somebody says they own the world. In the demo that
somebody is mara herself, who registered first and is therefore the
administrator; the script does it through the ordinary admin form, and prints
what it did in case you would rather have done it by hand.

Usage (from the repo root, stack already up and seeded):
    python docker/seed_prithvi_demo.py

Re-running is safe: it grants only what is missing, replaces the drawing and
moves the pins, rather than duplicating anything.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

AKASHA = os.environ.get("AKASHA_BASE", "http://localhost:5002")
PRITHVI = os.environ.get("PRITHVI_BASE", "http://localhost:5002/prithvi")

USER = "mara"
PASSWORD = "ember-pact-demo"
WORLD = "ember-pact"
MAP = "western-realms"
COLLECTION = "locations"

SVG_PATH = Path(__file__).with_name("ember_pact_map.svg")

# How wide the drawing is in the world's own units. Nothing reads it yet; it is
# recorded now so the maps drawn today are measurable when something does.
SCALE = {"across": 400, "unit": "leagues"}

# Chosen once against the drawing's 1200x720 box, so re-running is stable:
# Highkeep up in the marches, the Throne Hall on the road below it, Emberport
# where the Vale reaches the water.
PLACES = {
    "highkeep": {"x": 355, "y": 215},
    "throne-hall": {"x": 540, "y": 470},
    "emberport": {"x": 648, "y": 568},
}

_CSRF = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')


class Session:
    """A logged-in browser, near enough: one cookie jar, carried throughout."""

    def __init__(self):
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def call(self, method, url, body=None, content_type=None, headers=None):
        data = body
        if isinstance(body, (dict, list)):
            data, content_type = json.dumps(body).encode(), "application/json"
        request = urllib.request.Request(url, data=data, method=method)
        if content_type:
            request.add_header("Content-Type", content_type)
        for key, value in (headers or {}).items():
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


def main():
    session = Session()
    status, body = session.call(
        "POST", f"{AKASHA}/login", {"username": USER, "password": PASSWORD}
    )
    show(status, f"log in as {USER}")
    if status != 200:
        sys.exit(f"cannot log in -- run seed_demo.py first ({body})")

    grant_the_world(session)
    revision = upload_map(session)
    revision = set_scale(session, revision)
    for article, at in PLACES.items():
        place(session, article, at)

    print()
    print(f"map:   {PRITHVI}/worlds/{WORLD}/maps/{MAP}      (rev {revision})")
    print(f"view:  {PRITHVI}/worlds/{WORLD}/maps/{MAP}/render.svg")
    print(f"login: {USER} / {PASSWORD}")


def grant_the_world(session):
    """Give mara the world-scoped grant Prithvi asks for, as the admin she is.

    Asked first, because the admin form appends rather than replaces: running
    this twice would otherwise leave two identical grants behind. The cheapest
    way to ask is to use the permission -- if the world's map list answers, the
    grant is already there.
    """
    status, _ = session.call("GET", f"{PRITHVI}/worlds/{WORLD}/maps")
    if status == 200:
        show(status, f"{USER} already holds the world '{WORLD}'")
        return
    status, page = session.call("GET", f"{AKASHA}/admin")
    token = _CSRF.search(page or "")
    if status != 200 or token is None:
        show(status, "read the admin page", "skipping the grant; see below")
        return
    form = urllib.parse.urlencode(
        [
            ("csrf_token", token.group(1)),
            ("username", USER),
            ("database", WORLD),
            ("perms", "read"),
            ("perms", "write"),
            ("perms", "delete"),
        ]
    ).encode()
    status, _ = session.call(
        "POST",
        f"{AKASHA}/admin/grants",
        form,
        content_type="application/x-www-form-urlencoded",
    )
    show(status, f"grant {USER} the world '{WORLD}'")


def upload_map(session) -> int:
    url = f"{PRITHVI}/worlds/{WORLD}/maps/{MAP}"
    svg = SVG_PATH.read_bytes()
    status, body = session.call("POST", url, svg, content_type="image/svg+xml")
    if status == 409:
        # Already there from a previous run: replace the drawing in place.
        _, current = session.call("GET", url)
        status, body = session.call(
            "PUT",
            f"{url}/svg",
            svg,
            content_type="image/svg+xml",
            headers={"If-Match": f'"{current["rev"]}"'},
        )
    show(status, f"upload the map '{MAP}'", _why(status, body))
    if status >= 400:
        sys.exit(1)
    return body["rev"]


def set_scale(session, revision: int) -> int:
    url = f"{PRITHVI}/worlds/{WORLD}/maps/{MAP}/scale"
    status, body = session.call(
        "PUT", url, SCALE, headers={"If-Match": f'"{revision}"'}
    )
    show(status, f"scale the map at {SCALE['across']} {SCALE['unit']} across",
         _why(status, body))
    return body["rev"] if status < 400 else revision


def place(session, article: str, at: dict):
    url = f"{PRITHVI}/worlds/{WORLD}/maps/{MAP}/pins/{COLLECTION}/{article}"
    status, body = session.call("POST", url, at)
    if status == 409:
        _, current = session.call("GET", url)
        status, body = session.call(
            "PUT", url, at, headers={"If-Match": f'"{current["rev"]}"'}
        )
    show(status, f"pin {article} at ({at['x']}, {at['y']})", _why(status, body))


def _why(status, body) -> str:
    if status < 400:
        return ""
    if status == 403:
        return (
            f"no world-scoped grant. In the admin console, grant {USER} "
            f"database '{WORLD}' with collection and document left empty"
        )
    if isinstance(body, dict):
        return f"{body.get('code')}: {body.get('error')}"
    return str(body)


if __name__ == "__main__":
    main()
