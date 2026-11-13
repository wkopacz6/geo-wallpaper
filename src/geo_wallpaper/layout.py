"""Random, non-overlapping triangle layout in resolution-independent units."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .palettes import Palette

DESIGN_WIDTH = 2000.0  # layout units; renderers scale to the real pixel width
REF_HEIGHT = 1333.0
REF_COUNT = 38  # triangles for a 2000x1333 canvas; other shapes scale by area
DEFAULT_GAP = 24.0  # minimum clearance between triangles, in layout units
ATTEMPTS = 300  # placement tries per triangle before it is dropped

# Region (fractions of the canvas) kept empty for desktop icons / widgets.
CLEAR_X = (0.65, 0.95)
CLEAR_Y = (250 / 1333, 1000 / 1333)

Point = tuple[float, float]


@dataclass(frozen=True)
class Triangle:
    verts: tuple[Point, Point, Point]
    apex: Point
    faces: tuple[str, str, str]  # colours of faces over edges (v0,v1), (v1,v2), (v2,v0)
    size: float

    @property
    def shadow_depth(self) -> float:
        """Bigger shapes float higher: bigger offset and softer shadow."""
        return max(2.0, self.size / 14)


@dataclass(frozen=True)
class Layout:
    width: float
    height: float
    triangles: list[Triangle]


def _bbox(poly) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_apart(a, b, gap: float) -> bool:
    return a[0] - b[2] >= gap or b[0] - a[2] >= gap or a[1] - b[3] >= gap or b[1] - a[3] >= gap


def _separated(p, q, margin: float) -> bool:
    """Separating-axis test: True if convex polygons p and q are >= margin apart."""
    for poly in (p, q):
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            nx, ny = y1 - y2, x2 - x1
            n = math.hypot(nx, ny) or 1.0
            nx, ny = nx / n, ny / n
            pa = [x * nx + y * ny for x, y in p]
            qa = [x * nx + y * ny for x, y in q]
            if min(qa) - max(pa) >= margin or min(pa) - max(qa) >= margin:
                return True
    return False


def _make_vertices(rng: random.Random, size: float, w: float, h: float):
    cx = rng.uniform(-100, w + 100)
    cy = rng.uniform(-100, h + 100)
    rot = rng.random() * math.tau
    verts = []
    for k in range(3):
        # Slightly irregular: jitter each vertex's angle and radius
        a = rot + k * math.tau / 3 + rng.uniform(-0.35, 0.35)
        r = size * rng.uniform(0.75, 1.15)
        verts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return tuple(verts)


def generate_layout(
    palette: Palette,
    pixel_width: int,
    pixel_height: int,
    *,
    count: int | None = None,
    seed: int | None = None,
    gap: float = DEFAULT_GAP,
    keep_clear: bool = True,
) -> Layout:
    rng = random.Random(seed)
    w = DESIGN_WIDTH
    h = w * pixel_height / pixel_width
    if count is None:
        count = max(1, round(REF_COUNT * h / REF_HEIGHT))

    # Many small triangles, a few huge ones; place the big ones first so they fit.
    sizes = sorted((30 + rng.random() ** 2.6 * 380 for _ in range(count)), reverse=True)

    placed: list[tuple[tuple[Point, Point, Point], tuple[float, float, float, float], float]] = []
    for size in sizes:
        for _ in range(ATTEMPTS):
            verts = _make_vertices(rng, size, w, h)
            gx = sum(v[0] for v in verts) / 3
            gy = sum(v[1] for v in verts) / 3
            if keep_clear and CLEAR_X[0] * w < gx < CLEAR_X[1] * w and CLEAR_Y[0] * h < gy < CLEAR_Y[1] * h:
                continue
            bb = _bbox(verts)
            if all(_bbox_apart(bb, ob, gap) or _separated(verts, ov, gap) for ov, ob, _ in placed):
                placed.append((verts, bb, size))
                break

    weights = [g.weight for g in palette.groups]
    triangles = []
    for verts, _, size in placed:
        gx = sum(v[0] for v in verts) / 3
        gy = sum(v[1] for v in verts) / 3
        # Inner apex, offset from the centroid, gives the pyramid-from-above look
        apex = (gx + rng.uniform(-0.18, 0.18) * size, gy + rng.uniform(-0.18, 0.18) * size)
        group = rng.choices(palette.groups, weights=weights)[0]
        shift = rng.randrange(3)  # vary which face gets which shade
        faces = tuple(group.faces[(k + shift) % 3] for k in range(3))
        triangles.append(Triangle(verts, apex, faces, size))
    return Layout(w, h, triangles)
