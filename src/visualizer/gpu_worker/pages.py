"""Web pages as research reads them: clean text, a title, images, a license.

``extract()`` turns fetched HTML into a ``Page`` with the standard library's
parser -- no browser, nothing executed. Navigation, scripts, forms and page
furniture are dropped; what remains is the text a reader would read, which is
both what the model sees and what its quotes are checked against.

``find_quote()`` is the anti-hallucination rule: a quote counts only if it
appears in the page text. "Verbatim" here forgives only what HTML itself makes
arbitrary -- runs of whitespace, curly versus straight quotes, en/em dashes --
and the passage returned is the page's own normalised text, so the excerpt a
writer sees is exactly what the page says.
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .fetch import Fetched

# Shorter than this, a "quote" is a phrase that could appear anywhere.
MIN_QUOTE_CHARS = 12

_SKIPPED = {"script", "style", "noscript", "template", "svg", "nav", "footer",
            "header", "aside", "form", "iframe", "button", "select", "textarea"}
_BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr",
           "blockquote", "section", "article", "figcaption", "dd", "dt", "pre",
           "main", "table", "ul", "ol"}
# Curly quotes, dashes and the minus sign fold to ASCII; odd spaces become
# plain ones and zero-width ones vanish. Escaped, because they are invisible.
_TYPOGRAPHY = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u2009": " ", "\u202f": " ", "\u200b": "", "\ufeff": "",
})
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.translate(_TYPOGRAPHY)).strip()


def find_quote(quote: str, haystack: str) -> str | None:
    """The passage of ``haystack`` (already normalised) that ``quote`` is, or None."""
    wanted = normalize(quote or "").strip(" .,;:…\"'")
    if len(wanted) < MIN_QUOTE_CHARS:
        return None
    return wanted if wanted in haystack else None


@dataclass
class PageImage:
    url: str
    caption: str


@dataclass
class Page:
    url: str
    title: str
    site: str
    language: str | None
    text: str                       # blocks separated by blank lines
    images: list[PageImage] = field(default_factory=list)
    license: str | None = None

    @property
    def haystack(self) -> str:
        """The text quotes are matched against: normalised, one line."""
        return normalize(self.text)


class _Reader(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.blocks: list[str] = []
        self.current: list[str] = []
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False
        self.og_title = None
        self.language = None
        self.license = None
        self.images: list[PageImage] = []
        self.figure_images: list[str] | None = None
        self.caption_parts: list[str] | None = None

    # -- structure -----------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        attrs = {name: value or "" for name, value in attrs}
        if tag == "html" and attrs.get("lang"):
            self.language = attrs["lang"].split("-")[0].lower()
        elif tag == "base" and attrs.get("href"):
            self.base = urljoin(self.base, attrs["href"])
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            self._meta(attrs)
        elif tag in ("link", "a") and "license" in attrs.get("rel", "").lower().split():
            self.license = self.license or attrs.get("href") or None
        if tag in _SKIPPED:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "figure":
            self.figure_images = []
        elif tag == "figcaption":
            self.caption_parts = []
        elif tag == "img":
            self._img(attrs)
        if tag in _BLOCKS:
            self._end_block()

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in _SKIPPED:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == "figcaption" and self.caption_parts is not None:
            caption = normalize("".join(self.caption_parts))
            for url in self.figure_images or []:
                self._add_image(url, caption)
            self.figure_images = []
            self.caption_parts = None
        elif tag == "figure":
            self.figure_images = None
        if tag in _BLOCKS:
            self._end_block()

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
            return
        if self.skip_depth:
            return
        self.current.append(data)
        if self.caption_parts is not None:
            self.caption_parts.append(data)

    # -- details -------------------------------------------------------------

    def _meta(self, attrs):
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        content = attrs.get("content", "").strip()
        if key == "og:title" and content:
            self.og_title = content
        elif key in ("dc.rights", "dcterms.rights", "license") and content:
            self.license = self.license or content

    def _img(self, attrs):
        src = attrs.get("src", "")
        if not src or src.startswith("data:") or src.lower().endswith(".svg"):
            return
        if _tiny(attrs.get("width")) or _tiny(attrs.get("height")):
            return  # icons, spacers, avatars
        url = urljoin(self.base, src)
        if self.figure_images is not None:
            self.figure_images.append(url)
        alt = normalize(attrs.get("alt", ""))
        if len(alt) >= 15:
            self._add_image(url, alt)

    def _add_image(self, url, caption):
        if not caption or urlsplit(url).scheme not in ("http", "https"):
            return
        for image in self.images:
            if image.url == url:
                if len(caption) > len(image.caption):
                    image.caption = caption
                return
        self.images.append(PageImage(url=url, caption=caption[:300]))

    def _end_block(self):
        text = normalize("".join(self.current))
        if text:
            self.blocks.append(text)
        self.current = []


def _tiny(value: str | None) -> bool:
    try:
        return value is not None and int(str(value).rstrip("px")) < 100
    except ValueError:
        return False


def extract(fetched: Fetched) -> Page:
    reader = _Reader(fetched.url)
    reader.feed(_decode(fetched))
    reader.close()
    reader._end_block()
    title = normalize(reader.og_title or "".join(reader.title_parts)) or fetched.url
    host = urlsplit(fetched.url).hostname or ""
    return Page(
        url=fetched.url,
        title=title[:300],
        site=host.removeprefix("www."),
        language=reader.language,
        text="\n\n".join(reader.blocks),
        images=reader.images,
        license=reader.license[:300] if reader.license else None,
    )


def _decode(fetched: Fetched) -> str:
    charset = fetched.charset
    if not charset:
        sniff = re.search(rb'<meta[^>]+charset=["\']?([A-Za-z0-9_-]+)', fetched.body[:4096],
                          re.IGNORECASE)
        charset = sniff.group(1).decode() if sniff else "utf-8"
    try:
        return fetched.body.decode(charset, errors="replace")
    except LookupError:
        return fetched.body.decode("utf-8", errors="replace")
