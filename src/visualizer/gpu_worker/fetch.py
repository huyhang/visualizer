"""Fetching from the open web without becoming a way into the private network.

Everything the worker downloads -- research pages, image candidates -- goes
through ``Fetcher``. A URL can come, indirectly, from a web page the model
read, so the fetcher treats every one as hostile:

- only ``http``/``https``, only ports 80 and 443;
- every address the host resolves to must be public (``is_global``): no
  loopback, private ranges, link-local (cloud metadata), CGNAT/Tailscale
  100.64.0.0/10, unique-local IPv6, or IPv4 hidden inside IPv6;
- the connection is made to the address that was checked, never re-resolved,
  so a DNS answer cannot change between the check and the connect;
- every redirect hop is checked again, and there are at most five;
- a size cap, a per-read timeout and an overall deadline.
"""

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

DEFAULT_PORTS = {"http": 80, "https": 443}
MAX_REDIRECTS = 5
USER_AGENT = "visualizer-research/1 (private, non-commercial)"


class FetchError(Exception):
    """Why a URL could not be fetched. ``message`` is safe to show and log."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Fetched:
    url: str              # after redirects
    content_type: str     # lower-case, without parameters
    charset: str | None
    body: bytes


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
    return ip.is_global and not ip.is_multicast


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, timeout):
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout, context):
        super().__init__(host, port, timeout=timeout, context=context)
        self._address = address

    def connect(self):
        sock = socket.create_connection((self._address, self.port), self.timeout)
        # The certificate is checked against the *name*, as the browser would.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class Fetcher:
    def __init__(self, *, timeout: float = 15.0, max_bytes: int = 5 * 1024 * 1024,
                 resolve: Callable = socket.getaddrinfo,
                 address_ok: Callable[[str], bool] = is_public,
                 allowed_ports: set[int] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._resolve = resolve
        self._address_ok = address_ok
        # An empty set means any port: only tests, against a local server, pass one.
        self._ports = {80, 443} if allowed_ports is None else allowed_ports
        self._clock = clock
        self._tls = ssl.create_default_context()

    def fetch(self, url: str, *, accept: tuple[str, ...] | None = None,
              max_bytes: int | None = None) -> Fetched:
        limit = max_bytes or self.max_bytes
        deadline = self._clock() + self.timeout
        for _ in range(MAX_REDIRECTS + 1):
            response, connection = self._open(url, deadline)
            try:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location:
                        raise FetchError("status", "A redirect without a destination")
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise FetchError("status", f"The source answered {response.status}")
                content_type, charset = _content_type(response.getheader("Content-Type"))
                if accept and not content_type.startswith(accept):
                    raise FetchError("type", f"Unexpected content type {content_type!r}")
                body = self._read(response, limit, deadline)
                return Fetched(url=url, content_type=content_type, charset=charset,
                               body=body)
            finally:
                connection.close()
        raise FetchError("redirects", "Too many redirects")

    # -- one hop -------------------------------------------------------------

    def _open(self, url: str, deadline: float):
        parts = urlsplit(url)
        if parts.scheme not in DEFAULT_PORTS or not parts.hostname:
            raise FetchError("bad_url", "Only http and https URLs can be fetched")
        try:
            port = parts.port or DEFAULT_PORTS[parts.scheme]
        except ValueError:
            raise FetchError("bad_url", "The URL has an invalid port") from None
        if self._ports and port not in self._ports:
            raise FetchError("blocked", "Only ports 80 and 443 are fetched")
        address = self._checked_address(parts.hostname, port)
        timeout = max(0.1, min(self.timeout, deadline - self._clock()))
        if parts.scheme == "https":
            connection = _PinnedHTTPSConnection(parts.hostname, port, address, timeout,
                                                self._tls)
        else:
            connection = _PinnedHTTPConnection(parts.hostname, port, address, timeout)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        try:
            connection.request("GET", path, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,image/*;q=0.9,*/*;q=0.5",
                "Accept-Encoding": "identity",
            })
            return connection.getresponse(), connection
        except TimeoutError:
            connection.close()
            raise FetchError("timeout", "The source did not answer in time") from None
        except (OSError, http.client.HTTPException, ssl.SSLError):
            connection.close()
            raise FetchError("unreachable", "The source is unreachable") from None

    def _checked_address(self, host: str, port: int) -> str:
        """The address to connect to, once every address for ``host`` passed."""
        try:
            literal = ipaddress.ip_address(host)
            addresses = [str(literal)]
        except ValueError:
            try:
                infos = self._resolve(host, port, type=socket.SOCK_STREAM)
            except (OSError, UnicodeError):
                raise FetchError("unreachable", "The source's name does not resolve") \
                    from None
            addresses = list(dict.fromkeys(info[4][0] for info in infos))
        if not addresses:
            raise FetchError("unreachable", "The source's name does not resolve")
        if not all(self._address_ok(address) for address in addresses):
            raise FetchError("blocked", "Refused: the source is not a public address")
        return addresses[0]

    def _read(self, response, limit: int, deadline: float) -> bytes:
        chunks, size = [], 0
        try:
            while True:
                if self._clock() > deadline:
                    raise FetchError("timeout", "The source did not answer in time")
                chunk = response.read(64 * 1024)
                if not chunk:
                    return b"".join(chunks)
                size += len(chunk)
                if size > limit:
                    raise FetchError("too_large",
                                     f"Larger than the {limit // (1024 * 1024)} MB limit")
                chunks.append(chunk)
        except TimeoutError:
            raise FetchError("timeout", "The source did not answer in time") from None
        except (OSError, http.client.HTTPException):
            raise FetchError("unreachable", "The source stopped answering") from None


def _content_type(header: str | None) -> tuple[str, str | None]:
    if not header:
        return "", None
    kind, _, params = header.partition(";")
    charset = None
    for param in params.split(";"):
        name, _, value = param.strip().partition("=")
        if name.lower() == "charset" and value:
            charset = value.strip().strip('"')
    return kind.strip().lower(), charset
