"""Portable, bounded .app inventory with explicit architecture and platform facts."""

import hashlib
import json
import os
import plistlib
import shutil
import stat
import struct
from pathlib import Path, PurePosixPath

from copyapp.ipa import ARM64_CPU, MAX_BINARY, _slice_macho, inspect_macho
from copyapp.macos.case import Case, canonical, digest


MAX_ENTRIES = 40000
MAX_BYTES = 8 * 1024 ** 3


def inventory(app: Path) -> list:
    root = app.resolve(strict=True)
    entries = []
    total = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            row = {"path": relative, "mode": stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                if (os.path.isabs(target) or root not in path.resolve(strict=True).parents):
                    raise ValueError("non-portable or escaping bundle symlink: " + relative)
                row.update(kind="symlink", target=target)
            elif stat.S_ISDIR(info.st_mode):
                row.update(kind="directory")
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                if total > MAX_BYTES:
                    raise ValueError("app package exceeds acquisition size limit")
                row.update(kind="file", size=info.st_size, sha256=digest(path))
                after = path.stat()
                if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                    raise ValueError("bundle changed during inventory: " + relative)
            else:
                raise ValueError("unsupported bundle entry: " + relative)
            entries.append(row)
            if len(entries) > MAX_ENTRIES:
                raise ValueError("bundle entry count exceeds limit")
    return sorted(entries, key=lambda item: item["path"])


def app_facts(app: Path) -> dict:
    info_path = app / "Contents/Info.plist"
    if info_path.stat().st_size > 1024 * 1024:
        raise ValueError("oversized bundle Info.plist")
    info = plistlib.loads(info_path.read_bytes())
    bundle = info.get("CFBundleIdentifier")
    executable = info.get("CFBundleExecutable")
    if (not isinstance(bundle, str) or not bundle or
            not isinstance(executable, str) or not executable or
            Path(executable).name != executable or executable in {".", ".."} or
            info.get("CFBundlePackageType") != "APPL"):
        raise ValueError("invalid macOS application identity")
    relative = "Contents/MacOS/" + executable
    binary = app / relative
    if binary.stat().st_size > MAX_BINARY:
        raise ValueError("main executable exceeds bounded Mach-O inspection limit")
    data = binary.read_bytes()
    facts = inspect_macho(data)
    if facts["cpu_type"] != ARM64_CPU:
        raise ValueError("initial macOS scope requires an arm64 executable")
    body = _slice_macho(data)
    count, size = struct.unpack_from("<II", body, 16)
    cursor = 32
    platforms = set()
    for _ in range(count):
        command, length = struct.unpack_from("<II", body, cursor)
        if command == 0x32 and length >= 24:  # LC_BUILD_VERSION
            platforms.add(struct.unpack_from("<I", body, cursor + 8)[0])
        elif command == 0x24:  # LC_VERSION_MIN_MACOSX
            platforms.add(1)
        cursor += length
    if platforms != {1}:
        raise ValueError("executable does not declare the macOS platform")
    return {"bundle_id": bundle, "version": str(info.get("CFBundleShortVersionString", "")),
            "build": str(info.get("CFBundleVersion", "")), "executable": relative,
            "binary_sha256": hashlib.sha256(data).hexdigest(),
            "arm64_sha256": hashlib.sha256(body).hexdigest(), "platform": "macos",
            "architecture": "arm64", "macho": facts}


def snapshot_bundle(source: Path, target: Path, entries: list):
    """Copy bytes, permissions and links, not protected system filesystem flags.

    shutil.copytree/copystat attempts to copy the system app's restricted flags
    onto the research copy. Those flags are not package contents or code-signing
    bytes, and can make the copy unwritable before it is complete. Never alter
    the installed original to work around that failure.
    """
    target.mkdir(parents=True)
    directories = [row for row in entries if row["kind"] == "directory"]
    for row in sorted(directories, key=lambda item: len(PurePosixPath(item["path"]).parts)):
        (target / row["path"]).mkdir()
    for row in entries:
        path = target / row["path"]
        if row["kind"] == "file":
            shutil.copyfile(source / row["path"], path)
            path.chmod(row["mode"])
        elif row["kind"] == "symlink":
            path.symlink_to(row["target"])
    for row in reversed(sorted(directories, key=lambda item: len(PurePosixPath(item["path"]).parts))):
        (target / row["path"]).chmod(row["mode"])


def index_app(source: Path, output: Path) -> Path:
    if source.is_symlink() or source.suffix != ".app" or not source.is_dir():
        raise ValueError("source must be a real .app directory")
    source = source.resolve()
    if output.resolve() == source or source in output.resolve().parents:
        raise ValueError("case must be outside the source app")
    before = inventory(source)
    app_facts(source)  # Reject unsupported platforms before copying.
    case = Case(output, "mac_app_index")
    try:
        snapshot = case.root / "app/" / source.name
        snapshot_bundle(source, snapshot, before)
        saved = inventory(snapshot)
        if saved != before or inventory(source) != before:
            raise ValueError("app changed during snapshot; preserve failed attempt and retry separately")
        facts = app_facts(snapshot)
        case.add("app-index.json", {"schema_version": 2, "platform": "macos",
                                   "scope": "static_package_only", "source_path": str(source),
                                   "snapshot_path": snapshot.relative_to(case.root).as_posix(),
                                   "app": facts, "entries": saved,
                                   "package_sha256": hashlib.sha256(canonical(saved)).hexdigest()})
        # Complete inventory validation below binds every copied entry, including links.
        case.finish("complete", scope="static_package_only", bundle_id=facts["bundle_id"])
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="static_package_only")
        raise


def validate_index(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import checked_path
    if (manifest["status"] != "complete" or manifest.get("scope") != "static_package_only" or
            "app-index.json" not in names):
        return False
    index = json.loads((root / "app-index.json").read_text())
    name = index["snapshot_path"]
    parts = PurePosixPath(name).parts
    if (len(parts) != 2 or parts[0] != "app" or not parts[1].endswith(".app") or
            index.get("schema_version") != 2 or index.get("platform") != "macos" or
            index.get("scope") != "static_package_only"):
        return False
    snapshot = checked_path(root, name)
    entries = inventory(snapshot)
    return (entries == index["entries"] and app_facts(snapshot) == index["app"] and
            manifest["bundle_id"] == index["app"]["bundle_id"] and
            hashlib.sha256(canonical(entries)).hexdigest() == index["package_sha256"])
