"""Generate-and-apply logic shared by the CLI, launchd tick and menu bar app."""
from __future__ import annotations

import contextlib
import fcntl
import random
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config, desktop, palettes
from .layout import generate_layout
from .render import render_png, render_svg

KEEP_IMAGES = 8  # generated wallpapers kept in ~/Pictures/geo-wallpaper


@contextlib.contextmanager
def lock(blocking: bool = True):
    """Serialise wallpaper changes between tick, the CLI and the menu bar app."""
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.LOCK_FILE, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def resolve_palette(selection: str, rng: random.Random) -> palettes.Palette:
    if selection == config.RANDOM_PRESET:
        return palettes.random_preset(rng)
    if selection == config.RANDOM:
        return palettes.random_palette(rng)
    try:
        return palettes.get_palette(selection)
    except palettes.PaletteError as e:
        print(f"geo-wallpaper: {e}; using {config.DEFAULT_PALETTE}", file=sys.stderr)
        return palettes.get_palette(config.DEFAULT_PALETTE)


def validate_selection(selection: str) -> None:
    """Raise PaletteError unless `selection` is a palette name or a random mode."""
    if selection not in config.RESERVED_NAMES:
        palettes.get_palette(selection)


def _prune_images() -> None:
    files = sorted(config.IMAGE_DIR.glob("wallpaper-*.png"), key=lambda p: p.stat().st_mtime)
    for old in files[:-KEEP_IMAGES]:
        old.unlink(missing_ok=True)


def change_wallpaper(
    selection: str,
    *,
    sizes: list[tuple[int, int]] | None = None,
    seed: int | None = None,
    count: int | None = None,
    gap: float | None = None,
    set_it: bool = True,
    output: Path | None = None,
) -> dict:
    """Generate a wallpaper per display and (optionally) apply it.

    With `output`, a single image is written there and nothing is applied."""
    base_seed = seed if seed is not None else secrets.randbits(32)
    palette = resolve_palette(selection, random.Random(base_seed))
    sizes = sizes or desktop.screen_sizes()
    extra = {} if gap is None else {"gap": gap}

    if output is not None:
        sizes, set_it = sizes[:1], False
    paths = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for i, (w, h) in enumerate(sizes):
        layout = generate_layout(palette, w, h, count=count, seed=base_seed + i, **extra)
        if output is not None:
            path = output
        else:
            config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            path = config.IMAGE_DIR / f"wallpaper-{stamp}-{base_seed:08x}-{i + 1}.png"
        if path.suffix.lower() == ".svg":
            path.write_text(render_svg(layout, palette, w, h))
        else:
            render_png(layout, palette, w, h).save(path)
        paths.append(path)

    if set_it:
        desktop.set_wallpapers(paths)
        config.save_state(
            {
                "last_change": time.time(),
                "palette": palette.name,
                "seed": base_seed,
                "images": [str(p) for p in paths],
            }
        )
        _prune_images()
    return {"palette": palette.name, "seed": base_seed, "paths": paths}


def tick() -> bool:
    """Called by launchd every few minutes: change the wallpaper if the interval is up."""
    cfg = config.load()

    def due() -> bool:
        last = config.load_state().get("last_change")
        return not isinstance(last, (int, float)) or (
            time.time() - last >= cfg.interval_seconds - config.TICK_SLACK
        )

    if not due():
        return False
    with lock(blocking=False) as got:
        if not got or not due():  # someone else is changing it, or just did
            return False
        change_wallpaper(cfg.palette)
    return True
