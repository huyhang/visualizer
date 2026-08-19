"""The admin-only observability page and its pause switch.

Both routes use the project's existing ``@admin_required`` guard and ordinary
CSRF-protected forms -- there is no separate authorization path here and nothing
is exempted, so these endpoints are protected exactly like the rest of the admin
console.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from flask import flash, redirect, render_template, request, url_for

from visualizer.auth import Forbidden, admin_required

from .view import (
    DEFAULT_WINDOW,
    ROUTE_LIMIT,
    WINDOWS,
    build_overview,
    window_hours,
)

# How much per-writer storage history the growth projection may consider.
_HISTORY_DAYS = 90
_PROBLEM_ROWS = 50


def register_observability_page(app, observability) -> None:
    """Attach ``/admin/observability`` and its switch to ``app``."""
    # Lets the admin console link to the page only when it actually exists --
    # an app built without a metrics store has no such route to point at.
    app.context_processor(lambda: {"observability_enabled": True})

    @app.get("/admin/observability")
    @admin_required
    def observability_page():
        window = _window()
        now = datetime.now(UTC)
        return render_template(
            "observability.html",
            overview=_overview(observability.store, window, now),
            windows=list(WINDOWS),
            route_limit=ROUTE_LIMIT,
            monitoring_enabled=observability.switch.enabled(),
        )

    @app.post("/admin/observability/switch")
    @admin_required
    def set_monitoring():
        observability.switch.set(_requested_state())
        flash(
            "Monitoring resumed."
            if observability.switch.enabled()
            else "Monitoring paused. Existing history is kept.",
            "success",
        )
        return redirect(url_for("observability_page"))


def _window() -> str:
    requested = request.args.get("window", DEFAULT_WINDOW)
    return requested if requested in WINDOWS else DEFAULT_WINDOW


def _requested_state() -> bool:
    value = request.form.get("enabled")
    if value not in ("true", "false"):
        raise Forbidden("Invalid monitoring setting.")
    return value == "true"


def _overview(store, window: str, now: datetime):
    """Read everything the page needs, then hand it to the pure shaper."""
    since = now - timedelta(hours=window_hours(window))
    latest_day = store.latest_storage_day()
    return build_overview(
        request_rows=store.request_hours(since=since),
        storage_rows=store.storage_days(since=latest_day) if latest_day else [],
        storage_history=store.storage_days(since=now - timedelta(days=_HISTORY_DAYS)),
        capacity=store.latest_capacity(),
        problems=store.problems(limit=_PROBLEM_ROWS),
        window=window,
        now=now,
    )
