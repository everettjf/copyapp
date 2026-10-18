# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · 日本語 · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP は、脱獄済み iPhone にインストールされたアプリのパッケージ、UI、サンドボックス、実行時の証拠を収集します。根拠を示す分析レポートを作成し、選んだ機能を再現する独立した iOS アプリの開発と実機比較を支援します。

## 仕組み

Coding Agent が Mac 上の Copy APP CLI を操作します。指定した端末から OpenSSH、Frida、iOS MCP または任意の iCTRL を使って証拠を取得し、必要に応じて Mac の Ghidra または Hopper でネイティブコードを調べます。レビュー済みレポートと `feature-spec.json` を基に別のアプリを作り、同じ iPhone で元アプリとの操作結果とスクリーンショットを比較します。[構成図と詳細なセットアップ](../../README.md#how-it-works)は英語版を参照してください。

## クイックスタート

Mac に Python 3.9 以降を用意し、脱獄済み iPhone を USB 接続して信頼した後、実行します。

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

まず[USB 調査の手順](../../README.md#install-and-run-your-first-survey)を完了してください。詳しい分析には端末側の SSH、Frida、UI サービスが必要です。

## 方針と貢献

説明より先に証拠を残し、不明な点を明記します。選んだ操作の検証はアプリ全体の同等性を意味しません。再現手順のある不具合、テスト、UI スクリプト、翻訳を歓迎します。IPA、認証情報、端末の生データはコミットしないでください。[貢献ガイド](../../CONTRIBUTING.md)を参照してください。

選定した解析・再実装フローは iOS 16.1.1 の iPhone XR と iOS 17.3.1 の iPhone 14 で検証済みです。iOS 26.0.1 の iPhone 11 では Calculator と Clock の選定フローも検証しました。詳細は[対応範囲](../../README.md)をご覧ください。文書の言語は CLI や生成レポートの言語を変更しません。
