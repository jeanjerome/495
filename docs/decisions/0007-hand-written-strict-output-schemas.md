# 0007. Agent output schemas are hand-written, strict and nullable, then re-validated by pydantic

- Status: accepted
- Date: 2026-09-11

## Context

Claude Code (`--json-schema`) and Codex (`--output-schema`) accept a JSON schema for structured
output, with restrictions: `additionalProperties: false`, every property listed in `required`,
no `$ref`. A schema derived from the pydantic models carries `$ref`, optional fields and nested
definitions that one or the other CLI rejects. In strict modes a model that omits an optional
field produces a rejected object.

## Decision

`harness495/core/schemas.py` holds three schemas written by hand: `SPEC_SCHEMA`,
`REVIEW_SCHEMA`, `PRODUCER_SUMMARY_SCHEMA`. Every object is built by `_obj`, which sets
`additionalProperties: false` and requires every property. Optional values are typed
`["string", "null"]` (or array/number/null) so that a model with nothing to say answers `null`.

The parsed object is then read by `_spec_from_agent`, `_verdict_from`/`_finding_from_agent` and
the producer summary reader in `engine.py`, which coerce into the pydantic models
(`Spec`, `ReviewVerdict`, `Finding`, `ReportedCommand`) and validate a second time; an
unparsable or invalid answer becomes a failed specifier, an `undetermined` reviewer, or an
ignored producer claim. A structured output missing from the CLI result falls back to
`_parse_json_text` on the free text.

`495 schema run|event|spec|config` publishes the schemas of the *persisted* documents, which are
generated from the pydantic models; those are a different set and may use `$ref`.

## Consequences

- A field added to a model that agents must fill is added in both places: the hand-written
  schema and the reader in `engine.py`. `tests/test_models_store.py::test_run_round_trip_and_schema`
  covers the persisted side only.
- A reviewer's `requirement_assessment` may arrive as a list or as a mapping; `_verdict_from`
  accepts both.
- A finding whose `requirement_id` names a verification is re-filed under `verification_id`
  (`_finding_from_agent`).

## Where in the code

- `harness495/core/schemas.py`.
- `harness495/core/engine.py`: `_spec_from_agent`, `_normalise_spec`, `_verdict_from`,
  `_finding_from_agent`, `_parse_json_text`, `_produce` (summary reader).
- `harness495/agents/claude_code.py`: `--json-schema`; `harness495/agents/codex.py`:
  `--output-schema`; `harness495/agents/openai_compat.py`: `schema_hint`, `final` block.
- `tests/test_agents.py`: `test_claude_agent_runs_fake_cli`, `test_codex_agent_runs_fake_cli`,
  `test_openai_compat_loop_executes_commands_then_final`.
