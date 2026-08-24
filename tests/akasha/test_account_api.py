"""HTTP-level tests for self-service account management.

Any logged-in user can view their account page and change their own email; the
page also surfaces the resources they own so they can share them. (Password
changes are covered by the shared auth tests.)
"""

from conftest import ADMIN_USER, collection_url, doc_url, login, register


def _user(app, username, password="correct-horse-battery"):
    register(app.test_client(), username, password)
    c = app.test_client()
    assert login(c, username, password).status_code == 200
    return c


# -- viewing the account page -------------------------------------------------


def test_account_page_requires_auth(anon_client):
    resp = anon_client.get("/account")
    # Unauthenticated browser requests are redirected to the login page.
    assert resp.status_code in (302, 401)


def test_account_page_renders_for_a_logged_in_user(app, auth_store):
    user = _user(app, "alice")
    resp = user.get("/account")
    assert resp.status_code == 200
    assert b"<h1>Access</h1>" in resp.data
    assert b"alice" in resp.data


def test_account_page_lists_owned_resources(app, auth_store):
    user = _user(app, "alice")
    # Alice needs write somewhere to create (and thereby own) a collection.
    auth_store.add_grant("alice", "world", "cast", None, ["read", "write"], granted_by="admin")
    assert user.post(collection_url(database="world", collection="cast")).status_code == 201
    resp = user.get("/account")
    assert resp.status_code == 200
    assert b"cast" in resp.data  # the owned collection is shown to share


# -- changing your own email --------------------------------------------------


def test_user_can_update_their_own_email_json(app, auth_store):
    user = _user(app, "alice")
    resp = user.post("/account/email", json={"email": "alice-new@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["email"] == "alice-new@example.com"
    assert auth_store.get_user("alice")["email"] == "alice-new@example.com"


def test_update_email_via_form_redirects(app, auth_store):
    user = _user(app, "alice")
    resp = user.post("/account/email", data={"email": "alice-form@example.com"})
    assert resp.status_code == 302
    assert auth_store.get_user("alice")["email"] == "alice-form@example.com"


def test_update_email_rejects_invalid_address(app, auth_store):
    user = _user(app, "alice")
    resp = user.post("/account/email", json={"email": "not-an-email"})
    assert resp.status_code == 400
    # Unchanged.
    assert auth_store.get_user("alice")["email"] == "alice@example.com"


def test_update_email_rejects_duplicate(app, auth_store):
    _user(app, "alice")  # alice@example.com
    bob = _user(app, "bob")  # bob@example.com
    resp = bob.post("/account/email", json={"email": "alice@example.com"})
    assert resp.status_code == 409
    assert auth_store.get_user("bob")["email"] == "bob@example.com"


def test_update_email_requires_a_value_json(app):
    user = _user(app, "alice")
    assert user.post("/account/email", json={"email": ""}).status_code == 400


def test_update_email_requires_auth(anon_client):
    resp = anon_client.post("/account/email", json={"email": "x@example.com"})
    assert resp.status_code == 401


def test_admin_sees_owned_shared_collections_on_their_account(app, auth_store, client):
    # The seeded admin creates a collection and can then manage its sharing from
    # their own account page (ownership, not the admin role, drives this).
    client.post(collection_url(database="mine", collection="cast"))
    client.post(doc_url("aldric", database="mine", collection="cast"), json={"n": 1})
    resp = client.get("/account")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "cast" in body
    assert ADMIN_USER in body


# -- collaborator roster (contacts) ------------------------------------------


def test_user_can_add_list_and_remove_contacts(app, auth_store):
    alice = _user(app, "alice")
    register(app.test_client(), "bob", "correct-horse-battery")

    assert alice.post("/account/contacts", data={"username": "bob"}).status_code == 302
    assert auth_store.list_contacts("alice") == ["bob"]

    body = alice.get("/account/contacts").get_json()
    assert body["contacts"] == ["bob"]

    assert alice.post("/account/contacts/bob/delete").status_code == 302
    assert auth_store.list_contacts("alice") == []


def test_cannot_add_yourself_as_a_contact(app, auth_store):
    alice = _user(app, "alice")
    resp = alice.post("/account/contacts", data={"username": "alice"}, follow_redirects=True)
    assert resp.status_code == 200  # redirected back with a flashed error
    assert auth_store.list_contacts("alice") == []


def test_adding_unknown_user_as_contact_is_rejected(app, auth_store):
    alice = _user(app, "alice")
    resp = alice.post("/account/contacts", data={"username": "ghost"}, follow_redirects=True)
    assert resp.status_code == 200
    assert auth_store.list_contacts("alice") == []


def test_contacts_json_requires_auth(anon_client):
    # The SPA fetches this with an Accept: application/json header, which yields a
    # 401 rather than an HTML login redirect.
    resp = anon_client.get("/account/contacts", headers={"Accept": "application/json"})
    assert resp.status_code == 401


# -- shared with me -----------------------------------------------------------


def test_shared_with_me_lists_resources_others_granted(app, auth_store, client):
    # Admin owns mine/cast and shares it with alice; alice sees it as shared in.
    client.post(collection_url(database="mine", collection="cast"))
    alice = _user(app, "alice")
    assert client.put(
        "/databases/mine/collections/cast/collaborators/alice", json={"role": "reader"}
    ).status_code == 200

    body = alice.get("/account").data.decode()
    assert "cast" in body          # the shared collection
    assert ADMIN_USER in body      # who shared it (the "Shared by" column)


def test_shared_access_offers_one_toggleable_list_per_kind(app, auth_store, client):
    client.post(collection_url(database="mine", collection="cast"))
    client.post(doc_url("aldric", database="mine", collection="cast"), json={"n": 1})
    body = client.get("/account").data.decode()
    # Every kind gets its own list, including the two whose resources live in
    # chronos -- and including the empty ones, so a writer with no books still
    # learns that sharing one is a thing they could do.
    for kind in ("collection", "article", "book", "calendar"):
        assert f'data-mode="{kind}"' in body, f"no list for {kind}"
    # The owned collection and the owned article each appear as a share row.
    assert "cast" in body
    assert "aldric" in body


def test_a_book_owned_in_chronos_is_shareable_from_the_account_page(app, auth_store):
    """The point of the exercise: one grant store, so akasha can list and share
    a book without chronos being involved at all."""
    alice = _user(app, "alice")
    bo = _user(app, "bo")  # noqa: F841 -- must exist for the share to be accepted
    auth_store.grant_owner(
        "alice", "ember-pact", None, None, ["read", "write", "delete"],
        resource_type="book",
    )
    body = alice.get("/account").data.decode()
    assert "ember-pact" in body
    assert "/account/sharing/book/ember-pact/collaborators" in body

    resp = alice.put(
        "/account/sharing/book/ember-pact/collaborators/bo", json={"role": "editor"}
    )
    assert resp.status_code == 200
    listed = alice.get("/account/sharing/book/ember-pact/collaborators").get_json()
    assert {"username": "bo", "role": "editor"} in listed["collaborators"]


def test_shared_with_me_excludes_your_own_resources(app, auth_store):
    # A user's own created collection is "owned", not "shared with me".
    alice = _user(app, "alice")
    auth_store.add_grant("alice", "world", "cast", None, ["read", "write"], granted_by="admin")
    alice.post(collection_url(database="world", collection="cast"))
    body = alice.get("/account").data.decode()
    assert "Nothing has been shared with you yet." in body


# -- the Accounts tabs ----------------------------------------------------------
#
# Account and Admin used to be two header links. They are one destination now,
# with a tab each, so these check what each role is offered -- and that hiding
# the Admin tab is presentation rather than the boundary itself.


def test_the_account_page_leads_with_the_accounts_tabs(app):
    html = _user(app, "alice").get("/account").get_data(as_text=True)
    assert "<h1>Access</h1>" in html
    assert 'class="tabs"' in html
    assert ">Account</a>" in html


def test_an_ordinary_user_is_offered_no_admin_tab(app):
    html = _user(app, "alice").get("/account").get_data(as_text=True)
    assert ">Admin</a>" not in html


def test_an_admin_is_offered_both_tabs(client):
    html = client.get("/account").get_data(as_text=True)
    assert ">Account</a>" in html
    assert ">Admin</a>" in html


def test_the_admin_console_wears_the_same_tabs(client):
    html = client.get("/admin").get_data(as_text=True)
    assert "<h1>Access</h1>" in html
    assert ">Account</a>" in html
    assert ">Admin</a>" in html


def _tab_strip(html):
    """Just the tabs nav -- the shared header marks its active link the same way."""
    return html.split('class="tabs"', 1)[1].split("</nav>", 1)[0]


def test_each_page_marks_its_own_tab_current(client):
    account = _tab_strip(client.get("/account").get_data(as_text=True))
    admin = _tab_strip(client.get("/admin").get_data(as_text=True))
    # Exactly one tab is current on each page, and it is the one you are on
    # rather than simply the first.
    assert account.count('aria-current="page"') == 1
    assert admin.count('aria-current="page"') == 1
    assert 'aria-current="page"' in account.split(">Account</a>")[0]
    assert 'aria-current="page"' in admin.split(">Admin</a>")[0]
    assert 'aria-current="page"' not in admin.split(">Account</a>")[0]


def test_hiding_the_admin_tab_is_not_the_only_guard(app):
    """The tab is presentation; ``admin_required`` is the actual boundary."""
    assert _user(app, "alice").get("/admin").status_code == 403
