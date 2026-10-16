import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.report_portfolio import create_report_portfolio, validate_report_portfolio
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


class ReportPortfolioTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.reports = [self.make_report('one'), self.make_report('two')]
        self.output = self.root / 'combined'

    def make_report(self, name, *, binary='a' * 64, device='device-hash'):
        analysis = self.root / name / 'analysis'
        report = self.root / name / 'report'
        write(analysis / 'analysis-index.json', {'schema_version': 1})
        write(analysis / 'run-state.json', {
            'bundle_id': 'com.example.app', 'device_id_sha256_prefix': device})
        write(analysis / 'survey/app.json', {
            'CFBundleIdentifier': 'com.example.app',
            'CFBundleShortVersionString': '1.2', 'CFBundleVersion': '3'})
        write(analysis / 'decrypted/static/ipa-index.json', {
            'bundle_id': 'com.example.app', 'version': '1.2', 'build': '3',
            'executable': 'Main',
            'binaries': [{'path': 'Payload/App.app/Main', 'sha256': binary,
                          'encryption_status': 'cryptid_zero'}]})
        write(report / 'report-index.json', {
            'target_bundle_id': 'com.example.app', 'source_case': str(analysis),
            'source_case_index_sha256': sha256_file(analysis / 'analysis-index.json')})
        (report / 'evidence').mkdir()
        (report / 'evidence' / 'proof.txt').write_text('proof')
        (report / 'report.md').write_text(
            '# Source report\n\n## Finding\n\n[proof](evidence/proof.txt)\n')
        return report

    def test_combines_exact_build_and_rewrites_local_evidence_links(self):
        with patch('copyapp.report_portfolio._verified', return_value=True):
            manifest = create_report_portfolio(self.reports, self.output)
            self.assertTrue(validate_report_portfolio(self.output,
                                                      json.loads(manifest.read_text())))
            self.assertTrue(verify_case(self.output))
        report = (self.output / 'report.md').read_text()
        self.assertIn('## Source report', report)
        self.assertIn('one/report/evidence/proof.txt', report)
        self.assertIn('two/report/evidence/proof.txt', report)

    def test_rejects_different_main_binary_even_on_same_bundle_version(self):
        other = self.make_report('other', binary='b' * 64)
        with patch('copyapp.report_portfolio._verified', return_value=True), \
                self.assertRaisesRegex(ValueError, 'different device, App build or main binary'):
            create_report_portfolio([self.reports[0], other], self.output)

    def test_rejects_source_mutation_after_creation(self):
        with patch('copyapp.report_portfolio._verified', return_value=True):
            manifest = create_report_portfolio(self.reports, self.output)
            (self.reports[1] / 'report.md').write_text('# Changed\n')
            self.assertFalse(validate_report_portfolio(self.output,
                                                       json.loads(manifest.read_text())))
            self.assertFalse(verify_case(self.output))


if __name__ == '__main__':
    unittest.main()
