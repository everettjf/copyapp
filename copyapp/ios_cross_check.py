"""Compare offline code bytes with a separately verified device recovery."""

from pathlib import Path

from copyapp.ios_analysis import _verified
from copyapp.ios_cases import read_json, require_separate_trees, seal_case, write_json
from copyapp.verify import sha256_file


def compare_recoveries(offline: dict, device: dict, package: dict) -> list[dict]:
    if (offline.get("status") != "complete" or offline.get("strategy") != "fairplay_offline" or
            offline.get("plaintext_validation") != "structural_only" or
            device.get("recovery_strategy") == "source_snapshot_unencrypted" or
            offline.get("bundle_id") != device.get("bundle_id") or
            package.get("bundle_id") != device.get("bundle_id") or
            not package.get("version") or not package.get("build") or
            package["version"] != device.get("installed_version") or
            package["build"] != device.get("installed_build")):
        raise ValueError("cross-check requires genuine recovery records with matching App version/build")
    left, right = offline.get("recovered_binaries"), device.get("recovered_binaries")
    if (not isinstance(left, list) or not left or not isinstance(right, list) or
            len({row["path"] for row in left}) != len(left) or
            len({row["path"] for row in right}) != len(right)):
        raise ValueError("cross-check needs complete distinct encrypted-binary inventories")
    other = {row["path"]: row for row in right}
    if {row["path"] for row in left} != set(other):
        raise ValueError("encrypted-binary inventories differ, including extension coverage")
    rows = []
    for row in left:
        peer = other[row["path"]]
        keys = ("uuid", "cryptoff", "cryptsize", "encrypted_sha256", "decrypted_sha256")
        if (not row.get("uuid") or not row.get("encrypted_sha256") or not row.get("decrypted_sha256") or
                any(row.get(key) != peer.get(key) for key in keys) or
                row.get("only_cryptid_and_encrypted_region_changed") is not True or
                peer.get("only_cryptid_and_encrypted_region_changed") is not True):
            raise ValueError("source binary identity or recovered bytes differ: " + row["path"])
        rows.append({"path": row["path"], **{key: row[key] for key in keys}})
    return rows


def recovery_links(offline: Path, device: Path) -> dict:
    offline, device = offline.resolve(strict=True), device.resolve(strict=True)
    om, dm = read_json(offline / "manifest.json"), read_json(device / "manifest.json")
    if (offline == device or om.get("kind") != "ios_offline_package" or
            dm.get("kind") != "decrypted_package" or dm.get("status") != "complete"):
        raise ValueError("provide separate offline and device decrypted-package cases")
    _verified(offline)
    _verified(device)
    package = read_json(offline / "source/package-index.json")
    original, recovered = read_json(offline / "offline.json"), read_json(device / "decryption.json")
    rows = compare_recoveries(original, recovered, package)
    return {"offline_case": str(offline), "offline_manifest_sha256": sha256_file(offline / "manifest.json"),
            "device_case": str(device), "device_manifest_sha256": sha256_file(device / "manifest.json"),
            "device_id_sha256_prefix": dm["device_id_sha256_prefix"],
            "bundle_id": package["bundle_id"], "version": package["version"], "build": package["build"],
            "result": "matches_device_recovery", "binaries": rows,
            "limitation": "Matches separately collected code bytes only. It does not establish current loaded-module "
                          "identity, simultaneous UI observations, semantic correctness or installability."}


def cross_check_offline(offline: Path, device: Path, output: Path) -> Path:
    for source in (offline, device):
        require_separate_trees(source, output)
    if output.exists():
        raise FileExistsError(output)
    result = recovery_links(offline, device)
    output.mkdir(parents=True)
    write_json(output / "comparison.json", result)
    (output / "report.md").write_text(
        "# Offline / device code cross-check\n\n"
        f"App: `{result['bundle_id']}`, version `{result['version']}`, build `{result['build']}`. "
        f"{len(result['binaries'])} encrypted program(s), including all recovered extensions, match in "
        "source encrypted bytes, Mach-O UUID, encryption span and recovered bytes.\n\n" + result["limitation"] + "\n",
        encoding="utf-8")
    seal_case(output, "ios_package_cross_check", status="matches_device_recovery",
              bundle_id=result["bundle_id"])
    return output / "report.md"


def validate_cross_check(root: Path, manifest: dict) -> bool:
    result = read_json(root / "comparison.json")
    return (manifest.get("status") == "matches_device_recovery" and
            manifest.get("bundle_id") == result["bundle_id"] and
            result == recovery_links(Path(result["offline_case"]), Path(result["device_case"])))
