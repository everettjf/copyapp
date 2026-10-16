import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.copy_workflow import copy_app, validate_copy_workflow
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


class CopyWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'cases/copy'
        self.project = self.root / 'rebuild/Clone'
        self.script = self.root / 'playbook.json'
        write(self.script, {'bundle_id': 'com.example.original'})
        self.executable = self.root / 'fake-codex'
        self.executable.write_text('#!/bin/sh\nexit 0\n')
        self.executable.chmod(0o755)
        self.calls = []
        self.fail_analysis = False
        self.bad_report = False

    async def survey(self, *args):
        return 0

    async def prepare(self, udid, bundle, scripts, output, survey, **kwargs):
        self.calls.append('prepare')
        write(output / 'manifest.json', {
            'status': 'needs_semantic_review', 'bundle_id': bundle,
            'device_id_sha256_prefix': hashlib.sha256(udid.encode()).hexdigest()[:16],
            'scripts': [{'path': str(path), 'sha256': sha256_file(path)}
                        for path in scripts],
            'rebuilt_bundle_id': kwargs['rebuilt_bundle_id'],
            'provider': kwargs['provider'], 'ui_backend': kwargs['ui_backend'],
            'investigation_backend': kwargs['backend'], 'decrypt': kwargs['decrypt'],
            'network_requested': kwargs['network'],
            'decrypt_helper': str(kwargs['decrypt_helper'].resolve()),
            'ssh_port': kwargs['ssh_port'], 'ssh_user': kwargs['ssh_user'],
            'ssh_identity': str(kwargs['ssh_identity'].resolve()),
            'ssh_known_hosts': str(kwargs['ssh_known_hosts'].resolve()),
            'ghidra_dir': None, 'java_home': None, 'disabled_analyzer': None,
            'timeout': kwargs['timeout'],
        })
        write(output / 'preparation/draft/task.json', {'kind': 'agent_semantic_review_task'})
        return output / 'manifest.json', True

    def agent(self, task, output, *args, **kwargs):
        if kwargs.get('verify_analysis'):
            self.calls.append('analysis-agent')
            output.mkdir(parents=True)
            write(output / 'run.json', {'status': 'agent_exited_unverified',
                                        'provider': args[0],
                                        'task_case': str(task)})
            write(output / 'manifest.json', {'kind': 'agent_execution'})
            if self.fail_analysis:
                return output / 'run.json', False
            report = output / 'reviewed-report'
            write(report / 'report-index.json', {'kind': 'report'})
            write(report / 'feature-spec.json', {
                'target_bundle_id': 'com.example.original',
                'rebuilt_bundle_id': ('com.example.wrong' if self.bad_report
                                      else 'com.example.clone'),
                'flows': [{'id': 'one'}],
            })
            delivery = output / 'analysis-delivery'
            write(delivery / 'manifest.json', {'kind': 'analysis_delivery'})
            write(output / 'analysis-verification.json', {
                'status': 'source_linked_report_ready_for_review',
                'report_case': str(report), 'analysis_delivery_case': str(delivery),
                'analysis_delivery_manifest_sha256': sha256_file(delivery / 'manifest.json'),
            })
            return output / 'run.json', True
        self.calls.append('rebuild-agent')
        output.mkdir(parents=True)
        write(output / 'run.json', {'status': 'agent_exited_unverified',
                                    'provider': args[0],
                                    'task_case': str(task)})
        write(output / 'manifest.json', {'kind': 'agent_execution'})
        delivery = output / 'agent-delivery'
        write(delivery / 'manifest.json', {'kind': 'agent_delivery'})
        write(delivery / 'delivery.json', {
            'asserted_flow_count': 1, 'visual_unreviewed_flow_count': 0,
            'visual_major_difference_flow_count': 0,
            'flow_results': [{'script_assertions_status': 'passed'}],
        })
        write(output / 'rebuild-verification.json', {
            'status': 'selected_flows_verified',
            'agent_delivery_case': str(delivery),
            'agent_delivery_manifest_sha256': sha256_file(delivery / 'manifest.json'),
            'selected_flow_count': 1, 'asserted_flow_count': 1,
        })
        return output / 'run.json', True

    def rebuild(self, report, output, backend, flow_ids, udid, project, resume=False):
        self.calls.append('rebuild-preparation')
        write(output / 'manifest.json', {
            'status': 'ready_for_agent', 'report': str(report),
            'device_udid': udid, 'project_dir': str(project),
            'ui_backend': backend, 'selected_flow_ids': ['one'],
        })
        write(output / 'task/task.json', {'kind': 'agent_implementation_task',
                                          'flows': [{'id': 'one'}]})
        return output / 'manifest.json', True

    def run_workflow(self, *, resume=False, discovery_case=None):
        with patch('copyapp.copy_workflow.prepare_app', side_effect=self.prepare), \
             patch('copyapp.copy_workflow.run_agent_task', side_effect=self.agent), \
             patch('copyapp.copy_workflow.prepare_rebuild', side_effect=self.rebuild), \
             patch('copyapp.copy_workflow.verify_case', return_value=True):
            return asyncio.run(copy_app(
                '00008020-1111111111111111', 'com.example.original',
                [self.script], self.project, 'com.example.clone', self.output,
                self.survey, workspace=self.root, agent_executable=self.executable,
                discovery_case=discovery_case,
                resume=resume))

    def test_full_handoff_and_resume_reuse_verified_stages(self):
        path, complete = self.run_workflow()
        self.assertTrue(complete)
        self.assertEqual(json.loads(path.read_text())['status'], 'complete')
        self.assertEqual(self.calls, ['prepare', 'analysis-agent',
                                      'rebuild-preparation', 'rebuild-agent'])
        with patch('copyapp.copy_workflow.verify_case', return_value=True):
            self.assertTrue(validate_copy_workflow(self.output, json.loads(path.read_text())))
            self.assertTrue(verify_case(self.output))
        path, complete = self.run_workflow(resume=True)
        self.assertTrue(complete)
        self.assertEqual(len(self.calls), 4)

    def test_failed_agent_is_retained_and_not_replayed_on_resume(self):
        self.fail_analysis = True
        path, complete = self.run_workflow()
        self.assertFalse(complete)
        self.assertEqual(json.loads(path.read_text())['status'], 'analysis_agent_needs_review')
        self.fail_analysis = False
        path, complete = self.run_workflow(resume=True)
        self.assertFalse(complete)
        self.assertEqual(self.calls, ['prepare', 'analysis-agent'])

    def test_mismatched_reviewed_report_stops_before_rebuild(self):
        self.bad_report = True
        path, complete = self.run_workflow()
        self.assertFalse(complete)
        record = json.loads(path.read_text())
        self.assertEqual(record['status'], 'failed')
        self.assertIn('rebuilt bundle differs', record['error']['message'])
        self.assertNotIn('rebuild-preparation', self.calls)

    def test_resume_rejects_changed_playbook_without_device_work(self):
        self.run_workflow()
        write(self.script, {'bundle_id': 'com.example.original', 'changed': True})
        with self.assertRaisesRegex(ValueError, 'settings differ'):
            self.run_workflow(resume=True)
        self.assertEqual(len(self.calls), 4)

    def test_saved_success_is_rejected_if_visual_or_behavior_gap_appears(self):
        path, complete = self.run_workflow()
        self.assertTrue(complete)
        delivery = self.output / 'rebuild-agent/agent-delivery/delivery.json'
        data = json.loads(delivery.read_text())
        data['visual_major_difference_flow_count'] = 1
        write(delivery, data)
        with patch('copyapp.copy_workflow.verify_case', return_value=True):
            self.assertFalse(validate_copy_workflow(self.output,
                                                    json.loads(path.read_text())))
            self.assertFalse(verify_case(self.output))
        path, complete = self.run_workflow(resume=True)
        self.assertFalse(complete)
        self.assertEqual(len(self.calls), 4)

    def test_discovery_source_is_pinned_across_the_full_workflow(self):
        discovery = self.root / 'cases/discovery'
        write(discovery / 'manifest.json', {'status': 'complete'})
        with patch('copyapp.copy_workflow.accepted_playbooks',
                   return_value=[self.script.resolve()]):
            path, complete = self.run_workflow(discovery_case=discovery)
            self.assertTrue(complete)
            self.assertEqual(json.loads(path.read_text())['discovery_case'], str(discovery))
            write(discovery / 'manifest.json', {'status': 'changed'})
            with patch('copyapp.copy_workflow.verify_case', return_value=True):
                self.assertFalse(validate_copy_workflow(
                    self.output, json.loads(path.read_text())))

    def test_auto_discovery_precedes_preparation_and_pins_agent_evidence(self):
        scripts = [self.script]
        for index in (2, 3):
            path = self.root / f'playbook-{index}.json'
            write(path, {'bundle_id': 'com.example.original', 'flow': index})
            scripts.append(path)
        discoveries = []

        def discover(udid, bundle, backend, output, **kwargs):
            discoveries.append(kwargs['resume'])
            if not kwargs['resume']:
                write(output / 'discovery/manifest.json', {'status': 'complete'})
                write(output / 'manifest.json', {
                    'status': 'complete', 'device_udid': udid,
                    'bundle_id': bundle, 'backend': backend,
                    'provider': kwargs['provider'],
                    'scripts': [{'path': str(path), 'sha256': sha256_file(path)}
                                for path in scripts],
                })
            return output / 'manifest.json', True

        def run(*, resume=False):
            with patch('copyapp.copy_workflow.run_discovery_agent', side_effect=discover), \
                 patch('copyapp.copy_workflow.accepted_playbooks', return_value=scripts), \
                 patch('copyapp.copy_workflow.prepare_app', side_effect=self.prepare), \
                 patch('copyapp.copy_workflow.run_agent_task', side_effect=self.agent), \
                 patch('copyapp.copy_workflow.prepare_rebuild', side_effect=self.rebuild), \
                 patch('copyapp.copy_workflow.verify_case', return_value=True):
                return asyncio.run(copy_app(
                    '00008020-1111111111111111', 'com.example.original', [],
                    self.project, 'com.example.clone', self.output, self.survey,
                    workspace=self.root, agent_executable=self.executable,
                    auto_discover=True, resume=resume))

        path, complete = run()
        self.assertTrue(complete)
        self.assertEqual(discoveries, [False])
        self.assertEqual(self.calls, ['prepare', 'analysis-agent',
                                      'rebuild-preparation', 'rebuild-agent'])
        record = json.loads(path.read_text())
        self.assertEqual(record['scripts'][0]['path'], str(self.script))
        self.assertEqual(len(record['scripts']), 3)
        path, complete = run(resume=True)
        self.assertTrue(complete)
        self.assertEqual(discoveries, [False, True])
        self.assertEqual(len(self.calls), 4)
        write(self.output / 'discovery-agent/discovery/manifest.json',
              {'status': 'changed'})
        with patch('copyapp.copy_workflow.accepted_playbooks', return_value=scripts), \
             patch('copyapp.copy_workflow.verify_case', return_value=True):
            self.assertFalse(validate_copy_workflow(self.output,
                                                    json.loads(path.read_text())))


if __name__ == '__main__':
    unittest.main()
