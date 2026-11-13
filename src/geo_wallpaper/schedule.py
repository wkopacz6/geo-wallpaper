"""launchd LaunchAgents: the periodic `tick` job and the menu bar login item."""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

from . import config

TICK_LABEL = "com.geo-wallpaper.tick"
MENUBAR_LABEL = "com.geo-wallpaper.menubar"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def plist_path(label: str) -> Path:
    return LAUNCH_AGENTS / f"{label}.plist"


def is_installed(label: str) -> bool:
    return plist_path(label).exists()


def build_plist(label: str) -> bytes:
    command = "tick" if label == TICK_LABEL else "menubar"
    data: dict = {
        "Label": label,
        # The interpreter that ran `install`, so the agent uses the same environment.
        "ProgramArguments": [sys.executable, "-m", "geo_wallpaper", command],
        "RunAtLoad": True,
        "StandardOutPath": str(config.LOG_FILE),
        "StandardErrorPath": str(config.LOG_FILE),
    }
    if label == TICK_LABEL:
        data["StartInterval"] = config.TICK_SECONDS
        data["ProcessType"] = "Background"
    else:
        # Restart after a crash, but stay quit when the user picks "Quit".
        data["KeepAlive"] = {"SuccessfulExit": False}
        data["ProcessType"] = "Interactive"
        data["LimitLoadToSessionType"] = "Aqua"
    return plistlib.dumps(data)


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(label: str, *, load: bool = True) -> Path:
    """Write the plist and (optionally) load it now. Loading the menu bar agent from
    inside the running app would start a second copy, so the app passes load=False."""
    path = plist_path(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_plist(label))
    if load:
        domain = f"gui/{os.getuid()}"
        _launchctl("bootout", f"{domain}/{label}")  # fine if it wasn't loaded
        for attempt in range(4):  # bootout can still be settling
            result = _launchctl("bootstrap", domain, str(path))
            if result.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"launchctl bootstrap failed: {result.stderr.strip()}")
    return path


def uninstall(label: str, *, unload: bool = True) -> None:
    if unload:
        _launchctl("bootout", f"gui/{os.getuid()}/{label}")
    plist_path(label).unlink(missing_ok=True)
