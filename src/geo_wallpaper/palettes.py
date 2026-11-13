"""Colour palettes: built-ins, user TOML files, and random generation."""
from __future__ import annotations

import colorsys
import random
import re
import sys
import tomllib
from dataclasses import dataclass

from . import config

Rgb = tuple[int, int, int]


class PaletteError(ValueError):
    pass


@dataclass(frozen=True)
class Group:
    weight: float
    faces: tuple[str, str, str]  # lit, middle, shaded (hex)


@dataclass(frozen=True)
class Palette:
    name: str
    bg_inner: str
    bg_outer: str
    groups: tuple[Group, ...]
    shadow: str


_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_hex(value: str) -> Rgb:
    m = _HEX.match(str(value).strip())
    if not m:
        raise PaletteError(f"invalid colour {value!r} (use #rrggbb)")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def to_hex(rgb: Rgb) -> str:
    return "#%02x%02x%02x" % rgb


def shade(color: str, factor: float) -> str:
    return to_hex(tuple(min(255, round(c * factor)) for c in parse_hex(color)))


def derive_faces(color: str) -> tuple[str, str, str]:
    """One base colour -> lit / middle / shaded faces (matches the original look)."""
    return to_hex(parse_hex(color)), shade(color, 0.9), shade(color, 0.81)


def parse_palette(name: str, data: dict) -> Palette:
    bg = data.get("background")
    if not isinstance(bg, dict):
        raise PaletteError("missing [background] table")
    if "inner" in bg and "outer" in bg:
        inner, outer = to_hex(parse_hex(bg["inner"])), to_hex(parse_hex(bg["outer"]))
    elif "color" in bg:
        outer = to_hex(parse_hex(bg["color"]))
        inner = shade(outer, 1.25)
    else:
        raise PaletteError("[background] needs `inner` and `outer` (or `color`)")

    groups = []
    for g in data.get("group", []):
        weight = float(g.get("weight", 1))
        if weight <= 0:
            raise PaletteError("group weight must be positive")
        if "faces" in g:
            faces = [to_hex(parse_hex(c)) for c in g["faces"]]
            if len(faces) != 3:
                raise PaletteError("`faces` needs exactly 3 colours (lit, middle, shaded)")
            groups.append(Group(weight, tuple(faces)))
        elif "color" in g:
            groups.append(Group(weight, derive_faces(g["color"])))
        else:
            raise PaletteError("each [[group]] needs `color` or `faces`")
    if not groups:
        raise PaletteError("needs at least one [[group]]")

    shadow = to_hex(parse_hex(data["shadow"])) if data.get("shadow") else shade(outer, 0.3)
    return Palette(name, inner, outer, tuple(groups), shadow)


_BUILTIN_DATA = {
    # The original wallpaper.
    "teal-yellow": {
        "background": {"inner": "#007a78", "outer": "#004d52"},
        "shadow": "#00161a",
        "group": [
            {"weight": 3, "faces": ["#ffd800", "#e6c000", "#cfa900"]},
            {"weight": 3, "faces": ["#72b890", "#62a07c", "#6cab88"]},
            {"weight": 2, "faces": ["#2f7a72", "#26695f", "#225a56"]},
            {"weight": 2, "faces": ["#004b4f", "#003e42", "#00272c"]},
        ],
    },
    "sunset": {
        "background": {"inner": "#4a1d6b", "outer": "#2a0f45"},
        "group": [
            {"weight": 3, "color": "#ff8a3d"},
            {"weight": 3, "color": "#ff5d73"},
            {"weight": 2, "color": "#8e5bd1"},
            {"weight": 2, "color": "#1d0a33"},
        ],
    },
    "ocean": {
        "background": {"inner": "#0b4f8a", "outer": "#06274d"},
        "group": [
            {"weight": 3, "color": "#5ad1ff"},
            {"weight": 3, "color": "#2f8fe0"},
            {"weight": 2, "color": "#ffd166"},
            {"weight": 2, "color": "#0a1f3d"},
        ],
    },
    "ember": {
        "background": {"inner": "#3a2a2a", "outer": "#1c1414"},
        "group": [
            {"weight": 3, "color": "#ff5a36"},
            {"weight": 3, "color": "#ff9f1c"},
            {"weight": 2, "color": "#8a3b2e"},
            {"weight": 2, "color": "#0f0a0a"},
        ],
    },
    "slate": {
        "background": {"inner": "#3b4350", "outer": "#20252d"},
        "group": [
            {"weight": 3, "color": "#e8ecf1"},
            {"weight": 3, "color": "#aab4c0"},
            {"weight": 1, "color": "#ff5a5f"},
            {"weight": 2, "color": "#5a6573"},
        ],
    },
    "pastel": {
        "background": {"inner": "#ffe3f1", "outer": "#e6b3d3"},
        "shadow": "#6b3a5b",
        "group": [
            {"weight": 3, "color": "#7be0c3"},
            {"weight": 3, "color": "#b69cff"},
            {"weight": 2, "color": "#ff8fb8"},
            {"weight": 2, "color": "#ffffff"},
        ],
    },
}

BUILTIN: dict[str, Palette] = {n: parse_palette(n, d) for n, d in _BUILTIN_DATA.items()}


_warned: set[tuple[str, str]] = set()


def user_palettes() -> dict[str, Palette]:
    """Palettes from ~/.config/geo-wallpaper/palettes/*.toml (bad files are skipped)."""
    out: dict[str, Palette] = {}
    if not config.PALETTE_DIR.is_dir():
        return out
    for path in sorted(config.PALETTE_DIR.glob("*.toml")):
        if path.name.startswith("_"):
            continue
        try:
            data = tomllib.loads(path.read_text())
            name = str(data.get("name") or path.stem)
            if name in config.RESERVED_NAMES:
                raise PaletteError(f"{name!r} is a reserved name")
            out[name] = parse_palette(name, data)
        except (OSError, tomllib.TOMLDecodeError, PaletteError, TypeError, ValueError) as e:
            if (path.name, str(e)) not in _warned:  # once per process, not once per lookup
                _warned.add((path.name, str(e)))
                print(f"geo-wallpaper: skipping palette {path.name}: {e}", file=sys.stderr)
    return out


def all_palettes() -> dict[str, Palette]:
    """Built-ins plus user palettes (a user palette overrides a built-in of the same name)."""
    return {**BUILTIN, **user_palettes()}


def get_palette(name: str) -> Palette:
    palettes = all_palettes()
    if name not in palettes:
        raise PaletteError(f"unknown palette {name!r} (available: {', '.join(palettes)})")
    return palettes[name]


def random_preset(rng: random.Random) -> Palette:
    palettes = all_palettes()
    return palettes[rng.choice(sorted(palettes))]


def _hsv(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(1.0, s), min(1.0, v))
    return to_hex((round(r * 255), round(g * 255), round(b * 255)))


def random_palette(rng: random.Random) -> Palette:
    """A fresh palette with the same structure as the original: a dark gradient
    background, one vivid accent, a pale tint, a mid tone and a deep tone."""
    h = rng.random()
    sat = rng.uniform(0.7, 1.0)
    v_out = rng.uniform(0.28, 0.4)
    outer = _hsv(h, sat, v_out)
    inner = _hsv(h, sat * 0.95, v_out + 0.12)
    accent_h = h + rng.choice([0.5, 0.33, 0.67, 0.42, 0.58]) + rng.uniform(-0.03, 0.03)
    groups = (
        Group(3, derive_faces(_hsv(accent_h, rng.uniform(0.85, 1.0), 1.0))),
        Group(3, derive_faces(_hsv(h + rng.uniform(-0.1, 0.1), rng.uniform(0.3, 0.5), rng.uniform(0.7, 0.85)))),
        Group(2, derive_faces(_hsv(h, rng.uniform(0.5, 0.7), v_out + 0.2))),
        Group(2, derive_faces(_hsv(h, sat, v_out * 0.6))),
    )
    return Palette("random", inner, outer, groups, shade(outer, 0.3))
