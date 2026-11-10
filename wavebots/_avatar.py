"""Draw a Wave bot's on-chain mascot (wave.avatar/1, kind pixel20) as a PNG for Hermes's Bots list.

Pure standard library (zlib + struct). The pixels come from the bot's verified design card, so the
avatar in Hermes is the same mascot the bots.theta store shows.
"""
from __future__ import annotations

import base64
import re
import struct
import zlib

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _rgb(h: str, fallback=(20, 184, 166)) -> tuple[int, int, int]:
    m = _HEX.match(str(h or ""))
    if not m:
        return fallback
    v = m.group(1)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _mix(a, b, t: float):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _png(w: int, h: int, rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)  # filter type 0 per row
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def mascot_png(design: dict, size: int = 256) -> bytes:
    """A square avatar: the mascot centred on a soft tint of its profile colour over Wave's dark
    store background. Raises ValueError for designs that aren't pixel20."""
    if not isinstance(design, dict) or design.get("kind") != "pixel20":
        raise ValueError("Only pixel20 mascots can be drawn")
    px = base64.b64decode(str(design.get("pixels") or ""), validate=False)
    if len(px) != 400:
        raise ValueError("A pixel20 mascot has 400 pixels")
    pal = [_rgb(c) for c in (design.get("palette") or [])][:8]
    if not pal:
        raise ValueError("The mascot has no palette")
    base = (11, 15, 26)  # #0B0F1A, the bots.theta store background
    tint = _mix(base, _rgb(design.get("profileColor") or design.get("eyelid") or "#14b8a6"), 0.22)
    cell = max(1, (size * 11 // 13) // 20)  # leave a margin around the 20x20 grid
    off = (size - cell * 20) // 2
    rows = []
    for y in range(size):
        row = bytearray()
        gy = (y - off) // cell if off <= y < off + cell * 20 else -1
        for x in range(size):
            gx = (x - off) // cell if off <= x < off + cell * 20 else -1
            color = tint
            if gx >= 0 and gy >= 0:
                v = px[gy * 20 + gx]
                if 0 < v <= len(pal):
                    color = pal[v - 1]
            row += bytes(color) + b"\xff"
        rows.append(bytes(row))
    return _png(size, size, rows)
