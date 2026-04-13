
import unittest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from src.config import Settings
from src.domain import PostRecord
from src.pipeline.rank import score_post
from src.pipeline.summarize import build_summary_bundle, build_summary_sentences, llm_summarize_posts


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

    def test_summary_falls_back_to_polished_traditional_chinese_when_llm_is_unavailable(self):
        posts = [_scored('fallback', 'AI Edge', 'My favorite Claude prompts save token usage and get deeper insights for AI coding workflows.')]
        settings = Settings(summarize_backend='acp')

        with (
            patch('src.pipeline.summarize._run_cli_acp', new=AsyncMock(return_value=None)),
            patch('src.pipeline.summarize._run_llm_cli_exec', return_value=None),
            patch('src.pipeline.summarize._run_openai_prompt', return_value=None),
        ):
            asyncio.run(llm_summarize_posts(posts, settings))

        self.assertEqual(
            posts[0].record.summary,
            '這則貼文聚焦 Claude prompts 與 AI coding workflows，強調可節省 token 並深化分析。',
        )
        self.assertEqual(posts[0].record.category, 'other')

    def test_bundle(self):
        posts = [
            _scored('1', 'Addy Osmani', 'Browser performance and web vitals'),
            _scored('2', 'Matt Pocock', 'TypeScript inference and tooling'),
        ]
        bundle = build_summary_bundle(posts, Settings())
        self.assertEqual(bundle.raw_count, 2)
        self.assertGreaterEqual(len(bundle.sentences), 3)

    def test_missing_invalid_category_triggers_second_llm_classification(self):
        posts = [_scored('1', 'Author', 'Unusual semiconductor sanctions update with no fallback keyword match')]
        settings = Settings(summarize_backend='acp')

        with (
            patch('src.pipeline.summarize._run_cli_acp', new=AsyncMock(return_value='[{"id":"1","summary":"測試摘要","category":"weird"}]')),
            patch('src.pipeline.summarize._run_codex_exec', return_value=None),
            patch('src.pipeline.summarize._run_openai_prompt', return_value='[{"id":"1","category":"geopolitics"}]'),
        ):
            asyncio.run(llm_summarize_posts(posts, settings))

        self.assertEqual(posts[0].record.summary, '測試摘要')
        self.assertEqual(posts[0].record.category, 'geopolitics')

    def test_acp_backend_can_use_copilot_cli_entry(self):
        posts = [_scored('1', 'Author', 'React compiler updates for large frontend apps')]
        settings = Settings(summarize_backend='acp', summarize_cli='copilot', summarize_model='gpt-5-mini')

        with patch('src.acp.cli_bridge_client.run_prompt_via_acp', new=AsyncMock(return_value='[{"id":"1","summary":"React 編譯流程更新，鎖定大型前端應用效能。","category":"frontend"}]')) as acp_mock:
            asyncio.run(llm_summarize_posts(posts, settings))

        self.assertEqual(posts[0].record.category, 'frontend')
        self.assertEqual(posts[0].record.summary, 'React 編譯流程更新，鎖定大型前端應用效能。')
        acp_mock.assert_awaited_once()
        _, kwargs = acp_mock.await_args
        self.assertEqual(kwargs['cli_name'], 'copilot')
        self.assertEqual(kwargs['model_id'], 'gpt-5-mini')

    def test_chinese_source_keeps_existing_sentence_when_llm_is_unavailable(self):
        posts = [_scored('zh', '作者', '這篇貼文整理前端效能優化重點，並補上實作上的注意事項。')]
        settings = Settings(summarize_backend='acp')

        with (
            patch('src.pipeline.summarize._run_cli_acp', new=AsyncMock(return_value=None)),
            patch('src.pipeline.summarize._run_llm_cli_exec', return_value=None),
            patch('src.pipeline.summarize._run_openai_prompt', return_value=None),
        ):
            asyncio.run(llm_summarize_posts(posts, settings))

        self.assertIn('前端效能優化重點', posts[0].record.summary)
        self.assertIn('實作上的注意事項', posts[0].record.summary)
        self.assertEqual(posts[0].record.category, 'other')

    def test_direct_codex_cli_exec_uses_custom_binary_path(self):
        posts = [_scored('codex', 'Author', 'Postgres performance notes for backend services')]
        settings = Settings(
            summarize_backend='codex',
            summarize_cli='codex',
            summarize_cli_path='/tmp/custom-codex',
            summarize_model='gpt-5-mini',
        )

        with patch(
            'src.pipeline.summarize._run_codex_exec',
            return_value='[{"id":"codex","summary":"Postgres 效能調整重點整理。","category":"engineering"}]',
        ) as codex_mock:
            asyncio.run(llm_summarize_posts(posts, settings))

        self.assertEqual(posts[0].record.summary, 'Postgres 效能調整重點整理。')
        self.assertEqual(posts[0].record.category, 'engineering')
        _, kwargs = codex_mock.call_args
        self.assertEqual(kwargs['cli_path'], '/tmp/custom-codex')
