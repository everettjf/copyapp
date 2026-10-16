"""Link completed UI/Frida experiments to local Objective-C method addresses."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from copyapp.report import _validate_experiment, _validate_flow_capture
from copyapp.verify import sha256_file
from copyapp.objc import MachOImage


def _evidence(output: Path, path: Path, source: Path, records: list) -> None:
    target = output / path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    records.append({"path": str(path), "sha256": sha256_file(target)})


def _binding(method: dict, static_address: str, image_base: int, binary: Path) -> dict:
    """Compare a PAC-stripped runtime IMP's module offset with the static IMP."""
    expected = int(static_address, 16) - image_base
    result = {"static_offset": f"0x{expected:x}"}
    if not method.get("imp_stripped") and not method.get("module_offset"):
        result["status"] = "not_recorded"
        return result
    try:
        address = int(method["imp_stripped"], 16)
        base = int(method["module_base"], 16)
        offset = int(method["module_offset"], 16)
        module_path = str(method["module_path"])
        same_module = module_path.endswith("/" + binary.parent.name + "/" + binary.name)
        valid = offset >= 0 and address - base == offset and offset == expected and same_module
    except (KeyError, TypeError, ValueError):
        valid = False
    result["status"] = "offset_match" if valid else "mismatch"
    result["runtime_module_path"] = method.get("module_path")
    result["runtime_module_offset"] = method.get("module_offset")
    result["limitation"] = "A module/offset comparison does not prove that loaded code bytes equal the acquired file or exclude runtime patching."
    return result


def _static_binding(record: dict, index: int, static_address: str,
                    image_base: int, binary: Path, digest: str) -> Optional[dict]:
    entries = record.get("static_entries")
    if entries is None:
        return None
    counts = record.get("static_call_counts")
    offsets = record.get("static_requested_offsets")
    if (record.get("static_binary_sha256") != digest or
            not isinstance(entries, list) or not isinstance(counts, list) or
            not isinstance(offsets, list) or len(entries) != len(record["methods"]) or
            len(counts) != len(entries) or len(offsets) != len(entries)):
        raise ValueError("static experiment metadata is incomplete or belongs to another binary")
    entry = entries[index]
    expected = int(static_address, 16) - image_base
    method = record["methods"][index]
    try:
        address = int(entry["address"], 16)
        base = int(entry["module_base"], 16)
        offset = int(entry["module_offset"], 16)
        path = str(entry["module_path"])
        valid = (entry["status"] == "hooked" and entry["index"] == index and
                 entry["class"] == method["class"] and entry["selector"] == method["selector"] and
                 counts[index] >= 0 and type(counts[index]) is int and
                 int(offsets[index], 16) == expected == offset and
                 address - base == offset and
                 path.endswith("/" + binary.parent.name + "/" + binary.name))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("static entry does not match selected binary's method and loaded app module")
    return {"status": "direct_static_entry", "calls": counts[index],
            "runtime_address": entry["address"], "runtime_module_path": path,
            "runtime_module_offset": entry["module_offset"],
            "limitation": "Matching path and offset plus acquired-file hash do not prove loaded code bytes are identical."}


def build_candidates(udid: str, bundle: str, binary: Path, objc_index: Path,
                     experiments: List[Path], output: Path) -> Tuple[Path, bool]:
    if not 1 <= len(experiments) <= 16:
        raise ValueError("provide 1–16 completed experiments")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite candidates: {output}")
    binary = binary.resolve(strict=True)
    static = json.loads(objc_index.read_text(encoding="utf-8"))
    if (static.get("schema_version") != 1 or not isinstance(static.get("classes"), list) or
            static.get("binary_sha256") != sha256_file(binary)):
        raise ValueError("Objective-C index does not match the selected binary")
    image_base = MachOImage(binary.read_bytes()).base
    if image_base is None or (static.get("image_base") is not None and
                              int(static["image_base"], 16) != image_base):
        raise ValueError("Objective-C index image base does not match the selected binary")
    device_prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    records = []
    sources = []
    for directory in experiments:
        if (directory / "playbook").is_dir() and (directory / "view-tree").is_dir():
            flow = _validate_flow_capture(directory, bundle, device_prefix,
                                          {static["binary_sha256"]})
            trace = flow.get("trace")
            if trace is None:
                raise ValueError(f"flow has no method trace: {directory}")
            source_index = len(sources) + 1
            sources.append({"kind": "flow_capture", "path": directory,
                            "files": flow["files"]})
            for step in trace["steps"]:
                observation = dict(trace)
                observation["call_counts"] = step["call_counts"]
                observation["static_call_counts"] = step["static_call_counts"]
                records.append({"record": observation, "source_index": source_index,
                                "step_index": step["index"], "action": step["action"]})
        else:
            record = _validate_experiment(directory, bundle, device_prefix)
            if record.get("frontmost_after") != bundle:
                raise ValueError(f"target left foreground during experiment: {directory}")
            source_index = len(sources) + 1
            sources.append({"kind": "experiment", "path": directory})
            records.append({"record": record, "source_index": source_index})
    addresses: Dict[Tuple[str, str], dict] = {}
    for cls in static["classes"]:
        # trace_script resolves class_getInstanceMethod, never metaclass methods.
        for method in cls.get("instance_methods", []):
            key = (cls["name"], method["selector"])
            addresses.setdefault(key, {"address": method["imp"],
                                       "method_kind": "instance_methods"})
    found: Dict[Tuple[str, str], dict] = {}
    unresolved = []
    conflicts = set()
    for experiment_index, source in enumerate(records, 1):
        record = source["record"]
        for method_index, (method, count) in enumerate(zip(record["methods"], record["call_counts"])):
            key = (method["class"], method["selector"])
            match = addresses.get(key)
            if match is not None:
                static_binding = _static_binding(record, method_index, match["address"],
                                                 image_base, binary, static["binary_sha256"])
            else:
                static_binding = None
            static_calls = static_binding["calls"] if static_binding else 0
            if count == 0 and static_calls == 0:
                continue
            if match is None:
                unresolved.append({"experiment": experiment_index,
                                   "source": source["source_index"],
                                   **({"step_index": source["step_index"]} if "step_index" in source else {}),
                                   "class": key[0], "selector": key[1], "calls": count,
                                   "reason": "not in this binary's local Objective-C index; may be in a framework or replaced at runtime"})
                continue
            binding = _binding(method, match["address"], image_base, binary)
            if binding["status"] == "mismatch" and static_calls == 0:
                conflicts.add(key)
                unresolved.append({"experiment": experiment_index,
                                   "source": source["source_index"],
                                   **({"step_index": source["step_index"]} if "step_index" in source else {}),
                                   "class": key[0], "selector": key[1], "calls": count,
                                   "reason": "runtime IMP module/offset does not match this binary's static method",
                                   "binding": binding})
                continue
            item = found.setdefault(key, {
                "class": key[0], "selector": key[1],
                "static_address": match["address"], "method_kind": match["method_kind"],
                "binary_sha256": static["binary_sha256"], "observations": [],
                "limitation": "Runtime-to-static identity uses class/selector plus either a matching current IMP offset or a separately hooked app entry. Loaded code bytes and absence of runtime patching remain unverified.",
            })
            item["observations"].append({"experiment": experiment_index,
                                         "source": source["source_index"],
                                         **({"step_index": source["step_index"],
                                             "action": source["action"]}
                                            if "step_index" in source else {}),
                                         "calls": count, "runtime_imp": method.get("imp"),
                                         "binding": binding,
                                         **({"static_entry": static_binding} if static_binding else {})})
    for key in conflicts:
        found.pop(key, None)
    candidates = sorted(found.values(), key=lambda item: (item["class"], item["selector"]))
    output.mkdir(parents=True)
    evidence = []
    _evidence(output, Path("sources/objc-index.json"), objc_index, evidence)
    for index, source in enumerate(sources, 1):
        directory = source["path"]
        if source["kind"] == "experiment":
            for name in ("experiment.json", "before.jpg", "after.jpg"):
                _evidence(output, Path(f"sources/experiment-{index:02d}/{name}"),
                          directory / name, evidence)
        else:
            for name in source["files"]:
                _evidence(output, Path(f"sources/flow-{index:02d}/{name}"),
                          directory / name, evidence)
    summary: Dict[str, Any] = {
        "schema_version": 1, "kind": "runtime_static_candidates", "bundle_id": bundle,
        "device_id_sha256_prefix": device_prefix, "binary_path": str(binary),
        "binary_sha256": static["binary_sha256"], "image_base": f"0x{image_base:x}",
        "experiment_count": len(sources), "observation_count": len(records),
        "sources": [{"index": index, "kind": source["kind"]}
                    for index, source in enumerate(sources, 1)],
        "candidates": candidates, "unresolved": unresolved,
        "scope": "Observed nonzero Frida call counts linked to one selected binary by Objective-C class/selector and a matching current IMP offset or separately hooked static app entry. These are candidate addresses for optional decompilation, not causal proof or original source.",
    }
    summary_path = output / "candidates.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence.append({"path": "candidates.json", "sha256": sha256_file(summary_path)})
    lines = ["# 运行时 → 静态函数候选", "",
             f"- App：`{bundle}`", f"- 二进制 SHA-256：`{static['binary_sha256']}`",
             f"- 已验证来源：{len(sources)}；点击观测：{len(records)}；候选函数：{len(candidates)}；未匹配观测：{len(unresolved)}", "",
             "| 类 | 方法 | 静态地址 | 当前入口 / 静态入口命中 |", "| --- | --- | --- | ---: |"]
    for item in candidates:
        current = sum(observation["calls"] for observation in item["observations"])
        direct = sum((observation.get("static_entry") or {}).get("calls", 0)
                     for observation in item["observations"])
        lines.append(f"| `{item['class']}` | `{item['selector']}` | `{item['static_address']}` | {current} / {direct} |")
    lines += ["", "新实验核对去除指针认证后的当前 IMP；提供精确二进制和 Objective-C 索引时，还可直接挂钩 App 静态入口。系统框架替换当前 IMP 时保留冲突证据，并用独立的静态入口命中确认该地址执行。模块路径和偏移仍不能证明内存代码字节与采集文件一致。", ""]
    report_path = output / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    evidence.append({"path": "report.md", "sha256": sha256_file(report_path)})
    manifest = {"schema_version": 1, "kind": "runtime_static_candidates", "evidence": evidence}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return summary_path, bool(candidates)
