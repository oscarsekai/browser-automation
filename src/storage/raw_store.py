
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil
from typing import Any, Optional

from src.domain import PostRecord


def _default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _run_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime('%Y%m%dT%H%M%SZ')


def write_raw_run(base_dir: str | Path, posts: list[PostRecord], metadata: Optional[dict[str, Any]] = None, now: Optional[datetime] = None) -> Path:
    base_path = Path(base_dir)
    now = now or datetime.now(timezone.utc)
    day_dir = base_path / now.strftime('%Y-%m-%d') / _run_id(now)
    day_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'generated_at': now.isoformat(),
        'post_count': len(posts),
        'metadata': metadata or {},
    }
    (day_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, default=_default), encoding='utf-8')
    (day_dir / 'posts.json').write_text(
        json.dumps([post.to_dict() for post in posts], indent=2, ensure_ascii=False, default=_default),
        encoding='utf-8',
    )
    return day_dir


def load_raw_run(run_dir: str | Path) -> dict[str, Any]:
    run_path = Path(run_dir)
    manifest = json.loads((run_path / 'manifest.json').read_text(encoding='utf-8'))
    posts = json.loads((run_path / 'posts.json').read_text(encoding='utf-8'))
    return {'manifest': manifest, 'posts': posts}


def load_today_posts(base_dir: str | Path, now: Optional[datetime] = None) -> list[PostRecord]:
    """Load and deduplicate all PostRecords collected today.

    Scans every ``YYYY-MM-DD/HHMMSSZ/posts.json`` under *base_dir* for
    today's date (UTC), reconstructs ``PostRecord`` objects, and returns a
    URL-deduplicated merged list (first occurrence wins).
    """
    base_path = Path(base_dir)
    today = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%d')
    day_dir = base_path / today
    if not day_dir.exists():
        return []

    seen_urls: set[str] = set()
    merged: list[PostRecord] = []

    for run_dir in sorted(day_dir.iterdir()):
        posts_file = run_dir / 'posts.json'
        if not posts_file.exists():
            continue
        try:
            raw_list: list[dict] = json.loads(posts_file.read_text(encoding='utf-8'))
        except Exception:
            continue
        for d in raw_list:
            # Reconstruct timestamp (stored as ISO string)
            ts = d.get('timestamp')
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    ts = datetime.now(timezone.utc)
            post = PostRecord(
                id=d.get('id', ''),
                source=d.get('source', ''),
                timestamp=ts,
                author=d.get('author', ''),
                handle=d.get('handle', ''),
                text=d.get('text', ''),
                url=d.get('url'),
                followers=d.get('followers'),
                raw_html=d.get('raw_html'),
                summary=d.get('summary'),
                category=d.get('category'),
                metadata=d.get('metadata', {}),
            )
            dedup_key = post.url or post.id
            if dedup_key in seen_urls:
                continue
            seen_urls.add(dedup_key)
            merged.append(post)

    return merged


def cleanup_raw_runs(base_dir: str | Path, retention_days: int, now: Optional[datetime] = None) -> list[Path]:
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    removed: list[Path] = []
    for day_dir in base_path.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            day_dt = datetime.strptime(day_dir.name, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if day_dt < cutoff:
            shutil.rmtree(day_dir)
            removed.append(day_dir)
    return removed
