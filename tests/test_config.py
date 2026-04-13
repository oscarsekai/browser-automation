
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.config import load_settings, load_env_file


class ConfigTests(unittest.TestCase):
    def test_load_env_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env.local'
            path.write_text('SCROLL_COUNT=12\nFOCUS_KEYWORDS=python, ai\n', encoding='utf-8')
            values = load_env_file(path)
            self.assertEqual(values['SCROLL_COUNT'], '12')
            self.assertEqual(values['FOCUS_KEYWORDS'], 'python, ai')

    def test_load_settings_from_env_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text('SCROLL_COUNT=12\nDELETE_RAW_AFTER_SUMMARY=true\n', encoding='utf-8')
            settings = load_settings(root, environ={})
            self.assertEqual(settings.scroll_count, 12)
            self.assertTrue(settings.delete_raw_after_summary)

    def test_load_settings_defaults_match_documented_runtime(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = load_settings(root, environ={})
            self.assertEqual(settings.scroll_count, 80)
            self.assertEqual(settings.raw_retention_days, 3)
            self.assertEqual(settings.summarize_backend, 'acp')
            self.assertEqual(settings.summarize_cli, 'copilot')
            self.assertEqual(settings.summarize_model, 'gpt-5-mini')

    def test_load_settings_supports_cli_selection(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text('SUMMARIZE_CLI=copilot\nSUMMARIZE_CLI_PATH=/tmp/copilot\n', encoding='utf-8')
            settings = load_settings(root, environ={})
            self.assertEqual(settings.summarize_cli, 'copilot')
            self.assertEqual(settings.summarize_cli_path, '/tmp/copilot')

    def test_load_settings_reads_chrome_user_data_dir(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text('CHROME_USER_DATA_DIR=$HOME/chrome-hermes-profile\n', encoding='utf-8')
            settings = load_settings(root, environ={})
            self.assertEqual(settings.chrome_user_data_dir, '$HOME/chrome-hermes-profile')

    def test_load_settings_reads_collect_target_and_interval(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text('COLLECT_TARGET=5\nCOLLECT_INTERVAL_SECONDS=3600\n', encoding='utf-8')
            settings = load_settings(root, environ={})
            self.assertEqual(settings.collect_target, 5)
            self.assertEqual(settings.collect_interval_seconds, 3600)

    def test_load_settings_collect_defaults(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = load_settings(root, environ={})
            self.assertEqual(settings.collect_target, 3)
            self.assertEqual(settings.collect_interval_seconds, 18000)
