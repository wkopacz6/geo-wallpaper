"""Command-line interface."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config, core, palettes, schedule


def _swatch(hex_color: str) -> str:
    r, g, b = palettes.parse_hex(hex_color)
    return f"\x1b[48;2;{r};{g};{b}m  \x1b[0m"


def _parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not WIDTHxHEIGHT (e.g. 2560x1600)")


def cmd_new(args) -> int:
    cfg = config.load()
    selection = args.palette or cfg.palette
    try:
        core.validate_selection(selection)
    except palettes.PaletteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    output = args.output
    if args.format == "svg" and output is None:
        output = Path("wallpaper.svg")
    if args.format == "png" and output is not None and output.suffix.lower() == ".svg":
        args.format = "svg"
    set_it = not args.no_set and output is None
    sizes = [args.size] if args.size else None
    with core.lock():
        result = core.change_wallpaper(
            selection, sizes=sizes, seed=args.seed, count=args.count, gap=args.gap,
            set_it=set_it, output=output,
        )
    verb = "Set wallpaper" if set_it else "Wrote image"
    files = ", ".join(str(p) for p in result["paths"])
    print(f"{verb}: palette {result['palette']}, seed {result['seed']} -> {files}")
    return 0


def cmd_tick(_args) -> int:
    core.tick()
    return 0


def cmd_install(args) -> int:
    config.ensure_dirs()
    path = schedule.install(schedule.TICK_LABEL)
    print(f"Installed {path}")
    print(f"  wallpaper changes every {config.format_interval(config.load().interval_seconds)}")
    if args.menubar:
        path = schedule.install(schedule.MENUBAR_LABEL)
        print(f"Installed {path} (menu bar app starts at login)")
    return 0


def cmd_uninstall(_args) -> int:
    for label in (schedule.TICK_LABEL, schedule.MENUBAR_LABEL):
        if schedule.is_installed(label):
            schedule.uninstall(label)
            print(f"Removed {schedule.plist_path(label)}")
    return 0


def cmd_menubar(_args) -> int:
    import fcntl

    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    guard = open(config.MENUBAR_LOCK_FILE, "w")  # held for the life of the process
    try:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("geo-wallpaper menu bar app is already running", file=sys.stderr)
        return 0
    config.ensure_dirs()
    from . import menubar

    menubar.run()
    return 0


def cmd_interval(args) -> int:
    cfg = config.load()
    if args.value is None:
        print(config.format_interval(cfg.interval_seconds))
        return 0
    try:
        cfg.interval_seconds = config.parse_interval(args.value)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    config.save(cfg)
    print(f"Wallpaper will change every {config.format_interval(cfg.interval_seconds)}")
    return 0


def cmd_palette(args) -> int:
    cfg = config.load()
    if args.value is None:
        print(cfg.palette)
        return 0
    try:
        core.validate_selection(args.value)
    except palettes.PaletteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    cfg.palette = args.value
    config.save(cfg)
    print(f"Palette: {cfg.palette} (applies from the next change; run `geo-wallpaper new` for one now)")
    return 0


def cmd_palettes(_args) -> int:
    config.ensure_dirs()
    current = config.load().palette
    tty = sys.stdout.isatty()
    user = palettes.user_palettes()
    for name, pal in palettes.all_palettes().items():
        swatches = ""
        if tty:
            colors = [pal.bg_inner, pal.bg_outer] + [g.faces[0] for g in pal.groups]
            swatches = " " + "".join(_swatch(c) for c in colors)
        tags = []
        if name in user:
            tags.append("yours")
        if name == current:
            tags.append("selected")
        tag = f"  ({', '.join(tags)})" if tags else ""
        print(f"{name:<14}{swatches}{tag}")
    print(f"{config.RANDOM_PRESET:<14}  random pick among the palettes above" + ("  (selected)" if current == config.RANDOM_PRESET else ""))
    print(f"{config.RANDOM:<14}  a freshly generated palette every time" + ("  (selected)" if current == config.RANDOM else ""))
    print(f"\nAdd your own: drop a .toml file in {config.PALETTE_DIR} (see _example.toml there)")
    return 0


def cmd_status(_args) -> int:
    cfg = config.load()
    state = config.load_state()
    print(f"Palette:   {cfg.palette}")
    print(f"Interval:  {config.format_interval(cfg.interval_seconds)}")
    nxt = config.next_change_time(cfg, state)
    if state.get("last_change"):
        print(f"Last:      {datetime.fromtimestamp(state['last_change']):%a %H:%M} ({state.get('palette')}, seed {state.get('seed')})")
    if nxt:
        print(f"Next:      {datetime.fromtimestamp(max(nxt, time.time())):%a %H:%M}")
    for label, name in ((schedule.TICK_LABEL, "Scheduler"), (schedule.MENUBAR_LABEL, "Menu bar at login")):
        print(f"{name + ':':<19}{'installed' if schedule.is_installed(label) else 'not installed'}")
    print(f"Palettes:  {config.PALETTE_DIR}")
    print(f"Images:    {config.IMAGE_DIR}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geo-wallpaper", description="3D-triangle wallpapers on a schedule.")
    sub = p.add_subparsers(dest="command", required=True)

    n = sub.add_parser("new", help="generate a wallpaper and set it now")
    n.add_argument("--palette", help="palette name, 'random-preset' or 'random' (default: from config)")
    n.add_argument("--seed", type=int, help="reproduce a specific layout")
    n.add_argument("--count", type=int, help="number of triangles (default: scaled to screen)")
    n.add_argument("--gap", type=float, help="minimum space between triangles")
    n.add_argument("--size", type=_parse_size, help="WIDTHxHEIGHT in pixels (default: your screen)")
    n.add_argument("--no-set", action="store_true", help="only generate the image")
    n.add_argument("-o", "--output", type=Path, help="write to this file (.png or .svg) instead of setting it")
    n.add_argument("--format", choices=["png", "svg"], default="png")
    n.set_defaults(func=cmd_new)

    sub.add_parser("tick", help="change the wallpaper if the interval is up (run by launchd)").set_defaults(func=cmd_tick)

    i = sub.add_parser("install", help="install the launchd scheduler")
    i.add_argument("--menubar", action="store_true", help="also start the menu bar app at login")
    i.set_defaults(func=cmd_install)
    sub.add_parser("uninstall", help="remove the launchd agents").set_defaults(func=cmd_uninstall)
    sub.add_parser("menubar", help="run the menu bar app").set_defaults(func=cmd_menubar)

    iv = sub.add_parser("interval", help="show or set how often the wallpaper changes (30m to 2w)")
    iv.add_argument("value", nargs="?", help="e.g. 30m, 2h, 3d, 1w")
    iv.set_defaults(func=cmd_interval)

    pa = sub.add_parser("palette", help="show or choose the palette (name, random-preset, random)")
    pa.add_argument("value", nargs="?")
    pa.set_defaults(func=cmd_palette)

    sub.add_parser("palettes", help="list available palettes").set_defaults(func=cmd_palettes)
    sub.add_parser("status", help="show settings and schedule").set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        code = args.func(args)
    except (RuntimeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        code = 1
    sys.exit(code)
