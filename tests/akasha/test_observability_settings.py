"""Tests for the durable monitoring switch.

Two properties, both of which have to hold on the request path: it is read at
most once per TTL, and a failure to read it never propagates to the caller.
"""

import logging

from visualizer.observability.settings import CachedSwitch, StaticSwitch


class FakeStore:
    def __init__(self, value=None):
        self.value = value
        self.reads = 0
        self.writes = []

    def get_monitoring_enabled(self):
        self.reads += 1
        return self.value

    def set_monitoring_enabled(self, enabled):
        self.writes.append(enabled)
        self.value = enabled


class BrokenStore:
    def __init__(self):
        self.reads = 0

    def get_monitoring_enabled(self):
        self.reads += 1
        raise RuntimeError("mongo unreachable")

    def set_monitoring_enabled(self, enabled):
        raise RuntimeError("mongo unreachable")


def test_static_switch_is_a_plain_toggle():
    switch = StaticSwitch(True)
    assert switch.enabled() is True
    switch.set(False)
    assert switch.enabled() is False


def test_an_unset_switch_uses_the_boot_default():
    assert CachedSwitch(FakeStore(None), default=True).enabled() is True
    assert CachedSwitch(FakeStore(None), default=False).enabled() is False


def test_a_stored_value_overrides_the_boot_default():
    assert CachedSwitch(FakeStore(False), default=True).enabled() is False


def test_the_store_is_read_at_most_once_per_ttl():
    store = FakeStore(True)
    now = [0.0]
    switch = CachedSwitch(store, ttl_seconds=30.0, clock=lambda: now[0])

    for _ in range(100):
        switch.enabled()
    assert store.reads == 1

    now[0] = 29.9
    switch.enabled()
    assert store.reads == 1

    now[0] = 30.0
    switch.enabled()
    assert store.reads == 2


def test_a_change_is_picked_up_once_the_ttl_expires():
    store = FakeStore(True)
    now = [0.0]
    switch = CachedSwitch(store, ttl_seconds=10.0, clock=lambda: now[0])

    assert switch.enabled() is True
    store.value = False
    assert switch.enabled() is True  # still cached
    now[0] = 10.0
    assert switch.enabled() is False


def test_setting_persists_and_takes_effect_immediately():
    store = FakeStore(True)
    now = [0.0]
    switch = CachedSwitch(store, ttl_seconds=999.0, clock=lambda: now[0])
    switch.enabled()

    switch.set(False)

    assert store.writes == [False]
    assert switch.enabled() is False


def test_a_failing_read_never_raises_and_holds_the_last_known_value():
    """A MongoDB blip must not become a failed request."""
    store = FakeStore(False)
    now = [0.0]
    switch = CachedSwitch(store, default=True, ttl_seconds=5.0, clock=lambda: now[0])
    assert switch.enabled() is False

    switch._store = BrokenStore()
    now[0] = 10.0

    assert switch.enabled() is False


def test_a_failure_on_the_very_first_read_falls_back_to_the_default():
    switch = CachedSwitch(BrokenStore(), default=True)
    assert switch.enabled() is True


def test_a_failing_read_still_honours_the_ttl_rather_than_retrying_per_call():
    store = BrokenStore()
    now = [0.0]
    switch = CachedSwitch(store, ttl_seconds=5.0, clock=lambda: now[0])

    for _ in range(50):
        switch.enabled()

    assert store.reads == 1


def test_repeated_failures_are_logged_once_not_every_ttl(caplog):
    store = BrokenStore()
    now = [0.0]
    switch = CachedSwitch(store, ttl_seconds=1.0, clock=lambda: now[0])

    with caplog.at_level(logging.WARNING, logger="visualizer.observability"):
        for tick in range(5):
            now[0] = float(tick)
            switch.enabled()

    assert len(caplog.records) == 1


def test_recovery_re_arms_the_warning():
    store = FakeStore(True)
    now = [0.0]
    switch = CachedSwitch(store, ttl_seconds=1.0, clock=lambda: now[0])
    switch._store = BrokenStore()
    switch.enabled()
    assert switch._degraded is True

    switch._store = store
    now[0] = 5.0
    switch.enabled()

    assert switch._degraded is False
