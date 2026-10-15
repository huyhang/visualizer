"""What Logos's route modules share: URL templates, guards, request parsing.

Every route module authorises against the same Chronos book grant, reads the
same ``If-Match`` precondition and shapes its responses the same way, so those
live here rather than in any one of them -- ``app.py`` imports all of them, and
the reverse import would be a cycle. ``RouteDeps`` is the bundle of services
``create_app`` builds once and hands to every registrar.
"""

from collections.abc import Callable
from dataclasses import dataclass

from flask import jsonify, request
from flask_login import current_user

from visualizer.auth import AuthStore, is_allowed

from .errors import Forbidden, InvalidRevision, InvalidSearch, PreconditionRequired
from .gateways import ArticleGateway
from .publication import ExportJobs, PublicationService
from .reader import ReaderService
from .search import SearchService
from .services import DraftService, ManuscriptService, SectionService, VolumeService
from .writing import SeriesWritingReview, WritingAdvisor

# Logos reads the Chronos book grant directly -- one resource kind, one grant,
# no second sharing model and no migration for books that already exist.
BOOK_RESOURCE = "book"

BOOK = "/books/<book>"
VOLUME = BOOK + "/volumes/<volume>"
SECTION = VOLUME + "/sections/<section>"
DRAFTS = SECTION + "/drafts"
DRAFT = DRAFTS + "/<draft>"
DRAFT_VERSIONS = DRAFT + "/versions"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def allowed(auth_store, permission: str, book: str) -> bool:
    return is_allowed(
        auth_store.grants_for(current_user.username),
        permission,
        book,
        resource_type=BOOK_RESOURCE,
    )


def authorize(auth_store, permission: str, book: str) -> None:
    if not allowed(auth_store, permission, book):
        raise Forbidden(
            f"You lack '{permission}' permission on Chronos book '{book}'."
        )


def with_permissions(result: dict, auth_store, book: str) -> dict:
    return {
        **result,
        "permissions": {
            "write": allowed(auth_store, "write", book),
            "delete": allowed(auth_store, "delete", book),
        },
    }


def json_body():
    return request.get_json(silent=True)


def expected_rev() -> int:
    """The revision the caller says they read. Required for every mutation.

    Prose is the one thing in this stack a lost update destroys irrecoverably,
    so Logos refuses an unconditional write rather than accepting it the way
    Chronos and Prithvi do. See ``docs/logos/README.md``.
    """
    raw = request.headers.get("If-Match")
    if raw is None:
        raise PreconditionRequired(
            "This request must carry an If-Match header naming the revision read."
        )
    candidate = raw.strip().strip('"')
    if not candidate or candidate == "*":
        raise InvalidRevision("If-Match must name a concrete revision number.")
    try:
        revision = int(candidate)
    except ValueError as exc:
        raise InvalidRevision(f"If-Match is not a revision number: {raw!r}.") from exc
    if revision < 1:
        raise InvalidRevision("A revision number starts at 1.")
    return revision


def truthy(value) -> bool:
    return value is not None and str(value).strip().lower() in _TRUTHY


def writing_dialect(value) -> str:
    if value not in {"en-US", "en-GB"}:
        raise InvalidSearch("The writing dialect must be 'en-US' or 'en-GB'.")
    return value


def resource(result: dict, status: int = 200):
    """A JSON body, with an ETag whenever the resource actually has a revision.

    A manuscript that has no outline yet reads as revision 0 and gets no ETag:
    there is no revision to quote back, and offering ``"0"`` would only hand the
    caller a precondition the API must then reject.
    """
    response = jsonify(result)
    response.status_code = status
    if result.get("rev"):
        response.headers["ETag"] = f'"{result["rev"]}"'
    return response


@dataclass(frozen=True)
class RouteDeps:
    """Everything a registrar's routes close over, built once in ``create_app``.

    Each ``register_*_routes`` takes the whole bundle and names the few it uses,
    so adding a service touches this class and ``create_app`` -- not the
    signature of every registrar.
    """

    auth_store: AuthStore
    manuscripts: ManuscriptService
    volumes: VolumeService
    sections: SectionService
    drafts: DraftService
    readers: ReaderService
    search: SearchService
    publications: PublicationService
    export_jobs: ExportJobs
    articles: ArticleGateway
    writing_advisor: WritingAdvisor
    series_review: SeriesWritingReview
    # The writing page's compiled bundle: which script and styles to link.
    writer_assets: Callable[[], dict | None]
