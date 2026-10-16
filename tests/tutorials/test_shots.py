"""The pictures' manifest: written by the camera, read by the page, one shape."""

import json

from visualizer.tutorials.shots import (
    Box,
    ManifestBuilder,
    ManifestShots,
    Ring,
    load_shots,
    ring_within,
    shot_path,
)


def test_a_ring_is_a_padded_percentage_of_its_picture():
    frame = Box(x=100, y=50, width=400, height=200)
    target = Box(x=200, y=100, width=80, height=20)
    assert ring_within(frame, target, pad=5) == Ring(left=23.75, top=22.5, width=22.5, height=15.0)


def test_a_picture_is_named_by_id_width_and_theme():
    assert shot_path("first/name-it", 390, "dark") == "shots/first/name-it-390-dark.webp"


def test_what_the_camera_writes_the_page_reads_back():
    builder = ManifestBuilder()
    ring = Ring(left=1.0, top=2.0, width=3.0, height=4.0)
    builder.add("first/name-it", 1280, Box(0, 0, 560.4, 420), (ring,))
    builder.add("first/name-it", 390, Box(0, 0, 390, 610), ())
    library = ManifestShots.from_manifest(json.loads(builder.json()))
    shot = library.shot("first/name-it")
    assert (shot.desktop.width, shot.desktop.height, shot.desktop.rings) == (560, 420, (ring,))
    assert (shot.phone.width, shot.phone.rings) == (390, ())
    assert library.ids() == frozenset({"first/name-it"})


def test_the_labels_seen_at_either_width_are_kept_together():
    builder = ManifestBuilder()
    builder.add("a/one", 1280, Box(0, 0, 10, 10), (), frozenset({"Create", "Cancel"}))
    builder.add("a/one", 390, Box(0, 0, 10, 10), (), frozenset({"Create", "☰"}))
    shot = ManifestShots.from_manifest(json.loads(builder.json())).shot("a/one")
    assert shot.labels == frozenset({"Create", "Cancel", "☰"})


def test_the_manifest_keeps_its_pictures_in_a_stable_order():
    builder = ManifestBuilder()
    for shot_id in ("b/two", "a/one"):
        for size in (1280, 390):
            builder.add(shot_id, size, Box(0, 0, 10, 10), ())
    assert list(builder.manifest()["shots"]) == ["a/one", "b/two"]


def test_no_manifest_yet_is_no_pictures_yet():
    def missing(_path):
        raise FileNotFoundError

    assert load_shots(read=missing).ids() == frozenset()


def test_an_unknown_picture_is_none():
    assert ManifestShots().shot("nowhere") is None
