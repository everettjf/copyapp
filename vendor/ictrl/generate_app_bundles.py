#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🛠 生成内置常用 app 的 bundle id 清单 (AppBundles.plist)

用 iTunes Search API 查询一批国内外常用 app 的名称 → bundle_id，
写入 iCTRLUITests/AppBundles.plist，打包进 runner。
运行时 search_app / launch_app 先查这份内置清单（离线、秒回），
未命中再回退到 iTunes Search API。

用法:
    python3 generate_app_bundles.py            # 生成 plist
    python3 generate_app_bundles.py --dry-run  # 只打印，不写文件

依赖: 仅标准库 (urllib) + tqdm (进度显示)。
"""

import sys
import json
import time
import plistlib
import argparse
import urllib.parse
import urllib.request
import concurrent.futures
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    print("⚠️ 未安装 tqdm，进度将以简单文本显示。 pip install tqdm 获得更好体验。")
    def tqdm(it, **kw):
        return it

OUTPUT = Path(__file__).parent / "iCTRLUITests" / "AppBundles.plist"

# 🌏 常用 app 查询列表: (搜索关键词, 商店国家)
# 国内 app 用 cn 商店，国际 app 用 us 商店，命中更准。
QUERIES = [
    # —— 国内 · 社交/通讯 ——
    ("微信", "cn"), ("QQ", "cn"), ("钉钉", "cn"), ("企业微信", "cn"),
    ("飞书", "cn"), ("微博", "cn"), ("小红书", "cn"), ("知乎", "cn"),
    ("豆瓣", "cn"), ("陌陌", "cn"), ("Soul", "cn"),
    # —— 国内 · 电商/支付 ——
    ("淘宝", "cn"), ("天猫", "cn"), ("京东", "cn"), ("拼多多", "cn"),
    ("支付宝", "cn"), ("闲鱼", "cn"), ("唯品会", "cn"), ("苏宁易购", "cn"),
    ("得物", "cn"), ("1688", "cn"), ("云闪付", "cn"),
    # —— 国内 · 出行/生活/本地 ——
    ("高德地图", "cn"), ("百度地图", "cn"), ("滴滴出行", "cn"),
    ("美团", "cn"), ("大众点评", "cn"), ("饿了么", "cn"), ("携程旅行", "cn"),
    ("去哪儿旅行", "cn"), ("飞猪", "cn"), ("12306", "cn"),
    ("大麦", "cn"), ("猫眼电影", "cn"), ("肯德基", "cn"), ("麦当劳", "cn"),
    # —— 国内 · 视频/音乐/娱乐 ——
    ("抖音", "cn"), ("快手", "cn"), ("哔哩哔哩", "cn"), ("腾讯视频", "cn"),
    ("爱奇艺", "cn"), ("优酷", "cn"), ("芒果TV", "cn"), ("西瓜视频", "cn"),
    ("网易云音乐", "cn"), ("QQ音乐", "cn"), ("酷狗音乐", "cn"), ("喜马拉雅", "cn"),
    # —— 国内 · 资讯/工具/浏览器 ——
    ("今日头条", "cn"), ("腾讯新闻", "cn"), ("百度", "cn"), ("UC浏览器", "cn"),
    ("夸克", "cn"), ("WPS Office", "cn"), ("百度网盘", "cn"),
    ("菜鸟", "cn"), ("顺丰速运", "cn"),
    # —— 国内 · 金融/银行 ——
    ("中国工商银行", "cn"), ("中国建设银行", "cn"), ("招商银行", "cn"),
    ("中国农业银行", "cn"), ("中国银行", "cn"),
    # —— 国内 · 教育/健康/其他 ——
    ("学习强国", "cn"), ("作业帮", "cn"), ("Keep", "cn"), ("boss直聘", "cn"),
    ("智联招聘", "cn"), ("58同城", "cn"), ("链家", "cn"), ("贝壳找房", "cn"),
    # —— 国际 · 社交/通讯 ——
    ("WhatsApp", "us"), ("Messenger", "us"), ("Instagram", "us"),
    ("Facebook", "us"), ("X Twitter", "us"), ("Telegram", "us"),
    ("Snapchat", "us"), ("Discord", "us"), ("LINE", "us"), ("WeChat", "us"),
    ("Threads", "us"), ("Reddit", "us"), ("LinkedIn", "us"),
    # —— 国际 · 视频/音乐 ——
    ("YouTube", "us"), ("TikTok", "us"), ("Netflix", "us"), ("Spotify", "us"),
    ("Disney+", "us"), ("Twitch", "us"), ("Prime Video", "us"),
    ("Apple Music", "us"), ("SoundCloud", "us"),
    # —— 国际 · 工具/生产力 ——
    ("Gmail", "us"), ("Google Maps", "us"), ("Google Chrome", "us"),
    ("Google Drive", "us"), ("Microsoft Outlook", "us"), ("Microsoft Teams", "us"),
    ("Zoom", "us"), ("Slack", "us"), ("Notion", "us"), ("Google Translate", "us"),
    ("ChatGPT", "us"), ("Google", "us"),
    # —— 国际 · 电商/出行/支付 ——
    ("Amazon", "us"), ("PayPal", "us"), ("Uber", "us"), ("Airbnb", "us"),
    ("Booking.com", "us"), ("AliExpress", "us"), ("SHEIN", "us"), ("Temu", "us"),
]


def query_itunes(term, country):
    """查一个关键词，返回 (name, bundle_id) 或 None。"""
    params = urllib.parse.urlencode({
        "term": term, "country": country, "entity": "software", "limit": 1,
    })
    url = f"https://itunes.apple.com/search?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "iCTRL/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])
        if not results:
            return None
        r = results[0]
        bid = r.get("bundleId")
        name = r.get("trackName")
        if not bid:
            return None
        return {
            "name": name,
            "bundle_id": bid,
            "query": term,
            "country": country,
        }
    except Exception as e:
        print(f"❌ 查询失败 {term} ({country}): {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    ap.add_argument("--workers", type=int, default=8, help="并发数")
    args = ap.parse_args()

    print(f"🔍 查询 {len(QUERIES)} 个常用 app 的 bundle id...")

    apps = []
    seen_bids = set()

    # 并发查询，持续补充任务提升效率
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(query_itunes, term, c): (term, c)
                      for term, c in QUERIES}
        for future in tqdm(concurrent.futures.as_completed(future_map),
                           total=len(future_map), desc="🌐 iTunes"):
            res = future.result()
            if not res:
                continue
            bid = res["bundle_id"]
            if bid in seen_bids:      # 去重 (如 微信/WeChat 可能重复)
                continue
            seen_bids.add(bid)
            apps.append(res)
            time.sleep(0.02)          # 轻微限速，避免触发 API 限流

    # 按名称排序，稳定输出
    apps.sort(key=lambda a: (a["country"], a["name"] or ""))

    print(f"\n✅ 命中 {len(apps)}/{len(QUERIES)} 个 app")
    for a in apps:
        print(f"  {a['bundle_id']:40} {a['name']}")

    if args.dry_run:
        print("\n(--dry-run，未写文件)")
        return

    # plist 结构: { "apps": [ {name, bundle_id, query, country}, ... ], "generated_count": N }
    payload = {
        "apps": apps,
        "count": len(apps),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as f:
        plistlib.dump(payload, f)
    print(f"\n💾 已写入 {OUTPUT} ({len(apps)} 个 app)")


if __name__ == "__main__":
    main()
