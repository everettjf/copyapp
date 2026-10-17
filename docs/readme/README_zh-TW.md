# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · 繁體中文 · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP 在越獄 iPhone 上蒐集已安裝 App 的套件、介面、沙盒及執行時證據，產生附有來源的分析報告，並協助建立獨立、可執行的 iOS App 來重現選定功能。

## 運作方式

Coding Agent 驅動 Mac 上的 Copy APP CLI；OpenSSH、Frida，以及 iOS MCP 或可選的 iCTRL 從指定手機取得證據。Mac 可選用 Ghidra 或 Hopper 分析原生程式碼。經審閱的報告與 `feature-spec.json` 交給復刻階段；新 App 安裝到同一台手機後，逐條重放原版與復刻版流程並審閱截圖。完整[架構圖與安裝指南](../../README.md#how-it-works)以英文提供。

## 快速開始

在 Mac 安裝 Python 3.9+、連接並信任越獄 iPhone，然後執行：

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

先依照[完整安裝步驟](../../README.md#install-and-run-your-first-survey)完成 USB 初步調查；深入分析才需要手機端 SSH、Frida 與介面服務。

## 理念與貢獻

先保存證據，再解釋功能；明確指出未知部分。驗證選定流程不代表整個 App 等價。歡迎提交可重現的問題、測試、介面腳本和翻譯；請勿提交原始 IPA、憑證或手機沙盒資料。請參閱[貢獻指南](../../CONTRIBUTING.md)。

目前已驗證 iPhone XR / iOS 16.1.1，以及 iPhone 14 / iOS 17.3.1（Relaxin/RootHide）的選定分析與復刻流程；iOS 26 尚未測試。詳細範圍見[英文相容性表](../../README.md)。文件語言不會改變 CLI 或報告語言。
