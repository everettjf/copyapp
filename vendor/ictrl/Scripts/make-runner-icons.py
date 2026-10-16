#!/usr/bin/env python3
"""Generate the XCTest Runner's home-screen icons from the app icon.

The Runner is built from Xcode's XCTRunner template, which declares no icon:
its Info.plist has no CFBundleIcons and it ships no Assets.car, so iOS shows
the placeholder. `make ipa` copies these files into the Runner and declares
them through CFBundleIconFiles (plain PNG lookup, no CFBundleIconName: a name
makes iOS look only in Assets.car).

Output is standard PNG (not Xcode's CgBI-crushed variant) without an alpha
channel: iOS composites a transparent icon on black. Regenerate after the app
icon changes:

    python3 Scripts/make-runner-icons.py
"""
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "iCTRLApp/Assets.xcassets/AppIcon.appiconset/icon_1024x1024.png"
OUT = REPO / "Config/RunnerIcon"

# (base name, point size, scale, suffix): file is <base>[@<scale>x]<suffix>.png
ICONS = [
    # iPhone: notification, settings, spotlight, home screen
    ("AppIcon20x20", 20, 2, ""), ("AppIcon20x20", 20, 3, ""),
    ("AppIcon29x29", 29, 2, ""), ("AppIcon29x29", 29, 3, ""),
    ("AppIcon40x40", 40, 2, ""), ("AppIcon40x40", 40, 3, ""),
    ("AppIcon60x60", 60, 2, ""), ("AppIcon60x60", 60, 3, ""),
    # iPad
    ("AppIcon20x20", 20, 1, "~ipad"), ("AppIcon20x20", 20, 2, "~ipad"),
    ("AppIcon29x29", 29, 1, "~ipad"), ("AppIcon29x29", 29, 2, "~ipad"),
    ("AppIcon40x40", 40, 1, "~ipad"), ("AppIcon40x40", 40, 2, "~ipad"),
    ("AppIcon76x76", 76, 1, "~ipad"), ("AppIcon76x76", 76, 2, "~ipad"),
    ("AppIcon83.5x83.5", 83.5, 2, "~ipad"),
]


def main() -> None:
    src = Image.open(SOURCE).convert("RGBA")
    # Flatten onto the icon's own corner colour rather than black, in case the
    # source ever gains transparency.
    base = Image.new("RGB", src.size, src.getpixel((0, 0))[:3])
    base.paste(src, mask=src.split()[3])
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    for name, points, scale, suffix in ICONS:
        px = round(points * scale)
        scale_tag = f"@{scale}x" if scale > 1 else ""
        path = OUT / f"{name}{scale_tag}{suffix}.png"
        base.resize((px, px), Image.LANCZOS).save(path, "PNG", optimize=True)
        print(f"🎨 {path.relative_to(REPO)} {px}x{px}")


if __name__ == "__main__":
    main()
