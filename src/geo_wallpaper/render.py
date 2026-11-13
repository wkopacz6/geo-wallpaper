"""Render a Layout to a PNG (Pillow) or an SVG string."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from .layout import Layout, Triangle
from .palettes import Palette, parse_hex

SHADOW_OPACITY = 0.4


def _background(palette: Palette, width: int, height: int) -> Image.Image:
    size = (width, height)
    # Radial gradient centred at 70%/55%, radius 80% (same as the SVG version).
    ew, eh = int(1.6 * width), int(1.6 * height)
    grad = Image.radial_gradient("L").resize((ew, eh), Image.Resampling.BILINEAR)
    mask = Image.new("L", size, 255)
    mask.paste(grad, (int(0.7 * width - ew / 2), int(0.55 * height - eh / 2)))
    return Image.composite(
        Image.new("RGB", size, parse_hex(palette.bg_outer)),
        Image.new("RGB", size, parse_hex(palette.bg_inner)),
        mask,
    )


def _draw_shadow(img: Image.Image, t: Triangle, s: float, rgb) -> None:
    depth = t.shadow_depth * s
    sigma = depth * 0.8
    pad = depth + 3 * sigma + 2
    xs = [v[0] * s for v in t.verts]
    ys = [v[1] * s for v in t.verts]
    # Work area is the shadow's full extent (so the blur is not cut off where the
    # triangle runs off-canvas), limited to canvas +/- pad.
    x0, y0 = math.floor(min(xs) - pad), math.floor(min(ys) - pad)
    x1, y1 = math.ceil(max(xs) + pad), math.ceil(max(ys) + pad)
    x0, y0 = max(x0, -math.ceil(pad)), max(y0, -math.ceil(pad))
    x1, y1 = min(x1, img.width + math.ceil(pad)), min(y1, img.height + math.ceil(pad))
    if x1 <= x0 or y1 <= y0:
        return
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(mask).polygon(
        [(x * s + depth - x0, y * s + depth - y0) for x, y in t.verts], fill=255
    )
    mask = mask.filter(ImageFilter.GaussianBlur(sigma)).point(lambda v: int(v * SHADOW_OPACITY))
    cx0, cy0 = max(x0, 0), max(y0, 0)
    cx1, cy1 = min(x1, img.width), min(y1, img.height)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    mask = mask.crop((cx0 - x0, cy0 - y0, cx1 - x0, cy1 - y0))
    img.paste(rgb, (cx0, cy0, cx1, cy1), mask)


def _draw_body(img: Image.Image, t: Triangle, s: float) -> None:
    xs = [v[0] * s for v in t.verts]
    ys = [v[1] * s for v in t.verts]
    x0, y0 = max(0, math.floor(min(xs)) - 1), max(0, math.floor(min(ys)) - 1)
    x1, y1 = min(img.width, math.ceil(max(xs)) + 1), min(img.height, math.ceil(max(ys)) + 1)
    fw, fh = x1 - x0, y1 - y0
    if fw <= 0 or fh <= 0:
        return
    ss = 3 if max(fw, fh) <= 1500 else 2  # supersample for anti-aliasing
    layer = Image.new("RGBA", (fw * ss, fh * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    def P(p):
        return (p[0] * s - x0) * ss, (p[1] * s - y0) * ss

    v = [P(p) for p in t.verts]
    apex = P(t.apex)
    for k in range(3):
        color = (*parse_hex(t.faces[k]), 255)
        # outline == fill so neighbouring faces overlap slightly: no hairline seams
        draw.polygon([v[k], v[(k + 1) % 3], apex], fill=color, outline=color)
    small = layer.resize((fw, fh), Image.Resampling.BOX)
    img.paste(small, (x0, y0), small)


def render_png(layout: Layout, palette: Palette, width: int, height: int) -> Image.Image:
    s = width / layout.width
    img = _background(palette, width, height)
    shadow_rgb = parse_hex(palette.shadow)
    for t in layout.triangles:
        _draw_shadow(img, t, s, shadow_rgb)
    for t in layout.triangles:
        _draw_body(img, t, s)
    return img


SHADOW_STEPS = 8  # stacked translucent copies approximate a blur (no SVG filters)


def render_svg(layout: Layout, palette: Palette, width: int, height: int) -> str:
    """SVG without filters (they render inconsistently); shadows are stacked polygons."""
    f = lambda p: f"{p[0]:.1f},{p[1]:.1f}"
    shadows, bodies = [], []
    for t in layout.triangles:
        sh = t.shadow_depth
        pts = " ".join(f(v) for v in t.verts)
        layers = "".join(
            f'<polygon points="{pts}" fill="{palette.shadow}" stroke="{palette.shadow}" '
            f'stroke-linejoin="round" stroke-width="{2 * sh * 1.2 * (i + 1) / SHADOW_STEPS:.1f}" opacity="0.07"/>'
            for i in reversed(range(SHADOW_STEPS))
        )
        shadows.append(f'<g transform="translate({sh:.1f},{sh:.1f})">{layers}</g>')
        bodies.append(
            "".join(
                f'<polygon points="{f(t.verts[k])} {f(t.verts[(k + 1) % 3])} {f(t.apex)}" '
                f'fill="{t.faces[k]}" stroke="{t.faces[k]}" stroke-width="0.8" stroke-linejoin="round"/>'
                for k in range(3)
            )
        )
    nl = "\n"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {layout.width:.0f} {layout.height:.0f}" width="{width}" height="{height}">
<defs>
<radialGradient id="bg" cx="70%" cy="55%" r="80%">
<stop offset="0" stop-color="{palette.bg_inner}"/><stop offset="1" stop-color="{palette.bg_outer}"/>
</radialGradient>
</defs>
<rect width="{layout.width:.0f}" height="{layout.height:.0f}" fill="url(#bg)"/>
{nl.join(shadows)}
{nl.join(bodies)}
</svg>
"""
