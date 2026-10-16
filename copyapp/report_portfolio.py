"""Combine independently verified reports for the same exact App build."""

import hashlib
import io
import json
import os
import re
from contextlib import redirect_stdout
from pathlib import Path

from copyapp.verify import sha256_file, verify_case


LINK = re.compile(r"\]\(([^)]+)\)")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verified(path: Path) -> bool:
    with redirect_stdout(io.StringIO()):
        return verify_case(path)


def _source_identity(report: Path) -> dict:
    if not _verified(report):
        raise ValueError(f"source report failed verification: {report}")
    index = _read(report / "report-index.json")
    analysis = Path(index["source_case"]).resolve(strict=True)
    if report == analysis or report in analysis.parents or analysis in report.parents:
        raise ValueError("source report and analysis must be separate")
    if (sha256_file(analysis / "analysis-index.json") !=
            index["source_case_index_sha256"] or not _verified(analysis)):
        raise ValueError("source analysis changed or failed verification")
    state = _read(analysis / "run-state.json")
    app = _read(analysis / "survey" / "app.json")
    static = _read(analysis / "decrypted" / "static" / "ipa-index.json")
    executable = static["executable"]
    matches = [item for item in static["binaries"]
               if item["path"].endswith(".app/" + executable)]
    if len(matches) != 1:
        raise ValueError("decrypted main executable is ambiguous")
    identity = {
        "bundle_id": index["target_bundle_id"],
        "device_id_sha256_prefix": state["device_id_sha256_prefix"],
        "version": app["CFBundleShortVersionString"],
        "build": app["CFBundleVersion"],
        "main_binary_sha256": matches[0]["sha256"],
    }
    if (state["bundle_id"] != identity["bundle_id"] or
            app["CFBundleIdentifier"] != identity["bundle_id"] or
            static["bundle_id"] != identity["bundle_id"] or
            static["version"] != identity["version"] or
            static["build"] != identity["build"] or
            matches[0]["encryption_status"] != "cryptid_zero"):
        raise ValueError("source analysis App build or binary identity differs")
    return identity


def _linked_report(source: Path, output: Path) -> str:
    """Copy prose while making only source-local Markdown links work from output."""
    body = (source / "report.md").read_text(encoding="utf-8")
    inside_fence = False
    lines = []
    for line in body.splitlines():
        if line.startswith("```"):
            inside_fence = not inside_fence
        if not inside_fence and line.startswith("#"):
            line = "#" + line
        if not inside_fence:
            def relink(match):
                target = match.group(1)
                if (target.startswith(("https://", "http://", "mailto:", "#", "/")) or
                        "?" in target or "#" in target):
                    return match.group(0)
                destination = (source / target).resolve(strict=True)
                if source not in destination.parents:
                    raise ValueError("report link leaves its source case")
                relative = os.path.relpath(destination, output)
                return "](" + Path(relative).as_posix() + ")"
            line = LINK.sub(relink, line)
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


def _render(sources: list[Path], output: Path, identity: dict) -> str:
    text = ["# Copy APP 综合逆向报告", "",
            f"- App：`{identity['bundle_id']}` / {identity['version']} ({identity['build']})",
            f"- 设备身份摘要：`{identity['device_id_sha256_prefix']}`",
            f"- 解密主程序 SHA-256：`{identity['main_binary_sha256']}`", "",
            "各部分保留独立采集时点和原报告结论等级；同一主程序哈希不代表沙盒状态或运行事件同时发生。",
            ""]
    for number, source in enumerate(sources, 1):
        source_link = Path(os.path.relpath(source / "report.md", output)).as_posix()
        text += [f"## 第 {number} 部分：{source.name}", "",
                 f"来源：[已验证原报告]({source_link})。", "",
                 _linked_report(source, output).rstrip(), ""]
    return "\n".join(text).rstrip() + "\n"


def create_report_portfolio(reports: list[Path], output: Path) -> Path:
    if not 2 <= len(reports) <= 8:
        raise ValueError("combine 2–8 formal reports")
    sources = [report.resolve(strict=True) for report in reports]
    output = output.resolve()
    if (len(set(sources)) != len(sources) or
            any(output == source or output in source.parents or source in output.parents
                for source in sources)):
        raise ValueError("portfolio and source reports must be separate")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"portfolio output is not empty: {output}")
    identities = [_source_identity(source) for source in sources]
    if any(identity != identities[0] for identity in identities[1:]):
        raise ValueError("source reports use different device, App build or main binary")
    output.mkdir(parents=True, exist_ok=True)
    source_records = [{"path": str(source),
                       "report_index_sha256": sha256_file(source / "report-index.json"),
                       "report_sha256": sha256_file(source / "report.md"),
                       "analysis_index_sha256": _read(source / "report-index.json")
                       ["source_case_index_sha256"]}
                      for source in sources]
    record = {"schema_version": 1, "kind": "report_portfolio",
              "identity": identities[0], "reports": source_records}
    (output / "portfolio.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(_render(sources, output, identities[0]),
                                      encoding="utf-8")
    manifest = {"schema_version": 1, "kind": "report_portfolio",
                "status": "complete", "identity_sha256": hashlib.sha256(
                    json.dumps(identities[0], sort_keys=True).encode()).hexdigest(),
                "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                             for name in ("portfolio.json", "report.md")]}
    target = output / "manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    if not _verified(output):
        raise ValueError("new portfolio failed source verification")
    return target


def validate_report_portfolio(output: Path, manifest: dict) -> bool:
    try:
        record = _read(output / "portfolio.json")
        sources = [Path(item["path"]).resolve(strict=True) for item in record["reports"]]
        if (record.get("schema_version") != 1 or
                record.get("kind") != "report_portfolio" or
                manifest.get("status") != "complete" or
                not 2 <= len(sources) <= 8 or len(set(sources)) != len(sources) or
                any(output == source or output in source.parents or source in output.parents
                    for source in sources)):
            return False
        identities = [_source_identity(source) for source in sources]
        if any(identity != identities[0] for identity in identities[1:]):
            return False
        for source, saved in zip(sources, record["reports"]):
            if (saved.get("report_index_sha256") !=
                    sha256_file(source / "report-index.json") or
                    saved.get("report_sha256") != sha256_file(source / "report.md") or
                    saved.get("analysis_index_sha256") !=
                    _read(source / "report-index.json")["source_case_index_sha256"]):
                return False
        return (record.get("identity") == identities[0] and
                manifest.get("identity_sha256") == hashlib.sha256(
                    json.dumps(identities[0], sort_keys=True).encode()).hexdigest() and
                (output / "report.md").read_text(encoding="utf-8") ==
                _render(sources, output, identities[0]))
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
