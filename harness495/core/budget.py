"""Resource accounting and limits."""

from __future__ import annotations

from dataclasses import dataclass

from harness495.core.models import Budget, Consumption, CostBasis, Intervention, Run, Usage


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class BudgetCheck:
    ok: bool
    reason: str = ""
    remaining_usd: float | None = None


def check_before(run: Run) -> BudgetCheck:
    b: Budget = run.budget
    c: Consumption = run.consumption
    if c.interventions >= b.max_interventions:
        return BudgetCheck(False, f"intervention limit reached ({b.max_interventions})")
    remaining: float | None = None
    if b.max_cost_usd is not None:
        remaining = b.max_cost_usd - c.cost_usd
        if remaining <= 0:
            return BudgetCheck(
                False, f"cost limit reached ({c.cost_usd:.4f} >= {b.max_cost_usd} USD)"
            )
    if b.max_total_tokens is not None and c.usage.total_tokens >= b.max_total_tokens:
        return BudgetCheck(
            False, f"token limit reached ({c.usage.total_tokens} >= {b.max_total_tokens})"
        )
    return BudgetCheck(True, remaining_usd=remaining)


def per_intervention_budget(run: Run, agent_cap: float | None) -> float | None:
    check = check_before(run)
    candidates = [x for x in (check.remaining_usd, agent_cap) if x is not None]
    return min(candidates) if candidates else None


def record(run: Run, intervention: Intervention) -> list[str]:
    """Add an intervention's consumption to the run and return warnings."""
    warnings: list[str] = []
    c = run.consumption
    c.interventions += 1
    c.usage = c.usage.add(intervention.usage)
    key = f"{intervention.agent.kind.value}:{intervention.agent.model or 'default'}"
    c.by_agent[key] = c.by_agent.get(key, Usage()).add(intervention.usage)
    if intervention.cost.usd is not None:
        c.cost_usd = round(c.cost_usd + intervention.cost.usd, 6)
        c.cost_by_agent[key] = round(c.cost_by_agent.get(key, 0.0) + intervention.cost.usd, 6)
        if c.cost_basis is CostBasis.unknown:
            c.cost_basis = intervention.cost.basis
        elif intervention.cost.basis is CostBasis.estimated:
            c.cost_basis = CostBasis.estimated
    else:
        c.cost_unknown_interventions += 1
    util = intervention.usage.context_utilization
    if util is not None:
        bound = " (upper bound)" if intervention.usage.context_peak_is_upper_bound else ""
        if util >= run.budget.context_abort_ratio:
            warnings.append(
                f"{intervention.id}: context window at {util:.0%}{bound}, above the abort ratio"
            )
        elif util >= run.budget.context_warn_ratio:
            warnings.append(f"{intervention.id}: context window at {util:.0%}{bound}")
    if run.budget.max_cost_usd is not None and c.cost_usd > run.budget.max_cost_usd:
        warnings.append(
            f"cost {c.cost_usd:.4f} USD exceeds the limit of {run.budget.max_cost_usd} USD"
        )
    return warnings
