"""Compose the NEXUS-AI identity: wordmark, lockups, app icon, and the SVG asset files.

The wordmark is hand-drawn as monoline geometry on the same construction logic as the marks, not set
in a typeface. Two reasons: the identity must not depend on a font being installed (Inter is not
present in this environment, so a font-set wordmark would render differently here than anywhere
else), and a real wordmark is drawn, not typed. The full typographic system is deliberately Stage 2.
"""

from __future__ import annotations

import pathlib
import re
from geometry import GRID, ACCENT, INK, PLATINUM, Path, DIRECTIONS, to_svg, _fmt

CAP = 48.0        # wordmark cap height, in wordmark-local units
STROKE = 7.0      # monoline weight
TRACK = 10.0      # letter tracking

# letter paths in local boxes (0,0)-(w,CAP), monoline, round caps/joins
GLYPHS: dict[str, tuple[float, str]] = {
    "N": (40.0, "M3.5,44.5 L3.5,3.5 L36.5,44.5 L36.5,3.5"),
    "E": (30.0, "M30,3.5 L3.5,3.5 L3.5,44.5 L30,44.5 M3.5,24 L24,24"),
    "X": (36.0, "M3.5,3.5 L32.5,44.5 M32.5,3.5 L3.5,44.5"),
    "U": (40.0, "M3.5,3.5 L3.5,28 A16.5,16.5 0 0 0 36.5,28 L36.5,3.5"),
    "S": (32.0, "M28.5,10 C28.5,5 23,3.5 16,3.5 C8,3.5 3.5,8 3.5,14 C3.5,21 9,24 16,26 "
                 "C24,28 28.5,31 28.5,37 C28.5,43 23,44.5 16,44.5 C9,44.5 3.5,43 3.5,38"),
    "-": (16.0, "M0,24 L16,24"),
    "A": (40.0, "M3.5,44.5 L20,3.5 L36.5,44.5 M10.5,29 L29.5,29"),
    "I": (7.0, "M3.5,3.5 L3.5,44.5"),
}
WORD = "NEXUS-AI"


def word_width(text: str = WORD) -> float:
    total = 0.0
    for i, ch in enumerate(text):
        total += GLYPHS[ch][0]
        if i < len(text) - 1:
            total += TRACK
    return total


def wordmark_paths(text: str, *, x: float, y: float, scale: float,
                   colour: str, accent_from: int | None = None) -> list[Path]:
    """Lay the wordmark out at (x, y) top-left, scaled, returning Path primitives."""
    out: list[Path] = []
    cursor = x
    for i, ch in enumerate(text):
        w, d = GLYPHS[ch]
        colour_i = colour
        if accent_from is not None and i >= accent_from:
            colour_i = ACCENT
        # shift the path data into place
        out.append(Path(_translate(d, cursor, y, scale), colour_i, STROKE * scale))
        cursor += (w + TRACK) * scale
    return out


def _translate(d: str, dx: float, dy: float, s: float) -> str:
    tokens = re.findall(r"[A-Za-z]|-?\d*\.?\d+", d)
    out: list[str] = []
    i = 0
    cmd = ""
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            out.append(tok)
            i += 1
            continue
        nums: list[float] = []
        while i < len(tokens) and not tokens[i].isalpha():
            nums.append(float(tokens[i]))
            i += 1
        scaled: list[str] = []
        for k, n in enumerate(nums):
            if cmd.upper() == "A":
                # rx ry rot large-arc sweep x y : the flags and the rotation are not coordinates,
                # and the radii scale but do not translate, so parity cannot decide x vs y here.
                m = k % 7
                if m in (3, 4):
                    scaled.append(str(int(n)))
                elif m == 2:
                    scaled.append(_fmt(n))
                elif m in (0, 1):
                    scaled.append(_fmt(n * s))
                elif m == 5:
                    scaled.append(_fmt(n * s + dx))
                else:
                    scaled.append(_fmt(n * s + dy))
                continue
            if k % 2 == 0:
                scaled.append(_fmt(n * s + dx))
            else:
                scaled.append(_fmt(n * s + dy))
        out.extend(scaled)
    return " ".join(out)


def primary_lockup(fg: str, *, accent: bool = True, cap: float = 44.0) -> str:
    """Horizontal: mark left, wordmark right, optically centred."""
    gap = 26.0
    scale = cap / CAP
    ww = word_width() * scale
    height = GRID
    width = GRID + gap + ww + 4.0
    shapes = DIRECTIONS["B"]["build"](fg, node=ACCENT if accent else None)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(width)} {_fmt(height)}" '
        f'role="img" aria-label="NEXUS-AI">'
    ]
    for sh in shapes:
        parts.append(_shape_svg(sh))
    y = (height - cap) / 2.0
    for path in wordmark_paths(WORD, x=GRID + gap, y=y, scale=scale, colour=fg,
                               accent_from=len("NEXUS-") if accent else None):
        parts.append(_shape_svg(path))
    parts.append("</svg>")
    return "".join(parts)


def stacked_lockup(fg: str, *, accent: bool = True) -> str:
    """Vertical secondary: mark centred above the wordmark."""
    target_word_width = GRID
    scale = target_word_width / word_width()
    cap = CAP * scale
    gap = 14.0
    height = GRID + gap + cap + 4.0
    shapes = DIRECTIONS["B"]["build"](fg, node=ACCENT if accent else None)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(GRID)} {_fmt(height)}" '
        f'role="img" aria-label="NEXUS-AI">'
    ]
    for sh in shapes:
        parts.append(_shape_svg(sh))
    x = (GRID - word_width() * scale) / 2.0
    for path in wordmark_paths(WORD, x=x, y=GRID + gap, scale=scale, colour=fg,
                               accent_from=len("NEXUS-") if accent else None):
        parts.append(_shape_svg(path))
    parts.append("</svg>")
    return "".join(parts)


def _shape_svg(sh) -> str:
    return to_svg([sh]).replace('<svg xmlns="http://www.w3.org/2000/svg" '
                                f'viewBox="0 0 {_fmt(GRID)} {_fmt(GRID)}" '
                                'width="96" height="96" role="img">', "").replace("</svg>", "")


def app_icon(fg: str, bg: str, *, radius: float = 22.0) -> str:
    """Rounded tile with the mark inset to the iOS safe area."""
    inset = 18.0
    shapes = DIRECTIONS["B"]["build"](fg, node=ACCENT)
    inner = []
    for sh in shapes:
        inner.append(_shape_svg(sh))
    inner_svg = "".join(inner)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(GRID)} {_fmt(GRID)}" role="img">'
        f'<rect width="{_fmt(GRID)}" height="{_fmt(GRID)}" rx="{_fmt(radius)}" fill="{bg}"/>'
        f'<g transform="translate({inset},{inset}) scale({(GRID - 2 * inset) / GRID})">'
        f'{inner_svg}</g></svg>'
    )


def write_assets(out_dir: pathlib.Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    # Masters are locked to their approved surface: B's knockout is a surface-coloured
    # counterform, so a transparent master would lose the node on the wrong ground.
    for key in DIRECTIONS:
        for variant, fg, node, bg in (
            ("on-ink", PLATINUM, ACCENT, INK),
            ("on-platinum", INK, ACCENT, PLATINUM),
            ("mono-on-ink", PLATINUM, PLATINUM, INK),
            ("mono-on-platinum", INK, INK, PLATINUM),
        ):
            shapes = DIRECTIONS[key]["build"](fg, node=node, bg=bg)
            name = f"mark-{key.lower()}-{variant}.svg"
            (out_dir / name).write_text(to_svg(shapes, bg=bg))
            written.append(name)
    for name, svg in (
        ("lockup-primary-on-ink.svg", wrap(primary_lockup(PLATINUM), INK)),
        ("lockup-primary-on-platinum.svg", wrap(primary_lockup(INK), PLATINUM)),
        ("lockup-stacked-on-ink.svg", wrap(stacked_lockup(PLATINUM), INK)),
        ("lockup-stacked-on-platinum.svg", wrap(stacked_lockup(INK), PLATINUM)),
        ("app-icon-on-ink.svg", app_icon(PLATINUM, INK)),
        ("app-icon-on-platinum.svg", app_icon(INK, PLATINUM)),
    ):
        (out_dir / name).write_text(svg)
        written.append(name)
    return written


def wrap(svg: str, bg: str) -> str:
    """Insert a background rect as the first child, preserving the viewBox."""
    head, rest = svg.split(">", 1)
    vb = head.split('viewBox="')[1].split('"')[0].split()
    w, h = vb[-2], vb[-1]
    return f'{head}><rect width="{w}" height="{h}" fill="{bg}"/>{rest}'
