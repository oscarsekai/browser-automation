"""Self-scheduling daemon loop.

Starts a continuous collect → wait → collect → ... cycle.
When the daily collect count reaches ``collect_target``, the loop automatically
runs the full build phase (summarise → write HTML/digest → git commit + push)
then continues to the next cycle.

Usage::

    python -m src.scheduler.loop                     # run forever with .env.local config
    python -m src.scheduler.loop --interval 300      # override interval (seconds)
    python -m src.scheduler.loop --target 2          # build after every 2 collects

Environment variables (read from .env.local):
    COLLECT_INTERVAL_SECONDS   Seconds between collect cycles (default: 28800 = 8 h)
    COLLECT_TARGET             Number of daily collects before a build (default: 3)
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

from src.config import load_settings
from src.scheduler.collect_state import bump
from src.scheduler.run_once import _build_phase, _collect_phase


def loop(
    workspace_root: Optional[Path] = None,
    interval_seconds: Optional[int] = None,
    target: Optional[int] = None,
    run_once: bool = False,
    force_build: bool = False,
    html_source_path: Optional[Path] = None,
) -> None:
    """Run the collect→build daemon loop indefinitely.

    Each iteration:
    1. Reload settings (picks up .env.local changes without restart).
    2. Run CDP collect phase (restarts Chrome, scrapes, persists raw posts).
    3. Increment the daily counter via ``bump()``.
    4. If the counter reached ``target`` (or ``force_build`` is set), run build+commit+push.
    5. Sleep ``interval_seconds`` then repeat (unless ``run_once`` is True).

    Args:
        run_once:    Exit after one collect (+ optional build) cycle.
        force_build: Build after this collect regardless of the daily counter.
    """
    workspace_root = Path(workspace_root) if workspace_root is not None else Path.cwd()

    _initial = load_settings(workspace_root)
    interval = interval_seconds if interval_seconds is not None else _initial.collect_interval_seconds
    tgt = target if target is not None else _initial.collect_target

    if run_once:
        print(f'[loop] one-shot mode — collect once{"+ force-build" if force_build else ""}')
    else:
        print(f'[loop] started — collect every {interval}s, build every {tgt} collects/day')

    while True:
        settings = load_settings(workspace_root)
        effective_interval = interval_seconds if interval_seconds is not None else settings.collect_interval_seconds
        effective_target = target if target is not None else settings.collect_target

        try:
            _raw_dir, _raw_posts = _collect_phase(
                workspace_root,
                settings,
                html_source_path=html_source_path,
                cdp_host=None,
                cdp_port=None,
                cdp_target_url=None,
            )
        except Exception as exc:
            print(f'[loop] collect failed: {exc} — skipping this cycle')
            if run_once:
                return
            print(f'[loop] sleeping {effective_interval}s before retry...')
            time.sleep(effective_interval)
            continue

        data_dir = workspace_root / settings.raw_dir
        count, should_build = bump(data_dir, target=effective_target)
        print(f'[loop] collect #{count}/{effective_target} done')

        if should_build or force_build:
            print('[loop] building + commit + push...')
            try:
                _build_phase(workspace_root, settings)
                print('[loop] build complete')
            except Exception as exc:
                print(f'[loop] build failed: {exc}')
            # reset force_build so subsequent cycles follow normal counter logic
            force_build = False

        if run_once:
            return

        print(f'[loop] sleeping {effective_interval}s until next collect...')
        time.sleep(effective_interval)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description='Self-scheduling collect→build daemon for browser-automation'
    )
    parser.add_argument(
        '--workspace-root',
        default='.',
        help='Workspace root directory (default: current directory)',
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=None,
        metavar='SECONDS',
        help='Override COLLECT_INTERVAL_SECONDS — seconds between collect runs',
    )
    parser.add_argument(
        '--target',
        type=int,
        default=None,
        metavar='N',
        help='Override COLLECT_TARGET — number of daily collects before a build',
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Collect once (+ build if target reached) then exit — useful for manual / cron use',
    )
    parser.add_argument(
        '--force-build',
        action='store_true',
        help='Build immediately after this collect, regardless of the daily counter',
    )
    parser.add_argument(
        '--html-source',
        default=None,
        metavar='PATH',
        help='Use a saved HTML snapshot instead of live CDP (for testing / offline use)',
    )
    args = parser.parse_args(argv)

    try:
        loop(
            workspace_root=Path(args.workspace_root),
            interval_seconds=args.interval,
            target=args.target,
            run_once=args.once,
            force_build=args.force_build,
            html_source_path=Path(args.html_source) if args.html_source else None,
        )
    except KeyboardInterrupt:
        print('\n[loop] interrupted by user — stopping')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
