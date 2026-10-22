"""Static ZIP/DMG import. Applications and package installers are never run."""

import fcntl
import hashlib
import os
import platform
import plistlib
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
import zlib
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.package import MAX_BYTES, MAX_ENTRIES, app_facts, index_app, inventory
from copyapp.macos.report import read


def member_path(value: str) -> str:
    if (not isinstance(value, str) or not value or "\0" in value or "\\" in value or
            PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts or
            str(PurePosixPath(value)) != value or value == "." or
            any(len(part.encode("utf-8")) > 255 for part in PurePosixPath(value).parts)):
        raise ValueError("distribution member must be a canonical relative path")
    return value


def zip_model(archive: zipfile.ZipFile) -> tuple:
    infos, rows, spellings = {}, {}, {}
    total = 0
    members = archive.infolist()
    if not 1 <= len(members) <= MAX_ENTRIES:
        raise ValueError("ZIP entry count exceeds the bound")
    for info in members:
        if "\0" in info.orig_filename or info.flag_bits & 1:
            raise ValueError("encrypted or NUL-containing ZIP members are unsupported")
        name = member_path(info.filename[:-1] if info.is_dir() else info.filename)
        if name in infos:
            raise ValueError("duplicate ZIP member")
        for length in range(1, len(PurePosixPath(name).parts) + 1):
            prefix = "/".join(PurePosixPath(name).parts[:length])
            folded = unicodedata.normalize("NFC", prefix).casefold()
            if folded in spellings and spellings[folded] != prefix:
                raise ValueError("ZIP case or Unicode-normalization collision")
            spellings[folded] = prefix
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if mode & 0o7000 or kind not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
            raise ValueError("special ZIP file modes are unsupported")
        if (kind == stat.S_IFDIR and not info.is_dir()) or (info.is_dir() and kind not in {0, stat.S_IFDIR}):
            raise ValueError("inconsistent ZIP directory type")
        row = {"path": name, "mode": stat.S_IMODE(mode) or (0o755 if info.is_dir() else 0o644)}
        if info.is_dir():
            row["kind"] = "directory"
        elif kind == stat.S_IFLNK:
            if info.file_size > 4096:
                raise ValueError("oversized ZIP symlink")
            target = archive.read(info).decode("utf-8")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if not target or "\0" in target or target.startswith("/") or resolved == ".." or resolved.startswith("../"):
                raise ValueError("ZIP symlink escapes its extraction root")
            row.update(kind="symlink", target=target)
        else:
            total += info.file_size
            if total > MAX_BYTES:
                raise ValueError("uncompressed ZIP exceeds the 8 GiB bound")
            row.update(kind="file", size=info.file_size)
        infos[name], rows[name] = info, row
    for name in list(rows):
        for parent in PurePosixPath(name).parents:
            if str(parent) == ".": continue
            prefix = str(parent)
            if prefix in rows and rows[prefix]["kind"] != "directory":
                raise ValueError("ZIP member has a non-directory ancestor")
            rows.setdefault(prefix, {"path": prefix, "kind": "directory", "mode": 0o755})
    if len(rows) > MAX_ENTRIES:
        raise ValueError("ZIP including implicit directories exceeds the entry bound")
    return infos, rows, total


def zip_bytes(archive, info, destination=None) -> str:
    sha, count, deadline = hashlib.sha256(), 0, time.monotonic() + 300
    stream = destination.open("xb") if destination is not None else None
    try:
        with archive.open(info) as source:
            while True:
                chunk = source.read(1 << 20)
                if not chunk: break
                count += len(chunk)
                if count > info.file_size or count > MAX_BYTES or time.monotonic() > deadline:
                    raise ValueError("ZIP member exceeded its declared size or reading deadline")
                sha.update(chunk)
                if stream is not None: stream.write(chunk)
        if count != info.file_size:
            raise ValueError("ZIP member size differs from its declaration")
        return sha.hexdigest()
    finally:
        if stream is not None: stream.close()


def extract_zip(source: Path, output: Path):
    with zipfile.ZipFile(source) as archive:
        infos, rows, total = zip_model(archive)
        if shutil.disk_usage(output.parent).free < total * 2 + (512 << 20):
            raise ValueError("insufficient space for ZIP extraction and package snapshot")
        output.mkdir()
        directories = sorted((row for row in rows.values() if row["kind"] == "directory"),
                             key=lambda row: len(PurePosixPath(row["path"]).parts))
        for row in directories: (output / row["path"]).mkdir()
        for name, row in rows.items():
            path = output / name
            if row["kind"] == "file":
                zip_bytes(archive, infos[name], path)
                path.chmod(row["mode"])
        for name, row in rows.items():
            if row["kind"] == "symlink": (output / name).symlink_to(row["target"])
        inventory(output)  # Reject dangling or chained escaping links before App selection.
        for row in reversed(directories): (output / row["path"]).chmod(row["mode"])


def candidates(root: Path) -> list:
    result, pending, visited = [], [root], 0
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            visited += 1
            if visited > MAX_ENTRIES:
                raise ValueError("distribution search exceeds the entry bound")
            if path.is_symlink() or not path.is_dir() or path.name in {"__MACOSX", ".Trashes", ".Spotlight-V100", ".fseventsd"}:
                continue
            if path.suffix == ".app":
                result.append(path.relative_to(root).as_posix())
            else:
                pending.append(path)
    return sorted(result)


def select(root: Path, selection=None) -> str:
    choices = candidates(root)
    if selection is not None:
        member_path(selection)
        if selection not in choices:
            raise ValueError("requested .app is not a distribution candidate: " + ", ".join(choices))
        return selection
    if len(choices) != 1:
        raise ValueError("select one explicit --app-relative candidate: " + ", ".join(choices))
    return choices[0]


def normalized(rows: list) -> list:
    return sorted([{**row, "path": unicodedata.normalize("NFC", row["path"])} for row in rows], key=lambda row: row["path"])


def zip_package(source: Path, selection: str) -> list:
    with zipfile.ZipFile(source) as archive:
        infos, rows, _ = zip_model(archive)
        if selection not in rows or rows[selection]["kind"] != "directory" or not selection.endswith(".app"):
            raise ValueError("selected App is absent from ZIP")
        result = []
        for name, row in rows.items():
            if name.startswith(selection + "/"):
                row = dict(row, path=name[len(selection) + 1:])
                if row["kind"] == "file": row["sha256"] = zip_bytes(archive, infos[name])
                result.append(row)
        return normalized(result)


def native(argv: list, logs: list, timeout=60) -> bytes:
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        truncated = len(result.stdout) > 16 << 20 or len(result.stderr) > 16 << 20
        logs.append({"argv": argv, "returncode": result.returncode,
                     "stdout": result.stdout[:16 << 20].decode("utf-8", errors="replace"),
                     "stderr": result.stderr[:16 << 20].decode("utf-8", errors="replace"), "output_truncated": truncated})
        if truncated:
            raise RuntimeError("disk-image command output exceeds its bound")
        if result.returncode:
            raise RuntimeError("disk-image command failed: " + result.stderr.decode("utf-8", errors="replace")[-1000:])
        return result.stdout
    except subprocess.TimeoutExpired as exc:
        logs.append({"argv": argv, "returncode": None, "error": "timeout"})
        raise RuntimeError("disk-image operation timed out; inspect the recorded cleanup outcome") from exc


def attached(image: Path) -> list:
    raw = subprocess.run(["/usr/bin/hdiutil", "info", "-plist"], stdin=subprocess.DEVNULL,
                         capture_output=True, timeout=30, check=True)
    return [entry for entry in plistlib.loads(raw.stdout).get("images", [])
            if Path(entry.get("image-path", "/absent")).resolve() == image.resolve()]


@contextmanager
def mount_image(image: Path, mount: Path, logs: list):
    if platform.system() != "Darwin" or int(platform.mac_ver()[0].split(".")[0]) < 27:
        raise ValueError("DMG import/reverification currently requires macOS 27 or later's diskutil image interface")
    lock_path = Path(tempfile.gettempdir()) / ("copyapp-image-" + hashlib.sha256(str(image.resolve()).encode()).hexdigest() + ".lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if attached(image):
            raise ValueError("this exact snapshot is already attached; inspect it instead of reusing an unknown mount")
        info = plistlib.loads(native(["/usr/bin/hdiutil", "imageinfo", "-stdinpass", "-plist", str(image)], logs))
        properties = info.get("Properties", {})
        if properties.get("Encrypted") is not False or properties.get("Software License Agreement") is not False:
            raise ValueError("encrypted or license-interactive DMGs are unsupported; no password or agreement is submitted")
        try:
            raw = native(["/usr/sbin/diskutil", "image", "attach", "--stdinpassphrase", "--plist", "--readOnly", "--nobrowse",
                          "--mountPoint", str(mount), "--mountOptions", "noexec,nosuid,nodev", str(image)], logs)
            entities = plistlib.loads(raw)["system-entities"]
            mounts = [entry for entry in entities if "mount-point" in entry]
            if len(mounts) != 1 or Path(mounts[0]["mount-point"]).resolve() != mount.resolve() or not os.path.ismount(mount):
                raise ValueError("image did not produce the single requested owned mount")
            all_mounts = subprocess.check_output(["/sbin/mount"], text=True, timeout=30)
            matching = []
            for line in all_mounts.splitlines():
                parsed = re.fullmatch(r"/dev/disk[0-9]+(?:s[0-9]+)* on (.+) \((.*)\)", line)
                if parsed and Path(parsed[1]).resolve() == mount.resolve():
                    matching.append(line)
            if len(matching) != 1:
                raise ValueError("cannot bind native mount policy to the owned path")
            flags = matching[0].rsplit(" (", 1)[1].rstrip(")").split(", ")
            if not {"read-only", "noexec", "nosuid", "nodev", "nobrowse"}.issubset(flags):
                raise ValueError("native image mount did not retain the requested restrictions")
            logs.append({"mount_policy": matching[0]})
            yield mount
        finally:
            # Reconcile even a timed-out/failed attach by its unique snapshot
            # path. Never guess a disk number or force-eject an unrelated disk.
            primary_failure = sys.exc_info()[0] is not None
            try:
                owned = attached(image)
                if len(owned) > 1:
                    raise RuntimeError("multiple image associations need manual cleanup review")
                if owned:
                    devices = [row["dev-entry"] for row in owned[0].get("system-entities", [])
                               if re.fullmatch(r"/dev/disk[0-9]+", row.get("dev-entry", ""))]
                    if not devices:
                        raise RuntimeError("owned image has no safely identified whole-device cleanup target")
                    target = str(mount) if os.path.ismount(mount) else devices[0]
                    native(["/usr/sbin/diskutil", "eject", target], logs)
                if attached(image) or os.path.ismount(mount):
                    raise RuntimeError("owned image cleanup did not complete")
            except BaseException as cleanup:
                logs.append({"cleanup_error": type(cleanup).__name__, "message": str(cleanup)})
                if not primary_failure: raise


def import_app(source: Path, output: Path, selection=None) -> Path:
    if source.is_symlink() or not source.is_file() or source.suffix.lower() not in {".zip", ".dmg"} or source.stat().st_size > MAX_BYTES:
        raise ValueError("import requires a bounded regular .zip or .dmg; use mac inspect for a .app")
    source = source.resolve(strict=True)
    before = source.stat()
    source_hash = digest(source)
    case = Case(output, "mac_distribution")
    kind, logs = source.suffix.lower()[1:], []
    try:
        snapshot = case.root / ("source." + kind)
        shutil.copyfile(source, snapshot)
        case.record(snapshot.name)
        after = source.stat()
        if (digest(snapshot) != source_hash or digest(source) != source_hash or
                (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError("distribution changed during snapshot")
        if kind == "zip":
            extract_zip(snapshot, case.root / "extracted")
            chosen = select(case.root / "extracted", selection)
            package = index_app(case.root / "extracted" / chosen, case.root / "package")
            if normalized(read(package, "app-index.json")["entries"]) != zip_package(snapshot, chosen):
                raise ValueError("extracted App differs from its ZIP members")
        else:
            with mount_image(snapshot, case.root / "mount", logs) as mounted:
                chosen = select(mounted, selection)
                package = index_app(mounted / chosen, case.root / "package")
        case.record("package/manifest.json")
        case.add("native-log.json", logs)
        index = read(package, "app-index.json")
        case.add("import.json", {"schema_version": 2, "platform": "macos", "scope": "static_distribution_only", "format": kind,
                                 "source_path": str(source), "source_sha256": source_hash, "selection": chosen,
                                 "package_manifest_sha256": digest(package / "manifest.json"), "package_sha256": index["package_sha256"],
                                 "app": index["app"], "launched": False, "installed": False,
                                 "host_os": platform.mac_ver()[0],
                                 "disk_tools": {path: digest(Path(path)) for path in ("/usr/bin/hdiutil", "/usr/sbin/diskutil")} if kind == "dmg" else {}})
        case.finish("complete", scope="static_distribution_only")
        from copyapp.verify import verify_case
        if not verify_case(case.root):
            raise ValueError("distribution provenance failed source revalidation")
        return case.root
    except BaseException as exc:
        if not (case.root / "native-log.json").exists(): case.add("native-log.json", logs)
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="static_distribution_only")
        raise


def validate_import(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    if (manifest.get("status") != "complete" or manifest.get("scope") != "static_distribution_only" or
            not {"import.json", "native-log.json", "package/manifest.json"}.issubset(names) or
            not verify_case(root / "package") or read(root / "package", "manifest.json").get("kind") != "mac_app_index"):
        return False
    record, package = read(root, "import.json"), read(root / "package", "app-index.json")
    kind = record["format"]
    if (kind not in {"zip", "dmg"} or "source." + kind not in names or (root / ("source." + kind)).stat().st_size > MAX_BYTES or
            type(record.get("schema_version")) is not int or record["schema_version"] != 2 or record.get("platform") != "macos" or
            record.get("scope") != "static_distribution_only" or record.get("launched") is not False or record.get("installed") is not False or
            record.get("source_sha256") != digest(root / ("source." + kind)) or
            record.get("package_manifest_sha256") != digest(root / "package/manifest.json") or record.get("package_sha256") != package["package_sha256"] or
            canonical(record.get("app")) != canonical(package["app"])):
        return False
    if (not isinstance(record.get("source_path"), str) or not Path(record["source_path"]).is_absolute() or
            not isinstance(record.get("host_os"), str)):
        return False
    member_path(record["selection"])
    if kind == "zip":
        try:
            return (record.get("disk_tools") == {} and read(root, "native-log.json") == [] and
                    zip_package(root / "source.zip", record["selection"]) == normalized(package["entries"]))
        except (zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError, zlib.error):
            return False
    logs = read(root, "native-log.json")
    tools = record.get("disk_tools")
    if (not isinstance(tools, dict) or set(tools) != {"/usr/bin/hdiutil", "/usr/sbin/diskutil"} or
            any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in tools.values())):
        return False
    if (not isinstance(logs, list) or not logs or not any("mount_policy" in row for row in logs) or
            any(row.get("returncode", 0) != 0 or row.get("output_truncated", False) or "cleanup_error" in row for row in logs)):
        return False
    folder = Path(tempfile.mkdtemp(prefix="copyapp-dmg-verify-")).resolve()
    verification_log = []
    try:
        with mount_image(root / "source.dmg", folder / "mount", verification_log) as mounted:
            chosen = select(mounted, record["selection"])
            return (normalized(inventory(mounted / chosen)) == normalized(package["entries"]) and
                    canonical(app_facts(mounted / chosen)) == canonical(package["app"]))
    except (RuntimeError, subprocess.SubprocessError):
        return False
    finally:
        if os.path.ismount(folder / "mount"):
            # Do not let TemporaryDirectory/rmtree traverse a mount after a
            # cleanup failure, even if the filesystem policy was unexpected.
            (folder / "verification-failure.json").write_bytes(canonical({"source": str(root / "source.dmg"),
                                                                         "native_log": verification_log,
                                                                         "left_mounted": True}))
            print("DMG verification left an owned mount; inspect " + str(folder / "verification-failure.json"), file=sys.stderr)
        else:
            shutil.rmtree(folder)
