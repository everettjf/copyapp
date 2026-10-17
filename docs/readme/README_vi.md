# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · Tiếng Việt · [ไทย](README_th.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP thu thập bằng chứng về gói ứng dụng, giao diện, sandbox và hành vi khi chạy của một ứng dụng đã cài trên iPhone jailbreak. Công cụ tạo báo cáo phân tích có dẫn nguồn, rồi hỗ trợ xây dựng một ứng dụng iOS độc lập để tái hiện và so sánh các chức năng đã chọn trên thiết bị thật.

## Cách hoạt động

Coding Agent điều khiển Copy APP CLI trên Mac. OpenSSH, Frida, iOS MCP hoặc iCTRL tùy chọn thu thập bằng chứng từ đúng iPhone. Khi cần, Ghidra hoặc Hopper trên Mac phân tích mã gốc. Báo cáo đã rà soát và `feature-spec.json` hướng dẫn việc xây dựng ứng dụng mới; các luồng của bản gốc và bản mới được chạy lại trên cùng điện thoại và ảnh màn hình được đối chiếu. Xem [sơ đồ kiến trúc và hướng dẫn cài đặt đầy đủ](../../README.md#how-it-works) bằng tiếng Anh.

## Bắt đầu nhanh

Cài Python 3.9+ trên Mac, kết nối iPhone jailbreak qua USB, xác nhận tin cậy rồi chạy:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

Trước tiên hãy hoàn tất [khảo sát USB ban đầu](../../README.md#install-and-run-your-first-survey). Phân tích sâu cần thêm SSH, Frida và dịch vụ giao diện trên điện thoại.

## Nguyên tắc và đóng góp

Lưu bằng chứng trước khi diễn giải và nêu rõ những điều chưa biết. Kiểm chứng vài luồng được chọn không chứng minh toàn bộ ứng dụng tương đương. Chúng tôi hoan nghênh lỗi có thể tái hiện, bài kiểm tra, kịch bản UI và bản dịch. Không đưa IPA, thông tin xác thực hay dữ liệu sandbox thô vào Git. Xem [hướng dẫn đóng góp](../../CONTRIBUTING.md).

Đã kiểm chứng iPhone XR chạy iOS 16.1.1 và quy trình phân tích, dựng lại đã chọn trên iPhone 14 chạy iOS 17.3.1 (Relaxin/RootHide); iOS 26 chưa được kiểm thử. Xem [phạm vi hỗ trợ](../../README.md). Ngôn ngữ tài liệu không thay đổi ngôn ngữ CLI hoặc báo cáo.
