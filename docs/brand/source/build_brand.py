"""Generate VibeForge brand assets as font-independent SVG (text outlined to paths).

Fonts (SIL OFL 1.1) must sit next to this script; they are not committed:
  curl -sSLo SpaceGrotesk.ttf "https://github.com/google/fonts/raw/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf"
  curl -sSLo DMMono-Medium.ttf "https://github.com/google/fonts/raw/main/ofl/dmmono/DMMono-Medium.ttf"
Run:
  uv run --with fonttools --with uharfbuzz python build_brand.py ../
PNG exports (social-preview.png, logo-mark-512.png, apple-touch-icon.png) are
rendered from the SVGs with render_png.py (headless Edge/Chromium).
"""

from __future__ import annotations

import io
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

INK = "#11110f"
INK_2 = "#1b1b18"
CREAM = "#f4f1e9"
LIME = "#d9f36a"
MUTED = "#92928a"
CORAL = "#ff7158"


# ── Font handling ────────────────────────────────────────────────────────────
class Face:
    def __init__(self, path: Path, wght: float | None = None):
        font = TTFont(path)
        if wght is not None and "fvar" in font:
            font = instancer.instantiateVariableFont(font, {"wght": wght})
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
            tpen = TransformPen(pen, (scale, 0, 0, -scale, gx, gy))
            self.glyphs[name].draw(tpen)
            cursor += pos.x_advance
            if i < n - 1:
                cursor += tracking_em * self.upem
        return pen.getCommands(), cursor * scale


GROTESK_BOLD = Face(HERE / "SpaceGrotesk.ttf", 700)
GROTESK_MED = Face(HERE / "SpaceGrotesk.ttf", 500)
MONO = Face(HERE / "DMMono-Medium.ttf")


# ── Mark: equalizer bars tracing a "V", with a forge spark in the notch ──────
def mark_group(
    size: float, x: float = 0, y: float = 0, tile: str = LIME, ink: str = INK, tile_rx: float = 16
) -> str:
    s = size / 64
    bar_w, gap = 6.0, 4.5
    tops = [16, 26, 35, 26, 16]
    base = 49
    x0 = (64 - (len(tops) * bar_w + (len(tops) - 1) * gap)) / 2
    bars = "".join(
        f'<rect x="{x0 + i * (bar_w + gap):.2f}" y="{t}" width="{bar_w}" height="{base - t}" rx="{bar_w / 2}"/>'
        for i, t in enumerate(tops)
    )
    # Four-point spark centred in the V notch.
    cx, cy, r, w = 32, 23.5, 7.5, 1.6
    spark = (
        f'<path d="M{cx} {cy - r} Q{cx + w} {cy - w} {cx + r} {cy} Q{cx + w} {cy + w} {cx} {cy + r} '
        f'Q{cx - w} {cy + w} {cx - r} {cy} Q{cx - w} {cy - w} {cx} {cy - r}Z"/>'
    )
    tile_el = f'<rect width="64" height="64" rx="{tile_rx}" fill="{tile}"/>' if tile else ""
    return (
        f'<g transform="translate({x} {y}) scale({s})">{tile_el}'
        f'<g fill="{ink}">{bars}{spark}</g></g>'
    )


def svg(w: float, h: float, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n'
    )


def write(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8", newline="\n")
    print("wrote", OUT / name)


# 1. Mark (app icon / favicon)
write("logo-mark.svg", svg(64, 64, mark_group(64), "VibeForge"))
# Full-bleed square for apple-touch-icon: iOS applies its own mask and fills
# transparent pixels with black, so this one must be opaque edge to edge.
write("app-icon-square.svg", svg(64, 64, mark_group(64, tile_rx=0), "VibeForge"))


# 2. Horizontal lockups (dark text for light backgrounds, light text for dark backgrounds)
def lockup(text_color: str) -> str:
    h = 96
    mark = mark_group(h, 0, 0)
    fs = 64
    baseline = 70
    vibe_d, vibe_w = GROTESK_BOLD.text_path("Vibe", fs, h + 24, baseline, -0.04)
    forge_d, forge_w = GROTESK_BOLD.text_path("Forge", fs, h + 24 + vibe_w + fs * -0.04, baseline, -0.04)
    total_w = h + 24 + vibe_w + fs * -0.04 + forge_w + 4
    forge_color = LIME if text_color == CREAM else INK
    body = (
        f"{mark}<path fill=\"{text_color}\" d=\"{vibe_d}\"/>"
        f"<path fill=\"{forge_color}\" d=\"{forge_d}\"/>"
    )
    return svg(round(total_w), h, body, "VibeForge")


write("logo-horizontal-light.svg", lockup(CREAM))  # for dark backgrounds
write("logo-horizontal-dark.svg", lockup(INK))     # for light backgrounds


# 3. README banner + social preview (self-contained dark artwork)
def eq_strip(x: float, y: float, w: float, h: float, n: int, color: str, opacity: float) -> str:
    """Decorative waveform strip; deterministic heights."""
    import math

    bw = w / n * 0.55
    step = w / n
    out = []
    for i in range(n):
        t = i / (n - 1)
        amp = 0.18 + 0.82 * abs(math.sin(t * math.pi * 3.1 + 0.6)) * (0.55 + 0.45 * math.sin(t * math.pi))
        bh = max(bw, h * amp)
        out.append(
            f'<rect x="{x + i * step:.1f}" y="{y + (h - bh) / 2:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="{bw / 2:.1f}"/>'
        )
    return f'<g fill="{color}" opacity="{opacity}">{"".join(out)}</g>'


def hero(
    w: int, h: int, *, title_size: int, tag_size: int, mark_size: int, pad: int, chips: bool, rounded: bool
) -> str:
    defs = (
        "<defs>"
        f'<radialGradient id="glow" cx="0.82" cy="0.3" r="0.65"><stop offset="0" stop-color="{LIME}" stop-opacity=".22"/>'
        f'<stop offset="1" stop-color="{LIME}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="{INK}" stop-opacity="1"/>'
        f'<stop offset=".55" stop-color="{INK}" stop-opacity=".2"/><stop offset="1" stop-color="{INK}" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="clip"><rect width="{w}" height="{h}" rx="{int(h * 0.06) if rounded else 0}"/></clipPath>'
        "</defs>"
    )
    bg = f'<rect width="{w}" height="{h}" fill="{INK}"/><rect width="{w}" height="{h}" fill="url(#glow)"/>'

    mark = mark_group(mark_size, pad, pad)
    eyebrow_d, _ = MONO.text_path("AI MOOD-TO-PLAYLIST AGENT", tag_size * 0.62, pad + mark_size + 18, pad + mark_size * 0.62, 0.09)
    ty = h * 0.60
    vibe_d, vibe_w = GROTESK_MED.text_path("Vibe", title_size, pad - title_size * 0.04, ty, -0.06)
    forge_d, forge_w = GROTESK_MED.text_path("Forge", title_size, pad - title_size * 0.04 + vibe_w - title_size * 0.06, ty, -0.06)
    tag_d, _ = GROTESK_MED.text_path("Your mood. Forged into sound.", tag_size, pad, ty + tag_size * 2.0, -0.02)
    title_end = pad - title_size * 0.04 + vibe_w - title_size * 0.06 + forge_w
    wx = title_end + title_size * 0.35
    ww = w - wx - pad * 0.6
    n = max(12, int(ww / 13))
    wave = eq_strip(wx, h * 0.16, ww, h * 0.68, n, LIME, 0.9)
    parts = [
        defs,
        '<g clip-path="url(#clip)">',
        bg,
        wave,
        mark,
        f'<path fill="{MUTED}" d="{eyebrow_d}"/>',
        f'<path fill="{CREAM}" d="{vibe_d}"/>',
        f'<path fill="{LIME}" d="{forge_d}"/>',
        f'<path fill="{CREAM}" opacity=".78" d="{tag_d}"/>',
    ]
    if chips:
        cy = h - pad - tag_size * 0.4
        cx = pad
        for label in ["FAST", "DEEP", "AGENTIC · LANGGRAPH", "CRITIC LOOP"]:
            fs = tag_size * 0.58
            d, tw = MONO.text_path(label, fs, cx + fs * 1.1, cy + fs * 0.36, 0.08)
            cw = tw + fs * 2.2
            ch = fs * 2.2
            parts.append(
                f'<rect x="{cx}" y="{cy - ch / 2}" width="{cw:.1f}" height="{ch:.1f}" rx="{ch / 2:.1f}" '
                f'fill="none" stroke="{CREAM}" stroke-opacity=".22"/>'
            )
            parts.append(f'<path fill="{CREAM}" opacity=".8" d="{d}"/>')
            cx += cw + fs * 0.9
    parts.append("</g>")
    return svg(w, h, "".join(parts), "VibeForge — Your mood. Forged into sound.")


write("banner.svg", hero(1280, 400, title_size=120, tag_size=28, mark_size=44, pad=56, chips=False, rounded=True))
# GitHub crops social previews full-bleed; transparent rounded corners would show as wedges.
write("social-preview.svg", hero(1280, 640, title_size=150, tag_size=34, mark_size=56, pad=72, chips=True, rounded=False))
