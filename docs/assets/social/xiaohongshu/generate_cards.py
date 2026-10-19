"""Render six Chinese, 3:4 Copy APP cards for a Xiaohongshu image post.

Run from the repository root with `.venv/bin/python`.
The two Calculator captures are only resized to fit the phone frames.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "publish"
OUT.mkdir(exist_ok=True)
W, H = 1242, 1656

BG = "#F8FCF8"
INK = "#1E3025"
MUTED = "#52675A"
GREEN = "#087D44"
LIME = "#00D861"
MINT = "#DCF5E5"
PEACH = "#FFE6D9"
ORANGE = "#D9613D"
LAVENDER = "#EAE3F8"
PURPLE = "#6949C6"
PINK = "#FCE4EE"
WHITE = "#FFFFFF"
GRID = "#E9F1EA"
YELLOW = "#FFE177"

ZH = "/System/Library/Fonts/STHeiti Medium.ttc"
ZH_LIGHT = "/System/Library/Fonts/STHeiti Light.ttc"
LATIN = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"


def f(size, light=False, latin=False, mono=False):
    return ImageFont.truetype(
        MONO if mono else LATIN if latin else ZH_LIGHT if light else ZH, size
    )


def t(d, xy, value, size=36, color=INK, light=False, latin=False, mono=False):
    d.text(xy, value, font=f(size, light, latin, mono), fill=color)


def center(d, y, value, size=36, color=INK, light=False):
    face = f(size, light)
    width = d.textbbox((0, 0), value, font=face)[2]
    d.text(((W - width) / 2, y), value, font=face, fill=color)


def rr(d, xy, color, radius=30, outline=None, width=2):
    d.rounded_rectangle(xy, radius, fill=color, outline=outline, width=width)


def dot(d, x, y, color=GREEN, r=8):
    d.ellipse((x-r, y-r, x+r, y+r), fill=color)


def pill(d, xy, value, bg=MINT, fg=GREEN, size=27):
    rr(d, xy, bg, 24)
    x1, y1, x2, y2 = xy
    face = f(size)
    width = d.textbbox((0, 0), value, font=face)[2]
    d.text((x1+(x2-x1-width)/2, y1+(y2-y1-size)/2-3), value, font=face, fill=fg)


def base(n, kicker, lines, subtitle):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 54):
        d.line((x, 0, x, H), fill=GRID, width=1)
    for y in range(0, H, 54):
        d.line((0, y, W, y), fill=GRID, width=1)
    d.ellipse((940, -210, 1410, 260), fill=LAVENDER)
    d.ellipse((-160, 1420, 200, 1780), fill=PEACH)
    pill(d, (68, 56, 316, 116), "COPY APP", LIME, INK, 30)
    t(d, (1030, 68), f"{n} / 06", 30, GREEN, latin=True)
    t(d, (70, 173), kicker, 30, GREEN)
    for i, line in enumerate(lines):
        t(d, (69, 228+i*111), line, 83, INK)
    t(d, (72, 255+len(lines)*111), subtitle, 35, MUTED, light=True)
    d.line((70, 1565, 1172, 1565), fill="#C8DBCD", width=2)
    t(d, (72, 1590), "开源项目 · 选定流程实测 · 差异如实记录", 24, MUTED)
    return im, d


def save(im, name):
    im.save(OUT / name, optimize=True)


def cover():
    im, d = base("01", "一个开源实验", ["把越狱 iPhone", "接给 Coding Agent"],
                 "分析 App，再做可运行复刻")
    rr(d, (86, 645, 818, 1200), WHITE, 42, "#CEE2D2", 3)
    rr(d, (116, 678, 788, 1100), "#E3F8E9", 27)
    rr(d, (148, 713, 462, 767), LIME, 23)
    t(d, (173, 723), "COPY APP", 28, INK, latin=True)
    t(d, (148, 818), "coding agent  →  证据", 38, GREEN)
    t(d, (148, 890), "报告  →  新 iOS 工程", 38, INK)
    t(d, (148, 962), "同机对照  →  差异清单", 38, INK)
    rr(d, (282, 1200, 622, 1230), "#73877A", 15)
    rr(d, (231, 1230, 675, 1250), "#9DB0A1", 10)
    rr(d, (817, 727, 1148, 1278), INK, 51)
    rr(d, (834, 756, 1131, 1237), "#FFF8F1", 31)
    pill(d, (878, 790, 1089, 842), "越狱 iPhone", PEACH, ORANGE, 27)
    rr(d, (891, 903, 1073, 1085), MINT, 36)
    t(d, (929, 944), "APP", 45, GREEN, latin=True)
    d.line((938, 1170, 1027, 1170), fill="#8CA199", width=7)
    d.line((790, 957, 817, 957), fill=ORANGE, width=8)
    d.polygon([(821, 957), (802, 944), (802, 970)], fill=ORANGE)
    for x, label, bg, fg in [(70, "证据分析", MINT, GREEN),
                             (447, "独立复刻", PEACH, ORANGE),
                             (824, "同机对照", LAVENDER, PURPLE)]:
        pill(d, (x, 1370, x+348, 1446), label, bg, fg, 37)
    save(im, "01-cover.png")


def architecture():
    im, d = base("02", "工作原理", ["真实手机 + Mac", "各做擅长的事"],
                 "设备采集事实，Agent 整理并验证")
    rr(d, (70, 620, 591, 1260), MINT, 39)
    rr(d, (651, 620, 1172, 1260), PEACH, 39)
    pill(d, (103, 661, 299, 716), "MAC", WHITE, GREEN, 31)
    pill(d, (687, 661, 1084, 716), "越狱 iPhone", WHITE, ORANGE, 31)
    t(d, (103, 760), "编排 + 分析", 47, INK)
    t(d, (687, 760), "来源 + 测试", 47, INK)
    for i, (left, right) in enumerate([
        ("Coding Agent", "已安装 App"),
        ("Copy APP CLI", "沙盒与文件"),
        ("证据报告", "UI 截图与层级"),
        ("Xcode 工程", "选定运行时跟踪"),
    ]):
        y = 853 + 91*i
        rr(d, (102, y, 559, y+69), WHITE, 17)
        rr(d, (684, y, 1141, y+69), WHITE, 17)
        dot(d, 130, y+35, GREEN, 7)
        dot(d, 712, y+35, ORANGE, 7)
        t(d, (151, y+13), left, 31, INK)
        t(d, (733, y+13), right, 31, INK)
    d.line((590, 969, 651, 969), fill=ORANGE, width=9)
    d.polygon([(653, 969), (630, 954), (630, 984)], fill=ORANGE)
    pill(d, (85, 1350, 1157, 1447), "同一设备  ·  同一 Bundle ID  ·  同一版本", WHITE, GREEN, 34)
    save(im, "02-architecture.png")


def evidence():
    im, d = base("03", "深度分析", ["不只是砸壳"],
                 "五类证据拼出可追溯的分析报告")
    items = [
        ("二进制", "依赖库、类与权限", LAVENDER, PURPLE),
        ("沙盒", "文件、数据库与配置", MINT, GREEN),
        ("界面", "截图、层级与交互", PEACH, ORANGE),
        ("运行时", "选定的 Frida 跟踪", PINK, "#B33268"),
    ]
    for i, (head, sub, bg, fg) in enumerate(items):
        x = 70 + (i%2)*563
        y = 555 + (i//2)*274
        rr(d, (x, y, x+538, y+245), bg, 31)
        dot(d, x+45, y+55, fg, 16)
        t(d, (x+83, y+31), head, 45, INK)
        t(d, (x+42, y+121), sub, 32, MUTED)
        t(d, (x+42, y+181), f"0{i+1} / EVIDENCE", 22, fg, latin=True)
    rr(d, (70, 1130, 1172, 1450), "#EDF5EE", 35)
    t(d, (109, 1165), "关键函数 · Hopper / Ghidra", 40, INK)
    rr(d, (107, 1235, 1135, 1366), WHITE, 20)
    t(d, (139, 1263), "定位函数  →  阅读调用  →  对照行为  →  引用原始证据", 32, GREEN)
    t(d, (110, 1393), "分析方法示意；反编译结果不是原始源码", 26, MUTED)
    save(im, "03-evidence.png")


def workflow():
    im, d = base("04", "两阶段流程", ["先分析，再复刻"],
                 "目标随 App 的复杂度调整")
    rr(d, (70, 560, 1172, 880), MINT, 35)
    pill(d, (105, 603, 354, 660), "01 / ANALYZE", WHITE, GREEN, 28)
    t(d, (104, 704), "先生成带出处的报告", 50, INK)
    t(d, (105, 784), "功能、UI、关键类、依赖与未知项", 34, MUTED)
    rr(d, (70, 915, 1172, 1235), PEACH, 35)
    pill(d, (105, 958, 346, 1015), "02 / REBUILD", WHITE, ORANGE, 28)
    t(d, (104, 1059), "再做独立可运行工程", 50, INK)
    t(d, (105, 1139), "先选范围，再实现并同机比较", 34, MUTED)
    rr(d, (70, 1290, 1172, 1450), WHITE, 28, "#D1E1D3", 2)
    t(d, (106, 1325), "复杂 App：验证选定流程", 39, GREEN)
    t(d, (107, 1390), "覆盖范围和剩余差异会明确列出", 30, MUTED)
    save(im, "04-workflow.png")


def phone(im, d, x, y, path, label, color):
    pill(d, (x, y-70, x+430, y-9), label, color, INK, 31)
    rr(d, (x, y, x+430, y+951), INK, 54)
    shot = Image.open(path).convert("RGB")
    shot = shot.resize((390, 844), Image.Resampling.LANCZOS)
    im.paste(shot, (x+20, y+49))
    d.line((x+174, y+918, x+256, y+918), fill="#B4C1B9", width=7)


def compare():
    im, d = base("05", "实机对照", ["同一台手机上", "差异看得见"],
                 "Calculator · iPhone 14 · iOS 17.3.1")
    phone(im, d, 70, 603, ROOT / "assets/calculator-original.jpg", "原版 App", MINT)
    phone(im, d, 742, 603, ROOT / "assets/calculator-rebuilt.jpg", "独立复刻", PINK)
    rr(d, (527, 919, 714, 1080), YELLOW, 32)
    center(d, 944, "7 + 8", 40, INK)
    center(d, 1008, "= 15", 42, PURPLE)
    pill(d, (141, 1508, 1101, 1555), "选定流程已验证 · 可见差异仍记录在报告里", WHITE, GREEN, 29)
    save(im, "05-comparison.png")


def deliverables():
    im, d = base("06", "结果与入口", ["交付的不只是截图"],
                 "报告、工程和对照结果一起留下")
    rr(d, (70, 555, 601, 982), MINT, 33)
    rr(d, (641, 555, 1172, 982), PEACH, 33)
    pill(d, (104, 595, 344, 650), "深度分析", WHITE, GREEN, 30)
    pill(d, (675, 595, 915, 650), "可运行复刻", WHITE, ORANGE, 30)
    for i, item in enumerate(["带证据的报告", "核心 UI 与功能", "关键类与依赖", "未知项明确标记"]):
        dot(d, 119, 731+i*58, GREEN, 7)
        t(d, (146, 704+i*58), item, 31, INK)
    for i, item in enumerate(["独立 iOS 工程", "同机安装测试", "选定流程对照", "差异清单"]):
        dot(d, 690, 731+i*58, ORANGE, 7)
        t(d, (717, 704+i*58), item, 31, INK)
    rr(d, (70, 1023, 1172, 1185), WHITE, 28, "#D1E1D3", 2)
    t(d, (106, 1054), "实测设备", 35, GREEN)
    t(d, (106, 1110), "iOS 16  ·  iOS 17  ·  iOS 26", 38, INK)
    rr(d, (70, 1226, 1172, 1480), "#D9F6E3", 35)
    t(d, (107, 1263), "在 GitHub 搜索", 35, GREEN)
    t(d, (104, 1343), "everettjf/copyapp", 62, INK, latin=True)
    t(d, (109, 1433), "查看代码、安装文档与已知限制", 27, MUTED)
    save(im, "06-github.png")


if __name__ == "__main__":
    cover()
    architecture()
    evidence()
    workflow()
    compare()
    deliverables()
    preview = Image.new("RGB", (3*414, 2*552), BG)
    for i, path in enumerate(sorted(OUT.glob("0[1-6]-*.png"))):
        tile = Image.open(path).resize((414, 552), Image.Resampling.LANCZOS)
        preview.paste(tile, ((i%3)*414, (i//3)*552))
    preview.save(HERE / "preview.png", optimize=True)
