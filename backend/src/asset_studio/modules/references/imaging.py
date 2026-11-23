"""Image sniffing without a decoder: the real type from the magic bytes, and the pixel size.

The declared Content-Type is never trusted (FR-025): the file must parse as the format its
magic bytes say, and that format must be one we accept.
"""

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageInfo:
    mime: str
    ext: str
    width: int
    height: int


class ImageError(ValueError):
    pass


def _png(data: bytes) -> ImageInfo:
    # Signature, then the IHDR chunk: length, b"IHDR", width, height.
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ImageError("truncated PNG header")
    width, height = struct.unpack(">II", data[16:24])
    return ImageInfo("image/png", "png", width, height)


# Start-of-frame markers carry the size (baseline, progressive, lossless, ...).
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg(data: bytes) -> ImageInfo:
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ImageError("corrupt JPEG marker")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        if marker in _SOF:
            if i + 9 > len(data):
                break
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return ImageInfo("image/jpeg", "jpg", width, height)
        if marker == 0xDA:  # start of scan before any frame header
            break
        i += 2 + length
    raise ImageError("no JPEG frame header")


def _webp(data: bytes) -> ImageInfo:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
    elif chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width, height = (v & 0x3FFF for v in struct.unpack("<HH", data[26:30]))
    elif chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    else:
        raise ImageError("unknown WebP chunk")
    return ImageInfo("image/webp", "webp", width, height)


def sniff(data: bytes) -> ImageInfo:
    """Identify a PNG, JPEG or WebP image from its first bytes; raise ImageError otherwise."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        info = _png(data)
    elif data.startswith(b"\xff\xd8\xff"):
        info = _jpeg(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        info = _webp(data)
    else:
        raise ImageError("not a PNG, JPEG or WebP image")
    if info.width <= 0 or info.height <= 0:
        raise ImageError("image has no pixels")
    return info
