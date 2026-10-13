"""The fetcher reaches the public web and nothing else.

Real HTTP against a local server -- which, being on 127.0.0.1, the guard would
refuse; so these tests allow loopback *only* and keep every other private
range refused, which is what the redirect and DNS tests rely on.
"""

import socket
import threading
import time

import pytest
from werkzeug.serving import make_server
from werkzeug.wrappers import Request, Response

from visualizer.gpu_worker.fetch import Fetcher, FetchError, is_public

# -- the address rule --------------------------------------------------------


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.9", "192.168.1.20",   # loopback, RFC 1918
    "169.254.169.254",                                       # cloud metadata
    "100.100.100.100", "100.64.0.1",                         # Tailscale / CGNAT
    "0.0.0.0", "224.0.0.1", "255.255.255.255",               # unspecified, multicast
    "::1", "fd7a:115c:a1e0::1", "fe80::1",                   # IPv6 loopback, ULA, link
    "::ffff:127.0.0.1", "::ffff:10.0.0.1",                   # IPv4 hidden in IPv6
    "2002:7f00:1::",                                         # 6to4 wrapping 127.0.0.1
])
def test_private_addresses_are_refused(address):
    assert not is_public(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:2800:220:1::1"])
def test_public_addresses_are_allowed(address):
    assert is_public(address)


def resolver(table):
    def resolve(host, port, type=None):
        addresses = table[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]
    return resolve


def loopback_only_otherwise_public(address):
    return address == "127.0.0.1" or is_public(address)


@pytest.mark.parametrize("url,reason", [
    ("http://127.0.0.1/", "blocked"),
    ("http://169.254.169.254/latest/meta-data/", "blocked"),
    ("http://[::1]/", "blocked"),
    ("ftp://example.org/file", "bad_url"),
    ("file:///etc/passwd", "bad_url"),
    ("http://example.org:8080/", "blocked"),     # not 80 or 443
    ("http:///nohost", "bad_url"),
])
def test_urls_that_never_leave_the_box(url, reason):
    with pytest.raises(FetchError) as raised:
        Fetcher().fetch(url)
    assert raised.value.reason == reason


def test_a_name_resolving_to_a_private_address_is_refused():
    fetcher = Fetcher(resolve=resolver({"intranet.example": ["10.0.0.5"]}))
    with pytest.raises(FetchError) as raised:
        fetcher.fetch("http://intranet.example/")
    assert raised.value.reason == "blocked"


def test_one_private_answer_among_public_ones_is_enough_to_refuse():
    fetcher = Fetcher(resolve=resolver({"mixed.example": ["93.184.216.34",
                                                         "192.168.0.1"]}))
    with pytest.raises(FetchError) as raised:
        fetcher.fetch("http://mixed.example/")
    assert raised.value.reason == "blocked"


# -- against a real server ---------------------------------------------------


@pytest.fixture
def site():
    @Request.application
    def app(request):
        if request.path == "/page":
            return Response("<html><title>Tea</title><p>Whisked.</p></html>",
                            content_type="text/html; charset=utf-8")
        if request.path == "/to-page":
            return Response("", 302, headers={"Location": "/page"})
        if request.path == "/to-intranet":
            return Response("", 302, headers={"Location": "http://intranet.example/x"})
        if request.path == "/loop":
            return Response("", 302, headers={"Location": "/loop"})
        if request.path == "/big":
            return Response(b"x" * 300_000, content_type="application/octet-stream")
        if request.path == "/slow":
            time.sleep(1.0)
            return Response("late")
        return Response("missing", 404)

    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://site.example:{server.server_port}"
    server.shutdown()


def local_fetcher(**kwargs):
    return Fetcher(resolve=resolver({"site.example": ["127.0.0.1"],
                                     "intranet.example": ["10.0.0.5"]}),
                   address_ok=loopback_only_otherwise_public, allowed_ports=set(),
                   **kwargs)


def test_a_page_is_fetched_with_its_type_and_charset(site):
    page = local_fetcher().fetch(f"{site}/page", accept=("text/html",))
    assert page.content_type == "text/html" and page.charset == "utf-8"
    assert b"Whisked" in page.body


def test_redirects_are_followed_and_reported(site):
    page = local_fetcher().fetch(f"{site}/to-page")
    assert page.url == f"{site}/page"


def test_a_redirect_into_the_private_network_is_refused(site):
    with pytest.raises(FetchError) as raised:
        local_fetcher().fetch(f"{site}/to-intranet")
    assert raised.value.reason == "blocked"


def test_redirect_loops_end(site):
    with pytest.raises(FetchError) as raised:
        local_fetcher().fetch(f"{site}/loop")
    assert raised.value.reason == "redirects"


@pytest.mark.parametrize("path,kwargs,reason", [
    ("/missing", {}, "status"),
    ("/big", {"max_bytes": 100_000}, "too_large"),
    ("/page", {"accept": ("image/",)}, "type"),
])
def test_what_is_refused_on_the_way_back(site, path, kwargs, reason):
    with pytest.raises(FetchError) as raised:
        local_fetcher().fetch(f"{site}{path}", **kwargs)
    assert raised.value.reason == reason


def test_a_slow_source_times_out(site):
    with pytest.raises(FetchError) as raised:
        local_fetcher(timeout=0.3).fetch(f"{site}/slow")
    assert raised.value.reason == "timeout"


def test_the_connection_goes_to_the_address_that_was_checked(site, monkeypatch):
    """A second lookup could answer differently; the fetcher never makes one."""
    lookups = []
    table = resolver({"site.example": ["127.0.0.1"]})

    def counting(host, port, type=None):
        lookups.append(host)
        return table(host, port, type)

    real_getaddrinfo = socket.getaddrinfo

    def no_name_lookups(host, *args, **kwargs):
        # Connecting to an IP literal still passes through getaddrinfo (it
        # parses the literal); only looking the *name* up again is forbidden.
        if host == "site.example":
            raise AssertionError("the connection must not resolve the name again")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", no_name_lookups)
    fetcher = Fetcher(resolve=counting, address_ok=loopback_only_otherwise_public,
                      allowed_ports=set())
    assert b"Whisked" in fetcher.fetch(f"{site}/page").body
    assert lookups == ["site.example"]
