
import unittest
from datetime import datetime, timezone

from src.config import Settings
from src.domain import PostRecord
from src.pipeline.rank import score_post
from src.pipeline.summarize import build_summary_bundle, build_summary_sentences, summarize_post_text


def _scored(pid: str, author: str, text: str, followers: int = 1000):
    post = PostRecord(
        id=pid,
        source='x-home',
        timestamp=datetime.now(timezone.utc),
        author=author,
        handle=author.lower(),
        text=text,
        followers=followers,
    )
    return score_post(post, Settings())


class SummaryTests(unittest.TestCase):
    def test_summary_has_three_to_five_sentences(self):
        posts = [
            _scored('1', 'Addy Osmani', 'Browser performance and web vitals'),
            _scored('2', 'Matt Pocock', 'TypeScript inference and tooling'),
            _scored('3', 'Simon Willison', 'LLM tools and agents'),
        ]
        sentences = build_summary_sentences(posts, 5)
        self.assertGreaterEqual(len(sentences), 3)
        self.assertLessEqual(len(sentences), 5)
        self.assertTrue(any('browser' in sentence.lower() for sentence in sentences))

    def test_summary_text_is_concise_and_chinese(self):
        summary = summarize_post_text(
            'AI Edge @aiedge_ · 1h My all-time favorite Claude prompts. Simple inputs, yet they yield massive returns, Save on token usage, get deeper insights, kill AI slop, and more. I recommend saving these to a Notion or Obsidian database.'
        )
        self.assertTrue(summary.startswith('重點：'))
        self.assertRegex(summary, r'[\u4e00-\u9fff]')
        self.assertNotIn('AI Edge', summary)
        self.assertNotIn('aiedge_', summary)
        self.assertLess(len(summary), 90)

    def test_bundle(self):
        posts = [
            _scored('1', 'Addy Osmani', 'Browser performance and web vitals'),
            _scored('2', 'Matt Pocock', 'TypeScript inference and tooling'),
        ]
        bundle = build_summary_bundle(posts, Settings())
        self.assertEqual(bundle.raw_count, 2)
        self.assertGreaterEqual(len(bundle.sentences), 3)
