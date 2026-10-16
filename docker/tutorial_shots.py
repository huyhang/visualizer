"""Take every picture the tutorials show, in a throwaway stack.

    docker compose -f docker/docker-compose.screenshots.yml run --rm --build tutorial-shots

The entrypoint of the ``tutorial-shots`` service. It starts the dev server --
in memory, empty, no demo story -- makes an administrator first, so the writer
it photographs is an ordinary account like most readers', then plays every
recipe in ``tutorial_recipes.py`` in the course's order. Each picture is
written as WebP, at both widths and in both themes, into
``src/visualizer/tutorials/static/shots/`` (mounted at /out) with
``shots.json`` beside it; a picture no recipe took this time is removed.

A recipe that fails stops the run and leaves the pictures as they were: the
lesson has gone stale, and saying so is the job. A screenshot of the moment
it failed goes to /debug when that is mounted.
"""

from __future__ import annotations

import io
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright
from tutorial_camera import VIEWPORTS, Camera, Ui
from tutorial_recipes import RECIPES

from visualizer.tutorials.shots import DESKTOP, Box, ManifestBuilder, Ring, shot_path

OUT = Path(os.environ.get("TUTORIAL_SHOTS_OUT", "/out"))
DEBUG = Path(os.environ.get("TUTORIAL_SHOTS_DEBUG", "/debug"))
PORT = 5050
BASE = f"http://127.0.0.1:{PORT}"
# Sharp text, a fraction of PNG's size.
WEBP_QUALITY = 90
ADMIN = {"username": "keeper", "email": "keeper@example.com", "password": "keeps-the-keys-2026"}


def say(message: str) -> None:
    print(f"tutorial-shots: {message}", flush=True)


@dataclass
class FolderStore:
    """Pictures as files under ``root``, and the manifest describing them."""

    root: Path
    manifest: ManifestBuilder = field(default_factory=ManifestBuilder)
    written: set[Path] = field(default_factory=set)

    def save(self, shot_id: str, size: int, theme: str, png: bytes) -> None:
        path = self.root / shot_path(shot_id, size, theme).removeprefix("shots/")
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.open(io.BytesIO(png)).save(path, "WEBP", quality=WEBP_QUALITY, method=6)
        self.written.add(path)

    def record(self, shot_id: str, size: int, picture: Box,
               rings: tuple[Ring, ...], labels: frozenset[str]) -> None:
        self.manifest.add(shot_id, size, picture, rings, labels)

    def finish(self) -> None:
        (self.root / "shots.json").write_text(self.manifest.json())
        for stale in sorted(set(self.root.rglob("*.webp")) - self.written):
            stale.unlink()
            say(f"removed {stale.relative_to(self.root)}, which no lesson shows now")
        for folder in sorted(self.root.rglob("*"), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()


def start_server(log: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "visualizer.devserver", "--fresh", "--no-reload",
         "--no-rate-limit", "--port", str(PORT), "--data", "/tmp/tutorial-shots.json"],
        cwd="/app", stdout=log.open("w"), stderr=subprocess.STDOUT, start_new_session=True,
    )


def wait_for_port(timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("the dev server did not start; see /tmp/tutorial-shots-server.log")


def make_admin() -> None:
    """The first account is the administrator; take it, so the writer is not."""
    request = urllib.request.Request(
        f"{BASE}/register", data=json.dumps(ADMIN).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        if response.status >= 400:
            raise RuntimeError(f"could not make the administrator: {response.status}")


def stop(server: subprocess.Popen) -> None:
    try:
        os.killpg(server.pid, signal.SIGINT)
        server.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(server.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def photograph(store: FolderStore) -> list[str]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORTS[DESKTOP], color_scheme="light")
        ui, camera = Ui(page, BASE), Camera(page, store)
        for recipe in RECIPES:
            say(recipe.__name__.replace("_", "-"))
            try:
                recipe(ui, camera)
            except Exception:
                if DEBUG.is_dir():
                    page.screenshot(path=str(DEBUG / f"{recipe.__name__}.png"), full_page=True)
                raise
        browser.close()
    return camera.missing


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    server = start_server(Path("/tmp/tutorial-shots-server.log"))
    try:
        wait_for_port()
        make_admin()
        store = FolderStore(OUT)
        missing = photograph(store)
        store.finish()
    finally:
        stop(server)
    shots = len(store.manifest.entries)
    say(f"{shots} pictures, {len(store.written)} files, in {OUT}")
    for line in missing:
        say(f"warning: a ring had nothing to ring -- {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
