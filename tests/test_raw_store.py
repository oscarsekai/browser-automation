
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from src.domain import PostRecord
from src.storage.raw_store import cleanup_raw_runs, load_raw_run, write_raw_run


class RawStoreTests(unittest.TestCase):
    def test_write_and_load_raw_run(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            post = PostRecord(
                id='1', source='x-home', timestamp=datetime.now(timezone.utc),
                author='Ada', handle='ada', text='Hello browser automation', followers=1000,
                url='https://x.com/ada/status/1'
            )
            run_dir = write_raw_run(root, [post], metadata={'source': 'x-home'}, now=datetime.now(timezone.utc))
            loaded = load_raw_run(run_dir)
            self.assertEqual(loaded['manifest']['post_count'], 1)
            self.assertEqual(loaded['posts'][0]['author'], 'Ada')

    def test_cleanup_raw_runs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_day = root / '2026-04-01' / '20260401T000000Z'
            old_day.mkdir(parents=True)
            (old_day / 'manifest.json').write_text('{}', encoding='utf-8')
            (old_day / 'posts.json').write_text('[]', encoding='utf-8')
            now = datetime(2026, 4, 13, tzinfo=timezone.utc)
            removed = cleanup_raw_runs(root, 3, now=now)
            self.assertTrue(removed)
            self.assertFalse(old_day.exists())
