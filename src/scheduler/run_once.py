from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from src.config import load_settings
from src.pipeline.filter import filter_posts
from src.pipeline.rank import rank_posts
from src.pipeline.summarize import build_summary_bundle, llm_summarize_posts
from src.storage.raw_store import cleanup_raw_runs, load_today_posts, write_raw_run
from src.storage.summary_store import cleanup_summary_runs, write_summary_bundle
from src.scheduler.collect_state import bump

_CHROME_APP = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def _find_chrome_main_pid(port: int) -> Optional[int]:
    try:
        result = subprocess.run(['ps', '-ax', '-o', 'pid=,command='], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) < 2:
                continue
            pid_str, cmd = parts
            if f'--remote-debugging-port={port}' in cmd and 'Google Chrome' in cmd and 'Helper' not in cmd:
                return int(pid_str)
    except Exception:
        pass
    return None


def restart_chrome(port: int, profile: str | None = None) -> None:
    """Kill existing Chrome on port, relaunch, wait for CDP to be ready."""
    if profile is None:
        profile = os.environ.get('CHROME_USER_DATA_DIR', '$HOME/chrome-hermes-profile')
    profile_path = os.path.expanduser(os.path.expandvars(profile))
    pid = _find_chrome_main_pid(port)
    if pid:
        print(f'[chrome] killing PID {pid} on port {port}...')
        os.kill(pid, signal.SIGTERM)
        time.sleep(3.0)

    print(f'[chrome] launching Chrome on port {port}...')
    subprocess.Popen(
        [
            _CHROME_APP,
            f'--remote-debugging-port={port}',
            f'--user-data-dir={profile_path}',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-default-apps',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 25.0
    while time.time() < deadline:
        try:
            with socket.create_connection(('localhost', port), timeout=1.0):
                time.sleep(2.0)
                print(f'[chrome] CDP ready on port {port}')
                return
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    print(f'[chrome] WARNING: CDP port {port} not ready after 25s — proceeding anyway')


def _build_adapter(
    workspace_root: Path,
    settings,
    html_source_path: Optional[Path] = None,
    cdp_host: Optional[str] = None,
    cdp_port: Optional[int] = None,
    cdp_target_url: Optional[str] = None,
):
    from src.browser.runner import StaticHtmlAdapter

    if html_source_path is not None:
        return StaticHtmlAdapter.from_path(html_source_path), 'html'

    from src.browser.cdp import CDPBrowserAdapter

    port = cdp_port if cdp_port is not None else settings.cdp_remote_debugging_port
    if port is None:
        raise ValueError('Provide --html-source for snapshot replay or set CDP_REMOTE_DEBUGGING_PORT to use live CDP')
    host = cdp_host or settings.cdp_remote_debugging_host
    target_url = cdp_target_url or settings.cdp_target_url
    return CDPBrowserAdapter.from_remote_debugging_port(host=host, port=port, target_url=target_url), 'cdp'


def _summarize_git_output(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ''
    for line in lines:
        if 'Everything up-to-date' in line:
            return 'Everything up-to-date'
        if '->' in line or 'To ' in line or 'branch' in line.lower():
            return line
    return lines[-1]


def _git_commit_and_push(repo_root: Path, index_html: Path) -> dict[str, str]:
    """Stage index.html + digest.md, commit with today's date, and push."""
    from datetime import datetime, timezone
    label = datetime.now(timezone.utc).strftime('%Y/%-m/%-d')
    msg = f'{label} summary'
    digest_md = repo_root / 'digest.md'
    try:
        subprocess.run(['git', 'add', str(index_html)], cwd=repo_root, check=True, capture_output=True, text=True)
        if digest_md.exists():
            subprocess.run(['git', 'add', str(digest_md)], cwd=repo_root, check=True, capture_output=True, text=True)
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=repo_root, capture_output=True, text=True,
        )
        if result.returncode == 0:
            print('[git] nothing changed, skipping commit')
            return {'status': 'nothing-changed', 'message': 'nothing changed'}
        commit_result = subprocess.run(
            ['git', 'commit', '-m', msg],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        push_result = subprocess.run(
            ['git', 'push'],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        push_summary = _summarize_git_output('\n'.join(filter(None, [push_result.stdout, push_result.stderr])))
        if push_summary == 'Everything up-to-date':
            print('[git] push completed: Everything up-to-date')
            return {'status': 'up-to-date', 'message': push_summary}
        commit_summary = _summarize_git_output(commit_result.stdout) or msg
        if push_summary:
            print(f'[git] push completed: {push_summary}')
        else:
            print(f'[git] push completed after commit: {commit_summary}')
        return {'status': 'pushed', 'message': push_summary or commit_summary}
    except subprocess.CalledProcessError as e:
        detail = _summarize_git_output('\n'.join(filter(None, [getattr(e, 'stdout', ''), getattr(e, 'stderr', '')])))
        suffix = f' — {detail}' if detail else ''
        print(f'[git] warning: commit/push failed{suffix}')
        return {'status': 'failed', 'message': detail or str(e)}


def _collect_phase(
    workspace_root: Path,
    settings,
    html_source_path,
    cdp_host,
    cdp_port,
    cdp_target_url,
) -> tuple[Path, list]:
    """Run CDP scrape and persist raw posts. Returns (raw_dir, raw_posts)."""
    from src.browser.runner import BrowserRunner

    runner = BrowserRunner(settings)

    if html_source_path is None:
        port = cdp_port if cdp_port is not None else settings.cdp_remote_debugging_port
        if port is None:
            raise ValueError('Provide --html-source for snapshot replay or set CDP_REMOTE_DEBUGGING_PORT to use live CDP')
        restart_chrome(port=port, profile=settings.chrome_user_data_dir)

    adapter, source_mode = _build_adapter(
        workspace_root,
        settings,
        html_source_path=html_source_path,
        cdp_host=cdp_host,
        cdp_port=cdp_port,
        cdp_target_url=cdp_target_url,
    )

    try:
        raw_posts = runner.collect_home(adapter, html_source='x-home')
    finally:
        close = getattr(adapter, 'close', None)
        if callable(close):
            close()

    raw_dir = write_raw_run(
        workspace_root / settings.raw_dir,
        raw_posts,
        metadata={'source': source_mode, 'url': settings.x_home_url},
    )
    print(f'[collect] saved {len(raw_posts)} posts → {raw_dir}')
    return raw_dir, raw_posts


def _build_phase(workspace_root: Path, settings) -> dict[str, Any]:
    """Merge today's raw posts, summarise, write index.html/digest.md, git push."""
    all_posts = load_today_posts(workspace_root / settings.raw_dir)
    print(f'[build] merged {len(all_posts)} posts from today\'s runs')

    filtered = filter_posts(all_posts)
    scored = rank_posts(filtered.kept, settings)
    import asyncio
    asyncio.run(llm_summarize_posts(scored, settings))
    bundle = build_summary_bundle(scored, settings, raw_count=len(all_posts))
    summary_paths = write_summary_bundle(workspace_root / settings.output_dir, bundle)
    root_index_html = workspace_root / 'index.html'
    root_digest_md = workspace_root / 'digest.md'
    root_index_html.write_text(summary_paths['html'].read_text(encoding='utf-8'), encoding='utf-8')
    root_digest_md.write_text(summary_paths['md'].read_text(encoding='utf-8'), encoding='utf-8')

    removed = cleanup_raw_runs(workspace_root / settings.raw_dir, settings.raw_retention_days)
    cleanup_summary_runs(workspace_root / settings.output_dir, settings.raw_retention_days)

    git_result = _git_commit_and_push(workspace_root, root_index_html)

    return {
        'summary_html': summary_paths['html'],
        'summary_md': summary_paths['md'],
        'root_index_html': root_index_html,
        'root_digest_md': root_digest_md,
        'latest_html': root_index_html,
        'latest_md': root_digest_md,
        'summary_json': summary_paths['json'],
        'removed_raw_dirs': removed,
        'summary_bundle': bundle,
        'git_result': git_result,
    }


def run_once(
    workspace_root: Optional[Path] = None,
    html_source_path: Optional[Path] = None,
    cdp_host: Optional[str] = None,
    cdp_port: Optional[int] = None,
    cdp_target_url: Optional[str] = None,
    force_build: bool = False,
    build_only: bool = False,
) -> dict[str, Any]:
    workspace_root = Path(workspace_root) if workspace_root is not None else Path.cwd()
    settings = load_settings(workspace_root)

    if build_only:
        build_result = _build_phase(workspace_root, settings)
        return {
            'source_mode': 'build-only',
            **build_result,
        }

    raw_dir, raw_posts = _collect_phase(
        workspace_root, settings, html_source_path, cdp_host, cdp_port, cdp_target_url,
    )

    if settings.delete_raw_after_summary and raw_dir.exists() and not force_build:
        # Only clean individual run dir when NOT building (build needs today's data)
        pass  # deferred to build phase

    data_dir = workspace_root / settings.raw_dir
    count, should_build = bump(data_dir)
    print(f'[state] collect count today: {count}, should_build: {should_build or force_build}')

    if should_build or force_build:
        build_result = _build_phase(workspace_root, settings)
        if settings.delete_raw_after_summary and raw_dir.exists():
            import shutil
            shutil.rmtree(raw_dir)
        return {
            'raw_dir': raw_dir,
            'source_mode': 'cdp' if html_source_path is None else 'html',
            **build_result,
        }

    # Collect-only run — clean up only this run's dir if requested
    if settings.delete_raw_after_summary and raw_dir.exists():
        import shutil
        shutil.rmtree(raw_dir)

    return {
        'raw_dir': raw_dir,
        'source_mode': 'cdp' if html_source_path is None else 'html',
        'collect_count': count,
        'build_skipped': True,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Run the browser automation digest once')
    parser.add_argument('--workspace-root', default='.', help='Workspace root')
    parser.add_argument('--html-source', help='Path to a saved snapshot HTML file')
    parser.add_argument('--cdp-host', help='Chrome remote debugging host')
    parser.add_argument('--cdp-port', type=int, help='Chrome remote debugging port')
    parser.add_argument('--cdp-target-url', help='Initial target URL for the live browser tab')
    parser.add_argument('--force-build', action='store_true', help='Skip counter check and build immediately after collecting')
    parser.add_argument('--build-only', action='store_true', help='Build from existing raw data only; do not collect or launch Chrome')
    args = parser.parse_args(argv)
    result = run_once(
        args.workspace_root,
        args.html_source,
        args.cdp_host,
        args.cdp_port,
        args.cdp_target_url,
        force_build=args.force_build,
        build_only=args.build_only,
    )
    if result.get('build_skipped'):
        print(f"[done] collect #{result['collect_count']} saved — build pending next run")
    else:
        if result.get('latest_html'):
            print(f"[output] html: {result['latest_html']}")
        elif result.get('summary_html'):
            print(f"[output] html: {result['summary_html']}")
        if result.get('latest_md'):
            print(f"[output] digest: {result['latest_md']}")
        elif result.get('summary_md'):
            print(f"[output] digest: {result['summary_md']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
