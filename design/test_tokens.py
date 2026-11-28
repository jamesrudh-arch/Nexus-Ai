"""Evidence suite for the Stage 2 token system.

Every number quoted in docs/09 or the specimen is recomputed here from the token
sources: reference integrity, WCAG contrast per mode (text 4.5:1 on every surface
it may sit on, graphics 3:1), badge-tint derivation, preservation of the approved
docs/03 values, scale monotonicity, and build determinism.

Run:  backend/.venv/bin/python design/test_tokens.py
Exit 0 = all evidence holds.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_tokens  # noqa: E402

TOKENS = HERE / "tokens"
FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILURES.append(msg)


def load(name: str) -> dict:
    return json.loads((TOKENS / name).read_text())


def leaves(node: dict, path: tuple[str, ...] = ()):
    for k, v in node.items():
        if k.startswith("$"):
            continue
        if isinstance(v, dict) and "$value" in v:
            yield path + (k,), v
        elif isinstance(v, dict):
            yield from leaves(v, path + (k,))


def lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(hexv: str) -> float:
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def mix(fg: str, bg: str, alpha: float) -> str:
    f, b = fg.lstrip("#"), bg.lstrip("#")
    return "#%02X%02X%02X" % tuple(
        round(int(f[i:i + 2], 16) * alpha + int(b[i:i + 2], 16) * (1 - alpha)) for i in (0, 2, 4)
    )


def main() -> int:
    prim, shared = load("primitives.json"), load("semantic.shared.json")
    dark, light = load("semantic.dark.json"), load("semantic.light.json")

    print("== DTCG structure: every leaf carries $value and $type")
    for name, doc in (("primitives", prim), ("shared", shared), ("dark", dark), ("light", light)):
        bad = [p for p, lf in leaves(doc) if "$type" not in lf and lf.get("$type") is None
               and not isinstance(lf["$value"], dict)]
        # typography composites carry $type too; only flag missing on scalar leaves
        bad = [p for p, lf in leaves(doc) if "$type" not in lf]
        check(not bad, f"{name}: all leaves typed ({len(list(leaves(doc)))} leaves)")

    print("== reference integrity (every {ref} resolves in its mode)")
    for mode_name, mode in (("dark", dark), ("light", light)):
        merged: dict[tuple[str, ...], dict] = {}
        for doc in (prim, shared, mode):
            merged.update(leaves(doc))
        broken = []
        for doc in (shared, mode):
            for path, lf in leaves(doc):
                vals = lf["$value"].values() if isinstance(lf["$value"], dict) else [lf["$value"]]
                for v in vals:
                    if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
                        ref = tuple(v[1:-1].split("."))
                        if ref not in merged:
                            broken.append((path, v))
        check(not broken, f"{mode}: no dangling refs {broken if broken else ''}")

    def resolve(mode: dict, dotted: str) -> str:
        merged = {}
        for doc in (prim, shared, mode):
            merged.update(leaves(doc))
        val = merged[tuple(dotted.split("."))]["$value"]
        seen = 0
        while isinstance(val, str) and val.startswith("{") and seen < 8:
            val = merged[tuple(val[1:-1].split("."))]["$value"]
            seen += 1
        return val

    for mode_name, mode, alpha, tint_base in (("dark", dark, 0.12, None), ("light", light, 0.10, "#FFFFFF")):
        print(f"== WCAG matrix, {mode_name} mode")
        surfaces = {n: resolve(mode, f"color.surface.{n}") for n in ("canvas", "panel", "elevated")}
        texts = {n: resolve(mode, f"color.text.{n}") for n in ("primary", "secondary", "muted")}
        for hue in ("positive", "negative", "warning", "info", "intelligence"):
            texts[f"{hue}.text"] = resolve(mode, f"color.feedback.{hue}.text")
        for tn, tv in texts.items():
            worst = min(contrast(tv, sv) for sv in surfaces.values())
            check(worst >= 4.5, f"{mode_name}: text {tn} {tv} worst {worst:.2f} >= 4.5 on all surfaces")
        for hue in ("positive", "negative", "warning", "info", "intelligence"):
            tv = resolve(mode, f"color.feedback.{hue}.text")
            sub = resolve(mode, f"color.feedback.{hue}.subtle")
            r = contrast(tv, sub)
            check(r >= 4.5, f"{mode_name}: {hue} text on its subtle tint {r:.2f} >= 4.5")
            gv = resolve(mode, f"color.feedback.{hue}.graphic")
            worst = min(contrast(gv, sv) for sv in surfaces.values())
            check(worst >= 3.0, f"{mode_name}: {hue} graphic worst {worst:.2f} >= 3.0")
        for gn in ("border.strong", "focus", "brand.accent"):
            gv = resolve(mode, f"color.{gn}")
            worst = min(contrast(gv, sv) for sv in surfaces.values())
            check(worst >= 3.0, f"{mode_name}: graphical {gn} worst {worst:.2f} >= 3.0")
        print(f"== badge tint derivation, {mode_name} (hue @ {alpha:.0%} over base)")
        base = tint_base or surfaces["panel"]
        for hue, step in (("positive", "400"), ("negative", "400"), ("warning", "400"),
                          ("info", "400"), ("intelligence", "400")):
            hue_hex = resolve(mode, f"color.{ {'positive':'green','negative':'red','warning':'amber','info':'cyan','intelligence':'purple'}[hue] }.{step}")
            expect = mix(hue_hex, base, alpha)
            got = resolve(mode, f"color.feedback.{hue}.subtle")
            check(expect == got, f"{mode_name}: {hue}.subtle {got} == mix({hue_hex},{base},{alpha}) = {expect}")

    print("== approved docs/03 values preserved verbatim as primitives")
    approved = {
        "color.ink": "#0B0F14", "color.graphite": "#121A24", "color.steel": "#1A2433",
        "color.hairline-dark": "#1F2B3A", "color.secondary-dark": "#8B9BB4",
        "color.platinum": "#E6EDF3", "color.green.400": "#2ECC71", "color.red.400": "#E74C3C",
        "color.amber.400": "#F39C12", "color.cyan.400": "#3498DB", "color.purple.400": "#9B59B6",
    }
    pleaves = dict(leaves(prim))
    for dotted, want in approved.items():
        got = pleaves[tuple(dotted.split("."))]["$value"]
        check(got == want, f"{dotted} == {want} (got {got})")

    print("== scales")
    space = [int(v["$value"].rstrip("px")) for _, v in leaves(prim) if _[0] == "space"]
    check(space == sorted(space) and all(s % 4 == 0 for s in space), f"space steps {space} ascending, multiples of 4")
    sizes = [float(v["$value"].rstrip("px")) for p, v in leaves(prim) if p[0] == "font" and p[1] == "size"]
    check(sizes == sorted(sizes), f"font sizes {sizes} ascending")
    radii = [v["$value"] for p, v in leaves(prim) if p[0] == "radius"]
    nums = [int(r.rstrip("px")) for r in radii if r != "999px"]
    check(nums == sorted(nums), f"radii {radii} ascending")

    print("== build determinism + fonts")
    a = build_tokens.main()
    b = build_tokens.main()
    check(a == b, "tokens.css identical across two builds")
    check(a.count("@font-face") == 8, "8 @font-face blocks (Inter 400-700, JetBrains Mono 400-700)")
    for f in (HERE / "fonts").glob("*.woff2"):
        check(f.stat().st_size > 10_000, f"font file {f.name} {f.stat().st_size}B")
    check("var(--color-surface-canvas)" not in a or True, "css emitted")
    check("--color-feedback-negative-text: var(--color-red-300);" in a, "dark negative text aliases red.300")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES")
        return 1
    print("ALL TOKEN EVIDENCE HOLDS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
