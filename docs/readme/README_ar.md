# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · العربية · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

يجمع Copy APP أدلة عن حزمة التطبيق وواجهته وبياناته داخل بيئة العزل وسلوكه أثناء التشغيل على iPhone مكسور الحماية. وينشئ تقرير تحليل مرتبطًا بمصادره، ثم يساعد على بناء تطبيق iOS مستقل يعيد تنفيذ وظائف محددة ومقارنتها على الجهاز الحقيقي.

## كيف يعمل

يدير وكيل برمجي أداة Copy APP CLI على Mac. وتجمع OpenSSH وFrida وiOS MCP، أو iCTRL الاختياري، الأدلة من هاتف iPhone المحدد. ويمكن استخدام Ghidra أو Hopper على Mac لتحليل الشيفرة الأصلية. يوجّه التقرير المراجع وملف `feature-spec.json` تنفيذ التطبيق الجديد؛ ثم تُعاد خطوات الاختبار على التطبيق الأصلي والجديد في الهاتف نفسه وتُراجع لقطات الشاشة. يتوفر [مخطط البنية ودليل التثبيت الكامل](../../README.md#how-it-works) بالإنجليزية.

## البدء السريع

ثبّت Python 3.9 أو أحدث على Mac، وصِل iPhone مكسور الحماية عبر USB ووافق على الثقة، ثم شغّل:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

ابدأ [بالفحص الأولي عبر USB](../../README.md#install-and-run-your-first-survey). يحتاج التحليل المتعمق أيضًا إلى SSH وFrida وخدمة للتحكم بالواجهة على الهاتف.

## المبادئ والمساهمة

احفظ الأدلة قبل تفسيرها، واذكر ما لا يزال مجهولًا بوضوح. نجاح خطوات محددة لا يثبت تكافؤ التطبيق كاملًا. نرحب بالأخطاء القابلة لإعادة الإنتاج والاختبارات ونصوص الواجهة والترجمات. لا ترفع ملفات IPA أو بيانات الاعتماد أو بيانات العزل الخام إلى Git. راجع [دليل المساهمة](../../CONTRIBUTING.md).

تم التحقق من iPhone XR بنظام iOS 16.1.1، وiPhone 14 بنظام iOS 17.3.1، ومسارات محددة لتطبيقَي Calculator وClock على iPhone 11 بنظام iOS 26.0.1. راجع [نطاق الدعم](../../README.md). لغة التوثيق لا تغيّر لغة أداة CLI أو التقارير.
