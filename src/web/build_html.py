from __future__ import annotations

import re
from html import escape
from typing import Iterable

from src.domain import ScoredPost, SummaryBundle


SECTION_ORDER = ['ai', 'geopolitics', 'engineering', 'frontend', 'security', 'finance', 'other']

SECTION_META: dict[str, str] = {
    'ai':          '🤖 AI 模型與工具',
    'geopolitics': '🌐 地緣政治',
    'engineering': '⚙️ 軟體工程',
    'frontend':    '🖥️ 前端開發',
    'security':    '🔐 資安與隱私',
    'finance':     '💰 財經',
    'other':       '🧩 其他觀察',
}

# Per-section hard cap (None = unlimited)
SECTION_CAPS: dict[str, int] = {
    'ai': 20,
    'engineering': 15,
    'other': 5,
}

THEME_RULES: list[tuple[str, tuple[str, ...]]] = [
    # AI must be first — it's the broadest and highest-priority topic.
    # Without this, Claude/GPT posts mentioning 'python' or 'github' would
    # fall into engineering instead.
    (
        'ai',
        (
            'claude', 'codex', 'gpt', 'anthropic', 'openai', 'minimax', 'llm', 'llms',
            'model', 'models', 'agent', 'agents', 'inference', 'swe-bench', 'terminal bench',
            'prompt', 'prompting', 'cursor', 'windsurf', 'gemini', 'copilot',
            'vibe coding', 'ai coding', 'ai agent',
        ),
    ),
    (
        'geopolitics',
        (
            'hormuz', 'strait', 'iran', 'trump', 'tariff', 'blockade', 'blockaded', 'shipping',
            'oil', 'war', 'navy', 'middle east', 'geopolit', 'china', 'canada', 'spain', 'pakistan',
            'israel', 'ukraine', 'russia', 'palestine',
        ),
    ),
    (
        'security',
        (
            'security', 'vulnerability', 'cve', 'exploit', 'hack', 'breach', 'leak',
            'privacy', 'encrypted', 'e2e', 'password', 'phishing', 'malware', 'zero-day',
        ),
    ),
    (
        'engineering',
        (
            # backend / infra
            'backend', 'postgres', 'postgresql', 'mysql', 'sqlite', 'redis', 'kafka', 'rabbitmq',
            'docker', 'kubernetes', 'k8s', 'terraform', 'ansible', 'ci/cd', 'github actions',
            'deploy', 'deployment', 'microservice', 'monolith', 'architecture', 'system design',
            'api design', 'grpc', 'graphql', 'websocket', 'load balancer',
            # languages (non-frontend focused)
            'golang', 'rust', 'python', 'nodejs', 'node.js', 'deno',
            'java', 'kotlin', 'scala', 'elixir', 'haskell', 'c++',
            # tooling / workflow
            'refactor', 'code review', 'unit test', 'integration test', 'tdd',
            'open source', 'devops', 'sre', 'observability', 'tracing', 'monitoring',
            # general engineering
            'software engineer', 'software engineering', 'developer experience',
        ),
    ),
    (
        'frontend',
        (
            'react', 'vue', 'svelte', 'angular', 'next.js', 'nextjs', 'nuxt', 'astro',
            'vite', 'tailwind', 'shadcn', 'radix', 'frontend', 'front-end',
            'css', 'design system', 'web component', 'vercel', 'netlify',
        ),
    ),
    (
        'finance',
        (
            'market', 'markets', 'oil price', 'oil futures', 'saas', 'valuation', 'reprice',
            'stock', 'equity', 'fund', 'invest', 'finance', 'financial', 'mrr', 'revenue', 'earnings',
        ),
    ),
]


def _jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r'[a-z0-9]{3,}', a.lower()))
    tb = set(re.findall(r'[a-z0-9]{3,}', b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _dedup_posts(posts: list[ScoredPost], threshold: float = 0.45) -> list[ScoredPost]:
    """Keep highest-scored post when two posts have high token overlap."""
    kept: list[ScoredPost] = []
    for post in posts:
        if not any(_jaccard(post.record.text, k.record.text) >= threshold for k in kept):
            kept.append(post)
    return kept


def _contains_keyword(text: str, keyword: str) -> bool:
    needle = keyword.strip().lower()
    if not needle:
        return False
    haystack = (text or '').lower()
    if ' ' in needle:
        return needle in haystack
    return re.search(rf'\b{re.escape(needle)}\b', haystack) is not None


def _theme_for_text(text: str) -> str:
    for theme, keywords in THEME_RULES:
        if any(_contains_keyword(text, keyword) for keyword in keywords):
            return theme
    return 'other'


def _theme_for_post(post: ScoredPost) -> str:
    """Use AI-assigned category if available, fall back to keyword matching."""
    cat = (post.record.category or '').strip().lower()
    if cat and cat in {name for name in SECTION_ORDER}:
        return cat
    return _theme_for_text(post.record.text)


def _group_posts(posts: Iterable[ScoredPost]) -> dict[str, list[ScoredPost]]:
    grouped: dict[str, list[ScoredPost]] = {name: [] for name in SECTION_ORDER}
    for post in posts:
        grouped[_theme_for_post(post)].append(post)
    # Deduplicate within each section, then apply per-section cap
    for theme in SECTION_ORDER:
        grouped[theme] = _dedup_posts(grouped[theme])
        cap = SECTION_CAPS.get(theme)
        if cap is not None:
            grouped[theme] = grouped[theme][:cap]
    return grouped


def _condense_text(text: str, limit: int = 200) -> str:
    clean = re.sub(r'\s+', ' ', text or '').strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + '…'


def _post_link(post: ScoredPost) -> str:
    record = post.record
    if not record.url:
        return ''
    return f'<a class="item-link" href="{escape(record.url)}" target="_blank" rel="noreferrer">查看推文</a>'


def _fallback_text(text: str, limit: int = 180) -> str:
    clean = re.sub(r'\s+', ' ', text or '').strip()
    return clean[:limit]


_ENGINEERING_SUBTITLES: list[tuple[str, list[str]]] = [
    ('⚙️ DevOps 與基礎設施', ['docker', 'kubernetes', 'k8s', 'ci/cd', 'cicd', 'terraform', 'ansible', 'helm', 'deploy', 'container', 'pipeline', 'infra', 'nginx', 'prometheus', 'grafana', 'observability']),
    ('⚙️ 後端開發',          ['api', 'database', 'golang', 'rust', 'python', 'django', 'fastapi', 'microservice', 'grpc', 'sql', 'postgres', 'redis', 'backend', 'server-side', 'rabbitmq', 'kafka', 'orm']),
    ('⚙️ 前端開發',          ['react', 'vue', 'svelte', 'css', 'javascript', 'typescript', 'next.js', 'nextjs', 'tailwind', 'component', 'frontend', 'web dev', 'html', 'browser']),
    ('⚙️ 行動開發',          ['ios', 'android', 'swift', 'flutter', 'react native', 'mobile app', 'xcode']),
    ('⚙️ 系統設計',          ['architecture', 'distributed', 'scalability', 'latency', 'system design', 'microservices', 'event-driven', 'cap theorem', 'consistency']),
    ('⚙️ 開發工具',          ['editor', 'vim', 'vscode', 'ide', 'debugger', 'profiler', 'build tool', 'webpack', 'vite', 'git', 'github', 'refactor', 'testing', 'unit test']),
]


def _section_title(theme: str, posts: list[ScoredPost]) -> str:
    """Return display title for a section; engineering is dynamically derived."""
    if theme != 'engineering' or not posts:
        return SECTION_META[theme]
    combined = ' '.join(
        ((p.record.text or '') + ' ' + (p.record.summary or '')).lower()
        for p in posts
    )
    scores = {label: sum(combined.count(kw) for kw in kws) for label, kws in _ENGINEERING_SUBTITLES}
    best, best_score = max(scores.items(), key=lambda x: x[1])
    return best if best_score >= 2 else SECTION_META['engineering']


def _render_item(post: ScoredPost) -> str:
    raw_text = post.record.summary or _fallback_text(post.record.text)
    text = escape(_condense_text(raw_text, limit=200))
    link = _post_link(post)
    return (
        '\n          <div class="item">'
        '\n            <div class="item-dot"></div>'
        '\n            <div class="item-body">'
        f'\n              <p class="item-text">{text}</p>'
        f'\n              {link}'
        '\n            </div>'
        '\n          </div>'
    )


def _render_section(theme: str, posts: list[ScoredPost]) -> str:
    if not posts:
        return ''
    title = _section_title(theme, posts)
    items = ''.join(_render_item(post) for post in posts)
    return (
        f'\n      <section class="section">'
        f'\n        <div class="section-header">'
        f'\n          <span class="section-title">{title}</span>'
        f'\n          <span class="section-count">{len(posts)} 則</span>'
        f'\n        </div>'
        f'\n        <div class="item-list">{items}'
        f'\n        </div>'
        f'\n      </section>'
    )


def _build_hero_desc(grouped: dict[str, list[ScoredPost]], total: int) -> str:
    active = [_section_title(t, grouped[t]) for t in SECTION_ORDER if grouped[t]]
    if not active:
        return f'精選 {total} 則核心動態。'
    topic_str = '、'.join(active[:-1]) + (f' 與 {active[-1]}' if len(active) > 1 else active[0])
    return f'今日話題涵蓋 {topic_str}，精選 {total} 則核心動態。'


def _build_summary_line(grouped: dict[str, list[ScoredPost]]) -> str:
    active = [(_section_title(t, grouped[t]), len(grouped[t])) for t in SECTION_ORDER if grouped[t]]
    if not active:
        return '今天沒有足夠的內容可生成摘要。'
    parts = '、'.join(f'{title}（{count} 則）' for title, count in active)
    return f'本次討論主要集中於：{parts}。'


def _build_tags(grouped: dict[str, list[ScoredPost]]) -> str:
    tags = [
        f'<span class="tag">{_section_title(t, grouped[t])} {len(grouped[t])} 則</span>'
        for t in SECTION_ORDER if grouped[t]
    ]
    return '\n            '.join(tags)


_CSS = '''\
    :root {
      color-scheme: dark;
      --bg: #060816;
      --surface: rgba(10, 14, 30, 0.9);
      --border: rgba(98, 143, 255, 0.18);
      --border-strong: rgba(98, 143, 255, 0.38);
      --text: #e4eaff;
      --text-secondary: #7d93bc;
      --accent: #6fa3ff;
      --accent-dim: rgba(111, 163, 255, 0.1);
      --shadow-sm: 0 4px 20px rgba(0, 0, 0, 0.4);
      --shadow-lg: 0 24px 64px rgba(0, 0, 0, 0.55);
      --radius-lg: 18px;
      --radius-md: 12px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html {
      min-height: 100%;
      background:
        radial-gradient(ellipse 70% 45% at 8% 0%, rgba(50, 90, 200, 0.2), transparent),
        radial-gradient(ellipse 55% 35% at 92% 8%, rgba(90, 130, 240, 0.12), transparent),
        linear-gradient(180deg, #03040d 0%, var(--bg) 55%, #020308 100%);
    }
    body {
      font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      color: var(--text);
      background: transparent;
      line-height: 1.7;
    }
    .page { max-width: 960px; margin: auto; padding: 60px 40px 80px; }
    .hero {
      padding: 30px 28px 26px;
      border-radius: var(--radius-lg);
      background: linear-gradient(160deg, rgba(18, 28, 62, 0.97) 0%, rgba(7, 9, 20, 0.98) 100%);
      border: 1px solid var(--border-strong);
      box-shadow: var(--shadow-lg);
      margin-bottom: 22px;
    }
    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: var(--accent);
      background: var(--accent-dim);
      border: 1px solid rgba(111, 163, 255, 0.22);
      border-radius: 100px;
      padding: 3px 12px;
      margin-bottom: 14px;
    }
    .hero h1 {
      font-size: clamp(1.7rem, 4vw, 2.6rem);
      font-weight: 800;
      letter-spacing: -0.04em;
      line-height: 1.1;
      color: #f0f4ff;
      margin-bottom: 10px;
    }
    .hero-desc { font-size: 0.92rem; color: var(--text-secondary); line-height: 1.65; margin-bottom: 5px; }
    .section {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 22px 24px;
      margin-bottom: 18px;
      box-shadow: var(--shadow-sm);
    }
    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }
    .section-title { font-size: 0.95rem; font-weight: 700; color: #eef2ff; }
    .section-count {
      font-size: 0.7rem;
      color: var(--text-secondary);
      background: rgba(98, 143, 255, 0.08);
      border: 1px solid var(--border);
      border-radius: 100px;
      padding: 2px 10px;
    }
    .item-list { display: flex; flex-direction: column; gap: 0; }
    .item {
      display: flex;
      align-items: baseline;
      gap: 10px;
      padding: 12px 0;
      border-bottom: 1px solid rgba(98, 143, 255, 0.08);
    }
    .item:last-child { border-bottom: none; padding-bottom: 0; }
    .item:first-child { padding-top: 0; }
    .item-dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: rgba(111, 163, 255, 0.45);
      flex-shrink: 0;
      margin-top: 10px;
    }
    .item-body {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: row;
      gap: 16px;
      align-items: flex-start;
      justify-content: space-between;
    }
    .item-text { font-size: 0.88rem; color: var(--text); line-height: 1.7; }
    .item-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 0.75rem;
      color: var(--accent);
      text-decoration: none;
      opacity: 0.75;
      transition: opacity 0.15s;
      flex-shrink: 0;
      margin-top: 2px;
      white-space: nowrap;
    }
    .item-link:hover { opacity: 1; }
    .item-link::after { content: '↗'; font-size: 0.7rem; }
    .footer-grid { display: flex; flex-direction: column; gap: 18px; }
    .footer-panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 20px 22px;
      box-shadow: var(--shadow-sm);
    }
    .footer-panel h2 {
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-secondary);
      margin-bottom: 12px;
    }
    .footer-panel p { font-size: 0.88rem; color: var(--text); line-height: 1.7; }
    .tags { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
    .tag {
      font-size: 0.73rem;
      color: var(--text-secondary);
      background: rgba(98, 143, 255, 0.07);
      border: 1px solid var(--border);
      border-radius: 100px;
      padding: 3px 10px;
    }
    @media (max-width: 600px) {
      .page { padding: 20px 14px 60px; }
      .hero { padding: 22px 18px; }
      .section { padding: 18px 16px; }
      .item-body { flex-direction: column; gap: 8px; }
      .item-link { align-self: flex-start; margin-top: 0; }
    }'''


def render_summary_markdown(bundle: SummaryBundle, title: str = 'X 動態摘要') -> str:
    """Render a clean Markdown version of the digest — token-efficient for AI agents."""
    all_posts = [*bundle.top_picks, *bundle.secondary, *bundle.archive]
    grouped = _group_posts(all_posts)
    total_selected = len(all_posts)

    date_str = bundle.generated_at.strftime('%Y 年 %-m 月 %-d 日')
    time_str = bundle.generated_at.strftime('%H:%M UTC')

    lines: list[str] = []
    lines.append(f'# {title}')
    lines.append(f'📅 {date_str} ｜ 最後更新：{time_str}')
    lines.append('')

    hero_desc = _build_hero_desc(grouped, total_selected)
    lines.append(hero_desc)
    lines.append('')

    for theme in SECTION_ORDER:
        posts = grouped.get(theme, [])
        if not posts:
            continue
        section_title = _section_title(theme, posts)
        lines.append(f'## {section_title}')
        lines.append('')
        for post in posts:
            text = post.record.summary or _fallback_text(post.record.text)
            text = re.sub(r'\s+', ' ', text or '').strip()
            url = post.record.url or ''
            if url:
                lines.append(f'- {text} [↗]({url})')
            else:
                lines.append(f'- {text}')
        lines.append('')

    lines.append('---')
    lines.append(f'📊 採集 {bundle.raw_count} 條，精選 {total_selected} 則 ｜ 來源：X ｜ 更新：{time_str}')

    return '\n'.join(lines)


def render_summary_html(bundle: SummaryBundle, title: str = 'X 動態摘要') -> str:
    all_posts = [*bundle.top_picks, *bundle.secondary, *bundle.archive]
    grouped = _group_posts(all_posts)
    total_selected = len(all_posts)

    date_str = bundle.generated_at.strftime('📅 %Y 年 %-m 月 %-d 日')
    time_str = bundle.generated_at.strftime('%H:%M UTC')
    hero_desc = _build_hero_desc(grouped, total_selected)
    summary_line = _build_summary_line(grouped)
    tags_html = _build_tags(grouped)

    topic_sections = ''.join(
        _render_section(theme, grouped[theme])
        for theme in SECTION_ORDER
        if grouped[theme]
    )

    return f'''<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <style>
{_CSS}
    </style>
  </head>
  <body>
    <main class="page">
      <section class="hero">
        <div class="hero-badge">{date_str}</div>
        <h1>{escape(title)}</h1>
        <p class="hero-desc">{escape(hero_desc)}</p>
      </section>

      {topic_sections}

      <div class="footer-grid">
        <div class="footer-panel">
          <h2>📊 收集統計</h2>
          <p>本次共採集 <strong>{bundle.raw_count}</strong> 條推文，精選 <strong>{total_selected}</strong> 則核心動態。</p>
          <p style="margin-top: 7px; color: var(--text-secondary); font-size: 0.85rem;">來源：X ｜更新時間：{time_str}</p>
          <div class="tags">
            {tags_html}
          </div>
        </div>
        <div class="footer-panel">
          <h2>📝 今日總結</h2>
          <p>{escape(summary_line)}</p>
        </div>
      </div>
    </main>
  </body>
</html>'''

