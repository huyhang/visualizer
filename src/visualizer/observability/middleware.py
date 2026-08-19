"""The only Flask-aware part of the package.

Installed as one ``before_request`` / ``after_request`` pair. Everything it does
is in-process arithmetic against the recorder -- no socket, no database, no
blocking call -- so the cost a request pays for being observed is a timestamp
and a handful of increments.

Two exclusions are deliberate. ``/health`` is a liveness probe fired on a timer
and would otherwise dominate every count, and static assets are not API
workload. Routes are recorded as Flask *rule templates*, never raw paths, so
document ids and usernames cannot leak from the URL into telemetry.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter

from flask import Flask, g, request
from flask.signals import got_request_exception
from flask_login import current_user

from .aggregation import route_key
from .recorder import Sample

LOGGER = logging.getLogger("visualizer.observability")

_START = "_observability_started"
_ERROR = "_observability_error"

ANONYMOUS = "anonymous"

_EXCLUDED_RULES = frozenset({"/health"})
_EXCLUDED_PREFIXES = ("/static/",)


def register_observability(
    app: Flask, recorder, switch, service: str, *, now=None
) -> None:
    """Attach request observability to ``app``.

    :param recorder: receives a ``Sample`` per request; does no I/O.
    :param switch: ``.enabled()`` decides whether to record; must not raise.
    :param service: which half of the stack this app is, for the labels.
    """
    clock = now or (lambda: datetime.now(UTC))
    state = {"warned": False}

    @app.before_request
    def _start_timing():
        g.__dict__[_START] = perf_counter()

    @got_request_exception.connect_via(app)
    def _note_exception(sender, exception, **extra):
        g.__dict__[_ERROR] = type(exception).__name__

    @app.after_request
    def _finish_timing(response):
        try:
            _observe(recorder, switch, service, response, clock)
        except Exception:
            # Deliberately broad, and the last of three such handlers in this
            # package. Whatever went wrong measuring a request, the request
            # itself already succeeded and must be returned. Logged once per
            # process so a systematic fault is visible without flooding.
            if not state["warned"]:
                state["warned"] = True
                LOGGER.exception("request observability failed; continuing untimed")
        return response


def _observe(recorder, switch, service: str, response, clock) -> None:
    started = g.__dict__.get(_START)
    if started is None or _excluded(request.url_rule) or not switch.enabled():
        return
    recorder.record(
        Sample(
            service=service,
            route=route_key(request.url_rule.rule if request.url_rule else None),
            method=request.method,
            status=response.status_code,
            writer=_writer(),
            duration_ms=max(0.0, (perf_counter() - started) * 1000.0),
            bytes_in=max(0, request.content_length or 0),
            bytes_out=max(0, response.calculate_content_length() or 0),
            at=clock(),
            error=g.__dict__.get(_ERROR),
        )
    )


def _excluded(url_rule) -> bool:
    if url_rule is None:
        return False
    rule = url_rule.rule
    return rule in _EXCLUDED_RULES or rule.startswith(_EXCLUDED_PREFIXES)


def _writer() -> str:
    return current_user.username if current_user.is_authenticated else ANONYMOUS
