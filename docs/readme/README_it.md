# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · Italiano · [Ελληνικά](README_el.md)

Copy APP raccoglie prove relative al pacchetto, all'interfaccia, alla sandbox e al comportamento di un'app installata su un iPhone con jailbreak. Produce un rapporto di analisi collegato alle fonti e aiuta a creare un'app iOS indipendente che riproduca funzioni selezionate per confrontarle sul dispositivo reale.

## Come funziona

Un agente di programmazione guida la CLI di Copy APP sul Mac. OpenSSH, Frida, iOS MCP o iCTRL opzionale raccolgono le prove dall'iPhone scelto. Quando serve, Ghidra o Hopper analizzano il codice nativo sul Mac. Il rapporto revisionato e `feature-spec.json` guidano la nuova implementazione; gli stessi percorsi vengono ripetuti nell'originale e nella nuova app, confrontando anche gli screenshot. Il [diagramma dell'architettura e la guida completa all'installazione](../../README.md#how-it-works) sono in inglese.

## Avvio rapido

Installa Python 3.9+ sul Mac, collega via USB un iPhone con jailbreak, conferma l'attendibilità ed esegui:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Completa prima la [prima ricognizione USB](../../README.md#install-and-run-your-first-survey). L'analisi approfondita richiede anche SSH, Frida e un servizio per l'interfaccia sul telefono.

## Principi e contributi

Conserva le prove prima di interpretarle e indica chiaramente ciò che resta ignoto. La verifica dei percorsi scelti non dimostra l'equivalenza completa delle app. Sono benvenuti bug riproducibili, test, script UI e traduzioni. Non inviare IPA, credenziali o dati grezzi della sandbox a Git. Consulta la [guida ai contributi](../../CONTRIBUTING.md).

È stato verificato l'iPhone XR con iOS 16.1.1; iOS 17 e 26 non sono ancora stati testati. La lingua della documentazione non cambia quella della CLI o dei rapporti.
