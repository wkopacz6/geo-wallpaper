"""macOS screen info and setting the desktop picture (via AppKit, no permissions needed)."""
from __future__ import annotations

from pathlib import Path

FALLBACK_SIZE = (2560, 1600)


def _appkit():
    try:
        import AppKit

        return AppKit
    except ImportError:
        return None


def screen_sizes() -> list[tuple[int, int]]:
    """Native pixel size of every connected display."""
    ak = _appkit()
    if ak is None:
        return [FALLBACK_SIZE]
    sizes = []
    for screen in ak.NSScreen.screens():
        frame, scale = screen.frame(), screen.backingScaleFactor()
        sizes.append((int(frame.size.width * scale), int(frame.size.height * scale)))
    return sizes or [FALLBACK_SIZE]


def set_wallpapers(paths: list[Path]) -> None:
    """Set one image per display (in NSScreen order; extra displays reuse the last image)."""
    ak = _appkit()
    if ak is None:
        raise RuntimeError("AppKit is not available (macOS only)")
    ws = ak.NSWorkspace.sharedWorkspace()
    options = {
        ak.NSWorkspaceDesktopImageScalingKey: ak.NSImageScaleProportionallyUpOrDown,
        ak.NSWorkspaceDesktopImageAllowClippingKey: True,
    }
    for i, screen in enumerate(ak.NSScreen.screens()):
        path = paths[min(i, len(paths) - 1)]
        url = ak.NSURL.fileURLWithPath_(str(path))
        ok, err = ws.setDesktopImageURL_forScreen_options_error_(url, screen, options, None)
        if not ok:
            raise RuntimeError(f"could not set wallpaper on display {i + 1}: {err}")


def current_wallpapers() -> list[Path]:
    ak = _appkit()
    if ak is None:
        return []
    ws = ak.NSWorkspace.sharedWorkspace()
    return [Path(ws.desktopImageURLForScreen_(s).path()) for s in ak.NSScreen.screens()]
