# Copy APP

**Dil:** Türkçe · [Tüm diller](../../README.md#languages) · [English](../../README.md)

Copy APP, jailbreak uygulanmış bir iPhone'daki kurulu uygulamanın paket, arayüz, sandbox ve çalışma zamanı kanıtlarını toplar. Kaynaklara bağlı bir analiz raporu üretir ve seçilen davranışları bağımsız, çalıştırılabilir bir iOS uygulamasında yeniden oluşturup gerçek cihazda karşılaştırmaya yardımcı olur.

## Nasıl çalışır?

Bir kodlama ajanı Mac'teki Copy APP CLI'yi yönetir. OpenSSH, Frida ve iOS MCP ya da isteğe bağlı iCTRL, belirtilen iPhone'dan kanıt toplar. Gerekirse Ghidra veya Hopper Mac'te yerel kodu inceler. İncelenmiş rapor ve `feature-spec.json` yeni uygulamaya yol gösterir; özgün ve yeni uygulamanın akışları aynı telefonda yeniden oynatılır ve ekran görüntüleri karşılaştırılır. [Mimari şema ve ayrıntılı kurulum](../../README.md#how-it-works) İngilizce kılavuzdadır.

## Hızlı başlangıç

Mac'te Python 3.9+ kurun, jailbreak uygulanmış iPhone'u USB ile bağlayıp güvenin ve çalıştırın:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Önce [USB ile ilk incelemeyi](../../README.md#install-and-run-your-first-survey) tamamlayın. Derin analiz için telefonda SSH, Frida ve arayüz servisi gerekir.

## İlkeler ve katkı

Önce kanıtı kaydedin, sonra açıklayın; bilinmeyenleri açıkça belirtin. Seçilen akışların doğrulanması uygulamanın tümüyle eşdeğer olduğu anlamına gelmez. Tekrarlanabilir hata raporları, testler, UI betikleri ve çeviriler memnuniyetle karşılanır. IPA, kimlik bilgileri veya ham telefon verilerini göndermeyin. [Katkı kılavuzuna](../../CONTRIBUTING.md) bakın.

Şu ana kadar iOS 16.1.1 yüklü iPhone XR doğrulandı; iOS 17 ve 26 henüz test edilmedi. Belge dili CLI veya rapor dilini değiştirmez.
