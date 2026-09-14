"""The workflow engine: a resumable state machine over :class:`Run`.

Phases::

    created ─► profiled ─► clarifying ─► clarified ─► specified ─► ready ─► producing ─►
    produced ─► verifying ─► verified ─► reviewing ─► reviewed ─►
    (accepted ─► delivered | rejected ─► ready | undetermined)

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
from typing import Any, assert_never

from harness495 import __version__
from harness495.agents.base import Agent, AgentResult, AgentTask
from harness495.agents.registry import build_agent
from harness495.core import budget as budget_mod
from harness495.core import git
from harness495.core import prompts as P
from harness495.core import proposals as proposals_mod
from harness495.core.context import (
    ContextPack,
    render_behaviour_test_form,
    render_catalogue,
    render_decisions_taken,
    render_evidence,
    render_lessons,
    render_mutation_reading,
    render_profile,
    render_reach_reading,
    render_refuted,
    render_reviews,
    render_spec,
    render_stability_reading,
    render_suite_reading,
    render_test_design,
    render_version,
    trim_output,
    truncate_diff,
)
from harness495.core.decide import Assessment, assess
from harness495.core.diff import code_lines
from harness495.core.models import (
    ADMISSIBLE,
    NON_DISCRIMINATING,
    REPLACED_PREFIX,
    AgentIdentity,
    BehaviourScenario,
    Capability,
    CatalogueRole,
    Clarification,
    ClarifyAnswer,
    ClarifyOption,
    ClarifyQuestion,
    ClarifyReply,
    ClarifyRound,
    Cost,
    CostBasis,
    Decision,
    DecisionAnswer,
    DecisionKind,
    DecisionMaker,
    DecisionOption,
    DecisionTaken,
    DesignedTest,
    Event,
    Evidence,
    EvidenceKind,
    Finding,
    HarnessConfig,
    Intent,
    Intervention,
    InterventionStatus,
    Iteration,
    LessonKind,
    PendingDecision,
    ReadinessCheck,
    ReportedCommand,
    Requirement,
    RequirementKind,
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
    TestDesign,
    Verdict,
    Verification,
    VerificationKind,
    Version,
    new_id,
    normalise_question,
    utcnow,
)
from harness495.core.mutation import Mutant, mutated_source, plan_mutants
from harness495.core.profile import detect_profile, read_doc_excerpts
from harness495.core.reach import (
    READERS,
    REPORT_DIR,
    Hits,
    Instrumented,
    cross,
    instrument,
    merge,
)
from harness495.core.report import render_markdown
from harness495.core.schemas import (
    CLARIFY_SCHEMA,
    PRODUCER_SUMMARY_SCHEMA,
    REVIEW_SCHEMA,
    SPEC_SCHEMA,
    TEST_DESIGNER_SUMMARY_SCHEMA,
)
from harness495.core.scope import check_scope, effective_allowed
from harness495.core.store import RunStore
from harness495.core.suite import (
    CountComparison,
    SuiteReading,
    compare_counts,
    read_suite_changes,
)
from harness495.core.verification import (
    VersionMismatch,
    assess_sufficiency,
    classify_instrument,
    instrument_files,
    looks_like_a_test,
    measures_the_change,
    reports_the_same_twice,
    run_control,
    run_verification,
)
from harness495.sandbox import Sandbox, select_sandbox
from harness495.sandbox.base import ExecRequest

DecisionHandler = Callable[[Run, PendingDecision], DecisionAnswer | None]
EventHandler = Callable[[Event], None]

OTHER_OPTION = "other"
"""The answer the harness adds to every clarification question: a tree may not force a false
choice, so every question can be answered in the requester's own words instead."""

PHASE_ENTRY: dict[RunStatus, RunStatus] = {
    RunStatus.clarifying: RunStatus.profiled,
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
        label: str = "495",
    ) -> None:
        self.store = store
        self._sandbox = sandbox
        self._sandbox_warnings: list[str] = []
        self.on_event = on_event
        self.decision_handler = decision_handler
        self.agent_factory = agent_factory or build_agent
        #: How this engine names itself to whoever finds the run already claimed.
        self.label = label
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
        """Advance until the run blocks (decision, pause, terminal state).

        The run is claimed for the duration: a second engine — another terminal, the run
        surface, a CI job — is refused rather than allowed to interleave its writes with
        these ones.
        """
        run = self.store.load(run_id)
        self.store.claim(run_id, self.label)
        try:
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
        finally:
            self.store.release(run_id)
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
        self,
        run_id: str,
        choice: str,
        note: str = "",
        made_by: DecisionMaker = DecisionMaker.human,
        answers: list[ClarifyReply] | None = None,
    ) -> Run:
        """Record an answer on the decision the run is stopped at.

        ``answers`` carries one reply per question of a ``clarify`` round; every other decision
        is one question and answers it with ``choice`` alone.
        """
        run = self.store.load(run_id)
        if run.pending_decision is None:
            raise EngineError("no pending decision")
        return self._apply_decision(run, choice, note, made_by, answers)

    def step(self, run: Run) -> Run:
        handler = {
            RunStatus.created: self._profile,
            RunStatus.profiled: self._clarify,
            RunStatus.clarifying: self._clarify,
            RunStatus.clarified: self._specify,
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
                run = self._apply_decision(
                    run, answer.choice, answer.note, DecisionMaker.human, answer.answers
                )
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
        answers: list[ClarifyAnswer] | None = None,
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
            answers=answers or [],
        )
        run.decisions.append(d)
        self.emit(
            run,
            "decision",
            f"{kind.value}: {outcome} ({made_by.value})",
            {"id": d.id, "rationale": rationale},
        )
        return d

    def _apply_decision(
        self,
        run: Run,
        choice: str,
        note: str,
        made_by: DecisionMaker,
        replies: list[ClarifyReply] | None = None,
    ) -> Run:
        pending = run.pending_decision
        if pending is None:
            raise EngineError("no pending decision")
        keys = {o.key for o in pending.options}
        if choice not in keys:
            raise EngineError(f"invalid choice {choice!r}; expected one of {sorted(keys)}")
        option = next(o for o in pending.options if o.key == choice)
        if option.needs_note and not note.strip():
            raise EngineError(f"choice {choice!r} requires a note")
        # Built before anything is recorded: an answer the round refuses leaves the run where it
        # was, still asking, rather than half-decided with the question already gone.
        answers = (
            self._clarify_answers(pending, choice, replies or [], made_by)
            if pending.kind is DecisionKind.clarify and choice != "abort"
            else []
        )
        self._record_decision(
            run, pending.kind, made_by, choice, note, question=pending.question, answers=answers
        )
        run.pending_decision = None
        kind = pending.kind
        if choice == "abort":
            return self._abort(
                run, f"aborted by {made_by.value} at {kind.value}: {note}".rstrip(": ")
            )
        match kind:
            case DecisionKind.clarify:
                self._record_clarify_answers(run, answers)
                self._set_status(run, RunStatus.clarifying)
            case DecisionKind.approve_spec:
                if choice in ("approve", "approve_with_gaps"):
                    run.spec.approved = True
                    run.spec.approved_by = made_by
                    self._set_status(run, RunStatus.ready)
                elif choice == "revise":
                    run.spec.approved = False
                    run.spec.assumptions.append(f"revision requested: {note}")
                    run.intent.text = run.intent.text  # unchanged; the note travels with the spec
                    self._set_status(run, RunStatus.clarified)
            case DecisionKind.readiness:
                if choice == "proceed":
                    self._set_status(run, RunStatus.profiled)
                elif choice == "allow_network":
                    run.config.sandbox.allow_network = True
                    self._warn(
                        run,
                        "verification commands now run with network access; "
                        "agent isolation is unchanged",
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
            case DecisionKind.no_progress:
                if choice == "respecify":
                    run.spec.approved = False
                    run.spec.assumptions.append(f"revision requested: {note}")
                    self._set_status(run, RunStatus.clarified)
                elif choice == "review_anyway":
                    self._set_status(run, RunStatus.produced)
                elif choice == "stop":
                    run.result.outcome = Verdict.reject
                    run.result.summary = "rejected: the corrections produced no change"
                    self._set_status(run, RunStatus.rejected)
            case DecisionKind.instrument_fault:
                if choice == "recalibrate":
                    self._recalibrate(run, note)
                    self._set_status(run, RunStatus.produced)
                elif choice == "respecify":
                    run.spec.approved = False
                    run.spec.assumptions.append(f"revision requested: {note}")
                    self._set_status(run, RunStatus.clarified)
                elif choice == "ignore":
                    # The verification keeps running and keeps being recorded, but goes on
                    # counting as proof of nothing, so the requirements it carries stay
                    # undetermined rather than becoming violations the producer would be sent to
                    # fix. The answer holds for the rest of the run: the fault is in the
                    # specification and has not moved.
                    self._set_status(run, run.resume_status or RunStatus.reviewed)
            case DecisionKind.iteration_limit:
                if choice == "continue":
                    run.budget.max_iterations += 1
                    self._set_status(run, RunStatus.ready)
                elif choice == "stop":
                    run.result.outcome = Verdict.reject
                    run.result.summary = "rejected after reaching the iteration limit"
                    self._set_status(run, RunStatus.rejected)
            case DecisionKind.undetermined:
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
            case DecisionKind.budget:
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
            case DecisionKind.scope:
                if choice == "allow":
                    it = run.current_iteration
                    if it is not None:
                        it.correction_requests = [
                            c for c in it.correction_requests if not c.startswith("[scope]")
                        ]
                    self._set_status(run, RunStatus.produced)
            case DecisionKind.acceptance:
                # The verdict the harness records for itself in _decide, from the evidence it
                # measured. It is never raised as a question, so no answer to it arrives here;
                # the case exists so that the kind is covered rather than overlooked.
                pass
            case _:
                assert_never(kind)
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
        profile.declined_roles = proposals_mod.declined_roles(self.store.load_proposals())
        profile.lessons = self.store.load_lessons().in_force
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

    def _clarify(self, run: Run) -> Run:
        """Put the decisions the intent leaves open to the requester, one round at a time.

        The clarifier reads the repository and returns the frontier: the decisions whose
        prerequisites are settled, each with its options, what each option does to the
        specification, a recommendation and what was checked to reach it. The harness never
        keeps a queue of them — every round is a new intervention over all the answers so far,
        because a question's options depend on answers not yet given, and a question already
        answered is dropped from the round rather than asked twice (0025).

        The phase ends when a round comes back with no question. One round runs after the last
        one the requester answered, to see whether the frontier is empty; when it is not, its
        questions are recorded unanswered and the specifier is told, so that an assumption
        taken in their place says what it stands on.
        """
        clar = run.clarification
        if clar.complete:
            self._set_status(run, RunStatus.clarified)
            return run
        if run.budget.max_clarify_rounds <= 0:
            clar.complete = True
            self._set_status(run, RunStatus.clarified)
            return run
        self._ensure_sandbox(run)
        assert run.profile is not None
        wt = self._worktree(run)
        self._set_status(run, RunStatus.clarifying)
        n = len(clar.rounds) + 1
        pack = ContextPack(role="clarifier")
        pack.add_fact("Intent (as given by the requester)", run.intent.text)
        pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
        pack.add_fact(
            "Test-library catalogue and the project's role coverage",
            render_catalogue(run.profile),
        )
        pack.add_fact("Tracked files (first 200)", "\n".join(git.top_level_listing(wt)) or "(none)")
        pack.add_fact(
            "Round",
            f"round {n}; the requester answers at most {run.budget.max_clarify_rounds} of them, "
            f"{clar.rounds_answered} answered so far",
        )
        pack.add_fact("Requester's decisions", render_decisions_taken(clar))
        if run.mode is RunMode.evaluate:
            pack.add_fact("Change under evaluation", render_version(self._evaluation_version(run)))
        for name, text in read_doc_excerpts(wt, run.profile.doc_files).items():
            pack.add_untrusted(f"repository file {name}", text)
        pack.instructions = P.CLARIFIER_TASK
        try:
            intervention, result = self._intervene(
                run,
                Role.clarifier,
                run.config.roles.clarifier,
                Capability.read,
                P.CLARIFIER_SYSTEM,
                pack,
                CLARIFY_SCHEMA,
            )
        except budget_mod.BudgetExceeded as exc:
            return self._budget_decision(run, str(exc), RunStatus.profiled)
        if result is None or result.status is not InterventionStatus.completed:
            # Nothing the clarifier produces is needed to specify: what it buys is that the
            # decisions were put to the requester, and one that never ran put none. The run
            # goes on with that said, rather than failing over a phase that asks questions.
            self._warn(
                run,
                "the clarifier did not complete "
                f"({(result.error or result.status.value) if result else 'no result'}); "
                "no decision was put to you, and the specifier decides what the intent leaves open",
            )
            clar.complete = True
            self._set_status(run, RunStatus.clarified)
            return run
        data = result.structured or _parse_json_text(result.text) or {}
        questions, dropped = _clarify_frontier(data, clar)
        round_ = ClarifyRound(n=n, intervention_id=intervention.id, dropped=dropped)
        clar.rounds.append(round_)
        for reason in dropped:
            self._warn(run, f"clarification round {n}: {reason}")
        if not questions:
            clar.complete = True
            self.emit(
                run,
                "clarify.settled",
                f"round {n} returned no question: nothing is left to decide before the "
                f"specification; {len(clar.answers)} decision(s) taken",
            )
            self._set_status(run, RunStatus.clarified)
            return run
        if clar.rounds_answered >= run.budget.max_clarify_rounds:
            clar.open_questions = questions
            clar.stopped_at_cap = True
            clar.complete = True
            round_.dropped.append(
                f"{len(questions)} question(s) recorded as unanswered: the cap of "
                f"{run.budget.max_clarify_rounds} answered round(s) was reached"
            )
            self._warn(
                run,
                f"the clarification stopped at {run.budget.max_clarify_rounds} answered round(s) "
                f"with {len(questions)} question(s) still open: "
                + "; ".join(q.title for q in questions)
                + "; the specifier decides them and records each as an assumption",
            )
            self._set_status(run, RunStatus.clarified)
            return run
        round_.questions = questions
        if run.config.auto_approve:
            answers = [_recommended_answer(q, DecisionMaker.harness) for q in questions]
            self._record_decision(
                run,
                DecisionKind.clarify,
                DecisionMaker.harness,
                "recommended",
                "auto-approve enabled: the recommended answer was taken for each question",
                question=_clarify_question_text(questions),
                answers=answers,
            )
            self._record_clarify_answers(run, answers)
            self._set_status(run, RunStatus.clarifying)
            return run
        return self._raise_decision(
            run,
            _clarify_decision(questions, n, run.budget.max_clarify_rounds),
            RunStatus.clarifying,
        )

    def _clarify_answers(
        self,
        pending: PendingDecision,
        choice: str,
        replies: list[ClarifyReply],
        made_by: DecisionMaker,
    ) -> list[ClarifyAnswer]:
        """The round's answers, one per question, or nothing and an error saying what is missing.

        A round is one reading and one gesture, so it is answered whole: a question left out
        would become a silent assumption, which is the thing the phase exists to remove.
        """
        if choice == "recommended":
            return [_recommended_answer(q, made_by) for q in pending.questions]
        given = {r.question_id: r for r in replies}
        answers: list[ClarifyAnswer] = []
        missing: list[str] = []
        for question in pending.questions:
            reply = given.get(question.id)
            if reply is None:
                missing.append(question.id)
                continue
            option = question.option(reply.option)
            if option is None:
                raise EngineError(
                    f"{question.id}: {reply.option!r} is not one of its options "
                    f"({', '.join(o.key for o in question.options)})"
                )
            if option.key == OTHER_OPTION and not reply.note.strip():
                raise EngineError(f"{question.id}: answering {OTHER_OPTION!r} requires a note")
            answers.append(
                ClarifyAnswer(
                    question_id=question.id,
                    question=question.title,
                    option=option.key,
                    label=option.label,
                    note=reply.note.strip()[:2000],
                    recommended=option.key == question.recommended,
                    taken_by=made_by,
                )
            )
        unknown = sorted(set(given) - {q.id for q in pending.questions})
        if unknown:
            raise EngineError(f"the round has no question {', '.join(unknown)}")
        if missing:
            raise EngineError(f"unanswered question(s): {', '.join(missing)}")
        return answers

    def _record_clarify_answers(self, run: Run, answers: list[ClarifyAnswer]) -> None:
        """Keep the answers on the round that asked them, and say what was decided."""
        if not answers or not run.clarification.rounds:
            return
        run.clarification.rounds[-1].answers = answers
        for answer in answers:
            self.emit(
                run,
                "clarify.answered",
                answer.statement,
                {
                    "question": answer.question_id,
                    "option": answer.option,
                    "by": answer.taken_by.value,
                },
            )

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
        passing_on_base = {
            r.command for r in run.profile.readiness if r.executable and r.exit_code == 0
        }
        run.test_design = None  # the tests written for a previous specification do not carry over
        decisions = _decisions_taken(run.clarification)
        if run.spec.source == "user" and run.spec.requirements:
            run.spec.decisions_taken = decisions
            _normalise_spec(run.spec)
            assess_sufficiency(run.spec, executable, passing_on_base, run.profile)
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
        if run.clarification.says_anything:
            pack.add_fact("Requester's decisions", render_decisions_taken(run.clarification))
        pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
        # A refuted reviewer claim bears on a reviewer, not on how the change is specified.
        for_spec = [x for x in run.profile.lessons if x.kind is not LessonKind.false_positive]
        if for_spec:
            pack.add_fact(
                "What earlier runs showed about this project",
                render_lessons(for_spec),
            )
        pack.add_fact(
            "Test-library catalogue and the project's role coverage",
            render_catalogue(run.profile),
        )
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
            return self._budget_decision(run, str(exc), RunStatus.clarified)
        if result is None or result.status is not InterventionStatus.completed:
            return self._fail(
                run,
                f"specifier failed: {result.error if result else 'no result'}",
                RunStatus.clarified,
            )
        data = result.structured or _parse_json_text(result.text)
        if not data:
            return self._fail(
                run, "specifier returned no parsable specification", RunStatus.clarified
            )
        try:
            spec = _spec_from_agent(data)
        except (ValueError, KeyError, TypeError) as exc:
            return self._fail(
                run, f"specification rejected by schema validation: {exc}", RunStatus.clarified
            )
        if run.spec.assumptions:
            spec.assumptions.extend(
                a for a in run.spec.assumptions if a.startswith("revision requested")
            )
        if not spec.allowed_paths and run.config.project.scope.allowed_paths:
            spec.allowed_paths = list(run.config.project.scope.allowed_paths)
        spec.decisions_taken = decisions
        run.spec = spec
        assess_sufficiency(run.spec, executable, passing_on_base, run.profile)
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

    def _preflight(self, run: Run) -> list[Evidence]:
        """Run each proposed command once on the base version, before anything is produced.

        Nothing is concluded from what comes back. The change does not exist yet, so a failure is
        expected of the commands that measure it and means nothing on its own. What this buys is
        that no command reaches the requester unexecuted: its output is on file at the moment the
        specification is approved, for whoever reads the question to judge.
        """
        if run.mode is not RunMode.change or run.profile is None:
            return []
        wt = self._worktree(run)
        if not wt.exists():
            return []
        already = {r.command for r in run.profile.readiness}
        already |= {
            e.command for e in run.evidence if e.kind is EvidenceKind.baseline and e.command
        }
        produced: list[Evidence] = []
        for v in run.spec.verifications:
            if not v.command or v.command in already or v.sufficiency not in ADMISSIBLE:
                continue
            already.add(v.command)
            req = ExecRequest(
                command=v.command,
                cwd=wt,
                timeout_s=v.timeout_s or run.budget.command_timeout_s,
                writable=True,
                network=run.config.sandbox.allow_network,
                stop_check=self._stop_check(run),
            )
            res = self.sandbox.run(req)
            if res.interrupted:
                raise KeyboardInterrupt
            ev = Evidence(
                id=new_id("ev"),
                kind=EvidenceKind.baseline,
                iteration=0,
                subject_version=run.profile.base_commit,
                verification_id=v.id,
                command=v.command,
                exit_code=res.exit_code,
                expected_exit_code=v.expected_exit_code,
                passed=None,  # what it reports here is not yet about anything
                summary=f"never run before: exit {res.exit_code} on the base version",
            )
            ev.output_ref = self.store.write_text(
                run.id, str(self.store.evidence_dir(run.id, ev.id) / "output.txt"), res.output
            )
            ev.output_sha256 = git.sha256_text(res.output)
            ev.duration_s = res.duration_s
            ev.sandbox = self.sandbox.describe(req)
            produced.append(ev)
            self.emit(
                run,
                "preflight",
                f"{v.id}: exit {res.exit_code} on the base version, before the change exists",
                {"id": ev.id, "verification": v.id},
            )
        run.evidence.extend(produced)
        return produced

    def _gate(self, run: Run) -> Run:
        preflight = self._preflight(run)
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
        if preflight:
            # Said, not read: on a tree without the change, a command that measures the change is
            # meant to fail. This is what each of them printed there, and what it means is the
            # reader's to decide.
            printed = "; ".join(f"{e.verification_id} exits {e.exit_code}" for e in preflight)
            question += f" Run once on the base version, before the change exists: {printed}."
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
                "preflight": [
                    {
                        "verification": e.verification_id,
                        "command": e.command,
                        "exit_code": e.exit_code,
                        "output_ref": e.output_ref,
                    }
                    for e in preflight
                ],
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
        blocked = self._design_tests(run)
        if blocked is not None:
            return blocked
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
        if run.clarification.says_anything:
            pack.add_fact("Requester's decisions", render_decisions_taken(run.clarification))
        pack.add_fact("Approved specification", render_spec(run.spec))
        pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
        pack.add_fact("Behaviour scenarios", render_behaviour_test_form(run.profile))
        scope_lines = [
            "Allowed paths: " + (", ".join(effective_allowed(run)) or "any path"),
            "Forbidden paths: " + ", ".join(run.config.project.scope.forbidden_paths),
        ]
        design = run.test_design
        if design is not None and design.files:
            pack.add_fact("Tests written by the test designer", render_test_design(design))
            scope_lines.append(
                "Protected paths (tests written by the test designer; a version that modifies "
                "one is rejected): " + ", ".join(design.files)
            )
        pack.add_fact("Scope", "\n".join(scope_lines))
        if design is not None and design.not_done:
            pack.add_untrusted(
                "what the test designer reported it could not write (agent-produced)",
                "\n".join(f"- {c}" for c in design.not_done),
            )
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
            iteration.commands_reported = [
                ReportedCommand(
                    command=str(c["command"]).strip()[:500], exit_code=int(c["exit_code"])
                )
                for c in (result.structured.get("commands_run") or [])
                if isinstance(c, dict)
                and str(c.get("command", "")).strip()
                and isinstance(c.get("exit_code"), int)
            ][:20]
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

    def _design_tests(self, run: Run) -> Run | None:
        """Write the tests to create in an intervention of their own, before the producer.

        The producer that writes the test that judges its change is one reasoner checking
        itself: the control run only shows that such a test fails without the change, not that
        it asserts anything (0019). The test designer writes the tests from the approved
        scenarios in a tree where the behaviour does not exist yet, the harness commits them,
        and the producer receives them as protected files. Runs once per approved
        specification; returns the run when it had to stop it (budget, failure), None when
        the producer may go on.
        """
        roles = run.config.roles
        if (
            run.mode is not RunMode.change
            or run.test_design is not None
            or roles.test_designer is None
            or not any(v.to_create and v.sufficiency in ADMISSIBLE for v in run.spec.verifications)
        ):
            return None
        assert run.profile is not None and run.profile.base_commit
        wt = self._worktree(run)
        self._set_status(run, RunStatus.producing)
        before = git.head_commit(wt)
        pack = ContextPack(role="test_designer")
        pack.add_fact("Intent (as given by the requester)", run.intent.text)
        if run.clarification.says_anything:
            pack.add_fact("Requester's decisions", render_decisions_taken(run.clarification))
        pack.add_fact("Approved specification", render_spec(run.spec))
        pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
        pack.add_fact("Behaviour scenarios", render_behaviour_test_form(run.profile))
        pack.add_fact(
            "Scope",
            "Test files only, within the allowed paths: "
            + (", ".join(effective_allowed(run)) or "any path")
            + ". Any other file you write is put back as it was.",
        )
        pack.add_fact(
            "Version",
            f"commit {before}; the behaviour the tests observe is not implemented here, and the "
            "harness commits your tests when you finish",
        )
        pack.instructions = P.TEST_DESIGNER_TASK
        try:
            intervention, result = self._intervene(
                run,
                Role.test_designer,
                roles.test_designer,
                Capability.write,
                P.TEST_DESIGNER_SYSTEM,
                pack,
                TEST_DESIGNER_SUMMARY_SCHEMA,
            )
        except budget_mod.BudgetExceeded as exc:
            return self._budget_decision(run, str(exc), RunStatus.ready)
        if intervention.status is InterventionStatus.tampered:
            return self._fail(
                run,
                "the test designer modified the project working tree instead of its worktree; "
                f"the run stops so you can inspect `git -C {run.project_root} status`",
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
                f"test designer did not complete: {result.error if result else 'no result'}",
                RunStatus.ready,
            )
        if result.status is not InterventionStatus.completed:
            self._warn(
                run,
                f"test designer ended with {result.status.value}: {result.error}; keeping "
                "whatever tests were written",
            )
        written = git.dirty_paths(wt)
        kept = [f for f in written if looks_like_a_test(f)]
        discarded = [f for f in written if f not in kept]
        if discarded:
            git.discard_paths(wt, discarded)
            self._warn(
                run,
                "the test designer wrote files that are not tests, put back as they were: "
                + ", ".join(discarded),
            )
        reported: list[DesignedTest] = []
        not_done: list[str] = []
        if isinstance(result.structured, dict):
            not_done = [
                str(c).strip()[:500]
                for c in (result.structured.get("not_done") or [])
                if str(c).strip()
            ][:20]
            reported = [
                DesignedTest(
                    verification_id=str(t["verification_id"]).strip()[:50],
                    file=str(t["file"]).strip()[:500],
                )
                for t in (result.structured.get("tests") or [])
                if isinstance(t, dict) and t.get("verification_id") and t.get("file")
            ][:50]
        commit = git.commit_all(wt, f"495 tests: {run.intent.text[:60]}") or before
        run.test_design = TestDesign(
            intervention_id=intervention.id,
            base_commit=before,
            commit=commit,
            files=kept,
            discarded=discarded,
            reported=reported,
            not_done=not_done,
        )
        for claim in not_done:
            self.emit(run, "test_designer.blocked", claim)
        if kept:
            self.emit(
                run,
                "tests.designed",
                f"{len(kept)} test file(s) written by the test designer, committed as "
                f"{commit[:12]}; the producer may not modify them",
                {"files": kept, "commit": commit, "intervention": intervention.id},
            )
        else:
            self._warn(
                run,
                "the test designer wrote no test file; the producer creates the tests to create "
                "itself, and the test_quality reviewer reads them",
            )
        self.store.save(run)
        return None

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
        allowed = effective_allowed(run)
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
        design = run.test_design
        if design is not None and design.files:
            # The tests the designer wrote are the instrument; the change is what they measure.
            # A version that edits one has moved the instrument, and what the instrument then
            # reports is about the edit, not about the behaviour: that version is out of scope.
            touched = [
                f
                for f in git.diff_names(wt, design.commit, it.version.head_commit)
                if f in design.files
            ]
            protected_ev = Evidence(
                id=new_id("ev"),
                kind=EvidenceKind.scope_check,
                iteration=it.n,
                subject_version=it.version.head_commit,
                passed=not touched,
                summary=(
                    f"{len(touched)} test file(s) written by the test designer modified by the "
                    "change: " + ", ".join(touched)
                    if touched
                    else f"the {len(design.files)} test file(s) written by the test designer "
                    "are as written"
                ),
            )
            evidence.append(protected_ev)
            self.emit(
                run,
                "evidence",
                f"protected tests: {'ok' if not touched else 'VIOLATION'} - {protected_ev.summary}",
                {"id": protected_ev.id},
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
        evidence.extend(self._repeat(run, it, evidence))
        evidence.append(self._check_suite(run, it, evidence))
        it.instrument_faults = []
        calibration, proposals = self._calibrate(run, it, evidence)
        evidence.extend(calibration)
        if not it.instrument_faults:
            # An instrument the calibration found blind is about to stop the run; measuring
            # what it reaches and what it lets through would describe that instrument, not the
            # tests.
            evidence.extend(self._reach(run, it, evidence))
            evidence.extend(self._mutate(run, it, evidence))
        # Verification runs may write caches; restore the exact version for the reviewers.
        git.reset_hard_clean(wt, it.version.head_commit)
        run.evidence.extend(evidence)
        it.evidence_ids.extend(e.id for e in evidence)
        self._set_status(run, RunStatus.verified)
        if it.instrument_faults and not self._instrument_fault_settled(run):
            # Nothing downstream can recover from this. Reviewers would be handed a failure that
            # is not the change's, or a success that is not the change's either, and would spend a
            # full round reasoning about the wrong object.
            return self._raise_decision(
                run, self._instrument_decision(run, it, proposals), RunStatus.verified
            )
        return run

    def _flipped_since(self, run: Run, it: Iteration, evidence: list[Evidence]) -> set[str]:
        """The verifications that report something else than they did on the previous iteration.

        A flip is where an unstable command does its damage: it is the moment the harness
        either credits a requirement it refused before, or charges one it credited, and it
        cannot tell the producer's work from the command's own weather. Both readings ask for
        the same thing — run it again — so a flipped command is repeated before any other.
        """
        if it.n < 2 or len(run.iterations) < it.n:
            return set()
        before: dict[str, bool | None] = {}
        for e in (run.evidence_by_id(x) for x in run.iterations[it.n - 2].evidence_ids):
            if e is not None and e.kind is EvidenceKind.command_result and e.verification_id:
                before[e.verification_id] = e.passed
        return {
            e.verification_id
            for e in evidence
            if e.kind is EvidenceKind.command_result
            and e.verification_id
            and e.passed is not None
            and before.get(e.verification_id) is not None
            and before[e.verification_id] != e.passed
        }

    def _repeat_watchers(
        self, run: Run, it: Iteration, evidence: list[Evidence]
    ) -> list[Verification]:
        """The commands worth running a second time on the version under review.

        Every command a requirement leans on and that reported something: what it reported is
        about to credit that requirement or charge it, and a reading taken once says nothing
        about whether it repeats. A command that did not run has nothing to compare, and one
        slower on the change than the budget allows is left out with a warning, since the
        check costs one more run of it. What comes first is the command whose result flipped
        since the previous iteration, then the cheapest, so that a cap spends itself where a
        difference has already been seen.
        """
        durations = {
            e.verification_id: e.duration_s or 0.0
            for e in evidence
            if e.kind is EvidenceKind.command_result and e.verification_id and e.passed is not None
        }
        carried = {vid for r in run.spec.requirements for vid in r.verification_ids}
        flipped = self._flipped_since(run, it, evidence)
        watchers: list[Verification] = []
        slow: set[str] = set()
        for v in run.spec.verifications:
            if v.command is None or v.sufficiency not in ADMISSIBLE or v.id not in durations:
                continue
            if v.id not in carried:
                continue
            if durations[v.id] > run.budget.repeat_command_max_s:
                slow.add(v.id)
                continue
            watchers.append(v)
        for vid in sorted(slow):
            self._warn(
                run,
                f"{vid} took {durations[vid]:.0f}s on the change, over the "
                f"{run.budget.repeat_command_max_s}s a second run is given: whether it reports "
                "the same thing twice is not measured",
            )
        return sorted(watchers, key=lambda v: (v.id not in flipped, durations[v.id]))

    def _repeat(self, run: Run, it: Iteration, evidence: list[Evidence]) -> list[Evidence]:
        """Run the commands the requirements lean on a second time on the same version.

        Every other control the harness runs compares two trees; this one compares two runs of
        the same command on the same tree, where nothing changed between them. A command that
        reports success once and failure once is not an instrument: what it happened to report
        first would credit a requirement no one could reproduce, or send the producer after a
        defect that is not in the change. Either reading is withdrawn and the requirement waits
        for the requester (``docs/decisions/0024``).

        The second run follows the first in the worktree the verifications left, in the order
        they ran in, so that a command finding what an earlier one built still finds it.
        """
        assert it.version is not None and it.version.head_commit
        for v in run.spec.verifications:
            v.stable = None
        limit = run.budget.max_repeated_commands
        watchers = self._repeat_watchers(run, it, evidence)[:limit] if limit > 0 else []
        if not watchers:
            return []
        first_run = {
            e.verification_id: e
            for e in evidence
            if e.kind is EvidenceKind.command_result and e.verification_id
        }
        req_by_verification: dict[str, list[str]] = {}
        for r in run.spec.requirements:
            for vid in r.verification_ids:
                req_by_verification.setdefault(vid, []).append(r.id)
        wt = self._worktree(run)
        produced: list[Evidence] = []
        for v in watchers:
            assert v.command is not None
            first = first_run[v.id]
            req = ExecRequest(
                command=v.command,
                cwd=wt,
                timeout_s=v.timeout_s or run.budget.command_timeout_s,
                writable=True,
                network=run.config.sandbox.allow_network,
                stop_check=self._stop_check(run),
            )
            res = self.sandbox.run(req)
            if res.interrupted:
                raise KeyboardInterrupt
            stable, summary = reports_the_same_twice(
                v.expected_exit_code,
                first.exit_code,
                self.store.read_text(run.id, first.output_ref or ""),
                first.summary == "timed out",
                res,
            )
            v.stable = stable
            eid = new_id("ev")
            ev = Evidence(
                id=eid,
                kind=EvidenceKind.stability_check,
                iteration=it.n,
                subject_version=it.version.head_commit,
                verification_id=v.id,
                requirement_ids=[] if stable else req_by_verification.get(v.id, []),
                command=v.command,
                exit_code=res.exit_code,
                expected_exit_code=v.expected_exit_code,
                passed=stable,
                summary=f"{v.id} {summary}",
                output_ref=self.store.write_text(
                    run.id, str(self.store.evidence_dir(run.id, eid) / "output.txt"), res.output
                ),
                output_sha256=git.sha256_text(res.output),
                duration_s=res.duration_s,
                sandbox=self.sandbox.describe(req),
            )
            produced.append(ev)
            self.emit(
                run,
                "evidence",
                f"stability: {'ok' if stable else 'UNSTABLE'} - {ev.summary}",
                {"id": ev.id, "verification": v.id},
            )
        return produced

    def _suite_reading(self, run: Run, it: Iteration, evidence: list[Evidence]) -> SuiteReading:
        """What the change did to the suite that passed on the base: the diff over the test
        files that existed there, and the runner's tally on both versions for each command a
        non-regression requirement leans on (the base's from the baseline run of the same
        command, the change's from this iteration)."""
        assert it.version is not None and it.version.head_commit
        wt = self._worktree(run)
        changes = read_suite_changes(git.diff(wt, it.version.base_commit, it.version.head_commit))
        baseline_by_command = {
            e.command: e
            for e in run.evidence
            if e.kind is EvidenceKind.baseline and e.command and e.output_ref
        }
        counts: list[CountComparison] = []
        for vid in _non_regression_verifications(run.spec):
            v = run.spec.verification(vid)
            result = next(
                (
                    e
                    for e in reversed(evidence)
                    if e.kind is EvidenceKind.command_result
                    and e.verification_id == vid
                    and e.output_ref
                ),
                None,
            )
            base = baseline_by_command.get(v.command or "") if v else None
            if v is None or result is None or base is None:
                continue
            comparison = compare_counts(
                vid,
                self.store.read_text(run.id, base.output_ref or ""),
                self.store.read_text(run.id, result.output_ref or ""),
            )
            if comparison is not None:
                counts.append(comparison)
        return SuiteReading(changes=changes, counts=counts)

    def _check_suite(self, run: Run, it: Iteration, evidence: list[Evidence]) -> Evidence:
        """One evidence saying whether the existing suite is, on the change, the suite the base
        passed. It names the non-regression requirements that lean on a test command, since
        those are the ones a passing command would otherwise credit."""
        assert it.version is not None
        reading = self._suite_reading(run, it, evidence)
        named = [
            r.id
            for r in run.spec.requirements
            if r.kind is RequirementKind.non_regression
            and any(
                v.command and v.kind is VerificationKind.test
                for v in map(run.spec.verification, r.verification_ids)
                if v is not None
            )
        ]
        ev = Evidence(
            id=new_id("ev"),
            kind=EvidenceKind.suite_check,
            iteration=it.n,
            subject_version=it.version.head_commit,
            requirement_ids=named,
            passed=not reading.weakened,
            summary=reading.summary(),
        )
        self.emit(
            run,
            "evidence",
            f"suite: {'ok' if ev.passed else 'WEAKENED'} - {ev.summary}",
            {"id": ev.id},
        )
        return ev

    def _coverage_watchers(self, run: Run, evidence: list[Evidence]) -> list[Verification]:
        """The commands worth running again under the project's coverage tool.

        A ``test`` verification that reported success on the evaluated commit and observes the
        change. Only a test is instrumented: a linter, a build or a type checker reads the
        source without executing it, and a coverage engine put in front of one would report
        that the change runs nowhere, which is about the command and not about the tests. A
        command already failing is being corrected, and one the calibration found blind, or
        one the second run did not agree with, describes itself. The cheapest goes first,
        since what bounds the check is a number of commands.
        """
        durations = {
            e.verification_id: e.duration_s or 0.0
            for e in evidence
            if e.kind is EvidenceKind.command_result and e.passed is True and e.verification_id
        }
        watchers = [
            v
            for v in run.spec.verifications
            if v.command
            and v.kind is VerificationKind.test
            and v.sufficiency in ADMISSIBLE
            and v.discriminates is not False
            and v.stable is not False
            and v.id in durations
        ]
        return sorted(watchers, key=lambda v: durations[v.id])

    def _instrument(self, run: Run, command: str) -> Instrumented | None:
        """The command rewritten to write a coverage report, from the tool the profile found.

        The project's own tool makes the measure, and the profile says which one it is, per
        technology (``RoleCoverage`` of the ``coverage`` role). A project that measures the
        role with nothing, or with a tool this cannot drive, is not instrumented: the gap is
        the catalogue's to state and the requester's to close by a proposal, never the
        harness's to close by a command it invented (``docs/decisions/0014``).
        """
        assert run.profile is not None
        for row in run.profile.role_coverage:
            if row.role is not CatalogueRole.coverage or not row.tools:
                continue
            found = instrument(row.technology, row.tools, command, REPORT_DIR)
            if found is not None:
                return found
        return None

    def _reach(self, run: Run, it: Iteration, evidence: list[Evidence]) -> list[Evidence]:
        """Measure which lines the change adds the verifications execute, and which they miss.

        The control run and the mutation check both ask what a command reports on another
        version of the tree; neither says anything about a line no command runs, since a
        command that never executes a line reports the same thing whatever that line says. The
        project's own coverage tool answers that, so the harness runs the test commands once
        more under it and crosses the report with the diff. A line the report holds with no
        hit leaves the behaviour requirements resting on those commands undetermined, for the
        same reason a surviving mutant does: the line may carry behaviour no requirement
        states, and only a reader tells that from a hole in the tests
        (``docs/decisions/0023``).
        """
        assert it.version is not None and it.version.head_commit
        limit = run.budget.max_coverage_commands
        watchers = self._coverage_watchers(run, evidence)[:limit] if limit > 0 else []
        pairs = [
            (v, recipe)
            for v in watchers
            if (recipe := self._instrument(run, v.command or "")) is not None
        ]
        if not pairs:
            return []
        wt = self._worktree(run)
        head = it.version.head_commit
        test_commands = [
            v.command
            for v in run.spec.verifications
            if v.command and v.kind is VerificationKind.test
        ]
        lines = code_lines(git.diff(wt, it.version.base_commit, head), test_commands)
        if not lines:
            # The change adds no line a coverage engine counts (test files, documentation): a
            # run of the commands would measure nothing to cross.
            return []
        hits: Hits = {}
        measured: list[str] = []
        tools: list[str] = []
        last = ""
        try:
            for v, recipe in pairs:
                # The tool writes its data file where it is told and creates no directory for
                # it; a report left by the command before is not read as this one's.
                shutil.rmtree(wt / REPORT_DIR, ignore_errors=True)
                (wt / REPORT_DIR).mkdir(parents=True, exist_ok=True)
                res = self.sandbox.run(
                    ExecRequest(
                        command=recipe.command,
                        cwd=wt,
                        timeout_s=run.budget.command_timeout_s,
                        writable=True,
                        network=run.config.sandbox.allow_network,
                        env=dict(recipe.env),
                        stop_check=self._stop_check(run),
                    )
                )
                if res.interrupted:
                    raise KeyboardInterrupt
                last = res.output
                found: Hits = {}
                for path in sorted(wt.glob(recipe.report)):
                    text = path.read_text(encoding="utf-8", errors="replace")
                    merge(found, READERS[recipe.reader](text))
                if not found:
                    state = "timed out" if res.timed_out else f"exit {res.exit_code}"
                    self._warn(
                        run,
                        f"{v.id} under {recipe.tool} wrote no coverage report ({state}): which "
                        "lines of the change it executes is not measured",
                    )
                    continue
                measured.append(v.id)
                tools.append(recipe.tool)
                merge(hits, found)
        finally:
            # The measure writes in the worktree; the reviewers read the version under review.
            git.reset_hard_clean(wt, head)
        reading = cross(lines, hits, measured, tools)
        # What an unexecuted line leaves undetermined: a requirement that states the change
        # makes something true, and rests on one of the commands that were measured.
        stakes = [
            r.id
            for r in run.spec.requirements
            if r.kind is RequirementKind.behaviour
            and set(measured).intersection(r.verification_ids)
        ]
        eid = new_id("ev")
        ev = Evidence(
            id=eid,
            kind=EvidenceKind.coverage_check,
            iteration=it.n,
            subject_version=head,
            requirement_ids=stakes if reading.missed else [],
            passed=None if not measured else not reading.missed,
            summary=reading.summary(),
        )
        if not measured or reading.missed:
            ev.output_ref = self.store.write_text(
                run.id, str(self.store.evidence_dir(run.id, eid) / "output.txt"), last
            )
            ev.output_sha256 = git.sha256_text(last)
        self.emit(
            run,
            "evidence",
            f"coverage: {'ok' if ev.passed else 'NOT EXECUTED' if ev.passed is False else 'not measured'}"
            f" - {ev.summary}",
            {"id": ev.id},
        )
        return [ev]

    def _mutation_watchers(self, run: Run, evidence: list[Evidence]) -> list[Verification]:
        """The commands worth running against a wrong version of the change.

        Every command that reported success on the evaluated commit twice and can say
        something else on another tree: a command already failing is being corrected, and what
        a command that does not repeat its own reading reports on an altered version of the
        same code is not a statement about anything. The
        set is not restricted to the requirement a mutated line belongs to, because the
        harness does not know which requirement a line belongs to: what a mutant asks is
        whether the evidence the run rests on, taken together, tells this version of the
        change from a wrong one. A command slower on the change than the budget allows is left
        out with a warning, since the check costs one run per mutant; the rest are ordered by
        what they took, so that the cheapest gets the chance to settle the mutant first.
        """
        durations = {
            e.verification_id: e.duration_s or 0.0
            for e in evidence
            if e.kind is EvidenceKind.command_result and e.passed is True and e.verification_id
        }
        watchers: list[Verification] = []
        slow: set[str] = set()
        for v in run.spec.verifications:
            if (
                v.command is None
                or v.sufficiency not in ADMISSIBLE
                or v.discriminates is False
                or v.stable is False
                or v.id not in durations
            ):
                continue
            if durations[v.id] > run.budget.mutant_command_max_s:
                slow.add(v.id)
                continue
            watchers.append(v)
        for vid in sorted(slow):
            self._warn(
                run,
                f"{vid} took {durations[vid]:.0f}s on the change, over the "
                f"{run.budget.mutant_command_max_s}s a mutant run is given: what it lets "
                "through is not measured",
            )
        return sorted(watchers, key=lambda v: durations[v.id])

    def _mutate(self, run: Run, it: Iteration, evidence: list[Evidence]) -> list[Evidence]:
        """Measure what the verifications let through, on wrong versions of the change itself.

        The calibration says each command reports something else without the change; it cannot
        say the command would report something else if the change were wrong. So the harness
        writes a few wrong versions: one line of the diff altered in one stated way each, on a
        worktree of the evaluated commit. A wrong version every command reports success on is
        one the run's evidence does not tell from the change, and the behaviour requirements
        resting on those commands are left undetermined for the requester to rule on: a mutant
        may be equivalent to the line it replaces, and only a reader can tell that from a hole
        in the tests (``docs/decisions/0022``).
        """
        assert it.version is not None and it.version.head_commit
        watchers = self._mutation_watchers(run, evidence)
        # What a mutant nothing reports leaves undetermined: a requirement that states the
        # change makes something true, and rests on one of the commands that passed it.
        watched = {v.id for v in watchers}
        stakes = [
            r.id
            for r in run.spec.requirements
            if r.kind is RequirementKind.behaviour and watched.intersection(r.verification_ids)
        ]
        if not watchers or not stakes:
            return []
        wt = self._worktree(run)
        head = it.version.head_commit
        mutants = plan_mutants(
            git.diff(wt, it.version.base_commit, head),
            run.budget.max_mutants,
            [
                v.command
                for v in run.spec.verifications
                if v.command and v.kind is VerificationKind.test
            ],
        )
        if not mutants:
            return []
        produced: list[Evidence] = []
        mutant_wt = wt.parent / f"{run.id}.mutant"
        root = Path(run.project_root)
        git.remove_worktree(root, mutant_wt)
        shutil.rmtree(mutant_wt, ignore_errors=True)
        try:
            git.add_worktree_detached(root, mutant_wt, head)
        except git.GitError as exc:
            self._warn(run, f"cannot measure the verifications against wrong versions: {exc}")
            return []
        try:
            for mutant in mutants:
                produced.append(self._run_mutant(run, it, mutant, watchers, stakes, mutant_wt))
        finally:
            git.remove_worktree(root, mutant_wt)
            shutil.rmtree(mutant_wt, ignore_errors=True)
        return produced

    def _run_mutant(
        self,
        run: Run,
        it: Iteration,
        mutant: Mutant,
        watchers: list[Verification],
        stakes: list[str],
        mutant_wt: Path,
    ) -> Evidence:
        """Apply one mutant, run the commands watching it, and record what they reported.

        The first command that fails settles it: one report is enough to say the change is
        told from this wrong version of it, and the commands that would have run after it say
        nothing more. A mutant no command reports is charged to every behaviour requirement
        those commands carry, since which of them the altered line serves is exactly what the
        harness cannot read.
        """
        assert it.version is not None
        source = mutant_wt / mutant.file
        original = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
        written = mutated_source(original, mutant) if original else None
        eid = new_id("ev")
        if written is None:
            return Evidence(
                id=eid,
                kind=EvidenceKind.mutation_check,
                iteration=it.n,
                subject_version=it.version.head_commit,
                passed=None,
                summary=f"{mutant.describe()}: the line is not where the diff put it; not applied",
            )
        ran: list[str] = []
        killer: str | None = None
        last = ""
        state = ""
        source.write_text(written, encoding="utf-8")
        try:
            for v in watchers:
                assert v.command is not None
                res = self.sandbox.run(
                    ExecRequest(
                        command=v.command,
                        cwd=mutant_wt,
                        timeout_s=run.budget.mutant_command_max_s * 2,
                        writable=True,
                        network=run.config.sandbox.allow_network,
                        stop_check=self._stop_check(run),
                    )
                )
                if res.interrupted:
                    raise KeyboardInterrupt
                ran.append(v.id)
                last = res.output
                # A command that times out on the mutant is counted as having reported it: it
                # did not report success, and calling that "let through" would be an
                # accusation resting on a run that did not finish.
                state = "timed out" if res.timed_out else f"exit {res.exit_code}"
                if res.timed_out or res.exit_code != v.expected_exit_code:
                    killer = v.id
                    break
        finally:
            source.write_text(original, encoding="utf-8")
        summary = f"{mutant.describe()}: " + (
            f"{killer} reported it ({state})"
            if killer is not None
            else f"passed by every command that watches the change ({', '.join(ran)})"
        )
        ev = Evidence(
            id=eid,
            kind=EvidenceKind.mutation_check,
            iteration=it.n,
            subject_version=it.version.head_commit,
            verification_id=killer,
            requirement_ids=[] if killer is not None else stakes,
            passed=killer is not None,
            summary=summary,
            output_ref=self.store.write_text(
                run.id, str(self.store.evidence_dir(run.id, eid) / "output.txt"), last
            ),
            output_sha256=git.sha256_text(last),
        )
        self.emit(
            run,
            "evidence",
            f"mutation: {'reported' if ev.passed else 'LET THROUGH'} - {ev.summary}",
            {"id": ev.id, "mutant": mutant.id},
        )
        return ev

    def _recalibrate(self, run: Run, note: str) -> None:
        """Point a verification at another command, keeping the requirement it carries.

        The command is not adopted on anyone's say-so: the run goes back to verifying, and the
        replacement is measured on both versions exactly as the one it replaces was.
        """
        it = run.current_iteration
        faulty = [v for v in run.spec.verifications if v.sufficiency in NON_DISCRIMINATING]
        if not faulty:
            raise EngineError("no verification is at fault, so there is no command to replace")
        head, sep, tail = note.partition(":")
        named = head.strip()
        chosen = next((v for v in faulty if v.id == named), None)
        command = tail if chosen is not None else note
        if chosen is None:
            # A note that opens on the id of a verification is naming one, and naming the wrong
            # one is a mistake to report rather than a command that happens to start with `V2:`.
            if sep and any(v.id == named for v in run.spec.verifications):
                raise EngineError(
                    f"{named} is not one of the verifications at fault: "
                    + ", ".join(v.id for v in faulty)
                )
            if len(faulty) != 1:
                raise EngineError(
                    "name the verification the command is for, as `" + faulty[0].id + ": <command>`"
                )
            chosen = faulty[0]
        command = command.strip()
        if not command:
            raise EngineError("the note must carry the command to use instead")
        previous = chosen.command
        chosen.command = command
        chosen.sufficiency = Sufficiency.sufficient
        chosen.discriminates = None
        chosen.rationale = f"{REPLACED_PREFIX}{previous}` on the requester's instruction"
        if it is not None:
            it.instrument_faults = [
                f for f in it.instrument_faults if not f.startswith(f"{chosen.id}:")
            ]
        run.spec.artifact_ref = self.store.write_json(
            run.id,
            str(self.store.artifacts_dir(run.id) / "spec.json"),
            run.spec.model_dump(mode="json"),
        )
        self.emit(
            run,
            "verification.replaced",
            f"{chosen.id}: `{command}` replaces `{previous}`; it is measured on both versions "
            "before it counts",
            {"verification": chosen.id},
        )

    @staticmethod
    def _instrument_fault_settled(run: Run) -> bool:
        return any(
            d.kind is DecisionKind.instrument_fault and d.outcome == "ignore" for d in run.decisions
        )

    def _instrument_decision(
        self, run: Run, it: Iteration, proposals: dict[str, str]
    ) -> PendingDecision:
        measured = "; ".join(f"{vid}: `{cmd}`" for vid, cmd in proposals.items())
        question = (
            "These verifications report the same thing with and without the change, so they "
            "cannot show whether the requirements they carry hold: "
            + "; ".join(it.instrument_faults)
            + "."
        )
        if measured:
            question += (
                " The producer reported another command, and it was run on both versions: "
                + measured
                + " reports success with the change and something else without it."
            )
        question += (
            " Replace the command, go back to the specification, keep them as no proof either "
            "way, or abort?"
        )
        return PendingDecision(
            kind=DecisionKind.instrument_fault,
            question=question,
            options=[
                DecisionOption(
                    key="recalibrate",
                    label="Use another command (note: the command, or `V2: the command`)",
                    needs_note=True,
                    consequence="The command replaces the one in the specification, and the "
                    "change already produced is verified again with it, on both versions. "
                    "Nothing is implemented again and no agent is called.",
                ),
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
            context={"faults": it.instrument_faults, "measured": proposals},
        )

    def _calibrate(
        self, run: Run, it: Iteration, evidence: list[Evidence]
    ) -> tuple[list[Evidence], dict[str, str]]:
        """Run every demonstrating verification again on the base version and read the pair.

        The tree it runs against is the base version carrying the change's own test files: the
        instrument is there, what it measures is not. A command whose outcome is the same on both
        trees is not looking at the change — it either never reports success, or reports it
        whatever the tree holds — and no edit the producer could make would alter that.

        Pass or fail, every verification that a behaviour requirement leans on is measured this
        way. Checking only the failing ones catches the loud half and credits the silent one.
        A command the second run did not agree with is left out: what it reported on the change
        is one of two readings, and comparing it with a third run on another tree would name an
        instrument at fault on the strength of a coin that came up heads.
        """
        assert run.profile is not None and run.profile.base_commit and it.version is not None
        assert it.version.head_commit
        base = run.profile.base_commit
        head = it.version.head_commit
        leaned_on = {
            vid
            for r in run.spec.requirements
            if r.kind is RequirementKind.behaviour
            for vid in r.verification_ids
        }
        subjects = [
            (v, e)
            for e in evidence
            if e.kind is EvidenceKind.command_result and e.verification_id
            for v in [run.spec.verification(e.verification_id)]
            if v is not None
            and v.command
            and v.sufficiency in ADMISSIBLE
            and v.stable is not False
            and (v.to_create or v.id in leaned_on)
        ]
        if not subjects:
            return [], {}
        produced: list[Evidence] = []
        proposals: dict[str, str] = {}
        control_wt = self._worktree(run).parent / f"{run.id}.control"
        root = Path(run.project_root)
        git.remove_worktree(root, control_wt)
        shutil.rmtree(control_wt, ignore_errors=True)
        try:
            git.add_worktree_detached(root, control_wt, base)
        except git.GitError as exc:
            self._warn(run, f"cannot check the verifications against the base version: {exc}")
            return [], {}

        def sink(eid: str, text: str) -> str:
            return self.store.write_text(
                run.id, str(self.store.evidence_dir(run.id, eid) / "output.txt"), text
            )

        try:
            wanted = instrument_files(it.version.files_changed)
            applied = git.checkout_paths(control_wt, head, wanted) if wanted else []
            if wanted:
                self.emit(
                    run,
                    "control.prepared",
                    f"base version {base[:12]} with {len(applied)} test file(s) of the change "
                    "applied, so the commands have something to run",
                    {"files": applied},
                )
            for v, ev in subjects:
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
                    applied=applied,
                )
                if control.interrupted:
                    raise KeyboardInterrupt
                produced.append(control_ev)
                subject_output = self.store.read_text(run.id, ev.output_ref or "")
                discriminates, sufficiency, rationale = classify_instrument(
                    v,
                    ev.passed,
                    ev.exit_code,
                    subject_output,
                    ev.summary == "timed out",
                    control,
                    base,
                    applied,
                )
                v.discriminates = discriminates
                v.sufficiency = sufficiency
                if rationale:
                    v.rationale = rationale
                if discriminates:
                    self.emit(
                        run,
                        "control.ended",
                        f"{v.id}: reports something else without the change, so what it reports "
                        "with it is about the change"
                        + (
                            f"; unconfirmed: {rationale}"
                            if sufficiency is Sufficiency.unconfirmed
                            else ""
                        ),
                        {
                            "verification": v.id,
                            "faulty": False,
                            "unconfirmed": sufficiency is Sufficiency.unconfirmed,
                        },
                    )
                    continue
                if sufficiency is Sufficiency.sufficient:
                    self._warn(run, f"{v.id} could not be calibrated: {rationale}")
                    continue
                it.instrument_faults.append(f"{v.id}: {v.rationale}")
                self.emit(
                    run,
                    "instrument.fault",
                    f"{v.id} does not observe the change: {v.rationale}",
                    {"verification": v.id, "cause": sufficiency.value},
                )
                proposal = self._measure_proposal(run, it, v, control_wt, applied, sink)
                if proposal is not None:
                    proposals[v.id] = proposal[0]
                    produced.extend(proposal[1])
        finally:
            git.remove_worktree(root, control_wt)
            shutil.rmtree(control_wt, ignore_errors=True)
        return produced, proposals

    def _measure_proposal(
        self,
        run: Run,
        it: Iteration,
        v: Verification,
        control_wt: Path,
        applied: list[str],
        sink: Callable[[str, str], str],
    ) -> tuple[str, list[Evidence]] | None:
        """Take the producer's word for a command, then check it the same way as the spec's.

        The producer runs the commands by hand and is the first to see one of them refuse to work;
        what it reports is a claim, and the only thing that turns a claim into a fact here is the
        harness running it itself, on both trees, and finding that the two disagree.
        """
        assert it.version is not None and it.version.head_commit and run.profile is not None
        assert run.profile.base_commit
        head = (v.command or "").split()[:1]
        candidate = next(
            (
                c.command
                for c in it.commands_reported
                if c.exit_code == 0 and c.command != v.command and c.command.split()[:1] == head
            ),
            None,
        )
        if candidate is None:
            return None
        probe = v.model_copy(update={"command": candidate})
        wt = self._worktree(run)
        on_change, change_res = run_control(
            probe,
            wt,
            it.version.head_commit,
            self.sandbox,
            it.n,
            run.budget.command_timeout_s,
            sink,
            self._stop_check(run),
            network=run.config.sandbox.allow_network,
            label=f"command reported by the producer, run on the change for {v.id}",
        )
        without, without_res = run_control(
            probe,
            control_wt,
            run.profile.base_commit,
            self.sandbox,
            it.n,
            run.budget.command_timeout_s,
            sink,
            self._stop_check(run),
            network=run.config.sandbox.allow_network,
            applied=applied,
            label=f"the same command run without the change for {v.id}",
        )
        if change_res.interrupted or without_res.interrupted:
            raise KeyboardInterrupt
        passes = change_res.exit_code == v.expected_exit_code
        differs = measures_the_change(
            change_res.exit_code, change_res.output, without_res, change_res.timed_out
        )
        verdict = (
            "reports success with the change and something else without it"
            if passes and differs
            else f"exits {change_res.exit_code} with the change and "
            f"{without_res.exit_code} without it"
        )
        self.emit(
            run,
            "proposal.measured",
            f"{v.id}: `{candidate}` {verdict}",
            {"verification": v.id, "command": candidate, "usable": passes and differs},
        )
        if not (passes and differs):
            return None
        return candidate, [on_change, without]

    def _review(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        it = run.current_iteration
        assert it is not None and it.version is not None and it.version.head_commit
        wt = self._worktree(run)
        self._set_status(run, RunStatus.reviewing)
        diff_text = git.diff(wt, it.version.base_commit, it.version.head_commit)
        evidence = [e for e in (run.evidence_by_id(x) for x in it.evidence_ids) if e]
        suite_reading = self._suite_reading(run, it, evidence)
        for reviewer in run.config.roles.reviewers_for(run.spec):
            if any(
                r.perspective == reviewer.perspective
                and r.intervention_id in it.review_ids
                and not r.discarded
                for r in run.reviews
            ):
                continue  # already done (resume)
            pack = ContextPack(role=f"reviewer:{reviewer.perspective}")
            pack.add_fact("Intent (as given by the requester)", run.intent.text)
            if run.clarification.says_anything:
                pack.add_fact("Requester's decisions", render_decisions_taken(run.clarification))
            pack.add_fact("Approved specification", render_spec(run.spec))
            pack.add_fact("Version under review", render_version(it.version))
            pack.add_fact(
                "Evidence collected by the harness on this exact version", render_evidence(evidence)
            )
            assert run.profile is not None
            pack.add_fact("Project profile", render_profile(run.profile, str(wt)))
            pack.add_fact("Behaviour scenarios", render_behaviour_test_form(run.profile))
            if run.test_design is not None and run.test_design.files:
                pack.add_fact(
                    "Tests written by the test designer", render_test_design(run.test_design)
                )
            if suite_reading.changes or suite_reading.counts:
                pack.add_fact(
                    "Existing tests modified by the change",
                    render_suite_reading(suite_reading),
                )
            reach = [e for e in evidence if e.kind is EvidenceKind.coverage_check]
            if reach:
                pack.add_fact(
                    "Lines of the change no verification executed", render_reach_reading(reach)
                )
            unsteady = [
                e for e in evidence if e.kind is EvidenceKind.stability_check and e.passed is False
            ]
            if unsteady:
                pack.add_fact(
                    "Verifications that did not report the same thing twice",
                    render_stability_reading(unsteady),
                )
            mutation = [e for e in evidence if e.kind is EvidenceKind.mutation_check]
            if mutation:
                pack.add_fact(
                    "Wrong versions of the change, and what the verifications reported",
                    render_mutation_reading(mutation),
                )
            refuted = [
                x
                for x in run.profile.lessons
                if x.kind is LessonKind.false_positive and x.perspective == reviewer.perspective
            ]
            if refuted:
                pack.add_fact(
                    "Claims of this perspective the requester found do not hold here",
                    render_refuted(refuted),
                )
            pack.add_untrusted("git diff base..head", truncate_diff(diff_text) or "(empty diff)")
            for e in evidence:
                # What a command printed where it failed on the change. A mutation check also
                # keeps an output, of a command that passed on a tree that is not the one
                # under review; handing that over as the output of a failure would misread it.
                if e.kind is EvidenceKind.command_result and e.output_ref and e.passed is False:
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
                _finding_from_agent(f, run.spec)
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
            )
            + (
                "; not credited: " + "; ".join(assessment.uncredited)
                if assessment.uncredited
                else ""
            ),
            [e.id for e in evidence],
        )
        it.decision_id = decision.id
        self.emit(run, "iteration.assessed", f"iteration {it.n}: {assessment.summary}")
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

    def merge_delivery(
        self, run_id: str, how: str = "fast-forward", rerun_verifications: bool = False
    ) -> Run:
        """Bring the delivered branch into the branch checked out in the project, then look.

        The one command that writes to the tree people work in. Everything else 495 does
        happens in a worktree of its own, which is why the run can be walked without asking
        anyone: nothing it does is visible in the repository until this. So the preconditions
        are refusals rather than repairs — an unclean tree is not stashed, a conflict is not
        resolved, a branch already merged is not merged twice — and each of them leaves the
        repository exactly as it was found.

        Merging and checking are one command because they are one act: the merge is what the
        check exists to inspect, and a merge left unchecked would be the only integration 495
        ever performed and never verified.
        """
        self.store.claim(run_id, self.label)
        try:
            self._merge_delivery(run_id, how)
            return self._check_integration(run_id, "HEAD", rerun_verifications)
        finally:
            self.store.release(run_id)

    def _merge_delivery(self, run_id: str, how: str) -> Run:
        run = self.store.load(run_id)
        it = run.current_iteration
        if it is None or it.version is None or not it.version.head_commit:
            raise EngineError("the run has no evaluated version")
        branch = run.result.branch or it.version.branch
        if not branch:
            raise EngineError("the run delivered no branch to merge")
        if how not in git.INTEGRATIONS:
            raise EngineError(
                f"unknown way to integrate: {how!r}; one of {', '.join(git.INTEGRATIONS)}"
            )
        root = Path(run.project_root)
        into = git.current_branch(root) or "HEAD"
        if git.has_uncommitted_changes(root):
            raise EngineError(
                f"{root} has uncommitted changes; commit or stash them before integrating "
                f"into {into}"
            )
        if git.is_ancestor(root, it.version.head_commit, "HEAD"):
            raise EngineError(f"{into} already contains {it.version.head_commit[:12]}")
        if how == "fast-forward" and not git.can_fast_forward(root, branch):
            raise EngineError(
                f"{into} carries commits of its own since the run branched, so nothing can be "
                "fast-forwarded onto it; integrate it as rebase, squash or merge"
            )
        before = git.head_commit(root)
        merged = git.integrate_branch(
            root,
            branch,
            how,
            self._integration_message(run, branch, how),
            it.version.base_commit,
        )
        run.result.integrated_as = how
        self.emit(
            run,
            "integration.merged",
            f"{branch} integrated into {into} as {how}: {before[:12]} -> {merged[:12]}",
            {"branch": branch, "into": into, "how": how, "before": before, "after": merged},
        )
        self.store.save(run)
        return run

    @staticmethod
    def _integration_message(run: Run, branch: str, how: str) -> str:
        """The commit an integration writes, for the two shapes that write one.

        What the change does, and then where the evidence for it is. That second line is the
        only thing tying a squashed commit back to the run that produced and verified it: the
        branch survives locally, but nothing in the history would point at it.
        """
        it = run.current_iteration
        head = (it.version.head_commit if it and it.version else "") or ""
        text = run.intent.text.strip()
        subject = text.splitlines()[0] if text else branch
        lead = f"Merge branch '{branch}'\n\n{subject}" if how == "merge" else subject
        return f"{lead}\n\nVerified as {head[:12]} by 495 {run.id}."

    def check_integration(
        self, run_id: str, target_ref: str = "HEAD", rerun_verifications: bool = False
    ) -> Run:
        self.store.claim(run_id, self.label)
        try:
            return self._check_integration(run_id, target_ref, rerun_verifications)
        finally:
            self.store.release(run_id)

    def _check_integration(self, run_id: str, target_ref: str, rerun_verifications: bool) -> Run:
        run = self.store.load(run_id)
        self._ensure_sandbox(run)
        it = run.current_iteration
        if it is None or it.version is None or not it.version.head_commit:
            raise EngineError("the run has no evaluated version")
        root = Path(run.project_root)
        head = it.version.head_commit
        target = git.rev_parse(root, target_ref)
        # "HEAD" is where you happen to be standing, not a name anyone can act on, and the one
        # question this stop answers is which branch carries the change. So the ref is recorded
        # under the name it has there: a check that says "HEAD" reads the same whichever branch
        # it was run on, and the one fact worth keeping is the one it drops. A detached head has
        # no name to take and keeps the one it was given.
        if target_ref == "HEAD":
            target_ref = git.current_branch(root) or target_ref
        contains = git.is_ancestor(root, head, target)
        identical = True
        diffs: list[str] = []
        for f in it.version.files_changed:
            expected = git.blob_hash(root, head, f)
            actual = git.blob_hash(root, target, f)
            if expected != actual:
                identical = False
                diffs.append(
                    f"{f}: evaluated {expected or 'deleted'} vs integrated {actual or 'missing'}"
                )
        # A ref still sitting on the commit the run branched from has not been merged into, so
        # nothing was integrated and nothing can differ. A blob pair per changed file would
        # answer a question nobody asked, and reads as a broken integration where the truth is
        # that there is not one yet.
        untouched = not contains and not identical and target == it.version.base_commit
        details: list[str] = (
            [
                f"{target_ref} is still {target[:12]}, the commit the run started from; "
                "nothing of this run has been merged into it"
            ]
            if untouched
            else list(diffs)
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
        from harness495.core.models import IntegrationCheck

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


def _clarify_frontier(
    data: dict[str, Any], clarification: Clarification
) -> tuple[list[ClarifyQuestion], list[str]]:
    """The questions of one round that are worth putting to the requester, and the drops.

    Three things are taken out, each for the same reason — a question that cannot change what
    gets specified is a stop that buys nothing: one already answered, one offering fewer than
    two options, and one whose option says nothing about its consequence on the specification.
    Every drop is stated, so a round that asked nothing can be told from one whose questions
    were all refused.
    """
    kept: list[ClarifyQuestion] = []
    dropped: list[str] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for i, item in enumerate(data.get("questions") or []):
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or f"Q{i + 1}").strip()[:50] or f"Q{i + 1}"
        title = str(item.get("title") or "").strip()[:500]
        if not title:
            dropped.append(f"{qid} was dropped: it states no question")
            continue
        label = f"{qid} '{title}'"
        options: list[ClarifyOption] = []
        for raw in item.get("options") or []:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or "").strip().lower()[:30]
            text = str(raw.get("label") or "").strip()[:300]
            if not key or not text or key == OTHER_OPTION or key in {o.key for o in options}:
                continue
            options.append(
                ClarifyOption(
                    key=key,
                    label=text,
                    consequence=str(raw.get("consequence") or "").strip()[:500],
                )
            )
        question = ClarifyQuestion(
            id=qid,
            title=title,
            body=str(item.get("body") or "").strip()[:4000],
            options=options[:8],
            recommended=str(item.get("recommended") or "").strip().lower()[:30],
            checked=[str(c).strip()[:300] for c in (item.get("checked") or []) if str(c).strip()][
                :20
            ],
        )
        settled = clarification.answered(question)
        if settled is not None:
            dropped.append(
                f"{label} was not asked again: it is already answered — "
                f"{settled.label or settled.option}"
            )
            continue
        if qid in seen_ids or normalise_question(title) in seen_titles:
            dropped.append(f"{label} was dropped: the round asks it twice")
            continue
        if len(question.options) < 2:
            dropped.append(f"{label} was dropped: it offers fewer than two options")
            continue
        silent = [o.key for o in question.options if not o.consequence]
        if silent:
            dropped.append(
                f"{label} was dropped: option(s) {', '.join(silent)} state no consequence on "
                "the specification"
            )
            continue
        if question.recommended not in {o.key for o in question.options}:
            dropped.append(f"{label} was dropped: its recommended answer names no option it offers")
            continue
        question.options.append(
            ClarifyOption(
                key=OTHER_OPTION,
                label="Something else — say what",
                consequence="Your words go to the specifier in place of the options above.",
            )
        )
        kept.append(question)
        seen_ids.add(qid)
        seen_titles.add(normalise_question(title))
    return kept, dropped


def _recommended_answer(question: ClarifyQuestion, made_by: DecisionMaker) -> ClarifyAnswer:
    option = question.option(question.recommended)
    assert option is not None  # a question whose recommendation names no option was dropped
    return ClarifyAnswer(
        question_id=question.id,
        question=question.title,
        option=option.key,
        label=option.label,
        recommended=True,
        taken_by=made_by,
    )


def _clarify_question_text(questions: list[ClarifyQuestion]) -> str:
    n = len(questions)
    return (
        f"{n} decision{'s' if n > 1 else ''} to take before the specification is written: "
        + "; ".join(q.title for q in questions)
    )


def _clarify_decision(
    questions: list[ClarifyQuestion], round_n: int, max_rounds: int
) -> PendingDecision:
    """One stop for the whole round: the frontier is one reading, so it is one question."""
    left = max_rounds - round_n
    more = (
        f" Answering may open further decisions; at most {left} more round(s) will be put to you."
        if left > 0
        else " This is the last round you will be asked; anything it opens is recorded unanswered."
    )
    return PendingDecision(
        kind=DecisionKind.clarify,
        question=_clarify_question_text(questions) + "." + more,
        options=[
            DecisionOption(
                key="recommended",
                label="Take the recommended answer for every question",
                consequence="Each recommendation is recorded as yours. The clarification goes "
                "on to the next round; nothing is specified or implemented yet.",
            ),
            DecisionOption(
                key="answer",
                label="Answer them one by one",
                consequence="You choose an option per question, or say something else in your "
                "own words. Every question of the round has to be answered.",
            ),
            DecisionOption(
                key="abort",
                label="Abort the run",
                consequence="The run stops for good. Nothing was specified or produced, so "
                "there is nothing to keep.",
            ),
        ],
        questions=questions,
        context={
            "round": round_n,
            "max_rounds": max_rounds,
            "questions": [q.model_dump(mode="json") for q in questions],
        },
    )


def _decisions_taken(clarification: Clarification) -> list[DecisionTaken]:
    """The clarification as the specification carries it: what was asked, chosen and by whom."""
    taken: list[DecisionTaken] = []
    for round_ in clarification.rounds:
        for answer in round_.answers:
            question = round_.question(answer.question_id)
            taken.append(
                DecisionTaken(
                    question=answer.question,
                    options=[o.label for o in question.options] if question else [],
                    choice=answer.label or answer.option,
                    note=answer.note,
                    taken_by=answer.taken_by,
                )
            )
    return taken


def _spec_from_agent(data: dict[str, Any]) -> Spec:
    verifications: list[Verification] = []
    for i, v in enumerate(data.get("verifications", []), start=1):
        if not isinstance(v, dict):
            continue
        kind = str(v.get("kind", "command"))
        if kind not in VerificationKind.__members__:
            kind = "command"
        role = str(v.get("role") or "")
        verifications.append(
            Verification(
                id=str(v.get("id") or f"V{i}"),
                kind=VerificationKind(kind),
                description=str(v.get("description", "")).strip() or "(no description)",
                command=(str(v["command"]).strip() or None) if v.get("command") else None,
                to_create=bool(v.get("to_create", False)),
                role=CatalogueRole(role) if role in CatalogueRole.__members__ else None,
                scenario=_scenario_from_agent(v.get("scenario")),
            )
        )
    requirements: list[Requirement] = []
    for i, r in enumerate(data.get("requirements", []), start=1):
        if not isinstance(r, dict):
            continue
        kind = str(r.get("kind", RequirementKind.behaviour.value))
        requirements.append(
            Requirement(
                id=str(r.get("id") or f"R{i}"),
                statement=str(r.get("statement", "")).strip() or "(empty)",
                # Anything unrecognised is read as new behaviour: that is the reading under which
                # a command which already passes is not accepted as proof.
                kind=RequirementKind(kind)
                if kind in RequirementKind.__members__
                else RequirementKind.behaviour,
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


def _scenario_from_agent(data: Any) -> BehaviourScenario | None:
    """Read a scenario's steps; blank steps are dropped, and no step at all is no scenario."""
    if not isinstance(data, dict):
        return None
    steps = {
        key: [str(x).strip() for x in data.get(key) or [] if str(x).strip()]
        if isinstance(data.get(key), list)
        else []
        for key in ("given", "when", "then")
    }
    if not any(steps.values()):
        return None
    return BehaviourScenario(**steps)


def _finding_from_agent(f: dict[str, Any], spec: Spec) -> Finding:
    """Read one finding, and file it against whatever it is actually about.

    A reviewer with something to say about how a requirement is measured has a requirement field
    and no other, and writes the verification's id in it. Read literally, that finding is about a
    requirement that does not exist and is dropped; read for what it says, it is about the
    verification it names.
    """
    requirement_id = str(f.get("requirement_id") or "") or None
    verification_id = str(f.get("verification_id") or "") or None
    names_a_verification = (
        requirement_id is not None
        and spec.verification(requirement_id) is not None
        and not any(r.id == requirement_id for r in spec.requirements)
    )
    if names_a_verification:
        requirement_id, verification_id = None, verification_id or requirement_id
    return Finding(
        severity=Severity(str(f.get("severity", "info"))),
        title=str(f.get("title", ""))[:200],
        detail=str(f.get("detail", "")),
        file=f.get("file") or None,
        line=int(f["line"]) if isinstance(f.get("line"), int) else None,
        requirement_id=requirement_id,
        verification_id=verification_id,
        evidence=str(f.get("evidence", "")),
    )


def _normalise_spec(spec: Spec) -> None:
    known = {v.id for v in spec.verifications}
    for r in spec.requirements:
        r.verification_ids = [v for v in r.verification_ids if v in known]


def _non_regression_verifications(spec: Spec) -> list[str]:
    """The verifications a non-regression requirement leans on, in specification order."""
    return list(
        dict.fromkeys(
            vid
            for r in spec.requirements
            if r.kind is RequirementKind.non_regression
            for vid in r.verification_ids
        )
    )


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

    base = configured or os.environ.get("HARNESS495_WORKTREES_DIR")
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
