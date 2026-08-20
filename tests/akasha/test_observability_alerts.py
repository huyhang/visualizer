"""Tests for threshold evaluation and the notifier seam.

The behaviour that makes a delivery mechanism safe to plug in is here: a
condition that stays true must be reported once, not once per cycle, and it must
survive a rewording of its own message.
"""

import pytest

from visualizer.observability.alerts import (
    FILL_PROJECTION,
    MEMORY,
    VOLUME,
    Alert,
    NullNotifier,
    Thresholds,
    evaluate,
    raised,
    resolved,
)

TB = 1_000_000_000_000


def _capacity(used_fraction=0.5, memory_used=0.5):
    return {
        "volume_total": 4 * TB,
        "volume_free": int(4 * TB * (1 - used_fraction)),
        "memory_total": 8_000_000_000,
        "memory_available": int(8_000_000_000 * (1 - memory_used)),
    }


# -- evaluation ---------------------------------------------------------------


def test_a_healthy_system_raises_nothing():
    assert evaluate(_capacity(), months_until_full=48.0) == []


def test_missing_capacity_raises_nothing_rather_than_guessing():
    assert evaluate(None, None) == []
    assert evaluate({}, None) == []


def test_a_partial_reading_still_evaluates_what_it_has():
    """Memory is unavailable off Linux; the volume alert must still fire."""
    partial = {"volume_total": 100, "volume_free": 2}
    kinds = [a.kind for a in evaluate(partial, None)]
    assert kinds == [VOLUME]


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(0.74, []), (0.75, ["warn"]), (0.89, ["warn"]), (0.90, ["danger"]), (1.0, ["danger"])],
)
def test_volume_severity_bands(fraction, expected):
    alerts = evaluate(_capacity(used_fraction=fraction), None)
    assert [a.severity for a in alerts if a.kind == VOLUME] == expected


def test_memory_is_evaluated_independently_of_the_volume():
    alerts = evaluate(_capacity(used_fraction=0.1, memory_used=0.95), None)
    assert [(a.kind, a.severity) for a in alerts] == [(MEMORY, "danger")]


def test_thresholds_are_injectable():
    strict = Thresholds(warn_at=0.30, danger_at=0.40)
    assert evaluate(_capacity(used_fraction=0.5), None, strict)[0].severity == "danger"
    assert evaluate(_capacity(used_fraction=0.5), None) == []


def test_the_fill_projection_alerts_only_when_close():
    assert evaluate(_capacity(), 12.0) == []
    near = evaluate(_capacity(), 5.0)
    assert [a.kind for a in near] == [FILL_PROJECTION]
    assert near[0].severity == "warn"


def test_an_imminent_fill_is_danger_not_warning():
    assert evaluate(_capacity(), 1.0)[0].severity == "danger"


def test_no_projection_means_no_projection_alert():
    assert [a.kind for a in evaluate(_capacity(), None)] == []


def test_alerts_carry_the_value_not_just_a_sentence():
    alert = evaluate(_capacity(used_fraction=0.95), None)[0]
    assert alert.value == pytest.approx(0.95)
    assert "%" in alert.message


def test_evaluation_order_is_stable():
    both = evaluate(_capacity(used_fraction=0.95, memory_used=0.95), 1.0)
    assert [a.kind for a in both] == [VOLUME, MEMORY, FILL_PROJECTION]


# -- the diff that makes delivery safe ----------------------------------------


def _alert(kind, severity="warn"):
    return Alert(kind=kind, severity=severity, message=f"{kind} {severity}")


def test_a_new_condition_is_raised():
    assert [a.kind for a in raised([], [_alert(VOLUME)])] == [VOLUME]


def test_a_condition_that_persists_is_not_raised_again():
    """The whole point: an hourly scan must not send an hourly email."""
    active = [_alert(VOLUME)]
    assert raised(active, active) == []


def test_a_reworded_message_is_not_a_new_alert():
    """De-duplication keys on identity, never on the rendered sentence."""
    before = [Alert(VOLUME, "warn", "Volume is 82% full.")]
    after = [Alert(VOLUME, "warn", "Volume is 83% full.", value=0.83)]
    assert raised(before, after) == []


def test_escalation_is_reported_as_a_new_event():
    before, after = [_alert(VOLUME, "warn")], [_alert(VOLUME, "danger")]
    assert [a.severity for a in raised(before, after)] == ["danger"]


def test_escalation_is_not_also_reported_as_the_warning_clearing():
    before, after = [_alert(VOLUME, "warn")], [_alert(VOLUME, "danger")]
    assert resolved(before, after) == []


def test_a_condition_that_clears_is_resolved():
    assert [a.kind for a in resolved([_alert(VOLUME)], [])] == [VOLUME]


def test_unrelated_conditions_do_not_mask_each_other():
    before = [_alert(VOLUME)]
    after = [_alert(MEMORY)]
    assert [a.kind for a in raised(before, after)] == [MEMORY]
    assert [a.kind for a in resolved(before, after)] == [VOLUME]


def test_nothing_changing_produces_no_events():
    active = [_alert(VOLUME), _alert(MEMORY, "danger")]
    assert raised(active, active) == [] and resolved(active, active) == []


# -- serialisation -------------------------------------------------------------


def test_an_alert_round_trips_through_storage():
    original = Alert(VOLUME, "danger", "Volume is 95% full.", value=0.95)
    assert Alert.from_record(original.as_record()) == original


def test_a_record_missing_optional_fields_still_loads():
    restored = Alert.from_record({"kind": VOLUME, "severity": "warn"})
    assert (restored.kind, restored.severity, restored.value) == (VOLUME, "warn", None)


# -- the null seam --------------------------------------------------------------


def test_the_default_notifier_accepts_everything_and_does_nothing():
    assert NullNotifier().notify([_alert(VOLUME)], [_alert(MEMORY)]) is None
