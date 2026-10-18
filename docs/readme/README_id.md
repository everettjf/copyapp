# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · Bahasa Indonesia · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP mengumpulkan bukti paket aplikasi, antarmuka, sandbox, dan perilaku saat berjalan dari aplikasi yang terpasang pada iPhone jailbreak. Proyek ini menghasilkan laporan analisis dengan rujukan sumber dan membantu membangun aplikasi iOS mandiri yang meniru fungsi terpilih untuk dibandingkan pada perangkat asli.

## Cara kerja

Coding Agent menjalankan Copy APP CLI di Mac. OpenSSH, Frida, iOS MCP, atau iCTRL opsional mengumpulkan bukti dari iPhone yang dipilih secara tepat. Jika diperlukan, Ghidra atau Hopper menganalisis kode native di Mac. Laporan yang ditinjau dan `feature-spec.json` memandu implementasi baru; alur yang sama dijalankan pada aplikasi asli dan aplikasi baru, lalu tangkapan layar diperiksa. [Diagram arsitektur dan panduan instalasi lengkap](../../README.md#how-it-works) tersedia dalam bahasa Inggris.

## Mulai cepat

Pasang Python 3.9+ di Mac, sambungkan iPhone jailbreak melalui USB, terima permintaan kepercayaan, lalu jalankan:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Mulailah dengan [survei USB pertama](../../README.md#install-and-run-your-first-survey). Analisis mendalam juga memerlukan SSH, Frida, dan layanan antarmuka di ponsel.

## Prinsip dan kontribusi

Simpan bukti sebelum menafsirkannya dan jelaskan hal yang belum diketahui. Keberhasilan beberapa alur terpilih tidak membuktikan kesetaraan seluruh aplikasi. Laporan bug yang dapat diulang, pengujian, skrip UI, dan terjemahan sangat diterima. Jangan memasukkan IPA, kredensial, atau data sandbox mentah ke Git. Lihat [panduan kontribusi](../../CONTRIBUTING.md).

Alur terpilih telah diverifikasi pada iPhone XR dengan iOS 16.1.1 dan iPhone 14 dengan iOS 17.3.1, serta untuk Calculator dan Clock pada iPhone 11 dengan iOS 26.0.1. Lihat [cakupan dukungan](../../README.md). Bahasa dokumentasi tidak mengubah bahasa CLI atau laporan.
