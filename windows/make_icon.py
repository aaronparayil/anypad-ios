"""Draws AnyPad.ico (a simple gamepad) with nothing but the standard library."""
import os
import struct
import zlib

BG, PAD, MARK = (37, 99, 235), (255, 255, 255), (37, 99, 235)


def inside(x, y):
    """Color at (x, y) in a 0..1 square, or None outside the rounded tile."""
    r = 0.20
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return None
    body = 0.30 <= x <= 0.70 and 0.34 <= y <= 0.62
    grips = any((x - gx) ** 2 + ((y - 0.53) * 0.85) ** 2 <= 0.19 ** 2 for gx in (0.30, 0.70))
    if not (body or grips):
        return BG
    if (abs(x - 0.31) < 0.095 and abs(y - 0.48) < 0.032) or (abs(x - 0.31) < 0.032 and abs(y - 0.48) < 0.095):
        return MARK
    if any((x - bx) ** 2 + (y - by) ** 2 <= 0.038 ** 2 for bx, by in ((0.69, 0.41), (0.69, 0.55), (0.62, 0.48), (0.76, 0.48))):
        return MARK
    return PAD


def png(size):
    n, rows = 4, bytearray()
    for py in range(size):
        rows.append(0)
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(n):
                for sx in range(n):
                    c = inside((px + (sx + .5) / n) / size, (py + (sy + .5) / n) / size)
                    if c:
                        acc = [acc[0] + c[0], acc[1] + c[1], acc[2] + c[2], acc[3] + 1]
            k = acc[3]
            rows += bytes((acc[0] // k, acc[1] // k, acc[2] // k, 255 * k // (n * n)) if k else (0, 0, 0, 0))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


sizes = (16, 24, 32, 48, 64, 256)
images = [png(s) for s in sizes]
out, offset = struct.pack("<HHH", 0, 1, len(sizes)), 6 + 16 * len(sizes)
for s, im in zip(sizes, images):
    out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(im), offset)
    offset += len(im)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "AnyPad.ico"), "wb") as f:
    f.write(out + b"".join(images))
print("AnyPad.ico written")
