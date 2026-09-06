import tempfile
import unittest
from pathlib import Path

from application import (
    ApplicationAccepted,
    ApplicationErrorCode,
    CommandEnvelope,
    LocalOrchestrator,
    command_document,
    state_document,
)
from domain.commands import ApplyGateDecisionPayload, Command, SealArtifactPayload
from domain.references import ArtifactRef
from domain.sealing import digest_bytes
from domain.vocabulary import ArtifactKind, CommandName, Gate, GateVerdict, Phase
from persistence import LocalRepository, Persisted
from policy import EvaluationContext, build_policy
from validation import build_fact_bundle
from tests.application.support import (
    close_envelope,
    create_envelope,
    start_attempt_envelope,
)


class LocalOrchestratorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "repository"
        self.repository = LocalRepository(self.root)
        self.orchestrator = LocalOrchestrator(self.repository)

    def journal_lines(self):
        path = self.repository.journal.path
        return path.read_bytes().splitlines() if path.exists() else []

    def test_create_apply_reconstruct_and_restart(self):
        created = self.orchestrator.execute(create_envelope())
        self.assertIsInstance(created, ApplicationAccepted)
        self.assertEqual(created.value.state_version_after, 1)
        closed = self.orchestrator.execute(close_envelope())
        self.assertEqual(closed.value.state_version_after, 2)
        self.assertEqual(closed.value.state.phase, Phase.CLOSED)

        restarted = LocalOrchestrator(LocalRepository(self.root))
        snapshot = restarted.reconstruct().value
        self.assertEqual(snapshot.state_version, 2)
        self.assertEqual(snapshot.state_for("INC-A"), closed.value.state)

    def test_exact_replay_precedes_version_check_and_conflict_is_stable(self):
        first = self.orchestrator.execute(create_envelope())
        self.orchestrator.execute(close_envelope())
        replay = LocalOrchestrator(LocalRepository(self.root)).execute(create_envelope())
        self.assertTrue(replay.value.replayed)
        self.assertEqual(replay.value.state, first.value.state)
        self.assertEqual(replay.value.state_version_after, 1)
        self.assertEqual(replay.value.current_state_version, 2)

        conflict = self.orchestrator.execute(create_envelope(profile="strict"))
        self.assertEqual(conflict.code, ApplicationErrorCode.COMMAND_CONFLICT)
        self.assertEqual(len(self.journal_lines()), 2)

    def test_stale_and_domain_refusals_do_not_append(self):
        self.orchestrator.execute(create_envelope())
        before = self.repository.journal.path.read_bytes()
        stale = self.orchestrator.execute(
            close_envelope(command_id="stale", version=0)
        )
        self.assertEqual(stale.code, ApplicationErrorCode.STATE_VERSION_MISMATCH)
        self.assertEqual(self.repository.journal.path.read_bytes(), before)

        invalid_transition = self.orchestrator.execute(
            close_envelope(command_id="invalid", target=Phase.SPECIFYING)
        )
        self.assertEqual(invalid_transition.code, ApplicationErrorCode.DOMAIN_REFUSED)
        self.assertEqual(self.repository.journal.path.read_bytes(), before)

    def test_multiple_increments_are_reconstructed_independently(self):
        self.orchestrator.execute(create_envelope("INC-A", version=0))
        self.orchestrator.execute(
            create_envelope("INC-B", command_id="create-b", version=1)
        )
        snapshot = self.orchestrator.reconstruct().value
        self.assertEqual(tuple(key for key, _ in snapshot.increments), ("INC-A", "INC-B"))
        self.assertEqual(snapshot.state_version, 2)

    def test_sealed_bytes_are_verified_during_reconstruction(self):
        self.orchestrator.execute(create_envelope())
        raw = b"sealed-content"
        artifact = ArtifactRef(
            "artifact",
            1,
            ArtifactKind.DESIGN,
            "1",
            digest_bytes(raw),
        )
        sealed = self.orchestrator.execute(
            CommandEnvelope(
                "INC-A",
                Command(
                    "seal",
                    CommandName.SEAL_ARTIFACT,
                    1,
                    SealArtifactPayload(artifact, raw, True),
                ),
            )
        )
        self.assertIsInstance(sealed, ApplicationAccepted)
        object_path = (
            self.root
            / "objects/sha256"
            / artifact.digest.removeprefix("sha256:")
        )
        self.assertEqual(object_path.read_bytes(), raw)
        object_path.unlink()
        refusal = self.orchestrator.reconstruct()
        self.assertEqual(refusal.code, ApplicationErrorCode.PERSISTENCE_REFUSED)
        self.assertEqual(refusal.source_code, "OBJECT_MISSING")

    def test_corrupt_snapshot_blocks_reconstruction(self):
        stored = self.repository.execute(
            command_id="corrupt",
            expected_state_version=0,
            command={"name": "corrupt"},
            result={
                "increment_id": "INC-A",
                "schema_version": "application-state-1",
                "state": {
                    "schema_version": "application-codec-1",
                    "value": {"$type": "Unknown"},
                },
            },
        )
        self.assertIsInstance(stored, Persisted)
        refusal = self.orchestrator.reconstruct()
        self.assertEqual(refusal.code, ApplicationErrorCode.SNAPSHOT_INVALID)

    def test_snapshot_is_bound_to_the_event_increment(self):
        envelope = create_envelope("INC-A")
        state = LocalOrchestrator(LocalRepository(self.root)).execute(envelope).value.state
        second_root = self.root.parent / "other-repository"
        repository = LocalRepository(second_root)
        mismatched = repository.execute(
            command_id=envelope.command.command_id,
            expected_state_version=0,
            command=command_document(
                CommandEnvelope("INC-B", envelope.command)
            ),
            result=state_document(state),
            event_type="DomainCommandApplied",
        )
        self.assertIsInstance(mismatched, Persisted)
        refusal = LocalOrchestrator(repository).reconstruct()
        self.assertEqual(refusal.code, ApplicationErrorCode.SNAPSHOT_INVALID)
        self.assertEqual(refusal.details, ("event_binding",))

    def test_gate_evaluation_is_pure_and_application_is_explicit(self):
        self.orchestrator.execute(create_envelope())
        self.orchestrator.execute(start_attempt_envelope())
        policy = build_policy(
            {
                "schema_version": "policy-1",
                "gate": "G0",
                "root": {
                    "operator": "capability_satisfied",
                    "obligation": "ready",
                    "key": "ready",
                },
            }
        ).value
        facts = build_fact_bundle(capabilities=("ready",)).value
        context = EvaluationContext("decision-g0", "engine-1", 2, "sha256:facts")
        before = self.repository.journal.path.read_bytes()
        evaluated = self.orchestrator.evaluate("INC-A", Gate.G0, policy, facts, context)
        self.assertEqual(evaluated.value.decision.verdict, GateVerdict.PASS)
        self.assertEqual(self.repository.journal.path.read_bytes(), before)

        applied = self.orchestrator.execute(
            CommandEnvelope(
                "INC-A",
                Command(
                    "apply-g0",
                    CommandName.APPLY_GATE_DECISION,
                    2,
                    ApplyGateDecisionPayload(
                        evaluated.value.decision, Phase.SPECIFYING
                    ),
                ),
            )
        )
        self.assertEqual(applied.value.state.phase, Phase.SPECIFYING)
        self.assertEqual(applied.value.state_version_after, 3)
