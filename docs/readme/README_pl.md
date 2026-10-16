# Copy APP

**Język:** Polski · [Wszystkie języki](../../README.md#languages) · [English](../../README.md)

Copy APP zbiera dowody dotyczące pakietu, interfejsu, piaskownicy i działania zainstalowanej aplikacji na iPhonie z jailbreakiem. Tworzy raport analityczny z odnośnikami do źródeł i pomaga zbudować niezależną aplikację iOS odtwarzającą wybrane funkcje, które następnie można porównać na prawdziwym urządzeniu.

## Jak to działa

Agent programistyczny steruje Copy APP CLI na Macu. OpenSSH, Frida, iOS MCP lub opcjonalny iCTRL zbierają dowody z dokładnie wskazanego iPhone'a. W razie potrzeby Ghidra lub Hopper analizują kod natywny na Macu. Sprawdzony raport i `feature-spec.json` prowadzą nową implementację; te same scenariusze są odtwarzane w oryginale i nowej aplikacji, a zrzuty ekranu porównywane. [Schemat architektury i pełna instalacja](../../README.md#how-it-works) są dostępne po angielsku.

## Szybki start

Zainstaluj Python 3.9+ na Macu, podłącz iPhone'a z jailbreakiem przez USB i potwierdź zaufanie, a następnie uruchom:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Najpierw wykonaj [pierwszą inspekcję USB](../../README.md#install-and-run-your-first-survey). Głębsza analiza wymaga ponadto SSH, Fridy i usługi interfejsu na telefonie.

## Zasady i współpraca

Najpierw zapisuj dowody, potem je interpretuj, wyraźnie oznaczając niewiadome. Sprawdzenie wybranych scenariuszy nie oznacza pełnej równoważności aplikacji. Mile widziane są odtwarzalne błędy, testy, skrypty UI i tłumaczenia. Nie dodawaj do Git plików IPA, danych logowania ani surowych danych piaskownicy. Zobacz [przewodnik współtworzenia](../../CONTRIBUTING.md).

Zweryfikowano iPhone'a XR z iOS 16.1.1; iOS 17 i 26 jeszcze nie testowano. Język dokumentacji nie zmienia języka CLI ani raportów.
