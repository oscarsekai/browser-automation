
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
            self.assertEqual(settings.summarize_model, 'gpt-5.4-mini')
