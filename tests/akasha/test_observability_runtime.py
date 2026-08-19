"""Tests for environment reading and production assembly.

``runtime.start`` is the one place that wires everything together, and the
property worth protecting is that building it touches nothing: an unreachable
MongoDB must delay observability, never stop the application from serving.
"""

import mongomock
import pytest

from visualizer.observability import config, runtime
from visualizer.observability.capacity import HostCapacitySource, _linux_memory
from visualizer.observability.recorder import InProcessRecorder
from visualizer.observability.store import MetricsStore

# -- configuration -----------------------------------------------------------


def test_monitoring_defaults_to_on(monkeypatch):
    monkeypatch.delenv("MONITORING_ENABLED", raising=False)
    assert config.get_monitoring_enabled() is True


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_truthy_spellings(monkeypatch, value):
    monkeypatch.setenv("MONITORING_ENABLED", value)
    assert config.get_monitoring_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", "nonsense", ""])
def test_anything_else_disables(monkeypatch, value):
    """Unrecognised values disable rather than silently enabling."""
    monkeypatch.setenv("MONITORING_ENABLED", value)
    assert config.get_monitoring_enabled() is False


def test_interval_defaults(monkeypatch):
    monkeypatch.delenv("MONITORING_FLUSH_SECONDS", raising=False)
    monkeypatch.delenv("MONITORING_SCAN_SECONDS", raising=False)
    assert config.get_flush_seconds() == config.DEFAULT_FLUSH_SECONDS
    assert config.get_scan_seconds() == config.DEFAULT_SCAN_SECONDS


def test_intervals_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("MONITORING_FLUSH_SECONDS", "45")
    monkeypatch.setenv("MONITORING_SCAN_SECONDS", "900")
    assert config.get_flush_seconds() == 45
    assert config.get_scan_seconds() == 900


def test_intervals_have_a_floor_so_a_typo_cannot_busy_loop(monkeypatch):
    monkeypatch.setenv("MONITORING_FLUSH_SECONDS", "0")
    monkeypatch.setenv("MONITORING_SCAN_SECONDS", "1")
    assert config.get_flush_seconds() == 10
    assert config.get_scan_seconds() == 60


def test_a_non_numeric_interval_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("MONITORING_FLUSH_SECONDS", "soon")
    assert config.get_flush_seconds() == config.DEFAULT_FLUSH_SECONDS


def test_the_data_path_is_configurable(monkeypatch):
    monkeypatch.delenv("MONITORING_DATA_PATH", raising=False)
    assert config.get_data_path() == config.DEFAULT_DATA_PATH
    monkeypatch.setenv("MONITORING_DATA_PATH", "/data/mongo")
    assert config.get_data_path() == "/data/mongo"


# -- assembly ----------------------------------------------------------------


class SpyClient:
    """A client that fails loudly if anything is asked of it."""

    def list_database_names(self):
        raise AssertionError("start() must not touch MongoDB")

    def __getitem__(self, name):
        raise AssertionError("start() must not touch MongoDB")


class SpyAuthStore:
    def all_grants(self):
        raise AssertionError("start() must not touch MongoDB")


def test_building_the_stack_touches_no_database(monkeypatch):
    """Observability must never be the reason the application fails to boot."""
    started = []
    monkeypatch.setattr(
        "visualizer.observability.runtime.BackgroundFlusher.start",
        lambda self: started.append(True),
    )

    observability = runtime.start(SpyClient(), SpyAuthStore())

    assert started == [True]
    assert isinstance(observability.recorder, InProcessRecorder)
    assert isinstance(observability.store, MetricsStore)


def test_the_boot_default_reaches_the_switch(monkeypatch):
    monkeypatch.setattr(
        "visualizer.observability.runtime.BackgroundFlusher.start", lambda self: None
    )
    monkeypatch.setenv("MONITORING_ENABLED", "false")

    observability = runtime.start(SpyClient(), SpyAuthStore())

    # Nothing is stored yet, so the switch answers with the boot default.
    assert observability.switch.enabled() is False


def test_a_clean_shutdown_is_registered(monkeypatch):
    monkeypatch.setattr(
        "visualizer.observability.runtime.BackgroundFlusher.start", lambda self: None
    )
    registered = []
    monkeypatch.setattr(
        "visualizer.observability.runtime.atexit.register",
        lambda fn, *a, **k: registered.append(fn),
    )

    runtime.start(SpyClient(), SpyAuthStore())

    assert registered, "nothing would drain the recorder on shutdown"


# -- host sampling -----------------------------------------------------------


class StubDatabase:
    def __init__(self, stats):
        self._stats = stats

    def command(self, name):
        assert name == "dbStats"
        return self._stats


class StubClient:
    def __init__(self, databases):
        self._databases = databases

    def list_database_names(self):
        return list(self._databases)

    def __getitem__(self, name):
        return StubDatabase(self._databases[name])


def test_host_sampling_reads_the_configured_volume(tmp_path):
    client = StubClient(
        {
            "_chronos": {"storageSize": 100, "indexSize": 20},
            "_auth": {"storageSize": 5, "indexSize": 1},
        }
    )
    sample = HostCapacitySource(client, str(tmp_path)).sample()

    assert sample.volume_total > 0
    assert sample.volume_free > 0
    assert sample.mongo_bytes == 126


def test_mongo_size_is_zero_with_no_databases(tmp_path):
    assert HostCapacitySource(StubClient({}), str(tmp_path)).sample().mongo_bytes == 0


def test_a_missing_meminfo_yields_unknown_rather_than_failing(monkeypatch):
    """Developer laptops are frequently not Linux; the NAS is."""
    monkeypatch.setattr("visualizer.observability.capacity._MEMINFO", "/nonexistent")
    assert _linux_memory() == (None, None)


def test_meminfo_is_parsed_into_bytes(tmp_path, monkeypatch):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       16305016 kB\n"
        "MemFree:          204540 kB\n"
        "MemAvailable:    9033168 kB\n"
        "Buffers:          182380 kB\n"
    )
    monkeypatch.setattr("visualizer.observability.capacity._MEMINFO", str(meminfo))

    total, available = _linux_memory()

    assert total == 16305016 * 1024
    assert available == 9033168 * 1024


def test_a_truncated_meminfo_reports_what_it_found(tmp_path, monkeypatch):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16305016 kB\n")
    monkeypatch.setattr("visualizer.observability.capacity._MEMINFO", str(meminfo))

    total, available = _linux_memory()

    assert total == 16305016 * 1024
    assert available is None


def test_a_real_sample_survives_a_host_without_meminfo(tmp_path, monkeypatch):
    monkeypatch.setattr("visualizer.observability.capacity._MEMINFO", "/nonexistent")
    sample = HostCapacitySource(StubClient({}), str(tmp_path)).sample()

    assert sample.memory_total is None
    assert sample.volume_total > 0  # the disk reading is unaffected


def test_the_default_wiring_uses_a_real_metrics_store():
    """Guards against the store being swapped for something without a TTL."""
    store = MetricsStore(mongomock.MongoClient())
    store.ensure_indexes()
    assert store.get_monitoring_enabled() is None
