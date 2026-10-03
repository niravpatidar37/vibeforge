"""Generate VibeForge "After Hours" brand assets as font-independent SVG.

All text is converted to outlines, so the SVGs render identically without fonts.

Fonts (SIL OFL 1.1) must sit next to this script; they are not committed:
  curl -sSfLo Fraunces.ttf        "https://github.com/google/fonts/raw/main/ofl/fraunces/Fraunces%5BSOFT,WONK,opsz,wght%5D.ttf"
  curl -sSfLo Fraunces-Italic.ttf "https://github.com/google/fonts/raw/main/ofl/fraunces/Fraunces-Italic%5BSOFT,WONK,opsz,wght%5D.ttf"
  curl -sSfLo DMMono-Medium.ttf   "https://github.com/google/fonts/raw/main/ofl/dmmono/DMMono-Medium.ttf"
Run:
  uv run --no-project --with fonttools --with uharfbuzz python build_brand.py ../
PNG exports (social-preview.png, logo-mark-512.png, apple-touch-icon.png) are
rendered from the SVGs with render_png.py (headless Edge/Chromium).
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).parent
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "out")
OUT.mkdir(parents=True, exist_ok=True)

# ── Palette (mirrors vibeforge-ui/src/index.css) ─────────────────────────────
INK = "#140c0e"     # warm wine-black
CREAM = "#f7ede4"
MUTED = "#a8948e"
ROSE = "#ff4f6d"
AMBER = "#ffb05c"
WINE = "#b3174f"


# ── Font handling ────────────────────────────────────────────────────────────
class Face:
    def __init__(self, path: Path, axes: dict[str, float] | None = None):
        font = TTFont(path)
        if axes and "fvar" in font:
            font = instancer.instantiateVariableFont(font, axes)
        buf = io.BytesIO()
        font.save(buf)
        data = buf.getvalue()
        self.font = TTFont(io.BytesIO(data))
        self.glyphs = self.font.getGlyphSet()
        self.order = self.font.getGlyphOrder()
        self.upem = self.font["head"].unitsPerEm
        self.hbfont = hb.Font(hb.Face(data))

    def text_path(self, text: str, size: float, x: float, y: float, tracking_em: float = 0.0):
        """Return (svg path d, advance width in px) for text with baseline at (x, y)."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hbfont, buf, {"kern": True, "liga": True})
        scale = size / self.upem
        pen = SVGPathPen(self.glyphs)
        cursor = 0.0
        n = len(buf.glyph_infos)
        for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
            name = self.order[info.codepoint]
            gx = x + (cursor + pos.x_offset) * scale
            gy = y - pos.y_offset * scale
            self.glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, gx, gy)))
            cursor += pos.x_advance
            if i < n - 1:
                cursor += tracking_em * self.upem
        return pen.getCommands(), cursor * scale


DISPLAY = Face(HERE / "Fraunces.ttf", {"opsz": 144, "wght": 560, "SOFT": 100, "WONK": 0})
DISPLAY_IT = Face(HERE / "Fraunces-Italic.ttf", {"opsz": 144, "wght": 560, "SOFT": 100, "WONK": 1})
TAGLINE = Face(HERE / "Fraunces-Italic.ttf", {"opsz": 48, "wght": 380, "SOFT": 100, "WONK": 1})
MONO = Face(HERE / "DMMono-Medium.ttf")


# ── Mark: a guitar pick (its point is the V) with beamed eighth notes cut in ─
PICK_D = "M32 59 C27 54 9 37 8 23 C7 11 19 5.5 32 5.5 C45 5.5 57 11 56 23 C55 37 37 54 32 59Z"


def beamed_notes(x: float, y: float, s: float, fill: str, fill_opacity: float = 1) -> str:
    """Two beamed eighth notes drawn as geometry. (x, y) = left notehead centre, s = scale."""

    def head(cx: float, cy: float) -> str:
        return f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{5.4 * s:.2f}" ry="{3.9 * s:.2f}" transform="rotate(-24 {cx:.2f} {cy:.2f})"/>'

    dx, rise, stem_w, beam_h = 17 * s, 4 * s, 2.4 * s, 5 * s
    l_head, r_head = (x, y), (x + dx, y - rise)
    l_stem_x, r_stem_x = l_head[0] + 4.6 * s, r_head[0] + 4.6 * s
    top_l, top_r = l_head[1] - 22 * s, r_head[1] - 22 * s
    return (
        f'<g fill="{fill}" fill-opacity="{fill_opacity}">{head(*l_head)}{head(*r_head)}'
        f'<rect x="{l_stem_x - stem_w:.2f}" y="{top_l:.2f}" width="{stem_w:.2f}" height="{l_head[1] - top_l - s:.2f}"/>'
        f'<rect x="{r_stem_x - stem_w:.2f}" y="{top_r:.2f}" width="{stem_w:.2f}" height="{r_head[1] - top_r - s:.2f}"/>'
        f'<path d="M{l_stem_x - stem_w:.2f} {top_l:.2f} L{r_stem_x:.2f} {top_r:.2f} L{r_stem_x:.2f} {top_r + beam_h:.2f} '
        f'L{l_stem_x - stem_w:.2f} {top_l + beam_h:.2f}Z"/></g>'
    )


def pick_group(uid: str) -> str:
    """Pick artwork in a 64-unit box. uid keeps gradient ids unique per document."""
    defs = (
        f'<linearGradient id="pg-{uid}" x1="0.15" y1="0" x2="0.85" y2="1">'
        f'<stop offset="0" stop-color="{AMBER}"/><stop offset=".5" stop-color="{ROSE}"/>'
        f'<stop offset="1" stop-color="{WINE}"/></linearGradient>'
    )
    gloss = f'<path d="M15 16 Q22 9 33 8.5 L33 11.5 Q23 12.5 17 18Z" fill="{CREAM}" fill-opacity=".28"/>'
    return f'<defs>{defs}</defs><path d="{PICK_D}" fill="url(#pg-{uid})"/>{gloss}' + beamed_notes(23.5, 37, 0.92, INK)


def mark_group(size: float, x: float = 0, y: float = 0, *, uid: str, tile: str | None = INK, tile_rx: float = 15) -> str:
    s = size / 64
    tile_el = f'<rect width="64" height="64" rx="{tile_rx}" fill="{tile}"/>' if tile else ""
    return f'<g transform="translate({x} {y}) scale({s})">{tile_el}{pick_group(uid)}</g>'


def svg(w: float, h: float, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n'
    )


def write(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8", newline="\n")
    print("wrote", OUT / name)


# 1. Marks
write("logo-mark.svg", svg(64, 64, mark_group(64, uid="m"), "VibeForge"))
write("logo-pick.svg", svg(64, 64, mark_group(64, uid="p", tile=None), "VibeForge"))
# Full-bleed square for apple-touch-icon: iOS masks it and fills transparency with black.
write("app-icon-square.svg", svg(64, 64, mark_group(64, uid="a", tile_rx=0), "VibeForge"))


# 2. Wordmark
def wordmark(size: float, x: float, baseline: float, vibe_color: str, forge_color: str) -> tuple[str, float]:
    vibe_d, vibe_w = DISPLAY.text_path("Vibe", size, x, baseline, -0.02)
    forge_d, forge_w = DISPLAY_IT.text_path("Forge", size, x + vibe_w + size * 0.01, baseline, -0.01)
    body = f'<path fill="{vibe_color}" d="{vibe_d}"/><path fill="{forge_color}" d="{forge_d}"/>'
    return body, vibe_w + size * 0.01 + forge_w


def lockup(text_color: str, uid: str) -> str:
    h = 96
    mark = mark_group(h, 0, 0, uid=uid, tile=None)
    body, w = wordmark(70, h + 14, 70, text_color, ROSE if text_color == CREAM else WINE)
    return svg(round(h + 14 + w + 6), h, mark + body, "VibeForge")


write("logo-horizontal-light.svg", lockup(CREAM, "l"))  # for dark backgrounds
write("logo-horizontal-dark.svg", lockup(INK, "d"))     # for light backgrounds


# 3. Record artwork for banner / social preview
def record(cx: float, cy: float, r: float, uid: str) -> str:
    grooves = []
    rr, i = r * 0.40, 0
    while rr < r * 0.975:
        op = 0.10 if i % 3 else 0.22
        grooves.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" stroke-opacity="{op}"/>')
        rr += r * 0.018
        i += 1
    label_r = r * 0.34
    ns = label_r / 30  # beamed-notes scale on the label
    return (
        "<defs>"
        f'<radialGradient id="vinyl-{uid}" cx=".5" cy=".5" r=".5"><stop offset=".3" stop-color="#1d1214"/>'
        f'<stop offset="1" stop-color="#0b0607"/></radialGradient>'
        f'<linearGradient id="sheen-{uid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset=".25" stop-color="{CREAM}" stop-opacity="0"/><stop offset=".42" stop-color="{CREAM}" stop-opacity=".09"/>'
        f'<stop offset=".5" stop-color="{CREAM}" stop-opacity="0"/><stop offset=".72" stop-color="{AMBER}" stop-opacity=".07"/>'
        f'<stop offset=".8" stop-color="{AMBER}" stop-opacity="0"/></linearGradient>'
        f'<radialGradient id="label-{uid}" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="{AMBER}"/>'
        f'<stop offset=".55" stop-color="{ROSE}"/><stop offset="1" stop-color="{WINE}"/></radialGradient>'
        "</defs>"
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="url(#vinyl-{uid})"/>'
        f'<g fill="none" stroke="{CREAM}" stroke-width="1">{"".join(grooves)}</g>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="url(#sheen-{uid})"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{label_r:.1f}" fill="url(#label-{uid})"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{label_r * 0.86:.1f}" fill="none" stroke="{INK}" stroke-opacity=".25"/>'
        # Solid ink: translucent overlapping shapes would show darker seams. No spindle dot:
        # it would land between the stems like a stray mark.
        + beamed_notes(cx - 9.6 * ns, cy + 12 * ns, ns, INK)
    )


def hero(w: int, h: int, *, title_size: int, tag_size: int, mark_size: int, pad: int, chips: bool, rounded: bool) -> str:
    uid = f"{w}x{h}"
    defs = (
        "<defs>"
        f'<radialGradient id="glow-{uid}" cx=".78" cy=".5" r=".6"><stop offset="0" stop-color="{ROSE}" stop-opacity=".26"/>'
        f'<stop offset=".5" stop-color="{WINE}" stop-opacity=".10"/><stop offset="1" stop-color="{INK}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="ember-{uid}" cx=".08" cy="1" r=".55"><stop offset="0" stop-color="{AMBER}" stop-opacity=".14"/>'
        f'<stop offset="1" stop-color="{AMBER}" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="clip-{uid}"><rect width="{w}" height="{h}" rx="{int(h * 0.06) if rounded else 0}"/></clipPath>'
        "</defs>"
    )
    bg = (
        f'<rect width="{w}" height="{h}" fill="{INK}"/>'
        f'<rect width="{w}" height="{h}" fill="url(#glow-{uid})"/>'
        f'<rect width="{w}" height="{h}" fill="url(#ember-{uid})"/>'
    )
    rec_r = h * 0.62
    rec = record(w - rec_r * 0.5, h * 0.5, rec_r, uid)

    mark = mark_group(mark_size, pad, pad, uid=f"hero-{uid}", tile=None)
    eyebrow_d, _ = MONO.text_path(
        "AN AI THAT LISTENS TO HOW YOU FEEL", tag_size * 0.56, pad + mark_size + 16, pad + mark_size * 0.64, 0.12
    )
    ty = h * 0.60
    title, _ = wordmark(title_size, pad - title_size * 0.03, ty, CREAM, ROSE)
    tag_d, _ = TAGLINE.text_path("Fall in love with music again.", tag_size * 1.08, pad, ty + tag_size * 1.9, 0)
    parts = [
        defs,
        f'<g clip-path="url(#clip-{uid})">',
        bg,
        rec,
        mark,
        f'<path fill="{MUTED}" d="{eyebrow_d}"/>',
        title,
        f'<path fill="{CREAM}" fill-opacity=".82" d="{tag_d}"/>',
    ]
    if chips:
        cy = h - pad - tag_size * 0.3
        cx = pad
        for label in ["WRITE A FEELING", "SIDE A · SIDE B", "TEN TRACKS", "CRITIC-CHECKED"]:
            fs = tag_size * 0.5
            d, tw = MONO.text_path(label, fs, cx + fs * 1.2, cy + fs * 0.36, 0.1)
            cw, ch = tw + fs * 2.4, fs * 2.3
            parts.append(
                f'<rect x="{cx:.1f}" y="{cy - ch / 2:.1f}" width="{cw:.1f}" height="{ch:.1f}" rx="{ch / 2:.1f}" '
                f'fill="{INK}" fill-opacity=".55" stroke="{CREAM}" stroke-opacity=".2"/>'
            )
            parts.append(f'<path fill="{CREAM}" fill-opacity=".82" d="{d}"/>')
            cx += cw + fs * 0.9
    parts.append("</g>")
    return svg(w, h, "".join(parts), "VibeForge — Fall in love with music again.")


write("banner.svg", hero(1280, 400, title_size=128, tag_size=30, mark_size=40, pad=56, chips=False, rounded=True))
# GitHub crops social previews full-bleed; transparent rounded corners would show as wedges.
write("social-preview.svg", hero(1280, 640, title_size=144, tag_size=36, mark_size=52, pad=72, chips=True, rounded=False))
