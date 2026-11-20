"""Synthetic satellite-like PNGs for APP_MODE=demo: deterministic, in memory, Pillow only."""

import hashlib
import io
import json
import random
from datetime import date
from typing import Any

from PIL import Image, ImageDraw

from app.monitoring.domain.geo import BBox

MAX_SIDE = 384
MIN_SIDE = 128


def _size(geometry: dict[str, Any]) -> tuple[int, int]:
    bbox = BBox.from_geometry(geometry)
    aspect = (bbox.width or 1e-9) / (bbox.height or 1e-9)
    if aspect >= 1:
        return MAX_SIDE, max(MIN_SIDE, round(MAX_SIDE / aspect))
    return max(MIN_SIDE, round(MAX_SIDE * aspect)), MAX_SIDE


def render_demo_image(geometry: dict[str, Any], day: date) -> bytes:
    """Same (geometry, day) -> same bytes; a different day -> a visibly different image.

    A forest-green patchwork with, for later dates, a brown cleared/burnt scar; the caption
    says it is synthetic so nobody mistakes it for imagery.
    """
    digest = hashlib.sha256(
        f"{json.dumps(geometry, sort_keys=True)}|{day.isoformat()}".encode()
    ).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    width, height = _size(geometry)
    image = Image.new("RGB", (width, height), (30, 78, 42))
    draw = ImageDraw.Draw(image)

    for _ in range(260):  # canopy texture
        x, y = rng.randrange(width), rng.randrange(height)
        r = rng.randrange(6, 26)
        green = rng.randrange(60, 130)
        draw.ellipse(
            (x - r, y - r, x + r, y + r), fill=(rng.randrange(15, 50), green, rng.randrange(25, 60))
        )

    # a scar whose position and size depend on the date, so before and after never match
    cx, cy = rng.randrange(width // 4, 3 * width // 4), rng.randrange(height // 4, 3 * height // 4)
    for _ in range(14):
        r = rng.randrange(14, max(16, min(width, height) // 4))
        ox, oy = rng.randrange(-30, 30), rng.randrange(-30, 30)
        draw.ellipse(
            (cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r),
            fill=(rng.randrange(110, 160), rng.randrange(80, 110), rng.randrange(50, 80)),
        )

    draw.rectangle((0, height - 18, width, height), fill=(15, 15, 15))
    draw.text((6, height - 15), f"DEMO sintetica {day.isoformat()}", fill=(235, 235, 235))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
