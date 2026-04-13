from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import AgentMessageChunk, DeniedOutcome, RequestPermissionResponse


class _BufferingClient(Client):
    def __init__(self) -> None:
        self._parts: dict[str, list[str]] = defaultdict(list)

    async def request_permission(self, options, session_id, tool_call, **kwargs: Any) -> RequestPermissionResponse:
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, session_id, update, **kwargs: Any) -> None:
        if isinstance(update, AgentMessageChunk) and getattr(update.content, "type", None) == "text":
            text = getattr(update.content, "text", "")
            if text:
                self._parts[session_id].append(str(text))

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any):
        raise NotImplementedError

    async def read_text_file(self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any):
        raise NotImplementedError

    async def create_terminal(self, command: str, session_id: str, args=None, cwd=None, env=None, output_byte_limit=None, **kwargs: Any):
        raise NotImplementedError

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any):
        raise NotImplementedError

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any):
        raise NotImplementedError

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any):
        raise NotImplementedError

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any):
        raise NotImplementedError

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None

    def on_connect(self, conn) -> None:
        return None

    def take_text(self, session_id: str) -> str:
        return "".join(self._parts.pop(session_id, []))


async def run_prompt_via_acp(
    prompt: str,
    *,
    cwd: Path,
    model_id: str,
    reasoning_effort: str,
) -> str:
    client = _BufferingClient()
    agent_module = "src.acp.codex_bridge_agent"
    async with spawn_agent_process(
        client,
        sys.executable,
        "-m",
        agent_module,
        cwd=cwd,
        env={
            "ACP_CODEX_MODEL": model_id,
            "ACP_CODEX_REASONING_EFFORT": reasoning_effort,
        },
        use_unstable_protocol=True,
    ) as (conn, _proc):
        await conn.initialize(protocol_version=PROTOCOL_VERSION)
        session = await conn.new_session(cwd=str(cwd.resolve()), mcp_servers=[])
        await conn.set_session_model(model_id=model_id, session_id=session.session_id)
        await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block(prompt)],
        )
        await asyncio.sleep(0)
        return client.take_text(session.session_id)
