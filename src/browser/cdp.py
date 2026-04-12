from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import urlopen

from websockets.sync.client import connect as _ws_connect_lib


class CDPError(RuntimeError):
    pass


_SENTINEL = object()


def _ws_connect(url: str, **kwargs: Any) -> Any:
    """WebSocket connect wrapper with no message-size limit (needed for full-page HTML snapshots)."""
    return _ws_connect_lib(url, max_size=None, **kwargs)


@dataclass
class CDPBrowserAdapter:
    websocket_url: str
    target_url: str = 'about:blank'
    ws_factory: Any = _ws_connect
    connect_timeout: float = 10.0
    ready_timeout: float = 30.0
    current_url: Optional[str] = None
    scrolled: int = 0
    _ws: Any = field(default=None, init=False, repr=False)
    _session_id: Optional[str] = field(default=None, init=False, repr=False)
    _next_id: int = field(default=1, init=False, repr=False)
    _events: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    @classmethod
    def from_remote_debugging_port(
        cls,
        host: str = 'localhost',
        port: int = 9222,
        target_url: str = 'about:blank',
        ws_factory: Any = _ws_connect,
    ) -> 'CDPBrowserAdapter':
        version_url = f'http://{host}:{port}/json/version'
        try:
            with urlopen(version_url, timeout=10) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except URLError as exc:
            raise CDPError(
                f'Unable to reach Chrome CDP at {version_url}. '
                'Launch Chrome with --remote-debugging-port and a dedicated user-data-dir first.'
            ) from exc
        websocket_url = payload.get('webSocketDebuggerUrl')
        if not websocket_url:
            raise CDPError(f'Chrome CDP endpoint {version_url} did not expose webSocketDebuggerUrl')
        return cls(websocket_url=websocket_url, target_url=target_url, ws_factory=ws_factory)

    @classmethod
    def from_ws_url(
        cls,
        ws_url: str,
        target_url: str = 'about:blank',
        ws_factory: Any = _ws_connect,
    ) -> 'CDPBrowserAdapter':
        """Connect directly using a WebSocket URL (e.g. from Browserbase or Amazon Bedrock)."""
        return cls(websocket_url=ws_url, target_url=target_url, ws_factory=ws_factory)

    def __enter__(self) -> 'CDPBrowserAdapter':
        self._ensure_connected()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None
                self._session_id = None

    def goto(self, url: str) -> None:
        self._ensure_connected()
        self.current_url = url
        self._send('Page.navigate', {'url': url})
        self._wait_for_ready_state()

    def scroll(self, times: int, pause_seconds: float) -> None:
        self._ensure_connected()
        if times <= 0:
            return
        for _ in range(times):
            self._evaluate(
                "window.scrollBy({top: Math.max(window.innerHeight * 0.85, 600), left: 0, behavior: 'instant'});"
            )
            self.scrolled += 1
            if pause_seconds > 0:
                time.sleep(pause_seconds)

    def snapshot_html(self) -> str:
        self._ensure_connected()
        value = self._evaluate('document.documentElement.outerHTML')
        return value if isinstance(value, str) else str(value)

    def _ensure_connected(self) -> None:
        if self._ws is not None:
            return
        self._ws = self.ws_factory(self.websocket_url, open_timeout=self.connect_timeout)
        self._send('Browser.getVersion', session_id=None)
        target = self._send('Target.createTarget', {'url': self.target_url}, session_id=None)
        target_id = target.get('targetId')
        if not target_id:
            raise CDPError('Target.createTarget did not return targetId')
        attached = self._send(
            'Target.attachToTarget',
            {'targetId': target_id, 'flatten': True},
            session_id=None,
        )
        self._session_id = attached.get('sessionId')
        if not self._session_id:
            raise CDPError('Target.attachToTarget did not return sessionId')
        self._send('Page.enable')
        self._send('Runtime.enable')
        self._send('DOM.enable')

    def _wait_for_ready_state(self) -> None:
        deadline = time.monotonic() + self.ready_timeout
        last_state = None
        while time.monotonic() < deadline:
            try:
                last_state = self._evaluate('document.readyState')
            except CDPError:
                last_state = None
            if last_state == 'complete':
                return
            time.sleep(0.2)
        raise CDPError(f'Page did not reach readyState=complete before timeout; last_state={last_state!r}')

    def _evaluate(self, expression: str) -> Any:
        result = self._send(
            'Runtime.evaluate',
            {
                'expression': expression,
                'returnByValue': True,
                'awaitPromise': True,
            },
        )
        if 'result' not in result:
            raise CDPError(f'Runtime.evaluate returned no result for {expression!r}')
        payload = result['result']
        return payload.get('value')

    def _send(
        self,
        method: str,
        params: Optional[dict[str, Any]] = None,
        session_id: Any = _SENTINEL,
    ) -> dict[str, Any]:
        if self._ws is None:
            raise CDPError('CDP websocket is not connected')
        message_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {'id': message_id, 'method': method}
        if params:
            payload['params'] = params
        if session_id is _SENTINEL:
            session_id = self._session_id
        if session_id is not None:
            payload['sessionId'] = session_id
        self._ws.send(json.dumps(payload))
        while True:
            raw = self._ws.recv()
            message = json.loads(raw)
            if message.get('id') == message_id:
                if 'error' in message:
                    raise CDPError(f"CDP call {method} failed: {message['error']}")
                return message.get('result', {})
            self._events.append(message)
