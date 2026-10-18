# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · Français · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP recueille des preuves sur le paquet, l'interface, le bac à sable et le comportement d'une application installée sur un iPhone jailbreaké. Il produit un rapport d'analyse relié à ses sources, puis aide à créer une application iOS indépendante qui reproduit des fonctions choisies et les compare sur l'appareil réel.

## Fonctionnement

Un agent de codage pilote la CLI Copy APP sur Mac. OpenSSH, Frida, iOS MCP ou iCTRL en option recueillent des preuves sur l'iPhone sélectionné. Ghidra ou Hopper peuvent analyser le code natif sur Mac. Le rapport relu et `feature-spec.json` guident la nouvelle application ; les mêmes parcours sont ensuite rejoués dans l'original et la reconstruction, avec examen des captures d'écran. Le [schéma d'architecture et le guide d'installation détaillé](../README.md) sont en anglais.

## Démarrage rapide

Installez Python 3.9+ sur Mac, branchez un iPhone jailbreaké en USB et confirmez la confiance, puis lancez :

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Commencez par le [premier relevé USB](../setup.md). Une analyse approfondie nécessite aussi SSH, Frida et un service d'interface sur le téléphone.

## Principes et contributions

Conserver les preuves avant de les interpréter et signaler les inconnues. La validation de parcours choisis ne démontre pas une équivalence complète. Les bogues reproductibles, tests, scripts UI et traductions sont bienvenus. Ne commitez ni IPA, ni identifiants, ni données brutes du bac à sable. Voir le [guide de contribution](../../CONTRIBUTING.md).

Des parcours choisis ont été vérifiés sur l'iPhone XR sous iOS 16.1.1 et l'iPhone 14 sous iOS 17.3.1, ainsi que pour Calculator et Clock sur l'iPhone 11 sous iOS 26.0.1. Voir le [périmètre de prise en charge](../../README.md). La langue de la documentation ne modifie pas celle de la CLI ou des rapports.
