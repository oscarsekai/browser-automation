from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from src.browser.fetch_x import extract_posts_from_html, load_html_from_path
from src.config import Settings
from src.domain import PostRecord

if TYPE_CHECKING:
    from src.browser.cdp import CDPBrowserAdapter

# Snapshot HTML every this many scroll steps to capture virtualized posts
_SNAPSHOT_BATCH = 5
# Stop early if no new posts appear for this many consecutive batches
_STALE_BATCH_LIMIT = 4
# Minimum posts before we honour early-stop
_EARLY_STOP_MIN_POSTS = 20


@runtime_checkable
class BrowserAdapter(Protocol):
    def goto(self, url: str) -> None: ...
    def scroll(self, times: int, pause_seconds: float) -> None: ...
    def snapshot_html(self) -> str: ...


@dataclass
class StaticHtmlAdapter:
    html: str
    current_url: Optional[str] = None
    scrolled: int = 0

    def goto(self, url: str) -> None:
        self.current_url = url

    def scroll(self, times: int, pause_seconds: float) -> None:
        self.scrolled += max(0, times)

    def snapshot_html(self) -> str:
        return self.html

    @classmethod
    def from_path(cls, path: Path) -> 'StaticHtmlAdapter':
        return cls(html=load_html_from_path(path))


class BrowserRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def collect_home(self, adapter: BrowserAdapter, html_source: str = 'x-home') -> list[PostRecord]:
        adapter.goto(self.settings.x_home_url)

        # X.com uses a virtualised list — posts leave the DOM as you scroll.
        # We must snapshot incrementally and deduplicate across batches.
        seen: dict[str, PostRecord] = {}
        stale_batches = 0

        for step in range(1, self.settings.scroll_count + 1):
            adapter.scroll(1, self.settings.scroll_pause_seconds)

            if step % _SNAPSHOT_BATCH == 0 or step == self.settings.scroll_count:
                html = adapter.snapshot_html()
                batch = extract_posts_from_html(html, source=html_source)
                new_count = 0
                for post in batch:
                    if post.id not in seen:
                        seen[post.id] = post
                        new_count += 1

                if new_count == 0:
                    stale_batches += 1
                else:
                    stale_batches = 0

                # Early stop: feed appears exhausted or errored out
                if stale_batches >= _STALE_BATCH_LIMIT and len(seen) >= _EARLY_STOP_MIN_POSTS:
                    break

        return list(seen.values())

    def collect_from_html(self, html: str, html_source: str = 'x-home') -> list[PostRecord]:
        return extract_posts_from_html(html, source=html_source)

    def collect_from_path(self, path: str | Path, html_source: str = 'x-home') -> list[PostRecord]:
        html = load_html_from_path(path)
        return extract_posts_from_html(html, source=html_source)

    def collect_home_cdp(self, adapter: CDPBrowserAdapter, html_source: str = 'x-home') -> list[PostRecord]:
        return self.collect_home(adapter, html_source=html_source)
