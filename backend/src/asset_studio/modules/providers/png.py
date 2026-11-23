"""A minimal PNG writer, so the fake provider needs no imaging library."""

import struct
import zlib


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def encode_rgba(width: int, height: int, pixels: bytes) -> bytes:
    """Encode 8-bit RGBA ``pixels`` (row-major, width*height*4 bytes) as PNG."""
    if len(pixels) != width * height * 4:
        raise ValueError("pixel buffer does not match the size")
    stride = width * 4
    raw = b"".join(b"\x00" + pixels[y * stride : (y + 1) * stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def sample_image(width: int, height: int, seed: int) -> bytes:
    """A deterministic gradient whose colours depend on the seed; corners are transparent
    so the transparency checkerboard is visible in the UI."""
    r0, g0, b0 = (seed * 67) % 256, (seed * 131) % 256, (seed * 199) % 256
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            corner = (x < width // 8 or x >= width - width // 8) and (
                y < height // 8 or y >= height - height // 8
            )
            row += bytes(
                (
                    (r0 + x * 255 // max(width - 1, 1)) % 256,
                    (g0 + y * 255 // max(height - 1, 1)) % 256,
                    b0,
                    0 if corner else 255,
                )
            )
        rows.append(bytes(row))
    return encode_rgba(width, height, b"".join(rows))
