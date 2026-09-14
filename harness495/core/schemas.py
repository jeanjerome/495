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
CATALOGUE_ROLES = [
    "runner",
    "bdd",
    "property",
    "fuzzing",
    "mutation",
    "coverage",
    "architecture",
    "static",
    "types",
    "security",
    "contract",
    "performance",
    "doubles",
]
"""The roles of ``docs/test-libraries.md``, as ``CatalogueRole`` lists them; a verification
names the one it measures, or null."""
REQUIREMENT_KINDS = ["behaviour", "non_regression"]


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
                    "kind": {"type": "string", "enum": REQUIREMENT_KINDS},
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
                    "role": {"type": ["string", "null"], "enum": [*CATALOGUE_ROLES, None]},
                    "scenario": {
                        "type": ["object", "null"],
                        "properties": {
                            "given": {"type": "array", "items": {"type": "string"}},
                            "when": {"type": "array", "items": {"type": "string"}},
                            "then": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["given", "when", "then"],
                        "additionalProperties": False,
                    },
                }
            ),
        },
        "out_of_scope": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "allowed_paths": {"type": "array", "items": {"type": "string"}},
    }
)

CLARIFY_SCHEMA: dict[str, Any] = _obj(
    {
        "questions": {
            "type": "array",
            "items": _obj(
                {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": _obj(
                            {
                                "key": {"type": "string"},
                                "label": {"type": "string"},
                                "consequence": {"type": "string"},
                            }
                        ),
                    },
                    "recommended": {"type": "string"},
                    "checked": {"type": "array", "items": {"type": "string"}},
                }
            ),
        }
    }
)
"""One round of the clarification: the frontier, and nothing else. An empty ``questions`` says
the frontier is empty, which is how the phase ends; there is no field for an answer, because
the clarifier does not take the decisions it states."""


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
                    "verification_id": {"type": ["string", "null"]},
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


TEST_DESIGNER_SUMMARY_SCHEMA: dict[str, Any] = _obj(
    {
        "summary": {"type": "string"},
        "files_written": {"type": ["array", "null"], "items": {"type": "string"}},
        "tests": {
            "type": ["array", "null"],
            "items": _obj({"verification_id": {"type": "string"}, "file": {"type": "string"}}),
        },
        "not_done": {"type": ["array", "null"], "items": {"type": "string"}},
    }
)
"""``tests`` says which file holds which verification's test and ``not_done`` what could not
be written; both are claims the harness shows and never concludes from. The files that count
are the ones found written in the worktree."""
