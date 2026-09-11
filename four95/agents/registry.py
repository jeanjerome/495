"""Agent construction from configuration."""

from __future__ import annotations

from four95.agents.base import Agent
from four95.agents.claude_code import ClaudeCodeAgent
from four95.agents.codex import CodexAgent
from four95.agents.openai_compat import OpenAICompatAgent
from four95.core.models import AgentKind, AgentSpec
from four95.sandbox import Sandbox


def build_agent(spec: AgentSpec, sandbox: Sandbox) -> Agent:
    if spec.kind is AgentKind.claude_code:
        return ClaudeCodeAgent(spec)
    if spec.kind is AgentKind.codex:
        return CodexAgent(spec)
    if spec.kind is AgentKind.openai_compat:
        return OpenAICompatAgent(spec, sandbox)
    raise ValueError(f"unsupported agent kind {spec.kind}")
