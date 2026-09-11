"""The workflow engine: a resumable state machine over :class:`Run`.

Phases::

    created ─► profiled ─► specified ─► ready ─► producing ─► produced ─► verifying ─►
    verified ─► reviewing ─► reviewed ─► (accepted ─► delivered | rejected ─► ready | undetermined)

Every phase persists the run before and after its work. Human decisions suspend the run in
``awaiting_decision``; an interruption suspends it in ``paused``. ``resume`` re-enters the
phase recorded in ``resume_status``.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from four95 import __version__
from four95.agents.base import Agent, AgentResult, AgentTask
from four95.agents.registry import build_agent
from four95.core import budget as budget_mod
from four95.core import git
from four95.core import prompts as P
from four95.core.context import (
    ContextPack,
    render_evidence,
    render_profile,
    render_reviews,
    render_spec,
    render_version,
    trim_output,
    truncate_diff,
)
from four95.core.decide import Assessment, assess
from four95.core.models import (
    AgentIdentity,
    Capability,
    Cost,
    CostBasis,
    Decision,
    DecisionKind,
    DecisionMaker,
    DecisionOption,
    Event,
    Evidence,
    EvidenceKind,
    Finding,
    HarnessConfig,
    Intent,
    Intervention,
    InterventionStatus,
    Iteration,
    PendingDecision,
    ReadinessCheck,
    Requirement,
    RequirementStatus,
    ReviewVerdict,
    Role,
    Run,
    RunMode,
    RunStatus,
    SandboxInfo,
    Severity,
    Spec,
    Sufficiency,
    Verdict,
    Verification,
    VerificationKind,
    Version,
    new_id,
    utcnow,
)
from four95.core.profile import detect_profile, read_doc_excerpts
from four95.core.report import render_markdown
from four95.core.schemas import PRODUCER_SUMMARY_SCHEMA, REVIEW_SCHEMA, SPEC_SCHEMA
from four95.core.scope import check_scope
from four95.core.store import RunStore
from four95.core.verification import (
    VersionMismatch,
    assess_sufficiency,
    measures_the_change,
    run_control,
    run_verification,
)
from four95.sandbox import Sandbox, select_sandbox
from four95.sandbox.base import CommandResult, ExecRequest

DecisionHandler = Callable[[Run, PendingDecision], tuple[str, str] | None]
EventHandler = Callable[[Event], None]

PHASE_ENTRY: dict[RunStatus, RunStatus] = {
    RunStatus.producing: RunStatus.ready,
    RunStatus.verifying: RunStatus.produced,
    RunStatus.reviewing: RunStatus.verified,
}


class EngineError(RuntimeError):
    pass


class Engine:
    def __init__(
        self,
        store: RunStore,
        sandbox: Sandbox | None = None,
        on_event: EventHandler | None = None,
        decision_handler: DecisionHandler | None = None,
        agent_factory: Callable[[Any, Sandbox], Agent] | None = None,
    ) -> None:
        self.store = store
        self._sandbox = sandbox
        self._sandbox_warnings: list[str] = []
        self.on_event = on_event
        self.decision_handler = decision_handler
        self.agent_factory = agent_factory or build_agent
        self._stop = threading.Event()

    # ------------------------------------------------------------------ public API

    def create_run(
        self,
        intent: str,
        project_root: Path,
        config: HarnessConfig,
        mode: RunMode = RunMode.change,
        evaluate_ref: str | None = None,
        spec: Spec | None = None,
        source: str = "cli",
    ) -> Run:
        project_root = project_root.resolve()
        if not git.is_repo(project_root):
            raise EngineError(
                f"{project_root} is not a git repository; 495 needs git to identify versions"
            )
        root = git.repo_root(project_root)
        run = Run(
            id=new_id("run"),
            harness_version=__version__,
            mode=mode,
            intent=Intent(text=intent, source=source),
            project_root=str(root),
            config=config,
            budget=config.budget,
            evaluate_ref=evaluate_ref,
        )
        if spec is not None:
            run.spec = spec
            run.spec.source = "user"
        self.store.save(run)
        git.ensure_excluded(root, ".495/")
        self.emit(run, "run.created", f"run {run.id} created ({mode.value})", {"intent": intent})
        return run

    def run(self, run_id: str) -> Run:
        """Advance until the run blocks (decision, pause, terminal state)."""
        run = self.store.load(run_id)
        self.store.clear_stop(run_id)
        self._stop.clear()
        if run.status is RunStatus.paused or run.status is RunStatus.failed:
            run = self.resume(run_id)
        while not run.is_blocked():
            try:
                run = self.step(run)
            except KeyboardInterrupt:
                run = self._pause(run, "interrupted by user")
                break
        return run

    def resume(self, run_id: str) -> Run:
        run = self.store.load(run_id)
        self.store.clear_stop(run_id)
        self._stop.clear()
        if run.status in (RunStatus.paused, RunStatus.failed):
            target = run.resume_status or RunStatus.created
            self.emit(run, "run.resumed", f"resuming at {target.value}")
            run.status = target
            run.resume_status = None
            run.stop_reason = None
            self.store.save(run)
        return run

    def request_stop(self, run_id: str, reason: str = "stop requested") -> None:
        self.store.request_stop(run_id, reason)
        self._stop.set()

    def decide(
        self, run_id: str, choice: str, note: str = "", made_by: DecisionMaker = DecisionMaker.human
    ) -> Run:
        run = self.store.load(run_id)
        if run.pending_decision is None:
            raise EngineError("no pending decision")
        return self._apply_decision(run, choice, note, made_by)

    def step(self, run: Run) -> Run:
        handler = {
            RunStatus.created: self._profile,
            RunStatus.profiled: self._specify,
            RunStatus.specified: self._gate,
            RunStatus.ready: self._produce,
            RunStatus.produced: self._verify,
            RunStatus.verified: self._review,
            RunStatus.reviewed: self._decide,
            RunStatus.accepted: self._deliver,
            RunStatus.undetermined: self._ask_undetermined,
        }.get(run.status)
        if handler is None:
            raise EngineError(f"no handler for status {run.status.value}")
        entry = run.status
        try:
            run = handler(run)
        except KeyboardInterrupt:
            raise
        except VersionMismatch as exc:
            run = self._fail(run, f"version integrity violated: {exc}", entry)
        except git.GitError as exc:
            run = self._fail(run, f"git error: {exc}", entry)
        self.store.save(run)
        return run

    # ------------------------------------------------------------------ infrastructure

    @property
    def sandbox(self) -> Sandbox:
        if self._sandbox is None:
            raise EngineError("sandbox not initialised")
        return self._sandbox

    def _ensure_sandbox(self, run: Run) -> None:
        if self._sandbox is None:
            self._sandbox, self._sandbox_warnings = select_sandbox(run.config.sandbox)
            for w in self._sandbox_warnings:
                self._warn(run, w)

    def emit(
        self, run: Run, type_: str, message: str = "", data: dict[str, Any] | None = None
    ) -> None:
        ev = Event(run_id=run.id, type=type_, message=message, data=data or {})
        self.store.append_event(ev)
        if self.on_event is not None:
            self.on_event(ev)

    def _warn(self, run: Run, message: str) -> None:
        if message not in run.warnings:
            run.warnings.append(message)
        self.emit(run, "warning", message)

    def _stop_check(self, run: Run) -> Callable[[], bool]:
        def check() -> bool:
            return self._stop.is_set() or self.store.stop_requested(run.id) is not None

        return check

    def _set_status(self, run: Run, status: RunStatus) -> None:
        old = run.status
        run.status = status
        self.store.save(run)
        self.emit(
            run, "status", f"{old.value} -> {status.value}", {"from": old.value, "to": status.value}
        )

    def _fail(self, run: Run, reason: str, retry_at: RunStatus) -> Run:
        run.stop_reason = reason
        run.resume_status = retry_at
        self._set_status(run, RunStatus.failed)
        self.emit(run, "run.failed", reason)
        return run

    def _pause(self, run: Run, reason: str) -> Run:
        for i in run.interventions:
            if i.status is InterventionStatus.running:
                i.status = InterventionStatus.interrupted
                i.ended_at = utcnow()
                i.error = reason
        entry = PHASE_ENTRY.get(run.status, run.status)
        run.resume_status = entry
        run.stop_reason = reason
        self._set_status(run, RunStatus.paused)
        self.emit(run, "run.paused", reason)
        return run

    def _abort(self, run: Run, reason: str) -> Run:
        run.stop_reason = reason
        run.pending_decision = None
        self._set_status(run, RunStatus.aborted)
        self.emit(run, "run.aborted", reason)
        return run

    def worktree_path(self, run: Run) -> Path:
        if run.worktree:
            return Path(run.worktree)
        path = worktrees_root(run.config.sandbox.worktrees_dir, Path(run.project_root)) / run.id
        run.worktree = str(path)
        return path

    def _worktree(self, run: Run) -> Path:
        wt = self.worktree_path(run)
        if not wt.exists():
            raise EngineError(f"worktree missing: {wt}")
        return wt

    # ------------------------------------------------------------------ decisions

    def _raise_decision(self, run: Run, pending: PendingDecision, resume_at: RunStatus) -> Run:
        run.pending_decision = pending
        run.resume_status = resume_at
        self._set_status(run, RunStatus.awaiting_decision)
        self.emit(run, "decision.requested", pending.question, {"kind": pending.kind.value})
        if self.decision_handler is not None:
            answer = self.decision_handler(run, pending)
            if answer is not None:
                choice, note = answer
                run = self._apply_decision(run, choice, note, DecisionMaker.human)
        return run

    def _record_decision(
        self,
        run: Run,
        kind: DecisionKind,
        made_by: DecisionMaker,
        outcome: str,
        rationale: str = "",
        evidence_ids: list[str] | None = None,
        question: str | None = None,
    ) -> Decision:
        d = Decision(
            id=new_id("dec"),
            kind=kind,
            made_by=made_by,
            outcome=outcome,
            rationale=rationale,
            evidence_ids=evidence_ids or [],
            iteration=run.iteration_number,
            question=question,
        )
        run.decisions.append(d)
        self.emit(
            run,
            "decision",
            f"{kind.value}: {outcome} ({made_by.value})",
            {"id": d.id, "rationale": rationale},
        )
        return d

    def _apply_decision(self, run: Run, choice: str, note: str, made_by: DecisionMaker) -> Run:
        pending = run.pending_decision
        if pending is None:
            raise EngineError("no pending decision")
        keys = {o.key for o in pending.options}
        if choice not in keys:
            raise EngineError(f"invalid choice {choice!r}; expected one of {sorted(keys)}")
        option = next(o for o in pending.options if o.key == choice)
        if option.needs_note and not note.strip():
            raise EngineError(f"choice {choice!r} requires a note")
        self._record_decision(run, pending.kind, made_by, choice, note, question=pending.question)
        run.pending_decision = None
        kind = pending.kind
        if choice == "abort":
            return self._abort(
                run, f"aborted by {made_by.value} at {kind.value}: {note}".rstrip(": ")
            )
        if kind is DecisionKind.approve_spec:
            if choice in ("approve", "approve_with_gaps"):
                run.spec.approved = True
                run.spec.approved_by = made_by
                self._set_status(run, RunStatus.ready)
            elif choice == "revise":
                run.spec.approved = False
                run.spec.assumptions.append(f"revision requested: {note}")
                run.intent.text = run.intent.text  # unchanged; the note travels with the spec
                self._set_status(run, RunStatus.profiled)
        elif kind is DecisionKind.readiness:
            if choice == "proceed":
                self._set_status(run, RunStatus.profiled)
            elif choice == "allow_network":
                run.config.sandbox.allow_network = True
                self._warn(
                    run,
                    "verification commands now run with network access; agent isolation is unchanged",
                )
                self._set_status(run, RunStatus.created)
            elif choice == "drop":
                assert run.profile is not None
                bad = {r.command_name for r in run.profile.readiness if not r.executable}
                run.profile.commands = [c for c in run.profile.commands if c.name not in bad]
                run.profile.readiness = [r for r in run.profile.readiness if r.executable]
                self._set_status(run, RunStatus.profiled)
            elif choice == "retry":
                self._set_status(run, RunStatus.created)
        elif kind is DecisionKind.no_progress:
            if choice == "respecify":
                run.spec.approved = False
                run.spec.assumptions.append(f"revision requested: {note}")
                self._set_status(run, RunStatus.profiled)
            elif choice == "review_anyway":
                self._set_status(run, RunStatus.produced)
            elif choice == "stop":
                run.result.outcome = Verdict.reject
                run.result.summary = "rejected: the corrections produced no change"
                self._set_status(run, RunStatus.rejected)
        elif kind is DecisionKind.instrument_fault:
            if choice == "respecify":
                run.spec.approved = False
                run.spec.assumptions.append(f"revision requested: {note}")
                self._set_status(run, RunStatus.profiled)
            elif choice == "ignore":
                # The verification keeps running and keeps being recorded, but goes on counting
                # as proof of nothing, so the requirements it carries stay undetermined rather
                # than becoming violations the producer would be sent to fix. The answer holds
                # for the rest of the run: the fault is in the specification and has not moved.
                self._set_status(run, RunStatus.reviewed)
        elif kind is DecisionKind.iteration_limit:
            if choice == "continue":
                run.budget.max_iterations += 1
                self._set_status(run, RunStatus.ready)
            elif choice == "stop":
                run.result.outcome = Verdict.reject
                run.result.summary = "rejected after reaching the iteration limit"
                self._set_status(run, RunStatus.rejected)
        elif kind is DecisionKind.undetermined:
            if choice == "accept_with_risk":
                run.result.summary = f"accepted by human despite undetermined evidence: {note}"
                self._set_status(run, RunStatus.accepted)
            elif choice == "rerun":
                self._set_status(run, RunStatus.produced)
            elif choice == "correct":
                it = run.current_iteration
                if it is not None:
                    it.correction_requests.append(f"[human] {note}")
                if run.mode is RunMode.evaluate:
                    run.result.outcome = Verdict.reject
                    run.result.summary = f"rejected by human: {note}"
                    self._set_status(run, RunStatus.rejected)
                else:
                    self._set_status(run, RunStatus.ready)
        elif kind is DecisionKind.budget:
            if choice == "raise":
                try:
                    extra = float(note.strip().split()[0])
                except (ValueError, IndexError) as exc:
                    raise EngineError(
                        "the note must start with the additional budget in USD"
                    ) from exc
                run.budget.max_cost_usd = (run.budget.max_cost_usd or 0.0) + extra
                run.budget.max_interventions += 5
                self._set_status(run, run.resume_status or RunStatus.ready)
        elif kind is DecisionKind.scope and choice == "allow":
            it = run.current_iteration
            if it is not None:
                it.correction_requests = [
                    c for c in it.correction_requests if not c.startswith("[scope]")
                ]
            self._set_status(run, RunStatus.produced)
        run.resume_status = None
        self.store.save(run)
        return run

    # ------------------------------------------------------------------ interventions

    def _agent_for(self, run: Run, name: str) -> Agent:
        spec = run.config.agent(name)
        return self.agent_factory(spec, self.sandbox)

    def _intervene(
        self,
        run: Run,
        role: Role,
        agent_name: str,
        capability: Capability,
        system_prompt: str,
        pack: ContextPack,
        schema: dict[str, Any] | None,
        perspective: str | None = None,
        cwd: Path | None = None,
    ) -> tuple[Intervention, AgentResult | None]:
        check = budget_mod.check_before(run)
        if not check.ok:
            raise budget_mod.BudgetExceeded(check.reason)
        agent = self._agent_for(run, agent_name)
        cwd = cwd or self._worktree(run)
        project_before = project_snapshot(Path(run.project_root))
        iid = new_id("int")
        idir = self.store.intervention_dir(run.id, iid)
        prompt_text = pack.render()
        prompt_ref = self.store.write_text(run.id, str(idir / "prompt.md"), prompt_text)
        self.store.write_json(run.id, str(idir / "context.json"), pack.to_json())
        version_before = git.head_commit(cwd)
        intervention = Intervention(
            id=iid,
            iteration=run.iteration_number,
            role=role,
            perspective=perspective,
            agent=AgentIdentity(kind=agent.spec.kind, name=agent.spec.name, model=agent.spec.model),
            capability=capability,
            sandbox=SandboxInfo(backend="pending"),
            cwd=str(cwd),
            timeout_s=run.budget.intervention_timeout_s,
            context_ref=prompt_ref,
            version_before=version_before,
        )
        run.interventions.append(intervention)
        self.store.save(run)
        self.emit(
            run,
            "intervention.started",
            f"{role.value}{' (' + perspective + ')' if perspective else ''} by {agent.spec.kind.value}"
            f"{':' + agent.spec.model if agent.spec.model else ''}",
            {"id": iid, "role": role.value, "agent": agent.spec.name},
        )
        scratch = idir / "scratch"
        scratch.mkdir(exist_ok=True)
        task = AgentTask(
            role=role,
            capability=capability,
            system_prompt=system_prompt,
            prompt=prompt_text,
            cwd=cwd,
            timeout_s=run.budget.intervention_timeout_s,
            max_budget_usd=budget_mod.per_intervention_budget(run, agent.spec.max_budget_usd),
            output_schema=schema,
            scratch_dir=scratch,
            stop_check=self._stop_check(run),
            max_steps=run.budget.local_max_steps,
        )
        result: AgentResult | None = None
        try:
            result = agent.run(task)
        finally:
            intervention.ended_at = utcnow()
            if result is None:
                intervention.status = InterventionStatus.interrupted
                intervention.error = "interrupted before the agent returned"
                intervention.duration_s = (
                    intervention.ended_at - intervention.started_at
                ).total_seconds()
                self.store.save(run)
        assert result is not None
        intervention.status = result.status
        intervention.agent = result.identity
        intervention.sandbox = result.sandbox
        intervention.allowed_tools = result.allowed_tools
        intervention.usage = result.usage
        intervention.cost = (
            Cost(usd=result.cost_usd, basis=CostBasis.reported, source="agent")
            if result.cost_reported
            else Cost(
                usd=result.cost_usd,
                basis=CostBasis.estimated if result.cost_usd is not None else CostBasis.unknown,
                source="pricing.json"
                if result.cost_usd is not None
                else "no pricing for this model",
            )
        )
        intervention.exit_code = result.exit_code
        intervention.error = result.error
        intervention.duration_s = result.duration_s
        intervention.activity = dict(result.activity)
        intervention.transcript_ref = self.store.write_text(
            run.id, str(idir / "transcript.txt"), result.transcript
        )
        if result.structured is not None:
            intervention.output_ref = self.store.write_json(
                run.id, str(idir / "output.json"), result.structured
            )
        else:
            intervention.output_ref = self.store.write_text(
                run.id, str(idir / "output.md"), result.text
            )
        self.store.write_json(
            run.id,
            str(idir / "meta.json"),
            {
                "argv": result.argv,
                "identity": result.identity.model_dump(),
                "sandbox": result.sandbox.model_dump(),
            },
        )
        try:
            intervention.version_after = git.head_commit(cwd)
        except git.GitError:
            intervention.version_after = None
        if project_snapshot(Path(run.project_root)) != project_before:
            intervention.status = InterventionStatus.tampered
            intervention.error = (
                "the project working tree changed during the intervention: the agent escaped its "
                "worktree (or the tree was edited concurrently); inspect `git status` in the project"
            )
            escape = Evidence(
                id=new_id("ev"),
                kind=EvidenceKind.integrity,
                iteration=run.iteration_number,
                produced_by=intervention.id,
                passed=False,
                summary=f"{role.value} intervention {intervention.id}: project working tree modified outside the run worktree",
            )
            run.evidence.append(escape)
            if run.current_iteration is not None:
                run.current_iteration.evidence_ids.append(escape.id)
            self._warn(run, escape.summary)
        for w in budget_mod.record(run, intervention):
            self._warn(run, w)
        self.store.save(run)
        self.emit(
            run,
            "intervention.ended",
            f"{role.value} {result.status.value} in {result.duration_s:.0f}s, "
            f"{result.usage.total_tokens} tokens, cost {self._fmt_cost(intervention.cost)}",
            {
                "id": iid,
                "status": result.status.value,
                "usage": result.usage.model_dump(),
                "cost": intervention.cost.model_dump(),
                "consumption": {
                    "cost_usd": run.consumption.cost_usd,
                    "tokens": run.consumption.usage.total_tokens,
                    "interventions": run.consumption.interventions,
                    "max_cost_usd": run.budget.max_cost_usd,
                    "max_interventions": run.budget.max_interventions,
                },
            },
        )
        if result.status is InterventionStatus.interrupted:
            raise KeyboardInterrupt
        return intervention, result

    @staticmethod
    def _fmt_cost(cost: Cost) -> str:
        if cost.usd is None:
            return "unknown"
        return f"{cost.usd:.4f} USD ({cost.basis.value})"

    # ------------------------------------------------------------------ phases

    def _profile(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        root = Path(run.project_root)
        profile = detect_profile(root, run.config.project)
        run.profile = profile
        self.emit(
            run,
            "profile.detected",
            f"languages: {', '.join(profile.languages) or 'unknown'}; commands: "
            + (", ".join(c.name for c in profile.commands) or "none"),
        )
        wt = self.worktree_path(run)
        base = profile.base_commit
        if base is None:
            return self._fail(
                run, "the project has no commit; 495 needs a base commit", RunStatus.created
            )
        if run.mode is RunMode.evaluate:
            base, head = self._prepare_evaluation_worktree(run, root, wt, base)
            profile.base_commit = base
        elif not wt.exists():
            git.add_worktree(root, wt, f"495/{run.id}", base)
            self.emit(run, "worktree.created", f"{wt} on branch 495/{run.id} at {base[:12]}")
        # Readiness: run every command once on the base version.
        profile.readiness = []
        for cmd in profile.commands:
            req = ExecRequest(
                command=cmd.command,
                cwd=wt,
                timeout_s=cmd.timeout_s or run.budget.command_timeout_s,
                writable=True,
                network=run.config.sandbox.allow_network,
                stop_check=self._stop_check(run),
            )
            res = self.sandbox.run(req)
            executable = (
                not res.timed_out
                and res.exit_code not in (126, 127, None)
                and not _looks_unavailable(res.output)
            )
            detail = f"baseline exit {res.exit_code} in {res.duration_s:.1f}s"
            if res.timed_out:
                detail = "timed out"
            elif res.interrupted:
                raise KeyboardInterrupt
            elif not executable:
                detail = f"cannot run: exit {res.exit_code}; {res.output.strip()[-300:]}"
            profile.readiness.append(
                ReadinessCheck(
                    command_name=cmd.name,
                    command=cmd.command,
                    executable=executable,
                    exit_code=res.exit_code,
                    detail=detail,
                    duration_s=res.duration_s,
                )
            )
            # The whole run is read against this baseline, so keep what it actually printed:
            # a bare exit code cannot say whether the tree is broken or the environment is.
            baseline_ev = Evidence(
                id=new_id("ev"),
                kind=EvidenceKind.baseline,
                iteration=0,
                subject_version=base,
                command=cmd.command,
                exit_code=res.exit_code,
                expected_exit_code=0,
                passed=res.exit_code == 0,
                summary=f"{cmd.name} on the base version: {detail}",
                duration_s=res.duration_s,
                sandbox=self.sandbox.describe(req),
            )
            baseline_ev.output_ref = self.store.write_text(
                run.id,
                str(self.store.evidence_dir(run.id, baseline_ev.id) / "output.txt"),
                res.output,
            )
            baseline_ev.output_sha256 = git.sha256_text(res.output)
            run.evidence.append(baseline_ev)
            self.emit(
                run,
                "readiness",
                f"{cmd.name}: {'ok' if executable else 'NOT executable'} ({detail})",
                {"id": baseline_ev.id},
            )
        # Readiness runs leave caches behind; restore the pristine tree before production.
        git.reset_hard_clean(wt, "HEAD")
        if not profile.ready:
            bad = [r for r in profile.readiness if not r.executable]
            pending = PendingDecision(
                kind=DecisionKind.readiness,
                question="Some verification commands cannot run on this machine: "
                + "; ".join(f"{r.command_name} ({r.detail[:120]})" for r in bad)
                + ". Drop them, retry after fixing the environment, or abort?",
                options=[
                    DecisionOption(
                        key="drop",
                        label="Drop the non-executable commands",
                        consequence="The run continues without them. The specifier will not be "
                        "able to propose them, so whatever they covered will rest on other "
                        "verifications or end undetermined.",
                    ),
                    DecisionOption(
                        key="retry",
                        label="Retry the readiness checks",
                        consequence="Runs them again, unchanged. Take this after fixing the "
                        "environment in another shell; nothing else changes.",
                    ),
                    DecisionOption(
                        key="abort",
                        label="Abort the run",
                        consequence="The run stops for good. Nothing was produced.",
                    ),
                ],
                context={"commands": [r.model_dump() for r in bad]},
            )
            return self._raise_decision(run, pending, RunStatus.created)
        red = [r for r in profile.readiness if r.executable and r.exit_code not in (0, None)]
        if red and not run.config.auto_approve:
            # Everything the run concludes later is a comparison against this version. If it is
            # already failing, a verification that fails after the change proves nothing about it.
            offline = not run.config.sandbox.allow_network
            options = [
                DecisionOption(
                    key="proceed",
                    label="Proceed: these failures pre-date the change",
                    consequence="The run continues. These commands will most likely fail again "
                    "after the change for the same reason; the harness re-runs each failing one "
                    "on this base version and will not charge the producer for what fails here "
                    "too.",
                ),
            ]
            if offline:
                options.append(
                    DecisionOption(
                        key="allow_network",
                        label="Retry with network access for the commands",
                        consequence="Re-runs the readiness checks with the network open to the "
                        "verification commands, for builds that resolve dependencies on first "
                        "use. Agents keep their own isolation; only the harness's commands are "
                        "affected.",
                    )
                )
            options += [
                DecisionOption(
                    key="retry",
                    label="Retry the readiness checks",
                    consequence="Runs them again, unchanged. Take this after fixing the "
                    "environment in another shell.",
                ),
                DecisionOption(
                    key="abort",
                    label="Abort the run",
                    consequence="The run stops for good. Nothing was produced.",
                ),
            ]
            hint = (
                " The sandbox denies network access, which is the usual cause when a build has "
                "to resolve its dependencies on first use."
                if offline
                else ""
            )
            pending = PendingDecision(
                kind=DecisionKind.readiness,
                question="These commands already fail on the base version, before any change: "
                + "; ".join(f"{r.command_name} (exit {r.exit_code})" for r in red)
                + ". Anything they report later cannot be attributed to the change."
                + hint,
                options=options,
                context={
                    "commands": [r.model_dump() for r in red],
                    "allow_network": run.config.sandbox.allow_network,
                },
            )
            return self._raise_decision(run, pending, RunStatus.created)
        for r in red:
            self._warn(run, f"baseline '{r.command_name}' exits {r.exit_code} on the base version")
        self._set_status(run, RunStatus.profiled)
        return run

    def _prepare_evaluation_worktree(
        self, run: Run, root: Path, wt: Path, base: str
    ) -> tuple[str, str]:
        """Materialise the change to evaluate as a commit in the run's worktree."""
        ref = run.evaluate_ref or "WORKTREE"
        if wt.exists():
            return base, git.head_commit(wt)
        if ref.startswith("patch:"):
            patch = Path(ref[len("patch:") :]).expanduser().resolve()
            git.add_worktree(root, wt, f"495/{run.id}", base)
            ok, msg = git.apply_check(wt, patch)
            if not ok:
                raise EngineError(f"patch does not apply on {base[:12]}: {msg}")
            git.git(["apply", str(patch)], wt)
            head = git.commit_all(wt, f"495 evaluation of patch {patch.name}") or base
        elif ref == "WORKTREE":
            diff_text = git.worktree_diff(root)
            git.add_worktree(root, wt, f"495/{run.id}", base)
            if diff_text.strip():
                patch = wt.parent / f"{run.id}.worktree.diff"
                patch.write_text(diff_text, encoding="utf-8")
                git.git(["apply", str(patch)], wt)
                patch.unlink()
            head = git.commit_all(wt, "495 evaluation of the working tree") or base
        else:
            # "<ref>" evaluates one commit against its parent; "<base>..<ref>" against a base.
            base_spec, sep, head_spec = ref.partition("..")
            if not sep:
                base_spec, head_spec = f"{ref}~1", ref
            head_ref = git.rev_parse(root, head_spec)
            base_ref = git.rev_parse(root, base_spec)
            git.add_worktree(root, wt, f"495/{run.id}", head_ref)
            base, head = base_ref, head_ref
        self.emit(run, "worktree.created", f"{wt} evaluating {head[:12]} against base {base[:12]}")
        return base, head

    def _specify(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        assert run.profile is not None
        executable = {
            c.command
            for c in run.profile.commands
            if any(r.command_name == c.name and r.executable for r in run.profile.readiness)
        }
        if run.spec.source == "user" and run.spec.requirements:
            _normalise_spec(run.spec)
            assess_sufficiency(run.spec, executable)
            self.emit(
                run,
                "spec.provided",
                f"{len(run.spec.requirements)} requirement(s) from user; {len(run.spec.gaps)} gap(s)",
            )
            self._set_status(run, RunStatus.specified)
            return run
        pack = ContextPack(role="specifier")
        pack.add_fact("Intent (as given by the requester)", run.intent.text)
        wt = self._worktree(run)
        pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
        listing = git.top_level_listing(wt)
        pack.add_fact("Tracked files (first 200)", "\n".join(listing) or "(none)")
        if run.mode is RunMode.evaluate:
            it_version = self._evaluation_version(run)
            pack.add_fact("Change under evaluation", render_version(it_version))
        if run.spec.requirements:
            pack.add_untrusted("previous specification (agent-produced)", render_spec(run.spec))
            revisions = [a for a in run.spec.assumptions if a.startswith("revision requested")]
            if revisions:
                pack.add_fact("Revision requests from the requester", "\n".join(revisions))
        for name, text in read_doc_excerpts(wt, run.profile.doc_files).items():
            pack.add_untrusted(f"repository file {name}", text)
        pack.instructions = P.SPECIFIER_TASK
        try:
            intervention, result = self._intervene(
                run,
                Role.specifier,
                run.config.roles.specifier,
                Capability.read,
                P.SPECIFIER_SYSTEM,
                pack,
                SPEC_SCHEMA,
            )
        except budget_mod.BudgetExceeded as exc:
            return self._budget_decision(run, str(exc), RunStatus.profiled)
        if result is None or result.status is not InterventionStatus.completed:
            return self._fail(
                run,
                f"specifier failed: {result.error if result else 'no result'}",
                RunStatus.profiled,
            )
        data = result.structured or _parse_json_text(result.text)
        if not data:
            return self._fail(
                run, "specifier returned no parsable specification", RunStatus.profiled
            )
        try:
            spec = _spec_from_agent(data)
        except (ValueError, KeyError, TypeError) as exc:
            return self._fail(
                run, f"specification rejected by schema validation: {exc}", RunStatus.profiled
            )
        if run.spec.assumptions:
            spec.assumptions.extend(
                a for a in run.spec.assumptions if a.startswith("revision requested")
            )
        if not spec.allowed_paths and run.config.project.scope.allowed_paths:
            spec.allowed_paths = list(run.config.project.scope.allowed_paths)
        run.spec = spec
        assess_sufficiency(run.spec, executable)
        # Written before the gate, not after it: the specification is what the requester is
        # asked to approve, so it has to be readable at the moment the question is put.
        run.spec.artifact_ref = self.store.write_json(
            run.id,
            str(self.store.artifacts_dir(run.id) / "spec.json"),
            run.spec.model_dump(mode="json"),
        )
        spec_path = self.store.resolve(run.id, run.spec.artifact_ref)
        self.emit(
            run,
            "spec.proposed",
            f"{len(spec.requirements)} requirement(s), {len(spec.verifications)} verification(s), "
            f"{len(spec.gaps)} gap(s); written to {spec_path}",
            {"spec_ref": run.spec.artifact_ref},
        )
        self._set_status(run, RunStatus.specified)
        return run

    def _gate(self, run: Run) -> Run:
        gaps = run.spec.gaps
        if run.config.auto_approve and not gaps:
            run.spec.approved = True
            run.spec.approved_by = DecisionMaker.harness
            self._record_decision(
                run,
                DecisionKind.approve_spec,
                DecisionMaker.harness,
                "approve",
                "auto-approve enabled and no verification gap",
            )
            self._set_status(run, RunStatus.ready)
            return run
        spec_path = (
            str(self.store.resolve(run.id, run.spec.artifact_ref)) if run.spec.artifact_ref else ""
        )
        where = f" The full specification is at {spec_path}." if spec_path else ""
        question = (
            f"Approve the specification: {len(run.spec.requirements)} requirement(s), "
            f"{len(run.spec.verifications)} verification(s)?{where}"
        )
        if gaps:
            question = (
                "The specification has verification gaps: "
                + "; ".join(gaps)
                + ". Approve anyway (affected requirements can only end undetermined), ask for a "
                "revision, or abort?" + where
            )
        options = [
            DecisionOption(
                key="approve",
                label="Approve the specification",
                consequence="The producer starts implementing it. Nothing else is asked of you "
                "until the change has been verified and reviewed.",
            )
        ]
        if gaps:
            options = [
                DecisionOption(
                    key="approve_with_gaps",
                    label="Approve despite the gaps",
                    consequence="The producer starts. The requirements listed above as gaps have "
                    "no verification that can prove them, so they can only end undetermined, and "
                    "the run will stop and ask you again before concluding.",
                )
            ]
        options += [
            DecisionOption(
                key="revise",
                label="Request a revision (note required)",
                needs_note=True,
                consequence="The specifier runs again with your note and proposes a new "
                "specification. Costs one specifier intervention; nothing is implemented yet.",
            ),
            DecisionOption(
                key="abort",
                label="Abort the run",
                consequence="The run stops for good. Nothing was produced, so there is nothing "
                "to keep.",
            ),
        ]
        pending = PendingDecision(
            kind=DecisionKind.approve_spec,
            question=question,
            options=options,
            context={
                "gaps": gaps,
                "spec_path": spec_path,
                "spec": run.spec.model_dump(mode="json"),
            },
        )
        return self._raise_decision(run, pending, RunStatus.specified)

    def _budget_decision(self, run: Run, reason: str, resume_at: RunStatus) -> Run:
        pending = PendingDecision(
            kind=DecisionKind.budget,
            question=f"Budget exhausted: {reason}. Raise the budget (note: additional USD) or abort?",
            options=[
                DecisionOption(
                    key="raise",
                    label="Raise the budget (note = additional USD)",
                    needs_note=True,
                    consequence="Adds the amount in your note to the run's budget and five more "
                    "interventions, then resumes at the phase that was interrupted.",
                ),
                DecisionOption(
                    key="abort",
                    label="Abort the run",
                    consequence="The run stops for good. Whatever was produced stays on the branch.",
                ),
            ],
            context={"consumption": run.consumption.model_dump(mode="json")},
        )
        return self._raise_decision(run, pending, resume_at)

    def _evaluation_version(self, run: Run) -> Version:
        wt = self._worktree(run)
        assert run.profile is not None and run.profile.base_commit
        base = run.profile.base_commit
        head = git.head_commit(wt)
        return Version(
            base_commit=base,
            head_commit=head,
            branch=git.current_branch(wt),
            worktree=str(wt),
            files_changed=git.diff_names(wt, base, head),
        )

    def _produce(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        assert run.profile is not None and run.profile.base_commit
        wt = self._worktree(run)
        n = run.iteration_number + 1
        if run.mode is RunMode.evaluate:
            if run.iterations:
                run.result.outcome = Verdict.reject
                run.result.summary = "evaluation rejected; no production agent in evaluate mode"
                self._set_status(run, RunStatus.rejected)
                return run
            version = self._evaluation_version(run)
            version.patch_ref = self._save_patch(run, version)
            run.iterations.append(Iteration(n=n, version=version))
            self.emit(
                run, "iteration.started", f"iteration {n} (evaluation of {version.head_commit})"
            )
            self._set_status(run, RunStatus.produced)
            return run
        previous = run.current_iteration
        corrections = list(previous.correction_requests) if previous else []
        iteration = Iteration(n=n)
        run.iterations.append(iteration)
        self._set_status(run, RunStatus.producing)
        self.emit(
            run,
            "iteration.started",
            f"iteration {n}" + (" (corrections)" if corrections else ""),
            {"n": n, "max": run.budget.max_iterations},
        )
        base_for_diff = run.profile.base_commit
        pack = ContextPack(role="producer")
        pack.add_fact("Intent (as given by the requester)", run.intent.text)
        pack.add_fact("Approved specification", render_spec(run.spec))
        pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
        scope_lines = [
            "Allowed paths: " + (", ".join(_effective_allowed(run)) or "any path"),
            "Forbidden paths: " + ", ".join(run.config.project.scope.forbidden_paths),
        ]
        pack.add_fact("Scope", "\n".join(scope_lines))
        pack.add_fact(
            "Version", f"base commit {base_for_diff}; the harness commits your work when you finish"
        )
        if corrections and previous is not None:
            pack.add_fact(
                "Correction requests (derived by the harness from evidence)",
                "\n".join(f"- {c}" for c in corrections),
            )
            prev_ev = [run.evidence_by_id(e) for e in previous.evidence_ids]
            pack.add_fact(
                "Evidence from the previous iteration", render_evidence([e for e in prev_ev if e])
            )
            for e in prev_ev:
                if e and e.passed is False and e.output_ref:
                    pack.add_untrusted(
                        f"output of `{e.command}` (previous iteration)",
                        trim_output(self.store.read_text(run.id, e.output_ref)),
                    )
            prev_reviews = [r for r in run.reviews if r.intervention_id in previous.review_ids]
            pack.add_untrusted(
                "reviewer findings (previous iteration, agent-produced)",
                render_reviews(prev_reviews, observations_only=True),
            )
            pack.instructions = P.CORRECTION_TASK + "\n" + P.PRODUCER_TASK
        else:
            pack.instructions = P.PRODUCER_TASK
        try:
            intervention, result = self._intervene(
                run,
                Role.producer,
                run.config.roles.producer,
                Capability.write,
                P.PRODUCER_SYSTEM,
                pack,
                PRODUCER_SUMMARY_SCHEMA,
            )
        except budget_mod.BudgetExceeded as exc:
            run.iterations.pop()
            return self._budget_decision(run, str(exc), RunStatus.ready)
        iteration.production_intervention_id = intervention.id
        if intervention.status is InterventionStatus.tampered:
            return self._fail(
                run,
                "the producer modified the project working tree instead of its worktree; the run "
                f"stops so you can inspect `git -C {run.project_root} status` (nothing was committed)",
                RunStatus.ready,
            )
        if result is None or result.status not in (
            InterventionStatus.completed,
            InterventionStatus.failed,
            InterventionStatus.timed_out,
            InterventionStatus.budget_exceeded,
        ):
            return self._fail(
                run,
                f"producer did not complete: {result.error if result else 'no result'}",
                RunStatus.ready,
            )
        if result.status is not InterventionStatus.completed:
            self._warn(
                run,
                f"producer ended with {result.status.value}: {result.error}; evaluating whatever was produced",
            )
        if isinstance(result.structured, dict):
            claims = result.structured.get("not_done") or []
            iteration.blocked_claims = [str(c).strip()[:500] for c in claims if str(c).strip()][:20]
            for claim in iteration.blocked_claims:
                self.emit(run, "producer.blocked", claim)
        # Freeze the delivered version.
        head = git.commit_all(wt, f"495 iteration {n}: {run.intent.text[:60]}") or git.head_commit(
            wt
        )
        version = Version(
            base_commit=base_for_diff,
            head_commit=head,
            branch=git.current_branch(wt),
            worktree=str(wt),
            files_changed=git.diff_names(wt, base_for_diff, head),
        )
        version.patch_ref = self._save_patch(run, version)
        iteration.version = version
        self.emit(
            run,
            "version.frozen",
            f"iteration {n} committed as {head[:12]} ({len(version.files_changed)} file(s))",
            {"head": head, "patch_sha256": version.patch_sha256},
        )
        if head == base_for_diff:
            self._warn(run, f"iteration {n} produced no change")
        self._set_status(run, RunStatus.produced)
        previous_version = previous.version if previous is not None else None
        if (
            previous is not None
            and previous_version is not None
            and version.patch_sha256 == previous_version.patch_sha256
            and corrections
        ):
            # Verifying and reviewing a tree that is byte-for-byte the one already judged would
            # spend a full round to reach the same conclusion. Whatever was asked for did not
            # happen, and one more identically-worded request will not make it happen.
            pending = PendingDecision(
                kind=DecisionKind.no_progress,
                question=f"Iteration {n} delivers exactly the tree of iteration {previous.n}: the "
                "corrections produced no edit at all"
                + (
                    f", and the producer reported {len(iteration.blocked_claims)} thing(s) it "
                    "could not do"
                    if iteration.blocked_claims
                    else ""
                )
                + ".",
                options=[
                    DecisionOption(
                        key="respecify",
                        label="Change the specification, then produce again",
                        needs_note=True,
                        consequence="The specifier runs again with your note. Take this when the "
                        "producer is right that what was asked cannot be done as specified.",
                    ),
                    DecisionOption(
                        key="review_anyway",
                        label="Verify and review this version as it stands",
                        consequence="Spends a full verification and review round on a tree that "
                        "has already been judged. Worth it only if something outside the tree "
                        "has changed since.",
                    ),
                    DecisionOption(
                        key="stop",
                        label="Stop: the change is rejected",
                        consequence="The run ends as rejected. The branch and the patch stay on "
                        "disk for you to inspect or salvage.",
                    ),
                    DecisionOption(
                        key="abort",
                        label="Abort the run",
                        consequence="The run stops for good, with no outcome recorded.",
                    ),
                ],
                context={
                    "iteration": n,
                    "patch_sha256": version.patch_sha256,
                    "blocked_claims": iteration.blocked_claims,
                    "corrections": corrections,
                },
            )
            return self._raise_decision(run, pending, RunStatus.produced)
        return run

    def _save_patch(self, run: Run, version: Version) -> str | None:
        wt = self._worktree(run)
        assert version.head_commit
        patch = git.diff(wt, version.base_commit, version.head_commit)
        version.patch_sha256 = git.sha256_text(patch)
        if not patch.strip():
            return None
        ref = self.store.write_text(
            run.id,
            str(self.store.artifacts_dir(run.id) / f"iteration-{run.iteration_number or 1}.patch"),
            patch,
        )
        return ref

    def _verify(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        it = run.current_iteration
        assert it is not None and it.version is not None and it.version.head_commit
        wt = self._worktree(run)
        self._set_status(run, RunStatus.verifying)
        git.reset_hard_clean(wt, it.version.head_commit)
        evidence: list[Evidence] = []
        # Scope check.
        allowed = _effective_allowed(run)
        report = check_scope(
            it.version.files_changed, allowed, run.config.project.scope.forbidden_paths
        )
        scope_ev = Evidence(
            id=new_id("ev"),
            kind=EvidenceKind.scope_check,
            iteration=it.n,
            subject_version=it.version.head_commit,
            passed=report.ok,
            summary=report.summary(),
        )
        evidence.append(scope_ev)
        self.emit(
            run,
            "evidence",
            f"scope: {'ok' if report.ok else 'VIOLATION'} - {report.summary()}",
            {"id": scope_ev.id},
        )
        # Verifications.
        req_by_verification: dict[str, list[str]] = {}
        for r in run.spec.requirements:
            for vid in r.verification_ids:
                req_by_verification.setdefault(vid, []).append(r.id)
        for v in run.spec.verifications:
            if v.command is None:
                ev = run_verification(
                    v,
                    wt,
                    it.version.head_commit,
                    self.sandbox,
                    it.n,
                    run.budget.command_timeout_s,
                    lambda _e, _t: "",
                    None,
                    req_by_verification.get(v.id, []),
                    network=run.config.sandbox.allow_network,
                )
                evidence.append(ev)
                continue
            self.emit(run, "verification.started", f"{v.id}: {v.command}", {"verification": v.id})

            def sink(eid: str, text: str) -> str:
                return self.store.write_text(
                    run.id, str(self.store.evidence_dir(run.id, eid) / "output.txt"), text
                )

            ev = run_verification(
                v,
                wt,
                it.version.head_commit,
                self.sandbox,
                it.n,
                run.budget.command_timeout_s,
                sink,
                self._stop_check(run),
                req_by_verification.get(v.id, []),
                network=run.config.sandbox.allow_network,
            )
            evidence.append(ev)
            self.emit(
                run,
                "evidence",
                f"{v.id}: {'PASS' if ev.passed else 'FAIL' if ev.passed is False else 'NOT RUN'} ({ev.summary})",
                {"id": ev.id, "verification": v.id},
            )
            if ev.summary == "interrupted":
                raise KeyboardInterrupt
        evidence.extend(self._control_failing(run, it, evidence))
        # Verification runs may write caches; restore the exact version for the reviewers.
        git.reset_hard_clean(wt, it.version.head_commit)
        run.evidence.extend(evidence)
        it.evidence_ids.extend(e.id for e in evidence)
        self._set_status(run, RunStatus.verified)
        return run

    def _control_failing(self, run: Run, it: Iteration, evidence: list[Evidence]) -> list[Evidence]:
        """Re-run every failing verification on the base version, where the change does not exist.

        A failure that reproduces identically without the change is not telling us anything about
        the change. Asking the producer to make such a command pass sends it to work on whatever
        the command is actually measuring, which is never what the requirement is about.
        """
        assert run.profile is not None and run.profile.base_commit
        base = run.profile.base_commit
        failing = [
            (v, e)
            for e in evidence
            if e.passed is False and e.kind is EvidenceKind.command_result and e.verification_id
            for v in [run.spec.verification(e.verification_id)]
            if v is not None and v.command
        ]
        if not failing:
            return []
        produced: list[Evidence] = []
        control_wt = self._worktree(run).parent / f"{run.id}.control"
        root = Path(run.project_root)
        git.remove_worktree(root, control_wt)
        shutil.rmtree(control_wt, ignore_errors=True)
        try:
            git.add_worktree_detached(root, control_wt, base)
        except git.GitError as exc:
            self._warn(run, f"cannot check the verifications against the base version: {exc}")
            return []
        try:
            for v, ev in failing:
                previous = next(
                    (
                        e
                        for e in run.evidence
                        if e.kind is EvidenceKind.instrument_check
                        and e.verification_id == v.id
                        and e.command == v.command
                        and e.subject_version == base
                    ),
                    None,
                )
                if previous is not None:
                    control_output = self.store.read_text(run.id, previous.output_ref or "")
                    control = CommandResult(
                        command=v.command or "",
                        exit_code=previous.exit_code,
                        output=control_output,
                        duration_s=previous.duration_s or 0.0,
                    )
                else:
                    self.emit(
                        run,
                        "control.started",
                        f"{v.id} failed: checking whether it fails without the change too",
                        {"verification": v.id},
                    )

                    def sink(eid: str, text: str) -> str:
                        return self.store.write_text(
                            run.id, str(self.store.evidence_dir(run.id, eid) / "output.txt"), text
                        )

                    control_ev, control = run_control(
                        v,
                        control_wt,
                        base,
                        self.sandbox,
                        it.n,
                        run.budget.command_timeout_s,
                        sink,
                        self._stop_check(run),
                        network=run.config.sandbox.allow_network,
                    )
                    if control.interrupted:
                        raise KeyboardInterrupt
                    produced.append(control_ev)
                subject_output = self.store.read_text(run.id, ev.output_ref or "")
                if measures_the_change(
                    ev.exit_code, subject_output, control, ev.summary == "timed out"
                ):
                    self.emit(
                        run,
                        "control.ended",
                        f"{v.id}: behaves differently without the change, so the failure is "
                        "about the change",
                        {"verification": v.id, "faulty": False},
                    )
                    continue
                v.sufficiency = Sufficiency.faulty
                v.rationale = (
                    f"fails identically on the base version {base[:12]} (exit {control.exit_code}), "
                    "so its outcome does not depend on the change"
                )
                it.instrument_faults.append(f"{v.id}: {v.rationale}")
                self.emit(
                    run,
                    "instrument.fault",
                    f"{v.id} does not observe the change: {v.rationale}",
                    {"verification": v.id},
                )
        finally:
            git.remove_worktree(root, control_wt)
            shutil.rmtree(control_wt, ignore_errors=True)
        return produced

    def _review(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        it = run.current_iteration
        assert it is not None and it.version is not None and it.version.head_commit
        wt = self._worktree(run)
        self._set_status(run, RunStatus.reviewing)
        diff_text = git.diff(wt, it.version.base_commit, it.version.head_commit)
        evidence = [e for e in (run.evidence_by_id(x) for x in it.evidence_ids) if e]
        for reviewer in run.config.roles.reviewers:
            if any(
                r.perspective == reviewer.perspective
                and r.intervention_id in it.review_ids
                and not r.discarded
                for r in run.reviews
            ):
                continue  # already done (resume)
            pack = ContextPack(role=f"reviewer:{reviewer.perspective}")
            pack.add_fact("Intent (as given by the requester)", run.intent.text)
            pack.add_fact("Approved specification", render_spec(run.spec))
            pack.add_fact("Version under review", render_version(it.version))
            pack.add_fact(
                "Evidence collected by the harness on this exact version", render_evidence(evidence)
            )
            assert run.profile is not None
            pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
            pack.add_untrusted("git diff base..head", truncate_diff(diff_text) or "(empty diff)")
            for e in evidence:
                if e.output_ref and e.passed is False:
                    pack.add_untrusted(
                        f"output of `{e.command}`",
                        trim_output(self.store.read_text(run.id, e.output_ref)),
                    )
            pack.instructions = P.REVIEWER_TASK.format(
                perspective=reviewer.perspective,
                perspective_instructions=P.perspective_instructions(
                    reviewer.perspective, reviewer.instructions
                ),
            )
            git.reset_hard_clean(wt, it.version.head_commit)
            try:
                intervention, result = self._intervene(
                    run,
                    Role.reviewer,
                    reviewer.agent,
                    Capability.read,
                    P.REVIEWER_SYSTEM,
                    pack,
                    REVIEW_SCHEMA,
                    reviewer.perspective,
                )
            except budget_mod.BudgetExceeded as exc:
                return self._budget_decision(run, str(exc), RunStatus.verified)
            it.review_ids.append(intervention.id)
            verdict = self._verdict_from(intervention, reviewer.perspective, result, run)
            # Integrity: a reviewer must not have altered the tree.
            tampered = git.head_commit(wt) != it.version.head_commit or git.is_dirty(wt)
            if tampered:
                git.reset_hard_clean(wt, it.version.head_commit)
                intervention.status = InterventionStatus.tampered
                verdict.discarded = True
                verdict.discard_reason = (
                    "the reviewer modified the worktree; verdict discarded and tree restored"
                )
                self._warn(
                    run,
                    f"reviewer {reviewer.perspective} modified the read-only worktree; verdict discarded",
                )
                integ = Evidence(
                    id=new_id("ev"),
                    kind=EvidenceKind.integrity,
                    iteration=it.n,
                    subject_version=it.version.head_commit,
                    produced_by=intervention.id,
                    passed=False,
                    summary=f"reviewer {reviewer.perspective} altered the worktree during review; restored",
                )
                run.evidence.append(integ)
                it.evidence_ids.append(integ.id)
            run.reviews.append(verdict)
            rv_ev = Evidence(
                id=new_id("ev"),
                kind=EvidenceKind.review_verdict,
                iteration=it.n,
                subject_version=it.version.head_commit,
                produced_by=intervention.id,
                passed=None if verdict.discarded else verdict.verdict is Verdict.accept,
                summary=f"{reviewer.perspective}: {verdict.verdict.value}"
                + (" (discarded)" if verdict.discarded else "")
                + f"; {len(verdict.findings)} finding(s)",
            )
            run.evidence.append(rv_ev)
            it.evidence_ids.append(rv_ev.id)
            self.emit(
                run,
                "review",
                rv_ev.summary,
                {"perspective": reviewer.perspective, "verdict": verdict.verdict.value},
            )
            self.store.save(run)
        self._set_status(run, RunStatus.reviewed)
        return run

    def _verdict_from(
        self, intervention: Intervention, perspective: str, result: AgentResult | None, run: Run
    ) -> ReviewVerdict:
        if result is None:
            return ReviewVerdict(
                intervention_id=intervention.id,
                perspective=perspective,
                verdict=Verdict.undetermined,
                summary="reviewer did not complete (no result)",
            )
        # A reviewer that ran the whole review and then failed to shape its answer has still done
        # the work; take the answer if it is recoverable rather than paying for the review twice.
        data = result.structured or _parse_json_text(result.text)
        if result.status is not InterventionStatus.completed and not data:
            return ReviewVerdict(
                intervention_id=intervention.id,
                perspective=perspective,
                verdict=Verdict.undetermined,
                summary=f"reviewer did not complete ({result.status.value}): {result.error or ''}",
            )
        if not data:
            return ReviewVerdict(
                intervention_id=intervention.id,
                perspective=perspective,
                verdict=Verdict.undetermined,
                summary="reviewer returned no parsable verdict",
            )
        try:
            findings = [
                Finding(
                    severity=Severity(str(f.get("severity", "info"))),
                    title=str(f.get("title", ""))[:200],
                    detail=str(f.get("detail", "")),
                    file=f.get("file") or None,
                    line=int(f["line"]) if isinstance(f.get("line"), int) else None,
                    requirement_id=f.get("requirement_id") or None,
                    evidence=str(f.get("evidence", "")),
                )
                for f in data.get("findings", [])
                if isinstance(f, dict)
            ]
            assessment: dict[str, RequirementStatus] = {}
            raw_assessment = data.get("requirement_assessment", [])
            if isinstance(raw_assessment, dict):
                raw_assessment = [
                    {"requirement_id": k, "status": v} for k, v in raw_assessment.items()
                ]
            for a in raw_assessment:
                if isinstance(a, dict) and a.get("requirement_id"):
                    assessment[str(a["requirement_id"])] = RequirementStatus(
                        str(a.get("status", "undetermined"))
                    )
            verdict = Verdict(str(data.get("verdict", "undetermined")))
            confidence = data.get("confidence")
            return ReviewVerdict(
                intervention_id=intervention.id,
                perspective=perspective,
                verdict=verdict,
                summary=str(data.get("summary", ""))[:2000],
                findings=findings,
                requirement_assessment=assessment,
                confidence=float(confidence) if isinstance(confidence, int | float) else None,
            )
        except (ValueError, TypeError) as exc:
            return ReviewVerdict(
                intervention_id=intervention.id,
                perspective=perspective,
                verdict=Verdict.undetermined,
                summary=f"reviewer verdict failed validation: {exc}",
            )

    def _decide(self, run: Run) -> Run:
        it = run.current_iteration
        assert it is not None
        evidence = [e for e in (run.evidence_by_id(x) for x in it.evidence_ids) if e]
        reviews = [r for r in run.reviews if r.intervention_id in it.review_ids]
        assessment: Assessment = assess(run.spec, evidence, reviews)
        for r in run.spec.requirements:
            r.status = assessment.requirement_status.get(r.id, RequirementStatus.undetermined)
            r.status_reason = assessment.reasons.get(r.id, "")
        it.outcome = assessment.outcome
        it.ended_at = utcnow()
        it.correction_requests = list(assessment.correction_requests)
        decision = self._record_decision(
            run,
            DecisionKind.acceptance,
            DecisionMaker.harness,
            assessment.outcome.value,
            assessment.summary
            + (
                "; undetermined: " + "; ".join(assessment.undetermined_reasons)
                if assessment.undetermined_reasons
                else ""
            ),
            [e.id for e in evidence],
        )
        it.decision_id = decision.id
        self.emit(run, "iteration.assessed", f"iteration {it.n}: {assessment.summary}")
        already_answered = any(
            d.kind is DecisionKind.instrument_fault and d.outcome == "ignore" for d in run.decisions
        )
        if (
            assessment.instrument_faults
            and assessment.outcome is not Verdict.accept
            and not already_answered
        ):
            # No correction can move a verification that does not look at the change. The gap is
            # in the specification, and only the requester can decide how to close it.
            pending = PendingDecision(
                kind=DecisionKind.instrument_fault,
                question="These verifications fail the same way with and without the change, so "
                "they cannot show whether the requirements they carry hold: "
                + "; ".join(assessment.instrument_faults)
                + ". Go back to the specification, keep them as no proof either way, or abort?",
                options=[
                    DecisionOption(
                        key="respecify",
                        label="Write a specification these commands can actually check",
                        needs_note=True,
                        consequence="The specifier runs again with your note and proposes new "
                        "verifications. The work already produced stays on the branch but is "
                        "judged afresh against the new specification.",
                    ),
                    DecisionOption(
                        key="ignore",
                        label="Leave them; accept that they prove nothing either way",
                        consequence="The run continues and stops asking. The requirements these "
                        "commands were meant to cover can only end undetermined, so the run will "
                        "ask you once more before concluding.",
                    ),
                    DecisionOption(
                        key="abort",
                        label="Abort the run",
                        consequence="The run stops for good. The branch and the patch stay on disk.",
                    ),
                ],
                context={"faults": assessment.instrument_faults},
            )
            return self._raise_decision(run, pending, RunStatus.reviewed)
        if assessment.outcome is Verdict.accept:
            run.result.outcome = Verdict.accept
            run.result.summary = assessment.summary
            self._set_status(run, RunStatus.accepted)
        elif assessment.outcome is Verdict.reject:
            if run.mode is RunMode.evaluate:
                run.result.outcome = Verdict.reject
                run.result.summary = assessment.summary
                self._set_status(run, RunStatus.rejected)
            elif it.n >= run.budget.max_iterations:
                pending = PendingDecision(
                    kind=DecisionKind.iteration_limit,
                    question=f"Iteration {it.n} was rejected and the limit of "
                    f"{run.budget.max_iterations} is reached, with "
                    f"{len(assessment.correction_requests)} correction(s) still outstanding"
                    + (
                        f" and {len(it.blocked_claims)} thing(s) the producer reported it could "
                        "not do"
                        if it.blocked_claims
                        else ""
                    )
                    + ".",
                    options=[
                        DecisionOption(
                            key="continue",
                            label="Allow one more iteration",
                            consequence="Raises the limit by one and runs producer, verification "
                            "and reviewers again. Costs roughly what one iteration has cost so "
                            "far.",
                        ),
                        DecisionOption(
                            key="stop",
                            label="Stop: the change is rejected",
                            consequence="The run ends as rejected. The branch and the patch stay "
                            "on disk for you to inspect or salvage.",
                        ),
                        DecisionOption(
                            key="abort",
                            label="Abort the run",
                            consequence="The run stops for good, with no outcome recorded.",
                        ),
                    ],
                    context={
                        "corrections": assessment.correction_requests,
                        "blocked_claims": it.blocked_claims,
                    },
                )
                return self._raise_decision(run, pending, RunStatus.reviewed)
            else:
                self.emit(
                    run,
                    "iteration.rejected",
                    f"iteration {it.n} rejected; {len(assessment.correction_requests)} correction(s) requested",
                )
                self._set_status(run, RunStatus.ready)
        else:
            run.result.outcome = Verdict.undetermined
            run.result.summary = assessment.summary
            self._set_status(run, RunStatus.undetermined)
        return run

    def _ask_undetermined(self, run: Run) -> Run:
        it = run.current_iteration
        reasons = _undetermined_reasons(run)
        blocked = len(
            [r for r in run.spec.requirements if r.status is RequirementStatus.undetermined]
        )
        options = [
            DecisionOption(
                key="accept_with_risk",
                label="Accept anyway, on your own judgement (note required)",
                needs_note=True,
                consequence="The run is delivered as accepted with your note recorded. The "
                "requirements above stay undetermined in the report: you are signing that you "
                "checked them yourself, because the harness did not.",
            ),
            DecisionOption(
                key="rerun",
                label="Measure the same version again",
                consequence="Re-runs the verifications and all reviewers on the same commit, "
                "without producing anything. Worth it when what blocked them was transient; "
                "costs one full review round.",
            ),
        ]
        if run.mode is RunMode.change:
            options.append(
                DecisionOption(
                    key="correct",
                    label="Send it back to the producer (note required)",
                    needs_note=True,
                    consequence="Starts a new iteration with your note as the correction "
                    "request, on top of the current version.",
                )
            )
        else:
            options.append(
                DecisionOption(
                    key="correct",
                    label="Reject with a note",
                    needs_note=True,
                    consequence="The run ends as rejected, with your note as the reason.",
                )
            )
        options.append(
            DecisionOption(
                key="abort",
                label="Abort the run",
                consequence="The run stops for good. The branch and the patch stay on disk.",
            )
        )
        pending = PendingDecision(
            kind=DecisionKind.undetermined,
            question=f"On iteration {it.n if it else '?'} the harness has no evidence it can "
            f"conclude from: {blocked} of {len(run.spec.requirements)} requirement(s) are "
            "undetermined. It will not decide for you.",
            options=options,
            context={"reasons": reasons},
        )
        return self._raise_decision(run, pending, RunStatus.undetermined)

    def _deliver(self, run: Run) -> Run:
        it = run.current_iteration
        assert it is not None and it.version is not None
        run.result.outcome = run.result.outcome or Verdict.accept
        run.result.head_commit = it.version.head_commit
        run.result.branch = it.version.branch
        run.result.patch_ref = it.version.patch_ref
        report = render_markdown(run, self.store)
        run.result.report_ref = self.store.write_text(
            run.id, str(self.store.artifacts_dir(run.id) / "report.md"), report
        )
        self._set_status(run, RunStatus.delivered)
        self.emit(
            run,
            "run.delivered",
            f"branch {it.version.branch} at {it.version.head_commit}; patch {it.version.patch_ref or 'none'}; report {run.result.report_ref}",
        )
        return run

    # ------------------------------------------------------------------ post-integration

    def check_integration(
        self, run_id: str, target_ref: str = "HEAD", rerun_verifications: bool = False
    ) -> Run:
        run = self.store.load(run_id)
        self._ensure_sandbox(run)
        it = run.current_iteration
        if it is None or it.version is None or not it.version.head_commit:
            raise EngineError("the run has no evaluated version")
        root = Path(run.project_root)
        head = it.version.head_commit
        target = git.rev_parse(root, target_ref)
        contains = git.is_ancestor(root, head, target)
        identical = True
        details: list[str] = []
        for f in it.version.files_changed:
            expected = git.blob_hash(root, head, f)
            actual = git.blob_hash(root, target, f)
            if expected != actual:
                identical = False
                details.append(
                    f"{f}: evaluated {expected or 'deleted'} vs integrated {actual or 'missing'}"
                )
        passed: bool | None = None
        if rerun_verifications:
            tmp = self.worktree_path(run).parent / f"{run.id}-integration"
            if tmp.exists():
                git.remove_worktree(root, tmp)
            git.git(["worktree", "add", "--detach", str(tmp), target], root)
            try:
                passed = True
                for v in run.spec.verifications:
                    if not v.command:
                        continue
                    req = ExecRequest(
                        command=v.command,
                        cwd=tmp,
                        timeout_s=v.timeout_s or run.budget.command_timeout_s,
                        writable=True,
                        network=run.config.sandbox.allow_network,
                    )
                    res = self.sandbox.run(req)
                    ok = res.exit_code == v.expected_exit_code
                    passed = passed and ok
                    details.append(
                        f"{v.id} on {target[:12]}: exit {res.exit_code} ({'pass' if ok else 'FAIL'})"
                    )
            finally:
                git.remove_worktree(root, tmp)
                shutil.rmtree(tmp, ignore_errors=True)
        from four95.core.models import IntegrationCheck

        run.result.integration = IntegrationCheck(
            target_ref=target_ref,
            target_commit=target,
            contains_commit=contains,
            files_identical=identical,
            verifications_rerun=rerun_verifications,
            verifications_passed=passed,
            detail="; ".join(details)
            if details
            else (
                "commit contained and files identical"
                if contains and identical
                else "files identical"
                if identical
                else "differences found"
            ),
        )
        self.emit(
            run,
            "integration.checked",
            f"{target_ref} ({target[:12]}): contains commit={contains}, files identical={identical}"
            + (f", verifications passed={passed}" if rerun_verifications else ""),
        )
        self.store.save(run)
        return run

    def cleanup_worktree(self, run_id: str) -> None:
        run = self.store.load(run_id)
        wt = self.worktree_path(run)
        if wt.exists():
            git.remove_worktree(Path(run.project_root), wt)
            shutil.rmtree(wt, ignore_errors=True)


# ---------------------------------------------------------------------- helpers


def _looks_unavailable(output: str) -> bool:
    tail = output[-2000:].lower()
    markers = (
        "command not found",
        "no module named",
        "not recognized as an internal",
        "no such file or directory",
        "could not find a version",
        "is not installed",
    )
    return any(m in tail for m in markers)


def _effective_allowed(run: Run) -> list[str]:
    if run.config.project.scope.allowed_paths:
        return list(run.config.project.scope.allowed_paths)
    return list(run.spec.allowed_paths)


def _parse_json_text(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    candidates = [text]
    if "```" in text:
        for block in text.split("```")[1::2]:
            block = block.strip()
            if block.startswith("json"):
                block = block[4:]
            candidates.append(block.strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _spec_from_agent(data: dict[str, Any]) -> Spec:
    verifications: list[Verification] = []
    for i, v in enumerate(data.get("verifications", []), start=1):
        if not isinstance(v, dict):
            continue
        kind = str(v.get("kind", "command"))
        if kind not in VerificationKind.__members__:
            kind = "command"
        verifications.append(
            Verification(
                id=str(v.get("id") or f"V{i}"),
                kind=VerificationKind(kind),
                description=str(v.get("description", "")).strip() or "(no description)",
                command=(str(v["command"]).strip() or None) if v.get("command") else None,
                to_create=bool(v.get("to_create", False)),
            )
        )
    requirements: list[Requirement] = []
    for i, r in enumerate(data.get("requirements", []), start=1):
        if not isinstance(r, dict):
            continue
        requirements.append(
            Requirement(
                id=str(r.get("id") or f"R{i}"),
                statement=str(r.get("statement", "")).strip() or "(empty)",
                rationale=str(r.get("rationale", "")),
                verification_ids=[str(x) for x in r.get("verification_ids", []) if str(x)],
            )
        )
    if not requirements:
        raise ValueError("no requirement in the specification")
    spec = Spec(
        requirements=requirements,
        verifications=verifications,
        out_of_scope=[str(x) for x in data.get("out_of_scope", [])],
        assumptions=[str(x) for x in data.get("assumptions", [])],
        allowed_paths=[str(x) for x in data.get("allowed_paths", []) if str(x).strip()],
        source="agent",
    )
    _normalise_spec(spec)
    return spec


def _normalise_spec(spec: Spec) -> None:
    known = {v.id for v in spec.verifications}
    for r in spec.requirements:
        r.verification_ids = [v for v in r.verification_ids if v in known]


def _undetermined_reasons(run: Run) -> list[str]:
    """One line per distinct reason, naming the requirements that share it.

    Seven requirements blocked by the same command is one fact, not seven; repeating it once per
    requirement is what made this unreadable.
    """
    by_reason: dict[str, list[str]] = {}
    for r in run.spec.requirements:
        if r.status is RequirementStatus.undetermined:
            by_reason.setdefault(r.status_reason or "no reason recorded", []).append(r.id)
    return [f"{', '.join(ids)}: {reason}" for reason, ids in by_reason.items()] or [
        "no reason recorded"
    ]


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def worktrees_root(configured: str | None, project_root: Path) -> Path:
    """Directory holding a project's run worktrees; always outside the project itself."""
    import hashlib
    import os

    base = configured or os.environ.get("FOUR95_WORKTREES_DIR")
    if base:
        root = Path(base).expanduser().resolve()
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser()
        root = (cache / "495" / "worktrees").resolve()
    digest = hashlib.sha1(str(project_root.resolve()).encode("utf-8")).hexdigest()[:8]
    return root / f"{project_root.name}-{digest}"


def project_snapshot(root: Path) -> str:
    """Fingerprint of the project's working tree: status listing plus the tracked diff."""
    try:
        status = git.status_porcelain(root)
        diff_text = git.git(["diff", "HEAD", "--no-color", "--no-ext-diff"], root, check=False)
    except (git.GitError, OSError):
        return "unavailable"
    return git.sha256_text(status + "\n" + diff_text)
