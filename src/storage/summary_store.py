
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil
from typing import Optional

from src.domain import SummaryBundle
from src.web.build_html import render_summary_html, render_summary_markdown


def _run_dir(base_dir: str | Path, now: Optional[datetime] = None) -> Path:
    now = now or datetime.now(timezone.utc)
    return Path(base_dir) / now.strftime('%Y-%m-%d') / now.strftime('%Y%m%dT%H%M%SZ')


def write_summary_bundle(base_dir: str | Path, bundle: SummaryBundle, filename: str = 'index.html', now: Optional[datetime] = None, publish_latest: bool = True) -> dict[str, Path]:
    base_dir = Path(base_dir)
    out_dir = _run_dir(base_dir, now=now)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_dir.mkdir(parents=True, exist_ok=True)
    html = render_summary_html(bundle)
    md = render_summary_markdown(bundle)
    html_path = out_dir / filename
    json_path = out_dir / 'summary.json'
    md_path = out_dir / 'digest.md'
    html_path.write_text(html, encoding='utf-8')
    json_path.write_text(json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
    md_path.write_text(md, encoding='utf-8')
    latest_html_path = base_dir / filename
    latest_md_path = base_dir / 'digest.md'
    if publish_latest:
        latest_html_path.write_text(html, encoding='utf-8')
        latest_md_path.write_text(md, encoding='utf-8')
    return {'directory': out_dir, 'html': html_path, 'json': json_path, 'latest_html': latest_html_path, 'md': md_path, 'latest_md': latest_md_path}


def cleanup_summary_runs(base_dir: str | Path, retention_days: int, now: Optional[datetime] = None) -> list[Path]:
    """Delete daily summary directories older than retention_days."""
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
