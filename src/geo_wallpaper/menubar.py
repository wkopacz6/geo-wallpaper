"""Menu bar app (rumps): palette, interval, new-wallpaper-now, scheduler toggles."""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from . import config, palettes, schedule

INTERVAL_PRESETS = [
    (30, "30 minutes"), (60, "1 hour"), (120, "2 hours"), (360, "6 hours"), (720, "12 hours"),
    (1440, "1 day"), (4320, "3 days"), (10080, "1 week"), (20160, "2 weeks"),
]
RANDOM_PRESET_TITLE = "Random (from my palettes)"
RANDOM_TITLE = "Totally random"


class GeoWallpaperApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Geo Wallpaper", title="▲")
        self._proc: subprocess.Popen | None = None
        self._failed = False
        self._palette_values: dict[str, str] = {}
        self._palette_items: dict[str, rumps.MenuItem] = {}
        self._interval_items: dict[int, rumps.MenuItem] = {}
        self._seconds_by_title: dict[str, int] = {}
        self._palette_dir_mtime = self._dir_mtime()

        self.status_item = rumps.MenuItem("…")
        self.current_item = rumps.MenuItem("…")
        self.palette_menu = rumps.MenuItem("Palette")
        self.interval_menu = rumps.MenuItem("Change every")
        self.custom_item = rumps.MenuItem("Custom…", callback=self.on_custom_interval)
        self.auto_item = rumps.MenuItem("Change automatically", callback=self.on_toggle_auto)
        self.login_item = rumps.MenuItem("Open at login", callback=self.on_toggle_login)

        for minutes, label in INTERVAL_PRESETS:
            item = rumps.MenuItem(label, callback=self.on_interval)
            self._interval_items[minutes * 60] = item
            self._seconds_by_title[label] = minutes * 60
            self.interval_menu.add(item)
        self.interval_menu.add(self.custom_item)

        self._build_palette_menu()
        self.menu = [
            self.status_item,
            self.current_item,
            None,
            rumps.MenuItem("New wallpaper now", callback=self.on_new),
            self.palette_menu,
            self.interval_menu,
            None,
            self.auto_item,
            self.login_item,
            None,
            rumps.MenuItem("Open palettes folder", callback=lambda _: subprocess.run(["open", str(config.PALETTE_DIR)])),
            rumps.MenuItem("Open wallpapers folder", callback=self.on_open_images),
        ]
        self.refresh()
        self._timer = rumps.Timer(self.on_timer, 2)
        self._timer.start()

    # -- menu construction -------------------------------------------------

    @staticmethod
    def _dir_mtime() -> float | None:
        try:
            return config.PALETTE_DIR.stat().st_mtime
        except OSError:
            return None

    def _build_palette_menu(self) -> None:
        if len(self.palette_menu):  # rumps submenus have no native menu until first item
            self.palette_menu.clear()
        self._palette_values = {}
        self._palette_items = {}

        def add(title: str, value: str) -> None:
            item = rumps.MenuItem(title, callback=self.on_palette)
            self._palette_values[title] = value
            self._palette_items[value] = item
            self.palette_menu.add(item)

        add(RANDOM_PRESET_TITLE, config.RANDOM_PRESET)
        add(RANDOM_TITLE, config.RANDOM)
        self.palette_menu.add(rumps.separator)
        user = palettes.user_palettes()
        for name in palettes.all_palettes():
            add(name + ("  (yours)" if name in user else ""), name)

    # -- state -> UI ---------------------------------------------------------

    def refresh(self) -> None:
        cfg = config.load()
        state = config.load_state()

        if self._proc is not None:
            status = "Generating…"
        elif self._failed:
            status = "Last change failed (see ~/Library/Logs/geo-wallpaper.log)"
        elif not schedule.is_installed(schedule.TICK_LABEL):
            status = "Automatic changes are off"
        else:
            nxt = config.next_change_time(cfg, state)
            if nxt is None:
                status = "Next change: soon"
            else:
                when = datetime.fromtimestamp(max(nxt, time.time()))
                fmt = "%H:%M" if when.date() == datetime.now().date() else "%a %H:%M"
                status = f"Next change: {when:{fmt}}"
        self.status_item.title = status
        current = state.get("palette")
        self.current_item.title = f"Current palette: {current}" if current else "No wallpaper generated yet"

        for value, item in self._palette_items.items():
            item.state = 1 if value == cfg.palette else 0
        known = cfg.interval_seconds in self._interval_items
        for seconds, item in self._interval_items.items():
            item.state = 1 if seconds == cfg.interval_seconds else 0
        self.custom_item.state = 0 if known else 1
        self.custom_item.title = "Custom…" if known else f"Custom… ({config.format_interval(cfg.interval_seconds)})"
        self.auto_item.state = 1 if schedule.is_installed(schedule.TICK_LABEL) else 0
        self.login_item.state = 1 if schedule.is_installed(schedule.MENUBAR_LABEL) else 0

    # -- actions -------------------------------------------------------------

    def _run_new(self) -> None:
        if self._proc is not None:
            return
        config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.LOG_FILE, "ab") as log:
            # A subprocess keeps the AppKit work off this UI process and is the same
            # code path launchd uses.
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "geo_wallpaper", "new"],
                stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            )
        self._failed = False
        self.refresh()

    def on_new(self, _sender) -> None:
        self._run_new()

    def on_palette(self, sender) -> None:
        cfg = config.load()
        cfg.palette = self._palette_values[sender.title]
        config.save(cfg)
        self._run_new()  # apply straight away so the choice has visible effect
        self.refresh()

    def on_interval(self, sender) -> None:
        cfg = config.load()
        cfg.interval_seconds = self._seconds_by_title[sender.title]
        config.save(cfg)
        self.refresh()

    def on_custom_interval(self, _sender) -> None:
        cfg = config.load()
        window = rumps.Window(
            message="How often should the wallpaper change?\nBetween 30m and 2w, e.g. 45m, 3h, 2d, 1w.",
            title="Change every",
            default_text=config.format_interval(cfg.interval_seconds),
            ok="Set",
            cancel="Cancel",
            dimensions=(220, 24),
        )
        response = window.run()
        if not response.clicked:
            return
        try:
            cfg.interval_seconds = config.parse_interval(response.text)
        except ValueError as e:
            rumps.alert(title="Invalid interval", message=str(e))
            return
        config.save(cfg)
        self.refresh()

    def on_toggle_auto(self, _sender) -> None:
        try:
            if schedule.is_installed(schedule.TICK_LABEL):
                schedule.uninstall(schedule.TICK_LABEL)
            else:
                config.ensure_dirs()
                schedule.install(schedule.TICK_LABEL)
        except RuntimeError as e:
            rumps.alert(title="Scheduler", message=str(e))
        self.refresh()

    def on_toggle_login(self, _sender) -> None:
        # Don't load/unload: loading would start a second copy of this app now, and
        # unloading would quit this one. The change takes effect at next login.
        if schedule.is_installed(schedule.MENUBAR_LABEL):
            schedule.uninstall(schedule.MENUBAR_LABEL, unload=False)
        else:
            schedule.install(schedule.MENUBAR_LABEL, load=False)
        self.refresh()

    def on_open_images(self, _sender) -> None:
        config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(config.IMAGE_DIR)])

    def on_timer(self, _sender) -> None:
        if self._proc is not None and self._proc.poll() is not None:
            self._failed = self._proc.returncode != 0
            self._proc = None
        mtime = self._dir_mtime()
        if mtime != self._palette_dir_mtime:  # palette files added or removed
            self._palette_dir_mtime = mtime
            self._build_palette_menu()
        self.refresh()


def run() -> None:
    # Menu bar only: no Dock icon.
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    GeoWallpaperApp().run()
