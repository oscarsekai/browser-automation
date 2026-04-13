"""Tests for src.scheduler.loop — all time.sleep calls are mocked so tests run instantly."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


# Patch targets (where the names are looked up in loop.py)
_COLLECT = 'src.scheduler.loop._collect_phase'
_BUILD   = 'src.scheduler.loop._build_phase'
_BUMP    = 'src.scheduler.loop.bump'
_SLEEP   = 'src.scheduler.loop.time.sleep'


def _make_bump_sequence(*pairs):
    """Return a side_effect list of (count, should_build) tuples."""
    return [pair for pair in pairs]


class LoopDaemonTests(unittest.TestCase):
    """Unit tests for the loop() daemon function."""

    def _run_loop_once(self, target=3, interval=1, force_build=False):
        """Helper: run loop() in --once mode with all I/O mocked."""
        from src.scheduler.loop import loop

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(_COLLECT, return_value=(root / 'raw', [])) as m_collect,
                mock.patch(_BUILD, return_value={}) as m_build,
                mock.patch(_BUMP, return_value=(1, False)) as m_bump,
                mock.patch(_SLEEP) as m_sleep,
            ):
                loop(
                    workspace_root=root,
                    interval_seconds=interval,
                    target=target,
                    run_once=True,
                    force_build=force_build,
                )
                return m_collect, m_build, m_bump, m_sleep

    # ------------------------------------------------------------------
    # run_once mode
    # ------------------------------------------------------------------
    def test_once_mode_calls_collect_exactly_once(self):
        m_collect, _, _, _ = self._run_loop_once()
        self.assertEqual(m_collect.call_count, 1)

    def test_once_mode_does_not_sleep(self):
        _, _, _, m_sleep = self._run_loop_once()
        m_sleep.assert_not_called()

    def test_once_mode_no_build_when_target_not_reached(self):
        _, m_build, _, _ = self._run_loop_once()
        m_build.assert_not_called()

    def test_once_mode_builds_when_bump_says_should_build(self):
        from src.scheduler.loop import loop

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(_COLLECT, return_value=(root / 'raw', [])),
                mock.patch(_BUILD, return_value={}) as m_build,
                mock.patch(_BUMP, return_value=(3, True)),
                mock.patch(_SLEEP),
            ):
                loop(workspace_root=root, interval_seconds=1, target=3, run_once=True)
        self.assertEqual(m_build.call_count, 1)

    def test_once_force_build_always_builds(self):
        from src.scheduler.loop import loop

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(_COLLECT, return_value=(root / 'raw', [])),
                mock.patch(_BUILD, return_value={}) as m_build,
                mock.patch(_BUMP, return_value=(1, False)),   # counter NOT at target
                mock.patch(_SLEEP),
            ):
                loop(workspace_root=root, interval_seconds=1, target=3, run_once=True, force_build=True)
        self.assertEqual(m_build.call_count, 1)

    # ------------------------------------------------------------------
    # daemon (continuous) mode — limited iterations via side_effect
    # ------------------------------------------------------------------
    def test_daemon_builds_on_third_collect(self):
        """Daemon runs 3 iterations; build triggered on iteration 3."""
        from src.scheduler.loop import loop

        bump_results = [(1, False), (2, False), (3, True)]
        call_count = {'n': 0}

        def fake_sleep(seconds):
            call_count['n'] += 1
            if call_count['n'] >= 3:
                raise KeyboardInterrupt  # stop the loop after 3 sleeps

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(_COLLECT, return_value=(root / 'raw', [])),
                mock.patch(_BUILD, return_value={}) as m_build,
                mock.patch(_BUMP, side_effect=bump_results),
                mock.patch(_SLEEP, side_effect=fake_sleep),
            ):
                try:
                    loop(workspace_root=root, interval_seconds=1, target=3)
                except KeyboardInterrupt:
                    pass

        self.assertEqual(m_build.call_count, 1)

    def test_daemon_skips_build_on_collect_failures(self):
        """Collect errors → build never called, loop continues, sleep called."""
        from src.scheduler.loop import loop

        sleep_count = {'n': 0}

        def fake_sleep(seconds):
            sleep_count['n'] += 1
            if sleep_count['n'] >= 2:
                raise KeyboardInterrupt

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(_COLLECT, side_effect=RuntimeError('CDP down')),
                mock.patch(_BUILD, return_value={}) as m_build,
                mock.patch(_BUMP, return_value=(1, False)),
                mock.patch(_SLEEP, side_effect=fake_sleep),
            ):
                try:
                    loop(workspace_root=root, interval_seconds=1, target=3)
                except KeyboardInterrupt:
                    pass

        m_build.assert_not_called()
        self.assertGreaterEqual(sleep_count['n'], 2)

    # ------------------------------------------------------------------
    # CLI parsing
    # ------------------------------------------------------------------
    def test_main_once_flag_exits_cleanly(self):
        from src.scheduler.loop import main

        with TemporaryDirectory() as tmp:
            with (
                mock.patch(_COLLECT, return_value=(Path(tmp) / 'raw', [])),
                mock.patch(_BUILD, return_value={}),
                mock.patch(_BUMP, return_value=(1, False)),
                mock.patch(_SLEEP),
            ):
                exit_code = main(['--workspace-root', tmp, '--once', '--interval', '1', '--target', '3'])
        self.assertEqual(exit_code, 0)

    def test_main_force_build_flag_triggers_build(self):
        from src.scheduler.loop import main

        with TemporaryDirectory() as tmp:
            with (
                mock.patch(_COLLECT, return_value=(Path(tmp) / 'raw', [])),
                mock.patch(_BUILD, return_value={}) as m_build,
                mock.patch(_BUMP, return_value=(1, False)),
                mock.patch(_SLEEP),
            ):
                main(['--workspace-root', tmp, '--once', '--force-build', '--interval', '1', '--target', '3'])

        self.assertEqual(m_build.call_count, 1)


if __name__ == '__main__':
    unittest.main()
