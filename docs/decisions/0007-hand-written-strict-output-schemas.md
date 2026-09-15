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

The parsed object is then read by `spec_from_agent`, `_verdict_from`/`_finding_from_agent` and
the producer summary reader in `engine.py`, which coerce into the pydantic models
(`Spec`, `ReviewVerdict`, `Finding`, `ReportedCommand`) and validate a second time; an
unparsable or invalid answer becomes a failed specifier, an `undetermined` reviewer, or an
ignored producer claim. A structured output missing from the CLI result falls back to
`_parse_json_text` on the free text.

`_parse_json_text` builds candidates out of the prose — the whole text, the body of every fenced
block with its info string removed, and the span from the first `{` to the last `}` — and returns
**the largest that parses as an object**, a tie going to the last built. Size decides and not
position: the candidates do not come in the order the agent wrote them, since the whole text is
built first and the brace span last however the prose is laid out. An agent that shows a JSON
block before its answer is showing the shape it is about to fill, and fills it in a block that
follows, so the answer is the one carrying the content.

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
- A prose answer holding an illustration and the answer is read as the larger of the two. The
  cost is the answer genuinely shorter than the example preceding it, which stays mis-read;
  nothing in a page of prose tells the two cases apart, and the shorter answer is the rarer
  shape. A block that loses is discarded silently: there is no artifact of it to read back,
  which is why the rule the reading follows has to be the one that is right more often.

## Where in the code

- `harness495/core/schemas.py`.
- `harness495/core/engine/engine.py`: `spec_from_agent`, `_normalise_spec`, `_verdict_from`,
  `_finding_from_agent`, `_parse_json_text`, `_produce` (summary reader).
- `harness495/agents/claude_code.py`: `--json-schema`; `harness495/agents/codex.py`:
  `--output-schema`; `harness495/agents/openai_compat.py`: `schema_hint`, `final` block.
- `tests/test_agents.py`: `test_claude_agent_runs_fake_cli`, `test_codex_agent_runs_fake_cli`,
  `test_openai_compat_loop_executes_commands_then_final`.
- `tests/features/agent_answer.feature`, `tests/test_agent_answer_scenarios.py`: the candidate
  `_parse_json_text` returns, over prose, one fence, two fences, a `jsonc` fence, an object
  written into the prose, a truncated object, a list and an empty answer.
