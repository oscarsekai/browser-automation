
import unittest
from datetime import datetime, timedelta, timezone

from src.config import Settings
from src.domain import PostRecord
from src.pipeline.rank import rank_posts, score_post


def _post(pid: str, followers: int | None, text: str, hours_ago: int = 1, tier=None, metadata=None) -> PostRecord:
    meta = dict(metadata or {})
    if tier:
        meta['source_tier'] = tier
    return PostRecord(
        id=pid,
        source='x-home',
        timestamp=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        author='A',
        handle='a',
        text=text,
        followers=followers,
        metadata=meta,
    )


class RankTests(unittest.TestCase):
    def test_rank_prefers_a_tier_and_followers(self):
        settings = Settings(focus_keywords=('python',))
        a_post = _post('1', 2_000_000, 'Python packaging insight', tier='A')
        c_post = _post('2', 10, 'Python packaging insight', tier='C')
        scored = rank_posts([c_post, a_post], settings)
        self.assertEqual(scored[0].record.id, '1')
        self.assertGreater(scored[0].score, scored[1].score)

    def test_score_changes_with_keywords(self):
        settings = Settings(focus_keywords=('browser', 'python'))
        post = _post('1', 1000, 'Python browser automation is fun')
        scored = score_post(post, settings)
        self.assertGreater(scored.breakdown['relevance'], 0.0)
        self.assertGreater(scored.score, 0.0)

    def test_no_followers_post_can_rank_when_traffic_is_high(self):
        settings = Settings(focus_keywords=('python',))
        low_signal = _post('1', None, 'Python browser automation insight', metadata={'views': 10, 'likes': 1})
        high_signal = _post('2', None, 'Python browser automation insight', metadata={'views': 250_000, 'likes': 12_000, 'replies': 600})
        scored = rank_posts([low_signal, high_signal], settings)
        self.assertEqual(scored[0].record.id, '2')
        self.assertEqual(scored[0].tier, 'C')
        self.assertGreater(scored[0].breakdown['traffic_engagement'], scored[1].breakdown['traffic_engagement'])
        self.assertIn('high-traffic', scored[0].reasons)
