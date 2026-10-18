# Copy APP

[English](../../README.md) · [简体中文](../../README.zh-CN.md) · [繁體中文](README_zh-TW.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Türkçe](README_tr.md) · [Русский](README_ru.md) · [Tiếng Việt](README_vi.md) · ไทย · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Українська](README_uk.md) · [Polski](README_pl.md) · [Português (Brasil)](README_pt-BR.md) · [العربية](README_ar.md) · [فارسی](README_fa.md) · [Bahasa Indonesia](README_id.md) · [Italiano](README_it.md) · [Ελληνικά](README_el.md)

Copy APP รวบรวมหลักฐานจากแพ็กเกจ หน้าจอ แซนด์บ็อกซ์ และพฤติกรรมขณะทำงานของแอปที่ติดตั้งบน iPhone ที่เจลเบรกแล้ว จากนั้นสร้างรายงานวิเคราะห์ที่อ้างอิงแหล่งข้อมูล และช่วยสร้างแอป iOS อิสระเพื่อทำซ้ำฟังก์ชันที่เลือกและเปรียบเทียบบนอุปกรณ์จริง

## วิธีทำงาน

Coding Agent ควบคุม Copy APP CLI บน Mac โดยใช้ OpenSSH, Frida, iOS MCP หรือ iCTRL ซึ่งเป็นตัวเลือกเสริม เพื่อเก็บหลักฐานจาก iPhone เครื่องที่ระบุ หากจำเป็น Ghidra หรือ Hopper บน Mac จะช่วยวิเคราะห์โค้ดเนทีฟ รายงานที่ตรวจทานแล้วและ `feature-spec.json` ใช้กำหนดงานสร้างแอปใหม่ จากนั้นเล่นขั้นตอนเดิมบนแอปต้นฉบับและแอปใหม่ในโทรศัพท์เครื่องเดียวกัน พร้อมตรวจภาพหน้าจอ ดู[แผนภาพสถาปัตยกรรมและคู่มือติดตั้งฉบับเต็ม](../README.md) ภาษาอังกฤษ

## เริ่มต้นอย่างรวดเร็ว

ติดตั้ง Python 3.9+ บน Mac เชื่อมต่อ iPhone ที่เจลเบรกผ่าน USB และกดยืนยันความเชื่อถือ แล้วรัน:

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

เริ่มจาก[การสำรวจผ่าน USB](../setup.md) ก่อน การวิเคราะห์เชิงลึกต้องใช้ SSH, Frida และบริการควบคุมหน้าจอบนโทรศัพท์เพิ่มเติม

## หลักการและการมีส่วนร่วม

บันทึกหลักฐานก่อนตีความ และระบุสิ่งที่ยังไม่ทราบให้ชัดเจน การทดสอบขั้นตอนที่เลือกไม่ได้พิสูจน์ว่าแอปทั้งสองเหมือนกันทุกด้าน ยินดีรับรายงานข้อผิดพลาดที่ทำซ้ำได้ การทดสอบ สคริปต์ UI และคำแปล อย่าคอมมิต IPA ข้อมูลรับรอง หรือข้อมูลแซนด์บ็อกซ์ดิบ อ่าน[คู่มือการมีส่วนร่วม](../../CONTRIBUTING.md)

ขณะนี้ทดสอบขั้นตอนที่เลือกบน iPhone XR ที่ใช้ iOS 16.1.1 และ iPhone 14 ที่ใช้ iOS 17.3.1 รวมถึง Calculator และ Clock บน iPhone 11 ที่ใช้ iOS 26.0.1 แล้ว ดู[ขอบเขตการรองรับ](../../README.md) ภาษาของเอกสารไม่เปลี่ยนภาษาของ CLI หรือรายงาน
