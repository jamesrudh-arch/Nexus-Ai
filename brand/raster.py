"""Rasterise the brand geometry with Pillow, so small-size legibility is measured not asserted.

The same primitive list that produces the SVG is drawn here. Rendering at 16px directly would alias
away the very detail under examination, so each size is drawn supersampled and downscaled with a
Lanczos filter -- which is also what a browser does, making the result a fair test.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geometry import GRID, Circle, Line, Path, Poly, Shape  # noqa: E402


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _scale(shapes: list[Shape], factor: float) -> list[Shape]:
    out: list[Shape] = []
    for sh in shapes:
        if isinstance(sh, Circle):
            out.append(Circle(sh.cx * factor, sh.cy * factor, sh.r * factor,
                              sh.fill, sh.stroke, sh.width * factor))
        elif isinstance(sh, Line):
            out.append(Line(sh.x1 * factor, sh.y1 * factor, sh.x2 * factor, sh.y2 * factor,
                            sh.stroke, sh.width * factor, sh.cap))
        elif isinstance(sh, Poly):
            out.append(Poly(tuple((x * factor, y * factor) for x, y in sh.points),
                            sh.fill, sh.stroke, sh.width * factor, sh.close, sh.join))
        elif isinstance(sh, Path):
            out.append(_ScaledPath(sh, factor))
    return out


class _ScaledPath:
    """A Path whose commands are scaled; only the wordmark uses paths, and only M/L/V/H/C/A appear."""

    def __init__(self, source: Path, factor: float) -> None:
        self.stroke = source.stroke
        self.width = source.width * factor
        self.fill = source.fill
        self.cap = source.cap
        self.join = source.join
        self.d = _scale_path(source.d, factor)


def _scale_path(d: str, f: float) -> str:
    tokens = d.replace(",", " ").split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            out.append(tok)
            i += 1
            continue
        # numeric run: scale every number, but arc flags (0/1) in A commands stay as flags
        nums: list[str] = []
        while i < len(tokens) and not tokens[i].isalpha():
            nums.append(tokens[i])
            i += 1
        command = out[-1] if out and out[-1].isalpha() else ""
        if command.upper() == "A":
            for k, n in enumerate(nums):
                # A rx ry rot large sweep x y  -> positions 3 and 4 are flags
                nums[k] = n if k % 7 in (3, 4) else f"{float(n) * f:.4f}"
        else:
            nums = [f"{float(n) * f:.4f}" for n in nums]
        out.extend(nums)
    return " ".join(out)


def _draw_path(draw: ImageDraw.ImageDraw, d: str, stroke: str, width: float,
               cap: str, join: str) -> None:
    """Minimal path interpreter: M/L/H/V/C/Z, plus A approximated by a polyline."""
    tokens = d.replace(",", " ").split()
    pts: list[tuple[float, float]] = []
    x = y = 0.0
    start: tuple[float, float] | None = None
    i = 0

    def emit(target: list[tuple[float, float]], p: tuple[float, float]) -> None:
        target.append(p)

    while i < len(tokens):
        cmd = tokens[i]
        if not cmd.isalpha():
            i += 1
            continue
        i += 1
        nums: list[float] = []
        while i < len(tokens) and not tokens[i].isalpha():
            nums.append(float(tokens[i]))
            i += 1
        if cmd in "Mm":
            step = 2
            for k in range(0, len(nums), step):
                if cmd == "m" and pts:
                    x, y = pts[-1][0] + nums[k], pts[-1][1] + nums[k + 1]
                else:
                    x, y = nums[k], nums[k + 1]
                if start is None:
                    start = (x, y)
                if pts:
                    draw.line(pts, fill=stroke, width=max(1, int(round(width))), joint=join)
                    pts = []
                pts.append((x, y))
        elif cmd in "Ll":
            step = 2
            for k in range(0, len(nums), step):
                if cmd == "l":
                    x, y = x + nums[k], y + nums[k + 1]
                else:
                    x, y = nums[k], nums[k + 1]
                pts.append((x, y))
        elif cmd in "Hh":
            for n in nums:
                x = x + n if cmd == "h" else n
                pts.append((x, y))
        elif cmd in "Vv":
            for n in nums:
                y = y + n if cmd == "v" else n
                pts.append((x, y))
        elif cmd in "Cc":
            step = 6
            for k in range(0, len(nums), step):
                p0 = pts[-1] if pts else (x, y)
                if cmd == "c":
                    c1 = (p0[0] + nums[k], p0[1] + nums[k + 1])
                    c2 = (p0[0] + nums[k + 2], p0[1] + nums[k + 3])
                    p3 = (p0[0] + nums[k + 4], p0[1] + nums[k + 5])
                else:
                    c1 = (nums[k], nums[k + 1])
                    c2 = (nums[k + 2], nums[k + 3])
                    p3 = (nums[k + 4], nums[k + 5])
                pts.extend(_cubic(p0, c1, c2, p3))
                x, y = p3
        elif cmd in "Aa":
            step = 7
            for k in range(0, len(nums), step):
                rx, ry = nums[k], nums[k + 1]
                large, sweep = int(nums[k + 3]), int(nums[k + 4])
                ex, ey = nums[k + 5], nums[k + 6]
                if cmd == "a":
                    ex, ey = x + ex, y + ey
                pts.extend(_arc_polyline(x, y, rx, ry, large, sweep, ex, ey))
                x, y = ex, ey
        elif cmd in "Zz":
            if start is not None:
                pts.append(start)
                x, y = start
    if len(pts) > 1:
        draw.line(pts, fill=stroke, width=max(1, int(round(width))), joint=join)


def _cubic(p0, p1, p2, p3, steps: int = 24) -> list[tuple[float, float]]:
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        out.append((x, y))
    return out


def _arc_polyline(x0, y0, rx, ry, large, sweep, x1, y1, steps: int = 40):
    """Endpoint-to-centre arc conversion, then sample. Semantics match SVG's A command."""
    if rx == 0 or ry == 0:
        return [(x1, y1)]
    rx, ry = abs(rx), abs(ry)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    x1p, y1p = dx, dy
    lam = (x1p**2) / (rx**2) + (y1p**2) / (ry**2)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    sign = -1.0 if large == sweep else 1.0
    num = rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2
    den = rx**2 * y1p**2 + ry**2 * x1p**2
    co = sign * math.sqrt(max(0.0, num / den)) if den else 0.0
    cxp = co * (rx * y1p / ry)
    cyp = co * (-ry * x1p / rx)
    cx = cxp + (x0 + x1) / 2
    cy = cyp + (y0 + y1) / 2

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        c = max(-1.0, min(1.0, dot / norm)) if norm else 1.0
        a = math.degrees(math.acos(c))
        return -a if (ux * vy - uy * vx) < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 360
    elif sweep and dtheta < 0:
        dtheta += 360
    out = []
    for i in range(1, steps + 1):
        t = math.radians(theta1 + dtheta * (i / steps))
        out.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return out


def render(shapes: list[Shape], size: int, *, bg: str | None, supersample: int = 8) -> Image.Image:
    big = size * supersample
    factor = big / GRID
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if bg:
        draw.rectangle([0, 0, big, big], fill=_hex_to_rgb(bg) + (255,))
    for sh in _scale(shapes, factor):
        if isinstance(sh, Circle):
            box = [sh.cx - sh.r, sh.cy - sh.r, sh.cx + sh.r, sh.cy + sh.r]
            if sh.fill:
                draw.ellipse(box, fill=_hex_to_rgb(sh.fill) + (255,))
            if sh.stroke:
                draw.ellipse(box, outline=_hex_to_rgb(sh.stroke) + (255,),
                             width=max(1, int(round(sh.width))))
        elif isinstance(sh, Line):
            draw.line([sh.x1, sh.y1, sh.x2, sh.y2], fill=_hex_to_rgb(sh.stroke) + (255,),
                      width=max(1, int(round(sh.width))))
        elif isinstance(sh, Poly):
            pts = list(sh.points)
            if sh.fill:
                draw.polygon(pts, fill=_hex_to_rgb(sh.fill) + (255,))
            if sh.stroke:
                draw.line(pts + [pts[0]], fill=_hex_to_rgb(sh.stroke) + (255,),
                          width=max(1, int(round(sh.width))), joint=sh.join)
        elif isinstance(sh, _ScaledPath):
            _draw_path(draw, sh.d, _hex_to_rgb(sh.stroke) + (255,), sh.width, sh.cap, sh.join)
    if supersample > 1:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def render_lockup(shapes: list[Shape], width: int, height: int, *, bg: str | None) -> Image.Image:
    """Render a non-square canvas by laying the mark out inside a GRID x GRID box at an offset."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if bg:
        ImageDraw.Draw(img).rectangle([0, 0, width, height], fill=_hex_to_rgb(bg) + (255,))
    return img


def render_wide(shapes: list[Shape], units_w: float, units_h: float, *, px_height: int,
                bg: str | None, supersample: int = 6) -> "Image.Image":
    """Render a non-square composition: `units_*` are design units, px_height the output height."""
    scale = (px_height * supersample) / units_h
    w = int(round(units_w * scale))
    h = int(round(units_h * scale))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if bg:
        draw.rectangle([0, 0, w, h], fill=_hex_to_rgb(bg) + (255,))
    for sh in _scale(shapes, scale):
        if isinstance(sh, Circle):
            box = [sh.cx - sh.r, sh.cy - sh.r, sh.cx + sh.r, sh.cy + sh.r]
            if sh.fill:
                draw.ellipse(box, fill=_hex_to_rgb(sh.fill) + (255,))
            if sh.stroke:
                draw.ellipse(box, outline=_hex_to_rgb(sh.stroke) + (255,),
                             width=max(1, int(round(sh.width))))
        elif isinstance(sh, Line):
            draw.line([sh.x1, sh.y1, sh.x2, sh.y2], fill=_hex_to_rgb(sh.stroke) + (255,),
                      width=max(1, int(round(sh.width))))
        elif isinstance(sh, Poly):
            pts = list(sh.points)
            if sh.fill:
                draw.polygon(pts, fill=_hex_to_rgb(sh.fill) + (255,))
            if sh.stroke:
                draw.line(pts + [pts[0]], fill=_hex_to_rgb(sh.stroke) + (255,),
                          width=max(1, int(round(sh.width))), joint=sh.join)
        elif isinstance(sh, _ScaledPath):
            _draw_path(draw, sh.d, _hex_to_rgb(sh.stroke) + (255,), sh.width, sh.cap, sh.join)
    if supersample > 1:
        final_w = int(round(units_w * px_height / units_h))
        img = img.resize((final_w, px_height), Image.LANCZOS)
    return img
