
import unittest
from datetime import datetime, timezone

from src.config import Settings
from src.domain import PostRecord
from src.pipeline.rank import score_post
from src.pipeline.summarize import build_summary_bundle
from src.web.build_html import render_summary_html


def _scored(pid: str, text: str, url: str = 'https://x.com/author/status/1'):
    post = PostRecord(
        id=pid,
        source='x-home',
        timestamp=datetime.now(timezone.utc),
        author='Author',
        handle='author',
        text=text,
        url=url,
        followers=1000,
    )
    return score_post(post, Settings())


class HtmlTests(unittest.TestCase):
    def test_render_contains_section_headings_links_and_omits_empty_archive(self):
        bundle = build_summary_bundle([
            _scored('1', 'The Strait of Hormuz blockade is driving oil prices higher', url='https://x.com/a/status/1'),
            _scored('2', 'Claude and MiniMax are fighting over the AI tooling stack', url='https://x.com/b/status/2'),
            _scored('3', 'Markets are repricing software and SaaS companies', url='https://x.com/c/status/3'),
        ], Settings())
        html = render_summary_html(bundle)
        self.assertIn('### 🌐 地緣政治', html)
        self.assertIn('### 💰 財經市場', html)
        self.assertIn('### 🤖 AI 模型與工具', html)
        self.assertIn('href="https://x.com/a/status/1"', html)
        self.assertIn('href="https://x.com/b/status/2"', html)
        self.assertIn('href="https://x.com/c/status/3"', html)
        self.assertNotIn('Addy Osmani @addyosmani', html)
        self.assertNotIn('Matt Pocock @mattpocockuk', html)
        self.assertNotIn('Simon Willison @simonw', html)
        self.assertNotIn('簡潔版中文摘要', html)
        self.assertNotIn('資料庫 / 歸檔', html)
        self.assertNotIn('fresh, relevant, dense, original', html)
        self.assertNotIn('score ', html.lower())
        self.assertNotIn('tier ', html.lower())
