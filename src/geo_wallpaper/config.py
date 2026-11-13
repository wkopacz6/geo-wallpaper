"""Paths, user settings, persisted state and interval parsing."""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "geo-wallpaper"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = CONFIG_DIR / "state.json"
LOCK_FILE = CONFIG_DIR / ".lock"
MENUBAR_LOCK_FILE = CONFIG_DIR / ".menubar.lock"
PALETTE_DIR = CONFIG_DIR / "palettes"
IMAGE_DIR = Path.home() / "Pictures" / "geo-wallpaper"
LOG_FILE = Path.home() / "Library" / "Logs" / "geo-wallpaper.log"

DEFAULT_PALETTE = "teal-yellow"
RANDOM_PRESET = "random-preset"  # random pick among the named palettes
RANDOM = "random"  # a freshly generated palette
RESERVED_NAMES = (RANDOM_PRESET, RANDOM)

MIN_INTERVAL = 30 * 60
MAX_INTERVAL = 14 * 24 * 3600
DEFAULT_INTERVAL = 2 * 3600

# launchd wakes `tick` this often; tick only changes the wallpaper once the
# configured interval has elapsed (so long intervals survive reboots/sleep).
TICK_SECONDS = 300
TICK_SLACK = 150

EXAMPLE_PALETTE = '''\
# Example palette. Copy this file to e.g. my-palette.toml (files starting with
# "_" are ignored), edit the colours, and it shows up in `geo-wallpaper palettes`
# and in the menu bar. The palette name is the file name unless you set
#   name = "my palette"

[background]            # radial gradient: lighter centre -> darker edge
inner = "#007a78"
outer = "#004d52"
# or a single colour:  color = "#004d52"

# Optional drop-shadow colour (default: a very dark version of background.outer)
# shadow = "#00161a"

# Each [[group]] is a family of triangles; `weight` is how common it is.
# Give one `color` and the three face shades are derived automatically...
[[group]]
weight = 3
color = "#ffd800"

# ...or spell out the three faces yourself: lit, middle, shaded.
[[group]]
weight = 3
faces = ["#72b890", "#62a07c", "#6cab88"]

[[group]]
weight = 2
color = "#2f7a72"

[[group]]
weight = 2
color = "#004b4f"
'''

_UNITS = {
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}
_INTERVAL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]*)\s*$", re.I)


def parse_interval(text: str) -> int:
    """'30m', '2h', '1.5d', '2w' (bare numbers are minutes) -> seconds."""
    m = _INTERVAL_RE.match(text)
    unit = m.group(2).lower() or "m" if m else None
    if not m or unit not in _UNITS:
        raise ValueError(f"can't read {text!r} as an interval (try 30m, 2h, 3d, 1w)")
    seconds = round(float(m.group(1)) * _UNITS[unit])
    if not MIN_INTERVAL <= seconds <= MAX_INTERVAL:
        raise ValueError(
            f"interval must be between {format_interval(MIN_INTERVAL)} and "
            f"{format_interval(MAX_INTERVAL)} (got {format_interval(seconds)})"
        )
    return seconds


def format_interval(seconds: float) -> str:
    """7200 -> '2h', 90000 -> '1d 1h', 1209600 -> '2w'."""
    minutes = round(seconds / 60)
    parts = []
    for unit, size in (("w", 10080), ("d", 1440), ("h", 60), ("m", 1)):
        n, minutes = divmod(minutes, size)
        if n:
            parts.append(f"{n}{unit}")
    return " ".join(parts) or "0m"


@dataclass
class Config:
    interval_seconds: int = DEFAULT_INTERVAL
    palette: str = DEFAULT_PALETTE  # palette name, RANDOM_PRESET or RANDOM


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def load() -> Config:
    data = _read_json(CONFIG_FILE)
    cfg = Config()
    secs = data.get("interval_seconds")
    if isinstance(secs, (int, float)) and MIN_INTERVAL <= secs <= MAX_INTERVAL:
        cfg.interval_seconds = int(secs)
    if isinstance(data.get("palette"), str) and data["palette"]:
        cfg.palette = data["palette"]
    return cfg


def save(cfg: Config) -> None:
    _write_json(CONFIG_FILE, asdict(cfg))


def load_state() -> dict:
    return _read_json(STATE_FILE)


def save_state(state: dict) -> None:
    _write_json(STATE_FILE, state)


def next_change_time(cfg: Config, state: dict) -> float | None:
    last = state.get("last_change")
    return last + cfg.interval_seconds if isinstance(last, (int, float)) else None


def ensure_dirs() -> None:
    """Create the config/palette dirs and drop in the example palette once."""
    PALETTE_DIR.mkdir(parents=True, exist_ok=True)
    example = PALETTE_DIR / "_example.toml"
    if not example.exists():
        example.write_text(EXAMPLE_PALETTE)
