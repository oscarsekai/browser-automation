"""Tracks how many collect runs have happened today.

State is persisted to ``data/.collect_state.json`` so cron restarts don't
lose the counter.  The counter auto-resets when the date changes (UTC).

Usage::

    from src.scheduler.collect_state import bump
    count, should_build = bump(workspace_root / 'data', target=3)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


_STATE_FILE = '.collect_state.json'


def _today() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _load(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'date': '', 'count': 0}


def bump(base_dir: str | Path, target: int = 3) -> tuple[int, bool]:
    """Increment today's collect counter and return (count, should_build).

    ``should_build`` is ``True`` exactly when the counter reaches ``target``,
    after which the counter resets to 0 so the next cycle can start fresh.

    Args:
        base_dir: The data directory (e.g. ``workspace_root / 'data'``).
        target: Number of collects before a build is triggered.

    Returns:
        A tuple ``(count, should_build)`` where ``count`` is the new value
        after incrementing and ``should_build`` is whether a build should run.
    """
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    state_path = base_path / _STATE_FILE

    state = _load(state_path)
    today = _today()

    if state.get('date') != today:
        state = {'date': today, 'count': 0}

    state['count'] += 1
    count = state['count']
    should_build = count >= target

    if should_build:
        state['count'] = 0

    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    return count, should_build
