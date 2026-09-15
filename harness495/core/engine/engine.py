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
from harness495.core.engine import checks
from harness495.core.engine.errors import EngineError
from harness495.core.engine.running import VersionMismatch
from harness495.core.engine.services import RunServices
from harness495.core.models import (
    ADMISSIBLE,
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
    TestDesign,
    Verdict,
    Verification,
    VerificationKind,
    Version,
    new_id,
    normalise_question,
    utcnow,
)
from harness495.core.profile import detect_profile, read_doc_excerpts
from harness495.core.reading.decide import Assessment, assess
from harness495.core.reading.scope import effective_allowed
from harness495.core.reading.verification import assess_sufficiency, looks_like_a_test
from harness495.core.report import render_markdown
from harness495.core.schemas import (
    CLARIFY_SCHEMA,
    PRODUCER_SUMMARY_SCHEMA,
    REVIEW_SCHEMA,
    SPEC_SCHEMA,
    TEST_DESIGNER_SUMMARY_SCHEMA,
)
from harness495.core.store import RunStore
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
        self._sandbox = sandbox
        self._sandbox_warnings: list[str] = []
        self.on_event = on_event
        self.decision_handler = decision_handler
        self.agent_factory = agent_factory or build_agent
        #: How this engine names itself to whoever finds the run already claimed.
        self.label = label
        self._stop = threading.Event()
        self._services = RunServices(
            store=store,
            sandbox=lambda: self.sandbox,
            emit=self.emit,
            warn=self._warn,
            worktree=self._worktree,
            stop_check=self._stop_check,
            set_status=self._set_status,
        )

    @property
    def store(self) -> RunStore:
        """The run store, which the services hold and the surfaces read."""
        return self._services.store

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
        self._services.store.save(run)
        git.ensure_excluded(root, ".495/")
        self._services.emit(
            run, "run.created", f"run {run.id} created ({mode.value})", {"intent": intent}
        )
        return run

    def run(self, run_id: str) -> Run:
        """Advance until the run blocks (decision, pause, terminal state).

        The run is claimed for the duration: a second engine — another terminal, the run
        surface, a CI job — is refused rather than allowed to interleave its writes with
        these ones.
        """
        run = self._services.store.load(run_id)
        self._services.store.claim(run_id, self.label)
        try:
            self._services.store.clear_stop(run_id)
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
            self._services.store.release(run_id)
        return run

    def resume(self, run_id: str) -> Run:
        run = self._services.store.load(run_id)
        self._services.store.clear_stop(run_id)
        self._stop.clear()
        if run.status in (RunStatus.paused, RunStatus.failed):
            target = run.resume_status or RunStatus.created
            self._services.emit(run, "run.resumed", f"resuming at {target.value}")
            run.status = target
            run.resume_status = None
            run.stop_reason = None
            self._services.store.save(run)
        return run

    def request_stop(self, run_id: str, reason: str = "stop requested") -> None:
        self._services.store.request_stop(run_id, reason)
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
        run = self._services.store.load(run_id)
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
        self._services.store.save(run)
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
                self._services.warn(run, w)

    def emit(
        self, run: Run, type_: str, message: str = "", data: dict[str, Any] | None = None
    ) -> None:
        ev = Event(run_id=run.id, type=type_, message=message, data=data or {})
        self._services.store.append_event(ev)
        if self.on_event is not None:
            self.on_event(ev)

    def _warn(self, run: Run, message: str) -> None:
        if message not in run.warnings:
            run.warnings.append(message)
        self._services.emit(run, "warning", message)

    def _stop_check(self, run: Run) -> Callable[[], bool]:
        def check() -> bool:
            return self._stop.is_set() or self._services.store.stop_requested(run.id) is not None

        return check

    def _set_status(self, run: Run, status: RunStatus) -> None:
        old = run.status
        run.status = status
        self._services.store.save(run)
        self._services.emit(
            run, "status", f"{old.value} -> {status.value}", {"from": old.value, "to": status.value}
        )

    def _fail(self, run: Run, reason: str, retry_at: RunStatus) -> Run:
        run.stop_reason = reason
        run.resume_status = retry_at
        self._services.set_status(run, RunStatus.failed)
        self._services.emit(run, "run.failed", reason)
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
        self._services.set_status(run, RunStatus.paused)
        self._services.emit(run, "run.paused", reason)
        return run

    def _abort(self, run: Run, reason: str) -> Run:
        run.stop_reason = reason
        run.pending_decision = None
        self._services.set_status(run, RunStatus.aborted)
        self._services.emit(run, "run.aborted", reason)
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
        self._services.set_status(run, RunStatus.awaiting_decision)
        self._services.emit(
            run, "decision.requested", pending.question, {"kind": pending.kind.value}
        )
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
        self._services.emit(
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
                self._services.set_status(run, RunStatus.clarifying)
            case DecisionKind.approve_spec:
                if choice in ("approve", "approve_with_gaps"):
                    run.spec.approved = True
                    run.spec.approved_by = made_by
                    self._services.set_status(run, RunStatus.ready)
                elif choice == "revise":
                    run.spec.approved = False
                    run.spec.assumptions.append(f"revision requested: {note}")
                    run.intent.text = run.intent.text  # unchanged; the note travels with the spec
                    self._services.set_status(run, RunStatus.clarified)
            case DecisionKind.readiness:
                if choice == "proceed":
                    self._services.set_status(run, RunStatus.profiled)
                elif choice == "allow_network":
                    run.config.sandbox.allow_network = True
                    self._services.warn(
                        run,
                        "verification commands now run with network access; "
                        "agent isolation is unchanged",
                    )
                    self._services.set_status(run, RunStatus.created)
                elif choice == "drop":
                    assert run.profile is not None
                    bad = {r.command_name for r in run.profile.readiness if not r.executable}
                    run.profile.commands = [c for c in run.profile.commands if c.name not in bad]
                    run.profile.readiness = [r for r in run.profile.readiness if r.executable]
                    self._services.set_status(run, RunStatus.profiled)
                elif choice == "retry":
                    self._services.set_status(run, RunStatus.created)
            case DecisionKind.no_progress:
                if choice == "respecify":
                    run.spec.approved = False
                    run.spec.assumptions.append(f"revision requested: {note}")
                    self._services.set_status(run, RunStatus.clarified)
                elif choice == "review_anyway":
                    self._services.set_status(run, RunStatus.produced)
                elif choice == "stop":
                    run.result.outcome = Verdict.reject
                    run.result.summary = "rejected: the corrections produced no change"
                    self._services.set_status(run, RunStatus.rejected)
            case DecisionKind.instrument_fault:
                if choice == "recalibrate":
                    checks.recalibrate(self._services, run, note)
                    self._services.set_status(run, RunStatus.produced)
                elif choice == "respecify":
                    run.spec.approved = False
                    run.spec.assumptions.append(f"revision requested: {note}")
                    self._services.set_status(run, RunStatus.clarified)
                elif choice == "ignore":
                    # The verification keeps running and keeps being recorded, but goes on
                    # counting as proof of nothing, so the requirements it carries stay
                    # undetermined rather than becoming violations the producer would be sent to
                    # fix. The answer holds for the rest of the run: the fault is in the
                    # specification and has not moved.
                    self._services.set_status(run, run.resume_status or RunStatus.reviewed)
            case DecisionKind.iteration_limit:
                if choice == "continue":
                    run.budget.max_iterations += 1
                    self._services.set_status(run, RunStatus.ready)
                elif choice == "stop":
                    run.result.outcome = Verdict.reject
                    run.result.summary = "rejected after reaching the iteration limit"
                    self._services.set_status(run, RunStatus.rejected)
            case DecisionKind.undetermined:
                if choice == "accept_with_risk":
                    run.result.summary = f"accepted by human despite undetermined evidence: {note}"
                    self._services.set_status(run, RunStatus.accepted)
                elif choice == "rerun":
                    self._services.set_status(run, RunStatus.produced)
                elif choice == "correct":
                    it = run.current_iteration
                    if it is not None:
                        it.correction_requests.append(f"[human] {note}")
                    if run.mode is RunMode.evaluate:
                        run.result.outcome = Verdict.reject
                        run.result.summary = f"rejected by human: {note}"
                        self._services.set_status(run, RunStatus.rejected)
                    else:
                        self._services.set_status(run, RunStatus.ready)
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
                    self._services.set_status(run, run.resume_status or RunStatus.ready)
            case DecisionKind.scope:
                if choice == "allow":
                    it = run.current_iteration
                    if it is not None:
                        it.correction_requests = [
                            c for c in it.correction_requests if not c.startswith("[scope]")
                        ]
                    self._services.set_status(run, RunStatus.produced)
            case DecisionKind.acceptance:
                # The verdict the harness records for itself in _decide, from the evidence it
                # measured. It is never raised as a question, so no answer to it arrives here;
                # the case exists so that the kind is covered rather than overlooked.
                pass
            case _:
                assert_never(kind)
        run.resume_status = None
        self._services.store.save(run)
        return run

    # ------------------------------------------------------------------ interventions

    def _agent_for(self, run: Run, name: str) -> Agent:
        spec = run.config.agent(name)
        return self.agent_factory(spec, self._services.sandbox)

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
        cwd = cwd or self._services.worktree(run)
        project_before = project_snapshot(Path(run.project_root))
        iid = new_id("int")
        idir = self._services.store.intervention_dir(run.id, iid)
        prompt_text = pack.render()
        prompt_ref = self._services.store.write_text(run.id, str(idir / "prompt.md"), prompt_text)
        self._services.store.write_json(run.id, str(idir / "context.json"), pack.to_json())
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
        self._services.store.save(run)
        self._services.emit(
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
            stop_check=self._services.stop_check(run),
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
                self._services.store.save(run)
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
        intervention.transcript_ref = self._services.store.write_text(
            run.id, str(idir / "transcript.txt"), result.transcript
        )
        if result.structured is not None:
            intervention.output_ref = self._services.store.write_json(
                run.id, str(idir / "output.json"), result.structured
            )
        else:
            intervention.output_ref = self._services.store.write_text(
                run.id, str(idir / "output.md"), result.text
            )
        self._services.store.write_json(
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
            self._services.warn(run, escape.summary)
        for w in budget_mod.record(run, intervention):
            self._services.warn(run, w)
        self._services.store.save(run)
        self._services.emit(
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
        profile.declined_roles = proposals_mod.declined_roles(self._services.store.load_proposals())
        profile.lessons = self._services.store.load_lessons().in_force
        run.profile = profile
        self._services.emit(
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
            self._services.emit(
                run, "worktree.created", f"{wt} on branch 495/{run.id} at {base[:12]}"
            )
        # Readiness: run every command once on the base version.
        profile.readiness = []
        for cmd in profile.commands:
            req = ExecRequest(
                command=cmd.command,
                cwd=wt,
                timeout_s=cmd.timeout_s or run.budget.command_timeout_s,
                writable=True,
                network=run.config.sandbox.allow_network,
                stop_check=self._services.stop_check(run),
            )
            res = self._services.sandbox.run(req)
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
                sandbox=self._services.sandbox.describe(req),
            )
            baseline_ev.output_ref = self._services.store.write_text(
                run.id,
                str(self._services.store.evidence_dir(run.id, baseline_ev.id) / "output.txt"),
                res.output,
            )
            baseline_ev.output_sha256 = git.sha256_text(res.output)
            run.evidence.append(baseline_ev)
            self._services.emit(
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
            self._services.warn(
                run, f"baseline '{r.command_name}' exits {r.exit_code} on the base version"
            )
        self._services.set_status(run, RunStatus.profiled)
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
            self._services.set_status(run, RunStatus.clarified)
            return run
        if run.budget.max_clarify_rounds <= 0:
            clar.complete = True
            self._services.set_status(run, RunStatus.clarified)
            return run
        self._ensure_sandbox(run)
        assert run.profile is not None
        wt = self._services.worktree(run)
        self._services.set_status(run, RunStatus.clarifying)
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
            self._services.warn(
                run,
                "the clarifier did not complete "
                f"({(result.error or result.status.value) if result else 'no result'}); "
                "no decision was put to you, and the specifier decides what the intent leaves open",
            )
            clar.complete = True
            self._services.set_status(run, RunStatus.clarified)
            return run
        data = result.structured or _parse_json_text(result.text) or {}
        questions, dropped = _clarify_frontier(data, clar)
        round_ = ClarifyRound(n=n, intervention_id=intervention.id, dropped=dropped)
        clar.rounds.append(round_)
        for reason in dropped:
            self._services.warn(run, f"clarification round {n}: {reason}")
        if not questions:
            clar.complete = True
            self._services.emit(
                run,
                "clarify.settled",
                f"round {n} returned no question: nothing is left to decide before the "
                f"specification; {len(clar.answers)} decision(s) taken",
            )
            self._services.set_status(run, RunStatus.clarified)
            return run
        if clar.rounds_answered >= run.budget.max_clarify_rounds:
            clar.open_questions = questions
            clar.stopped_at_cap = True
            clar.complete = True
            round_.dropped.append(
                f"{len(questions)} question(s) recorded as unanswered: the cap of "
                f"{run.budget.max_clarify_rounds} answered round(s) was reached"
            )
            self._services.warn(
                run,
                f"the clarification stopped at {run.budget.max_clarify_rounds} answered round(s) "
                f"with {len(questions)} question(s) still open: "
                + "; ".join(q.title for q in questions)
                + "; the specifier decides them and records each as an assumption",
            )
            self._services.set_status(run, RunStatus.clarified)
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
            self._services.set_status(run, RunStatus.clarifying)
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
            self._services.emit(
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
        self._services.emit(
            run, "worktree.created", f"{wt} evaluating {head[:12]} against base {base[:12]}"
        )
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
            self._services.emit(
                run,
                "spec.provided",
                f"{len(run.spec.requirements)} requirement(s) from user; {len(run.spec.gaps)} gap(s)",
            )
            self._services.set_status(run, RunStatus.specified)
            return run
        pack = ContextPack(role="specifier")
        pack.add_fact("Intent (as given by the requester)", run.intent.text)
        wt = self._services.worktree(run)
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
            spec = spec_from_agent(data)
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
        run.spec.artifact_ref = self._services.store.write_json(
            run.id,
            str(self._services.store.artifacts_dir(run.id) / "spec.json"),
            run.spec.model_dump(mode="json"),
        )
        spec_path = self._services.store.resolve(run.id, run.spec.artifact_ref)
        self._services.emit(
            run,
            "spec.proposed",
            f"{len(spec.requirements)} requirement(s), {len(spec.verifications)} verification(s), "
            f"{len(spec.gaps)} gap(s); written to {spec_path}",
            {"spec_ref": run.spec.artifact_ref},
        )
        self._services.set_status(run, RunStatus.specified)
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
        wt = self._services.worktree(run)
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
                stop_check=self._services.stop_check(run),
            )
            res = self._services.sandbox.run(req)
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
            ev.output_ref = self._services.store.write_text(
                run.id,
                str(self._services.store.evidence_dir(run.id, ev.id) / "output.txt"),
                res.output,
            )
            ev.output_sha256 = git.sha256_text(res.output)
            ev.duration_s = res.duration_s
            ev.sandbox = self._services.sandbox.describe(req)
            produced.append(ev)
            self._services.emit(
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
            self._services.set_status(run, RunStatus.ready)
            return run
        spec_path = (
            str(self._services.store.resolve(run.id, run.spec.artifact_ref))
            if run.spec.artifact_ref
            else ""
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
        wt = self._services.worktree(run)
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
        wt = self._services.worktree(run)
        n = run.iteration_number + 1
        if run.mode is RunMode.evaluate:
            if run.iterations:
                run.result.outcome = Verdict.reject
                run.result.summary = "evaluation rejected; no production agent in evaluate mode"
                self._services.set_status(run, RunStatus.rejected)
                return run
            version = self._evaluation_version(run)
            version.patch_ref = self._save_patch(run, version)
            run.iterations.append(Iteration(n=n, version=version))
            self._services.emit(
                run, "iteration.started", f"iteration {n} (evaluation of {version.head_commit})"
            )
            self._services.set_status(run, RunStatus.produced)
            return run
        blocked = self._design_tests(run)
        if blocked is not None:
            return blocked
        previous = run.current_iteration
        corrections = list(previous.correction_requests) if previous else []
        iteration = Iteration(n=n)
        run.iterations.append(iteration)
        self._services.set_status(run, RunStatus.producing)
        self._services.emit(
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
                        trim_output(self._services.store.read_text(run.id, e.output_ref)),
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
            self._services.warn(
                run,
                f"producer ended with {result.status.value}: {result.error}; evaluating whatever was produced",
            )
        if isinstance(result.structured, dict):
            claims = result.structured.get("not_done") or []
            iteration.blocked_claims = [str(c).strip()[:500] for c in claims if str(c).strip()][:20]
            for claim in iteration.blocked_claims:
                self._services.emit(run, "producer.blocked", claim)
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
        self._services.emit(
            run,
            "version.frozen",
            f"iteration {n} committed as {head[:12]} ({len(version.files_changed)} file(s))",
            {"head": head, "patch_sha256": version.patch_sha256},
        )
        if head == base_for_diff:
            self._services.warn(run, f"iteration {n} produced no change")
        self._services.set_status(run, RunStatus.produced)
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
        wt = self._services.worktree(run)
        self._services.set_status(run, RunStatus.producing)
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
            self._services.warn(
                run,
                f"test designer ended with {result.status.value}: {result.error}; keeping "
                "whatever tests were written",
            )
        written = git.dirty_paths(wt)
        kept = [f for f in written if looks_like_a_test(f)]
        discarded = [f for f in written if f not in kept]
        if discarded:
            git.discard_paths(wt, discarded)
            self._services.warn(
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
            self._services.emit(run, "test_designer.blocked", claim)
        if kept:
            self._services.emit(
                run,
                "tests.designed",
                f"{len(kept)} test file(s) written by the test designer, committed as "
                f"{commit[:12]}; the producer may not modify them",
                {"files": kept, "commit": commit, "intervention": intervention.id},
            )
        else:
            self._services.warn(
                run,
                "the test designer wrote no test file; the producer creates the tests to create "
                "itself, and the test_quality reviewer reads them",
            )
        self._services.store.save(run)
        return None

    def _save_patch(self, run: Run, version: Version) -> str | None:
        wt = self._services.worktree(run)
        assert version.head_commit
        patch = git.diff(wt, version.base_commit, version.head_commit)
        version.patch_sha256 = git.sha256_text(patch)
        if not patch.strip():
            return None
        ref = self._services.store.write_text(
            run.id,
            str(
                self._services.store.artifacts_dir(run.id)
                / f"iteration-{run.iteration_number or 1}.patch"
            ),
            patch,
        )
        return ref

    def _verify(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        _evidence, pending = checks.verify(self._services, run)
        if pending is not None:
            return self._raise_decision(run, pending, RunStatus.verified)
        return run

    def _review(self, run: Run) -> Run:
        self._ensure_sandbox(run)
        it = run.current_iteration
        assert it is not None and it.version is not None and it.version.head_commit
        wt = self._services.worktree(run)
        self._services.set_status(run, RunStatus.reviewing)
        diff_text = git.diff(wt, it.version.base_commit, it.version.head_commit)
        evidence = [e for e in (run.evidence_by_id(x) for x in it.evidence_ids) if e]
        suite_reading = checks.suite_reading(self._services, run, it, evidence)
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
                        trim_output(self._services.store.read_text(run.id, e.output_ref)),
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
                self._services.warn(
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
            self._services.emit(
                run,
                "review",
                rv_ev.summary,
                {"perspective": reviewer.perspective, "verdict": verdict.verdict.value},
            )
            self._services.store.save(run)
        self._services.set_status(run, RunStatus.reviewed)
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
        self._services.emit(run, "iteration.assessed", f"iteration {it.n}: {assessment.summary}")
        if assessment.outcome is Verdict.accept:
            run.result.outcome = Verdict.accept
            run.result.summary = assessment.summary
            self._services.set_status(run, RunStatus.accepted)
        elif assessment.outcome is Verdict.reject:
            if run.mode is RunMode.evaluate:
                run.result.outcome = Verdict.reject
                run.result.summary = assessment.summary
                self._services.set_status(run, RunStatus.rejected)
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
                self._services.emit(
                    run,
                    "iteration.rejected",
                    f"iteration {it.n} rejected; {len(assessment.correction_requests)} correction(s) requested",
                )
                self._services.set_status(run, RunStatus.ready)
        else:
            run.result.outcome = Verdict.undetermined
            run.result.summary = assessment.summary
            self._services.set_status(run, RunStatus.undetermined)
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
        report = render_markdown(run, self._services.store)
        run.result.report_ref = self._services.store.write_text(
            run.id, str(self._services.store.artifacts_dir(run.id) / "report.md"), report
        )
        self._services.set_status(run, RunStatus.delivered)
        self._services.emit(
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
        self._services.store.claim(run_id, self.label)
        try:
            self._merge_delivery(run_id, how)
            return self._check_integration(run_id, "HEAD", rerun_verifications)
        finally:
            self._services.store.release(run_id)

    def _merge_delivery(self, run_id: str, how: str) -> Run:
        run = self._services.store.load(run_id)
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
        self._services.emit(
            run,
            "integration.merged",
            f"{branch} integrated into {into} as {how}: {before[:12]} -> {merged[:12]}",
            {"branch": branch, "into": into, "how": how, "before": before, "after": merged},
        )
        self._services.store.save(run)
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
        self._services.store.claim(run_id, self.label)
        try:
            return self._check_integration(run_id, target_ref, rerun_verifications)
        finally:
            self._services.store.release(run_id)

    def _check_integration(self, run_id: str, target_ref: str, rerun_verifications: bool) -> Run:
        run = self._services.store.load(run_id)
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
                    res = self._services.sandbox.run(req)
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
        self._services.emit(
            run,
            "integration.checked",
            f"{target_ref} ({target[:12]}): contains commit={contains}, files identical={identical}"
            + (f", verifications passed={passed}" if rerun_verifications else ""),
        )
        self._services.store.save(run)
        return run

    def cleanup_worktree(self, run_id: str) -> None:
        run = self._services.store.load(run_id)
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
    """The JSON object an agent's prose carries, or None if it carries none.

    Three kinds of candidate are built: the whole text, the body of every fenced block, and the
    span from the first ``{`` to the last ``}``. **The largest candidate that parses as an object
    wins**, a tie going to the last one built.

    Size decides, and not position, because the candidates do not come in the order the agent
    wrote them: the whole text is built first and the brace span last however the prose is laid
    out, so the rank of a candidate says nothing about which answer it holds. Size says
    something. An agent that shows a JSON block before its answer is showing the shape it is
    about to fill — an empty skeleton, one illustrative element — and fills it in a block that
    follows; the answer is the one carrying the content. Taking the first candidate that parsed
    read that illustration as the answer, and the block it discarded left nothing behind to read:
    the run went on with an empty specification, an empty question list or an empty verdict.

    What the rule costs: an answer genuinely shorter than an example preceding it is still
    mis-read. Nothing in a page of prose distinguishes the two, and the shorter answer is the
    rarer shape.
    """
    text = text.strip()
    if not text:
        return None
    candidates = [text]
    if "```" in text:
        for block in text.split("```")[1::2]:
            # ```json, ```jsonc, ```JSON: a fence carries its info string on a line of its own,
            # and a first line that opens a JSON value is content rather than an info string.
            info, _, body = block.partition("\n")
            head = info.strip()
            candidates.append((block if not head or head[0] in "{[" else body).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    best: dict[str, Any] | None = None
    best_size = -1
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and len(candidate) >= best_size:
            best, best_size = obj, len(candidate)
    return best


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


def spec_from_agent(data: dict[str, Any]) -> Spec:
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
