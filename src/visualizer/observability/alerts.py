"""Threshold evaluation, as structured events rather than sentences.

The admin banner only ever needed strings, but anything that *delivers* an alert
-- email, a webhook, a chat message -- needs to answer "have I already told them
about this?", and that question cannot be answered reliably against a formatted
sentence: ``Volume is 82% full`` becoming ``Volume is 83% full`` is the same
condition, not a new one.

So evaluation produces ``Alert`` records with a stable ``kind``. Rendering is the
last step, never the only representation.

The other half is the distinction between *state* and *events*. ``evaluate``
reports the conditions currently true, which is what a page wants. ``raised``
and ``resolved`` diff two evaluations, which is what a notifier wants. Both are
pure, so a delivery mechanism inherits de-duplication for free instead of
reimplementing it.

This module deliberately contains no delivery of any kind -- see ``Notifier``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .capacity import DANGER, DANGER_AT, OK, WARN, WARN_AT, format_bytes, format_months

# Stable identities. A notifier keys on these, so they must not be reworded
# when the human-facing message is.
VOLUME = "volume"
MEMORY = "memory"
FILL_PROJECTION = "fill_projection"


@dataclass(frozen=True)
class Thresholds:
    """When a reading becomes worth saying out loud.

    Injected rather than read from module constants: a banner and a 3am email
    can reasonably disagree about what deserves attention.
    """

    warn_at: float = WARN_AT
    danger_at: float = DANGER_AT
    fill_months: float = 6.0


@dataclass(frozen=True)
class Alert:
    kind: str
    severity: str
    message: str
    value: float | None = None

    @property
    def identity(self) -> tuple[str, str]:
        """What makes two alerts "the same alert" for de-duplication.

        Severity is part of it, so a warning escalating to danger reads as a new
        event rather than a continuation of the old one.
        """
        return (self.kind, self.severity)

    def as_record(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "value": self.value,
        }

    @classmethod
    def from_record(cls, record: dict) -> Alert:
        return cls(
            kind=record["kind"],
            severity=record["severity"],
            message=record.get("message", ""),
            value=record.get("value"),
        )


def evaluate(
    capacity: dict | None,
    months_until_full: float | None,
    thresholds: Thresholds | None = None,
) -> list[Alert]:
    """Every condition currently worth reporting. Pure; order is stable."""
    limits = thresholds or Thresholds()
    capacity = capacity or {}
    found = [
        _usage_alert(VOLUME, "Volume", capacity.get("volume_total"), capacity.get("volume_free"), limits),
        _usage_alert(MEMORY, "Memory", capacity.get("memory_total"), capacity.get("memory_available"), limits),
        _projection_alert(months_until_full, limits),
    ]
    return [alert for alert in found if alert is not None]


def raised(previous: Iterable[Alert], current: Iterable[Alert]) -> list[Alert]:
    """Alerts in ``current`` that were not already active at this severity."""
    before = {alert.identity for alert in previous}
    return [alert for alert in current if alert.identity not in before]


def resolved(previous: Iterable[Alert], current: Iterable[Alert]) -> list[Alert]:
    """Alerts that were active and no longer are, by kind.

    Keyed on ``kind`` rather than ``identity`` so a warning escalating to danger
    is not also reported as the warning having cleared.
    """
    now_active = {alert.kind for alert in current}
    return [alert for alert in previous if alert.kind not in now_active]


class Notifier(Protocol):
    """Delivers alerts somewhere off-box.

    Implementations must not raise: the flusher logs and continues, but a
    notifier that throws every cycle turns the log into noise. They also must
    not de-duplicate -- ``raised`` has already done that -- so an implementation
    is genuinely just "send these".
    """

    def notify(self, raised: list[Alert], resolved: list[Alert]) -> None: ...


class NullNotifier:
    """The default: evaluation still runs, nothing is delivered.

    Present so the alerting path is exercised in production from day one. A real
    notifier replaces this object and changes nothing else.
    """

    def notify(self, raised: list[Alert], resolved: list[Alert]) -> None:
        return None


# -- individual conditions ----------------------------------------------------


def _usage_alert(
    kind: str, label: str, total: int | None, free: int | None, limits: Thresholds
) -> Alert | None:
    if not total or free is None:
        return None
    fraction = max(0.0, min(1.0, (total - free) / total))
    level = _band(fraction, limits)
    if level == OK:
        return None
    return Alert(
        kind=kind,
        severity=level,
        value=fraction,
        message=(
            f"{label} is {round(fraction * 100)}% full "
            f"({format_bytes(free)} free of {format_bytes(total)})."
        ),
    )


def _projection_alert(months: float | None, limits: Thresholds) -> Alert | None:
    if months is None or months >= limits.fill_months:
        return None
    return Alert(
        kind=FILL_PROJECTION,
        severity=DANGER if months < limits.fill_months / 2 else WARN,
        value=months,
        message=f"At the current growth rate the volume fills in {format_months(months)}.",
    )


def _band(fraction: float, limits: Thresholds) -> str:
    """``capacity.severity`` with injected cut-offs instead of the defaults."""
    if fraction >= limits.danger_at:
        return DANGER
    if fraction >= limits.warn_at:
        return WARN
    return OK
