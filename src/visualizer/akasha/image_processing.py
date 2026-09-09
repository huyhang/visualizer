"""Decode untrusted image uploads and build bounded browser-sized variants."""

import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import ImageTooLarge, InvalidImage
from .metadata import strip_metadata

FORMAT_MIMES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

# Above this many distinct colours an image is photographic and quantising it
# would be visible. At or below it the artwork is already palette-scale, and
# resampling is the only reason the derivative has more colours than the source.
_PALETTE_LIMIT = 256


@dataclass(frozen=True)
class ImageVariant:
    data: bytes
    mime_type: str
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class EncodeHints:
    """What the *source* bytes tell us about how to encode a derivative.

    Both facts are about the upload, not the resized copy, so they are read
    once and carried down rather than re-derived per variant.
    """

    lossless_webp: bool
    palette_scale: bool


@dataclass(frozen=True)
class ProcessedImage:
    filename: str
    format: str
    width: int
    height: int
    original: ImageVariant
    display: ImageVariant
    thumbnail: ImageVariant


class ImageProcessor:
    """Pillow-backed processor whose limits are injected by configuration."""

    def __init__(
        self,
        max_bytes: int,
        max_pixels: int,
        display_max_px: int,
        thumbnail_max_px: int = 360,
    ):
        if min(max_bytes, max_pixels, display_max_px, thumbnail_max_px) < 1:
            raise ValueError("Image processing limits must be positive.")
        self.max_bytes = max_bytes
        self._max_pixels = max_pixels
        self._display_max_px = display_max_px
        self._thumbnail_max_px = thumbnail_max_px

    def process(self, data: bytes, filename: str | None) -> ProcessedImage:
        if not data:
            raise InvalidImage("Choose an image to upload.")
        if len(data) > self.max_bytes:
            raise ImageTooLarge(
                f"An image upload is at most {self.max_bytes} bytes."
            )
        image, format_name = self._decode(data)
        oriented = ImageOps.exif_transpose(image)
        # The archived copy keeps every pixel of the upload, but not the story
        # attached to it: this is what the lightbox serves, so a phone's GPS
        # tag would otherwise reach every reader of the article. Its rotation
        # survives, so it hangs the same way up as the copies derived from it.
        archived = strip_metadata(data, format_name, _orientation(image))
        original = ImageVariant(
            data=archived,
            mime_type=FORMAT_MIMES[format_name],
            # As displayed, matching the derivatives: a portrait phone photo is
            # stored landscape and turned by its Exif, and reporting the stored
            # shape would contradict what every client actually renders.
            width=oriented.width,
            height=oriented.height,
            sha256=sha256(archived).hexdigest(),
        )
        hints = EncodeHints(
            lossless_webp=format_name == "WEBP" and _is_lossless_webp(data),
            palette_scale=_is_palette_scale(oriented),
        )
        display = self._variant(
            oriented, format_name, self._display_max_px, hints, original
        )
        thumbnail = self._variant(
            oriented, format_name, self._thumbnail_max_px, hints, original
        )
        return ProcessedImage(
            filename=_safe_filename(filename, format_name),
            format=format_name,
            width=oriented.width,
            height=oriented.height,
            original=original,
            display=display,
            thumbnail=thumbnail,
        )

    def _decode(self, data: bytes) -> tuple[Image.Image, str]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                probe = Image.open(BytesIO(data))
                format_name = str(probe.format or "").upper()
                if format_name not in FORMAT_MIMES:
                    raise InvalidImage("Upload a JPEG, PNG, or WebP image.")
                if getattr(probe, "is_animated", False):
                    raise InvalidImage("Animated images are not supported.")
                width, height = probe.size
                if width * height > self._max_pixels:
                    raise ImageTooLarge(
                        f"An image may contain at most {self._max_pixels} pixels."
                    )
                probe.verify()
                image = Image.open(BytesIO(data))
                image.load()
                return image, format_name
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ImageTooLarge(
                f"An image may contain at most {self._max_pixels} pixels."
            ) from None
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            # The refusals raised above are AkashaErrors, which none of these
            # cover, so they pass through this handler untouched.
            raise InvalidImage(
                "The upload is not a valid JPEG, PNG, or WebP image."
            ) from exc

    def _variant(
        self,
        image: Image.Image,
        format_name: str,
        max_px: int,
        hints: EncodeHints,
        original: ImageVariant,
    ) -> ImageVariant:
        """A bounded copy -- or the original, when the copy would cost more.

        A derivative larger than the thing it derives from is not a saving, and
        it happens routinely: resampling flat artwork invents gradients a small
        palette used to cover. Serving the original is both fewer bytes and
        better pixels, so there is no reason to prefer the derivative.
        """
        candidate = self._render(image, format_name, max_px, hints)
        return candidate if len(candidate.data) < len(original.data) else original

    def _render(
        self, image: Image.Image, format_name: str, max_px: int, hints: EncodeHints
    ) -> ImageVariant:
        rendered = image.copy()
        rendered.info.clear()
        rendered.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
        candidates = [_encode(rendered, format_name, hints)]
        if format_name == "PNG" and hints.palette_scale:
            candidates.append(_encode_palette_png(rendered))
        data = min(candidates, key=len)
        return ImageVariant(
            data=data,
            mime_type=FORMAT_MIMES[format_name],
            width=rendered.width,
            height=rendered.height,
            sha256=sha256(data).hexdigest(),
        )


def _encode(image: Image.Image, format_name: str, hints: EncodeHints) -> bytes:
    out = BytesIO()
    if format_name == "JPEG":
        image.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
    elif format_name == "PNG":
        image.save(out, "PNG", optimize=True)
    elif hints.lossless_webp:
        # Pillow defaults WebP to lossy q80. Doing that to a lossless upload
        # discards quality nobody asked to lose -- and on flat artwork it also
        # multiplies the file size, because lossy codecs hate hard edges.
        image.save(out, "WEBP", lossless=True, method=4)
    else:
        image.save(out, "WEBP", quality=85, method=4)
    return out.getvalue()


def _encode_palette_png(image: Image.Image) -> bytes:
    """A PNG quantised back to the colour depth the source artwork had."""
    out = BytesIO()
    image.convert("RGB").quantize(colors=_PALETTE_LIMIT).save(out, "PNG", optimize=True)
    return out.getvalue()


def _is_palette_scale(image: Image.Image) -> bool:
    """Whether the source is drawn artwork rather than a photograph.

    Transparency is excluded because quantising drops the alpha channel, and
    a silently flattened logo is a worse outcome than a large thumbnail.
    """
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        return False
    return image.convert("RGB").getcolors(maxcolors=_PALETTE_LIMIT) is not None


def _orientation(image: Image.Image) -> int:
    """The Exif rotation the upload declared, or 1 when it declared none."""
    try:
        return int(image.getexif().get(274) or 1)
    except (AttributeError, TypeError, ValueError, OSError):
        return 1


def _is_lossless_webp(data: bytes) -> bool:
    """Whether a WebP carries the lossless (VP8L) bitstream.

    Pillow does not surface this on the opened image, so read the container.
    The chunks are walked rather than probing a fixed offset: an extended file
    (VP8X) puts its bitstream after the header and any ICC/animation chunks.
    """
    if len(data) < 16 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return False
    offset = 12
    while offset + 4 <= len(data):
        fourcc = data[offset:offset + 4]
        if fourcc == b"VP8L":
            return True
        if fourcc == b"VP8 ":
            return False
        if offset + 8 > len(data):
            return False  # a fourcc with no length: truncated, decide nothing
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        offset += 8 + size + (size & 1)  # chunks are padded to an even length
    return False


def _safe_filename(filename: str | None, format_name: str) -> str:
    """Keep a display/download name, never a path supplied by the browser."""
    fallback = f"image.{format_name.lower().replace('jpeg', 'jpg')}"
    if not filename:
        return fallback
    name = PurePath(filename.replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:200] or fallback
