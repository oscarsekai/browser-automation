
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Optional

from src.config import Settings
from src.domain import PostRecord, ScoredPost


WORD_RE = re.compile(r"[A-Za-z0-9']+")
FRONTEND_KEYS = (
    'react', 'vue', 'svelte', 'angular', 'next.js', 'nextjs', 'nuxt', 'astro',
    'tailwind', 'css', 'frontend', 'front-end', 'ui', 'ux', 'design system',
    'component', 'browser', 'web app', 'html', 'typescript', 'javascript', 'vite',
    'shadcn', 'radix', 'storybook',
)

TRAFFIC_KEYS = (
    'views',
    'view_count',
    'impressions',
    'likes',
    'replies',
    'repost_count',
    'reposts',
    'retweets',
    'comments',
    'bookmarks',
    'shares',
    'quote_count',
)


def tier_from_followers(post: PostRecord) -> str:
    explicit = (post.metadata or {}).get('source_tier')
    if explicit:
        return str(explicit).strip().upper()[0]
    followers = post.followers or 0
    if followers >= 1_000_000:
        return 'A'
    if followers >= 50_000:
        return 'B'
    return 'C'

def tier_weight(settings: Settings, tier: str) -> float:
    if tier == 'A':
        return settings.source_weight_a
    if tier == 'B':
        return settings.source_weight_b
    return settings.source_weight_c


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def freshness_score(post: PostRecord, now: datetime) -> float:
    delta = now - post.timestamp
    hours = max(delta.total_seconds() / 3600.0, 0.0)
    return clamp(1.0 - hours / 48.0)


def relevance_score(post: PostRecord, settings: Settings) -> float:
    text = post.text.lower()
    keywords = tuple(k.lower() for k in settings.focus_keywords if k.strip())
    frontend_bonus = frontend_signal(post) * settings.frontend_boost_weight
    if keywords:
        hits = sum(1 for keyword in keywords if keyword in text)
        return clamp((hits / max(len(keywords), 1)) + frontend_bonus)
    return clamp(0.35 + min(len(text) / 350.0, 0.4) + frontend_bonus)


def frontend_signal(post: PostRecord) -> float:
    text = (post.text or '').lower()
    hits = sum(1 for keyword in FRONTEND_KEYS if keyword in text)
    return clamp(hits / 4.0)


def density_score(post: PostRecord) -> float:
    tokens = WORD_RE.findall(post.text)
    if not tokens:
        return 0.0
    length_score = clamp(len(tokens) / 60.0)
    unique_ratio = len({token.lower() for token in tokens}) / len(tokens)
    return clamp((length_score * 0.7) + (unique_ratio * 0.3))


def originality_score(post: PostRecord) -> float:
    tokens = [token.lower() for token in WORD_RE.findall(post.text)]
    if not tokens:
        return 0.0
    unique_ratio = len(set(tokens)) / len(tokens)
    return clamp(unique_ratio)


def engagement_components(post: PostRecord) -> tuple[float, float, float]:
    followers = max(post.followers or 0, 0)
    follower_score = 0.0 if followers <= 0 else clamp(math.log10(followers + 1) / 6.0)
    meta = post.metadata or {}
    traffic_total = 0.0
    for key in TRAFFIC_KEYS:
        raw_value = meta.get(key)
        if raw_value is None:
            continue
        try:
            traffic_total += max(float(str(raw_value).replace(',', '').strip()), 0.0)
        except ValueError:
            continue
    traffic_score = clamp(math.log10(traffic_total + 1.0) / 6.0) if traffic_total > 0 else 0.0
    return follower_score, traffic_score, max(follower_score, traffic_score)


def engagement_score(post: PostRecord) -> float:
    return engagement_components(post)[2]


def duplicate_penalty(post: PostRecord) -> float:
    meta = post.metadata or {}
    if meta.get('duplicate'):
        return 1.0
    if meta.get('duplicate_of'):
        return 1.0
    return 0.0


def score_post(post: PostRecord, settings: Settings, now: Optional[datetime] = None) -> ScoredPost:
    now = now or datetime.now(timezone.utc)
    tier = tier_from_followers(post)
    tier_w = tier_weight(settings, tier)
    freshness = freshness_score(post, now)
    relevance = relevance_score(post, settings)
    density = density_score(post)
    originality = originality_score(post)
    follower_engagement, traffic_engagement, engagement = engagement_components(post)
    dup = duplicate_penalty(post)
    frontend_bias = frontend_signal(post)
    score = (
        tier_w
        + freshness * settings.freshness_weight
        + relevance * settings.relevance_weight
        + density * settings.density_weight
        + originality * settings.originality_weight
        + engagement * settings.engagement_weight
        + frontend_bias * settings.frontend_boost_weight
        - dup * settings.duplicate_penalty
    )
    reasons = []
    if freshness > 0.75:
        reasons.append('fresh')
    if engagement > 0.5:
        reasons.append('high-traffic' if (post.followers or 0) <= 0 else 'high-followers')
    if relevance > 0.5:
        reasons.append('relevant')
    if density > 0.5:
        reasons.append('dense')
    if originality > 0.5:
        reasons.append('original')
    if frontend_bias > 0.4:
        reasons.append('frontend-boost')
    if dup:
        reasons.append('duplicate-penalty')
    breakdown = {
        'tier_weight': tier_w,
        'freshness': freshness,
        'relevance': relevance,
        'density': density,
        'originality': originality,
        'engagement': engagement,
        'follower_engagement': follower_engagement,
        'traffic_engagement': traffic_engagement,
        'frontend_bias': frontend_bias,
        'duplicate_penalty': dup,
    }
    return ScoredPost(record=post, score=round(score, 6), tier=tier, reasons=tuple(reasons), breakdown=breakdown)


def rank_posts(posts: list[PostRecord], settings: Settings, now: Optional[datetime] = None) -> list[ScoredPost]:
    scored = [score_post(post, settings, now=now) for post in posts]
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[: settings.summary_top_n]
