"""
Convert an image (e.g. a portrait photo) into ASCII art for the profile card.

Usage:
    pip install pillow opencv-python-headless
    python ascii_art.py me.png                # writes ascii_dark.txt + ascii_light.txt
    python ascii_art.py me.png --cols 40      # PNG with transparent background works best

Tips:
  * Remove the background first (e.g. `pip install rembg` then
    `rembg i photo.jpg me.png`) - transparent pixels become blank space.
  * Crop tightly to head + shoulders.
  * Two versions are written: ascii_dark.txt (bright pixels = dense chars, for the
    dark card) and ascii_light.txt (inverted, for the light card).
"""
import argparse
import numpy as np
import cv2
from PIL import Image

RAMP = " .:-=+*#%@"  # sparse -> dense; a short ramp reads more clearly at this size


def convert(path, cols=44, invert=False, char_aspect=0.5, clip=3.0):
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    rows = max(1, int(h / w * cols * char_aspect))
    gray = np.array(img.convert("L"))
    alpha = np.array(img.getchannel("A"))
    # local contrast so features (eyes, glasses, beard) survive downscaling
    gray = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(gray)
    if invert:
        gray = 255 - gray
    g = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA).astype(float)
    a = cv2.resize(alpha, (cols, rows), interpolation=cv2.INTER_AREA)
    fg = g[a > 128]
    if fg.size:  # stretch foreground to full range
        lo, hi = np.percentile(fg, 2), np.percentile(fg, 98)
        g = np.clip((g - lo) / max(1, hi - lo) * 255, 0, 255)
    lines = []
    for r in range(rows):
        line = "".join(" " if a[r, c] <= 128 else RAMP[1 + int(g[r, c]) * (len(RAMP) - 2) // 255]
                       for c in range(cols))
        lines.append(line.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--cols", type=int, default=44)
    a = ap.parse_args()
    for name, inv in (("ascii_dark.txt", False), ("ascii_light.txt", True)):
        art = convert(a.image, a.cols, inv)
        with open(name, "w", encoding="utf-8") as f:
            f.write(art + "\n")
        print(f"--- {name} ---\n{art}\n")
