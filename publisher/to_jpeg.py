#!/usr/bin/env python3
"""Convert rendered 1080x1350 PNG slides to JPEG (Instagram API only accepts JPEG).
usage: python3 to_jpeg.py <png_dir> <jpg_dir>
"""
import sys, os
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
for f in sorted(os.listdir(src)):
    if f.lower().endswith(".png"):
        im = Image.open(os.path.join(src, f)).convert("RGB")
        assert im.size == (1080, 1350), f"{f}: unexpected size {im.size}"
        im.save(os.path.join(dst, f[:-4] + ".jpg"), "JPEG", quality=92, optimize=True)
        print("wrote", f[:-4] + ".jpg")
