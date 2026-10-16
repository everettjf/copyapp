#!/usr/bin/env python3
"""Generate iCTRL app icon with proper font rendering."""

from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
CENTER = SIZE // 2

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Background gradient
for y in range(SIZE):
    for x in range(SIZE):
        t = (x + y) / (2 * SIZE)
        r = int(30 * (1 - t) + 13 * t)
        g = int(34 * (1 - t) + 15 * t)
        b = int(53 * (1 - t) + 26 * t)
        img.putpixel((x, y), (r, g, b, 255))

# Load fonts
font_i = ImageFont.truetype("/System/Library/Fonts/SF-Pro-Rounded-Bold.otf", 300)
font_ctrl = ImageFont.truetype("/System/Library/Fonts/SF-Pro-Rounded-Bold.otf", 270)

# Measure "i" and "CTRL" actual rendered bounds
i_bbox = font_i.getbbox("i")
ctrl_bbox = font_ctrl.getbbox("CTRL")

i_w = i_bbox[2] - i_bbox[0]
i_h = i_bbox[3] - i_bbox[1]
ctrl_w = ctrl_bbox[2] - ctrl_bbox[0]
ctrl_h = ctrl_bbox[3] - ctrl_bbox[1]

# Total width and max height for centering
spacing = 8
total_w = i_w + spacing + ctrl_w
max_h = max(i_h, ctrl_h)

# True center position
text_left = (SIZE - total_w) // 2
text_top_center = (SIZE - max_h) // 2

# "i" position — align baseline with CTRL
i_x = text_left - i_bbox[0]
i_y = text_top_center - i_bbox[1]

# "CTRL" position — align vertically by baseline
ctrl_x = text_left + i_w + spacing - ctrl_bbox[0]
# Align baselines: "i" bottom = i_y + i_bbox[3], "CTRL" bottom = ctrl_y + ctrl_bbox[3]
ctrl_y = (i_y + i_bbox[3]) - ctrl_bbox[3]

# Orbit center = visual center of the text block
orbit_cx = text_left + total_w // 2
orbit_cy = text_top_center + max_h // 2

def draw_arc(cx, cy, radius, start_angle, end_angle, color, width, alpha=255):
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    odraw.arc(bbox, start_angle, end_angle, fill=color + (alpha,), width=width)
    img.alpha_composite(overlay)

# Orbits centered on text
draw_arc(orbit_cx, orbit_cy, 270, -160, 200, (0, 153, 255), 7, 90)
draw_arc(orbit_cx, orbit_cy, 330, -150, 210, (0, 120, 230), 5, 45)
draw_arc(orbit_cx, orbit_cy, 390, -140, 220, (80, 60, 200), 3, 22)

# Draw "i" in cyan
i_overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(i_overlay).text((i_x, i_y), "i", font=font_i, fill=(0, 200, 255, 255))
img.alpha_composite(i_overlay)

# Draw "CTRL" in white
ctrl_overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(ctrl_overlay).text((ctrl_x, ctrl_y), "CTRL", font=font_ctrl, fill=(255, 255, 255, 255))
img.alpha_composite(ctrl_overlay)

# "i" dot glow — find rendered dot position
i_dot_cx = i_x + i_bbox[0] + i_w // 2
i_dot_cy = i_y + i_bbox[1] + 20  # top of "i" glyph

for r in range(45, 0, -1):
    alpha = int(60 * (1 - r / 45))
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [i_dot_cx - r, i_dot_cy - r, i_dot_cx + r, i_dot_cy + r],
        fill=(0, 229, 255, alpha)
    )
    img.alpha_composite(glow)

# Particles
for px, py, pr, pc in [(820, 340, 5, (0, 204, 255, 100)), (190, 690, 4, (123, 66, 246, 90)), (765, 725, 4, (0, 136, 255, 65))]:
    p = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(p).ellipse([px - pr, py - pr, px + pr, py + pr], fill=pc)
    img.alpha_composite(p)

output = "iCTRLApp/Assets.xcassets/AppIcon.appiconset/icon_1024x1024.png"
img.save(output, "PNG")
print(f"✅ Icon saved to {output}")
