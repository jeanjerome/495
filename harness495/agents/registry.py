"""Agent construction from configuration."""

from __future__ import annotations

from harness495.agents.base import Agent
from harness495.agents.claude_code import ClaudeCodeAgent
from harness495.agents.codex import CodexAgent
from harness495.agents.openai_compat import OpenAICompatAgent
from harness495.core.models import AgentKind, AgentSpec
from harness495.sandbox import Sandbox


def build_agent(spec: AgentSpec, sandbox: Sandbox) -> Agent:
    if spec.kind is AgentKind.claude_code:
        return ClaudeCodeAgent(spec)
    if spec.kind is AgentKind.codex:
        return CodexAgent(spec)
    if spec.kind is AgentKind.openai_compat:
        return OpenAICompatAgent(spec, sandbox)
    raise ValueError(f"unsupported agent kind {spec.kind}")
