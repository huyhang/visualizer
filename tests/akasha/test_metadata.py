"""Container surgery on uploads: drop the description, keep every pixel.

The archived copy is what the full-size view serves, so anything left in it is
published. These check both halves of the bargain -- that the metadata really
goes, and that the picture really does not change.
"""

from io import BytesIO

import pytest
from PIL import Image

from visualizer.akasha.metadata import strip_metadata


def _photo(size=(120, 90)):
    return Image.effect_noise(size, 40).convert("RGB")


def _saved(fmt, **kwargs):
    out = BytesIO()
    _photo().save(out, fmt, **kwargs)
    return out.getvalue()


def _pixels(data):
    return Image.open(BytesIO(data)).convert("RGB").tobytes()


def _exif():
    exif = Image.Exif()
    exif[271] = "SecretCam"          # Make
    exif[305] = "SecretApp 1.0"      # Software
    exif[37510] = "shot at home"     # UserComment
    return exif


def test_jpeg_exif_is_removed_and_the_picture_is_untouched():
    raw = _saved("JPEG", quality=95, exif=_exif())
    cleaned = strip_metadata(raw, "JPEG")

    assert len(cleaned) < len(raw)
    assert dict(Image.open(BytesIO(raw)).getexif())          # it was there
    assert not dict(Image.open(BytesIO(cleaned)).getexif())  # and now is not
    assert _pixels(cleaned) == _pixels(raw)


def test_a_jpeg_comment_goes_too():
    raw = _saved("JPEG", quality=90, comment=b"a private note")
    assert b"a private note" in raw
    assert b"a private note" not in strip_metadata(raw, "JPEG")


def test_an_icc_profile_survives_because_dropping_it_changes_colour():
    profile = b"\x00" * 128 + b"acsp" + b"\x00" * 60
    out = BytesIO()
    _photo().save(out, "JPEG", quality=90, exif=_exif(), icc_profile=profile)
    raw = out.getvalue()

    cleaned = strip_metadata(raw, "JPEG")
    assert not dict(Image.open(BytesIO(cleaned)).getexif())
    assert Image.open(BytesIO(cleaned)).info.get("icc_profile") is not None


def test_png_text_chunks_are_removed_and_the_picture_is_untouched():
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "Someone")
    info.add_text("Comment", "a private note")
    out = BytesIO()
    _photo().save(out, "PNG", pnginfo=info)
    raw = out.getvalue()

    cleaned = strip_metadata(raw, "PNG")
    assert b"a private note" in raw
    assert b"a private note" not in cleaned
    assert cleaned.endswith(b"IEND\xae\x42\x60\x82")
    assert _pixels(cleaned) == _pixels(raw)


def test_webp_exif_is_removed_and_the_picture_is_untouched():
    out = BytesIO()
    _photo().save(out, "WEBP", lossless=True, exif=_exif())
    raw = out.getvalue()

    cleaned = strip_metadata(raw, "WEBP")
    assert b"SecretCam" in raw
    assert b"SecretCam" not in cleaned
    assert _pixels(cleaned) == _pixels(raw)


def test_a_webp_header_stops_advertising_the_chunks_that_were_dropped():
    out = BytesIO()
    _photo().save(out, "WEBP", lossless=True, exif=_exif())
    cleaned = strip_metadata(out.getvalue(), "WEBP")

    assert cleaned[:4] == b"RIFF"
    assert int.from_bytes(cleaned[4:8], "little") == len(cleaned) - 8
    if cleaned[12:16] == b"VP8X":
        assert cleaned[20] & 0x08 == 0  # Exif-present flag
        assert cleaned[20] & 0x04 == 0  # XMP-present flag


def test_an_upload_with_nothing_to_strip_is_returned_unchanged():
    """Byte-identical, not merely equivalent -- the archive should be the file
    that was sent whenever there is no reason for it not to be."""
    for fmt in ("JPEG", "PNG", "WEBP"):
        raw = _saved(fmt)
        assert strip_metadata(raw, fmt) is raw


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xff\xd8",                      # a JPEG that stops after SOI
        b"\xff\xd8\xff\xe1\x00\x02",      # APP1 with a length and no payload
        b"\xff\xd8\xff\xe1\xff\xff" + b"\x00" * 8,   # length past the end
        b"\xff\xd8\xff\xe1\x00\x00zzzz",  # length below the legal minimum
        b"\x89PNG\r\n\x1a\n",             # a PNG with no chunks
        b"\x89PNG\r\n\x1a\n" + b"\xff\xff\xff\xffiTXt",  # chunk past the end
        b"RIFF\x04\x00\x00\x00WEBP",      # a WebP with no chunks
        b"RIFF\x00\x00\x00\x00WEBPEXIF\xff\xff\xff\xff",  # size past the end
        b"not an image at all",
    ],
)
@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_malformed_input_is_returned_rather_than_raising(data, fmt):
    """This runs after the decoder accepted the file, so it must never be the
    thing that fails the upload."""
    assert isinstance(strip_metadata(data, fmt), bytes)


def test_an_unknown_format_is_left_alone():
    raw = _saved("PNG")
    assert strip_metadata(raw, "GIF") is raw


def _rotated_jpeg(orientation=6):
    exif = _exif()
    exif[274] = orientation
    out = BytesIO()
    _photo().save(out, "JPEG", quality=95, exif=exif)
    return out.getvalue()


def test_a_rotated_jpeg_keeps_its_rotation_and_loses_everything_else():
    """Orientation is layout, not provenance. Dropping it would leave the
    archived copy -- the one the full-size view serves -- lying on its side."""
    raw = _rotated_jpeg()
    cleaned = strip_metadata(raw, "JPEG", orientation=6)

    kept = dict(Image.open(BytesIO(cleaned)).getexif())
    assert kept == {274: 6}
    assert b"SecretCam" not in cleaned
    assert _pixels(cleaned) == _pixels(raw)
    assert len(cleaned) < len(raw)


def test_an_unrotated_jpeg_gets_no_exif_block_back():
    raw = _saved("JPEG", quality=95, exif=_exif())
    assert not dict(Image.open(BytesIO(strip_metadata(raw, "JPEG", 1))).getexif())


@pytest.mark.parametrize("fmt,kwargs", [("PNG", {}), ("WEBP", {"lossless": True})])
def test_a_rotated_png_or_webp_is_left_intact_rather_than_rebuilt(fmt, kwargs):
    """Their Exif lives in a chunk we would have to re-encode to replace, so a
    rotated one keeps its metadata rather than losing its rotation."""
    out = BytesIO()
    _photo().save(out, fmt, exif=_exif(), **kwargs)
    raw = out.getvalue()
    assert strip_metadata(raw, fmt, orientation=8) is raw
