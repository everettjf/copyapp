# Copy APP

**Bahasa:** Bahasa Indonesia · [Semua bahasa](../../README.md#languages) · [English](../../README.md)

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

Yang sudah diverifikasi adalah iPhone XR dengan iOS 16.1.1; iOS 17 dan 26 belum diuji. Bahasa dokumentasi tidak mengubah bahasa CLI atau laporan.
