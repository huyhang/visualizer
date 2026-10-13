"""The job store: survives restarts, forgets inputs, and lets results expire."""

from datetime import timedelta

from visualizer.gpu_worker.store import JobStore

from .conftest import RESEARCH_JOB


def create(store, clock, key=None):
    job, created = store.create("research", RESEARCH_JOB["request"], "hash", key,
                                clock())
    return job, created


def test_jobs_survive_a_restart(tmp_path, clock):
    path = tmp_path / "jobs.sqlite3"
    job, _ = create(JobStore(path), clock)
    assert JobStore(path).get(job["id"])["state"] == "queued"


def test_what_was_running_fails_on_restart_and_queued_work_waits(tmp_path, clock):
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    running, _ = create(store, clock)
    waiting, _ = create(store, clock)
    store.claim_next(clock())
    reopened = JobStore(path)
    assert reopened.recover(clock()) == 1
    error = reopened.get(running["id"])["error"]
    assert error["code"] == "unavailable" and error["retryable"] is True
    assert reopened.get(waiting["id"])["state"] == "queued"


def test_a_jobs_input_is_erased_when_it_ends(store, clock):
    done, _ = create(store, clock)
    cancelled, _ = create(store, clock)
    assert store.raw_request(done["id"]) is not None
    store.claim_next(clock())
    store.finish(done["id"], "done", clock(), result={"ok": True})
    store.cancel(cancelled["id"], clock())
    assert store.raw_request(done["id"]) is None
    assert store.raw_request(cancelled["id"]) is None


def test_deleted_rows_are_overwritten_on_disk(store):
    assert store._db.execute("PRAGMA secure_delete").fetchone()[0] == 1


def test_results_expire(store, clock):
    job, _ = create(store, clock)
    store.claim_next(clock())
    store.finish(job["id"], "done", clock(), result={"ok": True})
    clock.advance(hours=23)
    assert store.sweep(clock()) == 0
    clock.advance(hours=1)
    assert store.sweep(clock()) == 1
    assert store.get(job["id"]) is None


def test_unfinished_jobs_never_expire(store, clock):
    create(store, clock)
    clock.advance(days=30)
    assert store.sweep(clock()) == 0


def test_a_key_that_raced_in_returns_the_first_job(store, clock):
    first, created = create(store, clock, key="k")
    again, created_again = create(store, clock, key="k")
    assert (created, created_again) == (True, False)
    assert again["id"] == first["id"]


def test_a_late_answer_does_not_overwrite_a_cancellation(store, clock):
    job, _ = create(store, clock)
    store.claim_next(clock())
    store.cancel(job["id"], clock())
    store.finish(job["id"], "done", clock(), result={"ok": True})
    assert store.get(job["id"])["state"] == "cancelled"


def test_positions_close_up_as_the_queue_moves(store, clock):
    a, _ = create(store, clock)
    b, _ = create(store, clock)
    c, _ = create(store, clock)
    store.cancel(a["id"], clock())
    assert (store.get(b["id"])["position"], store.get(c["id"])["position"]) == (1, 2)
    store.claim_next(clock())
    assert store.get(b["id"])["position"] is None
    assert store.get(c["id"])["position"] == 1
    assert store.counts() == {"queued": 1, "running": 1}


def test_ttl_is_configurable(tmp_path, clock):
    store = JobStore(tmp_path / "j.sqlite3", ttl=timedelta(hours=1))
    job, _ = create(store, clock)
    store.claim_next(clock())
    store.finish(job["id"], "done", clock(), result={})
    assert store.get(job["id"])["expires_at"] == "2026-10-13T10:00:00Z"
