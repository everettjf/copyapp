import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.discover_check import check_discovered_flows, inspect_playbook
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


class DiscoveryCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'discovery'
        self.scripts = []
        for n in range(3):
            path = self.root / f'flow-{n}.json'
            write(path, {'schema_version': 1, 'bundle_id': 'com.example.app',
                         'scenario_id': f'flow-{n}', 'fresh_launch': True,
                         'steps': [
                             {'action': 'observe', 'contains': ['Home']},
                             {'action': 'tap_label', 'label': f'Action {n}'},
                             {'action': 'screenshot', 'stable': True,
                              'ready_contains': f'Result {n}'}]})
            self.scripts.append(path)
        self.calls = []
        self.fail_first = False

    def replay(self, udid, backend, script, output):
        self.calls.append(script.name)
        plan = json.loads(script.read_text())
        output.mkdir(parents=True)
        (output / 'playbook.json').write_bytes(script.read_bytes())
        write(output / 'step-01-observe.json', {'elements': [{'text': 'Home'}]})
        Image.new('RGB', (20, 30), '#303030').save(output / 'step-03-screenshot.jpg')
        evidence = [{'path': name, 'sha256': sha256_file(output / name)}
                    for name in ('playbook.json', 'step-01-observe.json',
                                 'step-03-screenshot.jpg')]
        complete = not self.fail_first or len(self.calls) > 1
        steps = [
            {'action': 'observe', 'frontmost': 'com.example.app',
             'evidence_path': 'step-01-observe.json'},
            {'action': 'tap_label', 'frontmost': 'com.example.app',
             'result': {'ok': True}},
            {'action': 'screenshot', 'frontmost': 'com.example.app',
             'evidence_path': 'step-03-screenshot.jpg',
             'sha256': sha256_file(output / 'step-03-screenshot.jpg'),
             'stability': {'stable': True}, 'ready_found': True}]
        write(output / 'manifest.json', {
            'status': 'complete' if complete else 'failed',
            'bundle_id': 'com.example.app', 'ui_backend': backend,
            'device_id_sha256_prefix': hashlib.sha256(udid.encode()).hexdigest()[:16],
            'scenario_id': plan['scenario_id'], 'steps': steps,
            'evidence': evidence})
        return output / 'manifest.json', complete

    def run_check(self, resume=False):
        with patch('copyapp.discover_check.run_playbook', side_effect=self.replay):
            return check_discovered_flows(
                '00008020-1111111111111111', 'com.example.app',
                self.scripts, self.output, resume=resume)

    def test_accepts_distinct_device_replayed_flows_and_reuses_on_resume(self):
        manifest, complete = self.run_check()
        self.assertTrue(complete)
        self.assertTrue(verify_case(self.output))
        self.assertEqual(len(self.calls), 3)
        manifest, complete = self.run_check(resume=True)
        self.assertTrue(complete)
        self.assertEqual(len(self.calls), 3)

    def test_duplicate_actions_stop_before_phone(self):
        write(self.scripts[1], json.loads(self.scripts[0].read_text()) |
              {'scenario_id': 'unique-name'})
        with self.assertRaisesRegex(ValueError, 'duplicate scenario or action'):
            self.run_check()
        self.assertEqual(self.calls, [])

    def test_unready_final_screenshot_is_rejected_before_phone(self):
        plan = json.loads(self.scripts[0].read_text())
        plan['steps'][-1].pop('ready_contains')
        write(self.scripts[0], plan)
        with self.assertRaisesRegex(ValueError, 'ready final screenshot'):
            self.run_check()
        self.assertEqual(self.calls, [])

    def test_failed_tap_flow_is_not_replayed_on_resume(self):
        self.fail_first = True
        manifest, complete = self.run_check()
        self.assertFalse(complete)
        self.assertEqual(json.loads(manifest.read_text())['status'], 'needs_review')
        self.fail_first = False
        manifest, complete = self.run_check(resume=True)
        self.assertFalse(complete)
        self.assertEqual(len(self.calls), 1)

    def test_saved_success_rejects_mutated_source_script(self):
        self.run_check()
        plan = json.loads(self.scripts[0].read_text())
        plan['steps'][1]['label'] = 'Changed'
        write(self.scripts[0], plan)
        self.assertFalse(verify_case(self.output))


if __name__ == '__main__':
    unittest.main()
