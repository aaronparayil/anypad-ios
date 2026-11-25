"""Draws the AnyPad logo, half gamepad and half wireless waves, with only the standard library.

Writes windows/AnyPad.ico, linux/anypad.png and assets/logo.png.
"""
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOP, BOTTOM, WHITE, WAVE = (79, 70, 229), (14, 165, 233), (255, 255, 255), (224, 247, 255)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def inside(x, y):
    """Color at (x, y) in a 0..1 square, or None outside the rounded tile."""
    r = 0.23
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return None
    back = mix(TOP, BOTTOM, (x + y) / 2)
    if x <= 0.485:      # left: half a gamepad
        body = x >= 0.30 and 0.335 <= y <= 0.63
        shoulder = (x - 0.30) ** 2 / 0.155 ** 2 + (y - 0.485) ** 2 / 0.150 ** 2 <= 1
        # the grip leans outwards
        t = min(max(((x - 0.285) * -0.075 + (y - 0.50) * 0.20) / (0.075 ** 2 + 0.20 ** 2), 0), 1)
        grip = math.hypot(x - (0.285 - 0.075 * t), y - (0.50 + 0.20 * t)) <= 0.092
        if not (body or shoulder or grip):
            return back
        dx, dy = abs(x - 0.315), abs(y - 0.475)
        if (dx < 0.088 and dy < 0.030) or (dx < 0.030 and dy < 0.088):
            return mix(TOP, BOTTOM, 0.35)
        return WHITE
    if x >= 0.535:      # right: wireless waves
        d, a = math.hypot(x - 0.50, y - 0.485), math.degrees(math.atan2(y - 0.485, x - 0.50))
        for radius in (0.130, 0.235, 0.340):
            if abs(d - radius) <= 0.032 and abs(a) <= 52:
                return WAVE
            for end in (-52, 52):     # rounded ends
                ex, ey = 0.50 + radius * math.cos(math.radians(end)), 0.485 + radius * math.sin(math.radians(end))
                if math.hypot(x - ex, y - ey) <= 0.032:
                    return WAVE
    return back


def png(size, n=4):
    rows = bytearray()
    for py in range(size):
        rows.append(0)
        for px in range(size):
            acc, hits = [0.0, 0.0, 0.0], 0
            for sy in range(n):
                for sx in range(n):
                    c = inside((px + (sx + .5) / n) / size, (py + (sy + .5) / n) / size)
                    if c:
                        acc, hits = [acc[i] + c[i] for i in range(3)], hits + 1
            rows += bytes([int(v / hits) for v in acc] + [255 * hits // (n * n)]) if hits else bytes(4)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def write(name, data):
    with open(os.path.join(ROOT, name), "wb") as f:
        f.write(data)
    print(name, len(data), "bytes")


sizes = (16, 20, 24, 32, 48, 64, 256)
images = [png(s) for s in sizes]
out, offset = struct.pack("<HHH", 0, 1, len(sizes)), 6 + 16 * len(sizes)
for s, im in zip(sizes, images):
    out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(im), offset)
    offset += len(im)
write("windows/AnyPad.ico", out + b"".join(images))
write("linux/anypad.png", images[-1])
write("assets/logo.png", images[-1])
