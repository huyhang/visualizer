"""Where each part of the stack lives, as the service navigation links to it.

One value built once -- by ``stack.py`` behind one origin, by a service's own
``wsgi.py`` from the environment -- and handed to every app factory, rather
than one keyword per service threaded through each of them. A fifth tab used
to mean a fifth keyword in five factories and every test that built one.

Every field is required. A factory may default the whole value to
``STANDALONE_LINKS``, but never one link of it: a navigation whose links
depend on which caller remembered which argument is a navigation that
silently points somewhere wrong.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceLinks:
    akasha: str
    chronos: str
    prithvi: str
    logos: str
    tutorials: str

    @property
    def account(self) -> str:
        """The account page, which akasha serves for every service."""
        return self._under_akasha("account")

    @property
    def admin(self) -> str:
        """The admin page, which akasha serves for every service."""
        return self._under_akasha("admin")

    @property
    def login(self) -> str:
        """Signing in, for a page anyone may read: akasha's, which lands in Articles."""
        return self._under_akasha("login")

    @property
    def register(self) -> str:
        """Making an account, beside signing in."""
        return self._under_akasha("register")

    def _under_akasha(self, page: str) -> str:
        return self.akasha.rstrip("/") + "/" + page


def tutorials_beside(akasha: str) -> str:
    """Where the tutorials are when nothing says otherwise: beside akasha.

    ``stack.py`` mounts them at ``/tutorials`` of the one origin akasha serves
    from ``/``, which is exactly this.
    """
    return akasha.rstrip("/") + "/tutorials"


# Each service run on its own, on the ports the per-service Dockerfiles and
# `flask run` use. Only the combined stack serves the tutorials.
STANDALONE_LINKS = ServiceLinks(
    akasha="http://localhost:5002",
    chronos="http://localhost:5003",
    prithvi="http://localhost:5004",
    logos="http://localhost:5005",
    tutorials=tutorials_beside("http://localhost:5002"),
)
