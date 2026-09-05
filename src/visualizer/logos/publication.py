"""Publication metadata and whole-series PDF/EPUB rendering."""

from __future__ import annotations

import base64
import html
import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore, Thread
from typing import Any, Protocol

from .errors import (
    ExportJobNotFound,
    ExportUnavailable,
    InvalidPublication,
    LogosError,
)

MAX_COVER_BYTES = 5 * 1024 * 1024
MAX_PUBLICATION_FIELD = 500
# Measured: peak renderer memory runs about 200x the print HTML, so this is the
# largest series that fits inside the app container's memory limit with room for
# the other three services.
MAX_PRINT_HTML_BYTES = 12 * 1024 * 1024
PUBLICATION_FIELDS = (
    "title",
    "subtitle",
    "author",
    "language",
    "publisher",
    "copyright",
)


@dataclass(frozen=True)
class ExportedFile:
    data: bytes
    mimetype: str
    extension: str


class PdfRenderer(Protocol):
    def render(self, source: str) -> bytes: ...


class WeasyPrintRenderer:
    def render(self, source: str) -> bytes:
        try:
            from weasyprint import HTML
        except (ImportError, OSError) as exc:
            raise ExportUnavailable(
                "PDF export is unavailable because its renderer is not installed."
            ) from exc
        return HTML(string=source).write_pdf()


class PublicationService:
    def __init__(
        self,
        store,
        manuscripts,
        pdf_renderer: PdfRenderer | None = None,
        concurrent_renders: int = 1,
    ):
        self.store = store
        self.manuscripts = manuscripts
        self.pdf_renderer = pdf_renderer or WeasyPrintRenderer()
        # Laying out a whole series costs roughly 10 KB of peak memory per word,
        # so a long book is over a gigabyte while it renders. Eight request
        # threads all rendering at once is how a small host runs out of memory
        # and the kernel kills the database instead.
        self._render_slots = BoundedSemaphore(concurrent_renders)

    def get(self, book: str) -> dict:
        chronos_book = self.manuscripts.require(book)
        return self._metadata_view(book, chronos_book.get("title") or book)

    def _metadata_view(self, book: str, default_title: str) -> dict:
        stored = self.store.find_publication(book)
        body = stored or {
            "title": default_title,
            "subtitle": "",
            "author": "",
            "language": "en",
            "publisher": "",
            "copyright": "",
            "rev": 0,
            "created_by": None,
            "updated_by": None,
            "updated_at": None,
        }
        return {
            **body,
            "book": book,
            "has_cover": self.store.has_publication_cover(book),
        }

    def create(self, book: str, payload: Any, author: str) -> dict:
        self.manuscripts.publication(book)
        stored = self.store.create_publication(
            book, validate_publication(payload), author
        )
        return {**stored, "has_cover": self.store.has_publication_cover(book)}

    def update(self, book: str, payload: Any, expected_rev: int, author: str) -> dict:
        self.manuscripts.publication(book)
        stored = self.store.update_publication(
            book, validate_publication(payload), expected_rev, author
        )
        return {**stored, "has_cover": self.store.has_publication_cover(book)}

    def set_cover(self, book: str, data: bytes) -> dict:
        self.manuscripts.publication(book)
        mime = validate_cover(data)
        self.store.set_publication_cover(book, data, mime)
        return {"book": book, "has_cover": True, "mime": mime}

    def delete_cover(self, book: str) -> None:
        self.manuscripts.publication(book)
        self.store.delete_publication_cover(book)

    def cover(self, book: str) -> dict | None:
        self.manuscripts.publication(book)
        return self.store.get_publication_cover(book)

    def export(self, book: str, file_format: str) -> ExportedFile:
        manuscript = self.manuscripts.publication(book)
        if not manuscript["volumes"]:
            raise InvalidPublication("A series with no volumes cannot be exported.")
        metadata = self._metadata_view(book, manuscript.get("title") or book)
        cover = self.store.get_publication_cover(book)
        if file_format == "epub":
            return ExportedFile(
                render_epub(manuscript, metadata, cover),
                "application/epub+zip",
                "epub",
            )
        if file_format == "pdf":
            return ExportedFile(
                self._render_pdf(render_print_html(manuscript, metadata, cover)),
                "application/pdf",
                "pdf",
            )
        raise InvalidPublication("Export format must be 'pdf' or 'epub'.")

    def _render_pdf(self, source: str) -> bytes:
        # The renderer holds the whole laid-out book in memory at once, at
        # roughly two hundred times the size of this HTML. Refusing an
        # over-large series costs one reader an export; attempting it costs
        # everyone the container, because the process is killed mid-render and
        # takes all four services with it.
        if len(source) > MAX_PRINT_HTML_BYTES:
            raise ExportUnavailable(
                "This series is too large to render as one PDF. Export it as "
                "EPUB, which streams, or split it across volumes."
            )
        if not self._render_slots.acquire(blocking=False):
            raise ExportUnavailable(
                "Another PDF export is already running; try again in a moment."
            )
        try:
            return self.pdf_renderer.render(source)
        finally:
            self._render_slots.release()


def background(work: Callable[[], None]) -> None:
    """Default runner: a daemon thread, so a render outlives its request."""
    Thread(target=work, daemon=True).start()


class ExportJobs:
    """Whole-series PDF as a job, because it is minutes of work.

    A synchronous download ties up a request thread for the whole render and
    dies at whatever timeout the reverse proxy in front of the NAS happens to
    use. Starting a job instead lets the reader close the dialog and come back.

    The runner is injected: tests pass one that runs the work inline, so nothing
    here needs a thread to be exercised. State lives in the database rather than
    in the worker that started it, so the download works from either gunicorn
    worker; a job whose worker died is swept by age instead of hanging forever.
    """

    def __init__(
        self,
        store,
        publications: PublicationService,
        *,
        runner: Callable[[Callable[[], None]], None] = background,
        clock: Callable[[], datetime] | None = None,
        keep: timedelta = timedelta(minutes=30),
    ):
        self.store = store
        self.publications = publications
        self.runner = runner
        self.clock = clock or (lambda: datetime.now(UTC))
        self.keep = keep

    def start(self, book: str, owner: str) -> dict:
        self.publications.manuscripts.require(book)
        self.store.expire_export_jobs((self.clock() - self.keep).isoformat())
        job = self.store.create_export_job(book, owner, self.clock().isoformat())
        self.runner(lambda: self._render(book, job))
        return {"book": book, "job": job, "state": "running"}

    def _render(self, book: str, job: str) -> None:
        try:
            exported = self.publications.export(book, "pdf")
            self.store.finish_export_job(job, data=exported.data)
        except LogosError as exc:
            self.store.finish_export_job(job, error=exc.message)
        except Exception:
            # Deliberately broad: this runs on a thread nobody is waiting on, so
            # an escaping exception would leave the job saying "running" until
            # the age sweep, and the reader polling forever.
            self.store.finish_export_job(job, error="The PDF could not be created.")

    def status(self, book: str, owner: str, job: str) -> dict:
        record = self._require(book, owner, job)
        return {
            "book": book,
            "job": job,
            "state": record["state"],
            "error": record.get("error"),
        }

    def collect(self, book: str, owner: str, job: str) -> ExportedFile | None:
        """The finished file, or ``None`` while it is still rendering.

        Collecting is what retires the job: the bytes are handed over once and
        the record goes, so a finished export is not left sitting in the
        database waiting for the age sweep.
        """
        record = self._require(book, owner, job)
        if record["state"] == "running":
            return None
        self.store.delete_export_job(job)
        if record["state"] == "failed":
            raise ExportUnavailable(record.get("error") or "The export failed.")
        return ExportedFile(bytes(record["data"]), "application/pdf", "pdf")

    def _require(self, book: str, owner: str, job: str) -> dict:
        record = self.store.find_export_job(book, owner, job)
        if record is None:
            raise ExportJobNotFound(f"Export job '{job}' was not found.")
        return record


def validate_publication(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise InvalidPublication("Publication metadata must be a JSON object.")
    unexpected = sorted(set(payload) - set(PUBLICATION_FIELDS))
    if unexpected:
        raise InvalidPublication(
            "Publication metadata contains unsupported fields.",
            evidence={"unexpected": unexpected},
        )
    result = {}
    for field in PUBLICATION_FIELDS:
        value = payload.get(field, "")
        if not isinstance(value, str):
            raise InvalidPublication(f"'{field}' must be text.")
        value = value.strip()
        if len(value) > MAX_PUBLICATION_FIELD:
            raise InvalidPublication(
                f"'{field}' must be at most {MAX_PUBLICATION_FIELD} characters."
            )
        result[field] = value
    if not result["title"]:
        raise InvalidPublication("'title' must not be empty.")
    if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", result["language"]):
        raise InvalidPublication("'language' must be a language tag such as 'en'.")
    return result


def validate_cover(data: bytes) -> str:
    if not data:
        raise InvalidPublication("A cover image is required.")
    if len(data) > MAX_COVER_BYTES:
        raise InvalidPublication("A cover image may be at most 5 MiB.")
    expected = (
        "PNG"
        if data.startswith(b"\x89PNG\r\n\x1a\n")
        else ("JPEG" if data.startswith(b"\xff\xd8\xff") else None)
    )
    if expected is None:
        raise InvalidPublication("A cover must be a PNG or JPEG image.")
    # Imported before the `try`, because naming `UnidentifiedImageError` in an
    # `except` clause only works if the import that binds it already ran --
    # inside the `try`, a missing Pillow would raise `NameError` from the
    # handler rather than the error we mean.
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != expected or image.width * image.height > 40_000_000:
                raise InvalidPublication("The cover image is invalid or too large.")
            image.verify()
    except InvalidPublication:
        raise
    except (
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as exc:
        raise InvalidPublication("The cover image is corrupt.") from exc
    return "image/png" if expected == "PNG" else "image/jpeg"


def render_print_html(manuscript: dict, metadata: dict, cover: dict | None) -> str:
    cover_html = ""
    if cover:
        encoded = base64.b64encode(bytes(cover["data"])).decode("ascii")
        cover_html = (
            '<section class="cover"><img alt="" src="data:'
            f'{cover["mime"]};base64,{encoded}"></section>'
        )
    volumes = "".join(_print_volume(volume) for volume in manuscript["volumes"])
    contents = _print_contents(manuscript["volumes"])
    subtitle = (
        f'<p class="subtitle">{_e(metadata["subtitle"])}</p>'
        if metadata["subtitle"]
        else ""
    )
    byline = (
        f'<p class="author">{_e(metadata["author"])}</p>' if metadata["author"] else ""
    )
    copyright_page = "<br>".join(
        _e(value) for value in (metadata["copyright"], metadata["publisher"]) if value
    )
    return f"""<!doctype html>
<html lang="{_e(metadata["language"])}"><head><meta charset="utf-8">
<style>{PRINT_CSS}</style></head><body>{cover_html}
<section class="title-page"><h1>{_e(metadata["title"])}</h1>{subtitle}{byline}</section>
<section class="copyright">{copyright_page}</section>{contents}{volumes}</body></html>"""


def render_epub(manuscript: dict, metadata: dict, cover: dict | None) -> bytes:
    stream = io.BytesIO()
    volume_files = []
    section_files = []
    for volume_index, volume in enumerate(manuscript["volumes"], 1):
        volume_files.append((f"text/v{volume_index}.xhtml", volume))
        for section_index, section in enumerate(volume["sections"], 1):
            name = f"text/v{volume_index}-s{section_index}.xhtml"
            section_files.append((name, volume_index, volume, section))
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        archive.writestr("META-INF/container.xml", CONTAINER_XML)
        archive.writestr("OEBPS/styles.css", EPUB_CSS)
        archive.writestr("OEBPS/title.xhtml", _epub_title(metadata, cover))
        archive.writestr(
            "OEBPS/nav.xhtml",
            _epub_navigation(metadata, volume_files, section_files),
        )
        for name, volume in volume_files:
            archive.writestr("OEBPS/" + name, _epub_volume(metadata, volume))
        for name, _volume_index, volume, section in section_files:
            archive.writestr("OEBPS/" + name, _epub_section(metadata, volume, section))
        if cover:
            extension = "png" if cover["mime"] == "image/png" else "jpg"
            archive.writestr(f"OEBPS/cover.{extension}", bytes(cover["data"]))
        archive.writestr(
            "OEBPS/content.opf",
            _epub_package(
                manuscript["book"], metadata, volume_files, section_files, cover
            ),
        )
    return stream.getvalue()


def _print_volume(volume: dict) -> str:
    sections = "".join(
        _print_section(volume, section, index)
        for index, section in enumerate(volume["sections"], 1)
    )
    return (
        '<section class="volume-title">'
        f"<p>Volume {volume['number']}</p><h1>{_e(volume['title'])}</h1></section>"
        + sections
    )


def _print_section(volume: dict, section: dict, index: int) -> str:
    label = _section_label(section)
    title = section.get("title") or label
    return (
        f'<section class="chapter" id="v{volume["number"]}-s{index}"><header><p>{_e(label)}</p><h1>{_e(title)}</h1></header>'
        f"{_document_html(section['document'])}</section>"
    )


def _print_contents(volumes: list[dict]) -> str:
    groups = []
    for volume in volumes:
        links = "".join(
            f'<li><a href="#v{volume["number"]}-s{index}">'
            f"{_e(section.get('title') or _section_label(section))}</a></li>"
            for index, section in enumerate(volume["sections"], 1)
        )
        groups.append(
            f"<li><strong>Volume {volume['number']}: {_e(volume['title'])}</strong>"
            f"<ol>{links}</ol></li>"
        )
    return (
        '<nav class="contents"><h1>Contents</h1><ol>' + "".join(groups) + "</ol></nav>"
    )


def _document_html(document: dict) -> str:
    return "".join(_block_html(block) for block in document.get("content", []))


def _block_html(block: dict) -> str:
    anchor = _e(block["id"])
    content = "".join(_inline_html(node) for node in block.get("content", []))
    if block["type"] == "paragraph":
        return f'<p id="{anchor}">{content}</p>'
    if block["type"] == "heading":
        level = min(4, block["level"] + 1)
        return f'<h{level} id="{anchor}">{content}</h{level}>'
    tag = "ul" if block["type"] == "bullet_list" else "ol"
    items = "".join(
        "<li>"
        + "".join(_inline_html(node) for node in item.get("content", []))
        + "</li>"
        for item in block.get("content", [])
    )
    return f'<{tag} id="{anchor}">{items}</{tag}>'


def _inline_html(node: dict) -> str:
    if node["type"] == "hard_break":
        return "<br>"
    text = _e(node.get("text", ""))
    if node["type"] == "link":
        href = node.get("href", "")
        if not href.startswith("//") and href.startswith(("/", "http://", "https://")):
            text = f'<a href="{_e(href)}">{text}</a>'
    if node["type"] == "text":
        tags = {"em": "em", "strong": "strong", "strike": "del", "code": "code"}
        for mark in node.get("marks", []):
            tag = tags[mark["type"]]
            text = f"<{tag}>{text}</{tag}>"
    return text


def _epub_title(metadata: dict, cover: dict | None) -> str:
    subtitle = f"<p>{_e(metadata['subtitle'])}</p>" if metadata["subtitle"] else ""
    cover_image = ""
    if cover:
        extension = "png" if cover["mime"] == "image/png" else "jpg"
        cover_image = f'<img class="cover" alt="" src="cover.{extension}"/>'
    return _xhtml(
        metadata,
        "Title",
        f'<section class="title-page">{cover_image}<h1>{_e(metadata["title"])}</h1>{subtitle}<p>{_e(metadata["author"])}</p></section>',
    )


def _epub_section(metadata: dict, volume: dict, section: dict) -> str:
    label = _section_label(section)
    title = section.get("title") or label
    body = (
        f"<article><header><p>Volume {volume['number']} · {_e(volume['title'])}</p>"
        f"<p>{_e(label)}</p><h1>{_e(title)}</h1></header>"
        f"{_document_html(section['document'])}</article>"
    )
    return _xhtml(metadata, title, body)


def _epub_volume(metadata: dict, volume: dict) -> str:
    return _xhtml(
        metadata,
        volume["title"],
        f'<section class="volume-title"><p>Volume {volume["number"]}</p>'
        f"<h1>{_e(volume['title'])}</h1></section>",
    )


def _epub_navigation(
    metadata: dict, volume_files: list[tuple], section_files: list[tuple]
) -> str:
    groups = []
    for volume_index, (volume_name, volume) in enumerate(volume_files, 1):
        sections = "".join(
            f'<li><a href="{_e(name)}">'
            f"{_e(section.get('title') or _section_label(section))}</a></li>"
            for name, index, _volume, section in section_files
            if index == volume_index
        )
        groups.append(
            f'<li><a href="{volume_name}">{_e(volume["title"])}</a>'
            f"<ol>{sections}</ol></li>"
        )
    items = "".join(groups)
    return _xhtml(
        metadata,
        "Contents",
        f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{items}</ol></nav>',
        epub=True,
    )


def _epub_package(
    book: str,
    metadata: dict,
    volume_files: list[tuple],
    section_files: list[tuple],
    cover: dict | None,
) -> str:
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="css" href="styles.css" media-type="text/css"/>',
    ]
    spine = ['<itemref idref="title"/>']
    section_id = 1
    for volume_index, (volume_name, _volume) in enumerate(volume_files, 1):
        manifest.append(
            f'<item id="v{volume_index}" href="{volume_name}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="v{volume_index}"/>')
        for name, index, _volume, _section in section_files:
            if index != volume_index:
                continue
            manifest.append(
                f'<item id="s{section_id}" href="{name}" media-type="application/xhtml+xml"/>'
            )
            spine.append(f'<itemref idref="s{section_id}"/>')
            section_id += 1
    if cover:
        extension = "png" if cover["mime"] == "image/png" else "jpg"
        manifest.append(
            f'<item id="cover" href="cover.{extension}" media-type="{cover["mime"]}" properties="cover-image"/>'
        )
    modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    legacy_cover = '<meta name="cover" content="cover"/>' if cover else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="{_e(metadata["language"])}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">urn:logos:{_e(book)}</dc:identifier><dc:title>{_e(metadata["title"])}</dc:title><dc:language>{_e(metadata["language"])}</dc:language><dc:creator>{_e(metadata["author"])}</dc:creator><dc:publisher>{_e(metadata["publisher"])}</dc:publisher><dc:rights>{_e(metadata["copyright"])}</dc:rights><meta property="dcterms:modified">{modified}</meta>{legacy_cover}</metadata>
<manifest>{"".join(manifest)}</manifest><spine>{"".join(spine)}</spine></package>'''


def _xhtml(metadata: dict, title: str, body: str, *, epub: bool = False) -> str:
    namespace = ' xmlns:epub="http://www.idpf.org/2007/ops"' if epub else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"{namespace} lang="{_e(metadata["language"])}"><head><title>{_e(title)}</title><link rel="stylesheet" type="text/css" href="styles.css"/></head><body>{body}</body></html>'''


def _section_label(section: dict) -> str:
    return (
        f"Chapter {section['number']}"
        if section["kind"] == "chapter"
        else section["kind"].title()
    )


def export_filename(title: str, extension: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-.") or "manuscript"
    return f"{stem}.{extension}"


def _e(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""

EPUB_CSS = """
body { font-family: serif; line-height: 1.55; margin: 5%; }
h1, h2, h3, h4 { font-family: sans-serif; line-height: 1.2; }
.title-page, .volume-title { text-align: center; margin-top: 30%; }
.cover { display: block; max-width: 100%; max-height: 90vh; margin: 0 auto 2em; }
article header { text-align: center; margin: 18% 0 8%; }
article header p { text-transform: uppercase; letter-spacing: .08em; font-size: .75em; }
p { margin: 0 0 .7em; } p + p { text-indent: 1.25em; }
blockquote, ul, ol { margin: 1em 0; } code { font-family: monospace; }
"""

PRINT_CSS = """
@page { size: 6in 9in; margin: .8in .72in .85in; @top-center { content: string(chapter); font-size: 7pt; color: #888; } @bottom-center { content: counter(page); font-size: 8pt; color: #777; } }
@page:first { @bottom-center { content: none; } }
body { color: #171513; font-family: Georgia, 'Liberation Serif', 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.55; }
.cover, .title-page, .volume-title { page-break-after: always; text-align: center; }
.cover { page: cover; margin: -0.8in -.72in -.85in; height: 9in; }
.cover img { width: 100%; height: 100%; object-fit: cover; }
.title-page, .volume-title { padding-top: 34%; }
.title-page h1, .volume-title h1 { font-size: 28pt; letter-spacing: .02em; }
.subtitle { font-size: 15pt; font-style: italic; } .author { margin-top: 3em; letter-spacing: .08em; text-transform: uppercase; }
.copyright, .contents { page-break-after: always; }
.copyright { padding-top: 70%; font-size: 8.5pt; }
.contents h1 { font-family: sans-serif; font-size: 18pt; } .contents ol { list-style: none; padding: 0; }
.contents ol ol { margin: .4em 0 1.1em 1em; } .contents a::after { content: leader('.') target-counter(attr(href), page); }
.volume-title p, .chapter header p { font-family: sans-serif; font-size: 8pt; letter-spacing: .14em; text-transform: uppercase; }
.chapter { page-break-before: always; } .chapter header { text-align: center; margin: 24% 0 3em; }
.chapter header h1 { font-size: 20pt; string-set: chapter content(); } .chapter > p { margin: 0; text-align: justify; hyphens: auto; orphans: 3; widows: 3; }
.chapter > p + p { text-indent: 1.4em; } h2, h3, h4 { font-family: sans-serif; page-break-after: avoid; }
ul, ol { page-break-inside: avoid; } a { color: inherit; text-decoration: none; }
"""
