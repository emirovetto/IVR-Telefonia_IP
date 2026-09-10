from __future__ import annotations

import re

PALETTE = [
    "#2f6b54",
    "#3d6ea8",
    "#c45c26",
    "#7a4ea3",
    "#c49a2c",
    "#1a7a7a",
    "#8b3a4a",
    "#4a7c2e",
    "#2c5f8a",
    "#a65d2f",
    "#5c4a8a",
    "#b03d6e",
]

DEFAULT_COLOR = PALETTE[0]


def normalize_color(value: str | None) -> str:
    raw = (value or "").strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", raw):
        return raw.lower()
    if re.fullmatch(r"[0-9A-Fa-f]{6}", raw):
        return f"#{raw.lower()}"
    return DEFAULT_COLOR


def text_on(bg: str) -> str:
    color = normalize_color(bg).lstrip("#")
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "#f7f3ea" if luminance < 0.55 else "#14241e"
