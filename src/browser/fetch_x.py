
from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from src.domain import PostRecord


ARTICLE_RE = re.compile(r'<article([^>]*)>(.*?)</article>', re.I | re.S)
LINE_RE = re.compile(r'<div([^>]*)data-line="\d+"[^>]*>(.*?)</div>', re.I | re.S)
ATTR_RE = re.compile(r'([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(["\'])(.*?)\2', re.S)
URL_RE = re.compile(r'https?://x\.com/[A-Za-z0-9_]+/status/\d+', re.I)
HANDLE_RE = re.compile(r'@([A-Za-z0-9_]{1,15})')
# X.com-specific author/handle extraction patterns
AVATAR_HANDLE_RE = re.compile(r'UserAvatar-Container-([A-Za-z0-9_]+)', re.I)
STATUS_URL_HANDLE_RE = re.compile(r'https?://x\.com/([A-Za-z0-9_]+)/status/', re.I)
USER_NAME_DISPLAY_RE = re.compile(r'data-testid="User-Name"[^>]*>.*?<span[^>]*>([^<]+)</span>', re.I | re.S)
FOLLOWERS_RE = re.compile(r'([0-9]+(?:\.[0-9]+)?\s*[KMB]?)\s*Followers', re.I)
FOLLOWERS_RE2 = re.compile(r'Followers[:\s]+([0-9,]+)', re.I)
# Match tweetText and capture everything up to its closing tag (handles nested divs via balanced approach)
TWEET_TEXT_OUTER_RE = re.compile(r'data-testid="tweetText"([^>]*)>(.*)', re.I | re.S)
SOCIAL_PREFIX_RE = re.compile(
    r'^.*?(?:·\s*(?:\d+[hm]|\w{3,9}\s+\d{1,2}(?:,\s*\d{4})?)|'
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,\s*\d{4})?)\s*',
    re.I,
)
TRAILING_METRICS_RE = re.compile(r'\s+(?:\d+(?:\.\d+)?[KMB]?)(?:\s+\d+(?:\.\d+)?[KMB]?)*\s*$', re.I)
BOILERPLATE_PATTERNS = [
    re.compile(r'^\s*follow\s+for\s+more', re.I),
    re.compile(r'^\s*subscribe\s+for\s+more', re.I),
    re.compile(r'^\s*retweet\s+if', re.I),
    re.compile(r'^\s*like\s+and\s+repost', re.I),
    re.compile(r'^\s*ad\s*:', re.I),
]
# Patterns to strip from the middle/end of extracted text (word-boundary-safe)
INLINE_JUNK_RE = re.compile(
    r'(?:Translated from \w+|Show original|Show more)\s*'
    r'|\b(?:Reply|Repost|Like|Bookmark|Share)\b\s*',
    re.I,
)
# Strip interaction counts: "3 replies", "1.2K likes", etc.
INTERACTION_COUNT_RE = re.compile(
    r'\b\d+(?:\.\d+)?[KMB]?\s+(?:Replies|Reposts?|Likes?|Views?|Bookmarks?|Shares?|Comments?|Quotes?)\b',
    re.I,
)


class _TextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return normalize_whitespace(' '.join(self.parts))


def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def strip_tags(html: str) -> str:
    stripper = _TextStripper()
    stripper.feed(html)
    return stripper.get_text()


def parse_attrs(opening_tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _quote, value in ATTR_RE.findall(opening_tag):
        attrs[key.lower()] = value
    return attrs


def parse_followers(value: Optional[str], text: str) -> Optional[int]:
    candidate = value or _first_match(FOLLOWERS_RE, text) or _first_match(FOLLOWERS_RE2, text)
    if not candidate:
        return None
    candidate = candidate.replace(',', '').strip().upper()
    multiplier = 1
    if candidate.endswith('K'):
        multiplier = 1_000
        candidate = candidate[:-1]
    elif candidate.endswith('M'):
        multiplier = 1_000_000
        candidate = candidate[:-1]
    elif candidate.endswith('B'):
        multiplier = 1_000_000_000
        candidate = candidate[:-1]
    try:
        return int(float(candidate) * multiplier)
    except ValueError:
        return None


def parse_timestamp(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    cleaned = value.strip()
    for candidate in (cleaned, cleaned.replace('Z', '+00:00')):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _first_match(pattern: re.Pattern[str], text: str) -> Optional[str]:
    match = pattern.search(text)
    if match:
        return match.group(1)
    return None


def derive_handle(attrs: dict[str, str], body: str, url: Optional[str]) -> str:
    # Try X.com-specific patterns first (most reliable)
    m = AVATAR_HANDLE_RE.search(body)
    if m:
        return m.group(1)
    if url:
        m = STATUS_URL_HANDLE_RE.match(url)
        if m:
            return m.group(1)
    explicit = attrs.get('data-handle') or attrs.get('handle')
    if explicit:
        return explicit.lstrip('@')
    m = HANDLE_RE.search(body)
    return m.group(1) if m else 'unknown'


def derive_author(attrs: dict[str, str], handle: str, body: str) -> str:
    # Try X.com User-Name testid (display name)
    m = USER_NAME_DISPLAY_RE.search(body)
    if m:
        name = normalize_whitespace(m.group(1))
        if name:
            return name
    explicit = attrs.get('data-author') or attrs.get('author') or attrs.get('aria-label')
    if explicit:
        return normalize_whitespace(explicit).lstrip('@')
    if handle and handle != 'unknown':
        return handle
    return 'unknown'


def derive_url(attrs: dict[str, str], body: str) -> Optional[str]:
    explicit = attrs.get('data-url') or attrs.get('url')
    if explicit:
        return explicit
    status_match = re.search(r'<a[^>]+href="([^"]*/status/\d+[^"]*)"', body, re.I)
    if status_match:
        return urljoin('https://x.com', status_match.group(1))
    href_match = re.search(r'<a[^>]+href="([^"]+)"', body, re.I)
    if href_match:
        return urljoin('https://x.com', href_match.group(1))
    match = URL_RE.search(body)
    return match.group(0) if match else None


def derive_id(attrs: dict[str, str], url: Optional[str], index: int, source: str) -> str:
    return attrs.get('data-post-id') or attrs.get('id') or url or f'{source}:{index}'


def _extract_tweet_text(body: str) -> str:
    match = TWEET_TEXT_OUTER_RE.search(body or '')
    if not match:
        return ''
    rest = match.group(2)
    depth = 1
    pos = 0
    while pos < len(rest) and depth > 0:
        open_tag = re.search(r'<div[^>]*>', rest[pos:], re.I)
        close_tag = re.search(r'</div>', rest[pos:], re.I)
        if open_tag and (not close_tag or open_tag.start() < close_tag.start()):
            depth += 1
            pos += open_tag.end()
        elif close_tag:
            depth -= 1
            pos += close_tag.end()
        else:
            break
    return strip_tags(rest[:pos])


def clean_post_text(text: str) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ''
    cleaned = INTERACTION_COUNT_RE.sub('', cleaned)
    cleaned = INLINE_JUNK_RE.sub('', cleaned)
    cleaned = SOCIAL_PREFIX_RE.sub('', cleaned)
    cleaned = TRAILING_METRICS_RE.sub('', cleaned)
    cleaned = normalize_whitespace(cleaned)
    return cleaned


def looks_like_boilerplate(text: str) -> bool:
    lower = text.lower().strip()
    if not lower:
        return True
    if len(lower) < 12:
        return True
    if not any(ch.isalpha() for ch in lower):
        return True
    for pattern in BOILERPLATE_PATTERNS:
        if pattern.search(lower):
            return True
    return False


def extract_posts_from_html(html: str, source: str = 'x-home') -> list[PostRecord]:
    posts: list[PostRecord] = []
    for index, match in enumerate(ARTICLE_RE.finditer(html or ''), start=1):
        attrs = parse_attrs(match.group(1))
        body = match.group(2)
        text = clean_post_text(_extract_tweet_text(body) or strip_tags(body))
        if looks_like_boilerplate(text):
            continue
        url = derive_url(attrs, body)
        handle = derive_handle(attrs, body, url)
        author = derive_author(attrs, handle, body)
        followers = parse_followers(attrs.get('data-followers'), text)
        timestamp = parse_timestamp(attrs.get('data-time') or attrs.get('datetime') or attrs.get('data-created-at'))
        post = PostRecord(
            id=derive_id(attrs, url, index, source),
            source=source,
            timestamp=timestamp,
            author=author,
            handle=handle,
            text=text,
            url=url,
            followers=followers,
            raw_html=match.group(0),
            metadata=attrs,
        )
        posts.append(post)
    return posts


def load_html_from_path(path: str | Path, encoding: str = 'utf-8') -> str:
    return Path(path).read_text(encoding=encoding)
