import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.discovery_agent import run_discovery_agent, validate_discovery_agent


class DiscoveryAgentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.output = self.workspace / 'cases/agent-discovery'
        self.executable = self.workspace / 'fake-codex'
        self.executable.write_text('#!/bin/sh\nexit 0\n')
        self.scripts = []
        for index in range(3):
            script = self.output / 'discovery/playbooks' / f'flow-{index}.json'
            self.scripts.append(script)

    def launch(self, *, exit_code=0):
        owner = self

        class Process:
            stdin = io.BytesIO()
            returncode = exit_code

            def wait(self, timeout=None):
                if exit_code == 0:
                    manifest = owner.output / 'discovery/manifest.json'
                    manifest.parent.mkdir(parents=True, exist_ok=True)
                    manifest.write_text(json.dumps({'status': 'complete'}) + '\n')
                    for index, script in enumerate(owner.scripts):
                        script.parent.mkdir(parents=True, exist_ok=True)
                        script.write_text(json.dumps({'flow': index}) + '\n')
                return exit_code

            def poll(self):
                return exit_code

        with patch('copyapp.discovery_agent.subprocess.Popen', return_value=Process()), \
             patch('copyapp.discovery_agent.accepted_playbooks',
                   return_value=self.scripts), \
             patch('copyapp.discovery_agent.verify_case', return_value=True):
            return run_discovery_agent(
                'device-1', 'com.example.original', 'ios-mcp', self.output,
                workspace=self.workspace, executable=self.executable,
                timeout_seconds=30)

    def test_complete_case_pins_discovery_and_script_hashes(self):
        path, ready = self.launch()
        self.assertTrue(ready)
        record = json.loads(path.read_text())
        self.assertEqual(record['status'], 'complete')
        self.assertEqual(len(record['scripts']), 3)
        with patch('copyapp.discovery_agent.accepted_playbooks',
                   return_value=self.scripts), \
             patch('copyapp.discovery_agent.verify_case', return_value=True):
            self.assertTrue(validate_discovery_agent(self.output, record))
            self.scripts[0].write_text('{"flow": "changed"}\n')
            self.assertFalse(validate_discovery_agent(self.output, record))
            self.scripts[0].write_text('{"flow": 0}\n')
            (self.output / 'prompt.txt').write_text('changed prompt')
            self.assertFalse(validate_discovery_agent(self.output, record))

    def test_failed_run_is_not_replayed_on_resume(self):
        path, ready = self.launch(exit_code=1)
        self.assertFalse(ready)
        self.assertEqual(json.loads(path.read_text())['status'], 'needs_review')
        with patch('copyapp.discovery_agent.subprocess.Popen',
                   side_effect=AssertionError('must not replay')), \
             patch('copyapp.discovery_agent.verify_case', return_value=False):
            resumed_path, resumed = run_discovery_agent(
                'device-1', 'com.example.original', 'ios-mcp', self.output,
                workspace=self.workspace, executable=self.executable,
                timeout_seconds=30, resume=True)
        self.assertEqual(resumed_path, path)
        self.assertFalse(resumed)

    def test_zero_exit_without_device_discovery_is_rejected(self):
        self.executable.chmod(0o755)
        path, ready = run_discovery_agent(
            'device-1', 'com.example.original', 'ios-mcp', self.output,
            workspace=self.workspace, executable=self.executable,
            timeout_seconds=30)
        self.assertFalse(ready)
        record = json.loads(path.read_text())
        self.assertEqual(record['exit_code'], 0)
        self.assertEqual(record['status'], 'needs_review')
        self.assertIn('verified discovery missing', record['error'])


if __name__ == '__main__':
    unittest.main()
