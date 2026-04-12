
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from src.browser.fetch_x import normalize_whitespace
from src.config import Settings
from src.domain import ScoredPost, SummaryBundle


STOPWORDS = {
    'the', 'and', 'for', 'with', 'that', 'this', 'you', 'your', 'are', 'was', 'were', 'from', 'have', 'has',
    'into', 'about', 'what', 'when', 'where', 'which', 'will', 'would', 'could', 'should', 'them', 'they',
    'their', 'been', 'being', 'than', 'then', 'there', 'here', 'just', 'also', 'more', 'most', 'some', 'much',
    'very', 'can', 'cant', 'does', 'did', 'doing', 'done', 'one', 'two', 'three', 'four', 'five', 'x', 'com',
    'http', 'https', 'rt', 'via', 'today', 'tonight', 'thread', 'post', 'posts', 'new', 'people', 'like', 'look',
    'make', 'made', 'using', 'use', 'used', 'way', 'work', 'working', 'still', 'need', 'needs', 'good', 'best',
    'great', 'real', 'even', 'many', 'get', 'got',
}

CODEX_BIN_DEFAULT = os.path.expanduser('~/.superset/bin/codex')


def tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9']+", text) if len(token) >= 3]


def extract_keywords(posts: list[ScoredPost], limit: int = 6) -> list[str]:
    counter: Counter[str] = Counter()
    for post in posts:
        counter.update(token for token in tokens(post.record.text) if token not in STOPWORDS)
    return [word for word, _count in counter.most_common(limit)]


def join_phrases(items: list[str]) -> str:
    if not items:
        return '整體討論'
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} 與 {items[1]}'
    return '、'.join(items[:-1]) + f' 與 {items[-1]}'


def _fallback_summary(text: str) -> str:
    """Extract first meaningful sentence from text (no translation)."""
    if not text:
        return ''
    sentences = re.split(r'[.!?。！？\n]+', text)
    for s in sentences:
        s = normalize_whitespace(s)
        if len(s) >= 15 and any(ch.isalpha() for ch in s):
            return s[:120]
    return normalize_whitespace(text)[:120]


def _load_codex_token() -> Optional[str]:
    """Try to load auth token from codex or hermes auth files."""
    candidates = [
        os.path.expanduser('~/.codex/auth.json'),
        os.path.expanduser('~/.hermes/auth.json'),
    ]
    for path in candidates:
        try:
            with open(path) as f:
                data = json.load(f)
            # Flat keys (legacy codex format)
            token = data.get('accessToken') or data.get('access_token')
            if not token:
                # Hermes nested format: providers.openai-codex.tokens.access_token
                codex_provider = (data.get('providers') or {}).get('openai-codex') or {}
                token = (
                    (codex_provider.get('tokens') or {}).get('access_token')
                    or codex_provider.get('access_token')
                )
            if token:
                return token
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
    return None


def _build_prompt(posts: list[ScoredPost]) -> str:
    items = []
    for post in posts:
        items.append({
            'id': post.record.id,
            'text': post.record.text,
            'url': post.record.url or '',
        })
    posts_json = json.dumps(items, ensure_ascii=False, indent=2)
    return f"""你是一個新聞摘要助手。請為以下 X.com 貼文列表生成摘要與分類。

規則（必須嚴格遵守）：
1. 每篇貼文輸出一行摘要，用繁體中文
2. 摘要只能抽取原文中實際出現的資訊，禁止補充或編造
3. 每條摘要不超過 60 字
4. 每篇貼文同時輸出一個 category，從以下選項中選最合適的一個：
   - ai        → AI 模型、LLM、agent、coding tool、prompt 工程
   - geopolitics → 地緣政治、戰爭、外交、制裁、貿易戰
   - engineering → 後端、資料庫、DevOps、軟體架構、程式語言、開源工具
   - frontend  → 前端框架、UI、CSS、設計系統
   - security  → 資安、漏洞、隱私、加密
   - finance   → 股市、投資、金融、SaaS 財務指標
   - other     → 不屬於以上任何類別
5. 回傳格式必須是 JSON array，每個元素有 "id"、"summary"、"category" 三個欄位
6. 不要輸出任何其他文字，只輸出 JSON

貼文列表：
{posts_json}

輸出範例格式：
[
  {{"id": "post-id-1", "summary": "繁中摘要...", "category": "ai"}},
  {{"id": "post-id-2", "summary": "繁中摘要...", "category": "geopolitics"}}
]"""


VALID_CATEGORIES = {'ai', 'geopolitics', 'engineering', 'frontend', 'security', 'finance', 'other'}


def _parse_summary_map(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse LLM output: returns (id→summary, id→category) mappings."""
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.M)
    text = re.sub(r'\s*```$', '', text.strip(), flags=re.M)
    match = re.search(r'\[.*\]', text, re.S)
    if not match:
        return {}, {}
    try:
        items = json.loads(match.group(0))
        summaries: dict[str, str] = {}
        categories: dict[str, str] = {}
        for item in items:
            if 'id' not in item:
                continue
            pid = str(item['id'])
            if 'summary' in item:
                summaries[pid] = str(item['summary'])
            raw_cat = str(item.get('category', '')).strip().lower()
            categories[pid] = raw_cat if raw_cat in VALID_CATEGORIES else 'other'
        return summaries, categories
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}, {}


def _run_codex_exec(prompt: str, timeout: int = 120) -> Optional[str]:
    """Run codex exec non-interactively, return the last message text."""
    codex = shutil.which('codex') or CODEX_BIN_DEFAULT
    if not os.path.isfile(codex):
        return None

    env = {**os.environ}
    env['PATH'] = f"{os.path.dirname(codex)}:{env.get('PATH', '')}"

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        subprocess.run(
            [
                codex, 'exec',
                '--ephemeral',
                '--skip-git-repo-check',
                '--full-auto',
                '--output-last-message', tmp_path,
                '-',
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if os.path.exists(tmp_path):
            with open(tmp_path) as f:
                return f.read().strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return None


def _openai_summarize(posts: list[ScoredPost], timeout: int = 60) -> tuple[dict[str, str], dict[str, str]]:
    """Fallback: call OpenAI API directly using codex auth token."""
    token = _load_codex_token()
    if not token:
        return {}, {}
    try:
        import openai
        client = openai.OpenAI(api_key=token)
        prompt = _build_prompt(posts)
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.2,
            timeout=timeout,
        )
        content = resp.choices[0].message.content or ''
        return _parse_summary_map(content)
    except Exception:
        return {}, {}


async def llm_summarize_posts(posts: list[ScoredPost], settings: Settings) -> None:
    """Populate post.record.summary and post.record.category for each post using codex exec in batches."""
    if not posts:
        return

    BATCH = 10
    summary_map: dict[str, str] = {}
    category_map: dict[str, str] = {}

    for i in range(0, len(posts), BATCH):
        batch = posts[i:i + BATCH]
        prompt = _build_prompt(batch)

        raw = _run_codex_exec(prompt, timeout=90)
        if raw:
            s, c = _parse_summary_map(raw)
            summary_map.update(s)
            category_map.update(c)

        # Fallback for posts still missing summaries in this batch
        missing = [p for p in batch if str(p.record.id) not in summary_map]
        if missing:
            s, c = _openai_summarize(missing)
            summary_map.update(s)
            category_map.update(c)

    # Apply summaries and categories; raw-text fallback for any still missing
    for post in posts:
        pid = str(post.record.id)
        summary = summary_map.get(pid)
        if not summary:
            summary = _fallback_summary(post.record.text)
        post.record.summary = summary
        post.record.category = category_map.get(pid)


def build_summary_sentences(posts: list[ScoredPost], sentence_count: int) -> list[str]:
    if not posts:
        return ['今天沒有足夠的內容可生成摘要。']
    sentence_count = max(3, min(5, sentence_count))
    kws = extract_keywords(posts, limit=6)
    top_keywords = join_phrases(kws[:3]) if kws else '幾個主題'
    secondary_keywords = join_phrases(kws[3:6]) if len(kws) > 3 else ''
    sentences = [
        f'今天的內容主要集中在 {top_keywords} 這幾個主題。',
        '整體來看，資訊密度偏高，值得追蹤的討論不少。',
        '這份摘要只保留可驗證的原文重點、連結與統計，不額外補故事。',
    ]
    if sentence_count >= 4 and secondary_keywords:
        sentences.append(f'次要線索則圍繞 {secondary_keywords} 展開，補足了前述主題的背景與細節。')
    if sentence_count >= 5:
        sentences.append('如果要先看內容，直接從各分類裡的單篇摘要與原文連結開始。')
    return sentences[:sentence_count]


def build_summary_bundle(
    posts: list[ScoredPost],
    settings: Settings,
    now: Optional[datetime] = None,
    raw_count: Optional[int] = None,
) -> SummaryBundle:
    now = now or datetime.now(timezone.utc)
    sentences = build_summary_sentences(posts, settings.summary_sentence_count)
    top_picks = posts[:5]
    secondary = posts[5:10]
    archive = posts[10:]
    source_count = len({item.record.handle or item.record.author for item in posts if (item.record.handle or item.record.author) != 'unknown'})
    return SummaryBundle(
        generated_at=now,
        sentences=sentences,
        top_picks=top_picks,
        secondary=secondary,
        archive=archive,
        source_count=source_count,
        raw_count=raw_count if raw_count is not None else len(posts),
    )

