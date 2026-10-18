# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · Deutsch · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP sammelt Paket-, UI-, Sandbox- und Laufzeitbelege einer installierten App auf einem iPhone mit Jailbreak. Daraus entsteht ein Analysebericht mit Quellenverweisen. Anschließend hilft das Projekt, ausgewählte Funktionen in einer unabhängigen, lauffähigen iOS-App umzusetzen und auf dem echten Gerät zu vergleichen.

## Funktionsweise

Ein Coding Agent steuert die Copy APP CLI auf dem Mac. OpenSSH, Frida sowie iOS MCP oder optional iCTRL erfassen Belege vom genau ausgewählten iPhone. Bei Bedarf untersuchen Ghidra oder Hopper den nativen Code auf dem Mac. Der geprüfte Bericht und `feature-spec.json` leiten die neue Implementierung an. Original und Nachbau werden auf demselben Telefon mit denselben Abläufen und Bildschirmfotos verglichen. [Architekturdiagramm und vollständige Installation](../../README.md#how-it-works) stehen im englischen Handbuch.

## Schnellstart

Python 3.9+ auf dem Mac installieren, das iPhone mit Jailbreak per USB verbinden und ihm vertrauen. Dann:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Zuerst die [erste USB-Bestandsaufnahme](../../README.md#install-and-run-your-first-survey) durchführen. Für tiefere Analysen werden zusätzlich SSH, Frida und ein UI-Dienst auf dem Telefon benötigt.

## Grundsätze und Mitarbeit

Erst Belege sichern, dann erklären; Unbekanntes ausdrücklich kennzeichnen. Ein bestandener Test ausgewählter Abläufe bedeutet keine vollständige Gleichwertigkeit der Apps. Reproduzierbare Fehler, Tests, UI-Skripte und Übersetzungen sind willkommen. Keine IPAs, Zugangsdaten oder rohen Sandbox-Daten einchecken. Siehe [Beitragsleitfaden](../../CONTRIBUTING.md).

Geprüft wurden ausgewählte Abläufe auf dem iPhone XR mit iOS 16.1.1 und dem iPhone 14 mit iOS 17.3.1 sowie Calculator und Clock auf dem iPhone 11 mit iOS 26.0.1. Einzelheiten stehen im [Testumfang](../../README.md). Die Dokumentationssprache ändert weder CLI noch Berichtssprache.
