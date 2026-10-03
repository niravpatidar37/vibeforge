"""Render VibeForge PNG exports from the generated SVGs with headless Edge/Chromium.

Run from this directory after build_brand.py:
  uv run --no-project --with pillow python render_png.py
Set BROWSER to a Chromium-family executable if Edge/Chrome isn't auto-detected.
Only local files are loaded; the HTML wrapper references the SVG by file:// URL.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BRAND = HERE.parent
UI_PUBLIC = BRAND.parents[1] / "vibeforge-ui" / "public"

# (source svg, output png, width, height, background: hex for an opaque export, None for transparent)
# Windows 11 rounds headless window corners, so the screenshot is taken on a padded
# canvas and cropped; opaque exports are then flattened to RGB.
PAD = 32
JOBS = [
    (BRAND / "social-preview.svg", BRAND / "social-preview.png", 1280, 640, "11110f"),
    (BRAND / "logo-mark.svg", BRAND / "logo-mark-512.png", 512, 512, None),
    (BRAND / "app-icon-square.svg", UI_PUBLIC / "apple-touch-icon.png", 180, 180, "d9f36a"),
]

CANDIDATES = [
    os.environ.get("BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "chromium",
    "google-chrome",
    "microsoft-edge",
]


def find_browser() -> str:
    for c in CANDIDATES:
        if c and (Path(c).is_file() or shutil.which(c)):
            return c
    sys.exit("No Chromium-family browser found; set BROWSER=/path/to/browser")


def render(browser: str, src: Path, out: Path, w: int, h: int, bg: str | None) -> None:
    page_bg = f"#{bg}" if bg else "transparent"
    html = (
        "<!doctype html><html><head><style>"
        f"html,body{{margin:0;padding:0;background:{page_bg};overflow:hidden}}"
        f"img{{display:block;margin:{PAD}px;width:{w}px;height:{h}px}}"
        f'</style></head><body><img src="{src.as_uri()}"></body></html>'
    )
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        shot = Path(tmp) / "shot.png"
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--disable-extensions",
            f"--user-data-dir={Path(tmp) / 'profile'}",
            f"--window-size={w + 2 * PAD},{h + 2 * PAD}",
            f"--screenshot={shot}",
        ]
        cmd.append(f"--default-background-color={bg + 'ff' if bg else '00000000'}")
        cmd.append(page.as_uri())
        subprocess.run(cmd, check=True, timeout=60, capture_output=True)
        # msedge.exe can hand off to a child process and return before the file exists.
        deadline = time.monotonic() + 60
        while not (shot.is_file() and shot.stat().st_size > 0):
            if time.monotonic() > deadline:
                sys.exit(f"screenshot never appeared for {src.name}")
            time.sleep(0.25)
        time.sleep(0.5)  # let the writer finish flushing
        with Image.open(shot) as im:
            img = im.convert("RGBA").crop((PAD, PAD, PAD + w, PAD + h))
        if bg:
            img = img.convert("RGB")
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, optimize=True)
    print("rendered", out)


if __name__ == "__main__":
    b = find_browser()
    for job in JOBS:
        render(b, *job)
