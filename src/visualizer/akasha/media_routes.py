"""HTTP boundary for Akasha's authenticated, world-scoped media library."""

from io import BytesIO

from flask import jsonify, request, send_file, url_for
from flask_login import current_user, login_required

from visualizer.auth import DELETE, READ, WRITE, Forbidden, is_allowed

from .errors import ImageTooLarge, InvalidImage, MediaInUse, MediaNotFound, ReservedName
from .media_service import MediaService

_MEDIA = "/databases/<database>/media"
_MEDIA_ITEM = _MEDIA + "/<media_id>"
_VARIANTS = ("original", "display", "thumbnail")


def register_media_routes(app, service: MediaService, auth_store, csrf) -> None:
    @app.get(_MEDIA)
    @login_required
    def list_media(database):
        _reject_reserved(database)
        records = service.store.list(database)
        visible = _visible_ids(service, auth_store, database, records)
        shown = records if visible is None else [r for r in records if r["id"] in visible]
        return jsonify(
            {
                "media": [
                    _present(r, database, _can_manage(auth_store, database, r))
                    for r in shown
                ],
                "count": len(shown),
            }
        )

    @app.post(_MEDIA)
    @csrf.exempt
    @login_required
    def upload_media(database):
        _reject_reserved(database)
        if (
            request.content_length is not None
            and request.content_length > service.processor.max_bytes + 1024 * 1024
        ):
            raise ImageTooLarge(
                f"An image upload is at most {service.processor.max_bytes} bytes."
            )
        collection = request.form.get("collection", "").strip()
        article = request.form.get("article", "").strip()
        if not collection or not article:
            raise InvalidImage("An article context is required for an upload.")
        grants = auth_store.grants_for(current_user.username)
        if not is_allowed(grants, WRITE, database, collection, article):
            raise Forbidden("You do not have 'write' permission on this article.")
        upload = request.files.get("file")
        if upload is None:
            raise InvalidImage("Choose an image to upload.")
        data = upload.stream.read(service.processor.max_bytes + 1)
        record = service.upload(
            database,
            current_user.username,
            upload.filename,
            data,
            request.form.get("alt"),
        )
        return jsonify(_present(record, database, can_manage=True)), 201

    @app.get(_MEDIA_ITEM)
    @login_required
    def get_media(database, media_id):
        _reject_reserved(database)
        record = service.store.get(database, media_id)
        _require_visible(service, auth_store, database, record)
        return jsonify(
            _present(record, database, _can_manage(auth_store, database, record))
        )

    @app.patch(_MEDIA_ITEM)
    @csrf.exempt
    @login_required
    def update_media(database, media_id):
        _reject_reserved(database)
        record = service.store.get(database, media_id)
        _require_manager(auth_store, database, record)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InvalidImage("Provide image metadata as a JSON object.")
        updated = service.update_alt(database, media_id, payload.get("alt"))
        return jsonify(_present(updated, database, can_manage=True))

    @app.delete(_MEDIA_ITEM)
    @csrf.exempt
    @login_required
    def delete_media(database, media_id):
        _reject_reserved(database)
        record = service.store.get(database, media_id)
        _require_manager(auth_store, database, record)
        try:
            references = service.delete(database, media_id, force=_flag("force"))
        except MediaInUse as error:
            raise MediaInUse(
                "This image is still used by an article or retained revision.",
                _readable_references(auth_store, database, error.references),
            ) from None
        return jsonify(
            {
                "deleted": media_id,
                "broken_references": _readable_references(
                    auth_store, database, references
                ),
            }
        )

    @app.get(_MEDIA_ITEM + "/<variant>")
    @login_required
    def media_content(database, media_id, variant):
        _reject_reserved(database)
        if variant not in _VARIANTS:
            raise MediaNotFound(f"Image variant '{variant}' does not exist.")
        record = service.store.get(database, media_id)
        _require_visible(service, auth_store, database, record)
        data, details = service.store.read_variant(database, media_id, variant)
        response = send_file(
            BytesIO(data),
            mimetype=details["mime_type"],
            download_name=details["filename"],
            as_attachment=False,
            conditional=True,
            etag=details["sha256"],
        )
        response.cache_control.private = True
        response.cache_control.max_age = 86400
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def _present(record: dict, database: str, can_manage: bool) -> dict:
    presented = dict(record)
    presented["can_manage"] = can_manage
    for variant in _VARIANTS:
        presented[f"{variant}_url"] = url_for(
            "media_content", database=database, media_id=record["id"], variant=variant
        )
    return presented


def _visible_ids(service, auth_store, database, records) -> set[str] | None:
    grants = auth_store.grants_for(current_user.username)
    if is_allowed(grants, READ, database, None, None):
        return None
    visible = {r["id"] for r in records if r["uploader"] == current_user.username}
    visible.update(
        service.references.visible_ids(
            database,
            lambda collection, article: is_allowed(
                grants, READ, database, collection, article
            ),
        )
    )
    return visible


def _require_visible(service, auth_store, database, record) -> None:
    if record["uploader"] == current_user.username:
        return
    visible = _visible_ids(service, auth_store, database, [record])
    if visible is not None and record["id"] not in visible:
        raise Forbidden("You do not have 'read' permission on this image.")


def _require_manager(auth_store, database, record) -> None:
    if not _can_manage(auth_store, database, record):
        raise Forbidden("Only the uploader or world owner may manage this image.")


def _can_manage(auth_store, database, record) -> bool:
    if record["uploader"] == current_user.username:
        return True
    grants = auth_store.grants_for(current_user.username)
    return is_allowed(grants, DELETE, database, None, None)


def _readable_references(auth_store, database, references) -> list[dict]:
    grants = auth_store.grants_for(current_user.username)
    return [
        reference
        for reference in references
        if is_allowed(
            grants,
            READ,
            database,
            reference["collection"],
            reference["article"],
        )
    ]


def _reject_reserved(database: str) -> None:
    if database.startswith("_"):
        raise ReservedName(f"Database '{database}' is reserved and not accessible.")


def _flag(name: str) -> bool:
    return request.args.get(name, "").strip().lower() in ("1", "true", "yes", "on")
