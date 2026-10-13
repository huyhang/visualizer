"""Image candidates: signing them, and fetching one when a caller asks.

A research result lists images it found as URLs. Fetching one later must not
let a caller choose *any* URL -- a compromised NAS would otherwise have a
fetcher inside the tailnet -- so each candidate leaves the worker with a
``fetch_token``: an HMAC of its URL under a key only the worker holds.
``POST /v1/images`` fetches a URL only alongside its own token. The token never
expires; rotating the key (``WORKER_SIGNING_KEY``, or deleting the key file)
revokes every one.

Fetched bytes are checked to be an image Pillow can open, in a format Akasha
stores, before anything is returned.
"""

import base64
import hashlib
import hmac
import io
import os
import secrets
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .fetch import Fetcher, FetchError

PREVIEW_PX = 360
# Exactly what Akasha stores: anything else would be fetched only to be refused.
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
# A decoded-size cap, so a tiny file cannot unpack into gigabytes of pixels.
MAX_PIXELS = 40_000_000


def load_signing_key(configured: str | None, key_file: Path) -> bytes:
    """``WORKER_SIGNING_KEY`` if set, else a key kept beside the job store.

    Generated on first start and kept in the data volume, so tokens survive
    rebuilds; it never leaves the box.
    """
    if configured:
        return hashlib.sha256(configured.encode()).digest()
    if key_file.exists():
        return key_file.read_bytes()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key)
    return key


class TokenSigner:
    def __init__(self, key: bytes):
        self._key = key

    def sign(self, url: str) -> str:
        digest = hmac.new(self._key, b"image-v1:" + url.encode(), hashlib.sha256)
        return base64.urlsafe_b64encode(digest.digest()).decode().rstrip("=")

    def verify(self, url: str, token: str) -> bool:
        return hmac.compare_digest(self.sign(url), token or "")


class Images:
    def __init__(self, signer: TokenSigner, fetcher: Fetcher, max_bytes: int):
        self.signer = signer
        self.fetcher = fetcher
        self.max_bytes = max_bytes

    def fetch(self, url: str, size: str = "full") -> tuple[bytes, str]:
        """(bytes, content type). Raises ``FetchError`` with a safe message."""
        fetched = self.fetcher.fetch(url, max_bytes=self.max_bytes)
        return to_image(fetched.body, size)


def to_image(data: bytes, size: str) -> tuple[bytes, str]:
    """Check ``data`` is a supported image; for a preview, shrink and re-encode."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with warnings.catch_warnings():
            # Pillow only *warns* between 1x and 2x its limit; refuse there too.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            image = Image.open(io.BytesIO(data))
            if image.format not in FORMATS:
                raise FetchError("type", f"Not a supported image format ({image.format})")
            if size != "preview":
                return data, FORMATS[image.format]
            image.thumbnail((PREVIEW_PX, PREVIEW_PX))
        buffer = io.BytesIO()
        transparent = (image.mode in ("RGBA", "LA")
                       or (image.mode == "P" and "transparency" in image.info))
        if transparent:
            image.convert("RGBA").save(buffer, "PNG", optimize=True)
            return buffer.getvalue(), "image/png"
        image.convert("RGB").save(buffer, "JPEG", quality=85)
        return buffer.getvalue(), "image/jpeg"
    except FetchError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, OSError, SyntaxError, ValueError):
        raise FetchError("type", "Not an image the worker can read") from None
