import json
import unittest
from unittest.mock import patch

from src.browser.cdp import CDPBrowserAdapter
from src.browser.runner import BrowserRunner
from src.config import Settings


class FakeWS:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.closed = False

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def recv(self):
        if not self.responses:
            raise AssertionError('No more fake CDP responses queued')
        return json.dumps(self.responses.pop(0))

    def close(self):
        self.closed = True


class CdpAdapterTests(unittest.TestCase):
    def test_collect_home_cdp_uses_cdp_commands_and_parses_html(self):
        html = "<html><body><article data-post-id='1' data-author='Ada' data-handle='ada' data-followers='1000'>https://x.com/ada/status/1 Hello CDP</article></body></html>"
        ws = FakeWS([
            {'id': 1, 'result': {'product': 'Chrome/1.0'}},
            {'id': 2, 'result': {'targetId': 'target-1'}},
            {'id': 3, 'result': {'sessionId': 'session-1'}},
            {'id': 4, 'result': {}},
            {'id': 5, 'result': {}},
            {'id': 6, 'result': {}},
            {'id': 7, 'result': {'frameId': 'frame-1'}},
            {'id': 8, 'result': {'result': {'type': 'string', 'value': 'complete'}}},
            {'id': 9, 'result': {'result': {'type': 'undefined'}}},
            {'id': 10, 'result': {'result': {'type': 'string', 'value': html}}},
        ])

        adapter = CDPBrowserAdapter(
            websocket_url='ws://example',
            ws_factory=lambda *args, **kwargs: ws,
            ready_timeout=1.0,
        )
        runner = BrowserRunner(Settings(scroll_count=1, scroll_pause_seconds=0.0, x_home_url='https://x.com/'))

        with patch('src.browser.runner.time.sleep'):
            posts = runner.collect_home_cdp(adapter)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].author, 'Ada')
        self.assertEqual(posts[0].handle, 'ada')
        self.assertEqual(adapter.current_url, 'https://x.com/')
        self.assertEqual(adapter.scrolled, 1)
        self.assertTrue(ws.closed is False)
        self.assertEqual([call['method'] for call in ws.sent[:6]], [
            'Browser.getVersion',
            'Target.createTarget',
            'Target.attachToTarget',
            'Page.enable',
            'Runtime.enable',
            'DOM.enable',
        ])
        self.assertEqual(ws.sent[6]['method'], 'Page.navigate')
        self.assertEqual(ws.sent[6]['sessionId'], 'session-1')
