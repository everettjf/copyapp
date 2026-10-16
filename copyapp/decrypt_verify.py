"""Check a candidate decrypted IPA without claiming how it was produced."""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from zipfile import ZipFile

from copyapp.ipa import analyze_ipa


def inspect_decrypted_ipa(path: Path, bundle_id: Optional[str] = None) -> Dict[str, Any]:
    static = analyze_ipa(path)
    binaries = static["binaries"]
    main_path = next((item["path"] for item in binaries
                      if item["path"].startswith("Payload/")
                      and item["path"].count("/") == 2
                      and item["path"].endswith("/" + static["executable"])), None)
    failures = []
    if bundle_id and static["bundle_id"] != bundle_id:
        failures.append("bundle_id_mismatch")
    if main_path is None:
        failures.append("main_binary_missing")
    for binary in binaries:
        if binary.get("status"):
            failures.append("binary_unreadable:" + binary["path"])
        elif binary.get("encryption_status") == "cryptid_nonzero":
            failures.append("still_encrypted:" + binary["path"])
        elif binary.get("encryption_status") not in ("cryptid_zero", "command_absent"):
            failures.append("encryption_unknown:" + binary["path"])
    with ZipFile(path) as archive:
        support_files = [name for name in archive.namelist()
                         if "/SC_Info/" in name and not name.endswith("/")]
    return {
        "schema_version": 1,
        "source": str(path), "ipa_sha256": static["ipa_sha256"],
        "bundle_id": static["bundle_id"], "version": static["version"],
        "build": static["build"], "main_path": main_path,
        "checked_binaries": len(binaries),
        "encryption_statuses": [{"path": item["path"],
                                 "status": item.get("encryption_status", "unreadable")}
                                for item in binaries],
        "sc_info_file_count": len(support_files),
        "header_check_passed": not failures,
        "failures": failures,
        "note": "Header checks do not prove code bytes were correctly decrypted; compare against runtime evidence when available. SC_Info files may contain account-specific data and are not listed here.",
    }


def write_decryption_check(result: Dict[str, Any], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    (output / "decryption-check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# IPA 加密标记校验", "",
             f"- Bundle ID：`{result['bundle_id']}`",
             f"- IPA SHA-256：`{result['ipa_sha256']}`",
             f"- 已检查二进制：{result['checked_binaries']}",
             f"- 加密标记校验：{'通过' if result['header_check_passed'] else '未通过'}",
             f"- SC_Info 文件数：{result['sc_info_file_count']}（可能含账号相关数据，报告不列文件名）", ""]
    for item in result["encryption_statuses"]:
        lines.append(f"- `{item['path']}`：`{item['status']}`")
    if result["failures"]:
        lines.extend(["", "## 未通过原因", ""])
        lines.extend(f"- `{reason}`" for reason in result["failures"])
    lines.extend(["", "Mach-O 头部加密标记为零或不存在，只是静态分析的必要检查；"
                  "本命令没有执行脱壳，也不能单独证明代码字节正确。", ""])
    report = output / "decryption-check.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
