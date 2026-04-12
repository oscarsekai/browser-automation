
from __future__ import annotations

from difflib import SequenceMatcher
import re

from src.domain import DroppedRecord, FilterResult, PostRecord


NOISE_PATTERNS = [
    # Self-promotion / engagement bait
    re.compile(r'^\s*follow\s+for\s+more', re.I),
    re.compile(r'^\s*subscribe\s+for\s+more', re.I),
    re.compile(r'^\s*retweet\s+if', re.I),
    re.compile(r'^\s*like\s+and\s+repost', re.I),
    re.compile(r'^\s*ad\s*:', re.I),
    re.compile(r'\blike\s+and\s+share\b', re.I),
    re.compile(r'\bcomment\s+below\b', re.I),
    re.compile(r'\bdrop\s+a\s+(?:like|comment|follow)\b', re.I),
    re.compile(r'\bclick\s+(?:the\s+)?(?:link|bell|button)\b', re.I),
    # Inspirational fluff / empty positivity
    re.compile(r'^\s*(?:good\s+morning|gm|gn)\b', re.I),
    re.compile(r'\bkeep\s+(?:grinding|hustling|pushing)\b', re.I),
    re.compile(r'\bnever\s+(?:give\s+up|stop\s+dreaming)\b', re.I),
    re.compile(r'\bbelieve\s+in\s+yourself\b', re.I),
    re.compile(r'\bhard\s+work\s+pays?\s+off\b', re.I),
    # Engagement bait
    re.compile(r'\bwho\s+(?:agrees?|relates?)\s*\?', re.I),
    re.compile(r'\blet\s+me\s+know\s+in\s+the\s+comments\b', re.I),
    re.compile(r'\bsave\s+this\s+(?:post|tweet|thread)\b', re.I),
]


def normalize_text(text: str) -> str:
    text = re.sub(r'https?://\S+', ' ', text or '')
    text = re.sub(r'@([A-Za-z0-9_]{1,15})', '@', text)
    text = re.sub(r'[^\w\s@#.-]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


def canonical_text(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r'(rt|via)', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def is_noise(record: PostRecord) -> bool:
    text = (record.text or '').strip()
    if not text:
        return True
    normalized = text.lower().strip()
    if len(normalized) < 40:
        return True
    if not any(ch.isalpha() for ch in normalized):
        return True
    if not any(ch.isdigit() for ch in normalized) and len(normalized.split()) <= 2:
        return True
    for pattern in NOISE_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def is_duplicate(candidate: PostRecord, seen: list[PostRecord], threshold: float = 0.92) -> bool:
    candidate_text = canonical_text(candidate.text)
    for existing in seen:
        existing_text = canonical_text(existing.text)
        if not candidate_text or not existing_text:
            continue
        if candidate_text == existing_text:
            return True
        if SequenceMatcher(None, candidate_text, existing_text).ratio() >= threshold:
            return True
    return False


def filter_posts(posts: list[PostRecord]) -> FilterResult:
    kept: list[PostRecord] = []
    dropped: list[DroppedRecord] = []
    for post in posts:
        if is_noise(post):
            dropped.append(DroppedRecord(post, 'noise'))
            continue
        if is_duplicate(post, kept):
            dropped.append(DroppedRecord(post, 'duplicate'))
            continue
        kept.append(post)
    return FilterResult(kept=kept, dropped=dropped)
