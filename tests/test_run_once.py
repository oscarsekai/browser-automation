
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.scheduler.run_once import run_once


SAMPLE_HTML = '''
<html><body>
  <article data-post-id="1" data-author="Addy Osmani" data-handle="addyosmani" data-followers="400000">
    <a href="https://x.com/addyosmani/status/1">link</a>
    Addy explains browser performance today.
  </article>
  <article data-post-id="2" data-author="Matt Pocock" data-handle="mattpocockuk" data-followers="120000">
    <a href="https://x.com/mattpocockuk/status/2">link</a>
    Typescript tooling is getting better.
  </article>
</body></html>
'''


class RunOnceTests(unittest.TestCase):
    def test_run_once_writes_summary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text('OUTPUT_DIR=data/summaries\nRAW_DIR=data/raw\n', encoding='utf-8')
            html_path = root / 'snapshot.html'
            html_path.write_text(SAMPLE_HTML, encoding='utf-8')
            result = run_once(root, html_path)
            self.assertTrue(result['summary_html'].exists())
            self.assertTrue(result['summary_json'].exists())
            self.assertTrue(result['raw_dir'].exists())
            self.assertTrue(result['latest_html'].exists())
            self.assertEqual(result['latest_html'].name, 'index.html')
