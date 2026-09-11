"""JSON schemas for structured agent outputs.

They are written by hand (not derived from the pydantic models) so that they stay minimal, use
no ``$ref``, and satisfy both Claude Code ``--json-schema`` and Codex ``--output-schema``
(``additionalProperties: false``, every property required). Optional values are expressed as
nullable types rather than by dropping them from ``required``: strict structured-output modes
reject a partial object, so a model that has nothing to say must be able to answer ``null``.
The harness validates the parsed objects again with pydantic before using them.
"""

from __future__ import annotations

from typing import Any

VERIFICATION_KINDS = ["command", "test", "lint", "build", "typecheck", "review", "manual"]


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties),
        "additionalProperties": False,
    }


SPEC_SCHEMA: dict[str, Any] = _obj(
    {
        "requirements": {
            "type": "array",
            "items": _obj(
                {
                    "id": {"type": "string"},
                    "statement": {"type": "string"},
                    "rationale": {"type": "string"},
                    "verification_ids": {"type": "array", "items": {"type": "string"}},
                }
            ),
        },
        "verifications": {
            "type": "array",
            "items": _obj(
                {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": VERIFICATION_KINDS},
                    "description": {"type": "string"},
                    "command": {"type": ["string", "null"]},
                    "to_create": {"type": "boolean"},
                }
            ),
        },
        "out_of_scope": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "allowed_paths": {"type": "array", "items": {"type": "string"}},
    }
)

REVIEW_SCHEMA: dict[str, Any] = _obj(
    {
        "verdict": {"type": "string", "enum": ["accept", "reject", "undetermined"]},
        "summary": {"type": "string"},
        "confidence": {"type": ["number", "null"]},
        "requirement_assessment": {
            "type": ["array", "null"],
            "items": _obj(
                {
                    "requirement_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["satisfied", "violated", "undetermined"]},
                    "reason": {"type": "string"},
                }
            ),
        },
        "findings": {
            "type": ["array", "null"],
            "items": _obj(
                {
                    "severity": {"type": "string", "enum": ["blocker", "major", "minor", "info"]},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "file": {"type": ["string", "null"]},
                    "line": {"type": ["integer", "null"]},
                    "requirement_id": {"type": ["string", "null"]},
                    "evidence": {"type": "string"},
                }
            ),
        },
    }
)

PRODUCER_SUMMARY_SCHEMA: dict[str, Any] = _obj(
    {
        "summary": {"type": "string"},
        "files_changed": {"type": ["array", "null"], "items": {"type": "string"}},
        "commands_run": {
            "type": ["array", "null"],
            "items": _obj({"command": {"type": "string"}, "exit_code": {"type": "integer"}}),
        },
        "not_done": {"type": ["array", "null"], "items": {"type": "string"}},
    }
)
"""``not_done`` is the producer's only channel for "this could not be done": the harness reads
it as a claim to surface to the requester, never as a fact and never as a veto."""
