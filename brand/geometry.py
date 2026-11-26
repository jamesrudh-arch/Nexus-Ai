"""NEXUS-AI brand geometry.

Every mark is defined once, as data on a single 96x96 construction grid with an 8-unit module, and
then rendered two ways: to SVG for the deliverable assets, and to a raster at several pixel sizes so
that small-size legibility is *measured* rather than asserted. Defining the geometry once is what
keeps the two renderings from drifting apart.

The three directions share a construction discipline -- one grid, one stroke weight per mark, no
gradients, and a node motif -- so that whichever is chosen, the family logic survives.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

GRID = 96.0          # mark viewBox
MODULE = 8.0         # construction module: the grid is 12 x 12 cells
CENTRE = GRID / 2.0

INK = "#0B0F14"
GRAPHITE = "#121A24"
PLATINUM = "#E6EDF3"
ACCENT = "#7364D8"   # hue 247.8 deg: inside the only free window wide enough, see docs/08


# --------------------------------------------------------------------------- primitives
@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    r: float
    fill: str | None = None
    stroke: str | None = None
    width: float = 0.0


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    stroke: str
    width: float
    cap: str = "butt"


@dataclass(frozen=True)
class Poly:
    points: tuple[tuple[float, float], ...]
    fill: str | None = None
    stroke: str | None = None
    width: float = 0.0
    close: bool = True
    join: str = "miter"


@dataclass(frozen=True)
class Path:
    d: str
    stroke: str
    width: float
    fill: str | None = None
    cap: str = "round"
    join: str = "round"


Shape = Circle | Line | Poly | Path


def polar(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    """A point at `radius` from (cx, cy), measured with 0 degrees up and increasing clockwise."""
    rad = math.radians(degrees - 90.0)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad)


def _fmt(n: float) -> str:
    return f"{n:.3f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- direction A
def convergence(fg: str, node: str | None = None, bg: str | None = None) -> list[Shape]:
    """A — CONVERGENCE.

    Four signals approach a single decision point and stop short of it. The gap is the idea, not a
    decoration: nothing touches the node until it has been admitted, which is the product's whole
    posture -- evidence converges, then a gate decides. Diagonal orientation keeps it away from the
    crosshair and the four-pointed "sparkle" that currently signals generic AI.
    """
    node_fill = node or fg
    shapes: list[Shape] = [Poly(_diamond(CENTRE, CENTRE, 11.0), fill=node_fill)]
    node_r, ray_near, ray_far, weight = 11.0, 20.0, 41.0, 10.0
    for bearing in (45.0, 135.0, 225.0, 315.0):
        x1, y1 = polar(CENTRE, CENTRE, ray_near, bearing)
        x2, y2 = polar(CENTRE, CENTRE, ray_far, bearing)
        shapes.append(Line(x1, y1, x2, y2, fg, weight, cap="butt"))
    assert ray_near - node_r >= 8.0, "the threshold gap must stay >= one grid module"
    return shapes


# --------------------------------------------------------------------------- direction B
def nexus_n(fg: str, node: str | None = None, bg: str | None = None) -> list[Shape]:
    """B — NEXUS N.

    The letter, drawn solid, with a node knocked out of the exact centre where the diagonal crosses
    the midline, and a smaller node restored inside it. The knockout is what lets the motif survive
    in one colour: with no accent available the node is still legible as a ring of background.
    """
    node_fill = node or fg
    stem = 14.0
    top, bottom = 14.0, 82.0
    left, right = 14.0, 82.0
    shapes: list[Shape] = [
        Poly(((left, top), (left + stem, top), (left + stem, bottom), (left, bottom)), fill=fg),
        Poly(((right - stem, top), (right, top), (right, bottom), (right - stem, bottom)), fill=fg),
        Poly(((left, top), (left + stem, top), (right, bottom), (right - stem, bottom)), fill=fg),
    ]
    # knockout, then the node inside it. The knockout takes the surface colour so the hole
    # reads on any approved background; callers must pass the surface they will place it on.
    shapes.append(Poly(_diamond(CENTRE, CENTRE, 16.0), fill=bg or INK))
    shapes.append(Poly(_diamond(CENTRE, CENTRE, 7.0), fill=node_fill))
    return shapes


def _diamond(cx: float, cy: float, half: float) -> tuple[tuple[float, float], ...]:
    return ((cx, cy - half), (cx + half, cy), (cx, cy + half), (cx - half, cy))


# --------------------------------------------------------------------------- direction C
def aperture(fg: str, node: str | None = None, bg: str | None = None) -> list[Shape]:
    """C — APERTURE.

    Four shutter blades arranged with rotational symmetry around a node, leaving four gaps where the
    iris would close. It is the most literal of the three about the product's discipline: an aperture
    admits only what it is opened to, and this one is drawn nearly shut, with the verified point at
    the centre. The blades are straight bars rather than a stroked polygon, which keeps the
    silhouette clean at small sizes and free of join artifacts.
    """
    node_fill = node or fg
    shapes: list[Shape] = []
    blade_r, weight = 35.0, 14.0
    for start in (45.0, 135.0, 225.0, 315.0):
        x1, y1 = polar(CENTRE, CENTRE, blade_r, start)
        x2, y2 = polar(CENTRE, CENTRE, blade_r, start + 45.0)
        shapes.append(Line(x1, y1, x2, y2, fg, weight, cap="butt"))
    shapes.append(Poly(_diamond(CENTRE, CENTRE, 11.0), fill=node_fill))
    return shapes


DIRECTIONS: dict[str, Any] = {
    "A": {"name": "Convergence", "build": convergence, "idea": "signals converging on a gated decision point"},
    "B": {"name": "Nexus N", "build": nexus_n, "idea": "the letter, with the connection point at its centre"},
    "C": {"name": "Aperture", "build": aperture, "idea": "an iris that admits only what has been verified"},
}


# --------------------------------------------------------------------------- SVG
def to_svg(shapes: list[Shape], *, size: float = GRID, bg: str | None = None) -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(GRID)} {_fmt(GRID)}" '
        f'width="{_fmt(size)}" height="{_fmt(size)}" role="img">'
    ]
    if bg:
        parts.append(f'<rect width="{_fmt(GRID)}" height="{_fmt(GRID)}" fill="{bg}"/>')
    for sh in shapes:
        if isinstance(sh, Circle):
            attrs = f'cx="{_fmt(sh.cx)}" cy="{_fmt(sh.cy)}" r="{_fmt(sh.r)}"'
            if sh.fill:
                attrs += f' fill="{sh.fill}"'
            else:
                attrs += ' fill="none"'
            if sh.stroke:
                attrs += f' stroke="{sh.stroke}" stroke-width="{_fmt(sh.width)}"'
            parts.append(f"<circle {attrs}/>")
        elif isinstance(sh, Line):
            parts.append(
                f'<line x1="{_fmt(sh.x1)}" y1="{_fmt(sh.y1)}" x2="{_fmt(sh.x2)}" y2="{_fmt(sh.y2)}" '
                f'stroke="{sh.stroke}" stroke-width="{_fmt(sh.width)}" stroke-linecap="{sh.cap}"/>'
            )
        elif isinstance(sh, Poly):
            pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in sh.points)
            attrs = f'points="{pts}"'
            attrs += f' fill="{sh.fill}"' if sh.fill else ' fill="none"'
            if sh.stroke:
                attrs += (
                    f' stroke="{sh.stroke}" stroke-width="{_fmt(sh.width)}" '
                    f'stroke-linejoin="{sh.join}"'
                )
            parts.append(f"<polygon {attrs}/>")
        elif isinstance(sh, Path):
            attrs = f'd="{sh.d}" stroke="{sh.stroke}" stroke-width="{_fmt(sh.width)}"'
            attrs += f' fill="{sh.fill}"' if sh.fill else ' fill="none"'
            attrs += f' stroke-linecap="{sh.cap}" stroke-linejoin="{sh.join}"'
            parts.append(f"<path {attrs}/>")
    parts.append("</svg>")
    return "".join(parts)
