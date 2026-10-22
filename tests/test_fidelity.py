import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.fidelity import (create_plan, create_check, evaluate, policy, review_template,
                             visual_context, verify_fidelity)
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


class FidelityTests(unittest.TestCase):
    def setUp(self):
        self.context = {'pairs': [{'id': 'r01.search.step-1', 'verdict': 'major_difference'}],
                        'core_behavior_passed': True, 'guard_issues': []}
        self.review = review_template(self.context)
        self.review['reviewer'] = 'test reviewer'
        self.review['dimensions']['layout'].update(score=85, notes='The main layout and navigation match the selected task.')
        self.review['dimensions']['details'].update(score=40, notes='Offline cards and font details remain visibly different.')
        self.review['differences'][0].update(impact='non_blocking', reason='Offline example content is an explicit remaining difference.')

    def test_default_80_stops_with_acknowledged_differences(self):
        result = evaluate(policy(), self.context, self.review, 1)
        self.assertEqual(result['grade'], 82)
        self.assertEqual(result['decision'], 'target_met')
        self.assertIsNone(result['similarity_percent'])
        self.assertIsNone(result['known_capability_coverage'])
        self.assertFalse(result['strict_delivery_certified'])
        self.assertEqual(evaluate(policy(90), self.context, self.review, 1)['decision'], 'continue')
        limited = evaluate(policy(90), self.context, self.review, 3)
        self.assertEqual(limited['decision'], 'iteration_limit')
        self.assertFalse(limited['target_met'])

    def test_threshold_cannot_bypass_core_or_blocking_issues(self):
        for changed in [dict(self.context, core_behavior_passed=False),
                        dict(self.context, guard_issues=['unknown starting state'])]:
            self.assertFalse(evaluate(policy(0), changed, self.review, 1)['target_met'])
        self.review['differences'][0]['impact'] = 'blocking'
        self.assertFalse(evaluate(policy(0), self.context, self.review, 1)['target_met'])

    def test_every_difference_and_real_image_citation_is_required(self):
        for mutate in [lambda r: r.update(differences=[]),
                       lambda r: r['dimensions']['layout'].update(pair_ids=['invented']),
                       lambda r: r['dimensions']['layout'].update(score=True),
                       lambda r: r['differences'][0].update(impact=None)]:
            changed = copy.deepcopy(self.review)
            mutate(changed)
            with self.assertRaises(ValueError):
                evaluate(policy(), self.context, changed, 1)

    def test_100_does_not_hide_minor_differences(self):
        self.context['pairs'][0]['verdict'] = 'minor_difference'
        for row in self.review['dimensions'].values():
            row['score'] = 100
        self.assertFalse(evaluate(policy(100), self.context, self.review, 1)['target_met'])

    def test_invalid_targets_and_iteration_ranges(self):
        for target in [-1, 101, True, 80.5]:
            with self.assertRaises(ValueError):
                policy(target)
        for count in [0, 21, False]:
            with self.assertRaises(ValueError):
                policy(80, count)
        with self.assertRaises(ValueError):
            evaluate(policy(), self.context, self.review, 4)

    def test_failed_attempts_consume_budget_and_cannot_get_visual_points(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'manifest.json', {'kind': 'mac_rebuild_check', 'status': 'failed'})
            context = visual_context(root, {'platform': 'macos'})
            review = review_template(context)
            review['reviewer'] = 'test reviewer'
            for row in review['dimensions'].values():
                row.update(score=0, notes='The failed run has no complete image review.')
            self.assertEqual(evaluate(policy(), context, review, 3)['decision'], 'iteration_limit')
            review['dimensions']['layout']['score'] = 100
            with self.assertRaises(ValueError):
                evaluate(policy(), context, review, 1)

    def test_frozen_plan_and_iteration_chain_reject_rehash_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            task = root / 'task'
            write(task / 'manifest.json', {'kind': 'agent_implementation_task'})
            write(task / 'task.json', {'status': 'ready_for_agent', 'report_index_sha256': 'a' * 64,
                  'project_dir': str(root / 'project'), 'rebuilt_bundle_id': 'test.clone',
                  'flows': [{'id': 'search'}], 'device_udid': 'test-device'})
            # Only the external task is stubbed here. Fidelity cases exercise
            # their real dispatch, chain and semantic verifier.
            real_verify = verify_case
            def external(path):
                return True if path.resolve() == task.resolve() else real_verify(path)
            with patch('copyapp.fidelity.verify_case', side_effect=external):
                plan = create_plan(task, root / 'plan', max_iterations=2)
                self.assertTrue(verify_case(plan))
                previous = None
                for index in (1, 2):
                    failed = root / ('failed-' + str(index))
                    write(failed / 'manifest.json', {'kind': 'rebuild_check', 'status': 'failed', 'attempt': index})
                    context = visual_context(failed, {'platform': 'ios'})
                    review = review_template(context)
                    review['reviewer'] = 'test reviewer'
                    for row in review['dimensions'].values():
                        row.update(score=0, notes='Failed replay; no completed image review is available.')
                    review_path = root / 'review.json'
                    write(review_path, review)
                    current = create_check(plan, failed, review_path, root / ('cycle-' + str(index)), previous)
                    self.assertTrue(verify_case(current))
                    if previous:
                        data = json.loads((current / 'fidelity-check.json').read_text())
                        self.assertEqual(data['result']['decision'], 'iteration_limit')
                    previous = current
                with self.assertRaises(ValueError):
                    create_check(plan, failed, review_path, root / 'cycle-3', previous)
                saved = json.loads((current / 'fidelity-check.json').read_text())
                saved['result'].update(target_met=True, decision='target_met')
                write(current / 'fidelity-check.json', saved)
                manifest = json.loads((current / 'manifest.json').read_text())
                for row in manifest['evidence']:
                    if row['path'] == 'fidelity-check.json':
                        row['sha256'] = sha256_file(current / row['path'])
                write(current / 'manifest.json', manifest)
                self.assertFalse(verify_fidelity(current))

    def test_ios_adapter_requires_reviewed_selected_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / 'delivery'
            review = root / 'visual'
            write(evidence / 'manifest.json', {'kind': 'agent_delivery'})
            write(evidence / 'delivery.json', {'task_case': str(root / 'task'),
                  'visual_review_case': str(review), 'visual_unreviewed_flow_count': 0,
                  'asserted_flow_count': 1, 'source_project_sha256': 'a' * 64,
                  'ipa_snapshot_sha256': 'b' * 64})
            write(review / 'review.json', {'pairs': [{'flow_id': 'search', 'step': 2, 'verdict': 'major_difference'},
                                                   {'flow_id': 'omitted', 'step': 3, 'verdict': 'match'}]})
            frozen = {'platform': 'ios', 'flow_ids': ['search'], 'project': str(root / 'project')}
            with patch('copyapp.fidelity.require'), patch('copyapp.fidelity.contract', return_value=frozen):
                context = visual_context(evidence, frozen)
                self.assertTrue(context['core_behavior_passed'])
                self.assertEqual(context['pairs'], [{'id': 'search.step-2', 'verdict': 'major_difference'}])
                data = json.loads((evidence / 'delivery.json').read_text())
                data['visual_review_case'] = None
                write(evidence / 'delivery.json', data)
                with self.assertRaises(ValueError):
                    visual_context(evidence, frozen)


if __name__ == '__main__':
    unittest.main()
