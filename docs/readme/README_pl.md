# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · Polski · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP zbiera dowody dotyczące pakietu, interfejsu, piaskownicy i działania zainstalowanej aplikacji na iPhonie z jailbreakiem. Tworzy raport analityczny z odnośnikami do źródeł i pomaga zbudować niezależną aplikację iOS odtwarzającą wybrane funkcje, które następnie można porównać na prawdziwym urządzeniu.

## Jak to działa

Agent programistyczny steruje Copy APP CLI na Macu. OpenSSH, Frida, iOS MCP lub opcjonalny iCTRL zbierają dowody z dokładnie wskazanego iPhone'a. W razie potrzeby Ghidra lub Hopper analizują kod natywny na Macu. Sprawdzony raport i `feature-spec.json` prowadzą nową implementację; te same scenariusze są odtwarzane w oryginale i nowej aplikacji, a zrzuty ekranu porównywane. [Schemat architektury i pełna instalacja](../README.md) są dostępne po angielsku.

## Szybki start

Zainstaluj Python 3.9+ na Macu, podłącz iPhone'a z jailbreakiem przez USB i potwierdź zaufanie, a następnie uruchom:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Najpierw wykonaj [pierwszą inspekcję USB](../setup.md). Głębsza analiza wymaga ponadto SSH, Fridy i usługi interfejsu na telefonie.

## Zasady i współpraca

Najpierw zapisuj dowody, potem je interpretuj, wyraźnie oznaczając niewiadome. Sprawdzenie wybranych scenariuszy nie oznacza pełnej równoważności aplikacji. Mile widziane są odtwarzalne błędy, testy, skrypty UI i tłumaczenia. Nie dodawaj do Git plików IPA, danych logowania ani surowych danych piaskownicy. Zobacz [przewodnik współtworzenia](../../CONTRIBUTING.md).

Zweryfikowano wybrane przebiegi na iPhonie XR z iOS 16.1.1 i iPhonie 14 z iOS 17.3.1 oraz aplikacje Calculator i Clock na iPhonie 11 z iOS 26.0.1. Szczegóły opisuje [zakres wsparcia](../../README.md). Język dokumentacji nie zmienia języka CLI ani raportów.
