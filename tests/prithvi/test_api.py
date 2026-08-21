"""The service over HTTP: status codes, headers, and who is allowed what."""

from .conftest import (
    CLOSED_PIN_URL,
    COLLECTION,
    MAP_URL,
    OPEN_ARTICLE,
    PIN_URL,
    SVG,
    WORLD,
    login,
)

SVG_TYPE = "image/svg+xml"
WIDER = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"/>'


def upload(client, url=MAP_URL, body=SVG, **kwargs):
    return client.post(url, data=body, content_type=SVG_TYPE, **kwargs)


# -- getting in ---------------------------------------------------------------


def test_health_needs_no_account(app):
    assert app.test_client().get("/health").get_json() == {
        "status": "ok",
        "service": "prithvi",
    }


def test_an_api_client_without_a_session_is_told_so_in_json(app):
    response = app.test_client().get(
        f"/worlds/{WORLD}/maps", headers={"Accept": "application/json"}
    )
    assert response.status_code == 401
    assert response.is_json


# -- uploading a map ----------------------------------------------------------


def test_a_map_is_uploaded_as_an_svg_body(client):
    created = upload(client)

    assert created.status_code == 201
    assert created.headers["ETag"] == '"1"'
    assert created.get_json()["view_box"] == [0.0, 0.0, 100.0, 50.0]


def test_an_svg_must_arrive_as_an_svg(client):
    response = client.post(MAP_URL, data=SVG, content_type="text/plain")
    assert response.status_code == 415
    assert response.get_json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_an_oversized_upload_is_refused(client):
    body = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">' + b" " * 10_000
    response = upload(client, body=body)
    assert response.status_code == 413
    assert response.get_json()["code"] == "SVG_TOO_LARGE"


def test_a_bad_map_name_blames_the_name_and_not_the_drawing(client):
    response = upload(client, url=f"/worlds/{WORLD}/maps/not a name")
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_MAP_NAME"


def test_what_the_sanitizer_removed_comes_back_with_the_map(client):
    body = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
        b"<script>alert(1)</script><rect/></svg>"
    )
    created = upload(client, body=body)

    assert created.get_json()["sanitization"]["removed_elements"] == {"script": 1}
    assert "script" not in client.get(f"{MAP_URL}/svg").get_data(as_text=True)


def test_a_stored_drawing_is_served_so_a_browser_will_only_draw_it(mapped):
    response = mapped.get(f"{MAP_URL}/svg")

    assert response.mimetype == SVG_TYPE
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"].startswith("sandbox")
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["ETag"] == '"1"'


def test_listing_maps_is_paginated_like_everything_else(mapped):
    body = mapped.get(f"/worlds/{WORLD}/maps").get_json()
    assert [row["id"] for row in body["maps"]] == ["western-realms"]
    assert (body["page"], body["per_page"], body["total"], body["pages"]) == (1, 25, 1, 1)


# -- pins ---------------------------------------------------------------------


def test_a_pin_is_placed_moved_and_removed(mapped):
    placed = mapped.post(PIN_URL, json={"x": 10, "y": 20})
    assert placed.status_code == 201
    assert placed.get_json()["position"] == {"x": 10.0, "y": 20.0}
    assert placed.get_json()["article"]["title"] == "Highkeep"

    moved = mapped.put(PIN_URL, json={"x": 30, "y": 30}, headers={"If-Match": '"1"'})
    assert moved.status_code == 200
    assert moved.get_json()["rev"] == 2

    assert mapped.delete(PIN_URL, headers={"If-Match": '"2"'}).status_code == 204
    assert mapped.get(PIN_URL).status_code == 404


def test_a_pin_removed_by_mistake_can_just_be_placed_again(mapped):
    """The plain path back, without the client needing to know about restore."""
    mapped.post(PIN_URL, json={"x": 10, "y": 20})
    mapped.delete(PIN_URL, headers={"If-Match": '"1"'})

    replaced = mapped.post(PIN_URL, json={"x": 40, "y": 40})

    assert replaced.status_code == 201
    assert replaced.get_json()["position"] == {"x": 40.0, "y": 40.0}


def test_a_pin_can_also_be_restored_to_where_it_was(mapped):
    mapped.post(PIN_URL, json={"x": 10, "y": 20})
    mapped.delete(PIN_URL, headers={"If-Match": '"1"'})

    restored = mapped.post(f"{PIN_URL}/restore/1", headers={"If-Match": '"2"'})

    assert restored.status_code == 200
    assert restored.get_json()["position"] == {"x": 10.0, "y": 20.0}


def test_a_pin_outside_the_map_is_refused(mapped):
    response = mapped.post(PIN_URL, json={"x": 500, "y": 20})
    assert response.status_code == 422
    assert response.get_json()["code"] == "POSITION_OUT_OF_BOUNDS"


def test_a_pin_for_an_article_that_does_not_exist_is_refused(mapped):
    response = mapped.post(f"{MAP_URL}/pins/{COLLECTION}/nowhere", json={"x": 1, "y": 1})
    assert response.status_code == 422
    assert response.get_json()["code"] == "ARTICLE_NOT_FOUND"


def test_a_pin_whose_article_is_deleted_stays_and_says_so(mapped, document_store):
    mapped.post(PIN_URL, json={"x": 10, "y": 20})
    document_store.delete(WORLD, COLLECTION, OPEN_ARTICLE, expected_rev=1, author="mara")

    article = mapped.get(PIN_URL).get_json()["article"]

    assert article["status"] == "missing"
    assert article["title"] is None


# -- concurrency --------------------------------------------------------------


def test_a_change_without_a_precondition_is_refused(mapped):
    mapped.post(PIN_URL, json={"x": 10, "y": 20})
    response = mapped.put(PIN_URL, json={"x": 11, "y": 21})
    assert response.status_code == 428
    assert response.get_json()["code"] == "PRECONDITION_REQUIRED"


def test_a_change_from_a_stale_revision_is_refused(mapped):
    mapped.post(PIN_URL, json={"x": 10, "y": 20})
    mapped.put(PIN_URL, json={"x": 11, "y": 21}, headers={"If-Match": '"1"'})

    response = mapped.put(PIN_URL, json={"x": 12, "y": 22}, headers={"If-Match": '"1"'})

    assert response.status_code == 409
    assert response.get_json()["code"] == "REVISION_CONFLICT"


def test_a_precondition_that_is_not_a_revision_is_refused(mapped):
    response = mapped.delete(MAP_URL, headers={"If-Match": '"*"'})
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REVISION"


def test_a_precondition_that_is_not_a_number_is_refused(mapped):
    response = mapped.delete(MAP_URL, headers={"If-Match": '"soon"'})
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REVISION"


def test_a_precondition_below_the_first_revision_is_refused(mapped):
    response = mapped.delete(MAP_URL, headers={"If-Match": '"0"'})
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REVISION"


def test_a_redraw_cannot_move_the_ground_under_a_pin(mapped):
    mapped.post(PIN_URL, json={"x": 10, "y": 20})

    response = mapped.put(
        f"{MAP_URL}/svg", data=WIDER, content_type=SVG_TYPE, headers={"If-Match": '"1"'}
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "VIEWBOX_LOCKED"


# -- who may see what ---------------------------------------------------------


def test_a_reader_may_look_but_not_touch(reader, mapped):
    assert reader.get(MAP_URL).status_code == 200
    assert reader.post(PIN_URL, json={"x": 1, "y": 1}).status_code == 403


def test_a_world_you_were_never_given_is_not_yours_to_list(reader):
    assert reader.get("/worlds/salt-road/maps").status_code == 403


def test_access_to_a_collection_is_not_access_to_the_world_s_maps(app, auth_store):
    """Map permissions are the world's permissions, and only the world's."""
    from werkzeug.security import generate_password_hash

    auth_store.create_user("cole", generate_password_hash("cole-pw"))
    auth_store.add_grant("cole", WORLD, COLLECTION, None, ["read", "write"],
                         granted_by="admin")
    client = app.test_client()
    assert login(client, "cole").status_code == 200

    assert client.get(f"/worlds/{WORLD}/maps").status_code == 403


def test_a_pin_you_may_not_read_is_hidden_everywhere_it_would_appear(reader, mapped):
    assert mapped.post(CLOSED_PIN_URL, json={"x": 10, "y": 10}).status_code == 201
    assert mapped.post(PIN_URL, json={"x": 20, "y": 20}).status_code == 201

    listing = reader.get(f"{MAP_URL}/pins").get_json()
    drawn = reader.get(f"{MAP_URL}/render.svg").get_data(as_text=True)

    assert [row["article"]["id"] for row in listing["pins"]] == [OPEN_ARTICLE]
    assert listing["total"] == 1
    assert reader.get(CLOSED_PIN_URL).status_code == 404
    assert reader.get(f"{CLOSED_PIN_URL}/versions").status_code == 404
    assert "Oathstone" not in drawn
    assert "Highkeep" in drawn


# -- the map you can open -----------------------------------------------------


def test_the_rendered_map_carries_its_pins_and_links_them(mapped):
    mapped.post(PIN_URL, json={"x": 10, "y": 20})

    response = mapped.get(f"{MAP_URL}/render.svg")
    body = response.get_data(as_text=True)

    assert response.mimetype == SVG_TYPE
    assert response.headers["Cache-Control"] == "no-store"
    assert "prithvi-pins" in body
    assert "Highkeep" in body
    assert f'href="/#/{WORLD}/{COLLECTION}/{OPEN_ARTICLE}"' in body


# -- history ------------------------------------------------------------------


def test_a_map_remembers_being_scaled_and_redrawn(mapped):
    mapped.put(f"{MAP_URL}/scale", json={"across": 400, "unit": "leagues"},
               headers={"If-Match": '"1"'})
    mapped.put(f"{MAP_URL}/svg", data=SVG, content_type=SVG_TYPE,
               headers={"If-Match": '"2"'})

    versions = mapped.get(f"{MAP_URL}/versions").get_json()["versions"]
    first = mapped.get(f"{MAP_URL}/versions/1").get_json()

    assert [v["rev"] for v in versions] == [3, 2, 1]
    assert mapped.get(MAP_URL).get_json()["scale"] == {"across": 400.0, "unit": "leagues"}
    assert first["op"] == "create"
    assert first["scale"] is None


def test_a_deleted_map_is_gone_until_it_is_restored(mapped):
    mapped.post(PIN_URL, json={"x": 10, "y": 20})
    assert mapped.delete(MAP_URL, headers={"If-Match": '"1"'}).status_code == 204
    assert mapped.get(MAP_URL).status_code == 404
    assert mapped.get(PIN_URL).status_code == 404

    restored = mapped.post(f"{MAP_URL}/restore/1", headers={"If-Match": '"2"'})

    assert restored.status_code == 200
    assert mapped.get(PIN_URL).status_code == 200


def test_a_deleted_map_name_can_simply_be_used_again(mapped):
    mapped.delete(MAP_URL, headers={"If-Match": '"1"'})
    assert upload(mapped).status_code == 201


# -- wiring -------------------------------------------------------------------


def test_the_factory_refuses_to_build_something_unusable(prithvi_store,
                                                         article_gateway, auth_store):
    """Both of these would fail later, and less legibly, on a real request."""
    import pytest

    from visualizer.prithvi.app import create_app

    with pytest.raises(ValueError):
        create_app(prithvi_store, article_gateway, auth_store, secret_key="")
    with pytest.raises(ValueError):
        create_app(prithvi_store, article_gateway, auth_store, secret_key="s",
                   max_svg_bytes=0)


# -- sharing a world ----------------------------------------------------------


def _share_the_world(auth_store, username, role="reader"):
    """Exactly what the account page does, and nothing Prithvi-specific."""
    from visualizer import sharing

    return sharing.share(
        auth_store,
        sharing.WORLD,
        sharing.WORLD.scope({"database": WORLD}),
        username,
        role,
        me="mara",
    )


def test_sharing_a_world_shares_its_maps_and_their_pins(app, auth_store, mapped):
    """No cascade needed: a map's permissions *are* its world's.

    Nothing in Prithvi is enumerated or copied when a world changes hands. The
    map is reachable because the reader can read the world, and each pin is
    visible because that same grant reaches the article beneath it.
    """
    from werkzeug.security import generate_password_hash

    mapped.post(PIN_URL, json={"x": 10, "y": 20})
    auth_store.create_user("newcomer", generate_password_hash("newcomer-pw"))
    guest = app.test_client()
    assert login(guest, "newcomer").status_code == 200
    assert guest.get(MAP_URL).status_code == 403

    _share_the_world(auth_store, "newcomer")

    assert guest.get(f"/worlds/{WORLD}/maps").get_json()["total"] == 1
    assert guest.get(MAP_URL).status_code == 200
    assert [p["article"]["id"] for p in guest.get(f"{MAP_URL}/pins").get_json()["pins"]] == [
        OPEN_ARTICLE
    ]
    assert "Highkeep" in guest.get(f"{MAP_URL}/render.svg").get_data(as_text=True)


def test_a_world_reader_still_cannot_change_the_map(app, auth_store, mapped):
    from werkzeug.security import generate_password_hash

    auth_store.create_user("newcomer", generate_password_hash("newcomer-pw"))
    guest = app.test_client()
    login(guest, "newcomer")
    _share_the_world(auth_store, "newcomer")

    assert guest.post(PIN_URL, json={"x": 1, "y": 1}).status_code == 403
    assert upload(guest, url=f"/worlds/{WORLD}/maps/second").status_code == 403


def test_sharing_a_world_as_an_editor_hands_over_its_maps_too(app, auth_store, mapped):
    from werkzeug.security import generate_password_hash

    auth_store.create_user("newcomer", generate_password_hash("newcomer-pw"))
    guest = app.test_client()
    login(guest, "newcomer")
    _share_the_world(auth_store, "newcomer", role="editor")

    assert guest.post(PIN_URL, json={"x": 1, "y": 1}).status_code == 201


def test_taking_the_world_back_takes_the_maps_with_it(app, auth_store, mapped):
    from werkzeug.security import generate_password_hash

    from visualizer import sharing

    auth_store.create_user("newcomer", generate_password_hash("newcomer-pw"))
    guest = app.test_client()
    login(guest, "newcomer")
    _share_the_world(auth_store, "newcomer")
    assert guest.get(MAP_URL).status_code == 200

    sharing.unshare(
        auth_store,
        sharing.WORLD,
        sharing.WORLD.scope({"database": WORLD}),
        "newcomer",
        me="mara",
    )

    assert guest.get(MAP_URL).status_code == 403
