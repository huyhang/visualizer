"""Whole-series publication metadata and downloadable formats."""

import base64
import io
import threading
import zipfile
from xml.etree import ElementTree

import pytest

from visualizer.logos.app import create_app
from visualizer.logos.errors import ExportUnavailable, InvalidPublication
from visualizer.logos.publication import PublicationService, validate_cover
from visualizer.logos.services import ManuscriptService

from .conftest import BOOK, SECTION, VOLUME, document, login, section_payload

PUBLICATION = f"/books/{BOOK}/publication"


def _metadata():
    return {
        "title": "The Ember Pact",
        "subtitle": "A Chronicle",
        "author": "Mara Vale",
        "language": "en",
        "publisher": "North Light",
        "copyright": "Copyright 2026 Mara Vale",
    }


def test_publication_metadata_is_versioned_and_writer_owned(volume, reader):
    default = volume.get(PUBLICATION).get_json()
    assert default["title"] == "The Ember Pact" and default["rev"] == 0

    created = volume.post(PUBLICATION, json=_metadata())
    assert created.status_code == 201
    assert reader.get(PUBLICATION).get_json()["author"] == "Mara Vale"
    assert (
        reader.put(
            PUBLICATION, json=_metadata(), headers={"If-Match": '"1"'}
        ).status_code
        == 403
    )


def test_cover_is_checked_by_content_and_downloadable(volume):
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    saved = volume.put(PUBLICATION + "/cover", data=png)
    assert saved.get_json()["mime"] == "image/png"
    assert volume.get(PUBLICATION + "/cover").data == png
    with pytest.raises(InvalidPublication):
        validate_cover(b"not an image")


def test_epub_contains_every_section_in_reading_order(section):
    section.post(
        f"/books/{BOOK}/me/items",
        json={
            "kind": "note",
            "volume": VOLUME,
            "section": SECTION,
            "block": "p1",
            "text": "private editorial note",
        },
    )
    section.post(f"/books/{BOOK}/volumes/two", json={"title": "Volume Two"})
    section.post(
        f"/books/{BOOK}/volumes/two/sections/ending",
        json=section_payload(
            kind="epilogue", title="Afterward", events=(), doc=document("The end.")
        ),
    )
    response = section.get(f"/books/{BOOK}/exports/epub")
    assert response.status_code == 200
    assert response.mimetype == "application/epub+zip"
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.infolist()[0].compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"
        chapter = archive.read("OEBPS/text/v1-s1.xhtml").decode()
        volume_leaf = archive.read("OEBPS/text/v2.xhtml").decode()
        ending = archive.read("OEBPS/text/v2-s1.xhtml").decode()
        assert "The gate was open." in chapter
        assert "Volume Two" in volume_leaf
        assert "The end." in ending
        assert SECTION not in chapter  # display metadata, not storage ids
        assert "private editorial note" not in chapter
        for name in ("OEBPS/content.opf", "OEBPS/nav.xhtml"):
            ElementTree.fromstring(archive.read(name))


def test_pdf_renderer_is_injected(
    section, logos_store, chronos_gateway, article_gateway
):
    class FakePdf:
        def render(self, source):
            assert "The gate was open." in source
            return b"%PDF-fake"

    manuscripts = ManuscriptService(logos_store, chronos_gateway, article_gateway)
    exported = PublicationService(logos_store, manuscripts, FakePdf()).export(
        BOOK, "pdf"
    )
    assert exported.data == b"%PDF-fake"


def test_only_one_pdf_renders_at_a_time(
    section, logos_store, chronos_gateway, article_gateway
):
    """Laying out a series costs about 10 KB of peak memory per word.

    Eight request threads rendering at once is how a small host runs out of
    memory, and the kernel answers that by killing the biggest process, which is
    the database rather than the export. Turning the second caller away costs
    them a retry; not turning them away costs everyone the book.
    """
    started, release = threading.Event(), threading.Event()

    class SlowPdf:
        def render(self, source):
            started.set()
            assert release.wait(timeout=5)
            return b"%PDF-slow"

    manuscripts = ManuscriptService(logos_store, chronos_gateway, article_gateway)
    publications = PublicationService(logos_store, manuscripts, SlowPdf())
    done = {}
    worker = threading.Thread(
        target=lambda: done.setdefault("pdf", publications.export(BOOK, "pdf").data)
    )
    worker.start()
    try:
        assert started.wait(timeout=5)
        with pytest.raises(ExportUnavailable):
            publications.export(BOOK, "pdf")
        # EPUB holds no slot: it is a stdlib zip and costs almost nothing.
        assert publications.export(BOOK, "epub").mimetype == "application/epub+zip"
    finally:
        release.set()
        worker.join(timeout=5)

    assert done["pdf"] == b"%PDF-slow"
    # The slot is returned, so the next export is not turned away.
    assert publications.export(BOOK, "pdf").data == b"%PDF-slow"


def test_publication_metadata_reads_no_prose(section, logos_store, monkeypatch):
    """Reading the title should not assemble the manuscript to find it."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("reading publication metadata loaded section prose")

    monkeypatch.setattr(logos_store, "list_sections", refuse)

    assert section.get(PUBLICATION).get_json()["title"] == "The Ember Pact"


def _pdf_app(logos_store, chronos_gateway, article_gateway, auth_store, renderer):
    """A client whose export runner is inline, so a job finishes before it returns."""
    app = create_app(
        logos_store,
        chronos_gateway,
        article_gateway,
        auth_store,
        "test-secret",
        pdf_renderer=renderer,
        export_runner=lambda work: work(),
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    browser = app.test_client()
    assert login(browser).status_code == 200
    return browser


def test_a_pdf_is_started_then_collected(
    section, logos_store, chronos_gateway, article_gateway, auth_store
):
    class FakePdf:
        def render(self, source):
            assert "Contents" in source
            return b"%PDF-fake"

    browser = _pdf_app(
        logos_store, chronos_gateway, article_gateway, auth_store, FakePdf()
    )
    started = browser.post(f"/books/{BOOK}/exports/pdf")
    assert started.status_code == 202
    job = started.get_json()["job"]

    collected = browser.get(f"/books/{BOOK}/exports/pdf/{job}")
    assert collected.data == b"%PDF-fake"
    assert collected.mimetype == "application/pdf"
    assert collected.headers["Content-Disposition"].endswith('"The-Ember-Pact.pdf"')
    # Collecting retires the job rather than leaving the bytes in the database.
    assert browser.get(f"/books/{BOOK}/exports/pdf/{job}").status_code == 404


def test_a_failed_render_is_reported_not_left_running(
    section, logos_store, chronos_gateway, article_gateway, auth_store
):
    class BrokenPdf:
        def render(self, source):
            raise RuntimeError("pango exploded")

    browser = _pdf_app(
        logos_store, chronos_gateway, article_gateway, auth_store, BrokenPdf()
    )
    job = browser.post(f"/books/{BOOK}/exports/pdf").get_json()["job"]
    failed = browser.get(f"/books/{BOOK}/exports/pdf/{job}")

    assert failed.status_code == 503
    assert failed.get_json()["code"] == "EXPORT_UNAVAILABLE"


def test_one_readers_export_job_is_not_anothers(
    section, logos_store, chronos_gateway, article_gateway, auth_store
):
    class FakePdf:
        def render(self, source):
            return b"%PDF-fake"

    app = create_app(
        logos_store, chronos_gateway, article_gateway, auth_store, "test-secret",
        pdf_renderer=FakePdf(), export_runner=lambda work: work(),
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    owner, other = app.test_client(), app.test_client()
    assert login(owner).status_code == 200
    assert login(other, "devi").status_code == 200

    job = owner.post(f"/books/{BOOK}/exports/pdf").get_json()["job"]

    assert other.get(f"/books/{BOOK}/exports/pdf/{job}").status_code == 404
    assert owner.get(f"/books/{BOOK}/exports/pdf/{job}").status_code == 200


def test_a_series_too_large_to_lay_out_is_refused(
    section, logos_store, chronos_gateway, article_gateway
):
    class NeverCalled:
        def render(self, source):
            raise AssertionError("an oversized series reached the renderer")

    manuscripts = ManuscriptService(logos_store, chronos_gateway, article_gateway)
    publications = PublicationService(logos_store, manuscripts, NeverCalled())
    monkey = publications._render_pdf

    with pytest.raises(ExportUnavailable, match="too large"):
        monkey("x" * (12 * 1024 * 1024 + 1))
