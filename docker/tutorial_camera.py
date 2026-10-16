"""The tutorials' camera: one state of the UI, at both widths and in both themes.

Used by ``tutorial_shots.py``, inside the screenshot container. A recipe walks
the real UI to the state a lesson describes, then asks the camera for a picture
of part of it with rings round what to press. The camera does the rest: each
width the reader might have, each theme, the crop, where the rings fall, and
which labels were on screen -- and hands every picture to a store it is given.

What a picture *is* -- the file names, the manifest, the ring arithmetic -- is
``visualizer.tutorials.shots``, shared with the page that shows it. Only the
parts that need a browser live here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from playwright.sync_api import Locator, Page

from visualizer.tutorials.shots import DESKTOP, PHONE, THEMES, Box, Ring, ring_within

VIEWPORTS = {DESKTOP: {"width": DESKTOP, "height": 800}, PHONE: {"width": PHONE, "height": 844}}
# Long enough for a resize to lay out and a theme change to repaint.
SETTLE_MS = 450

# What counts as a label: anything a writer could be told to press or read.
_LABELS_JS = """() => {
  const seen = new Set();
  const shown = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const add = text => { text = (text || "").replace(/\\s+/g, " ").trim(); if (text) seen.add(text); };
  document.querySelectorAll(
    "button, [role=button], a, label, legend, h1, h2, h3, [role=tab], summary, option"
  ).forEach(e => {
    if (e.tagName !== "OPTION" && !shown(e)) return;
    add(e.innerText || e.textContent);
    add(e.getAttribute("aria-label"));
  });
  document.querySelectorAll("input[type=submit], input[type=button]").forEach(e => add(e.value));
  return [...seen];
}"""

_THEME_JS = "theme => document.documentElement.setAttribute('data-theme', theme)"


class ShotStore(Protocol):
    """Where pictures go: the camera takes them, the store keeps them."""

    def save(self, shot_id: str, size: int, theme: str, png: bytes) -> None: ...

    def record(self, shot_id: str, size: int, picture: Box,
               rings: tuple[Ring, ...], labels: frozenset[str]) -> None: ...


# -- what to photograph -----------------------------------------------------------

Frame = Callable[[Page], Box]
Target = Callable[[Page], Locator]


def element(target: Target, pad: float = 0) -> Frame:
    """The box of an element, scrolled into view, with ``pad`` around it."""

    def frame(page: Page) -> Box:
        found = target(page)
        found.scroll_into_view_if_needed()
        return padded(_box_of(found), pad, page)

    return frame


def around(*targets: Target, pad: float = 12, within: Target | None = None) -> Frame:
    """The smallest box holding every target, with ``pad`` around it.

    ``within`` -- a dialog, say -- widens the box to the container's full
    width and keeps it inside, so the picture is a clean slice of the dialog
    rather than a sliver with the page showing at its edges. The last target is
    scrolled into view first; the others should be near it.
    """

    def frame(page: Page) -> Box:
        found = [target(page) for target in targets]
        found[-1].scroll_into_view_if_needed()
        boxes = [_box_of(each) for each in found]
        x, y = min(b.x for b in boxes), min(b.y for b in boxes)
        right = max(b.x + b.width for b in boxes)
        bottom = max(b.y + b.height for b in boxes)
        box = padded(Box(x, y, right - x, bottom - y), pad, page)
        if within is None:
            return box
        outer = _box_of(within(page))
        top = max(box.y, outer.y)
        low = min(box.y + box.height, outer.y + outer.height)
        return Box(outer.x, top, outer.width, low - top)

    return frame


def region(x: float, y: float, width: float, height: float) -> Frame:
    """A fixed part of the window, as wide as it is when narrower."""

    def frame(page: Page) -> Box:
        view = page.viewport_size
        return Box(x, y, min(width, view["width"] - x), min(height, view["height"] - y))

    return frame


def window_top(height: float, left: float = 0, top: float = 0) -> Frame:
    """The top of the window, from ``left`` across to its right edge."""

    def frame(page: Page) -> Box:
        view = page.viewport_size
        return Box(left, top, view["width"] - left, min(height, view["height"] - top))

    return frame


def window() -> Frame:
    return lambda page: Box(0, 0, page.viewport_size["width"], page.viewport_size["height"])


def per_size(desktop: Frame, phone: Frame) -> Frame:
    """One frame for the desktop picture and another for the phone's."""
    return lambda page: (phone if page.viewport_size["width"] <= PHONE else desktop)(page)


def padded(box: Box, pad: float, page: Page) -> Box:
    """``box`` grown by ``pad`` a side, kept inside the window."""
    view = page.viewport_size
    x, y = max(box.x - pad, 0), max(box.y - pad, 0)
    right = min(box.x + box.width + pad, view["width"])
    bottom = min(box.y + box.height + pad, view["height"])
    return Box(x, y, right - x, bottom - y)


def _box_of(found: Locator) -> Box:
    box = found.bounding_box()
    if box is None:
        raise LookupError(f"nothing on screen to photograph for {found}")
    return Box(box["x"], box["y"], box["width"], box["height"])


# -- the camera ---------------------------------------------------------------------


@dataclass
class Camera:
    page: Page
    store: ShotStore
    sizes: Sequence[int] = (DESKTOP, PHONE)
    themes: Sequence[str] = THEMES
    # Rings that had nothing to ring at some width, said once the run ends.
    missing: list[str] = field(default_factory=list)

    def shoot(self, shot_id: str, frame: Frame, rings: Sequence[Target] = (),
              prepare: Callable[[Page], None] | None = None) -> None:
        """Photograph the state the page is in, at every width and theme.

        ``prepare`` runs after each change of width, for a state the page lays
        out once rather than on resize -- a popup placed where it opened.
        """
        for size in self.sizes:
            self._at(size)
            if prepare is not None:
                prepare(self.page)
            picture = frame(self.page)
            self.store.record(shot_id, size, picture, self._rings(shot_id, size, picture, rings),
                              self._labels())
            for theme in self.themes:
                self.page.evaluate(_THEME_JS, theme)
                self.page.wait_for_timeout(SETTLE_MS // 3)
                self.store.save(shot_id, size, theme, self._png(picture))
        self.page.evaluate(_THEME_JS, self.themes[0])
        self._at(self.sizes[0])

    def _at(self, size: int) -> None:
        if self.page.viewport_size != VIEWPORTS[size]:
            self.page.set_viewport_size(VIEWPORTS[size])
            self.page.wait_for_timeout(SETTLE_MS)

    def _rings(self, shot_id: str, size: int, picture: Box,
               targets: Sequence[Target]) -> tuple[Ring, ...]:
        rings = []
        for target in targets:
            found = target(self.page)
            box = found.bounding_box() if found.count() else None
            if box is None or box["width"] == 0:
                self.missing.append(f"{shot_id} at {size}px: no {found}")
                continue
            rings.append(ring_within(picture, Box(box["x"], box["y"], box["width"], box["height"])))
        return tuple(rings)

    def _labels(self) -> frozenset[str]:
        return frozenset(self.page.evaluate(_LABELS_JS))

    def _png(self, picture: Box) -> bytes:
        return self.page.screenshot(clip={
            "x": picture.x, "y": picture.y, "width": picture.width, "height": picture.height,
        })


# -- the UI, in a writer's words ----------------------------------------------------


@dataclass
class Ui:
    """The actions a lesson describes, by the labels a writer sees."""

    page: Page
    base: str

    def go(self, path: str) -> None:
        self.page.goto(self.base + path)
        self.settle()

    def settle(self, extra_ms: int = 300) -> None:
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(extra_ms)

    def button(self, label: str) -> Locator:
        return self.page.get_by_role("button", name=label, exact=True).first

    def link(self, label: str) -> Locator:
        return self.page.get_by_role("link", name=label, exact=True).first

    def press(self, label: str) -> None:
        self.button(label).click()
        self.settle()

    def dialog(self) -> Locator:
        return self.page.locator("dialog[open], [role=dialog]").last

    def field(self, label: str, within: Locator | None = None) -> Locator:
        """The input a visible label names, whether or not it is wired to it."""
        scope = within if within is not None else self.page
        wired = scope.get_by_label(label, exact=True)
        if wired.count():
            return wired.first
        holder = scope.locator(".field, label").filter(
            has=self.page.get_by_text(label, exact=True)
        )
        return holder.locator("input, textarea, select").first

    def fill(self, label: str, value: str, within: Locator | None = None) -> None:
        self.field(label, within).fill(value)

    def quiet_dialog_backdrop(self) -> None:
        """Clear a dialog's dimmed backdrop, so its picture has no grey frame."""
        self.page.evaluate("""() => {
          document.querySelectorAll('dialog[open], [role=dialog]').forEach(d => {
            for (let e = d.parentElement; e && e !== document.body; e = e.parentElement) {
              if (getComputedStyle(e).position === 'fixed') {
                e.style.background = 'transparent'; e.style.backdropFilter = 'none';
              }
            }
          });
          const s = document.createElement('style');
          s.textContent = 'dialog::backdrop{background:transparent!important}';
          document.head.appendChild(s);
        }""")

    def wait_for_toasts(self) -> None:
        """Let a "Created …" toast leave before a picture is taken."""
        self.page.wait_for_timeout(2600)
