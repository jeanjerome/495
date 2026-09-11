"""Scope control: the change may only touch the authorised paths."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field


def _match(path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if not pattern:
        return False
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    if pattern.endswith("/"):
        return path.startswith(pattern)
    if "**" in pattern:
        # "a/**/b.py": match any depth.
        head, _, tail = pattern.partition("**")
        if not path.startswith(head):
            return False
        rest = path[len(head) :]
        tail = tail.lstrip("/")
        return fnmatch.fnmatch(rest, "*" + tail) if tail else True
    if fnmatch.fnmatch(path, pattern):
        return True
    return (
        path.startswith(pattern.rstrip("/") + "/")
        and "/" not in pattern.rstrip("/")
        and not any(ch in pattern for ch in "*?[")
    )


@dataclass
class ScopeReport:
    allowed: list[str]
    forbidden: list[str]
    files: list[str]
    violations: list[str] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations and not self.forbidden_hits

    def summary(self) -> str:
        if self.ok:
            scope = ", ".join(self.allowed) if self.allowed else "any path except forbidden ones"
            return f"{len(self.files)} file(s) changed, all within scope ({scope})"
        parts = []
        if self.forbidden_hits:
            parts.append("forbidden paths touched: " + ", ".join(self.forbidden_hits))
        if self.violations:
            parts.append("outside allowed paths: " + ", ".join(self.violations))
        return "; ".join(parts)


def check_scope(files: list[str], allowed: list[str], forbidden: list[str]) -> ScopeReport:
    report = ScopeReport(allowed=list(allowed), forbidden=list(forbidden), files=list(files))
    for f in files:
        if any(_match(f, p) for p in forbidden):
            report.forbidden_hits.append(f)
            continue
        if allowed and not any(_match(f, p) for p in allowed):
            report.violations.append(f)
    return report
