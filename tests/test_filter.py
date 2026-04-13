
import unittest
from datetime import datetime, timezone

from src.domain import PostRecord
from src.pipeline.filter import canonical_text, filter_posts


def _post(pid: str, text: str) -> PostRecord:
    return PostRecord(
        id=pid,
        source='x-home',
        timestamp=datetime.now(timezone.utc),
        author='A',
        handle='a',
        text=text,
        followers=10,
    )


class FilterTests(unittest.TestCase):
    def test_filters_noise_and_duplicates(self):
        posts = [
            _post('1', 'follow for more'),
            _post('2', 'This is a useful post about Python packaging.'),
            _post('3', 'This is a useful post about Python packaging!'),
            _post('4', 'Another distinct useful post about TypeScript.'),
        ]
        result = filter_posts(posts)
        self.assertEqual(len(result.kept), 2)
        self.assertEqual(len(result.dropped), 2)
        self.assertTrue(any(item.reason == 'noise' for item in result.dropped))
        self.assertTrue(any(item.reason == 'duplicate' for item in result.dropped))

    def test_canonical_text(self):
        self.assertEqual(canonical_text('Hello http://x.com World!'), 'hello world')
