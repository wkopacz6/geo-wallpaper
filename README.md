# geo-wallpaper

Generates 3D-triangle wallpapers and swaps them on a schedule (macOS).

## Setup

```sh
uv run geo-wallpaper install --menubar   # scheduler + menu bar app at login
```

The agents point at this project's `.venv`; if you move the folder, run `install` again.
Remove them with `uv run geo-wallpaper uninstall`.

## Use

```sh
uv run geo-wallpaper new                  # new wallpaper now
uv run geo-wallpaper interval 2h          # 30m .. 2w  (default 2h)
uv run geo-wallpaper palette sunset       # a name, `random-preset`, or `random`
uv run geo-wallpaper palettes             # list palettes
uv run geo-wallpaper status
uv run geo-wallpaper new -o out.svg       # also exports SVG / any size: --size 3840x2160
```

Palette modes: a specific palette (default `teal-yellow`, the original), `random-preset`
(random pick among the named palettes, including yours), or `random` (a freshly generated one).

## Your own palettes

Drop a `.toml` file in `~/.config/geo-wallpaper/palettes/` — see `_example.toml` there.
It appears in the CLI and menu bar automatically.

## How it works

launchd runs `geo-wallpaper tick` every 5 minutes; tick only changes the wallpaper once the
configured interval has passed, so long intervals survive sleep and reboots. Images go to
`~/Pictures/geo-wallpaper/` (last 8 kept); logs to `~/Library/Logs/geo-wallpaper.log`.
