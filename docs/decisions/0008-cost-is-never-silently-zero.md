# 0008. Cost is reported, estimated or unknown, never silently zero

- Status: accepted
- Date: 2026-09-11

## Context

Claude Code reports `total_cost_usd`; Codex reports tokens only; an OpenAI-compatible endpoint
reports tokens and no price. A cost field defaulting to `0.0` reads as "free" and lets a budget
check pass for an agent whose spend is unknown.

## Decision

`Cost` carries `usd: float | None` and `basis: CostBasis`:

- `reported`: the agent stated the amount (Claude Code).
- `estimated`: computed from tokens and `harness495/data/pricing.json` (overridable by
  `~/.config/495/pricing.json`, model names matched on the longest prefix).
- `unknown`: no price for the model; `usd` is `None`.

`Consumption` sums what is known, counts `cost_unknown_interventions`, and its `cost_basis`
degrades to `estimated` as soon as one intervention is estimated. Reports and interfaces print
`unknown` rather than `0.0000`. `check_before` enforces `max_cost_usd`, `max_interventions` and
`max_total_tokens` before each intervention; the per-intervention cap passed to Claude Code
(`--max-budget-usd`) is the smaller of the remaining run budget and the agent's own cap.

## Consequences

- A run driven by an agent without pricing reaches `max_interventions` or `max_total_tokens`,
  never `max_cost_usd`; set one of those when using such an agent.
- Adding a model means adding a row to `pricing.json`, or its cost stays `unknown`
  (`docs/etude-harnais-495.md`, E48).

## Where in the code

- `harness495/core/models.py`: `Cost`, `CostBasis`, `Consumption`, `Budget`.
- `harness495/core/budget.py`: `check_before`, `per_intervention_budget`, `record`.
- `harness495/core/pricing.py`: `lookup`, `estimate`, `context_window`.
- `harness495/core/engine.py`: `_intervene` (cost assignment), `_fmt_cost`.
- `harness495/core/report.py`: `_cost`.
- `tests/test_sandbox_budget_pricing.py`: `test_pricing_lookup_and_estimate`,
  `test_budget_checks_and_warnings`.
