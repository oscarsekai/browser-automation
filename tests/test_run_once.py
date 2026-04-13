
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io

from src.domain import PostRecord
from src.scheduler.run_once import main, run_once
from src.storage.raw_store import write_raw_run


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

            async def _fake_summarize(posts, settings):
                for scored in posts:
                    scored.record.summary = '這是一則測試摘要。'
                    scored.record.category = 'engineering'

            with patch('src.scheduler.run_once.llm_summarize_posts', new=_fake_summarize), \
                 patch('src.scheduler.run_once._git_commit_and_push', return_value={'status': 'skipped'}):
                result = run_once(root, html_path, force_build=True)

            self.assertTrue(result['summary_html'].exists())
            self.assertTrue(result['summary_json'].exists())
            self.assertTrue(result['raw_dir'].exists())
            self.assertTrue(result['latest_html'].exists())
            self.assertEqual(result['latest_html'].name, 'index.html')

    def test_build_only_writes_root_digest_and_returns_latest_md(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text('OUTPUT_DIR=data/summaries\nRAW_DIR=data/raw\n', encoding='utf-8')
            post = PostRecord(
                id='1',
                source='x-home',
                timestamp=datetime.now(timezone.utc),
                author='Ada',
                handle='ada',
                text='Claude and browser tooling updates are landing fast.',
                url='https://x.com/ada/status/1',
                followers=1000,
            )
            write_raw_run(root / 'data' / 'raw', [post], metadata={'source': 'html'})

            async def _fake_summarize(posts, settings):
                for scored in posts:
                    scored.record.summary = 'Ada 說瀏覽器工具與 AI 工作流正在快速整合。'
                    scored.record.category = 'frontend'

            with patch('src.scheduler.run_once.llm_summarize_posts', new=_fake_summarize), \
                 patch('src.scheduler.run_once._git_commit_and_push', return_value={'status': 'skipped'}):
                result = run_once(root, build_only=True)

            self.assertEqual(result['source_mode'], 'build-only')
            self.assertTrue(result['latest_html'].exists())
            self.assertTrue(result['latest_md'].exists())
            self.assertTrue((root / 'digest.md').exists())
            self.assertEqual(result['latest_md'], root / 'digest.md')
            self.assertEqual((root / 'digest.md').read_text(encoding='utf-8'), result['summary_md'].read_text(encoding='utf-8'))

    def test_main_prints_html_and_digest_paths_after_build(self):
        stdout = io.StringIO()
        with patch('src.scheduler.run_once.run_once', return_value={
            'summary_html': Path('data/summaries/2026-04-13/20260413T000000Z/index.html'),
            'latest_html': Path('index.html'),
            'latest_md': Path('digest.md'),
        }):
            with redirect_stdout(stdout):
                exit_code = main([])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('[output] html: index.html', output)
        self.assertIn('[output] digest: digest.md', output)

    def test_live_collect_requires_cdp_port_before_restart(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text('OUTPUT_DIR=data/summaries\nRAW_DIR=data/raw\n', encoding='utf-8')

            with patch('src.scheduler.run_once.restart_chrome') as restart_mock:
                with self.assertRaisesRegex(ValueError, 'CDP_REMOTE_DEBUGGING_PORT'):
                    run_once(root)

            restart_mock.assert_not_called()

    def test_live_collect_uses_configured_chrome_user_data_dir(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.env.local').write_text(
                'OUTPUT_DIR=data/summaries\nRAW_DIR=data/raw\nCDP_REMOTE_DEBUGGING_PORT=9333\nCHROME_USER_DATA_DIR=$HOME/chrome-hermes-profile\n',
                encoding='utf-8',
            )

            with patch('src.scheduler.run_once.restart_chrome') as restart_mock, \
                 patch('src.scheduler.run_once._build_adapter', side_effect=RuntimeError('stop-after-restart')):
                with self.assertRaisesRegex(RuntimeError, 'stop-after-restart'):
                    run_once(root)

            restart_mock.assert_called_once_with(port=9333, profile='$HOME/chrome-hermes-profile')
