import hashlib
import json
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.rea_function import _run_bounded, analyze_rea_function


class ReaFunctionTest(unittest.TestCase):
    def test_hash_mismatch_prevents_provider_launch(self):
        with tempfile.TemporaryDirectory() as root:
            binary = Path(root) / "app"
            binary.write_bytes(b"known fixture")
            with patch("copyapp.rea_function._run_bounded") as run:
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    analyze_rea_function(binary, "0" * 64, "0x1000", "ghidra",
                                         Path(root) / "out", Path(__file__), None, None)
                run.assert_not_called()

    def test_provider_identity_is_checked_before_saving_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            binary = Path(root) / "app"
            binary.write_bytes(b"known fixture")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            evidence = {
                "subject": {"digest": {"sha256": digest}},
                "provider": {"id": "hopper", "version": "test"},
                "evidence_id": "ev-test",
                "normalized_result": {"procedure": {"name": "f", "address": "0x1000"},
                                      "pseudocode": "void f() {}"},
            }
            run_result = subprocess.CompletedProcess([], 0, json.dumps(evidence).encode(), b"")
            output = Path(root) / "out"
            with patch("copyapp.rea_function.shutil.which", return_value="/bin/node"), patch(
                "copyapp.rea_function._run_bounded", return_value=run_result
            ):
                with self.assertRaisesRegex(RuntimeError, "identity"):
                    analyze_rea_function(binary, digest, "0x1000", "ghidra",
                                         output, Path(__file__), None, None)
            self.assertFalse((output / "evidence.json").exists())
            self.assertEqual(json.loads((output / "failure.json").read_text())["status"],
                             "identity_mismatch")

    def test_outer_timeout_sets_provider_startup_deadline(self):
        with tempfile.TemporaryDirectory() as root:
            binary = Path(root) / "app"
            binary.write_bytes(b"known fixture")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            for provider, setting in (
                ("ghidra", "REA_GHIDRA_STARTUP_TIMEOUT_MS"),
                ("hopper", "REA_HOPPER_STARTUP_TIMEOUT_MS"),
            ):
                with self.subTest(provider=provider), patch.dict(
                    "copyapp.rea_function.os.environ", {setting: ""}
                ), patch("copyapp.rea_function.shutil.which", return_value="/bin/node"), patch(
                    "copyapp.rea_function._run_bounded"
                ) as run:
                    run.return_value = subprocess.CompletedProcess([], 1, b"failure", b"")
                    with self.assertRaisesRegex(RuntimeError, "query failed"):
                        analyze_rea_function(binary, digest, "0x1000", provider,
                                             Path(root) / provider, Path(__file__),
                                             None, None, timeout=600)
                    self.assertEqual(run.call_args.args[2][setting], "585000")
                    self.assertEqual(run.call_args.args[1], 600)

    def test_explicit_provider_deadline_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            binary = Path(root) / "app"
            binary.write_bytes(b"known fixture")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            with patch.dict("copyapp.rea_function.os.environ",
                            {"REA_GHIDRA_STARTUP_TIMEOUT_MS": "120000"}), patch(
                "copyapp.rea_function.shutil.which", return_value="/bin/node"
            ), patch("copyapp.rea_function._run_bounded") as run:
                run.return_value = subprocess.CompletedProcess([], 1, b"failure", b"")
                with self.assertRaisesRegex(RuntimeError, "query failed"):
                    analyze_rea_function(binary, digest, "0x1000", "ghidra",
                                         Path(root) / "explicit", Path(__file__),
                                         None, None, timeout=600)
                self.assertEqual(run.call_args.args[2][
                    "REA_GHIDRA_STARTUP_TIMEOUT_MS"], "120000")

    def test_timeout_terminates_provider_process_group(self):
        class FakeProcess:
            pid = 12345
            returncode = -9
            calls = 0

            def communicate(self, timeout):
                self.calls += 1
                if self.calls < 3:
                    raise subprocess.TimeoutExpired(["node", "rea"], timeout)
                return b"", b""

        process = FakeProcess()
        with patch("copyapp.rea_function.subprocess.Popen", return_value=process) as popen, \
                patch("copyapp.rea_function.os.killpg") as killpg:
            with self.assertRaises(subprocess.TimeoutExpired):
                _run_bounded(["node", "rea"], 20, {"X": "Y"})
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(killpg.call_args_list[0].args, (12345, signal.SIGTERM))
        self.assertEqual(killpg.call_args_list[1].args, (12345, signal.SIGKILL))


if __name__ == "__main__":
    unittest.main()
