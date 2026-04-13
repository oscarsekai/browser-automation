from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp import (
    PROTOCOL_VERSION,
    Agent,
    RequestError,
    text_block,
    update_agent_message,
)
from acp.core import run_agent
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    CloseSessionResponse,
    ForkSessionResponse,
    Implementation,
    InitializeResponse,
    ListSessionsResponse,
    LoadSessionResponse,
    ModelInfo,
    NewSessionResponse,
    PromptResponse,
    ResumeSessionResponse,
    SessionInfo,
    SessionMode,
    SessionModeState,
    SessionModelState,
    SetSessionConfigOptionResponse,
    SetSessionModelResponse,
    SetSessionModeResponse,
)

DEFAULT_CLI_BIN = os.environ.get("ACP_CLI_BIN") or os.path.expanduser("~/.superset/bin/codex")
DEFAULT_MODEL = os.environ.get("ACP_CLI_MODEL", "gpt-5.4-mini")
DEFAULT_REASONING_EFFORT = os.environ.get("ACP_CLI_REASONING_EFFORT", "low")
SUPPORTED_MODELS = (
    ("gpt-5.4-mini", "GPT-5.4-Mini", "Smaller frontier agentic coding model."),
    ("gpt-5.4", "gpt-5.4", "Most capable default coding model."),
    ("gpt-5.1-codex-mini", "gpt-5.1-codex-mini", "Cheaper, faster coding model."),
    ("gpt-5-mini", "gpt-5-mini", "Compact GPT-5 model for GitHub Copilot CLI."),
)


@dataclass
class _SessionState:
    cwd: str
    current_model_id: str
    updated_at: datetime


class CliBridgeAgent(Agent):
    def __init__(
        self,
        *,
        default_model: str = DEFAULT_MODEL,
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
        cli_bin: str | None = None,
    ) -> None:
        self._client: Client | None = None
        self._default_model = default_model if default_model in {m[0] for m in SUPPORTED_MODELS} else DEFAULT_MODEL
        self._reasoning_effort = reasoning_effort
        self._cli_bin = cli_bin or shutil.which("codex") or DEFAULT_CLI_BIN
        self._sessions: dict[str, _SessionState] = {}

    def on_connect(self, conn: Client) -> None:
        self._client = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities=None,
        client_info=None,
        **kwargs: Any,
    ) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=min(protocol_version, PROTOCOL_VERSION),
            agent_capabilities=AgentCapabilities(),
            agent_info=Implementation(
                name="browser-automation-cli-acp",
                title="Browser Automation CLI ACP Bridge",
                version="0.1.0",
            ),
        )

    async def new_session(self, cwd: str, mcp_servers=None, **kwargs: Any) -> NewSessionResponse:
        session_id = str(uuid4())
        state = _SessionState(
            cwd=str(Path(cwd).resolve()),
            current_model_id=self._default_model,
            updated_at=datetime.now(timezone.utc),
        )
        self._sessions[session_id] = state
        return NewSessionResponse(
            session_id=session_id,
            models=self._model_state(state.current_model_id),
            modes=self._mode_state(),
        )

    async def load_session(self, cwd: str, session_id: str, mcp_servers=None, **kwargs: Any) -> LoadSessionResponse:
        state = self._require_session(session_id)
        return LoadSessionResponse(
            models=self._model_state(state.current_model_id),
            modes=self._mode_state(),
        )

    async def list_sessions(self, cursor: str | None = None, cwd: str | None = None, **kwargs: Any) -> ListSessionsResponse:
        sessions = [
            SessionInfo(
                cwd=state.cwd,
                session_id=session_id,
                title="CLI ACP summarizer",
                updated_at=state.updated_at.isoformat(),
            )
            for session_id, state in self._sessions.items()
        ]
        return ListSessionsResponse(sessions=sessions)

    async def set_session_mode(self, mode_id: str, session_id: str, **kwargs: Any) -> SetSessionModeResponse:
        if mode_id != "summarize":
            raise RequestError.invalid_params({"mode_id": mode_id})
        self._require_session(session_id)
        return SetSessionModeResponse()

    async def set_session_model(self, model_id: str, session_id: str, **kwargs: Any) -> SetSessionModelResponse:
        if model_id not in {model[0] for model in SUPPORTED_MODELS}:
            raise RequestError.invalid_params({"model_id": model_id})
        state = self._require_session(session_id)
        state.current_model_id = model_id
        state.updated_at = datetime.now(timezone.utc)
        return SetSessionModelResponse()

    async def set_config_option(self, config_id: str, session_id: str, value: str | bool, **kwargs: Any) -> SetSessionConfigOptionResponse:
        raise RequestError.method_not_found("session/setConfigOption")

    async def authenticate(self, method_id: str, **kwargs: Any):
        raise RequestError.method_not_found("authenticate")

    async def prompt(self, prompt: list[Any], session_id: str, message_id: str | None = None, **kwargs: Any) -> PromptResponse:
        state = self._require_session(session_id)
        prompt_text = self._prompt_to_text(prompt)
        output = await asyncio.to_thread(
            self._run_cli_exec,
            prompt_text,
            state.cwd,
            state.current_model_id,
        )
        state.updated_at = datetime.now(timezone.utc)

        if self._client is not None and output:
            await self._client.session_update(
                session_id=session_id,
                update=update_agent_message(text_block(output)),
            )

        return PromptResponse(stop_reason="end_turn", user_message_id=message_id)

    async def fork_session(self, cwd: str, session_id: str, mcp_servers=None, **kwargs: Any) -> ForkSessionResponse:
        state = self._require_session(session_id)
        new_session_id = str(uuid4())
        new_state = _SessionState(
            cwd=str(Path(cwd).resolve()),
            current_model_id=state.current_model_id,
            updated_at=datetime.now(timezone.utc),
        )
        self._sessions[new_session_id] = new_state
        return ForkSessionResponse(
            session_id=new_session_id,
            models=self._model_state(new_state.current_model_id),
            modes=self._mode_state(),
        )

    async def resume_session(self, cwd: str, session_id: str, mcp_servers=None, **kwargs: Any) -> ResumeSessionResponse:
        state = self._require_session(session_id)
        return ResumeSessionResponse(
            models=self._model_state(state.current_model_id),
            modes=self._mode_state(),
        )

    async def close_session(self, session_id: str, **kwargs: Any) -> CloseSessionResponse:
        self._sessions.pop(session_id, None)
        return CloseSessionResponse()

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        self._require_session(session_id)

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None

    def _require_session(self, session_id: str) -> _SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            raise RequestError.resource_not_found(session_id)
        return state

    def _model_state(self, current_model_id: str) -> SessionModelState:
        return SessionModelState(
            current_model_id=current_model_id,
            available_models=[
                ModelInfo(model_id=model_id, name=name, description=description)
                for model_id, name, description in SUPPORTED_MODELS
            ],
        )

    def _mode_state(self) -> SessionModeState:
        return SessionModeState(
            current_mode_id="summarize",
            available_modes=[
                SessionMode(
                    id="summarize",
                    name="Summarize",
                    description="Summarize posts and return JSON only.",
                )
            ],
        )

    def _prompt_to_text(self, prompt: list[Any]) -> str:
        parts: list[str] = []
        for block in prompt:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "\n\n".join(parts).strip()

    def _run_cli_exec(self, prompt: str, cwd: str, model: str) -> str:
        cli_bin = self._cli_bin
        if not os.path.isfile(cli_bin):
            raise RuntimeError(f"CLI binary not found: {cli_bin}")

        env = {**os.environ}
        env["PATH"] = f"{os.path.dirname(cli_bin)}:{env.get('PATH', '')}"

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            subprocess.run(
                [
                    cli_bin,
                    "exec",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--full-auto",
                    "-m",
                    model,
                    "-c",
                    f'model_reasoning_effort="{self._reasoning_effort}"',
                    "--output-last-message",
                    tmp_path,
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=env,
                timeout=120,
                check=False,
            )
            return Path(tmp_path).read_text(encoding="utf-8").strip()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


async def main() -> None:
    await run_agent(CliBridgeAgent(), use_unstable_protocol=True)


if __name__ == "__main__":
    asyncio.run(main())