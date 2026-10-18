# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · Español · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP recopila pruebas del paquete, la interfaz, el sandbox y el comportamiento en ejecución de una aplicación instalada en un iPhone con jailbreak. Produce un informe de análisis con referencias a las fuentes y ayuda a crear una aplicación iOS independiente que reproduzca funciones seleccionadas para compararlas en el dispositivo real.

## Cómo funciona

Un agente de programación controla la CLI de Copy APP en el Mac. OpenSSH, Frida, iOS MCP o el iCTRL opcional obtienen pruebas del iPhone elegido. Cuando hace falta, Ghidra o Hopper analizan el código nativo en el Mac. El informe revisado y `feature-spec.json` guían la nueva aplicación; después se repiten los mismos flujos en la original y la nueva, y se revisan las capturas. El [diagrama de arquitectura y la instalación detallada](../../README.md#how-it-works) están en inglés.

## Inicio rápido

Instala Python 3.9+ en el Mac, conecta por USB un iPhone con jailbreak y acepta la confianza. Después ejecuta:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Completa primero la [inspección inicial por USB](../../README.md#install-and-run-your-first-survey). El análisis profundo también necesita SSH, Frida y un servicio de interfaz en el teléfono.

## Principios y contribuciones

Primero se conserva la evidencia; después se interpreta, indicando lo que sigue siendo desconocido. Verificar unos flujos no demuestra equivalencia completa. Se agradecen errores reproducibles, pruebas, guiones de UI y traducciones. No incluyas IPA, credenciales ni datos sin procesar del sandbox en Git. Consulta la [guía de contribución](../../CONTRIBUTING.md).

Se han verificado flujos seleccionados en el iPhone XR con iOS 16.1.1 y el iPhone 14 con iOS 17.3.1, además de Calculator y Clock en el iPhone 11 con iOS 26.0.1. Consulte el [alcance de compatibilidad](../../README.md). El idioma de la documentación no cambia el idioma de la CLI ni de los informes.
