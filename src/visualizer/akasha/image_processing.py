"""Decode untrusted image uploads and build bounded browser-sized variants."""

import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import ImageTooLarge, InvalidImage

FORMAT_MIMES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


@dataclass(frozen=True)
class ImageVariant:
    data: bytes
    mime_type: str
    width: int
    height: int
    sha256: str


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
        width, height = image.size
        original = ImageVariant(
            data=data,
            mime_type=FORMAT_MIMES[format_name],
            width=width,
            height=height,
            sha256=sha256(data).hexdigest(),
        )
        oriented = ImageOps.exif_transpose(image)
        display = self._resize(oriented, format_name, self._display_max_px)
        thumbnail = self._resize(oriented, format_name, self._thumbnail_max_px)
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
            if isinstance(exc, (InvalidImage, ImageTooLarge)):
                raise
            raise InvalidImage("The upload is not a valid JPEG, PNG, or WebP image.") from exc

    @staticmethod
    def _resize(image: Image.Image, format_name: str, max_px: int) -> ImageVariant:
        rendered = image.copy()
        rendered.info.clear()
        rendered.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
        out = BytesIO()
        if format_name == "JPEG":
            rendered.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
        elif format_name == "PNG":
            rendered.save(out, "PNG", optimize=True)
        else:
            rendered.save(out, "WEBP", quality=85, method=4)
        data = out.getvalue()
        return ImageVariant(
            data=data,
            mime_type=FORMAT_MIMES[format_name],
            width=rendered.width,
            height=rendered.height,
            sha256=sha256(data).hexdigest(),
        )


def _safe_filename(filename: str | None, format_name: str) -> str:
    """Keep a display/download name, never a path supplied by the browser."""
    fallback = f"image.{format_name.lower().replace('jpeg', 'jpg')}"
    if not filename:
        return fallback
    name = PurePath(filename.replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:200] or fallback
