"""Token pricing and context-window lookup for agents that do not report their cost."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from harness495.core.config import USER_CONFIG
from harness495.core.models import Cost, CostBasis, Usage

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "pricing.json"


@lru_cache(maxsize=1)
def load_table() -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for path in (BUNDLED, USER_CONFIG / "pricing.json"):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            table.update(data.get("models", {}))
    return table


def lookup(model: str | None) -> dict[str, Any] | None:
    if not model:
        return None
    table = load_table()
    if model in table:
        return table[model]
    # Tolerate dated suffixes and provider prefixes: "openai/gpt-5-2026-01-01" -> "gpt-5".
    base = model.split("/")[-1]
    for name in sorted(table, key=len, reverse=True):
        if base == name or base.startswith(name + "-"):
            return table[name]
    return None


def context_window(model: str | None, default: int | None = None) -> int | None:
    info = lookup(model)
    if info and info.get("context_window"):
        return int(info["context_window"])
    return default


def estimate(model: str | None, usage: Usage) -> Cost:
    info = lookup(model)
    if info is None:
        return Cost(usd=None, basis=CostBasis.unknown, source=f"no pricing for model {model!r}")
    per_m = 1_000_000
    usd = (
        usage.input_tokens * float(info.get("input", 0.0))
        + usage.output_tokens * float(info.get("output", 0.0))
        + usage.cache_read_tokens * float(info.get("cache_read", info.get("input", 0.0)))
        + usage.cache_write_tokens * float(info.get("cache_write", info.get("input", 0.0)))
    ) / per_m
    return Cost(usd=round(usd, 6), basis=CostBasis.estimated, source="pricing.json")
