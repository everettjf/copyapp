"""Render the Copy APP X announcement cards from public, selected evidence.

Run with the bundled Codex Python (Pillow required):
python docs/assets/social/generate_cards.py

Original device screenshots are composited without altering their pixels.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
W, H = 1600, 900

INK = "#202820"
MUTED = "#536357"
CREAM = "#F8FCF8"
WHITE = "#FFFFFF"
PANEL = "#FFFFFF"
PURPLE = "#6949C6"
LAVENDER = "#EAE3F8"
ORANGE = "#DE663F"
PEACH = "#FFE5D7"
GREEN = "#087D44"
MINT = "#DBF6E5"
PINK = "#FCE2EC"
YELLOW = "#FFE078"
PLUM = "#EDF5EE"

REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"


def font(size, bold=False, mono=False):
    return ImageFont.truetype(MONO if mono else BOLD if bold else REG, size)


def text(draw, xy, value, size, fill=INK, bold=False, mono=False):
    draw.text(xy, value, font=font(size, bold, mono), fill=fill)


def box(draw, xy, fill, radius=32, outline=None, width=2):
    draw.rounded_rectangle(xy, radius, fill=fill, outline=outline, width=width)


def base(number, label, title, subtitle):
    im = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 58):
        d.line((x, 0, x, H), fill="#E8F0E9", width=1)
    for y in range(0, H, 58):
        d.line((0, y, W, y), fill="#E8F0E9", width=1)
    d.ellipse((1320, -190, 1800, 290), fill=LAVENDER)
    d.ellipse((-170, 740, 180, 1090), fill=PEACH)
    box(d, (66, 48, 286, 94), "#00D861", 22)
    text(d, (88, 58), "COPY APP", 23, INK, True)
    text(d, (1336, 57), f"{number} / 04", 25, GREEN, True)
    text(d, (70, 128), label.upper(), 20, GREEN, True)
    text(d, (70, 166), title, 62, INK, True)
    text(d, (72, 249), subtitle, 25, MUTED)
    return im, d


def save(im, name):
    im.save(OUT / name, optimize=True)


def card_one():
    im, d = base("01", "System map", "A real phone. A traceable rebuild.",
                 "The Mac coordinates analysis; the selected jailbroken iPhone supplies the evidence.")
    box(d, (70, 324, 829, 746), MINT, 36)
    box(d, (945, 324, 1530, 746), PEACH, 36)
    text(d, (108, 355), "MAC", 24, GREEN, True)
    text(d, (108, 393), "Control + analysis", 38, INK, True)
    mac_items = [("Coding agent", "Interpret and implement"), ("Copy APP CLI", "Pin device + verify cases"),
                 ("Local evidence", "Hashes, sources, report"), ("Xcode", "Build an independent app")]
    for i, (head, sub) in enumerate(mac_items):
        x = 109 + (i % 2) * 355
        y = 463 + (i // 2) * 119
        box(d, (x, y, x + 324, y + 96), PANEL, 19)
        text(d, (x + 18, y + 15), head, 23, GREEN, True)
        text(d, (x + 18, y + 53), sub, 17, MUTED)
    d.line((849, 502, 918, 502), fill=ORANGE, width=8)
    d.polygon([(919, 502), (898, 488), (898, 516)], fill=ORANGE)
    d.line((919, 609, 850, 609), fill=GREEN, width=8)
    d.polygon([(848, 609), (870, 594), (870, 624)], fill=GREEN)
    box(d, (856, 537, 916, 574), YELLOW, 17)
    text(d, (862, 544), "USB", 20, INK, True)
    text(d, (985, 355), "JAILBROKEN IPHONE", 24, ORANGE, True)
    text(d, (985, 393), "Source + test device", 38, INK, True)
    for i, (head, sub, color) in enumerate([
        ("OpenSSH", "Package + bounded sandbox", GREEN),
        ("iOS MCP / iCTRL", "UI tree + screenshots", PURPLE),
        ("Frida", "Targeted runtime traces", ORANGE),
    ]):
        y = 469 + i * 80
        box(d, (985, y, 1488, y + 67), PANEL, 18)
        d.ellipse((1003, y + 22, 1025, y + 44), fill=color)
        text(d, (1044, y + 10), head, 22, INK, True)
        text(d, (1044, y + 39), sub, 16, MUTED)
    text(d, (74, 791), "ANALYZE", 22, GREEN, True)
    text(d, (293, 791), "→", 28, ORANGE, True)
    text(d, (350, 791), "SET SCOPE", 22, GREEN, True)
    text(d, (594, 791), "→", 28, ORANGE, True)
    text(d, (651, 791), "REBUILD", 22, GREEN, True)
    text(d, (870, 791), "→", 28, ORANGE, True)
    text(d, (927, 791), "COMPARE", 22, GREEN, True)
    text(d, (73, 841), "Exact device · exact app build · measured selected flows", 20, MUTED)
    save(im, "01-system-map.png")


def card_two():
    im, d = base("02", "Evidence", "Analysis, with receipts.",
                 "A cited report joins what was observed, inferred, and still unknown.")
    types = [
        ("PACKAGE", "Binary + imports", LAVENDER, PURPLE),
        ("SANDBOX", "Files + schemas", MINT, GREEN),
        ("UI", "Screens + hierarchy", PEACH, ORANGE),
        ("RUNTIME", "Bounded Frida traces", PINK, "#B63469"),
    ]
    for i, (label, detail, bg, fg) in enumerate(types):
        y = 329 + i * 114
        box(d, (70, y, 565, y + 91), bg, 23)
        text(d, (100, y + 13), label, 23, fg, True)
        text(d, (100, y + 47), detail, 22, INK)
    box(d, (620, 329, 1530, 799), PLUM, 31)
    box(d, (649, 352, 1501, 409), "#D9EADC", 17)
    d.ellipse((674, 373, 690, 389), fill=ORANGE)
    d.ellipse((702, 373, 718, 389), fill=YELLOW)
    d.ellipse((730, 373, 746, 389), fill="#00D861")
    text(d, (780, 365), "Hopper · selected iOS 17 Calculator function", 21, INK, True)
    code = [
        ("// CalculatorModel", "#657B69"),
        ("buttonPressed(arg2)", INK),
        ("  var_18 = retain(self);", "#3F5043"),
        ("  sub_10000fb4c(arg2);", PURPLE),
        ("  r0 = var_18;", "#3F5043"),
    ]
    for i, (line, fill) in enumerate(code):
        text(d, (675, 448 + i * 50), line, 26, fill, mono=True)
    d.line((674, 719, 1476, 719), fill="#B4C9B8", width=2)
    text(d, (676, 738), "Recorded excerpt · not original source · not the full algorithm", 18, MUTED)
    text(d, (72, 825), "Function interpretation remains linked to its exact binary and evidence case.", 19, MUTED)
    save(im, "02-evidence.png")


def screenshot_card(im, d, path, x, label, color):
    box(d, (x, 315, x + 550, 821), color, 28)
    text(d, (x + 27, 337), label, 27, INK, True)
    shot = Image.open(path).convert("RGB")
    # Preserve the captured screenshot pixels; only resize for this display card.
    shot = shot.resize((204, 442), Image.Resampling.LANCZOS)
    box(d, (x + 165, 370, x + 385, 826), "#3A413B", 25)
    im.paste(shot, (x + 173, 377))


def card_three():
    im, d = base("03", "Same-device comparison", "Same flow. Same device.",
                 "iPhone 14 · iOS 17.3.1 · selected Calculator flow: 7 + 8 = 15")
    screenshot_card(im, d, ROOT / "assets/calculator-original.jpg", 70, "ORIGINAL", MINT)
    screenshot_card(im, d, ROOT / "assets/calculator-rebuilt.jpg", 980, "INDEPENDENT REBUILD", PINK)
    box(d, (663, 473, 937, 634), YELLOW, 34)
    text(d, (707, 497), "7 + 8", 42, INK, True)
    text(d, (733, 554), "= 15", 43, PURPLE, True)
    text(d, (670, 720), "Paired observation", 22, GREEN, True)
    text(d, (670, 753), "Differences stay", 19, MUTED)
    text(d, (670, 779), "visible in the report.", 19, MUTED)
    save(im, "03-calculator-comparison.png")


def card_four():
    im, d = base("04", "Deliverables", "A report. A runnable app. Clear limits.",
                 "The target adapts to the app's complexity; every verified flow stays explicit.")
    box(d, (70, 334, 757, 725), MINT, 34)
    box(d, (799, 334, 1530, 725), PEACH, 34)
    text(d, (106, 370), "01 / ANALYZE", 25, GREEN, True)
    text(d, (106, 422), "Deep, cited report", 41, INK, True)
    for i, item in enumerate(["Package and sandbox", "UI structure and flows", "Selected native functions", "Unknowns called out"]):
        y = 493 + i * 48
        d.ellipse((108, y + 7, 123, y + 22), fill=GREEN)
        text(d, (144, y), item, 24, INK)
    text(d, (835, 370), "02 / REBUILD", 25, ORANGE, True)
    text(d, (835, 422), "Independent iOS app", 41, INK, True)
    for i, item in enumerate(["Implement selected flows", "Install on the same device", "Compare behavior + visuals", "Report verified coverage + gaps"]):
        y = 493 + i * 48
        d.ellipse((837, y + 7, 852, y + 22), fill=ORANGE)
        text(d, (873, y), item, 23, INK)
    box(d, (70, 758, 1530, 844), MINT, 25)
    text(d, (98, 781), "TESTED PATHS", 21, GREEN, True)
    text(d, (296, 778), "iOS 16  ·  iOS 17  ·  iOS 26", 29, INK, True)
    text(d, (920, 786), "Named devices, not a universal guarantee", 19, MUTED)
    save(im, "04-deliverables.png")


if __name__ == "__main__":
    card_one()
    card_two()
    card_three()
    card_four()
    preview = Image.new("RGB", (1600, 900), CREAM)
    for i, path in enumerate(sorted(OUT.glob("0[1-4]-*.png"))):
        tile = Image.open(path).resize((800, 450), Image.Resampling.LANCZOS)
        preview.paste(tile, ((i % 2) * 800, (i // 2) * 450))
    preview.save(OUT / "preview.png", optimize=True)
