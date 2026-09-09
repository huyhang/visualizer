"""Remove metadata from an image without touching a pixel.

Akasha archives the bytes you uploaded and serves them as the full-size view,
so anything embedded in them reaches every reader of the article -- including
the GPS coordinates a phone writes into every photo. Re-encoding would strip
that too, but at the cost of the quality the archived copy exists to preserve.

So this edits the *container* instead: it walks the segment or chunk list and
drops the ones that hold description rather than picture. Colour-critical
records (JFIF density, ICC profiles, PNG gamma) are deliberately kept -- losing
them changes how the image looks, which is not what "strip metadata" should
mean. Nothing here decodes, resamples or re-compresses, so the pixels that come
out are bit-for-bit the pixels that went in.

Pure: bytes in, bytes out. When there is nothing to remove the input is
returned unchanged, so an already-clean upload is stored exactly as sent.
"""

# JPEG application segments that carry description, not picture. Kept on
# purpose: APP0 (JFIF density), APP2 (ICC profile) and APP14 (Adobe colour
# transform) all change how the image renders.
_JPEG_DROP = frozenset({
    0xE1,  # APP1  -- Exif, including GPS, and XMP
    0xEC,  # APP12 -- Ducky / "picture info"
    0xED,  # APP13 -- Photoshop IRB, which carries IPTC
    0xFE,  # COM   -- free-text comment
})

# Markers that stand alone: no length field follows them.
_JPEG_STANDALONE = {0xD8, 0xD9, 0x01, *range(0xD0, 0xD8)}

_PNG_DROP = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}

# Exif tag 274. Not a privacy record -- it is the difference between a portrait
# photo displaying upright and displaying on its side -- so a JPEG that carries
# a real one gets a minimal Exif block back after everything else is removed.
_ORIENTATION_TAG = 274

_WEBP_DROP = {b"EXIF", b"XMP "}
_WEBP_VP8X_METADATA_FLAGS = 0x08 | 0x04  # Exif present | XMP present


def strip_metadata(data: bytes, format_name: str, orientation: int = 1) -> bytes:
    """Return ``data`` without its descriptive metadata.

    ``orientation`` is the Exif rotation the source declared. When it is
    anything but the default, a JPEG gets a minimal Exif block back holding
    that one tag -- otherwise the archived copy, which is what the full-size
    view serves, would display on its side while every derived copy was
    upright. PNG and WebP are left alone in that case rather than rebuilt:
    their Exif lives in a chunk this module would have to re-encode the file to
    replace, and a rotated one is rare enough not to be worth that.

    Unknown or malformed input is returned untouched: this runs after the
    decoder has already accepted the upload, so refusing here would reject a
    file the rest of the system considers valid.
    """
    rotated = orientation not in (0, 1)
    if rotated and format_name != "JPEG":
        return data
    try:
        cleaned = _STRIPPERS[format_name](data)
        if rotated:
            cleaned = _with_orientation(cleaned, orientation)
    except (KeyError, IndexError, ValueError):
        return data
    return cleaned if cleaned and len(cleaned) < len(data) else data


def _with_orientation(data: bytes, orientation: int) -> bytes:
    """Put a minimal Exif segment holding only Orientation back into a JPEG."""
    from PIL import Image  # local: keeps this module importable without Pillow

    exif = Image.Exif()
    exif[_ORIENTATION_TAG] = orientation
    payload = exif.tobytes()
    segment = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    return data[:2] + segment + data[2:]


def _strip_jpeg(data: bytes) -> bytes:
    if data[:2] != b"\xff\xd8":
        return data
    out = bytearray(data[:2])
    offset = 2
    while offset + 1 < len(data):
        if data[offset] != 0xFF:
            break  # not a marker boundary; copy the rest verbatim below
        marker = data[offset + 1]
        if marker == 0xFF:  # fill byte, legal padding before a marker
            offset += 1
            out.append(0xFF)
            continue
        if marker in _JPEG_STANDALONE:
            out += data[offset:offset + 2]
            offset += 2
            continue
        if marker == 0xDA:  # start of scan: entropy data to the end, as-is
            return bytes(out + data[offset:])
        length = int.from_bytes(data[offset + 2:offset + 4], "big")
        if length < 2:
            break
        end = offset + 2 + length
        if marker not in _JPEG_DROP:
            out += data[offset:end]
        offset = end
    return bytes(out + data[offset:])


def _strip_png(data: bytes) -> bytes:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return data
    out = bytearray(data[:8])
    offset = 8
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length  # length + type + payload + crc
        if end > len(data):
            break
        if kind not in _PNG_DROP:
            out += data[offset:end]
        offset = end
        if kind == b"IEND":
            break
    return bytes(out + data[offset:])


def _strip_webp(data: bytes) -> bytes:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return data
    body = bytearray()
    offset = 12
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        end = offset + 8 + size + (size & 1)  # chunks pad to an even length
        if end > len(data):
            break
        if kind not in _WEBP_DROP:
            chunk = bytearray(data[offset:end])
            if kind == b"VP8X" and size >= 1:
                # The header advertises which optional chunks follow. Having
                # just dropped two of them, say so, or a reader will hunt for
                # metadata that is no longer there.
                chunk[8] &= ~_WEBP_VP8X_METADATA_FLAGS & 0xFF
            body += chunk
        offset = end
    return bytes(
        b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + bytes(body)
    )


_STRIPPERS = {"JPEG": _strip_jpeg, "PNG": _strip_png, "WEBP": _strip_webp}
